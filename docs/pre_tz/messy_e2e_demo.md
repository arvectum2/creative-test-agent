# CTA-PRE-012 — Messy End-to-End Demo

Status: implemented.

This executable demonstration proves that the PRE-TZ pipeline can accept an inconsistent client-style delivery without imposing a mandatory source template and can still produce a traceable local review workbook.

## Command

```bash
python scripts/run_pre_tz_messy_demo.py \
  --workspace data/demo/cta_pre_012
```

The workspace is deleted and rebuilt by default. Use `--keep-existing` only for controlled diagnosis. The reset guard refuses root, home and repository-root paths.

## Deliberately messy source

The bundled `examples/pre_tz/messy_campaign_export.csv` contains:

- preamble and blank rows before the actual header;
- Russian headers and a semicolon delimiter;
- mixed date formats and an impossible date;
- decimal commas and percentages;
- numbers containing spaces, missing metrics and text placeholders;
- a supplied CTR inconsistent with clicks and impressions;
- a duplicated row;
- zero and negative performance values;
- one creative reference without a corresponding asset;
- two unmapped custom columns.

It is synthetic demonstration data and is not client data.

## Pipeline exercised

The command performs one complete isolated run:

1. creates a synthetic client, project and two local creative records;
2. stores the CSV through immutable SHA-256-addressed import storage;
3. seals and verifies the import session;
4. inspects the file and discovers its table/header structure;
5. generates mapping suggestions and records ten explicit analyst confirmations;
6. normalizes campaign, creative, platform, placement, audience and performance fields while preserving unknown columns;
7. executes the deterministic data-quality engine;
8. generates evidence-backed client and analyst clarification batches;
9. evaluates capability-specific prediction readiness with graceful degradation;
10. runs a configurable quantitative instrument using deterministic responses labelled `synthetic` and `not_real_people`;
11. produces and verifies the local XLSX data-review report;
12. writes `demo_manifest.json` with identifiers, statuses, warnings, capability decisions and artifact hashes.

## Outputs

The workspace contains:

```text
creative_test_agent_demo.db
storage/imports/originals/...
storage/data_review_reports/*.xlsx
demo_manifest.json
```

The manifest is the primary machine-readable proof. It records the report path and SHA-256, import integrity, mapping coverage, normalization counts, quality issue codes, clarification counts, readiness status and synthetic-response provenance.

## Safety boundary

The demo:

- forces local-only storage and a local SQLite database;
- disables cloud LLM use and authentication side effects;
- does not train or invoke a prediction model;
- does not derive or fabricate CTR;
- does not represent synthetic answers as real respondents;
- does not claim causal lift, market accuracy or pharma benchmark validity.

The synthetic response effect parameters exist only to make deterministic aggregation testable. They are not model outputs and must not be interpreted as expected market performance.

## CI

Mandatory CI runs the complete demo after the regression suite in a disposable `.ci/cta-pre-012-demo` workspace. The CI step fails if any pipeline stage, integrity check, workbook generation or manifest assertion fails.
