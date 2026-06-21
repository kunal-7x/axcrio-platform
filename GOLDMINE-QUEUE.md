# GOLDMINE-QUEUE — Prioritized Gold-Mine Build Runlist
> Generated 2026-06-15 from NEXT-BIG-BUILDS.md (#26-50) + WORKFLOW_LEDGER.md + PLAYBOOK.md + MASTER_DNA_PLAN.md
> Rule: EARNER-SAFE (agent.py md5 9150fabe NEVER touched), ADDITIVE, FLAG-GATED, NOT founder-gated, NOT already built.

---

## 🟥 T0 — MUST-DO FIRST (HARD GATE, unblocks #9c telephony rotation)

### T0: scheduler_loop retry-bug fix
- **Scope:** `caller.py` scheduler_loop (~:7131) — add `if attempts >= max_retries: remove + skip` so an exhausted (3/3) retry entry can NEVER re-fire. This is what auto-dialed 6 numbers + kept the carrier 486 block alive + burned Vobiz balance. `var/retry_queue.json.PAUSED_20260614-201754.bak` is the backup.
- **Files:** `caller.py` only (famit-caller restart only).
- **caller.py touch:** YES — needs `CALLER_EDIT_LOCK` (serialize vs any other caller.py wave). Small additive guard, ~5 lines.
- **Earner safety:** famit-agent (PID 1477083) NEVER restarted; only famit-caller. Additive guard on an already-paused loop.
- **Size:** SMALL wave (1 function, 1 guard, 1 test).
- **Launch:** NEXT caller.py slot (currently free — T3 trunk mount already shipped). Launch NOW once you confirm no other caller.py wave is in flight.
- **Gate before:** telephony T5 (rotation flag-ON), any campaign resume.

---

## 🟩 CAN LAUNCH RIGHT NOW IN PARALLEL (touch NEITHER caller.py NOR the panel)

### #1 — Eval/replay harness + per-call QA score (NEXT-BIG-BUILDS #44)
- **Scope:** Offline persona-scenario runner + LLM-judge that scores every voice change (TTFT, faithfulness, language-mirror, no-announce, objection-handling). Writes scores to `design/eval-harness.md` spec already exists. Produces a gate (`eval PASS`) required before any future voice flag flip.
- **Files:** NEW `droplet_work/eval/` package (scenarios JSON + runner + judge prompt + scorer); no caller.py, no panel, no box mutation. Purely LOCAL offline tooling.
- **caller.py touch:** NO.
- **Panel touch:** NO.
- **Earner safety:** OFFLINE — reads `_inbound_ref/*.py` and prompt fixtures only. Zero box mutations. Zero restarts. Zero ring.
- **Size:** MEDIUM wave (Opus for the judge design; Sonnet for the runner script).
- **Launch:** RIGHT NOW in parallel (no locks needed).
- **Why gold-mine:** This is the highest-leverage item in the backlog. Every voice change (MLV, W3 memory, naturalness, language-lock) is currently verified by re-reading the code and a synthetic smoke. The eval harness makes every future voice change PROVABLE vs a baseline — it is the seatbelt for the entire voice-brain epic.

---

### #2 — Inbound never-silent apology guard (NEXT-BIG-BUILDS #29)
- **Scope:** In `aim_voice_agent.py` (inbound worker only), wrap the `_entrypoint_impl` top-level try/except so any uncaught exception speaks a short apology line ("Sorry, there was a technical issue — please try again") before disconnecting. Today: uncaught error = dead air (terrible UX, trust-killer).
- **Files:** `aim_voice_agent.py` only (aim-voice-agent restart only, NOT famit-agent).
- **caller.py touch:** NO.
- **Panel touch:** NO.
- **Earner safety:** INBOUND ONLY. Does not touch agent.py, caller.py, or the outbound earner. Purely additive error-handler.
- **Size:** SMALL wave (~10 lines; Sonnet).
- **Launch:** RIGHT NOW in parallel (no locks needed). Box-mutating but ONLY restarts aim-voice-agent.
- **Why gold-mine:** Prevents dead-air on any future inbound bug — earner-safety multiplier for the whole inbound epic.

---

### #3 — DPDP delete-my-data endpoint (NEXT-BIG-BUILDS #33)
- **Scope:** A new `POST /leads/{phone}/erase` route on caller.py that: purges the lead's `var/memory/<tenant>/<phone>.json` file, soft-deletes their `lead_memory` + `episodes` PG rows, logs a DPDP-erasure event to the immutable `events` audit table, and returns 204. Add a matching "Erase lead data" button in the CRM detail page (panel).
- **Files:**
  - Backend: `caller.py` (+1 route, additive). Needs `CALLER_EDIT_LOCK` (small).
  - DB: no DDL change (uses existing `lead_memory` + `events` tables).
  - Panel: `famit-panel/app/crm/` — one button + confirm modal in lead detail. Panel deploy deferred (batch with next panel deploy).
- **caller.py touch:** YES (small — 1 route). Serialize after T0.
- **Panel touch:** YES (small UI addition — deferred to next panel batch deploy).
- **Earner safety:** Additive route behind auth, never touches agent.py or voice path.
- **Size:** SMALL wave (Sonnet; BE + FE together).
- **Launch:** After T0 (needs caller.py slot). FE portion ships in next panel batch.
- **Why gold-mine:** Legal exposure item. DPDP Act 2023 is live in India — a founder selling to enterprise/SMBs who handle customer PII needs this. It is also a trust/sales signal ("we handle your data responsibly").

---

### #4 — Inbound analytics dashboard (NEXT-BIG-BUILDS #34)
- **Scope:** A new `/analytics/inbound` panel page (or extend existing `/analytics`) showing: containment rate (calls that resolved without human transfer), booking rate, hot-lead rate, sentiment distribution (from transcript), language-mix (Hindi vs English vs Hinglish), average call duration, and transfer/fallback ladder hits. All from existing `calls.json` / `lead_memory` / `episodes` tables — no new schema.
- **Files:**
  - Panel only: `famit-panel/app/analytics/` (new sub-page or section). Zero box mutation.
  - Backend: possibly 1-2 new aggregation query routes on `caller.py` (e.g. `GET /analytics/inbound-summary`). Needs `CALLER_EDIT_LOCK` if BE routes added; panel portion is panel-only.
- **caller.py touch:** OPTIONAL — if queries are added. The FE portion is panel-only and can ship standalone via a `GET /calls` + client-side aggregation first pass.
- **Panel touch:** YES — new page. Deferred to next panel batch deploy.
- **Earner safety:** Read-only analytics. Zero earner/voice path contact.
- **Size:** MEDIUM wave (Sonnet + frontend-design skill for the dashboard; Core_2 kit).
- **Launch:** FE panel portion RIGHT NOW (no caller.py lock needed for read-only queries using existing `/calls` endpoint). BE aggregation routes: after T0.
- **Why gold-mine:** The founder has no visibility into what the inbound agent is actually doing. This dashboard answers the "#1 question any customer or investor asks" — "is it working?" It also surfaces the booking rate, which is the key ROI metric for the sales proposal.

---

### #5 — Dormant-flag activation: CTX_CACHE + INBOUND_PROV_LOCK (WORKFLOW_LEDGER queued item)
- **Scope:** Both flags are BUILT, TESTED, DEPLOYED to the box, but NOT set in `/opt/famit-agent/.env`. Activating them is a pure `.env` edit + aim-voice-agent restart:
  - `CTX_CACHE=1` → enables the W2 LRU+Redis campaign-fields warm cache (0.164ms warm vs 103ms cold).
  - `INBOUND_PROV_LOCK=1` → locks the inbound agent to the proven STT/LLM/TTS provider stack (prevents accidental drift if env changes).
- **Files:** `/opt/famit-agent/.env` ONLY (no code edit, no caller.py, no panel).
- **caller.py touch:** NO.
- **Panel touch:** NO.
- **Earner safety:** aim-voice-agent restart ONLY. famit-agent (PID 1477083) NEVER restarted. Flags are built/tested/verified — activation is a one-liner.
- **Size:** TINY (5-min op). Verify with a 5-probe smoke (W2 cache: cold→warm ratio).
- **Launch:** RIGHT NOW — it is literally a 2-line `.env` edit + restart.
- **Why gold-mine:** W2 was built and verified but never activated. This is free performance (0.16ms vs 103ms for campaign context on every inbound call) and provider stability — at zero build cost. Classic "forgotten gain."

---

## 🟨 NEXT QUEUE (need caller.py slot or panel batch — launch after T0)

### #6 — Mid-call `lead_is_hot` LLM tool (NEXT-BIG-BUILDS #35)
- **Scope:** Add a `lead_is_hot` tool declaration to `aim_voice_agent.py`'s tool list. When the LLM detects strong buy-intent signals mid-conversation, it calls this tool → the backend marks `lead.hot=True` in the lead_memory PG row + emits a `lead.hot` event to the immutable audit log + triggers a Telegram hot-lead alert (pairs with the Communication wave). The tool call happens in the existing tool-dispatch loop, no new infrastructure.
- **Files:** `aim_voice_agent.py` (tool declaration + handler ~30 lines); `lead_memory` table already exists; `caller.py` needs a `POST /leads/{phone}/mark-hot` route (caller.py slot). Panel: CRM lead-list can show a 🔥 badge (FE-only, small, next panel batch).
- **caller.py touch:** YES (1 small route). Serialize after T0.
- **Earner safety:** Additive tool in inbound agent only. agent.py untouched.
- **Size:** SMALL wave (Sonnet).
- **Launch:** After T0 (caller.py slot free).

---

### #7 — Post-call workflow event emission (NEXT-BIG-BUILDS #37)
- **Scope:** At call completion (`_finalize_call` in `caller.py`), emit a `call.completed` event into the workflow DSL trigger system so that workflow templates can fire on call-end (e.g. "after a call → send WhatsApp follow-up → wait 2 days → retry"). Pairs with the existing Workflow builder (item #8, DONE).
- **Files:** `caller.py` `_finalize_call` hook + workflow event table (additive PG insert, no new table needed — reuse the existing workflow trigger mechanism).
- **caller.py touch:** YES (additive hook in `_finalize_call`). Serialize after T0.
- **Earner safety:** Additive, best-effort (`asyncio.create_task`, never `await` on the hot path). agent.py untouched.
- **Size:** SMALL wave (Sonnet).
- **Launch:** After T0 (caller.py slot free). High value because it activates the Workflow builder as a real automation engine (right now workflows run but don't react to call outcomes).

---

### #8 — LiveKit semantic turn-detector (NEXT-BIG-BUILDS #42)
- **Scope:** Add the LiveKit `turn-detector` plugin with Silero VAD to `aim_voice_agent.py`. This replaces the current silence-timeout-based endpointing with true semantic turn detection (~99.4% accuracy on Hindi; cuts false-start interruptions and dead-air gaps). Inbound only. Plugin is an additive `TurnDetector` kwarg on the existing `VoiceAssistant` constructor.
- **Files:** `aim_voice_agent.py` (additive kwarg + import); `requirements.txt` or `pyproject.toml` for the plugin package (if not already present).
- **caller.py touch:** NO.
- **Panel touch:** NO.
- **Earner safety:** Inbound only (aim-voice-agent restart). agent.py + famit-agent UNTOUCHED.
- **Size:** SMALL wave (Sonnet). Verify: a 2-scenario smoke (fast speaker, slow speaker) measuring endpointing latency before/after.
- **Launch:** Can launch after any current aim-voice-agent wave finishes (no caller.py lock needed). HIGH priority — directly fixes the call naturalness the founder cares about.

---

### #9 — Inbound voice warm-cache + pooled HTTP client (NEXT-BIG-BUILDS #47)
- **Scope:** Two micro-optimizations on `aim_voice_agent.py`:
  1. Redis hot-cache for the STT/LLM/TTS provider config (currently resolved fresh per-call from PG; a Redis `HSET` cache with 60s TTL cuts this to <1ms).
  2. Reuse a single `httpx.AsyncClient` (session-level) for all STT/LLM/TTS calls instead of creating a new client per-turn (cuts TLS handshake overhead ~20-50ms/turn for providers that support keepalive).
  These two together shave 50-150ms from inbound TTFT (first token latency).
- **Files:** `aim_voice_agent.py` only (additive; the Redis client `:6380` is already on box).
- **caller.py touch:** NO.
- **Panel touch:** NO.
- **Earner safety:** Inbound only. Additive. agent.py untouched.
- **Size:** SMALL wave (Sonnet).
- **Launch:** After any current aim-voice-agent wave finishes. No caller.py lock.

---

## 🟦 DEFERRED / NEEDS DESIGN-FIRST (P2 items — lower urgency but high value)

### #10 — Inbound recording Egress (NEXT-BIG-BUILDS #30)
- **Scope:** Outbound calls auto-egress OGG to DO Spaces and store `recording_url`. Inbound calls (aim-voice-agent) do NOT — so inbound transcripts have no paired audio. Wire LiveKit Egress for the inbound room + store the presigned `recording_url` in the `calls.json` entry for the session.
- **Files:** `aim_voice_agent.py` + `caller.py` (Egress API call on call-end). Needs `CALLER_EDIT_LOCK`.
- **caller.py touch:** YES. Serialize after T0.
- **Earner safety:** Additive, mirrors existing outbound Egress pattern. agent.py untouched.
- **Size:** MEDIUM wave. Design-first (mirror the outbound Egress wiring exactly — pull from outbound code path). Needs DO Spaces token confirmed.
- **Launch:** After T0 + after a caller.py slot is free.

### #11 — Inbound spend metering (NEXT-BIG-BUILDS #31)
- **Scope:** Today only outbound calls are metered into `wallet_accounts`. Inbound minutes, handoff events, and RAG queries are FREE-riding the wallet. Wire inbound call-end to `wallet.debit(tenant, paise_per_min * duration_s / 60)` — same `_charge_call` pattern as outbound but gated by `WALLET_ENABLED` + `INBOUND_BILLING_ENABLED` flags (both default OFF = byte-identical).
- **Files:** `caller.py` + `wallet.py` (additive). Needs `CALLER_EDIT_LOCK`.
- **caller.py touch:** YES. Serialize after T0.
- **Earner safety:** Flag-gated default-OFF. Additive. agent.py untouched.
- **Size:** SMALL wave (Sonnet).
- **Launch:** After T0. Flags stay OFF until the founder enables billing.

### #12 — ADS ENGINE dormant activation (NEXT-BIG-BUILDS #26)
- **Scope:** `ads_engine/endpoints.py` + FE `app/ads/page.tsx` already exist. `FEATURE_ADS` is OFF. Activate the propose/approve flow (no live spend — that needs Ads OAuth). The "propose an ad from a campaign" UI is buildable today.
- **Files:** `.env` flip + FE panel (already built). No new code. Panel deploy needed.
- **caller.py touch:** NO.
- **Panel touch:** YES (flag-flip exposes existing page).
- **Earner safety:** Purely additive. No live ad spend. agent.py untouched.
- **Size:** TINY (env + panel deploy).
- **Launch:** Next panel batch deploy.

---

## 🔴 NOT IN THIS QUEUE (founder-gated or too risky to parallelize now)

- **#30 warm-transfer fallback ladder (#36):** touches `aim_voice_agent.py` call-transfer logic — deferred until telephony T5 (multi-trunk) is active, otherwise fallback-to-what?
- **#38 Customer-mode sales-in inbound worker:** large new `sales_flow.py` module — needs a dedicated megaplan wave (Design first).
- **#11 Earner LLM fallback:** GATED — requires agent.py edit + founder sign-off.
- **#46 LoRA fine-tune:** GATED — after eval harness + GPU.
- **Communication W1 (Telegram):** GATED — needs founder BotFather token (2-min action, but it IS founder-gated).
- **WhatsApp residuals (#19, #50):** GATED — Meta WABA approval.
- **Vault (#10):** large wave — design is DONE but build needs a dedicated Opus wave; not parallelizable.
- **Telephony T4 FE + T5 flag-ON:** T4 (FE) = next panel batch after T0+T3 (caller.py) free; T5 = needs founder outbound ring + 140/DLT DID.

---

## 🚦 PARALLEL LAUNCH DECISION (RIGHT NOW)

These 3 items touch NEITHER caller.py NOR the panel and can start IMMEDIATELY in parallel:

| # | Item | What to launch |
|---|------|---------------|
| A | **Eval/replay harness** (#44) | Opus agent: design the scenario JSON + LLM-judge prompt spec + runner script in `droplet_work/eval/`. Offline, no box touch. |
| B | **Dormant-flag activation** (CTX_CACHE + INBOUND_PROV_LOCK) | Sonnet agent: `.env` edit + aim-voice-agent restart + 5-probe smoke. 5-minute op. |
| C | **Inbound never-silent apology guard** (#29) | Sonnet agent: `aim_voice_agent.py` top-level try/except + apology TTS line + deploy (aim-voice-agent restart only). |

After those 3 clear, in the first caller.py slot:
- **T0 scheduler retry-bug fix** (unblocks rotation + campaign resume).
- Then serialize: #6 lead_is_hot → #7 post-call event → #33 DPDP → #30 recording Egress → #31 spend metering.

---

## SUMMARY TABLE

| Priority | Item | NEXT-BIG-BUILDS # | Touches caller.py? | Touches Panel? | Launch when? |
|---|---|---|---|---|---|
| T0 | scheduler retry-bug fix | (queued in WORKFLOW_LEDGER) | YES | NO | Next caller.py slot (NOW if free) |
| 1 | Eval/replay harness | #44 | NO | NO | **RIGHT NOW** |
| 2 | Dormant-flag activation | (queued) | NO | NO | **RIGHT NOW** |
| 3 | Inbound never-silent guard | #29 | NO | NO | **RIGHT NOW** |
| 4 | DPDP delete-my-data | #33 | YES (small) | YES (small) | After T0 |
| 5 | Inbound analytics dashboard | #34 | OPTIONAL | YES | FE: RIGHT NOW; BE: after T0 |
| 6 | Mid-call `lead_is_hot` tool | #35 | YES (small) | YES (badge) | After T0 |
| 7 | Post-call workflow event | #37 | YES (hook) | NO | After T0 |
| 8 | LiveKit semantic turn-detector | #42 | NO | NO | After any aim-voice-agent wave |
| 9 | Inbound warm-cache + pooled client | #47 | NO | NO | After any aim-voice-agent wave |
| 10 | Inbound recording Egress | #30 | YES | NO | After T0, after design pass |
| 11 | Inbound spend metering | #31 | YES | NO | After T0, flags OFF |
| 12 | ADS ENGINE activation | #26 | NO | YES | Next panel batch |
