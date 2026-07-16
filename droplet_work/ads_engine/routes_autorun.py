"""ads_engine.routes_autorun — the AUTONOMY + STANDALONE-CREATIVE sub-router (BLINDSPOTS B9/B10/B6).

A SEPARATE route surface mounted onto the main /ads router by endpoints.build_router via a single
`register(router, deps)` call (so endpoints.py stays minimally edited). Every route reuses the
host router's already-wired auth/RBAC/audit closures (passed in `deps`) — NO new auth code here.

Routes (all under /ads, FEATURE_ADS-gated by the shared `auth` closure):
  GET  /ads/autorun/status            -> orchestrator config + preconditions + phase cursor
  POST /ads/autorun/enable            -> opt a tenant in {brief, autopilot_launch?, uploaded_asset_id?}
  POST /ads/autorun/disable           -> opt out
  POST /ads/autorun/advance           -> manually advance the cursor ONE phase (operator kick)
  POST /ads/creative/standalone       -> B10: type a brief -> creative job, NO pre-existing plan_id
  POST /ads/creative/bridge           -> B6: bridge a media-engine asset -> moderated ad variant
  POST /ads/media/register            -> mirror a media-engine asset into the backend gallery

EARNER-SAFE: every spend/launch path stays behind the SAME gates as the manual surface (autopilot
launch needs both global ADS_AUTORUN_AUTOLAUNCH and the per-tenant opt-in; campaign.approve honours
ADS_DRY_RUN). These routes only sequence/decouple existing gated calls — they add no spend authority.
"""

from __future__ import annotations

from typing import Any

from . import config, orchestrator


def register(router: Any, deps: Any) -> None:
    """Attach the autonomy + standalone-creative routes to the host /ads router.

    `deps` carries the host's closures: auth(request)->(t,err), write_gate(request,t)->resp|None,
    tid(t)->str, body(request)->dict, audit(request,t,action,obj_type,obj_id,meta), forbidden(msg),
    json(payload, status_code=200). Crash-proof: a registration failure must never break the mount.
    """
    JSON = deps.json
    auth = deps.auth
    write_gate = deps.write_gate
    tid = deps.tid
    body = deps.body
    audit = deps.audit
    forbidden = deps.forbidden

    # ---------------------------------------------------------------- AUTORUN
    @router.get("/autorun/status")
    async def autorun_status(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        try:
            return JSON(orchestrator.status(tid(t)))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "status_error"}, status_code=200)

    @router.post("/autorun/enable")
    async def autorun_enable(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        brief = b.get("brief") if isinstance(b.get("brief"), dict) else {}
        if not brief:
            return forbidden("brief required")
        actor = str((t or {}).get("user_id") or (t or {}).get("email") or "operator")
        try:
            res = orchestrator.enable(
                tid(t), dict(brief),
                autopilot_launch=bool(b.get("autopilot_launch")),
                uploaded_asset_id=str(b.get("uploaded_asset_id") or ""),
                actor=actor)
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "enable_failed"}, status_code=200)
        audit(request, t, "ads.autorun.enable", "autorun", tid(t),
              {"autopilot_launch": bool(b.get("autopilot_launch"))})
        return JSON(res)

    @router.post("/autorun/disable")
    async def autorun_disable(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        try:
            res = orchestrator.disable(tid(t))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "disable_failed"}, status_code=200)
        audit(request, t, "ads.autorun.disable", "autorun", tid(t), {})
        return JSON(res)

    @router.post("/autorun/advance")
    async def autorun_advance(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        try:
            res = await orchestrator.advance(tid(t))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "advance_failed"}, status_code=200)
        audit(request, t, "ads.autorun.advance", "autorun", tid(t),
              {"phase": res.get("phase"), "advanced": res.get("advanced")})
        return JSON({"ok": True, "result": res, "status": orchestrator.status(tid(t))})

    # ------------------------------------------------------ STANDALONE CREATIVE
    @router.post("/creative/standalone")
    async def creative_standalone(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        brief = b.get("brief") if isinstance(b.get("brief"), dict) else {}
        if not brief:
            return forbidden("brief required")
        kinds = b.get("kinds") if isinstance(b.get("kinds"), list) else None
        sizes = b.get("sizes") if isinstance(b.get("sizes"), list) else None
        try:
            res = orchestrator.standalone_generate(tid(t), dict(brief), kinds=kinds, sizes=sizes)
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "standalone_failed"}, status_code=200)
        audit(request, t, "ads.creative.standalone", "creative_job",
              str((res.get("job") or {}).get("job_id", "")),
              {"plan_id": res.get("plan_id"), "synthetic_plan": (res.get("draft") or {}).get("synthetic")})
        return JSON(res)

    @router.post("/creative/bridge")
    async def creative_bridge(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        asset_id = str(b.get("asset_id") or "")
        if not asset_id:
            return forbidden("asset_id required")
        brief = b.get("brief") if isinstance(b.get("brief"), dict) else {}
        plan_id = str(b.get("plan_id") or "")
        try:
            res = orchestrator.bridge_media_asset(tid(t), asset_id, brief=dict(brief),
                                                  plan_id=plan_id)
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "bridge_failed"}, status_code=200)
        audit(request, t, "ads.creative.bridge", "ad_variant",
              str((res.get("variant") or {}).get("variant_id", "")),
              {"asset_id": asset_id, "plan_id": res.get("plan_id")})
        return JSON(res)

    @router.post("/media/register")
    async def media_register(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        asset = b.get("asset") if isinstance(b.get("asset"), dict) else {}
        if not asset:
            return forbidden("asset required")
        try:
            row = orchestrator.register_media_asset(tid(t), dict(asset))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "error": "register_failed"}, status_code=200)
        audit(request, t, "ads.media.register", "media_asset",
              str(row.get("asset_id", "")), {})
        return JSON({"ok": True, "asset": row})
