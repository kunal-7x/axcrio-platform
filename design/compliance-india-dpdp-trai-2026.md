# India 2026 Compliance for the Live AI Voice Telecaller (Famit/Axcrio)

> **Status:** RESEARCH / DESIGN (doc-only). Gates the live earner legally.
> Researched 2026-06-18 (current, post-notification). Not legal advice — engage Indian
> counsel before relying on the "disclosure-line" resolution at scale.
>
> **Consumed by:** W2 (brain — disclosure line + de-hardcode of "I am an AI assistant"),
> W26 (build), W12 (telephony safety / compliance-as-a-feature).

---

## TL;DR — the three regimes that bind a live AI telecaller

There is **no single "India 2026 AI law."** A live outbound/inbound AI telecaller is bound by
**THREE separate, simultaneously-applicable** regimes. They must ALL be satisfied:

| Regime | Governs | Max penalty | Status / deadline |
|---|---|---|---|
| **TRAI TCCCPR 2018 + 2025 Amendment** (telecom) | Commercial calls, DLT, DND, 140/1600 series, AI-call disclosure, calling windows | Graded ₹2L → ₹5L → ₹10L per violation; usage-cap (6 mo) → **full disconnection** of all telecom resources | **IN FORCE NOW** (amendment 12 Feb 2025). HARD LAW. |
| **DPDP Act 2023 + DPDP Rules 2025** (data) | Consent, notice, PII rights, retention, security, breach, erasure | **₹250 crore** per violation (security failure); ₹200 cr (breach-notify failure) | Rules notified **13 Nov 2025**; full operational compliance by **13 May 2027** (18-mo glide). HARD LAW, phased. |
| **IT Rules 2021 + 2026 Amendment** (synthetic media) | Labelling of AI-generated ("SGI") content incl. **audio identifier** | IT Act intermediary liability; 3-hr takedown | Notified **10 Feb 2026**. HARD LAW. Applicability to *live* calls is ambiguous (see §5). |

**The ₹10 lakh + suspension gate in the wave brief is the TRAI TCCCPR regime, NOT DPDP.**
The brief conflated them. Precise facts below.

---

## 1. THE COLLISION: "the AI must NEVER say I am an AI assistant"

The founder's hard demand collides with a **TRAI disclosure obligation**, but the collision is
**resolvable** — and the resolution is the load-bearing output for W2.

### What the law actually requires (hard law)
- **TRAI / TCCCPR:** an AI/automated outbound commercial call must, **at the start (best-practice
  cited as within ~15 seconds)**, disclose (a) the **identity of the caller/company (the Principal
  Entity)** and (b) that the call is **automated / pre-recorded / made via an auto-dialer or
  robo-call**. Telemarketers "must disclose the use and intended purpose of Auto Dialer or
  Robo-Calls." Passing an AI off as a live human is treated as a **deceptive trade practice** under
  consumer-protection law (independent exposure beyond TRAI).
- **Consumer Protection:** misrepresenting a bot as a human = unfair/deceptive practice.
- **IT Rules 2026 (SGI):** "audible disclosure at the beginning of audio" for synthetically
  generated audio — see §5 for the live-call ambiguity.

### The key legal nuance that RESOLVES the founder's demand
**No hard law requires the literal sentence "I am an AI assistant."** What is required is:
1. **Caller/company identity** ("This is a call from <Company> about <purpose>"), AND
2. **A truthful signal that the call is automated/not a live human agent.**

The mandate is **truthful non-deception + automation transparency**, NOT a scripted self-label
that breaks the human persona. So the brain can satisfy the law with a **company-first,
automation-true** opener that never utters the persona-breaking "I am an AI assistant."

### APPROVED DISCLOSURE-LINE PATTERNS (the W2 output)
Each is legally defensible (identity + automated-nature, truthful, no human-impersonation) while
**preserving the warm human persona** the founder wants. Pick per-vendor/locale; keep configurable.

**Pattern A — automated-call frame (recommended default, Hinglish):**
> "Namaste, main <Company> ki taraf se ek **automated call** par baat kar rahi hoon — <Riya>.
> <one-line purpose>. Kya main aapse 2 minute baat kar sakti hoon?"

> EN: "Hi, this is an **automated call** from <Company> — I'm <Riya>. <purpose>. Is now a good time?"

- Discloses (a) company, (b) **automated call**. Does NOT say "I am an AI assistant."
- The persona name ("Riya") is retained; the *medium* is disclosed, not a robot self-label.

**Pattern B — "AI assistant of the company" frame (if counsel wants the word "AI"):**
> "Namaste, main <Company> ki **AI assistant Riya** bol rahi hoon..."

- Uses "AI assistant" but as a **branded identity of the company**, not the persona-breaking
  confession "I am an AI assistant, not a human." Softer than the literal banned phrase; still some
  persona cost. Offer as a fallback if legal review rejects Pattern A.

**Pattern C — recorded/automated + consent-confirm (highest-safety, TCCCPR-aligned):**
> "Namaste, yeh <Company> ki taraf se ek **automated call** hai. Kya aap baat continue karna
> chahenge? Haan ke liye 'haan' boliye." (verbal/DTMF confirm → proceed; else end.)

- Adds the **consent-confirmation** TRAI guidance expects ("verbal or DTMF confirmation before
  continuing; silence ≠ consent"). Use for cold/promotional lists; can relax for warm/consented
  leads.

**HARD RULES for W2 (de-hardcode):**
- Remove the firing of the literal self-deprecating "I am an AI assistant" line
  (`agent.py:218`, `prompt.py:358`) — replace with a **configurable disclosure-line slot** that
  defaults to **Pattern A**.
- The disclosure must be **truthful** (we are automated) — do NOT let the brain deny being
  automated if the human directly asks "are you a real person / a robot?" Build an **honesty
  fallback**: if asked, confirm it's an automated/AI-assisted call for <Company>. Lying when
  directly asked is the deceptive-practice trap; the persona is preserved by *framing*, not by
  *lying*.
- Make the disclosure line **per-vendor/per-locale configurable** (Hindi/Hinglish/EN), logged with
  consent, and A/B-flaggable — but **non-empty is enforced** (cannot ship a call with zero
  disclosure).

---

## 2. TRAI TCCCPR (telecom) — HARD LAW, IN FORCE NOW

This is the regime with the **near-term suspension teeth**. Most relevant to a high-volume caller.

### Obligations (hard law)
- **Principal Entity (PE) + Telemarketer (TM) registration on the DLT** (blockchain) platform of an
  access provider. Unregistered commercial calling is itself a violation.
- **Telecom-resource series:** **140-series** for promotional, **1600-series** (a.k.a. "160") for
  transactional/service. Using ordinary 10-digit numbers for marketing → **disconnection on first
  complaint + 2-year blacklist** of the caller.
- **DND / NCPR scrubbing:** scrub lists against the National Customer Preference Register
  (regularly, typically weekly) before promotional calls.
- **Calling-time window:** **no promotional calls 9:00 PM – 9:00 AM** (local time).
- **AI/auto-dialer disclosure** at call start (see §1): company identity + automated nature; opt-out
  honoured **within 24–48 hrs**.
- **Consent timestamped + logged**; silence/continued-listening ≠ valid consent.
- **No silent/abandoned autodialer calls** (predictive-dialer abandonment is a violation vector).

### Penalties (hard law — the real suspension regime)
- **Graded financial disincentives:** **₹2 lakh (1st) → ₹5 lakh (2nd) → ₹10 lakh (repeat)** per
  violation category (imposed separately for registered vs unregistered senders; also on access
  providers for their own failures).
- **Graded telecom-resource action against the sender:** 1st = **warning**; 2nd = **usage cap for
  6 months**; 3rd+ = **disconnection of ALL telecom resources** of the sender.
- **Complaint-triggered:** 3 complaints → service disconnection path; using a normal number for
  marketing → disconnect on **first** complaint + **2-yr blacklist**.
- **Security deposit:** access providers may take a **security deposit** from senders/TMs, **forfeit
  on violation**.
- *(The "15-day suspension" in the wave brief maps to this disconnection/usage-cap family — TRAI's
  enforcement is graded warning → cap → disconnect, not a fixed 15-day figure in the 2025 amendment
  text I reviewed. Treat the **suspension/disconnection risk** as the real gate; confirm the exact
  duration with counsel for the specific access-provider agreement.)*

> Amendment effective **12 Feb 2025** (Gazette, Part III §4). **This is live now** — it gates
> high-volume calling **today**, independent of the DPDP 2027 glide path.

---

## 3. DPDP Act 2023 + DPDP Rules 2025 (data) — HARD LAW, PHASED to May 2027

### Timeline (hard law)
- **13 Nov 2025** — Rules notified (Gazette G.S.R. 846(E)); staggered commencement begins. Data
  Protection Board institutional provisions effective immediately.
- **~12 Nov 2026 (12 mo)** — **Rule 4 Consent Manager registration** in force; consent-manager
  ecosystem operational; revalidation of legacy/pre-DPDP data must be underway.
- **13 May 2027 (18 mo)** — **Rules 3, 5–16, 22, 23 in force** = the **core operational compliance**
  (notice, consent mechanics, data-principal rights, breach process, security safeguards, retention,
  SDF audit). **Hard enforcement + full ₹-penalty adjudication from this date.**

> Practical read: **soft-enforcement glide now → build for 13 May 2027.** Do NOT wait — build the
> consent/notice/rights/retention/security machinery into the product now (it is also a **sales
> differentiator** and de-risks the TRAI overlap which is *already* live).

### Obligations (hard law / Rules)
- **Consent:** free, specific, informed, **unambiguous**, and as easy to **withdraw** as to give;
  **verifiable** (keep records of scope + timestamp + policy version). Purpose-limited (one purpose =
  one consent; separate core service from optional uses like model-training/personalisation).
- **Notice (itemised):** plain-language, available in **English + any of the 22 Eighth-Schedule
  languages** (Section 5(3)); state what data, why, how to exercise rights, how to complain to the
  Board, how to withdraw consent.
- **Lawful basis:** consent OR a **narrow "legitimate uses"** carve-out. **For outbound *sales*
  calling, do NOT rely on "legitimate use" as a blanket basis** — India's legitimate-use is much
  narrower than GDPR legitimate-interest. Get consent (or use the consent the lead gave at lead-gen,
  recorded + scoped to outreach).
- **Data-principal rights:** access, correction/completion/update, **erasure**, grievance redressal,
  **nomination**. Build self-service flows; **erasure must cascade** across CRM, transcripts,
  recordings, analytics, backups.
- **Grievance redressal:** complete within **90 days**.
- **Retention limitation:** delete when purpose served / consent withdrawn / inactivity window
  passes ("erasure by default after inactivity"). Rules require retaining personal data + traffic
  data + logs **≥ 1 year** (for the prescribed classes) — i.e. a **floor for logs, a ceiling for
  purpose-spent PII**. Set explicit per-artefact retention (recordings/transcripts/lead PII) in the
  product.
- **Security safeguards (highest-penalty trigger — up to ₹250 cr):** **encryption** /
  identity-verification, masking/tokenisation of direct identifiers, **access control (RBAC)**,
  **logging + log retention (≥1 yr)**, segregated vault storage. Industry baseline cited:
  **AES-256 at rest, TLS 1.3 in transit, RBAC on recordings/transcripts.**
- **Breach notification:** notify the **Data Protection Board** and **affected data principals**;
  data-principal notice **within 72 hours** with plain-language description, data exposed,
  protective steps, and contact.
- **Significant Data Fiduciary (SDF)** extra duties (if designated — thresholds incl. ~5M+
  residents' data, ₹250cr+ turnover, or AI-driven profiling/decisioning): **India-based DPO**,
  **DPIA / algorithmic impact assessment**, **periodic independent audit** (audit cycle from
  Q1 2027). A high-volume AI telecaller **using AI for profiling/decisioning is a candidate** —
  design DPIA + DPO readiness now.
- **Automated decisioning:** DPDP expects **meaningful human oversight** of solely-automated
  decisions; explainability/fairness for SDFs. Keep a human-handoff + audit trail (already in the
  product design via warm-transfer + audit).

### Penalties (hard law — Section 33)
- **Range ₹10,000 → ₹250 crore per violation** (per violation, not per incident; cumulative across
  violations).
- **₹250 crore** — failure of reasonable **security safeguards** (the big one).
- **₹200 crore** — failure to **notify breach**.
- Penalty factors: nature/gravity, sensitivity, repetition, gain, mitigation. Deposited to the
  Consolidated Fund (not victim compensation).

---

## 4. The intersection that bites the Famit pipeline

| Pipeline element (from the kernel plan) | Obligation it triggers | Regime |
|---|---|---|
| Outbound AI call opener | Identity + automated-nature disclosure; no human-impersonation | TRAI + Consumer law (§1) |
| Cold/promotional lists | DLT reg, 140-series, NCPR scrub, 9pm–9am window, consent-confirm | TRAI (§2) |
| Lead PII / campaign card / lead-memory | Consent + notice + purpose-limit + erasure cascade + retention | DPDP (§3) |
| **Recording + transcript + AI summary** (W9) | Recording-consent on call; encryption at rest; RBAC; retention; erasure cascade; ≥1-yr log floor | DPDP (§3) |
| **R2/B2 object storage** of recordings | Encryption at rest, access control, breach-readiness | DPDP (§3) |
| WhatsApp follow-up (W14/W16) | TCCCPR template/consent + DPDP consent scope | TRAI + DPDP |
| Daily WhatsApp exec summary w/ lead names | Purpose-limit + access control (don't leak PII cross-tenant) | DPDP (§3) |
| AI profiling / hot-warm-cold scoring (W7) | Possible SDF → DPIA, human-oversight, explainability | DPDP-SDF (§3) |
| Multi-tenant isolation | Each tenant = its own Fiduciary; RLS + erasure scoped per-tenant | DPDP (§3) |

**Product implications (feed to W12 compliance-as-a-feature + W9 retention + W2 disclosure):**
1. **Disclosure-line slot** in the brain (Pattern A default), per-vendor/locale, enforced non-empty,
   logged (§1).
2. **Honesty fallback** when directly asked "are you human?" (truthful automated/AI confirmation).
3. **Consent ledger**: scope + timestamp + source + policy-version per lead; opt-out honoured
   24–48h; withdrawal = stop + erasure trigger.
4. **DLT/NCPR/window/140-series guardrails** in the number-pool + scheduler (W12) — *these gate
   high-volume NOW*.
5. **Retention policy engine** (W9): per-artefact TTL (recordings/transcripts/PII) with erasure
   cascade across CRM/analytics/backups/object-store; ≥1-yr log floor.
6. **Encryption-at-rest + RBAC + audit logging** on recordings/transcripts/PII (already partially in
   wallet/firewall/audit — extend to the media store).
7. **Breach runbook** (72-hr data-principal notice template).
8. **DPIA + DPO readiness** if SDF-designated (AI profiling at volume).
9. **Right-to-erasure API** + self-service in the panel (DPDP rights = also a sellable feature).

---

## 5. IT Rules 2026 (synthetic-media labelling) — applicability nuance

- Notified **10 Feb 2026**. Brings "Synthetically Generated Information (SGI)" — deepfakes,
  AI-generated audio — into the IT Rules due-diligence framework. Requires a **"clear and prominent"
  label**: on-screen for visual, an **"audible disclosure at the beginning of audio"** + permanent
  tamper-resistant metadata identifier; **3-hour takedown** of flagged content.
- **Ambiguity (flag for counsel):** the IT Rules SGI regime is framed around **intermediaries /
  platforms publishing/hosting synthetic *content/files***, not unambiguously around a **live,
  real-time AI phone conversation**. A live two-way call is plausibly governed by **TRAI** (the
  telecom-call disclosure in §1), not the SGI content-labelling rule. **BUT** the safest posture —
  and the one that also satisfies §1 — is to **front-load the automated-call audio disclosure
  (Pattern A) at the very beginning of the call**, which discharges both the TRAI duty and the
  spirit of the SGI "audio identifier at the beginning" duty simultaneously. One disclosure, two
  regimes covered.

---

## 6. Hard-law vs guidance — what to treat as binding

**HARD LAW (binding now / on the stated dates):**
- TCCCPR 2018 + 2025 amendment: DLT, 140/1600, NCPR/DND, 9pm–9am window, auto-dialer disclosure,
  graded ₹2/5/10-lakh + disconnection penalties, security-deposit forfeiture. **In force.**
- DPDP Act 2023 + Rules 2025: consent/notice/rights/retention/security/breach; ₹250-cr cap.
  Phased — **core ops binding 13 May 2027**, consent-manager 12 Nov 2026.
- IT Rules 2026 SGI labelling. **In force 10 Feb 2026** (applicability to live calls ambiguous, §5).
- Consumer Protection law: bot-as-human = deceptive practice. **In force.**

**GUIDANCE / BEST-PRACTICE (not statutory text, but de-risks and is what enforcement expects):**
- The specific "within 15 seconds" disclosure window and "verbal/DTMF consent-confirm before
  continuing" — derived from regulatory commentary + vendor guides, not a quoted clause. Treat as
  the safe operating standard.
- Specific retention figures (recordings 90d / transcripts 1yr / metadata 2yr) — illustrative;
  set by purpose + consult counsel (RBI overrides to 8yr for financial).
- AES-256 / TLS 1.3 — industry baseline for "reasonable security safeguards," not a named DPDP
  standard.

---

## 7. Citations (authoritative / current)

- DPDP Rules 2025 notification (PIB, Gov of India): https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf
- DPDP Act §33 penalties (full text): https://www.dpdpa.com/dpdpa2023/chapter-8/section33.html
- EY — DPDP Act 2023 + Rules 2025 compliance guide: https://www.ey.com/en_in/insights/cybersecurity/decoding-the-digital-personal-data-protection-act-2023
- Deloitte — DPDP Rules 2025: https://www.deloitte.com/in/en/services/consulting/about/indias-dpdp-rules-2025-leading-digital-privacy-compliance.html
- India Briefing — DPDP compliance timeline 2026-27: https://www.india-briefing.com/news/india-dpdp-compliance-timeline-enforcement-2026-27-44740.html/
- S.S. Rana — MeitY notifies final DPDP Rules 2025: https://ssrana.in/articles/meity-notifies-final-digital-personal-data-protection-rules-2025/
- TRAI TCCCPR amendment regulation (Gazette, 12 Feb 2025): https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf
- Securiti — India spam rules / TRAI amendment takeaways: https://securiti.ai/india-spam-rules-trai-latest-amendment/
- Saikrishna & Associates — TCCCPR amendment (penalties): https://www.saikrishnaassociates.com/strengthening-consumer-protection-by-trai-amendment-to-the-tcccpr/
- The420 — Robocalls legal in India (TRAI 2026): https://the420.in/are-robocalls-legal-in-india-trai-rules-2026/
- ondial.ai — AI calling legal in India (TRAI rules + consent + opener): https://www.ondial.ai/blog/ai-calling-legal-india-trai-rules-consent
- Caller.digital — Voice AI India regulatory map 2026: https://www.caller.digital/blog/voice-ai-india-regulatory-map-2026
- Caller.digital — DPDP Act voice-AI compliance checklist: https://www.caller.digital/blog/dpdp-act-compliance-checklist-voice-ai-india
- TALK-Q — India outbound call regulations 2025 (DPDPA + TRAI): https://talk-q.com/outbound-call-regulations-in-india
- Hogan Lovells — IT Rules 2026 AI labelling + 3-hr takedown: https://www.hoganlovells.com/en/publications/india-introduces-mandatory-labelling-for-ai-and-3hour-takedown-for-illegal-content
- Leegality — DPDP impact on telemarketing: https://www.leegality.com/consent-blog/dpdp-telemarketing-regulations
