# PRE-PILOT-004 — Pilot Intake and Acceptance Package

Status: implemented transfer and acceptance-control package; final client fields and thresholds remain open until real materials arrive.

## Purpose

This stage prepares a controlled handoff for the first real pilot without forcing the agency to redesign its files before transfer.

The client may send materials as they exist. The package records what was received, preserves immutable originals, captures only known relationships and makes pilot acceptance measurable. It does not define a mandatory client schema and does not approve a predictive model.

## Generate the package

```bash
python scripts/pilot_intake_package.py generate \
  --output data/generated/pilot_intake_template/v1
```

The command creates:

```text
README.md
client_intake_manifest.json
pilot_acceptance_plan.json
file_register.csv
relationship_hints.csv
package_manifest.json
materials/
```

Generated transfer folders are local artifacts and are not committed to the repository.

## Client intake manifest

`client_intake_manifest.json` records:

- client and project identity;
- requested business decision;
- expected creative count and working language;
- confidentiality classification;
- local-only processing requirement;
- prohibition of cloud transfer;
- immutable-original requirement;
- retention and deletion fields;
- available, pending, unavailable and non-applicable material categories;
- known limitations and sign-off fields.

The minimum material categories are:

1. creative;
2. brief;
3. audience;
4. evaluation criteria.

Optional categories are brandbook, historical campaign data, compliance rules, a reference report and other supporting material. Their absence must reduce readiness or appear as a report limitation rather than being silently invented.

## As-is intake policy

The manifest explicitly states:

```text
files_may_be_sent_as_is = true
mandatory_client_schema = false
mandatory_file_renaming = false
internal_mapping_and_normalization = true
```

The system inspects real files first and asks only evidence-backed questions. A clarification batch remains limited to 3–5 questions and may contain fewer when fewer material gaps exist.

## File register

Every received file is entered into `file_register.csv` with:

```text
record_id
category
relative_path
original_filename
media_type
size_bytes
sha256
received_at
status
notes
```

A row marked `provided` must resolve inside the package root and match the registered byte size and SHA-256. Parent-directory escapes are rejected. Original filenames are preserved and no renaming convention is imposed.

## Relationship hints

`relationship_hints.csv` accepts only relationships already known to the client or analyst:

- creative to historical row or key;
- creative to brief;
- creative to audience;
- creative to brandbook;
- creative variant relationship;
- another documented relationship.

A relationship hint is evidence, not permission to invent a link. Unknown record identifiers and incomplete relationships are rejected.

## Seal after editing

Generation creates a blank, sealed template. After client details, file rows, relationships or acceptance fields are edited, the control-file hashes must be refreshed:

```bash
python scripts/pilot_intake_package.py seal \
  --input <pilot-transfer-folder>
```

`seal` recomputes `package_manifest.json` and records:

```text
template_only
provided_file_count
contains_client_data
confidentiality
accuracy_promise = false
prediction_generated = false
real_respondents_used = false
```

`contains_client_data` becomes true only when at least one file is registered as `provided` and confidentiality is not `synthetic`. This avoids incorrectly labelling a completed NDA package as an empty template.

Any subsequent change to a transfer-control file invalidates the manifest until the package is sealed again.

## Acceptance gates

`pilot_acceptance_plan.json` contains six separate gates.

### G1 — Intake integrity

All files are traceable by path, size and SHA-256; originals remain unchanged; confidentiality and local handling are recorded.

### G2 — Data understanding

Files are inspected without a mandatory client schema; mappings require analyst confirmation; gaps become explicit issues and questions.

### G3 — Capability honesty

Each capability receives an independent readiness decision. Missing evidence cannot be replaced by fabricated CTR, lift, accuracy or respondent claims.

### G4 — Closed-loop execution

At least one intake-to-report workflow completes on the target workstation; an unchanged-input rerun is reproducible; report statements remain traceable to source evidence.

### G5 — Expert usefulness

Client or agency experts review findings at finding level. Disagreement is retained rather than hidden in a composite score. Report revisions and reasons are measured.

### G6 — Operational exit

Backup/restore is exercised or explicitly waived; retention/deletion is recorded; unresolved risks are assigned, accepted or carried forward.

Gates G1, G2, G3, G4 and G6 are blocking. G5 evaluates practical value: a technically complete workflow cannot be called useful when expert review rejects its findings.

## Pilot metrics

The package fixes metric definitions before results are seen:

```text
time_to_first_report_minutes
operator_touch_time_minutes
manual_mapping_count
clarification_question_count
unresolved_blocker_count
successful_closed_loop_rate
repeat_run_consistency
expert_agreement
report_revision_count
```

Targets are intentionally provisional:

- first useful report: proposed target up to 60 minutes;
- successful closed-loop rate: proposed target at least 0.90;
- unresolved blockers: zero before a client-facing conclusion;
- clarification questions: 3–5 per evidence-backed batch, with fewer allowed;
- expert agreement and repeat consistency: measure a baseline before setting a pass threshold.

These are pilot operating criteria, not model-accuracy promises.

## Evidence boundary

The acceptance plan always records:

```text
technical_readiness_is_not_model_accuracy = true
synthetic_results_are_not_market_results = true
client_methodology_is_not_final = true
final_thresholds_require_real_pilot_data = true
```

Historical CTR is not causal creative lift. Synthetic questionnaire output is not a real respondent study. A technically successful run can still end with a restricted descriptive/compliance-only capability.

## Validation

Validate a generated blank package:

```bash
python scripts/pilot_intake_package.py validate \
  --input data/generated/pilot_intake_template/v1
```

After real materials are registered:

```bash
python scripts/pilot_intake_package.py seal \
  --input <pilot-transfer-folder>

python scripts/pilot_intake_package.py validate \
  --input <pilot-transfer-folder> \
  --verify-registered-materials
```

Check deterministic template generation:

```bash
python scripts/pilot_intake_package.py check-determinism
```

Validation covers package identity, local-only/no-cloud policy, immutable originals, required material categories, the clarification limit, all six gates, all nine metrics, evidence boundaries, identifier uniqueness, allowed statuses and relations, path confinement, registered material size/SHA-256, dynamic package state and hashes of all transfer-control files.

## Exit decisions

The acceptance plan supports:

```text
accept_for_controlled_internal_use
continue_calibration
limit_to_descriptive_or_compliance_workflow
pause_for_data_remediation
stop_pilot
```

The first pilot is not forced into a binary success/failure label. A restricted useful workflow can be retained while unsupported prediction claims remain disabled.

## Non-goals

PRE-PILOT-004 does not:

- receive or commit real client data;
- define a final model or accuracy threshold;
- force a client spreadsheet schema;
- create cloud transfer tooling;
- generate a client-facing one-page report;
- execute the operator rehearsal;
- train or calibrate a prediction model;
- replace legal, NDA or information-security review.
