from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.modules.creative_assets.models import CreativeAsset
from src.modules.normalized_data.models import (
    Campaign,
    CreativeRecord,
    NormalizationRun,
    NormalizationRunStatus,
    PerformanceObservation,
    Placement,
)
from src.modules.ozon_showcase_loader.contracts import LOADER_NAME
from src.modules.projects.models import Project
from src.modules.test_runs.models import TestRun
from src.shared.db.repository import db_session, json_loads
from src.shared.errors import AppError

from .schemas import (
    AgentDiagnosticEvidence,
    CampaignAssetEvidence,
    CampaignEvidence,
    CampaignEvidenceSummary,
    CampaignEvidenceWorkspace,
    CampaignOutcomeEvidence,
    EvidenceBoundary,
    EvidenceLimitation,
)


ACCEPTED_LINKAGE_STATUSES = {"exact", "probable", "one_to_many", "uncertain"}
CONTRAST_CASE_ORDER = ("OZON-007", "OZON-003", "OZON-001", "OZON-006")
METRIC_LABELS = {
    "ad_recall": "Ad recall",
    "awareness": "Brand awareness",
    "customer_consideration": "Customer consideration",
    "purchase_intent": "Purchase intent",
}
METRIC_ORDER = {
    "ad_recall": 10,
    "awareness": 20,
    "customer_consideration": 30,
    "purchase_intent": 40,
}


def get_campaign_evidence_workspace(project_id: str) -> CampaignEvidenceWorkspace:
    with db_session() as db:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project is None:
            raise AppError("project_not_found", "Project not found", 404)

        run = _latest_showcase_run(db, project_id)
        if run is None:
            raise AppError(
                "ozon_showcase_not_loaded",
                "No completed Ozon showcase loader run exists for this project",
                404,
            )

        campaign_models = (
            db.query(Campaign)
            .filter(
                Campaign.normalization_run_id == run.id,
                Campaign.project_id == project_id,
            )
            .order_by(Campaign.reference_key.asc(), Campaign.id.asc())
            .all()
        )
        creative_records = (
            db.query(CreativeRecord)
            .filter(
                CreativeRecord.normalization_run_id == run.id,
                CreativeRecord.project_id == project_id,
            )
            .order_by(CreativeRecord.display_reference.asc(), CreativeRecord.id.asc())
            .all()
        )
        placements = (
            db.query(Placement)
            .filter(
                Placement.normalization_run_id == run.id,
                Placement.project_id == project_id,
            )
            .all()
        )
        observations = (
            db.query(PerformanceObservation)
            .filter(
                PerformanceObservation.normalization_run_id == run.id,
                PerformanceObservation.project_id == project_id,
            )
            .all()
        )

        asset_ids = [
            item.creative_asset_id
            for item in creative_records
            if item.creative_asset_id
        ]
        assets_by_id: dict[str, CreativeAsset] = {}
        if asset_ids:
            assets_by_id = {
                item.id: item
                for item in db.query(CreativeAsset)
                .filter(CreativeAsset.id.in_(asset_ids))
                .all()
            }
        diagnostics_by_asset = _latest_diagnostics(db, asset_ids)

        placements_by_id = {item.id: item for item in placements}
        outcomes_by_campaign: dict[str, list[CampaignOutcomeEvidence]] = defaultdict(list)
        for observation in observations:
            placement = placements_by_id.get(observation.placement_id or "")
            if placement is None or placement.campaign_id is None:
                continue
            outcomes_by_campaign[placement.campaign_id].append(
                _outcome_evidence(observation)
            )
        for items in outcomes_by_campaign.values():
            items.sort(key=lambda item: (METRIC_ORDER.get(item.metric, 999), item.metric))

        records_by_case: dict[str, list[CreativeRecord]] = defaultdict(list)
        unlabelled_records: list[CreativeRecord] = []
        for record in creative_records:
            metadata = _mapping(record.metadata_json)
            case_id = _text(metadata.get("linked_case_id"))
            if case_id:
                records_by_case[case_id].append(record)
            else:
                unlabelled_records.append(record)

        campaigns = [
            _campaign_evidence(
                model=model,
                records=records_by_case.get(model.reference_key or "", []),
                outcomes=outcomes_by_campaign.get(model.id, []),
                assets_by_id=assets_by_id,
                diagnostics_by_asset=diagnostics_by_asset,
            )
            for model in campaign_models
        ]
        campaigns.sort(key=_campaign_sort_key)

        unlabelled_assets = [
            _asset_evidence(
                record,
                assets_by_id.get(record.creative_asset_id or ""),
                diagnostics_by_asset.get(record.creative_asset_id or ""),
            )
            for record in unlabelled_records
        ]

        accepted_asset_count = sum(
            asset.accepted_for_campaign_set
            for campaign in campaigns
            for asset in campaign.assets
        )
        rejected_asset_count = sum(
            asset.linkage_status == "rejected"
            for campaign in campaigns
            for asset in campaign.assets
        )
        campaigns_with_diagnostics = sum(
            any(asset.diagnostic.status == "completed" for asset in campaign.assets)
            for campaign in campaigns
        )
        warnings = _mapping(run.warnings_json)
        source_fingerprint = _text(warnings.get("source_fingerprint")) or run.mapping_fingerprint

        return CampaignEvidenceWorkspace(
            project_id=project.id,
            project_name=project.name,
            normalization_run_id=run.id,
            source_fingerprint=source_fingerprint,
            mapping_version=run.normalizer_version,
            generated_from_loader=run.normalizer_name,
            evidence_boundaries=EvidenceBoundary(),
            summary=CampaignEvidenceSummary(
                campaign_count=len(campaigns),
                outcome_count=sum(len(item.outcomes) for item in campaigns),
                creative_count=sum(len(item.assets) for item in campaigns) + len(unlabelled_assets),
                accepted_asset_count=accepted_asset_count,
                rejected_asset_count=rejected_asset_count,
                unlabelled_asset_count=len(unlabelled_assets),
                campaigns_with_diagnostics=campaigns_with_diagnostics,
                campaigns_with_limitations=sum(bool(item.limitations) for item in campaigns),
            ),
            campaigns=campaigns,
            unlabelled_assets=unlabelled_assets,
        )


def get_campaign_evidence_detail(project_id: str, campaign_id: str) -> CampaignEvidence:
    workspace = get_campaign_evidence_workspace(project_id)
    for campaign in workspace.campaigns:
        if campaign.campaign_id == campaign_id or campaign.case_id == campaign_id:
            return campaign
    raise AppError("campaign_not_found", "Campaign not found in Ozon showcase workspace", 404)


def _latest_showcase_run(db, project_id: str) -> NormalizationRun | None:
    return (
        db.query(NormalizationRun)
        .filter(
            NormalizationRun.project_id == project_id,
            NormalizationRun.normalizer_name == LOADER_NAME,
            NormalizationRun.status == NormalizationRunStatus.completed,
        )
        .order_by(NormalizationRun.created_at.desc(), NormalizationRun.id.desc())
        .first()
    )


def _latest_diagnostics(db, asset_ids: list[str]) -> dict[str, AgentDiagnosticEvidence]:
    if not asset_ids:
        return {}
    runs = (
        db.query(TestRun)
        .filter(TestRun.creative_asset_id.in_(asset_ids))
        .order_by(TestRun.created_at.desc(), TestRun.id.desc())
        .all()
    )
    selected: dict[str, TestRun] = {}
    fallback: dict[str, TestRun] = {}
    for run in runs:
        fallback.setdefault(run.creative_asset_id, run)
        if run.status == "completed":
            selected.setdefault(run.creative_asset_id, run)
    for asset_id, run in fallback.items():
        selected.setdefault(asset_id, run)
    return {asset_id: _diagnostic_evidence(run) for asset_id, run in selected.items()}


def _diagnostic_evidence(run: TestRun | None) -> AgentDiagnosticEvidence:
    if run is None:
        return AgentDiagnosticEvidence()
    payload = _mapping(run.structured_findings_json)
    return AgentDiagnosticEvidence(
        test_run_id=run.id,
        status=run.status,
        summary=run.summary or "",
        overall_score=run.overall_score,
        proposed_recommendation=run.final_recommendation or "",
        effective_recommendation=_text(payload.get("effective_recommendation")) or (run.final_recommendation or ""),
        findings=_dict_list(payload.get("findings")),
        scorecard=_dict_list(payload.get("scorecard")),
        risks=_dict_list(payload.get("risks")),
        visual_traceability_status=_text(payload.get("visual_traceability_status")) or "not_available",
        visual_decision_status=_text(payload.get("visual_decision_status")) or "not_available",
        completed_at=run.completed_at,
    )


def _campaign_evidence(
    *,
    model: Campaign,
    records: list[CreativeRecord],
    outcomes: list[CampaignOutcomeEvidence],
    assets_by_id: dict[str, CreativeAsset],
    diagnostics_by_asset: dict[str, AgentDiagnosticEvidence],
) -> CampaignEvidence:
    metadata = _mapping(model.metadata_json)
    assets = [
        _asset_evidence(
            record,
            assets_by_id.get(record.creative_asset_id or ""),
            diagnostics_by_asset.get(record.creative_asset_id or ""),
        )
        for record in records
    ]
    assets.sort(key=lambda item: (item.linkage_status == "rejected", item.filename or item.title))
    accepted = [item for item in assets if item.accepted_for_campaign_set]
    rejected = [item for item in assets if item.linkage_status == "rejected"]
    limitations: list[EvidenceLimitation] = []

    if not accepted:
        limitations.append(EvidenceLimitation(
            code="campaign_without_accepted_asset",
            message="Observed campaign outcomes have no accepted platform-matched creative in the supplied package.",
            severity="high",
        ))
    if len(accepted) > 1 or any(item.linkage_status == "one_to_many" for item in accepted):
        limitations.append(EvidenceLimitation(
            code="campaign_multi_asset",
            message="Outcomes are campaign-level evidence and must not be attributed to one creative asset.",
            context={"accepted_asset_count": len(accepted)},
        ))
    if rejected:
        limitations.append(EvidenceLimitation(
            code="rejected_asset_link",
            message="One or more supplied assets are rejected for campaign attribution, usually because the platform does not match.",
            context={"rejected_asset_count": len(rejected)},
        ))
    if not outcomes:
        limitations.append(EvidenceLimitation(
            code="missing_outcomes",
            message="No observed CG/TG outcomes are available for this campaign.",
            severity="high",
        ))
    if not any(item.diagnostic.status == "completed" for item in accepted):
        limitations.append(EvidenceLimitation(
            code="missing_diagnostics",
            message="No completed asset-level agent diagnostic is available for the accepted creative set.",
            severity="info",
        ))

    case_id = model.reference_key or _text(metadata.get("case_id")) or model.id
    try:
        rank = CONTRAST_CASE_ORDER.index(case_id) + 1
    except ValueError:
        rank = None

    return CampaignEvidence(
        campaign_id=model.id,
        case_id=case_id,
        brand=model.brand,
        product=model.product,
        period_start=_text(metadata.get("period_start")),
        period_end=_text(metadata.get("period_end")),
        platform=_text(metadata.get("platform")),
        is_contrast_case=rank is not None,
        showcase_rank=rank,
        campaign_level_outcomes=bool(metadata.get("campaign_level_outcomes", True)),
        individual_asset_attribution_allowed=False,
        assets=assets,
        outcomes=outcomes,
        limitations=limitations,
    )


def _asset_evidence(
    record: CreativeRecord,
    asset: CreativeAsset | None,
    diagnostic: AgentDiagnosticEvidence | None,
) -> CampaignAssetEvidence:
    metadata = _mapping(record.metadata_json)
    asset_metadata = _mapping(asset.metadata_json if asset is not None else None)
    status = _text(metadata.get("linkage_status")) or _text(asset_metadata.get("linkage_status")) or "uncertain"
    confidence = _float(metadata.get("linkage_confidence"), default=0.0)
    notes = metadata.get("notes")
    if not isinstance(notes, list):
        notes = asset_metadata.get("linkage_notes")
    if isinstance(notes, str):
        notes = [notes]
    if not isinstance(notes, list):
        notes = []
    asset_id = record.creative_asset_id
    return CampaignAssetEvidence(
        creative_record_id=record.id,
        creative_asset_id=asset_id,
        title=(asset.title if asset is not None else None) or record.display_reference or record.reference_key,
        filename=(asset.original_filename if asset is not None else None) or record.display_reference,
        preview_url=f"/creative-assets/{asset_id}/image" if asset_id and asset is not None and asset.asset_type == "image" else None,
        brand=_text(metadata.get("brand")) or _text(asset_metadata.get("brand")),
        inferred_platform=_text(metadata.get("inferred_platform")) or _text(asset_metadata.get("inferred_platform")),
        linkage_status=status,
        linkage_confidence=confidence,
        linkage_notes=[str(item) for item in notes],
        accepted_for_campaign_set=status in ACCEPTED_LINKAGE_STATUSES,
        diagnostic=diagnostic or AgentDiagnosticEvidence(),
    )


def _outcome_evidence(observation: PerformanceObservation) -> CampaignOutcomeEvidence:
    metadata = _mapping(observation.metadata_json)
    metric = _text(metadata.get("metric")) or "unknown"
    return CampaignOutcomeEvidence(
        observation_id=observation.id,
        metric=metric,
        metric_label=METRIC_LABELS.get(metric, metric.replace("_", " ").title()),
        control_n=_int(metadata.get("control_n")),
        test_n=_int(metadata.get("test_n")),
        cg_rate=_optional_float(metadata.get("cg_rate")),
        tg_rate=_optional_float(metadata.get("tg_rate")),
        uplift_pp_descriptive=_optional_float(metadata.get("uplift_pp_descriptive")),
        evidence_status=_text(metadata.get("evidence_status")),
        period_start=_text(metadata.get("period_start")),
        period_end=_text(metadata.get("period_end")),
        platform=_text(metadata.get("platform")),
        source_sheet=_text(metadata.get("source_sheet")),
        source_row_number=_int(metadata.get("source_row_number")),
        causal_interpretation_allowed=bool(metadata.get("causal_interpretation_allowed", False)),
        numeric_prediction_generated=bool(metadata.get("numeric_prediction_generated", False)),
        notes=[str(item) for item in metadata.get("notes", [])] if isinstance(metadata.get("notes"), list) else [],
    )


def _campaign_sort_key(item: CampaignEvidence):
    if item.showcase_rank is not None:
        return (0, item.showcase_rank, item.case_id)
    return (1, 999, item.case_id)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    parsed = json_loads(value) if value else {}
    return parsed if isinstance(parsed, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return None if value is None or value == "" else int(value)
    except (TypeError, ValueError):
        return None
