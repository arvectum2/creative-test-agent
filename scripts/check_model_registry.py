#!/usr/bin/env python3
"""Verify that runtime and Alembic register the same SQLAlchemy model modules.

The application currently keeps explicit model imports in two places:

- ``src/shared/db/session.py`` for ``Base.metadata.create_all()``;
- ``migrations/env.py`` for Alembic metadata.

If these lists drift, local startup can create a table that Alembic does not know
about. This check is intentionally static so it can fail before a database is
created.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_REGISTRY = ROOT / "src" / "shared" / "db" / "session.py"
ALEMBIC_REGISTRY = ROOT / "migrations" / "env.py"
MODEL_PREFIX = "src.modules."
MODEL_SUFFIX = ".models"


def collect_model_imports(path: Path) -> set[str]:
    """Return explicit ``src.modules.*.models`` imports from *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            name = alias.name
            if name.startswith(MODEL_PREFIX) and name.endswith(MODEL_SUFFIX):
                imports.add(name)

    return imports


def main() -> int:
    runtime = collect_model_imports(RUNTIME_REGISTRY)
    alembic = collect_model_imports(ALEMBIC_REGISTRY)

    missing_from_alembic = sorted(runtime - alembic)
    missing_from_runtime = sorted(alembic - runtime)

    print("SQLAlchemy model registry check")
    print(f"  runtime modules: {len(runtime)}")
    print(f"  Alembic modules: {len(alembic)}")

    if missing_from_alembic:
        print("\nMissing from migrations/env.py:")
        for module in missing_from_alembic:
            print(f"  - {module}")

    if missing_from_runtime:
        print("\nMissing from src/shared/db/session.py:")
        for module in missing_from_runtime:
            print(f"  - {module}")

    if missing_from_alembic or missing_from_runtime:
        print("\nModel registry check: FAIL")
        return 1

    print("Model registry check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
