"""Generic OpenAI-compatible local LLM provider.

Used for local endpoints that expose ``/v1/models`` and ``/v1/chat/completions``
(such as mlx-openai-server or llama.cpp). Enforces loopback-only, never requires
an API key by default and requires an explicit model ID.
"""

from __future__ import annotations

import httpx

from src.shared.config.settings import get_settings
from src.shared.errors import AppError
from src.shared.llm.base import LLMProvider
from src.shared.security.hardening import is_loopback_url


class OpenAiCompatibleLocalProvider(LLMProvider):
    def __init__(self, settings=None):
        self._settings = settings or get_settings()
        self.model = self._settings.llm_model or "local-model"
        self.base_url = (self._settings.llm_base_url or "http://127.0.0.1:8080/v1").rstrip("/")
        self.timeout = self._settings.llm_timeout_seconds
        if not is_loopback_url(self.base_url):
            raise AppError(
                code="llm_loopback_required",
                message=(
                    f"OpenAI-compatible local LLM base URL must be loopback-only, "
                    f"got '{self.base_url}'."
                ),
                status_code=400,
            )

    def generate(self, prompt: str, metadata: dict | None = None) -> dict:
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 4096,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "provider": "openai_compatible_local",
                "content": content,
                "metadata": {
                    "model": self.model,
                    "base_url": self.base_url,
                    **(metadata or {}),
                },
            }
        except httpx.ConnectError:
            raise AppError(
                code="llm_connection_error",
                message=f"Cannot connect to the local OpenAI-compatible server at {self.base_url}.",
                status_code=503,
            )
        except httpx.TimeoutException:
            raise AppError(
                code="llm_timeout",
                message=f"Local LLM request timed out after {self.timeout}s.",
                status_code=504,
            )
        except httpx.HTTPStatusError as e:
            raise AppError(
                code="llm_http_error",
                message=f"Local LLM returned HTTP {e.response.status_code}: {e.response.text[:200]}",
                status_code=502,
            )

    def healthcheck(self) -> dict:
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=5)
            resp.raise_for_status()
            return {
                "provider": "openai_compatible_local",
                "model": self.model,
                "base_url": self.base_url,
                "available": True,
                "local_only_mode": True,
            }
        except Exception:
            return {
                "provider": "openai_compatible_local",
                "model": self.model,
                "base_url": self.base_url,
                "available": False,
                "local_only_mode": True,
            }
