"""CTA-BENCH-002 CLI.

Commands:
- init          create the artifact revision root and frozen case manifests
- env           write environment.json inventory
- run           execute a single candidate against a case set
- run-all       execute the full candidate matrix (OCR/VLM/LLM/hybrid)
- topology      execute TOPOLOGY-U/S (and R when headroom allows)
- self-test     deterministic harness check using in-process fixture/stub
- validate      validate all artifacts for a revision
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from src.shared.security.hardening import is_loopback_url

from scripts.cta_bench_002 import llm_cases, metrics, runtime, visual_cases
from scripts.cta_bench_002.clients import (
    AppProfileLlmBenchmarkClient,
    EndpointError,
    LlmBenchmarkClient,
    TesseractBenchmarkClient,
    VlmBenchmarkClient,
)
from scripts.cta_bench_002.environment import (
    environment_file_sha,
    validate_environment,
    write_environment,
)
from scripts.cta_bench_002.runner import (
    _client_for,
    _load_llm_cases,
    _load_visual_cases,
    _llm_prompt,
    _run_hybrid_candidate,
    _run_llm_candidate,
    _run_visual_candidate,
    _sampled_resource_rows,
    resource_csv_rows,
)
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
    candidate_catalog,
)


def _revision_dir(revision: str) -> Path:
    return Path("artifacts/cta-bench-002") / revision


def _commit_sha() -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return proc.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _pack_dirs(revision: str) -> tuple[Path, Path, Path]:
    root = _revision_dir(revision)
    visual_dir = root / "case_pack" / "visual"
    llm_dir = root / "case_pack" / "llm"
    return root, visual_dir, llm_dir


def _require_revision(revision: str) -> tuple[Path, Path, Path]:
    root, visual_dir, llm_dir = _pack_dirs(revision)
    if not (visual_dir / "case_manifest_visual.json").is_file():
        raise SystemExit(f"Visual case set not initialized for {revision}. Run init first.")
    if not (llm_dir / "case_manifest_llm.json").is_file():
        raise SystemExit(f"LLM case set not initialized for {revision}. Run init first.")
    return root, visual_dir, llm_dir


# ---------------------------------------------------------------------------
# init / env
# ---------------------------------------------------------------------------

def _cmd_init(args: argparse.Namespace) -> int:
    root, visual_dir, llm_dir = _pack_dirs(args.revision)
    root.mkdir(parents=True, exist_ok=True)
    visual_manifest = visual_cases.generate(visual_dir)
    llm_cases.write_manifest(llm_dir)
    errors = visual_cases.validate_generated(visual_dir)
    errors += llm_cases.validate_manifest(llm_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "initialized",
                "revision": args.revision,
                "root": str(root),
                "visual_case_count": visual_manifest["case_count"],
                "llm_case_count": llm_cases.build_manifest()["case_count"],
                "commit_sha": _commit_sha(),
            },
            sort_keys=True,
        )
    )
    return 0


def _cmd_env(args: argparse.Namespace) -> int:
    root, _, _ = _pack_dirs(args.revision)
    payload = write_environment(root, _commit_sha())
    errors = validate_environment(root / "environment.json")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "captured",
                "revision": args.revision,
                "hardware": payload["hardware"]["platform"],
                "mac_model": payload["hardware"].get("mac_model"),
                "commit_sha": payload["commit_sha"],
                "sha256": environment_file_sha(root / "environment.json"),
            },
            sort_keys=True,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# single candidate run
# ---------------------------------------------------------------------------

def _cmd_run(args: argparse.Namespace) -> int:
    root, visual_dir, llm_dir = _require_revision(args.revision)
    commit_sha = _commit_sha()
    if not (root / "environment.json").is_file():
        write_environment(root, commit_sha)

    _, _, visual_cases_list = _load_visual_cases(visual_dir)
    llm_cases_list = _load_llm_cases(llm_dir)

    candidate = next(
        (item for item in candidate_catalog() if item["candidate_id"] == args.candidate),
        None,
    )
    if candidate is None:
        print(f"ERROR: unknown candidate {args.candidate}", file=sys.stderr)
        return 1

    results: dict[str, Any] = {}
    resource_rows: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []

    # Launch server candidate if required.
    server_client = None
    lifecycle: runtime.RuntimeLifecycle | None = None
    if candidate["requires_server"]:
        lifecycle = runtime.RuntimeLifecycle(root)
        launch_spec = _launch_spec_for(candidate, args)
        result = lifecycle.launch(launch_spec)
        lifecycle.record_audit(args.candidate, result)
        if not result.health_ok:
            print(f"ERROR: {args.candidate} failed to become healthy", file=sys.stderr)
            print(json.dumps({"errors": result.errors}, indent=2), file=sys.stderr)
            lifecycle_rows = lifecycle.audit_rows()
            runtime.write_cleanup_audit_csv(root, lifecycle_rows)
            return 1
        base_url = f"http://{LOOPBACK}:{candidate['port']}"
        server_client = _client_for(args.candidate, base_url, candidate["model"], args.timeout_seconds)
        # Resource sample during the candidate's workload.
        pids = _server_pids(lifecycle)

    # Build the in-process client for OCR / LLM-CURRENT.
    try:
        client = server_client or _client_for(args.candidate, None, None, args.timeout_seconds)
    except EndpointError as exc:
        _persist_run_results(
            root,
            args.candidate,
            {
                "runs": [],
                "summary": {
                    "candidate_id": args.candidate,
                    "candidate_type": candidate["candidate_type"],
                    "engine": candidate["engine"],
                    "model": candidate["model"],
                    "baseline": candidate.get("baseline", False),
                    "status": "unavailable",
                    "compatibility_failure": str(exc),
                },
            },
        )
        print(json.dumps({"status": "compatibility_failure", "candidate_id": args.candidate, "error": str(exc)}, sort_keys=True))
        return 0

    try:
        if candidate["candidate_type"] == "vlm" or candidate["candidate_type"] == "ocr":
            warmup = visual_cases_list[0] if WARMUP_CASE_COUNT else None
            runs, summary = _run_visual_candidate(
                args.candidate,
                client,
                visual_dir,
                visual_cases_list,
                repeats=args.repeats,
                warmup_case=warmup,
            )
        else:
            runs, summary = _run_llm_candidate(args.candidate, client, llm_cases_list, repeats=args.repeats)
    except EndpointError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if lifecycle:
            shutdown = lifecycle.shutdown()
            lifecycle.record_audit(args.candidate, shutdown)
            runtime.write_cleanup_audit_csv(root, lifecycle.audit_rows())
        return 1

    if lifecycle and candidate["requires_server"]:
        resource_rows = resource_csv_rows(_sampled_resource_rows(pids, 2.0), args.candidate)
        shutdown = lifecycle.shutdown()
        lifecycle.record_audit(args.candidate, shutdown)
        lifecycle_rows = lifecycle.audit_rows()

    summary.update(
        {
            "candidate_id": args.candidate,
            "candidate_type": candidate["candidate_type"],
            "engine": candidate["engine"],
            "model": candidate["model"],
            "baseline": candidate.get("baseline", False),
        }
    )
    results["runs"] = runs
    results["summary"] = summary
    results["resource_rows"] = resource_rows
    results["lifecycle_rows"] = lifecycle_rows

    _persist_run_results(root, args.candidate, results)
    return 0


def _launch_spec_for(candidate: dict[str, Any], args: argparse.Namespace) -> runtime.LaunchSpec:
    port = int(candidate["port"])
    model = candidate["model"]
    if candidate["candidate_id"] == "VLM-BASE-LLAMA":
        command = [
            args.llama_server or "llama-server",
            "-m",
            args.llama_model,
            "--mmproj",
            args.llama_mmproj,
            "-c",
            str(args.llama_context),
            "--host",
            LOOPBACK,
            "--port",
            str(port),
            "--alias",
            model,
        ]
        return runtime.LaunchSpec(
            candidate_id=candidate["candidate_id"],
            runtime="llama.cpp",
            port=port,
            launch_command=command,
            env_python=sys.executable,
            model=model,
            model_id_in_log=model,
        )
    if candidate["candidate_id"] in {"VLM-MLX-8B", "VLM-MLX-4B"}:
        python = args.mlx_vlm_python
        command = [
            python,
            "-m",
            "mlx_vlm.server",
            "--model",
            model,
            "--host",
            LOOPBACK,
            "--port",
            str(port),
        ]
        return runtime.LaunchSpec(
            candidate_id=candidate["candidate_id"],
            runtime="mlx-vlm.server",
            port=port,
            launch_command=command,
            env_python=python,
            model=model,
            model_id_in_log=model,
        )
    if candidate["candidate_id"] in {"LLM-MLX-9B", "LLM-MLX-4B"}:
        python = args.mlx_llm_python
        command = [
            python,
            "-m",
            "app.cli",
            "launch",
            "--model-path",
            model,
            "--model-type",
            "lm",
            "--host",
            LOOPBACK,
            "--port",
            str(port),
        ]
        return runtime.LaunchSpec(
            candidate_id=candidate["candidate_id"],
            runtime="mlx-openai-server",
            port=port,
            launch_command=command,
            env_python=python,
            model=model,
            model_id_in_log=model,
        )
    raise ValueError(f"no launch spec for {candidate['candidate_id']}")


def _server_pids(lifecycle: runtime.RuntimeLifecycle) -> list[int]:
    if not lifecycle.handle:
        return []
    return [lifecycle.handle.pid]


def _persist_run_results(root: Path, candidate_id: str, results: dict[str, Any]) -> None:
    out_dir = root / "candidates" / candidate_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "runs.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "candidate_id": candidate_id,
                "summary": results["summary"],
            },
            sort_keys=True,
        )
    )


# ---------------------------------------------------------------------------
# run-all
# ---------------------------------------------------------------------------

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

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CTA-BENCH-002 benchmark harness.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def _revision_arg(subparser) -> None:
        subparser.add_argument("--revision", required=True, help="Benchmark revision (e.g. 20260801-091536).")

    init = subparsers.add_parser("init", help="Create artifact root + frozen case manifests.")
    _revision_arg(init)

    env = subparsers.add_parser("env", help="Capture environment.json.")
    _revision_arg(env)

    run = subparsers.add_parser("run", help="Run a single candidate.")
    _revision_arg(run)
    run.add_argument("--candidate", required=True)
    run.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    run.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    run.add_argument("--llama-server", default=None)
    run.add_argument("--llama-model", required=False)
    run.add_argument("--llama-mmproj", required=False)
    run.add_argument("--llama-context", type=int, default=8192)
    run.add_argument("--mlx-vlm-python", default=None)
    run.add_argument("--mlx-llm-python", default=None)

    run_all = subparsers.add_parser("run-all", help="Run the full candidate matrix.")
    _revision_arg(run_all)
    run_all.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    run_all.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    run_all.add_argument("--with-challenger", action="store_true")
    run_all.add_argument("--llama-server", default=None)
    run_all.add_argument("--llama-model", default=None)
    run_all.add_argument("--llama-mmproj", default=None)
    run_all.add_argument("--llama-context", type=int, default=8192)
    run_all.add_argument("--mlx-vlm-python", default=None)
    run_all.add_argument("--mlx-llm-python", default=None)

    topology = subparsers.add_parser("topology", help="Run a deployment topology.")
    _revision_arg(topology)
    topology.add_argument("--topology", choices=TOPOLOGIES, required=True)
    topology.add_argument("--vlm-candidate", default="VLM-MLX-4B")
    topology.add_argument("--llm-candidate", default="LLM-MLX-4B")
    topology.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    topology.add_argument("--llama-server", default=None)
    topology.add_argument("--llama-model", default=None)
    topology.add_argument("--llama-mmproj", default=None)
    topology.add_argument("--llama-context", type=int, default=8192)
    topology.add_argument("--mlx-vlm-python", default=None)
    topology.add_argument("--mlx-llm-python", default=None)

    hybrid = subparsers.add_parser("hybrid", help="Run OCR+VLM hybrid candidates (OCR text passed to VLM).")
    _revision_arg(hybrid)
    hybrid.add_argument("--vlm-candidates", default="VLM-MLX-4B,VLM-MLX-8B,VLM-BASE-LLAMA")
    hybrid.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    hybrid.add_argument("--llama-server", default=None)
    hybrid.add_argument("--llama-model", default=None)
    hybrid.add_argument("--llama-mmproj", default=None)
    hybrid.add_argument("--llama-context", type=int, default=8192)
    hybrid.add_argument("--mlx-vlm-python", default=None)
    hybrid.add_argument("--mlx-llm-python", default=None)

    self_test = subparsers.add_parser("self-test", help="Deterministic harness check.")
    _revision_arg(self_test)

    aggregate_parser = subparsers.add_parser("aggregate", help="Build aggregated section-18 artifacts.")
    _revision_arg(aggregate_parser)

    validate = subparsers.add_parser("validate", help="Validate artifact set.")
    _revision_arg(validate)

    args = parser.parse_args(argv)
    commands = {
        "init": _cmd_init,
        "env": _cmd_env,
        "run": _cmd_run,
        "run-all": _cmd_run_all,
        "topology": _cmd_topology,
        "hybrid": _cmd_hybrid,
        "self-test": _cmd_self_test,
        "aggregate": _cmd_aggregate,
        "validate": _cmd_validate,
    }
    try:
        return commands[args.command](args)
    except (OSError, ValueError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
