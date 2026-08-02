"""Optional local VLM adapter.

Supports two API styles:
- ollama (default): sends to {base_url}/api/chat with images array
- openai_compatible: sends to {base_url}/v1/chat/completions with content parts

Falls back gracefully if the model or endpoint is unavailable.
"""

import base64
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.shared.vision.base import VisionAnalyzer
from src.shared.vision.schemas import VisionResult

logger = logging.getLogger(__name__)

LOCALHOST_IPS = {"127.0.0.1", "::1", "localhost"}
_VLM_STRUCTURED_PROMPT = (
    "Analyze this marketing creative image. "
    "Return a JSON object with fields: "
    '"visual_summary" (brief description), '
    '"detected_text" (any visible text), '
    '"layout_notes" (list of layout observations), '
    '"visual_risks" (list of objects with risk_type, level, description, mitigation).'
)


def _validate_loopback_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host not in LOCALHOST_IPS:
        raise ValueError(
            f"Vision base URL must be a loopback address (localhost, 127.0.0.1, ::1), got '{host}'"
        )


def _detect_image_mime(image_path: str) -> str:
    suffix = Path(image_path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "image/png")


def _image_limit_result(
    warning: str,
    detail: str,
    metadata: dict | None = None,
) -> VisionResult:
    warnings = ["local_vlm_image_limit_exceeded", detail]
    return VisionResult(
        provider="local_vlm",
        visual_summary="",
        detected_text="",
        layout_notes=[],
        visual_risks=[],
        warnings=warnings,
        metadata={
            **(metadata or {}),
            "vlm_limit_warning": warning,
        },
    )


def _check_image_limits(
    image_path: str,
    *,
    max_image_bytes: int | None,
    max_image_pixels: int | None,
    metadata: dict | None = None,
) -> VisionResult | None:
    if max_image_bytes is None and max_image_pixels is None:
        return None
    path = Path(image_path)
    try:
        size = path.stat().st_size
    except OSError:
        return _image_limit_result(
            "image_unreadable",
            f"image file cannot be read: {path}",
            metadata=metadata,
        )
    if max_image_bytes is not None and size > max_image_bytes:
        return _image_limit_result(
            "image_too_large_bytes",
            f"image exceeds the frozen byte limit ({size} > {max_image_bytes})",
            metadata={**(metadata or {}), "image_bytes": size, "max_image_bytes": max_image_bytes},
        )
    if max_image_pixels is not None:
        try:
            from PIL import Image

            with Image.open(str(path)) as img:
                pixels = img.width * img.height
        except Exception:
            return _image_limit_result(
                "image_dimensions_unreadable",
                "image dimensions cannot be determined; refusing to send",
                metadata=metadata,
            )
        if pixels > max_image_pixels:
            return _image_limit_result(
                "image_too_many_pixels",
                f"image exceeds the frozen pixel limit ({pixels} > {max_image_pixels})",
                metadata={
                    **(metadata or {}),
                    "image_pixels": pixels,
                    "max_image_pixels": max_image_pixels,
                },
            )
    return None


class LocalVlmAnalyzer(VisionAnalyzer):
    def __init__(
        self,
        base_url: str = "",
        model: str = "",
        max_image_bytes: int | None = None,
        max_image_pixels: int | None = None,
    ):
        self.base_url = base_url
        self.model = model
        self.max_image_bytes = max_image_bytes
        self.max_image_pixels = max_image_pixels

    def analyze_image(self, image_path: str, metadata: dict | None = None) -> VisionResult:
        if not self.base_url or not self.model:
            return VisionResult(
                provider="local_vlm",
                visual_summary="",
                detected_text="",
                layout_notes=[],
                visual_risks=[],
                warnings=["local_vlm_unavailable"],
                metadata=metadata or {},
            )

        limited = _check_image_limits(
            image_path,
            max_image_bytes=self.max_image_bytes,
            max_image_pixels=self.max_image_pixels,
            metadata=metadata,
        )
        if limited is not None:
            return limited

        try:
            with open(image_path, "rb") as f:
                b64_img = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": _VLM_STRUCTURED_PROMPT,
                        "images": [b64_img],
                    }
                ],
                "stream": False,
            }

            response = httpx.post(
                f"{self.base_url.rstrip('/')}/api/chat",
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            content = result.get("message", {}).get("content", "")

            parsed = {}
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                pass

            detected_text = parsed.get("detected_text", "")
            if isinstance(detected_text, list):
                detected_text = " ".join(str(part) for part in detected_text)

            return VisionResult(
                provider="local_vlm",
                visual_summary=parsed.get("visual_summary", content),
                detected_text=detected_text,
                layout_notes=parsed.get("layout_notes", []),
                visual_risks=parsed.get("visual_risks", []),
                warnings=[],
                metadata={"vlm_model": self.model, "raw_response_length": len(content)},
            )

        except Exception as exc:
            logger.warning("Local VLM failed: %s", exc)
            return VisionResult(
                provider="local_vlm",
                visual_summary="",
                detected_text="",
                layout_notes=[],
                visual_risks=[],
                warnings=["local_vlm_unavailable", str(exc)],
                metadata=metadata or {},
            )


class OpenAiCompatibleVlmAnalyzer(VisionAnalyzer):
    def __init__(
        self,
        base_url: str = "",
        model: str = "",
        timeout_seconds: int = 240,
        max_image_bytes: int | None = None,
        max_image_pixels: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds
        self.max_image_bytes = max_image_bytes
        self.max_image_pixels = max_image_pixels

    def analyze_image(self, image_path: str, metadata: dict | None = None) -> VisionResult:
        if not self.base_url or not self.model:
            return VisionResult(
                provider="local_vlm",
                visual_summary="",
                detected_text="",
                layout_notes=[],
                visual_risks=[],
                warnings=["local_vlm_unavailable"],
                metadata=metadata or {},
            )

        limited = _check_image_limits(
            image_path,
            max_image_bytes=self.max_image_bytes,
            max_image_pixels=self.max_image_pixels,
            metadata=metadata,
        )
        if limited is not None:
            return limited

        try:
            _validate_loopback_url(self.base_url)

            with open(image_path, "rb") as f:
                b64_img = base64.b64encode(f.read()).decode("ascii")

            mime = _detect_image_mime(image_path)

            payload = {
                "model": self.model,
                "temperature": 0.0,
                "seed": 42,
                "max_tokens": 2048,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _VLM_STRUCTURED_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64_img}"},
                            },
                        ],
                    }
                ],
                "stream": False,
            }

            response = httpx.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            parsed = {}
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                pass

            detected_text = parsed.get("detected_text", "")
            if isinstance(detected_text, list):
                detected_text = " ".join(str(part) for part in detected_text)

            return VisionResult(
                provider="local_vlm",
                visual_summary=parsed.get("visual_summary", content),
                detected_text=detected_text,
                layout_notes=parsed.get("layout_notes", []),
                visual_risks=parsed.get("visual_risks", []),
                warnings=[],
                metadata={
                    "vlm_model": self.model,
                    "vlm_api_style": "openai_compatible",
                    "vlm_backend": "llamacpp",
                    "raw_response_length": len(content),
                },
            )

        except Exception as exc:
            logger.warning("OpenAI-compatible VLM failed: %s", exc)
            return VisionResult(
                provider="local_vlm",
                visual_summary="",
                detected_text="",
                layout_notes=[],
                visual_risks=[],
                warnings=["local_vlm_unavailable", str(exc)],
                metadata=metadata or {},
            )
