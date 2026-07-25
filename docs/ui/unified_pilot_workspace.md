# UI-PILOT-001 — Unified Pilot Workspace

Unified Pilot Workspace is the operator-facing browser workflow for the implemented PRE-TZ and PRE-PILOT services.

## Purpose

The workspace removes the need for an ordinary operator to type UUIDs, JSON payloads, local paths or direct API calls. It provides one project-scoped flow:

1. create or select a client and create a pilot project;
2. upload client materials as immutable originals;
3. upload creative assets linked to the project;
4. inspect CSV, TSV and XLSX files;
5. preview detected tables and headers;
6. review explainable mapping suggestions and confirm each source column;
7. normalize the selected table;
8. run Data Quality with current lineage binding;
9. generate up to five client or analyst clarification questions;
10. record answers, deferrals or unavailable evidence;
11. evaluate capability-specific Prediction Readiness;
12. generate and download Data Review XLSX and client one-page artifacts.

## Entry points

- `/ui/pilot-workspaces` — project list;
- `/ui/pilot-workspaces/new` — create a client/project pilot;
- `/ui/pilot-workspaces/{project_id}` — operator dashboard;
- project cards and the main dashboard link back to the workspace.

## Operator workflow

### Create a pilot

Select an existing client or enter a new client name, then enter the pilot project name and description. The system creates the project and opens its workspace.

### Upload the client delivery

Use **Загрузить поставку заказчика**. Files are stored through the existing immutable import-session service, completed, checksum-verified and, for CSV/TSV/XLSX, inspected automatically.

Non-tabular source documents remain registered in the same delivery but are not forced through the table inspector.

### Upload creatives

Use **Добавить креативы**. Accepted creative files go through the existing safe upload processor and are linked to the current project.

### Process a table

Open an inspected table from the workspace. The page shows:

- detected header row and confidence;
- source warnings;
- a bounded data preview;
- every source column, inferred type and sample values;
- mapping proposals and confidence;
- current normalization and Data Quality state.

The operator can confirm a target field, mark a column unused, reject a proposal or explicitly allow a duplicate target.

### Run Data Quality

Data Quality is generated only after the operator chooses to run it. Existing strict lineage rules remain in force: a normalization from an older mapping contract is not consumed.

### Questions and readiness

The Data Quality page can generate separate client and analyst question batches. Each response is append-only and can be marked answered, deferred, unavailable or not applicable.

Prediction Readiness is presented separately for every capability. It is a workflow availability decision and is never described as model accuracy.

### Reports

The operator can generate:

- internal Data Review XLSX;
- client one-page PPTX;
- client one-page HTML;
- evidence JSON;
- artifact manifest.

Downloads use the existing path-confinement and SHA-256 verification helpers.

## Roles and safety

When authentication is enabled, existing write middleware limits workspace mutations to admin, manager and analyst roles. Viewer accounts remain read-only.

All processing stays inside the configured local-only security posture. The workspace does not enable cloud LLMs or remote file transfer.

## Evidence boundaries

The workspace does not introduce or imply:

- predicted CTR;
- causal creative lift;
- validated model accuracy;
- market-effectiveness proof;
- legal, medical or regulatory approval;
- final client methodology or thresholds;
- automatic model selection.

Synthetic and human evidence remain separately labelled by the underlying services.

## Remaining advanced workflows

Quantitative questionnaire authoring, human-study administration, calibration-package editing, local model benchmark execution and disaster-recovery administration remain advanced/API/CLI workflows in UI-PILOT-001. They can be added to later operator screens without changing the minimum controlled pilot path delivered here.
