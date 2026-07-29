from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .contracts import ALLOWED_LINKAGE_STATUSES, OzonShowcaseError
from .utils import normalize_token


def load_mapping(path: str | Path) -> tuple[dict[str, Any], str]:
    mapping_path = Path(path)
    if not mapping_path.is_file():
        raise OzonShowcaseError(f"Mapping file not found: {mapping_path}")
    raw = mapping_path.read_bytes()
    try:
        mapping = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OzonShowcaseError(f"Invalid UTF-8 JSON mapping: {mapping_path}") from exc
    validate_mapping(mapping)
    return mapping, hashlib.sha256(raw).hexdigest()


def validate_mapping(mapping: dict[str, Any]) -> None:
    if mapping.get("schema_id") != "cta.ozon_showcase.mapping":
        raise OzonShowcaseError("Unsupported Ozon showcase mapping schema_id")
    version = str(mapping.get("schema_version") or "").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise OzonShowcaseError("mapping schema_version must use semantic x.y.z format")
    for key in ("client", "project", "workbook", "campaigns", "asset_rules"):
        if key not in mapping:
            raise OzonShowcaseError(f"Mapping is missing required section: {key}")

    case_ids: set[str] = set()
    for campaign in mapping["campaigns"]:
        case_id = str(campaign.get("case_id") or "").strip()
        if not case_id or case_id in case_ids:
            raise OzonShowcaseError("Campaign case_id values must be non-empty and unique")
        if not campaign.get("brand"):
            raise OzonShowcaseError(f"Campaign {case_id} is missing brand")
        case_ids.add(case_id)

    seen: set[tuple[str, str]] = set()
    for rule in mapping["asset_rules"]:
        status = str(rule.get("linkage_status") or "").strip()
        if status not in ALLOWED_LINKAGE_STATUSES:
            raise OzonShowcaseError(f"Unsupported asset linkage_status: {status!r}")
        case_id = rule.get("linked_case_id")
        if case_id is not None and case_id not in case_ids:
            raise OzonShowcaseError(f"Asset rule references unknown campaign: {case_id}")
        digest = str(rule.get("sha256") or "")
        if digest and not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise OzonShowcaseError("Asset-rule sha256 must be lowercase hexadecimal")
        filename = normalize_token(rule.get("filename"))
        if not filename and not digest and not rule.get("filename_regex"):
            raise OzonShowcaseError("Each asset rule needs filename, sha256 or filename_regex")
        key = (digest, filename)
        if key in seen:
            raise OzonShowcaseError("Asset rules must not duplicate the same sha256/filename key")
        seen.add(key)


def campaign_lookup(mapping: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for campaign in mapping["campaigns"]:
        for alias in [campaign["case_id"], campaign["brand"], *campaign.get("aliases", [])]:
            result[normalize_token(alias)] = campaign
    return result


def resolve_campaign(case_value: Any, brand_value: Any, lookup: dict[str, dict[str, Any]]):
    for candidate in (case_value, brand_value):
        token = normalize_token(candidate)
        if token and token in lookup:
            return lookup[token]
    brand_token = normalize_token(brand_value)
    matches = {
        item["case_id"]: item
        for alias, item in lookup.items()
        if brand_token and alias and (alias in brand_token or brand_token in alias)
    }
    return next(iter(matches.values())) if len(matches) == 1 else None


def canonical_metric(value: Any, mapping: dict[str, Any]) -> str | None:
    token = normalize_token(value)
    if not token:
        return None
    for canonical, aliases in mapping["workbook"]["metrics"].items():
        tokens = {normalize_token(canonical), *(normalize_token(item) for item in aliases)}
        if token in tokens or any(alias and alias in token for alias in tokens):
            return canonical
    return None
