"""comm.endpoints — the Communication HTTP surface (Wave 1): channels setup/test, sessions,
test-send, and the FAIL-CLOSED inbound Telegram webhook. Mounted by caller.py via build_router.

Spec: communication/COMMUNICATION-MASTER-PLAN.md §7 (the /communication FE consumes these) +
§4 S2 (the webhook is the ONLY unauthenticated route — fail-closed, secret bound to the path
tenant) + WAVE 1/2.

TENANT ISOLATION (the build_router pattern — same shape as whatsapp_builder/provider_registry):
  * EVERY authenticated route derives the tenant from the AUTHENTICATED request token
    (resolve_tenant(request)["tenant_id"]) — NEVER from a body/query/path field. So a plain
    app.include_router(router) is cross-tenant-safe. Writes enforce can(t, "write").
  * The ONE exception is POST /comm/webhook/telegram/{tenant_id}: Telegram (a machine) calls it
    UNAUTHENTICATED. The {tenant_id} is UNTRUSTED until comm.webhook.handle() verifies the
    per-tenant secret_token (fail-closed); the RLS GUC is set only AFTER that verify.

EARNER LAW: FastAPI is imported lazily (offline tests import the package without it). build_router
degrades to None when FastAPI is absent. Every route is gated by COMM_ENABLED (config.comm_enabled())
so the resting state is byte-identical (routes self-404 when the flag is off). No route raises.

NOTE: this module intentionally does NOT use `from __future__ import annotations` — FastAPI must
see the REAL `Request`/`Body` annotation objects (imported in build_router's local scope) at route
decoration time to resolve them as request params, not stringified names against the module globals.
"""
from typing import Any, Callable, Optional

from . import config, engine, sessions
from .channels.base import Button, MediaItem, SendEnvelope


def build_router(
    resolve_tenant: Callable,
    can: Callable,
    need_auth: Optional[Callable] = None,
    forbidden: Optional[Callable] = None,
    *,
    require_super_admin: Optional[Callable] = None,
    firewall: Any = None,
    audit: Optional[Callable] = None,
):
    """Return a FastAPI APIRouter (prefix /comm) or None if FastAPI is absent. Mirrors the
    whatsapp_builder/provider_registry build_router signature so the caller.py mount is uniform."""
    try:
        from fastapi import APIRouter, Body, Request
        from fastapi.responses import JSONResponse
    except Exception:  # noqa: BLE001
        return None

    router = APIRouter(prefix="/comm", tags=["communication"])

    # ---- local helpers (degrade to the house defaults when the host didn't pass one) ----
    def _auth(request) -> Optional[dict]:
        return resolve_tenant(request)

    def _need_auth():
        if need_auth:
            return need_auth()
        return JSONResponse({"error": "authentication required"}, status_code=401)

    def _forbid(msg: str = "insufficient permissions"):
        if forbidden:
            return forbidden(msg)
        return JSONResponse({"error": msg}, status_code=403)

    def _is_admin(t: dict) -> bool:
        return bool(t.get("is_admin")) or t.get("role") == "admin"

    def _dormant():
        # COMM_ENABLED off -> the surface does not exist (404), resting byte-identical.
        return JSONResponse({"error": "not_found"}, status_code=404)

    def _audit(request, t, action, target_type, target_id, meta=None):
        if audit:
            try:
                audit(request, t, action, target_type, target_id, meta=meta or {})
            except Exception:  # noqa: BLE001
                pass

    # ======================================================================
    # CHANNELS — list / test / derive-chat-id / connect-webhook
    # ======================================================================
    @router.get("/channels")
    async def _channels(request: Request):
        if not config.comm_enabled():
            return _dormant()
        t = _auth(request)
        if not t:
            return _need_auth()
        st = engine.status()
        configured = bool(st.get("vault_available")) and config.telegram_enabled()
        return JSONResponse({
            "channels": [{
                "channel": "telegram",
                "enabled": config.telegram_enabled(),
                "configured": configured,
                "founder_alert": config.founder_alert_enabled(),
                "followup": config.followup_enabled(),
            }],
            "flags": st.get("flags", {}),
        })

    @router.post("/channels/telegram/test")
    async def _tg_test(request: Request):
        """The channel-setup "Test" — getMe identity check. Returns (ok, username)."""
        if not config.comm_enabled():
            return _dormant()
        t = _auth(request)
        if not t:
            return _need_auth()
        ok, username = await engine.verify_telegram(t["tenant_id"])
        return JSONResponse({"ok": bool(ok), "username": username})

    @router.post("/channels/telegram/derive-chat-id")
    async def _tg_chatid(request: Request, body: dict = Body(default={})):
        """Derive the founder chat_id from getUpdates (the founder tapped Start). Write-gated."""
        if not config.comm_enabled():
            return _dormant()
        t = _auth(request)
        if not t:
            return _need_auth()
        if not can(t, "write"):
            return _forbid()
        force = bool((body or {}).get("force"))
        chat_id = await engine.derive_founder_chat_id(t["tenant_id"], force=force)
        return JSONResponse({"chat_id": chat_id, "found": bool(chat_id)})

    @router.post("/channels/telegram/set-webhook")
    async def _tg_set_webhook(request: Request, body: dict = Body(default={})):
        """Register the inbound webhook with Telegram (setWebhook + the per-tenant secret_token).
        Body: {webhook_url} (https). Write-gated. The secret_token is derived server-side (never
        client-supplied) and bound to (tenant, bot def)."""
        if not config.comm_enabled():
            return _dormant()
        t = _auth(request)
        if not t:
            return _need_auth()
        if not can(t, "write"):
            return _forbid()
        url = str((body or {}).get("webhook_url", "")).strip()
        ok, pdid, err = await engine.set_telegram_webhook(t["tenant_id"], url)
        _audit(request, t, "comm.webhook.set", "comm_channel", "telegram",
               meta={"ok": bool(ok), "error": err})
        return JSONResponse({"ok": bool(ok), "provider_def_id": pdid, "error": err})

    @router.post("/channels/telegram/deeplink")
    async def _tg_deeplink(request: Request, body: dict = Body(default={})):
        """Mint a SIGNED, SINGLE-USE Telegram /start consent deep-link binding (this tenant, a
        contact phone). Body: {phone, bot_username?}. Returns {payload, link}. The tenant shares
        the link; when the contact taps it the webhook verifies it (S5) + binds their chat_id +
        writes a telegram_start consent row. Write-gated; the secret is server-side only."""
        if not config.comm_enabled():
            return _dormant()
        t = _auth(request)
        if not t:
            return _need_auth()
        if not can(t, "write"):
            return _forbid()
        b = body or {}
        phone = str(b.get("phone", "")).strip()
        if not phone:
            return JSONResponse({"error": "phone required"}, status_code=400)
        from . import deeplink
        payload = deeplink.mint(t["tenant_id"], phone)
        bot = str(b.get("bot_username", "")).strip()
        link = deeplink.link_for(bot, t["tenant_id"], phone) if bot else ""
        _audit(request, t, "comm.deeplink.mint", "comm_channel", "telegram",
               meta={"minted": bool(payload)})
        return JSONResponse({"payload": payload, "link": link, "ok": bool(payload)})

    # ======================================================================
    # SESSIONS — list / detail (the brain's rolling window; seeded post-call / inbound)
    # ======================================================================
    @router.get("/sessions")
    async def _sessions(request: Request, channel: str = "", status: str = "",
                        limit: int = 50, offset: int = 0):
        if not config.comm_enabled():
            return _dormant()
        t = _auth(request)
        if not t:
            return _need_auth()
        rows = sessions.list_sessions(
            t["tenant_id"], channel=channel, status=status, limit=limit, offset=offset,
            is_admin=_is_admin(t),
        )
        return JSONResponse({"sessions": rows, "total": len(rows)})

    @router.get("/sessions/{session_id}")
    async def _session_detail(session_id: str, request: Request):
        if not config.comm_enabled():
            return _dormant()
        t = _auth(request)
        if not t:
            return _need_auth()
        row = sessions.get_session(t["tenant_id"], session_id, is_admin=_is_admin(t))
        if row is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse({"session": row})

    # ======================================================================
    # SEND — a tenant-initiated test send (the "send to me" channel-setup proof). Write-gated.
    # ======================================================================
    @router.post("/send")
    async def _send(request: Request, body: dict = Body(default={})):
        """Send one message on a channel (W1: Telegram). Body:
        {to_ref, text, kind?, purpose?, media?[{url,kind,caption}], buttons?[{text,url}]}.
        Tenant-derived from the token; metered + logged by the engine. Write-gated."""
        if not config.comm_enabled():
            return _dormant()
        t = _auth(request)
        if not t:
            return _need_auth()
        if not can(t, "write"):
            return _forbid()
        b = body or {}
        to_ref = str(b.get("to_ref", "")).strip()
        if not to_ref:
            return JSONResponse({"error": "to_ref required"}, status_code=400)
        media = []
        for m in (b.get("media") or [])[:4]:
            if isinstance(m, dict):
                media.append(MediaItem(
                    kind=str(m.get("kind", "photo")), url=str(m.get("url", "")),
                    file_id=str(m.get("file_id", "")), caption=str(m.get("caption", "")),
                    spaces_key=str(m.get("spaces_key", "")),
                ))
        buttons = []
        for btn in (b.get("buttons") or [])[:6]:
            if isinstance(btn, dict) and btn.get("url") and btn.get("text"):
                buttons.append(Button(text=str(btn["text"]), url=str(btn["url"])))
        env = SendEnvelope(
            to_ref=to_ref, kind=str(b.get("kind", "text")),
            purpose=str(b.get("purpose", "service")), text=str(b.get("text", "")),
            media=media, buttons=buttons,
        )
        res = await engine.send(t["tenant_id"], env, session_id=str(b.get("session_id", "")))
        _audit(request, t, "comm.send", "comm_message", res.external_id or "",
               meta={"channel": res.channel, "status": res.status, "kind": env.kind})
        return JSONResponse({
            "ok": res.ok, "status": res.status, "channel": res.channel,
            "external_id": res.external_id, "error_code": res.error_code,
            "cost_minor": res.cost_minor,
        })

    # ======================================================================
    # WEBHOOK — the ONLY unauthenticated route. FAIL-CLOSED (S2). Telegram calls it.
    # ======================================================================
    @router.post("/webhook/telegram/{tenant_id}")
    async def _tg_webhook(tenant_id: str, request: Request):
        """Inbound Telegram webhook for the PATH tenant. UNAUTHENTICATED (a machine calls it):
        the {tenant_id} is UNTRUSTED until comm.webhook.handle() verifies the per-tenant
        secret_token (fail-closed). The RLS GUC is set only AFTER that verify, inside handle().
        ALWAYS returns fast; never raises; never blocks. W1 = verify + store + ack (no reply)."""
        # resting byte-identical: when the flag is off this route does not functionally exist.
        if not config.comm_enabled():
            return _dormant()
        from .webhook import SECRET_HEADER, handle  # local import (no module-load cost when dormant)
        header_value = request.headers.get(SECRET_HEADER, "")
        try:
            raw = await request.body()
        except Exception:  # noqa: BLE001
            raw = b""
        status_code, payload = await handle(tenant_id, header_value, raw)
        return JSONResponse(payload, status_code=status_code)

    return router
