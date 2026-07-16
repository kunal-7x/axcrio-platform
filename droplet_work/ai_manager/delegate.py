"""ai_manager.delegate — the workforce RUNNER seam (spec §C). Maps an NLU match to a concrete
action card, loads best-effort vendor context for the brain, and EXECUTES a single tool through the
ai_manager.tools registry (live loopback when transport is configured, in-memory stub otherwise).

THE LLM NEVER AUTHORIZES. Risk + step-up scope are derived deterministically from identity.classify_risk
/ identity.stepup_scope — the model's own risk guess is ignored everywhere downstream. This module only
runs what the state_machine / endpoints safety spine already permitted (permission + PIN/step-up gates
live in those callers); here we dispatch the tool, mint a run token when live, and map the adapter's
{ok,data,reason,status,actual_spend_minor} result into the dual-shape result the two consumers read:
  * state_machine reads action["scope"] + result["status"] (executed iff status=="done"),
  * endpoints reads result["effective"] + result["data"] (+ run_id/reason/last_reason/parked/outcome).
So execute() ALWAYS returns BOTH status (with "done" on success) AND effective + data + run_id + reason +
last_reason + parked + outcome.

IMPORT-SAFE: nothing here imports identity / tools / config / transport at module load — every heavy dep
is lazy inside the function, each guarded so an ABSENT sibling (config/identity not yet built, transport
dormant, no db.engine/keys) degrades to an honest dormant result instead of crashing. NEVER raises.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Optional


def role_for(tool: str) -> str:
    """The target module (target_module on the action_run row) — the bit before the first dot.
    `state_machine` passes this as `target_module=`. "" / no-dot tool -> the whole string. NEVER raises."""
    t = (tool or "").strip()
    return t.split(".", 1)[0] if t else ""


def map_intent_to_action(match: dict) -> dict:
    """Turn an NLU match card into a concrete action card the runner + safety spine consume.

    Returns {tool, risk, scope, args} — `risk`/`scope` are DETERMINISTIC (identity.classify_risk /
    identity.stepup_scope), never the model's guess. `scope` is read by state_machine._step_up; `risk`
    by both consumers; `args` is a fresh dict copy of the match slots. Degrades to a safe empty action
    when identity isn't importable. NEVER raises."""
    m = match or {}
    tool = (m.get("intent", "") or "").strip()
    risk = "safe"
    scope = ""
    try:
        from . import identity as _identity
        risk = _identity.classify_risk(tool)
        scope = _identity.stepup_scope(tool)
    except Exception:  # noqa: BLE001 — identity absent / not yet built: default-safe action card.
        risk, scope = "safe", ""
    return {"tool": tool, "risk": risk, "scope": scope, "args": dict(m.get("slots", {}) or {})}


def read_context(tenant_id: str, runner: Optional[Callable] = None) -> dict:
    """Best-effort vendor context for the NLU (business_name / active_campaigns / wallet / grants / ...).

    OFFLINE / dormant -> {} (the brain degrades to placeholder readouts). When transport is configured we
    MAY pull a small read-only snapshot over the loopback; ANY error / blank tenant -> {}. `runner` is an
    optional injected fetcher (tests / a live workforce.run_agent) — when callable it is preferred. The two
    consumers call this differently (endpoints: read_context(tid); state_machine: read_context(tid,
    runner=...)) so `runner` stays an optional kw. NEVER raises."""
    if not (tenant_id or "").strip():
        return {}
    # 1) an injected fetcher wins (tests / a live runner that already holds the org context).
    if callable(runner):
        try:
            ctx = runner(tenant_id)
            return dict(ctx) if isinstance(ctx, dict) else {}
        except Exception:  # noqa: BLE001
            return {}
    # 2) dormant unless transport is configured — no socket on a keyless box.
    try:
        from . import config as _config
        if not _config.transport_configured():
            return {}
    except Exception:  # noqa: BLE001
        return {}
    # 3) live: pull a tiny read-only snapshot (best-effort; any miss -> {}). Reads are idempotent / no-PIN.
    try:
        from .tools import transport as _t
        out: dict = {}
        resp = _t.call("GET", "/analytics", run_token="", params={"tenant_id": tenant_id})
        if isinstance(resp, dict) and resp.get("ok"):
            data = resp.get("data") or {}
            if isinstance(data, dict):
                for k in ("business_name", "active_campaigns", "recent_leads", "wallet",
                          "available_modules", "grants"):
                    if k in data:
                        out[k] = data[k]
        return out
    except Exception:  # noqa: BLE001
        return {}


# ----- the terminal reasons that mean "the target module simply isn't switched on" (honest no-op) -----
_NOT_CONFIGURED_REASONS = {"not_configured", "transport_dormant", "transport_error", "disabled"}
# HTTP-ish statuses an adapter may surface: 404/503 = unmounted/off -> not_configured; 402 = no credits.
_NOT_CONFIGURED_STATUS = {404, 503, "404", "503"}
_INSUFFICIENT_STATUS = {402, "402"}


def execute(tenant_id: str, action: dict, *, tenant_dict: Optional[dict] = None,
            step_up_token: str = "", actor: str = "", runner: Optional[Callable] = None,
            is_admin: bool = False) -> dict:
    """Dispatch ONE already-authorized action through the tool registry and report the TRUTH.

    The permission + PIN/step-up gates were enforced by the caller (state_machine S5-S7 / endpoints
    /execute); here we just run the tool and map its {ok,data,reason,status,actual_spend_minor} result.

    Returns a dict carrying BOTH consumers' keys:
      status  : "done" on a real side effect / successful read, else not_configured | insufficient_credits
                | error | <reason> (state_machine: executed iff status=="done").
      effective: bool — a real side effect actually landed (== ok). (endpoints truth-in-reporting.)
      data    : dict — the read/response payload (scrubbed of transport meta by the caller).
      run_id  : str — the dispatched-run id (from the tool, else a minted run_<hex>).
      reason  : str — failure reason ("" on success).
      last_reason / outcome / parked : mirrors endpoints reads (parked.scope = the park status).

    A `runner` callable, when injected (tests / a StubDelegate), is preferred over the registry path and
    its dict is adapted identically — lets the offline lifecycle inject a fake. NEVER raises."""
    action = action or {}
    tool = (action.get("tool", "") or "").strip()
    args = dict(action.get("args", {}) or {})

    # fail-closed on a blank tenant: nothing is dispatched, reported as an honest error (no side effect).
    if not (tenant_id or "").strip():
        return _fail("error", "blank_tenant")
    if not tool:
        return _fail("error", "unknown_tool")

    # 1) an injected runner wins (tests inject a StubDelegate; a live box may inject workforce.run_agent).
    if callable(runner):
        try:
            res = runner(tenant_id, action, tenant_dict=tenant_dict, step_up_token=step_up_token,
                         actor=actor, is_admin=is_admin)
        except TypeError:
            # a leaner fake that only takes (tenant_id, action).
            try:
                res = runner(tenant_id, action)
            except Exception:  # noqa: BLE001
                return _fail("error", "runner_error")
        except Exception:  # noqa: BLE001
            return _fail("error", "runner_error")
        return _adapt(res)

    # 2) pick the catalog: live loopback when transport is configured, else the in-memory stub mirror.
    try:
        from . import config as _config
        mode = "live" if _config.transport_configured() else "stub"
    except Exception:  # noqa: BLE001 — config absent: behave dormant (stub).
        mode = "stub"

    try:
        from . import tools as _tools
        reg = _tools.build_registry(mode)
    except Exception:  # noqa: BLE001 — registry can't build: report dormant, never crash.
        return _fail("not_configured", "not_configured")

    spec = reg.get(tool)
    if spec is None:
        return _fail("error", "unknown_tool")

    # 3) build the call ctx. Stub tools ignore run_token; live tools read ctx["run_token"]. We mint a run
    # token over transport ONLY when live + needed; offline / dormant -> "" (transport then behaves
    # unauthenticated/dormant and the adapter parks gracefully).
    run_token = _mint_run_token(tenant_id, mode, is_admin=is_admin)
    ctx = {"run_token": run_token, "tenant_id": tenant_id, "step_up_token": step_up_token or "",
           "is_admin": bool(is_admin), "actor": actor or tenant_id}

    # 4) run it. Adapters NEVER raise — but we guard anyway (defense in depth).
    try:
        res = spec.fn(args, ctx)
    except Exception:  # noqa: BLE001
        return _fail("error", "exec_error")
    return _adapt(res)


# ============================================================================ #
# result mapping — adapter {ok,data,reason,status,actual_spend_minor} -> dual-shape result
# ============================================================================ #
def _adapt(res: Any) -> dict:
    """Map a tool/runner result into the result dict BOTH consumers read. The live catalog flattens the
    payload INTO the result (`_result`/`_result_parkable` return {ok:True, ...data..., spend}), so a nested
    `data` key may be absent — in that case the data IS the result minus the meta keys. NEVER raises."""
    if not isinstance(res, dict):
        # a non-dict (None / odd return) is an honest no-op error, not a crash.
        return _fail("error", "tool_failed")

    ok = bool(res.get("ok"))
    reason = res.get("reason") or ""
    if not isinstance(reason, str):
        reason = str(reason)
    pstatus = res.get("status")

    # data: prefer an explicit nested `data` dict; else the flattened payload (drop transport/meta keys).
    raw_data = res.get("data")
    if isinstance(raw_data, dict):
        data = dict(raw_data)
    else:
        data = {k: v for k, v in res.items()
                if k not in ("ok", "reason", "status", "run_id", "data")}

    run_id = res.get("run_id") or ("run_" + uuid.uuid4().hex[:10])

    if ok:
        return {"status": "done", "effective": True, "data": data, "run_id": run_id,
                "reason": "", "last_reason": "", "outcome": pstatus, "parked": {}}

    # ---- not ok: classify the failure honestly ----
    rkey = (reason or "").split(":", 1)[0].strip()
    if rkey in _NOT_CONFIGURED_REASONS or pstatus in _NOT_CONFIGURED_STATUS:
        status = "not_configured"
    elif pstatus in _INSUFFICIENT_STATUS or rkey == "insufficient_credits":
        status = "insufficient_credits"
    else:
        status = reason or "error"

    return {"status": status, "effective": False, "data": data, "run_id": run_id,
            "reason": reason, "last_reason": reason, "outcome": pstatus,
            "parked": {"scope": status}}


def _fail(status: str, reason: str) -> dict:
    """A no-side-effect failure result carrying every key the two consumers read (run_id minted so the
    action_run/command rows always have an id). `parked.scope` mirrors the status for endpoints."""
    return {"status": status, "effective": False, "data": {},
            "run_id": "run_" + uuid.uuid4().hex[:10], "reason": reason, "last_reason": reason,
            "outcome": None, "parked": ({} if status == "done" else {"scope": status})}


def _mint_run_token(tenant_id: str, mode: str, *, is_admin: bool = False) -> str:
    """Mint a per-run loopback Bearer for a LIVE dispatch (RLS/org-scoped). Stub mode / dormant transport
    / any error -> "" (the adapter then behaves dormant/unauthenticated and parks). NEVER raises."""
    if mode != "live":
        return ""
    try:
        from .tools import transport as _t
    except Exception:  # noqa: BLE001
        return ""
    # the box mints run tokens through caller.py; absent a real mint endpoint we fall back to "" (dormant).
    minter = getattr(_t, "mint_run_token", None)
    if callable(minter):
        try:
            tok = minter(tenant_id, is_admin=is_admin)
            return tok if isinstance(tok, str) else ""
        except Exception:  # noqa: BLE001
            return ""
    return ""
