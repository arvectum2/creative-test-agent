# PRE-PILOT-003 — Local OCR/VLM Benchmark

Status: implemented benchmark harness; real candidate runs remain local-machine work.

## Purpose

This stage turns the PRE-PILOT-002 Synthetic Creative Golden Pack into an executable comparison harness for local OCR, local VLM and hybrid configurations before any client creative is received.

The benchmark measures only:

- text extraction against visible synthetic text;
- recognition of explicitly labelled observable properties;
- abstention;
- repeatability across repeated runs;
- wall-clock latency;
- runner-process CPU time and peak RSS;
- Ollama-compatible server timing counters when the endpoint returns them.

It does not measure or claim CTR, causal creative lift, market effectiveness, respondent reaction, pharmaceutical compliance, client-level accuracy or production readiness.

## Candidate types

Supported candidate specifications:

```text
ocr:tesseract
vlm:<local-model-name>
hybrid:<local-model-name>
```

VLM and hybrid candidates use an Ollama-compatible `/api/chat` endpoint. The benchmark accepts loopback URLs only, such as `http://127.0.0.1:11434` or `http://localhost:11434`. Remote or cloud endpoints are rejected.

The `fixture:golden-contract` candidate exists only for an executable harness self-test. It receives the expected contract directly, is marked `harness_only=true`, is excluded from selection and must never be reported as a model result.

## Metrics

### OCR text quality

Expected text is derived from fields that are visibly rendered in each synthetic case. Tokens are compared as multisets.

- precision: matched tokens divided by detected tokens;
- recall: matched tokens divided by expected visible tokens;
- F1: harmonic mean of precision and recall;
- case abstention: no detected text.

### Observable quality

Only explicit golden slots for the current case are scored. Shared evidence-boundary flags are excluded.

Allowed predictions:

```text
present
absent
review_required
uncertain
```

`uncertain` and missing values count as abstentions.

- precision: correct answered slots divided by answered slots;
- recall: correct slots divided by all evaluated golden slots;
- F1: harmonic mean;
- abstention rate: unanswered slots divided by evaluated slots;
- per-observable precision, recall, F1 and abstention are also recorded.

Both first-pass and repeated-run consensus metrics are stored. A tied consensus becomes `uncertain`.

### Repeatability

- OCR: exact normalized-text repeat rate and mean pairwise token Jaccard;
- VLM: exact case-level repeat rate and mean modal agreement across scored observable slots.

### Performance and resources

Every run records:

- wall-clock latency;
- benchmark-process CPU time;
- benchmark-process peak RSS before and after the call;
- optional model-server durations and token counters returned by the local Ollama-compatible endpoint.

Peak RSS does not include a separate model-server process. The report states this limitation explicitly.

## Harness self-test

```bash
python scripts/benchmark_local_vision.py self-test \
  --output .ci/pre-pilot-003-self-test

python scripts/benchmark_local_vision.py validate \
  --input .ci/pre-pilot-003-self-test
```

The self-test generates the golden pack, runs the harness-only fixture twice, requires text and observable F1 equal to 1.0, validates artifact hashes and confirms that no model was selected.

## Running real local candidates

Tesseract only:

```bash
python scripts/benchmark_local_vision.py run \
  --candidate ocr:tesseract \
  --repeats 3 \
  --output data/generated/vision_benchmarks/tesseract
```

Local VLM and hybrid comparison:

```bash
python scripts/benchmark_local_vision.py run \
  --candidate vlm:<model-name> \
  --candidate hybrid:<model-name> \
  --base-url http://127.0.0.1:11434 \
  --repeats 3 \
  --output data/generated/vision_benchmarks/<run-name>
```

`--require-available` turns an unavailable requested candidate into a non-zero exit status. Without it, an unavailable model is preserved as an explicit benchmark result rather than silently omitted.

## Output

```text
benchmark_results.json   complete per-case and per-repeat evidence
benchmark_summary.csv    flat candidate comparison
benchmark_report.md      readable limitations-first report
benchmark_manifest.json  SHA-256 and size for every report artifact
```

The result always records:

```text
synthetic_creatives_only = true
market_effectiveness_not_evaluated = true
real_respondents_used = false
prediction_generated = false
model_selected = false
```

## Selection boundary

PRE-PILOT-003 does not automatically approve a model or define a universal pass threshold. A real local run may make a candidate eligible for human comparison, but final configuration still requires:

- review of observable-level errors;
- acceptable abstention and repeatability;
- acceptable latency and hardware load;
- testing of PNG/PDF/PPTX transformations in a later stage;
- expert review and real-client calibration;
- a locked holdout before any client-facing accuracy claim.

The golden-contract fixture is never eligible for model selection.
