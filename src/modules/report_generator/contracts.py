"""Stable report mode and format contracts shared by API and service layers."""

from __future__ import annotations

REPORT_MODES = frozenset({"internal", "client_facing"})
REPORT_FORMATS = frozenset({"json", "markdown", "html", "pdf_stub"})


def supported_values(values: frozenset[str]) -> str:
    return ", ".join(sorted(values))
