# CTA-OZON-001 acceptance

## GitHub scope

- [x] Versioned Ozon showcase mapping schema.
- [x] Local CLI loader for ZIP + XLSX.
- [x] Immutable source SHA-256 and provenance registration.
- [x] Client, project, campaigns, assets, creative records, placements, and observed outcomes.
- [x] Explicit `exact`, `probable`, `one_to_many`, `uncertain`, `missing`, and `rejected` linkage contract.
- [x] Hash mismatch degrades linkage; heuristic linkage is never exact.
- [x] Repeatable source fingerprint and idempotent database execution.
- [x] Synthetic package fixture and regression tests.
- [x] JSON Data Quality/load report with claim boundaries.
- [x] Local operating and Mac mini/OpenCode acceptance documentation.

## Local acceptance still required

- [ ] Real ZIP and XLSX load without entering Git history.
- [ ] Source counts and hashes recorded.
- [ ] Repeat execution returns the same persisted IDs and no duplicates.
- [ ] Relief platform mismatch remains rejected and visible.
- [ ] Triderm remains an asset without outcomes.
- [ ] Multi-asset campaigns remain campaign-level evidence.
- [ ] Non-exact linkage is not promoted to exact.
- [ ] Local JSON report is generated and hashed.
- [ ] Full synthetic/CI-equivalent checks pass on Mac mini.
- [ ] Sanitized smoke-test summary is added to issue #45.

Until the local section is complete, the canonical task status is `BLOCKED_LOCAL`, not `DONE`.
