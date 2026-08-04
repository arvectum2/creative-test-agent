"""Per-row deterministic normalization and provenance persistence."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from src.modules.creative_assets.models import CreativeAsset
from src.modules.mapping_engine.models import ColumnMapping
from src.modules.normalized_data.models import (
    AudienceSegment,
    Campaign,
    CreativeRecord,
    NormalizedFieldValue,
    NormalizedRowStatus,
    NormalizedSourceRow,
    PerformanceObservation,
    Placement,
    Platform,
)
from src.modules.normalized_data.normalizers import issue as _issue, normalize_field as _normalize_field
from src.shared.db.repository import json_dumps, json_loads


def normalize_rows(
    *,
    db,
    run,
    inspection,
    table,
    mappings,
    columns,
    data_rows,
    source_file_id: str,
) -> dict[str, Any]:
    from src.modules.normalized_data.service import (
        NORMALIZER_VERSION,
        _PERFORMANCE_FIELDS,
        _PLACEMENT_FIELDS,
        _campaign_for_row,
        _creative_for_row,
        _entity_targets,
        _is_empty,
        _named_dimension_for_row,
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

    return {
        "status_counts": status_counts,
        "campaign_cache": campaign_cache,
        "creative_cache": creative_cache,
        "platform_cache": platform_cache,
        "audience_cache": audience_cache,
        "warnings": warnings,
    }
