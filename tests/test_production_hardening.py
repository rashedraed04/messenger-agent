"""
Production hardening: fail-closed defaults, hidden API docs, friendly 500s,
a /health that answers fast, and a locked-down daily report trigger.
"""

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
import app.routes.health as health_module
from app.config import Settings
from app.dependencies import get_config, get_db
from app.main import app, create_app


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_app_env_defaults_to_production(monkeypatch):
    """A forgotten APP_ENV must not switch on the dev login bypass or the docs."""
    monkeypatch.delenv("APP_ENV", raising=False)
    settings = _settings()
    assert settings.app_env == "production"
    assert settings.is_production


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_hidden_in_production(monkeypatch, path):
    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(app_env="production"))
    res = TestClient(create_app()).get(path)
    assert res.status_code == 404


def test_api_docs_available_in_development(monkeypatch):
    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(app_env="development"))
    assert TestClient(create_app()).get("/openapi.json").status_code == 200


@pytest.fixture
def crashing_client():
    application = create_app()

    @application.get("/boom")
    def boom():
        raise RuntimeError(r"secret detail C:\app\internal.py")

    return TestClient(application, raise_server_exceptions=False)


def test_unhandled_error_returns_arabic_json(crashing_client):
    res = crashing_client.get("/boom")
    assert res.status_code == 500
    assert res.json() == {"detail": main_module.SERVER_ERROR_MESSAGE}
    assert "secret detail" not in res.text


def test_unhandled_error_returns_arabic_page_for_browsers(crashing_client):
    res = crashing_client.get("/boom", headers={"Accept": "text/html"})
    assert res.status_code == 500
    assert "text/html" in res.headers["content-type"]
    assert "خطأ" in res.text
    for leak in ("Traceback", "RuntimeError", "secret detail", "internal.py"):
        assert leak not in res.text


@pytest.fixture
def health_client():
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    # Keep one event loop alive across the request, as uvicorn does
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.pop(get_db, None)


def test_health_pings_database(health_client):
    client, db = health_client
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    db.table.assert_called_with("stores")


def test_health_answers_head_requests(health_client):
    client, _ = health_client
    assert client.head("/health").status_code == 200


def test_health_times_out_instead_of_hanging(health_client, monkeypatch):
    client, db = health_client
    monkeypatch.setattr(health_module, "DB_PING_TIMEOUT_SECONDS", 0.05)
    db.table.return_value.select.return_value.limit.return_value.execute.side_effect = (
        lambda: time.sleep(0.5)
    )

    started = time.perf_counter()
    res = client.get("/health")
    assert time.perf_counter() - started < 0.4
    assert res.status_code == 200
    assert res.json() == {**res.json(), "status": "degraded", "database": "error: timeout"}


def test_daily_report_rejects_wrong_token(client):
    res = client.post("/internal/daily-report", headers={"X-Internal-Token": "guess"})
    assert res.status_code == 403


def test_daily_report_rejects_missing_token(client):
    assert client.post("/internal/daily-report").status_code == 422


def test_daily_report_refuses_when_token_unset(client, test_settings):
    app.dependency_overrides[get_config] = lambda: test_settings.model_copy(
        update={"internal_api_token": ""}
    )
    res = client.post("/internal/daily-report", headers={"X-Internal-Token": ""})
    assert res.status_code == 503


async def test_telegram_failure_never_logs_bot_token(monkeypatch, caplog):
    import httpx

    from app.telegram.reporter import TelegramReporter

    token = "123456:SECRET-BOT-TOKEN"

    async def fail(self, url, **kwargs):
        request = httpx.Request("POST", url)
        response = httpx.Response(400, request=request)
        raise httpx.HTTPStatusError(f"Client error for url '{url}'", request=request, response=response)

    monkeypatch.setattr(httpx.AsyncClient, "post", fail)
    sent = await TelegramReporter(token, "42").send_message("hello")

    assert sent is False
    assert "HTTP 400" in caplog.text
    assert token not in caplog.text
