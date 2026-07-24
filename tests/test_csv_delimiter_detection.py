from pathlib import Path

import pytest

from src.modules.import_sessions.tabular_inspector import (
    _detect_delimiter,
    inspect_tabular_file,
)


def test_semicolon_csv_wins_over_consistent_decimal_commas(tmp_path: Path):
    content = (
        "Campaign;CTR, %;Clicks\n"
        "Alpha;2,1%;21\n"
        "Beta;1,0%;10\n"
    )
    source = tmp_path / "history.csv"
    source.write_text(content, encoding="utf-8")

    inspection = inspect_tabular_file(source, ".csv")

    assert inspection.delimiter == ";"
    assert inspection.tables[0].column_count == 3
    assert [column.source_header for column in inspection.tables[0].columns] == [
        "Campaign",
        "CTR, %",
        "Clicks",
    ]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("name,ctr\nA,0.1\nB,0.2\n", ","),
        ("name;ctr\nA;0,1\nB;0,2\n", ";"),
        ("name\tctr\nA\t0.1\nB\t0.2\n", "\t"),
        ("name|ctr\nA|0.1\nB|0.2\n", "|"),
    ],
)
def test_supported_delimiters_remain_detectable(content: str, expected: str):
    assert _detect_delimiter(content) == expected


def test_comma_csv_keeps_quoted_commas_inside_fields():
    content = 'name,notes,ctr\nA,"hello, world",0.1\nB,"goodbye, world",0.2\n'

    assert _detect_delimiter(content) == ","
