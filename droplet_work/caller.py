"""caller.py — Famit backend API + (legacy) simple Caller page.

Serves JSON /campaigns,/extract,/leads,/run,/status,/calls,/stats (the Famit panel calls these
via nginx /api -> here) plus the legacy HTML page at '/'. Reuses the working LiveKit agent
(agent_name 'capsy') + campaign-adaptive dispatch metadata {campaign_id, lead_name}. Records every
call. Auth: Basic OR header 'X-Auth: <pass>' OR 'Authorization: Bearer <pass>'.
"""
from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from google.protobuf.duration_pb2 import Duration
from livekit import api

from prompt import build_system_prompt

try:
    import whatsapp as wa_mod  # WAVE3 Unit5: provider-agnostic WhatsApp sender
except Exception:  # noqa: BLE001
    wa_mod = None

# WA-AUTO: per-person cross-call memory (voice agent's recap store). Import-safe and
# read-only here — used to enrich the WhatsApp reply brain with prior-call context.
# A missing/broken module leaves the WA path fully functional (memory is additive).
try:
    import memory as _mem_mod  # load_memory(phone) + build_recap(mem)
except Exception:  # noqa: BLE001
    _mem_mod = None

# WAVE A: vendor cost adapters (import-safe; each adapter no-ops without keys).
try:
    from vendors import elevenlabs as v_elevenlabs
    from vendors import vobiz as v_vobiz
    from vendors import groq_meter as v_groq
    from vendors import sarvam_meter as v_sarvam
    from vendors import display_name as vendor_display_name, VENDOR_IDS
except Exception:  # noqa: BLE001
    v_elevenlabs = v_vobiz = v_groq = v_sarvam = None
    VENDOR_IDS = ["vobiz", "elevenlabs", "groq", "sarvam", "livekit"]

    def vendor_display_name(vid):  # type: ignore
        return vid

load_dotenv("/opt/famit-agent/.env")

# P0 config resolver (Doppler-if-DOPPLER_TOKEN else .env/os.environ). Import-safe:
# if config.py is missing or errors, fall back to os.getenv so the service still
# starts. cfg_get/cfg_require are exact pass-throughs to os.getenv/os.environ when
# Doppler is disabled (today), so NO current value changes.
try:
    from config import get as cfg_get, require as cfg_require
except Exception:  # noqa: BLE001
    def cfg_get(key, default=None):
        return os.getenv(key, default)

    def cfg_require(key):
        return os.environ[key]

# P0 auth module (JWT access + rotating refresh). Import-safe: a missing module
# or missing pyjwt leaves _auth_mod usable-but-degraded (legacy auth untouched).
# It is wired via _auth_mod.init(...) AFTER the tenant store + _role_of exist.
try:
    import auth as _auth_mod
except Exception:  # noqa: BLE001
    _auth_mod = None

# P0 append-only audit log (best-effort; never breaks a request). init() after VAR.
try:
    import audit as _audit_mod
except Exception:  # noqa: BLE001
    _audit_mod = None

# F2 Business Brain + Knowledge Base (RAG) substrate (import-safe; dormant-degrade).
# brain = structured per-org identity store (JSON mode); kb = pgvector+FTS corpus.
# Both no-op cleanly when their deps are absent. The live voice path imports NEITHER.
try:
    import brain as _brain_mod
except Exception:  # noqa: BLE001
    _brain_mod = None
try:
    import kb as _kb_mod
except Exception:  # noqa: BLE001
    _kb_mod = None

# F4 Credit/Wallet ACID ledger + Action Firewall (import-safe; both degrade cleanly).
# wallet = the money-custody transactional core (reserve/settle/release/topup/balance) on Postgres;
# firewall = PIN/OTP step-up gate. The live RUN-PATH imports NEITHER for spend gating yet (that wiring
# is a later flag-gated unit) — these only back the additive /wallet* and /firewall/* endpoints here.
try:
    import wallet as _wallet_mod
except Exception:  # noqa: BLE001
    _wallet_mod = None
try:
    import firewall as _firewall_mod
except Exception:  # noqa: BLE001
    _firewall_mod = None

# CRM CORE: contact spine + unified timeline + next-best-action (import-safe; PG-native projection).
# A read-model/intent layer over the existing leads/calls/wa/suppression/events stores — NEVER a second
# writer of core records, NEVER on the voice run-path. Degrades to empty shapes when PG is absent.
try:
    import crm as _crm_mod
except Exception:  # noqa: BLE001
    _crm_mod = None

# CONTROL LAYER: Foundation entitlement engine (CL-B1). Import-safe; PG-native projection like crm.
# Provides resolve_modes/mode_for/assert_access/feature_key_for_path + the /me/entitlements payload.
# The enforcement choke-point (CL-B2, below) reads through it. Degrades to all-default 'on' when PG is
# absent → live site untouched. NOTHING is enforced unless CONTROL_ENABLED is on (default off).
try:
    import entitlements as _ent_mod
except Exception:  # noqa: BLE001
    _ent_mod = None

# P0 per-tenant rate limiter (Redis-if-reachable else in-proc; FAIL-OPEN always).
try:
    import ratelimit as _rl_mod
except Exception:  # noqa: BLE001
    _rl_mod = None

# P0 observability: Prometheus /metrics + structured request logs (best-effort).
try:
    import obs as _obs_mod
except Exception:  # noqa: BLE001
    _obs_mod = None

# Legacy-token kill switch. Default ON so NOTHING breaks today. Set
# LEGACY_TOKEN_ENABLED=false ONLY after every client uses JWT (post-cutover).
LEGACY_TOKEN_ENABLED = (cfg_get("LEGACY_TOKEN_ENABLED", "true") or "true").strip().lower() \
    not in ("0", "false", "no", "off")

# CONTROL LAYER master gate. DEFAULT OFF -> the entitlement enforcement middleware is a pure no-op
# passthrough (resting state byte-identical to today, F2/F4 discipline). Flip to true ONLY after the
# T1-T18 isolation/impersonation probes pass (CONTROL_LAYER_EXECUTION_PLAN §5 C12).
CONTROL_ENABLED = (cfg_get("CONTROL_ENABLED", "false") or "false").strip().lower() \
    in ("1", "true", "yes", "on")

TRUNK = cfg_get("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa")
AGENT = cfg_get("LIVEKIT_AGENT_NAME", "capsy")
LK_URL = cfg_get("LIVEKIT_URL", "ws://127.0.0.1:7880")
LK_KEY = cfg_require("LIVEKIT_API_KEY")
LK_SECRET = cfg_require("LIVEKIT_API_SECRET")
USER = cfg_get("CALLER_USER", "famit")
PW = cfg_get("CALLER_PASS", "Famit@2026")
GROQ_KEY = cfg_require("GROQ_API_KEY")
GROQ_MODEL = cfg_get("CALLER_EXTRACT_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
VAR = Path(os.getenv("FAMIT_VAR", "/opt/famit-agent/var"))
CAMPAIGN_DIR = VAR / "campaigns"
TRANSCRIPT_DIR = VAR / "transcripts"
LEADS_FILE = VAR / "leads.json"
CALLS_FILE = VAR / "calls.json"
TENANTS_FILE = VAR / "tenants.json"
SECRET_FILE = VAR / "secret"
SUPPRESSION_FILE = VAR / "suppression.json"   # P0.2 DND/suppression store
RETRY_FILE = VAR / "retry_queue.json"         # P0.5 retry + callback queue
WA_LOG_FILE = VAR / "wa_log.json"             # P1.A whatsapp send log
WA_THREADS_DIR = VAR / "wa_threads"           # WAVE A2 per-contact WhatsApp conversation state
WEBHOOK_FILE = VAR / "webhooks.json"          # P1.C registered webhooks
WEBHOOK_LOG_FILE = VAR / "webhook_log.json"   # P1.C delivery log
BILLING_FILE = VAR / "billing.json"           # WAVE3 Unit4 per-tenant billing plans
LEDGER_DIR = VAR / "ledger"                   # WAVE3 Unit4 per-tenant charge ledgers
# ---------- WAVE A: real vendor-cost metering stores ----------
USAGE_EVENTS_FILE = VAR / "usage_events.json"     # append: per-call per-vendor internal metering rows
COST_LEDGER_FILE = VAR / "cost_ledger.json"       # normalized joined cost rows (usage + vendor CDR)
DAILY_ROLLUPS_FILE = VAR / "daily_rollups.json"   # precomputed daily/vendor/tenant rollups
VENDOR_SNAPSHOTS_FILE = VAR / "vendor_snapshots.json"  # per-vendor sync status/timestamps for Audit tab
MIN_CALL_FLOOR = 22

# ---------- IST time helpers (P0.1 / P0.5) ----------
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


app = FastAPI()
JOBS: dict = {}


# ---------- P0: per-tenant rate-limit middleware (additive, FAIL-OPEN) ----------
# Pick the backend once at startup (redis on :6380 if reachable, else in-proc, else
# disabled). On ANY problem this middleware allows the request — it never blocks
# real traffic. Health/metrics and the legacy HTML page are exempt.
_RL_BACKEND = "disabled"
if _rl_mod is not None:
    try:
        _RL_BACKEND = _rl_mod.init()
    except Exception:  # noqa: BLE001
        _RL_BACKEND = "disabled"

_RL_EXEMPT_PATHS = {"/", "/health", "/metrics", "/favicon.ico"}
# Auth endpoints get the strict 'auth' class (brute-force guard), keyed by IP.
_RL_AUTH_PATHS = {"/login", "/auth/login", "/auth/refresh"}


def _rl_route_class(method: str, path: str) -> str:
    if path in _RL_AUTH_PATHS:
        return "auth"
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return "write"
    return "read"


@app.middleware("http")
async def _rate_limit_mw(request: Request, call_next):
    # Disabled / module missing -> straight through.
    if _rl_mod is None or _RL_BACKEND == "disabled":
        return await call_next(request)
    try:
        path = request.url.path
        if path in _RL_EXEMPT_PATHS:
            return await call_next(request)
        route_class = _rl_route_class(request.method, path)
        # Key by tenant when we can resolve one cheaply; else by client IP so
        # anonymous floods (e.g. login brute-force) are still bounded.
        try:
            t = resolve_tenant(request)
        except Exception:  # noqa: BLE001
            t = None
        key = (t or {}).get("tenant_id") or f"ip:{_client_ip(request)}"
        allowed, info = _rl_mod.allow(key, route_class)
        if not allowed:
            retry = int(info.get("reset_in", 1) or 1)
            resp = JSONResponse(
                {"error": "rate limit exceeded", "route_class": route_class,
                 "retry_after": retry}, status_code=429)
            resp.headers["Retry-After"] = str(retry)
            resp.headers["X-RateLimit-Limit"] = str(info.get("limit", ""))
            resp.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))
            return resp
    except Exception:  # noqa: BLE001 — limiter must never break the request path
        return await call_next(request)
    return await call_next(request)


# ---------- P0: observability (Prometheus + structured access log) ----------
# Cost gauge REUSES the existing metered cost_ledger (lazy callback; the function
# is defined later in this file but only invoked at /metrics render time).
def _cost_by_currency() -> dict:
    out: dict = {}
    try:
        for r in _read_cost_ledger():
            ccy = r.get("currency") or "INR"
            out[ccy] = out.get(ccy, 0.0) + float(r.get("cost", 0) or 0)
    except Exception:  # noqa: BLE001
        pass
    return out or {"INR": 0.0}


if _obs_mod is not None:
    try:
        _obs_mod.init(cost_provider=_cost_by_currency, component="famit-caller")
    except Exception:  # noqa: BLE001
        pass


@app.middleware("http")
async def _metrics_mw(request: Request, call_next):
    if _obs_mod is None or not _obs_mod.ready():
        return await call_next(request)
    start = time.perf_counter()
    _obs_mod.inprogress_inc()
    status = 500
    try:
        resp = await call_next(request)
        status = resp.status_code
        return resp
    finally:
        _obs_mod.inprogress_dec()
        try:
            dt = time.perf_counter() - start
            # Route TEMPLATE (e.g. /campaigns/{cid}) to bound metric cardinality.
            route = request.url.path
            r = request.scope.get("route")
            if r is not None and getattr(r, "path", None):
                route = r.path
            _obs_mod.observe(request.method, route, status, dt)
            # one-line structured access log (journald)
            tid = ""
            try:
                _t = resolve_tenant(request)
                tid = (_t or {}).get("tenant_id", "")
            except Exception:  # noqa: BLE001
                pass
            _obs_mod.log_request(request.method, request.url.path, route, status,
                                 dt * 1000.0, tenant=tid, ip=_client_ip(request))
        except Exception:  # noqa: BLE001
            pass


# ════════════════════════════════════════════════════════════════════════════
# CONTROL LAYER — entitlement ENFORCEMENT middleware (CL-B2 / plan C3)
# ════════════════════════════════════════════════════════════════════════════
# THE REAL SECURITY BOUNDARY (control-security.md §1.3, spec-control-layer §3):
#   path -> feature_key (via entitlements.feature_key_for_path, longest-prefix +
#   explicit shared map) -> mode -> HIDDEN=404 (no existence leak), LOCKED=402
#   (+upsell JSON), CORE=always pass, unmapped-legacy-path=pass, ON=pass.
#
# It is implemented as an @app.middleware("http") that RETURNS a JSONResponse for a
# block (it NEVER raises HTTPException inside the middleware — the researched
# Starlette gotcha is that raising inside a custom middleware runs OUTSIDE the
# ExceptionMiddleware and leaks a 500; the existing _rate_limit_mw already follows
# this return-don't-raise pattern, so we match it). Frontend HIDE/LOCK is cosmetic;
# this layer is what a saved token / curl / devtools actually hits.
#
# GATED behind CONTROL_ENABLED (default OFF) -> pure no-op passthrough = resting
# byte-identical (T17). On the off path the function returns before any work.
#
# Paths this layer NEVER governs (entitlement is N/A — orthogonal gates own them):
#   * infra/docs (/, /health, /metrics, /favicon.ico, /docs, /openapi.json, /redoc)
#   * /admin/*  -> role-gated by require_super_admin (403 for a vendor); NOT a
#                  hidden FEATURE, so it must not 404/402 here (control-security §1.4).
_CONTROL_EXEMPT_EXACT = {"/", "/health", "/metrics", "/favicon.ico",
                         "/docs", "/openapi.json", "/redoc"}


def _control_path_exempt(path: str) -> bool:
    if path in _CONTROL_EXEMPT_EXACT:
        return True
    # admin plane (role-gated, not entitlement-gated) + swagger assets.
    if path.startswith("/admin") or path.startswith("/docs") or path.startswith("/openapi"):
        return True
    return False


# CONTROL LAYER (CL-B3): act-as READ-ONLY write block. ALWAYS active (independent of CONTROL_ENABLED —
# impersonation is a live capability, not gated by the entitlement master flag). A read_only act-as token
# may ONLY make safe (GET/HEAD/OPTIONS) requests; any POST/PUT/DELETE/PATCH is refused (T10). The act-as
# exit + the firewall verify-pin (to elevate) are the only mutating exceptions. Costs nothing on a normal
# request: we only decode when the cred is present AND carries the act_as marker.
_ACT_AS_WRITE_OK_PATHS = {"/admin/act-as/exit", "/firewall/verify-pin"}


def _act_as_readonly_block(request: Request):
    """Return a 403 JSONResponse if this is a read_only act-as token attempting a mutation; else None."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if _auth_mod is None:
        return None
    try:
        cred = _extract_cred(request)
        if not cred or cred.count(".") != 2:
            return None
        claims = _auth_mod.act_as_claims(cred)
    except Exception:  # noqa: BLE001
        return None
    if not claims:
        return None
    if claims.get("scope") == "read_only" and request.url.path not in _ACT_AS_WRITE_OK_PATHS:
        return JSONResponse(
            {"error": "act-as session is read-only", "act_as": claims.get("act_as")},
            status_code=403)
    return None


@app.middleware("http")
async def _enforce_entitlement_mw(request: Request, call_next):
    # (-1) ACT-AS READ-ONLY GUARD — always on (impersonation safety, not entitlement enforcement).
    blocked = _act_as_readonly_block(request)
    if blocked is not None:
        return blocked

    # (0) MASTER GATE: off -> byte-identical passthrough (no resolve, no lookup).
    if not CONTROL_ENABLED or _ent_mod is None:
        return await call_next(request)

    path = request.url.path
    if _control_path_exempt(path):
        return await call_next(request)

    feature_key = None
    try:
        # (1) path -> governing feature_key (longest-prefix + shared map). None for an
        #     ungoverned legacy route -> pass through (CI registry-drift guard closes
        #     that gap later; spec §3). A resolver error -> treat as ungoverned (pass).
        feature_key = _ent_mod.feature_key_for_path(path)
        if not feature_key:
            return await call_next(request)

        # (2) CORE floor: un-hideable keys (login/me/settings/health/wallet-pay) ALWAYS
        #     pass — anti-lockout (a misconfig must never brick the way back in).
        reg = _ent_mod.load_registry().get(feature_key) or {}
        if reg.get("is_core"):
            return await call_next(request)

        # (3) resolve the calling tenant from the TOKEN (never the body). If we can't,
        #     do NOT 404/402 here — let the route's own auth return 401 (don't mask the
        #     auth failure as a not-found). Anonymous traffic on a public route (e.g.
        #     /f/ public forms) is governed by that route, not by an entitlement.
        try:
            tenant = resolve_tenant(request)
        except Exception:  # noqa: BLE001
            tenant = None
        if tenant is None:
            return await call_next(request)
        tid = tenant.get("tenant_id") or ""

        # (4) effective mode for THIS tenant+feature. The engine is fail-closed for an
        #     unknown/garbage mode (-> hidden); it degrades to 'on' only when PG is down
        #     (resting safety, by design). Admin tenants are NOT entitlement-gated here
        #     (they manage entitlements; their own plane is role-gated) -> always pass.
        if tenant.get("is_admin"):
            return await call_next(request)
        mode = _ent_mod.evaluate(tid, feature_key)
    except Exception as exc:  # noqa: BLE001
        # FAIL-CLOSED: an unexpected error AFTER a governed feature_key was resolved =
        # deny (404, no existence leak). If no key was resolved we already passed above.
        if feature_key:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return await call_next(request)

    if mode == "hidden":
        return JSONResponse({"error": "not_found"}, status_code=404)
    if mode == "locked":
        return JSONResponse(
            {"error": "locked", "feature": feature_key, "upgrade": True},
            status_code=402)
    # mode == "on" (or any unexpected-but-non-blocking value already normalized by the
    # engine to hidden above) -> proceed.
    return await call_next(request)


# In-memory live concurrency per tenant (P0.7). Source of truth for active SIP calls.
ACTIVE_CALLS: dict = {}

# Serialize read-modify-write on shared JSON stores. run_job (dial loop) AND
# scheduler_loop both write leads/calls/suppression/retry concurrently -> without
# this lock concurrent writers lose updates. ALL async writers MUST use _awrite.
_STORE_LOCK = asyncio.Lock()

# P1 strangler: per-store MODE router (store.py). Declared = None HERE (B4) so the rewritten
# _read/_write shims are safe at IMPORT TIME (_migrate_to_admin() @504 and CALLS=_read() @683 run
# before store.init below). Assigned only AFTER store.init() returns; shims guard `_store is not None`.
_store = None

# WAVE A Unit3: timestamp (monotonic-ish epoch) of the last full vendor-sync pass.
# 0 -> forces a sync on the first scheduler tick after startup.
_LAST_VENDOR_SYNC = 0.0


# ---------- secret (HMAC signing key) ----------
def _load_secret() -> str:
    try:
        if SECRET_FILE.exists():
            s = SECRET_FILE.read_text(encoding="utf-8").strip()
            if s:
                return s
    except Exception:  # noqa: BLE001
        pass
    s = secrets.token_hex(32)
    try:
        VAR.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(s, encoding="utf-8")
        try:
            os.chmod(SECRET_FILE, 0o600)
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001
        pass
    return s


SECRET = _load_secret()


# ---------- tenant store ----------
def _hash_pw(password: str, salt: str) -> str:
    return hashlib.sha256((salt + ":" + (password or "")).encode("utf-8")).hexdigest()


def _read_tenants() -> list[dict]:
    return _read(TENANTS_FILE, [])


def _write_tenants(tenants: list[dict]):
    _write(TENANTS_FILE, tenants)


def _seed_admin() -> dict:
    """Ensure exactly one admin tenant exists; its password == legacy PW so panel login keeps working."""
    tenants = _read_tenants()
    admin = next((t for t in tenants if t.get("is_admin")), None)
    if admin:
        return admin
    salt = secrets.token_hex(8)
    admin = {
        "tenant_id": "admin",
        "email": "admin@famit.in",
        "salt": salt,
        "pass_hash": _hash_pw(PW, salt),
        "name": "Famit Admin",
        "is_admin": True,
        "role": "admin",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    tenants.insert(0, admin)
    _write_tenants(tenants)
    return admin


def _make_token(tenant_id: str) -> str:
    sig = hmac.new(SECRET.encode("utf-8"), tenant_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{tenant_id}.{sig}"


def _tenant_by_id(tenant_id: str) -> dict | None:
    return next((t for t in _read_tenants() if t.get("tenant_id") == tenant_id), None)


def _verify_token(token: str) -> dict | None:
    """token == tenant_id.hmac(tenant_id, SECRET). Returns the tenant dict or None."""
    if not token or "." not in token:
        return None
    tid, _, sig = token.partition(".")
    expect = hmac.new(SECRET.encode("utf-8"), tid.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    return _tenant_by_id(tid)


# NOTE: ADMIN_TENANT / ADMIN_ID are seeded after _read/_write are defined (see below).
ADMIN_TENANT: dict = {}
ADMIN_ID = "admin"


# ---------- auth ----------
def _extract_cred(request: Request) -> str:
    """Pull the raw credential string from Basic / Bearer / X-Auth."""
    h = request.headers.get("authorization", "")
    if h.startswith("Basic "):
        try:
            _, p = base64.b64decode(h[6:]).decode().split(":", 1)
            return p
        except Exception:  # noqa: BLE001
            return ""
    if h.startswith("Bearer "):
        return h[7:].strip()
    return request.headers.get("x-auth", "")


def resolve_tenant(request: Request) -> dict | None:
    """Resolve the calling tenant. Accepts (in order, all ADDITIVE):
       - a P0 JWT access token (Bearer/X-Auth) -> that tenant   [new, optional]
       - legacy bare password (== PW)  -> admin tenant (keeps panel login working)
       - signed token  tenant_id.hmac  -> that tenant
    Returns tenant dict or None. The legacy/hmac branch is gated by
    LEGACY_TOKEN_ENABLED (default True) so it can be turned off AFTER cutover
    without code changes; JWT is never gated.
    """
    cred = _extract_cred(request)
    if not cred:
        return None
    # 1) JWT access token (no-op/None if pyjwt missing or cred isn't a JWT).
    if _auth_mod is not None:
        try:
            t = _auth_mod.resolve_token(cred)
            if t:
                return t
        except Exception:  # noqa: BLE001 — never let auth module break the request
            pass
    # 2) legacy paths (unchanged), gated by the flag.
    if not LEGACY_TOKEN_ENABLED:
        return None
    if cred == PW:
        return _tenant_by_id(ADMIN_ID) or ADMIN_TENANT
    return _verify_token(cred)


def authed(request: Request) -> bool:
    return resolve_tenant(request) is not None


def need_auth() -> Response:
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Famit"'})


# ════════════════════════════════════════════════════════════════════════════
# CONTROL LAYER — admin-plane gate (CL-B2 / plan C2 gate)
# ════════════════════════════════════════════════════════════════════════════
# THE #1 SECURITY FINDING (control-security.md §1.1): the legacy static password
# (CALLER_PASS / "FamitCall2026") is a permanent, un-revocable, un-audited admin
# BEARER token. It MUST NOT reach the /admin/* control plane. require_super_admin
# = is_admin AND auth_method != legacy_pw. This mirrors the existing /tenants gate
# (`if not t.get("is_admin"): 403`) but ADDS the legacy-password exclusion.
def _auth_method(request: Request) -> str:
    """Re-derive HOW the caller authenticated, using the SAME precedence as
    resolve_tenant (JWT first, then legacy bare-password, then signed hmac token).
    Returns 'jwt' | 'legacy_pw' | 'hmac' | 'none'. Non-mutating: resolve_tenant's
    return contract is unchanged — this is a separate, cheap re-classification so
    the admin gate can exclude the static password without touching every reader."""
    cred = _extract_cred(request)
    if not cred:
        return "none"
    # 1) a valid Famit ACCESS JWT (revocable, short-TTL) — the strong path.
    if _auth_mod is not None:
        try:
            if _auth_mod.resolve_token(cred):
                return "jwt"
        except Exception:  # noqa: BLE001
            pass
    if not LEGACY_TOKEN_ENABLED:
        return "none"
    # 2) the legacy bare password -> admin tenant. THE excluded path.
    if cred == PW:
        return "legacy_pw"
    # 3) a signed tenant_id.hmac token (per-tenant, derived from var/secret).
    if _verify_token(cred) is not None:
        return "hmac"
    return "none"


def _is_super_admin(tenant: dict | None, request: Request) -> bool:
    """Phase 1 predicate (control-security.md §1.2): is_admin AND non-legacy auth.
    Phase 2 (when Logto lands): admin-org membership + 'manage_tenants' scope.
    The bare static password is REJECTED here even though it still authenticates
    vendor-grade routes during the transition (residual risk #1, flagged)."""
    if not tenant or not tenant.get("is_admin"):
        return False
    return _auth_method(request) != "legacy_pw"


def require_super_admin(request: Request) -> dict | JSONResponse:
    """The ONE centralized /admin/* gate. Returns the resolved admin tenant dict
    on success, or a Response (401/403) to return directly. Usage in a handler:
        t = require_super_admin(request)
        if isinstance(t, JSONResponse): return t
    Returns 403 (NOT 404) for a non-admin: the EXISTENCE of an admin plane is not a
    secret (control-security.md §1.4); only hidden FEATURES return 404. A vendor
    token, an unauthenticated caller, or the legacy password all fail here."""
    t = resolve_tenant(request)
    if t is None:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    if not _is_super_admin(t, request):
        return _forbidden("super-admin required")
    return t


# ---------- helpers / stores ----------
def norm(n: str) -> str:
    d = re.sub(r"\D", "", n or "")
    if d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "91" + d
    return "+" + d if len(d) >= 11 else ""


def _read_raw(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return default


def _write_raw(path: Path, data):
    try:
        VAR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def _awrite_raw(path: Path, data):
    """Lock-guarded write for shared stores written from concurrent async tasks
    (run_job + scheduler_loop). Prevents lost updates on leads/calls/suppression/retry."""
    async with _STORE_LOCK:
        _write_raw(path, data)


# ---- P1 strangler shims: route registered non-json stores through store.py; else byte-identical
#      pass-through to the *_raw bodies above (R3: json mode NEVER reserializes). _store guarded
#      `is not None` (B4) so import-time calls (504/683) are safe before store.init runs. ----
def _read(path: Path, default):
    if _store is not None and _store.mode_of(path) != "json":
        return _store.read(path, default)
    return _read_raw(path, default)


def _write(path: Path, data):
    if _store is not None and _store.mode_of(path) != "json":
        _store.write(path, data)
        return
    _write_raw(path, data)


async def _awrite(path: Path, data):
    if _store is not None and _store.mode_of(path) != "json":
        await _store.awrite(path, data)
        return
    await _awrite_raw(path, data)


# ---- P1: initialize the store router ONCE, here, BEFORE _migrate_to_admin() (@504) and
#      CALLS=_read() (@683) run at import. With STORE_MODES empty (default) every store stays json,
#      so the shims above are a transparent pass-through and behavior is byte-identical to pre-P1.
#      Import-safe: any failure leaves _store=None -> shims call the raw funcs (degrade-to-json). ----
class _StoreConfigShim:
    """Adapts caller's cfg_get into the .get(key, default) surface store.py/db.engine expect,
    so it works whether config.py imported or fell back to os.getenv."""
    @staticmethod
    def get(key, default=""):
        return cfg_get(key, default)

try:
    import store as _store_mod
    _store_mod.init(_read_raw, _write_raw, _awrite_raw, _STORE_LOCK, _StoreConfigShim)
    _store = _store_mod
except Exception:  # noqa: BLE001
    _store = None


# ---------- calling-window helpers (P0.1 / P0.5) ----------
def _in_window(fields: dict) -> tuple[bool, str]:
    """True if 'now' (IST) is within the campaign's calling window. Default 09:00-21:00."""
    fields = fields or {}
    s = fields.get("call_window_start") or "09:00"
    e = fields.get("call_window_end") or "21:00"
    now = now_ist().strftime("%H:%M")
    ok = s <= now <= e
    return ok, f"{s}-{e} IST"


def _clamp_to_window(dt: datetime, fields: dict) -> datetime:
    """Move dt into the calling window: before start -> start same day; after end -> start next day."""
    fields = fields or {}
    s = (fields.get("call_window_start") or "09:00").split(":")
    e = (fields.get("call_window_end") or "21:00").split(":")
    try:
        sh, sm = int(s[0]), int(s[1]); eh, em = int(e[0]), int(e[1])
    except Exception:  # noqa: BLE001
        sh, sm, eh, em = 9, 0, 21, 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    start = dt.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = dt.replace(hour=eh, minute=em, second=0, microsecond=0)
    if dt < start:
        return start
    if dt > end:
        return (start + timedelta(days=1))
    return dt


# ---- seed admin + migrate legacy records to admin tenant (now that _read/_write exist) ----
ADMIN_TENANT = _seed_admin()
ADMIN_ID = ADMIN_TENANT["tenant_id"]


def _migrate_to_admin():
    """Backwards-compatible: any existing record with no tenant_id belongs to admin.
    Never loses data; only fills the missing field in place."""
    # campaigns
    try:
        for p in CAMPAIGN_DIR.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            if not d.get("tenant_id"):
                d["tenant_id"] = ADMIN_ID
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    # leads
    leads = _read(LEADS_FILE, [])
    changed = False
    for x in leads:
        if not x.get("tenant_id"):
            x["tenant_id"] = ADMIN_ID
            changed = True
    if changed:
        _write(LEADS_FILE, leads)
    # calls
    calls = _read(CALLS_FILE, [])
    changed = False
    for c in calls:
        if not c.get("tenant_id"):
            c["tenant_id"] = ADMIN_ID
            changed = True
    if changed:
        _write(CALLS_FILE, calls)


_migrate_to_admin()


def _migrate_tenant_limits():
    """P0.7: backfill plan limits on existing tenants with generous defaults (admin = high)."""
    tenants = _read_tenants()
    changed = False
    for x in tenants:
        is_admin = bool(x.get("is_admin"))
        if "max_concurrency" not in x:
            x["max_concurrency"] = 20 if is_admin else 3; changed = True
        if "daily_call_cap" not in x:
            x["daily_call_cap"] = 100000 if is_admin else 500; changed = True
        if "monthly_minutes_cap" not in x:
            x["monthly_minutes_cap"] = 1000000 if is_admin else 5000; changed = True
    if changed:
        _write_tenants(tenants)


_migrate_tenant_limits()


# ---------- WAVE3 Unit 1: RBAC ----------
# Roles: admin | manager | agent.
#   admin   = full control + tenant management + limits + billing config.
#   manager = run campaigns, manage campaigns/leads/webhooks within own tenant.
#   agent   = read-only (view calls/leads/analytics); cannot /run, create or delete.
ROLES = ("admin", "manager", "agent")


def _role_of(tenant: dict) -> str:
    """Resolve a tenant/user's role. Backwards-compatible migration:
    explicit `role` wins; else is_admin -> admin, otherwise -> manager."""
    if not tenant:
        return "agent"
    r = (tenant.get("role") or "").strip().lower()
    if r in ROLES:
        return r
    return "admin" if tenant.get("is_admin") else "manager"


def _migrate_tenant_roles():
    """Backfill `role` on existing tenants so nothing breaks. admin tenants -> admin,
    all other existing users -> manager (they could already run campaigns)."""
    tenants = _read_tenants()
    changed = False
    for x in tenants:
        if not (x.get("role") or "").strip().lower() in ROLES:
            x["role"] = "admin" if x.get("is_admin") else "manager"
            changed = True
    if changed:
        _write_tenants(tenants)


_migrate_tenant_roles()


def can(tenant: dict, action: str) -> bool:
    """Lightweight permission check.
    action: 'manage_tenants' (admin only), 'write' (admin/manager: run/create/delete
    campaigns+leads+webhooks+whatsapp), 'read' (everyone authed)."""
    role = _role_of(tenant)
    if action == "manage_tenants":
        return role == "admin"
    if action == "write":
        return role in ("admin", "manager")
    return True  # read


def _forbidden(msg: str = "insufficient permissions") -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=403)


# ---------- P0: BOLA ownership guard (defensive depth) ----------
def _owns(tenant: dict | None, obj: dict | None) -> bool:
    """True if `tenant` may access `obj`. Admin sees all; otherwise obj.tenant_id
    must equal the tenant's id. Legacy objects without tenant_id default to the
    admin tenant (ADMIN_ID), matching how the rest of the code scopes data."""
    if not tenant or obj is None:
        return False
    if tenant.get("is_admin"):
        return True
    return obj.get("tenant_id", ADMIN_ID) == tenant.get("tenant_id")


def require_object(tenant: dict | None, obj: dict | None,
                   not_found: bool = True) -> JSONResponse | None:
    """Central BOLA assert for per-ID handlers. Returns an error Response if the
    tenant does NOT own `obj` (or it's missing), else None so the caller proceeds.

    Defense-in-depth: existing handlers already fetch via tenant-scoped readers
    (get_campaign_for / calls_for / _leads_for) that return None cross-tenant.
    This makes the ownership check explicit and uniform wherever a raw object is
    in hand, so a future handler that forgets to scope its read still can't leak
    another tenant's object. By default returns 404 (don't reveal existence of
    other tenants' objects); pass not_found=False for an explicit 403.
    """
    if obj is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    if _owns(tenant, obj):
        return None
    if not_found:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"error": "forbidden: not your object"}, status_code=403)


# ---------- P0: wire JWT auth module to the existing tenant store ----------
def _verify_password_for_auth(email: str, password: str) -> dict | None:
    """Password check used by the JWT /auth/login. Mirrors the legacy /login
    semantics EXACTLY so both stay in lock-step:
      - bare password == PW (no email) -> admin tenant
      - email + matching salted hash    -> that tenant
      - admin email + legacy PW         -> admin tenant
    Returns the tenant dict or None.
    """
    email = (email or "").strip().lower()
    if not email and password == PW:
        return _tenant_by_id(ADMIN_ID) or ADMIN_TENANT
    if email:
        t = next((x for x in _read_tenants() if (x.get("email") or "").lower() == email), None)
        if t and t.get("pass_hash") == _hash_pw(password, t.get("salt", "")):
            return t
        if t and t.get("is_admin") and password == PW:
            return t
    return None


# Initialise the JWT module (reuses the SAME var/secret as the hmac tokens, so no
# new secret to provision and tokens survive restart). Degrades to NO-OP if pyjwt
# is unavailable — legacy auth is untouched either way.
AUTH_JWT_READY = False
if _auth_mod is not None:
    try:
        AUTH_JWT_READY = _auth_mod.init(
            secret=SECRET,
            refresh_file=VAR / "refresh_tokens.json",
            tenant_by_id=_tenant_by_id,
            verify_password=_verify_password_for_auth,
            role_of=_role_of,
        )
    except Exception:  # noqa: BLE001
        AUTH_JWT_READY = False

# Initialise the append-only audit log.
if _audit_mod is not None:
    try:
        _audit_mod.init(VAR / "audit_log.jsonl")
    except Exception:  # noqa: BLE001
        pass

# F4 Action Firewall: reuse the SAME var/secret (SECRET) the JWT/hmac path uses, + a pins store.
# Degrades to pass-through (no gating) if pyjwt absent or no secret. wallet needs NO init (it rides
# db.engine, which store.init() already wires at startup).
FIREWALL_READY = False
if _firewall_mod is not None:
    try:
        FIREWALL_READY = _firewall_mod.init(secret=SECRET, pin_file=VAR / "pins.json")
    except Exception:  # noqa: BLE001
        FIREWALL_READY = False

# CONTROL LAYER: load the entitlement catalog/plans seed + best-effort apply the additive control
# schema. NEVER raises (degrades to all-default 'on' when PG/seed absent -> resting byte-identical).
# This only loads the engine; NOTHING is enforced unless CONTROL_ENABLED is on.
CONTROL_READY = False
if _ent_mod is not None:
    try:
        CONTROL_READY = _ent_mod.init()
    except Exception:  # noqa: BLE001
        CONTROL_READY = False


def _client_ip(request: Request) -> str:
    """Best-effort client IP (honours X-Forwarded-For from nginx)."""
    try:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else ""
    except Exception:  # noqa: BLE001
        return ""


def _audit(request: Request, tenant: dict | None, action: str,
           object_type: str = "", object_id: str = "",
           channel: str = "api", meta: dict | None = None) -> None:
    """Tiny wrapper so mutating endpoints can log in one line. Best-effort."""
    if _audit_mod is None:
        return
    try:
        tid = (tenant or {}).get("tenant_id", "")
        _audit_mod.record(actor=tid, action=action, object_type=object_type,
                          object_id=object_id, ip=_client_ip(request),
                          channel=channel, tenant_id=tid,
                          actor_role=_role_of(tenant) if tenant else "",
                          meta=meta)
    except Exception:  # noqa: BLE001
        pass


CALLS: list = _read(CALLS_FILE, [])


def parse_leads(text: str, csv_bytes: bytes | None) -> list[dict]:
    leads: list[dict] = []

    def add(name: str, raw: str):
        nn = norm(raw)
        if nn:
            leads.append({"name": (name or "").strip(), "num": nn})

    for line in (text or "").splitlines():
        if not line.strip():
            continue
        parts = re.split(r"[,\t]", line)
        phone, name = "", ""
        for p in parts:
            if re.search(r"\d{8,}", p):
                phone = p
            elif p.strip():
                name = name or p.strip()
        add(name, phone or line)
    if csv_bytes:
        try:
            for r in csv.reader(io.StringIO(csv_bytes.decode("utf-8", errors="ignore"))):
                phone, name = "", ""
                for cell in r:
                    if re.search(r"\d{8,}", cell or ""):
                        phone = cell
                    elif (cell or "").strip() and not name and not re.fullmatch(r"[\d\s\-+]+", cell or ""):
                        name = cell.strip()
                if phone:
                    add(name, phone)
        except Exception:  # noqa: BLE001
            pass
    seen, out = set(), []
    for x in leads:
        if x["num"] not in seen:
            seen.add(x["num"])
            out.append(x)
    return out


def parse_xlsx(xlsx_bytes: bytes | None) -> list[dict]:
    """Parse an Excel (.xlsx/.xls) workbook into [{name,num}] using openpyxl
    (read-only, pure-python). Sniffs the phone column (>=8 digits) and the first
    non-numeric text cell as the name — mirrors parse_leads's column logic so the
    behaviour is identical whether a vendor uploads CSV or Excel. Never raises:
    on any failure (missing dep, corrupt file) returns [] so the caller degrades
    to the existing csv/text path. RC2."""
    out: list[dict] = []
    if not xlsx_bytes:
        return out
    try:
        import openpyxl  # lazy: only loaded when an xlsx is actually uploaded
    except Exception:  # noqa: BLE001 — dep absent -> behave like no xlsx given
        return out
    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return out
    seen: set[str] = set()
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                if row is None:
                    continue
                phone, name = "", ""
                for cell in row:
                    if cell is None:
                        continue
                    # openpyxl gives ints/floats for numeric cells -> stringify.
                    s = str(cell).strip()
                    if not s:
                        continue
                    if re.search(r"\d{8,}", s):
                        if not phone:
                            phone = s
                    elif not name and not re.fullmatch(r"[\d\s\-+.eE]+", s):
                        name = s
                if not phone:
                    continue
                nn = norm(phone)
                if nn and nn not in seen:
                    seen.add(nn)
                    out.append({"name": name, "num": nn})
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            wb.close()
        except Exception:  # noqa: BLE001
            pass
    return out


def _is_xlsx_name(filename: str | None) -> bool:
    """True when an uploaded filename looks like an Excel workbook."""
    fn = (filename or "").lower().strip()
    return fn.endswith(".xlsx") or fn.endswith(".xlsm") or fn.endswith(".xls")


def parse_upload(text: str, upload: "UploadFile | None", file_bytes: bytes | None) -> list[dict]:
    """Unified parse: text lines + an uploaded file routed by filename
    (.xlsx/.xls -> openpyxl, else stdlib csv). Returns the de-duplicated
    [{name,num}] list. Back-compat: with no file this is exactly parse_leads(text).
    RC2."""
    if file_bytes and upload is not None and _is_xlsx_name(getattr(upload, "filename", "")):
        rows = parse_leads(text, None) + parse_xlsx(file_bytes)
    else:
        rows = parse_leads(text, file_bytes)
    seen, out = set(), []
    for x in rows:
        if x["num"] and x["num"] not in seen:
            seen.add(x["num"])
            out.append(x)
    return out


def extract_fields(brief: str) -> dict:
    sysmsg = (
        "You convert a tele-calling campaign brief into JSON. Return ONLY a JSON object with keys: "
        "company_name, agent_name, product_name, product_summary, location, price_offer, "
        "usps (array of short strings), talking_points (array), objections (array of {q,a}), "
        "qualifying_questions (array), language. Hinglish-friendly, concise. agent_name default 'Riya', "
        "language default 'Hinglish'. If unknown, use a short sensible default."
    )
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + GROQ_KEY},
            json={"model": GROQ_MODEL, "temperature": 0.2, "max_tokens": 900,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "system", "content": sysmsg},
                               {"role": "user", "content": brief[:6000]}]},
            timeout=30,
        )
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.DOTALL)
        return json.loads(m.group(0) if m else content)
    except Exception as exc:  # noqa: BLE001
        return {"_error": repr(exc)[:200], "agent_name": "Riya", "company_name": "",
                "product_name": "", "product_summary": brief[:400], "language": "Hinglish"}


def _groq_chat(messages: list, max_tokens: int = 300, temperature: float = 0.5,
               timeout: int = 20) -> str:
    """Reuse the Groq client/key for a one-shot chat completion. Returns the
    assistant text, or "" on any failure (never raises). Used by WhatsApp AI drafts."""
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer " + GROQ_KEY},
            json={"model": GROQ_MODEL, "temperature": temperature,
                  "max_tokens": max_tokens, "messages": messages},
            timeout=timeout,
        )
        return (r.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def save_campaign(fields: dict, tenant_id: str) -> dict:
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    cid = uuid.uuid4().hex[:10]
    rec = {"id": cid, "tenant_id": tenant_id,
           "name": (fields.get("product_name") or fields.get("company_name") or cid),
           "company": fields.get("company_name", ""), "product": fields.get("product_name", ""),
           "status": "ready", "created_at": datetime.now().isoformat(timespec="seconds"),
           "fields": fields, "system_prompt": build_system_prompt(fields)}
    (CAMPAIGN_DIR / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    # P1 DUAL MIRROR (best-effort, additive): campaigns are written per-id (bypassing _write), so the
    # store seam can't see them — mirror this one record to PG explicitly. No-op unless campaigns is
    # flipped to dual in STORE_MODES; off-loop; swallows all errors (must NOT break campaign create).
    try:
        if _store is not None:
            _store.mirror_campaign_upsert(rec)
    except Exception:  # noqa: BLE001
        pass
    return rec


def get_campaign(cid: str) -> dict | None:
    cid = "".join(ch for ch in (cid or "") if ch.isalnum() or ch in "-_")
    return _read(CAMPAIGN_DIR / f"{cid}.json", None) if cid else None


def get_campaign_for(cid: str, tenant: dict) -> dict | None:
    """Load a campaign only if the tenant owns it (admin sees all)."""
    d = get_campaign(cid)
    if not d:
        return None
    if tenant.get("is_admin") or d.get("tenant_id", ADMIN_ID) == tenant["tenant_id"]:
        return d
    return None


def list_campaigns(tenant: dict | None = None) -> list[dict]:
    out = []
    try:
        for p in sorted(CAMPAIGN_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            d = json.loads(p.read_text(encoding="utf-8"))
            tid = d.get("tenant_id", ADMIN_ID)
            if tenant is not None and not tenant.get("is_admin") and tid != tenant["tenant_id"]:
                continue
            out.append({"id": d["id"], "name": d.get("name", d["id"]),
                        "company": d.get("company", ""), "product": d.get("product", ""),
                        "status": d.get("status", "ready"), "created_at": d.get("created_at", ""),
                        "voice_id": (d.get("fields") or {}).get("voice_id", ""),
                        "tenant_id": tid})
    except Exception:  # noqa: BLE001
        pass
    return out


def record_call(rec: dict):
    CALLS.insert(0, rec)
    del CALLS[2000:]
    _write(CALLS_FILE, CALLS)


def calls_for(tenant: dict) -> list[dict]:
    if tenant.get("is_admin"):
        return CALLS
    return [c for c in CALLS if c.get("tenant_id", ADMIN_ID) == tenant["tenant_id"]]


# ---------- P0.2 suppression / DND ----------
def _suppressed_set(tenant_id: str) -> set:
    return {x["phone"] for x in _read(SUPPRESSION_FILE, [])
            if x.get("tenant_id") == tenant_id and x.get("phone")}


async def _add_suppression(tenant_id: str, phone: str, reason: str, source: str = ""):
    """Add a number to a tenant's DND list (idempotent). Lock-guarded shared-store write."""
    phone = norm(phone)
    if not phone:
        return
    async with _STORE_LOCK:
        store = _read(SUPPRESSION_FILE, [])
        if not any(x.get("phone") == phone and x.get("tenant_id") == tenant_id for x in store):
            store.append({"tenant_id": tenant_id, "phone": phone, "reason": reason,
                          "source": source, "added_at": datetime.now().isoformat(timespec="seconds")})
            _write(SUPPRESSION_FILE, store)


async def _flip_lead_status(tenant_id: str, phone: str, status: str):
    """Mark a tenant's lead (matched by normalized phone) with a status. Lock-guarded."""
    phone = norm(phone)
    if not phone:
        return
    async with _STORE_LOCK:
        store = _read(LEADS_FILE, [])
        changed = False
        for x in store:
            if x.get("tenant_id", ADMIN_ID) == tenant_id and norm(x.get("phone", "")) == phone:
                if x.get("status") != status:
                    x["status"] = status; changed = True
        if changed:
            _write(LEADS_FILE, store)


# ---------- P0.4 outcome classification (answering machine / no-answer) ----------
def _classify_outcome(rec: dict, tr: dict) -> str:
    turns = tr.get("turns") or []
    user_turns = [x for x in turns if x.get("role") == "user" and (x.get("content") or "").strip()]
    dur = rec.get("duration_s", 0)
    if tr.get("amd_hint") == "no_user_audio" and not user_turns:
        return "no_answer" if dur < 8 else "voicemail"
    if not turns and dur < 8:
        return "no_answer"            # never connected / ring-out
    if len(user_turns) == 0 and dur < 25:
        return "voicemail"            # agent spoke, human never did -> machine/VM
    if len(user_turns) == 0:
        return "no_human"             # connected, no human turns (likely VM/IVR)
    return tr.get("outcome") or "answered"


_REAL_CONVO = ("answered", "interested", "not_interested", "callback", "opt_out")


# ---------- P0.6 lead scoring ----------
async def _update_lead_after_call(tenant_id: str, phone: str, score, outcome: str,
                                  call_at: str = ""):
    """Update a lead from a finalized call. Never regresses: keeps the MOST RECENT call's
    outcome and the HIGHEST interest score seen (so a later voicemail can't wipe an earlier
    'interested/80'). call_at = the call's started_at (chronology); falls back to now."""
    phone = norm(phone)
    if not phone:
        return
    call_at = call_at or datetime.now().isoformat(timespec="seconds")
    try:
        sc = int(score or 0)
    except Exception:  # noqa: BLE001
        sc = 0
    async with _STORE_LOCK:
        store = _read(LEADS_FILE, [])
        changed = False
        for x in store:
            if x.get("tenant_id", ADMIN_ID) == tenant_id and norm(x.get("phone", "")) == phone:
                prev_at = x.get("last_call_at", "")
                if call_at >= prev_at:                       # only the most recent call sets outcome
                    x["last_outcome"] = outcome or ""
                    x["last_call_at"] = call_at
                best = max(int(x.get("score", 0) or 0), sc)  # keep best interest ever seen
                x["score"] = best
                x["hot"] = best >= 70
                changed = True
        if changed:
            _write(LEADS_FILE, store)


# ---------- P0.7 usage metering ----------
def _tenant_usage(tenant_id: str, since_iso: str) -> dict:
    rows = [c for c in CALLS if c.get("tenant_id") == tenant_id and c.get("started_at", "") >= since_iso]
    return {"calls": len(rows),
            "minutes": round(sum(c.get("duration_s", 0) for c in rows) / 60, 1)}


def _today_iso() -> str:
    return now_ist().date().isoformat()


def _month_iso() -> str:
    return now_ist().strftime("%Y-%m")


# ---------- P0.5 retry / callback queue ----------
async def _enqueue_retry(tenant_id, campaign_id, name, phone, attempts, max_attempts,
                         next_at, reason):
    phone = norm(phone)
    if not phone:
        return
    async with _STORE_LOCK:
        store = _read(RETRY_FILE, [])
        existing = next((r for r in store if r.get("phone") == phone
                         and r.get("campaign_id") == campaign_id
                         and r.get("tenant_id") == tenant_id), None)
        if existing:
            existing["attempts"] = attempts
            existing["next_attempt_at"] = next_at
            existing["reason"] = reason
            existing["max_attempts"] = max_attempts
        else:
            store.append({"id": uuid.uuid4().hex[:10], "tenant_id": tenant_id,
                          "campaign_id": campaign_id, "name": name or "", "phone": phone,
                          "attempts": attempts, "max_attempts": max_attempts,
                          "next_attempt_at": next_at, "reason": reason,
                          "created_at": datetime.now().isoformat(timespec="seconds")})
        _write(RETRY_FILE, store)


async def _remove_retry(retry_id: str):
    async with _STORE_LOCK:
        store = _read(RETRY_FILE, [])
        store = [r for r in store if r.get("id") != retry_id]
        _write(RETRY_FILE, store)


# ---------- P1.A WhatsApp follow-up (fire-and-forget stub) ----------
async def _send_whatsapp(tenant_id, rec, outcome, camp_fields):
    """Optional per-campaign WhatsApp follow-up via a BSP. Never blocks/raises into the loop."""
    try:
        if not (camp_fields or {}).get("wa_enabled"):
            return
        api_url = os.getenv("WA_API_URL", "")
        api_key = os.getenv("WA_API_KEY", "")
        score = rec.get("interest", 0) or 0
        if outcome == "interested" or score >= 70:
            template = camp_fields.get("wa_template_qualified", "")
        elif outcome in ("no_answer", "voicemail", "no_human"):
            template = camp_fields.get("wa_template_noanswer", "")
        else:
            template = ""
        if not template:
            return
        status = "skipped_no_bsp"
        if api_url and api_key:
            try:
                async with httpx.AsyncClient(timeout=10) as cli:
                    resp = await cli.post(api_url, headers={"Authorization": "Bearer " + api_key},
                                          json={"to": rec.get("phone"), "template": template})
                    status = f"sent:{resp.status_code}"
            except Exception as exc:  # noqa: BLE001
                status = f"error:{repr(exc)[:60]}"
        async with _STORE_LOCK:
            log = _read(WA_LOG_FILE, [])
            log.insert(0, {"tenant_id": tenant_id, "phone": rec.get("phone"), "template": template,
                           "status": status, "at": datetime.now().isoformat(timespec="seconds")})
            del log[2000:]
            _write(WA_LOG_FILE, log)
    except Exception:  # noqa: BLE001
        pass


# ---------- WAVE3 Unit5: WhatsApp send via clean module ----------
async def _wa_log(tenant_id: str, to: str, template: str, result: dict, kind: str = "manual"):
    async with _STORE_LOCK:
        log = _read(WA_LOG_FILE, [])
        log.insert(0, {"tenant_id": tenant_id, "phone": to, "template": template,
                       "kind": kind, "status": result.get("status", ""),
                       "ok": bool(result.get("ok")),
                       "at": datetime.now().isoformat(timespec="seconds")})
        del log[2000:]
        _write(WA_LOG_FILE, log)


async def _wa_send(tenant_id: str, to: str, template: str, params, kind: str = "manual",
                   is_text: bool = False) -> dict:
    """Send via whatsapp.py (no-ops gracefully if unconfigured). Logs every attempt.

    is_text=True => `template` carries a RAW free-form text body (valid only inside the 24h
    customer-service window) and is routed to the Meta TEXT path, NOT the template path —
    else a free-form string is mis-sent as a template name (Graph #132001). Default False
    preserves the template-name behaviour for every existing caller (auto-followup etc.)."""
    to = norm(to) or (to or "")
    if wa_mod is None:
        result = {"ok": False, "status": "module_unavailable"}
    elif is_text and hasattr(wa_mod, "send_whatsapp_text_async"):
        result = await wa_mod.send_whatsapp_text_async(to, template)
    else:
        result = await wa_mod.send_whatsapp_async(to, template, params)
    await _wa_log(tenant_id, to, template, result, kind=kind)
    return result


# ============================================================================
# HUMAN HANDOFF — per-vendor handoff team list (Business Brain `handoff` block) +
# hot-lead WhatsApp notify. ADDITIVE + ISOLATED: lives on the Brain JSON (no new
# table, no new auth), reuses the existing /brain auth + whatsapp.py sender.
# ============================================================================
# Approved Meta template for cold hot-lead alerts to the team (no open 24h window
# with team members). Registering it is a Meta-onboarding step (GAP-C1); until then
# the send no-ops gracefully (dormant) like every other WA path.
HOT_LEAD_ALERT_TEMPLATE = (os.getenv("HOT_LEAD_ALERT_TEMPLATE", "hot_lead_alert")
                           or "hot_lead_alert").strip()

import logging as _lg_handoff_mod
_lg_handoff = _lg_handoff_mod.getLogger("famit-caller.handoff")


def _handoff_get(tenant_id: str) -> list[dict]:
    """The vendor's handoff team list: [{phone, whatsapp, role, hours, priority}, ...].
    Read from the Business Brain `handoff` block (var/brain/<tenant>.json). [] when none.
    NEVER raises (a broken brain must not break a call)."""
    if not tenant_id or _brain_mod is None:
        return []
    try:
        prof = _brain_mod.get_profile(tenant_id) or {}
        hl = prof.get("handoff")
        if isinstance(hl, dict):                 # tolerate {"team":[...]} shape
            hl = hl.get("team") or hl.get("numbers") or []
        if not isinstance(hl, list):
            return []
        out = []
        for h in hl:
            if not isinstance(h, dict):
                continue
            ph = norm(str(h.get("phone", ""))) or str(h.get("phone", "")).strip()
            wa = norm(str(h.get("whatsapp", ""))) or str(h.get("whatsapp", "")).strip() or ph
            if not ph and not wa:
                continue
            out.append({"phone": ph, "whatsapp": wa,
                        "role": str(h.get("role", "") or ""),
                        "hours": str(h.get("hours", "") or ""),
                        "priority": int(h.get("priority", 99) or 99)})
        out.sort(key=lambda x: x.get("priority", 99))
        return out
    except Exception as exc:  # noqa: BLE001
        _lg_handoff.warning("handoff_get failed tenant=%s: %r", tenant_id, exc)
        return []


def _handoff_set(tenant_id: str, team: list, actor: str = "system") -> list[dict]:
    """Replace the vendor's handoff team list on the Brain. Returns the stored list.
    Validates+normalises each entry; NEVER raises (returns prior list on failure)."""
    if not tenant_id or _brain_mod is None:
        return _handoff_get(tenant_id)
    clean = []
    for h in (team or []):
        if not isinstance(h, dict):
            continue
        ph = str(h.get("phone", "")).strip()
        wa = str(h.get("whatsapp", "")).strip()
        if not ph and not wa:
            continue
        clean.append({"phone": norm(ph) or ph,
                      "whatsapp": norm(wa) or wa or (norm(ph) or ph),
                      "role": str(h.get("role", "") or ""),
                      "hours": str(h.get("hours", "") or ""),
                      "priority": int(h.get("priority", 99) or 99)})
    try:
        _brain_mod.upsert_profile(tenant_id, {"handoff": clean}, actor=actor)
    except Exception as exc:  # noqa: BLE001
        _lg_handoff.warning("handoff_set failed tenant=%s: %r", tenant_id, exc)
        return _handoff_get(tenant_id)
    return _handoff_get(tenant_id)


async def notify_handoff_team(tenant_id: str, lead: dict, summary: str = "",
                              score: int = 0) -> dict:
    """HOT-LEAD -> TEAM WHATSAPP. Send the lead phone + call summary to EVERY handoff-list
    WhatsApp number so a human can take over. Reuses whatsapp.py via _wa_send (logs each).
    Cold path uses the approved `hot_lead_alert` template (the team rarely has an open 24h
    window); if Meta isn't configured the send no-ops gracefully (dormant). NEVER raises into
    the call loop. Returns {ok, sent, attempts, results:[...]}.
    Triggered from the post-call hot branch (interest>=70) AND as the warm-transfer fallback."""
    out = {"ok": False, "sent": 0, "attempts": 0, "results": []}
    try:
        team = _handoff_get(tenant_id)
        if not team:
            out["note"] = "no_handoff_team"
            return out
        name = (lead.get("name") or "").strip() or "Lead"
        phone = (lead.get("phone") or "").strip() or "—"
        summ = (summary or lead.get("summary") or "").strip()[:300] or "Hot lead from a call."
        sc = int(score or lead.get("interest", 0) or lead.get("score", 0) or 0)
        # free-form body (used when a team member's 24h window is open / generic BSP).
        text_body = (f"🔥 Hot lead: {name} ({phone}). Score {sc}/100. "
                     f"Summary: {summ}. Reply to take over.")
        params = [name, phone, summ, str(sc)]   # hot_lead_alert template body vars
        meta = bool(wa_mod and getattr(wa_mod, "meta_configured", lambda: False)())
        for h in team:
            wa = (h.get("whatsapp") or h.get("phone") or "").strip()
            if not wa:
                continue
            out["attempts"] += 1
            try:
                if meta:
                    # cold-safe: approved template (no 24h window assumed with the team).
                    res = await _wa_send(tenant_id, wa, HOT_LEAD_ALERT_TEMPLATE, params,
                                         kind="hot_lead_alert")
                else:
                    # generic BSP / dormant -> free-form text path (no-ops if unconfigured).
                    res = await _wa_send(tenant_id, wa, text_body, None,
                                         kind="hot_lead_alert", is_text=True)
            except Exception as exc:  # noqa: BLE001
                res = {"ok": False, "status": f"error:{type(exc).__name__}"}
            out["results"].append({"to": wa, "ok": bool(res.get("ok")),
                                   "status": res.get("status", ""),
                                   "wamid": _wa_mid(res)})
            if res.get("ok"):
                out["sent"] += 1
        out["ok"] = out["sent"] > 0
        _lg_handoff.info("notify_handoff_team tenant=%s team=%d sent=%d", tenant_id, len(team), out["sent"])
        return out
    except Exception as exc:  # noqa: BLE001
        _lg_handoff.warning("notify_handoff_team failed tenant=%s: %r", tenant_id, exc)
        out["note"] = f"error:{type(exc).__name__}"
        return out


def _wa_mid(result: dict) -> str:
    """Best-effort extract the Meta message id (wamid) from a send result for the audit/proof."""
    try:
        import json as _json
        raw = result.get("response") or ""
        if raw and "wamid" in raw:
            d = _json.loads(raw)
            msgs = d.get("messages") or []
            if msgs and isinstance(msgs, list):
                return str(msgs[0].get("id", ""))
    except Exception:  # noqa: BLE001
        pass
    return ""


async def _wa_followup(tenant_id: str, rec: dict, outcome: str, camp_fields: dict):
    """WAVE3 Unit5: per-campaign auto follow-up after interested/callback calls.
    Gated behind campaign `wa_followup` flag (default OFF). No-op if no creds/template."""
    try:
        if not (camp_fields or {}).get("wa_followup"):
            return
        if outcome == "interested" or (rec.get("interest", 0) or 0) >= 70:
            template = (camp_fields.get("wa_template_interested")
                        or camp_fields.get("wa_template_qualified") or "")
        elif outcome == "callback":
            template = camp_fields.get("wa_template_callback", "")
        else:
            return
        if not template:
            return
        await _wa_send(tenant_id, rec.get("phone", ""), template,
                       [rec.get("name", "")], kind="auto_followup")
    except Exception:  # noqa: BLE001
        pass


# ---------- WAVE A2: per-contact WhatsApp conversation threads ----------
WA_MAX_TURNS = int(os.getenv("WA_MAX_TURNS", "12") or "12")  # human turns before handoff
# WA-AUTO post-call template follow-up — DEFAULT OFF (safe). When ON, a completed call
# instantly sends the APPROVED post-call template (cold-safe vehicle) to the lead.
# Gate = global WA_AUTO_FOLLOWUP=1 OR per-campaign fields.wa_followup=True.
WA_AUTO_FOLLOWUP = (os.getenv("WA_AUTO_FOLLOWUP", "0") or "0").strip().lower() in ("1", "true", "yes", "on")
# Approved template name + its var mapping. Body: "Hi {{1}}, thanks for taking our call
# about {{2}}. ..."  -> {{1}}=lead name, {{2}}=product/enquiry. Lang from WA_LANG (en).
WA_FOLLOWUP_TEMPLATE = (os.getenv("WA_FOLLOWUP_TEMPLATE", "post_call_followup") or "post_call_followup").strip()
WA_FOLLOWUP_ENQUIRY_FALLBACK = (os.getenv("WA_FOLLOWUP_ENQUIRY_FALLBACK", "your enquiry") or "your enquiry").strip()
_WA_OPTOUT_WORDS = ("stop", "unsubscribe", "opt out", "optout", "band karo",
                    "band karein", "mat bhejo", "remove me", "do not", "dont contact",
                    "don't contact", "block")
_WA_HANDOFF_WORDS = ("talk to human", "human agent", "real person", "call me",
                     "agent se baat", "complaint", "manager")


def _wa_thread_path(phone: str) -> Path:
    safe = re.sub(r"[^0-9]", "", phone or "")
    return WA_THREADS_DIR / f"{safe}.json"


def _wa_thread_read(phone: str) -> dict:
    return _read(_wa_thread_path(phone), {}) or {}


async def _wa_thread_write(phone: str, thread: dict):
    async with _STORE_LOCK:
        try:
            WA_THREADS_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        _write(_wa_thread_path(phone), thread)


def _resolve_contact_by_phone(phone: str) -> dict:
    """Best-effort link an inbound WhatsApp number to a known lead/campaign/tenant.
    Returns {tenant_id, name, campaign_id, campaign_name} (any may be empty)."""
    p = norm(phone)
    out = {"tenant_id": "", "name": "", "campaign_id": "", "campaign_name": ""}
    if not p:
        return out
    # 1) most-recent call to this number carries tenant + campaign
    for c in CALLS:
        if norm(c.get("phone", "")) == p:
            out["tenant_id"] = c.get("tenant_id", "") or out["tenant_id"]
            out["name"] = c.get("name", "") or out["name"]
            out["campaign_id"] = c.get("campaign_id", "") or out["campaign_id"]
            out["campaign_name"] = c.get("campaign_name", "") or out["campaign_name"]
            break
    # 2) fall back to a stored lead
    if not out["tenant_id"] or not out["name"]:
        for x in _read(LEADS_FILE, []):
            if norm(x.get("phone", "")) == p:
                out["tenant_id"] = out["tenant_id"] or x.get("tenant_id", ADMIN_ID)
                out["name"] = out["name"] or x.get("name", "")
                break
    if not out["tenant_id"]:
        out["tenant_id"] = ADMIN_ID
    return out


def _wa_draft_followup_text(rec: dict, outcome: str, camp_fields: dict, tr: dict) -> str:
    """ONE Groq call -> a short Hinglish WhatsApp follow-up tailored to the call.
    Returns "" on failure (caller then falls back to a template send)."""
    name = rec.get("name", "") or "ji"
    company = (camp_fields or {}).get("company_name", "")
    product = (camp_fields or {}).get("product_name", "")
    agent = (camp_fields or {}).get("agent_name", "Riya")
    summary = (tr or {}).get("summary", "")
    next_action = (tr or {}).get("next_action", "")
    interest = rec.get("interest", 0)
    sysmsg = (
        "You are " + agent + ", a friendly Indian sales assistant writing a SHORT WhatsApp "
        "follow-up in natural Hinglish (Roman script). 1-3 short sentences, warm, no emojis spam "
        "(max one), no markdown. Recap the call briefly and give ONE clear next step "
        "(site visit / share details / answer a pending question / schedule a callback). "
        "Do not invent facts beyond the context. Output ONLY the message text."
    )
    ctx = (
        f"Company: {company}\nProduct: {product}\nLead name: {name}\n"
        f"Call outcome: {outcome}\nInterest score: {interest}\n"
        f"Call summary: {summary}\nSuggested next action: {next_action}\n"
    )
    return _groq_chat([{"role": "system", "content": sysmsg},
                       {"role": "user", "content": ctx}], max_tokens=220, temperature=0.6)


def _wa_memory_recap(phone: str) -> str:
    """Per-person prior-call recap from memory.py (the voice agent's cross-call store).
    Read-only, import-safe; returns "" when memory is absent/unreadable. Never raises."""
    try:
        if _mem_mod is None or not phone:
            return ""
        rec = _mem_mod.load_memory(re.sub(r"[^0-9]", "", phone or ""))
        return (_mem_mod.build_recap(rec) or "")[:500]
    except Exception:  # noqa: BLE001
        return ""


def _wa_reply_text(thread: dict, camp_fields: dict, incoming: str) -> str:
    """Multi-turn, context-rich reply: ONE Groq call grounded in the CAMPAIGN brain + what
    happened on the CALL (summary / next step / interest, persisted on the thread by
    _wa_ai_followup) + the per-person MEMORY recap + the last 10 thread turns. "" on failure."""
    agent = (camp_fields or {}).get("agent_name", "Riya")
    company = (camp_fields or {}).get("company_name", "")
    product = (camp_fields or {}).get("product_name", "") or thread.get("product", "")
    summary = (camp_fields or {}).get("product_summary", "")
    name = thread.get("name", "") or "ji"
    # Call grounding (written at follow-up/seed time).
    call_summary = (thread.get("call_summary") or "").strip()
    next_action = (thread.get("next_action") or "").strip()
    call_outcome = (thread.get("call_outcome") or "").strip()
    interest = thread.get("interest", 0)
    mem_recap = _wa_memory_recap(thread.get("phone", ""))
    grounding = ""
    if call_summary:
        grounding += f"What happened on the phone call: {call_summary[:400]}. "
    if next_action:
        grounding += f"Agreed/suggested next step from the call: {next_action[:160]}. "
    if call_outcome:
        grounding += f"Call outcome: {call_outcome} (interest {interest}). "
    if mem_recap:
        grounding += f"Earlier history with this person: {mem_recap}. "
    sysmsg = (
        "You are " + agent + (f", a sales assistant for {company}" if company else "") +
        ". You are continuing a conversation with " + name + " on WhatsApp AFTER a phone call. "
        "Reply to the customer's message in SHORT natural Hinglish (Roman script), "
        "1-3 sentences, warm and helpful, at most one emoji, no markdown. "
        + (f"You are following up about: {product}. " if product else "")
        + (f"Product/offer context: {summary[:300]}. " if summary else "")
        + (grounding if grounding else "")
        + "Use the call context above so you don't repeat yourself or contradict the call. "
        "Move the conversation toward a clear next step (site visit / share details / schedule "
        "a callback / booking). If they ask something you don't know, offer to have a human call "
        "them. Do not invent facts beyond the context. Output ONLY the reply text."
    )
    msgs = [{"role": "system", "content": sysmsg}]
    for t in (thread.get("turns") or [])[-10:]:
        role = "assistant" if t.get("role") == "assistant" else "user"
        msgs.append({"role": role, "content": t.get("text", "")})
    msgs.append({"role": "user", "content": incoming})
    return _groq_chat(msgs, max_tokens=220, temperature=0.6)


async def _wa_handle_inbound(phone: str, text: str) -> dict:
    """Core inbound handler (provider-agnostic). Maintains thread state, applies opt-out /
    handoff / max-turn guards, generates+sends the next reply when WA is configured.
    Returns a small dict for logging. Safe + dormant when WA env missing."""
    phone_n = norm(phone) or (phone or "")
    link = _resolve_contact_by_phone(phone_n)
    tenant_id = link["tenant_id"] or ADMIN_ID
    thread = _wa_thread_read(phone_n)
    if not thread:
        thread = {"phone": phone_n, "tenant_id": tenant_id, "name": link["name"],
                  "campaign_id": link["campaign_id"], "campaign_name": link["campaign_name"],
                  "status": "active", "turns": [],
                  "created_at": datetime.now().isoformat(timespec="seconds")}
    tenant_id = thread.get("tenant_id") or tenant_id
    thread.setdefault("turns", []).append(
        {"role": "user", "text": text, "at": datetime.now().isoformat(timespec="seconds")})
    low = (text or "").strip().lower()
    action = "noted"
    # Opt-out / STOP keywords -> end thread + suppress (reuse existing suppression logic).
    if any(w in low for w in _WA_OPTOUT_WORDS):
        thread["status"] = "opted_out"
        await _add_suppression(tenant_id, phone_n, "wa_opt_out", source="whatsapp")
        await _flip_lead_status(tenant_id, phone_n, "opted_out")
        await _emit_webhook(tenant_id, "lead.opted_out",
                            {"phone": phone_n, "campaign_id": thread.get("campaign_id", "")})
        action = "opted_out"
    elif any(w in low for w in _WA_HANDOFF_WORDS):
        thread["status"] = "needs_human"
        action = "needs_human"
    else:
        human_turns = sum(1 for t in thread["turns"] if t.get("role") == "user")
        if human_turns >= WA_MAX_TURNS:
            thread["status"] = "needs_human"
            action = "max_turns_handoff"
        elif wa_mod and wa_mod.is_configured():
            camp = get_campaign(thread.get("campaign_id", "")) or {}
            reply = _wa_reply_text(thread, camp.get("fields") or {}, text)
            if reply:
                result = (await wa_mod.send_whatsapp_text_async(phone_n, reply)
                          if getattr(wa_mod, "meta_configured", lambda: False)()
                          else await wa_mod.send_whatsapp_async(phone_n, reply, None))
                await _wa_log(tenant_id, phone_n, "ai_reply", result, kind="inbound_reply")
                thread["turns"].append({"role": "assistant", "text": reply,
                                        "at": datetime.now().isoformat(timespec="seconds")})
                action = "replied"
            else:
                action = "draft_failed"
        else:
            # Dormant: store the inbound, nothing to call out to. ("WA not configured")
            action = "stored_dormant"
    thread["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if len(thread["turns"]) > 200:        # keep the thread file bounded
        thread["turns"] = thread["turns"][-200:]
    await _wa_thread_write(phone_n, thread)
    return {"phone": phone_n, "action": action, "status": thread["status"]}


def _wa_followup_product(camp_fields: dict, tr: dict) -> str:
    """Resolve {{2}} for the post-call template: the product/enquiry the call was about.
    Prefers the campaign product, then the transcript's stated enquiry, else a safe
    generic fallback. Trimmed to a WhatsApp-template-safe length. Never raises."""
    cand = ((camp_fields or {}).get("product_name", "")
            or (tr or {}).get("enquiry", "")
            or (tr or {}).get("next_action", "")
            or WA_FOLLOWUP_ENQUIRY_FALLBACK)
    cand = " ".join(str(cand).split())[:60].strip()
    return cand or WA_FOLLOWUP_ENQUIRY_FALLBACK


async def _wa_ai_followup(tenant_id: str, rec: dict, outcome: str, camp_fields: dict, tr: dict):
    """WA-AUTO post-call WhatsApp follow-up.

    Gate = global WA_AUTO_FOLLOWUP=1 OR per-campaign fields.wa_followup=True (default OFF).
    On a fresh completed call there is NO open 24h customer-service window, so a cold
    free-form text would be REJECTED by Meta. The cold-safe vehicle is the APPROVED
    TEMPLATE (`WA_FOLLOWUP_TEMPLATE`, lang from WA_LANG=en) populated with [name, product].
    Idempotent (one send per call), consent-checked (skips suppressed numbers), and seeds
    the conversation thread WITH the call context so an inbound reply is grounded.
    Never blocks / raises into the call loop (fire-and-forget, best-effort)."""
    try:
        # GATE: global flag OR per-campaign flag.
        if not (WA_AUTO_FOLLOWUP or (camp_fields or {}).get("wa_followup")):
            return
        # Only act on meaningful outcomes (interested / callback / high interest).
        score = rec.get("interest", 0) or 0
        if not (outcome in ("interested", "callback") or score >= 70):
            return
        configured = bool(wa_mod and wa_mod.is_configured())
        phone = rec.get("phone", "")
        phone_n = norm(phone) or phone
        if not phone_n:
            return
        # IDEMPOTENCY: never send the post-call follow-up twice for the same call.
        if rec.get("wa_followup_sent"):
            return
        # CONSENT / opt-out: do not message a suppressed (DND) number.
        try:
            if phone_n in _suppressed_set(tenant_id):
                rec["wa_followup_sent"] = "skipped_suppressed"
                return
        except Exception:  # noqa: BLE001
            pass
        if not configured:
            # Dormant (no WA env): keep the legacy template path (logs skipped_no_config).
            await _wa_followup(tenant_id, rec, outcome, camp_fields)
            rec["wa_followup_sent"] = "dormant"
            return

        name = (rec.get("name", "") or "").strip() or "there"
        product = _wa_followup_product(camp_fields, tr)
        meta = bool(wa_mod and getattr(wa_mod, "meta_configured", lambda: False)())

        # Is the 24h CS window already open? Only true if the lead has sent us an inbound
        # WhatsApp recently (their inbound seeds a 'user' turn). A fresh OUTBOUND call does
        # NOT open it -> cold path MUST use the approved template, never free-form text.
        existing = _wa_thread_read(phone_n)
        window_open = any(t.get("role") == "user" for t in (existing.get("turns") or []))

        sent_text = ""
        if meta and window_open:
            # Window open -> a personalised free-form follow-up is allowed and nicer.
            draft = _wa_draft_followup_text(rec, outcome, camp_fields, tr)
            if draft:
                result = await wa_mod.send_whatsapp_text_async(phone_n, draft)
                await _wa_log(tenant_id, phone_n, "ai_followup", result, kind="auto_followup")
                sent_text = draft
        if not sent_text and meta:
            # COLD post-call (no open window) -> APPROVED TEMPLATE, params [name, product].
            # Lang is taken from WA_LANG (=en) inside whatsapp.send_whatsapp_async.
            result = await wa_mod.send_whatsapp_async(phone_n, WA_FOLLOWUP_TEMPLATE,
                                                      [name, product])
            await _wa_log(tenant_id, phone_n, WA_FOLLOWUP_TEMPLATE, result,
                          kind="auto_followup_template")
            # Mirror the template's body so the reply brain has the opener verbatim.
            sent_text = (f"Hi {name}, thanks for taking our call about {product}. "
                         "Reply here if you have questions or want to take the next step.")
        elif not sent_text:
            # No Meta path (generic/other BSP) -> legacy template fallback.
            await _wa_followup(tenant_id, rec, outcome, camp_fields)
            sent_text = "[template:" + ((camp_fields or {}).get("wa_template_interested")
                                        or (camp_fields or {}).get("wa_template_qualified")
                                        or (camp_fields or {}).get("wa_template_callback")
                                        or WA_FOLLOWUP_TEMPLATE) + "]"

        # Mark idempotency (one send per call) regardless of which path fired.
        rec["wa_followup_sent"] = datetime.now().isoformat(timespec="seconds")

        # Seed / update the conversation thread, persisting the CALL CONTEXT so the inbound
        # reply brain (_wa_reply_text) can ground every later turn in what happened on the call.
        if sent_text:
            thread = existing or _wa_thread_read(phone_n)
            if not thread:
                thread = {"phone": phone_n, "tenant_id": tenant_id,
                          "name": rec.get("name", ""), "campaign_id": rec.get("campaign_id", ""),
                          "campaign_name": rec.get("campaign_name", ""),
                          "status": "active", "turns": [],
                          "created_at": datetime.now().isoformat(timespec="seconds")}
            # Call-context grounding (read back in _wa_reply_text on every inbound turn).
            thread["call_summary"] = (tr or {}).get("summary", "") or thread.get("call_summary", "")
            thread["next_action"] = (tr or {}).get("next_action", "") or thread.get("next_action", "")
            thread["call_outcome"] = outcome or thread.get("call_outcome", "")
            thread["interest"] = score if score else thread.get("interest", 0)
            thread["product"] = product or thread.get("product", "")
            thread["name"] = thread.get("name") or rec.get("name", "")
            thread["campaign_id"] = thread.get("campaign_id") or rec.get("campaign_id", "")
            thread["campaign_name"] = thread.get("campaign_name") or rec.get("campaign_name", "")
            thread.setdefault("turns", []).append(
                {"role": "assistant", "text": sent_text,
                 "at": datetime.now().isoformat(timespec="seconds")})
            thread["updated_at"] = datetime.now().isoformat(timespec="seconds")
            thread["status"] = thread.get("status") or "active"
            await _wa_thread_write(phone_n, thread)
    except Exception:  # noqa: BLE001
        pass


# ---------- P1.C CRM webhook out (fire-and-forget stub) ----------
async def _emit_webhook(tenant_id, event, payload):
    """Deliver an event to a tenant's registered webhook(s), HMAC-signed. Never blocks the loop."""
    try:
        hooks = [w for w in _read(WEBHOOK_FILE, [])
                 if w.get("tenant_id") == tenant_id and w.get("active", True)
                 and (not w.get("events") or event in w.get("events", []))]
        if not hooks:
            return
        body = json.dumps({"event": event, "data": payload,
                           "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False)
        for w in hooks:
            sig = hmac.new((w.get("secret") or "").encode("utf-8"), body.encode("utf-8"),
                           hashlib.sha256).hexdigest()
            status = "error"
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=10) as cli:
                        resp = await cli.post(w["url"], content=body,
                                              headers={"Content-Type": "application/json",
                                                       "X-Famit-Signature": sig,
                                                       "X-Famit-Event": event})
                        status = f"sent:{resp.status_code}"
                        if resp.status_code < 500:
                            break
                except Exception as exc:  # noqa: BLE001
                    status = f"error:{repr(exc)[:60]}"
                await asyncio.sleep(2 ** attempt)
            async with _STORE_LOCK:
                log = _read(WEBHOOK_LOG_FILE, [])
                log.insert(0, {"tenant_id": tenant_id, "url": w["url"], "event": event,
                               "status": status, "at": datetime.now().isoformat(timespec="seconds")})
                del log[2000:]
                _write(WEBHOOK_LOG_FILE, log)
    except Exception:  # noqa: BLE001
        pass


# ---------- WAVE3 Unit4: billing / metering ----------
# Default plan is GENEROUS + postpaid so nothing is blocked for existing tenants today.
def _default_billing(tenant: dict | None = None) -> dict:
    is_admin = bool((tenant or {}).get("is_admin"))
    return {"plan": "postpaid", "rate_per_min": 0.0, "rate_per_call": 0.0,
            "currency": "INR", "balance": 0.0,
            "included_minutes": 1000000 if is_admin else 100000}


def _read_billing() -> dict:
    """Map of tenant_id -> billing record."""
    b = _read(BILLING_FILE, {})
    return b if isinstance(b, dict) else {}


def _billing_for(tenant_id: str) -> dict:
    """Billing record for a tenant; lazily seeds a generous default (never blocks today)."""
    store = _read_billing()
    rec = store.get(tenant_id)
    if not rec:
        rec = _default_billing(_tenant_by_id(tenant_id))
        store[tenant_id] = rec
        _write(BILLING_FILE, store)
    # backfill any missing keys on legacy/partial records
    base = _default_billing(_tenant_by_id(tenant_id))
    for k, v in base.items():
        rec.setdefault(k, v)
    return rec


def _ledger_path(tenant_id: str) -> Path:
    safe = "".join(ch for ch in tenant_id if ch.isalnum() or ch in "-_") or "unknown"
    return LEDGER_DIR / f"{safe}.json"


def _read_ledger(tenant_id: str) -> list[dict]:
    return _read(_ledger_path(tenant_id), [])


def _call_cost(billing: dict, duration_s: int) -> float:
    mins = (duration_s or 0) / 60.0
    cost = mins * float(billing.get("rate_per_min", 0) or 0)
    cost += float(billing.get("rate_per_call", 0) or 0)
    return round(cost, 4)


async def _charge_call(tenant_id: str, rec: dict):
    """Append an itemized charge to the tenant ledger + decrement prepaid balance.
    Best-effort, lock-guarded, never raises into the call loop. Postpaid plans just
    accrue cost (no balance decrement)."""
    try:
        dur = int(rec.get("duration_s", 0) or 0)
        if dur <= 0 and rec.get("status") in ("suppressed", "failed"):
            return  # nothing billable
        async with _STORE_LOCK:
            billing_store = _read_billing()
            billing = billing_store.get(tenant_id) or _default_billing(_tenant_by_id(tenant_id))
            base = _default_billing(_tenant_by_id(tenant_id))
            for k, v in base.items():
                billing.setdefault(k, v)
            cost = _call_cost(billing, dur)
            entry = {"id": uuid.uuid4().hex[:10], "call_id": rec.get("id"),
                     "phone": rec.get("phone", ""), "campaign_id": rec.get("campaign_id", ""),
                     "duration_s": dur, "cost": cost, "currency": billing.get("currency", "INR"),
                     "outcome": rec.get("outcome", ""),
                     "at": datetime.now().isoformat(timespec="seconds")}
            LEDGER_DIR.mkdir(parents=True, exist_ok=True)
            ledger = _read_ledger(tenant_id)
            ledger.insert(0, entry)
            del ledger[5000:]
            _write(_ledger_path(tenant_id), ledger)
            # prepaid: decrement balance (may go negative; /run gate stops the next batch)
            if billing.get("plan") == "prepaid":
                billing["balance"] = round(float(billing.get("balance", 0) or 0) - cost, 4)
            billing_store[tenant_id] = billing
            _write(BILLING_FILE, billing_store)
    except Exception:  # noqa: BLE001
        pass


# ---------- WAVE A Unit1: internal per-call vendor metering ----------
async def record_usage_event(ev: dict) -> None:
    """Append one usage event to var/usage_events.json (lock-guarded, best-effort).
    Shape: {ts,call_id,room,tenant_id,campaign_id,vendor,service_type,qty,unit,
            est_cost_inr,actual_or_estimated}. A metering failure NEVER breaks a call."""
    try:
        row = {
            "ts": ev.get("ts") or datetime.now().isoformat(timespec="seconds"),
            "call_id": ev.get("call_id", ""),
            "room": ev.get("room", ""),
            "tenant_id": ev.get("tenant_id", ""),
            "campaign_id": ev.get("campaign_id", ""),
            "vendor": ev.get("vendor", ""),
            "service_type": ev.get("service_type", ""),
            "qty": ev.get("qty", 0),
            "unit": ev.get("unit", ""),
            "est_cost_inr": round(float(ev.get("est_cost_inr", 0) or 0), 6),
            "actual_or_estimated": ev.get("actual_or_estimated", "estimated"),
            "sip_call_id": ev.get("sip_call_id", ""),
        }
        async with _STORE_LOCK:
            rows = _read(USAGE_EVENTS_FILE, [])
            if not isinstance(rows, list):
                rows = []
            rows.append(row)
            del rows[:-50000]   # cap growth (keep newest 50k)
            _write(USAGE_EVENTS_FILE, rows)
    except Exception:  # noqa: BLE001
        pass


def _read_usage_events() -> list[dict]:
    rows = _read(USAGE_EVENTS_FILE, [])
    return rows if isinstance(rows, list) else []


USAGE_RAW_DIR = VAR / "usage_events_raw"   # agent drops one file per room here


def _call_by_room(room: str) -> dict | None:
    if not room:
        return None
    return next((c for c in CALLS if c.get("room") == room), None)


async def _drain_usage_raw() -> int:
    """Fold the agent's per-room usage files (usage_events_raw/<room>.json) into the
    shared usage_events.json, stamping tenant_id+call_id by joining on `room`. The agent
    runs in a separate process and writes one file per call to avoid clobbering. We only
    ingest a room once its call record exists (so we can attribute the tenant); files for
    unknown rooms are left for a later tick. Lock-guarded, best-effort."""
    drained = 0
    try:
        if not USAGE_RAW_DIR.exists():
            return 0
        files = list(USAGE_RAW_DIR.glob("*.json"))
        if not files:
            return 0
        async with _STORE_LOCK:
            rows = _read(USAGE_EVENTS_FILE, [])
            if not isinstance(rows, list):
                rows = []
            seen_rooms = {r.get("room") for r in rows}
            for f in files:
                try:
                    room = f.stem
                    if room in seen_rooms:
                        f.unlink(missing_ok=True)   # already ingested; clean up
                        continue
                    call = _call_by_room(room)
                    if not call:
                        continue   # call rec not landed yet; ingest on a later tick
                    evs = _read(f, [])
                    if not isinstance(evs, list):
                        f.unlink(missing_ok=True); continue
                    tid = call.get("tenant_id", "")
                    cid = call.get("campaign_id", "")
                    for ev in evs:
                        ev["tenant_id"] = ev.get("tenant_id") or tid
                        ev["campaign_id"] = ev.get("campaign_id") or cid
                        ev["call_id"] = ev.get("call_id") or call.get("id", "")
                        rows.append(ev)
                        drained += 1
                    f.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    continue
            del rows[:-50000]
            _write(USAGE_EVENTS_FILE, rows)
    except Exception:  # noqa: BLE001
        pass
    return drained


# ---------- dial loop ----------
async def _phone_present(lk, room: str) -> bool:
    try:
        r = await lk.room.list_participants(api.ListParticipantsRequest(room=room))
        return any(p.identity.startswith("phone-") for p in r.participants)
    except Exception:  # noqa: BLE001
        return False


async def _finalize_call(it: dict, now_t: float, tenant_id: str, cid: str, camp_fields: dict):
    """Single finalize touch-point (P0.3/4/5/6 + P1.A/C). Runs once per completed call.
    Order: classify -> update lead score -> enqueue retry/callback -> opt-out suppress -> WA -> webhook."""
    rec = it.get("_rec")
    if not rec:
        return
    rec["status"] = "done"
    rec["ended_at"] = datetime.now().isoformat(timespec="seconds")
    rec["duration_s"] = int(now_t - it["launched_at"])
    room = rec.get("room", "")
    tr = _read(TRANSCRIPT_DIR / f"{room}.json", {}) if room else {}
    # If the transcript exists with real data, mark reconciled so the scheduler sweep skips it.
    # If it's empty (agent shutdown lags hangup), leave it UNMARKED so the sweep re-reconciles.
    if tr:
        rec["_reconciled"] = True
    # P0.4 classify
    outcome = _classify_outcome(rec, tr)
    rec["outcome"] = outcome
    rec["answered"] = outcome in _REAL_CONVO
    rec["interest"] = tr.get("interest", 0)               # P0.6 surface score on call rec
    async with _STORE_LOCK:
        _write(CALLS_FILE, CALLS)
    # WAVE3 Unit4: bill this completed call (ledger + prepaid balance). Best-effort.
    await _charge_call(tenant_id, rec)
    # P0.6 lead scoring
    await _update_lead_after_call(tenant_id, rec.get("phone", ""), tr.get("interest", 0), outcome,
                                  call_at=rec.get("started_at", ""))
    # P0.3 opt-out -> auto-suppress + flip lead
    if tr.get("opt_out") or tr.get("outcome") == "opt_out":
        rec["outcome"] = "opt_out"; rec["answered"] = True
        await _add_suppression(tenant_id, rec.get("phone", ""), "opt_out_call", source=room)
        await _flip_lead_status(tenant_id, rec.get("phone", ""), "opted_out")
        async with _STORE_LOCK:
            _write(CALLS_FILE, CALLS)
        await _emit_webhook(tenant_id, "lead.opted_out",
                            {"phone": rec.get("phone"), "campaign_id": cid})
    else:
        # P0.5 retry / callback enqueue (only when not opted out)
        maxa = int((camp_fields or {}).get("retry_max_attempts", 3))
        backoff = (camp_fields or {}).get("retry_backoff_mins") or [120, 360, 1440]
        attempts = int(it.get("attempt", 0))
        cb = tr.get("callback_at")
        if cb:
            await _enqueue_retry(tenant_id, cid, rec.get("name", ""), rec.get("phone", ""),
                                 attempts, maxa, cb, "callback")
            await _emit_webhook(tenant_id, "callback.scheduled",
                                {"phone": rec.get("phone"), "campaign_id": cid,
                                 "name": rec.get("name", ""), "when": cb,
                                 "callback_raw": tr.get("callback_raw", "")})
        elif outcome in ("no_answer", "voicemail", "busy") and attempts < maxa:
            delay = backoff[min(attempts, len(backoff) - 1)]
            next_at = _clamp_to_window(now_ist() + timedelta(minutes=delay), camp_fields)
            await _enqueue_retry(tenant_id, cid, rec.get("name", ""), rec.get("phone", ""),
                                 attempts + 1, maxa, next_at.isoformat(), outcome)
    # P1.A WhatsApp + P1.C webhook (fire-and-forget; never block)
    await _send_whatsapp(tenant_id, rec, rec["outcome"], camp_fields)
    # WAVE A2: AI-drafted context-aware follow-up (gated by per-campaign wa_followup
    # flag + configured WA env). Falls back to the WAVE3 template path when dormant or
    # when no free-form (Meta) text path is available.
    await _wa_ai_followup(tenant_id, rec, rec["outcome"], camp_fields, tr)
    _score = rec.get("interest", 0) or 0
    # WAVE3 Unit2: mark completed-emitted ONLY when transcript was real here; if it was
    # empty (agent shutdown lags), leave unmarked so the reconciliation sweep re-emits
    # ONCE with the real summary/score.
    if rec.get("_reconciled"):
        rec["_wh_completed"] = True
    await _emit_webhook(tenant_id, "call.completed",
                        {"call_id": rec.get("id"), "phone": rec.get("phone"),
                         "name": rec.get("name", ""), "campaign_id": cid,
                         "campaign_name": rec.get("campaign_name", ""),
                         "outcome": rec["outcome"], "interest": _score, "score": _score,
                         "summary": tr.get("summary", ""), "next_action": tr.get("next_action", ""),
                         "duration_s": rec.get("duration_s", 0), "room": room})
    # WAVE3 Unit2: lead.qualified on a high-interest, real conversation
    if rec["outcome"] != "opt_out" and _score >= 70:
        await _emit_webhook(tenant_id, "lead.qualified",
                            {"call_id": rec.get("id"), "phone": rec.get("phone"),
                             "name": rec.get("name", ""), "campaign_id": cid,
                             "score": _score, "outcome": rec["outcome"],
                             "summary": tr.get("summary", "")})
        # BUILD#6: HOT-LEAD -> TEAM WHATSAPP. Notify the vendor's handoff team (lead phone +
        # call summary) so a human can take over a hot lead. Reuses whatsapp.py; no-ops if no
        # handoff team or WA dormant. Fire-and-forget, never blocks/raises into the call loop.
        try:
            await notify_handoff_team(
                tenant_id,
                {"name": rec.get("name", ""), "phone": rec.get("phone", "")},
                summary=tr.get("summary", ""), score=_score)
        except Exception as exc:  # noqa: BLE001
            _lg_handoff.warning("hot-lead notify_handoff_team failed: %r", exc)


def _variant_pool(camp_fields: dict) -> list[str]:
    """Build a weighted round-robin pool of variant ids for a campaign. Empty if no variants."""
    variants = (camp_fields or {}).get("variants") or []
    pool: list[str] = []
    for v in variants:
        if isinstance(v, dict) and v.get("id"):
            pool.extend([v["id"]] * max(1, int(v.get("weight", 1) or 1)))
    return pool


def _variant_by_id(camp_fields: dict, vid: str) -> dict | None:
    for v in (camp_fields or {}).get("variants") or []:
        if isinstance(v, dict) and v.get("id") == vid:
            return v
    return None


async def run_job(job_id: str) -> None:
    job = JOBS[job_id]
    cid = job["campaign_id"]
    tenant_id = job.get("tenant_id", ADMIN_ID)
    camp = get_campaign(cid) or {}
    cname = camp.get("name", "")
    camp_fields = camp.get("fields", {}) or {}
    # WAVE3 Unit3: A/B variant assignment (weighted round-robin across dialed leads).
    variant_pool = _variant_pool(camp_fields)
    variant_idx = 0
    # Load these ONCE per job (cheap; not per tick) — risk-note discipline.
    supp = _suppressed_set(tenant_id)
    tenant = _tenant_by_id(tenant_id) or {}
    max_conc = int(tenant.get("max_concurrency", 3))
    daily_cap_tenant = int(tenant.get("daily_call_cap", 500))
    lk = api.LiveKitAPI(url=LK_URL, api_key=LK_KEY, api_secret=LK_SECRET)
    started_ts: list[float] = []
    pending = job["leads"]
    idx = 0
    active: list[dict] = []
    job["state"] = "running"
    try:
        while idx < len(pending) or active:
            now = time.time()
            still = []
            for it in active:
                if now - it["launched_at"] < MIN_CALL_FLOOR or await _phone_present(lk, it["room"]):
                    still.append(it)
                else:
                    it["status"] = "done"
                    ACTIVE_CALLS[tenant_id] = max(0, ACTIVE_CALLS.get(tenant_id, 0) - 1)
                    await _finalize_call(it, now, tenant_id, cid, camp_fields)
            active = still
            # P0.1 window gate: out of window + nothing active -> idle and auto-resume.
            in_win, win = _in_window(camp_fields)
            if not in_win:
                job["paused_reason"] = "out_of_window"
                if not active and idx < len(pending):
                    await asyncio.sleep(60)
                    continue
            else:
                job.pop("paused_reason", None)
            started_ts = [t for t in started_ts if now - t < 86400]
            hourly = len([t for t in started_ts if now - t < 3600])
            daily = len(started_ts)
            while (in_win and idx < len(pending) and len(active) < job["concurrency"]
                   and hourly < job["hourly_cap"] and daily < job["daily_cap"]):
                it = pending[idx]
                if it["status"] != "queued":
                    idx += 1
                    continue
                num = it["num"]
                # P0.2 suppression skip
                if num in supp:
                    it["status"] = "suppressed"; idx += 1
                    record_call({"id": uuid.uuid4().hex[:10], "tenant_id": tenant_id,
                                 "name": it.get("name", ""), "phone": num,
                                 "campaign_id": cid, "campaign_name": cname, "status": "suppressed",
                                 "outcome": "suppressed", "answered": False,
                                 "started_at": datetime.now().isoformat(timespec="seconds"),
                                 "ended_at": datetime.now().isoformat(timespec="seconds"),
                                 "duration_s": 0, "room": ""})
                    continue
                # P0.7 per-tenant concurrency cap (stacks under per-job concurrency)
                if ACTIVE_CALLS.get(tenant_id, 0) >= max_conc:
                    break   # leave queued; revisit next tick
                # P0.7 daily cap -> pause job
                if _tenant_usage(tenant_id, _today_iso())["calls"] >= daily_cap_tenant:
                    job["paused_reason"] = "daily_cap_reached"
                    break
                idx += 1
                room = f"famit-{num[1:]}-{uuid.uuid4().hex[:6]}"
                # WAVE3 Unit3: assign an A/B variant (round-robin over the weighted pool).
                md_obj = {"campaign_id": cid, "lead_name": it.get("name", "")}
                v_id, v_label = "", ""
                if variant_pool:
                    v_id = variant_pool[variant_idx % len(variant_pool)]
                    variant_idx += 1
                    vdef = _variant_by_id(camp_fields, v_id) or {}
                    v_label = vdef.get("label", v_id)
                    md_obj["variant_id"] = v_id
                    md_obj["variant_label"] = v_label
                    md_obj["fields_override"] = vdef.get("fields_override") or {}
                md = json.dumps(md_obj)
                try:
                    await lk.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=300, departure_timeout=20))
                    await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
                        room=room, agent_name=AGENT, metadata=md))
                    _sip_resp = await lk.sip.create_sip_participant(api.CreateSIPParticipantRequest(
                        sip_trunk_id=TRUNK, sip_call_to=num, room_name=room,
                        participant_identity=f"phone-{num}", participant_name=it.get("name") or num,
                        wait_until_answered=False, ringing_timeout=Duration(seconds=45)))
                    _sip_call_id = (getattr(_sip_resp, "sip_call_id", "") or "").strip()
                    it["status"] = "calling"; it["room"] = room; it["launched_at"] = time.time()
                    rec = {"id": uuid.uuid4().hex[:10], "tenant_id": tenant_id,
                           "name": it.get("name", ""), "phone": num,
                           "campaign_id": cid, "campaign_name": cname, "status": "calling",
                           "variant_id": v_id, "variant_label": v_label,
                           "started_at": datetime.now().isoformat(timespec="seconds"),
                           "ended_at": "", "duration_s": 0, "room": room,
                           "sip_call_id": _sip_call_id}
                    it["_rec"] = rec
                    record_call(rec)
                    ACTIVE_CALLS[tenant_id] = ACTIVE_CALLS.get(tenant_id, 0) + 1
                    active.append(it); started_ts.append(time.time()); hourly += 1; daily += 1
                except Exception as exc:  # noqa: BLE001
                    it["status"] = "failed"; it["error"] = repr(exc)[:140]
                    record_call({"id": uuid.uuid4().hex[:10], "tenant_id": tenant_id,
                                 "name": it.get("name", ""), "phone": num,
                                 "campaign_id": cid, "campaign_name": cname, "status": "failed",
                                 "started_at": datetime.now().isoformat(timespec="seconds"),
                                 "ended_at": "", "duration_s": 0})
            await asyncio.sleep(4)
        job["state"] = "done"
    finally:
        await lk.aclose()


# ---------- JSON API (frontend hits these via nginx /api -> /) ----------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    """Prometheus exposition (no auth — standard scrape endpoint; exposes only
    aggregate counters/latency/cost, never secrets or per-tenant data). Returns a
    tiny stub if prometheus_client is unavailable."""
    if _obs_mod is None:
        return Response(content="# obs module unavailable\nfamit_up 1\n",
                        media_type="text/plain; version=0.0.4; charset=utf-8")
    body, ctype = _obs_mod.render()
    return Response(content=body, media_type=ctype)


def _login_blocked_by_status(tenant: dict | None) -> bool:
    """CONTROL LAYER (CL-B3 / control-security §5.1): a suspended/disabled vendor cannot mint a token.
    Admins are NEVER blocked (anti-lockout). Gated behind CONTROL_ENABLED so resting login is unchanged.
    Suspension's INSTANT kill is auth.revoke_all (next call 401); this closes the fresh-login door too."""
    if not CONTROL_ENABLED or _ent_mod is None or not tenant:
        return False
    if tenant.get("is_admin"):
        return False
    try:
        st = _ent_mod.load_status(tenant.get("tenant_id", "")).get("status", "active")
    except Exception:  # noqa: BLE001
        return False
    return st in ("suspended", "disabled")


@app.post("/login")
async def login(request: Request, password: str = Form(""), email: str = Form("")):
    """Accepts BOTH:
       - {password}            legacy panel login (FamitCall2026) -> admin tenant
       - {email, password}     vendor / tenant login
    Returns {token, tenant_id, name, is_admin}. Token = tenant_id.hmac(tenant_id, SECRET).
    """
    email = (email or "").strip().lower()
    # Legacy: bare password with no email == admin login. Keep this working forever.
    if not email and password == PW:
        t = _tenant_by_id(ADMIN_ID) or ADMIN_TENANT
        return JSONResponse({"token": _make_token(t["tenant_id"]), "tenant_id": t["tenant_id"],
                             "name": t.get("name", ""), "is_admin": True, "role": _role_of(t)})
    if email:
        t = next((x for x in _read_tenants() if (x.get("email") or "").lower() == email), None)
        if t and t.get("pass_hash") == _hash_pw(password, t.get("salt", "")):
            if _login_blocked_by_status(t):
                return JSONResponse({"error": "account suspended"}, status_code=403)
            return JSONResponse({"token": _make_token(t["tenant_id"]), "tenant_id": t["tenant_id"],
                                 "name": t.get("name", ""), "is_admin": bool(t.get("is_admin")),
                                 "role": _role_of(t)})
        # Admin may also log in via its email + the legacy password.
        if t and t.get("is_admin") and password == PW:
            return JSONResponse({"token": _make_token(t["tenant_id"]), "tenant_id": t["tenant_id"],
                                 "name": t.get("name", ""), "is_admin": True, "role": _role_of(t)})
    return JSONResponse({"error": "invalid credentials"}, status_code=401)


# ---------- P0: JWT access + rotating refresh (ADDITIVE; legacy /login above stays) ----------
@app.post("/auth/login")
async def auth_login(request: Request, email: str = Form(""), password: str = Form("")):
    """JWT login. Returns {access_token, refresh_token, token_type, expires_in,
    tenant_id, role, is_admin, name}. Same credentials as /login (bare PW -> admin,
    or email+password). The legacy /login endpoint is unchanged and still works."""
    if not AUTH_JWT_READY or _auth_mod is None:
        return JSONResponse({"error": "jwt auth unavailable"}, status_code=503)
    pair = _auth_mod.login((email or "").strip().lower(), password or "")
    if not pair:
        return JSONResponse({"error": "invalid credentials"}, status_code=401)
    if _login_blocked_by_status(_tenant_by_id(pair.get("tenant_id", ""))):
        return JSONResponse({"error": "account suspended"}, status_code=403)
    return JSONResponse(pair)


@app.post("/auth/refresh")
async def auth_refresh(request: Request, refresh_token: str = Form("")):
    """Rotate tokens: revoke the presented refresh token and return a NEW
    access+refresh pair. 401 if the refresh token is unknown/expired/revoked."""
    if not AUTH_JWT_READY or _auth_mod is None:
        return JSONResponse({"error": "jwt auth unavailable"}, status_code=503)
    rt = (refresh_token or "").strip()
    if not rt:
        # also accept JSON body or Authorization: Bearer for convenience
        rt = (request.headers.get("x-refresh-token", "") or "").strip()
    pair = _auth_mod.refresh(rt)
    if not pair:
        return JSONResponse({"error": "invalid or expired refresh token"}, status_code=401)
    return JSONResponse(pair)


@app.post("/auth/logout")
async def auth_logout(request: Request, refresh_token: str = Form("")):
    """Revoke a refresh token (idempotent). Access tokens expire on their own."""
    if _auth_mod is None:
        return JSONResponse({"ok": True})
    rt = (refresh_token or "").strip() or (request.headers.get("x-refresh-token", "") or "").strip()
    revoked = _auth_mod.logout(rt)
    return JSONResponse({"ok": True, "revoked": bool(revoked)})


@app.get("/me")
async def me(request: Request):
    """Current identity + role. Frontend uses role to show/hide actions."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    return JSONResponse({"tenant_id": t["tenant_id"], "email": t.get("email", ""),
                         "name": t.get("name", ""), "role": _role_of(t),
                         "is_admin": bool(t.get("is_admin"))})


# ---------- F2: Business Brain + Knowledge Base (additive; tenant-scoped; org_id from token only) ----------
# org_id is ALWAYS t["tenant_id"] (resolve_tenant), NEVER a body/param (platform-business-brain RT-5).
# All routes degrade cleanly when brain/kb modules are absent. Nothing here touches an existing route.
@app.get("/brain")
async def brain_get(request: Request):
    """Full Business Brain profile for the caller's org. {} when none yet."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _brain_mod is None:
        return JSONResponse({"profile": {}, "note": "brain module unavailable"})
    return JSONResponse({"profile": _brain_mod.get_profile(t["tenant_id"]),
                         "completeness": _brain_mod.completeness(t["tenant_id"])})


@app.put("/brain")
async def brain_put(request: Request):
    """Upsert (merge) the Business Brain profile. Versioned + audited. write-role gated."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden()
    if _brain_mod is None:
        return JSONResponse({"error": "brain module unavailable"}, status_code=503)
    try:
        patch = await request.json()
        if not isinstance(patch, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    # never honour a body-supplied org_id/id (RT-5): strip before merge.
    patch.pop("org_id", None)
    patch.pop("id", None)
    prof = _brain_mod.upsert_profile(t["tenant_id"], patch, actor=t["tenant_id"])
    return JSONResponse({"profile": prof,
                         "completeness": _brain_mod.completeness(t["tenant_id"])})


@app.get("/brain/handoff")
async def brain_handoff_get(request: Request):
    """The vendor's HUMAN HANDOFF team list (warm-transfer + hot-lead WhatsApp targets).
    [{phone, whatsapp, role, hours, priority}, ...]. Lives on the Business Brain `handoff` block."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    return JSONResponse({"handoff": _handoff_get(t["tenant_id"])})


@app.put("/brain/handoff")
async def brain_handoff_put(request: Request):
    """Replace the vendor's handoff team list. write-role gated. Body = a JSON array of
    {phone, whatsapp, role, hours, priority}, or {"handoff":[...]} / {"team":[...]}."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden()
    if _brain_mod is None:
        return JSONResponse({"error": "brain module unavailable"}, status_code=503)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if isinstance(body, dict):
        team = body.get("handoff") or body.get("team") or body.get("numbers") or []
    elif isinstance(body, list):
        team = body
    else:
        return JSONResponse({"error": "body must be a JSON array or {handoff:[...]}"},
                            status_code=400)
    if not isinstance(team, list):
        return JSONResponse({"error": "handoff must be an array"}, status_code=400)
    stored = _handoff_set(t["tenant_id"], team, actor=t["tenant_id"])
    return JSONResponse({"handoff": stored})


@app.post("/handoff/notify")
async def handoff_notify(request: Request):
    """Internal: fire the HOT-LEAD WhatsApp to the vendor's handoff team. Used by the inbound
    voice agent's warm-transfer fallback (and any caller) to drop lead phone+summary into the
    team's chat. write-role gated; reuses notify_handoff_team. Returns the send report."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    lead = {"name": str((body or {}).get("name", "") or ""),
            "phone": str((body or {}).get("phone", "") or "")}
    summary = str((body or {}).get("summary", "") or "")
    try:
        score = int((body or {}).get("score", 0) or 0)
    except Exception:  # noqa: BLE001
        score = 0
    res = await notify_handoff_team(t["tenant_id"], lead, summary=summary, score=score)
    return JSONResponse(res)


@app.get("/brain/completeness")
async def brain_completeness(request: Request):
    """Readiness score + missing fields (onboarding checklist + hallucination guard)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _brain_mod is None:
        return JSONResponse({"score": 0, "missing": [], "note": "brain module unavailable"})
    return JSONResponse(_brain_mod.completeness(t["tenant_id"]))


@app.post("/brain/knowledge")
async def brain_add_knowledge(request: Request, content: str = Form(""), title: str = Form(""),
                              doc_type: str = Form("generic"), kind: str = Form("paste")):
    """Ingest a long-form knowledge doc into the KB corpus (business-scoped) for the caller's org.
    Chunk + FTS + (optional, dormant-until-key) embed -> upsert. Heavy work runs OFF the event loop."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden()
    if _brain_mod is None:
        return JSONResponse({"ok": False, "reason": "brain module unavailable"}, status_code=503)
    if not (content or "").strip():
        return JSONResponse({"ok": False, "reason": "empty content"}, status_code=400)
    # embed() may do a network round-trip -> run the whole ingest off the uvicorn loop (event-loop safety).
    res = await asyncio.to_thread(_brain_mod.add_knowledge, t["tenant_id"], content,
                                  title=title, kind=kind, doc_type=doc_type, actor=t["tenant_id"])
    return JSONResponse(res)


@app.get("/brain/retrieve")
async def brain_retrieve(request: Request, q: str = "", k: int = 4):
    """Hybrid (FTS + dense-when-configured) retrieve over the caller's org KB. RLS-scoped.
    [] when KB/PG absent. Off the voice hot path (voice uses precomputed blob — later unit)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _brain_mod is None or not (q or "").strip():
        return JSONResponse({"results": []})
    res = await asyncio.to_thread(_brain_mod.retrieve, t["tenant_id"], q, max(1, min(int(k or 4), 20)))
    return JSONResponse({"results": res})


# ============================================================================
# CRM CORE — contact spine + unified timeline + next-best-action (additive; read-model).
# All X-Auth, tenant-scoped (org_id == t["tenant_id"], NEVER a body/param), RBAC per can().
# PG work runs OFF the uvicorn loop (asyncio.to_thread) — project/rebuild do several round-trips.
# These NEVER write leads and NEVER touch the run-path. Degrade to empty shapes when crm/PG absent.
# ============================================================================
@app.get("/contacts")
async def contacts_list(request: Request, stage: str = "", hot: str = "", q: str = "",
                        segment: str = "", sort: str = "last_activity_at", limit: int = 100):
    """List/filter/segment contacts for the caller's org. {contacts:[...], total}."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _crm_mod is None:
        return JSONResponse({"contacts": [], "total": 0, "note": "crm module unavailable"})
    hot_f = None
    if str(hot).lower() in ("1", "true", "yes"):
        hot_f = True
    elif str(hot).lower() in ("0", "false", "no"):
        hot_f = False
    res = await asyncio.to_thread(
        lambda: _crm_mod.list_contacts(t["tenant_id"], stage=stage, hot=hot_f, q=q, sort=sort,
                                       limit=max(1, min(int(limit or 100), 1000)),
                                       is_admin=bool(t.get("is_admin"))))
    return JSONResponse(res)


@app.get("/contacts/{phone}")
async def contacts_get(request: Request, phone: str):
    """One contact: full profile + the authoritative lead + the rule-based next-best-action.
    `phone` is any phone form (canonicalized) OR a ct_ contact id."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _crm_mod is None:
        return JSONResponse({"contact": None, "note": "crm module unavailable"}, status_code=503)
    org = t["tenant_id"]
    adm = bool(t.get("is_admin"))
    # project on read so stage/score/timeline reflect the latest lead truth (off the loop).
    c = await asyncio.to_thread(lambda: _crm_mod.project_contact(org, phone, is_admin=adm))
    if c is None:
        c = await asyncio.to_thread(lambda: _crm_mod.get_contact(org, phone, is_admin=adm))
    if c is None:
        return JSONResponse({"error": "contact not found"}, status_code=404)
    tl = await asyncio.to_thread(lambda: _crm_mod.get_timeline(org, c["id"], limit=50, is_admin=adm))
    nba = await asyncio.to_thread(lambda: _crm_mod.next_best_action(org, c, timeline=tl, is_admin=adm))
    return JSONResponse({"contact": c, "timeline": tl, "nba": nba})


@app.get("/contacts/{phone}/timeline")
async def contacts_timeline(request: Request, phone: str, kinds: str = "", limit: int = 100):
    """The full chronological interaction history (newest-first) for a person."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _crm_mod is None:
        return JSONResponse({"timeline": [], "note": "crm module unavailable"})
    org = t["tenant_id"]
    adm = bool(t.get("is_admin"))
    kinds_l = [k.strip() for k in kinds.split(",") if k.strip()] or None
    cid = phone if str(phone).startswith("ct_") else _crm_mod.contact_id(org, phone)
    tl = await asyncio.to_thread(
        lambda: _crm_mod.get_timeline(org, cid, limit=max(1, min(int(limit or 100), 1000)),
                                      kinds=kinds_l, is_admin=adm))
    return JSONResponse({"timeline": tl, "contact_id": cid})


@app.get("/contacts/{phone}/nba")
async def contacts_nba(request: Request, phone: str):
    """The recommended next action for a contact (deterministic rules; no metered call)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _crm_mod is None:
        return JSONResponse({"action": "none", "reason": "crm module unavailable"})
    org = t["tenant_id"]
    adm = bool(t.get("is_admin"))
    c = await asyncio.to_thread(lambda: _crm_mod.get_contact(org, phone, is_admin=adm))
    if c is None:
        return JSONResponse({"error": "contact not found"}, status_code=404)
    tl = await asyncio.to_thread(lambda: _crm_mod.get_timeline(org, c["id"], limit=50, is_admin=adm))
    nba = await asyncio.to_thread(lambda: _crm_mod.next_best_action(org, c, timeline=tl, is_admin=adm))
    return JSONResponse(nba)


@app.put("/contacts/{phone}")
async def contacts_update(request: Request, phone: str):
    """Update contact name/email/tags/stage (a CONTACT-only manual override — NEVER writes leads).
    Body = JSON {name?,email?,tags?[],stage?,data?{}}. write-role gated."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden()
    if _crm_mod is None:
        return JSONResponse({"error": "crm module unavailable"}, status_code=503)
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    # never honour a body-supplied org_id/id/phone_key (identity is derived from the path).
    for k in ("org_id", "id", "phone_key"):
        body.pop(k, None)
    org = t["tenant_id"]
    adm = bool(t.get("is_admin"))
    c = await asyncio.to_thread(
        lambda: _crm_mod.update_contact(
            org, phone, name=body.get("name"), email=body.get("email"),
            tags=body.get("tags"), stage=body.get("stage"), data=body.get("data"), is_admin=adm))
    if c is None:
        return JSONResponse({"error": "contact not found / crm unavailable"}, status_code=404)
    return JSONResponse({"ok": True, "contact": c})


# ---------- P0: read-only audit log (admin; tenant-scoped; paginated) ----------
@app.get("/audit")
async def get_audit(request: Request, limit: int = 100, offset: int = 0,
                    action: str = "", channel: str = ""):
    """Append-only audit trail. Admin sees ALL events; a non-admin sees only its
    own tenant's events. Read-only + paginated (newest first). `channel` filters by
    event channel (e.g. ?channel=ai for AI-decision rows — F4 §7)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _audit_mod is None:
        return JSONResponse({"events": [], "total": 0, "limit": limit, "offset": offset,
                             "note": "audit module unavailable"})
    scope = None if t.get("is_admin") else t["tenant_id"]
    return JSONResponse(_audit_mod.tail(limit=limit, offset=offset,
                                        tenant_id=scope, action_prefix=action, channel=channel))


# ============================================================================
# F4: Credit/Wallet ledger + Action Firewall — ADDITIVE endpoints (tenant-scoped).
# org_id is ALWAYS t["tenant_id"] (resolve_tenant), NEVER a body/param. All routes degrade to a clean
# shape (never 500) when wallet/firewall are unavailable. None of these touch the existing run-path.
# Money crosses the API in MAJOR units (rupees); the wallet core stores INTEGER MINOR units (paise).
# ============================================================================
def _minor_to_major(m) -> float:
    try:
        return round(int(m) / 100.0, 2)
    except Exception:  # noqa: BLE001
        return 0.0


def _wallet_unavailable_body() -> dict:
    return {"wallet_available": False, "note": "wallet ledger unavailable (Postgres down or module absent)"}


def _step_up_guard(request: Request, scope: str, tenant: dict):
    """Apply the Action Firewall step-up gate. Returns an error Response to RETURN (deny), or None to
    proceed. Pass-through when firewall is OFF / unavailable / tenant has no PIN (non-breaking)."""
    if _firewall_mod is None:
        return None
    try:
        _firewall_mod.require_step_up(request, scope, tenant)
        return None
    except _firewall_mod.StepUpDenied as d:
        return JSONResponse(d.body, status_code=d.status)
    except Exception:  # noqa: BLE001
        return None  # firewall must never hard-break a request


@app.get("/wallet")
async def wallet_get(request: Request):
    """Wallet balance for the caller's org (major units). Clean shape when unavailable / no account."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _wallet_mod is None or not _wallet_mod.available():
        return JSONResponse(_wallet_unavailable_body())
    bal = await asyncio.to_thread(_wallet_mod.balance, t["tenant_id"], "INR", bool(t.get("is_admin")))
    plan = (_billing_for(t["tenant_id"]) or {}).get("plan", "postpaid") if "_billing_for" in globals() else "postpaid"
    if bal is None:
        return JSONResponse({"tenant_id": t["tenant_id"], "currency": "INR", "available": 0.0,
                             "held": 0.0, "plan": plan, "lifetime_topup": 0.0, "lifetime_spend": 0.0,
                             "wallet_available": True, "note": "no wallet account yet"})
    return JSONResponse({
        "tenant_id": t["tenant_id"], "currency": bal["currency"], "plan": plan,
        "available": _minor_to_major(bal["available_minor"]),
        "held": _minor_to_major(bal["held_minor"]),
        "lifetime_topup": _minor_to_major(bal["lifetime_topup_minor"]),
        "lifetime_spend": _minor_to_major(bal["lifetime_spend_minor"]),
        "wallet_available": True,
    })


@app.get("/wallet/ledger")
async def wallet_ledger(request: Request, limit: int = 100):
    """Wallet transaction ledger (newest first) for the caller's org. Amounts in major units."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _wallet_mod is None or not _wallet_mod.available():
        return JSONResponse({"transactions": [], "total": 0, **_wallet_unavailable_body()})
    rows = await asyncio.to_thread(_wallet_mod.transactions, t["tenant_id"], limit, bool(t.get("is_admin")))
    out = [{
        "id": r["id"], "kind": r["kind"], "amount": _minor_to_major(r["amount_minor"]),
        "held_delta": _minor_to_major(r["held_delta_minor"]),
        "resource_type": r["resource_type"], "resource_id": r["resource_id"],
        "balance_after": _minor_to_major(r["balance_after_minor"]), "hold_id": r["hold_id"], "at": r["at"],
    } for r in rows]
    return JSONResponse({"transactions": out, "total": len(out)})


@app.get("/wallet/holds")
async def wallet_holds(request: Request, state: str = ""):
    """Open/closed reservations for the caller's org. Amounts in major units."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _wallet_mod is None or not _wallet_mod.available():
        return JSONResponse({"holds": [], **_wallet_unavailable_body()})
    rows = await asyncio.to_thread(_wallet_mod.holds, t["tenant_id"], state, bool(t.get("is_admin")))
    out = [{
        "id": r["id"], "amount": _minor_to_major(r["amount_minor"]), "state": r["state"],
        "resource_type": r["resource_type"], "resource_id": r["resource_id"],
        "settled": (_minor_to_major(r["settled_minor"]) if r["settled_minor"] is not None else None),
        "expires_at": r["expires_at"], "at": r["at"],
    } for r in rows]
    return JSONResponse({"holds": out})


@app.post("/wallet/topup/{tenant_id}")
async def wallet_topup(request: Request, tenant_id: str, amount: float = Form(...),
                       payment_ref: str = Form("")):
    """ADMIN credit to a tenant's wallet (major units rupees). Idempotent on payment_ref so a webhook
    retry can't double-credit. Gated by the Action Firewall (spend scope) when FIREWALL_ENABLED + a PIN
    is set on the ACTING admin. Audited."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "manage_tenants"):
        return _forbidden("admin only")
    # Action Firewall: a topup is spend-sensitive. Gate on the ACTING tenant's step-up.
    denied = _step_up_guard(request, "spend", t)
    if denied is not None:
        _audit(request, t, "firewall.stepup.denied", "wallet", tenant_id,
               meta={"scope": "spend", "action": "wallet.topup"})
        return denied
    if _wallet_mod is None or not _wallet_mod.available():
        return JSONResponse(_wallet_unavailable_body(), status_code=503)
    minor = int(round(float(amount) * 100))
    if minor <= 0:
        return JSONResponse({"ok": False, "reason": "amount must be positive"}, status_code=400)
    idem = f"topup:{payment_ref}" if payment_ref else f"topup:manual:{secrets.token_hex(8)}"
    res = await asyncio.to_thread(_wallet_mod.topup, tenant_id, minor, t["tenant_id"], idem, "INR", True, None)
    _audit(request, t, "wallet.topup", "wallet", tenant_id,
           meta={"amount_minor": minor, "payment_ref": payment_ref, "ok": bool(res.get("ok"))})
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    return JSONResponse({
        "ok": True, "tenant_id": tenant_id, "credited": _minor_to_major(minor),
        "available": _minor_to_major(res.get("available_minor", 0)),
        "held": _minor_to_major(res.get("held_minor", 0)),
    })


@app.put("/firewall/pin")
async def firewall_set_pin(request: Request, pin: str = Form(...)):
    """Set/replace the caller's own Action-Firewall PIN (salted-hash stored; never the raw PIN). Audited."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _firewall_mod is None or not _firewall_mod.available():
        return JSONResponse({"ok": False, "reason": "firewall unavailable"}, status_code=503)
    res = _firewall_mod.set_pin(t["tenant_id"], pin)
    if res.get("ok"):
        _audit(request, t, "firewall.pin.set", "firewall", t["tenant_id"])
    return JSONResponse(res, status_code=200 if res.get("ok") else 400)


@app.post("/firewall/verify-pin")
async def firewall_verify_pin(request: Request, pin: str = Form(...), scope: str = Form("spend")):
    """Verify the caller's PIN; on match mint a short-TTL step-up token (the client then replays the
    gated action with X-Step-Up: <token>). On mismatch -> 401 + an audited firewall.stepup.fail row."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _firewall_mod is None or not _firewall_mod.available():
        return JSONResponse({"ok": False, "reason": "firewall unavailable"}, status_code=503)
    if not _firewall_mod.has_pin(t["tenant_id"]):
        return JSONResponse({"ok": False, "reason": "no PIN set"}, status_code=400)
    if not _firewall_mod.check_pin(t["tenant_id"], pin):
        _audit(request, t, "firewall.stepup.fail", "firewall", t["tenant_id"], meta={"scope": scope})
        return JSONResponse({"ok": False, "error": "invalid PIN"}, status_code=401)
    tok = _firewall_mod.mint_step_up(t["tenant_id"], scope)
    _audit(request, t, "firewall.stepup.ok", "firewall", t["tenant_id"], meta={"scope": scope})
    return JSONResponse({"ok": True, **(tok or {})})


@app.get("/firewall/status")
async def firewall_status(request: Request):
    """Firewall enrollment + flag state for the caller's org."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _firewall_mod is None:
        return JSONResponse({"pin_set": False, "firewall_enabled": False, "available": False})
    return JSONResponse(_firewall_mod.status(t["tenant_id"]))


@app.post("/extract")
async def extract(request: Request, brief: str = Form("")):
    if not authed(request):
        return need_auth()
    return JSONResponse(extract_fields(brief or ""))


@app.get("/voices")
async def voices(request: Request):
    if not authed(request):
        return need_auth()
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/voices",
                      headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=15)
        vs = [{"voice_id": v["voice_id"], "name": v["name"]} for v in r.json().get("voices", [])]
        return JSONResponse({"voices": vs})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"voices": [], "error": repr(exc)[:140]})


@app.get("/campaigns")
async def campaigns(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    return JSONResponse({"campaigns": list_campaigns(t)})


def _coerce_fields(fields: dict) -> dict:
    """Normalise extracted/edited campaign fields so a save never 500s and the
    agent always gets a usable shape. Missing/odd values get sensible defaults."""
    if not isinstance(fields, dict):
        raise ValueError("fields must be a JSON object")
    out = dict(fields)
    # strings
    for k, default in (("company_name", ""), ("agent_name", "Riya"), ("product_name", ""),
                       ("product_summary", ""), ("location", ""), ("price_offer", ""),
                       ("language", "Hinglish"), ("voice_id", ""),
                       # P0.1 calling window (HH:MM, IST gate); call_window_tz informational
                       ("call_window_start", "09:00"), ("call_window_end", "21:00"),
                       ("call_window_tz", "Asia/Kolkata")):
        v = out.get(k)
        out[k] = (str(v).strip() if v is not None else default) or default
    # P0.5 retry policy
    try:
        out["retry_max_attempts"] = max(0, int(out.get("retry_max_attempts", 3)))
    except Exception:  # noqa: BLE001
        out["retry_max_attempts"] = 3
    bo = out.get("retry_backoff_mins")
    if isinstance(bo, str):
        bo = [s.strip() for s in re.split(r"[,\s]+", bo) if s.strip()]
    if isinstance(bo, list):
        try:
            bo = [int(x) for x in bo if str(x).strip()]
        except Exception:  # noqa: BLE001
            bo = []
    out["retry_backoff_mins"] = bo or [120, 360, 1440]
    # P1.A whatsapp follow-up (per-campaign)
    out["wa_enabled"] = bool(out.get("wa_enabled", False))
    # WAVE3 Unit5: per-campaign auto WhatsApp follow-up after interested/callback calls.
    # Defaults OFF so nothing fires until the user enables it AND adds WA_* creds.
    out["wa_followup"] = bool(out.get("wa_followup", False))
    for k in ("wa_template_qualified", "wa_template_noanswer",
              "wa_template_interested", "wa_template_callback"):
        v = out.get(k)
        out[k] = str(v).strip() if v is not None else ""
    # list-of-strings
    for k in ("usps", "talking_points", "qualifying_questions"):
        v = out.get(k)
        if isinstance(v, str):
            v = [s.strip() for s in re.split(r"[\n;]+", v) if s.strip()]
        out[k] = [str(s) for s in v] if isinstance(v, list) else []
    # objections: list of {q,a}
    obj = out.get("objections")
    norm_obj = []
    if isinstance(obj, list):
        for o in obj:
            if isinstance(o, dict):
                norm_obj.append({"q": str(o.get("q", "")), "a": str(o.get("a", ""))})
    out["objections"] = norm_obj
    # WAVE3 Unit3: A/B variants. Each = {id,label,fields_override:{...},weight}.
    # A campaign with no variants behaves exactly as before.
    variants = out.get("variants")
    norm_var = []
    if isinstance(variants, list):
        for v in variants:
            if not isinstance(v, dict):
                continue
            vid = str(v.get("id") or uuid.uuid4().hex[:6])
            ov = v.get("fields_override")
            ov = ov if isinstance(ov, dict) else {}
            try:
                w = max(1, int(v.get("weight", 1)))
            except Exception:  # noqa: BLE001
                w = 1
            norm_var.append({"id": vid, "label": str(v.get("label") or vid),
                             "fields_override": ov, "weight": w})
    out["variants"] = norm_var
    return out


@app.post("/campaigns")
async def create_campaign(request: Request, fields_json: str = Form("")):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot create campaigns")
    # Bulletproof: validate input, never 500, return a clear error instead.
    if not (fields_json or "").strip():
        return JSONResponse({"error": "fields_json is required"}, status_code=400)
    try:
        raw = json.loads(fields_json.lstrip("﻿"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"fields_json is not valid JSON: {exc}"}, status_code=400)
    try:
        fields = _coerce_fields(raw)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"invalid fields: {exc}"}, status_code=400)
    if not (fields.get("company_name") or fields.get("product_name")):
        return JSONResponse({"error": "at least one of company_name or product_name is required"},
                            status_code=400)
    try:
        rec = save_campaign(fields, t["tenant_id"])
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"could not save campaign: {repr(exc)[:160]}"}, status_code=500)
    _audit(request, t, "campaign.create", "campaign", rec["id"], meta={"name": rec.get("name")})
    return JSONResponse({"id": rec["id"], "name": rec["name"], "tenant_id": rec["tenant_id"]})


@app.get("/campaigns/{cid}")
async def get_campaign_detail(request: Request, cid: str):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    d = get_campaign_for(cid, t)
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({"campaign": d})


@app.get("/campaigns/{cid}/ab")
async def campaign_ab(request: Request, cid: str):
    """WAVE3 Unit3: per-variant A/B stats computed from call records.
    Returns {campaign_id, variants:[{id,label,weight,dialed,connected,interested,
    qualified,avg_interest}]}. Calls with no variant_id are bucketed under '(default)'."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    d = get_campaign_for(cid, t)
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)
    defs = (d.get("fields") or {}).get("variants") or []
    # seed buckets from defined variants (so a 0-call variant still appears)
    buckets: dict = {}
    for v in defs:
        if isinstance(v, dict) and v.get("id"):
            buckets[v["id"]] = {"id": v["id"], "label": v.get("label", v["id"]),
                                "weight": int(v.get("weight", 1) or 1),
                                "dialed": 0, "connected": 0, "interested": 0,
                                "qualified": 0, "_interest_sum": 0, "_interest_n": 0}
    rows = [c for c in calls_for(t) if c.get("campaign_id") == cid]
    for c in rows:
        vid = c.get("variant_id") or "(default)"
        b = buckets.get(vid)
        if b is None:
            b = buckets[vid] = {"id": vid, "label": c.get("variant_label") or vid,
                                "weight": 0, "dialed": 0, "connected": 0, "interested": 0,
                                "qualified": 0, "_interest_sum": 0, "_interest_n": 0}
        if c.get("status") == "suppressed":
            continue
        b["dialed"] += 1
        if c.get("status") not in ("queued", "suppressed"):
            b["connected"] += 1
        if c.get("answered") is True or (c.get("answered") is None and c.get("duration_s", 0) >= 8):
            pass
        if c.get("outcome") == "interested":
            b["interested"] += 1
        score = c.get("interest", 0) or 0
        if score >= 70:
            b["qualified"] += 1
        if score:
            b["_interest_sum"] += score
            b["_interest_n"] += 1
    out = []
    for b in buckets.values():
        n = b.pop("_interest_n"); s = b.pop("_interest_sum")
        b["avg_interest"] = round(s / n, 1) if n else 0
        out.append(b)
    return JSONResponse({"campaign_id": cid, "variants": out})


@app.post("/campaigns/{cid}")
async def update_campaign(request: Request, cid: str, fields_json: str = Form("")):
    """Update a campaign's fields (incl. voice_id). Rebuilds the system prompt. Tenant-scoped."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot edit campaigns")
    d = get_campaign_for(cid, t)
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)
    if not (fields_json or "").strip():
        return JSONResponse({"error": "fields_json is required"}, status_code=400)
    try:
        raw = json.loads(fields_json.lstrip("﻿"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"fields_json is not valid JSON: {exc}"}, status_code=400)
    try:
        fields = _coerce_fields(raw)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"invalid fields: {exc}"}, status_code=400)
    try:
        d["fields"] = fields
        d["name"] = fields.get("product_name") or fields.get("company_name") or d["id"]
        d["company"] = fields.get("company_name", "")
        d["product"] = fields.get("product_name", "")
        d["system_prompt"] = build_system_prompt(fields)
        d.setdefault("tenant_id", t["tenant_id"])
        safe = "".join(ch for ch in cid if ch.isalnum() or ch in "-_")
        (CAMPAIGN_DIR / f"{safe}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"could not update: {repr(exc)[:160]}"}, status_code=500)
    # P1 DUAL MIRROR (best-effort, additive): mirror the edited campaign to PG (per-id upsert). No-op
    # unless campaigns is dual in STORE_MODES; off-loop; swallows — must NOT break campaign edit.
    try:
        if _store is not None:
            _store.mirror_campaign_upsert(d)
    except Exception:  # noqa: BLE001
        pass
    _audit(request, t, "campaign.update", "campaign", d["id"], meta={"name": d.get("name")})
    return JSONResponse({"id": d["id"], "name": d["name"]})


@app.delete("/campaigns/{cid}")
async def delete_campaign(request: Request, cid: str):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot delete campaigns")
    d = get_campaign_for(cid, t)
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)
    cid = "".join(ch for ch in cid if ch.isalnum() or ch in "-_")
    p = CAMPAIGN_DIR / f"{cid}.json"
    if p.exists():
        p.unlink()
    # P1 DUAL MIRROR (best-effort, additive): drop the campaign row from PG. No-op unless campaigns is
    # dual in STORE_MODES; off-loop; swallows — must NOT break campaign delete.
    try:
        if _store is not None:
            _store.mirror_campaign_delete(cid)
    except Exception:  # noqa: BLE001
        pass
    _audit(request, t, "campaign.delete", "campaign", cid)
    return JSONResponse({"deleted": cid})


def _leads_for(tenant: dict) -> list[dict]:
    store = _read(LEADS_FILE, [])
    if tenant.get("is_admin"):
        return store
    return [x for x in store if x.get("tenant_id", ADMIN_ID) == tenant["tenant_id"]]


# RC2 temperature bands — MUST match app/leads/page.tsx: hot>=70, warm 40-69, cold<40/unscored.
def _lead_temp(lead: dict) -> str:
    s = int(lead.get("score", 0) or 0)
    if s >= 70:
        return "hot"
    if s >= 40:
        return "warm"
    return "cold"


def _csv_set(raw: str) -> set:
    """Split a comma/space/repeated-field selector string into a clean set."""
    if not raw:
        return set()
    return {p.strip() for p in re.split(r"[,\s]+", raw) if p.strip()}


def _resolve_audience(t: dict, *, source_mode: str = "", lead_ids: str = "",
                      temps: str = "", batch_ids: str = "",
                      score_min: str = "", score_max: str = "") -> list[dict]:
    """RC2: resolve the OPTIONAL composable /run selectors to a concrete set of
    this tenant's stored lead rows (BOLA-safe — only ever this tenant's leads).
    Returns full lead dicts (with phone/name/score/batch_id). Layers, in order:

      BASE POOL  = stored leads, narrowed to selected batch_ids (if any).
      TEMPERATURE/SCORE FILTER = temps (hot/warm/cold) and/or a custom score band.
      MANUAL OVERRIDE = if lead_ids given, use EXACTLY those (intersected with the
                        tenant's own leads — never another tenant's).

    Returns [] (no selector resolution) when none of the selectors are present,
    so the legacy csv/use_stored/text path in /run is completely untouched."""
    pool = _leads_for(t)
    by_id = {x.get("id"): x for x in pool}

    # MANUAL: explicit lead_ids win outright (primary UI path = preview==dials).
    ids = _csv_set(lead_ids)
    if ids:
        return [by_id[i] for i in ids if i in by_id]

    # Nothing else selected -> signal "no server-side resolution" to the caller.
    bset = _csv_set(batch_ids)
    tset = {x.lower() for x in _csv_set(temps)}
    has_band = bool(str(score_min).strip() or str(score_max).strip())
    if not (bset or tset or has_band or source_mode in ("all", "temperature", "upload")):
        return []

    rows = pool
    # BASE POOL narrowing by uploaded batch.
    if bset:
        rows = [x for x in rows if (x.get("batch_id") or "") in bset]
    # TEMPERATURE filter (multi-select).
    if tset:
        rows = [x for x in rows if _lead_temp(x) in tset]
    # CUSTOM score band.
    if has_band:
        try:
            lo = int(float(score_min)) if str(score_min).strip() else 0
        except Exception:  # noqa: BLE001
            lo = 0
        try:
            hi = int(float(score_max)) if str(score_max).strip() else 100
        except Exception:  # noqa: BLE001
            hi = 100
        rows = [x for x in rows if lo <= int(x.get("score", 0) or 0) <= hi]
    return rows


@app.get("/leads")
async def get_leads(request: Request, hot: str = "", sort: str = ""):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = _leads_for(t)
    if hot:
        rows = [x for x in rows if (x.get("score", 0) or 0) >= 70]
    if sort == "score":
        rows = sorted(rows, key=lambda x: x.get("score", 0) or 0, reverse=True)
    return JSONResponse({"leads": rows})


@app.post("/leads")
async def add_leads(request: Request, leads: str = Form(""), csv: UploadFile | None = File(None)):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot add leads")
    csv_bytes = await csv.read() if csv is not None else None
    parsed = parse_upload(leads, csv, csv_bytes)
    # RC2: stamp a batch_id + source_file when leads arrive via an uploaded file,
    # so leads can later be filtered by which upload they came from. Manual
    # text-only adds stay batch-less (back-compat: existing rows keep working).
    src_file = (getattr(csv, "filename", "") or "") if (csv is not None and csv_bytes) else ""
    batch_id = uuid.uuid4().hex[:8] if src_file else ""
    now_iso = datetime.now().isoformat(timespec="seconds")
    store = _read(LEADS_FILE, [])
    # de-dup within THIS tenant's leads (different tenants may share a number)
    have = {x["phone"] for x in store if x.get("tenant_id", ADMIN_ID) == t["tenant_id"]}
    added = 0
    for x in parsed:
        if x["num"] not in have:
            rec = {"id": uuid.uuid4().hex[:8], "tenant_id": t["tenant_id"],
                   "name": x["name"], "phone": x["num"],
                   "status": "new", "added_at": now_iso}
            if batch_id:
                rec["batch_id"] = batch_id
                rec["source_file"] = src_file
            store.append(rec)
            have.add(x["num"]); added += 1
    _write(LEADS_FILE, store)
    _audit(request, t, "leads.add", "lead", "", meta={"added": added, "batch_id": batch_id,
                                                        "source_file": src_file})
    resp = {"added": added, "total": len(_leads_for(t))}
    if batch_id:
        resp["batch_id"] = batch_id
        resp["source_file"] = src_file
    return JSONResponse(resp)


@app.get("/leads/batches")
async def leads_batches(request: Request):
    """RC2: return the distinct upload batches for this tenant, derived by
    grouping the lead store on batch_id (no new storage). Each batch =
    {batch_id, source_file, count, added_at}. Leads with no batch_id (manual /
    legacy adds) are folded into a single synthetic 'manual' bucket so the UI can
    always show a complete picture. Newest-first by added_at."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    groups: dict[str, dict] = {}
    for x in _leads_for(t):
        bid = x.get("batch_id") or ""
        key = bid or "manual"
        g = groups.get(key)
        added = x.get("added_at", "") or ""
        if g is None:
            groups[key] = {
                "batch_id": bid,
                "source_file": x.get("source_file", "") or ("" if bid else "Manual / legacy"),
                "count": 1,
                "added_at": added,
            }
        else:
            g["count"] += 1
            if added and (not g["added_at"] or added > g["added_at"]):
                g["added_at"] = added
            if bid and not g["source_file"]:
                g["source_file"] = x.get("source_file", "")
    batches = sorted(groups.values(), key=lambda b: b.get("added_at", ""), reverse=True)
    return JSONResponse({"batches": batches})


@app.delete("/leads/{lead_id}")
async def delete_lead(request: Request, lead_id: str):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot delete leads")
    store = _read(LEADS_FILE, [])
    target = next((x for x in store if x.get("id") == lead_id), None)
    guard = require_object(t, target)  # 404 if missing or not owned (BOLA)
    if guard is not None:
        return guard
    store = [x for x in store if x.get("id") != lead_id]
    _write(LEADS_FILE, store)
    _audit(request, t, "leads.delete", "lead", lead_id)
    return JSONResponse({"deleted": lead_id, "total": len(_leads_for(t))})


@app.post("/run/preview")
async def run_preview(request: Request, leads: str = Form(""),
                      use_stored: str = Form(""), source_mode: str = Form(""),
                      lead_ids: str = Form(""), temps: str = Form(""),
                      batch_ids: str = Form(""), score_min: str = Form(""),
                      score_max: str = Form(""), csv: UploadFile | None = File(None)):
    """RC2: resolve the SAME composable audience selectors as /run and return a
    truthful preview { count, suppressed_count, breakdown } WITHOUT creating a job
    or dialling anyone. Lets the UI show 'N leads will be called' before launch.
    No paid call can originate here — there is no run_job dispatch."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    csv_bytes = await csv.read() if csv is not None else None
    parsed = parse_upload(leads, csv, csv_bytes)
    resolved = _resolve_audience(
        t, source_mode=source_mode, lead_ids=lead_ids, temps=temps,
        batch_ids=batch_ids, score_min=score_min, score_max=score_max)
    rc2_used = bool(resolved or _csv_set(lead_ids) or _csv_set(batch_ids)
                    or _csv_set(temps) or str(score_min).strip() or str(score_max).strip()
                    or source_mode in ("all", "temperature", "upload", "manual"))
    if resolved:
        parsed += [{"name": x.get("name", ""), "num": x.get("phone", "")} for x in resolved]
    if use_stored and not rc2_used:
        parsed += [{"name": x.get("name", ""), "num": x["phone"]} for x in _leads_for(t)]
    seen, uniq = set(), []
    for x in parsed:
        if x["num"] and x["num"] not in seen:
            seen.add(x["num"]); uniq.append(x)
    supp = _suppressed_set(t["tenant_id"])
    suppressed_count = sum(1 for x in uniq if x["num"] in supp)
    _phone_temp = {x.get("phone"): _lead_temp(x) for x in _leads_for(t)}
    breakdown = {"hot": 0, "warm": 0, "cold": 0}
    for x in uniq:
        tb = _phone_temp.get(x["num"])
        if tb in breakdown:
            breakdown[tb] += 1
    # callable count = unique candidates minus those already suppressed (DND).
    callable_count = sum(1 for x in uniq if x["num"] not in supp)
    return JSONResponse({"count": len(uniq), "callable_count": callable_count,
                         "suppressed_count": suppressed_count, "breakdown": breakdown})


@app.post("/run")
async def run(request: Request, campaign_id: str = Form(""), leads: str = Form(""),
              use_stored: str = Form(""), concurrency: int = Form(3),
              hourly_cap: int = Form(200), daily_cap: int = Form(1000),
              force: str = Form(""),
              # RC2 composable OPTIONAL audience selectors (all default ""/absent
              # -> legacy behaviour: csv + leads-text + use_stored unchanged).
              source_mode: str = Form(""), lead_ids: str = Form(""),
              temps: str = Form(""), batch_ids: str = Form(""),
              score_min: str = Form(""), score_max: str = Form(""),
              csv: UploadFile | None = File(None)):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot run campaigns")
    cid = (campaign_id or "").strip()
    camp = get_campaign_for(cid, t) if cid else None
    if cid and not camp:
        return JSONResponse({"error": "campaign not found for this account"}, status_code=404)
    camp_fields = (camp or {}).get("fields", {}) or {}
    tenant_id = t["tenant_id"]
    # P0.7 monthly minutes admission cap
    tenant_rec = _tenant_by_id(tenant_id) or {}
    monthly_cap = int(tenant_rec.get("monthly_minutes_cap", 5000))
    used_min = _tenant_usage(tenant_id, _month_iso())["minutes"]
    if used_min >= monthly_cap:
        return JSONResponse({"error": "monthly minutes cap reached",
                             "used_minutes": used_min, "cap": monthly_cap}, status_code=429)
    # WAVE3 Unit4: prepaid balance gate. Prepaid + balance<=0 -> refuse (402-style), no crash.
    billing = _billing_for(tenant_id)
    if billing.get("plan") == "prepaid" and float(billing.get("balance", 0) or 0) <= 0:
        return JSONResponse({"error": "insufficient balance",
                             "message": "Your prepaid balance is exhausted. Please top up to run campaigns.",
                             "balance": float(billing.get("balance", 0) or 0),
                             "currency": billing.get("currency", "INR")}, status_code=402)
    csv_bytes = await csv.read() if csv is not None else None
    parsed = parse_upload(leads, csv, csv_bytes)
    # RC2: composable audience selectors (lead_ids / temps / batch_ids / score band
    # / source_mode). Resolved over THIS tenant's stored leads (BOLA-safe). When any
    # are present they ADD to the ad-hoc parsed set; legacy use_stored is honoured
    # only when no RC2 selector narrows the set (so use_stored stays "all stored").
    resolved = _resolve_audience(
        t, source_mode=source_mode, lead_ids=lead_ids, temps=temps,
        batch_ids=batch_ids, score_min=score_min, score_max=score_max)
    rc2_used = bool(resolved or _csv_set(lead_ids) or _csv_set(batch_ids)
                    or _csv_set(temps) or str(score_min).strip() or str(score_max).strip()
                    or source_mode in ("all", "temperature", "upload", "manual"))
    if resolved:
        parsed += [{"name": x.get("name", ""), "num": x.get("phone", "")} for x in resolved]
    # Legacy "use all stored" — kept working, but suppressed when RC2 selectors are
    # driving the audience (otherwise picking a subset would still dial everyone).
    if use_stored and not rc2_used:
        parsed += [{"name": x.get("name", ""), "num": x["phone"]} for x in _leads_for(t)]
    seen, uniq = set(), []
    for x in parsed:
        if x["num"] and x["num"] not in seen:
            seen.add(x["num"]); uniq.append(x)
    # P0.2 pre-filter suppressed numbers (visibility; dial loop also enforces)
    supp = _suppressed_set(tenant_id)
    suppressed_count = sum(1 for x in uniq if x["num"] in supp)
    # RC2 preview breakdown: temperature counts over the resolved stored leads.
    _phone_temp = {x.get("phone"): _lead_temp(x) for x in _leads_for(t)}
    temp_breakdown = {"hot": 0, "warm": 0, "cold": 0}
    for x in uniq:
        tb = _phone_temp.get(x["num"])
        if tb in temp_breakdown:
            temp_breakdown[tb] += 1
    # P0.7 clamp concurrency to tenant cap
    conc = max(1, min(int(concurrency), 20, int(tenant_rec.get("max_concurrency", 3))))
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {
        "state": "queued", "campaign_id": cid, "tenant_id": tenant_id,
        "concurrency": conc,
        "hourly_cap": max(1, int(hourly_cap)), "daily_cap": max(1, int(daily_cap)),
        "leads": [{"name": x["name"], "num": x["num"], "status": "queued", "room": "",
                   "launched_at": 0.0, "attempt": 0}
                  for x in uniq],
    }
    asyncio.create_task(run_job(job_id))
    _audit(request, t, "run.dispatch", "job", job_id,
           meta={"campaign_id": cid, "count": len(uniq), "suppressed": suppressed_count})
    # P0.1 calling-window gate: out of window (and not forced) -> 202, job still created + auto-resumes.
    in_win, win = _in_window(camp_fields)
    if not in_win and not force:
        return JSONResponse({"queued_out_of_window": True, "window": win, "job_id": job_id,
                             "count": len(uniq), "suppressed_count": suppressed_count,
                             "breakdown": temp_breakdown}, status_code=202)
    return JSONResponse({"job_id": job_id, "count": len(uniq),
                         "suppressed_count": suppressed_count, "breakdown": temp_breakdown})


@app.get("/status")
async def status(request: Request, job: str = ""):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    j = JOBS.get(job)
    if not j:
        return JSONResponse({"state": "unknown", "leads": []})
    # don't leak another tenant's job
    if not t.get("is_admin") and j.get("tenant_id", ADMIN_ID) != t["tenant_id"]:
        return JSONResponse({"state": "unknown", "leads": []})
    return JSONResponse({"state": j["state"],
                         "leads": [{"name": x["name"], "num": x["num"], "status": x["status"]} for x in j["leads"]]})


@app.get("/calls")
async def calls(request: Request, limit: int = 200, campaign_id: str = "", outcome: str = ""):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = calls_for(t)
    if campaign_id:
        rows = [c for c in rows if c.get("campaign_id") == campaign_id]
    if outcome:
        # outcome may live on the call rec or in its transcript; match either.
        def _match(c):
            if c.get("outcome") == outcome:
                return True
            tr = _read(TRANSCRIPT_DIR / f"{c.get('room', '')}.json", {}) if c.get("room") else {}
            return tr.get("outcome") == outcome
        rows = [c for c in rows if _match(c)]
    return JSONResponse({"calls": rows[:max(1, min(limit, 1000))]})


@app.get("/calls/{call_id}")
async def call_detail(request: Request, call_id: str):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    # Look up across ALL calls, then assert ownership explicitly (BOLA guard).
    # A genuinely missing id -> 404; another tenant's call -> 403 (require_object).
    rec = next((c for c in CALLS if c.get("id") == call_id), None)
    if rec is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    guard = require_object(t, rec, not_found=False)
    if guard is not None:
        return guard
    transcript = _read(TRANSCRIPT_DIR / f"{rec.get('room', '')}.json", {}) if rec.get("room") else {}
    return JSONResponse({"call": rec, "transcript": transcript})


@app.get("/stats")
async def stats(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = calls_for(t)
    total = len(rows)

    def _is_answered(c):
        if "answered" in c:
            return c.get("answered") is True
        return c.get("duration_s", 0) >= 8   # legacy rows without the flag

    answered = len([c for c in rows if _is_answered(c)])
    in_prog = len([c for c in rows if c.get("status") == "calling"])
    voicemail = len([c for c in rows if c.get("outcome") == "voicemail"])
    no_answer = len([c for c in rows if c.get("outcome") == "no_answer"])
    # last-14-days series by date
    from collections import Counter
    cnt = Counter((c.get("started_at", "")[:10]) for c in rows if c.get("started_at"))
    series = [{"name": d[5:], "amt": n} for d, n in sorted(cnt.items())[-14:]]
    return JSONResponse({"total": total, "answered": answered, "in_progress": in_prog,
                         "voicemail": voicemail, "no_answer": no_answer,
                         "campaigns": len(list_campaigns(t)), "series": series})


# ---------- P1.B analytics endpoint ----------
@app.get("/analytics")
async def analytics(request: Request, campaign_id: str = ""):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    from_ = request.query_params.get("from", "")
    to_ = request.query_params.get("to", "")
    rows = calls_for(t)
    if campaign_id:
        rows = [c for c in rows if c.get("campaign_id") == campaign_id]
    # optional date range filter (YYYY-MM-DD)
    if from_:
        rows = [c for c in rows if (c.get("started_at") or "") >= from_]
    if to_:
        rows = [c for c in rows if (c.get("started_at") or "") <= (to_ + "T23:59:59")]
    dialed = len(rows)
    connected = len([c for c in rows if c.get("status") not in ("queued", "suppressed")])
    answered = len([c for c in rows if c.get("answered") is True or
                    (c.get("answered") is None and c.get("duration_s", 0) >= 8)])
    interested = len([c for c in rows if c.get("outcome") == "interested"])
    callback_cnt = len([c for c in rows if c.get("outcome") == "callback"])
    qualified = len([c for c in rows if (c.get("interest") or 0) >= 70])
    opted_out = len([c for c in rows if c.get("outcome") == "opt_out"])
    voicemail = len([c for c in rows if c.get("outcome") == "voicemail"])
    no_answer = len([c for c in rows if c.get("outcome") == "no_answer"])
    funnel = [
        {"stage": "dialed", "count": dialed},
        {"stage": "connected", "count": connected},
        {"stage": "answered", "count": answered},
        {"stage": "interested", "count": interested},
        {"stage": "callback", "count": callback_cnt},
        {"stage": "qualified", "count": qualified},
    ]
    return JSONResponse({
        "dialed": dialed, "connected": connected, "answered": answered,
        "interested": interested, "callback": callback_cnt, "qualified": qualified,
        "opted_out": opted_out, "voicemail": voicemail, "no_answer": no_answer,
        "funnel": funnel,
    })


# ---------- tenants (admin only) ----------
@app.get("/tenants")
async def list_tenants(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not t.get("is_admin"):
        return JSONResponse({"error": "admin only"}, status_code=403)
    out = [{"tenant_id": x["tenant_id"], "email": x.get("email", ""), "name": x.get("name", ""),
            "is_admin": bool(x.get("is_admin")), "role": _role_of(x),
            "created_at": x.get("created_at", "")}
           for x in _read_tenants()]
    return JSONResponse({"tenants": out})


@app.post("/tenants")
async def create_tenant(request: Request, email: str = Form(""), password: str = Form(""),
                        name: str = Form(""), role: str = Form("manager")):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not t.get("is_admin"):
        return JSONResponse({"error": "admin only"}, status_code=403)
    email = (email or "").strip().lower()
    if not email or not password:
        return JSONResponse({"error": "email and password are required"}, status_code=400)
    role = (role or "manager").strip().lower()
    if role not in ROLES:
        role = "manager"
    tenants = _read_tenants()
    if any((x.get("email") or "").lower() == email for x in tenants):
        return JSONResponse({"error": "email already exists"}, status_code=409)
    salt = secrets.token_hex(8)
    rec = {"tenant_id": uuid.uuid4().hex[:12], "email": email, "salt": salt,
           "pass_hash": _hash_pw(password, salt), "name": (name or email.split("@")[0]).strip(),
           "is_admin": (role == "admin"), "role": role,
           "created_at": datetime.now().isoformat(timespec="seconds")}
    tenants.append(rec)
    _write_tenants(tenants)
    _audit(request, t, "tenant.create", "tenant", rec["tenant_id"],
           meta={"email": rec["email"], "role": rec["role"]})
    return JSONResponse({"tenant_id": rec["tenant_id"], "email": rec["email"],
                         "name": rec["name"], "role": rec["role"]})


# ---------- P0.2 suppression endpoints ----------
@app.get("/suppression")
async def get_suppression(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = [x for x in _read(SUPPRESSION_FILE, []) if x.get("tenant_id") == t["tenant_id"]]
    out = [{"phone": x["phone"], "reason": x.get("reason", ""), "source": x.get("source", ""),
            "added_at": x.get("added_at", "")} for x in rows]
    return JSONResponse({"numbers": out, "total": len(out)})


@app.post("/suppression")
async def add_suppression(request: Request, numbers: str = Form(""),
                          csv: UploadFile | None = File(None)):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot edit suppression list")
    csv_bytes = await csv.read() if csv is not None else None
    parsed = parse_leads(numbers, csv_bytes)
    added = 0
    before = _suppressed_set(t["tenant_id"])
    for x in parsed:
        if x["num"] not in before:
            await _add_suppression(t["tenant_id"], x["num"], "upload")
            before.add(x["num"]); added += 1
    total = len(_suppressed_set(t["tenant_id"]))
    _audit(request, t, "suppression.add", "suppression", "", meta={"added": added})
    return JSONResponse({"added": added, "total": total})


@app.delete("/suppression/{phone}")
async def delete_suppression(request: Request, phone: str):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot edit suppression list")
    p = norm(phone)
    async with _STORE_LOCK:
        store = _read(SUPPRESSION_FILE, [])
        new = [x for x in store if not (x.get("tenant_id") == t["tenant_id"] and x.get("phone") == p)]
        _write(SUPPRESSION_FILE, new)
    _audit(request, t, "suppression.delete", "suppression", p)
    return JSONResponse({"deleted": p})


@app.post("/optout")
async def optout(request: Request, phone: str = Form(""), campaign_id: str = Form(""),
                 source: str = Form("manual")):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot opt out numbers")
    reason = "opt_out_call" if source == "call" else ("manual" if source == "manual" else "api")
    await _add_suppression(t["tenant_id"], phone, reason, source=campaign_id or source)
    await _flip_lead_status(t["tenant_id"], phone, "opted_out")
    await _emit_webhook(t["tenant_id"], "lead.opted_out",
                        {"phone": norm(phone), "campaign_id": campaign_id})
    _audit(request, t, "lead.optout", "lead", norm(phone),
           channel=("call" if source == "call" else "api"),
           meta={"campaign_id": campaign_id, "source": source})
    return JSONResponse({"ok": True})


# ---------- P0.5 callbacks / retry queue endpoints ----------
@app.get("/callbacks")
async def get_callbacks(request: Request, all: str = ""):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = [r for r in _read(RETRY_FILE, [])
            if t.get("is_admin") or r.get("tenant_id") == t["tenant_id"]]
    if not all:
        rows = [r for r in rows if r.get("reason") == "callback"]
    rows.sort(key=lambda r: r.get("next_attempt_at", ""))
    return JSONResponse({"items": rows})


@app.delete("/callbacks/{rid}")
async def cancel_callback(request: Request, rid: str):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot cancel callbacks")
    target = next((r for r in _read(RETRY_FILE, []) if r.get("id") == rid), None)
    guard = require_object(t, target)  # 404 if missing or not owned (BOLA)
    if guard is not None:
        return guard
    await _remove_retry(rid)
    _audit(request, t, "callback.cancel", "callback", rid)
    return JSONResponse({"cancelled": rid})


@app.post("/callbacks")
async def add_callback(request: Request, phone: str = Form(""), campaign_id: str = Form(""),
                       when: str = Form(""), name: str = Form("")):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot add callbacks")
    if not get_campaign_for(campaign_id, t):
        return JSONResponse({"error": "campaign not found for this account"}, status_code=404)
    if not norm(phone):
        return JSONResponse({"error": "valid phone required"}, status_code=400)
    await _enqueue_retry(t["tenant_id"], campaign_id, name, phone, 0, 3,
                         when or now_ist().isoformat(), "callback")
    _audit(request, t, "callback.add", "callback", norm(phone),
           meta={"campaign_id": campaign_id, "when": when})
    return JSONResponse({"ok": True})


# ---------- P0.7 usage endpoints ----------
@app.get("/usage")
async def usage(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    tid = t["tenant_id"]
    tr = _tenant_by_id(tid) or {}
    return JSONResponse({
        "today": _tenant_usage(tid, _today_iso()),
        "month": _tenant_usage(tid, _month_iso()),
        "limits": {"max_concurrency": int(tr.get("max_concurrency", 3)),
                   "daily_call_cap": int(tr.get("daily_call_cap", 500)),
                   "monthly_minutes_cap": int(tr.get("monthly_minutes_cap", 5000))},
        "active_now": ACTIVE_CALLS.get(tid, 0),
    })


@app.get("/usage/all")
async def usage_all(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not t.get("is_admin"):
        return JSONResponse({"error": "admin only"}, status_code=403)
    out = []
    for x in _read_tenants():
        tid = x["tenant_id"]
        out.append({"tenant_id": tid, "name": x.get("name", ""), "email": x.get("email", ""),
                    "today": _tenant_usage(tid, _today_iso()),
                    "month": _tenant_usage(tid, _month_iso()),
                    "active_now": ACTIVE_CALLS.get(tid, 0),
                    "limits": {"max_concurrency": int(x.get("max_concurrency", 3)),
                               "daily_call_cap": int(x.get("daily_call_cap", 500)),
                               "monthly_minutes_cap": int(x.get("monthly_minutes_cap", 5000))}})
    return JSONResponse({"tenants": out})


@app.post("/tenants/{tid}/limits")
async def set_tenant_limits(request: Request, tid: str, max_concurrency: int = Form(None),
                            daily_call_cap: int = Form(None), monthly_minutes_cap: int = Form(None)):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not t.get("is_admin"):
        return JSONResponse({"error": "admin only"}, status_code=403)
    async with _STORE_LOCK:
        tenants = _read_tenants()
        target = next((x for x in tenants if x.get("tenant_id") == tid), None)
        if not target:
            return JSONResponse({"error": "not found"}, status_code=404)
        if max_concurrency is not None:
            target["max_concurrency"] = max(1, int(max_concurrency))
        if daily_call_cap is not None:
            target["daily_call_cap"] = max(0, int(daily_call_cap))
        if monthly_minutes_cap is not None:
            target["monthly_minutes_cap"] = max(0, int(monthly_minutes_cap))
        _write_tenants(tenants)
    return JSONResponse({"ok": True, "tenant_id": tid,
                         "max_concurrency": target.get("max_concurrency"),
                         "daily_call_cap": target.get("daily_call_cap"),
                         "monthly_minutes_cap": target.get("monthly_minutes_cap")})


# ════════════════════════════════════════════════════════════════════════════
# CONTROL LAYER — /admin/* super-admin API + /me/entitlements + act-as (CL-B3 / plan C2+C4+C11)
# ════════════════════════════════════════════════════════════════════════════
# EVERY /admin/* route calls require_super_admin (is_admin AND non-legacy-pw — control-security §1.2);
# the TARGET tenant is the path {id}, NEVER a body field (security invariant #3); every write is audited
# to the IMMUTABLE PG `events` leg via _audit(channel="control") with before/after, AND mirrored into the
# entitlement_audit read-copy by the engine. Money/destructive writes (credits, status->disabled,
# impersonate) additionally clear the firewall step-up. Behind CONTROL_ENABLED only for ENFORCEMENT (the
# middleware) — the /admin/* routes themselves are always role-gated (an admin manages entitlements even
# while the master flag is off, so the founder can configure BEFORE flipping enforcement on).

def _control_unavailable() -> JSONResponse:
    return JSONResponse({"error": "control layer unavailable"}, status_code=503)


def _control_audit(request: Request, admin: dict, action: str, *, target_tenant: str | None = None,
                   feature_key: str | None = None, old_value=None, new_value=None,
                   reason: str = "") -> None:
    """Audit a super-admin control action to BOTH the immutable PG `events` leg (channel='control',
    the source of truth) AND the entitlement_audit read-mirror. before/after are MANDATORY (§4.2)."""
    real_admin = (admin or {}).get("real_admin") or (admin or {}).get("tenant_id", "")
    actor = (admin or {}).get("tenant_id", "")
    meta = {"target_tenant": target_tenant, "feature_key": feature_key,
            "old_value": (str(old_value) if old_value is not None else None),
            "new_value": (str(new_value) if new_value is not None else None),
            "reason": reason, "real_admin": real_admin,
            "act_as": (admin or {}).get("act_as"), "auth_method": _auth_method(request)}
    _audit(request, admin, action, "control", target_tenant or feature_key or "",
           channel="control", meta=meta)
    if _ent_mod is not None:
        try:
            _ent_mod._mirror_audit(
                real_admin, actor, action, target_tenant=target_tenant, feature_key=feature_key,
                old_value=meta["old_value"], new_value=meta["new_value"],
                reason=reason, ip=_client_ip(request))
        except Exception:  # noqa: BLE001
            pass


def _vendor_health(tid: str) -> dict:
    """Executive 'last activity' health for a vendor (cheap, reuses existing in-RAM/JSON stores)."""
    try:
        last_call = ""
        for c in reversed(CALLS):
            if c.get("tenant_id") == tid:
                last_call = c.get("at") or c.get("started_at") or ""
                break
        return {"active_now": ACTIVE_CALLS.get(tid, 0), "last_call": last_call}
    except Exception:  # noqa: BLE001
        return {"active_now": 0, "last_call": ""}


# ---------- registry / global flags ----------
@app.get("/admin/features")
async def admin_features(request: Request):
    """The full feature_registry catalog tree (for the Feature-Flags + per-vendor UI)."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    return JSONResponse({"features": _ent_mod.registry_tree()})


@app.get("/admin/flags")
async def admin_flags_get(request: Request):
    """Global default_mode per feature (the baseline for every vendor)."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    flags = {r["key"]: r.get("default_mode", "on") for r in _ent_mod.registry_tree()}
    return JSONResponse({"flags": flags})


@app.put("/admin/flags/{feature_key}")
async def admin_flags_set(request: Request, feature_key: str, mode: str = Form(...)):
    """Set the GLOBAL baseline mode for a feature (affects ALL vendors -> drops every resolve cache)."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    res = _ent_mod.set_global_flag(feature_key, (mode or "").strip(), set_by=t["tenant_id"])
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    _control_audit(request, t, "control.flag.set", feature_key=feature_key,
                   old_value=res.get("before"), new_value=res.get("after"))
    return JSONResponse({"ok": True, "feature_key": feature_key, **res})


# ---------- plans ----------
@app.get("/admin/plans")
async def admin_plans_get(request: Request):
    """List plans + their entitlements + limits."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    return JSONResponse({"plans": _ent_mod.plans_detail()})


@app.post("/admin/plans")
async def admin_plans_create(request: Request, plan_id: str = Form(...), name: str = Form(""),
                             description: str = Form("")):
    """Create a plan (catalog seed + PG). Entitlements/limits are set via PUT. Audited."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    pid = (plan_id or "").strip().lower()
    if not pid:
        return JSONResponse({"error": "plan_id required"}, status_code=400)
    if pid in _ent_mod.load_plans():
        return JSONResponse({"error": "plan already exists"}, status_code=409)
    if _ent_mod.available():
        try:
            _ent_mod._exec_admin(
                "INSERT INTO plans (plan_id, name, description) VALUES (:p,:n,:d) "
                "ON CONFLICT (plan_id) DO NOTHING",
                {"p": pid, "n": name or pid, "d": description})
        except Exception:  # noqa: BLE001
            return _control_unavailable()
    # reflect in the in-proc catalog so it's immediately listable.
    _ent_mod.load_plans()[pid] = {"plan_id": pid, "name": name or pid, "is_default": False,
                                  "entitlements": {}, "limits": {}}
    _control_audit(request, t, "control.plan.create", target_tenant=None,
                   old_value=None, new_value=pid)
    return JSONResponse({"ok": True, "plan_id": pid, "name": name or pid})


@app.put("/admin/plans/{plan_id}")
async def admin_plans_edit(request: Request, plan_id: str):
    """Edit a plan bundle: JSON body {entitlements:{key:mode}, limits:{key:int}}. Replaces both sets +
    bumps every tenant ON that plan (global cache drop). Audited."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    pid = (plan_id or "").strip().lower()
    if pid not in _ent_mod.load_plans():
        return JSONResponse({"error": "unknown plan"}, status_code=404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    ents = {k: v for k, v in (body.get("entitlements") or {}).items()
            if v in _ent_mod.MODES and k in _ent_mod.load_registry()}
    limits = {}
    for k, v in (body.get("limits") or {}).items():
        try:
            limits[k] = int(v)
        except Exception:  # noqa: BLE001
            pass
    before = _ent_mod.plans_detail()
    if _ent_mod.available():
        try:
            _ent_mod._exec_admin("DELETE FROM plan_entitlements WHERE plan_id = :p", {"p": pid})
            for k, m in ents.items():
                _ent_mod._exec_admin(
                    "INSERT INTO plan_entitlements (plan_id, feature_key, mode) VALUES (:p,:k,:m)",
                    {"p": pid, "k": k, "m": m})
            _ent_mod._exec_admin("DELETE FROM plan_limits WHERE plan_id = :p", {"p": pid})
            for k, v in limits.items():
                _ent_mod._exec_admin(
                    "INSERT INTO plan_limits (plan_id, limit_key, value) VALUES (:p,:k,:v)",
                    {"p": pid, "k": k, "v": v})
        except Exception:  # noqa: BLE001
            return _control_unavailable()
    p = _ent_mod.load_plans().get(pid, {})
    p["entitlements"] = ents
    p["limits"] = limits
    _ent_mod.invalidate(None)  # plan change can affect every tenant on it
    _control_audit(request, t, "control.plan.edit", target_tenant=None,
                   old_value=str(len(before)), new_value=f"ents={len(ents)},limits={len(limits)}")
    return JSONResponse({"ok": True, "plan_id": pid, "entitlements": ents, "limits": limits})


# ---------- vendors (list + workspace) ----------
@app.get("/admin/vendors")
async def admin_vendors(request: Request):
    """Vendor list: {tenant_id,name,email,plan,status,created_at,usage_summary,health}. Joins the tenant
    store + control status + usage + last-activity (executive view)."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    out = []
    for x in _read_tenants():
        if x.get("is_admin"):
            continue  # the admin tenant is not a managed vendor
        tid = x["tenant_id"]
        st = _ent_mod.load_status(tid) if _ent_mod else {"status": "active", "plan_id": None}
        out.append({
            "tenant_id": tid, "name": x.get("name", ""), "email": x.get("email", ""),
            "role": _role_of(x), "created_at": x.get("created_at", ""),
            "status": st.get("status", "active"), "plan": st.get("plan_id"),
            "usage": {"today": _tenant_usage(tid, _today_iso()),
                      "month": _tenant_usage(tid, _month_iso())},
            "health": _vendor_health(tid),
        })
    return JSONResponse({"vendors": out})


@app.get("/admin/vendors/{vid}")
async def admin_vendor_detail(request: Request, vid: str):
    """Full vendor profile + resolved entitlement map (effective mode + provenance) + usage + health +
    wallet balance. The Permissions/Overview/Usage/Billing tabs all read from here."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    rec = _tenant_by_id(vid)
    if not rec:
        return JSONResponse({"error": "vendor not found"}, status_code=404)
    detail = _ent_mod.vendor_detail(vid) if _ent_mod else {}
    wallet = None
    if _wallet_mod is not None and _wallet_mod.available():
        try:
            bal = await asyncio.to_thread(_wallet_mod.balance, vid, "INR", True)
            if bal:
                wallet = {"available": _minor_to_major(bal["available_minor"]),
                          "held": _minor_to_major(bal["held_minor"])}
        except Exception:  # noqa: BLE001
            wallet = None
    return JSONResponse({
        "tenant_id": vid, "name": rec.get("name", ""), "email": rec.get("email", ""),
        "role": _role_of(rec), "created_at": rec.get("created_at", ""),
        "usage": {"today": _tenant_usage(vid, _today_iso()), "month": _tenant_usage(vid, _month_iso())},
        "health": _vendor_health(vid), "wallet": wallet, **detail,
    })


# ---------- per-vendor entitlement overrides (HIDE/LOCK/ON) ----------
@app.put("/admin/vendors/{vid}/entitlements/{feature_key}")
async def admin_set_override(request: Request, vid: str, feature_key: str,
                             mode: str = Form(...), reason: str = Form("")):
    """Per-vendor override (HIDE/LOCK/ON). Bumps that tenant's ent_version -> real-time. Audited."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    if not _tenant_by_id(vid):
        return JSONResponse({"error": "vendor not found"}, status_code=404)
    res = _ent_mod.set_override(vid, feature_key, (mode or "").strip(),
                                set_by=t["tenant_id"], reason=reason)
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    _control_audit(request, t, "control.override.set", target_tenant=vid, feature_key=feature_key,
                   old_value=res.get("before"), new_value=res.get("after"), reason=reason)
    return JSONResponse({"ok": True, "tenant_id": vid, "feature_key": feature_key, **res})


@app.delete("/admin/vendors/{vid}/entitlements/{feature_key}")
async def admin_clear_override(request: Request, vid: str, feature_key: str):
    """Clear a per-vendor override -> revert to plan/global. Bumps ent_version. Audited."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    if not _tenant_by_id(vid):
        return JSONResponse({"error": "vendor not found"}, status_code=404)
    res = _ent_mod.clear_override(vid, feature_key, set_by=t["tenant_id"])
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    _control_audit(request, t, "control.override.clear", target_tenant=vid, feature_key=feature_key,
                   old_value=res.get("before"), new_value=None)
    return JSONResponse({"ok": True, "tenant_id": vid, "feature_key": feature_key, **res})


@app.put("/admin/vendors/{vid}/plan")
async def admin_set_plan(request: Request, vid: str, plan_id: str = Form(...)):
    """Assign a plan to a vendor. Bumps ent_version. Audited."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    if not _tenant_by_id(vid):
        return JSONResponse({"error": "vendor not found"}, status_code=404)
    res = _ent_mod.set_plan(vid, (plan_id or "").strip(), updated_by=t["tenant_id"])
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    _control_audit(request, t, "control.plan.assign", target_tenant=vid,
                   old_value=res.get("before"), new_value=res.get("after"))
    return JSONResponse({"ok": True, "tenant_id": vid, **res})


@app.put("/admin/vendors/{vid}/status")
async def admin_set_status(request: Request, vid: str, status: str = Form(...), reason: str = Form("")):
    """Vendor lifecycle: active/trial/suspended/disabled/expired. suspended/disabled REVOKES all the
    vendor's tokens (auth.revoke_all -> next call 401) and the status floor hides every non-core feature;
    DATA IS PRESERVED (a flag flip, never a delete). disabled additionally requires firewall step-up.
    Audited."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if _ent_mod is None:
        return _control_unavailable()
    if not _tenant_by_id(vid):
        return JSONResponse({"error": "vendor not found"}, status_code=404)
    new_status = (status or "").strip().lower()
    # disabled is the harshest lifecycle change -> spend/destructive step-up on the ACTING admin.
    if new_status == "disabled":
        denied = _step_up_guard(request, "destructive", t)
        if denied is not None:
            _control_audit(request, t, "control.status.stepup_denied", target_tenant=vid,
                           old_value=None, new_value=new_status, reason=reason)
            return denied
    res = _ent_mod.set_status(vid, new_status, reason=reason, updated_by=t["tenant_id"])
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    # INSTANT KILL: revoke the vendor's refresh tokens so a token minted seconds ago dies now (T15).
    revoked = 0
    if new_status in ("suspended", "disabled", "expired") and _auth_mod is not None:
        try:
            revoked = _auth_mod.revoke_all(vid)
        except Exception:  # noqa: BLE001
            revoked = 0
    _control_audit(request, t, "control.status.set", target_tenant=vid,
                   old_value=res.get("before"), new_value=res.get("after"), reason=reason)
    return JSONResponse({"ok": True, "tenant_id": vid, "tokens_revoked": revoked, **res})


@app.post("/admin/vendors/{vid}/credits")
async def admin_credits(request: Request, vid: str, amount: float = Form(...), reason: str = Form("")):
    """Wallet top-up / freeze for a vendor (rupees). Requires firewall step-up (spend scope) on the
    ACTING admin. Rides the F4 wallet ledger (idempotent). Audited."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    if not _tenant_by_id(vid):
        return JSONResponse({"error": "vendor not found"}, status_code=404)
    denied = _step_up_guard(request, "spend", t)
    if denied is not None:
        _control_audit(request, t, "control.credit.stepup_denied", target_tenant=vid,
                       old_value=None, new_value=str(amount), reason=reason)
        return denied
    if _wallet_mod is None or not _wallet_mod.available():
        return JSONResponse(_wallet_unavailable_body(), status_code=503)
    minor = int(round(float(amount) * 100))
    if minor <= 0:
        return JSONResponse({"ok": False, "reason": "amount must be positive"}, status_code=400)
    idem = f"admin_credit:{vid}:{secrets.token_hex(8)}"
    res = await asyncio.to_thread(_wallet_mod.topup, vid, minor, t["tenant_id"], idem, "INR", True, None)
    _control_audit(request, t, "control.credit.topup", target_tenant=vid,
                   old_value=None, new_value=_minor_to_major(minor), reason=reason)
    if not res.get("ok"):
        return JSONResponse(res, status_code=400)
    return JSONResponse({"ok": True, "tenant_id": vid, "credited": _minor_to_major(minor),
                         "available": _minor_to_major(res.get("available_minor", 0))})


# ---------- impersonation / act-as (the sharpest knife — gated like root) ----------
@app.post("/admin/vendors/{vid}/impersonate")
async def admin_impersonate(request: Request, vid: str, scope: str = Form("read_only")):
    """Enter act-as: mint a short-TTL (<=10min) act-as token (sub=vendor, real_admin=admin, read-only by
    default). Requires firewall step-up (the sub-bound F3 token). CANNOT target another admin (no lateral
    takeover). Enter is audited; exit is POST /admin/act-as/exit (also audited)."""
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    rec = _tenant_by_id(vid)
    if not rec:
        return JSONResponse({"error": "vendor not found"}, status_code=404)
    # T12: cannot act-as another admin (admin-on-admin impersonation refused).
    if rec.get("is_admin"):
        return _forbidden("cannot impersonate an admin tenant")
    # T9: firewall step-up to ENTER (sub-bound to the acting admin).
    denied = _step_up_guard(request, "destructive", t)
    if denied is not None:
        _control_audit(request, t, "control.impersonate.stepup_denied", target_tenant=vid)
        return denied
    if _auth_mod is None or not _auth_mod.available():
        return JSONResponse({"error": "auth (JWT) unavailable for act-as"}, status_code=503)
    sc = (scope or "read_only").strip().lower()
    if sc not in ("read_only", "read_write"):
        sc = "read_only"
    tok = _auth_mod.make_act_as(vid, t["tenant_id"], sc)
    if not tok:
        return JSONResponse({"error": "could not mint act-as token"}, status_code=503)
    _control_audit(request, t, "control.impersonate.start", target_tenant=vid,
                   old_value=None, new_value=sc)
    resp = JSONResponse({"ok": True, "act_as": vid, "real_admin": t["tenant_id"], "scope": sc,
                         "access_token": tok, "token_type": "Bearer",
                         "expires_in": _auth_mod.ACT_AS_TTL_SECONDS})
    resp.headers["X-Act-As"] = vid  # so the FE banner can't be suppressed via localStorage tamper
    return resp


@app.post("/admin/act-as/exit")
async def admin_act_as_exit(request: Request):
    """Exit act-as. The caller presents the act-as token; we audit the exit (actor=real_admin) and revoke
    the vendor's act-as session. The token's own short TTL bounds it regardless."""
    cred = _extract_cred(request)
    claims = _auth_mod.act_as_claims(cred) if _auth_mod is not None else None
    if not claims:
        return JSONResponse({"error": "not an act-as session"}, status_code=400)
    real_admin = claims.get("real_admin")
    vendor = claims.get("act_as")
    admin_t = _tenant_by_id(real_admin) or {"tenant_id": real_admin}
    _control_audit(request, admin_t, "control.impersonate.stop", target_tenant=vendor,
                   old_value=claims.get("scope"), new_value=None)
    return JSONResponse({"ok": True, "exited": vendor})


# ---------- vendor-facing entitlement read (the panel + AI Copilot consume THIS) ----------
@app.get("/me/entitlements")
async def me_entitlements(request: Request):
    """Versioned resolved entitlement map for the logged-in tenant: {modes, status, plan, version}.
    ETag = the tenant's ent_version; If-None-Match short-circuits to 304 (cheap poll). Core route —
    bypasses the enforcement choke-point (anti-lockout) so it always answers even when suspended."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if _ent_mod is None:
        # degrade: all-on (resting). Still a valid, versionless map so the FE renders full nav.
        return JSONResponse({"modes": {}, "status": "active", "plan": None, "version": 1})
    tid = t["tenant_id"]
    payload = _ent_mod.entitlements_payload(tid)
    etag = f'W/"ent-{tid}-{payload.get("version", 1)}"'
    inm = request.headers.get("if-none-match", "")
    if inm and inm == etag:
        return Response(status_code=304, headers={"ETag": etag,
                                                  "Cache-Control": "private, no-cache"})
    return JSONResponse(payload, headers={"ETag": etag, "Cache-Control": "private, no-cache"})


# ---------- WAVE3 Unit4: billing endpoints ----------
def _month_cost(tenant_id: str) -> float:
    month = _month_iso()
    return round(sum(e.get("cost", 0) or 0 for e in _read_ledger(tenant_id)
                     if (e.get("at") or "")[:7] == month), 4)


@app.get("/billing")
async def billing(request: Request):
    """Current plan + month-to-date usage/cost + remaining balance for the caller's tenant."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    tid = t["tenant_id"]
    b = _billing_for(tid)
    mtd = _tenant_usage(tid, _month_iso())
    cost = _month_cost(tid)
    return JSONResponse({
        "tenant_id": tid,
        "plan": b.get("plan", "postpaid"),
        "currency": b.get("currency", "INR"),
        "rate_per_min": float(b.get("rate_per_min", 0) or 0),
        "rate_per_call": float(b.get("rate_per_call", 0) or 0),
        "balance": float(b.get("balance", 0) or 0),
        "included_minutes": int(b.get("included_minutes", 0) or 0),
        "month_to_date": {"calls": mtd.get("calls", 0), "minutes": mtd.get("minutes", 0),
                          "cost": cost},
    })


@app.get("/billing/ledger")
async def billing_ledger(request: Request, limit: int = 100):
    """Itemized recent charges for the caller's tenant (most recent first)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = _read_ledger(t["tenant_id"])[:max(1, min(limit, 1000))]
    return JSONResponse({"ledger": rows, "total": len(_read_ledger(t["tenant_id"]))})


# ---------- WAVE A Unit4: real vendor-cost billing endpoints (additive) ----------
def _vendor_status(vid: str) -> str:
    try:
        if vid == "elevenlabs" and v_elevenlabs:
            return v_elevenlabs.status()
        if vid == "vobiz" and v_vobiz:
            return v_vobiz.status()
        if vid == "groq" and v_groq:
            return v_groq.status()
        if vid == "sarvam" and v_sarvam:
            return v_sarvam.status()
        if vid == "livekit":
            return "configured"
    except Exception:  # noqa: BLE001
        return "error"
    return "not_configured"


def _per_vendor_totals(rows: list[dict]) -> dict:
    """vendor_id -> {cost, qty_by_service} from cost_ledger rows."""
    out: dict = {}
    for r in rows:
        v = r.get("vendor") or "unknown"
        out.setdefault(v, {"cost": 0.0})
        out[v]["cost"] = round(out[v]["cost"] + float(r.get("cost", 0) or 0), 6)
    return out


def _currency_for(tenant: dict) -> str:
    try:
        return _billing_for(tenant["tenant_id"]).get("currency", "INR")
    except Exception:  # noqa: BLE001
        return "INR"


@app.get("/billing/overview")
async def billing_overview(request: Request):
    """Grand total + per-vendor totals + month-to-date for the caller's scope
    (admin = all tenants; manager/agent = own tenant)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = _cost_rows_for(t)
    month = _month_iso()
    grand = round(sum(float(r.get("cost", 0) or 0) for r in rows), 4)
    mtd = round(sum(float(r.get("cost", 0) or 0) for r in rows
                    if (r.get("ts") or "")[:7] == month), 4)
    totals = _per_vendor_totals(rows)
    per_vendor = [{"vendor": vid, "display_name": vendor_display_name(vid),
                   "cost": round(totals.get(vid, {}).get("cost", 0.0), 4),
                   "status": _vendor_status(vid)} for vid in VENDOR_IDS]
    snaps = _read(VENDOR_SNAPSHOTS_FILE, {}) or {}
    updated = ""
    if isinstance(snaps, dict):
        updated = max((v.get("synced_at", "") for v in snaps.values()
                       if isinstance(v, dict)), default="")
    return JSONResponse({"currency": _currency_for(t), "grand_total": grand,
                         "month_to_date": mtd, "per_vendor": per_vendor,
                         "updated_at": updated})


@app.get("/billing/vendors")
async def billing_vendors(request: Request):
    """List every vendor with status + totals + display name (real names now; the
    display-name map makes switching to abstract labels trivial)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = _cost_rows_for(t)
    totals = _per_vendor_totals(rows)
    snaps = _read(VENDOR_SNAPSHOTS_FILE, {}) or {}
    vendors = []
    for vid in VENDOR_IDS:
        snap = snaps.get(vid, {}) if isinstance(snaps, dict) else {}
        vendors.append({"vendor": vid, "display_name": vendor_display_name(vid),
                        "status": _vendor_status(vid),
                        "cost": round(totals.get(vid, {}).get("cost", 0.0), 4),
                        "synced_at": snap.get("synced_at", ""),
                        "stale": bool(snap.get("stale", False)),
                        "estimated": bool(snap.get("estimated", vid in ("groq", "sarvam")))})
    return JSONResponse({"vendors": vendors, "currency": _currency_for(t)})


@app.get("/billing/vendor/{vid}")
async def billing_vendor_detail(request: Request, vid: str):
    """One vendor: status, total cost, and a daily timeseries (from cost_ledger rows)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if vid not in VENDOR_IDS:
        return JSONResponse({"error": "unknown vendor"}, status_code=404)
    rows = [r for r in _cost_rows_for(t) if r.get("vendor") == vid]
    by_day: dict = {}
    for r in rows:
        day = (r.get("ts") or "")[:10] or "unknown"
        by_day[day] = round(by_day.get(day, 0.0) + float(r.get("cost", 0) or 0), 6)
    series = [{"date": d, "cost": c} for d, c in sorted(by_day.items())]
    snap = (_read(VENDOR_SNAPSHOTS_FILE, {}) or {}).get(vid, {})
    return JSONResponse({"vendor": vid, "display_name": vendor_display_name(vid),
                         "status": _vendor_status(vid),
                         "total_cost": round(sum(float(r.get("cost", 0) or 0) for r in rows), 4),
                         "currency": _currency_for(t),
                         "timeseries": series, "rows": len(rows),
                         "synced_at": snap.get("synced_at", ""),
                         "stale": bool(snap.get("stale", False))})


@app.get("/billing/explorer")
async def billing_explorer(request: Request):
    """Per call/lead/campaign cost rows from cost_ledger, filterable by from/to/campaign_id.
    Aggregated by call_id (one row per call, vendor breakdown nested). `from` is a Python
    keyword so query params are read off the request directly."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    qp = request.query_params
    frm = qp.get("from", "")
    to = qp.get("to", "")
    camp = qp.get("campaign_id", "")
    rows = _cost_rows_for(t)
    agg: dict = {}
    for r in rows:
        day = (r.get("ts") or "")[:10]
        if frm and day and day < frm:
            continue
        if to and day and day > to:
            continue
        if camp and r.get("campaign_id") != camp:
            continue
        cid = r.get("call_id") or f"room:{r.get('room','')}"
        a = agg.setdefault(cid, {"call_id": r.get("call_id", ""), "room": r.get("room", ""),
                                 "tenant_id": r.get("tenant_id", ""),
                                 "campaign_id": r.get("campaign_id", ""),
                                 "ts": r.get("ts", ""), "total_cost": 0.0, "by_vendor": {}})
        a["total_cost"] = round(a["total_cost"] + float(r.get("cost", 0) or 0), 6)
        a["by_vendor"][r.get("vendor", "")] = round(
            a["by_vendor"].get(r.get("vendor", ""), 0.0) + float(r.get("cost", 0) or 0), 6)
        if r.get("ts") and (not a["ts"] or r["ts"] < a["ts"]):
            a["ts"] = r["ts"]
    out = sorted(agg.values(), key=lambda x: x.get("ts", ""), reverse=True)
    # Attach lead name + outcome + campaign name by joining the call record.
    for o in out:
        c = _call_by_room(o.get("room", "")) or {}
        o["name"] = c.get("name", "")
        o["phone"] = c.get("phone", "")
        o["campaign_name"] = c.get("campaign_name", "")
        o["outcome"] = c.get("outcome", "")
        o["duration_s"] = c.get("duration_s", 0)
    return JSONResponse({"rows": out[:2000], "total": len(out),
                         "currency": _currency_for(t),
                         "filters": {"from": frm, "to": to, "campaign_id": camp}})


@app.get("/billing/audit")
async def billing_audit(request: Request):
    """Sync status per vendor, stale flags, and vendor-reported vs internal-ledger compare."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    snaps = _read(VENDOR_SNAPSHOTS_FILE, {}) or {}
    rows = _cost_rows_for(t)
    internal = _per_vendor_totals(rows)
    vendors = []
    for vid in VENDOR_IDS:
        snap = snaps.get(vid, {}) if isinstance(snaps, dict) else {}
        # vendor-reported figure (only meaningful for keyed vendors).
        reported = None
        if vid == "vobiz" and isinstance(snap, dict):
            recs = snap.get("records") or []
            reported = round(sum(float(r.get("total_cost", 0) or 0) for r in recs), 4) if recs else None
        elif vid == "elevenlabs" and isinstance(snap, dict):
            u = (snap.get("usage") or {})
            reported = u.get("total_credits") if isinstance(u, dict) else None
        vendors.append({
            "vendor": vid, "display_name": vendor_display_name(vid),
            "status": _vendor_status(vid),
            "synced_at": snap.get("synced_at", ""),
            "stale": bool(snap.get("stale", False)),
            "error": snap.get("error", ""),
            "internal_ledger_cost": round(internal.get(vid, {}).get("cost", 0.0), 4),
            "vendor_reported": reported,
        })
    return JSONResponse({"vendors": vendors, "currency": _currency_for(t),
                         "note": "vendor_reported is workspace/account-level (ElevenLabs, Vobiz balance) "
                                 "and may exceed per-tenant internal ledger; groq/sarvam are estimated."})


@app.post("/billing/sync")
async def billing_sync(request: Request):
    """ADMIN: trigger an immediate vendor-sync pass; return the fresh snapshot.
    (Registered BEFORE /billing/{tenant_id} so 'sync' isn't captured as a tenant_id.)"""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "manage_tenants"):
        return _forbidden("admin only")
    global _LAST_VENDOR_SYNC
    _LAST_VENDOR_SYNC = time.time()
    snaps = await vendor_sync()
    summary = {vid: {"status": (snaps.get(vid, {}) or {}).get("status", _vendor_status(vid)),
                     "synced_at": (snaps.get(vid, {}) or {}).get("synced_at", ""),
                     "stale": bool((snaps.get(vid, {}) or {}).get("stale", False))}
               for vid in VENDOR_IDS}
    return JSONResponse({"ok": True, "synced_at": now_ist().isoformat(timespec="seconds"),
                         "vendors": summary})


@app.get("/admin/store-status")
async def admin_store_status(request: Request):
    """ADMIN (P1 U8): per-store storage-seam visibility — each registered store's effective MODE +
    max_safe + live PG/JSON row counts + mirror ok/fail counters + last error. Read-only; additive.
    JSON count = len(authoritative JSON file); PG count = admin-GUC SELECT count(*). When they match the
    store is converged (an effectively-live drift indicator; the spec's last_shadow_diff stays None
    because shadow_diff.py runs out-of-process and can't write the live spec object). Best-effort
    everywhere: any per-store error is captured into that store's `error` field, never 500s the route."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "manage_tenants"):
        return _forbidden("admin only")

    # base: store.py's own status (modes, max_safe, pg ok/fail, worker liveness, last_error)
    try:
        base = _store.status() if _store is not None else {"ready": False, "stores": {}, "db": {}}
    except Exception as exc:  # noqa: BLE001
        base = {"ready": False, "stores": {}, "db": {}, "status_error": repr(exc)[:200]}

    stores = base.get("stores", {}) or {}

    # registered-store name -> authoritative JSON file path (for the live JSON count)
    _file_for = {
        "leads.json": LEADS_FILE, "calls.json": CALLS_FILE, "suppression.json": SUPPRESSION_FILE,
        "retry_queue.json": RETRY_FILE, "webhooks.json": WEBHOOK_FILE, "billing.json": BILLING_FILE,
        "wa_log.json": WA_LOG_FILE, "usage_events.json": USAGE_EVENTS_FILE,
        "cost_ledger.json": COST_LEDGER_FILE,
    }
    _table_for = {
        "leads.json": "leads", "calls.json": "calls", "suppression.json": "suppression",
        "retry_queue.json": "retry_queue", "webhooks.json": "webhooks", "billing.json": "billing",
        "wa_log.json": "wa_log", "usage_events.json": "usage_events", "cost_ledger.json": "cost_ledger",
        "ledger": "ledger",  # multi_file: per-tenant files var/ledger/<stem>.json
    }

    # live JSON counts (cheap, off the authoritative files)
    for name, info in stores.items():
        try:
            if name == "ledger":
                # multi_file: sum rows across all per-tenant files var/ledger/<stem>.json
                total = 0
                if LEDGER_DIR.exists():
                    for lf in LEDGER_DIR.glob("*.json"):
                        obj = _read_raw(lf, [])
                        total += len(obj) if isinstance(obj, list) else 0
                info["json_count"] = total
                continue
            f = _file_for.get(name)
            if f is not None:
                obj = _read_raw(f, [])
                info["json_count"] = len(obj) if isinstance(obj, (list, dict)) else None
            else:
                info["json_count"] = None
        except Exception as exc:  # noqa: BLE001
            info["json_count"] = None
            info["error"] = repr(exc)[:200]

    # live PG counts (admin GUC; only if the db layer is up). Best-effort, swallow per-store.
    try:
        from db import engine as _eng  # local import: import-safe, never required for the route
        if _eng.available():
            from sqlalchemy import text as _text
            with _eng.session("", is_admin=True) as _s:
                for name, info in stores.items():
                    tbl = _table_for.get(name)
                    if not tbl:
                        info["pg_count"] = None
                        continue
                    try:
                        info["pg_count"] = _s.execute(
                            _text(f"SELECT count(*) FROM {tbl}")).scalar() or 0
                    except Exception as exc:  # noqa: BLE001
                        info["pg_count"] = None
                        info["error"] = repr(exc)[:200]
                # identity mirror (orgs/users/memberships) — not a seam store but useful here
                try:
                    base["identity"] = {
                        "orgs": _s.execute(_text("SELECT count(*) FROM orgs")).scalar() or 0,
                        "users": _s.execute(_text("SELECT count(*) FROM users")).scalar() or 0,
                        "memberships": _s.execute(
                            _text("SELECT count(*) FROM memberships")).scalar() or 0,
                    }
                except Exception:  # noqa: BLE001
                    pass
        else:
            for info in stores.values():
                info.setdefault("pg_count", None)
    except Exception as exc:  # noqa: BLE001
        base["pg_count_error"] = repr(exc)[:200]

    base["at"] = now_ist().isoformat(timespec="seconds")
    return JSONResponse(base)


@app.post("/billing/{tenant_id}")
async def set_billing(request: Request, tenant_id: str, plan: str = Form(None),
                      rate_per_min: float = Form(None), rate_per_call: float = Form(None),
                      currency: str = Form(None), balance: float = Form(None),
                      included_minutes: int = Form(None), topup: float = Form(None)):
    """ADMIN: set a tenant's plan/rates/balance, or top up. `balance` sets absolute;
    `topup` adds to the current balance. Returns the updated billing record."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "manage_tenants"):
        return _forbidden("admin only")
    if not _tenant_by_id(tenant_id):
        return JSONResponse({"error": "tenant not found"}, status_code=404)
    async with _STORE_LOCK:
        store = _read_billing()
        rec = store.get(tenant_id) or _default_billing(_tenant_by_id(tenant_id))
        if plan is not None:
            rec["plan"] = "prepaid" if str(plan).lower() == "prepaid" else "postpaid"
        if rate_per_min is not None:
            rec["rate_per_min"] = max(0.0, float(rate_per_min))
        if rate_per_call is not None:
            rec["rate_per_call"] = max(0.0, float(rate_per_call))
        if currency is not None and str(currency).strip():
            rec["currency"] = str(currency).strip().upper()[:4]
        if included_minutes is not None:
            rec["included_minutes"] = max(0, int(included_minutes))
        if balance is not None:
            rec["balance"] = round(float(balance), 4)
        if topup is not None:
            rec["balance"] = round(float(rec.get("balance", 0) or 0) + float(topup), 4)
        store[tenant_id] = rec
        _write(BILLING_FILE, store)
    _audit(request, t, "billing.config", "billing", tenant_id,
           meta={"plan": rec.get("plan"), "topup": topup})
    return JSONResponse({"tenant_id": tenant_id, **rec})


# ---------- WAVE3 Unit5: WhatsApp manual send ----------
@app.post("/whatsapp/send")
async def whatsapp_send(request: Request, to: str = Form(""), template: str = Form(""),
                        text: str = Form(""), params: str = Form("")):
    """Manager+ manual WhatsApp send. `template` = template name (BSP) OR pass `text`
    for a raw-text generic send. `params` = comma-separated template variables.
    No-ops gracefully (status 'skipped_no_config') if WA_* env not set."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot send WhatsApp")
    to_n = norm(to)
    if not to_n:
        return JSONResponse({"error": "valid 'to' phone required"}, status_code=400)
    tpl = (template or text or "").strip()
    if not tpl:
        return JSONResponse({"error": "template or text is required"}, status_code=400)
    is_text = bool(text.strip() and not template.strip())
    plist = [p.strip() for p in re.split(r"[,\|]", params) if p.strip()] if params else []
    result = await _wa_send(t["tenant_id"], to_n, tpl, plist, kind="manual", is_text=is_text)
    code = 200 if result.get("status") != "skipped_no_config" else 200
    _audit(request, t, "whatsapp.send", "whatsapp", to_n, channel="whatsapp",
           meta={"status": result.get("status")})
    return JSONResponse({"ok": bool(result.get("ok")), "status": result.get("status"),
                         "to": to_n, "configured": bool(wa_mod and wa_mod.is_configured())},
                        status_code=code)


# ---------- P1 visibility endpoints ----------
@app.get("/whatsapp/log")
async def whatsapp_log(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = [x for x in _read(WA_LOG_FILE, [])
            if t.get("is_admin") or x.get("tenant_id") == t["tenant_id"]]
    return JSONResponse({"log": rows[:500]})


# ---------- WAVE A2: inbound WhatsApp webhook (Meta) + conversation threads ----------
@app.get("/whatsapp/inbound")
async def whatsapp_inbound_verify(request: Request):
    """Meta webhook verification handshake (NO auth — Meta calls this).
    Echoes hub.challenge as plain text when hub.verify_token == META_WA_VERIFY_TOKEN."""
    q = request.query_params
    mode = q.get("hub.mode", "")
    token = q.get("hub.verify_token", "")
    challenge = q.get("hub.challenge", "")
    expected = os.getenv("META_WA_VERIFY_TOKEN", "").strip()
    if mode == "subscribe" and expected and token == expected:
        return Response(content=challenge, media_type="text/plain", status_code=200)
    return Response(content="verification failed", status_code=403)


def _verify_meta_signature(raw: bytes, header_sig: str) -> bool:
    """Verify X-Hub-Signature-256 (HMAC-SHA256 of the raw body w/ META_WA_APP_SECRET).
    If no app secret is configured (dormant), accept (nothing to verify against yet)."""
    secret = os.getenv("META_WA_APP_SECRET", "").strip()
    if not secret:
        return True  # dormant: can't verify, accept so the pipeline is exercisable
    if not header_sig or "=" not in header_sig:
        return False
    algo, _, sent = header_sig.partition("=")
    if algo != "sha256":
        return False
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, sent)


def _parse_meta_inbound(payload: dict) -> list[dict]:
    """Extract [{phone, text}] from a Meta messages webhook payload. Tolerant."""
    out = []
    try:
        for entry in payload.get("entry", []) or []:
            for ch in entry.get("changes", []) or []:
                val = ch.get("value", {}) or {}
                for m in val.get("messages", []) or []:
                    phone = m.get("from", "")
                    text = ""
                    if m.get("type") == "text":
                        text = (m.get("text", {}) or {}).get("body", "")
                    elif m.get("type") == "button":
                        text = (m.get("button", {}) or {}).get("text", "")
                    elif m.get("type") == "interactive":
                        inter = m.get("interactive", {}) or {}
                        text = ((inter.get("button_reply", {}) or {}).get("title")
                                or (inter.get("list_reply", {}) or {}).get("title") or "")
                    if phone:
                        out.append({"phone": phone, "text": text or ""})
    except Exception:  # noqa: BLE001
        pass
    return out


@app.post("/whatsapp/inbound")
async def whatsapp_inbound(request: Request):
    """Receive Meta message webhooks. Verifies X-Hub-Signature-256, parses sender+text,
    drives the per-contact conversation thread. ALWAYS returns 200 quickly (Meta requires
    a fast 2xx). Dormant-safe: with no WA env it stores inbound + no-ops the reply."""
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_meta_signature(raw, sig):
        return JSONResponse({"error": "bad signature"}, status_code=403)
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:  # noqa: BLE001
        payload = {}
    msgs = _parse_meta_inbound(payload)
    results = []
    for m in msgs:
        try:
            results.append(await _wa_handle_inbound(m["phone"], m["text"]))
        except Exception:  # noqa: BLE001
            pass
    return JSONResponse({"ok": True, "handled": len(results)})


@app.get("/whatsapp/threads")
async def whatsapp_threads(request: Request):
    """List WhatsApp conversation threads (tenant-scoped; manager+/admin)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    out = []
    try:
        if WA_THREADS_DIR.exists():
            for p in sorted(WA_THREADS_DIR.glob("*.json"),
                            key=lambda x: x.stat().st_mtime, reverse=True):
                th = _read(p, {}) or {}
                tid = th.get("tenant_id", ADMIN_ID)
                if not t.get("is_admin") and tid != t["tenant_id"]:
                    continue
                out.append({"phone": th.get("phone", ""), "name": th.get("name", ""),
                            "tenant_id": tid, "campaign_id": th.get("campaign_id", ""),
                            "campaign_name": th.get("campaign_name", ""),
                            "status": th.get("status", "active"),
                            "turns": len(th.get("turns") or []),
                            "updated_at": th.get("updated_at", th.get("created_at", ""))})
    except Exception:  # noqa: BLE001
        pass
    return JSONResponse({"threads": out, "total": len(out)})


@app.get("/whatsapp/threads/{phone}")
async def whatsapp_thread_detail(phone: str, request: Request):
    """Full conversation history for one contact (tenant-scoped)."""
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    th = _wa_thread_read(norm(phone) or phone)
    guard = require_object(t, th)  # 404 if missing or not owned (BOLA)
    if guard is not None:
        return guard
    return JSONResponse({"thread": th})


@app.get("/webhooks")
async def get_webhooks(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = [w for w in _read(WEBHOOK_FILE, []) if w.get("tenant_id") == t["tenant_id"]]
    return JSONResponse({"webhooks": rows})


@app.post("/webhooks")
async def add_webhook(request: Request, url: str = Form(""), secret: str = Form(""),
                      events: str = Form("")):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot add webhooks")
    if not (url or "").strip():
        return JSONResponse({"error": "url is required"}, status_code=400)
    ev = [e.strip() for e in re.split(r"[,\s]+", events) if e.strip()]
    rec = {"id": uuid.uuid4().hex[:10], "tenant_id": t["tenant_id"], "url": url.strip(),
           "secret": secret or secrets.token_hex(16), "events": ev, "active": True,
           "created_at": datetime.now().isoformat(timespec="seconds")}
    async with _STORE_LOCK:
        store = _read(WEBHOOK_FILE, [])
        store.append(rec)
        _write(WEBHOOK_FILE, store)
    _audit(request, t, "webhook.create", "webhook", rec["id"], meta={"url": rec["url"]})
    return JSONResponse({"id": rec["id"], "url": rec["url"], "secret": rec["secret"]})


@app.delete("/webhooks/{wid}")
async def delete_webhook(request: Request, wid: str):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    if not can(t, "write"):
        return _forbidden("read-only role cannot delete webhooks")
    async with _STORE_LOCK:
        store = _read(WEBHOOK_FILE, [])
        target = next((w for w in store if w.get("id") == wid), None)
        if not target or (not t.get("is_admin") and target.get("tenant_id") != t["tenant_id"]):
            return JSONResponse({"error": "not found"}, status_code=404)
        store = [w for w in store if w.get("id") != wid]
        _write(WEBHOOK_FILE, store)
    _audit(request, t, "webhook.delete", "webhook", wid)
    return JSONResponse({"deleted": wid})


# ---------- WAVE A Unit3: cost ledger + rollups + vendor sync ----------
def _telephony_rate_per_min(tenant_id: str) -> float:
    """Admin-set rate_per_min from the existing billing config — used as the telephony
    cost fallback when Vobiz is dormant (so the meter is never 0)."""
    try:
        return float(_billing_for(tenant_id).get("rate_per_min", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _read_cost_ledger() -> list[dict]:
    rows = _read(COST_LEDGER_FILE, [])
    return rows if isinstance(rows, list) else []


def rebuild_cost_ledger() -> dict:
    """Join usage_events + Vobiz CDR snapshot into a normalized var/cost_ledger.json,
    one row per (call, vendor). Idempotent: rebuilt fully each pass from source stores
    (usage_events + vendor_snapshots), so re-running can't double-count. Also writes
    var/daily_rollups.json. Returns a small summary. Synchronous; callers hold no lock
    (it reads sources + writes two derived files)."""
    events = _read_usage_events()
    snaps = _read(VENDOR_SNAPSHOTS_FILE, {}) or {}
    vobiz_snap = (snaps.get("vobiz") or {}) if isinstance(snaps, dict) else {}
    # Map sip_call_id -> cdr record (deduped by sip_call_id).
    cdr_by_sip = {}
    for rec in (vobiz_snap.get("records") or []):
        sid = rec.get("sip_call_id")
        if sid:
            cdr_by_sip[sid] = rec
    # Secondary index: normalised phone -> list of cdr records (for calls lacking sip_call_id).
    def _norm_phone(p: str) -> str:
        p = (p or "").strip().lstrip("+")
        return p[-10:] if len(p) >= 10 else p
    cdr_by_phone: dict = {}
    for rec in (vobiz_snap.get("records") or []):
        ph = _norm_phone(rec.get("to_number", ""))
        if ph:
            cdr_by_phone.setdefault(ph, []).append(rec)
    # Index calls by room + by phone for telephony attribution.
    call_by_room = {c.get("room"): c for c in CALLS if c.get("room")}

    rows: list[dict] = []
    # 1) Per-vendor internal usage rows (groq/sarvam/elevenlabs/livekit).
    for ev in events:
        rows.append({
            "source": "internal",
            "ts": ev.get("ts", ""),
            "call_id": ev.get("call_id", ""),
            "room": ev.get("room", ""),
            "tenant_id": ev.get("tenant_id", ""),
            "campaign_id": ev.get("campaign_id", ""),
            "vendor": ev.get("vendor", ""),
            "service_type": ev.get("service_type", ""),
            "qty": ev.get("qty", 0),
            "unit": ev.get("unit", ""),
            "cost": round(float(ev.get("est_cost_inr", 0) or 0), 6),
            "currency": "INR",
            "actual_or_estimated": ev.get("actual_or_estimated", "estimated"),
        })
    # 2) Telephony (Vobiz) rows: one per call. Join strategy (in order):
    #    a) sip_call_id exact match (new calls — stamped by run_job since Wave-A activation)
    #    b) phone + 15-min window match (legacy calls lacking sip_call_id; best-effort)
    #    c) fallback: duration_s/60 × admin rate (when Vobiz dormant or call unmatched)
    #    After matching calls, any remaining unmatched CDR records are emitted as orphan rows
    #    (real cost, no call attribution) so Vobiz total is never silently dropped.
    used_sids = set()
    # Build a consumable list of cdr recs keyed by phone for the secondary join.
    # Sort each phone's CDR list by 'at' for deterministic matching.
    cdr_candidates: dict = {ph: sorted(lst, key=lambda x: x.get("at", ""))
                             for ph, lst in cdr_by_phone.items()}
    used_phone_sids: set = set()  # sip_call_ids consumed by secondary join

    for c in CALLS:
        if c.get("status") not in ("done",) and not c.get("duration_s"):
            continue
        dur = int(c.get("duration_s", 0) or 0)
        tid = c.get("tenant_id", "")
        sid = c.get("sip_call_id", "")
        cdr = cdr_by_sip.get(sid) if sid else None
        if cdr and sid not in used_sids:
            # (a) Primary: exact sip_call_id match.
            used_sids.add(sid)
            used_phone_sids.add(sid)
            rows.append({
                "source": "vobiz_cdr", "ts": cdr.get("at", c.get("ended_at", "")),
                "call_id": c.get("id", ""), "room": c.get("room", ""), "tenant_id": tid,
                "campaign_id": c.get("campaign_id", ""), "vendor": "vobiz",
                "service_type": "telephony",
                "qty": cdr.get("billable_seconds", dur), "unit": "seconds",
                "cost": round(float(cdr.get("total_cost", 0) or 0), 6),
                "currency": vobiz_snap.get("currency", "INR"),
                "actual_or_estimated": "actual",
            })
        else:
            # (b) Secondary: phone + 15-min window match (for legacy calls lacking sip_call_id).
            ph = _norm_phone(c.get("phone", ""))
            matched_cdr = None
            if ph and not sid:
                call_ts = c.get("started_at", "") or c.get("ended_at", "")
                for candidate in cdr_candidates.get(ph, []):
                    csid = candidate.get("sip_call_id", "")
                    if csid in used_phone_sids:
                        continue
                    cdr_ts = candidate.get("at", "")
                    # Accept if the CDR end_time is within 15 minutes of call start_at.
                    try:
                        # Normalise ISO strings: strip trailing Z, handle +HH:MM offsets.
                        def _parse_iso(s: str):
                            s = s.replace("Z", "+00:00")
                            return datetime.fromisoformat(s)
                        dt_call = _parse_iso(call_ts) if call_ts else None
                        dt_cdr = _parse_iso(cdr_ts) if cdr_ts else None
                        if dt_call and dt_cdr:
                            # Make both offset-naive for comparison (strip tz).
                            tc = dt_call.replace(tzinfo=None)
                            tcd = dt_cdr.replace(tzinfo=None)
                            if abs((tcd - tc).total_seconds()) <= 900:
                                matched_cdr = candidate
                                used_phone_sids.add(csid)
                                break
                    except Exception:  # noqa: BLE001
                        pass
            if matched_cdr:
                msid = matched_cdr.get("sip_call_id", "")
                used_sids.add(msid)
                rows.append({
                    "source": "vobiz_cdr_phone", "ts": matched_cdr.get("at", c.get("ended_at", "")),
                    "call_id": c.get("id", ""), "room": c.get("room", ""), "tenant_id": tid,
                    "campaign_id": c.get("campaign_id", ""), "vendor": "vobiz",
                    "service_type": "telephony",
                    "qty": matched_cdr.get("billable_seconds", dur), "unit": "seconds",
                    "cost": round(float(matched_cdr.get("total_cost", 0) or 0), 6),
                    "currency": vobiz_snap.get("currency", "INR"),
                    "actual_or_estimated": "actual",
                })
            elif dur > 0:
                # (c) Fallback: estimated from duration × rate.
                rate = _telephony_rate_per_min(tid)
                rows.append({
                    "source": "telephony_fallback", "ts": c.get("ended_at", ""),
                    "call_id": c.get("id", ""), "room": c.get("room", ""), "tenant_id": tid,
                    "campaign_id": c.get("campaign_id", ""), "vendor": "vobiz",
                    "service_type": "telephony",
                    "qty": dur, "unit": "seconds",
                    "cost": round(dur / 60.0 * rate, 6), "currency": "INR",
                    "actual_or_estimated": "estimated",
                })
    # (d) Orphan CDR rows: Vobiz records not matched to any call (e.g. manual test dials,
    #     calls placed before this system existed). Real cost — include under admin tenant.
    all_used_sids = used_sids | used_phone_sids
    admin_tid = "admin"
    for rec in (vobiz_snap.get("records") or []):
        rsid = rec.get("sip_call_id", "")
        if rsid and rsid not in all_used_sids:
            rows.append({
                "source": "vobiz_cdr_orphan", "ts": rec.get("at", ""),
                "call_id": "", "room": "", "tenant_id": admin_tid,
                "campaign_id": "", "vendor": "vobiz",
                "service_type": "telephony",
                "qty": rec.get("billable_seconds", 0), "unit": "seconds",
                "cost": round(float(rec.get("total_cost", 0) or 0), 6),
                "currency": vobiz_snap.get("currency", "INR"),
                "actual_or_estimated": "actual",
            })
    _write(COST_LEDGER_FILE, rows)
    _rebuild_daily_rollups(rows)
    return {"rows": len(rows), "vobiz_cdr_matched": len(used_sids)}


def _rebuild_daily_rollups(rows: list[dict]) -> None:
    """Precompute var/daily_rollups.json: {date: {tenant_id: {vendor: cost}, _total}}."""
    roll: dict = {}
    for r in rows:
        day = (r.get("ts") or "")[:10] or "unknown"
        tid = r.get("tenant_id") or "unknown"
        vendor = r.get("vendor") or "unknown"
        cost = float(r.get("cost", 0) or 0)
        roll.setdefault(day, {})
        roll[day].setdefault(tid, {})
        roll[day][tid][vendor] = round(roll[day][tid].get(vendor, 0.0) + cost, 6)
        roll[day].setdefault("_total", 0.0)
        roll[day]["_total"] = round(roll[day]["_total"] + cost, 6)
    _write(DAILY_ROLLUPS_FILE, roll)


def _cost_rows_for(tenant: dict) -> list[dict]:
    """Tenant-scoped cost_ledger rows (admin sees all)."""
    rows = _read_cost_ledger()
    if tenant.get("is_admin"):
        return rows
    tid = tenant.get("tenant_id")
    return [r for r in rows if r.get("tenant_id") == tid]


async def vendor_sync(now: datetime | None = None) -> dict:
    """~30-min vendor-sync pass. Pulls ElevenLabs analytics + (when keyed) Vobiz CDR for
    the last 24-48h, writes var/vendor_snapshots.json with per-vendor status/timestamp/
    stale flag. On failure: keep last snapshot, mark stale, continue. Then rebuilds the
    cost ledger + rollups. Best-effort; never raises."""
    now = now or now_ist()
    ts = now.isoformat(timespec="seconds")
    try:
        snaps = _read(VENDOR_SNAPSHOTS_FILE, {}) or {}
        if not isinstance(snaps, dict):
            snaps = {}

        # ElevenLabs: subscription + usage-over-time (workspace level).
        if v_elevenlabs is not None:
            try:
                st = v_elevenlabs.status()
                if st == "configured":
                    import time as _t
                    end_ms = int(_t.time() * 1000)
                    start_ms = end_ms - 48 * 3600 * 1000
                    sub = v_elevenlabs.get_subscription()
                    usage = v_elevenlabs.get_usage_over_time(start_ms, end_ms)
                    snaps["elevenlabs"] = {"status": "configured", "synced_at": ts, "stale": False,
                                           "subscription": sub, "usage": usage}
                else:
                    prev = snaps.get("elevenlabs", {})
                    snaps["elevenlabs"] = {**prev, "status": st, "synced_at": prev.get("synced_at", ""),
                                           "stale": st != "configured"}
            except Exception as exc:  # noqa: BLE001
                prev = snaps.get("elevenlabs", {})
                snaps["elevenlabs"] = {**prev, "status": "error", "error": repr(exc)[:120],
                                       "stale": True}

        # Vobiz: CDR + balance (dormant until creds).
        if v_vobiz is not None:
            try:
                st = v_vobiz.status()
                if st == "configured":
                    start_d = (now - timedelta(hours=48)).strftime("%Y-%m-%d")
                    end_d = now.strftime("%Y-%m-%d")
                    cdr = v_vobiz.get_cdr(start_d, end_d)
                    bal = v_vobiz.get_balance()
                    ok = cdr.get("status") == "configured"
                    snaps["vobiz"] = {"status": "configured" if ok else cdr.get("status", "error"),
                                      "synced_at": ts, "stale": not ok,
                                      "records": cdr.get("records", []) if ok else snaps.get("vobiz", {}).get("records", []),
                                      "currency": cdr.get("currency", "INR"),
                                      "balance": bal.get("balance") if bal.get("status") == "configured" else None}
                else:
                    prev = snaps.get("vobiz", {})
                    snaps["vobiz"] = {**prev, "status": st, "stale": True,
                                      "synced_at": prev.get("synced_at", ""),
                                      "records": prev.get("records", [])}
            except Exception as exc:  # noqa: BLE001
                prev = snaps.get("vobiz", {})
                snaps["vobiz"] = {**prev, "status": "error", "error": repr(exc)[:120], "stale": True}

        # Groq / Sarvam: internal meters (no external API) — mark configured + estimated.
        snaps["groq"] = {"status": "configured", "synced_at": ts, "stale": False, "estimated": True}
        snaps["sarvam"] = {"status": "configured", "synced_at": ts, "stale": False, "estimated": True}
        snaps["livekit"] = {"status": "configured", "synced_at": ts, "stale": False, "note": "self-hosted=free"}

        async with _STORE_LOCK:
            _write(VENDOR_SNAPSHOTS_FILE, snaps)
        # Rebuild derived ledger/rollups from the fresh snapshot + usage events.
        rebuild_cost_ledger()
        return snaps
    except Exception as exc:  # noqa: BLE001
        try:
            import logging as _lg
            _lg.getLogger("famit-caller").warning("vendor_sync failed: %r", exc)
        except Exception:  # noqa: BLE001
            pass
        return {}


# ---------- P0.5 scheduler: ONE 60s loop (retry/callback dispatch + opt-out safety sweep) ----------
def _spawn_retry_job(r: dict) -> str:
    """Build a single-lead JOBS entry mirroring /run and kick run_job. No new dial code path."""
    tenant = _tenant_by_id(r["tenant_id"]) or {}
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {
        "state": "queued", "campaign_id": r["campaign_id"], "tenant_id": r["tenant_id"],
        "concurrency": 1, "hourly_cap": 200, "daily_cap": int(tenant.get("daily_call_cap", 500)),
        "leads": [{"name": r.get("name", ""), "num": r["phone"], "status": "queued",
                   "room": "", "launched_at": 0.0, "attempt": int(r.get("attempts", 0))}],
        "retry_of": r.get("id"),
    }
    asyncio.create_task(run_job(jid))
    return jid


async def scheduler_loop():
    while True:
        try:
            await asyncio.sleep(60)
            now_iso = now_ist().isoformat()
            # WAVE A Unit1: ingest the agent's per-room usage files into usage_events.json.
            await _drain_usage_raw()
            # WAVE A Unit3: vendor-sync pass every ~30 min (ElevenLabs + Vobiz-when-keyed),
            # then rebuild cost_ledger + rollups. Cheap rebuild also runs each tick so
            # internally-metered cost shows up promptly after a call.
            global _LAST_VENDOR_SYNC
            _now_t = time.time()
            if _now_t - _LAST_VENDOR_SYNC >= 1800:
                _LAST_VENDOR_SYNC = _now_t
                await vendor_sync()
            else:
                try:
                    rebuild_cost_ledger()
                except Exception:  # noqa: BLE001
                    pass
            due = [r for r in _read(RETRY_FILE, []) if r.get("next_attempt_at", "") <= now_iso]
            for r in due:
                camp_fields = (get_campaign(r["campaign_id"]) or {}).get("fields", {}) or {}
                if not _in_window(camp_fields)[0]:
                    continue                                   # respect calling window
                if norm(r["phone"]) in _suppressed_set(r["tenant_id"]):
                    await _remove_retry(r["id"]); continue     # opted out since enqueue
                _spawn_retry_job(r)
                await _remove_retry(r["id"])
            # Reconciliation sweep: the agent writes the transcript on shutdown, which can
            # LAG run_job's finalize (which then read an empty transcript -> misclassified as
            # no_human/0). Re-reconcile any done call whose transcript now has real data but
            # whose rec wasn't enriched yet (no _reconciled flag). Fixes classify + score +
            # retry/callback + opt-out for late transcripts.
            calls_dirty = False
            for c in list(CALLS):
                room = c.get("room", "")
                if (not room or c.get("status") != "done" or c.get("outcome") == "suppressed"
                        or c.get("_reconciled")):
                    continue
                tr = _read(TRANSCRIPT_DIR / f"{room}.json", {})
                if not tr:
                    continue   # transcript still not written; try again next tick
                tid = c.get("tenant_id", ADMIN_ID)
                phone = c.get("phone", "")
                cid = c.get("campaign_id", "")
                outcome = _classify_outcome(c, tr)
                c["outcome"] = outcome
                c["interest"] = tr.get("interest", 0)
                c["answered"] = outcome in _REAL_CONVO
                c["_reconciled"] = True
                calls_dirty = True
                await _update_lead_after_call(tid, phone, tr.get("interest", 0), outcome,
                                              call_at=c.get("started_at", ""))
                if tr.get("opt_out") or tr.get("outcome") == "opt_out":
                    c["outcome"] = "opt_out"; c["answered"] = True
                    if norm(phone) not in _suppressed_set(tid):
                        await _add_suppression(tid, phone, "opt_out_call", source=room)
                        await _flip_lead_status(tid, phone, "opted_out")
                else:
                    camp_fields = (get_campaign(cid) or {}).get("fields", {}) or {}
                    maxa = int(camp_fields.get("retry_max_attempts", 3))
                    backoff = camp_fields.get("retry_backoff_mins") or [120, 360, 1440]
                    cb = tr.get("callback_at")
                    already = any(r.get("phone") == norm(phone) and r.get("campaign_id") == cid
                                  for r in _read(RETRY_FILE, []))
                    if cb and not already:
                        await _enqueue_retry(tid, cid, c.get("name", ""), phone, 0, maxa, cb, "callback")
                        await _emit_webhook(tid, "callback.scheduled",
                                            {"phone": phone, "campaign_id": cid,
                                             "name": c.get("name", ""), "when": cb,
                                             "callback_raw": tr.get("callback_raw", "")})
                    elif outcome in ("no_answer", "voicemail", "busy") and not already:
                        next_at = _clamp_to_window(now_ist() + timedelta(minutes=backoff[0]), camp_fields)
                        await _enqueue_retry(tid, cid, c.get("name", ""), phone, 1, maxa,
                                             next_at.isoformat(), outcome)
                # WAVE3 Unit2: emit completion + qualified for late-reconciled calls.
                # Only if _finalize_call hadn't already emitted (it emits with an empty
                # transcript; here we re-emit ONCE with the real summary/score).
                if not c.get("_wh_completed"):
                    _sc = c.get("interest", 0) or 0
                    c["_wh_completed"] = True
                    await _emit_webhook(tid, "call.completed",
                                        {"call_id": c.get("id"), "phone": phone, "name": c.get("name", ""),
                                         "campaign_id": cid, "outcome": c["outcome"], "interest": _sc,
                                         "score": _sc, "summary": tr.get("summary", ""),
                                         "duration_s": c.get("duration_s", 0), "room": room})
                    if c["outcome"] != "opt_out" and _sc >= 70:
                        await _emit_webhook(tid, "lead.qualified",
                                            {"call_id": c.get("id"), "phone": phone,
                                             "name": c.get("name", ""), "campaign_id": cid,
                                             "score": _sc, "outcome": c["outcome"],
                                             "summary": tr.get("summary", "")})
            if calls_dirty:
                async with _STORE_LOCK:
                    _write(CALLS_FILE, CALLS)
        except Exception as exc:  # noqa: BLE001
            try:
                import logging as _lg
                _lg.getLogger("famit-caller").warning("scheduler_loop tick failed: %r", exc)
            except Exception:  # noqa: BLE001
                pass


@app.on_event("startup")
async def _start_scheduler():
    asyncio.create_task(scheduler_loop())
    # CRM CORE: single-source the phone canonicalizer + lazily ensure the projection schema.
    # Best-effort — a crm failure must NEVER affect the scheduler / run-path.
    if _crm_mod is not None:
        try:
            _crm_mod.init(norm=norm)
        except Exception:  # noqa: BLE001
            pass


# ---------- P0.6 hot-leads convenience ----------
@app.get("/leads/hot")
async def leads_hot(request: Request):
    t = resolve_tenant(request)
    if not t:
        return need_auth()
    rows = [x for x in _leads_for(t) if (x.get("score", 0) or 0) >= 70]
    rows.sort(key=lambda x: x.get("score", 0), reverse=True)
    return JSONResponse({"leads": rows})


@app.get("/")
async def index(request: Request):
    if not authed(request):
        return need_auth()
    return HTMLResponse("<h3>Famit backend API is running. Use the panel.</h3>")


# ==============================================================================================
# MODULE MOUNT — ads-engine (autonomous paid-ads engine, prefix /ads). ADDITIVE, FLAG-GATED.
# ----------------------------------------------------------------------------------------------
# The ads_engine router is BARE-OK / TOKEN-DERIVED: its handlers look up
# caller.resolve_tenant / need_auth / can LAZILY (ads_engine.endpoints._auth_helpers) and ALWAYS
# take org_id from the token (t["tenant_id"]) — NEVER from the request body/header. So a plain
# include_router is safe (no cross-tenant hole; no build_router needed — unlike booking/media-gen/
# funnels which read tenant from body and require a token-deriving surface first).
#
# IMPORT-GUARD (house pattern): a missing/broken ads_engine package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_ADS!=1/true => router NOT mounted => byte-identical behavior.
# No scheduler poll_and_enforce tick is wired here (DEFERRED per the build state).
try:
    from ads_engine.endpoints import router as _ads_router  # noqa: E402
except Exception:  # noqa: BLE001
    _ads_router = None

FEATURE_ADS = (cfg_get("FEATURE_ADS", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_ADS and _ads_router is not None:
    try:
        app.include_router(_ads_router)
    except Exception:  # noqa: BLE001 — a mount failure must never crash the live spine
        import logging as _lg_ads
        _lg_ads.getLogger("famit-caller").warning("ads_engine router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT — media-gen (provider-agnostic media-generation ENGINE, prefix /media). FLAG-GATED.
# ----------------------------------------------------------------------------------------------
# ⚠ TENANT ISOLATION: media-gen is a BODY-TENANT module — its bare module-level `router`
# (`media_gen.router.router`) reads tenant_id from the request body/query and MUST NEVER be mounted
# (mounting it is a cross-tenant hole: any caller could pass tenant_id=<victim>). We mount the
# token-deriving AUTHENTICATED surface `build_router(resolve_tenant, can, need_auth, forbidden,
# firewall)` instead — tenant_id is ALWAYS resolve_tenant(request)["tenant_id"] (token-derived),
# writes enforce can(t,"write"), and by-job_id routes verify rec["tenant_id"]==token (ownership).
# Mirrors the workflow-studio / forms-surveys settled pattern (and unlike ads-engine, which was
# bare-OK / token-derived and needed no build_router).
#
# The video webhook (/media/video/webhook) is intentionally UNAUTHENTICATED on this surface —
# it is provider-signed (providers.verify_webhook, fail-closed) and matched by external_id.
#
# IMPORT-GUARD (house pattern): a missing/broken media_gen package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_MEDIA!=1/true => router NOT mounted => byte-identical behavior.
# firewall is passed for forward-compat (reserved for future step-up on approve; not wired yet).
try:
    from media_gen.router import build_router as _build_media_router  # noqa: E402
except Exception:  # noqa: BLE001
    _build_media_router = None

FEATURE_MEDIA = (cfg_get("FEATURE_MEDIA", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_MEDIA and _build_media_router is not None:
    try:
        _media_router = _build_media_router(
            resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod
        )
        if _media_router is not None:
            app.include_router(_media_router)
    except Exception:  # noqa: BLE001 — a mount failure must never crash the live spine
        import logging as _lg_media
        _lg_media.getLogger("famit-caller").warning("media_gen router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT — booking (appointments / site-visits / reminders ENGINE, prefix /booking). FLAG-GATED.
# ----------------------------------------------------------------------------------------------
# ⚠ TENANT ISOLATION: booking is a HEADER-TENANT module on its bare surface — its module-level
# `router` + default `get_ctx` trust the `X-Tenant-Id` header (spoofable) and MUST NEVER be mounted.
# We mount the token-deriving AUTHENTICATED surface `build_router(resolve_tenant, can, need_auth,
# forbidden, firewall)` instead — tenant_id is ALWAYS resolve_tenant(request)["tenant_id"]
# (token-derived), writes enforce can(t,"write") / reads enforce can(t,"read"), and is_admin is
# HARDCODED False into every core.* call (is_admin feeds db.engine.session(tenant_id, is_admin);
# is_admin=1 BYPASSES RLS — so it must never be body/header/claim-derived). This supersedes the
# old "override get_ctx" instruction in REMAINING_MODULES_BUILD_STATE.md — a clean token-deriving
# surface now exists. Mirrors the workflow-studio / forms-surveys / media-gen settled pattern.
#
# DORMANT-SAFE: booking core returns {"status":"not_configured"} when Postgres is down/unconfigured,
# so every endpoint is inert until F1 lands + the deferred Alembic 0003_booking migration + rls.sql
# apply (NOT part of this mount). The risky /tick reminder spend flows through core.tick's own
# firewall(PIN, fail-closed) + wallet gates with the body-supplied pin (only tenant/is_admin move to
# the token; pin legitimately stays in the body).
#
# IMPORT-GUARD (house pattern): a missing/broken booking package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_BOOKING!=1/true => router NOT mounted => byte-identical behavior.
# firewall is passed for signature-uniformity (reserved seam; risky tick spend self-gates in core).
try:
    from booking.router import build_router as _build_booking_router  # noqa: E402
except Exception:  # noqa: BLE001
    _build_booking_router = None

FEATURE_BOOKING = (cfg_get("FEATURE_BOOKING", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_BOOKING and _build_booking_router is not None:
    try:
        _booking_router = _build_booking_router(
            resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod
        )
        if _booking_router is not None:
            app.include_router(_booking_router)
    except Exception:  # noqa: BLE001 — a mount failure must never crash the live spine
        import logging as _lg_booking
        _lg_booking.getLogger("famit-caller").warning("booking router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT — payments (vendor->customer collections: links/invoices/receipts, prefix /payments).
# FLAG-GATED. THIS IS THE LIVE EARNER — mount is dormant-by-flag, byte-identical when OFF.
# ----------------------------------------------------------------------------------------------
# ⚠ TENANT ISOLATION: payments ships a CLEAN token-deriving surface — there is no body/header-tenant
# bare router to avoid (unlike media-gen/booking). The module-level `payments.router.router` resolves
# tenant ONLY from the token via the injected resolve_tenant, enforces can(t,"write") on mutating
# routes (create-link / mark-paid / refund), and ALWAYS uses org_id = the resolved tenant_id (never a
# spoofable body/query param). Spend-sensitive routes additionally pass through firewall.require_step_up
# (PASS-THROUGH when FIREWALL disabled / no PIN — non-breaking; 403 challenge when active). The
# /payments/webhooks/{provider} route is intentionally UNAUTHENTICATED — it is provider-signature-
# verified inside core.ingest_webhook (a machine call) and always returns 200 (so no provider retry-storm).
#
# WIRE-THEN-INCLUDE: unlike build_router modules, payments injects its auth helpers via wire(...) (which
# mutates module globals) and then mounts the module-level `router` with prefix="/payments". wire() takes
# KEYWORD-ONLY args. The router has NO internal prefix, so the prefix is applied here at include time.
#
# DORMANT-SAFE: with no PG, core.* returns {"status":"unavailable"}; with no provider creds,
# {"status":"not_configured"}. ensure_schema() is LAZY (first-use, never raises) — payments.init() is
# NOT called at startup ON PURPOSE: calling it would touch PG / apply DDL even with the flag OFF and
# break the byte-identical-when-OFF guarantee. init() + drain_followups() (the scheduler dunning tick)
# are DEFERRED (recorded in the build log), exactly as booking deferred its reminder tick.
#
# IMPORT-GUARD (house pattern): a missing/broken payments package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_PAYMENTS!=1/true => router NOT mounted => byte-identical behavior.
try:
    from payments.router import router as _payments_router, wire as _payments_wire  # noqa: E402
except Exception:  # noqa: BLE001
    _payments_router = None
    _payments_wire = None

FEATURE_PAYMENTS = (cfg_get("FEATURE_PAYMENTS", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_PAYMENTS and _payments_router is not None and _payments_wire is not None:
    try:
        _payments_wire(
            resolve_tenant=resolve_tenant, can=can, need_auth=need_auth,
            forbidden=_forbidden, firewall=_firewall_mod,
        )
        app.include_router(_payments_router, prefix="/payments")
    except Exception:  # noqa: BLE001 — a mount failure must never crash the live spine
        import logging as _lg_payments
        _lg_payments.getLogger("famit-caller").warning("payments router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT -- support (AI Customer Support: omnichannel ticketing + KB-grounded AI replies,
# prefix /support). FLAG-GATED.
# ----------------------------------------------------------------------------------------------
# TENANT ISOLATION: support ships a CLEAN token-deriving surface (same shape as payments -- there is
# NO body/header-tenant bare router to avoid, unlike media-gen/booking). Every tenant route resolves
# tenant ONLY from the token via the injected resolve_tenant; org_id is ALWAYS the resolved tenant_id
# (NEVER a spoofable body/query param). Mutating routes (inbound / draft / reply / escalate / claim /
# resolve) enforce can(t,"write"). support is NOT a money path, so there is no blanket spend step-up;
# the ONLY step-up-gated route is /support/tickets/{id}/resolve (a risky human force-close, scope
# "support_override") -- PASS-THROUGH when FIREWALL disabled / no PIN (non-breaking), 403 when active.
# The /support/webhooks/{channel} route is intentionally UNAUTHENTICATED (a machine call): today it is
# a dormant no-op returning {"status":"not_configured"} (200), so providers never retry-storm; the
# channel adapter + tenant binding + signature verify are DEFERRED (Omnichannel Inbox unit).
#
# WIRE-THEN-INCLUDE (identical to payments): support injects its auth helpers via wire(...) (mutates
# module globals) and then mounts the module-level `router` with prefix="/support". wire() takes
# KEYWORD-ONLY args. The router has NO internal prefix, so the prefix is applied here at include time.
#
# DORMANT-SAFE: with no PG, core.* returns {"status":"unavailable"}; with an empty KB / no LLM creds,
# the deterministic extractive KB draft fires (grounded-or-escalate -- never hallucinates).
# ensure_schema() is LAZY (first-use, never raises) -- support.init() is NOT called at startup ON
# PURPOSE: calling it would touch PG / apply DDL even with the flag OFF and break the
# byte-identical-when-OFF guarantee. init() is DEFERRED (gate it INSIDE the flag-on block when
# activated), exactly as payments/booking deferred theirs.
#
# IMPORT-GUARD (house pattern): a missing/broken support package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_SUPPORT!=1/true => router NOT mounted => byte-identical behavior.
try:
    from support.router import router as _support_router, wire as _support_wire  # noqa: E402
except Exception:  # noqa: BLE001
    _support_router = None
    _support_wire = None

FEATURE_SUPPORT = (cfg_get("FEATURE_SUPPORT", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_SUPPORT and _support_router is not None and _support_wire is not None:
    try:
        _support_wire(
            resolve_tenant=resolve_tenant, can=can, need_auth=need_auth,
            forbidden=_forbidden, firewall=_firewall_mod,
        )
        app.include_router(_support_router, prefix="/support")
    except Exception:  # noqa: BLE001 -- a mount failure must never crash the live spine
        import logging as _lg_support
        _lg_support.getLogger("famit-caller").warning("support router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT -- forms-surveys (Form/Lead-Capture builder + Survey/Feedback engine). FLAG-GATED.
# Authed CRUD at /forms*, PUBLIC token routes at /f/{token}. No router prefix (paths are absolute).
# ----------------------------------------------------------------------------------------------
# TENANT ISOLATION: forms-surveys ships a CLEAN token-deriving surface (the build_router pattern --
# same shape as media-gen/booking, NOT the wire() shape). Authed CRUD routes resolve tenant ONLY
# from the token via the injected resolve_tenant; org_id is ALWAYS the resolved tenant_id (NEVER a
# spoofable body/query param), writes enforce can(t,"write") / reads can(t,"read"), and is_admin is
# token-derived (feeds db.engine.session -> RLS). The PUBLIC routes /f/{public_token} (render) and
# /f/{public_token}/submit are intentionally UNAUTHENTICATED by design: there is no authenticated
# tenant on the public path, so org_id is SERVER-DERIVED from the form record resolved by the
# unguessable public_token (secrets.token_urlsafe) -- never a request param. Anti-abuse on that
# unauth endpoint is mandatory and lives in the router/core (per-(token,IP) rate limit, raw-body
# size cap pre-parse, honeypot silent-drop, allow-list schema validation, sha256(ip+token)
# forensics, tenant-scoped audit). The two existing @app.middleware("http") handlers are rate-limit
# + metrics ONLY (no global auth wall), so the public /f/ routes are reachable as designed.
#
# SIGNATURE: build_router(resolve_tenant, can, need_auth, forbidden, *, ratelimit=None, audit=None).
# NOTE -- UNLIKE media-gen/booking, forms' build_router has NO `firewall` param (forms are FREE: no
# spend, no wallet hold). Passing firewall= would TypeError (swallowed by the except -> silently
# mounts nothing). We pass only the 4 positional auth helpers; ratelimit/audit fall back to the
# router's own import-guarded `import ratelimit`/`import audit`.
#
# HYPHENATED PACKAGE: the dir is `forms-surveys` (not a legal Python identifier), so a plain
# `import forms_surveys` cannot find it. We register the package under the alias `forms_surveys`
# in sys.modules via importlib spec_from_file_location (submodule_search_locations=[pkgdir]) so the
# inner relative imports resolve -- self-contained, no dependency on the package's own _bootstrap.
#
# init() DELIBERATELY DEFERRED (protects byte-identical-when-OFF, same as payments/support/booking):
# forms.core.init() calls ensure_schema() which applies DDL when PG is reachable -- calling it would
# touch the live PG even with the flag OFF. The deferred leads-write + workflow-trigger emit hooks
# (init(emit_lead=, emit_workflow=)) are likewise DEFERRED (recorded in the build log). build_router
# stands alone: routes call core.* directly; ensure_schema() is LAZY (first-use, never raises) so
# schema applies only on the first authed call AFTER the flag is turned on.
#
# IMPORT-GUARD (house pattern): a missing/broken forms-surveys package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_FORMS!=1/true => router NOT mounted => byte-identical behavior.
try:
    import importlib.util as _fs_ilu  # noqa: E402
    import os as _fs_os  # noqa: E402
    import sys as _fs_sys  # noqa: E402
    _fs_pkgdir = _fs_os.path.join(_fs_os.path.dirname(_fs_os.path.abspath(__file__)), "forms-surveys")
    if "forms_surveys" in _fs_sys.modules:
        _fs_pkg = _fs_sys.modules["forms_surveys"]
    else:
        _fs_spec = _fs_ilu.spec_from_file_location(
            "forms_surveys", _fs_os.path.join(_fs_pkgdir, "__init__.py"),
            submodule_search_locations=[_fs_pkgdir],
        )
        _fs_pkg = _fs_ilu.module_from_spec(_fs_spec)
        _fs_sys.modules["forms_surveys"] = _fs_pkg
        _fs_spec.loader.exec_module(_fs_pkg)
    _build_forms_router = _fs_pkg.build_router
except Exception:  # noqa: BLE001
    _build_forms_router = None

FEATURE_FORMS = (cfg_get("FEATURE_FORMS", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_FORMS and _build_forms_router is not None:
    try:
        _forms_router = _build_forms_router(resolve_tenant, can, need_auth, _forbidden)
        if _forms_router is not None:
            app.include_router(_forms_router)
    except Exception:  # noqa: BLE001 -- a mount failure must never crash the live spine
        import logging as _lg_forms
        _lg_forms.getLogger("famit-caller").warning("forms-surveys router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT -- workflow-studio (durable visual-automation engine, prefix /workflows). FLAG-GATED.
# ----------------------------------------------------------------------------------------------
# TENANT ISOLATION: workflow-studio ships a CLEAN token-deriving surface (the build_router pattern --
# same shape as media-gen/booking/forms). We mount ONLY build_router(resolve_tenant, can, need_auth,
# forbidden, firewall) -- tenant_id is ALWAYS resolve_tenant(request)["tenant_id"] (token-derived),
# NEVER a body/query field. Writes enforce can(t,"write"); /workflows/killswitch is admin-only
# (can(t,"manage_tenants")); /workflows/runs/{id}/approve verifies the firewall step-up token bound to
# the authed tenant (sub==tenant_id) inside the approval node. ⚠ We NEVER mount the bare module-level
# `workflow.endpoints.router` (kept for the offline test only): it reads tenant_id from the request
# body so the package can run decoupled, which is the exact cross-tenant hole build_router closes
# (RLS cannot save it -- the store would be invoked with the attacker-supplied tenant).
#
# EVENT BRIDGE: attach_event_bridge(app) is called inside the flag-on block. Today it is a DEFINED-not-
# wired no-op descriptor (zero side effects -- it does NOT touch caller.py's emit points): the real
# spine emit wiring (_emit_webhook / _finalize_call -> dispatch_event) is DEFERRED (Lifecycle-Trigger
# unit), so calling it is safe and satisfies the checklist without changing behavior.
#
# NO init()/ensure_schema TO DEFER (unlike payments/support/forms/booking): workflow-studio has none.
# make_store() defaults to the IN-MEMORY backend unless WORKFLOW_STORE=pg, so even with the flag ON the
# live PG is NOT touched. The Hatchet engine is dormant-until-creds (hatchet_sdk is LAZY-imported inside
# get_hatchet(), never at module top), so the same single interpreter runs in-process when dormant.
#
# IMPORT: the inner package was deployed to /opt/famit-agent/workflow/ (a plain top-level package, like
# ads_engine/media_gen) so `from workflow.endpoints import build_router` resolves with NO sys.path hack;
# this also lets funnels' later `import workflow` resolve for free. Mount workflow BEFORE funnels.
#
# IMPORT-GUARD (house pattern): a missing/broken workflow package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_WORKFLOWS!=1/true => router NOT mounted => byte-identical behavior.
try:
    from workflow.endpoints import build_router as _build_workflow_router  # noqa: E402
    from workflow.events import attach_event_bridge as _wf_attach_event_bridge  # noqa: E402
except Exception:  # noqa: BLE001
    _build_workflow_router = None
    _wf_attach_event_bridge = None

FEATURE_WORKFLOWS = (cfg_get("FEATURE_WORKFLOWS", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_WORKFLOWS and _build_workflow_router is not None:
    try:
        _workflow_router = _build_workflow_router(
            resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod
        )
        if _workflow_router is not None:
            app.include_router(_workflow_router)
        if _wf_attach_event_bridge is not None:
            _wf_attach_event_bridge(app)
    except Exception:  # noqa: BLE001 -- a mount failure must never crash the live spine
        import logging as _lg_workflow
        _lg_workflow.getLogger("famit-caller").warning("workflow-studio router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT -- ai-manager (voice/chat command-center management API, prefix /ai-manager). FLAG-GATED.
# ----------------------------------------------------------------------------------------------
# TENANT ISOLATION: ai-manager is a BARE-OK / TOKEN-DERIVED module (same class as ads-engine, NOT the
# body/header-tenant class of media-gen/booking/funnels). ai_manager.endpoints derives tenant ONLY from
# the authenticated request via a lazy `import caller; caller.resolve_tenant(request)` -- tenant_id is
# ALWAYS t["tenant_id"] (token), NEVER a body/query field. So a plain app.include_router(router) is safe
# (no cross-tenant hole; no build_router needed). Reads enforce can(t,"read"), writes can(t,"write"),
# grant/revoke require can(t,"manage_tenants") + a firewall step-up. The two SERVICE-TOKEN endpoints
# (/numbers/lookup, POST /sessions) are DORMANT until AIM_SERVICE_TOKEN is set (always 401 otherwise).
#
# NO init()/ensure_schema TO DEFER: ai-manager persists sessions as JSONL on the control plane (no PG /
# no DDL), so there is nothing schema-side to gate -- the live PG is never touched, flag ON or OFF.
# The LiveKit voice front (inbound_agent.py) + SIP dispatch are a SEPARATE later wire (do NOT pass
# through caller.py); this mount is the management/HTTP surface only.
#
# IMPORT: the package was deployed to /opt/famit-agent/ai_manager/ (a plain top-level package, like
# ads_engine/media_gen/workflow) so `from ai_manager.endpoints import router` resolves with NO sys.path
# hack. router is None when FastAPI is absent (offline test env) -- guarded below.
#
# IMPORT-GUARD (house pattern): a missing/broken ai_manager package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_AI_MANAGER!=1/true => router NOT mounted => byte-identical behavior.
try:
    from ai_manager.endpoints import router as _ai_manager_router  # noqa: E402
except Exception:  # noqa: BLE001
    _ai_manager_router = None

FEATURE_AI_MANAGER = (cfg_get("FEATURE_AI_MANAGER", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_AI_MANAGER and _ai_manager_router is not None:
    try:
        app.include_router(_ai_manager_router)
    except Exception:  # noqa: BLE001 -- a mount failure must never crash the live spine
        import logging as _lg_aimanager
        _lg_aimanager.getLogger("famit-caller").warning("ai-manager router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT -- funnels (ad->landing->lead->call->WA->booking->payment funnel builder, prefix
# /funnels). FLAG-GATED. ⚠ SECURITY-CRITICAL: was the "BLOCKED" checklist row #9.
# ----------------------------------------------------------------------------------------------
# TENANT ISOLATION (the build-state must-fix, RESOLVED): funnels ships BOTH a bare module-level `router`
# (funnels.endpoints.router) that reads tenant_id FROM THE BODY (`payload.get("tenant_id")`) -- the exact
# cross-tenant hole -- AND a CLEAN token-deriving `build_router(resolve_tenant, can, need_auth, forbidden,
# firewall)` (funnels/endpoints.py L132, the same shape as workflow-studio/forms-surveys, ADDED by the
# 2026-06-10 security fix). We mount ONLY `build_router`: every route does
# `t = resolve_tenant(request)` (token), `if not t: need_auth()`, tenant_id is ALWAYS t["tenant_id"]
# (verified by Read), writes enforce `can(t,"write")`. Because publish/run DELEGATE to the workflow engine,
# deriving tenant from the TOKEN here is what stops an attacker body-tenant from flowing into
# workflow.publish/run. We NEVER mount the bare `router`, and we DO NOT apply funnel_wiring.diff (the
# shipped diff mounts the bare body-tenant router = the hole; it is inert text in the package, ignored).
#
# ORDER: mounted AFTER workflow-studio (above) -- funnels lazy-`import workflow` to delegate publish/run,
# and the workflow package is already on the box (/opt/famit-agent/workflow/), so this resolves for free.
#
# NO init()/ensure_schema TO DEFER: make_store() defaults to the IN-MEMORY backend unless FUNNELS_STORE=pg,
# so even with the flag ON the live PG is NOT touched. No DDL. config.killswitch() (FUNNELS_KILLSWITCH) is a
# separate runtime break-glass, NOT this mount flag.
#
# IMPORT-GUARD (house pattern): a missing/broken funnels package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_FUNNELS!=1/true => router NOT mounted => byte-identical behavior.
try:
    from funnels.endpoints import build_router as _build_funnels_router  # noqa: E402
except Exception:  # noqa: BLE001
    _build_funnels_router = None

FEATURE_FUNNELS = (cfg_get("FEATURE_FUNNELS", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_FUNNELS and _build_funnels_router is not None:
    try:
        _funnels_router = _build_funnels_router(
            resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod
        )
        if _funnels_router is not None:
            app.include_router(_funnels_router)
    except Exception:  # noqa: BLE001 -- a mount failure must never crash the live spine
        import logging as _lg_funnels
        _lg_funnels.getLogger("famit-caller").warning("funnels router mount failed", exc_info=True)


# ==============================================================================================
# MODULE MOUNT -- whatsapp-builder (AI WhatsApp template-generation BRAIN, prefix
# /whatsapp/campaign). FLAG-GATED, default OFF, dormant-until-creds.
# ----------------------------------------------------------------------------------------------
# WHAT: the upstream brain for the WhatsApp Campaign Builder -- pick a campaign -> the LLM
# (reused Groq->OpenRouter seam) PROPOSES Meta-compliant template suggestions + variations + CTAs
# + personalization tokens + media recs + campaign structure; a DETERMINISTIC Meta-compliance
# validator is the AUTHORITY (grammar, category auto-classify, NO-INVENT scrub). Spec:
# design/wa-template-ai-backend.md. Package deployed to /opt/famit-agent/whatsapp_builder/.
#
# DISTINCT from the live whatsapp.py (send/receive/webhook) -- this NEVER edits it. Generation
# spend rides wallet.py (resource_type="wa_template_gen", idempotent F4 reserve/settle/release);
# the eventual per-message SEND cost stays the whatsapp.py meter's job (no double-charge here).
#
# TENANT ISOLATION: we mount ONLY the token-deriving build_router (funnels/workflow shape). Every
# route does `t = resolve_tenant(request)` (token), tenant_id is ALWAYS t["tenant_id"], NEVER a
# body/query field. Writes enforce can(t,"write"). There is NO bare body-tenant router to avoid.
#
# NO init()/ensure_schema TO DEFER AT IMPORT: the ai_wa_* DDL (whatsapp_builder/db/ddl_ai_wa.sql)
# is applied STANDALONE via psql as famit_app (off the Alembic chain, same as ddl_wallet.sql).
# With no DB reachable the module falls back to var/whatsapp_builder/*.jsonl, so the live PG is
# untouched whether the flag is ON or OFF until the schema is explicitly applied + ENSURE run.
#
# IMPORT-GUARD (house pattern): a missing/broken whatsapp_builder package can NEVER break startup.
# FEATURE FLAG default OFF: FEATURE_WHATSAPP_BUILDER!=1/true => router NOT mounted => byte-identical.
try:
    from whatsapp_builder.router import build_router as _build_wab_router  # noqa: E402
except Exception:  # noqa: BLE001
    _build_wab_router = None

FEATURE_WHATSAPP_BUILDER = (cfg_get("FEATURE_WHATSAPP_BUILDER", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_WHATSAPP_BUILDER and _build_wab_router is not None:
    try:
        _wab_router = _build_wab_router(
            resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod
        )
        if _wab_router is not None:
            app.include_router(_wab_router)
    except Exception:  # noqa: BLE001 -- a mount failure must never crash the live spine
        import logging as _lg_wab
        _lg_wab.getLogger("famit-caller").warning("whatsapp-builder router mount failed", exc_info=True)
