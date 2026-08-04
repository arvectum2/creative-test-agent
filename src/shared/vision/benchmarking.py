from __future__ import annotations

import base64
import csv
import hashlib
import itertools
import json
import math
import os
import platform
import re
import statistics
import time
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.shared.security.hardening import is_loopback_url
from src.shared.vision.ocr import LocalOcrAnalyzer

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None

BENCHMARK_ID = "local-vision-golden-pack-benchmark"
BENCHMARK_VERSION = "1.0.0"
ALLOWED_STATUSES = {"present", "absent", "review_required", "uncertain"}
EVIDENCE_ONLY_OBSERVABLES = {
    "brand_is_fictional",
    "market_effectiveness_not_evaluated",
    "real_respondent_evidence",
}
TOKEN_PATTERN = re.compile(r"[\w%]+", flags=re.UNICODE)


@dataclass(frozen=True)
class CandidateOutput:
    detected_text: str = ""
    observations: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    abstained: bool = False
    error: str | None = None


class VisionBenchmarkCandidate(ABC):
    candidate_id: str
    candidate_type: str
    model: str | None = None
    harness_only: bool = False

    @abstractmethod
    def analyze(self, image_path: Path, case: dict[str, Any]) -> CandidateOutput:
        raise NotImplementedError


class GoldenContractFixtureCandidate(VisionBenchmarkCandidate):
    """Harness self-test only. It must never be ranked as a model candidate."""

    candidate_id = "fixture:golden-contract"
    candidate_type = "fixture"
    model = None
    harness_only = True

    def analyze(self, image_path: Path, case: dict[str, Any]) -> CandidateOutput:
        del image_path
        return CandidateOutput(
            detected_text=expected_visible_text(case),
            observations=scored_expected_observations(case),
            metadata={"fixture_contract": True},
        )


class OcrCandidate(VisionBenchmarkCandidate):
    candidate_id = "ocr:tesseract"
    candidate_type = "ocr"
    model = "tesseract"
    harness_only = False

    def __init__(self) -> None:
        self._analyzer = LocalOcrAnalyzer()

    def analyze(self, image_path: Path, case: dict[str, Any]) -> CandidateOutput:
        result = self._analyzer.analyze_image(
            str(image_path),
            {"case_id": case["case_id"], "benchmark_id": BENCHMARK_ID},
        )
        warnings = list(result.warnings)
        unavailable = any(
            warning.startswith("local_ocr_unavailable") or warning.startswith("local_ocr_failed")
            for warning in warnings
        )
        return CandidateOutput(
            detected_text=result.detected_text,
            warnings=warnings,
            metadata=dict(result.metadata),
            abstained=unavailable or not normalize_tokens(result.detected_text),
        )


class OllamaVlmCandidate(VisionBenchmarkCandidate):
    candidate_type = "vlm"
    harness_only = False

    def __init__(self, model: str, base_url: str, timeout_seconds: int = 120) -> None:
        if not model.strip():
            raise ValueError("A local VLM model name is required.")
        normalized_url = base_url.rstrip("/")
        if not is_loopback_url(normalized_url):
            raise ValueError("Vision benchmark endpoints must be loopback-only.")
        self.model = model.strip()
        self.base_url = normalized_url
        self.timeout_seconds = max(int(timeout_seconds), 1)
        self.candidate_id = f"vlm:{self.model}"

    def analyze(self, image_path: Path, case: dict[str, Any]) -> CandidateOutput:
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        observables = sorted(scored_expected_observations(case))
        prompt = _vlm_prompt(observables)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0, "seed": 0},
        }
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            response_data = response.json()
            content = str(response_data.get("message", {}).get("content", ""))
            parsed = parse_json_object(content)
            observations, warnings = normalize_observations(
                parsed.get("observations"), observables
            )
            detected_text = str(parsed.get("detected_text", ""))
            metadata = {
                "vlm_model": self.model,
                "raw_response_length": len(content),
                "raw_response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "server_total_duration_ns": response_data.get("total_duration"),
                "server_load_duration_ns": response_data.get("load_duration"),
                "server_prompt_eval_count": response_data.get("prompt_eval_count"),
                "server_prompt_eval_duration_ns": response_data.get("prompt_eval_duration"),
                "server_eval_count": response_data.get("eval_count"),
                "server_eval_duration_ns": response_data.get("eval_duration"),
            }
            abstained = all(value == "uncertain" for value in observations.values())
            return CandidateOutput(
                detected_text=detected_text,
                observations=observations,
                warnings=warnings,
                metadata=metadata,
                abstained=abstained,
            )
        except Exception as exc:
            return CandidateOutput(
                warnings=["local_vlm_unavailable"],
                metadata={"vlm_model": self.model},
                abstained=True,
                error=f"{type(exc).__name__}: {exc}",
            )


class HybridCandidate(VisionBenchmarkCandidate):
    candidate_type = "hybrid"
    harness_only = False

    def __init__(self, model: str, base_url: str, timeout_seconds: int = 120) -> None:
        self._ocr = OcrCandidate()
        self._vlm = OllamaVlmCandidate(model, base_url, timeout_seconds)
        self.model = model
        self.candidate_id = f"hybrid:tesseract+{model}"

    def analyze(self, image_path: Path, case: dict[str, Any]) -> CandidateOutput:
        ocr = self._ocr.analyze(image_path, case)
        vlm = self._vlm.analyze(image_path, case)
        return CandidateOutput(
            detected_text=ocr.detected_text or vlm.detected_text,
            observations=vlm.observations,
            warnings=sorted(set(ocr.warnings + vlm.warnings)),
            metadata={"ocr": ocr.metadata, "vlm": vlm.metadata},
            abstained=ocr.abstained and vlm.abstained,
            error=vlm.error,
        )


def parse_candidate(
    value: str,
    *,
    base_url: str | None,
    timeout_seconds: int = 120,
    allow_fixture: bool = False,
) -> VisionBenchmarkCandidate:
    normalized = value.strip()
    if normalized in {"ocr", "ocr:tesseract"}:
        return OcrCandidate()
    if normalized in {"fixture", "fixture:golden-contract"}:
        if not allow_fixture:
            raise ValueError("The golden-contract fixture is restricted to harness self-tests.")
        return GoldenContractFixtureCandidate()
    prefix, separator, model = normalized.partition(":")
    if prefix not in {"vlm", "hybrid"} or not separator or not model.strip():
        raise ValueError(
            "Candidate must be ocr:tesseract, vlm:<local-model>, or hybrid:<local-model>."
        )
    if not base_url:
        raise ValueError("A loopback --base-url is required for VLM and hybrid candidates.")
    if prefix == "vlm":
        return OllamaVlmCandidate(model, base_url, timeout_seconds)
    return HybridCandidate(model, base_url, timeout_seconds)


def _vlm_prompt(observables: list[str]) -> str:
    catalog = ", ".join(observables)
    return (
        "Analyze this fictional marketing creative for a local benchmark. "
        "Do not estimate CTR, market effectiveness, lift, or respondent reaction. "
        "Return JSON only with keys detected_text, observations, and notes. "
        "observations must contain every requested observable and use exactly one of "
        "present, absent, review_required, uncertain. Use uncertain when the image is "
        "insufficient. Requested observables: "
        f"{catalog}."
    )


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def normalize_observations(
    raw: Any, requested: list[str]
) -> tuple[dict[str, str], list[str]]:
    source = raw if isinstance(raw, dict) else {}
    result: dict[str, str] = {}
    warnings: list[str] = []
    for observable in requested:
        value = str(source.get(observable, "uncertain")).strip().casefold()
        if value not in ALLOWED_STATUSES:
            warnings.append(f"invalid_status:{observable}")
            value = "uncertain"
        result[observable] = value
    unknown = sorted(set(source) - set(requested))
    if unknown:
        warnings.append("unexpected_observables:" + ",".join(unknown))
    return result, warnings


def scored_expected_observations(case: dict[str, Any]) -> dict[str, str]:
    expected = case.get("expected_observations") or {}
    return {
        key: value
        for key, value in expected.items()
        if key not in EVIDENCE_ONLY_OBSERVABLES and value in ALLOWED_STATUSES
    }


def expected_visible_text(case: dict[str, Any]) -> str:
    render = case.get("render") or {}
    values: list[str] = []
    if render.get("show_brand", True):
        values.append(str(render.get("brand", "")))
    values.extend([str(render.get("headline", "")), str(render.get("body", ""))])
    if render.get("show_cta", True):
        values.append(str(render.get("cta", "")))
    if render.get("show_claim_source", False):
        values.append(str(render.get("claim_source", "")))
    if render.get("pressure_badge"):
        values.append(str(render["pressure_badge"]))
    if render.get("show_disclaimer", True):
        values.append(str(render.get("disclaimer", "")))
    if render.get("text_density") == "high":
        values.extend(
            [
                "Detailed feature one with supporting explanation.",
                "Detailed feature two with another explanation.",
                "Conditions, exceptions, context and additional notes.",
                "Multiple secondary messages compete for attention.",
            ]
        )
    return "\n".join(value for value in values if value.strip())


def normalize_tokens(text: str) -> list[str]:
    return [token.strip("_") for token in TOKEN_PATTERN.findall(text.casefold()) if token.strip("_")]


def score_text(expected_text: str, detected_text: str) -> dict[str, Any]:
    expected = Counter(normalize_tokens(expected_text))
    detected = Counter(normalize_tokens(detected_text))
    overlap = sum((expected & detected).values())
    expected_count = sum(expected.values())
    detected_count = sum(detected.values())
    precision = overlap / detected_count if detected_count else 0.0
    recall = overlap / expected_count if expected_count else 1.0
    return {
        "expected_token_count": expected_count,
        "detected_token_count": detected_count,
        "matched_token_count": overlap,
        "precision": precision,
        "recall": recall,
        "f1": harmonic_mean(precision, recall),
        "abstained": detected_count == 0,
    }


def score_observations(
    expected: dict[str, str], predicted: dict[str, str]
) -> dict[str, Any]:
    total = len(expected)
    answered = 0
    correct = 0
    confusion: dict[str, int] = defaultdict(int)
    details: dict[str, dict[str, Any]] = {}
    for observable, gold in sorted(expected.items()):
        guess = predicted.get(observable, "uncertain")
        abstained = guess == "uncertain"
        if not abstained:
            answered += 1
        if guess == gold:
            correct += 1
        confusion[f"{gold}->{guess}"] += 1
        details[observable] = {
            "expected": gold,
            "predicted": guess,
            "correct": guess == gold,
            "abstained": abstained,
        }
    precision = correct / answered if answered else 0.0
    recall = correct / total if total else 1.0
    return {
        "evaluated_slots": total,
        "answered_slots": answered,
        "correct_slots": correct,
        "precision": precision,
        "recall": recall,
        "f1": harmonic_mean(precision, recall),
        "exact_accuracy": correct / total if total else 1.0,
        "abstention_rate": (total - answered) / total if total else 0.0,
        "confusion": dict(sorted(confusion.items())),
        "details": details,
    }


def harmonic_mean(left: float, right: float) -> float:
    return 2 * left * right / (left + right) if left + right else 0.0


def consensus_observations(
    outputs: list[CandidateOutput], expected_keys: list[str]
) -> dict[str, str]:
    consensus: dict[str, str] = {}
    for observable in expected_keys:
        values = [
            output.observations.get(observable, "uncertain")
            for output in outputs
            if output.error is None
        ]
        if not values:
            consensus[observable] = "uncertain"
            continue
        counts = Counter(values)
        top = counts.most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            consensus[observable] = "uncertain"
        else:
            consensus[observable] = top[0][0]
    return consensus


def observation_repeatability(
    outputs: list[CandidateOutput], expected_keys: list[str]
) -> dict[str, Any]:
    if len(outputs) < 2:
        return {
            "repeat_count": len(outputs),
            "slot_modal_agreement": 1.0,
            "case_exact_repeat": True,
        }
    modal_scores: list[float] = []
    normalized_runs: list[tuple[tuple[str, str], ...]] = []
    for observable in expected_keys:
        values = [output.observations.get(observable, "uncertain") for output in outputs]
        modal_scores.append(max(Counter(values).values()) / len(values))
    for output in outputs:
        normalized_runs.append(
            tuple(
                (key, output.observations.get(key, "uncertain"))
                for key in sorted(expected_keys)
            )
        )
    return {
        "repeat_count": len(outputs),
        "slot_modal_agreement": statistics.fmean(modal_scores) if modal_scores else 1.0,
        "case_exact_repeat": len(set(normalized_runs)) == 1,
    }


def text_repeatability(outputs: list[CandidateOutput]) -> dict[str, Any]:
    texts = [" ".join(normalize_tokens(output.detected_text)) for output in outputs]
    if len(texts) < 2:
        return {
            "repeat_count": len(texts),
            "exact_repeat": True,
            "mean_pairwise_token_jaccard": 1.0,
        }
    similarities: list[float] = []
    for left, right in itertools.combinations(texts, 2):
        left_tokens, right_tokens = set(left.split()), set(right.split())
        union = left_tokens | right_tokens
        similarities.append(len(left_tokens & right_tokens) / len(union) if union else 1.0)
    return {
        "repeat_count": len(texts),
        "exact_repeat": len(set(texts)) == 1,
        "mean_pairwise_token_jaccard": statistics.fmean(similarities),
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(max(math.ceil(fraction * len(ordered)) - 1, 0), len(ordered) - 1)
    return ordered[index]


def _peak_rss_bytes() -> int | None:
    if resource is None:
        return None
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if platform.system() == "Darwin" else value * 1024


def _total_memory_bytes() -> int | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages) * int(page_size)
    except (AttributeError, OSError, ValueError):
        return None


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_pack(pack_dir: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    spec_path = pack_dir / "pack_spec.json"
    manifest_path = pack_dir / "generated_manifest.json"
    if not spec_path.is_file() or not manifest_path.is_file():
        raise ValueError("Golden pack metadata is missing. Generate PRE-PILOT-002 first.")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = spec.get("cases")
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("Golden pack must contain 24 expanded cases.")
    manifest_cases = {
        item["case_id"]: item
        for item in manifest.get("cases", [])
        if isinstance(item, dict) and item.get("case_id")
    }
    for case in cases:
        entry = manifest_cases.get(case.get("case_id"))
        if entry is None:
            raise ValueError(f"Golden pack manifest is missing {case.get('case_id')}.")
        image_path = pack_dir / str(entry.get("filename", ""))
        if not image_path.is_file() or _sha_file(image_path) != entry.get("sha256"):
            raise ValueError(f"Golden pack integrity failed for {case.get('case_id')}.")
    return spec, manifest, sorted(cases, key=lambda item: item["case_id"])

from src.shared.vision.benchmark_execution import (
    aggregate_observation_scores,
    aggregate_repeatability,
    aggregate_text_scores,
    render_markdown_report,
    run_benchmark,
    summarize_candidate,
    summarize_per_observable,
    validate_benchmark,
)

