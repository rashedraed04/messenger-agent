"""
Conversation and Message repository for database operations on conversations and messages.
"""

from datetime import datetime, timezone
from typing import Any
from supabase import Client

from app.models.conversation import ConversationState


class ConversationRepository:
    """Handles conversation sessions and message logs."""

    def __init__(self, client: Client):
        self.client = client
        self.conversations_table = "conversations"
        self.messages_table = "messages"

    def get_or_create(
        self,
        store_id: str,
        messenger_psid: str,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get the active conversation for a user, or create one in DISCOVERY state.
        """
        res = (
            self.client.table(self.conversations_table)
            .select("*")
            .eq("store_id", store_id)
            .eq("messenger_psid", messenger_psid)
            .order("last_message_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            conv = res.data[0]
            # Link customer if not linked
            if customer_id and not conv.get("customer_id"):
                self.client.table(self.conversations_table).update(
                    {"customer_id": customer_id}
                ).eq("id", conv["id"]).execute()
                conv["customer_id"] = customer_id
            return conv

        # Create new
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            "store_id": store_id,
            "messenger_psid": messenger_psid,
            "customer_id": customer_id,
            "state": ConversationState.DISCOVERY.value,
            "collected_slots": {},
            "is_human_handoff": False,
            "last_message_at": now_iso,
            "created_at": now_iso,
        }
        create_res = (
            self.client.table(self.conversations_table).insert(payload).execute()
        )
        return create_res.data[0] if create_res.data else {}

    def get_by_id(self, store_id: str, conversation_id: str) -> dict[str, Any] | None:
        """Fetch conversation by ID."""
        res = (
            self.client.table(self.conversations_table)
            .select("*, customers(*)")
            .eq("store_id", store_id)
            .eq("id", conversation_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def update_state(
        self,
        store_id: str,
        conversation_id: str,
        state: ConversationState | str,
        collected_slots: dict[str, Any] | None = None,
        current_order_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Update conversation state machine state and collected slots."""
        state_val = state.value if isinstance(state, ConversationState) else state
        payload: dict[str, Any] = {
            "state": state_val,
            "last_message_at": datetime.now(timezone.utc).isoformat(),
        }
        if collected_slots is not None:
            payload["collected_slots"] = collected_slots
        if current_order_id is not None:
            payload["current_order_id"] = current_order_id

        res = (
            self.client.table(self.conversations_table)
            .update(payload)
            .eq("store_id", store_id)
            .eq("id", conversation_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def set_human_handoff(
        self,
        store_id: str,
        conversation_id: str,
        is_handoff: bool = True,
        reason: str | None = None,
    ) -> dict[str, Any] | None:
        """Toggle human handover mode."""
        payload: dict[str, Any] = {
            "is_human_handoff": is_handoff,
            "handoff_reason": reason if is_handoff else None,
            "state": ConversationState.HUMAN_HANDOFF.value
            if is_handoff
            else ConversationState.DISCOVERY.value,
            "last_message_at": datetime.now(timezone.utc).isoformat(),
        }
        res = (
            self.client.table(self.conversations_table)
            .update(payload)
            .eq("store_id", store_id)
            .eq("id", conversation_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def add_message(
        self,
        conversation_id: str,
        direction: str,  # 'inbound' | 'outbound'
        content: str,
        message_type: str = "text",
        ai_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save a message in the conversation history."""
        payload = {
            "conversation_id": conversation_id,
            "direction": direction,
            "content": content,
            "message_type": message_type,
            "ai_metadata": ai_metadata,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        res = self.client.table(self.messages_table).insert(payload).execute()
        return res.data[0] if res.data else {}

    def get_messages(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Fetch messages in chronological order."""
        res = (
            self.client.table(self.messages_table)
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def get_recent_messages(
        self,
        conversation_id: str,
        since: datetime | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Fetch the LATEST `limit` messages (optionally only those created at/after `since`),
        returned in chronological order.

        Unlike get_messages(), which returns the oldest messages first, this is what
        prompt context and "latest message" lookups need.
        """
        query = (
            self.client.table(self.messages_table)
            .select("*")
            .eq("conversation_id", conversation_id)
        )
        if since is not None:
            query = query.gte("created_at", since.isoformat())
        res = query.order("created_at", desc=True).limit(limit).execute()
        return list(reversed(res.data or []))
