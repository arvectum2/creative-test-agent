# Repository-wide refactor — August 2026

## Goal

Eliminate known structural technical debt without changing the Creative Test Agent product contract: local-only processing, deterministic evidence handling, role-aware writes, and backward-compatible API/UI routes.

## Architecture changes

- Replaced the 258-line import-time application bootstrap with a small ASGI entry point and an explicit `create_app()` factory.
- Centralized application lifecycle, middleware, exception handlers, operational endpoints, and router registration under `src/app/`.
- Migrated startup initialization from deprecated FastAPI `on_event` hooks to lifespan management.
- Moved nested client/project compatibility routes into their owning domain routers.
- Removed startup-time mutation of the UI router; authentication pages now have one explicit owner.
- Replaced the monolithic UI and pilot-workspace routers with domain-focused composition roots.

## Domain refactors

- Split data-quality policy into source, normalization, readiness, and issue-construction modules.
- Split clarification generation into a small orchestrator, shared context/value objects, and ordered rule modules.
- Split normalized-data response serialization, scalar normalization, and row persistence from service orchestration.
- Split calibration metric assembly and deterministic export rendering from dashboard composition.
- Split mapping-engine response assembly from mapping decisions.
- Split tabular detection and scalar inference from file inspection.
- Split vision benchmark candidate/scoring logic from execution, aggregation, and reporting.
- Split CTA-BENCH command handling and deployment-topology execution from common runner utilities.
- Split PRE-TZ workspace management, pipeline stages, contracts, and manifest serialization.
- Split test-run safety/compliance stages from the central analytical pipeline.
- Centralized report mode/format contracts in `src/modules/report_generator/contracts.py`.
- Replaced duplicated request-user helpers with typed shared authentication helpers.

## Correctness and hardening

- Expected authentication failures are handled explicitly; unexpected database or programming errors are no longer silently converted to anonymous requests.
- Unexpected API errors are logged centrally while returning a stable public error contract.
- Mutable Pydantic collection defaults were replaced with `Field(default_factory=...)`.
- Alembic configuration was updated to remove legacy path parsing behavior.
- SQLAlchemy test model discovery is explicitly disabled for the `TestRun` ORM class.
- Public routes and tested compatibility imports are preserved by the new composition modules.

## Executable debt controls

`python scripts/check_code_health.py` enforces:

- parseable Python sources;
- no deprecated FastAPI startup hooks;
- no duplicated private request-user helpers;
- no mutable literal defaults in schema models;
- no legacy route mutation;
- a slim application entry point;
- repository-wide module and function size ceilings;
- an empty legacy-exception budget.

The gate runs in CI and is also available as:

```bash
make code-health
```

The final structural budget is defined in `config/quality/code_health_budget.json`. It contains no tracked module or function exceptions; all current and future code is evaluated against the same ceilings. One-time transformation scripts and workflows were removed after application, so the repository contains only maintained runtime, test, and quality-control code.

## Regression coverage

Application-composition tests cover lifespan usage, route uniqueness, domain ownership, and compatibility exports. Existing authentication, UI, data-quality, clarification, normalization, calibration, prediction-readiness, reporting, benchmark, backup, and recovery tests remain the behavioral safety net. Every structural extraction is accepted only after the complete CI, calibration, and local-model contract workflows pass.
