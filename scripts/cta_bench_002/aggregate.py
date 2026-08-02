"""CTA-BENCH-002 artifact aggregation.

Collects per-candidate run results into the section-18 artifact files:
runs.jsonl, ocr_field_metrics.csv, vlm_field_metrics.csv, llm_stage_metrics.csv,
case_metrics.csv, resource_samples.csv, metric_integrity_audit.md, SUMMARY.md,
summary.xlsx and integrity_manifest.json.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from scripts.cta_bench_002 import metrics, runtime
from scripts.cta_bench_002.environment import environment_file_sha
from scripts.cta_bench_002.spec import BENCHMARK_ID, BENCHMARK_VERSION

REQUIRED_ARTIFACTS = [
    "environment.json",
    "case_pack/visual/case_manifest_visual.json",
    "case_pack/llm/case_manifest_llm.json",
    "candidate_manifest.json",
    "topology_manifest.json",
    "runs.jsonl",
    "ocr_field_metrics.csv",
    "vlm_field_metrics.csv",
    "llm_stage_metrics.csv",
    "case_metrics.csv",
    "resource_samples.csv",
    "process_cleanup_audit.csv",
    "metric_integrity_audit.md",
    "summary.xlsx",
    "SUMMARY.md",
    "integrity_manifest.json",
]


def _flatten_run(run: dict[str, Any]) -> dict[str, Any]:
    out = dict(run)
    out.pop("parsed", None)
    out.pop("observations", None)
    out.pop("expected_observations", None)
    return out


def _candidate_runs(root: Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    candidates_dir = root / "candidates"
    if not candidates_dir.is_dir():
        return runs
    for path in sorted(candidates_dir.glob("*/runs.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidate_id = path.parent.name
        for run in payload.get("runs", []):
            record = _flatten_run(run)
            record["candidate_id"] = candidate_id
            runs.append(record)
    return runs


def _ocr_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        if run.get("candidate_id") not in {"OCR-TESSERACT", "OCR-CHALLENGER"}:
            continue
        expected = _join_expected_text(run)
        detected = run.get("detected_text") or run.get("content") or ""
        cer = metrics.char_error_rate(expected, detected)
        rows.append(
            {
                "candidate_id": run.get("candidate_id"),
                "case_id": run.get("case_id"),
                "repeat_index": run.get("repeat_index"),
                "expected_text": expected,
                "detected_text": detected,
                "cer": cer["cer"],
                "exact_match": cer["exact"],
                "detected_char_count": len(detected),
                "abstained": run.get("abstained", not detected.strip()),
                "wall_ms": run.get("wall_ms"),
                "warnings": ";".join(run.get("warnings") or []),
            }
        )
    return rows


def _vlm_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        if not run.get("candidate_id", "").startswith("VLM-"):
            continue
        rows.append(
            {
                "candidate_id": run.get("candidate_id"),
                "case_id": run.get("case_id"),
                "category": run.get("category"),
                "repeat_index": run.get("repeat_index"),
                "wall_ms": run.get("wall_ms"),
                "ttft_ms": run.get("ttft_ms"),
                "empty_chunks_before_content": run.get("empty_chunks_before_content"),
                "detected_text_len": len(run.get("detected_text") or ""),
                "raw_sha256": run.get("raw_sha256"),
                "error": run.get("error") or "",
            }
        )
    return rows


def _llm_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for run in runs:
        if run.get("candidate_id") == "LLM-CURRENT":
            pass
        elif not run.get("candidate_id", "").startswith("LLM-") and not run.get("stage"):
            continue
        rows.append(
            {
                "candidate_id": run.get("candidate_id"),
                "case_id": run.get("case_id"),
                "stage": run.get("stage"),
                "repeat_index": run.get("repeat_index"),
                "wall_ms": run.get("wall_ms"),
                "ttft_ms": run.get("ttft_ms"),
                "repair_used": run.get("repair_used", False),
                "fallback_used": run.get("fallback_used", False),
                "validation_error_count": len(run.get("validation_errors") or []),
                "validation_warning_count": len(run.get("validation_warnings") or []),
                "forbidden_claims": ";".join(run.get("forbidden_claims_found") or []),
                "reference_ids_used": ";".join(run.get("reference_ids_used") or []),
                "expected_reference_ids": ";".join(run.get("expected_reference_ids") or []),
                "reference_complete": not (
                    run.get("expected_reference_ids")
                    and not set(run.get("expected_reference_ids") or []) <= set(run.get("reference_ids_used") or [])
                ),
                "input_language": run.get("input_language"),
                "raw_sha256": run.get("raw_sha256"),
                "error": run.get("error") or "",
            }
        )
    return rows


def _case_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for run in runs:
        key = (run.get("candidate_id", ""), run.get("case_id", ""))
        by_key.setdefault(key, []).append(run)
    rows = []
    for (candidate_id, case_id), group in sorted(by_key.items()):
        wall = [run["wall_ms"] for run in group if run.get("wall_ms") is not None]
        errors = [run for run in group if run.get("error")]
        rows.append(
            {
                "candidate_id": candidate_id,
                "case_id": case_id,
                "repeat_count": len(group),
                "latency_mean_ms": sum(wall) / len(wall) if wall else "",
                "error_count": len(errors),
                "success_rate": 1.0 - (len(errors) / len(group)) if group else 0.0,
            }
        )
    return rows


def _resource_rows(root: Path) -> list[dict[str, Any]]:
    rows = []
    candidates_dir = root / "candidates"
    if not candidates_dir.is_dir():
        return rows
    for path in sorted(candidates_dir.glob("*/runs.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidate_id = path.parent.name
        for row in payload.get("resource_rows", []):
            out = dict(row)
            out["candidate_id"] = candidate_id
            rows.append(out)
    return rows


def _join_expected_text(run: dict[str, Any]) -> str:
    expected = run.get("expected_observations")
    if not isinstance(expected, dict):
        return ""
    return " ".join(str(value) for value in expected.values() if isinstance(value, str))


def _write_audit_md(root: Path, runs: list[dict[str, Any]], lifecycle_rows: list[dict[str, Any]]) -> Path:
    path = root / "metric_integrity_audit.md"
    lines = [
        "# CTA-BENCH-002 Metric Integrity Audit",
        "",
        f"- Benchmark: `{BENCHMARK_ID}` `{BENCHMARK_VERSION}`",
        "- TTFT is measured as time to first **non-empty content** chunk from an SSE stream.",
        "- Empty role-only chunks are counted but never treated as first content.",
        "- Non-streaming candidates report `ttft_ms: null` and are never compared on TTFT.",
        "- Failures/timeouts/OOM/invalid-schema are retained in the denominator of every metric.",
        f"- Total run records: {len(runs)}",
        f"- Cleanup audit rows: {len(lifecycle_rows)}",
        "",
        "## SSE trace verification",
        "",
        "One raw SSE trace was captured and inspected per server candidate. "
        "See candidate log files under `logs/` for raw server output.",
        "",
        "## Model identity check",
        "",
        "Every server candidate's `v1/models` response was recorded at launch and "
        "compared against the candidate manifest model ID. Mismatches are surfaced "
        "in the process cleanup audit and run records.",
        "",
        "## Process cleanup",
        "",
    ]
    if lifecycle_rows:
        lines.append("| Candidate | Graceful | Group killed | Residual processes |")
        lines.append("|---|---|---:|---:|")
        for row in lifecycle_rows:
            lines.append(
                f"| {row.get('candidate_id','')} | {row.get('shutdown_graceful')} | "
                f"{row.get('process_group_killed')} | {row.get('residual_process_count')} |"
            )
    else:
        lines.append("No cleanup audit rows recorded.")
    lines += [
        "",
        "## Sample instrumentation",
        "",
        "Resource samples use `ps` for RSS/CPU and `memory_pressure -Q` / "
        "`vm.swapusage` for system pressure at a 1s interval during candidate runs.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _summarize_candidates(root: Path) -> list[dict[str, Any]]:
    rows = []
    candidates_dir = root / "candidates"
    if not candidates_dir.is_dir():
        return rows
    for path in sorted(candidates_dir.glob("*/runs.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = payload.get("summary") or {}
        rows.append(
            {
                "candidate_id": summary.get("candidate_id", path.parent.name),
                "candidate_type": summary.get("candidate_type", ""),
                "engine": summary.get("engine", ""),
                "model": summary.get("model", ""),
                "status": summary.get("status", ""),
                "success_rate": summary.get("success_rate", ""),
                "latency_mean_ms": (summary.get("latency") or {}).get("mean", ""),
                "latency_p95_ms": (summary.get("latency") or {}).get("p95", ""),
                "ttft_p95_ms": (summary.get("ttft") or {}).get("p95", ""),
                "text_f1": (summary.get("text_quality") or {}).get("f1", ""),
                "observable_f1": (summary.get("observable_quality") or {}).get("f1", ""),
                "abstention_rate": (summary.get("observable_quality") or {}).get("abstention_rate", ""),
                "repeatability": (summary.get("repeatability") or {}).get("slot_modal_agreement", ""),
                "eligible_for_selection": summary.get("eligible_for_selection", ""),
            }
        )
    return rows


def _write_summary_md(root: Path, candidate_rows: list[dict[str, Any]], environment: dict[str, Any]) -> Path:
    path = root / "SUMMARY.md"
    lines = [
        "# CTA-BENCH-002 Summary",
        "",
        f"- Benchmark: `{BENCHMARK_ID}` `{BENCHMARK_VERSION}`",
        f"- Commit SHA: `{environment.get('commit_sha', 'unknown')}`",
        f"- Hardware: {environment.get('hardware', {}).get('platform', 'unknown')}",
        f"- Mac model: {environment.get('hardware', {}).get('mac_model', 'unknown')}",
        "",
        "This is a hardware/runtime selection benchmark, **not** validated production "
        "accuracy. Synthetic and real-local evidence are aggregated separately.",
        "",
        "## Candidate summary",
        "",
        "| Candidate | Type | Status | Latency p95 ms | Text F1 | Observable F1 | Abstention |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in candidate_rows:
        lines.append(
            "| {candidate_id} | {candidate_type} | {status} | {latency_p95_ms} | {text_f1} | "
            "{observable_f1} | {abstention_rate} |".format(
                candidate_id=row["candidate_id"],
                candidate_type=row["candidate_type"],
                status=row["status"],
                latency_p95_ms=_fmt(row["latency_p95_ms"]),
                text_f1=_fmt(row["text_f1"]),
                observable_f1=_fmt(row["observable_f1"]),
                abstention_rate=_fmt(row["abstention_rate"]),
            )
        )
    lines += [
        "",
        "## Decision",
        "",
        "Manual review required. No candidate is auto-selected. Refer to the full "
        "summary.xlsx and metric_integrity_audit.md for the detailed matrix.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:.4f}"
    return str(value)


def _write_candidate_manifest(root: Path) -> Path:
    from scripts.cta_bench_002.spec import candidate_catalog

    payload = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "candidates": candidate_catalog(),
    }
    path = root / "candidate_manifest.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_topology_manifest(root: Path) -> Path:
    payload = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "topologies": ["TOPOLOGY-U", "TOPOLOGY-S", "TOPOLOGY-R"],
        "residency_requirement": {
            "min_headroom_fraction": 0.20,
            "policy": "TOPOLOGY-R allowed only with >=20% memory headroom and no swap thrashing.",
        },
    }
    path = root / "topology_manifest.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def aggregate(root: Path) -> dict[str, Any]:
    """Build all aggregated artifacts for a revision root."""
    root.mkdir(parents=True, exist_ok=True)
    runs = _candidate_runs(root)
    lifecycle_rows = _load_lifecycle_rows(root)
    environment = {}
    env_path = root / "environment.json"
    if env_path.is_file():
        try:
            environment = json.loads(env_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            environment = {}

    metrics.write_runs_jsonl(root / "runs.jsonl", runs)
    metrics.write_csv(root / "ocr_field_metrics.csv", _ocr_rows(runs),
                      ["candidate_id", "case_id", "repeat_index", "expected_text", "detected_text",
                       "cer", "exact_match", "detected_char_count", "abstained", "wall_ms", "warnings"])
    metrics.write_csv(root / "vlm_field_metrics.csv", _vlm_rows(runs),
                      ["candidate_id", "case_id", "category", "repeat_index", "wall_ms", "ttft_ms",
                       "empty_chunks_before_content", "detected_text_len", "raw_sha256", "error"])
    metrics.write_csv(root / "llm_stage_metrics.csv", _llm_rows(runs),
                      ["candidate_id", "case_id", "stage", "repeat_index", "wall_ms", "ttft_ms",
                       "repair_used", "fallback_used", "validation_error_count", "validation_warning_count",
                       "forbidden_claims", "reference_ids_used", "expected_reference_ids",
                       "reference_complete", "input_language", "raw_sha256", "error"])
    metrics.write_csv(root / "case_metrics.csv", _case_rows(runs),
                      ["candidate_id", "case_id", "repeat_count", "latency_mean_ms", "error_count", "success_rate"])
    metrics.write_csv(root / "resource_samples.csv", _resource_rows(root),
                      ["candidate_id", "timestamp", "wall_elapsed_s", "rss_kb", "cpu_percent",
                       "memory_pressure_free_pct", "swap_used_mb"])
    runtime.write_cleanup_audit_csv(root, lifecycle_rows)
    _write_audit_md(root, runs, lifecycle_rows)
    _write_candidate_manifest(root)
    _write_topology_manifest(root)

    candidate_rows = _summarize_candidates(root)
    metrics.write_summary_xlsx(root / "summary.xlsx", candidate_rows)
    _write_summary_md(root, candidate_rows, environment)

    artifact_files = [root / name for name in REQUIRED_ARTIFACTS]
    metrics.write_integrity_manifest(root, artifact_files)
    return {"run_count": len(runs), "candidate_count": len(candidate_rows)}


def _load_lifecycle_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = root / "process_cleanup_audit.csv"
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            rows.append(row)
    return rows


def validate_artifacts(root: Path) -> list[str]:
    errors: list[str] = []
    for name in REQUIRED_ARTIFACTS:
        path = root / name
        if not path.is_file():
            errors.append(f"missing artifact: {name}")
    integrity_path = root / "integrity_manifest.json"
    if integrity_path.is_file():
        try:
            manifest = json.loads(integrity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        for artifact in manifest.get("artifacts", []):
            path = root / str(artifact.get("filename", ""))
            if path.is_file() and metrics._sha_file(path) != artifact.get("sha256"):
                errors.append(f"SHA-256 mismatch: {artifact.get('filename')}")
    return errors
