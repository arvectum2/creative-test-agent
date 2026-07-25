# UI-PILOT-001 acceptance

The increment is accepted only when an isolated browser regression proves that an operator can create a pilot, upload an as-is client CSV and a creative, inspect the table, confirm mappings, normalize, run Data Quality, handle clarification questions, evaluate capability readiness and download both report families.

The final branch must also pass the complete regression suite and all existing PRE-PILOT/PRE-TZ executable gates with `contents: read` permissions.

The browser regression must use synthetic materials only and must not rely on direct UUID entry, JSON input, API clients or terminal commands in the operator path.

This acceptance does not assert model accuracy, causal lift, market effectiveness, regulatory approval or successful human usability testing with an external operator.
