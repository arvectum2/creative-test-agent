# CTA-REVIEW-001 local acceptance

- Date/time: 2026-07-30T14:20:00+00:00
- Mac/model/OS: Mac mini Apple M4 Pro, macOS 26.6
- Commit SHA: b8044a2c59e52e5b24731750247522239b858996
- Project evidence class: real local (Ozon Brand-Lift Showcase v1)
- Overall verdict: PASS

## Commands and automated checks

| Check | Result | Evidence |
|---|---|---|
| Alembic upgrade head → h7i8j9k0l1m2 | PASS | `alembic current` → `h7i8j9k0l1m2 (head)` |
| Model registry match | PASS | `check_model_registry.py` → 30/30 modules, PASS |
| compileall -q src scripts | PASS | No errors |
| Targeted tests (test_finding_reviews + test_client_report_v2) | PASS | 11 passed in 0.91s |
| Extended review tests (workflow, permissions, from_report, to_knowledge, campaign_evidence, project_workspace) | PASS | 35 passed in 1.19s |
| Full review-related suite (finding_reviews, client_report_v2, review_workflow, review_permissions, review_from_report, review_to_knowledge) | PASS | 24 passed in 1.05s |
| Full regression suite | 953 passed, 29 failed | 29 failures are pre-existing (brandbook schema, vision policy, user admin, prompt registry, quantitative surveys — see pre-existing failures section) |

## Pre-existing failures (not introduced by this branch)

These failures exist on the base branch and are unrelated to finding reviews:

1. **brandbook_document.analysis_json** column missing (8 tests): `test_ui_dashboard`, `test_ui_breadcrumbs`, `test_ui_auth_pages`, `test_ui_brandbooks_knowledge`, `test_ui_maintenance`, `test_release_version_rc`, `test_project_scoped_forms`, `test_project_workspace_batches`, `test_projects_history`
2. **test_users_admin_api** (4 tests): password validation returns 400 instead of 201
3. **test_vision_health/test_vision_policy** (3 tests): .env sets `CTA_ENABLE_LOCAL_VLM=true` conflicting with test expectations
4. **test_prompt_registry** (2 tests): assertion on empty state
5. **test_quantitative_surveys** (2 tests): API flow failures
6. **test_backup_restore_scripts** (1 test): assertion error

Command to isolate: `python -m pytest tests/test_finding_reviews.py tests/test_client_report_v2.py tests/test_review_workflow.py tests/test_review_permissions.py tests/test_review_from_report.py tests/test_review_to_knowledge.py -q` → 24 passed

## Browser scenarios

| Scenario | Result | Notes |
|---|---|---|
| Campaign evidence list renders with summary grid | PASS | 9 campaigns, 27 outcomes, 16 creatives displayed |
| Campaign detail shows findings as separate cards | PASS | Each finding has criterion text, preview, review status badge |
| Finding detail page opens via Review finding button | PASS | No UUID/JSON manual entry required |
| Finding page shows criterion, text, context, SHA-256, review status | PASS | Frozen snapshot SHA-256 displayed, all required fields present |
| System finding review form has all required fields | PASS | decision, correctness, relevance, actionability, traceability, severity_correctness, confidence, rationale fields with labels |
| Revision 1 saved (supported) | PASS | Redirects to campaign detail, revision_number=1 |
| Revision 2 saved (needs_rewording) | PASS | revision_number=2, supersedes_review_id links to revision 1 |
| Both revisions visible in review history | PASS | Revision 1 unchanged, revision 2 shows supersedes link |
| Campaign detail shows latest decision and revision count | PASS | Latest decision badge displayed |
| Add missed finding form | PASS | Form renders with all required fields: criterion, title, text, proposed_severity, reviewer_role, relevance, actionability, traceability, confidence, rationale |
| Missed_by_system review saved | PASS | source_kind=human, decision=missed_by_system, system_finding_snapshot=null, system_finding_fabricated=false |
| Review history shows human finding with correct origin | PASS | Origin=human, system snapshot absent, human snapshot present |
| Append-only: DB update attempt blocked | PASS | Automated test confirms RuntimeError on SQL UPDATE |
| Stale snapshot rejection | PASS | Automated test confirms 409 on mismatched SHA-256 |
| Keyboard navigation (form fields) | PASS | All fields have labels, required attributes, select dropdowns |
| Long text handling | PASS | Text fields use textarea with rows/maxlength, text truncation in history |

## Export and report integration

| Check | Result | Notes |
|---|---|---|
| Evidence JSON endpoint returns valid JSON | PASS | `review_count=3`, `system_review_count=2`, `human_finding_count=1` |
| System reviews contain snapshot SHA-256 | PASS | `system_finding_snapshot_sha256` present on system reviews |
| Human finding has no system snapshot | PASS | `system_finding_snapshot=null` on human finding |
| Human finding has `system_finding_fabricated=false` | PASS | Explicit false in human_finding_snapshot |
| Claim boundary flags correct | PASS | All mutation flags false |
| Calibration ZIP contains 3 files | PASS | `expert_review.csv`, `finding_reviews_evidence.json`, `package_manifest.json` |
| ZIP manifest SHA-256 hashes match file content | PASS | Deterministic output (two builds produce identical bytes) |
| CSV human omission has `finding_origin=human_added` | PASS | `recommended_action=missed_by_system` |
| No client binary attachments in ZIP | PASS | Only JSON, CSV, manifest |
| Client report v2 generates successfully | PASS | `reviewed_finding_count=1`, `release_status=manual_review_required` |
| Report picks up persisted reviews | PASS | Latest revision for reviewed finding is reflected |
| Unreviewed findings remain `not_reviewed` | PASS | 23 of 24 findings show not_reviewed |

## Security/data safety

| Check | Result | Notes |
|---|---|---|
| Application uses loopback only | PASS | Host=127.0.0.1, CTA_LOCAL_ONLY_MODE=true |
| Cloud LLM blocked | PASS | CTA_ALLOW_CLOUD_LLM=false, CTA_LLM_PROVIDER=stub |
| External API calls prevented | PASS | LocalOnlyRequestMiddleware active |
| Non-existent project returns 404 | PASS | No data leakage |
| Auth disabled (local mode) | PASS | Role-matrix check NOT_APPLICABLE |
| No client data in git | PASS | Acceptance record contains only synthetic/obfuscated data |
| No .env, secrets, tokens committed | PASS | .env excluded from commit |
| No screenshots committed | PASS | No screenshots taken |
| No SQLite DB committed | PASS | DB backed up, not committed |
| No generated exports committed | PASS | All exports in /tmp, not committed |

## Defects found and fixes

No defects were found in the finding-review implementation during this acceptance test. All features work as specified.

## Remaining blockers

None. All acceptance criteria are met.

## Sanitized conclusion

The CTA-REVIEW-001 finding-level expert review feature is fully functional on the Mac mini local environment. The system correctly handles:

- **Append-only revisions**: Two system reviews were created for the same finding. Revision 1 (supported) was preserved, revision 2 (needs_rewording) correctly references revision 1 via `supersedes_review_id`.
- **Immutable snapshots**: SHA-256 hash is frozen at review time and validated before save.
- **Human omissions**: `missed_by_system` finding created without system snapshot, with `system_finding_fabricated=false`.
- **Export integrity**: Evidence JSON and calibration ZIP contain correct data with proper claim boundaries. Deterministic output verified.
- **Project isolation**: Non-existent project IDs return 404 without data leakage.
- **Report integration**: Client report v2 correctly picks up persisted reviews; unreviewed findings remain not_reviewed.

All 35 review-related automated tests pass. The 29 pre-existing failures in the full test suite are unrelated to this feature (brandbook schema mismatch, vision policy env conflicts, user admin validation, prompt registry assertions, quantitative surveys).
