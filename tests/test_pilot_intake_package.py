from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from scripts.pilot_intake_package import (
    ACCEPTANCE_METRICS,
    PACKAGE_ID,
    check_determinism,
    generate,
    seal,
    validate,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_generate_and_validate_template(tmp_path: Path):
    manifest = generate(tmp_path)

    assert manifest["package_id"] == PACKAGE_ID
    assert manifest["template_only"] is True
    assert manifest["contains_client_data"] is False
    assert manifest["provided_file_count"] == 0
    assert manifest["accuracy_promise"] is False
    assert validate(tmp_path) == []

    intake = json.loads((tmp_path / "client_intake_manifest.json").read_text(encoding="utf-8"))
    assert intake["intake_policy"]["files_may_be_sent_as_is"] is True
    assert intake["intake_policy"]["mandatory_client_schema"] is False
    assert intake["handling"]["local_only_processing_required"] is True
    assert intake["handling"]["cloud_transfer_allowed"] is False

    acceptance = json.loads((tmp_path / "pilot_acceptance_plan.json").read_text(encoding="utf-8"))
    assert {item["metric"] for item in acceptance["metrics"]} == set(ACCEPTANCE_METRICS)
    assert len(acceptance["gates"]) == 6
    assert acceptance["evidence_boundary"]["technical_readiness_is_not_model_accuracy"] is True


def test_completed_nda_intake_can_be_sealed_and_verified(tmp_path: Path):
    generate(tmp_path)
    material = tmp_path / "materials" / "creative-a.png"
    material.write_bytes(b"client creative bytes")

    intake_path = tmp_path / "client_intake_manifest.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    intake["handling"]["confidentiality"] = "nda_restricted"
    intake_path.write_text(
        json.dumps(intake, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = _read_rows(tmp_path / "file_register.csv")
    rows[0].update(
        {
            "relative_path": "materials/creative-a.png",
            "original_filename": "creative-a.png",
            "media_type": "image/png",
            "size_bytes": str(material.stat().st_size),
            "sha256": _sha(material),
            "status": "provided",
        }
    )
    _write_rows(tmp_path / "file_register.csv", rows)

    manifest = seal(tmp_path)
    assert manifest["template_only"] is False
    assert manifest["contains_client_data"] is True
    assert manifest["provided_file_count"] == 1
    assert manifest["confidentiality"] == "nda_restricted"
    assert validate(tmp_path, verify_registered_materials=True) == []

    material.write_bytes(b"changed")
    errors = validate(tmp_path, verify_registered_materials=True)
    assert "size mismatch for F001" in errors
    assert "SHA-256 mismatch for F001" in errors


def test_control_file_edits_require_resealing(tmp_path: Path):
    generate(tmp_path)
    intake_path = tmp_path / "client_intake_manifest.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    intake["project"]["name"] = "Updated project"
    intake_path.write_text(json.dumps(intake, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert "package manifest mismatch: client_intake_manifest.json" in validate(tmp_path)
    seal(tmp_path)
    assert validate(tmp_path) == []


def test_path_escape_and_cloud_transfer_are_rejected(tmp_path: Path):
    generate(tmp_path)
    intake_path = tmp_path / "client_intake_manifest.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    intake["handling"]["cloud_transfer_allowed"] = True
    intake_path.write_text(json.dumps(intake, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rows = _read_rows(tmp_path / "file_register.csv")
    rows[0]["relative_path"] = "../outside.bin"
    rows[0]["status"] = "provided"
    _write_rows(tmp_path / "file_register.csv", rows)
    seal(tmp_path)

    errors = validate(tmp_path)
    assert "cloud_transfer_allowed must be false" in errors
    assert "file path escapes package root: F001" in errors


def test_manifest_tampering_and_missing_metric_are_detected(tmp_path: Path):
    generate(tmp_path)
    acceptance_path = tmp_path / "pilot_acceptance_plan.json"
    acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    acceptance["metrics"] = acceptance["metrics"][1:]
    acceptance_path.write_text(json.dumps(acceptance, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    errors = validate(tmp_path)
    assert "missing acceptance metric: time_to_first_report_minutes" in errors
    assert "package manifest mismatch: pilot_acceptance_plan.json" in errors


def test_generation_is_deterministic():
    assert check_determinism() == []
