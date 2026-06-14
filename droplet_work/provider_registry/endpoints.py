"""provider_registry.endpoints — the connector API (W4 mount).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §8 (endpoints + flags) + §14 W4 (mount via the proven
`build_router(...)` guarded pattern) + §6 (security model: token-derived tenant, super-admin/
vendor entitlement scoping, PIN step-up reveal, SSRF guard on self-hosted, audit, legacy-pw
exclusion) + §2c (capability resolution).

⚠ THE MOUNT SURFACE — token-deriving `build_router(resolve_tenant, can, need_auth, firewall)`:
caller.py mounts ONLY this (the workflow-studio / media-gen / forms settled pattern). tenant_id
is ALWAYS `resolve_tenant(request)["tenant_id"]` (token-derived), NEVER a body/query field — so a
caller can never pass tenant_id=<victim>. There is NO body-tenant "bare router" here at all (unlike
media_gen, which kept a decoupled introspection router) — every route on this module derives the
tenant from the token, so there is nothing unsafe to accidentally mount.

TWO ROLE SURFACES on one router (the §8 table):
  * SUPER-ADMIN (`/admin/providers/*`)  — gated by the injected `require_super_admin` (= is_admin
    AND non-legacy-auth; the static `FamitCall2026` bearer is REJECTED here, control-security #1).
    The super-admin manages platform `_global` defs + any tenant's defs, can register a
    self-hosted endpoint (SSRF-validated), and can reveal/rotate any credential.
  * VENDOR / TENANT (`/providers/byo/*`) — gated by `resolve_tenant` (any authenticated tenant).
    A vendor brings their OWN hosted-api key (scope='integration'), can reveal/rotate ONLY their
    own integration credential (PIN step-up), and CANNOT register a self-hosted endpoint or reveal
    a platform ('ai_provider') key.

SECURITY (every control from §6):
  * tenant from token (resolve_tenant) — never body. is_admin never body-derived.
  * RLS via store.py (is_admin=False on the vendor surface) / store write with is_admin=True only on
    the super-admin surface (the admin GUC leg — lets a super-admin touch `_global`).
  * SSRF guard: a self_hosted base_url is split to host+port+scheme and run through
    ssrf_guard.validate_endpoint BEFORE the def can be created / before any test-connection fetch.
    A vendor may register ONLY hosted_api (self_hosted is super-admin-only, §6).
  * field-map injection: a custom_field_map def's request/response maps are validated at write-time
    via adapter.validate_field_map (JSONPath-only, depth-limited, no-eval) — a bad map → 400.
  * reveal: PIN step-up via firewall.consume_reveal_step_up — the X-Step-Up header carries a
    provider.reveal token (60s TTL, aud=provider_def_id, SINGLE-USE jti). Replay → 403. A vendor
    may reveal only an 'integration' credential they own; an 'ai_provider' (platform) credential →
    403 even for the owning tenant. Super-admin may reveal any (audited).
  * audit: every create/update/delete/reveal/rotate/test → audit_hook(...) (best-effort; the
    plaintext is NEVER in the audit meta).
  * legacy-pw exclusion: the super-admin surface uses the injected require_super_admin which already
    excludes the static password (caller.py:723 `_is_super_admin`).

DORMANT until mounted (W4) AND flag PROVIDER_REGISTRY_ENABLED on. FastAPI is the only optional
import; its absence degrades build_router to return None (never an ImportError at package import) —
the exact pattern of media_gen.router / creative.video_studio.endpoints.

NEVER imports agent.py. Does ZERO network I/O at import. test-connection / health do an
SSRF-guarded outbound probe ONLY when invoked (never a generation endpoint — §2f).
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from . import admin_store, adapter, config, credentials, health, registry, ssrf_guard, store
from .schema import (
    AuthScheme,
    CredentialScope,
    ProviderDef,
    ProviderType,
)

_log = logging.getLogger("provider_registry.endpoints")

try:
    from fastapi import APIRouter, Request  # type: ignore
    from fastapi.responses import JSONResponse  # type: ignore
    _HAVE_FASTAPI = True
except Exception:  # noqa: BLE001 — FastAPI optional at scaffold time
    APIRouter = None  # type: ignore
    Request = None  # type: ignore
    JSONResponse = None  # type: ignore
    _HAVE_FASTAPI = False


# ---------------------------------------------------------------------------
# helpers (pure; no I/O).
# ---------------------------------------------------------------------------
def _def_public_dict(d: ProviderDef) -> dict:
    """A JSON-able, NON-SECRET view of a provider definition for the UI/list. NEVER includes a
    credential. Enums are emitted as their string value."""
    def _v(x):
        return x.value if hasattr(x, "value") else x
    return {
        "id": d.id,
        "tenant_id": d.tenant_id,
        "is_global": d.is_global,
        "slug": d.slug,
        "display_name": d.display_name,
        "provider_type": _v(d.provider_type),
        "capabilities": list(d.capabilities or []),
        "base_url": d.base_url,
        "auth_scheme": _v(d.auth_scheme),
        "auth_header_name": d.auth_header_name,
        "transform_type": _v(d.transform_type),
        "named_provider": d.named_provider,
        "model_default": d.model_default,
        "cost_per_unit_micros": d.cost_per_unit_micros,
        "cost_unit": d.cost_unit,
        "health_check_path": d.health_check_path,
        "priority": d.priority,
        "rate_limit_rpm": d.rate_limit_rpm,
        "is_enabled": d.is_enabled,
        "is_platform_default": d.is_platform_default,
        "created_at": str(d.created_at) if d.created_at else None,
        "updated_at": str(d.updated_at) if d.updated_at else None,
    }


def _split_base_url(base_url: str):
    """Split a base_url into (host, port, scheme) WITHOUT trusting a pre-assembled URL for the
    security decision — the SSRF guard re-validates host+port+scheme separately (§6). Returns
    (host, port, scheme) or (None, 0, '') if unparseable."""
    try:
        from urllib.parse import urlsplit
        parts = urlsplit((base_url or "").strip())
    except Exception:  # noqa: BLE001
        return None, 0, ""
    scheme = (parts.scheme or "").lower()
    host = parts.hostname or ""
    port = parts.port or (443 if scheme == "https" else (80 if scheme == "http" else 0))
    return host, port, scheme


def _enum_str(x, default: str) -> str:
    return x.value if hasattr(x, "value") else (str(x) if x else default)


def _is_self_hosted(provider_type) -> bool:
    return _enum_str(provider_type, "") == ProviderType.SELF_HOSTED.value


def _validate_self_hosted_ssrf(base_url: str) -> ssrf_guard.Decision:
    """Run the SSRF gate on a self-hosted base_url (§6 / §2e). Returns the Decision (truthy iff
    safe). The endpoint maps a falsey Decision to a 400 with the precise reason."""
    host, port, scheme = _split_base_url(base_url)
    if not host:
        return ssrf_guard.Decision(False, reason="unparseable_base_url")
    allow = config.registry_config().get("ssrf_allow_hosts") or []
    return ssrf_guard.validate_endpoint(host, port or 443, scheme or "https", allow_hosts=allow)


def _validate_field_maps(fields: dict) -> Optional[str]:
    """If the def is a custom_field_map, validate the request/response maps (JSONPath-only,
    no-eval, depth-limited). Returns an error string on failure, else None."""
    tt = _enum_str(fields.get("transform_type"), "openai_compat")
    if tt != "custom_field_map":
        return None
    try:
        adapter.validate_field_map(fields.get("request_field_map"))
        adapter.validate_field_map(fields.get("response_field_map"))
    except Exception as exc:  # noqa: BLE001 — validate_field_map raises FieldMapError
        return f"invalid field_map: {exc}"
    return None


# A curated set of provider-def fields a write may carry (mirrors store._DEF_WRITE_COLS). The
# endpoint extracts ONLY these from the body — tenant_id / created_by / id / timestamps are
# server-set, never body-derived.
_BODY_DEF_FIELDS = (
    "slug", "display_name", "provider_type", "capabilities", "base_url", "auth_scheme",
    "auth_header_name", "auth_value_tmpl", "transform_type", "named_provider",
    "request_field_map", "response_field_map", "model_default", "cost_per_unit_micros",
    "cost_unit", "health_check_path", "health_interval_s", "priority", "rate_limit_rpm",
    "is_enabled", "is_platform_default",
)


def _extract_def_fields(body: dict) -> dict:
    out = {}
    for k in _BODY_DEF_FIELDS:
        if k in body:
            out[k] = body[k]
    return out


def _real_probe(d: ProviderDef, key: str = "") -> tuple:
    """The REAL test-connection / health probe: an SSRF-guarded, NO-generation GET against the
    provider's health/list-models path (§2f — NEVER a generation endpoint). Returns
    (healthy: bool, latency_ms: int, detail: str). NEVER raises; degrades to (False, 0, reason).

    httpx/requests are optional; if neither is present the probe reports a clean
    'http_client_unavailable' (the def is still created — the probe is a convenience)."""
    base = (d.base_url or "").rstrip("/")
    path = d.health_check_path or ("/v1/models" if _enum_str(d.transform_type, "") == "openai_compat"
                                   else "/health")
    url = base + (path if path.startswith("/") else "/" + path)
    host, port, scheme = _split_base_url(d.base_url or "")
    if not host:
        return False, 0, "unparseable_base_url"
    # SSRF gate the target host (self-hosted is the dangerous surface; hosted is gated by https +
    # the optional allowlist). allow_redirects=False is enforced below + redirects re-validated.
    allow = config.registry_config().get("ssrf_allow_hosts") or []
    dec = ssrf_guard.validate_endpoint(host, port or 443, scheme or "https", allow_hosts=allow)
    if not dec.ok:
        return False, 0, f"ssrf_blocked:{dec.reason}"
    # auth header (so a Bearer-gated /v1/models readiness probe works) via the adapter's scheme.
    headers = {}
    try:
        headers, _qp = adapter._auth_headers(d, key)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        headers = {}
    import time as _time
    t0 = _time.time()
    try:
        import httpx  # type: ignore
        with httpx.Client(follow_redirects=False,
                          timeout=httpx.Timeout(ssrf_guard.CONNECT_TIMEOUT_S,
                                                read=ssrf_guard.READ_TIMEOUT_S)) as cli:
            resp = cli.get(url, headers=headers)
            # a 3xx must be re-validated, never auto-followed (the metadata-redirect bypass).
            if 300 <= resp.status_code < 400:
                loc = resp.headers.get("location", "")
                rdec = ssrf_guard.revalidate_redirect_location(loc, allow_hosts=allow)
                if not rdec.ok:
                    return False, int((_time.time() - t0) * 1000), f"redirect_blocked:{rdec.reason}"
            healthy = 200 <= resp.status_code < 500 and resp.status_code != 401  # reachable
            lat = int((_time.time() - t0) * 1000)
            return healthy, lat, f"http_{resp.status_code}"
    except Exception as exc:  # noqa: BLE001 — any failure = unhealthy, with a reason
        return False, int((_time.time() - t0) * 1000), f"probe_error:{type(exc).__name__}"


# ---------------------------------------------------------------------------
# build_router — the AUTHENTICATED mount surface (the one caller.py wires, W4).
# ---------------------------------------------------------------------------
def build_router(resolve_tenant: "Callable", can: "Callable", need_auth: "Callable",
                 forbidden: "Callable", *, require_super_admin: "Callable" = None,
                 firewall: Any = None, audit: "Callable" = None) -> Any:
    """Build the provider-registry router, injecting caller.py's auth helpers.

      resolve_tenant(request) -> {"tenant_id","role","is_admin",...}|None  (token-derived identity)
      can(t, action) -> bool                                              (RBAC; "write" mutations)
      need_auth() -> Response(401) ; forbidden(msg) -> Response(403)
      require_super_admin(request) -> tenant dict | Response               (the /admin/* gate;
                                       excludes legacy-pw — control-security #1). If None is
                                       passed, the /admin/* routes self-gate on t.is_admin +
                                       can(t,"manage_tenants") as a safe fallback.
      firewall -> the firewall module (for consume_reveal_step_up / mint_reveal_step_up). If absent,
                  reveal/rotate fail-closed (403 step-up-unavailable) — never an open reveal.
      audit(request, tenant, action, object_type, object_id, meta) -> None (best-effort).

    Returns an APIRouter, or None if FastAPI is absent. The router itself is harmless if mounted
    while the flag is OFF: every route first checks config.is_enabled() and 404s when off (so even
    a mounted router is dormant/not-active until the flag flips — defense in depth over the
    mount-guard in caller.py).
    """
    if not _HAVE_FASTAPI:
        return None

    # PREFIX = /provider-registry (NOT the bare /providers). caller.py ALREADY has a live
    # `@app.get("/providers")` (the legacy LLM-router provider list this framework will later
    # STRANGLE, plan §3). Mounting our list at the bare /providers would be shadowed by that
    # earlier-registered route (FastAPI matches first-registered). Using the registry's OWN
    # namespace keeps W4 fully ISOLATED + collision-free; the FE maps to /provider-registry/*.
    router = APIRouter(prefix="/provider-registry", tags=["provider-registry"])

    def _tid(t: dict) -> str:
        return str((t or {}).get("tenant_id") or "")

    async def _body(request) -> dict:
        try:
            b = await request.json()
            return b if isinstance(b, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _disabled():
        # flag OFF -> the registry is dormant: behave as if the feature does not exist (404).
        return JSONResponse({"error": "not_found"}, status_code=404)

    def _audit(request, t, action, object_type="provider", object_id="", meta=None):
        if audit is None:
            return
        try:
            audit(request, t, action, object_type, object_id, meta=meta)
        except Exception:  # noqa: BLE001
            pass

    def _admin_gate(request):
        """Resolve the super-admin tenant for /admin/providers/* — via the injected
        require_super_admin (preferred; excludes legacy-pw) or a safe self-gate fallback."""
        if require_super_admin is not None:
            t = require_super_admin(request)
            # require_super_admin returns a Response on failure, a dict on success.
            if not isinstance(t, dict):
                return None, t
            return t, None
        # Fallback self-gate (require_super_admin not injected): is_admin + manage_tenants.
        t = resolve_tenant(request)
        if not t:
            return None, need_auth()
        if not (t.get("is_admin") and can(t, "manage_tenants")):
            return None, forbidden("super-admin required")
        return t, None

    def _step_up_token(request) -> str:
        # The reveal step-up token rides the X-Step-Up header (the firewall convention).
        try:
            return (request.headers.get("x-step-up", "")
                    or request.headers.get("X-Step-Up", "") or "")
        except Exception:  # noqa: BLE001
            return ""

    # ===========================================================================================
    # VENDOR / TENANT surface — /providers (token-derived tenant; RLS is_admin=False).
    # ===========================================================================================

    @router.get("")
    async def list_providers(request: "Request", capability: str = "") -> Any:
        """GET /providers — the defs VISIBLE to this tenant (own + `_global`, RLS-scoped),
        entitlement-scoped, optionally filtered to one capability. Masked creds only."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        tid = _tid(t)
        defs = store.list_definitions(tid, capability=capability)
        # which of this tenant's defs have an active credential (masked, never decrypted).
        creds = {c.provider_def_id: c for c in store.list_credentials_masked(tid)}
        out = []
        for d in defs:
            row = _def_public_dict(d)
            c = creds.get(d.id)
            row["has_credential"] = c is not None
            row["credential_scope"] = (_enum_str(c.scope, "") if c else "")
            row["circuit"] = health.circuit_state(tid, d.id or "")
            out.append(row)
        return JSONResponse({"providers": out, "capability": capability or None})

    @router.get("/health")
    async def providers_health(request: "Request", capability: str = "") -> Any:
        """GET /providers/health — per-provider circuit state + a non-secret resolution diagnostic
        for the tenant (the live health badge). Never reveals a credential."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        tid = _tid(t)
        cap = capability or "text_gen"
        return JSONResponse(registry.resolve_status(tid, cap))

    @router.post("")
    async def create_provider(request: "Request") -> Any:
        """POST /providers — a VENDOR adds their OWN provider def. hosted_api ONLY (self_hosted is
        super-admin-only, §6). The credential (if supplied) is stored scope='integration'."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot add a provider")
        tid = _tid(t)
        body = await _body(request)
        fields = _extract_def_fields(body)
        # vendor surface: force hosted_api (a vendor may NEVER register a self-hosted endpoint).
        if _is_self_hosted(fields.get("provider_type")):
            return forbidden("self-hosted providers are super-admin only")
        fields["provider_type"] = fields.get("provider_type") or ProviderType.HOSTED_API.value
        # hosted base_url must be https (defense-in-depth — no plaintext key over http).
        host, _port, scheme = _split_base_url(fields.get("base_url", ""))
        if host and scheme != "https":
            return JSONResponse({"error": "hosted base_url must be https"}, status_code=400)
        fm_err = _validate_field_maps(fields)
        if fm_err:
            return JSONResponse({"error": fm_err}, status_code=400)
        try:
            row = store.create_definition(tid, fields, created_by=tid, is_admin=False)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if row is None:
            return JSONResponse({"error": "create failed"}, status_code=400)
        new_def = ProviderDef.from_any(row)
        # optionally store the BYO key in the same call (scope='integration').
        key = (body.get("api_key") or body.get("credential") or "").strip()
        cred_meta = None
        if key:
            cred_meta = _store_credential(tid, new_def, key, scope="integration", is_admin=False)
            if isinstance(cred_meta, JSONResponse):
                # def created but key store failed — surface it (def remains; user can retry key).
                _audit(request, t, "provider.create", object_id=new_def.id or "",
                       meta={"slug": new_def.slug, "credential": "store_failed"})
                return cred_meta
        _audit(request, t, "provider.create", object_id=new_def.id or "",
               meta={"slug": new_def.slug, "type": _enum_str(new_def.provider_type, ""),
                     "credential": "stored" if key else "none"})
        out = _def_public_dict(new_def)
        out["has_credential"] = cred_meta is not None
        return JSONResponse(out, status_code=201)

    @router.put("/{provider_id}")
    async def update_provider(provider_id: str, request: "Request") -> Any:
        """PUT /providers/{id} — update a def the tenant OWNS (RLS scopes the row). Whitelisted
        columns only; the credential is updated via the /credential route, not here."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot edit a provider")
        tid = _tid(t)
        existing = store.get_definition(tid, provider_id)
        if existing is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        # a vendor may not edit a `_global` platform def (RLS would block the write anyway).
        if existing.is_global:
            return forbidden("platform-managed provider — super-admin only")
        body = await _body(request)
        fields = _extract_def_fields(body)
        if _is_self_hosted(fields.get("provider_type")):
            return forbidden("self-hosted providers are super-admin only")
        fm_err = _validate_field_maps({**existing.__dict__, **fields})
        if fm_err:
            return JSONResponse({"error": fm_err}, status_code=400)
        try:
            row = store.update_definition(tid, provider_id, fields, is_admin=False)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if row is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        _audit(request, t, "provider.update", object_id=provider_id,
               meta={"fields": sorted(fields.keys())})
        return JSONResponse(_def_public_dict(ProviderDef.from_any(row)))

    @router.delete("/{provider_id}")
    async def delete_provider(provider_id: str, request: "Request") -> Any:
        """DELETE /providers/{id} — delete a def the tenant OWNS (cascades its creds). `_global`
        is super-admin only."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot delete a provider")
        tid = _tid(t)
        existing = store.get_definition(tid, provider_id)
        if existing is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if existing.is_global:
            return forbidden("platform-managed provider — super-admin only")
        try:
            ok = store.delete_definition(tid, provider_id, is_admin=False)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if not ok:
            return JSONResponse({"error": "not_found"}, status_code=404)
        _audit(request, t, "provider.delete", object_id=provider_id, meta={"slug": existing.slug})
        return JSONResponse({"deleted": True, "id": provider_id})

    @router.post("/{provider_id}/credential")
    async def set_credential(provider_id: str, request: "Request") -> Any:
        """POST /providers/{id}/credential — store an AAD-encrypted key for a def the tenant owns.
        Vendor scope is always 'integration' (their own, revealable). Rotation-aware (deactivates
        the prior active version). NEVER echoes the plaintext."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot set a credential")
        tid = _tid(t)
        d = store.get_definition(tid, provider_id)
        if d is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        # a vendor stores a key for THEIR OWN def (a `_global` platform def's key is super-admin).
        if d.is_global:
            return forbidden("platform credential — super-admin only")
        body = await _body(request)
        key = (body.get("api_key") or body.get("credential") or "").strip()
        if not key:
            return JSONResponse({"error": "credential required"}, status_code=400)
        res = _store_credential(tid, d, key, scope="integration", is_admin=False)
        if isinstance(res, JSONResponse):
            return res
        _audit(request, t, "provider.credential.set", object_id=provider_id,
               meta={"scope": "integration", "key_masked": credentials.mask(key)})
        return JSONResponse({"stored": True, "provider_id": provider_id,
                             "key_masked": credentials.mask(key), "scope": "integration"})

    @router.post("/{provider_id}/reveal")
    async def reveal_credential(provider_id: str, request: "Request") -> Any:
        """POST /providers/{id}/reveal — reveal the plaintext of a credential the tenant owns.
        Requires a provider.reveal PIN step-up (X-Step-Up header; 60s, aud-bound, single-use jti).
        A vendor may reveal ONLY an 'integration' (own) credential — an 'ai_provider' (platform)
        credential is masked-only (403). Replay of the step-up jti → 403. Audited either way."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        tid = _tid(t)
        d = store.get_definition(tid, provider_id)
        if d is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        cred = store.get_active_credential(tid, provider_id)
        if cred is None:
            return JSONResponse({"error": "no_credential"}, status_code=404)
        # reveal POLICY (§6): a vendor may reveal ONLY their own 'integration' scope key.
        if not cred.is_revealable_by_vendor:
            _audit(request, t, "provider.reveal.denied", object_id=provider_id,
                   meta={"reason": "platform_scope"})
            return forbidden("platform-managed credential cannot be revealed")
        denied = _consume_reveal(request, tid, provider_id)
        if denied is not None:
            _audit(request, t, "provider.reveal.denied", object_id=provider_id,
                   meta={"reason": "step_up"})
            return denied
        try:
            plaintext = credentials.decrypt_credential(cred)
        except Exception:  # noqa: BLE001 — decrypt failure (tamper/cross-tenant) → 409, no plaintext
            _audit(request, t, "provider.reveal.error", object_id=provider_id,
                   meta={"reason": "decrypt_failed"})
            return JSONResponse({"error": "decrypt_failed"}, status_code=409)
        _audit(request, t, "provider.reveal", object_id=provider_id,
               meta={"scope": _enum_str(cred.scope, ""), "key_masked": credentials.mask(plaintext)})
        # returned ONCE; the step-up jti is now consumed (single-use).
        return JSONResponse({"provider_id": provider_id, "credential": plaintext})

    @router.post("/{provider_id}/test")
    async def test_connection(provider_id: str, request: "Request") -> Any:
        """POST /providers/{id}/test — SSRF-guarded test-connection (NO generation, §2f): a
        health/list-models GET through the def's auth, updating the circuit breaker."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        tid = _tid(t)
        d = store.get_definition(tid, provider_id)
        if d is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return _run_test(tid, d)

    # ===========================================================================================
    # SUPER-ADMIN surface — /providers/admin (require_super_admin; is_admin=True writes touch
    # `_global`). NOTE: the prefix is /providers/admin (under this router's /providers prefix), and
    # the spec's logical name is /admin/providers — both reach the same gate. We expose it as
    # /providers/admin/* so the ONE router owns the whole namespace; the FE maps to it.
    # ===========================================================================================

    @router.get("/admin/all")
    async def admin_list_all(request: "Request", capability: str = "", tenant_id: str = "") -> Any:
        """GET /providers/admin/all — list defs ACROSS all tenants (+ `_global`) for the console."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        defs = admin_store.list_all_definitions(capability=capability, tenant_id=tenant_id)
        out = []
        for d in defs:
            row = _def_public_dict(d)
            row["circuit"] = health.circuit_state(d.tenant_id, d.id or "")
            out.append(row)
        return JSONResponse({"providers": out})

    @router.post("/admin")
    async def admin_create(request: "Request") -> Any:
        """POST /providers/admin — super-admin creates a def (may be `_global` platform-shared, or
        self_hosted SSRF-validated). is_admin=True → the admin RLS leg authorizes a `_global` write."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        body = await _body(request)
        fields = _extract_def_fields(body)
        # owner: a super-admin may create a `_global` platform def, OR a def for a specific tenant.
        owner = (body.get("owner_tenant_id") or body.get("tenant_id") or "_global").strip() or "_global"
        # SSRF gate a self-hosted endpoint BEFORE the row can exist (§6 / §2e).
        if _is_self_hosted(fields.get("provider_type")):
            if config.registry_config().get("ssrf_block_self_hosted"):
                return forbidden("self-hosted providers are disabled (kill switch)")
            dec = _validate_self_hosted_ssrf(fields.get("base_url", ""))
            if not dec.ok:
                return JSONResponse({"error": f"ssrf_blocked:{dec.reason}",
                                     "resolved_ips": dec.resolved_ips}, status_code=400)
        fm_err = _validate_field_maps(fields)
        if fm_err:
            return JSONResponse({"error": fm_err}, status_code=400)
        try:
            row = store.create_definition(owner, fields,
                                          created_by=_tid(t) or "super-admin", is_admin=True)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if row is None:
            return JSONResponse({"error": "create failed"}, status_code=400)
        new_def = ProviderDef.from_any(row)
        # an optional platform credential is stored scope='ai_provider' (masked-only to vendors).
        key = (body.get("api_key") or body.get("credential") or "").strip()
        cred_meta = None
        if key:
            scope = (body.get("credential_scope") or "ai_provider").strip() or "ai_provider"
            cred_meta = _store_credential(owner, new_def, key, scope=scope, is_admin=True)
            if isinstance(cred_meta, JSONResponse):
                return cred_meta
        _audit(request, t, "provider.admin.create", object_id=new_def.id or "",
               meta={"owner": owner, "slug": new_def.slug,
                     "type": _enum_str(new_def.provider_type, ""),
                     "credential": "stored" if key else "none"})
        out = _def_public_dict(new_def)
        out["has_credential"] = cred_meta is not None
        return JSONResponse(out, status_code=201)

    @router.put("/admin/{provider_id}")
    async def admin_update(provider_id: str, request: "Request") -> Any:
        """PUT /providers/admin/{id} — super-admin updates ANY def (incl. `_global`)."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        existing = admin_store.get_any_definition(provider_id)
        if existing is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        body = await _body(request)
        fields = _extract_def_fields(body)
        if _is_self_hosted(fields.get("provider_type")) or _is_self_hosted(existing.provider_type):
            new_url = fields.get("base_url", existing.base_url)
            if new_url and not config.registry_config().get("ssrf_block_self_hosted"):
                dec = _validate_self_hosted_ssrf(new_url)
                if not dec.ok:
                    return JSONResponse({"error": f"ssrf_blocked:{dec.reason}"}, status_code=400)
        fm_err = _validate_field_maps({**existing.__dict__, **fields})
        if fm_err:
            return JSONResponse({"error": fm_err}, status_code=400)
        try:
            row = store.update_definition(existing.tenant_id, provider_id, fields, is_admin=True)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if row is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        _audit(request, t, "provider.admin.update", object_id=provider_id,
               meta={"owner": existing.tenant_id, "fields": sorted(fields.keys())})
        return JSONResponse(_def_public_dict(ProviderDef.from_any(row)))

    @router.delete("/admin/{provider_id}")
    async def admin_delete(provider_id: str, request: "Request") -> Any:
        """DELETE /providers/admin/{id} — super-admin deletes ANY def (incl. `_global`)."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        existing = admin_store.get_any_definition(provider_id)
        if existing is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            ok = store.delete_definition(existing.tenant_id, provider_id, is_admin=True)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if not ok:
            return JSONResponse({"error": "not_found"}, status_code=404)
        _audit(request, t, "provider.admin.delete", object_id=provider_id,
               meta={"owner": existing.tenant_id, "slug": existing.slug})
        return JSONResponse({"deleted": True, "id": provider_id})

    @router.post("/admin/{provider_id}/reveal")
    async def admin_reveal(provider_id: str, request: "Request") -> Any:
        """POST /providers/admin/{id}/reveal — super-admin reveals ANY credential (any scope),
        PIN step-up + single-use jti, audited. The owner tenant may be passed in the body."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        body = await _body(request)
        owner = (body.get("owner_tenant_id") or "").strip()
        cred = admin_store.get_any_credential(provider_id, owner_tenant_id=owner)
        if cred is None:
            return JSONResponse({"error": "no_credential"}, status_code=404)
        denied = _consume_reveal(request, _tid(t), provider_id)
        if denied is not None:
            _audit(request, t, "provider.admin.reveal.denied", object_id=provider_id,
                   meta={"reason": "step_up"})
            return denied
        try:
            plaintext = credentials.decrypt_credential(cred)
        except Exception:  # noqa: BLE001
            _audit(request, t, "provider.admin.reveal.error", object_id=provider_id,
                   meta={"reason": "decrypt_failed"})
            return JSONResponse({"error": "decrypt_failed"}, status_code=409)
        _audit(request, t, "provider.admin.reveal", object_id=provider_id,
               meta={"owner": cred.tenant_id, "scope": _enum_str(cred.scope, ""),
                     "key_masked": credentials.mask(plaintext)})
        return JSONResponse({"provider_id": provider_id, "credential": plaintext,
                             "owner_tenant_id": cred.tenant_id})

    @router.post("/admin/{provider_id}/test")
    async def admin_test(provider_id: str, request: "Request") -> Any:
        """POST /providers/admin/{id}/test — SSRF-guarded test-connection for any def."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        d = admin_store.get_any_definition(provider_id)
        if d is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        # decrypt the platform credential (if any) so a Bearer-gated readiness probe authenticates.
        key = ""
        cred = admin_store.get_any_credential(provider_id, owner_tenant_id=d.tenant_id)
        if cred is not None:
            try:
                key = credentials.decrypt_credential(cred)
            except Exception:  # noqa: BLE001 — probe without auth if decrypt fails
                key = ""
        return _run_test(d.tenant_id, d, key=key, is_admin=True)

    @router.get("/admin/health")
    async def admin_health(request: "Request") -> Any:
        """GET /providers/admin/health — per-provider circuit state across all tenants."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        defs = admin_store.list_all_definitions()
        out = [{
            "id": d.id, "tenant_id": d.tenant_id, "slug": d.slug,
            "display_name": d.display_name, "is_enabled": d.is_enabled,
            "circuit": health.circuit_state(d.tenant_id, d.id or ""),
        } for d in defs]
        return JSONResponse({"providers": out})

    # ---------------- shared internal helpers (closures over the injected deps) ----------------
    def _store_credential(tid: str, d: ProviderDef, key: str, *, scope: str, is_admin: bool):
        """Encrypt + persist a credential; returns a JSONResponse error or a meta dict."""
        try:
            enc = credentials.encrypt_credential(tid, d.id or "", key)
        except credentials.CredentialError as exc:
            return JSONResponse({"error": f"encrypt_unavailable:{type(exc).__name__}"},
                                status_code=503)
        try:
            return store.upsert_credential(tid, d.id or "", enc, scope=scope, is_admin=is_admin)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    def _consume_reveal(request, expected_sub: str, provider_def_id: str):
        """Verify + CONSUME a provider.reveal step-up. Returns a JSONResponse(403) to RETURN on
        denial, or None to PROCEED. Fail-closed if the firewall is unavailable (never an open
        reveal)."""
        if firewall is None or not hasattr(firewall, "consume_reveal_step_up"):
            return JSONResponse({"error": "step_up_unavailable", "scope": "provider.reveal"},
                                status_code=403)
        token = _step_up_token(request)
        if not token:
            # tell the client to mint one (the FE then PIN-pads → /providers/{id}/reveal-init).
            return JSONResponse({"error": "step_up_required", "scope": "provider.reveal"},
                                status_code=403)
        claims = firewall.consume_reveal_step_up(token, provider_def_id, expected_sub)
        if claims is None:
            return JSONResponse({"error": "step_up_invalid", "scope": "provider.reveal"},
                                status_code=403)
        return None

    def _run_test(tid: str, d: ProviderDef, key: str = "", is_admin: bool = False):
        """Run the SSRF-guarded probe + update the in-memory breaker + best-effort health-log.
        `is_admin` is True on the super-admin test path (the health-row write then rides the admin
        RLS leg so a super-admin can log a probe against any tenant's def)."""
        healthy, latency_ms, detail = _real_probe(d, key=key)
        try:
            if healthy:
                health.record_success(tid, d.id or "")
            else:
                health.record_failure(tid, d.id or "", detail)
        except Exception:  # noqa: BLE001
            pass
        try:
            store.write_health_row(tid, d.id or "", healthy, latency_ms, detail, is_admin=is_admin)
        except Exception:  # noqa: BLE001
            pass
        return JSONResponse({
            "provider_id": d.id, "slug": d.slug, "healthy": healthy,
            "latency_ms": latency_ms, "detail": detail,
            "circuit": health.circuit_state(tid, d.id or ""),
        })

    # mint-a-reveal-token helper endpoint (the FE PIN-pad posts the PIN to the firewall verify, gets
    # a generic step-up, then asks here for a provider.reveal token aud-bound to this def).
    @router.post("/{provider_id}/reveal-init")
    async def reveal_init(provider_id: str, request: "Request") -> Any:
        """POST /providers/{id}/reveal-init — mint a 60s, aud-bound, single-use provider.reveal
        step-up token for THIS def, after a recent PIN (the FE flow: verify-pin → reveal-init →
        reveal). Bound to sub=tenant (F3). Returns the token the FE sends as X-Step-Up to /reveal."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if firewall is None or not hasattr(firewall, "mint_reveal_step_up"):
            return JSONResponse({"error": "step_up_unavailable"}, status_code=503)
        tid = _tid(t)
        # the def must be visible to this tenant (own or `_global`) — RLS via store.
        d = store.get_definition(tid, provider_id)
        if d is None:
            # super-admins resolve via admin_store (they can reveal any).
            if t.get("is_admin"):
                d2 = admin_store.get_any_definition(provider_id)
                if d2 is None:
                    return JSONResponse({"error": "not_found"}, status_code=404)
            else:
                return JSONResponse({"error": "not_found"}, status_code=404)
        minted = firewall.mint_reveal_step_up(tid, provider_id)
        if minted is None:
            return JSONResponse({"error": "step_up_unavailable"}, status_code=503)
        _audit(request, t, "provider.reveal.init", object_id=provider_id, meta={})
        return JSONResponse(minted)

    return router
