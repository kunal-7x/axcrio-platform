"""ads_engine.routes_llm — the V2-W4 sub-router: reasoning-model config + LLM features + creative AI.

A SEPARATE route surface mounted onto the main /ads router via one `register(router, deps)` call
(so endpoints.py stays minimally edited), reusing the host's already-wired auth/RBAC/audit closures.

Routes (all under /ads, FEATURE_ADS-gated by the shared `auth` closure):
  REASONING MODEL (vault-configurable, real-time, no redeploy — founder decision #2):
    GET  /ads/reasoning/status     -> secret-free config status (configured? provider/model/cap/spend)
    GET  /ads/reasoning/models     -> recommended provider->model catalog for the UI picker
    POST /ads/reasoning/select     -> set provider/model/key/cap into the vault (takes effect NOW)
    POST /ads/reasoning/test       -> tiny gateway ping proving the tenant's key+model actually route
  FIRST LLM FEATURE (proposal-only, routed through the gateway):
    POST /ads/copy/generate        -> N on-brand ad-copy angles for a brief
    POST /ads/brief/parse          -> infer an AdsBrief draft from a selected voice campaign
  AUTO CREATIVE-VARIANTS (through the moderation gate):
    POST /ads/creative/adapt       -> format/orientation adaptation of a master variant
    POST /ads/creative/slideshow   -> auto-slideshow video from a plan's static images
    POST /ads/creative/asset-bridge-> turn a gallery asset into a moderated ad variant on a plan_id

EARNER-SAFE: every LLM route is PROPOSAL-ONLY (returns text/assets, never spends/launches/mutates a
campaign). Creative routes run THROUGH the moderation gate. No spend authority is added here; these
routes only sequence existing gated/proposal calls. Crash-proof: a registration or route failure
never breaks the mount (the whole block is swallowed by endpoints.py's try/except).
"""

from __future__ import annotations

from typing import Any

from . import creative_variants, llm_copy, llm_gateway


def register(router: Any, deps: Any) -> None:
    """Attach the reasoning/LLM/creative-AI routes to the host /ads router.

    `deps` carries: json, auth(request)->(t,err), write_gate(request,t)->resp|None, tid(t)->str,
    body(request)->dict, audit(...), forbidden(msg), creative_service()->CreativeService.
    """
    JSON = deps.json
    auth = deps.auth
    write_gate = deps.write_gate
    tid = deps.tid
    body = deps.body
    audit = deps.audit
    forbidden = deps.forbidden
    creative_service = getattr(deps, "creative_service", None)

    # ----------------------------------------------------------- REASONING MODEL
    @router.get("/reasoning/status")
    async def reasoning_status(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        try:
            return JSON(llm_gateway.status(tid(t)))
        except Exception:  # noqa: BLE001
            return JSON({"configured": False, "reason": "status_error"}, status_code=200)

    @router.get("/reasoning/models")
    async def reasoning_models(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        return JSON({
            "providers": list(llm_gateway.PROVIDER_MAP.keys()),
            "recommended": llm_gateway.RECOMMENDED,
            "default_provider": llm_gateway.DEFAULT_PROVIDER,
            "default_model": llm_gateway.DEFAULT_MODEL,
            "gateway_available": llm_gateway.gateway_available(),
        })

    @router.post("/reasoning/select")
    async def reasoning_select(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        try:
            res = llm_gateway.save_selection(
                tid(t),
                provider=str(b.get("provider") or ""),
                model=str(b.get("model") or ""),
                api_key=str(b.get("api_key") or ""),
                base_url=str(b.get("base_url") or ""),
                monthly_cap_minor=b.get("monthly_cap_minor"),
                temperature=b.get("temperature"),
            )
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "reason": "select_failed"}, status_code=200)
        # SECRET-FREE audit: never log the key; record only which non-secret fields changed.
        audit(request, t, "ads.reasoning.select", "reasoning_model", tid(t),
              {"provider": b.get("provider"), "model": b.get("model"),
               "fields": [f for f in res.get("fields_written", []) if f != "api_key"]})
        return JSON(res)

    @router.post("/reasoning/test")
    async def reasoning_test(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        messages = [{"role": "user", "content": "Reply with the single word: ok"}]
        try:
            res = llm_gateway.complete(tid(t), messages, max_tokens=8, trace_name="ads.reasoning.test")
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "reason": "test_failed"}, status_code=200)
        audit(request, t, "ads.reasoning.test", "reasoning_model", tid(t),
              {"ok": res.get("ok"), "reason": res.get("reason"), "model": res.get("model")})
        # do NOT return the raw text verbatim beyond a short echo (no prompt-injection surface).
        return JSON({"ok": res.get("ok"), "reason": res.get("reason"),
                     "provider": res.get("provider"), "model": res.get("model"),
                     "cost_minor": res.get("cost_minor"),
                     "echo": str(res.get("text") or "")[:64]})

    # ---------------------------------------------------------- FIRST LLM FEATURE
    @router.post("/copy/generate")
    async def copy_generate(request: "Any") -> Any:
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
        try:
            res = llm_copy.generate_ad_copy(tid(t), dict(brief))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "angles": [], "reason": "copy_failed"}, status_code=200)
        audit(request, t, "ads.copy.generate", "llm_copy", tid(t),
              {"ok": res.get("ok"), "n": len(res.get("angles", [])),
               "model": res.get("model"), "cost_minor": res.get("cost_minor")})
        return JSON(res)

    @router.post("/brief/parse")
    async def brief_parse(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        fields = b.get("campaign") if isinstance(b.get("campaign"), dict) else \
            (b.get("fields") if isinstance(b.get("fields"), dict) else {})
        if not fields:
            return forbidden("campaign fields required")
        try:
            res = llm_copy.parse_brief(tid(t), dict(fields))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "brief": {}, "reason": "parse_failed"}, status_code=200)
        audit(request, t, "ads.brief.parse", "llm_copy",
              str(res.get("source_campaign_id") or ""),
              {"ok": res.get("ok"), "model": res.get("model"), "cost_minor": res.get("cost_minor")})
        return JSON(res)

    # --------------------------------------------------------- AUTO CREATIVE-VARIANTS
    def _svc():
        if creative_service is None:
            return None
        try:
            return creative_service()
        except Exception:  # noqa: BLE001
            return None

    @router.post("/creative/adapt")
    async def creative_adapt(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        master = str(b.get("master_variant_id") or b.get("variant_id") or "")
        if not master:
            return forbidden("master_variant_id required")
        families = b.get("families") if isinstance(b.get("families"), list) else None
        try:
            res = creative_variants.adapt_formats(_svc(), tid(t), master, families=families)
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "reason": "adapt_failed"}, status_code=200)
        audit(request, t, "ads.creative.adapt", "ad_variant", str(res.get("variant_id") or ""),
              {"master": master, "moderation_status": res.get("moderation_status"),
               "families_added": res.get("families_added")})
        return JSON(res)

    @router.post("/creative/slideshow")
    async def creative_slideshow(request: "Any") -> Any:
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        plan_id = str(b.get("plan_id") or "")
        if not plan_id:
            return forbidden("plan_id required")
        urls = b.get("image_urls") if isinstance(b.get("image_urls"), list) else None
        brief = b.get("brief") if isinstance(b.get("brief"), dict) else {}
        try:
            res = creative_variants.build_slideshow(_svc(), tid(t), plan_id,
                                                    image_urls=urls, brief=dict(brief))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "reason": "slideshow_failed"}, status_code=200)
        audit(request, t, "ads.creative.slideshow", "ad_variant", str(res.get("variant_id") or ""),
              {"plan_id": plan_id, "slides": len(res.get("slides", [])),
               "moderation_status": res.get("moderation_status")})
        return JSON(res)

    @router.post("/creative/asset-bridge")
    async def creative_asset_bridge(request: "Any") -> Any:
        """Turn an Image-Studio gallery asset into a MODERATED ad variant bound to a plan_id
        (the W1-deferred asset bridge). Reuses CreativeService.import_upload -> the same RERA/Housing
        gate applies; cross-tenant asset_id -> not_found."""
        t, err = auth(request)
        if err:
            return err
        gate = write_gate(request, t)
        if gate:
            return gate
        b = await body(request)
        asset_id = str(b.get("asset_id") or "")
        plan_id = str(b.get("plan_id") or "")
        if not asset_id or not plan_id:
            return forbidden("asset_id and plan_id required")
        brief = b.get("brief") if isinstance(b.get("brief"), dict) else {}
        svc = _svc()
        if svc is None:
            return JSON({"ok": False, "reason": "creative_unavailable"}, status_code=200)
        try:
            res = svc.import_upload(tid(t), plan_id, asset_id, brief=dict(brief))
        except Exception:  # noqa: BLE001
            return JSON({"ok": False, "reason": "bridge_failed"}, status_code=200)
        audit(request, t, "ads.creative.asset_bridge", "ad_variant",
              str(res.get("variant_id") or ""),
              {"asset_id": asset_id, "plan_id": plan_id,
               "moderation_status": res.get("moderation_status")})
        return JSON(res)
