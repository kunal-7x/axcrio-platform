"""trunk_registry.rotation — DID rotation + spam-reputation quarantine guard (T2, NEW).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.5 (number rotation + spam-reputation guard,
CORRECTED to a signal that EXISTS) + §3 red-team B-rel / B3 / B (rel) / Velocity / E.

THE CORE RED-TEAM CORRECTION (B-rel) — load-bearing:
  The dial uses `wait_until_answered=False` (caller.py:2916) and returns immediately; the outcome
  is inferred from DURATION + transcript in `_classify_outcome` (caller.py:1551). There is NO
  486/480/603 SIP code captured anywhere in caller.py. So the ORIGINAL "quarantine on a 486 burst"
  guard could NEVER fire. The corrected, fireable signal is:

      a BURST of ZERO-DURATION RING-OUTS on a DID within a rolling window.

  `note_call_outcome(...)` is fed the (duration, answered) the dial loop already computes; a
  zero-duration unanswered call is logged as a `ring_out` health event. When the count of
  `ring_out` events for a DID in the window crosses the threshold, the trunk is QUARANTINED
  (quarantined_until set in PG) — spam-rest. (A cleaner long-term signal is real SIP-webhook /
  participant-disconnected plumbing — that is an explicit FUTURE build sub-task, NOT assumed
  present here.)

ESCALATION, NOT SILENT POOL-BURN (red-team B3):
  >= K quarantine events on ONE trunk in the window -> DISABLE the trunk (is_enabled=false) +
  emit a loud compliance alert. Do NOT keep rotating to the next 10-digit DID — that just burns
  the whole pool one number at a time while hiding the root cause (exactly what blocked
  +918071583488, now automated across N numbers). The alert is the LOUD part.

DID SELECTION:
  `pick_did(trunk, ...)` chooses the next caller-ID from the trunk's did_pool by the trunk's
  rotation_strategy (round_robin | least_used | sticky). Round-robin state is in-process (one
  worker -> authoritative). A reputation-aware caller can pass `avoid` (DIDs currently in a bad
  state) so a fresh DID is never fed into a campaign already throwing failures (§2.5 death-spiral
  guard).

This module's PG mutations (quarantine, disable) go through store.py (RLS-scoped, audited). It
NEVER imports agent.py, NEVER dials, NEVER raises into the caller. A test injects a fake clock +
a fake store.
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from . import store as _store
from .config import registry_config
from .schema import RotationStrategy, SipTrunk

_log = logging.getLogger("trunk_registry.rotation")

# in-process round-robin cursor + least-used counters (one worker -> authoritative).
_LOCK = threading.Lock()
_RR_CURSOR: Dict[str, int] = {}          # trunk_id -> next index into did_pool
_DID_USE: Dict[str, int] = {}            # (trunk_id::did) -> lifetime selection count (least_used)


# A compliance-alert sink (injectable). Default logs LOUDLY; T3 wires a real Telegram/audit hook.
AlertSink = Callable[[str, dict], None]


def _default_alert(kind: str, detail: dict) -> None:
    _log.error("TRUNK COMPLIANCE ALERT [%s]: %s", kind, {k: v for k, v in detail.items()
                                                          if k not in ("secret",)})


# ---------------------------------------------------------------------------
# DID selection.
# ---------------------------------------------------------------------------
def pick_did(trunk: SipTrunk, *, avoid: Optional[List[str]] = None) -> Optional[str]:
    """Choose the next caller-ID for this trunk per its rotation_strategy, skipping any DID in
    `avoid` (reputation-aware — never feed a known-bad DID into a campaign). Returns None if the
    pool is empty or every DID is avoided. In-process round-robin/least-used state."""
    pool = [d for d in trunk.dids if d and (not avoid or d not in avoid)]
    if not pool:
        return None
    strat = trunk.rotation_strategy
    strat = strat.value if isinstance(strat, RotationStrategy) else str(strat or "round_robin")
    tid = str(trunk.id or trunk.slug or "")
    with _LOCK:
        if strat == RotationStrategy.STICKY.value:
            chosen = pool[0]
        elif strat == RotationStrategy.LEAST_USED.value:
            chosen = min(pool, key=lambda d: _DID_USE.get(f"{tid}::{d}", 0))
        else:  # round_robin (default)
            cur = _RR_CURSOR.get(tid, 0)
            chosen = pool[cur % len(pool)]
            _RR_CURSOR[tid] = (cur + 1) % len(pool)
        _DID_USE[f"{tid}::{chosen}"] = _DID_USE.get(f"{tid}::{chosen}", 0) + 1
        return chosen


# ---------------------------------------------------------------------------
# Spam-reputation: log an outcome, quarantine on a ring-out burst, escalate to disable.
# ---------------------------------------------------------------------------
@dataclass
class OutcomeResult:
    """What note_call_outcome decided (for the dial loop's diagnostics + the test)."""
    logged: bool = False
    quarantined: bool = False
    disabled: bool = False
    reason: str = ""


def note_call_outcome(
    tenant_id: str,
    trunk: SipTrunk,
    did: str,
    duration_s: float,
    answered: bool,
    *,
    now_fn: Callable[[], _dt.datetime] = None,
    alert: AlertSink = None,
    store=None,
) -> OutcomeResult:
    """Feed a completed call's outcome to the reputation guard (red-team B-rel). A ZERO-DURATION
    UNANSWERED call is the fireable spam signal (caller.py never captures the 486). On a burst,
    QUARANTINE the trunk; on >= K quarantines, DISABLE it + ALERT (B3).

      * duration_s : the call's connected duration (0 for a ring-out / immediate carrier reject).
      * answered   : whether the call was answered (from the dial loop's _classify_outcome).

    Returns an OutcomeResult. NEVER raises into the dial loop (best-effort; swallows store errors).
    `store`/`alert`/`now_fn` are injectable for the offline test."""
    st = store or _store
    alert = alert or _default_alert
    now = (now_fn or (lambda: _dt.datetime.now(_dt.timezone.utc)))()
    cfg = registry_config()
    res = OutcomeResult()
    trunk_id = str(trunk.id or "")
    if not trunk_id:
        return res

    is_ringout = (not answered) and (float(duration_s or 0) <= 0.0)
    event = "ring_out" if is_ringout else ("connected" if answered else "no_answer")
    try:
        st.write_health_row(tenant_id, trunk_id, event=event, did=did,
                            is_healthy=bool(answered), latency_ms=0,
                            error_code=("zero_duration_ringout" if is_ringout else ""))
        res.logged = True
    except Exception:  # noqa: BLE001 — best-effort
        pass

    if not is_ringout:
        return res

    # Count ring-outs for this DID in the rolling window; quarantine the trunk on a burst.
    window_s = int(cfg["ringout_burst_window_s"])
    threshold = int(cfg["ringout_burst_threshold"])
    try:
        ringouts = st.recent_did_ringouts(tenant_id, trunk_id, did, window_s)
    except Exception:  # noqa: BLE001
        ringouts = 0
    if ringouts < threshold:
        res.reason = f"ringouts={ringouts}<thr={threshold}"
        return res

    # ---- QUARANTINE the trunk (spam-rest) ----
    quarantine_until = now + _dt.timedelta(minutes=int(cfg["quarantine_minutes"]))
    try:
        st.set_quarantine(tenant_id, trunk_id, quarantine_until)
        st.write_health_row(tenant_id, trunk_id, event="quarantine", did=did,
                            is_healthy=False, error_code="ringout_burst")
        res.quarantined = True
        res.reason = f"quarantined: ringouts={ringouts}>=thr={threshold}"
        alert("trunk_quarantined", {"tenant_id": tenant_id, "trunk_id": trunk_id,
                                    "slug": trunk.slug, "did": did, "ringouts": ringouts,
                                    "until": quarantine_until.isoformat()})
    except Exception as exc:  # noqa: BLE001
        _log.warning("rotation: quarantine write failed for %s: %r", trunk.slug, type(exc).__name__)
        return res

    # ---- ESCALATION (red-team B3): >= K quarantines on this trunk -> DISABLE + LOUD alert ----
    disable_at = int(cfg["trunk_disable_quarantines"])
    try:
        q_count = st.count_trunk_quarantines(tenant_id, trunk_id, window_s)
    except Exception:  # noqa: BLE001
        q_count = 0
    if disable_at > 0 and q_count >= disable_at:
        try:
            st.soft_disable_trunk(tenant_id, trunk_id)
            res.disabled = True
            res.reason = (f"DISABLED: {q_count} quarantines >= {disable_at} — stop rotating, "
                          "fix the root cause (compliance/route)")
            alert("trunk_disabled_pool_burn_guard",
                  {"tenant_id": tenant_id, "trunk_id": trunk_id, "slug": trunk.slug,
                   "quarantines": q_count, "threshold": disable_at,
                   "action": "trunk disabled — do NOT keep rotating the DID pool; this is the "
                             "+918071583488 pattern automated across numbers. Fix the route/DLT."})
        except Exception as exc:  # noqa: BLE001
            _log.warning("rotation: disable write failed for %s: %r", trunk.slug, type(exc).__name__)
    return res


def manual_quarantine_did(tenant_id: str, trunk: SipTrunk, did: str, minutes: int = None,
                          *, now_fn: Callable[[], _dt.datetime] = None, store=None) -> bool:
    """The §3.E real-time per-DID/trunk kill switch (independent of the master flag). A founder
    can 'rest this number' from the UI. Quarantines the trunk now + logs the event. Returns True
    on success. (Per-DID granular quarantine columns are a future add; today this rests the trunk
    carrying the DID, which is the safe, conservative action.)"""
    st = store or _store
    now = (now_fn or (lambda: _dt.datetime.now(_dt.timezone.utc)))()
    mins = int(minutes if minutes is not None else registry_config()["quarantine_minutes"])
    trunk_id = str(trunk.id or "")
    if not trunk_id:
        return False
    try:
        st.set_quarantine(tenant_id, trunk_id, now + _dt.timedelta(minutes=mins))
        st.write_health_row(tenant_id, trunk_id, event="quarantine", did=did,
                            is_healthy=False, error_code="manual_kill_switch")
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("rotation: manual_quarantine failed for %s: %r", trunk.slug, type(exc).__name__)
        return False


def reset_state() -> None:
    """Test helper: clear in-process rotation cursors/counters."""
    with _LOCK:
        _RR_CURSOR.clear()
        _DID_USE.clear()
