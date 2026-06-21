# W18 RESEARCH — Call-Recording Consent + AI Disclosure (India, 2025-2026)

> STRICT DOC-ONLY research output. Gates a LIVE earner legally (panel.famit.in
> outbound/inbound AI telecaller, India-first Hindi/Hinglish, multi-tenant).
> Consumed by W2 (voice brain) + W26 (build). Distinguishes HARD LAW vs GUIDANCE.
> Researched 2026-06-18.

---

## TL;DR — the legal gate for the founder

1. **Two-/one-party consent is the WRONG frame for India.** India has no
   federal "two-party consent to record" wiretap statute like US states. The
   binding regime for a BUSINESS recording calls with PII is the **DPDP Act
   2023 + DPDP Rules 2025** consent-and-notice regime (the org is a "Data
   Fiduciary"), backed by the constitutional privacy right (Puttaswamy, Art 21).
   In practice this is *stricter* than two-party: you must give a **specific,
   informed, plain-language notice + obtain free affirmative consent** before
   recording, then store securely and delete on purpose-end. **HARD LAW.**

2. **The AI-self-identification collision is REAL but currently SOFT, not yet
   hard law.** As of June 2026 there is **NO in-force statute that forces the
   words "I am an AI"** at call open. The mandatory AI-disclosure rule is in a
   **TRAI consultation paper (open >1 year) + the proposed TCCCPR amendment for
   AI-based telemarketing + the 2026 IT-Rules synthetic-content push** — all
   directional, not yet enforceable text. **What IS hard law today** is
   *identity + purpose + recording* disclosure (who/what entity/why + "this
   call is recorded"), NOT a forced "I am a bot." => The founder's "never say I
   am an AI" can be honored *today* by a compliant identity/purpose/recording
   line, but a forced AI-disclosure rule is on the near horizon and W26 must be
   built to flip it on per-tenant via a flag.

3. **The NOW penalty gate is TCCCPR (TRAI), not DPDP.** TCCCPR Second Amendment
   (gazetted **12 Feb 2025**) = graded financial disincentives **₹2L / ₹5L /
   ₹10L** + header/template **suspension & blacklisting** of telecom resources.
   This is in force and is the ₹10-lakh + suspension threat. DPDP monetary
   penalties (Schedule, up to **₹250 crore**) become enforceable on the
   **13 May 2027** full-compliance date (Rules notified 14 Nov 2025, 18-mo
   phase-in).

---

## A. CALL-RECORDING CONSENT — what the law actually requires

### A1. Consent model (HARD LAW)
- India is **NOT a "two-party consent" jurisdiction by statute.** There is no
  general criminal wiretap law requiring both parties to agree to a recording
  by a participant. Older one-party tolerance came from being a party to the
  call. **BUT** for a *business/commercial* recording of calls containing
  personal data, the governing hard law is now **DPDP Act 2023** (in force since
  enactment Aug 2023; operational via **DPDP Rules 2025**, notified 14 Nov 2025).
- Under DPDP, the recording org = a **Data Fiduciary**. It MUST, before/at the
  point of recording:
  (a) give a **clear, specific, plain-language NOTICE** (Section 5 / Rule on
      notice) stating the personal data sought, the **specified purpose**, how
      to exercise rights, and how to complain;
  (b) obtain consent that is **free, specific, informed, unconditional,
      unambiguous, with a clear affirmative action** (Section 6);
  (c) store securely with **reasonable security safeguards** (Section 8(5));
  (d) **erase** when purpose is served / consent withdrawn (Section 8(7)).
- Constitutional backstop: **Puttaswamy v. Union of India** made privacy a
  fundamental right (Art 21) — non-consensual recording of a private
  conversation is presumptively a privacy wrong. (HARD constitutional law; sets
  the floor the DPDP regime operationalizes.)
- **Net rule for Famit:** treat it as **two-party-equivalent**. Disclose +
  obtain affirmative consent before recording every call. Do not rely on
  "we're a party so one-party is fine" for a commercial PII recording.

### A2. What must be SAID before recording (HARD LAW notice + GUIDANCE script)
- Hard-law content of the notice (DPDP): WHAT data, WHY (specified purpose),
  HOW to exercise rights / withdraw, HOW to complain.
- **Critical, often-missed point (best-practice tightening, becoming expected):**
  the notice should name the **modality of analysis** — i.e. if AI processes the
  audio/transcript, say "**recorded and analysed by AI**", not merely "recorded
  for quality." This is currently *guidance* but is the direction DPDP Rules
  enforcement is heading and is the safest line.
- Affirmative-consent capture in a voice flow (GUIDANCE pattern, widely used):
  IVR/opening line + an explicit affirmative act ("press 1" / a spoken "yes" /
  continuing after a clear opt-out offer) logged as the consent marker.
- **Disclosure line W2/W26 can ship (compliant TODAY, AI-identity-neutral):**
  > "This call is being recorded and may be analysed to improve our service.
  >  I'm calling from [Tenant/Brand] about [purpose]. You can opt out or ask us
  >  to delete your data at any time."
  This satisfies identity + purpose + recording + rights WITHOUT the words "I am
  an AI" — honoring the founder demand under *current* law. Keep a second,
  flag-gated variant that prepends an AI-disclosure clause for the day the TRAI
  AI rule lands or a tenant/sector (BFSI/insurance) requires it.

### A3. Retention + access + security for recordings/transcripts with PII
- **Retention (HARD LAW principle, no single national number):** DPDP Section
  8(7) = **erase once purpose served / consent withdrawn.** No fixed universal
  retention period; it's purpose-bound (data minimisation).
- **Reconciliation rule:** retention = **GREATER OF (sectoral legal floor, DPDP
  purpose-lifetime).** Sectoral floors that OVERRIDE the "delete ASAP" default:
  - RBI (collections / lending calls): **min 90 days** (best practice 12+ mo).
  - IRDAI (insurance sales calls): policy term + statutory limitation (commonly
    **3+ years**).
  - NMC telemedicine: typically **3 years**.
  (These are sector-specific; apply per tenant vertical.)
- **Erasure notice (HARD LAW, DPDP Rules 2025):** for certain Data Fiduciaries,
  notify the Data Principal **at least 48 hours before** scheduled erasure.
  Erasure-request responses to be handled within **90 days**.
- **Erasure must be COMPLETE:** primary store + secondary + backups + vendor
  systems, evidenced by a deletion record/certificate (GUIDANCE on how, mandated
  outcome under DPDP).
- **Security safeguards (HARD LAW, Section 8(5) + DPDP Rules 2025):** reasonable
  safeguards across all processing stages. Rules specify **access logs, traffic
  data, processing logs retained ≥ 1 year** for detection/investigation.
- **Consent-record retention:** maintain consent artefacts (notice version,
  timestamp, purposes, response) — industry expectation **~7 years** for audit
  defensibility (GUIDANCE; DPDP requires demonstrable consent, doesn't fix the
  number).
- **PII redaction (GUIDANCE, strongly advised):** auto-redact Aadhaar, PAN, card
  numbers, OTPs from transcripts before storage/third-party sharing.
- **Access control (HARD-law outcome via 8(5); GUIDANCE on mechanism):** who
  accessed which recording, when, why; periodic (e.g. quarterly DPO) review.

---

## B. AI DISCLOSURE — the founder collision, precisely scoped

### B1. What is HARD LAW today (in force, June 2026)
- TCCCPR (TRAI) + sectoral codes require, at call open: **caller identity, the
  entity on whose behalf, and the purpose**; plus a **recording disclosure**.
  Examples: RBI collections — within 30s: who you are, what entity, what
  purpose + recording disclosure; IRDAI — "I am calling on behalf of [insurer],
  in my capacity as [agent/intermediary/TPA]."
- TCCCPR also requires telemarketers to **declare use/intended purpose of
  Auto-Dialer / Robo-Calls** to the access provider, and to register/route via
  DLT with proper headers (140-series promotional, 1600-series service/
  transactional). Senders must **self-declare A2P/automated usage to the
  operator** (the network can't tell human vs synthetic voice; onus is on
  sender). This is about telecom-side declaration, **NOT** a scripted
  "I am an AI" to the called person.
- **=> There is NO in-force rule today forcing the AI to tell the human "I am an
  AI/bot."** Founder's hard demand is legally survivable under current law.

### B2. What is PROPOSED / COMING (NOT yet hard law — the horizon risk)
- **TRAI consultation paper on AI-generated / synthetic-voice communications**
  — open for >1 year; not finalized.
- **Proposed TCCCPR amendment** to cover AI-based telemarketing, **AI
  disclosure, and consent-verification systems** (TRAI signaled intent).
- **2026 IT-Rules amendment** push for transparency/labelling of synthetically
  generated content (incl. AI voice).
- Likely outcome (directional, not yet binding): a **mandatory AI-disclosure at
  the start of every commercial call** + synthetic-voice consent + AI-specific
  recordkeeping. Also a proposed **₹0.05/min charge on automated bulk calls**
  (TRAI, Mar 2026 proposal).
- **Design implication for W26:** ship a per-tenant, per-sector **AI-disclosure
  flag** (default OFF to honor founder today; force-ON for BFSI/insurance or the
  moment the TRAI AI rule is notified). Do not hardcode "never say AI" — make it
  a flip so the live earner doesn't become illegal overnight.

---

## C. PENALTIES + DEADLINES (the numbers that gate the earner)

### C1. TCCCPR / TRAI — IN FORCE NOW (the immediate threat)
- Gazette: **TCCCPR Second Amendment, 12 Feb 2025.**
- **Graded financial disincentives:** **₹2 lakh** (1st violation), **₹5 lakh**
  (2nd), **₹10 lakh** (each subsequent). Imposed separately for registered vs
  unregistered senders; levied on access providers too.
- **Suspension / blacklisting:** access providers must **immediately suspend
  traffic** on header/template misuse; suspension persists until the sender
  files with law enforcement + takes prescribed remediation. Repeat offenders →
  **industry-wide unified suspension / permanent disconnection** of telecom
  resources (zero-tolerance).
- **Spam action threshold tightened:** from 10 complaints/7 days to **5
  complaints/10 days** (faster trigger — easier to hit the penalty ladder).
- The "**15-day suspension**" figure cited by some 2026 trade write-ups maps to
  the first-violation suspension consequence in the AI-calling enforcement
  framing; treat ₹10L + suspension/blacklist as the hard worst-case for repeat
  UCC/header misuse. (Secondary-source figure; the gazette text governs.)

### C2. DPDP Act 2023 — penalties enforceable from 13 May 2027
- **Rules notified 14 Nov 2025**, phased over **18 months → full compliance
  13 May 2027.**
- Schedule penalties (per the Act): up to **₹250 crore** — failure to implement
  reasonable security safeguards (8(5)); up to **₹200 crore** — failure to
  notify a breach (Board/principals); up to **₹200 crore** — children's-data
  special-provision breach. (Plus other graded amounts.)
- **Breach notification:** notify the Data Protection Board + affected
  principals (Rules tighten timelines; trade analyses cite ~72h-class duties).
- => DPDP is the *bigger* monetary stick but its enforcement runway is mid-2027;
  TCCCPR is the *now* stick.

---

## D. CONCRETE OBLIGATIONS FOR FAMIT (build checklist for W26)

HARD LAW (must do):
1. Play/state a **consent notice before recording**: identity + entity +
   purpose + "recorded (and analysed)" + opt-out/delete rights. Capture an
   affirmative consent marker; log it. (DPDP 5/6 + TCCCPR identity/recording.)
2. **DLT-register** senders; correct headers; **140 promo / 1600 service**;
   declare auto-dialer/AI usage to the operator. (TCCCPR — avoids ₹2-10L.)
3. **Honor DND / opt-out**; ≥90-day wait before re-consent of opted-out users.
4. **Retention = greater of sectoral floor and purpose-lifetime;** erase on
   purpose-end/withdrawal; complete deletion incl. backups/vendors.
5. **48h pre-erasure notice** (where applicable); **90-day** erasure-request SLA.
6. **Reasonable security safeguards**; access/processing **logs ≥1 year**.
7. **Demonstrable consent records** (versioned notice + per-principal artefact).

GUIDANCE / strongly advised (do, but not yet black-letter):
8. Say "**analysed by AI**" in the recording notice (modality transparency).
9. **Redact** Aadhaar/PAN/card/OTP from stored transcripts.
10. **Per-tenant AI-disclosure flag** (OFF today, force-ON for BFSI/insurance &
    the day TRAI's AI rule is notified) — the founder-collision release valve.
11. Granular consent per data category (raw audio / transcript / biometrics /
    derived intent) where feasible.

---

## E. SOURCES (authoritative + current)

HARD-LAW / OFFICIAL:
- TRAI Gazette — TCCCPR Second Amendment (12 Feb 2025):
  https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf
- TRAI Press Release No.11/2025 (TCCCPR amendment):
  https://trai.gov.in/sites/default/files/2025-02/PR_No.11of2025.pdf
- DPDP Rules 2025 notified — PIB (14 Nov 2025):
  https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf
- DPDP Rule 8 (retention/erasure): https://www.dpdpa.com/dpdparules/rule8.html

LAW-FIRM / ANALYST (interpretation):
- Securiti — India spam rules / TRAI amendment: https://securiti.ai/india-spam-rules-trai-latest-amendment/
- EY — DPDP Act 2023 & Rules 2025 decoded: https://www.ey.com/en_in/insights/cybersecurity/decoding-the-digital-personal-data-protection-act-2023
- VISTA InfoSec — DPDP penalties: https://vistainfosec.com/blog/dpdp-act-non-compliance-penalties/
- ksandk — recording without consent violates Art 21: https://ksandk.com/litigation/recording-calls-without-consent-is-a-violation-of-article-21/
- ksandk — DPDP retention & deletion: https://ksandk.com/data-protection-and-data-privacy/data-retention-and-deletion-under-indias-dpdp-rules/

VOICE-AI-SPECIFIC (operational):
- Caller Digital — Voice AI India regulatory map 2026 (hard vs proposed): https://www.caller.digital/blog/voice-ai-india-regulatory-map-2026
- Caller Digital — DPDP vs TRAI consent for voice recordings: https://www.caller.digital/blog/dpdp-vs-trai-consent-voice-recordings-audit-trail-india-2026
- S.S. Rana & Co — TRAI crackdown on spam/AI telemarketing: https://ssrana.in/articles/trais-crackdown-on-spam-calls-and-ai-driven-telemarketing/
- Recording consent / DPDP call-center: https://www.recordinglaw.com/world-laws/world-data-privacy-laws/india-data-privacy-laws/
