# EXPLORE-2 — WARM TRANSFER · HOT-LEAD DETECTION · WHATSAPP NOTIFY (handoff + hot-lead features)

> **Status:** READ-ONLY explore/design. No code, no deploy, no git. Extends `INBOUND-PIPELINE-MASTER-PLAN.md`
> (Phase 7 "handoff" line) and `plan-handoff-hotlead.md` is the grounded map for two new founder features:
> **(1) live human warm-transfer** ("I want a human" / lead is hot → bridge the live call to a real person),
> and **(2) hot-lead → WhatsApp** (after a call, if hot, auto-notify the vendor's handoff team the lead phone
> + summary). **#1 RULE unchanged:** every capability here is **ADDITIVE + ISOLATED** and **NEVER touches the
> outbound earner** (`agent.py` / `famit-agent` / outbound trunks `ST_fmtVmNJmpzKa`+`ST_LH8ighJJtHSi`). The
> earner was just restored after an infra mistake. Outbound regression-gate `G` runs before+after every step.
>
> **Box (read-only):** `famit@168.144.153.145`. Voice venv = `/opt/capsy-agent/.venv` (livekit-api **1.1.0**,
> livekit-agents **1.5.17**); API/worker venv = `/opt/famit-agent/.venv`.

---

## 0. HEADLINE VERDICT (per the three asked questions)

| Capability | State | One-line truth |
|---|---|---|
| **(A) WARM TRANSFER** (live call → human PSTN) | 🟢 **POSSIBLE, primitive present, UN-WIRED** | LiveKit `transfer_sip_participant` (SIP REFER) is in the running venv + `lk sip participant transfer --to tel:<num>`. **No code calls it; no handoff-number list exists.** Build = a transfer tool + handoff-list config + LLM trigger. |
| **(B) HOT-LEAD DETECTION** | 🟢 **EXISTS, post-call, reusable** | Every call already gets `_summarize_transcript → {interest:0-100, outcome, summary, next_action}`; `_update_lead_after_call` sets **`hot = score >= 70`** on the lead. Threshold + signal already live. **Mid-call** hot-detection is the only gap. |
| **(C) WHATSAPP SEND to arbitrary team** | 🟢 **EXISTS, reusable** | `whatsapp.send_whatsapp_text(to, text)` sends free-form to ANY E.164; `send_whatsapp(to, template, params)` sends templates. **Constraint:** free-form only inside the 24h window → team-notify MUST use an **approved template** (the team rarely messages the business first). |

**Net:** all three building blocks **already exist on the box** — the work is **glue + config + 1 LLM tool**,
all additive. The single genuinely-new code is the live-transfer tool; hot-detect + WA-send are reuse.

---

## 1. (A) WARM TRANSFER — can the live stack transfer an in-progress call to a human PSTN number?

**YES — the primitive is present and verified, but nothing wires it.** Evidence (read-only):

- **LiveKit SIP transfer API is in the running voice venv.** `livekit-api 1.1.0` →
  `livekit/api/sip_service.py:804 async def transfer_sip_participant(transfer: TransferSIPParticipantRequest)`.
  The proto `TransferSIPParticipantRequest` carries `participant_identity`, `room_name`, `transfer_to`,
  `play_dialtone`, `headers`, `ringing_timeout`; the `SIP` service exposes the `TransferSIPParticipant` RPC.
- **CLI mirror exists:** `lk sip participant transfer --room <r> --identity <id> --to tel:<phone> --play-dialtone`
  (lk 2.16.3). `--to` accepts `tel:<E.164>` (PSTN) or a `sip:` URI.
- **Mechanism = SIP REFER (cold/blind transfer at the carrier).** LiveKit sends a REFER for the caller's SIP
  leg to the trunk; the **carrier (Vobiz)** must honour REFER and re-INVITE the leg to the human's PSTN number.
  This is a **blind/cold** transfer (the human is dialed, the AI leg drops) — NOT an attended/3-way bridge.
  `play_dialtone=true` plays a dial tone to the caller while the human is rung (covers the gap).
- **Two transfer shapes possible on this stack:**
  - **(i) SIP REFER cold transfer** (`transfer_sip_participant`, `transfer_to="tel:+91…"`) — simplest, one
    API call, but **context is spoken-only** (AI verbally briefs, then drops) and **depends on Vobiz REFER
    support** (UNVERIFIED — carrier capability question, see GAP-A1).
  - **(ii) Conference/dial-in bridge** (no REFER needed): keep the caller in the room, **`CreateSIPParticipant`
    dials the human into the SAME room** via the OUTBOUND trunk — now it's a 3-way (caller + human + AI). The
    AI gives a live spoken context handoff ("Riya: this is Mr. Sharma, hot on the 2BHK, here's the summary…"),
    then leaves. This is a **true warm/attended transfer**, **does NOT need carrier REFER**, and **reuses the
    exact outbound dial path** — but it **dials over the outbound trunk** (must be read-only reuse: place the
    leg from the INBOUND worker using the trunk ID, never edit the trunk/earner). **RECOMMENDED** — more
    reliable than REFER and gives a genuine warm intro.
- **What's MISSING (all additive):**
  1. **No handoff-number list anywhere.** Grep for `handoff_number|human_number|transfer_number|escalation`
     across `*.py/*.json/*.sql` = **0 hits**. Needs a per-vendor list (a vendor adds MULTIPLE numbers):
     `var/handoff_team.json` → `{tenant_id, numbers:[{phone, label, wa_optin}], hours, strategy:"first_free|round_robin"}`
     (or PG `handoff_targets` with FORCE-RLS — preferred for multi-vendor isolation, mirrors `ai_manager_*`).
  2. **No transfer tool / trigger.** `inbound_agent.py` is a deferred stub; `workforce/handover.py` is
     **summary-to-inbox handover, NOT live-call transfer** (it writes an audit item + inbox shape, never
     touches the voice leg). Build a `@function_tool transfer_to_human(reason)` the LLM calls when the caller
     says "talk to a human" OR the mid-call hot-signal fires; it picks a free handoff number (respect hours),
     speaks a bridge line, then dials-into-room (shape ii) or REFERs (shape i).
  3. **No fallback when no human answers** → must fall back to "logged callback + hot-WhatsApp notify" (feature B),
     never a dead drop (Master-Plan §5.4/§5.13 never-silent rule).

**Attended vs blind verdict:** **prefer attended/warm via dial-into-room conference (shape ii)** — it preserves
context with a live spoken intro and avoids the Vobiz-REFER unknown. Keep SIP-REFER (shape i) as a lighter
fallback. **Context preservation** = the AI speaks the summary to the human on the bridge **+** the same
hot-lead WhatsApp (feature B) lands the phone+summary in the human's chat simultaneously (belt-and-braces).

---

## 2. (B) HOT-LEAD DETECTION — is there a lead-scoring / hot signal? how is "hot" decided post-call?

**YES — fully built and live for OUTBOUND; the same logic is reusable for inbound verbatim.**

- **Post-call scorer:** `agent.py:155 _summarize_transcript()` → **one Groq call** returns
  `{summary, outcome∈[interested,not_interested,callback,no_answer,voicemail,opt_out], interest:int 0-100,
  next_action, opt_out, callback_at}`. Runs on every call's transcript at shutdown (`agent.py:474` logs
  `outcome=… interest=…`).
- **Hot flag set on the lead:** `caller.py:1273 _update_lead_after_call()` keeps the **best interest ever seen**
  and sets **`x["hot"] = best >= 70`** (caller.py:1297). So **"hot" = interest score ≥ 70** — the threshold
  already exists and is the natural trigger. `db/models.py:124 leads_org_score_idx (org_id, score desc)` indexes it.
- **Existing post-call WhatsApp hooks (to the LEAD, not the team):** `caller.py:1351 _send_whatsapp`,
  `:1417 _wa_followup`, `:1600 _wa_ai_followup` already fire on `outcome=="interested" or interest>=70` and
  draft a context message (`_wa_draft_followup_text` at :1492 uses summary+next_action+interest). **This is the
  exact branch to tee the team-notification off** — same trigger, new recipient set.
- **Workflow events exist:** `workflow/dsl.py:36` emits `lead.qualified` / `call.completed` — a clean event to
  hang the hot-lead automation on later.
- **GAP (small):** **mid-call** hotness for live transfer. The 0-100 score is computed **post-call** only. For
  the "lead gets hot → transfer NOW" path, add a **lightweight in-call signal**: either (a) the LLM emits a
  `lead_is_hot` tool-call when buying-intent phrases hit (cheap, reuses the `_CLOSE_*` phrase banks at
  agent.py:280-312), or (b) a periodic mini-classify of the running transcript. Post-call hot → WhatsApp needs
  **no new detection** (reuse interest≥70). **Threshold should become per-vendor configurable** (some want ≥60).

---

## 3. (C) WHATSAPP SEND — can whatsapp.py message an ARBITRARY number (the handoff team) with lead context?

**YES — `whatsapp.py` already sends to any number; the only constraint is Meta's template/24h-window rule.**

- **Free-form to any E.164:** `whatsapp.py:233 send_whatsapp_text(to, text)` posts a Meta `type:"text"` body to
  any recipient (`_meta_to` strips the `+`). **Valid ONLY inside the 24h customer-service window** (Meta rule).
- **Template to any E.164:** `whatsapp.py:248 send_whatsapp(to, template_name, params)` posts a `type:"template"`
  body — **works cold, no 24h window**, but needs a **pre-approved template** with body variables.
- **Async variants** (`*_async`) exist for the FastAPI loop; native Meta path wins when `META_WA_*` is set;
  **graceful no-op when WA creds absent** (today WA is dormant/`not_configured` per HANDOFF — Meta creds pending).
- **THE CONSTRAINT (load-bearing for team-notify):** the handoff team almost never messages the business first,
  so **there is usually NO open 24h window with them** → **free-form `send_whatsapp_text` will be rejected**.
  The team alert **MUST be an approved template** like
  `hot_lead_alert` body = *"🔥 Hot lead {{1}} ({{2}}). Summary: {{3}}. Score {{4}}/100. Reply to take over."*
  → `send_whatsapp(team_number, "hot_lead_alert", [name, phone, summary, score])`. Registering that template is a
  **founder/Meta-onboarding step** (recorded as a gap), not code. (Once the team replies, the 24h window opens and
  richer free-form follow-ups become possible.)
- **Reuse, don't rebuild:** the team-notify is a thin loop over the handoff-list calling the **same** `send_whatsapp`
  used by `_wa_followup` — one new function `notify_handoff_team(tenant_id, lead, summary)`; the context payload
  is already assembled by `_wa_draft_followup_text` (caller.py:1492) — reuse its summary/next_action/interest fields.

---

## 4. (BONUS) RAG / pgvector — VERIFIED IT EXISTS (founder's question #3, relevant to context)

**The founder is RIGHT — a pgvector RAG was built.** `kb/` module: `kb/schema.sql` declares
`kb_chunks.embedding vector(1024)` (pgvector dense leg) + `fts tsvector` (Postgres FTS sparse leg) with an
**HNSW cosine index** (`kb_chunks_embed_hnsw`); `kb/core.py:299 retrieve(tenant_id, query, scope, channel,
scope_campaign_id)` does **hybrid (FTS + dense) RLS-scoped retrieval**, `ingest()` chunks+embeds.
`brain/core.py` wraps it (`retrieve()`/`add_knowledge()` → `kb.retrieve`/`kb.ingest`, business-scoped). **Status:
FTS leg works keyless TODAY; the dense/embedding leg is DORMANT until an embedder key (`vendors/embeddings`).**
**Where inbound should USE it** (covered fully in the companion RAG doc): inject `kb.retrieve()` hits into the
inbound sales prompt for **objection-handling + product detail + campaign knowledge**, scoped to the resolved
`campaign_id` — this is the "greater context" the founder wants and needs **no new infra**, just a key + a
retrieve-call in the inbound prompt builder. (Full design → separate `plan-rag-context.md`.)

---

## 5. 12-LINE MAP (transfer + hot-detect + WhatsApp, with the gaps)

1. **WARM TRANSFER — PRIMITIVE PRESENT, UN-WIRED.** `livekit-api 1.1.0 transfer_sip_participant` (sip_service.py:804) + `lk sip participant transfer --to tel:<num>` exist in the live voice venv; **zero code calls them.**
2. **TWO transfer shapes:** (i) **SIP REFER cold** (`transfer_to="tel:+91…"`, `play_dialtone`) — needs Vobiz REFER support (UNVERIFIED gap); (ii) **dial-human-into-room conference** (`CreateSIPParticipant` over the outbound trunk) — true **warm/attended**, no REFER needed → **RECOMMENDED**.
3. **HANDOFF-LIST DOESN'T EXIST** — grep `handoff_number|human_number|transfer_number` = 0 hits. Build per-vendor `handoff_targets` (PG+RLS preferred; vendor adds MULTIPLE numbers + hours + WA-optin).
4. **`workforce/handover.py` is NOT a live transfer** — it's summary-to-inbox/approval handover (audit item only), never touches the voice leg. New `transfer_to_human()` voice tool required.
5. **HOT-DETECT EXISTS POST-CALL** — `agent.py:155 _summarize_transcript` → `interest 0-100`; `caller.py:1297` sets `lead.hot = interest>=70`. Threshold already live + indexed (`leads_org_score_idx`).
6. **MID-CALL hotness = the only detection gap** — add a cheap LLM `lead_is_hot` tool-call (reuse `_CLOSE_*` phrase banks at agent.py:280-312) so "gets hot → transfer NOW" can fire; post-call hot needs no new code.
7. **WHATSAPP-SEND TO ANY NUMBER EXISTS** — `whatsapp.py:233 send_whatsapp_text(to,text)` (free-form, 24h window) + `:248 send_whatsapp(to,template,params)` (cold, template). Async variants present.
8. **TEAM-NOTIFY MUST USE AN APPROVED TEMPLATE** — the handoff team has no open 24h window → free-form rejected; register `hot_lead_alert` template `{{name}}{{phone}}{{summary}}{{score}}`. **Template registration = founder/Meta step (gap).**
9. **POST-CALL WA HOOK ALREADY EXISTS to tee off** — `caller.py:1351/1417/1600 _wa_*` fire on `interested or interest>=70`; add `notify_handoff_team()` on the SAME trigger, new recipients; reuse `_wa_draft_followup_text` (:1492) for the payload.
10. **WA IS DORMANT TODAY** — Meta `META_WA_*` creds pending (HANDOFF); all WA paths no-op gracefully until creds land. **Meta onboarding + template approval = founder blocker** for feature (2).
11. **CONTEXT PRESERVATION = belt-and-braces** — on transfer, the AI speaks the summary on the bridge **AND** the hot-lead WhatsApp drops phone+summary into the human's chat simultaneously; on no-human-answer, fall back to logged-callback + hot-WA (never a dead drop).
12. **RAG/pgvector CONFIRMED REAL** — `kb/` (pgvector `vector(1024)` + FTS hybrid, HNSW, `kb.retrieve` RLS-scoped) wrapped by `brain/core.py`; FTS works keyless now, dense leg dormant until an embedder key. Use it to inject objection/product/campaign context into the inbound prompt (full design → `plan-rag-context.md`).

---

## 6. OPEN GAPS / FOUNDER (non-code) BLOCKERS — recorded so the build doesn't drop them
- **GAP-A1 (carrier):** does **Vobiz honour SIP REFER**? If not, the cold-REFER shape (i) is out → use the
  dial-into-room conference shape (ii), which needs no REFER. **Verify with Vobiz before relying on REFER.**
- **GAP-A2:** per-vendor **handoff-number list** UI + storage (PG `handoff_targets`, FORCE-RLS) — a vendor can add
  many numbers, each with label/hours/WA-optin; transfer picks a free one (respect business hours).
- **GAP-B1:** **mid-call hot signal** (LLM tool-call) so live transfer can fire on getting-hot, not only post-call.
- **GAP-B2:** **per-vendor hot threshold** (some want ≥60, some ≥80) instead of the hardcoded 70.
- **GAP-C1 (Meta, founder):** register the **`hot_lead_alert` WhatsApp template** + finish Meta onboarding so the
  team-notify can send cold; until then WA is dormant (graceful no-op).
- **GAP-C2:** handoff-team members must **opt-in / be WA-reachable**; store per-number `wa_optin`.
- **SAFETY (unchanged):** the transfer leg, if it dials over the outbound trunk, is **read-only reuse** of the
  trunk ID — **never** edit the trunk, dispatch, or `agent.py`; meter+wallet-gate the human leg against the
  resolved tenant; outbound regression-gate `G` before+after every step. Audit every transfer (who/when/to-whom).

## 7. EVIDENCE INDEX (file:line, live box — all read-only)
- **Transfer primitive:** `/opt/capsy-agent/.venv/.../livekit/api/sip_service.py:804 transfer_sip_participant`;
  proto `TransferSIPParticipantRequest{participant_identity,room_name,transfer_to,play_dialtone,headers,ringing_timeout}`;
  `lk sip participant transfer --room --identity --to tel:<num> --play-dialtone` (lk 2.16.3). Conference shape =
  `CreateSIPParticipant` over outbound trunk `ST_fmtVmNJmpzKa` (env `LIVEKIT_SIP_TRUNK_ID`).
- **Hot-lead:** `agent.py:155 _summarize_transcript` (interest 0-100); `caller.py:1273 _update_lead_after_call`,
  `:1297 hot=score>=70`; `db/models.py:124 leads_org_score_idx`; phrase banks `agent.py:280-312 _CLOSE_*`.
- **WhatsApp:** `whatsapp.py:233 send_whatsapp_text` (free-form/24h), `:248 send_whatsapp` (template/cold),
  `:291 send_whatsapp_async`; post-call hooks `caller.py:1351 _send_whatsapp`, `:1417 _wa_followup`,
  `:1492 _wa_draft_followup_text`, `:1600 _wa_ai_followup`; OTP-to-WA mirror `ai_manager/otp/sender.py`.
- **Handover (NOT live transfer):** `workforce/handover.py:13 summarize`, `:35 notify_approver` (inbox/audit only).
- **RAG/pgvector:** `kb/schema.sql` (`embedding vector(1024)`, `fts tsvector`, HNSW `kb_chunks_embed_hnsw`);
  `kb/core.py:299 retrieve`, `:209 ingest`, `:52 available`; `brain/core.py` wrapper; embedder dormant (`vendors/embeddings`).
- **Deferred inbound voice stub:** `ai_manager/inbound_agent.py` (VoiceTransport contract, livekit lazy-imported).
