#!/usr/bin/env python3
"""CTA-MODEL-001 production-profile CLI.

This CLI never downloads a model. It validates or seals the deployment contract,
renders the existing CTA application settings, checks model identity on loopback
endpoints, and controls only processes explicitly described by a frozen profile.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.shared.model_profile.profile import (  # noqa: E402
    DEFAULT_PROFILE_PATH,
    ProfileValidationError,
    env_text,
    load_profile,
    parse_env_text,
    seal_profile,
    validate_application_env,
    validate_profile,
)
from src.shared.model_profile.runtime import (  # noqa: E402
    component_status,
    preflight,
    start_runtime,
    stop_runtime,
)


def _load(path: str) -> dict:
    return load_profile(path)


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _cmd_validate(args: argparse.Namespace) -> int:
    profile = _load(args.profile)
    errors = validate_profile(
        profile,
        mode=args.mode,
        require_integrity=args.mode == "frozen",
        raise_on_error=False,
    )
    result = {
        "task_id": "CTA-MODEL-001",
        "profile": args.profile,
        "mode": args.mode,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }
    _print_json(result)
    return 0 if not errors else 1


def _cmd_render_env(args: argparse.Namespace) -> int:
    profile = _load(args.profile)
    text = env_text(profile)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(path)
    else:
        print(text, end="")
    return 0


def _cmd_check_env(args: argparse.Namespace) -> int:
    profile = _load(args.profile)
    env = parse_env_text(Path(args.env_file).read_text(encoding="utf-8"))
    errors = validate_application_env(profile, env)
    _print_json({"status": "PASS" if not errors else "FAIL", "errors": errors})
    return 0 if not errors else 1


def _cmd_seal(args: argparse.Namespace) -> int:
    source = Path(args.profile)
    destination = Path(args.output)
    if destination.exists() and not args.force:
        raise ProfileValidationError([f"output already exists: {destination}; pass --force to replace"])
    profile = seal_profile(_load(str(source)), sealed_at=args.sealed_at)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _print_json(
        {
            "status": "SEALED",
            "output": str(destination),
            "profile_sha256": profile["integrity"]["profile_sha256"],
        }
    )
    return 0


def _cmd_preflight(args: argparse.Namespace) -> int:
    rows = preflight(_load(args.profile), require_runtime=args.require_runtime)
    _print_json({"status": "PASS", "components": rows})
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    profile = _load(args.profile)
    names = ["vision", "llm"] if args.component == "all" else [args.component]
    rows = [
        component_status(profile, name, repository_root=args.repository_root).as_dict()
        for name in names
    ]
    healthy = all(row["process_alive"] and row["identity_match"] for row in rows)
    _print_json({"status": "HEALTHY" if healthy else "NOT_READY", "components": rows})
    return 0 if healthy else 1


def _cmd_start(args: argparse.Namespace) -> int:
    rows = start_runtime(
        _load(args.profile),
        component=args.component,
        repository_root=args.repository_root,
        wait_seconds=args.wait_seconds,
    )
    _print_json({"status": "STARTED", "components": rows})
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    rows = stop_runtime(
        _load(args.profile),
        component=args.component,
        repository_root=args.repository_root,
    )
    _print_json({"status": "STOPPED", "components": rows})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.set_defaults(func=None)
    subparsers = parser.add_subparsers(dest="command")

    def profile_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH))

    validate = subparsers.add_parser("validate", help="Validate schema and semantic constraints.")
    profile_arg(validate)
    validate.add_argument("--mode", choices=("draft", "frozen"), required=True)
    validate.set_defaults(func=_cmd_validate)

    render = subparsers.add_parser("render-env", help="Render deterministic CTA_* application settings.")
    profile_arg(render)
    render.add_argument("--output")
    render.set_defaults(func=_cmd_render_env)

    check_env = subparsers.add_parser("check-env", help="Reject application settings that drift from the profile.")
    profile_arg(check_env)
    check_env.add_argument("--env-file", required=True)
    check_env.set_defaults(func=_cmd_check_env)

    seal = subparsers.add_parser("seal", help="Freeze and integrity-bind a fully populated draft profile.")
    profile_arg(seal)
    seal.add_argument("--output", required=True)
    seal.add_argument("--sealed-at", help="RFC 3339 UTC time; defaults to current UTC.")
    seal.add_argument("--force", action="store_true")
    seal.set_defaults(func=_cmd_seal)

    preflight_parser = subparsers.add_parser("preflight", help="Check profile and optional live model identities.")
    profile_arg(preflight_parser)
    preflight_parser.add_argument("--require-runtime", action="store_true")
    preflight_parser.set_defaults(func=_cmd_preflight)

    for name, function in (("status", _cmd_status), ("start", _cmd_start), ("stop", _cmd_stop)):
        command = subparsers.add_parser(name)
        profile_arg(command)
        command.add_argument("--component", choices=("all", "vision", "llm"), default="all")
        command.add_argument("--repository-root", default=".")
        if name == "start":
            command.add_argument("--wait-seconds", type=int, default=180)
        command.set_defaults(func=function)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.func is None:
        parser.print_help()
        return 2
    try:
        return int(args.func(args))
    except ProfileValidationError as exc:
        _print_json({"status": "FAIL", "errors": exc.errors})
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json({"status": "FAIL", "errors": [f"{type(exc).__name__}: {exc}"]})
        return 1


if __name__ == "__main__":
    sys.exit(main())
