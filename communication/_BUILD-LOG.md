# communication/_BUILD-LOG.md — per-phase build conclusions (APPEND-ONLY)

> Each phase appends its conclusion under a per-phase heading. The final phase also
> appends one line to `caps/WORKFLOW_LEDGER.md` + updates `communication/README.md`.

---

## W1-P0 — DB + TOKEN (Telegram, founder tenant) · 2026-06-14 19:53 UTC · backend, no caller.py

**Scope:** Apply the Wave-1 comm DDL (4 FORCE-RLS tables) to the live box PG + store the
founder Telegram bot token AAD-encrypted in the LIVE provider_credentials vault. NO caller.py,
NO agent.py, additive-only, backup-not-needed (additive — drop is the rollback). Branch
`fe/unify-run-wavec`.

### Earner gate (BEFORE + AFTER — box `famit@168.144.153.145`, the voice box `famit-livekit`)
| Check | BEFORE | AFTER |
|---|---|---|
| `agent.py` md5 (expect `9150fabe4ff62b4b4470f9a87df346e5`) | `9150fabe…` UNCHANGED | `9150fabe…` UNCHANGED |
| famit-agent MainPID (must not restart by my work) | 2808658 active | 2808658 active (SAME) |
| caller `/health` (port 8209) | 200 | 200 |
| famit-caller / famit-panel | active / inactive | active / inactive (untouched) |
| caller 5xx (last 20m) | — | 0 |
> NOTE: the lock file cited PID 1477083; the live famit-agent has since been restarted by a
> PRIOR wave to PID 2808658, but the **byte-identical** md5 `9150fabe…` is the earner truth and
> is UNCHANGED. THIS phase did not restart any service (DB + vault only). No ring placed.

### DDL — `communication/db/ddl_comm.sql` (box: `/opt/famit-agent/communication/db/ddl_comm.sql`, md5 `3abd30fbf3d0136788c78f573185d016`)
Four FORCE-RLS tables, `tenant_id TEXT`, INTEGER paise, idempotent `IF NOT EXISTS`, applied via the
live `db.engine` as `famit_app` (NOSUPERUSER/NOBYPASSRLS — confirmed). Key line ranges:
- `comm_sessions` — DDL lines **31–55** (LLM brain rolling-20 window; UNIQUE `(tenant,channel,external_chat_id,provider_def_id)` — no shared bot across tenants, S4).
- `comm_send_log` — DDL lines **61–90** (append-at-create; `cost_minor BIGINT` paise; `idempotency_key` UNIQUE = `comms:{message_id}`; `outcome` CAPI col day-1).
- `comm_consent_log` — DDL lines **97–115** (the `channel × purpose` model; `consent_basis` derived from `lead_source`; **append-only HARD**).
- `comm_asset_cache` — DDL lines **120–134** (Telegram `file_id` reuse; UNIQUE `(tenant,spaces_key,channel)`).
- RLS `DO $rls$` admin-GUC block (ddl_ai_wa.sql shape verbatim) — DDL lines **139–161**.
- Append-only hardening (REVOKE + immutability trigger) — DDL lines **165–192**.

### RLS / append-only PROOF (live, as `famit_app`)
- **4 tables rls=t force=t:** `comm_sessions`, `comm_send_log`, `comm_consent_log`, `comm_asset_cache` — all `(True, True)`. ✅
- **4 isolation policies present** (`comm_*_isolation`). ✅
- **comm_consent_log append-only:** `famit_app` grants = `INSERT, SELECT, REFERENCES, TRIGGER, TRUNCATE` — **NO UPDATE, NO DELETE** (REVOKE worked); trigger `comm_consent_no_update` present. ✅
- **Cross-tenant SELECT = 0:** insert a `comm_sessions` row as tenant `admin` → `admin` sees 1, `tenant_b` cross-read = **0**. PASS. ✅
- **consent immutable:** UPDATE → blocked (ProgrammingError), DELETE → blocked, row survives (count=1). PASS. ✅

### TOKEN — founder Telegram bot stored AAD-encrypted in the LIVE vault (zero new crypto)
- Token read from `.env.local` at RUNTIME (first line `TELEGRAM_BOT_TOKEN=`), bot `mr_kunal_bot`. Verified LIVE via `getMe` → `ok:true`, username `mr_kunal_bot`. **Never hardcoded, never committed, never logged, never on argv** (piped over the ssh stdin env, dropped from `os.environ` immediately after read).
- Stored under tenant **`admin`** (the founder tenant — `caller.py:598`, legacy panel login → admin), channel **telegram**, reusing the live registry vault:
  - `provider_definitions` row **`95ed8978-8bfe-4de2-8506-52e989d09f0e`** — slug `telegram-founder`, display "Telegram (mr_kunal_bot)", `provider_type=tool_connector`, capabilities `[webhook, tool_call]`, `base_url=https://api.telegram.org`, `named_provider=telegram`, `cost_per_unit_micros=0`.
  - `provider_credentials` row **`d3303376-701a-4a22-bef5-8308898160a6`** — `scope=integration` (founder's own, revealable via step-up), `is_active=true`, `key_version=1`, AAD `admin||95ed8978-8bfe-4de2-8506-52e989d09f0e||1`.
- **Decrypt-roundtrip MATCH = True**, masked **`8934…O7Js`** (matches the live getMe identity).
- **NO plaintext in DB:** the `ciphertext` bytea (74 bytes = 12-byte nonce + GCM) does NOT contain the plaintext token bytes; `ciphertext != token`. ✅
- **AAD binding holds:** copying admin's ciphertext into a `tenant_b` cred shape → decrypt raises **InvalidTag** (cross-tenant copy refused, no plaintext). ✅ (This is the T-VAULT probe shape.)
- **NO plaintext in logs:** caller journal + postgres journal (last 20m) → **0** hits for the bot-id portion. ✅

### Flags
None flipped this phase (DB + token only). The W1 code flags (`COMM_ENABLED`, `COMM_TELEGRAM_ENABLED`,
`FEATURE_TELEGRAM_FOUNDER_ALERT`, `FEATURE_TELEGRAM_FOLLOWUP`) stay OFF; they flip ON for the founder
tenant only AFTER the W1 code + security probes ship. Resting state is byte-identical (no code path
reads these tables until the comm package + caller.py mount land in a later phase).

### Rollback
`DROP TABLE comm_sessions, comm_send_log, comm_consent_log, comm_asset_cache;` (additive — nothing
else altered) + `DELETE FROM provider_credentials WHERE id='d3303376-…'` and the def row (vault rows are
inert until the adapter reads them).

### Files
- NEW `communication/db/ddl_comm.sql` (the 4-table DDL).
- NEW `communication/_BUILD-LOG.md` (this log).
- Box: `/opt/famit-agent/communication/db/ddl_comm.sql` (md5-gated copy).

**Status: DONE. DB live + token stored + earner gate green (before+after). Next phase: the comm
package (channels/base + telegram adapter, founder_alert, post_call, send_log, consent, router) +
the caller.py `_finalize_call` insertions under the CALLER_EDIT_LOCK.**

---

## W1-P1 — ADAPTER + ENGINE (Telegram, offline) · backend, NO caller.py · `fe/unify-run-wavec`

**Scope:** Build the `droplet_work/comm/` package — the Telegram Bot API channel adapter + a
channel-agnostic send engine — behind the one `ChannelAdapter` contract, reusing the LIVE
provider-vault crypto (ZERO new crypto). NO caller.py edit, NO agent.py import, all flags default
OFF (resting byte-identical), py_compile clean, offline tests green, gitleaks 0.

### Files (NEW — `droplet_work/comm/`, force-added; `droplet_work/` is otherwise gitignored scratch)
| File | Lines | What |
|---|---|---|
| `comm/__init__.py` | 1–74 | flag-gate shell; import-guarded behavioural surface; empty-env safe; `__version__=0.1.0-w1` |
| `comm/config.py` | 1–101 | the 4 W1 flags read at CALL TIME (default OFF): `COMM_ENABLED`/`COMM_TELEGRAM_ENABLED`/`FEATURE_TELEGRAM_FOUNDER_ALERT`/`FEATURE_TELEGRAM_FOLLOWUP` + the per-channel `send_timeout_s`/`http_timeout_s` |
| `comm/vault_read.py` | 1–117 | bridge: read the active credential (RLS-scoped) + decrypt via `provider_registry.credentials` (AAD-bound, InvalidTag→None); resolve the provider_def by slug/named_provider; degrade-never-raise |
| `comm/channels/base.py` | 1–150 | the channel-NEUTRAL contract: `SendEnvelope`/`SendResult`/`MediaItem`/`Button` dataclasses + the `ChannelAdapter` Protocol (NEVER raises, dormant when unconfigured) |
| `comm/channels/telegram.py` | 1–270 | the Telegram Bot API adapter: `send()` routes text→`sendMessage`, media→`sendPhoto`/`sendVideo`/`sendDocument`; inline-keyboard URL buttons; `verify()`=getMe; `derive_founder_chat_id()`=getUpdates (private-chat, cached); file_id cache (§1.2 #6); token redacted from every log/URL |
| `comm/channels/__init__.py` | 1–32 | the channels import surface |
| `comm/send_log.py` | 1–135 | `comm_send_log` writer: `new_message_id()`=`cms_<uuid4hex>`, `record_send()` idempotent on `(tenant, comms:{message_id})` via `ON CONFLICT DO NOTHING`, RLS-scoped, best-effort (no-PG→False, never raises) |
| `comm/engine.py` | 1–205 | the channel-agnostic dispatch seam: `send()` resolves the adapter (token read FRESH) → `asyncio.wait_for(adapter.send, send_timeout_s)` (the earner-safety HARD cap) → writes the send_log; plus `resolve_telegram_adapter`/`verify_telegram`/`derive_founder_chat_id`; NEVER raises |
| `comm/tests/*` | — | 2 offline suites (no network, no PG) |

### Verification
- **py_compile:** all 11 files compile clean.
- **`comm.tests.test_telegram_offline` — 22/22 PASS** (dormant-when-token-less; text→sendMessage+message_id; inline URL buttons; photo/video/document file_id cache; getMe verify; getUpdates private-chat-wins + group-ignored + cached; no-destination/no-media-source clean failures; token redaction — no leak). EXIT=0.
- **`comm.tests.test_engine_offline` — 9/9 PASS** (flag-OFF→`comm_disabled` no-I/O; non-telegram channel→`channel_not_enabled`; happy send returns the adapter result + mints `comms:` idem key; a HANGING adapter is killed by `wait_for`→`status='timeout'` (the earner cap); no-adapter→`no_channel_or_token`; send_log no-PG→False never raises; `status()` no-secret). EXIT=0.
- **Import-safe (empty env):** `import comm` + `import comm.engine` succeed with ZERO I/O; all flags report OFF; `engine.status()` clean. (Resting byte-identical.)
- **CI grep gate:** `import agent|from agent` over `comm/` = **0** matches (agent.py never imported).
- **gitleaks `protect --staged`:** **0 leaks** (~59 KB scanned). The only `bot...:SECRET` string is the deliberate redaction-test fixture in `test_telegram_offline.py`, not a real token.

### getMe / founder chat_id
The live `getMe` (ok=true, username `mr_kunal_bot`) was proven in W1-P0 against the real token in
the vault. THIS phase is offline (no box mutation per the directive) — the getMe path + the
getUpdates→founder-chat_id derivation are exercised by `test_telegram_offline` against a fake Bot
API (private-chat sender wins, cached). The REAL founder chat_id is derived at runtime by
`engine.derive_founder_chat_id("admin")` once the flags flip ON (the founder has tapped Start);
it is NOT hardcoded anywhere.

### The send contract (the seam the next phase consumes)
```
await comm.engine.send(
    tenant_id, SendEnvelope(to_ref=<chat_id>, kind="alert|summary|text|photo|...",
                            purpose="service", text=..., media=[MediaItem(url=<presigned>)],
                            buttons=[Button(text="Call Now", url=<panel_url>)]),
    slug="telegram-founder", session_id=..., outcome=...) -> SendResult(ok, status, external_id, ...)
```
The caller.py `_finalize_call` hook (NEXT phase) calls this via `asyncio.create_task(...)` — NEVER
awaited on the dial loop, with a synchronous payload snapshot — under the CALLER_EDIT_LOCK.

### Flags / Rollback
No flag flipped (build OFF). Rollback = delete the `droplet_work/comm/` package (additive; nothing
else altered; the W1-P0 vault row + DDL are independent).

**Status: DONE. Adapter + engine built, offline-green, import-safe, gitleaks 0, committed on
`fe/unify-run-wavec`. Next phase: `founder_alert.py` + `post_call.py` + `router.py` mount + the
caller.py `_finalize_call` insertions (CALLER_EDIT_LOCK).**

---

## W1-P2 — WEBHOOK + COMM ENDPOINTS + caller.py MOUNT · `fe/unify-run-wavec` · LIVE (flags ON)

**Scope:** Build the inbound webhook (FAIL-CLOSED) + the comm API endpoints, then MOUNT them in
`caller.py` via the CALLER_EDIT_LOCK (anchor-string, additive, flag-gated `COMM_ENABLED`). Deploy
the comm package + the mounted caller.py to the box; flip the flags ON for the founder tenant and
run the LIVE T-WEBHOOK probes. Earner gate before+after under an INDUCED Telegram outage.

### Files (NEW / EDIT, `droplet_work/comm/`)
| File | file:lines | What |
|---|---|---|
| `comm/webhook.py` | **1–214** | the FAIL-CLOSED inbound Telegram handler. Per-tenant `secret_token = HMAC-SHA256(signing, "telegram-webhook‖{tenant}‖{provider_def_id}")` (hex, domain-separated). `handle(tenant_id, header_value, raw)`: (1) dormant→403; (2) resolve the tenant's bot provider_def (bot-identity bind) or →403; (3) **constant-time `compare_digest` the X-Telegram-Bot-Api-Secret-Token header BEFORE any DB row** — no/wrong/other-tenant secret→403; (4) only AFTER verify, set the RLS GUC (inside `sessions.*`) + store the inbound turn; `update_id` idempotency; (5) ack 200 fast. **W1 reply-DISABLED** (the brain is W2). `_signing_secret()` reads `COMM_WEBHOOK_SIGNING_SECRET` → box `var/secret` (the SAME secret caller.py uses) → '' (fail-closed). NEVER raises. |
| `comm/sessions.py` | **1–250** | `comm_sessions` `get_or_create` (UNIQUE upsert) + `append_turn` (rolling-20, **server-side jsonb trim**) + `list_sessions`/`get_session`. RLS-scoped via `db.engine.session`; best-effort (no-PG→None/[]/False); never raises. |
| `comm/endpoints.py` | **1–250** | `build_router(resolve_tenant, can, need_auth, forbidden, *, require_super_admin=, firewall=, audit=)` (prefix `/comm`). Authed (token-derived tenant): `GET /channels`, `POST /channels/telegram/test` (getMe), `/derive-chat-id` (write), `/set-webhook` (write), `GET /sessions[/{id}]`, `POST /send` (write). UNAUTH: `POST /webhook/telegram/{tenant_id}` → `webhook.handle` (fail-closed). `COMM_ENABLED`-gated → **404 dormant**. (Intentionally NOT `from __future__ import annotations` so FastAPI resolves the `Request`/`Body` annotations as request params.) |
| `comm/router.py` | **1–17** | thin `build_router` re-export (caller.py mounts `from comm.router import build_router`). |
| `comm/engine.py` | +**202–263** | `set_telegram_webhook(tenant, url)` — `setWebhook` with the derived `secret_token` (https-only, bounded by `wait_for`). |
| `comm/__init__.py` | +1 | behavioural import-guard now pulls `sessions, webhook`. |
| `comm/tests/test_webhook_offline.py` | — | **17/17 PASS** — derive distinct-per-tenant; dormant/no-bot/no-header/wrong/cross-tenant→403 (+ no-store-before-verify = GUC-after-verify proof); correct→200 store; retry dedup; no-signing-secret→403; garbage body→200 no-raise. |
| `comm/tests/test_endpoints_offline.py` | — | **9/9 PASS** — flag-off→404 (incl. webhook); flag-on→200; no-auth→401; webhook unauth-fail-closed→403; read-only write→403. |

### caller.py mount (CALLER_EDIT_LOCK — additive, anchor-string from the box golden)
- **Lock:** acquired (no other wave held it; the video-activate wave's caller.py work was already
  deployed) → RELEASED after the earner gate. `CALLER_EDIT_LOCK.md`.
- **Edit:** ANCHOR after the `whatsapp-builder router mount failed` block → a new flag-gated
  `MODULE MOUNT — communication` block: `from comm.router import build_router`,
  `COMM_ENABLED = cfg_get(...)`, `build_router(resolve_tenant, can, need_auth, _forbidden,
  require_super_admin=require_super_admin, firewall=_firewall_mod, audit=_audit)` → `include_router`.
  Import-guarded (a broken comm pkg can never crash startup); a mount failure is swallowed.
- **Additive proof:** `diff` box-golden `44b867ea` vs mounted = **+43 lines, 0 deletions**, single
  hunk `7830a7831,7873`. py_compile clean (local + box). Box live caller.py md5: **`73d7be4f`**
  (local `caller.py.LIVEBOX.py` re-synced to match = the new golden).
- **Deploy:** backup `caller.py.COMMW1P2bak.20260614-201851` + `.env.COMMW1P2bak.*`; full comm pkg
  scp'd to `/opt/famit-agent/comm/` (W1-P1 modules were offline-only — deployed here for the first
  time); caller.py via md5-gated staged-then-move; restart **famit-caller ONLY**.

### Flags (LIVE — flipped ON for the founder tenant, NOT dormant)
`COMM_ENABLED=1` + `COMM_TELEGRAM_ENABLED=1` appended to `/opt/famit-agent/.env`. (`FEATURE_TELEGRAM_FOUNDER_ALERT` / `FEATURE_TELEGRAM_FOLLOWUP` stay OFF — their post-call `_finalize_call` hook is the next phase.)

### LIVE PROOF (over real HTTP, box `:8209`)
- **Routes LIVE:** `/comm/channels` + `/comm/sessions` → **401** (auth-gated, NOT 404). Flag-OFF (pre-flip) both → **404** (resting byte-identical — route table identical).
- **T-WEBHOOK 6/6 PASS:** (1) no secret→**403** · (2) wrong→**403** · (3) **other-tenant's secret on admin's path→403** (bound to the PATH tenant) · (4) correct→**200** `{ok,handled,stored:true,reply:false}` (row landed in admin's scope ⇒ GUC set AFTER verify) · (5) retry same `update_id`→**200 dedup** (no double-store) · (6) unknown tenant→**403**.

### EARNER GATE (before + after, under an INDUCED `api.telegram.org` black-hole — NOT a green path)
| Check | BEFORE | AFTER (under outage) |
|---|---|---|
| agent.py md5 (`9150fabe…`) | `9150fabe…` UNCHANGED | `9150fabe…` UNCHANGED |
| famit-agent MainPID | 2808658 | **2808658 (NOT restarted)** |
| caller `/health` | 200 | **200** |
| caller 5xx | 0 | **0** |
| webhook under outage | — | **fail-closed in 9ms** (pure HMAC, no Telegram I/O) |
| outbound send under outage | — | **bounded ≤0.7s** (engine `wait_for` cap; never hangs) |
| famit-caller | active (2819984) | active (2825728) — restarted by THIS wave only |
> Black-hole induced via `/etc/hosts` `127.0.0.1 api.telegram.org`, then **removed** (telegram
> reachability restored, 0 residual pins). NO ring placed (PLAYBOOK #4 — the founder's job).

### gitleaks / CI grep
`gitleaks protect --staged` = **0 leaks** (+ pre-commit hook clean). `import agent|from agent` over
`comm/` = **0**. Empty-env `import comm` rc 0 (resting). The `secret_token` is HMAC-derived (never
stored/committed/logged); the only `SECRET` literals are the deliberate test fixtures.

### Commits (`fe/unify-run-wavec`)
- `4acaf26` — webhook + endpoints + sessions + router + engine.set_telegram_webhook + the 2 offline suites.
- (this build-log + lock + state commit follows.)

### Rollback
`COMM_ENABLED=0` (instant, routes→404, resting byte-identical) → if needed restore
`caller.py.COMMW1P2bak.20260614-201851` + `.env.COMMW1P2bak.*` + restart famit-caller. The comm
package + DDL are additive (drop-safe).

**Status: DONE + LIVE. Webhook fail-closed + comm endpoints mounted + flags ON, earner gate green
under induced outage. Next phase: `founder_alert.py` + `post_call.py` + the caller.py `_finalize_call`
insertions (founder hot-lead alert + post-call auto-summary), under the CALLER_EDIT_LOCK.**
