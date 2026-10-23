"""
Unit tests for ReportService and Telegram formatters.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.db.repositories.orders import OrderRepository
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


def test_confirmed_orders_query_uses_amman_day():
    """The report day runs from Amman midnight to Amman midnight, not UTC."""
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value
    query.gte.return_value.lt.return_value.neq.return_value.order.return_value.execute.return_value.data = []

    OrderRepository(client).get_confirmed_orders_by_date("s1", date(2026, 10, 22))

    start = query.gte.call_args.args[1]
    end = query.gte.return_value.lt.call_args.args[1]
    assert start == "2026-10-22T00:00:00+03:00"
    assert end == "2026-10-23T00:00:00+03:00"


def _report_service(existing):
    order_repo = MagicMock()
    order_repo.get_confirmed_orders_by_date.return_value = []
    report_repo = MagicMock()
    report_repo.get_by_date.return_value = existing
    setting_repo = MagicMock()
    setting_repo.get_all.return_value = {}
    telegram = MagicMock()
    telegram.send_message = AsyncMock(return_value=True)
    service = ReportService(order_repo, report_repo, setting_repo, telegram)
    return service, report_repo, telegram


@pytest.mark.asyncio
async def test_manual_send_does_not_block_nightly_report():
    service, report_repo, telegram = _report_service(
        {"sent_successfully": True, "is_scheduled": False}
    )
    res = await service.generate_and_send_daily_report("s1", date(2026, 10, 22), scheduled=True)

    assert res["sent"] is True
    assert telegram.send_message.await_count == 1
    assert report_repo.save_report.call_args.kwargs["is_scheduled"] is True


@pytest.mark.asyncio
async def test_nightly_report_not_repeated():
    service, _, telegram = _report_service({"sent_successfully": True, "is_scheduled": True})
    res = await service.generate_and_send_daily_report("s1", date(2026, 10, 22), scheduled=True)

    assert res["already_sent"] is True
    telegram.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_resend_keeps_nightly_flag():
    service, report_repo, _ = _report_service({"sent_successfully": True, "is_scheduled": True})
    await service.generate_and_send_daily_report("s1", date(2026, 10, 22), force_resend=True)

    assert report_repo.save_report.call_args.kwargs["is_scheduled"] is True


@pytest.mark.parametrize("rows, force, should_send", [
    ([{"daily_report_enabled": False}], False, False),
    ([{"daily_report_enabled": False}], True, True),   # ?force=true still sends
    ([{"daily_report_enabled": True}], False, True),
    ([], False, True),                                  # no row saved means on
])
def test_scheduled_report_respects_toggle(client, monkeypatch, rows, force, should_send):
    from app.dependencies import get_db
    from app.main import app

    mock_db = MagicMock()
    query = mock_db.table.return_value
    query.select.return_value = query
    query.eq.return_value = query
    query.execute.return_value = MagicMock(data=rows)
    app.dependency_overrides[get_db] = lambda: mock_db

    send = AsyncMock(return_value={"sent": True})
    monkeypatch.setattr(ReportService, "generate_and_send_daily_report", send)

    res = client.post(
        f"/internal/daily-report?force={'true' if force else 'false'}",
        headers={"X-Internal-Token": "test-internal-token"},
    )
    assert res.status_code == 200
    assert send.called is should_send
    assert (res.json()["status"] == "skipped") is (not should_send)
