from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.modules.campaign_evidence.service import get_campaign_evidence_workspace
from src.modules.client_report_v2.rendering import (
    REPORT_VERSION,
    build_report_bundle,
    compose_report_evidence,
    validate_report_bundle,
)
from src.modules.client_report_v2.schemas import (
    ClientReportV2Artifact,
    ClientReportV2Response,
    ExpertAssessmentInput,
)
from src.modules.finding_reviews.service import report_review_payload
from src.shared.config.settings import get_settings
from src.shared.errors import AppError
from src.shared.security.hardening import ensure_within_root

_REPORT_ID = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


def generate_client_report_v2(
    project_id: str,
    *,
    locale: str = "ru",
    expert_assessments: list[ExpertAssessmentInput] | None = None,
    force: bool = False,
) -> ClientReportV2Response:
    workspace = get_campaign_evidence_workspace(project_id)
    workspace_dict = workspace.model_dump(mode="json")
    requested = [item.model_dump(mode="json") for item in (expert_assessments or [])]
    persisted, human_findings = report_review_payload(project_id)
    merged = {item["finding_id"]: item for item in requested}
    for item in persisted:
        merged[item["finding_id"]] = item
    assessment_dicts = [merged[key] for key in sorted(merged)]
    fingerprint = _fingerprint(workspace_dict, assessment_dicts, human_findings, locale)
    report_id = f"rpt2-{fingerprint[:24]}"
    if force:
        report_id = f"rpt2-{fingerprint[:16]}-{uuid4().hex[:8]}"
    directory = _report_directory(project_id, report_id)
    if not force and directory.is_dir() and not validate_report_bundle(directory):
        return _response_from_bundle(directory)

    evidence = compose_report_evidence(
        workspace_dict,
        expert_assessments=assessment_dicts,
        locale=locale,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    _attach_finding_reviews(evidence, persisted, human_findings)
    evidence["input_fingerprint"] = fingerprint
    evidence["report_run_id"] = report_id
    build_report_bundle(evidence, directory)
    errors = validate_report_bundle(directory)
    if errors:
        raise AppError(
            "client_report_v2_invalid",
            "Generated client report v2 failed validation: " + "; ".join(errors),
            500,
        )
    return _response_from_bundle(directory)


def _attach_finding_reviews(
    evidence: dict,
    persisted_assessments: list[dict],
    human_findings: list[dict],
) -> None:
    by_id = {item["finding_id"]: item for item in persisted_assessments}
    assessment_block = evidence.setdefault("expert_assessment", {})
    for row in assessment_block.get("assessments") or []:
        persisted = by_id.get(row.get("finding_id"))
        if persisted:
            row.update(persisted)
            row["status"] = "reviewed"
    assessment_block["human_findings"] = human_findings
    summary = evidence.setdefault("summary", {})
    summary["human_finding_count"] = len(human_findings)
    if human_findings:
        summary["release_status"] = "manual_review_required"
        limitations = evidence.setdefault("limitations_and_confidence", {}).setdefault("limitations", [])
        limitations.append(
            {
                "limitation_id": "boundary:human-added-findings",
                "campaign_id": None,
                "code": "human_findings_require_methodology_review",
                "severity": "warning",
                "message": f"{len(human_findings)} human-added finding(s) were recorded as missed_by_system.",
                "context": {"human_finding_count": len(human_findings)},
                "evidence_references": [],
            }
        )
    evidence.setdefault("claim_boundary", {}).update(
        {
            "system_findings_mutated_by_expert_review": False,
            "human_omissions_fabricated_as_system_findings": False,
            "finding_reviews_are_append_only": True,
        }
    )


def get_client_report_v2(project_id: str, report_id: str) -> ClientReportV2Response:
    directory = _report_directory(project_id, report_id)
    if not directory.is_dir():
        raise AppError("client_report_v2_not_found", "Client report v2 not found", 404)
    errors = validate_report_bundle(directory)
    if errors:
        raise AppError(
            "client_report_v2_corrupted",
            "Stored client report v2 failed validation: " + "; ".join(errors),
            409,
        )
    return _response_from_bundle(directory)


def secure_client_report_v2_artifact_path(
    project_id: str,
    report_id: str,
    artifact_type: str,
) -> tuple[Path, str, str]:
    directory = _report_directory(project_id, report_id)
    manifest_path = directory / "report_manifest.json"
    if not manifest_path.is_file():
        raise AppError("client_report_v2_not_found", "Client report v2 not found", 404)
    manifest = _read_json(manifest_path)
    if artifact_type == "manifest":
        return manifest_path, manifest_path.name, "application/json"
    artifact = next(
        (item for item in manifest.get("artifacts") or [] if item.get("artifact_type") == artifact_type),
        None,
    )
    if artifact is None:
        raise AppError("client_report_v2_artifact_not_found", "Requested artifact is unavailable", 404)
    try:
        path = ensure_within_root(directory / artifact["filename"], get_settings().storage_root)
    except ValueError as exc:
        raise AppError("client_report_v2_path_escape", "Report artifact is outside storage root", 409) from exc
    if not path.is_file() or _sha256_file(path) != artifact.get("sha256"):
        raise AppError("client_report_v2_artifact_corrupted", "Report artifact failed integrity check", 409)
    return path, artifact["filename"], artifact.get("media_type") or "application/octet-stream"


def _report_directory(project_id: str, report_id: str) -> Path:
    if not _REPORT_ID.fullmatch(report_id):
        raise AppError("invalid_client_report_v2_id", "Invalid client report v2 identifier", 400)
    project_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", project_id).strip("-")[:80]
    if not project_slug:
        raise AppError("invalid_project_id", "Invalid project identifier", 400)
    raw = Path(get_settings().storage_root) / "client_report_v2" / project_slug / report_id
    try:
        return ensure_within_root(raw, get_settings().storage_root)
    except ValueError as exc:
        raise AppError("client_report_v2_path_escape", "Report path is outside storage root", 409) from exc


def _fingerprint(
    workspace: dict,
    expert_assessments: list[dict],
    human_findings: list[dict],
    locale: str,
) -> str:
    payload = {
        "report_version": REPORT_VERSION,
        "locale": locale,
        "workspace": workspace,
        "expert_assessments": sorted(expert_assessments, key=lambda item: item.get("finding_id", "")),
        "human_findings": sorted(human_findings, key=lambda item: item.get("finding_id", "")),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _response_from_bundle(directory: Path) -> ClientReportV2Response:
    manifest_path = directory / "report_manifest.json"
    manifest = _read_json(manifest_path)
    summary = manifest.get("summary") or {}
    artifacts = [ClientReportV2Artifact(**item) for item in manifest.get("artifacts") or []]
    return ClientReportV2Response(
        report_id=manifest["report_id"],
        report_version=manifest["report_version"],
        project_id=manifest["project_id"],
        project_name=manifest.get("project_name") or "Project",
        locale=manifest["locale"],
        input_fingerprint=manifest.get("input_fingerprint") or "",
        generated_at=manifest["generated_at"],
        campaign_count=int(summary.get("campaign_count", 0)),
        finding_count=int(summary.get("finding_count", 0)),
        reviewed_finding_count=int(summary.get("reviewed_finding_count", 0)),
        release_status=str(summary.get("release_status") or "evidence_limited"),
        artifacts=artifacts,
        manifest_filename=manifest_path.name,
        manifest_sha256=_sha256_file(manifest_path),
    )


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AppError("client_report_v2_manifest_unreadable", "Report manifest is unreadable", 409) from exc
    if not isinstance(value, dict):
        raise AppError("client_report_v2_manifest_invalid", "Report manifest must be an object", 409)
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
