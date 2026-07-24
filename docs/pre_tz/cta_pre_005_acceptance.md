# CTA-PRE-005 acceptance checklist

- Confirmed mappings are snapshotted and fingerprinted.
- Repeated normalization with the same snapshot is idempotent.
- Forced and mapping-changed runs are explicit and separately reproducible.
- Campaign, creative, platform, audience, placement and performance records are nullable-first.
- Existing creative assets are linked rather than copied.
- Every selected mapped value has field-level source provenance.
- Entire source rows and unmapped columns are preserved.
- Parse failures are non-blocking and produce partial rows.
- No CTR is derived or predicted.
- Runtime and Alembic model registries remain aligned.
- API, service and migration behavior are covered by executable tests.
