# Ozon Campaign Evidence Workspace

`CTA-OZON-002` adds a read-only, project-scoped evidence workspace over the records produced by `CTA-OZON-001`.

## Purpose

The workspace keeps four layers visibly separate:

1. campaign identity and source period;
2. supplied creative set with linkage status and confidence;
3. observed campaign-level CG/TG outcomes;
4. the latest agent diagnostic for each individual creative asset.

The page is intended for evidence review, not for causal attribution or prediction.

## Routes

### JSON API

- `GET /campaign-evidence/projects/{project_id}` — full workspace.
- `GET /campaign-evidence/projects/{project_id}/campaigns/{campaign_id}` — one campaign. The second parameter accepts either the normalized campaign ID or canonical case ID such as `OZON-007`.

### Browser UI

- `GET /ui/projects/{project_id}/campaign-evidence` — campaign cards and unlabelled assets.
- `GET /ui/projects/{project_id}/campaign-evidence/{campaign_id}` — factual outcomes beside asset-level diagnostics.

The project page contains a `Campaign Evidence` card linking to the workspace.

## Data source and selection

The service selects the newest completed `NormalizationRun` for the project where:

- `normalizer_name = ozon_showcase_loader`;
- `status = completed`;
- the run belongs to the requested project.

It then aggregates:

- `Campaign`;
- `CreativeRecord` and the corresponding `CreativeAsset`;
- `Placement` and `PerformanceObservation`;
- the latest `TestRun` per creative asset, preferring a completed run over a newer incomplete fallback.

No data is copied into a second workspace table. The UI is a deterministic read model over persisted evidence.

## Linkage semantics

The loader contract is preserved without promotion:

- `exact` — accepted in the creative set;
- `probable` — visible as non-exact evidence;
- `one_to_many` — visible as campaign-level evidence only;
- `uncertain` — visible and never promoted automatically;
- `missing` — shown outside campaign outcomes where no campaign row exists;
- `rejected` — shown inside the relevant campaign as rejected evidence, but excluded from the accepted creative set.

A campaign with more than one accepted asset, or any `one_to_many` asset, receives `campaign_multi_asset`. A campaign with outcomes but no accepted platform-matched asset receives `campaign_without_accepted_asset`.

## Outcome semantics

The workspace displays the loader's descriptive fields:

- `control_n` and `test_n`;
- `cg_rate` and `tg_rate`;
- `uplift_pp_descriptive`;
- `evidence_status`;
- source dates, platform, sheet and row where available.

Funnel stages remain distinct:

- `ad_recall`;
- `awareness`;
- `customer_consideration`;
- `purchase_intent`.

The service does not calculate a composite score, statistical significance, causal effect, or predicted uplift.

## Diagnostic semantics

Diagnostics are always asset-level. For the latest selected `TestRun`, the workspace can display:

- summary and overall score;
- findings, scorecard and risks;
- proposed and effective recommendation;
- visual traceability status;
- visual decision status.

A multi-asset campaign never receives a synthetic campaign diagnostic. Missing diagnostics remain an explicit `missing` state.

## Immutable evidence boundaries

Every workspace response states:

```json
{
  "causal_interpretation_allowed": false,
  "numeric_uplift_prediction_generated": false,
  "individual_asset_outcome_attribution_allowed": false,
  "missing_values_inferred": false,
  "diagnostics_are_model_outputs_not_factual_outcomes": true
}
```

These values are presentation and interpretation boundaries. They do not override the source records.

## Asset previews

Image previews use the existing protected route:

```text
/creative-assets/{asset_id}/image
```

That endpoint validates that the resolved file path remains under the configured local storage root. The workspace does not embed client binaries into HTML, API payloads, GitHub, or CI artifacts.

## Contrast-case order

The campaign list places the four canonical contrast cases first:

1. `OZON-007` — Theraflex Ultra;
2. `OZON-003` — Rennie;
3. `OZON-001` — Bepanthen Ointment;
4. `OZON-006` — Supradyn Energy.

All other campaigns follow in canonical case-ID order. This is navigation ordering only; it is not a ranking of creative quality or campaign effectiveness.

## Tests

`tests/test_campaign_evidence_workspace.py` uses only an in-memory SQLite database and synthetic records. It verifies:

- aggregation of campaigns, outcomes and creatives;
- exact preservation of evidence boundaries;
- contrast-case ordering;
- multi-asset non-attribution;
- Relief-style rejected linkage;
- Triderm-style unlabelled evidence;
- asset-level diagnostics beside unchanged factual outcomes;
- browser list and detail rendering without network access.

Real client assets remain outside GitHub. Final acceptance is the local Mac mini browser smoke test described in `docs/local/CTA-OZON-002_MAC_MINI_OPENCODE.md`.
