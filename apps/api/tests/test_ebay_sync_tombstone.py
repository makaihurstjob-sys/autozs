from datetime import datetime

from app.services.ebay_sync import _scheduled_start_passed


def test_eastern_wall_time_not_started_when_utc_clock_passes_naive_value() -> None:
    # Job 157 regression: 7:20 PM Eastern schedule, checked at 3:25 PM Eastern
    # (19:25 UTC). The naive comparison saw 19:20 <= 19:25 and tombstoned it.
    schedule = datetime(2026, 7, 30, 19, 20, 0)
    now_utc = datetime(2026, 7, 30, 19, 25, 0)
    assert _scheduled_start_passed(schedule, now_utc) is False


def test_eastern_wall_time_within_grace_period_not_started() -> None:
    schedule = datetime(2026, 7, 30, 19, 20, 0)
    now_utc = datetime(2026, 7, 30, 23, 30, 0)  # 7:30 PM Eastern
    assert _scheduled_start_passed(schedule, now_utc) is False


def test_eastern_wall_time_started_after_grace_period() -> None:
    schedule = datetime(2026, 7, 30, 19, 20, 0)
    now_utc = datetime(2026, 7, 31, 0, 0, 0)  # 8:00 PM Eastern
    assert _scheduled_start_passed(schedule, now_utc) is True


def test_utc_stored_value_never_reports_started_early() -> None:
    # Some rows store UTC (e.g. job 160's 2026-07-31T00:20:00). Interpreting
    # as Eastern delays the start moment, which is the safe direction for a
    # destructive tombstone.
    schedule = datetime(2026, 7, 31, 0, 20, 0)
    now_utc = datetime(2026, 7, 31, 0, 30, 0)
    assert _scheduled_start_passed(schedule, now_utc) is False
    assert _scheduled_start_passed(schedule, datetime(2026, 7, 31, 5, 0, 0)) is True
