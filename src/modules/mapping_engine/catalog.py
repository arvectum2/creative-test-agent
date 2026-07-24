from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

ENGINE_NAME = "deterministic_column_mapper"
ENGINE_VERSION = "1.0.0"
MIN_SUGGESTION_CONFIDENCE = 0.35
AUTO_SUGGEST_CONFIDENCE = 0.55
MAX_SUGGESTIONS_PER_COLUMN = 3


@dataclass(frozen=True)
class Alias:
    value: str
    weight: float = 1.0


@dataclass(frozen=True)
class TargetFieldDefinition:
    key: str
    label: str
    description: str
    expected_types: tuple[str, ...]
    aliases: tuple[Alias, ...]


TARGET_FIELDS: tuple[TargetFieldDefinition, ...] = (
    TargetFieldDefinition(
        key="campaign_reference",
        label="Campaign reference",
        description="Client campaign identifier or campaign name.",
        expected_types=("text", "mixed", "integer"),
        aliases=(
            Alias("campaign"), Alias("campaign name"), Alias("campaign id"),
            Alias("кампания"), Alias("название кампании"), Alias("название рк"),
            Alias("рк", 0.92), Alias("id кампании"), Alias("номер кампании"),
        ),
    ),
    TargetFieldDefinition(
        key="creative_reference",
        label="Creative reference",
        description="Creative, banner, asset identifier or source filename.",
        expected_types=("text", "mixed", "integer"),
        aliases=(
            Alias("creative"), Alias("creative id"), Alias("creative name"),
            Alias("asset"), Alias("asset id"), Alias("banner"), Alias("banner id"),
            Alias("filename"), Alias("file name"), Alias("макет"), Alias("креатив"),
            Alias("баннер"), Alias("имя файла"), Alias("файл креатива"),
        ),
    ),
    TargetFieldDefinition(
        key="platform",
        label="Platform",
        description="Media platform, marketplace, search or advertising system.",
        expected_types=("text", "mixed"),
        aliases=(
            Alias("platform"), Alias("media platform"), Alias("ad platform"),
            Alias("площадка"), Alias("медиаплощадка"), Alias("рекламная система"),
            Alias("источник", 0.72), Alias("source", 0.68),
        ),
    ),
    TargetFieldDefinition(
        key="placement_type",
        label="Placement type",
        description="Placement, inventory, position or advertising block type.",
        expected_types=("text", "mixed"),
        aliases=(
            Alias("placement"), Alias("placement type"), Alias("inventory"),
            Alias("inventory type"), Alias("position", 0.78), Alias("ad position"),
            Alias("размещение"), Alias("тип размещения"), Alias("место размещения"),
            Alias("тип блока"), Alias("позиция", 0.78),
        ),
    ),
    TargetFieldDefinition(
        key="format",
        label="Format",
        description="Creative or placement format, dimensions or banner size.",
        expected_types=("text", "mixed", "integer"),
        aliases=(
            Alias("format"), Alias("creative format"), Alias("banner format"),
            Alias("banner size"), Alias("size", 0.78), Alias("dimensions"),
            Alias("формат"), Alias("формат баннера"), Alias("размер баннера"),
            Alias("размер", 0.78), Alias("габариты"),
        ),
    ),
    TargetFieldDefinition(
        key="date",
        label="Date",
        description="Observation date, day or reporting period value.",
        expected_types=("date", "datetime", "text", "mixed"),
        aliases=(
            Alias("date"), Alias("day"), Alias("observation date"),
            Alias("report date"), Alias("дата"), Alias("день"),
            Alias("дата отчета"), Alias("период", 0.72), Alias("period", 0.72),
        ),
    ),
    TargetFieldDefinition(
        key="impressions",
        label="Impressions",
        description="Number of served or counted advertising impressions.",
        expected_types=("integer", "number", "formula", "text", "mixed"),
        aliases=(
            Alias("impressions"), Alias("impression"), Alias("ad impressions"),
            Alias("показы"), Alias("показов"), Alias("количество показов"),
            Alias("views", 0.62), Alias("просмотры", 0.58),
        ),
    ),
    TargetFieldDefinition(
        key="clicks",
        label="Clicks",
        description="Number of counted clicks or transitions.",
        expected_types=("integer", "number", "formula", "text", "mixed"),
        aliases=(
            Alias("clicks"), Alias("click"), Alias("ad clicks"),
            Alias("клики"), Alias("кликов"), Alias("количество кликов"),
            Alias("переходы", 0.88), Alias("transitions", 0.82),
            Alias("interactions", 0.58), Alias("взаимодействия", 0.52),
        ),
    ),
    TargetFieldDefinition(
        key="ctr",
        label="CTR",
        description="Click-through rate supplied by the source; it is not recalculated here.",
        expected_types=("integer", "number", "formula", "text", "mixed"),
        aliases=(
            Alias("ctr"), Alias("ctr percent"), Alias("click through rate"),
            Alias("click-through rate"), Alias("click rate"),
            Alias("кликабельность"), Alias("коэффициент кликабельности"),
            Alias("процент кликов"),
        ),
    ),
    TargetFieldDefinition(
        key="audience",
        label="Audience",
        description="Audience, targeting or segment reference.",
        expected_types=("text", "mixed", "integer"),
        aliases=(
            Alias("audience"), Alias("audience segment"), Alias("segment"),
            Alias("targeting"), Alias("target audience"), Alias("аудитория"),
            Alias("сегмент"), Alias("таргетинг"), Alias("целевая аудитория"),
        ),
    ),
    TargetFieldDefinition(
        key="brand",
        label="Brand",
        description="Brand or trademark reference.",
        expected_types=("text", "mixed", "integer"),
        aliases=(
            Alias("brand"), Alias("brand name"), Alias("trademark"),
            Alias("бренд"), Alias("название бренда"), Alias("торговая марка"),
        ),
    ),
    TargetFieldDefinition(
        key="product",
        label="Product",
        description="Product, SKU or advertised item reference.",
        expected_types=("text", "mixed", "integer"),
        aliases=(
            Alias("product"), Alias("product name"), Alias("product id"),
            Alias("sku"), Alias("item"), Alias("продукт"), Alias("товар"),
            Alias("название продукта"), Alias("наименование товара"),
        ),
    ),
)

TARGET_FIELD_BY_KEY = {item.key: item for item in TARGET_FIELDS}


@dataclass(frozen=True)
class CandidateScore:
    target_field: str
    confidence: float
    method: str
    explanation: dict[str, Any]


def public_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": definition.key,
            "label": definition.label,
            "description": definition.description,
            "expected_types": list(definition.expected_types),
        }
        for definition in TARGET_FIELDS
    ]


def normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower().replace("ё", "е")
    text = text.replace("%", " percent ")
    text = re.sub(r"__\d+$", "", text)
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def score_column(
    *,
    source_header: str | None,
    normalized_header: str,
    inferred_type: str,
    sample_values: list[Any],
    profile_targets: dict[str, tuple[str, str | None]] | None = None,
) -> list[CandidateScore]:
    source_key = normalized_header.strip().lower()
    lexical_header = normalize_text(source_header or normalized_header)
    profile_targets = profile_targets or {}

    profile_match = profile_targets.get(source_key)
    if profile_match:
        target_field, profile_type = profile_match
        compatible = _type_compatible(inferred_type, TARGET_FIELD_BY_KEY[target_field])
        confidence = 0.995 if compatible else 0.90
        return [
            CandidateScore(
                target_field=target_field,
                confidence=confidence,
                method="profile_exact",
                explanation={
                    "profile_match": source_key,
                    "source_type": inferred_type,
                    "profile_source_type": profile_type,
                    "type_compatible": compatible,
                    "reason": "Exact source-column key matched a confirmed mapping profile rule.",
                },
            )
        ]

    candidates: list[CandidateScore] = []
    for definition in TARGET_FIELDS:
        lexical_score, alias, lexical_method = _best_alias_score(lexical_header, definition)
        type_adjustment = _type_adjustment(inferred_type, definition)
        sample_adjustment, sample_reasons = _sample_adjustment(
            definition.key, lexical_header, sample_values, inferred_type
        )
        confidence = max(0.0, min(1.0, lexical_score + type_adjustment + sample_adjustment))
        method = lexical_method
        if sample_adjustment > 0 and lexical_score < 0.45:
            method = "sample_signal"
        explanation = {
            "matched_alias": alias,
            "lexical_score": round(lexical_score, 4),
            "lexical_method": lexical_method,
            "source_type": inferred_type,
            "expected_types": list(definition.expected_types),
            "type_adjustment": round(type_adjustment, 4),
            "sample_adjustment": round(sample_adjustment, 4),
            "sample_reasons": sample_reasons,
        }
        candidates.append(
            CandidateScore(
                target_field=definition.key,
                confidence=round(confidence, 6),
                method=method,
                explanation=explanation,
            )
        )

    candidates.sort(key=lambda item: (-item.confidence, item.target_field))
    return [item for item in candidates if item.confidence >= MIN_SUGGESTION_CONFIDENCE][
        :MAX_SUGGESTIONS_PER_COLUMN
    ]


def _best_alias_score(
    header: str,
    definition: TargetFieldDefinition,
) -> tuple[float, str | None, str]:
    if not header:
        return 0.0, None, "none"

    canonical = normalize_text(definition.key)
    if header == canonical:
        return 0.98, definition.key, "canonical_exact"

    best_score = 0.0
    best_alias: str | None = None
    best_method = "none"
    header_tokens = set(header.split())

    for alias in definition.aliases:
        normalized_alias = normalize_text(alias.value)
        if not normalized_alias:
            continue
        if header == normalized_alias:
            score, method = 0.94 * alias.weight, "alias_exact"
        else:
            alias_tokens = set(normalized_alias.split())
            overlap = len(header_tokens & alias_tokens) / max(len(header_tokens | alias_tokens), 1)
            sequence = SequenceMatcher(None, header, normalized_alias).ratio()
            contains = 0.82 if normalized_alias in header or header in normalized_alias else 0.0
            score = max(sequence * 0.72, overlap * 0.82, contains) * alias.weight
            method = "alias_fuzzy"
        if score > best_score:
            best_score = score
            best_alias = alias.value
            best_method = method

    return best_score, best_alias, best_method


def _type_compatible(source_type: str, definition: TargetFieldDefinition) -> bool:
    return source_type in definition.expected_types or source_type in {"mixed", "empty"}


def _type_adjustment(source_type: str, definition: TargetFieldDefinition) -> float:
    if source_type == "empty":
        return -0.25
    if source_type in definition.expected_types:
        return 0.05
    if source_type == "mixed":
        return 0.0
    if definition.key == "date" and source_type in {"date", "datetime"}:
        return 0.18
    if definition.key in {"impressions", "clicks", "ctr"} and source_type in {
        "integer", "number", "formula"
    }:
        return 0.04
    return -0.08


def _sample_adjustment(
    target_field: str,
    header: str,
    sample_values: list[Any],
    inferred_type: str,
) -> tuple[float, list[str]]:
    samples = [str(value).strip() for value in sample_values if value not in (None, "")]
    reasons: list[str] = []
    adjustment = 0.0

    if target_field == "date" and inferred_type in {"date", "datetime"}:
        adjustment += 0.16
        reasons.append("source type is date-like")

    if target_field == "ctr" and (
        "percent" in header or any("%" in value for value in samples)
    ):
        adjustment += 0.14
        reasons.append("header or sample values contain a percent marker")

    if target_field == "format" and any(
        re.search(r"\b\d{2,4}\s*[xх×]\s*\d{2,4}\b", value.lower()) for value in samples
    ):
        adjustment += 0.14
        reasons.append("sample values look like banner dimensions")

    if target_field == "creative_reference" and any(
        re.search(r"\.(png|jpe?g|webp|gif|pdf|html?)$", value.lower()) for value in samples
    ):
        adjustment += 0.16
        reasons.append("sample values look like creative filenames")

    if target_field == "platform" and any(
        re.search(
            r"\b(yandex|яндекс|google|гугл|ozon|озон|wildberries|wb|avito|авито|vk|вк|mytarget|telegram)\b",
            value.lower(),
        )
        for value in samples
    ):
        adjustment += 0.13
        reasons.append("sample values contain known media-platform names")

    return adjustment, reasons
