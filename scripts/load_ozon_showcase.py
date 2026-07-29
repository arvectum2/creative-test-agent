#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.modules.ozon_showcase_loader import OzonShowcaseError, load_ozon_showcase

DEFAULT_MAPPING = REPO_ROOT / "config" / "ozon_showcase" / "mapping_v1.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Assemble the local Ozon showcase project from a creative ZIP and a CG/TG XLSX. "
            "Real client binaries stay outside Git and are stored only in the configured local storage."
        )
    )
    parser.add_argument("--assets", required=True, help="Path to the local creative ZIP")
    parser.add_argument("--outcomes", required=True, help="Path to the local CG/TG XLSX/XLSM")
    parser.add_argument(
        "--mapping",
        default=str(DEFAULT_MAPPING),
        help=f"Versioned mapping JSON (default: {DEFAULT_MAPPING.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--report",
        default=None,
        help=(
            "JSON report file or directory. Default: "
            "data/generated/ozon_showcase/<source_fingerprint>.json"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and produce the Data Quality/load report without writing database records",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = load_ozon_showcase(
            assets_path=args.assets,
            outcomes_path=args.outcomes,
            mapping_path=args.mapping,
            report_path=args.report,
            dry_run=args.dry_run,
        )
    except OzonShowcaseError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"status": "ok", **result.to_dict()}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
