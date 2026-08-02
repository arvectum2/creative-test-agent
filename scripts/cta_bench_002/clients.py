"""Benchmark clients for CTA-BENCH-002.

OpenAI-compatible VLM/LLM clients with explicit model IDs, loopback-only
validation, base64 image transport and SSE streaming for TTFT measurement.
In-process OCR (Tesseract / PaddleOCR) and the application LLM profile are
also exposed as benchmark candidates.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import httpx

from src.shared.security.hardening import is_loopback_url
from src.shared.vision.ocr import LocalOcrAnalyzer

import re as _re

def _strip_thinking_tags(text: str) -> str:
    return _re.sub(r"<think>.*?</think>\s*", "", text, flags=_re.DOTALL).strip()

from scripts.cta_bench_002.spec import LOOPBACK


class EndpointError(Exception):
    pass


class OpenAiCompatibleClient:
    """Minimal OpenAI-compatible client with explicit model and stream support."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 240,
        max_tokens: int = 4096,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        parsed = self.base_url.split("//")[-1]
        host = parsed.split(":")[0] if ":" in parsed else parsed
        if not is_loopback_url(f"http://{host}"):
            raise ValueError(f"Benchmark endpoint must be loopback-only, got {base_url}")

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        stream: bool = False,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        else:
            payload["max_tokens"] = self.max_tokens
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
                if resp.status_code >= 400:
                    raise EndpointError(
                        f"HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                return resp.json()
        except httpx.HTTPError as exc:
            raise EndpointError(f"{type(exc).__name__}: {exc}") from exc

    def stream_first_content(self, *, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Stream and capture TTFT (first non-empty content chunk) + full text.

        Empty role-only chunks are not counted as first content.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "stream": True,
            "max_tokens": self.max_tokens,
        }
        started = time.perf_counter()
        ttft_ms: float | None = None
        chunks: list[str] = []
        usage: dict[str, Any] = {}
        first_chunk_at: float | None = None
        empty_chunks_before_content = 0
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream("POST", f"{self.base_url}/v1/chat/completions", json=payload) as resp:
                    if resp.status_code >= 400:
                        raise EndpointError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if event.get("usage"):
                            usage = event["usage"]
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            if ttft_ms is None:
                                ttft_ms = (time.perf_counter() - started) * 1000
                                first_chunk_at = time.perf_counter()
                            chunks.append(content)
                        elif delta.get("role"):
                            empty_chunks_before_content += 1
            wall_ms = (time.perf_counter() - started) * 1000
            full_text = _strip_thinking_tags("".join(chunks))
            return {
                "content": full_text,
                "ttft_ms": ttft_ms,
                "wall_ms": wall_ms,
                "empty_chunks_before_content": empty_chunks_before_content,
                "usage": usage,
                "stream": True,
            }
        except httpx.HTTPError as exc:
            raise EndpointError(f"{type(exc).__name__}: {exc}") from exc


class VlmBenchmarkClient(OpenAiCompatibleClient):
    def analyze_image(
        self,
        image_path: Path,
        prompt: str,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ]
        if stream:
            return self.stream_first_content(messages=messages)
        result = self.chat(messages=messages, temperature=0.0)
        content = (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return {
            "content": content,
            "usage": result.get("usage") or {},
            "wall_ms": None,
            "ttft_ms": None,
            "stream": False,
            "model": result.get("model"),
        }


class LlmBenchmarkClient(OpenAiCompatibleClient):
    def complete(self, prompt: str, *, stream: bool = False) -> dict[str, Any]:
        messages = [{"role": "user", "content": prompt}]
        if stream:
            result = self.stream_first_content(messages=messages)
            result["content"] = _strip_thinking_tags(result["content"])
            return result
        result = self.chat(messages=messages, temperature=0.0)
        content = (result.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return {
            "content": _strip_thinking_tags(content),
            "usage": result.get("usage") or {},
            "wall_ms": None,
            "ttft_ms": None,
            "stream": False,
            "model": result.get("model"),
        }


class TesseractBenchmarkClient:
    """In-process OCR candidate using the application Tesseract analyzer."""

    candidate_id = "OCR-TESSERACT"

    def __init__(self) -> None:
        self._analyzer = LocalOcrAnalyzer()

    def analyze_image(self, image_path: Path, case_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        result = self._analyzer.analyze_image(
            str(image_path),
            {"case_id": case_id, "benchmark_id": "cta-bench-002"},
        )
        wall_ms = (time.perf_counter() - started) * 1000
        return {
            "content": result.detected_text,
            "warnings": list(result.warnings),
            "metadata": dict(result.metadata),
            "wall_ms": wall_ms,
            "ttft_ms": None,
            "abstained": not result.detected_text.strip(),
            "stream": False,
        }


class PaddleOcrBenchmarkClient:
    """Optional in-process OCR challenger. Raises at import/use if unavailable."""

    candidate_id = "OCR-CHALLENGER"

    def __init__(self) -> None:
        try:
            from paddleocr import PaddleOCR  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise EndpointError(
                "PaddleOCR is not installed: " + str(exc)
            ) from exc
        self._ocr = PaddleOCR(lang="multilingual")

    def analyze_image(self, image_path: Path, case_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            output = self._ocr.ocr(str(image_path), cls=False)
        except Exception as exc:  # pragma: no cover - runtime dependent
            return {
                "content": "",
                "warnings": [f"paddleocr_failed:{exc}"],
                "metadata": {},
                "wall_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": None,
                "abstained": True,
                "stream": False,
                "error": str(exc),
            }
        lines: list[str] = []
        if output:
            for page in output:
                if not page:
                    continue
                for item in page:
                    text = (item or [None, None])[1]
                    if isinstance(text, tuple) and text:
                        lines.append(str(text[0]))
        wall_ms = (time.perf_counter() - started) * 1000
        return {
            "content": "\n".join(lines),
            "warnings": [],
            "metadata": {"engine": "paddleocr"},
            "wall_ms": wall_ms,
            "ttft_ms": None,
            "abstained": not lines,
            "stream": False,
        }


class AppProfileLlmBenchmarkClient:
    """LLM-CURRENT baseline through the application LLM provider (stub/ollama/lmstudio)."""

    candidate_id = "LLM-CURRENT"

    def __init__(self, provider_name: str = "stub") -> None:
        self.provider_name = provider_name
        from src.shared.llm.factory import get_llm_provider
        from src.shared.config.settings import Settings

        self._settings = Settings()
        self._provider = get_llm_provider(self._settings)

    def complete(self, prompt: str, *, stream: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        result = self._provider.generate(prompt)
        wall_ms = (time.perf_counter() - started) * 1000
        return {
            "content": result.get("content", ""),
            "metadata": result.get("metadata", {}),
            "wall_ms": wall_ms,
            "ttft_ms": None,
            "stream": False,
            "provider": self.provider_name,
        }


class FixtureLlmBenchmarkClient:
    """Deterministic schema-valid LLM fixture for harness self-tests only.

    Returns stage-appropriate JSON that passes the canonical structured-output
    schema without touching any model. It must never be ranked as a candidate.
    """

    candidate_id = "fixture:llm-contract"
    harness_only = True

    def complete(self, prompt: str, *, stream: bool = False) -> dict[str, Any]:
        started = time.perf_counter()
        content = _fixture_response(prompt)
        return {
            "content": content,
            "metadata": {"fixture_contract": True},
            "wall_ms": (time.perf_counter() - started) * 1000,
            "ttft_ms": None,
            "stream": False,
        }


def _fixture_response(prompt: str) -> str:
    import json

    lowered = prompt.casefold()
    stage = "unknown"
    for name, key in [
        ("creative_summary", "creative intake agent"),
        ("audience_simulation", "audience simulation agent"),
        ("brand_safety_review", "brand safety agent"),
        ("brandbook_compliance_review", "brandbook compliance agent"),
        ("rubric_scoring", "rubric scoring agent"),
        ("final_recommendation", "final diagnostic recommendation"),
    ]:
        if key in lowered:
            stage = name
            break
    payloads = {
        "creative_summary": {
            "summary": "Synthetic fixture summary with complete visual evidence.",
            "key_message": "Everyday support",
            "tone": "calm",
            "target_audience_vibe": "adults",
            "confidence": 0.8,
            "evidence_scope": "mixed",
            "visual_evidence_refs": ["ref_cta_001", "ref_brand_001"],
        },
        "audience_simulation": {
            "reaction": "Neutral, evidence-bound reaction.",
            "positive_triggers": ["ref_brand_001"],
            "objections": ["None recorded"],
            "engagement_probability": 6,
            "confidence": 0.7,
            "evidence_scope": "mixed",
            "visual_evidence_refs": ["ref_brand_001"],
        },
        "brand_safety_review": {
            "overall_risk_level": "low",
            "risks": [],
            "brand_fit_score": 8.0,
            "claims_compliance": "compliant",
            "confidence": 0.8,
            "evidence_scope": "non_visual",
            "visual_evidence_refs": [],
        },
        "brandbook_compliance_review": {
            "overall_verdict": "compliant",
            "violations": [],
            "recommendations": [],
            "compliance_score": 8.0,
        },
        "rubric_scoring": {
            "scorecard": [
                {
                    "criterion": "message_clarity",
                    "score": 7.5,
                    "rationale": "Clear message.",
                    "confidence": 0.8,
                }
            ],
            "overall_score": 7.5,
            "strengths": ["Clear message"],
            "weaknesses": [],
        },
        "final_recommendation": {
            "final_recommendation": "revise",
            "rationale": "Evidence is sufficient but requires review.",
            "top_actions": ["Review visual evidence"],
            "confidence": "medium",
        },
        "unknown": {"status": "fixture"},
    }
    return json.dumps(payloads.get(stage, payloads["unknown"]), ensure_ascii=False)
