#!/usr/bin/env python3
from pathlib import Path

from src.shared.config.settings import get_settings
from src.shared.security.hardening import validate_security_posture


def main() -> int:
    settings = get_settings()
    for raw in (settings.storage_root, settings.exports_root, settings.backup_root):
        Path(raw).expanduser().mkdir(parents=True, exist_ok=True)
    posture = validate_security_posture(settings)
    for check in posture.checks:
        print(f"{check.status.upper():16} {check.key}: {check.message}")
    print(f"SECURITY_POSTURE={posture.status}")
    if posture.blocking_errors:
        print("SECURITY_POSTURE_BLOCKED")
        return 1
    print("SECURITY_POSTURE_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
