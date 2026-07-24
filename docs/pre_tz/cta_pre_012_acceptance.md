# CTA-PRE-012 acceptance checklist

- The demo runs in an isolated local workspace and never enables cloud LLM access.
- The input is a deliberately messy CSV, not a prescribed client template.
- Original bytes are stored through the immutable import-session path and pass SHA-256 verification.
- Inspection discovers the real header after preamble and blank rows.
- Mapping suggestions are generated before ten explicit analyst confirmations.
- Unknown source columns remain preserved rather than deleted or silently normalized.
- Normalization creates campaign, creative, media-context and performance records with provenance.
- Data-quality issues are retained and produce progressive client/analyst clarification batches when supported by evidence.
- Prediction readiness is capability-specific and does not generate a prediction or fabricate CTR.
- Quantitative responses are deterministic, labelled `synthetic` and explicitly marked as not real people.
- The generated XLSX review workbook includes readiness and quantitative evidence.
- The workbook is checked against its persisted SHA-256.
- A machine-readable manifest records every run identifier, status, safety claim and artifact hash.
- The complete demo is executed by mandatory CI after the normal regression suite.
