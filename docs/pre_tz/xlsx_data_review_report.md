# CTA-PRE-010 — XLSX Data Review Report

Status: implemented.

The report is a local, versioned XLSX workbook for analyst review of a client delivery before any client-facing prediction report is prepared.

## Workbook contents

The generator creates ten worksheets:

1. `Summary` — project and source identifiers, data-quality and readiness statuses, issue counts and limitations.
2. `Source Files` — immutable original names, MIME types, sizes, SHA-256 values and current integrity verification.
3. `Tables` — detected sheets/tables, headers, confidence, dimensions, truncation and parser warnings.
4. `Columns and Mapping` — source headers, inferred types, samples and current mapping decisions.
5. `Data Quality Issues` — severity, category, evidence scope, affected counts and remediation guidance.
6. `Clarifications` — client/analyst questions, status, latest answer and linked issue codes.
7. `Prediction Readiness` — capability-specific statuses, allowed modes and prohibited claims.
8. `Normalized Rows` — up to 500 normalized rows with issues, custom fields and preserved source payload.
9. `Quantitative Survey` — selected study metrics and per-creative aggregates, when available.
10. `Provenance` — generator version, fingerprints, source hashes and interpretation limits.

## Review-oriented formatting

- title and header styles;
- frozen header rows;
- filters on tabular sheets;
- wrapped text and bounded column widths;
- visual highlighting for information, warnings and blockers;
- landscape page setup for wide review tables.

The workbook uses a deterministic local OOXML writer implemented with the Python standard library. It does not require cloud services or office automation software.

## Versioning and integrity

Each report stores:

- generator name and version;
- a fingerprint of the selected Data Quality, Prediction Readiness and quantitative-study evidence;
- file name, local path, byte size and SHA-256;
- sheet count and export summary.

Repeated generation with unchanged inputs returns the existing verified workbook. `force=true` creates a new report run. Download verifies existence and SHA-256 before returning the file.

## Row limits

The normalized-row sheet exports up to 500 rows. When more rows exist, the workbook contains an explicit truncation notice. All aggregate counts and source provenance remain available.

## API

```text
POST /data-quality-runs/{data_quality_run_id}/data-review-report
GET  /data-quality-runs/{data_quality_run_id}/data-review-report/latest
GET  /data-review-reports/{report_id}
GET  /data-review-reports/{report_id}/download
```

## Explicit limitations

The workbook does not:

- invent historical CTR or model accuracy;
- present synthetic respondents as real people;
- treat a brand-lift proxy as observed market lift;
- claim causal creative lift without a study design;
- replace the later one-page client report.
