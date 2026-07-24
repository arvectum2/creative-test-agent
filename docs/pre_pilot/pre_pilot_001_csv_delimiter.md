# PRE-PILOT-001 — deterministic delimiter selection

## Problem

A semicolon-delimited client export could be misclassified as comma-delimited when every row also contained an ordinary comma, for example in `CTR, %` and decimal-comma values such as `2,1%`.

## Resolution

Delimiter selection now evaluates comma, semicolon, tab and pipe candidates by the amount of consistent non-trivial tabular structure each candidate produces. `csv.Sniffer` remains only a tie-breaker. The parser does not require commas to be quoted when comma is not the delimiter.

## Acceptance evidence

Regression coverage verifies the ambiguous semicolon case, ordinary comma/semicolon/tab/pipe files and quoted commas in a comma-delimited file. The parser version is `1.0.2`.
