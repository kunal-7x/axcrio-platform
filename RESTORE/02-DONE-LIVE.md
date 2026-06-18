# 02-DONE-LIVE.md — Authoritative "What Is Already Built" Inventory

> **Date:** 2026-06-18  
> **Total VERIFIED-LIVE items:** 49  
> **Total BUILT-NOT-DEPLOYED items:** 7  
>
> Purpose: pre-compact handoff so no future session rebuilds what already exists.  
> Earner baseline throughout: `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` (never edited, never restarted by any wave). Box: `famit@168.144.153.145`, panel: `famit@143.110.247.249`.

---

## 1. VOICE / TELEPHONY

### 1.1 Outbound Calling (via Vobiz SIP)  **VERIFIED-LIVE** (2026-06-15)
- What: Outbound calls via LiveKit SIP. DID was spam-flagged → new DID provisioned on same Vobiz account.
- Flag/file: `LIVEKIT_SIP_TRUNK_ID=ST_bpGqmc9TL9Ph` in `/opt/famit-agent/.env` (line 13). Old trunk `ST_fmtVmNJmpzKa` intact for rollback.
- Backup: `/opt/famit-agent/.env.VOBIZbak.20260615-164935`
- Verify: place a call → should ring within ~3500ms (`inviteToRingingMs 3463` was the test proof). `place_call.py` reads `LIVEKIT_SIP_TRUNK_ID` from env.

### 1.2 Inbound Warm-Transfer (human handoff)  **VERIFIED-LIVE** (2026-06-15)
- What: During an inbound call, agent says one line, starts hold music, dials the handoff team number into the same SIP room, AI exits on answer. Code: `aim_voice_agent.py:779 _do_warm_transfer()`.
- Fix applied: `aim-voice-agent` restarted after DID swap so it loaded the new trunk ID from env.
- Handoff list: `var/brain/admin.json` — 2 entries (priorities 1 & 2), both `enabled=True`, `hours=24x7`.
- Verify: inbound call → say "please transfer" → agent confirms transfer, dials `…9021` → hold music → human answers.

### 1.3 Vendor-Script Inject (Script Studio)  **VERIFIED-LIVE**
- What: Pasted vendor greeting → inbound AI persona adapts dynamically. `VENDOR_SCRIPT_INJECT=1` systemd drop-in.
- Flag: `/etc/systemd/system/aim-voice-agent.service.d/vendor-script.conf`
- Commits: `29a2f1cc`/`a2c5b053`/`f169d6e1`. Panel BUILD_ID `Ykm_1fVt267VDkPib8uVg`.
- Verify: `POST /campaigns/{cid}/prompt-preview` with a vendor greeting → returned prompt adopts it.

### 1.4 Cross-Tenant Memory Leak CLOSED (P0)  **VERIFIED-LIVE**
- What: Tenant A cannot read Tenant B's lead memory files. `memory.py:_path_for(phone, tenant_id)` → `{tenant}/{phone}.json`. Commit `4db497f`.
- Verify: `ls var/memory/` — each subfolder is a tenant_id. Tenant path-traversal returns 0 rows cross-tenant.

### 1.5 Multilingual Adaptive Voice (MLV)  **VERIFIED-LIVE**
- What: Agent mirrors the caller's language (Hindi/English/Hinglish/Tamil etc.). ADAPTIVE MIRROR rule + language-neutral greeting + FINAL LANGUAGE LOCK.
- Flag: active by default in `aim_voice_agent.py` (no env gate). 5/5 live-shape smoke PASS.
- Verify: inbound call in Tamil → agent replies in Tamil.

### 1.6 Sarvam Bulbul v3 TTS  **VERIFIED-LIVE**
- What: Fixes v2 garbling of acronyms ("BHK"). `.env` `SARVAM_TTS_MODEL=bulbul:v3` + `SARVAM_TTS_SPEAKER=priya`.
- Backup: `/opt/famit-agent/.env.SURGbak.20260614-154923`
- Verify: `GET /api/voice/preview` — audio contains correct pronunciation of "BHK".

### 1.7 Context Cache (CTX_CACHE)  **VERIFIED-LIVE**
- What: Warm 0.205ms vs 57ms cold (277×). `CTX_CACHE=1` in systemd drop-in (NOT in `.env`).
- Flag: `/etc/systemd/system/aim-voice-agent.service.d/vendor-script.conf` — `Environment=CTX_CACHE=1`
- Verify: `/proc/<aim-voice-agent-PID>/environ` contains `CTX_CACHE=1`.

### 1.8 Provider Lock for Inbound (INBOUND_PROV_LOCK)  **VERIFIED-LIVE**
- What: Routes lean/standard to Sarvam Bulbul v3/priya, premium to ElevenLabs.
- Flag: `INBOUND_PROV_LOCK=1` in systemd drop-in (same file as CTX_CACHE above).
- Verify: `/proc/<aim-voice-agent-PID>/environ` contains `INBOUND_PROV_LOCK=1`.

### 1.9 W3 Multi-Channel Memory (lead_memory/episodes)  **VERIFIED-LIVE**
- What: Durable PG-outbox extraction of lead episodes, survives restart. FORCE-RLS tables.
- Flag: none (structural change). State: `design/W3b-EXTRACTION-STATE.md`.

### 1.10 W4 Memory Read Side  **VERIFIED-LIVE**
- What: PG retrieval into inbound agent + CRM Memory tab. `LEAD_MEMORY_PG=1`.
- Verify: CRM `/crm/{phone}` shows Memory tab with prior conversation episodes. 10/10 verification.

### 1.11 Never-Silent Apology Guard  **VERIFIED-LIVE**
- What: On any uncaught exception → speaks apology + hangs up gracefully. Per-turn recovery voice.
- Location: `aim_voice_agent.py:2127-2147` (outer) + `:2508 _speak_recovery()`.
- Already present in box golden `1614be09` — NOT rebuilt (verified and confirmed present).

### 1.12 LLM Provider Pool  **VERIFIED-LIVE**
- What: `llm_router/provider_pool.py` — 9 Groq keys, least-used pick, per-key 429 cooldown, hot-reload. Groq → SambaNova → OpenRouter-free FallbackAdapter.
- Verify: force a 429 on one Groq key → system rotates to next key without call failure.

### 1.13 Telephony T1+T2 DDL (Flag-OFF)  **VERIFIED-LIVE (DB applied, routes dormant)**
- What: 3 FORCE-RLS tables in PG: `sip_trunks`/`sip_trunk_credentials`/`sip_trunk_health_log`. `is_campaign_eligible` GENERATED column (B1 campaign gate). `_global` Vobiz trunk seeded. Commit `f0efa6c`.
- Flag: `TRUNK_REGISTRY_ENABLED` default OFF (resting byte-identical).

### 1.14 Telephony T3 trunk_registry Mount (Flag-OFF)  **VERIFIED-LIVE (mount dormant)**
- What: 16-route `trunk_registry` API mounted in `caller.py:7349-7393` (0-del/45-add). Flag OFF → `/trunk-registry/*` returns 404. Box md5 `44b867ea` (pre-leads-wave; current golden is `32e6062f`). Commit `46301d2`. Backup `caller.py.T3bak.20260615-004201`.
- Flag: `TRUNK_REGISTRY_ENABLED=1` to activate.
- Verify (dormant): `GET /trunk-registry` returns 404.

### 1.15 Outbound Recordings (Egress → DO Spaces)  **VERIFIED-LIVE**
- What: Outbound auto-egress OGG → DO Spaces + presigned URL. Inbound finalize-on-read. Unified `/api/calls/{room}/transcript`. CRM player. 90-day retention.
- Verify: after a call, `GET /api/calls/{room}/transcript` returns `recording_url` with a presigned URL.

### 1.16 Inbound Recording  **VERIFIED-LIVE**
- What: `AIM_RECORDING_ENABLED=1` in `.env`. Inbound calls recorded.
- Verify: `/opt/famit-agent/.env` contains `AIM_RECORDING_ENABLED=1`.

### 1.17 Callback/Retry Kill-Switch  **VERIFIED-LIVE** (2026-06-16)
- What: `RETRY_SCHEDULER_ENABLED` default OFF gates the dial point in `caller.py scheduler_loop` — stops runaway retry spam. 7 spam entries in `retry_queue.json` cleared. Box caller.py md5 `6d9f9e7d`. Commit `6aa1f32`.
- Branch: `fix/callback-retry-scheduling`. Backup `caller.py.bak.20260616-041519`.
- PENDING: the full scheduler REBUILD (correct ≤2 retries, next-day cadence, etc.) is IN PROGRESS. Kill-switch is live.

---

## 2. LEADS / CRM

### 2.1 Leads Management — Sort, Delete, Multi-Select  **VERIFIED-LIVE** (2026-06-15)
- What: `/leads` page — sort dropdown (Newest/Oldest/Name/Status/Score), multi-select + bulk delete, per-row hover-trash delete, delete-all type-DELETE-to-confirm modal. `/run` manual-pick sort.
- Backend caller.py md5: `32e6062f`. Panel BUILD_ID: `xF8YUvBmTwYj_yP4w7WY4`.
- Backup (BE): `/opt/famit-agent/caller.py.leadsmgmtbak.20260615-174918`. Backup (panel): `/opt/famit-panel/.next.leadsmgmtbak.20260615-124143`.
- Verify: `panel.famit.in/leads` → sort dropdown visible + works; hover a row → trash icon appears.

### 2.2 CRM Core + Business Brain  **VERIFIED-LIVE**
- What: Unified person spine. CRM page at `/crm`. Lead detail with call history, transcript player, Memory tab.
- Verify: `panel.famit.in/crm` → 200; `/crm?phone=XXXX` → lead detail view.

### 2.3 Handoff Name / Clean Line  **VERIFIED-LIVE**
- What: Handoff list shows person's name; clean call-end line. Commit `4db497f`. Founder confirmed live.

### 2.4 AIM Access + PIN Change  **VERIFIED-LIVE**
- What: `/ai-manager/numbers` CRUD + `POST /firewall/pin/change` (old→new + lockout). BUILD_ID `sTCWP4Jj…`.
- Verify: `panel.famit.in/ai-manager` → 200; try PIN change flow.

### 2.5 Workflow/Funnel Execution  **VERIFIED-LIVE**
- What: `POST /funnels/{id}/run` via `_mint_run_token`. Human labels, 4 templates. Verified 200 + run_id + NO auto-ring. BUILD_ID `A7YHO-5a5p7ZcKqSUrKOo`.

---

## 3. COMMS / TELEGRAM

### 3.1 DB Schema (4 FORCE-RLS tables)  **VERIFIED-LIVE** (on box PG)
- What: `comm_sessions`/`comm_send_log`/`comm_consent_log`/`comm_asset_cache`. All FORCE-RLS, append-only consent. Cross-tenant isolation proven. DDL `communication/db/ddl_comm.sql` md5 `3abd30fb`.
- Verify: `SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname LIKE 'comm_%'` → all true.

### 3.2 Bot Token in Vault  **VERIFIED-LIVE**
- What: Founder Telegram bot `mr_kunal_bot` token stored AAD-encrypted in `provider_credentials` (row `d3303376-…`). Cross-tenant AAD binding proven (InvalidTag if copied). `getMe ok=true` proven live.

### 3.3 Telegram Adapter + Engine  **VERIFIED-LIVE** (flags ON)
- What: `comm/` package — channel-neutral engine, Telegram Bot API adapter, send_log writer, webhook (FAIL-CLOSED HMAC), sessions. Flags `COMM_ENABLED=1` + `COMM_TELEGRAM_ENABLED=1` live in `.env`.
- Caller.py mount: `7830a7831,7873` (+43 lines, 0 deletions), box caller.py was `73d7be4f` at mount time.
- Verify: `GET /comm/channels` (authed) → 200 (not 404 = routes mounted).

### 3.4 Founder Hot-Lead Alert + Post-Call Auto-Summary  **VERIFIED-LIVE** (flags ON)
- What: When call ends with interest ≥ 70 → `asyncio.create_task(comm.post_call.run(snap))` fires a Telegram alert to founder + (when a contact chat_id exists) a post-call summary. Earner hot-path cost: 0.047ms sync snapshot + 0.015ms create_task.
- Flags: `FEATURE_TELEGRAM_FOUNDER_ALERT=1` + `FEATURE_TELEGRAM_FOLLOWUP=1` in `.env`.
- Commits: `889807e`, `e58c836`. Caller.py hook at `2795a2796,2822` (+28 lines).
- Verify: Watch `.env` for these flags = 1. After an inbound call closes hot → check `comm_send_log` for a new `kind=alert` row.

### 3.5 Real Message Delivered + Founder Chat_ID  **VERIFIED-LIVE** (2026-06-15)
- What: Real Telegram message (message_id=4) landed on founder's phone. Chat_id `1862240811` persisted as sentinel row in `comm_sessions`.
- Verify: `SELECT external_chat_id FROM comm_sessions WHERE call_id='__founder_chat__' AND tenant_id='admin'` → `1862240811`.

### 3.6 GetUpdates Poll Worker (comm-poll.service)  **VERIFIED-LIVE** (2026-06-15)
- What: Standalone `comm/poll_worker.py` running as systemd service `comm-poll`. Receives inbound Telegram messages → feeds `comm.webhook.handle` → brain replies. Real round-trip proven (founder said "done" → Riya replied grounded in prior call context).
- Service: `/etc/systemd/system/comm-poll.service` enabled + `active (running)` PID 2961553.
- Verify: `systemctl status comm-poll` → active. Sending a message to `@mr_kunal_bot` → Riya replies within ~2s.

### 3.7 Conversation Brain (W2) — Riya replies on Telegram  **BUILT-NOT-DEPLOYED** (flag OFF)
- What: `comm/brain.py` — grounded Hinglish LLM reply (one Groq call, session-seeded with call_summary). `comm/deeplink.py` — signed single-use `?start=` consent link. `comm/ratelimit.py` — per-tenant flood gate + daily Groq cap.
- Status: offline-green (all 3 test suites PASS), committed on `fe/unify-run-wavec`. Waiting on `COMM_BRAIN_ENABLED=1` flip + `setWebhook` or poll worker flip ON.
- Actually — the poll worker IS live and running. Brain flag `COMM_BRAIN_ENABLED` defaults OFF. To activate: set `COMM_BRAIN_ENABLED=1` in `.env` + restart famit-caller.
- Known gap: occasional hallucination in Riya's replies (documented, not a blocker — it replies).

---

## 4. CREATIVE / VIDEO

### 4.1 Video Studio — Real MP4 Render  **VERIFIED-LIVE** (2026-06-15)
- What: Composite MP4 renders at `panel.famit.in/creative/video`. Real h264 1080x1920 + aac (ffprobe proven). 2 videos in library. Sarvam TTS voiceover. DO Spaces storage.
- Flags: `FEATURE_VIDEO_STUDIO=1` + `FEATURE_VIDEO_COMPOSE=1` + `VIDEO_PROVIDER=compose` (caller .env); `FEATURE_VIDEO_LIBRARY=1` + `AIASSET_SERVICE_TOKEN` (aiasset .env). Backup: `.env.VIDACTbak.20260615-010535`.
- Worker: `media_gen/video/compose_worker.py` deployed on box (`/opt/famit-agent/media_gen/video/compose_worker.py`). Auto-spawns a detached render process on `POST /batches/{id}/approve`.
- Commit: `ef95422` (W7+W8 FE). `2d26c98` (VideoCreatePanel/BatchProgress/TierTabs/etc.).
- Verify: `panel.famit.in/creative/video` → real studio (NOT DormantCard). `GET /api/creative/video/campaigns` (authed) → 200 with real campaigns. `GET /assets?media_type=video` → 2 real videos.

### 4.2 Video Studio FE (Panel UI)  **VERIFIED-LIVE**
- What: Full functional FE — VideoCreatePanel, TierTabs (Composite default ≈₹0.25/clip, no key), BatchProgress job-status poller, `<video>` AssetMedia player, library Images↔Videos toggle.
- Commit: `2d26c98`. BUILD_ID `u6yKGIuhALhhzdzQcywXQ` (panel now `xF8YUvBmTwYj_yP4w7WY4` from leads wave).

### 4.3 AI Asset Service (famit-aiasset on VPC :8310)  **VERIFIED-LIVE**
- What: `/assets` CRUD, video library bridge (register-video internal endpoint), DO Spaces integration.
- Verify: `curl http://10.122.0.4:8310/status` → 200 from voice box internal network.

### 4.4 Provider Registry for Video (REGISTRY_FOR_VIDEO strangler)  **VERIFIED-LIVE (flag OFF)**
- What: `media_gen/video/client._resolve_key` — if `REGISTRY_FOR_VIDEO=1`, uses provider-registry for keys; else falls back to env. Flag default OFF = resting byte-identical. Commit `a71b87a`.

---

## 5. CONTROL PLANE (Foundation Control Layer)

### 5.1 Foundation Control Layer — LIVE + ENFORCING (2026-06-11)  **VERIFIED-LIVE**
- What: Tier-0 Super-Admin control plane. Per-vendor HIDE/LOCK/ON entitlements, plans, suspend, act-as impersonation, immutable audit. `CONTROL_ENABLED=1` in `.env`.
- Results: 18/18 T1-T18 probes PASS. HIDE→404, LOCK→402, suspend→data-preserved+login-block, legacy `FamitCall2026`→403 (also via Cloudflare), no cross-tenant cache bleed.
- Backup: `/opt/famit-agent/.env.CLbak.20260610-195647`. Panel backup: `/opt/famit-panel.CLbak.1781120589`.
- Verify: `GET /admin/anything` with `FamitCall2026` header → 403. `GET /super-admin/` (panel) → 200.
- Residual: Panel `/login` mints stateless HMAC token (no jti) → suspension relies on status-floor, not crypto-revoke (T15 still PASSES).

### 5.2 ACID Wallet + Firewall  **VERIFIED-LIVE**
- What: 4 PG FORCE-RLS tables (wallet_accounts/transactions/holds/idempotency, INTEGER paise). 24-concurrent no-oversell proven. `FIREWALL_ENABLED=true`. 21/21 live proof.
- Verify: `SELECT * FROM wallet_accounts WHERE tenant_id='admin'` — row exists. `POST /firewall/ping` → 200.
- Note: `wallet.debit()` does NOT exist (was deferred). `wallet.reserve`/`settle` are implemented.

### 5.3 Action Firewall (PIN step-up)  **VERIFIED-LIVE**
- What: `firewall.py` — HS256 sub-bound step-up token (TTL 300s, single-use jti). PIN salted-hash. `FIREWALL_ENABLED=true`.

### 5.4 Immutable Audit Log  **VERIFIED-LIVE**
- What: PG `events` table (NOT JSONL). Append-only. Every admin action logged.

---

## 6. BILLING / WALLET

### 6.1 Run-Platform Billing (RUN-PLATFORM A+B+C)  **VERIFIED-LIVE**
- What: Env-based billing meter (`USD_INR=95.2`, `EL_RATE=4.76`, Sarvam v2/v3 split). Preview fix (force `audio/mpeg`). 4-step Run stepper + cost-meter + provider-lock banner + exclude-called toggle.
- Commit: `fa99acb`. BUILD_ID `TU16Mn1DcJVmxnxr2GVyL`.
- Verify: `/run` page → 4-step stepper visible; cost-meter shows ₹/call estimate.

### 6.2 Provider Registry W1-W5  **VERIFIED-LIVE**
- What: `PROVIDER_REGISTRY_ENABLED=1`. 3 FORCE-RLS tables, AAD AES-256-GCM creds, SSRF guard, PIN-step-up reveal (single-use jti). 6/6 live verify PASS. Bug fixed: `schema.py` UUID stringify.
- Verify: `GET /provider-registry` (authed) → 200 with list. `PROVIDER_REGISTRY_ENABLED=0` makes → 404.

### 6.3 WhatsApp B1/B2/C2  **VERIFIED-LIVE**
- What: Real wamid proven. `FEATURE_WHATSAPP=1`. AI WhatsApp template builder backend.
- Verify: `/opt/famit-agent/.env` → `FEATURE_WHATSAPP=1`. `GET /whatsapp/templates` (authed) → 200.
- Note: Frontend WhatsApp template builder UI is a KNOWN GAP (backend exists, no full UI).

### 6.4 Dormant Feature Modules (9 modules, flag OFF)  **BUILT-NOT-DEPLOYED (dormant)**
- What: booking, payments, support, forms, funnels, workflow, ads, media, lifecycle — all MOUNTED, flag OFF, resting byte-identical. Security holes (X-Tenant-Id header, body-tenant) refactored to token-deriving `build_router`.
- Note: `FEATURE_ADS=1` flip would expose existing ads endpoints immediately (quick-win).

---

## 7. RAG

### 7.1 RAG W0 Kill-Switch  **VERIFIED-LIVE**
- What: `RAG_INJECT_ENABLED` flag (`1` in `.env`). Set to `0` + restart aim-voice-agent → instant RAG disable. Box aim_voice_agent.py md5 `8335d4ba` post-W0.
- Verify: `grep RAG_INJECT_ENABLED /opt/famit-agent/.env` → `1`. The 3 grounding sites are all gated.

### 7.2 RAG W1 Retrieval Hardening  **VERIFIED-LIVE**
- What: `dense=False` default (zero embed RTT), `_global` UNION under RLS, `kb_query_log` FORCE-RLS, `KB_INCLUDE_GLOBAL` tunable. 8/8 probes PASS. Commit `266f2c1`.

### 7.3 RAG W2 Telecaller Corpus  **VERIFIED-LIVE**
- What: 120 chunks / 41 `_global` sources seeded. FTS 6-12ms. Commits `ff44770`/`41fde4a`/`8a62fde`.
- Verify: `GET /kb/sources` (authed) → at least 41 global sources with chunk counts.

### 7.4 RAG W3 KB Management Backend  **VERIFIED-LIVE**
- What: `GET /kb/sources`, `POST /kb/upload` (text|PDF), `POST /kb/test-retrieve`, `GET /kb/gaps`. Commit `a91d049`.
- Verify: `GET /kb/sources?scope_campaign_id=X` (authed) → 200 with source list.

### 7.5 RAG W7 Knowledge UI  **VERIFIED-LIVE**
- What: `/knowledge` page in panel. BUILD_ID `YV9obkLRRD0U5oX-CPOCH`.
- Verify: `panel.famit.in/knowledge` → 200.

---

## 8. INFRA

### 8.1 FORTRESS 3-Box Topology  **VERIFIED-LIVE**
- Boxes:
  - `famit-panel-2 143.110.247.249` (priv `10.122.0.2`) — panel, egress-locked, Cloudflare-fronted
  - `famit-livekit 168.144.153.145` — voice box, runs caller.py + aim-voice-agent + agent.py
  - `famit-hatchet 68.183.94.38` (priv `10.122.0.3`) — Hatchet + Logto
- Hardening: DO egress-locked firewall, Telegram alerts, Cloudflare Full Strict.
- P0 secrets gate: gitleaks v8 + pre-commit hook + CI `secrets.yml`.

### 8.2 Hatchet Durable Orchestration  **VERIFIED-LIVE (hello-world; NOT in request path)**
- What: Hatchet-lite on `famit-hatchet` (Postgres-broker, no RabbitMQ). Hello-world durable job proven. NOT wired into caller.py yet.
- Connection env (for future cutover): `HATCHET_CLIENT_HOST_PORT=10.122.0.3:7077`.

### 8.3 Logto Self-Hosted OIDC  **VERIFIED-LIVE (running; NOT wired into caller.py)**
- What: `logto:1.40.1` + own Postgres on `famit-hatchet`. Localhost-only (ufw+`hatchet-fw`). Seeded. Reboot-safe. Issuer `https://auth.famit.in/oidc` (DNS pending).
- Verify: `curl http://10.122.0.3:3001/oidc/.well-known/openid-configuration` from hatchet box → 200.
- **GATED**: founder console step needed to set first admin (no headless OSS first-admin). See `infra/logto/CONSOLE_SETUP_HOWTO.md`.

### 8.4 Inbound Voice (aim-voice-agent service)  **VERIFIED-LIVE**
- What: `aim-voice-agent.service` running on voice box. PID `2739156` (as of 2026-06-15). Box md5 `1614be09`.

---

## 9. PANEL UI

### 9.1 Panel Core Shell  **VERIFIED-LIVE** (BUILD_ID `xF8YUvBmTwYj_yP4w7WY4`)
- What: Next.js App Router at `panel.famit.in`. 8/8 routes verified 200: /integrations, /super-admin/integrations, /creative/video, /run, /crm, /ai-manager, /workflows, /knowledge.

### 9.2 Integrations UI  **VERIFIED-LIVE**
- What: `/integrations` page — provider registry CRUD, circuit-state badges, PIN-step-up reveal, admin override panel. Commit `f3d9bd4`.
- Verify: `panel.famit.in/integrations` → 200.

### 9.3 Performance Overhaul (6 units)  **VERIFIED-LIVE**
- What: Pagination, react-query cache, virtualization, code-split, gzip 90%/10× (`/api/*` 27425B→2746B), immutable static cache. BUILD_ID `p6hSTJX9R46-NQdLf8Daw`. Commits `dfb663f`/`40caf3c`/`d42d130`/`7068bd7`/`d48ed46`/`c030ee4`.

### 9.4 AIM Sessions Page  **VERIFIED-LIVE**
- What: `app/ai-manager/sessions/page.tsx` — transcript list + TranscriptModal. Commit `73054f9`.
- Verify: `panel.famit.in/ai-manager/sessions` → 200.

### 9.5 CRM Transcript View + Asset Preview Fix  **VERIFIED-LIVE**
- What: Chat-style transcript (AI-left/customer-right). Asset presigned preview (flatten `{asset,versions}` envelope). BUILD_ID `tuuIjqN7fCf_iEL-obLon`. Commits `d9daa86`/`6940742`.

### 9.6 Communication Tab Visible  **VERIFIED-LIVE** (2026-06-15)
- What: Communication tab visible on `panel.famit.in` (deployed with leads wave, BUILD_ID `xF8YUvBmTwYj_yP4w7WY4`).

### 9.7 Super-Admin Panel  **VERIFIED-LIVE**
- What: `/super-admin/*` — tenant management, entitlements (HIDE/LOCK/ON), plan assignment, act-as impersonation. Verify: `panel.famit.in/super-admin` → 200.

---

## ⚠️ BUILT-NOT-DEPLOYED / GAPS

| Item | What Exists | What's Missing |
|---|---|---|
| **Telegram Brain (W2) flip** | `comm/brain.py` + `deeplink.py` + `ratelimit.py` offline-green on box | `COMM_BRAIN_ENABLED=1` + `setWebhook` NOT flipped live (poll worker is live; brain just needs the env flag) |
| **Callback/Retry REBUILD** | Kill-switch live (spam stopped). `_scheduler_rebuild/DESIGN_SPEC.md` exists. | Rebuilt engine not yet built; `RETRY_SCHEDULER_ENABLED` stays OFF until rebuild deployed |
| **Telephony T4 FE** | T3 routes mounted flag-OFF | `/app/telephony/page.tsx` trunk management UI not built |
| **Vault (V0-V8)** | Design spec `design/VAULT-MASTER-PLAN.md` complete | New `droplet_work/vault/` package + DDL not built |
| **Hatchet ↔ caller.py cutover** | Hatchet running, hello-world proven | `HATCHET_CLIENT_HOST_PORT` env set but caller.py NOT wired to submit jobs |
| **Logto ↔ caller.py wiring** | Logto OIDC running + seeded | `caller.py` still uses legacy auth; Logto integration is the future auth spine |
| **WhatsApp Template Builder UI** | Backend AI template-builder exists | No dedicated frontend page for it |

---

## Box Golden Summary (as of 2026-06-18)

| Service | File | md5 | Note |
|---|---|---|---|
| EARNER | `agent.py` | `9150fabe4ff62b4b4470f9a87df346e5` | NEVER edit/restart |
| Inbound agent | `aim_voice_agent.py` | `1614be09` | W4 memory + multi-lang + never-silent |
| FastAPI app | `caller.py` | `6d9f9e7d` (post kill-switch) | Current box golden on `fix/callback-retry-scheduling` |
| Panel | BUILD_ID | `xF8YUvBmTwYj_yP4w7WY4` | Leads wave (2026-06-15) |

**ROLLBACK ANCHORS** (most recent):
- BE → `sudo cp /opt/famit-agent/caller.py.bak.20260616-041519 /opt/famit-agent/caller.py && sudo systemctl restart famit-caller`
- Panel → `mv /opt/famit-panel/.next /opt/famit-panel/.next.bad && mv /opt/famit-panel/.next.leadsmgmtbak.20260615-124143 /opt/famit-panel/.next && systemctl restart famit-panel`
- Outbound DID → restore `.env.VOBIZbak.20260615-164935` + restart famit-caller
