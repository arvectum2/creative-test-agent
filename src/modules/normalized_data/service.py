from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func

from src.modules.creative_assets.models import CreativeAsset
from src.modules.import_sessions.models import SourceColumn, SourceInspection, SourceRow, SourceTable
from src.modules.mapping_engine.models import ColumnMapping, ColumnMappingStatus
from src.modules.normalized_data.models import (
    AudienceSegment,
    Campaign,
    CreativeRecord,
    NormalizationRun,
    NormalizationRunStatus,
    NormalizedFieldValue,
    NormalizedRowStatus,
    NormalizedSourceRow,
    PerformanceObservation,
    Placement,
    Platform,
)
from src.modules.normalized_data.schemas import (
    AudienceSegmentResponse,
    CampaignResponse,
    CreativeRecordResponse,
    NormalizationResultResponse,
    NormalizationRunResponse,
    NormalizedFieldValueResponse,
    NormalizedSourceRowResponse,
    PerformanceObservationResponse,
    PlacementResponse,
    PlatformResponse,
)
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError
from src.modules.normalized_data.normalizers import (
    issue as _issue,
    normalize_field as _normalize_field,
)
from src.modules.normalized_data.row_normalizer import normalize_rows
from src.modules.normalized_data.responses import (
    normalization_result as _normalization_result,
    require_run as _require_run,
    row_response as _row_response,
    run_response as _run_response,
    campaign_response as _campaign_response,
    creative_response as _creative_response,
    platform_response as _platform_response,
    audience_response as _audience_response,
    placement_response as _placement_response,
    performance_response as _performance_response,
)

NORMALIZER_NAME = "deterministic-domain-normalizer"
NORMALIZER_VERSION = "1.0.0"

_TEXT_FIELDS = {
    "campaign_reference",
    "creative_reference",
    "platform",
    "placement_type",
    "format",
    "audience",
    "brand",
    "product",
}
_PERFORMANCE_FIELDS = {"date", "impressions", "clicks", "ctr"}
_PLACEMENT_FIELDS = {
    "campaign_reference",
    "creative_reference",
    "platform",
    "placement_type",
    "format",
    "audience",
    "date",
    "impressions",
    "clicks",
    "ctr",
}


def normalize_source_table(
    import_session_id: str,
    source_file_id: str,
    source_table_id: str,
    *,
    force: bool = False,
    created_by_user_id: str | None = None,
) -> NormalizationResultResponse:
    with db_session() as db:
        table, inspection = _load_table_context(
            db, import_session_id, source_file_id, source_table_id
        )
        mappings = _confirmed_mappings(db, table.id)
        if not mappings:
            raise AppError(
                "normalization_requires_confirmed_mapping",
                "Confirm at least one source-column mapping before normalization",
                409,
            )

        snapshot = [_mapping_snapshot_item(mapping, column) for mapping, column in mappings]
        fingerprint = hashlib.sha256(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()

        latest = (
            db.query(NormalizationRun)
            .filter(
                NormalizationRun.source_table_id == table.id,
                NormalizationRun.normalizer_version == NORMALIZER_VERSION,
                NormalizationRun.mapping_fingerprint == fingerprint,
                NormalizationRun.status == NormalizationRunStatus.completed,
            )
            .order_by(NormalizationRun.run_number.desc(), NormalizationRun.created_at.desc())
            .first()
        )
        if latest is not None and not force:
            return _normalization_result(db, latest, row_limit=20)

        run_number = (
            db.query(func.max(NormalizationRun.run_number))
            .filter(NormalizationRun.source_table_id == table.id)
            .scalar()
            or 0
        ) + 1
        run = NormalizationRun(
            source_table_id=table.id,
            source_file_id=source_file_id,
            import_session_id=import_session_id,
            project_id=inspection.project_id,
            run_number=run_number,
            normalizer_name=NORMALIZER_NAME,
            normalizer_version=NORMALIZER_VERSION,
            mapping_fingerprint=fingerprint,
            mapping_snapshot_json=json_dumps(snapshot),
            status=NormalizationRunStatus.completed,
            warnings_json=json_dumps([]),
            created_by_user_id=created_by_user_id,
        )
        db.add(run)
        db.flush()

        columns = (
            db.query(SourceColumn)
            .filter(SourceColumn.source_table_id == table.id)
            .order_by(SourceColumn.position.asc())
            .all()
        )
        data_rows = (
            db.query(SourceRow)
            .filter(SourceRow.source_table_id == table.id, SourceRow.row_kind == "data")
            .order_by(SourceRow.source_row_number.asc(), SourceRow.id.asc())
            .all()
        )
        row_state = normalize_rows(
            db=db,
            run=run,
            inspection=inspection,
            table=table,
            mappings=mappings,
            columns=columns,
            data_rows=data_rows,
            source_file_id=source_file_id,
        )
        status_counts = row_state["status_counts"]
        campaign_cache = row_state["campaign_cache"]
        creative_cache = row_state["creative_cache"]
        platform_cache = row_state["platform_cache"]
        audience_cache = row_state["audience_cache"]
        warnings = row_state["warnings"]
        run.source_row_count = len(data_rows)
        run.normalized_row_count = status_counts[NormalizedRowStatus.normalized]
        run.partial_row_count = status_counts[NormalizedRowStatus.partial]
        run.skipped_row_count = status_counts[NormalizedRowStatus.skipped]
        run.failed_row_count = status_counts[NormalizedRowStatus.failed]
        run.campaign_count = len(campaign_cache)
        run.creative_count = len(creative_cache)
        run.platform_count = len(platform_cache)
        run.audience_segment_count = len(audience_cache)
        run.placement_count = (
            db.query(Placement).filter(Placement.normalization_run_id == run.id).count()
        )
        run.performance_observation_count = (
            db.query(PerformanceObservation)
            .filter(PerformanceObservation.normalization_run_id == run.id)
            .count()
        )
        run.warning_count = len(warnings) + sum(
            1
            for row in db.query(NormalizedSourceRow)
            .filter(NormalizedSourceRow.normalization_run_id == run.id)
            .all()
            for issue in (json_loads(row.issues_json) if isinstance(json_loads(row.issues_json), list) else [])
            if issue.get("severity") in {"warning", "error"}
        )
        run.warnings_json = json_dumps(warnings)
        db.flush()
        db.refresh(run)
        return _normalization_result(db, run, row_limit=20)


def get_latest_normalization(
    import_session_id: str,
    source_file_id: str,
    source_table_id: str,
) -> NormalizationResultResponse | None:
    with db_session() as db:
        table, _inspection = _load_table_context(
            db, import_session_id, source_file_id, source_table_id
        )
        run = (
            db.query(NormalizationRun)
            .filter(NormalizationRun.source_table_id == table.id)
            .order_by(NormalizationRun.run_number.desc(), NormalizationRun.created_at.desc())
            .first()
        )
        return _normalization_result(db, run, row_limit=20) if run else None


def get_normalization_run(run_id: str) -> NormalizationRunResponse | None:
    with db_session() as db:
        run = db.query(NormalizationRun).filter(NormalizationRun.id == run_id).first()
        return _run_response(run) if run else None


def list_normalized_rows(
    run_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
) -> tuple[int, list[NormalizedSourceRowResponse]]:
    with db_session() as db:
        _require_run(db, run_id)
        query = db.query(NormalizedSourceRow).filter(
            NormalizedSourceRow.normalization_run_id == run_id
        )
        total = query.count()
        rows = (
            query.order_by(NormalizedSourceRow.source_row_number.asc(), NormalizedSourceRow.id.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return total, [_row_response(db, row) for row in rows]


def list_campaigns(run_id: str) -> list[CampaignResponse]:
    with db_session() as db:
        _require_run(db, run_id)
        models = (
            db.query(Campaign)
            .filter(Campaign.normalization_run_id == run_id)
            .order_by(Campaign.reference_key.asc(), Campaign.id.asc())
            .all()
        )
        return [_campaign_response(model) for model in models]


def list_creatives(run_id: str) -> list[CreativeRecordResponse]:
    with db_session() as db:
        _require_run(db, run_id)
        models = (
            db.query(CreativeRecord)
            .filter(CreativeRecord.normalization_run_id == run_id)
            .order_by(CreativeRecord.reference_key.asc(), CreativeRecord.id.asc())
            .all()
        )
        return [_creative_response(model) for model in models]


def list_platforms(run_id: str) -> list[PlatformResponse]:
    with db_session() as db:
        _require_run(db, run_id)
        models = (
            db.query(Platform)
            .filter(Platform.normalization_run_id == run_id)
            .order_by(Platform.canonical_key.asc(), Platform.id.asc())
            .all()
        )
        return [_platform_response(model) for model in models]


def list_audience_segments(run_id: str) -> list[AudienceSegmentResponse]:
    with db_session() as db:
        _require_run(db, run_id)
        models = (
            db.query(AudienceSegment)
            .filter(AudienceSegment.normalization_run_id == run_id)
            .order_by(AudienceSegment.canonical_key.asc(), AudienceSegment.id.asc())
            .all()
        )
        return [_audience_response(model) for model in models]


def list_placements(run_id: str) -> list[PlacementResponse]:
    with db_session() as db:
        _require_run(db, run_id)
        models = (
            db.query(Placement)
            .filter(Placement.normalization_run_id == run_id)
            .order_by(Placement.created_at.asc(), Placement.id.asc())
            .all()
        )
        return [_placement_response(model) for model in models]


def list_performance_observations(run_id: str) -> list[PerformanceObservationResponse]:
    with db_session() as db:
        _require_run(db, run_id)
        models = (
            db.query(PerformanceObservation)
            .filter(PerformanceObservation.normalization_run_id == run_id)
            .order_by(
                PerformanceObservation.observation_date.asc(),
                PerformanceObservation.created_at.asc(),
                PerformanceObservation.id.asc(),
            )
            .all()
        )
        return [_performance_response(model) for model in models]


def _load_table_context(db, import_session_id: str, source_file_id: str, source_table_id: str):
    table = (
        db.query(SourceTable)
        .filter(SourceTable.id == source_table_id, SourceTable.source_file_id == source_file_id)
        .first()
    )
    if table is None:
        raise AppError("source_table_not_found", "Source table not found", 404)
    inspection = (
        db.query(SourceInspection)
        .filter(
            SourceInspection.id == table.inspection_id,
            SourceInspection.source_file_id == source_file_id,
            SourceInspection.import_session_id == import_session_id,
            SourceInspection.status == "completed",
        )
        .first()
    )
    if inspection is None:
        raise AppError(
            "source_table_context_mismatch",
            "Source table does not belong to the requested completed inspection",
            404,
        )
    return table, inspection


def _confirmed_mappings(db, source_table_id: str):
    return (
        db.query(ColumnMapping, SourceColumn)
        .join(SourceColumn, SourceColumn.id == ColumnMapping.source_column_id)
        .filter(
            ColumnMapping.source_table_id == source_table_id,
            ColumnMapping.status == ColumnMappingStatus.confirmed,
            ColumnMapping.target_field.is_not(None),
            SourceColumn.source_table_id == source_table_id,
        )
        .order_by(SourceColumn.position.asc(), ColumnMapping.id.asc())
        .all()
    )


def _mapping_snapshot_item(mapping: ColumnMapping, column: SourceColumn) -> dict:
    return {
        "column_mapping_id": mapping.id,
        "source_column_id": column.id,
        "position": column.position,
        "source_header": column.source_header,
        "normalized_header": column.normalized_header,
        "inferred_type": column.inferred_type,
        "target_field": mapping.target_field,
        "mapping_profile_id": mapping.mapping_profile_id,
        "decision_source": mapping.decision_source,
    }


def _campaign_for_row(db, run, source_row, normalized, cache):
    reference = normalized.get("campaign_reference")
    brand = normalized.get("brand")
    product = normalized.get("product")
    if not any((reference, brand, product)):
        return None
    cache_key = _canonical_key(reference) if reference else f"row:{source_row.id}"
    model = cache.get(cache_key)
    if model is None:
        model = Campaign(
            normalization_run_id=run.id,
            project_id=run.project_id,
            reference_key=reference or cache_key,
            brand=brand,
            product=product,
            metadata_json=json_dumps({}),
        )
        db.add(model)
        db.flush()
        cache[cache_key] = model
    else:
        if model.brand is None and brand:
            model.brand = brand
        if model.product is None and product:
            model.product = product
    return model


def _creative_for_row(db, run, normalized, cache, project_assets):
    reference = normalized.get("creative_reference")
    if not reference:
        return None, None
    key = _canonical_key(reference)
    model = cache.get(key)
    if model is not None:
        return model, None

    matches = []
    reference_names = {key, _canonical_key(Path(reference).name)}
    for asset in project_assets:
        candidates = {
            _canonical_key(asset.id),
            _canonical_key(asset.title),
            _canonical_key(asset.original_filename),
            _canonical_key(Path(asset.original_filename).name) if asset.original_filename else "",
        }
        if reference_names & candidates:
            matches.append(asset)
    unique_matches = {asset.id: asset for asset in matches}
    linked_asset_id = next(iter(unique_matches)) if len(unique_matches) == 1 else None
    issue = None
    if len(unique_matches) > 1:
        issue = _issue(
            "creative_reference_ambiguous",
            "The creative reference matches several existing creative assets; no link was selected.",
            severity="warning",
            creative_reference=reference,
            creative_asset_ids=sorted(unique_matches),
        )
    elif not unique_matches:
        issue = _issue(
            "creative_asset_not_linked",
            "No existing creative asset matched the source reference; the normalized record remains usable.",
            severity="info",
            creative_reference=reference,
        )

    model = CreativeRecord(
        normalization_run_id=run.id,
        project_id=run.project_id,
        reference_key=key,
        display_reference=reference,
        creative_asset_id=linked_asset_id,
        metadata_json=json_dumps({}),
    )
    db.add(model)
    db.flush()
    cache[key] = model
    return model, issue


def _named_dimension_for_row(db, *, model, run, raw_name, cache):
    if not raw_name:
        return None
    key = _canonical_key(raw_name)
    existing = cache.get(key)
    if existing is not None:
        return existing
    existing = model(
        normalization_run_id=run.id,
        project_id=run.project_id,
        canonical_key=key,
        name=raw_name,
        metadata_json=json_dumps({}),
    )
    db.add(existing)
    db.flush()
    cache[key] = existing
    return existing


def _entity_targets(*, normalized_row, campaign, creative, platform, audience, placement, performance):
    fallback = ("normalized_source_row", normalized_row.id)
    return {
        "campaign_reference": ("campaign", campaign.id) if campaign else fallback,
        "brand": ("campaign", campaign.id) if campaign else fallback,
        "product": ("campaign", campaign.id) if campaign else fallback,
        "creative_reference": ("creative_record", creative.id) if creative else fallback,
        "platform": ("platform", platform.id) if platform else fallback,
        "audience": ("audience_segment", audience.id) if audience else fallback,
        "placement_type": ("placement", placement.id) if placement else fallback,
        "format": ("placement", placement.id) if placement else fallback,
        "date": ("performance_observation", performance.id) if performance else fallback,
        "impressions": ("performance_observation", performance.id) if performance else fallback,
        "clicks": ("performance_observation", performance.id) if performance else fallback,
        "ctr": ("performance_observation", performance.id) if performance else fallback,
    }


def _canonical_key(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
