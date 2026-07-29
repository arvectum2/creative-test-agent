from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.modules.clients.models import Client
from src.modules.creative_assets.models import CreativeAsset
from src.modules.import_sessions.models import ImportSession, ImportSessionStatus, ImportSourceFile
from src.modules.import_sessions.storage import ImmutableOriginalStorage
from src.modules.normalized_data.models import (
    Campaign,
    CreativeRecord,
    NormalizationRun,
    NormalizationRunStatus,
    NormalizedRowStatus,
    NormalizedSourceRow,
    PerformanceObservation,
    Placement,
    Platform,
)
from src.modules.projects.models import Project, ProjectStatus
from src.shared.db.repository import db_session, json_dumps, json_loads
from src.shared.db.session import init_db
from src.shared.storage.local_storage import LocalStorage

from .contracts import LOADER_NAME, ParsedAsset, ParsedOutcome
from .utils import fingerprint, text


def persist_showcase(
    *,
    mapping: dict[str, Any],
    source_fingerprint: str,
    assets_file: Path,
    outcomes_file: Path,
    assets_bytes: bytes,
    outcomes_bytes: bytes,
    assets: list[ParsedAsset],
    outcomes: list[ParsedOutcome],
    workbook_metadata: dict[str, Any],
    source_hashes: dict[str, str],
    warnings: list[str],
    limitations: list[dict[str, Any]],
) -> dict[str, Any]:
    init_db()
    immutable = ImmutableOriginalStorage()
    stored_zip = immutable.store(assets_bytes)
    stored_xlsx = immutable.store(outcomes_bytes)
    asset_storage = LocalStorage()

    with db_session() as db:
        client = _get_or_create_client(db, mapping)
        project = _get_or_create_project(db, client, mapping)
        existing = (
            db.query(NormalizationRun)
            .filter(
                NormalizationRun.project_id == project.id,
                NormalizationRun.normalizer_name == LOADER_NAME,
                NormalizationRun.normalizer_version == mapping["schema_version"],
                NormalizationRun.mapping_fingerprint == source_fingerprint,
                NormalizationRun.status == NormalizationRunStatus.completed,
            )
            .order_by(NormalizationRun.created_at.asc())
            .first()
        )
        if existing is not None:
            return {
                "client_id": client.id,
                "project_id": project.id,
                "import_session_id": existing.import_session_id,
                "normalization_run_id": existing.id,
                "idempotent_reuse": True,
                "campaign_count": existing.campaign_count,
                "outcome_count": existing.performance_observation_count,
                "creative_record_count": existing.creative_count,
                "creative_asset_count": existing.creative_count,
                "linkage_counts": _linkage_counts(db, existing.id),
            }

        session = ImportSession(
            project_id=project.id,
            name=f"Ozon showcase {source_fingerprint[:12]}",
            notes="CTA-OZON-001 local immutable source registration",
            status=ImportSessionStatus.completed,
            metadata_json=json_dumps({
                "loader": LOADER_NAME,
                "mapping_version": mapping["schema_version"],
                "source_fingerprint": source_fingerprint,
            }),
            file_count=2,
            total_bytes=len(assets_bytes) + len(outcomes_bytes),
            completed_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(session)
        db.flush()
        zip_source = _source_file(
            session=session,
            project=project,
            filename=assets_file.name,
            extension=assets_file.suffix.lower(),
            mime_type="application/zip",
            size=len(assets_bytes),
            sha256=stored_zip.sha256,
            storage_path=stored_zip.storage_path,
            metadata={"role": "creative_archive", "source_fingerprint": source_fingerprint},
        )
        xlsx_source = _source_file(
            session=session,
            project=project,
            filename=outcomes_file.name,
            extension=outcomes_file.suffix.lower(),
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size=len(outcomes_bytes),
            sha256=stored_xlsx.sha256,
            storage_path=stored_xlsx.storage_path,
            metadata={
                "role": "campaign_outcomes",
                "source_fingerprint": source_fingerprint,
                **workbook_metadata,
            },
        )
        db.add_all([zip_source, xlsx_source])
        db.flush()

        run = NormalizationRun(
            source_table_id=f"ozon-showcase:{stored_xlsx.sha256[:32]}",
            source_file_id=xlsx_source.id,
            import_session_id=session.id,
            project_id=project.id,
            run_number=1,
            normalizer_name=LOADER_NAME,
            normalizer_version=mapping["schema_version"],
            mapping_fingerprint=source_fingerprint,
            mapping_snapshot_json=json_dumps(mapping) or "{}",
            status=NormalizationRunStatus.completed,
            source_row_count=len(outcomes),
            normalized_row_count=len(outcomes),
            partial_row_count=sum(bool(item.notes) for item in outcomes),
            skipped_row_count=0,
            failed_row_count=0,
            warning_count=len(warnings),
            warnings_json=json_dumps({
                "warnings": warnings,
                "limitations": limitations,
                "source_hashes": source_hashes,
                "source_fingerprint": source_fingerprint,
            }),
        )
        db.add(run)
        db.flush()
        platforms = _create_platforms(db, run, project, outcomes, assets)
        campaigns = _create_campaigns(db, run, project, outcomes, assets)
        records = _create_assets(db, run, project, zip_source, assets, asset_storage)
        _create_outcomes(db, run, project, xlsx_source, outcomes, campaigns, platforms)
        run.campaign_count = len(campaigns)
        run.creative_count = len(records)
        run.platform_count = len(platforms)
        run.audience_segment_count = 0
        run.placement_count = len(outcomes)
        run.performance_observation_count = len(outcomes)
        db.flush()
        return {
            "client_id": client.id,
            "project_id": project.id,
            "import_session_id": session.id,
            "normalization_run_id": run.id,
            "idempotent_reuse": False,
            "campaign_count": len(campaigns),
            "outcome_count": len(outcomes),
            "creative_record_count": len(records),
            "creative_asset_count": len(records),
            "linkage_counts": dict(Counter(item.linkage_status for item in assets)),
        }


def _get_or_create_client(db, mapping):
    cfg = mapping["client"]
    existing = db.query(Client).filter(Client.name == cfg["name"]).order_by(Client.created_at.asc()).first()
    if existing:
        return existing
    model = Client(
        name=cfg["name"],
        industry=cfg.get("industry"),
        description=cfg.get("description"),
        metadata_json=json_dumps({"canonical_key": cfg.get("canonical_key"), "created_by": LOADER_NAME}),
    )
    db.add(model)
    db.flush()
    return model


def _get_or_create_project(db, client, mapping):
    cfg = mapping["project"]
    existing = (
        db.query(Project)
        .filter(Project.client_id == client.id, Project.name == cfg["name"])
        .order_by(Project.created_at.asc())
        .first()
    )
    if existing:
        return existing
    model = Project(
        client_id=client.id,
        name=cfg["name"],
        description=cfg.get("description"),
        status=ProjectStatus.active,
        metadata_json=json_dumps({"canonical_key": cfg.get("canonical_key"), "created_by": LOADER_NAME}),
    )
    db.add(model)
    db.flush()
    return model


def _source_file(*, session, project, filename, extension, mime_type, size, sha256, storage_path, metadata):
    return ImportSourceFile(
        import_session_id=session.id,
        project_id=project.id,
        original_filename=filename,
        extension=extension,
        declared_mime_type=mime_type,
        file_size_bytes=size,
        sha256=sha256,
        storage_path=storage_path,
        metadata_json=json_dumps({"provenance": "local_cli_argument", **metadata}),
    )


def _create_platforms(db, run, project, outcomes, assets):
    names = {
        text(item.platform).upper() for item in outcomes if text(item.platform)
    } | {
        text(item.inferred_platform).upper() for item in assets if text(item.inferred_platform)
    }
    result = {}
    for name in sorted(names):
        model = Platform(
            normalization_run_id=run.id,
            project_id=project.id,
            canonical_key=name.casefold(),
            name=name,
            metadata_json=json_dumps({"source": LOADER_NAME}),
        )
        db.add(model)
        db.flush()
        result[name.casefold()] = model
    return result


def _create_campaigns(db, run, project, outcomes, assets):
    grouped: dict[str, list[ParsedOutcome]] = defaultdict(list)
    assets_by_case: dict[str, list[ParsedAsset]] = defaultdict(list)
    for item in outcomes:
        grouped[item.case_id].append(item)
    for asset in assets:
        if asset.linked_case_id:
            assets_by_case[asset.linked_case_id].append(asset)
    result = {}
    for case_id, items in sorted(grouped.items()):
        linked = assets_by_case.get(case_id, [])
        model = Campaign(
            normalization_run_id=run.id,
            project_id=project.id,
            reference_key=case_id,
            brand=items[0].brand,
            product=items[0].brand,
            metadata_json=json_dumps({
                "source": LOADER_NAME,
                "case_id": case_id,
                "period_start": items[0].period_start,
                "period_end": items[0].period_end,
                "platform": items[0].platform,
                "metrics": sorted(item.metric for item in items),
                "asset_links": [
                    {
                        "filename": asset.filename,
                        "sha256": asset.sha256,
                        "status": asset.linkage_status,
                        "confidence": asset.linkage_confidence,
                    }
                    for asset in linked
                ],
                "campaign_level_outcomes": True,
                "individual_asset_attribution_allowed": len(linked) == 1 and linked[0].linkage_status == "exact",
            }),
        )
        db.add(model)
        db.flush()
        result[case_id] = model
    return result


def _create_assets(db, run, project, zip_source, assets, storage):
    existing = db.query(CreativeAsset).filter(CreativeAsset.project_id == project.id).all()
    by_sha = {
        str(json_loads(item.metadata_json).get("source_entry_sha256")): item
        for item in existing
        if json_loads(item.metadata_json).get("source_entry_sha256")
    }
    records = []
    for asset in assets:
        model = by_sha.get(asset.sha256)
        if model is None:
            relative = f"ozon_showcase/assets/sha256/{asset.sha256[:2]}/{asset.sha256}{asset.extension}"
            stored_path = storage.store_immutable(relative, asset.content, expected_sha256=asset.sha256)
            model = CreativeAsset(
                title=asset.brand or Path(asset.filename).stem,
                asset_type="image",
                original_filename=asset.filename,
                file_path=stored_path,
                mime_type=asset.mime_type,
                file_size_bytes=len(asset.content),
                project_id=project.id,
                metadata_json=json_dumps({
                    "source": LOADER_NAME,
                    "source_zip_file_id": zip_source.id,
                    "source_zip_sha256": zip_source.sha256,
                    "source_archive_path": asset.archive_path,
                    "source_entry_sha256": asset.sha256,
                    "width": asset.width,
                    "height": asset.height,
                    "brand": asset.brand,
                    "inferred_platform": asset.inferred_platform,
                    "linked_case_id": asset.linked_case_id,
                    "linkage_status": asset.linkage_status,
                    "linkage_confidence": asset.linkage_confidence,
                    "linkage_notes": asset.notes,
                }),
            )
            db.add(model)
            db.flush()
            by_sha[asset.sha256] = model
        record = CreativeRecord(
            normalization_run_id=run.id,
            project_id=project.id,
            reference_key=asset.sha256,
            display_reference=asset.filename,
            creative_asset_id=model.id,
            metadata_json=json_dumps({
                "source": LOADER_NAME,
                "source_zip_file_id": zip_source.id,
                "source_zip_sha256": zip_source.sha256,
                "source_entry_sha256": asset.sha256,
                "archive_path": asset.archive_path,
                "linked_case_id": asset.linked_case_id,
                "brand": asset.brand,
                "inferred_platform": asset.inferred_platform,
                "linkage_status": asset.linkage_status,
                "linkage_confidence": asset.linkage_confidence,
                "notes": asset.notes,
            }),
        )
        db.add(record)
        db.flush()
        records.append(record)
    return records


def _create_outcomes(db, run, project, xlsx_source, outcomes, campaigns, platforms):
    for outcome in outcomes:
        source_row_id = "ozon:" + fingerprint({
            "source_file_sha256": xlsx_source.sha256,
            "sheet": outcome.source_sheet,
            "row": outcome.source_row_number,
            "case_id": outcome.case_id,
            "metric": outcome.metric,
        })
        campaign = campaigns[outcome.case_id]
        platform = platforms.get((text(outcome.platform) or "").casefold())
        placement = Placement(
            normalization_run_id=run.id,
            project_id=project.id,
            source_row_id=source_row_id,
            campaign_id=campaign.id,
            creative_record_id=None,
            platform_id=platform.id if platform else None,
            audience_segment_id=None,
            placement_type="campaign_brand_lift",
            format=None,
            metadata_json=json_dumps({
                "source": LOADER_NAME,
                "metric": outcome.metric,
                "campaign_level_outcome": True,
                "individual_asset_attribution_allowed": False,
            }),
        )
        db.add(placement)
        db.flush()
        observation = PerformanceObservation(
            normalization_run_id=run.id,
            project_id=project.id,
            source_row_id=source_row_id,
            placement_id=placement.id,
            observation_date=outcome.period_end,
            impressions=None,
            clicks=None,
            ctr=None,
            metadata_json=json_dumps({
                "source": LOADER_NAME,
                "case_id": outcome.case_id,
                "brand": outcome.brand,
                "metric": outcome.metric,
                "period_start": outcome.period_start,
                "period_end": outcome.period_end,
                "platform": outcome.platform,
                "control_n": outcome.control_n,
                "test_n": outcome.test_n,
                "cg_rate": outcome.cg_rate,
                "tg_rate": outcome.tg_rate,
                "uplift_pp_descriptive": outcome.uplift_pp,
                "evidence_status": outcome.evidence_status,
                "causal_interpretation_allowed": False,
                "numeric_prediction_generated": False,
                "source_sheet": outcome.source_sheet,
                "source_row_number": outcome.source_row_number,
                "notes": outcome.notes,
            }),
        )
        db.add(observation)
        db.flush()
        db.add(NormalizedSourceRow(
            normalization_run_id=run.id,
            project_id=project.id,
            source_file_id=xlsx_source.id,
            source_table_id=run.source_table_id,
            source_row_id=source_row_id,
            source_row_number=outcome.source_row_number,
            status=NormalizedRowStatus.partial if outcome.notes else NormalizedRowStatus.normalized,
            issue_count=len(outcome.notes),
            issues_json=json_dumps(outcome.notes),
            source_payload_json=json_dumps(outcome.source_payload) or "{}",
            custom_fields_json=json_dumps({
                "metric": outcome.metric,
                "cg_rate": outcome.cg_rate,
                "tg_rate": outcome.tg_rate,
                "control_n": outcome.control_n,
                "test_n": outcome.test_n,
                "uplift_pp_descriptive": outcome.uplift_pp,
            }) or "{}",
            campaign_id=campaign.id,
            creative_record_id=None,
            platform_id=platform.id if platform else None,
            audience_segment_id=None,
            placement_id=placement.id,
            performance_observation_id=observation.id,
        ))


def _linkage_counts(db, run_id):
    counts: Counter[str] = Counter()
    for record in db.query(CreativeRecord).filter(CreativeRecord.normalization_run_id == run_id).all():
        counts[str(json_loads(record.metadata_json).get("linkage_status", "uncertain"))] += 1
    return dict(counts)
