"""trunk_registry.endpoints — the telephony trunk-registry API (T3 mount).

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §5 (T3 row: "Additive /trunk-registry/* + /trunks/byo/*
guarded mount; /test-call rate-limited (<=3/hr); DELETE soft-disables + refuses `_global`/env trunk;
POST /quarantine-did kill switch") + §3 red-team B1/D/E/F + §4 (the FE surface this serves) + §6
(security model: token-derived tenant, super-admin/vendor entitlement scoping, PIN step-up reveal,
SSRF guard on the BYO sip_host, audit, legacy-pw exclusion via require_super_admin).

A column-for-column TWIN of provider_registry/endpoints.py — the SAME token-deriving
`build_router(resolve_tenant, can, need_auth, forbidden, require_super_admin=, firewall=, audit=)`
guarded-mount pattern caller.py already wires for provider-registry / media-gen / booking / forms /
workflow / video-studio. caller.py mounts ONLY this; tenant_id is ALWAYS
`resolve_tenant(request)["tenant_id"]` (token-derived), NEVER a body/query field — so a caller can
never pass tenant_id=<victim>. There is NO body-tenant "bare router" here at all.

TWO ROLE SURFACES on one router (the §4 + §6 table):
  * VENDOR / TENANT (`/trunk-registry/*` + `/trunks/byo/*`) — gated by `resolve_tenant` (any
    authenticated tenant). A vendor adds their OWN BYO-number SIP trunk (creds scope='integration',
    SSRF-validated sip_host), reveals/rotates ONLY their own integration credential (PIN step-up),
    soft-disables (the DEFAULT 'remove'), places a SINGLE founder test call (rate-limited <=3/hr),
    and quarantines a DID (the kill switch). A vendor may NOT register a gsm_gateway / direct_sip
    trunk (super-admin only) and may NEVER hard-delete a `_global`/env-protected trunk.
  * SUPER-ADMIN (`/trunk-registry/admin/*`) — gated by the injected `require_super_admin` (= is_admin
    AND non-legacy-auth; the static `FamitCall2026` bearer is REJECTED here, control-security #1).
    The super-admin manages platform `_global` trunks + any tenant's trunks, registers a
    gsm_gateway / direct_sip trunk, and reveals any credential (audited).

SECURITY (every control from §6):
  * tenant from token (resolve_tenant) — never body. is_admin never body-derived.
  * RLS via store.py (is_admin=False on the vendor surface) / admin_store + store write is_admin=True
    only on the super-admin surface (the admin GUC leg — lets a super-admin touch `_global`).
  * SSRF guard: a BYO sip_host is run through ssrf_guard.validate_endpoint BEFORE the trunk row can be
    created (a self-hosted GSM gateway on a LAN, or a SIP provider host — the CVE-2025-59146 surface).
  * RED-TEAM D — DELETE default = soft_disable_trunk. A genuine hard-delete is PIN-gated + REFUSES the
    env-protected (LIVEKIT_SIP_TRUNK_ID) / `_global` trunk (the un-deletable DB trigger is the backstop).
  * RED-TEAM B1 — campaign-eligibility is the DB-derived `is_campaign_eligible` column; a vendor can
    NEVER user-set it (it is excluded from the write whitelist). The registry choke-point enforces it.
  * RED-TEAM F — /test-call is rate-limited (<=3/hr/trunk, in-process), founder-typed destination,
    NEVER an auto-dial. It is the ONLY non-campaign originate this system exposes — and it does NOT
    dial here; it returns a single dial-intent the caller.py /run path executes (T5). At T3 the route
    is present + gated + dormant (flag OFF -> 404); the wired single-dial lands with the strangler.
  * RED-TEAM E — POST /quarantine-did is the real-time per-DID kill switch independent of the master
    flag's rotation (rest a number now).
  * reveal: PIN step-up via firewall.consume_reveal_step_up — the X-Step-Up header carries a
    trunk.reveal token (60s TTL, aud=trunk_id, SINGLE-USE jti). Replay -> 403. A vendor may reveal
    only an 'integration' credential they own; a 'platform' credential -> 403. Super-admin may reveal
    any (audited).
  * audit: every create/update/delete/reveal/rotate/test/quarantine -> audit_hook(...) (best-effort;
    the SIP password is NEVER in the audit meta).
  * legacy-pw exclusion: the super-admin surface uses the injected require_super_admin which already
    excludes the static password (caller.py `_is_super_admin`).

DORMANT until mounted (T3) AND flag TRUNK_REGISTRY_ENABLED on. FastAPI is the only optional import;
its absence degrades build_router to return None (never an ImportError at package import) — the exact
pattern of provider_registry.endpoints / media_gen.router / creative.video_studio.endpoints.

NEVER imports agent.py. Does ZERO network I/O at import. The test-call probe / LiveKit-sync run an
outbound API call ONLY when invoked behind the flag.
"""
from __future__ import annotations

import logging
import threading
import time as _time
from typing import Any, Callable, Optional

from . import admin_store, config, credentials, registry, rotation, ssrf_guard, store
from .schema import (
    CredentialScope,
    Direction,
    SipTrunk,
    TrunkType,
)

_log = logging.getLogger("trunk_registry.endpoints")

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
# /test-call rate-limit (RED-TEAM F): in-process, per-trunk, <=N/hour. The box is uvicorn
# --workers 1 (ratelimit.py:13) so an in-process counter is authoritative (the same call the
# concurrency module makes). A founder hammering 'Test' must NOT reputation-damage the DID.
# ---------------------------------------------------------------------------
_TESTCALL_LOCK = threading.Lock()
_TESTCALL_HITS: dict = {}  # (tenant::trunk) -> [unix_ts, ...] within the rolling hour
_TESTCALL_MAX_PER_HOUR = 3
_TESTCALL_WINDOW_S = 3600


def _testcall_allowed(tenant_id: str, trunk_id: str, *, now: Optional[float] = None) -> tuple:
    """Return (allowed: bool, remaining: int). Prunes the rolling-hour window. Never raises."""
    now = now if now is not None else _time.time()
    key = f"{tenant_id}::{trunk_id}"
    with _TESTCALL_LOCK:
        hits = [t for t in _TESTCALL_HITS.get(key, []) if now - t < _TESTCALL_WINDOW_S]
        if len(hits) >= _TESTCALL_MAX_PER_HOUR:
            _TESTCALL_HITS[key] = hits
            return False, 0
        hits.append(now)
        _TESTCALL_HITS[key] = hits
        return True, max(0, _TESTCALL_MAX_PER_HOUR - len(hits))


# ---------------------------------------------------------------------------
# helpers (pure; no I/O).
# ---------------------------------------------------------------------------
def _enum_str(x, default: str = "") -> str:
    return x.value if hasattr(x, "value") else (str(x) if x else default)


def _trunk_public_dict(t: SipTrunk) -> dict:
    """A JSON-able, NON-SECRET view of a trunk for the UI/list. NEVER includes a SIP password.
    Enums emit as their string value. Surfaces the DB-derived is_campaign_eligible gate +
    quarantine + the compliance fields the FE compliance badge reads (§4)."""
    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "is_global": t.is_global,
        "slug": t.slug,
        "display_name": t.display_name,
        "trunk_type": _enum_str(t.trunk_type),
        "provider_vendor": t.provider_vendor,
        "direction": _enum_str(t.direction),
        "sip_host": t.sip_host,
        "sip_port": t.sip_port,
        "transport": _enum_str(t.transport),
        "encryption": _enum_str(t.encryption),
        "auth_username": t.auth_username,
        "allowed_addresses": list(t.allowed_addresses or []),
        "did_pool": list(t.did_pool or []),
        "caller_id": t.caller_id,
        "max_concurrency": t.max_concurrency,
        "cost_per_minute_paise": t.cost_per_minute_paise,
        # compliance gates (RED-TEAM B1) — is_campaign_eligible is DB-DERIVED (read-only).
        "is_140_series": t.is_140_series,
        "dlt_entity_id": t.dlt_entity_id,
        "dlt_status": _enum_str(t.dlt_status),
        "per_did_daily_cap": t.per_did_daily_cap,
        "is_campaign_eligible": bool(getattr(t, "is_campaign_eligible", False)),
        "priority": t.priority,
        "rotation_strategy": _enum_str(t.rotation_strategy),
        "is_enabled": t.is_enabled,
        "is_test_verified": t.is_test_verified,
        "is_undeletable": t.is_undeletable,
        "is_quarantined": t.is_quarantined(),
        "quarantined_until": (str(t.quarantined_until) if t.quarantined_until else None),
        "livekit_trunk_id": t.livekit_trunk_id,
        "created_at": str(t.created_at) if t.created_at else None,
        "updated_at": str(t.updated_at) if t.updated_at else None,
    }


# Columns a write may carry (mirrors store._TRUNK_WRITE_COLS). The endpoint extracts ONLY these from
# the body — tenant_id / created_by / id / timestamps are server-set, never body-derived. NOTE:
# is_campaign_eligible (DB-GENERATED), is_undeletable (admin/seed-only) are intentionally ABSENT.
_BODY_TRUNK_FIELDS = (
    "slug", "display_name", "trunk_type", "provider_vendor", "direction", "sip_host", "sip_port",
    "transport", "encryption", "auth_username", "allowed_addresses", "did_pool", "caller_id",
    "max_concurrency", "cost_per_minute_paise", "is_140_series", "dlt_entity_id", "dlt_status",
    "per_did_daily_cap", "priority", "rotation_strategy", "is_enabled", "is_test_verified",
    "livekit_trunk_id",
)


def _extract_trunk_fields(body: dict) -> dict:
    return {k: body[k] for k in _BODY_TRUNK_FIELDS if k in body}


def _is_privileged_type(trunk_type) -> bool:
    """gsm_gateway / direct_sip are super-admin-only (§4/§6). A vendor may register ONLY a
    sip_provider trunk (their BYO-number CPaaS/SIP route)."""
    tt = _enum_str(trunk_type, "")
    return tt in (TrunkType.GSM_GATEWAY.value, TrunkType.DIRECT_SIP.value)


def _validate_sip_host_ssrf(host: str, port: int, transport: str) -> "ssrf_guard.Decision":
    """Run the SSRF gate on a BYO sip_host (§6). A host resolving to a metadata IP / RFC1918 /
    loopback is rejected before the trunk row can exist. transport tls -> https-class probe scheme,
    else http-class (the guard only cares about the resolved IP, not the app-layer scheme)."""
    if not host:
        return ssrf_guard.Decision(False, reason="missing_sip_host")
    scheme = "https" if (transport or "").lower() == "tls" else "http"
    allow = config.registry_config().get("ssrf_allow_hosts") or []
    return ssrf_guard.validate_endpoint(host, int(port or 5060), scheme, allow_hosts=allow)


# ---------------------------------------------------------------------------
# build_router — the AUTHENTICATED mount surface (the one caller.py wires, T3).
# ---------------------------------------------------------------------------
def build_router(resolve_tenant: "Callable", can: "Callable", need_auth: "Callable",
                 forbidden: "Callable", *, require_super_admin: "Callable" = None,
                 firewall: Any = None, audit: "Callable" = None,
                 livekit_client: Any = None, place_test_call: "Callable" = None) -> Any:
    """Build the trunk-registry router, injecting caller.py's auth helpers (the SAME contract as
    provider_registry.build_router, + two telephony-only optional seams).

      resolve_tenant(request) -> {"tenant_id","role","is_admin",...}|None  (token-derived identity)
      can(t, action) -> bool                                              (RBAC; "write" mutations)
      need_auth() -> Response(401) ; forbidden(msg) -> Response(403)
      require_super_admin(request) -> tenant dict | Response               (the /admin/* gate;
                                       excludes legacy-pw — control-security #1). If None, the
                                       /admin/* routes self-gate on is_admin + can(manage_tenants).
      firewall -> the firewall module (consume_reveal_step_up / mint_reveal_step_up). If absent,
                  reveal/rotate fail-closed (403 step-up-unavailable) — never an open reveal.
      audit(request, tenant, action, object_type, object_id, meta=) -> None (best-effort).
      livekit_client -> an injected async LiveKit Server-API client (for trunk SYNC/delete). Absent
                  at T3 -> the LiveKit-sync routes report 'livekit_unavailable' (DB row still made).
      place_test_call(tenant_id, trunk, did, destination) -> dict  -> the single founder test-dial
                  seam (wired at T5 via the caller.py /run path). Absent at T3 -> the route returns
                  a dial-intent only (NEVER auto-dials).

    Returns an APIRouter, or None if FastAPI is absent. The router is harmless if mounted while the
    flag is OFF: every route first checks config.is_enabled() and 404s when off (defense in depth)."""
    if not _HAVE_FASTAPI:
        return None

    # PREFIX = /trunk-registry (mirrors provider_registry's /provider-registry namespace choice —
    # NOT the bare /trunks, which could collide with a future legacy route). The BYO add lives at
    # /trunk-registry/byo/* (the §5 "/trunks/byo/*" path maps here under the one router). The FE
    # maps to /trunk-registry/*.
    router = APIRouter(prefix="/trunk-registry", tags=["trunk-registry"])

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

    def _audit(request, t, action, object_type="trunk", object_id="", meta=None):
        if audit is None:
            return
        try:
            audit(request, t, action, object_type, object_id, meta=meta)
        except Exception:  # noqa: BLE001
            pass

    def _admin_gate(request):
        """Resolve the super-admin tenant for /trunk-registry/admin/* — via the injected
        require_super_admin (preferred; excludes legacy-pw) or a safe self-gate fallback."""
        if require_super_admin is not None:
            t = require_super_admin(request)
            if not isinstance(t, dict):
                return None, t
            return t, None
        t = resolve_tenant(request)
        if not t:
            return None, need_auth()
        if not (t.get("is_admin") and can(t, "manage_tenants")):
            return None, forbidden("super-admin required")
        return t, None

    def _step_up_token(request) -> str:
        try:
            return (request.headers.get("x-step-up", "")
                    or request.headers.get("X-Step-Up", "") or "")
        except Exception:  # noqa: BLE001
            return ""

    # ===========================================================================================
    # VENDOR / TENANT surface — /trunk-registry (token-derived tenant; RLS is_admin=False).
    # ===========================================================================================

    @router.get("")
    async def list_trunks(request: "Request", direction: str = "") -> Any:
        """GET /trunk-registry — the trunks VISIBLE to this tenant (own + `_global`, RLS-scoped),
        optionally filtered by direction. Masked creds only (has_credential flag, never the key)."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        tid = _tid(t)
        trunks = store.list_trunks(tid, direction=direction)
        creds = {c.trunk_id: c for c in store.list_credentials_masked(tid)}
        out = []
        for tr in trunks:
            row = _trunk_public_dict(tr)
            c = creds.get(tr.id)
            row["has_credential"] = c is not None
            row["credential_scope"] = (_enum_str(c.scope) if c else "")
            out.append(row)
        return JSONResponse({"trunks": out, "direction": direction or None})

    @router.get("/health")
    async def trunks_health(request: "Request", purpose: str = "campaign") -> Any:
        """GET /trunk-registry/health — per-trunk circuit/quarantine/eligibility diagnostic for the
        tenant (the live health + compliance badge). Never reveals a credential."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse(registry.resolve_status(_tid(t), purpose))

    @router.post("/byo")
    async def create_byo_trunk(request: "Request") -> Any:
        """POST /trunk-registry/byo — a VENDOR adds their OWN BYO-number SIP trunk. sip_provider
        ONLY (gsm_gateway / direct_sip are super-admin-only, §6). sip_host is SSRF-validated BEFORE
        the row is created. The SIP password (if supplied) is stored scope='integration'. is_140 /
        DLT are accepted but is_campaign_eligible stays DB-derived (a non-140 trunk is campaign-
        blocked at the choke-point even if the vendor flips is_enabled)."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot add a trunk")
        tid = _tid(t)
        body = await _body(request)
        fields = _extract_trunk_fields(body)
        # vendor surface: force sip_provider (a vendor may NEVER register gsm/direct_sip).
        if _is_privileged_type(fields.get("trunk_type")):
            return forbidden("gsm_gateway / direct_sip trunks are super-admin only")
        fields["trunk_type"] = fields.get("trunk_type") or TrunkType.SIP_PROVIDER.value
        # SSRF gate the BYO sip_host BEFORE the trunk can exist (§6).
        dec = _validate_sip_host_ssrf(fields.get("sip_host", ""), fields.get("sip_port", 5060),
                                      _enum_str(fields.get("transport"), "udp"))
        if not dec.ok:
            return JSONResponse({"error": f"ssrf_blocked:{getattr(dec, 'reason', '')}",
                                 "resolved_ips": getattr(dec, "resolved_ips", None)},
                                status_code=400)
        try:
            row = store.create_trunk(tid, fields, created_by=tid, is_admin=False)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if row is None:
            return JSONResponse({"error": "create failed"}, status_code=400)
        new_trunk = SipTrunk.from_any(row)
        # optionally store the BYO SIP password in the same call (scope='integration').
        sip_pw = (body.get("sip_password") or body.get("auth_password")
                  or body.get("credential") or "").strip()
        cred_meta = None
        if sip_pw:
            cred_meta = _store_credential(tid, new_trunk, sip_pw, scope="integration", is_admin=False)
            if isinstance(cred_meta, JSONResponse):
                _audit(request, t, "trunk.create", object_id=new_trunk.id or "",
                       meta={"slug": new_trunk.slug, "credential": "store_failed"})
                return cred_meta
        _audit(request, t, "trunk.create", object_id=new_trunk.id or "",
               meta={"slug": new_trunk.slug, "type": _enum_str(new_trunk.trunk_type),
                     "sip_host": new_trunk.sip_host,
                     "credential": "stored" if sip_pw else "none"})
        out = _trunk_public_dict(new_trunk)
        out["has_credential"] = cred_meta is not None
        return JSONResponse(out, status_code=201)

    @router.put("/{trunk_id}")
    async def update_trunk(trunk_id: str, request: "Request") -> Any:
        """PUT /trunk-registry/{id} — update a trunk the tenant OWNS (RLS scopes the row).
        Whitelisted columns only; the SIP password is updated via /credential, not here. A `_global`
        trunk is super-admin only."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot edit a trunk")
        tid = _tid(t)
        existing = store.get_trunk(tid, trunk_id)
        if existing is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if existing.is_global:
            return forbidden("platform-managed trunk — super-admin only")
        body = await _body(request)
        fields = _extract_trunk_fields(body)
        if _is_privileged_type(fields.get("trunk_type")):
            return forbidden("gsm_gateway / direct_sip trunks are super-admin only")
        # if the sip_host changed, re-SSRF-validate it.
        if "sip_host" in fields and fields.get("sip_host") != existing.sip_host:
            dec = _validate_sip_host_ssrf(
                fields.get("sip_host", ""),
                fields.get("sip_port", existing.sip_port),
                _enum_str(fields.get("transport", existing.transport), "udp"))
            if not dec.ok:
                return JSONResponse({"error": f"ssrf_blocked:{getattr(dec, 'reason', '')}"},
                                    status_code=400)
        try:
            row = store.update_trunk(tid, trunk_id, fields, is_admin=False)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if row is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        _audit(request, t, "trunk.update", object_id=trunk_id, meta={"fields": sorted(fields.keys())})
        return JSONResponse(_trunk_public_dict(SipTrunk.from_any(row)))

    @router.delete("/{trunk_id}")
    async def delete_trunk(trunk_id: str, request: "Request", hard: int = 0) -> Any:
        """DELETE /trunk-registry/{id} — RED-TEAM D: the DEFAULT is a SOFT-DISABLE (is_enabled=false),
        NOT a row delete. A genuine hard-delete (?hard=1) REFUSES an un-deletable / `_global` /
        env-protected trunk and requires a PIN step-up (X-Step-Up). The un-deletable DB trigger is
        the backstop. Soft-disable never deletes data (the FE 'Disable' action)."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot remove a trunk")
        tid = _tid(t)
        existing = store.get_trunk(tid, trunk_id)
        if existing is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        # ---- HARD delete path (?hard=1): refuse protected, require PIN step-up ----
        if int(hard or 0) == 1:
            if existing.is_global or existing.is_undeletable:
                _audit(request, t, "trunk.delete.refused", object_id=trunk_id,
                       meta={"reason": "global_or_undeletable"})
                return forbidden("this trunk is protected and cannot be hard-deleted (disable it instead)")
            # env-protected live LiveKit trunk id -> never hard-delete.
            from . import livekit_sync as _lks
            if _lks.is_protected_trunk_id(existing.livekit_trunk_id or ""):
                _audit(request, t, "trunk.delete.refused", object_id=trunk_id,
                       meta={"reason": "env_protected_livekit_trunk"})
                return forbidden("this trunk maps to the live LiveKit trunk and cannot be hard-deleted")
            denied = _consume_reveal(request, tid, trunk_id, scope="trunk.delete")
            if denied is not None:
                _audit(request, t, "trunk.delete.denied", object_id=trunk_id, meta={"reason": "step_up"})
                return denied
            try:
                ok = store.delete_trunk(tid, trunk_id, is_admin=False)
            except store.StoreWriteError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            if not ok:
                return JSONResponse({"error": "not_found"}, status_code=404)
            _audit(request, t, "trunk.delete", object_id=trunk_id, meta={"slug": existing.slug})
            return JSONResponse({"deleted": True, "id": trunk_id})
        # ---- DEFAULT: soft-disable (the safe 'remove') ----
        try:
            row = store.soft_disable_trunk(tid, trunk_id, is_admin=False)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        _audit(request, t, "trunk.disable", object_id=trunk_id, meta={"slug": existing.slug})
        return JSONResponse({"disabled": True, "id": trunk_id,
                             "trunk": _trunk_public_dict(SipTrunk.from_any(row)) if row else None})

    @router.post("/{trunk_id}/credential")
    async def set_credential(trunk_id: str, request: "Request") -> Any:
        """POST /trunk-registry/{id}/credential — store an AAD-encrypted SIP password for a trunk the
        tenant owns. Vendor scope is always 'integration' (revealable). Rotation-aware. NEVER echoes
        the plaintext."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot set a credential")
        tid = _tid(t)
        tr = store.get_trunk(tid, trunk_id)
        if tr is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if tr.is_global:
            return forbidden("platform credential — super-admin only")
        body = await _body(request)
        sip_pw = (body.get("sip_password") or body.get("auth_password")
                  or body.get("credential") or "").strip()
        if not sip_pw:
            return JSONResponse({"error": "credential required"}, status_code=400)
        res = _store_credential(tid, tr, sip_pw, scope="integration", is_admin=False)
        if isinstance(res, JSONResponse):
            return res
        _audit(request, t, "trunk.credential.set", object_id=trunk_id,
               meta={"scope": "integration", "key_masked": credentials.mask(sip_pw)})
        return JSONResponse({"stored": True, "trunk_id": trunk_id,
                             "key_masked": credentials.mask(sip_pw), "scope": "integration"})

    @router.post("/{trunk_id}/reveal-init")
    async def reveal_init(trunk_id: str, request: "Request") -> Any:
        """POST /trunk-registry/{id}/reveal-init — mint a 60s, aud-bound, single-use trunk.reveal
        step-up token for THIS trunk after a recent PIN (FE flow: verify-pin -> reveal-init ->
        reveal). Bound to sub=tenant (F3). Returns the token the FE sends as X-Step-Up to /reveal."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if firewall is None or not hasattr(firewall, "mint_reveal_step_up"):
            return JSONResponse({"error": "step_up_unavailable"}, status_code=503)
        tid = _tid(t)
        tr = store.get_trunk(tid, trunk_id)
        if tr is None:
            if t.get("is_admin"):
                if admin_store.get_any_trunk(trunk_id) is None:
                    return JSONResponse({"error": "not_found"}, status_code=404)
            else:
                return JSONResponse({"error": "not_found"}, status_code=404)
        minted = firewall.mint_reveal_step_up(tid, trunk_id)
        if minted is None:
            return JSONResponse({"error": "step_up_unavailable"}, status_code=503)
        _audit(request, t, "trunk.reveal.init", object_id=trunk_id, meta={})
        return JSONResponse(minted)

    @router.post("/{trunk_id}/reveal")
    async def reveal_credential(trunk_id: str, request: "Request") -> Any:
        """POST /trunk-registry/{id}/reveal — reveal the plaintext SIP password of a credential the
        tenant owns. Requires a trunk.reveal PIN step-up (X-Step-Up; 60s, aud-bound, single-use jti).
        A vendor may reveal ONLY an 'integration' (own) credential — a 'platform' credential is
        masked-only (403). Replay -> 403. Audited either way."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        tid = _tid(t)
        tr = store.get_trunk(tid, trunk_id)
        if tr is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        cred = store.get_active_credential(tid, trunk_id)
        if cred is None:
            return JSONResponse({"error": "no_credential"}, status_code=404)
        if not cred.is_revealable_by_vendor:
            _audit(request, t, "trunk.reveal.denied", object_id=trunk_id,
                   meta={"reason": "platform_scope"})
            return forbidden("platform-managed credential cannot be revealed")
        denied = _consume_reveal(request, tid, trunk_id, scope="trunk.reveal")
        if denied is not None:
            _audit(request, t, "trunk.reveal.denied", object_id=trunk_id, meta={"reason": "step_up"})
            return denied
        try:
            plaintext = credentials.decrypt_credential(cred)
        except Exception:  # noqa: BLE001 — decrypt failure (tamper/cross-tenant) -> 409, no plaintext
            _audit(request, t, "trunk.reveal.error", object_id=trunk_id, meta={"reason": "decrypt_failed"})
            return JSONResponse({"error": "decrypt_failed"}, status_code=409)
        _audit(request, t, "trunk.reveal", object_id=trunk_id,
               meta={"scope": _enum_str(cred.scope), "key_masked": credentials.mask(plaintext)})
        return JSONResponse({"trunk_id": trunk_id, "credential": plaintext})

    @router.post("/{trunk_id}/test-call")
    async def test_call(trunk_id: str, request: "Request") -> Any:
        """POST /trunk-registry/{id}/test-call — RED-TEAM F: a SINGLE founder-placed test ring,
        rate-limited (<=3/hr/trunk, in-process). The founder TYPES the destination; this is the ONLY
        non-campaign originate this system exposes and it is NEVER an auto-dial. It does NOT loop a
        campaign. At T3 (no place_test_call seam wired) it returns the resolved dial-intent
        (trunk + DID + destination) WITHOUT dialing; T5 wires the actual single dial via the caller.py
        /run path. The rate-limit + founder-typed destination guarantees are enforced regardless."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot place a test call")
        tid = _tid(t)
        tr = store.get_trunk(tid, trunk_id)
        if tr is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        body = await _body(request)
        destination = (body.get("destination") or body.get("to") or "").strip()
        if not destination:
            return JSONResponse({"error": "destination required (founder-typed; never auto-dialed)"},
                                status_code=400)
        # RED-TEAM F rate-limit (in-process, per-trunk).
        allowed, remaining = _testcall_allowed(tid, trunk_id)
        if not allowed:
            _audit(request, t, "trunk.test_call.rate_limited", object_id=trunk_id,
                   meta={"destination": destination})
            return JSONResponse({"error": "rate_limited",
                                 "detail": f"max {_TESTCALL_MAX_PER_HOUR} test calls/hour/trunk"},
                                status_code=429)
        # resolve the trunk + DID for a 'test' purpose (skips the campaign eligibility gate — a single
        # founder ring may use the non-140 Vobiz `_global` trunk). Never raises.
        choice = registry.get_trunk(tid, purpose="test", routing_hint=tr.slug)
        if not choice.ok:
            return JSONResponse({"error": "no_dialable_trunk", "reason": choice.reason},
                                status_code=409)
        intent = {
            "trunk_id": trunk_id, "slug": tr.slug,
            "livekit_trunk_id": choice.livekit_trunk_id, "did": choice.did,
            "destination": destination, "purpose": "test", "remaining_this_hour": remaining,
        }
        _audit(request, t, "trunk.test_call", object_id=trunk_id,
               meta={"destination": destination, "did": choice.did})
        # seam: if caller.py injected a single-dial executor, place exactly ONE call; else intent-only.
        if place_test_call is not None:
            try:
                res = place_test_call(tid, tr, choice.did, destination) or {}
                return JSONResponse({"placed": True, **intent, **res})
            except Exception as exc:  # noqa: BLE001 — a dial failure must not 500
                return JSONResponse({"placed": False, "error": f"dial_failed:{type(exc).__name__}",
                                     **intent}, status_code=502)
        return JSONResponse({"placed": False, "dial_intent": intent,
                             "note": "test-call intent resolved; single dial wires at T5 (never auto-dial)"})

    @router.post("/{trunk_id}/quarantine-did")
    async def quarantine_did(trunk_id: str, request: "Request") -> Any:
        """POST /trunk-registry/{id}/quarantine-did — RED-TEAM E: the real-time per-DID kill switch
        (independent of the master rotation flag). 'Rest this number' from the UI. body: {did, minutes?}.
        A release is handled by /release-quarantine (clears quarantined_until)."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot quarantine a number")
        tid = _tid(t)
        tr = store.get_trunk(tid, trunk_id)
        if tr is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        body = await _body(request)
        did = (body.get("did") or "").strip()
        minutes = body.get("minutes")
        try:
            minutes = int(minutes) if minutes is not None else None
        except (TypeError, ValueError):
            minutes = None
        ok = rotation.manual_quarantine_did(tid, tr, did, minutes=minutes)
        _audit(request, t, "trunk.quarantine_did", object_id=trunk_id,
               meta={"did": did, "minutes": minutes, "ok": ok})
        return JSONResponse({"quarantined": bool(ok), "trunk_id": trunk_id, "did": did})

    @router.post("/{trunk_id}/release-quarantine")
    async def release_quarantine(trunk_id: str, request: "Request") -> Any:
        """POST /trunk-registry/{id}/release-quarantine — RED-TEAM E (release): clear quarantined_until
        (re-enable the rested trunk). The §4 reputation-panel 'release' toggle."""
        if not config.is_enabled():
            return _disabled()
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot release a quarantine")
        tid = _tid(t)
        tr = store.get_trunk(tid, trunk_id)
        if tr is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        try:
            store.set_quarantine(tid, trunk_id, None, is_admin=False)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        _audit(request, t, "trunk.release_quarantine", object_id=trunk_id, meta={})
        return JSONResponse({"released": True, "trunk_id": trunk_id})

    # ===========================================================================================
    # SUPER-ADMIN surface — /trunk-registry/admin (require_super_admin; is_admin=True touches
    # `_global`). Exposed under this router's prefix so the ONE router owns the namespace; the FE
    # maps to /trunk-registry/admin/*.
    # ===========================================================================================

    @router.get("/admin/all")
    async def admin_list_all(request: "Request", direction: str = "", tenant_id: str = "") -> Any:
        """GET /trunk-registry/admin/all — list trunks ACROSS all tenants (+ `_global`)."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        trunks = admin_store.list_all_trunks(direction=direction, tenant_id=tenant_id)
        return JSONResponse({"trunks": [_trunk_public_dict(tr) for tr in trunks]})

    @router.post("/admin")
    async def admin_create(request: "Request") -> Any:
        """POST /trunk-registry/admin — super-admin creates a trunk (may be `_global` platform-shared,
        OR a gsm_gateway / direct_sip — both SSRF-validated). is_admin=True -> the admin RLS leg
        authorizes a `_global` write."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        body = await _body(request)
        fields = _extract_trunk_fields(body)
        owner = (body.get("owner_tenant_id") or body.get("tenant_id") or "_global").strip() or "_global"
        # SSRF gate any sip_host (gsm/direct_sip on a LAN is the dangerous surface).
        if fields.get("sip_host"):
            dec = _validate_sip_host_ssrf(fields.get("sip_host", ""), fields.get("sip_port", 5060),
                                          _enum_str(fields.get("transport"), "udp"))
            if not dec.ok:
                return JSONResponse({"error": f"ssrf_blocked:{getattr(dec, 'reason', '')}",
                                     "resolved_ips": getattr(dec, "resolved_ips", None)},
                                    status_code=400)
        try:
            row = store.create_trunk(owner, fields, created_by=_tid(t) or "super-admin", is_admin=True)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if row is None:
            return JSONResponse({"error": "create failed"}, status_code=400)
        new_trunk = SipTrunk.from_any(row)
        sip_pw = (body.get("sip_password") or body.get("auth_password")
                  or body.get("credential") or "").strip()
        cred_meta = None
        if sip_pw:
            scope = (body.get("credential_scope") or "platform").strip() or "platform"
            cred_meta = _store_credential(owner, new_trunk, sip_pw, scope=scope, is_admin=True)
            if isinstance(cred_meta, JSONResponse):
                return cred_meta
        _audit(request, t, "trunk.admin.create", object_id=new_trunk.id or "",
               meta={"owner": owner, "slug": new_trunk.slug, "type": _enum_str(new_trunk.trunk_type),
                     "credential": "stored" if sip_pw else "none"})
        out = _trunk_public_dict(new_trunk)
        out["has_credential"] = cred_meta is not None
        return JSONResponse(out, status_code=201)

    @router.put("/admin/{trunk_id}")
    async def admin_update(trunk_id: str, request: "Request") -> Any:
        """PUT /trunk-registry/admin/{id} — super-admin updates ANY trunk (incl. `_global`: set the
        DLT fields / soft-disable). The un-deletable trigger still blocks a DELETE of the seed row."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        existing = admin_store.get_any_trunk(trunk_id)
        if existing is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        body = await _body(request)
        fields = _extract_trunk_fields(body)
        if fields.get("sip_host") and fields.get("sip_host") != existing.sip_host:
            dec = _validate_sip_host_ssrf(fields.get("sip_host", ""),
                                          fields.get("sip_port", existing.sip_port),
                                          _enum_str(fields.get("transport", existing.transport), "udp"))
            if not dec.ok:
                return JSONResponse({"error": f"ssrf_blocked:{getattr(dec, 'reason', '')}"},
                                    status_code=400)
        try:
            row = store.update_trunk(existing.tenant_id, trunk_id, fields, is_admin=True)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        if row is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        _audit(request, t, "trunk.admin.update", object_id=trunk_id,
               meta={"owner": existing.tenant_id, "fields": sorted(fields.keys())})
        return JSONResponse(_trunk_public_dict(SipTrunk.from_any(row)))

    @router.post("/admin/{trunk_id}/reveal")
    async def admin_reveal(trunk_id: str, request: "Request") -> Any:
        """POST /trunk-registry/admin/{id}/reveal — super-admin reveals ANY SIP credential (any
        scope), PIN step-up + single-use jti, audited. The owner tenant may be passed in the body."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        body = await _body(request)
        owner = (body.get("owner_tenant_id") or "").strip()
        cred = admin_store.get_any_credential(trunk_id, owner_tenant_id=owner)
        if cred is None:
            return JSONResponse({"error": "no_credential"}, status_code=404)
        denied = _consume_reveal(request, _tid(t), trunk_id, scope="trunk.reveal")
        if denied is not None:
            _audit(request, t, "trunk.admin.reveal.denied", object_id=trunk_id, meta={"reason": "step_up"})
            return denied
        try:
            plaintext = credentials.decrypt_credential(cred)
        except Exception:  # noqa: BLE001
            _audit(request, t, "trunk.admin.reveal.error", object_id=trunk_id,
                   meta={"reason": "decrypt_failed"})
            return JSONResponse({"error": "decrypt_failed"}, status_code=409)
        _audit(request, t, "trunk.admin.reveal", object_id=trunk_id,
               meta={"owner": cred.tenant_id, "scope": _enum_str(cred.scope),
                     "key_masked": credentials.mask(plaintext)})
        return JSONResponse({"trunk_id": trunk_id, "credential": plaintext,
                             "owner_tenant_id": cred.tenant_id})

    @router.get("/admin/health")
    async def admin_health(request: "Request") -> Any:
        """GET /trunk-registry/admin/health — per-trunk state across all tenants."""
        if not config.is_enabled():
            return _disabled()
        t, resp = _admin_gate(request)
        if resp is not None:
            return resp
        trunks = admin_store.list_all_trunks()
        out = [{
            "id": tr.id, "tenant_id": tr.tenant_id, "slug": tr.slug,
            "display_name": tr.display_name, "is_enabled": tr.is_enabled,
            "is_campaign_eligible": bool(getattr(tr, "is_campaign_eligible", False)),
            "is_quarantined": tr.is_quarantined(),
        } for tr in trunks]
        return JSONResponse({"trunks": out})

    # ---------------- shared internal helpers (closures over the injected deps) ----------------
    def _store_credential(tid: str, tr: SipTrunk, sip_pw: str, *, scope: str, is_admin: bool):
        """Encrypt + persist a SIP password; returns a JSONResponse error or a meta dict."""
        try:
            enc = credentials.encrypt_credential(tid, tr.id or "", sip_pw)
        except credentials.CredentialError as exc:
            return JSONResponse({"error": f"encrypt_unavailable:{type(exc).__name__}"},
                                status_code=503)
        try:
            return store.upsert_credential(tid, tr.id or "", enc, scope=scope, is_admin=is_admin)
        except store.StoreWriteError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

    def _consume_reveal(request, expected_sub: str, trunk_id: str, *, scope: str = "trunk.reveal"):
        """Verify + CONSUME a trunk step-up. Returns a JSONResponse(403) to RETURN on denial, or None
        to PROCEED. Fail-closed if the firewall is unavailable (never an open reveal/hard-delete)."""
        if firewall is None or not hasattr(firewall, "consume_reveal_step_up"):
            return JSONResponse({"error": "step_up_unavailable", "scope": scope}, status_code=403)
        token = _step_up_token(request)
        if not token:
            return JSONResponse({"error": "step_up_required", "scope": scope}, status_code=403)
        claims = firewall.consume_reveal_step_up(token, trunk_id, expected_sub)
        if claims is None:
            return JSONResponse({"error": "step_up_invalid", "scope": scope}, status_code=403)
        return None

    return router
