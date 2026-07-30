from __future__ import annotations

import csv
import json
import re
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .spec import (
    ALLOWED, BOOLEAN_FIELDS, DATE_FIELDS, FIELD_META, HEADERS, INTEGER_FIELDS,
    NUMBER_FIELDS, REQUIRED_BASE, SCHEMA_VERSION,
)


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_records_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: "" if row.get(key) is None else str(row[key]).lower()
                if isinstance(row.get(key), bool) else row.get(key)
                for key in HEADERS
            })


def write_dictionary(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["field", "required", "type", "allowed_values", "description", "example"])
        for name in HEADERS:
            required, kind, description, example = FIELD_META[name]
            writer.writerow([name, required, kind, ";".join(ALLOWED.get(name, [])), description, example])


def _normalize_xlsx(path: Path) -> None:
    temp = path.with_suffix(".xlsx.tmp")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
        temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as target:
        for name in sorted(source.namelist()):
            data = source.read(name)
            if name == "docProps/core.xml":
                data = re.sub(
                    rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                    rb"\g<1>2026-07-30T00:00:00Z\g<2>", data,
                )
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            info.create_system = 3
            target.writestr(info, data)
    temp.replace(path)


def build_xlsx(path: Path, rows: list[dict[str, Any]]) -> None:
    book = Workbook()
    data = book.active
    data.title = "Data"
    dictionary = book.create_sheet("Dictionary")
    instructions = book.create_sheet("Instructions")
    lists = book.create_sheet("Lists")
    fixed = datetime(2026, 7, 30, tzinfo=timezone.utc)
    book.properties.creator = book.properties.lastModifiedBy = "Arvectum"
    book.properties.created = book.properties.modified = fixed
    book.properties.title = "CTA-DATA-002 Client Calibration Data Request"
    book.properties.description = "Local-first evidence request; causal interpretation disabled."

    dark = PatternFill("solid", fgColor="0B1F33")
    required_fill = PatternFill("solid", fgColor="FFF4CC")
    conditional_fill = PatternFill("solid", fgColor="EAF4F8")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    for column, name in enumerate(HEADERS, 1):
        cell = data.cell(1, column, name)
        cell.fill, cell.font = dark, header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    data.freeze_panes = "A2"
    data.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}201"
    data.row_dimensions[1].height = 42

    defaults = {
        "schema_version": SCHEMA_VERSION, "comparison_design": "control_test",
        "measurement_basis": "absolute_counts", "metric_unit": "proportion",
        "causal_interpretation_allowed": False,
    }
    for row_number in range(2, 202):
        for name, value in defaults.items():
            data.cell(row_number, HEADERS.index(name) + 1, value)
    for row_number, record in enumerate(rows, 2):
        for column, name in enumerate(HEADERS, 1):
            value = record.get(name)
            if name in DATE_FIELDS and isinstance(value, str) and value:
                value = date.fromisoformat(value)
            data.cell(row_number, column, value)

    widths = [13,16,20,15,22,15,28,19,15,14,24,18,16,22,36,22,18,18,19,14,18,18,18,18,16,16,14,14,30,16,16,22,20,20,18,34,28]
    for index, width in enumerate(widths, 1):
        data.column_dimensions[get_column_letter(index)].width = width
    for row in data.iter_rows(min_row=2, max_row=201, max_col=len(HEADERS)):
        for cell in row:
            cell.font = Font(size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for name in REQUIRED_BASE:
        column = HEADERS.index(name) + 1
        for row_number in range(2, 202):
            data.cell(row_number, column).fill = required_fill
    conditional = {
        "campaign_id", "asset_id", "placement_id", "platform", "placement_name",
        "linkage_missing_fields", "linkage_notes", "control_sample_count",
        "control_positive_count", "test_sample_count", "test_positive_count",
        "counts_unavailable_reason", "measurement_notes",
    }
    for name in conditional:
        column = HEADERS.index(name) + 1
        for row_number in range(2, 202):
            data.cell(row_number, column).fill = conditional_fill
    for name in DATE_FIELDS:
        for row_number in range(2, 202):
            data.cell(row_number, HEADERS.index(name) + 1).number_format = "yyyy-mm-dd"
    for name in INTEGER_FIELDS:
        for row_number in range(2, 202):
            data.cell(row_number, HEADERS.index(name) + 1).number_format = "0"
    for name in NUMBER_FIELDS:
        for row_number in range(2, 202):
            data.cell(row_number, HEADERS.index(name) + 1).number_format = "0.000000"

    ranges: dict[str, tuple[str, int]] = {}
    for list_index, (name, values) in enumerate(ALLOWED.items(), 1):
        letter = get_column_letter(list_index)
        lists.cell(1, list_index, name).fill = dark
        lists.cell(1, list_index).font = header_font
        for row_number, value in enumerate(values, 2):
            lists.cell(row_number, list_index, value)
        lists.column_dimensions[letter].width = 28
        ranges[name] = (letter, len(values) + 1)
    lists.freeze_panes = "A2"
    for name, (letter, last) in ranges.items():
        target = get_column_letter(HEADERS.index(name) + 1)
        validation = DataValidation(type="list", formula1=f"=Lists!${letter}$2:${letter}${last}", allow_blank=True)
        data.add_data_validation(validation)
        validation.add(f"{target}2:{target}201")
    basis = get_column_letter(HEADERS.index("measurement_basis") + 1)
    reason = get_column_letter(HEADERS.index("counts_unavailable_reason") + 1)
    data.conditional_formatting.add(
        f"{reason}2:{reason}201",
        FormulaRule(formula=[f'=${basis}2="rates_only"'], fill=PatternFill("solid", fgColor="FCE8E6")),
    )

    dictionary.append(["field", "required", "type", "allowed_values", "description", "example"])
    for cell in dictionary[1]:
        cell.fill, cell.font = dark, header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for name in HEADERS:
        required, kind, description, example = FIELD_META[name]
        dictionary.append([name, required, kind, "; ".join(ALLOWED.get(name, [])), description, example])
    dictionary.freeze_panes = "A2"
    for column, width in zip("ABCDEF", [28, 12, 18, 40, 72, 30], strict=True):
        dictionary.column_dimensions[column].width = width
    for row in dictionary.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    instructions.merge_cells("A1:H1")
    instructions["A1"] = "CTA-DATA-002 — Client Calibration Data Request"
    instructions["A1"].fill, instructions["A1"].font = dark, Font(color="FFFFFF", bold=True, size=16)
    instructions["A1"].alignment = Alignment(vertical="center")
    instructions.row_dimensions[1].height = 34
    rows_text = [
        ("Назначение", "Один ряд = одна метрика для кампания → креатив → размещение → период."),
        ("Связь", "Для exact обязательны campaign_id, asset_id, placement_id, platform и placement_name."),
        ("Неизвестная связь", "Используйте missing, заполните linkage_missing_fields и linkage_notes. Не придумывайте ID."),
        ("Counts", "Для долей предпочтительны sample_count и positive_count. Rates-only требует причины."),
        ("Формат rates", "35,9% = 0.359, не 35.9."),
        ("Период и источник", "Даты YYYY-MM-DD; source_system и source_record_id обязательны."),
        ("Причинность", "causal_interpretation_allowed всегда false."),
        ("Проверка", "python scripts/client_calibration_data_request_pack.py validate --input <file.xlsx>"),
    ]
    for row_number, (title, text) in enumerate(rows_text, 3):
        instructions.cell(row_number, 1, title).fill = PatternFill("solid", fgColor="DDEBF3")
        instructions.cell(row_number, 1).font = Font(bold=True, color="0B1F33", size=11)
        instructions.cell(row_number, 2, text)
        for column in (1, 2):
            instructions.cell(row_number, column).alignment = Alignment(vertical="top", wrap_text=True)
        instructions.row_dimensions[row_number].height = 42
    instructions.column_dimensions["A"].width = 24
    instructions.column_dimensions["B"].width = 90
    instructions.merge_cells("A13:H15")
    instructions["A13"] = "Реальные клиентские материалы не должны попадать в GitHub. Только локальный закрытый контур."
    instructions["A13"].fill = PatternFill("solid", fgColor="FCE8E6")
    instructions["A13"].font = Font(bold=True, color="7F1D1D", size=11)
    instructions["A13"].alignment = Alignment(vertical="center", wrap_text=True)

    book.save(path)
    _normalize_xlsx(path)


def _empty_template_record(row: dict[str, Any]) -> bool:
    defaults = {
        "schema_version": SCHEMA_VERSION, "comparison_design": "control_test",
        "measurement_basis": "absolute_counts", "metric_unit": "proportion",
        "causal_interpretation_allowed": False,
    }
    if row.get("record_id") not in (None, ""):
        return False
    return all(key == "_row_number" or value in (None, "") or defaults.get(key) == value for key, value in row.items())


def read_records(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        document = read_json(path)
        if not isinstance(document, dict) or not isinstance(document.get("records"), list):
            return [], ["INVALID_JSON_DOCUMENT"]
        return list(document["records"]), []
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if (reader.fieldnames or []) != HEADERS:
                return [], ["HEADER_MISMATCH"]
            return list(reader), []
    if suffix != ".xlsx":
        return [], ["UNSUPPORTED_FORMAT"]
    book = load_workbook(path, read_only=True, data_only=True)
    if "Data" not in book.sheetnames:
        return [], ["DATA_SHEET_MISSING"]
    sheet = book["Data"]
    values = list(sheet.iter_rows(values_only=True))
    if not values or [str(value or "").strip() for value in values[0]][:len(HEADERS)] != HEADERS:
        return [], ["HEADER_MISMATCH"]
    records: list[dict[str, Any]] = []
    for row_number, values_row in enumerate(values[1:], 2):
        row = {name: values_row[index] if index < len(values_row) else None for index, name in enumerate(HEADERS)}
        for name in DATE_FIELDS:
            if isinstance(row[name], (date, datetime)):
                row[name] = row[name].date().isoformat() if isinstance(row[name], datetime) else row[name].isoformat()
        row["_row_number"] = row_number
        if not _empty_template_record(row):
            records.append(row)
    return records, []
