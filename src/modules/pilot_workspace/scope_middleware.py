from __future__ import annotations

from starlette.responses import JSONResponse

from src.modules.clarifications.models import ClarificationQuestion, ClarificationRun
from src.modules.data_quality.models import DataQualityRun
from src.modules.import_sessions.models import ImportSession, ImportSourceFile, SourceInspection, SourceTable
from src.modules.projects.models import Project
from src.shared.db.repository import db_session


class PilotWorkspaceScopeMiddleware:
    """Reject cross-project ID substitution in operator workspace URLs.

    The browser UI does not ask operators to type UUIDs, but every nested route
    still carries identifiers. This middleware verifies the complete project /
    import-session / file / table / Data Quality / clarification chain before a
    request reaches the route handler.
    """

    _PREFIX = "/ui/pilot-workspaces"

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        if not path.startswith(self._PREFIX + "/"):
            await self.app(scope, receive, send)
            return

        parts = [item for item in path.split("/") if item]
        # /ui/pilot-workspaces and /ui/pilot-workspaces/new have no project scope.
        if len(parts) < 3 or parts[2] == "new":
            await self.app(scope, receive, send)
            return

        project_id = parts[2]
        if not _scope_is_valid(parts, project_id):
            response = JSONResponse(
                status_code=404,
                content={"detail": "Pilot workspace resource not found"},
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _scope_is_valid(parts: list[str], project_id: str) -> bool:
    with db_session() as db:
        if db.query(Project.id).filter(Project.id == project_id).first() is None:
            return False

        if len(parts) > 3 and parts[3] == "sessions":
            index = 3
            if len(parts) <= index + 1:
                return False
            session_id = parts[index + 1]
            session = (
                db.query(ImportSession.id)
                .filter(
                    ImportSession.id == session_id,
                    ImportSession.project_id == project_id,
                )
                .first()
            )
            if session is None:
                return False

            if "files" in parts:
                file_index = parts.index("files")
                if len(parts) <= file_index + 1:
                    return False
                file_id = parts[file_index + 1]
                source = (
                    db.query(ImportSourceFile.id)
                    .filter(
                        ImportSourceFile.id == file_id,
                        ImportSourceFile.import_session_id == session_id,
                        ImportSourceFile.project_id == project_id,
                    )
                    .first()
                )
                if source is None:
                    return False

                if "tables" in parts:
                    table_index = parts.index("tables")
                    if len(parts) <= table_index + 1:
                        return False
                    table_id = parts[table_index + 1]
                    table = (
                        db.query(SourceTable.id)
                        .join(SourceInspection, SourceInspection.id == SourceTable.inspection_id)
                        .filter(
                            SourceTable.id == table_id,
                            SourceTable.source_file_id == file_id,
                            SourceInspection.import_session_id == session_id,
                            SourceInspection.project_id == project_id,
                        )
                        .first()
                    )
                    if table is None:
                        return False

        # Only the top-level /{project_id}/data-quality/{run_id} family carries a
        # Data Quality run ID. The table action ending in /data-quality creates it.
        if len(parts) > 3 and parts[3] == "data-quality":
            index = 3
            if len(parts) <= index + 1:
                return False
            run_id = parts[index + 1]
            quality = (
                db.query(DataQualityRun.id)
                .filter(
                    DataQualityRun.id == run_id,
                    DataQualityRun.project_id == project_id,
                )
                .first()
            )
            if quality is None:
                return False

            if "questions" in parts:
                question_index = parts.index("questions")
                if len(parts) <= question_index + 1:
                    return False
                question_id = parts[question_index + 1]
                question = (
                    db.query(ClarificationQuestion.id)
                    .join(
                        ClarificationRun,
                        ClarificationRun.id == ClarificationQuestion.clarification_run_id,
                    )
                    .filter(
                        ClarificationQuestion.id == question_id,
                        ClarificationRun.data_quality_run_id == run_id,
                        ClarificationRun.project_id == project_id,
                    )
                    .first()
                )
                if question is None:
                    return False

        return True
