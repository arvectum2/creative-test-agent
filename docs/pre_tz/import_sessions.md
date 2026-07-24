# CTA-PRE-002 - import sessions and immutable originals

Status: implemented.

## Purpose

The import boundary accepts client source files in the form in which they are received. It does not require a prescribed workbook and does not parse, normalize or reinterpret the contents during this stage.

## Data model

An `import_session` belongs to one project and groups one delivery of source material. It records the operator, status, file count, total byte count and optional delivery metadata.

Every upload creates a separate `import_source_file` provenance record with:

- original filename;
- client-declared MIME type;
- byte size;
- SHA-256 checksum;
- project and import-session identifiers;
- uploader identifier and upload metadata;
- creation timestamp.

The physical storage path is intentionally not returned by the public API.

## Immutability guarantees

Original bytes are stored in a content-addressed namespace:

```text
imports/originals/sha256/<first-two-hash-characters>/<full-sha256>
```

The storage layer uses exclusive file creation. A pre-existing path is accepted only when its contents have the same SHA-256 checksum; different bytes are never written over an existing original.

Source-file database records have no update or delete API. SQLAlchemy update and delete events reject ORM mutation attempts. External filesystem tampering remains possible for an operating-system administrator, so checksum verification is executable through the integrity endpoint and is also performed before download.

Identical bytes uploaded more than once produce separate provenance records but share the same physical content-addressed blob.

## Lifecycle

1. Create an open import session for an existing project.
2. Upload one or more source files without parsing or schema requirements.
3. Verify stored checksums.
4. Complete the session. Completion is idempotent and seals the session against further uploads.

An empty session cannot be completed.

## API

```text
POST /import-sessions
GET  /import-sessions?project_id=...&status=...
GET  /import-sessions/{session_id}
POST /import-sessions/{session_id}/files
GET  /import-sessions/{session_id}/files
GET  /import-sessions/{session_id}/files/{file_id}/download
GET  /import-sessions/{session_id}/verify
POST /import-sessions/{session_id}/complete
```

Downloads use `application/octet-stream`, `Content-Disposition: attachment`, `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

## Configuration

`CTA_IMPORT_MAX_UPLOAD_SIZE_MB` controls the maximum source-file size. The default is 250 MB. The import boundary accepts any non-empty file with a safe leaf filename because files are stored, not executed.

## Explicit non-goals

CTA-PRE-002 does not introduce:

- spreadsheet parsing;
- column mapping;
- normalization;
- validation of campaign semantics;
- CTR modelling;
- client-specific brand-lift methodology.

Those capabilities consume immutable source records in later roadmap stages.
