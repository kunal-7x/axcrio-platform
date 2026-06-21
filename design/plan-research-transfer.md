# RESEARCH — WARM TRANSFER · HOT-LEAD ROUTING (web-grounded patterns for the inbound brain)

> **Status:** READ-ONLY web research + applied design. No code, no deploy, no git. Writes only this doc.
> **Extends:** `INBOUND-PIPELINE-MASTER-PLAN.md` (§5.4 "human handoff", Phase 7), `plan-handoff-hotlead.md`
> (the box-grounded primitive map), `plan-vendor-modules.md` (the handoff-list storage design), and
> `plan-rag-context.md` (context preservation). **This doc supplies the EXTERNAL best-practice evidence** —
> how the best AI voice systems (Vapi / Retell / Bland / Telnyx / contact-centers) do human handoff and
> hot-lead routing — so the Famit build copies a proven shape, not a guess.
>
> **#1 RULE (unchanged):** every capability here is **ADDITIVE + ISOLATED** and **NEVER touches the live
> outbound earner** (`agent.py` / `famit-agent` / outbound trunks `ST_fmtVmNJmpzKa`+`ST_LH8ighJJtHSi`). The
> earner was just restored after an infra mistake. Outbound regression-gate `G` runs before+after every step.
> **Box (read-only):** `famit@168.144.153.145`; voice venv `/opt/capsy-agent/.venv` (livekit-api **1.1.0**).

---

## 0. WHY THIS DOC (the founder's two new asks, in one line each)
1. **WARM HUMAN HANDOFF** — AI runs the whole sales call (goal = full automation); but if the lead gets HOT
   **or** explicitly asks "I want a human," **seamlessly + fast** transfer the LIVE call to a real human phone
   number from the vendor's **handoff list** (a vendor may add MULTIPLE numbers), **with context preserved**.
2. **HOT-LEAD → WHATSAPP** — after every call, if the lead is HOT, auto-create the hot-lead entry and
   auto-send the lead phone + call summary to the handoff-list WhatsApp numbers (reuse the LIVE `whatsapp.py`).

The box-side feasibility for both is already proven in `plan-handoff-hotlead.md` (transfer primitive present
but un-wired; `interest>=70` hot flag live at `caller.py:1297`; `send_whatsapp` reusable). **What was missing
was the EXTERNAL pattern evidence — supplied here.**

---

## 1. THE THREE TRANSFER PATTERNS (what the best systems actually do)

Every production voice-AI platform converges on **exactly three handoff shapes**. Verbatim from Vapi, Retell,
and Telnyx docs (cited §6):

| # | Pattern | Mechanism | Context to human | Verdict for Famit |
|---|---------|-----------|------------------|-------------------|
| **A** | **Blind / cold transfer** (the universal default) | **SIP REFER** (or carrier "Voice API transfer") — the AI **drops**, the carrier re-INVITEs the caller's leg to the human's number. | **NONE** — human picks up cold, asks the caller to repeat. | **FALLBACK ONLY.** Simplest (one API call: `transfer_sip_participant(transfer_to="tel:+91…")`), but loses context and **depends on Vobiz honouring REFER (UNVERIFIED — GAP-A1)**. |
| **B** | **Private / attended warm transfer** | **Dial + Bridge:** AI dials the human FIRST, **privately** speaks a summary while the caller waits (on hold / dial-tone), THEN bridges the caller in. | **Spoken brief BEFORE the caller joins** ("whisper"). | **The gold standard for sales.** The human is briefed privately, the caller never hears "who is this?". Maps to **dial-the-human-into-a-staging step, then merge.** |
| **C** | **Conferenced warm transfer** (3-way) | **Invite the human as a 3rd participant** into the SAME room; all three can speak; the AI can **stay silent** ("skip turn") and remain available. | **Full live spoken intro** with everyone present; AI keeps its tools. | **The shape this stack can do TODAY with no carrier REFER** — `CreateSIPParticipant` dials the human into the inbound room over the trunk (read-only reuse). Slightly less private than B (caller hears the brief) but **reliable + needs no REFER**. |

**Vapi's named modes** (the canonical menu the founder's product should mirror): `blind` · `warm-transfer
with-summary` (auto-summary from `{{transcript}}`) · `warm-transfer with-message` (custom line) ·
`warm-transfer wait-for-operator-speech` (waits for the human to say hello first, then briefs) ·
`warm-transfer experimental` (dials, **holds caller with hold-audio**, **voicemail-detection**, **fallback
plan if transfer fails**). **Retell** ships warm transfer + native SIP trunking with "full context intact" and
a **private whisper** to the receiving agent. **Telnyx** is the only one shipping **conferenced** warm
transfer as a built-in (AI stays on the line, tools still work).

### THE FAMIT DECISION (grounded in what the box can do)
- **PRIMARY = Pattern C (dial-human-into-room conference) with a Pattern-B-style private whisper where
  possible.** Rationale: (i) it needs **no carrier REFER** (sidesteps GAP-A1 entirely); (ii) it reuses the
  exact outbound dial path (`CreateSIPParticipant` over the trunk ID — **read-only reuse, never edit the
  trunk/earner**); (iii) it gives a **genuine warm spoken intro** ("Riya: this is Mr. Sharma, hot on the
  2BHK, budget ~80L, wants a site visit Saturday — over to you, Rohan"); (iv) the AI can **skip-turn** and
  stay available as a safety net. **Belt-and-braces context:** the same hot-lead WhatsApp (feature 2) drops
  phone+summary into the human's chat **simultaneously**, so even a noisy verbal brief is backed by text.
- **FALLBACK = Pattern A (SIP REFER)** kept as a lighter path **only if** Vobiz confirms REFER support — but
  not required, because C works without it.
- **Do NOT block the live turn-loop** doing the transfer: speak a one-line bridge sentence to the caller
  ("Bilkul — main aapko abhi Rohan se connect karta hoon, ek second"), dial the human off-loop, then merge.

---

## 2. WHEN TO TRIGGER HANDOFF (the trigger taxonomy — copy this list)

The research is unanimous: **trigger on intent/score/sentiment, NOT on "the AI got confused."** Telnyx states
the anti-pattern explicitly: *"Not 'Hand off when the AI gets confused'."* The five legitimate triggers,
mapped to Famit:

| Trigger | Industry rule | Famit wiring (additive) |
|---------|---------------|------------------------|
| **1. Explicit ask** | Caller says "talk to a human / manager / agent." Always honour immediately. | LLM tool-call `transfer_to_human(reason="explicit_ask")` on the phrase; cheap keyword + intent guard. |
| **2. Hot / buying-signal (the sales one)** | "Caller crosses a qualification threshold X" → escalate to close. | **Mid-call hot signal** (GAP-B1): LLM emits `lead_is_hot` when buying-intent phrases hit (reuse `_CLOSE_*` phrase banks `agent.py:280-312`); if `score ≥ rules.transfer_on.hot_score_gte` (per-vendor, default 80) → transfer. |
| **3. Sentiment escalation** | Track **emotional accumulation** across the call ("this is wrong" → "I've waited 20 min" → "forget it"); cross a cumulative-frustration threshold → escalate **before** the customer screams for a human. Leading brands cut escalation + handle time ~40% this way. | Lightweight running-sentiment guard on the transcript; on sustained negative → offer human. **Secondary** to the sales-hot path but valuable for retention. |
| **4. Policy / expertise / licensing gap** | Hand off when the request needs human judgment, a policy exception, or a licensed human (insurance/health). | Per-vendor `escalation_rules` on the Business Brain (already a field — `plan-vendor-modules.md §1`). |
| **5. Repeated confusion (bounded)** | NOT a primary trigger, but after **N failed clarifications** offer a human rather than loop. | Bound by the existing `MAX_CLARIFY≈3` (master-plan Phase 2) → on exhaustion, offer transfer, never dead-air. |

**Context-preservation on EVERY trigger (the defining best-practice):** *"pass full intent history, extracted
entities, and conversation summaries to human agents"* — this is what separates good handoff from bad. Famit
already produces this payload (`_summarize_transcript → {summary, interest, next_action}`,
`_wa_draft_followup_text caller.py:1492`); reuse it for both the spoken whisper AND the WhatsApp alert.

---

## 3. FALLBACK WHEN NO HUMAN ANSWERS (never a dead drop)

The research thins out here (Telnyx's guide *omits* no-answer handling — a gap the build must NOT inherit), but
Vapi's **experimental** mode shows the production shape: **hold-audio while ringing**, **voicemail detection**,
and an explicit **`fallbackPlan` if the transfer fails**. Famit's master-plan never-silent rule (§5.13) demands
a defined ladder. **The Famit fallback ladder (additive, in the handoff `rules`):**

1. **Ring the next eligible number** by `ring_strategy` (`priority_then_roundrobin`), `ring_timeout_s≈25`,
   `max_attempts≈2` — respect each number's `hours` (skip out-of-hours numbers, like round-robin skips OOO reps).
2. **Hold-audio / dial-tone to the caller** while ringing (Vapi `holdAudioUrl` / LiveKit `play_dialtone=true`)
   so the caller never hears silence.
3. **Voicemail detection** — if the human leg hits voicemail, treat as no-answer, don't bridge into a machine.
4. **After-hours / nobody-answers → `after_hours:"wa_only"` + `fallback:"capture_callback"`:** the AI gracefully
   says "our team will call you back," **logs a callback task**, AND fires the **hot-lead WhatsApp** to the team
   (feature 2) so speed-to-lead still wins even when no human picked up live. **Never a dead drop.**
5. **Audit every attempt** (who was rung, answered/declined/voicemail, final disposition).

---

## 4. HOT-LEAD ROUTING / NOTIFICATION BEST PRACTICE (speed-to-lead is the whole game)

The single most important external finding for feature 2 — the **economics of speed**:

- **The 5-minute rule (MIT / InsideSales):** contacting a lead within **5 minutes** makes you **21× more
  likely to qualify** it than waiting 30 minutes. Responding within **1 minute** lifts conversion ~**391%**
  vs even a 5-minute wait; first-minute leads are **7× more likely to qualify** than first-hour.
- **First-responder wins:** **78% of customers buy from the business that responds FIRST.** After 5 minutes,
  lead quality drops ~**80%**. Industry average response is a dismal **42 hours**; **~73% of leads are never
  contacted at all.** → A hot-lead alert that lands in the team's WhatsApp **within seconds of hangup** is a
  decisive, measurable edge. This is the entire justification for the auto-WhatsApp feature.
- **Round-robin distribution (how to pick WHICH human):** assign sequentially to the next available rep;
  **skip OOO/at-capacity reps**, **pair with lead-scoring** to prioritize high-intent leads, and **define a
  max response SLA** (e.g. 15 min for inbound) tracked weekly. Pure round-robin's weakness: it treats every
  lead equally (a hot enterprise lead can land on a junior). → Famit's `ring_strategy:
  "priority_then_roundrobin"` is the correct hybrid: **priority first** (best closer for hot leads), round-robin
  for fairness/load — exactly the "smarter than naive round-robin" pattern the research recommends.
- **Context-rich alerts (not bare "new lead"):** the alert must carry **name · phone · summary · score ·
  next-action** so the human can act without re-discovery — same context-preservation rule as the live
  whisper. Famit's `hot_lead_alert` template `{{name}}{{phone}}{{summary}}{{score}}` (`plan-handoff-hotlead.md
  §3`) matches this exactly.

### THE FAMIT HOT-LEAD ROUTING DECISION
- **Trigger:** on hangup, `score ≥ rules.hot_score_gte` (per-vendor, reuse the live `interest>=70` flag at
  `caller.py:1297` as the default) → create hot-lead entry + fire WhatsApp **immediately** (speed-to-lead).
- **Recipients:** every handoff-list number with `roles ∋ hot_lead_wa`; send via `whatsapp.send_whatsapp(to,
  "hot_lead_alert", [...])` — reuse `whatsapp.py:248` verbatim (free-form `send_whatsapp_text` is rejected
  with no open 24h window → **must be an approved template**, founder/Meta step GAP-C1).
- **Routing:** `priority_then_roundrobin` so the best closer gets first crack at a hot lead, with round-robin
  fairness as the fallback; respect `hours`; if the LIVE warm-transfer already connected a human, the WA is
  the durable record + backup, not a duplicate ask.

---

## 5. 14-LINE SUMMARY (transfer patterns + triggers + hot-lead routing best practice)
1. **Three canonical transfer shapes exist everywhere:** (A) **blind/cold** = SIP REFER, AI drops, zero
   context; (B) **private warm** = dial-the-human-first, whisper a summary, then bridge the caller in;
   (C) **conferenced warm** = invite the human as a 3rd party, AI can skip-turn and stay available.
2. **Famit should use C as PRIMARY** (dial-human-into-room via `CreateSIPParticipant` over the trunk —
   read-only reuse, **no carrier REFER needed**, sidesteps the unverified Vobiz-REFER gap), with a B-style
   **private spoken whisper** of the summary where possible.
3. **Keep A (SIP REFER) as a lighter fallback** only if Vobiz confirms REFER support — not required, since C works.
4. **Vapi's mode menu is the product blueprint:** blind · warm-with-summary · warm-with-message ·
   wait-for-operator-speech · experimental (hold-audio + voicemail-detect + fallback-plan). Retell = warm +
   private whisper + native SIP; Telnyx = conferenced, AI stays on the line.
5. **NEVER block the turn-loop:** speak a one-line bridge sentence, dial the human off-loop, then merge.
6. **Handoff TRIGGERS (copy this list, not "AI got confused"):** (1) explicit "talk to a human"; (2) **hot /
   buying-signal** = crosses qualification threshold X → the sales trigger; (3) **sentiment escalation** =
   cumulative-frustration threshold; (4) policy/expertise/licensing gap; (5) bounded repeated-confusion (after
   N clarifies). Telnyx's anti-pattern: never hand off "because the AI is confused."
7. **Mid-call hot signal is the one new detection** (GAP-B1): LLM emits `lead_is_hot` from buying-intent
   phrases (reuse `_CLOSE_*` banks `agent.py:280-312`); post-call hot needs no new code (`interest>=70` live).
8. **CONTEXT PRESERVATION is the defining best-practice** — pass intent history + extracted entities + summary
   to the human on EVERY handoff (spoken whisper AND the WhatsApp text, belt-and-braces). Famit already
   produces this payload (`_summarize_transcript`, `_wa_draft_followup_text caller.py:1492`).
9. **NO-ANSWER FALLBACK LADDER (never a dead drop):** ring next number by strategy (timeout ~25s, ~2 attempts,
   skip out-of-hours) → hold-audio/dial-tone while ringing → voicemail-detect (don't bridge a machine) →
   after-hours/nobody → `wa_only` + logged callback + hot-lead WA; audit every attempt.
10. **SPEED-TO-LEAD is the entire case for the WhatsApp alert:** within 5 min → **21× more likely to qualify**;
    within 1 min → **~391% conversion lift / 7× qualify**; **78% buy from whoever responds FIRST**; quality
    drops ~80% after 5 min; industry average is 42h and ~73% of leads are never contacted. A WA alert in
    **seconds** is a decisive, measurable edge.
11. **WHICH human = round-robin DONE RIGHT:** sequential assignment but **skip OOO/at-capacity**, **pair with
    lead-scoring** (hot leads to the best closer), define a response SLA, track weekly. Naive round-robin's flaw
    = treats every lead equally. → Famit's **`priority_then_roundrobin`** is the correct smarter hybrid.
12. **ALERTS MUST BE CONTEXT-RICH, not bare "new lead":** name · phone · summary · score · next-action so the
    human acts without re-discovery — matches the `hot_lead_alert {{name}}{{phone}}{{summary}}{{score}}` template.
13. **Hot-lead routing decision:** on hangup if `score ≥ per-vendor hot_score_gte` (default = live `>=70`),
    create the hot-lead + fire `send_whatsapp(to,"hot_lead_alert",[...])` (reuse `whatsapp.py:248`) to every
    `hot_lead_wa` number immediately; **must be an approved template** (no 24h window → GAP-C1, founder/Meta step).
14. **SAFETY (unchanged):** the human leg dials over the trunk = **read-only reuse** (never edit trunk/dispatch/
    `agent.py`); meter+wallet-gate the human leg against the resolved tenant; audit every transfer + every WA;
    outbound regression-gate `G` (famit-agent active + a real Riya test call) **before+after every step**.

---

## 6. OPEN GAPS / FOUNDER (non-code) BLOCKERS — carried from research
- **GAP-A1 (carrier):** does **Vobiz honour SIP REFER**? If not, Pattern A is out → Pattern C (dial-into-room)
  needs no REFER, so the build does **not** depend on this — but verify before relying on REFER as a fallback.
- **GAP-B1:** **mid-call hot signal** (LLM `lead_is_hot` tool-call) so live transfer fires on *getting* hot,
  not only post-call. Post-call hot reuses `interest>=70` — no new detection.
- **GAP-B2 / per-vendor thresholds:** `transfer_on.hot_score_gte` (default 80 for live transfer; 70 for the
  WA alert) configurable per vendor on the Business Brain `handoff.rules`.
- **GAP-C1 (Meta, founder):** register the **`hot_lead_alert` WhatsApp template** + finish Meta onboarding so
  the team-notify can send cold (no 24h window with the team). WA is dormant until creds land (graceful no-op).
- **GAP-C2:** handoff-team members must be **WA-reachable / opted-in** (per-number `wa_optin`/`whatsapp`).
- **GAP (UX):** a per-vendor **hold-audio asset** + a localized bridge/whisper line bank (Hinglish) for the
  warm intro; voicemail-detection mode to avoid bridging into a machine.

## 7. EVIDENCE INDEX
- **Box (read-only, verified this session):** `transfer_sip_participant` at
  `/opt/capsy-agent/.venv/.../livekit/api/sip_service.py:804` (livekit-api 1.1.0); hot flag `caller.py:1297
  x["hot"]=best>=70`, hot WA hooks `caller.py:1359/1611/1946` fire on `interested or score>=70`; WhatsApp send
  `whatsapp.py:233 send_whatsapp_text` (free-form/24h) + `:248 send_whatsapp` (template/cold); **no existing
  handoff-number list** (grep `handoff_number|human_number|transfer_number|warm_transfer|transfer_to_human` = 0 hits).
- **Web sources (cited):**
  - Telnyx — *AI-to-human handoff for voice AI agents: a practical guide* (cold vs private-warm vs conferenced;
    triggers; "not when the AI gets confused"; context-card). https://telnyx.com/resources/ai-to-human-handoff-voice-ai
  - Vapi — *Call Forwarding* docs (blind · warm-summary · warm-message · wait-for-operator · experimental
    hold-audio+voicemail+fallbackPlan; SIP REFER via `sipVerb`). https://docs.vapi.ai/call-forwarding
  - Retell AI — *How AI Voice Agents Are Perfecting the Warm Transfer* / *Warm vs Cold Transfer* (warm + native
    SIP + private whisper, full context intact). https://www.retellai.com/blog/how-ai-voice-agents-are-perfecting-the-warm-transfer · https://www.retellai.com/blog/effortless-handoffs-with-retell-ais-warm-transfer-feature
  - Gnani / Haiptik / Shunya — *real-time sentiment escalation* (cumulative-frustration threshold; ~40%
    escalation+handle-time reduction; context passed on handoff). https://www.gnani.ai/resources/blogs/how-real-time-sentiment-detection-works-in-voice-ai · https://www.haptik.ai/blog/voice-ai-real-time-sentiment-analysis
  - Speed-to-lead (5-minute rule, 21×, 391%, 78%-first-responder, 42h average): Kixie
    https://www.kixie.com/sales-blog/speed-to-lead-response-time-statistics-that-drive-conversions/ · Chili Piper
    https://www.chilipiper.com/article/speed-to-lead-statistics · CaseyResponse
    https://caseyresponse.com/blog/lead-response-time-statistics
  - Round-robin best practice (skip OOO/at-capacity, pair with scoring, SLA, naive-RR flaw): LeanData
    https://www.leandata.com/blog/round-robin-lead-distribution-best-practices/ · RevenueTools
    https://www.revenuetools.io/blog/round-robin-lead-routing
- **Companion design docs:** `plan-handoff-hotlead.md` (box primitive map), `plan-vendor-modules.md` (handoff
  -list storage on Business Brain), `plan-rag-context.md` (context layer), `INBOUND-PIPELINE-MASTER-PLAN.md §5/Phase7`.
