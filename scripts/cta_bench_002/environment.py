"""Phase 0 environment inventory capture (environment.json).

Records the exact host, OS, runtimes, model sources and versions used for the
CTA-BENCH-002 benchmark so results are reproducible and attributable.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None


def _run(cmd: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        value = proc.stdout.strip()
        return value or None
    except (OSError, subprocess.SubprocessError):
        return None


def _sha_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def system_memory_bytes() -> int | None:
    if sys.platform == "darwin":
        value = _run(["sysctl", "-n", "hw.memsize"])
        try:
            return int(value) if value else None
        except ValueError:
            return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages) * int(page_size)
    except (AttributeError, OSError, ValueError):
        return None


def swap_usage() -> dict[str, Any] | None:
    if sys.platform != "darwin":
        return None
    value = _run(["sysctl", "-n", "vm.swapusage"])
    if not value:
        return None
    parts = {}
    for token in value.split(","):
        token = token.strip()
        if "=" in token:
            key, _, raw = token.partition("=")
            try:
                number = float(raw.replace("M", ""))
            except ValueError:
                continue
            parts[key.strip()] = number
    return parts or None


def gpu_wired_limit_mb() -> str | None:
    if sys.platform != "darwin":
        return None
    return _run(["sysctl", "-n", "iogpu.wired_limit_mb"])


def memory_pressure_ok() -> dict[str, Any]:
    if sys.platform != "darwin":
        return {"sampled": False}
    value = _run(["memory_pressure", "-Q"])
    ok = value is not None and "System-wide memory free percentage:" in value
    percentage = None
    if value:
        for line in value.splitlines():
            if "System-wide memory free percentage:" in line:
                try:
                    percentage = int(line.rsplit(":", 1)[1].strip().rstrip("%"))
                except ValueError:
                    pass
    return {"sampled": True, "pressure_ok": ok, "free_percentage": percentage}


def process_versions() -> dict[str, Any]:
    result: dict[str, Any] = {}

    def add(name: str, cmd: list[str], flags: list[str] | None = None) -> None:
        flags = flags or []
        full = cmd + flags
        value = _run(full)
        if value is not None:
            result[name] = value
        else:
            result[name] = "unavailable"

    add("python", [sys.executable, "--version"])
    add("uv", ["uv", "--version"])
    add("tesseract", ["tesseract", "--version"])
    result["tesseract_languages"] = _run(["tesseract", "--list-langs"])
    add("git", ["git", "--version"])
    add("llama-server", ["llama-server", "--version"])
    add("ollama", ["ollama", "--version"])
    return result


def python_packages(*env_pythons: list[str]) -> dict[str, Any]:
    packages: dict[str, Any] = {}
    probes = [
        ("mlx", "mlx"),
        ("mlx_lm", "mlx-lm"),
        ("mlx_vlm", "mlx-vlm"),
        ("mlx_openai_server", "mlx-openai-server"),
        ("httpx", "httpx"),
        ("PIL", "pillow"),
        ("openpyxl", "openpyxl"),
    ]
    for index, python in enumerate([sys.executable, *env_pythons]):
        found: dict[str, str] = {}
        for module, package in probes:
            code = (
                "import importlib.metadata as m;"
                f"print(m.version({package!r}))"
            )
            version = _run([python, "-c", code])
            if version:
                found[module] = version
        packages[str(index)] = {"python": python, "packages": found}
    return packages


def disk_free_bytes(path: str) -> int | None:
    value = _run(["df", "-k", path])
    if not value:
        return None
    lines = value.splitlines()
    if len(lines) < 2:
        return None
    fields = lines[1].split()
    if len(fields) < 4:
        return None
    try:
        return int(fields[3]) * 1024
    except ValueError:
        return None


def capture_environment(root: Path, commit_sha: str) -> dict[str, Any]:
    """Build the environment.json payload for the current machine state."""
    mac_model = _run(["sysctl", "-n", "hw.model"])
    cpu = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
    core_count = _run(["sysctl", "-n", "hw.logicalcpu"])
    physical_count = _run(["sysctl", "-n", "hw.physicalcpu"])
    gpu_core_count = _run(["sysctl", "-n", "hw.perflevel0.logicalcpu"]) or core_count
    free_mb = disk_free_bytes(str(root))

    return {
        "benchmark_id": "cta-bench-002",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": commit_sha,
        "hardware": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "mac_model": mac_model,
            "cpu_brand": cpu,
            "logical_cpu_count": core_count,
            "physical_cpu_count": physical_count,
            "gpu_core_count_heuristic": gpu_core_count,
            "total_memory_bytes": system_memory_bytes(),
            "iogpu_wired_limit_mb": gpu_wired_limit_mb(),
        },
        "memory": {
            "swap_usage": swap_usage(),
            "pressure": memory_pressure_ok(),
        },
        "disk": {
            "workspace_disk_free_bytes": free_mb,
            "workspace_disk_free_gib": round(free_mb / (1024**3), 2) if free_mb else None,
        },
        "runtimes": process_versions(),
        "python_environments": python_packages(),
        "process_resource_scope": {
            "note": "memory sampling covers the benchmark harness and the target server process group; "
                    "Ollama/LM Studio system daemons are recorded as baseline load only.",
        },
        "constraints": {
            "loopback_only": True,
            "cloud_fallback_disabled": True,
            "external_telemetry_disabled": True,
        },
    }


def write_environment(root: Path, commit_sha: str) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    payload = capture_environment(root, commit_sha)
    path = root / "environment.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def environment_file_sha(path: Path) -> str | None:
    return _sha_file(path)


def validate_environment(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.is_file():
        return ["environment.json is missing"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"environment.json unreadable: {exc}"]
    if payload.get("benchmark_id") != "cta-bench-002":
        errors.append("unexpected benchmark id")
    hardware = payload.get("hardware") or {}
    if not hardware.get("platform"):
        errors.append("hardware platform missing")
    if not payload.get("commit_sha"):
        errors.append("commit SHA missing")
    if not payload.get("runtimes"):
        errors.append("runtime versions missing")
    return errors
