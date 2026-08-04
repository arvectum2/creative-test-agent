#!/usr/bin/env python3
"""Run PRE-PILOT-006 in an isolated synthetic workspace.

The automated drill creates a complete PRE-TZ demo, generates the provisional
one-page report, takes and validates a backup, deliberately damages database
records and local files, restores the backup, restarts the data layer and
verifies the critical workflow evidence.

It does not pretend that a human operator completed the usability rehearsal.
A separate blank sign-off checklist is generated for that purpose.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import shutil
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.backup_common import load_backup_manifest, sha256_file, validate_backup
from scripts.backup_data import create_backup
from scripts.restore_data import restore_backup
from scripts.operator_rehearsal_checklist import blank_operator_checklist as _blank_operator_checklist

REHEARSAL_ID = "PRE-PILOT-006"
REHEARSAL_VERSION = "1.0.0"
_REQUIRED_AUTOMATED_CHECKS = {
    "demo_completed",
    "one_page_report_generated",
    "backup_validated",
    "damage_confirmed",
    "restore_verified",
    "database_integrity_verified",
    "immutable_import_verified",
    "data_review_report_verified",
    "one_page_artifacts_verified",
    "quantitative_evidence_verified",
    "pre_restore_backup_verified",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_reset(path: Path) -> None:
    target = path.expanduser().resolve()
    forbidden = {Path("/").resolve(), Path.home().resolve(), Path.cwd().resolve(), REPOSITORY_ROOT.resolve()}
    if target in forbidden or len(target.parts) < 3:
        raise ValueError(f"Refusing to reset unsafe rehearsal workspace: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sqlite_integrity(path: Path) -> str:
    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "no-result"
    finally:
        connection.close()


def _set_recovery_marker(database: Path, value: str) -> None:
    connection = sqlite3.connect(str(database))
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS operator_recovery_marker "
            "(id TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO operator_recovery_marker (id, value, updated_at) VALUES (?, ?, ?)",
            (REHEARSAL_ID, value, _utc_now()),
        )
        connection.commit()
    finally:
        connection.close()


def _get_recovery_marker(database: Path) -> str | None:
    connection = sqlite3.connect(str(database))
    try:
        row = connection.execute(
            "SELECT value FROM operator_recovery_marker WHERE id = ?", (REHEARSAL_ID,)
        ).fetchone()
        return str(row[0]) if row else None
    finally:
        connection.close()


def _delete_report_records(database: Path, *, data_review_report_id: str, one_page_report_id: str) -> None:
    connection = sqlite3.connect(str(database))
    try:
        connection.execute("DELETE FROM data_review_report_run WHERE id = ?", (data_review_report_id,))
        connection.execute("DELETE FROM client_one_page_report_run WHERE id = ?", (one_page_report_id,))
        connection.commit()
    finally:
        connection.close()


@contextmanager
def _workspace_settings(live: Path, backup_root: Path) -> Iterator[None]:
    from src.shared.config.settings import get_settings
    from src.shared.db.session import close_db

    settings = get_settings()
    fields = (
        "database_url",
        "storage_root",
        "exports_root",
        "backup_root",
        "backup_include_uploads",
        "backup_include_exports",
        "local_only_mode",
        "allow_cloud_llm",
        "enable_auth",
        "host",
        "port",
        "public_base_url",
        "trusted_hosts",
        "cors_allowed_origins",
    )
    original = {name: getattr(settings, name) for name in fields}
    settings.database_url = f"sqlite:///{live / 'creative_test_agent_demo.db'}"
    settings.storage_root = str(live / "storage")
    settings.exports_root = str(live / "exports")
    settings.backup_root = str(backup_root)
    settings.backup_include_uploads = True
    settings.backup_include_exports = True
    settings.local_only_mode = True
    settings.allow_cloud_llm = False
    settings.enable_auth = False
    settings.host = "127.0.0.1"
    settings.port = 8000
    settings.public_base_url = "http://localhost:8000"
    settings.trusted_hosts = "localhost,127.0.0.1,test,testserver"
    settings.cors_allowed_origins = ""
    close_db()
    try:
        yield
    finally:
        close_db()
        for name, value in original.items():
            setattr(settings, name, value)


def _phase(timeline: list[dict[str, Any]], name: str):
    class Phase:
        def __enter__(self):
            self.started = time.perf_counter()
            self.started_at = _utc_now()
            return self

        def __exit__(self, exc_type, exc, _tb):
            timeline.append(
                {
                    "phase": name,
                    "started_at": self.started_at,
                    "completed_at": _utc_now(),
                    "duration_seconds": round(time.perf_counter() - self.started, 4),
                    "status": "failed" if exc_type else "passed",
                    "error": str(exc) if exc else "",
                }
            )
            return False

    return Phase()


def _critical_file(path: Path, root: Path, artifact_type: str) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "path_relative_to_live_workspace": str(path.resolve().relative_to(root.resolve())),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }




def _finalize_rehearsal(
    *,
    root: Path,
    live: Path,
    evidence_dir: Path,
    manifest_path: Path,
    timeline: list[dict[str, Any]],
    checks: dict[str, dict[str, Any]],
    started: float,
    demo: dict[str, Any],
    one_page: Any,
    primary_backup: Path,
    critical_files: list[dict[str, Any]],
) -> dict[str, Any]:
    operator_checklist = _blank_operator_checklist()
    checklist_path = evidence_dir / "operator_checklist.json"
    _write_json(checklist_path, operator_checklist)

    timeline_path = evidence_dir / "automated_timeline.csv"
    with timeline_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["phase", "started_at", "completed_at", "duration_seconds", "status", "error"],
        )
        writer.writeheader()
        writer.writerows(timeline)

    missing_checks = sorted(_REQUIRED_AUTOMATED_CHECKS - set(checks))
    failed_checks = sorted(name for name, result in checks.items() if result["status"] != "passed")
    overall_pass = not missing_checks and not failed_checks
    total_seconds = round(time.perf_counter() - started, 4)
    manifest = {
        "rehearsal_id": REHEARSAL_ID,
        "rehearsal_version": REHEARSAL_VERSION,
        "status": "passed" if overall_pass else "failed",
        "generated_at": _utc_now(),
        "workspace": str(root),
        "live_workspace": str(live),
        "synthetic_data_only": True,
        "contains_client_data": False,
        "local_only": True,
        "automated_recovery_drill_completed": overall_pass,
        "human_operator_signoff_completed": False,
        "human_usability_proven": False,
        "developer_assistance_absence_proven": False,
        "same_configured_paths_required_for_restore": True,
        "total_duration_seconds": total_seconds,
        "platform": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "project": demo["project"],
        "runs": {
            "data_quality_run_id": demo["data_quality"]["run_id"],
            "prediction_readiness_run_id": demo["prediction_readiness"]["run_id"],
            "quantitative_study_id": demo["quantitative_proxy"]["study_id"],
            "data_review_report_id": demo["report"]["id"],
            "client_one_page_report_id": one_page.id,
        },
        "primary_backup": {
            "path": str(primary_backup),
            "manifest": load_backup_manifest(primary_backup),
            "validation_errors": validate_backup(primary_backup),
        },
        "pre_restore_backup": checks["pre_restore_backup_verified"]["evidence"],
        "automated_checks": checks,
        "required_automated_checks": sorted(_REQUIRED_AUTOMATED_CHECKS),
        "missing_automated_checks": missing_checks,
        "failed_automated_checks": failed_checks,
        "critical_files": critical_files,
        "timeline_file": str(timeline_path.relative_to(root)),
        "operator_checklist_file": str(checklist_path.relative_to(root)),
        "evidence_boundary": {
            "automated_drill_is_not_human_signoff": True,
            "recovery_success_is_not_model_accuracy": True,
            "synthetic_results_are_not_market_results": True,
            "no_client_data_used": True,
            "prediction_generated": False,
        },
    }
    _write_json(manifest_path, manifest)

    report_path = evidence_dir / "automated_rehearsal_report.md"
    report_path.write_text(
        "\n".join(
            [
                f"# {REHEARSAL_ID} — automated operator/recovery rehearsal",
                "",
                f"Status: **{manifest['status'].upper()}**",
                f"Duration: {total_seconds:.2f} seconds",
                "",
                "## Verified automatically",
                "",
                *[f"- {name}: {result['status']}" for name, result in sorted(checks.items())],
                "",
                "## Evidence boundary",
                "",
                "This run proves that the synthetic workspace can be backed up, deliberately damaged, restored at the same configured paths and reopened with its critical records and files intact.",
                "",
                "It does not prove that a non-developer operator can complete the workflow unaided. Complete evidence/operator_checklist.json during a separate observed session.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    evidence_files = [manifest_path, checklist_path, timeline_path, report_path]
    evidence_manifest = {
        "rehearsal_id": REHEARSAL_ID,
        "generated_at": _utc_now(),
        "files": [
            {
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in evidence_files
        ],
    }
    _write_json(root / "evidence_manifest.json", evidence_manifest)
    return manifest


def run_rehearsal(workspace: str | Path, *, respondent_count: int = 12, reset: bool = True) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    if reset:
        _safe_reset(root)
    else:
        root.mkdir(parents=True, exist_ok=True)
    live = root / "live"
    backups = root / "backups"
    evidence_dir = root / "evidence"
    backups.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "rehearsal_manifest.json"
    timeline: list[dict[str, Any]] = []
    checks: dict[str, dict[str, Any]] = {}
    started = time.perf_counter()

    def record(name: str, passed: bool, evidence: Any = None) -> None:
        checks[name] = {"status": "passed" if passed else "failed", "evidence": evidence}
        if not passed:
            raise RuntimeError(f"Automated rehearsal check failed: {name}")

    try:
        with _phase(timeline, "build_complete_synthetic_workflow"):
            from src.modules.pre_tz_demo import run_messy_demo

            demo = run_messy_demo(live, reset=True, respondent_count=respondent_count)
            record("demo_completed", demo.get("status") == "completed", demo.get("demo"))

        database = live / "creative_test_agent_demo.db"
        storage = live / "storage"
        exports = live / "exports"
        primary_backup = backups / "pre_pilot_006_primary.zip"

        with _workspace_settings(live, backups):
            from src.shared.db.session import init_db, close_db

            init_db()
            with _phase(timeline, "generate_provisional_one_page_report"):
                from src.modules.client_one_page_reports.secure_download import (
                    secure_client_one_page_artifact_path,
                )
                from src.modules.client_one_page_reports.service import (
                    generate_client_one_page_report,
                )

                one_page = generate_client_one_page_report(
                    demo["data_quality"]["run_id"],
                    prediction_readiness_run_id=demo["prediction_readiness"]["run_id"],
                    quantitative_study_id=demo["quantitative_proxy"]["study_id"],
                    locale="ru",
                    force=True,
                )
                one_page_files: list[dict[str, Any]] = []
                for artifact_type in ("pptx", "html", "evidence", "manifest"):
                    path, _filename, _media_type = secure_client_one_page_artifact_path(
                        one_page.id, artifact_type
                    )
                    one_page_files.append(_critical_file(Path(path), live, artifact_type))
                record(
                    "one_page_report_generated",
                    one_page.slide_count == 1 and {item["artifact_type"] for item in one_page_files}
                    == {"pptx", "html", "evidence", "manifest"},
                    {"report_id": one_page.id, "verdict": one_page.verdict},
                )

            export_sentinel = exports / "operator_recovery_export.json"
            export_sentinel.parent.mkdir(parents=True, exist_ok=True)
            _write_json(
                export_sentinel,
                {
                    "rehearsal_id": REHEARSAL_ID,
                    "project_id": demo["project"]["id"],
                    "not_client_data": True,
                },
            )
            _set_recovery_marker(database, "baseline")
            data_review_path = Path(demo["report"]["path"])
            critical_files = [
                _critical_file(data_review_path, live, "data_review_xlsx"),
                _critical_file(export_sentinel, live, "export_sentinel"),
                *one_page_files,
            ]

            with _phase(timeline, "create_and_validate_primary_backup"):
                close_db()
                created_backup = Path(create_backup(str(primary_backup))).resolve()
                backup_errors = validate_backup(created_backup)
                record(
                    "backup_validated",
                    not backup_errors,
                    {
                        "path": str(created_backup),
                        "errors": backup_errors,
                        "manifest": load_backup_manifest(created_backup),
                    },
                )

            with _phase(timeline, "simulate_recoverable_loss"):
                _set_recovery_marker(database, "damaged")
                _delete_report_records(
                    database,
                    data_review_report_id=demo["report"]["id"],
                    one_page_report_id=one_page.id,
                )
                shutil.rmtree(storage)
                shutil.rmtree(exports)
                storage.mkdir(parents=True)
                exports.mkdir(parents=True)
                (storage / "damage-marker.txt").write_text("simulated loss\n", encoding="utf-8")
                (exports / "damage-marker.txt").write_text("simulated loss\n", encoding="utf-8")
                record(
                    "damage_confirmed",
                    _get_recovery_marker(database) == "damaged" and not data_review_path.exists(),
                    "report records removed and storage/exports replaced",
                )

            with _phase(timeline, "restore_and_verify_payload"):
                restore_result = restore_backup(
                    str(primary_backup),
                    force=True,
                    create_pre_restore_backup=True,
                )
                record("restore_verified", bool(restore_result.get("verified")), restore_result)
                pre_restore_path = Path(str(restore_result.get("pre_restore_backup_path")))
                pre_restore_errors = validate_backup(pre_restore_path)
                record(
                    "pre_restore_backup_verified",
                    pre_restore_path.is_file() and not pre_restore_errors,
                    {"path": str(pre_restore_path), "errors": pre_restore_errors},
                )

            with _phase(timeline, "restart_data_layer_and_verify_workflow"):
                close_db()
                init_db()
                integrity_result = _sqlite_integrity(database)
                record(
                    "database_integrity_verified",
                    integrity_result.lower() == "ok" and _get_recovery_marker(database) == "baseline",
                    {"pragma_integrity_check": integrity_result, "marker": _get_recovery_marker(database)},
                )

                from src.modules.import_sessions.service import verify_import_session
                import_integrity = verify_import_session(demo["import"]["session_id"])
                record(
                    "immutable_import_verified",
                    bool(import_integrity.ok),
                    {"session_id": demo["import"]["session_id"], "ok": import_integrity.ok},
                )

                from src.modules.data_review_reports.service import (
                    data_review_report_path,
                    get_data_review_report,
                )
                restored_review = get_data_review_report(demo["report"]["id"])
                restored_review_path, _ = data_review_report_path(demo["report"]["id"])
                record(
                    "data_review_report_verified",
                    restored_review is not None
                    and sha256_file(restored_review_path) == demo["report"]["sha256"],
                    {"report_id": demo["report"]["id"], "sha256": demo["report"]["sha256"]},
                )

                from src.modules.client_one_page_reports.service import get_client_one_page_report
                restored_one_page = get_client_one_page_report(one_page.id)
                restored_artifacts = []
                for artifact in one_page_files:
                    path, _filename, _media_type = secure_client_one_page_artifact_path(
                        one_page.id, artifact["artifact_type"]
                    )
                    restored_artifacts.append(
                        {
                            "artifact_type": artifact["artifact_type"],
                            "sha256": sha256_file(path),
                            "expected_sha256": artifact["sha256"],
                        }
                    )
                record(
                    "one_page_artifacts_verified",
                    restored_one_page is not None
                    and all(item["sha256"] == item["expected_sha256"] for item in restored_artifacts),
                    restored_artifacts,
                )

                from src.modules.quantitative_surveys.service import study_results
                survey = study_results(demo["quantitative_proxy"]["study_id"])
                record(
                    "quantitative_evidence_verified",
                    survey.total_responses == demo["quantitative_proxy"]["response_count"]
                    and survey.source_counts.get("synthetic", 0) == survey.total_responses,
                    {
                        "total_responses": survey.total_responses,
                        "source_counts": survey.source_counts,
                    },
                )

                file_results = []
                for item in critical_files:
                    path = live / item["path_relative_to_live_workspace"]
                    file_results.append(
                        {
                            "artifact_type": item["artifact_type"],
                            "exists": path.is_file(),
                            "sha256": sha256_file(path) if path.is_file() else None,
                            "expected_sha256": item["sha256"],
                        }
                    )
                record(
                    "critical_file_set_verified",
                    all(item["exists"] and item["sha256"] == item["expected_sha256"] for item in file_results),
                    file_results,
                )

        return _finalize_rehearsal(
            root=root,
            live=live,
            evidence_dir=evidence_dir,
            manifest_path=manifest_path,
            timeline=timeline,
            checks=checks,
            started=started,
            demo=demo,
            one_page=one_page,
            primary_backup=primary_backup,
            critical_files=critical_files,
        )
    except Exception as exc:
        failure = {
            "rehearsal_id": REHEARSAL_ID,
            "rehearsal_version": REHEARSAL_VERSION,
            "status": "failed",
            "generated_at": _utc_now(),
            "workspace": str(root),
            "synthetic_data_only": True,
            "human_operator_signoff_completed": False,
            "automated_checks": checks,
            "timeline": timeline,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _write_json(manifest_path, failure)
        raise


def validate_rehearsal(workspace: str | Path) -> list[str]:
    root = Path(workspace).expanduser().resolve()
    errors: list[str] = []
    manifest_path = root / "rehearsal_manifest.json"
    evidence_manifest_path = root / "evidence_manifest.json"
    if not manifest_path.is_file():
        return ["rehearsal_manifest.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"rehearsal_manifest.json is invalid: {exc}"]
    if manifest.get("rehearsal_id") != REHEARSAL_ID:
        errors.append("unexpected rehearsal_id")
    if manifest.get("rehearsal_version") != REHEARSAL_VERSION:
        errors.append("unexpected rehearsal_version")
    if manifest.get("status") != "passed":
        errors.append("automated rehearsal status is not passed")
    if manifest.get("human_operator_signoff_completed") is not False:
        errors.append("automated self-test must not claim human operator sign-off")
    if manifest.get("human_usability_proven") is not False:
        errors.append("automated self-test must not claim human usability")
    checks = manifest.get("automated_checks", {})
    missing = sorted(_REQUIRED_AUTOMATED_CHECKS - set(checks))
    if missing:
        errors.append("missing required automated checks: " + ", ".join(missing))
    failed = sorted(name for name, item in checks.items() if item.get("status") != "passed")
    if failed:
        errors.append("failed automated checks: " + ", ".join(failed))
    primary_path = Path(manifest.get("primary_backup", {}).get("path", ""))
    primary_errors = validate_backup(primary_path)
    if primary_errors:
        errors.append("primary backup invalid: " + "; ".join(primary_errors))
    pre_path = Path(manifest.get("pre_restore_backup", {}).get("path", ""))
    pre_errors = validate_backup(pre_path)
    if pre_errors:
        errors.append("pre-restore backup invalid: " + "; ".join(pre_errors))

    if not evidence_manifest_path.is_file():
        errors.append("evidence_manifest.json is missing")
    else:
        try:
            evidence = json.loads(evidence_manifest_path.read_text(encoding="utf-8"))
            for item in evidence.get("files", []):
                path = root / item["path"]
                if not path.is_file():
                    errors.append(f"evidence file missing: {item['path']}")
                elif path.stat().st_size != item["size_bytes"]:
                    errors.append(f"evidence size mismatch: {item['path']}")
                elif sha256_file(path) != item["sha256"]:
                    errors.append(f"evidence SHA-256 mismatch: {item['path']}")
        except Exception as exc:
            errors.append(f"evidence_manifest.json is invalid: {exc}")

    checklist_path = root / manifest.get("operator_checklist_file", "")
    if not checklist_path.is_file():
        errors.append("operator checklist is missing")
    else:
        checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
        if checklist.get("final_decision") != "not_started":
            errors.append("generated operator checklist must remain unsigned")
        if checklist.get("automated_drill_is_human_signoff") is not False:
            errors.append("operator checklist mislabels automated evidence")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PRE-PILOT-006 operator and recovery rehearsal")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run the isolated automated recovery drill")
    run.add_argument("--workspace", default="data/rehearsals/pre_pilot_006")
    run.add_argument("--respondent-count", type=int, default=12)
    run.add_argument("--keep-existing", action="store_true")
    validate = subparsers.add_parser("validate", help="Validate a completed rehearsal workspace")
    validate.add_argument("--input", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run":
        try:
            manifest = run_rehearsal(
                args.workspace,
                respondent_count=args.respondent_count,
                reset=not args.keep_existing,
            )
        except Exception as exc:
            print(f"Operator recovery rehearsal failed: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "rehearsal_id": manifest["rehearsal_id"],
                    "status": manifest["status"],
                    "workspace": manifest["workspace"],
                    "duration_seconds": manifest["total_duration_seconds"],
                    "human_operator_signoff_completed": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    errors = validate_rehearsal(args.input)
    if errors:
        print("Rehearsal validation: FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Rehearsal validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
