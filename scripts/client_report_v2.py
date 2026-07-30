#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.modules.client_report_v2.rendering import (
    build_report_bundle,
    compose_report_evidence,
    validate_report_bundle,
)
from src.modules.client_report_v2.schemas import ExpertAssessmentInput

FIXED_GENERATED_AT = "2026-07-30T00:00:00+00:00"


def synthetic_workspace() -> dict:
    return {
        "project_id": "synthetic-ozon-showcase",
        "project_name": "Synthetic Ozon campaign evidence",
        "normalization_run_id": "norm-synthetic-001",
        "source_fingerprint": "a" * 64,
        "mapping_version": "ozon-showcase-loader/1.0",
        "generated_from_loader": "ozon-showcase-loader",
        "evidence_boundaries": {
            "causal_interpretation_allowed": False,
            "numeric_uplift_prediction_generated": False,
            "individual_asset_outcome_attribution_allowed": False,
            "missing_values_inferred": False,
            "diagnostics_are_model_outputs_not_factual_outcomes": True,
        },
        "summary": {
            "campaign_count": 2,
            "outcome_count": 3,
            "creative_count": 3,
            "accepted_asset_count": 2,
            "rejected_asset_count": 1,
            "unlabelled_asset_count": 0,
            "campaigns_with_diagnostics": 2,
            "campaigns_with_limitations": 1,
        },
        "campaigns": [
            {
                "campaign_id": "campaign-theraflex",
                "case_id": "OZON-007",
                "brand": "Theraflex",
                "product": "Joint care",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "platform": "Ozon",
                "is_contrast_case": True,
                "showcase_rank": 1,
                "campaign_level_outcomes": True,
                "individual_asset_attribution_allowed": False,
                "assets": [
                    {
                        "creative_record_id": "creative-theraflex-1",
                        "creative_asset_id": "asset-theraflex-1",
                        "title": "Theraflex master creative",
                        "filename": "theraflex_master.png",
                        "brand": "Theraflex",
                        "inferred_platform": "Ozon",
                        "linkage_status": "exact",
                        "linkage_confidence": 0.98,
                        "linkage_notes": ["Filename and platform match."],
                        "accepted_for_campaign_set": True,
                        "diagnostic": {
                            "test_run_id": "test-run-theraflex",
                            "status": "completed",
                            "summary": "The brand is visible; the CTA requires review.",
                            "overall_score": 7.2,
                            "proposed_recommendation": "review",
                            "effective_recommendation": "manual_review_required",
                            "visual_traceability_status": "complete",
                            "visual_decision_status": "manual_review_required",
                            "findings": [
                                {
                                    "criterion": "brand_linkage",
                                    "score": 8.0,
                                    "explanation": "Brand and product are clearly connected in the visual hierarchy.",
                                    "confidence": 0.91,
                                    "visual_confidence_score": 0.89,
                                    "visual_confidence_band": "high",
                                    "visual_abstention_status": "accepted",
                                    "visual_traceability_status": "supported",
                                    "visual_evidence_refs": ["visual:theraflex:brand-lockup"],
                                },
                                {
                                    "criterion": "cta_clarity",
                                    "score": 5.5,
                                    "explanation": "The call to action is present but visually secondary.",
                                    "confidence": 0.76,
                                    "visual_confidence_score": 0.72,
                                    "visual_confidence_band": "medium",
                                    "visual_abstention_status": "review_required",
                                    "visual_traceability_status": "supported",
                                    "visual_evidence_refs": ["visual:theraflex:cta"],
                                },
                            ],
                            "scorecard": [],
                            "risks": [],
                        },
                    }
                ],
                "outcomes": [
                    {
                        "observation_id": "obs-theraflex-recall",
                        "metric": "ad_recall",
                        "metric_label": "Ad recall",
                        "control_n": 420,
                        "test_n": 418,
                        "cg_rate": 0.31,
                        "tg_rate": 0.37,
                        "uplift_pp_descriptive": 6.0,
                        "evidence_status": "observed",
                        "period_start": "2026-01-01",
                        "period_end": "2026-01-31",
                        "platform": "Ozon",
                        "source_sheet": "Brand lift",
                        "source_row_number": 7,
                        "causal_interpretation_allowed": False,
                        "numeric_prediction_generated": False,
                        "notes": ["Descriptive CG/TG difference only."],
                    },
                    {
                        "observation_id": "obs-theraflex-pi",
                        "metric": "purchase_intent",
                        "metric_label": "Purchase intent",
                        "control_n": 420,
                        "test_n": 418,
                        "cg_rate": 0.22,
                        "tg_rate": 0.24,
                        "uplift_pp_descriptive": 2.0,
                        "evidence_status": "observed",
                        "period_start": "2026-01-01",
                        "period_end": "2026-01-31",
                        "platform": "Ozon",
                        "source_sheet": "Brand lift",
                        "source_row_number": 8,
                        "causal_interpretation_allowed": False,
                        "numeric_prediction_generated": False,
                        "notes": [],
                    },
                ],
                "limitations": [],
            },
            {
                "campaign_id": "campaign-rennie",
                "case_id": "OZON-003",
                "brand": "Rennie",
                "product": "Antacid",
                "period_start": "2026-02-01",
                "period_end": "2026-02-28",
                "platform": "Ozon",
                "is_contrast_case": True,
                "showcase_rank": 2,
                "campaign_level_outcomes": True,
                "individual_asset_attribution_allowed": False,
                "assets": [
                    {
                        "creative_record_id": "creative-rennie-1",
                        "creative_asset_id": "asset-rennie-1",
                        "title": "Rennie campaign set A",
                        "filename": "rennie_a.png",
                        "brand": "Rennie",
                        "inferred_platform": "Ozon",
                        "linkage_status": "one_to_many",
                        "linkage_confidence": 0.74,
                        "linkage_notes": ["Campaign contains multiple supplied assets."],
                        "accepted_for_campaign_set": True,
                        "diagnostic": {
                            "test_run_id": "test-run-rennie",
                            "status": "completed",
                            "summary": "Message is readable but campaign attribution is set-level only.",
                            "overall_score": 6.4,
                            "proposed_recommendation": "review",
                            "effective_recommendation": "manual_review_required",
                            "visual_traceability_status": "complete",
                            "visual_decision_status": "manual_review_required",
                            "findings": [
                                {
                                    "criterion": "message_clarity",
                                    "score": 6.5,
                                    "explanation": "The main benefit is readable, while supporting copy is dense.",
                                    "confidence": 0.82,
                                    "visual_confidence_score": 0.80,
                                    "visual_confidence_band": "high",
                                    "visual_abstention_status": "accepted",
                                    "visual_traceability_status": "supported",
                                    "visual_evidence_refs": ["visual:rennie:headline"],
                                }
                            ],
                            "scorecard": [],
                            "risks": [],
                        },
                    },
                    {
                        "creative_record_id": "creative-rennie-rejected",
                        "creative_asset_id": "asset-rennie-rejected",
                        "title": "Rennie non-Ozon asset",
                        "filename": "rennie_social.png",
                        "brand": "Rennie",
                        "inferred_platform": "social",
                        "linkage_status": "rejected",
                        "linkage_confidence": 0.99,
                        "linkage_notes": ["Platform mismatch."],
                        "accepted_for_campaign_set": False,
                        "diagnostic": {"status": "missing", "findings": [], "scorecard": [], "risks": []},
                    },
                ],
                "outcomes": [
                    {
                        "observation_id": "obs-rennie-awareness",
                        "metric": "awareness",
                        "metric_label": "Brand awareness",
                        "control_n": 390,
                        "test_n": 392,
                        "cg_rate": 0.48,
                        "tg_rate": None,
                        "uplift_pp_descriptive": None,
                        "evidence_status": "partial",
                        "period_start": "2026-02-01",
                        "period_end": "2026-02-28",
                        "platform": "Ozon",
                        "source_sheet": "Brand lift",
                        "source_row_number": 14,
                        "causal_interpretation_allowed": False,
                        "numeric_prediction_generated": False,
                        "notes": ["TG rate is missing and is not inferred."],
                    }
                ],
                "limitations": [
                    {
                        "code": "campaign_multi_asset",
                        "message": "Outcomes are campaign-level evidence and must not be attributed to one creative asset.",
                        "severity": "warning",
                        "context": {"accepted_asset_count": 1, "supplied_asset_count": 2},
                    },
                    {
                        "code": "missing_tg_rate",
                        "message": "TG rate is missing for awareness and remains missing in every export.",
                        "severity": "high",
                        "context": {"metric": "awareness"},
                    },
                ],
            },
        ],
        "unlabelled_assets": [],
    }


def synthetic_assessments() -> list[dict]:
    return [
        ExpertAssessmentInput(
            finding_id="finding:test-run-theraflex:1",
            verdict="supported",
            rationale="The evidence reference resolves to the brand lockup observation.",
            reviewer_role="senior strategist",
            confidence=0.92,
        ).model_dump(mode="json"),
        ExpertAssessmentInput(
            finding_id="finding:test-run-theraflex:2",
            verdict="needs_rewording",
            rationale="Keep the conclusion descriptive and avoid implying conversion impact.",
            reviewer_role="senior strategist",
            confidence=0.84,
        ).model_dump(mode="json"),
    ]


def build_synthetic(output: Path) -> dict:
    evidence = compose_report_evidence(
        synthetic_workspace(),
        expert_assessments=synthetic_assessments(),
        locale="ru",
        generated_at=FIXED_GENERATED_AT,
    )
    evidence["input_fingerprint"] = hashlib.sha256(b"cta-report-002-synthetic").hexdigest()
    evidence["report_run_id"] = "rpt2-synthetic-acceptance"
    return build_report_bundle(evidence, output)


def command_self_test(args) -> int:
    manifest = build_synthetic(Path(args.output))
    errors = validate_report_bundle(Path(args.output))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def command_validate(args) -> int:
    errors = validate_report_bundle(Path(args.input))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("CTA_REPORT_002_BUNDLE_VALID")
    return 0


def command_check_determinism(_args) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        first = Path(tmp) / "first"; second = Path(tmp) / "second"
        one = build_synthetic(first); two = build_synthetic(second)
        hashes_one = {item["artifact_type"]: item["sha256"] for item in one["artifacts"]}
        hashes_two = {item["artifact_type"]: item["sha256"] for item in two["artifacts"]}
        if hashes_one != hashes_two:
            print(json.dumps({"first": hashes_one, "second": hashes_two}, indent=2), file=sys.stderr)
            return 1
    print("CTA_REPORT_002_DETERMINISTIC")
    return 0


def command_generate(args) -> int:
    from src.modules.client_report_v2.service import generate_client_report_v2
    result = generate_client_report_v2(args.project_id, locale=args.locale, force=args.force)
    print(result.model_dump_json(indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="CTA-REPORT-002 client report v2 harness")
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("self-test"); p.add_argument("--output", required=True); p.set_defaults(handler=command_self_test)
    p = sub.add_parser("validate"); p.add_argument("--input", required=True); p.set_defaults(handler=command_validate)
    p = sub.add_parser("check-determinism"); p.set_defaults(handler=command_check_determinism)
    p = sub.add_parser("generate"); p.add_argument("--project-id", required=True); p.add_argument("--locale", choices=("ru", "en"), default="ru"); p.add_argument("--force", action="store_true"); p.set_defaults(handler=command_generate)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
