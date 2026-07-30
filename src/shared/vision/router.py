import httpx

from fastapi import APIRouter

from src.shared.config.settings import get_settings
from src.shared.vision.schemas import VisionProviderHealth

router = APIRouter()


def _check_vlm_endpoint(base_url: str, timeout: int = 5) -> str | None:
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/v1/models", timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data", [])
            if models:
                return str(models[0].get("id", "unknown"))
            return "no_models"
        return f"http_{resp.status_code}"
    except Exception as exc:
        return f"unreachable: {exc}"


@router.get("/health", response_model=VisionProviderHealth)
def vision_health():
    settings = get_settings()
    provider = settings.vision_provider
    api_style = getattr(settings, "vision_api_style", "ollama")
    warnings = []
    extra = {}

    if provider == "local_ocr":
        try:
            from src.shared.vision.ocr import _TESSERACT_AVAILABLE
            if not _TESSERACT_AVAILABLE:
                warnings.append("local_ocr_unavailable")
        except Exception:
            warnings.append("local_ocr_unavailable")

    if provider in ("local_vlm", "hybrid"):
        if not settings.vision_base_url or not settings.vision_model:
            warnings.append("local_vlm_unavailable")
        else:
            found = _check_vlm_endpoint(settings.vision_base_url)
            if found and not found.startswith("http") and not found.startswith("unreachable"):
                extra["vlm_model_found"] = found
            else:
                warnings.append(f"local_vlm_endpoint_{found}" if found else "local_vlm_endpoint_error")

    if provider == "hybrid":
        ocr_ok = True
        vlm_ok = not any("local_vlm" in w for w in warnings)
        try:
            from src.shared.vision.ocr import _TESSERACT_AVAILABLE
            if not _TESSERACT_AVAILABLE:
                ocr_ok = False
        except Exception:
            ocr_ok = False
        if not ocr_ok and not vlm_ok:
            warnings.append("hybrid_unavailable")
        elif not ocr_ok:
            warnings.append("local_ocr_unavailable")

    return VisionProviderHealth(
        provider=provider,
        api_style=api_style,
        local_ocr_enabled=settings.enable_local_ocr,
        local_vlm_enabled=settings.enable_local_vlm,
        available=provider == "stub" or not warnings,
        warnings=warnings,
        **extra,
    )
