# PRE-PILOT-005 — Provisional One-Page Client Report

Status: implemented as a provisional, evidence-bound report format. Final client branding, methodology and wording remain open until the pilot team reviews real materials.

## Purpose

The report converts completed Data Quality and Prediction Readiness evidence into a compact client-discussion artifact without hiding limitations or presenting technical readiness as proven market effectiveness.

It is intentionally different from the analyst XLSX Data Review Report:

- the XLSX contains detailed operational evidence;
- the one-page report presents only the main workflow verdict, evidence coverage, capability statuses, limitations and next actions;
- every statement remains traceable through a machine-readable evidence file and provenance identifiers.

The verdict is a workflow state, not a creative score.

## Required evidence

Generation requires:

1. a completed `DataQualityRun`;
2. a completed `PredictionReadinessRun` belonging to that Data Quality run;
3. a valid immutable source file whose current SHA-256 matches the stored source record.

A quantitative study is optional and is included only when its ID is explicitly supplied. The generator does not silently select a study.

## Workflow verdicts

The report uses four bounded verdicts:

```text
blocked
 evidence_limited
review_required
controlled_review_ready
```

Decision logic:

- Data Quality `blocked` → `blocked`;
- Prediction Readiness `unavailable` → `evidence_limited`;
- Data Quality `review_required` or Prediction Readiness `degraded` → `review_required`;
- Data Quality `passed` and Prediction Readiness `ready` → `controlled_review_ready`.

`controlled_review_ready` means that the available evidence may be discussed under its stated limitations. It is not an accuracy certificate and is not a claim that the creative will succeed in market.

## Content of the page

The single page contains:

- client and project names;
- one bounded workflow verdict;
- evidence counts: files, rows, creative links, quality issues and selected survey responses;
- separate readiness status for each capability;
- capability operating mode and evidence strength;
- supported statements derived from ready or degraded capability messages;
- top blocking and warning limitations;
- next actions derived from issue remediation and missing inputs;
- short provenance footer with Data Quality run, Prediction Readiness run and immutable source SHA-256.

The design deliberately omits:

- a composite score;
- a universal creative ranking;
- an invented CTR;
- a causal creative-lift value;
- a hidden conversion of synthetic responses into human evidence;
- a legal or regulatory approval statement.

## Survey evidence labels

The evidence file distinguishes:

```text
none
synthetic_proxy
human_quantitative
imported_quantitative
mixed
```

It records separate counts for human, imported and synthetic responses. Synthetic responses remain explicitly labelled and are never described as observations from real people.

## Artifacts

Each run creates a versioned local bundle:

```text
client_one_page_ru.pptx or client_one_page_en.pptx
client_one_page_ru.html or client_one_page_en.html
client_one_page_ru_evidence.json or client_one_page_en_evidence.json
report_manifest.json
```

The PPTX contains exactly one slide. The HTML has an A4 landscape one-page print contract and may be exported to PDF through an approved local browser or office workflow. PRE-PILOT-005 does not bundle a headless PDF converter.

The evidence JSON contains the complete report inputs, limitations, prohibited statements and claim-boundary flags. The manifest records file size and SHA-256 for every artifact.

## Claim boundary

Every evidence file fixes these declarations:

```text
provisional_report = true
technical_readiness_is_not_model_accuracy = true
market_effectiveness_not_evaluated = true
prediction_generated = false
causal_creative_lift_estimated = false
composite_score_generated = false
synthetic_responses_must_remain_labelled = true
client_methodology_final = false
```

## Idempotency and versions

The input fingerprint includes:

- locale;
- client and project metadata;
- immutable source metadata and SHA-256;
- Data Quality evidence and issues;
- Prediction Readiness evidence and per-capability state;
- the complete selected quantitative-study result, including response sources and aggregates;
- provenance identifiers.

An unchanged request reuses the existing valid report. `force=true` creates a new numbered run. A changed study result, issue, capability state or source context creates a different fingerprint.

## API

```text
POST /data-quality-runs/{data_quality_run_id}/client-one-page-report
GET  /data-quality-runs/{data_quality_run_id}/client-one-page-report/latest
GET  /client-one-page-reports/{report_id}
GET  /client-one-page-reports/{report_id}/download?artifact=pptx|html|evidence|manifest
```

Example request:

```json
{
  "prediction_readiness_run_id": null,
  "quantitative_study_id": null,
  "locale": "ru",
  "force": false
}
```

When readiness ID is omitted, the latest completed readiness run belonging to the selected Data Quality run is used. A mismatched readiness or study ID is rejected.

Downloads are confined to the configured local storage root and rechecked against persisted SHA-256 before delivery.

## CLI and self-test

Executable harness check:

```bash
python scripts/client_one_page_report.py self-test \
  --output .ci/pre-pilot-005-one-page

python scripts/client_one_page_report.py validate \
  --input .ci/pre-pilot-005-one-page

python scripts/client_one_page_report.py check-determinism
```

Generate from persisted local evidence:

```bash
python scripts/client_one_page_report.py generate \
  --data-quality-run-id <id> \
  --prediction-readiness-run-id <id> \
  --quantitative-study-id <optional-id> \
  --locale ru
```

## Boundaries

PRE-PILOT-005 does not:

- repair source data, mappings or normalization;
- fix an outdated or internally inconsistent Data Quality run;
- run an OCR/VLM model;
- select a prediction model;
- establish client-level accuracy;
- replace expert, legal, medical or compliance review;
- finalize client branding or the pilot methodology.

The report inherits the evidence state of the referenced completed runs. Any later data correction requires new upstream runs and a newly fingerprinted report.
