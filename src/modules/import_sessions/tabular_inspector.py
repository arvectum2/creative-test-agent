from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from src.shared.config.settings import get_settings

PARSER_NAME = "tabular_inspector"
PARSER_VERSION = "1.0.1"
SUPPORTED_EXTENSIONS = {".xlsx", ".csv", ".tsv"}


class TabularInspectionError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class InspectedColumn:
    position: int
    source_header: str | None
    normalized_header: str
    inferred_type: str
    is_empty: bool
    duplicate_index: int
    duplicate_group: str | None
    non_empty_count: int
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class InspectedRow:
    source_row_number: int
    row_kind: str
    values: list[Any]
    cell_types: list[str]


@dataclass
class InspectedTable:
    sheet_index: int
    sheet_name: str
    header_row_number: int | None
    header_confidence: float | None
    source_row_count: int
    data_row_count: int
    column_count: int
    truncated: bool
    warnings: list[dict[str, Any]]
    columns: list[InspectedColumn]
    rows: list[InspectedRow]


@dataclass
class InspectionResult:
    file_format: str
    encoding: str | None
    delimiter: str | None
    warnings: list[dict[str, Any]]
    tables: list[InspectedTable]


def inspect_tabular_file(path: Path, extension: str | None) -> InspectionResult:
    ext = (extension or path.suffix).lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise TabularInspectionError(
            "unsupported_tabular_format",
            f"Tabular inspection supports only: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    return _inspect_xlsx(path) if ext == ".xlsx" else _inspect_delimited(path, ext)


def _inspect_delimited(path: Path, extension: str) -> InspectionResult:
    settings = get_settings()
    sample = path.read_bytes()[:65536]
    encoding, encoding_warning = _detect_encoding(sample)
    warnings: list[dict[str, Any]] = []
    if encoding_warning:
        warnings.append(encoding_warning)

    try:
        sample_text = sample.decode(encoding)
    except UnicodeDecodeError as exc:
        raise TabularInspectionError(
            "text_decode_failed", f"Could not decode delimited file using {encoding}"
        ) from exc

    delimiter = "\t" if extension == ".tsv" else _detect_delimiter(sample_text)
    rows: list[tuple[int, list[Any], list[str]]] = []
    truncated = False
    column_warning_added = False
    truncated_cells = 0

    try:
        with path.open("rb") as binary:
            text = io.TextIOWrapper(binary, encoding=encoding, newline="")
            reader = csv.reader(text, delimiter=delimiter)
            for row_number, raw_row in enumerate(reader, start=1):
                if row_number > settings.tabular_inspection_max_rows_per_table:
                    truncated = True
                    break
                if len(raw_row) > settings.tabular_inspection_max_columns:
                    raw_row = raw_row[: settings.tabular_inspection_max_columns]
                    if not column_warning_added:
                        warnings.append(
                            _warning(
                                "column_limit_reached",
                                "Columns beyond the configured limit were not materialized.",
                                limit=settings.tabular_inspection_max_columns,
                                row_number=row_number,
                            )
                        )
                        column_warning_added = True
                values: list[Any] = []
                kinds: list[str] = []
                for value in raw_row:
                    value, was_truncated = _truncate_cell(value)
                    truncated_cells += int(was_truncated)
                    values.append(value)
                    kinds.append(_classify_value(value))
                rows.append((row_number, values, kinds))
    except (csv.Error, UnicodeDecodeError, OSError) as exc:
        raise TabularInspectionError(
            "delimited_parse_failed", f"Could not parse delimited file: {exc}"
        ) from exc

    if truncated_cells:
        warnings.append(
            _warning(
                "cell_values_truncated",
                "Some cell values exceeded the configured preview/storage limit.",
                count=truncated_cells,
                max_chars=settings.tabular_inspection_max_cell_chars,
            )
        )
    if truncated:
        warnings.append(
            _warning(
                "row_limit_reached",
                "Rows beyond the configured inspection limit were not materialized.",
                limit=settings.tabular_inspection_max_rows_per_table,
            )
        )

    rows = _trim_trailing_empty_rows(rows)
    return InspectionResult(
        file_format=extension.lstrip("."),
        encoding=encoding,
        delimiter=delimiter,
        warnings=warnings,
        tables=[
            _build_table(
                sheet_index=0,
                sheet_name="data",
                raw_rows=rows,
                inherited_warnings=list(warnings),
                truncated=truncated,
            )
        ],
    )


def _inspect_xlsx(path: Path) -> InspectionResult:
    settings = get_settings()
    source_stream = None
    workbook = None
    try:
        # Immutable originals are content-addressed and deliberately have no file
        # extension. Passing a binary stream makes openpyxl validate the ZIP
        # contents instead of rejecting the storage filename.
        source_stream = path.open("rb")
        workbook = load_workbook(
            filename=source_stream,
            read_only=True,
            data_only=False,
            keep_links=False,
        )
    except (InvalidFileException, BadZipFile, OSError, ValueError, KeyError, EOFError) as exc:
        if source_stream is not None:
            source_stream.close()
        raise TabularInspectionError(
            "xlsx_parse_failed", f"Could not open XLSX workbook: {exc}"
        ) from exc

    tables: list[InspectedTable] = []
    global_warnings: list[dict[str, Any]] = []
    try:
        for sheet_index, worksheet in enumerate(workbook.worksheets):
            rows: list[tuple[int, list[Any], list[str]]] = []
            truncated = False
            blank_run = 0
            seen_content = False
            truncated_cells = 0
            stopped_on_blank_run = False

            for row_number, cells in enumerate(
                worksheet.iter_rows(max_col=settings.tabular_inspection_max_columns),
                start=1,
            ):
                if row_number > settings.tabular_inspection_max_rows_per_table:
                    truncated = True
                    break
                values: list[Any] = []
                kinds: list[str] = []
                for cell in cells:
                    value, kind = _serialize_excel_cell(cell)
                    value, was_truncated = _truncate_cell(value)
                    truncated_cells += int(was_truncated)
                    values.append(value)
                    kinds.append(kind if value is not None else "empty")
                values, kinds = _trim_trailing_empty_cells(values, kinds)

                if any(not _is_empty(value) for value in values):
                    seen_content = True
                    blank_run = 0
                else:
                    blank_run += 1
                rows.append((row_number, values, kinds))

                if (
                    seen_content
                    and settings.tabular_inspection_blank_row_stop > 0
                    and blank_run >= settings.tabular_inspection_blank_row_stop
                ):
                    rows = rows[:-blank_run]
                    stopped_on_blank_run = True
                    break

            sheet_warnings: list[dict[str, Any]] = []
            if stopped_on_blank_run:
                warning = _warning(
                    "blank_row_stop_reached",
                    "Worksheet scanning stopped after a long trailing blank run.",
                    sheet_name=worksheet.title,
                    blank_rows=blank_run,
                )
                global_warnings.append(warning)
                sheet_warnings.append(warning)
            if truncated_cells:
                sheet_warnings.append(
                    _warning(
                        "cell_values_truncated",
                        "Some cell values exceeded the configured preview/storage limit.",
                        count=truncated_cells,
                        max_chars=settings.tabular_inspection_max_cell_chars,
                    )
                )
            if truncated:
                sheet_warnings.append(
                    _warning(
                        "row_limit_reached",
                        "Rows beyond the configured inspection limit were not materialized.",
                        limit=settings.tabular_inspection_max_rows_per_table,
                    )
                )

            tables.append(
                _build_table(
                    sheet_index=sheet_index,
                    sheet_name=worksheet.title,
                    raw_rows=_trim_trailing_empty_rows(rows),
                    inherited_warnings=sheet_warnings,
                    truncated=truncated,
                )
            )
    except (BadZipFile, OSError, ValueError, KeyError, EOFError, TypeError) as exc:
        raise TabularInspectionError(
            "xlsx_parse_failed", f"Could not inspect XLSX workbook: {exc}"
        ) from exc
    finally:
        workbook.close()
        source_stream.close()

    return InspectionResult(
        file_format="xlsx",
        encoding=None,
        delimiter=None,
        warnings=global_warnings,
        tables=tables,
    )


def _build_table(
    *,
    sheet_index: int,
    sheet_name: str,
    raw_rows: list[tuple[int, list[Any], list[str]]],
    inherited_warnings: list[dict[str, Any]],
    truncated: bool,
) -> InspectedTable:
    settings = get_settings()
    warnings = list(inherited_warnings)
    column_count = max((len(values) for _, values, _ in raw_rows), default=0)
    if not raw_rows or column_count == 0:
        warnings.append(
            _warning(
                "empty_table",
                "No non-empty cells were found in this table.",
                sheet_name=sheet_name,
            )
        )
        return InspectedTable(
            sheet_index=sheet_index,
            sheet_name=sheet_name,
            header_row_number=None,
            header_confidence=None,
            source_row_count=len(raw_rows),
            data_row_count=0,
            column_count=0,
            truncated=truncated,
            warnings=warnings,
            columns=[],
            rows=[],
        )

    header_row_number, header_confidence = _detect_header(
        raw_rows, column_count, settings.tabular_inspection_header_scan_rows
    )
    if header_row_number is None:
        warnings.append(
            _warning(
                "header_not_detected",
                "No confident header row was detected; generated column names are used.",
                sheet_name=sheet_name,
            )
        )
    elif header_confidence is not None and header_confidence < 0.75:
        warnings.append(
            _warning(
                "low_header_confidence",
                "The detected header row should be reviewed.",
                sheet_name=sheet_name,
                row_number=header_row_number,
                confidence=round(header_confidence, 3),
            )
        )

    header_values: list[Any] = [None] * column_count
    if header_row_number is not None:
        header_values = next(
            (
                values + [None] * (column_count - len(values))
                for row_number, values, _ in raw_rows
                if row_number == header_row_number
            ),
            header_values,
        )

    base_names = [
        _normalize_header(header_values[index], index + 1)
        for index in range(column_count)
    ]
    totals = Counter(base_names)
    occurrences: Counter[str] = Counter()
    normalized_names: list[str] = []
    duplicate_indexes: list[int] = []
    duplicate_groups: list[str | None] = []
    for base_name in base_names:
        occurrences[base_name] += 1
        duplicate_index = occurrences[base_name]
        duplicate_indexes.append(duplicate_index)
        duplicate_groups.append(base_name if totals[base_name] > 1 else None)
        normalized_names.append(
            base_name if duplicate_index == 1 else f"{base_name}__{duplicate_index}"
        )

    duplicate_headers = sorted(name for name, count in totals.items() if count > 1)
    if duplicate_headers:
        warnings.append(
            _warning(
                "duplicate_headers",
                "Duplicate header names were disambiguated.",
                headers=duplicate_headers,
            )
        )

    data_rows = [
        (row_number, values, kinds)
        for row_number, values, kinds in raw_rows
        if header_row_number is None or row_number > header_row_number
    ]
    columns: list[InspectedColumn] = []
    empty_positions: list[int] = []
    for index in range(column_count):
        values = [
            row_values[index] if index < len(row_values) else None
            for _, row_values, _ in data_rows
        ]
        non_empty = [value for value in values if not _is_empty(value)]
        is_empty = not non_empty
        if is_empty:
            empty_positions.append(index + 1)
        columns.append(
            InspectedColumn(
                position=index + 1,
                source_header=_header_text(header_values[index]),
                normalized_header=normalized_names[index],
                inferred_type=_infer_column_type(non_empty),
                is_empty=is_empty,
                duplicate_index=duplicate_indexes[index],
                duplicate_group=duplicate_groups[index],
                non_empty_count=len(non_empty),
                sample_values=non_empty[:5],
            )
        )
    if empty_positions:
        warnings.append(
            _warning(
                "empty_columns",
                "Columns with no data values were detected.",
                positions=empty_positions,
            )
        )

    materialized_rows: list[InspectedRow] = []
    data_row_count = 0
    for row_number, values, kinds in raw_rows:
        padded_values = values + [None] * (column_count - len(values))
        padded_kinds = kinds + ["empty"] * (column_count - len(kinds))
        if header_row_number is None:
            row_kind = "data"
        elif row_number < header_row_number:
            row_kind = "preamble"
        elif row_number == header_row_number:
            row_kind = "header"
        else:
            row_kind = "data"
        if row_kind == "data" and any(not _is_empty(value) for value in padded_values):
            data_row_count += 1
        materialized_rows.append(
            InspectedRow(
                source_row_number=row_number,
                row_kind=row_kind,
                values=padded_values,
                cell_types=padded_kinds,
            )
        )

    return InspectedTable(
        sheet_index=sheet_index,
        sheet_name=sheet_name,
        header_row_number=header_row_number,
        header_confidence=header_confidence,
        source_row_count=len(raw_rows),
        data_row_count=data_row_count,
        column_count=column_count,
        truncated=truncated,
        warnings=warnings,
        columns=columns,
        rows=materialized_rows,
    )


def _detect_header(
    rows: list[tuple[int, list[Any], list[str]]],
    column_count: int,
    scan_limit: int,
) -> tuple[int | None, float | None]:
    candidates: list[tuple[float, int]] = []
    scanned = rows[:scan_limit]
    for position, (row_number, values, _) in enumerate(scanned):
        padded = values + [None] * (column_count - len(values))
        non_empty = [value for value in padded if not _is_empty(value)]
        minimum = 1 if column_count == 1 else 2
        if len(non_empty) < minimum:
            continue
        text_ratio = sum(
            _classify_value(value) in {"text", "formula"} for value in non_empty
        ) / len(non_empty)
        unique_ratio = len({_comparison_text(value) for value in non_empty}) / len(non_empty)
        density = len(non_empty) / max(column_count, 1)
        next_bonus = 0.0
        for _, following, _ in scanned[position + 1 :]:
            following_count = sum(not _is_empty(value) for value in following)
            if following_count:
                next_bonus = 1.0 if following_count >= minimum else 0.0
                break
        preamble_bonus = 0.0
        if position:
            previous_counts = [
                sum(not _is_empty(value) for value in previous)
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


def _detect_encoding(sample: bytes) -> tuple[str, dict[str, Any] | None]:
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", None
    for encoding in ("utf-8", "cp1251"):
        try:
            sample.decode(encoding)
            return encoding, None
        except UnicodeDecodeError:
            pass
    return "latin-1", _warning(
        "encoding_fallback",
        "The file was decoded with latin-1 after UTF-8 and CP1251 failed.",
    )


def _detect_delimiter(sample: str) -> str:
    text = "\n".join(line for line in sample.splitlines() if line.strip())
    if not text:
        return ","
    try:
        return csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {candidate: text.count(candidate) for candidate in (",", ";", "\t", "|")}
        delimiter, count = max(counts.items(), key=lambda item: item[1])
        return delimiter if count else ","


def _serialize_excel_cell(cell) -> tuple[Any, str]:
    if cell.value is None:
        return None, "empty"
    if cell.data_type == "f":
        formula = str(cell.value)
        return (formula if formula.startswith("=") else f"={formula}"), "formula"
    value = _json_value(cell.value)
    return value, _classify_value(value)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _truncate_cell(value: Any) -> tuple[Any, bool]:
    limit = get_settings().tabular_inspection_max_cell_chars
    if not isinstance(value, str) or limit <= 0 or len(value) <= limit:
        return value, False
    return value[:limit], True


def _trim_trailing_empty_cells(
    values: list[Any], kinds: list[str]
) -> tuple[list[Any], list[str]]:
    end = len(values)
    while end and _is_empty(values[end - 1]):
        end -= 1
    return values[:end], kinds[:end]


def _trim_trailing_empty_rows(
    rows: list[tuple[int, list[Any], list[str]]]
) -> list[tuple[int, list[Any], list[str]]]:
    end = len(rows)
    while end and not any(not _is_empty(value) for value in rows[end - 1][1]):
        end -= 1
    return rows[:end]


def _normalize_header(value: Any, position: int) -> str:
    text = _header_text(value)
    if not text:
        return f"column_{position}"
    normalized = re.sub(r"\s+", "_", text.casefold().strip())
    normalized = re.sub(r"[^\w]+", "_", normalized, flags=re.UNICODE).strip("_")
    return normalized[:220] or f"column_{position}"


def _header_text(value: Any) -> str | None:
    return None if _is_empty(value) else str(value).strip()


def _comparison_text(value: Any) -> str:
    return str(value).strip().casefold()


def _infer_column_type(values: list[Any]) -> str:
    kinds = {_classify_value(value) for value in values if not _is_empty(value)}
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


def _classify_value(value: Any) -> str:
    if _is_empty(value):
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


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _warning(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "context": context}
