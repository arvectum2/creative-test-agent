"""Execution, aggregation, and reporting for local vision benchmarks."""

from __future__ import annotations

import csv
import json
import os
import platform
import statistics
import time
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.shared.vision.benchmarking import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    CandidateOutput,
    VisionBenchmarkCandidate,
    _json_dump,
    _load_pack,
    _peak_rss_bytes,
    _sha_file,
    _total_memory_bytes,
    consensus_observations,
    expected_visible_text,
    harmonic_mean,
    observation_repeatability,
    score_observations,
    score_text,
    scored_expected_observations,
    text_repeatability,
)

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


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


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
