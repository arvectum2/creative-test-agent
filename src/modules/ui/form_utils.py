"""Pure form parsing helpers shared by UI routers."""

from __future__ import annotations

import json


def line_values(value: str | None) -> list[str]:
    return [item.strip() for item in value.split("\n") if item.strip()] if value else []


def comma_values(value: str | None) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def json_object(value: str | None, *, strict: bool = False) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        if strict:
            raise
        return {}
    if not isinstance(parsed, dict):
        if strict:
            raise json.JSONDecodeError("Expected a JSON object", value, 0)
        return {}
    return parsed


def batch_request_payload(
    *,
    project_id: str | None,
    name: str,
    description: str | None,
    creative_asset_ids: str | None,
    audience_profile_ids: str | None,
    brand_profile_id: str | None,
    test_rubric_id: str | None,
    input_context: str | None,
) -> dict:
    return {
        "project_id": project_id or None,
        "name": name,
        "description": description or None,
        "creative_asset_ids": line_values(creative_asset_ids),
        "audience_profile_ids": line_values(audience_profile_ids),
        "brand_profile_id": brand_profile_id or None,
        "test_rubric_id": test_rubric_id or None,
        "input_context": json_object(input_context),
    }
