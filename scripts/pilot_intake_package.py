from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

PACKAGE_ID = "creative-test-agent-pilot-intake"
PACKAGE_VERSION = "1.0.0"
DEFAULT_OUTPUT = Path("data/generated/pilot_intake_template/v1")

REQUIRED_MATERIAL_CATEGORIES = ("creative", "brief", "audience", "evaluation_criteria")
OPTIONAL_MATERIAL_CATEGORIES = (
    "brandbook",
    "historical_campaign_data",
    "compliance_rules",
    "reference_report",
    "other",
)
ALLOWED_MATERIAL_CATEGORIES = set(REQUIRED_MATERIAL_CATEGORIES + OPTIONAL_MATERIAL_CATEGORIES)
ALLOWED_STATUSES = {"provided", "not_available", "pending", "not_applicable"}
ALLOWED_CONFIDENTIALITY = {"nda_restricted", "internal", "synthetic"}
ALLOWED_RELATION_TYPES = {
    "creative_to_history",
    "creative_to_brief",
    "creative_to_audience",
    "creative_to_brandbook",
    "creative_variant",
    "other",
}
ACCEPTANCE_METRICS = (
    "time_to_first_report_minutes",
    "operator_touch_time_minutes",
    "manual_mapping_count",
    "clarification_question_count",
    "unresolved_blocker_count",
    "successful_closed_loop_rate",
    "repeat_run_consistency",
    "expert_agreement",
    "report_revision_count",
)
CONTROL_FILES = (
    "README.md",
    "client_intake_manifest.json",
    "pilot_acceptance_plan.json",
    "file_register.csv",
    "relationship_hints.csv",
)


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def build_intake_manifest() -> dict[str, Any]:
    return {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "client": {
            "name": "FICTIONAL CLIENT",
            "industry": "pharmaceutical-marketing-demo",
            "contact_name": "",
            "contact_email": "",
        },
        "project": {
            "name": "Synthetic pilot intake",
            "description": "Template only. Replace after receipt of real materials.",
            "requested_decision": "Select which creative variants require revision before handoff.",
            "planned_creative_count": 20,
            "working_language": "ru",
        },
        "handling": {
            "confidentiality": "synthetic",
            "local_only_processing_required": True,
            "cloud_transfer_allowed": False,
            "originals_must_remain_immutable": True,
            "retain_until": "",
            "deletion_confirmed_after_pilot": False,
            "notes": "For real client work set confidentiality to nda_restricted and complete retention terms.",
        },
        "intake_policy": {
            "files_may_be_sent_as_is": True,
            "mandatory_client_schema": False,
            "mandatory_file_renaming": False,
            "internal_mapping_and_normalization": True,
            "clarification_question_limit_per_batch": 5,
            "clarification_questions_must_be_evidence_backed": True,
        },
        "materials": [
            {
                "category": category,
                "status": "pending",
                "required_for_intake": True,
                "description": "",
                "expected_location": "materials/",
                "notes": "",
            }
            for category in REQUIRED_MATERIAL_CATEGORIES
        ]
        + [
            {
                "category": category,
                "status": "pending",
                "required_for_intake": False,
                "description": "",
                "expected_location": "materials/",
                "notes": "Optional; absence must appear in readiness and report limitations.",
            }
            for category in OPTIONAL_MATERIAL_CATEGORIES
        ],
        "known_relationships": [],
        "known_limitations": [
            "No model-accuracy promise is accepted before calibration on real data.",
            "Synthetic or proxy responses must not be represented as real respondents.",
            "Historical CTR must not be presented as causal creative lift.",
            "Missing source data must produce an explicit unavailable or degraded capability.",
        ],
        "signoff": {
            "client_materials_confirmed_by": "",
            "client_materials_confirmed_at": "",
            "analyst_intake_confirmed_by": "",
            "analyst_intake_confirmed_at": "",
        },
    }


def build_acceptance_plan() -> dict[str, Any]:
    gates = [
        ("G1_intake_integrity", "Immutable and traceable intake", True, [
            "Every received file has a registered relative path, byte size and SHA-256.",
            "Original bytes are not modified after registration.",
            "The intake manifest records confidentiality and local-only handling.",
        ]),
        ("G2_data_understanding", "Data structure and gaps are explicit", True, [
            "Tabular files are inspected without requiring a client-specific schema.",
            "Mappings are analyst-confirmed rather than silently accepted.",
            "Blocking gaps are represented as quality issues and clarification questions.",
        ]),
        ("G3_capability_honesty", "Capabilities degrade safely", True, [
            "Each capability has a separate available, degraded, unavailable or blocked decision.",
            "No CTR, lift, accuracy or respondent evidence is fabricated.",
            "Limitations and prohibited claims are visible in outputs.",
        ]),
        ("G4_closed_loop_execution", "Operator can complete the workflow", True, [
            "At least one full intake-to-report run completes on the target workstation.",
            "A repeated run is reproducible under unchanged inputs.",
            "The analyst can trace a report statement back to source evidence.",
        ]),
        ("G5_expert_usefulness", "Output is useful to expert reviewers", False, [
            "Client or agency experts review every pilot creative or a pre-agreed sample.",
            "Disagreements are recorded at finding level rather than hidden in an average score.",
            "At least one report revision cycle is measured and documented.",
        ]),
        ("G6_operational_exit", "Pilot can be closed safely", True, [
            "Backup and restore have been exercised or explicitly waived.",
            "Retention and deletion actions are recorded.",
            "Known unresolved risks are accepted, assigned or carried into the next phase.",
        ]),
    ]
    metric_specs = {
        "time_to_first_report_minutes": ("minutes", "lower_is_better", "record baseline; proposed pilot target <= 60", "workflow timestamps"),
        "operator_touch_time_minutes": ("minutes", "lower_is_better", "record baseline; no fixed promise before pilot", "operator activity log"),
        "manual_mapping_count": ("count", "lower_is_better", "measure by source table", "mapping decisions"),
        "clarification_question_count": ("count", "contextual", "3-5 per evidence-backed batch; fewer when fewer material gaps exist", "clarification runs"),
        "unresolved_blocker_count": ("count", "lower_is_better", "0 before client-facing conclusion", "data quality and readiness"),
        "successful_closed_loop_rate": ("ratio", "higher_is_better", "proposed pilot target >= 0.90; confirm after first runs", "completed versus attempted workflows"),
        "repeat_run_consistency": ("ratio", "higher_is_better", "measure unchanged-input agreement; threshold not final", "repeated run comparison"),
        "expert_agreement": ("ratio_and_disagreement_log", "higher_is_better", "baseline only; no accuracy promise", "expert finding-level review"),
        "report_revision_count": ("count", "lower_is_better_after_learning", "record all revisions and reasons", "versioned report history"),
    }
    return {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "status": "provisional_before_real_materials",
        "evidence_boundary": {
            "technical_readiness_is_not_model_accuracy": True,
            "synthetic_results_are_not_market_results": True,
            "client_methodology_is_not_final": True,
            "final_thresholds_require_real_pilot_data": True,
        },
        "gates": [
            {"gate_id": gate_id, "title": title, "blocking": blocking, "pass_when": pass_when}
            for gate_id, title, blocking, pass_when in gates
        ],
        "metrics": [
            {
                "metric": metric,
                "unit": metric_specs[metric][0],
                "direction": metric_specs[metric][1],
                "provisional_target": metric_specs[metric][2],
                "source": metric_specs[metric][3],
            }
            for metric in ACCEPTANCE_METRICS
        ],
        "pilot_exit_decisions": [
            "accept_for_controlled_internal_use",
            "continue_calibration",
            "limit_to_descriptive_or_compliance_workflow",
            "pause_for_data_remediation",
            "stop_pilot",
        ],
        "signoff": {
            "technical_owner": "",
            "methodology_owner": "",
            "client_owner": "",
            "decision": "",
            "decision_date": "",
            "accepted_limitations": [],
        },
    }


def _file_register_rows() -> list[dict[str, str]]:
    return [
        {
            "record_id": f"F{index:03d}",
            "category": category,
            "relative_path": "",
            "original_filename": "",
            "media_type": "",
            "size_bytes": "",
            "sha256": "",
            "received_at": "",
            "status": "pending",
            "notes": "",
        }
        for index, category in enumerate(REQUIRED_MATERIAL_CATEGORIES + OPTIONAL_MATERIAL_CATEGORIES, start=1)
    ]


def _relationship_rows() -> list[dict[str, str]]:
    return [{
        "relation_id": "R001",
        "relation_type": "creative_to_history",
        "left_record_id": "",
        "right_reference": "",
        "confidence": "unknown",
        "source": "client_or_analyst",
        "notes": "Optional hint only; the system must not invent links.",
    }]


def _package_state(output_dir: Path) -> dict[str, Any]:
    intake = _read_json(output_dir / "client_intake_manifest.json")
    rows = _read_csv(output_dir / "file_register.csv")
    provided = [row for row in rows if (row.get("status") or "").strip() == "provided"]
    confidentiality = ((intake.get("handling") or {}).get("confidentiality") or "").strip()
    return {
        "template_only": not provided,
        "provided_file_count": len(provided),
        "contains_client_data": bool(provided) and confidentiality != "synthetic",
        "confidentiality": confidentiality,
    }


def seal(output_dir: Path) -> dict[str, Any]:
    missing = [name for name in CONTROL_FILES if not (output_dir / name).is_file()]
    if missing:
        raise ValueError("cannot seal package; missing control files: " + ", ".join(missing))
    state = _package_state(output_dir)
    manifest = {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        **state,
        "accuracy_promise": False,
        "prediction_generated": False,
        "real_respondents_used": False,
        "files": [
            {
                "filename": name,
                "size_bytes": (output_dir / name).stat().st_size,
                "sha256": _sha_file(output_dir / name),
            }
            for name in CONTROL_FILES
        ],
    }
    _write_json(output_dir / "package_manifest.json", manifest)
    return manifest


def generate(output_dir: Path, *, clean: bool = True) -> dict[str, Any]:
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "materials").mkdir()
    _write_json(output_dir / "client_intake_manifest.json", build_intake_manifest())
    _write_json(output_dir / "pilot_acceptance_plan.json", build_acceptance_plan())
    _write_csv(output_dir / "file_register.csv", [
        "record_id", "category", "relative_path", "original_filename", "media_type",
        "size_bytes", "sha256", "received_at", "status", "notes",
    ], _file_register_rows())
    _write_csv(output_dir / "relationship_hints.csv", [
        "relation_id", "relation_type", "left_record_id", "right_reference",
        "confidence", "source", "notes",
    ], _relationship_rows())
    (output_dir / "README.md").write_text(
        "# Creative Test Agent — pilot intake package\n\n"
        "Client files may be placed in `materials/` as received; renaming and a mandatory client schema are not required.\n\n"
        "1. Complete `client_intake_manifest.json`, including NDA/local-only and retention fields.\n"
        "2. Register every received file in `file_register.csv` with path, size and SHA-256.\n"
        "3. Add only known links to `relationship_hints.csv`; do not guess relationships.\n"
        "4. Review `pilot_acceptance_plan.json` with technical, methodology and client owners.\n"
        "5. Seal with `python scripts/pilot_intake_package.py seal --input <folder>`.\n"
        "6. Validate with `python scripts/pilot_intake_package.py validate --input <folder> --verify-registered-materials`.\n\n"
        "This package does not approve a model, promise accuracy, create real respondent evidence or convert historical CTR into causal creative lift.\n",
        encoding="utf-8",
    )
    return seal(output_dir)


def validate(output_dir: Path, *, verify_registered_materials: bool = False) -> list[str]:
    errors: list[str] = []
    required_files = set(CONTROL_FILES) | {"package_manifest.json"}
    missing = [name for name in sorted(required_files) if not (output_dir / name).is_file()]
    if missing:
        return ["missing package files: " + ", ".join(missing)]
    try:
        intake = _read_json(output_dir / "client_intake_manifest.json")
        acceptance = _read_json(output_dir / "pilot_acceptance_plan.json")
        manifest = _read_json(output_dir / "package_manifest.json")
        rows = _read_csv(output_dir / "file_register.csv")
        relations = _read_csv(output_dir / "relationship_hints.csv")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"package data is unreadable: {exc}"]

    if intake.get("package_id") != PACKAGE_ID or intake.get("package_version") != PACKAGE_VERSION:
        errors.append("unexpected intake package identity or version")
    handling = intake.get("handling") or {}
    confidentiality = handling.get("confidentiality")
    if confidentiality not in ALLOWED_CONFIDENTIALITY:
        errors.append("invalid confidentiality value")
    if handling.get("local_only_processing_required") is not True:
        errors.append("local_only_processing_required must be true")
    if handling.get("cloud_transfer_allowed") is not False:
        errors.append("cloud_transfer_allowed must be false")
    if handling.get("originals_must_remain_immutable") is not True:
        errors.append("originals_must_remain_immutable must be true")

    policy = intake.get("intake_policy") or {}
    if policy.get("files_may_be_sent_as_is") is not True:
        errors.append("files_may_be_sent_as_is must be true")
    if policy.get("mandatory_client_schema") is not False:
        errors.append("mandatory_client_schema must be false")
    if policy.get("mandatory_file_renaming") is not False:
        errors.append("mandatory_file_renaming must be false")
    limit = policy.get("clarification_question_limit_per_batch")
    if not isinstance(limit, int) or not 3 <= limit <= 5:
        errors.append("clarification question limit must be between 3 and 5")

    materials = intake.get("materials") or []
    categories = {item.get("category") for item in materials if isinstance(item, dict)}
    for category in REQUIRED_MATERIAL_CATEGORIES:
        if category not in categories:
            errors.append(f"missing required material category: {category}")
    for item in materials:
        if not isinstance(item, dict):
            errors.append("material entry must be an object")
        elif item.get("category") not in ALLOWED_MATERIAL_CATEGORIES:
            errors.append(f"invalid material category: {item.get('category')}")
        elif item.get("status") not in ALLOWED_STATUSES:
            errors.append(f"invalid material status for {item.get('category')}")

    required_gates = {
        "G1_intake_integrity", "G2_data_understanding", "G3_capability_honesty",
        "G4_closed_loop_execution", "G5_expert_usefulness", "G6_operational_exit",
    }
    gate_ids = {gate.get("gate_id") for gate in acceptance.get("gates", []) if isinstance(gate, dict)}
    for gate_id in sorted(required_gates - gate_ids):
        errors.append(f"missing acceptance gate: {gate_id}")
    metric_names = {metric.get("metric") for metric in acceptance.get("metrics", []) if isinstance(metric, dict)}
    for metric in ACCEPTANCE_METRICS:
        if metric not in metric_names:
            errors.append(f"missing acceptance metric: {metric}")
    boundary = acceptance.get("evidence_boundary") or {}
    for key in (
        "technical_readiness_is_not_model_accuracy",
        "synthetic_results_are_not_market_results",
        "client_methodology_is_not_final",
        "final_thresholds_require_real_pilot_data",
    ):
        if boundary.get(key) is not True:
            errors.append(f"acceptance evidence boundary missing: {key}")

    record_ids: set[str] = set()
    for row in rows:
        record_id = (row.get("record_id") or "").strip()
        if not record_id or record_id in record_ids:
            errors.append(f"invalid or duplicate file record_id: {record_id}")
            continue
        record_ids.add(record_id)
        category = (row.get("category") or "").strip()
        if category not in ALLOWED_MATERIAL_CATEGORIES:
            errors.append(f"invalid file category for {record_id}: {category}")
        status = (row.get("status") or "").strip()
        if status not in ALLOWED_STATUSES:
            errors.append(f"invalid file status for {record_id}: {status}")
        relative_path = (row.get("relative_path") or "").strip()
        if status == "provided" and not relative_path:
            errors.append(f"provided file has no relative_path: {record_id}")
            continue
        if not relative_path:
            continue
        target = (output_dir / relative_path).resolve(strict=False)
        try:
            target.relative_to(output_dir.resolve())
        except ValueError:
            errors.append(f"file path escapes package root: {record_id}")
            continue
        if verify_registered_materials or status == "provided":
            if not target.is_file():
                errors.append(f"registered material missing: {record_id}")
            else:
                size = (row.get("size_bytes") or "").strip()
                digest = (row.get("sha256") or "").strip().lower()
                if not size.isdigit() or int(size) != target.stat().st_size:
                    errors.append(f"size mismatch for {record_id}")
                if len(digest) != 64 or digest != _sha_file(target):
                    errors.append(f"SHA-256 mismatch for {record_id}")

    relation_ids: set[str] = set()
    for row in relations:
        relation_id = (row.get("relation_id") or "").strip()
        if not relation_id or relation_id in relation_ids:
            errors.append(f"invalid or duplicate relation_id: {relation_id}")
        relation_ids.add(relation_id)
        relation_type = (row.get("relation_type") or "").strip()
        if relation_type not in ALLOWED_RELATION_TYPES:
            errors.append(f"invalid relationship type for {relation_id}: {relation_type}")
        left = (row.get("left_record_id") or "").strip()
        right = (row.get("right_reference") or "").strip()
        if left and left not in record_ids:
            errors.append(f"unknown left_record_id for {relation_id}: {left}")
        if left and not right:
            errors.append(f"relationship has no right_reference: {relation_id}")

    expected_state = _package_state(output_dir)
    if manifest.get("package_id") != PACKAGE_ID or manifest.get("package_version") != PACKAGE_VERSION:
        errors.append("package manifest identity mismatch")
    for key, expected in expected_state.items():
        if manifest.get(key) != expected:
            errors.append(f"package manifest state mismatch: {key}")
    if manifest.get("accuracy_promise") is not False:
        errors.append("package must not make an accuracy promise")
    if manifest.get("prediction_generated") is not False or manifest.get("real_respondents_used") is not False:
        errors.append("intake package must not claim predictions or real respondents")
    manifest_files = {item.get("filename"): item for item in manifest.get("files", []) if isinstance(item, dict)}
    for name in CONTROL_FILES:
        entry = manifest_files.get(name)
        path = output_dir / name
        if not entry:
            errors.append(f"manifest entry missing: {name}")
        elif entry.get("size_bytes") != path.stat().st_size or entry.get("sha256") != _sha_file(path):
            errors.append(f"package manifest mismatch: {name}")
    return errors


def check_determinism() -> list[str]:
    with tempfile.TemporaryDirectory() as left_raw, tempfile.TemporaryDirectory() as right_raw:
        left, right = Path(left_raw), Path(right_raw)
        generate(left)
        generate(right)
        names = list(CONTROL_FILES) + ["package_manifest.json"]
        return [name for name in names if _sha_file(left / name) != _sha_file(right / name)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate, seal and validate the PRE-PILOT-004 package.")
    parser.add_argument("command", choices=("generate", "seal", "validate", "check-determinism"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--verify-registered-materials", action="store_true")
    args = parser.parse_args(argv)
    try:
        source = args.input or args.output
        if args.command == "generate":
            manifest = generate(args.output)
            print(json.dumps({"status": "generated", "output": str(args.output), **_package_state(args.output)}, sort_keys=True))
            return 0
        if args.command == "seal":
            manifest = seal(source)
            print(json.dumps({"status": "sealed", "input": str(source), **{key: manifest[key] for key in ("template_only", "contains_client_data", "provided_file_count")}}, sort_keys=True))
            return 0
        errors = check_determinism() if args.command == "check-determinism" else validate(
            source,
            verify_registered_materials=args.verify_registered_materials,
        )
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(json.dumps({"status": "valid", "command": args.command}, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
