# Model Profiles

Model profiles define how the system connects to local LLM providers for inference. A DB connection profile is intentionally smaller than the CTA-MODEL-001 production profile: it stores the application connection, while the production profile also freezes model hashes, runtime versions, limits, topology and resources.

## Supported Providers

| Provider | Status | Base URL Default / contract |
|----------|--------|-----------------------------|
| `stub` | Built-in | N/A |
| `ollama` | Local | `http://localhost:11434` |
| `lmstudio` | Local | `http://localhost:1234` |
| `openai_compatible_local` | Local, loopback-only | Explicit URL ending in `/v1`, for example `http://127.0.0.1:8093/v1` |

Cloud providers remain forbidden by default.

## Configuration Files

Default profiles ship as JSON in `config/model_profiles/`:

- `stub.json` — enabled, default for deterministic tests and demos;
- `ollama.example.json` — template for Ollama;
- `lmstudio.example.json` — template for LM Studio;
- `cta-model-001-llm.example.json` — analytical LLM connection derived from CTA-MODEL-001.

Files ending in `.example.json` are not loaded. Copy a template to a normal `.json` file only after its local runtime and model identity are accepted.

### Loading from config

```bash
curl -X POST http://localhost:8000/model-profiles/load-from-config
```

The loader scans `config/model_profiles/*.json`, skips `.example.json`, and performs an idempotent upsert by `profile_name`.

The response is explicit:

```json
{
  "loaded": [
    {
      "file": "stub.json",
      "profile_name": "stub",
      "profile_id": "...",
      "action": "created"
    }
  ],
  "errors": [],
  "ok": true
}
```

A second load updates the same profile instead of creating a duplicate. Parsing, provider-policy and database failures appear in `errors`; they are no longer silently swallowed.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/model-profiles` | List all profiles |
| POST | `/model-profiles` | Create a profile; duplicate names are rejected |
| GET | `/model-profiles/{id}` | Get profile by ID |
| POST | `/model-profiles/{id}/health` | Check reachability and, where supported, model identity |
| POST | `/model-profiles/load-from-config` | Idempotently load non-example JSON profiles |

## Health Check

`POST /model-profiles/{id}/health` behaves as follows:

- **stub**: always reachable;
- **ollama / lmstudio**: checks the configured loopback endpoint;
- **openai_compatible_local**: calls `{base_url}/models` and requires the configured explicit model ID to be present in the response;
- **forbidden provider or non-loopback URL**: unreachable with a visible warning.

Reachability alone is not sufficient for `openai_compatible_local`: serving a different model or quantization is an identity failure.

## Provider Policy

Allowed:

```text
stub
ollama
lmstudio
openai_compatible_local
```

Forbidden include:

```text
openai
anthropic
gemini
perplexity
claude
azure_openai
```

All non-stub allowed providers require a loopback URL. An attempt to create a local provider with a non-loopback endpoint returns HTTP 400.

## CTA-MODEL-001 Production Profile

The canonical production contract is documented in:

```text
docs/model_profile/CTA-MODEL-001_PRODUCTION_PROFILE_RU.md
```

Files:

```text
config/model_profiles/production/cta_model_001.schema.json
config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.draft.json
```

The draft is safe for GitHub and contains explicit `null` values for measurements that must be recovered from the private local CTA-BENCH-002 artifact bundle. It cannot be used as a frozen deployment contract.

Validate and render application settings:

```bash
python scripts/cta_model_001.py validate \
  --mode draft \
  --profile config/model_profiles/production/cta_model_001.mac_mini_m4pro_24gb.draft.json

python scripts/cta_model_001.py render-env \
  --profile <PROFILE_JSON> \
  --output .local/cta-model-001/application.env
```

The full Mac mini freeze and acceptance procedure is in:

```text
docs/local/CTA-MODEL-001_MAC_MINI_OPENCODE.md
```

## UI

Navigate to `/ui/model-profiles` to list, create, view details, and check health. The UI manages DB connection profiles; it does not edit or seal the production manifest.
