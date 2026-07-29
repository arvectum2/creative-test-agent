from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import Workbook
from PIL import Image

from src.modules.creative_assets.models import CreativeAsset
from src.modules.import_sessions.models import ImportSession, ImportSourceFile
from src.modules.normalized_data.models import (
    Campaign,
    CreativeRecord,
    NormalizationRun,
    PerformanceObservation,
)
from src.modules.ozon_showcase_loader import (
    load_mapping,
    load_ozon_showcase,
    parse_assets_archive,
    parse_outcomes_workbook,
)
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session, json_loads

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MAPPING = REPO_ROOT / "config" / "ozon_showcase" / "mapping_v1.json"
FIXTURE_SPEC = REPO_ROOT / "tests" / "fixtures" / "ozon_showcase" / "fixture_spec.json"


@pytest.fixture
def isolated_ozon_storage(tmp_path):
    settings = get_settings()
    old_root = settings.storage_root
    settings.storage_root = str(tmp_path / "storage")
    try:
        yield tmp_path
    finally:
        settings.storage_root = old_root


def _png_bytes(seed: int) -> bytes:
    image = Image.new("RGB", (32 + seed, 18 + seed), (seed * 17 % 255, 90, 180))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _build_synthetic_package(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, bytes]]:
    assets = {
        "Bepanthen_Ozon_1.png": _png_bytes(1),
        "Bepanthen_Ozon_2.png": _png_bytes(2),
        "Relief_VK.png": _png_bytes(3),
        "Supradyn_Immuno_Ozon.png": _png_bytes(4),
        "Triderm_Ozon.png": _png_bytes(5),
    }
    zip_path = tmp_path / "Synthetic_Ozon.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in assets.items():
            archive.writestr(f"creatives/{name}", content)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Ozon Brand Lift"
    sheet.append(["Synthetic fixture — no client data"])
    sheet.append(
        [
            "case_id",
            "brand",
            "period",
            "platform",
            "control_n",
            "test_n",
            "Ad recall CG",
            "Ad recall TG",
            "Awareness CG",
            "Awareness TG",
            "Purchase intent CG",
            "Purchase intent TG",
        ]
    )
    sheet.append(
        ["OZON-001", "Bepanthen Ointment", "2025-01-01/2025-01-31", "OZON", 1000, 1100, 0.20, 0.22, 0.25, 0.26, 0.23, 0.24]
    )
    sheet.append(
        ["OZON-004", "Relief", "2025-02-01/2025-02-28", "OZON", 900, 950, 0.29, 0.32, 0.30, 0.34, 0.28, 0.31]
    )
    sheet.append(
        ["OZON-005", "Supradyn Immuno", "2025-03-01/2025-03-31", "OZON", 1024, 1079, 0.18, 0.26, 0.22, 0.30, 0.23, 0.31]
    )
    xlsx_path = tmp_path / "Synthetic_Test.xlsx"
    workbook.save(xlsx_path)

    unique = uuid4().hex
    mapping = {
        "schema_id": "cta.ozon_showcase.mapping",
        "schema_version": "1.0.0",
        "client": {
            "canonical_key": f"synthetic-client-{unique}",
            "name": f"Synthetic Ozon Client {unique}",
            "industry": "test",
            "description": "Synthetic fixture only",
        },
        "project": {
            "canonical_key": f"synthetic-project-{unique}",
            "name": f"Synthetic Ozon Project {unique}",
            "description": "Synthetic fixture only",
        },
        "archive": {
            "allowed_extensions": [".png"],
            "max_entries": 20,
            "max_entry_bytes": 1000000,
        },
        "workbook": {
            "sheet_name_patterns": ["ozon", "brand lift"],
            "header_scan_rows": 10,
            "minimum_header_score": 5,
            "columns": {
                "case_id": ["case_id"],
                "brand": ["brand"],
                "period": ["period"],
                "period_start": ["period_start"],
                "period_end": ["period_end"],
                "platform": ["platform"],
                "control_n": ["control_n"],
                "test_n": ["test_n"],
                "metric": ["metric"],
                "cg_rate": ["cg_rate"],
                "tg_rate": ["tg_rate"],
            },
            "metrics": {
                "ad_recall": ["ad recall"],
                "awareness": ["awareness"],
                "purchase_intent": ["purchase intent"],
            },
            "groups": {"cg": ["cg", "control"], "tg": ["tg", "test"]},
        },
        "campaigns": [
            {"case_id": "OZON-001", "brand": "Bepanthen Ointment", "aliases": ["Bepanthen"], "expected_platform": "OZON"},
            {"case_id": "OZON-004", "brand": "Relief", "aliases": ["Relief"], "expected_platform": "OZON"},
            {"case_id": "OZON-005", "brand": "Supradyn Immuno", "aliases": ["Supradyn Immuno"], "expected_platform": "OZON"},
        ],
        "asset_rules": [],
        "validation": {
            "allowed_metrics": ["ad_recall", "awareness", "purchase_intent"],
            "expected_limitations": [
                {"code": "rejected_asset_link"},
                {"code": "asset_without_outcomes"},
                {"code": "campaign_multi_asset"},
                {"code": "campaign_without_accepted_asset"},
            ],
        },
    }
    rule_values = [
        ("Bepanthen_Ozon_1.png", "Bepanthen Ointment", "OZON", "OZON-001", "one_to_many", 0.8),
        ("Bepanthen_Ozon_2.png", "Bepanthen Ointment", "OZON", "OZON-001", "one_to_many", 0.8),
        ("Relief_VK.png", "Relief", "VK", "OZON-004", "rejected", 1.0),
        ("Supradyn_Immuno_Ozon.png", "Supradyn Immuno", "OZON", "OZON-005", "exact", 1.0),
        ("Triderm_Ozon.png", "Triderm", "OZON", None, "missing", 0.0),
    ]
    for filename, brand, platform, case_id, status, confidence in rule_values:
        mapping["asset_rules"].append(
            {
                "filename": filename,
                "sha256": hashlib.sha256(assets[filename]).hexdigest(),
                "brand": brand,
                "inferred_platform": platform,
                "linked_case_id": case_id,
                "linkage_status": status,
                "linkage_confidence": confidence,
                "notes": "Synthetic fixture rule",
            }
        )
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return zip_path, xlsx_path, mapping_path, assets


def test_canonical_mapping_and_fixture_contract_are_versioned():
    mapping, mapping_sha = load_mapping(CANONICAL_MAPPING)
    fixture = json.loads(FIXTURE_SPEC.read_text(encoding="utf-8"))

    assert mapping["schema_version"] == "1.0.0"
    assert len(mapping_sha) == 64
    assert {item["case_id"] for item in mapping["campaigns"]} == {
        f"OZON-{number:03d}" for number in range(1, 10)
    }
    assert {rule["linkage_status"] for rule in mapping["asset_rules"]} >= {
        "exact",
        "probable",
        "one_to_many",
        "missing",
        "rejected",
    }
    assert fixture["required_report_boundaries"]["uncertain_linkage_auto_promoted"] is False


def test_synthetic_workbook_and_archive_preserve_linkage_boundaries(tmp_path):
    zip_path, xlsx_path, mapping_path, assets = _build_synthetic_package(tmp_path)
    mapping, _ = load_mapping(mapping_path)

    workbook = parse_outcomes_workbook(xlsx_path.read_bytes(), mapping)
    parsed_assets = parse_assets_archive(zip_path.read_bytes(), mapping)

    assert workbook.layout == "wide"
    assert len(workbook.outcomes) == 9
    assert {item.linkage_status for item in parsed_assets} == {
        "exact",
        "one_to_many",
        "missing",
        "rejected",
    }

    mutated = dict(assets)
    mutated["Supradyn_Immuno_Ozon.png"] = _png_bytes(11)
    changed_zip = io.BytesIO()
    with zipfile.ZipFile(changed_zip, "w") as archive:
        for name, content in mutated.items():
            archive.writestr(name, content)
    changed_assets = parse_assets_archive(changed_zip.getvalue(), mapping)
    changed_exact = next(item for item in changed_assets if item.filename == "Supradyn_Immuno_Ozon.png")
    assert changed_exact.linkage_status == "probable"
    assert changed_exact.linkage_confidence <= 0.65


def test_loader_is_idempotent_and_writes_data_quality_report(isolated_ozon_storage):
    zip_path, xlsx_path, mapping_path, _ = _build_synthetic_package(isolated_ozon_storage)
    report_dir = isolated_ozon_storage / "reports"

    first = load_ozon_showcase(
        assets_path=zip_path,
        outcomes_path=xlsx_path,
        mapping_path=mapping_path,
        report_path=report_dir,
    )
    second = load_ozon_showcase(
        assets_path=zip_path,
        outcomes_path=xlsx_path,
        mapping_path=mapping_path,
        report_path=report_dir,
    )

    assert first.idempotent_reuse is False
    assert second.idempotent_reuse is True
    assert second.project_id == first.project_id
    assert second.import_session_id == first.import_session_id
    assert second.normalization_run_id == first.normalization_run_id
    assert first.campaign_count == 3
    assert first.outcome_count == 9
    assert first.creative_asset_count == 5
    assert first.linkage_counts == {
        "one_to_many": 2,
        "rejected": 1,
        "exact": 1,
        "missing": 1,
    }

    report = json.loads(Path(first.report_path).read_text(encoding="utf-8"))
    assert report["evidence_boundaries"] == {
        "causal_interpretation_allowed": False,
        "numeric_uplift_prediction_generated": False,
        "individual_asset_attribution_requires_exact_linkage": True,
        "uncertain_linkage_auto_promoted": False,
        "real_client_binaries_committed": False,
    }
    limitation_codes = {item["code"] for item in report["limitations"]}
    assert {
        "rejected_asset_link",
        "asset_without_outcomes",
        "campaign_multi_asset",
        "campaign_without_accepted_asset",
    } <= limitation_codes

    with db_session() as db:
        assert db.query(NormalizationRun).filter(NormalizationRun.id == first.normalization_run_id).count() == 1
        assert db.query(ImportSession).filter(ImportSession.project_id == first.project_id).count() == 1
        assert db.query(ImportSourceFile).filter(ImportSourceFile.project_id == first.project_id).count() == 2
        assert db.query(Campaign).filter(Campaign.normalization_run_id == first.normalization_run_id).count() == 3
        assert db.query(CreativeRecord).filter(CreativeRecord.normalization_run_id == first.normalization_run_id).count() == 5
        assert db.query(CreativeAsset).filter(CreativeAsset.project_id == first.project_id).count() == 5
        observations = (
            db.query(PerformanceObservation)
            .filter(PerformanceObservation.normalization_run_id == first.normalization_run_id)
            .all()
        )
        assert len(observations) == 9
        assert all(json_loads(item.metadata_json)["causal_interpretation_allowed"] is False for item in observations)
        assert all(item.ctr is None for item in observations)


def test_dry_run_validates_without_database_writes(isolated_ozon_storage):
    zip_path, xlsx_path, mapping_path, _ = _build_synthetic_package(isolated_ozon_storage)
    result = load_ozon_showcase(
        assets_path=zip_path,
        outcomes_path=xlsx_path,
        mapping_path=mapping_path,
        report_path=isolated_ozon_storage / "dry-run.json",
        dry_run=True,
    )

    assert result.project_id is None
    assert result.normalization_run_id is None
    assert json.loads(Path(result.report_path).read_text(encoding="utf-8"))["status"] == "validated_dry_run"
