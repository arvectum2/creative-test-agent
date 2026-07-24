# CTA-PRE-003 — tabular source inspection

Status: implemented.

## Purpose

The tabular inspector reads immutable source files created by CTA-PRE-002 and describes their structure without requiring a client template and without converting them into campaign-domain entities.

Supported formats:

- XLSX;
- CSV;
- TSV.

The original file remains the source of truth. Inspection output is a versioned, derived representation with complete provenance back to the source file, sheet and row number.

## Processing model

Each run creates a `source_inspection` record containing the parser name and version, status, detected format, encoding or delimiter, totals, warnings and any non-fatal or fatal error.

A successful inspection creates:

- `source_table` — one record per workbook sheet or delimited table;
- `source_column` — detected headers, stable generated names, inferred types and sample values;
- `source_row` — materialized source values, cell types, original row number and row role.

Rows are classified as `preamble`, `header` or `data`. If no sufficiently confident header is found, generated names such as `column_1` are used and the condition is reported as a warning.

## Detection behaviour

The inspector:

- discovers XLSX worksheets;
- detects CSV encoding and delimiter;
- scans the first configured rows for a probable header;
- preserves formula text rather than evaluating formulas;
- identifies duplicate headers and disambiguates them as `name`, `name__2`, and so on;
- identifies empty columns;
- infers simple column types: empty, boolean, integer, number, date, datetime, time, formula, text or mixed;
- records previews and paginated raw rows;
- stores corrupt or unsupported-file outcomes as failed inspection records instead of deleting the original source.

Header detection is intentionally advisory. The confidence value and warnings are inputs to the mapping stage; they are not treated as confirmed client semantics.

## Limits

The following settings bound resource use:

```text
CTA_TABULAR_INSPECTION_MAX_ROWS_PER_TABLE=100000
CTA_TABULAR_INSPECTION_PREVIEW_ROWS=20
CTA_TABULAR_INSPECTION_HEADER_SCAN_ROWS=25
CTA_TABULAR_INSPECTION_MAX_COLUMNS=512
CTA_TABULAR_INSPECTION_MAX_CELL_CHARS=10000
CTA_TABULAR_INSPECTION_BLANK_ROW_STOP=200
```

When a row, column or cell limit is reached, the inspection remains successful but is marked with warnings and the affected table has `truncated=true`. The immutable original still contains the complete client file.

## Idempotency and versions

A repeated request returns the latest result from the current parser version. `force=true` creates a new numbered inspection. This permits deterministic reuse while retaining an explicit path for parser upgrades or operator-requested reprocessing.

## API

```text
POST /import-sessions/{session_id}/files/{file_id}/inspect
GET  /import-sessions/{session_id}/files/{file_id}/inspection
GET  /import-sessions/{session_id}/files/{file_id}/tables
GET  /import-sessions/{session_id}/files/{file_id}/tables/{table_id}
GET  /import-sessions/{session_id}/files/{file_id}/tables/{table_id}/rows
```

`preview_limit`, `offset` and `limit` are bounded query parameters. Internal storage paths are never returned.

## Explicit non-goals

CTA-PRE-003 does not:

- map client columns to campaign-domain fields;
- normalize values;
- decide whether a metric means clicks, views or impressions;
- link creatives to campaign rows;
- calculate CTR;
- assess model readiness;
- implement a client brand-lift methodology.

Those actions require later mapping, normalization and data-quality stages.
