from __future__ import annotations

import json
from uuid import uuid4

import pytest

from src.modules.model_profiles.schemas import CreateModelProfileRequest
from src.modules.model_profiles.service import (
    check_profile_health,
    create_profile,
    get_profile,
    upsert_profile,
)
from src.shared.db.session import init_db


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield


def _name(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def test_openai_compatible_local_profile_is_allowed():
    profile = create_profile(
        CreateModelProfileRequest(
            profile_name=_name("mlx-local"),
            provider="openai_compatible_local",
            model="mlx-community/Qwen3.5-4B-MLX-4bit",
            base_url="http://127.0.0.1:8093/v1",
            timeout_seconds=240,
        )
    )
    assert profile.provider == "openai_compatible_local"
    assert profile.model.endswith("4B-MLX-4bit")


def test_openai_compatible_local_rejects_non_loopback_url():
    with pytest.raises(ValueError, match="Non-loopback"):
        create_profile(
            CreateModelProfileRequest(
                profile_name=_name("bad-local"),
                provider="openai_compatible_local",
                model="model-id",
                base_url="https://models.example.com/v1",
            )
        )


def test_upsert_profile_is_idempotent_and_preserves_metadata():
    name = _name("upsert-local")
    first, first_action = upsert_profile(
        CreateModelProfileRequest(
            profile_name=name,
            provider="openai_compatible_local",
            model="model-a",
            base_url="http://127.0.0.1:8093/v1",
            metadata={"profile_id": "cta-model-001"},
        )
    )
    second, second_action = upsert_profile(
        CreateModelProfileRequest(
            profile_name=name,
            provider="openai_compatible_local",
            model="model-b",
            base_url="http://127.0.0.1:8093/v1",
            metadata={"profile_id": "cta-model-001", "revision": "20260801-091536"},
        )
    )
    assert first_action == "created"
    assert second_action == "updated"
    assert first.id == second.id
    assert get_profile(first.id).model == "model-b"
    assert get_profile(first.id).metadata["revision"] == "20260801-091536"


class _Response:
    status = 200

    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def test_health_requires_exact_served_model_identity(monkeypatch):
    model = "mlx-community/Qwen3.5-4B-MLX-4bit"
    profile = create_profile(
        CreateModelProfileRequest(
            profile_name=_name("health-local"),
            provider="openai_compatible_local",
            model=model,
            base_url="http://127.0.0.1:8093/v1",
        )
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _Response({"data": [{"id": model}]}),
    )
    health = check_profile_health(profile.id)
    assert health.reachable is True
    assert model in health.detail

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: _Response({"data": [{"id": "wrong-model"}]}),
    )
    health = check_profile_health(profile.id)
    assert health.reachable is False
    assert any("identity mismatch" in warning for warning in health.warnings)
