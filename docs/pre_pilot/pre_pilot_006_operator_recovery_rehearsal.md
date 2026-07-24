# PRE-PILOT-006 — Operator and Recovery Rehearsal

Status: executable automated recovery drill implemented; human operator sign-off remains a separate observed activity.

## Purpose

This stage verifies that a complete local pilot workspace can be created, backed up, deliberately damaged, restored and reopened without losing the evidence required for review.

It also creates a structured checklist for a non-developer operator. The automated drill must never mark that human checklist as completed or claim that usability has been proven.

## Command

```bash
python scripts/operator_recovery_rehearsal.py run \
  --workspace data/rehearsals/pre_pilot_006

python scripts/operator_recovery_rehearsal.py validate \
  --input data/rehearsals/pre_pilot_006
```

The command uses only synthetic materials and an isolated workspace. It does not touch the normal application database, storage or exports directories.

A Make target is also available:

```bash
make operator-recovery-rehearsal
```

## Automated scenario

The rehearsal performs the following sequence:

1. Creates an isolated PRE-TZ messy-data workspace.
2. Completes immutable intake, inspection, mapping, normalization, Data Quality, clarifications, Prediction Readiness and a labelled synthetic quantitative proxy.
3. Generates and verifies the XLSX Data Review Report.
4. Generates the provisional one-slide client PPTX, one-page HTML, evidence JSON and manifest.
5. Adds a local export sentinel and a database recovery marker.
6. Creates a backup using the SQLite backup API rather than copying the live database file directly.
7. Validates every archived payload file by path, size and SHA-256.
8. Deliberately deletes report records and replaces storage and exports with damage markers.
9. Confirms that the workspace is no longer usable.
10. Creates the mandatory pre-restore backup of the damaged state.
11. Restores the primary backup through path-confined extraction and atomic replacement.
12. Reopens the database layer and runs `PRAGMA integrity_check`.
13. Revalidates the immutable source session.
14. Reopens the restored Data Review Report and all one-page report artifacts through checksum-verifying accessors.
15. Revalidates the quantitative study and its explicit synthetic source label.
16. Produces machine-readable evidence and a blank operator checklist.

## Output

```text
data/rehearsals/pre_pilot_006/
├── live/
│   ├── creative_test_agent_demo.db
│   ├── storage/
│   ├── exports/
│   └── demo_manifest.json
├── backups/
│   ├── pre_pilot_006_primary.zip
│   └── pre_restore_..._pre_pilot_006_primary.zip
├── evidence/
│   ├── automated_rehearsal_report.md
│   ├── automated_timeline.csv
│   └── operator_checklist.json
├── rehearsal_manifest.json
└── evidence_manifest.json
```

`rehearsal_manifest.json` contains all automated checks, run identifiers, backup manifests, durations and evidence boundaries. `evidence_manifest.json` records size and SHA-256 for the evidence files.

## Backup format v2

PRE-PILOT-006 upgrades the local backup archive to format version 2.

Every payload file is listed in `manifest.json` with:

```text
path
size_bytes
sha256
```

The manifest also records:

- backup ID and timestamp;
- exact inclusion of database, storage and exports;
- complete SQLite table counts from the snapshot;
- total payload size and file count;
- SQLite snapshot method;
- explicit absence of environment files and secrets by design.

The database snapshot is created with `sqlite3.Connection.backup`, which includes committed WAL state and avoids the inconsistency risk of copying a live SQLite file directly.

## Validation and extraction rules

A backup is rejected when it contains:

- an unsupported format version;
- duplicate ZIP members;
- undeclared payload files;
- missing declared files;
- size or SHA-256 mismatches;
- absolute, parent-directory or drive-like paths;
- backslash-based paths;
- `.env` files;
- symbolic links;
- encrypted ZIP members;
- an invalid SQLite database;
- inclusion flags that do not match the actual payload.

Restore never calls `ZipFile.extractall`. Each declared file is copied to a path proven to be inside a temporary extraction root and verified again after extraction.

## Restore behaviour

The default restore path is fail-safe:

1. Validate the source backup completely.
2. Refuse to continue when the local application appears to be running, unless `--force` is explicit.
3. Close the current database engine.
4. Create and validate a pre-restore backup of the current state.
5. Stage the restored database and directories.
6. Replace configured paths atomically where supported by the operating system.
7. Verify every restored file and run SQLite integrity checking.

Emergency-only restore without a pre-restore backup requires an explicit flag:

```bash
python scripts/restore_data.py <backup.zip> \
  --force \
  --skip-pre-restore-backup
```

This flag is not used by the rehearsal or normal runbook.

## Same-path limitation

Current database records store local artifact paths. Therefore the verified restore scenario restores to the same configured database, storage and exports paths.

Moving a backup to a different root or another workstation can require path migration. PRE-PILOT-006 does not claim relocatable disaster recovery.

## Human operator session

After the automated drill passes, a non-developer operator must complete `evidence/operator_checklist.json` during an observed session.

The checklist covers:

- starting the rehearsal without developer assistance;
- locating the workspace, backup and restored artifacts;
- validating the backup independently;
- finding the project and reports in the restored application;
- tracing a statement to source evidence;
- recognising degraded or unavailable capabilities;
- recording elapsed time, assistance requested and blockers.

Allowed final decisions are:

```text
passed
passed_with_observations
repeat_required
blocked
```

The generated checklist always starts with `not_started` and `human_operator_signoff_completed=false`.

## Evidence boundary

A green automated rehearsal proves only that:

- the synthetic workflow can complete locally;
- a consistent backup can be created and validated;
- a deliberately damaged workspace can be restored at the same paths;
- critical records and files remain checksum-verifiable after restart.

It does not prove:

- that a non-developer can complete the workflow unaided;
- product usability or training quality;
- model accuracy;
- market effectiveness;
- a formal disaster-recovery SLA;
- cross-machine or cross-path restoration;
- legal, medical or regulatory compliance.
