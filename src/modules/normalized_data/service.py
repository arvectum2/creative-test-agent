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
        mapping_by_target: dict[str, list[tuple[ColumnMapping, SourceColumn]]] = defaultdict(list)
        mapped_column_ids: set[str] = set()
        for mapping, column in mappings:
            mapping_by_target[mapping.target_field].append((mapping, column))
            mapped_column_ids.add(column.id)

        warnings: list[dict] = []
        duplicate_targets = sorted(
            target for target, items in mapping_by_target.items() if len(items) > 1
        )
        if duplicate_targets:
            warnings.append(
                _issue(
                    "duplicate_confirmed_targets",
                    "Several confirmed columns map to the same target; the first non-empty value is used per row.",
                    severity="warning",
                    target_fields=duplicate_targets,
                )
            )
        if not data_rows:
            warnings.append(
                _issue(
                    "no_data_rows",
                    "The inspected table contains no materialized data rows.",
                    severity="warning",
                )
            )

        campaign_cache: dict[str, Campaign] = {}
        creative_cache: dict[str, CreativeRecord] = {}
        platform_cache: dict[str, Platform] = {}
        audience_cache: dict[str, AudienceSegment] = {}
        project_assets = (
            db.query(CreativeAsset)
            .filter(CreativeAsset.project_id == inspection.project_id)
            .all()
        )

        status_counts: Counter[str] = Counter()
        for source_row in data_rows:
            values = json_loads(source_row.values_json)
            if not isinstance(values, list):
                values = []
            padded = values + [None] * max(0, len(columns) - len(values))
            source_payload = {
                column.normalized_header: padded[column.position - 1]
                if column.position - 1 < len(padded)
                else None
                for column in columns
            }
            custom_fields = {
                column.normalized_header: source_payload.get(column.normalized_header)
                for column in columns
                if column.id not in mapped_column_ids
            }

            row_issues: list[dict] = []
            selected: dict[str, tuple[ColumnMapping, SourceColumn, Any]] = {}
            for target, target_mappings in mapping_by_target.items():
                non_empty: list[tuple[ColumnMapping, SourceColumn, Any]] = []
                for mapping, column in sorted(target_mappings, key=lambda item: item[1].position):
                    raw = padded[column.position - 1] if column.position - 1 < len(padded) else None
                    if not _is_empty(raw):
                        non_empty.append((mapping, column, raw))
                if non_empty:
                    selected[target] = non_empty[0]
                if len(non_empty) > 1:
                    row_issues.append(
                        _issue(
                            "multiple_values_for_target",
                            "Multiple confirmed columns contain values for one target; the leftmost value was used.",
                            severity="warning",
                            target_field=target,
                            source_column_ids=[item[1].id for item in non_empty],
                        )
                    )

            normalized: dict[str, Any] = {}
            transformations: dict[str, str] = {}
            for target, (_mapping, column, raw) in selected.items():
                value, transformation, issue = _normalize_field(target, raw)
                normalized[target] = value
                transformations[target] = transformation
                if issue is not None:
                    issue["context"].update(
                        {
                            "target_field": target,
                            "source_column_id": column.id,
                            "source_header": column.source_header,
                        }
                    )
                    row_issues.append(issue)

            normalized_row = NormalizedSourceRow(
                normalization_run_id=run.id,
                project_id=inspection.project_id,
                source_file_id=source_file_id,
                source_table_id=table.id,
                source_row_id=source_row.id,
                source_row_number=source_row.source_row_number,
                status=NormalizedRowStatus.normalized,
                issue_count=0,
                issues_json=json_dumps([]),
                source_payload_json=json_dumps(source_payload),
                custom_fields_json=json_dumps(custom_fields),
            )
            db.add(normalized_row)
            db.flush()

            campaign = _campaign_for_row(
                db,
                run,
                source_row,
                normalized,
                campaign_cache,
            )
            creative, creative_issue = _creative_for_row(
                db,
                run,
                normalized,
                creative_cache,
                project_assets,
            )
            if creative_issue is not None:
                row_issues.append(creative_issue)
            platform = _named_dimension_for_row(
                db,
                model=Platform,
                run=run,
                raw_name=normalized.get("platform"),
                cache=platform_cache,
            )
            audience = _named_dimension_for_row(
                db,
                model=AudienceSegment,
                run=run,
                raw_name=normalized.get("audience"),
                cache=audience_cache,
            )

            placement = None
            if any(field in selected for field in _PLACEMENT_FIELDS):
                placement = Placement(
                    normalization_run_id=run.id,
                    project_id=run.project_id,
                    source_row_id=source_row.id,
                    campaign_id=campaign.id if campaign else None,
                    creative_record_id=creative.id if creative else None,
                    platform_id=platform.id if platform else None,
                    audience_segment_id=audience.id if audience else None,
                    placement_type=normalized.get("placement_type"),
                    format=normalized.get("format"),
                    metadata_json=json_dumps({}),
                )
                db.add(placement)
                db.flush()

            performance = None
            if any(field in selected for field in _PERFORMANCE_FIELDS):
                performance = PerformanceObservation(
                    normalization_run_id=run.id,
                    project_id=run.project_id,
                    source_row_id=source_row.id,
                    placement_id=placement.id if placement else None,
                    observation_date=normalized.get("date"),
                    impressions=normalized.get("impressions"),
                    clicks=normalized.get("clicks"),
                    ctr=normalized.get("ctr"),
                    metadata_json=json_dumps({}),
                )
                db.add(performance)
                db.flush()

            normalized_row.campaign_id = campaign.id if campaign else None
            normalized_row.creative_record_id = creative.id if creative else None
            normalized_row.platform_id = platform.id if platform else None
            normalized_row.audience_segment_id = audience.id if audience else None
            normalized_row.placement_id = placement.id if placement else None
            normalized_row.performance_observation_id = performance.id if performance else None

            if not selected:
                row_status = NormalizedRowStatus.skipped
            elif any(item.get("severity") in {"warning", "error"} for item in row_issues):
                row_status = NormalizedRowStatus.partial
            else:
                row_status = NormalizedRowStatus.normalized
            normalized_row.status = row_status
            normalized_row.issue_count = len(row_issues)
            normalized_row.issues_json = json_dumps(row_issues)
            status_counts[row_status] += 1

            entity_by_field = _entity_targets(
                normalized_row=normalized_row,
                campaign=campaign,
                creative=creative,
                platform=platform,
                audience=audience,
                placement=placement,
                performance=performance,
            )
            for target, (mapping, column, raw) in selected.items():
                entity_type, entity_id = entity_by_field[target]
                db.add(
                    NormalizedFieldValue(
                        normalization_run_id=run.id,
                        project_id=run.project_id,
                        normalized_source_row_id=normalized_row.id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        field_name=target,
                        source_file_id=source_file_id,
                        source_table_id=table.id,
                        source_row_id=source_row.id,
                        source_row_number=source_row.source_row_number,
                        source_column_id=column.id,
                        source_column_name=column.source_header or column.normalized_header,
                        column_mapping_id=mapping.id,
                        mapping_profile_id=mapping.mapping_profile_id,
                        normalization_version=NORMALIZER_VERSION,
                        raw_value_json=json_dumps(raw),
                        normalized_value_json=json_dumps(normalized.get(target)),
                        transformation=transformations[target],
                    )
                )

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


def _normalize_field(target: str, raw: Any):
    if target in _TEXT_FIELDS:
        value = str(raw).strip()
        if len(value) > 512:
            return (
                value[:512],
                "trim_and_truncate_text",
                _issue(
                    "normalized_text_truncated",
                    "The normalized text exceeded 512 characters and was truncated; the raw value is preserved in provenance.",
                    severity="warning",
                    original_length=len(value),
                ),
            )
        return value, "trim_text", None
    if target in {"impressions", "clicks"}:
        return _normalize_integer(raw)
    if target == "ctr":
        return _normalize_ctr(raw)
    if target == "date":
        return _normalize_date(raw)
    return raw, "identity", None


def _normalize_integer(raw: Any):
    if isinstance(raw, bool):
        return None, "parse_failed", _parse_issue("integer", raw)
    if isinstance(raw, int):
        return raw, "integer", None
    if isinstance(raw, float) and raw.is_integer():
        return int(raw), "integral_number_to_integer", None
    text = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text), "text_to_integer", None
    match = re.fullmatch(r"([-+]?\d+)[.,](0+)", text)
    if match:
        return int(match.group(1)), "integral_decimal_text_to_integer", None
    return None, "parse_failed", _parse_issue("integer", raw)


def _normalize_ctr(raw: Any):
    if isinstance(raw, bool):
        return None, "parse_failed", _parse_issue("CTR number", raw)
    if isinstance(raw, (int, float)):
        return float(raw), "number", None
    text = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None, "parse_failed", _parse_issue("CTR number", raw)
    if percent:
        return number / 100.0, "percent_text_to_ratio", None
    return number, "text_to_number", None


def _normalize_date(raw: Any):
    if isinstance(raw, datetime):
        return raw.date(), "datetime_to_date", None
    if isinstance(raw, date):
        return raw, "date", None
    text = str(raw).strip()
    for fmt in (
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt).date(), "text_to_date", None
        except ValueError:
            continue
    return None, "parse_failed", _parse_issue("date", raw)


def _parse_issue(expected: str, raw: Any):
    return _issue(
        "value_parse_failed",
        f"The source value could not be normalized as {expected}; the raw value is preserved.",
        severity="warning",
        raw_value=raw,
        expected=expected,
    )


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


def _normalization_result(db, run, *, row_limit: int):
    rows = (
        db.query(NormalizedSourceRow)
        .filter(NormalizedSourceRow.normalization_run_id == run.id)
        .order_by(NormalizedSourceRow.source_row_number.asc(), NormalizedSourceRow.id.asc())
        .limit(row_limit)
        .all()
    )
    return NormalizationResultResponse(
        run=_run_response(run),
        rows=[_row_response(db, row) for row in rows],
    )


def _run_response(model):
    snapshot = json_loads(model.mapping_snapshot_json)
    warnings = json_loads(model.warnings_json)
    return NormalizationRunResponse(
        id=model.id,
        source_table_id=model.source_table_id,
        source_file_id=model.source_file_id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        run_number=model.run_number,
        normalizer_name=model.normalizer_name,
        normalizer_version=model.normalizer_version,
        mapping_fingerprint=model.mapping_fingerprint,
        mapping_snapshot=snapshot if isinstance(snapshot, list) else [],
        status=model.status,
        source_row_count=model.source_row_count,
        normalized_row_count=model.normalized_row_count,
        partial_row_count=model.partial_row_count,
        skipped_row_count=model.skipped_row_count,
        failed_row_count=model.failed_row_count,
        campaign_count=model.campaign_count,
        creative_count=model.creative_count,
        platform_count=model.platform_count,
        audience_segment_count=model.audience_segment_count,
        placement_count=model.placement_count,
        performance_observation_count=model.performance_observation_count,
        warning_count=model.warning_count,
        warnings=warnings if isinstance(warnings, list) else [],
        error_code=model.error_code,
        error_message=model.error_message,
        created_by_user_id=model.created_by_user_id,
        created_at=model.created_at,
    )


def _row_response(db, model):
    issues = json_loads(model.issues_json)
    payload = json_loads(model.source_payload_json)
    custom = json_loads(model.custom_fields_json)
    field_values = (
        db.query(NormalizedFieldValue)
        .filter(NormalizedFieldValue.normalized_source_row_id == model.id)
        .order_by(NormalizedFieldValue.field_name.asc())
        .all()
    )
    return NormalizedSourceRowResponse(
        id=model.id,
        normalization_run_id=model.normalization_run_id,
        project_id=model.project_id,
        source_file_id=model.source_file_id,
        source_table_id=model.source_table_id,
        source_row_id=model.source_row_id,
        source_row_number=model.source_row_number,
        status=model.status,
        issue_count=model.issue_count,
        issues=issues if isinstance(issues, list) else [],
        source_payload=payload if isinstance(payload, dict) else {},
        custom_fields=custom if isinstance(custom, dict) else {},
        campaign_id=model.campaign_id,
        creative_record_id=model.creative_record_id,
        platform_id=model.platform_id,
        audience_segment_id=model.audience_segment_id,
        placement_id=model.placement_id,
        performance_observation_id=model.performance_observation_id,
        field_values=[_field_value_response(item) for item in field_values],
        created_at=model.created_at,
    )


def _field_value_response(model):
    return NormalizedFieldValueResponse(
        id=model.id,
        normalization_run_id=model.normalization_run_id,
        normalized_source_row_id=model.normalized_source_row_id,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        field_name=model.field_name,
        source_file_id=model.source_file_id,
        source_table_id=model.source_table_id,
        source_row_id=model.source_row_id,
        source_row_number=model.source_row_number,
        source_column_id=model.source_column_id,
        source_column_name=model.source_column_name,
        column_mapping_id=model.column_mapping_id,
        mapping_profile_id=model.mapping_profile_id,
        normalization_version=model.normalization_version,
        raw_value=json_loads(model.raw_value_json),
        normalized_value=json_loads(model.normalized_value_json),
        transformation=model.transformation,
        created_at=model.created_at,
    )


def _campaign_response(model):
    metadata = json_loads(model.metadata_json)
    return CampaignResponse(
        id=model.id,
        normalization_run_id=model.normalization_run_id,
        project_id=model.project_id,
        reference_key=model.reference_key,
        brand=model.brand,
        product=model.product,
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=model.created_at,
    )


def _creative_response(model):
    metadata = json_loads(model.metadata_json)
    return CreativeRecordResponse(
        id=model.id,
        normalization_run_id=model.normalization_run_id,
        project_id=model.project_id,
        reference_key=model.reference_key,
        display_reference=model.display_reference,
        creative_asset_id=model.creative_asset_id,
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=model.created_at,
    )


def _platform_response(model):
    metadata = json_loads(model.metadata_json)
    return PlatformResponse(
        id=model.id,
        normalization_run_id=model.normalization_run_id,
        project_id=model.project_id,
        canonical_key=model.canonical_key,
        name=model.name,
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=model.created_at,
    )


def _audience_response(model):
    metadata = json_loads(model.metadata_json)
    return AudienceSegmentResponse(
        id=model.id,
        normalization_run_id=model.normalization_run_id,
        project_id=model.project_id,
        canonical_key=model.canonical_key,
        name=model.name,
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=model.created_at,
    )


def _placement_response(model):
    metadata = json_loads(model.metadata_json)
    return PlacementResponse(
        id=model.id,
        normalization_run_id=model.normalization_run_id,
        project_id=model.project_id,
        source_row_id=model.source_row_id,
        campaign_id=model.campaign_id,
        creative_record_id=model.creative_record_id,
        platform_id=model.platform_id,
        audience_segment_id=model.audience_segment_id,
        placement_type=model.placement_type,
        format=model.format,
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=model.created_at,
    )


def _performance_response(model):
    metadata = json_loads(model.metadata_json)
    return PerformanceObservationResponse(
        id=model.id,
        normalization_run_id=model.normalization_run_id,
        project_id=model.project_id,
        source_row_id=model.source_row_id,
        placement_id=model.placement_id,
        observation_date=model.observation_date,
        impressions=model.impressions,
        clicks=model.clicks,
        ctr=model.ctr,
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=model.created_at,
    )


def _require_run(db, run_id: str):
    run = db.query(NormalizationRun).filter(NormalizationRun.id == run_id).first()
    if run is None:
        raise AppError("normalization_run_not_found", "Normalization run not found", 404)
    return run


def _canonical_key(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().casefold())


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _issue(code: str, message: str, *, severity: str, **context: Any) -> dict:
    return {"code": code, "message": message, "severity": severity, "context": context}
