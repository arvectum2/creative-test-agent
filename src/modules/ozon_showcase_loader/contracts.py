from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

LOADER_NAME = "ozon_showcase_loader"
ALLOWED_LINKAGE_STATUSES = {
    "exact",
    "probable",
    "one_to_many",
    "uncertain",
    "missing",
    "rejected",
}


class OzonShowcaseError(RuntimeError):
    """Raised when the local showcase package cannot be loaded safely."""


@dataclass(frozen=True)
class ParsedOutcome:
    case_id: str
    brand: str
    period_start: date | None
    period_end: date | None
    platform: str | None
    control_n: int | None
    test_n: int | None
    metric: str
    cg_rate: float | None
    tg_rate: float | None
    uplift_pp: float | None
    evidence_status: str
    source_sheet: str
    source_row_number: int
    source_payload: dict[str, Any]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedAsset:
    archive_path: str
    filename: str
    sha256: str
    content: bytes = field(repr=False)
    extension: str
    mime_type: str
    width: int | None
    height: int | None
    brand: str | None
    inferred_platform: str | None
    linked_case_id: str | None
    linkage_status: str
    linkage_confidence: float
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkbookParseResult:
    outcomes: list[ParsedOutcome]
    selected_sheet: str
    header_row_number: int
    layout: str
    warnings: list[str]


@dataclass(frozen=True)
class ShowcaseLoadResult:
    source_fingerprint: str
    mapping_version: str
    client_id: str | None
    project_id: str | None
    import_session_id: str | None
    normalization_run_id: str | None
    idempotent_reuse: bool
    campaign_count: int
    outcome_count: int
    creative_asset_count: int
    creative_record_count: int
    linkage_counts: dict[str, int]
    source_hashes: dict[str, str]
    warnings: list[str]
    limitations: list[dict[str, Any]]
    report_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
