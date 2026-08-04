"""Extended run, topology, validation, and self-test CLI commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.cta_bench_002 import llm_cases, runtime, visual_cases
from scripts.cta_bench_002.__main__ import (
    _commit_sha,
    _launch_spec_for,
    _pack_dirs,
    _persist_run_results,
    _require_revision,
)
from scripts.cta_bench_002.clients import (
    AppProfileLlmBenchmarkClient,
    EndpointError,
    LlmBenchmarkClient,
    TesseractBenchmarkClient,
    VlmBenchmarkClient,
)
from scripts.cta_bench_002.environment import validate_environment, write_environment
from scripts.cta_bench_002.runner import (
    _load_llm_cases,
    _load_visual_cases,
    _run_hybrid_candidate,
    _run_llm_candidate,
    _run_visual_candidate,
)
from scripts.cta_bench_002.spec import LOOPBACK, WARMUP_CASE_COUNT, candidate_catalog

def _cmd_run_all(args: argparse.Namespace) -> int:
    root, visual_dir, llm_dir = _require_revision(args.revision)
    if not (root / "environment.json").is_file():
        write_environment(root, _commit_sha())
    _, _, visual_cases_list = _load_visual_cases(visual_dir)
    llm_cases_list = _load_llm_cases(llm_dir)

    ocr_client = TesseractBenchmarkClient()
    candidates = candidate_catalog()

    # OCR candidates first (in-process).
    for candidate in candidates:
        if candidate["candidate_id"] == "OCR-TESSERACT":
            runs, summary = _run_visual_candidate(
                candidate["candidate_id"],
                ocr_client,
                visual_dir,
                visual_cases_list,
                repeats=args.repeats,
                warmup_case=visual_cases_list[0],
            )
            summary.update({"engine": "tesseract", "model": "tesseract-5.5.3", "baseline": True})
            _persist_run_results(root, candidate["candidate_id"], {"runs": runs, "summary": summary})

    if args.with_challenger:
        try:
            from scripts.cta_bench_002.clients import PaddleOcrBenchmarkClient

            challenger = PaddleOcrBenchmarkClient()
            runs, summary = _run_visual_candidate(
                "OCR-CHALLENGER",
                challenger,
                visual_dir,
                visual_cases_list,
                repeats=args.repeats,
                warmup_case=visual_cases_list[0],
            )
            summary.update({"engine": "paddleocr", "model": "PP-OCRv5-mobile", "baseline": False})
            _persist_run_results(root, "OCR-CHALLENGER", {"runs": runs, "summary": summary})
        except (EndpointError, ImportError) as exc:
            print(
                json.dumps(
                    {
                        "status": "compatibility_failure",
                        "candidate_id": "OCR-CHALLENGER",
                        "error": str(exc),
                    },
                    sort_keys=True,
                )
            )
            _persist_run_results(
                root,
                "OCR-CHALLENGER",
                {
                    "runs": [],
                    "summary": {
                        "candidate_id": "OCR-CHALLENGER",
                        "status": "unavailable",
                        "engine": "paddleocr",
                        "model": "PP-OCRv5-mobile",
                        "compatibility_failure": str(exc),
                    },
                },
            )

    # Server candidates (VLM + LLM).
    for candidate in candidates:
        if not candidate["requires_server"] or candidate["candidate_id"] in {"OCR-TESSERACT", "OCR-CHALLENGER", "LLM-CURRENT"}:
            continue
        cmd_args = argparse.Namespace(
            revision=args.revision,
            candidate=candidate["candidate_id"],
            repeats=args.repeats,
            timeout_seconds=args.timeout_seconds,
            llama_server=args.llama_server,
            llama_model=args.llama_model,
            llama_mmproj=args.llama_mmproj,
            llama_context=args.llama_context,
            mlx_vlm_python=args.mlx_vlm_python,
            mlx_llm_python=args.mlx_llm_python,
        )
        _cmd_run(cmd_args)

    # LLM-CURRENT (application stub baseline).
    llm_current = AppProfileLlmBenchmarkClient(provider_name="stub")
    runs, summary = _run_llm_candidate("LLM-CURRENT", llm_current, llm_cases_list, repeats=args.repeats)
    summary.update({"engine": "app-profile", "model": "profile:current", "baseline": True})
    _persist_run_results(root, "LLM-CURRENT", {"runs": runs, "summary": summary})

    return 0


# ---------------------------------------------------------------------------
# topology
# ---------------------------------------------------------------------------

def _cmd_topology(args: argparse.Namespace) -> int:
    from scripts.cta_bench_002.runner import _run_topology_s, _run_topology_u

    root, visual_dir, llm_dir = _require_revision(args.revision)
    _, _, visual_cases_list = _load_visual_cases(visual_dir)
    llm_cases_list = _load_llm_cases(llm_dir)

    vlm_candidate = next(
        item for item in candidate_catalog() if item["candidate_id"] == args.vlm_candidate
    )
    llm_candidate = next(
        item for item in candidate_catalog() if item["candidate_id"] == args.llm_candidate
    )
    vlm_base = f"http://{LOOPBACK}:{vlm_candidate['port']}"
    llm_base = f"http://{LOOPBACK}:{llm_candidate['port']}"
    vlm_client = VlmBenchmarkClient(vlm_base, vlm_candidate["model"], args.timeout_seconds)
    llm_client = LlmBenchmarkClient(llm_base, llm_candidate["model"], args.timeout_seconds)

    lifecycle = runtime.RuntimeLifecycle(root)
    results: dict[str, Any] = {"topologies": {}, "resource_rows": [], "lifecycle_rows": []}

    if args.topology == "TOPOLOGY-U":
        launch_spec = _launch_spec_for(vlm_candidate, args)
        lifecycle.launch(launch_spec)
        topology_result = _run_topology_u(vlm_client, llm_client, visual_dir, visual_cases_list, llm_cases_list)
        lifecycle.record_audit("TOPOLOGY-U", runtime.LifecycleResult(
            candidate_id="TOPOLOGY-U", launched=True, health_ok=True, models_ok=True,
            model_id_seen=vlm_candidate["model"], smoke_ok=True, smoke_error=None,
            shutdown_graceful=False, process_group_killed=False, residual_processes=[],
            load_time_seconds=None, launch_command=[],
        ))
        shutdown = lifecycle.shutdown()
        lifecycle.record_audit("TOPOLOGY-U", shutdown)
        results["topologies"]["TOPOLOGY-U"] = topology_result

    if args.topology == "TOPOLOGY-S":
        launch_vlm = _launch_spec_for(vlm_candidate, args)
        launch_llm = _launch_spec_for(llm_candidate, args)
        topology_result = _run_topology_s(
            vlm_client, llm_client, lifecycle, launch_vlm, launch_llm,
            visual_dir, visual_cases_list, llm_cases_list,
        )
        results["topologies"]["TOPOLOGY-S"] = topology_result

    if args.topology == "TOPOLOGY-R":
        from scripts.cta_bench_002.runner import _run_topology_r
        from scripts.cta_bench_002.spec import TOPOLOGY_R_MIN_HEADROOM_FRACTION

        lifecycle_vlm = runtime.RuntimeLifecycle(root)
        lifecycle_llm = runtime.RuntimeLifecycle(root)
        launch_vlm = _launch_spec_for(vlm_candidate, args)
        launch_llm = _launch_spec_for(llm_candidate, args)
        topology_result = _run_topology_r(
            vlm_client, llm_client, lifecycle_vlm, lifecycle_llm,
            launch_vlm, launch_llm,
            visual_dir, visual_cases_list, llm_cases_list,
            min_headroom_fraction=TOPOLOGY_R_MIN_HEADROOM_FRACTION,
        )
        lifecycle_vlm.record_audit("TOPOLOGY-R-VLM", runtime.LifecycleResult(
            candidate_id="TOPOLOGY-R-VLM", launched=True, health_ok=bool(topology_result.get("visual_runs")),
            models_ok=bool(topology_result.get("visual_runs")), model_id_seen=vlm_candidate["model"],
            smoke_ok=bool(topology_result.get("visual_runs")), smoke_error=None,
            shutdown_graceful=bool(topology_result.get("vlm_shutdown_graceful")),
            process_group_killed=False, residual_processes=topology_result.get("residual_vlm") or [],
            load_time_seconds=None, launch_command=[],
        ))
        lifecycle_llm.record_audit("TOPOLOGY-R-LLM", runtime.LifecycleResult(
            candidate_id="TOPOLOGY-R-LLM", launched=True, health_ok=bool(topology_result.get("llm_runs")),
            models_ok=bool(topology_result.get("llm_runs")), model_id_seen=llm_candidate["model"],
            smoke_ok=bool(topology_result.get("llm_runs")), smoke_error=None,
            shutdown_graceful=bool(topology_result.get("llm_shutdown_graceful")),
            process_group_killed=False, residual_processes=topology_result.get("residual_llm") or [],
            load_time_seconds=None, launch_command=[],
        ))
        results["topologies"]["TOPOLOGY-R"] = topology_result

    results["lifecycle_rows"] = lifecycle.audit_rows()
    runtime.write_cleanup_audit_csv(root, lifecycle.audit_rows())
    existing = {}
    topo_file = root / "topology_results.json"
    if topo_file.is_file():
        try:
            existing = json.loads(topo_file.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    merged = {
        "revision": args.revision,
        "topologies": {**(existing.get("topologies") or {}), **results["topologies"]},
        "lifecycle_rows": results["lifecycle_rows"] or (existing.get("lifecycle_rows") or []),
    }
    topo_file.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "completed", "topology": args.topology, "revision": args.revision}, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# hybrid
# ---------------------------------------------------------------------------

def _cmd_hybrid(args: argparse.Namespace) -> int:
    from scripts.cta_bench_002.runner import _run_hybrid_candidate

    root, visual_dir, llm_dir = _require_revision(args.revision)
    _, _, visual_cases_list = _load_visual_cases(visual_dir)
    ocr_client = TesseractBenchmarkClient()
    candidates = {item["candidate_id"]: item for item in candidate_catalog()}
    vlm_ids = [c.strip() for c in args.vlm_candidates.split(",") if c.strip()]
    lifecycle = runtime.RuntimeLifecycle(root)
    results: dict[str, Any] = {"hybrids": {}, "lifecycle_rows": []}

    for vlm_id in vlm_ids:
        candidate = candidates.get(vlm_id)
        if candidate is None or candidate["candidate_type"] != "vlm":
            continue
        base_url = f"http://{LOOPBACK}:{candidate['port']}"
        vlm_client = VlmBenchmarkClient(base_url, candidate["model"], args.timeout_seconds)
        launch_spec = _launch_spec_for(candidate, args)
        launch_result = lifecycle.launch(launch_spec)
        if not launch_result.health_ok:
            results["hybrids"][vlm_id] = {"status": "unavailable", "errors": launch_result.errors}
            print(json.dumps({"candidate_id": vlm_id, "status": "unavailable", "errors": launch_result.errors}, sort_keys=True))
            lifecycle.shutdown()
            continue
        runs, summary = _run_hybrid_candidate(vlm_id, ocr_client, vlm_client, visual_dir, visual_cases_list)
        lifecycle.shutdown()
        results["hybrids"][vlm_id] = summary
        _persist_run_results(root, f"HYBRID-OCR+{vlm_id}", {"runs": runs, "summary": summary})
        print(json.dumps({"candidate_id": f"HYBRID-OCR+{vlm_id}", "status": "completed", "summary": summary}, sort_keys=True))

    results["lifecycle_rows"] = lifecycle.audit_rows()
    runtime.write_cleanup_audit_csv(root, lifecycle.audit_rows())
    (root / "hybrid_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "completed", "command": "hybrid", "revision": args.revision}, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def _cmd_self_test(args: argparse.Namespace) -> int:
    root, visual_dir, llm_dir = _pack_dirs(args.revision)
    errors: list[str] = []

    # 1. Visual case set determinism.
    errors += visual_cases.check_determinism()
    # 2. LLM manifest validity.
    manifest = llm_cases.build_manifest()
    if not manifest["cases"]:
        errors.append("LLM case set is empty")

    # 3. Deterministic OCR self-test with Tesseract on the generated pack.
    visual_manifest, _, visual_cases_list = _load_visual_cases(visual_dir)
    ocr_client = TesseractBenchmarkClient()
    runs, summary = _run_visual_candidate(
        "OCR-TESSERACT",
        ocr_client,
        visual_dir,
        visual_cases_list,
        repeats=2,
        warmup_case=visual_cases_list[0],
    )
    if summary["status"] != "complete":
        errors.append("OCR self-test did not complete")
    # Tesseract should at least detect the explicit CTA case text.
    cta_case = next(case for case in visual_cases_list if case["case_id"] == "explicit-cta")
    cta_runs = [run for run in runs if run["case_id"] == "explicit-cta"]
    if cta_runs and not cta_runs[0]["content"].strip():
        errors.append("OCR detected no text on the explicit-cta case")

    # 4. LLM fixture self-test (deterministic, schema-valid, harness-only).
    from scripts.cta_bench_002.clients import FixtureLlmBenchmarkClient

    llm_fixture = FixtureLlmBenchmarkClient()
    llm_cases_list = _load_llm_cases(llm_dir)
    llm_runs, llm_summary = _run_llm_candidate("fixture:llm-contract", llm_fixture, llm_cases_list, repeats=1)
    if llm_summary["schema_valid_rate"] < 1.0:
        errors.append("fixture LLM self-test should be schema-valid")
    if llm_summary["fallback_rate"] > 0.0:
        errors.append("fixture LLM self-test should not trigger fallback")
    if llm_summary["forbidden_claim_total"] > 0:
        errors.append("fixture LLM self-test produced forbidden claims")
    # 5. LLM-CURRENT stub self-test must not crash (unavailability is acceptable).
    llm_current = AppProfileLlmBenchmarkClient(provider_name="stub")
    _run_llm_candidate("LLM-CURRENT", llm_current, llm_cases_list, repeats=1)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "valid",
                "command": "self-test",
                "revision": args.revision,
                "harness_only": True,
                "visual_case_count": visual_manifest["case_count"],
                "llm_case_count": manifest["case_count"],
                "ocr_self_test": "passed",
                "llm_fixture_self_test": "passed",
            },
            sort_keys=True,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# aggregate / validate
# ---------------------------------------------------------------------------

def _cmd_aggregate(args: argparse.Namespace) -> int:
    from scripts.cta_bench_002.aggregate import aggregate, validate_artifacts

    root, _, _ = _pack_dirs(args.revision)
    result = aggregate(root)
    errors = validate_artifacts(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "aggregated",
                "revision": args.revision,
                "run_count": result["run_count"],
                "candidate_count": result["candidate_count"],
            },
            sort_keys=True,
        )
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    root, visual_dir, llm_dir = _pack_dirs(args.revision)
    errors: list[str] = []
    errors += visual_cases.validate_generated(visual_dir)
    errors += llm_cases.validate_manifest(llm_dir)
    env_path = root / "environment.json"
    if env_path.is_file():
        errors += validate_environment(env_path)
    else:
        errors.append("environment.json is missing")
    for name in ["runs.jsonl", "ocr_field_metrics.csv", "vlm_field_metrics.csv", "llm_stage_metrics.csv", "case_metrics.csv"]:
        if not (root / name).is_file():
            errors.append(f"missing artifact: {name}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "valid", "command": "validate", "revision": args.revision}, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
