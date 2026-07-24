from __future__ import annotations

import hashlib
from pathlib import Path

from src.modules.client_one_page_reports.models import ClientOnePageReportRun
from src.shared.config.settings import get_settings
from src.shared.db.repository import db_session, json_loads
from src.shared.errors import AppError
from src.shared.security.hardening import ensure_within_root


def secure_client_one_page_artifact_path(
    report_id: str,
    artifact_type: str,
) -> tuple[Path, str, str]:
    with db_session() as db:
        model = (
            db.query(ClientOnePageReportRun)
            .filter(ClientOnePageReportRun.id == report_id)
            .first()
        )
        if model is None:
            raise AppError("client_one_page_report_not_found", "Client one-page report not found", 404)
        if artifact_type == "manifest":
            path_value = model.manifest_storage_path
            filename = model.manifest_filename
            expected_sha = model.manifest_sha256
            media_type = "application/json"
        else:
            artifacts = json_loads(model.artifacts_json)
            artifacts = artifacts if isinstance(artifacts, list) else []
            artifact = next(
                (item for item in artifacts if item.get("artifact_type") == artifact_type),
                None,
            )
            if artifact is None:
                raise AppError(
                    "client_one_page_artifact_not_found",
                    "Requested report artifact is not available",
                    404,
                )
            path_value = artifact.get("storage_path", "")
            filename = artifact.get("filename", "report.bin")
            expected_sha = artifact.get("sha256", "")
            media_type = artifact.get("media_type", "application/octet-stream")
        try:
            path = ensure_within_root(path_value, get_settings().storage_root)
        except ValueError as exc:
            raise AppError(
                "client_one_page_report_path_escape",
                "Stored report artifact is outside the configured storage root",
                409,
            ) from exc
        if not path.is_file():
            raise AppError(
                "client_one_page_report_missing",
                "Stored report artifact is missing",
                409,
            )
        if _sha256_file(path) != expected_sha:
            raise AppError(
                "client_one_page_report_corrupted",
                "Stored report artifact failed SHA-256 verification",
                409,
            )
        return path, filename, media_type


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
