import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "calibration" / "ozon_brand_lift_v1"
PROFILE_PATH = ROOT / "config" / "pilot_profiles" / "ozon_brand_lift_calibration_v1.json"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_ozon_calibration_outcomes_are_non_causal_and_complete():
    rows = _read_csv(DATA_DIR / "campaign_outcomes.csv")

    assert len(rows) == 27
    assert len({row["case_id"] for row in rows}) == 9
    assert all(row["causal_interpretation_allowed"] == "false" for row in rows)
    assert sum(row["evidence_status"] == "fdr_supported" for row in rows) == 11
    assert all(float(row["ci95_low_pp"]) <= float(row["uplift_pp"]) <= float(row["ci95_high_pp"]) for row in rows)


def test_ozon_creative_manifest_preserves_linkage_uncertainty():
    rows = _read_csv(DATA_DIR / "creative_manifest.csv")

    assert len(rows) == 16
    relief = next(row for row in rows if row["brand"] == "Relief")
    triderm = next(row for row in rows if row["brand"] == "Triderm")

    assert relief["inferred_platform"] == "VK"
    assert relief["linkage_confidence"] == "low"
    assert triderm["linked_case_id"] == ""
    assert triderm["linkage_confidence"] == "none"


def test_ozon_calibrated_rubric_has_consistent_score_direction():
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    criteria = profile["rubric"]["criteria"]
    names = [criterion["name"] for criterion in criteria]

    assert profile["demo"] is False
    assert len(criteria) == 12
    assert len(set(names)) == len(names)
    assert "negative_reaction_resilience" in names
    assert "negativity_risk" not in names
    assert profile["calibration_reference"]["dataset_path"].endswith("campaign_outcomes.csv")
