"""ads_engine.learning_phase — LEARNING-PHASE state, awareness + the "do-not-edit" lock (V2-W3).

Every autonomous ad platform has a learning period it must clear before delivery stabilizes — Meta: ~50
conversions / 7 days per ad set; Google PMax: ~30-50 conversions / 30 days — and a >20% structural edit
RESETS that clock (research/comp-autonomy.md §"learning phase" + gap #6). Competitors surface this loudly
("you're in learning, don't change anything"); we surface nothing and our optimizer could thrash a
still-learning campaign. This module computes the phase from the live ad_events, exposes it for the UI, and
drives the SAME `learning_lock` the guardrail chain already honours (so discretionary kill/scale defer
until the campaign has real signal — REDTEAM C4 keeps SAFETY pauses exempt).

EARNER-SAFE: pure phase math + a state/guardrail write only (learning_lock is a PROPOSE-side gate, never a
spend). No network, no caller import. Deterministic + offline-testable. Never raises into the daemon.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from . import ad_events as _ev, store

_log = logging.getLogger("ads_engine.learning_phase")

# ---------------------------------------------------------------------------
# Provider thresholds: (conversions_needed, window_days). Researched floors; a campaign that hasn't met
# the conversion count within the window is "limited" (stuck) — a signal to fix structure, not to thrash.
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "meta": (50, 7),
    "whatsapp": (50, 7),
    "google": (30, 30),    # PMax ~30-50 conv / 30d rolling — use the 30 floor
    "default": (50, 7),
}

PHASE_LEARNING = "learning"            # below threshold, still inside the window — DO NOT EDIT
PHASE_LIMITED = "learning_limited"     # past the window, still below threshold — structurally stuck
PHASE_ACTIVE = "active"                # threshold met — optimizer free to kill/scale

# The conversion rungs that count toward exiting learning (real optimization events, NOT form-fills).
_COUNTING_EVENTS = frozenset({_ev.EV_LEAD_QUALIFIED, _ev.EV_HOT,
                              _ev.EV_SITE_VISIT_BOOKED, _ev.EV_BOOKING})


def thresholds_for(provider: str) -> tuple:
    return THRESHOLDS.get(str(provider or "").strip().lower(), THRESHOLDS["default"])


def count_conversions(events: list, *, campaign_id: Optional[str] = None,
                      window_s: Optional[float] = None, now_ts: Optional[float] = None,
                      counting_events: Optional[frozenset] = None) -> int:
    """Count the conversions that exit learning (quality rungs by default) within an optional window."""
    cnt = 0
    counting = counting_events or _COUNTING_EVENTS
    floor_ts = None
    if window_s is not None:
        floor_ts = float(now_ts if now_ts is not None else time.time()) - float(window_s)
    for e in events or []:
        if campaign_id is not None and str(e.get("campaign_id") or e.get("source_campaign_id")) != str(campaign_id):
            continue
        if floor_ts is not None and float(e.get("ts", 0) or 0) < floor_ts:
            continue
        if str(e.get("type") or "").strip().lower() in counting:
            cnt += 1
    return cnt


def evaluate(conv_count: int, *, provider: str = "meta", started_ts: Optional[float] = None,
             now_ts: Optional[float] = None, threshold_override: Optional[int] = None) -> dict:
    """Compute the learning-phase verdict for ONE campaign. Pure; deterministic.

    Returns {phase, do_not_edit, conversions, threshold, window_days, days_elapsed, progress_pct,
    remaining, message}. `do_not_edit` is True while learning/limited (discretionary edits reset the
    clock); the daemon mirrors it into guardrail_state.learning_lock."""
    threshold, window_days = thresholds_for(provider)
    if threshold_override is not None:
        try:
            threshold = max(1, int(threshold_override))
        except Exception:  # noqa: BLE001
            pass
    now = float(now_ts if now_ts is not None else time.time())
    days_elapsed = ((now - float(started_ts)) / 86400.0) if started_ts else 0.0
    conv = max(0, int(conv_count))
    progress = min(1.0, conv / threshold) if threshold else 1.0
    remaining = max(0, threshold - conv)
    if conv >= threshold:
        phase, dne = PHASE_ACTIVE, False
        msg = (f"Active — {conv}/{threshold} conversions met; the optimizer can now scale winners and "
               "cut losers.")
    elif days_elapsed <= window_days:
        phase, dne = PHASE_LEARNING, True
        msg = (f"Learning — {conv}/{threshold} conversions in the first {window_days}d. Do not edit "
               f"budget/targeting >20% or the learning clock resets. ~{remaining} conversions to go.")
    else:
        phase, dne = PHASE_LIMITED, True
        msg = (f"Learning limited — only {conv}/{threshold} conversions after {days_elapsed:.0f}d "
               f"(window {window_days}d). Delivery is unstable; fix structure (budget/audience/creative) "
               "rather than nudging settings.")
    return {"phase": phase, "do_not_edit": dne, "conversions": conv, "threshold": threshold,
            "window_days": window_days, "days_elapsed": round(days_elapsed, 1),
            "progress_pct": round(progress * 100, 1), "remaining": remaining, "message": msg,
            "provider": str(provider or "meta").lower()}


def apply_learning_lock(tenant_id: str, campaign_id: str, verdict: dict) -> bool:
    """Mirror the phase verdict into guardrail_state.learning_lock (CAS) so the fail-closed chain defers
    discretionary kill/scale during learning. SAFETY pauses stay exempt (handled in guardrails, REDTEAM
    C4). Returns True on write. Never raises — a failure leaves the existing lock untouched."""
    try:
        existing = store.get_guardrail_state(tenant_id, campaign_id) or {}
        merged = dict(existing)
        merged["learning_lock"] = bool(verdict.get("do_not_edit"))
        merged["learning_phase"] = verdict.get("phase")
        merged["conv_7d"] = verdict.get("conversions")
        merged["min_conv"] = verdict.get("threshold")
        ver = int(existing.get("version", 0) or 0) if isinstance(existing, dict) else None
        store.put_guardrail_state(tenant_id, campaign_id, merged, expected_version=ver)
        return True
    except store.VersionConflict:
        _log.info("learning_phase.apply_learning_lock: CAS conflict %s/%s (retry next tick)",
                  tenant_id, campaign_id)
        return False
    except Exception as exc:  # noqa: BLE001
        _log.warning("learning_phase.apply_learning_lock failed: %r", type(exc).__name__)
        return False


def refresh(tenant_id: str, campaign_id: str, *, provider: str = "meta",
            started_ts: Optional[float] = None, now_ts: Optional[float] = None,
            persist: bool = True, apply_lock: bool = True) -> dict:
    """Recompute a campaign's learning phase from the live ad_events, persist the learning_state row (for
    the UI) and (optionally) mirror the lock into guardrail_state. Returns the verdict. Never raises."""
    try:
        threshold, window_days = thresholds_for(provider)
        events = store.get_ad_events(tenant_id)
        conv = count_conversions(events, campaign_id=campaign_id,
                                 window_s=window_days * 86400, now_ts=now_ts)
        verdict = evaluate(conv, provider=provider, started_ts=started_ts, now_ts=now_ts)
        if persist:
            try:
                row = dict(verdict)
                row["campaign_id"] = campaign_id
                row["updated_ts"] = float(now_ts if now_ts is not None else time.time())
                store.put_row(tenant_id, "learning_state", campaign_id, row)
            except Exception:  # noqa: BLE001
                pass
        if apply_lock:
            apply_learning_lock(tenant_id, campaign_id, verdict)
        return verdict
    except Exception as exc:  # noqa: BLE001
        _log.warning("learning_phase.refresh failed: %r", type(exc).__name__)
        return {"phase": PHASE_LEARNING, "do_not_edit": True, "message": "learning (compute error)"}


def status(tenant_id: str, campaign_id: str) -> dict:
    """UI-facing read: the last persisted learning_state row, or a fresh compute if none exists yet."""
    try:
        row = store.get_row(tenant_id, "learning_state", campaign_id)
        if isinstance(row, dict) and row:
            return row
    except Exception:  # noqa: BLE001
        pass
    return refresh(tenant_id, campaign_id, persist=False, apply_lock=False)


__all__ = ["evaluate", "count_conversions", "refresh", "status", "apply_learning_lock",
           "thresholds_for", "THRESHOLDS", "PHASE_LEARNING", "PHASE_LIMITED", "PHASE_ACTIVE"]
