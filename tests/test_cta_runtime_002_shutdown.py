from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from src.shared.model_profile.profile import ProfileValidationError
from src.shared.model_profile.runtime import stop_runtime


_SERVER_CODE = r'''
import signal
import socket
import sys
import time

port = int(sys.argv[1])
delay = float(sys.argv[2])
ignore_term = sys.argv[3] == "ignore"
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", port))
server.listen(8)
server.settimeout(0.05)

def shutdown(signum, frame):
    if ignore_term:
        return
    time.sleep(delay)
    server.close()
    raise SystemExit(0)

signal.signal(signal.SIGTERM, shutdown)
print("READY", flush=True)
while True:
    try:
        connection, _ = server.accept()
    except socket.timeout:
        continue
    connection.close()
'''


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _profile(port: int, *, graceful: float = 2.0, forced: float = 1.0) -> dict:
    endpoint = {"host": "127.0.0.1", "port": port}
    return {
        "integrity": {"profile_sha256": "a" * 64},
        "topology": {
            "process_policy": {
                "pid_root": ".local/cta-model-001",
                "graceful_shutdown_seconds": graceful,
                "force_kill_seconds": forced,
            }
        },
        "vision": {"endpoint": dict(endpoint)},
        "llm": {"endpoint": dict(endpoint)},
    }


def _start_server(port: int, *, delay: float, ignore_term: bool = False) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _SERVER_CODE,
            str(port),
            str(delay),
            "ignore" if ignore_term else "handle",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "READY"
    threading.Thread(target=process.wait, daemon=True).start()
    return process


def _write_pid_record(root: Path, process: subprocess.Popen[str], profile: dict) -> Path:
    runtime_root = root / ".local" / "cta-model-001"
    runtime_root.mkdir(parents=True)
    path = runtime_root / "vision.pid.json"
    path.write_text(
        json.dumps(
            {
                "component": "vision",
                "pid": process.pid,
                "process_group_id": os.getpgid(process.pid),
                "profile_sha256": profile["integrity"]["profile_sha256"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_one_stop_waits_for_delayed_graceful_shutdown(tmp_path: Path):
    port = _free_port()
    profile = _profile(port, graceful=2.0, forced=1.0)
    process = _start_server(port, delay=0.4)
    pid_path = _write_pid_record(tmp_path, process, profile)

    started = time.monotonic()
    rows = stop_runtime(profile, component="vision", repository_root=tmp_path)
    elapsed = time.monotonic() - started

    assert elapsed >= 0.35
    assert elapsed < 2.0
    assert rows[0]["stopped"] is True
    assert rows[0]["force_kill_used"] is False
    assert rows[0]["port_free"] is True
    assert rows[0]["pid_file_removed"] is True
    assert rows[0]["residual_process_count"] == 0
    assert not pid_path.exists()


def test_force_kill_is_used_only_after_grace_period(tmp_path: Path):
    port = _free_port()
    profile = _profile(port, graceful=1.0, forced=2.0)
    process = _start_server(port, delay=0.0, ignore_term=True)
    pid_path = _write_pid_record(tmp_path, process, profile)

    started = time.monotonic()
    rows = stop_runtime(profile, component="vision", repository_root=tmp_path)
    elapsed = time.monotonic() - started

    assert elapsed >= 0.9
    assert elapsed < 3.0
    assert rows[0]["stopped"] is True
    assert rows[0]["graceful_signal_sent"] is True
    assert rows[0]["force_kill_used"] is True
    assert rows[0]["port_free"] is True
    assert rows[0]["residual_process_count"] == 0
    assert not pid_path.exists()


def test_stop_refuses_unowned_port_without_pid_record(tmp_path: Path):
    port = _free_port()
    profile = _profile(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", port))
        server.listen(1)
        with pytest.raises(ProfileValidationError, match="no PID record"):
            stop_runtime(profile, component="vision", repository_root=tmp_path)


def test_stale_pid_record_is_removed_only_after_verified_shutdown(tmp_path: Path):
    port = _free_port()
    profile = _profile(port)
    runtime_root = tmp_path / ".local" / "cta-model-001"
    runtime_root.mkdir(parents=True)
    pid_path = runtime_root / "vision.pid.json"
    pid_path.write_text(
        json.dumps(
            {
                "component": "vision",
                "pid": 999_999_991,
                "process_group_id": 999_999_991,
                "profile_sha256": profile["integrity"]["profile_sha256"],
            }
        ),
        encoding="utf-8",
    )

    rows = stop_runtime(profile, component="vision", repository_root=tmp_path)

    assert rows[0]["stopped"] is True
    assert rows[0]["graceful_signal_sent"] is False
    assert rows[0]["force_kill_used"] is False
    assert rows[0]["pid_file_removed"] is True
    assert not pid_path.exists()
