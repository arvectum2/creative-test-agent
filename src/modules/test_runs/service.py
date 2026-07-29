import json
from datetime import datetime, timezone

from src.modules.test_runs.models import TestRun
from src.modules.test_runs.pipeline import run_pipeline
from src.modules.test_runs.schemas import (
    AudienceReaction,
    BrandbookCompliance,
    ComplianceViolation,
    CreateTestRunRequest,
    FindingItem,
    RiskEntry,
    ScorecardEntry,
    TestRunResponse,
)
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.llm.factory import get_llm_provider
from src.shared.llm.policy import validate_llm_provider


def _to_response(run: TestRun) -> TestRunResponse:
    findings_data = json_loads(run.structured_findings_json) or {}
    compliance_raw = findings_data.get("brandbook_compliance") or {}
    recommendation_details = findings_data.get("final_recommendation_details") or {}
    return TestRunResponse(
        id=run.id,
        creative_asset_id=run.creative_asset_id,
        brand_profile_id=run.brand_profile_id,
        audience_profile_ids=json_loads(run.audience_profile_ids_json) or [],
        rubric_id=run.rubric_id,
        status=run.status,
        input_context=json_loads(run.input_context_json) or {},
        project_id=run.project_id,
        findings=[FindingItem(**item) if isinstance(item, dict) else item for item in (findings_data.get("findings") or [])],
        summary=run.summary or "",
        overall_score=run.overall_score or 0.0,
        scorecard=[ScorecardEntry(**item) if isinstance(item, dict) else item for item in (findings_data.get("scorecard") or [])],
        risks=[RiskEntry(**item) if isinstance(item, dict) else item for item in (findings_data.get("risks") or [])],
        audience_reactions=[AudienceReaction(**item) if isinstance(item, dict) else item for item in (findings_data.get("audience_reactions") or [])],
        brandbook_compliance=BrandbookCompliance(
            overall_verdict=compliance_raw.get("overall_verdict", "compliant"),
            violations=[ComplianceViolation(**item) if isinstance(item, dict) else item for item in (compliance_raw.get("violations") or [])],
            recommendations=compliance_raw.get("recommendations", []),
            compliance_score=compliance_raw.get("compliance_score", 10.0),
            confidence=compliance_raw.get("confidence", 1.0),
            visual_evidence_fingerprint=compliance_raw.get("visual_evidence_fingerprint", ""),
        ),
        final_recommendation=run.final_recommendation or "",
        final_recommendation_confidence=recommendation_details.get("confidence_score", 1.0),
        final_recommendation_rationale=recommendation_details.get("rationale", ""),
        final_recommendation_actions=recommendation_details.get("top_actions", []),
        visual_context=findings_data.get("visual_context"),
        visual_evidence=findings_data.get("visual_evidence"),
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _value(item, key, default=""):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _findings_to_json(
    findings,
    scorecard,
    risks,
    audience_reactions,
    brandbook_compliance=None,
    visual_context=None,
    visual_evidence=None,
    final_recommendation_details=None,
) -> str:
    data = {
        "findings": [
            {
                "criterion": _value(item, "criterion"),
                "score": _value(item, "score", 0.0),
                "explanation": _value(item, "explanation"),
                "confidence": _value(item, "confidence", 1.0),
                "evidence_notes": _value(item, "evidence_notes", []),
            }
            for item in (findings or [])
        ],
        "scorecard": [
            {
                "criterion": _value(item, "criterion"),
                "score": _value(item, "score", 0.0),
                "rationale": _value(item, "rationale"),
                "recommendation": _value(item, "recommendation"),
                "confidence": _value(item, "confidence", 1.0),
                "evidence_notes": _value(item, "evidence_notes", []),
                "visual_evidence_fingerprint": _value(item, "visual_evidence_fingerprint"),
            }
            for item in (scorecard or [])
        ],
        "risks": [
            {
                "risk_type": _value(item, "risk_type"),
                "level": _value(item, "level"),
                "description": _value(item, "description"),
                "mitigation": _value(item, "mitigation"),
                "confidence": _value(item, "confidence", 1.0),
                "provenance": _value(item, "provenance", []),
                "visual_evidence_fingerprint": _value(item, "visual_evidence_fingerprint"),
            }
            for item in (risks or [])
        ],
        "audience_reactions": [
            {
                "audience_profile_id": _value(item, "audience_profile_id"),
                "segment_name": _value(item, "segment_name"),
                "reaction": _value(item, "reaction"),
                "positive_triggers": _value(item, "positive_triggers", []),
                "objections": _value(item, "objections", []),
                "engagement_probability": _value(item, "engagement_probability", 0.0),
                "confidence": _value(item, "confidence", 1.0),
                "visual_evidence_status": _value(item, "visual_evidence_status", "not_applicable"),
                "visual_evidence_fingerprint": _value(item, "visual_evidence_fingerprint"),
            }
            for item in (audience_reactions or [])
        ],
        "visual_context": visual_context,
        "visual_evidence": visual_evidence,
        "final_recommendation_details": final_recommendation_details or {},
    }
    if brandbook_compliance:
        data["brandbook_compliance"] = brandbook_compliance
    return json.dumps(data, default=str)


def get_test_run_by_asset(asset_id: str) -> TestRun | None:
    with db_session() as db:
        run = (
            db.query(TestRun)
            .filter(TestRun.creative_asset_id == asset_id)
            .order_by(TestRun.created_at.desc())
            .first()
        )
        if run is None:
            return None
        db.expunge(run)
        return run


def create_test_run(req: CreateTestRunRequest) -> TestRunResponse:
    with db_session() as db:
        run = TestRun(
            creative_asset_id=req.creative_asset_id,
            brand_profile_id=req.brand_profile_id,
            audience_profile_ids_json=json_dumps(req.audience_profile_ids),
            rubric_id=req.rubric_id,
            input_context_json=json_dumps(req.input_context),
            project_id=req.project_id,
        )
        db.add(run)
        db.flush()
        db.refresh(run)
        return _to_response(run)


def list_test_runs() -> list[TestRunResponse]:
    with db_session() as db:
        runs = db.query(TestRun).order_by(TestRun.created_at.desc()).all()
        return [_to_response(run) for run in runs]


def get_test_run(run_id: str) -> TestRunResponse | None:
    with db_session() as db:
        run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if run is None:
            return None
        return _to_response(run)


def run_test_run(run_id: str, audit_writer=None) -> TestRunResponse:
    with db_session() as db:
        run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Test run {run_id} not found")

        validate_llm_provider()
        if audit_writer:
            audit_writer("test_run_started", "test_run", run_id, {})

        provider = get_llm_provider()
        run.status = "running"
        db.flush()

        creative_asset_id = run.creative_asset_id
        brand_profile_id = run.brand_profile_id
        audience_profile_ids = json_loads(run.audience_profile_ids_json) or []
        rubric_id = run.rubric_id

    try:
        result = run_pipeline(
            creative_asset_id=creative_asset_id,
            brand_profile_id=brand_profile_id,
            audience_profile_ids=audience_profile_ids,
            rubric_id=rubric_id,
            provider=provider,
        )

        with db_session() as db:
            fresh = db.query(TestRun).filter(TestRun.id == run_id).first()
            fresh.structured_findings_json = _findings_to_json(
                result["findings"],
                result["scorecard"],
                result["risks"],
                result["audience_reactions"],
                brandbook_compliance=result.get("brandbook_compliance"),
                visual_context=result.get("visual_context"),
                visual_evidence=result.get("visual_evidence"),
                final_recommendation_details=result.get("final_recommendation_details"),
            )
            fresh.summary = result["summary"]
            fresh.overall_score = result.get("overall_score", 0.0)
            fresh.final_recommendation = result["final_recommendation"]
            fresh.status = "completed"
            fresh.completed_at = datetime.now(timezone.utc)
            db.flush()
            db.refresh(fresh)

            if audit_writer:
                audit_writer("test_run_completed", "test_run", run_id, {
                    "findings_count": len(result["findings"]),
                    "final_recommendation": result["final_recommendation"],
                    "visual_evidence_confidence": result.get("visual_evidence_confidence"),
                })
            return _to_response(fresh)

    except Exception:
        with db_session() as db:
            failed = db.query(TestRun).filter(TestRun.id == run_id).first()
            failed.status = "failed"
            failed.completed_at = datetime.now(timezone.utc)
            db.flush()
        raise
