"""CTA-BENCH-002 target-hardware LLM/VLM/OCR benchmark harness.

Runs frozen OCR/VLM/LLM/hybrid case sets against local server candidates,
manages runtime lifecycle, captures resource metrics, and produces the
sanitized artifact set described in the CTA-BENCH-002 task specification.
"""

from scripts.cta_bench_002.spec import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    candidate_catalog,
)

__all__ = ["BENCHMARK_ID", "BENCHMARK_VERSION", "candidate_catalog"]
