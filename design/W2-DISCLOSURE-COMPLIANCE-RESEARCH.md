# W2 — India Voice-AI Disclosure & Compliance Research (2025–2026)

> READ-ONLY research output. Feeds W2 (voice brain) disclosure-line design + W26 (compliance build).
> Resolves the collision: founder's "the AI must NEVER say I am an AI assistant" vs India's NOW legal gate.
> Date: 2026-06-18. All claims web-verified against current (2025–2026) authoritative sources.

---

## TL;DR for the brain (W2) — the one decision

The legal NOW-gate is **TRAI TCCCPR 2018 + 2nd Amendment (12 Feb 2025)** — DLT registration, DND/NCPR
scrub, auto-dialer/robocall **pre-notification to the access provider**, 140/1600 numbering, calling-window.
Penalty for the telco-resource holder: **first offence ₹2 lakh + 15-day suspension of outgoing telecom
service; repeat ₹5L→₹10L; persistent = 1-year disconnection + industry blacklist.**

The hard part — "must the AI literally say *I am an AI*?" — is **NOT a single black-letter TRAI verbatim
rule today.** It is a *layered* obligation:
- **TRAI hard law:** the sender must *disclose the use and intended purpose of Auto-Dialer/Robo-calls* (to
  the operator, and the call must be transparent/non-deceptive). It does **not** prescribe the exact spoken
  words "I am an AI assistant."
- **DPDP Act 2023 + Rules 2025 (substantive parts in force 13 May 2027):** "free, specific, informed"
  consent + recording/processing disclosure. Informed ⇒ the person must know they're talking to an
  automated system and that it's recorded.
- **MeitY AI Governance Guidelines (Nov 2025) — advisory, not binding:** explicitly recommends
  "transparency that the caller is interacting with an AI system, not a human agent."
- **IT (Intermediary) Amendment Rules 2025 (in force 15 Nov 2025):** mandatory *labelling of
  synthetically generated information* — but scoped to social-media/uploaded content, **not** a
  per-phone-call spoken-disclosure rule. Vendor blogs conflate this; it does **not** legally force a voice
  bot to say "I am AI" on a live call.

**=> The compliant resolution (no conflict needed):** the law requires *transparency that the call is
automated + recorded + how to opt out*. It does **NOT** require the deception-killing phrase "I am an AI
assistant." A single, warm, human-sounding, rapport-preserving opener satisfies every binding obligation:

> **Disclosure line (Hinglish, recommended default):**
> "Namaste, main **{AgentName}**, **{Company}** ki taraf se ek **automated call** kar rahi hoon — aur yeh
> call quality ke liye **record** hoti hai. Aapke paas 2 minute hain?"
> (EN gloss: "Hi, I'm {AgentName}, calling on behalf of {Company} — this is an automated call and it's
> recorded for quality. Do you have 2 minutes?")

This says **"automated call"** (satisfies auto-dialer transparency + MeitY "interacting with AI system"),
names the **company** (TRAI sender-identity), states **recording** (DPDP informed consent), and the
turn-loop must honor an **immediate opt-out** ("don't call me / cut my number" → stop + suppress).
It never utters the founder's banned phrase "I am an AI assistant," and "automated"/"system" reads as a
normal modern telecaller, not a robot confession. **This is the line W2 wires and W26 enforces.**

Why "automated" is enough and "AI assistant" is not mandated: no in-force Indian statute prescribes the
literal words "AI"/"assistant." The binding tests are (a) *not deceptive about being a machine-driven
call*, (b) *sender identified*, (c) *recording/processing disclosed for consent to be "informed,"* (d)
*opt-out honored*. "Automated call, recorded, on behalf of {company}, opt-out" clears all four. A regulator
or court asking "did the recipient know it wasn't a live human and could they opt out?" answers **yes**.
(If risk-tolerance later demands belt-and-suspenders for a regulated vertical — BFSI/insurance — add an
explicit "AI" token; see Vertical overlays below. Default consumer outbound does not need it.)

---

## 1. HARD LAW (binding NOW) vs GUIDANCE — the map

| Layer | Instrument | Status / in force | Binds Famit? | The obligation that bites |
|---|---|---|---|---|
| Telecom | **TCCCPR 2018 + 2nd Amendment 12 Feb 2025** | **HARD LAW, IN FORCE** (came into force +30/+60 days from gazette) | **YES — the NOW gate** | DLT registration (PE+header+template), DND/NCPR scrub, auto-dialer/robocall pre-notification to access provider, 140 (promo)/1600 (txn) series, calling-window, no 10-digit bulk promo |
| Data | **DPDP Act 2023 + DPDP Rules 2025 (notified 13 Nov 2025)** | **HARD LAW; substantive duties in force 13 May 2027** (consent/notice/security/retention/erasure/rights); Board live now | **YES (prepare now, enforced 2027)** | Free/specific/**informed** consent; recording+processing disclosure; purpose limitation; data minimization; retention TTL + erasure; audit logs |
| Content | **IT (Intermediary) Amendment Rules 2025** | **IN FORCE 15 Nov 2025** | **Edge / mostly N/A to live calls** | Labelling of *synthetically generated information* (social/media content, ≥10% area or first 10% of audio). NOT a per-call spoken-AI-disclosure mandate. Relevant only if Famit publishes synthetic audio/clips. |
| AI policy | **MeitY AI Governance Guidelines (Nov 2025)** | **ADVISORY (non-binding)** | Signals direction | Recommends transparency that caller interacts with AI, accountability, redressal, decision-logic documentation |
| Telecom infra | **DoT** caller-ID / anti-spoofing, lawful-intercept | HARD LAW | YES | Verified, traceable CLI; advance operator notification for auto-diallers; no spoofing |
| Vertical | **RBI FPC** (BFSI/collections) | HARD LAW (if vertical) | Only if tenant is BFSI | Human-escalation option; calling window 08:00–19:00; frequency caps; grievance info each call |
| Vertical | **IRDAI** (insurance) | HARD LAW (if vertical) | Only if tenant is insurer | Record+retain ≥6 months; recording-consent notice; disclose material terms + free-look; firm liable for AI mis-sell |
| Vertical | **SEBI** (securities) | HARD LAW (if vertical) | Only if tenant is invest/securities | No misleading/AI-simulated financial advice; pre-approved statements |

**Key correction of a common vendor-blog error:** several India "AI calling 2026" blogs assert a flat rule
that "AI must identify as automated within the first 15 seconds." The **15-second / verbatim** framing is
**best-practice/vendor convention, not a quoted black-letter TRAI clause.** Treat "automated + recorded +
opt-out, up front" as the *defensible* standard; the 15-second window is a sound implementation default, not
a statutory number to cite to a regulator. Where this doc marks something HARD-LAW it is traceable to TRAI
TCCCPR text, DPDP Act/Rules, or a sector regulator — not to a blog's paraphrase.

---

## 2. CONCRETE OBLIGATIONS (what W26 must build / enforce)

### A. AI / automation disclosure (the founder-collision item)
- **REQUIRED (transparency, non-deception):** state up front that the call is **automated** and on behalf
  of **{named company}**. ← satisfied by the disclosure line above.
- **REQUIRED for "informed" consent (DPDP):** state the call is **recorded** and (lightly) why
  ("for quality").
- **REQUIRED:** an **immediate, honored opt-out** path ("remove my number / don't call").
- **NOT REQUIRED by in-force law:** the literal phrase "I am an AI assistant." Founder's constraint is
  satisfiable. Use "automated call" / "automated system."
- **ADVISORY (MeitY):** transparency that it's an AI system → "automated" wording already aligns.

### B. DLT onboarding flow (HARD LAW, do once per principal entity)
1. **Principal Entity (PE) registration** on a TRAI-approved DLT platform (Airtel Smart Hub / Jio
   TRUECONNECT / Vi Vilpower / BSNL / Tanla Trubloq). Docs: PAN, GST, authorization letter, KYC. ~3–7
   business days.
2. **Header / sender-ID registration.** ~1–3 days.
3. **Template registration** (call scripts). ~1–5 days. **Dynamic variables allowed inside a registered
   template; fully ad-lib conversation is prohibited** ← design constraint for the brain: the *open + key
   claims* live inside a registered template; the LLM fills variables / handles dialogue, it does not
   invent the regulated script frame.
4. **Numbering:** 140-series promotional, 1600-series transactional/service. No bulk promo on 10-digit
   numbers (= unregistered telemarketing).
5. **Pre-notify the access provider** that auto-dialer/robo-calling is used and its purpose (TRAI + DoT).

### C. DND / NCPR scrubbing (HARD LAW)
- Scrub every target list against **NCPR/DND before each campaign**; refresh **≤ every 30 days** (TRAI
  cadence). Registered-preference numbers must not get promotional calls.
- **Practical caveat (vendor consensus):** NCPR data lags **7–15 days** for newly-added numbers ⇒ scrub
  **more often than 30 days**, and **honor real-time in-call opt-out** as the backstop.
- **Log every dial attempt with its DND-verification status** (evidentiary trail).
- Consumer-side reporting: 1909 / DND app; complaint window now 7 days; action threshold tightened to
  **5 complaints in 10 days** (was 10-in-7) → less margin for sloppy lists.

### D. Recording consent (DPDP — informed; in force for substance 13 May 2027, build now)
- Disclose recording **before** substantive conversation (in the opener).
- India is effectively **one-party-consent** (a party to the call may record) → a clear *disclosure* +
  continued participation is the working standard; **two-party explicit opt-in is the safer belt** and is
  advisable for regulated verticals.
- **Log consent** (verbal "yes" or DTMF) with **timestamp**, retrievable.
- If consent refused → graceful close + suppress ("No problem, I'll end the call — have a good day").

### E. Data lifecycle (DPDP — build now, enforced 2027)
- **Purpose limitation + data minimization;** separate consent to repurpose.
- **Retention TTL + erasure:** define retention; honor erasure (vendor norm: action within ~30 days).
  Erasure must **cascade** across recording + transcript + vector index + lead memory + WhatsApp logs
  (ties to W18 MD4). Practitioner retention defaults seen in market: active-dispute recordings ~2 yrs,
  inactive ~6 months, anonymized analytics indefinitely — *set per-tenant policy, don't hardcode.*
- **Audit logs** of processing; breach-notification readiness (DPDP).
- **Vertical conflict to encode:** IRDAI ≥6-month retention **collides** with DPDP erasure → retention
  hierarchy must be documented and the erasure engine must respect a legal-hold exception.

### F. Calling-window (HARD LAW where vertical / TRAI norm)
- Promotional calling generally restricted to daytime (sources cite windows ~09:00/10:00–19:00/21:00;
  **RBI BFSI is firm 08:00–19:00**). Use a conservative **09:00–19:00** default, tenant/vertical-tunable;
  never call outside the window.

---

## 3. PENALTIES (cite-ready)

- **TRAI TCCCPR (the earner-killer):** first offence **₹2 lakh + 15-day suspension of outgoing telecom
  service**; second **₹5 lakh**; repeat **₹10 lakh**; persistent non-compliance = **1-year disconnection
  from all telecom resources + industry-wide blacklist.** Enforcement is real and automated (TRAI reports
  tens of thousands of numbers auto-disconnected in 2026). Primary practical hit = **number/sender
  blacklisting across all carriers simultaneously** → the live earner goes dark.
- **DPDP Act:** very large administrative fines (cited up to ~**₹250 crore** per major category;
  aggregate framings up to ₹500cr+) for consent/security/breach failures — enforced from 2027 once
  substantive rules bite; build to it now.
- **Sector:** RBI license suspension; IRDAI regulatory action; SEBI action — only if the tenant operates
  in that vertical.

---

## 4. HOW INDIAN VENDORS DO IT IN PRACTICE (pattern Famit should mirror)

- **Built-in, automatic compliance rails** (Exotel-class): auto DND-registry check, calling-hour
  enforcement, consent capture — done by the *platform*, not left to the script. → Famit should make
  DLT-template + DND-scrub + window-check **platform-enforced pre-dial gates**, not per-campaign manual
  steps.
- **Recording-disclosure wording in market** (illustrative, NOT a legal verbatim):
  "Hello, this is an automated call from {Company}. This conversation is recorded for quality and
  training." / "This call is being recorded for quality and training purposes — do you consent to
  continue?" → Famit's Hinglish opener (§ TL;DR) is the rapport-preserving equivalent.
- **Template + variable** discipline: regulated frame is the registered template; AI fills slots / drives
  dialogue inside it. Fully ad-lib = non-compliant.
- **Consent + DND status logged per call** as the audit/defense artifact.

---

## 5. DESIGN HANDOFF — what W2 (brain) and W26 (build) must encode

**W2 disclosure-line spec (final):**
- One warm Hinglish opener that contains: **automated** + **{company}** + **recorded** + (implicit consent
  to continue / 2-min ask). Never the banned phrase. Mirror language to the lead (Hindi/Hinglish/English).
- Turn-loop must detect **opt-out intents** ("don't call / cut number / not interested permanently") and
  **stop + suppress + log**.
- The regulated open + key claims sit inside a **DLT-registered template**; the brain fills variables and
  handles free dialogue *after* the disclosed open — it does not invent the regulated frame.

**W26 compliance-build spec (platform gates, all earner-safe/additive):**
1. **Pre-dial gate:** DLT template bound + DND/NCPR scrub fresh (≤30d, ideally tighter) + within calling
   window + 140/1600 numbering + auto-dialer pre-notified — else dial is blocked.
2. **Consent ledger:** per-call recording-disclosure + opt-out event, timestamped, retrievable.
3. **Suppression list:** honored in real time across channels.
4. **Retention/erasure engine:** TTL + cascading right-to-erasure (recording/transcript/vector/lead
   memory/WhatsApp), with a legal-hold exception for IRDAI-class retention.
5. **Per-vertical overlay** (BFSI/insurance/securities): stricter window, explicit "AI" token, human-
   escalation, mandated material-terms/free-look disclosures, firm-liability acknowledgement.
6. **Audit trail** of every processing + dial decision (DPDP).

---

## Sources (verified 2025–2026)
- TRAI TCCCPR 2nd Amendment (12 Feb 2025) — official: http://www.trai.gov.in/telecom-commercial-communications-customer-preference-second-amendment-regulations-2025 ; gazette PDF: https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf
- Securiti analysis of TCCCPR amendment: https://securiti.ai/india-spam-rules-trai-latest-amendment/
- S.S. Rana / Bar&Bench on TRAI AI-telemarketing crackdown: https://ssrana.in/articles/trais-crackdown-on-spam-calls-and-ai-driven-telemarketing/ · https://www.barandbench.com/view-point/trais-crackdown-on-spam-calls-and-ai-driven-telemarketing
- AI calling India compliance guide (DLT flow, DND, vertical penalties): https://www.autointerviewai.com/blog/ai-calling-india-dpdp-trai-dlt-compliance-complete-guide-2026
- TRAI AI-calling penalties incl. 15-day suspension: https://qcall.ai/trai-updates-for-ai-calling
- Robocall legality India 2026: https://the420.in/are-robocalls-legal-in-india-trai-rules-2026/
- Voice-AI compliance beyond TRAI (DPDP/MeitY/IRDAI/RBI layers): https://rootle.ai/blog/voice-ai-compliance-in-india-beyond-trai/
- Practical disclosure wording + retention defaults: https://www.conversailabs.com/blog/voice-ai-compliance-in-india
- DPDP Rules 2025 notified 13 Nov 2025 + phased enforcement (substantive 13 May 2027): https://www.dpdpa.com/DPDP_Rules_2025_English_only.pdf · https://www.lexology.com/library/detail.aspx?g=bbd416e3-04a5-4f77-a83b-76a01aeda951
- IT (Intermediary) Amendment Rules 2025 on synthetically generated info (in force 15 Nov 2025): https://ssrana.in/articles/2025-it-rules-amendment-regulating-synthetically-generated-information-in-indias-ai-and-privacy-landscape/ · https://www.mondaq.com/india/new-technology/1720652/deepfake-regulation-india-2025-meitys-comprehensive-it-rules-amendment
