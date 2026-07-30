# Evidence-Bound Client Report v2

`CTA-REPORT-002` turns the Ozon campaign evidence workspace into the main pilot client report while keeping five evidence layers separate:

1. observed campaign and asset facts;
2. agent diagnostics;
3. factual CG/TG outcomes;
4. expert assessment;
5. limitations and confidence.

## Safety semantics

Agent findings are asset-level diagnostic outputs. CG/TG observations are campaign-set facts. The report never maps a campaign-level outcome to one asset, never fills missing values and never converts descriptive CG/TG difference into causal lift or a prediction.

Each finding receives a stable ID and evidence references. At minimum, the references identify the source test-run finding and the creative record. Visual evidence references emitted by the diagnostic pipeline are preserved and registered separately.

Expert assessment is supplied explicitly. If no assessment exists for a finding, the exported row is `not_reviewed`; no expert verdict is synthesized.

## API

```text
POST /campaign-evidence/reports-v2/projects/{project_id}
GET  /campaign-evidence/reports-v2/projects/{project_id}/{report_id}
GET  /campaign-evidence/reports-v2/projects/{project_id}/{report_id}/download?artifact=...
```

Generate request:

```json
{
  "locale": "ru",
  "force": false,
  "expert_assessments": [
    {
      "finding_id": "finding:test-run-id:1",
      "verdict": "supported",
      "rationale": "Evidence and wording were checked.",
      "reviewer_role": "senior strategist",
      "confidence": 0.9
    }
  ]
}
```

Artifact values:

```text
html
one_page_pptx
full_pptx
docx
evidence
xlsx
manifest
```

Downloads are constrained to the configured storage root and SHA-256 checked before delivery.

## CLI

```bash
python scripts/client_report_v2.py self-test --output .ci/cta-report-002
python scripts/client_report_v2.py validate --input .ci/cta-report-002
python scripts/client_report_v2.py check-determinism
python scripts/client_report_v2.py generate --project-id <project-id> --locale ru
```

## Bundle

```text
client_report_v2.html
client_report_v2_one_page.pptx
client_report_v2_full.pptx
client_report_v2.docx
client_report_v2_evidence.json
client_report_v2_appendix.xlsx
report_manifest.json
```

The manifest records report identity/version, project and input fingerprint, summary, claim boundary, media type, byte size and SHA-256 for every artifact.
