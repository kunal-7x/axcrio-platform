"""voice_ops.telephony.window — the CallingWindowScheduler (W12 #6).

Decides, at any instant, whether a campaign may dial RIGHT NOW, and when it next may —
so a campaign runs ONLY inside its calling window and pauses/resumes cleanly across
days (a 5000-lead list that can't clear in one window spills to tomorrow's window, it
does not dial at 2 AM). This is the tracked, offline-testable twin of caller.py's
`_in_window` / `_clamp_to_window` (caller.py:862), extended with:

  * recipient-local-aware evaluation (default Asia/Kolkata; a future tz column per
    number/lead plugs in here);
  * the COMPLIANCE LEGAL HARD FLOOR — the window a tenant configures is INTERSECTED
    with the legal floor (voice_ops.compliance.window_floor) so a tenant can only ever
    NARROW the legal window, never widen past it. This is wired LAZILY (so telephony
    has no hard dependency on compliance and stays importable alone) and is only applied
    when COMPLIANCE_ENABLED is on — otherwise the tenant window is honoured verbatim
    (resting build byte-identical).

`decide(campaign, now)` -> WindowDecision{in_window, reason, next_open_iso}. The seam
uses `in_window` exactly where caller.py:2889 already computes it; when out of window
the dial worker sleeps and re-checks (the existing caller.py:2896 pattern), so a paused
campaign resumes itself when its window opens the next day — no cron needed.

PURE: stdlib (datetime + optional zoneinfo); NEVER raises into the dial loop (a bad
window string -> closed, fail-safe: don't dial when the window is unparseable).
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from .config import TelephonyOpsConfig

log = logging.getLogger("voice_ops.telephony.window")


def _tz(name: str):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name or "Asia/Kolkata")
    except Exception:  # noqa: BLE001 — no tzdata -> fall back to a fixed +05:30 IST offset
        return _dt.timezone(_dt.timedelta(hours=5, minutes=30))


def _parse_hhmm(s: str, default: Tuple[int, int]) -> Tuple[int, int]:
    try:
        hh, mm = (s or "").strip().split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except Exception:  # noqa: BLE001
        pass
    return default


@dataclass(frozen=True)
class WindowDecision:
    """Whether dialing is allowed now + when the window next opens (ISO, recipient-local
    rendered as UTC instant)."""
    in_window: bool
    reason: str
    start_hhmm: str            # the EFFECTIVE (post-floor) window start applied
    end_hhmm: str              # the EFFECTIVE window end applied
    next_open_iso: Optional[str] = None   # UTC ISO of the next time the window opens (when closed)


class CallingWindowScheduler:
    """Stateless window evaluator. Construct once: `CallingWindowScheduler(cfg)`."""

    def __init__(self, cfg: Optional[TelephonyOpsConfig] = None):
        self.cfg = cfg or TelephonyOpsConfig.from_env()

    def effective_window(
        self, *, start: str, end: str, vertical: str = "",
        apply_legal_floor: bool = False,
    ) -> Tuple[Tuple[int, int], Tuple[int, int], str]:
        """Resolve the EFFECTIVE (h,m) start/end after the legal-floor intersection.
        When `apply_legal_floor` is True we lazily call the compliance window_floor to
        clamp — a tenant can only NARROW, never widen. Returns ((sh,sm),(eh,em), note)."""
        s = _parse_hhmm(start, (9, 0))
        e = _parse_hhmm(end, (21, 0))
        note = "tenant_window"
        if apply_legal_floor:
            try:
                from voice_ops.compliance.window_floor import clamp_to_legal_floor
                (s, e), note = clamp_to_legal_floor(s, e, vertical=vertical)
            except Exception as exc:  # noqa: BLE001 — compliance absent/CI -> honour tenant window
                log.info("window: legal-floor clamp unavailable (%r) — tenant window verbatim", exc)
        return s, e, note

    def decide(
        self, *, start: str = "09:00", end: str = "21:00", tz_name: str = "",
        vertical: str = "", apply_legal_floor: bool = False,
        now: Optional[_dt.datetime] = None,
    ) -> WindowDecision:
        """Is dialing allowed right now for a campaign with this window? Computes the
        effective (floor-clamped) window, evaluates it in the recipient tz, and — when
        closed — the next instant it opens (today or tomorrow). NEVER raises."""
        tzinfo = _tz(tz_name or self.cfg.default_tz)
        now = (now or _dt.datetime.now(_dt.timezone.utc)).astimezone(tzinfo)
        (sh, sm), (eh, em), note = self.effective_window(
            start=start, end=end, vertical=vertical, apply_legal_floor=apply_legal_floor)

        # An empty/degenerate window (start >= end) is treated as CLOSED (fail-safe).
        start_minutes = sh * 60 + sm
        end_minutes = eh * 60 + em
        cur_minutes = now.hour * 60 + now.minute
        eff_start = f"{sh:02d}:{sm:02d}"
        eff_end = f"{eh:02d}:{em:02d}"

        if end_minutes <= start_minutes:
            nxt = self._next_open(now, sh, sm, tzinfo)
            return WindowDecision(False, f"degenerate_window({note})", eff_start, eff_end,
                                  nxt.astimezone(_dt.timezone.utc).isoformat())

        if start_minutes <= cur_minutes < end_minutes:
            return WindowDecision(True, f"in_window({note})", eff_start, eff_end, None)

        nxt = self._next_open(now, sh, sm, tzinfo)
        reason = "before_window" if cur_minutes < start_minutes else "after_window"
        return WindowDecision(False, f"{reason}({note})", eff_start, eff_end,
                              nxt.astimezone(_dt.timezone.utc).isoformat())

    @staticmethod
    def _next_open(now_local: _dt.datetime, sh: int, sm: int, tzinfo) -> _dt.datetime:
        """The next datetime (recipient-local) at which the window opens: today at
        (sh:sm) if still ahead, else tomorrow at (sh:sm)."""
        today_open = now_local.replace(hour=sh, minute=sm, second=0, microsecond=0)
        if now_local < today_open:
            return today_open
        return today_open + _dt.timedelta(days=1)
