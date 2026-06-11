# PRODUCT-TRUTH INVENTORY — Famit / Axcrio Sales Proposal

> Source of truth for the customer-facing sales proposal. Compiled READ-ONLY from
> `memory/brain/*.md`, `memory/MEMORY.md`, `MASTER_VISION.md`, `MASTER_PLATFORM_ROADMAP.md`,
> `GROWTH-OS-BUILD-SPEC.md`, `CREATIVE_STUDIO_MASTER_PROMPT.md`, `AI_MANAGER_MASTER_PROMPT.md`.
> **RULE: every number/claim here is real or honestly tagged. NEVER fabricate metrics in the proposal.**
> Tags: **[LIVE]** = running in production today · **[READY/DORMANT]** = built + tested, flag-gated OFF,
> activates with a credential/flag flip · **[SOON]** = designed/specced, not yet built or activating.

---

## 1. THE ONE-LINE TRUTH (what we actually sell)

**Famit / Axcrio is an AI Revenue Workforce — a closed-loop AI Revenue OS that replaces a telecaller +
a marketing team.** A business owner enters their business, products, pricing, offers and leads once,
and an AI workforce then runs the whole revenue loop: **Ad → Lead → AI voice CALL → WhatsApp follow-up
→ appointment → repeat revenue** — all under a hard safety model (PIN/approval/audit) and twice-enforced
tenant isolation. Live today at **panel.famit.in**.

**The closed loop (the product, in one picture):**
`Business data → Campaign → AI Creative → Ads/WhatsApp/Landing → Lead capture → AI VOICE CALL →
WhatsApp follow-up → Qualify → Book/Pay → Review/Referral → Analytics → Optimize → repeat` — with
**one unified memory per lead across every hop**, and **revenue attribution closing the loop**.

---

## 2. THE MOAT — why this is not "another AI tool" (the differentiation narrative)

The proposal's center of gravity. Creative generation and ad setup are commoditized (Meta Advantage+,
Google PMax, dozens of "AI ad" tools). **We do not compete on those. We own the layer none of them own:
the post-click conversation.** Four compounding moats:

1. **The Revenue-Truth Signal Loop (the crown jewel / GROWTH OS).** Almost every SMB feeds Meta/Google
   junk conversion signals ("form submitted", "chat started"). We own the **real ground truth of lead
   quality** — the AI **voice-call outcome + WhatsApp conversation outcome + booking + sale** — and feed
   it back to the ad platforms as **quality-weighted conversion events**. So Meta/Google literally start
   hunting for people who **answer calls and buy**, not people who merely click. **No creative tool, no
   dashboard, no agency has this loop closed end-to-end.** Positioning line: *"The platforms decide who
   sees the ad. We decide what to say, whether the lead was real, and what to do next — and we prove it
   with revenue, not clicks."*
2. **We own the conversation layer.** The AI voice call + WhatsApp thread is OUR surface — competitors
   stop at the click/landing page. That ownership is what produces the truth signal in moat #1 and the
   single cross-channel memory per lead.
3. **Cross-tenant learning network.** Anonymized priors by industry × geography × objective mean a
   brand-new salon in Ahmedabad starts with the posterior of hundreds of salons, not from zero. Every
   vendor makes every other vendor's first campaign smarter — a classic data network effect. **[SOON]**
   as a live aggregate; the architecture (anonymization pipeline, priors store) is specced.
4. **Attribute-level creative learning ("Creative DNA").** We generate along an explicit diversity matrix
   (angle × format × visual × hook × headline) and learn at the *attribute* level ("question-hook +
   price-anchor wins for this vendor"), not the asset level — and the learning loop **biases winning
   style/angle/CTA but NEVER fabricates a fact** (no invented price/RERA/testimonial; deterministic
   no-invent validator is the authority).

**Honest framing to keep in the proposal:** we do NOT fight Advantage+/PMax delivery — we feed it better
signals and better creative. We do NOT promise attribution voodoo — we promise deterministic journey
truth (click-ID → conversation → call → booking → sale).

---

## 3. PROOF POINTS (real — use these, do not inflate)

- **Real AI tele-calling, in production:** ~**96 real calls across 8 live campaigns** on the LiveKit
  low-latency multilingual "Riya" voice agent. **[LIVE]**
- **Real per-call billing meter:** live vendor-API metering (ElevenLabs / Groq / Sarvam + Vobiz CDR),
  running at roughly **~Rs 68/month** in measured spend on the live account — proof the unit economics
  are metered, not estimated. **[LIVE]**
- **Real AI banners generated:** OpenRouter `gemini-2.5-flash-image` produced real **1024² / 1.2–1.9 MB
  PNG** banners from a real campaign ("Codename Joy 3.0", Shapoorji Pallonji), 3 distinct angles, verbatim
  facts (no-invent held), stored in DO Spaces. Wallet settled the **actual ~Rs 10/banner** with **no
  double-charge** (proven). **[LIVE]**
- **AI Manager executing real actions from chat:** a typed/spoken command → NLU → risk classification →
  PIN step-up → real banner generated + credit settled + immutable audit; reads return real live data
  (analytics funnel, wallet balance). **[LIVE on chat/test-console]**
- **WhatsApp Cloud API live send** (real `wamid` returned) + an **AI compliant-template builder** where
  the LLM proposes and a **deterministic Meta-compliance validator is the authority** (never invents
  facts). **[LIVE]**
- **Foundation Control Layer LIVE + ENFORCING in production:** per-vendor feature HIDE/LOCK, plans,
  suspend, act-as impersonation, immutable audit — verified by an **18-probe isolation/impersonation
  test passing 18/18 over real HTTP** (HIDE→404, LOCK→402, suspend neutralizes a vendor, no cross-tenant
  bleed). **[LIVE]**
- **No-double-spend money custody proven:** ACID wallet ledger (INR paise, atomic conditional updates,
  idempotency) — 24-concurrent no-oversell + concurrent double-settle charged once, proven. **[LIVE]**
- **Twice-enforced tenant isolation:** `tenant_id` derived from the auth token (never the request body)
  AND Postgres Row-Level Security (FORCE-RLS) — a leaked token still cannot read another tenant's rows.
  Re-proven on every new module. **[LIVE]**
- **Multilingual voice:** low-latency Hinglish/multilingual agent (Sarvam + Groq, key round-robin for
  resilience). **[LIVE]**

---

## 4. CAPABILITY LIST (LIVE / READY / SOON)

### 4.1 The revenue loop — core engine
- **AI Voice Calls (Riya telecaller):** dial, converse, transcribe, summarize, classify; low-latency
  multilingual; call logs, suppression/DND, callbacks. **[LIVE]**
- **Campaigns + Run-Campaign:** multi-channel campaign intake; 8 live campaigns; rich campaign context
  (company/product/USPs/offer/language/agent). **[LIVE]**
- **WhatsApp Automation:** Cloud API live send (free-form/open-session today); AI compliant-template
  builder with deterministic Meta-compliance + no-invent validator; banner-as-template-header attach.
  **[LIVE — builder live; cold list-sends gated on one approved Meta template]**
- **Creative Studio + AI Asset Service:** campaign-aware AI banner/image generation, real PNGs to DO
  Spaces, versioned assets, approve/reject content gate, per-tenant credit metering. **[LIVE]**
- **Billing / Credits / Wallet:** real vendor-API billing meter; ACID prepaid wallet (no double-spend);
  multi-tab billing UI. **[LIVE]**
- **AI Manager (voice/chat command brain):** NLU → RBAC → deterministic risk table → PIN/step-up →
  delegate to AI workforce roles → immutable audit. Chat path fully live; **voice (inbound DID/SIP) is
  the founder-blocked last wire.** **[LIVE on chat; voice SOON]**
- **Foundation Control Layer (Super-Admin):** per-vendor HIDE/LOCK/plans/suspend/act-as + audit,
  enforced backend-first. **[LIVE]**

### 4.2 Built + ready to activate (flag-gated, dormant-safe — short runway to live)
- **Booking / Appointments / Site-Visits:** atomic anti-double-book (DB constraint), reminders,
  reschedule/cancel, no-show follow-up; tied to the CRM contact spine. Mounted flag-OFF. **[READY/DORMANT]**
- **Payments / Collections:** Razorpay/Stripe payment links, invoice/receipt, status→CRM stitch, dunning
  follow-up. Mounted flag-OFF (needs gateway creds). **[READY/DORMANT]**
- **Workflow Automation Studio:** durable, crash-safe visual-automation engine (10 node types incl.
  BUDGET + APPROVAL) on Hatchet; the engine refuses to compile a workflow that spends/sends in bulk
  without a budget + approval gate. React-Flow canvas is the frontend follow-up. **[READY/DORMANT]**
- **Funnels:** ad→landing→lead→call→WhatsApp→booking→payment→review as one funnel over the workflow
  engine, with per-stage conversion analytics. **[READY/DORMANT]**
- **Lifecycle Trigger Engine + Segmentation:** proactive re-engagement on each business's service cycle
  (salon 30d, clinic follow-up, real-estate re-check) + 5 named segments (hot/warm/repeat/churn-risk/
  high-value), enqueue-only through the gated dial path. **[READY/DORMANT]**
- **Customer Support (AI agent + ticketing) over Knowledge Base.** Mounted flag-OFF. **[READY/DORMANT]**
- **Form / Lead-Capture + Survey/Feedback builder:** public submit → CRM contact, anti-abuse hardened,
  deterministic NPS/CSAT insights. Mounted flag-OFF. **[READY/DORMANT]**
- **Ad Automation engine (Meta/Google create/run/optimize under spend caps):** mounted flag-OFF, dormant
  until ad-platform creds. **[READY/DORMANT]**
- **CRM core (contacts/timeline) + Hatchet durable orchestration spine + Logto OIDC auth/orgs/RBAC:**
  infrastructure live/seeded; integration into the run-path is staged. **[LIVE infra / wiring staged]**

### 4.3 Roadmap (honest "coming soon")
Sales Pipeline · Revenue Attribution ledger (live aggregate) · Analytics/Reports cross-module ·
Conversation Intelligence · Business Brain + Knowledge Base RAG (live read substrate) · Industry Packs
(vertical templates) · Reviews/Reputation · Landing Page builder · Inbound voice for the AI Manager
(needs DID/SIP/DLT) · cross-tenant learning aggregate · video creative · 3D product/property studio ·
Agency/White-label modes · Mobile app. **[SOON]**

---

## 5. VALUE PROPS PER BUYER PERSONA (the sell-anything pitch)

> Same engine, configured per vertical. Each persona: the pain → what Famit replaces → the headline win.

- **Real Estate / Builders:** leads from portals/ads go cold in minutes and telecallers can't call 200
  leads at 9pm. Famit's AI calls every new lead **instantly in their language**, qualifies budget/intent,
  books the **site visit**, and WhatsApps the brochure/floor-plan banner — then feeds "answered + visited
  + booked" back to Meta so the ad budget hunts for **real buyers, not form-fillers**. Replaces a
  tele-calling team + a site-visit coordinator. No-invent guard means it **never fabricates price/RERA**.
- **Salon / Spa:** no-shows and dead time kill revenue. AI books appointments, sends reminders, and the
  **lifecycle engine auto-re-engages every client on their ~30-day cycle** ("time for your next visit")
  via WhatsApp/voice. Replaces a front-desk + a "marketing person" who never follows up.
- **Clinic / Healthcare:** follow-up calls (post-consult, report-ready, recall) are the missed revenue.
  AI handles reminders + recalls + appointment booking, escalates to a human only by exception (with an
  AI summary), all DND/consent/window-compliant. Replaces a reception + recall-calling staff.
- **Coaching / EdTech:** counsellors can't speed-dial every enquiry. AI calls each lead in minutes,
  answers course/fee questions **from approved facts only**, books a demo/counselling slot, and nurtures
  on WhatsApp — and the platform learns which **angle/offer** converts which cohort. Replaces an inside-
  sales / counselling team's grunt work.
- **D2C / E-commerce:** abandoned carts and one-time buyers. AI re-engages, runs WhatsApp offers, and
  closes the loop ad→sale so spend optimizes on **buyers, not clickers** (the Creative-DNA + signal loop).
  Replaces a performance-marketer + a retention/CRM hire.
- **Agency / Multi-client:** run all the above **across many client accounts** with per-tenant isolation,
  per-vendor feature HIDE/LOCK + plans (the Control Layer), white-label-ready. Sell it as your own AI
  revenue desk. Replaces a roomful of junior media buyers + callers — one operator steers by exception.

**The universal value prop (works for all six):** *"One operator, an AI workforce. It calls, follows up
on WhatsApp, books the appointment, and feeds real outcomes back to your ads — so your money chases
people who actually answer and buy. You steer by exception, by voice."*

---

## 6. THE SAFETY & TRUST STORY (sell the trust — autonomous spend's adoption bottleneck)

Trust is engineered as a feature, and it's a genuine differentiator for a system that spends money and
calls customers autonomously:
- **PIN / step-up firewall** on every risky action (spend, bulk send, launch/pause ads, mass-call,
  price/refund/export/delete) — proven live (wrong PIN denied + audited; correct PIN → scoped step-up).
- **BUDGET + APPROVAL gates enforced server-side** — a workflow physically cannot compile/route around
  them; the engine refuses.
- **Immutable audit ledger** — every AI decision recorded with its reason (PG `events` leg, append-only).
- **No-invent guard everywhere** — creative + WhatsApp templates strip any price/%/RERA/phone/claim not
  verbatim in the campaign facts; the LLM is input, never the authority on facts.
- **Twice-enforced tenant isolation** (token + Postgres FORCE-RLS) — proven by an 18-probe suite.
- **No-double-spend wallet** (ACID, idempotent, INR paise) — concurrency-proven.
- **DND / consent / calling-window / DPDP compliance** enforced in the dial path, not optional.

---

## 7. THE ONBOARDING PROMISE

Enter your business once — products, pricing, offers, goals, leads, voice/persona — and the AI workforce
takes over the loop. Steer by exception and **by voice** via the AI Manager; humans never start cold
(every handover carries an AI summary). Business-vertical-agnostic: the same engine, configured by the
Business Brain and shipped per vertical by Industry Packs.

---

## 8. HONEST CAVEATS (so the proposal never over-promises)

- **Inbound voice for the AI Manager** needs a dedicated DID/SIP trunk + DLT — chat/test-console path is
  fully live without it; voice is the last founder-blocked wire.
- **Cold WhatsApp list-sends** need one approved real Meta template (only `hello_world` exists today);
  open-session sends and the AI template builder are live now.
- **Cross-tenant learning** is architected; the live aggregate is roadmap.
- Several modules (Booking/Payments/Workflows/Funnels/Lifecycle/Support/Forms/Ads) are **built, tested,
  and mounted dormant** — they activate with a flag/cred flip, not a rebuild. Tag them honestly as
  "ready to switch on," not "shipping."
- AI writes compliant drafts a human approves; Meta still approves templates; the learning loop biases
  style, never fabricates facts.

---

*Compiled for the sales proposal. Architecture/vision are settled; this file is the product truth the
proposal renders. Keep every metric real: 96 calls / 8 campaigns / ~Rs68/mo meter / ~Rs10 per real
banner / 18/18 isolation probes / no-double-spend proven.*
