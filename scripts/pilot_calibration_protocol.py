from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

PACKAGE_ID = "creative-test-agent-pilot-calibration"
PACKAGE_VERSION = "1.0.0"
DEFAULT_OUTPUT = Path("data/generated/pre_pilot_007_calibration/v1")
PILOT_MIN, PILOT_MAX = 15, 20
MANIFEST = "package_manifest.json"
MANIFEST_FILE = MANIFEST
SUMMARY_FILES = ("calibration_summary.json", "calibration_summary.md")

HEADERS = {
    "metric_dictionary.csv": ["metric_key", "domain", "unit", "direction", "aggregation", "evidence_source", "interpretation", "provisional_use", "final_threshold_allowed", "notes"],
    "case_register.csv": ["case_id", "creative_id", "variant_label", "asset_sha256", "source_record_id", "platform", "placement", "format", "audience_segment", "campaign_reference", "observation_start", "observation_end", "confidentiality", "evidence_class", "inclusion_status", "exclusion_reason", "calibration_partition", "notes"],
    "expert_review.csv": ["review_id", "case_id", "reviewer_id", "review_round", "finding_id", "finding_origin", "finding_category", "finding_text", "severity", "correctness", "relevance", "actionability", "evidence_traceability", "recommended_action", "reviewer_confidence", "blind_to_outcomes", "reviewed_at", "notes"],
    "finding_adjudication.csv": ["finding_id", "case_id", "reviewer_count", "agreement_status", "final_disposition", "adjudicator_id", "rationale", "adjudicated_at", "notes"],
    "outcome_linkage.csv": ["case_id", "evidence_type", "metric_name", "metric_value", "metric_unit", "source_system", "source_record_id", "observation_start", "observation_end", "context_comparable", "causal_interpretation_allowed", "provenance_sha256", "notes"],
    "questionnaire_evidence.csv": ["case_id", "study_id", "response_source", "respondent_count", "metric_name", "estimate", "scale_min", "scale_max", "real_human_count", "synthetic_count", "observed_at", "notes"],
    "workflow_log.csv": ["run_id", "case_id", "stage", "started_at", "completed_at", "wall_clock_seconds", "operator_touch_seconds", "manual_action_count", "status", "error_code", "report_version", "notes"],
    "decision_log.csv": ["decision_id", "scope", "scope_id", "decision_type", "decision", "rationale", "evidence_refs", "owner", "decided_at", "limitations_accepted"],
}
CORE = ("README.md", "calibration_protocol.json", *HEADERS.keys())
CORE_FILES = CORE
ALLOWED = {
    "confidentiality": {"synthetic", "internal", "nda_restricted"},
    "evidence_class": {"template", "synthetic", "real_client", "reference_only"},
    "inclusion_status": {"pending", "included", "excluded", "deferred"},
    "calibration_partition": {"pilot_observation_only", "development_calibration", "future_holdout", "not_applicable"},
    "finding_origin": {"system", "human_added", "human_rephrased"},
    "severity": {"info", "low", "medium", "high", "critical", "not_applicable"},
    "ternary": {"yes", "no", "uncertain", "not_assessed"},
    "agreement_status": {"pending", "agreed", "partial", "disagreed", "single_reviewer"},
    "final_disposition": {"pending", "supported", "unsupported", "revised", "missed_by_system", "not_applicable"},
    "evidence_type": {"historical_performance", "post_campaign_observation", "brand_lift_proxy", "compliance_outcome", "other"},
    "response_source": {"pending", "human", "imported_human", "synthetic", "mixed"},
    "workflow_status": {"pending", "completed", "failed", "blocked", "cancelled"},
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = HEADERS[path.name]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="raise")
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in headers} for row in rows])


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def protocol() -> dict[str, Any]:
    return {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "status": "provisional_before_real_pilot",
        "purpose": "Collect calibration and measurement evidence during a controlled real pilot; do not train or select a model.",
        "pilot_scope": {
            "planned_real_creative_cases_min": PILOT_MIN,
            "planned_real_creative_cases_max": PILOT_MAX,
            "sufficient_for": ["workflow calibration", "report usability review", "finding-level disagreement analysis"],
            "insufficient_for": ["robust model training", "validated accuracy", "causal creative lift", "regulatory certification"],
        },
        "units": {
            "creative_case": "creative variant + documented media context + observation window",
            "finding": "system finding, human-added omission or adjudicated revision",
            "outcome_observation": "provenance-linked historical or post-campaign metric; non-causal by default",
            "workflow_run": "timestamped stage for one case or batch",
        },
        "review_protocol": {
            "freeze_system_output_before_review": True,
            "finding_level_review_required": True,
            "independent_reviewers_preferred": 2,
            "blind_to_outcomes_where_practical": True,
            "adjudicate_after_independent_review": True,
            "composite_creative_score_required": False,
            "record_missing_findings_as_human_added": True,
        },
        "analysis_policy": {
            "descriptive_statistics_first": True,
            "separate_real_and_synthetic_evidence": True,
            "preserve_disagreements": True,
            "final_thresholds_defined_before_real_data": False,
            "automatic_model_selection": False,
            "automatic_threshold_tuning": False,
            "future_validated_claim_requires_holdout": True,
            "holdout_rule": "to_be_defined_after_real-data audit and methodology sign-off",
        },
        "evidence_boundary": {
            "technical_readiness_is_not_model_accuracy": True,
            "historical_ctr_is_not_causal_creative_lift": True,
            "synthetic_responses_are_not_real_respondents": True,
            "expert_review_is_not_regulatory_approval": True,
            "pilot_sample_is_not_robust_training_data": True,
            "prediction_generated_by_this_package": False,
            "accuracy_promise": False,
        },
        "required_external_claim_signoffs": ["methodology_owner", "technical_owner", "client_owner"],
        "exit_decisions": ["continue_evidence_collection", "accept_for_controlled_internal_workflow", "limit_to_descriptive_or_compliance_support", "redesign_measurement_instrument", "pause_for_data_remediation", "stop_pilot"],
    }


def metrics() -> list[dict[str, str]]:
    specs = [
        ("time_to_first_report_minutes", "workflow", "minutes", "lower_is_better", "median_and_range", "workflow_log", "Elapsed intake-to-first-report time."),
        ("operator_touch_time_minutes", "workflow", "minutes", "lower_is_better", "median_and_range", "workflow_log", "Active operator time, separate from runtime."),
        ("manual_action_count", "workflow", "count", "lower_is_better_after_learning", "median_and_range", "workflow_log", "Manual mappings, corrections and retries."),
        ("closed_loop_completion_rate", "workflow", "ratio", "higher_is_better", "completed_over_attempted", "workflow_log", "Completed divided by attempted workflow records."),
        ("expert_supported_finding_rate", "expert_review", "ratio", "higher_is_better", "yes_over_yes_plus_no", "expert_review", "Assessed system findings experts mark correct; not validated accuracy."),
        ("finding_actionability_rate", "expert_review", "ratio", "higher_is_better", "yes_over_assessed", "expert_review", "Assessed findings judged actionable."),
        ("evidence_traceability_rate", "expert_review", "ratio", "higher_is_better", "yes_over_assessed", "expert_review", "Reviewed findings with traceable evidence."),
        ("human_added_finding_count", "expert_review", "count", "lower_is_better_after_learning", "count", "expert_review", "Material omissions added by a human."),
        ("harmful_false_positive_count", "expert_review", "count", "lower_is_better", "count", "expert_review", "Unsupported high/critical system findings."),
        ("reviewer_disagreement_rate", "expert_review", "ratio", "contextual", "partial_or_disagreed_over_adjudicated", "finding_adjudication", "Finding-level disagreement retained for methodology review."),
        ("historical_metric_coverage", "outcomes", "ratio", "higher_is_better", "linked_cases_over_included", "outcome_linkage", "Included cases with provenance-linked outcomes."),
        ("human_questionnaire_case_coverage", "questionnaire", "ratio", "higher_is_better", "human_cases_over_included", "questionnaire_evidence", "Included cases with real-human questionnaire evidence."),
        ("synthetic_human_proxy_difference", "questionnaire", "scale_units", "closer_to_zero", "paired_descriptive_difference", "questionnaire_evidence", "Source-labelled synthetic versus human proxy difference."),
        ("future_prediction_absolute_error", "future_prediction", "metric_units", "lower_is_better", "mae_when_valid", "future frozen predictions + outcomes", "Reserved until real predictions and comparable outcomes exist."),
        ("future_directional_agreement", "future_prediction", "ratio", "higher_is_better", "agreement_when_valid", "future frozen predictions + outcomes", "Reserved for signed-off direction-only evaluation."),
    ]
    return [{"metric_key": key, "domain": domain, "unit": unit, "direction": direction, "aggregation": aggregation, "evidence_source": source, "interpretation": meaning, "provisional_use": "pilot baseline only", "final_threshold_allowed": "false", "notes": "No final threshold before real evidence and methodology sign-off."} for key, domain, unit, direction, aggregation, source, meaning in specs]


def case_rows() -> list[dict[str, str]]:
    rows = []
    for index in range(1, PILOT_MAX + 1):
        rows.append({"case_id": f"C{index:03d}", "confidentiality": "synthetic", "evidence_class": "template", "inclusion_status": "pending", "calibration_partition": "pilot_observation_only", "notes": "Template row; use only in the local NDA-controlled package."})
    return rows


def blank_rows() -> dict[str, list[dict[str, str]]]:
    rows = {name: [{}] for name in HEADERS if name not in {"metric_dictionary.csv", "case_register.csv"}}
    rows["outcome_linkage.csv"] = [{"causal_interpretation_allowed": "false"}]
    rows["questionnaire_evidence.csv"] = [{"response_source": "pending", "real_human_count": "0", "synthetic_count": "0"}]
    rows["workflow_log.csv"] = [{"status": "pending"}]
    return rows


def readme() -> str:
    return f"""# Creative Test Agent — pilot calibration package

Target: {PILOT_MIN}–{PILOT_MAX} real creative cases for workflow calibration, report review and finding-level disagreement analysis. This is not robust model-training data.

1. Register creative/context units in `case_register.csv` and keep source hashes.
2. Freeze system findings before expert review.
3. Record every finding in `expert_review.csv`; omissions use `finding_origin=human_added`.
4. Preserve and adjudicate disagreements in `finding_adjudication.csv`.
5. Link historical or observed outcomes in `outcome_linkage.csv`; causal interpretation must stay false.
6. Separate human and synthetic questionnaire evidence.
7. Record wall-clock time, operator touch time and manual actions.
8. Run `seal`, `validate`, then `summarize`.

```bash
python scripts/pilot_calibration_protocol.py generate --output <dir>
python scripts/pilot_calibration_protocol.py seal --input <dir>
python scripts/pilot_calibration_protocol.py validate --input <dir>
python scripts/pilot_calibration_protocol.py summarize --input <dir>
```

The package does not select a model or produce an accuracy, causal-lift, market-effectiveness or regulatory-approval claim.
"""


def to_int(value: str | None) -> int | None:
    try:
        return int((value or "").strip())
    except ValueError:
        return None


def to_float(value: str | None) -> float | None:
    try:
        result = float((value or "").strip().replace(",", "."))
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def to_bool(value: str | None) -> bool | None:
    text = (value or "").strip().lower()
    return True if text in {"true", "1", "yes"} else False if text in {"false", "0", "no"} else None


def populated(rows: list[dict[str, str]], key: str) -> list[dict[str, str]]:
    return [row for row in rows if row.get(key, "").strip()]


def package_state(root: Path) -> dict[str, Any]:
    cases = read_csv(root / "case_register.csv")
    reviews = populated(read_csv(root / "expert_review.csv"), "review_id")
    workflow = populated(read_csv(root / "workflow_log.csv"), "run_id")
    questionnaires = populated(read_csv(root / "questionnaire_evidence.csv"), "case_id")
    included = [row for row in cases if row.get("inclusion_status") == "included"]
    real = [row for row in included if row.get("evidence_class") == "real_client"]
    human = sum(to_int(row.get("real_human_count")) or 0 for row in questionnaires)
    started = bool(included or reviews or workflow or questionnaires)
    return {"template_only": not started, "contains_real_pilot_data": bool(real or human), "included_case_count": len(included), "real_client_case_count": len(real), "expert_review_count": len(reviews), "workflow_record_count": len(workflow), "real_human_response_count": human}


def manifest_files(root: Path) -> list[str]:
    return [*CORE, *(name for name in SUMMARY_FILES if (root / name).is_file())]


def seal(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    missing = [name for name in CORE if not (root / name).is_file()]
    if missing:
        raise ValueError("missing files: " + ", ".join(missing))
    value = {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        **package_state(root),
        "prediction_generated": False,
        "model_selected": False,
        "accuracy_promise": False,
        "causal_lift_claim": False,
        "files": [{"path": name, "size_bytes": (root / name).stat().st_size, "sha256": sha(root / name)} for name in manifest_files(root)],
    }
    write_json(root / MANIFEST, value)
    return value


def generate(root: Path, clean: bool = True) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if clean and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(readme(), encoding="utf-8")
    write_json(root / "calibration_protocol.json", protocol())
    write_csv(root / "metric_dictionary.csv", metrics())
    write_csv(root / "case_register.csv", case_rows())
    for name, rows in blank_rows().items():
        write_csv(root / name, rows)
    return seal(root)


def validate(root: Path) -> list[str]:
    root = root.expanduser().resolve()
    errors: list[str] = []
    for name in (*CORE, MANIFEST):
        if not (root / name).is_file():
            errors.append(f"missing required file: {name}")
    if errors:
        return errors
    try:
        doc = read_json(root / "calibration_protocol.json")
    except Exception as exc:
        return [f"invalid calibration_protocol.json: {exc}"]
    if (doc.get("package_id"), doc.get("package_version")) != (PACKAGE_ID, PACKAGE_VERSION):
        errors.append("calibration protocol identity mismatch")
    boundary = doc.get("evidence_boundary") or {}
    for key in ("technical_readiness_is_not_model_accuracy", "historical_ctr_is_not_causal_creative_lift", "synthetic_responses_are_not_real_respondents", "pilot_sample_is_not_robust_training_data"):
        if boundary.get(key) is not True:
            errors.append(f"evidence boundary must remain true: {key}")
    if boundary.get("prediction_generated_by_this_package") is not False or boundary.get("accuracy_promise") is not False:
        errors.append("protocol must not generate predictions or promise accuracy")

    tables: dict[str, list[dict[str, str]]] = {}
    for name, expected in HEADERS.items():
        with (root / name).open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if (reader.fieldnames or []) != expected:
                errors.append(f"{name}: header mismatch")
            tables[name] = list(reader)
    metric_rows = tables["metric_dictionary.csv"]
    metric_keys = [row.get("metric_key", "").strip() for row in metric_rows]
    if any(not key for key in metric_keys) or len(metric_keys) != len(set(metric_keys)):
        errors.append("metric_dictionary.csv: metric_key must be present and unique")
    for number, row in enumerate(metric_rows, 2):
        if row.get("final_threshold_allowed", "").strip().lower() != "false":
            errors.append(f"metric_dictionary.csv:{number}: final_threshold_allowed must remain false")

    cases = tables["case_register.csv"]
    ids = [row.get("case_id", "").strip() for row in cases]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        errors.append("case_register.csv: case_id must be present and unique")
    id_set = set(ids)
    for number, row in enumerate(cases, 2):
        for key in ("confidentiality", "evidence_class", "inclusion_status", "calibration_partition"):
            if row.get(key) not in ALLOWED[key]:
                errors.append(f"case_register.csv:{number}: invalid {key}")
        digest = row.get("asset_sha256", "").strip().lower()
        if digest and (len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest)):
            errors.append(f"case_register.csv:{number}: invalid asset_sha256")
        if row.get("inclusion_status") == "included":
            if row.get("evidence_class") == "template":
                errors.append(f"case_register.csv:{number}: included case cannot remain template evidence")
            for key in ("creative_id", "source_record_id", "asset_sha256"):
                if not row.get(key, "").strip():
                    errors.append(f"case_register.csv:{number}: included case requires {key}")
        if row.get("inclusion_status") == "excluded" and not row.get("exclusion_reason", "").strip():
            errors.append(f"case_register.csv:{number}: exclusion_reason required")

    reviews = populated(tables["expert_review.csv"], "review_id")
    seen: set[str] = set()
    for number, row in enumerate(reviews, 2):
        if row["review_id"] in seen:
            errors.append(f"expert_review.csv:{number}: duplicate review_id")
        seen.add(row["review_id"])
        if row.get("case_id") not in id_set:
            errors.append(f"expert_review.csv:{number}: unknown case_id")
        for key in ("reviewer_id", "finding_id", "finding_text"):
            if not row.get(key, "").strip():
                errors.append(f"expert_review.csv:{number}: {key} required")
        if row.get("finding_origin") not in ALLOWED["finding_origin"] or row.get("severity") not in ALLOWED["severity"]:
            errors.append(f"expert_review.csv:{number}: invalid origin or severity")
        for key in ("correctness", "relevance", "actionability", "evidence_traceability"):
            if row.get(key) not in ALLOWED["ternary"]:
                errors.append(f"expert_review.csv:{number}: invalid {key}")
        if to_bool(row.get("blind_to_outcomes")) is None:
            errors.append(f"expert_review.csv:{number}: blind_to_outcomes must be boolean")

    for number, row in enumerate(populated(tables["finding_adjudication.csv"], "finding_id"), 2):
        if row.get("case_id") not in id_set or row.get("agreement_status") not in ALLOWED["agreement_status"] or row.get("final_disposition") not in ALLOWED["final_disposition"]:
            errors.append(f"finding_adjudication.csv:{number}: invalid case or status")
        if (to_int(row.get("reviewer_count")) or 0) < 1:
            errors.append(f"finding_adjudication.csv:{number}: reviewer_count must be positive")
        if row.get("agreement_status") != "pending" and not all(row.get(key, "").strip() for key in ("adjudicator_id", "rationale")):
            errors.append(f"finding_adjudication.csv:{number}: adjudicated finding requires adjudicator_id and rationale")

    for number, row in enumerate(populated(tables["outcome_linkage.csv"], "case_id"), 2):
        if row.get("case_id") not in id_set or row.get("evidence_type") not in ALLOWED["evidence_type"]:
            errors.append(f"outcome_linkage.csv:{number}: invalid case or evidence_type")
        if to_bool(row.get("causal_interpretation_allowed")) is not False:
            errors.append(f"outcome_linkage.csv:{number}: causal_interpretation_allowed must be false")
        if row.get("metric_value", "").strip():
            if to_float(row.get("metric_value")) is None:
                errors.append(f"outcome_linkage.csv:{number}: metric_value must be numeric")
            if not all(row.get(key, "").strip() for key in ("metric_name", "source_system", "source_record_id")):
                errors.append(f"outcome_linkage.csv:{number}: metric source fields required")
            digest = row.get("provenance_sha256", "").strip().lower()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                errors.append(f"outcome_linkage.csv:{number}: valid provenance_sha256 required")

    for number, row in enumerate(populated(tables["questionnaire_evidence.csv"], "case_id"), 2):
        source = row.get("response_source")
        if row.get("case_id") not in id_set or source not in ALLOWED["response_source"] - {"pending"}:
            errors.append(f"questionnaire_evidence.csv:{number}: invalid case or source")
        total, human, synthetic = (to_int(row.get(key)) for key in ("respondent_count", "real_human_count", "synthetic_count"))
        if None in {total, human, synthetic} or min(total or 0, human or 0, synthetic or 0) < 0:
            errors.append(f"questionnaire_evidence.csv:{number}: counts must be non-negative integers")
        elif human + synthetic != total:
            errors.append(f"questionnaire_evidence.csv:{number}: human plus synthetic must equal respondent_count")
        if total is not None and total < 1:
            errors.append(f"questionnaire_evidence.csv:{number}: respondent_count must be positive")
        if not row.get("metric_name", "").strip():
            errors.append(f"questionnaire_evidence.csv:{number}: metric_name required")
        estimate, scale_min, scale_max = (to_float(row.get(key)) for key in ("estimate", "scale_min", "scale_max"))
        if None in {estimate, scale_min, scale_max} or scale_min >= scale_max:
            errors.append(f"questionnaire_evidence.csv:{number}: estimate and valid scale bounds required")
        elif not scale_min <= estimate <= scale_max:
            errors.append(f"questionnaire_evidence.csv:{number}: estimate must be within scale bounds")
        if source == "synthetic" and human:
            errors.append(f"questionnaire_evidence.csv:{number}: synthetic source cannot include real humans")
        if source in {"human", "imported_human"} and synthetic:
            errors.append(f"questionnaire_evidence.csv:{number}: human source cannot include synthetic responses")

    for number, row in enumerate(populated(tables["workflow_log.csv"], "run_id"), 2):
        if row.get("case_id", "").strip() and row.get("case_id") not in id_set:
            errors.append(f"workflow_log.csv:{number}: unknown case_id")
        if row.get("status") not in ALLOWED["workflow_status"] - {"pending"}:
            errors.append(f"workflow_log.csv:{number}: invalid status")
        wall, touch = (to_float(row.get(key)) for key in ("wall_clock_seconds", "operator_touch_seconds"))
        actions = to_int(row.get("manual_action_count"))
        if wall is None or touch is None or actions is None or min(wall, touch, actions) < 0:
            errors.append(f"workflow_log.csv:{number}: timing/action values must be non-negative and actions integer")
        elif touch > wall:
            errors.append(f"workflow_log.csv:{number}: operator touch exceeds wall clock")

    try:
        package = read_json(root / MANIFEST)
    except Exception as exc:
        return [*errors, f"invalid {MANIFEST}: {exc}"]
    if (package.get("package_id"), package.get("package_version")) != (PACKAGE_ID, PACKAGE_VERSION):
        errors.append("package manifest identity mismatch")
    for key in ("prediction_generated", "model_selected", "accuracy_promise", "causal_lift_claim"):
        if package.get(key) is not False:
            errors.append(f"package manifest must keep {key}=false")
    records = package.get("files") if isinstance(package.get("files"), list) else []
    if [item.get("path") for item in records if isinstance(item, dict)] != manifest_files(root):
        errors.append("package manifest file list mismatch")
    for item in records:
        if not isinstance(item, dict):
            errors.append("invalid manifest file record")
            continue
        name = str(item.get("path", ""))
        pure = PurePosixPath(name)
        if not name or pure.is_absolute() or ".." in pure.parts or "\\" in name:
            errors.append(f"unsafe manifest path: {name}")
            continue
        path = root / name
        if not path.is_file():
            errors.append(f"manifest file missing: {name}")
        else:
            if item.get("size_bytes") != path.stat().st_size:
                errors.append(f"package manifest size mismatch: {name}")
            if item.get("sha256") != sha(path):
                errors.append(f"package manifest sha256 mismatch: {name}")
    return errors


def yes_ratio(rows: list[dict[str, str]], key: str) -> dict[str, Any]:
    assessed = [row for row in rows if row.get(key) in {"yes", "no"}]
    yes = sum(row.get(key) == "yes" for row in assessed)
    return {"yes": yes, "assessed": len(assessed), "rate": yes / len(assessed) if assessed else None}


def median(rows: list[dict[str, str]], key: str) -> float | None:
    values = [value for row in rows if (value := to_float(row.get(key))) is not None]
    return statistics.median(values) if values else None


def build_summary(root: Path) -> dict[str, Any]:
    cases = read_csv(root / "case_register.csv")
    reviews = populated(read_csv(root / "expert_review.csv"), "review_id")
    adjudications = populated(read_csv(root / "finding_adjudication.csv"), "finding_id")
    outcomes = populated(read_csv(root / "outcome_linkage.csv"), "case_id")
    questions = populated(read_csv(root / "questionnaire_evidence.csv"), "case_id")
    workflow = populated(read_csv(root / "workflow_log.csv"), "run_id")
    decisions = populated(read_csv(root / "decision_log.csv"), "decision_id")
    included = [row for row in cases if row.get("inclusion_status") == "included"]
    real = [row for row in included if row.get("evidence_class") == "real_client"]
    synthetic = [row for row in included if row.get("evidence_class") == "synthetic"]
    attempted = [row for row in workflow if row.get("status") in {"completed", "failed", "blocked", "cancelled"}]
    completed = [row for row in attempted if row.get("status") == "completed"]
    linked_cases = {row["case_id"] for row in outcomes if row.get("metric_value", "").strip()}
    human_cases = {row["case_id"] for row in questions if (to_int(row.get("real_human_count")) or 0) > 0}
    synthetic_cases = {row["case_id"] for row in questions if (to_int(row.get("synthetic_count")) or 0) > 0}
    adjudicated = [row for row in adjudications if row.get("agreement_status") != "pending"]
    disagreements = sum(row.get("agreement_status") in {"partial", "disagreed"} for row in adjudicated)
    real_responses = sum(to_int(row.get("real_human_count")) or 0 for row in questions)
    synthetic_responses = sum(to_int(row.get("synthetic_count")) or 0 for row in questions)
    real_ids = {row["case_id"] for row in real}
    reviewed_case_ids = {row.get("case_id") for row in reviews}
    workflow_case_ids = {row.get("case_id") for row in workflow if row.get("status") == "completed"}
    real_review_coverage = len(real_ids & reviewed_case_ids) / len(real_ids) if real_ids else None
    real_workflow_coverage = len(real_ids & workflow_case_ids) / len(real_ids) if real_ids else None
    started = bool(included or reviews or workflow or questions)
    status = "template_only" if not started else "evidence_collection_in_progress"
    if len(real) >= PILOT_MIN and real_review_coverage == 1.0 and real_workflow_coverage == 1.0:
        status = "methodology_review_required"
    warnings = []
    if len(real) < PILOT_MIN:
        warnings.append(f"Real creative case target not met: {len(real)}/{PILOT_MIN} minimum planned.")
    if not reviews:
        warnings.append("No finding-level expert reviews.")
    if not workflow:
        warnings.append("No workflow measurements.")
    if real_ids and real_review_coverage != 1.0:
        warnings.append("Not every included real case has a finding-level expert review.")
    if real_ids and real_workflow_coverage != 1.0:
        warnings.append("Not every included real case has a completed workflow measurement.")
    if synthetic and not real:
        warnings.append("Included cases are synthetic only; no real-pilot conclusion is allowed.")
    if synthetic_responses and not real_responses:
        warnings.append("Questionnaire evidence is synthetic only and remains a proxy.")
    return {
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "status": status,
        "pilot_sample": {"included_case_count": len(included), "real_client_case_count": len(real), "synthetic_case_count": len(synthetic), "planned_real_min": PILOT_MIN, "planned_real_max": PILOT_MAX, "real_case_target_met": len(real) >= PILOT_MIN, "robust_model_training_supported": False},
        "workflow": {"attempted_record_count": len(attempted), "completed_record_count": len(completed), "completion_rate": len(completed) / len(attempted) if attempted else None, "real_case_coverage": real_workflow_coverage, "median_wall_clock_seconds": median(completed, "wall_clock_seconds"), "median_operator_touch_seconds": median(completed, "operator_touch_seconds"), "median_manual_action_count": median(completed, "manual_action_count")},
        "expert_review": {"review_count": len(reviews), "unique_reviewer_count": len({row.get("reviewer_id") for row in reviews}), "real_case_coverage": real_review_coverage, "correctness": yes_ratio(reviews, "correctness"), "relevance": yes_ratio(reviews, "relevance"), "actionability": yes_ratio(reviews, "actionability"), "evidence_traceability": yes_ratio(reviews, "evidence_traceability"), "human_added_finding_count": sum(row.get("finding_origin") == "human_added" for row in reviews), "harmful_false_positive_count": sum(row.get("finding_origin") == "system" and row.get("correctness") == "no" and row.get("severity") in {"high", "critical"} for row in reviews), "adjudicated_finding_count": len(adjudicated), "reviewer_disagreement_rate": disagreements / len(adjudicated) if adjudicated else None},
        "outcomes": {"linked_observation_count": sum(bool(row.get("metric_value", "").strip()) for row in outcomes), "covered_case_count": len(linked_cases), "coverage_over_included_cases": len(linked_cases) / len(included) if included else None, "causal_interpretation_allowed": False},
        "questionnaire": {"record_count": len(questions), "real_human_response_count": real_responses, "synthetic_response_count": synthetic_responses, "human_case_count": len(human_cases), "synthetic_case_count": len(synthetic_cases), "evidence_sources_separated": True},
        "decisions": {"record_count": len(decisions), "external_claim_signoff_complete": False},
        "claim_boundary": {"prediction_generated": False, "model_selected": False, "validated_accuracy_claim_permitted": False, "causal_creative_lift_claim_permitted": False, "regulatory_approval_claim_permitted": False, "synthetic_evidence_is_real_market_evidence": False},
        "warnings": warnings,
    }


def fmt(value: Any) -> str:
    return "not available" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def summary_md(summary: dict[str, Any]) -> str:
    sample, workflow, expert, question = (summary[key] for key in ("pilot_sample", "workflow", "expert_review", "questionnaire"))
    lines = [
        "# PRE-PILOT-007 calibration evidence summary", "", f"Status: `{summary['status']}`", "",
        "## Sample", "", f"- Included: {sample['included_case_count']}", f"- Real client: {sample['real_client_case_count']}", f"- Synthetic: {sample['synthetic_case_count']}", f"- Planned real range: {PILOT_MIN}–{PILOT_MAX}", "- Robust model training supported: false", "",
        "## Workflow", "", f"- Completed/attempted: {workflow['completed_record_count']}/{workflow['attempted_record_count']}", f"- Completion rate: {fmt(workflow['completion_rate'])}", f"- Median wall-clock seconds: {fmt(workflow['median_wall_clock_seconds'])}", f"- Median operator-touch seconds: {fmt(workflow['median_operator_touch_seconds'])}", "",
        "## Expert review", "", f"- Reviews: {expert['review_count']}", f"- Reviewers: {expert['unique_reviewer_count']}", f"- Expert-supported finding rate: {fmt(expert['correctness']['rate'])}", f"- Actionability rate: {fmt(expert['actionability']['rate'])}", f"- Traceability rate: {fmt(expert['evidence_traceability']['rate'])}", f"- Human-added findings: {expert['human_added_finding_count']}", f"- Harmful false positives: {expert['harmful_false_positive_count']}", "",
        "## Questionnaire", "", f"- Real-human responses: {question['real_human_response_count']}", f"- Synthetic responses: {question['synthetic_response_count']}", "- Sources remain separate.", "",
        "## Claim boundary", "", "No model is selected; no validated accuracy, causal creative-lift, market-effectiveness or regulatory-approval claim is permitted.",
    ]
    if summary["warnings"]:
        lines += ["", "## Warnings", "", *[f"- {item}" for item in summary["warnings"]]]
    return "\n".join(lines) + "\n"


def summarize(root: Path) -> dict[str, Any]:
    errors = validate(root)
    if errors:
        raise ValueError("validation failed before summary: " + "; ".join(errors))
    result = build_summary(root)
    write_json(root / SUMMARY_FILES[0], result)
    (root / SUMMARY_FILES[1]).write_text(summary_md(result), encoding="utf-8")
    seal(root)
    errors = validate(root)
    if errors:
        raise ValueError("validation failed after summary: " + "; ".join(errors))
    return result


def populate_self_test(root: Path) -> None:
    cases = read_csv(root / "case_register.csv")
    for index, row in enumerate(cases[:15], 1):
        row.update({"creative_id": f"SYN-{index:03d}", "variant_label": f"Synthetic variant {index}", "asset_sha256": hashlib.sha256(f"asset-{index}".encode()).hexdigest(), "source_record_id": f"SYN-SOURCE-{index:03d}", "platform": "synthetic-platform", "placement": "synthetic-placement", "format": "banner", "audience_segment": "synthetic-audience", "campaign_reference": f"SYN-CAMPAIGN-{index:03d}", "observation_start": "2026-01-01", "observation_end": "2026-01-07", "evidence_class": "synthetic", "inclusion_status": "included", "notes": "Synthetic self-test; not a real pilot case."})
    write_csv(root / "case_register.csv", cases)
    reviews, adjudications, outcomes, questions, workflow = [], [], [], [], []
    for index in range(1, 16):
        case_id, finding_id = f"C{index:03d}", f"F-{index:03d}"
        for reviewer in (1, 2):
            reviews.append({"review_id": f"REV-{index:03d}-{reviewer}", "case_id": case_id, "reviewer_id": f"synthetic-reviewer-{reviewer}", "review_round": "1", "finding_id": finding_id, "finding_origin": "system", "finding_category": "message_clarity", "finding_text": "Synthetic finding.", "severity": "medium", "correctness": "no" if index == 15 and reviewer == 2 else "yes", "relevance": "yes", "actionability": "yes", "evidence_traceability": "yes", "recommended_action": "Review synthetic copy.", "reviewer_confidence": "0.8", "blind_to_outcomes": "true", "reviewed_at": f"2026-02-{index:02d}T10:00:00Z", "notes": "Synthetic reviewer; not a real expert."})
        adjudications.append({"finding_id": finding_id, "case_id": case_id, "reviewer_count": "2", "agreement_status": "partial" if index == 15 else "agreed", "final_disposition": "revised" if index == 15 else "supported", "adjudicator_id": "synthetic-adjudicator", "rationale": "Deterministic self-test.", "adjudicated_at": f"2026-03-{index:02d}T10:00:00Z", "notes": "Synthetic only."})
        outcomes.append({"case_id": case_id, "evidence_type": "historical_performance", "metric_name": "ctr_observed", "metric_value": f"{0.01 + index / 10000:.4f}", "metric_unit": "fraction", "source_system": "synthetic-history", "source_record_id": f"SYN-HIST-{index:03d}", "observation_start": "2026-01-01", "observation_end": "2026-01-07", "context_comparable": "unknown", "causal_interpretation_allowed": "false", "provenance_sha256": hashlib.sha256(f"history-{index}".encode()).hexdigest(), "notes": "Synthetic historical observation; non-causal."})
        questions.append({"case_id": case_id, "study_id": "SYN-STUDY", "response_source": "synthetic", "respondent_count": "12", "metric_name": "click_intent", "estimate": f"{3.5 + index / 100:.2f}", "scale_min": "1", "scale_max": "7", "real_human_count": "0", "synthetic_count": "12", "observed_at": f"2026-02-{index:02d}T12:00:00Z", "notes": "Synthetic proxy; no real respondents."})
        workflow.append({"run_id": f"RUN-{index:03d}", "case_id": case_id, "stage": "intake_to_report", "started_at": f"2026-02-{index:02d}T09:00:00Z", "completed_at": f"2026-02-{index:02d}T09:20:00Z", "wall_clock_seconds": str(1200 + index), "operator_touch_seconds": str(300 + index), "manual_action_count": str(index % 4), "status": "completed", "report_version": "1", "notes": "Synthetic execution measurement."})
    for name, rows in (("expert_review.csv", reviews), ("finding_adjudication.csv", adjudications), ("outcome_linkage.csv", outcomes), ("questionnaire_evidence.csv", questions), ("workflow_log.csv", workflow)):
        write_csv(root / name, rows)
    write_csv(root / "decision_log.csv", [{"decision_id": "D001", "scope": "package", "scope_id": PACKAGE_ID, "decision_type": "self_test", "decision": "continue_evidence_collection", "rationale": "Synthetic self-test cannot support a real-pilot decision.", "evidence_refs": "calibration_summary.json", "owner": "synthetic-owner", "decided_at": "2026-03-20T10:00:00Z", "limitations_accepted": "synthetic only; no model claim"}])
    seal(root)


def self_test(root: Path) -> dict[str, Any]:
    generate(root)
    populate_self_test(root)
    errors = validate(root)
    if errors:
        raise ValueError("self-test invalid before summary: " + "; ".join(errors))
    result = summarize(root)
    assert result["pilot_sample"]["included_case_count"] == 15
    assert result["pilot_sample"]["real_client_case_count"] == 0
    assert result["expert_review"]["review_count"] == 30
    assert result["questionnaire"]["synthetic_response_count"] == 180
    assert result["claim_boundary"]["validated_accuracy_claim_permitted"] is False
    return result


def check_determinism() -> None:
    with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
        generate(Path(left)); generate(Path(right))
        if {name: sha(Path(left) / name) for name in (*CORE, MANIFEST)} != {name: sha(Path(right) / name) for name in (*CORE, MANIFEST)}:
            raise RuntimeError("generated packages are not deterministic")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="PRE-PILOT-007 calibration protocol and measurement instruments")
    sub = value.add_subparsers(dest="command", required=True)
    p = sub.add_parser("generate"); p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p = sub.add_parser("seal"); p.add_argument("--input", type=Path, required=True)
    p = sub.add_parser("validate"); p.add_argument("--input", type=Path, required=True)
    p = sub.add_parser("summarize"); p.add_argument("--input", type=Path, required=True)
    p = sub.add_parser("self-test"); p.add_argument("--output", type=Path, required=True)
    sub.add_parser("check-determinism")
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "generate":
            generate(args.output); print(json.dumps({"status": "generated", **package_state(args.output)}, ensure_ascii=False, indent=2))
        elif args.command == "seal":
            print(json.dumps({"status": "sealed", **seal(args.input)}, ensure_ascii=False, indent=2))
        elif args.command == "validate":
            errors = validate(args.input)
            print(json.dumps({"status": "invalid" if errors else "valid", "errors": errors}, ensure_ascii=False, indent=2))
            return 1 if errors else 0
        elif args.command == "summarize":
            print(json.dumps(summarize(args.input), ensure_ascii=False, indent=2))
        elif args.command == "self-test":
            result = self_test(args.output); print(json.dumps({"status": "passed", "summary_status": result["status"]}, indent=2))
        else:
            check_determinism(); print(json.dumps({"status": "deterministic"}, indent=2))
    except Exception as exc:
        print(f"Calibration protocol failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
