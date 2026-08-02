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


@pytest.mark.parametrize(
    "api_style",
    ["openai_compatible", "ollama"],
)
def test_image_byte_limit_fails_closed_before_request(tmp_path, api_style, monkeypatch):
    import httpx

    img = tmp_path / "img.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 2048)
    called = []

    def _fake_post(*args, **kwargs):
        called.append(True)
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(httpx, "post", _fake_post)

    if api_style == "openai_compatible":
        analyzer = OpenAiCompatibleVlmAnalyzer(
            base_url="http://127.0.0.1:8099",
            model="mlx-test",
            timeout_seconds=30,
            max_image_bytes=1024,
            max_image_pixels=16_000_000,
        )
    else:
        analyzer = LocalVlmAnalyzer(
            base_url="http://127.0.0.1:11434",
            model="mlx-test",
            max_image_bytes=1024,
            max_image_pixels=16_000_000,
        )

    result = analyzer.analyze_image(str(img))

    assert called == []
    assert any("local_vlm_image_limit_exceeded" in w for w in result.warnings)
    assert result.metadata.get("vlm_limit_warning") == "image_too_large_bytes"
    assert result.detected_text == ""
    assert result.visual_risks == []


@pytest.mark.parametrize(
    "api_style",
    ["openai_compatible", "ollama"],
)
def test_image_pixel_limit_fails_closed_before_request(tmp_path, api_style, monkeypatch):
    import httpx

    from PIL import Image

    img = tmp_path / "img.png"
    Image.new("RGB", (4096, 4096)).save(str(img))
    called = []

    def _fake_post(*args, **kwargs):
        called.append(True)
        return _FakeResponse({"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(httpx, "post", _fake_post)

    if api_style == "openai_compatible":
        analyzer = OpenAiCompatibleVlmAnalyzer(
            base_url="http://127.0.0.1:8099",
            model="mlx-test",
            timeout_seconds=30,
            max_image_bytes=100_000_000,
            max_image_pixels=4_000_000,
        )
    else:
        analyzer = LocalVlmAnalyzer(
            base_url="http://127.0.0.1:11434",
            model="mlx-test",
            max_image_bytes=100_000_000,
            max_image_pixels=4_000_000,
        )

    result = analyzer.analyze_image(str(img))

    assert called == []
    assert any("local_vlm_image_limit_exceeded" in w for w in result.warnings)
    assert result.metadata.get("vlm_limit_warning") == "image_too_many_pixels"
    assert result.detected_text == ""


@pytest.mark.parametrize(
    "api_style",
    ["openai_compatible", "ollama"],
)
def test_image_within_limits_passes_through(tmp_path, api_style, monkeypatch):
    import httpx

    from PIL import Image

    img = tmp_path / "img.png"
    Image.new("RGB", (64, 64), color=(10, 20, 30)).save(str(img))
    called = []

    def _fake_post(*args, **kwargs):
        called.append(True)
        return _FakeResponse({
            "choices": [{"message": {"content": json.dumps(
                {"visual_summary": "s", "detected_text": "OK"}
            )}}],
            "message": {"content": json.dumps(
                {"visual_summary": "s", "detected_text": "OK"}
            )},
        })

    monkeypatch.setattr(httpx, "post", _fake_post)

    if api_style == "openai_compatible":
        analyzer = OpenAiCompatibleVlmAnalyzer(
            base_url="http://127.0.0.1:8099",
            model="mlx-test",
            timeout_seconds=30,
            max_image_bytes=10_000_000,
            max_image_pixels=16_000_000,
        )
    else:
        analyzer = LocalVlmAnalyzer(
            base_url="http://127.0.0.1:11434",
            model="mlx-test",
            max_image_bytes=10_000_000,
            max_image_pixels=16_000_000,
        )

    result = analyzer.analyze_image(str(img))

    assert called == [True]
    assert result.warnings == []
    assert result.detected_text == "OK"
