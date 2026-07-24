# PRE-TZ architecture decisions

Status: accepted for the PRE-TZ roadmap.

These decisions govern development until the client's specification and source materials are received and analysed.

## AD-001 — Accept source data as received

The product must not require the client to populate a large prescribed workbook before discovery begins.

The ingestion boundary will accept source files in their existing form. Internal normalization, mapping and quality analysis are responsibilities of the product team and the software.

## AD-002 — Preserve immutable raw inputs

Every imported source file must be retained unchanged, identified by a cryptographic hash and linked to the user, project and import event that introduced it.

Normalized records never replace raw records.

## AD-003 — Provenance is mandatory

Every normalized value introduced by the future ingestion pipeline must be traceable to its source file, sheet or table, row and source column, plus the mapping or normalization version that produced it.

Values created by calculation must identify their inputs and calculation version.

## AD-004 — Unknown fields are preserved

Unexpected columns and metadata must not be discarded merely because the current domain schema does not recognize them. They remain available in the raw layer and may be carried into structured metadata until promoted to first-class fields.

## AD-005 — Validation is progressive

Missing campaign, placement, audience or performance fields do not automatically reject an import.

Validation findings are classified as informational, warning or blocking. A condition is blocking only when the next requested operation cannot be performed safely or deterministically.

## AD-006 — Mapping suggestions require evidence

Automatic column mapping may propose a target field and confidence score, but ambiguous mappings are not silently accepted. A confirmed mapping profile must record who or what confirmed it and which source format it applies to.

## AD-007 — Prediction is capability-gated

Creative analysis, synthetic survey, media baseline and CTR prediction are separate capabilities.

A numerical CTR prediction must not be produced unless the project satisfies explicit readiness rules. When it does not, the product reports a reasoned status such as insufficient history, missing placement context or calibration required.

## AD-008 — No final CTR algorithm before data discovery

Before the client's real historical data is inspected, the project will not commit to a final statistical or machine-learning algorithm, final feature set, accuracy promise or fixed retraining procedure.

Infrastructure may be prepared, but modelling decisions must follow evidence from the supplied data.

## AD-009 — Brand-lift methodology is configurable

The existing general creative rubric is not treated as the client's brand-lift methodology.

Questionnaires, response scales, metrics and aggregation rules must be versioned configuration. The client-specific methodology will be configured only after it is received and understood.

## AD-010 — Local-only is the default trust boundary

Client creative assets, campaign history, brand materials and reports must remain inside the configured local deployment unless an explicitly approved future requirement changes that boundary.

Cloud LLM and cloud vision providers remain disabled by default. CI must continuously verify the local-only defaults.

## AD-011 — Schema changes require migrations

`Base.metadata.create_all()` remains temporarily for backward compatibility, but all new persistent entities must include an Alembic migration.

CI must create a fresh database through migrations and verify that the resulting revision equals the repository head. Runtime model registration and Alembic model registration must remain synchronized.

## AD-012 — Small, independently verifiable changes

Each PRE-TZ roadmap item is implemented as a separate branch and pull request with tests, migration checks and documentation appropriate to that item.

A roadmap item is complete only when its pull request passes the mandatory CI workflow and the merged state is independently rechecked.