"""Creative, brand, audience, and brandbook UI routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from src.modules.audit_log.service import write_audit_event
from src.modules.audience_profiles.schemas import CreateAudienceProfileRequest
from src.modules.audience_profiles.service import (
    create_profile as create_audience_profile,
    get_profile as get_audience_profile,
    list_profiles as list_audience_profiles,
)
from src.modules.brand_profiles.schemas import CreateBrandProfileRequest
from src.modules.brand_profiles.service import (
    create_profile as create_brand_profile,
    get_profile as get_brand_profile,
    list_profiles as list_brand_profiles,
)
from src.modules.creative_assets.schemas import CreateCreativeAssetRequest
from src.modules.creative_assets.service import (
    create_asset,
    create_asset_from_file,
    get_asset,
    list_assets,
)
from src.modules.creative_assets.upload import process_upload
from src.modules.ui.common import detect_lang, render, render_error
from src.shared.errors import AppError

router = APIRouter()


@router.get("/ui/creative-assets", include_in_schema=False)
def ui_creative_assets_list(request: Request):
    return render(request, "creative_assets/list.html", assets=list_assets())


@router.get("/ui/creative-assets/new", include_in_schema=False)
def ui_creative_assets_new(request: Request):
    return render(request, "creative_assets/new.html")


@router.post("/ui/creative-assets", include_in_schema=False)
async def ui_creative_assets_create(
    request: Request,
    title: str = Form(...),
    asset_type: str = Form("text"),
    text_content: str | None = Form(None),
    file: UploadFile | None = File(None),
    project_id: str | None = Form(None),
    metadata: str | None = Form(None),
):
    try:
        parsed_metadata = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        return render(
            request,
            "creative_assets/new.html",
            error="Invalid JSON in metadata field.",
        )

    try:
        asset = await _create_creative_asset(
            title=title,
            asset_type=asset_type,
            text_content=text_content,
            file=file,
            project_id=project_id,
            metadata=parsed_metadata,
        )
    except AppError as exc:
        return render(request, "creative_assets/new.html", error=exc.message)
    return RedirectResponse(url=f"/ui/creative-assets/{asset.id}", status_code=303)


async def _create_creative_asset(
    *,
    title: str,
    asset_type: str,
    text_content: str | None,
    file: UploadFile | None,
    project_id: str | None,
    metadata: dict,
):
    if asset_type == "file" and file and file.filename:
        result = process_upload(
            filename=file.filename,
            content=await file.read(),
            content_type=file.content_type or "application/octet-stream",
        )
        asset = create_asset_from_file(
            title=title or result["original_filename"],
            asset_type=result["asset_type"],
            file_path=result["file_path"],
            original_filename=result["original_filename"],
            mime_type=result["mime_type"],
            file_size_bytes=result["file_size_bytes"],
            extracted_text=result["extracted_text"],
            project_id=project_id or None,
            metadata={
                **metadata,
                **result.get("parser_metadata", {}),
                "warnings": result.get("warnings", []),
            },
        )
        write_audit_event(
            "creative_file_uploaded",
            "creative_asset",
            asset.id,
            {
                "title": asset.title,
                "original_filename": result["original_filename"],
            },
        )
        return asset

    if not text_content:
        raise AppError(
            "creative_asset_text_required",
            "Text content is required for text assets.",
            400,
        )
    asset = create_asset(
        CreateCreativeAssetRequest(
            title=title,
            asset_type="text",
            text_content=text_content,
            project_id=project_id or None,
            metadata=metadata,
        )
    )
    write_audit_event(
        "creative_asset_created",
        "creative_asset",
        asset.id,
        {"title": asset.title},
    )
    return asset


@router.get("/ui/creative-assets/{asset_id}", include_in_schema=False)
def ui_creative_assets_detail(request: Request, asset_id: str):
    asset = get_asset(asset_id)
    if asset is None:
        return render_error(request, f"Creative asset not found: {asset_id}")
    return render(request, "creative_assets/detail.html", asset=asset)


@router.get("/ui/brand-profiles", include_in_schema=False)
def ui_brand_profiles_list(request: Request):
    return render(
        request,
        "brand_profiles/list.html",
        profiles=list_brand_profiles(),
    )


@router.get("/ui/brand-profiles/new", include_in_schema=False)
def ui_brand_profiles_new(request: Request):
    return render(request, "brand_profiles/new.html")


@router.post("/ui/brand-profiles", include_in_schema=False)
def ui_brand_profiles_create(
    request: Request,
    name: str = Form(...),
    tone_of_voice: str | None = Form(None),
    target_audience: str | None = Form(None),
    restrictions: str | None = Form(None),
    claims_policy: str | None = Form(None),
):
    try:
        profile = create_brand_profile(
            CreateBrandProfileRequest(
                name=name,
                tone_of_voice=tone_of_voice,
                target_audience=target_audience,
                restrictions=restrictions,
                claims_policy=claims_policy,
            )
        )
    except AppError as exc:
        return render(request, "brand_profiles/new.html", error=exc.message)
    return RedirectResponse(url=f"/ui/brand-profiles/{profile.id}", status_code=303)


@router.get("/ui/brand-profiles/{profile_id}", include_in_schema=False)
def ui_brand_profiles_detail(request: Request, profile_id: str):
    profile = get_brand_profile(profile_id)
    if profile is None:
        return render_error(request, f"Brand profile not found: {profile_id}")
    return render(request, "brand_profiles/detail.html", profile=profile)


@router.get("/ui/audience-profiles", include_in_schema=False)
def ui_audience_profiles_list(request: Request):
    return render(
        request,
        "audience_profiles/list.html",
        profiles=list_audience_profiles(),
    )


@router.get("/ui/audience-profiles/new", include_in_schema=False)
def ui_audience_profiles_new(request: Request):
    return render(request, "audience_profiles/new.html")


@router.post("/ui/audience-profiles", include_in_schema=False)
def ui_audience_profiles_create(
    request: Request,
    name: str = Form(...),
    segment_description: str = Form(...),
    pains: str | None = Form(None),
    motivations: str | None = Form(None),
    objections: str | None = Form(None),
):
    try:
        profile = create_audience_profile(
            CreateAudienceProfileRequest(
                name=name,
                segment_description=segment_description,
                pains=pains,
                motivations=motivations,
                objections=objections,
            )
        )
    except AppError as exc:
        return render(request, "audience_profiles/new.html", error=exc.message)
    return RedirectResponse(url=f"/ui/audience-profiles/{profile.id}", status_code=303)


@router.get("/ui/audience-profiles/{profile_id}", include_in_schema=False)
def ui_audience_profiles_detail(request: Request, profile_id: str):
    profile = get_audience_profile(profile_id)
    if profile is None:
        return render_error(request, f"Audience profile not found: {profile_id}")
    return render(request, "audience_profiles/detail.html", profile=profile)


@router.get("/ui/brandbooks", include_in_schema=False)
def ui_brandbooks_list(request: Request):
    from src.modules.brandbooks.service import list_brandbooks

    return render(request, "brandbooks/list.html", docs=list_brandbooks())


@router.get("/ui/brandbooks/new", include_in_schema=False)
def ui_brandbooks_new(request: Request):
    return render(request, "brandbooks/new.html")


@router.post("/ui/brandbooks", include_in_schema=False)
async def ui_brandbooks_create(
    request: Request,
    title: str | None = Form(None),
    document_type: str = Form("brandbook"),
    brand_profile_id: str | None = Form(None),
    client_id: str | None = Form(None),
    project_id: str | None = Form(None),
    file: UploadFile = File(...),
):
    from src.modules.brandbooks.router import post_upload_brandbook

    try:
        document = await post_upload_brandbook(
            file=file,
            title=title,
            document_type=document_type,
            client_id=client_id,
            project_id=project_id,
            brand_profile_id=brand_profile_id,
        )
    except Exception as exc:
        return render(request, "brandbooks/new.html", error=str(exc))
    return RedirectResponse(url=f"/ui/brandbooks/{document.id}", status_code=303)


@router.get("/ui/brandbooks/{doc_id}", include_in_schema=False)
def ui_brandbooks_detail(request: Request, doc_id: str):
    from src.modules.brandbooks.service import get_brandbook

    document = get_brandbook(doc_id)
    if document is None:
        return render_error(request, f"Brandbook not found: {doc_id}")
    return render(request, "brandbooks/detail.html", doc=document)


@router.post("/ui/brandbooks/{doc_id}/ingest", include_in_schema=False)
def ui_brandbooks_ingest(request: Request, doc_id: str):
    from src.modules.brandbooks.ingestion import ingest_brandbook
    from src.modules.brandbooks.service import get_brandbook

    document = get_brandbook(doc_id)
    if document is None:
        return render_error(request, f"Brandbook not found: {doc_id}")
    try:
        chunks_created = ingest_brandbook(doc_id)
    except ValueError as exc:
        return render(
            request,
            "brandbooks/detail.html",
            doc=document,
            error=str(exc),
        )
    return render(
        request,
        "brandbooks/detail.html",
        doc=document,
        ingest_result={"chunks_created": chunks_created},
    )


@router.post("/ui/brandbooks/{doc_id}/analyze", include_in_schema=False)
def ui_brandbooks_analyze(request: Request, doc_id: str):
    from src.modules.brandbooks.service import analyze_brandbook, get_brandbook

    document = get_brandbook(doc_id)
    if document is None:
        return render_error(request, f"Brandbook not found: {doc_id}")
    try:
        analysis = analyze_brandbook(doc_id, lang=detect_lang(request))
        document = get_brandbook(doc_id)
    except ValueError as exc:
        return render(
            request,
            "brandbooks/detail.html",
            doc=document,
            error=str(exc),
        )
    except Exception as exc:
        return render(
            request,
            "brandbooks/detail.html",
            doc=document,
            error=f"LLM error: {exc}",
        )
    return render(
        request,
        "brandbooks/detail.html",
        doc=document,
        analysis=analysis,
    )
