"""Scheduler maths + email poller dedupe (pure parts)."""
from datetime import datetime, timezone

from aia.agents.scheduler import seconds_until, seconds_until_weekday
from aia.integrations.email.base import EmailMessage
from aia.integrations.email.poller import new_messages

UTC = timezone.utc


def test_seconds_until_same_day_future():
    now = datetime(2026, 10, 27, 6, 0, tzinfo=UTC)
    assert seconds_until(8, 0, now) == 2 * 3600


def test_seconds_until_rolls_to_tomorrow_when_past():
    now = datetime(2026, 10, 27, 9, 30, tzinfo=UTC)
    assert seconds_until(8, 0, now) == 22.5 * 3600


def test_seconds_until_exactly_now_is_a_full_day_away():
    now = datetime(2026, 10, 27, 8, 0, tzinfo=UTC)
    assert seconds_until(8, 0, now) == 24 * 3600


def test_seconds_until_weekday_today_in_future_counts_today():
    # 2026-10-27 is a Tuesday.
    now = datetime(2026, 10, 27, 6, 0, tzinfo=UTC)
    assert seconds_until_weekday(1, 8, 0, now) == 2 * 3600  # weekday 1 = Tuesday


def test_seconds_until_weekday_today_in_past_goes_next_week():
    now = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
    assert seconds_until_weekday(1, 8, 0, now) == 7 * 24 * 3600 - 3600


def test_seconds_until_weekday_other_day():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)  # Tuesday
    # Next Monday (weekday 0) at 08:00.
    target = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    assert seconds_until_weekday(0, 8, 0, now) == (target - now).total_seconds()


def test_new_messages_dedupes_by_external_id():
    seen = {"a", "b"}
    msgs = [
        EmailMessage(external_id="a", sender="x", subject="", snippet=""),
        EmailMessage(external_id="c", sender="y", subject="", snippet=""),
        EmailMessage(external_id="", sender="z", subject="", snippet=""),
    ]
    fresh = new_messages(seen, msgs)
    assert [m.external_id for m in fresh] == ["c"]
