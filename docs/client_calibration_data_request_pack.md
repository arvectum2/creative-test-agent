# CTA-DATA-002 — Client Calibration Data Request Pack

Status: implemented as a deterministic, local-first client transfer package.

## Purpose

The package standardizes the next calibration-data request after `CTA-DEMO-001`. It asks for one evidence row per observed metric and preserves the documented relationship:

```text
project → campaign → asset → placement → observation window → metric
```

The package does not infer missing links, convert rounded percentages into invented counts, train a model or make a causal uplift claim.

## Generate the client pack

```bash
python scripts/client_calibration_data_request_pack.py generate \
  --output data/generated/client_calibration_data_request/v1
```

Generated output:

```text
calibration_data_request_template.xlsx
calibration_data_request_template.csv
calibration_data_request.schema.json
data_dictionary.csv
client_instruction_ru.md
examples/
  valid_calibration_data.csv
  valid_calibration_data.json
  valid_calibration_data.xlsx
  invalid_calibration_data.csv
  invalid_calibration_data.json
  invalid_calibration_data.xlsx
package_manifest.json
```

The generated directory is intentionally ignored by Git. Real client data must remain in the local closed loop.

## XLSX structure

The XLSX template contains:

- `Data` — canonical 37-column intake table with 200 editable rows;
- `Dictionary` — field requirements, types, allowed values and examples;
- `Instructions` — client-facing completion rules;
- `Lists` — controlled values used by dropdown validation.

Required columns are highlighted separately from conditional columns. The workbook freezes the header row, applies date/number formats and provides controlled-value dropdowns.

The workbook is generated locally with `openpyxl`. The resulting ZIP container is normalized before hashing, so repeated generation is byte-for-byte deterministic and uses no cloud spreadsheet service.

## CSV and JSON

The CSV header exactly matches the `Data` sheet.

JSON uses a Draft 2020-12 schema:

```json
{
  "schema_version": "1.0.0",
  "records": [
    {
      "...": "one metric observation"
    }
  ]
}
```

Unknown JSON fields are rejected. Required fields, enums, dates, identifier patterns, SHA-256 values, numeric ranges and evidence-boundary constants are formally validated.

## Linkage policy

`linkage_status=exact` requires:

- `campaign_id`;
- `asset_id`;
- `placement_id`;
- `platform`;
- `placement_name`.

When a link is unavailable, the row must use `linkage_status=missing`, list blank identifiers in `linkage_missing_fields` and explain the limitation in `linkage_notes`.

`probable`, `one_to_many`, `uncertain` and `rejected` also require notes and produce a visible analyst-review warning. The validator never promotes those states to `exact`.

## Counts before rounded rates

For proportion metrics, the preferred evidence is:

- control sample count;
- control positive count;
- test sample count;
- test positive count.

Optional rates must be decimals from 0 to 1 and must agree with counts within `0.005`.

Rate-only evidence is allowed only when:

```text
measurement_basis = rates_only
counts_unavailable_reason is populated
```

It remains valid with a `COUNTS_PREFERRED` warning. `--strict` turns warnings into a non-zero exit status.

## Evidence boundary

Every record requires:

```text
causal_interpretation_allowed = false
```

Observed CG/TG differences are descriptive evidence. The pack does not prove causal brand lift, attribute a campaign-set result to one creative or predict numeric uplift.

## Validation

Validate one submitted file:

```bash
python scripts/client_calibration_data_request_pack.py validate \
  --input /local/path/client_data.xlsx
```

Supported formats:

- `.xlsx`;
- `.csv`;
- `.json`.

Strict mode:

```bash
python scripts/client_calibration_data_request_pack.py validate \
  --input /local/path/client_data.xlsx \
  --strict
```

Validate a generated pack:

```bash
python scripts/client_calibration_data_request_pack.py validate-pack \
  --input data/generated/client_calibration_data_request/v1
```

Run complete acceptance:

```bash
python scripts/client_calibration_data_request_pack.py self-test \
  --output .ci/cta-data-002
```

The self-test verifies:

- pack integrity and manifest hashes;
- deterministic generation;
- exact CSV/XLSX headers;
- all required workbook sheets;
- valid CSV/JSON/XLSX examples pass without warnings;
- invalid examples fail with expected linkage, counts, date, SHA-256 and causal-boundary errors;
- a documented rates-only exception produces `COUNTS_PREFERRED`.

## Main validation codes

| Code | Meaning |
|---|---|
| `LINKAGE_ID_REQUIRED` | Exact linkage is missing a campaign, asset, placement, platform or placement name |
| `UNDECLARED_MISSING_LINKAGE` | Blank linkage field was not explicitly listed as missing |
| `LINKAGE_REVIEW_REQUIRED` | Linkage is explicit but not exact |
| `ABSOLUTE_COUNT_REQUIRED` | Required sample count is absent or invalid |
| `POSITIVE_COUNT_REQUIRED` | Proportion numerator is absent |
| `RATE_COUNT_MISMATCH` | Supplied rate does not agree with absolute counts |
| `RATES_ONLY_REASON_REQUIRED` | Rate-only evidence has no reason |
| `COUNTS_PREFERRED` | Rate-only evidence is accepted as degraded evidence |
| `OBSERVATION_DATE_ORDER` | Observation end precedes start |
| `INVALID_SHA256` | Provenance hash is malformed |
| `CAUSAL_INTERPRETATION_FORBIDDEN` | Causal flag is not false |

## Non-goals

CTA-DATA-002 does not:

- receive or commit real client materials;
- replace the as-is pilot intake package;
- infer campaign-to-asset links;
- merge different funnel stages;
- perform model training or automatic threshold tuning;
- create validated accuracy or causal-effect claims.
