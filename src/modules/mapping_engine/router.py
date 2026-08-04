from fastapi import APIRouter, Query, Request

from src.modules.audit_log.service import write_audit_event
from src.modules.mapping_engine.schemas import (
    ApplyMappingProfileRequest,
    ColumnMappingDecisionRequest,
    ColumnMappingResponse,
    CreateMappingProfileRequest,
    GenerateMappingRequest,
    MappingFieldResponse,
    MappingProfileResponse,
    TableMappingResponse,
)
from src.modules.mapping_engine.service import (
    create_mapping_profile,
    decide_column_mapping,
    generate_mapping_suggestions,
    get_mapping_profile,
    get_table_mapping,
    list_mapping_fields,
    list_mapping_profiles,
)
from src.shared.errors import AppError
from src.shared.security.auth import get_optional_user_id

router = APIRouter(tags=["mapping-engine"])


@router.get("/mapping-fields", response_model=list[MappingFieldResponse])
def get_mapping_fields():
    return list_mapping_fields()


@router.post(
    "/import-sessions/{import_session_id}/files/{file_id}/tables/{table_id}/mapping/suggest",
    response_model=TableMappingResponse,
)
def post_generate_mapping(
    import_session_id: str,
    file_id: str,
    table_id: str,
    body: GenerateMappingRequest,
    request: Request,
):
    result = generate_mapping_suggestions(
        import_session_id,
        file_id,
        table_id,
        mapping_profile_id=body.mapping_profile_id,
        force=body.force,
        created_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "source_column_mapping_generated",
        "source_table",
        table_id,
        {
            "import_session_id": import_session_id,
            "source_file_id": file_id,
            "mapping_run_id": result.run.id if result.run else None,
            "mapping_profile_id": body.mapping_profile_id,
            "force": body.force,
            "suggested_columns": result.suggested_columns,
            "unmapped_columns": result.unmapped_columns,
        },
    )
    return result


@router.get(
    "/import-sessions/{import_session_id}/files/{file_id}/tables/{table_id}/mapping",
    response_model=TableMappingResponse,
)
def get_source_table_mapping(import_session_id: str, file_id: str, table_id: str):
    return get_table_mapping(import_session_id, file_id, table_id)


@router.patch(
    "/import-sessions/{import_session_id}/files/{file_id}/tables/{table_id}/mapping/columns/{column_id}",
    response_model=ColumnMappingResponse,
)
def patch_column_mapping(
    import_session_id: str,
    file_id: str,
    table_id: str,
    column_id: str,
    body: ColumnMappingDecisionRequest,
    request: Request,
):
    result = decide_column_mapping(
        import_session_id,
        file_id,
        table_id,
        column_id,
        body,
        decided_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "source_column_mapping_decided",
        "source_column",
        column_id,
        {
            "source_table_id": table_id,
            "status": result.status,
            "target_field": result.target_field,
            "selected_suggestion_id": result.selected_suggestion_id,
            "allow_duplicate": body.allow_duplicate,
        },
    )
    return result


@router.post("/mapping-profiles", response_model=MappingProfileResponse, status_code=201)
def post_create_mapping_profile(body: CreateMappingProfileRequest, request: Request):
    profile = create_mapping_profile(body, created_by_user_id=get_optional_user_id(request))
    write_audit_event(
        "mapping_profile_created",
        "mapping_profile",
        profile.id,
        {
            "project_id": profile.project_id,
            "name": profile.name,
            "version": profile.version,
            "rule_count": len(profile.rules),
            "created_from_table_id": profile.created_from_table_id,
        },
    )
    return profile


@router.get("/mapping-profiles", response_model=list[MappingProfileResponse])
def get_mapping_profiles(
    project_id: str = Query(..., min_length=1),
    status: str | None = Query(None),
):
    return list_mapping_profiles(project_id, status=status)


@router.get("/mapping-profiles/{profile_id}", response_model=MappingProfileResponse)
def get_mapping_profile_by_id(profile_id: str):
    profile = get_mapping_profile(profile_id)
    if profile is None:
        raise AppError("mapping_profile_not_found", "Mapping profile not found", 404)
    return profile


@router.post(
    "/import-sessions/{import_session_id}/files/{file_id}/tables/{table_id}/mapping/apply-profile",
    response_model=TableMappingResponse,
)
def post_apply_mapping_profile(
    import_session_id: str,
    file_id: str,
    table_id: str,
    body: ApplyMappingProfileRequest,
    request: Request,
):
    result = generate_mapping_suggestions(
        import_session_id,
        file_id,
        table_id,
        mapping_profile_id=body.mapping_profile_id,
        force=body.force,
        created_by_user_id=get_optional_user_id(request),
    )
    write_audit_event(
        "mapping_profile_applied",
        "source_table",
        table_id,
        {
            "mapping_profile_id": body.mapping_profile_id,
            "mapping_run_id": result.run.id if result.run else None,
            "suggested_columns": result.suggested_columns,
            "unmapped_columns": result.unmapped_columns,
        },
    )
    return result
