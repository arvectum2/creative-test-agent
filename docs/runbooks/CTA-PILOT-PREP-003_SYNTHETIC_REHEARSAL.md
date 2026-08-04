# CTA-PILOT-PREP-003 — synthetic rehearsal runbook

## Purpose

Run one reproducible, client-independent rehearsal of the controlled-pilot process. Use only `tests/fixtures/pilot_rehearsal/cases.json` or a separately frozen synthetic derivative. Never substitute client material in this command path.

## Automated stub rehearsal

From a clean checkout with the development environment active:

```bash
python -m pip install -e '.[dev]'
export CTA_DATABASE_URL='sqlite:///./.local/cta-pilot-prep-003.db'
export CTA_LOCAL_ONLY_MODE=true
export CTA_ALLOW_CLOUD_LLM=false
export CTA_LLM_PROVIDER=stub
export CTA_VISION_PROVIDER=stub
export CTA_ENABLE_AUTH=false

rm -f .local/cta-pilot-prep-003.db
mkdir -p artifacts/local-acceptance/CTA-PILOT-PREP-003/stub
python scripts/run_migrations.py
python scripts/cta_pilot_prep_003.py validate \
  --fixture tests/fixtures/pilot_rehearsal/cases.json
python scripts/cta_pilot_prep_003_runtime.py \
  --fixture tests/fixtures/pilot_rehearsal/cases.json \
  --output-dir artifacts/local-acceptance/CTA-PILOT-PREP-003/stub
python -m pytest tests/test_cta_pilot_prep_003.py -q -s
```

Expected summary:

- six cases;
- four frozen blind runs;
- four outcome reveals, all after freeze;
- two adjudicated disagreements;
- one harmful false positive;
- 34 explicit manual actions;
- no missing-value inference, count reconstruction or linkage promotion.

## Artifact verification

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path('artifacts/local-acceptance/CTA-PILOT-PREP-003/stub')
manifest = json.loads((root / 'rehearsal-manifest.json').read_text())
for item in manifest['files']:
    payload = (root / item['name']).read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    assert actual == item['sha256'], (item['name'], actual, item['sha256'])
print('manifest: PASS')
PY
```

The output directory is local acceptance evidence and must remain ignored by Git.

## Browser and production-model gate

Follow `docs/local/CTA-PILOT-PREP-003_MAC_MINI_OPENCODE.md`. The local gate must use the accepted frozen production model profile, loopback-only endpoints and the existing browser workflows. It must not modify the synthetic fixture to make the result look better.

## Stop conditions

Stop and record a failure when any of these occurs:

- outcome plaintext is visible before the corresponding diagnostic revision is frozen;
- a frozen output is overwritten instead of creating a new revision;
- missing counts or rates are inferred;
- probable/uncertain linkage becomes exact without direct evidence;
- two reviewer identities collapse into one stream;
- adjudicator is one of the basis reviewers;
- unresolved or stale disagreement is presented as completed review;
- dashboard/report labels a synthetic metric as validated model accuracy;
- an external API, telemetry endpoint or non-loopback model endpoint is contacted.
