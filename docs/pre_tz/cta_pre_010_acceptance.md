# CTA-PRE-010 acceptance checklist

- A completed Data Quality run is required.
- The report is generated locally as a valid XLSX/OOXML ZIP package.
- Source-file SHA-256 integrity is rechecked and shown in the workbook.
- Source tables, columns, mappings, issues, clarifications, readiness, normalized rows, survey evidence and provenance have dedicated sheets.
- Warnings and blockers are visually distinguishable.
- The normalized-row sheet has a documented 500-row limit and explicit truncation notice.
- Prediction and survey limitations are stated in the workbook.
- Report inputs are fingerprinted and unchanged requests are idempotent.
- Stored XLSX bytes are protected by size and SHA-256 verification before download.
- API, audit, migration, documentation and executable tests are included.
