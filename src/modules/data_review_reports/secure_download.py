from __future__ import annotations

import hashlib
from pathlib import Path

from src.modules.data_review_reports.models import DataReviewReportRun
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session
from src.shared.errors import AppError
from src.shared.security.hardening import ensure_within_root


def secure_data_review_report_path(report_id: str) -> tuple[Path, str]:
    with db_session() as db:
        model = (
            db.query(DataReviewReportRun)
            .filter(DataReviewReportRun.id == report_id)
            .first()
        )
        if model is None:
            raise AppError(
                "data_review_report_not_found",
                "Data-review report not found",
                404,
            )

        try:
            path = ensure_within_root(
                model.storage_path,
                get_settings().storage_root,
            )
        except ValueError as exc:
            raise AppError(
                "data_review_report_path_escape",
                "Stored report path is outside the configured storage root",
                409,
            ) from exc

        if not path.is_file():
            raise AppError(
                "data_review_report_missing",
                "Stored data-review report is missing",
                409,
            )
        if _sha256_file(path) != model.sha256:
            raise AppError(
                "data_review_report_corrupted",
                "Stored data-review report failed SHA-256 verification",
                409,
            )
        return path, model.filename


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
