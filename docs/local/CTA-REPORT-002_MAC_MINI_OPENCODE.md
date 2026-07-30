# CTA-REPORT-002 — local real-project check

The implementation and synthetic visual acceptance are complete. Real client files remain local and must not be committed.

## Run

```bash
python scripts/client_report_v2.py generate --project-id <ozon-project-id> --locale ru
```

Use the returned `report_id` to download all artifacts from the API or open the generated bundle under the configured `CTA_STORAGE_ROOT/client_report_v2` directory.

## Real-project checklist

- confirm every displayed finding has resolvable evidence references;
- compare asset filenames and linkage status against the campaign evidence workspace;
- verify campaign-level outcomes are never printed as asset-level outcomes;
- verify missing CG/TG cells remain blank/missing;
- inspect every PPTX slide in PowerPoint or LibreOffice;
- inspect every DOCX page at 100% zoom;
- open the XLSX appendix and confirm filters, wrapped text and evidence references;
- record expert verdicts only after an actual reviewer supplies them.

A different result on real data is a new evidence state, not permission to weaken the claim boundary.
