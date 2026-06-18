"""W8 canonical timestamp / timezone tests.

The load-bearing case is the founder bug: a call placed at 00:30 IST is
19:00 UTC the PREVIOUS day. Rendering it in the vendor zone must show TODAY's
IST date (00:30), not "yesterday". We assert the render layer fixes the
off-by-one, that naive timestamps are treated as UTC (the storage contract),
and that the 'Z' marker is always present on the wire.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from voice_kernel.events import timeutil as tu


def test_now_utc_iso_is_z_suffixed_and_aware():
    s = tu.now_utc_iso()
    assert s.endswith("Z"), s
    assert "+00:00" not in s
    # round-trips back to aware-UTC
    assert tu.parse_iso(s).tzinfo is not None


def test_parse_z_and_offset_and_naive_all_utc():
    z = tu.parse_iso("2026-06-18T19:00:00Z")
    off = tu.parse_iso("2026-06-18T19:00:00+00:00")
    naive = tu.parse_iso("2026-06-18T19:00:00")  # storage contract: naive == UTC
    assert z == off == naive
    assert z.tzinfo == timezone.utc


def test_to_vendor_renders_ist_offset():
    # 19:00 UTC -> 00:30 IST the NEXT calendar day.
    local = tu.to_vendor("2026-06-18T19:00:00Z")
    assert local.utcoffset() == timedelta(hours=5, minutes=30)
    assert local.hour == 0 and local.minute == 30
    assert local.strftime("%Y-%m-%d") == "2026-06-19"  # next day in IST


def test_the_one_day_ago_bug_is_fixed():
    """A call 'just now' at 19:05 UTC == 00:35 IST on 2026-06-19. 'Now' is a few
    minutes later. The vendor-local humanize must say 'just now' / 'today', NEVER
    'yesterday' — the exact founder complaint."""
    event_utc = "2026-06-19T19:05:00Z"          # 00:35 IST on the 20th
    now = datetime(2026, 6, 19, 19, 30, 0, tzinfo=timezone.utc)  # 25 min later
    label = tu.humanize(event_utc, now=now)
    # The bug was this rendering as "yesterday"/a stale date. It must read as a
    # fresh, same-IST-day label.
    assert label == "25 min ago", label
    assert "yesterday" not in label and "ago" in label
    # And the grouping date is the VENDOR date (20th), not the UTC date (19th).
    assert tu.vendor_date(event_utc) == "2026-06-20"


def test_humanize_buckets():
    base = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    # 30 min ago
    assert tu.humanize(base - timedelta(minutes=30), now=base) == "30 min ago"
    # earlier today (IST): base = 17:30 IST; 5h earlier = 12:30 IST same IST day
    earlier = base - timedelta(hours=5)
    assert tu.humanize(earlier, now=base).startswith("today ")
    # ~26h ago crosses to yesterday in IST
    y = base - timedelta(hours=26)
    assert tu.humanize(y, now=base).startswith("yesterday ")


def test_future_timestamp_clamps_to_just_now():
    base = datetime(2026, 6, 18, 12, 0, 0, tzinfo=timezone.utc)
    future = base + timedelta(minutes=5)
    assert tu.humanize(future, now=base) == "just now"


def test_ensure_utc_naive_assumed_utc():
    naive = datetime(2026, 6, 18, 19, 0, 0)  # no tzinfo
    aware = tu.ensure_utc(naive)
    assert aware.tzinfo == timezone.utc
    assert aware.hour == 19  # NOT shifted (assumed already UTC, not local)


def test_render_vendor_string():
    assert tu.render_vendor("2026-06-18T19:00:00Z") == "2026-06-19 00:30"
