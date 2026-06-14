"""trunk_registry.health — REUSES the provider_registry in-memory circuit breaker.

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.1 / §8 ("REUSE ... health.py — import/share, do
not rewrite") + §2.5 (reputation-aware selection) + §3 (A1/A2/C-rel: in-process, not Redis).

The breaker PRIMITIVE (3-fail open, exponential backoff 60->120->240, half-open trial, success
closes) is identical to what a trunk needs for "is this trunk currently degraded? skip it +
fall back by priority". So we REUSE provider_registry.health's in-memory `_CIRCUITS` map and its
is_open / record_failure / record_success / circuit_state / run_probe verbatim — ONE breaker
implementation on the box, keyed per (tenant_id, trunk_id). NO PG hit on the hot path (the
breaker is in-memory; the PG sip_trunk_health_log is the append-only audit/reputation trail,
written best-effort via store.write_health_row).

NOTE — this is the *circuit* breaker (transient trunk degradation). The *spam-reputation*
quarantine (zero-duration ring-out burst, red-team B-rel) is a DIFFERENT, slower mechanism and
lives in rotation.py (it writes `quarantined_until` to PG + escalates). Both feed trunk
selection in registry.get_trunk: a circuit-open OR a PG-quarantined trunk is skipped.

import-safe: if provider_registry is absent, this module provides a tiny local breaker so the
trunk registry still degrades gracefully (it just won't share the breaker map — acceptable, the
provider registry is always present on the box).
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

try:  # pragma: no cover - the box always ships provider_registry alongside this package.
    from provider_registry.health import (  # type: ignore  # noqa: F401
        FAIL_THRESHOLD,
        BACKOFF_BASE_S,
        MAX_BACKOFF_S,
        is_open,
        record_failure,
        record_success,
        circuit_state,
        run_probe,
        reset_all,
    )
    _SHARED_OK = True
except Exception:  # noqa: BLE001 — local fallback breaker (never the box path).
    _SHARED_OK = False
    import threading
    import time as _time
    from dataclasses import dataclass as _dc

    FAIL_THRESHOLD = 3
    BACKOFF_BASE_S = 60
    MAX_BACKOFF_S = 60 * 60

    @_dc
    class _CS:
        fails: int = 0
        open_until: float = 0.0
        backoff_s: int = BACKOFF_BASE_S
        last_error: str = ""

    _C: dict = {}
    _L = threading.Lock()

    def _k(t, p):
        return (t or "", str(p or ""))

    def is_open(tenant_id, trunk_id, *, now_fn: Callable[[], float] = _time.time) -> bool:  # type: ignore[no-redef]
        with _L:
            st = _C.get(_k(tenant_id, trunk_id))
            return bool(st and now_fn() < st.open_until)

    def record_failure(tenant_id, trunk_id, error="", *, now_fn=_time.time):  # type: ignore[no-redef]
        now = now_fn()
        with _L:
            st = _C.setdefault(_k(tenant_id, trunk_id), _CS())
            st.fails += 1
            st.last_error = (error or "")[:200]
            if st.fails >= FAIL_THRESHOLD:
                if st.open_until and now >= st.open_until:
                    st.backoff_s = min(st.backoff_s * 2, MAX_BACKOFF_S)
                elif not st.open_until:
                    st.backoff_s = BACKOFF_BASE_S
                st.open_until = now + st.backoff_s
            return st

    def record_success(tenant_id, trunk_id, *, now_fn=_time.time):  # type: ignore[no-redef]
        with _L:
            st = _C.setdefault(_k(tenant_id, trunk_id), _CS())
            st.fails = 0
            st.open_until = 0.0
            st.backoff_s = BACKOFF_BASE_S
            st.last_error = ""
            return st

    def circuit_state(tenant_id, trunk_id, *, now_fn=_time.time) -> dict:  # type: ignore[no-redef]
        with _L:
            st = _C.get(_k(tenant_id, trunk_id))
            if st is None:
                return {"open": False, "fails": 0, "backoff_s": BACKOFF_BASE_S, "retry_in_s": 0,
                        "last_error": ""}
            now = now_fn()
            return {"open": now < st.open_until, "fails": st.fails, "backoff_s": st.backoff_s,
                    "retry_in_s": max(0, int(st.open_until - now)) if st.open_until else 0,
                    "last_error": st.last_error}

    def run_probe(tenant_id, def_, prober, *, now_fn=_time.time, log_writer=None) -> dict:  # type: ignore[no-redef]
        pdid = getattr(def_, "id", None) or ""
        try:
            healthy, latency_ms, error_code = prober(def_)
        except Exception as exc:  # noqa: BLE001
            healthy, latency_ms, error_code = False, 0, f"probe_exc:{type(exc).__name__}"
        if healthy:
            record_success(tenant_id, pdid, now_fn=now_fn)
        else:
            record_failure(tenant_id, pdid, error_code, now_fn=now_fn)
        if log_writer is not None:
            try:
                log_writer(tenant_id, pdid, healthy, latency_ms, error_code)
            except Exception:  # noqa: BLE001
                pass
        return circuit_state(tenant_id, pdid, now_fn=now_fn)

    def reset_all() -> None:  # type: ignore[no-redef]
        with _L:
            _C.clear()


# ---------------------------------------------------------------------------
# Trunk-friendly aliases (same primitive; clearer names at the trunk call sites).
# ---------------------------------------------------------------------------
def trunk_is_degraded(tenant_id: str, trunk_id: str, *,
                      now_fn: Callable[[], float] = None) -> bool:
    """True iff this trunk's transient circuit is OPEN (skip it; fall back by priority)."""
    import time as _t
    return is_open(tenant_id, trunk_id, now_fn=now_fn or _t.time)


def trunk_health_snapshot(tenant_id: str, trunk_id: str) -> dict:
    """A JSON-able non-secret snapshot for the /telephony health badge."""
    return circuit_state(tenant_id, trunk_id)
