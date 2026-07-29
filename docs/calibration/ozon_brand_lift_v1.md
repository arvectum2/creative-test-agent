# Ozon brand-lift calibration v1

## Scope

This calibration uses the supplied creative archive and nine campaign rows with control-group (CG) and exposed/test-group (TG) brand metrics. It is a first evidence-based calibration of the diagnostic methodology, not model training and not a validated predictor of market lift.

The unit of evidence is a campaign/creative set linked to a platform and observation window. It is not automatically an individual image. `causal_interpretation_allowed=false` for all rows.

## Statistical treatment

For each available metric, the package records:

- uplift in percentage points (`TG - CG`);
- approximate 95% confidence interval for the difference in proportions;
- two-sided two-proportion z-test;
- Benjamini-Hochberg false-discovery-rate correction across 27 comparisons.

The source rates are rounded to three decimals, so inferential values are approximate.

## Strongest supported patterns

1. **Theraflex Ultra** is the strongest full-funnel case: awareness `+14.2 pp`, ad recall `+7.1 pp`, purchase intent `+17.4 pp`; all remain supported after FDR correction.
2. **Supradyn Immuno** is the most balanced case: `+8.3 / +8.2 / +8.1 pp`; all supported.
3. **Elevit** is primarily an upper-funnel success: awareness `+7.5 pp` and ad recall `+7.9 pp` are supported; purchase intent `+4.1 pp` is nominal only after multiple-comparison correction.
4. **Rennie** demonstrates funnel divergence: awareness `+5.7 pp` is supported, while purchase intent is `-0.5 pp`.
5. **Aerius** and **Supradyn Kids** show lower-funnel strength without comparable upper-funnel evidence: purchase intent `+5.9 pp` and `+4.0 pp`, respectively.
6. **Bepanthen Ointment** and **Supradyn Energy** show that a clean packshot, bright palette, CTA and promotional wording do not by themselves imply material brand lift.

## Calibration implications

The agent must:

- separate awareness, ad recall, purchase intent and consideration instead of collapsing them into one effectiveness claim;
- evaluate the chain `brand → category/problem → specific benefit → product proof → CTA`;
- treat discount and visual brightness as amplifiers, not independent effectiveness drivers;
- distinguish brand prominence from purchase motivation;
- score generic benefits below specific, relevant and credible reasons to buy;
- include visual hierarchy, packshot, brand legibility, message/visual binding and cognitive load in rubric scoring;
- lower confidence when platform, placement, period or asset-to-outcome linkage is uncertain;
- keep missing outcomes missing and mark unlabeled creatives explicitly;
- avoid causal or numeric uplift predictions from this small observational calibration set.

## Data-quality constraints

- Relief has an OZON row in the spreadsheet but only a VK creative in the archive.
- Several campaign rows link to multiple assets or formats: Bepanthen, Aerius, Rennie and Theraflex.
- Triderm has a creative but no outcome row.
- Aerius lacks ad-recall data; most rows lack customer-consideration data.

## Files

- `campaign_outcomes.csv` — normalized outcomes and approximate inference.
- `creative_manifest.csv` — asset hashes, dimensions and linkage confidence.
- `config/pilot_profiles/ozon_brand_lift_calibration_v1.json` — loadable calibrated rubric.
