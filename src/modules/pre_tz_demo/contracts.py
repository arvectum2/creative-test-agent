"""Internal value objects for the executable PRE-TZ demo pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class DemoFoundation:
    client: Any
    project: Any
    asset_a: Any
    asset_b: Any


@dataclass(frozen=True, slots=True)
class DemoImportedSource:
    completed_session: Any
    source_file: Any
    source_bytes: bytes
    integrity: Any
    inspection: Any
    table: Any
    table_detail: Any


@dataclass(frozen=True, slots=True)
class DemoAnalysis:
    confirmed_headers: list[str]
    mapping: Any
    normalization: Any
    quality: Any
    client_questions: Any
    analyst_questions: Any
    readiness: Any


@dataclass(frozen=True, slots=True)
class DemoSurvey:
    questionnaire: Any
    study: Any
    synthetic_responses: list[Any]
    results: Any


@dataclass(frozen=True, slots=True)
class DemoReport:
    record: Any
    path: Path
    filename: str
    verified_sha256: str


@dataclass(frozen=True, slots=True)
class DemoRun:
    foundation: DemoFoundation
    imported: DemoImportedSource
    analysis: DemoAnalysis
    survey: DemoSurvey
    report: DemoReport
