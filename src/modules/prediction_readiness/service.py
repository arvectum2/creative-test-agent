from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func

from src.modules.clarifications.models import (
    ClarificationAudience,
    ClarificationQuestion,
    ClarificationQuestionStatus,
    ClarificationRun,
)
from src.modules.data_quality.models import DataQualityIssue, DataQualityRun, DataQualityRunStatus
from src.modules.prediction_readiness.models import (
    CapabilityStatus,
    EvidenceStrength,
    PredictionCapabilityReadiness,
    PredictionReadinessOverallStatus,
    PredictionReadinessRun,
    PredictionReadinessRunStatus,
)
from src.modules.prediction_readiness.schemas import (
    PredictionCapabilityResponse,
    PredictionReadinessResultResponse,
    PredictionReadinessRunResponse,
)
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError

EVALUATOR_NAME = "deterministic-prediction-readiness-evaluator"
EVALUATOR_VERSION = "1.0.0"


@dataclass
class _Decision:
    key: str
    title: str
    status: str
    mode: str
    evidence_strength: str
    user_message: str
    internal_message: str
    required_inputs: list[str]
    missing_inputs: list[str]
    degraded_inputs: list[str]
    allowed_operations: list[str]
    prohibited_operations: list[str]
    reasons: list[dict[str, Any]]
    evidence: dict[str, Any]


def evaluate_prediction_readiness(
    data_quality_run_id: str,
    *,
    force: bool = False,
    created_by_user_id: str | None = None,
) -> PredictionReadinessResultResponse:
    with db_session() as db:
        quality_run = db.query(DataQualityRun).filter(DataQualityRun.id == data_quality_run_id).first()
        if quality_run is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        if quality_run.status != DataQualityRunStatus.completed:
            raise AppError(
                "data_quality_run_not_completed",
                "Prediction readiness requires a completed data-quality run",
                409,
            )

        issues = (
            db.query(DataQualityIssue)
            .filter(DataQualityIssue.data_quality_run_id == quality_run.id)
            .order_by(DataQualityIssue.category.asc(), DataQualityIssue.code.asc(), DataQualityIssue.id.asc())
            .all()
        )
        clarification_state = _clarification_state(db, quality_run.source_table_id)
        quality_summary = json_loads(quality_run.summary_json)
        if not isinstance(quality_summary, dict):
            quality_summary = {}
        indicators = quality_summary.get("readiness_indicators")
        if not isinstance(indicators, dict):
            indicators = {}

        fingerprint_payload = {
            "evaluator_version": EVALUATOR_VERSION,
            "data_quality_run_id": quality_run.id,
            "data_quality_input_fingerprint": quality_run.input_fingerprint,
            "data_quality_status": quality_run.overall_status,
            "counts": {
                "source_rows": quality_run.source_row_count,
                "creative_records": quality_run.creative_record_count,
                "linked_creatives": quality_run.linked_creative_count,
                "observations": quality_run.performance_observation_count,
                "blocking": quality_run.blocking_issue_count,
                "warning": quality_run.warning_issue_count,
            },
            "issues": [
                {
                    "id": item.id,
                    "category": item.category,
                    "code": item.code,
                    "severity": item.severity,
                    "affected_count": item.affected_count,
                }
                for item in issues
            ],
            "indicators": indicators,
            "clarifications": clarification_state,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        existing = (
            db.query(PredictionReadinessRun)
            .filter(
                PredictionReadinessRun.data_quality_run_id == quality_run.id,
                PredictionReadinessRun.evaluator_version == EVALUATOR_VERSION,
                PredictionReadinessRun.input_fingerprint == fingerprint,
                PredictionReadinessRun.status == PredictionReadinessRunStatus.completed,
            )
            .order_by(PredictionReadinessRun.run_number.desc(), PredictionReadinessRun.created_at.desc())
            .first()
        )
        if existing is not None and not force:
            return _result_response(db, existing)

        issue_codes = {item.code for item in issues}
        blocking_codes = {item.code for item in issues if item.severity == "blocking"}
        warning_codes = {item.code for item in issues if item.severity == "warning"}
        decisions = [
            _historical_ctr_decision(quality_run, indicators, issue_codes, blocking_codes, warning_codes),
            _creative_lift_decision(quality_run, indicators, issue_codes, blocking_codes, warning_codes),
            _synthetic_click_intent_decision(quality_run, indicators),
            _brand_lift_proxy_decision(quality_run, indicators),
            _compliance_review_decision(quality_run, indicators, issue_codes, blocking_codes),
        ]

        status_counts = Counter(item.status for item in decisions)
        analytical = [item for item in decisions if item.key != "compliance_risk_review"]
        if any(item.status == CapabilityStatus.ready for item in analytical):
            overall = (
                PredictionReadinessOverallStatus.degraded
                if any(item.status in {CapabilityStatus.degraded, CapabilityStatus.unavailable} for item in analytical)
                else PredictionReadinessOverallStatus.ready
            )
        elif any(item.status == CapabilityStatus.degraded for item in analytical):
            overall = PredictionReadinessOverallStatus.degraded
        else:
            overall = PredictionReadinessOverallStatus.unavailable

        run_number = (
            db.query(func.max(PredictionReadinessRun.run_number))
            .filter(PredictionReadinessRun.data_quality_run_id == quality_run.id)
            .scalar()
            or 0
        ) + 1
        summary = {
            "policy": "capability_specific_graceful_degradation",
            "source_data_quality_status": quality_run.overall_status,
            "no_prediction_was_generated": True,
            "no_ctr_was_fabricated": True,
            "capability_order": [item.key for item in decisions],
            "clarification_state": clarification_state,
            "principles": [
                "Each analytical capability is evaluated independently.",
                "Unavailable prediction paths fall back only to explicitly allowed descriptive or workflow modes.",
                "Readiness does not claim model accuracy and does not train or invoke a model.",
                "Clarification answers are evidence only until a separate workflow updates source or normalized data.",
            ],
        }
        run = PredictionReadinessRun(
            data_quality_run_id=quality_run.id,
            source_table_id=quality_run.source_table_id,
            source_file_id=quality_run.source_file_id,
            import_session_id=quality_run.import_session_id,
            project_id=quality_run.project_id,
            run_number=run_number,
            evaluator_name=EVALUATOR_NAME,
            evaluator_version=EVALUATOR_VERSION,
            input_fingerprint=fingerprint,
            status=PredictionReadinessRunStatus.completed,
            overall_status=overall,
            capability_count=len(decisions),
            ready_count=status_counts[CapabilityStatus.ready],
            degraded_count=status_counts[CapabilityStatus.degraded],
            unavailable_count=status_counts[CapabilityStatus.unavailable],
            not_applicable_count=status_counts[CapabilityStatus.not_applicable],
            unresolved_client_question_count=clarification_state["client"]["unresolved_count"],
            unresolved_analyst_question_count=clarification_state["analyst"]["unresolved_count"],
            summary_json=json_dumps(summary),
            created_by_user_id=created_by_user_id,
        )
        db.add(run)
        db.flush()
        for item in decisions:
            db.add(
                PredictionCapabilityReadiness(
                    prediction_readiness_run_id=run.id,
                    capability_key=item.key,
                    status=item.status,
                    mode=item.mode,
                    evidence_strength=item.evidence_strength,
                    title=item.title,
                    user_message=item.user_message,
                    internal_message=item.internal_message,
                    reasons_json=json_dumps(item.reasons),
                    required_inputs_json=json_dumps(item.required_inputs),
                    missing_inputs_json=json_dumps(item.missing_inputs),
                    degraded_inputs_json=json_dumps(item.degraded_inputs),
                    allowed_operations_json=json_dumps(item.allowed_operations),
                    prohibited_operations_json=json_dumps(item.prohibited_operations),
                    evidence_json=json_dumps(item.evidence),
                )
            )
        db.flush()
        db.refresh(run)
        return _result_response(db, run)


def get_latest_prediction_readiness(data_quality_run_id: str) -> PredictionReadinessResultResponse | None:
    with db_session() as db:
        quality = db.query(DataQualityRun.id).filter(DataQualityRun.id == data_quality_run_id).first()
        if quality is None:
            raise AppError("data_quality_run_not_found", "Data-quality run not found", 404)
        run = (
            db.query(PredictionReadinessRun)
            .filter(PredictionReadinessRun.data_quality_run_id == data_quality_run_id)
            .order_by(PredictionReadinessRun.run_number.desc(), PredictionReadinessRun.created_at.desc())
            .first()
        )
        return _result_response(db, run) if run else None


def get_prediction_readiness_run(run_id: str) -> PredictionReadinessResultResponse | None:
    with db_session() as db:
        run = db.query(PredictionReadinessRun).filter(PredictionReadinessRun.id == run_id).first()
        return _result_response(db, run) if run else None


def _clarification_state(db, source_table_id: str) -> dict:
    result: dict[str, dict[str, Any]] = {}
    for audience in (ClarificationAudience.client, ClarificationAudience.analyst):
        runs = (
            db.query(ClarificationRun)
            .filter(
                ClarificationRun.source_table_id == source_table_id,
                ClarificationRun.audience == audience,
            )
            .order_by(ClarificationRun.run_number.desc(), ClarificationRun.created_at.desc())
            .all()
        )
        run_ids = [item.id for item in runs]
        questions = (
            db.query(ClarificationQuestion)
            .filter(ClarificationQuestion.clarification_run_id.in_(run_ids))
            .all()
            if run_ids
            else []
        )
        latest_by_key: dict[str, ClarificationQuestion] = {}
        for question in questions:
            latest_by_key.setdefault(question.question_key, question)
        unresolved = [
            item
            for item in latest_by_key.values()
            if item.status in {ClarificationQuestionStatus.open, ClarificationQuestionStatus.deferred}
        ]
        terminal = [item for item in latest_by_key.values() if item.status not in {ClarificationQuestionStatus.open, ClarificationQuestionStatus.deferred}]
        result[str(audience)] = {
            "run_ids": run_ids,
            "unresolved_count": len(unresolved),
            "unresolved_keys": sorted(item.question_key for item in unresolved),
            "terminal_count": len(terminal),
            "terminal_keys": sorted(item.question_key for item in terminal),
        }
    return result


def _historical_ctr_decision(run, indicators, issue_codes, blocking_codes, warning_codes):
    required = [
        "verified immutable originals",
        "completed normalization",
        "creative references",
        "media context",
        "paired clicks and impressions",
        "consistent metric semantics",
    ]
    missing = []
    if not indicators.get("file_integrity_ok"):
        missing.append("verified immutable originals")
    if not indicators.get("normalization_available"):
        missing.append("completed normalization")
    if not indicators.get("creative_references_present"):
        missing.append("creative references")
    if not indicators.get("media_context_present"):
        missing.append("media context")
    if not indicators.get("paired_click_impression_rows_present"):
        missing.append("paired clicks and impressions")
    relevant_blockers = blocking_codes & {
        "source_files_missing",
        "source_files_corrupted",
        "source_table_truncated",
        "normalization_not_available",
        "negative_impressions",
        "negative_clicks",
        "negative_ctr",
        "clicks_with_zero_impressions",
        "no_usable_normalized_rows",
    }
    degraded = []
    if run.performance_observation_count < 20:
        degraded.append("fewer than 20 normalized observations")
    if not indicators.get("creative_assets_linked"):
        degraded.append("creative references are not linked to uploaded assets")
    if warning_codes & {
        "ctr_percent_scale_suspected",
        "ctr_click_impression_mismatch",
        "clicks_above_impressions",
        "duplicate_performance_observations",
        "missing_platform",
        "missing_format",
        "missing_placement_type",
    }:
        degraded.append("metric or media-context warnings remain")
    if missing or relevant_blockers:
        status = CapabilityStatus.unavailable
        mode = "disabled"
        strength = EvidenceStrength.none
        user = "Historical CTR prediction is unavailable for this delivery. The report may only describe the imported data and list the missing evidence."
        allowed = ["data-quality review", "descriptive counts", "clarification workflow"]
    elif degraded:
        status = CapabilityStatus.degraded
        mode = "descriptive_baseline_or_calibration_only"
        strength = EvidenceStrength.weak if run.performance_observation_count < 10 else EvidenceStrength.moderate
        user = "Historical CTR analysis is available only as a descriptive baseline or calibration exercise. Creative-specific CTR must not be presented as a reliable prediction."
        allowed = ["descriptive baseline", "exploratory calibration", "backtest design", "uncertainty statement"]
    else:
        status = CapabilityStatus.ready
        mode = "ready_for_model_evaluation"
        strength = EvidenceStrength.strong
        user = "The data is ready for a separately validated historical CTR modelling and backtesting step. No prediction has been generated yet."
        allowed = ["model evaluation", "backtesting", "calibration", "prediction with explicit uncertainty after validation"]
    return _Decision(
        key="historical_ctr_prediction",
        title="Historical CTR prediction",
        status=status,
        mode=mode,
        evidence_strength=strength,
        user_message=user,
        internal_message="Readiness concerns data and workflow only; the final algorithm, validation threshold and accuracy claims remain frozen until real data is assessed.",
        required_inputs=required,
        missing_inputs=sorted(set(missing) | set(relevant_blockers)),
        degraded_inputs=degraded,
        allowed_operations=allowed,
        prohibited_operations=["fabricated CTR", "accuracy guarantee", "creative-specific prediction without validation", "silent metric repair"],
        reasons=_reason_rows(missing, degraded, relevant_blockers),
        evidence=_base_evidence(run, indicators, issue_codes),
    )


def _creative_lift_decision(run, indicators, issue_codes, blocking_codes, warning_codes):
    required = ["at least two creatives", "linked creative assets", "performance observations", "comparable media context"]
    missing = []
    if run.creative_record_count < 2:
        missing.append("at least two creatives")
    if run.linked_creative_count < 2:
        missing.append("linked creative assets")
    if run.performance_observation_count < 2:
        missing.append("performance observations")
    if not indicators.get("media_context_present"):
        missing.append("comparable media context")
    blockers = blocking_codes & {"source_files_missing", "source_files_corrupted", "normalization_not_available", "no_usable_normalized_rows"}
    degraded = []
    if run.performance_observation_count < 20:
        degraded.append("small historical sample")
    if warning_codes & {"duplicate_performance_observations", "missing_platform", "missing_format", "missing_placement_type"}:
        degraded.append("comparability warnings remain")
    if missing or blockers:
        status, mode, strength = CapabilityStatus.unavailable, "disabled", EvidenceStrength.none
        user = "Creative lift estimation is unavailable because the delivery does not contain enough linked creatives in comparable observed contexts."
        allowed = ["creative inventory review", "context coverage review"]
    elif degraded:
        status, mode, strength = CapabilityStatus.degraded, "directional_comparison_only", EvidenceStrength.weak
        user = "Only directional creative comparisons are supportable. Causal or media-normalized lift must not be claimed."
        allowed = ["directional comparison", "matched-context exploration", "uncertainty disclosure"]
    else:
        status, mode, strength = CapabilityStatus.ready, "ready_for_comparability_analysis", EvidenceStrength.moderate
        user = "The delivery is ready for a separately validated comparable-context creative lift analysis. Causal claims still require an explicit design."
        allowed = ["matched-context analysis", "lift model evaluation", "sensitivity analysis"]
    return _Decision(
        key="creative_lift_estimation",
        title="Creative lift estimation",
        status=status,
        mode=mode,
        evidence_strength=strength,
        user_message=user,
        internal_message="Readiness never converts observational association into a causal lift claim.",
        required_inputs=required,
        missing_inputs=sorted(set(missing) | set(blockers)),
        degraded_inputs=degraded,
        allowed_operations=allowed,
        prohibited_operations=["causal lift claim without design", "comparison across uncontrolled media contexts", "fabricated control group"],
        reasons=_reason_rows(missing, degraded, blockers),
        evidence=_base_evidence(run, indicators, issue_codes),
    )


def _synthetic_click_intent_decision(run, indicators):
    missing = []
    if not indicators.get("creative_references_present"):
        missing.append("creative references")
    if not indicators.get("creative_assets_linked"):
        missing.append("linked creative assets")
    degraded = ["quantitative questionnaire is not configured yet"]
    if missing:
        status, mode, strength = CapabilityStatus.unavailable, "disabled", EvidenceStrength.none
        user = "Synthetic click-intent measurement cannot be prepared until the tested creatives are identified and linked."
        allowed = ["creative inventory preparation"]
    else:
        status, mode, strength = CapabilityStatus.degraded, "questionnaire_configuration_required", EvidenceStrength.weak
        user = "The creatives can enter a quantitative click-intent workflow after a questionnaire and respondent plan are configured. No synthetic score exists yet."
        allowed = ["questionnaire design", "stimulus assignment", "respondent-plan preparation"]
    return _Decision(
        key="synthetic_click_intent",
        title="Synthetic click intent",
        status=status,
        mode=mode,
        evidence_strength=strength,
        user_message=user,
        internal_message="CTA-PRE-009 supplies questionnaire configuration; this readiness decision must be reevaluated after that stage produces evidence.",
        required_inputs=["linked creative assets", "configured quantitative questionnaire", "respondent plan", "completed responses"],
        missing_inputs=missing + (["questionnaire configuration", "respondent plan", "completed responses"] if not missing else []),
        degraded_inputs=degraded if not missing else [],
        allowed_operations=allowed,
        prohibited_operations=["invented respondent answers", "qualitative interview claims", "synthetic score without completed responses"],
        reasons=_reason_rows(missing, degraded if not missing else [], set()),
        evidence=_base_evidence(run, indicators, set()),
    )


def _brand_lift_proxy_decision(run, indicators):
    missing = []
    if not indicators.get("creative_assets_linked"):
        missing.append("linked creative assets")
    if run.creative_record_count == 0:
        missing.append("creative records")
    if missing:
        status, mode, strength = CapabilityStatus.unavailable, "disabled", EvidenceStrength.none
        user = "Brand-lift proxy measurement is unavailable until tested creatives are identified and linked."
        allowed = ["stimulus inventory preparation"]
        degraded = []
    else:
        status, mode, strength = CapabilityStatus.degraded, "questionnaire_configuration_required", EvidenceStrength.weak
        user = "A brand-lift proxy study can be configured, but no proxy score or benchmark is available before questionnaire setup and completed responses."
        allowed = ["questionnaire design", "brand and product context review", "proxy endpoint definition"]
        degraded = ["questionnaire is not configured", "no completed responses", "no client-specific benchmark"]
    return _Decision(
        key="brand_lift_proxy",
        title="Brand-lift proxy",
        status=status,
        mode=mode,
        evidence_strength=strength,
        user_message=user,
        internal_message="No pharmaceutical or brand-lift norm is assumed. Benchmarks remain client- and study-specific.",
        required_inputs=["linked creative assets", "brand/product context", "configured questionnaire", "completed responses", "approved benchmark or interpretation rule"],
        missing_inputs=missing + (["questionnaire configuration", "completed responses", "approved interpretation rule"] if not missing else []),
        degraded_inputs=degraded,
        allowed_operations=allowed,
        prohibited_operations=["invented brand-lift norm", "causal lift claim", "proxy presented as observed market lift"],
        reasons=_reason_rows(missing, degraded, set()),
        evidence=_base_evidence(run, indicators, set()),
    )


def _compliance_review_decision(run, indicators, issue_codes, blocking_codes):
    missing = []
    if not indicators.get("creative_assets_linked"):
        missing.append("linked creative assets")
    blockers = blocking_codes & {"source_files_missing", "source_files_corrupted"}
    degraded = []
    if run.unlinked_creative_count:
        degraded.append("some creative references remain unlinked")
    if missing or blockers:
        status, mode, strength = CapabilityStatus.unavailable, "inventory_only", EvidenceStrength.none
        user = "Creative-specific compliance review is unavailable; only an inventory gap report can be produced."
        allowed = ["inventory gap report", "checklist preparation"]
    elif degraded:
        status, mode, strength = CapabilityStatus.degraded, "linked_assets_only", EvidenceStrength.moderate
        user = "Compliance review can cover linked assets only; unlinked references remain outside the review scope."
        allowed = ["linked-asset checklist review", "risk flagging", "human approval workflow"]
    else:
        status, mode, strength = CapabilityStatus.ready, "checklist_and_human_review", EvidenceStrength.strong
        user = "The linked creative inventory is ready for rules-based risk flagging and mandatory human compliance review."
        allowed = ["checklist review", "risk flagging", "evidence capture", "human approval workflow"]
    return _Decision(
        key="compliance_risk_review",
        title="Compliance risk review",
        status=status,
        mode=mode,
        evidence_strength=strength,
        user_message=user,
        internal_message="Readiness does not constitute legal or medical approval. Human review remains mandatory.",
        required_inputs=["linked creative assets", "applicable checklist", "human reviewer"],
        missing_inputs=sorted(set(missing) | set(blockers)),
        degraded_inputs=degraded,
        allowed_operations=allowed,
        prohibited_operations=["automatic legal approval", "automatic medical approval", "claim that absence of flags means compliance"],
        reasons=_reason_rows(missing, degraded, blockers),
        evidence=_base_evidence(run, indicators, issue_codes),
    )


def _reason_rows(missing, degraded, blockers):
    rows = []
    for item in sorted(set(missing)):
        rows.append({"kind": "missing_input", "value": item})
    for item in sorted(set(blockers)):
        rows.append({"kind": "blocking_issue", "value": item})
    for item in sorted(set(degraded)):
        rows.append({"kind": "degradation", "value": item})
    return rows


def _base_evidence(run, indicators, issue_codes):
    return {
        "data_quality_run_id": run.id,
        "data_quality_input_fingerprint": run.input_fingerprint,
        "data_quality_overall_status": run.overall_status,
        "source_row_count": run.source_row_count,
        "creative_record_count": run.creative_record_count,
        "linked_creative_count": run.linked_creative_count,
        "unlinked_creative_count": run.unlinked_creative_count,
        "performance_observation_count": run.performance_observation_count,
        "blocking_issue_count": run.blocking_issue_count,
        "warning_issue_count": run.warning_issue_count,
        "readiness_indicators": indicators,
        "issue_codes": sorted(issue_codes),
    }


def _result_response(db, run):
    capabilities = (
        db.query(PredictionCapabilityReadiness)
        .filter(PredictionCapabilityReadiness.prediction_readiness_run_id == run.id)
        .order_by(PredictionCapabilityReadiness.created_at.asc(), PredictionCapabilityReadiness.capability_key.asc())
        .all()
    )
    summary = json_loads(run.summary_json)
    return PredictionReadinessResultResponse(
        run=PredictionReadinessRunResponse(
            id=run.id,
            data_quality_run_id=run.data_quality_run_id,
            source_table_id=run.source_table_id,
            source_file_id=run.source_file_id,
            import_session_id=run.import_session_id,
            project_id=run.project_id,
            run_number=run.run_number,
            evaluator_name=run.evaluator_name,
            evaluator_version=run.evaluator_version,
            input_fingerprint=run.input_fingerprint,
            status=run.status,
            overall_status=run.overall_status,
            capability_count=run.capability_count,
            ready_count=run.ready_count,
            degraded_count=run.degraded_count,
            unavailable_count=run.unavailable_count,
            not_applicable_count=run.not_applicable_count,
            unresolved_client_question_count=run.unresolved_client_question_count,
            unresolved_analyst_question_count=run.unresolved_analyst_question_count,
            summary=summary if isinstance(summary, dict) else {},
            error_code=run.error_code,
            error_message=run.error_message,
            created_by_user_id=run.created_by_user_id,
            created_at=run.created_at,
        ),
        capabilities=[_capability_response(item) for item in capabilities],
    )


def _capability_response(item):
    def _list(value):
        parsed = json_loads(value)
        return parsed if isinstance(parsed, list) else []

    evidence = json_loads(item.evidence_json)
    return PredictionCapabilityResponse(
        id=item.id,
        prediction_readiness_run_id=item.prediction_readiness_run_id,
        capability_key=item.capability_key,
        status=item.status,
        mode=item.mode,
        evidence_strength=item.evidence_strength,
        title=item.title,
        user_message=item.user_message,
        internal_message=item.internal_message,
        reasons=_list(item.reasons_json),
        required_inputs=_list(item.required_inputs_json),
        missing_inputs=_list(item.missing_inputs_json),
        degraded_inputs=_list(item.degraded_inputs_json),
        allowed_operations=_list(item.allowed_operations_json),
        prohibited_operations=_list(item.prohibited_operations_json),
        evidence=evidence if isinstance(evidence, dict) else {},
        created_at=item.created_at,
    )
