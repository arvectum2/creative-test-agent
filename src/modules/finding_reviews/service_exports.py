from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Iterable

from src.modules.finding_reviews.models import FindingAdjudication, FindingReview
from src.modules.finding_reviews.schemas import (
    FindingReviewEvidenceExport,
    FindingReviewResponse,
)
from src.modules.finding_reviews.service_commands import (
    list_project_adjudications,
    list_project_reviews,
)
from src.modules.finding_reviews.service_core import (
    _all_adjudications,
    _all_reviews,
    _latest_review_rows,
    _reviewable_findings,
    _to_response,
    get_finding_disagreement,
    list_project_disagreements,
)
from src.shared.db.repository import json_loads

EVIDENCE_SCHEMA_VERSION = "finding-review-evidence/2.0"
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
ADJUDICATION_HEADERS = [
    "adjudication_id",
    "case_id",
    "finding_id",
    "adjudication_round",
    "policy_id",
    "basis_review_ids",
    "basis_fingerprint_sha256",
    "adjudicator_id",
    "adjudicator_role",
    "decision",
    "correctness",
    "relevance",
    "actionability",
    "traceability",
    "severity_correctness",
    "adjudicator_confidence",
    "adjudicated_at",
    "rationale",
    "notes",
]


def export_review_evidence(project_id: str) -> FindingReviewEvidenceExport:
    reviews = list_project_reviews(project_id)
    adjudications = list_project_adjudications(project_id)
    disagreements = list_project_disagreements(project_id)
    generated_at = max(
        [item.created_at for item in reviews] + [item.created_at for item in adjudications],
        default=datetime(1970, 1, 1, tzinfo=timezone.utc),
    )
    return FindingReviewEvidenceExport(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        generated_at=generated_at,
        project_id=project_id,
        review_count=len(reviews),
        system_review_count=sum(item.source_kind == "system" for item in reviews),
        human_finding_count=sum(item.source_kind == "human" for item in reviews),
        adjudication_count=len(adjudications),
        reviews=reviews,
        adjudications=adjudications,
        disagreements=disagreements,
        claim_boundary={
            "system_findings_mutated": False,
            "independent_reviews_mutated": False,
            "adjudications_mutated": False,
            "human_omissions_fabricated_as_system_findings": False,
            "validated_accuracy_claim_generated": False,
            "automatic_threshold_tuning_performed": False,
        },
    )


def _review_assessment(response: FindingReviewResponse, *, review_status: str) -> dict[str, Any]:
    return {
        "review_id": response.id,
        "finding_id": response.finding_id,
        "decision": response.decision,
        "verdict": response.decision,
        "rationale": response.rationale,
        "comment": response.comment or "",
        "reviewer_id": response.reviewer_subject_id,
        "reviewer_name": response.reviewer_display_name,
        "reviewer_role": response.reviewer_role,
        "confidence": response.reviewer_confidence,
        "correctness": response.correctness,
        "relevance": response.relevance,
        "actionability": response.actionability,
        "traceability": response.traceability,
        "severity_correctness": response.severity_correctness,
        "revision_number": response.revision_number,
        "reviewer_revision_number": response.reviewer_revision_number,
        "reviewed_at": response.created_at.isoformat(),
        "review_status": review_status,
    }


def report_review_payload(project_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    assessments: list[dict[str, Any]] = []
    for finding in _reviewable_findings(project_id):
        finding_id = str(finding.get("finding_id"))
        state = get_finding_disagreement(project_id, finding_id)
        if state.status == "adjudicated" and state.latest_adjudication:
            adj = state.latest_adjudication
            assessments.append(
                {
                    "adjudication_id": adj.id,
                    "finding_id": finding_id,
                    "decision": adj.decision,
                    "verdict": adj.decision,
                    "rationale": adj.rationale,
                    "comment": adj.comment or "",
                    "reviewer_id": adj.adjudicator_subject_id,
                    "reviewer_name": adj.adjudicator_display_name,
                    "reviewer_role": adj.adjudicator_role,
                    "confidence": adj.adjudicator_confidence,
                    "correctness": adj.correctness,
                    "relevance": adj.relevance,
                    "actionability": adj.actionability,
                    "traceability": adj.traceability,
                    "severity_correctness": adj.severity_correctness,
                    "adjudication_round": adj.adjudication_round,
                    "basis_review_ids": adj.basis_review_ids,
                    "basis_fingerprint_sha256": adj.basis_fingerprint_sha256,
                    "reviewed_at": adj.created_at.isoformat(),
                    "review_status": "adjudicated",
                }
            )
        elif state.status == "agreement" and state.latest_reviews:
            first = state.latest_reviews[0]
            assessments.append(
                {
                    **_review_assessment(first, review_status="independent_agreement"),
                    "review_id": None,
                    "reviewer_id": None,
                    "reviewer_name": "Independent reviewer consensus",
                    "reviewer_role": "independent reviewer consensus",
                    "confidence": min(item.reviewer_confidence for item in state.latest_reviews),
                    "rationale": (
                        f"{len(state.latest_reviews)} independent reviewers agreed on "
                        f"'{first.decision}'. See finding-review evidence for immutable rationales."
                    ),
                    "basis_review_ids": state.basis_review_ids,
                    "basis_fingerprint_sha256": state.basis_fingerprint_sha256,
                }
            )
        elif state.status == "insufficient_reviews" and len(state.latest_reviews) == 1:
            item = _review_assessment(state.latest_reviews[0], review_status="single_review")
            item["system_finding_snapshot_sha256"] = state.latest_reviews[0].system_finding_snapshot_sha256
            assessments.append(item)
        elif state.status in {"disagreement", "stale_adjudication"}:
            assessments.append(
                {
                    "finding_id": finding_id,
                    "decision": "not_reviewed",
                    "verdict": "not_reviewed",
                    "rationale": "Independent reviews disagree; current adjudication is required.",
                    "reviewer_role": "",
                    "confidence": None,
                    "review_status": "pending_adjudication",
                    "basis_review_ids": state.basis_review_ids,
                    "basis_fingerprint_sha256": state.basis_fingerprint_sha256,
                    "disagreement_reasons": state.disagreement_reasons,
                }
            )

    human_findings: list[dict[str, Any]] = []
    human_latest: dict[str, FindingReview] = {}
    for row in _latest_review_rows(project_id).values():
        if row.source_kind != "human":
            continue
        current = human_latest.get(row.finding_id)
        if current is None or row.revision_number > current.revision_number:
            human_latest[row.finding_id] = row
    for row in human_latest.values():
        response = _to_response(row)
        common = _review_assessment(response, review_status="human_added")
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
        notes.append(f"global_revision={row.revision_number}")
        writer.writerow(
            {
                "review_id": row.id,
                "case_id": row.case_id or row.creative_record_id or row.campaign_id or "unscoped",
                "reviewer_id": row.reviewer_subject_id,
                "review_round": row.reviewer_revision_number,
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


def _adjudication_csv_bytes(rows: Iterable[FindingAdjudication]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=ADJUDICATION_HEADERS, extrasaction="raise")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "adjudication_id": row.id,
                "case_id": row.case_id or row.creative_record_id or row.campaign_id or "unscoped",
                "finding_id": row.finding_id,
                "adjudication_round": row.adjudication_round,
                "policy_id": row.policy_id,
                "basis_review_ids": "|".join(json_loads(row.basis_review_ids_json) or []),
                "basis_fingerprint_sha256": row.basis_fingerprint_sha256,
                "adjudicator_id": row.adjudicator_subject_id,
                "adjudicator_role": row.adjudicator_role,
                "decision": row.decision,
                "correctness": row.correctness,
                "relevance": row.relevance,
                "actionability": row.actionability,
                "traceability": row.traceability,
                "severity_correctness": row.severity_correctness,
                "adjudicator_confidence": f"{row.adjudicator_confidence:.4f}",
                "adjudicated_at": row.created_at.isoformat(),
                "rationale": row.rationale,
                "notes": row.comment or "",
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
    adjudications = _all_adjudications(project_id)
    evidence = export_review_evidence(project_id).model_dump(mode="json")
    evidence_bytes = (
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    artifacts = {
        "finding_reviews_evidence.json": evidence_bytes,
        "expert_review.csv": _csv_bytes(rows),
        "adjudications.csv": _adjudication_csv_bytes(adjudications),
    }
    manifest = {
        "package_id": "creative-test-agent-finding-review-calibration",
        "package_version": "2.0.0",
        "project_id": project_id,
        "generated_at": evidence["generated_at"],
        "review_count": len(rows),
        "adjudication_count": len(adjudications),
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
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in sorted(artifacts.items()):
            _zip_write(archive, name, data)
        _zip_write(archive, "package_manifest.json", manifest_bytes)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", project_id).strip("-")[:80] or "project"
    return buffer.getvalue(), f"finding-review-calibration-{slug}.zip"
