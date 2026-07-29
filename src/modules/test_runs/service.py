import json
from datetime import datetime, timezone

from src.modules.test_runs.confidence_policy import run_confidence_aware_pipeline
from src.modules.test_runs.models import TestRun
from src.modules.test_runs.schemas import (
    AudienceReaction,
    BrandbookCompliance,
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
        summary_details=findings_data.get("summary_details") or {},
        overall_score=run.overall_score or 0.0,
        scorecard=[ScorecardEntry(**item) if isinstance(item, dict) else item for item in (findings_data.get("scorecard") or [])],
        risks=[RiskEntry(**item) if isinstance(item, dict) else item for item in (findings_data.get("risks") or [])],
        audience_reactions=[AudienceReaction(**item) if isinstance(item, dict) else item for item in (findings_data.get("audience_reactions") or [])],
        brandbook_compliance=BrandbookCompliance.model_validate(compliance_raw),
        final_recommendation=run.final_recommendation or "",
        effective_recommendation=findings_data.get("effective_recommendation", run.final_recommendation or ""),
        final_recommendation_confidence=recommendation_details.get("confidence_score", 1.0),
        final_recommendation_rationale=recommendation_details.get("rationale", ""),
        final_recommendation_actions=recommendation_details.get("top_actions", []),
        final_recommendation_visual_evidence_refs=recommendation_details.get("visual_evidence_refs", []),
        final_recommendation_visual_traceability_status=recommendation_details.get(
            "visual_traceability_status", "not_used"
        ),
        visual_context=findings_data.get("visual_context"),
        visual_evidence=findings_data.get("visual_evidence"),
        visual_evidence_trace=findings_data.get("visual_evidence_trace"),
        visual_traceability_status=findings_data.get("visual_traceability_status", "not_applicable"),
        unresolved_visual_finding_count=findings_data.get("unresolved_visual_finding_count", 0),
        visual_confidence_policy=findings_data.get("visual_confidence_policy"),
        visual_decision_status=findings_data.get("visual_decision_status", "not_applicable"),
        visual_abstention_count=findings_data.get("visual_abstention_count", 0),
        visual_review_required_count=findings_data.get("visual_review_required_count", 0),
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _item_dict(item) -> dict:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if hasattr(item, "__dict__"):
        return dict(item.__dict__)
    raise TypeError(f"Unsupported finding payload type: {type(item)!r}")


def _findings_to_json(
    findings,
    scorecard,
    risks,
    audience_reactions,
    brandbook_compliance=None,
    visual_context=None,
    visual_evidence=None,
    visual_evidence_trace=None,
    visual_traceability_status="not_applicable",
    unresolved_visual_finding_count=0,
    summary_details=None,
    final_recommendation_details=None,
    visual_confidence_policy=None,
    visual_decision_status="not_applicable",
    visual_abstention_count=0,
    visual_review_required_count=0,
    effective_recommendation="",
) -> str:
    data = {
        "findings": [_item_dict(item) for item in (findings or [])],
        "scorecard": [_item_dict(item) for item in (scorecard or [])],
        "risks": [_item_dict(item) for item in (risks or [])],
        "audience_reactions": [_item_dict(item) for item in (audience_reactions or [])],
        "summary_details": summary_details or {},
        "visual_context": visual_context,
        "visual_evidence": visual_evidence,
        "visual_evidence_trace": visual_evidence_trace,
        "visual_traceability_status": visual_traceability_status,
        "unresolved_visual_finding_count": unresolved_visual_finding_count,
        "final_recommendation_details": final_recommendation_details or {},
        "visual_confidence_policy": visual_confidence_policy,
        "visual_decision_status": visual_decision_status,
        "visual_abstention_count": visual_abstention_count,
        "visual_review_required_count": visual_review_required_count,
        "effective_recommendation": effective_recommendation,
    }
    if brandbook_compliance:
        data["brandbook_compliance"] = _item_dict(brandbook_compliance)
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
        result = run_confidence_aware_pipeline(
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
                visual_evidence_trace=result.get("visual_evidence_trace"),
                visual_traceability_status=result.get("visual_traceability_status", "not_applicable"),
                unresolved_visual_finding_count=result.get("unresolved_visual_finding_count", 0),
                summary_details=result.get("summary_details"),
                final_recommendation_details=result.get("final_recommendation_details"),
                visual_confidence_policy=result.get("visual_confidence_policy"),
                visual_decision_status=result.get("visual_decision_status", "not_applicable"),
                visual_abstention_count=result.get("visual_abstention_count", 0),
                visual_review_required_count=result.get("visual_review_required_count", 0),
                effective_recommendation=result.get("effective_recommendation", ""),
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
                    "effective_recommendation": result.get("effective_recommendation"),
                    "visual_evidence_confidence": result.get("visual_evidence_confidence"),
                    "visual_traceability_status": result.get("visual_traceability_status"),
                    "unresolved_visual_finding_count": result.get("unresolved_visual_finding_count", 0),
                    "visual_decision_status": result.get("visual_decision_status"),
                    "visual_abstention_count": result.get("visual_abstention_count", 0),
                    "visual_review_required_count": result.get("visual_review_required_count", 0),
                    "visual_confidence_policy_fingerprint": (
                        result.get("visual_confidence_policy") or {}
                    ).get("fingerprint"),
                })
            return _to_response(fresh)

    except Exception:
        with db_session() as db:
            failed = db.query(TestRun).filter(TestRun.id == run_id).first()
            failed.status = "failed"
            failed.completed_at = datetime.now(timezone.utc)
            db.flush()
        raise
