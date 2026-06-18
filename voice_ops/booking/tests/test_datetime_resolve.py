"""Tests for voice_ops.booking.datetime_resolve — pure, clock-injected, deterministic."""
from __future__ import annotations

import datetime as _dt

from voice_ops.booking.datetime_resolve import humanize_slot, resolve_slot_start

# A fixed "now": 2026-06-18 06:00 UTC == 2026-06-18 11:30 IST.
NOW = _dt.datetime(2026, 6, 18, 6, 0, tzinfo=_dt.timezone.utc)


def test_iso_passthrough():
    out = resolve_slot_start("2026-06-20T10:00:00+00:00", now=NOW)
    assert out == _dt.datetime(2026, 6, 20, 10, 0, tzinfo=_dt.timezone.utc)


def test_kal_subah_das_baje():
    # "kal" = tomorrow (19 Jun), "subah ... 10 baje" -> 10:00 IST -> 04:30 UTC.
    out = resolve_slot_start("kal subah 10 baje", now=NOW, tz="Asia/Kolkata")
    assert out is not None
    assert out == _dt.datetime(2026, 6, 19, 4, 30, tzinfo=_dt.timezone.utc)


def test_tomorrow_3pm():
    out = resolve_slot_start("tomorrow 3pm", now=NOW, tz="Asia/Kolkata")
    # 15:00 IST tomorrow -> 09:30 UTC
    assert out == _dt.datetime(2026, 6, 19, 9, 30, tzinfo=_dt.timezone.utc)


def test_period_default_when_no_clock():
    # "kal shaam" -> evening default 17:00 IST -> 11:30 UTC tomorrow
    out = resolve_slot_start("kal shaam", now=NOW, tz="Asia/Kolkata")
    assert out == _dt.datetime(2026, 6, 19, 11, 30, tzinfo=_dt.timezone.utc)


def test_today_past_time_bumps_to_tomorrow():
    # now is 11:30 IST; "aaj subah 10 baje" already passed -> bump to tomorrow.
    out = resolve_slot_start("aaj subah 10 baje", now=NOW, tz="Asia/Kolkata")
    assert out is not None
    assert out.date() == _dt.date(2026, 6, 19) or out > NOW


def test_unparseable_returns_none():
    assert resolve_slot_start("", now=NOW) is None
    assert resolve_slot_start("maybe sometime later perhaps", now=NOW) is None


def test_humanize_slot():
    s = humanize_slot("2026-06-20T04:30:00+00:00", tz="Asia/Kolkata")
    # 04:30 UTC -> 10:00 IST
    assert "10:00 AM" in s
    assert "20 Jun" in s
