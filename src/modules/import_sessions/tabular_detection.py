"""Pure detection and normalization helpers for tabular inspection."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import date, datetime, time
from typing import Any

from src.shared.config.settings import get_settings

def detect_header(
    rows: list[tuple[int, list[Any], list[str]]],
    column_count: int,
    scan_limit: int,
) -> tuple[int | None, float | None]:
    candidates: list[tuple[float, int]] = []
    scanned = rows[:scan_limit]
    for position, (row_number, values, _) in enumerate(scanned):
        padded = values + [None] * (column_count - len(values))
        non_empty = [value for value in padded if not is_empty(value)]
        minimum = 1 if column_count == 1 else 2
        if len(non_empty) < minimum:
            continue
        text_ratio = sum(
            classify_value(value) in {"text", "formula"} for value in non_empty
        ) / len(non_empty)
        unique_ratio = len({comparison_text(value) for value in non_empty}) / len(non_empty)
        density = len(non_empty) / max(column_count, 1)
        next_bonus = 0.0
        for _, following, _ in scanned[position + 1 :]:
            following_count = sum(not is_empty(value) for value in following)
            if following_count:
                next_bonus = 1.0 if following_count >= minimum else 0.0
                break
        preamble_bonus = 0.0
        if position:
            previous_counts = [
                sum(not is_empty(value) for value in previous)
                for _, previous, _ in scanned[:position]
            ]
            if previous_counts and max(previous_counts) < len(non_empty):
                preamble_bonus = 0.5
        score = (
            0.35 * density
            + 0.35 * text_ratio
            + 0.20 * unique_ratio
            + 0.07 * next_bonus
            + 0.03 * preamble_bonus
        )
        candidates.append((score, row_number))
    if not candidates:
        return None, None
    score, row_number = sorted(candidates, key=lambda item: (-item[0], item[1]))[0]
    return (None, None) if score < 0.55 else (row_number, round(min(score, 1.0), 4))


def detect_encoding(sample: bytes) -> tuple[str, dict[str, Any] | None]:
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", None
    for encoding in ("utf-8", "cp1251"):
        try:
            sample.decode(encoding)
            return encoding, None
        except UnicodeDecodeError:
            pass
    return "latin-1", warning(
        "encoding_fallback",
        "The file was decoded with latin-1 after UTF-8 and CP1251 failed.",
    )


def detect_delimiter(sample: str) -> str:
    text = "\n".join(line for line in sample.splitlines() if line.strip())
    if not text:
        return ","

    sample_text = text[:65536]
    candidates = (",", ";", "\t", "|")
    sniffed: str | None = None
    try:
        sniffed = csv.Sniffer().sniff(
            sample_text, delimiters="".join(candidates)
        ).delimiter
    except csv.Error:
        pass

    ranked: list[tuple[int, float, float, int, int, int, str]] = []
    for order, candidate in enumerate(candidates):
        try:
            parsed_rows = list(
                csv.reader(io.StringIO(sample_text), delimiter=candidate)
            )
        except csv.Error:
            continue

        widths = [
            len(row)
            for row in parsed_rows
            if any(str(cell).strip() for cell in row)
        ]
        structural_widths = [width for width in widths if width > 1]
        if not structural_widths:
            continue

        width_counts = Counter(structural_widths)
        modal_width, modal_count = max(
            width_counts.items(), key=lambda item: (item[1], item[0])
        )
        structural_support = modal_count * (modal_width - 1)
        modal_consistency = modal_count / len(structural_widths)
        structural_coverage = len(structural_widths) / len(widths)
        ranked.append(
            (
                structural_support,
                modal_consistency,
                structural_coverage,
                modal_width,
                int(candidate == sniffed),
                -order,
                candidate,
            )
        )

    if ranked:
        return max(ranked)[-1]
    return sniffed or ","


def serialize_excel_cell(cell) -> tuple[Any, str]:
    if cell.value is None:
        return None, "empty"
    if cell.data_type == "f":
        formula = str(cell.value)
        return (formula if formula.startswith("=") else f"={formula}"), "formula"
    value = json_value(cell.value)
    return value, classify_value(value)


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def truncate_cell(value: Any) -> tuple[Any, bool]:
    limit = get_settings().tabular_inspection_max_cell_chars
    if not isinstance(value, str) or limit <= 0 or len(value) <= limit:
        return value, False
    return value[:limit], True


def trim_trailing_empty_cells(
    values: list[Any], kinds: list[str]
) -> tuple[list[Any], list[str]]:
    end = len(values)
    while end and is_empty(values[end - 1]):
        end -= 1
    return values[:end], kinds[:end]


def trim_trailing_empty_rows(
    rows: list[tuple[int, list[Any], list[str]]]
) -> list[tuple[int, list[Any], list[str]]]:
    end = len(rows)
    while end and not any(not is_empty(value) for value in rows[end - 1][1]):
        end -= 1
    return rows[:end]


def normalize_header(value: Any, position: int) -> str:
    text = header_text(value)
    if not text:
        return f"column_{position}"
    normalized = re.sub(r"\s+", "_", text.casefold().strip())
    normalized = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE).strip("_")
    return normalized[:220] or f"column_{position}"


def header_text(value: Any) -> str | None:
    return None if is_empty(value) else str(value).strip()


def comparison_text(value: Any) -> str:
    return str(value).strip().casefold()


def infer_column_type(values: list[Any]) -> str:
    kinds = {classify_value(value) for value in values if not is_empty(value)}
    if not kinds:
        return "empty"
    if kinds <= {"integer"}:
        return "integer"
    if kinds <= {"integer", "number"}:
        return "number"
    if kinds <= {"date"}:
        return "date"
    if kinds <= {"date", "datetime"}:
        return "datetime"
    return next(iter(kinds)) if len(kinds) == 1 else "mixed"


def classify_value(value: Any) -> str:
    if is_empty(value):
        return "empty"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, date):
        return "date"
    if isinstance(value, time):
        return "time"

    text = str(value).strip()
    if text.startswith("="):
        return "formula"
    if text.casefold() in {"true", "false", "yes", "no", "да", "нет"}:
        return "boolean"
    compact = text.replace("\u00a0", "").replace(" ", "")
    if re.fullmatch(r"[-+]?\d+", compact):
        return "integer"
    numeric = compact.replace(",", ".")
    if re.fullmatch(r"[-+]?(?:\d+\.\d+|\d+\.|\.\d+)(?:[eE][-+]?\d+)?", numeric):
        return "number"
    for fmt, kind in (
        ("%Y-%m-%dT%H:%M:%S", "datetime"),
        ("%Y-%m-%d %H:%M:%S", "datetime"),
        ("%d.%m.%Y %H:%M", "datetime"),
        ("%Y-%m-%d", "date"),
        ("%d.%m.%Y", "date"),
        ("%d/%m/%Y", "date"),
    ):
        try:
            datetime.strptime(text, fmt)
            return kind
        except ValueError:
            pass
    return "text"


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def warning(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "context": context}
