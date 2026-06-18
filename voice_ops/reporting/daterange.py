"""voice_ops.reporting.daterange — the date-range engine (W14).

THE FOUNDER REQUIREMENT (#3): a universal dashboard whose DEFAULT is Today, with
Yesterday / 7d / 30d / this-month / prev-month / custom, and EVERY metric is
recalculated per range. The recalculation is correct ONLY if the range window is
computed in the VENDOR'S wall-clock zone (Asia/Kolkata), not UTC — otherwise a
call placed at 00:30 IST (= 19:00 UTC the previous day) lands in the wrong
"today" and the count is wrong. This module is the single chokepoint for that.

Output contract: a `DateRange` carries an explicit, HALF-OPEN [start_utc, end_utc)
pair of aware-UTC datetimes. Half-open avoids the classic double-count at the
boundary (a call exactly at midnight belongs to the new day, once). A FactCall is
"in range" iff `start_utc <= ts < end_utc`. Both ends are also exposed as
canonical 'Z' ISO strings for the wire / panel API.

Pure stdlib + voice_kernel.events.timeutil only. No droplet import.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from voice_kernel.events.timeutil import (
    VENDOR_TZ_NAME,
    _to_z,
    _tz,
    ensure_utc,
    now_utc,
    parse_iso,
)

# The closed set of presets the founder asked for. "custom" is handled separately
# (it needs explicit from/to). Order is the panel's chip order.
RANGE_PRESETS = (
    "today",
    "yesterday",
    "7d",
    "30d",
    "this-month",
    "prev-month",
    "custom",
)


@dataclass(frozen=True)
class DateRange:
    """A resolved, half-open [start_utc, end_utc) window plus its label + the
    vendor-local calendar dates it spans (for day-bucketing the timeline)."""

    preset: str
    start_utc: datetime  # inclusive, aware-UTC
    end_utc: datetime    # exclusive, aware-UTC
    tz_name: str = VENDOR_TZ_NAME

    @property
    def start_iso(self) -> str:
        return _to_z(self.start_utc)

    @property
    def end_iso(self) -> str:
        return _to_z(self.end_utc)

    def contains(self, ts) -> bool:
        """True iff timestamp `ts` (ISO str or datetime) is in [start, end).
        A naive/unparseable ts is treated as OUT of range (fail-closed: never
        let a malformed timestamp inflate a count) — except it never raises."""
        try:
            t = parse_iso(ts)
        except Exception:
            return False
        return self.start_utc <= t < self.end_utc

    def vendor_dates(self) -> list[str]:
        """Every vendor-local calendar date 'YYYY-MM-DD' the window touches, in
        order — the buckets for the daily activity timeline. Computed on the
        vendor-local day boundaries so the first/last partial day still appears."""
        tz = _tz(self.tz_name)
        cur = self.start_utc.astimezone(tz).date()
        # end is exclusive: the last touched day is the day of (end - 1 microsecond).
        last = (self.end_utc - timedelta(microseconds=1)).astimezone(tz).date()
        out: list[str] = []
        while cur <= last:
            out.append(cur.isoformat())
            cur = cur + timedelta(days=1)
        return out


def _vendor_midnight_utc(local_date, tz) -> datetime:
    """The UTC instant of 00:00 vendor-local on `local_date`."""
    naive_midnight = datetime(local_date.year, local_date.month, local_date.day)
    local_midnight = naive_midnight.replace(tzinfo=tz)
    return ensure_utc(local_midnight)


def resolve_range(
    preset: str,
    *,
    now: Optional[datetime] = None,
    frm: Optional[str] = None,
    to: Optional[str] = None,
    tz_name: str = VENDOR_TZ_NAME,
) -> DateRange:
    """Resolve a preset (or 'custom' with frm/to) to a half-open UTC window.

    `now` is injectable (tests pin it; prod passes None -> now_utc()). All day
    math happens in the vendor zone, then the boundaries are converted to UTC.

    Presets:
      today        : [vendor-midnight today, vendor-midnight tomorrow)
      yesterday    : [vendor-midnight yesterday, vendor-midnight today)
      7d           : last 7 vendor-days INCLUDING today -> [today-6 00:00, tomorrow 00:00)
      30d          : last 30 vendor-days including today
      this-month   : [1st 00:00 this vendor-month, 1st 00:00 next vendor-month)
      prev-month   : [1st 00:00 prev vendor-month, 1st 00:00 this vendor-month)
      custom       : [frm 00:00 vendor, (to)+1day 00:00 vendor)  — `to` is an
                     INCLUSIVE calendar date the user picked, so the exclusive end
                     is the start of the day AFTER it (covers the whole `to` day).

    Unknown preset -> falls back to 'today' (safe default, never raises)."""
    preset = (preset or "today").strip().lower()
    tz = _tz(tz_name)
    now_local = (now or now_utc()).astimezone(tz)
    today_local = now_local.date()

    def span(start_date, end_date_exclusive) -> DateRange:
        return DateRange(
            preset=preset,
            start_utc=_vendor_midnight_utc(start_date, tz),
            end_utc=_vendor_midnight_utc(end_date_exclusive, tz),
            tz_name=tz_name,
        )

    if preset == "today":
        return span(today_local, today_local + timedelta(days=1))

    if preset == "yesterday":
        return span(today_local - timedelta(days=1), today_local)

    if preset == "7d":
        return span(today_local - timedelta(days=6), today_local + timedelta(days=1))

    if preset == "30d":
        return span(today_local - timedelta(days=29), today_local + timedelta(days=1))

    if preset == "this-month":
        first = today_local.replace(day=1)
        nxt = _add_month(first)
        return span(first, nxt)

    if preset == "prev-month":
        first_this = today_local.replace(day=1)
        first_prev = _sub_month(first_this)
        return span(first_prev, first_this)

    if preset == "custom":
        start_date = _parse_date(frm, default=today_local)
        end_date_incl = _parse_date(to, default=start_date)
        # Guard: if the user inverts the range, swap so it is always well-formed.
        if end_date_incl < start_date:
            start_date, end_date_incl = end_date_incl, start_date
        return span(start_date, end_date_incl + timedelta(days=1))

    # Unknown -> today (never raise).
    return span(today_local, today_local + timedelta(days=1))


def _parse_date(value: Optional[str], *, default):
    """Parse a 'YYYY-MM-DD' calendar date; tolerate a full ISO timestamp by taking
    its date part. Empty/bad -> `default`. Never raises."""
    s = (value or "").strip()
    if not s:
        return default
    try:
        return datetime.fromisoformat(s[:10]).date()
    except Exception:
        return default


def _add_month(d):
    """First-of-next-month for a date that is already the 1st."""
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


def _sub_month(d):
    """First-of-previous-month for a date that is already the 1st."""
    if d.month == 1:
        return d.replace(year=d.year - 1, month=12)
    return d.replace(month=d.month - 1)
