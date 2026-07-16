"""grow.endpoints — the token-deriving AUTHENTICATED HTTP surface (prefix /grow).

Mounted by caller.py via `build_router(resolve_tenant, can, need_auth, forbidden, ...)`
behind FEATURE_GROW (default OFF => byte-identical resting). tenant_id is ALWAYS
resolve_tenant(request)["tenant_id"] — NEVER read from the body/query (no cross-tenant
hole, the house rule). FastAPI is imported lazily inside build_router so a missing FastAPI
degrades the factory to None and can never crash startup.

Routes (all tenant-scoped, read-mostly):
  GET  /grow/health           — module + signal-mode status (no secrets)
  GET  /grow/leads            — scored leads (?tier= ?min_score= ?sales_ready=1)
  GET  /grow/leads/{lead_id}  — one scored lead
  POST /grow/score            — score a lead WITHOUT persist/dispatch (the "try-it" tool)
  GET  /grow/journeys         — journey spine
  GET  /grow/signals/log      — CAPI dispatch ledger (?journey_id=)
  GET  /grow/signals/health   — Signal Health card (EMQ/dedup/ladder/click-id coverage)

NOTE: this module deliberately does NOT use `from __future__ import annotations`. FastAPI
resolves handler annotations (`request: Request`) at mount time; with PEP-563 string
annotations + the lazy in-function `Request` import, FastAPI cannot resolve "Request" from
module globals and mis-reads `request` as a query param (422). Keeping real annotations fixes it.
"""
import logging

from .config import GrowConfig
from .loop import get_loop
from .model import ScoringInput

log = logging.getLogger("grow.endpoints")


def build_router(resolve_tenant, can, need_auth, forbidden, *,
                 require_super_admin=None, firewall=None, audit=None):
    """Return a FastAPI APIRouter, or None if FastAPI is unavailable (dormant-safe)."""
    try:
        from fastapi import APIRouter, Request  # noqa: PLC0415
        from fastapi.responses import JSONResponse  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        log.info("grow.endpoints: FastAPI unavailable — router not built")
        return None

    router = APIRouter(tags=["grow"])

    def _tid(request):
        """Token-derived tenant or None. Handlers fall back to need_auth() on None."""
        try:
            t = resolve_tenant(request)
        except Exception:  # noqa: BLE001
            return None
        if not t or not (t.get("tenant_id") or "").strip():
            return None
        return t

    # ----------------------------------------------------------------- health #
    @router.get("/grow/health")
    async def grow_health(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        loop = get_loop()
        st = loop.cfg.status()
        st["signal_health"] = loop.signal_health(t["tenant_id"])
        return JSONResponse(st)

    # ----------------------------------------------------------------- leads #
    @router.get("/grow/leads")
    async def grow_leads(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        q = request.query_params
        tier = (q.get("tier") or "").strip().lower()
        try:
            min_score = int(q.get("min_score") or 0)
        except (TypeError, ValueError):
            min_score = 0
        sales_only = (q.get("sales_ready") or "").strip().lower() in ("1", "true", "yes")
        rows = get_loop().scores.list(t["tenant_id"], tier=tier, min_score=min_score,
                                      sales_ready_only=sales_only)
        return JSONResponse({"leads": [r.public() for r in rows], "count": len(rows)})

    @router.get("/grow/leads/{lead_id}")
    async def grow_lead(lead_id: str, request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        r = get_loop().scores.get(t["tenant_id"], lead_id)
        if r is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(r.public())

    # ----------------------------------------------------------------- score #
    @router.post("/grow/score")
    async def grow_score(request: Request):
        """Score a hypothetical/real lead WITHOUT persisting or dispatching — the
        operator 'try-it' console. tenant_id is token-derived; body carries the signals."""
        t = _tid(request)
        if not t:
            return need_auth()
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not isinstance(body, dict):
            body = {}
        inp = ScoringInput(
            tenant_id=t["tenant_id"],
            lead_id=str(body.get("lead_id") or "preview"),
            phone=str(body.get("phone") or ""),
            name=str(body.get("name") or ""),
            source_platform=str(body.get("source_platform") or ""),
            phone_valid=bool(body.get("phone_valid", True)),
            disposable_email=bool(body.get("disposable_email", False)),
            call_answered=bool(body.get("call_answered", False)),
            call_duration_s=int(body.get("call_duration_s") or 0),
            interest_score=int(body.get("interest_score") or 0),
            budget_mentioned=bool(body.get("budget_mentioned", False)),
            timeline_mentioned=bool(body.get("timeline_mentioned", False)),
            decision_authority=bool(body.get("decision_authority", False)),
            site_visit_ready=bool(body.get("site_visit_ready", False)),
            booking_made=bool(body.get("booking_made", False)),
            investor_intent=bool(body.get("investor_intent", False)),
            end_user_intent=bool(body.get("end_user_intent", False)),
            last_outcome=str(body.get("last_outcome") or ""),
            wa_replied=bool(body.get("wa_replied", False)),
            wa_depth=int(body.get("wa_depth") or 0))
        scored = get_loop().score_only(inp)
        return JSONResponse(scored.public())

    # ----------------------------------------------------------------- journeys #
    @router.get("/grow/journeys")
    async def grow_journeys(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        rows = get_loop().journeys.list(t["tenant_id"])
        return JSONResponse({"journeys": [r.public() for r in rows], "count": len(rows)})

    # ----------------------------------------------------------------- signals #
    @router.get("/grow/signals/log")
    async def grow_signals_log(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        jid = (request.query_params.get("journey_id") or "").strip()
        rows = get_loop().signals_store.list(t["tenant_id"], journey_id=jid)
        return JSONResponse({"signals": [r.public() for r in rows], "count": len(rows)})

    @router.get("/grow/signals/health")
    async def grow_signals_health(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        return JSONResponse(get_loop().signal_health(t["tenant_id"]))

    # ----------------------------------------------------------- L3 orchestration #
    @router.post("/grow/ingest")
    async def grow_ingest(request: Request):
        """Speed-to-lead trigger: a consent-clean captured lead -> compliance gate -> fire
        WhatsApp + AI call <60s, journey-threaded. tenant_id is token-derived; the body
        carries the lead + attribution. (The real L1 webhook calls grow.on_lead_captured
        directly; this authenticated route powers manual/replay + the panel.)"""
        t = _tid(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("write permission required")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not isinstance(body, dict):
            body = {}
        lead_id = str(body.get("lead_id") or body.get("phone") or "").strip()
        if not lead_id:
            return JSONResponse({"error": "lead_id_or_phone_required"}, status_code=400)
        out = get_loop().on_lead_captured(
            t["tenant_id"], lead_id,
            phone=str(body.get("phone") or ""), name=str(body.get("name") or ""),
            email=str(body.get("email") or ""),
            source_platform=str(body.get("source_platform") or ""),
            source_ad_id=str(body.get("source_ad_id") or ""),
            ctwa_clid=str(body.get("ctwa_clid") or ""), fbclid=str(body.get("fbclid") or ""),
            gclid=str(body.get("gclid") or ""), campaign_id=str(body.get("campaign_id") or ""),
            consent_basis=str(body.get("consent_basis") or "explicit"),
            consent_channel=str(body.get("consent_channel") or "web_form"))
        return JSONResponse(out, status_code=200 if out.get("ok") else 400)

    @router.get("/grow/orchestrations")
    async def grow_orchestrations(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        rows = get_loop().orchestrations.list(t["tenant_id"])
        return JSONResponse({"orchestrations": [o.public() for o in rows], "count": len(rows)})

    # ----------------------------------------------------- L1 acquisition (W3) #
    # Authenticated replay/test surface (tenant token-derived). The live unauthenticated
    # leadgen webhook (GET verify + POST signature) is a thin founder-gated wrapper over
    # grow.acquisition.verify_meta_* + AcquisitionService.ingest_meta_webhook (needs Meta
    # app review + a page->tenant map + GROW_META_APP_SECRET).
    async def _acquire(request, provider: str):
        t = _tid(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("write permission required")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not isinstance(body, dict):
            body = {}
        acq = get_loop().acquisition
        tid = t["tenant_id"]
        if provider == "meta":
            out = acq.ingest_meta_value(body, tid)
        elif provider == "google":
            out = acq.ingest_google(body, tid)
        else:  # ctwa
            out = acq.ingest_ctwa(body, tid)
        return JSONResponse(out, status_code=200 if out.get("ok") else 400)

    @router.post("/grow/acquire/meta")
    async def grow_acquire_meta(request: Request):
        return await _acquire(request, "meta")

    @router.post("/grow/acquire/google")
    async def grow_acquire_google(request: Request):
        return await _acquire(request, "google")

    @router.post("/grow/acquire/ctwa")
    async def grow_acquire_ctwa(request: Request):
        return await _acquire(request, "ctwa")

    # ------------------------------------------------------ L8 funnel / ROI (W4) #
    def _spend(request) -> int:
        try:
            return max(0, int(request.query_params.get("spend_minor") or 0))
        except (TypeError, ValueError):
            return 0

    @router.get("/grow/funnel")
    async def grow_funnel(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        m = get_loop().metrics
        tid = t["tenant_id"]
        return JSONResponse({"funnel": m.funnel(tid), "tier_distribution": m.tier_distribution(tid),
                             "by_source": m.by_source(tid), "sla": m.sla(tid)})

    @router.get("/grow/roi")
    async def grow_roi(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        return JSONResponse(get_loop().metrics.roi(t["tenant_id"], spend_minor=_spend(request)))

    @router.get("/grow/summary")
    async def grow_summary(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        return JSONResponse(get_loop().metrics.summary(t["tenant_id"], spend_minor=_spend(request)))

    # ----------------------------------------------------- L7 ad-optimization (W5) #
    @router.get("/grow/ads/health")
    async def grow_ads_health(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        return JSONResponse({
            "optimizer": "draft_trash_promote_v1 (Gamma-Poisson + guardrails G1-G6)",
            "budget_governor": "caps + anomaly sentinel + kill-switch",
            "mode": "dry_run", "connector": "not_configured",
            "note": "Decisions are advisory until a Meta/Google Ads connector + OAuth are wired "
                    "(founder-gated). The brain runs live; only the execute step is gated.",
        })

    @router.post("/grow/ads/optimize")
    async def grow_ads_optimize(request: Request):
        """Dry-run the Draft/Trash/Promote brain over a set of arms. No live spend — returns
        the decisions (each with a plain-language Explanation) + the budget allocation."""
        t = _tid(request)
        if not t:
            return need_auth()
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not isinstance(body, dict):
            body = {}
        try:
            target = int(body.get("target_cpql_minor") or 0)
            daily_share = int(body.get("daily_share_minor") or 0)
        except (TypeError, ValueError):
            target, daily_share = 0, 0
        from .optimizer import Arm  # noqa: PLC0415
        arms = []
        for a in (body.get("arms") or []):
            if not isinstance(a, dict):
                continue
            arms.append(Arm(
                id=str(a.get("id") or ""), name=str(a.get("name") or ""),
                spend_minor=int(a.get("spend_minor") or 0),
                qualified_leads=int(a.get("qualified_leads") or 0),
                leads=int(a.get("leads") or 0), junk_leads=int(a.get("junk_leads") or 0),
                impressions=int(a.get("impressions") or 0), clicks=int(a.get("clicks") or 0),
                days_running=int(a.get("days_running") or 0),
                frequency_7d=float(a.get("frequency_7d") or 0.0),
                ctr_now=float(a.get("ctr_now") or 0.0),
                ctr_peak_7d=float(a.get("ctr_peak_7d") or 0.0),
                ctr_declining_days=int(a.get("ctr_declining_days") or 0),
                delivery_error=bool(a.get("delivery_error", False))))
        opt = get_loop().optimizer
        decisions = [opt.evaluate(a, target, daily_share_minor=daily_share).public() for a in arms]
        allocation = opt.allocate(arms, target)
        return JSONResponse({"mode": "dry_run", "decisions": decisions,
                             "allocation": allocation, "count": len(decisions)})

    # ------------------------------------------ Realtime All-Ads-Platform (W7/W8) #
    def _period(request) -> str:
        p = (request.query_params.get("period") or "30d").strip()
        return p if p in ("7d", "30d", "90d", "today") else "30d"

    def _demo(request):
        v = (request.query_params.get("demo") or "").strip().lower()
        return True if v in ("1", "true", "yes") else (False if v in ("0", "false", "no") else None)

    @router.get("/grow/platforms")
    async def grow_platforms(request: Request):
        """The Famit Growth snapshot: every ad platform normalized + cross-platform insights."""
        t = _tid(request)
        if not t:
            return need_auth()
        from . import platforms as _pf  # noqa: PLC0415
        return JSONResponse(_pf.snapshot(t["tenant_id"], period=_period(request), demo=_demo(request)))

    @router.get("/grow/platforms/config")
    async def grow_platforms_config(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        from . import platforms as _pf  # noqa: PLC0415
        return JSONResponse({"platforms": _pf.configured_platforms()})

    @router.get("/grow/platforms/{platform}")
    async def grow_platform_one(platform: str, request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        from . import platforms as _pf  # noqa: PLC0415
        m = _pf.fetch_platform(t["tenant_id"], platform, period=_period(request), demo=_demo(request))
        return JSONResponse(m.public())

    @router.post("/grow/advisor/recommend")
    async def grow_advisor_recommend(request: Request):
        t = _tid(request)
        if not t:
            return need_auth()
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        goal = str((body or {}).get("goal") or "min_cost") if isinstance(body, dict) else "min_cost"
        from . import platforms as _pf, advisor as _adv  # noqa: PLC0415
        snap = _pf.snapshot(t["tenant_id"], period=_period(request), demo=_demo(request))
        return JSONResponse(_adv.recommend(snap, goal=goal))

    @router.post("/grow/advisor/chat")
    async def grow_advisor_chat(request: Request):
        """Chat over the live ads data (deterministic; LLM-narrative is an optional seam)."""
        t = _tid(request)
        if not t:
            return need_auth()
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        question = str((body or {}).get("question") or "") if isinstance(body, dict) else ""
        from . import platforms as _pf, advisor as _adv  # noqa: PLC0415
        snap = _pf.snapshot(t["tenant_id"], period=_period(request), demo=_demo(request))
        out = _adv.chat(snap, question)
        return JSONResponse(out)

    @router.post("/grow/ads/budget/check")
    async def grow_ads_budget_check(request: Request):
        """Budget Governor admission check + anomaly sentinel (pure; no live mutation)."""
        t = _tid(request)
        if not t:
            return need_auth()
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not isinstance(body, dict):
            body = {}
        from .budget import BudgetGovernor, BudgetTree  # noqa: PLC0415
        tr = body.get("tree") or {}
        gov = BudgetGovernor(BudgetTree(
            workspace_monthly_minor=int(tr.get("workspace_monthly_minor") or 0),
            daily_cap_minor=int(tr.get("daily_cap_minor") or 0),
            adsets=int(tr.get("adsets") or 1)))
        verdict = gov.admit_spend(
            spent_today_minor=int(body.get("spent_today_minor") or 0),
            proposed_minor=int(body.get("proposed_minor") or 0),
            spent_month_minor=int(body.get("spent_month_minor") or 0))
        return JSONResponse({"allow": verdict.allow, "reason": verdict.reason,
                             "headroom_minor": verdict.headroom_minor, "stamp": verdict.stamp,
                             "runaway": gov.is_runaway(
                                 spent_today_minor=int(body.get("spent_today_minor") or 0))})

    return router
