# RVK2 — PRODUCT-REALITY RED-TEAM (Grand Red-Team pass 3)

> READ-ONLY design artifact. No code/box mutation. Date 2026-06-18.
> Angle (distinct from the other pass-3 notes): NOT security, NOT isolation, NOT
> observability, NOT provider-failover (those are owned by
> `RVK2-SECURITY-ISOLATION-MASTER-GAPS.md`, `RVK2-BLINDSPOT-OBSERVABILITY.md`,
> `RVK2-PROVIDER-FAILOVER-KEYHEALTH-GAPS.md`).
> THIS note attacks from the **non-technical founder + paying-vendor seat**:
> after all 18 waves report DONE, what STILL makes him say *"you said done but my
> real product is fucked"*? What does a real telecaller-replacement need that the
> plan never names?
> Grounded in: the 18-wave plan, request1/request2 (founder's own words), live
> code diagnosis already in the plan, + 2026 web research (sources at bottom).

---

## THE CORE INDICTMENT

The 18-wave plan is an **engineering plan for a voice runtime**. It is NOT a plan
for a **business that replaces 500 telecallers**. Every wave answers "is the
component built correctly?" Almost none answer **"does the founder's real
business run on this without him babysitting it, and will a paying vendor keep
paying?"** The plan's reflex is *make the call itself excellent*. The 99% it is
blind to is **everything that happens around the call** — the call connecting at
all, the call reaching a human (not a voicemail), the vendor setting it up
without a 30-hour engineer, the founder trusting the numbers, the law not
shutting it down, and the customer on the other end not hating it.

A telecaller is not a "voice that talks well." A telecaller is a **worker who
shows up, dials the right number at the right time, knows when nobody's home,
takes a 'stop calling me' seriously, hands the hot one to a human, writes down
what happened, and doesn't get the company sued or its numbers blocked.** The
plan builds the mouth and forgets the worker.

Below: the blockers, each mapped to an owning wave or flagged NET-NEW, ranked by
"probability the founder rage-calls you × business blast radius."

---

## TIER 0 — THE THINGS THAT MAKE THE PRODUCT ILLEGAL OR UNUSABLE AT SCALE (fix or it cannot ship to a paying vendor)

### PR-1 — Voicemail / answering-machine detection (AMD) is COMPLETELY ABSENT from all 18 waves. 🔴 [NET-NEW wave, hooks W1+W12]
This is the single biggest hole. In real Indian outbound, **a large fraction of
dials hit voicemail, switched-off, IVR, or "this number does not exist."** The
plan has the agent greet and pitch into the void. Consequences the founder WILL
hit on day one of real volume:
- The agent delivers its full pitch to a voicemail beep → wasted LLM/TTS/telco
  spend on every unanswered dial, and the "lead" is logged as a real call with a
  transcript of the agent talking to itself. **The dashboard's call counts and
  "interested" rates become fiction.**
- Worse: it leaves no message OR leaves a broken one. A human telecaller either
  hangs up or leaves a crisp callback message. Neither is in the plan.
- 2026 production reality: demos avoid this; **a 1% AMD false-positive rate at 40M
  calls/mo = 400k wrongly-classified calls.** At the founder's "500 telecaller"
  scale this is not an edge case, it's the median dial.
**What's needed (NET-NEW):** asynchronous AMD (connect immediately, classify
human-vs-machine in parallel in <2s via the STT partial "you've reached…/please
leave a message" pattern, not a synchronous wait that adds dead air); a
voicemail-policy per campaign (hang up silently / leave a short registered
callback line / mark "left VM, retry"); "number invalid / out-of-service"
detection feeding the number-pool and the lead state. **None of this is named in
W1, W10, W11, or W12.** The whole conversation engine assumes a live human picked
up — which is the assumption that breaks first in production.

### PR-2 — India DLT / 140-series / Principal-Entity registration is named as "compliance" but the SPECIFICS that block the business are not in the plan, and one of them CONTRADICTS W12. 🔴 [W12, but needs a real regulatory sub-design]
W12 says "TRAI compliance (DND/consent/windows)". That is the legal decoration
the founder explicitly warned against. The reality the plan does NOT name:
- **Promotional outbound in India must originate from the 140-number series**
  (transactional/service = 160 series), from a **DLT-registered Principal Entity
  + registered telemarketer with active linkage**, using **registered headers**.
  A normal mobile/landline DID dialing sales = an *unregistered telemarketer*,
  which TRAI now **proactively detects with its own AI/ML in 2026** → number
  disconnection + blacklisting of the PE.
- **This directly CONTRADICTS W12's own design.** W12 plans a "number pool +
  spam-reputation + adaptive routing" that *rotates ordinary numbers to dodge
  spam flags.* Rotating un-registered numbers to evade carrier spam-labelling is
  **exactly the unregistered-telemarketer pattern TRAI is hunting** — it doesn't
  reduce risk, it *manufactures* it. The number-pool design and the compliance
  design are at war and the plan never reconciles them.
- **Consent windows changed (Feb 2025 TCCCPR amendment):** inferred consent valid
  only for the contractual relationship; explicit transactional consent valid
  **7 days**. The plan has no consent-state model with these TTLs, no opt-out
  capture during the call ("stop calling me" must instantly write DND and never
  dial again — the agent has no tool to do this), no scrubbing against the DLT
  preference list before dialing.
- **DPDP Act** (personal data of leads): the plan records every call + stores PII
  in vectors/PG with no consent line, no retention TTL, no erasure — flagged in
  the security note as #15 but it's a NOW commercial blocker, not a "later"
  nicety: a vendor's compliance officer will refuse to sign.
**Owning wave:** W12, but it needs a dedicated India-regulatory sub-design (PE/TM
registration runbook the founder can actually execute, 140-series DID procurement
path, registered-header binding, in-call opt-out tool, consent-state with the
correct TTLs, pre-dial DND scrub) — and W12's number-pool must be **re-scoped
from "evade spam labels" to "operate compliantly within registered series."**

### PR-3 — There is no SELF-SERVE ONBOARDING / time-to-value path. A paying vendor cannot turn this on themselves, so it doesn't scale and it churns. 🔴 [NET-NEW onboarding wave; W3+W15 adjacent]
The plan assumes a campaign and a vendor script *already exist* and are *correct*.
It never builds the **path from "vendor signs up" to "first good call"**. Real-
world 2026 data: voice-AI products see **15–25% monthly churn in year one**,
**83% of it controllable**, and the #1 cause is **time-to-value** — vendors cancel
at month 3 because setup took 20–40 engineer-hours and they "never saw value."
The founder's own product, as planned, requires:
- Someone to write a good vendor script (the plan makes the script *authoritative*
  but never helps the vendor *author a good one* — no guided builder, no template
  library per industry, no "your script is missing an objection-handler" linting,
  no AI-assisted draft-from-brochure).
- Someone to know the call actually sounds right before spending money — there's
  **no "test this campaign by calling MY phone right now" preview** (req2 asks for
  preview everywhere; the plan has preview for *assets/PDFs* but NOT for **a live
  test call of the configured agent**). The founder debugs by placing real PSTN
  calls; the *vendor* has no equivalent and will not trust the system blind.
- A clear "you are ready to go live" checklist (script ✓, brief ✓, DID registered
  ✓, calling window set ✓, consent source declared ✓, test call passed ✓).
**Without this, every new vendor is a manual, founder-led, 30-hour implementation
— which is the exact opposite of "replace 500 telecallers with software you sell."**
The plan builds the engine and forgets the ignition the customer can reach.
**NET-NEW: an Onboarding / Campaign-Authoring / Go-Live-Readiness wave** — guided
script builder (AI-draft from brochure → vendor edits → lint), industry-pack
starter templates, the **live "call me now" test-call button**, and a go-live
checklist. This is the difference between a tool and a product.

---

## TIER 1 — THE THINGS THAT MAKE A REAL CALL FAIL THAT THE "GREAT CONVERSATION" WAVES DON'T COVER

### PR-4 — Bad/dead phone numbers, retries, and "call didn't connect" are unmodeled. 🟠 [W10 + W12]
W10 is "smart callback cadence (Day0/1/3/7…)". But the plan never models the
**reasons a dial fails**: ringing-no-answer vs busy vs switched-off vs
invalid-number vs network-congestion vs voicemail (PR-1). A real telecaller treats
these completely differently (retry busy in 20 min; never retry invalid; try a
different number for switched-off). The plan's cadence is a calendar with no
awareness of *why* the last attempt failed → it will hammer dead numbers and give
up on temporarily-busy hot leads. **SIP call-progress / SIP-cause-code → outcome
mapping is a missing primitive** that W10's cadence and W12's number-pool both
depend on.

### PR-5 — IVR / "press 1 for English" / human gatekeepers / "who is this?" are unhandled. 🟠 [W1 + W6]
A non-trivial share of B2C/B2B dials reach an IVR tree, a receptionist, a family
member ("he's not home"), or a suspicious "who is this and how did you get my
number?" A real telecaller navigates all of these. The plan's conversation engine
(W1/W6) is built for "qualify the lead and pitch" — it has **no gatekeeper
handling, no IVR-digit sending (and note: DTMF as audio fails over voice codecs —
must send RFC 4733 out-of-band, a real engineering gap), no "wrong person /
callback the right person" branch, no graceful "I'll call back" when it's clearly
a bad moment.** These aren't objection-handling; they're *call-reality* branches
the brain packs don't include.

### PR-6 — Noisy lines, partial words, "hello? hello?", and call-quality degradation have no in-call recovery. 🟠 [W1 + W5]
Indian mobile calls drop, echo, and fill with background noise (traffic, TV,
crowd). req2 explicitly names "noisy environments" and "false-interruption
recovery." The plan lists semantic turn-detection and barge-in (W5) but has **no
strategy for: STT returning garbage on a noisy line (the agent must say "sorry, I
didn't catch that" like a human, not pitch into noise), the caller saying
"hello? hello?" when there's audio lag (a latency-tail symptom that reads as a
dead agent), or a call so degraded the right move is "let me call you back on a
better line."** A human telecaller does all three reflexively.

### PR-7 — "Repeat that / send me the details on WhatsApp / what's your number" mid-call asks have no tool wiring named. 🟠 [W11 + W16 + W1]
Real leads constantly say "send me the brochure on WhatsApp," "can you repeat the
price," "what's your office number," "call me after 6." The plan has WhatsApp
media (W16) and callback scheduling (W10) as *separate* surfaces but **does not
wire them as in-call tools the agent can fire mid-conversation** ("ok sir, I'm
sending the brochure to your WhatsApp now" → actually triggers W16 send → confirms
it arrived). Without this, the agent promises things it can't do, or can't do the
single most common real ask (WhatsApp the details), and the lead feels lied to.

---

## TIER 2 — THE THINGS THAT MAKE THE FOUNDER NOT TRUST / NOT BE ABLE TO RUN THE PRODUCT

### PR-8 — The founder can't tell a GOOD call from a BAD one at a glance, or steer the agent without a code change. 🟠 [W15 + W17 + W2]
Even with the Call Inspector (observability note G15), there's no **"the agent did
X wrong, fix it HERE"** loop for a non-technical owner. The plan makes the
RenderBrain "editable/versioned" (W2) — good — but the founder's actual need is
*"the agent kept offering discounts it shouldn't / talked too much Hindi / didn't
push for the booking — let me correct THAT behavior and test it on a call in 2
minutes."* There's no behavior-correction → instant-test → publish loop scoped for
a non-engineer. Versioning a 15k-char prompt is an engineer's tool; the founder
needs guardrail knobs and example-based correction. (Adjacent to W2 but the
*non-technical control surface* is unbuilt.)

### PR-9 — Money the founder/vendor cares about is invisible: "what did this campaign COST me and what did it EARN me?" 🟠 [W13 + W14 + W17]
The plan tracks cost-per-appointment as an *engineering metric* (W17). The
**founder/vendor business view is missing**: per-campaign "you spent ₹X on Y calls,
booked Z visits, here's your cost-per-booking and your remaining wallet balance,
and at this burn you have N days left." No spend forecasting, no "you're about to
run out of credits" alert, no per-vendor invoice/usage statement they can show
*their* boss. A paying vendor who can't see ROI in rupees churns (the integration-
stickiness data: clients who see clear value/ROI churn far less). This is a
business-facing reporting gap, not the engineering cost dashboard W17 builds.

### PR-10 — No graceful degradation story the founder can understand: "what happens to my calls when something is down?" 🟠 [W5 + W12 + NET-NEW status]
When Groq browns out, SIP trunk dies, or the box restarts mid-campaign, what
happens to the 200 leads queued? The provider-failover note covers the *technical*
failover, but the **product** has no answer for: do queued calls pause and resume,
or silently vanish? Does the founder get told "your campaign is paused, telephony
is down"? Is there a status page / "is my AI working right now" signal? A vendor
whose campaign silently stalls overnight and finds out next morning will not trust
it again. **NET-NEW: a campaign-level run-state (running/paused/degraded/stalled)
with a reason and a founder-visible status + a resume-safe queue.**

### PR-11 — "Did the lead actually get called, and what happened" must be bulletproof and HUMAN-readable, or the founder distrusts everything. 🟠 [W7 + W14 + W15]
The founder's recurring grievance is "call happened but nothing updated." Beyond
the event-bus plumbing (W8), the *product* need is: every lead row shows a plain-
language history a non-technical person reads — "Called 3:42pm, rang 22s, spoke
4min, interested, wants a callback Saturday 11am, brochure sent on WhatsApp ✓."
The plan stores structured memory (W7) and events (W8) but **never specifies the
human-readable per-lead activity timeline** that makes the founder *believe* the
system did the work. Trust is a feature; it has no owner.

---

## TIER 3 — THE THINGS A REAL TELECALLER DOES THAT NO WAVE NAMES

### PR-12 — Compliant call opening + recording-consent disclosure + "this call is being recorded" + identifying the caller/brand. 🟡 [W2 + W12]
Every legitimate telecaller call in India increasingly must disclose the brand
(registered header/PE) and, for recording, state consent. The plan records every
call (W9) but the agent **never says "this call is being recorded"** and the brand-
identity opening isn't tied to the registered PE. This is both a legal exposure
and a "the AI sounds shady" trust problem.

### PR-13 — Pricing/discount/commitment guardrails must be SERVER-SIDE, not prompt-instructed. 🟡 [W1 + W11]
2026 production lesson: prompt-based price floors *fail under adversarial users* —
"give me 50% off" talks the model past a stated rule. The fix is architectural:
**any quotable price/discount/commitment runs through a server-side function that
validates against the campaign's floor before the number is spoken.** The plan's
"vendor-script-priority" makes the script authoritative for *content* but has **no
hard guardrail layer for commitments the agent must NOT make** (over-discount,
promise a delivery date, guarantee an outcome). The founder will get a call where
the AI promised something the business can't honor. (Cross-refs the injection note
#6/#10 but this is the *business-rule* facet, not the security facet.)

### PR-14 — "Don't call this person again" / suppression list / already-a-customer / already-booked dedup. 🟡 [W10 + W12 + W7]
A real telecaller never re-pitches someone who already bought, already said no
hard, already booked, or asked to be left alone. The plan has callback dedup
(W10) but **no global suppression/Do-Not-Contact list, no "this lead is already a
customer" guard, no cross-campaign "we already called this number 3 times this
week" frequency cap.** Without it, the founder's leads get pestered across
campaigns → complaints → spam labels → exactly the reputation death W12 fears.

### PR-15 — Timezone / local-hours / festival / language-region awareness per lead. 🟡 [W10 + W12]
"Calling windows" (W12) is named but thin. Real India ops needs: per-lead local
calling hours (a lead in a different state/timezone), no calls during festivals/
odd hours, and **language inference per lead/region** (the plan mirrors the
*caller's* language reactively, but a real telecaller knows from the lead's
city/name to *open* in the likely language, not guess turn-1). These are cheap,
high-trust wins the plan leaves on the table.

### PR-16 — Outcome honesty: "interested" must mean interested. 🟡 [W7 + W17]
The plan classifies leads hot/warm/cold (W7) but a real risk is **outcome
inflation** — the model marking voicemails, polite brush-offs, and "send me info"
as "interested" to look successful. Combined with PR-1 (voicemail counted as a
call), the founder's hot-lead list fills with garbage, he chases dead leads, loses
trust in the whole product. Needs grounded outcome criteria + a "we're not sure"
bucket, not optimistic labels.

---

## NET-NEW WAVES THIS ANGLE ADDS (beyond the security note's W19–W23)

- **NET-NEW W24 — Call-Reality Layer (AMD + call-progress + gatekeeper/IVR + noise-recovery).**
  Owns PR-1, PR-4, PR-5, PR-6. The "what actually happens when you dial a real
  Indian number" layer the conversation waves assume away. Hooks W1/W10/W12.
  **This is arguably as important as W1 — the brain is useless if it's talking to
  a voicemail.**
- **NET-NEW W25 — India Regulatory Operating Model (DLT/PE/TM/140-series/consent-TTL/in-call-opt-out/DND-scrub).**
  Owns PR-2, PR-12, parts of PR-14/PR-15. Re-scopes W12's number-pool from
  "evade" to "operate compliant." A founder-executable registration runbook +
  the consent/opt-out *product* features. Without this the business is illegal at
  volume.
- **NET-NEW W26 — Vendor Onboarding & Go-Live Readiness (guided script authoring + live test-call + readiness checklist + ROI view).**
  Owns PR-3, PR-9 (business ROI view), PR-8 (non-technical steering). The
  product-ization layer that turns the engine into something a paying vendor
  self-serves and keeps paying for. This is the anti-churn wave.
- **NET-NEW W27 — Suppression / Frequency-Cap / Campaign Run-State / Trust-Timeline.**
  Owns PR-10, PR-11, PR-14, PR-16. The "the founder believes it and it won't get
  him in trouble" operational-trust layer.

---

## TOP BLOCKERS (the ones that make him say "done but FUCKED") — ranked

1. **Voicemail/AMD absent (PR-1).** The most-common dial outcome at scale is
   unhandled; pitching into voicemail wastes money and poisons every metric. Fires
   on literally the first real campaign. → **NET-NEW W24.**
2. **India DLT/140-series unhandled AND W12's number-pool contradicts it (PR-2).**
   The product is *illegal as designed* at volume and the spam-evasion design
   *increases* legal risk. A vendor's compliance officer kills the deal. →
   **NET-NEW W25 + re-scope W12.**
3. **No self-serve onboarding / live test-call / time-to-value (PR-3).** Every
   vendor is a 30-hour manual founder-led install → doesn't scale, churns at month
   3. This is the commercial death of "sell it to replace 500 telecallers." →
   **NET-NEW W26.**
4. **Call-reality branches missing (PR-4/5/6): dead numbers, IVR, gatekeepers,
   noisy lines.** The "great conversation" only happens if a live human picked up
   on a clean line — the median real dial isn't that. → **W24.**
5. **In-call WhatsApp/callback/repeat tools not wired (PR-7).** The single most
   common real ask ("WhatsApp me the brochure") isn't an in-call action; the agent
   lies or fails. → **W11/W16 must expose call-time tools.**
6. **Founder/vendor can't see ROI in rupees or trust the lead list (PR-9/PR-11/PR-16).**
   No business-facing cost↔earn view, no human-readable per-lead timeline, outcome
   inflation. Trust collapses → churn. → **W26 + W27.**
7. **Server-side commitment/price guardrails missing (PR-13).** The AI will
   promise something the business can't honor; prompt rules don't hold under
   adversarial leads. → **W1/W11 hard guardrail layer.**

---

## WHAT MUST CHANGE IN THE PLAN (concrete)

1. **Add the Call-Reality Layer (W24) to Wave A**, alongside W1 — the kernel is
   incomplete without AMD + call-progress + gatekeeper handling. Treat "what
   happens before/around a human answering" as core, not edge.
2. **Re-scope W12** from "number-pool + spam-evasion" to "compliant number
   operation," and split out the **India Regulatory Operating Model (W25)** with a
   founder-executable PE/TM/140-series registration runbook + in-call opt-out tool
   + consent-state with correct TTLs + pre-dial DND scrub. Resolve the
   pool-vs-compliance contradiction explicitly.
3. **Add an Onboarding / Go-Live wave (W26):** guided AI-assisted script authoring
   from the brochure, industry starter templates, a **live "call my phone now to
   test this campaign" button**, a go-live readiness checklist, and a business ROI
   view (₹ spent vs bookings vs wallet runway). This is the wave that makes it a
   *product*, not an engine.
4. **Wire in-call tools (W11/W16):** WhatsApp-send-now, schedule-callback-now,
   send-brochure-now, capture-opt-out-now — as functions the agent fires mid-call
   with confirmation, not separate dashboard surfaces.
5. **Add a Trust/Operations layer (W27):** global suppression + frequency cap +
   campaign run-state (running/paused/degraded with a reason, resume-safe queue) +
   human-readable per-lead activity timeline + grounded outcome criteria (no
   inflation, an explicit "unsure" bucket).
6. **Make commitment guardrails server-side (W1/W11):** price/discount/promise
   validation behind a function the LLM can't talk past, not a prompt sentence.
7. **Add recording-consent disclosure + registered-brand opening to the brain
   (W2/W12).**

## ONE-LINE BOTTOM LINE
The plan builds a brilliant **mouth**; it forgets the **worker, the law, and the
buyer.** A telecaller-replacement that pitches into voicemails, dials un-registered
numbers TRAI is hunting, takes 30 engineer-hours per vendor to set up, can't
WhatsApp a brochure mid-call, and shows the founder no rupee ROI will be reported
"done" and felt as "fucked" the first week a real vendor runs a real campaign. The
four NET-NEW waves (Call-Reality, India-Regulatory, Onboarding/Go-Live,
Trust/Operations) are the gap between a voice demo and a sellable AI revenue
workforce.

---

## SOURCES
- Retell AI — hardest parts of a real call (IVR/voicemail/interruption/price-floor): https://www.retellai.com/blog/how-voice-ai-handles-hardest-parts-real-call
- Outbound Voice AI voicemail detection (AMD, async vs sync, scale math): https://vegavid.com/blog/outbound-voice-ai-voicemail-detection
- Regal.ai — how AMD algorithms actually work: https://www.regal.ai/blog/demystifying-amd-how-answering-machine-detection-algorithms-actually-work
- Caller.digital — TRAI DND compliance for AI outbound calling India 2026: https://www.caller.digital/blog/trai-dnd-compliance-ai-outbound-calling-india
- AutoInterviewAI — DPDP / TRAI DLT / RBI AI-calling compliance guide 2026: https://www.autointerviewai.com/blog/ai-calling-india-dpdp-trai-dlt-compliance-complete-guide-2026
- Chambers / S.S. Rana — TRAI crackdown on spam & AI telemarketing (140/160 series, PE/TM, AI/ML detection): https://ssrana.in/articles/trais-crackdown-on-spam-calls-and-ai-driven-telemarketing/
- Trillet — voice-agent client retention/churn (15-25% monthly, time-to-value, integration stickiness): https://trillet.ai/blogs/voice-agent-client-retention-strategies
