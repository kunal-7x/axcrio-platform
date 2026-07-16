# 🧭 MASTER-INDEX.md — THE single read-first orchestration index

> **This is the ONE file every session reads first.** It points at everything, holds the live wave
> state, the complete pending build queue (detailed enough to build with zero re-planning), the gated
> founder actions, the file map, and the laws. It is compaction-proof by design: nothing here is a
> one-line summary that loses the *why*. Treasure everything. Never lose a line.
>
> Last assembled: 2026-06-15 · Branch: `backend/handoff-name-clean-line` · FE work on `fe/unify-run-wavec`
> · Panel BUILD_ID `u6yKGIuhALhhzdzQcywXQ` · Earner `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5`.

---

# 🛑 0. AFTER A COMPACTION, READ `RESTORE/00-READ-FIRST.md` FIRST

The canonical restore point is now the **`RESTORE/`** folder (built 2026-06-15 to end the
repeat-mistake loop): `00-READ-FIRST.md` (current live truth + order) → `01-LEARNINGS-MASTER.md`
(~75 mistakes never to repeat — READ BEFORE ANY WORK) → `02-DONE-LIVE.md` (49 live items, don't
rebuild) → `03-PENDING-AND-TRIED.md` (queue + dead-ends) → `04-SESSION-HISTORY.md` (journey +
founder style). This MASTER-INDEX is the bird's-eye that follows.

**CURRENT TRUTH (2026-06-15, overrides older "blocked" notes below):** outbound calling RESTORED
(new DID, trunk `ST_bpGqmc9TL9Ph`); warm-transfer RESTORED (inbound; aim-voice-agent reloaded);
leads mgmt + Communication tab + Video Studio LIVE on the panel; Telegram built+live but the
conversation HALLUCINATES (grounding seed = #1 pending fix, `design/TELEGRAM-ECOSYSTEM-DIAGNOSIS.md`).
`agent.py` md5 `9150fabe` unchanged. The earlier Telegram HOLD is resolved.

---

# 1. 🟥 COMPACTION PROTOCOL — DO THIS STEP 0 (before anything else)

A session can be cut off at ANY moment by the limit, and the harness compaction summary only lives in
ONE window — the session after it loses it unless you persist it. So, the instant you resume from a
compaction:

### STEP 0 — SAVE THE HARNESS SUMMARY VERBATIM (1 Write, non-negotiable)
1. The harness injected a big summary at the top of this new context. **`Write` it VERBATIM** to
   `memory/session-summaries/<YYYY-MM-DD-HHMM>-<short-tag>.md`, with a header
   `# SESSION SUMMARY — <date> — <tag>` and a one-line "what was happening".
2. Append one line to the INDEX in `memory/session-summaries/README.md`
   (`- <date> <tag> → <file> — <hook>`).
3. This costs ~1 Write and guarantees the summary survives the NEXT compaction too (history compounds —
   nothing is ever lost across chained compactions).

### STEP 1 — READ THIS FILE (MASTER-INDEX.md) top to bottom
It is the bird's-eye. It tells you: what's running, what's done + how to verify, what to build next
(with files + earner-safety + serialization), what's gated, the file map, and the laws.

### STEP 2 — DRILL INTO THE DETAILED PLANS (only what the next wave needs)
Read-order after this file: `MASTER_DNA_PLAN.md` (full DNA/why) → `ORCHESTRATOR.md` (live wave ledger) →
`AGENT_LEARNINGS.md` (append-only mistakes — read before ANY wave) → `TONIGHT-AUTONOMOUS-BUILD.md`
(the loop + priority) → `NEXT-BIG-BUILDS.md` (canonical 1-50 backlog) → `PLAYBOOK.md` (distilled rules)
→ `WORKFLOW_LEDGER.md` (one-line-per-wave history) → the per-domain `design/*-MASTER-PLAN.md`. (See §6.)

### STEP 3 — RECONCILE TRUTH ON DISK (don't trust memory)
`git status` + `git log --oneline -10`; read the latest `memory/wave_runs/*.md` for any wave that was
mid-flight; verify the last unit actually works before building on it. **Box is the source of truth** —
`scp` pull + md5 before editing any deployed file.

### ♻️ THE FOREVER-LEARNING LOOP (compounds across all sessions)
- Every SESSION and every WORKFLOW/SUBAGENT appends its mistakes + learnings (one tight dated line:
  context — lesson) to **`AGENT_LEARNINGS.md`**; a NEW class of mistake also gets a numbered rule in
  **`PLAYBOOK.md §1`**.
- Every wave's agents READ `PLAYBOOK.md` + `AGENT_LEARNINGS.md` BEFORE starting. This is how each session
  is sharper than the last. **The future-of-the-future ultra-agent is built by never repeating a mistake.**
- **FUTURE SESSIONS: do this same thing every time.** Save the summary verbatim, update this index +
  the ledgers after every wave, never end a turn with the queue un-touched, and treasure everything —
  never lose a line.

---

# 2. 🟢 RUNNING NOW

**⚠️ CORRECTION (post-survey): `communication-telegram-build` was STILL RUNNING when this
section was assembled — its final leg ships a real Telegram message to the founder. After it
lands, the standing order is HOLD (see §0): wait for the founder to test Telegram before any
new wave. The "all clear" wording below applies only to the box being earner-stable, NOT to
"go build the queue."**

**Box status: clean and stable, earner untouched, no caller.py lock held.**

All historically-cited workflow runIds resolve to waves that are **DONE** (verified against
`WORKFLOW_LEDGER.md` + `memory/wave_runs/*`):

| Named workflow / runId | Maps to | Status | Output file | Resume command (if ever needed) |
|---|---|---|---|---|
| `communication-telegram-build [wf_b36d2bbe-067]` | `comm-omnichannel-megaplan` DESIGN | **DONE (design wave)** — plan + README written; W1 BUILD not started | `communication/COMMUNICATION-MASTER-PLAN.md` + `communication/README.md` + `communication/_RESEARCH-LOG.md` | Read `communication/README.md` → `COMMUNICATION-MASTER-PLAN.md §8` → launch W1 build. GATED on founder BotFather token. |
| `video-studio-activate-real [wf_96724c63-663]` | `video-studio-activate-real` | **DONE through render-worker** — real MP4s render (2 clips proven); REMAINING = U7-U10 hardening + Hatchet-saga durable upgrade of `enqueue` | `memory/wave_runs/video-studio-activate-real.md` | Next video unit = U7 Signal-Loop / U8 reaper-moderation. Studio is REAL+USABLE today. |
| `goldmine-quickwins [wf_5fea07b9-1c4]` | `goldmine-quickwins` | **DONE (0 box mutations)** — both targeted items found ALREADY SHIPPED + ACTIVE on box | `memory/wave_runs/goldmine-quickwins.md` | Nothing remaining. Next is GOLDMINE-QUEUE T0. |
| `handoff-realtime-fix wf_3dcb8fb6-bf3` | handoff name/clean-line | **DONE** (founder confirmed live; refinement committed `4db497f`) | ORCHESTRATOR "HANDOFF REBUILD" entry | — |
| `resilience wf_832cdc86-295` | LLM provider pool | **DONE** | `memory/brain/...` | — |

**CONCLUSION:** No wave is in flight. The next build units are fully scoped (see §4) and ready to launch.
The single most-recent caller.py edit was Telephony T3 (box md5 `44b867ea`); the next caller.py wave is
**T0 scheduler retry-bug fix** (HARD GATE).

---

# 3. ✅ DONE + LIVE (with BUILD_IDs / flags / commits + how to verify)

> Earner gate verified on every box-mutating wave: `agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5`
> UNCHANGED · famit-agent NOT restarted · `/health :8209` 200 · 0 5xx · golden 5/5 byte-identical · NO ring.

### Voice / Inbound (`aim_voice_agent.py`, box md5 `1614be09`, PID `2739156`)
- **W1 vendor-script → adaptive persona + Script Studio UI** — `VENDOR_SCRIPT_INJECT=1` (systemd drop-in,
  inbound only). Golden 5/5. Commits `29a2f1cc`/`a2c5b053`/`f169d6e1`. Script Studio BUILD_ID
  `Ykm_1fVt267VDkPib8uVg`. *Verify:* `/campaigns/{cid}/prompt-preview` adopts pasted vendor greeting.
- **P0-LEAK** — cross-tenant memory/WA leak CLOSED. `memory.py:_path_for(phone,tenant_id)` →
  `{tenant}/{phone}.json`; load-bearing check `memory.py:110-113`. Unknown WA → `_unrouted`. Commit
  `4db497f`. *Verify:* tenant A cannot read tenant B's `{phone}.json`.
- **MLV — Multilingual Adaptive Voice** — ADAPTIVE MIRROR rule + language-neutral greeting + FINAL
  LANGUAGE LOCK. 5/5 live-shape smoke PASS on real Groq llama-4-scout.
- **Voice-core-surgery — Sarvam Bulbul v3** — `.env` `SARVAM_TTS_MODEL=bulbul:v3` +
  `SARVAM_TTS_SPEAKER=priya` (fixes v2 garbling "BHK"→"उसाई"). SCRIPT RULE (Devanagari+Latin) KEPT.
  Backup `.env.SURGbak.20260614-154923`.
- **Inbound voice naturalness** — SCRIPT RULE (Devanagari Hindi + Latin loan-words). Commit `69374eb`.
  TTS clips show SIGNIFICANT improvement. *FINAL acceptance = founder's real inbound call.*
- **W2 context cache** — `CTX_CACHE=1` (drop-in). Warm 0.205ms vs 57ms cold (277×). VERIFIED ACTIVE in
  running proc env. `ai_manager/voice_tools.py` wired to `context_store.get_campaign_context`.
- **W3 multi-channel memory** — `lead_memory`/`lead_episodes` FORCE-RLS tables + durable PG-outbox
  extraction. State `design/W3b-EXTRACTION-STATE.md`.
- **W4 memory read side** — `LEAD_MEMORY_PG=1`, retrieval into inbound + CRM Memory tab. 10/10 verify.
  State `design/W4-MEMORY-READ-STATE.md`.
- **Never-silent apology guard** — ALREADY SHIPPED in box golden `aim_voice_agent.py:2127-2147` + `:2508`.
  Verified, not rebuilt.
- **`INBOUND_PROV_LOCK=1`** (drop-in) — routes lean/standard to Sarvam Bulbul v3/priya, premium to EL.

### RAG (FTS-only, 120 chunks / 41 `_global` sources, `RAG_INJECT_ENABLED=1`)
- **W0 kill-switch** (md5 `8335d4ba`, flag=1, 3 flag-gate proofs PASS), **W1 retrieval hardening**
  (`dense=False`, `_global` UNION under RLS, `kb_query_log` FORCE-RLS, 8/8 probes), **W2 telecaller corpus**
  (120 chunks/41 sources seeded, commits `ff44770`/`41fde4a`/`8a62fde`), **W3 KB-management backend**
  (`GET /kb/sources`, `POST /kb/upload`, `POST /kb/test-retrieve`, `GET /kb/gaps`, commit `a91d049`),
  **W7 Knowledge UI** `/knowledge` (BUILD_ID `YV9obkLRRD0U5oX-CPOCH`). Grounding LIVE at 3 sites
  (connect-prefetch, `pick_campaign`, `lookup`), FTS 6-12ms.

### Backend (`caller.py`, box md5 `44b867ea` post-T3, famit-caller `:8209`)
- **RUN-PLATFORM A+B+C** — A: env billing (`USD_INR=95.2`, `EL_RATE=4.76`, Sarvam v2/v3 split,
  `INBOUND_PROV_LOCK`, funnels mount; commits `9e18231`/`ab6777c`). B: preview fix (real cause
  `Content-Type: text/plain` → FORCE `audio/mpeg`). C: 4-step Run stepper + cost-meter + provider-lock
  banner + exclude-called toggle (commit `fa99acb`). BUILD_ID `TU16Mn1DcJVmxnxr2GVyL`.
- **Provider Registry W1-W5 + W4 LIVE** — `PROVIDER_REGISTRY_ENABLED=1`. 3 FORCE-RLS tables, AAD
  AES-256-GCM creds, SSRF guard, PIN-step-up reveal (single-use jti). 6/6 live verify PASS. BUG fixed:
  `schema.py` UUID stringify. W5 `REGISTRY_FOR_VIDEO` strangler (commit `a71b87a`, flag OFF).
- **Telephony T1+T2+T3 (flag OFF dormant)** — T1 DDL: 3 FORCE-RLS tables (`sip_trunks`/
  `sip_trunk_credentials`/`sip_trunk_health_log`), `is_campaign_eligible` GENERATED column (B1 gate),
  Vobiz `ST_fmtVmNJmpzKa` seeded as UN-DELETABLE `_global` row (commit `f0efa6c`). T2 `trunk_registry/`
  pkg, 31/31 offline PASS (commit `46301d2`). T3 caller.py mount, 16 routes, 0-del/45-add
  (`ef9ae696→44b867ea`), `/trunk-registry*` → 404 flag-OFF. Backup `caller.py.T3bak.20260615-004201`.
- **Video Studio LIVE + USABLE** — `FEATURE_VIDEO_STUDIO=1` + `FEATURE_VIDEO_COMPOSE=1` +
  `VIDEO_PROVIDER=compose` + `FEATURE_VIDEO_LIBRARY=1`. ffmpeg 6.1.1 on box. compose_worker.py deployed;
  **2 real MP4s rendered** (Codename Joy 3.0 12s, DLF The Crest 10s; ffprobe h264 1080x1920 + aac) in
  library with presigned URLs. Backup `.env.VIDACTbak.20260615-010535`. Commit `ef95422` (W7+W8).
  *Verify:* `panel.famit.in/creative/video` = 200 real studio (not DormantCard).
- **AIM Access + PIN** — `/ai-manager/numbers` CRUD + `POST /firewall/pin/change`. BUILD_ID `sTCWP4Jj…`.
- **Workflow/Funnel execution** — human labels, 4 templates, `POST /funnels/{id}/run` via `_mint_run_token`
  (token-derived). Verified 200 + run_id + NO ring. BUILD_ID `A7YHO-5a5p7ZcKqSUrKOo`.
- **Foundation Control Layer** — LIVE+ENFORCING since 2026-06-11. 18/18 T1-T18 PASS. `CONTROL_ENABLED=1`.
  HIDE→404, LOCK→402, `FamitCall2026`→403. Backup `.env.CLbak.20260610-195647`.
- **ACID Wallet + Firewall** — 4 PG tables (INTEGER paise), 24-concurrent no-oversell proven.
  `FIREWALL_ENABLED=true`. (`wallet.reserve`/`settle` exist; `wallet.debit()` does NOT.)
- **9 dormant modules** (booking/payments/support/forms/funnels/workflow/ads/media/lifecycle) — mounted,
  flag-OFF, resting byte-identical. Security holes (X-Tenant-Id header, body-tenant) refactored to
  token-deriving `build_router`.
- **WhatsApp B1/B2/C2** — real wamid proven. `FEATURE_WHATSAPP=1`. AI template builder.
- **Recordings (REC)** — outbound auto-egress OGG → DO Spaces + presigned, inbound finalize-on-read,
  unified `/api/calls/{room}/transcript`, CRM player, playable HEAD-gate, 90-day retention.
- **LLM provider pool** — `llm_router/provider_pool.py`, 9 Groq keys, least-used pick, per-key 429
  cooldown, hot-reload. Groq → SambaNova → OpenRouter-free FallbackAdapter.
- **Handoff / warm-transfer** — same-room `create_sip_participant` bridge, `session.aclose()`, names the
  person, no AI-disclosure. Founder confirmed live.

### Panel / FE (FORTRESS `143.110.247.249`, BUILD_ID `u6yKGIuhALhhzdzQcywXQ`)
- **Ship UI + Telephony T3** (2026-06-15) — Integrations UI (`f3d9bd4`) + Video Studio FE (TierTabs/
  VideoCreatePanel/BatchProgress/Images↔Videos toggle, `<video>` AssetMedia, commit `2d26c98`). tsc fix:
  `IntegrationsBody` → `_body.tsx` (commit `2c299c8`). Build 58/58. Edge 8/8 200: /integrations,
  /super-admin/integrations, /creative/video, /run, /crm, /ai-manager, /workflows, /knowledge.
- **Performance overhaul (6 units)** — pagination, react-query cache, virtualization, code-split, gzip
  90%/10× (`/api/*` 27425B→2746B), immutable static cache, transcript L/R fix. BUILD_ID
  `p6hSTJX9R46-NQdLf8Daw`. Commits `dfb663f`/`40caf3c`/`d42d130`/`7068bd7`/`d48ed46`/`c030ee4`.
- **FIXES wave** — asset-detail presigned preview (flatten `{asset,versions}` envelope) + CRM transcript
  chat-view (AI-left/customer-right). BUILD_ID `tuuIjqN7fCf_iEL-obLon`. Commits `d9daa86`/`6940742`.
- **AIM sessions page** — `app/ai-manager/sessions/page.tsx` list + TranscriptModal. Commit `73054f9`.

### Infra / Platform
- **FORTRESS 3-box egress-locked topology** (see §6) + Cloudflare Full Strict + P0 secrets gate
  (gitleaks v8 + pre-commit hook + CI `secrets.yml`).
- **Hatchet** deployed on hatchet box (hello-world durable proven, NOT in request path). **Logto** OIDC
  deployed + seeded (NOT wired into caller.py).
- **Communication megaplan** design DONE. **Growth OS Phase-0** (25 frozen schemas, hash-chain ledger,
  in-memory demo). **Eval harness core** (offline, baseline frozen). **Sales proposal** (interactive HTML,
  3-tier pricing, ROI calc). **CRM core + Business Brain** (unified person spine).

---

# 4. 🏗️ COMPLETE PENDING BUILD QUEUE (build with zero re-planning)

> Each item: WHAT · FILES · caller.py-touch · EARNER-SAFETY · SIZE/MODEL · LAUNCH-WHEN.
> Serialization law: only ONE of {RAG, Vault, Registry, Video, Telephony, Communication, any new module}
> edits `caller.py` at a time — claim `CALLER_EDIT_LOCK.md` before touching. The next caller.py wave is T0.

## 🟥 T0 — HARD GATE (must be the next caller.py wave)
**T0: `scheduler_loop` retry-bug fix**
- WHAT: `caller.py scheduler_loop` (~:7131) — add `if attempts >= max_retries: remove + skip` so an
  exhausted (3/3) retry entry can NEVER re-fire. This is the bug that auto-dialed 6 numbers, kept the
  carrier 486 block alive, and burned Vobiz balance. Backup `var/retry_queue.json.PAUSED_20260614-201754.bak`.
- FILES: `caller.py` only (~5 lines). caller.py-touch: YES (claim CALLER_EDIT_LOCK). EARNER: famit-caller
  restart only; agent.py NEVER touched; additive guard on an already-paused loop. SIZE: SMALL (Sonnet).
- LAUNCH: NOW (caller.py slot is free). GATE before: telephony T5 rotation + any campaign resume.

## 🟩 CAN LAUNCH RIGHT NOW IN PARALLEL (touch NEITHER caller.py NOR panel)
**1. Eval/replay harness (#44) — HIGHEST LEVERAGE**
- WHAT: offline persona-scenario runner + pinned-separate-model LLM-judge (temp 0, NOT the candidate).
  5 checks: TTFT p95 BOX-ONLY hard gate, guard-violations zero-tolerance, language/monologue/judge
  no-regress vs frozen baseline (`llama-4-scout`, p95 1332ms). Output: a gate (`eval PASS`) required
  before any future voice flag flip. Spec `design/eval-harness.md` + `design/RAG-EVAL-SPEC.md` exist.
- FILES: NEW `droplet_work/eval/` package. caller.py: NO. EARNER: offline, reads `_inbound_ref/*.py` +
  fixtures only; zero box mutation/restart/ring. SIZE: MEDIUM (Opus for judge design, Sonnet for runner).
- LAUNCH: RIGHT NOW. (Core already built offline; PENDING = box re-run with `--freeze-baseline` +
  `selftest_bad_model` to exercise the latency half — the highest-leverage safety item.)

**2. LiveKit semantic turn-detector (#42)**
- WHAT: add `turn-detector` plugin (Silero VAD / Qwen2.5-0.5B INT8, ~99.4% Hindi) as an additive
  `TurnDetector` kwarg on the existing `VoiceAssistant`. Replaces silence-timeout endpointing.
- FILES: `aim_voice_agent.py` + `requirements.txt`. caller.py: NO. EARNER: inbound only (aim-voice-agent
  restart). SIZE: SMALL (Sonnet). Spec `design/voice-quickwins.md`. LAUNCH: after any aim-voice-agent wave.

**3. Inbound warm-cache + pooled HTTP (#47)**
- WHAT: Redis hot-cache (60s TTL) for STT/LLM/TTS provider config (<1ms vs PG round-trip) + single
  session-level `httpx.AsyncClient` (cuts TLS handshake ~20-50ms/turn). Shaves 50-150ms inbound TTFT.
- FILES: `aim_voice_agent.py` only (Redis `:6380` already on box). caller.py: NO. EARNER: inbound only.
  SIZE: SMALL (Sonnet). LAUNCH: after any aim-voice-agent wave.

**4. Telephony T4 FE (`app/telephony/page.tsx`) — panel-only**
- WHAT: Core_2 port — trunk cards (health dot + concurrency gauge + DID-budget bars + compliance badge +
  quarantine banner) + 3-step Add-trunk wizard ending in a FOUNDER-PLACED single test call (the ONLY
  non-campaign originate, never auto) + inbound-routing + spam-reputation panels + per-DID kill switch.
- FILES: panel only. caller.py: NO. EARNER: FE-only, no box touch. SIZE: MEDIUM (Sonnet + frontend-design).
  LAUNCH: next panel batch (T3 done ✅).

**5. Inbound analytics dashboard FE (#34) — panel-only first pass**
- WHAT: `/analytics/inbound` — containment rate, booking rate, hot-lead rate, sentiment, language-mix,
  avg duration, transfer hits. FE-first pass = client-side aggregation over existing `/calls`.
- FILES: panel only first pass; BE aggregation routes after T0. EARNER: read-only. SIZE: MEDIUM
  (Sonnet + frontend-design). LAUNCH: FE now; BE routes after T0.

**6. ADS ENGINE dormant activation (#26) — env + panel**
- WHAT: `FEATURE_ADS=1` flip exposes existing `ads_engine/endpoints.py` + `app/ads/page.tsx`
  (propose/approve flow, NO live spend — that needs Ads OAuth). caller.py: NO. SIZE: TINY. LAUNCH: next
  panel batch.

## 🟨 AFTER T0 (caller.py slots — serialize in this order)
**7. DPDP delete-my-data (#33)** — `POST /leads/{phone}/erase`: purge `var/memory/{tenant}/{phone}.json`
+ soft-delete `lead_memory`/`episodes` rows + DPDP-erasure event to immutable `events` + return 204. CRM
"Erase lead data" button. FILES: `caller.py` (+1 route) + CRM FE. EARNER: additive auth'd route. SIZE:
SMALL. *Legal exposure — India DPDP Act 2023.*

**8. Mid-call `lead_is_hot` tool (#35)** — tool declaration in `aim_voice_agent.py` (~30 lines) + `POST
/leads/{phone}/mark-hot` (caller.py) + `lead.hot` event + Telegram hot-lead alert (pairs with Comm wave)
+ CRM 🔥 badge. EARNER: additive inbound tool; agent.py untouched. SIZE: SMALL.

**9. Post-call workflow event (#37)** — emit `call.completed` into the workflow DSL from `_finalize_call`
as `asyncio.create_task` (NEVER `await` on the hot path — `_finalize_call` is awaited in the dial loop).
Activates the Workflow builder as a real automation engine. FILES: `caller.py` hook. SIZE: SMALL.

**10. Inbound recording Egress (#30)** — mirror outbound Egress for inbound rooms → presigned
`recording_url` in `calls.json`. FILES: `aim_voice_agent.py` + `caller.py`. EARNER: mirrors outbound
pattern. SIZE: MEDIUM (design-first: copy the outbound Egress path exactly).

**11. Inbound spend metering (#31)** — wire inbound call-end to `wallet.reserve→settle` (same `_charge_call`
pattern). Flags `WALLET_ENABLED` + `INBOUND_BILLING_ENABLED` default OFF (byte-identical resting). FILES:
`caller.py` + `wallet.py`. SIZE: SMALL. Flags stay OFF until founder enables billing.

## 🟦 P1 — BIG SEQUENTIAL BUILDS
**12. Communication Wave 1 — Telegram** (`communication/COMMUNICATION-MASTER-PLAN.md §8 W1`) — NEW
`droplet_work/comm/` package + 3 tables (`comm_sessions`/`comm_send_log`/`comm_consent_log`) + Telegram
adapter + founder hot-lead alert + post-call auto-summary (`asyncio.create_task` + snapshot, NEVER await)
+ channel setup UI (paste BotFather token + Test + founder chat_id). Channel registry = the LIVE
provider_registry (1 cred row + 1 adapter = a channel, zero new crypto). 6 security probes gate ship
(T-VAULT/T-WEBHOOK/T-INJECT/T-LEAK/T-DEEPLINK/T-GATE). `COMM_ENABLED` default OFF (flags OFF → `/comm/*`
404). caller.py-touch: YES (2 small `create_task` insertions + mount — LAST step, after pkg built/tested
offline). EARNER: agent.py never imported; per-channel timeout. BE Opus, FE Sonnet. **GATED on founder
BotFather token (2-min, free).**

**13. Vault (V0-V8)** (`design/VAULT-MASTER-PLAN.md`, 11 red-team corrections folded) — PIN-gated
per-vendor AES-256-GCM AAD-bound envelope, 5 FORCE-RLS tables incl. append-only access log. Key facts:
PIN = salted sha256 NOT Argon2id; `vault_used_jti` single-use; AAD mandatory; KEK-0 absent → 503
fail-closed; read-seam `vault.get_secret(...)` is the #1 cross-product gap. FILES: NEW `droplet_work/vault/`
+ `db/ddl_vault.sql` + caller.py mount. caller.py-touch: YES (serialize). EARNER: all flags default OFF;
agent.py never imported. SIZE: LARGE (Opus BE, Sonnet FE).

**14. Communication Wave 2 — LLM brain + inbound webhook** (`§8 W2`) — COPY `_wa_reply_text` →
`comm/brain.py` channel-neutral (WA byte-identical); Telegram webhook `POST /comm/webhook/telegram/{tenant}`
(fail-CLOSED, secret-bound-to-path-tenant); signed single-use deep-link consent. caller.py-touch: YES.

**15. W4 RAG grounding cache + collateral ingest** (`RAG-MASTER-PLAN W4`) — `kb/grounding_cache.py` keyed
`(tenant,campaign,stage,channel,kb_version)` + campaign-save ingest + PII-scrub + versioning + quota +
meter the ~350-tok prompt-tax. FILES: `aim_voice_agent.py` + caller.py campaign-save hook + new module.
caller.py-touch: YES.

**16. Voice-brain W4 Hinglish v2 register + semantic turn-detector** (overlaps #2) — Hinglish v2 few-shots
in a NEW render path (never mutate `_flow_block`). FILES: `aim_voice_agent.py`. caller.py: NO.

**17. Telephony T5 strangler (flag-ON)** — strangler cut behind `TRUNK_REGISTRY_ENABLED`; real founder
outbound-ring smoke before+after. GATE: T0 done + T4 FE done + founder 140/DLT DID or Plivo 2nd trunk +
the 4 red-team corrections (B1/B-rel/C-rel/D) already folded in T1-T3. caller.py-touch: YES.

**18. Run-Campaign audience-builder UX** — composable filters (temperature hot≥70/warm/cold, by-upload,
manual), `lead_ids` explicit list, Excel `.xlsx` (`openpyxl`), `batch_id`, `GET /leads/batches`. PORT
Core_2. No dial-loop change.

**19. Communication W3 (Email)** (`§8 W3`) — Resend adapter + SPF/DKIM/DMARC wizard + List-Unsubscribe +
cost-router + all cost guards + multi-step template builder. **GATED on Resend key.**

## 🟪 P2 — SPEC'D / LOWER URGENCY
- **Cost-meter re-tune** — `tts_chars_per_min` 900→~330-360 in `llm_router/tiers.py` (pure data edit; meter
  is ~2.5× inflated).
- **Video Studio hardening U7-U10** — Signal-Loop lineage, reaper/moderation/lifecycle/alerts, BYO-key
  Vault seam/music/multilingual, durable Hatchet-saga upgrade of `enqueue` (swap `fork` for a Hatchet step),
  full 4-rung ABR.
- **Sarvam pronunciation dictionary** + **EL premium-tier Hindi voice** (Raju `zT03pEAEi0VHKciJODfn` +
  remove `AIM_TTS_LANG=hi`) — P1 latent, applies to premium-tier callers only.
- **6 Creative sub-products** (Brochure/Catalog, Creative-Batch, Ads Engine, Landing-Page, 3D, A/B-Lab —
  specs in `design/creative-*.md`).
- **Customer-mode sales-in inbound worker** (`design/CUSTOMER-MODE-BUILD-STATE.md`) — large new
  `sales_flow.py`, separate `SALES_INBOUND_ENABLED` worker; needs a dedicated megaplan wave.
- **Control-Layer C10** (AI-Copilot gate, probe T18) + **C12** (CI registry-drift guard).
- **AIM dedicated service** (39-unit plan) — GATED on DO droplet limit raise.
- **Hatchet caller.py cutover** (gated on P1) + **Logto caller.py wiring** (gated on DNS).
- **Communication W4-W6** (unified inbox + book_slot; SMS DLT-gated; CAPI signal closure = the moat).
- **Growth OS** — fix `@growth-os/events` codegen build first (`<Name>Payload` suffix + duplicate
  interfaces), then boot 6-container stack (GATED on DO droplet raise).
- **WhatsApp residuals** — WB-2 `status=partial` fallback (P0 FE-only `app/whatsapp/_lib/waapi.ts`),
  WB-3 banner via `header_url`, WB-4 Submit-to-Meta (GATED Meta).
- **LoRA/QLoRA fine-tune** (#46) — DEFERRED after eval harness + self-host latency decision + GPU.

---

# 5. ⛔ GATED + FOUNDER ACTIONS (do NOT build the blocked half)

| # | Founder action | Unblocks |
|---|---|---|
| 1 | **Vobiz support: clear/rotate DID `+918071583488`** (carrier-spam-blocked since 2026-06-13 ~12:51 UTC; 486/480/603 immediate). Rest DID; NO test calls until cleared. | All outbound campaign runs, telephony T5, OB-PROV ring-gate, earner-LLM-fallback |
| 2 | **BotFather `/newbot` → copy token → tap Start** (2 min, free, no verification) | Communication W1 (Telegram founder alert) |
| 3 | **Meta WhatsApp: payment 141006 + business verify + subscribe `messages` webhook + 1 approved template** (`FOUNDER-META-WHATSAPP-FIX.md`) | WA delivery, `hot_lead_alert`, Submit-to-Meta, cold sends |
| 4 | **ModelScope ↔ Alibaba Cloud bind** (`FOUNDER-MODELSCOPE-BIND.md`) | Image generation (401s) |
| 5 | **140-series DID + DLT Principal-Entity registration** (~1-2wk, Airtel Business/Tata Tele) + **Plivo 2nd trunk** (₹250/DID + ₹0.60/min) | Legal India-scale outbound; Telephony T5 rotation/failover |
| 6 | **OB-PROV / W-OB sign-off** (agent.py edit + DID un-rested + real ring before+after) | Outbound provider-lock + earner script-persona-memory; closes P0-LEAK outbound side |
| 7 | **FE-box root `143.110.247.249`** — nginx `/api/assets/` proxy repoint → `10.122.0.4:8310` | Clickable Creative Studio browser demo + Logto DNS nginx |
| 8 | **DO droplet limit raise (3/3 FULL)** | AIM dedicated service, Growth OS 6-container stack, any new box |
| 9 | **Resend key** (W3) / **MSG91 + DLT** (W5, 5-10 days) | Communication Email / SMS |
| 10 | **GitHub private repo creation + push** | Remote backup (git init'd locally, not pushed) |
| 11 | **Razorpay keys** (ON-HOLD) / **Ads OAuth** / **SambaNova Developer tier** / **Cloudflare token re-scope** / **Video-gen API key** (fal.ai/Replicate/Wan) | Payments / Ads spend / real LLM fallback / Logto DNS / Video AI-motion tier |

---

# 6. 🗺️ FILE MAP + READ-ORDER

### READ-ORDER (post-compaction, after Step 0)
1. **`MASTER-INDEX.md`** (this file) — read-first orchestration index
2. `MASTER_DNA_PLAN.md` — full DNA (vision · every subsystem with why-born · done · pending · gated · laws)
3. `ORCHESTRATOR.md` — live wave ledger (newest-on-top, every wave's PLAN+OUTPUT+STATUS)
4. `AGENT_LEARNINGS.md` — append-only mistakes (read before ANY wave)
5. `TONIGHT-AUTONOMOUS-BUILD.md` — the night-loop + priority order
6. `NEXT-BIG-BUILDS.md` — canonical 1-50 backlog (grind top-down)
7. `PLAYBOOK.md` — distilled "mistake → rule that prevents it"
8. `WORKFLOW_LEDGER.md` — one-line-per-wave durable history (newest on top)
9. `GOLDMINE-QUEUE.md` — prioritized goldmine quick-wins (T0 → parallel items)
10. Per domain: `design/VOICE-BRAIN-MASTER-PLAN.md` · `design/RUN-PLATFORM-MASTER-PLAN.md` ·
    `design/RAG-MASTER-PLAN.md` · `design/VIDEO-STUDIO-MASTER-PLAN.md` · `design/VAULT-MASTER-PLAN.md` ·
    `design/PROVIDER-FRAMEWORK-PLAN.md` · `design/TELEPHONY-INDEPENDENCE-PLAN.md` ·
    `design/RECOVERY-STATE.md` (authoritative source map) · `communication/README.md` +
    `communication/COMMUNICATION-MASTER-PLAN.md` · the relevant `memory/wave_runs/*.md`.

### CANONICAL SOURCE MAP (edit from these; box is truth — pull + md5 before editing)
| File | Start from | Box md5 | Notes |
|---|---|---|---|
| `aim_voice_agent.py` | `droplet_work/aim_voice_agent.LIVEBOX.py` | `1614be09` | ALWAYS start edits here (inbound) |
| `prompt.py` | `droplet_work/prompt.LIVEBOX.py` | `fb87ea56` | SHARED inbound+outbound — golden 5/5 byte-identical gate |
| `agent.py` (EARNER) | BOX ONLY `/opt/famit-agent/agent.py` | `9150fabe` | NEVER deploy from local; read-only mirror `_inbound_ref/agent.REFERENCE.py` |
| `caller.py` | `droplet_work/caller.py` | `44b867ea` (post-T3) | Pull box before edit; anchor-string inserts (3 disk variants exist) |
| `memory.py` | `droplet_work/memory.py` | `cb70e1d7` | P0-LEAK deployed; leak check `:110-113` |
| `firewall.py` | `droplet_work/firewall.py` | `b77c2cbe` (post-W4 reveal scope) | |
| `context_store.py` | `droplet_work/context_store.py` | `245d864f` | |
| `kb/` (`__init__.py`/`core.py`/`schema.sql`) | BOX ONLY | `f6ec3720`/`3922266f`/`fabd3803` | Pull before editing |

STALE / DANGER — never deploy: `_inbound_ref/aim_voice_agent.LIVE.py` (`4bbd0956`), `.NEW.py`, `.VERIFY.py`.

### INFRA — three-box FORTRESS (DO blr1, VPC 10.122.0.0/20)
- **famit-panel-2** `143.110.247.249` / `10.122.0.2` — FORTRESS FE. Cloudflare Full Strict. nginx
  `/api/assets/`→`10.122.0.4:8310`, `/api/`→`:8209`, `/`→`127.0.0.1:3001`. BUILD locally (box 2GB OOMs).
- **famit-livekit** `168.144.153.145` / `10.122.0.4` — earner box. famit-caller `:8209`, famit-agent
  (SACRED), famit-aiasset `:8310`, PG 16, Docker livekit-server/sip/redis/egress, ffmpeg 6.1.1.
  **capsy-venv trap:** running service uses `/opt/capsy-agent/.venv` (NOT `/opt/famit-agent/.venv`).
- **famit-hatchet** `68.183.94.38` / `10.122.0.3` — Hatchet-lite + Logto, localhost-bound, NOT in request
  path. **DO droplet limit 3/3 FULL.**
- SSH key: `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`.

### LIVE FLAGS ON BOX (load-bearing)
`.env`: `CONTROL_ENABLED=1`, `FIREWALL_ENABLED=true`, `AIM_ENABLED=1`, `AIM_RECORDING_ENABLED=1`,
`RAG_INJECT_ENABLED=1`, `LEAD_MEMORY_PG=1`, `STORE_MODES=dual`, `MEMORY_TENANT_SCOPED=1`,
`PROVIDER_REGISTRY_ENABLED=1`, `FEATURE_VIDEO_STUDIO=1`, `FEATURE_VIDEO_COMPOSE=1`, `VIDEO_PROVIDER=compose`,
`FEATURE_VIDEO_LIBRARY=1` (aiasset), `AIASSET_LOOPBACK_BASE=http://10.122.0.4:8310`, `AIASSET_SERVICE_TOKEN=set`,
`SARVAM_TTS_MODEL=bulbul:v3`, `SARVAM_TTS_SPEAKER=priya`, all `FEATURE_*` modules `=1`. NOT SET (OFF):
`TRUNK_REGISTRY_ENABLED`, `WALLET_ENABLED`, `INBOUND_BILLING_ENABLED`, `EMBED_API_KEY`, `REGISTRY_FOR_VIDEO`,
`COMM_ENABLED`, `FEATURE_ADS`.
Systemd drop-in `aim-voice-agent.service.d/vendor-script.conf` (NOT .env — confirm via `/proc/2739156/environ`):
`VENDOR_SCRIPT_INJECT=1`, `CTX_CACHE=1`, `INBOUND_PROV_LOCK=1`.

---

# 7. 📏 STANDING RULES + TOP LEARNINGS

### STANDING LAWS (never violate)
1. **NEVER edit/restart `agent.py`** (md5 `9150fabe`) without founder sign-off + a real ring before+after.
   Every new capability = additive + isolated + earner-regression-gated. Inbound work stays in
   `aim_voice_agent.py` / `caller.py`. Restart only famit-caller / aim-voice-agent / famit-panel.
2. **NO outbound test calls** — DID is carrier-blocked; a real ring is the FOUNDER's job. A real ring =
   `inviteToRingingMs>0` / SIP 180 / 200 in livekit-sip — NOT the agent-join line, NOT a 486 "Busy".
3. **Golden byte-diff `verify_golden.py` 5/5 exit 0** BEFORE any caller.py/prompt.py deploy. (agent.py md5
   unchanged is a FALSE safety signal alone — the earner re-renders through SHARED `prompt.py`.)
4. **Every backend capability ships with a FRONTEND control UI** (Core_2 kit, never from scratch).
5. **A green report ≠ a working product** — only the founder's real call/WA/click is truth.
6. **Never burn PAID credits** (free providers first; 1 paid test max). OpenRouter $ is real money.
7. **One box-mutating wave at a time.** Claim `CALLER_EDIT_LOCK.md` before any caller.py edit; only ONE
   wave edits caller.py at a time. Read-only research may parallelize.
8. **Tenant ALWAYS from the auth token, never the body.** Money = INTEGER PAISE, never float. Fail-closed
   everywhere (unknown=HIDDEN, missing-creds=not_configured, KEK-0-absent=503).
9. **429 = quota (add capacity); 400 = code bug (fix/revert).** Never revert code for a 429.
10. **`_finalize_call` is AWAITED in the dial loop** — every post-call send MUST be `asyncio.create_task`
    + synchronous payload snapshot + timeout, NEVER `await`.
11. **FORTRESS deploy recipe:** build LOCALLY → backup-first → md5-gate scp before extract → atomic `.next`
    swap → chown deployuser → restart famit-panel ONLY → verify 200 + new BUILD_ID on loopback + edge.
    NEVER deploy a lone FE branch (silently reverts others) — unify onto `fe/unify-run-wavec` first.
12. **Box is source of truth; the repo can be stale.** Always `scp` pull + md5 before editing deployed
    files; start from the `.LIVEBOX` golden. Anchor-string inserts in caller.py, never LIVEBOX line numbers.
13. **The capsy-venv trap:** the running service uses `/opt/capsy-agent/.venv`, NOT `/opt/famit-agent/.venv`.
14. **Compaction-proof:** update this index + ORCHESTRATOR + AGENT_LEARNINGS + ledgers after every wave;
    never end a turn with zero waves running while the queue remains.

### TOP LEARNINGS (blood-written — never repeat)
- **486 Busy ≠ it rang.** A 486 with only `inviteToTryingMs` = carrier-rejected pre-ring.
- **Groq TPD exhaustion** ("thoda sa system slow hua hai") — 6 keys share ONE org's 500k/day pool; AIM
  test-burn starves the live earner. FallbackAdapter shipped; give the earner its own org (gated).
- **RAG was LIVE+UNGATED** before W0 retro-gated it (`grep RAG_INJECT_ENABLED` = 0 hits). Trace every flag
  end-to-end (UI→API→toggle) before assuming.
- **A seam can point at a module that doesn't exist** (compose_worker.py was wired but absent). Grep the
  tree for the target module's DEFINITION before claiming a path works.
- **ADMIN_ID default poisoned the admin tenant** for unknown inbound WA → now `_unrouted`, never ADMIN_ID.
- **Sarvam Bulbul v2 garbles romanized Hindi** — always Devanagari for Hindi words; v3+priya now live.
- **scheduler_loop retry bug (T0)** — exhausted retries re-fire → auto-dialed 6 numbers → deepened the
  carrier flag. Queue PAUSED at `var/retry_queue.json.PAUSED_20260614-201754.bak`. Fix is T0 before resume.
- **Presign DO Spaces URLs + HEAD-verify non-empty before presigning** — private URL → 403 blank is a
  recurring bug class (asset preview, recordings).
- **P0-LEAK was a live cross-tenant security hole** — load-bearing fix `memory.py:110-113`.
