# Independent finding-review adjudication

Canonical task: `CTA-REVIEW-002`.

## Data model

### FindingReview

`FindingReview` remains append-only. CTA-REVIEW-002 adds:

- `reviewer_subject_id` — stable reviewer identity;
- `reviewer_subject_kind` — authenticated, declared local expert or migrated legacy identity;
- `reviewer_revision_number` — revision sequence inside one reviewer stream.

`revision_number` remains a finding-wide append order for backward compatibility. `supersedes_review_id` points only to the prior revision from the same reviewer subject.

### FindingAdjudication

An adjudication stores:

- project/finding/campaign scope;
- policy ID;
- immutable ordered basis review IDs;
- SHA-256 basis fingerprint;
- adjudicator identity and role;
- final decision and rating dimensions;
- confidence and mandatory rationale;
- append-only adjudication round and superseded round ID.

Update and delete are rejected by SQLAlchemy lifecycle guards.

## Reviewer identity

- authenticated user: `user:<user_id>`;
- local/no-auth mode: `declared:<operator-entered-id>`;
- migrated CTA-REVIEW-001 rows: `legacy:<normalized-display-name>` where no user ID existed.

The browser form uses a human-readable Expert ID; operators do not enter UUID or JSON.

## Disagreement policy v1

Policy ID: `independent-review-adjudication/1.0`.

The latest immutable revision of every reviewer stream is compared. A material disagreement exists when at least two reviewer subjects are present and one or more conditions hold:

- decisions differ;
- severity-correctness values differ;
- spread for correctness, relevance, actionability or traceability is at least 2 on the 1–5 scale.

States:

- `insufficient_reviews`;
- `agreement`;
- `disagreement`;
- `adjudicated`;
- `stale_adjudication`.

A current adjudication must match both the ordered basis review IDs and the SHA-256 basis fingerprint. Any new reviewer revision changes the basis and makes the previous adjudication stale.

## Permissions

- reviews: admin, manager, analyst;
- adjudication: admin or manager;
- adjudicator must be distinct from every basis reviewer under policy v1.

The service layer repeats the permission check so direct internal callers cannot bypass router authorization.

## API

Read:

- `GET /finding-reviews/projects/{project_id}/findings`;
- `GET /finding-reviews/projects/{project_id}/findings/{finding_id}`;
- `GET /finding-reviews/projects/{project_id}/findings/{finding_id}/disagreement`;
- `GET /finding-reviews/projects/{project_id}/disagreements`;
- `GET /finding-reviews/projects/{project_id}/reviews`;
- `GET /finding-reviews/projects/{project_id}/adjudications`;
- `GET /finding-reviews/projects/{project_id}/evidence.json`;
- `GET /finding-reviews/projects/{project_id}/calibration-package.zip`.

Write:

- `POST /finding-reviews/projects/{project_id}/findings/{finding_id}/reviews`;
- `POST /finding-reviews/projects/{project_id}/findings/{finding_id}/adjudications`;
- `POST /finding-reviews/projects/{project_id}/human-findings`.

Writes use optimistic fingerprints. A stale system snapshot or adjudication basis returns HTTP 409.

## Browser workflow

From Campaign Evidence, open the finding review page, save reviewer-specific decisions, inspect the automatically calculated state, and open the adjudication page for active or stale disagreement. The page shows both basis reviews and the basis fingerprint before saving.

## Evidence and report behavior

Evidence JSON includes reviews, adjudications, disagreement states and claim boundaries. Calibration ZIP contains:

- `finding_reviews_evidence.json`;
- `expert_review.csv`;
- `adjudications.csv`;
- `package_manifest.json`.

ZIP timestamps are fixed and the manifest contains SHA-256 checksums, so unchanged data produce byte-identical packages.

Client Report v2 behavior:

- unresolved/stale disagreement → `not_reviewed`, `pending_adjudication`, `manual_review_required`;
- current adjudication → adjudicated final verdict with immutable basis;
- independent agreement → consensus state with references to immutable reviews;
- human-added omissions remain separate from system findings.

No validated-accuracy, causal-lift, individual-asset outcome attribution or automatic-threshold claim is generated.
