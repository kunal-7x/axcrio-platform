"""voice_ops.flywheel.router — the Flywheel super-admin console HTTP surface (prefix /flywheel).

Mounted from caller.py via build_router(...), the SAME dependency-injection pattern as
grow.endpoints / pmodel.router / provider_registry: the droplet injects the auth helpers
(resolve_tenant / can / need_auth / forbidden), the super-admin predicate, the audit sink, and an
`apply_config` callback (so a HUMAN-approved challenger's config is applied to the live campaign +
a config_changed event emitted by the DROPLET — the package itself never writes campaign state).

LAWS: tenant is TOKEN-derived (resolve_tenant), NEVER a body/query param (an admin may pass
?tenant= to inspect a specific tenant, but a non-admin is always pinned to their own). Writes
(approve/reject/label) require super-admin + audit. Reads degrade to a clean shape (never 500) and
to a labelled demo payload when ClickHouse is empty, so the console is alive day-one. build_router
returns None when FastAPI is unavailable (dormant-safe), and the mount is flag-gated in caller.py.
"""
from __future__ import annotations

import json
import logging

from . import config as _cfg
from . import store as _st
from . import schema as S

logger = logging.getLogger("flywheel.router")


def build_router(resolve_tenant, can, need_auth, forbidden, *,
                 require_super_admin=None, audit=None, apply_config=None):
    try:
        from fastapi import APIRouter, Form, Request
        from fastapi.responses import JSONResponse
    except Exception:  # noqa: BLE001 — FastAPI absent ⇒ dormant
        return None

    r = APIRouter(prefix="/flywheel", tags=["flywheel"])

    def _scope(t: dict, request: "Request") -> str:
        """Tenant boundary: own tenant, unless an admin explicitly inspects ?tenant=X."""
        if t.get("is_admin"):
            q = (request.query_params.get("tenant") or "").strip()
            if q:
                return q
        return t.get("tenant_id", "")

    def _super(t: dict) -> bool:
        if require_super_admin is not None:
            try:
                return bool(require_super_admin(t))
            except Exception:  # noqa: BLE001
                return False
        return bool(t.get("is_admin"))

    def _audit(request, t, action, target):
        if audit:
            try:
                audit(request, t, action, "flywheel", target, channel="control")
            except Exception:  # noqa: BLE001
                pass

    async def _challenger_by_id(tenant_id: str, cid: str):
        data = await _st.read_challengers(tenant_id)
        for row in data.get("challengers") or []:
            if row.get("challenger_id") == cid:
                return row
        return None

    # ----- dormancy probe / health (un-scoped, no secrets) ----------------- #
    @r.get("/health")
    async def health(request: Request):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(_cfg.status())

    # ----- reads (tenant-scoped) ------------------------------------------- #
    @r.get("/dashboard")
    async def dashboard(request: Request, minutes: int = 43200):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        try:
            data = await _st.read_dashboard(_scope(t, request), minutes)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"error": str(exc)[:200], "trajectory": {}, "preferences": {}})
        data["enabled"] = _cfg.load().active()
        return JSONResponse(data)

    @r.get("/trajectory/{call_id}")
    async def trajectory(request: Request, call_id: str):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_trajectory(_scope(t, request), call_id))

    @r.get("/moves")
    async def moves(request: Request, vertical: str = ""):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_moves(_scope(t, request), vertical))

    @r.get("/bandit")
    async def bandit(request: Request, campaign_id: str = ""):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_bandit(_scope(t, request), campaign_id))

    @r.get("/preferences")
    async def preferences(request: Request, objection: str = "", temp: str = "", limit: int = 100):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_preferences(_scope(t, request), objection, temp, limit))

    @r.get("/challengers")
    async def challengers(request: Request, status: str = ""):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_challengers(_scope(t, request), status))

    @r.get("/labels")
    async def labels(request: Request):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_labels(_scope(t, request)))

    @r.get("/monitors")
    async def monitors(request: Request, minutes: int = 43200):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_monitors(_scope(t, request), minutes))

    # ----- power-up tier reads (B1–B7) ------------------------------------- #
    @r.get("/causal")
    async def causal(request: Request, vertical: str = "", minutes: int = 43200):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_move_cate(_scope(t, request), vertical, minutes))

    @r.get("/critic")
    async def critic(request: Request):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_critic(_scope(t, request)))

    @r.get("/policy")
    async def policy(request: Request, campaign_id: str = ""):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_policy(_scope(t, request), campaign_id))

    @r.get("/play-library")
    async def play_library(request: Request, objection: str = ""):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_play_library(_scope(t, request), objection))

    @r.get("/archetypes")
    async def archetypes(request: Request):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_archetypes(_scope(t, request)))

    @r.get("/sim-rollouts")
    async def sim_rollouts(request: Request, minutes: int = 43200):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_sim_rollouts(_scope(t, request), minutes))

    @r.get("/sequential")
    async def sequential(request: Request, challenger_id: str = ""):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_sequential_state(_scope(t, request), challenger_id))

    @r.get("/distill")
    async def distill(request: Request):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(await _st.read_distill_runs(_scope(t, request)))

    # ----- writes (super-admin + audit; HUMAN-in-the-loop promotion) ------- #
    @r.post("/challengers/{cid}/approve")
    async def approve(request: Request, cid: str):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not _super(t):
            return forbidden("super-admin only")
        tenant_id = _scope(t, request)
        row = await _challenger_by_id(tenant_id, cid)
        if not row:
            return JSONResponse({"error": "not_found"}, status_code=404)
        from . import gate
        ch = _row_to_challenger(row, tenant_id)
        result = gate.promote(ch, approved_by=t.get("tenant_id", "admin"))
        # The DROPLET applies the approved config to the live campaign + emits config_changed.
        if result.get("ok") and apply_config:
            try:
                apply_config(tenant_id, ch.campaign_id, result.get("config") or {}, ch.kind)
            except Exception as exc:  # noqa: BLE001
                logger.warning("apply_config failed: %r", exc)
                result["apply_warning"] = str(exc)[:150]
        _audit(request, t, "flywheel.promote", cid)
        return JSONResponse(result)

    @r.post("/challengers/{cid}/reject")
    async def reject(request: Request, cid: str, reason: str = Form("")):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not _super(t):
            return forbidden("super-admin only")
        tenant_id = _scope(t, request)
        row = await _challenger_by_id(tenant_id, cid)
        if not row:
            return JSONResponse({"error": "not_found"}, status_code=404)
        from . import gate
        ch = _row_to_challenger(row, tenant_id)
        result = gate.reject(ch, approved_by=t.get("tenant_id", "admin"), reason=reason)
        _audit(request, t, "flywheel.reject", cid)
        return JSONResponse(result)

    @r.post("/labels/{call_id}/{turn}")
    async def submit_label(request: Request, call_id: str, turn: int,
                           label: str = Form(""), rationale: str = Form("")):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not _super(t):
            return forbidden("super-admin only")
        tenant_id = _scope(t, request)
        hl = S.HumanLabel(tenant_id=tenant_id, call_id=call_id, turn_num=int(turn or 0),
                          ts_iso=S.now_iso(), trigger="manual", label=(label or "")[:40],
                          labeler=t.get("tenant_id", "admin"), rationale=rationale,
                          used_for_calibration=True)
        ok = _st.insert_human_labels([hl])
        _audit(request, t, "flywheel.label", f"{call_id}:{turn}")
        return JSONResponse({"ok": bool(ok)})

    return r


def _row_to_challenger(row: dict, tenant_id: str):
    return S.Challenger(
        tenant_id=tenant_id, challenger_id=row.get("challenger_id", ""),
        ts_iso=S.now_iso(), kind=row.get("kind", "variant"),
        campaign_id=row.get("campaign_id", ""),
        proposed_config_json=row.get("proposed_config_json", ""),
        rationale=row.get("rationale", ""),
        ope_snips_value=float(row.get("ope_snips_value", 0) or 0),
        gates_passed=bool(row.get("gates_passed", 0)),
        replay_delta=float(row.get("replay_delta", 0) or 0),
        shadow_ok=bool(row.get("shadow_ok", 0)), status=row.get("status", "proposed"),
        approved_by=row.get("approved_by", ""), reward_lift=float(row.get("reward_lift", 0) or 0),
        ttft_ms=int(row.get("ttft_ms", 0) or 0),
        cost_per_appointment=float(row.get("cost_per_appointment", 0) or 0))
