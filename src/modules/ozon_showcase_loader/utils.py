from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from PIL import Image


def fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_token(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).casefold().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def text(value: Any) -> str | None:
    if value is None:
        return None
    clean = str(value).strip()
    return clean or None


def cell(row: list[Any], index: int | None) -> Any:
    if index is None or index < 0 or index >= len(row):
        return None
    return row[index]


def header_index(headers: list[Any]) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for index, value in enumerate(headers):
        token = normalize_token(value)
        if token:
            result.setdefault(token, []).append(index)
    return result


def find_alias_column(index: dict[str, list[int]], aliases: Iterable[Any]) -> int | None:
    normalized = [normalize_token(alias) for alias in aliases]
    for alias in normalized:
        if alias in index:
            return index[alias][0]
    for alias in normalized:
        if not alias:
            continue
        for header, positions in index.items():
            if alias in header or header in alias:
                return positions[0]
    return None


def resolve_period(combined: Any, start: Any, end: Any) -> tuple[date | None, date | None, list[str]]:
    notes: list[str] = []
    start_date = to_date(start)
    end_date = to_date(end)
    if start_date or end_date:
        return start_date, end_date, notes
    if combined is None:
        return None, None, notes
    if isinstance(combined, (date, datetime)):
        parsed = to_date(combined)
        return parsed, parsed, notes
    matches = re.findall(
        r"\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[./]\d{1,2}[./]\d{4}",
        str(combined).strip(),
    )
    parsed = [item for item in (to_date(value) for value in matches) if item]
    if len(parsed) >= 2:
        return parsed[0], parsed[1], notes
    if len(parsed) == 1:
        return parsed[0], parsed[0], ["Only one date was parsed from campaign period"]
    return None, None, ["Campaign period could not be parsed"]


def to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    clean = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(clean, fmt).date()
        except ValueError:
            continue
    return None


def to_int(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    if number < 0 or not number.is_integer():
        return None
    return int(number)


def to_rate(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    clean = str(value).strip().replace(" ", "").replace(",", ".")
    percent = clean.endswith("%")
    if percent:
        clean = clean[:-1]
    try:
        number = float(clean)
    except ValueError:
        return None
    if percent or 1 < number <= 100:
        number /= 100.0
    return number if 0 <= number <= 1 else None


def image_dimensions(content: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None, None


def unsafe_zip_member(name: str) -> bool:
    path = Path(name)
    return path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts)


def resolve_report_path(report_path: str | Path | None, source_fingerprint: str) -> Path:
    if report_path is None:
        return Path("data/generated/ozon_showcase") / f"{source_fingerprint}.json"
    target = Path(report_path).expanduser()
    if target.suffix.lower() != ".json":
        target = target / f"{source_fingerprint}.json"
    return target


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
