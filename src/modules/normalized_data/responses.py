"""Response serialization for normalized-domain records."""

from __future__ import annotations

from src.modules.normalized_data.models import (
    NormalizationRun,
    NormalizedFieldValue,
    NormalizedSourceRow,
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
from src.shared.db.repository import json_loads
from src.shared.errors import AppError

def normalization_result(db, run, *, row_limit: int):
    rows = (
        db.query(NormalizedSourceRow)
        .filter(NormalizedSourceRow.normalization_run_id == run.id)
        .order_by(NormalizedSourceRow.source_row_number.asc(), NormalizedSourceRow.id.asc())
        .limit(row_limit)
        .all()
    )
    return NormalizationResultResponse(
        run=run_response(run),
        rows=[row_response(db, row) for row in rows],
    )


def run_response(model):
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


def row_response(db, model):
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
        field_values=[field_value_response(item) for item in field_values],
        created_at=model.created_at,
    )


def field_value_response(model):
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


def campaign_response(model):
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


def creative_response(model):
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


def platform_response(model):
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


def audience_response(model):
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


def placement_response(model):
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


def performance_response(model):
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


def require_run(db, run_id: str):
    run = db.query(NormalizationRun).filter(NormalizationRun.id == run_id).first()
    if run is None:
        raise AppError("normalization_run_not_found", "Normalization run not found", 404)
    return run
