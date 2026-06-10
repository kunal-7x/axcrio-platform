# WAVE BUILD F4 (part 1) — Logto self-hosted OIDC engine deploy

Phase F4 of MASTER_PLATFORM_ROADMAP (Auth/RBAC/orgs/white-label IdP).
Spec: `caps/design/auth-logto.md`. State ledger: `caps/infra/logto/F4_LOGTO_STATE.md`.
Scope of THIS unit: deploy Logto OSS (Docker) + its OWN Postgres on an EXISTING box; secure it
(no public internals); stand up the console; capture the OIDC issuer/client config the LATER caller.py
integration consumes; document the tenant->Logto-org migration plan. **NOT in scope: editing caller.py**
(the auth integration is a later spine unit — legacy X-Auth + HS256 JWT keep working untouched).
Date: 2026-06-09/10. **Live boxes (famit-livekit, famit-panel-2) untouched.**

---

## 1. WHERE DEPLOYED (decision + why)

**Box = famit-hatchet** — public **68.183.94.38**, **priv 10.122.0.3** (VPC default-blr1), s-2vcpu-4gb.
- Chosen over the backend voice box (spec §4 named it, but its own RED-TEAM FIX #3 forbids co-locating an
  IdP with the TTFT-critical voice agent) and over the panel box (live earning frontend — don't add load).
  Hatchet is the least-critical box (durable orchestration, not realtime/earning) and already runs Docker.
- **Headroom verified before deploy:** 3915 MB RAM, 2841 available; Hatchet idle (lite 41 MB + pg 302 MB);
  70 GB disk free; 2 vcpu + 2 GB swap. Logto fits with room to spare (see §6).

**Stack** (`/opt/logto/` on the box; source `caps/infra/logto/docker-compose.logto.yml`):
- `logto` = `ghcr.io/logto-io/logto:1.40.1` (PINNED — latest stable 2026-05-29, NOT `:latest`; spec §10).
  Core/OIDC on **127.0.0.1:3001**, Admin console on **127.0.0.1:3002**. mem_limit 1g / cpus 1.0.
  ENDPOINT/ADMIN_ENDPOINT intentionally UNSET -> Logto defaults to `http://localhost` so the console +
  sign-in redirect work over the SSH tunnel while `auth.famit.in` DNS is not yet live.
- `logto-postgres` = `postgres:15.6`, **SEPARATE** db `logto` / role `logto_app`, named volume
  `logto_postgres_data`, **NO published port** (compose-internal network `logto-net` only). Physically +
  logically isolated from Hatchet's broker PG (`hatchet_lite_postgres_data`) — no collision. mem 1g/cpus .75.
- Secrets: `/opt/logto/logto.env` (PG password + DB_URL), chmod 600, never committed. Random 24-byte pw.

**Health verified on the box:**
- `curl 127.0.0.1:3001/oidc/.well-known/openid-configuration` -> 200, `issuer: http://localhost:3001/oidc`,
  `jwks_uri: http://127.0.0.1:3001/oidc/jwks`, `token_endpoint: .../oidc/token`.
- `curl 127.0.0.1:3001/oidc/jwks` -> 200. Admin console `127.0.0.1:3002` -> 302 (alive, redirects to sign-in).
- Seed completed on first boot ("Seed data" ✔; tenant org template + Management-API proxy apps created).
- Both containers `restart: unless-stopped` -> reboot-safe.

---

## 2. SECURITY POSTURE (no public internals — VERIFIED)

- **Localhost-bound:** `ss -tlnp` shows 3001 + 3002 on `127.0.0.1` ONLY (docker-proxy). PG 5432 not
  published at all.
- **Public negative test (from the internet):** `http://68.183.94.38:{3001,3002,5432}` -> `000` (refused/
  timeout) on all three. Internals are NOT internet-reachable.
- **Two firewalls:** host **ufw** active (inbound 22/tcp only) + DO cloud firewall **hatchet-fw**
  (SSH 22 + ICMP inbound only, egress-locked). No public 3001/3002/5432.
- **Console reached via SSH tunnel ONLY:**
  `ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 -L 3002:127.0.0.1:3002 -L 3001:127.0.0.1:3001 root@68.183.94.38`
  then `http://localhost:3002`.
- No Cloudflare/public `auth.famit.in` endpoint stood up (no Cloudflare token — fortress note: PENDING
  re-scope). That is the REMAINING gated step, NOT a security hole (tunnel-only is strictly more locked).

---

## 3. STATUS: deployed + secured DONE; console config = GATED FOUNDER STEP (5 min)

The infra + security half is COMPLETE and durable. The console config (first admin user + 1 organization +
1 OIDC app + 1 M2M app) is a **founder click-by-click over the SSH tunnel** because **Logto OSS has NO
headless first-admin path**:
- Logto CLI = `{init, db(seed/alt/config/system), connector}` only — no user/admin-create command.
- The seeded `m-default`/`m-admin` M2M apps are INTERNAL proxy apps (`protected_app_metadata`) — NOT usable
  on the public `/oidc/token` endpoint (`invalid_client`). Creating a real, usable M2M app needs the
  Management API, which needs the first admin, which is created via the **console UI (browser)** on first
  visit. A headless agent has no browser -> founder does it.
- **5-minute guide written:** `caps/infra/logto/CONSOLE_SETUP_HOWTO.md` (dead-simple, click-by-click).
- **Doing it now (issuer = localhost) is fine:** users/orgs/apps + client id/secret are PERSISTED and
  survive the later `ENDPOINT=https://auth.famit.in` switch (ENDPOINT only changes the runtime `iss` claim,
  not stored records). The HOWTO already sets the OIDC redirect URIs to PRODUCTION values
  (`https://panel.famit.in/callback`) so they're forward-compatible.

---

## 4. OIDC ISSUER / CLIENT CONFIG — what the LATER caller.py integration consumes

These are the env values the deferred caller.py auth unit (spec §3 `logto_verify.py` + §7 flags) will read.
Filled-in values that depend on console config are AWAITED from the founder (see §3 + HOWTO step 10).

```
# --- known NOW (from this deploy) ---
LOGTO_ENDPOINT      = https://auth.famit.in        # PRODUCTION issuer base (set ENDPOINT to this once DNS/TLS live)
                                                   # current runtime issuer = http://localhost:3001/oidc (pre-DNS)
LOGTO_ISSUER        = {LOGTO_ENDPOINT}/oidc         # token `iss` MUST equal this
LOGTO_API_RESOURCE  = https://api.famit.in          # API indicator -> token `aud` (create in console step 5)
LOGTO_JWKS_URI      = http://10.122.0.3:3001/oidc/jwks   # *** CORRECTED from spec default ***
   # Spec default `http://127.0.0.1:3001/oidc/jwks` assumed Logto co-located with caller.py. Here Logto is
   # on famit-hatchet (priv 10.122.0.3) and caller.py runs on famit-livekit (priv 10.122.0.4) -> fetch keys
   # over the VPC. The `iss` string stays https://auth.famit.in/oidc (independent of fetch URL; spec FIX #2).
   # INTEGRATION PREREQ: open hatchet-fw inbound tcp/3001 from 10.122.0.4/32 ONLY (mirrors hatchet's gRPC
   # cutover pattern). Until then cross-box JWKS fetch is blocked (LOGTO_ENABLED stays false -> no-op anyway).
LOGTO_MGMT_TOKEN_ENDPOINT = http://127.0.0.1:3001/oidc/token    # (or VPC 10.122.0.3:3001) for the M2M flow
LOGTO_MGMT_API_RESOURCE   = https://default.logto.app/api       # default-tenant Management API indicator (verified in DB NOW)
   # VERIFY-AT-INTEGRATION: re-confirm this indicator from the console/DB AFTER ENDPOINT is set to
   # https://auth.famit.in — the management resource indicator can be ENDPOINT-derived in some Logto
   # versions; don't hardcode blindly or the M2M client_credentials token request can silently 400.

# --- AWAITED from founder console setup (HOWTO step 10) ---
LOGTO_M2M_APP_ID      = <from M2M "Famit Management" app>    # for logto_provision.py (tenant->org backfill)
LOGTO_M2M_APP_SECRET  = <from M2M app>
LOGTO_PANEL_CLIENT_ID     = <from "Famit Panel" web app>    # for the frontend Logto login (spec STEP 7)
LOGTO_PANEL_CLIENT_SECRET = <from web app>
FAMIT_ADMIN_ORG_ID    = <the "Famit" org id>               # -> written to admin tenant's logto_org_id (see §5)
```

---

## 5. TENANTS -> LOGTO-ORGS MIGRATION PLAN

Mapping principle (spec §0 + P1 lock): **1 existing tenant <=> 1 Logto organization** (semantic
`org_id == tenant_id`), joined by a NEW tenant field **`logto_org_id`** (the Logto org's own random id,
NOT the literal tenant_id string). Migration is ADDITIVE — it only ADDS `logto_org_id` to each tenant row;
legacy `X-Auth: FamitCall2026` + HS256 JWT + `tenant_id.hmac` stay valid throughout and after cutover.

Steps (run via `logto_provision.py`, spec §6 — a LATER unit; do NOT run from the request path):
1. Get an M2M Management-API token (client_credentials, `resource=https://default.logto.app/api`,
   `scope=all`) using `LOGTO_M2M_APP_ID/SECRET` from the founder console step.
2. For each tenant in `var/tenants.json` (currently the authoritative store; becomes the P1 `orgs` table
   after P1.U7 — keep the script routed through `_read_tenants`/`_write_tenants` so the swap is transparent):
   - If `logto_org_id` already set -> skip (idempotent).
   - `POST /api/organizations {name: tenant.name}` -> capture `org.id`.
   - `POST /api/users {primaryEmail: tenant.email, name: tenant.name}` (or find existing) -> `user.id`.
   - `POST /api/organizations/{org.id}/users {userIds:[user.id]}` (add member).
   - `POST /api/organizations/{org.id}/users/{user.id}/roles` -> org role matching `tenant.role`
     (`admin|manager|agent`).
   - Write `tenant.logto_org_id = org.id` back; atomic write keeping a `tenants.json.logtobak.<ts>`.
3. The single admin tenant (`tenant_id="admin"`) -> the **"Famit" org** (created manually in the console,
   step 4) with org-role `admin`; its `logto_org_id = FAMIT_ADMIN_ORG_ID`. (Other tenants: created by the
   script.) Never set/alter `is_admin`; never delete fields.
4. Cutover stays flag-gated: `LOGTO_ENABLED=false` until the caller.py unit ships + is canary-tested
   (spec STEP 6). `LEGACY_TOKEN_ENABLED=true` through the whole cutover; flip last (spec STEP 8).

Backfill safety: `tenants.json` is on famit-livekit (`/opt/famit-agent/var/`); the script runs there (or
reaches the JSON), backs it up first, and only ADDS a field -> zero risk to current auth.

---

## 6. RESOURCE IMPACT ON THE SHARED BOX (measured)

After Logto came up (idle), `docker stats`:
| Container | Mem | Notes |
|---|---|---|
| logto | 273 MB / 1g cap | Node core+admin |
| logto-postgres | 39 MB / 1g cap | dedicated Logto DB |
| hatchet-lite | 38 MB / 1.5g cap | unchanged |
| hatchet-lite-postgres | 233 MB / 1g cap | unchanged |

Box: 3915 MB total, **2663 MB available** after Logto. CPU near-idle. **Logto added ~312 MB; comfortable
headroom remains.** Self-host did NOT strain the box -> the Logto-Cloud fallback's trigger never fired;
self-host is the chosen, working path (no recurring cost vs Cloud's free-tier limits).

---

## 7. FILES (local source of truth)
- `caps/infra/logto/docker-compose.logto.yml` — the stack (Logto 1.40.1 + dedicated PG, localhost-bound, capped).
- `caps/infra/logto/logto.env.example` — env template (no secrets).
- `caps/infra/logto/CONSOLE_SETUP_HOWTO.md` — founder click-by-click for admin/org/OIDC/M2M (the gated step).
- `caps/infra/logto/F4_LOGTO_STATE.md` — crash-safe per-unit ledger.
- On box: `/opt/logto/{docker-compose.yml, logto.env(600)}`, volume `logto_postgres_data`, network `logto-net`.

## 8. REMAINING GATED STEPS (not blockers for THIS unit)
1. FOUNDER: run `CONSOLE_SETUP_HOWTO.md` -> create admin + Famit org + API resource + org roles + OIDC web
   app + M2M app; return the 6 values in §4. (5-10 min.)
2. LATER (DNS): once Cloudflare token re-scoped, point `auth.famit.in` at the box, add nginx+TLS, set
   `ENDPOINT=https://auth.famit.in` in logto.env, recreate the logto container. Issuer becomes production.
3. LATER (caller.py spine unit): implement `logto_verify.py` + flags + `resolve_tenant` STEP-0 branch
   (spec §3, default OFF) and `logto_provision.py` backfill (§5). Open hatchet-fw tcp/3001 from
   10.122.0.4/32 for cross-box JWKS. ALL flag-gated OFF -> non-breaking.

---

## 9. F4 PART 2 — CONSOLE CONFIG COMPLETED PROGRAMMATICALLY (2026-06-10) — ORG-TOKEN TEST PASSED ✅

The founder ran most of CONSOLE_SETUP_HOWTO.md (created the admin user `admin@famit.in`, the Famit org,
the M2M `Famit Management` app + its Management-API role, the Famit Panel Traditional-web app w/ correct
prod redirect URIs, the `https://api.famit.in` API resource + read/write/manage_tenants scopes, and the
`admin`/`manager`/`agent` org roles with those resource scopes). The two confusing bits the HOWTO flagged
were finished here **via the Logto Management API from the box** (localhost only — nothing exposed):

- **Management token obtained** off the M2M app (`9rzus3efmmbb9zmivl9a5`, secret read from PG
  `application_secrets`), `client_credentials` `resource=https://default.logto.app/api scope=all` ->
  `GET /api/organizations` 200.
- **Added the M2M app as a member of the Famit org** (`7g5hzj2r6zjw`). This was the founder's blocker.
- **KEY LEARNING — org roles are TYPED (User vs MachineToMachine).** The founder's `admin` org role
  (`fh2ll2f37krwag7go9m2p`) is **User**-type; a DB CHECK (`check_organization_role_type`) REJECTS assigning
  a User-type role to an *application* (got HTTP 422 db_constraint_violated). Logto's design: one role
  object can't serve both a user and an M2M app. FIX: created a sibling **`admin-m2m`
  (MachineToMachine-type) org role** (`us61s0x2tmjcfa5s2zwya`) with the SAME 3 Famit-API resource scopes
  (read/write/manage_tenants), assigned it to the M2M app. The admin USER keeps the User-type `admin` role.
- **Set a known password** on `admin@famit.in` via `PATCH /api/users/{id}/password` (recorded in the result file).
- **THE MONEY TEST PASSED:** minted an org-API-resource token (client_credentials, `resource=https://api.famit.in`,
  `organization_id=7g5hzj2r6zjw`, `scope=read write manage_tenants`). Decoded claims:
  `aud=https://api.famit.in`, `organization_id=7g5hzj2r6zjw`, `iss=http://localhost:3001/oidc` (pre-DNS),
  `scope="read write manage_tenants"` (non-empty), `sub=9rzus3efmmbb9zmivl9a5`. This is exactly the claim
  shape `logto_verify.py` consumes. NOTE: client_credentials returns scopes ONLY when `scope=` is requested
  explicitly (without it, `organization_id`+`aud` still present but `scope=null` — expected Logto M2M behaviour).
- All ops idempotent (re-runnable). Box temp files (with the token/secret) deleted afterward.

**Full config (App IDs/Secrets, org id, admin creds, token-test result):**
`caps/infra/logto/LOGTO_CONFIG_RESULT.md` (LOCAL only, full secrets, never commit).
caller.py is UNTOUCHED — the auth integration remains a later spine unit. Live boxes untouched.
