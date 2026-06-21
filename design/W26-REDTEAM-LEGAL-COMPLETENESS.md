# W26 — RED-TEAM: Legal Completeness of the Consent & Regulatory Engine

> **Status:** RED-TEAM / doc-only. No code, no box. 2026-06-18.
> **Target:** `design/W26-COMPLIANCE-CONSENT-ENGINE.md` (the engine spec).
> **Method:** attack the engine for any **missed NOW-obligation** (TRAI/MeitY/DPDP/recording)
> that could still get the live earner *suspended or fined* despite W26 being implemented as written.
> **Inputs cross-checked:** the two W26 law docs + `W18-RESEARCH-call-recording-consent-india.md`
> + fresh web verification (DPDP Rules 2025 enforcement dates, breach/erasure SLAs, WhatsApp opt-in).
> **Scope caveat:** engineering due-diligence, not legal advice; counsel sign-off still gates high-volume.

---

## VERDICT (one paragraph)

W26 is **strong on the TRAI/TCCCPR dial-path** (DLT, number-series, NCPR scrub, window-floor,
consent-freshness) — that is correctly identified as the NOW earner-killer and the gate is well-shaped.
**But the engine has real legal gaps on the DPDP/recording/data layer and on adjacent channels**, several
of which are **NOW or near-NOW** exposures, not "ramp to 2027." The most serious: (G1) the **on-call
affirmative recording-consent capture** is missing — W26 *announces* recording in the opener but never
**captures + logs an affirmative consent marker before the recorder starts**, which is the actual DPDP/
Puttaswamy duty and a civil exposure that exists TODAY independent of the May-2027 penalty date; (G2)
**voiceprint/transcript = biometric + granular-purpose consent** — a single "may be recorded" line does
NOT cover AI-analysis/sentiment/biometric processing; (G3) the **WhatsApp follow-up channel is entirely
absent** from the engine yet is a live part of the product with its own Meta opt-in + 24h-window rules and
DPDP consent; (G4) **no DSAR/grievance/erasure-request intake + 90-day SLA + 48h pre-erasure notice + the
mandatory point-of-contact** — W26 builds the *erasure cascade mechanism* but not the **request lifecycle**
the law actually grades; (G5) **breach-notification (72h to Board + principals)** is unaddressed; (G6) the
**1-year processing-log retention floor COLLIDES with W26's "hash-only, no raw PII" minimisation** and with
the 90-day recording purge — a reconciliation bug. None of these change the "don't say I am an AI" verdict
(that stays resolved), but **6 of them must be added to the engine spec before high-volume**, and 3 are
fixable in the design doc right now. **SHIP the engine's dial-path; do NOT call the engine legally complete
until G1–G6 are folded in.**

---

## SEVERITY LEGEND
- **NOW** = live civil/contractual/constitutional or in-force-statutory exposure today (not gated on May-2027).
- **NEAR** = becomes a graded penalty on a known near date (DPDP substantive provisions 13 May 2027) but the
  *infrastructure must exist before high-volume*, so it is a design-now gap.
- **OPS** = operational earner-kill risk (suspension by operator/Meta action) regardless of statute date.

---

## THE GAPS (concrete issue → concrete fix)

### G1 — [NOW] No on-call affirmative recording-CONSENT CAPTURE (only an announcement)
**Issue.** W26 §4.4 says "Recording notice is carried by the Tier-0 opener (`…may be recorded…`)" and writes
a `recording` consent row *"when the call is recorded."* That is **disclosure, not consent.** The DPDP model
(`W18-RESEARCH` A1/A2) + the Puttaswamy constitutional floor require, **before/at the point of recording**, a
**free, informed, affirmative act** captured as the consent marker — not merely an announcement the recorder
already started behind. Writing the `recording` row *because* the call was recorded is **circular**: it logs
that you recorded, not that the principal agreed. This is a **present-tense civil/tort exposure** (non-
consensual recording of a private conversation is presumptively an Art-21 wrong) that exists **independent of
the May-2027 DPDP penalty date** — i.e. it is NOT covered by the "Tier-B ramps to 2027" posture.
**Fix.**
1. Add an explicit **affirmative-consent capture step** to the opener/turn-1 flow (co-owned W2): the agent
   states the record/analyse notice, then **the first substantive turn proceeds only after an affirmative
   cue** (spoken "haan/yes/theek hai", or DTMF, or an explicit "I'll stop if you say so" + no objection),
   and that cue — with timestamp + the **notice version** — is what writes the `recording` consent row.
2. Engine change: `consent_ledger` should store `notice_version TEXT` and `affirmative_marker TEXT`
   (`'verbal_yes'|'dtmf_1'|'continued_after_optout_offer'`) so the row proves *informed affirmative* consent,
   not "we recorded."
3. **Recorder-start gate:** if recording is ON and no affirmative marker is captured within the opener window,
   either (a) do not start/keep the recording, or (b) flag the call `recording_consent=implied_continuation`
   for the panel — never silently record a refusal. (REC-B egress in `caller.py` must be gated on this.)

### G2 — [NOW/NEAR] "May be recorded" does NOT cover AI-analysis / biometric / sentiment (granular purpose)
**Issue.** Multiple India voice-AI compliance analyses (ConversAI, Caller Digital, Rootle) are explicit: a
**voiceprint is biometric data**, a transcript is PII, and **sentiment/emotion/intent tagging are distinct
processing operations** — a single blanket "recorded for quality" notice **does not cover them**, because
DPDP requires **granular, purpose-specific consent** and "blanket/general consents are no longer valid."
W26's opener says only "*ye call record ho sakti hai*" — it discloses *recording*, not **AI analysis,
transcription, sentiment/intent extraction, or voiceprint processing**, which is exactly what the brain does.
This is the W18-RESEARCH A2 "often-missed point" ("**recorded *and analysed by AI***") — and W26's Tier-0
opener dropped it. This is a NOW best-practice and a NEAR hard duty (Rule 5 notice content, 13 May 2027).
**Fix.**
1. W2 opener (all tiers/langs) must say **"recorded and analysed to help us serve you"** (Hinglish: *"…record
   aur analyse ho sakti hai behtar madad ke liye…"*) — the **analysis modality**, not just "recorded."
2. `consent_ledger.consent_type` must split `recording` into **`recording`** and **`ai_analysis`** (and,
   where voiceprint/biometric is derived, **`biometric`**) so granular per-purpose consent is provable.
3. The notice the brain emits and the **itemised purposes** must be the **DPDP notice content** (what data,
   why, how to exercise rights, how to complain) — see G4. The opener carries the cue; the **full itemised
   notice** is delivered (form/IVR/WhatsApp link) and `evidence_ref` points to it.

### G3 — [NOW/OPS] The WhatsApp follow-up channel is ENTIRELY ABSENT from the engine
**Issue.** The product is explicitly "calls **and follows up on WhatsApp**" (CLAUDE.md, the sales positioning,
the erasure-cascade even lists "WhatsApp logs"). Yet the W26 engine has **zero** WhatsApp compliance surface:
no opt-in ledger, no template-category gate, no 24-hour-window rule, no Meta-policy block. This is a **separate
legal regime** the engine ignores:
- **Meta WhatsApp Business Policy** requires **explicit prior opt-in** before any business-initiated
  **marketing** template, and **business-initiated messages outside the 24-hour customer-care window MUST use a
  pre-approved template** (free-form only inside 24h of the user's last message). Violation = **template
  rejection, quality-rating downgrade, and number ban** — an **OPS earner-kill** by Meta action, parallel to
  TRAI's telecom suspension.
- **DPDP** applies to WhatsApp PII/consent identically (the consent to *call* ≠ consent to *WhatsApp*).
- Note (correct, keep): WhatsApp marketing in India is **NOT** under TRAI DLT (DLT is SMS/voice-only) — so the
  gate is **Meta-policy + DPDP**, not DLT. The engine must not wrongly apply DLT to WhatsApp.
**Fix.**
1. Add a **`whatsapp_optin`** consent_type (channel='whatsapp') to `consent_ledger`; a WhatsApp send is
   **blocked** unless a fresh opt-in row exists for the right **category** (marketing vs utility).
2. Add a **`wa_window` gate**: business-initiated outside 24h ⇒ must bind an **approved template_id** (reuse
   the `dlt_registry.templates` shape, but a **Meta-approved** template set, category-tagged). Free-form only
   inside the 24h window.
3. Surface WhatsApp **opt-in coverage + template-category + quality-rating** in the W14 compliance dashboard,
   and include the WhatsApp opt-out ("STOP") write into the same suppression/`revoked` flow as the call DND.
4. Engine wave-map: this is W26 (channel-symmetric consent) co-owned with the WhatsApp-delivery wave.

### G4 — [NOW/NEAR] No DSAR / grievance lifecycle: 90-day erasure SLA, 48h pre-erasure notice, mandatory point-of-contact
**Issue.** W26 builds the **erasure *mechanism*** (`erasure.cascade(principal_ref)`) but **not the request
lifecycle the law actually grades.** Missing, all from verified DPDP Rules 2025:
- A **request-intake** path (data-principal can ask to **access / correct / erase / withdraw / nominate**) and
  a **grievance-redressal** channel (Sec 8(9): a toll-free number / in-app button / email is the *mandated
  outcome*). W26 has no intake table, no SLA clock.
- **Erasure-request SLA: respond within 90 days.** No timer in W26.
- **48-hour pre-erasure notice** to the principal before scheduled (inactivity-triggered) erasure — a hard
  Rule-8 requirement W26's "purge job" omits (it just deletes past-TTL).
- **Mandatory published point-of-contact / DPO-style contact** for data questions (Rule requires a contact
  in the notice). W26 never states where this lives.
- **Inactivity-triggered erasure** (the principal "has not engaged within the retention period") — Rule 8
  mandates erasure on *inactivity*, which is a different trigger than purpose-end/withdrawal that W26 models.
**Fix.**
1. New table **`data_request_ledger`** (FORCE-RLS, same shape): `request_type` (access|correct|erase|withdraw
   |nominate|grievance), `received_at`, `due_at` (received + 90d), `status`, `principal_ref`, `evidence_ref`.
   The erasure cascade is **triggered by** an `erase` row and stamps it complete; the **SLA clock** alarms the
   tenant + super-admin before `due_at`.
2. Purge job adds a **48h pre-erasure notice** step (write a `pending_erase` notice + wait ≥48h) for
   inactivity-triggered deletes.
3. Engine resolves a **point-of-contact** per tenant (config in `dlt_registry` or a new `tenant_compliance`
   row: `grievance_contact`, `dpo_contact`) and the brain's notice/opener exposes "you can opt out or ask us
   to delete your data — contact {X}."
4. W14 dashboard: a **DSAR/grievance queue** with the 90-day countdown (founder rule: frontend CRUD for every
   compliance capability).

### G5 — [NEAR] No data-breach detection + 72-hour notification path
**Issue.** DPDP Rules 2025 (verified): on a personal-data breach the Data Fiduciary must notify the **Data
Protection Board + affected Data Principals within 72 hours** (with nature/extent/timing/remediation), penalty
**up to ₹200 crore** for failure. W26 stores recordings/transcripts/voiceprints/PII but has **no breach-
notification obligation, runbook, or contact path** anywhere. The Board is **operational NOW** (Rules 17–21 in
force 13 Nov 2025), even though the penalty plane matures May-2027 — so the runbook should exist before volume.
**Fix.** Add a **breach-notification runbook** to the engine spec (not code): a `breach_register` row + a
72-hour notification workflow (Board portal + affected-principal notice templates) wired to the security/audit
layer; reference it from W14. Lightweight (a documented procedure + a table), but it must be named — right now
it is a silent zero.

### G6 — [NOW] The 1-year processing-log floor COLLIDES with W26's hash-only minimisation and 90-day purge
**Issue.** Two W26 design choices contradict a verified DPDP Rule 8 requirement:
- W26 stores **only salted hashes, no raw PII** in compliance tables (good for minimisation) **and** purges
  recordings at **90 days** (§4.4 default).
- But Rule 8 sets a **mandatory floor: traffic data + processing logs retained ≥1 year** from processing (for
  detection/investigation), and `W18-RESEARCH` A3 confirms **access/processing logs ≥1 year**. A 90-day
  recording purge is fine, but the **processing/consent/access logs must survive ≥1 year**, and "hash-only"
  can defeat the **demonstrable-consent** duty if the hash can't be tied back to the principal during a DSAR.
- Also: W26's **`compliance_audit` retention is "≥6 months (UCC)"** — that is the TRAI floor, but the **DPDP
  processing-log floor is ≥12 months**, which is *longer*. Using 6 months under-retains for DPDP.
**Fix.**
1. Set the **engine log/audit retention floor to the GREATER of (TRAI 6mo, DPDP 12mo) = 12 months** for
   `compliance_audit` and any processing/consent/access logs. State it explicitly.
2. Keep hash-only at rest, **but** ensure the **consent_ledger keeps `lead_id` (already does)** so consent is
   *demonstrable per principal* during a DSAR — minimisation must not break the demonstrable-consent duty.
3. Reconcile retention as **GREATER OF (sectoral floor, DPDP purpose-lifetime, 1-yr log floor)** — W26's flat
   "recordings 90d / transcripts 180d" **under-retains for regulated tenants**: RBI collections ≥90d (best
   12mo+), IRDAI insurance ≈3yr+, NMC telemedicine ≈3yr (`W18-RESEARCH` A3). The purge job must take the
   **per-tenant-vertical max**, never a flat 90/180.

---

## SECONDARY / TIGHTENING (lower severity, fold in)

### S1 — [OPS] DND cache-miss "block-and-requeue" is a self-inflicted availability hole
W26 §3.3 blocks-and-requeues on a `dnd_cache` miss (fail-closed, correct for legality). But with a cold cache
or a slow/operator-down scrub API, this **silently stalls the whole dialer** — an earner-availability bug
dressed as compliance. **Fix:** add a **bounded async pre-scrub** (scrub the campaign list at enqueue, not at
dial), a **scrub-API health alarm**, and a clear panel state "N leads awaiting DND scrub" so a stall is visible
and bounded, never a silent dial-stop.

### S2 — [NOW] Consent to PLACE the call (TCCCPR) vs the DND override needs the "explicit-consent register"
W26 lets a fresh **explicit** consent row override NCPR/DND (§4.2). Correct in principle, but the Feb-2025
amendment ties DND override to **registered, time-boxed, category-scoped consent** (explicit-txn = 7 days,
inferred = contract duration). **Fix:** the `consent_gate` override must verify the consent row's
**`basis`+`scope`+`expires_at`** match the **promo category** the number opted out of — not any fresh row.
A generic consent must NOT override a category-specific DND.

### S3 — [NEAR] Cross-border / data-residency is asserted but not gated
W26 §4.4 says "data kept in-region (DO blr1)" — but several sub-processors are **US-stored**: LiveKit Cloud
observability (US, 30-day auto-delete; flagged L3 in W18), and any US LLM/STT/TTS vendor sees the **transcript/
audio in transit**. DPDP Rule on cross-border transfer (Rules 3,5-16, 13 May 2027) + the government's power to
restrict transfers means **transcript/PII flowing to a US model is a transfer**. **Fix:** add a
**sub-processor/data-flow register** (which vendor sees what PII, where) to the engine spec; it is the artifact
counsel + the DPDP notice both need, and it is currently missing.

### S4 — [NOW] "Wrong number / not the consenting principal" is unhandled
If the dialed number reaches **someone other than the lead** (reassigned number, family member), continuing to
process/record is processing a **non-consenting** principal. **Fix:** the brain must **verify it's reaching the
intended person** before the substantive turn ("Am I speaking with {name}?"), and a mismatch ⇒ no recording/no
pitch + suppression-write. Cheap, NOW, and currently absent.

### S5 — [TRACK] Per-minute automated-call levy + AI-disclosure amendment are correctly NOT-gated — keep tracking
W18 flagged a proposed **₹0.05/min levy on automated bulk calls** (TRAI, Mar-2026) and the AI-self-ID
amendment. W26 correctly does **not** gate on these (Tier-C). **Keep:** the Tier-2 flip already future-proofs
the AI-disclosure line; add a one-line cost note that the levy, **if** notified, changes per-call unit
economics (a billing/pricing input, not a dial gate).

---

## WHAT W26 GOT RIGHT (so the build doesn't over-correct)
- **TRAI is the NOW earner-killer, not DPDP** — correct, and the complaint-rate monitor + auto-throttle (§4.5)
  is correctly named the single highest-leverage operational control.
- **Calling-window 09:00–21:00 → clamp to 10:00–19:00 legal floor** — correct and the right first dial-path fix.
- **Number-series (140/1600) + DLT PE + auto-dialer pre-notification as hard NOW gates** — correct.
- **Consent freshness AT DIAL TIME (explicit 7d / inferred contract)** — correct and well-modelled.
- **The "don't say I am an AI" collision stays resolved** — Tier-0 default + Tier-2 dormant flip is sound; no
  in-force law forces the banned phrase. **None of the gaps above re-open that verdict.**
- **Fail-closed on Tier A, flag-gated default-OFF until DLT registered, byte-identical resting build** — the
  earner-safety posture is right.

---

## CORRECTION TO W26's DPDP FRAMING (precision, verified)
W26 labels all DPDP as "Tier-B, enforcement ramps to ~May-2027." **Verified nuance:**
- **DPDP substantive obligations (Rules 3, 5–16, 22, 23: notice, consent, rights, security, retention/erasure,
  children, cross-border) = enforceable 13 May 2027.** So the *penalty plane* timing in W26 is right.
- **BUT the Data Protection Board is operational NOW** (Rules 17–21, since 13 Nov 2025), and **recording-consent
  is a NOW exposure via the constitutional/contract floor (Puttaswamy), independent of the 2027 date** — it is
  not safe to treat *all* recording/consent as "ramps later." G1/G2 are **NOW**, not 2027.
- **Consent-manager registration = 13 Nov 2026** (a separate near date W26 doesn't mention; relevant because
  DPDP consent may later have to be **routed through a registered Consent Manager** — track for the consent
  ledger's external interface).

---

## SHIP DECISION
**Dial-path engine (TRAI/DLT/NCPR/window/consent-freshness): SHIP** — it is the correct NOW gate and well-built.
**Legal-completeness of the full engine: NOT clean — fold in G1–G6 (and S1–S4) before high-volume.** G1, G2,
G3, G6, S2, S4 are **NOW**; G4, G5, S3 are **near (13-May-2027 plane) but design-now**. Three are pure doc
fixes (G2 wording, G6 retention reconciliation, the DPDP framing correction); the rest add tables/flows the
build waves must own. After these are in the spec, the engine is legally complete to the standard of
engineering due-diligence — **counsel sign-off (§9) still gates the first high-volume campaign.**

---

### Sources (this red-team's new verifications)
- DPDP Rules 2025 — enforcement-date phasing (Rules 17–21 in force 13 Nov 2025; Rule 4 / consent-manager 13 Nov
  2026; Rules 3,5–16,22,23 substantive 13 May 2027): https://www.amsshardul.com/insight/enforcement-of-the-dpdp-act-and-notification-of-the-dpdp-rules/ · https://www.taxmann.com/post/blog/analysis-indias-dpdp-act-and-rules · https://www.seclore.com/fundamentals/dpdp-rules-2025-compliance-guide/
- DPDP breach notification 72h to Board + principals; ₹200cr tier: https://www.medianama.com/2025/11/223-data-breach-reporting-timeline-of-dpdp-rules-2025-explained/ · https://www.consently.in/blog/dpdp-breach-notification-template-response-playbook-india
- Rule 8 retention/erasure — 48h pre-erasure notice, 90-day DSAR SLA, ≥1-yr processing-log floor, inactivity
  trigger: https://www.dpdpa.com/dpdparules/rule8.html · https://tsaaro.com/blogs/dpdp-rules-2025-explained-full-overview-and-practical-summary
- Granular/biometric/AI-analysis consent (voiceprint = biometric; blanket "recorded for quality" insufficient;
  itemised notice; grievance Sec 8(9)): https://www.conversailabs.com/blog/voice-ai-compliance-in-india · https://www.caller.digital/blog/dpdp-act-compliance-checklist-voice-ai-india · https://rootle.ai/voice-ai-compliance/
- WhatsApp India: Meta opt-in + 24h-window + template approval; WhatsApp marketing NOT under TRAI DLT, governed
  by Meta policy + DPDP: https://www.messagecentral.com/blog/whatsapp-business-api-india-guide · https://www.enchant.com/whatsapp-business-platform-24-hour-rule · https://www.infobip.com/docs/whatsapp/compliance/template-compliance
- TCCCPR 2025 — 140/1600 series, binding access-provider↔sender agreements, ₹2L/₹5L/₹10L, header/template
  suspension: https://securiti.ai/india-spam-rules-trai-latest-amendment/ · https://exotel.com/blog/tcccpr-140-1600-headers-the-2025-compliance-guide-every-enterprise-needs/
- (Grounded on the prior W26 law docs + `W18-RESEARCH-call-recording-consent-india.md`, which carry the primary
  TRAI gazette + DPDP Rules citations.) Engineering due-diligence, not legal advice.
