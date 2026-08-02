"""CTA-BENCH-002 benchmark orchestrator.

Runs the candidate matrix (OCR/VLM/LLM/hybrid) against the frozen case sets,
manages server lifecycle per the launch protocol, measures cold/warm/single/
concurrency latency, samples resources, audits process cleanup and produces the
full section-18 artifact set under artifacts/cta-bench-002/<revision>/.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.shared.llm.stage_processor import process_stage_output
from src.shared.security.hardening import is_loopback_url

from scripts.cta_bench_002 import llm_cases, metrics, runtime, visual_cases
from scripts.cta_bench_002.clients import (
    AppProfileLlmBenchmarkClient,
    EndpointError,
    LlmBenchmarkClient,
    PaddleOcrBenchmarkClient,
    TesseractBenchmarkClient,
    VlmBenchmarkClient,
)
from scripts.cta_bench_002.environment import write_environment
from scripts.cta_bench_002.spec import (
    DEFAULT_CONCURRENCY,
    DEFAULT_REPEATS,
    DEFAULT_TIMEOUT_SECONDS,
    LOOPBACK,
    PORT_LLM_MLX_4B,
    PORT_LLM_MLX_9B,
    PORT_VLM_BASE_LLAMA,
    PORT_VLM_MLX_4B,
    PORT_VLM_MLX_8B,
    SINGLE_REQUEST_CANDIDATES,
    TOPOLOGIES,
    TOPOLOGY_R_MIN_HEADROOM_FRACTION,
    WARMUP_CASE_COUNT,
)


# ---------------------------------------------------------------------------
# Prompt builders (frozen, mirror the production prompt contracts)
# ---------------------------------------------------------------------------

_VLM_OBSERVABLE_PROMPT = (
    "Analyze this fictional marketing creative for a local benchmark. "
    "Do not estimate CTR, market effectiveness, lift, or respondent reaction. "
    "Return JSON only with keys detected_text, observations, and notes. "
    "observations must contain every requested observable and use exactly one of "
    "present, absent, review_required, uncertain. Use uncertain when the image is "
    "insufficient. Requested observables: "
)


def _vlm_prompt(observables: list[str]) -> str:
    return _VLM_OBSERVABLE_PROMPT + ", ".join(sorted(observables)) + "."


def _llm_prompt(case: dict[str, Any]) -> str:
    from src.modules.test_runs.prompts import load_prompt

    stage = case["stage"]
    prompt_name = {
        "creative_summary": "creative_summary",
        "audience_simulation": "audience_simulation",
        "brand_safety_review": "brand_safety",
        "brandbook_compliance_review": "brandbook_compliance",
        "rubric_scoring": "rubric_scoring",
        "final_recommendation": "final_recommendation",
    }[stage]
    params = dict(case["params"])
    params.setdefault("visual_context", json.dumps(case["visual_evidence_envelope"]["visual_context"], ensure_ascii=False))
    return load_prompt(prompt_name, **params)


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------

def _load_visual_cases(pack_dir: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((pack_dir / "case_manifest_visual.json").read_text(encoding="utf-8"))
    spec = json.loads((pack_dir / "case_spec.json").read_text(encoding="utf-8"))
    cases = spec.get("cases") or []
    errors = visual_cases.validate_generated(pack_dir)
    if errors:
        raise ValueError("Invalid visual case set:\n- " + "\n- ".join(errors))
    return manifest, spec, sorted(cases, key=lambda item: item["case_id"])


def _load_llm_cases(pack_dir: Path) -> list[dict[str, Any]]:
    manifest = json.loads((pack_dir / "case_manifest_llm.json").read_text(encoding="utf-8"))
    errors = llm_cases.validate_manifest(pack_dir)
    if errors:
        raise ValueError("Invalid LLM case set:\n- " + "\n- ".join(errors))
    return manifest["cases"]


# ---------------------------------------------------------------------------
# Candidate client factory
# ---------------------------------------------------------------------------

def _client_for(candidate_id: str, base_url: str | None, model: str | None, timeout: int):
    if candidate_id == "OCR-TESSERACT":
        return TesseractBenchmarkClient()
    if candidate_id == "OCR-CHALLENGER":
        return PaddleOcrBenchmarkClient()
    if candidate_id == "LLM-CURRENT":
        return AppProfileLlmBenchmarkClient(provider_name="stub")
    if not base_url or not model:
        raise ValueError(f"{candidate_id} requires a loopback base_url and explicit model id")
    if not is_loopback_url(base_url):
        raise ValueError(f"{candidate_id} endpoint must be loopback-only: {base_url}")
    if candidate_id.startswith("VLM-"):
        return VlmBenchmarkClient(base_url=base_url, model=model, timeout_seconds=timeout)
    return LlmBenchmarkClient(base_url=base_url, model=model, timeout_seconds=timeout)


# ---------------------------------------------------------------------------
# Single-candidate visual run (OCR or VLM)
# ---------------------------------------------------------------------------

def _run_visual_candidate(
    candidate_id: str,
    client: Any,
    pack_dir: Path,
    cases: list[dict[str, Any]],
    repeats: int,
    warmup_case: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads((pack_dir / "case_manifest_visual.json").read_text(encoding="utf-8"))
    files = {item["case_id"]: item["filename"] for item in manifest["cases"]}
    runs: list[dict[str, Any]] = []
    per_case: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def one(image_path: Path, case: dict[str, Any], repeat_index: int, *, concurrency: int = 1) -> dict[str, Any]:
        observables = sorted(
            key for key, value in case["expected_observations"].items()
            if key not in {"brand_is_fictional", "market_effectiveness_not_evaluated", "real_respondent_evidence"}
        )
        prompt = _vlm_prompt(observables)
        started = time.perf_counter()
        if candidate_id == "OCR-TESSERACT" or candidate_id == "OCR-CHALLENGER":
            result = client.analyze_image(image_path, case["case_id"])
        else:
            result = client.analyze_image(image_path, prompt, stream=True)
        wall_ms = result.get("wall_ms") or (time.perf_counter() - started) * 1000
        content = result.get("content", "")
        if isinstance(content, list):
            content = " ".join(str(part) for part in content)
        parsed = metrics.parse_json_object(content) if candidate_id.startswith("VLM-") else {}
        observations: dict[str, str] = {}
        if candidate_id.startswith("VLM-"):
            for observable in observables:
                value = str((parsed.get("observations") or {}).get(observable, "uncertain")).strip().casefold()
                if value not in {"present", "absent", "review_required", "uncertain"}:
                    value = "uncertain"
                observations[observable] = value
        elif candidate_id == "OCR-TESSERACT":
            observations = {}
        run = {
            "candidate_id": candidate_id,
            "case_id": case["case_id"],
            "category": case.get("category"),
            "repeat_index": repeat_index,
            "wall_ms": wall_ms,
            "ttft_ms": result.get("ttft_ms"),
            "content": content,
            "raw_sha256": _sha_text(content),
            "detected_text": parsed.get("detected_text", content) if candidate_id.startswith("VLM-") else content,
            "observations": observations,
            "expected_observations": case["expected_observations"],
            "usage": result.get("usage") or {},
            "empty_chunks_before_content": result.get("empty_chunks_before_content", 0),
            "warnings": result.get("warnings") or [],
            "error": result.get("error"),
            "concurrency": concurrency,
            "stream": bool(result.get("stream")),
        }
        return run

    # Warm-up (not scored).
    if warmup_case is not None:
        image_path = pack_dir / files[warmup_case["case_id"]]
        try:
            one(image_path, warmup_case, 0, concurrency=1)
        except EndpointError:
            pass

    for case in cases:
        for repeat_index in range(1, repeats + 1):
            image_path = pack_dir / files[case["case_id"]]
            run = one(image_path, case, repeat_index, concurrency=1)
            runs.append(run)
            per_case[case["case_id"]].append(run)

    summary = _summarize_visual(candidate_id, cases, per_case, runs)
    return runs, summary


def _sha_text(content: str) -> str:
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _summarize_visual(
    candidate_id: str,
    cases: list[dict[str, Any]],
    per_case: dict[str, list[dict[str, Any]]],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    is_vlm = candidate_id.startswith("VLM-")
    is_ocr = candidate_id.startswith("OCR-")
    is_hybrid = candidate_id.startswith("HYBRID-")
    latencies = [run["wall_ms"] for run in runs if run.get("wall_ms") is not None]
    ttfts = [run["ttft_ms"] for run in runs if run.get("ttft_ms") is not None]
    text_scores: list[dict[str, Any]] = []
    obs_scores: list[dict[str, Any]] = []
    if is_vlm or is_hybrid:
        for case in cases:
            expected_text = _expected_visible_text(case)
            first = per_case[case["case_id"]][0]
            detected = first.get("detected_text", first.get("content", ""))
            text_scores.append(metrics.score_text(expected_text, detected))
            if first.get("observations"):
                obs_scores.append(metrics.score_observations(case["expected_observations"], first["observations"]))
    if is_ocr:
        for case in cases:
            expected_text = _expected_visible_text(case)
            first = per_case[case["case_id"]][0]
            text_scores.append(metrics.score_text(expected_text, first["content"]))

    repeatability = _repeatability(cases, per_case)
    failures = [run for run in runs if run.get("error")]
    success_rate = 1.0 - (len(failures) / len(runs)) if runs else 0.0
    return {
        "candidate_id": candidate_id,
        "candidate_type": "vlm" if is_vlm else ("ocr" if is_ocr else "hybrid"),
        "status": "complete" if success_rate == 1.0 else "partial",
        "run_count": len(runs),
        "success_rate": success_rate,
        "latency": metrics.latency_stats(latencies),
        "ttft": metrics.latency_stats(ttfts),
        "text_quality": _aggregate_text(text_scores) if text_scores else None,
        "observable_quality": _aggregate_obs(obs_scores) if obs_scores else None,
        "repeatability": repeatability,
    }


def _expected_visible_text(case: dict[str, Any]) -> str:
    overrides = case.get("render_overrides") or {}
    base = {
        "brand": "NOVALEN",
        "headline": "Everyday support, clearly explained",
        "body": "A fictional wellness product for synthetic testing only.",
        "cta": "LEARN MORE",
        "disclaimer": "Fictional product. Demo only. Not medical advice.",
    }
    merged = dict(base)
    merged.update(overrides)
    values: list[str] = []
    for key in ("brand", "headline", "body", "cta", "disclaimer"):
        value = str(merged.get(key, "")).strip()
        if value:
            values.append(value)
    if merged.get("text_density") == "high":
        values.extend(
            [
                "Detailed feature one with supporting explanation.",
                "Detailed feature two with another explanation.",
                "Conditions, exceptions, context and additional notes.",
                "Multiple secondary messages compete for attention.",
            ]
        )
    if merged.get("show_cta") is False:
        values = [value for value in values if value != "LEARN MORE"]
    if merged.get("show_disclaimer") is False:
        values = [value for value in values if "Fictional product. Demo only" not in value]
    return "\n".join(values)


def _aggregate_text(scores: list[dict[str, Any]]) -> dict[str, Any]:
    expected = sum(item["expected_token_count"] for item in scores)
    detected = sum(item["detected_token_count"] for item in scores)
    matched = sum(item["matched_token_count"] for item in scores)
    precision = matched / detected if detected else 0.0
    recall = matched / expected if expected else 1.0
    return {
        "case_count": len(scores),
        "precision": precision,
        "recall": recall,
        "f1": metrics.harmonic_mean(precision, recall),
        "case_abstention_rate": sum(item["abstained"] for item in scores) / len(scores),
    }


def _aggregate_obs(scores: list[dict[str, Any]]) -> dict[str, Any]:
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
        "f1": metrics.harmonic_mean(precision, recall),
        "abstention_rate": (total - answered) / total if total else 0.0,
    }


def _repeatability(cases: list[dict[str, Any]], per_case: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    if not cases:
        return {"case_count": 0}
    exact = 0
    agreements: list[float] = []
    for case in cases:
        runs = per_case[case["case_id"]]
        if len(runs) < 2:
            exact += 1
            agreements.append(1.0)
            continue
        contents = [run["content"] for run in runs]
        if len(set(contents)) == 1:
            exact += 1
        if case["expected_observations"]:
            keys = sorted(k for k in case["expected_observations"] if k not in {"brand_is_fictional", "market_effectiveness_not_evaluated", "real_respondent_evidence"})
            if keys:
                for observable in keys:
                    values = [run["observations"].get(observable, "uncertain") for run in runs]
                    agreements.append(max(Counter(values).values()) / len(values))
    return {
        "case_count": len(cases),
        "exact_text_repeat_rate": exact / len(cases),
        "slot_modal_agreement": statistics.fmean(agreements) if agreements else 1.0,
    }


# ---------------------------------------------------------------------------
# Single-candidate LLM run
# ---------------------------------------------------------------------------

def _run_llm_candidate(
    candidate_id: str,
    client: Any,
    cases: list[dict[str, Any]],
    repeats: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    per_case: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for case in cases:
        prompt = _llm_prompt(case)
        for repeat_index in range(1, repeats + 1):
            started = time.perf_counter()
            if candidate_id == "LLM-CURRENT":
                result = client.complete(prompt, stream=False)
                wall_ms = result.get("wall_ms") or (time.perf_counter() - started) * 1000
                content = result.get("content", "")
                ttft_ms = None
                usage = {}
            else:
                result = client.complete(prompt, stream=True)
                wall_ms = result.get("wall_ms") or (time.perf_counter() - started) * 1000
                content = result.get("content", "")
                ttft_ms = result.get("ttft_ms")
                usage = result.get("usage") or {}
            stage_processor = process_stage_output(
                stage_name=case["stage"],
                raw_response=content,
                prompt_text=prompt,
                latency_ms=wall_ms,
            )
            parsed = stage_processor.parsed_data or {}
            run = {
                "candidate_id": candidate_id,
                "case_id": case["case_id"],
                "stage": case["stage"],
                "repeat_index": repeat_index,
                "wall_ms": wall_ms,
                "ttft_ms": ttft_ms,
                "content": content,
                "raw_sha256": _sha_text(content),
                "parsed": parsed,
                "repair_used": stage_processor.repaired,
                "repair_steps": stage_processor.repair_steps,
                "validation_errors": stage_processor.validation_errors,
                "validation_warnings": stage_processor.validation_warnings,
                "fallback_used": stage_processor.fallback_used,
                "reference_ids_used": sorted(metrics.extract_reference_ids(content)),
                "expected_reference_ids": sorted(
                    ref["reference_id"]
                    for ref in (case["visual_evidence_envelope"]["visual_context"].get("references") or [])
                ),
                "usage": usage,
                "forbidden_claims_found": _find_forbidden_claims(content, case.get("forbidden_claims") or []),
                "input_language": case.get("input_language"),
                "stream": True,
            }
            runs.append(run)
            per_case[case["case_id"]].append(run)

    summary = _summarize_llm(candidate_id, cases, per_case, runs)
    return runs, summary


def _find_forbidden_claims(content: str, forbidden: list[str]) -> list[str]:
    lowered = content.casefold()
    found = []
    for claim in forbidden:
        if claim.casefold() in lowered:
            found.append(claim)
    return found


def _summarize_llm(
    candidate_id: str,
    cases: list[dict[str, Any]],
    per_case: dict[str, list[dict[str, Any]]],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    latencies = [run["wall_ms"] for run in runs if run.get("wall_ms") is not None]
    ttfts = [run["ttft_ms"] for run in runs if run.get("ttft_ms") is not None]
    schema_valid = sum(1 for run in runs if not run.get("validation_errors"))
    fallback_used = sum(1 for run in runs if run.get("fallback_used"))
    repaired = sum(1 for run in runs if run.get("repair_used"))
    forbidden_total = sum(len(run.get("forbidden_claims_found", [])) for run in runs)
    ref_missing = 0
    for run in runs:
        expected = run.get("expected_reference_ids") or []
        if expected and not set(expected) <= set(run.get("reference_ids_used", [])):
            ref_missing += 1
    return {
        "candidate_id": candidate_id,
        "candidate_type": "llm",
        "status": "complete",
        "run_count": len(runs),
        "case_count": len(cases),
        "schema_valid_rate": schema_valid / len(runs) if runs else 0.0,
        "fallback_rate": fallback_used / len(runs) if runs else 0.0,
        "repair_rate": repaired / len(runs) if runs else 0.0,
        "forbidden_claim_total": forbidden_total,
        "reference_missing_case_count": ref_missing,
        "latency": metrics.latency_stats(latencies),
        "ttft": metrics.latency_stats(ttfts),
    }


# ---------------------------------------------------------------------------
# Hybrid OCR + VLM
# ---------------------------------------------------------------------------

def _run_hybrid_candidate(
    vlm_candidate_id: str,
    ocr_client: Any,
    vlm_client: Any,
    pack_dir: Path,
    cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads((pack_dir / "case_manifest_visual.json").read_text(encoding="utf-8"))
    files = {item["case_id"]: item["filename"] for item in manifest["cases"]}
    runs: list[dict[str, Any]] = []
    per_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_id = f"HYBRID-OCR+{vlm_candidate_id}"

    for case in cases:
        image_path = pack_dir / files[case["case_id"]]
        observables = sorted(
            key for key, value in case["expected_observations"].items()
            if key not in {"brand_is_fictional", "market_effectiveness_not_evaluated", "real_respondent_evidence"}
        )
        prompt = _vlm_prompt(observables) + "\nOCR transcription (may be partial):\n"
        started = time.perf_counter()
        ocr_result = ocr_client.analyze_image(image_path, case["case_id"])
        ocr_text = ocr_result.get("content", "")
        # Pass OCR output to the VLM as an additional provenance-bound text input.
        vlm_payload = prompt + (ocr_text or "(no OCR text)")
        vlm_result = vlm_client.analyze_image(image_path, vlm_payload, stream=True)
        wall_ms = (time.perf_counter() - started) * 1000
        content = vlm_result.get("content", "")
        parsed = metrics.parse_json_object(content)
        observations = {}
        for observable in observables:
            value = str((parsed.get("observations") or {}).get(observable, "uncertain")).strip().casefold()
            if value not in {"present", "absent", "review_required", "uncertain"}:
                value = "uncertain"
            observations[observable] = value
        run = {
            "candidate_id": candidate_id,
            "case_id": case["case_id"],
            "repeat_index": 1,
            "wall_ms": wall_ms,
            "ttft_ms": vlm_result.get("ttft_ms"),
            "content": content,
            "ocr_transcription": ocr_text,
            "ocr_warnings": ocr_result.get("warnings") or [],
            "observations": observations,
            "expected_observations": case["expected_observations"],
            "usage": vlm_result.get("usage") or {},
            "stream": True,
        }
        runs.append(run)
        per_case[case["case_id"]].append(run)

    summary = _summarize_visual(candidate_id, cases, per_case, runs)
    summary["candidate_type"] = "hybrid"
    summary["vlm_candidate_id"] = vlm_candidate_id
    summary["ocr_candidate_id"] = "OCR-TESSERACT"
    return runs, summary


# ---------------------------------------------------------------------------
# Resource sampling wrapper
# ---------------------------------------------------------------------------

def _sampled_resource_rows(pids: list[int], seconds: float) -> list[dict[str, Any]]:
    sampler = metrics.ResourceSampler(interval=1.0)
    rows: list[dict[str, Any]] = []
    sampler.start(pids)
    end = time.time() + seconds
    while time.time() < end:
        sampler.tick(pids)
        time.sleep(1.0)
    rows = sampler.stop()
    return rows


def resource_csv_rows(rows: list[dict[str, Any]], candidate_id: str) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        out = dict(row)
        out["candidate_id"] = candidate_id
        result.append(out)
    return result


# ---------------------------------------------------------------------------
# Topology runs
# ---------------------------------------------------------------------------

def _run_topology_u(
    vlm_client: Any,
    llm_client: Any,
    pack_dir: Path,
    visual_cases: list[dict[str, Any]],
    llm_cases_list: list[dict[str, Any]],
) -> dict[str, Any]:
    """Unified model: VLM performs visual extraction AND text analytical stages."""
    started = time.perf_counter()
    visual_runs, visual_summary = _run_visual_candidate(
        "TOPOLOGY-U-VLM",
        vlm_client,
        pack_dir,
        visual_cases,
        repeats=1,
        warmup_case=None,
    )
    llm_runs, llm_summary = _run_llm_candidate("TOPOLOGY-U-LLM", llm_client, llm_cases_list, repeats=1)
    return {
        "topology": "TOPOLOGY-U",
        "wall_ms_total": (time.perf_counter() - started) * 1000,
        "visual_summary": visual_summary,
        "llm_summary": llm_summary,
        "visual_runs": visual_runs,
        "llm_runs": llm_runs,
    }


def _run_topology_s(
    vlm_client: Any,
    llm_client: Any,
    lifecycle: runtime.RuntimeLifecycle,
    launch_vlm: Any,
    launch_llm: Any,
    pack_dir: Path,
    visual_cases: list[dict[str, Any]],
    llm_cases_list: list[dict[str, Any]],
) -> dict[str, Any]:
    """Sequential dual model: VLM extraction, unload, LLM analytical stages."""
    started = time.perf_counter()
    lifecycle.launch(launch_vlm)
    visual_runs, visual_summary = _run_visual_candidate(
        "TOPOLOGY-S-VLM",
        vlm_client,
        pack_dir,
        visual_cases,
        repeats=1,
        warmup_case=None,
    )
    shutdown_vlm = lifecycle.shutdown()
    lifecycle.launch(launch_llm)
    llm_runs, llm_summary = _run_llm_candidate("TOPOLOGY-S-LLM", llm_client, llm_cases_list, repeats=1)
    shutdown_llm = lifecycle.shutdown()
    return {
        "topology": "TOPOLOGY-S",
        "wall_ms_total": (time.perf_counter() - started) * 1000,
        "visual_summary": visual_summary,
        "llm_summary": llm_summary,
        "visual_runs": visual_runs,
        "llm_runs": llm_runs,
        "vlm_shutdown_graceful": shutdown_vlm.shutdown_graceful,
        "llm_shutdown_graceful": shutdown_llm.shutdown_graceful,
    }


def _measure_seconds(func) -> float:
    started = time.perf_counter()
    func()
    return time.perf_counter() - started


def _run_topology_r(
    vlm_client: Any,
    llm_client: Any,
    lifecycle_vlm: runtime.RuntimeLifecycle,
    lifecycle_llm: runtime.RuntimeLifecycle,
    launch_vlm: Any,
    launch_llm: Any,
    pack_dir: Path,
    visual_cases: list[dict[str, Any]],
    llm_cases_list: list[dict[str, Any]],
    min_headroom_fraction: float = 0.20,
) -> dict[str, Any]:
    """Resident dual model: VLM and LLM stay loaded simultaneously.

    Measures both latencies under co-residency, then captures memory/swap
    pressure to decide whether TOPOLOGY-R is allowed per the headroom policy.
    """
    import subprocess

    started = time.perf_counter()
    errors: list[str] = []

    result_vlm = lifecycle_vlm.launch(launch_vlm)
    if not result_vlm.health_ok:
        errors.append(f"VLM failed health: {result_vlm.errors}")
        lifecycle_llm.shutdown()
        lifecycle_vlm.shutdown()
        return _topology_r_failure(started, errors)

    result_llm = lifecycle_llm.launch(launch_llm)
    if not result_llm.health_ok:
        errors.append(f"LLM failed health: {result_llm.errors}")
        lifecycle_llm.shutdown()
        lifecycle_vlm.shutdown()
        return _topology_r_failure(started, errors)

    visual_runs, visual_summary = _run_visual_candidate(
        "TOPOLOGY-R-VLM",
        vlm_client,
        pack_dir,
        visual_cases,
        repeats=1,
        warmup_case=None,
    )
    llm_runs, llm_summary = _run_llm_candidate("TOPOLOGY-R-LLM", llm_client, llm_cases_list, repeats=1)

    headroom, swap = _memory_pressure_audit()

    shutdown_vlm = lifecycle_vlm.shutdown()
    shutdown_llm = lifecycle_llm.shutdown()
    if not shutdown_vlm.shutdown_graceful and not shutdown_vlm.process_group_killed:
        errors.append("VLM process did not stop cleanly")
    if not shutdown_llm.shutdown_graceful and not shutdown_llm.process_group_killed:
        errors.append("LLM process did not stop cleanly")

    allowed = headroom >= min_headroom_fraction and not swap.get("thrashing", True)
    if not allowed:
        errors.append(
            f"headroom {headroom:.2f} < {min_headroom_fraction} or swap thrashing {swap.get('thrashing')}"
        )

    return {
        "topology": "TOPOLOGY-R",
        "wall_ms_total": (time.perf_counter() - started) * 1000,
        "visual_summary": visual_summary,
        "llm_summary": llm_summary,
        "visual_runs": visual_runs,
        "llm_runs": llm_runs,
        "headroom_fraction": headroom,
        "swap_pressure": swap,
        "allowed": allowed,
        "errors": errors,
        "vlm_shutdown_graceful": shutdown_vlm.shutdown_graceful,
        "llm_shutdown_graceful": shutdown_llm.shutdown_graceful,
        "residual_vlm": shutdown_vlm.residual_processes,
        "residual_llm": shutdown_llm.residual_processes,
    }


def _topology_r_failure(started: float, errors: list[str]) -> dict[str, Any]:
    return {
        "topology": "TOPOLOGY-R",
        "wall_ms_total": (time.perf_counter() - started) * 1000,
        "errors": errors,
        "visual_summary": {},
        "llm_summary": {},
        "visual_runs": [],
        "llm_runs": [],
        "headroom_fraction": 0.0,
        "swap_pressure": {"thrashing": True},
        "allowed": False,
    }


def _memory_pressure_audit() -> tuple[float, dict[str, Any]]:
    """Return (free_memory_fraction, swap_pressure). Uses vm_stat + swapusage."""
    import re
    import subprocess

    def _parse_key(text: str, key: str) -> int:
        m = re.search(rf"{re.escape(key)}\s*[:=]\s*([\d.]+)", text)
        return int(float(m.group(1))) if m else 0

    vm_text = ""
    swap_text = ""
    try:
        vm_text = subprocess.check_output(["vm_stat"], text=True, timeout=15)
    except Exception:
        pass
    try:
        swap_text = subprocess.check_output(["sysctl", "vm.swapusage"], text=True, timeout=15)
    except Exception:
        pass

    active = _parse_key(vm_text, "Pages active")
    free = _parse_key(vm_text, "Pages free")
    inactive = _parse_key(vm_text, "Pages inactive")
    speculative = _parse_key(vm_text, "Pages speculative")
    total_pages = active + free + inactive + speculative
    if total_pages <= 0:
        return 0.0, {"total_gb": 0.0, "used_gb": 0.0, "free_fraction": 0.0, "thrashing": True}

    page_size = _parse_key(vm_text, "page size of") or 16384
    swap_used = _parse_key(swap_text, "used")
    pageouts = _parse_key(vm_text, "pageouts")
    free_fraction = (free + inactive + speculative) / total_pages
    return free_fraction, {
        "total_gb": round(total_pages * page_size / (1024 ** 3), 2),
        "used_gb": round(active * page_size / (1024 ** 3), 2),
        "free_fraction": round(free_fraction, 3),
        "swap_used_gb": round(swap_used / 1024.0, 2),
        "pageouts": pageouts,
        "thrashing": bool(swap_used > 0 and pageouts > 0),
    }
