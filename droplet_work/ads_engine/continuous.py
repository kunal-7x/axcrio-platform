"""ads_engine.continuous — the CONTINUOUS OPTIMIZATION DAEMON (V2-W3 parity loop).

Meta/Google reallocate budget toward winners at auction frequency with NO human trigger; ours only moved
on a manual action or a coarse batch (research/comp-autonomy.md gap #1). This module is the always-on
brain the detached tick drives on a cadence: it pulls the LIVE conversion signals off the ad_events spine,
feeds them into the existing TTTS bandit + GP-UCB/knapsack allocator (REUSED, not rewritten), and PROPOSES
budget reallocation toward winners, creative rotation, audience expansion and learning-phase locks — every
move passing the fail-closed guardrail chain and writing a reversible decision row.

It adds ZERO spend authority: `config.dry_run()` (default ON) means every "applied" verdict is logged, not
executed; spend-increasing moves are forced to draft/approve by guardrails regardless. The daemon only
SEQUENCES the already-gated propose path on a cadence — it is the cadence, not a new power.

Reversibility (master plan §9 W3): every mutation move carries its INVERSE in `reversal_payload`, written
at decision time, so the Decision-Log [Rollback] can replay the exact undo.

EARNER-SAFE: own detached cadence inside the bounded tick; never raises out; per-tenant isolated; no
caller import; no agent.py/voice touch. Deterministic (injectable rng/clock). Offline-testable.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from . import (ad_events as _ev, audience as _aud, config, fatigue as _fat,
               guardrails, learning_phase as _lp, optimization, store)

_log = logging.getLogger("ads_engine.continuous")

# Bound the work per tenant per pass (belt-and-suspenders over the tick's own bound).
DECISIONS_PER_TENANT_CAP = 100
# How far back the daemon looks for "live" signal when refreshing the allocator response curves.
SIGNAL_WINDOW_S = 7 * 86400


# ===========================================================================
# Reversal payloads — the inverse of a mutation move (for Decision-Log rollback).
# ===========================================================================
def reversal_for_move(move: dict) -> Optional[dict]:
    """The INVERSE of a spend-mutating move, written at decision time so [Rollback] can replay the undo.
    Returns None for moves with no meaningful inverse (e.g. hold)."""
    m = str(move.get("move", ""))
    if m == "reallocate":
        return {"move": "reallocate", "channel": move.get("channel"),
                "from_minor": move.get("to_minor"), "to_minor": move.get("from_minor"),
                "spend_delta_sign": -int(move.get("spend_delta_sign", 0)),
                "reason": "rollback of reallocate"}
    if m == "rotate_creative":
        return {"move": "resume_creative", "variant_id": move.get("variant_id"),
                "spend_delta_sign": +1, "reason": "rollback: un-pause rotated creative"}
    if m == "audience_expand":
        return {"move": "audience_contract", "segment": move.get("segment"),
                "spend_delta_sign": -1, "reason": "rollback: remove expanded segment"}
    if m == "scale_winner":
        return {"move": "kill_loser", "variant_id": move.get("variant_id"),
                "spend_delta_sign": -1, "reason": "rollback of scale"}
    if m == "kill_loser":
        return {"move": "scale_winner", "variant_id": move.get("variant_id"),
                "spend_delta_sign": +1, "reason": "rollback of kill"}
    return None


def _log_decision(tenant_id: str, gstate: dict, move: dict, *, now_ts: int, actor: str,
                  extra_inputs: Optional[dict] = None) -> dict:
    """Evaluate a move through the fail-closed chain, stamp a reversal payload, append a decision row.
    Returns the verdict dict. Never raises — a logging failure is swallowed."""
    verdict = guardrails.evaluate(gstate or {}, move)
    inputs = {"dry_run": config.dry_run(), "daemon": True}
    if extra_inputs:
        inputs.update(extra_inputs)
    row = guardrails.build_decision_row(tenant_id, move, verdict, inputs=inputs,
                                        ts=now_ts, actor=actor)
    rev = reversal_for_move(move)
    if rev is not None:
        row["reversal_payload"] = rev
        row["reversible"] = True
    try:
        store.append_decision(tenant_id, row)
    except Exception as exc:  # noqa: BLE001
        _log.warning("continuous._log_decision append failed: %r", type(exc).__name__)
    return {"verdict": verdict, "row": row}


# ===========================================================================
# Per-campaign passes.
# ===========================================================================
def _campaign_provider(rec: dict) -> str:
    return str((rec or {}).get("provider") or "meta").strip().lower()


def learning_and_signal_pass(tenant_id: str, campaign_id: str, rec: dict, *, now_ts: int) -> dict:
    """Refresh the learning phase (sets the do-not-edit lock) AND fold live ad_events into the bandit
    reward — so the optimizer is always working off the freshest real-buyer signal."""
    provider = _campaign_provider(rec)
    started = rec.get("launched_ts") or rec.get("created_ts")
    verdict = _lp.refresh(tenant_id, campaign_id, provider=provider, started_ts=started, now_ts=now_ts)
    feed = _ev.feed_optimizer(tenant_id, campaign_id, window_s=SIGNAL_WINDOW_S, now_ts=now_ts)
    return {"learning": verdict, "feed": feed}


def fatigue_pass(tenant_id: str, campaign_id: str, events: list, *, now_ts: int) -> int:
    """Detect creative fatigue and log rotation proposals (propose-only). Returns decisions written."""
    analysis = _fat.analyze(events, campaign_id=campaign_id)
    moves = _fat.propose_rotation(analysis, campaign_id=campaign_id)
    try:
        store.put_row(tenant_id, "fatigue_state", campaign_id,
                      _fat.build_state(campaign_id, analysis, moves, now_ts=now_ts))
    except Exception:  # noqa: BLE001
        pass
    gstate = store.get_guardrail_state(tenant_id, campaign_id) or {}
    written = 0
    for mv in moves:
        if written >= DECISIONS_PER_TENANT_CAP:
            break
        _log_decision(tenant_id, gstate, mv, now_ts=now_ts, actor="daemon:fatigue",
                      extra_inputs={"fatigue_reason": mv.get("fatigue", {}).get("reason")})
        written += 1
    return written


def audience_pass(tenant_id: str, campaign_id: str, rec: dict, events: list, *, now_ts: int) -> int:
    """Discover converting segments beyond the seed and log expansion proposals (proposal-only, soft
    ceiling, spend-increasing => human-gated by guardrails). Returns decisions written."""
    brief = (rec or {}).get("plan", {}).get("brief", {}) if isinstance((rec or {}).get("plan"), dict) else {}
    seed = (brief.get("audience_segments") or brief.get("segments")
            or (rec or {}).get("seed_segments") or [])
    budget_daily = int((brief.get("budget_daily_minor") or (rec or {}).get("budget_daily_minor") or 0))
    discovery = _aud.discover_segments(events, seed, campaign_id=campaign_id)
    moves = _aud.propose_expansion(discovery, campaign_id=campaign_id, budget_daily_minor=budget_daily)
    try:
        store.put_row(tenant_id, "audience_state", campaign_id,
                      _aud.build_state(campaign_id, seed, discovery, moves, now_ts=now_ts))
    except Exception:  # noqa: BLE001
        pass
    gstate = store.get_guardrail_state(tenant_id, campaign_id) or {}
    written = 0
    for mv in moves:
        if written >= DECISIONS_PER_TENANT_CAP:
            break
        _log_decision(tenant_id, gstate, mv, now_ts=now_ts, actor="daemon:audience",
                      extra_inputs={"segment": mv.get("segment")})
        written += 1
    return written


# ===========================================================================
# Per-account budget reallocation toward winners (the headline continuous loop).
# ===========================================================================
def _refresh_channel_history(alloc_state: dict, platforms: dict) -> None:
    """Append the freshest LIVE (spend, reward) response point per channel from the platform-level
    signal, so the GP-UCB curve reallocates on current performance, not stale history. reward = the
    quality-weighted true-conv the channel produced this window (real buyers)."""
    channels = alloc_state.get("channels", {})
    for ch, meta in channels.items():
        plat = str(ch).split(":", 1)[0]
        sig = platforms.get(plat)
        if not sig:
            continue
        spend = int(meta.get("alloc_minor", 0) or 0)
        reward = float(sig.get("true_conv", 0.0))
        hist = list(meta.get("history", []))
        hist.append([spend, reward])
        meta["history"] = hist[-24:]  # bounded rolling window


def reallocation_pass(tenant_id: str, *, now_ts: int, rng: Any = None,
                      events: Optional[list] = None) -> int:
    """Reallocate budget toward winners for every account, using LIVE signal. Reuses
    optimization.propose_allocation (GP-UCB + knapsack); each reallocate move runs through guardrails and
    is logged with a reversal payload. DRY-RUN: spend-increasing reallocations defer to approval; nothing
    spends. Returns decisions written. Never raises."""
    written = 0
    try:
        evs = events if events is not None else store.get_ad_events(tenant_id, since_ts=now_ts - SIGNAL_WINDOW_S)
        platforms = _ev.aggregate_signals(evs)["platforms"]
        allocations = store.get_collection(tenant_id, "allocations")
    except Exception as exc:  # noqa: BLE001
        _log.warning("continuous.reallocation_pass setup failed: %r", type(exc).__name__)
        return 0
    for account_id, alloc_state in (allocations or {}).items():
        if written >= DECISIONS_PER_TENANT_CAP:
            break
        if not isinstance(alloc_state, dict) or not alloc_state.get("channels"):
            continue
        try:
            _refresh_channel_history(alloc_state, platforms)
            result = optimization.propose_allocation(alloc_state, rng=rng)
            # Persist the refreshed/proposed allocation state (propose-only; alloc_minor is the PROPOSAL,
            # not a spend — it only becomes spend after an approved, non-dry-run apply).
            try:
                ver = int(alloc_state.get("version", 0) or 0)
                store.put_allocation(tenant_id, account_id, alloc_state, expected_version=ver)
            except store.VersionConflict:
                pass
            gstate = store.get_guardrail_state(tenant_id, str(alloc_state.get("account_id") or account_id)) or {}
            for mv in result.get("moves", []):
                if written >= DECISIONS_PER_TENANT_CAP:
                    break
                _log_decision(tenant_id, gstate, mv, now_ts=now_ts, actor="daemon:reallocate",
                              extra_inputs={"changed_points": result.get("changed_points"),
                                            "solver": result.get("solver")})
                written += 1
        except Exception as exc:  # noqa: BLE001 — one account's failure never aborts the rest
            _log.warning("continuous.reallocation_pass account %s failed: %r",
                         account_id, type(exc).__name__)
            continue
    return written


# ===========================================================================
# The tenant pass + the public daemon entrypoint the tick calls on a cadence.
# ===========================================================================
async def optimize_tenant(tenant_id: str, *, now_ts: int, rng: Any = None) -> dict:
    """One full continuous-optimization pass for ONE tenant: learning+signal refresh -> bandit feed ->
    budget reallocation -> creative fatigue rotation -> audience expansion -> same-day CAPI drain. Every
    sub-pass is individually crash-proofed; one failure never aborts the others. Returns a summary."""
    summary = {"campaigns": 0, "decisions": 0, "capi": {}}
    try:
        campaigns = store.list_campaigns(tenant_id)
        events = store.get_ad_events(tenant_id, since_ts=now_ts - SIGNAL_WINDOW_S)
    except Exception as exc:  # noqa: BLE001
        _log.warning("continuous.optimize_tenant setup failed for %s: %r", tenant_id, type(exc).__name__)
        return summary
    for rec in (campaigns or []):
        cid = rec.get("plan_id") or rec.get("campaign_id") or rec.get("id") or ""
        if not cid:
            continue
        status = str(rec.get("status", ""))
        if status and status not in ("active", "running", "launched", ""):
            continue
        summary["campaigns"] += 1
        for fn, label in ((lambda: learning_and_signal_pass(tenant_id, cid, rec, now_ts=now_ts), "learn"),):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                _log.warning("continuous %s pass failed %s/%s: %r", label, tenant_id, cid, type(exc).__name__)
        try:
            summary["decisions"] += fatigue_pass(tenant_id, cid, events, now_ts=now_ts)
        except Exception as exc:  # noqa: BLE001
            _log.warning("continuous fatigue pass failed %s/%s: %r", tenant_id, cid, type(exc).__name__)
        try:
            summary["decisions"] += audience_pass(tenant_id, cid, rec, events, now_ts=now_ts)
        except Exception as exc:  # noqa: BLE001
            _log.warning("continuous audience pass failed %s/%s: %r", tenant_id, cid, type(exc).__name__)
    # Account-level budget reallocation (the headline continuous loop).
    try:
        summary["decisions"] += reallocation_pass(tenant_id, now_ts=now_ts, rng=rng, events=events)
    except Exception as exc:  # noqa: BLE001
        _log.warning("continuous reallocation pass failed for %s: %r", tenant_id, type(exc).__name__)
    # Same-day CAPI escalation of the quality signals.
    try:
        summary["capi"] = await _ev.same_day_capi_drain(tenant_id, now_epoch=now_ts)
    except Exception as exc:  # noqa: BLE001
        _log.warning("continuous capi drain failed for %s: %r", tenant_id, type(exc).__name__)
    return summary


async def optimize_pass(tids: Optional[list] = None, *, now_ts: Optional[int] = None,
                        rng: Any = None) -> dict:
    """The cadence entrypoint the detached tick calls (throttled). Runs a continuous-optimization pass for
    every ads tenant. Globally inert unless FEATURE_ADS is on (defense in depth). Per-tenant isolated;
    never raises into the tick. Returns a small summary for the smoke tests."""
    summary = {"ran": False, "tenants": 0, "decisions": 0}
    if not config.is_enabled():
        return summary
    now = int(now_ts if now_ts is not None else time.time())
    summary["ran"] = True
    try:
        ids = tids if tids is not None else store.list_tenant_ids("campaigns")
    except Exception as exc:  # noqa: BLE001
        _log.warning("continuous.optimize_pass tenant enumeration failed: %r", type(exc).__name__)
        return summary
    for tid in (ids or []):
        try:
            res = await optimize_tenant(tid, now_ts=now, rng=rng)
            summary["tenants"] += 1
            summary["decisions"] += int(res.get("decisions", 0) or 0)
        except Exception as exc:  # noqa: BLE001 — per-tenant isolation
            _log.warning("continuous.optimize_pass tenant %s failed: %r", tid, type(exc).__name__)
            continue
    return summary


__all__ = ["optimize_pass", "optimize_tenant", "reallocation_pass", "fatigue_pass",
           "audience_pass", "learning_and_signal_pass", "reversal_for_move"]
