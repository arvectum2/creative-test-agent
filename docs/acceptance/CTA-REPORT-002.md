# CTA-REPORT-002 — Acceptance

Status: `DONE`  
Implementation mode: `HYBRID`  
Completed: 2026-07-30

## Delivered

- evidence-bound composition with five isolated layers;
- deterministic evidence registry and finding-level references;
- explicit `individual_asset` and `campaign_set` scopes;
- factual CG/TG rows that remain campaign-level;
- expert assessments with explicit `not_reviewed` fallback;
- HTML, one-page PPTX, full PPTX, DOCX, evidence JSON and XLSX appendix;
- SHA-256 manifest and bundle validation;
- project-scoped API, secure downloads and CLI harness;
- synthetic regression tests and CI acceptance bundle.

## Acceptance checks

- [x] Every agent finding has at least one source-run reference and one asset reference.
- [x] Referenced visual observations are retained as separately labelled references.
- [x] Every reference emitted by a finding resolves in the evidence registry.
- [x] Agent findings are `individual_asset`; CG/TG outcomes are `campaign_set`.
- [x] `individual_asset_attribution_allowed=false` for every outcome.
- [x] `causal_interpretation_allowed=false` and no numeric prediction is generated.
- [x] Null CG/TG values remain null in JSON and blank/missing in visual exports.
- [x] Missing expert verdicts remain `not_reviewed`; the generator never fabricates expert review.
- [x] All six required formats are generated and listed in the integrity manifest.
- [x] Fixed-input artifact hashes are deterministic, including Office core-property timestamps.
- [x] CLI runs directly from the repository root without a manual `PYTHONPATH` override.
- [x] Synthetic PPTX and DOCX were rendered locally with LibreOffice on 2026-07-30 and inspected page by page.

## Visual acceptance evidence

Commands used:

```bash
python scripts/client_report_v2.py self-test --output .ci/cta-report-002
python scripts/client_report_v2.py validate --input .ci/cta-report-002
python scripts/client_report_v2.py check-determinism
```

The acceptance bundle rendered as:

- one-page PPTX: 1 slide;
- full PPTX: 5 slides for the two-campaign synthetic fixture;
- DOCX: 2 landscape pages;
- no clipped headings, overlapping panels or broken tables were observed;
- missing TG values remained visibly missing rather than inferred.

## Explicit non-acceptance

This task does not prove model accuracy, forecast campaign performance, estimate causal brand lift, or allow campaign outcomes to be attributed to an individual asset. Real client materials are not committed to the repository.
