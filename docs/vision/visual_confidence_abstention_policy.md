# Visual Confidence and Abstention Policy

Task: `CTA-020 — Visual Confidence and Abstention Policy`  
Canonical roadmap mapping: `CTA-VIS-005 — Visual Confidence and Abstention Policy`

## Purpose

The policy turns visual confidence into an operational release gate. A small confidence number is not merely displayed next to a conclusion: unsupported or unreliable visual conclusions are abstained, limited conclusions are routed to manual review, and only sufficiently supported conclusions may be treated as client-releasable.

The policy is local-first, deterministic, evidence-bound and applied after `CTA-VIS-004` traceability. It does not change legacy diagnostic scores solely because extraction is missing or weak. It does not claim validated model accuracy, predicted CTR, brand lift, uplift or real respondent behaviour.

## Four confidence layers

The implementation keeps four different confidence concepts separate:

1. **Extraction confidence** — confidence reported for the OCR/VLM extraction operation.
2. **Observation confidence** — confidence of each canonical observation referenced by a finding.
3. **Finding confidence** — diagnostic confidence after traceability; it cannot exceed the confidence of accepted observation references.
4. **Decision confidence** — the minimum confidence governing whether the proposed recommendation can be released, must be reviewed, or must be abstained.

A higher-level confidence never repairs missing lower-level evidence. A model-written conclusion without a valid relevant visual reference remains unsupported regardless of wording.

## Versioned provisional thresholds

Policy ID: `visual-confidence-abstention-v1`  
Schema: `visual_confidence_abstention_policy` version `1.0`

| Gate | Threshold | Operational meaning |
|---|---:|---|
| Hard abstention floor | `< 0.45` | visual conclusion is not accepted |
| Client release gate | `>= 0.65` | visual conclusion may be released when traceability is complete |
| High-confidence band | `>= 0.75` | reporting band only; not a production-accuracy claim |

Values from `0.45` to below `0.65` require manual review. These are provisional operational safeguards for the pilot, not empirically validated accuracy thresholds. Controlled-pilot calibration may replace them only through a new policy version.

## Finding-level states

Every visual or mixed finding receives one state:

- `accepted` — valid relevant references exist, traceability is complete, and finding confidence is at least `0.65`;
- `review_required` — references exist, but traceability is partial, the evidence envelope is limited, or confidence is between `0.45` and `0.65`;
- `abstained` — references are missing/invalid, traceability is unsupported or unassessed, or confidence is below `0.45`;
- `not_applicable` — the conclusion is non-visual or the asset does not require visual evidence.

The policy adds:

- `visual_confidence_score`;
- `visual_confidence_band`;
- `visual_abstention_status`;
- `visual_abstention_reasons`;
- `visual_assessment_allowed`;
- `visual_client_release_allowed`.

The original criterion score is preserved. Missing extraction changes confidence and release state, not the legacy score by itself.

## Assessed absence

`null` remains unassessed and cannot support a conclusion. An explicit observation such as `presence: "absent"` is assessed evidence, receives a traceable reference, and may be accepted when its confidence clears the policy gates. It may support an absence claim only; it is never converted into a presence claim.

## Decision-level release state

The model or deterministic pipeline still produces the auditable `final_recommendation` (`show_to_client`, `revise`, or `reject`). The policy preserves it as the proposed recommendation and derives a separate operational result:

| Release state | Effective recommendation |
|---|---|
| `released` | proposed recommendation |
| `manual_review_required` | `manual_review` |
| `abstained` | `abstain` |
| `not_applicable` | proposed recommendation |

Critical visual findings are rubric scoring, brand safety and brandbook compliance. An abstained critical finding blocks release. A review-required critical finding routes the decision to manual review. Unresolved visual summary or audience findings are advisory but also prevent automatic client release.

## Integrity-checked manifest

Each run persists `visual_confidence_policy` in the existing structured findings JSON. No database migration is required.

The manifest contains:

- policy ID, schema version and thresholds;
- calibration disclaimer;
- creative asset ID;
- exact `visual_evidence_fingerprint`;
- exact `visual_trace_fingerprint`;
- envelope confidence decision;
- finding-level confidence and abstention records;
- accepted/reviewed/abstained counts;
- proposed and effective recommendations;
- deterministic SHA-256 fingerprint.

`validate_visual_confidence_policy_manifest()` recomputes the fingerprint and fails on modified policy content.

## API and persistence

`TestRunResponse` exposes:

- `effective_recommendation`;
- `visual_confidence_policy`;
- `visual_decision_status`;
- `visual_abstention_count`;
- `visual_review_required_count`;
- finding-level confidence and abstention fields.

The legacy `final_recommendation`, `overall_score` and criterion scores remain available for audit and backward compatibility. Consumers that make client-release decisions should use `effective_recommendation` and `visual_decision_status`.

## Pipeline order

The canonical persisted path is:

1. build one canonical `VisualEvidenceEnvelope`;
2. run all analytical stages;
3. validate finding-level visual references;
4. apply confidence and abstention policy;
5. persist trace and policy manifests together;
6. expose both through the API and audit event.

## Regression requirements

The automated tests cover:

- complete high-confidence evidence;
- limited evidence requiring review;
- missing observations causing abstention without score penalty;
- supported finding below the hard floor;
- assessed absence;
- non-visual assets;
- manifest tamper detection;
- database persistence and API round-trip.

## Limitations

The thresholds are not a substitute for target-hardware benchmarking or controlled-pilot calibration. They do not establish sensitivity, specificity, human agreement, campaign effectiveness, causal lift or market outcome prediction. A new calibrated policy must use a new immutable policy ID and schema/versioned documentation.
