"""Deployment-topology execution for CTA-BENCH-002."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from scripts.cta_bench_002 import runtime
from scripts.cta_bench_002.runner import _run_llm_candidate, _run_visual_candidate

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
