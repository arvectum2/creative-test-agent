"""Read model for the unified pilot workspace screen."""

from __future__ import annotations

from typing import Any

from src.modules.clients.service import get_client
from src.modules.creative_assets.service import list_assets
from src.modules.data_quality.service import get_latest_data_quality_report
from src.modules.import_sessions.service import (
    list_import_sessions,
    list_source_files,
    verify_import_session,
)
from src.modules.import_sessions.tabular_service import (
    get_latest_source_inspection,
    list_source_tables,
)
from src.modules.mapping_engine.service import get_table_mapping
from src.modules.normalized_data.service import get_latest_normalization
from src.modules.pilot_workspace.helpers import is_tabular, require_project
from src.modules.prediction_readiness.service import get_latest_prediction_readiness


def load_workspace(project_id: str) -> dict[str, Any]:
    project = require_project(project_id)
    sessions = list_import_sessions(project_id=project_id)
    project_assets = [
        item
        for item in list_assets()
        if getattr(item, "project_id", None) == project_id
    ]
    session_cards, counts = _session_cards(sessions)
    return {
        "project": project,
        "client": get_client(project.client_id),
        "sessions": session_cards,
        "assets": project_assets,
        "progress": _progress(counts, bool(sessions or project_assets)),
        "counts": {
            "sessions": len(sessions),
            "assets": len(project_assets),
            **counts,
        },
    }


def _session_cards(sessions) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = {
        "tables": 0,
        "mapped_tables": 0,
        "normalized_tables": 0,
        "quality_tables": 0,
        "ready_tables": 0,
    }
    cards = []
    for session in sorted(
        sessions,
        key=lambda item: item.created_at or "",
        reverse=True,
    ):
        files = list_source_files(session.id)
        cards.append(
            {
                "session": session,
                "files": [_file_card(session.id, source, counts) for source in files],
                "integrity": (
                    verify_import_session(session.id)
                    if session.status == "completed"
                    else None
                ),
            }
        )
    return cards, counts


def _file_card(session_id: str, source, counts: dict[str, int]) -> dict[str, Any]:
    inspection = get_latest_source_inspection(session_id, source.id)
    tables = (
        list_source_tables(session_id, source.id)
        if inspection is not None and inspection.status == "completed"
        else []
    )
    return {
        "source": source,
        "inspection": inspection,
        "tables": [
            _table_card(session_id, source.id, table, counts)
            for table in tables
        ],
        "tabular": is_tabular(source.original_filename),
    }


def _table_card(
    session_id: str,
    source_file_id: str,
    table,
    counts: dict[str, int],
) -> dict[str, Any]:
    counts["tables"] += 1
    mapping = get_table_mapping(session_id, source_file_id, table.id)
    normalization = get_latest_normalization(session_id, source_file_id, table.id)
    quality = get_latest_data_quality_report(session_id, source_file_id, table.id)
    readiness = (
        get_latest_prediction_readiness(quality.run.id)
        if quality is not None
        else None
    )
    counts["mapped_tables"] += int(bool(mapping.confirmed_columns))
    counts["normalized_tables"] += int(normalization is not None)
    counts["quality_tables"] += int(quality is not None)
    counts["ready_tables"] += int(readiness is not None)
    return {
        "table": table,
        "mapping": mapping,
        "normalization": normalization,
        "quality": quality,
        "readiness": readiness,
    }


def _progress(counts: dict[str, int], has_materials: bool) -> dict[str, bool]:
    tables = counts["tables"]
    return {
        "project": True,
        "materials": has_materials,
        "inspection": tables > 0,
        "mapping": tables > 0 and counts["mapped_tables"] == tables,
        "normalization": tables > 0 and counts["normalized_tables"] == tables,
        "quality": tables > 0 and counts["quality_tables"] == tables,
        "readiness": tables > 0 and counts["ready_tables"] == tables,
    }
