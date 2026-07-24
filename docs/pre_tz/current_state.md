# PRE-TZ baseline: current state

Baseline branch: `main`

Audited baseline commit: `bd6b652dd3f156f0656a010f5211bcaad2682807`

This document records the implementation state before the flexible client-data foundation is added. It is intentionally limited to facts verified in the repository.

## Product foundation already present

The application is a FastAPI service with a local web UI. The default persistence layer is SQLAlchemy with SQLite, with PostgreSQL support available through the configured database URL.

The application currently registers modules for:

- agent registry;
- creative assets;
- brand and audience profiles;
- test rubrics and test runs;
- report generation and comparisons;
- clients, projects and project history;
- users, authentication and administration;
- brandbooks and the local knowledge base;
- model profiles, prompt registry, prompt traces and evaluations;
- reviews, local job queue and batches;
- audit log, exports, demo UI, local LLM and local vision providers.

## Local-only defaults

The checked-in defaults are safe for local development:

- `CTA_LOCAL_ONLY_MODE=true`;
- `CTA_ALLOW_CLOUD_LLM=false`;
- `CTA_LLM_PROVIDER=stub`;
- `CTA_VISION_PROVIDER=stub`;
- uploads and generated exports are stored locally.

Cloud SDKs are not project dependencies. `scripts/check_closed_loop.py` verifies the supported local provider set and rejects known cloud SDK packages when they are installed in the runtime environment.

## Authentication and access control

Authentication and role-based write protection exist, with the roles `admin`, `manager`, `analyst` and `viewer`. Authentication is disabled by default for local development. Server or client-data deployments must explicitly enable it and provide a non-default secret.

Current limitations that remain outside CTA-PRE-001:

- no MFA or SSO;
- no password-reset flow;
- no server-side session store;
- project-level read isolation requires a dedicated security review before confidential client data is accepted.

## Persistence and migrations

Runtime startup currently calls `Base.metadata.create_all()`. Alembic migrations also exist and are used by the deployment scripts.

This dual mechanism is retained for backward compatibility in CTA-PRE-001, but it creates an important rule for all future work:

> A table existing after application startup is not proof that its Alembic migration exists.

The mandatory CI sequence therefore creates a fresh database through Alembic first, verifies that the database revision equals the repository head, and only then runs the test suite.

CTA-PRE-001 also adds an executable check that the model modules registered by runtime database initialization and Alembic metadata stay synchronized.

## Existing verification entry points

The repository already contains:

- the pytest suite under `tests/`;
- `scripts/run_migrations.py`;
- `scripts/check_migrations.py`;
- `scripts/check_closed_loop.py`;
- `scripts/check_demo_readiness.py`;
- evaluation and release-readiness scripts.

CTA-PRE-001 combines the stable baseline checks into one command:

```bash
make PYTHON=python ci-check
```

The same command is executed by GitHub Actions on pull requests and pushes to `main`.

## Exports

Real local DOCX and PPTX generation and PDF-ready HTML are implemented. Legacy stub endpoints remain for backward compatibility. The canonical export description is `docs/advanced_report_exports.md`.

## PRE-TZ scope boundary

No CTR prediction model, campaign-history import contract, fixed brand-lift methodology or client-specific schema is introduced in CTA-PRE-001.

The next PRE-TZ tasks may rely on this baseline only after the required CI workflow passes.