# F4 LOGTO — crash-safe per-unit ledger

Spec: `caps/design/auth-logto.md`. Build log: `memory/build_log/wave-build-F4-logto.md`.
Scope of THIS unit (F4 part 1): deploy Logto OSS (Docker) + its own Postgres on the EXISTING
hatchet box; secure it (no public internals); create admin user + 1 org + 1 OIDC app; capture the
issuer/client config the LATER caller.py integration consumes; document tenant->org migration plan.
NOT in scope: editing caller.py (later spine unit). Live boxes untouched.

## DECISION LOG
- BOX = **famit-hatchet 68.183.94.38 / priv 10.122.0.3** (s-2vcpu-4gb). Reason: task-recommended,
  least-critical (durable orch, not realtime/earning), Docker present, headroom verified
  (3915MB RAM, 2841 available; lite 41MB + pg 302MB idle; 70GB disk free; 2 vcpu + 2G swap).
  Backend voice box OFF the table (spec RED-TEAM FIX #3: TTFT-critical). Panel = fallback only.
- Logto image PINNED `ghcr.io/logto-io/logto:1.40.1` (latest stable 2026-05-29; NOT :latest, spec §10).
- SEPARATE Postgres `logto-postgres` (own volume `logto_postgres_data`, db `logto`, role `logto_app`),
  port NOT published (compose-internal only) -> cannot collide with Hatchet's broker PG.
- Core 127.0.0.1:3001, Admin 127.0.0.1:3002 (localhost-bound; reach via SSH tunnel). mem/cpu capped.
- Cloudflare token ABSENT (fortress note: PENDING re-scope) -> NO public auth.famit.in this unit.
  Deploy TUNNEL-ONLY: ENDPOINT/ADMIN_ENDPOINT unset -> Logto defaults to localhost so the admin
  console + sign-in work over the SSH tunnel. Production issuer https://auth.famit.in/oidc is the
  REMAINING GATED step (set ENDPOINT once DNS/TLS exist, before any client tokens are minted for real).
- JWKS fetch for later caller.py (on famit-livekit 10.122.0.4) = http://10.122.0.3:3001/oidc/jwks
  over the VPC (NOT 127.0.0.1 — spec default assumed co-location). Needs hatchet-fw inbound tcp/3001
  from 10.122.0.4/32 at integration time. iss string stays https://auth.famit.in/oidc.

## UNITS
- U0 pre-flight (resources, cloudflare, docs, tag) ......... DONE
- U1 write infra files (compose/env/README) local .......... DONE
- U2 deploy logto-postgres + logto on box, seed, health .... DONE (OIDC discovery 200, jwks 200)
- U3 firewall/posture verify (no public internals) ......... DONE (3001/3002 127.0.0.1 only; public 000; ufw 22 only)
- U4 admin console via tunnel: create admin user ........... GATED -> FOUNDER (no headless path; see U6 note)
- U5 create 1 organization + API resource + org roles ...... GATED -> FOUNDER (console, after admin)
- U6 create OIDC app (traditional web) + M2M app; capture ... GATED -> FOUNDER (console, after admin)
- U7 document migration plan + append build_log + HANDOFF + brain  DONE

## WHY U4-U6 ARE A FOUNDER STEP (not a skip)
Logto OSS has NO headless first-admin path: CLI = {init, db(seed/alt/config/system), connector} only —
no user-create. The seeded m-default/m-admin M2M apps are INTERNAL proxy apps (protected_app_metadata),
not externally usable on /oidc/token -> `invalid_client`. So creating your OWN usable M2M app requires
the Management API, which requires the first admin, which is created via the console UI (browser) on
first visit. Headless agent has no browser -> founder does it over the SSH tunnel (5 min, guide written:
infra/logto/CONSOLE_SETUP_HOWTO.md). Creating it now vs after DNS is fine: users/orgs/apps + client
id/secret are PERSISTED and survive the later ENDPOINT=https://auth.famit.in switch (ENDPOINT only changes
the runtime `iss` claim, not stored records). Set OIDC redirect URIs to PRODUCTION values now.
