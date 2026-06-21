# AUDIT — THE CONNECTED LIFECYCLE (production-readiness, end-to-end)

> **READ-ONLY audit, 2026-06-12.** Maps the ONE pipeline the founder is building as a single connected
> system — outbound AI call → per-person memory/context → WhatsApp follow-up (template → LLM conversation) →
> inbound AI with FULL history → hot warm-transfer to human + hot-lead WhatsApp to the team — and rates every
> stage with **where the code is, what truly works, what is only front-end, what is dormant.** Ground-truth is
> the live box `famit@168.144.153.145` (read-only) cross-checked against the V2 master plan and the six
> grounded explores. **The emphasis is the CONNECTIONS — does context actually flow call → WhatsApp → inbound?**
>
> **#1 rule (unchanged, absolute):** the live OUTBOUND earner (`agent.py` / `capsy` / `famit-agent.service` /
> `:8090` / trunks `ST_fmtVmNJmpzKa`+`ST_LH8ighJJtHSi`) was just restored after an infra mistake. **Every
> future build is ADDITIVE + ISOLATED and NEVER touches it.** Outbound regression-gate `G` (famit-agent active
> + one real test call) runs before and after every step.
>
> Rating legend: **BUILT** (live, works) · **PARTIAL** (built but un-wired / outbound-only / incomplete) ·
> **NOT-BUILT** (greenfield) · **NOT-TESTED** (code exists, never proven E2E) · **DORMANT** (gated off by a
> flag or a missing cred, code present).

---

## 0. LIVE-BOX VERIFICATION (what I confirmed this session, read-only)

| Probe | Result |
|---|---|
| Services running | `famit-agent` ✅ active (outbound earner), `aim-voice-agent` ✅ active (inbound `manager`), `famit-caller`/`famit-bridge`/`famit-aiasset`/`llm-router` ✅ active |
| **WhatsApp creds** | `META_WA_PHONE_NUMBER_ID`, `_BUSINESS_ACCOUNT_ID`, `_TOKEN`, `_VERIFY_TOKEN`, `_APP_SECRET`, `_API_VERSION` **ALL PRESENT** + `FEATURE_WHATSAPP=1`, `FEATURE_WHATSAPP_BUILDER=1`. **WA is NOT dormant on creds anymore** — the V2 master plan's "Meta creds pending / WA dormant" line is STALE; the real blocker is now gate config + template wiring, not creds. |
| RAG corpus | `kb_sources / kb_documents / kb_chunks = 0 / 0 / 0` (empty). No `EMBED_*` keys in `.env` → dense pgvector leg dormant; FTS leg keyless. |
| Warm-transfer | grep `handoff_number\|human_number\|transfer_number\|warm_transfer\|notify_handoff_team\|transfer_to_human` across `*.py` = **0 hits**. Primitive `transfer_sip_participant` present in `/opt/capsy-agent/.venv/.../livekit/api/sip_service.py`. |
| Memory store | `var/memory/` = **7 files** (outbound writes these per person). `var/wa_threads/` = **0** (the post-call WA auto-followup has never fired — gate is OFF on every campaign). |
| SIP inbound | inbound trunk + dispatch EMPTY (per V2 plan; no inbound call has ever completed). Outbound trunks frozen/untouched. |

---

## 1. STAGE-BY-STAGE — the connected pipeline

### Stage 1 — OUTBOUND call + dial + voice (the LIVE earner) → **BUILT**
- **Code:** `agent.py` (worker `capsy`, `famit-agent.service:8090`), `prompt.py` (`build_system_prompt:254`,
  warm opener `:228`, natural AI disclosure `:274-284`), tuned `AgentSession` kwargs `agent.py:597-651`
  (barge-in, semantic turn-detect, ~1.1 s/turn). Dial bridge = `famit-bridge`, queue = `famit-caller`.
- **Works:** real money-earning outbound calls; Riya greets human-like, multi-lingual (Sarvam `unknown`
  Hinglish), books-intent, ~1.1 s/turn latency moat. This is the proven asset everything else hangs off.
- **Frozen** — read-only reuse only. Note: it is the **producer** of Stages 2–3's context.

### Stage 2 — Per-call transcript + summary + per-PERSON memory + cross-call recap → **BUILT (outbound) / the unifying spine**
- **Code:** transcript `var/transcripts/{room}.json`; per-call row `var/calls.json` (**116 rows live**, has
  `interest`, `outcome`, `campaign_id`, `room`); **per-person memory `var/memory/{digits}.json`** (the running
  multi-call dialog — `{phone,last_call_at,summary,history[]}`); summary+score = `agent.py:155
  _summarize_transcript` → `{summary, outcome, interest 0-100, next_action, opt_out, callback_at}`. Recap =
  `memory.py` (`load_memory`, `build_recap` ≤600 chars, `save_memory`, `parse_phone`). The outbound recap
  injection that proves the pattern works = `agent.py:391-413` (`=== PICHHLI BAAT ===` into the prompt).
- **Works:** outbound writes memory + transcript + summary every call, and **recalls prior context on the next
  outbound call** — the "continue the conversation" behaviour ALREADY works for outbound.
- **THE CONNECTION GAP:** this per-person store is the unifying context for the whole pipeline, but **only the
  outbound path reads/writes it.** Inbound never loads it (Stage 5 gap), and the memory key normalization must
  go raw-CLI → `caller.norm()` → `load_memory()` or it misses (`06375548830` vs `916375548830.json`). The
  unified PG CRM tables (`contacts/contact_identity/contact_timeline`) exist but are **0 rows** — the live path
  is the JSON files, not PG.

### Stage 3 — Post-call WhatsApp TEMPLATE send → **PARTIAL → DORMANT (gate off, not creds)**
- **Code:** send = `whatsapp.py` (`send_whatsapp_async` template `:291`, `send_whatsapp_text_async` free-form
  `:242`). After-call hook = `_finalize_call` (`caller.py:1873`) → already calls `_wa_ai_followup`
  (`caller.py:1601`). Approved template **`post_call_followup`** is LIVE in Meta (MARKETING/en, 2 vars
  `{{name}},{{product}}` + 2 quick-reply buttons).
- **Works:** the after-call hook is **wired** and creds are present — template-send to any number works.
- **GAP / why nothing fires:** (a) the gate is the **per-campaign `fields.wa_followup` boolean = False on
  EVERY campaign** and there is no global `WA_AUTO_FOLLOWUP` flag → fires on zero campaigns; (b) the instant
  post-call auto-send currently drafts **free-form text**, which Meta **rejects cold** (a fresh outbound call
  does NOT open the 24h window) — the approved `post_call_followup` **template** is not wired into the
  auto-send path (its name is referenced nowhere in `caller.py`); (c) language must be `en` or Meta 404s.
  **Net: instant cold template-send on call-complete is built-but-not-armed.** `var/wa_threads/` = 0 confirms
  it has never fired. *(A separate WhatsApp-automation wave is mid-flight closing exactly these gaps.)*

### Stage 4 — WhatsApp LLM multi-step conversation (with call context) → **BUILT (inbound-reply) / DORMANT until lead replies**
- **Code:** inbound webhook GET-verify `caller.py:4361` (token `evsaivoiceagent`) + POST-receive `:4415`
  (HMAC-checked, parses text + button taps). Reply brain = `_wa_handle_inbound` (`caller.py:1543`) →
  per-contact thread `var/wa_threads/<digits>.json`, opt-out (STOP) + human-handoff-word + `WA_MAX_TURNS=12`
  guards → `_wa_reply_text` (`caller.py:1518`) = **one Groq call with system brain (agent/company/product/
  call-summary) + last 10 thread turns + incoming**.
- **Works:** a genuine **multi-turn, call-context-grounded** reply brain exists and is valid (the lead's
  inbound message opens the 24h window, so free-form is allowed). This is a real strength.
- **CONNECTION (good):** the WA reply brain **is** seeded with the call summary/campaign — so context DOES
  flow call → WhatsApp on the reply side. **GAP:** it is NOT routed to `ai_manager`/`workforce`, so it
  converses but **cannot take actions** (book/schedule) — only flags `needs_human`. Dormant in practice
  because Stage 3 never sends the opener, so no lead has ever replied (0 threads).

### Stage 5 — Inbound call routing + returning-caller history continuation + new-caller campaign-ask → **NOT-BUILT / PARTIAL (the biggest hole)**
- **Code present (reusable):** caller-ID read inbound `aim_voice_agent.py:398-413`; multi-form matcher
  `:151 _match_forms`; resolver `caller.py:1465 _resolve_contact_by_phone` → `{tenant_id,name,campaign_id}`;
  campaigns `var/campaigns/{id}.json` (8, ≥6 ready) carry the full sales brain.
- **State:** the inbound worker that exists (`aim-voice-agent`, `agent_name=manager`) is the **Mode-B command
  brain only** — there is **NO Mode-A customer-sales inbound worker** (`sales-in`). **No inbound call has ever
  completed** because: (1) the voice rail dies on a transient STT blip — **P0 silence bug** (Sarvam
  `max_retry=0`, `sarvam/stt.py:567`); (2) **SIP inbound trunk + dispatch are EMPTY** (no DID wired, container
  is UDP-only, needs additive TCP-5060); (3) nothing wires inbound caller-ID → `norm()` → `load_memory()` →
  recap inject (Stage 2 store is never read inbound). Campaign-by-DID is impossible today (campaigns carry no
  `did` field; no `var/inbound_dids.json`), so a new caller can only be **asked** which campaign.
- **THE CENTRAL CONNECTION FAILURE:** the founder's headline promise — *"if they call back, the inbound AI has
  the FULL history (call + WhatsApp)"* — **does not exist.** The per-person memory (Stage 2) and the WA thread
  (Stage 4) are both on disk, but no inbound voice path loads either. This is the keystone gap.

### Stage 6 — Hot-lead detection + human warm-transfer + hot-lead → WhatsApp-to-team → **PARTIAL (detect) / NOT-BUILT (transfer + team-notify)**
- **Hot detection — PARTIAL/BUILT (post-call):** `agent.py:155` interest 0-100; `caller.py:1297` sets
  `lead.hot = interest >= 70` (indexed `leads_org_score_idx`). **Post-call hot works.** **Mid-call** hot
  signal (needed to transfer DURING a call) does NOT exist — the only detection gap (GAP-B1).
- **Warm transfer — NOT-BUILT:** primitive `transfer_sip_participant` is in the venv (verified), but **zero
  code calls it and no handoff-number list exists** (grep = 0). `workforce/handover.py` is summary-to-inbox,
  **not** a live-call transfer. Decision (from plans): **Pattern C — dial the human INTO the room via
  `CreateSIPParticipant` over the trunk (read-only reuse), warm whisper, no carrier REFER needed.** Needs a
  `transfer_to_human` tool + a per-vendor `handoff{}` block on the Business Brain + a no-answer fallback ladder.
- **Hot-lead → team WhatsApp — NOT-BUILT (reuse-ready):** every block exists (`whatsapp.py:248` template send,
  the post-call hot trigger, `_wa_draft_followup_text` payload) but `notify_handoff_team()` is unwritten and
  the **`hot_lead_alert` template is not registered in Meta** (GAP-C1, founder/Meta step). The handoff team has
  no open 24h window → the alert MUST be an approved template.
- **CONNECTION:** none of this is wired; "when hot, warm-transfer + WhatsApp the hot lead to the team" is fully
  designed but unbuilt.

### Stage 7 — The PANEL surfaces for all of the above → **PARTIAL (good coverage, key gaps)**
- **BUILT + backed (live `${BASE}` API):** `app/calls` (`getCalls`→`/calls?limit=200`, `getCallDetail`→
  `/calls/{id}`) shows **transcript + interest + outcome**; `app/crm/[id]` = **contact-360 with a 13-ref
  timeline + Calls + WhatsApp**; `app/leads` (`getLeads` hot/sort); `app/callbacks` (`getCallbacks`/add/
  cancel); `app/whatsapp` (`/whatsapp/send` + `/whatsapp/log`, template-aware); `app/ai-manager/sessions`.
- **GAPS (front-end-missing or backend-missing):**
  - **No Human-Handoff settings card** (`settings/page.tsx` has 0 handoff/transfer refs) → vendor cannot add
    handoff numbers (Stage 6 has no config surface).
  - **No WhatsApp conversation/thread viewer** — panel shows a send-log only, not the per-contact LLM thread
    (`var/wa_threads/*`) from Stage 4.
  - **No inbound-DID admin** (no `inbound_dids` super-admin surface) → no way to map DID→campaign/tenant for
    Stage 5 zero-ask routing.
  - **No inbound analytics** (containment/transfer/hot/sentiment) and **no recording player** (recording is a
    `_NullRecorder` no-op; `ai_manager` read API not fully mounted; no Egress/Spaces).

---

## 2. THE CONNECTIONS — does context truly flow call → WhatsApp → inbound? (the headline question)

| Hop | Flows today? | Verdict |
|---|---|---|
| Outbound call → per-person MEMORY (Stage 1→2) | **YES** | memory + transcript + summary written every call; recap recalled on next OUTBOUND call. |
| Outbound call → WhatsApp opener (Stage 2→3) | **NO (armed-but-not-firing)** | hook wired, creds present, but gate off on every campaign + template not wired + cold-send uses free-form → 0 threads ever. |
| WhatsApp opener → WhatsApp LLM thread (Stage 3→4) | **Reply brain READY, but never reached** | reply brain is call-context-grounded and works once a lead replies — but no opener is sent, so no reply, so dormant. |
| **Call + WhatsApp history → INBOUND voice (Stage 2/4 → 5)** | **NO — the keystone gap** | no Mode-A inbound worker, no SIP, P0 silence bug; nothing loads memory or WA thread on an inbound call. The "full history on callback" promise is unbuilt. |
| Inbound/any call → hot warm-transfer + team WhatsApp (Stage 5→6) | **NO** | transfer primitive present but uncalled; no handoff list; team-notify + `hot_lead_alert` template unbuilt. |
| All stages → PANEL visibility (→7) | **PARTIAL** | calls/CRM-360/leads/callbacks/WA-log/sessions backed; handoff config, WA-thread viewer, inbound-DID admin, recording, inbound analytics missing. |

**Bottom line:** the system is a set of strong, individually-real components that are **NOT yet connected into
one loop.** ~70% of a world-class brain exists (memory, summary, hot-score, RAG engine, WA reply brain,
booking/payments/CRM engines, transfer primitive, panel-360) — **most remaining work is WIRING + config +
arming gates, plus three genuinely-new pieces** (the `sales-in` inbound worker, the `handoff/` package, and the
panel handoff/thread/DID surfaces). The two hardest, highest-value holes are **Stage 5** (inbound with full
history — the keystone) and **Stage 6** (warm-transfer + hot-team-WhatsApp).

---

## 3. WHAT IS ONLY FRONT-END vs ONLY BACK-END (the mismatch list)
- **Back-end exists, NO panel surface:** WhatsApp LLM threads (`var/wa_threads`, no viewer); hot-flag on leads
  (shown as badge but no hot-pipeline view); inbound sessions partially (page exists, voice never populates).
- **Designed/needed, NEITHER built:** Human-Handoff settings card; inbound-DID map admin; inbound analytics
  dashboard; recording player (recording itself is a no-op).
- **Engines mounted, voice un-wired (built but unreachable from a call):** `booking/core.py` (atomic
  no-double-book), `payments/core.py`, `crm/core.py`, RAG `kb/`+`brain/`, `scheduler_loop` callbacks,
  `eval/scorers` per-call QA.

---

## 4. TOP PRODUCTION-READINESS BLOCKERS (priority order, for the next build waves)
1. **P0 — inbound voice never survives a call** (Sarvam `max_retry=0` silence bug). Nothing downstream matters
   until an inbound call is answered and heard. *(code fix, isolated to `aim_voice_agent.py`.)*
2. **SIP inbound not wired** (empty trunk/dispatch, UDP-only container). *(one additive TCP-5060 change + DID.)*
3. **Stage 5 keystone** — no `sales-in` worker loading memory + WA history on inbound. *(new isolated worker.)*
4. **Stage 3 arming** — turn on the auto-followup gate + wire the approved `post_call_followup` template for
   cold send (template not free-form). *(config + small wire; WA wave mid-flight.)*
5. **Stage 6** — `handoff/` package (warm-transfer Pattern C + `notify_handoff_team`) + handoff settings card +
   register `hot_lead_alert` Meta template (founder step) + mid-call hot signal.
6. **RAG arming** — populate the KB corpus per tenant + add an embedder key (config, not code; FTS works now).
7. **Panel gaps** — handoff card, WA-thread viewer, inbound-DID admin, recording + inbound analytics.

## 5. FOUNDER/NON-CODE BLOCKERS (so the build never silently stalls)
- Register the **`hot_lead_alert`** WhatsApp template in Meta (Stage 6 team-notify cold-send).
- Procure + map DIDs (Vobiz): a private manager DID + per-campaign customer DIDs (DLT 160-series, attestation).
- Verify whether **Vobiz honours SIP REFER** (Pattern C avoids needing it, but confirm for the fallback).
- DO Spaces creds (recording upload) + gateway keys (in-call payment) — Stage 5/6 polish.
- Configure an off-box embedder (`EMBED_*`) to light the RAG dense leg.

---

## 6. EVIDENCE INDEX (file:line, live box `168.144.153.145`, all read-only)
- **Outbound earner:** `agent.py` (`_load_campaign:142`, `_summarize_transcript:155`, kwargs `:597-651`,
  `_CLOSE_*` banks `:280-312`), `prompt.py:254/228/274-284`. Worker `capsy`/`famit-agent`/`:8090`.
- **Memory/context spine:** `memory.py` (`load_memory:53`, `build_recap:67`, `save_memory:96`,
  `parse_phone:34`); `var/memory/{digits}.json` (7 files); recap inject `agent.py:391-413`;
  `caller.py:649 norm`, `:1465 _resolve_contact_by_phone`, `:1297 hot=score>=70`.
- **WhatsApp:** `whatsapp.py` (`send_whatsapp_async:291` template, `send_whatsapp_text_async:242` free-form,
  `meta_configured:101`); `caller.py` (`_finalize_call:1873` → `_wa_ai_followup:1601`,
  `_wa_draft_followup_text:1492`, inbound `_wa_handle_inbound:1543`, `_wa_reply_text:1518`,
  webhook GET `:4361`/POST `:4415`, manual `/whatsapp/send:4321`). Approved template `post_call_followup`.
  Creds `META_WA_*` PRESENT; gate `fields.wa_followup`=False on all campaigns; `var/wa_threads`=0.
- **Warm transfer:** `/opt/capsy-agent/.venv/.../livekit/api/sip_service.py transfer_sip_participant` (present,
  uncalled); Pattern C = `CreateSIPParticipant` over trunk `ST_fmtVmNJmpzKa`; handoff grep = 0 hits.
- **RAG:** `kb/core.py` (hybrid FTS+pgvector RRF, `retrieve`/`ingest`), `kb/schema.sql` (`vector(1024)`, HNSW+GIN,
  FORCE-RLS), `brain/core.py` wrapper, `vendors/embeddings.py` dormant; corpus 0/0/0; no `EMBED_*`.
- **Inbound (un-wired):** `aim_voice_agent.py` (caller-ID `:398-413`, `_match_forms:151`, greet `:481`,
  apology guard `:381`, STT P0 `_build_stt:644` ← `sarvam/stt.py:567 max_retry=0`); `ai_manager/` command spine;
  SIP inbound/dispatch EMPTY; campaigns lack `did`; no `var/inbound_dids.json`.
- **Un-wired engines:** `booking/core.py` (mounted `caller.py:5012`), `payments/core.py`, `crm/core.py`,
  `eval/scorers.py`, `scheduler_loop caller.py:4813`, `workflow/dsl.py:36` (`lead.qualified`/`call.completed`).
- **Panel:** `famit-panel/lib/api.ts` (`getCalls:539`→`/calls`, `getCallDetail:566`→`/calls/{id}`,
  `getLeads:401`, `getCallbacks:1175`, `sendWhatsApp:1586`→`/whatsapp/send`, `getWhatsAppLog:1608`); pages
  `app/calls`, `app/crm/[id]` (360 timeline), `app/leads`, `app/callbacks`, `app/whatsapp`,
  `app/ai-manager/sessions`. Missing: handoff settings card, WA-thread viewer, inbound-DID admin,
  recording player, inbound analytics.
- **Companion plans:** `INBOUND-PIPELINE-MASTER-PLAN.md` (v1) + `-V2.md`; explores `plan-lead-history.md`,
  `plan-handoff-hotlead.md`, `plan-rag-context.md`, `wa-automation-state.md`, `wa-llm-conversation.md`.
