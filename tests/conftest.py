import pytest
from sqlalchemy.pool import StaticPool

from src.shared.db.session import init_db, reset_engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    reset_engine(
        url="sqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    init_db()
    yield


@pytest.fixture(autouse=True)
def default_legacy_ui_tests_to_english(monkeypatch):
    """Keep pre-i18n UI assertions deterministic without changing product defaults.

    Explicit ``?lang=`` parameters and language cookies still take precedence, so
    localization tests can exercise both supported locales. Requests that do not
    specify a locale use English because the legacy UI test suite asserts the
    original English labels.
    """
    import src.modules.ui.router as ui_router

    original_detect_lang = ui_router._detect_lang

    def detect_lang(request):
        query_lang = request.query_params.get("lang", "")
        cookie_lang = request.cookies.get("lang", "")
        if query_lang in ("ru", "en") or cookie_lang in ("ru", "en"):
            return original_detect_lang(request)
        return "en"

    monkeypatch.setattr(ui_router, "_detect_lang", detect_lang)
