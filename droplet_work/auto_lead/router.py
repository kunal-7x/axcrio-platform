"""
auto_lead.router — Haptica's Auto-Lead ingestion + automation API.

Built with the house build_router(resolve_tenant, can, need_auth, forbidden) pattern.

The hero is the PUBLIC real-time webhook:  POST /auto-lead/ingest/{token}
External systems (website forms, Zapier/Make, Meta/Google lead forms, custom) POST a
lead payload here; we map → validate → dedup → ROUTE it into Haptica's leads store
(so Riya can call it) + log it to the live feed. Unauthenticated by design (tenant is
derived from the unguessable per-source token, never a request field), with size cap +
honeypot on top of caller.py's global IP rate-limit.

Pull sources (email IMAP, Apollo) are polled by poll_once() (driven from caller.py's
scheduler) through the SAME pipeline.

Injected from caller.py:
  add_lead(tenant_id, lead) -> {"added": bool, "lead_id"?, "reason"?}  (writes leads.json)
  norm(phone) -> normalized phone                                       (callable)
  sync_crm(tenant_id, lead) -> awaitable   (optional; routes a lead to Sales CRM)
  client_ip(request) -> str                (optional)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .store import AutoLeadStore
from .pipeline import extract_candidate, validate
from .sources import SOURCE_TYPES, public_types, is_pull, poll_source, type_meta

_MAX_BODY = 64 * 1024  # 64 KB cap on an inbound webhook payload
_SECRET_KEYS = ("password", "api_key", "secret", "token_secret")


def _grow_enabled() -> bool:
    """FEATURE_GROW gate for the speed-to-lead hook (default OFF -> zero behaviour change)."""
    import os
    return (os.getenv("FEATURE_GROW", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def build_router(resolve_tenant, can, need_auth, forbidden, *,
                 var_dir, add_lead, norm, sync_crm=None, client_ip=None):
    store = AutoLeadStore(var_dir)
    router = APIRouter()

    def _tenant(request: Request):
        return resolve_tenant(request)

    def _ip(request: Request) -> str:
        if client_ip:
            try:
                return client_ip(request) or ""
            except Exception:  # noqa: BLE001
                pass
        return request.client.host if request.client else ""

    def _public_source(s: dict) -> dict:
        """Browser-safe view: mask credential config values; keep the ingest token
        (the tenant owns it — it's how they wire the webhook)."""
        cfg = dict(s.get("config") or {})
        for k in list(cfg.keys()):
            if k in _SECRET_KEYS and cfg[k]:
                cfg[k] = "••••"
        meta = type_meta(s.get("type"))
        return {
            "id": s.get("id"), "type": s.get("type"), "name": s.get("name"),
            "enabled": bool(s.get("enabled")), "token": s.get("token"),
            "mode": meta.get("mode"), "icon": meta.get("icon"), "type_label": meta.get("label"),
            "config": cfg, "mapping": s.get("mapping") or {},
            "validation": s.get("validation") or {}, "routing": s.get("routing") or {},
            "honeypot": s.get("honeypot") or "",
            "stats": s.get("stats") or {}, "created_at": s.get("created_at"),
            "updated_at": s.get("updated_at"),
        }

    async def _json_body(request: Request):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        return body

    # ── the pipeline core (shared by webhook / poll / test) ───────────────────
    async def _process(tid: str, source: dict, payload, *, ip: str = "",
                       channel: str = "webhook", dry_run: bool = False) -> dict:
        cand = extract_candidate(payload, source.get("mapping"))
        ok, reason, phone_norm = validate(cand, source.get("validation"), norm)
        routing = source.get("routing") or {}
        accepted = False
        lead_id = None
        actions: list[str] = []

        if ok and not dry_run:
            tags = [source.get("name") or source.get("type")] + list(routing.get("tags") or [])
            res = await add_lead(tid, {
                "name": cand["name"], "phone": cand["phone"], "email": cand["email"],
                "status": routing.get("status") or "new",
                "source": f"auto:{source.get('type')}", "tags": tags,
                "hot": bool(routing.get("mark_hot")),
            })
            if res.get("added"):
                accepted, lead_id = True, res.get("lead_id")
                actions.append("lead_created")
                if routing.get("sync_crm") and sync_crm:
                    try:
                        await sync_crm(tid, {"name": cand["name"], "phone": phone_norm,
                                             "email": cand["email"], "company": cand["company"],
                                             "status": routing.get("status") or "new"})
                        actions.append("crm_synced")
                    except Exception:  # noqa: BLE001
                        pass
                # ── Haptica Grow (FEATURE_GROW): a fresh, consent-clean lead -> the <60s
                #    speed-to-lead orchestrator (compliance gate -> WhatsApp + AI call) +
                #    the scoring/CAPI loop. Async-safe (binds the loop, runs off-thread) +
                #    best-effort — Grow can NEVER break lead ingest.
                if _grow_enabled():
                    try:
                        import grow as _grow  # noqa: PLC0415
                        _src = (source.get("type") or "").lower()
                        _plat = _src if _src in ("meta", "google", "whatsapp") else "auto"
                        await _grow.acapture(
                            tid, phone_norm or lead_id or "",
                            phone=cand["phone"], name=cand["name"], email=cand["email"],
                            source_platform=_plat, campaign_id=(routing.get("campaign_id") or ""),
                            consent_basis="explicit", consent_channel="web_form")
                        actions.append("grow_captured")
                    except Exception:  # noqa: BLE001 — Grow can NEVER break lead ingest
                        pass
            else:
                reason = res.get("reason") or "not added"
                lead_id = res.get("lead_id")
        elif ok and dry_run:
            accepted = True  # "would accept"

        if not dry_run:
            store.add_event(tid, {
                "source_id": source.get("id"), "source_name": source.get("name"),
                "source_type": source.get("type"), "channel": channel,
                "name": cand["name"], "phone": phone_norm or cand["phone"],
                "email": cand["email"], "company": cand["company"],
                "accepted": accepted, "reason": "accepted" if accepted else reason,
                "lead_id": lead_id, "actions": actions, "ip": ip,
            })
            store.bump_stats(tid, source.get("id"), accepted=accepted,
                             status=("accepted" if accepted else reason))
        return {"accepted": accepted, "reason": "accepted" if accepted else reason,
                "lead_id": lead_id, "actions": actions, "candidate": cand}

    # ── PUBLIC real-time ingest (unauthenticated; tenant from token) ──────────
    @router.post("/auto-lead/ingest/{token}")
    async def ingest(request: Request, token: str):
        raw = await request.body()
        if len(raw) > _MAX_BODY:
            return JSONResponse({"error": "payload too large"}, status_code=413)
        found = store.find_by_token(token)
        if not found:
            return JSONResponse({"error": "unknown source"}, status_code=404)
        tid, source = found
        if not source.get("enabled"):
            return JSONResponse({"ok": True, "ignored": "source paused"})
        payload = _parse_inbound(raw, request.headers.get("content-type", ""))
        hp = (source.get("honeypot") or "").strip()
        if hp and isinstance(payload, dict) and str(payload.get(hp) or "").strip():
            return JSONResponse({"ok": True})  # bot honeypot -> silent accept-drop
        res = await _process(tid, source, payload, ip=_ip(request), channel="webhook")
        return JSONResponse({"ok": True, "accepted": res["accepted"],
                             "reason": res["reason"], "lead_id": res["lead_id"]})

    # ── catalog ────────────────────────────────────────────────────────────────
    @router.get("/auto-lead/types")
    async def types(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        return JSONResponse({"types": public_types()})

    # ── sources CRUD ───────────────────────────────────────────────────────────
    @router.get("/auto-lead/sources")
    async def sources_list(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        rows = [_public_source(s) for s in store.list_sources(t["tenant_id"])]
        return JSONResponse({"sources": rows, "can_write": bool(can(t, "write"))})

    @router.post("/auto-lead/sources")
    async def sources_create(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("creating a source needs an admin or manager")
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        if (body.get("type") or "custom") not in SOURCE_TYPES:
            return JSONResponse({"error": "unknown source type"}, status_code=400)
        rec = store.add_source(t["tenant_id"], body)
        return JSONResponse({"ok": True, "source": _public_source(rec)})

    @router.get("/auto-lead/sources/{sid}")
    async def sources_get(request: Request, sid: str):
        t = _tenant(request)
        if not t:
            return need_auth()
        s = store.get_source(t["tenant_id"], sid)
        if not s:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"source": _public_source(s)})

    @router.patch("/auto-lead/sources/{sid}")
    async def sources_update(request: Request, sid: str):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        # never overwrite a masked secret: drop config keys whose value is the mask
        cfg = body.get("config")
        if isinstance(cfg, dict):
            existing = (store.get_source(t["tenant_id"], sid) or {}).get("config") or {}
            for k, v in list(cfg.items()):
                if v == "••••":
                    cfg[k] = existing.get(k, "")
        s = store.update_source(t["tenant_id"], sid, body)
        if not s:
            return JSONResponse({"error": "not found"}, status_code=404)
        return JSONResponse({"ok": True, "source": _public_source(s)})

    @router.delete("/auto-lead/sources/{sid}")
    async def sources_delete(request: Request, sid: str):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        return JSONResponse({"ok": store.delete_source(t["tenant_id"], sid)})

    # ── test (dry-run: shows the parse+validate plan, no lead created) ────────
    @router.post("/auto-lead/sources/{sid}/test")
    async def sources_test(request: Request, sid: str):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        s = store.get_source(t["tenant_id"], sid)
        if not s:
            return JSONResponse({"error": "not found"}, status_code=404)
        body = await _json_body(request)
        payload = body if not isinstance(body, JSONResponse) else {}
        if not payload:
            payload = {"name": "Test Lead", "phone": "+91 98765 43210",
                       "email": "test@example.com", "company": "Acme"}
        res = await _process(t["tenant_id"], s, payload, channel="test", dry_run=True)
        return JSONResponse({"ok": True, "would_accept": res["accepted"],
                             "reason": res["reason"], "parsed": res["candidate"]})

    # ── sync now (pull sources) ────────────────────────────────────────────────
    @router.post("/auto-lead/sources/{sid}/sync")
    async def sources_sync(request: Request, sid: str):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        s = store.get_source(t["tenant_id"], sid)
        if not s:
            return JSONResponse({"error": "not found"}, status_code=404)
        if not is_pull(s.get("type")):
            return JSONResponse({"error": "this source receives leads via its webhook URL"},
                                status_code=400)
        try:
            payloads = await asyncio.to_thread(poll_source, s)
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": f"poll failed: {e!s}"}, status_code=502)
        accepted = 0
        for p in payloads:
            r = await _process(t["tenant_id"], s, p, channel="poll")
            if r["accepted"]:
                accepted += 1
        return JSONResponse({"ok": True, "fetched": len(payloads), "accepted": accepted})

    # ── live feed ──────────────────────────────────────────────────────────────
    @router.get("/auto-lead/feed")
    async def feed(request: Request, source: str = "", status: str = "", limit: int = 100):
        t = _tenant(request)
        if not t:
            return need_auth()
        return JSONResponse({"events": store.list_events(t["tenant_id"], source_id=source,
                                                         status=status, limit=limit)})

    # ── overview ───────────────────────────────────────────────────────────────
    @router.get("/auto-lead/overview")
    async def overview(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        srcs = store.list_sources(t["tenant_id"])
        evs = store.list_events(t["tenant_id"], limit=400)
        today = datetime.now(timezone.utc).date().isoformat()

        def _st(s, k):
            return int((s.get("stats") or {}).get(k, 0) or 0)

        return JSONResponse({
            "total_sources": len(srcs),
            "active_sources": sum(1 for s in srcs if s.get("enabled")),
            "total_ingested": sum(_st(s, "ingested") for s in srcs),
            "total_accepted": sum(_st(s, "accepted") for s in srcs),
            "total_rejected": sum(_st(s, "rejected") for s in srcs),
            "accepted_today": sum(1 for e in evs if e.get("accepted") and (e.get("at", "")[:10] == today)),
            "rejected_today": sum(1 for e in evs if not e.get("accepted") and (e.get("at", "")[:10] == today)),
            "by_source": [{"id": s["id"], "name": s.get("name"), "type": s.get("type"),
                           "icon": type_meta(s.get("type")).get("icon"),
                           "ingested": _st(s, "ingested"), "accepted": _st(s, "accepted"),
                           "enabled": bool(s.get("enabled"))} for s in srcs],
            "recent": evs[:8],
        })

    # ── settings ───────────────────────────────────────────────────────────────
    @router.get("/auto-lead/settings")
    async def settings_get(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        return JSONResponse({"settings": store.get_settings(t["tenant_id"])})

    @router.put("/auto-lead/settings")
    async def settings_put(request: Request):
        t = _tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden()
        body = await _json_body(request)
        if isinstance(body, JSONResponse):
            return body
        return JSONResponse({"ok": True, "settings": store.set_settings(t["tenant_id"], body)})

    # ── poll loop (driven by caller.py's scheduler) ───────────────────────────
    async def poll_once():
        for tid, source in store.all_enabled_sources():
            if not is_pull(source.get("type")):
                continue
            try:
                payloads = await asyncio.to_thread(poll_source, source)
            except Exception:  # noqa: BLE001
                payloads = []
            for p in payloads:
                try:
                    await _process(tid, source, p, channel="poll")
                except Exception:  # noqa: BLE001
                    pass

    router.poll_once = poll_once  # type: ignore[attr-defined]
    return router


def _parse_inbound(raw: bytes, content_type: str):
    """Parse a webhook body: JSON, form-urlencoded, else best-effort JSON-or-raw."""
    ct = (content_type or "").lower()
    text = ""
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001
        text = ""
    if "application/json" in ct or text.strip().startswith(("{", "[")):
        try:
            d = json.loads(text or "{}")
            return d if isinstance(d, (dict, list)) else {"value": d}
        except Exception:  # noqa: BLE001
            pass
    if "application/x-www-form-urlencoded" in ct or ("=" in text and "{" not in text):
        try:
            return {k: (v[0] if isinstance(v, list) and v else "") for k, v in parse_qs(text).items()}
        except Exception:  # noqa: BLE001
            pass
    return {"_raw": text[:2000]}
