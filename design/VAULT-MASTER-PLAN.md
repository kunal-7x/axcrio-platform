# VAULT — MASTER PLAN (FINAL, red-team-corrected 2026-06-14)

> Read-only design. No code/box edits. Source of truth for Wave #10 (Vault) build.
> Supersedes the 2026-06-14 draft. Every fiction in the draft (Argon2id-PIN, jti/Redis single-use,
> immutability "trigger", `/vault*` wildcard, RLS-exempt log, missing AAD, plaintext-fallback) is
> CORRECTED here against live code, per the red-team passes (vault-backend · vault-frontend ·
> vault-security · earner-safety · cost-blowup · completeness).
> Provenance: explore/vault-have · vault-fe-have · vault-security-have · research/vault-secret-mgmt ·
> vault-ux-features · vault-compliance-automation + 6 red-team verdicts (this file's §R).

---

## 0. ONE-LINE VERDICT

Build Vault as a **net-new package `droplet_work/vault/`** mounted via the PROVEN
`build_router(resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod)` + `app.include_router(...)`
shape (NOT the draft's fictional `build_router("vault", …)`). Net-new **AES-256-GCM** envelope store,
**AAD-bound** ciphertext, **FORCE-RLS on all 4 tables (incl. the access log)**, reads default
**`is_admin=False`**, gated by `VAULT_ENABLED` (default OFF). The live earner `agent.py`
(md5 `9150fabe…`) is NEVER imported and NEVER touched — Vault rides `caller.py` (the separate
FastAPI control-plane process), which the earner-safety red-team confirmed is genuinely
earner-isolated. The 40+ live `.env` keys migrate in behind a **dual-read (vault-first, .env-fallback)**
period so no migration causes an outage. Vendors manage their own keys from day 1.

---

## 0b. THE LOAD-BEARING CORRECTIONS (do NOT execute the old §3/§4/§7/§12/§20 — they encode guarantees the code does not provide)

| # | Draft claimed | LIVE truth (file:line) | This plan does |
|---|---|---|---|
| C1 | `build_router("vault", …)` factory | No such factory. Funnels shape is `build_router(resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod)` → `app.include_router` (`caller.py:7304-7320`) | Export EXACTLY that signature |
| C2 | PIN = Argon2id `m=64MB,t=3` | PIN = salted **SHA-256** (`firewall.py:95`); step-up HS256, sub-bound, TTL 300, **no jti store** | Reuse live sha256 step-up AS-IS; Argon2id may wrap the **DEK at rest**, never the PIN |
| C3 | jti stored in Redis, single-use, atomic DEL | `verify_step_up_token` (`firewall.py:278-295`) checks sig+exp+type+scope+sub and **nothing else** — jti is minted but never consumed → token **replayable for 300s** | BUILD a real `vault_used_jti` PG consume-table (no Redis dep) + bind `aud=secret_id` for REVEAL + drop REVEAL TTL to 60s |
| C4 | `vault_access_log` "RLS not needed … via app middleware" | That re-opens cross-tenant log read | FORCE-RLS the log with the identical policy; super-admin reads via `is_admin=True` only |
| C5 | "immutable … enforced by app + PG trigger" | repo-wide grep `CREATE TRIGGER\|BEFORE DELETE\|BEFORE UPDATE` = **0 matches** — no DB-level guard exists anywhere | Ship `REVOKE UPDATE,DELETE ON vault_access_log FROM famit_app` + a `BEFORE UPDATE OR DELETE … RAISE EXCEPTION` trigger (real append-only) |
| C6 | KEK→DEK envelope (no AAD) | ciphertext carries no identity → copy-paste-swappable across rows even under RLS | AAD = `tenant_id‖secret_id‖version` MANDATORY in `crypto.py`; wrong-row decrypt MUST raise `InvalidTag` |
| C7 | `api_prefixes: ["/vault*"]` | matcher is `p==pr or p.startswith(pr+"/")` (`entitlements.py:418`) — literal `*` never matches → LOCK/suspend **silently bypassed** for vault | `["/vault"]` ONLY, everywhere |
| C8 | KEK-0 env var, absent = "MVP-acceptable" (copies `key_store.py` plaintext fallback) | `key_store.py:18,42-43,58` degrades to **0600 plaintext JSON** when its secret is unset — catastrophic if copied for tenant secrets | KEK-0 absent/<32B → routes **503 disabled**, NEVER plaintext. CI grep-proof: no plaintext-write branch in `crypto.py` |
| C9 | RLS admin clause harmless | `is_admin='1'` (`rls.sql:29`) is a **master skeleton key** reading ALL tenants; `engine.session(is_admin=True)` is used by backfill/super-admin routes | Tenant reads live in `store.py` (`is_admin=False` HARDCODED); the `is_admin=True` path lives in a SEPARATE `admin_store.py` mounted ONLY under `require_super_admin` — a tenant route physically cannot import the admin reader |
| C10 | "4-attempt lockout" on step-up | live lockout = 5 fails/15min and gates **change_pin ONLY** — step-up mint has **NO rate limit** | Add a per-tenant rate-limit on step-up mint for the `vault.reveal` scope before declaring brute-force protection |
| C11 | Vault is the secret store; Fernet store "stays as-is" | → Vault becomes a **write-only museum**; Video/RAG BYO-key read from the OLD Fernet store | Ship the **Vault read-seam** `vault.get_secret(tenant,key_type,scope,is_admin=False)` that the voice connect-window + video worker + llm-router all call (the #1 cross-product gap) |

---

## 1. WHY NOW — PROBLEM STATEMENT

| Pain | Evidence |
|---|---|
| 40+ live keys in plaintext `.env` | `/opt/famit-agent/.env` readable to anyone with box access; `design/obs-sec-cost.md:894` |
| AI credential leaks +81% YoY | GitGuardian 2025 Secrets Sprawl; Groq/OpenAI/Sarvam fastest-growing leak categories |
| No per-tenant key isolation | A vendor's Shopify/WhatsApp/custom-LLM key sits in shared `.env` — zero RLS |
| Video Studio + RAG BYO-key gate | Both products' "bring-your-own-key" stories assume a Vault read-seam that does not exist yet |
| Rotation is manual / zero automation | No expiry policy, reminder, or rotation workflow in the stack today |
| SOC 2 procurement gate | Per-operation audit + tamper-evident records + SIEM export is a B2B deal requirement |

---

## 2. WHAT EXISTS TODAY (HAVE — reuse, file:line confirmed)

| Primitive | File:Line | Status | Role in Vault |
|---|---|---|---|
| Firewall step-up (sha256 PIN, HS256, sub-bound, TTL300) | `firewall.py:42,95,267,278-295,307` | LIVE, PROVEN | Gates every WRITE/ROTATE/REVOKE/REVEAL |
| `build_router(...)` + `include_router` mount | `caller.py:7304-7320` (funnels) | LIVE | Exact shape Vault exports |
| Token-derived tenant (never body) | `caller.py:7249` `resolve_tenant(request)["tenant_id"]` | LIVE, T3 PASS | `tenant_id` ALWAYS from JWT |
| FORCE-RLS + GUC | `db/rls.sql:1-44`; `engine.session(is_admin=False)` default sets `app.is_admin='0'` (`engine.py:160,168-169`) | PROVEN 42/0 | All 4 vault tables ship identical policy |
| Immutable audit ledger | `audit.py` + PG `events` table | LIVE | `channel='vault'` events — same write path |
| Control HIDE/LOCK/ON middleware + matcher | `entitlements.py:361-369,401-422` (HIDE 404/LOCK 402; `p==pr or startswith(pr+"/")`) | LIVE | Vault feature_key gated through unchanged choke-point |
| Status-floor (suspend → 404) | `design/control-security.md:261-279`, T15 PASS | LIVE | Suspended tenant → vault 404 — IF prefix is `/vault` not `/vault*` |
| `require_super_admin` (legacy `FamitCall2026` EXCLUDED) | control-security #1 finding | LIVE | Only gate that opens `is_admin=True` |
| Fernet platform key store | `llm_router/key_store.py:40-53` | LIVE (platform keys) | **Left untouched**; Vault is a separate, stronger store; consumers migrated via the read-seam |
| Hatchet durable scheduler | `68.183.94.38`, hatchet-lite | LIVE | Rotation + expiry + health-check + jti-reaper jobs |
| Core_2 UI kit + api-keys secret-row | `famit-panel/app/super-admin/api-keys/page.tsx:268-327` | LIVE | Vault FE ports it verbatim |

**VAULT TODAY = 0% FE, 0% BE, 0% schema.** Infrastructure exists; implementation is net-new.

---

## 3. ENCRYPTION ARCHITECTURE (AAD-bound, fail-closed)

### 3.1 Cipher stack (3-layer envelope, with AAD)

```
KEK-0  VAULT_ROOT_KEY (env, 32 random bytes b64; ABSENT/<32B ⇒ routes 503 disabled — NEVER plaintext)
  └─ wraps ─► KEK-1  per-tenant AES-256 key, stored vault_keys.wrapped_kek1 (wrapped under KEK-0)
                └─ wraps ─► DEK  per-secret AES-256 key
                              └─ AES-256-GCM encrypts ─► ciphertext  (12-byte random nonce prepended)
                                                          AAD = tenant_id ‖ secret_id ‖ version   ◄── MANDATORY
```

- **Cipher** = `cryptography.hazmat.primitives.ciphers.aead.AESGCM(256)` (already in venv —
  `key_store.py:48` imports from the same `cryptography` package). AES-NI hardware path on DO KVM.
- **AAD binds the ciphertext to its row** (`tenant_id‖secret_id‖version`). Copying tenant-A's
  `encrypted_value` BYTEA into tenant-B's row → decrypt raises `InvalidTag`. This is the real
  cross-tenant defense BELOW RLS (defends a box-level DB-write attacker / SQLi).
- **KEK-0 absent or <32 bytes ⇒ `crypto.py` init asserts → all vault routes return 503 disabled.**
  There is **NO plaintext-write branch** (the anti-pattern in `key_store.py`). CI grep-proof gates V0.
- **Argon2id (if used) wraps the DEK at rest ONLY** — never the firewall PIN, never the voice path.

### 3.2 Key rotation (zero-downtime, dual-active)

1. Generate new credential at provider. 2. Write `version N+1` alongside active `version N`.
3. Propagation 5-30 min (app reads N+1, old conns drain N). 4. Deactivate N at provider.
5. Mark N `health='revoked'` (keep ciphertext — audit). 6. Emit `vault.secret.rotated`.
**Root-key rotation is P2 ONLY** and MUST be one PG transaction (decrypt-all-DEKs-under-old →
re-wrap-under-new atomically); a crash mid-rotate corrupts the store. Do NOT ship in MVP.

---

## 4. DATABASE SCHEMA (FORCE-RLS on ALL tables + real append-only)

All tables follow `ddl_control.sql:84-91` (**ZERO percent-format markers** — the silent-no-tables
trap), owned by `famit_app` (NOSUPERUSER/NOBYPASSRLS so REVOKE actually binds). 5 tables (4 +
the jti-consume table the draft assumed existed).

```sql
-- vault_secrets : canonical secret registry
CREATE TABLE vault_secrets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL, name TEXT NOT NULL,
  key_type TEXT NOT NULL, provider TEXT, scope TEXT,
  encrypted_value BYTEA NOT NULL,            -- AES-256-GCM, nonce-prefixed, AAD-bound
  kek1_ref UUID REFERENCES vault_keys(id),
  version INT NOT NULL DEFAULT 1, ttl_days INT, expires_at TIMESTAMPTZ,
  last_rotated_at TIMESTAMPTZ,
  health TEXT DEFAULT 'unknown', health_checked_at TIMESTAMPTZ,
  rotation_policy TEXT DEFAULT 'manual',
  deleted_at TIMESTAMPTZ,                    -- soft-delete (30-day bin); NULL = live
  frozen BOOLEAN DEFAULT false,              -- tenant break-glass freeze (D4)
  created_at TIMESTAMPTZ DEFAULT now(), created_by TEXT,
  UNIQUE (tenant_id, name, version));
ALTER TABLE vault_secrets ENABLE ROW LEVEL SECURITY; ALTER TABLE vault_secrets FORCE ROW LEVEL SECURITY;
CREATE POLICY vault_secrets_isolation ON vault_secrets
  USING (current_setting('app.is_admin',true)='1' OR tenant_id=current_setting('app.tenant_id',true));

-- vault_keys : per-tenant KEK-1 wrapped under KEK-0  (FORCE-RLS, same policy)
CREATE TABLE vault_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL UNIQUE, wrapped_kek1 BYTEA NOT NULL,
  kek0_hint TEXT, created_at TIMESTAMPTZ DEFAULT now());
ALTER TABLE vault_keys ENABLE ROW LEVEL SECURITY; ALTER TABLE vault_keys FORCE ROW LEVEL SECURITY;
CREATE POLICY vault_keys_isolation ON vault_keys
  USING (current_setting('app.is_admin',true)='1' OR tenant_id=current_setting('app.tenant_id',true));

-- vault_access_log : append-only audit  (FORCE-RLS + DB-enforced immutability — C4 + C5)
CREATE TABLE vault_access_log (
  id TEXT PRIMARY KEY,                       -- sha256(secret_id‖accessor‖at_ns)
  secret_id UUID, secret_name TEXT NOT NULL, tenant_id TEXT NOT NULL,
  accessor_id TEXT NOT NULL, accessor_ip INET,
  action TEXT NOT NULL,                      -- READ|WRITE|ROTATE|REVOKE|REVEAL|HEALTH_CHECK|FREEZE
  result TEXT NOT NULL,                      -- OK|DENIED|ERROR  (NEVER the value/plaintext)
  at TIMESTAMPTZ NOT NULL DEFAULT now());
ALTER TABLE vault_access_log ENABLE ROW LEVEL SECURITY; ALTER TABLE vault_access_log FORCE ROW LEVEL SECURITY;
CREATE POLICY vault_access_log_isolation ON vault_access_log
  USING (current_setting('app.is_admin',true)='1' OR tenant_id=current_setting('app.tenant_id',true));
CREATE INDEX vault_access_log_tenant_at ON vault_access_log (tenant_id, at DESC);
REVOKE UPDATE, DELETE ON vault_access_log FROM famit_app;       -- C5: append-only by Postgres
CREATE FUNCTION vault_log_immutable() RETURNS trigger LANGUAGE plpgsql AS
  $f$ BEGIN RAISE EXCEPTION 'vault_access_log is append-only'; END $f$;
CREATE TRIGGER vault_log_noupd BEFORE UPDATE OR DELETE ON vault_access_log
  FOR EACH ROW EXECUTE FUNCTION vault_log_immutable();

-- vault_used_jti : single-use step-up consume store (C3 — the table the draft pretended existed)
CREATE TABLE vault_used_jti (
  jti TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
  consumed_at TIMESTAMPTZ NOT NULL DEFAULT now());
-- no RLS needed (jti is opaque + tenant-stamped); reaped by a Hatchet sweep > TTL.

-- vault_rotation_jobs : Hatchet integration  (unchanged shape)
CREATE TABLE vault_rotation_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  secret_id UUID, tenant_id TEXT NOT NULL, scheduled_at TIMESTAMPTZ NOT NULL,
  triggered_by TEXT, status TEXT DEFAULT 'pending',
  hatchet_run_id TEXT, completed_at TIMESTAMPTZ, error TEXT);
```

**Migration:** additive DDL only. `VAULT_ENABLED=0` ⇒ zero change to any existing route.
Apply `psql -f db/ddl_vault.sql` (same as `ddl_wallet.sql`). The new schemas must be confirmed
inside the existing PG backup cadence + a restore test that re-passes the RLS probe (E2).

---

## 5. SECRET TAXONOMY + AUTO-CLASSIFICATION

Closed enum (`ai_provider · self_hosted · database · messaging · integration · oauth · webhook ·
ssh_key · tls_cert · env_config · custom`). **Auto-classify is sync + cheap only:**
Layer 1 regex (`gsk_…`=Groq, `sk-ant-…`=Anthropic, etc., <1ms) + Layer 2 Shannon-entropy/prefix
(<5ms). **No SLM in the hot path** — the Llama-1B classifier is a Phase-2 background Hatchet job
that only refines `key_type` if confidence >0.8. Per-tenant chunk/size implications do not apply
to Vault (it's secrets, not a corpus) but **a per-tenant secret-count quota tied to plan tier**
prevents abuse (completeness B4 analogue).

---

## 6. API SURFACE (additive, all under `VAULT_ENABLED`)

`tenant_id = resolve_tenant(request)["tenant_id"]` ALWAYS. Reads = metadata only (never
ciphertext/plaintext). Writes + REVEAL require `firewall.require_step_up(request, scope, t)`.
Register a vault scope by adding `vault.reveal` to `firewall._DESTRUCTIVE_ACTIONS` (one-line,
additive, `firewall.py:56`).

```
# tenant — reads (can(t,"read"); no step-up)
GET    /vault/secrets                 list (metadata only)
GET    /vault/secrets/{id}            metadata + health
GET    /vault/secrets/{id}/history    version history
GET    /vault/secrets/{id}/log        access log (paginated, newest-first)
GET    /vault/health                  health score (0-100) + expiry summary
GET    /vault/expiry                  secrets by days-to-expiry (heatmap data)
GET    /vault/drift                   .env keys not in vault (READ .env only; never write/remove)

# tenant — writes (can(t,"write") + step-up)
POST   /vault/secrets                 create (step-up for ai_provider/ssh_key/tls_cert)
PUT    /vault/secrets/{id}            update name/scope/ttl/policy (NOT value)
POST   /vault/secrets/{id}/update-value   bump version (step-up) — GATED per §9 trust model
POST   /vault/secrets/{id}/reveal     decrypt→plaintext ONCE (step-up, aud=secret_id, 60s, jti-consumed)
POST   /vault/secrets/{id}/rotate     Hatchet rotation job (step-up) — GATED per §9
POST   /vault/secrets/{id}/revoke     mark health='revoked' (step-up)
DELETE /vault/secrets/{id}            soft-delete → 30-day bin (step-up)
POST   /vault/secrets/{id}/freeze     tenant break-glass: deny all reveals on this secret (D4)
POST   /vault/test-connection         single free-tier probe (NEVER paid credits, 1-call cap)

# super-admin only (require_super_admin — legacy FamitCall2026 EXCLUDED; ONLY admin_store, is_admin=True)
GET    /admin/vault/tenants           all-tenant health (metadata only)
GET    /admin/vault/tenants/{id}      one tenant metadata + log
GET    /admin/vault/export            NDJSON SIEM stream of vault_access_log (SOC-2 gate)
POST   /admin/vault/freeze-tenant     freeze an entire tenant's vault (compromise break-glass, D4)
POST   /admin/vault/rotate-root       re-wrap all DEKs under new KEK-0 (P2 ONLY, single PG txn)
```

**Reveal contract:** `X-Step-Up` HS256 token, `aud=secret_id`, TTL 60s; backend consumes `jti`
into `vault_used_jti` (INSERT … ON CONFLICT DO NOTHING — 0 rows ⇒ 403 replay) inside the reveal
txn. Plaintext held in a LOCAL `del`'d in `finally`, returned ONCE, `auto_conceal_s:30` (FE).
**Plaintext NEVER enters: the access log, `audit.py` payloads, journald, exception tracebacks,
or the connect-cache session dict that gets logged.** Reveal route wraps ALL exceptions → generic
500 logging `secret_id` only (no `exc_info`). The mount is import-guarded so a vault failure can
NEVER crash the spine: `try: app.include_router(_bv(...)) except Exception: log; pass`.

---

## 7. STEP-UP FLOW (reuse live sha256/HS256 firewall — NO Argon2id, NO Redis)

```
1. UI inline PIN pad (no page leave).
2. POST /firewall/step-up { pin }  → firewall.py: sha256(salt‖pin)==stored?  (NOT Argon2id)
   → mint HS256 { sub=tenant_id, jti=uuid4, scope='vault.reveal', aud=secret_id, exp=+60s }
   → rate-limit the MINT per-tenant (C10: step-up mint is unthrottled today — add the lockout-shaped limiter)
3. Client calls the vault route with X-Step-Up.
4. Vault: firewall.verify_step_up_token (sig+exp+type+scope+sub) THEN consume jti in vault_used_jti
   (atomic INSERT … ON CONFLICT → 0 rows = replay → 403) AND check aud==secret_id.
5. Proceed; emit vault_access_log + an audit `events` row (channel='vault', action only, NEVER value).
```

Step-up REQUIRED: WRITE · UPDATE-VALUE · REVEAL · ROTATE · REVOKE · DELETE · FREEZE.
NOT required: LIST · GET · history · log · health · expiry · drift (all metadata).

---

## 8. VOICE / CONSUMER READ-SEAM + HOT-PATH (zero per-turn latency)

**The read-seam (`vault.get_secret`) is the #1 cross-product deliverable** — without it Vault is
write-only and Video/RAG BYO-key are fiction (completeness A1). Single function, `is_admin=False`
hardcoded, called by the voice connect-window, the video render worker, and the llm-router:

```python
def get_secret(tenant, key_type, scope, is_admin=False) -> str | None:
    # store.py session: SET LOCAL app.tenant_id + app.is_admin='0'; AAD-checked decrypt; vault-first.
```

- **Dual-read migration:** consumers read **vault-first, `.env`-fallback** until a source proves
  fully migrated (D2). The drift wizard must NOT advise `.env` removal until dual-read is live.
- **Voice path:** vault is NOT in the per-turn loop. `scope='inbound_agent'` secrets load ONCE at
  connect inside the **existing W2 `context_store.py` connect-window cache** (reuse it — do NOT add
  a second cache), `is_admin=False`, ~5-10ms local PG + <1ms AES-NI decrypt. Cached in the session
  dict, **wiped on disconnect** (`del` + the dict is NEVER logged/`repr`'d on error). Per-turn = 0ms.

---

## 9. REVEAL / WRITE TRUST MODEL (resolve the half-gate — security theater otherwise)

The draft left reveal-policy as an open question while the UI shipped a Reveal button on every row,
and gave the same vendor `update-value`/`rotate` (write-without-read is NOT containment — V-9/D5).
**Resolved:**

- **`scope ∈ {ai_provider, platform}` (platform-owned keys the vendor must not exfiltrate):**
  vendor gets **NEITHER reveal NOR update-value NOR rotate** — only masked metadata + health +
  test-connection. Only super-admin manages these. The FE **hides Reveal/Rotate/Update for this
  category**. AI-provider keys are consumed via the platform proxy, never handed to the vendor.
- **`scope ∈ {integration, messaging, oauth, webhook, custom}` (tenant-owned, e.g. their Shopify
  token):** vendor CAN reveal + update + rotate (their own credential), step-up gated.

This is enforced server-side (route checks category before honoring reveal/update/rotate), not just
hidden in the UI.

---

## 10. ROTATION + EXPIRY + LEAK + HEALTH (Hatchet workflows)

- **Rotation modes:** manual (default) · scheduled (`auto_30d/90d`, cron fires N days pre-expiry;
  human-issued keys → alert only) · dynamic PG creds (P2). Workflow `vault-rotate-secret`:
  validate → provider rotate API → write N+1 → test-connection → revoke N → audit + notify.
  On failure: job `failed`, alert, **old version stays active** (never leave the tenant keyless).
- **Expiry cron (daily):** 30-60d in-app badge · 7-30d orange + WhatsApp alert · <7d red + urgent +
  block new connects · expired → block reads for that key. Auto-suggest TTL by type (Groq/EL/Sarvam
  90d, WhatsApp BSP 60d, JWT 30d).
- **Leak gates:** G1 gitleaks pre-commit (LIVE) · G2 `--staged` on push · G3 TruffleHog
  `--only-verified` daily (P3) · G4 drift check. **Auto-revoke webhook** `POST /vault/webhook/leak-detected`
  → immediate REVOKE + queued rotation, `triggered_by='leak_detection'`.
- **Health score (0-100):** +20 each for all-have-expiry · all-rotated-in-policy · all-active-verified ·
  none-scope-'all' · ai_provider-not-manual. Ring gauge on the dashboard.
- **jti reaper + orphan sweeps (Hatchet):** sweep `vault_used_jti` > TTL; reap stale rotation jobs.

---

## 11. FRONTEND (Core_2 kit — verbatim ports, token-only, registered glyphs only)

**Verdict:** 2 routes + 1 shared drawer; **port the api-keys secret-row pattern verbatim**
(`super-admin/api-keys/page.tsx:268-327` = masked-row/Switch/confirm-delete) + `_shared.tsx` admin
chrome. Zero new component library — `Card/Table/Badge/Modal/Switch/Field/Select/Button` + 3 net-new
leaves. Inter Display, **zero raw hex**, **only registered glyphs**.

**Hard kit constraints (silent-break if ignored):**
- **No `shield`/`eye`/`copy`/`key`/`refresh`/`download` glyph exists** — a missing `name` renders an
  invisible empty `<path>` with NO error. Vault nav icon = **`lock`** (not shield); Reveal = `lock`;
  Rotate = `clock-1`; Copy/Export = **text buttons**; Drift = `info`. A richer glyph set is a separate
  non-blocking Icon-registry PR — do NOT block the wave.
- Modal is headless with `isSlidePanel` (`Modal/index.tsx:54-63`) → access-log + detail = right
  drawer; add/reveal/rotate = centered `max-w-md`. Badge = 5 variants + `dot` → `VaultHealthBadge`
  clones `StatusPill` (`_shared.tsx:166-173`). Page title rendered ONCE by `<Layout title="Vault">`
  (no PageHeader, no subtitle). Sub-nav = pill-strip ported from `AdminHeader` (NOT `<Tabs>`).
- Entitlement gating = 1-line wrapper `<EntitlementGuard featureKey="vault.secrets">` (HIDE redirect
  / LOCK overlay); super-admin page wraps in `SuperAdminGuard`. **The entitlement IS the FE flag.**
- Optimistic mutation + rollback + `ToastView` = house pattern (ported verbatim for toggle/delete/
  rotate). **Reveal is NOT optimistic and NOT react-query-cached** — imperative call, plaintext held
  in a `useRef` wiped on unmount/timeout, never in `useState` that survives (V-7/R2 leak defense).

**Files:**
```
famit-panel/app/vault/{page,_sub-nav,_secret-list,_add-modal,_reveal-pin,_health-panel,
                       _expiry-heatmap,_drift-wizard,_access-drawer,_vault-badges}.tsx
famit-panel/app/super-admin/vault/page.tsx       (+ one ADMIN_TABS line, _shared.tsx:103)
famit-panel/lib/vault.ts                         (typed fetchers + useVault* react-query hooks)
```
**3 net-new leaves** (everything else is a verbatim port): `_reveal-pin.tsx` (inline PIN pad + 30s
countdown ring), `_health-panel.tsx` (score-ring gauge), `_expiry-heatmap.tsx` (month CSS grid).
Per §9 the FE **hides Reveal/Rotate/Update on `ai_provider` rows**. All animated elements are
reduced-motion + dark-mode safe. Build on Sonnet + the **frontend-design** skill.

---

## 12. SUPER-ADMIN VAULT (control-plane)

`require_super_admin` + add `{label:"Vault",href:"/super-admin/vault"}` to `ADMIN_TABS`. Fleet
health table (`Tenant·Active·Expiring·Unknown·HealthScore·LastActivity`), per-tenant detail
(**metadata only, no reveal even under act-as**), Rotate-Root panel (P2), tenant-freeze button,
access-log drawer + **Export CSV/NDJSON** (SIEM/SOC-2 gate). Registry seed (App.B) is the
**only correct prefix — `["/vault"]`, never `/vault*`**.

---

## 13. DISASTER RECOVERY — KEK-0 (MVP, NOT deferred)

KEK-0 loss = **every tenant's every secret permanently unrecoverable**. "MVP-acceptable" is the
wrong call for the thing whose entire job is not-losing-secrets (completeness D1). **MVP MUST ship:**
- KEK-0 backed up to a **second sealed/offline location** (encrypted, out-of-band, like the SSH key)
  + a documented break-glass restore runbook — **BEFORE any real tenant secret is stored**.
- Optional P2 hardening: Shamir 2-of-3 split / KMS unwrap (one-line swap in the unwrap helper).
- Fail-closed-on-absence (§3.1) prevents silent plaintext, but only the backup prevents total loss.

---

## 14. COMPLIANCE (SOC 2 + OWASP + DPDP) — now backed by real mechanisms

| Requirement | Implementation (corrected) |
|---|---|
| Per-operation audit | `vault_access_log` synchronous write, **FORCE-RLS** |
| Tamper-evident / append-only | **`REVOKE UPDATE,DELETE` + `BEFORE UPDATE/DELETE` trigger** (real, not "we promise the app won't") |
| SIEM export <1hr | `GET /admin/vault/export` NDJSON stream |
| Retention configurable | `vault_access_log` month-partitioned + retention env var (SOC-2 ≥1yr) |
| Least-privilege RBAC | §9 trust model + FORCE-RLS; reads `is_admin=False` |
| Secret expiry | `expires_at` on every secret, TTL auto-suggested |
| Key never logged | local `del` in `finally`; never in log/audit/journald/traceback/session-dict; grep-proof test |
| Rotation | Hatchet dual-active, zero-downtime, old-stays-active-on-fail |
| DPDP delete path | soft-delete + `POST /data/delete-request` per-person purge (NEXT-BIG-BUILDS #33) |

---

## 15. FOUNDER-UNNAMED FEATURES (the 1% → 100%)

Backend/security: **(a) AAD-bound ciphertext** · **(b) `is_admin=False` hardcoded in `store.py` +
separate `admin_store.py`** · **(c) KEK-0-absent fail-closed** · **(d) `vault_used_jti` single-use +
`aud=secret_id` 60s reveal** · **(e) append-only DB trigger + REVOKE** · **(f) step-up mint
rate-limit** · **(g) the read-seam `vault.get_secret` (cross-product)** · **(h) dual-read .env
migration** · **(i) KEK-0 backup/break-glass** · **(j) tenant-freeze break-glass** · **(k) §9
reveal/write trust model**.
Frontend/UX: inline PIN-pad countdown-ring reveal · copy-without-revealing · auto-classify
confidence chip · drift import wizard · rotation animation · sidebar expiry badge · test-connection
green/red dot (free-tier only) · health score ring · expiry heatmap · version rollback UI ·
reduced-motion/dark-mode safe · `font-mono tabular-nums` masked-at-rest.
Operational: PushNotification/WhatsApp alerts on the 3 urgent conditions (key <24h, leak-detected,
stuck rotation holding action) — the non-technical founder won't watch a dashboard (E1).

---

## 16. FLAG / ACCEPTANCE / ROLLBACK

- **Flag:** `VAULT_ENABLED` (default `0`) → router not mounted → byte-identical, `/vault/*`=404.
  `VAULT_ROOT_KEY` separate; absent → routes 503 disabled, never plaintext. FE flag = the
  `vault.secrets` entitlement (no separate FE flag).
- **Earner gate (EVERY unit, before+after):** `agent.py` md5 `9150fabe…` UNCHANGED + famit-agent
  PID/ActiveEnter unchanged + caller `/health`=200 + 0 5xx. `agent.py` is NEVER imported.
- **Acceptance probes:** DDL applied (`COUNT(*) vault_secrets`=0, append-only trigger blocks an
  UPDATE) · flag-OFF resting byte-identical · flag-ON create+list = metadata-only · **REVEAL without
  step-up→403; with step-up→plaintext ONCE; REPLAY same token→403 (jti consumed)** · **RLS T3 probe:
  POST as A, forge B token, GET→0 rows** · **AAD probe: write A's ciphertext into B's row→decrypt
  raises InvalidTag** · **plaintext-leak probe: grep test-run logs + `events` rows after a reveal=0
  hits** · **LOCK probe: lock vault for a tenant → `/vault/secrets/{id}/reveal`→402** · every action
  emits a `vault_access_log` row · `tsc --noEmit`=0, `npm run build`=0, gitleaks staged=0, zero raw
  hex in `app/vault`, every Icon `name=` registered.
- **Rollback:** `VAULT_ENABLED=0` + restart **famit-caller ONLY** (never famit-agent). DDL additive
  (no existing table altered). FE = delete `app/vault/`, `app/super-admin/vault/`, the one
  `ADMIN_TABS` line, `lib/vault.ts`. FORTRESS deploy is backup-first + `systemctl restart famit-panel`
  ONLY — the panel box `143.110.247.249` is NOT the earner box `168.144.153.145`.

---

## 17. CROSS-PRODUCT SERIALIZATION (RAG · Video · Vault share `caller.py` + registry + nav)

All three edit `caller.py`, `var/control/registry.json`, and the nav. **Hard rule: only ONE of
{RAG, Vault, Video} touches `caller.py` at a time** (ORCHESTRATOR owns the mount-order ledger).
One consolidated registry-seed with a reserved `sort_order` block (avoid the `mod.knowledge`
18-21 / `vault.secrets` / Video collision). Earner-safety red-team confirmed Video + Vault are
genuinely process-isolated from `agent.py`; the ONLY shared-file risk is the `caller.py` mount —
serialize it. One box-mutating wave at a time.

---

## 18. COST DISCIPLINE (free/1-test default — coded, not prose)

Vault's own spend is near-zero (PG + AES-NI). The cost guard that DOES apply: **test-connection is
free-tier probe ONLY, 1-call cap, NEVER paid credits** (founder HARD RULE). The Phase-2 SLM
classifier is CPU-only, async, off the hot path. No paid-API path is the default anywhere in Vault.

---

## 19. PHASED EARNER-SAFE BUILD ROADMAP

BE on **Opus**, FE on **Sonnet + frontend-design**. One box-mutating wave at a time. Each wave:
backend → verify → earner-gate (md5/PID/health before+after) → commit → next. V0-V3 backend-only
(no FE deploy). V4 = first FORTRESS deploy.

| Wave | Scope | Flag | Acceptance gate | Rollback |
|---|---|---|---|---|
| **V0** | `ddl_vault.sql` (5 tables, FORCE-RLS all, append-only trigger+REVOKE, jti table) + `VAULT_ENABLED` flag + import-guarded mount shell + `crypto.py` KEK-0 fail-closed | `VAULT_ENABLED=0` | DDL applied, COUNT=0, **UPDATE on log blocked**, **KEK-0-absent→503**, flag-OFF byte-identical, earner md5 unchanged | drop tables (additive); flag stays 0 |
| **V1** | `store.py` (is_admin=False) + `admin_store.py` (is_admin=True, super-admin only) + CRUD (POST/GET/LIST/PUT/DELETE) + AAD encrypt + step-up on write + §9 category gate | `VAULT_ENABLED=1` (box only) | **RLS T3 probe=0 rows**, **AAD wrong-row→InvalidTag**, create+list metadata-only, write-without-step-up→403, earner gate | `VAULT_ENABLED=0`, restart caller |
| **V2** | REVEAL + `vault_used_jti` single-use (aud=secret_id, 60s) + step-up mint rate-limit + access-log write + plaintext-leak sealing | `VAULT_ENABLED=1` | reveal once → plaintext; **replay→403**; **leak-probe (logs+events)=0**; LOCK→402; earner gate | flag 0 |
| **V3** | **read-seam `vault.get_secret`** + dual-read (.env-fallback) + connect-window cache wiring (W2 reuse, is_admin=False) | `VAULT_ENABLED=1` | seam returns A's secret, never B's (RLS probe via seam); voice connect adds ~0 per-turn; earner gate | flag 0 |
| V4 | FE: `_vault-badges`+`_sub-nav`+`_secret-list`+`_add-modal`+`lib/vault.ts` — first FORTRESS deploy | entitlement | `/vault` 200, masked metadata, tsc+build+gitleaks=0, zero hex, glyphs registered | delete `app/vault/` |
| V4b | FE: `_reveal-pin` (PIN pad + 30s ring, useRef-wiped, copy-post-conceal) | entitlement | reveal-without-PIN→403 toast; plaintext masks at 30s; no plaintext in react-state | delete file |
| V5 | FE: `_health-panel` ring + `_expiry-heatmap` + drift banner; BE health-score + expiry cron + drift endpoint | flag+entitlement | health score renders; drift lists `.env` keys (read-only) | flag/file |
| V6 | `/super-admin/vault` + `ADMIN_TABS` line + `_access-drawer` + NDJSON export + tenant-freeze | flag+entitlement | admin fleet table; no reveal under act-as; export streams | revert ADMIN_TABS line |
| V7 | Rotation route + Hatchet `vault-rotate-secret` + jti/orphan reaper + test-connection (free-tier) | flag | job done, N+1 exists, N revoked, old-stays-on-fail | flag 0 |
| V8 | Drift import wizard FE + dual-read coach (no `.env`-removal advice until seam proven) | entitlement | import toggles work; never advises removal pre-dual-read | delete file |
| **DR** | KEK-0 backup + break-glass runbook (BEFORE first real tenant secret — gates production use) | n/a | backup verified, restore drill passes | n/a |
| P2 | SLM classifier · anomaly detection · root-key rotation (single PG txn) · dynamic PG creds | flag | future | flag 0 |

---

## R. RED-TEAM LEDGER (what each pass forced into this plan)

- **vault-backend:** C1 (signature) · C2 (sha256 not Argon2id) · C4 (log FORCE-RLS) · C7 (no wildcard) ·
  C8 (fail-closed) · C9 (is_admin=False) · AAD · `vault.reveal` scope. **All folded.**
- **vault-security (9 attacks):** V-1 jti replay→C3 (`vault_used_jti` + aud + 60s) · V-2 log RLS→C4 ·
  V-3 plaintext fallback→C8 · V-4 fake immutability→C5 (REVOKE+trigger) · V-5 admin-GUC→C9
  (split admin_store) · V-6 AAD→C6 · V-7 plaintext leak→§6/§11 sealing · V-8 wildcard→C7 ·
  V-9 half-gate→§9 trust model · V-10 Argon2id fiction→C2 · V-11 lockout→C10 mint rate-limit.
- **earner-safety:** Vault is process-isolated (rides `caller.py`, never imports `agent.py`); only
  shared-file risk = the `caller.py` mount → §17 serialization + import-guard + flag-off /health probe.
- **cost-blowup:** test-connection free-tier 1-call cap; no paid default anywhere (§18).
- **completeness:** A1 read-seam (§8) · A2/A3 serialization+registry (§17) · D1 KEK-0 backup in MVP
  (§13/DR wave) · D2 dual-read migration (§8) · D4 tenant/secret freeze (§4/§6) · D5/§9 reveal policy ·
  E1 alerts (§15) · E2 PG backup+restore probe (§4) · E4 in the THREE_PRODUCTS_ROLLBACK runbook.

---

## APPENDIX A — FILES TO CREATE

```
droplet_work/vault/{__init__,endpoints,crypto,store,admin_store,classify,health}.py
droplet_work/db/ddl_vault.sql
famit-panel/app/vault/{page,_sub-nav,_secret-list,_add-modal,_reveal-pin,_health-panel,
                       _expiry-heatmap,_drift-wizard,_access-drawer,_vault-badges}.tsx
famit-panel/app/super-admin/vault/page.tsx
famit-panel/lib/vault.ts
```
Caller mount (mirror funnels `caller.py:7304-7320`): `try: from vault.endpoints import build_router as _bv`
→ `FEATURE_VAULT = cfg_get("VAULT_ENABLED","0")` → guarded
`app.include_router(_bv(resolve_tenant, can, need_auth, _forbidden, firewall=_firewall_mod))`
inside `try/except` (mount failure NEVER crashes the spine).

## APPENDIX B — FEATURE REGISTRY SEED (`var/control/registry.json`)

```json
{ "key":"vault.secrets","kind":"module","label":"Vault","nav_href":"/vault",
  "api_prefixes":["/vault"],"default_mode":"on","is_core":false,
  "description":"PIN-gated encrypted secret store for API keys, credentials, integration tokens" }
```
`["/vault"]` ONLY (NOT `/vault*` — the matcher is literal `startswith(pr+"/")`). `default_mode:"on"`
+ `is_core:false` → HIDE is cosmetic, LOCK→402, suspend→404, through the unchanged choke-point.

**Key files (absolute):** `droplet_work/firewall.py:42,56,95,150,267,278-295,307` ·
`droplet_work/caller.py:7249,7304-7320` · `droplet_work/db/rls.sql:3,26-36,29` ·
`droplet_work/db/engine.py:160,168-169` · `droplet_work/entitlements.py:361-369,401-422` ·
`droplet_work/llm_router/key_store.py:18,40-53,58` (Fernet — leave untouched) ·
`droplet_work/control/db/ddl_control.sql:84-91` · `droplet_work/context_store.py:197` (W2 cache) ·
`famit-panel/app/super-admin/api-keys/page.tsx:268-327,330-410` ·
`famit-panel/app/super-admin/_shared.tsx:103,166-173,242-258` ·
`famit-panel/components/{Badge,Modal,EntitlementGuard,Tabs,Field,Switch,Card,Icon}/index.tsx`.
