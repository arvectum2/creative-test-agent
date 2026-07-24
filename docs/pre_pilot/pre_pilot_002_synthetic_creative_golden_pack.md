# PRE-PILOT-002 — Synthetic Creative Golden Pack

Status: implemented as a candidate pre-pilot evidence pack.

## Purpose

The pack provides a reproducible set of fictional creatives for checking whether the local visual-analysis contour can identify concrete observable properties before any client intellectual property is received.

It is not a benchmark of market effectiveness. It does not contain real campaign outcomes, respondents, CTR, causal lift or pharmaceutical norms.

## Composition

The pack contains 12 controlled A/B pairs and 24 generated PNG creatives. Every pair changes one declared contrast axis while retaining a shared fictional brand and common evidence boundaries.

The contrast axes are:

1. CTA present versus absent;
2. readable versus unreadable disclaimer;
3. clear hierarchy versus overloaded layout;
4. brand visible versus absent;
5. measured wording versus an absolute guaranteed claim;
6. aligned image and text versus image-text conflict;
7. respected mobile safe zone versus clipped edge content;
8. sufficient versus insufficient text contrast;
9. specific audience cue versus generic message;
10. numerical claim with source versus unsupported number;
11. neutral CTA versus pressure language;
12. specific offer versus deliberately vague wording.

Formats include square, landscape, story and small-banner canvases.

## Golden labels

Labels describe only properties that are deliberately encoded in the synthetic specification. Examples include:

- `cta_present`;
- `disclaimer_readable`;
- `visual_hierarchy_clear`;
- `brand_present`;
- `absolute_claim_present`;
- `image_text_conflict`;
- `mobile_safe_zone_respected`;
- `contrast_sufficient`;
- `numerical_claim_has_source`;
- `urgency_pressure_present`;
- `review_due_to_ambiguity`.

Allowed statuses are `present`, `absent`, `review_required` and `uncertain`.

The pack deliberately does not contain expected overall scores, expected CTR, creative-lift values or claims about likely respondent behaviour.

## Fictional-content boundary

All creatives use the invented brand `NOVALEN`. The generator rejects known real pharmaceutical brand names in visible pack text. Every case carries the following shared evidence labels:

- `brand_is_fictional = present`;
- `market_effectiveness_not_evaluated = present`;
- `real_respondent_evidence = absent`.

The renderer uses no network access and no external font files. It relies on Pillow's built-in default font and geometric shapes.

## Generation

```bash
python scripts/synthetic_creative_golden_pack.py generate \
  --output data/generated/synthetic_creatives/v1
```

The command produces:

```text
24 case PNG files
contact_sheet.png
pack_spec.json
generated_manifest.json
```

Each PNG embeds `pack_id`, `pack_version`, `pair_id` and `case_id`. The generated manifest records dimensions, byte size and SHA-256 for every asset and for the contact sheet.

Generated binary assets are intentionally not committed. The reviewed specification and deterministic renderer are the source of truth.

## Validation

Validate the specification or an existing generated pack:

```bash
python scripts/synthetic_creative_golden_pack.py validate
python scripts/synthetic_creative_golden_pack.py validate \
  --output data/generated/synthetic_creatives/v1
```

Verify byte-level repeatability inside the same pinned runtime:

```bash
python scripts/synthetic_creative_golden_pack.py check-determinism
```

Validation checks:

- exactly 12 unique pairs and 24 unique cases;
- one A and one B variant per pair;
- a different golden status on the declared contrast axis;
- known observable names and allowed statuses only;
- fictional brand boundary;
- no prediction or respondent claim;
- valid PNG dimensions and embedded identifiers;
- SHA-256 integrity of all generated files;
- deterministic repeated generation in the same runtime.

## Intended next use

PRE-PILOT-003 may run local OCR/VLM candidates against this pack and measure observable-level precision, recall, abstention, repeatability, latency and resource use.

The pack itself does not select a model and does not establish client-level accuracy. Real creatives, expert review and a later locked holdout remain necessary.
