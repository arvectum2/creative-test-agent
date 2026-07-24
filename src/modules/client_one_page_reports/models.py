from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.db.base import Base


class ClientOnePageReportStatus(StrEnum):
    completed = "completed"
    failed = "failed"


class ClientOnePageReportRun(Base):
    __tablename__ = "client_one_page_report_run"
    __table_args__ = (
        UniqueConstraint(
            "data_quality_run_id",
            "generator_version",
            "input_fingerprint",
            "run_number",
            name="uq_client_one_page_report_input_version_number",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    data_quality_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    prediction_readiness_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    quantitative_study_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_table_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    import_session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    client_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    generator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    generator_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ClientOnePageReportStatus.completed, index=True
    )
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="ru")
    verdict: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    bundle_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    artifacts_json: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    manifest_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    slide_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
