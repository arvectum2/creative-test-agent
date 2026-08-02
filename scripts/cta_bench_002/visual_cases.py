"""CTA-BENCH-002 frozen visual case set.

Reuses the deterministic PRE-PILOT-002 golden pack for the categories it already
covers and adds deterministic renderings for the remaining CTA-BENCH-002
categories (Cyrillic-heavy, mixed Russian/English, no-text, low-resolution/blur,
multi-image). The produced manifest is immutable and SHA-256 bound.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from scripts.cta_bench_002.spec import BENCHMARK_ID, BENCHMARK_VERSION

PACK_ID = "cta-bench-002-visual-case-set"
PACK_VERSION = "1.0.0"
RENDERER_VERSION = "1.0.0"

# Deterministic order for the scored visual cases.
VISUAL_CATEGORIES = [
    "clean_text_heavy",
    "low_resolution_blur",
    "mixed_russian_english",
    "cyrillic_heavy",
    "no_text",
    "dense_layout",
    "small_disclaimer",
    "explicit_cta",
    "assessed_absence_cta_packshot_promo",
    "logo_prominence",
    "message_visual_mismatch",
    "abstain_unreadable",
    "multi_image",
]

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

_ALLOWED_STATUSES = {"present", "absent", "review_required", "uncertain"}
_OBSERVABLE_CATALOG = [
    "cta_present",
    "cta_prominent",
    "disclaimer_present",
    "disclaimer_readable",
    "visual_hierarchy_clear",
    "text_density_high",
    "brand_present",
    "brand_prominence_high",
    "absolute_claim_present",
    "compliance_review_needed",
    "image_text_conflict",
    "review_due_to_ambiguity",
    "mobile_safe_zone_respected",
    "content_clipping_risk",
    "contrast_sufficient",
    "readability_risk",
    "audience_cue_present",
    "numerical_claim_present",
    "numerical_claim_has_source",
    "urgency_pressure_present",
    "offer_clarity",
    "brand_is_fictional",
    "market_effectiveness_not_evaluated",
    "real_respondent_evidence",
]

_UNSUPPORTED = [
    "CTR prediction",
    "causal creative lift",
    "brand-lift result",
    "real respondent reaction",
    "market effectiveness ranking",
]


def _font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=max(size, 8))
    return ImageFont.load_default(size=max(size, 8))


def _color(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    if len(raw) != 6:
        raise ValueError(f"Expected #RRGGBB, got {value!r}")
    return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))


def _draw_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int],
    size: int,
    align: str = "left",
    max_lines: int = 4,
) -> None:
    if not text:
        return
    x0, y0, x1, y1 = box
    font = _font(size)
    average = max(int(size * 0.55), 1)
    width_chars = max((x1 - x0) // average, 4)
    lines = textwrap.wrap(text, width=width_chars)[:max_lines] or [text]
    line_height = max(int(size * 1.3), 10)
    y = y0
    for line in lines:
        if y + line_height > y1:
            break
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        if align == "center":
            x = x0 + max((x1 - x0 - line_width) // 2, 0)
        elif align == "right":
            x = x1 - line_width
        else:
            x = x0
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height


def _base_render() -> dict[str, Any]:
    return {
        "brand": "NOVALEN",
        "headline": "Everyday support, clearly explained",
        "body": "A fictional wellness product for synthetic testing only.",
        "cta": "LEARN MORE",
        "disclaimer": "Fictional product. Demo only. Not medical advice.",
        "background": "#F5F7FA",
        "foreground": "#132238",
        "accent": "#6C4DD8",
        "muted": "#D9DEE8",
        "show_brand": True,
        "show_cta": True,
        "show_disclaimer": True,
    }


def ImageFilter_GaussianBlur(radius: float):
    from PIL import ImageFilter

    return ImageFilter.GaussianBlur(radius)


# (case_id, category, width, height, render_overrides, expected_observations)
_CASE_SPECS = [
    (
        "clean-text-heavy",
        "clean_text_heavy",
        1080,
        1080,
        {"text_density": "high", "show_cta": True, "headline": "Support for everyday routines"},
        {
            "text_density_high": "present",
            "cta_present": "present",
            "cta_prominent": "present",
            "visual_hierarchy_clear": "absent",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "low-resolution-blur",
        "low_resolution_blur",
        1080,
        1080,
        {"blur_radius": 6.0, "low_resolution": True, "show_cta": True},
        {
            "cta_present": "review_required",
            "disclaimer_readable": "absent",
            "readability_risk": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "mixed-russian-english",
        "mixed_russian_english",
        1200,
        628,
        {
            "headline": "Поддержка для занятых дней / Support for busy days",
            "body": "Ежедневная поддержка вашего ритма. Fictional demo product.",
            "disclaimer": "Вымышленный продукт для теста. Demo only.",
        },
        {
            "cta_present": "present",
            "offer_clarity": "review_required",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "cyrillic-heavy",
        "cyrillic_heavy",
        1200,
        628,
        {
            "headline": "Проверка распознавания кириллицы",
            "body": "Фирменный вымышленный продукт для синтетического теста.",
            "cta": "УЗНАТЬ БОЛЬШЕ",
            "disclaimer": "Вымышленный продукт. Только для демонстрации.",
        },
        {
            "cta_present": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "no-text",
        "no_text",
        1080,
        1080,
        {"headline": "", "body": "", "show_cta": False, "show_disclaimer": False, "no_symbol": False},
        {
            "cta_present": "absent",
            "cta_prominent": "absent",
            "disclaimer_present": "absent",
            "brand_present": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "dense-layout",
        "dense_layout",
        1080,
        1080,
        {"layout": "overloaded", "text_density": "high", "show_cta": True},
        {
            "text_density_high": "present",
            "visual_hierarchy_clear": "absent",
            "readability_risk": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "small-disclaimer",
        "small_disclaimer",
        1200,
        628,
        {"disclaimer_scale": "tiny", "show_cta": True},
        {
            "disclaimer_present": "present",
            "disclaimer_readable": "absent",
            "compliance_review_needed": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "explicit-cta",
        "explicit_cta",
        1080,
        1080,
        {"cta": "LEARN MORE", "show_cta": True, "show_disclaimer": True},
        {
            "cta_present": "present",
            "cta_prominent": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "assessed-absence",
        "assessed_absence_cta_packshot_promo",
        1080,
        1080,
        {"show_cta": False, "show_disclaimer": True, "headline": "Support for busy days"},
        {
            "cta_present": "absent",
            "cta_prominent": "absent",
            "disclaimer_present": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "logo-prominence",
        "logo_prominence",
        1080,
        1080,
        {"show_cta": True, "show_disclaimer": True, "logo_scale": "small"},
        {
            "brand_present": "present",
            "brand_prominence_high": "absent",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "message-visual-mismatch",
        "message_visual_mismatch",
        1080,
        1080,
        {"headline": "Calm support for busy days", "alarm_symbol": True},
        {
            "image_text_conflict": "present",
            "review_due_to_ambiguity": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "abstain-unreadable",
        "abstain_unreadable",
        600,
        500,
        {"contrast": "low", "blur_radius": 4.0},
        {
            "contrast_sufficient": "absent",
            "readability_risk": "present",
            "review_due_to_ambiguity": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
    (
        "multi-image",
        "multi_image",
        1080,
        1080,
        {"multi_asset": True, "show_cta": True, "show_disclaimer": True},
        {
            "cta_present": "present",
            "brand_is_fictional": "present",
            "market_effectiveness_not_evaluated": "present",
            "real_respondent_evidence": "absent",
        },
    ),
]


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _render_one(case: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    render = dict(_base_render())
    render.update(case["render_overrides"])
    width, height = case["width"], case["height"]
    background = _color(render["background"])
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    margin = int(min(width, height) * 0.06)
    x0, x1 = margin, width - margin
    if render.get("layout") == "overloaded":
        pass
    accent = _color(render["accent"])
    muted = _color(render["muted"])
    foreground = _color(render["foreground"])
    if render.get("contrast") == "low":
        foreground = tuple(min(channel + 10, 255) for channel in background)

    if render.get("logo_scale") == "small":
        _draw_text(
            draw,
            render["brand"],
            (x0, margin, x1, margin + int(height * 0.05)),
            fill=foreground,
            size=max(width // 60, 10),
            max_lines=1,
        )
    elif render.get("show_brand", True):
        _draw_text(
            draw,
            render["brand"],
            (x0, margin, x1, margin + int(height * 0.08)),
            fill=foreground,
            size=max(width // 32, 18),
            max_lines=1,
        )

    if not render.get("no_symbol") and not render.get("multi_asset"):
        symbol = int(min(width, height) * 0.22)
        sx = x0 + max((x1 - x0 - symbol) // 2, 0)
        sy = int(height * 0.14)
        if render.get("alarm_symbol"):
            draw.polygon(
                [
                    (sx + symbol // 2, sy),
                    (sx + symbol, sy + symbol),
                    (sx, sy + symbol),
                ],
                fill=(220, 65, 70),
            )
        else:
            draw.rounded_rectangle((sx, sy, sx + symbol, sy + symbol), radius=symbol // 6, fill=accent)

    if render.get("multi_asset"):
        panel = int(height * 0.28)
        gap = int(width * 0.06)
        top = int(height * 0.16)
        draw.rounded_rectangle((x0, top, x0 + panel, top + panel), radius=8, fill=muted)
        draw.rounded_rectangle(
            (width - x0 - panel, top, width - x0, top + panel), radius=8, fill=accent
        )
        headline_top = top + panel + int(height * 0.05)
    else:
        symbol = int(min(width, height) * 0.22)
        sx = x0 + max((x1 - x0 - symbol) // 2, 0)
        sy = int(height * 0.14)
        headline_top = sy + symbol + int(height * 0.04)

    headline_height = int(height * 0.18)
    if render.get("headline"):
        _draw_text(
            draw,
            render["headline"],
            (x0, headline_top, x1, headline_top + headline_height),
            fill=foreground,
            size=max(width // 20, 22),
            align="center",
            max_lines=3,
        )
    body_top = headline_top + headline_height + int(height * 0.015)
    if render.get("body"):
        _draw_text(
            draw,
            render["body"],
            (x0 + int(width * 0.04), body_top, x1 - int(width * 0.04), int(height * 0.70)),
            fill=foreground,
            size=max(width // 38, 14),
            align="center",
            max_lines=5,
        )

    if render.get("show_cta", True) and render.get("cta"):
        top, bottom = int(height * 0.76), int(height * 0.86)
        left = x0 + int((x1 - x0) * 0.18)
        right = x1 - int((x1 - x0) * 0.18)
        draw.rounded_rectangle((left, top, right, bottom), radius=max(int(height * 0.02), 4), fill=accent)
        _draw_text(
            draw,
            render["cta"],
            (left, top, right, bottom),
            fill=(255, 255, 255),
            size=max(width // 28, 16),
            align="center",
            max_lines=1,
        )

    if render.get("show_disclaimer", True) and render.get("disclaimer"):
        tiny = render.get("disclaimer_scale") == "tiny"
        top = int(height * (0.965 if tiny else 0.915))
        _draw_text(
            draw,
            render["disclaimer"],
            (x0, top, x1, height - max(margin // 3, 1)),
            fill=foreground,
            size=max(width // (140 if tiny else 70), 8),
            align="center",
            max_lines=2,
        )

    if render.get("blur_radius"):
        image = image.filter(ImageFilter_GaussianBlur(render["blur_radius"]))
    if render.get("low_resolution"):
        small_w, small_h = max(width // 3, 64), max(height // 3, 64)
        image = image.resize((small_w, small_h), Image.Resampling.BILINEAR)
        image = image.resize((width, height), Image.Resampling.NEAREST)

    filename = f"{case['case_id']}.png"
    output_path = output_dir / filename
    info = PngImagePlugin.PngInfo()
    info.add_text("case_id", case["case_id"])
    info.add_text("category", case["category"])
    info.add_text("pack_id", PACK_ID)
    image.save(output_path, "PNG", optimize=False, compress_level=9, pnginfo=info)
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "filename": filename,
        "width": width,
        "height": height,
        "sha256": _sha_file(output_path),
        "size_bytes": output_path.stat().st_size,
        "expected_observations": case["expected_observations"],
    }


def build_case_specs() -> list[dict[str, Any]]:
    cases = []
    for case_id, category, width, height, overrides, expected in _CASE_SPECS:
        cases.append(
            {
                "case_id": case_id,
                "category": category,
                "width": width,
                "height": height,
                "render_overrides": overrides,
                "expected_observations": expected,
            }
        )
    return cases


def validate_spec(cases: list[dict[str, Any]] | None = None) -> list[str]:
    cases = cases or build_case_specs()
    errors: list[str] = []
    catalog = set(_OBSERVABLE_CATALOG)
    seen: set[str] = set()
    for case in cases:
        case_id = case.get("case_id")
        if not case_id or case_id in seen:
            errors.append(f"invalid or duplicate case_id: {case_id}")
        seen.add(case_id)
        category = case.get("category")
        if category not in VISUAL_CATEGORIES:
            errors.append(f"{case_id} unknown category {category}")
        expected = case.get("expected_observations") or {}
        for observable, status in expected.items():
            if observable not in catalog:
                errors.append(f"{case_id} unknown observable {observable}")
            if status not in _ALLOWED_STATUSES:
                errors.append(f"{case_id} invalid status {status!r}")
    for category in VISUAL_CATEGORIES:
        if category not in {case.get("category") for case in cases}:
            errors.append(f"missing category: {category}")
    return errors


def generate(output_dir: Path, *, clean: bool = True) -> dict[str, Any]:
    cases = build_case_specs()
    errors = validate_spec(cases)
    if errors:
        raise ValueError("Invalid visual case spec:\n- " + "\n- ".join(errors))
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = [_render_one(case, output_dir) for case in cases]
    spec = {"pack_id": PACK_ID, "version": PACK_VERSION, "cases": cases}
    manifest = {
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "pack_id": PACK_ID,
        "pack_version": PACK_VERSION,
        "renderer_version": RENDERER_VERSION,
        "spec_sha256": _sha_bytes(_json(spec).encode("utf-8")),
        "case_count": len(entries),
        "fictional_only": True,
        "prediction_generated": False,
        "real_respondents_used": False,
        "unsupported_conclusions": _UNSUPPORTED,
        "cases": entries,
    }
    (output_dir / "case_spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "case_manifest_visual.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_generated(output_dir: Path) -> list[str]:
    errors = validate_spec()
    manifest_path = output_dir / "case_manifest_visual.json"
    spec_path = output_dir / "case_spec.json"
    if not manifest_path.is_file() or not spec_path.is_file():
        return errors + ["case_manifest_visual.json or case_spec.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"manifest unreadable: {exc}"]
    if manifest.get("spec_sha256") != _sha_bytes(_json(spec).encode("utf-8")):
        errors.append("spec SHA-256 mismatch")
    for entry in manifest.get("cases", []):
        path = output_dir / str(entry.get("filename", ""))
        if not path.is_file():
            errors.append(f"missing asset: {path.name}")
            continue
        if _sha_file(path) != entry.get("sha256"):
            errors.append(f"SHA-256 mismatch for {path.name}")
    return errors


def check_determinism() -> list[str]:
    with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
        first, second = generate(Path(left)), generate(Path(right))
        errors = []
        if first["spec_sha256"] != second["spec_sha256"]:
            errors.append("spec hash differs between runs")
        left_hashes = {item["case_id"]: item["sha256"] for item in first["cases"]}
        right_hashes = {item["case_id"]: item["sha256"] for item in second["cases"]}
        if left_hashes != right_hashes:
            errors.append("case hashes differ between runs")
        return errors
