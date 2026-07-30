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

from scripts.client_report_v2 import FIXED_GENERATED_AT, synthetic_workspace
from src.modules.campaign_evidence.schemas import CampaignEvidenceWorkspace
from src.modules.client_demo.schemas import (
    DemoReportArtifact,
    DemoReportState,
    DemoVisualExtraction,
    DemoVisualObservation,
    OzonClientDemoState,
)
from src.modules.client_demo.service import compose_ozon_client_demo
from src.modules.client_report_v2.rendering import (
    build_report_bundle,
    compose_report_evidence,
    validate_report_bundle,
)

DEMO_MANIFEST = "cta_demo_001_manifest.json"
OPERATOR_CHECKLIST = "cta_demo_001_operator_checklist.md"


def synthetic_demo_inputs():
    raw = synthetic_workspace()
    raw["project_name"] = "Synthetic Ozon end-to-end demo"
    first = raw["campaigns"][0]["assets"][0]
    first["preview_url"] = "/creative-assets/asset-theraflex-1/image"
    second = raw["campaigns"][1]["assets"][0]
    second["preview_url"] = "/creative-assets/asset-rennie-1/image"
    workspace = CampaignEvidenceWorkspace.model_validate(raw)

    visual_map = {
        "asset-theraflex-1": DemoVisualExtraction(
            status="available",
            provider="local_vlm",
            extraction_confidence=0.93,
            evidence_confidence=0.86,
            completeness_ratio=0.82,
            fingerprint="1" * 64,
            reference_ids=["ve-synthetic-brand", "ve-synthetic-cta", "ve-synthetic-summary"],
            observations=[
                DemoVisualObservation(
                    observation_path="visual_context.visual_summary",
                    label="Visual summary",
                    value="Packshot and brand lockup dominate; the CTA is visually secondary.",
                    confidence=0.93,
                    evidence_reference_ids=["ve-synthetic-summary"],
                    provenance=["vlm:local_vlm:visual_analysis.visual_summary"],
                ),
                DemoVisualObservation(
                    observation_path="visual_context.brand_logo_prominence",
                    label="Brand/logo prominence",
                    value="presence: present; prominence: prominent",
                    confidence=0.91,
                    evidence_reference_ids=["ve-synthetic-brand"],
                    provenance=["vlm:local_vlm:visual_analysis.brand_logo_prominence"],
                ),
                DemoVisualObservation(
                    observation_path="visual_context.cta",
                    label="CTA",
                    value="presence: present; prominence: subtle; text: Узнать больше",
                    confidence=0.88,
                    evidence_reference_ids=["ve-synthetic-cta"],
                    provenance=["vlm:local_vlm:visual_analysis.cta"],
                ),
            ],
        ),
        "asset-rennie-1": DemoVisualExtraction(
            status="limited",
            provider="local_ocr",
            extraction_confidence=0.71,
            evidence_confidence=0.51,
            completeness_ratio=0.36,
            fingerprint="2" * 64,
            reference_ids=["ve-synthetic-rennie-ocr"],
            observations=[
                DemoVisualObservation(
                    observation_path="visual_context.ocr_text",
                    label="OCR text",
                    value="Rennie",
                    confidence=0.71,
                    evidence_reference_ids=["ve-synthetic-rennie-ocr"],
                    provenance=["ocr:local_ocr:visual_analysis.detected_text"],
                )
            ],
            limitations=["unassessed_visual_fields remain missing"],
        ),
    }
    return raw, workspace, visual_map


def build_acceptance_bundle(output: Path) -> dict:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    raw, workspace, visual_map = synthetic_demo_inputs()
    report_evidence = compose_report_evidence(
        raw,
        expert_assessments=[],
        locale="ru",
        generated_at=FIXED_GENERATED_AT,
    )
    report_evidence["input_fingerprint"] = "d" * 64
    report_evidence["report_run_id"] = "rpt2-cta-demo-001-synthetic"
    report_dir = output / "report_v2"
    report_manifest = build_report_bundle(report_evidence, report_dir)
    report_errors = validate_report_bundle(report_dir)
    if report_errors:
        raise RuntimeError("Synthetic report bundle failed validation: " + "; ".join(report_errors))

    report_state = DemoReportState(
        report_id=report_manifest["report_id"],
        report_version=report_manifest["report_version"],
        release_status=(report_manifest.get("summary") or {}).get("release_status", "evidence_limited"),
        generated_at=report_manifest["generated_at"],
        manifest_sha256=_sha256_file(report_dir / "report_manifest.json"),
        artifacts=[DemoReportArtifact(**item) for item in report_manifest["artifacts"]],
    )
    demo = compose_ozon_client_demo(
        workspace,
        campaign_id="OZON-007",
        report=report_state,
        visual_by_asset=visual_map,
    )

    manifest = {
        "task": "CTA-DEMO-001",
        "schema_version": "1.0",
        "generated_at": FIXED_GENERATED_AT,
        "synthetic_only": True,
        "real_client_materials_committed": False,
        "demo": demo.model_dump(mode="json"),
        "report_bundle": {
            "directory": "report_v2",
            "manifest_sha256": report_state.manifest_sha256,
            "artifact_sha256": {
                item.artifact_type: item.sha256 for item in report_state.artifacts
            },
        },
    }
    (output / DEMO_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / OPERATOR_CHECKLIST).write_text(_checklist_markdown(demo), encoding="utf-8")
    errors = validate_acceptance_bundle(output)
    if errors:
        raise RuntimeError("Synthetic demo acceptance failed: " + "; ".join(errors))
    return manifest


def validate_acceptance_bundle(directory: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = directory / DEMO_MANIFEST
    checklist_path = directory / OPERATOR_CHECKLIST
    if not manifest_path.is_file():
        return [f"missing {DEMO_MANIFEST}"]
    if not checklist_path.is_file():
        errors.append(f"missing {OPERATOR_CHECKLIST}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        demo = OzonClientDemoState.model_validate(manifest["demo"])
    except Exception as exc:
        return [f"invalid demo manifest: {exc}"]

    if [item.ordinal for item in demo.steps] != list(range(1, 8)):
        errors.append("canonical seven-step order is not preserved")
    if [item.code for item in demo.steps] != [
        "showcase_project",
        "campaign_selection",
        "original_creative",
        "visual_extraction",
        "funnel_diagnostics",
        "cg_tg_comparison",
        "report_download",
    ]:
        errors.append("canonical step codes are incomplete or reordered")
    if not demo.demo_ready:
        errors.append("synthetic demo path is not ready")
    if demo.primary_asset is None or not demo.primary_asset.visual_extraction.observations:
        errors.append("synthetic visual extraction is missing")
    if demo.primary_asset and demo.primary_asset.asset.diagnostic.status != "completed":
        errors.append("synthetic diagnostic is not completed")
    if not demo.selected_campaign.outcomes:
        errors.append("synthetic CG/TG evidence is missing")
    if demo.report is None or not demo.report.artifacts:
        errors.append("synthetic report download step is missing")
    if demo.evidence_boundaries.causal_interpretation_allowed:
        errors.append("causal interpretation must remain disabled")
    if demo.evidence_boundaries.individual_asset_outcome_attribution_allowed:
        errors.append("individual asset outcome attribution must remain disabled")
    if demo.evidence_boundaries.missing_values_inferred:
        errors.append("missing values must not be inferred")
    errors.extend(validate_report_bundle(directory / "report_v2"))
    return errors


def check_determinism() -> bool:
    with tempfile.TemporaryDirectory(prefix="cta-demo-001-") as tmp:
        root = Path(tmp)
        build_acceptance_bundle(root / "first")
        build_acceptance_bundle(root / "second")
        return _file_hashes(root / "first") == _file_hashes(root / "second")


def _checklist_markdown(demo: OzonClientDemoState) -> str:
    lines = [
        "# CTA-DEMO-001 — synthetic operator checklist",
        "",
        "This artifact contains synthetic evidence only.",
        "",
    ]
    for step in demo.steps:
        lines.append(f"- [x] {step.ordinal}. {step.title} — `{step.status}`")
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            "- [x] CG/TG remains campaign-level factual evidence.",
            "- [x] Agent diagnostics remain asset-level model outputs.",
            "- [x] No causal uplift claim or numeric prediction is generated.",
            "- [x] Missing values remain missing.",
            "- [x] Report artifacts are integrity checked.",
            "",
        ]
    )
    return "\n".join(lines)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_hashes(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): _sha256_file(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CTA-DEMO-001 synthetic acceptance harness")
    sub = parser.add_subparsers(dest="command", required=True)
    self_test = sub.add_parser("self-test")
    self_test.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--input", type=Path, required=True)
    sub.add_parser("check-determinism")
    args = parser.parse_args()

    if args.command == "self-test":
        build_acceptance_bundle(args.output)
        print(args.output)
        return 0
    if args.command == "validate":
        errors = validate_acceptance_bundle(args.input)
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        print("CTA-DEMO-001 bundle is valid")
        return 0
    if args.command == "check-determinism":
        if not check_determinism():
            print("CTA-DEMO-001 bundle is not deterministic", file=sys.stderr)
            return 1
        print("CTA-DEMO-001 bundle is deterministic")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
