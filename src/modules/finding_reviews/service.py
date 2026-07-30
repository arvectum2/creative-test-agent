from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from src.modules.audit_log.service import write_audit_event
from src.modules.campaign_evidence.service import get_campaign_evidence_workspace
from src.modules.client_report_v2.evidence import compose_report_evidence
from src.modules.finding_reviews.models import FindingReview
from src.modules.finding_reviews.schemas import (
    CreateFindingReviewRequest,
    CreateHumanFindingRequest,
    FindingReviewEvidenceExport,
    FindingReviewResponse,
    ReviewableFindingDetailResponse,
    ReviewableFindingResponse,
)
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError

EVIDENCE_SCHEMA_VERSION = "finding-review-evidence/1.0"
CALIBRATION_HEADERS = [
    "review_id",
    "case_id",
    "reviewer_id",
    "review_round",
    "finding_id",
    "finding_origin",
    "finding_category",
    "finding_text",
    "severity",
    "correctness",
    "relevance",
    "actionability",
    "evidence_traceability",
    "recommended_action",
    "reviewer_confidence",
    "blind_to_outcomes",
    "reviewed_at",
    "notes",
]


def _workspace_dict(project_id: str) -> dict[str, Any]:
    workspace = get_campaign_evidence_workspace(project_id)
    if hasattr(workspace, "model_dump"):
        return workspace.model_dump(mode="json")
    if isinstance(workspace, dict):
        return dict(workspace)
    raise AppError("campaign_evidence_invalid", "Campaign evidence workspace is invalid", 409)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reviewable_findings(project_id: str) -> list[dict[str, Any]]:
    workspace = _workspace_dict(project_id)
    evidence = compose_report_evidence(
        workspace,
        locale="ru",
        generated_at="1970-01-01T00:00:00+00:00",
    )
    case_by_campaign = {
        str(item.get("campaign_id")): str(item.get("case_id") or item.get("campaign_id"))
        for item in workspace.get("campaigns") or []
    }
    findings: list[dict[str, Any]] = []
    for item in (evidence.get("agent_diagnostics") or {}).get("findings") or []:
        snapshot = dict(item)
        snapshot["project_id"] = project_id
        snapshot["case_id"] = case_by_campaign.get(str(item.get("campaign_id")), str(item.get("campaign_id") or ""))
        findings.append(snapshot)
    return findings


def _find_system_finding(project_id: str, finding_id: str) -> dict[str, Any]:
    for item in _reviewable_findings(project_id):
        if item.get("finding_id") == finding_id:
            return item
    raise AppError("finding_not_found", "Finding not found in this project", 404)


def _all_reviews(project_id: str, finding_id: str | None = None) -> list[FindingReview]:
    with db_session() as db:
        query = db.query(FindingReview).filter(FindingReview.project_id == project_id)
        if finding_id:
            query = query.filter(FindingReview.finding_id == finding_id)
        rows = query.order_by(
            FindingReview.finding_id.asc(),
            FindingReview.revision_number.asc(),
            FindingReview.created_at.asc(),
        ).all()
        for row in rows:
            db.expunge(row)
        return rows


def _latest_rows(project_id: str) -> tuple[dict[str, FindingReview], dict[str, int]]:
    rows = _all_reviews(project_id)
    latest: dict[str, FindingReview] = {}
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.finding_id] = counts.get(row.finding_id, 0) + 1
        current = latest.get(row.finding_id)
        if current is None or row.revision_number >= current.revision_number:
            latest[row.finding_id] = row
    return latest, counts


def _to_response(row: FindingReview) -> FindingReviewResponse:
    return FindingReviewResponse(
        id=row.id,
        project_id=row.project_id,
        campaign_id=row.campaign_id,
        case_id=row.case_id,
        creative_record_id=row.creative_record_id,
        creative_asset_id=row.creative_asset_id,
        test_run_id=row.test_run_id,
        finding_id=row.finding_id,
        source_kind=row.source_kind,
        system_finding_snapshot=json_loads(row.system_finding_snapshot_json) if row.system_finding_snapshot_json else None,
        system_finding_snapshot_sha256=row.system_finding_snapshot_sha256,
        human_finding_snapshot=json_loads(row.human_finding_snapshot_json) if row.human_finding_snapshot_json else None,
        human_finding_snapshot_sha256=row.human_finding_snapshot_sha256,
        reviewer_user_id=row.reviewer_user_id,
        reviewer_display_name=row.reviewer_display_name,
        reviewer_role=row.reviewer_role,
        decision=row.decision,
        correctness=row.correctness,
        relevance=row.relevance,
        actionability=row.actionability,
        traceability=row.traceability,
        severity_correctness=row.severity_correctness,
        reviewer_confidence=row.reviewer_confidence,
        rationale=row.rationale,
        comment=row.comment,
        revision_number=row.revision_number,
        supersedes_review_id=row.supersedes_review_id,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_reviewable_findings(
    project_id: str,
    *,
    campaign_id: str | None = None,
) -> list[ReviewableFindingResponse]:
    latest, counts = _latest_rows(project_id)
    result: list[ReviewableFindingResponse] = []
    for snapshot in _reviewable_findings(project_id):
        if campaign_id and snapshot.get("campaign_id") != campaign_id and snapshot.get("case_id") != campaign_id:
            continue
        digest = _sha256_json(snapshot)
        latest_row = latest.get(str(snapshot.get("finding_id")))
        latest_response = _to_response(latest_row) if latest_row else None
        result.append(
            ReviewableFindingResponse(
                finding_id=str(snapshot.get("finding_id")),
                project_id=project_id,
                campaign_id=str(snapshot.get("campaign_id")),
                case_id=str(snapshot.get("case_id")),
                creative_record_id=str(snapshot.get("creative_record_id")),
                creative_asset_id=snapshot.get("creative_asset_id"),
                test_run_id=snapshot.get("test_run_id"),
                criterion=str(snapshot.get("criterion") or "finding"),
                text=str(snapshot.get("text") or ""),
                score=snapshot.get("score"),
                confidence=snapshot.get("confidence"),
                snapshot_sha256=digest,
                system_finding_snapshot=snapshot,
                latest_review=latest_response,
                review_count=counts.get(str(snapshot.get("finding_id")), 0),
                current_snapshot_matches_latest_review=(
                    latest_row is None or latest_row.system_finding_snapshot_sha256 == digest
                ),
            )
        )
    return result


def get_reviewable_finding(
    project_id: str,
    finding_id: str,
) -> ReviewableFindingDetailResponse:
    finding = _find_system_finding(project_id, finding_id)
    digest = _sha256_json(finding)
    history = [_to_response(item) for item in _all_reviews(project_id, finding_id)]
    latest = history[-1] if history else None
    return ReviewableFindingDetailResponse(
        finding_id=finding_id,
        project_id=project_id,
        campaign_id=str(finding.get("campaign_id")),
        case_id=str(finding.get("case_id")),
        creative_record_id=str(finding.get("creative_record_id")),
        creative_asset_id=finding.get("creative_asset_id"),
        test_run_id=finding.get("test_run_id"),
        criterion=str(finding.get("criterion") or "finding"),
        text=str(finding.get("text") or ""),
        score=finding.get("score"),
        confidence=finding.get("confidence"),
        snapshot_sha256=digest,
        system_finding_snapshot=finding,
        latest_review=latest,
        review_count=len(history),
        current_snapshot_matches_latest_review=(
            latest is None or latest.system_finding_snapshot_sha256 == digest
        ),
        review_history=history,
    )


def create_system_review(
    project_id: str,
    finding_id: str,
    body: CreateFindingReviewRequest,
    *,
    user: dict[str, Any],
) -> FindingReviewResponse:
    snapshot = _find_system_finding(project_id, finding_id)
    digest = _sha256_json(snapshot)
    if body.expected_system_finding_sha256 != digest:
        raise AppError(
            "finding_snapshot_changed",
            "The system finding changed after the review page was opened; reload before saving",
            409,
        )

    now = datetime.now(timezone.utc)
    with db_session() as db:
        latest = (
            db.query(FindingReview)
            .filter(
                FindingReview.project_id == project_id,
                FindingReview.finding_id == finding_id,
            )
            .order_by(FindingReview.revision_number.desc(), FindingReview.created_at.desc())
            .first()
        )
        revision_number = (latest.revision_number + 1) if latest else 1
        row = FindingReview(
            project_id=project_id,
            campaign_id=snapshot.get("campaign_id"),
            case_id=snapshot.get("case_id"),
            creative_record_id=snapshot.get("creative_record_id"),
            creative_asset_id=snapshot.get("creative_asset_id"),
            test_run_id=snapshot.get("test_run_id"),
            finding_id=finding_id,
            source_kind="system",
            system_finding_snapshot_json=json_dumps(snapshot),
            system_finding_snapshot_sha256=digest,
            human_finding_snapshot_json=None,
            human_finding_snapshot_sha256=None,
            reviewer_user_id=user.get("user_id"),
            reviewer_display_name=str(user.get("display_name") or "Local reviewer"),
            reviewer_role=body.reviewer_role,
            decision=body.decision,
            correctness=body.correctness,
            relevance=body.relevance,
            actionability=body.actionability,
            traceability=body.traceability,
            severity_correctness=body.severity_correctness,
            reviewer_confidence=body.reviewer_confidence,
            rationale=body.rationale,
            comment=body.comment,
            revision_number=revision_number,
            supersedes_review_id=latest.id if latest else None,
            created_by_user_id=user.get("user_id"),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        response = _to_response(row)

    write_audit_event(
        "finding_review_created",
        "finding_review",
        response.id,
        {
            "project_id": project_id,
            "finding_id": finding_id,
            "decision": response.decision,
            "revision_number": response.revision_number,
            "system_finding_snapshot_sha256": digest,
            "supersedes_review_id": response.supersedes_review_id,
        },
    )
    return response


def create_human_finding(
    project_id: str,
    body: CreateHumanFindingRequest,
    *,
    user: dict[str, Any],
) -> FindingReviewResponse:
    workspace = _workspace_dict(project_id)
    campaign = next(
        (
            item
            for item in workspace.get("campaigns") or []
            if item.get("campaign_id") == body.campaign_id or item.get("case_id") == body.campaign_id
        ),
        None,
    )
    if campaign is None:
        raise AppError("campaign_not_found", "Campaign not found in this project", 404)
    assets = campaign.get("assets") or []
    if body.creative_record_id and not any(
        item.get("creative_record_id") == body.creative_record_id for item in assets
    ):
        raise AppError("creative_record_not_found", "Creative record does not belong to this campaign", 404)
    if body.creative_asset_id and not any(
        item.get("creative_asset_id") == body.creative_asset_id for item in assets
    ):
        raise AppError("creative_asset_not_found", "Creative asset does not belong to this campaign", 404)

    finding_id = f"human-finding:{uuid4()}"
    snapshot = {
        "finding_id": finding_id,
        "project_id": project_id,
        "campaign_id": campaign.get("campaign_id"),
        "case_id": campaign.get("case_id") or campaign.get("campaign_id"),
        "creative_record_id": body.creative_record_id,
        "creative_asset_id": body.creative_asset_id,
        "criterion": body.criterion,
        "title": body.title,
        "text": body.text,
        "proposed_severity": body.proposed_severity,
        "source_kind": "human",
        "system_finding_fabricated": False,
    }
    digest = _sha256_json(snapshot)
    now = datetime.now(timezone.utc)
    with db_session() as db:
        row = FindingReview(
            project_id=project_id,
            campaign_id=campaign.get("campaign_id"),
            case_id=campaign.get("case_id") or campaign.get("campaign_id"),
            creative_record_id=body.creative_record_id,
            creative_asset_id=body.creative_asset_id,
            test_run_id=None,
            finding_id=finding_id,
            source_kind="human",
            system_finding_snapshot_json=None,
            system_finding_snapshot_sha256=None,
            human_finding_snapshot_json=json_dumps(snapshot),
            human_finding_snapshot_sha256=digest,
            reviewer_user_id=user.get("user_id"),
            reviewer_display_name=str(user.get("display_name") or "Local reviewer"),
            reviewer_role=body.reviewer_role,
            decision="missed_by_system",
            correctness=5,
            relevance=body.relevance,
            actionability=body.actionability,
            traceability=body.traceability,
            severity_correctness="not_applicable",
            reviewer_confidence=body.reviewer_confidence,
            rationale=body.rationale,
            comment=body.comment,
            revision_number=1,
            supersedes_review_id=None,
            created_by_user_id=user.get("user_id"),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        response = _to_response(row)

    write_audit_event(
        "human_finding_created",
        "finding_review",
        response.id,
        {
            "project_id": project_id,
            "finding_id": finding_id,
            "decision": "missed_by_system",
            "human_finding_snapshot_sha256": digest,
            "system_finding_fabricated": False,
        },
    )
    return response


def list_project_reviews(
    project_id: str,
    *,
    finding_id: str | None = None,
) -> list[FindingReviewResponse]:
    _workspace_dict(project_id)
    return [_to_response(item) for item in _all_reviews(project_id, finding_id)]


def latest_review_index(project_id: str) -> dict[str, FindingReviewResponse]:
    latest, _ = _latest_rows(project_id)
    return {key: _to_response(value) for key, value in latest.items()}


def export_review_evidence(project_id: str) -> FindingReviewEvidenceExport:
    reviews = list_project_reviews(project_id)
    generated_at = max(
        (item.created_at for item in reviews),
        default=datetime(1970, 1, 1, tzinfo=timezone.utc),
    )
    return FindingReviewEvidenceExport(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        generated_at=generated_at,
        project_id=project_id,
        review_count=len(reviews),
        system_review_count=sum(item.source_kind == "system" for item in reviews),
        human_finding_count=sum(item.source_kind == "human" for item in reviews),
        reviews=reviews,
        claim_boundary={
            "system_findings_mutated": False,
            "human_omissions_fabricated_as_system_findings": False,
            "multi_reviewer_adjudication_performed": False,
            "validated_accuracy_claim_generated": False,
            "automatic_threshold_tuning_performed": False,
        },
    )


def report_review_payload(project_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    latest, _ = _latest_rows(project_id)
    assessments: list[dict[str, Any]] = []
    human_findings: list[dict[str, Any]] = []
    for row in latest.values():
        response = _to_response(row)
        common = {
            "review_id": response.id,
            "finding_id": response.finding_id,
            "decision": response.decision,
            "verdict": response.decision,
            "rationale": response.rationale,
            "comment": response.comment or "",
            "reviewer_id": response.reviewer_user_id,
            "reviewer_name": response.reviewer_display_name,
            "reviewer_role": response.reviewer_role,
            "confidence": response.reviewer_confidence,
            "correctness": response.correctness,
            "relevance": response.relevance,
            "actionability": response.actionability,
            "traceability": response.traceability,
            "severity_correctness": response.severity_correctness,
            "revision_number": response.revision_number,
            "reviewed_at": response.created_at.isoformat(),
        }
        if response.source_kind == "system":
            common["system_finding_snapshot_sha256"] = response.system_finding_snapshot_sha256
            assessments.append(common)
        else:
            common["human_finding_snapshot"] = response.human_finding_snapshot
            common["human_finding_snapshot_sha256"] = response.human_finding_snapshot_sha256
            common["system_finding_fabricated"] = False
            human_findings.append(common)
    assessments.sort(key=lambda item: item["finding_id"])
    human_findings.sort(key=lambda item: item["finding_id"])
    return assessments, human_findings


def _ternary(rating: int) -> str:
    if rating >= 4:
        return "yes"
    if rating == 3:
        return "uncertain"
    return "no"


def _review_snapshot(row: FindingReview) -> dict[str, Any]:
    if row.source_kind == "system":
        return json_loads(row.system_finding_snapshot_json)
    return json_loads(row.human_finding_snapshot_json)


def _csv_bytes(rows: Iterable[FindingReview]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CALIBRATION_HEADERS, extrasaction="raise")
    writer.writeheader()
    for row in rows:
        snapshot = _review_snapshot(row)
        notes = [row.rationale]
        if row.comment:
            notes.append(row.comment)
        snapshot_hash = row.system_finding_snapshot_sha256 or row.human_finding_snapshot_sha256
        if snapshot_hash:
            notes.append(f"snapshot_sha256={snapshot_hash}")
        writer.writerow(
            {
                "review_id": row.id,
                "case_id": row.case_id or row.creative_record_id or row.campaign_id or "unscoped",
                "reviewer_id": row.reviewer_user_id or row.reviewer_display_name,
                "review_round": row.revision_number,
                "finding_id": row.finding_id,
                "finding_origin": "system" if row.source_kind == "system" else "human_added",
                "finding_category": snapshot.get("criterion") or "finding",
                "finding_text": snapshot.get("text") or snapshot.get("title") or "",
                "severity": snapshot.get("proposed_severity") or snapshot.get("severity") or "not_applicable",
                "correctness": _ternary(row.correctness),
                "relevance": _ternary(row.relevance),
                "actionability": _ternary(row.actionability),
                "evidence_traceability": _ternary(row.traceability),
                "recommended_action": row.decision,
                "reviewer_confidence": f"{row.reviewer_confidence:.4f}",
                "blind_to_outcomes": "not_assessed",
                "reviewed_at": row.created_at.isoformat(),
                "notes": " | ".join(notes),
            }
        )
    return output.getvalue().encode("utf-8")


def _zip_write(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data)


def build_calibration_package(project_id: str) -> tuple[bytes, str]:
    rows = _all_reviews(project_id)
    evidence = export_review_evidence(project_id).model_dump(mode="json")
    evidence_bytes = (json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    review_csv = _csv_bytes(rows)
    artifacts = {
        "finding_reviews_evidence.json": evidence_bytes,
        "expert_review.csv": review_csv,
    }
    manifest = {
        "package_id": "creative-test-agent-finding-review-calibration",
        "package_version": "1.0.0",
        "project_id": project_id,
        "generated_at": evidence["generated_at"],
        "review_count": len(rows),
        "artifacts": [
            {
                "filename": name,
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for name, data in sorted(artifacts.items())
        ],
        "claim_boundary": evidence["claim_boundary"],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in sorted(artifacts.items()):
            _zip_write(archive, name, data)
        _zip_write(archive, "package_manifest.json", manifest_bytes)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", project_id).strip("-")[:80] or "project"
    return buffer.getvalue(), f"finding-review-calibration-{slug}.zip"
