# DESIGN SPEC — Logto self-hosted OIDC (Phase 4 AUTH), STRANGLE & EVOLVE

> Status: EXECUTION-READY. A build agent implements this verbatim, one unit at a time, crash-safe.
> Verdict (settled): keep the live system earning. Logto is added **behind a feature flag, default OFF**,
> as a THIRD credential branch in the existing `resolve_tenant` chokepoint. Legacy `X-Auth: FamitCall2026`,
> the HS256 JWT from `auth.py`, and the `tenant_id.hmac` token ALL keep working through and after cutover.
> Nothing in the voice path, billing, campaigns, or `/run` changes.

---

## 0. GROUND TRUTH (verified against source — cite before editing)

Backend lives on `famit@168.144.153.145:/opt/famit-agent/` (service `famit-caller`, uvicorn `caller:app :8209`,
venv `/opt/capsy-agent/.venv` py3.12.3). SSH key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`. Public base
`https://panel.famit.in/api` (nginx on the panel box `143.110.247.249` strips `/api/` → `168.144.153.145:8209`).
Backend ufw allows `:8209` ONLY from `10.122.0.2` (the panel box private IP). Local edit copies:
`C:\Users\kunal\Desktop\caps\droplet_work\`.

The auth chokepoint and the exact seams Logto plugs into:

- **`droplet_work/caller.py:366` `resolve_tenant(request)`** — THE single auth chokepoint. Order today:
  (1) `_auth_mod.resolve_token(cred)` [HS256 JWT, `caller.py:379-385`]; (2) legacy `cred == PW` → admin
  [`:389`]; (3) `_verify_token(cred)` [hmac, `:391`]. Branches 2+3 gated by `LEGACY_TOKEN_ENABLED`
  (`caller.py:96`, default true). **We insert Logto as a NEW branch BEFORE step 1.**
- **`droplet_work/caller.py:352` `_extract_cred(request)`** — already pulls the raw cred from
  `Authorization: Bearer` / Basic / `X-Auth`. Reused unchanged for Logto bearer tokens.
- **`droplet_work/caller.py:331` `_tenant_by_id(tid)`** and **`:296` `_read_tenants()`** — tenant store
  (`var/tenants.json`, list of `{tenant_id,email,salt,pass_hash,name,is_admin,role,created_at, ...limits}`).
- **`droplet_work/caller.py:534 _role_of(tenant)`** — `explicit role | is_admin→admin | else manager`.
  Reused to map a Logto org-role → our role when minting/refreshing.
- **`droplet_work/caller.py:304 _seed_admin()`** — seeds the single admin tenant (`tenant_id="admin"`).
- **`droplet_work/auth.py`** — the HS256 module (Wave P0). `init(...)` at `caller.py:637`. We DO NOT modify
  `auth.py`'s verification (HS256 stays for the legacy/native JWT path); Logto verification is a SEPARATE
  module so the two never entangle.
- **`droplet_work/config.py` `get()/require()`** — secret/flag resolver (`cfg_get` alias in caller.py).
  All new env flags read through this, so Doppler/`.env` both work.
- Frontend: Next.js at `/opt/famit-panel` on `143.110.247.249` (systemd `famit-panel`, `next -p 3001`,
  user `deployuser`). `lib/api.ts` sends `X-Auth` from `localStorage['famit_token']`; `AuthGuard` in
  `app/providers.tsx`; login page posts `{email,password}` to `/api/login`. WORKING COPY for edits:
  `C:\Users\kunal\Desktop\caps\famit-panel` (confirm path on box before deploy — HANDOFF says panel was
  rebuilt at `/opt/famit-panel`; the local working copy may still be `caps\famit-panel`).

P1 lock (P1_FOUNDATION_STATE.md:21,38): **`org_id == existing tenant_id`** as the mapping principle, and
P1.U7 will mirror `orgs/users/memberships` into Postgres. Logto becomes the IdP that backs those rows.
IMPORTANT nuance this spec resolves: a **Logto organization's id is its own random string** (e.g.
`abcd1234`), NOT our `tenant_id` ("admin"). So we map via a NEW tenant field **`logto_org_id`**, set at
provision time. "org_id == tenant_id" remains the *semantic* mapping (1 Logto org ⇔ 1 tenant); the join key
is `logto_org_id` on the tenant record.

### The core technical seam (the one thing that matters)
`auth.py` verifies **HS256** (symmetric, shared `var/secret`). **Logto issues RS256 JWTs verified via JWKS**
(`{ENDPOINT}/oidc/jwks`), with issuer `{ENDPOINT}/oidc`. For backend calls Logto issues an **organization
(API-resource) token** whose claims are:
- `iss` = `{LOGTO_ENDPOINT}/oidc`
- `aud` = the API resource indicator we register (e.g. `https://api.famit.in`) — for **org-level API
  resource** tokens; `organization_id` is then ALSO present. (Per Logto docs: a token requested *with* an
  `organization_id` carries both the API `aud` and the `organization_id` claim, scopes filtered to that
  org's roles. citation: logto docs "organization-level API resources".)
- `organization_id` = the Logto org id (our join key → `logto_org_id`)
- `sub` = the Logto user id
- `scope` = space-separated permissions
- `roles` (or org roles surfaced via scopes) — used to derive our `admin|manager|agent`.

So Logto verification = **RS256 + JWKS + check iss + check aud == our API indicator + read
`organization_id` → tenant**. This is implemented in a NEW module `logto_verify.py`, never in `auth.py`.

---

## 1. ARCHITECTURE DECISION (locked for this subsystem)

1. **Additive, flag-gated, default OFF.** New flag `LOGTO_ENABLED` (default `false`). When false,
   `logto_verify` is a hard NO-OP and `resolve_tenant` is byte-for-byte the behaviour shipped today.
2. **New module `logto_verify.py`** (parallel to `auth.py`). Verifies Logto RS256 access/organization
   tokens via a cached JWKS client, validates `iss`/`aud`/`exp`, extracts `organization_id` + roles +
   email, and resolves to a tenant via `logto_org_id`. Import-safe degrade exactly like the P0 modules
   (`auth`, `audit`, `obs`): a failed import or missing PyJWKClient → `_auth_mod`-style `None`, legacy path
   untouched.
3. **Logto is the IdP, `tenants.json` stays authoritative for authZ scoping.** We do NOT move the user
   database into Logto in this phase. Logto authenticates; the existing tenant record (looked up by
   `logto_org_id`) still carries `is_admin`/`role`/limits/billing that every endpoint already reads. This
   keeps RLS-by-tenant, billing, RBAC, and the P1 Postgres migration entirely unchanged.
4. **Just-In-Time tenant provisioning (optional, flagged).** First time a valid Logto org token arrives
   for a `logto_org_id` we don't know, IF `LOGTO_JIT_PROVISION=true` (default `false`) create a tenant row
   (role from org-role claim, never admin). Default off → unknown org → 401 (safe; you pre-provision the
   mapping explicitly via `POST /tenants` / the backfill script).
5. **Two enforcement points unchanged.** `organization_id`→tenant at the API boundary AND (Phase 1) Postgres
   RLS by `tenant_id`. Logto only changes *how the caller proves identity*, not the scoping.
6. **Deployment:** Logto runs as Docker on the existing backend box `168.144.153.145`, bound to
   `127.0.0.1` only, fronted by nginx on the panel box at `auth.famit.in` (Cloudflare). It uses an EXTERNAL
   managed/standalone Postgres (NOT the bundled compose db — that bundled db is dev-only and data-losing).
   **RED-TEAM FIX #3 (hidden coupling — co-location with the latency-critical voice agent):** the agent on
   this box is TTFT-sensitive (HANDOFF is emphatic; free-tier Groq already causes spikes). Putting a Java/
   Node IdP **and** its Postgres in CPU/RAM contention with `famit-agent` can regress call latency. MUST
   pin `mem_limit`/`cpus` on the Logto + PG containers (see 4.2), OR host Logto on the panel box
   `143.110.247.249` and fetch JWKS over the VPC (FIX #2 makes the fetch URL configurable for exactly this).
   Decide explicitly; do not co-locate unbounded.
7. **Social login (Google) is OPTIONAL and decoupled** — a console toggle + connector creds; the backend
   verification code is identical whether the user logged in by email/password or Google (it only ever sees
   a Logto-signed JWT). No code path depends on Google.
8. **Rollback = flip `LOGTO_ENABLED=false` and restart.** Zero data migration to undo. Legacy creds never
   stopped working, so there is no lockout risk.

### Why not replace `auth.py` HS256 with Logto outright
Because the live panel + every curl/test + the frontend send `X-Auth: FamitCall2026` and `tenant_id.hmac`
tokens today; ripping those out is the breaking change we are explicitly avoiding. Logto is *added*; legacy
is *retired later* by flipping `LEGACY_TOKEN_ENABLED=false` only once telemetry shows zero legacy traffic.

---

## 2. FILES TO CREATE / EDIT (exact paths)

### CREATE
| Path | Purpose | Model |
|---|---|---|
| `droplet_work/logto_verify.py` | RS256/JWKS Logto token verification + org→tenant resolution. Import-safe. | opus |
| `droplet_work/logto_provision.py` | Idempotent admin script: create Logto orgs for existing tenants via Logto Management API, write `logto_org_id` back into `var/tenants.json`. Run manually. | sonnet |
| `infra/logto/docker-compose.logto.yml` | Logto OSS container (external PG), bound 127.0.0.1, on the backend box. | sonnet |
| `infra/logto/logto.env.example` | Documented env template (DB_URL, ENDPOINT, ADMIN_ENDPOINT, secrets). NO real secrets committed. | sonnet |
| `infra/logto/nginx-auth.conf` | nginx vhost `auth.famit.in` → `127.0.0.1:3001` (core) and the admin console gate. | sonnet |
| `design/auth-logto.md` | THIS spec. | (done) |

### EDIT
| Path:line | Change | Model |
|---|---|---|
| `droplet_work/caller.py:96` (flag block) | Add `LOGTO_ENABLED`, `LOGTO_ENDPOINT`, `LOGTO_API_RESOURCE`, `LOGTO_JIT_PROVISION`, `LOGTO_JWKS_TTL` flags via `cfg_get`. | opus |
| `droplet_work/caller.py:70` (defensive import block, next to `import auth as _auth_mod`) | Add `try: import logto_verify as _logto_mod except: _logto_mod=None`. | opus |
| `droplet_work/caller.py` (after `_role_of`/tenant helpers, near `:643` wiring) | Add `_logto_mod.init(...)` wiring with callbacks `tenant_by_logto_org`, `provision_tenant`, `role_map`. | opus |
| `droplet_work/caller.py:366` `resolve_tenant` | Insert Logto branch as STEP 0 (before the HS256 branch). ~8 lines, try/except, returns tenant or falls through. | opus |
| `droplet_work/caller.py` (`/me` route `:1773`) | Add `auth_source` field (`logto|jwt|legacy`) to the response for observability. (optional, additive) | sonnet |
| `droplet_work/caller.py` (`/health` or new `/auth/providers`) | Expose `{logto_enabled, logto_endpoint, jwks_ok}` for a no-secret readiness probe. | sonnet |
| frontend `lib/api.ts` + `app/providers.tsx` + login page | Add OPTIONAL Logto login (redirect flow) behind a build-time/env flag; keep email/password→`/api/login` as the default. Store Logto access token, send as `Authorization: Bearer`. | sonnet |

---

## 3. `logto_verify.py` — CONTRACT (the build agent implements to this)

```python
"""logto_verify.py — verify Logto (self-hosted OIDC) RS256 tokens, map org->tenant.

ADDITIVE + import-safe. Mirrors auth.py's degrade contract: if PyJWT/PyJWKClient is
unavailable OR LOGTO is unconfigured, available() is False and resolve_token() returns
None so caller.resolve_tenant() falls straight through to the existing branches.

Never raises into a request. Never touches auth.py's HS256 path.
"""
from __future__ import annotations
import time
from typing import Any, Callable, Optional

try:
    import jwt as _jwt
    from jwt import PyJWKClient            # PyJWT >= 2.x ships PyJWKClient
except Exception:
    _jwt = None
    PyJWKClient = None  # type: ignore

ALGOS = ["RS256"]

# ---- injected via init() ----
_ENDPOINT = ""            # e.g. https://auth.famit.in   (NO trailing slash) — used for ISSUER
_ISSUER = ""              # f"{_ENDPOINT}/oidc"  (token `iss` MUST equal the PUBLIC endpoint)
_JWKS_URI = ""            # RED-TEAM FIX #2: key FETCH uri — defaults to the LOCALHOST Logto core
                          # (http://127.0.0.1:3001/oidc/jwks), NOT {_ENDPOINT}/oidc/jwks. The
                          # issuer string and the fetch URL are independent; fetching over the
                          # public host hairpins backend->Cloudflare->panel-nginx->VPC->the Logto
                          # container on the SAME backend box on every cold-kid fetch. Keep the
                          # `iss` check public, fetch keys locally.
_API_RESOURCE = ""        # registered API indicator, e.g. https://api.famit.in
_TENANT_BY_LOGTO_ORG: Callable[[str], Optional[dict]] = lambda _o: None
_PROVISION: Optional[Callable[[str, str, str], Optional[dict]]] = None  # (org_id,email,role)->tenant
_ROLE_MAP: Callable[[list[str]], str] = lambda _roles: "manager"
_JIT = False
_jwks_client = None       # PyJWKClient (caches keys, lifespan_hours=… built-in cache)
_ready = False
_JWKS_FETCHES = 0         # FIX #1 instrumentation: bumped each time we actually hit JWKS.

def _jwks_fetch_count() -> int:
    return _JWKS_FETCHES
# Wrap get_signing_key_from_jwt so test (a) can observe network fetches WITHOUT relying on
# PyJWT internals: increment a counter only on a real key resolution. (The authoritative
# cross-check remains the Logto core access-log hit count for /oidc/jwks — see STEP 6 (a).)

def init(endpoint, api_resource, tenant_by_logto_org, role_map,
         provision=None, jit=False, jwks_ttl=600, jwks_uri="") -> bool:
    """Wire to caller.py. Returns True if Logto verification is live.
    `jwks_uri` (RED-TEAM FIX #2): explicit key-fetch URL; defaults to the localhost Logto
    core so verification never hairpins through the public edge."""
    global _ENDPOINT,_ISSUER,_JWKS_URI,_API_RESOURCE,_TENANT_BY_LOGTO_ORG,_PROVISION,_ROLE_MAP,_JIT,_jwks_client,_ready
    _ENDPOINT = (endpoint or "").rstrip("/")
    if not _ENDPOINT or _jwt is None or PyJWKClient is None:
        _ready = False; return False
    _ISSUER = f"{_ENDPOINT}/oidc"                              # PUBLIC issuer (token `iss`)
    _JWKS_URI = (jwks_uri or "").rstrip("/") or "http://127.0.0.1:3001/oidc/jwks"  # LOCAL fetch
    _API_RESOURCE = api_resource or ""
    _TENANT_BY_LOGTO_ORG = tenant_by_logto_org
    _ROLE_MAP = role_map or _ROLE_MAP
    _PROVISION = provision
    _JIT = bool(jit)
    try:
        # PyJWKClient caches keys and refetches on unknown kid; ttl via lifespan
        _jwks_client = PyJWKClient(_JWKS_URI, cache_keys=True, lifespan=int(jwks_ttl))
        _ready = True
    except Exception:
        _ready = False
    return _ready

def available() -> bool:
    return _ready

def resolve_token(cred: str) -> Optional[dict]:
    """If cred is a valid Logto org/access JWT, return the mapped tenant dict; else None.
    NEVER raises. A non-JWT (bare PW / tenant_id.hmac) fails decode -> None -> legacy path."""
    if not _ready or not cred or cred.count(".") != 2:
        return None
    # RED-TEAM FIX #1 (BLOCKING for flag-ON): peek the UNVERIFIED claims and bail on a
    # foreign issuer BEFORE touching the JWKS client. Without this, every legacy P0 HS256
    # token (2 dots, no `kid`) and every attacker-supplied `aaa.bbb.ccc` would reach
    # get_signing_key_from_jwt(), miss the kid, and force a SYNCHRONOUS outbound JWKS
    # refetch on the event loop (PyJWKClient refreshes with refresh=True on a kid miss,
    # bypassing the lifespan cache) — a per-request latency hit on the warm panel path and
    # a pre-auth, unauthenticated DoS / loop-stall vector. auth.py `_make_access` sets NO
    # `iss` claim, so legacy famit JWTs are filtered here for free, zero network.
    try:
        _unv = _jwt.decode(cred, options={"verify_signature": False})
    except Exception:
        return None
    if _unv.get("iss") != _ISSUER:        # only Logto-issued tokens proceed to JWKS
        return None
    try:
        global _JWKS_FETCHES
        _JWKS_FETCHES += 1                 # FIX #1 instrumentation (test (a) reads this)
        signing_key = _jwks_client.get_signing_key_from_jwt(cred)  # network only on new kid
        opts = {"require": ["exp", "iss"]}
        # Verify aud ONLY when we registered an API resource (org-API-resource tokens carry it).
        # `leeway=30` tolerates clock skew on the short 15-min org tokens (RED-TEAM test (d)).
        if _API_RESOURCE:
            payload = _jwt.decode(cred, signing_key.key, algorithms=ALGOS, leeway=30,
                                  issuer=_ISSUER, audience=_API_RESOURCE, options=opts)
        else:
            payload = _jwt.decode(cred, signing_key.key, algorithms=ALGOS, leeway=30,
                                  issuer=_ISSUER, options={**opts, "verify_aud": False})
    except Exception:
        return None
    org_id = payload.get("organization_id")
    # Fallback: some Logto org (non-API) tokens carry org in aud as urn:logto:organization:<id>
    if not org_id:
        auds = payload.get("aud", [])
        auds = [auds] if isinstance(auds, str) else (auds or [])
        for a in auds:
            if isinstance(a, str) and a.startswith("urn:logto:organization:"):
                org_id = a.split(":")[-1]; break
    if not org_id:
        return None
    tenant = _TENANT_BY_LOGTO_ORG(org_id)
    if tenant:
        return tenant
    if _JIT and _PROVISION:
        roles = _extract_roles(payload)
        return _PROVISION(org_id, payload.get("username") or payload.get("email") or "",
                          _ROLE_MAP(roles))
    return None

def _extract_roles(payload: dict) -> list[str]:
    # RED-TEAM FIX #5: Logto org-API-resource tokens convey grants via `scope`
    # (space-separated permissions), NOT a top-level `roles` claim. Reading only
    # roles/organization_roles → JIT tenants ALWAYS resolve "manager". Low impact
    # (tenants.json is authoritative for authZ; the org-role is only a provisioning
    # seed), but derive from scope too so the seed is meaningful. Map perms→role in
    # _logto_role_map (e.g. a `manage_tenants` scope ⇒ stronger role) if you ever lean
    # on Logto for role. Do NOT auto-grant admin from a scope.
    r = payload.get("roles") or payload.get("organization_roles") or []
    if isinstance(r, str): r = [r]
    if not r:
        scope = payload.get("scope") or ""
        r = scope.split() if isinstance(scope, str) else []
    return r

def health() -> dict:
    """No-secret readiness for /auth/providers.
    Pass `refresh=False` so this probe reads the CACHED set and never itself triggers a
    network fetch (otherwise the readiness probe pollutes the FIX-#1 no-refetch test)."""
    ok = False
    if _ready:
        try:
            _jwks_client.get_jwk_set(refresh=False)  # cached; no network on the probe
            ok = True
        except Exception:
            ok = False
    return {"logto_enabled": _ready, "endpoint": _ENDPOINT, "issuer": _ISSUER,
            "jwks_uri": _JWKS_URI, "jwks_ok": ok, "jwks_fetches": _jwks_fetch_count()}
```

### Wiring in caller.py (near the `auth.init(...)` block, after `_role_of` + tenant helpers exist):

```python
# --- Logto (self-hosted OIDC) verification — additive, flag-gated, default OFF ---
def _tenant_by_logto_org(org_id: str) -> dict | None:
    if not org_id:
        return None
    return next((t for t in _read_tenants() if t.get("logto_org_id") == org_id), None)

def _logto_role_map(roles: list[str]) -> str:
    rl = [str(x).lower() for x in (roles or [])]
    if "admin" in rl:    return "admin"
    if "agent" in rl or "readonly" in rl or "viewer" in rl: return "agent"
    return "manager"

def _provision_tenant_from_logto(org_id: str, email: str, role: str) -> dict | None:
    """JIT: create a NON-admin tenant bound to a Logto org. Idempotent on logto_org_id.
    RED-TEAM FIX #4 (must-fix BEFORE enabling JIT): this read-modify-write of tenants.json
    runs from the SYNC request path with NO lock. P0 added `_STORE_LOCK` for exactly this
    hazard — concurrent first-hits for one org race into duplicate/lost rows. JIT is OFF by
    default so this is non-blocking TODAY, but enabling LOGTO_JIT_PROVISION is gated on
    routing this write through the same locked seam P0/P1 use (or making provisioning an
    out-of-band admin action, not an inline request-path side effect). `pass_hash=""` is
    VERIFIED-SAFE (not an auth bypass): `_hash_pw` never returns "" so no password can match
    it, and `is_admin` is hard-False here."""
    tenants = _read_tenants()
    existing = next((t for t in tenants if t.get("logto_org_id") == org_id), None)
    if existing:
        return existing
    tid = secrets.token_hex(6)
    t = {"tenant_id": tid, "email": (email or "").lower(),
         "salt": secrets.token_hex(8), "pass_hash": "",          # no local password; Logto-only
         "name": email or f"org-{org_id[:6]}",
         "is_admin": False,                                       # JIT NEVER mints admin
         "role": role if role in ("manager", "agent") else "manager",
         "logto_org_id": org_id,
         "created_at": datetime.now().isoformat(timespec="seconds")}
    tenants.append(t); _write_tenants(tenants)
    return t

LOGTO_JWT_READY = False
if _logto_mod is not None and LOGTO_ENABLED:
    try:
        LOGTO_JWT_READY = _logto_mod.init(
            endpoint=LOGTO_ENDPOINT,
            api_resource=LOGTO_API_RESOURCE,
            tenant_by_logto_org=_tenant_by_logto_org,
            role_map=_logto_role_map,
            provision=(_provision_tenant_from_logto if LOGTO_JIT_PROVISION else None),
            jit=LOGTO_JIT_PROVISION,
            jwks_ttl=int(LOGTO_JWKS_TTL),
            jwks_uri=LOGTO_JWKS_URI,        # RED-TEAM FIX #2: localhost key fetch by default
        )
    except Exception:
        LOGTO_JWT_READY = False
```

### The ONLY change to `resolve_tenant` (caller.py:366) — insert as STEP 0:

```python
    cred = _extract_cred(request)
    if not cred:
        return None
    # 0) Logto (self-hosted OIDC) RS256 org token — additive, flag-gated, default OFF.
    if _logto_mod is not None and LOGTO_JWT_READY:
        try:
            t = _logto_mod.resolve_token(cred)
            if t:
                return t
        except Exception:        # never let Logto break a request
            pass
    # 1) P0 HS256 JWT access token (unchanged) ...
    if _auth_mod is not None:
        ...
```

Everything below step 1 is untouched. When `LOGTO_ENABLED=false` (default), `LOGTO_JWT_READY` is False and
this block is a single boolean check that always falls through — i.e. ZERO behavioural change.

### New flags block (caller.py:96 area):
```python
LOGTO_ENABLED = (cfg_get("LOGTO_ENABLED", "false") or "false").strip().lower() in ("1","true","yes","on")
LOGTO_ENDPOINT = cfg_get("LOGTO_ENDPOINT", "")              # e.g. https://auth.famit.in
LOGTO_API_RESOURCE = cfg_get("LOGTO_API_RESOURCE", "")      # e.g. https://api.famit.in
LOGTO_JIT_PROVISION = (cfg_get("LOGTO_JIT_PROVISION","false") or "false").strip().lower() in ("1","true","yes","on")
LOGTO_JWKS_TTL = cfg_get("LOGTO_JWKS_TTL", "600")
# RED-TEAM FIX #2: key-fetch URL. Default = localhost Logto core (no public-edge hairpin).
# Override only if Logto runs off-box. `iss` is still checked against LOGTO_ENDPOINT.
LOGTO_JWKS_URI = cfg_get("LOGTO_JWKS_URI", "http://127.0.0.1:3001/oidc/jwks")
```

### Tenant record gains ONE field
`logto_org_id` (string, optional). Backfilled by `logto_provision.py` (Section 6) and settable via an
extended `POST /tenants` (add optional `logto_org_id` form field → `_role_of`-consistent). Migration:
nothing required — absent field just means "no Logto org mapped yet" (legacy auth still works for that
tenant). This dovetails with P1.U7 (`orgs/users/memberships`): store `logto_org_id` on the `orgs` row too.

---

## 4. LOGTO DEPLOYMENT (Docker on DO `168.144.153.145`)

### 4.1 Database (do NOT use the bundled compose Postgres — it is dev-only/data-losing)
Logto needs its OWN Postgres database. Two acceptable options; pick by cost:
- **Option A (recommended, isolated):** a dedicated `logto` database in a **DO Managed Postgres** cluster
  (blr1) OR a separate standalone Postgres container with a **named volume** (NOT bundled-ephemeral).
- **Option B (cheapest):** reuse the box's Postgres instance that P1 provisions, but a SEPARATE database
  `logto` and a SEPARATE role `logto_app` (NEVER the `famit_app` RLS role, NEVER the app `famit` db). Logto
  manages its own schema; keep it physically separate from the tenant data db to avoid coupling and to keep
  the P1 RLS model clean.

`DB_URL=postgres://logto_app:<pw>@<host>:5432/logto`

### 4.2 `infra/logto/docker-compose.logto.yml`
```yaml
# Logto OSS — bound to localhost only; nginx terminates TLS at auth.famit.in.
# External Postgres (see 4.1). Do NOT add the bundled postgres service for prod.
services:
  logto:
    image: ghcr.io/logto-io/logto:latest          # pin a concrete tag in prod, e.g. :1.x.y
    container_name: logto
    restart: unless-stopped
    # RED-TEAM FIX #3: cap resources so the IdP cannot starve the TTFT-critical voice agent
    # on this box. (compose v2 honours these; or enforce via a systemd slice / cgroup.)
    mem_limit: 1g
    cpus: 1.0
    # First boot ONLY needs the seed; afterwards run plain `npm start`.
    entrypoint: ["sh","-c","npm run cli db seed -- --swe && npm start"]
    ports:
      - "127.0.0.1:3001:3001"     # core / OIDC  -> nginx auth.famit.in
      - "127.0.0.1:3002:3002"     # admin console -> nginx (IP-allowlisted) or SSH tunnel only
    environment:
      - TRUST_PROXY_HEADER=1
      - DB_URL=${DB_URL}
      - ENDPOINT=https://auth.famit.in
      - ADMIN_ENDPOINT=https://auth.famit.in      # or a separate admin host; see 4.4
      # Secrets (generate; keep in .env / Doppler, NOT in compose):
      # - SECRET_…  (Logto generates app secrets in DB on seed; cookie keys below)
    env_file:
      - ./logto.env
```
> After the FIRST successful seed, change the entrypoint to `["sh","-c","npm start"]` (or set an env guard)
> so restarts don't re-run the seeder. The seeder is idempotent-ish but don't rely on it per-boot.

### 4.3 `infra/logto/logto.env.example`
```
# Copy to logto.env on the box, fill real values, chmod 600. NEVER commit the real file.
DB_URL=postgres://logto_app:CHANGE_ME@127.0.0.1:5432/logto
ENDPOINT=https://auth.famit.in
ADMIN_ENDPOINT=https://auth.famit.in
TRUST_PROXY_HEADER=1
# Optional: pin Logto cookie/oidc keys for multi-instance; single instance can let Logto manage them.
```

### 4.4 nginx (`infra/logto/nginx-auth.conf`, on the PANEL box 143.110.247.249, Cloudflare-fronted)
- `server_name auth.famit.in;` TLS via certbot (same pattern as panel.famit.in).
- `location / { proxy_pass http://127.0.0.1:3001; ... }` — BUT the backend box is `168.144.153.145`, so
  either (a) run nginx for auth ON the backend box and point a `auth.famit.in A 168.144.153.145` record at
  it, OR (b) proxy from the panel box over the VPC to `http://168.144.153.145:3001`. **Recommended:**
  terminate `auth.famit.in` on the panel box (where TLS/Cloudflare already live) and `proxy_pass` over the
  private VPC to the Logto container; open backend ufw `:3001` from `10.122.0.2` ONLY (mirrors the existing
  `:8209`-from-`10.122.0.2` rule). Standard OIDC proxy headers: `Host`, `X-Forwarded-Proto https`,
  `X-Forwarded-For`. Logto requires `TRUST_PROXY_HEADER=1` (set above) to honour them.
- **Admin console (3002):** do NOT expose publicly. Reach it via SSH tunnel
  (`ssh -L 3002:127.0.0.1:3002 famit@168.144.153.145`) OR an IP-allowlisted nginx location. Initial admin
  account is created on first visit to the admin console.

### 4.5 Logto console configuration (one-time, via admin console)
1. Create an **API resource** with indicator `https://api.famit.in` (= `LOGTO_API_RESOURCE`). Enable
   **"Is this a default API resource?"** off; we request it explicitly per org.
2. Enable **Organizations**. Create **organization roles**: `admin`, `manager`, `agent`, and organization
   **scopes/permissions** mapped onto the API resource (e.g. `read`, `write`, `manage_tenants`) so org
   tokens carry meaningful `scope`. (Our backend currently authorizes by tenant `role`, so scopes are
   advisory at first; wire scope→action later if desired.)
3. Create a **Machine-to-Machine app** for the Logto **Management API** (used by `logto_provision.py`):
   grant it the management API resource (`https://<logto>/api`) with `all` role. Capture
   `LOGTO_M2M_APP_ID` / `LOGTO_M2M_APP_SECRET`.
4. Create a **traditional web app** (for the Next.js panel) OR an **SPA app** — capture client id/secret,
   set redirect URIs `https://panel.famit.in/callback` and post-logout `https://panel.famit.in`.
5. **Google social connector (OPTIONAL):** Social connectors → Google → paste Google OAuth client
   id/secret (the founder-provided blocker #4). Purely a console action; no backend change.

---

## 5. STEP ORDER (each step: crash-safe unit + per-step ACCEPTANCE TEST on the live box)

> Golden rule every step: **back up before edit, deploy one unit, run the REGRESSION GATE, then the
> step's acceptance test, then commit/build_log.** Regression gate (reused from P1):
> `curl -H "X-Auth: FamitCall2026" https://panel.famit.in/api/campaigns` → 200; `/auth/login` issues
> tokens; `/me`,`/leads`,`/billing/overview` → 200; `famit-caller`+`famit-agent` active; md5 local==deployed;
> NO paid call. If any fails → revert THAT unit only.

**STEP 0 — Pre-flight (no code).** Confirm venv has PyJWT≥2 with PyJWKClient. `PyJWKClient` is a CLASS, not
a submodule — import it correctly:
`ssh famit@168.144.153.145 '/opt/capsy-agent/.venv/bin/python -c "import jwt; from jwt import PyJWKClient; print(jwt.__version__)"'`
(P0 already installed pyjwt). If the `from jwt import PyJWKClient` import fails →
`/opt/capsy-agent/.venv/bin/pip install -U "pyjwt[crypto]"` in the venv (adds `cryptography` for RS256).
**Accept:** prints a version ≥ 2.4 and no ImportError. ALSO assert the constructor kwargs this spec
uses actually exist on the installed version (they shipped well before 2.4, but verify rather than
assume): `PyJWKClient("https://x/jwks", cache_keys=True, lifespan=600)` must construct without
`TypeError` (a no-network construction is fine; it only fetches on first key use). If it raises
`TypeError: unexpected keyword`, the venv PyJWT is too old → `pip install -U "pyjwt[crypto]"`. This
guards against `init()` silently catching the TypeError and degrading to `_ready=False` — i.e. a
"why is Logto off even though the flag is on" mystery. Model: sonnet.

**STEP 1 — Ship `logto_verify.py` + caller wiring, flag OFF (the safe no-op deploy).** Create the module,
add the import, flags, wiring, and the `resolve_tenant` STEP-0 branch — but `LOGTO_ENABLED` stays unset
(=false). Deploy caller.py + logto_verify.py, restart famit-caller.
**Accept:** (a) regression gate fully green — because the Logto block is inert; (b)
`GET /auth/providers` (new) returns `{"logto_enabled": false, ...}`; (c) `python -c "import logto_verify"`
on the box succeeds. This proves the code is shippable with zero behaviour change. Model: opus. **COMMIT.**

**STEP 2 — Stand up Logto (Docker + external PG), still no app cutover.** Provision the `logto` db/role,
write `logto.env`, bring up the compose file bound to 127.0.0.1, seed once.
**Accept:** `curl -s http://127.0.0.1:3001/oidc/.well-known/openid-configuration` (on the box) returns JSON
with `"issuer":"https://auth.famit.in/oidc"` and a `jwks_uri`; admin console reachable via SSH tunnel.
Live panel/backend untouched (Logto is a separate process). Model: sonnet.

**STEP 3 — nginx `auth.famit.in` + Cloudflare DNS + ufw.** Add the vhost, certbot cert, open backend
ufw `:3001` from `10.122.0.2` only. **Accept:** `curl https://auth.famit.in/oidc/jwks` from the public
internet returns the JWKS JSON; `nginx -t` clean; `panel.famit.in` still 200 (gate). Model: sonnet.

**STEP 4 — Console config (API resource, orgs, roles + RESOURCE-SCOPED org permissions, M2M app, web app).**
Section 4.5. CRITICAL: the organization roles (`admin/manager/agent`) MUST be granted **permissions that
belong to the `https://api.famit.in` API resource** (not just plain org scopes) — otherwise an
org-API-resource token for that resource comes back with an EMPTY `scope` and may be refused, and the whole
point (an org token carrying `aud=https://api.famit.in` + `organization_id` + scopes) doesn't materialize.
**Accept (direct, not indirect):** via the M2M token, `GET {LOGTO}/api/resources` lists `https://api.famit.in`
AND `GET {LOGTO}/api/organizations` works; THEN mint an org-API-resource token for
`resource=https://api.famit.in` + an `organization_id`, base64-decode its payload, and assert
ALL of: `aud == "https://api.famit.in"`, `organization_id` present, `iss == "https://auth.famit.in/oidc"`,
`scope` non-empty. (This is the §10-risk-2 failure mode caught at config time instead of as an opaque 401.)
NOTE for the test grant: a token (M2M client-credentials OR a user) only receives `organization_id` if that
principal is a **member of the org with a role granting the API-resource permissions** — so for the STEP 6
test, add the M2M app (or test user) to the admin org with the `admin` org role; otherwise the minted token
comes back WITHOUT `organization_id` and the test fails confusingly.
Model: sonnet (founder may need to click Google connector — leave a HUMAN_TASKS line if creds absent).

**STEP 5 — Provision orgs for existing tenants + backfill `logto_org_id`.** Run `logto_provision.py`
(Section 6): for each tenant in `var/tenants.json`, create/find a Logto org, create a Logto user for the
tenant email, assign org membership + org role from the tenant's `role`, write `logto_org_id` back into
`var/tenants.json` (BACK UP the file first). **Accept:** every tenant row now has a `logto_org_id`; the
admin tenant maps to an "Admin" org with org-role `admin`; `var/tenants.json` still loads + legacy
`X-Auth: FamitCall2026` still 200 (we only ADDED a field). Model: sonnet. **COMMIT the script + the backed-up
mapping note (NOT secrets).**

**STEP 6 — Mint a real Logto org token + flip the flag in a CANARY way.** Set `LOGTO_ENABLED=true`,
`LOGTO_ENDPOINT=https://auth.famit.in`, `LOGTO_API_RESOURCE=https://api.famit.in` in `/opt/famit-agent/.env`
(BACK UP .env), restart famit-caller. Obtain an **org-API-resource token** for the admin org (the token from
`getAccessToken('https://api.famit.in', <adminOrgId>)`, or the equivalent client-credentials grant with
`resource=https://api.famit.in` + that `organization_id` — NOT a plain access token, which carries no
`organization_id` and would 401). FIRST decode it and assert `aud=="https://api.famit.in"` +
`organization_id` present (pre-check so a token-type mistake fails with a clear message, not an opaque 401),
THEN: `curl -H "Authorization: Bearer <logto_org_token>" https://panel.famit.in/api/me`.
**Accept (the money test):** (a) that call returns the ADMIN tenant identity (`tenant_id:"admin"`,
`is_admin:true`) and (if added) `auth_source:"logto"`; (b) SIMULTANEOUSLY legacy
`curl -H "X-Auth: FamitCall2026" .../api/campaigns` STILL returns 200; (c) the P0 HS256 path still works
(`/auth/login` → use that access token → 200). All three auth methods live at once = non-breaking proven.
`GET /auth/providers` now `{"logto_enabled":true,"jwks_ok":true}`.

**RED-TEAM acceptance tests (MANDATORY before COMMIT — these catch the test-invisible flag-ON
regressions; STEP 6 as originally written asserts 200 not latency and would pass while the box
hammers its own JWKS):**
- **(a) hot-path / no-refetch (proves FIX #1).** With the flag ON, hit `/me` 50× with a NORMAL P0
  **HS256** access token (from `/auth/login`). Assert ALL 200 AND the JWKS fetch count did NOT
  increase (read it from `/auth/providers`→`jwks_fetches` or the Logto core access log). If the
  count climbs, the `iss` pre-filter (FIX #1) is missing — every legacy JWT is forcing a network
  refetch on the event loop. Also time the 50 calls; p95 must be flat vs flag-OFF.
- **(b) JWKS-down isolation.** `docker stop logto`, then: a Logto org token → 401 (fail-closed,
  correct), WHILE `X-Auth: FamitCall2026` /campaigns and a P0 HS256 token both STILL return 200.
  Proves the Logto failure domain never touches the legacy/HS256 paths. Restart Logto after.
- **(c) algorithm-confusion negative.** Mint an HS256 token signed with the JWKS RSA *public* key
  bytes as the HMAC secret (the classic alg-confusion attack) and an RS256-shaped junk token; assert
  BOTH branches reject (Logto pins `algorithms=["RS256"]`, auth.py pins `["HS256"]`, different keys).
- **(d) expired / unknown-org → 401 not silent-200.** An expired org token → 401; a valid-signature
  token whose `organization_id` maps to NO tenant (JIT off) → 401. Neither falls through to a
  legacy 200.

Model: opus. **COMMIT.**

**STEP 7 — Frontend optional Logto login (behind env flag) — MUST send an ORGANIZATION token, not a plain
access token.** This is the one place a backend-only test can't catch a mistake: a vanilla SPA/web-login
access token carries **neither** `organization_id` nor the org `aud`, so `resolve_token` returns None and the
Logto login silently fails even though STEP 6's M2M curl passed. Implement with `@logto/react` (or `@logto/browser`):
1. Init the SDK with **`resources: ['https://api.famit.in']`** AND
   **`scopes: [UserScope.Organizations, ...]`** (i.e. include `urn:logto:scope:organizations` + the API
   resource permissions). Without the Organizations scope, no org token can be minted.
2. After login, read the user's org id from id-token claims (`getIdTokenClaims().organizations[0]`), then
   fetch the **org-API-resource token**: `await getAccessToken('https://api.famit.in', organizationId)`.
   Store THAT, send it as `Authorization: Bearer`. **Do NOT use `getOrganizationToken(organizationId)` here**
   — that returns a token with `aud == urn:logto:organization:<id>` (no resource aud), which the backend
   verifier REJECTS at the audience check (it passes `audience=LOGTO_API_RESOURCE` to `jwt.decode`). Only the
   two-arg `getAccessToken(resource, organizationId)` yields the `aud == https://api.famit.in` +
   `organization_id` token the verifier accepts. (citation: logto docs — `getAccessToken(resource, organizationId)`.)
Keep email/password→`/api/login` as the DEFAULT and visible; gate the Logto button on
`NEXT_PUBLIC_LOGTO_ENABLED`. **Accept:** with the flag off the panel is byte-identical to today; with it on,
a Logto login round-trips, the stored bearer token decodes with `organization_id` + `aud==https://api.famit.in`,
and the dashboard loads tenant-scoped data through it (`/me` returns the mapped tenant). Build with
`npm install --legacy-peer-deps && npm run build` (React 19). Model: sonnet. **Deploy per HANDOFF recipe.**

**STEP 8 — (LATER, not in this phase) cutover toggle.** Only once telemetry (`/me auth_source` counts /
access logs) shows zero legacy traffic: set `LEGACY_TOKEN_ENABLED=false`. Until then, leave it ON.
**Accept:** before flipping, a dashboard panel/log proves 0 `legacy` auths for N days. Model: opus + human
sign-off via AskUserQuestion.

---

## 6. `logto_provision.py` — CONTRACT (idempotent admin script, run manually)

Inputs (env): `LOGTO_ENDPOINT`, `LOGTO_M2M_APP_ID`, `LOGTO_M2M_APP_SECRET`, path to `var/tenants.json`.
Steps:
1. Get an M2M access token: `POST {LOGTO_ENDPOINT}/oidc/token` (client_credentials, `resource={LOGTO}/api`,
   `scope=all`).
2. For each tenant in `tenants.json`:
   - If `logto_org_id` already set → skip (idempotent).
   - `POST /api/organizations {name: tenant.name}` → capture `org.id`.
   - `POST /api/users {primaryEmail: tenant.email, name: tenant.name}` (or find existing) → `user.id`.
   - `POST /api/organizations/{org.id}/users {userIds:[user.id]}` (add member).
   - Assign org role: `POST /api/organizations/{org.id}/users/{user.id}/roles` with the role matching
     `tenant.role` (`admin|manager|agent`).
   - Write `tenant.logto_org_id = org.id` back; persist `tenants.json` (atomic write, keep a `.bak`).
3. Print a mapping table `tenant_id → logto_org_id` (no secrets).
**Safety:** read-modify-write `tenants.json` with a single backup `tenants.json.logtobak.<ts>`; never delete
fields; never set `is_admin`. Re-runnable.

> NOTE: `tenants.json` is currently authoritative. After P1.U7 lands (orgs/users in Postgres), this script's
> write target becomes the `orgs` table (`logto_org_id` column) instead — same logic, different store.
> Keep the script store-agnostic by routing through the same seam (`_read_tenants`/`_write_tenants` if run
> in-process, or the JSON file if run standalone).

---

## 7. FEATURE FLAGS + ROLLBACK (summary table)

| Flag (env) | Default | Effect | Where read |
|---|---|---|---|
| `LOGTO_ENABLED` | `false` | Master switch. False → `logto_verify` inert, `resolve_tenant` unchanged. | caller.py:96; wiring |
| `LOGTO_ENDPOINT` | `""` | Logto base URL (`https://auth.famit.in`). Empty → init returns False. | logto_verify.init |
| `LOGTO_API_RESOURCE` | `""` | API indicator for `aud` check. Empty → aud check skipped (still verifies sig+iss). | logto_verify.init |
| `LOGTO_JIT_PROVISION` | `false` | Auto-create tenant for unknown valid org (never admin). Off → unknown org = 401. | wiring |
| `LOGTO_JWKS_TTL` | `600` | JWKS cache seconds. | logto_verify.init |
| `LOGTO_JWKS_URI` | `http://127.0.0.1:3001/oidc/jwks` | RED-TEAM FIX #2: key-FETCH URL (localhost, no edge hairpin). `iss` still checked vs `LOGTO_ENDPOINT`. | caller.py:96; logto_verify.init |
| `LEGACY_TOKEN_ENABLED` | `true` | EXISTING. Keep TRUE through cutover; flip last. | caller.py:96 |

**Rollback (instant, no data undo):** `LOGTO_ENABLED=false` in `/opt/famit-agent/.env` →
`sudo systemctl restart famit-caller`. Legacy + HS256 paths were never removed, so callers are unaffected.
To fully remove: stop the Logto container; the `logto_org_id` fields are inert and harmless.

**Crash-safety:** every unit is independently revertible (file backups `*.logtobak.<ts>` on the box, git
commit per unit). The risky moment is STEP 6 (flag flip); its acceptance test asserts all THREE auth paths
simultaneously before commit, so a regression is caught in one curl, not in production traffic.

---

## 8. DEPENDENCIES

- **Python (backend venv `/opt/capsy-agent/.venv`):** `pyjwt[crypto] >= 2.4` (brings `cryptography` for
  RS256 + `PyJWKClient`). P0 already installed `pyjwt`; STEP 0 verifies/upgrades. `httpx` already present
  (provision script + JWKS fallback). NO new heavy deps.
- **Infra:** Docker + docker compose on `168.144.153.145` (LiveKit already uses Docker there — present).
  An external Postgres DB for Logto (DO Managed or a separate container w/ named volume).
- **DNS/Edge:** `auth.famit.in` A-record + Cloudflare + certbot. Needs the **re-scoped Cloudflare token**
  (founder blocker #6) for automated DNS; can be done manually in the dashboard otherwise.
- **Founder-provided (optional, non-blocking):** Google OAuth client id/secret (blocker #4) for social
  login — purely a console paste, zero code dependency.
- **Ordering dep:** independent of P1 Postgres EXCEPT the `logto_org_id` field, which should also be added
  to the P1 `orgs` table (U7) so the two migrations stay coherent. Logto can ship before or after P1.

---

## 9. MODEL ROUTING (for the implementing agent)

| Work | Model | Why |
|---|---|---|
| `logto_verify.py` + `resolve_tenant` seam + wiring (STEP 1, 6) | **opus** | Security-critical auth chokepoint; subtle RS256/JWKS/aud/org correctness; must be non-breaking. |
| Docker/compose/nginx/DNS/ufw (STEP 2,3) | **sonnet** | Mechanical infra following the documented pattern. |
| Logto console config (STEP 4) | **sonnet** | Click-ops + M2M API calls. |
| `logto_provision.py` + backfill (STEP 5) | **sonnet** | Straightforward Management-API CRUD + idempotent file write. |
| Frontend Logto login (STEP 7) | **sonnet** | Standard OIDC SPA/redirect wiring; delegate to the frontend coding agent per HANDOFF. |
| Cutover decision (STEP 8) | **opus** + human | Irreversible-ish flip; needs telemetry + AskUserQuestion sign-off. |
| One-time security review of the final diff | **opus** | Confirm no token-confusion (HS256 vs RS256), no aud bypass, JIT never mints admin. |

---

## 10. OPEN RISKS / NOTES (carry into implementation)

1. **Token confusion (CRITICAL):** ensure the Logto branch ONLY accepts RS256 (`algorithms=["RS256"]`) and
   the HS256 branch ONLY HS256 — never let a token verified by one be accepted by the other. They use
   different keys (JWKS RSA pub vs `var/secret`) so cross-acceptance is cryptographically impossible, but the
   `algorithms=` allow-lists must be explicit in BOTH modules. (auth.py already pins `["HS256"]`.) The opus
   security review (Section 9) must assert this.
2. **`aud` shape — STANDARDIZE on the org-API-resource token (`https://api.famit.in`).** That token carries
   `aud == https://api.famit.in` + `organization_id` + resource-scoped `scope` — exactly what the frontend
   (`getAccessToken(resource, orgId)`) and `resolve_token` (which decodes with `audience=_API_RESOURCE`) use.
   The pure-org (non-API) token (`aud = urn:logto:organization:<id>`, no `organization_id`) is the OTHER type;
   note that because `resolve_token` passes `audience=_API_RESOURCE` to `jwt.decode`, a pure-urn token is
   REJECTED at the audience check *before* the urn fallback runs — so the urn-parse branch is a defensive
   path only, NOT runtime dual-support. If you ever need to accept pure-org tokens too, set
   `LOGTO_API_RESOURCE=""` (verifier then skips the aud check and the urn fallback becomes live) — but the
   chosen, tested path is the API-resource token with the aud check ON.
3. **JWKS availability:** if Logto/JWKS is down, Logto-authed callers get 401 — but legacy + HS256 callers
   are unaffected (separate path). PyJWKClient caches keys; set `LOGTO_JWKS_TTL` sensibly. Fail-closed for
   Logto tokens is correct (don't trust an unverifiable token). **See RED-TEAM FIX #1**: the `iss`
   pre-filter is what keeps a kid-miss (or attacker token) from forcing a synchronous JWKS refetch on the
   event loop — without it "JWKS down" degrades EVERY request, not just Logto ones. FIX #2 fetches keys
   from localhost so a Cloudflare/edge blip doesn't break verification of locally-issued tokens.
4. **Admin-console exposure:** never expose `:3002` publicly without an IP allowlist; default to SSH tunnel.
   The initial admin account is created on first console visit — do that over the tunnel immediately so no
   one else can claim it.
5. **Bundled-PG footgun:** the public `docker compose -f - up` one-liner uses an EPHEMERAL bundled Postgres
   that is recreated (data-lost) on re-run. We MUST use an external DB (Section 4.1). This is the single
   biggest deployment mistake to avoid.
6. **Mapping authority during P1:** `tenants.json` is the join store today; after P1.U7 the `orgs` table
   gets `logto_org_id`. Keep `_tenant_by_logto_org` routed through the same `_read_tenants` seam so the
   store swap is transparent (it already is — `store.py` will back `_read_tenants`).
7. **Email/password still works without Logto:** the existing `/login` + `/auth/login` are untouched, so a
   tenant with no Logto org can still log in the old way. Logto adoption is per-tenant and gradual.
8. **Frontend dual-mode:** until STEP 7 ships, the panel keeps using `/api/login` + `X-Auth`. The Logto
   bearer flow is additive and flag-gated so a half-finished frontend never bricks login.

---

## RED-TEAM FIXES (folded)

Adversarial principal review against the LIVE source (`droplet_work/caller.py`, `auth.py`, `config.py`,
`P1_FOUNDATION_STATE.md`) and the canonical master plan. The spec's ground-truth was verified accurate
(every cited line number — `resolve_tenant:366`, `_extract_cred:352`, PW`:389`, hmac`:391`, flags`:96`,
defensive import`:70`, `_role_of:534`, `_auth_mod.init:637`, `/me:1773` — matches the real file; the
degrade pattern mirrors auth.py; `import secrets`/`datetime` exist at module scope for the JIT code;
`org_id==tenant_id` + "don't rewire resolve_tenant" is the P1 lock; Logto-as-Phase-4-IdP is the plan).
PyJWT API verified against docs: `PyJWKClient(uri, cache_keys, lifespan)` kwargs are real;
`jwt.decode(..., issuer=, audience=, algorithms=, options=, leeway=)` shape is correct. The following
**real** issues were folded in:

1. **[BLOCKING for flag-ON] JWKS hot-path DoS / latency regression — §3 `resolve_token`.** The Logto
   branch runs FIRST on EVERY request and filtered only on dot-count, so once `LOGTO_ENABLED=true`,
   every legacy P0 **HS256** token (2 dots, no `kid`) and any attacker `aaa.bbb.ccc` reached
   `get_signing_key_from_jwt()`, missed the kid, and forced a **synchronous outbound JWKS refetch on
   the event loop** (`resolve_tenant` is sync, called from async handlers) — per-request latency on the
   warm panel path + a **pre-auth unauthenticated DoS / loop-stall**. STEP 6 asserted 200 not latency,
   so it would have passed GREEN. FIX: decode unverified claims and **bail on `iss != _ISSUER` before any
   network call** (auth.py `_make_access` sets no `iss`, so legacy JWTs are filtered for free). Added
   `leeway=30` for clock skew.
2. **[latency/resilience] JWKS hairpin — §3 `init`, flags, §1.6.** Key fetch was `{ENDPOINT}/oidc/jwks`
   = backend → Cloudflare → panel nginx → VPC → the Logto container on the SAME backend box. FIX: split
   the public **issuer string** (token `iss`) from the **fetch URL**; new `LOGTO_JWKS_URI` defaults to
   `http://127.0.0.1:3001/oidc/jwks`. (Verify Logto serves jwks on localhost without 301→ENDPOINT; if it
   redirects, point the override at the panel-box VPC address instead.)
3. **[hidden coupling] IdP co-located with the TTFT-critical voice agent — §1.6, §4.2.** A Java/Node IdP
   + Postgres in CPU/RAM contention with `famit-agent` risks call-latency spikes (HANDOFF's #1 concern).
   FIX: `mem_limit: 1g` / `cpus: 1.0` on the Logto + PG containers, OR host Logto on the panel box and
   fetch JWKS over the VPC (FIX #2 enables this).
4. **[must-fix before enabling JIT] unlocked tenants.json write — §3 `_provision_tenant_from_logto`.**
   Read-modify-write from the sync request path with no `_STORE_LOCK` → concurrent first-hits for one org
   race into duplicate/lost rows. OFF by default (non-blocking now); enabling `LOGTO_JIT_PROVISION` is
   gated on routing through the locked seam (or making provisioning out-of-band). `pass_hash=""` noted
   VERIFIED-SAFE (not a bypass: `_hash_pw` never returns "", `is_admin` hard-False).
5. **[correctness, low-impact] role seed always "manager" — §3 `_extract_roles`.** Logto org tokens carry
   grants in `scope`, not a `roles` claim, so JIT role-mapping never saw a role. FIX: derive from `scope`
   when `roles` absent. (tenants.json stays authoritative for authZ, so impact is cosmetic until you lean
   on Logto for role — never auto-grant admin from a scope.)
6. **[test gaps the task named] STEP 6 extended** with four adversarial, MANDATORY-before-COMMIT tests:
   (a) 50× `/me` with an HS256 token under flag-ON asserts 200 **and a flat JWKS-fetch count** (proves
   #1); (b) `docker stop logto` → Logto token 401 while X-Auth + HS256 still 200 (failure-domain
   isolation); (c) alg-confusion negative (HS256-signed-with-RSA-pubkey rejected by both branches);
   (d) expired / unknown-org → 401 not silent-200. `health()` now exposes `jwks_fetches` + `jwks_uri`
   and probes with `refresh=False` so it can't pollute test (a). STEP 0 now also asserts the PyJWKClient
   kwargs construct without `TypeError` (else `init()` silently degrades to `_ready=False`).

**Residual risks accepted (not blockers):** JWKS single-point fail-closed for Logto tokens is *by design*
(legacy unaffected); the urn-aud fallback in `resolve_token` is dead code on the chosen API-resource path
(documented in §10.2, harmless); Logto container image tag must be PINNED in prod (`:latest` is a
supply-chain/repro risk — §4.2 already says pin it, enforce in review); external-DB discipline (§4.1/§10.5)
is operator-dependent and unverifiable from the spec. Founder blockers (Google OAuth, Cloudflare token)
remain non-blocking and code-independent.

### VERDICT (this subsystem)
- **GO — STEP 0–5 + STEP 1's flag-OFF no-op deploy.** The inert-when-`LOGTO_ENABLED=false` claim is
  sound: with the flag off, `LOGTO_JWT_READY` is False and the STEP-0 branch is a single boolean
  short-circuit → byte-for-byte today's behaviour. Infra steps (2–5) are correct with FIX #3's pin.
- **NO-GO — STEP 6 (flag flip) until FIX #1 + #2 and tests (a)/(b)/(c) are implemented and green.**
  These are folded into the spec above; the flip is safe ONLY with the `iss` pre-filter in place. Without
  #1, enabling Logto silently degrades panel latency and opens a pre-auth DoS.
- **GO — STEP 7 (frontend)** as written (the org-API-resource-token trap was already sealed) once the
  backend gate (STEP 6) is green.
- Mandatory opus security review of the final diff (§9) must additionally assert FIX #1's pre-filter is
  present and the `algorithms=` allow-lists are pinned in both modules.

---

## SOURCES (Logto specifics verified 2026-06; not from memory)
- Validate access tokens / FastAPI RBAC + JWT (JWKS, RS256, aud, scope): https://docs.logto.io/authorization/validate-access-tokens · https://docs.logto.io/api-protection/python/fastapi
- Organization-level API resources (org token claims: `organization_id`, `aud`, `urn:logto:organization:<id>`): https://docs.logto.io/authorization/organization-level-api-resources
- RBAC / organization roles: https://docs.logto.io/authorization/role-based-access-control
- Frontend FETCHES an organization token (`getOrganizationToken` / `getAccessToken(resource, organizationId)`, SDK init `resources` + `UserScope.Organizations` / `urn:logto:scope:organizations`): https://docs.logto.io/use-cases/multi-tenancy/build-multi-tenant-saas-application · https://docs.logto.io/authorization/organization-level-api-resources (Refresh token flow)
- OSS deployment + env (`DB_URL`, `ENDPOINT`, `ADMIN_ENDPOINT`, `TRUST_PROXY_HEADER`, ports 3001/3002, seed): https://docs.logto.io/logto-oss/deployment-and-configuration · https://docs.logto.io/logto-oss/get-started-with-oss · https://github.com/logto-io/logto/blob/master/docker-compose.yml
