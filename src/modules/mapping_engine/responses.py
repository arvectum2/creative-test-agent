"""Response assembly for the deterministic mapping engine."""

from __future__ import annotations

from collections import Counter

from src.modules.import_sessions.models import SourceColumn, SourceTable
from src.modules.mapping_engine.models import (
    ColumnMapping,
    ColumnMappingStatus,
    MappingProfileRule,
    MappingRun,
    MappingSuggestion,
)
from src.modules.mapping_engine.schemas import (
    ColumnMappingResponse,
    MappingProfileResponse,
    MappingProfileRuleResponse,
    MappingRunResponse,
    MappingSuggestionResponse,
    TableMappingResponse,
)
from src.shared.db.repository import json_loads

def build_table_mapping(db, table: SourceTable, run: MappingRun | None):
    columns = (
        db.query(SourceColumn)
        .filter(SourceColumn.source_table_id == table.id)
        .order_by(SourceColumn.position.asc())
        .all()
    )
    mappings = {
        item.source_column_id: item
        for item in db.query(ColumnMapping)
        .filter(ColumnMapping.source_table_id == table.id)
        .all()
    }
    column_responses = [
        column_mapping_response(db, column, mappings.get(column.id), run)
        for column in columns
        if mappings.get(column.id) is not None
    ]
    counts = Counter(item.status for item in mappings.values())
    run_warnings = json_loads(run.warnings_json) if run else []
    if not isinstance(run_warnings, list):
        run_warnings = []
    return TableMappingResponse(
        run=run_response(run) if run else None,
        source_table_id=table.id,
        mapped_columns=len(mappings),
        confirmed_columns=counts[ColumnMappingStatus.confirmed],
        suggested_columns=counts[ColumnMappingStatus.suggested],
        rejected_columns=counts[ColumnMappingStatus.rejected],
        unmapped_columns=counts[ColumnMappingStatus.unmapped],
        warnings=run_warnings,
        columns=column_responses,
    )


def column_mapping_response(db, column, mapping, run):
    suggestions: list[MappingSuggestion] = []
    if run is not None:
        suggestions = (
            db.query(MappingSuggestion)
            .filter(
                MappingSuggestion.mapping_run_id == run.id,
                MappingSuggestion.source_column_id == column.id,
            )
            .order_by(MappingSuggestion.rank.asc())
            .all()
        )
    samples = json_loads(column.sample_values_json)
    if not isinstance(samples, list):
        samples = []
    return ColumnMappingResponse(
        id=mapping.id,
        source_table_id=mapping.source_table_id,
        source_column_id=mapping.source_column_id,
        position=column.position,
        source_header=column.source_header,
        normalized_header=column.normalized_header,
        inferred_type=column.inferred_type,
        is_empty=column.is_empty,
        sample_values=samples,
        target_field=mapping.target_field,
        status=mapping.status,
        confidence=mapping.confidence,
        decision_source=mapping.decision_source,
        selected_suggestion_id=mapping.selected_suggestion_id,
        mapping_profile_id=mapping.mapping_profile_id,
        rationale=json_loads(mapping.rationale_json),
        decided_by_user_id=mapping.decided_by_user_id,
        suggestions=[suggestion_response(item) for item in suggestions],
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


def suggestion_response(model):
    return MappingSuggestionResponse(
        id=model.id,
        mapping_run_id=model.mapping_run_id,
        source_column_id=model.source_column_id,
        target_field=model.target_field,
        rank=model.rank,
        confidence=model.confidence,
        method=model.method,
        explanation=json_loads(model.explanation_json),
        created_at=model.created_at,
    )


def run_response(model):
    warnings = json_loads(model.warnings_json)
    if not isinstance(warnings, list):
        warnings = []
    return MappingRunResponse(
        id=model.id,
        source_table_id=model.source_table_id,
        source_file_id=model.source_file_id,
        import_session_id=model.import_session_id,
        project_id=model.project_id,
        run_number=model.run_number,
        engine_name=model.engine_name,
        engine_version=model.engine_version,
        mapping_profile_id=model.mapping_profile_id,
        status=model.status,
        suggestion_count=model.suggestion_count,
        warnings=warnings,
        error_code=model.error_code,
        error_message=model.error_message,
        created_by_user_id=model.created_by_user_id,
        created_at=model.created_at,
    )


def profile_response(db, profile):
    rules = (
        db.query(MappingProfileRule)
        .filter(MappingProfileRule.mapping_profile_id == profile.id)
        .order_by(MappingProfileRule.source_key.asc())
        .all()
    )
    return MappingProfileResponse(
        id=profile.id,
        project_id=profile.project_id,
        name=profile.name,
        description=profile.description,
        source_label=profile.source_label,
        file_format=profile.file_format,
        sheet_name_pattern=profile.sheet_name_pattern,
        version=profile.version,
        status=profile.status,
        created_from_table_id=profile.created_from_table_id,
        created_by_user_id=profile.created_by_user_id,
        rules=[
            MappingProfileRuleResponse(
                id=rule.id,
                mapping_profile_id=rule.mapping_profile_id,
                source_key=rule.source_key,
                source_header=rule.source_header,
                source_inferred_type=rule.source_inferred_type,
                target_field=rule.target_field,
                confidence=rule.confidence,
                created_from_column_id=rule.created_from_column_id,
                is_active=rule.is_active,
                created_at=rule.created_at,
            )
            for rule in rules
        ],
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )
