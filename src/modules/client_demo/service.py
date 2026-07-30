from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from src.modules.campaign_evidence.schemas import (
    CampaignAssetEvidence,
    CampaignEvidence,
    CampaignEvidenceWorkspace,
)
from src.modules.campaign_evidence.service import get_campaign_evidence_workspace
from src.modules.client_report_v2.schemas import ClientReportV2Response
from src.modules.client_report_v2.service import get_client_report_v2
from src.modules.creative_assets.models import CreativeAsset
from src.modules.test_runs.visual_context import build_visual_evidence
from src.shared.db.repository import db_session
from src.shared.errors import AppError

from .schemas import (
    DemoCampaignOption,
    DemoPrimaryAsset,
    DemoReportArtifact,
    DemoReportState,
    DemoStep,
    DemoVisualExtraction,
    DemoVisualObservation,
    OzonClientDemoState,
)

_VISUAL_LABELS = {
    "ocr_text": "OCR text",
    "visual_summary": "Visual summary",
    "brand_logo_prominence": "Brand/logo prominence",
    "packshot": "Packshot",
    "cta": "CTA",
    "promo_badge": "Promo badge",
    "hierarchy": "Hierarchy",
    "message_visual_binding": "Message–visual binding",
    "cognitive_load": "Cognitive load",
    "readability": "Readability",
    "visual_risks": "Visual risk",
}


def build_ozon_client_demo(
    project_id: str,
    *,
    campaign_id: str | None = None,
    report_id: str | None = None,
) -> OzonClientDemoState:
    workspace = get_campaign_evidence_workspace(project_id)
    visual_by_asset = _load_visual_evidence_map(workspace)
    report = get_client_report_v2(project_id, report_id) if report_id else None
    return compose_ozon_client_demo(
        workspace,
        campaign_id=campaign_id,
        report=report,
        visual_by_asset=visual_by_asset,
    )


def compose_ozon_client_demo(
    workspace: CampaignEvidenceWorkspace,
    *,
    campaign_id: str | None = None,
    report: ClientReportV2Response | DemoReportState | None = None,
    visual_by_asset: dict[str, DemoVisualExtraction] | None = None,
) -> OzonClientDemoState:
    if not workspace.campaigns:
        raise AppError("demo_campaigns_missing", "The showcase project has no campaigns", 409)

    visual_by_asset = visual_by_asset or {}
    selected = _select_campaign(workspace, campaign_id, visual_by_asset)
    asset = _select_primary_asset(selected, visual_by_asset)
    visual = _visual_for_asset(asset, visual_by_asset)
    primary_asset = DemoPrimaryAsset(asset=asset, visual_extraction=visual) if asset else None
    report_state = _report_state(report)
    limitation_codes = [item.code for item in selected.limitations]

    project_refs = [
        f"normalization_run:{workspace.normalization_run_id}",
        f"source_fingerprint:{workspace.source_fingerprint or 'missing'}",
    ]
    campaign_refs = [f"campaign:{selected.campaign_id}", f"case:{selected.case_id}"]
    asset_refs = []
    if asset is not None:
        asset_refs.extend(
            [
                f"creative_record:{asset.creative_record_id}",
                f"creative_asset:{asset.creative_asset_id or 'missing'}",
                f"linkage:{asset.linkage_status}:{asset.linkage_confidence:.4f}",
            ]
        )
    diagnostic_refs = []
    if asset is not None and asset.diagnostic.test_run_id:
        diagnostic_refs.append(f"test_run:{asset.diagnostic.test_run_id}")
    outcome_refs = [f"outcome:{item.observation_id}" for item in selected.outcomes]

    accepted_assets = [item for item in selected.assets if item.accepted_for_campaign_set]
    preview_ready = asset is not None and bool(asset.preview_url)
    visual_status = "blocked"
    if asset is not None:
        if visual.observations:
            visual_status = "ready" if visual.status == "available" else "limited"
        else:
            visual_status = "limited"
    diagnostic_ready = asset is not None and asset.diagnostic.status == "completed"
    outcomes_ready = bool(selected.outcomes)

    steps = [
        DemoStep(
            ordinal=1,
            code="showcase_project",
            title="Открыть showcase-проект",
            operator_prompt="Покажите, что все материалы, история и отчёты находятся в локальном проекте.",
            status="ready",
            evidence_references=project_refs,
        ),
        DemoStep(
            ordinal=2,
            code="campaign_selection",
            title="Выбрать кампанию",
            operator_prompt="Выберите контрастный кейс и проговорите уровень linkage до интерпретации результатов.",
            status="ready" if accepted_assets else "limited",
            evidence_references=campaign_refs,
            limitation_codes=limitation_codes,
        ),
        DemoStep(
            ordinal=3,
            code="original_creative",
            title="Показать исходный креатив",
            operator_prompt="Откройте исходный файл и назовите платформу, имя файла и confidence связи с кампанией.",
            status="ready" if preview_ready else ("limited" if asset is not None else "blocked"),
            evidence_references=asset_refs,
            limitation_codes=limitation_codes,
        ),
        DemoStep(
            ordinal=4,
            code="visual_extraction",
            title="Показать visual extraction",
            operator_prompt="Покажите OCR, визуальное резюме, наблюдения, confidence, provenance и abstention/missing state.",
            status=visual_status,
            evidence_references=list(visual.reference_ids),
            limitation_codes=list(visual.limitations),
        ),
        DemoStep(
            ordinal=5,
            code="funnel_diagnostics",
            title="Показать funnel diagnostics",
            operator_prompt="Разберите scorecard, findings, risks и effective recommendation как диагностику агента, а не факт рынка.",
            status="ready" if diagnostic_ready else ("limited" if asset else "blocked"),
            evidence_references=diagnostic_refs,
            limitation_codes=["missing_diagnostics"] if not diagnostic_ready else [],
        ),
        DemoStep(
            ordinal=6,
            code="cg_tg_comparison",
            title="Сопоставить с CG/TG",
            operator_prompt="Покажите фактические campaign-level CG/TG рядом с диагностикой, не называя разницу causal uplift.",
            status="ready" if outcomes_ready else "limited",
            evidence_references=outcome_refs,
            limitation_codes=limitation_codes,
        ),
        DemoStep(
            ordinal=7,
            code="report_download",
            title="Скачать отчёт",
            operator_prompt="Сформируйте report v2 и скачайте нужный формат; manifest и SHA-256 остаются частью evidence chain.",
            status="ready" if report_state else "limited",
            evidence_references=[f"report:{report_state.report_id}"] if report_state else [],
            limitation_codes=[] if report_state else ["report_not_generated"],
        ),
    ]

    return OzonClientDemoState(
        project_id=workspace.project_id,
        project_name=workspace.project_name,
        selected_campaign_id=selected.campaign_id,
        selected_case_id=selected.case_id,
        campaign_options=[_campaign_option(item, visual_by_asset) for item in workspace.campaigns],
        selected_campaign=selected,
        primary_asset=primary_asset,
        steps=steps,
        report=report_state,
        demo_ready=all(item.status != "blocked" for item in steps[:6]),
        evidence_boundaries=workspace.evidence_boundaries,
        operator_stop_conditions=[
            "Не показывать campaign outcome как результат отдельного креатива.",
            "Не заполнять missing visual fields или CG/TG значения догадкой.",
            "Не называть descriptive difference причинным uplift или прогнозом.",
            "Остановить демонстрацию, если preview, evidence references или report integrity check не проходят.",
        ],
    )


def _load_visual_evidence_map(workspace: CampaignEvidenceWorkspace) -> dict[str, DemoVisualExtraction]:
    asset_ids = {
        asset.creative_asset_id
        for campaign in workspace.campaigns
        for asset in campaign.assets
        if asset.creative_asset_id
    }
    asset_ids.update(
        asset.creative_asset_id for asset in workspace.unlabelled_assets if asset.creative_asset_id
    )
    if not asset_ids:
        return {}
    with db_session() as db:
        assets = db.query(CreativeAsset).filter(CreativeAsset.id.in_(asset_ids)).all()
        return {asset.id: _visual_extraction(asset) for asset in assets}


def _visual_extraction(asset: CreativeAsset) -> DemoVisualExtraction:
    try:
        envelope = build_visual_evidence(asset)
    except Exception:
        return DemoVisualExtraction(
            status="missing",
            warnings=["visual_evidence_invalid"],
            limitations=["visual evidence could not be validated; do not infer visual absence"],
        )

    refs_by_path: dict[str, list[str]] = defaultdict(list)
    for reference in envelope.references:
        refs_by_path[reference.observation_path].append(reference.reference_id)

    observations: list[DemoVisualObservation] = []
    context = envelope.visual_context
    provider = ""
    if context is not None:
        provider = context.extraction.provider
        for field, label in _VISUAL_LABELS.items():
            value = getattr(context, field, None)
            if value is None:
                continue
            items = value if isinstance(value, list) else [value]
            for index, item in enumerate(items):
                path = f"visual_context.{field}"
                if isinstance(value, list):
                    path += f"[{index}]"
                payload = item.model_dump(mode="json", exclude_none=True)
                observations.append(
                    DemoVisualObservation(
                        observation_path=path,
                        label=label,
                        value=_observation_value(payload),
                        confidence=float(payload.get("confidence", 0.0)),
                        evidence_reference_ids=refs_by_path.get(path, []),
                        provenance=_provenance_labels(payload.get("provenance")),
                    )
                )

    return DemoVisualExtraction(
        status=envelope.status,
        provider=provider,
        extraction_confidence=envelope.extraction_confidence,
        evidence_confidence=envelope.evidence_confidence,
        completeness_ratio=envelope.completeness_ratio,
        fingerprint=envelope.fingerprint,
        reference_ids=[item.reference_id for item in envelope.references],
        observations=observations,
        warnings=list(envelope.warnings),
        limitations=list(envelope.limitations),
    )


def _observation_value(payload: dict[str, Any]) -> str:
    if payload.get("value"):
        return str(payload["value"])
    parts: list[str] = []
    for key in ("presence", "prominence", "text", "description", "level", "explanation", "risk_type", "mitigation"):
        if payload.get(key) not in (None, "", []):
            parts.append(f"{key}: {payload[key]}")
    for key in ("ordered_elements", "notes", "drivers", "issues"):
        values = payload.get(key)
        if values:
            parts.append(f"{key}: {', '.join(str(item) for item in values)}")
    if parts:
        return "; ".join(parts)
    compact = {key: value for key, value in payload.items() if key not in {"confidence", "provenance"}}
    return json.dumps(compact, ensure_ascii=False, sort_keys=True)


def _provenance_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    labels = []
    for item in value:
        if not isinstance(item, dict):
            continue
        labels.append(
            ":".join(
                str(item.get(key) or "unknown")
                for key in ("source_type", "provider", "evidence_key")
            )
        )
    return sorted(set(labels))


def _select_campaign(
    workspace: CampaignEvidenceWorkspace,
    campaign_id: str | None,
    visual_by_asset: dict[str, DemoVisualExtraction],
) -> CampaignEvidence:
    if campaign_id:
        for campaign in workspace.campaigns:
            if campaign.campaign_id == campaign_id or campaign.case_id == campaign_id:
                return campaign
        raise AppError("demo_campaign_not_found", "Campaign not found in showcase project", 404)

    return sorted(workspace.campaigns, key=lambda item: _campaign_priority(item, visual_by_asset))[0]


def _campaign_priority(
    campaign: CampaignEvidence,
    visual_by_asset: dict[str, DemoVisualExtraction],
) -> tuple:
    primary = _select_primary_asset(campaign, visual_by_asset)
    visual = _visual_for_asset(primary, visual_by_asset)
    complete = bool(
        primary
        and primary.accepted_for_campaign_set
        and primary.preview_url
        and visual.observations
        and primary.diagnostic.status == "completed"
        and campaign.outcomes
    )
    return (
        0 if complete else 1,
        0 if campaign.is_contrast_case else 1,
        campaign.showcase_rank or 999,
        campaign.case_id,
    )


def _select_primary_asset(
    campaign: CampaignEvidence,
    visual_by_asset: dict[str, DemoVisualExtraction],
) -> CampaignAssetEvidence | None:
    accepted = [item for item in campaign.assets if item.accepted_for_campaign_set]
    candidates = accepted or campaign.assets
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            0 if item.diagnostic.status == "completed" else 1,
            0 if _visual_for_asset(item, visual_by_asset).observations else 1,
            0 if item.preview_url else 1,
            -item.linkage_confidence,
            item.filename or item.title,
        ),
    )[0]


def _visual_for_asset(
    asset: CampaignAssetEvidence | None,
    visual_by_asset: dict[str, DemoVisualExtraction],
) -> DemoVisualExtraction:
    if asset is None or not asset.creative_asset_id:
        return DemoVisualExtraction(
            status="missing",
            limitations=["creative asset is missing; visual evidence is unavailable"],
        )
    return visual_by_asset.get(
        asset.creative_asset_id,
        DemoVisualExtraction(
            status="missing",
            limitations=["canonical visual context is missing; do not infer visual absence"],
        ),
    )


def _campaign_option(
    campaign: CampaignEvidence,
    visual_by_asset: dict[str, DemoVisualExtraction],
) -> DemoCampaignOption:
    primary = _select_primary_asset(campaign, visual_by_asset)
    visual = _visual_for_asset(primary, visual_by_asset)
    accepted = any(item.accepted_for_campaign_set for item in campaign.assets)
    complete = bool(
        primary
        and accepted
        and primary.preview_url
        and visual.observations
        and primary.diagnostic.status == "completed"
        and campaign.outcomes
    )
    status = "ready" if complete else ("limited" if campaign.assets or campaign.outcomes else "blocked")
    reason = "Полная демонстрационная цепочка доступна."
    if not complete:
        gaps = []
        if not accepted:
            gaps.append("нет accepted asset")
        if not primary or not primary.preview_url:
            gaps.append("нет preview")
        if not visual.observations:
            gaps.append("нет visual extraction")
        if not primary or primary.diagnostic.status != "completed":
            gaps.append("нет completed diagnostic")
        if not campaign.outcomes:
            gaps.append("нет CG/TG outcomes")
        reason = "; ".join(gaps) or "Есть ограничения evidence."
    label = campaign.brand or campaign.product or campaign.case_id
    return DemoCampaignOption(
        campaign_id=campaign.campaign_id,
        case_id=campaign.case_id,
        label=label,
        showcase_rank=campaign.showcase_rank,
        status=status,
        reason=reason,
    )


def _report_state(report: ClientReportV2Response | DemoReportState | None) -> DemoReportState | None:
    if report is None:
        return None
    if isinstance(report, DemoReportState):
        return report
    return DemoReportState(
        report_id=report.report_id,
        report_version=report.report_version,
        release_status=report.release_status,
        generated_at=report.generated_at.isoformat(),
        manifest_sha256=report.manifest_sha256,
        artifacts=[
            DemoReportArtifact(
                artifact_type=item.artifact_type,
                filename=item.filename,
                media_type=item.media_type,
                sha256=item.sha256,
                size_bytes=item.size_bytes,
            )
            for item in report.artifacts
        ],
    )
