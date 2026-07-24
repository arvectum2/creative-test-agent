# CTA-PRE-007 acceptance checklist

- Clarifications require a completed, persisted Data Quality Engine run.
- Client and analyst questions are generated separately.
- Generation requests accept a maximum of three to five questions.
- Fewer questions are returned when fewer material gaps exist; filler questions are never invented.
- Questions are ranked deterministically by downstream impact.
- Every question records source issue IDs, codes, affected counts, source identifiers and impact.
- Questions expose a separate explanation of why the answer is required.
- Choice answers are validated against the options stored with the question.
- Responses are append-only, numbered and auditable.
- `answered`, `not_available` and `not_applicable` suppress the same question in later batches.
- `deferred` remains unresolved and does not silently close the run.
- A run resolves only when no open or deferred questions remain.
- Repeated generation is fingerprinted and idempotent unless `force=true` is used.
- Recorded answers never mutate source files, mappings, normalized data, duplicates, creative links or CTR automatically.
- API, migration, lifecycle, progression, no-filler and response-history behavior are covered by executable tests.
- Runtime and Alembic model registries remain aligned.
