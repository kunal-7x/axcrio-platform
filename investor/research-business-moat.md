# INVESTOR DECK — BUSINESS MODEL · TRACTION · MOAT (research input)

> **Purpose:** the INVESTMENT story for the Famit / Axcrio VC pitch deck — about the COMPANY as an
> investment, not a product sale. Compiled READ-ONLY from `memory/MEMORY.md`, `memory/brain/*.md`,
> `MASTER_VISION.md`, `MASTER_PLATFORM_ROADMAP.md`, `GROWTH-OS-BUILD-SPEC.md`, and the existing
> `sales/research-product-truth.md` (the no-fabrication product inventory).
>
> **RULE:** every metric here is REAL or honestly tagged. Mark roadmap as roadmap. Never inflate.
> Tags: **[LIVE]** running in prod · **[READY/DORMANT]** built+tested, flag/cred-gated · **[ROADMAP]** specced.
>
> **The raise amount + valuation are deliberately left as a FOUNDER-TO-FILL placeholder** (§7). Do not invent them.

---

## 1. THE ONE-LINE INVESTMENT THESIS

**Famit / Axcrio is an AI Revenue Workforce that owns the entire post-click revenue loop — ad → AI
voice call → WhatsApp → appointment → sale — and turns the conversation it owns into a proprietary
ad-optimization signal no competitor can replicate.** It replaces the telecaller team AND the marketing
team for an SMB, sells on a model that can charge for OUTCOMES (a booked appointment) because it owns
the funnel end-to-end, and compounds a cross-tenant data network effect every month it runs.

The category framing for the deck: not "another AI ad tool" (commoditized) and not "another AI
voice-bot" (commoditized) — but **the conversation + revenue-truth layer that sits between them**, which
is the one piece neither the ad platforms nor the point tools own.

---

## 2. THE BUSINESS MODEL (how it makes money — three layers + the unique fourth)

A **three-layer model with a fourth, defensible, outcome-based layer** that competitors structurally
cannot offer:

1. **Base subscription (SaaS, recurring).** Per-tenant plan fee for platform access — the AI workforce,
   dashboard, control layer, modules. Predictable MRR floor. (Plans + entitlements are already enforced
   live by the Foundation Control Layer — per-vendor HIDE/LOCK/plan/suspend. **[LIVE]**)
2. **Usage credits (consumption, expansion).** A prepaid credit wallet meters real consumption — AI
   call minutes, LLM tokens, generated banners/creatives, WhatsApp messages by category. This is the
   **net-dollar-retention engine**: a tenant that grows usage grows revenue automatically.
   (ACID wallet + real per-call/per-asset metering are **[LIVE]** — no-double-spend proven.)
3. **% of managed ad spend (take-rate, scales with the customer).** Optional, per-plan: a percentage of
   the ad budget the platform manages/optimizes — the classic agency/ad-tech take-rate, but earned by
   software, not headcount. Scales linearly with each customer's marketing budget.
4. **★ OUTCOME-BASED BILLING — charge per BOOKED APPOINTMENT / qualified lead / sale (the wedge no one
   else can offer).** Because Famit owns the *whole* funnel — it places the ad, makes the call, runs the
   WhatsApp thread, books the appointment, and records the sale — it can price on the **outcome** (a
   booked site-visit, a qualified lead, a closed sale), not on seats or messages. **Point tools cannot
   do this:** Bland/Vapi/Retell sell call minutes (they don't own the ad or the booking); ringg.ai sells
   per-call/seat; horizontal ad tools (AdCreative, Madgicx) sell creatives/optimization (they never touch
   the call or the booking). **Owning the funnel end-to-end is the precondition for outcome pricing — and
   outcome pricing is the highest-trust, highest-willingness-to-pay model an SMB will accept** ("pay me
   when I put a real buyer in your calendar"). This is the pricing moat that *follows from* the product moat.

**Why the model is investable:** layers 1+2 give a predictable, expanding SaaS base (low-churn, NDR
>100% by construction as usage grows); layers 3+4 add a take-rate that rides the customer's *own* growth
in marketing spend and revenue — so ARPU expands without new logos. The same engine serves any vertical
(real-estate, salon, clinic, coaching, D2C, agency), so TAM is broad, not niche.

---

## 3. UNIT ECONOMICS — SHAPE & GROSS-MARGIN DRIVERS

> Frame as the *shape* of unit economics from REAL metered COGS, not as audited financials.

**COGS (the variable cost of the loop) — three drivers, all metered LIVE today:**
- **Telephony / voice minutes** — Vobiz CDR (the actual call carriage). **[LIVE meter]**
- **TTS + STT + LLM** — ElevenLabs (TTS), Sarvam + Groq (multilingual STT/LLM), key round-robin for
  resilience. The voice agent's per-second cost. **[LIVE meter]**
- **Creative generation** — OpenRouter `gemini-2.5-flash-image` per banner. Real measured **~Rs 10 per
  banner** (wallet settled the ACTUAL spend, no double-charge). **[LIVE]**

**The proof the economics are metered, not estimated:** the live account ran the full stack at roughly
**~Rs 68/month** of measured vendor-API spend across ~96 calls + real banners. The cost side is
*instrumented at the call/asset level* — every unit of consumption is metered against the wallet before
it is billed. That instrumentation is itself the asset (most competitors estimate; Famit meters).

**Gross-margin drivers (the levers that move margin up):**
- **AI replaces labor, not augments it.** The expensive line an SMB pays today is the *telecaller/
  marketing salary*; Famit's COGS is cents of API spend per call. The spread between "a human
  telecaller's cost per call" and "Rs-of-API per AI call" is the gross-margin story. The pitch isn't
  "cheaper software" — it's "the workforce cost goes to near-zero."
- **Model/vendor arbitrage.** Multi-vendor round-robin (Groq/Sarvam/ElevenLabs) + an LLM-gateway routing
  tier (reasoning/bulk/cheap) means COGS falls as models commoditize — margin *expands* over time without
  a price change. (LLM-gateway routing is **[ROADMAP]** per GROWTH-OS §9.1; the round-robin is **[LIVE]**.)
- **Credits + outcome billing decouple price from COGS.** Outcome billing (per booked appointment) is
  priced on *value delivered*, not cost incurred — so as COGS falls, margin on the outcome layer rises.

**Expansion-revenue path (the "land-and-expand" that VCs underwrite):** start a tenant on base + a small
credit pack → usage grows as the AI proves it books appointments → tenant adds % of ad spend / outcome
billing → tenant adds dormant modules (Booking, Payments, Workflows, Funnels — all **[READY/DORMANT]**, a
flag-flip not a rebuild) → ARPU compounds. NDR is engineered, not hoped-for.

---

## 4. TRACTION FRAMING (real + honest — the credibility section)

> The investor rule: show *real* proof of a working system, label everything precisely, never inflate.
> The honest story is strong *because* it's honest — a working closed loop with metered economics.

**What is LIVE and real today (use these exact numbers; do not round up):**
- **Real AI tele-calling in production:** **~96 real calls across 8 live campaigns** on the LiveKit
  low-latency multilingual "Riya" voice agent (Hinglish + multilingual). **[LIVE]**
- **Metered unit economics, not estimates:** real per-call/per-asset billing meter (ElevenLabs / Groq /
  Sarvam + Vobiz CDR), **~Rs 68/month** measured spend on the live account. **[LIVE]**
- **Real AI creative:** OpenRouter `gemini-2.5-flash-image` produced real 1024²/1.2–1.9 MB PNG banners
  from a real client campaign (Shapoorji Pallonji "Codename Joy 3.0"), 3 distinct angles, verbatim facts
  (no-invent guard held), stored to DO Spaces; wallet settled the actual **~Rs 10/banner, no double-charge.
  [LIVE]**
- **The command brain works end-to-end:** AI Manager — typed/spoken command → NLU → deterministic risk
  table → PIN step-up → real banner generated + credit settled + immutable audit; reads return real live
  data. **[LIVE on chat/test-console; inbound voice = founder-blocked last wire]**
- **WhatsApp Cloud API live send** (real `wamid` returned) + AI compliant-template builder. **[LIVE]**
- **Enterprise-grade trust, proven by tests (de-risks the "can it spend money safely?" objection):**
  - Foundation Control Layer LIVE + enforcing; **18-probe isolation/impersonation suite passing 18/18**
    over real HTTP (HIDE→404, LOCK→402, suspend neutralizes a vendor, zero cross-tenant bleed). **[LIVE]**
  - No-double-spend wallet: 24-concurrent no-oversell + concurrent double-settle charged once, proven. **[LIVE]**
  - Twice-enforced tenant isolation: `tenant_id` from the token (never the body) AND Postgres FORCE-RLS —
    a leaked token still can't read another tenant's rows. **[LIVE]**

**The honest "early-stage" framing (so the deck never over-promises):** this is a **working closed loop
with real usage and metered economics, at design-partner / pilot scale** — not yet a revenue-at-scale
story. The investment is in *the loop being closed and the moat being real today*, plus a large built-but-
dormant surface (Booking/Payments/Workflows/Funnels/Lifecycle/Support/Forms/Ads are **[READY/DORMANT]** —
flag/cred flips, not rebuilds) and a specced cross-tenant network effect. **Mark cross-tenant learning
aggregate, inbound voice, and revenue-at-scale as ROADMAP — they are the use-of-funds, not the claim.**

---

## 5. DEFENSIBILITY / MOAT (the section the whole raise turns on)

Creative generation and campaign setup are **commoditized** (Meta Advantage+, Google PMax, dozens of AI
ad tools). Famit does **not** compete there. The moat is four compounding layers neither the platforms
nor the point tools own:

1. **★ THE REVENUE-TRUTH SIGNAL LOOP (the crown jewel / GROWTH OS).** Ad platforms optimize toward
   whatever conversion events you feed them. Almost every SMB feeds them **junk** ("form submitted",
   "conversation started") — so the algorithms hunt for cheap clickers. Famit owns the **ground truth of
   lead quality** — the AI voice-call outcome + WhatsApp conversation outcome + booking + sale — and feeds
   it back to Meta/Google as **quality-weighted conversion events (value = lead-quality score)**. So the
   platforms literally start optimizing for people who **answer calls and buy**, in the vendor's own
   definition of a good customer. **No creative tool, no dashboard, no agency, no voice-bot has this loop
   closed end-to-end.** Positioning: *"The platforms decide who sees the ad. We decide what to say,
   whether the lead was real, and what to do next — and we prove it with revenue, not clicks."*
2. **Owned conversation layer.** The AI voice call + WhatsApp thread is OUR surface. Competitors stop at
   the click / landing page. Owning the conversation is the *precondition* for moat #1 (the truth signal),
   for the single cross-channel memory per lead, and for outcome-based pricing (§2.4). You can't fake
   owning the conversation — you have to build the whole funnel, which is exactly what's **[LIVE]**.
3. **Cross-tenant learning network effect.** Anonymized priors by industry × geo × objective mean a
   brand-new salon in Ahmedabad starts with the posterior of hundreds of salons, not from zero. Every
   vendor makes every other vendor's first campaign smarter — a classic data network effect that
   **compounds monthly** and that a new entrant cannot buy. (Architecture/anonymization pipeline specced;
   live aggregate is **[ROADMAP]** — frame as the network effect the raise *capitalizes*, not as live.)
4. **Attribute-level creative learning ("Creative DNA") + the strangler-evolved live system.** Famit
   learns at the *attribute* level (angle × hook × format × offer → CPqL posterior), so knowledge survives
   creative fatigue; and the learning loop **biases winning style but NEVER fabricates a fact** (a
   deterministic no-invent validator is the authority — no invented price/RERA/testimonial). Plus the
   system is a **strangler-evolved live platform** (a real production SaaS at panel.famit.in, not a
   greenfield demo) — the moat includes the un-sexy but un-cloneable enterprise substrate: twice-enforced
   RLS, ACID wallet, immutable audit, the PIN/approval firewall, the Control Layer.

**The defensibility one-liner for the deck:** *"Owning the conversation produces a revenue-truth signal
that makes ads hunt for buyers — a post-click moat the ad platforms structurally can't build (it lives
outside their incentive set: they optimize THEIR spend with THEIR events) and the point tools can't build
(they don't own the funnel) — and it compounds into a cross-tenant data network effect."*

**Why Meta won't just do this (the standard VC objection, pre-answered):** Meta optimizes *its* spend
with *its* events; it has no incentive to own a vendor's phone calls + WhatsApp + booking + cross-platform
brain. Famit's truth layer, cross-platform orchestration (Meta + Google + WhatsApp + voice), and
refusal-to-waste positioning live *outside* the platforms' incentive set — and Famit *feeds* their AI
rather than fighting it.

---

## 6. COMPETITION TABLE (what they lack — the gap is the moat)

Two competitor sets; Famit's wedge is the same against both: **nobody else owns the whole funnel, so
nobody else can produce the revenue-truth signal or bill on outcomes.**

| | AI voice / SDR bots (ringg.ai, Bland, Vapi, Retell) | Horizontal ad tools (AdCreative, Madgicx, Smartly, PMax/Advantage+) | **Famit / Axcrio** |
|---|---|---|---|
| Owns the AI voice call | ✅ | ❌ | ✅ |
| Owns WhatsApp follow-up | ✕ (mostly) | ❌ | ✅ |
| Owns the ad → optimizes spend | ❌ | ✅ | ✅ |
| Owns booking / appointment | ❌ | ❌ | ✅ **[READY/DORMANT]** |
| **Closes the full loop (ad→call→WA→book→sale)** | ❌ | ❌ | **✅ — the whole point** |
| **Feeds real call/sale OUTCOMES back to ads as quality signal** | ❌ | ❌ (feeds clicks/forms) | **✅ — the moat** |
| Single cross-channel memory per lead | ❌ | ❌ | ✅ |
| Cross-tenant learning network effect | ❌ | partial (own data only) | ✅ **[ROADMAP]** |
| **Can bill on OUTCOMES (per booked appointment)** | ❌ (per-minute/seat) | ❌ (per-creative/seat) | **✅ — only one who can** |
| Enterprise trust substrate (RLS, ACID wallet, PIN firewall, audit) | varies | varies | ✅ proven (18/18, no-double-spend) |

**The gaps, stated plainly:** voice bots are a *feature* (the call) without the funnel — they can't see
whether the lead bought, so they can't optimize the ad or bill on the outcome. Ad tools are the *top of
funnel* without the conversation — they optimize toward form-fills (junk), never toward answered-calls-
that-bought. **Famit is the only player that owns ad + call + WhatsApp + booking as one loop — which is
precisely what unlocks the revenue-truth signal, the network effect, and outcome-based pricing.** The
competition slide's headline: *"Everyone owns a slice. We own the loop."*

---

## 7. THE ASK — USE-OF-FUNDS BUCKETS (raise amount + valuation = FOUNDER-TO-FILL)

> ⚠ **The raise amount and pre/post valuation are a deliberate FOUNDER-TO-FILL placeholder.** The deck
> slide must render them as a clearly-labeled blank for the founder to set — do NOT invent figures.
> What the research CAN frame is *where the money goes* (the use-of-funds buckets) and *what each unlocks*.

Use-of-funds buckets (each tied to a moat/milestone, so the ask reads as "fund the moat, not the burn"):

1. **Activate the dormant surface → expand ARPU.** Flip on Booking, Payments, Workflows, Funnels,
   Lifecycle, Support, Forms, Ads (all **[READY/DORMANT]** — built+tested) and wire the inbound-voice DID/
   SIP/DLT (the AI Manager's last founder-blocked wire). *Unlocks outcome-based billing + the full
   expansion-revenue ladder.*
2. **Build the cross-tenant learning network (the compounding moat).** Ship the anonymization pipeline +
   priors store + benchmark brain (specced in GROWTH-OS §14.4) so every tenant makes every other tenant
   smarter. *Unlocks the data network effect — the defensibility that compounds monthly.*
3. **Harden + scale the Revenue-Truth Signal Loop across platforms.** Deepen Meta CAPI + Google Enhanced
   Conversions, EMQ/dedup/latency health, CTWA `ctwa_clid` attribution. *Unlocks the flagship moat at
   production scale.*
4. **Go-to-market + design partners → revenue at scale.** Sales, onboarding ("magic onboarding" <10-min
   time-to-value), industry packs per vertical (real-estate/salon/clinic/coaching/D2C/agency). *Unlocks
   the logo growth the SaaS layers monetize.*
5. **Team (founding engineers + GTM hires).** The talent to execute 1–4. *Unlocks velocity.*
6. **Compliance + trust runway.** DPDP/DLT/TRAI compliance, SOC2-track hardening, security. *Unlocks
   up-market and regulated verticals (clinic/finance).*

**The ask framing line:** *"We've proven the loop closes and the moat is real with [Rs/$ of measured
spend] and a [18/18] safety suite. The raise capitalizes the three things that compound — the dormant
revenue surface, the cross-tenant network effect, and the signal loop at scale — to turn a working closed
loop into a category."* (Amount + valuation: founder-to-fill.)

---

## 8. DECK-READY SOUNDBITES (one-liners the slides can lift verbatim)

- **Thesis:** "We own the post-click revenue loop and turn the conversation into a signal the ad
  platforms can't build and the point tools can't fake."
- **Model:** "Base subscription + usage credits + % of ad spend — and, uniquely, we can bill per booked
  appointment, because we own the funnel."
- **Moat:** "The platforms decide who sees the ad. We decide whether the lead was real — and prove it with
  revenue, not clicks."
- **Competition:** "Everyone owns a slice. We own the loop."
- **Network effect:** "A new salon in Ahmedabad starts with the posterior of hundreds of salons."
- **Trust:** "A system that spends money and calls customers autonomously — proven by an 18/18 isolation
  suite, a no-double-spend wallet, and an immutable audit ledger."
- **Margin:** "Our COGS is cents of API per call; the line we replace is a telecaller's salary."

---

*Compiled READ-ONLY for the investor deck. Every metric real or tagged. Raise amount + valuation =
FOUNDER-TO-FILL. Companion product-truth: `sales/research-product-truth.md`. Vision/moat source:
`GROWTH-OS-BUILD-SPEC.md` §1–2/§11/§14, `MASTER_VISION.md`.*
