"""Tests for the OpenAI-compatible local LLM provider (CTA-BENCH-002)."""

import pytest

from src.shared.config.settings import Settings
from src.shared.errors import AppError
from src.shared.llm.factory import get_llm_provider
from src.shared.llm.openai_compatible_local import OpenAiCompatibleLocalProvider


def test_factory_returns_openai_compatible_local():
    settings = Settings(
        llm_provider="openai_compatible_local",
        llm_model="mlx-community/Qwen3.5-9B-MLX-4bit",
        llm_base_url="http://127.0.0.1:8092/v1",
        local_only_mode=True,
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAiCompatibleLocalProvider)


def test_constructor_rejects_non_loopback_url():
    with pytest.raises(AppError) as exc:
        OpenAiCompatibleLocalProvider(
            Settings(
                llm_provider="openai_compatible_local",
                llm_model="model",
                llm_base_url="http://example.com/v1",
            )
        )
    assert exc.value.code == "llm_loopback_required"


def test_constructor_rejects_cloud_host():
    with pytest.raises(AppError):
        OpenAiCompatibleLocalProvider(
            Settings(
                llm_provider="openai_compatible_local",
                llm_model="model",
                llm_base_url="https://api.openai.com/v1",
            )
        )


def test_policy_allows_openai_compatible_local_in_local_only_mode():
    settings = Settings(
        llm_provider="openai_compatible_local",
        local_only_mode=True,
        llm_model="model",
        llm_base_url="http://127.0.0.1:8092/v1",
    )
    provider = get_llm_provider(settings)
    assert isinstance(provider, OpenAiCompatibleLocalProvider)


def test_healthcheck_reports_unavailable_when_no_server():
    settings = Settings(
        llm_provider="openai_compatible_local",
        llm_model="model",
        llm_base_url="http://127.0.0.1:1/v1",
    )
    provider = OpenAiCompatibleLocalProvider(settings)
    result = provider.healthcheck()
    assert result["available"] is False
    assert result["local_only_mode"] is True


def test_generate_connection_error_when_no_server():
    settings = Settings(
        llm_provider="openai_compatible_local",
        llm_model="model",
        llm_base_url="http://127.0.0.1:1/v1",
        llm_timeout_seconds=2,
    )
    provider = OpenAiCompatibleLocalProvider(settings)
    with pytest.raises(AppError) as exc:
        provider.generate("ping")
    assert exc.value.code in {"llm_connection_error", "llm_timeout"}
