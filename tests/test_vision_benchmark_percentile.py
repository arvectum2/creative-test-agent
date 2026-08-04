"""Regression tests for local benchmark percentile aggregation."""

from src.shared.vision.benchmark_execution import _percentile


def test_percentile_handles_empty_and_single_value_inputs():
    assert _percentile([], 0.95) is None
    assert _percentile([12.5], 0.95) == 12.5


def test_percentile_interpolates_sorted_values():
    values = [40.0, 10.0, 20.0, 30.0]

    assert _percentile(values, 0.50) == 25.0
    assert _percentile(values, 0.95) == 38.5


def test_percentile_preserves_sample_bounds():
    values = [9.0, 3.0, 6.0]

    assert _percentile(values, 0.0) == 3.0
    assert _percentile(values, 1.0) == 9.0
