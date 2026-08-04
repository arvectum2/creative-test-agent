"""Safe local runtime controls for a frozen CTA-MODEL-001 profile.

The module intentionally does not download models or use a shell. Commands are
read from the integrity-bound profile, whole-token environment references are
resolved, and each server owns a separate process group.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .profile import (
    ProfileValidationError,
    _origin,
    model_identity_url,
    resolve_command,
    validate_profile,
)


@dataclass(frozen=True)
class ComponentStatus:
    component: str
    pid: int | None
    process_group_id: int | None
    process_alive: bool
    endpoint_reachable: bool
    expected_model: str
    served_models: tuple[str, ...]
    identity_match: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "pid": self.pid,
            "process_group_id": self.process_group_id,
            "process_alive": self.process_alive,
            "endpoint_reachable": self.endpoint_reachable,
            "expected_model": self.expected_model,
            "served_models": list(self.served_models),
            "identity_match": self.identity_match,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class _ShutdownObservation:
    pid_alive: bool
    process_group_alive: bool
    port_open: bool

    @property
    def complete(self) -> bool:
        return not (self.pid_alive or self.process_group_alive or self.port_open)


def _runtime_root(profile: Mapping[str, Any], repository_root: str | Path = ".") -> Path:
    raw = profile["topology"]["process_policy"]["pid_root"]
    root = (Path(repository_root) / raw).resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def _pid_path(root: Path, component: str) -> Path:
    return root / f"{component}.pid.json"


def _log_path(root: Path, component: str) -> Path:
    return root / f"{component}.log"


def _read_pid(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _pid_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _pgid_alive(pgid: int | None) -> bool:
    if not isinstance(pgid, int) or pgid <= 0:
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _port_open(host: str, port: int, *, timeout_seconds: float = 0.1) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout_seconds):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def _shutdown_observation(
    profile: Mapping[str, Any],
    component: str,
    *,
    pid: int | None,
    pgid: int | None,
) -> _ShutdownObservation:
    endpoint = profile[component]["endpoint"]
    return _ShutdownObservation(
        pid_alive=_pid_alive(pid),
        process_group_alive=_pgid_alive(pgid),
        port_open=_port_open(str(endpoint["host"]), int(endpoint["port"])),
    )


def _wait_for_shutdown(
    profile: Mapping[str, Any],
    component: str,
    *,
    pid: int | None,
    pgid: int | None,
    timeout_seconds: float,
    poll_interval_seconds: float = 0.25,
) -> _ShutdownObservation:
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    observation = _shutdown_observation(profile, component, pid=pid, pgid=pgid)
    while not observation.complete:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval_seconds, remaining))
        observation = _shutdown_observation(profile, component, pid=pid, pgid=pgid)
    return observation


def _send_process_group_signal(pgid: int | None, sig: signal.Signals) -> bool:
    if not _pgid_alive(pgid):
        return False
    try:
        os.killpg(int(pgid), sig)
        return True
    except ProcessLookupError:
        return False


def _process_group_members(pgid: int | None) -> tuple[int, ...] | None:
    if not isinstance(pgid, int) or pgid <= 0:
        return ()
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,pgid="],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    members: list[int] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            member_pid, member_pgid = (int(value) for value in fields)
        except ValueError:
            continue
        if member_pgid == pgid:
            members.append(member_pid)
    return tuple(sorted(set(members)))


def _residual_process_count(pid: int | None, pgid: int | None) -> int:
    members = _process_group_members(pgid)
    if members is not None:
        return len(members)
    return int(_pid_alive(pid) or _pgid_alive(pgid))


def _pid_record_errors(
    profile: Mapping[str, Any],
    component: str,
    record: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    pid = record.get("pid")
    pgid = record.get("process_group_id")
    if record.get("component") != component:
        errors.append(f"component mismatch: expected {component!r}")
    if not isinstance(pid, int) or pid <= 0:
        errors.append("PID is missing or invalid")
    if not isinstance(pgid, int) or pgid <= 0:
        errors.append("process_group_id is missing or invalid")
    if isinstance(pid, int) and isinstance(pgid, int) and pid != pgid:
        errors.append("PID record does not own a separate process group")
    expected_hash = profile.get("integrity", {}).get("profile_sha256")
    if expected_hash and record.get("profile_sha256") != expected_hash:
        errors.append("profile SHA-256 ownership mismatch")
    return errors


def fetch_served_models(server: Mapping[str, Any], timeout_seconds: float = 5.0) -> tuple[str, ...]:
    request = urllib.request.Request(
        model_identity_url(server),
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
        return ()

    raw_models = payload.get("data") or payload.get("models") or []
    result: list[str] = []
    for item in raw_models:
        if isinstance(item, dict):
            value = item.get("id") or item.get("model") or item.get("name")
        else:
            value = item
        if value is not None:
            result.append(str(value))
    return tuple(result)


def fetch_loaded_model(
    server: Mapping[str, Any],
    timeout_seconds: float = 5.0,
) -> str | None:
    """Confirm the exact model actually loaded by the server process.

    mlx-vlm enumerates the entire local Hugging Face cache on ``/v1/models``, so a
    listed model ID alone does not prove it is the loaded model. When the server
    exposes an extra health payload with a ``loaded_model`` field it is used as the
    authoritative identity source.
    """
    endpoint = server["endpoint"]
    url = _origin(endpoint["base_url"]) + "/health"
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    value = payload.get("loaded_model")
    return str(value) if value is not None else None


def component_status(
    profile: Mapping[str, Any],
    component: str,
    *,
    repository_root: str | Path = ".",
    endpoint_timeout_seconds: float = 5.0,
) -> ComponentStatus:
    if component not in {"vision", "llm"}:
        raise ValueError(f"unsupported component: {component}")
    root = _runtime_root(profile, repository_root)
    pid_record = _read_pid(_pid_path(root, component)) or {}
    pid = pid_record.get("pid")
    pgid = pid_record.get("process_group_id")
    alive = _pid_alive(pid) or _pgid_alive(pgid)
    server = profile[component]
    models = fetch_served_models(server, endpoint_timeout_seconds)
    loaded_model = fetch_loaded_model(server, endpoint_timeout_seconds)
    expected = server["model"]["model_id"]
    match = expected in models and (loaded_model is None or loaded_model == expected)
    if not models:
        detail = "model endpoint is unreachable or returned no model identities"
    elif not match:
        if loaded_model is not None and loaded_model != expected:
            detail = f"served model identity mismatch: expected {expected!r}, loaded {loaded_model!r}"
        else:
            detail = f"served model identity mismatch: expected {expected!r}"
    elif not alive:
        detail = "endpoint matches but the process is not owned by this profile runtime"
    else:
        detail = "process and model identity are healthy"
    return ComponentStatus(
        component=component,
        pid=pid if isinstance(pid, int) else None,
        process_group_id=pgid if isinstance(pgid, int) else None,
        process_alive=alive,
        endpoint_reachable=bool(models),
        expected_model=expected,
        served_models=models,
        identity_match=match,
        detail=detail,
    )


def preflight(profile: dict[str, Any], *, require_runtime: bool = False) -> list[dict[str, Any]]:
    validate_profile(
        profile,
        mode=str(profile.get("status") or "draft"),
        require_integrity=profile.get("status") == "frozen",
    )
    rows = [component_status(profile, component).as_dict() for component in ("vision", "llm")]
    if require_runtime:
        errors = [
            f"{row['component']}: {row['detail']}"
            for row in rows
            if not (row["process_alive"] and row["identity_match"])
        ]
        if errors:
            raise ProfileValidationError(errors)
    return rows


def _components_for_start(profile: Mapping[str, Any], requested: str) -> list[str]:
    if requested in {"vision", "llm"}:
        return [requested]
    if requested != "all":
        raise ProfileValidationError([f"unknown component selector: {requested}"])
    mode = profile["topology"]["operational_mode"]
    if mode == "dual_server_sequential":
        raise ProfileValidationError(
            ["operational_mode=dual_server_sequential requires --component vision or --component llm"]
        )
    if mode == "single_multimodal_server":
        return ["vision"]
    return ["vision", "llm"]


def start_runtime(
    profile: dict[str, Any],
    *,
    component: str = "all",
    repository_root: str | Path = ".",
    env: Mapping[str, str] | None = None,
    wait_seconds: int = 180,
) -> list[dict[str, Any]]:
    """Start selected frozen-profile servers and verify exact model identity."""
    validate_profile(profile, mode="frozen", require_integrity=True)
    runtime_env = dict(os.environ)
    if env:
        runtime_env.update(env)
    root = _runtime_root(profile, repository_root)
    started: list[str] = []
    try:
        for name in _components_for_start(profile, component):
            existing = component_status(profile, name, repository_root=repository_root)
            if existing.process_alive:
                if not existing.identity_match:
                    raise ProfileValidationError(
                        [f"{name}: an owned process is alive but serves the wrong model identity"]
                    )
                started.append(name)
                continue

            command = resolve_command(profile[name]["runtime"]["command"], runtime_env)
            log_path = _log_path(root, name)
            log_stream = log_path.open("ab")
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(Path(repository_root).resolve()),
                    env=runtime_env,
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            finally:
                log_stream.close()
            record = {
                "component": name,
                "pid": process.pid,
                "process_group_id": process.pid,
                "command": command,
                "profile_sha256": profile["integrity"]["profile_sha256"],
                "started_at_epoch": time.time(),
            }
            _pid_path(root, name).write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            started.append(name)

            deadline = time.monotonic() + wait_seconds
            last = component_status(profile, name, repository_root=repository_root)
            while time.monotonic() < deadline:
                if not _pid_alive(process.pid):
                    break
                last = component_status(profile, name, repository_root=repository_root)
                if last.identity_match:
                    break
                time.sleep(2)
            if not last.identity_match:
                raise ProfileValidationError([f"{name}: {last.detail}; see {log_path}"])
        return [
            component_status(profile, name, repository_root=repository_root).as_dict()
            for name in started
        ]
    except Exception:
        for name in reversed(started):
            try:
                stop_runtime(profile, component=name, repository_root=repository_root)
            except Exception:
                pass
        raise


def _stop_one(profile: Mapping[str, Any], component: str, repository_root: str | Path) -> dict[str, Any]:
    root = _runtime_root(profile, repository_root)
    path = _pid_path(root, component)
    record = _read_pid(path)
    endpoint = profile[component]["endpoint"]
    port = int(endpoint["port"])
    started_at = time.monotonic()

    if not record:
        port_open = _port_open(str(endpoint["host"]), port)
        return {
            "component": component,
            "stopped": not port_open,
            "residual": port_open,
            "residual_process_count": 0,
            "pid": None,
            "process_group_id": None,
            "port": port,
            "port_free": not port_open,
            "pid_file_removed": not path.exists(),
            "graceful_signal_sent": False,
            "force_kill_used": False,
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
            "detail": (
                "already stopped; no PID record and endpoint port is free"
                if not port_open
                else "no PID record; endpoint port remains in use and cannot be stopped safely"
            ),
        }

    ownership_errors = _pid_record_errors(profile, component, record)
    pid = record.get("pid") if isinstance(record.get("pid"), int) else None
    pgid = record.get("process_group_id") if isinstance(record.get("process_group_id"), int) else None
    if ownership_errors:
        port_open = _port_open(str(endpoint["host"]), port)
        return {
            "component": component,
            "stopped": False,
            "residual": True,
            "residual_process_count": _residual_process_count(pid, pgid),
            "pid": pid,
            "process_group_id": pgid,
            "port": port,
            "port_free": not port_open,
            "pid_file_removed": False,
            "graceful_signal_sent": False,
            "force_kill_used": False,
            "elapsed_seconds": round(time.monotonic() - started_at, 3),
            "detail": "PID ownership verification failed: " + "; ".join(ownership_errors),
        }

    policy = profile["topology"]["process_policy"]
    graceful = float(policy["graceful_shutdown_seconds"])
    forced = float(policy["force_kill_seconds"])
    observation = _shutdown_observation(profile, component, pid=pid, pgid=pgid)
    graceful_signal_sent = False
    force_kill_used = False

    if not observation.complete:
        graceful_signal_sent = _send_process_group_signal(pgid, signal.SIGTERM)
        observation = _wait_for_shutdown(
            profile,
            component,
            pid=pid,
            pgid=pgid,
            timeout_seconds=graceful,
        )

    if not observation.complete:
        force_kill_used = _send_process_group_signal(pgid, signal.SIGKILL)
        observation = _wait_for_shutdown(
            profile,
            component,
            pid=pid,
            pgid=pgid,
            timeout_seconds=forced,
        )

    residual_process_count = _residual_process_count(pid, pgid)
    residual = not observation.complete or residual_process_count > 0
    pid_file_error: str | None = None
    if not residual:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            pid_file_error = f"cannot remove PID record: {type(exc).__name__}: {exc}"
    pid_file_removed = not path.exists()
    stopped = not residual and pid_file_removed

    if stopped:
        if force_kill_used:
            detail = "stopped cleanly after force-kill verification"
        elif graceful_signal_sent:
            detail = "stopped cleanly within graceful shutdown period"
        else:
            detail = "already stopped; stale PID record removed"
    else:
        failures: list[str] = []
        if observation.process_group_alive:
            failures.append("residual process group remains")
        if observation.pid_alive:
            failures.append("owned PID remains alive")
        if observation.port_open:
            failures.append(f"port {port} remains in use")
        if residual_process_count:
            failures.append(f"residual process count is {residual_process_count}")
        if pid_file_error:
            failures.append(pid_file_error)
        if not pid_file_removed:
            failures.append("PID record retained")
        detail = "; ".join(failures) or "shutdown verification failed"

    return {
        "component": component,
        "stopped": stopped,
        "residual": residual,
        "residual_process_count": residual_process_count,
        "pid": pid,
        "process_group_id": pgid,
        "port": port,
        "port_free": not observation.port_open,
        "pid_file_removed": pid_file_removed,
        "graceful_signal_sent": graceful_signal_sent,
        "force_kill_used": force_kill_used,
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
        "detail": detail,
    }


def stop_runtime(
    profile: Mapping[str, Any],
    *,
    component: str = "all",
    repository_root: str | Path = ".",
) -> list[dict[str, Any]]:
    names = ["vision", "llm"] if component == "all" else [component]
    if any(name not in {"vision", "llm"} for name in names):
        raise ValueError(f"unsupported component selector: {component}")
    rows = [_stop_one(profile, name, repository_root) for name in reversed(names)]
    failures = [row for row in rows if not row["stopped"]]
    if failures:
        raise ProfileValidationError([f"{row['component']}: {row['detail']}" for row in failures])
    return rows
