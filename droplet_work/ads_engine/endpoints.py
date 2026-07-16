"""ads_engine.endpoints — the /ads/* router that lights up the EXISTING /ads UI.

`build_router(...)` mirrors provider_registry/endpoints.py:227 verbatim in spirit: it injects
caller's auth helpers (resolve_tenant / can / need_auth / forbidden / require_super_admin /
firewall / audit) so tenant_id is ALWAYS token-derived (NEVER body/query). The 6 contract routes
match `famit-panel/app/ads/_lib.ts` 1:1 (methods/paths/auth/headers); W5 ADDS functional creative
+ guardrails + decisions surfaces (additive — the contract routes are unchanged).

REDTEAM fixes wired here:
  * C4 — only this token-injected surface exists; the bare module-level `router` is REMOVED so
    no ads route is reachable without resolve_tenant injection. (The caller mount uses build_router.)
  * Defense in depth — EVERY route first checks config.is_enabled(); 404s when FEATURE_ADS is OFF
    even if mounted (mirrors provider_registry `_disabled()`).
  * M1 — EVERY `/{plan_id}` route applies require_object(tenant, rec): a tenant cannot read/mutate
    another tenant's campaign (404, doesn't reveal existence). can(t,"write") alone is tenant-blind.
  * M2 — spend/mutating routes (propose/approve/pause/optimize/creative-mutations) EXCLUDE the
    legacy static-password auth path: if auth_method(request) == "legacy_pw" -> 403. The
    un-revocable shared admin password must never spend money or mutate ad state.
  * Spend-mutating approve additionally requires a firewall step-up (X-Step-Up); fail-closed
    (blocked_not_approved) when no step-up is supplied — never an open launch.
  * C5 — /ads/optimize AUTO-APPLIES only spend-DECREASING moves; every non-decreasing move is
    drafted for approval (the guardrails chain decides). Nothing here spends (DRY-RUN).

W5 wires the real engine: propose/approve/pause delegate to `campaign.*` (HOUSING single-setter +
the CPA x50 viability gate + lifecycle), optimize delegates to `optimization.propose_* ->
guardrails.evaluate`, and /ads/creative/* drives the `CreativeService` factory (generate/list/
upload/moderate) through the vault seam. Everything stays DRY-RUN (config.dry_run() default ON):
no route ever spends real money or touches the live earner.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

# REDTEAM H2 (isolation): cap the number of lead items processed per inbound webhook request.
# Each ingest is a full read-modify-write of the tenant's JSON file, so an unbounded body (even a
# valid-HMAC one from the tenant's own page) is a CPU + rewrite-amplification DoS. A single Meta
# leadgen webhook delivery is normally a handful of items; 100 is a generous ceiling.
_WEBHOOK_MAX_ITEMS = 100

# REDTEAM H3 (isolation): hard cap on /ads/leads/import rows, enforced at the route. The function
# default was 5000 (~5000 full-file rewrites of a growing list = quadratic). 1000 is a sane per-call
# ceiling for the JSON store; larger imports must be chunked by the client.
_IMPORT_MAX_ROWS = 1000

# REDTEAM H4 (isolation): cap the number of optimize proposals (each appends a decision_log row via a
# full read-modify-write) drafted per /ads/optimize call across all of a tenant's bandit states.
_OPTIMIZE_MAX_PROPOSALS = 200

from . import analytics, budget, campaign, compliance, config, guardrails, leads as _leads_mod
from . import optimization, store, vault_adapter
from . import connectors as _connectors_mod
# `seams` is the FACTORY FUNCTION defined in __init__.py (returns the wired _SEAMS bag);
# `_seams_fn()` at the BOLA guard below calls it. There is intentionally NO `seams.py`
# submodule — creating one would make `from . import seams` resolve to the module and
# shadow the function, so `_seams_fn()` (and every `seams()` call in store/tick/
# vault_adapter/leads) would break and the whole router would go dark. DO NOT add seams.py.
from . import seams as _seams_fn
from .connectors.meta import MetaConnector as _MetaConnector

try:
    from fastapi import APIRouter, Request, Response
    from fastapi.responses import JSONResponse
    _HAVE_FASTAPI = True
except Exception:  # noqa: BLE001
    _HAVE_FASTAPI = False
    APIRouter = Request = Response = JSONResponse = None  # type: ignore


def build_router(resolve_tenant, can, need_auth, forbidden, *,
                 require_super_admin=None, firewall=None, audit=None, auth_method=None):
    """Build the /ads router injecting caller's auth helpers.

      resolve_tenant(request) -> {"tenant_id","role","is_admin",...}|None
      can(t, action) -> bool ; need_auth() -> 401 ; forbidden(msg) -> 403
      require_super_admin(request) -> tenant|Response  (excludes legacy-pw)
      firewall -> module (consume_reveal_step_up); absent => approve fail-closed
      audit(request, t, action, object_type, object_id, meta=) -> None
      auth_method(request) -> 'jwt'|'legacy_pw'|'hmac'|'none'  (M2 legacy-pw exclusion)

    Returns an APIRouter, or None if FastAPI is absent (the mount guard treats None as no-mount).
    Every route 404s while FEATURE_ADS is OFF (defense in depth).
    """
    if not _HAVE_FASTAPI:
        return None

    router = APIRouter(prefix="/ads", tags=["ads_engine"])

    # The campaign domain lazily defaults store/config; bind the connectors seam so the LIVE
    # publish path (DRY-RUN OFF) can resolve a provider. Idempotent + crash-proof.
    try:
        campaign.bind(store=store, config=config, connectors=_connectors_mod, guardrails=guardrails)
    except Exception:  # noqa: BLE001 — wiring must never crash the mount
        pass

    # ---- local helpers (mirror provider_registry) ----
    def _disabled():
        # flag OFF -> dormant: behave as if the feature does not exist (404).
        return JSONResponse({"error": "not_found"}, status_code=404)

    def _tid(t: dict) -> str:
        return str((t or {}).get("tenant_id") or "")

    async def _body(request) -> dict:
        try:
            b = await request.json()
            return b if isinstance(b, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _audit(request, t, action, object_type="campaign", object_id="", meta=None):
        if audit is None:
            return
        try:
            audit(request, t, action, object_type, object_id, meta=meta)
        except Exception:  # noqa: BLE001
            pass

    def _step_up_token(request) -> str:
        try:
            return (request.headers.get("x-step-up", "")
                    or request.headers.get("X-Step-Up", "") or "")
        except Exception:  # noqa: BLE001
            return ""

    def _verify_spend_step_up(token: str, sub: str) -> bool:
        """REDTEAM H1 (routes-auth): the SINGLE spend-class step-up verifier for approve + import.

        The old code called firewall.consume_reveal_step_up(token, "ads.campaign.approve"/"ads.leads.import", sub)
        — but that verifier hard-requires claims['aud'] == a real provider_def_id and scope == 'provider.reveal',
        so NO mintable token could ever satisfy it (the action string is never a provider id). With a real
        firewall wired that made the spend gate PERMANENTLY un-passable; and the `firewall is None` branch
        fell OPEN (accepted ANY non-empty header). Both are wrong.

        We now use the GENERIC step-up verifier `verify_step_up_token(token, 'spend', sub)` (firewall.py:278),
        which checks HS256 signature + exp + type=='step_up' + scope=='spend' + sub==tenant (F3 replay-bind).
        And we FAIL-CLOSED when no firewall/verifier is available: no firewall => no step-up => block.
        """
        if not token or not sub:
            return False
        if firewall is None:
            return False  # fail-CLOSED: no firewall => the spend gate cannot be satisfied.
        verifier = getattr(firewall, "verify_step_up_token", None)
        if verifier is None:
            return False  # fail-CLOSED: verifier absent => block (never accept a raw header).
        try:
            return bool(verifier(token, "spend", sub))
        except Exception:  # noqa: BLE001 — any verify error => no step-up (fail-closed)
            return False

    def _is_legacy_pw(request) -> bool:
        """M2: the un-revocable shared static password must never spend/mutate ad state.

        REDTEAM secrets-N1: this gate is consulted ONLY on the mutation path (_write_gate), so a
        classifier EXCEPTION must fail CLOSED (treat as legacy_pw => block the mutation) rather than
        fail open. If auth_method is not injected at all we can't classify, so we keep the prior
        behaviour (False) — mutations then rely on can(t,'write') alone, as before."""
        if auth_method is None:
            return False
        try:
            return auth_method(request) == "legacy_pw"
        except Exception:  # noqa: BLE001 — classifier error on a MUTATION path => fail CLOSED (block)
            return True

    def _auth(request):
        """Common gate: enabled + token-derived tenant. Returns (tenant, None) or (None, response)."""
        if not config.is_enabled():
            return None, _disabled()
        t = resolve_tenant(request)
        if not t:
            return None, need_auth()
        return t, None

    def _write_gate(request, t):
        """Mutation gate: can(write) + NOT legacy-pw (M2). Returns a Response to short-circuit, or None."""
        if not can(t, "write"):
            return forbidden("read-only")
        if _is_legacy_pw(request):
            return forbidden("legacy password cannot mutate ad campaigns")
        return None

    def _load_campaign(tenant_id, plan_id):
        try:
            return store.get_row(tenant_id, "campaigns", plan_id)
        except Exception:  # noqa: BLE001
            return None

    def _require_object(t, rec):
        """M1: BOLA guard via the injected require_object seam (defaults to 404). If the seam is
        absent, do an inline ownership check (rec.tenant_id == token tenant)."""
        s = _seams_fn()
        ro = getattr(s, "require_object", None)
        if ro is not None:
            try:
                return ro(t, rec)
            except Exception:  # noqa: BLE001
                pass
        if rec is None:
            return JSONResponse({"error": "not found"}, status_code=404)
        if rec.get("tenant_id") != _tid(t) and not (t or {}).get("is_admin"):
            return JSONResponse({"error": "not found"}, status_code=404)
        return None

    # ---- creative factory construction (per request; dormant-safe) ----
    def _creative_service():
        """Build a CreativeService bound to the vault seam. The model-secret resolver maps a
        creative model_id -> a provider_def_id via the vault adapter (named_provider lookup); when
        no def/cred exists, the generation stage degrades to not_configured (no crash, no spend).
        V2-W1: the AssetBridge is now INJECTED (was None) so approved variants mirror into the
        Image-Studio gallery and gallery assets can be adopted as ad variants (in-process, no HTTP,
        no token; degrades to a tenant-scoped store mirror if creative_engine is absent)."""
        from .creative import CreativeService
        from .asset_bridge import AssetBridge

        def _resolve_def_id(tenant_id, model_id):
            # creative models are a distinct vault provider family ("creative_gen"); resolve by
            # named_provider so a tenant's stored creative key is found. Best-effort, None-safe.
            try:
                return vault_adapter.resolve_provider_def_id(
                    tenant_id, named_provider="creative_gen", slug=str(model_id or "")) or ""
            except Exception:  # noqa: BLE001
                return ""

        bridge = None
        try:
            bridge = AssetBridge()
        except Exception:  # noqa: BLE001 — bridge construction must never break the mount
            bridge = None

        return CreativeService(
            get_secret_json=vault_adapter.get_secret_json,
            resolve_def_id=_resolve_def_id,
            asset_bridge=bridge,
        )

    # =========================================================================
    # 1) GET /ads/health  ->  AdsHealth  (token; read)
    # =========================================================================
    @router.get("/health")
    async def ads_health(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        return JSONResponse(analytics.health(_tid(t)))

    # =========================================================================
    # 2) GET /ads/campaigns  ->  AdsStatusResponse  (token; read)
    # =========================================================================
    @router.get("/campaigns")
    async def ads_campaigns(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        return JSONResponse(analytics.status(_tid(t)))

    # =========================================================================
    # 3) POST /ads/campaigns/propose  ->  {ok,status,plan_id,plan,viability}  (token + write)
    #    Delegates to campaign.propose: HOUSING single-setter + CPA x50 viability gate. A sub-floor
    #    housing launch is persisted blocked_insufficient_funds (cannot be approved). DRY: no spend.
    # =========================================================================
    @router.post("/campaigns/propose")
    async def ads_propose(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        body = await _body(request)
        brief = body.get("brief") if isinstance(body.get("brief"), dict) else {}
        tenant_id = _tid(t)
        try:
            result = campaign.propose(tenant_id, dict(brief or {}))
        except Exception:  # noqa: BLE001 — never crash the request; surface dormant-ish
            return JSONResponse({"ok": False, "status": "not_configured",
                                 "plan_id": "", "plan": {}}, status_code=200)
        _audit(request, t, "ads.campaign.propose", "campaign", result.get("plan_id") or "",
               {"status": result.get("status"),
                "verdict": (result.get("viability") or {}).get("verdict")})
        return JSONResponse(result)

    # =========================================================================
    # 4) POST /ads/campaigns/{plan_id}/approve  (token + write + X-Step-Up firewall)
    #    SPEND-MUTATING: legacy-pw excluded (M2). A campaign launch must ride a real step-up, so
    #    without X-Step-Up this fail-closes to blocked_not_approved (campaign.approve also refuses a
    #    warn_underfunded plan without step_up, and blocks a sub-floor one outright). DRY by default.
    # =========================================================================
    @router.post("/campaigns/{plan_id}/approve")
    async def ads_approve(plan_id: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tenant_id = _tid(t)
        rec = _load_campaign(tenant_id, plan_id)
        owner_err = _require_object(t, rec)  # M1 — own-or-404
        if owner_err:
            return owner_err

        # FAIL-CLOSED step-up: launching spends real money, so it MUST present an X-Step-Up token.
        # When a firewall is injected we consume the token (single-use); a missing/invalid token =>
        # blocked_not_approved (no launch). The presence of a validated step-up is what authorizes
        # a warn_underfunded override inside campaign.approve.
        token = _step_up_token(request)
        step_up = _verify_spend_step_up(token, tenant_id)
        if not step_up:
            _audit(request, t, "ads.campaign.approve_blocked", "campaign", plan_id,
                   {"reason": "blocked_not_approved", "phase": "step_up_required"})
            return JSONResponse({"ok": False, "status": "blocked_not_approved",
                                 "plan_id": plan_id, "reason": "approval requires a step-up (X-Step-Up)",
                                 "spending": False})

        actor = str((t or {}).get("user_id") or (t or {}).get("email") or "operator")
        try:
            result = await campaign.approve(tenant_id, plan_id, step_up=True, actor=actor)
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "status": "not_configured", "plan_id": plan_id,
                                 "reason": "approve failed", "spending": False}, status_code=200)
        _audit(request, t, "ads.campaign.approve", "campaign", plan_id,
               {"status": result.get("status"), "spending": result.get("spending")})
        return JSONResponse(result)

    # =========================================================================
    # 5) POST /ads/campaigns/{plan_id}/pause  (token + write)  body {reason}
    #    Always allowed (a pause is the spend-decreasing remedy; never learning-resetting).
    # =========================================================================
    @router.post("/campaigns/{plan_id}/pause")
    async def ads_pause(plan_id: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tenant_id = _tid(t)
        rec = _load_campaign(tenant_id, plan_id)
        owner_err = _require_object(t, rec)  # M1
        if owner_err:
            return owner_err
        body = await _body(request)
        reason = str(body.get("reason", "manual_pause"))[:200]
        actor = str((t or {}).get("user_id") or (t or {}).get("email") or "operator")
        try:
            result = await campaign.pause(tenant_id, plan_id, reason, actor=actor)
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "status": "not_configured", "plan_id": plan_id},
                                status_code=200)
        if not result.get("already"):
            _audit(request, t, "ads.campaign.pause", "campaign", plan_id, {"reason": reason})
        return JSONResponse(result)

    # =========================================================================
    # 6) POST /ads/optimize  (token + write)  body {dry_run, campaign_id?, account_id?}
    #    PROPOSE bandit/allocation moves -> run each through the guardrails chain. AUTO-APPLY ONLY
    #    spend-DECREASING moves (REDTEAM C5); every non-decreasing move is deferred for approval.
    #    Nothing here spends — the "apply" is a state/decision-log write only (DRY-RUN).
    # =========================================================================
    @router.post("/optimize")
    async def ads_optimize(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        body = await _body(request)
        dry = bool(body.get("dry_run", True))
        tenant_id = _tid(t)
        campaign_id = body.get("campaign_id")  # optional: optimize a single campaign's bandit
        account_id = body.get("account_id")    # optional: re-allocate one account's channels

        proposals: list[dict] = []

        # Collect candidate moves from the propose-only optimizer.
        try:
            if campaign_id:
                bstate = store.get_bandit_state(tenant_id, str(campaign_id))
                if bstate:
                    proposals.extend(optimization.propose_bandit_moves(bstate))
            else:
                for bstate in store.list_bandit_states(tenant_id):
                    proposals.extend(optimization.propose_bandit_moves(bstate))
            if account_id:
                alloc = store.get_allocation(tenant_id, str(account_id))
                if alloc:
                    proposals.extend(optimization.propose_allocation(alloc).get("moves", []))
        except Exception:  # noqa: BLE001 — optimizer must never crash the request
            proposals = []

        # REDTEAM H4 (isolation): bound the decision_log write fan-out per call — each appended row is
        # a full read-modify-write of the tenant's decision_log file, so an account with many bandit
        # states could drive a large synchronous write storm. Cap proposals processed per request.
        if len(proposals) > _OPTIMIZE_MAX_PROPOSALS:
            proposals = proposals[:_OPTIMIZE_MAX_PROPOSALS]

        # Dispose each proposed move through the fail-closed guardrails chain. Auto-apply ONLY the
        # spend-decreasing moves (verdict.auto_apply); record every disposition to the decision_log.
        decided: list[dict] = []
        for mv in proposals:
            gstate = _guardrail_state_for(tenant_id, mv)
            try:
                verdict = guardrails.evaluate(gstate, mv)
            except Exception:  # noqa: BLE001 — fail-closed: skip a move we can't dispose
                continue
            # DRY-RUN: an auto-apply does NOT spend; it is recorded as the decision the tick would
            # enact. Non-decreasing moves are deferred_pending_approval (need draft -> approve).
            # The guardrails chain already enforces C5 — only spend-DECREASING moves get
            # verdict.auto_apply=True; everything else is deferred for approval. No spend here.
            row = guardrails.build_decision_row(tenant_id, mv, verdict, actor="optimize")
            try:
                store.append_decision(tenant_id, row)
            except Exception:  # noqa: BLE001
                pass
            decided.append({
                "plan_id": mv.get("plan_id"),
                "move": mv.get("move"),
                "reason": mv.get("reason"),
                "variant_id": mv.get("variant_id"),
                "channel": mv.get("channel"),
                "spend_delta_sign": mv.get("spend_delta_sign", 0),
                "outcome": verdict.outcome,
                "auto_apply": bool(verdict.auto_apply),
                "blocked_by": verdict.blocked_by,
                "guard_reason": verdict.reason,
            })

        applied_n = sum(1 for d in decided if d["auto_apply"])
        deferred_n = sum(1 for d in decided if d["outcome"] == "deferred_pending_approval")
        _audit(request, t, "ads.optimize", "campaign", str(campaign_id or ""),
               {"dry_run": dry, "proposed": len(decided),
                "auto_applied": applied_n, "deferred": deferred_n})
        return JSONResponse({"ok": True, "dry_run": dry, "moves": decided,
                             "proposed": len(decided), "auto_applied": applied_n,
                             "deferred": deferred_n})

    def _guardrail_state_for(tenant_id: str, move: dict) -> dict:
        """Assemble the GuardrailState the chain evaluates for one move: the persisted guardrail_state
        row (caps/tracking/learning lock/baselines) merged with the live campaign caps. Default-safe."""
        plan_id = str(move.get("plan_id") or "")
        gstate: dict = {}
        try:
            row = store.get_guardrail_state(tenant_id, plan_id) if plan_id else None
            if isinstance(row, dict):
                gstate = dict(row)
        except Exception:  # noqa: BLE001
            gstate = {}
        if plan_id:
            try:
                rec = store.get_row(tenant_id, "campaigns", plan_id) or {}
            except Exception:  # noqa: BLE001
                rec = {}
            gstate.setdefault("daily_cap_minor", int(rec.get("daily_cap_minor", 0) or 0))
            gstate.setdefault("lifetime_cap_minor", int(rec.get("lifetime_cap_minor", 0) or 0))
            gstate.setdefault("spend_today_minor", int(rec.get("spend_today_minor", 0) or 0))
            gstate.setdefault("spend_life_minor", int(rec.get("spend_life_minor", 0) or 0))
            gstate.setdefault("cpl_target_minor", int(rec.get("cpl_max_minor", 0) or 0))
        # Carry the move's own spend delta so the cap/funds gates can size the increase.
        if "spend_delta_minor" in move:
            gstate["spend_delta_minor"] = move["spend_delta_minor"]
        return gstate

    # =========================================================================
    # 7) GET /ads/guardrails  (token; read)  -> current guardrail state for this tenant
    #    The live spend-cap / tracking / learning-lock snapshot the optimizer disposes against.
    # =========================================================================
    def _guardrails_view(tenant_id: str) -> dict:
        """The flat guardrails policy = config defaults <- persisted tenant overrides (B7). Matches
        `_lib.ts:AdsGuardrails` so GET and the save echo render in the Guardrails tab without a remap.
        Live spend/CPL state is echoed for the meters (best-effort, default-safe)."""
        caps = {}
        try:
            caps = config.caps()
        except Exception:  # noqa: BLE001
            caps = {}
        try:
            overrides = store.get_guardrails_config(tenant_id) or {}
        except Exception:  # noqa: BLE001
            overrides = {}
        flat = {
            "daily_cap_minor": int(caps.get("daily_cap_minor", 0) or 0),
            "org_daily_cap_minor": int(caps.get("org_daily_cap_minor", 0) or 0),
            "per_account_cap_minor": 0,
            "cpl_max_minor": int(caps.get("cpl_max_minor", 0) or 0),
            "cpl_breaker_on": True,
            "anomaly_breaker_on": True,
            "require_approval": bool(config.require_approval()),
            "no_tracking_gate": True,
            "poll_minutes": int(caps.get("poll_minutes", 5) or 5),
            "currency": caps.get("currency", "INR"),
            "dry_run": bool(config.dry_run()),
        }
        # Apply persisted overrides over the defaults (only known guardrail keys).
        for k in ("daily_cap_minor", "org_daily_cap_minor", "per_account_cap_minor",
                  "cpl_max_minor", "cpl_breaker_on", "anomaly_breaker_on",
                  "require_approval", "no_tracking_gate", "poll_minutes", "currency"):
            if k in overrides and overrides[k] is not None:
                flat[k] = overrides[k]
        # Live state for the spend-vs-cap meters.
        try:
            st = analytics.status(tenant_id)
            flat["spend_today_minor"] = int(st.get("spend_today_minor", 0) or 0)
        except Exception:  # noqa: BLE001
            flat["spend_today_minor"] = 0
        flat["current_cpl_minor"] = None
        return flat

    @router.get("/guardrails")
    async def ads_guardrails(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tenant_id = _tid(t)
        plan_id = request.query_params.get("campaign_id") if hasattr(request, "query_params") else None
        try:
            if plan_id:
                row = store.get_guardrail_state(tenant_id, str(plan_id))
                states = [row] if row else []
            else:
                states = store.list_guardrail_states(tenant_id)
        except Exception:  # noqa: BLE001
            states = []
        # Flat `_lib.ts:AdsGuardrails` fields at the top level (FE reads these directly) PLUS the
        # legacy caps/guardrail_states block (kept for any existing consumer — additive).
        out = _guardrails_view(tenant_id)
        out.update({
            "ok": True,
            "caps": config.caps(),
            "guardrail_states": states,
            "count": len(states),
        })
        return JSONResponse(out)

    # =========================================================================
    # 7b) POST /ads/guardrails  (token + write + STEP-UP)  -> persist caps/breaker/approval (B7)
    #     Changing a spend cap / breaker / approval gate is a spend-class control change, so it is
    #     fail-closed step-up gated exactly like /campaigns/{id}/approve (M2 legacy-pw excluded +
    #     X-Step-Up verified). Persists ONLY the known guardrail keys into guardrails_config; never
    #     spends. Echoes the merged `_lib.ts:AdsGuardrails` back.
    # =========================================================================
    _GUARDRAIL_SAVE_KEYS = (
        "daily_cap_minor", "org_daily_cap_minor", "per_account_cap_minor", "cpl_max_minor",
        "cpl_breaker_on", "anomaly_breaker_on", "require_approval", "no_tracking_gate",
        "poll_minutes", "currency",
    )

    @router.post("/guardrails")
    async def ads_guardrails_save(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tenant_id = _tid(t)
        # SPEND-CLASS step-up (fail-closed when absent), same gate as approve/import.
        token = _step_up_token(request)
        if not _verify_spend_step_up(token, tenant_id):
            _audit(request, t, "ads.guardrails.save_blocked", "guardrails", "",
                   {"reason": "step_up_required"})
            return JSONResponse({"ok": False, "status": "blocked_not_approved",
                                 "reason": "saving guardrails requires a step-up (X-Step-Up)"},
                                status_code=200)
        body = await _body(request)
        try:
            existing = store.get_guardrails_config(tenant_id) or {}
        except Exception:  # noqa: BLE001
            existing = {}
        updates: dict = {}
        for k in _GUARDRAIL_SAVE_KEYS:
            if k in body and body[k] is not None:
                v = body[k]
                if k.endswith("_minor") or k == "poll_minutes":
                    try:
                        v = int(v)
                    except Exception:  # noqa: BLE001
                        continue
                    if v < 0:
                        continue
                elif k in ("cpl_breaker_on", "anomaly_breaker_on", "require_approval",
                           "no_tracking_gate"):
                    v = bool(v)
                updates[k] = v
        merged = {**existing, **updates}
        try:
            store.put_guardrails_config(tenant_id, merged)
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "guardrails_save_failed"}, status_code=200)
        _audit(request, t, "ads.guardrails.save", "guardrails", "",
               {"keys": sorted(updates.keys())})
        return JSONResponse({"ok": True, "guardrails": _guardrails_view(tenant_id)})

    # =========================================================================
    # 8) GET /ads/decisions  (token; read)  -> the immutable decision_log (explained actions feed)
    # =========================================================================
    @router.get("/decisions")
    async def ads_decisions(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tenant_id = _tid(t)
        qp = getattr(request, "query_params", {}) or {}
        try:
            limit = int(qp.get("limit", 50))
        except Exception:  # noqa: BLE001
            limit = 50
        campaign_id = qp.get("campaign_id") or None
        try:
            decisions = store.get_decisions(tenant_id, limit=limit, campaign_id=campaign_id)
        except Exception:  # noqa: BLE001
            decisions = []
        return JSONResponse({"ok": True, "decisions": decisions, "count": len(decisions)})

    # =========================================================================
    # 9) POST /ads/creative/generate  (token + write)  body {plan_id, brief, kinds?, sizes?}
    #    Submit a creative job (queued). The async stages (generate/compose/moderate) are advanced by
    #    the tick / CreativeService.advance — NOTHING is publishable until it passes the moderation
    #    gate (RERA/Housing/brand/broken-text). DRY: this is a job-row write, no spend.
    # =========================================================================
    @router.post("/creative/generate")
    async def ads_creative_generate(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        body = await _body(request)
        tenant_id = _tid(t)
        plan_id = str(body.get("plan_id") or "")
        if not plan_id:
            return forbidden("plan_id required")
        # M1: only the owner of the campaign may attach creatives to it.
        rec = _load_campaign(tenant_id, plan_id)
        owner_err = _require_object(t, rec)
        if owner_err:
            return owner_err
        brief = body.get("brief") if isinstance(body.get("brief"), dict) else {}
        kinds = body.get("kinds") if isinstance(body.get("kinds"), list) else None
        sizes = body.get("sizes") if isinstance(body.get("sizes"), list) else None
        try:
            job = _creative_service().submit(tenant_id, plan_id, dict(brief or {}),
                                             kinds=kinds, sizes=sizes)
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "status": "not_configured"}, status_code=200)
        _audit(request, t, "ads.creative.generate", "creative_job", job.get("job_id", ""),
               {"plan_id": plan_id})
        return JSONResponse({"ok": True, "job": job})

    # =========================================================================
    # 10) GET /ads/creative/list  (token; read)  ?plan_id=  -> jobs + variants for the plan
    # =========================================================================
    @router.get("/creative/list")
    async def ads_creative_list(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tenant_id = _tid(t)
        qp = getattr(request, "query_params", {}) or {}
        plan_id = qp.get("plan_id") or None
        svc = _creative_service()
        try:
            jobs = svc.list_jobs(tenant_id, plan_id=plan_id)
            variants = svc.get_variants(tenant_id, plan_id) if plan_id else []
        except Exception:  # noqa: BLE001
            jobs, variants = [], []
        return JSONResponse({"ok": True, "jobs": jobs, "variants": variants,
                             "count": len(jobs)})

    # =========================================================================
    # 11) POST /ads/creative/upload  (token + write)  body {plan_id, asset_id, brief?, kind?}
    #     Adopt a vendor's own gallery asset as an ad variant (REUSE the gallery). The SAME
    #     moderation gate runs (RERA/Housing still apply). DRY: a variant-row write, no spend.
    # =========================================================================
    @router.post("/creative/upload")
    async def ads_creative_upload(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        body = await _body(request)
        tenant_id = _tid(t)
        plan_id = str(body.get("plan_id") or "")
        asset_id = str(body.get("asset_id") or "")
        if not plan_id or not asset_id:
            return forbidden("plan_id and asset_id required")
        rec = _load_campaign(tenant_id, plan_id)
        owner_err = _require_object(t, rec)
        if owner_err:
            return owner_err
        brief = body.get("brief") if isinstance(body.get("brief"), dict) else {}
        kind = str(body.get("kind") or "uploaded_image")
        try:
            variant = _creative_service().import_upload(tenant_id, plan_id, asset_id,
                                                        kind=kind, brief=dict(brief or {}))
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "upload_failed"}, status_code=200)
        _audit(request, t, "ads.creative.upload", "ad_variant",
               str(variant.get("variant_id", "")), {"plan_id": plan_id, "asset_id": asset_id})
        return JSONResponse({"ok": variant.get("ok", True) is not False,
                             "variant": variant})

    # =========================================================================
    # 12) POST /ads/creative/moderate  (token + write)  body {variant_id}
    #     Re-run the publish moderation gate on one variant (after a copy edit / regenerate).
    # =========================================================================
    @router.post("/creative/moderate")
    async def ads_creative_moderate(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        body = await _body(request)
        tenant_id = _tid(t)
        variant_id = str(body.get("variant_id") or "")
        if not variant_id:
            return forbidden("variant_id required")
        # M1: a variant is tenant-scoped via the store; cross-tenant -> not_found.
        try:
            v = store.get_row(tenant_id, "ad_variants", variant_id)
        except Exception:  # noqa: BLE001
            v = None
        owner_err = _require_object(t, v)
        if owner_err:
            return owner_err
        try:
            result = _creative_service().moderate(tenant_id, variant_id)
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "moderate_failed"}, status_code=200)
        _audit(request, t, "ads.creative.moderate", "ad_variant", variant_id,
               {"status": result.get("status")})
        return JSONResponse(result)

    # =========================================================================
    # 12b) GET /ads/creative/jobs  (token; read)  -> {ok, jobs}
    #      Canonical job feed matching `_lib.ts:getCreativeJobs`. Tenant-wide (optional ?plan_id=).
    # =========================================================================
    @router.get("/creative/jobs")
    async def ads_creative_jobs(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tenant_id = _tid(t)
        qp = getattr(request, "query_params", {}) or {}
        plan_id = qp.get("plan_id") or None
        try:
            jobs = _creative_service().list_jobs(tenant_id, plan_id=plan_id)
        except Exception:  # noqa: BLE001
            jobs = []
        return JSONResponse({"ok": True, "jobs": jobs, "count": len(jobs)})

    # =========================================================================
    # 12c) GET /ads/creative/variants  (token; read)  -> {ok, variants}
    #      The moderation feed matching `_lib.ts:getCreativeVariants`. Tenant-wide; optional
    #      ?plan_id= and ?moderation_status= filters. Empty-but-valid for a fresh tenant.
    # =========================================================================
    @router.get("/creative/variants")
    async def ads_creative_variants(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tenant_id = _tid(t)
        qp = getattr(request, "query_params", {}) or {}
        plan_id = qp.get("plan_id") or None
        mod = qp.get("moderation_status") or None
        try:
            variants = _creative_service().list_variants(
                tenant_id, plan_id=plan_id, moderation_status=mod)
        except Exception:  # noqa: BLE001
            variants = []
        return JSONResponse({"ok": True, "variants": variants, "count": len(variants)})

    # =========================================================================
    # 12d) POST /ads/creative/variants/{variant_id}/moderate  (token + write)  body {decision}
    #      The moderation feed's approve/block. Canonical path matching `_lib.ts:moderateVariant`
    #      (the body-variant_id `/creative/moderate` re-run route above is kept as an alias). A
    #      human verdict (approved|blocked) is NOT spend-class, but it IS write-gated (no legacy-pw)
    #      and tenant-scoped (cross-tenant variant -> 404). X-Step-Up is accepted but not required.
    # =========================================================================
    @router.post("/creative/variants/{variant_id}/moderate")
    async def ads_creative_variant_moderate(variant_id: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tenant_id = _tid(t)
        vid = str(variant_id or "")
        if not vid:
            return forbidden("variant_id required")
        try:
            v = store.get_row(tenant_id, "ad_variants", vid)
        except Exception:  # noqa: BLE001
            v = None
        owner_err = _require_object(t, v)
        if owner_err:
            return owner_err
        body = await _body(request)
        decision = str(body.get("decision") or "").lower()
        if decision not in ("approved", "blocked"):
            return forbidden("decision must be 'approved' or 'blocked'")
        try:
            result = _creative_service().set_moderation(tenant_id, vid, decision, by="human")
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "moderate_failed"}, status_code=200)
        if not result.get("ok"):
            return JSONResponse(result, status_code=200)
        _audit(request, t, "ads.creative.variant_moderate", "ad_variant", vid,
               {"decision": decision})
        return JSONResponse({"ok": True, "variant_id": vid,
                             "moderation_status": result.get("moderation_status", decision)})

    # =========================================================================
    # 12e) GET /ads/analytics/{kind}  (token; read)  kind ∈ funnel|per-ad|per-platform|real-vs-reported
    #      The 4 store-only rollups (BLINDSPOTS B6). Unknown kind -> 404 (dormant-safe on the FE).
    #      Optional ?campaign_id= scopes the rollup to one plan. Empty-but-valid for fresh tenants.
    # =========================================================================
    @router.get("/analytics/{kind}")
    async def ads_analytics(kind: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tenant_id = _tid(t)
        qp = getattr(request, "query_params", {}) or {}
        campaign_id = str(qp.get("campaign_id") or qp.get("campaign") or "")
        try:
            out = analytics.rollup(tenant_id, str(kind or ""), campaign_id=campaign_id)
        except Exception:  # noqa: BLE001
            out = None
        if out is None:
            return JSONResponse({"error": "unknown_analytics_kind"}, status_code=404)
        return JSONResponse(out)

    # =========================================================================
    # ===============  W6 — LEADS · CONSENT · INBOUND WEBHOOK  =================
    # The ONLY unauth surface is the Meta leadgen webhook; it is FAIL-CLOSED on a strict
    # trust-ordering (redteam secrets-vault C3): page_id -> tenant via the ownership-checked
    # page_tenant_map -> load that tenant's app_secret via the vault -> HMAC-verify the RAW body
    # fail-closed -> ONLY THEN parse. Unknown page_id is REJECTED (no default/admin tenant). We
    # log the event TYPE only, never the body. Consent + form routes are token-authed.
    # =========================================================================

    # Re-assert the compliance fail-closed invariant at mount (a permissive default is unshippable).
    try:
        compliance.assert_fail_closed()
    except Exception:  # noqa: BLE001 — if this trips, the build still returns None-safe below
        import logging as _lg_c
        _lg_c.getLogger("ads_engine.endpoints").error("compliance fail-closed assertion TRIPPED")
        return None  # refuse to mount a permissive-default compliance gate.

    async def _raw_body(request) -> bytes:
        try:
            return await request.body()
        except Exception:  # noqa: BLE001
            return b""

    # ---- GET /ads/webhooks/meta/leadgen — Meta webhook verify (echo hub.challenge) ----
    @router.get("/webhooks/meta/leadgen")
    async def meta_leadgen_verify(request: "Request") -> Any:
        if not config.is_enabled():
            return _disabled()
        qp = getattr(request, "query_params", {}) or {}
        mode = qp.get("hub.mode") or qp.get("hub.mode".replace(".", "_")) or ""
        token = qp.get("hub.verify_token") or ""
        challenge = qp.get("hub.challenge") or ""
        page_id = qp.get("page_id") or ""
        # Resolve tenant from the page map; verify the token against THAT tenant's stored verify_token.
        tid = None
        try:
            tid = store.get_tenant_for_page(page_id) if page_id else None
        except Exception:  # noqa: BLE001
            tid = None
        if not tid:
            return JSONResponse({"error": "unknown_page"}, status_code=403)
        expected = ""
        try:
            pdid = vault_adapter._def_id_for(tid, "meta")
            blob = vault_adapter.get_secret_json(tid, pdid) if pdid else None
            expected = vault_adapter.get_field(blob, "webhook_verify_token") or ""
        except Exception:  # noqa: BLE001
            expected = ""
        if mode == "subscribe" and token and expected and token == expected:
            return Response(content=str(challenge), media_type="text/plain")
        return JSONResponse({"error": "verify_failed"}, status_code=403)

    # ---- POST /ads/webhooks/meta/leadgen — fail-closed trust-ordering, then ingest ----
    @router.post("/webhooks/meta/leadgen")
    async def meta_leadgen_event(request: "Request") -> Any:
        if not config.is_enabled():
            return _disabled()
        raw = await _raw_body(request)
        # 1) page_id from the (UNTRUSTED) parsed body is used ONLY to look up the tenant in the
        #    ownership-checked map — never to grant trust. We parse minimally just to read page_id.
        page_id = ""
        try:
            import json as _json
            preview = _json.loads(raw.decode("utf-8")) if raw else {}
            entries = preview.get("entry", []) if isinstance(preview, dict) else []
            for e in entries:
                page_id = str(e.get("id") or "")
                if page_id:
                    break
                for ch in (e.get("changes", []) or []):
                    page_id = str((ch.get("value") or {}).get("page_id") or "")
                    if page_id:
                        break
                if page_id:
                    break
        except Exception:  # noqa: BLE001 — malformed body => no page_id => reject below
            page_id = ""
        # 2) page_id -> tenant via the persisted, ownership-checked map. UNKNOWN => REJECT (no
        #    default/admin tenant). The body is still UNTRUSTED at this point.
        tid = None
        try:
            tid = store.get_tenant_for_page(page_id) if page_id else None
        except Exception:  # noqa: BLE001
            tid = None
        if not tid:
            # log TYPE only, never the body.
            import logging as _lg_w
            _lg_w.getLogger("ads_engine.endpoints").warning("leadgen webhook: unknown page_id (rejected)")
            return JSONResponse({"error": "unknown_page"}, status_code=403)
        # 3) load THAT tenant's app_secret via the vault, then HMAC-verify the RAW body fail-closed.
        app_secret = ""
        try:
            pdid = vault_adapter._def_id_for(tid, "meta")
            blob = vault_adapter.get_secret_json(tid, pdid) if pdid else None
            app_secret = vault_adapter.field_aliased(blob, "app_secret") or ""
        except Exception:  # noqa: BLE001
            app_secret = ""
        sig = ""
        try:
            sig = request.headers.get("x-hub-signature-256", "") or \
                request.headers.get("X-Hub-Signature-256", "")
        except Exception:  # noqa: BLE001
            sig = ""
        verified = False
        try:
            verified = _MetaConnector(creds=None).verify_webhook_signature(app_secret, raw, sig)
        except Exception:  # noqa: BLE001 — any verify error => fail closed
            verified = False
        if not verified:
            import logging as _lg_w2
            _lg_w2.getLogger("ads_engine.endpoints").warning("leadgen webhook: HMAC verify failed (rejected)")
            return JSONResponse({"error": "bad_signature"}, status_code=403)
        # 4) ONLY NOW parse the (now-trusted) body + ingest each lead under the resolved tenant.
        try:
            import json as _json2
            payload = _json2.loads(raw.decode("utf-8")) if raw else {}
            items = _MetaConnector.parse_leadgen(payload)
        except Exception:  # noqa: BLE001
            items = []
        ingested = 0
        # REDTEAM H2: bound the per-request item count (amplification DoS guard).
        for it in (items or [])[:_WEBHOOK_MAX_ITEMS]:
            try:
                # field_data retrieval (get_lead) is a connector call deferred to the tick backstop;
                # here we ingest the leadgen IDs as the lead skeleton -> gate -> dry-run enqueue.
                raw_lead = {"source_ref": it, "campaign_id": ""}
                _leads_mod.ingest(tid, _leads_mod.SOURCE_META, raw_lead, channel="voice")
                ingested += 1
            except Exception:  # noqa: BLE001 — one lead's failure never aborts the batch
                continue
        # Return 200 fast (Meta retries/disables on slow/err). Log type+count only.
        return JSONResponse({"ok": True, "ingested": ingested})

    # ---- POST /ads/leads/form — own-landing form intake (signed/scoped/revocable token) ----
    @router.post("/leads/form")
    async def leads_form_intake(request: "Request") -> Any:
        if not config.is_enabled():
            return _disabled()
        body = await _body(request)
        token = str(body.get("form_token") or "")
        if not token:
            return forbidden("form_token required")
        # Resolve + validate the signed/scoped/revocable/rate-limited token -> tenant_id.
        tok = _resolve_form_token(token)
        if not tok or not tok.get("ok"):
            return JSONResponse({"error": (tok or {}).get("reason", "invalid_token")},
                                status_code=403)
        tid = tok["tenant_id"]
        # Inline consent capture (DPDP + DCA). For VOICE the gate later rejects a checkbox-only DCA.
        name = str(body.get("name") or "")
        phone = str(body.get("phone") or "")
        raw_lead = {"name": name, "phone": phone, "email": body.get("email", ""),
                    "campaign_id": tok.get("campaign_id", ""), "source_ref": {"form_id": tok.get("form_id", "")}}
        # Record consent rows (DPDP always if checkbox true; DCA only if a DLT id is supplied —
        # a bare checkbox DCA will NOT pass the voice gate, by design).
        try:
            if body.get("consent_dpdp"):
                compliance.record_consent(
                    tid, lead_id="", phone=phone, kind=compliance.KIND_DPDP, who=f"{name}/{phone}",
                    source="landing_form", method=compliance.METHOD_FORM_CHECKBOX,
                    evidence={"form_id": tok.get("form_id", "")})
            if body.get("consent_dca"):
                dlt_id = str(body.get("dlt_consent_id") or "")
                method = compliance.METHOD_OTP_127_DLT if dlt_id else compliance.METHOD_FORM_CHECKBOX
                compliance.record_consent(
                    tid, lead_id="", phone=phone, kind=compliance.KIND_DCA, who=f"{name}/{phone}",
                    source="landing_form", method=method,
                    evidence={"form_id": tok.get("form_id", ""), "dlt_consent_id": dlt_id})
        except Exception:  # noqa: BLE001
            pass
        lead = _leads_mod.ingest(tid, _leads_mod.SOURCE_FORM, raw_lead, channel="voice")
        return JSONResponse({"ok": True, "lead_id": lead.get("lead_id", ""),
                             "status": lead.get("status", ""), "gate": lead.get("gate")})

    # ---- POST /ads/webhooks/ctwa — click-to-WhatsApp inbound (FAIL-CLOSED, HMAC-verified) ----
    @router.post("/webhooks/ctwa")
    async def ctwa_inbound(request: "Request") -> Any:
        if not config.is_enabled():
            return _disabled()
        raw = await _raw_body(request)
        # REDTEAM C1 (routes-auth): CTWA inbound MUST be cryptographically verified before ingest —
        # mirror the Meta leadgen trust-ordering EXACTLY. The wa_phone_id in the body is UNTRUSTED;
        # it is used ONLY to look up the tenant in the ownership-checked map. We then load THAT
        # tenant's WhatsApp app_secret from the vault and HMAC-verify the RAW body (X-Hub-Signature-256),
        # fail-closed. A wa_phone_id is public-ish, not a secret — without this an attacker could forge
        # leads (name/phone of their choosing) into any tenant's dial pipeline.
        # 1) wa_phone_id from the UNTRUSTED body (parse-minimally, used for lookup only).
        wa_phone_id = ""
        page_id = ""
        try:
            import json as _json3
            b = _json3.loads(raw.decode("utf-8")) if raw else {}
            wa_phone_id = str((b.get("wa_phone_id") or b.get("phone_number_id") or ""))
            page_id = wa_phone_id
        except Exception:  # noqa: BLE001
            page_id = ""
        # 2) wa_phone_id -> tenant via the persisted, ownership-checked map. UNKNOWN => REJECT.
        tid = None
        try:
            tid = store.get_tenant_for_page(page_id) if page_id else None
        except Exception:  # noqa: BLE001
            tid = None
        if not tid:
            import logging as _lg_cw
            _lg_cw.getLogger("ads_engine.endpoints").warning("ctwa webhook: unknown wa_phone_id (rejected)")
            return JSONResponse({"error": "unknown_wa_phone"}, status_code=403)
        # 3) load THAT tenant's WhatsApp app_secret via the vault, then HMAC-verify the RAW body
        #    fail-closed. WhatsApp Cloud API signs the body with the app secret as X-Hub-Signature-256.
        app_secret = ""
        try:
            pdid = vault_adapter._def_id_for(tid, "whatsapp")
            blob = vault_adapter.get_secret_json(tid, pdid) if pdid else None
            app_secret = vault_adapter.field_aliased(blob, "app_secret") or ""
        except Exception:  # noqa: BLE001
            app_secret = ""
        sig = ""
        try:
            sig = request.headers.get("x-hub-signature-256", "") or \
                request.headers.get("X-Hub-Signature-256", "")
        except Exception:  # noqa: BLE001
            sig = ""
        verified = False
        try:
            verified = _MetaConnector(creds=None).verify_webhook_signature(app_secret, raw, sig)
        except Exception:  # noqa: BLE001 — any verify error => fail closed
            verified = False
        if not verified:
            import logging as _lg_cw2
            _lg_cw2.getLogger("ads_engine.endpoints").warning("ctwa webhook: HMAC verify failed (rejected)")
            return JSONResponse({"error": "bad_signature"}, status_code=403)
        # 4) ONLY NOW parse the (now-trusted) body + ingest under the resolved tenant.
        try:
            import json as _json4
            b2 = _json4.loads(raw.decode("utf-8")) if raw else {}
        except Exception:  # noqa: BLE001
            b2 = {}
        raw_lead = {"name": b2.get("name", ""), "phone": b2.get("from", "") or b2.get("phone", ""),
                    "source_ref": {"ctwa_clid": b2.get("ctwa_clid", ""), "wa_phone_id": wa_phone_id}}
        lead = _leads_mod.ingest(tid, _leads_mod.SOURCE_CTWA, raw_lead, channel="voice")
        return JSONResponse({"ok": True, "lead_id": lead.get("lead_id", "")})

    # NOTE: the earlier POST /ads/leads/bulk route was REMOVED — it was a superseded duplicate that
    # defaulted consent_dpdp=True (forging a DPDP basis for any uploaded row), had no DPA-ack gate and
    # no step-up, and miscounted error/dry_run rows as "ingested". /ads/leads/import below is the one
    # consented import path: DPA-ack + step-up gated, delegating to the single leads.bulk_import gate.

    # ---- POST /ads/leads/import — Dead-Lead Revival consented bulk-import (step-up gated) ----
    #     The vendor uploads its OWN consented leads under a Data Processing Agreement (DPA). This is
    #     a spend-class action (it can fan out promo dials once 140-series is live), so it requires
    #     can(write) + NOT legacy-pw (M2) + a firewall step-up (X-Step-Up), exactly like approve. The
    #     WHOLE import is REJECTED when dpa_acknowledged is false (no DPA => no processing basis). Per
    #     lead: record consent in the hash-chained ledger + run the fail-closed pre_dial_gate + dry-run
    #     enqueue (source=ad/revival). REUSES leads.bulk_import — the gate/enqueue is NOT duplicated.
    @router.post("/leads/import")
    async def leads_import(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        body = await _body(request)
        # DPA acknowledgement FLAG — fail-closed: a false/absent flag REJECTS the whole import.
        dpa_ack = bool(body.get("dpa_acknowledged"))
        if not dpa_ack:
            _audit(request, t, "ads.leads.import_rejected", "lead", "",
                   {"reason": "dpa_not_acknowledged"})
            return JSONResponse({"ok": False, "status": "rejected",
                                 "reason": "dpa_acknowledged must be true to import consented leads",
                                 "ingested": 0, "blocked": 0}, status_code=200)
        # SPEND-CLASS step-up: a bulk dial-eligible import must ride a single-use X-Step-Up token
        # (fail-closed when absent, like /campaigns/{id}/approve). Stays DRY-RUN regardless.
        token = _step_up_token(request)
        step_up = _verify_spend_step_up(token, tid)
        if not step_up:
            _audit(request, t, "ads.leads.import_blocked", "lead", "",
                   {"reason": "step_up_required"})
            return JSONResponse({"ok": False, "status": "blocked_not_approved",
                                 "reason": "import requires a step-up (X-Step-Up)",
                                 "ingested": 0, "blocked": 0})
        rows = body.get("leads") if isinstance(body.get("leads"), list) else []
        # REDTEAM H3 (isolation): enforce the import cap at the ROUTE, not only the function default —
        # each row is a full read-modify-write of the tenant's growing JSON file (quadratic IO). Reject
        # an over-cap submission outright rather than churn the shared single-process store.
        if len(rows) > _IMPORT_MAX_ROWS:
            _audit(request, t, "ads.leads.import_blocked", "lead", "",
                   {"reason": "too_many_rows", "submitted": len(rows), "cap": _IMPORT_MAX_ROWS})
            return JSONResponse({"ok": False, "status": "rejected",
                                 "reason": f"at most {_IMPORT_MAX_ROWS} leads per import",
                                 "ingested": 0, "blocked": 0}, status_code=200)
        dpa_ref = str(body.get("dpa_ref") or "")
        # Delegate to the single import path (records consent + gate + dry-run enqueue). No dup logic.
        try:
            res = _leads_mod.bulk_import(tid, rows, dpa_ref=dpa_ref, channel="voice",
                                         dpa_acknowledged=dpa_ack)
        except Exception:  # noqa: BLE001 — never crash the route
            return JSONResponse({"ok": False, "status": "error", "ingested": 0, "blocked": 0},
                                status_code=200)
        _audit(request, t, "ads.leads.import", "lead", "",
               {"submitted": len(rows), "ingested": res.get("ingested"),
                "blocked": res.get("blocked"), "dpa_ref": dpa_ref})
        return JSONResponse({"ok": True, "status": "imported",
                             "ingested": res.get("ingested", 0),
                             "blocked": res.get("blocked", 0),
                             "leads": res.get("leads", [])})

    # ---- POST /ads/consent — capture a consent ledger row (DPDP/DCA), token-authed ----
    @router.post("/consent")
    async def consent_capture(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        body = await _body(request)
        kind = str(body.get("kind") or "")
        if kind not in (compliance.KIND_DPDP, compliance.KIND_DCA):
            return forbidden("kind must be dpdp_process or dca_commercial")
        phone = str(body.get("phone") or "")
        method = str(body.get("method") or compliance.METHOD_FORM_CHECKBOX)
        dlt_id = str(body.get("dlt_consent_id") or "")
        ev = {"form_id": body.get("form_id", ""), "ip": body.get("ip", ""),
              "ua": body.get("ua", ""), "dlt_consent_id": dlt_id}
        try:
            row = compliance.record_consent(
                tid, lead_id=str(body.get("lead_id") or ""), phone=phone, kind=kind,
                who=str(body.get("who") or phone), source=str(body.get("source") or "panel"),
                method=method, scope_text=str(body.get("scope_text") or ""), evidence=ev)
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "consent_write_failed"}, status_code=200)
        _audit(request, t, "ads.consent.capture", "consent", row.get("consent_id", ""),
               {"kind": kind, "method": method})
        # B8: echo lead_id + status so the shape matches `_lib.ts:ConsentMutationResponse`.
        return JSONResponse({"ok": True, "consent_id": row.get("consent_id", ""),
                             "lead_id": str(body.get("lead_id") or ""), "status": "granted"})

    # ---- POST /ads/consent/revoke — append a revocation (90d cool-off) ----
    @router.post("/consent/revoke")
    async def consent_revoke(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        body = await _body(request)
        # B8: the panel revokes by lead_id (LeadsTab has no raw phone). Accept EITHER lead_id or a
        # raw phone; resolve a lead_id -> its stored E.164 phone (own-tenant rows only). The phone
        # never leaves the backend — only the masked tail is audited.
        phone = str(body.get("phone") or "")
        lead_id = str(body.get("lead_id") or "")
        if not phone and lead_id:
            try:
                rows = store.get_tenant_file(tid, "leads_ads")
            except Exception:  # noqa: BLE001
                rows = []
            lead = next((r for r in rows if r.get("lead_id") == lead_id), None)
            owner_err = _require_object(t, lead)  # own-or-404
            if owner_err:
                return owner_err
            phone = str((lead or {}).get("phone") or "")
        if not phone:
            return forbidden("phone or lead_id required")
        kind = body.get("kind") or None
        try:
            res = compliance.revoke_consent(tid, phone=phone, kind=kind)
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "revoke_failed"}, status_code=200)
        _audit(request, t, "ads.consent.revoke", "consent", "",
               {"phone_tail": phone[-4:], "lead_id": lead_id, "revoked": res.get("revoked")})
        return JSONResponse({"ok": True, "lead_id": lead_id, "status": "revoked", **res})

    # ---- GET /ads/consent — view this tenant's consent ledger + chain-verify status ----
    @router.get("/consent")
    async def consent_view(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tid = _tid(t)
        try:
            rows = store.consent_log_rows(tid)
            verify = compliance.verify_chain(tid)
        except Exception:  # noqa: BLE001
            rows, verify = [], {"ok": False, "reason": "read_failed"}
        # Mask the phone in the view (show last 4 only); the chain hashes are non-secret.
        masked = []
        for r in rows[-500:]:
            rr = dict(r)
            ph = str(rr.get("phone") or "")
            rr["phone"] = ("•••" + ph[-4:]) if len(ph) >= 4 else ""
            masked.append(rr)
        return JSONResponse({"ok": True, "rows": masked, "count": len(rows), "chain": verify})

    # ---- GET /ads/consent/{lead_id} — this lead's consent entries (B8) ----
    #      Matches `_lib.ts:getAdsConsent(leadId)` -> {ok, lead_id, entries}. Filters the tenant's
    #      hash-chained ledger to rows for this lead (by lead_id OR the lead's phone), phone masked.
    @router.get("/consent/{lead_id}")
    async def consent_for_lead_view(lead_id: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tid = _tid(t)
        lid = str(lead_id or "")
        # Resolve the lead's phone (own-tenant) so phone-keyed consent rows are also matched.
        phone = ""
        try:
            rows = store.get_tenant_file(tid, "leads_ads")
            lead = next((r for r in rows if r.get("lead_id") == lid), None)
            phone = str((lead or {}).get("phone") or "")
        except Exception:  # noqa: BLE001
            phone = ""
        try:
            out = analytics.consent_for_lead(tid, lid, phone=phone)
        except Exception:  # noqa: BLE001
            out = {"ok": True, "lead_id": lid, "entries": []}
        return JSONResponse(out)

    # ---- POST /ads/leads/{lead_id}/redial — manual re-trigger (re-runs the FULL gate) ----
    @router.post("/leads/{lead_id}/redial")
    async def leads_redial(lead_id: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        try:
            rows = store.get_tenant_file(tid, "leads_ads")
        except Exception:  # noqa: BLE001
            rows = []
        lead = next((r for r in rows if r.get("lead_id") == lead_id), None)
        owner_err = _require_object(t, lead)  # M1 — own-or-404
        if owner_err:
            return owner_err
        # Re-run the FULL pre-gate (consent may have changed; NCPR status changes daily).
        decision = compliance.pre_dial_gate(tid, lead, channel="voice")
        if not decision.allow:
            _audit(request, t, "ads.leads.redial_blocked", "lead", lead_id, {"reason": decision.reason})
            return JSONResponse({"ok": False, "blocked": True, "reason": decision.reason,
                                 "gate": decision.to_dict()})
        fw = compliance.compute_force_window(decision)
        enq = _leads_mod.enqueue_call(tid, lead, force_window=fw)
        _audit(request, t, "ads.leads.redial", "lead", lead_id, {"status": enq.get("status")})
        return JSONResponse({"ok": True, **enq})

    # ---- GET /ads/leads — list this tenant's ad-leads, normalized to `_lib.ts:AdsLead` (B8) ----
    #      newest-first; phone masked; id/consent_status/gate_decision/score/call_outcome filled.
    @router.get("/leads")
    async def ads_leads_list(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tid = _tid(t)
        try:
            out = analytics.list_leads(tid, limit=1000)
        except Exception:  # noqa: BLE001
            out = {"ok": True, "leads": [], "count": 0, "next_cursor": None}
        return JSONResponse(out)

    # ---- GET /ads/leads/{lead_id} — one ad-lead, normalized to `_lib.ts:AdsLead` (B8) ----
    @router.get("/leads/{lead_id}")
    async def ads_lead_get(lead_id: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tid = _tid(t)
        lid = str(lead_id or "")
        try:
            row = analytics.get_lead(tid, lid)
        except Exception:  # noqa: BLE001
            row = None
        owner_err = _require_object(t, row)  # own-or-404 (also handles None -> 404)
        if owner_err:
            return owner_err
        return JSONResponse(analytics.lead_view(row))

    # ---- form-token mint + resolve (signed/scoped/revocable/rate-limited) ----
    # REDTEAM C1 (isolation) / H3 (routes-auth): the form-token signing key MUST be an explicit,
    # per-deploy secret of >=32 bytes. The previous code degraded to the in-source literal
    # "ads_form_dev" when unset — a public key that lets anyone forge a token for ANY tenant_id
    # (the tenant_id is attacker-chosen and self-authenticated by the HMAC) and POST forged leads +
    # forged DPDP/DCA consent rows. We now FAIL-CLOSED: no real secret => no mint, no resolve.
    _FORM_TOKEN_MIN_LEN = 32

    def _form_token_secret() -> "bytes | None":
        # Return the signing key bytes ONLY when a real >=32-byte secret is configured; else None
        # (fail-closed). NEVER an in-source constant. Mirrors the firewall `_ready=bool(_SECRET)`
        # posture: a misconfigured droplet refuses to mint/resolve rather than ship a public key.
        sec = config.cfg("ADS_FORM_TOKEN_SECRET", "") or config.cfg("SECRET_KEY", "") or ""
        sec = str(sec or "")
        if len(sec) < _FORM_TOKEN_MIN_LEN:
            return None
        return sec.encode("utf-8")

    def _resolve_form_token(token: str) -> dict:
        """Validate a signed+scoped+revocable+rate-limited form token -> {ok, tenant_id, form_id,...}.

        The token is `<tenant_id>.<form_id>.<exp>.<hmac>`; we recompute the HMAC (constant-time),
        check expiry, and confirm the token row is not revoked in form_tokens. Fail-closed."""
        import hashlib as _h
        import hmac as _hm
        secret = _form_token_secret()
        if secret is None:
            # No real signing key configured => fail-closed (never validate against a public/dev key).
            return {"ok": False, "reason": "form_tokens_not_configured"}
        try:
            parts = str(token).split(".")
            if len(parts) != 4:
                return {"ok": False, "reason": "malformed"}
            tid, form_id, exp_s, mac = parts
            body = f"{tid}.{form_id}.{exp_s}".encode("utf-8")
            expected = _hm.new(secret, body, _h.sha256).hexdigest()
            if not _hm.compare_digest(expected, mac):
                return {"ok": False, "reason": "bad_signature"}
            if int(exp_s) < int(time.time()):
                return {"ok": False, "reason": "expired"}
            # REDTEAM H1 (isolation): require an EXISTING, non-revoked form_tokens row — do NOT treat
            # an absent row as "active by default". This means a token can only validate for a
            # (tenant, form_id) the tenant itself minted (mint_form_token writes the row), so a forged
            # token targeting a tenant that never minted any form is rejected even if the key leaks.
            try:
                row = store.get_row(tid, "form_tokens", form_id)
            except Exception:  # noqa: BLE001
                row = None
            if not isinstance(row, dict):
                return {"ok": False, "reason": "unknown_form"}
            if row.get("revoked"):
                return {"ok": False, "reason": "revoked"}
            return {"ok": True, "tenant_id": tid, "form_id": form_id,
                    "campaign_id": row.get("campaign_id", "")}
        except Exception:  # noqa: BLE001
            return {"ok": False, "reason": "invalid"}

    @router.post("/leads/form-token")
    async def mint_form_token(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        body = await _body(request)
        import hashlib as _h2
        import hmac as _hm2
        secret = _form_token_secret()
        if secret is None:
            # REDTEAM C1: refuse to mint against a missing/weak key (never the in-source dev key).
            _audit(request, t, "ads.form_token.mint_rejected", "form_token", "",
                   {"reason": "form_token_secret_not_configured"})
            return JSONResponse({"ok": False, "error": "form_tokens_not_configured",
                                 "reason": "ADS_FORM_TOKEN_SECRET (>=32 bytes) must be configured"},
                                status_code=503)
        form_id = str(body.get("form_id") or uuid.uuid4().hex[:10])
        ttl = max(60, min(int(body.get("ttl_seconds", 30 * 24 * 3600) or 0), 365 * 24 * 3600))
        exp = int(time.time()) + ttl
        sig_body = f"{tid}.{form_id}.{exp}".encode("utf-8")
        mac = _hm2.new(secret, sig_body, _h2.sha256).hexdigest()
        token = f"{tid}.{form_id}.{exp}.{mac}"
        try:
            store.put_row(tid, "form_tokens", form_id, {
                "form_id": form_id, "campaign_id": str(body.get("campaign_id") or ""),
                "revoked": False, "created_ts": time.time(), "exp": exp})
        except Exception:  # noqa: BLE001
            pass
        _audit(request, t, "ads.form_token.mint", "form_token", form_id, {"ttl": ttl})
        return JSONResponse({"ok": True, "form_token": token, "form_id": form_id, "exp": exp})

    # =========================================================================
    # BLINDSPOTS B13/B14 — AD-BUDGET FUNDING (Razorpay-first, India-appropriate).
    #
    # The vendor funds THEIR OWN ad budget through a gateway key they store in the vault (capability
    # payment_gateway). Funding ADDS the vendor's money to their own paise balance — it never spends
    # our money and never mutates a campaign — so the money-in routes are write-gated (can(write) +
    # not legacy-pw) like /payments, NOT step-up-gated (that gate is reserved for spend: approve).
    # Dormant-until-creds: with no gateway key every route returns a calm not_configured shape.
    # =========================================================================
    @router.get("/budget/health")
    async def ads_budget_health(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        return JSONResponse(budget.budget_health(_tid(t)))

    @router.get("/budget/balance")
    async def ads_budget_balance(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        return JSONResponse(budget.get_balance(_tid(t)))

    @router.get("/budget/intents")
    async def ads_budget_intents(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        try:
            limit = int(request.query_params.get("limit", "50"))
        except Exception:  # noqa: BLE001
            limit = 50
        return JSONResponse({"ok": True, "intents": budget.list_intents(_tid(t), limit)})

    @router.get("/budget/ledger")
    async def ads_budget_ledger(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        try:
            limit = int(request.query_params.get("limit", "50"))
        except Exception:  # noqa: BLE001
            limit = 50
        return JSONResponse({"ok": True, "ledger": budget.ledger(_tid(t), limit)})

    @router.post("/budget/fund")
    async def ads_budget_fund(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        body = await _body(request)
        try:
            amount_minor = int(body.get("amount_minor", 0) or 0)
        except Exception:  # noqa: BLE001
            amount_minor = 0
        try:
            result = budget.create_funding_intent(
                tid, amount_minor,
                currency=str(body.get("currency", "") or ""),
                idem_key=str(body.get("idem_key", "") or ""),
                description=str(body.get("description", "") or ""))
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "status": "not_configured"}, status_code=200)
        _audit(request, t, "ads.budget.fund", "budget", result.get("intent_id", ""),
               {"amount_minor": amount_minor, "status": result.get("status")})
        return JSONResponse(result)

    @router.post("/budget/confirm")
    async def ads_budget_confirm(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        body = await _body(request)
        intent_id = str(body.get("intent_id", "") or "")
        try:
            result = budget.confirm_funding(
                tid, intent_id,
                payment_id=str(body.get("payment_id", "") or ""),
                signature=str(body.get("signature", "") or ""))
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "status": "verification_failed"}, status_code=200)
        _audit(request, t, "ads.budget.confirm", "budget", intent_id,
               {"status": result.get("status"), "credited_minor": result.get("credited_minor")})
        return JSONResponse(result)

    # =========================================================================
    # CONNECTIONS — paste-key -> connected loop (BLINDSPOTS B2/B15).
    #   GET  /ads/connections/status  -> { meta|google|whatsapp: configured|not_configured }
    #   POST /ads/connections/test    -> { ok, channel, reason, missing[], present[] }  (secret-free)
    # The vendor creates a Meta/Google/WhatsApp provider def + pastes the key blob via the existing
    # provider-registry routes; these two read-backs prove the ad engine can actually resolve + read
    # that key (status flips configured, test confirms the required fields are present). No secret
    # value ever leaves the vault — status is channel->state, test is field NAMES only.
    # =========================================================================
    @router.get("/connections/status")
    async def ads_connections_status(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        try:
            statuses = vault_adapter.list_status(_tid(t))
        except Exception:  # noqa: BLE001 — degrade to all not_configured (never 500 the spine)
            statuses = {"meta": "not_configured", "google": "not_configured",
                        "whatsapp": "not_configured"}
        return JSONResponse({"ok": True, "providers": statuses})

    @router.post("/connections/test")
    async def ads_connections_test(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        body = await _body(request)
        channel = str(body.get("channel", "") or "").strip().lower()
        if channel not in ("meta", "google", "whatsapp"):
            return JSONResponse({"ok": False, "reason": "bad_channel",
                                 "missing": [], "present": []}, status_code=200)
        try:
            result = vault_adapter.test_connection(_tid(t), channel)
        except Exception:  # noqa: BLE001 — degrade-never-raise
            result = {"ok": False, "channel": channel, "reason": "error",
                      "missing": [], "present": []}
        _audit(request, t, "ads.connections.test", "connection", channel,
               {"reason": result.get("reason"), "ok": result.get("ok")})
        return JSONResponse(result)

    # ---- AUTONOMY + STANDALONE-CREATIVE sub-router (BLINDSPOTS B9/B10/B6) ----
    # Mounted as a SEPARATE module so this file stays minimally edited; it reuses the closures above
    # (auth/RBAC/audit) via a small deps bag. Crash-proof: a sub-router failure never breaks the mount.
    try:
        from types import SimpleNamespace as _NS
        from . import routes_autorun as _routes_autorun
        _routes_autorun.register(router, _NS(
            json=JSONResponse, auth=_auth, write_gate=_write_gate, tid=_tid,
            body=_body, audit=_audit, forbidden=forbidden))
    except Exception:  # noqa: BLE001 — autonomy routes are additive; never crash the mount.
        pass

    # ---- V2-W4: reasoning-model gateway + LLM features + creative-AI sub-router ----
    # Same minimal-edit pattern: one register() call, reusing the closures above + the creative
    # factory. PROPOSAL-ONLY routes (copy/brief) and moderation-gated creative routes; crash-proof.
    try:
        from types import SimpleNamespace as _NS2
        from . import routes_llm as _routes_llm
        _routes_llm.register(router, _NS2(
            json=JSONResponse, auth=_auth, write_gate=_write_gate, tid=_tid,
            body=_body, audit=_audit, forbidden=forbidden,
            creative_service=_creative_service))
    except Exception:  # noqa: BLE001 — LLM/creative-AI routes are additive; never crash the mount.
        pass

    # ---- V2-W3 CONTINUOUS-LOOP sub-router (events ingest, learning/fatigue/audience, optimize kick) ----
    # Same additive pattern: one register() call reusing the closures above. Propose-only + dry-run +
    # guardrail-gated; adds NO spend authority. Crash-proof: a failure never breaks the mount.
    try:
        from types import SimpleNamespace as _NS3
        from . import routes_optimize as _routes_optimize
        _routes_optimize.register(router, _NS3(
            json=JSONResponse, auth=_auth, write_gate=_write_gate, tid=_tid,
            body=_body, audit=_audit, forbidden=forbidden))
    except Exception:  # noqa: BLE001 — continuous-loop routes are additive; never crash the mount.
        pass

    return router
