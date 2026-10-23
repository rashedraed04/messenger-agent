"""
Pytest fixtures and configuration.

Provides:
- Test Settings with dummy values (no real Supabase needed for unit tests)
- FastAPI TestClient with dependency overrides
- Common test data fixtures
"""

import os

import pytest
from fastapi.testclient import TestClient

# Set test environment variables BEFORE importing app modules
os.environ.setdefault("SUPABASE_URL", "https://test-project.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("META_VERIFY_TOKEN", "test-verify-token")
os.environ.setdefault("META_APP_SECRET", "test-meta-secret")
os.environ.setdefault("INTERNAL_API_TOKEN", "test-internal-token")

from app.config import Settings
from app.dashboard.rate_limit import webhook_sender_limiter
from app.dependencies import get_config
from app.main import app


@pytest.fixture(autouse=True)
def clear_webhook_sender_limiter():
    """The per-sender limiter is module state; start each test with it empty."""
    webhook_sender_limiter.clear()
    yield


@pytest.fixture
def test_settings() -> Settings:
    """Return a Settings instance with test values."""
    return Settings(
        supabase_url="https://test-project.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_role_key="test-service-role-key",
        gemini_api_key="test-gemini-key",
        meta_app_secret="test-meta-secret",
        meta_page_access_token="test-page-token",
        meta_verify_token="test-verify-token",
        telegram_bot_token="test-telegram-token",
        telegram_chat_id="test-chat-id",
        internal_api_token="test-internal-token",
        app_env="testing",
        default_store_id="00000000-0000-0000-0000-000000000001",
    )


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    """Provide a TestClient with dependency overrides for unit testing."""
    app.dependency_overrides[get_config] = lambda: test_settings
    with TestClient(app) as test_client:
        # Behave like a browser: load a page to receive the CSRF cookie,
        # then echo the token on every state-changing request.
        test_client.get("/auth/login")
        test_client.headers["X-CSRF-Token"] = test_client.cookies.get("csrf_token", "")
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def default_store_id() -> str:
    """Return the default test store ID."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_product() -> dict:
    """Return a sample product data dict."""
    return {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "store_id": "00000000-0000-0000-0000-000000000001",
        "name_ar": "سوفاج ديور",
        "name_en": "Dior Sauvage",
        "brand": "Dior",
        "size_ml": "100",
        "price_jod": 45.000,
        "stock_quantity": 10,
        "in_stock": True,
        "is_active": True,
        "category": "رجالي",
    }
