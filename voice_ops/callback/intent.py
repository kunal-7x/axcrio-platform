"""voice_ops.callback.intent — "call me at X" natural-time -> exact ISO instant.

When a lead says "call me at 5pm" / "call tomorrow morning" / "ring me Sunday" /
"baad mein call karna 4 baje", that is the HIGHEST-PRIORITY callback signal — it
is the customer's own stated intent, not a retry. The cadence engine schedules it
at THAT wall-clock time (in the vendor tz, IST) and honors it even after a pickup.

This module turns a free-text preferred-callback phrase (the LLM transcript's
`callback_at`, which may already be ISO, OR a loose natural phrase) into an aware
UTC ISO instant, anchored to a `now` reference. It is deliberately conservative:
  * if the phrase is ALREADY a valid ISO timestamp, we just normalize it to UTC;
  * else we parse a small, high-precision grammar (clock times, am/pm, Hinglish
    "baje", relative day words EN + Hinglish, weekdays, "morning/afternoon/...");
  * if we cannot confidently parse, we return None (the caller falls back to the
    normal cadence — we NEVER guess a wrong time and spam the lead).

Pure stdlib + voice_kernel.events.timeutil. ZERO droplet_work imports.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Optional

from voice_kernel.events.timeutil import (
    VENDOR_TZ_NAME,
    _tz,                # internal tz resolver (IST with fixed-offset fallback)
    ensure_utc,
    now_utc,
    parse_iso,
)

# Parts-of-day -> a representative local hour (24h).
_PART_OF_DAY = {
    "morning": 10, "subah": 10, "subeh": 10,
    "noon": 12, "dopahar": 13, "afternoon": 15,
    "evening": 18, "shaam": 18, "sham": 18,
    "night": 20, "raat": 20, "tonight": 20,
}

# Weekday name -> Python weekday() index (Mon=0).
_WEEKDAYS = {
    "monday": 0, "mon": 0, "somvar": 0,
    "tuesday": 1, "tue": 1, "tues": 1, "mangalvar": 1,
    "wednesday": 2, "wed": 2, "budhvar": 2,
    "thursday": 3, "thu": 3, "thurs": 3, "guruvar": 3,
    "friday": 4, "fri": 4, "shukravar": 4,
    "saturday": 5, "sat": 5, "shanivar": 5,
    "sunday": 6, "sun": 6, "ravivar": 6, "itwar": 6,
}

# Default fallback hour when a day is named but no time is given.
_DEFAULT_HOUR = 11

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
# "5pm", "5 pm", "5:30 pm", "17:00", "4 baje", "4 बजे"
_CLOCK_RE = re.compile(
    r"(?<!\d)(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|am|pm|baje|baj|बजे)?",
    re.IGNORECASE,
)


def _vendor_now(now: Optional[datetime], tz_name: str) -> datetime:
    base = now or now_utc()
    return ensure_utc(base).astimezone(_tz(tz_name))


def _clamp_to_future(dt_local: datetime, ref_local: datetime) -> datetime:
    """If the parsed local time is already in the past relative to ref, push it to
    the next sensible occurrence (next day for a clock time) so 'call at 5pm' said
    at 6pm means 5pm TOMORROW, never 5pm today (which would fire immediately)."""
    if dt_local <= ref_local:
        return dt_local + timedelta(days=1)
    return dt_local


def _resolve_hour(hour: int, minute: int, ampm: Optional[str], text: str) -> Optional[tuple[int, int]]:
    ampm = (ampm or "").replace(".", "").lower()
    if ampm in ("am",):
        if hour == 12:
            hour = 0
    elif ampm in ("pm",):
        if hour != 12:
            hour += 12
    elif ampm in ("baje", "baj", "बजे", ""):
        # Hinglish "baje" / bare number: infer am/pm from context words. Business
        # calling hours bias afternoon/evening for ambiguous 1-7.
        if "morning" in text or "subah" in text or "subeh" in text:
            pass
        elif 1 <= hour <= 7:
            hour += 12  # "4 baje" in a sales-callback context => 16:00
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def parse_callback_time(
    phrase: str,
    now: Optional[datetime] = None,
    tz_name: str = VENDOR_TZ_NAME,
) -> Optional[str]:
    """Parse a preferred-callback phrase to an aware UTC ISO 'Z' string, or None.

    `now` is the reference instant (defaults to now_utc()); `tz_name` is the
    vendor wall-clock zone the lead spoke in (IST). The returned ISO is in UTC so
    it stores/compares canonically (W8 timeutil contract). None => not confidently
    parseable => the caller uses the normal cadence (never a wrong-time spam)."""
    s = (phrase or "").strip()
    if not s:
        return None

    # 1. Already ISO? Normalize to UTC and return (the LLM often emits ISO).
    if _ISO_RE.match(s):
        try:
            return parse_iso(s).isoformat().replace("+00:00", "Z")
        except (ValueError, TypeError):
            pass

    low = s.lower()
    ref_local = _vendor_now(now, tz_name)
    tz = _tz(tz_name)

    # 2. Establish the target DAY.
    target_date = ref_local.date()
    day_set = False
    if "day after tomorrow" in low or "parso" in low or "parson" in low:
        target_date = ref_local.date() + timedelta(days=2)
        day_set = True
    elif "tomorrow" in low or "kal" in low or "agle din" in low:
        target_date = ref_local.date() + timedelta(days=1)
        day_set = True
    elif "today" in low or "aaj" in low or "tonight" in low:
        target_date = ref_local.date()
        day_set = True
    else:
        for name, wd in _WEEKDAYS.items():
            # word-boundary match so 'sun' doesn't hit 'sunday' twice / substrings
            if re.search(rf"\b{name}\b", low):
                delta = (wd - ref_local.weekday()) % 7
                delta = delta or 7  # "on monday" said on monday => next monday
                target_date = ref_local.date() + timedelta(days=delta)
                day_set = True
                break

    # 3. Establish the target TIME.
    hour: Optional[int] = None
    minute = 0

    m = _CLOCK_RE.search(low)
    if m and m.group(1) is not None and (m.group(3) or m.group(2) or re.search(r"\b(at|by|around|call)\b", low)):
        h = int(m.group(1))
        mm = int(m.group(2)) if m.group(2) else 0
        resolved = _resolve_hour(h, mm, m.group(3), low)
        if resolved:
            hour, minute = resolved

    if hour is None:
        for word, h in _PART_OF_DAY.items():
            if word in low:
                hour = h
                break

    # 4. Need at least a day OR a time to be confident.
    if hour is None and not day_set:
        return None
    if hour is None:
        hour = _DEFAULT_HOUR  # a named day with no time -> late-morning default

    dt_local = datetime.combine(target_date, time(hour=hour, minute=minute), tzinfo=tz)

    # 5. If only a clock time was given (no explicit day) and it's already past,
    #    roll to tomorrow so we never schedule into the past.
    if not day_set:
        dt_local = _clamp_to_future(dt_local, ref_local)

    return ensure_utc(dt_local).isoformat().replace("+00:00", "Z")
