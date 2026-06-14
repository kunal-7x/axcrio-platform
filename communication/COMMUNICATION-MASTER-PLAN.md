# COMMUNICATION-MASTER-PLAN.md — The Omnichannel Revenue-Comms Tab (Telegram → Email → SMS)

> **Read-first context:** see `communication/README.md` (index of this folder).
> **Source research:** `communication/_RESEARCH-LOG.md` (every architecture phase + 7 red-teams + completeness critic appended there).
> **Status:** W1 DONE · W2 DONE · W3-COSTGUARDS DONE · **W1+W2+W3 LIVE (2026-06-15)** — Telegram alert + post-call auto-summary + LLM conversation brain + 6 cost guards ALL LIVE for the `admin` tenant. ONE founder action remaining: tap `@mr_kunal_bot` once to seed chat_id → real alerts land on phone. FE (Communication tab) COMMITTED on `fe/unify-run-wavec`, ships in the next canonical panel deploy. Next wave: W3 Email (needs Resend key); then W5 SMS (DLT-gated, 5-10d external). See `communication/README.md` for the full build status.
> **Date:** 2026-06-15. Base dir `C:\Users\kunal\Desktop\caps`. Box (READ-ONLY for design) `famit@168.144.153.145`.

---

## 0. EXECUTIVE SUMMARY (~25 lines)

The founder asked for a **Communication tab** (new section, alongside the live WhatsApp) carrying **Telegram + Email + SMS** that mirrors and exceeds the WhatsApp system: multi-step template builder, send banner/video/PDF, after-a-call auto-message the contact a summary, hot-lead auto-alert (phone + summary) to the founder's Telegram, a multi-step LLM conversation brain, per-tenant. That literal ask is **~1%**; this plan designs the other **99%** a billion-dollar, sellable omnichannel revenue product needs.

**The one structural decision (everything else is cheap because of it):** the *channel registry is the provider registry*. A Telegram bot token / Resend key / MSG91 key is just a `provider_credentials` row with a new `capability` — **zero new crypto, zero new vault, the AAD-bound AES-256-GCM store is already LIVE on the box** (`PROVIDER_REGISTRY_ENABLED=1`). Adding a channel = one DB row + one adapter file behind a unified `send / receive / template` contract. WhatsApp joins later as a *thin wrapper* (strangler) — the live WA earner path is never edited.

**Earner-safety is the law, and the red-team caught a real bug in the original briefs:** `_finalize_call` is **NOT off the hot path** — it is `await`ed inside the live dial loop (`caller.py:~2845`). So every contact-facing send MUST be `asyncio.create_task(...)` with a per-channel timeout and a **synchronous payload snapshot** — never `await`, never touching the live `rec`/`tr` objects, never editing `_wa_draft_followup_text` in the channel wave (duplicate the field reads). `agent.py` is never imported. All flags default OFF → resting byte-identical. Earner gate (agent.py md5 `9150fabe` unchanged, famit-agent PID not restarted, /health 200, 0 5xx, no ring) before+after **every** box wave, measured **under an induced channel outage**, not a green path.

**MVP-first, per the over-engineering red-team:** ship **3 tables + Telegram-only + alert + auto-summary + setup UI** in ~2 weeks — NOT the 10-table cathedral, NOT the cost-router (dead code with one channel), NOT Hatchet journeys, NOT the agentic tool-loop, NOT the unified inbox. Earn the moat wave-by-wave. **Telegram is the unblocked flagship** — a 2-minute BotFather token, no Meta business verification, free sends, real-reach-provable to the founder's own phone. Email and SMS follow (SMS hard-gated behind DLT until the founder registers). The compliance model is corrected to one canonical rule: **suppression is `(channel × purpose)`**, consent basis is **derived from `lead_source`** (purchased lists ≠ service-implicit), and every send records a consent artifact.

---

## 1. WHAT WE'RE BUILDING (the full product, MVP→moat)

A new **Communication** section in the panel's **Engage** nav group, holding the builder + unified inbox + journeys + analytics + channel setup + hot-leads feed. Behind it: a per-tenant **channel registry** resolving Telegram / Email / SMS / WhatsApp adapters, a **cost-router** (cheapest-channel-that-will-be-read), an **LLM conversation brain** (the proven `_wa_reply_text` generalized), an **automation engine** (post-call auto-summary, founder hot-lead alert, drip/journeys), all on the live `caller.py` (+ the idle Hatchet droplet for durable journeys), every send metered on the ACID wallet, FORCE-RLS multi-tenant, DPDP/DLT/SPF compliant.

### 1.1 The full feature set (named ask + the 99%)

| # | Feature | Founder-named? | Wave |
|---|---|---|---|
| Channel registry = provider registry (1 row + 1 adapter = a channel) | structural | W1 |
| Telegram adapter (send_text/photo/document/video, dormancy-safe, file_id cache) | yes (Telegram) | W1 |
| **Founder hot-lead alert** → Telegram (phone + summary + score + Call-Now URL button) | **yes** | W1 |
| **Post-call auto-summary** to the contact (Telegram) | **yes** | W1 |
| Channel setup UI (paste token + Test + founder chat_id) | implied | W1 |
| Append-only consent log + STOP-suppresses-all gate (`channel×purpose`) | the 99% | W1 |
| **LLM conversation brain** (5-layer grounding, persona "Riya" inherited from voice) | **yes** | W2 |
| Inbound webhook (per-tenant, `secret_token` constant-time verify, **fail-CLOSED**) | implied | W2 |
| Deep-link `?start=` **signed single-use** consent binding | the 99% | W2 |
| Inbound media: don't-crash + acknowledge (then download/store/scan) | the 99% (critic) | W2 |
| **Email** (Resend primary, SES fallback) + SPF/DKIM domain wizard | yes (Email) | W3 |
| **Cost-router waterfall** (TG→WA-window→Email→WA-tmpl→SMS) — *real once 2 channels* | the 99% | W3 |
| Per-tenant **budget ceiling + frequency cap + spend-anomaly alert** | the 99% (red-team) | W3 |
| Multi-step **template builder** (author-once, render-per-channel, "test send to me") | yes (mirror WA) | W3-4 |
| Banner / video / PDF attach (presigned Spaces URL, never base64/MMS) | **yes** | W3-4 |
| **Unified inbox** (one thread table, channel = a column) + human takeover | the 99% | W4 |
| `book_slot` tool (the one high-ROI agentic tool) | the 99% | W4 |
| LLM output-safety / moderation gate (no offensive/unauthorized-commitment sends) | the 99% (critic) | W4 |
| Failed-send **DLQ** + delivery-health internal alert | the 99% (critic) | W4 |
| **SMS** (MSG91 primary, Twilio intl) + **DLT hard gate** + GSM7 segment billing | yes (SMS) | W5 |
| **Automation engine** (durable Hatchet journeys: drip, A/B+holdout, abandoned-flow) | the 99% | W5 |
| Two-way Telegram war-room (assign/snooze/takeover callback buttons) | the 99% | W5 |
| **CAPI revenue-signal closure** (outcome→Meta/Google) — the named moat | the 99% | W6 |
| Team inbox concurrency + assignment + intra-tenant RBAC | the 99% (critic) | W6 |
| Public API + outbound webhooks (`reply.received`/`booked`) | the 99% (critic) | W6 |
| In-chat payment collection (UPI/Razorpay link) | the 99% (critic) | W6+ |

### 1.2 Founder-unnamed "99%" features folded into the SCHEMA from day 1 (zero refactor later)

These are **one column or one field**, baked in W1 so they enable later with a flag, not a migration:
1. **`comm_messages.outcome`** — CAPI revenue-truth signal closure (ad-click → omni-conversation → ad-signal). The sales-deck moat.
2. **`comm_conversations.agent_persona`** — "Riya" inherited from the voice earner; same named agent call→chat→email.
3. **`comm_contact_identity.preferred_channel` / `preferred_hour`** — per-contact channel + send-time learning.
4. **Unified `comm_messages` (channel = a column, NOT silos)** — cross-channel inbox + timeline for free.
5. **Negative-signal cross-channel suppression** — one opt-out freezes the right scope (`channel×purpose`).
6. **`comm_asset_cache.external_file_id`** — Telegram `file_id` reuse = brochure/banner re-sends at ₹0 forever.
7. **Channel registry = provider registry** — RCS/Slack/IG-DM later = one row + one capability key.

---

## 2. ARCHITECTURE (the seams, verified on disk)

### 2.1 The contract — one ABC every channel implements
`ChannelAdapter` (Protocol, **never raises**, mirrors `creative/image_banner_studio/providers/base.py`): `status() · estimate_cost_minor() · send(SendEnvelope)→SendResult · verify_inbound() · parse_inbound()→InboundEvent · render_template()`. The universal `SendEnvelope` is channel-neutral (`to{}`, `kind`, `text`, `template_ref`, `media[]`, `buttons[]`, `lang`, `idempotency_key`); the universal `SendResult` (`ok`, `status`, `channel`, `external_id`, `cost_minor`, `provider`, `file_id_cached`).

### 2.2 The resolver + cost-router (`comm_registry/registry.py`)
`get_channel(tenant, type)` (explicit) · `pick_cheapest(tenant, contact, kind)` (the waterfall — **only live from W3 when ≥2 channels exist**) · `dispatch(tenant, contact, envelope)` (the consumer seam). Cache-first per-tenant config map (channels are off the voice hot path entirely — post-call, async).

### 2.3 The post-call seam (earner-safe — RED-TEAM CORRECTED)
The single insertion in `caller.py:_finalize_call`, **alongside** the untouched `_wa_ai_followup` (~2764) and `notify_handoff_team` (~2789):
```python
# RED-TEAM MANDATE: create_task, NEVER await. Snapshot payload synchronously first.
if os.getenv("COMM_ENABLED") == "1":
    _snap = _comm_snapshot(rec, tr, camp_fields)          # pure sync dict copy, no refs to live objects
    asyncio.create_task(_comm_post_call(tenant_id, _snap)) # detached; owns asyncio.wait_for per-channel timeout
```
- **NEVER `await`** (an awaited Telegram/Resend/MSG91 call injects network+429-backoff latency into the live dial loop → stalls hangup detection + new-call launch).
- **Snapshot synchronously** — the task touches ONLY the detached dict, never the live `rec`/`tr`/`it` the loop keeps mutating, never the flat files the loop owns.
- **Do NOT refactor `_wa_draft_followup_text`** in the channel wave — duplicate the ~6 field reads (additive-and-isolated beats DRY when the shared code is the earner). The strangler-extract is a later, separately-gated wave.
- **Anchor-string insertions, never LIVEBOX line numbers** (three caller.py variants exist on disk, sizes differ). `md5` box-fresh `caller.py` and confirm the live variant before any edit. Claim `caps/CALLER_EDIT_LOCK.md` before touching `caller.py`; release after the earner gate passes.

### 2.4 The LLM brain (`comm/brain.py`)
`generate_reply(session, channel, inbound, ctx) -> ReplyPlan` — `_wa_reply_text` lifted to a channel-neutral module (COPIED, not moved — WhatsApp's own `_wa_reply_text` stays byte-identical). 5-layer grounding (campaign brain + call grounding + `memory.py` cross-call recap + last-20 turns + persona) + a per-channel system-prompt suffix. ONE Groq `llama-4-scout` call (temp 0.6, ~220 tokens, zero new LLM cost). **Tools OFF at launch** (`COMM_TOOLS_ENABLED=0` → degrades to plain reply). Pre-LLM keyword opt-out/handoff gate runs FIRST (free, ungameable).

---

## 3. DATA MODEL (FORCE-RLS, `tenant_id TEXT`, INTEGER paise — corrected by data-security + red-team)

**Non-negotiable conventions** (from arch-data-security, gate at review):
- `tenant_id TEXT` everywhere (== `org_id`). **REJECT any `uuid`/`UUID` PK or FK** — a UUID breaks the RLS GUC string-compare (`current_setting('app.tenant_id',true)` is TEXT) → fails-open-shaped.
- All PKs `TEXT` `"<prefix>_<uuid4hex>"` (matches `ai_wa_*`). All money `BIGINT` paise. Idempotent `CREATE ... IF NOT EXISTS`.
- RLS = the `ddl_ai_wa.sql:95-116` `DO $rls$ FOREACH t IN ARRAY[...]` admin-GUC block VERBATIM: `current_setting('app.is_admin',true)='1' OR tenant_id=current_setting('app.tenant_id',true)` in BOTH `USING` and `WITH CHECK`. `famit_app` is NOSUPERUSER/NOBYPASSRLS.
- **NO new credential table** — Telegram/Email/SMS = one `provider_definitions` row (`capability=telegram_send|email_send|sms_send` + non-secret `config JSONB`) + one AAD-bound `provider_credentials` row. **Reuse, zero new crypto.**
- **NO new money table** — every send (incl. ₹0 Telegram) writes ONE `wallet_transactions` row via `wallet.reserve→settle/release` (there is **NO `wallet.debit()`** — the router pseudocode that called it is wrong). Metering is **per-message** (`idem_key=comms:{message_id}`), NOT per-call.

### 3.1 MVP core (Wave 1 — ONLY these 3, per the over-engineering cut)
| Table | Purpose |
|---|---|
| `comm_sessions` | LLM brain rolling 20-turn JSONB window; `(tenant, channel, external_chat_id)` unique; seeds call_summary/next_action/outcome/interest post-call |
| `comm_send_log` | every outbound, every channel; **append-only** (REVOKE UPDATE/DELETE); `cost_minor BIGINT`, `idempotency_key UNIQUE`, `status/external_id/error_code`, `outcome` (CAPI col, day-1), `delivered_at/read_at/clicked_at` |
| `comm_consent_log` | **append-only** (REVOKE + BEFORE UPDATE/DELETE RAISE trigger); `channel` + **`purpose` (marketing\|service\|transactional)** + `consent_basis` + `wording` + `captured_at` (the `channel×purpose` model) |
| `comm_asset_cache` | (tiny, W1) Telegram `file_id` reuse — `UNIQUE(tenant, spaces_key, channel)` |

### 3.2 Added when their wave lands (NOT at launch)
`comm_contact_identity` (phone-anchored, `UNIQUE(tenant,phone)`) + `comm_channel_link` + `comm_conversations` (`agent_persona`) + `comm_messages` (`outcome` CAPI col) — **W4 with the unified inbox** (backfilled from `comm_sessions`). `comm_contact_memory` (async fact-extraction) — Enterprise/later. `comm_templates` + `comm_template_content` (`sms_dlt_template_id` carrier of the DLT hard-gate) — **W3-4 with the builder**. `comm_journeys` + `comm_journey_runs` + `comm_events` — **W5 with the automation engine**. `comm_global_suppression` (hard-bounce/complaint/report/DND) — **W3 with Email/SMS**.

---

## 4. SECURITY (the 6 SHIP-BLOCKERS the red-team found — all gated)

The reuse primitives (vault/jti/router/SSRF) are verified-strong, but the NEW surface (per-tenant webhooks + agentic brain + phone-anchored memory + deep-links) is where the holes live. Each fix below is an **acceptance probe**, not a "later":

- **S1 — per-tenant DEK.** Today `_interim_get_key` returns `sha256(MASTER)` — ONE global key for all tenants (AAD only stops copy-paste, not a master-secret leak). FIX: HKDF per-tenant derivation (`info=tenant_id‖def_id‖version`). Probe **T-VAULT**: two tenants' DEKs differ; AAD copy A→B → InvalidTag.
- **S2 — webhook FAIL-CLOSED, secret bound to the PATH tenant.** The existing `_verify_meta_signature` *accepts when dormant* (fail-OPEN) — acceptable single-tenant, **catastrophic** on the per-tenant `/comm/webhook/telegram/{tenant_id}` path. FIX: no secret configured → **403 not 200**; `compare_digest(header, THAT tenant's secret)` + bot-identity cross-check; set the RLS GUC only AFTER verify passes. Probe **T-WEBHOOK**: no/wrong/other-tenant's secret → 403; correct → 200, row lands only in that tenant's scope.
- **S3 — agentic brain prompt-injection → cross-tenant/destructive write.** FIX: tenant_id/phone/conversation_id injected from the verified session via `contextvars` (NEVER LLM-fillable args); per-tool allowlist (only `book_slot`/`opt_out` write, idempotent + rate-limited); pre-LLM keyword gates run first; 2-tool/turn budget → handoff. Probe **T-INJECT**: 12 injection strings → zero cross-tenant r/w, STOP unblockable. (Tools are OFF until W4 anyway.)
- **S4 — cross-tenant memory leak (the P0-LEAK class).** FIX: `load_memory`/`build_recap` MUST `raise` (not default) on a missing `tenant_id`; grep-gate zero un-tenanted call sites; **no shared bot across tenants** (each bot its own `provider_def`; session key includes `provider_def_id`). Probe **T-LEAK**: two tenants same phone+chat_id → no cross-read; cross-tenant SELECT = 0.
- **S5 — signed single-use deep-link.** `?start=base64(tenant‖token)` with no MAC is forgeable. FIX: `base64url(tenant‖nonce‖hmac(SECRET, tenant‖nonce‖phone))`, minted server-side, single-use (reuse firewall jti store), short TTL. Probe **T-DEEPLINK**: forged/replayed/expired → bind refused.
- **S7 — compliance gate is a SERVER send-path block, not a UI gate.** FIX: `sms/dlt_gate.py` + email adapter hard-block server-side (`blocked_dlt` / `blocked_unverified`) regardless of UI. Probe **T-GATE**: direct API send with null DLT / unverified domain → server-blocked.

Plus the strong reuse to keep verbatim: token reveal via single-use jti step-up (`firewall.py`), SSRF guard on any tenant-supplied endpoint, legacy `FamitCall2026` → 403 on all `/comm/*`, founder `chat_id` is the tenant's own configured value (never attacker-suppliable).

---

## 5. COMPLIANCE (the canonical consent model — corrected, gating all channels)

The red-team found the briefs shipped **two contradictory opt-out laws**. The canonical model (write once, every adapter checks it):

1. **Suppression is two-dimensional: `(channel × purpose)`** — never a single boolean.
   - **Marketing/promotional STOP on ANY channel → global marketing suppression across ALL channels** (DPDP + CAN-SPAM + TRAI).
   - **Service/transactional opt-out is per-channel** (a contact can refuse SMS but still get the owed booking confirmation).
   - "Delete and block" / report-spam → global suppression of both purposes.
2. **`consent_basis` is DERIVED from `lead_source`, never a constant.** Purchased/scraped lists → **promotional, explicit opt-in required, DND-scrubbed, 10:00–21:00 IST window**. Inbound-form / tenant's-own-customer / prior-transaction → service-implicit is defensible. The tenant **attests per list** that they own the relationship; the attestation is the audit artifact.
3. **The post-call auto-message records a consent artifact** at finalize time ("I'll text you a summary, okay?" → boolean+timestamp+wording in `comm_consent_log`) **before** the first contact-facing send. This is a gate on `_comm_post_call`, not a side-effect — it is what makes the founder's flagship feature legal.
4. **Pre-send suppression pipeline** (W3, real, not "carrier handles it"): tenant opt-out list + `comm_global_suppression` (hard-bounce/complaint/report/STOP/DND) checked BEFORE the cost-router. Promotional SMS is never auto-sent; only service-implicit post-call (the defensible lane) auto-fires.
5. **Email envelope is a compliance template** (W3): mandatory `List-Unsubscribe` + RFC 8058 `List-Unsubscribe-Post: One-Click` headers (Gmail/Yahoo bulk-sender mandate — also a *deliverability* gate), tenant's verified physical address in the footer, a `POST /comm/unsubscribe/{token}` that writes opt-out within one request. Block the marketing send if the address field is empty.
6. **Right-to-be-forgotten = pseudonymize-in-place, NOT delete-cascade** (the append-only consent log would abort a cascade). A `SECURITY DEFINER` erasure function replaces PII columns with a tombstone token across all `comm_*` tables, keeping the consent *fact* + timestamps. **Two retention clocks:** content prunes at 90d; consent + send metadata retained for the statutory limitation window (default 3y, tenant-configurable).
7. **Telegram `/start` writes a real consent row** (`consent_basis='telegram_start'` + the deep-link wording + timestamp). The founder-alert PII transfer to Telegram (a third country) is **minimized by default** ("Hot lead — tap to view in panel" + link, not full name/phone/summary inline) with full-PII inline as a tenant opt-in.
8. **Per-tenant reputation isolation enforced** (W3): the shared `noreply@mail.famit.in` fallback is transactional/low-volume only with **per-tenant complaint fuses**; own-domain mandatory above a low threshold; SMS = MSG91 sub-account per tenant so a DLT violation is contained, never implicating the Famit entity.

---

## 6. COST & SCALE (the 6 guards the red-team demanded as acceptance gates, NOT "later")

- **Per-message metering** through the real `reserve→settle/release` ledger (`idem_key=comms:{message_id}`). A provider 5xx → `release`, never bills. The pseudocode's `wallet.debit()` does not exist — strike it everywhere.
- **Per-tenant daily comm-spend ceiling** (`comm_daily_budget_minor`, default ~₹500/day) — over budget → metered channels return `blocked_budget`, free channels flow, founder alerted. The circuit-breaker that caps a runaway at a known rupee number.
- **Per-contact per-day send cap** (frequency cap, all channels) — stops a journey bug from spamming+billing.
- **Spend-anomaly alert** — comm spend > 3× trailing-7-day median → founder Telegram alert + auto-throttle.
- **Per-(identity, channel) deliverability state** — `chat_id` flips `dead` on a 403 block; email flips `suppressed` per-contact on bounce/complaint. "Cheapest" = "cheapest *not known-dead for THIS contact*", not "column non-null".
- **Per-bot-token async token-bucket** (30 msg/s global, 1 msg/s per chat) — the journey blast + post-call trickle + founder-alert burst **share** one budget; founder/hot-lead alerts get a priority lane.
- **Segment-accurate SMS pricing** — `gsm7.py` detects GSM-7 vs UCS-2 (Hindi → 70 chars/segment); reserve `segments × per-segment × 1.3`. The flat-rate margin table is wrong for the India-language path.
- **Honest savings ticker** — store chosen-channel cost AND counterfactual (next-cheapest *deliverable*) per send; saving is auditable, not asserted.
- **Inbox at scale** — keyset pagination (`WHERE last_message_at < :cursor ORDER BY ... DESC LIMIT 50`, never OFFSET); `(tenant_id, last_message_at DESC)` index on `comm_conversations` mandatory; message INSERT + `last_message_at` UPDATE in one txn.

---

## 7. THE FRONTEND (`/communication`, Core_2 reuse, ~70% cloned)

New **Communication** section in the **Engage** nav group. Routes: `/communication` (the builder shell = `whatsapp/page.tsx` + a `ChannelPicker` above the step rail, `STEPS` resolved per-channel) · `/communication/inbox` (the CRM `ChatBubble` chat-view → two-pane unified inbox + one-tap human takeover) · `/communication/journeys` (the shipped React-Flow `_editor.tsx` + a comm node palette) · `/communication/analytics` (omnichannel ROI + savings ticker) · `/communication/channels` (per-channel setup, sibling of `integrations/_body.tsx` + `_reveal-pin.tsx`) · `/communication/hot-leads` (live feed + alert-config).

**Net-new components (the only real design work):** `ChannelPicker`, `ChannelPreview` (+ `TelegramPreview`/`EmailPreview`/`SmsPreview`, restyles of `PhonePreview`), the inbox `Composer`, the comm journey node palette, the channel-setup wizards. Everything else is `Card/Tabs/Button/Field/Select/Modal/Badge/Spinner/KpiCard/Table/GenerationLoader/ChatBubble`. Dormant-safe `Dormant<T>` (404/503 → `ComingSoon`), zero raw hex, `dark:`-paired, reduced-motion safe. **WhatsApp tab in the picker deep-links to the live `/whatsapp` page** (no duplicated Meta logic — earner-safe). **Wave 1 FE is just Channel Setup + a simple send/log view** (the Integrations-card pattern); the 11-step builder, 4-up "author once" preview, and inbox are W3-4.

**MVP additions the critic demanded:** seed template/journey library (activation), LLM output-safety gate surfaced as a setting, failed-send DLQ view, delivery-health alert. **Build BE/Opus, FE/Sonnet + `frontend-design` skill. Deploy only when no other FE wave is mid-deploy (PLAYBOOK #15): unify all live FE branches, build once, md5-gate scp, atomic `.next` swap, restart famit-panel only.**

---

## 8. THE EARNER-SAFE BUILD ROADMAP (one box-mutating wave at a time)

Every wave: **flags default OFF → resting byte-identical.** Earner gate (agent.py md5 `9150fabe` unchanged · famit-agent PID 1477083 NOT restarted · /health 200 · 0 5xx · NO ring · golden byte-diff) **before+after, measured under an induced channel outage.** Restart ONLY famit-caller / famit-panel / the Hatchet worker — **NEVER famit-agent.** Serialize all `caller.py` edits against RAG/Vault/Video/Provider-registry/Telephony via `caps/CALLER_EDIT_LOCK.md`. CI grep `import agent|from agent` over `comm*/` must be empty.

### WAVE 1 — "Telegram alert + auto-summary" (the demo-closer) · BE/Opus + FE/Sonnet · ~1.5–2 wks
- **Scope:** Telegram-only. Founder hot-lead alert (URL-buttons only, no callback/firewall) + post-call contact auto-summary (one `create_task`, snapshot, timeout) + channel-setup UI (paste token + Test `getMe` + founder chat_id) + token in `provider_credentials`. NO cost-router, NO Hatchet, NO tools, NO builder, NO inbox, NO identity table.
- **Files (NEW):** `droplet_work/comm/` (`__init__.py` flag-gate · `config.py` · `channels/base.py` + `channels/telegram.py` · `registry_bridge.py` · `founder_alert.py` · `post_call.py` · `send_log.py` · `consent.py` · `router.py` build_router mount · `db/ddl_comm.sql` (3 tables + asset_cache) · `tests/*`). **EDIT (additive, anchor-string, create_task):** `caller.py` `_finalize_call` (2 insertions: founder alert + post-call) + one `include_router` mount. **FE:** `app/communication/channels/` + a simple send-log view + nav entry.
- **Flags:** `COMM_ENABLED` · `COMM_TELEGRAM_ENABLED` · `FEATURE_TELEGRAM_FOUNDER_ALERT` · `FEATURE_TELEGRAM_FOLLOWUP` (all OFF).
- **Acceptance:** resting byte-identical (flags OFF → `/comm/*` 404, route table identical); DDL 3 tables FORCE-RLS=t, consent/send-log UPDATE/DELETE blocked, cross-tenant SELECT=0; T-VAULT (per-tenant DEK / AAD); founder alert fires exactly one `sendMessage` with URL buttons, alert failure never blocks the call loop (kill the bot mid-call → call record still finalizes); dial-loop tick latency unchanged with Telegram pointed at a black-hole host; **REAL-REACH: a Telegram message lands on the founder's real phone.** Earner gate before+after.
- **Rollback:** flags → 0 (instant, no deploy). 3 tables additive (drop-safe). `caller.py` insertions inert when flag off.

### WAVE 2 — "The conversation brain (reply-only)" · BE/Opus · ~1.5 wks
- **Scope:** copy `_wa_reply_text` → `comm/brain.py` + Telegram suffix (`COMM_TOOLS_ENABLED=0`). Inbound webhook `POST /comm/webhook/telegram/{tenant_id}` (**fail-CLOSED** secret_token verify, bot-identity cross-check, GUC-after-verify) → brain → reply → `comm_sessions`. Signed single-use deep-link `?start=` consent binding. Inbound media: don't-crash + acknowledge (full download/store W4). `update_id` idempotency. Per-tenant webhook rate-limit + body-size cap + daily Groq ceiling BEFORE any LLM call.
- **Files:** `comm/brain.py` · `comm/webhook.py` · `comm/sessions.py` · `comm/deeplink.py` · `comm/lang.py` (langdetect). EDIT: rotate endpoint re-`setWebhook` (deaf-bot footgun).
- **Flags:** reuse W1 + the webhook route gated by `COMM_TELEGRAM_ENABLED`.
- **Acceptance:** T-WEBHOOK (no/wrong/other-tenant secret → 403; dormant → 403 not 200; correct → 200 row only in that tenant's scope); T-LEAK (`load_memory` without tenant raises; two tenants same phone → no cross-read); T-DEEPLINK (forged/replayed/expired → bind refused); brain reply grounded in the call_summary; opt-out word → suppression + no Groq call; LLM failure → ReplyPlan.text="" → webhook still 200; **REAL-REACH: the founder chats with "Riya" on Telegram and it answers grounded in the prior call.** Earner gate.
- **Rollback:** `COMM_ENABLED=0` (dormant) → `setWebhook(url="")` to detach → remove the include_router line + redeploy.

### WAVE 3 — "Email (the 2nd channel that makes routing real) + the cost guards" · BE/Opus + FE/Sonnet · ~2 wks
- **Scope:** Resend adapter (+ SES us-east-1 fallback) + SPF/DKIM/DMARC domain-verify wizard + the compliance email envelope (List-Unsubscribe + RFC 8058 + physical address + one-click unsubscribe endpoint). **Now** `pick_cheapest` (Telegram→Email) becomes real. Wire ALL cost guards: per-message `reserve/settle`, per-tenant daily budget ceiling, per-contact frequency cap, spend-anomaly alert, per-(identity,channel) deliverability state, `comm_global_suppression` pre-send pipeline, bounce/complaint per-tenant circuit-breaker. The multi-step template builder (author-once `{variable}` → per-channel render + "test send to me") + `comm_templates`/`comm_template_content`. Banner/PDF attach (presigned Spaces URL / CDN `<img>`, never base64).
- **Files:** `comm_channels/email/*` · `comm/cost_router.py` · `comm/consent.py` (the `channel×purpose` model) · `comm/shortlink/*` (`go.famit.in`) · `db/ddl_comm.sql` (+ identity/templates/global_suppression). FE: builder Template+Creative+Compliance+Preview steps, `EmailPreview`.
- **Flags:** `COMM_EMAIL_ENABLED` · `FEATURE_EMAIL_FOLLOWUP` · `COMM_EMAIL_PROVIDER` (all OFF).
- **Acceptance:** cost-router picks TG when chat_id present, falls to Email, never fires a paid channel when a free one was deliverable; budget ceiling → `blocked_budget`; T-GATE (direct API send to unverified domain → server-blocked); email lands in a real INBOX (seed-list), not spam; bounce flips per-contact deliverability; `List-Unsubscribe` one-click writes opt-out in one request. Earner gate.
- **Rollback:** per-channel + per-guard sub-flags revert independently.

### WAVE 4 — "Unified inbox + book_slot + safety + ops" · BE/Opus + FE/Sonnet · ~2 wks
- Add `comm_contact_identity`/`comm_channel_link`/`comm_conversations`/`comm_messages` (backfill from sessions). Unified inbox (CRM `ChatBubble` two-pane + `Composer` + one-tap human takeover + keyset pagination). The ONE agentic tool `book_slot` (`COMM_TOOLS_ENABLED=1`, server-injected scope, T-INJECT gate). LLM output-safety/moderation gate. Failed-send DLQ + delivery-health alert. Inbound media full download/store/scan. Per-message read-receipt-driven escalation.

### WAVE 5 — "SMS (DLT-gated) + the automation engine + war-room" · BE/Opus + FE/Sonnet · ~2-3 wks
- SMS (MSG91 + Twilio intl) behind the **DLT hard gate** (`blocked_dlt` until founder registers PE/header/template) + GSM7 segment billing + quiet-hours + per-bot/per-sender token-bucket. Durable Hatchet journeys (drip, A/B + 5% holdout, abandoned-flow recovery, re-engagement circuit-breaker, smart-send-time, chat→voice re-trigger) on the idle Hatchet droplet. Two-way Telegram war-room (assign/snooze/takeover callbacks, `answerCallbackQuery` ≤10s, firewall on destructive). `comm_journeys`/`comm_journey_runs`/`comm_events`.

### WAVE 6+ — "The moat" · BE/Opus + FE/Sonnet
- **CAPI revenue-signal closure** (the named moat — `outcome`→Meta/Google async event; promote to a real wave, not a column). Team inbox concurrency + assignment + intra-tenant RBAC. Public API + outbound webhooks. In-chat payment collection (UPI/Razorpay). Calendar/CRM/Sheets sync. Managed-bot provisioning at scale. Deliverability dashboard. Next-best-action cockpit.

---

## 9. FOUNDER CREDENTIAL ACTIONS (give these so we test on real numbers)

| Channel | What the founder does | Effort | Blocker? |
|---|---|---|---|
| **TELEGRAM** (W1 — the unblocked launch) | 1. Open Telegram → message **@BotFather** → `/newbot` → name it (e.g. "Famit Riya") → **copy the bot token** (`123456:ABC...`). 2. Message your own new bot once (tap **Start**) so we can read your `chat_id` for hot-lead alerts. That's it — **no verification, no business account, free.** Paste the token in `/communication/channels`. | **~2 min** | **NONE** |
| **EMAIL** (W3) | Create a **Resend** account → **API key** (`re_...`). For your own sending domain, add the **CNAME/TXT records** Resend shows (we give a guided wizard) — or use our shared `noreply@mail.famit.in` for low volume day-one. (SES key optional, high-volume fallback.) | ~10 min + DNS | domain verify ~15 min |
| **SMS** (W5) | 1. Create a **MSG91** account (INR billing). 2. **DLT registration** (TRAI): register your **PE ID**, **header/sender ID**, and the **post-call summary template** on the DLT portal (Jio/Airtel/Vi/BSNL). We block SMS until this is done (`blocked_dlt`). | DLT = **5–10 days** (external, founder action) | **YES — DLT** |

**Start with Telegram.** It needs nothing but a 2-minute BotFather token and proves real reach on your own phone in Wave 1. Email and SMS layer on after.

---

## 10. RISKS (honest, top of mind)

- **R1 — `caller.py` serialization.** Comm + RAG + Vault + Video + Provider-registry + Telephony all edit `caller.py`. ONE box wave at a time; `CALLER_EDIT_LOCK.md`; mount appended at the END of the include-router block; anchor-string + box-fresh md5, never LIVEBOX line numbers.
- **R2 — earner regression via the post-call hook.** Mitigated: `create_task` not `await`; payload snapshot; per-channel timeout; no `_wa_draft_followup_text` refactor in the channel wave; earner gate under induced outage.
- **R3 — webhook fail-open / cross-tenant write.** Mitigated: fail-CLOSED + secret-bound-to-path-tenant + GUC-after-verify (S2).
- **R4 — silent "everything green, nobody got the message".** Mitigated: loud `no_reachable_channel` state + reachability preflight + REAL-REACH founder-device gate per channel before "shipped" + the DLQ (W4).
- **R5 — DLT/domain compliance bleed across tenants.** Mitigated: per-tenant sub-account/own-domain, per-tenant reputation fuses, server-side hard gates.
- **R6 — scope sprawl.** Mitigated: the MVP-first cut (3 tables, 1 channel, no router/journeys/tools/inbox in W1); the moat is Waves 3-6, earned with traffic.

---

*Plan synthesized 2026-06-15 from `_RESEARCH-LOG.md` (6 architecture phases + 7 red-teams + completeness critic). Build BE on Opus, FE on Sonnet + the `frontend-design` skill, reusing Core_2. Telegram first.*
