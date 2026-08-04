"""Canonical issue dictionary construction for data-quality rules."""

from __future__ import annotations


def append_issue(
    issues,
    *,
    category,
    code,
    severity,
    message,
    affected_count=1,
    remediation_hint=None,
    scope_type="run",
    scope_id=None,
    source_file_id=None,
    source_table_id=None,
    source_row_id=None,
    source_column_id=None,
    details=None,
):
    issues.append(
        {
            "category": str(category),
            "code": code,
            "severity": str(severity),
            "message": message,
            "affected_count": max(int(affected_count), 0),
            "remediation_hint": remediation_hint,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "source_file_id": source_file_id,
            "source_table_id": source_table_id,
            "source_row_id": source_row_id,
            "source_column_id": source_column_id,
            "details": details or {},
        }
    )
