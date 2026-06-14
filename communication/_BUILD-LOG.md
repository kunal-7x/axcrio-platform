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
