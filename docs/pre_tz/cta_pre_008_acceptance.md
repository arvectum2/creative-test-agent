# CTA-PRE-008 acceptance checklist

- A completed Data Quality run is required.
- Historical CTR, creative lift, synthetic click intent, brand-lift proxy and compliance review are evaluated separately.
- Every capability stores status, mode, evidence, reasons, missing/degraded inputs and allowed/prohibited operations.
- Graceful degradation never fabricates CTR, respondent answers, control groups or causal lift.
- Small or incomplete history falls back only to descriptive/directional modes.
- Questionnaire-based capabilities remain unavailable or configuration-only until questionnaire evidence exists.
- Clarification state is fingerprinted but does not mutate data or enable a capability automatically.
- Runs are versioned, fingerprinted and idempotent unless forced.
- API, audit, migration and executable tests are included.
