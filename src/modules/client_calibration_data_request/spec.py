from __future__ import annotations

from typing import Any

PACKAGE_ID = "creative-test-agent-client-calibration-data-request"
PACKAGE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"

HEADERS = [
    "schema_version", "record_id", "project_id", "campaign_id", "campaign_name",
    "asset_id", "asset_filename", "asset_sha256", "placement_id", "platform",
    "placement_name", "placement_format", "linkage_status", "linkage_missing_fields",
    "linkage_notes", "metric_name", "funnel_stage", "comparison_design",
    "measurement_basis", "metric_unit", "control_sample_count",
    "control_positive_count", "test_sample_count", "test_positive_count",
    "control_value", "test_value", "control_rate", "test_rate",
    "counts_unavailable_reason", "observation_start", "observation_end",
    "source_system", "source_record_id", "source_file_sha256",
    "causal_interpretation_allowed", "measurement_notes", "notes",
]

INTEGER_FIELDS = {
    "control_sample_count", "control_positive_count", "test_sample_count",
    "test_positive_count",
}
NUMBER_FIELDS = {"control_value", "test_value", "control_rate", "test_rate"}
BOOLEAN_FIELDS = {"causal_interpretation_allowed"}
DATE_FIELDS = {"observation_start", "observation_end"}
LINKAGE_IDS = {"campaign_id", "asset_id", "placement_id"}

ALLOWED = {
    "linkage_status": ["exact", "probable", "one_to_many", "uncertain", "missing", "rejected"],
    "funnel_stage": [
        "awareness", "ad_recall", "message_recall", "consideration", "preference",
        "purchase_intent", "action", "other",
    ],
    "comparison_design": ["control_test", "pre_post", "single_group", "other"],
    "measurement_basis": ["absolute_counts", "rates_only", "continuous_value", "not_available"],
    "metric_unit": ["proportion", "score", "count", "currency", "seconds", "other"],
    "causal_interpretation_allowed": ["false"],
}

REQUIRED_BASE = [
    "schema_version", "record_id", "project_id", "linkage_status", "metric_name",
    "funnel_stage", "comparison_design", "measurement_basis", "metric_unit",
    "observation_start", "observation_end", "source_system", "source_record_id",
    "causal_interpretation_allowed",
]

EXPECTED_INVALID_CODES = {
    "LINKAGE_ID_REQUIRED", "RATES_ONLY_REASON_REQUIRED", "INVALID_RATE_RANGE",
    "OBSERVATION_DATE_ORDER", "CAUSAL_INTERPRETATION_FORBIDDEN", "INVALID_SHA256",
}

GENERATED_FILES = (
    "calibration_data_request_template.xlsx",
    "calibration_data_request_template.csv",
    "calibration_data_request.schema.json",
    "data_dictionary.csv",
    "client_instruction_ru.md",
    "examples/valid_calibration_data.csv",
    "examples/invalid_calibration_data.csv",
    "examples/valid_calibration_data.json",
    "examples/invalid_calibration_data.json",
    "examples/valid_calibration_data.xlsx",
    "examples/invalid_calibration_data.xlsx",
)

# required, type, description, example
FIELD_META: dict[str, tuple[str, str, str, str]] = {
    "schema_version": ("yes", "string", "Must be 1.0.0.", "1.0.0"),
    "record_id": ("yes", "string", "Unique row identifier in this dataset.", "OBS-0001"),
    "project_id": ("yes", "string", "Client/project transfer identifier.", "CLIENT-PILOT-2026"),
    "campaign_id": ("conditional", "string", "Required for exact linkage.", "CMP-001"),
    "campaign_name": ("no", "string", "Human-readable campaign name.", "Theraflex Q3"),
    "asset_id": ("conditional", "string", "Required for exact linkage.", "AST-001"),
    "asset_filename": ("no", "string", "Original filename without forced renaming.", "theraflex_banner_01.png"),
    "asset_sha256": ("no", "sha256", "Creative-file SHA-256 when available.", "a" * 64),
    "placement_id": ("conditional", "string", "Required for exact linkage.", "PLC-001"),
    "platform": ("conditional", "string", "Required for exact linkage.", "Ozon"),
    "placement_name": ("conditional", "string", "Required for exact linkage.", "Product card banner"),
    "placement_format": ("no", "string", "Dimensions or inventory type.", "1200x400"),
    "linkage_status": ("yes", "enum", "Use exact only for documented linkage.", "exact"),
    "linkage_missing_fields": ("conditional", "string", "Semicolon-separated missing linkage IDs.", "asset_id;placement_id"),
    "linkage_notes": ("conditional", "string", "Required for non-exact linkage.", "Keys were not exported."),
    "metric_name": ("yes", "string", "Source metric name; keep funnel stages separate.", "ad_recall"),
    "funnel_stage": ("yes", "enum", "Metric's funnel stage.", "ad_recall"),
    "comparison_design": ("yes", "enum", "How control/test values relate.", "control_test"),
    "measurement_basis": ("yes", "enum", "absolute_counts preferred; rates_only needs reason.", "absolute_counts"),
    "metric_unit": ("yes", "enum", "Rates are decimals from 0 to 1.", "proportion"),
    "control_sample_count": ("conditional", "integer", "Control denominator.", "500"),
    "control_positive_count": ("conditional", "integer", "Control numerator.", "150"),
    "test_sample_count": ("conditional", "integer", "Test/exposed denominator.", "520"),
    "test_positive_count": ("conditional", "integer", "Test/exposed numerator.", "187"),
    "control_value": ("conditional", "number", "Continuous/count control value.", ""),
    "test_value": ("conditional", "number", "Continuous/count test value.", ""),
    "control_rate": ("no", "number 0..1", "Optional; must agree with counts.", "0.3"),
    "test_rate": ("no", "number 0..1", "Optional; must agree with counts.", "0.359615"),
    "counts_unavailable_reason": ("conditional", "string", "Required for rates_only.", "Rounded rates only."),
    "observation_start": ("yes", "date", "ISO date YYYY-MM-DD.", "2026-04-01"),
    "observation_end": ("yes", "date", "ISO date, not before start.", "2026-04-30"),
    "source_system": ("yes", "string", "System/file/study source.", "Ozon Brand Lift"),
    "source_record_id": ("yes", "string", "Stable source row/study key.", "BL-2026-001"),
    "source_file_sha256": ("no", "sha256", "Transferred source-file SHA-256.", "b" * 64),
    "causal_interpretation_allowed": ("yes", "boolean", "Must remain false.", "false"),
    "measurement_notes": ("conditional", "string", "Method/scale notes; required when unavailable.", "Observed comparison only."),
    "notes": ("no", "string", "Additional non-sensitive context.", ""),
}


def build_schema() -> dict[str, Any]:
    nullable_string = {"type": ["string", "null"]}
    identifier = {"type": ["string", "null"], "pattern": "^[A-Za-z0-9._:-]+$"}
    sha256 = {"type": ["string", "null"], "pattern": "^[0-9a-fA-F]{64}$"}
    properties: dict[str, Any] = {name: nullable_string for name in HEADERS}
    properties.update({
        "schema_version": {"const": SCHEMA_VERSION},
        "record_id": {"type": "string", "minLength": 1, "pattern": "^[A-Za-z0-9._:-]+$"},
        "project_id": {"type": "string", "minLength": 1, "pattern": "^[A-Za-z0-9._:-]+$"},
        "campaign_id": identifier, "asset_id": identifier, "placement_id": identifier,
        "asset_sha256": sha256, "source_file_sha256": sha256,
        "linkage_status": {"enum": ALLOWED["linkage_status"]},
        "funnel_stage": {"enum": ALLOWED["funnel_stage"]},
        "comparison_design": {"enum": ALLOWED["comparison_design"]},
        "measurement_basis": {"enum": ALLOWED["measurement_basis"]},
        "metric_unit": {"enum": ALLOWED["metric_unit"]},
        "causal_interpretation_allowed": {"const": False},
        "observation_start": {"type": "string", "format": "date"},
        "observation_end": {"type": "string", "format": "date"},
    })
    for name in INTEGER_FIELDS:
        properties[name] = {"type": ["integer", "null"], "minimum": 0}
    for name in NUMBER_FIELDS:
        properties[name] = {"type": ["number", "null"]}
    properties["control_rate"] = {"type": ["number", "null"], "minimum": 0, "maximum": 1}
    properties["test_rate"] = {"type": ["number", "null"], "minimum": 0, "maximum": 1}
    record = {
        "type": "object", "additionalProperties": False, "required": REQUIRED_BASE,
        "properties": properties,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://arvectum.local/schemas/client-calibration-data-request/1.0.0",
        "title": "Creative Test Agent client calibration data request",
        "type": "object", "additionalProperties": False,
        "required": ["schema_version", "records"],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "records": {"type": "array", "minItems": 1, "items": record},
        },
    }


def valid_record() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION, "record_id": "OBS-0001",
        "project_id": "CLIENT-PILOT-2026", "campaign_id": "CMP-001",
        "campaign_name": "Theraflex Q3", "asset_id": "AST-001",
        "asset_filename": "theraflex_banner_01.png", "asset_sha256": "a" * 64,
        "placement_id": "PLC-001", "platform": "Ozon",
        "placement_name": "Product card banner", "placement_format": "1200x400",
        "linkage_status": "exact", "linkage_missing_fields": None,
        "linkage_notes": None, "metric_name": "ad_recall", "funnel_stage": "ad_recall",
        "comparison_design": "control_test", "measurement_basis": "absolute_counts",
        "metric_unit": "proportion", "control_sample_count": 500,
        "control_positive_count": 150, "test_sample_count": 520,
        "test_positive_count": 187, "control_value": None, "test_value": None,
        "control_rate": 0.3, "test_rate": round(187 / 520, 6),
        "counts_unavailable_reason": None, "observation_start": "2026-04-01",
        "observation_end": "2026-04-30", "source_system": "Ozon Brand Lift",
        "source_record_id": "BL-2026-001", "source_file_sha256": "b" * 64,
        "causal_interpretation_allowed": False,
        "measurement_notes": "Observed CG/TG comparison; no individual-asset causal attribution.",
        "notes": "Synthetic example only.",
    }


def invalid_record() -> dict[str, Any]:
    row = valid_record()
    row.update({
        "record_id": "OBS-INVALID-1", "asset_id": None, "asset_sha256": "bad-sha",
        "placement_id": None, "platform": None, "placement_name": None,
        "linkage_status": "exact", "measurement_basis": "rates_only",
        "control_sample_count": None, "control_positive_count": None,
        "test_sample_count": None, "test_positive_count": None,
        "test_rate": 1.12, "counts_unavailable_reason": None,
        "observation_start": "2026-05-31", "observation_end": "2026-05-01",
        "causal_interpretation_allowed": True, "measurement_notes": None,
        "notes": "Intentionally invalid example.",
    })
    return row


def client_instruction() -> str:
    return """# Инструкция по заполнению пакета калибровочных данных

## Что передать

Заполните `calibration_data_request_template.xlsx` или CSV и передайте исходные
креативы и исходную выгрузку отдельно, без переименования. Один ряд — одна
метрика для связки `кампания → креатив → размещение → период`.

## Связь

Для `linkage_status=exact` обязательны `campaign_id`, `asset_id`,
`placement_id`, `platform` и `placement_name`. Если связь неизвестна, используйте
`missing`, перечислите отсутствующие ID в `linkage_missing_fields` и объясните
причину в `linkage_notes`. Не придумывайте идентификаторы.

## Counts предпочтительнее rates

Для долей передавайте denominators и positive counts по CG/TG. Доли указываются
от 0 до 1. Если есть только округлённые проценты, выберите `rates_only`, заполните
`counts_unavailable_reason` и примите предупреждение `COUNTS_PREFERRED`.

## Источник и границы

Даты — `YYYY-MM-DD`; `source_system` и `source_record_id` обязательны.
`causal_interpretation_allowed` всегда `false`: наблюдаемая разница не доказывает
causal brand lift и не разрешает individual-asset attribution.

## Проверка

```bash
python scripts/client_calibration_data_request_pack.py validate --input <file.xlsx>
```

Строгий режим блокирует и предупреждения: добавьте `--strict`.
Реальные клиентские материалы не коммитятся в GitHub и обрабатываются только
в локальном закрытом контуре.
"""
