"""Dependency-free structural quality gate for the Python codebase."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (PROJECT_ROOT / "src", PROJECT_ROOT / "scripts")
BUDGET_PATH = PROJECT_ROOT / "config" / "quality" / "code_health_budget.json"


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def _python_files() -> list[Path]:
    return sorted(
        path
        for root in SOURCE_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _load_budget() -> dict:
    return json.loads(BUDGET_PATH.read_text(encoding="utf-8"))


def _mutable_model_defaults(tree: ast.AST, path: Path) -> Iterable[Violation]:
    if path.name != "schemas.py":
        return []
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign) or statement.value is None:
                continue
            if isinstance(statement.value, (ast.List, ast.Dict, ast.Set)):
                violations.append(
                    Violation(
                        _relative(path),
                        statement.lineno,
                        "mutable schema default; use Field(default_factory=...)",
                    )
                )
    return violations


def _forbidden_patterns(tree: ast.AST, path: Path) -> Iterable[Violation]:
    relative = _relative(path)
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "on_event":
                violations.append(
                    Violation(relative, node.lineno, "FastAPI on_event is forbidden; use lifespan")
                )
        if isinstance(node, ast.FunctionDef) and node.name == "_user_id":
            violations.append(
                Violation(
                    relative,
                    node.lineno,
                    "duplicate request-user helper; use get_optional_user_id",
                )
            )
        if isinstance(node, ast.Name) and node.id == "remove_legacy_ui_auth_routes":
            violations.append(
                Violation(relative, node.lineno, "legacy route mutation is forbidden")
            )
    return violations


def _size_violations(
    tree: ast.AST,
    path: Path,
    *,
    max_module_lines: int,
    max_function_lines: int,
    tracked_limits: dict[str, int],
    tracked_function_limits: dict[str, int],
) -> Iterable[Violation]:
    relative = _relative(path)
    line_count = len(path.read_text(encoding="utf-8").splitlines())
    limit = tracked_limits.get(relative, max_module_lines)
    violations: list[Violation] = []
    if line_count > limit:
        violations.append(
            Violation(relative, 1, f"module has {line_count} lines; budget is {limit}")
        )
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        length = (node.end_lineno or node.lineno) - node.lineno + 1
        function_key = f"{relative}::{node.name}"
        function_limit = tracked_function_limits.get(function_key, max_function_lines)
        if length > function_limit:
            violations.append(
                Violation(
                    relative,
                    node.lineno,
                    f"function {node.name!r} has {length} lines; budget is {function_limit}",
                )
            )
    return violations


def collect_violations() -> list[Violation]:
    budget = _load_budget()
    violations: list[Violation] = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(
                Violation(_relative(path), exc.lineno or 1, f"syntax error: {exc.msg}")
            )
            continue
        violations.extend(_mutable_model_defaults(tree, path))
        violations.extend(_forbidden_patterns(tree, path))
        violations.extend(
            _size_violations(
                tree,
                path,
                max_module_lines=int(budget["max_python_module_lines"]),
                max_function_lines=int(budget["max_function_lines"]),
                tracked_limits={
                    str(key): int(value)
                    for key, value in budget["tracked_module_line_limits"].items()
                },
                tracked_function_limits={
                    str(key): int(value)
                    for key, value in budget.get("tracked_function_line_limits", {}).items()
                },
            )
        )

    main_path = PROJECT_ROOT / "src" / "main.py"
    main_lines = len(main_path.read_text(encoding="utf-8").splitlines())
    if main_lines > 20:
        violations.append(
            Violation("src/main.py", 1, f"ASGI entry point has {main_lines} lines; budget is 20")
        )
    return sorted(violations, key=lambda item: (item.path, item.line, item.message))


def main() -> int:
    violations = collect_violations()
    if violations:
        print("CODE_HEALTH_FAILED")
        for violation in violations:
            print(violation.render())
        return 1
    print("CODE_HEALTH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
