# CTA-PRE-006 acceptance checklist

- Immutable originals are re-verified by existence and SHA-256.
- File, table, row, column, mapping, normalization and creative-linking coverage is reported.
- All eight roadmap data-quality categories are persisted.
- Issues use `info`, `warning` and `blocking` severities with affected counts and evidence.
- Overall status is derived from issue severity without a synthetic numeric score.
- Missing optional fields remain non-blocking and source payloads are never modified.
- Exact duplicate files, source rows and normalized performance observations are detected.
- Supplied metrics are checked for signs, zero-impression clicks and CTR consistency.
- CTR is not replaced, calculated into the domain layer or predicted.
- Preliminary readiness indicators are clearly separated from CTA-PRE-008 decisions.
- Runs are versioned, fingerprinted and idempotent unless `force=true` is used.
- API, audit, migration, service and idempotency behavior are covered by executable tests.
- Runtime and Alembic model registries remain aligned.
