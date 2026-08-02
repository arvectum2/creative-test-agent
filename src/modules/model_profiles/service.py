import json
import urllib.error
import urllib.request
from pathlib import Path

from src.modules.model_profiles.models import ModelProfile
from src.modules.model_profiles.schemas import (
    CreateModelProfileRequest,
    ModelProfileHealth,
    ModelProfileResponse,
)
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.security.hardening import is_loopback_url

ALLOWED_PROVIDERS = {"stub", "ollama", "lmstudio", "openai_compatible_local"}
FORBIDDEN_PROVIDERS = {
    "openai",
    "anthropic",
    "gemini",
    "perplexity",
    "claude",
    "azure_openai",
}

LOCAL_ONLY_PROVIDERS = {"ollama", "lmstudio", "openai_compatible_local"}


def _check_url_is_allowed(base_url: str, provider: str) -> list[str]:
    warnings: list[str] = []
    if provider in LOCAL_ONLY_PROVIDERS:
        if not base_url:
            warnings.append(f"base_url is required for local provider '{provider}'")
        elif not is_loopback_url(base_url):
            warnings.append(
                f"Cloud URL / Non-loopback URL is forbidden for local provider '{provider}': {base_url}"
            )
    return warnings


def _to_response(p: ModelProfile) -> ModelProfileResponse:
    return ModelProfileResponse(
        id=p.id,
        profile_name=p.profile_name,
        provider=p.provider,
        model=p.model,
        base_url=p.base_url,
        enabled=p.enabled,
        default_for_demo=p.default_for_demo,
        timeout_seconds=p.timeout_seconds,
        notes=p.notes,
        metadata=json_loads(p.metadata_json) or {},
        created_at=p.created_at,
    )


def _validate_request(req: CreateModelProfileRequest) -> None:
    if req.provider in FORBIDDEN_PROVIDERS:
        raise ValueError(f"Provider '{req.provider}' is not allowed")
    if req.provider not in ALLOWED_PROVIDERS:
        raise ValueError(
            f"Provider '{req.provider}' is not recognized. "
            f"Allowed: {', '.join(sorted(ALLOWED_PROVIDERS))}"
        )
    warnings = _check_url_is_allowed(req.base_url or "", req.provider)
    if warnings:
        raise ValueError("; ".join(warnings))
    if req.provider == "openai_compatible_local" and not req.model.strip():
        raise ValueError("An explicit model ID is required for openai_compatible_local")


def create_profile(req: CreateModelProfileRequest) -> ModelProfileResponse:
    _validate_request(req)
    with db_session() as db:
        existing = (
            db.query(ModelProfile)
            .filter(ModelProfile.profile_name == req.profile_name)
            .first()
        )
        if existing is not None:
            raise ValueError(f"Model profile already exists: {req.profile_name}")
        profile = ModelProfile(
            profile_name=req.profile_name,
            provider=req.provider,
            model=req.model,
            base_url=req.base_url,
            enabled=req.enabled,
            default_for_demo=req.default_for_demo,
            timeout_seconds=req.timeout_seconds,
            notes=req.notes,
            metadata_json=json_dumps(req.metadata),
        )
        db.add(profile)
        db.flush()
        db.refresh(profile)
        return _to_response(profile)


def upsert_profile(req: CreateModelProfileRequest) -> tuple[ModelProfileResponse, str]:
    """Create or replace a config-owned profile by its stable profile name."""
    _validate_request(req)
    with db_session() as db:
        profile = (
            db.query(ModelProfile)
            .filter(ModelProfile.profile_name == req.profile_name)
            .first()
        )
        action = "created"
        if profile is None:
            profile = ModelProfile(profile_name=req.profile_name)
            db.add(profile)
        else:
            action = "updated"
        profile.provider = req.provider
        profile.model = req.model
        profile.base_url = req.base_url
        profile.enabled = req.enabled
        profile.default_for_demo = req.default_for_demo
        profile.timeout_seconds = req.timeout_seconds
        profile.notes = req.notes
        profile.metadata_json = json_dumps(req.metadata)
        db.flush()
        db.refresh(profile)
        return _to_response(profile), action


def list_profiles() -> list[ModelProfileResponse]:
    with db_session() as db:
        profiles = db.query(ModelProfile).order_by(ModelProfile.profile_name).all()
        return [_to_response(p) for p in profiles]


def get_profile(profile_id: str) -> ModelProfileResponse | None:
    with db_session() as db:
        p = db.query(ModelProfile).filter(ModelProfile.id == profile_id).first()
        if p is None:
            return None
        return _to_response(p)


def _model_ids(payload: dict) -> list[str]:
    raw_models = payload.get("data") or payload.get("models") or []
    result: list[str] = []
    for item in raw_models:
        if isinstance(item, dict):
            value = item.get("id") or item.get("model") or item.get("name")
        else:
            value = item
        if value is not None:
            result.append(str(value))
    return result


def _health_url(profile: ModelProfileResponse) -> str:
    base = (profile.base_url or "").rstrip("/")
    if profile.provider == "openai_compatible_local":
        return f"{base}/models"
    return base or "/"


def check_profile_health(profile_id: str) -> ModelProfileHealth:
    profile = get_profile(profile_id)
    if profile is None:
        raise ValueError(f"Model profile not found: {profile_id}")

    warnings: list[str] = []

    if profile.provider == "stub":
        return ModelProfileHealth(
            profile_id=profile.id,
            profile_name=profile.profile_name,
            provider=profile.provider,
            reachable=True,
            detail="Stub provider is always available.",
            warnings=warnings,
        )

    if profile.provider in FORBIDDEN_PROVIDERS:
        warnings.append(f"Provider '{profile.provider}' is forbidden.")
        return ModelProfileHealth(
            profile_id=profile.id,
            profile_name=profile.profile_name,
            provider=profile.provider,
            reachable=False,
            detail="Forbidden provider.",
            warnings=warnings,
        )

    warnings.extend(_check_url_is_allowed(profile.base_url or "", profile.provider))
    if warnings:
        return ModelProfileHealth(
            profile_id=profile.id,
            profile_name=profile.profile_name,
            provider=profile.provider,
            reachable=False,
            detail="Local-provider URL policy failed.",
            warnings=warnings,
        )

    try:
        request = urllib.request.Request(
            _health_url(profile),
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=profile.timeout_seconds) as response:
            body = response.read()
            status = response.status
        reachable = True
        detail = f"Provider reachable (HTTP {status})."
        if profile.provider == "openai_compatible_local":
            payload = json.loads(body.decode("utf-8"))
            models = _model_ids(payload)
            if profile.model not in models:
                reachable = False
                warnings.append(
                    f"Model identity mismatch: expected '{profile.model}', served {models or 'none'}"
                )
                detail = "Provider reachable but the frozen model identity is not served."
            else:
                detail = f"Provider reachable and serves explicit model '{profile.model}'."
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        reachable = False
        detail = f"Provider unreachable: {exc}"
        warnings.append(f"Health check failed: {exc}")

    return ModelProfileHealth(
        profile_id=profile.id,
        profile_name=profile.profile_name,
        provider=profile.provider,
        reachable=reachable,
        detail=detail,
        warnings=warnings,
    )


def _request_from_config(config_path: str | Path) -> CreateModelProfileRequest:
    with Path(config_path).open(encoding="utf-8") as stream:
        data = json.load(stream)
    return CreateModelProfileRequest(
        profile_name=data["profile_name"],
        provider=data["provider"],
        model=data["model"],
        base_url=data.get("base_url"),
        enabled=data.get("enabled", False),
        default_for_demo=data.get("default_for_demo", False),
        timeout_seconds=data.get("timeout_seconds", 60),
        notes=data.get("notes"),
        metadata=data.get("metadata") or {},
    )


def load_profile_from_config_with_action(
    config_path: str | Path,
) -> tuple[ModelProfileResponse, str]:
    return upsert_profile(_request_from_config(config_path))


def load_profile_from_config(config_path: str | Path) -> ModelProfileResponse:
    profile, _ = load_profile_from_config_with_action(config_path)
    return profile
