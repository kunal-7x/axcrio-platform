"""W14 reporting — date-range engine: presets recalculate correctly, vendor-tz
aware, half-open windows, the off-by-one fix."""
from __future__ import annotations

from datetime import datetime, timezone

from voice_ops.reporting.daterange import RANGE_PRESETS, resolve_range


# A fixed "now": 2026-06-18 12:00 UTC == 17:30 IST on 2026-06-18.
NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)


def _len_days(rng):
    return round((rng.end_utc - rng.start_utc).total_seconds() / 86400)


def test_presets_exist():
    assert set(RANGE_PRESETS) >= {"today", "yesterday", "7d", "30d", "this-month", "prev-month", "custom"}


def test_today_is_vendor_midnight_to_midnight():
    r = resolve_range("today", now=NOW)
    # IST midnight 2026-06-18 == 2026-06-17 18:30 UTC; next midnight 24h later.
    assert r.start_iso == "2026-06-17T18:30:00Z"
    assert r.end_iso == "2026-06-18T18:30:00Z"
    assert _len_days(r) == 1


def test_yesterday():
    r = resolve_range("yesterday", now=NOW)
    assert r.start_iso == "2026-06-16T18:30:00Z"
    assert r.end_iso == "2026-06-17T18:30:00Z"
    assert _len_days(r) == 1


def test_7d_includes_today_so_seven_days():
    r = resolve_range("7d", now=NOW)
    assert _len_days(r) == 7
    # ends at tomorrow vendor-midnight (today is fully included)
    assert r.end_iso == "2026-06-18T18:30:00Z"


def test_30d_is_thirty_days():
    assert _len_days(resolve_range("30d", now=NOW)) == 30


def test_this_month():
    r = resolve_range("this-month", now=NOW)
    # June 1 IST midnight == May 31 18:30 UTC; July 1 IST midnight == June 30 18:30 UTC.
    assert r.start_iso == "2026-05-31T18:30:00Z"
    assert r.end_iso == "2026-06-30T18:30:00Z"
    assert _len_days(r) == 30  # June has 30 days


def test_prev_month():
    r = resolve_range("prev-month", now=NOW)
    # May: 1..31 -> 31 days. May 1 IST == Apr 30 18:30 UTC; Jun 1 IST == May 31 18:30 UTC.
    assert r.start_iso == "2026-04-30T18:30:00Z"
    assert r.end_iso == "2026-05-31T18:30:00Z"
    assert _len_days(r) == 31


def test_prev_month_year_boundary():
    jan = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    r = resolve_range("prev-month", now=jan)
    # Dec 2025 -> 31 days.
    assert _len_days(r) == 31
    assert r.start_iso.startswith("2025-11-30")  # Dec 1 IST == Nov 30 18:30 UTC


def test_custom_inclusive_to_date():
    r = resolve_range("custom", now=NOW, frm="2026-06-01", to="2026-06-03")
    # 3 inclusive days -> end is the start of 2026-06-04 vendor-local.
    assert _len_days(r) == 3
    assert r.start_iso == "2026-05-31T18:30:00Z"
    assert r.end_iso == "2026-06-03T18:30:00Z"


def test_custom_inverted_range_is_swapped():
    r = resolve_range("custom", now=NOW, frm="2026-06-03", to="2026-06-01")
    assert _len_days(r) == 3  # well-formed regardless of order


def test_unknown_preset_falls_back_to_today():
    r = resolve_range("garbage", now=NOW)
    assert _len_days(r) == 1
    assert r.start_iso == "2026-06-17T18:30:00Z"


def test_off_by_one_midnight_call_lands_on_correct_vendor_day():
    """A call at 00:30 IST on 2026-06-18 == 19:00 UTC on 2026-06-17. It MUST count
    as 'today' (2026-06-18), not 'yesterday'. This is the founder's timeline bug."""
    today = resolve_range("today", now=NOW)
    yesterday = resolve_range("yesterday", now=NOW)
    midnight_call_utc = "2026-06-17T19:00:00Z"  # = 00:30 IST 2026-06-18
    assert today.contains(midnight_call_utc) is True
    assert yesterday.contains(midnight_call_utc) is False


def test_contains_is_half_open():
    r = resolve_range("today", now=NOW)
    assert r.contains(r.start_iso) is True       # start inclusive
    assert r.contains(r.end_iso) is False        # end exclusive
    assert r.contains("not-a-timestamp") is False


def test_vendor_dates_buckets():
    r = resolve_range("custom", now=NOW, frm="2026-06-16", to="2026-06-18")
    assert r.vendor_dates() == ["2026-06-16", "2026-06-17", "2026-06-18"]
