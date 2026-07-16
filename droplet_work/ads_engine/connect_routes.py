"""ads_engine.connect_routes — the /ads/connect/* sub-router: OAuth connect + page claim + webhook
subscribe + budget funding (BLINDSPOTS B4, B16, B17, B13/B14/B15).

A SEPARATE build_router-style module (NOT endpoints.py) so it composes alongside the existing
`/ads` router without conflicting with parallel edits. Same auth contract as endpoints.build_router:
tenant is ALWAYS token-derived via the injected `resolve_tenant` — EXCEPT the OAuth callback, which
is a browser redirect (no auth header) and instead recovers the tenant from the HMAC-signed `state`
(CSRF + single-use nonce). Every route 404s while FEATURE_ADS is OFF (defense in depth).

EARNER-SAFE: no route spends money or touches agent.py/voice. Real provider network calls (token
exchange, page-ownership proof, leadgen subscribe, funding read) are flag-gated (ADS_OAUTH_LIVE /
ADS_CONNECT_LIVE); default DRY-RUN returns a clearly-flagged simulated result.

Mount: `caller.py` calls `build_connect_router(resolve_tenant, can, need_auth, forbidden, ...)` and
`app.include_router(...)` right after the main ads router (additive; mount failure never crashes).
"""

from __future__ import annotations

import logging
from typing import Any

from . import config, funding, oauth, store, vault_adapter
from .store import PageOwnershipConflict

try:
    from fastapi import APIRouter, Request, Response
    from fastapi.responses import JSONResponse, RedirectResponse
    _HAVE_FASTAPI = True
except Exception:  # noqa: BLE001
    _HAVE_FASTAPI = False
    APIRouter = Request = Response = JSONResponse = RedirectResponse = None  # type: ignore

_log = logging.getLogger("ads_engine.connect_routes")

_CLAIM_KINDS = ("page", "dataset", "wa-phone")
# kind -> the vault blob field that proves ownership for the live check (page only, today).
_NONCE_COLL = "oauth_nonces"
_SUBS_COLL = "leadgen_subscriptions"


def build_connect_router(resolve_tenant, can, need_auth, forbidden, *,
                         require_super_admin=None, firewall=None, audit=None, auth_method=None):
    """Build the /ads/connect router. Returns an APIRouter, or None if FastAPI is absent."""
    if not _HAVE_FASTAPI:
        return None

    router = APIRouter(prefix="/ads/connect", tags=["ads_connect"])

    # ---- local helpers (mirror endpoints.build_router) ----
    def _disabled():
        return JSONResponse({"error": "not_found"}, status_code=404)

    def _tid(t: dict) -> str:
        return str((t or {}).get("tenant_id") or "")

    async def _body(request) -> dict:
        try:
            b = await request.json()
            return b if isinstance(b, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _audit(request, t, action, object_type="connection", object_id="", meta=None):
        if audit is None:
            return
        try:
            audit(request, t, action, object_type, object_id, meta=meta)
        except Exception:  # noqa: BLE001
            pass

    def _is_legacy_pw(request) -> bool:
        if auth_method is None:
            return False
        try:
            return auth_method(request) == "legacy_pw"
        except Exception:  # noqa: BLE001 — classifier error on a mutation path => fail CLOSED
            return True

    def _auth(request):
        if not config.is_enabled():
            return None, _disabled()
        t = resolve_tenant(request)
        if not t:
            return None, need_auth()
        return t, None

    def _write_gate(request, t):
        if not can(t, "write"):
            return forbidden("read-only")
        if _is_legacy_pw(request):
            return forbidden("legacy password cannot mutate ad connections")
        return None

    # =========================================================================
    # PROVIDER STATUS — drives the "Connect with Meta / Google" panel.
    # =========================================================================
    @router.get("/providers")
    async def connect_providers(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        tid = _tid(t)
        out = []
        for p in oauth.supported_providers():
            au = oauth.build_authorize_url(tid, p, "probe")  # probe: app-configured check only
            try:
                connected = vault_adapter.is_configured(tid, p)
            except Exception:  # noqa: BLE001
                connected = False
            out.append({
                "provider": p,
                "connected": bool(connected),
                # ready to start the flow == ok (both the app client_id AND the state secret present);
                # any other reason (app_not_configured / oauth_state_not_configured) -> not ready.
                "app_configured": bool(au.get("ok")),
                "reason": au.get("reason", ""),
                "redirect_uri": au.get("redirect_uri", ""),
                "live": oauth.live_enabled(),
            })
        return JSONResponse({"ok": True, "providers": out})

    # =========================================================================
    # OAUTH START — build the provider authorize URL + store a single-use nonce.
    # =========================================================================
    @router.get("/{provider}/start")
    async def connect_start(provider: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        if not oauth.is_supported(provider):
            return JSONResponse({"ok": False, "reason": "unsupported_provider"}, status_code=200)
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        nonce = oauth.new_nonce()
        res = oauth.build_authorize_url(tid, provider, nonce)
        if res.get("ok"):
            # Persist the nonce (single-use) so the callback can prove this start was ours.
            try:
                store.put_row(tid, _NONCE_COLL, nonce,
                              {"provider": provider.lower(), "nonce": nonce})
            except Exception:  # noqa: BLE001 — nonce store best-effort; state HMAC still binds
                pass
        _audit(request, t, "ads.connect.start", "connection", provider,
               {"reason": res.get("reason")})
        return JSONResponse(res)

    # =========================================================================
    # OAUTH CALLBACK — browser redirect (UNAUTH). Tenant recovered from signed state.
    # =========================================================================
    @router.get("/{provider}/callback")
    async def connect_callback(provider: str, request: "Request") -> Any:
        if not config.is_enabled():
            return _disabled()
        qp = request.query_params
        code = str(qp.get("code", "") or "")
        state = str(qp.get("state", "") or "")
        payload = oauth.verify_state(state)
        # Sanitize the path-derived provider before it is reflected into the redirect Location
        # (defense-in-depth vs response-splitting / open-redirect): only a known provider slug is
        # ever echoed back; anything else collapses to "unknown".
        safe_provider = provider.lower() if oauth.is_supported(provider) else "unknown"

        def _redirect(status: str):
            target = f"/ads?tab=connections&connect={safe_provider}&status={status}"
            if RedirectResponse is not None:
                return RedirectResponse(url=target, status_code=303)
            return JSONResponse({"ok": status == "connected", "status": status,
                                 "provider": safe_provider})

        if not payload or payload.get("p") != (provider or "").lower():
            return _redirect("bad_state")
        tid = str(payload.get("t") or "")
        nonce = str(payload.get("n") or "")
        # Single-use: consume the stored nonce (replay defense). Missing nonce -> reject.
        try:
            row = store.get_row(tid, _NONCE_COLL, nonce)
        except Exception:  # noqa: BLE001
            row = None
        if not row:
            return _redirect("replayed_or_expired")
        try:
            store.delete_row(tid, _NONCE_COLL, nonce)
        except Exception:  # noqa: BLE001
            pass
        # Exchange the code (live-gated) and LAND the token into the vault. Token never echoed.
        exch = await oauth.exchange_code(provider, code)
        if not exch.get("ok"):
            # dry_run / app_not_configured / exchange_failed -> tell the UI, write nothing.
            return _redirect(str(exch.get("reason") or "exchange_failed"))
        token = exch.get("token")
        field = exch.get("token_field") or oauth.token_field(provider)
        wr = vault_adapter.write_channel_blob(tid, oauth._PROVIDERS[provider.lower()]["channel"],
                                              {field: token})
        if audit is not None:
            try:
                audit(None, {"tenant_id": tid}, "ads.connect.callback", "connection", provider,
                      meta={"reason": wr.get("reason"), "fields": wr.get("fields_written")})
            except Exception:  # noqa: BLE001
                pass
        return _redirect("connected" if wr.get("ok") else str(wr.get("reason") or "write_failed"))

    # =========================================================================
    # CLAIM — ownership-prove a Page / dataset / WhatsApp phone -> page_tenant_map (B16).
    # =========================================================================
    @router.post("/claim/{kind}")
    async def connect_claim(kind: str, request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        k = (kind or "").strip().lower()
        if k not in _CLAIM_KINDS:
            return JSONResponse({"ok": False, "reason": "bad_kind"}, status_code=200)
        tid = _tid(t)
        body = await _body(request)
        claim_id = str(body.get("id") or body.get("page_id") or body.get("dataset_id")
                       or body.get("wa_phone_id") or "").strip()
        if not claim_id:
            return JSONResponse({"ok": False, "reason": "missing_id"}, status_code=200)

        # Ownership proof (page only, live-gated): the id must appear in the vendor's OWN /me/accounts.
        proven = "asserted"
        if k == "page" and funding.live_enabled():
            try:
                creds = vault_adapter.get_connector_creds(tid, "meta")
                if getattr(creds, "ok", False):
                    from .connectors.meta import MetaConnector
                    res = await MetaConnector(creds).list_owned_pages()
                    if getattr(res, "ok", False):
                        owned = {str(p.get("id")) for p in
                                 ((getattr(res, "data", None) or {}).get("data") or [])}
                        if claim_id not in owned:
                            return JSONResponse({"ok": False, "reason": "not_owned"},
                                                status_code=200)
                        proven = "me_accounts"
                    else:
                        return JSONResponse({"ok": False, "reason": "ownership_unverified"},
                                            status_code=200)
                else:
                    return JSONResponse({"ok": False, "reason": "meta_not_configured"},
                                        status_code=200)
            except Exception:  # noqa: BLE001
                return JSONResponse({"ok": False, "reason": "ownership_check_failed"},
                                    status_code=200)

        evidence = {"oauth_flow": "connect", "connected_by": k,
                    "business_id": str(body.get("business_id") or "")}
        try:
            row = store.link_page_to_tenant(tid, claim_id, actor=k, evidence=evidence)
        except PageOwnershipConflict:
            return JSONResponse({"ok": False, "reason": "already_claimed_by_other_tenant"},
                                status_code=409)
        except ValueError:
            return JSONResponse({"ok": False, "reason": "invalid_id"}, status_code=200)
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "reason": "claim_failed"}, status_code=200)
        _audit(request, t, "ads.connect.claim", "page", claim_id,
               {"kind": k, "proven": proven})
        return JSONResponse({"ok": True, "kind": k, "id": claim_id, "proven": proven,
                             "linked_at": row.get("linked_at")})

    @router.get("/claims")
    async def connect_claims(request: "Request") -> Any:
        """List the pages/datasets/wa-phones THIS tenant has claimed (secret-free)."""
        t, err = _auth(request)
        if err:
            return err
        tid = _tid(t)
        rows = []
        try:
            read = store._require("read")  # type: ignore[attr-defined]
            data = read(store._page_map_path(), {})  # type: ignore[attr-defined]
            if isinstance(data, dict):
                for pid, r in data.items():
                    if isinstance(r, dict) and str(r.get("tenant_id")) == store._safe(tid):  # type: ignore[attr-defined]
                        rows.append({"id": pid, "kind": (r.get("evidence") or {}).get("connected_by", ""),
                                     "linked_at": r.get("linked_at"), "updated_at": r.get("updated_at")})
        except Exception:  # noqa: BLE001
            rows = []
        return JSONResponse({"ok": True, "claims": rows})

    # =========================================================================
    # SUBSCRIBE — wire the Meta leadgen webhook for a claimed page (B17).
    # =========================================================================
    @router.post("/subscribe/leadgen")
    async def connect_subscribe_leadgen(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        gate = _write_gate(request, t)
        if gate:
            return gate
        tid = _tid(t)
        body = await _body(request)
        page_id = str(body.get("page_id") or body.get("id") or "").strip()
        if not page_id:
            return JSONResponse({"ok": False, "reason": "missing_page_id"}, status_code=200)
        # The page must be claimed by THIS tenant first (anti-hijack: don't subscribe foreign pages).
        try:
            owner = store.get_tenant_for_page(page_id)
        except Exception:  # noqa: BLE001
            owner = None
        if owner and str(owner) != store._safe(tid):  # type: ignore[attr-defined]
            return JSONResponse({"ok": False, "reason": "page_not_claimed"}, status_code=200)

        if not funding.live_enabled():
            # DRY-RUN: record intent without calling Meta; the real subscribe runs when live.
            try:
                store.put_row(tid, _SUBS_COLL, page_id,
                              {"page_id": page_id, "status": "simulated", "fields": "leadgen"})
            except Exception:  # noqa: BLE001
                pass
            _audit(request, t, "ads.connect.subscribe", "page", page_id, {"status": "simulated"})
            return JSONResponse({"ok": True, "simulated": True, "status": "dry_run",
                                 "page_id": page_id})
        # LIVE: subscribe the app to the page's leadgen field.
        status_str, ok = "subscribe_failed", False
        try:
            creds = vault_adapter.get_connector_creds(tid, "meta")
            if not getattr(creds, "ok", False):
                return JSONResponse({"ok": False, "reason": "meta_not_configured"}, status_code=200)
            from .connectors.meta import MetaConnector
            res = await MetaConnector(creds).subscribe_leadgen(page_id)
            ok = bool(getattr(res, "ok", False))
            status_str = "subscribed" if ok else "subscribe_failed"
        except Exception:  # noqa: BLE001
            ok, status_str = False, "subscribe_failed"
        try:
            store.put_row(tid, _SUBS_COLL, page_id,
                          {"page_id": page_id, "status": status_str, "fields": "leadgen"})
        except Exception:  # noqa: BLE001
            pass
        _audit(request, t, "ads.connect.subscribe", "page", page_id, {"status": status_str})
        return JSONResponse({"ok": ok, "status": status_str, "page_id": page_id})

    # =========================================================================
    # FUNDING — vendor-own-card status + launch pre-check + manage deep-link (B13/B14/B15).
    # =========================================================================
    @router.get("/funding/status")
    async def connect_funding_status(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        try:
            st = await funding.funding_status(_tid(t))
        except Exception:  # noqa: BLE001
            st = {"ok": False, "model": funding.model(), "funded": None, "reason": "error"}
        return JSONResponse(st)

    @router.get("/funding/precheck")
    async def connect_funding_precheck(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        try:
            required = int(request.query_params.get("required_minor", "0") or 0)
        except Exception:  # noqa: BLE001
            required = 0
        try:
            res = await funding.launch_precheck(_tid(t), required_minor=required)
        except Exception:  # noqa: BLE001
            res = {"ok": True, "blocked": True, "status": "blocked_insufficient_funds",
                   "reason": "error"}
        return JSONResponse(res)

    @router.get("/funding/manage-link")
    async def connect_funding_manage(request: "Request") -> Any:
        t, err = _auth(request)
        if err:
            return err
        try:
            url = funding.manage_link(_tid(t))
        except Exception:  # noqa: BLE001
            url = ""
        return JSONResponse({"ok": bool(url), "url": url, "model": funding.model()})

    return router
