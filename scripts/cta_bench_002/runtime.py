"""Runtime lifecycle management for CTA-BENCH-002 server candidates.

Implements the launch protocol: launch command capture (sanitized), loopback
binding, /health + /v1/models checks, smoke request, graceful shutdown, whole
process-group termination after timeout, child/zombie audit and memory-pressure
baseline wait.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from scripts.cta_bench_002.spec import LOOPBACK

HEALTH_TIMEOUT_SECONDS = 180
SMOKE_TIMEOUT_SECONDS = 120
SHUTDOWN_GRACE_SECONDS = 20
KILL_GRACE_SECONDS = 10


@dataclass
class LaunchSpec:
    candidate_id: str
    runtime: str
    port: int
    launch_command: list[str]
    env_python: str
    env_extra: dict[str, str] = field(default_factory=dict)
    model: str = ""
    model_id_in_log: str = ""


def sanitize_command(command: list[str]) -> list[str]:
    """Mask secrets/home paths in a recorded launch command."""
    home = str(Path.home())
    result: list[str] = []
    for part in command:
        if home in part:
            part = part.replace(home, "$HOME")
        if "api_key" in part.lower() or "token" in part.lower():
            key, _, _ = part.partition("=")
            part = f"{key}=***"
        result.append(part)
    return result


@dataclass
class ProcessHandle:
    proc: subprocess.Popen
    pid: int
    log_path: Path | None
    port: int
    process_group_id: int | None = None
    started_at: float = field(default_factory=time.time)


@dataclass
class LifecycleResult:
    candidate_id: str
    launched: bool
    health_ok: bool
    models_ok: bool
    model_id_seen: str | None
    smoke_ok: bool
    smoke_error: str | None
    shutdown_graceful: bool
    process_group_killed: bool
    residual_processes: list[dict[str, Any]]
    load_time_seconds: float | None
    launch_command: list[str]
    errors: list[str] = field(default_factory=list)


class RuntimeLifecycle:
    def __init__(self, output_dir: Path, log_dir: Path | None = None) -> None:
        self.output_dir = output_dir
        self.log_dir = log_dir or (output_dir / "logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.handle: ProcessHandle | None = None
        self._audit_rows: list[dict[str, Any]] = []

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _http() -> httpx.Client:
        return httpx.Client(timeout=10)

    def _health_ok(self, base_url: str) -> bool:
        try:
            with self._http() as client:
                resp = client.get(f"{base_url}/health")
                return resp.status_code < 400
        except httpx.HTTPError:
            return False

    def _models_payload(self, base_url: str) -> list[dict[str, Any]]:
        try:
            with self._http() as client:
                resp = client.get(f"{base_url}/v1/models")
                if resp.status_code >= 400:
                    return []
                data = resp.json()
            models = data.get("data") or []
            if models:
                return [{"id": item.get("id"), "object": item.get("object")} for item in models]
            # Some servers return {"models": [...]} or a flat string list.
            if data.get("models"):
                return [
                    {"id": item.get("id") if isinstance(item, dict) else item, "object": "model"}
                    for item in data["models"]
                ]
            return []
        except (httpx.HTTPError, json.JSONDecodeError):
            return []

    def _smoke(self, base_url: str, model: str, prompt: str = "Reply with the single word: OK") -> dict[str, Any]:
        try:
            with httpx.Client(timeout=SMOKE_TIMEOUT_SECONDS) as client:
                resp = client.post(
                    f"{base_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 16,
                        "temperature": 0,
                        "stream": False,
                    },
                )
                if resp.status_code >= 400:
                    return {"ok": False, "status_code": resp.status_code, "body": resp.text[:500]}
                data = resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {
                    "ok": True,
                    "status_code": resp.status_code,
                    "content": content,
                    "model": data.get("model"),
                    "usage": data.get("usage"),
                }
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # -- process tree ------------------------------------------------------
    def _find_processes(self, port: int) -> list[dict[str, Any]]:
        """Find processes listening on a port plus their descendants."""
        found: list[dict[str, Any]] = []
        try:
            proc = subprocess.run(
                ["lsof", "-nP", "-iTCP", f":{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return found
        pids: set[int] = set()
        lines = proc.stdout.splitlines()
        if len(lines) > 1:
            for line in lines[1:]:
                fields = line.split()
                if len(fields) > 1 and fields[1].isdigit():
                    pids.add(int(fields[1]))
        for pid in pids:
            found.append({"pid": pid, "port": port, "relation": "listener"})
            found.extend(self._descendants(pid, port))
        return found

    def _descendants(self, parent_pid: int, port: int) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            proc = subprocess.run(
                ["pgrep", "-P", str(parent_pid)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return result
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                result.append({"pid": pid, "port": port, "relation": "descendant"})
                result.extend(self._descendants(pid, port))
        return result

    @staticmethod
    def _process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
        except OSError:
            return False

    def _memory_baseline(self) -> dict[str, Any]:
        """Return current memory pressure + swap baseline sample."""
        pressure = {"sampled": False}
        swap = {"sampled": False}
        try:
            result = subprocess.run(
                ["memory_pressure", "-Q"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            pressure = {
                "sampled": True,
                "output": result.stdout.strip()[:200],
                "exit_code": result.returncode,
            }
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            result = subprocess.run(
                ["sysctl", "-n", "vm.swapusage"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            swap = {"sampled": True, "output": result.stdout.strip(), "exit_code": result.returncode}
        except (OSError, subprocess.SubprocessError):
            pass
        return {"pressure": pressure, "swap": swap}

    # -- launch / shutdown --------------------------------------------------
    def launch(self, spec: LaunchSpec) -> LifecycleResult:
        base_url = f"http://{LOOPBACK}:{spec.port}"
        errors: list[str] = []
        result = LifecycleResult(
            candidate_id=spec.candidate_id,
            launched=False,
            health_ok=False,
            models_ok=False,
            model_id_seen=None,
            smoke_ok=False,
            smoke_error=None,
            shutdown_graceful=False,
            process_group_killed=False,
            residual_processes=[],
            load_time_seconds=None,
            launch_command=sanitize_command(spec.launch_command),
        )

        # Refuse if the port is already occupied.
        existing = self._find_processes(spec.port)
        if existing:
            errors.append(f"port {spec.port} already in use: {existing}")
            result.errors = errors
            return result

        log_path = self.log_dir / f"{spec.candidate_id}.log"
        env = dict(os.environ)
        env.update(spec.env_extra)
        try:
            proc = subprocess.Popen(
                spec.launch_command,
                stdout=open(log_path, "a"),
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
                cwd=os.getcwd(),
            )
        except OSError as exc:
            errors.append(f"launch failed: {exc}")
            result.errors = errors
            return result

        self.handle = ProcessHandle(
            proc=proc, pid=proc.pid, log_path=log_path, port=spec.port
        )
        result.launched = True
        result.log_path = str(log_path)

        started = time.time()
        health_ok = False
        models: list[dict[str, Any]] = []
        while time.time() - started < HEALTH_TIMEOUT_SECONDS:
            if proc.poll() is not None:
                errors.append(f"server exited early with code {proc.returncode}")
                break
            health_ok = self._health_ok(base_url)
            if health_ok:
                break
            time.sleep(2)
        result.health_ok = health_ok
        if health_ok:
            models = self._models_payload(base_url)
            result.models_ok = bool(models)
            result.model_id_seen = models[0]["id"] if models else None
            result.load_time_seconds = time.time() - started
            smoke = self._smoke(base_url, spec.model or "local-model")
            result.smoke_ok = bool(smoke.get("ok"))
            result.smoke_error = smoke.get("error") if not smoke.get("ok") else None
            if not result.smoke_ok:
                errors.append(f"smoke failed: {smoke}")
        else:
            errors.append("health check timed out")
        result.errors = errors
        return result

    def shutdown(self, kill_after: float = KILL_GRACE_SECONDS) -> LifecycleResult:
        result = LifecycleResult(
            candidate_id=self.handle.pid if self.handle else "no-handle",
            launched=False,
            health_ok=False,
            models_ok=False,
            model_id_seen=None,
            smoke_ok=False,
            smoke_error=None,
            shutdown_graceful=False,
            process_group_killed=False,
            residual_processes=[],
            load_time_seconds=None,
            launch_command=[],
        )
        if not self.handle:
            return result
        proc = self.handle.proc
        port = self.handle.port
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, PermissionError):
            pgid = None
        self.handle.process_group_id = pgid

        # 1. Graceful: SIGTERM to the whole process group.
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=SHUTDOWN_GRACE_SECONDS)
            result.shutdown_graceful = True
        except subprocess.TimeoutExpired:
            # 2. Force: SIGKILL the whole process group.
            if pgid is not None:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                proc.wait(timeout=kill_after)
                result.process_group_killed = True
            except subprocess.TimeoutExpired:
                pass

        # 3. Residual child/zombie audit.
        time.sleep(1)
        residual = self._find_processes(port)
        alive = [item for item in residual if self._process_alive(item["pid"])]
        result.residual_processes = alive
        if alive:
            try:
                for item in alive:
                    os.kill(item["pid"], signal.SIGKILL)
            except OSError:
                pass
            time.sleep(1)
            result.residual_processes = [
                item for item in alive if self._process_alive(item["pid"])
            ]
        self.handle = None
        return result

    def record_audit(self, candidate_id: str, result: LifecycleResult) -> dict[str, Any]:
        row = {
            "candidate_id": candidate_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "launched": result.launched,
            "health_ok": result.health_ok,
            "models_ok": result.models_ok,
            "smoke_ok": result.smoke_ok,
            "shutdown_graceful": result.shutdown_graceful,
            "process_group_killed": result.process_group_killed,
            "residual_process_count": len(result.residual_processes),
            "residual_processes": result.residual_processes,
            "load_time_seconds": result.load_time_seconds,
            "errors": result.errors,
        }
        self._audit_rows.append(row)
        return row

    def audit_rows(self) -> list[dict[str, Any]]:
        return list(self._audit_rows)


def write_cleanup_audit_csv(output_dir: Path, rows: list[dict[str, Any]]) -> Path:
    import csv

    path = output_dir / "process_cleanup_audit.csv"
    fields = [
        "candidate_id",
        "timestamp",
        "launched",
        "health_ok",
        "models_ok",
        "smoke_ok",
        "shutdown_graceful",
        "process_group_killed",
        "residual_process_count",
        "load_time_seconds",
        "errors",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})
    return path
