from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.synthetic_creative_golden_pack import generate, validate_generated
from src.shared.config.settings import get_settings
from src.shared.vision.benchmarking import (
    GoldenContractFixtureCandidate,
    parse_candidate,
    run_benchmark,
    validate_benchmark,
)

DEFAULT_GOLDEN_DIR = Path("data/generated/synthetic_creatives/v1")
DEFAULT_OUTPUT = Path("data/generated/vision_benchmarks/latest")


def _ensure_golden_pack(path: Path) -> None:
    if not (path / "generated_manifest.json").is_file():
        generate(path)
    errors = validate_generated(path)
    if errors:
        raise ValueError("Invalid PRE-PILOT-002 golden pack:\n- " + "\n- ".join(errors))


def _print_errors(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


def _self_test(output: Path) -> int:
    golden_dir = output / "golden_pack"
    _ensure_golden_pack(golden_dir)
    result = run_benchmark(
        pack_dir=golden_dir,
        output_dir=output,
        candidates=[GoldenContractFixtureCandidate()],
        repeats=2,
    )
    errors = validate_benchmark(output)
    summary = result["candidates"][0]["summary"]
    text = summary["text_quality_first_pass"]
    observations = summary["observation_quality_consensus"]
    if text["f1"] != 1.0:
        errors.append("golden-contract fixture text F1 must be 1.0")
    if observations["f1"] != 1.0:
        errors.append("golden-contract fixture observable F1 must be 1.0")
    if summary["eligible_for_model_selection"] is not False:
        errors.append("golden-contract fixture must be excluded from selection")
    if errors:
        return _print_errors(errors)
    print(
        json.dumps(
            {
                "status": "valid",
                "command": "self-test",
                "output": str(output),
                "candidate": "fixture:golden-contract",
                "harness_only": True,
                "model_selected": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    _ensure_golden_pack(args.golden_dir)
    settings = get_settings()
    base_url = args.base_url or settings.vision_base_url
    candidates = [
        parse_candidate(
            value,
            base_url=base_url,
            timeout_seconds=args.timeout_seconds,
        )
        for value in args.candidate
    ]
    result = run_benchmark(
        pack_dir=args.golden_dir,
        output_dir=args.output,
        candidates=candidates,
        repeats=args.repeats,
        case_limit=args.case_limit,
    )
    errors = validate_benchmark(args.output)
    if args.require_available:
        unavailable = [
            item["candidate"]["candidate_id"]
            for item in result["candidates"]
            if item["summary"]["status"] == "unavailable"
        ]
        if unavailable:
            errors.append("unavailable candidates: " + ", ".join(unavailable))
    if errors:
        return _print_errors(errors)
    print(
        json.dumps(
            {
                "status": "completed",
                "command": "run",
                "output": str(args.output),
                "candidate_count": len(candidates),
                "model_selected": False,
            },
            sort_keys=True,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark local OCR/VLM candidates on the synthetic creative golden pack."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    self_test = subparsers.add_parser(
        "self-test",
        help="Validate the harness with a golden-contract fixture excluded from model selection.",
    )
    self_test.add_argument(
        "--output",
        type=Path,
        default=Path(".ci/pre-pilot-003-self-test"),
    )

    run = subparsers.add_parser(
        "run",
        help="Run real local OCR, VLM, or hybrid candidates.",
    )
    run.add_argument(
        "--candidate",
        action="append",
        required=True,
        help="Repeatable: ocr:tesseract, vlm:<model>, or hybrid:<model>.",
    )
    run.add_argument("--base-url", default=None, help="Loopback Ollama-compatible base URL.")
    run.add_argument("--golden-dir", type=Path, default=DEFAULT_GOLDEN_DIR)
    run.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    run.add_argument("--repeats", type=int, default=3)
    run.add_argument("--case-limit", type=int, default=None)
    run.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
    )
    run.add_argument(
        "--require-available",
        action="store_true",
        help="Return a non-zero exit code when any requested candidate is unavailable.",
    )

    validate = subparsers.add_parser("validate", help="Validate benchmark artifacts and hashes.")
    validate.add_argument("--input", type=Path, required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "self-test":
            return _self_test(args.output)
        if args.command == "run":
            return _run(args)
        errors = validate_benchmark(args.input)
        if errors:
            return _print_errors(errors)
        print(
            json.dumps(
                {
                    "status": "valid",
                    "command": "validate",
                    "input": str(args.input),
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
