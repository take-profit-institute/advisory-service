from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from advisory_service.main import _next_sync_at

SEOUL = ZoneInfo("Asia/Seoul")


def test_next_sync_uses_same_day_23_kst_before_schedule():
    now = datetime(2026, 8, 15, 13, 0, tzinfo=UTC)  # 22:00 KST

    result = _next_sync_at(now, time(23, 0), SEOUL)

    assert result == datetime(2026, 8, 15, 23, 0, tzinfo=SEOUL)


def test_next_sync_uses_next_day_after_schedule():
    now = datetime(2026, 8, 15, 14, 1, tzinfo=UTC)  # 23:01 KST

    result = _next_sync_at(now, time(23, 0), SEOUL)

    assert result == datetime(2026, 8, 16, 23, 0, tzinfo=SEOUL)


def test_next_sync_runs_immediately_at_exact_same_time():
    now = datetime(2026, 8, 15, 14, 0, tzinfo=UTC)  # 23:00 KST

    result = _next_sync_at(now, time(23, 0), SEOUL)

    assert result == datetime(2026, 8, 15, 23, 0, tzinfo=SEOUL)
