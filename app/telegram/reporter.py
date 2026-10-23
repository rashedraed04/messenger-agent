"""
Telegram reporter for the daily list of orders to hand to the delivery company.
"""

import html
import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

# Telegram rejects longer messages, so long reports go out in several parts
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def split_telegram_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split on line breaks (every line's HTML tags are self-contained) into parts under the limit."""
    parts: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            parts.append(current)
            current = line
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts or [""]


def format_telegram_daily_report(
    store_name: str,
    report_date_str: str,
    orders: list[dict[str, Any]],
) -> str:
    """
    Format the daily order list (for the delivery company) in Arabic for Telegram.
    Uses HTML formatting supported by Telegram Bot API.
    """
    total_orders = len(orders)
    total_revenue = sum(float(o.get("total_jod") or 0.0) for o in orders)

    lines = [
        "📊 <b>التقرير اليومي للطلبات المؤكدة</b>",
        f"🏬 <b>{html.escape(store_name)}</b>",
        f"📅 <b>التاريخ:</b> {report_date_str}",
        "━━━━━━━━━━━━━━━━━━",
        f"📦 <b>عدد الطلبات:</b> {total_orders}",
        f"💰 <b>إجمالي التحصيل:</b> {total_revenue:.3f} د.أ",
        "━━━━━━━━━━━━━━━━━━\n",
    ]

    if not orders:
        lines.append("<i>لا توجد طلبات مؤكدة لهذا اليوم.</i>")
        return "\n".join(lines)

    lines.append("🚚 <b>تفاصيل التوصيل للطلبات:</b>\n")

    # Names and addresses are typed by customers: escape them so a stray "<" or "&"
    # can't make Telegram reject the report or plant a link in it
    for idx, order in enumerate(orders, 1):
        order_num = html.escape(str(order.get("order_number") or f"ORD-{idx}"))
        name = html.escape(order.get("customer_name") or "عميل")
        phone = html.escape(order.get("customer_phone") or "غير محدد")
        gov = html.escape(order.get("governorate") or "غير محدد")
        addr = html.escape(order.get("address_detail") or "")
        total_jod = float(order.get("total_jod") or 0.0)

        # Format items
        items = order.get("items") or []
        items_text = ", ".join(
            f"{html.escape(str(it.get('product_name_snapshot')))} × {it.get('quantity')}"
            for it in items
        ) or "منتجات"

        lines.append(f"<b>#{idx} — الطلب: {order_num}</b>")
        lines.append(f"👤 <b>الاسم:</b> {name}")
        lines.append(f"📞 <b>الهاتف:</b> <code>{phone}</code>")
        lines.append(f"📍 <b>العنوان:</b> {gov} - {addr}")
        lines.append(f"🧴 <b>المنتجات:</b> {items_text}")
        lines.append(f"💵 <b>المبلغ المطلوب تحصيله كاش:</b> <b>{total_jod:.3f} د.أ</b>")
        lines.append("──────────────────")

    return "\n".join(lines)


# Meta Business Suite inbox, where the owner answers Messenger customers
PAGE_INBOX_URL = "https://business.facebook.com/latest/inbox/all"


def format_angry_customer_alert(
    store_name: str,
    customer_name: str | None,
    message_text: str,
    is_test: bool = False,
) -> str:
    """Instant alert asking the store owner to step into an angry customer's chat."""
    lines = []
    if is_test:
        lines.append("🧪 <i>تجربة من لوحة التحكم</i>")
    lines += [
        "😠 <b>زبون منزعج على الماسنجر</b>",
        f"🏬 {html.escape(store_name)}",
        f"👤 <b>الزبون:</b> {html.escape(customer_name or 'غير معروف')}",
        f"💬 <b>رسالته:</b> <i>{html.escape(message_text[:500])}</i>",
        "البوت اعتذر منه وقله إنك رح تتابع معه شخصياً.",
    ]
    lines.append(f'<a href="{PAGE_INBOX_URL}">فتح رسائل الصفحة للرد عليه</a>')
    return "\n".join(lines)


class TelegramReporter:
    """Client for dispatching messages via Telegram Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send formatted text message to Telegram target chat.
        """
        if self.bot_token.startswith("test-"):
            logger.info("Mock Telegram message dispatch: chat_id=%s, len=%d", self.chat_id, len(text))
            return True
        if not self.bot_token or not self.chat_id:
            # Not configured: report failure so nothing is recorded as delivered
            logger.warning("Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID); message not sent")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                for part in split_telegram_message(text):
                    payload = {
                        "chat_id": self.chat_id,
                        "text": part,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True,
                    }
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    if not resp.json().get("ok"):
                        return False
                return True
            except httpx.HTTPStatusError as e:
                # str(e) includes the request URL, which contains the bot token
                logger.error("Failed to send Telegram message: HTTP %d", e.response.status_code)
                return False
            except Exception as e:
                logger.error("Failed to send Telegram message: %s", type(e).__name__)
                return False
