# Production Inbound Voice-AI Patterns — Research + Application to Famit's Inbound Brain

> **Status:** READ-ONLY research/architecture. No code, no deploy, no git. Writes only this design doc.
> **#1 CONSTRAINT (non-negotiable):** the live OUTBOUND earner — `agent.py` / `capsy` worker /
> `famit-agent.service` / outbound trunks `ST_fmtVmNJmpzKa`+`ST_LH8ighJJtHSi` — is **NEVER touched,
> restarted, or reconfigured**. Every inbound capability here is **additive + isolated**: a separate
> worker persona (`agent_name="manager"` / its own entrypoint), a separate inbound trunk + dispatch
> rule, separate systemd unit, no edits to the shared outbound media/signaling path. The earner was
> *just* restored after an infra mistake — design accordingly (backup-first, regression-gate outbound
> healthy before+after, restart ONLY the inbound unit).
>
> **Scope:** web-researched best-practice patterns for production inbound voice AI, mapped onto the
> founder's two-mode inbound vision: **(A) CUSTOMER INBOUND** (returning lead → continue prior call;
> new caller → disambiguate campaign → run the sales conversation like an outbound call) and
> **(B) MANAGER INBOUND** (designated numbers → authenticate → conversational command execution).
> Companion design docs already on disk: `aim-voice-telephony.md` (state machine S0–S_END for mode B),
> `aim-nlu-policy-security.md` (NLU + risk + PIN), `aim-inbound-wiring-plan.md` (SIP/trunk/dispatch),
> `inbound-gap-analysis.md` (what's built vs broken). **THIS doc adds the missing half: mode A
> (customer sales inbound) and the unified router that decides A-vs-B at call start.**

---

## 0. THE FIVE RESEARCHED PATTERNS (what the best production systems do)

### Pattern 1 — ROUTING a single line to different modes (DID / caller-ID / IVR)
**Finding.** Modern inbound systems (Vapi, Retell, Bland, contact-center AI) route by, in order of
reliability: **(a) DID / dialed-number (DNIS)** — the cleanest signal: a dedicated number per
purpose/campaign auto-selects the flow with zero ambiguity (Retell/Bland connect *any* DID via SIP
trunk and bind it to a specific agent/flow); **(b) caller-ID (ANI) lookup against CRM** — "is this a
known contact?" branches returning vs new; **(c) a short natural-language disambiguation turn**
("How can I help?") only when DID+ANI are insufficient. The industry-wide shift is **away from rigid
"press 1" IVR menus toward open-ended natural-language intent capture** — the agent asks one open
question and an LLM classifies, instead of forcing a tree. **Best practice = layer them:** DID first
(deterministic), ANI second (context), NL third (fallback). Caller-ID is used for *routing/context*,
never for *trust*.

**Applied to Famit.** A clean two-DID design removes almost all ambiguity:
- **Manager DID** (designated number) → mode B (AI Manager command brain). Dispatch rule routes it to
  `agent_name="manager"` already (per `aim-inbound-wiring-plan.md`).
- **Customer/campaign DID(s)** → mode A (sales). If the founder issues **one DID per active campaign**,
  the dialed number *is* the campaign — zero disambiguation needed (the strongest pattern). If only one
  shared customer DID exists, fall back to ANI-lookup + a one-turn NL "which property/campaign?".
- The router runs INSIDE the inbound worker at S0/S1 (cheap PG/file lookup), so a single trunk can
  serve both modes if needed — but **separate DIDs are the recommended production shape** (deterministic,
  auditable, and it keeps the manager line unlisted/private).

### Pattern 2 — CALLER IDENTIFICATION + history continuity ("screen pop")
**Finding.** The defining feature of good inbound CX is **context-at-answer**: the moment a call
connects, the system resolves the ANI to a CRM record and "pops" name, account status, call history,
and *recommended next action* — so the agent (human or AI) **picks up where the last interaction left
off** instead of starting cold. Retell exposes this as **call-history + custom attributes + dynamic
variables** injected at call start; contact-center "Agent Assist" pops a **conversation summary +
customer context + next-best-action**. For AI agents specifically, the prior-call **summary and
extracted entities** (not the raw 10-minute transcript) are injected into the system prompt so the
agent can say *"last time you asked about the 2BHK and wanted a callback"* without re-reading everything.

**Applied to Famit.** This maps **directly** onto code that already exists — no new data model:
- `_resolve_contact_by_phone(phone)` (`caller.py:1465`) already returns
  `{tenant_id, name, campaign_id, campaign_name}` by walking the most-recent CALL to that number, then
  falling back to a stored LEAD. This is the screen-pop resolver, already used for WhatsApp inbound.
- `_crm_mod.get_timeline(org, contact_id)` (`contacts_timeline`, `caller.py:2336`) returns the full
  chronological interaction history; `next_best_action` (`/contacts/{phone}/nba`) gives the deterministic
  NBA. These are the **prior-call context + recommended-continuation** pop.
- The prior call's **transcript** lives at `var/transcripts/<room>.json` joined via the call record's
  `room` field (`call_detail`, `caller.py:3198`); its `summary` / `next_action` are already extracted
  (used today by `_wa_draft_followup_text`). **Inject the SUMMARY + next_action, NOT the raw transcript**,
  into the inbound sales agent's opener context (token-budget + latency).

### Pattern 3 — INTENT DISAMBIGUATION for a NEW caller (which product/campaign)
**Finding.** For an unknown caller (number on a banner/brochure), the production pattern is a **single
open-ended NL turn, not a menu**: "Hi, thanks for calling — which property are you calling about?" then
LLM-classify the spoken answer against the *known set* (active campaigns). Two refinements: **(i)** if
there's exactly ONE active campaign, skip the question entirely and assume it; **(ii)** disambiguate
**deterministically** — the LLM extracts the spoken reference, but a code resolver matches it to the
active-campaign list and returns `matched` / `ambiguous(candidates)` / `not_found`, so the model never
"guesses" which campaign (same discipline as `resolve_campaign` in `aim-nlu-policy-security.md §3.4`).
Best-of-both: **prefer the DID** (one number per campaign) so disambiguation is usually unnecessary.

**Applied to Famit.** `list_campaigns(tenant)` (`caller.py:1188`) is the known-set source. Logic at S1
of mode A:
1. If DID maps to a specific campaign → use it (no question).
2. Else if tenant has exactly 1 active campaign → use it (no question).
3. Else ask ONE open question, STT the answer, resolve deterministically against `list_campaigns`;
   on `ambiguous` ask once more naming the 2–3 candidates ("Urban Nest ya Satellite?"); on `not_found`
   offer the top campaign or take a callback/name+number.

### Pattern 4 — CONVERSATIONAL SLOT-FILLING + confirm-before-action
**Finding (research-grounded).** Production multi-turn agents use a **finite-state slot tracker**: each
required parameter is a slot in state `unfilled | filled | conflict`; the planner asks for the **single
most-important missing slot per turn** (never a barrage), and applies a **stopping rule** — execute only
when all required slots are `filled` and consistent. Two hard guardrails from the literature: **(1) an
explicit confirmation gate before any side-effecting action** (order/booking/spend) — read the
parameters back and require a yes; **(2) do NOT ask for confirmation you don't need** — if all slots are
already known, don't re-prompt (over-confirmation kills UX). A ReAct-style "ask vs answer" loop with the
FSM deciding when enough is gathered is the validated pattern.

**Applied to Famit.** Mode B already encodes exactly this (the `CommandMachine` S4 capture-intent loop +
S7 confirm in `aim-voice-telephony.md`): NLU returns `missing_fields[]`; the machine asks the ONE
missing slot (`§13` "ask only the minimum"), and S7 reads back amount+scope before any side effect. The
research **validates** the existing design. The new work is to apply the **same slot-fill discipline to
mode A** for the few structured sub-tasks a sales call needs (book a site visit → slots {date, time,
property}; schedule a callback → {when}; capture name for a brand-new caller). Use one shared slot-fill
helper across both modes; keep open sales chat free-form (that's the campaign brain), and only switch to
strict slot-fill when the caller commits to a structured action (booking/callback).

### Pattern 5 — SECURITY for phone-based COMMAND systems (the must-haves)
**Finding (the load-bearing one for mode B).** Caller-ID/ANI is **trivially spoofable** and is
"viewed as worthless" for authentication in the VoIP community — entire websites exist to place calls
with any caller-ID. Spoofing powers impersonation, account takeover, and financial fraud; vishing was
**>60% of phishing IR engagements in Q1 2025** and AI voice cloning needs **~3 seconds of audio** to
fake a voice — so **voice biometrics alone are also insufficient**. The mandated controls for a system
that *executes commands* over the phone:
- **Caller-ID is a HINT for routing, NEVER a credential.** Possession of the line must be proven by a
  **shared secret the caller knows / out-of-band factor** — a PIN, or better an OTP to a pre-registered
  channel. (Research: "system employs a password prior to granting access"; "combine voice auth with
  SMS codes or app-based approvals"; "callback verification on a pre-registered number" is the single
  most-cited control.)
- **PIN via DTMF (keypad), not spoken**, where possible — DTMF digits arrive as signaling events and
  never transit STT or the call recording (leak-proof); spoken-PIN is a fallback with the recording
  **paused** around capture.
- **Step-up per risky action** (not one login that authorizes everything): a fresh, scoped, short-TTL
  authorization per money/bulk/destructive command.
- **Lockout + rate-limit** after N wrong PINs (per number AND per user, so a spoofed ANI can't grind),
  **never reveal** whether the user exists vs the PIN is wrong (anti-enumeration), and **reset only
  out-of-band** (dashboard/OTP) — never talk your way to a new PIN in-band.
- **Full immutable audit** with the *verified* identity as actor; **never log the PIN/OTP value**; mask
  spoken secrets to `****` in transcript + recording.
- **STIR/SHAKEN** caller-attestation is the carrier-level mitigation (where available) — a defense-in-
  depth signal, not a replacement for the PIN.

**Applied to Famit.** Mode B's existing design (`aim-voice-telephony.md §2.5/§4`,
`aim-nlu-policy-security.md §4`) **already implements every must-have**: caller-ID = hint only, PIN
proves possession BEFORE any business data, DTMF-preferred + recording-suppressed spoken fallback,
Argon2id per-user PIN + pepper, per-action fresh scoped step-up, PG-authoritative lockout, uniform
"PIN didn't match", out-of-band reset, immutable audit with PIN masking. The research confirms this is
correct and complete — **the gap is in mode A, not mode B's security**, and in *wiring* mode B's
security to the per-vendor registry instead of the single hardcoded caller (gap-analysis P2).

---

## 1. THE UNIFIED ROUTER (decide A vs B at call start — the missing top layer)

A single inbound entrypoint classifies the call in S0/S1 using DID-first, ANI-second, NL-third:

```
S0  answer; read SIP attrs: caller_id = sip.phoneNumber ; dialed_did = sip.trunkPhoneNumber
S1  ROUTE:
      if dialed_did == MANAGER_DID  OR  registry.is_authorized_manager(caller_id):
            -> MODE B (AI Manager): hand to CommandMachine (PIN gate FIRST, then commands)
      else  (customer line):
            contact = _resolve_contact_by_phone(caller_id)        # screen-pop resolver (caller.py:1465)
            if contact.campaign_id (returning lead, we called them before):
                  -> MODE A "RETURNING": load campaign brain + prior-call summary/NBA -> continue
            else (new caller, number off a banner):
                  campaign = disambiguate_campaign(dialed_did, list_campaigns(tenant), one_NL_turn)
                  -> MODE A "NEW": load that campaign brain -> run sales like an outbound call
```
**Safety ordering (critical):** the manager check is by **DID OR registry membership**, but mode B then
**still demands the PIN** (caller-ID never grants access). A spoofed manager caller-ID that hits the
manager DID gets the PIN prompt and nothing else. A customer-line call never reaches command execution
regardless of caller-ID. This keeps the two trust domains structurally separate.

**Recommended DID topology (cleanest, most production-grade):**
- 1 **private** Manager DID → mode B only.
- 1 **public** Customer DID **per active campaign** (banner/brochure prints the per-campaign number) →
  mode A with the campaign pre-selected by DID (no disambiguation turn). Falls back to shared-DID +
  ANI/NL if per-campaign numbers aren't available.

---

## 2. MODE A (CUSTOMER SALES INBOUND) — the new build, reusing the outbound brain verbatim

The founder's requirement: a customer inbound call must run the sales conversation **exactly like an
outbound call**, using the campaign script/knowledge — and for a returning lead, *continue* the prior
conversation. The outbound earner already does the hard part; mode A **reuses it without touching it**:

| Need | Reuse (already on box) | New glue (additive) |
|---|---|---|
| Campaign sales brain | `_load_campaign(cid)` → `{fields, system_prompt}` (`agent.py:142`) + `build_system_prompt(fields)` (`prompt.py:254`) — the SAME negotiation ladder / objection bank the outbound agent renders | inbound worker calls the SAME builder; the ONLY difference vs outbound is *where campaign_id comes from* (lookup, not dispatch metadata) |
| Returning-caller identity + history | `_resolve_contact_by_phone` (`caller.py:1465`); `_crm_mod.get_timeline` / `next_best_action`; prior transcript `summary`+`next_action` (`var/transcripts/<room>.json`) | inject prior **summary + NBA** (not raw transcript) into the opener context: *"Pichli baar aapne 2BHK ke baare me poocha tha, aur callback maanga tha…"* |
| New-caller campaign disambiguation | `list_campaigns(tenant)` (`caller.py:1188`) | DID→campaign map; else 1-campaign auto; else one NL turn + deterministic resolver |
| Tuned low-latency voice | the SAME `AgentSession` kwargs as outbound (Sarvam STT `language=unknown`, Groq scout, ElevenLabs flash, preemptive_generation, endpointing/barge-in) — `aim_voice_agent.py` already copies these verbatim | reuse the inbound worker that already exists; mode A is a different *system prompt + opener*, same pipeline |
| Lead/call logging | `record_call` / `_update_lead_after_call` / transcript write on shutdown (`agent.py`) | the inbound call WRITES a call record (so a future inbound/outbound sees THIS interaction) + updates the lead score/outcome, exactly as outbound does — closing the loop |

**Net for mode A:** it is the outbound `entrypoint` logic with (1) campaign_id resolved by phone/DID
instead of dispatch metadata, (2) a returning-caller **history-aware opener** prepended, and (3) the
call logged back so the contact-360 stays continuous. It needs **no PIN** (it's a customer, not a
commander) and **no command/risk engine** — it's a pure sales conversation. It must still respect
**compliance** (don't keep a STOP/opt-out lead engaged beyond their request) and **DLT/recording-consent**.

---

## 3. WHAT THE FOUNDER IS LIKELY MISSING (deep-reasoning surfacing — for a complete pipeline)

These are gaps not yet covered by the existing docs; each is required for production, recorded so the
build doesn't forget them:

1. **Per-campaign customer DID provisioning** — the cleanest router needs a DID per campaign (or at
   least one customer DID separate from the manager DID). Procuring/mapping DIDs (Vobiz) is a founder/
   carrier step, not code. Without it, every new caller needs the NL disambiguation turn.
2. **"New caller, brand-new number" capture** — a caller off a banner who is NOT a lead yet has no CRM
   row. Mode A must **create the lead** (name asked in-call + ANI) and attach it to the resolved
   campaign, so the very first inbound becomes a tracked lead (else the sale is invisible to the panel).
3. **Inbound concurrency / barge-storm** — multiple simultaneous inbound calls hit ONE worker; confirm
   the inbound worker's job concurrency and that it doesn't share a process/limit with the outbound
   earner (separate unit, separate port 8091 — already designed; verify capacity at activation).
4. **Returning-caller WITHIN calling hours / DND** — a returning lead calling US is fine, but mode A must
   not *initiate* follow-up outreach that violates DND; inbound answering is consent-by-action, but any
   scheduled callback created in-call must respect the compliance window.
5. **Mode-switch within a call** — a manager might call the customer line, or a customer might land on
   the manager line. The router decides ONCE at S1 by DID+registry; document that there is **no in-call
   escalation from customer→command** (a customer can never reach command execution), but a manager on
   the wrong line is simply told to use the manager number. Keep the trust domains hard-separated.
6. **Recording + transcript persistence for inbound** (gap-analysis P1) — inbound today has a `_NullRecorder`
   and writes JSONL, not the rich tables; both modes need transcript+recording captured and visible in
   the panel (mode A into the contact-360/call history; mode B into `ai_manager_sessions`).
7. **Resilient STT (gap-analysis P0)** — the inbound worker currently dies on a transient STT WS blip
   (no FallbackAdapter/retry) → total silence. This is the **#1 blocker for ANY inbound to work** and
   precedes everything in this doc. Fix (FallbackAdapter + connect-retry + never-silent guard) first.
8. **Human handoff path** — when the sales AI can't answer or the caller insists on a human, define the
   transfer/callback (warm-transfer with caller-ID preserved per Pattern 2, or a logged callback task).
9. **Greeting/identity disclosure + consent** — TRAI/DLT: the inbound agent should identify as an
   automated assistant and honor recording-consent, same posture as outbound's configurable disclosure.
10. **Outbound regression gate automated** (gap-analysis P0.4) — assert `famit-agent` active + a test
    outbound call works BEFORE and AFTER any inbound change. Non-negotiable given the recent incident.

---

## 4. BUILD ORDER (precedence; each additive + reversible; outbound untouched)
1. **P0 inbound-works-at-all** (from `inbound-gap-analysis.md`): resilient STT (FallbackAdapter + retry)
   + never-silent guard + the SIP wiring (`aim-inbound-wiring-plan.md` units 1–6) + outbound regression
   gate. *Nothing below matters until a call is answered and heard.*
2. **Unified router** (§1): DID+ANI+NL classification at S0/S1; manager-DID→mode B, customer→mode A.
3. **Mode A returning-caller** (§2): `_resolve_contact_by_phone` + prior summary/NBA opener + reuse
   `build_system_prompt`; log the call back + update the lead.
4. **Mode A new-caller** (§2/§3.2): disambiguate campaign (DID→1-campaign→NL resolver) + create the lead.
5. **Mode B registry wiring** (gap-analysis P2): replace the hardcoded `AUTHORIZED_CALLER` with
   `registry.lookup` per-vendor; per-vendor PIN; tenant isolation. (Mode B's *security spine* is already
   designed — this is wiring it to multi-vendor.)
6. **Persistence/recording** (gap-analysis P1): rich PG session rows + LiveKit Egress recording (paused
   around PIN) + panel history for both modes.
7. **Polish:** slot-fill helper shared by both modes (booking/callback), human-handoff/warm-transfer,
   compliance/consent/DLT, latency verification.

---

## 14-LINE SUMMARY (best-practice patterns + security must-haves)
1. Route a single inbound line by **DID-first → ANI-second → one open NL turn-third**; the industry has
   moved off rigid "press-1" IVR to **open-ended NL intent capture**.
2. The **cleanest production shape is a dedicated DID per purpose/campaign** — the dialed number selects
   the flow deterministically (private manager DID + public per-campaign customer DIDs).
3. **Caller-ID identifies and brings context, but NEVER authenticates** — it is trivially spoofable and
   "worthless" for trust in VoIP.
4. **Screen-pop / context-at-answer** is the defining inbound feature: resolve ANI→CRM and inject prior
   **summary + next-best-action** (not the raw transcript) so the agent continues, not restarts.
5. For a **new caller, ask ONE open question** ("which property?") and **resolve deterministically**
   against the known campaign set — the LLM extracts, code matches (`matched/ambiguous/not_found`).
6. If there's exactly one active campaign (or the DID implies one), **skip the question** — don't
   over-ask.
7. **Slot-filling = an FSM with per-slot states**; ask the **single most-important missing slot per
   turn**; **execute only when all required slots are filled + consistent**.
8. **Explicit confirm-before-action** (read parameters back, require yes) is a mandatory guardrail for
   any side-effecting/spend action — but **don't confirm what you already fully know**.
9. **Security must-have:** prove line-possession with a **PIN/OTP the caller knows**, **before** any
   sensitive data — caller-ID alone grants nothing.
10. **DTMF-PIN beats spoken-PIN** (digits as signaling events never hit STT/recording); spoken-PIN only
    as fallback with **recording paused** around capture; mask secrets to `****` everywhere.
11. **Step-up per risky action** (fresh, scoped, short-TTL) — one login must NOT silently authorize every
    subsequent money/bulk/destructive command.
12. **Lockout + dual-key rate-limit** (per number AND per user) after N fails, **uniform "PIN didn't
    match"** (anti-enumeration), and **out-of-band-only PIN reset** (never in-band).
13. **Immutable audit** with the *verified* identity as actor; **STIR/SHAKEN** caller-attestation +
    callback-to-registered-number as defense-in-depth; voice biometrics alone are NOT sufficient
    (3-sec AI voice cloning).
14. Famit status: **mode B's security spine already satisfies every must-have** (PIN-first, DTMF-pref,
    Argon2id+pepper, per-action step-up, PG lockout, masked audit) — the real gaps are **(a) the P0
    inbound-silence STT fix, (b) the unified A/B router, (c) mode-A customer-sales reusing the outbound
    `build_system_prompt` + `_resolve_contact_by_phone` history, and (d) wiring mode B to the per-vendor
    registry** — all additive, with the outbound earner never touched.

## SOURCES
**Web (patterns + security):**
- Retell AI — platform/SIP-trunk-any-DID, AI-IVR, intent detection, **call-history + warm-transfer
  caller-ID + components** (returning-caller context + flow routing): retellai.com, retellai.com/glossary/ai-intent-detection,
  retellai.com/changelog/cf-components-warm-transfer-caller-id-call-history-more
- Bland / Vapi — inbound+outbound agents over SIP, any carrier number, prompt-to-production: bland.ai, vapi.ai
- Cresta — "Three Pillars of Voice Integration" + "How AI Contact Centers Identify Caller Intent"
  (warm/cold/conference transfer with context; intent routing): cresta.com/blog, cresta.com/guides
- Landis / Ringover — **screen-pop** (caller info/history/account at answer from CRM/CTI):
  landistechnologies.com, ringover.co.uk/cti-screen-pop
- Decagon / Rasa / AssemblyAI / Aircall — conversational IVR vs menus, intent mapping, open-ended NL:
  decagon.ai/blog/conversational-ivr, rasa.com/blog, assemblyai.com/blog/ai-voice-agents, aircall.io/blog
- **Slot-filling / confirmation (research):** arxiv 2606.10315 (LLM-as-judge blind spots in multi-turn
  transaction agents — explicit-confirmation gate), emergentmind.com (multi-turn tool-calling LLMs;
  clarifying agent; FSM slot tracker), arxiv 2503.22458 (survey of multi-turn agent eval), daily.co
  benchmarking LLMs for voice agents.
- **Security (caller-ID spoofing / vishing / controls):** SecureLogix threats/spoofing, Vonage caller-ID
  spoofing, Enea voice-fraud, Keepnet/CloudEagle/Specops/Vectra/Group-IB/Kymatio (vishing 2025–2026,
  >60% of phishing IR, 3-sec voice cloning, STIR/SHAKEN, callback-to-registered-number, MFA/OTP).
**Live box (read-only, 168.144.153.145):** `agent.py` (`_load_campaign`:142, dispatch-metadata campaign
context:351-396, `build_system_prompt` import:27), `prompt.py` (`build_system_prompt`:254, `GODREJ_FIELDS`:389),
`caller.py` (`_resolve_contact_by_phone`:1465, `list_campaigns`:1188, `contacts_timeline`:2336,
`call_detail`:3198, `save_campaign`:1153). **Companion design docs:** `aim-voice-telephony.md`,
`aim-nlu-policy-security.md`, `aim-inbound-wiring-plan.md`, `inbound-gap-analysis.md`, `inbound-agent-notes.md`.
</content>
</invoke>
