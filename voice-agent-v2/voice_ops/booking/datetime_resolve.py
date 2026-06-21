"""voice_ops.booking.datetime_resolve — PURE date/time resolution for the booking tool.

The AI extracts a loose time reference from the conversation ("kal subah 10 baje", "tomorrow
3pm", "18 June 4:30pm", or an ISO string). This module turns that into a concrete UTC
`datetime` deterministically, so the slot-claim is unambiguous.

PURE: every function takes `now` injected (no hidden clock) so it is unit-testable with zero
infra and reproducible. Returns aware UTC datetimes. NEVER raises — an unparseable reference
returns None and the tool re-asks the prospect.

Scope is deliberately small + robust (not an NLP date library): ISO passthrough, a handful of
English + Hinglish day words (today/tomorrow/aaj/kal/parso), and "<H>[:MM] [am|pm|baje]" times,
plus a "subah/dopahar/shaam/raat" period default. Anything else -> None -> re-ask. The vendor's
resource timezone (default IST) maps local wall time to UTC.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Optional

# day-word -> day offset from `now` (local).
_DAY_WORDS = {
    "today": 0, "aaj": 0, "tonight": 0, "aj": 0,
    "tomorrow": 1, "tmrw": 1, "kal": 1, "kl": 1,
    "parso": 2, "day after tomorrow": 2, "dayaftertomorrow": 2,
}

# period-word -> default hour (24h, local) when only a vague period is given.
_PERIOD_HOUR = {
    "subah": 10, "morning": 10, "saver": 9,
    "dopahar": 13, "noon": 12, "afternoon": 15, "lunch": 13,
    "shaam": 17, "evening": 18, "sham": 17,
    "raat": 20, "night": 20, "rat": 20,
}

_TIME_RE = re.compile(
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm|a\.m\.|p\.m\.)?",
    re.IGNORECASE,
)


def tz_offset_minutes(tz: str) -> int:
    """IANA tz -> current UTC offset minutes. IST(+330) fallback. Pure-ish (uses zoneinfo)."""
    try:
        from zoneinfo import ZoneInfo
        off = _dt.datetime.now(ZoneInfo(tz or "Asia/Kolkata")).utcoffset()
        return int(off.total_seconds() // 60) if off else 330
    except Exception:  # noqa: BLE001
        return 330


def _try_iso(ref: str) -> Optional[_dt.datetime]:
    try:
        s = ref.strip().replace("Z", "+00:00")
        d = _dt.datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def resolve_slot_start(
    ref: str,
    *,
    now: _dt.datetime,
    tz: str = "Asia/Kolkata",
    default_hour: int = 11,
) -> Optional[_dt.datetime]:
    """Resolve a loose human time reference -> an aware UTC datetime, or None.

    `now` is the current instant (inject UTC `datetime`). `tz` is the resource-local timezone
    (the wall-clock the prospect means). If `ref` is already an ISO datetime it is honored as-is
    (assumed UTC if naive). Otherwise we read a day word + a time/period and build the local wall
    time, then convert to UTC by subtracting the tz offset.
    """
    if not (ref or "").strip():
        return None
    # 1) ISO passthrough (an upstream layer may already have a concrete time).
    iso = _try_iso(ref)
    if iso is not None and re.search(r"\d{4}-\d{2}-\d{2}", ref):
        return iso

    text = ref.strip().lower()
    off = tz_offset_minutes(tz)
    # local "now" wall clock
    local_now = now.astimezone(_dt.timezone.utc) + _dt.timedelta(minutes=off)

    # 2) day offset
    day_off = None
    for word, d in _DAY_WORDS.items():
        if word in text:
            day_off = d
            break

    # 3) explicit clock time
    hour: Optional[int] = None
    minute = 0
    m = _TIME_RE.search(text)
    if m and m.group("h"):
        try:
            h = int(m.group("h"))
            mm = int(m.group("m") or 0)
            ap = (m.group("ap") or "").replace(".", "").lower()
            if ap == "pm" and h < 12:
                h += 12
            if ap == "am" and h == 12:
                h = 0
            # bare "shaam 5"/"sham 5"/"5 baje sham" with an evening/afternoon word and no
            # am/pm -> PM bias for an evening-range hour. R6 fix: also match the bare spelling
            # "sham" (not just "shaam") and "dopahar"/"afternoon"/"lunch" — the founder's
            # "kal sham 5 baje" was resolving to 05:00 because only "shaam" was checked.
            _evening = ("shaam" in text or "sham" in text or "evening" in text
                        or "raat" in text or "night" in text)
            _afternoon = ("dopahar" in text or "afternoon" in text or "lunch" in text
                          or "noon" in text)
            if not ap and _evening and 1 <= h <= 11:
                h += 12
            elif not ap and _afternoon and 1 <= h <= 5:
                h += 12  # "dopahar 2/3 baje" -> 14:00/15:00 (not 02:00/03:00)
            if 0 <= h <= 23 and 0 <= mm <= 59:
                hour, minute = h, mm
        except Exception:  # noqa: BLE001
            hour = None

    # 4) period default if no explicit time
    if hour is None:
        for word, ph in _PERIOD_HOUR.items():
            if word in text:
                hour = ph
                break

    # If we have neither a day word NOR any time signal, it's unparseable.
    if day_off is None and hour is None:
        return None
    if day_off is None:
        day_off = 0
    if hour is None:
        hour = default_hour

    local_day = (local_now + _dt.timedelta(days=day_off)).date()
    local_dt = _dt.datetime(local_day.year, local_day.month, local_day.day, hour, minute,
                            tzinfo=_dt.timezone.utc)  # treat as local wall time tagged UTC
    # If the chosen local time is already in the past for "today", bump to tomorrow (don't book past).
    if day_off == 0:
        local_now_naive = local_now.replace(tzinfo=_dt.timezone.utc)
        if local_dt <= local_now_naive:
            local_dt = local_dt + _dt.timedelta(days=1)
    # local wall -> UTC
    return local_dt - _dt.timedelta(minutes=off)


def humanize_slot(slot_start_iso: str, *, tz: str = "Asia/Kolkata") -> str:
    """Render a UTC ISO slot start as a short vendor-local phrase, e.g. '18 Jun, 4:00 PM'.
    Used in the spoken confirmation. Best-effort; returns the raw iso on failure."""
    try:
        d = _try_iso(slot_start_iso)
        if d is None:
            return slot_start_iso
        local = d + _dt.timedelta(minutes=tz_offset_minutes(tz))
        return local.strftime("%d %b, %I:%M %p").lstrip("0")
    except Exception:  # noqa: BLE001
        return slot_start_iso
