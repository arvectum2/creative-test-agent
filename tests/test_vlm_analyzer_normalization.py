"""Normalization tests for the local VLM analyzers (CTA-BENCH-002)."""

import json

import pytest

from src.shared.vision.vlm import LocalVlmAnalyzer, OpenAiCompatibleVlmAnalyzer


class _FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def _analyze(analyzer, image_path, fake_body, monkeypatch):
    import httpx

    def _fake_post(*args, **kwargs):
        return _FakeResponse(fake_body)

    monkeypatch.setattr(httpx, "post", _fake_post)
    return analyzer.analyze_image(image_path)


@pytest.mark.parametrize(
    "api_style",
    ["openai_compatible", "ollama"],
)
def test_detected_text_list_is_normalized_to_string(tmp_path, api_style, monkeypatch):
    img = tmp_path / "img.png"
    img.write_bytes(b"not-a-real-png")

    if api_style == "openai_compatible":
        analyzer = OpenAiCompatibleVlmAnalyzer(
            base_url="http://127.0.0.1:8099", model="mlx-test", timeout_seconds=30
        )
    else:
        analyzer = LocalVlmAnalyzer(base_url="http://127.0.0.1:11434", model="mlx-test")

    body = {
        "choices": [{"message": {"content": json.dumps(
            {"visual_summary": "s", "detected_text": ["NOVALEN", "LEARN MORE"]}
        )}}],
        "message": {"content": json.dumps(
            {"visual_summary": "s", "detected_text": ["NOVALEN", "LEARN MORE"]}
        )},
    }
    result = _analyze(analyzer, str(img), body, monkeypatch)

    assert result.warnings == []
    assert result.detected_text == "NOVALEN LEARN MORE"


@pytest.mark.parametrize(
    "api_style",
    ["openai_compatible", "ollama"],
)
def test_detected_text_string_passthrough(tmp_path, api_style, monkeypatch):
    img = tmp_path / "img.png"
    img.write_bytes(b"not-a-real-png")

    if api_style == "openai_compatible":
        analyzer = OpenAiCompatibleVlmAnalyzer(
            base_url="http://127.0.0.1:8099", model="mlx-test", timeout_seconds=30
        )
    else:
        analyzer = LocalVlmAnalyzer(base_url="http://127.0.0.1:11434", model="mlx-test")

    body = {
        "choices": [{"message": {"content": json.dumps(
            {"visual_summary": "s", "detected_text": "NOVALEN"}
        )}}],
        "message": {"content": json.dumps(
            {"visual_summary": "s", "detected_text": "NOVALEN"}
        )},
    }
    result = _analyze(analyzer, str(img), body, monkeypatch)

    assert result.warnings == []
    assert result.detected_text == "NOVALEN"
