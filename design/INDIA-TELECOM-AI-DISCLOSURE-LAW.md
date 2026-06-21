# India 2026 Telecom / UCC Law for AI Voice Telecalling — Obligations, Penalties, and the Compliant Disclosure Line

> **Status:** DOC-ONLY research synthesis. No code, no box, `agent.py` untouched. Date 2026-06-18.
> **Owner wave:** NEW-W26 (India Regulatory & Consent Engine). **Consumed by:** W2 (voice brain — the disclosure/opener line) + W26 build (DLT/DND/consent engine).
> **Why this exists (W18 C7/M4):** India 2026 law makes commercial-call compliance a **NOW gate**, not a "high-volume-later" feature, and it **collides head-on** with the founder's repeated hard demand: *"the AI must NEVER say I am an AI assistant."* This doc resolves that collision into a single, citable, human-sounding open, and lists every obligation/penalty/deadline that gates a live earner legally.
> **Scope caveat:** This is informed legal research, not legal advice. The graded amounts and the "15-day / 1-year" sender consequence are corroborated across multiple law-firm/industry analyses of the TCCCPR 2018 + Feb-2025 amendment; before high-volume launch, a telecom-law counsel sign-off on the exact disconnection clause is a cheap insurance line item.

---

## 0. THE COLLISION, STATED PLAINLY

- **Founder demand (W2 / request1/2):** the agent must sound fully human; it must **never** say "I am an AI assistant."
- **The law (TCCCPR, Feb-2025 amendment + MeitY AI Governance Guidelines, Nov-2025):** a commercial **automated/AI** call must **identify that it is automated/AI up front** (industry consensus: within the first ~15 seconds / before any substantive pitch).
- **These are not reconcilable by ignoring one.** Ignoring the law risks **₹10 lakh + telecom-resource disconnection** (the live earner goes dark by operator action). Ignoring the founder kills the product thesis (a human-sounding salesperson).
- **The resolution is a DESIGN problem, not a conflict to pick a side of:** a one-line, warm, human-cadence open that **truthfully discloses the call is automated/AI** AND **preserves rapport** — said as a confident professional would, not as a robotic disclaimer. The founder's real intent ("don't sound like a robot / don't kill the call by apologizing for being a bot") is **fully satisfiable** while being legally truthful. See §5.

---

## 1. WHICH LAWS BIND (hard law vs guidance)

| Instrument | Status | What it governs for us | Binding? |
|---|---|---|---|
| **TCCCPR 2018** (Telecom Commercial Communications Customer Preference Regulations) + **Second Amendment, 12 Feb 2025** | **In force.** Core SMS-suffix/header changes phase in to **10 Mar 2026**; sender/UTM enforcement already live. | The master framework for ALL commercial voice (promotional/service/transactional). AI voice falls squarely inside it. DLT registration, headers/templates, DND scrub, number series, calling hours, autodialer notification, graded penalties, sender disconnection. | **HARD LAW** (TRAI regulation under the TRAI Act / Telecom Act). |
| **DPDP Act 2023** + **DPDP Rules (notified Nov 2025)** | Enacted; Rules notified; **staged enforcement, full force ~May 2027.** Build now. | Consent to process personal data (call audio + transcript + lead PII = personal data). Informed/specific/free/unambiguous/revocable consent; purpose limitation; retention limits; right to erasure; breach notice. | **HARD LAW** (build-now; penalties live as the Board stands up). |
| **MeitY AI Governance Guidelines** (Nov 2025) | **Advisory** (not a statute) — but already cited by regulators/courts. | Transparency that the user is talking to **AI, not a human**; accountability + redressal for AI errors. This is the clearest "must reveal it's AI" signal. | **GUIDANCE** — but it is the interpretive lens TRAI/courts will read TCCCPR's "automated call" disclosure through. Treat as effectively mandatory for risk. |
| **IT (Intermediary Guidelines) Amendment Rules, 2025** (draft, MeitY 22 Oct 2025) — "synthetically generated information" labelling | **DRAFT / proposed** (consultation closed 6 Nov 2025; not yet notified). Content-platform-scoped (SSMIs / hosting intermediaries). | Labelling of AI-generated audio (audible marker covering ≥10% of an audio clip; permanent metadata). Aimed at posted content, **not cleanly at a live 1:1 phone call** — but it is the direction of travel and the synthetic-voice-consent rationale. | **DRAFT — not yet binding on a live voice call.** Track; do not gate on the 10%-audio-marker yet, but design so the AI-identity disclosure satisfies its spirit. |
| **Sectoral overlays** — RBI Fair Practices Code / Digital Lending (collections, BFSI), IRDAI (insurance capacity disclosure), SEBI, RERA | In force per sector. | If a tenant's campaign is BFSI/insurance/lending: stricter calling-hours/identity/recording rules layer on top (e.g. RBI collections 8 AM–7 PM; identity within 30s). | **HARD LAW for regulated tenants.** Multi-tenant: must be a per-tenant/per-vertical policy knob. |

**Bottom line on the disclosure mandate:** The *cleanest hard hook* is **TCCCPR's requirement that an automated commercial call disclose its automated nature up front**, reinforced by **MeitY's AI-vs-human transparency guideline**. The IT-Rules synthetic-content labelling is **draft and content-scoped** — do not over-rotate on its 10%-audio rule, but the AI-identity open we ship also satisfies its intent.

---

## 2. HARD OBLIGATIONS BEFORE A SINGLE PROMOTIONAL CALL (the NOW gate)

> Each is a binding TCCCPR requirement (unless tagged). These gate W26 "done" and high-volume launch.

1. **Principal Entity (PE) registration on DLT.** The legal sender (the tenant, or Famit as sender-of-record per the commercial model — **decide this explicitly, it changes liability**) must be registered as a PE on an operator DLT platform (Airtel Smart Hub / Jio TrueConnect / Vi Vilpower / BSNL / Tanla Trubloq). Legal-entity docs + authorised signatory + per-operator fee. **3–7 business days.**
2. **Header (Sender/CLI) registration.** The calling-line identity used for outbound must be a **registered header**, not an arbitrary number. ~1–3 business days.
3. **Content/script template registration.** Every outbound voice campaign must run on **pre-registered templates**; the AI must **stay within the registered template structure**. (Tension: a free-form adaptive LLM brain vs a registered script — W26 must register a template *envelope* the brain operates inside, or register variable-slot templates.)
4. **Number series — NOT a 10-digit mobile.** Promotional commercial voice must originate from the **140-series**; transactional/service from the **160-series** (1600 block). **Using a standard 10-digit mobile number for commercial AI calling is itself a violation** under the Feb-2025 amendment. → The live earner's current dialing identity must be audited against this.
5. **DND / NCPR scrub-before-dial.** Every number must be scrubbed against the current **National Customer Preference Register (DND)** **before** it is queued — described by counsel as **real-time, not a stale batch**; preference register refreshed at least every ~30 days. Promotional calls to DND-registered numbers are prohibited (consent can override for explicit-consent categories, time-boxed — see §3).
6. **AI / automated-nature disclosure up front.** The call must disclose it is an **automated/AI** call at the start (industry consensus: **within the first ~15 seconds**, before the substantive pitch / before consent prompt). This is the line W2 must design (§5). Reinforced by MeitY (AI-vs-human).
7. **Calling hours.** Commercial calls only **10:00 AM – 7:00 PM**, recipient's local time. (Recommended safety buffer 10:30 AM–6:30 PM.) BFSI collections under RBI: **8 AM–7 PM**. Per-tenant/per-vertical enforced.
8. **Autodialer / robocall pre-notification.** Auto-dialers / pre-recorded / robocall systems must be **formally notified to the originating access provider in advance** (Feb-2025 amendment). An AI predictive/auto dialer is in scope.
9. **Abandoned / silent-call discipline.** The amendment introduces auto-dialer/robocall rules to prevent "undue disturbance." Specific silent/abandoned-call **percentage caps are not published as a single national number in the TCCCPR text we verified** — but predictive-dial abandonment must be controlled (global norm ~≤3%); treat a low abandonment cap + no-dead-air as a self-imposed compliance control, and confirm the exact figure with counsel/operator. **(Partly guidance / operator-policy, not a verified single TRAI number — flagged, do not assert a hard %.)**
10. **Consent — two distinct consents.** (a) **TCCCPR consent to *place* the commercial call**; (b) **DPDP consent to *process* personal data** (audio/transcript/PII). They are separate. Consent must be free/specific/informed/unambiguous and **revocable**; silence ≠ consent (verbal or DTMF confirmation before continuing).
11. **Recording consent + retention (DPDP).** Disclose the call may be recorded; obtain consent; **retain only as long as the stated purpose**; auto-purge past retention; honour erasure (cascade across recording + transcript + vector index + lead memory + WhatsApp logs). Audit/consent records kept (≥6 months for UCC audit per industry practice).
12. **Synthetic-voice transparency (forward-looking).** Following the 2025 IT-Rules direction + MeitY, treat the AI-identity open as also covering "this is a synthetic/AI voice." **Draft, not yet a hard standalone duty for a live call** — but the §5 line satisfies it at zero extra cost.

---

## 3. CONSENT VALIDITY WINDOWS (Feb-2025 amendment — these are short)

- **Inferred consent** (from an existing business relationship): valid **only for the duration of the contractual relationship** (no longer indefinite).
- **Explicit consent to fulfil a commercial transaction:** valid for **just 7 days** from acquisition.
- **Consumer complaint window:** extended from **3 days → 7 days** (recipients get longer to flag your AI call as spam → higher complaint exposure).
- **Access-provider complaint-resolution window:** shortened (to ~5 days).
- **Implication for the brain:** a lead's "consent" is not durable — the dialer must check consent freshness at dial time, not just at list-import. This is a W26 + dial-loop gate, not a one-time import flag.

---

## 4. PENALTIES & ENFORCEMENT (the cost of getting it wrong)

> Amounts corroborated across multiple law-firm/industry analyses of the TCCCPR 2018 + Feb-2025 amendment. Two distinct penalty planes: **TRAI/telecom** and **DPDP/data**.

### TRAI / TCCCPR plane
- **Graded financial disincentive** (on access providers / for failure to implement headers-templates, misreport UCC counts): **₹2 lakh (1st instance) → ₹5 lakh (2nd) → ₹10 lakh (subsequent).**
- **Per-violation UCC penalty band:** **₹1,000 – ₹1,50,000 per violation** (TRAI's general UCC penalty range).
- **Unregistered-Telemarketer (UTM) escalation against the *sender*:** **warning → 6-month "usage cap" → disconnection of ALL telecom resources** on repeated violation.
- **Sender disconnection consequence (the earner-killer):** widely reported as **first offence = ~15-day suspension/bar of outgoing/telecom services; repeat = ~1-year disconnection + blacklisting across all operators.** → **A single confirmed pattern can take the live earner offline by operator action, regardless of code quality.**
- **Complaint-triggered disconnection:** as few as **~3 complaints** against a number can trigger service disconnection.
- **Proactive AI/ML spam detection:** TRAI uses AI/ML to detect UTMs and is moving toward **disconnecting suspected-spam numbers even before a formal complaint** (tens of thousands of numbers disconnected per quarter). → spam-pattern avoidance (pacing, DND, consent) is existential, not cosmetic.

### DPDP plane (data, not telecom)
- **Up to ₹250 crore** for the most serious failures (e.g. failure to prevent a significant breach, failure to honour data-principal rights including **erasure**, processing without valid consent). Other tiers ₹200 cr (breach-notification / children's data) etc.
- These are **per-default, Board-imposed**; the live exposure ramps as the DPDP Board stands up (Rules notified Nov-2025; full force ~May-2027).

### Net earner risk
The TRAI plane is the **immediate** threat to the live product: it can **cut the founder's outgoing telecom service** on a complaint/scrub-audit. The DPDP plane is the **large-rupee** threat that compounds as 2026→2027 enforcement matures.

---

## 5. THE RESOLUTION — a compliant, human-sounding disclosure line (W2 deliverable)

**Design principle:** disclose **truthfully and up front** that the call is **automated/AI**, in **one warm, confident, human-cadence sentence**, folded into the greeting so it reads as professional transparency — NOT a robotic apology. The founder's real objection ("don't sound like a bot / don't kill rapport by saying 'I am an AI assistant, I cannot…'") is honoured: we never use the cringe disclaimer phrasing, we never *apologise* for being automated, and we move immediately into value. We DO satisfy the legal "it's automated/AI" duty.

### What is NOT allowed (kills the earner legally)
- Claiming or implying a **human** ("I'm Riya calling personally from…") with **no** automated/AI disclosure → false-identity + missing-disclosure violation.
- Burying the disclosure after the pitch, or only on request.

### What IS allowed and still sounds human (ship these — A/B in W2)
> All are **legally sufficient** (they state it's an automated/AI/virtual call up front) AND warm. Pick per-language; localise to Hindi/Hinglish without losing the disclosure token.

- **EN (recommended default):**
  *"Hi, this is Riya, an AI voice assistant calling on behalf of {Brand}. This call is automated and may be recorded. I'll be quick — is now an okay time?"*
- **EN (warmer / lower-friction):**
  *"Hello! You're speaking with {Brand}'s digital assistant, Riya — yes, an automated AI call, and it may be recorded. I just need thirty seconds…"*
- **Hinglish:**
  *"Namaste, main Riya — {Brand} ki taraf se ek automated AI voice call. Ye call record bhi ho sakti hai. Sirf ek minute…"*
- **Hindi:**
  *"Namaste, main {Brand} ki digital (AI) assistant Riya bol rahi hoon. Yeh ek automated call hai aur record ho sakti hai. Aapka thoda sa samay…"*

### Why this satisfies the founder AND the law
- **Legally:** the words "AI / automated / digital assistant / virtual" up front = the required automated-nature + AI transparency disclosure; "may be recorded" seeds recording-consent; it precedes the pitch. ✔
- **Founder:** it never says the cringe "I am an AI assistant, I cannot do that"; it's a confident, branded, fast, rapport-first open; the human warmth lives in *voice + cadence + immediate value*, not in pretending to be a person. The thing he actually hates (robotic, apologetic, self-limiting bot-speak) never appears. ✔

### Hard rules for the brain (W2 must enforce structurally, not by prompt-hope)
1. The disclosure token (one of: *AI / automated / virtual / digital assistant*) MUST appear in the **first utterance**, before any pitch. (Control-flow, like H8/H12 — not a soft instruction the caller can talk past.)
2. The agent MUST NOT affirmatively claim to be a **human** if asked ("are you a real person?") — answer truthfully and warmly ("I'm {Brand}'s AI assistant — but I can actually help you with X right now"). A truthful, value-forward answer keeps rapport without a violation.
3. **Recording line** present where recording is on; **opt-out / "press 9 / say stop"** path offered; honour it immediately (DPDP revocability + DND).
4. **Per-tenant/per-vertical config:** stricter sectoral lines (BFSI/insurance) override the default; calling-hours + number-series enforced server-side at dial time, not trusted to the campaign.

---

## 6. WHAT W26 MUST BUILD (engine side — fed from this doc)

- **DLT registry integration / state:** PE + header + template status per tenant; **block dial** if not registered.
- **DND/NCPR scrub-before-dial** as a hard dial-loop gate (real-time, refresh ≤30d); consent-freshness check (inferred = contract-duration; explicit-txn = 7 days).
- **Number-series enforcement:** outbound CLI must be 140/160-series-registered; reject 10-digit-mobile dialing for commercial campaigns.
- **Calling-hours gate** (10 AM–7 PM local; BFSI 8 AM–7 PM) at dial time.
- **Autodialer pre-notification** record/flag per access provider.
- **Disclosure-line enforcement** (the §5 line) as control-flow in the opener (co-owned with W2).
- **Consent ledger** (TCCCPR-place-call + DPDP-process-data, separate), revocable, time-boxed, audited.
- **Recording consent + retention TTL + cascading right-to-erasure + at-rest encryption** (co-owned W9/W7/W14).
- **Per-tenant sender-of-record decision** (who is the registered PE — Famit vs tenant) — **a commercial + liability decision the founder must make**; record it in W26 state.

---

## 7. OPEN QUESTIONS FOR FOUNDER / COUNSEL (record, don't block design)

1. **Sender-of-record:** Is Famit the registered Principal Entity for all tenants (platform model), or does each tenant register their own PE? Changes who eats the ₹10L / disconnection. *(Recommend per-tenant PE for liability isolation; Famit as RTM/aggregator.)*
2. **Exact abandoned/silent-call cap** — confirm the binding figure (if any) with the operator/counsel; §2.9 is flagged as guidance/operator-policy, not a verified single TRAI %.
3. **Counsel sign-off** on the precise "15-day suspension / 1-year disconnection" clause wording before high-volume launch (corroborated by multiple analyses; confirm against the gazette clause).
4. **Template-vs-adaptive-brain reconciliation:** register a variable-slot template envelope the LLM operates inside, so the adaptive brain doesn't break content-template registration.

---

## Sources
- TRAI Second Amendment to TCCCPR 2018, gazette (12 Feb 2025): https://trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf · https://trai.gov.in/tcccpr
- India Law — TRAI's measures to combat spam (graded ₹2L/₹5L/₹10L; UTM escalation; complaint windows; 140/1600; -P/-S/-T/-G): https://www.indialaw.in/blog/civil/trais-combat-spam-protect-consumers/
- Mondaq — Amended TCCCPR analysis: https://www.mondaq.com/india/telecoms-mobile-cable-communications/1586718/
- Saraf Partners — Modifications to TCCCPR 2018: https://sarafpartners.com/modifications-to-the-2018-telecom-commercial-communications-customer-preference-regulations/
- Saikrishna & Associates — Strengthening consumer protection (TCCCPR amendment): https://www.saikrishnaassociates.com/strengthening-consumer-protection-by-trai-amendment-to-the-tcccpr/
- Sigma Chambers — 2025 TCCCPR amendments: https://www.sigmachambers.in/post/2025-tcccpr-amendments-a-renewed-push-by-trai-for-order-in-commercial-communications-1
- OnDial — Is AI calling legal in India? TRAI rules & consent (15-sec disclosure, 140/160, 10 AM–7 PM, real-time DND, ₹1k–₹1.5L): https://www.ondial.ai/blog/ai-calling-legal-india-trai-rules-consent
- Auto Interview AI — AI calling India DPDP/TRAI/DLT complete guide 2026 (DLT, DND 30d, DPDP ₹250cr tiers): https://www.autointerviewai.com/blog/ai-calling-india-dpdp-trai-dlt-compliance-complete-guide-2026
- Caller Digital — Voice AI India Regulatory Map 2026 (TRAI/DPDP/RBI/IRDAI/RERA): https://www.caller.digital/blog/voice-ai-india-regulatory-map-2026
- qcall.ai — TRAI updates for AI calling 2026 (140/160, ₹2L+15-day / ₹10L+1-yr, Feb 2026 effective): https://qcall.ai/trai-updates-for-ai-calling
- S.S. Rana — 2025 IT Rules Amendment, synthetically generated information (draft; ≥10% audio marker; metadata): https://ssrana.in/articles/2025-it-rules-amendment-regulating-synthetically-generated-information-in-indias-ai-and-privacy-landscape/
- Lexology — Amendment to IT Rules regulating AI-generated content: https://www.lexology.com/library/detail.aspx?g=f003ab80-a596-4dbd-995d-b03bf3aad6e2
- DPDP Act 2023 + Rules (notified Nov 2025; full enforcement ~May 2027) — per Caller Digital / Auto Interview AI / OnDial analyses above.
- MeitY AI Governance Guidelines (Nov 2025, advisory — AI-vs-human transparency) — per OnDial / Caller Digital analyses above.
