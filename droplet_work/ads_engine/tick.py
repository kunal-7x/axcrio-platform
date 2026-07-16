"""ads_engine.tick — the DETACHED, BOUNDED ads background worker (W4).

THE EARNER-SAFETY UNIT. This loop runs as its OWN asyncio task (caller.py detaches it
with a single `asyncio.create_task(ads_engine.tick.run_loop(...))` at scheduler startup,
FEATURE_ADS-gated). It is fully ISOLATED from the live voice earner: it shares NO state
with `scheduler_loop`, never blocks it, and CANNOT raise into it.

Earner-safety invariants (redteam earner-safety.md C1 + spend-optimization-safety.md C1):

  * DETACHED — its own task, so a slow/hung pass can never delay the earner's own
    reconcile/retry/opt-out sweep inside scheduler_loop (redteam C1: do NOT await inline).
  * NEVER raises out — the whole loop body and every iteration are wrapped in try/except
    that swallow + log; the loop survives any sub-pass failure (earner E5).
  * EVERY internal op is `asyncio.wait_for`-bounded (~10s) — a hung connector/store op is
    cancelled and the loop continues; no op can stall the tick (earner E1).
  * RE-ENTRANCY guard (`_TICK_RUNNING`) — a tick that overruns the interval can never
    overlap a second tick (redteam earner-safety M4): the next wake no-ops if one is live.
  * STALE-SWEEP WATCHDOG (redteam spend C1) — if the spend-cap sweep has not COMPLETED
    within N ticks, fail-CLOSED: propose pause-all for every tenant + log a loud alarm.

DRY in W4: connectors are offline / have no keys. The tick therefore PROPOSES and LOGS
decisions (bandit moves through the guardrail chain → decision_log; spend-cap sweep →
decision_log) and does NOT actually spend or call a platform. Turning a proposal into a
real platform mutation is a later wave behind ADS_DRY_RUN / approval gates.

NO `from caller import ...` — this module uses ONLY the seams injected via ads_engine.wire()
(store IO, optionally _awrite). The RNG and clock are injectable so tests are deterministic.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from . import config, guardrails, optimization, seams, store

# ---------------------------------------------------------------------------
# Tunables (all overridable via run_loop(...) kwargs for tests).
# ---------------------------------------------------------------------------
DEFAULT_SLEEP_S = 60.0          # base loop interval (mirrors scheduler_loop cadence)
OP_TIMEOUT_S = 10.0             # tight per-op bound — a hung op is cancelled at this
STALE_SWEEP_MAX_TICKS = 5       # watchdog: pause-all if spend-sweep misses this many ticks
DECISIONS_PER_TICK_CAP = 200    # belt-and-suspenders: bound decision_log writes per tick

# Self-throttle cadences (a sub-pass runs only every N seconds of wall-clock; the bandit
# pass is heavier than the spend sweep, the NCPR refresh heavier still). Kept conservative.
BANDIT_EVERY_S = 300            # ~5 min — propose bandit moves
CONTINUOUS_EVERY_S = 600        # ~10 min — V2-W3 continuous optimization daemon (reallocate-to-winners
                                # using live ad_events signal + fatigue rotation + audience expansion +
                                # learning-phase refresh + same-day CAPI drain). Mirrors Meta's ~real-time
                                # cadence at a conservative, earner-safe interval. Propose-only + dry-run.
ORCHESTRATOR_EVERY_S = 120      # ~2 min — autonomy orchestrator: advance each opt-in tenant 1 phase
WEBHOOK_RECONCILE_EVERY_S = 300  # ~5 min — leadgen webhook reconciliation backstop
NCPR_REFRESH_EVERY_S = 3600     # ~hourly — NCPR/DND cache refresh (stub in W4)
VERSION_SUNSET_EVERY_S = 86400  # ~daily — pinned-API version-sunset drift alarm (redteam M1)

# ---------------------------------------------------------------------------
# Module-level loop state. A re-entrancy flag (NOT a lock object) so the guard is
# observable + testable without an event loop. Reset defensively on every loop start.
# ---------------------------------------------------------------------------
_TICK_RUNNING = False           # True while a single tick iteration is in flight
_LOOP_STARTED = False           # guards against two run_loop() tasks being detached
_LAST_BANDIT_TS = 0.0
_LAST_WEBHOOK_TS = 0.0
_LAST_NCPR_TS = 0.0
_LAST_VERSION_TS = 0.0          # last wall-clock the version-sunset alarm pass ran (~daily)
_LAST_ORCH_TS = 0.0             # last wall-clock the autonomy orchestrator pass ran (~2 min)
_LAST_CONTINUOUS_TS = 0.0       # last wall-clock the V2-W3 continuous optimization daemon ran (~10 min)
_TICKS_SINCE_SWEEP_OK = 0       # watchdog counter: ticks since the spend sweep last completed


def _reset_state() -> None:
    """Reset all module-level cadence/watchdog counters (used by run_loop start + tests)."""
    global _TICK_RUNNING, _LAST_BANDIT_TS, _LAST_WEBHOOK_TS, _LAST_NCPR_TS, _LAST_VERSION_TS
    global _LAST_ORCH_TS, _LAST_CONTINUOUS_TS, _TICKS_SINCE_SWEEP_OK
    _TICK_RUNNING = False
    _LAST_BANDIT_TS = 0.0
    _LAST_WEBHOOK_TS = 0.0
    _LAST_NCPR_TS = 0.0
    _LAST_VERSION_TS = 0.0
    _LAST_ORCH_TS = 0.0
    _LAST_CONTINUOUS_TS = 0.0
    _TICKS_SINCE_SWEEP_OK = 0


def _log(msg: str, *, level: str = "info") -> None:
    """Best-effort logging — NEVER raises (logging must not break the earner-safe loop)."""
    try:
        import logging as _lg
        logger = _lg.getLogger("ads_engine.tick")
        getattr(logger, level, logger.info)(msg)
    except Exception:  # noqa: BLE001
        pass


async def _bounded(fn: Callable[[], Any], *, timeout: float = OP_TIMEOUT_S) -> Any:
    """Run a SYNC op off the event loop, hard-bounded by `asyncio.wait_for`.

    Every connector/store op goes through here so a single hung op (a blocking read, a
    slow connector) is cancelled at `timeout` and CANNOT stall the loop (redteam C1).
    Raises asyncio.TimeoutError on overrun and the original exception on failure — the
    caller (run_tick) swallows both per-op so one bad op never aborts the whole tick.
    """
    return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout)


# ===========================================================================
# Per-tenant sub-passes. Each is wrapped by run_tick in its own try/except so a
# failure in one tenant/pass never aborts the others (per-tenant isolation).
# ===========================================================================
async def _sweep_tenant_guardrails(tid: str, *, now_ts: int) -> int:
    """Spend-cap sweep for ONE tenant: re-evaluate each GuardrailState's caps and, when a
    cap/CPL breach is detected, PROPOSE + log an auto_pause decision (DRY — no real spend).

    Returns the number of decisions written. All store IO is tenant-first + bounded.
    """
    written = 0
    gstates = await _bounded(lambda: store.list_guardrail_states(tid))
    for gstate in (gstates or []):
        if written >= DECISIONS_PER_TICK_CAP:
            break
        cid = gstate.get("campaign_id") or gstate.get("id") or ""
        if not cid:
            continue
        # A spend-decreasing safety pause is the move the sweep WANTS to propose when a
        # breach exists; evaluate it through the chain so the decision is auditable.
        pause = {"plan_id": cid, "move": "auto_pause", "spend_delta_sign": -1,
                 "reason": "spend-cap sweep: cap/CPL re-evaluation"}
        # Probe whether a discretionary scale WOULD breach a cap/CPL (i.e. is the campaign
        # at/over a limit?). If so, the campaign should be paused — propose it.
        probe = {"plan_id": cid, "move": "scale_winner", "spend_delta_sign": +1,
                 "spend_delta_minor": 1, "reason": "spend-cap sweep probe"}
        verdict_probe = guardrails.evaluate(gstate, probe)
        breached = (not verdict_probe.allow) and verdict_probe.blocked_by in (
            guardrails.BLOCKED_CAP, guardrails.BLOCKED_CPL, guardrails.BLOCKED_FUNDS)
        if not breached:
            continue
        verdict = guardrails.evaluate(gstate, pause)
        row = guardrails.build_decision_row(
            tid, pause, verdict,
            inputs={"spend_today_minor": gstate.get("spend_today_minor"),
                    "daily_cap_minor": gstate.get("daily_cap_minor"),
                    "last_cpl_minor": gstate.get("last_cpl_minor"),
                    "breach": verdict_probe.blocked_by, "dry_run": config.dry_run()},
            ts=now_ts, actor="tick:spend_sweep")
        await _bounded(lambda r=row: store.append_decision(tid, r))
        written += 1
    return written


async def _bandit_pass_tenant(tid: str, *, now_ts: int, rng: Any) -> int:
    """Bandit propose pass for ONE tenant: for each active campaign with bandit state,
    propose moves → run each through the guardrail chain → log the decision (DRY).

    Returns the number of decisions written. Tenant-first + bounded throughout.
    """
    written = 0
    campaigns = await _bounded(lambda: store.list_campaigns(tid))
    for cmp_ in (campaigns or []):
        if written >= DECISIONS_PER_TICK_CAP:
            break
        if str(cmp_.get("status", "")) not in ("active", "running", ""):
            continue
        cid = cmp_.get("plan_id") or cmp_.get("campaign_id") or cmp_.get("id") or ""
        if not cid:
            continue
        bstate = await _bounded(lambda c=cid: store.get_bandit_state(tid, c))
        if not bstate:
            continue
        gstate = await _bounded(lambda c=cid: store.get_guardrail_state(tid, c)) or {}
        moves = optimization.propose_bandit_moves(bstate, rng=rng)
        for move in moves:
            if written >= DECISIONS_PER_TICK_CAP:
                break
            if str(move.get("move", "")) == "hold":
                continue  # holds are not decisions worth persisting every tick
            verdict = guardrails.evaluate(gstate, move)
            row = guardrails.build_decision_row(
                tid, move, verdict,
                inputs={"best_arm_confidence": bstate.get("best_arm_confidence"),
                        "dry_run": config.dry_run()},
                ts=now_ts, actor="tick:bandit")
            await _bounded(lambda r=row: store.append_decision(tid, r))
            written += 1
    return written


async def _webhook_reconcile_backstop(tid: str, *, now_ts: int) -> None:
    """Leadgen webhook reconciliation backstop (redteam: webhooks can silently die post
    CA-migration; a poll is the backstop). W4 STUB — connectors are offline, so this only
    records that the backstop ran (no platform poll yet). Bounded + tenant-first."""
    # Intentionally a no-op store touch in W4 (no connector keys). Kept as a seam so the
    # cadence + isolation are proven now; the real poll lands when connectors are wired.
    return None


async def _ncpr_refresh(*, now_ts: int) -> None:
    """NCPR / DND cache refresh (compliance pre-gate dependency). W4 STUB — no provider
    configured yet, so this is a bounded no-op placeholder proving the ~hourly cadence."""
    return None


async def _version_sunset_alarm_pass(tids: list, *, now_ts: int) -> int:
    """~Daily pinned-API version-sunset drift alarm (redteam api-version-... M1/M4).

    Consults `config.version_sunset_alarms()` (the single sunset table) and, when any pinned
    Meta/Google/WhatsApp version is EXPIRED or within config.SUNSET_ALARM_DAYS of its sunset,
    logs a LOUD alarm AND writes a `version_sunset` row into EVERY ads tenant's decision_log
    so the alarm is VISIBLE to the operator (not just buried in process logs). A pinned version
    silently hitting a 4xx a year out is the exact failure this replaces the prose-only bump
    note with. Returns the number of decision rows written. Bounded + crash-proof per pass.
    """
    try:
        alarms = config.version_sunset_alarms()
    except Exception as exc:  # noqa: BLE001
        _log(f"version-sunset pass: alarm computation failed: {exc!r}", level="warning")
        return 0
    if not alarms:
        return 0  # all pins healthy — nothing to log

    # Loud process-log alarm (one line per alarming pin).
    for a in alarms:
        state = "EXPIRED" if a.get("expired") else f"sunsets in {a.get('days_to_sunset')}d"
        _log(f"ADS VERSION-SUNSET ALARM: {a.get('api')} pin {a.get('version')} {state} "
             f"(sunset={a.get('sunset')}) — BUMP THE PIN in ads_engine.config", level="error")

    # Visible Decision-Log row per tenant (idempotency: at most one per ~daily cadence).
    expired_any = any(a.get("expired") for a in alarms)
    min_runway = min((a.get("days_to_sunset") for a in alarms
                      if a.get("days_to_sunset") is not None), default=None)
    written = 0
    import uuid as _uuid
    for tid in (tids or []):
        if written >= DECISIONS_PER_TICK_CAP:
            break
        row = {
            # uuid suffix => globally-unique id (matches guardrails.build_decision_row), so the
            # row id never collides across tenants even though each tenant's log is independent.
            "id": "dec_vsun_" + _uuid.uuid4().hex[:10],
            "tenant_id": tid,
            "ts": int(now_ts),
            "kind": "version_sunset",
            "campaign_id": None,
            "decision": "version_sunset_alarm",
            "outcome": "expired" if expired_any else "warning",
            "blocked_by": None,
            "inputs": {"alarms": alarms, "min_days_to_sunset": min_runway,
                       "within_days": config.SUNSET_ALARM_DAYS, "dry_run": config.dry_run()},
            "explanation": ("A pinned ad-platform API version is "
                            + ("EXPIRED" if expired_any else "near sunset")
                            + " — bump the pin in ads_engine.config before calls 4xx."),
            "actor": "tick:version_sunset",
            "reversible": False,
        }
        try:
            await _bounded(lambda t=tid, r=row: store.append_decision(t, r))
            written += 1
        except Exception as exc:  # noqa: BLE001 — one tenant's failure never aborts the rest
            _log(f"version-sunset pass: append failed for tenant {tid}: {exc!r}", level="warning")
    return written


# ===========================================================================
# Watchdog — fail-closed pause-all when the spend sweep goes stale.
# ===========================================================================
async def _watchdog_pause_all(*, now_ts: int, reason: str) -> int:
    """Fail-CLOSED: the spend-cap sweep has not completed within STALE_SWEEP_MAX_TICKS.
    Propose a pause-all (auto_pause) for EVERY tenant's active campaigns + log a loud
    alarm. DRY (proposal only). Returns the number of pause decisions logged."""
    _log(f"STALE-SWEEP WATCHDOG TRIPPED: {reason} — proposing pause-all (fail-closed)",
         level="error")
    logged = 0
    try:
        tids = await _bounded(lambda: store.list_tenant_ids("campaigns"))
    except Exception as exc:  # noqa: BLE001
        _log(f"watchdog: could not enumerate tenants: {exc!r}", level="error")
        return 0
    for tid in (tids or []):
        try:
            campaigns = await _bounded(lambda t=tid: store.list_campaigns(t))
            for cmp_ in (campaigns or []):
                cid = cmp_.get("plan_id") or cmp_.get("campaign_id") or cmp_.get("id") or ""
                if not cid:
                    continue
                move = {"plan_id": cid, "move": "auto_pause", "spend_delta_sign": -1,
                        "reason": f"WATCHDOG fail-closed pause-all: {reason}"}
                verdict = guardrails.evaluate({}, move)
                row = guardrails.build_decision_row(
                    tid, move, verdict,
                    inputs={"watchdog": True, "reason": reason, "dry_run": config.dry_run()},
                    ts=now_ts, actor="tick:watchdog")
                await _bounded(lambda t=tid, r=row: store.append_decision(t, r))
                logged += 1
        except Exception as exc:  # noqa: BLE001 — one tenant's failure never aborts the rest
            _log(f"watchdog: tenant {tid} pause-all failed: {exc!r}", level="error")
            continue
    return logged


# ===========================================================================
# ONE tick iteration.
# ===========================================================================
async def run_tick(now_ts: Optional[int] = None, *, rng: Any = None) -> dict:
    """Run ONE bounded iteration. NEVER raises (each sub-pass is individually swallowed).

    Returns a small summary dict (decisions written, sweep_ok, watchdog_fired) — used by
    the smoke tests. Order: spend-cap sweep (every tick) → watchdog check → bandit
    (throttled) → webhook reconcile (throttled) → NCPR refresh (throttled).
    """
    global _LAST_BANDIT_TS, _LAST_WEBHOOK_TS, _LAST_NCPR_TS, _LAST_VERSION_TS, _TICKS_SINCE_SWEEP_OK
    global _LAST_ORCH_TS, _LAST_CONTINUOUS_TS
    now = int(now_ts if now_ts is not None else time.time())
    summary = {"decisions": 0, "sweep_ok": False, "watchdog_fired": False, "tenants": 0,
               "version_alarms": 0, "orchestrated": 0, "continuous_decisions": 0}

    # Enumerate tenants with ads activity (bounded; degrade-safe).
    try:
        tids = await _bounded(lambda: store.list_tenant_ids("campaigns"))
    except Exception as exc:  # noqa: BLE001
        _log(f"run_tick: tenant enumeration failed: {exc!r}", level="warning")
        tids = []
    summary["tenants"] = len(tids or [])

    # ---- spend-cap sweep (EVERY tick — the primary safety pass) ----
    sweep_ok = True
    for tid in (tids or []):
        try:
            summary["decisions"] += await _sweep_tenant_guardrails(tid, now_ts=now)
        except asyncio.TimeoutError:
            sweep_ok = False
            _log(f"run_tick: spend sweep timed out for tenant {tid}", level="warning")
        except Exception as exc:  # noqa: BLE001 — per-tenant isolation
            sweep_ok = False
            _log(f"run_tick: spend sweep failed for tenant {tid}: {exc!r}", level="warning")
    summary["sweep_ok"] = sweep_ok

    # ---- stale-sweep watchdog (redteam spend C1) ----
    if sweep_ok:
        _TICKS_SINCE_SWEEP_OK = 0
    else:
        _TICKS_SINCE_SWEEP_OK += 1
        if _TICKS_SINCE_SWEEP_OK >= STALE_SWEEP_MAX_TICKS:
            try:
                await _watchdog_pause_all(
                    now_ts=now,
                    reason=f"spend sweep failed {_TICKS_SINCE_SWEEP_OK} consecutive ticks")
                summary["watchdog_fired"] = True
            except Exception as exc:  # noqa: BLE001
                _log(f"run_tick: watchdog itself failed: {exc!r}", level="error")
            finally:
                _TICKS_SINCE_SWEEP_OK = 0  # re-arm after firing so it alarms again if still stale

    # ---- bandit pass (throttled ~5 min) ----
    if now - _LAST_BANDIT_TS >= BANDIT_EVERY_S:
        _LAST_BANDIT_TS = now
        for tid in (tids or []):
            try:
                summary["decisions"] += await _bandit_pass_tenant(tid, now_ts=now, rng=rng)
            except Exception as exc:  # noqa: BLE001 — per-tenant isolation
                _log(f"run_tick: bandit pass failed for tenant {tid}: {exc!r}", level="warning")

    # ---- webhook reconciliation backstop (throttled ~5 min) ----
    if now - _LAST_WEBHOOK_TS >= WEBHOOK_RECONCILE_EVERY_S:
        _LAST_WEBHOOK_TS = now
        for tid in (tids or []):
            try:
                await _webhook_reconcile_backstop(tid, now_ts=now)
            except Exception as exc:  # noqa: BLE001
                _log(f"run_tick: webhook reconcile failed for tenant {tid}: {exc!r}", level="warning")

    # ---- NCPR cache refresh (throttled ~hourly, stub) ----
    if now - _LAST_NCPR_TS >= NCPR_REFRESH_EVERY_S:
        _LAST_NCPR_TS = now
        try:
            await _ncpr_refresh(now_ts=now)
        except Exception as exc:  # noqa: BLE001
            _log(f"run_tick: NCPR refresh failed: {exc!r}", level="warning")

    # ---- version-sunset drift alarm (throttled ~daily; redteam api-version M1/M4) ----
    if now - _LAST_VERSION_TS >= VERSION_SUNSET_EVERY_S:
        _LAST_VERSION_TS = now
        try:
            summary["version_alarms"] = await _version_sunset_alarm_pass(tids, now_ts=now)
        except Exception as exc:  # noqa: BLE001
            _log(f"run_tick: version-sunset pass failed: {exc!r}", level="warning")

    # ---- V2-W3 continuous optimization daemon (throttled ~10 min) ----
    # Reallocates budget toward winners off the LIVE ad_events signal, rotates fatigued creative, proposes
    # audience expansion, refreshes the learning-phase lock and drains same-day CAPI — all propose-only +
    # dry-run + fail-closed through guardrails (NO human trigger, NO new spend authority). Fully isolated:
    # a failure here can never abort the safety passes above.
    if now - _LAST_CONTINUOUS_TS >= CONTINUOUS_EVERY_S:
        _LAST_CONTINUOUS_TS = now
        try:
            from . import continuous as _continuous
            res = await asyncio.wait_for(
                _continuous.optimize_pass(tids, now_ts=now, rng=rng), timeout=OP_TIMEOUT_S * 6)
            summary["continuous_decisions"] = int((res or {}).get("decisions", 0) or 0)
            summary["decisions"] += summary["continuous_decisions"]
        except Exception as exc:  # noqa: BLE001 — the daemon never breaks the tick
            _log(f"run_tick: continuous optimization pass failed: {exc!r}", level="warning")

    # ---- autonomy orchestrator (throttled ~2 min; BLINDSPOTS B9) ----
    # Globally OFF unless ADS_AUTORUN is set; the orchestrator itself re-checks the flag and is
    # fully self-contained + crash-proof, so a failure here can never abort the safety passes above.
    if now - _LAST_ORCH_TS >= ORCHESTRATOR_EVERY_S:
        _LAST_ORCH_TS = now
        try:
            from . import orchestrator as _orch
            res = await asyncio.wait_for(_orch.tick_pass(now_ts=now), timeout=OP_TIMEOUT_S * 6)
            summary["orchestrated"] = int((res or {}).get("advanced", 0) or 0)
        except Exception as exc:  # noqa: BLE001 — orchestrator never breaks the tick
            _log(f"run_tick: orchestrator pass failed: {exc!r}", level="warning")

    return summary


# ===========================================================================
# The detached loop — the entrypoint caller.py create_task's.
# ===========================================================================
async def run_loop(*, sleep_s: float = DEFAULT_SLEEP_S,
                   time_fn: Callable[[], float] = time.time,
                   rng: Any = None,
                   run_tick_fn: Optional[Callable] = None,
                   max_iterations: Optional[int] = None) -> None:
    """The ads background worker. Detached by caller.py as its OWN task (FEATURE_ADS-gated).

    NEVER raises out (the loop body is fully swallowed). Each iteration is RE-ENTRANCY
    guarded (`_TICK_RUNNING`) so an overrunning tick can never overlap the next wake.
    Sleeps `sleep_s` between iterations using an injectable clock.

    Args (all injectable for deterministic tests):
      sleep_s         interval between iterations.
      time_fn         clock (tests pass a fake to drive `now`).
      rng             numpy seed/Generator for the bandit (deterministic tests).
      run_tick_fn     override the per-tick coroutine fn (tests inject a raising/hung one).
      max_iterations  stop after N iterations (tests bound the loop; None = forever).
    """
    global _TICK_RUNNING, _LOOP_STARTED
    if _LOOP_STARTED:
        # Defensive: a second detached run_loop must NOT start (redteam: one tick task).
        _log("run_loop: already started — refusing to start a second loop", level="warning")
        return
    # ---- W4 NIT — NO-OP IF THE PACKAGE IS NOT FULLY WIRED -------------------------------
    # caller.py's tick-start guard (`if FEATURE_ADS and _ads_pkg is not None`) starts this
    # loop whenever the PACKAGE imported, even if `from ads_engine.endpoints import build_router`
    # FAILED (so the router never mounted AND ads_engine.wire(...) was never called). An un-wired
    # tick would run every pass against an empty seams bag (store IO seams = None) — pointless
    # churn with no router, exactly the half-wired state the caller guard can't see. So: if the
    # seams were never injected, the REAL detached loop (the production entrypoint, identified by
    # run_tick_fn being None) does NOTHING. Tests that inject a run_tick_fn / wire the package
    # bypass this (they exercise the loop mechanics directly). The caller.py guard stays as-is —
    # this fix lives entirely in tick.py.
    if run_tick_fn is None and not seams().wired:
        _log("run_loop: ads_engine not fully wired (seams not injected) — tick no-op "
             "(endpoints import likely failed; refusing to run un-wired)", level="warning")
        return
    _LOOP_STARTED = True
    _reset_state()
    tick_fn = run_tick_fn or run_tick
    _log("ads_engine tick loop started (detached, bounded, dry-run propose-only)")

    iterations = 0
    try:
        while True:
            if max_iterations is not None and iterations >= max_iterations:
                break
            iterations += 1
            # ---- RE-ENTRANCY guard: skip if the previous iteration is still running ----
            if _TICK_RUNNING:
                _log("run_loop: previous tick still running — skipping this wake (re-entrancy)",
                     level="warning")
            else:
                _TICK_RUNNING = True
                try:
                    now = int(time_fn())
                    # The whole iteration is bounded AGAIN at the loop level: even if a
                    # sub-pass forgot its wait_for, the tick as a whole can't run forever.
                    await asyncio.wait_for(
                        tick_fn(now, rng=rng),
                        timeout=OP_TIMEOUT_S * 6)  # generous whole-tick ceiling (~60s)
                except asyncio.TimeoutError:
                    _log("run_loop: whole-tick timeout — cancelled, continuing", level="warning")
                except asyncio.CancelledError:
                    raise  # honor task cancellation (shutdown) — re-raise out of the guard
                except Exception as exc:  # noqa: BLE001 — a raising tick must NOT kill the loop
                    _log(f"run_loop: tick raised, swallowed (loop survives): {exc!r}",
                         level="warning")
                finally:
                    _TICK_RUNNING = False
            try:
                await asyncio.sleep(sleep_s)
            except asyncio.CancelledError:
                raise
    except asyncio.CancelledError:
        _log("ads_engine tick loop cancelled (shutdown)")
        raise
    except Exception as exc:  # noqa: BLE001 — absolute backstop: the loop never crashes out
        _log(f"run_loop: fatal loop error swallowed: {exc!r}", level="error")
    finally:
        _LOOP_STARTED = False
        _TICK_RUNNING = False
