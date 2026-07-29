# CTA-OZON-001 — Ozon Showcase Data Loader

Status: GitHub implementation complete; real-data acceptance remains local.

## Purpose

The loader assembles one local Ozon showcase project from two files that remain outside Git:

- a ZIP archive with creative images;
- an XLSX/XLSM workbook with control-group and test/exposed-group outcomes.

The loader is evidence-bound. It registers immutable source hashes and provenance, preserves campaign-to-asset ambiguity, and does not turn observed CG/TG differences into a causal or predictive claim.

## Command

```bash
python scripts/load_ozon_showcase.py \
  --assets /local/path/Ozon.zip \
  --outcomes /local/path/Test.xlsx
```

Optional arguments:

```text
--mapping config/ozon_showcase/mapping_v1.json
--report /local/path/to/report-or-directory
--dry-run
```

`--dry-run` validates the package and writes a JSON Data Quality/load report without creating database records.

## Versioned mapping

The canonical schema is `config/ozon_showcase/mapping_v1.json`:

- `schema_id = cta.ozon_showcase.mapping`;
- semantic schema version;
- client/project identity;
- workbook sheet/header/column aliases;
- canonical metric aliases;
- campaign identities and platform expectations;
- asset rules keyed by SHA-256 and filename;
- explicit linkage status and confidence;
- expected data limitations.

A filename match with a different SHA-256 is degraded. It can never preserve an `exact` status. Assets not covered by a deterministic rule use a heuristic link of at most `uncertain`; the loader never auto-promotes them to `exact`.

## Linkage statuses

- `exact` — one verified source asset can be linked to the campaign under the mapping contract;
- `probable` — evidence supports the link but does not meet the exact contract;
- `one_to_many` — campaign outcomes apply to a set of assets, not an isolated image;
- `uncertain` — heuristic or incomplete linkage requiring analyst confirmation;
- `missing` — an asset has no supplied outcome row, or no campaign can be linked;
- `rejected` — the proposed link conflicts with evidence and must not be used.

`rejected`, `missing`, `uncertain`, `probable`, and `one_to_many` remain visible in CreativeRecord metadata and the report. Only a single `exact` link permits an `individual_asset_attribution_allowed=true` campaign metadata flag; the outcome records themselves remain campaign-level and non-causal.

## Persistence model

CTA-OZON-001 reuses the existing local-first persistence layer and requires no migration:

- `Client` and `Project` identify the showcase;
- `ImportSession` and `ImportSourceFile` register the original ZIP/XLSX in immutable content-addressed storage;
- `NormalizationRun` provides the source fingerprint and idempotency key;
- `Campaign`, `Platform`, `CreativeRecord`, `Placement`, `PerformanceObservation`, and `NormalizedSourceRow` hold the normalized showcase records;
- `CreativeAsset` holds local image bytes in content-addressed storage.

CG/TG rates, sample sizes, descriptive percentage-point difference, workbook sheet/row provenance, and claim boundaries are stored in `PerformanceObservation.metadata_json`. `ctr` remains null; the loader does not repurpose brand-lift metrics as CTR.

## Idempotency

The source fingerprint is SHA-256 over:

- loader identity;
- mapping version and mapping SHA-256;
- ZIP SHA-256;
- XLSX SHA-256.

Re-running the same source pair with the same mapping reuses the existing completed normalization run and creates no duplicate import session, campaign, creative record, asset, or outcome record. A changed source file or mapping creates a new, explicit evidence version.

## Data Quality/load report

Each run writes a local JSON report, by default:

```text
data/generated/ozon_showcase/<source_fingerprint>.json
```

The report contains:

- source names and SHA-256 values;
- selected workbook sheet, header row, and layout;
- campaign/outcome/asset/linkage counts;
- warnings and explicit limitations;
- local database identifiers after persistence;
- fixed evidence boundaries.

The following limitations are expected from the current Ozon package and must remain visible:

- Relief: the outcome row is Ozon while the supplied creative is VK, so the link is rejected;
- Triderm: creative is present without an outcome row;
- Bepanthen, Rennie, and Theraflex: campaign-level outcomes map to multiple assets;
- Aerius: the Ozon link remains probable because a cross-platform variant is also present.

## Security and data handling

- Real ZIP/XLSX/image binaries are not stored in the repository.
- ZIP entries are checked for path traversal, count, size, supported image type, duplicate bytes, and valid image dimensions.
- Original ZIP and XLSX bytes are registered in immutable content-addressed storage.
- Extracted assets are stored under a local SHA-256 path.
- No cloud LLM, telemetry, or remote transfer is introduced.
- Generated reports are under `data/generated/`, which is ignored by Git.

## Synthetic regression

```bash
python -m pytest tests/test_ozon_showcase_loader.py -v
make ci-check
```

The synthetic package covers:

- wide CG/TG workbook parsing;
- exact, one-to-many, rejected, and missing links;
- hash-mismatch degradation;
- immutable source registration;
- repeat-run idempotency;
- campaign/outcome/asset persistence;
- explicit Data Quality limitations and claim boundaries.

## Non-goals

CTA-OZON-001 does not implement:

- campaign evidence UI (`CTA-OZON-002`);
- client report v2;
- OCR/VLM model selection;
- causal attribution;
- numeric uplift prediction;
- individual-asset conclusions for campaign-level or ambiguous outcomes.
