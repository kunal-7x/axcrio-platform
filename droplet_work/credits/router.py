"""credits/router.py — the /credits API surface (FastAPI APIRouter, mounted by caller.py).

Wiring mirrors the payments/workflow house pattern: caller.py calls wire(...) to inject its auth
helpers, then app.include_router(router, prefix="/credits"). Tenant is ALWAYS token-derived
(resolve_tenant) — never a body/query field — so there is no cross-tenant hole. Reads require an
authed tenant; spend-sensitive admin writes additionally pass the Action-Firewall step-up.

Routes
  CLIENT (authed tenant, own data):
    GET  /credits/health              engine + gateway availability (dormant-safe summary)
    GET  /credits/wallet              balance (credits + ₹), lifetime, MTD spend, low-balance flag
    GET  /credits/ledger              unified ledger: top-ups/grants + per-service debits
    GET  /credits/usage               per-service usage + cost breakdown for a window
    GET  /credits/pricing             the service costing matrix (read)
    GET  /credits/packages            buy-credits packages + which gateways are live
    POST /credits/topup/checkout      create a Razorpay order / Stripe session for a top-up
    POST /credits/topup/webhook/{p}   gateway webhook (signature-verified) -> idempotent credit
  ADMIN (require_super_admin):
    GET  /credits/admin/overview      fleet credit analytics (outstanding, revenue, cost, margin)
    GET  /credits/admin/pricing       costing matrix (read)
    PUT  /credits/admin/pricing       save matrix overrides (basis/markup/price/metered)  [step-up]
    POST /credits/admin/grant         grant/adjust a tenant's credits                      [step-up]
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, Form, Request
from fastapi.responses import JSONResponse

from . import gateways, pricing
from .engine import get_engine

router = APIRouter()

# ── injected by wire() ──
_resolve_tenant = None
_can = None
_need_auth = None
_forbidden = None
_firewall = None
_require_super_admin = None
_audit = None
_step_up = None


def wire(*, resolve_tenant, can, need_auth, forbidden, firewall=None,
         require_super_admin=None, audit=None, step_up_guard=None):
    global _resolve_tenant, _can, _need_auth, _forbidden, _firewall
    global _require_super_admin, _audit, _step_up
    _resolve_tenant = resolve_tenant
    _can = can
    _need_auth = need_auth
    _forbidden = forbidden
    _firewall = firewall
    _require_super_admin = require_super_admin
    _audit = audit
    _step_up = step_up_guard


def _tenant(request: Request):
    return _resolve_tenant(request) if _resolve_tenant else None


def _var():
    try:
        import caller
        return caller.VAR
    except Exception:  # noqa: BLE001
        from pathlib import Path
        import os
        return Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))


def _admin_ok(request: Request):
    """Return (tenant, None) when the caller is a real super-admin, else (None, error-response)."""
    if _require_super_admin is not None:
        res = _require_super_admin(request)
        if isinstance(res, JSONResponse):
            return None, res
        return res, None
    t = _tenant(request)
    if not t:
        return None, (_need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401))
    if not (_can and _can(t, "manage_tenants")):
        return None, (_forbidden("admin only") if _forbidden else JSONResponse({"error": "admin only"}, status_code=403))
    return t, None


def _packages() -> list[dict]:
    """Buy-credits packages. price_inr buys `credits`; bigger packs add free `bonus`."""
    rate = pricing.credit_rate()
    base = [
        {"id": "starter", "credits": 500, "bonus": 0, "popular": False},
        {"id": "growth", "credits": 1000, "bonus": 50, "popular": True},
        {"id": "scale", "credits": 5000, "bonus": 500, "popular": False},
        {"id": "pro", "credits": 10000, "bonus": 1500, "popular": False},
    ]
    out = []
    for p in base:
        out.append({
            **p,
            "price_inr": round(p["credits"] * rate, 2),
            "total_credits": p["credits"] + p["bonus"],
            "bonus_pct": round(p["bonus"] / p["credits"] * 100, 1) if p["credits"] else 0,
        })
    return out


# ── CLIENT ────────────────────────────────────────────────────────────────────────────────
@router.get("/health")
async def credits_health(request: Request):
    t = _tenant(request)
    if not t:
        return _need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401)
    eng = get_engine()
    return JSONResponse({
        "ok": True, "engine": eng.name,
        "credit_rate_inr": pricing.credit_rate(),
        "gateways": gateways.configured_providers(),
        "default_gateway": gateways.default_provider(),
        "topup_enabled": bool(gateways.default_provider()),
    })


@router.get("/wallet")
async def credits_wallet(request: Request):
    t = _tenant(request)
    if not t:
        return _need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401)
    eng = get_engine()
    data = await asyncio.to_thread(eng.wallet, t["tenant_id"], bool(t.get("is_admin")))
    return JSONResponse(data)


@router.get("/ledger")
async def credits_ledger(request: Request, limit: int = 100):
    t = _tenant(request)
    if not t:
        return _need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401)
    eng = get_engine()
    rows = await asyncio.to_thread(eng.ledger, t["tenant_id"], int(limit or 100))
    return JSONResponse({"ledger": rows, "total": len(rows)})


@router.get("/usage")
async def credits_usage(request: Request, **__):
    t = _tenant(request)
    if not t:
        return _need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401)
    frm = request.query_params.get("from", "")
    to = request.query_params.get("to", "")
    eng = get_engine()
    data = await asyncio.to_thread(eng.usage, t["tenant_id"], frm, to)
    return JSONResponse(data)


@router.get("/pricing")
async def credits_pricing(request: Request):
    t = _tenant(request)
    if not t:
        return _need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401)
    return JSONResponse(pricing.matrix(_var()))


@router.get("/packages")
async def credits_packages(request: Request):
    t = _tenant(request)
    if not t:
        return _need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401)
    return JSONResponse({
        "packages": _packages(),
        "credit_rate_inr": pricing.credit_rate(),
        "gateways": gateways.configured_providers(),
        "default_gateway": gateways.default_provider(),
        "topup_enabled": bool(gateways.default_provider()),
        "min_topup_inr": 100,
    })


@router.post("/meter")
async def credits_meter(request: Request, service: str = Form(...), qty: float = Form(1.0),
                        idem_key: str = Form(""), tenant_id: str = Form("")):
    """Report ONE usage event for `service` (a costing-matrix key, e.g. "kb.index"/"creative.image").
    Tenant is token-derived; an ADMIN may meter on behalf of another tenant via the tenant_id field.
    Tracks the usage (Usage tab) and debits the wallet only when CREDITS_METER_CHARGE is on. In-process
    services call engine.record_usage() directly — this HTTP seam is for out-of-process / external
    callers (e.g. the ads_engine / media_gen packages deployed outside this repo)."""
    t = _tenant(request)
    if not t:
        return _need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401)
    target = t["tenant_id"]
    if tenant_id and t.get("is_admin"):
        target = tenant_id
    if not service:
        return JSONResponse({"ok": False, "reason": "service required"}, status_code=400)
    eng = get_engine()
    res = await asyncio.to_thread(eng.record_usage, target, service, float(qty or 0),
                                  meta={"idem_key": idem_key})
    return JSONResponse({"ok": True, "tenant_id": target, **res})


@router.post("/topup/checkout")
async def credits_topup_checkout(request: Request, amount_inr: float = Form(0.0),
                                 credits: float = Form(0.0), package_id: str = Form(""),
                                 provider: str = Form("")):
    t = _tenant(request)
    if not t:
        return _need_auth() if _need_auth else JSONResponse({"error": "auth"}, status_code=401)
    if not (_can and _can(t, "write")):
        return _forbidden("manager or admin required to buy credits") if _forbidden \
            else JSONResponse({"error": "forbidden"}, status_code=403)
    rate = pricing.credit_rate()
    # resolve amount: explicit ₹, explicit credits, or a named package
    amt = float(amount_inr or 0)
    cr = float(credits or 0)
    if package_id:
        pkg = next((p for p in _packages() if p["id"] == package_id), None)
        if not pkg:
            return JSONResponse({"status": "error", "message": "unknown package"}, status_code=400)
        amt = pkg["price_inr"]
        cr = pkg["total_credits"]
    elif amt <= 0 and cr > 0:
        amt = round(cr * rate, 2)
    elif amt > 0 and cr <= 0:
        cr = round(amt / rate, 4)
    if amt <= 0:
        return JSONResponse({"status": "error", "message": "amount must be positive"}, status_code=400)
    res = await asyncio.to_thread(
        gateways.create_checkout, provider, t["tenant_id"], amt, cr,
        f"Credit top-up for {t.get('name') or t['tenant_id']}", t.get("email", ""))
    if _audit:
        _audit(request, t, "credits.topup.checkout", "credits", t["tenant_id"],
               channel="api", meta={"amount_inr": amt, "credits": cr, "provider": res.get("provider"),
                                    "status": res.get("status")})
    code = 200 if res.get("status") in ("created", "not_configured") else 400
    return JSONResponse(res, status_code=code)


@router.post("/topup/webhook/{provider}")
async def credits_topup_webhook(request: Request, provider: str):
    """Gateway webhook -> idempotent credit. PUBLIC but HMAC-signature verified before any credit."""
    raw = await request.body()
    info = gateways.verify_and_extract(provider, raw, dict(request.headers))
    if not info.get("ok"):
        return JSONResponse({"ok": False, "reason": info.get("reason", "verification failed")}, status_code=400)
    if not info.get("captured"):
        return JSONResponse({"ok": True, "ignored": True, "event": info.get("event")})
    tenant_id = info.get("tenant_id")
    amount_inr = float(info.get("amount_inr", 0) or 0)
    if not tenant_id or amount_inr <= 0:
        return JSONResponse({"ok": False, "reason": "missing tenant/amount"}, status_code=400)
    eng = get_engine()
    res = await asyncio.to_thread(
        eng.topup, tenant_id, amount_inr,
        provider=provider, payment_id=info.get("payment_id", ""),
        idem_key=f"{provider}:{info.get('payment_id','')}", note="online top-up")
    return JSONResponse({"ok": bool(res.get("ok")), "credited_inr": res.get("credited_inr"),
                         "credited_credits": res.get("credited_credits"), "deduped": res.get("deduped", False)})


# ── ADMIN (super-admin only) ────────────────────────────────────────────────────────────────
@router.get("/admin/overview")
async def credits_admin_overview(request: Request):
    t, err = _admin_ok(request)
    if err:
        return err
    eng = get_engine()

    def _build():
        import caller
        store = caller._read_billing() if hasattr(caller, "_read_billing") else {}
        tenant_ids = list(store.keys())
        rows, outstanding, mtd_topup, mtd_spend = [], 0.0, 0.0, 0.0
        topups = eng.topups("", limit=100000)
        from .engine import _month_start, _parse_ts
        from datetime import timezone as _tz
        ms = _month_start()
        for tp in topups:
            ts = _parse_ts(tp.get("at"))
            if ts is not None and (ts if ts.tzinfo else ts.replace(tzinfo=_tz.utc)) >= ms \
                    and tp.get("status") == "captured":
                mtd_topup += float(tp.get("amount_inr", 0) or 0)
        for tid in tenant_ids:
            w = eng.wallet(tid, True)
            outstanding += w.get("balance_inr", 0)
            mtd_spend += w.get("mtd_spend_inr", 0)
            tn = caller._tenant_by_id(tid) if hasattr(caller, "_tenant_by_id") else None
            rows.append({
                "tenant_id": tid, "name": (tn or {}).get("name", tid),
                "email": (tn or {}).get("email", ""), "plan": w.get("plan"),
                "balance_inr": w.get("balance_inr"), "balance_credits": w.get("balance_credits"),
                "mtd_spend_inr": w.get("mtd_spend_inr"), "low_balance": w.get("low_balance"),
            })
        rows.sort(key=lambda r: r.get("balance_inr", 0), reverse=True)
        rate = pricing.credit_rate()
        return {
            "currency": "INR", "credit_rate_inr": rate, "engine": eng.name,
            "tenants": rows, "tenant_count": len(rows),
            "outstanding_inr": round(outstanding, 2), "outstanding_credits": round(outstanding / rate, 2),
            "mtd_revenue_inr": round(mtd_topup, 2), "mtd_cost_inr": round(mtd_spend, 2),
            "mtd_margin_inr": round(mtd_topup - mtd_spend, 2),
            "gateways": gateways.configured_providers(),
        }

    try:
        data = await asyncio.to_thread(_build)
    except Exception as e:  # noqa: BLE001
        data = {"currency": "INR", "tenants": [], "tenant_count": 0, "error": str(e),
                "outstanding_inr": 0, "mtd_revenue_inr": 0, "mtd_cost_inr": 0, "mtd_margin_inr": 0}
    return JSONResponse(data)


@router.get("/admin/pricing")
async def credits_admin_pricing(request: Request):
    t, err = _admin_ok(request)
    if err:
        return err
    return JSONResponse(pricing.matrix(_var()))


@router.put("/admin/pricing")
async def credits_admin_save_pricing(request: Request, payload: dict = Body(...)):
    t, err = _admin_ok(request)
    if err:
        return err
    if _step_up is not None:
        denied = _step_up(request, "spend", t)
        if denied is not None:
            return denied
    # payload = {overrides: {service_key: {basis_inr?, markup_pct?, price_inr?, metered?, label?}}}
    overrides = payload.get("overrides") if isinstance(payload, dict) else None
    if not isinstance(overrides, dict):
        return JSONResponse({"ok": False, "reason": "overrides object required"}, status_code=400)
    ok = await asyncio.to_thread(pricing.save_overrides, _var(), overrides)
    if _audit:
        _audit(request, t, "credits.pricing.update", "credits", "matrix",
               channel="control", meta={"keys": list(overrides.keys())})
    return JSONResponse({"ok": ok, **pricing.matrix(_var())})


@router.post("/admin/grant")
async def credits_admin_grant(request: Request, tenant_id: str = Form(...),
                              credits: float = Form(0.0), amount_inr: float = Form(0.0),
                              note: str = Form("")):
    t, err = _admin_ok(request)
    if err:
        return err
    if _step_up is not None:
        denied = _step_up(request, "spend", t)
        if denied is not None:
            return denied
    rate = pricing.credit_rate()
    amt = float(amount_inr or 0) or round(float(credits or 0) * rate, 2)
    if amt == 0:
        return JSONResponse({"ok": False, "reason": "credits or amount_inr required"}, status_code=400)
    eng = get_engine()
    res = await asyncio.to_thread(eng.topup, tenant_id, amt, provider="grant",
                                  note=note or "admin grant", acting=t.get("tenant_id", ""),
                                  idem_key="")
    if _audit:
        _audit(request, t, "credits.grant", "credits", tenant_id,
               channel="control", meta={"amount_inr": amt, "credits": round(amt / rate, 2), "note": note})
    return JSONResponse(res)
