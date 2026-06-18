# RESTORE — PENDING + TRIED/BLOCKED (archivist snapshot 2026-06-18)

> Sources: MASTER-INDEX.md §4+§5, HOLD-STATE.md, GOLDMINE-QUEUE.md, CALLBACK_SCHEDULER_REBUILD_STATE.md,
> COMMUNICATION-MASTER-PLAN.md, design/TELEGRAM-ECOSYSTEM-DIAGNOSIS.md, AGENT_LEARNINGS.md.
> Branch: `fix/callback-retry-scheduling`. Box caller.py md5 `6d9f9e7d` (kill-switch deployed).
> Earner agent.py md5 `9150fabe` UNCHANGED — sacred.

---

## SECTION 1 — PENDING BUILD QUEUE (ordered by impact + earner-safety)

### T0 — HARD GATE (next caller.py wave — must go first)
**Scheduler retry-bug rebuild**
- What: `caller.py scheduler_loop` — kill-switch (commit `6aa1f32`, `RETRY_SCHEDULER_ENABLED` default OFF) stops spam NOW. The FULL rebuild is in-progress: `CALLBACK_SCHEDULER_REBUILD_STATE.md` (Workflow 1 = DESIGN running, Workflow 2 = EXECUTE not started). Design spec target: `droplet_work/_scheduler_rebuild/DESIGN_SPEC.md`. Rules: ≤2 retries, next-day cadence, no-callback-on-pickup, busy→short reschedule, "call me at X"→that exact time, dedup + compliance.
- Files: `caller.py` + `droplet_work/_scheduler_rebuild/` (new package).
- Box-mutating: YES (caller.py). Claim `CALLER_EDIT_LOCK.md`. Deploy = scp to /tmp → sudo cp → restart famit-caller.
- Model: Opus design already running; Sonnet execute.
- Design doc: `CALLBACK_SCHEDULER_REBUILD_STATE.md` + `_scheduler_rebuild/REQUIREMENTS.md`.
- Gate before: telephony T5, any campaign resume, any outbound.

---

### PARALLEL QUEUE (touch neither caller.py nor panel — launch immediately once HOLD lifted)

**P1 — Eval/replay harness (#44) — highest leverage**
- What: offline persona-scenario runner + pinned-model LLM-judge (temp 0). Scores every voice change (TTFT p95, guard-violations, language-mirror, no-announce, objection-handling). Gate output (`eval PASS`) required before any future voice flag flip.
- Files: NEW `droplet_work/eval/` package. No caller.py, no panel, no box restart. Offline only.
- Box-mutating: NO.
- Model: Opus for judge design; Sonnet for runner.
- Design doc: `design/eval-harness.md` + `design/RAG-EVAL-SPEC.md`.

**P2 — Telegram ecosystem fix (6 units, HIGHEST earner-value communication fix)**
Based on `design/TELEGRAM-ECOSYSTEM-DIAGNOSIS.md` — the comm system is live but broken in 4 ways:

| Unit | What | Files | caller.py? |
|---|---|---|---|
| Unit 1 (⭐ #1 FIX) | Seed `comm_sessions` with real call facts post-call (stops hallucination). Add `sessions.py:seed_call_context()` + call from `post_call.py:run`. Add missing `company_name/product_name/product_summary` columns to `comm_sessions`. | `comm/sessions.py`, `comm/post_call.py`, `db/ddl_comm_v2.sql` | NO |
| Unit 2 | Telegram hot-lead HANDOFF cards to telecaller team (not just founder). Mirror `notify_handoff_team` loop using `_handoff_get()` → send Telegram card per team member. | `comm/post_call.py`, `comm/founder_alert.py` | NO |
| Unit 3 | Inbound call → Telegram follow-up seam. Add detached `create_task(comm.post_call.run(...))` to `aim_voice_agent.py:_AimSessionLogger.finish()`. Snapshot from `ai_manager_sessions` PG row + `_fields["_interest_note"]`. | `aim_voice_agent.py` ONLY | NO (aim-voice-agent restart only) |
| Unit 4 | Rich follow-up (AI template + banner from ai_asset + video). Fetch presigned banner URL from `ai_asset` loopback (`10.122.0.4:8310`) + pass as `MediaItem` to `telegram.sendPhoto`. | `comm/post_call.py` | NO |
| Unit 4b | Composite video attach (presigned MP4 via `submit_video_job` → library → sendVideo). | `comm/post_call.py` | NO |
| Unit 6 | Campaign-less/script-only composite video in Video Studio UI. Allow Generate without a campaign (send `_adhoc` brief; BE already has slate fallback). 1 FE line change + 1 BE brief tweak. | `famit-panel/app/creative/video/` + `compose_worker.py` brief resolver | NO |

Model: Sonnet for all units.

**P3 — Panel deploy (fe/unify-run-wavec)**
- What: deploy Communication tab FE + Video Studio FE from `fe/unify-run-wavec` to `panel.famit.in`. Build locally → backup → scp → atomic swap.
- Files: panel build only. No box edit.
- Box-mutating: panel box only (NOT earner box).
- Gate: founder OK per HOLD-STATE.md.

**P4 — LiveKit semantic turn-detector (#42)**
- What: additive `TurnDetector` kwarg (Silero VAD, Qwen2.5-0.5B INT8) on `VoiceAssistant` in `aim_voice_agent.py`. Replaces silence-timeout endpointing (~99.4% Hindi accuracy).
- Files: `aim_voice_agent.py` + `requirements.txt`.
- Box-mutating: aim-voice-agent restart only.
- Model: Sonnet.
- Design doc: `design/voice-quickwins.md`.

**P5 — Inbound warm-cache + pooled HTTP (#47)**
- What: Redis hot-cache (60s TTL) for STT/LLM/TTS provider config + single `httpx.AsyncClient` per session. Saves 50-150ms inbound TTFT. Redis `:6380` already on box.
- Files: `aim_voice_agent.py` only.
- Box-mutating: aim-voice-agent restart only.
- Model: Sonnet.

---

### AFTER T0 (caller.py slots — serialize in this order)

**A6 — DPDP delete-my-data (#33)** — `POST /leads/{phone}/erase`: purge memory JSON + soft-delete `lead_memory`/`episodes` + DPDP-erasure event to immutable `events` + 204. CRM "Erase lead data" button. Legal exposure (India DPDP Act 2023). Files: `caller.py` (+1 route) + `famit-panel/app/crm/`. Caller.py: YES.

**A7 — Mid-call `lead_is_hot` tool (#35)** — tool declaration in `aim_voice_agent.py` (~30 lines) + `POST /leads/{phone}/mark-hot` (caller.py) + `lead.hot` event + Telegram hot-lead alert + CRM 🔥 badge. Pairs with Telegram units above. Files: `aim_voice_agent.py` + `caller.py` (+1 route). Caller.py: YES.

**A8 — Post-call workflow event (#37)** — emit `call.completed` into workflow DSL from `_finalize_call` as `asyncio.create_task`. Activates Workflow builder as real automation engine. Files: `caller.py` hook only. Caller.py: YES.

**A9 — Inbound recording Egress (#30)** — mirror outbound OGG→DO Spaces Egress for inbound rooms. Files: `aim_voice_agent.py` + `caller.py`. Caller.py: YES. Design-first (copy outbound Egress path exactly).

**A10 — Inbound spend metering (#31)** — wire inbound call-end to `wallet.reserve→settle`. Flags `WALLET_ENABLED` + `INBOUND_BILLING_ENABLED` both default OFF. Files: `caller.py` + `wallet.py`. Caller.py: YES.

---

### BIG SEQUENTIAL BUILDS (P1)

**B1 — Communication W1 Telegram** (`communication/COMMUNICATION-MASTER-PLAN.md §8 W1`) — NEW `droplet_work/comm/` package (3 tables, Telegram adapter, founder hot-lead alert, post-call auto-summary, channel setup UI). Status: DESIGN DONE, BUILD NOT STARTED. GATED on founder BotFather token. Caller.py: YES (2 small `create_task` insertions + mount — last step). Model: Opus BE, Sonnet FE.

**B2 — Vault V0-V8** (`design/VAULT-MASTER-PLAN.md`) — PIN-gated AES-256-GCM per-vendor envelope, 5 FORCE-RLS tables, append-only access log. Key fact: PIN = salted sha256, NOT Argon2id (noted in spec). `vault.get_secret()` is the #1 cross-product gap. Files: NEW `droplet_work/vault/` + `db/ddl_vault.sql` + caller.py mount. Caller.py: YES. Model: Opus BE, Sonnet FE.

**B3 — Communication W2 LLM brain** (`§8 W2`) — channel-neutral brain, Telegram webhook (`POST /comm/webhook/telegram/{tenant}` fail-CLOSED), signed single-use deep-link consent. Caller.py: YES.

**B4 — RAG W4 grounding cache** (`RAG-MASTER-PLAN W4`) — `kb/grounding_cache.py` keyed by `(tenant,campaign,stage,channel,kb_version)` + campaign-save ingest + PII-scrub + versioning + quota. Files: `aim_voice_agent.py` + caller.py campaign-save hook + new module. Caller.py: YES.

**B5 — Telephony T4 FE** — `app/telephony/page.tsx` Core_2 port: trunk cards, 3-step Add-trunk wizard, inbound-routing panel, per-DID kill switch. Panel only. No caller.py.

**B6 — Telephony T5 strangler (flag ON)** — cut `TRUNK_REGISTRY_ENABLED=1`. Gate: T0 done + T4 FE done + founder BYO Plivo DID + real outbound ring before+after. Caller.py: YES.

**B7 — Run-Campaign audience-builder UX** — composable filters (hot/warm/cold, by-upload, manual), Excel `.xlsx` support (`openpyxl`), `batch_id`, `GET /leads/batches`. Port Core_2. No dial-loop change.

**B8 — Communication W3 Email** (`§8 W3`) — Resend adapter + SPF/DKIM/DMARC wizard + List-Unsubscribe + multi-step template builder. GATED on Resend key.

---

### P2 (spec'd / lower urgency)

- **ADS ENGINE activation (#26)** — `FEATURE_ADS=1` flip + panel deploy. No new code. TINY.
- **Inbound analytics dashboard (#34)** — `/analytics/inbound` page. FE-first (client-side agg over existing `/calls`); BE aggregation routes after T0.
- **Video Studio hardening U7-U10** — Signal-Loop lineage, reaper/moderation, Hatchet-saga upgrade of `enqueue`. `design/VIDEO-STUDIO-MASTER-PLAN.md`.
- **Cost-meter re-tune** — `tts_chars_per_min` 900→330-360 in `llm_router/tiers.py` (pure data edit; meter is ~2.5× inflated).
- **Communication W4-W6** — unified inbox + `book_slot` agentic tool (W4); SMS MSG91+DLT (W5, hard-gated); CAPI revenue-signal closure = the moat (W6).
- **AIM dedicated service** — 39-unit plan. GATED on DO droplet limit raise.
- **WhatsApp residuals** — WB-2 `status=partial` fallback, WB-3 banner via `header_url`, WB-4 Submit-to-Meta. All GATED on Meta.
- **Growth OS** — fix `@growth-os/events` codegen build first; then 6-container stack. GATED on DO droplet raise.
- **Hatchet caller.py cutover** + **Logto caller.py wiring** — both gated on other work completing.
- **Control-Layer C10** (AI-Copilot gate, T18) + **C12** (CI registry-drift guard).
- **LoRA/QLoRA fine-tune (#46)** — DEFERRED until eval harness + self-host latency decision + GPU.
- **Customer-mode sales-in inbound worker** (`design/CUSTOMER-MODE-BUILD-STATE.md`) — large, needs dedicated megaplan wave.

---

## SECTION 2 — TRIED / BLOCKED / DEAD-ENDS

### PERMANENT PLATFORM CONSTRAINTS (never retry)

**DE-1: Telegram CANNOT cold-message a lead's phone**
- What tried: assumed bot could DM a lead post-call automatically.
- Why blocked: Telegram bots can only send to a `chat_id`, and a `chat_id` only exists AFTER the user has messaged the bot first (tapped Start). No phone→chat_id lookup exists on the Telegram platform.
- Rule: lead-facing Telegram rich follow-up requires a deep-link tap first (`comm/deeplink.py:120 mint`). For zero-tap lead follow-up, use WhatsApp (existing `_wa_ai_followup`) or SMS (DLT-gated). NEVER promise cold Telegram DMs to leads.

**DE-2: WhatsApp blocked (Meta business unverification)**
- What tried: full WhatsApp automation pipeline built (W-A1/A2/B1/B2/C2; real wamid proven; AI template builder live).
- Why blocked: Meta business unverified — 4 pending values + need 1 approved template. `FOUNDER-META-WHATSAPP-FIX.md` has the exact steps.
- Rule: do NOT touch `_wa_send` / `_wa_ai_followup` / the live WA earner path until Meta verification complete. Build Telegram-first; WA joins as a thin strangler wrapper later.

**DE-3: Outbound 486 carrier spam-block (old DID)**
- What tried: repeated test calls on old DID `+918071583488` to verify outbound (pre-carrier-block period).
- Why blocked: DID carrier-spam-blocked since 2026-06-13 ~12:51 UTC. Returns 486/480/603 immediate (pre-ring). The "486" is carrier-rejected before ringing — NOT a valid ring. Evidence in `var/retry_queue.evidence.*`.
- Rule: NO test calls until Vobiz KYC-clears / rotates the DID. A real ring = `inviteToTryingMs > 0` AND SIP 180/200 — NOT the agent-join line.

**DE-4: Sarvam Bulbul v2 garbles English loan-words**
- What tried: provider-lock routed campaign voice to `bulbul:v2` with default speaker.
- Why failed: Bulbul v2 has no code-mix support — English words in Hindi scripts garble ("BHK"→"उसाई").
- Fix applied: `SARVAM_TTS_MODEL=bulbul:v3` + `SARVAM_TTS_SPEAKER=priya` (`.env.SURGbak.20260614-154923`). Never revert to v2 for Hinglish scripts.

**DE-5: Webhook mode for Telegram inbound is permanently blocked (no public HTTPS ingress)**
- What tried: `setWebhook` approach for inbound Telegram updates.
- Why blocked: caller (port 8209) is firewalled to panel box `10.122.0.2` only (DO firewall + ufw) — no public tunnel or reverse proxy. `setWebhook` to that endpoint registers a deaf bot; Telegram disables `getUpdates` as mutual-exclusive; the entire inbound path dies silently.
- Fix/rule: stay in `getUpdates`/polling mode (`comm-poll.service` systemd worker, Restart=always, PID 2961553). Only switch to webhook mode when a public panel-proxy or tunnel exists.

**DE-6: Compose worker lazy-import silent failure (Video Studio "green but no video")**
- What tried: activated Video Studio flags; routes returned 200; "green per-component" reported.
- Why failed: `_dispatch_render` lazily imported `compose_worker.enqueue(plan)` but the module did NOT EXIST anywhere. Every submitted batch sat in `running` forever; no error raised (bare `except: pass`). The acceptance test declared success on 200s, not on a real MP4.
- Fix: built `compose_worker.py`; proven real h264+aac MP4 (ffprobe verified, presigned URL, in library).
- Rule: for any "activate X" wave, acceptance = the founder's REAL artifact (playable video, delivered message, ringing call). Grep the whole tree for the target module's definition before claiming a lazy-import path works.

**DE-7: Old inbound-agent ref files are STALE — deploying them breaks the earner**
- What tried/risk: `_inbound_ref/aim_voice_agent.LIVE.py` (md5 `4bbd0956`), `.NEW.py`, `.VERIFY.py` — all stale.
- Why blocked: deploying these overwrites the live box golden (`1614be09`) and loses all post-baseline commits.
- Rule: ALWAYS start edits from `droplet_work/aim_voice_agent.LIVEBOX.py` (md5 `1614be09`). The `_inbound_ref/` files are read-only reference snapshots; never deploy them.

**DE-8: Local caller.py can be stale vs the box — deploying local silently reverts box work**
- What tried: editing local `caller.py` and deploying without pulling box first.
- Why failed: documented in CALLBACK_SCHEDULER_REBUILD_STATE.md — local was `ef9ae696`, box was `32e6062f` (2 sessions of changes diverged). Deploying local would have wiped all box-only waves.
- Rule: ALWAYS `scp` pull + md5 before any caller.py edit. Box is the source of truth. Anchor-string inserts, never LIVEBOX line numbers.

**DE-9: Comm session grounding build-log "PROOF" was faked by manual SQL INSERT**
- What tried/reported: the W1/W2/W3 build log claimed "grounded reply PROOF" for the Telegram brain.
- Why it failed in production: the test proof manually INSERTed `call_summary` via raw SQL. In a real flow NOTHING seeds it — `comm/sessions.py:get_or_create` writes only identity columns; `post_call.py:run` sends the message but never seeds the session. The founder's real test produced hallucinated property details (fabricated "xyz, 2000 sqft, 3 BHK, 1.5 cr").
- Rule: `comm/sessions.py` is missing `seed_call_context()` entirely. Unit 1 of the Telegram ecosystem plan must be built before the brain is trustworthy. A SQL-seeded test is NOT an integration test.

**DE-10: getUpdates ages out — chat_id cannot be derived after ~24 hours**
- What tried: planned to derive the founder's chat_id at deploy time from stale `getUpdates`.
- Why failed: by the time W1/W2/W3 shipped, `getUpdates` returned 0 updates; chat_id was unrecoverable.
- Fix: the sentinel must be persisted AT THE MOMENT of the tap, not derived retroactively. `sessions.py:261 set_founder_chat_id` now auto-persists on tap. HUMAN_TASKS must document the required founder action explicitly.

**DE-11: Past 90k-line rebuild mistake**
- What tried: full rebuild of caller.py from scratch in a prior session (exact commit unknown; pre-baseline).
- Why failed: rewrote ~90k lines; broke production; lost weeks.
- Rule: STRANGLE & EVOLVE, never rebuild. All new capabilities = additive routes + flag-gated + resting byte-identical. Earner gate before+after every deploy.

**DE-12: Groq TPD exhaustion under load**
- What tried: routing all inbound + outbound LLM calls through a single Groq key.
- Why failed: 6 keys share ONE org's 500k tokens/day pool; AIM sessions exhaust quota → silent "thoda sa system slow hua hai" degradation.
- Fix: LLM provider pool (`llm_router/provider_pool.py`, 9 Groq keys, least-used pick, per-key 429 cooldown). Fallback chain: Groq → SambaNova → OpenRouter-free FallbackAdapter.

**DE-13: DO droplet limit 3/3 FULL — cannot add boxes**
- What tried: planned AIM dedicated service + Growth OS 6-container stack requiring new droplets.
- Why blocked: DO account at 3/3 droplet limit. Both are GATED on DO droplet limit raise (founder action).
- Rule: do not design waves that assume a 4th box until founder raises the DO limit.

---

## SECTION 3 — FOUNDER ACTIONS TABLE (gates)

| # | What only the founder can do | How long | Unblocks |
|---|---|---|---|
| F1 | **Vobiz: clear/rotate spam-blocked DID `+918071583488`** (call Vobiz support, KYC-confirm the new trunk `ST_bpGqmc9TL9Ph` — do NOT re-flag it with test calls) | ~1-2 days | All outbound campaign runs, Telephony T5, earner-LLM-fallback |
| F2 | **BotFather: `/newbot` → copy token → tap Start on `@mr_kunal_bot`** (seeds chat_id `1862240811`) | 2 min, free | Communication W1 Telegram build |
| F3 | **Resend API key** | 5 min | Communication W3 Email |
| F4 | **MSG91 account + DLT Principal-Entity registration** (Airtel Business / Tata Tele, ~5-10 days TRAI) | 5-10 days | Communication W5 SMS |
| F5 | **Meta WhatsApp: payment ref 141006 + business verify + subscribe `messages` webhook + 1 approved template** (`FOUNDER-META-WHATSAPP-FIX.md`) | ~3-7 days | WA delivery, hot_lead_alert, cold sends, CAPI moat |
| F6 | **BYO Plivo 2nd trunk number** (₹250/DID + ₹0.60/min) + real outbound ring smoke before+after | 1 day | Telephony T5 flag-ON + outbound redundancy |
| F7 | **DO droplet limit raise** (current 3/3 full) | ~1 day (support ticket) | AIM dedicated service (39-unit), Growth OS 6-container stack |
| F8 | **FE-box root access: nginx `/api/assets/` → `10.122.0.4:8310`** proxy repoint | 10 min | Creative Studio browser demo + Logto DNS |
| F9 | **OpenAI API key** (optional — FTS works without it) | 5 min | RAG dense embeddings (optional upgrade) |
| F10 | **GitHub private repo push** (git init'd locally, remote not set) | 5 min | Remote backup of all work |
| F11 | **ModelScope ↔ Alibaba Cloud bind** (`FOUNDER-MODELSCOPE-BIND.md`) | ~30 min | Image generation (currently 401s) |
| F12 | **OB-PROV / W-OB sign-off** (agent.py edit approval + DID un-rested + real ring before+after) | After F1 | Outbound provider-lock + earner script-persona-memory |
| F13 | **Video-gen API key** (fal.ai / Replicate / Wan) | 10 min | Video AI-motion tier (current composite tier is free; AI-motion needs key) |

---

*Pending items: 30+ (T0 + 6 Telegram units + 12 goldmine queue + 8 big-sequential + ~10 P2)*
*Dead-ends / blocked: 13 documented*
*Founder-action gates: 13*
