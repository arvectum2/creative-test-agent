"""Keep the repository's structural debt budget executable in CI."""

from scripts.check_code_health import collect_violations


def test_structural_code_health_budget():
    assert collect_violations() == []
