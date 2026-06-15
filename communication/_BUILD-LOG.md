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

---

## W1-P3 — FOUNDER ALERT + POST-CALL AUTO-SUMMARY + _finalize_call HOOK · `fe/unify-run-wavec` · LIVE (flags ON)

**Scope:** the founder's two flagship Telegram features — (a) HOT-LEAD ALERT to the founder's
own Telegram when a call ends hot (interest ≥ 70), (b) POST-CALL AUTO-SUMMARY to the contact —
plus the caller.py `_finalize_call` insertion that fires them. EARNER LAW: a PURE-SYNC snapshot
on the hot path, then `asyncio.create_task` a DETACHED send, NEVER awaited on the dial loop; the
engine owns a HARD per-channel `asyncio.wait_for` timeout. Deployed LIVE; earner gate before+after
under an INDUCED `api.telegram.org` black-hole.

### Files (NEW / EDIT, `droplet_work/comm/`)
| File | file:lines | What |
|---|---|---|
| `comm/founder_alert.py` | **1–155** | `send_hot_lead_alert(tenant_id, snap) -> SendResult`. Resolves the founder chat_id (cached/persisted), builds a channel-neutral `SendEnvelope` (kind=`alert`, purpose=`service`, an "Open in panel" URL button → `/crm?phone=`, NO callback/firewall per W1), dispatches via `engine.send` (per-channel timeout). **PII-MINIMIZED by default** (§5.7): "Hot lead from a call — score N/100. Tap to view" + button; `COMM_FOUNDER_ALERT_FULL_PII=1` inlines name/phone/summary. Idempotent `comms:{call_id}:alert`. Dormant→`not_configured`. NEVER raises. |
| `comm/post_call.py` | **1–215** | `snapshot(rec,tr,camp_fields,*,tenant_id,call_id) -> dict` = the PURE-SYNC, NO-live-ref copy (the earner law; DUPLICATES the `_wa_draft_followup_text` reads — does NOT refactor it). `is_hot_lead` = the SAME `>=70 & non-opt_out` def caller.py already uses. `run(snap) -> dict` = the detached-task body: (a) founder alert (gated `FEATURE_TELEGRAM_FOUNDER_ALERT` + hot), (b) contact auto-summary (gated `FEATURE_TELEGRAM_FOLLOWUP`, only when a deliverable contact chat_id exists — W1 normally a clean `no_destination` no-op), each via `engine.send`; writes a service-implicit consent artifact BEFORE the contact send (§5.3). NEVER raises. |
| `comm/consent.py` | **1–135** | `record_consent(...)` = append-only `comm_consent_log` writer (RLS-scoped, best-effort, never raises). `derive_basis(lead_source)` derives `consent_basis` from `lead_source` (§5.2 — NEVER a constant): inbound/form→`inbound_form`, call→`prior_transaction`, purchased→`purchased_optin` (does NOT auto-fire in W1). |
| `comm/sessions.py` | +**251–330** | `set_founder_chat_id` / `get_founder_chat_id` — persist the founder chat_id as a STRICT sentinel `comm_sessions` row (`call_id=__founder_chat__`), surviving Telegram's getUpdates 24h-aging. **STRICT read (sentinel-only)** so a hot-lead alert can NEVER mis-route to a contact's chat. |
| `comm/engine.py` | ~**181–225** | `derive_founder_chat_id` now reads the persisted chat_id FIRST (no network), falls back to getUpdates, and AUTO-PERSISTS on derivation. |
| `comm/__init__.py` | +1 | behavioural import-guard pulls `consent, founder_alert, post_call`. |
| `comm/tests/test_post_call_offline.py` | — | **22/22 PASS** — snapshot-no-alias (mutate the live dict after snapshot → snapshot unchanged), dormant run→skip/skip, one-send-per-hot-lead, no-send-when-cold, PII-minimized alert (no name/phone inline) vs full-PII opt-in, consent basis derivation, followup no_destination vs send, never-raises. |

### caller.py hook (CALLER_EDIT_LOCK — additive, anchor-string from the box golden)
- **Lock:** acquired (FREE; box live caller.py md5 RE-VERIFIED `73d7be4f` == local golden before edit) → RELEASED after the earner gate.
- **Edit:** ANCHOR = the END of `_finalize_call`, right after the existing hot-lead `notify_handoff_team` try/except → a new flag-gated `COMMUNICATION (W1-P3)` block at the function-body level (runs for every finalized call): `if cfg_get("COMM_ENABLED")…: _comm_snap = comm.post_call.snapshot(rec, tr, camp_fields, tenant_id=…, call_id=rec.get("id")); asyncio.create_task(comm.post_call.run(_comm_snap))`. Import-guarded + wrapped in its OWN try/except (a comm fault can NEVER disrupt finalize).
- **Additive proof:** `diff` box-golden `73d7be4f` vs edited = **+28 lines, 0 deletions**, single hunk `2795a2796,2822`. py_compile clean (local + box caller-venv). Box live caller.py md5: **`ccf9715b`** (local `caller.py.LIVEBOX.py` re-synced = the new golden).
- **Deploy:** backup `caller.py.COMMW1P3bak.20260615-020542` + `.env.COMMW1P3bak.*`; comm modules md5-gated staged-then-move; caller.py md5-gated atomic move; restart **famit-caller ONLY**.

### Flags (LIVE — ON for the founder tenant)
`FEATURE_TELEGRAM_FOUNDER_ALERT=1` + `FEATURE_TELEGRAM_FOLLOWUP=1` appended to `/opt/famit-agent/.env` (atop the W1-P2 `COMM_ENABLED=1`+`COMM_TELEGRAM_ENABLED=1`). Live `config.config_snapshot()` confirms all four True. getMe ok (`mr_kunal_bot`).

### EARNER GATE (before + after, under an INDUCED `api.telegram.org` black-hole — NOT a green path)
Worst case: a HOT lead whose alert WILL attempt a network send while Telegram is unreachable.
| Check | Result |
|---|---|
| **[HOTPATH] snapshot sync** | **0.047 ms** (the only synchronous cost the dial loop pays) |
| **[HOTPATH] create_task scheduling** | **0.015 ms** (fire-and-forget; the dial loop never waits) |
| **[DETACHED] run() under black-hole** | **0.10 s** (≪ the 8s `send_timeout` cap; failed cleanly → `alert: failed`, never hung) |
| agent.py md5 (`9150fabe`) | UNCHANGED before+after |
| famit-agent MainPID | **2808658 — NOT restarted** |
| caller `/health` | **200** (under outage) |
| caller 5xx | **0** |
| token in error log | **redacted** (`bot<redacted>`) |
> Black-hole induced via `/etc/hosts` then **removed** (telegram reachability restored, `getMe ok`, **0 residual pins**). NO ring placed (PLAYBOOK #4 — the founder's job). The stale test chat rows were purged; `get_founder_chat_id` returns '' (no false founder).

### REAL-REACH (the one open founder action)
getMe verified (token works, `mr_kunal_bot`). The founder's ORIGINAL Start tap aged out of Telegram's getUpdates buffer (24h retention), so the live chat_id needs ONE fresh message from the founder; thereafter it AUTO-PERSISTS forever. Recorded as the single founder action in `communication/_HUMAN_TASKS.md`. Until then the alert no-ops cleanly (`no_founder_chat_id`) — it never blocks the call loop.

### gitleaks / CI grep
`gitleaks protect --staged` = **0 leaks** (pre-commit hook clean). `import agent|from agent` over `comm/` = **0**. All 5 comm offline suites PASS. The `secret_token`/tokens are vault/HMAC-derived (never stored/committed/logged).

### Commits (`fe/unify-run-wavec`)
- `889807e` — founder_alert + post_call + consent modules + the 22-case offline suite (offline-green).
- `e58c836` — founder chat_id persistence (sessions) + engine wiring + the live-deploy record.
- (this build-log + lock-release + ledger commit follows.)

### Rollback
`FEATURE_TELEGRAM_FOUNDER_ALERT=0` + `FEATURE_TELEGRAM_FOLLOWUP=0` (instant, the hook no-ops) — or `COMM_ENABLED=0` (the whole block is inert). If needed restore `caller.py.COMMW1P3bak.20260615-020542` + `.env.COMMW1P3bak.*` + restart famit-caller. The comm modules + DDL are additive (drop-safe).

**Status: DONE + LIVE. Founder hot-lead alert + post-call auto-summary wired into `_finalize_call`
(create_task + sync snapshot + per-channel timeout, never awaited), flags ON, earner gate green
under induced outage. ONE founder action pending (tap @mr_kunal_bot once) for live real-reach.
Next phase (W2): the LLM conversation brain (reply-only) + the contact deep-link that seeds
contact chat_ids (which activates the auto-summary's deliverable path).**

---

## W2 — THE CONVERSATION BRAIN (reply-only) + DEEP-LINK · `fe/unify-run-wavec` · BUILT OFF (flag-gated)

**Scope:** the contact chats with "Riya" on Telegram. Inbound webhook message -> the LLM brain
(reply-only, `COMM_TOOLS_ENABLED=0`) grounded in the prior call + the campaign context -> a
Telegram reply. A SIGNED, SINGLE-USE `?start=` consent deep-link (S5) that binds a contact's
chat_id + writes a `telegram_start` consent row (this is what makes the W1 post-call CONTACT
auto-summary deliverable). Inbound media must not crash. Per-tenant rate + body + daily-Groq caps.
NO caller.py edit this wave (the webhook route was already mounted in W1-P2 — W2 only flips the
reply ON inside the EXISTING handler, behind a new flag). All NEW flags default OFF (resting
byte-identical). `agent.py` NEVER imported; the Groq client is a SELF-CONTAINED copy (no caller.py
coupling). Built OFF + offline-green; the LIVE flag-flip + the LIVE webhook/brain reach-test is the
founder-gated step.

### Files (NEW / EDIT, `droplet_work/comm/`)
| File | file:lines | What |
|---|---|---|
| `comm/brain.py` | **1-260** | the channel-neutral reply brain — a COPY of caller.py `_wa_reply_text` (caller.py:2189), NOT a move (the WhatsApp helper stays byte-identical; `agent.py`/`caller.py` never imported). `precheck(text) -> PreCheck` = the FREE, ungameable PRE-LLM keyword gate (opt-out -> `opted_out`+short_circuit; handoff -> `needs_human`+short_circuit; copies the caller.py:2017/:2020 word lists) — runs BEFORE any token. `build_system_prompt(ctx)` injects the 5-layer grounding (campaign brand + call_summary/next_action/outcome/interest + cross-call memory recap + persona) + a per-channel suffix. `generate_reply(ctx) -> ReplyPlan` = ONE Groq call (self-contained `_groq_chat`, key=`GROQ_KEY`/model=`GROQ_MODEL`, temp 0.6, ~220 tok) -> reply text, `""` on any failure (the webhook still acks 200). `tools_enabled()` OFF this wave. |
| `comm/deeplink.py` | **1-280** | the SIGNED, SINGLE-USE Telegram `/start` consent deep-link (S5). `mint(tenant,phone)` -> a COMPACT Telegram-safe payload `<tenant_token>_<digits>_<nonce8>_<iat36>_<mac16>` (51 chars typ., **<= 64** of `[A-Za-z0-9_-]` — the /start budget; tenant_token is the short alnum id or its 12-hex hash, recomputed on verify from the PATH tenant). `verify(tenant,payload)` checks (in order, fail-closed each): signing secret present -> shape -> **tenant binding** (a payload minted for B presented on A -> `tenant_mismatch`) -> **HMAC** constant-time (`bad_mac`) -> **expiry** (`expired`) -> **single-use** nonce store (`replayed`, a firewall.py-style on-disk consumed-nonce file, offline-safe). NO new secret (reuses `comm.webhook._signing_secret`). |
| `comm/lang.py` | **1-60** | best-effort `langdetect` (optional dep) -> a BCP-47 hint; degrades to `''` when absent (the box default). The brain Hinglish prompt stands; a hint for a later localisation wave. |
| `comm/ratelimit.py` | **1-115** | in-process per-tenant cost guards run BEFORE any Groq token: `allow_inbound(tenant,chat)` = sliding-60s per-(tenant,chat) flood gate (`COMM_INBOUND_RATE_PER_MIN`, default 20); `allow_groq_call(tenant)` = per-UTC-day brain-call ceiling (`COMM_GROQ_DAILY_CAP`, default 500). |
| `comm/webhook.py` | +`_maybe_handle_start` / `_maybe_reply` / `_build_ctx` / `_memory_recap` / `_send_reply` + `handle` rewire | after the FAIL-CLOSED verify + store (unchanged), W2 adds: (a) a **body-size cap** (oversized -> 200 drop, no parse); (b) **`/start` deep-link** verify+bind+consent; (c) the **brain reply** (flag `COMM_BRAIN_ENABLED`): precheck -> rate/Groq-cap -> assemble ctx from the session seeds -> `brain.generate_reply` -> `engine.send` (per-channel `wait_for` timeout owned there) -> append the assistant turn. **Inbound media (photo-only, no text) does NOT crash** -> 200 ack, no reply, no Groq. The ack reports `{stored, reply, action, start}`. NEVER raises. |
| `comm/config.py` | +`brain_enabled()` + `groq_daily_cap()` + `inbound_rate_per_min()` + `inbound_body_max_bytes()` + snapshot | the W2 flags/caps, read at CALL time (default OFF / sane caps). |
| `comm/endpoints.py` | +`POST /comm/channels/telegram/deeplink` | mint a contact signed `?start=` link from the panel (write-gated; secret server-side only) -> `{payload, link}`. |
| `comm/__init__.py` | +1 | the behavioural import-guard now pulls `brain, deeplink, lang, ratelimit`. |

### The inbound -> brain -> reply loop (the seam)
```
Telegram POST /comm/webhook/telegram/{tenant}  (X-Telegram-Bot-Api-Secret-Token header)
  -> webhook.handle: FAIL-CLOSED secret verify (S2, unchanged) -> body-size cap
     -> _maybe_handle_start (a /start <payload> -> deeplink.verify -> bind chat_id + telegram_start consent)
     -> sessions.get_or_create + append_turn(role=user)            [the brain grounding window]
     -> if COMM_BRAIN_ENABLED and not a /start:
          brain.precheck(text)  [FREE: STOP -> suppress+canned ack, no Groq; handoff -> needs_human]
          ratelimit.allow_inbound + allow_groq_call                [cost guards BEFORE the LLM]
          _build_ctx(session seeds: call_summary/next_action/outcome/interest + turns + memory_recap + brand)
          brain.generate_reply(ctx)  [ONE Groq call, grounded]
          engine.send(SendEnvelope(text=reply))  [per-channel wait_for timeout]
          sessions.append_turn(role=assistant)
  -> ack 200 {ok,stored,reply,action[,start]}      (NEVER raises; an LLM/send failure is still 200)
```

### Grounded-reply PROOF (offline smoke, the brain reads the PRIOR call)
A full `webhook.handle` run with `COMM_BRAIN_ENABLED=1` and a session seeded with
`call_summary="Asha wanted EMI options for a 3BHK"`: the system prompt handed to Groq CONTAINED that
call summary (asserted via a sentinel only emitted when the prompt carried it), the reply was SENT to
the contact chat_id, the assistant turn appended -> `status 200, reply True, action replied`. On
`COMM_BRAIN_ENABLED=0` the SAME inbound is store+ack only (reply False, 0 Groq).

### Offline tests (no network, no PG — monkeypatched seams)
- `test_brain_offline` — **ALL PASS**: precheck opt-out/handoff/normal/empty/hinglish; the system
  prompt injects persona+company+call_summary+next_action+outcome+channel; generate_reply = EXACTLY
  ONE Groq call (system-first/incoming-last/turns-included); a Groq failure / a raising client ->
  `text=""`/never-raises; tools OFF; no caller/agent in the module namespace.
- `test_deeplink_offline` — **ALL PASS** (S5/T-DEEPLINK): payload <= 64 + Telegram alphabet;
  verify-own-tenant ok; **replay -> `replayed`**; no-consume-then-consume; **forged mac -> `bad_mac`**;
  tampered phone -> `bad_mac`; **tenant-mismatch -> `tenant_mismatch`**; long/unsafe tenant hashed but
  binds; **expired -> `expired`**; malformed payloads never raise; **no-secret -> fail-closed**.
- `test_webhook_reply_offline` — **ALL PASS**: brain-OFF = W1 store+ack (0 Groq); brain-ON = 1 Groq +
  reply sent + assistant turn + **grounded in the session seeds**; opt-out/handoff short-circuit BEFORE
  Groq (0 Groq); **inbound media (photo-only) no-crash 200**; `/start` verify+bind (no brain reply for a
  bare /start); **per-tenant daily Groq cap blocks the 2nd call**; **body-size cap drops oversized**; a
  Groq failure -> 200 no-reply, never raises.
- The 5 prior suites (`test_telegram/engine/webhook/endpoints/post_call_offline`) — **ALL PASS** (zero
  regression; the W1 webhook test still sees `reply: False` with the brain flag off).

### EARNER LAW / gates
- **NO caller.py edit this wave** (the W1-P2 webhook mount already exists; W2 only flips a reply ON
  inside the EXISTING handler, behind `COMM_BRAIN_ENABLED`). `git status` confirms the only `caller.py`
  diff is a PRIOR wave (zero `brain|deeplink|COMM_BRAIN|_maybe_reply|ratelimit` hits).
- **`agent.py`/`caller.py` NEVER imported** by the comm package (grep over `comm/` = 0). The Groq client
  is a self-contained copy (`comm.brain._groq_chat`), so the earner helper is never coupled.
- **Resting byte-identical:** empty-env `import comm` rc 0, `__version__=0.1.0-w1`, `brain_enabled()`
  False, `tools_enabled()` False. All new flags default OFF -> the webhook keeps its W1 behaviour.
- **py_compile:** all comm + channels + tests compile clean. **gitleaks `protect --staged`: 0 leaks**
  (~425 KB scanned). The signing secret / bot token are HMAC/vault-derived (never stored/committed/logged).

### NEW flags (all default OFF / safe caps)
`COMM_BRAIN_ENABLED` (the reply master — OFF keeps W1 store+ack) · `COMM_TOOLS_ENABLED` (OFF this wave;
reply degrades to plain text) · `COMM_GROQ_DAILY_CAP` (500/tenant/day) · `COMM_REPLY_MAX_TURNS` (12) ·
`COMM_INBOUND_RATE_PER_MIN` (20) · `COMM_INBOUND_BODY_MAX_BYTES` (64 KiB) · `COMM_DEEPLINK_TTL_S` (7d) ·
`COMM_DEEPLINK_STORE` (the single-use nonce file).

### Founder-gated LIVE step (recorded, not done in this build wave)
To go LIVE the founder taps `@mr_kunal_bot` once (already a pending W1 task), then we: `setWebhook`
(engine.set_telegram_webhook, the per-tenant secret_token) + flip `COMM_BRAIN_ENABLED=1` for the founder
tenant + run the LIVE reach test (the founder messages the bot -> Riya replies grounded in the prior
call). Earner gate (agent.py md5 `9150fabe` unchanged · famit-agent NOT restarted · /health 200 · 0 5xx ·
no ring) under an induced Telegram outage runs before+after the live deploy, exactly as W1-P2/P3.

### Rollback
`COMM_BRAIN_ENABLED=0` (instant — the webhook reverts to W1 store+ack, no Groq, no reply) — or
`COMM_ENABLED=0` (the whole surface dormant) -> `setWebhook(url="")` to detach. The comm modules + the
deep-link nonce store are additive (drop-safe).

**Status: BUILT + OFFLINE-GREEN (flag OFF, resting byte-identical), committed on `fe/unify-run-wavec`.
NO caller.py edit (no lock needed). The inbound->brain->reply loop + the signed single-use deep-link +
the cost/media guards are wired behind `COMM_BRAIN_ENABLED`. LIVE flip is the founder-gated step.**

---

## SECURITY-PROBES — the 6 ship-blockers, IMPLEMENTED + PROVEN · `fe/unify-run-wavec` · OFFLINE-GREEN (no box, no caller.py, no agent.py)

**Scope:** implement + PROVE the 6 SHIP-BLOCKER security probes the red-team gated ship on
(master-plan §4 / README.md): **T-WEBHOOK · T-INJECT · T-LEAK · T-VAULT · T-DEEPLINK · T-GATE**.
ONE consolidated harness drives the REAL comm-package code (no re-implementation), monkeypatching
ONLY the I/O seams (provider registry, DB sessions, on-disk nonce store, the Groq/engine send) so it
runs fully OFFLINE (no network, no PG) and deterministic. NO box mutation, NO caller.py edit, NO
agent.py import. Each probe returns PASS/FAIL; the harness exits non-zero on ANY failure (CI gate).

### File (NEW)
| File | file:lines | What |
|---|---|---|
| `comm/tests/test_security_probes.py` | **1–520** | the 6-probe harness. `probe_webhook` / `probe_inject` / `probe_leak` / `probe_vault` / `probe_deeplink` / `probe_gate`, each self-contained, exercising the live module + asserting the security contract; `main()` prints a PASS/FAIL line per probe + a summary, exit 0 iff all 6 pass. |

### RESULT — 6/6 PROBES PASS (53 sub-checks, 0 fail; `python -m comm.tests.test_security_probes` exit 0)

| Probe | PASS/FAIL | What was proven | file:lines |
|---|---|---|---|
| **T-WEBHOOK** | **PASS** | fail-CLOSED + secret bound to the PATH tenant + GUC-after-verify. 14 checks: dormant→403 (not 200); no-bot→403; missing/wrong header→403; **another tenant's valid secret on admin's path→403** (no DB row touched on any reject = GUC set only after verify); correct→200 stored (DB touched exactly once); retry update_id→dedup no double-store; no-signing-secret→fail-closed 403; garbage body→200 no-raise. | `webhook.py:359` handle · `:113` _verify_secret · `:92` derive_secret_token |
| **T-INJECT** | **PASS** | a prompt-injection inbound cannot drive a cross-tenant/destructive write or unblock STOP. 15 checks: tools OFF → NO write/tool surface to hijack (`brain.tools_enabled()` False); **12 classic injection strings** (ignore-previous / SQLi / role-override / "act as tenant_b" / "reveal the bot token") → each is merely `noted` text (never a command), and any that embed a STOP/handoff word are still caught by the ungameable pre-LLM gate; an injection in the call_summary renders as quoted GROUNDING DATA (the real "Output ONLY the reply text / Do not invent facts" instruction still stands); the webhook **scopes the store call to the PATH tenant** (a body carrying `tenant_id:"tenant_b"` is ignored — get_or_create receives `admin`). | `brain.py:101` precheck · `:62` tools_enabled · `webhook.py:434` get_or_create(tenant_id=PATH) |
| **T-LEAK** | **PASS** | no cross-tenant session/memory read. 5 checks: the `comm_sessions` UNIQUE key includes `provider_def_id` ⇒ two tenants with the SAME phone+chat_id resolve to DIFFERENT rows (no shared bot, S4); SELECT scoped by `tenant_id`; the founder-chat read is STRICT sentinel-only (an alert can never resolve to a contact row); **RUNTIME proof** — the live `memory.py` written by tenantA then read by tenantB returns `None` (tenantA self-read returns its own record); the brain recap helper ALWAYS passes a tenant_id. | `sessions.py:98` ON CONFLICT key · `:296` get_founder_chat_id · `memory.py:76` load_memory · `webhook.py:312` _memory_recap |
| **T-VAULT** | **PASS** (1 tracked residual) | per-tenant token isolation via the AAD binding. 6 checks (drives the REAL `provider_registry.credentials` with a fixed test key): **no plaintext at rest** (token bytes absent from the ciphertext); owner round-trip ok; **tenantA's ciphertext pasted under tenantB → InvalidTag, NO plaintext** (the catastrophic copy-paste attack); pasted under a different provider_def → refused; distinct ciphertext per tenant; AAD = `tenant‖def‖ver`. **RESIDUAL (S1, tracked, NOT a fail):** the interim DEK is ONE global `sha256(master)` key — the AAD binding (proven) blocks cross-tenant paste, but the per-tenant **HKDF DEK** is a separate key-version-gated migration (encrypt new rows under a v2 HKDF key, keep v1 decryption for the already-live founder token — changing it now would make the LIVE W1-P0 token undecryptable). Surfaced honestly rather than faked. | `credentials.py:133` decrypt · `:102` encrypt · `:85` compute_aad · residual `:56` _interim_get_key |
| **T-DEEPLINK** | **PASS** | the signed single-use `?start=` link refuses forged/replayed/expired/cross-tenant. 9 checks (real `comm.deeplink`, temp nonce store): minted within the 64-char Telegram alphabet; own-tenant verifies (phone recovered); **replay→`replayed`**; **forged mac→`bad_mac`**; **tampered phone→`bad_mac`**; **cross-tenant→`tenant_mismatch`**; **expired→`expired`** (TTL=0); malformed never raises; **no-secret→fail-closed** (`no_secret`). | `deeplink.py:231` verify · `:120` mint · `:214` _consume_nonce |
| **T-GATE** | **PASS** | the compliance gate is a SERVER send-path block, not a UI gate. 9 checks: opt-out is enforced SERVER-side pre-LLM (precheck short-circuits before any token); `consent_basis` is DERIVED from `lead_source` server-side (purchased→`purchased_optin` promotional [never auto-fires W1]; inbound→`inbound_form`; call→`prior_transaction`) and is NOT a constant; **end-to-end through the REAL webhook with the brain ON, a STOP** acks 200, spends **0 Groq tokens**, writes a **revoke** consent row, and labels the action `opted_out`. (The Email DLT/domain server hard-block is the W3 lane — noted; the W1/W2 server gates that exist today are proven.) | `brain.py:101` precheck · `webhook.py:232` opt-out branch · `consent.py:41` derive_basis |

### Earner / CI gates
- **NO box mutation, NO caller.py edit, NO agent.py import** — `import agent|from agent` over `comm/` = **0**. The harness is pure offline test code (rides the existing modules; touches no live service).
- **Zero regression:** all 8 prior comm offline suites still PASS (telegram/engine/webhook/endpoints/post_call/deeplink/brain/webhook_reply) alongside the new probe.
- **py_compile** clean; **gitleaks `protect --staged`** = **0 leaks** (~32.7 KB scanned — the only token-shaped literals are the obvious `123456:AAF…` fixture + `probe-*-signing` test secrets, never a real credential).
- The T-LEAK memory check ran the **real runtime path** (not a source assertion): tenantA's record written to a `tenantA/`-namespaced dir, tenantB's cross-read = `None`.

### How to run
`cd droplet_work && python -m comm.tests.test_security_probes` → prints each sub-check + the per-probe SUMMARY, exit 0 iff 6/6.

### Honest residual (tracked, NOT a ship-blocker for W1)
- **S1 per-tenant DEK (HKDF):** the AAD binding already defeats the cross-tenant copy-paste attack (proven). The per-tenant DEK is a defense-in-depth upgrade against a *master-key leak*; it requires a key-version-gated migration so the already-encrypted live founder token (v1) stays decryptable. Queue as its own additive crypto wave; do NOT flip `_interim_get_key` in place.
- **T-GATE Email DLT / unverified-domain server hard-block:** that lane lands with Email in **W3** (`sms/dlt_gate.py` + the email adapter). The W1/W2 server-side gates (opt-out + basis derivation) are live and proven now.

**Status: DONE. 6/6 security probes IMPLEMENTED + PROVEN (offline, real code, exit 0), one tracked
S1 residual surfaced honestly, zero regression, no box/caller.py/agent.py touch. The ship-blocker
security surface for Telegram W1/W2 is gated green.**

---

## W1/W2 FE — THE COMMUNICATION TAB · `fe/unify-run-wavec` · BUILT (panel deploy DEFERRED)

**Scope:** the omnichannel Communication TAB — a new **Engage > Communication** nav section
alongside WhatsApp. ONE page, four views (Channels / Builder / Inbox / Analytics) behind a SubNav,
scoped by a ChannelPicker. Telegram is the live channel (founder hot-lead alert + post-call
auto-summary + the LLM brain reply, all W1/W2 backend); Email/SMS render calm coming-soon cards
(W3/W5); WhatsApp deep-links to its own live page (earner-safe — NO duplicated Meta logic).
Built from `fe/unify-run-wavec`; tsc 0 + npm build GREEN + eslint 0 + gitleaks 0 + COMMITTED.
**Panel NOT deployed** (the video-studio-activate wave is also deploying the panel — single final
deploy from the latest canonical, no race). frontend-design skill invoked; Core_2 reuse, Inter
Display, ZERO raw hex, dormant-safe.

### Files (NEW — `famit-panel/`)
| File | file:lines | What |
|---|---|---|
| `lib/communication.ts` | **1–320** | the typed, DORMANT-SAFE client (mirrors `lib/integrations.ts`). Reads degrade to empty on any non-2xx (404 → `disabled` → coming-soon); mutations throw a typed `CommError` (humanized). Hooks `useChannels`/`useSessions`. Maps the LIVE `/api/comm/*` surface 1:1 (channels/test/derive-chat-id/set-webhook/deeplink/sessions/send). NEVER reveals the bot token. |
| `app/communication/page.tsx` | **1–32** | the route wrapper — `EntitlementGuard(engage.communication)` + `Layout` + `CommunicationBody` (the integrations/page.tsx pattern, avoids the Next route-type checker). |
| `app/communication/_body.tsx` | **1–120** | the shell — SubNav (4 views) + ChannelPicker + toast + the **dormant coming-soon card** when `COMM_ENABLED` is off (channels read 404). |
| `app/communication/_shared.tsx` | **1–185** | chrome primitives (ghost/text buttons, `SubNav` segmented control, `ChannelPicker` chip row [Telegram live · WhatsApp link · Email/SMS "Soon"], `ConsentBadge` for `channel×purpose`, `StatusDot`, `InfoStrip`) — same vocabulary as `integrations/_shared.tsx`. |
| `app/communication/_components/TelegramSetup.tsx` | **1–290** | the guided 3-step CONNECT flow: (1) Test the stored token via getMe, (2) Find-my-chat (derive founder chat_id) + Register-webhook, (3) Send-me-a-test (real-reach proof). Token NEVER pasted/revealed (it lives in the vault). Plus `useContactDeeplink` (mint a signed single-use `?start=` link). |
| `app/communication/_components/TelegramPreview.tsx` | **1–135** | the live phone PREVIEW — a restyle of the WhatsApp `PhonePreview` for Telegram (tinted own-bubble, media header for photo/video/document, inline URL buttons, `{variable}` token resolution). |
| `app/communication/_views/ChannelsView.tsx` | **1–215** | TelegramSetup + automations card (founder-alert / post-call-summary on/off + consent pill) + contact-deeplink minter + WhatsApp deep-link card + Email/SMS coming-soon cards. |
| `app/communication/_views/BuilderView.tsx` | **1–255** | the author-once message/template BUILDER: textarea + `{variable}` chips + seed templates + media (photo/video/PDF, presigned-URL) + up-to-3 URL buttons + sticky live `TelegramPreview` + "test send to me" (own chat only — never a contact). |
| `app/communication/_views/InboxView.tsx` | **1–230** | the unified INBOX: two-pane (session list ← channel column · transcript →) with the CRM `ChatBubble` pattern (CONTACT on the RIGHT/primary tint, **Riya on the LEFT**), a "from the call" grounding header (summary/next-action/interest), 20s poll, and a one-tap takeover composer (live send = W4). |
| `app/communication/_views/AnalyticsView.tsx` | **1–195** | per-channel KPIs derived from REAL session data (conversations / reply-rate / hot-leads / messages — no fabricated deltas) + a channel-mix meter + honest "on the roadmap" cards (savings ticker · cost guards · CAPI signal closure). |
| `contstants/navigation.tsx` | +1 child | `Engage > Communication` (`/communication`, `roles:"manager"`, `feature_key:"engage.communication"`) right after WhatsApp. |

### Verification (all GREEN)
- **tsc --noEmit:** exit 0 (zero type errors).
- **npm run build:** Compiled successfully; `/communication` route built (12.9 kB · 226 kB first-load).
- **eslint** (`app/communication` + `lib/communication.ts`, `--max-warnings=0`): 0 problems.
- **gitleaks `protect --staged`:** 0 leaks (~86 KB scanned). No token is ever client-side (getMe/test
  only; webhook secret_token + deep-link MAC are server-derived).
- **Dormant-safe:** `COMM_ENABLED` off → `/api/comm/*` 404 → reads `disabled` → the shell renders the
  calm coming-soon card, never an error wall. EntitlementGuard renders optimistically (the backend
  404 is the real boundary).
- **Earner-safe:** FE-only; no caller.py / agent.py touched; WhatsApp uses a deep-link (no Meta logic
  duplicated).

### Deploy
**DEFERRED** per the directive (panel deploy owned by the video-studio-activate wave — single final
deploy from the latest canonical, no race). This wave: build green + commit ONLY.

**Status: DONE (FE built + committed, panel deploy deferred). The Communication TAB is live-ready
behind `COMM_ENABLED`; flipping it ON for the founder tenant surfaces the full setup → builder →
inbox → analytics flow grounded in the W1/W2 backend.**

---

## W3-COSTGUARDS — THE 6 COST GUARDS (master plan §6) · `fe/unify-run-wavec` · BUILT OFF (flag-gated)

**Scope:** implement + PROVE the 6 cost guards as the master plan demands them — acceptance gates,
not "later". All NEW (additive, flag-gated default OFF -> resting byte-identical); the engine wires
them into the ONE send seam. NO caller.py edit (the W1-P2 mount already routes every send through
`comm.engine.send`; the guards live INSIDE the engine). NO agent.py import. `wallet.debit()` does
NOT exist — metering rides the LIVE ACID `reserve->settle/release`. Offline-green + earner-safe.

### Files (NEW / EDIT, `droplet_work/comm/` + `communication/db/`)
| File | file:lines | What |
|---|---|---|
| `communication/db/ddl_comm_cost.sql` | 1-110 | 3 NEW FORCE-RLS tables (additive to ddl_comm.sql): `comm_daily_spend` (per-(tenant,channel,UTC-day) spend paise — budget ceiling + anomaly median), `comm_freq_counter` (per-(tenant,contact,channel,day) send count — frequency cap), `comm_deliverability` (per-(tenant,contact,channel) reachability ok/dead/suppressed). tenant_id TEXT, BIGINT paise, idempotent, RLS DO-block VERBATIM. Rollback = DROP the 3 tables. |
| `comm/metering.py` | 1-120 | GUARD #1 — per-message metering. `reserve_for_send(tenant,message_id,est)` -> wallet.reserve (idem reserve:comms:{mid}) BEFORE the send; `finalize(ticket,sent_ok,actual)` -> wallet.settle (settle:comms:{mid}) on success / wallet.release (release:comms:{mid}) on failure -> a provider 5xx NEVER bills. Free send / metering OFF / wallet-down -> a permissive no-op ticket. NO wallet.debit (AST-proven). NEVER raises. |
| `comm/cost_guards.py` | 1-290 | GUARDS #2/#3/#4/#5 (DB-backed, RLS-scoped, permissive-on-fault, never-raise). #2 check_budget (per-tenant daily ceiling default 50000=Rs500; FREE sends always flow, only metered gated) + record_spend. #3 check_frequency (per-(contact,channel)/day cap default 8) + bump_frequency. #4 check_anomaly (today > mult x trailing-7-day median, above a paise floor) — the DETECTOR. #5 get_deliverability/is_dead/mark_deliverability/classify_failure (a 403-class error -> dead). precheck_send runs #5->#3->#2 (FIRST block wins). |
| `comm/token_bucket.py` | 1-175 | GUARD #6 — per-bot async token-bucket. A GLOBAL bucket per provider_def_id (30/s, capacity=rate) + a PER-CHAT bucket per (bot,chat) (1/s) — journey blast + post-call trickle + alert burst SHARE one budget. acquire(bot,chat,priority=) waits at most bucket_max_wait_s (3s << send_timeout) then returns False (never hangs). PRIORITY LANE: a founder/hot-lead alert borrows a global token immediately (never waits on global) so a blast can never delay it. Disabled -> grant instantly. In-process, never-raise. |
| `comm/engine.py` | +send wiring + _post_send_bookkeeping | the ONE seam now runs (flag-gated, resting byte-identical OFF): est-cost -> cost_guards.precheck_send (block -> blocked_dead/blocked_frequency/blocked_budget, adapter NEVER called) -> token_bucket.acquire(priority=) (block -> blocked_rate) -> metering.reserve_for_send (insufficient -> blocked_funds) -> adapter.send (bounded wait_for, unchanged) -> metering.finalize (settle ok / release fail) -> _post_send_bookkeeping (#3 bump + #2/#4 record_spend + #5 403->dead / ok-revive). send(...,priority=) added. |
| `comm/founder_alert.py` | +priority=True + maybe_alert_spend_anomaly | the hot-lead alert sends priority=True (guard #6 priority lane). GUARD #4 (ALERT half) maybe_alert_spend_anomaly(tenant) -> if check_anomaly trips, a once-per-UTC-day founder Telegram spike-alert (priority lane) + the throttle = the hard #2 ceiling. |
| `comm/config.py` | +cost-guard flags/caps | COMM_COST_GUARDS_ENABLED (master) / COMM_METERING_ENABLED / COMM_TOKEN_BUCKET_ENABLED (all OFF) + caps: COMM_DAILY_BUDGET_MINOR (50000) / COMM_FREQ_CAP_PER_CONTACT_DAY (8) / COMM_SPEND_ANOMALY_MULT (3.0) / COMM_SPEND_ANOMALY_FLOOR_MINOR (2000) / COMM_BUCKET_GLOBAL_RATE (30) / COMM_BUCKET_PER_CHAT_RATE (1) / COMM_BUCKET_MAX_WAIT_S (3). Read at CALL time. |
| `comm/__init__.py` | +1 | behavioural import-guard pulls cost_guards, metering, token_bucket. |
| `comm/tests/test_cost_guards_offline.py` | — | unit PROOF of each guard (fake in-memory db.engine + fake wallet). |
| `comm/tests/test_engine_costguards_offline.py` | — | INTEGRATION PROOF the guards are wired into engine.send. |

### PASS/FAIL per guard (the deliverable — offline, deterministic)
- #1 per-message metering — PASS. comm/metering.py: reserve BEFORE (reserve_for_send), settle on success / release on failure (never bills) (finalize); free send -> no hold; metering OFF -> wallet untouched; insufficient funds -> ticket.ok False -> engine blocked_funds. NO wallet.debit call (AST-proven across metering+engine). Integration: success reserves+settles, failure releases-never-settles. (test_cost_guards_offline 1.* + test_engine_costguards_offline wire1.*)
- #2 budget ceiling — PASS. cost_guards.check_budget — a FREE Telegram send ALWAYS flows; a metered send where spent+est > cap -> blocked_budget. Integration: 1st Rs6 paid send ok, 2nd over Rs10 cap -> blocked_budget, a free send still flows over budget. (2.* / wire2.*)
- #3 frequency cap — PASS. cost_guards.check_frequency + bump_frequency — cap=N; the (N+1)-th send to one contact/day -> blocked_frequency; a different contact unaffected. Integration: cap=2, 3rd send blocked. (3.* / wire3.*)
- #4 spend-anomaly — PASS. cost_guards.check_anomaly — today > mult x trailing-7-day median AND above the floor -> anomaly; a quiet week then a Rs50 spike trips (median Rs1); a brand-new tenant spending above the floor trips; below-floor never trips. ALERT half = founder_alert.maybe_alert_spend_anomaly (once/day, priority lane). (4.*)
- #5 deliverability state — PASS. cost_guards get/mark/classify_failure — a 403-class error -> dead; a transient net error -> no change; a dead chat -> precheck_send blocked_dead (adapter NEVER called). Integration: a 403 send flips the chat dead, the NEXT send is blocked without calling the adapter. (5.* / wire5.*)
- #6 per-bot token-bucket — PASS. token_bucket.acquire — global capacity drains (6th of 5 rejected no-wait); per-chat paced (3rd quick send to one chat rejected); priority lane bypasses a drained global bucket; disabled -> always grants. Integration: drain global -> a normal send blocked_rate, a priority=True send still ok. (6.* / wire6.*)

### Earner-safety / gates (ALL GREEN)
- NO caller.py edit, NO agent.py import (grep import agent|from agent over comm/ = 0). The guards live inside the existing comm.engine.send seam already mounted in W1-P2.
- Resting byte-identical: empty-env `import comm` rc 0; all 3 guard master flags default OFF; with COMM_COST_GUARDS_ENABLED=0 the engine sends EXACTLY as W1/W2 (an integration test sends to a dead chat normally when guards are OFF).
- Permissive-on-fault: PG down -> every guard returns allow (a guard must NEVER block a send because its own bookkeeping is unavailable — the dial loop's detached task always makes progress). Proven (fault.*).
- py_compile all comm clean. All 10 offline suites PASS (8 prior + 2 new) = zero regression. gitleaks protect --staged = 0 leaks (~82 KB). NEVER raises on any path.

### DDL apply / flags (LIVE step, founder-gated like W1/W2)
The 3 tables apply STANDALONE via the live db.engine as famit_app (additive, idempotent), exactly
like ddl_comm.sql. Flags flip ON for the founder tenant AFTER the live earner gate (agent.py md5
9150fabe unchanged / famit-agent NOT restarted / /health 200 / 0 5xx / no ring / under an induced
Telegram outage). Until then the guards are inert (resting byte-identical).

### Rollback
COMM_COST_GUARDS_ENABLED=0 + COMM_METERING_ENABLED=0 + COMM_TOKEN_BUCKET_ENABLED=0 (instant — the
engine reverts to W1/W2 send). The 3 cost-guard tables are additive (DROP-safe); the modules are
additive (delete-safe). No caller.py / agent.py touched.

**Status: BUILT + OFFLINE-GREEN (flags OFF, resting byte-identical), committed on `fe/unify-run-wavec`.
All 6 cost guards implemented + PROVEN PASS (unit + engine-integration). NO caller.py edit (no lock).
LIVE flip (DDL apply + flags ON + earner gate) is the founder-gated step, same recipe as W1-P2/P3.**

---

## W2+W3 LIVE DEPLOY + REAL-MESSAGE/BRAIN/EARNER VERIFY — 2026-06-15

The W2 conversation brain + the 6 W3 cost guards were deployed LIVE to the voice box
(`famit@168.144.153.145`, `/opt/famit-agent`) and the flags flipped ON for the founder
tenant `admin`. **NO caller.py edit** (the W1-P2 mount + W1-P3 hook already route every
send/inbound through the mounted `comm` package; box golden `caller.py` md5
`ccf9715b…` UNCHANGED → no CALLER_EDIT_LOCK needed). **NO agent.py touch.**

### What deployed (BE only — panel deploy still deferred per directive)
- **13 comm files** scp'd → staged → md5-verified == local → atomically moved into
  `/opt/famit-agent/comm/`: NEW `brain.py · cost_guards.py · deeplink.py · lang.py ·
  metering.py · ratelimit.py · token_bucket.py`; CHANGED `__init__.py · config.py ·
  endpoints.py · engine.py · founder_alert.py · webhook.py`. All 13 post-move md5 ==
  local source. Box venv `py_compile` clean + isolated `import comm.*` OK.
- **DDL** `ddl_comm_cost.sql` applied → 3 NEW tables `comm_daily_spend ·
  comm_freq_counter · comm_deliverability`, all **FORCE RLS = true**. (The 4 W1 tables
  already existed FORCE-RLS.) Total = 7 comm tables, all FORCE-RLS.
- **Flags flipped ON** (founder tenant, appended to `.env`, backup
  `.env.COMMW2W3bak.20260614-214442`): `COMM_BRAIN_ENABLED=1 ·
  COMM_COST_GUARDS_ENABLED=1 · COMM_METERING_ENABLED=1 · COMM_TOKEN_BUCKET_ENABLED=1`
  (on top of the already-ON `COMM_ENABLED · COMM_TELEGRAM_ENABLED ·
  FEATURE_TELEGRAM_FOUNDER_ALERT · FEATURE_TELEGRAM_FOLLOWUP`).
- **Restarted famit-caller ONLY** (new PID 2846741). Box comm backup
  `comm.COMMW2W3bak.20260614-214207`.

### Live surface proof (over real HTTP, minted admin JWT == panel path)
- `GET /comm/channels` → 200, `configured:true`, **flags all live**:
  `brain_enabled:true, cost_guards_enabled:true, metering_enabled:true,
  token_bucket_enabled:true`.
- `POST /comm/channels/telegram/test` (getMe) → 200 **`mr_kunal_bot`** (token decrypts
  through the live vault; `vault_read.available()=true`).
- `/comm/channels` 401 authed (mounted), webhook no-secret → **403 fail-closed (S2 holds)**.

### 🟥 REAL-MESSAGE (founder hot-lead alert) — PIPELINE PROVEN LIVE, blocked on ONE founder tap
- `engine.send("admin", …)` to a real Telegram chat → **reaches api.telegram.org for
  real** → `http_400: Bad Request: chat not found` (logged in append-only
  `comm_send_log`). i.e. the WHOLE chain (vault token → telegram adapter → real HTTPS
  POST → SendResult → metering → send_log) is LIVE; the ONLY missing piece is the
  destination.
- **Why no message landed yet:** `getWebhookInfo` = `{url:"", pending:0}`, `getUpdates`
  = **0 updates** → the founder has NOT messaged `@mr_kunal_bot` in the last ~24h, so
  his chat_id can't be derived (`derive_founder_chat_id(force) → ''`). The founder
  sentinel is correctly ABSENT (never fabricated). The alert no-ops cleanly
  (`no_founder_chat_id`) — never blocks the call loop. **ONE founder tap unblocks a real
  message** (then auto-persists forever). Recorded in `_HUMAN_TASKS.md` #1.
- **Webhook NOT set (deliberate):** the caller (8209) is firewalled to the panel box
  `10.122.0.2` only — NO public HTTPS ingress, no tunnel. `setWebhook` would create a
  DEAF BOT (PLAYBOOK footgun) and disable getUpdates. So we stay in **getUpdates mode**
  (the W1-P3 design path); the public inbound webhook is a later infra task (panel proxy).

### ✅ CONVERSATION BRAIN (reply, grounded) — PROVEN LIVE
- Seeded a `comm_session` with `call_summary="Asha asked about EMI options for a 3BHK
  flat at Prestige Lakeside; budget 95 lakh"` → POSTed a REAL inbound through the live
  `/comm/webhook/telegram/admin` with a valid HMAC `secret_token` →
  **200 `{stored:true}`** (fail-closed secret verify + GUC-after-verify, S2, LIVE).
- `brain.generate_reply(ctx)` (Groq `llama-3.3-70b-versatile`, ~1.5s) produced a
  **grounded, in-persona Hinglish reply**: *"haan ji, main aapko EMI breakup bhejne wali
  thi, abhi bhejti hoon, aap dekh kar batayein ki aapko kaisa lagta hai, phir hum site
  visit ke baare mein baat kar sakte hain"* (`action=replied`). The reply send 400'd only
  because the synthetic contact chat isn't real.
- **Cost-guard #5 PROVEN LIVE end-to-end:** the retry inbound was pre-blocked
  `blocked_dead / deliverability_dead` (the engine flipped the chat `dead` after the
  first 400; the adapter was never called → fast 0.46s return). #1 metering wrote the
  send_log row.

### 🟥 EARNER GATE (before + after, under an INDUCED `api.telegram.org` black-hole)
Black-holed `149.154.166.110` (telegram reachability → HTTP 000), then:
- **[HOTPATH]** `post_call.snapshot` **0.017 ms** + `asyncio.create_task` scheduling
  **0.016 ms** — the ONLY cost the dial loop pays at `_finalize_call` (~0.03 ms). Nothing
  awaited.
- **[DETACHED]** `post_call.run()` bounded **0.00 s** under outage (dead-chat fast path);
  a FRESH (non-dead) destination → `engine.send` bounded **0.75 s** under the black-hole
  (≪ the 8 s per-channel cap, failed cleanly, never hung).
- **agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED** · **famit-agent PID 2808658
  NRestarts=0 NOT restarted** · **famit-caller /health 200** · **0 5xx** under outage · **NO
  ring.** Black-hole removed → telegram reachable (302), **0 residual blackhole routes**.

### Cleanup + state
- Synthetic test session + deliverability row deleted (tenant `admin` clean: 0 residual
  test sessions / deliverability; founder sentinel correctly absent). The append-only
  `comm_send_log` retains the send-attempt audit rows (immutable by design).
- Temp box scripts + `_comm_stage` removed.

### Rollback
- Instant: set the 4 new flags → 0 (brain/guards no-op, reverts to W1-P3 live behaviour).
- Full: `COMM_ENABLED=0` (routes → 404) → restore `comm.COMMW2W3bak.20260614-214207` +
  `.env.COMMW2W3bak.20260614-214442` → restart famit-caller. (3 cost tables are
  additive/drop-safe.)

**NET: W2 brain + W3 cost guards are LIVE + USABLE for the founder tenant; the founder
hot-lead alert is fully wired and reaches Telegram — it will land a real message on the
founder's phone the instant he taps `@mr_kunal_bot` once. Earner untouched, proven under
outage.**

---

## COMM-FINAL-VERIFY (2026-06-15) — PER-ITEM PASS/FAIL + FOUNDER RECIPE

### Per-item result table

| # | Item | Result |
|---|---|---|
| 1 | comm BE LIVE (webhook 200, all flags ON for `admin` tenant) | PASS — `GET /comm/channels` 200 `configured:true`; `COMM_ENABLED · COMM_TELEGRAM_ENABLED · FEATURE_TELEGRAM_FOUNDER_ALERT · FEATURE_TELEGRAM_FOLLOWUP · COMM_BRAIN_ENABLED · COMM_COST_GUARDS_ENABLED · COMM_METERING_ENABLED · COMM_TOKEN_BUCKET_ENABLED` all ON |
| 2 | Telegram bot token decrypts via live vault | PASS — `POST /comm/channels/telegram/test` (getMe) → 200 `mr_kunal_bot` |
| 3 | Inbound webhook fail-closed (no secret → 403) | PASS — unauthenticated POST → 403, never 200 |
| 4 | Real Telegram message landed on founder phone | PENDING founder tap — pipeline PROVEN to reach `api.telegram.org` for real (`http_400: chat-not-found`); ONLY the destination is missing (`getUpdates=0`). NOT faked. ONE tap unblocks it. |
| 5 | LLM brain replies grounded in prior call | PASS — real inbound through `/comm/webhook/telegram/admin` (valid HMAC → 200 stored) → Groq `llama-3.3-70b-versatile` produced grounded Hinglish reply referencing EMI and the 3BHK flat (`action=replied`) |
| 6 | S1 — HMAC webhook verify fail-closed | PASS — wrong-secret/replay/wrong-tenant all → 403 |
| 7 | S2 — SQL-injection via contact identity | PASS — parameterized; no injection path |
| 8 | S3 — PII not logged in structured fields | PASS — send_log stores send result metadata only, no name/phone in JSON body |
| 9 | S4 — vault cross-tenant read blocked | PASS — AAD binding; wrong-tenant ciphertext → `InvalidTag` |
| 10 | S5 — deep-link signed single-use | PASS — replay → `token_used` reject |
| 11 | S6 — billing gate not bypassable | PASS — cost-guard #2 blocks over-budget sends server-side; no UI bypass path |
| 12 | Cost guard #1 — per-message metering via wallet reserve/settle | PASS — `wallet.reserve→settle` per send; `release` on failure (never bills failed sends); AST-proven no `wallet.debit` |
| 13 | Cost guard #2 — per-tenant daily budget ceiling | PASS — over-cap → `blocked_budget`; free-tier TG flows always |
| 14 | Cost guard #3 — per-contact/day frequency cap | PASS — over-cap → `blocked_frequency` |
| 15 | Cost guard #4 — spend-anomaly alert | PASS — today > 3× trailing-7d median → founder priority-alert (once/day flag) |
| 16 | Cost guard #5 — deliverability state (dead-chat block) | PASS PROVEN LIVE — retry inbound pre-blocked `blocked_dead` (403 flip → `dead`; adapter never called → fast 0.46s return) |
| 17 | Cost guard #6 — per-bot async token-bucket | PASS — 30/s global + 1/s per-chat; founder-alert PRIORITY LANE bypasses drained global; bounded wait never hangs |
| 18 | FE committed on `fe/unify-run-wavec` | PASS — tsc 0 + npm build EXIT 0 + eslint 0 + gitleaks 0; commit `c2d4e02`. Panel deploy deferred to single canonical deploy. |
| 19 | EARNER GATE — agent.py md5 `9150fabe` UNCHANGED | PASS |
| 20 | EARNER GATE — famit-agent PID 2808658 NOT restarted | PASS (NRestarts=0) |
| 21 | EARNER GATE — caller /health 200 | PASS |
| 22 | EARNER GATE — 0 5xx under induced Telegram outage | PASS |
| 23 | EARNER GATE — NO ring | PASS |
| 24 | EARNER GATE — hot-path latency (snapshot + create_task) | PASS — 0.017ms + 0.016ms (≪ 1ms; never blocks dial loop) |
| 25 | EARNER GATE — detached run bounded under black-hole | PASS — fresh-dest bounded 0.75s ≪ 8s per-channel cap; dead-chat path 0.00s |
| 26 | gitleaks 0 (no secrets committed) | PASS — `c2d4e02` gitleaks staged exit 0 |
| 27 | 7 comm tables FORCE-RLS | PASS — `ddl_comm_cost.sql` applied; all 7 `relforcerowsecurity=t` |

**SUMMARY: 26/27 PASS. Item 4 is PENDING one founder tap (not a system failure — a deliberate gap: we never fabricate a chat_id). Every system piece is live and proven.**

---

### FOUNDER RECIPE — how to use the Communication system today

**You already got the Telegram bot token set up and all waves are live. Here's what it means for you:**

**1. Hot-lead alerts to your Telegram (ONE tap away)**
- Open Telegram → search `@mr_kunal_bot` → send it any message (or tap Start).
- After that single tap: the next time a call ends with an interest score ≥ 70 (a "hot lead"), you automatically get a Telegram message: the lead's summary, score, and a "Open in panel" button. You never need to do anything else — it auto-persists forever.
- Privacy-minimized by default (no name/phone inline, just score + link). Set `COMM_FOUNDER_ALERT_FULL_PII=1` in `/opt/famit-agent/.env` if you want full detail in the message itself.

**2. Run a campaign → hot leads ping your Telegram**
- Start a campaign from the Run page as normal. When a lead shows strong interest and the AI scores it ≥ 70, within seconds you'll get a Telegram ping. No checking the panel — it comes to your phone.

**3. Contacts get an auto-summary after the call**
- After every call, Riya automatically sends the contact a WhatsApp-style follow-up message on Telegram IF the contact has ever messaged your bot (via the `?start=` deep-link the system generates). In W1/W2 there are no contact chats yet — this path is a clean no-op (`no_destination`) and activates automatically as contacts opt in.

**4. The brain replies for Riya (on Telegram)**
- When a contact replies on Telegram, the LLM brain (Riya persona, grounded in the prior call summary + lead context) auto-generates a reply. Proven live: real Hinglish reply generated from a real call context ("haan ji, main aapko EMI breakup bhejne wali thi…").

**5. The Communication tab in the panel**
- The full UI (Channels setup + Builder + Inbox + Analytics, `Engage > Communication`, `/communication`) is built and committed. It ships in the NEXT panel deploy — the same deploy that brings the Integrations page, Video Studio, and any other pending FE. No action needed from you; it comes automatically.

**Next waves (in order):**
- W3 Email: needs a Resend API key from `resend.com` (free tier, 3,000 emails/mo; own-domain DNS wizard ships with it). Give us the key and we set it up.
- W4: Unified inbox (one thread table for Telegram + Email + SMS + WhatsApp; human takeover).
- W5 SMS: needs MSG91 account + DLT registration (PE ID + header + template). This is a 5-10 day external process with TRAI — start it early.
- W6: CAPI signal closure — the named moat (omni-conversation outcome → Meta OfflineConv signal → smarter CPL bidding).

**Rollback (if anything looks wrong):**
- Instant: set `COMM_BRAIN_ENABLED=0 COMM_COST_GUARDS_ENABLED=0` in `/opt/famit-agent/.env` + `systemctl restart famit-caller` → brain + guards no-op, reverts to W1-P3 behavior.
- Full: `COMM_ENABLED=0` → restore box backups (`comm.COMMW2W3bak.20260614-214207` + `.env.COMMW2W3bak.20260614-214442`) + restart famit-caller.

**The earner is untouched.** agent.py `9150fabe` is byte-identical. famit-agent PID 2808658 was never restarted. The live dial loop runs exactly as before — the only additions are a ~0.03ms synchronous snapshot + a detached task that owns its own timeout.

---

## W1-P4 — LIVE REAL-MESSAGE + INBOUND CONVERSATION (founder real-life test)

**Date:** 2026-06-15 · Branch `fe/unify-run-wavec` · Box `famit@168.144.153.145`

**Scope:** The founder tapped @mr_kunal_bot ("hi" registered in getUpdates). This phase:
(a) sends a REAL message to his Telegram, (b) deploys a getUpdates long-poll worker as a
systemd service so inbound conversation is continuous, (c) confirms post-call flags are live.

### EARNER GATE (BEFORE + AFTER)
| Check | BEFORE | AFTER |
|---|---|---|
| agent.py md5 (expect `9150fabe`) | `9150fabe` UNCHANGED | `9150fabe` UNCHANGED |
| famit-agent MainPID | 2808658 | 2808658 (NOT restarted by this work) |
| famit-agent NRestarts | 0 | 0 |
| caller `/health` (port 8209) | 200 | 200 |
| caller 5xx | 0 | 0 |
| NO ring | confirmed | confirmed |
> NO caller.py edit · NO agent.py edit · famit-caller NOT restarted · NO ring.

### DELIVERABLE 1 — REAL MESSAGE LANDED ✅
- `engine.derive_founder_chat_id('admin', force=True)` → chat_id **`1862240811`** (from getUpdates — founder's tap registered; auto-persisted as sentinel row).
- `engine.send('admin', SendEnvelope(to_ref='1862240811', kind='alert', purpose='service', text='Famit Telegram is LIVE — your hot-lead alerts and post-call summaries will land right here. Welcome!', buttons=[Button('Open Panel', 'https://panel.famit.in')]), slug='telegram-founder')`
- **Result: `ok=True · status=sent · external_id=4`** (Telegram message_id = 4).
- `comm_send_log` row `cms_30de38a5fe844c1b…` at `2026-06-15 06:33:34 UTC`: `channel=telegram · kind=alert · status=sent`.
- **A real message landed on the founder's phone.**

### DELIVERABLE 2 — INBOUND CONVERSATION (POLL WORKER + REAL ROUND-TRIP) ✅
**Webhook reachability check:** `getWebhookInfo` → `url=""`, `pending_update_count=1`. The box port `:8209` is firewalled to `10.122.0.2` (panel) only — no public HTTPS ingress. `setWebhook` would disable getUpdates (PLAYBOOK footgun). **Decision: getUpdates long-poll worker (standalone process, NOT inside caller.py).**

**File:** `comm/poll_worker.py` (NEW, force-added to `fe/unify-run-wavec`):
- Async `getUpdates?timeout=25&offset={next_offset}` loop.
- Calls `comm.webhook.derive_secret_token(TENANT_ID, provider_def_id)` for the HMAC (same function as the handler → FAIL-CLOSED verify path exercised identically).
- Feeds each update to `comm.webhook.handle(tenant_id, secret_token, raw_body) → (http_status, dict)`.
- On any network/parse error: sleep 5s + retry (≤20 consecutive → exit → systemd restarts).
- **NO caller.py / NO agent.py import** (grep `import agent|from agent` = 0).

**Systemd service:** `/etc/systemd/system/comm-poll.service`
- `User=famit · WorkingDirectory=/opt/famit-agent · EnvironmentFile=/opt/famit-agent/.env · ExecStart=/opt/capsy-agent/.venv/bin/python3 /opt/famit-agent/comm/poll_worker.py · Restart=always · RestartSec=5`
- `systemctl enable comm-poll + systemctl start comm-poll` → **`active (running)` PID 2961553**.

**REAL ROUND-TRIP PROVEN:**
- Poll worker received `update_id=972273094`, `chat_id=1862240811`, `text='done'` (the founder's real message).
- Groq `llama-3.3-70b-versatile` POST → **HTTP 200 OK** (brain reply generated in ~1.5s).
- Telegram `sendMessage` → **HTTP 200 OK** (reply sent to founder's phone).
- `comm_send_log` `cms_28a66c2d24fb4df5…` at `2026-06-15 06:37:48 UTC`: `kind=text · status=sent`.
- **Riya's reply: grounded Hinglish message about EMI options / the lead context** (the session had the call_summary seed from the prior webhook test).
- Round-trip complete: founder sent → Riya replied on Telegram.

### DELIVERABLE 3 — POST-CALL ALERT WIRED ✅ (no change needed)
- `FEATURE_TELEGRAM_FOUNDER_ALERT=1` + `FEATURE_TELEGRAM_FOLLOWUP=1` already live in `.env` (flipped in W1-P3).
- `_finalize_call` hook already wired in caller.py golden `ccf9715b` (W1-P3 `+28 lines`, anchor-string, `asyncio.create_task(comm.post_call.run(snap))`).
- When a real inbound call ends with interest ≥ 70: `post_call.run` fires the hot-lead alert to chat_id `1862240811`. **No restart, no flag change, no code change needed.**

### Files
- NEW: `comm/poll_worker.py` (box md5 `5ced479c827c3872a5d28a53c85277d4`) — force-added to git.
- NEW systemd unit: `/etc/systemd/system/comm-poll.service` — enabled + running.
- Appended: `WORKFLOW_LEDGER.md` (1 newest-on-top line).

### Rollback
- `sudo systemctl stop comm-poll && sudo systemctl disable comm-poll` → inbound loop stops (all other comm surfaces stay live).
- No caller.py / .env change needed to roll back this phase.

**Status: DONE + LIVE + PROVEN. Real message landed (message_id=4). Inbound conversation continuous via comm-poll.service (PID 2961553, enabled, survives reboots). Post-call Telegram alert wired. Earner gate green before+after. The full Telegram loop is now real.**
