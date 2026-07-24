#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.modules.pre_tz_demo import DEMO_VERSION, run_messy_demo


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run CTA-PRE-012: an isolated local end-to-end demonstration over a "
            "deliberately messy campaign CSV."
        )
    )
    parser.add_argument(
        "--workspace",
        default="data/demo/cta_pre_012",
        help="Isolated directory for the demo database, originals and generated report.",
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help="Optional CSV fixture; defaults to examples/pre_tz/messy_campaign_export.csv.",
    )
    parser.add_argument(
        "--respondent-count",
        type=int,
        default=12,
        help="Number of explicitly synthetic questionnaire responses (1-500).",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete the workspace before the run. A fresh workspace is recommended.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    manifest = run_messy_demo(
        Path(args.workspace),
        fixture_path=args.fixture,
        reset=not args.keep_existing,
        respondent_count=args.respondent_count,
    )
    summary = {
        "demo": manifest["demo"],
        "demo_version": DEMO_VERSION,
        "status": manifest["status"],
        "workspace": manifest["workspace"],
        "data_quality": manifest["data_quality"]["overall_status"],
        "prediction_readiness": manifest["prediction_readiness"]["overall_status"],
        "synthetic_responses": manifest["quantitative_proxy"]["response_count"],
        "report": manifest["report"]["path"],
        "report_sha256": manifest["report"]["sha256"],
        "manifest": str(Path(manifest["workspace"]) / "demo_manifest.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
