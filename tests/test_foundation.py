"""
Foundation Layer Automated Test Suite.
Verifies:
1. SQL Schema and Migrations (13 tables, constraints, indexes, triggers, and RLS policies).
2. Strict RLS security: NO anon SELECT access on products or delivery_zones.
3. Server-side privilege separation: service_role key never exposed to client or anon flows.
4. Multi-tenant store_id isolation across repositories.
5. Health check endpoint reporting database connectivity.
"""

import os
import re
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from app.config import get_settings
from app.db.client import get_supabase_anon_client, get_supabase_client
from app.db.repositories.notification_settings import NotificationSettingRepository
from app.main import app
from app.models.notification_setting import (
    NotificationSettingCreate,
    NotificationSettingUpdate,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_schema_migration_files_exist():
    """Verify both migration files exist and are non-empty."""
    m1_path = os.path.join("migrations", "001_initial_schema.sql")
    m2_path = os.path.join("migrations", "002_seed_data.sql")
    assert os.path.exists(m1_path), "001_initial_schema.sql missing"
    assert os.path.exists(m2_path), "002_seed_data.sql missing"

    with open(m1_path, encoding="utf-8") as f:
        m1_content = f.read()
    with open(m2_path, encoding="utf-8") as f:
        m2_content = f.read()

    assert len(m1_content) > 1000
    assert len(m2_content) > 500


def test_schema_defines_all_required_tables():
    """Verify all 13 core tables are defined with CREATE TABLE IF NOT EXISTS."""
    m1_path = os.path.join("migrations", "001_initial_schema.sql")
    with open(m1_path, encoding="utf-8") as f:
        sql = f.read()

    expected_tables = [
        "stores",
        "store_members",
        "products",
        "delivery_zones",
        "customers",
        "conversations",
        "orders",
        "order_items",
        "messages",
        "faqs",
        "store_settings",
        "notification_settings",
        "processed_webhook_events",
        "report_history",
    ]

    for table in expected_tables:
        pattern = rf"CREATE TABLE IF NOT EXISTS {table}\s*\("
        assert re.search(pattern, sql, re.IGNORECASE), f"Missing CREATE TABLE for {table}"


def test_schema_enables_rls_on_all_tables():
    """Verify that every single table has ALTER TABLE ... ENABLE ROW LEVEL SECURITY."""
    m1_path = os.path.join("migrations", "001_initial_schema.sql")
    with open(m1_path, encoding="utf-8") as f:
        sql = f.read()

    expected_tables = [
        "stores",
        "store_members",
        "products",
        "delivery_zones",
        "customers",
        "conversations",
        "orders",
        "order_items",
        "messages",
        "faqs",
        "store_settings",
        "notification_settings",
        "processed_webhook_events",
        "report_history",
    ]

    for table in expected_tables:
        pattern = rf"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;"
        assert re.search(pattern, sql, re.IGNORECASE), f"Table {table} does not have RLS enabled"


def test_strict_rls_policies_no_anon_access_on_products_and_delivery_zones():
    """
    CRITICAL SECURITY TEST:
    Assert that 'anon' role is NEVER granted SELECT (or any access) on products or delivery_zones.
    All public queries must go server-side through FastAPI backend.
    """
    m1_path = os.path.join("migrations", "001_initial_schema.sql")
    with open(m1_path, encoding="utf-8") as f:
        sql = f.read()

    # Find all policies for products and delivery_zones
    product_policies = re.findall(
        r"CREATE POLICY\s+([a-zA-Z0-9_]+)\s+ON\s+products\s+FOR\s+([A-Z]+)\s+TO\s+([a-zA-Z0-9_]+)",
        sql,
        re.IGNORECASE,
    )
    assert len(product_policies) > 0, "No RLS policy defined on products table"
    for pol_name, action, role in product_policies:
        assert role.lower() != "anon", f"SECURITY BREACH: Found anon role on products table policy '{pol_name}'"
        assert role.lower() == "authenticated", f"Expected authenticated role, found: {role}"

    delivery_policies = re.findall(
        r"CREATE POLICY\s+([a-zA-Z0-9_]+)\s+ON\s+delivery_zones\s+FOR\s+([A-Z]+)\s+TO\s+([a-zA-Z0-9_]+)",
        sql,
        re.IGNORECASE,
    )
    assert len(delivery_policies) > 0, "No RLS policy defined on delivery_zones table"
    for pol_name, action, role in delivery_policies:
        assert role.lower() != "anon", f"SECURITY BREACH: Found anon role on delivery_zones table policy '{pol_name}'"
        assert role.lower() == "authenticated", f"Expected authenticated role, found: {role}"


def test_rls_is_store_member_helper_exists():
    """Verify that is_store_member helper function is created with SECURITY DEFINER."""
    m1_path = os.path.join("migrations", "001_initial_schema.sql")
    with open(m1_path, encoding="utf-8") as f:
        sql = f.read()

    assert "is_store_member" in sql
    assert "SECURITY DEFINER" in sql
    assert "(SELECT auth.uid())" in sql


def test_server_side_secret_hygiene():
    """
    Verify that privileged credentials (service_role_key) remain strictly server-side
    and are never returned or configured on the public anon client.
    """
    settings = get_settings()

    # The service role key must exist in settings
    assert settings.supabase_service_role_key is not None

    # Supabase anon client must use anon key, NEVER the service role key
    anon_client = get_supabase_anon_client()
    assert anon_client.supabase_key == settings.supabase_anon_key
    assert anon_client.supabase_key != settings.supabase_service_role_key

    # Supabase service client uses the service role key
    srv_client = get_supabase_client()
    assert srv_client.supabase_key == settings.supabase_service_role_key


def test_public_pages_do_not_leak_privileged_secrets(client: TestClient):
    """Ensure no server secret keys are exposed in HTML responses or public headers."""
    settings = get_settings()
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    assert settings.supabase_service_role_key not in html
    assert "service_role" not in html
    assert settings.internal_api_token not in html
    assert settings.meta_app_secret not in html


def test_notification_settings_pydantic_model_validation():
    """Test validation of NotificationSetting models."""
    valid_create = NotificationSettingCreate(
        store_id="00000000-0000-0000-0000-000000000001",
        channel="telegram",
        recipient_chat_id="123456789",
        daily_report_enabled=True,
        daily_report_time="21:30:00",
        alert_on_new_order=True,
        alert_on_human_handoff=True,
    )
    assert valid_create.channel == "telegram"

    # Update model allows partial fields
    update = NotificationSettingUpdate(alert_on_new_order=False)
    assert update.alert_on_new_order is False
    assert update.recipient_chat_id is None


def test_notification_setting_repository_store_isolation():
    """Test that NotificationSettingRepository enforces store_id on queries."""
    mock_client = MagicMock()
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"channel": "telegram", "daily_report_enabled": True}])

    repo = NotificationSettingRepository(mock_client)
    store_id = "00000000-0000-0000-0000-000000000001"

    # get_by_channel must filter by store_id and channel
    result = repo.get_by_channel(store_id, "telegram")
    assert result is not None
    mock_client.table.assert_called_with("notification_settings")
    mock_table.eq.assert_any_call("store_id", store_id)
    mock_table.eq.assert_any_call("channel", "telegram")


def test_health_check_endpoint(client: TestClient):
    """Test health check endpoint reports status and database connectivity."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ("healthy", "degraded")
    assert "database" in data
    assert "timestamp" in data
