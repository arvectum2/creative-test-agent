# PRE-PILOT-006 Acceptance Checklist

## Automated recovery drill

- [x] Runs only in an isolated synthetic workspace.
- [x] Completes the existing messy-data PRE-TZ workflow.
- [x] Generates the provisional one-page client report before backup.
- [x] Creates a consistent SQLite snapshot through the SQLite backup API.
- [x] Includes storage and exports when they contain files and configuration allows them.
- [x] Records every payload path, byte size and SHA-256 in backup format v2.
- [x] Rejects undeclared, missing, duplicated, traversing, encrypted, symlinked or checksum-mismatched payloads.
- [x] Confirms database, report-record and file loss before restore.
- [x] Creates and validates a pre-restore backup by default.
- [x] Restores through safe extraction and staged replacement.
- [x] Verifies every restored payload file.
- [x] Runs SQLite `PRAGMA integrity_check` after restore.
- [x] Reopens the database layer after restore.
- [x] Revalidates the immutable import session.
- [x] Revalidates the XLSX Data Review Report.
- [x] Revalidates PPTX, HTML, evidence JSON and manifest from PRE-PILOT-005.
- [x] Revalidates quantitative evidence and the explicit synthetic source label.
- [x] Produces a machine-readable manifest, timeline, report and SHA-256 evidence manifest.

## Operator controls

- [x] Generates a ten-step non-developer operator checklist.
- [x] Records allowed human decisions without preselecting a successful result.
- [x] Starts with `final_decision=not_started`.
- [x] Keeps `human_operator_signoff_completed=false` after the automated run.
- [x] Does not claim that absence of developer assistance was proven automatically.
- [x] Documents same-path restore limitations.
- [x] Documents emergency-only bypass of the pre-restore backup.

## Regression and operations

- [x] Existing backup and restore commands remain available.
- [x] `check_backup.py` is reusable as a function and CLI.
- [x] Backup creation validates its own archive before publication.
- [x] Archive publication uses an atomic file replacement.
- [x] Unit tests exercise tampering detection, recovery and pre-restore backup creation.
- [x] Mandatory CI executes the full isolated rehearsal and validates its evidence.
- [x] GitHub Actions retains `contents: read` permissions.

## Explicit non-goals

- [x] No client data is used or committed.
- [x] No human operator result is fabricated.
- [x] No model-quality or market-effectiveness conclusion is generated.
- [x] No disaster-recovery SLA is claimed.
- [x] No cross-machine/path relocation is claimed.
- [x] No cloud backup or transfer is introduced.
