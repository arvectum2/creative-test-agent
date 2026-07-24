# PRE-PILOT-005 Acceptance Checklist

## Evidence prerequisites

- [x] A completed Data Quality run is required.
- [x] A completed Prediction Readiness run from the same Data Quality context is required.
- [x] A mismatched readiness run is rejected.
- [x] A selected quantitative study must belong to the same project.
- [x] No quantitative study is silently selected.
- [x] The immutable primary source file is rechecked by SHA-256 before generation.
- [x] A missing, corrupted or escaping source path blocks generation.

## Report semantics

- [x] The report contains a workflow verdict rather than a creative score.
- [x] `blocked`, `evidence_limited`, `review_required` and `controlled_review_ready` are derived deterministically.
- [x] Every capability retains its independent readiness status, mode and evidence strength.
- [x] Supported statements are derived only from ready or degraded capability evidence.
- [x] Blocking and warning issues are retained as visible limitations.
- [x] Remediation hints and missing inputs become visible next actions.
- [x] Synthetic, imported and human survey sources remain separately counted and labelled.

## Claim safety

- [x] No composite score is generated.
- [x] No CTR is fabricated.
- [x] No causal creative lift is estimated.
- [x] No market-effectiveness result is claimed.
- [x] No technical-readiness status is represented as model accuracy.
- [x] No synthetic response is represented as a real respondent.
- [x] No legal, medical or regulatory approval is asserted.
- [x] Claim-boundary flags are present in the evidence JSON and validated.

## Artifacts

- [x] Exactly one PPTX slide is generated.
- [x] The HTML contains an A4 landscape one-page print contract.
- [x] A complete evidence JSON accompanies the visual report.
- [x] A manifest records SHA-256 and byte size for PPTX, HTML and evidence JSON.
- [x] Artifact validation detects missing, changed or corrupted files.
- [x] Russian and English report locales are supported.
- [x] No remote service or external font file is required for rendering.

## Persistence and lifecycle

- [x] Report runs are persisted and numbered per Data Quality run.
- [x] The fingerprint includes complete selected survey results, not only study ID or response count.
- [x] An unchanged valid request is idempotent.
- [x] `force=true` creates an explicit new version.
- [x] Changed evidence creates a changed fingerprint.
- [x] Stored manifest and artifact hashes are verified before reuse.
- [x] Downloads are confined to the configured storage root.
- [x] Downloads are checksum-verified and sent with `no-store` and `nosniff` headers.
- [x] Generation writes an audit event with evidence IDs, verdict and hashes.

## API and operations

- [x] Generate, latest, detail and artifact-download endpoints are available.
- [x] An executable CLI can generate from persisted local run IDs.
- [x] A fixture-based self-test validates the complete artifact bundle.
- [x] Deterministic fixed-input generation is tested.
- [x] The mandatory CI workflow executes self-test, validation and determinism checks.
- [x] The full regression suite, migrations, security gates and existing end-to-end demo remain green.

## Explicit non-acceptance

The checklist does not accept or prove:

- final client visual branding;
- final brand-lift methodology;
- OCR/VLM accuracy;
- CTR-model accuracy;
- causal creative effectiveness;
- regulatory or legal compliance;
- production pilot value on real client materials.
