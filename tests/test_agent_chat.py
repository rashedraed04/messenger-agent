"""
Unit and integration tests for Admin Talk with Agent (Customer simulation without preferences).
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.dashboard.middleware import require_auth
from app.dependencies import get_db
from app.main import app
from app.models.conversation import ConversationState


@pytest.fixture
def auth_chat_client(client):
    """Authenticated client with mocked database for agent chat testing."""
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_query.update.return_value = mock_query
    mock_query.delete.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.range.return_value = mock_query
    mock_query.execute.return_value = MagicMock(
        data=[
            {
                "id": "test-conv-id-1234",
                "store_id": "00000000-0000-0000-0000-000000000001",
                "messenger_psid": "sim_admin_test_123",
                "state": "DISCOVERY",
                "collected_slots": {},
                "is_human_handoff": False,
                "created_at": "2026-10-18T00:00:00Z",
                "last_message_at": "2026-10-18T00:00:00Z",
            }
        ],
        count=1,
    )

    mock_db.table.return_value = mock_query

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[require_auth] = lambda: {
        "id": "test-admin-user",
        "email": "admin@perfumestore.jo",
        "store_id": "00000000-0000-0000-0000-000000000001",
    }

    yield client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_auth, None)


def test_agent_chat_unauthenticated_redirects(client):
    """Unauthenticated users must be redirected to login."""
    res = client.get("/dashboard/chat", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/auth/login"


def test_agent_chat_page_renders(auth_chat_client):
    """Authenticated admin sees the agent chat page with clean customer badge."""
    res = auth_chat_client.get("/dashboard/chat")
    assert res.status_code == 200
    assert "التحدث مع الوكيل الذكي" in res.text
    assert "عميل عام (بدون تفضيلات مسبقة)" in res.text
    assert "مرقاب حالة المحادثة" in res.text
    assert "البيانات المستخرجة من العميل" in res.text
    assert "بدء محادثة جديدة (تصفير)" in res.text


def test_agent_chat_reset_endpoint(auth_chat_client):
    """Resetting the session clears slots and sets state back to DISCOVERY."""
    res = auth_chat_client.post(
        "/dashboard/chat/reset",
        json={"session_id": "sim_admin_test_123", "clear_history": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["state"] == "DISCOVERY"
    assert data["collected_slots"] == {}
    assert "session_id" in data
    assert data["session_id"].startswith("sim_admin_")


def test_agent_chat_handoff_toggle_endpoint(auth_chat_client):
    """Admin can toggle human handoff status during testing."""
    res = auth_chat_client.post(
        "/dashboard/chat/handoff-toggle",
        json={"session_id": "sim_admin_test_123", "is_handoff": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True


def test_agent_chat_send_message_endpoint(auth_chat_client):
    """Sending a message routes to conversation service and returns replies."""
    with patch(
        "app.services.conversation_service.ConversationService.handle_customer_message",
        new_callable=AsyncMock,
    ) as mock_handle:
        mock_handle.return_value = ["أهلاً وسهلاً بك في متجر العطور! ديور سوفاج متوفر بسعر 45 دينار."]

        res = auth_chat_client.post(
            "/dashboard/chat/send",
            json={
                "message": "كم سعر عطر ديور سوفاج؟",
                "customer_name": None,
                "session_id": "sim_admin_test_123",
            },
        )

        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert len(data["replies"]) == 1
        assert "ديور سوفاج" in data["replies"][0]
        assert "conversation" in data
        assert data["conversation"]["state"] == "DISCOVERY"


def test_send_ignores_non_simulator_session(auth_chat_client):
    """A real customer's PSID must never be reachable from the simulator."""
    with patch(
        "app.services.conversation_service.ConversationService.handle_customer_message",
        new_callable=AsyncMock,
    ) as mock_handle:
        mock_handle.return_value = ["هلا"]
        auth_chat_client.post(
            "/dashboard/chat/send",
            json={"message": "مرحبا", "customer_name": None, "session_id": "1234567890123456"},
        )
        assert mock_handle.call_args.kwargs["messenger_psid"].startswith("sim_")
