"""voice_kernel.events.timeutil — the canonical timestamp / timezone layer.

THE FOUNDER BUG ("timeline shows 1 day ago for a call just now"): a timestamp
crosses a layer WITHOUT an unambiguous UTC marker, so the receiving side parses a
naive string in a DIFFERENT zone (or as local), and a call placed at 00:30 IST
(= 19:00 UTC the *previous* day) renders as "yesterday". The fix is one rule,
enforced in one place:

    STORE in UTC, with an explicit offset/Z marker. RENDER in the vendor's
    timezone (Asia/Kolkata) at the edge. NEVER store or pass a naive datetime.

Downstream waves (dashboard/CRM/analytics/reports, and the Python side of the
panel API) reuse these helpers so the same canonical contract holds everywhere.
The JS/Next.js render side mirrors this with `Intl.DateTimeFormat` + an explicit
IANA `timeZone` (see design/W8-EVENT-SEAM.md) — same rule, both languages.

Pure stdlib (datetime + zoneinfo). zoneinfo ships in Python 3.9+; on a stripped
host without the tz database we fall back to a fixed +05:30 offset for
Asia/Kolkata (India has no DST, so the fixed offset is exact) — render never
crashes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Union

try:  # zoneinfo is stdlib (3.9+); fall back to fixed offset if tzdata absent.
    from zoneinfo import ZoneInfo  # type: ignore
except Exception:  # pragma: no cover - very old/stripped runtime
    ZoneInfo = None  # type: ignore

# India Standard Time is a fixed UTC+05:30 (no DST) — exact fallback when the
# IANA tz database is unavailable on the host.
_IST_FIXED = timezone(timedelta(hours=5, minutes=30), name="IST")
VENDOR_TZ_NAME = "Asia/Kolkata"


def _tz(name: str) -> timezone | "ZoneInfo":
    """Resolve an IANA tz name; degrade Asia/Kolkata to the exact fixed offset if
    zoneinfo/tzdata is missing. Any other name with no tzdata falls back to UTC
    (safe, explicit) rather than raising."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    if name == VENDOR_TZ_NAME:
        return _IST_FIXED
    return timezone.utc


def now_utc() -> datetime:
    """Timezone-AWARE current UTC instant. The only sanctioned 'now'."""
    return datetime.now(timezone.utc)


def now_utc_iso() -> str:
    """Canonical wire timestamp: UTC, ISO-8601, ALWAYS Z-suffixed.

    e.g. '2026-06-18T19:00:30.123456Z'. The trailing 'Z' is the unambiguous UTC
    marker whose absence causes the '1 day ago' bug. Millisecond+ precision is
    fine; the Z is the load-bearing part."""
    return _to_z(now_utc())


def _to_z(dt: datetime) -> str:
    """Render an aware UTC datetime as '...Z' (replace the '+00:00' offset)."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_utc(dt: datetime) -> datetime:
    """Coerce ANY datetime to aware-UTC. A NAIVE datetime is ASSUMED to already be
    UTC (the storage contract: we only ever store UTC). This is the chokepoint
    that prevents a naive value from being silently reinterpreted as local."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso(value: Union[str, datetime]) -> datetime:
    """Parse a stored timestamp to aware-UTC. Accepts a datetime (coerced),
    a 'Z'-suffixed ISO string, or an offset ISO string. A naive ISO string (no
    offset, no Z) is treated as UTC per the storage contract — NOT local. This is
    exactly where the bug used to enter; here it is closed."""
    if isinstance(value, datetime):
        return ensure_utc(value)
    s = (value or "").strip()
    if not s:
        raise ValueError("parse_iso: empty timestamp")
    # Accept trailing Z (datetime.fromisoformat handles 'Z' only on 3.11+).
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return ensure_utc(dt)


def to_vendor(value: Union[str, datetime], tz_name: str = VENDOR_TZ_NAME) -> datetime:
    """The RENDER primitive: take a stored UTC value, return an aware datetime in
    the vendor's wall-clock zone (default Asia/Kolkata). This is what makes a
    19:00Z timestamp correctly show as the next-day 00:30 IST instead of staying
    'yesterday'."""
    return parse_iso(value).astimezone(_tz(tz_name))


def render_vendor(value: Union[str, datetime], tz_name: str = VENDOR_TZ_NAME, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """Human-readable vendor-local string (default 'YYYY-MM-DD HH:MM' in IST)."""
    return to_vendor(value, tz_name).strftime(fmt)


def vendor_date(value: Union[str, datetime], tz_name: str = VENDOR_TZ_NAME) -> str:
    """The vendor-local CALENDAR DATE ('YYYY-MM-DD'). This is the exact value the
    'X days ago' / day-grouping logic must use — computing the date in UTC is the
    root cause of the off-by-one. Group/relative-time MUST use this."""
    return to_vendor(value, tz_name).strftime("%Y-%m-%d")


def humanize(value: Union[str, datetime], now: Optional[datetime] = None, tz_name: str = VENDOR_TZ_NAME) -> str:
    """Relative-time label ('just now', '5 min ago', 'today HH:MM', 'yesterday
    HH:MM', else vendor date) computed in the VENDOR zone — the correct,
    bug-free version of the timeline label. Both the event time and 'now' are
    normalized to vendor-local before any day comparison."""
    event_local = to_vendor(value, tz_name)
    now_local = (now or now_utc()).astimezone(_tz(tz_name))
    delta = now_local - event_local
    secs = delta.total_seconds()
    if secs < 0:
        # Clock skew / future timestamp: clamp to 'just now' rather than show a
        # nonsense negative.
        return "just now"
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    # Day comparison is on VENDOR-LOCAL calendar dates (the actual fix).
    days = (now_local.date() - event_local.date()).days
    if days == 0:
        return f"today {event_local.strftime('%H:%M')}"
    if days == 1:
        return f"yesterday {event_local.strftime('%H:%M')}"
    return event_local.strftime("%Y-%m-%d")
