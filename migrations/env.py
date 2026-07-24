from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from src.shared.config.settings import get_settings
from src.shared.db.base import Base

# Ensure all models are registered with Base.metadata. Keep this list aligned
# with src.shared.db.session.init_db; scripts/check_model_registry.py enforces it.
import src.modules.audit_log.models  # noqa: F401
import src.modules.audience_profiles.models  # noqa: F401
import src.modules.brand_profiles.models  # noqa: F401
import src.modules.creative_assets.models  # noqa: F401
import src.modules.report_generator.models  # noqa: F401
import src.modules.test_rubrics.models  # noqa: F401
import src.modules.test_runs.models  # noqa: F401
import src.modules.users.models  # noqa: F401
import src.modules.clients.models  # noqa: F401
import src.modules.projects.models  # noqa: F401
import src.modules.brandbooks.models  # noqa: F401
import src.modules.knowledge_base.models  # noqa: F401
import src.modules.export_jobs.models  # noqa: F401
import src.modules.model_profiles.models  # noqa: F401
import src.modules.prompt_registry.models  # noqa: F401
import src.modules.evaluations.models  # noqa: F401
import src.modules.prompt_traces.models  # noqa: F401
import src.modules.reviews.models  # noqa: F401
import src.modules.job_queue.models  # noqa: F401
import src.modules.batches.models  # noqa: F401
import src.modules.import_sessions.models  # noqa: F401
import src.modules.mapping_engine.models  # noqa: F401
import src.modules.normalized_data.models  # noqa: F401
import src.modules.data_quality.models  # noqa: F401
import src.modules.clarifications.models  # noqa: F401
import src.modules.prediction_readiness.models  # noqa: F401
import src.modules.quantitative_surveys.models  # noqa: F401
import src.modules.data_review_reports.models  # noqa: F401
import src.modules.client_one_page_reports.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    ini_url = config.get_main_option("sqlalchemy.url")
    default_url = "sqlite:///./creative_test_agent.db"
    if ini_url and ini_url != default_url:
        return ini_url
    try:
        return get_settings().database_url
    except Exception:
        return default_url


def run_migrations_offline() -> None:
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
