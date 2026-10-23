"""
Store settings repository for database operations on store_settings table.
"""

from typing import Any

from supabase import Client

# Flat fee charged by the delivery company, used until the admin sets one in Settings
DEFAULT_DELIVERY_FEE_JOD = 3.0


class StoreSettingRepository:
    """Handles key-value configuration per store."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "store_settings"

    def get_all(self, store_id: str) -> dict[str, str]:
        """Fetch all settings for a store as a {key: value} dict."""
        res = (
            self.client.table(self.table)
            .select("setting_key, setting_value")
            .eq("store_id", store_id)
            .execute()
        )
        return {
            row["setting_key"]: row.get("setting_value") or ""
            for row in (res.data or [])
        }

    def get_value(self, store_id: str, key: str, default: str = "") -> str:
        """Fetch a specific setting value."""
        res = (
            self.client.table(self.table)
            .select("setting_value")
            .eq("store_id", store_id)
            .eq("setting_key", key)
            .execute()
        )
        if res.data and res.data[0].get("setting_value") is not None:
            return res.data[0]["setting_value"]
        return default

    def set_value(
        self,
        store_id: str,
        key: str,
        value: str,
        setting_type: str = "text",
    ) -> dict[str, Any]:
        """Upsert a setting value."""
        payload = {
            "store_id": store_id,
            "setting_key": key,
            "setting_value": value,
            "setting_type": setting_type,
        }
        res = (
            self.client.table(self.table)
            .upsert(payload, on_conflict="store_id,setting_key")
            .execute()
        )
        return res.data[0] if res.data else {}

    def get_delivery_fee(self, store_id: str) -> float:
        """Flat delivery fee in JOD for all governorates."""
        try:
            return max(float(self.get_value(store_id, "delivery_fee_jod")), 0.0)
        except ValueError:
            return DEFAULT_DELIVERY_FEE_JOD

    def get_bot_config(self, store_id: str) -> dict[str, Any]:
        """
        Convenience method to retrieve structured bot configuration for prompts.
        """
        settings = self.get_all(store_id)
        return {
            "bot_enabled": settings.get("bot_enabled", "true").lower() == "true",
            "bot_greeting": settings.get(
                "bot_greeting",
                "هلا والله، نورت 🌹 كيف بقدر أساعدك؟",
            ),
            "bot_tone": settings.get(
                "bot_tone",
                "احكي بلهجة أردنية عمّانية عفوية وودية زي موظف المحل.",
            ),
            "store_name": settings.get("store_name", "متجر التقوى"),
            "store_description": settings.get("store_description", ""),
            "working_hours": settings.get("working_hours", ""),
            "return_policy": settings.get("return_policy", ""),
            "human_handoff_message": settings.get(
                "human_handoff_message",
                "تكرم عينك، هسا بخلي حدا من الشباب يحكي معك بأقرب وقت 🙏",
            ),
            "delivery_fee_jod": float(settings.get("delivery_fee_jod") or DEFAULT_DELIVERY_FEE_JOD),
        }
