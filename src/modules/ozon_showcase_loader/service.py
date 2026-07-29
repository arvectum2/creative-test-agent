from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .contracts import (
    ALLOWED_LINKAGE_STATUSES,
    LOADER_NAME,
    OzonShowcaseError,
    ShowcaseLoadResult,
)
from .mapping import load_mapping, validate_mapping
from .parsers import parse_assets_archive, parse_outcomes_workbook, validate_showcase_package
from .persistence import persist_showcase
from .utils import fingerprint, resolve_report_path, write_report


def load_ozon_showcase(
    *,
    assets_path: str | Path,
    outcomes_path: str | Path,
    mapping_path: str | Path,
    report_path: str | Path | None = None,
    dry_run: bool = False,
) -> ShowcaseLoadResult:
    assets_file = Path(assets_path).expanduser().resolve()
    outcomes_file = Path(outcomes_path).expanduser().resolve()
    if not assets_file.is_file():
        raise OzonShowcaseError(f"Creative ZIP not found: {assets_file}")
    if not outcomes_file.is_file():
        raise OzonShowcaseError(f"Outcomes workbook not found: {outcomes_file}")
    if assets_file.suffix.lower() != ".zip":
        raise OzonShowcaseError("--assets must point to a ZIP archive")
    if outcomes_file.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise OzonShowcaseError("--outcomes must point to an XLSX/XLSM workbook")

    mapping, mapping_sha256 = load_mapping(mapping_path)
    assets_bytes = assets_file.read_bytes()
    outcomes_bytes = outcomes_file.read_bytes()
    assets_sha256 = hashlib.sha256(assets_bytes).hexdigest()
    outcomes_sha256 = hashlib.sha256(outcomes_bytes).hexdigest()
    source_fingerprint = fingerprint({
        "loader": LOADER_NAME,
        "mapping_version": mapping["schema_version"],
        "mapping_sha256": mapping_sha256,
        "assets_sha256": assets_sha256,
        "outcomes_sha256": outcomes_sha256,
    })

    workbook = parse_outcomes_workbook(outcomes_bytes, mapping)
    assets = parse_assets_archive(assets_bytes, mapping)
    validation = validate_showcase_package(workbook.outcomes, assets, mapping)
    warnings = [*workbook.warnings, *validation["warnings"]]
    limitations = validation["limitations"]
    linkage_counts = dict(Counter(item.linkage_status for item in assets))
    source_hashes = {
        "assets_zip_sha256": assets_sha256,
        "outcomes_xlsx_sha256": outcomes_sha256,
        "mapping_sha256": mapping_sha256,
    }
    report_target = resolve_report_path(report_path, source_fingerprint)
    report = {
        "schema_id": "cta.ozon_showcase.load_report",
        "schema_version": "1.0.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint": source_fingerprint,
        "mapping_version": mapping["schema_version"],
        "source_hashes": source_hashes,
        "source_names": {
            "assets": assets_file.name,
            "outcomes": outcomes_file.name,
            "mapping": Path(mapping_path).name,
        },
        "workbook": {
            "selected_sheet": workbook.selected_sheet,
            "header_row_number": workbook.header_row_number,
            "layout": workbook.layout,
        },
        "counts": {
            "campaigns": len({item.case_id for item in workbook.outcomes}),
            "outcomes": len(workbook.outcomes),
            "assets": len(assets),
            "linkage": linkage_counts,
        },
        "warnings": warnings,
        "limitations": limitations,
        "evidence_boundaries": {
            "causal_interpretation_allowed": False,
            "numeric_uplift_prediction_generated": False,
            "individual_asset_attribution_requires_exact_linkage": True,
            "uncertain_linkage_auto_promoted": False,
            "real_client_binaries_committed": False,
        },
    }

    if dry_run:
        write_report(report_target, {**report, "status": "validated_dry_run"})
        return ShowcaseLoadResult(
            source_fingerprint=source_fingerprint,
            mapping_version=mapping["schema_version"],
            client_id=None,
            project_id=None,
            import_session_id=None,
            normalization_run_id=None,
            idempotent_reuse=False,
            campaign_count=report["counts"]["campaigns"],
            outcome_count=len(workbook.outcomes),
            creative_asset_count=len(assets),
            creative_record_count=len(assets),
            linkage_counts=linkage_counts,
            source_hashes=source_hashes,
            warnings=warnings,
            limitations=limitations,
            report_path=str(report_target),
        )

    persisted = persist_showcase(
        mapping=mapping,
        source_fingerprint=source_fingerprint,
        assets_file=assets_file,
        outcomes_file=outcomes_file,
        assets_bytes=assets_bytes,
        outcomes_bytes=outcomes_bytes,
        assets=assets,
        outcomes=workbook.outcomes,
        workbook_metadata={
            "selected_sheet": workbook.selected_sheet,
            "header_row_number": workbook.header_row_number,
            "layout": workbook.layout,
        },
        source_hashes=source_hashes,
        warnings=warnings,
        limitations=limitations,
    )
    write_report(report_target, {
        **report,
        "status": "reused" if persisted["idempotent_reuse"] else "loaded",
        "database": {
            "client_id": persisted["client_id"],
            "project_id": persisted["project_id"],
            "import_session_id": persisted["import_session_id"],
            "normalization_run_id": persisted["normalization_run_id"],
        },
    })
    return ShowcaseLoadResult(
        source_fingerprint=source_fingerprint,
        mapping_version=mapping["schema_version"],
        client_id=persisted["client_id"],
        project_id=persisted["project_id"],
        import_session_id=persisted["import_session_id"],
        normalization_run_id=persisted["normalization_run_id"],
        idempotent_reuse=persisted["idempotent_reuse"],
        campaign_count=persisted["campaign_count"],
        outcome_count=persisted["outcome_count"],
        creative_asset_count=persisted["creative_asset_count"],
        creative_record_count=persisted["creative_record_count"],
        linkage_counts=persisted["linkage_counts"],
        source_hashes=source_hashes,
        warnings=warnings,
        limitations=limitations,
        report_path=str(report_target),
    )


__all__ = [
    "ALLOWED_LINKAGE_STATUSES",
    "OzonShowcaseError",
    "ShowcaseLoadResult",
    "load_mapping",
    "load_ozon_showcase",
    "parse_assets_archive",
    "parse_outcomes_workbook",
    "validate_mapping",
    "validate_showcase_package",
]
