# CTA-OZON-002 acceptance

## GitHub scope

- [x] Typed project-level campaign evidence read model.
- [x] JSON workspace and campaign detail endpoints.
- [x] Project-scoped campaign cards.
- [x] Campaign detail page with factual CG/TG outcomes beside asset-level diagnostics.
- [x] Secure local preview URLs through the existing protected image endpoint.
- [x] Funnel metrics remain separate and descriptive.
- [x] Linkage status, confidence, platform and notes remain visible.
- [x] Multi-asset campaigns never receive individual-asset outcome attribution.
- [x] Rejected campaign links remain visible but excluded from accepted creative sets.
- [x] Assets without outcomes remain visible as unlabelled evidence.
- [x] Missing diagnostics remain explicit.
- [x] Offline synthetic API/UI regression tests.
- [x] Architecture and evidence-boundary documentation.
- [x] Mac mini/OpenCode local acceptance specification.

## Local acceptance still required

- [ ] Pull the merged GitHub implementation into the existing Mac mini clone.
- [ ] Start the application against the real local Ozon showcase database and storage.
- [ ] Open the workspace from the real project page without manually entering UUIDs.
- [ ] Verify all 9 real campaigns, 27 outcomes and 16 creative records, or document a source-version difference.
- [ ] Verify image previews load from local storage and no client binary is transmitted externally.
- [ ] Verify Theraflex, Rennie, Bepanthen and Supradyn Energy are available as contrast cases.
- [ ] Verify Relief has outcomes but no accepted Ozon creative.
- [ ] Verify Triderm remains unlabelled and without outcomes.
- [ ] Verify all multi-asset campaigns show campaign-level attribution warnings.
- [ ] Verify at least one completed local asset diagnostic is shown beside unchanged factual outcomes.
- [ ] Verify a campaign without a completed diagnostic shows an explicit missing state.
- [ ] Verify responsive layout and readable tables/previews in the browser.
- [ ] Run targeted tests and the complete CI-equivalent suite locally.
- [ ] Record a sanitized browser smoke-test summary in issue #48.

Until the local section is complete, the canonical task status is `BLOCKED_LOCAL`, not `DONE`.
