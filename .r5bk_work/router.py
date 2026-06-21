"""booking.router — FastAPI APIRouter for the Booking engine. DEFINED, NOT MOUNTED.

The orchestrator's DEFERRED sequential step mounts this into caller.py:
    from booking.router import router as booking_router
    app.include_router(booking_router)
This file does NOT import caller and is NOT wired into the app here (wiring is a deferred step).

TENANT / RBAC SEAM (injectable): there is no pre-existing APIRouter in this codebase (caller.py uses
raw `@app.post`), so the tenant + permission resolution is exposed as a dependency `get_ctx` that the
mount step OVERRIDES via `app.dependency_overrides[get_ctx] = <real resolver>` (binding it to
`caller.resolve_tenant` + the `can(tenant, action)` RBAC). The default `get_ctx` is import-safe and
self-contained so the router INSTANTIATES in the offline smoke test with no caller present.

All endpoints are dormant-safe: when Postgres is down the core returns `{"status":"not_configured"}`
and the endpoint returns it with 200 (or 503 for clearly-unavailable), never a 500 stack trace.
Risky reminder actuation flows through the same firewall/wallet gates as `core.tick`.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

try:
    from fastapi import APIRouter, Body, Depends, Query, Request
    _FASTAPI = True
except Exception:  # noqa: BLE001 - fastapi optional in a bare env; router degrades to a stub
    _FASTAPI = False

from . import calendar_sync, config, core


# --------------------------------------------------------------------------- #
# Auth context seam — OVERRIDDEN at mount. Default is safe + self-contained.
# --------------------------------------------------------------------------- #
class Ctx:
    """Resolved request context: tenant_id + admin flag + a permission checker."""

    def __init__(self, tenant_id: str = "", is_admin: bool = False, can=None):
        self.tenant_id = tenant_id
        self.is_admin = is_admin
        self._can = can

    def can(self, action: str) -> bool:
        if self._can is None:
            # No RBAC wired (offline/default) -> allow read-shaped, deny nothing here; the REAL
            # `can()` is injected at mount. Kept permissive ONLY in the un-mounted default so the
            # router is testable; production overrides this with caller's RBAC.
            return True
        try:
            return bool(self._can(self.tenant_id, action))
        except Exception:  # noqa: BLE001
            return False


def get_ctx(request: "Request" = None) -> Ctx:  # type: ignore[name-defined]
    """DEFAULT context resolver (overridden at mount via dependency_overrides).

    Reads `X-Tenant-Id` if present (dev/testing convenience); never trusts it in production because
    the mount step replaces this whole function with caller.resolve_tenant-backed resolution.
    """
    tid = ""
    try:
        if request is not None:
            tid = (request.headers.get("X-Tenant-Id") or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return Ctx(tenant_id=tid, is_admin=False, can=None)


def _parse_day(s: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat((s or "").strip())
    except Exception:  # noqa: BLE001
        return _dt.datetime.now(_dt.timezone.utc).date()


# --------------------------------------------------------------------------- #
# Router definition
# --------------------------------------------------------------------------- #
if _FASTAPI:
    router = APIRouter(prefix="/booking", tags=["booking"])

    @router.get("/status")
    def booking_status(ctx: Ctx = Depends(get_ctx)) -> dict:
        """Redacted module status (booleans only) — safe activation readout."""
        return {"booking": config.status(), "calendar": calendar_sync.status()}

    @router.post("/resources")
    def create_resource(ctx: Ctx = Depends(get_ctx), payload: dict = Body(default={})) -> dict:
        if not ctx.can("write"):
            return {"status": "error", "reason": "forbidden"}
        return core.create_resource(
            ctx.tenant_id, payload.get("name", ""), kind=payload.get("kind", "appointment"),
            timezone=payload.get("timezone", ""), slot_minutes=int(payload.get("slot_minutes", 0) or 0),
            capacity=int(payload.get("capacity", 1) or 1), windows=payload.get("windows"),
            is_admin=ctx.is_admin)

    @router.get("/availability")
    def availability(ctx: Ctx = Depends(get_ctx),
                     resource_id: str = Query(...), day: str = Query("")) -> dict:
        if not ctx.can("read"):
            return {"status": "error", "reason": "forbidden"}
        return core.get_availability(ctx.tenant_id, resource_id, day=_parse_day(day),
                                     is_admin=ctx.is_admin)

    @router.post("/book")
    def book(ctx: Ctx = Depends(get_ctx), payload: dict = Body(default={})) -> dict:
        if not ctx.can("write"):
            return {"status": "error", "reason": "forbidden"}
        return core.book(
            ctx.tenant_id, payload.get("resource_id", ""), payload.get("phone", ""),
            slot_start=payload.get("slot_start"), slot_end=payload.get("slot_end"),
            name=payload.get("name", ""), title=payload.get("title", ""),
            notes=payload.get("notes", ""), source=payload.get("source", "panel"),
            campaign_id=payload.get("campaign_id", ""), is_admin=ctx.is_admin)

    @router.get("/bookings")
    def list_bookings(ctx: Ctx = Depends(get_ctx),
                      contact_id: str = Query(""), status: str = Query(""),
                      limit: int = Query(100)) -> dict:
        if not ctx.can("read"):
            return {"status": "error", "reason": "forbidden"}
        return core.list_bookings(ctx.tenant_id, contact_id=contact_id, status=status,
                                  limit=limit, is_admin=ctx.is_admin)

    @router.get("/bookings/{booking_id}")
    def get_booking(booking_id: str, ctx: Ctx = Depends(get_ctx)) -> dict:
        if not ctx.can("read"):
            return {"status": "error", "reason": "forbidden"}
        return core.get_booking(ctx.tenant_id, booking_id, is_admin=ctx.is_admin)

    @router.post("/bookings/{booking_id}/reschedule")
    def reschedule(booking_id: str, ctx: Ctx = Depends(get_ctx),
                   payload: dict = Body(default={})) -> dict:
        if not ctx.can("write"):
            return {"status": "error", "reason": "forbidden"}
        return core.reschedule(ctx.tenant_id, booking_id,
                               new_slot_start=payload.get("slot_start"),
                               new_slot_end=payload.get("slot_end"), is_admin=ctx.is_admin)

    @router.post("/bookings/{booking_id}/cancel")
    def cancel(booking_id: str, ctx: Ctx = Depends(get_ctx),
               payload: dict = Body(default={})) -> dict:
        if not ctx.can("write"):
            return {"status": "error", "reason": "forbidden"}
        return core.cancel(ctx.tenant_id, booking_id, reason=payload.get("reason", ""),
                           is_admin=ctx.is_admin)

    @router.post("/bookings/{booking_id}/complete")
    def complete(booking_id: str, ctx: Ctx = Depends(get_ctx)) -> dict:
        if not ctx.can("write"):
            return {"status": "error", "reason": "forbidden"}
        return core.mark_completed(ctx.tenant_id, booking_id, is_admin=ctx.is_admin)

    @router.post("/tick")
    def tick(ctx: Ctx = Depends(get_ctx), dry_run: int = Query(1),
             payload: dict = Body(default={})) -> dict:
        """Manual fire of the reminder/no-show pass. `dry_run=1` (default) previews; `dry_run=0`
        actuates through the firewall (PIN, fail-closed) + wallet gates. Also runs every 60s in the
        scheduler once mounted. Requires `write` (and effectively a PIN for any spend)."""
        if not ctx.can("write"):
            return {"status": "error", "reason": "forbidden"}
        return core.tick(ctx.tenant_id, dry_run=bool(int(dry_run)), pin=payload.get("pin", ""))

else:  # pragma: no cover - bare env without fastapi
    router = None


# ================================================================================================
# build_router — the AUTHENTICATED mount surface (token-deriving), the platform pattern used by
# workflow-studio / forms-surveys. tenant_id is ALWAYS resolve_tenant(request)['tenant_id']
# (token-derived), NEVER the X-Tenant-Id header or a body field. Mutating routes enforce
# can(t,"write"); reads enforce can(t,"read"). is_admin is HARDCODED False — it feeds
# db.engine.session(tenant_id, is_admin) where is_admin=1 BYPASSES RLS, so it must never be
# attacker-influenced (neither body nor an unverified token claim). This is the surface the
# orchestrator mounts; the bare `router` + default `get_ctx` above are decoupled-for-test ONLY.
# ================================================================================================
def build_router(resolve_tenant: "Any", can: "Any", need_auth: "Any",
                 forbidden: "Any", firewall: Any = None,
                 loopback_resolver: "Any" = None) -> Any:
    """Build the tenant-authenticated booking router, injecting caller.py's auth helpers.

      resolve_tenant(request) -> {"tenant_id","role",...}|None   (token-derived identity)
      can(t, action) -> bool                                     (RBAC; "read"/"write")
      need_auth() -> Response (401) ; forbidden() -> Response (403)
      firewall -> the F4 firewall module (optional; risky tick spend flows through core.tick's
                  own firewall/wallet gates with the body-supplied pin).
      loopback_resolver(request, body) -> {"tenant_id",...}|None  (OPTIONAL; default None).
                  Used ONLY by POST /booking/book and ONLY when no token resolved a tenant.
                  Lets the in-box voice booking-tool (a local 127.0.0.1 POST that carries
                  campaign_id but no auth token) resolve to the campaign-OWNING tenant. The
                  caller injects a resolver that returns a tenant ONLY for a genuine loopback
                  peer (request.client.host) whose body.campaign_id maps to a real tenant; it
                  MUST return None for any non-loopback request. When None, behavior is
                  byte-identical to before (book stays 401 without a token).

    Returns an APIRouter or None if FastAPI is absent. tenant := token; is_admin := False always.
    """
    if not _FASTAPI:
        return None

    r = APIRouter(prefix="/booking", tags=["booking"])

    def _tid(t: dict) -> str:
        return str((t or {}).get("tenant_id") or "")

    async def _body(request) -> dict:
        try:
            b = await request.json()
            return b if isinstance(b, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    @r.get("/status")
    async def _status_ep(request: "Request"):  # type: ignore[name-defined]
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return {"booking": config.status(), "calendar": calendar_sync.status()}

    @r.post("/resources")
    async def _create_resource_ep(request: "Request"):  # type: ignore[name-defined]
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        p = await _body(request)
        return core.create_resource(
            _tid(t), p.get("name", ""), kind=p.get("kind", "appointment"),
            timezone=p.get("timezone", ""), slot_minutes=int(p.get("slot_minutes", 0) or 0),
            capacity=int(p.get("capacity", 1) or 1), windows=p.get("windows"), is_admin=False)

    @r.get("/availability")
    async def _availability_ep(request: "Request", resource_id: str = Query(...),  # type: ignore[name-defined]
                               day: str = Query("")):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "read"):
            return forbidden()
        return core.get_availability(_tid(t), resource_id, day=_parse_day(day), is_admin=False)

    @r.post("/book")
    async def _book_ep(request: "Request"):  # type: ignore[name-defined]
        t = resolve_tenant(request)
        # IN-BOX VOICE-TOOL EXEMPTION (book route ONLY): a local 127.0.0.1 POST from the
        # outbound voice agent carries campaign_id but no auth token. When (and ONLY when) no
        # token resolved a tenant, give the injected loopback_resolver the parsed body so it can
        # map campaign_id -> the campaign-OWNING tenant for a genuine loopback peer. The resolver
        # returns None for any non-loopback request, so external callers still get 401 below.
        p = await _body(request)
        if not t and loopback_resolver is not None:
            try:
                t = loopback_resolver(request, p)
            except Exception:  # noqa: BLE001 — a resolver fault must never 500 the book route
                t = None
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        org = _tid(t)
        # CONTRACT BRIDGE — accept BOTH the explicit panel shape AND the simplified voice/booking-tool
        # contract {phone, lead_name, datetime_iso, campaign_id, notes}. agent.py's booking-tool posts
        # the latter. Aliases: lead_name->name, datetime_iso->slot_start. Other fields unchanged.
        name = p.get("name") or p.get("lead_name", "")
        slot_start = p.get("slot_start") or p.get("datetime_iso")
        # AUTO-RESOURCE — when no resource_id is supplied, lazily ensure the tenant's single default
        # bookable resource so a phone+time book "just works" (the voice tool never knows a resource id).
        resource_id = p.get("resource_id", "")
        if not resource_id:
            dr = core.ensure_default_resource(org, is_admin=False)
            if dr.get("status") != "ok":
                return dr  # not_configured / db_error surfaces unchanged
            resource_id = dr["resource_id"]
        return core.book(
            org, resource_id, p.get("phone", ""),
            slot_start=slot_start, slot_end=p.get("slot_end"),
            name=name, title=p.get("title", ""), notes=p.get("notes", ""),
            source=p.get("source", "panel"), campaign_id=p.get("campaign_id", ""), is_admin=False)

    @r.get("/bookings")
    async def _list_bookings_ep(request: "Request", contact_id: str = Query(""),  # type: ignore[name-defined]
                                status: str = Query(""), limit: int = Query(100)):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "read"):
            return forbidden()
        return core.list_bookings(_tid(t), contact_id=contact_id, status=status,
                                  limit=limit, is_admin=False)

    @r.get("/bookings/{booking_id}")
    async def _get_booking_ep(booking_id: str, request: "Request"):  # type: ignore[name-defined]
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "read"):
            return forbidden()
        return core.get_booking(_tid(t), booking_id, is_admin=False)

    @r.post("/bookings/{booking_id}/reschedule")
    async def _reschedule_ep(booking_id: str, request: "Request"):  # type: ignore[name-defined]
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        p = await _body(request)
        return core.reschedule(_tid(t), booking_id, new_slot_start=p.get("slot_start"),
                               new_slot_end=p.get("slot_end"), is_admin=False)

    @r.post("/bookings/{booking_id}/cancel")
    async def _cancel_ep(booking_id: str, request: "Request"):  # type: ignore[name-defined]
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        p = await _body(request)
        return core.cancel(_tid(t), booking_id, reason=p.get("reason", ""), is_admin=False)

    @r.post("/bookings/{booking_id}/complete")
    async def _complete_ep(booking_id: str, request: "Request"):  # type: ignore[name-defined]
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        return core.mark_completed(_tid(t), booking_id, is_admin=False)

    @r.post("/tick")
    async def _tick_ep(request: "Request", dry_run: int = Query(1)):  # type: ignore[name-defined]
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        p = await _body(request)
        # spend actuation flows through core.tick's firewall(PIN, fail-closed)+wallet gates.
        return core.tick(_tid(t), dry_run=bool(int(dry_run)), pin=p.get("pin", ""))

    return r


# Public list of routes for the mount step / introspection (also handy in the smoke test).
ENDPOINTS = [
    ("GET", "/booking/status"),
    ("POST", "/booking/resources"),
    ("GET", "/booking/availability"),
    ("POST", "/booking/book"),
    ("GET", "/booking/bookings"),
    ("GET", "/booking/bookings/{booking_id}"),
    ("POST", "/booking/bookings/{booking_id}/reschedule"),
    ("POST", "/booking/bookings/{booking_id}/cancel"),
    ("POST", "/booking/bookings/{booking_id}/complete"),
    ("POST", "/booking/tick"),
]
