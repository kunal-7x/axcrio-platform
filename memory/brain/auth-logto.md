# BRAIN — Logto self-hosted OIDC (F4 auth IdP)

Durable facts + hard-won learnings for the Logto auth subsystem. Append, never delete.
Design spec: `caps/design/auth-logto.md`. Build log: `memory/build_log/wave-build-F4-logto.md`.
State ledger: `caps/infra/logto/F4_LOGTO_STATE.md`. Founder guide: `caps/infra/logto/CONSOLE_SETUP_HOWTO.md`.

## WHAT IT IS / SCOPE
- Logto = self-hosted OIDC IdP for the platform's auth / orgs / RBAC / white-label (F4). It AUTHENTICATES;
  `tenants.json` (-> P1 Postgres) stays authoritative for authZ scoping. 1 tenant <=> 1 Logto org.
- **F4 part 1 = engine deploy + secure + console-stand-up = DONE.** The caller.py write-path integration
  (`logto_verify.py` RS256/JWKS branch + flags + `resolve_tenant` STEP-0, default OFF) is a SEPARATE LATER
  spine unit — NOT built. Legacy X-Auth `FamitCall2026` + HS256 JWT + `tenant_id.hmac` untouched + working.

## THE DEPLOYMENT (on the EXISTING hatchet box — no new droplet)
- Box **famit-hatchet 68.183.94.38 / priv 10.122.0.3** (s-2vcpu-4gb, VPC default-blr1). Chose it over the
  backend voice box (spec's own FIX #3 forbids co-locating an IdP with the TTFT-critical agent) and panel
  (live earning). SSH `ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 root@68.183.94.38` (key-only).
- Stack `/opt/logto/docker-compose.yml` (src `caps/infra/logto/docker-compose.logto.yml`):
  - `logto` = `ghcr.io/logto-io/logto:1.40.1` (PINNED, latest stable 2026-05-29). Core `127.0.0.1:3001`,
    admin `127.0.0.1:3002`. mem 1g/cpus 1.0. ENDPOINT/ADMIN_ENDPOINT UNSET -> defaults to localhost (tunnel).
  - `logto-postgres` = `postgres:15.6`, db `logto`/role `logto_app`, vol `logto_postgres_data`, NO published
    port (network `logto-net` internal). SEPARATE from Hatchet's broker PG — no collision.
  - Secrets in `/opt/logto/logto.env` (chmod 600, random 24-byte pw). Never committed.
- Internal seeded M2M secrets (NOT externally usable — see learning below): m-default secret + m-admin
  secret live in the `applications.secret` column (NOT `application_secrets`, which is empty).

## SECURITY (verified)
- 3001/3002 bound 127.0.0.1 ONLY; PG 5432 unpublished. Public test `68.183.94.38:{3001,3002,5432}` -> 000.
- ufw (22 only) + DO `hatchet-fw` (SSH+ICMP, egress-locked). Console via SSH tunnel `-L 3002:127.0.0.1:3002`.
- No public `auth.famit.in` yet (no Cloudflare token — PENDING re-scope). Tunnel-only = strictly safer.

## CONFIG THE LATER caller.py INTEGRATION CONSUMES
```
LOGTO_ENDPOINT     = https://auth.famit.in           # set ENDPOINT to this once DNS/TLS live; issuer={EP}/oidc
LOGTO_API_RESOURCE = https://api.famit.in            # token aud (create as API resource in console)
LOGTO_JWKS_URI     = http://10.122.0.3:3001/oidc/jwks  # *** VPC, NOT spec's 127.0.0.1 (cross-box) ***
LOGTO_MGMT_API_RESOURCE = https://default.logto.app/api  # default-tenant Management API indicator (verified)
# AWAITED from founder console (HOWTO step 10): LOGTO_M2M_APP_ID/SECRET, LOGTO_PANEL_CLIENT_ID/SECRET, FAMIT_ADMIN_ORG_ID
```
INTEGRATION PREREQ: open `hatchet-fw` inbound tcp/3001 from `10.122.0.4/32` (famit-livekit) for cross-box
JWKS. The `iss` string stays https://auth.famit.in/oidc regardless of the fetch URL (spec FIX #2 split).

## TENANTS -> ORGS MIGRATION (plan; script = later)
Additive: add `logto_org_id` field to each tenant via `logto_provision.py` (spec §6). Admin tenant ("admin")
-> the manually-created "Famit" org (org-role admin). Legacy auth stays valid throughout; cutover flag-gated
(`LOGTO_ENABLED=false` until caller.py unit ships + canary; `LEGACY_TOKEN_ENABLED=true` flipped last).

## HARD-WON LEARNINGS (do not relearn)
- **Logto OSS has NO headless first-admin.** CLI = `{init, db(seed/alt/config/system), connector}` only —
  no user-create. First admin is created via the console UI (browser) on first visit. A headless agent
  can't do it -> founder click-by-click over the SSH tunnel (`CONSOLE_SETUP_HOWTO.md`).
- **The seeded `m-default`/`m-admin` M2M apps are INTERNAL proxy apps** (`protected_app_metadata` set) and
  return `invalid_client` on `/oidc/token`. You CANNOT use them as external Management-API M2M clients.
  Create your OWN M2M app in the console (needs the first admin) to drive the Management API.
- **ENDPOINT is optional + only affects the runtime issuer (`iss`), not stored records.** Deploy with it
  UNSET so the console works over a localhost tunnel pre-DNS; flip to `https://auth.famit.in` later with
  zero data migration. Set OIDC redirect URIs to PRODUCTION values now so they're forward-compatible.
- **psql via SSH heredoc mangles quotes/escapes.** Write the .sql LOCALLY, `scp` it, then
  `docker exec -i logto-postgres psql -U logto_app -d logto < file.sql`. Don't fight `-v`/`\047` over SSH.
- **Latest stable Logto = 1.40.1** (2026-05-29). PIN it (`:latest` is a supply-chain/repro risk).
- Logto core comes up FAST once PG is healthy (OIDC discovery 200 within ~3s of container start here).
- Resource cost on the shared box: ~312 MB idle (logto 273 + its PG 39). Box had 2.6 GB free after.
  Self-host did NOT strain it -> Logto-Cloud fallback unneeded (and Cloud also needs a human signup click).

## CONSOLE CONFIG — DONE (2026-06-10, programmatic) — ORG-TOKEN TEST PASSED ✅
Founder created admin user, Famit org, M2M app, Panel web app, API resource, org roles via console; the two
confusing finishing steps were completed via the Management API from the box. Concrete IDs (full secrets in
`caps/infra/logto/LOGTO_CONFIG_RESULT.md`, local-only):
- Famit org = `7g5hzj2r6zjw`. API resource `https://api.famit.in` = `vl1uxuoouvn5th14k4kwv` (scopes
  read `ul5natzh963l5rj6646is` / write `jh9ubzj9m7emloml8m54z` / manage_tenants `qtgf93vfzohi2axv23032`).
- M2M `Famit Management` = `9rzus3efmmbb9zmivl9a5` (secret in `application_secrets` table, NOT the
  `applications.secret` `#internal:` proxy one). Holds "Logto Management API access" role.
- Panel (Traditional web) = `xubtoblw3rirtae7mkn9e`, redirect `https://panel.famit.in/callback`, post-logout
  `https://panel.famit.in` (already correct). Admin user = `gzszbo857lfi` (`admin@famit.in`, pw set + recorded).

### CRITICAL LEARNING — org roles are TYPED (User vs MachineToMachine); a role can't serve both
DB CHECK `check_organization_role_type` rejects assigning a **User**-type org role to an **application**
(HTTP 422 `entity.db_constraint_violated`). The founder's `admin` org role (`fh2ll2f37krwag7go9m2p`) is
User-type -> works for the admin USER, but NOT for the M2M app. FIX: create a sibling M2M-type org role with
the SAME resource scopes. Created **`admin-m2m`** (`us61s0x2tmjcfa5s2zwya`, type MachineToMachine,
read/write/manage_tenants) and assigned it to the M2M app. So the intended "admin" end-state = TWO sibling
roles (one per principal type), identical scopes. This is Logto's design, not a bug.

### MONEY TEST (org token) — PASSED
`POST /oidc/token` client_credentials, `resource=https://api.famit.in`, `organization_id=7g5hzj2r6zjw`,
`scope=read write manage_tenants` -> token claims `aud=https://api.famit.in` + `organization_id=7g5hzj2r6zjw`
+ `iss=http://localhost:3001/oidc` (pre-DNS) + `scope="read write manage_tenants"` + `sub=<M2M id>`. Exactly
what `logto_verify.py` reads. **Gotcha:** client_credentials returns scopes ONLY if `scope=` is explicitly
requested (else `organization_id`+`aud` present but `scope=null` — normal Logto M2M behaviour, not an error).

## STATUS / REMAINING (gated, not blockers for the engine unit)
1. FOUNDER console + the 2 programmatic finishing steps -> DONE (see above). caller.py still UNTOUCHED.
2. LATER (DNS): point auth.famit.in at the box, nginx+TLS, set ENDPOINT, recreate logto container.
   ALL the IDs/secrets/memberships above survive the ENDPOINT switch (only `iss` changes).
3. LATER (caller.py spine unit): logto_verify.py + flags + resolve_tenant STEP-0 (default OFF) + provision script.
