"""Regression guard for the CTA-MODEL-001 frozen LLM runtime dependency contract.

mlx-lm 0.28.3 cannot load model_type=qwen3_5 and fails with:
    ValueError: Model type qwen3_5 not supported

The accepted local runtime is the exact pair:
    mlx-openai-server==1.3.12
    mlx-lm==0.31.3

These tests only verify the dependency contract in the repository. They do not
load models and must stay runnable in CI without local GPU environments.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = (
    PROJECT_ROOT
    / "config"
    / "model_profiles"
    / "runtime"
    / "cta_model_001.llm.requirements.txt"
)
OPERATOR_RUNBOOK = (
    PROJECT_ROOT / "docs" / "local" / "CTA-MODEL-001_MAC_MINI_OPENCODE.md"
)

PINNED = {
    "mlx-openai-server": "1.3.12",
    "mlx-lm": "0.31.3",
}


def _load_pins() -> dict[str, str]:
    if not REQUIREMENTS_PATH.is_file():
        raise AssertionError(f"missing requirements file: {REQUIREMENTS_PATH}")
    pins: dict[str, str] = {}
    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^;=\s]+)$", stripped)
        assert match, f"unpinned requirement line: {line!r}"
        pins[match.group(1)] = match.group(2)
    return pins


def test_frozen_llm_runtime_has_exact_compatible_pins():
    pins = _load_pins()
    assert pins["mlx-openai-server"] == PINNED["mlx-openai-server"]
    assert pins["mlx-lm"] == PINNED["mlx-lm"]


def test_frozen_llm_runtime_forbids_unpinned_entries():
    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = re.match(r"^([A-Za-z0-9_.-]+)", stripped)
        assert name, f"malformed requirement line: {line!r}"
        if name.group(1) in PINNED:
            assert "==" in stripped, f"unpinned {name.group(1)}: {line!r}"
            assert not stripped.startswith(f"{name.group(1)}>="), (
                f"unpinned range for {name.group(1)}: {line!r}"
            )


def test_operator_runbook_installs_llm_runtime_from_contract_file():
    text = OPERATOR_RUNBOOK.read_text(encoding="utf-8")
    assert "cta_model_001.llm.requirements.txt" in text
    assert "-r config/model_profiles/runtime/cta_model_001.llm.requirements.txt" in text
    assert "mlx-lm==0.28.3 cannot load model_type=qwen3_5" in text
    assert "ValueError: Model type qwen3_5 not supported" in text


def test_operator_runbook_pins_mlx_lm_explicitly():
    text = OPERATOR_RUNBOOK.read_text(encoding="utf-8")
    assert "mlx-openai-server==1.3.12" in text
    assert "mlx-lm==0.31.3" in text
