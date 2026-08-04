"""Pure scalar normalization functions with evidence-preserving issues."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_TEXT_FIELDS = {
    "campaign_reference",
    "creative_reference",
    "platform",
    "placement_type",
    "format",
    "audience",
    "brand",
    "product",
}


def issue(code: str, message: str, *, severity: str, **context: Any) -> dict:
    return {"code": code, "message": message, "severity": severity, "context": context}

def normalize_field(target: str, raw: Any):
    if target in _TEXT_FIELDS:
        value = str(raw).strip()
        if len(value) > 512:
            return (
                value[:512],
                "trim_and_truncate_text",
                issue(
                    "normalized_text_truncated",
                    "The normalized text exceeded 512 characters and was truncated; the raw value is preserved in provenance.",
                    severity="warning",
                    original_length=len(value),
                ),
            )
        return value, "trim_text", None
    if target in {"impressions", "clicks"}:
        return normalize_integer(raw)
    if target == "ctr":
        return normalize_ctr(raw)
    if target == "date":
        return normalize_date(raw)
    return raw, "identity", None


def normalize_integer(raw: Any):
    if isinstance(raw, bool):
        return None, "parse_failed", parseissue("integer", raw)
    if isinstance(raw, int):
        return raw, "integer", None
    if isinstance(raw, float) and raw.is_integer():
        return int(raw), "integral_number_to_integer", None
    text = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text), "text_to_integer", None
    match = re.fullmatch(r"([-+]?\d+)[.,](0+)", text)
    if match:
        return int(match.group(1)), "integral_decimal_text_to_integer", None
    return None, "parse_failed", parseissue("integer", raw)


def normalize_ctr(raw: Any):
    if isinstance(raw, bool):
        return None, "parse_failed", parseissue("CTR number", raw)
    if isinstance(raw, (int, float)):
        return float(raw), "number", None
    text = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None, "parse_failed", parseissue("CTR number", raw)
    if percent:
        return number / 100.0, "percent_text_to_ratio", None
    return number, "text_to_number", None


def normalize_date(raw: Any):
    if isinstance(raw, datetime):
        return raw.date(), "datetime_to_date", None
    if isinstance(raw, date):
        return raw, "date", None
    text = str(raw).strip()
    for fmt in (
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt).date(), "text_to_date", None
        except ValueError:
            continue
    return None, "parse_failed", parseissue("date", raw)


def parseissue(expected: str, raw: Any):
    return issue(
        "value_parse_failed",
        f"The source value could not be normalized as {expected}; the raw value is preserved.",
        severity="warning",
        raw_value=raw,
        expected=expected,
    )
