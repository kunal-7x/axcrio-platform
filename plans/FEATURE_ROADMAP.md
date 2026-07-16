# Famit — Production-Grade Outbound AI Calling Platform: Feature Roadmap

> Platform: FastAPI backend (DigitalOcean droplet) + LiveKit/Vobiz voice agent (Groq LLM, ElevenLabs Flash TTS, Sarvam STT) + Next.js panel  
> Use case: Outbound AI tele-calling SaaS for Indian real-estate; Hinglish agent "Riya" calls leads, qualifies, books site visits  
> Research date: June 2026 | Status: Pre-production → Production readiness gap analysis

---

## LEGEND
- **Effort**: Quick-win (days) / Medium (1–3 weeks) / Large (1–2 months)
- **P0**: Must-have before any real vendor goes live (legal liability or total product failure without it)
- **P1**: High-value differentiators; serious vendors will demand these
- **P2**: Nice-to-have; competitive moat, quality-of-life

---

## P0 — MUST-HAVE FOR PRODUCTION

### 1. TRAI Telemarketer Registration + DLT Onboarding
**What it is:** All entities making commercial outbound calls in India must register as a Telemarketer on the DLT (Distributed Ledger Technology) platform operated by TSPs (Airtel, Jio, BSNL). Issued a unique Registration ID used in all call metadata. As of September 2024, 140-series calls must be DLT-logged per TRAI mandate.  
**Why it matters:** Without registration, telecom operators will disconnect all lines and blacklist the entity for up to 2 years. Five complaints in ten days triggers action under the February 2025 TRAI amendment. This applies to Famit as the platform and every vendor client using it.  
**Effort: Medium**  
*Hint:* Register Famit as a Telemarketer on DLT; require vendor clients to register as Senders and supply their Sender ID + Registration ID before a campaign goes live. Enforce this as a campaign pre-flight check in the backend.

---

### 2. 140-Series Number Procurement + Calling Hours Enforcement
**What it is:** Outbound promotional calls in India must originate from the 140-series number range (160-series for transactional/service calls). Using regular 10-digit numbers for commercial calls is illegal and triggers immediate disconnection. Calling window: 9 AM – 9 PM IST only.  
**Why it matters:** Any call Riya makes from a non-140 number is a TRAI violation. Getting blacklisted means the entire platform goes dark for all vendors.  
**Effort: Medium**  
*Hint:* Procure 140-series virtual numbers via a licensed CPaaS partner (Exotel, Ozonetel, Knowlarity, or directly via TSP). In the campaign scheduler, add a hard gate: reject any campaign start time outside 09:00–21:00 IST and auto-pause active campaigns at 20:55 IST.

---

### 3. NCPR/DND Scrubbing Before Every Campaign Run
**What it is:** All outbound lead lists must be scrubbed against TRAI's National Customer Preference Register (NCPR) before dialling. Numbers registered for DND cannot be called for promotional purposes. TRAI mandates at minimum weekly scrubbing; best practice is per-campaign.  
**Why it matters:** Calling a DND-registered number is a direct TRAI violation carrying penalties and eventual blacklisting. Each vendor's campaign could contain hundreds of DND numbers.  
**Effort: Medium**  
*Hint:* Integrate with a scrubbing API provider (MSG91, Exotel, or direct NCPR API). Add a pre-run scrubbing step in campaign execution: mark DND leads as `status=excluded_dnd`, never dial them, and show the vendor a pre-dial exclusion count in the UI.

---

### 4. Consent Management + Opt-Out Handling (DPDP Act 2023)
**What it is:** The Digital Personal Data Protection Act 2023 requires free, specific, informed, unambiguous consent before processing personal data for marketing. Data Principals have the right to withdraw consent at any time. Violations carry penalties up to ₹250 crore per incident. Riya's voice recordings contain biometric PII (voiceprint + speech patterns) and transcripts contain spoken PII — both are covered.  
**Why it matters:** Every vendor using Famit is a Data Fiduciary. Famit as the processor is contractually liable if it lacks adequate controls. Consent violations, unhonorable opt-outs, and data breaches all trigger DPDP enforcement.  
**Effort: Medium**  
*Hint:* (a) Add a consent source field to the lead upload schema (web form, IVR, walk-in, etc.); (b) Riya must announce herself as an AI agent at call start and offer "press 1 to opt out / say 'no calls'"; (c) on opt-out detection (keyword or DTMF), immediately mark lead `status=opted_out` and never redial; (d) expose a vendor-facing "forget me" endpoint that cascades deletion across leads, transcripts, recordings.

---

### 5. Call Recording Disclosure + Retention Policy
**What it is:** Under DPDP Act, call recordings are personal data. Consent to record must be given (or best-practice disclosure made at call start). Retention: recordings should not be held beyond necessity; Indian BPO/telemarketing practice uses 6 months as a safe default. Recordings must be encrypted at rest (AES-256), TLS 1.3 in transit, and access-logged.  
**Why it matters:** Currently transcripts and likely audio blobs are stored without defined retention or encryption policies. A data breach or a DPDP complaint with no retention policy is a direct liability.  
**Effort: Quick-win**  
*Hint:* Add a recording disclosure line to Riya's opening script ("Yeh call record ki ja rahi hai"). Implement a nightly job to delete recordings + transcripts older than the configured retention window (default 180 days, vendor-configurable). Ensure DO Spaces/S3 bucket uses server-side AES-256 and that access is IAM-gated.

---

### 6. Answering Machine / Voicemail Detection (AMD)
**What it is:** AMD automatically detects whether the call was answered by a human or a voicemail/IVR system before Riya starts speaking. Without it, Riya delivers her pitch to a voicemail recording, wasting minutes, inflating costs, and burning the lead.  
**Why it matters:** In India, mobile carrier voicemail rates are high; missed-call-and-callback patterns are common. Without AMD, a significant fraction of "answered" calls are wasted on machines, distorting conversion metrics and costing ElevenLabs TTS credits.  
**Effort: Medium**  
*Hint:* Implement AMD via Twilio's `MachineDetection=Enable` or equivalent Exotel API param; on `machine` result, drop the call or play a pre-recorded callback prompt. Log AMD outcome per call for analytics.

---

### 7. Basic Call-Level Audit Log + Immutable Event Trail
**What it is:** Every significant system action (campaign created, lead called, opt-out processed, recording accessed, user login, config changed) must be logged immutably with timestamp, actor, and payload.  
**Why it matters:** DPDP Act mandates demonstrable compliance. Regulators, enterprise vendors, and legal counsel will demand logs. Currently unlogged actions create a "no evidence = no defense" problem.  
**Effort: Quick-win**  
*Hint:* Append-only `audit_log` Postgres table (id, tenant_id, actor_id, action, resource_type, resource_id, metadata_json, created_at). Index on (tenant_id, created_at). Never delete rows; archive to cold storage after 12 months.

---

### 8. Data Encryption at Rest + Secrets Management
**What it is:** PII in the database (phone numbers, names, transcripts), call recordings on object storage, and API keys/secrets in config must all be encrypted. Credentials must not be in plaintext env files on the droplet.  
**Why it matters:** A single droplet compromise currently exposes all vendor data. DPDP "reasonable safeguards" requirement means negligent storage = penalty.  
**Effort: Medium**  
*Hint:* Use pgcrypto or Postgres-level column encryption for phone/name fields. Migrate secrets to DO Managed Secrets or HashiCorp Vault. Rotate ElevenLabs/Groq/Sarvam API keys per-tenant rather than using a global key.

---

## P1 — HIGH-VALUE (Vendors Will Demand These)

### 9. Smart Retry Logic + Backoff with Calling-Window Awareness
**What it is:** When a lead doesn't answer, the system should retry with intelligent backoff (e.g., +2h, +6h, next day) but only within the 9AM–9PM window. Maximum retry cap per lead (e.g., 3 attempts) with configurable intervals per campaign.  
**Why it matters:** Without retry logic, unanswered calls are permanently abandoned. In Indian real-estate, leads answer calls at peak times (morning and evening); random retry wastes attempts and burns carrier costs.  
**Effort: Quick-win**  
*Hint:* Add `retry_count`, `next_retry_at`, `max_retries` fields to the leads table. A scheduler job (APScheduler or Celery beat) checks for `next_retry_at <= now()` and enqueues dials, capped at the calling window.

---

### 10. Callback Scheduling ("Call me back at 6 PM")
**What it is:** When a lead says "call me back later" or names a specific time, Riya should capture the time, confirm it, and the system should schedule the callback precisely. Lead status becomes `callback_scheduled` with the requested slot.  
**Why it matters:** "Call me after 5 PM" is the single most common lead response in Indian real estate. Without callback scheduling, this intent is lost and the lead is marked as a non-connect.  
**Effort: Medium**  
*Hint:* Add a Groq function-call tool `schedule_callback(datetime_iso)` to the Riya agent. On tool invocation, write to a `callbacks` table. Scheduler picks it up and dials at that time. Send the lead an SMS confirmation via Twilio/MSG91.

---

### 11. WhatsApp Follow-Up After Call
**What it is:** After a completed call, automatically send a WhatsApp message to the lead: site visit details if qualified, property brochure link, or a simple re-engagement message for no-answers. Uses WhatsApp Business API.  
**Why it matters:** In India, WhatsApp has ~500M users and open rates far exceed SMS. Competitors (SquadStack, Bolna) already offer voice+WhatsApp combos. Real estate developers expect leads to receive a WhatsApp with project details immediately after qualification.  
**Effort: Medium**  
*Hint:* Integrate with WhatsApp Business API via a BSP (Gupshup, Interakt, or 360Dialog). Add a post-call webhook trigger that fires template messages based on call outcome (qualified → send site-visit template; no-answer → send brochure template). Vendor can configure message templates per campaign in the panel.

---

### 12. SMS Follow-Up + Missed Call SMS
**What it is:** When a call goes unanswered (AMD=machine, or rings out), send a short SMS: "Namaste [Name], Riya from [Project] called you. [Project URL] or reply CALL to schedule a callback."  
**Why it matters:** Missed-call + SMS is a high-conversion Indian engagement pattern. Low cost ($0.01/SMS), high ROI, and keeps the lead warm without a re-dial cost.  
**Effort: Quick-win**  
*Hint:* Post-AMD or post-no-answer webhook → MSG91/Twilio SMS API with a registered DLT template. Track SMS delivery and link clicks (use a redirect URL with UTM params per lead).

---

### 13. Real-Time Campaign Analytics Dashboard
**What it is:** Live metrics per campaign: total leads, dials attempted, connected, qualified (site-visit booked), not-interested, no-answer, AMD/voicemail, opt-out, callbacks pending. Conversion funnel visualization (dials → connects → qualified → site-visit confirmed).  
**Why it matters:** Vendors currently have no real-time visibility into campaign performance. A real estate developer spending ₹50,000/month expects to see live conversion rates. Without this, churn is immediate.  
**Effort: Medium**  
*Hint:* Add materialized views or a Redis counter layer for fast aggregation. Build a `/api/campaigns/{id}/analytics` endpoint returning bucketed metrics. Frontend: simple funnel chart (Recharts or Chart.js) updated every 30s via polling or WebSocket.

---

### 14. Lead Scoring + Intent Classification
**What it is:** After each call, automatically score the lead (1–10) based on expressed interest signals: budget mentioned, timeline stated, location preference, asked for brochure, agreed to site visit. Expose score in the lead table and use it to prioritize retries.  
**Why it matters:** Currently all leads are treated equally. A lead who said "budget 80 lakhs, looking to buy in 3 months" is worth 10x a "just looking" contact — but without scoring, both get the same follow-up cadence. Vendors need this to manage their sales team's time.  
**Effort: Medium**  
*Hint:* Post-call, run a Groq inference pass on the transcript with a structured scoring prompt extracting: budget (yes/no/amount), timeline (yes/no/months), location preference, site-visit consent. Store in `lead_qualification_score` JSON column. Show in the leads table with color-coded badges.

---

### 15. AI Sentiment + QA Scoring per Call
**What it is:** Automated quality scoring on every call: (a) sentiment trajectory (positive → neutral → negative), (b) Riya's script adherence (did she cover all mandatory qualification questions?), (c) flagging aggressive or confused calls for human review.  
**Why it matters:** Vendors need assurance that the AI is performing consistently. QA scoring surfaces calls where Riya failed, enabling prompt/voice iteration. Sentiment analysis catches leads who were frustrated or hung up angrily.  
**Effort: Medium**  
*Hint:* Post-call Groq batch job: structured prompt on transcript → output JSON {sentiment: positive/neutral/negative, script_compliance: 0-100, flags: []}. Store in `call_qa` table. Add a QA review UI tab in the call logs panel.

---

### 16. Human Escalation / Warm Transfer
**What it is:** During a live call, if the lead explicitly asks for a human, expresses frustration, or triggers a defined escalation keyword, Riya transfers the call to a human sales agent with full conversation context (transcript so far, lead name, lead score, campaign brief).  
**Why it matters:** AI cannot close every conversation. For high-value real estate, some leads demand human follow-through. Without escalation, these leads are lost permanently — the exact opposite of what a developer pays for.  
**Effort: Large**  
*Hint:* Add a LiveKit SIP transfer action triggered by escalation intent detection in Groq. Pass conversation context via SIP headers or a real-time context push to the receiving agent's browser tab. Start with a "request callback from human" flow before full live transfer.

---

### 17. CRM Integration + Webhook Outbound
**What it is:** After each call, push lead outcome, transcript summary, score, and next action to the vendor's CRM (Salesforce, HubSpot, LeadSquared, PropTech-specific tools like Sell.do or Kylas). Also emit webhook events for campaign milestones.  
**Why it matters:** Large real-estate developers already have CRMs. If Famit can't push qualified leads directly into their pipeline, they'll use a competing solution. Webhooks also enable custom automation (e.g., Zapier → Sheets).  
**Effort: Medium**  
*Hint:* Build a generic webhook delivery system (retry-on-fail with exponential backoff, HMAC signature). Implement first-class LeadSquared and Kylas connectors (most used in Indian real estate). Offer a Zapier-compatible REST webhook format for others.

---

### 18. Role-Based Access Control (RBAC) — Multi-Tenant
**What it is:** Within a vendor account: Owner (full access), Manager (can see all campaigns, cannot delete), Agent/Viewer (read-only call logs for their assigned campaigns). Across tenants: complete data isolation.  
**Why it matters:** Currently any user in a vendor account likely has full access. Enterprise vendors (e.g., a developer group with multiple projects) need segregation. DPDP data fiduciary accountability requires demonstrable access controls.  
**Effort: Medium**  
*Hint:* Add `role` enum to `tenant_user` table (owner, manager, viewer). Implement FastAPI dependency injection middleware that enforces role per endpoint. Add campaign-level user assignment for fine-grained scoping.

---

### 19. Concurrency + Rate Limiting Per Vendor
**What it is:** Enforce a max concurrent calls per vendor account (e.g., free tier: 5, pro: 50, enterprise: 500). Rate-limit campaign launch to avoid blasting all leads simultaneously. Per-account call minute quotas tied to billing tier.  
**Why it matters:** Uncapped concurrency on a shared droplet will crash the LiveKit/Vobiz agent for all vendors simultaneously. Carrier-level dialling limits also exist (~10 CPS per number). Without metering, there is no basis for billing or tier differentiation.  
**Effort: Medium**  
*Hint:* Redis-based concurrent call counter per tenant (`INCR tenant:{id}:active_calls` / `DECR` on call end). Reject new dials when limit exceeded. Add `call_minutes_used` counter and a billing cap check on campaign start.

---

### 20. Cost / Usage Metering + Basic Billing
**What it is:** Track per-vendor per-campaign: total call minutes (telephony cost), ElevenLabs TTS characters, Groq inference tokens, Sarvam STT minutes. Display usage in the vendor panel and generate monthly invoices or trigger credit depletion alerts.  
**Why it matters:** Currently there is no metering — Famit absorbs all AI API costs without knowing per-vendor spend. Without this, the business cannot price correctly, will lose money on large campaigns, and cannot enforce plan limits.  
**Effort: Medium**  
*Hint:* `usage_events` table (tenant_id, event_type, quantity, unit_cost, campaign_id, created_at). Emit events from call lifecycle hooks. Build a monthly rollup job. Show a usage dashboard tab per vendor. Integrate Razorpay/Stripe India for prepaid credit top-ups.

---

## P2 — NICE-TO-HAVE (Competitive Moat)

### 21. A/B Testing of Scripts and Voices
**What it is:** Split-test two campaign variants (different opening lines, different voice, different qualification question order) and automatically route leads to each variant, tracking conversion rates per variant to determine winner.  
**Why it matters:** Script quality is the #1 driver of site-visit conversion rate. Systematic A/B testing is how professional contact centers improve over time. Differentiates Famit from basic dialler tools.  
**Effort: Large**  
*Hint:* Add a `campaign_variant` concept (parent campaign, variant A/B). Round-robin lead assignment at campaign run time. Aggregate funnel metrics per variant. Auto-declare winner at statistical significance (basic p-value check).

---

### 22. Intelligent Time-of-Day Optimization
**What it is:** Instead of blasting all leads at campaign start, the scheduler uses historical connect-rate data (from past campaigns on this platform) to dial each lead at the time-of-day when similar leads in that geography are most likely to answer.  
**Why it matters:** In Indian real estate, connect rates vary strongly by time: salaried leads answer during lunch (1–2 PM) and evening (6–8 PM); investors answer in morning (10 AM–12 PM). Smart scheduling can double connect rates without spending more on dials.  
**Effort: Large**  
*Hint:* After accumulating 1,000+ call records, build a connect-rate model by (hour, day-of-week, lead_type). Use it to score available dial slots and prioritize. Initially use heuristics (hardcoded time buckets based on Indian patterns).

---

### 23. Sentiment-Based Live Alert + Manager Notification
**What it is:** During a live call, if Riya's real-time sentiment analysis detects sustained negativity or an angry caller, immediately send a push/email alert to the vendor's campaign manager with a link to monitor the live call.  
**Why it matters:** Prevents PR disasters (lead records and shares an angry AI call). Gives managers the ability to intervene on high-value distressed leads.  
**Effort: Large**  
*Hint:* Real-time transcript streaming from LiveKit → lightweight sentiment classifier (small BERT/Groq) → if negative sustained for 3 consecutive utterances, fire webhook to notification service (email + in-app).

---

### 24. Voicemail Drop
**What it is:** When AMD confirms a voicemail, instead of hanging up, Riya plays a pre-recorded natural-sounding message ("Hi, this is Riya calling about [Project]…") and leaves it on the answering machine. Lead receives a personalized-sounding voicemail without using live agent time.  
**Why it matters:** Voicemail drops drive inbound callbacks. In markets where voicemail is used (certain smartphone users), a compelling voicemail generates 5–15% callback rates vs. 0% for silent drops.  
**Effort: Quick-win**  
*Hint:* Pre-generate per-campaign ElevenLabs voicemail audio at campaign creation. On AMD=machine detection, play the audio file instead of connecting the live agent.

---

### 25. Multi-Language / Multi-Voice Per Campaign
**What it is:** Allow vendors to configure a different Riya voice (or a "Raj" male voice) and language per campaign — Hindi, Tamil, Telugu, Marathi, Bengali — beyond the current Hinglish default. Different real estate developers target different regional markets.  
**Why it matters:** A Bangalore developer targeting South Indian buyers needs Kannada/Telugu; a Mumbai luxury developer may need English. Bolna and SquadStack already offer 10+ Indian languages. This is a table-stakes feature for national expansion.  
**Effort: Medium**  
*Hint:* Abstract the LLM prompt language, ElevenLabs voice ID, and Sarvam STT language into campaign-level config. Add a language selector in the campaign creation UI. Test Sarvam STT accuracy per language before enabling.

---

### 26. Lead Import from Property Portals (99acres, Housing.com, MagicBricks)
**What it is:** Auto-import new leads arriving in the vendor's 99acres/Housing.com/MagicBricks inbox directly into Famit campaigns via API or email parsing. Lead enters and is auto-dialled within 60 seconds of portal enquiry.  
**Why it matters:** Speed-to-dial is the #1 conversion driver in real estate lead management. 78% of leads convert with the company that responds first. Manual CSV upload introduces delays of hours.  
**Effort: Large**  
*Hint:* 99acres and Housing.com have lead APIs (paid tier) or email-to-lead webhook options. Build a per-vendor email parsing inbox (unique address) that parses incoming lead notification emails and creates leads automatically.

---

### 27. Campaign Pause / Resume on Complaint Detection
**What it is:** If a vendor's campaign receives elevated DND complaints (approaching TRAI's 5-in-10-days threshold) or a spike in call drops, automatically pause the campaign and alert the vendor to review the lead list.  
**Why it matters:** Proactively prevents TRAI action. Currently a rogue vendor uploading an unscrubbable list would burn the entire platform's 140-series registration.  
**Effort: Medium**  
*Hint:* Track complaint events per campaign. At 3 complaints, warn. At 5, auto-pause and notify vendor + Famit admin. Add a complaint webhook from the TSP/CPaaS provider.

---

### 28. Data Residency — Indian Data Center
**What it is:** Ensure all call recordings, transcripts, and PII are stored in Indian data centers. The DPDP Act mandates data localisation for sensitive personal data; cross-border transfer requires government-approved destination countries.  
**Why it matters:** Currently on a DO Bangalore droplet which is fine, but third-party APIs (ElevenLabs, Groq) may process PII outside India. Vendor contracts will increasingly include data residency clauses.  
**Effort: Medium**  
*Hint:* Audit each API call for whether PII leaves India. For TTS (ElevenLabs), only the script text (not caller data) is sent — acceptable. For STT (Sarvam), audio is sent — check Sarvam's data processing addendum. Store all outputs in DO Bangalore. Document the data flow map for vendor DPAs.

---

### 29. Breach Notification Workflow
**What it is:** Under DPDP Act, data breaches must be reported within 72 hours. The platform needs automated detection (unusual access, bulk export, account takeover) and a templated notification workflow to inform affected vendors and data principals.  
**Why it matters:** Without this, a breach discovered after 72 hours triggers automatic DPDP penalty. The platform must have a documented procedure.  
**Effort: Medium**  
*Hint:* Add alerting on anomalous bulk queries (>1000 rows in <60s), unusual login geos, and failed auth spikes. Build a breach notification email template. Designate a DPO contact in vendor onboarding docs.

---

### 30. Data Principal Rights Portal (Access / Correct / Delete)
**What it is:** A simple self-serve portal (or email workflow) where an individual can submit an access, correction, or deletion request for their personal data held in Famit. Required under DPDP Act Section 11–13.  
**Why it matters:** As Famit scales to millions of dials, it will receive data rights requests from leads. Without a process, each request is manual overhead and potential non-compliance.  
**Effort: Medium**  
*Hint:* Build a `data_requests` table and a public-facing form (`/data-rights`). Requests route to the relevant vendor and to Famit admin. Implement a cascade-delete function that removes a phone number across leads, transcripts, recordings, and audit logs (with tombstone record for compliance).

---

## PRIORITIZED IMPLEMENTATION ORDER

| Priority | Item | Effort | Why First |
|---|---|---|---|
| P0.1 | TRAI/DLT Registration + 140-series numbers | Medium | Platform-killing legal risk without it |
| P0.2 | NCPR/DND Scrubbing | Medium | Every campaign run is a violation risk |
| P0.3 | Calling window enforcement (9AM–9PM) | Quick-win | Trivially enforced, high penalty |
| P0.4 | Consent + Opt-out handling in Riya | Medium | DPDP ₹250Cr penalty exposure |
| P0.5 | Call recording disclosure + retention | Quick-win | DPDP data minimisation |
| P0.6 | Audit log (immutable) | Quick-win | Demonstrable compliance |
| P0.7 | Encryption at rest + secrets rotation | Medium | DPDP reasonable safeguards |
| P0.8 | AMD (Answering Machine Detection) | Medium | Cost bleed + analytics distortion |
| P1.1 | Smart retry + backoff | Quick-win | Highest ROI feature after compliance |
| P1.2 | Real-time analytics dashboard | Medium | Vendor churn prevention |
| P1.3 | Lead scoring + intent classification | Medium | Core product value, differentiator |
| P1.4 | WhatsApp follow-up | Medium | Indian market expectation |
| P1.5 | Callback scheduling | Medium | Biggest missed conversion in India |
| P1.6 | CRM integration + webhooks | Medium | Enterprise vendor requirement |
| P1.7 | Concurrency limits + usage metering | Medium | Business viability / billing |
| P1.8 | RBAC multi-tenant | Medium | Enterprise vendor requirement |
| P1.9 | SMS follow-up on missed calls | Quick-win | High ROI, low effort |
| P1.10 | AI QA/sentiment scoring | Medium | Product quality assurance |
| P2.1 | Human escalation / warm transfer | Large | High-value but complex |
| P2.2 | A/B testing scripts/voices | Large | Moat, do after core |
| P2.3 | Multi-language/voice per campaign | Medium | National expansion |
| P2.4 | Portal lead import (99acres etc.) | Large | Speed-to-dial killer feature |
| P2.5 | Data residency audit + DPA | Medium | Enterprise compliance |
| P2.6 | Data Principal rights portal | Medium | DPDP future-proofing |
| P2.7 | Breach notification workflow | Medium | DPDP 72hr rule |
| P2.8 | Intelligent time-of-day optimization | Large | Moat, needs data flywheel |

---

## COMPETITIVE LANDSCAPE SNAPSHOT

| Platform | Strengths | What Famit Must Match |
|---|---|---|
| **Bolna AI** | Developer API, Sarvam STT, 10+ Indian languages, <300ms latency, ₹7/min pricing | Language breadth, per-minute metering |
| **SquadStack** | 600M min training data, human-AI hybrid, SquadStack-managed service model | QA scoring, campaign analytics |
| **Ringg AI** | Pre-built real estate vertical templates, WhatsApp integration | WhatsApp follow-up, portal integrations |
| **TroikaTech** | Full CRM+WhatsApp+payment integration stack for India SMBs | CRM webhooks, WhatsApp |

**Famit's current edge:** LiveKit (low-latency infrastructure), Hinglish tuning, campaign brain auto-extraction from brief, multi-tenant vendor panel.  
**Critical gap vs. all competitors:** TRAI compliance layer, retry logic, WhatsApp follow-up, and analytics are table-stakes that Famit currently lacks.

---

## KEY REGULATORY REFERENCES

- TRAI TCCCPR 2018 + February 2025 Amendment: https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf
- DPDP Act 2023 full text: https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf
- India outbound call regulations guide: https://talk-q.com/outbound-call-regulations-in-india
- DPDP Voice AI checklist: https://www.caller.digital/blog/dpdp-act-compliance-checklist-voice-ai-india
- ConversAI Labs voice compliance: https://www.conversailabs.com/blog/voice-ai-compliance-in-india
- TRAI calling timings guide: https://www.cleartouch.in/blog/trai-guidelines-for-outbound-calling-timings-in-india/
