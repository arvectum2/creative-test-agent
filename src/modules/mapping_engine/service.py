from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from fnmatch import fnmatchcase

from sqlalchemy import func

from src.modules.import_sessions.models import SourceColumn, SourceInspection, SourceTable
from src.modules.mapping_engine.catalog import (
    AUTO_SUGGEST_CONFIDENCE,
    ENGINE_NAME,
    ENGINE_VERSION,
    TARGET_FIELD_BY_KEY,
    public_catalog,
    score_column,
)
from src.modules.mapping_engine.models import (
    ColumnMapping,
    ColumnMappingStatus,
    MappingProfile,
    MappingProfileRule,
    MappingProfileStatus,
    MappingRun,
    MappingRunStatus,
    MappingSuggestion,
)
from src.modules.mapping_engine.schemas import (
    ColumnMappingDecisionRequest,
    ColumnMappingResponse,
    CreateMappingProfileRequest,
    MappingFieldResponse,
    MappingProfileResponse,
    MappingProfileRuleResponse,
    MappingRunResponse,
    MappingSuggestionResponse,
    TableMappingResponse,
)
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.errors import AppError
from src.modules.mapping_engine.responses import (
    build_table_mapping as _build_table_mapping,
    column_mapping_response as _column_mapping_response,
    profile_response as _profile_response,
)


def list_mapping_fields() -> list[MappingFieldResponse]:
    return [MappingFieldResponse(**item) for item in public_catalog()]


def generate_mapping_suggestions(
    import_session_id: str,
    source_file_id: str,
    source_table_id: str,
    *,
    mapping_profile_id: str | None = None,
    force: bool = False,
    created_by_user_id: str | None = None,
) -> TableMappingResponse:
    with db_session() as db:
        table, inspection = _load_table_context(
            db, import_session_id, source_file_id, source_table_id
        )
        profile, profile_targets, profile_warnings = _load_profile_targets(
            db, mapping_profile_id, inspection.project_id, inspection.file_format, table.sheet_name
        )

        latest = _latest_mapping_run(db, source_table_id, mapping_profile_id)
        if latest is not None and not force and latest.engine_version == ENGINE_VERSION:
            return _build_table_mapping(db, table, latest)

        run_number = (
            db.query(func.max(MappingRun.run_number))
            .filter(MappingRun.source_table_id == source_table_id)
            .scalar()
            or 0
        ) + 1
        run = MappingRun(
            source_table_id=table.id,
            source_file_id=source_file_id,
            import_session_id=import_session_id,
            project_id=inspection.project_id,
            run_number=run_number,
            engine_name=ENGINE_NAME,
            engine_version=ENGINE_VERSION,
            mapping_profile_id=profile.id if profile else None,
            status=MappingRunStatus.completed,
            suggestion_count=0,
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
        warnings: list[dict] = list(profile_warnings)
        top_targets: list[str] = []
        suggestion_count = 0

        for column in columns:
            samples = json_loads(column.sample_values_json)
            if not isinstance(samples, list):
                samples = []
            candidates = score_column(
                source_header=column.source_header,
                normalized_header=column.normalized_header,
                inferred_type=column.inferred_type,
                sample_values=samples,
                profile_targets=profile_targets,
            )

            saved_suggestions: list[MappingSuggestion] = []
            for rank, candidate in enumerate(candidates, start=1):
                suggestion = MappingSuggestion(
                    mapping_run_id=run.id,
                    source_table_id=table.id,
                    source_column_id=column.id,
                    target_field=candidate.target_field,
                    rank=rank,
                    confidence=candidate.confidence,
                    method=candidate.method,
                    explanation_json=json_dumps(candidate.explanation),
                )
                db.add(suggestion)
                saved_suggestions.append(suggestion)
                suggestion_count += 1
            db.flush()

            top = saved_suggestions[0] if saved_suggestions else None
            if top is not None:
                top_targets.append(top.target_field)
            _upsert_engine_mapping(
                db,
                table=table,
                column=column,
                top=top,
                profile=profile,
            )

            if not saved_suggestions and not column.is_empty:
                warnings.append(
                    {
                        "code": "no_mapping_candidate",
                        "message": "No sufficiently supported target field was found for a source column.",
                        "context": {
                            "source_column_id": column.id,
                            "normalized_header": column.normalized_header,
                        },
                    }
                )

        duplicates = sorted(
            target for target, count in Counter(top_targets).items() if count > 1
        )
        if duplicates:
            warnings.append(
                {
                    "code": "duplicate_target_suggestions",
                    "message": "Several source columns have the same leading target-field suggestion.",
                    "context": {"target_fields": duplicates},
                }
            )

        run.suggestion_count = suggestion_count
        run.warnings_json = json_dumps(warnings)
        db.flush()
        db.refresh(run)
        return _build_table_mapping(db, table, run)


def get_table_mapping(
    import_session_id: str,
    source_file_id: str,
    source_table_id: str,
) -> TableMappingResponse:
    with db_session() as db:
        table, _inspection = _load_table_context(
            db, import_session_id, source_file_id, source_table_id
        )
        latest = (
            db.query(MappingRun)
            .filter(MappingRun.source_table_id == source_table_id)
            .order_by(MappingRun.run_number.desc(), MappingRun.created_at.desc())
            .first()
        )
        return _build_table_mapping(db, table, latest)


def decide_column_mapping(
    import_session_id: str,
    source_file_id: str,
    source_table_id: str,
    source_column_id: str,
    req: ColumnMappingDecisionRequest,
    *,
    decided_by_user_id: str | None = None,
) -> ColumnMappingResponse:
    with db_session() as db:
        table, _inspection = _load_table_context(
            db, import_session_id, source_file_id, source_table_id
        )
        column = (
            db.query(SourceColumn)
            .filter(
                SourceColumn.id == source_column_id,
                SourceColumn.source_table_id == table.id,
            )
            .first()
        )
        if column is None:
            raise AppError("source_column_not_found", "Source column not found", 404)

        selected_suggestion = None
        target_field = req.target_field
        if req.selected_suggestion_id:
            selected_suggestion = (
                db.query(MappingSuggestion)
                .filter(
                    MappingSuggestion.id == req.selected_suggestion_id,
                    MappingSuggestion.source_column_id == column.id,
                )
                .first()
            )
            if selected_suggestion is None:
                raise AppError(
                    "mapping_suggestion_not_found",
                    "The selected mapping suggestion does not belong to this source column",
                    404,
                )
            if target_field and target_field != selected_suggestion.target_field:
                raise AppError(
                    "mapping_target_mismatch",
                    "target_field does not match the selected suggestion",
                    409,
                )
            target_field = selected_suggestion.target_field

        if req.status == ColumnMappingStatus.confirmed:
            if not target_field:
                raise AppError(
                    "mapping_target_required",
                    "A confirmed mapping requires target_field or selected_suggestion_id",
                    400,
                )
            _validate_target_field(target_field)
            if not req.allow_duplicate:
                conflict = (
                    db.query(ColumnMapping)
                    .filter(
                        ColumnMapping.source_table_id == table.id,
                        ColumnMapping.source_column_id != column.id,
                        ColumnMapping.status == ColumnMappingStatus.confirmed,
                        ColumnMapping.target_field == target_field,
                    )
                    .first()
                )
                if conflict is not None:
                    raise AppError(
                        "mapping_target_already_confirmed",
                        "Another source column is already confirmed for this target field",
                        409,
                    )
        else:
            target_field = None
            selected_suggestion = None

        mapping = (
            db.query(ColumnMapping)
            .filter(ColumnMapping.source_column_id == column.id)
            .first()
        )
        if mapping is None:
            mapping = ColumnMapping(
                source_table_id=table.id,
                source_column_id=column.id,
            )
            db.add(mapping)

        mapping.target_field = target_field
        mapping.status = req.status
        mapping.confidence = selected_suggestion.confidence if selected_suggestion else None
        mapping.decision_source = "analyst"
        mapping.selected_suggestion_id = selected_suggestion.id if selected_suggestion else None
        mapping.mapping_profile_id = None
        mapping.rationale_json = json_dumps(req.rationale)
        mapping.decided_by_user_id = decided_by_user_id
        mapping.updated_at = datetime.now(timezone.utc)
        db.flush()
        db.refresh(mapping)

        latest = (
            db.query(MappingRun)
            .filter(MappingRun.source_table_id == table.id)
            .order_by(MappingRun.run_number.desc(), MappingRun.created_at.desc())
            .first()
        )
        return _column_mapping_response(db, column, mapping, latest)


def create_mapping_profile(
    req: CreateMappingProfileRequest,
    *,
    created_by_user_id: str | None = None,
) -> MappingProfileResponse:
    with db_session() as db:
        table = db.query(SourceTable).filter(SourceTable.id == req.source_table_id).first()
        if table is None:
            raise AppError("source_table_not_found", "Source table not found", 404)
        inspection = (
            db.query(SourceInspection)
            .filter(SourceInspection.id == table.inspection_id)
            .first()
        )
        if inspection is None or inspection.project_id != req.project_id:
            raise AppError(
                "mapping_profile_project_mismatch",
                "The source table does not belong to the requested project",
                409,
            )

        clean_name = req.name.strip()
        if not clean_name:
            raise AppError("mapping_profile_name_required", "Profile name is required", 400)

        confirmed = (
            db.query(ColumnMapping, SourceColumn)
            .join(SourceColumn, SourceColumn.id == ColumnMapping.source_column_id)
            .filter(
                ColumnMapping.source_table_id == table.id,
                ColumnMapping.status == ColumnMappingStatus.confirmed,
                ColumnMapping.target_field.is_not(None),
            )
            .order_by(SourceColumn.position.asc())
            .all()
        )
        if not confirmed:
            raise AppError(
                "mapping_profile_has_no_confirmed_rules",
                "Confirm at least one column mapping before creating a profile",
                409,
            )

        version = (
            db.query(func.max(MappingProfile.version))
            .filter(
                MappingProfile.project_id == req.project_id,
                MappingProfile.name == clean_name,
            )
            .scalar()
            or 0
        ) + 1
        profile = MappingProfile(
            project_id=req.project_id,
            name=clean_name,
            description=req.description,
            source_label=req.source_label,
            file_format=inspection.file_format,
            sheet_name_pattern=req.sheet_name_pattern or table.sheet_name,
            version=version,
            status=MappingProfileStatus.active,
            created_from_table_id=table.id,
            created_by_user_id=created_by_user_id,
        )
        db.add(profile)
        db.flush()

        for mapping, column in confirmed:
            db.add(
                MappingProfileRule(
                    mapping_profile_id=profile.id,
                    source_key=column.normalized_header.strip().lower(),
                    source_header=column.source_header,
                    source_inferred_type=column.inferred_type,
                    target_field=mapping.target_field,
                    confidence=mapping.confidence or 1.0,
                    created_from_column_id=column.id,
                    is_active=True,
                )
            )
        db.flush()
        db.refresh(profile)
        return _profile_response(db, profile)


def list_mapping_profiles(
    project_id: str,
    status: str | None = None,
) -> list[MappingProfileResponse]:
    with db_session() as db:
        query = db.query(MappingProfile).filter(MappingProfile.project_id == project_id)
        if status:
            query = query.filter(MappingProfile.status == status)
        profiles = query.order_by(
            MappingProfile.name.asc(), MappingProfile.version.desc()
        ).all()
        return [_profile_response(db, profile) for profile in profiles]


def get_mapping_profile(profile_id: str) -> MappingProfileResponse | None:
    with db_session() as db:
        profile = db.query(MappingProfile).filter(MappingProfile.id == profile_id).first()
        return _profile_response(db, profile) if profile else None


def _load_table_context(db, import_session_id: str, source_file_id: str, source_table_id: str):
    table = (
        db.query(SourceTable)
        .filter(
            SourceTable.id == source_table_id,
            SourceTable.source_file_id == source_file_id,
        )
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


def _load_profile_targets(
    db,
    profile_id: str | None,
    project_id: str,
    file_format: str | None,
    sheet_name: str,
):
    if not profile_id:
        return None, {}, []
    profile = (
        db.query(MappingProfile)
        .filter(
            MappingProfile.id == profile_id,
            MappingProfile.status == MappingProfileStatus.active,
        )
        .first()
    )
    if profile is None:
        raise AppError("mapping_profile_not_found", "Mapping profile not found", 404)
    if profile.project_id != project_id:
        raise AppError(
            "mapping_profile_project_mismatch",
            "Mapping profiles can only be applied inside their project",
            409,
        )
    warnings: list[dict] = []
    if profile.file_format and file_format and profile.file_format != file_format:
        warnings.append(
            {
                "code": "mapping_profile_format_mismatch",
                "message": "The profile was created from a different file format.",
                "context": {
                    "profile_format": profile.file_format,
                    "source_format": file_format,
                },
            }
        )
    if profile.sheet_name_pattern and not fnmatchcase(sheet_name, profile.sheet_name_pattern):
        warnings.append(
            {
                "code": "mapping_profile_sheet_mismatch",
                "message": "The source sheet name does not match the profile pattern.",
                "context": {
                    "pattern": profile.sheet_name_pattern,
                    "sheet_name": sheet_name,
                },
            }
        )
    rules = (
        db.query(MappingProfileRule)
        .filter(
            MappingProfileRule.mapping_profile_id == profile.id,
            MappingProfileRule.is_active.is_(True),
        )
        .all()
    )
    targets = {
        rule.source_key: (rule.target_field, rule.source_inferred_type) for rule in rules
    }
    return profile, targets, warnings


def _latest_mapping_run(db, source_table_id: str, profile_id: str | None):
    query = db.query(MappingRun).filter(MappingRun.source_table_id == source_table_id)
    if profile_id is None:
        query = query.filter(MappingRun.mapping_profile_id.is_(None))
    else:
        query = query.filter(MappingRun.mapping_profile_id == profile_id)
    return query.order_by(MappingRun.run_number.desc(), MappingRun.created_at.desc()).first()


def _upsert_engine_mapping(db, *, table, column, top, profile):
    mapping = (
        db.query(ColumnMapping)
        .filter(ColumnMapping.source_column_id == column.id)
        .first()
    )
    analyst_owned = mapping is not None and (
        mapping.decision_source == "analyst"
        or mapping.status in {ColumnMappingStatus.confirmed, ColumnMappingStatus.rejected}
    )
    if analyst_owned:
        return mapping
    if mapping is None:
        mapping = ColumnMapping(
            source_table_id=table.id,
            source_column_id=column.id,
        )
        db.add(mapping)

    if top is not None and top.confidence >= AUTO_SUGGEST_CONFIDENCE and not column.is_empty:
        mapping.target_field = top.target_field
        mapping.status = ColumnMappingStatus.suggested
        mapping.confidence = top.confidence
        mapping.decision_source = "profile" if profile else "engine"
        mapping.selected_suggestion_id = top.id
        mapping.mapping_profile_id = profile.id if profile else None
        mapping.rationale_json = json_dumps(
            {
                "reason": "Leading deterministic suggestion; analyst confirmation is still required.",
                "engine_version": ENGINE_VERSION,
            }
        )
    else:
        mapping.target_field = None
        mapping.status = ColumnMappingStatus.unmapped
        mapping.confidence = top.confidence if top else None
        mapping.decision_source = "profile" if profile else "engine"
        mapping.selected_suggestion_id = top.id if top else None
        mapping.mapping_profile_id = profile.id if profile else None
        mapping.rationale_json = json_dumps(
            {
                "reason": "No candidate reached the review-suggestion threshold.",
                "threshold": AUTO_SUGGEST_CONFIDENCE,
                "engine_version": ENGINE_VERSION,
            }
        )
    mapping.updated_at = datetime.now(timezone.utc)
    return mapping


def _validate_target_field(target_field: str) -> None:
    if target_field not in TARGET_FIELD_BY_KEY:
        raise AppError(
            "unknown_mapping_target_field",
            f"Unknown mapping target field: {target_field}",
            400,
        )
