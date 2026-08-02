"""Safe local runtime controls for a frozen CTA-MODEL-001 profile.

The module intentionally does not download models or use a shell. Commands are
read from the integrity-bound profile, whole-token environment references are
resolved, and each server owns a separate process group.
"""

from __future__ import annotations

import json
import os
import signal
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
    if not record:
        return {"component": component, "stopped": True, "residual": False, "detail": "no PID record"}
    pid = record.get("pid")
    pgid = record.get("process_group_id")
    policy = profile["topology"]["process_policy"]
    graceful = int(policy["graceful_shutdown_seconds"])
    forced = int(policy["force_kill_seconds"])

    if _pgid_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + graceful
        while time.monotonic() < deadline and _pgid_alive(pgid):
            time.sleep(0.25)
    if _pgid_alive(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + forced
        while time.monotonic() < deadline and _pgid_alive(pgid):
            time.sleep(0.25)

    residual = _pgid_alive(pgid) or _pid_alive(pid)
    if not residual:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return {
        "component": component,
        "stopped": not residual,
        "residual": residual,
        "pid": pid,
        "process_group_id": pgid,
        "detail": "residual process group remains" if residual else "stopped cleanly",
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
    residual = [row for row in rows if row["residual"]]
    if residual:
        raise ProfileValidationError([f"{row['component']}: {row['detail']}" for row in residual])
    return rows
