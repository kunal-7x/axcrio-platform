# Control Plane — Security Threat Model + Admin-Plane Design

> **Scope:** the SECURITY of the Foundation Control Layer (Tier-0 Super-Admin control center).
> This is the sharpest knife in the platform: a leaked admin token = full-platform, all-tenant
> compromise. Companion to `design/spec-control-layer.md` (the architecture/build plan) and
> founder spec `Z.MD`. **READ-ONLY design wave — no app code, no deploy, no git.**
>
> **Grounded in the LIVE code** (not aspiration). Load-bearing references:
> - `droplet_work/caller.py:404` `resolve_tenant()` — tenant is derived from the TOKEN, never the body.
> - `droplet_work/caller.py:641` `can(tenant, "manage_tenants")` — the existing admin predicate; `/tenants` 403s non-admins (`caller.py:3043`).
> - `droplet_work/firewall.py` — PIN store (`var/pins.json`, salted sha256), HS256 step-up token **sub-bound to the caller (F3 anti-replay)**, `STEP_UP_TTL_S=300`, `FIREWALL_ENABLED` default OFF.
> - `droplet_work/auth.py` — HS256 access JWT (`sub/role/is_admin/jti`, 15-min TTL), revocable rotating refresh, `revoke_all(tenant_id)`.
> - `engine.session(tenant_id=X, is_admin=True)` — the admin-GUC that drives FORCE-RLS; immutable audit = the PG **`events`** leg (NOT the rotating JSONL).
>
> **Posture in one line:** the BACKEND is the only real boundary; everything fails CLOSED; cross-tenant
> power is a narrow, audited, step-up-gated, short-TTL capability — never an ambient property of "being admin".

---

## 0. ASSETS, TRUST BOUNDARIES, ATTACKERS (what we are protecting, from whom)

**Crown-jewel assets (ranked by blast radius):**
1. **Super-admin authority** — the ability to read/modify EVERY tenant. Compromise = whole platform.
2. **The act-as / impersonation capability** — lets an admin operate inside any vendor. Compromise = silent tenant takeover.
3. **The entitlement map** — the source of truth for who-can-do-what. Tamper = privilege escalation or revenue bypass (use a feature you didn't pay for).
4. **Per-tenant data rows** (leads/calls/transcripts/wallet) — already RLS-isolated; control adds new write paths that must not weaken this.
5. **The signing secret `var/secret`** — signs every access JWT, the legacy hmac token, AND the firewall step-up. One secret, three token families → its leak forges all of them.
6. **The immutable audit (`events` leg)** — the only record of who did what. Tamper/erase = no accountability.

**Trust boundaries:**
- Public internet → Cloudflare → nginx (`/api/*` strip) → uvicorn `caller.py`. **The boundary that matters is `resolve_tenant()` + the per-route gate inside caller.py.** nginx/Cloudflare are not authZ boundaries.
- Vendor token ⇄ Admin token: the SAME `/api` surface; the ONLY thing separating a vendor from cross-tenant power is the `is_admin` flag on the resolved tenant. **This flag is the entire admin boundary today** — §1 hardens it.
- caller.py ⇄ Postgres: FORCE-RLS keyed on the `app.tenant_id` GUC set by `engine.session()`. A SQL-level boundary UNDER the app boundary (defense in depth).
- caller.py (livekit box) ⇄ Logto (hatchet box, over VPC `10.122.0.3:3001`): the future authZ authority (admin-org membership + scopes). JWKS fetched over the private VPC only.

**Attackers we design against:**
- **A1 — Malicious/curious VENDOR** with a valid vendor token: tries to reach `/admin/*`, forge another tenant in a request body, hit a hidden feature's route directly, or read another vendor's data.
- **A2 — Leaked ADMIN credential** (the legacy `FamitCall2026` password, or a stolen admin JWT/refresh): the catastrophic case. Goal of design: minimize what a single leaked admin secret can do, make it loud, make it short-lived, make it revocable.
- **A3 — Insider admin going rogue / fat-fingering** (the founder is the only admin today, but design for a future support team): act-as abuse, mass-suspend, silent data reads. Mitigation = mandatory audit + read-only-default + step-up.
- **A4 — Client-side bypass** (devtools, saved token replay, crafted curl): defeats any frontend-only HIDE/LOCK.
- **A5 — Token/secret thief** who exfiltrates `var/secret`, `var/pins.json`, or `var/tenants.json`.

---

## 1. ADMIN-PLANE GATING — `/admin/*` cross-tenant power, unreachable by any vendor

### 1.1 The boundary today (and its single weakness)
Cross-tenant power is gated SOLELY by `tenant.is_admin` resolved in `resolve_tenant()` (`caller.py:404`),
checked via `can(tenant,"manage_tenants")` / inline `if not t.get("is_admin"): 403` (`caller.py:3043,3058,3222,3243`).
Every existing `/tenants*` route already 403s a vendor. The pattern WORKS — but it rests on `is_admin`,
and `is_admin` is conferred TWO ways:
1. The tenant record `admin` has `is_admin:true` (legitimate).
2. **The legacy bare password `FamitCall2026` → admin tenant** (`caller.py:427` `if cred == PW: return admin`).

**🚨 THE #1 ADMIN-PLANE RISK: the shared static legacy password IS an admin bearer token.** Anyone who
ever saw it (it is in HANDOFF.md, in deploy recipes, typed at the panel login) holds permanent, un-rotatable,
un-revocable, un-audited super-admin. This is A2 made trivial. **Hard requirement before `/admin/*` ships:**

- **Demote the legacy password OFF the admin plane.** `cred == PW` may keep authenticating for *backward
  compatibility of the EXISTING vendor-grade routes* (so the live panel doesn't break), but it MUST NOT
  satisfy the `/admin/*` gate. The `/admin/*` gate requires a stronger predicate (`is_super_admin`, below)
  that the bare password does NOT confer. Concretely: `resolve_tenant` tags HOW the admin authenticated
  (`auth_method ∈ {jwt, legacy_pw, hmac}`); the admin-plane gate rejects `legacy_pw`.
- Better: flip `LEGACY_TOKEN_ENABLED=false` for the admin path entirely once the founder logs in via the
  JWT flow (`auth.login`). The flag already exists (`caller.py:410`). Keep legacy ON only for vendor routes
  during transition, OFF for `/admin/*` always.

### 1.2 The hardened admin gate — `require_super_admin` (the ONE choke point)
A single dependency every `/admin/*` route uses (mirrors the existing `can()` shape so it's a drop-in):

```
def require_super_admin(request) -> tenant | raise 403:
    t = resolve_tenant(request)                      # token-derived, never body
    if t is None:                       raise 401     # unauthenticated
    if not _is_super_admin(t, request):  raise 403    # NOT "404" — see §1.4 note
    return t

def _is_super_admin(t, request) -> bool:
    # Phase 1 (today's primitives):  is_admin == True  AND  auth_method != "legacy_pw"
    # Phase 2 (Logto lands):         membership in the Logto ADMIN ORG  AND  the
    #                                access token carries scope "manage_tenants"
    #                                (org-role -> scope, verified against JWKS over the VPC)
    ...
```

- **Phase 1 (ship now):** `is_admin AND auth_method in {jwt, hmac-of-admin}` — the bare password is excluded.
- **Phase 2 (when Logto integration lands — `brain/auth-logto.md`):** authority = **membership in the Logto
  admin org + a `manage_tenants` scope claim in the access token**, verified against Logto JWKS
  (`http://10.122.0.3:3001/oidc/jwks` over the VPC). `is_admin` on the tenant record becomes a cache of
  org membership, not the source of truth. This makes super-admin a *revocable org membership* (remove the
  user from the admin org → instant loss of power) instead of a boolean baked in a record.

**Every `/admin/*` route — and ONLY `/admin/*` routes — call `require_super_admin`.** No exceptions, no
per-route re-implementation (re-implementation is how one route forgets the gate — the `manage_tenants`
predicate is centralized for exactly this reason). A vendor token → **403 on every `/admin/*` path**.

### 1.3 The backend middleware IS the boundary — HIDDEN=404, LOCKED=402, fail-closed
Per `spec-control-layer.md §3`, a FastAPI dependency maps request path → `feature_key` (via
`feature_registry.api_prefixes`) → `assert_access(tenant, key)`:
- `hidden` → **404** (indistinguishable from "route doesn't exist" — no information leak that the feature exists).
- `locked` → **402** `{error:"locked", feature, upgrade:true}` (the UI renders the upsell overlay).
- `on` → proceed. Core routes (`/login`, `/me`, `/health`, `/auth/*`, wallet-PAY) BYPASS (or a misconfig
  bricks login — the `is_core` floor).
- **Unknown path / unmapped feature / missing plan / resolver error → DENY (404).** Fail-closed is the
  default branch, not an afterthought. A bug must drop access, never grant it.

**This middleware is the real lock. Frontend HIDE/LOCK is cosmetic.** A saved vendor token curling `/calls`
when `calls` is hidden MUST get 404 from this layer — the nav being gone is irrelevant. **Acceptance test:**
set a feature `hidden`, replay a raw token at its route → 404; set `locked` → 402; `on` → 200; `/login`
always 200. (See §6 test plan.)

### 1.4 Why `/admin/*` returns 403 (not 404) but hidden FEATURES return 404
Subtle but deliberate: the EXISTENCE of an admin plane is not a secret (it's a SaaS; admins obviously exist),
so `/admin/*` → **403** for a vendor is fine and clearer. But a *hidden feature* inside a vendor's own plane
returns **404** so the vendor cannot enumerate which features exist-but-are-withheld (that's an info leak that
fuels "why don't I have X" social-engineering and competitive intel). Two different leak surfaces, two codes.

### 1.5 Admin-plane hardening checklist
- `/admin/*` mounted under ONE router with `dependencies=[Depends(require_super_admin)]` so a new route
  cannot be added without the gate (router-level, not per-handler).
- The legacy password is excluded from the admin plane (§1.1).
- Admin access JWTs are SHORT-TTL (15 min, already the `auth.py` default) — a stolen admin access token
  dies fast; the refresh is revocable (`auth.revoke_all`).
- **Admin reads are cross-tenant ONLY through the dedicated `/admin/*` routes**, which are themselves
  audited (§4). There is no "admin happens to see everything" ambient path — every cross-tenant read is a
  named, logged route.
- Rate-limit `/admin/*` and especially `/admin/*/impersonate` (the existing P0 rate-limiter on :6380 covers it).

---

## 2. IMPERSONATION / ACT-AS — the sharpest knife, gated like root

The founder asked to "see vendor data." Naive impersonation (admin silently assumes a vendor identity) is a
silent-takeover primitive and an audit black hole. The controlled design:

### 2.1 The act-as token (short-TTL, scoped, attributable, distinct from a normal token)
`POST /admin/vendors/{id}/impersonate` returns a **dedicated act-as access token** — NOT a normal vendor
token — minted by extending `auth._make_access` with extra claims:
```
{ sub: <vendor tenant_id>,          # so RLS/handlers scope to the vendor's data
  act_as: <vendor tenant_id>,       # explicit marker: this is an impersonation
  real_admin: <admin tenant_id>,    # WHO is really behind the wheel (for audit + writes)
  amr: "act_as",
  scope: "read_only" | "read_write",# DEFAULT read_only
  type: "access",
  exp: now + ACT_AS_TTL (≤ 10 min, SHORTER than a normal 15-min token),
  jti: ... }
```
- **`sub` = the vendor** (so the existing tenant-scoped readers and RLS naturally show vendor data — no new
  cross-tenant read path is invented; we ride the proven isolation).
- **`real_admin`** travels in every request so the server NEVER loses track of who the human actually is.
- The token is recognizably an act-as token (`act_as` claim) so the middleware and audit treat it specially.

### 2.2 Five mandatory controls on act-as
1. **Firewall PIN step-up to ENTER.** `/admin/vendors/{id}/impersonate` is gated by `firewall.require_step_up`
   (scope `destructive` or a new `impersonate` scope). Reuses the EXISTING machinery verbatim — the step-up
   token is sub-bound to the admin (F3), so a leaked step-up token from one admin can't be replayed by another.
   (`FIREWALL_ENABLED` must be ON for the admin plane even though it's OFF for vendors today.)
2. **Read-only by DEFAULT.** `scope:"read_only"` unless the admin explicitly elevates (a second, separately-
   audited step-up). In read-only mode the act-as token is REJECTED by every mutating route (the middleware
   checks `if claims.amr=="act_as" and claims.scope=="read_only" and method in {POST,PUT,DELETE,PATCH}: 403`).
3. **Persistent on-screen banner.** The vendor frontend, on seeing an `act_as` token, renders a non-dismissible
   banner: *"You are viewing <Vendor> as Super-Admin <name> — READ ONLY. Exit act-as."* (Backend stamps a
   response header `X-Act-As: <vendor>` so the banner can't be suppressed by tampering with localStorage.)
4. **Both ENTER and EXIT audited** (§4) with `actor=real_admin`, `target=vendor`, scope, and TTL. Exit is an
   explicit `POST /admin/act-as/exit` that revokes the act-as token's session; a TTL expiry also writes an
   audit "act-as expired" row (so a forgotten session is still bounded + recorded).
5. **Writes-while-impersonating are attributed to the ADMIN, never silently to the vendor.** If `read_write`
   is granted, any mutation made under the act-as token is audited as `actor=real_admin (acting as <vendor>)`.
   The vendor's own audit trail shows "modified by Super-Admin", not a forged self-edit. No silent ghost-writes.

### 2.3 Act-as abuse cases closed
- **Privilege climb via act-as:** an act-as token's `sub` is a VENDOR → it CANNOT reach `/admin/*`
  (`require_super_admin` sees `act_as`/non-admin `sub` → 403). You cannot impersonate your way back up to admin.
- **Act-as another admin:** impersonating a tenant that is itself `is_admin` is BLOCKED (you can only act-as a
  vendor; admin-on-admin act-as is refused) — prevents lateral admin takeover.
- **Forgotten session:** ≤10-min TTL + the exit-audit-on-expiry bounds it. No indefinite shadow sessions.
- **Replay of the act-as token after exit:** exit revokes the session id (reuse the `revoke_all`/session
  machinery in `auth.py`), so a captured act-as token is dead after explicit exit.

---

## 3. TENANT ISOLATION UNDER THE NEW WRITE PATHS

The new control layer adds the FIRST cross-tenant WRITE routes the platform has had. Isolation must hold.

### 3.1 `tenant_id` is ALWAYS token-derived, never from the body — including the admin case
The platform's load-bearing invariant (proven by every prior isolation probe) is `resolve_tenant()` reading
the token, never a `tenant_id` in the request body/header. The control layer's twist: an admin route LEGITIMATELY
targets *another* tenant (e.g. `PUT /admin/vendors/{id}/status`). The rule:
- The ACTOR is always token-derived (`require_super_admin`).
- The TARGET (`{id}` in the path) is allowed cross-tenant **only because the caller passed `require_super_admin`**
  — and the engine writes scoped to that explicit path id, audited with both actor and target.
- A **vendor** route NEVER reads a tenant id from the body. The forge-tenant-B-while-authed-as-A probe
  (§6) must PASS — authed as vendor A, a `tenant_id:B` in the body is IGNORED; the write lands on A or 403s.
- `/me/entitlements` derives the tenant from the token ONLY — there is no `?tenant_id=` parameter. An admin
  who wants vendor B's entitlements uses `/admin/vendors/B`, which is audited; there is no unaudited self-serve
  cross-tenant read.

### 3.2 New tables ship with FORCED RLS, P1 shape
`tenant_entitlements`, `plan_entitlements` (plan-scoped, see note), `control_audit` (rides `events`), and the
tenant-record extensions all ship with the SAME `FORCE ROW LEVEL SECURITY` + `app.tenant_id` GUC policy as the
P1 keystone (`db/rls.sql` style — **explicit per-table ALTER/CREATE POLICY, ZERO `%` chars, NO `DO $$ format('%I')`
loop**, per the `mistakes.md` DDL trap that silently yields no tables). So even a control-layer app bug cannot
cross tenants at the ROW level — RLS is the floor under the app gate.
- `tenant_entitlements`: RLS keyed on `tenant_id` (a vendor reading its own row sees only its own; admin-GUC
  sees all). `plans`/`plan_entitlements` are GLOBAL catalog (not tenant-scoped) → readable by all authed
  tenants (read-only), writable ONLY via `/admin/*` (app-gated); they hold no tenant data so RLS-by-tenant
  doesn't apply, but they are REVOKE'd from the vendor-write path.
- `feature_registry` is global read-only catalog — same treatment.

### 3.3 Cross-tenant write cannot happen via the entitlement ENGINE's cache either
`entitlements.resolve_modes(tenant_id)` is cached per-tenant (in-proc dict + version). The cache key is the
tenant id; a write for tenant B bumps B's version only. No shared mutable map that a B-write could leak into an
A-response. (Cache poisoning check is in §6.)

### 3.4 The new write that touches MONEY/STATUS clears the firewall
`POST /admin/vendors/{id}/credits` (wallet top-up/freeze) and `PUT /admin/vendors/{id}/status` (suspend/disable)
are spend/destructive → gated by `firewall.require_step_up` (scopes `spend` / `destructive`). Plan change
(`billing.plan_change`) is already in `firewall._DESTRUCTIVE_ACTIONS`. Money and lifecycle changes always clear
the PIN gate, on top of `require_super_admin`.

---

## 4. IMMUTABLE AUDIT OF EVERY PERMISSION CHANGE

### 4.1 What is logged, and where
Every super-admin write — flag flip, plan assign, per-vendor override, status change, credit move, impersonate
enter/exit — appends an `events` row, **channel `control`**:
```
{ channel:"control", ts, actor_tenant, actor_user, auth_method,
  action,                         # e.g. "entitlement.override.set"
  target_tenant, feature_key,
  old_value, new_value,           # BEFORE and AFTER — both required
  reason, scope, ip, request_id,
  act_as: <vendor|null> }         # set when the actor was impersonating
```

### 4.2 Immutability is REAL, not aspirational
**🚨 The immutable leg is the append-only PG `events` table, NOT the rotating/mutable JSONL** (`mistakes.md`
2026-06-10: "audit recorded must be checked on the IMMUTABLE leg, not the convenient one"; the JSONL rotates).
Controls:
- `events` is append-only; the app role has INSERT (no UPDATE/DELETE grant) on it.
- The control-audit page (`/admin/audit`) is READ-ONLY (`GET /audit?channel=control` — the filter already
  exists). No route can edit/delete an audit row.
- **Verify on the PG leg, not the JSONL.** When proving "the override write was audited," SELECT FROM `events`
  via the admin GUC and confirm the row — do NOT grep the JSONL reader (it can lag/rotate and gave a false
  "audited" signal once already).
- BEFORE/AFTER are MANDATORY. An audit row without `old_value`+`new_value` is rejected at write time (you must
  be able to reconstruct the full state history from the log alone — "who watches the admin").

### 4.3 Who watches the admin
Single-admin today, but designed for a team: every `/admin/*` write is logged with `actor_user`; act-as writes
carry `real_admin`. For a multi-admin future the schema already supports `set_by` + an optional second-admin
approval gate on the most destructive ops (mass-suspend, credit-freeze, tenant.delete) — a config flag, not a
rebuild. The audit is the accountability backstop FOR the admins, not just for the vendors.

---

## 5. SUSPENSION ENFORCEMENT (login / call / create blocked; data preserved)

### 5.1 The status floor in the resolution rule (fail-closed at the top)
Per `spec-control-layer.md §2`, the resolution rule's FIRST clause: `tenant.status in
(suspended,disabled,expired)` → EVERYTHING hidden except `is_core`. This is enforced in the backend
middleware (§1.3), so a suspended tenant's saved token gets 404/402 on every feature route regardless of the
frontend. Specifics:
- **Login:** `suspended`/`disabled` → `/login` and `/auth/login` REFUSE to mint a token
  (`{error:"account suspended"}`, 403). A suspended vendor cannot get a fresh token. **And** any EXISTING
  refresh/access tokens are revoked on suspension (`auth.revoke_all(tenant_id)` — already implemented) so a
  token minted seconds before the suspend is killed, not left valid for 15 minutes.
- **Call / run:** the run-loop gate checks `status` BEFORE dispatching new dials. `suspended` → no NEW dials;
  **in-flight calls are allowed to FINISH** (data integrity + no half-charged calls), per `spec §8.2`.
  `disabled` is harder (also blocks login). This gate is at the `/run` + dial-loop layer, not the voice hot
  path (`agent.py` is never touched).
- **Create:** all mutating routes (`POST /campaigns`, `/leads`, etc.) → 402/404 via the status floor.
- **DATA PRESERVED:** suspension flips a `status` field and revokes tokens. It NEVER deletes rows. Reads by the
  ADMIN (via `/admin/*`) still work; the vendor simply cannot authenticate. Un-suspend = flip status back; the
  data was untouched. (Mirrors the wallet "data remains, balance frozen" precedent.)

### 5.2 The suspension propagation trap (a real bite, pre-empted)
**🚨 `mistakes.md` documents a recurring timing bug:** a write to suppression/state did not propagate to an
in-RAM read in the dial loop fast enough, so a "should-be-blocked" action still fired. The SAME class of bug
threatens suspension: suspend tenant → a dial loop that cached `status` at job-start keeps dialing. **Mitigation:**
the dial loop re-reads `status` (or the entitlement version) per-lead, not once per job; AND token revocation
(`revoke_all`) is the authoritative kill (the next API call by that tenant 401s immediately even if the run-loop
lags by one lead). The API-layer kill is instant; the run-loop "finish in-flight" is intentional, not a lag bug —
but the distinction must be tested (suspend → confirm NO new job can start + existing call record untouched).

---

## 6. ISOLATION + IMPERSONATION TEST PLAN (the probes that gate "ship it")

> Run BEFORE flipping `CONTROL_ENABLED` on. Each is a hard PASS/FAIL. Reuse the existing isolation-probe
> harness (the one that PASSED on every prior module activation). Where a real vendor JWT can't be minted
> in-shell (the Doppler-secret trap, `mistakes.md`), call the LIVE predicate directly
> (`can(...)`, `require_super_admin`'s `_is_super_admin(...)`) rather than chasing a real HTTP 403.

| # | Probe | Setup | PASS criteria |
|---|---|---|---|
| **T1** | Vendor → `/admin/*` denied | Vendor A token hits EVERY `/admin/*` route (GET+mutating) | **403** on all (401 if unauth). Zero data returned. |
| **T2** | Legacy password excluded from admin plane | `X-Auth: FamitCall2026` hits `/admin/vendors` | **403** (`auth_method=legacy_pw` rejected), even though it still authenticates vendor-grade routes. |
| **T3** | Forge-tenant-B-while-authed-as-A (the canonical probe) | Authed as vendor A, send `tenant_id:B` / `target:B` in BODY to every `/me/*` and vendor route | Write/read stays A-scoped; B in body IGNORED or 403. B sees nothing. Run on EVERY new `/admin/*` + `/me/entitlements` route. |
| **T4** | Hidden feature → 404 via raw token | Set feature `hidden` for tenant; replay a saved token at its route (curl, no frontend) | **404** (not 403, not 200). Nav-absence is irrelevant; the API is the lock. |
| **T5** | Locked feature → 402 | Set feature `locked`; hit its route | **402** `{error:"locked",upgrade:true}`. |
| **T6** | Core floor un-hideable | Attempt to set `login`/`settings`/`/auth/*`/wallet-pay `hidden` | Rejected (is_core), OR if forced, those routes STILL 200 (the bypass list holds). No self-lockout. |
| **T7** | Fail-closed on unknown | Hit a route whose feature_key is missing from the registry / resolver throws | **DENIED (404)**, never 200. |
| **T8** | RLS floor under the app | As `famit_app` WITHOUT the admin GUC, `SELECT * FROM tenant_entitlements` for another tenant | 0 rows (FORCE-RLS). With `engine.session(tenant_id=X)`: only X's rows. With admin GUC: all. |
| **T9** | Act-as enter requires step-up | `POST /admin/vendors/{id}/impersonate` WITHOUT `X-Step-Up` | **403 step-up required**. With a step-up token bound to a DIFFERENT admin (F3) → **403 identity mismatch**. |
| **T10** | Act-as is read-only by default | With a `read_only` act-as token, attempt any POST/PUT/DELETE on the vendor | **403**. GET works. |
| **T11** | Act-as can't climb to admin | With an act-as token (sub=vendor), hit `/admin/*` | **403**. Cannot impersonate your way to super-admin. |
| **T12** | Act-as can't target an admin | `POST /admin/vendors/<an-admin-tenant>/impersonate` | Refused. No admin-on-admin act-as. |
| **T13** | Act-as audited both ends | Enter, then exit (or let TTL expire) | TWO `events` rows (enter+exit), `actor=real_admin`, `target=vendor`, on the IMMUTABLE PG leg (verify via admin-GUC SELECT, not JSONL). |
| **T14** | Permission-change audited with before/after | Flip a flag / set an override | `events` row channel=control with non-null `old_value`+`new_value`; row is INSERT-only (no UPDATE/DELETE grant). |
| **T15** | Suspension kills tokens instantly | Suspend tenant A | A's next API call → 401 (refresh revoked); NO new `/run` job starts; an in-flight call record is untouched; A's rows still readable by admin. Un-suspend → A works again, data intact. |
| **T16** | Entitlement cache not cross-tenant | Flip B's flag, immediately read A's `/me/entitlements` | A's version/modes UNCHANGED (no shared-cache bleed). |
| **T17** | Resting-state byte-identical | With CONTROL_ENABLED off / every tenant on default plan + empty overrides + status=active | `/campaigns /leads /me` responses byte-identical to pre-control (the F2/F4 "resting state" proof). |
| **T18** | AI Copilot honors entitlements | With `billing` locked, ask the Copilot "show billing" | Polite refusal, NO data leaked. Copilot reads `/me/entitlements` and gates in the tool/prompt layer (it is NOT a side channel). |

**Gate:** T1–T18 all PASS, and the resting-state proof (T17) holds, before `CONTROL_ENABLED=true`. The
enforcement middleware stays behind that flag (default OFF) until the full smoke passes (per `spec §11`).

---

## 7. SECRET / KEY HYGIENE (the substrate every token rests on)
- **`var/secret` signs three token families** (access JWT, legacy hmac, firewall step-up). Its leak forges all
  three → it is the platform's single most sensitive file. Keep `0600`, never in git (the P0 gitleaks gate is
  in place), never logged. **Consider splitting the step-up signing key from the access-token key** so a
  step-up-token compromise doesn't imply access-token forgery (low effort, high containment — recommended).
- `var/pins.json`, `var/tenants.json`, `var/refresh_tokens.json` → `0600`, gitignored, on the hardened box only.
- Admin access tokens stay 15-min TTL; act-as tokens ≤10-min; step-up 5-min — short fuses everywhere on the
  admin plane.
- On any suspected admin-credential leak: rotate `var/secret` (invalidates ALL tokens platform-wide — a
  deliberate big-hammer kill switch) + `auth.revoke_all` per admin + force re-login. Document this runbook.

---

## 8. RESIDUAL RISKS / EXPLICITLY OUT OF SCOPE (honest call-outs)
1. **The legacy password keeps authenticating VENDOR-grade routes during transition** (only the admin plane
   excludes it). Until `LEGACY_TOKEN_ENABLED=false` platform-wide, a leaked `FamitCall2026` still grants
   vendor-level admin-tenant access to non-`/admin` data. Mitigation: it's excluded from the dangerous plane
   now; full retirement is a fast-follow once the founder uses JWT login. **Flagged, not hand-waved.**
2. **Single shared signing secret** across token families (§7) — split recommended, not yet done.
3. **Logto integration is the Phase-2 authority** but caller.py integration is a LATER unit; Phase 1 leans on
   `is_admin + auth_method`. Acceptable because Phase 1 already excludes the bare password and short-TTLs
   everything; Phase 2 upgrades authority to revocable org membership.
4. **Real-time propagation is poll-based (≤30s UI lag)** — acceptable because the API denies a revoked feature
   IMMEDIATELY (the poll is UI-freshness only, not the security boundary). Don't claim "instant" UI.
5. **Feature-registry drift** (a new module that forgets to self-register defaults to ungoverned `on`) — the CI
   check (every nav href + router prefix has a registry row) is the control; until that CI lands, a new route
   could be born outside the control plane. Track it.

---

## SUMMARY (15 lines)
1. The control plane is the platform's sharpest knife: a leaked admin token = total, all-tenant compromise — design accordingly.
2. **The #1 finding: the legacy static password `FamitCall2026` is a permanent, un-revocable admin bearer token** — it MUST be excluded from the `/admin/*` plane (and retired platform-wide soon).
3. Cross-tenant power is gated by ONE centralized `require_super_admin` (Phase 1: `is_admin` + non-legacy auth; Phase 2: Logto admin-org + `manage_tenants` scope), unreachable by any vendor token (403).
4. The BACKEND middleware is the only real boundary: HIDDEN→404 (no info leak), LOCKED→402, unknown→DENY — fail-closed everywhere. Frontend HIDE/LOCK is cosmetic.
5. `/admin/*` returns 403 (existence isn't secret); a hidden FEATURE returns 404 (so vendors can't enumerate withheld features) — two leak surfaces, two codes.
6. Impersonation is gated like root: firewall PIN step-up to enter, short-TTL act-as token (`sub=vendor`, `real_admin`, `scope`), read-only by default, persistent banner, enter+exit audited, writes attributed to the admin.
7. Act-as cannot climb to admin (sub=vendor → 403 on `/admin/*`) and cannot target another admin (no lateral takeover).
8. `tenant_id` stays token-derived everywhere; admin routes target the path `{id}` ONLY because they passed `require_super_admin`, and every such cross-tenant touch is audited.
9. The forge-tenant-B-while-authed-as-A probe must PASS on every new `/admin/*` and `/me/entitlements` route.
10. New tables (`tenant_entitlements`, audit, plan catalog) ship with FORCE-RLS in the P1 shape — explicit per-table policy, ZERO `%`/`DO format('%I')` (the silent-no-tables DDL trap), so RLS is the floor under the app gate.
11. The immutable audit is the append-only PG `events` leg (channel `control`), NOT the rotating JSONL — verify there; every permission change logs actor/target/before/after/time, INSERT-only.
12. Suspension revokes tokens instantly (`auth.revoke_all` → next call 401), blocks new dials at the run-gate (in-flight calls finish), blocks creates — and PRESERVES all data (status flip, never a delete).
13. The suspension/propagation timing trap (`mistakes.md`) is pre-empted: API-layer token revocation is the instant kill; the run-loop re-reads status per-lead.
14. Secret hygiene: `var/secret` signs all three token families (its leak forges everything) → split the step-up key, keep 0600, and a rotate-secret + revoke-all runbook is the leak kill switch.
15. T1–T18 isolation/impersonation probes gate `CONTROL_ENABLED`; resting state stays byte-identical until the flag flips (F2/F4 discipline).

## TOP 5 CONTROLS
1. **`require_super_admin` as the ONE centralized `/admin/*` gate** — `is_admin` + non-legacy auth now, Logto admin-org + `manage_tenants` scope next; the legacy password is EXCLUDED from this plane (closes the catastrophic shared-static-admin-credential hole). Vendor token → 403 on every `/admin/*`.
2. **Backend enforcement middleware as the real boundary, fail-closed** — path→feature_key→`assert_access`: HIDDEN→404, LOCKED→402, unknown/error→DENY, core routes bypass. Frontend is cosmetic; a saved token/curl/devtools cannot reach a hidden feature.
3. **Impersonation gated like root** — PIN step-up to enter (sub-bound, F3 anti-replay), short-TTL act-as token carrying `real_admin`, READ-ONLY default, persistent banner, enter+exit audited, writes attributed to the admin, cannot climb to or target an admin.
4. **Token-derived tenant + FORCE-RLS on every new table** — actor always from the token (never the body), admin cross-tenant only via audited `/admin/*` path-id, new tables RLS-isolated in the proven P1 shape; the forge-B-as-A probe PASSES on every new route.
5. **Immutable, complete audit on the PG `events` leg** — every permission change logs actor/target/before/after/time, INSERT-only (no UPDATE/DELETE grant), read-only audit page, act-as carries `real_admin`; suspension revokes tokens instantly while preserving all data.
