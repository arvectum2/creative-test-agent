from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.modules.auth import router as auth_router_module
from src.modules.auth import ui_router as auth_ui_router_module
from src.modules.data_review_reports.models import DataReviewReportRun
from src.modules.data_review_reports.secure_download import (
    secure_data_review_report_path,
)
from src.shared.config.settings import Settings, get_settings
from src.shared.db.repository import db_session
from src.shared.errors import AppError
from src.shared.security.config import security_fail_closed
from src.shared.security.hardening import (
    ensure_within_root,
    safe_download_name,
    validate_security_posture,
)
from src.shared.security.middleware import RequestBodyLimitMiddleware
from src.shared.security.rate_limit import login_rate_limiter


def test_security_posture_blocks_non_local_configuration(tmp_path):
    storage = tmp_path / "storage"
    exports = tmp_path / "exports"
    backups = tmp_path / "backups"
    for path in (storage, exports, backups):
        path.mkdir()
    settings = Settings(
        host="0.0.0.0",
        public_base_url="http://example.test:8000",
        local_only_mode=True,
        allow_cloud_llm=True,
        trusted_hosts="example.test",
        storage_root=str(storage),
        exports_root=str(exports),
        backup_root=str(backups),
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
    )

    posture = validate_security_posture(settings)

    assert posture.status == "blocked"
    failed = {item.key for item in posture.blocking_errors}
    assert {"local_bind", "local_public_base_url", "trusted_hosts", "cloud_llm_disabled"} <= failed


def test_auth_disabled_password_policy_is_not_a_false_warning(tmp_path):
    storage = tmp_path / "storage"
    exports = tmp_path / "exports"
    backups = tmp_path / "backups"
    for path in (storage, exports, backups):
        path.mkdir()
    settings = Settings(
        enable_auth=False,
        password_min_length=8,
        storage_root=str(storage),
        exports_root=str(exports),
        backup_root=str(backups),
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
    )

    posture = validate_security_posture(settings)
    password = next(item for item in posture.checks if item.key == "password_policy")

    assert password.status == "pass"
    assert posture.status == "hardened"


def test_invalid_security_boolean_keeps_fail_closed_default(monkeypatch):
    monkeypatch.setenv("CTA_SECURITY_FAIL_CLOSED", "typo")
    assert security_fail_closed() is True
    monkeypatch.setenv("CTA_SECURITY_FAIL_CLOSED", "false")
    assert security_fail_closed() is False


def test_storage_confinement_and_download_name(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "reports" / "report.xlsx"
    assert ensure_within_root(inside, root) == inside.resolve()
    with pytest.raises(ValueError):
        ensure_within_root(tmp_path / "outside.txt", root)
    assert safe_download_name("../../danger\x00.xlsx") == "_.._danger.xlsx"
    assert safe_download_name("   ", "fallback.bin") == "fallback.bin"


def test_report_path_is_confined_before_file_hashing(tmp_path):
    settings = get_settings()
    previous_storage_root = settings.storage_root
    root = tmp_path / "storage"
    root.mkdir()
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"not a report")
    report_id = str(uuid4())
    try:
        settings.storage_root = str(root)
        with db_session() as db:
            db.add(
                DataReviewReportRun(
                    id=report_id,
                    data_quality_run_id=str(uuid4()),
                    source_table_id=str(uuid4()),
                    source_file_id=str(uuid4()),
                    import_session_id=str(uuid4()),
                    project_id=str(uuid4()),
                    run_number=1,
                    generator_name="test",
                    generator_version="1",
                    input_fingerprint="a" * 64,
                    status="completed",
                    filename="outside.xlsx",
                    storage_path=str(outside),
                    sha256="b" * 64,
                    file_size_bytes=outside.stat().st_size,
                    sheet_count=1,
                )
            )

        with pytest.raises(AppError) as exc_info:
            secure_data_review_report_path(report_id)
        assert exc_info.value.code == "data_review_report_path_escape"
    finally:
        settings.storage_root = previous_storage_root


async def test_global_security_headers_and_local_request_enforcement():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cache-control"] == "no-store"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]

        posture = await client.get("/security/posture")
        assert posture.status_code == 200
        assert "checks" in posture.json()

        rejected = await client.get("/health", headers={"Host": "public.example"})
        assert rejected.status_code in {400, 403}

    remote_transport = ASGITransport(app=app, client=("198.51.100.20", 12345))
    async with AsyncClient(transport=remote_transport, base_url="http://test") as client:
        rejected = await client.get("/health")
        assert rejected.status_code == 403
        assert "client address" in rejected.json()["detail"]


async def test_browser_origin_guard_requires_an_exact_configured_origin():
    settings = get_settings()
    previous_auth = settings.enable_auth
    settings.enable_auth = True
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rejected = await client.post(
                "/auth/logout",
                headers={"Origin": "http://localhost:9999"},
            )
            assert rejected.status_code == 403

            allowed = await client.post(
                "/auth/logout",
                headers={"Origin": settings.public_base_url},
            )
            assert allowed.status_code == 200
    finally:
        settings.enable_auth = previous_auth


async def test_request_body_limit_rejects_declared_and_streamed_oversize():
    limited = FastAPI()

    @limited.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"size": len(body)}

    limited.add_middleware(RequestBodyLimitMiddleware, max_bytes=4)
    transport = ASGITransport(app=limited)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        declared = await client.post(
            "/echo",
            content=b"12345",
            headers={"Content-Length": "5"},
        )
        assert declared.status_code == 413

        async def chunks():
            yield b"123"
            yield b"45"

        streamed = await client.post("/echo", content=chunks())
        assert streamed.status_code == 413


async def test_login_rate_limit_and_hardened_api_cookie(monkeypatch):
    settings = get_settings()
    previous_auth = settings.enable_auth
    settings.enable_auth = True
    login_rate_limiter.reset()
    monkeypatch.setenv("CTA_LOGIN_RATE_LIMIT_ATTEMPTS", "2")
    monkeypatch.setenv("CTA_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")

    def failing_login(_email, _password):
        raise ValueError("user details must not leak")

    monkeypatch.setattr(auth_router_module, "login", failing_login)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(2):
                response = await client.post(
                    "/auth/login",
                    json={"email": "user@example.test", "password": "wrong-password"},
                )
                assert response.status_code == 401
                assert response.json()["detail"] == "Invalid email or password"
            limited = await client.post(
                "/auth/login",
                json={"email": "user@example.test", "password": "wrong-password"},
            )
            assert limited.status_code == 429
            assert int(limited.headers["retry-after"]) >= 1

        login_rate_limiter.reset()

        def successful_login(_email, _password):
            return {"token": "signed-token", "user_id": "user-1", "role": "analyst"}

        monkeypatch.setattr(auth_router_module, "login", successful_login)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            success = await client.post(
                "/auth/login",
                json={"email": "user@example.test", "password": "correct-password"},
            )
            assert success.status_code == 200
            cookie = success.headers["set-cookie"]
            assert "HttpOnly" in cookie
            assert "SameSite=strict" in cookie
            assert "Path=/" in cookie
            assert success.headers["cache-control"] == "no-store"
    finally:
        settings.enable_auth = previous_auth
        login_rate_limiter.reset()


async def test_html_login_uses_the_same_generic_throttle_and_cookie(monkeypatch):
    settings = get_settings()
    previous_auth = settings.enable_auth
    settings.enable_auth = True
    login_rate_limiter.reset()
    monkeypatch.setenv("CTA_LOGIN_RATE_LIMIT_ATTEMPTS", "2")
    monkeypatch.setenv("CTA_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")

    def failing_login(_email, _password):
        raise ValueError("inactive account must not leak")

    monkeypatch.setattr(auth_ui_router_module, "login", failing_login)
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(2):
                response = await client.post(
                    "/ui/login",
                    data={"email": "user@example.test", "password": "wrong-password"},
                )
                assert response.status_code == 401
                assert "Invalid email or password" in response.text
                assert "inactive account" not in response.text
            limited = await client.post(
                "/ui/login",
                data={"email": "user@example.test", "password": "wrong-password"},
            )
            assert limited.status_code == 429
            assert int(limited.headers["retry-after"]) >= 1

        login_rate_limiter.reset()

        def successful_login(_email, _password):
            return {"token": "signed-token", "user_id": "user-1", "role": "analyst"}

        monkeypatch.setattr(auth_ui_router_module, "login", successful_login)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            success = await client.post(
                "/ui/login",
                data={"email": "user@example.test", "password": "correct-password"},
            )
            assert success.status_code == 303
            cookie = success.headers["set-cookie"]
            assert "HttpOnly" in cookie
            assert "SameSite=strict" in cookie
            assert "Path=/" in cookie
            assert success.headers["cache-control"] == "no-store"
    finally:
        settings.enable_auth = previous_auth
        login_rate_limiter.reset()
