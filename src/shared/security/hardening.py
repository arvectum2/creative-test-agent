from __future__ import annotations

import ipaddress
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from src.shared.config.settings import Settings, get_settings


@dataclass(frozen=True)
class SecurityCheck:
    key: str
    status: str
    message: str
    blocking: bool = False


@dataclass(frozen=True)
class SecurityPosture:
    status: str
    checks: tuple[SecurityCheck, ...]

    @property
    def blocking_errors(self) -> tuple[SecurityCheck, ...]:
        return tuple(item for item in self.checks if item.blocking and item.status == "fail")

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "blocking_error_count": len(self.blocking_errors),
            "checks": [
                {
                    "key": item.key,
                    "status": item.status,
                    "message": item.message,
                    "blocking": item.blocking,
                }
                for item in self.checks
            ],
        }


def validate_security_posture(settings: Settings | None = None) -> SecurityPosture:
    settings = settings or get_settings()
    checks: list[SecurityCheck] = []

    host_loopback = is_loopback_host(settings.host)
    checks.append(
        SecurityCheck(
            "local_bind",
            "pass" if host_loopback or not settings.local_only_mode else "fail",
            f"Application binds to {settings.host}." if host_loopback else f"Application host {settings.host} is not loopback.",
            blocking=settings.local_only_mode,
        )
    )
    public_local = is_loopback_url(settings.public_base_url)
    checks.append(
        SecurityCheck(
            "local_public_base_url",
            "pass" if public_local or not settings.local_only_mode else "fail",
            f"Public base URL: {settings.public_base_url}.",
            blocking=settings.local_only_mode,
        )
    )
    trusted_nonlocal = [host for host in settings.trusted_hosts_list if not is_loopback_host(host)]
    checks.append(
        SecurityCheck(
            "trusted_hosts",
            "pass" if not (settings.local_only_mode and trusted_nonlocal) else "fail",
            "Trusted hosts are loopback-only." if not trusted_nonlocal else f"Non-loopback trusted hosts: {', '.join(trusted_nonlocal)}.",
            blocking=settings.local_only_mode,
        )
    )
    checks.append(
        SecurityCheck(
            "cloud_llm_disabled",
            "pass" if not settings.allow_cloud_llm else "fail",
            "Cloud LLM access is disabled." if not settings.allow_cloud_llm else "Cloud LLM access is enabled.",
            blocking=settings.local_only_mode,
        )
    )
    auth_secret_ok = not settings.enable_auth or (
        bool(settings.secret_key)
        and settings.secret_key != "change-this-secret-key"
        and len(settings.secret_key) >= 32
    )
    checks.append(
        SecurityCheck(
            "session_secret",
            "pass" if auth_secret_ok else "fail",
            "Session secret policy is satisfied." if auth_secret_ok else "Authentication requires a unique secret of at least 32 characters.",
            blocking=settings.enable_auth,
        )
    )
    if not settings.enable_auth:
        password_status = "pass"
        password_message = "Authentication is disabled; password policy is not active."
    elif settings.password_min_length >= 12:
        password_status = "pass"
        password_message = f"Minimum password length is {settings.password_min_length}."
    else:
        password_status = "warn"
        password_message = (
            f"Minimum password length is {settings.password_min_length}; 12 or more is recommended."
        )
    checks.append(
        SecurityCheck(
            "password_policy",
            password_status,
            password_message,
        )
    )

    for key, raw_path in (
        ("storage_root", settings.storage_root),
        ("exports_root", settings.exports_root),
        ("backup_root", settings.backup_root),
    ):
        checks.extend(_path_checks(key, Path(raw_path)))

    database_ok, database_message = _database_locality(settings.database_url)
    checks.append(
        SecurityCheck(
            "database_locality",
            "pass" if database_ok or not settings.local_only_mode else "fail",
            database_message,
            blocking=settings.local_only_mode,
        )
    )
    cors_ok = not settings.cors_origins_list or all(is_loopback_url(origin) for origin in settings.cors_origins_list)
    checks.append(
        SecurityCheck(
            "cors_origins",
            "pass" if cors_ok or not settings.local_only_mode else "fail",
            "CORS is disabled or loopback-only." if cors_ok else "Non-loopback CORS origins are configured.",
            blocking=settings.local_only_mode,
        )
    )

    if any(item.blocking and item.status == "fail" for item in checks):
        overall = "blocked"
    elif any(item.status in {"fail", "warn"} for item in checks):
        overall = "review_required"
    else:
        overall = "hardened"
    return SecurityPosture(status=overall, checks=tuple(checks))


def ensure_within_root(path: str | Path, root: str | Path) -> Path:
    """Resolve a stored path while keeping it inside ``root``.

    Absolute paths are checked as supplied. Relative paths are storage-relative
    identifiers and are resolved from the configured root, never from the
    process working directory. Resolving after the join also rejects ``..`` and
    symlink escapes.
    """

    root_path = Path(root).expanduser().resolve(strict=False)
    raw_path = Path(path).expanduser()
    candidate = (
        raw_path.resolve(strict=False)
        if raw_path.is_absolute()
        else (root_path / raw_path).resolve(strict=False)
    )
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"Path is outside configured root: {candidate}") from exc
    return candidate


def safe_download_name(filename: str, fallback: str = "download.bin") -> str:
    value = (filename or "").replace("\x00", "").replace("/", "_").replace("\\", "_")
    value = "".join(character for character in value if ord(character) >= 32 and ord(character) != 127)
    value = value.strip(" .")[:180]
    return value or fallback


def is_loopback_host(host: str) -> bool:
    value = (host or "").strip().lower().strip("[]").rstrip(".")
    if value in {"localhost", "localhost.localdomain", "test", "testserver"}:
        return True
    if value.startswith("localhost:"):
        return True
    try:
        return ipaddress.ip_address(value.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


def is_loopback_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and is_loopback_host(parsed.hostname or "")


def _path_checks(key: str, path: Path) -> list[SecurityCheck]:
    absolute = path.expanduser().resolve(strict=False)
    parent = absolute if absolute.exists() else absolute.parent
    writable = parent.exists() and os.access(parent, os.W_OK)
    symlink = path.is_symlink()
    world_writable = False
    if parent.exists():
        try:
            world_writable = bool(parent.stat().st_mode & stat.S_IWOTH)
        except OSError:
            pass
    return [
        SecurityCheck(
            f"{key}_writable",
            "pass" if writable else "warn",
            f"{key} is writable." if writable else f"{key} is not currently writable: {parent}",
        ),
        SecurityCheck(
            f"{key}_symlink",
            "warn" if symlink else "pass",
            f"{key} is a symbolic link." if symlink else f"{key} is not a symbolic link.",
        ),
        SecurityCheck(
            f"{key}_world_writable",
            "warn" if world_writable else "pass",
            f"{key} is world-writable." if world_writable else f"{key} is not world-writable.",
        ),
    ]


def _database_locality(database_url: str) -> tuple[bool, str]:
    normalized = database_url.lower()
    if normalized.startswith(("sqlite:///", "sqlite+pysqlite:///")):
        return True, "SQLite database is local."
    parsed = urlparse(database_url)
    host = parsed.hostname or ""
    if is_loopback_host(host):
        return True, f"Database host is loopback: {host}."
    return False, f"Database host is non-local: {host or 'unknown'}."
