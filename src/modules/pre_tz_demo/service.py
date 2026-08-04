"""Public entry point for the executable PRE-TZ demonstration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.modules.pre_tz_demo.manifest import (
    build_manifest,
    failure_manifest,
    write_manifest,
)
from src.modules.pre_tz_demo.pipeline import DEMO_VERSION, execute_demo
from src.modules.pre_tz_demo.workspace import (
    isolated_demo_environment,
    prepare_demo_paths,
)


def run_messy_demo(
    workspace: str | Path,
    *,
    fixture_path: str | Path | None = None,
    reset: bool = True,
    respondent_count: int = 12,
) -> dict[str, Any]:
    """Run the complete PRE-TZ pipeline against a deliberately messy local CSV."""

    paths = prepare_demo_paths(
        workspace,
        fixture_path=fixture_path,
        reset=reset,
        respondent_count=respondent_count,
    )
    with isolated_demo_environment(paths):
        try:
            manifest = build_manifest(
                paths,
                execute_demo(paths, respondent_count=respondent_count),
            )
            write_manifest(paths, manifest)
            return manifest
        except Exception as exc:
            write_manifest(paths, failure_manifest(paths, exc))
            raise


__all__ = ["DEMO_VERSION", "run_messy_demo"]
