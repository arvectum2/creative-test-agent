# CTA-PRE-008 — Prediction Readiness and Graceful Degradation

Status: implemented.

The readiness evaluator converts a completed `DataQualityRun` into capability-specific decisions. It never trains a model, invokes a prediction, fabricates CTR or claims accuracy.

## Capabilities

- `historical_ctr_prediction`
- `creative_lift_estimation`
- `synthetic_click_intent`
- `brand_lift_proxy`
- `compliance_risk_review`

Each capability is evaluated independently and receives:

- `ready`, `degraded`, `unavailable` or `not_applicable`;
- an explicit operating mode;
- evidence strength;
- required, missing and degraded inputs;
- allowed and prohibited operations;
- user-facing and internal explanations;
- source data-quality and clarification evidence.

## Graceful degradation

Examples:

- no paired clicks and impressions → historical CTR prediction is disabled, while descriptive review remains allowed;
- small or weakly comparable history → directional or calibration-only analysis, never a reliable creative-specific prediction;
- missing questionnaire evidence → synthetic click intent and brand-lift proxy remain configuration-only;
- partially linked creative inventory → compliance review covers linked assets only;
- missing or corrupted originals → prediction paths are unavailable.

The evaluator never silently substitutes one capability for another. A brand-lift proxy is not reported as observed market lift, directional association is not reported as causal creative lift, and a descriptive baseline is not presented as a prediction.

## Data thresholds

The PRE-TZ evaluator uses conservative workflow thresholds only:

- fewer than 20 normalized performance observations is treated as a small-sample degradation;
- at least two linked creatives and comparable media context are required before creative comparison can be considered;
- final modelling thresholds, algorithms, validation targets and accuracy promises remain frozen until real client data is studied.

## Clarification state

The fingerprint includes the latest terminal and unresolved client/analyst clarification state. Answers are evidence only. They do not mutate imported files, mapping decisions, normalized values or model availability.

## API

```text
POST /data-quality-runs/{data_quality_run_id}/prediction-readiness
GET  /data-quality-runs/{data_quality_run_id}/prediction-readiness/latest
GET  /prediction-readiness-runs/{run_id}
```

Repeated evaluation with unchanged evidence is idempotent. `force=true` creates an explicit additional run.
