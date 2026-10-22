"""
Unit tests for ReportService and Telegram formatters.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services.report_service import ReportService
from app.telegram.reporter import format_telegram_daily_report


def test_format_telegram_daily_report():
    orders = [
        {
            "order_number": "ORD-20261017-001",
            "customer_name": "أحمد الملكاوي",
            "customer_phone": "0791234567",
            "governorate": "عمّان",
            "address_detail": "طبربور قرب مسجد التوحيد",
            "total_jod": 47.0,
            "items": [
                {
                    "product_name_snapshot": "سوفاج ديور 100 مل",
                    "quantity": 1,
                }
            ],
        }
    ]

    report = format_telegram_daily_report("متجر العطور الأردني", "2026-10-17", orders)

    assert "التقرير اليومي للطلبات المؤكدة" in report
    assert "متجر العطور الأردني" in report
    assert "عدد الطلبات:</b> 1" in report
    assert "47.000 د.أ" in report
    assert "أحمد الملكاوي" in report
    assert "0791234567" in report
    assert "طبربور" in report
    assert "سوفاج ديور 100 مل × 1" in report


def test_format_empty_orders_report():
    report = format_telegram_daily_report("متجر العطور الأردني", "2026-10-17", [])
    assert "لا توجد طلبات مؤكدة لهذا اليوم" in report
    assert "عدد الطلبات:</b> 0" in report


@pytest.mark.asyncio
async def test_report_service_generate_and_send():
    order_repo = MagicMock()
    order_repo.get_confirmed_orders_by_date.return_value = [
        {
            "order_number": "ORD-1",
            "customer_name": "محمد",
            "customer_phone": "0781234567",
            "governorate": "إربد",
            "address_detail": "شارع الجامعة",
            "total_jod": 35.0,
            "items": [{"product_name_snapshot": "بلو دي شانيل", "quantity": 1}],
        }
    ]

    report_repo = MagicMock()
    report_repo.get_by_date.return_value = None  # not yet sent
    report_repo.save_report.return_value = {"id": "rep_1"}

    setting_repo = MagicMock()
    setting_repo.get_all.return_value = {"store_name": "متجر فخم"}

    telegram_mock = MagicMock()
    telegram_mock.send_message = AsyncMock(return_value=True)

    service = ReportService(
        order_repo=order_repo,
        report_repo=report_repo,
        setting_repo=setting_repo,
        telegram_reporter=telegram_mock,
    )

    res = await service.generate_and_send_daily_report(
        store_id="s1",
        target_date=date(2026, 10, 17),
    )

    assert res["sent"] is True
    assert res["orders_count"] == 1
    assert "ORD-1" in res["content"]
    assert telegram_mock.send_message.call_count == 1
    assert report_repo.save_report.call_count == 1
