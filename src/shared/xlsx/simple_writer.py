from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


@dataclass(frozen=True)
class Cell:
    value: Any
    style: str = "default"


@dataclass
class SheetSpec:
    name: str
    rows: list[list[Any]]
    header_rows: int = 1
    row_styles: dict[int, str] = field(default_factory=dict)
    column_widths: list[float] = field(default_factory=list)
    freeze_rows: int = 1
    auto_filter: bool = True


_STYLE_IDS = {
    "default": 0,
    "title": 1,
    "header": 2,
    "info": 3,
    "warning": 4,
    "blocking": 5,
    "muted": 6,
    "number": 7,
    "date": 8,
}


def write_xlsx(
    path: str | Path,
    sheets: list[SheetSpec],
    *,
    title: str,
    creator: str = "Arvectum Creative Test Agent",
) -> Path:
    if not sheets:
        raise ValueError("At least one worksheet is required")
    safe_names = _unique_sheet_names([item.name for item in sheets])
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types(len(sheets)))
        archive.writestr("_rels/.rels", _root_rels())
        archive.writestr("docProps/app.xml", _app_properties(safe_names))
        archive.writestr("docProps/core.xml", _core_properties(title, creator))
        archive.writestr("xl/workbook.xml", _workbook_xml(safe_names))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(len(sheets)))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, (spec, safe_name) in enumerate(zip(sheets, safe_names), start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _sheet_xml(spec, safe_name),
            )
    return target


def _unique_sheet_names(names: list[str]) -> list[str]:
    result: list[str] = []
    used: set[str] = set()
    for raw in names:
        base = re.sub(r"[\\/*?:\[\]]", "_", raw).strip() or "Sheet"
        base = base[:31]
        candidate = base
        suffix = 2
        while candidate.casefold() in used:
            tail = f" {suffix}"
            candidate = f"{base[:31-len(tail)]}{tail}"
            suffix += 1
        used.add(candidate.casefold())
        result.append(candidate)
    return result


def _content_types(sheet_count: int) -> str:
    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{overrides}</Types>"
    )


def _root_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )


def _app_properties(names: list[str]) -> str:
    titles = "".join(f"<vt:lpstr>{escape(name)}</vt:lpstr>" for name in names)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Arvectum Creative Test Agent</Application>'
        '<DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>'
        f'<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(names)}</vt:i4></vt:variant></vt:vector></HeadingPairs>'
        f'<TitlesOfParts><vt:vector size="{len(names)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>'
        '<Company>Arvectum</Company><LinksUpToDate>false</LinksUpToDate><SharedDoc>false</SharedDoc><HyperlinksChanged>false</HyperlinksChanged><AppVersion>1.0</AppVersion>'
        '</Properties>'
    )


def _core_properties(title: str, creator: str) -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<dc:title>{escape(title)}</dc:title><dc:creator>{escape(creator)}</dc:creator>'
        f'<cp:lastModifiedBy>{escape(creator)}</cp:lastModifiedBy>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        '</cp:coreProperties>'
    )


def _workbook_xml(names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<bookViews><workbookView activeTab="0"/></bookViews><sheets>{sheets}</sheets>'
        '<calcPr calcId="0" fullCalcOnLoad="1"/></workbook>'
    )


def _workbook_rels(sheet_count: int) -> str:
    sheet_rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, sheet_count + 1)
    )
    styles_id = sheet_count + 1
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{sheet_rels}<Relationship Id="rId{styles_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3">'
        '<font><sz val="10"/><name val="Aptos"/><family val="2"/></font>'
        '<font><b/><sz val="14"/><color rgb="FFFFFFFF"/><name val="Aptos Display"/><family val="2"/></font>'
        '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Aptos"/><family val="2"/></font>'
        '</fonts>'
        '<fills count="7">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF234E52"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF3F6C72"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFEAF3F4"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFE8A3"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill>'
        '</fills>'
        '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left style="thin"><color rgb="FFD9E2E3"/></left><right style="thin"><color rgb="FFD9E2E3"/></right><top style="thin"><color rgb="FFD9E2E3"/></top><bottom style="thin"><color rgb="FFD9E2E3"/></bottom><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="9">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/><protection locked="1"/></xf>'
        '<xf numFmtId="2" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"/>'
        '<xf numFmtId="14" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1"/>'
        '</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def _sheet_xml(spec: SheetSpec, safe_name: str) -> str:
    max_columns = max((len(row) for row in spec.rows), default=1)
    max_rows = max(len(spec.rows), 1)
    dimension = f"A1:{_column_name(max_columns)}{max_rows}"
    cols_xml = ""
    if spec.column_widths:
        cols = []
        for index, width in enumerate(spec.column_widths, start=1):
            cols.append(f'<col min="{index}" max="{index}" width="{max(4.0, min(float(width), 60.0))}" customWidth="1"/>')
        cols_xml = f"<cols>{''.join(cols)}</cols>"
    pane_xml = ""
    if spec.freeze_rows > 0:
        pane_xml = (
            f'<pane ySplit="{spec.freeze_rows}" topLeftCell="A{spec.freeze_rows + 1}" '
            'activePane="bottomLeft" state="frozen"/>'
        )
    rows_xml = []
    for row_index, row in enumerate(spec.rows, start=1):
        default_style = spec.row_styles.get(row_index)
        if default_style is None:
            if row_index == 1 and spec.header_rows == 0:
                default_style = "title"
            elif row_index <= spec.header_rows:
                default_style = "header"
            else:
                default_style = "default"
        cells_xml = "".join(
            _cell_xml(row_index, column_index, value, default_style)
            for column_index, value in enumerate(row, start=1)
        )
        height = 26 if default_style == "title" else 20 if default_style == "header" else 18
        rows_xml.append(f'<row r="{row_index}" ht="{height}" customHeight="1">{cells_xml}</row>')
    filter_xml = ""
    if spec.auto_filter and spec.header_rows > 0 and spec.rows:
        filter_xml = f'<autoFilter ref="A{spec.header_rows}:{_column_name(max_columns)}{max_rows}"/>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension}"/><sheetViews><sheetView workbookViewId="0">{pane_xml}</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="18"/>'
        f'{cols_xml}<sheetData>{"".join(rows_xml)}</sheetData>{filter_xml}'
        '<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>'
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
        '</worksheet>'
    )


def _cell_xml(row: int, column: int, raw: Any, default_style: str) -> str:
    cell = raw if isinstance(raw, Cell) else Cell(raw, default_style)
    style_id = _STYLE_IDS.get(cell.style, _STYLE_IDS[default_style])
    ref = f"{_column_name(column)}{row}"
    value = cell.value
    if value is None:
        return f'<c r="{ref}" s="{style_id}"/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" s="{style_id}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            value = str(value)
        else:
            return f'<c r="{ref}" s="{style_id}"><v>{value}</v></c>'
    if isinstance(value, (datetime, date)):
        value = value.isoformat()
    text = str(value)
    preserve = ' xml:space="preserve"' if text != text.strip() or "\n" in text else ""
    return f'<c r="{ref}" s="{style_id}" t="inlineStr"><is><t{preserve}>{escape(text)}</t></is></c>'


def _column_name(index: int) -> str:
    result = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result
