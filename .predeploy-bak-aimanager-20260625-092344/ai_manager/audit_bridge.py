"""ai_manager.audit_bridge — thin wrapper over the box-level `audit.py` (spec §G).

The AI-Manager state machine + control-plane endpoints emit a small set of named lifecycle
events (call_start / call_end / authed / auth_fail / stepup_ok / stepup_fail /
permission_denied / cancelled / execute). On the LIVE box those route to the immutable
`audit.py` channel; on THIS local box `audit.py` is ABSENT, so every function here is a pure
no-op that swallows all exceptions and returns None.

INVARIANTS (spec GLOBAL + §G):
  * Import never raises, never does I/O — `audit` is imported LAZILY inside each call, guarded.
  * NEVER load-bearing: every consumer wraps these calls in try/except already, and so do we —
    an absent / broken `audit.py` degrades silently to a no-op, never crashes a call.
  * No raw PIN / OTP / secret ever reaches the audit sink: every `meta` payload is scrubbed
    (secret-shaped keys -> "***") before it leaves this module.
  * Tenant is always the arg (the verified caller is the actor); we never invent one.

This module is purely the `audit.py` bridge. state_machine already calls
`store.record_audit_log` directly for the durable PG audit table, so we do NOT mirror to the
store here (that would double-write); we only fan the named event out to `audit.py`.
"""
from __future__ import annotations

from typing import Any, Optional

# Keys whose VALUES must never be persisted/logged in cleartext (case-insensitive match).
_SECRET_KEYS = {"pin", "otp", "secret", "code", "token", "step_up_token", "pin_hash", "salt"}


def _audit_mod():
    """Lazy-import the top-level `audit` module. Returns the module or None when it's absent
    (as on this local box) / un-importable. NEVER raises."""
    try:
        import audit as _a  # type: ignore  # top-level box module; absent locally -> no-op
        return _a
    except Exception:  # noqa: BLE001
        return None


def _scrub(value: Any) -> Any:
    """Deep-scrub any secret-shaped key (case-insensitive) -> '***'. Recurses dict/list, leaves
    scalars untouched. NEVER raises (returns the input on any error)."""
    try:
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if isinstance(k, str) and k.strip().lower() in _SECRET_KEYS:
                    out[k] = "***"
                else:
                    out[k] = _scrub(v)
            return out
        if isinstance(value, (list, tuple)):
            return [_scrub(v) for v in value]
        return value
    except Exception:  # noqa: BLE001
        return value


def _emit(event: str, *, actor: str, tenant_id: str, meta: Optional[dict] = None) -> None:
    """Best-effort route a named event to `audit.record(...)`. Scrubs secrets, swallows
    everything. Returns None always. The box `audit.record` signature is duck-typed
    (channel/actor/tenant_id/event/meta); if it differs / is absent we degrade to a no-op."""
    a = _audit_mod()
    if a is None:
        return None
    try:
        rec = getattr(a, "record", None)
        if not callable(rec):
            return None
        rec(channel="ai_manager", actor=actor or "", tenant_id=tenant_id or "",
            event=event, meta=_scrub(meta or {}))
    except Exception:  # noqa: BLE001
        return None
    return None


# ---------------- the named lifecycle events (consumers: state_machine + endpoints) ----------------
def call_start(*, actor: str, tenant_id: str, session_id: str, meta: Optional[dict] = None) -> None:
    """S0 CONNECT — a command session opened. `actor` is "anon" pre-auth (tenant unknown yet)."""
    payload = {"session_id": session_id}
    payload.update(_scrub(meta or {}))
    return _emit("call_start", actor=actor, tenant_id=tenant_id, meta=payload)


def call_end(*, actor: str, tenant_id: str, session_id: str, outcome: str, n_actions: int) -> None:
    """S_END — the session closed. `outcome` carries the terminal disposition; `n_actions` the
    count of real side effects executed."""
    return _emit("call_end", actor=actor, tenant_id=tenant_id,
                 meta={"session_id": session_id, "outcome": outcome, "n_actions": n_actions})


def authed(*, actor: str, tenant_id: str, session_id: str, method: str) -> None:
    """S2 — the human proved themselves (login PIN/OTP matched). NO secret in the payload."""
    return _emit("authed", actor=actor, tenant_id=tenant_id,
                 meta={"session_id": session_id, "method": method})


def auth_fail(*, actor: str, tenant_id: str, session_id: str, attempts: int, reason: str) -> None:
    """S2 — a login attempt failed. Records the running attempt count + a non-secret reason."""
    return _emit("auth_fail", actor=actor, tenant_id=tenant_id,
                 meta={"session_id": session_id, "attempts": attempts, "reason": reason})


def stepup_ok(*, actor: str, tenant_id: str, session_id: str, scope: str, action: str) -> None:
    """S6 — a fresh, scoped per-action step-up succeeded for `action` under `scope`."""
    return _emit("stepup_ok", actor=actor, tenant_id=tenant_id,
                 meta={"session_id": session_id, "scope": scope, "action": action})


def stepup_fail(*, actor: str, tenant_id: str, session_id: str, scope: str, action: str,
                attempts: int) -> None:
    """S6 — a per-action step-up attempt failed."""
    return _emit("stepup_fail", actor=actor, tenant_id=tenant_id,
                 meta={"session_id": session_id, "scope": scope, "action": action,
                       "attempts": attempts})


def permission_denied(*, actor: str, tenant_id: str, session_id: str, action: str) -> None:
    """S5 — a capability check denied `action` (default-deny). `action` may be a tool name or a
    "blocked:<br>" / "pin_failed:<tool>" marker (endpoints)."""
    return _emit("permission_denied", actor=actor, tenant_id=tenant_id,
                 meta={"session_id": session_id, "action": action})


def cancelled(*, actor: str, tenant_id: str, session_id: str, action: str) -> None:
    """S7 — the caller declined the read-back confirmation (or cancelled a pending command)."""
    return _emit("cancelled", actor=actor, tenant_id=tenant_id,
                 meta={"session_id": session_id, "action": action})


def execute(*, actor: str, tenant_id: str, session_id: str, action: str,
            meta: Optional[dict] = None) -> None:
    """S8 — a delegated action was dispatched to the runner. `meta` carries {status, executed,
    run_id} (scrubbed); never the args' raw secrets."""
    payload = {"session_id": session_id, "action": action}
    payload.update(_scrub(meta or {}))
    return _emit("execute", actor=actor, tenant_id=tenant_id, meta=payload)


__all__ = [
    "call_start", "call_end", "authed", "auth_fail", "stepup_ok", "stepup_fail",
    "permission_denied", "cancelled", "execute",
]
