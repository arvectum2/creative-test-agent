from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import textwrap
from copy import deepcopy
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

PACK_ID = "synthetic-creative-golden-pack"
PACK_VERSION = "1.0.0"
RENDERER_VERSION = "1.0.0"
DEFAULT_OUTPUT = Path("data/generated/synthetic_creatives/v1")
STATUSES = {"present", "absent", "review_required", "uncertain"}
OBSERVABLES = ['cta_present',
 'cta_prominent',
 'disclaimer_present',
 'disclaimer_readable',
 'visual_hierarchy_clear',
 'text_density_high',
 'brand_present',
 'absolute_claim_present',
 'compliance_review_needed',
 'image_text_conflict',
 'review_due_to_ambiguity',
 'mobile_safe_zone_respected',
 'content_clipping_risk',
 'contrast_sufficient',
 'readability_risk',
 'audience_cue_present',
 'numerical_claim_present',
 'numerical_claim_has_source',
 'urgency_pressure_present',
 'offer_clarity',
 'brand_is_fictional',
 'market_effectiveness_not_evaluated',
 'real_respondent_evidence']
UNSUPPORTED = [
    "CTR prediction",
    "causal creative lift",
    "brand-lift result",
    "real respondent reaction",
    "market effectiveness ranking",
]
BASE = {'brand': 'NOVALEN',
 'headline': 'Everyday support, clearly explained',
 'body': 'A fictional wellness product for synthetic testing only.',
 'cta': 'LEARN MORE',
 'disclaimer': 'Fictional product. Demo only. Not medical advice.',
 'claim_source': 'Synthetic specification v1',
 'background': '#F5F7FA',
 'foreground': '#132238',
 'accent': '#6C4DD8',
 'muted': '#D9DEE8',
 'layout': 'balanced',
 'text_density': 'normal',
 'contrast': 'high',
 'symbol': 'circle',
 'safe_zone': True,
 'show_brand': True,
 'show_cta': True,
 'show_disclaimer': True,
 'show_claim_source': False,
 'pressure_badge': '',
 'image_message': 'calm-support'}
PAIR_SPECS = [{'id': 'cta_presence',
  'title': 'CTA present versus absent',
  'axis': 'cta_present',
  'format': {'width': 1080, 'height': 1080, 'name': 'square'},
  'a': {'show_cta': True},
  'b': {'show_cta': False},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'cta_present': 'present', 'cta_prominent': 'present'},
  'eb': {'cta_present': 'absent', 'cta_prominent': 'absent'}},
 {'id': 'disclaimer_readability',
  'title': 'Readable versus unreadable disclaimer',
  'axis': 'disclaimer_readable',
  'format': {'width': 1200, 'height': 628, 'name': 'landscape'},
  'a': {'show_disclaimer': True, 'disclaimer_scale': 'normal'},
  'b': {'show_disclaimer': True, 'disclaimer_scale': 'tiny'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'disclaimer_present': 'present', 'disclaimer_readable': 'present'},
  'eb': {'disclaimer_present': 'present', 'disclaimer_readable': 'absent', 'compliance_review_needed': 'present'}},
 {'id': 'visual_hierarchy',
  'title': 'Balanced hierarchy versus overloaded layout',
  'axis': 'visual_hierarchy_clear',
  'format': {'width': 1080, 'height': 1080, 'name': 'square'},
  'a': {'layout': 'balanced', 'text_density': 'normal'},
  'b': {'layout': 'overloaded', 'text_density': 'high'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'visual_hierarchy_clear': 'present', 'text_density_high': 'absent'},
  'eb': {'visual_hierarchy_clear': 'absent', 'text_density_high': 'present'}},
 {'id': 'brand_presence',
  'title': 'Brand visible versus absent',
  'axis': 'brand_present',
  'format': {'width': 600, 'height': 500, 'name': 'small-banner'},
  'a': {'show_brand': True},
  'b': {'show_brand': False},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'brand_present': 'present'},
  'eb': {'brand_present': 'absent'}},
 {'id': 'claim_risk',
  'title': 'Measured wording versus guaranteed outcome',
  'axis': 'absolute_claim_present',
  'format': {'width': 1200, 'height': 628, 'name': 'landscape'},
  'a': {'headline': 'Support for everyday routines', 'body': 'Designed to support a balanced daily routine.'},
  'b': {'headline': 'Guaranteed results in 7 days', 'body': 'The only solution you will ever need.'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'absolute_claim_present': 'absent', 'compliance_review_needed': 'absent'},
  'eb': {'absolute_claim_present': 'present', 'compliance_review_needed': 'present'}},
 {'id': 'message_alignment',
  'title': 'Aligned visual message versus text-image conflict',
  'axis': 'image_text_conflict',
  'format': {'width': 1080, 'height': 1080, 'name': 'square'},
  'a': {'image_message': 'calm-support', 'headline': 'Calm support for busy days'},
  'b': {'image_message': 'alarm-danger', 'headline': 'Calm support for busy days'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'image_text_conflict': 'absent'},
  'eb': {'image_text_conflict': 'present', 'review_due_to_ambiguity': 'present'}},
 {'id': 'mobile_safe_zone',
  'title': 'Story-safe composition versus edge-clipped content',
  'axis': 'mobile_safe_zone_respected',
  'format': {'width': 1080, 'height': 1920, 'name': 'story'},
  'a': {'safe_zone': True, 'layout': 'story-safe'},
  'b': {'safe_zone': False, 'layout': 'edge-clipped'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'mobile_safe_zone_respected': 'present'},
  'eb': {'mobile_safe_zone_respected': 'absent', 'content_clipping_risk': 'present'}},
 {'id': 'contrast',
  'title': 'High versus low text contrast',
  'axis': 'contrast_sufficient',
  'format': {'width': 600, 'height': 500, 'name': 'small-banner'},
  'a': {'contrast': 'high'},
  'b': {'contrast': 'low'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'contrast_sufficient': 'present'},
  'eb': {'contrast_sufficient': 'absent', 'readability_risk': 'present'}},
 {'id': 'audience_cue',
  'title': 'Specific audience cue versus generic message',
  'axis': 'audience_cue_present',
  'format': {'width': 1080, 'height': 1080, 'name': 'square'},
  'a': {'headline': 'Support for night-shift professionals',
        'body': 'A fictional routine designed for changing schedules.'},
  'b': {'headline': 'Support for everyone', 'body': 'A fictional product for all people.'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'audience_cue_present': 'present'},
  'eb': {'audience_cue_present': 'absent'}},
 {'id': 'claim_source',
  'title': 'Numerical claim with source versus unsupported number',
  'axis': 'numerical_claim_has_source',
  'format': {'width': 1200, 'height': 628, 'name': 'landscape'},
  'a': {'headline': '72% noticed the message', 'show_claim_source': True},
  'b': {'headline': '72% noticed the message', 'show_claim_source': False},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'numerical_claim_present': 'present', 'numerical_claim_has_source': 'present'},
  'eb': {'numerical_claim_present': 'present',
         'numerical_claim_has_source': 'absent',
         'compliance_review_needed': 'present'}},
 {'id': 'urgency_pressure',
  'title': 'Neutral CTA versus pressure language',
  'axis': 'urgency_pressure_present',
  'format': {'width': 600, 'height': 500, 'name': 'small-banner'},
  'a': {'cta': 'READ THE DETAILS', 'pressure_badge': ''},
  'b': {'cta': 'ACT NOW', 'pressure_badge': 'LAST CHANCE'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'urgency_pressure_present': 'absent'},
  'eb': {'urgency_pressure_present': 'present', 'compliance_review_needed': 'present'}},
 {'id': 'offer_clarity',
  'title': 'Specific benefit versus deliberately vague offer',
  'axis': 'offer_clarity',
  'format': {'width': 1080, 'height': 1080, 'name': 'square'},
  'a': {'headline': 'A simple reminder system for daily routines',
        'body': 'Clear fictional benefit: organize reminders in one place.'},
  'b': {'headline': 'Feel the difference', 'body': 'A new experience for a better tomorrow.'},
  'shared': {'brand_is_fictional': 'present',
             'market_effectiveness_not_evaluated': 'present',
             'real_respondent_evidence': 'absent'},
  'ea': {'offer_clarity': 'present', 'review_due_to_ambiguity': 'absent'},
  'eb': {'offer_clarity': 'absent', 'review_due_to_ambiguity': 'present'}}]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        result[key] = deepcopy(value)
    return result


def build_spec() -> dict[str, Any]:
    pairs = []
    for item in PAIR_SPECS:
        pairs.append(
            {
                "pair_id": item["id"],
                "title": item["title"],
                "contrast_axis": item["axis"],
                "format": deepcopy(item["format"]),
                "base": deepcopy(BASE),
                "shared_expectations": deepcopy(item["shared"]),
                "variants": [
                    {
                        "variant": "A",
                        "case_id": f"{item['id']}-a",
                        "label": "control",
                        "render_overrides": deepcopy(item["a"]),
                        "expected_observations": deepcopy(item["ea"]),
                    },
                    {
                        "variant": "B",
                        "case_id": f"{item['id']}-b",
                        "label": "contrast",
                        "render_overrides": deepcopy(item["b"]),
                        "expected_observations": deepcopy(item["eb"]),
                    },
                ],
            }
        )
    return {
        "pack_id": PACK_ID,
        "version": PACK_VERSION,
        "status": "candidate",
        "purpose": "Deterministic visual-observation benchmark preparation before receipt of client creatives.",
        "fictional_only": True,
        "case_count": 24,
        "pair_count": 12,
        "render_contract": {
            "output_format": "PNG",
            "color_mode": "RGB",
            "renderer_version": RENDERER_VERSION,
            "no_external_network": True,
            "no_external_fonts": True,
        },
        "evidence_boundary": {
            "supported": ["observable visual/text properties explicitly encoded in the case specification"],
            "unsupported": UNSUPPORTED,
        },
        "allowed_observation_statuses": sorted(STATUSES),
        "observable_catalog": OBSERVABLES,
        "pairs": pairs,
    }


def expand_cases(pack: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    pack = pack or build_spec()
    cases = []
    for pair in pack["pairs"]:
        for variant in pair["variants"]:
            cases.append(
                {
                    "case_id": variant["case_id"],
                    "pair_id": pair["pair_id"],
                    "variant": variant["variant"],
                    "variant_label": variant["label"],
                    "title": pair["title"],
                    "contrast_axis": pair["contrast_axis"],
                    "format": deepcopy(pair["format"]),
                    "render": _merge(pair["base"], variant["render_overrides"]),
                    "expected_observations": _merge(
                        pair["shared_expectations"], variant["expected_observations"]
                    ),
                    "evidence_boundary": deepcopy(pack["evidence_boundary"]),
                }
            )
    return sorted(cases, key=lambda case: case["case_id"])


def validate_spec(pack: dict[str, Any] | None = None) -> list[str]:
    pack = pack or build_spec()
    errors: list[str] = []
    pairs = pack.get("pairs", [])
    if pack.get("pack_id") != PACK_ID or pack.get("version") != PACK_VERSION:
        errors.append("unexpected pack identity or version")
    if pack.get("fictional_only") is not True:
        errors.append("pack must be fictional-only")
    if len(pairs) != 12 or pack.get("pair_count") != 12:
        errors.append("pack must contain 12 pairs")
    pair_ids: set[str] = set()
    case_ids: set[str] = set()
    catalog = set(OBSERVABLES)
    for pair in pairs:
        pair_id = pair.get("pair_id")
        if not pair_id or pair_id in pair_ids:
            errors.append(f"invalid or duplicate pair_id: {pair_id}")
            continue
        pair_ids.add(pair_id)
        variants = pair.get("variants", [])
        if len(variants) != 2 or {v.get("variant") for v in variants} != {"A", "B"}:
            errors.append(f"{pair_id} must contain A and B variants")
            continue
        axis = pair.get("contrast_axis")
        if axis not in catalog:
            errors.append(f"{pair_id} has unknown contrast axis: {axis}")
        axis_values = []
        for variant in variants:
            case_id = variant.get("case_id")
            if not case_id or case_id in case_ids:
                errors.append(f"invalid or duplicate case_id: {case_id}")
                continue
            case_ids.add(case_id)
            expected = _merge(
                pair.get("shared_expectations", {}),
                variant.get("expected_observations", {}),
            )
            axis_values.append(expected.get(axis))
            for observable, status in expected.items():
                if observable not in catalog:
                    errors.append(f"{case_id} uses unknown observable: {observable}")
                if status not in STATUSES:
                    errors.append(f"{case_id} has invalid status {status!r} for {observable}")
            render = _merge(pair.get("base", {}), variant.get("render_overrides", {}))
            if render.get("brand") != "NOVALEN":
                errors.append(f"{case_id} must use the fictional NOVALEN brand")
            visible = " ".join(
                str(render.get(key, ""))
                for key in ("brand", "headline", "body", "cta", "disclaimer", "claim_source")
            ).casefold()
            for real_brand in ("pfizer", "bayer", "novartis", "roche", "sanofi"):
                if real_brand in visible:
                    errors.append(f"{case_id} contains a real pharma brand")
        if len(axis_values) == 2 and axis_values[0] == axis_values[1]:
            errors.append(f"{pair_id} does not contrast its declared axis {axis}")
    if len(case_ids) != 24 or pack.get("case_count") != 24:
        errors.append("pack must contain 24 unique cases")
    return errors


def _require_valid() -> dict[str, Any]:
    pack = build_spec()
    errors = validate_spec(pack)
    if errors:
        raise ValueError("Invalid golden pack:\n- " + "\n- ".join(errors))
    return pack


def _color(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    if len(raw) != 6:
        raise ValueError(f"Expected #RRGGBB, got {value!r}")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=max(size, 8))


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
    line_height = max(int(size * 1.25), 10)
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


def _draw_symbol(
    draw: ImageDraw.ImageDraw,
    render: dict[str, Any],
    box: tuple[int, int, int, int],
    accent: tuple[int, int, int],
) -> None:
    x0, y0, x1, y1 = box
    if render.get("image_message") == "alarm-danger":
        draw.polygon([(x0 + (x1 - x0) // 2, y0), (x1, y1), (x0, y1)], fill=(220, 65, 70))
        center = x0 + (x1 - x0) // 2
        draw.rectangle((center - 5, y0 + 25, center + 5, y1 - 24), fill=(255, 255, 255))
        draw.ellipse((center - 6, y1 - 18, center + 6, y1 - 6), fill=(255, 255, 255))
        return
    draw.ellipse(box, fill=accent)
    draw.line(
        (
            x0 + (x1 - x0) // 4,
            y0 + (y1 - y0) // 2,
            x0 + (x1 - x0) // 2,
            y1 - (y1 - y0) // 3,
            x1 - (x1 - x0) // 4,
            y0 + (y1 - y0) // 3,
        ),
        fill=(255, 255, 255),
        width=max((x1 - x0) // 24, 2),
    )


def render_case(case: dict[str, Any], output_path: Path) -> dict[str, Any]:
    width, height = int(case["format"]["width"]), int(case["format"]["height"])
    render = case["render"]
    background = _color(render["background"])
    foreground = _color(render["foreground"])
    accent = _color(render["accent"])
    muted = _color(render["muted"])
    if render.get("contrast") == "low":
        foreground = tuple(min(channel + 8, 255) for channel in background)
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    margin = int(min(width, height) * (0.065 if render.get("safe_zone", True) else 0.005))
    x0, x1 = margin, width - margin
    if render.get("layout") == "edge-clipped":
        x0, x1 = -int(width * 0.05), width + int(width * 0.04)

    if render.get("show_brand", True):
        _draw_text(draw, render["brand"], (x0, margin, x1, margin + int(height * 0.08)),
                   fill=foreground, size=max(width // 32, 18), max_lines=1)
    symbol = int(min(width, height) * 0.22)
    sx = x0 + max((x1 - x0 - symbol) // 2, 0)
    sy = int(height * 0.14)
    _draw_symbol(draw, render, (sx, sy, sx + symbol, sy + symbol), accent)

    headline_top = sy + symbol + int(height * 0.04)
    headline_height = int(height * (0.18 if render.get("layout") != "overloaded" else 0.12))
    _draw_text(draw, render["headline"], (x0, headline_top, x1, headline_top + headline_height),
               fill=foreground, size=max(width // 20, 22), align="center", max_lines=3)
    body_top = headline_top + headline_height + int(height * 0.015)
    _draw_text(draw, render["body"], (x0 + int(width * 0.04), body_top,
               x1 - int(width * 0.04), int(height * 0.70)),
               fill=foreground, size=max(width // 38, 14), align="center", max_lines=5)

    if render.get("text_density") == "high":
        extra = [
            "Detailed feature one with supporting explanation.",
            "Detailed feature two with another explanation.",
            "Conditions, exceptions, context and additional notes.",
            "Multiple secondary messages compete for attention.",
        ]
        h = max(int(height * 0.035), 18)
        start = int(height * 0.52)
        for index, line in enumerate(extra):
            y = start + index * h
            draw.rectangle((x0, y, x1, y + h - 3), fill=muted)
            _draw_text(draw, line, (x0 + 4, y, x1 - 4, y + h - 3),
                       fill=foreground, size=max(width // 70, 10), max_lines=1)

    if render.get("pressure_badge"):
        badge_h = int(height * 0.07)
        draw.rectangle((x0, margin, x1, margin + badge_h), fill=(220, 65, 70))
        _draw_text(draw, render["pressure_badge"], (x0, margin, x1, margin + badge_h),
                   fill=(255, 255, 255), size=max(width // 30, 16), align="center", max_lines=1)

    if render.get("show_cta", True):
        top, bottom = int(height * 0.76), int(height * 0.86)
        left = x0 + int((x1 - x0) * 0.18)
        right = x1 - int((x1 - x0) * 0.18)
        if render.get("layout") == "edge-clipped":
            right = width + int(width * 0.08)
        draw.rounded_rectangle((left, top, right, bottom), radius=max(int(height * 0.02), 4), fill=accent)
        _draw_text(draw, render["cta"], (left, top, right, bottom), fill=(255, 255, 255),
                   size=max(width // 28, 16), align="center", max_lines=1)

    if render.get("show_claim_source", False):
        _draw_text(draw, render["claim_source"], (x0, int(height * 0.875), x1, int(height * 0.91)),
                   fill=foreground, size=max(width // 75, 9), align="center", max_lines=1)

    if render.get("show_disclaimer", True):
        tiny = render.get("disclaimer_scale") == "tiny"
        top = int(height * (0.965 if tiny else 0.915))
        _draw_text(draw, render["disclaimer"], (x0, top, x1, height - max(margin // 3, 1)),
                   fill=foreground, size=max(width // (140 if tiny else 70), 8),
                   align="center", max_lines=2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    info = PngImagePlugin.PngInfo()
    for key in ("case_id", "pair_id"):
        info.add_text(key, case[key])
    info.add_text("pack_id", PACK_ID)
    info.add_text("pack_version", PACK_VERSION)
    image.save(output_path, "PNG", optimize=False, compress_level=9, pnginfo=info)
    return {
        "case_id": case["case_id"],
        "pair_id": case["pair_id"],
        "variant": case["variant"],
        "filename": output_path.name,
        "width": width,
        "height": height,
        "sha256": _sha_file(output_path),
        "size_bytes": output_path.stat().st_size,
        "contrast_axis": case["contrast_axis"],
        "expected_observations": case["expected_observations"],
    }


def _contact_sheet(entries: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    columns, cell_w, cell_h = 4, 300, 270
    rows = (len(entries) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), (245, 247, 250))
    draw = ImageDraw.Draw(sheet)
    for index, entry in enumerate(entries):
        with Image.open(output_dir / entry["filename"]) as source:
            thumb = source.convert("RGB")
            thumb.thumbnail((280, 220), Image.Resampling.LANCZOS)
        col, row = index % columns, index // columns
        x = col * cell_w + (cell_w - thumb.width) // 2
        y = row * cell_h + 8
        sheet.paste(thumb, (x, y))
        _draw_text(draw, entry["case_id"],
                   (col * cell_w + 8, row * cell_h + 232, (col + 1) * cell_w - 8, row * cell_h + 260),
                   fill=(19, 34, 56), size=16, align="center", max_lines=1)
    path = output_dir / "contact_sheet.png"
    sheet.save(path, "PNG", optimize=False, compress_level=9)
    return {"filename": path.name, "sha256": _sha_file(path), "size_bytes": path.stat().st_size,
             "width": sheet.width, "height": sheet.height}


def generate(output_dir: Path, *, clean: bool = True) -> dict[str, Any]:
    pack = _require_valid()
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = expand_cases(pack)
    entries = [render_case(case, output_dir / f"{case['case_id']}.png") for case in cases]
    contact = _contact_sheet(entries, output_dir)
    spec = {"pack": pack, "cases": cases}
    manifest = {
        "pack_id": PACK_ID,
        "pack_version": PACK_VERSION,
        "renderer_version": RENDERER_VERSION,
        "spec_sha256": _sha_bytes(_json(spec).encode("utf-8")),
        "case_count": len(entries),
        "pair_count": len(pack["pairs"]),
        "fictional_only": True,
        "prediction_generated": False,
        "real_respondents_used": False,
        "unsupported_conclusions": UNSUPPORTED,
        "contact_sheet": contact,
        "cases": entries,
    }
    (output_dir / "pack_spec.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "generated_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def validate_generated(output_dir: Path) -> list[str]:
    errors = validate_spec()
    manifest_path, spec_path = output_dir / "generated_manifest.json", output_dir / "pack_spec.json"
    if not manifest_path.is_file() or not spec_path.is_file():
        return errors + ["generated_manifest.json or pack_spec.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"generated metadata is unreadable: {exc}"]
    if manifest.get("spec_sha256") != _sha_bytes(_json(spec).encode("utf-8")):
        errors.append("generated spec SHA-256 mismatch")
    if manifest.get("prediction_generated") is not False or manifest.get("real_respondents_used") is not False:
        errors.append("pack must not claim predictions or real respondents")
    entries = manifest.get("cases", [])
    if len(entries) != 24:
        errors.append("generated pack must contain 24 cases")
    for entry in entries:
        path = output_dir / str(entry.get("filename", ""))
        if not path.is_file():
            errors.append(f"missing generated asset: {path.name}")
            continue
        if _sha_file(path) != entry.get("sha256"):
            errors.append(f"SHA-256 mismatch for {path.name}")
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    errors.append(f"{path.name} is not PNG")
                if image.size != (entry.get("width"), entry.get("height")):
                    errors.append(f"dimension mismatch for {path.name}")
                if image.info.get("case_id") != entry.get("case_id"):
                    errors.append(f"embedded case_id mismatch for {path.name}")
        except OSError as exc:
            errors.append(f"could not open {path.name}: {exc}")
    contact = manifest.get("contact_sheet", {})
    contact_path = output_dir / str(contact.get("filename", ""))
    if not contact_path.is_file() or _sha_file(contact_path) != contact.get("sha256"):
        errors.append("contact sheet is missing or corrupted")
    return errors


def check_determinism() -> list[str]:
    with tempfile.TemporaryDirectory() as left_dir, tempfile.TemporaryDirectory() as right_dir:
        left, right = generate(Path(left_dir)), generate(Path(right_dir))
        left_hashes = {item["case_id"]: item["sha256"] for item in left["cases"]}
        right_hashes = {item["case_id"]: item["sha256"] for item in right["cases"]}
        errors = []
        if left_hashes != right_hashes:
            errors.append("case hashes differ between repeated generations")
        if left["contact_sheet"]["sha256"] != right["contact_sheet"]["sha256"]:
            errors.append("contact sheet hash differs between repeated generations")
        if left["spec_sha256"] != right["spec_sha256"]:
            errors.append("spec hash differs between repeated generations")
        return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic Creative Golden Pack.")
    parser.add_argument("command", choices=("generate", "validate", "check-determinism"), nargs="?", default="validate")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.command == "generate":
        manifest = generate(args.output)
        print(json.dumps({"status": "generated", "output": str(args.output),
                          "case_count": manifest["case_count"], "pair_count": manifest["pair_count"],
                          "spec_sha256": manifest["spec_sha256"]}, sort_keys=True))
        return 0
    errors = check_determinism() if args.command == "check-determinism" else (
        validate_generated(args.output) if args.output.exists() else validate_spec()
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "valid", "command": args.command, "case_count": 24, "pair_count": 12},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
