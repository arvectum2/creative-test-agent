from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import re
import zipfile
from collections import Counter, defaultdict
from typing import Any

from openpyxl import load_workbook

from .contracts import (
    ALLOWED_LINKAGE_STATUSES,
    OzonShowcaseError,
    ParsedAsset,
    ParsedOutcome,
    WorkbookParseResult,
)
from .mapping import campaign_lookup, canonical_metric, resolve_campaign
from .utils import (
    cell,
    find_alias_column,
    header_index,
    image_dimensions,
    normalize_token,
    resolve_period,
    text,
    to_int,
    to_rate,
    unsafe_zip_member,
)


def parse_outcomes_workbook(content: bytes, mapping: dict[str, Any]) -> WorkbookParseResult:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise OzonShowcaseError(f"Could not open outcomes workbook: {exc}") from exc

    selected = _select_table(workbook, mapping)
    if selected is None:
        raise OzonShowcaseError(
            "Could not identify an Ozon outcome table. Workbook layout: "
            + json.dumps(_workbook_layout(workbook), ensure_ascii=False)
        )
    sheet, header_row, headers, layout = selected
    aliases = mapping["workbook"]["columns"]
    index = header_index(headers)
    base = {
        field: find_alias_column(index, values)
        for field, values in aliases.items()
        if field not in {"metric", "cg_rate", "tg_rate"}
    }
    long_columns = {
        field: find_alias_column(index, aliases.get(field, []))
        for field in ("metric", "cg_rate", "tg_rate")
    }
    wide_columns = _wide_metric_columns(headers, mapping)
    lookup = campaign_lookup(mapping)
    outcomes: list[ParsedOutcome] = []
    warnings: list[str] = []

    for row_number, values in enumerate(
        sheet.iter_rows(min_row=header_row + 1, values_only=True),
        start=header_row + 1,
    ):
        row = list(values)
        if not any(value not in (None, "") for value in row):
            continue
        payload = {
            str(headers[pos] or f"column_{pos + 1}"): row[pos] if pos < len(row) else None
            for pos in range(len(headers))
        }
        campaign = resolve_campaign(cell(row, base.get("case_id")), cell(row, base.get("brand")), lookup)
        if campaign is None:
            warnings.append(f"Skipped workbook row {row_number}: campaign identity is not mapped")
            continue
        period_start, period_end, notes = resolve_period(
            cell(row, base.get("period")),
            cell(row, base.get("period_start")),
            cell(row, base.get("period_end")),
        )
        common = dict(
            campaign=campaign,
            control_n=to_int(cell(row, base.get("control_n"))),
            test_n=to_int(cell(row, base.get("test_n"))),
            platform=text(cell(row, base.get("platform"))) or campaign.get("expected_platform"),
            period_start=period_start,
            period_end=period_end,
            sheet=sheet.title,
            row_number=row_number,
            payload=payload,
            notes=notes,
        )
        if layout == "long":
            metric = canonical_metric(cell(row, long_columns["metric"]), mapping)
            if metric is None:
                warnings.append(f"Skipped workbook row {row_number}: metric is not mapped")
                continue
            outcome = _make_outcome(
                metric=metric,
                cg_rate=to_rate(cell(row, long_columns["cg_rate"])),
                tg_rate=to_rate(cell(row, long_columns["tg_rate"])),
                **common,
            )
            if outcome:
                outcomes.append(outcome)
        else:
            for metric, pair in wide_columns.items():
                outcome = _make_outcome(
                    metric=metric,
                    cg_rate=to_rate(cell(row, pair["cg"])),
                    tg_rate=to_rate(cell(row, pair["tg"])),
                    **common,
                )
                if outcome:
                    outcomes.append(outcome)

    if not outcomes:
        raise OzonShowcaseError("The selected outcomes table produced no usable CG/TG metrics")
    duplicates = [
        key
        for key, count in Counter((item.case_id, item.metric) for item in outcomes).items()
        if count > 1
    ]
    if duplicates:
        raise OzonShowcaseError(f"Duplicate campaign/metric rows in workbook: {duplicates}")
    return WorkbookParseResult(
        outcomes=sorted(outcomes, key=lambda item: (item.case_id, item.metric)),
        selected_sheet=sheet.title,
        header_row_number=header_row,
        layout=layout,
        warnings=warnings,
    )


def parse_assets_archive(content: bytes, mapping: dict[str, Any]) -> list[ParsedAsset]:
    archive_cfg = mapping.get("archive", {})
    extensions = {str(item).lower() for item in archive_cfg.get("allowed_extensions", [])}
    max_entries = int(archive_cfg.get("max_entries", 500))
    max_bytes = int(archive_cfg.get("max_entry_bytes", 50 * 1024 * 1024))
    lookup = campaign_lookup(mapping)
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise OzonShowcaseError("Creative archive is not a valid ZIP") from exc

    assets: list[ParsedAsset] = []
    with archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        if len(infos) > max_entries:
            raise OzonShowcaseError(f"Creative archive exceeds max_entries={max_entries}")
        for info in infos:
            if unsafe_zip_member(info.filename):
                raise OzonShowcaseError(f"Unsafe ZIP member path: {info.filename}")
            if info.filename.startswith("__MACOSX/") or info.filename.rsplit("/", 1)[-1].startswith("._"):
                continue
            filename = info.filename.rsplit("/", 1)[-1]
            extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if extension not in extensions:
                continue
            if info.file_size > max_bytes:
                raise OzonShowcaseError(f"ZIP member exceeds max_entry_bytes: {info.filename}")
            raw = archive.read(info)
            digest = hashlib.sha256(raw).hexdigest()
            rule = _match_rule(filename, digest, mapping["asset_rules"])
            notes: list[str] = []
            if rule:
                status = rule["linkage_status"]
                confidence = float(rule.get("linkage_confidence", _default_confidence(status)))
                if rule.get("sha256") and rule["sha256"] != digest:
                    status = _degrade(status)
                    confidence = min(confidence, 0.65)
                    notes.append("Filename matched canonical rule but SHA-256 differs")
                notes.extend([str(rule["notes"])] if rule.get("notes") else [])
                identity = {
                    "brand": rule.get("brand"),
                    "platform": rule.get("inferred_platform"),
                    "case_id": rule.get("linked_case_id"),
                    "status": status,
                    "confidence": confidence,
                }
            else:
                identity = _infer_identity(filename, lookup)
                notes.append("No deterministic asset rule matched; linkage remains heuristic")
            if identity["status"] not in ALLOWED_LINKAGE_STATUSES:
                raise OzonShowcaseError(f"Invalid linkage status for {filename}")
            width, height = image_dimensions(raw)
            assets.append(
                ParsedAsset(
                    archive_path=info.filename,
                    filename=filename,
                    sha256=digest,
                    content=raw,
                    extension=extension,
                    mime_type=mimetypes.types_map.get(extension, "application/octet-stream"),
                    width=width,
                    height=height,
                    brand=identity.get("brand"),
                    inferred_platform=identity.get("platform"),
                    linked_case_id=identity.get("case_id"),
                    linkage_status=identity["status"],
                    linkage_confidence=float(identity["confidence"]),
                    notes=notes,
                )
            )
    if not assets:
        raise OzonShowcaseError("Creative archive contains no supported image assets")
    duplicate_hashes = [key for key, count in Counter(item.sha256 for item in assets).items() if count > 1]
    if duplicate_hashes:
        raise OzonShowcaseError(f"Creative archive contains duplicate asset bytes: {duplicate_hashes}")
    return sorted(assets, key=lambda item: item.filename.casefold())


def validate_showcase_package(
    outcomes: list[ParsedOutcome],
    assets: list[ParsedAsset],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    limitations: list[dict[str, Any]] = []
    campaign_ids = {item.case_id for item in outcomes}
    by_case: dict[str, list[ParsedAsset]] = defaultdict(list)
    for asset in assets:
        if asset.linked_case_id:
            by_case[asset.linked_case_id].append(asset)
        if asset.linkage_status == "rejected":
            limitations.append(_limit("rejected_asset_link", "warning", asset, "Asset linkage is rejected and must not be used as campaign evidence."))
        elif asset.linkage_status in {"uncertain", "probable"}:
            limitations.append(_limit("non_exact_asset_link", "warning", asset, f"Asset linkage remains {asset.linkage_status}; individual-asset attribution is not allowed."))
        elif asset.linkage_status == "missing":
            limitations.append(_limit("asset_without_outcomes", "info", asset, "Creative has no linked campaign outcome row and remains holdout/unlabelled evidence."))
    for case_id in sorted(campaign_ids):
        accepted = [item for item in by_case.get(case_id, []) if item.linkage_status not in {"rejected", "missing"}]
        if not accepted:
            limitations.append({
                "code": "campaign_without_accepted_asset",
                "severity": "warning",
                "case_id": case_id,
                "asset": None,
                "message": "Campaign has outcomes but no accepted creative linkage.",
            })
        elif len(accepted) > 1:
            limitations.append({
                "code": "campaign_multi_asset",
                "severity": "info",
                "case_id": case_id,
                "asset": None,
                "asset_count": len(accepted),
                "message": "Campaign-level outcomes are linked to multiple assets; asset-isolated attribution is prohibited.",
            })
    for asset in assets:
        if asset.linked_case_id and asset.linked_case_id not in campaign_ids:
            warnings.append(f"Asset {asset.filename} references {asset.linked_case_id}, which has no outcome row")
    allow = set(mapping.get("validation", {}).get("allowed_metrics", []))
    unexpected = sorted({item.metric for item in outcomes} - allow) if allow else []
    if unexpected:
        warnings.append(f"Workbook contains metrics outside mapping allow-list: {unexpected}")
    present = {item["code"] for item in limitations}
    for expected in mapping.get("validation", {}).get("expected_limitations", []):
        if expected.get("code") not in present:
            warnings.append(f"Expected limitation {expected.get('code')!r} was not observed; verify real package mapping")
    return {"warnings": warnings, "limitations": limitations}


def _make_outcome(*, campaign, metric, cg_rate, tg_rate, control_n, test_n, platform, period_start, period_end, sheet, row_number, payload, notes):
    if cg_rate is None and tg_rate is None:
        return None
    all_notes = list(notes)
    if cg_rate is None or tg_rate is None:
        all_notes.append("One CG/TG rate is missing; metric remains partial")
    uplift = round((tg_rate - cg_rate) * 100.0, 10) if cg_rate is not None and tg_rate is not None else None
    return ParsedOutcome(
        case_id=campaign["case_id"],
        brand=campaign["brand"],
        period_start=period_start,
        period_end=period_end,
        platform=text(platform),
        control_n=control_n,
        test_n=test_n,
        metric=metric,
        cg_rate=cg_rate,
        tg_rate=tg_rate,
        uplift_pp=uplift,
        evidence_status="source_observed",
        source_sheet=sheet,
        source_row_number=row_number,
        source_payload=payload,
        notes=all_notes,
    )


def _select_table(workbook, mapping):
    best = None
    best_score = -1
    scan_rows = int(mapping["workbook"].get("header_scan_rows", 30))
    for sheet in workbook.worksheets:
        for row_number, row in enumerate(sheet.iter_rows(min_row=1, max_row=scan_rows, values_only=True), start=1):
            headers = list(row)
            if not any(value not in (None, "") for value in headers):
                continue
            score, layout = _score_header(headers, mapping)
            name_token = normalize_token(sheet.title)
            if any(normalize_token(pattern) in name_token for pattern in mapping["workbook"].get("sheet_name_patterns", [])):
                score += 2
            if layout and score > best_score:
                best = (sheet, row_number, headers, layout)
                best_score = score
    return best if best and best_score >= int(mapping["workbook"].get("minimum_header_score", 5)) else None


def _score_header(headers, mapping):
    aliases = mapping["workbook"]["columns"]
    index = header_index(headers)
    base = sum(find_alias_column(index, aliases.get(field, [])) is not None for field in ("case_id", "brand", "period", "period_start", "period_end", "platform", "control_n", "test_n"))
    long_hits = sum(find_alias_column(index, aliases.get(field, [])) is not None for field in ("metric", "cg_rate", "tg_rate"))
    wide = _wide_metric_columns(headers, mapping)
    if long_hits == 3:
        return base + 4, "long"
    if wide:
        return base + 2 + 2 * len(wide), "wide"
    return base, None


def _wide_metric_columns(headers, mapping):
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for position, header in enumerate(headers):
        token = normalize_token(header)
        metric = next((name for name, aliases in mapping["workbook"]["metrics"].items() if any(normalize_token(alias) in token for alias in [name, *aliases])), None)
        group = next((name for name, aliases in mapping["workbook"]["groups"].items() if any(normalize_token(alias) in token for alias in [name, *aliases])), None)
        if metric and group in {"cg", "tg"}:
            result[metric][group] = position
    return {metric: pair for metric, pair in result.items() if {"cg", "tg"} <= pair.keys()}


def _match_rule(filename, digest, rules):
    by_sha = [rule for rule in rules if rule.get("sha256") == digest]
    if len(by_sha) == 1:
        return by_sha[0]
    by_name = [rule for rule in rules if normalize_token(rule.get("filename")) == normalize_token(filename)]
    if len(by_name) == 1:
        return by_name[0]
    return next((rule for rule in rules if rule.get("filename_regex") and re.search(rule["filename_regex"], filename, re.IGNORECASE)), None)


def _infer_identity(filename, lookup):
    token = normalize_token(filename)
    matches = {item["case_id"]: item for alias, item in lookup.items() if alias and alias in token}
    platform = "OZON" if "ozon" in token else "VK" if "vk" in token or "vkontakte" in token else None
    if len(matches) == 1:
        campaign = next(iter(matches.values()))
        expected = text(campaign.get("expected_platform"))
        rejected = expected and platform and expected.casefold() != platform.casefold()
        return {
            "case_id": campaign["case_id"],
            "brand": campaign["brand"],
            "platform": platform,
            "status": "rejected" if rejected else "uncertain",
            "confidence": 0.95 if rejected else 0.45,
        }
    return {"case_id": None, "brand": None, "platform": platform, "status": "missing", "confidence": 0.0}


def _default_confidence(status):
    return {"exact": 1.0, "probable": 0.75, "one_to_many": 0.8, "uncertain": 0.4, "missing": 0.0, "rejected": 1.0}[status]


def _degrade(status):
    if status == "exact":
        return "probable"
    if status in {"probable", "one_to_many"}:
        return "uncertain"
    return status


def _limit(code, severity, asset, message):
    return {"code": code, "severity": severity, "case_id": asset.linked_case_id, "asset": asset.filename, "message": message}


def _workbook_layout(workbook):
    result = {}
    for sheet in workbook.worksheets:
        rows = []
        for row in sheet.iter_rows(min_row=1, max_row=12, values_only=True):
            values = list(row)
            if any(value not in (None, "") for value in values):
                rows.append(values[:25])
        result[sheet.title] = rows
    return result
