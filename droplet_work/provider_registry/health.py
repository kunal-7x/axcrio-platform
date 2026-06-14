"""provider_registry.health — in-memory circuit breaker + background probe (W3).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §2f (health-check + in-memory circuit breaker:
3 consecutive fails -> circuit open IN MEMORY (not PG, to avoid write storms); exponential
backoff 60->120->240s; fallback chain ordered by priority; never use a generation endpoint for
health) + §4 ("health.py — background probe + in-memory circuit breaker (3-fail, expo backoff) +
health log write") + §10.8.

DESIGN:
  * The CIRCUIT STATE is per (tenant_id, provider_def_id), held in a process-local dict. It is the
    INPUT the registry's fallback uses: `is_open(...)` -> skip this provider, try the next by
    priority. NO PG read on the hot path (the §3 "0ms on the voice loop" rule — the LLM-router
    consumer reads this in-memory map, never the DB).
  * 3 consecutive failures -> OPEN. While open, `is_open` is True until `open_until`. Each
    re-open doubles the backoff: 60 -> 120 -> 240 -> ... capped at MAX_BACKOFF_S.
  * A single SUCCESS closes the circuit and resets the fail count + backoff.
  * A HALF-OPEN probe: once `open_until` passes, `is_open` returns False (allow ONE trial); if that
    trial fails the breaker re-opens with the next (doubled) backoff.
  * The clock is injectable (`now_fn`) so the offline test drives backoff deterministically with
    no real sleeping.

This module does ZERO network I/O by itself for the breaker logic. `probe_once` (the actual HTTP
health-check) is a thin, SSRF-guarded, injectable hook used by the background loop (W4 wires the
real httpx call); offline we drive it with a fake prober. The optional health-log PG write goes
through store/admin_store and is BEST-EFFORT (a log-write failure never affects the breaker).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

# §2f knobs (env-overridable via config.registry_config(); defaults match the spec).
FAIL_THRESHOLD = 3
BACKOFF_BASE_S = 60
MAX_BACKOFF_S = 60 * 60  # cap the doubling at 1h so a long-dead provider still gets a periodic retry


@dataclass
class _CircuitState:
    fails: int = 0                 # consecutive failures since the last success
    open_until: float = 0.0        # epoch seconds the circuit stays open until (0 = closed)
    backoff_s: int = BACKOFF_BASE_S  # the CURRENT backoff (doubles on each re-open)
    last_change: float = 0.0
    last_error: str = ""


# process-local breaker map + lock (the registry reads this; never a PG hit on the hot path).
_CIRCUITS: Dict[Tuple[str, str], _CircuitState] = {}
_LOCK = threading.Lock()


def _key(tenant_id: str, provider_def_id: str) -> Tuple[str, str]:
    return (tenant_id or "", str(provider_def_id or ""))


def is_open(tenant_id: str, provider_def_id: str, *, now_fn: Callable[[], float] = time.time) -> bool:
    """True iff the circuit for this provider is currently OPEN (skip it; fall back by priority).

    Half-open semantics: once `open_until` has passed we return False to allow ONE trial call. If
    that trial fails, `record_failure` re-opens with the next doubled backoff."""
    with _LOCK:
        st = _CIRCUITS.get(_key(tenant_id, provider_def_id))
        if st is None:
            return False
        return now_fn() < st.open_until


def record_failure(tenant_id: str, provider_def_id: str, error: str = "",
                   *, now_fn: Callable[[], float] = time.time) -> _CircuitState:
    """Register a failed probe/call. On the FAIL_THRESHOLD-th consecutive failure the circuit
    opens; a re-open while already past threshold DOUBLES the backoff (60->120->240..., capped)."""
    now = now_fn()
    with _LOCK:
        st = _CIRCUITS.setdefault(_key(tenant_id, provider_def_id), _CircuitState())
        st.fails += 1
        st.last_error = (error or "")[:200]
        st.last_change = now
        if st.fails >= FAIL_THRESHOLD:
            # opening (or re-opening after a failed half-open trial)
            if st.open_until and now >= st.open_until:
                # a half-open trial just failed -> double the backoff for the next window
                st.backoff_s = min(st.backoff_s * 2, MAX_BACKOFF_S)
            elif not st.open_until:
                # first open at this threshold -> start at the base backoff
                st.backoff_s = BACKOFF_BASE_S
            st.open_until = now + st.backoff_s
        return _snapshot(st)


def record_success(tenant_id: str, provider_def_id: str,
                   *, now_fn: Callable[[], float] = time.time) -> _CircuitState:
    """Register a healthy probe/call: close the circuit, reset the fail count + backoff."""
    now = now_fn()
    with _LOCK:
        st = _CIRCUITS.setdefault(_key(tenant_id, provider_def_id), _CircuitState())
        st.fails = 0
        st.open_until = 0.0
        st.backoff_s = BACKOFF_BASE_S
        st.last_change = now
        st.last_error = ""
        return _snapshot(st)


def circuit_state(tenant_id: str, provider_def_id: str,
                  *, now_fn: Callable[[], float] = time.time) -> dict:
    """A JSON-able snapshot for the /admin/providers/health badge (never a secret)."""
    with _LOCK:
        st = _CIRCUITS.get(_key(tenant_id, provider_def_id))
        if st is None:
            return {"open": False, "fails": 0, "backoff_s": BACKOFF_BASE_S, "retry_in_s": 0,
                    "last_error": ""}
        now = now_fn()
        return {
            "open": now < st.open_until,
            "fails": st.fails,
            "backoff_s": st.backoff_s,
            "retry_in_s": max(0, int(st.open_until - now)) if st.open_until else 0,
            "last_error": st.last_error,
        }


def _snapshot(st: _CircuitState) -> _CircuitState:
    return _CircuitState(fails=st.fails, open_until=st.open_until, backoff_s=st.backoff_s,
                         last_change=st.last_change, last_error=st.last_error)


def reset_all() -> None:
    """Test helper: clear the in-memory breaker map (no production caller)."""
    with _LOCK:
        _CIRCUITS.clear()


# ---------------------------------------------------------------------------
# The probe orchestrator — drives the breaker from a (real or fake) prober.
# `prober(def_)` returns (healthy: bool, latency_ms: int, error_code: str). The REAL prober is an
# SSRF-guarded list-models / status GET wired in W4 (NEVER a generation endpoint — §2f). Offline,
# the test injects a fake prober to exercise open/backoff/close with zero network + a fake clock.
# ---------------------------------------------------------------------------
def run_probe(tenant_id: str, def_, prober: Callable[[object], Tuple[bool, int, str]],
              *, now_fn: Callable[[], float] = time.time,
              log_writer: Optional[Callable[..., None]] = None) -> dict:
    """Probe one provider def once and update the breaker. Returns the post-probe circuit_state.

    `log_writer(tenant_id, provider_def_id, is_healthy, latency_ms, error_code)` is an OPTIONAL
    best-effort health-log write (PG, append-only) — a failure there is swallowed and never
    affects the breaker (§2f: the breaker is in-memory, the log is for the UI/audit)."""
    pdid = getattr(def_, "id", None) or ""
    try:
        healthy, latency_ms, error_code = prober(def_)
    except Exception as exc:  # noqa: BLE001 — a throwing prober counts as a failure
        healthy, latency_ms, error_code = False, 0, f"probe_exc:{type(exc).__name__}"
    if healthy:
        record_success(tenant_id, pdid, now_fn=now_fn)
    else:
        record_failure(tenant_id, pdid, error_code, now_fn=now_fn)
    if log_writer is not None:
        try:
            log_writer(tenant_id, pdid, healthy, latency_ms, error_code)
        except Exception:  # noqa: BLE001 — best-effort; never affects the breaker
            pass
    return circuit_state(tenant_id, pdid, now_fn=now_fn)
