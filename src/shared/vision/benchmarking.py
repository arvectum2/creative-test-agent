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


def run_benchmark(
    *,
    pack_dir: Path,
    output_dir: Path,
    candidates: list[VisionBenchmarkCandidate],
    repeats: int = 2,
    case_limit: int | None = None,
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("At least one benchmark candidate is required.")
    if repeats < 1 or repeats > 10:
        raise ValueError("repeats must be between 1 and 10.")
    spec, manifest, cases = _load_pack(pack_dir)
    if case_limit is not None:
        if case_limit < 1:
            raise ValueError("case_limit must be positive.")
        cases = cases[:case_limit]
    manifest_cases = {item["case_id"]: item for item in manifest["cases"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_results: list[dict[str, Any]] = []

    for candidate in candidates:
        records: list[dict[str, Any]] = []
        by_case: dict[str, list[CandidateOutput]] = defaultdict(list)
        latency_values: list[float] = []
        cpu_values: list[float] = []
        for case in cases:
            image_path = pack_dir / manifest_cases[case["case_id"]]["filename"]
            for repeat_index in range(repeats):
                started = time.perf_counter()
                cpu_started = time.process_time()
                rss_before = _peak_rss_bytes()
                try:
                    output = candidate.analyze(image_path, case)
                except Exception as exc:  # pragma: no cover - defensive adapter boundary
                    output = CandidateOutput(
                        abstained=True,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                latency_ms = (time.perf_counter() - started) * 1000
                cpu_ms = (time.process_time() - cpu_started) * 1000
                rss_after = _peak_rss_bytes()
                latency_values.append(latency_ms)
                cpu_values.append(cpu_ms)
                by_case[case["case_id"]].append(output)
                records.append(
                    {
                        "case_id": case["case_id"],
                        "pair_id": case["pair_id"],
                        "repeat_index": repeat_index + 1,
                        "latency_ms": latency_ms,
                        "runner_cpu_ms": cpu_ms,
                        "runner_peak_rss_bytes_before": rss_before,
                        "runner_peak_rss_bytes_after": rss_after,
                        "output": asdict(output),
                    }
                )
        summary = summarize_candidate(candidate, cases, by_case, latency_values, cpu_values)
        candidate_results.append(
            {
                "candidate": {
                    "candidate_id": candidate.candidate_id,
                    "candidate_type": candidate.candidate_type,
                    "model": candidate.model,
                    "harness_only": candidate.harness_only,
                },
                "summary": summary,
                "records": records,
            }
        )

    result = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "golden_pack": {
            "pack_id": manifest.get("pack_id"),
            "pack_version": manifest.get("pack_version"),
            "spec_sha256": manifest.get("spec_sha256"),
            "manifest_sha256": _sha_file(pack_dir / "generated_manifest.json"),
            "case_count": len(cases),
            "full_pack_case_count": manifest.get("case_count"),
        },
        "execution": {
            "repeats": repeats,
            "case_limit": case_limit,
            "runner_resource_scope": "benchmark_process_only",
            "external_model_server_memory_included": False,
            "system": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "processor": platform.processor(),
                "logical_cpu_count": os.cpu_count(),
                "total_memory_bytes": _total_memory_bytes(),
            },
        },
        "evidence_boundary": {
            "synthetic_creatives_only": True,
            "market_effectiveness_not_evaluated": True,
            "real_respondents_used": False,
            "prediction_generated": False,
            "model_selected": False,
            "selection_decision": "manual_review_required_after_real_candidate_runs",
            "harness_fixture_excluded_from_selection": True,
        },
        "candidates": candidate_results,
    }
    results_path = output_dir / "benchmark_results.json"
    _json_dump(results_path, result)
    _write_summary_csv(output_dir / "benchmark_summary.csv", candidate_results)
    (output_dir / "benchmark_report.md").write_text(
        render_markdown_report(result), encoding="utf-8"
    )
    artifact_names = [
        "benchmark_results.json",
        "benchmark_summary.csv",
        "benchmark_report.md",
    ]
    benchmark_manifest = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "artifacts": [
            {
                "filename": name,
                "sha256": _sha_file(output_dir / name),
                "size_bytes": (output_dir / name).stat().st_size,
            }
            for name in artifact_names
        ],
    }
    _json_dump(output_dir / "benchmark_manifest.json", benchmark_manifest)
    return result


def summarize_candidate(
    candidate: VisionBenchmarkCandidate,
    cases: list[dict[str, Any]],
    by_case: dict[str, list[CandidateOutput]],
    latency_values: list[float],
    cpu_values: list[float],
) -> dict[str, Any]:
    first_text_scores: list[dict[str, Any]] = []
    first_observation_scores: list[dict[str, Any]] = []
    consensus_scores: list[dict[str, Any]] = []
    text_repeat_scores: list[dict[str, Any]] = []
    observation_repeat_scores: list[dict[str, Any]] = []
    per_observable: dict[str, dict[str, int]] = defaultdict(
        lambda: {"evaluated": 0, "answered": 0, "correct": 0}
    )
    successful_runs = 0
    total_runs = sum(len(outputs) for outputs in by_case.values())

    for case in cases:
        outputs = by_case[case["case_id"]]
        successful_runs += sum(output.error is None and not output.abstained for output in outputs)
        first = next((output for output in outputs if output.error is None), outputs[0])
        if candidate.candidate_type in {"ocr", "hybrid", "fixture"}:
            first_text_scores.append(
                score_text(expected_visible_text(case), first.detected_text)
            )
            text_repeat_scores.append(text_repeatability(outputs))
        if candidate.candidate_type in {"vlm", "hybrid", "fixture"}:
            expected = scored_expected_observations(case)
            first_score = score_observations(expected, first.observations)
            first_observation_scores.append(first_score)
            consensus = consensus_observations(outputs, sorted(expected))
            consensus_score = score_observations(expected, consensus)
            consensus_scores.append(consensus_score)
            observation_repeat_scores.append(
                observation_repeatability(outputs, sorted(expected))
            )
            for observable, detail in consensus_score["details"].items():
                aggregate = per_observable[observable]
                aggregate["evaluated"] += 1
                if not detail["abstained"]:
                    aggregate["answered"] += 1
                if detail["correct"]:
                    aggregate["correct"] += 1

    status = (
        "unavailable"
        if successful_runs == 0
        else "complete"
        if successful_runs == total_runs
        else "partial"
    )
    return {
        "status": status,
        "run_count": total_runs,
        "successful_non_abstained_run_count": successful_runs,
        "latency_ms": {
            "mean": statistics.fmean(latency_values) if latency_values else None,
            "p50": _percentile(latency_values, 0.50),
            "p95": _percentile(latency_values, 0.95),
            "max": max(latency_values) if latency_values else None,
        },
        "runner_cpu_ms": {
            "mean": statistics.fmean(cpu_values) if cpu_values else None,
            "p95": _percentile(cpu_values, 0.95),
        },
        "text_quality_first_pass": aggregate_text_scores(first_text_scores),
        "text_repeatability": aggregate_repeatability(
            text_repeat_scores, "exact_repeat", "mean_pairwise_token_jaccard"
        ),
        "observation_quality_first_pass": aggregate_observation_scores(
            first_observation_scores
        ),
        "observation_quality_consensus": aggregate_observation_scores(
            consensus_scores
        ),
        "observation_repeatability": aggregate_repeatability(
            observation_repeat_scores, "case_exact_repeat", "slot_modal_agreement"
        ),
        "per_observable_consensus": summarize_per_observable(per_observable),
        "eligible_for_model_selection": not candidate.harness_only and status != "unavailable",
        "automatic_selection_performed": False,
    }


def aggregate_text_scores(scores: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not scores:
        return None
    expected = sum(item["expected_token_count"] for item in scores)
    detected = sum(item["detected_token_count"] for item in scores)
    matched = sum(item["matched_token_count"] for item in scores)
    precision = matched / detected if detected else 0.0
    recall = matched / expected if expected else 1.0
    return {
        "case_count": len(scores),
        "expected_token_count": expected,
        "detected_token_count": detected,
        "matched_token_count": matched,
        "precision": precision,
        "recall": recall,
        "f1": harmonic_mean(precision, recall),
        "case_abstention_rate": sum(item["abstained"] for item in scores) / len(scores),
    }


def aggregate_observation_scores(
    scores: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not scores:
        return None
    total = sum(item["evaluated_slots"] for item in scores)
    answered = sum(item["answered_slots"] for item in scores)
    correct = sum(item["correct_slots"] for item in scores)
    precision = correct / answered if answered else 0.0
    recall = correct / total if total else 1.0
    return {
        "case_count": len(scores),
        "evaluated_slots": total,
        "answered_slots": answered,
        "correct_slots": correct,
        "precision": precision,
        "recall": recall,
        "f1": harmonic_mean(precision, recall),
        "exact_accuracy": correct / total if total else 1.0,
        "abstention_rate": (total - answered) / total if total else 0.0,
    }


def aggregate_repeatability(
    scores: list[dict[str, Any]], exact_key: str, agreement_key: str
) -> dict[str, Any] | None:
    if not scores:
        return None
    return {
        "case_count": len(scores),
        "exact_repeat_rate": sum(bool(item[exact_key]) for item in scores) / len(scores),
        "mean_agreement": statistics.fmean(float(item[agreement_key]) for item in scores),
    }


def summarize_per_observable(
    per_observable: dict[str, dict[str, int]]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for observable, counts in sorted(per_observable.items()):
        answered = counts["answered"]
        total = counts["evaluated"]
        correct = counts["correct"]
        precision = correct / answered if answered else 0.0
        recall = correct / total if total else 1.0
        result[observable] = {
            **counts,
            "precision": precision,
            "recall": recall,
            "f1": harmonic_mean(precision, recall),
            "abstention_rate": (total - answered) / total if total else 0.0,
        }
    return result


def _write_summary_csv(path: Path, candidate_results: list[dict[str, Any]]) -> None:
    fields = [
        "candidate_id",
        "candidate_type",
        "model",
        "harness_only",
        "status",
        "eligible_for_model_selection",
        "latency_mean_ms",
        "latency_p95_ms",
        "text_precision",
        "text_recall",
        "text_f1",
        "observation_precision",
        "observation_recall",
        "observation_f1",
        "observation_abstention_rate",
        "observation_repeatability",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in candidate_results:
            candidate, summary = item["candidate"], item["summary"]
            text = summary.get("text_quality_first_pass") or {}
            observations = summary.get("observation_quality_consensus") or {}
            repeatability = summary.get("observation_repeatability") or {}
            writer.writerow(
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_type": candidate["candidate_type"],
                    "model": candidate.get("model") or "",
                    "harness_only": candidate["harness_only"],
                    "status": summary["status"],
                    "eligible_for_model_selection": summary["eligible_for_model_selection"],
                    "latency_mean_ms": summary["latency_ms"]["mean"],
                    "latency_p95_ms": summary["latency_ms"]["p95"],
                    "text_precision": text.get("precision", ""),
                    "text_recall": text.get("recall", ""),
                    "text_f1": text.get("f1", ""),
                    "observation_precision": observations.get("precision", ""),
                    "observation_recall": observations.get("recall", ""),
                    "observation_f1": observations.get("f1", ""),
                    "observation_abstention_rate": observations.get("abstention_rate", ""),
                    "observation_repeatability": repeatability.get("mean_agreement", ""),
                }
            )


def render_markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Local Vision Golden Pack Benchmark",
        "",
        f"- Benchmark version: `{result['benchmark_version']}`",
        f"- Golden pack: `{result['golden_pack']['pack_id']}` `{result['golden_pack']['pack_version']}`",
        f"- Cases: {result['golden_pack']['case_count']}",
        f"- Repeats: {result['execution']['repeats']}",
        "- Model selected: no",
        "- Decision: manual review required after real local candidate runs",
        "",
        "This report measures synthetic observable recognition and text extraction only. "
        "It does not establish CTR, lift, market effectiveness, respondent reaction, "
        "pharmaceutical compliance, or client-level accuracy.",
        "",
        "## Candidate summary",
        "",
        "| Candidate | Type | Status | Harness only | Latency p95 ms | Text F1 | Observable F1 | Abstention | Repeatability |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in result["candidates"]:
        candidate, summary = item["candidate"], item["summary"]
        text = summary.get("text_quality_first_pass") or {}
        observations = summary.get("observation_quality_consensus") or {}
        repeatability = summary.get("observation_repeatability") or {}
        lines.append(
            "| {candidate_id} | {candidate_type} | {status} | {harness_only} | "
            "{latency} | {text_f1} | {obs_f1} | {abstention} | {repeatability} |".format(
                candidate_id=candidate["candidate_id"],
                candidate_type=candidate["candidate_type"],
                status=summary["status"],
                harness_only="yes" if candidate["harness_only"] else "no",
                latency=_fmt(summary["latency_ms"]["p95"]),
                text_f1=_fmt(text.get("f1")),
                obs_f1=_fmt(observations.get("f1")),
                abstention=_fmt(observations.get("abstention_rate")),
                repeatability=_fmt(repeatability.get("mean_agreement")),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "- The golden-contract fixture validates the benchmark harness and is excluded from model selection.",
            "- OCR metrics use visible synthetic text tokens.",
            "- VLM metrics use only explicitly labelled observable slots.",
            "- `uncertain` and missing observations count as abstentions.",
            "- Runner RSS excludes memory consumed by a separate local model server.",
            "- No automatic winner or approval threshold is applied.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:.4f}"
    return str(value)


def validate_benchmark(output_dir: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = output_dir / "benchmark_manifest.json"
    results_path = output_dir / "benchmark_results.json"
    if not manifest_path.is_file() or not results_path.is_file():
        return ["benchmark_manifest.json or benchmark_results.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        results = json.loads(results_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"benchmark metadata is unreadable: {exc}"]
    if manifest.get("benchmark_id") != BENCHMARK_ID:
        errors.append("unexpected benchmark identity")
    for artifact in manifest.get("artifacts", []):
        path = output_dir / str(artifact.get("filename", ""))
        if not path.is_file():
            errors.append(f"missing benchmark artifact: {path.name}")
        elif _sha_file(path) != artifact.get("sha256"):
            errors.append(f"benchmark artifact SHA-256 mismatch: {path.name}")
    boundary = results.get("evidence_boundary") or {}
    if boundary.get("model_selected") is not False:
        errors.append("PRE-PILOT-003 must not auto-select a model")
    if boundary.get("prediction_generated") is not False:
        errors.append("benchmark must not claim a generated prediction")
    if boundary.get("real_respondents_used") is not False:
        errors.append("benchmark must not claim real respondents")
    if boundary.get("market_effectiveness_not_evaluated") is not True:
        errors.append("market-effectiveness boundary is missing")
    candidates = results.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("benchmark must contain at least one candidate result")
    return errors
