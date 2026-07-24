# CTA-PRE-009 — Configurable Quantitative Questionnaire

Status: implemented.

The module supports versioned quantitative instruments for banner testing without qualitative interviews or hidden generation of respondent evidence.

## Supported question types

- Likert scale
- bounded numeric rating
- yes/no
- single choice
- multiple choice

Free-text questions are intentionally rejected in this PRE-TZ scope. Every question has a stable code and a metric key such as `click_intent`, `brand_recall`, `brand_fit`, `message_clarity`, `relevance`, `trust`, `visual_appeal`, `comprehension` or `distinctiveness`.

## Questionnaire lifecycle

A questionnaire is created as `draft`, receives an automatic project/name version, and is published explicitly. Published versions are used by studies and are not edited in place; a changed instrument is created as a new version.

## Study lifecycle

```text
published questionnaire
→ draft study with project creatives and target response count
→ open study
→ human/imported/synthetic quantitative responses
→ close study
→ aggregate results
```

Only creative assets belonging to the study project may be selected.

## Privacy and provenance

The system stores a SHA-256 respondent hash scoped to the study, not the submitted respondent key. The questionnaire schema has no fields for names, email addresses, phone numbers or free-text biographies.

Every response is labelled as `human`, `imported` or `synthetic`. Synthetic responses require generation provenance. The built-in deterministic simulator stores generator version, seed, ordinal, declared creative effect and `not_a_real_person=true`.

## Deterministic simulation

The simulator exists for workflow and report testing. It does not represent real consumers. It uses the configured scale, an explicit seed, optional per-creative effect values from -1 to 1, and bounded random noise. It never changes historical CTR or claims observed market lift.

## Results

Results contain:

- total response count;
- source counts;
- metric coverage;
- per-creative response counts;
- means/min/max for numeric questions;
- distributions for boolean and choice questions;
- interpretation notes that distinguish proxy and synthetic evidence from observed campaign data.

## API

```text
POST /quantitative-questionnaires
POST /quantitative-questionnaires/{id}/publish
GET  /quantitative-questionnaires/{id}
GET  /quantitative-questionnaires?project_id=...

POST /quantitative-studies
GET  /quantitative-studies/{id}
POST /quantitative-studies/{id}/open
POST /quantitative-studies/{id}/close
POST /quantitative-studies/{id}/responses
POST /quantitative-studies/{id}/simulate
GET  /quantitative-studies/{id}/results
```

## Non-goals

- no qualitative interviews;
- no free-text thematic analysis;
- no claim that synthetic responses are real people;
- no automatic benchmark or pharmaceutical norm;
- no causal brand-lift claim;
- no replacement of observed CTR;
- no automatic client-facing report in this stage.
