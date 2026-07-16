# DESIGN SPEC — WhatsApp Campaigns ▸ **OUT-OF-THE-BOX FEATURES** (founder invites proactive additions)

> **Status:** EXECUTION-READY PRODUCT DESIGN (READ-ONLY wave — this doc writes NO app code, edits no
> `caller.py`/`agent.py`/`whatsapp.py`, does NO git). It proposes + prioritizes high-value WhatsApp-campaign
> features that **fit the already-decided architecture without bloat**. Every feature below binds to a
> **real, already-specced seam** — the `creative.*` contract, the WhatsApp creative kit/delivery layer, the
> Workflow Studio node engine, the Testing Lab scoreboard, the Adbot loop, the wallet/audit/RLS gates, and
> the live WhatsApp backend (`/whatsapp/inbound` + `/whatsapp/send`, per-message metering, 24h-window
> detection, status webhooks). **No feature here invents a new engine, money-path, or asset store.**
>
> **Authoritative parents (cited, never re-specified):** `CREATIVE_STUDIO_MASTER_PROMPT.md` (§32–38),
> `CREATIVE_STUDIO_PHASE2_SPEC.md` (§2 WhatsApp Campaign Builder, §4 "out of the box"),
> `design/creative-studio-integrations.md` (the `creative.*` contract + WhatsApp seam §2),
> `design/creative-whatsapp-creative.md` (kit packaging + delivery + per-message meter + session detect +
> suppression/approval gates + status webhook), `design/platform-workflow-studio.md` (10 node types:
> trigger/condition/delay/wait/budget/approval/action/ai_agent), `design/creative-testing-lab.md` (the
> cross-channel creative-DNA scoreboard), `design/creative-ads-engine.md` (variant→test→scale/kill loop),
> `WHATSAPP_GOLIVE.md` (LIVE end-to-end: real send proven, webhook connected, per-message billing).
>
> **Design discipline (frontend-design skill consulted):** every feature surfaces in the **premium
> Apple-like WhatsApp Campaign Workspace** (CREATIVE_STUDIO_PHASE2_SPEC §2), reusing the
> `core-2-dashboard-builder-react` COMPONENTS (cards/Table/Tabs/Modal/Switch/Select), Inter Display type,
> single `text-h4` heading with **no subtitle**, zero raw hex, dark premium dot-matrix loader for any
> generation step. **Layouts intentional per workflow; components mandatory-reuse.**

Research/verification date: 2026-06-11. Verified against the live sibling design docs + `WHATSAPP_GOLIVE.md`.

---

## 0. THE PRINCIPLE (read first — what "out of the box, no bloat" means here)

The founder said: *"Add new features out of the box no matter if I have told or not."* The trap is to bolt
on flashy features that each grow a new engine, a new money-door, or a new asset store — exactly the bloat
the architecture was designed to avoid. **The discipline:** every proposed feature must be expressible as a
**composition of seams that already exist** — a Workflow graph over `creative.*` + `whatsapp.*` tools, a new
read-join over the Testing Lab scoreboard, a new prompt-builder input, or a new card in the campaign
workspace. If a feature needs a net-new engine/queue/spend-path/store, it is **deferred or rejected**, not
shipped. That filter is applied to every candidate below; the ones that pass are the ones that turn the
WhatsApp module from a "send a template" tool into an **autonomous campaign system** at near-zero new
infrastructure.

**The five reuse pillars every feature snaps onto (no new ones invented):**
1. **`creative.*` contract** (integrations §1) — generate/edit/regenerate/approve/search/handoff, one risk
   table, one wallet path, one audit channel.
2. **WhatsApp creative kit + delivery** (`creative-whatsapp-creative.md`) — assemble_kit/send_kit,
   session-window detection, per-message meter (`vendor="whatsapp_creative"`), suppression, status webhook
   (delivered/read/click), `variant_id` tagging.
3. **Workflow Studio** (`platform-workflow-studio.md`) — durable Hatchet graph: `trigger(event/schedule/wait)`
   → `condition` → `delay`/`wait` → `action`/`ai_agent` → `budget`/`approval`. Creative+WhatsApp tools are
   Action nodes **out of the box**.
4. **Testing Lab scoreboard** (`creative-testing-lab.md`) — the cross-channel creative-DNA leaderboard that
   already unifies WhatsApp-replies + bookings + paid metrics on the creative tag.
5. **Wallet/audit/RLS + the live send path** — `wallet.reserve→settle/release` (INR paise, idempotent),
   `audit.record(channel="whatsapp"|"creative")`, FORCE-RLS, tenant-from-token-never-body, and the proven
   `/whatsapp/send` + `/whatsapp/inbound` routes.

---

## 1. THE CANDIDATE FEATURES (each: value · where it plugs in · effort · the seam it reuses)

Effort scale: **S** = a card/read-join over existing data; **M** = a workflow template + a small adapter or
prompt input; **L** = a new dormant-safe module/worker, still over existing engines. **No XL exists** — if a
feature would be XL (new engine), it was rejected (see §4).

### F1 — AI Auto Follow-Up Sequences (no-reply → reminder → last-chance) ⭐ TOP-5
- **Value (very high):** the single biggest revenue lever for WhatsApp. One send rarely converts; a
  3-touch sequence (send → wait 24h no-reply → reminder → wait 2d → last-chance/offer) multiplies replies
  and bookings with zero extra human effort. This is the founder's literal ask ("auto follow-up sequences,
  no-reply → reminder").
- **Where it plugs in:** ships as a **Workflow Studio template** + a one-click "Add follow-ups" toggle on a
  campaign card in the WhatsApp workspace. The graph is pure existing nodes:
  `Trigger(campaign.sent or lead.replied=false) → Delay(24h) → Condition(replied? via status webhook) ─no→
  Action(whatsapp.send reminder, reuses approved template/kit) → Delay(48h) → Condition(replied?) ─no→
  Action(whatsapp.send last-chance) ─yes(any step)→ Stop(exit sequence)`.
- **Reuses:** Workflow `trigger`/`delay`/`condition`/`action` (workflow-studio §4); the WhatsApp status
  webhook's delivered/read/**reply** signal as the Condition source (`creative-whatsapp-creative.md` §9
  `ingest_status` + caller.py `/whatsapp/inbound` thread store); suppression re-checked before each touch;
  per-message meter bills each touch honestly.
- **Effort: M** — it's a workflow template + a "replied since send?" condition helper + the workspace toggle.
  No new engine: durable Delay/Wait is native Hatchet (`ctx.aio_sleep_for`/`aio_wait_for_event`).
- **Guardrails:** every billed touch is rate-capped + suppression-gated + (optionally) approval-gated;
  reply at ANY step exits the sequence (no nagging a converted lead); cost-per-sequence shows on the card.

### F2 — Template Performance Leaderboard (winning templates surfaced + one-click reuse) ⭐ TOP-5
- **Value (high):** the founder's "surface winning templates / reuse winners" ask, made concrete. A ranked
  board of every WhatsApp template/angle by **reply rate · read rate · CTA-click · bookings · cost** lets
  the vendor instantly see what works and clone it — the learning loop made visible.
- **Where it plugs in:** a **"Top Templates" card/table** in the WhatsApp workspace, and the default sort
  for the template picker. It is a **read-join over the Testing Lab scoreboard** (`creative-testing-lab.md`
  already unifies WhatsApp-replies + bookings on the creative-DNA tag) filtered to `channel=whatsapp` —
  **no new metrics store.** Each row → a "Use this" / "5 more like this" action.
- **Reuses:** Testing Lab `scoreboard` read (DNA-tag rows); `creative.search(sort=top_ctr|top_reply,
  platform=whatsapp)` (library §6); the `variant_id`/`batch_id` tags every send already carries
  (`creative-whatsapp-creative.md` §1 REVENUE-CONNECTED); the "more like winner" regen
  (`creative.regenerate(mode=more_like_winner)`).
- **Effort: S–M** — mostly a read-join + a premium ranked card; the heavy lifting (cross-channel join,
  significance gate) is already the Testing Lab's job. Build = the WhatsApp-scoped view + the reuse actions.
- **Honest bound:** ranking needs real data; cold-start tenants see industry-pack defaults, not a populated
  board (don't fake numbers — show "collecting data" empty state per the no-fake-percentage loader rule).

### F3 — Per-Lead Personalized Banner + Message (segment/stage-aware creative) ⭐ TOP-5
- **Value (high, differentiating):** instead of one blast, each lead segment (hot/warm/missed-call/existing)
  gets a **stage-aware banner + copy** — the master DNA's "lead-follow-up banner (stage-aware)" +
  "personalization tokens." Hot leads get urgency/push; warm leads get reasons/trust; existing get
  loyalty/upsell. This is what makes Famit feel like a 1:1 system, not a mailmerge.
- **Where it plugs in:** the campaign workspace's audience selector already segments by lead-type
  (Run-Campaign filters hot/warm — `spec-run-campaign.md`); on "Generate creative for this audience" the
  builder calls `creative.generate(kind=wa_poster, segment=<stage>, campaign_id)` **once per segment**
  (not per person — bounded cost), and the caption uses WhatsApp's safe personalization tokens (name) the
  template supports. The poster set attaches per-segment in the same send flow.
- **Reuses:** `creative.generate` with the `segment`/angle DNA (master §8/§24 lead-stage); the WhatsApp
  kit's `angle` field (`WaKitSpec.angle`); CRM lead-stage signal (`platform-crm-core.md` / Run-Campaign
  segments); the **NO-INVENT guardrail** (never fabricate price/claims — tokens are name/segment only).
- **Effort: M** — a segment→angle map + a "generate per segment" loop in the builder; the generation,
  approval, attach, and send are all existing `creative.*`/kit calls. Bounded cost = N segments, not N leads.
- **Guardrail:** personalization tokens are limited to **safe, stored fields** (first name, segment); the
  banner text is per-segment, never per-person fabrication (master §20 text-accuracy firewall).

### F4 — WhatsApp + Voice-Call Combined Sequences (the cross-channel revenue play) ⭐ TOP-5
- **Value (very high, uniquely Famit):** Famit already owns the AI **voice** plane AND WhatsApp. The killer
  sequence chains them: *AI voice call → if interested/no-answer → auto-send WhatsApp creative kit (banner +
  brochure + price + booking link) → wait → if no reply, AI call-back or WhatsApp reminder.* The post-call
  WhatsApp send is **already designed** (`send_creative_package`, the headline integration at caller.py
  ~1248); this feature exposes it as a **composable sequence** the vendor builds in the workspace, plus the
  reverse (WhatsApp click → trigger an AI call).
- **Where it plugs in:** a Workflow template using existing triggers:
  `Trigger(call.completed, outcome=interested|no_answer) → Action(creative.send_to_whatsapp kit) →
  Delay(1d) → Condition(replied?) ─no→ Action(voice.callback OR whatsapp.send reminder)`. And the inverse:
  `Trigger(whatsapp.cta_click) → Action(voice.schedule_call)`.
- **Reuses:** the **post-call trigger already specced** (`creative-whatsapp-creative.md` §0/§8 — the
  headline integration); `call.completed` workflow trigger (workflow-studio §4.1 event triggers); the
  status-webhook CTA-click signal; the voice callback action the voice plane already exposes. **This is the
  cross-channel loop the architecture was built for — almost entirely wiring of existing seams.**
- **Effort: M** — two workflow templates + surfacing the already-designed post-call kit send as a node.
  The genuinely-new send shapes (media/interactive over WhatsApp) are already owned by the kit transport.
- **Honest bound:** cold post-call WhatsApp needs an approved Meta media-header template
  (`WHATSAPP_GOLIVE.md` — `hello_world` is test-only; founder must approve a real UTILITY template);
  category defaults to UTILITY framing for consent safety (`creative-whatsapp-creative.md` RED-TEAM B4).

### F5 — One-Click "Turn Winning Template into an Ad" (Adbot promotion) ⭐ TOP-5
- **Value (high, compounding):** the founder's explicit ask. When a WhatsApp template/angle wins on the
  leaderboard (F2), one click promotes its creative-DNA into a paid Meta/Google ad experiment — the
  WhatsApp channel becomes a **cheap, fast A/B lab that feeds paid spend only proven winners.** This is the
  growth flywheel the master spec draws (WhatsApp angles → winners → Adbot).
- **Where it plugs in:** a **"Promote to Ads"** action on a winning leaderboard row → `creative.send_to_adbot`
  with the asset's approved variants; the ads-engine's `propose_experiment` ingests it
  (`creative-ads-engine.md` §3.1). Only `status∈{approved,winner}` assets are eligible (the hard rule).
- **Reuses:** `creative.send_to_adbot` (integrations §1.1); the ads-engine variant→test→scale/kill loop
  (it owns the spend, the bandit, the approval gate — we only hand off approved DNA); Testing Lab's
  cross-channel winner classification (it already knows the WhatsApp winner). **No ad spend logic here —
  the money gate lives in the ads-engine's envelope + step-up.**
- **Effort: S–M** — a button wired to the existing `send_to_adbot` handoff + the eligibility filter; the
  whole ads loop already exists. Net-new = the workspace action + the "this WhatsApp winner → ad draft" UX.
- **Guardrail:** approval is the content-policy firewall (only approved assets leave); net-new ad spend is
  **human-approved by default** (ads-engine FIX A) — promotion creates a DRAFT experiment, not a live spend.

### F6 — Drip / Journey from the Workflow Builder (visual multi-step campaigns)
- **Value (high):** a visual journey designer for multi-step WhatsApp campaigns (welcome → educate →
  offer → win-back) — the founder's "drip/journey from the workflow builder" ask. This is the **generalized
  form** of F1/F4 (named flows are templates within it).
- **Where it plugs in:** the **existing React-Flow Workflow Studio** (`platform-workflow-studio.md` /
  `spec-workflow-builder.md`) — WhatsApp + creative actions are already Action nodes. The new bit is a
  **WhatsApp-journey starter palette** + 3–4 prebuilt journey templates surfaced from the WhatsApp workspace
  ("Start a journey").
- **Reuses:** the entire workflow engine (durable, multi-tenant, BUDGET/APPROVAL dominator-enforced); the
  `creative.*`/`whatsapp.*` Action nodes; the two founder flow templates already specced (integrations §5.2).
- **Effort: M** — journey templates + the WhatsApp-workspace entry point into the existing builder. **The
  engine is fully built; this is templates + a launch surface, not a new builder.**
- **Note:** F1 (follow-ups) and F4 (cross-channel) are the two most-valuable concrete journeys; F6 is the
  open-ended canvas behind them. Ship F1/F4 as templates first, expose the full canvas (F6) right after.

### F7 — Quick-Reply / Button Automation (interactive buttons → auto-actions)
- **Value (high):** WhatsApp interactive messages support buttons (quick-reply + CTA-URL). When a lead taps
  "Yes, book a visit" / "Send price" / "Call me," the platform **auto-responds or routes** — no human.
  Turns a broadcast into a conversation that books itself.
- **Where it plugs in:** the kit transport **already builds CTA-URL/interactive messages**
  (`creative-whatsapp-creative.md` §4 `send_interactive`); the inbound webhook **already parses replies**
  (caller.py `/whatsapp/inbound`). New = a small **button→action router**: a button payload becomes a
  Workflow `wait`-trigger (`lead.replied` with the button id) → branch (book / send price / schedule call).
- **Reuses:** the existing interactive send shapes; the inbound webhook + thread store; the workflow
  `wait`/event trigger (`lead_reply:<phone>`, workflow-studio §4.1) and `condition` branch; the suppression
  + opt-out words already parsed on inbound.
- **Effort: M** — a button-payload→event mapper feeding the existing `wait` trigger, + 2–3 default button
  flows (Book / Price / Call-me). The send shapes and webhook exist; this routes their output.
- **Honest bound:** WhatsApp interactive buttons have hard limits (quick-reply ≤3, CTA single URL ≤20 bytes
  — `creative-whatsapp-creative.md` §1) — the UX respects them, doesn't promise arbitrary button menus.

### F8 — Multi-Language Auto-Variants (English / Hindi / Hinglish / regional, one click)
- **Value (high in-market):** the master Language DNA (English/Hindi/Hinglish/Gujarati-local). One campaign
  → the AI generates the **same message + banner in N languages**, each a tagged variant, send the right
  language per lead's known language (or test all). Doubles reach in India's mixed-language market.
- **Where it plugs in:** `creative.edit(asset_id, "Hinglish version")` and the kit's `WaKitSpec.language`
  field already exist (master §26 NL editing "Hinglish version"; kit `language: en|hi|...`). New = a
  **"Generate language variants" toggle** that fans out N `creative.generate`/`edit` calls (one per language)
  → N tagged kits; the send picks per-lead language or A/B tests them (each `variant_id` measured separately).
- **Reuses:** `creative.edit`/`generate` language support; the kit `language` field; the per-variant
  metering + Testing Lab join (which language wins is just another scoreboard breakdown);
  non-Latin-script routing already handled (kit notes `hi` → image model that renders Devanagari).
- **Effort: M** — a language fan-out loop + the per-lead language pick; generation/edit/measure all exist.
- **Guardrail:** language variants are **style/translation**, never fact changes (master §20 — never invent
  price/claims, even across languages); credit-estimated up front ("3 languages ≈ N credits. Continue?").

### F9 — AI Best-Send-Time (per-lead optimal delivery window)
- **Value (medium-high):** instead of blasting at one time, schedule each lead's message for **when that
  lead historically reads/replies** (or a per-tenant learned window). Lifts read/reply rates measurably,
  protects WhatsApp quality rating (no 2 a.m. sends).
- **Where it plugs in:** a **send-time resolver** the WhatsApp send path / workflow Delay node calls before
  dispatch: it reads the lead's prior read/reply timestamps (status webhook history) or the tenant's
  aggregate best window, and schedules via the durable Delay (`ctx.aio_sleep_for` to the next good slot).
- **Reuses:** the status-webhook read/reply timestamps already ingested (`ingest_status`); the durable
  Delay node (workflow-studio §4.7); the existing scheduler — **no new ML service**: v1 = a simple
  per-tenant/per-lead heuristic (mode of past read hours), honestly labeled, not a black-box "AI."
- **Effort: M** — a read-time heuristic over existing webhook history + a schedule-to-slot helper on the
  Delay/send path. **Deliberately not a new prediction engine** — that would be the bloat we reject (§4).
- **Honest bound:** cold leads have no history → fall back to a tenant-default window (e.g. local business
  hours); never claim ML-grade prediction — it's a transparent heuristic that improves with data.

### F10 — Campaign-Performance → Auto-Regenerate Winners (closed creative loop)
- **Value (high, autonomous):** when a template's reply/booking rate beats a threshold, **auto-trigger
  "5 more like this winner"** to seed the next batch; when one underperforms, flag for regeneration. The
  master's "performance back → more variants from winners," running without a human poking it.
- **Where it plugs in:** a Workflow `Trigger(schedule weekly) → Action(testinglab.rank) → Condition(winner
  above threshold?) → Action(creative.regenerate mode=more_like_winner) → Approval → ready for next send`.
- **Reuses:** Testing Lab ranking + weak/winner classifier (`creative-testing-lab.md` §6 — it already emits
  a "regenerate this DNA" handoff); `creative.regenerate`; the workflow schedule trigger + approval gate.
- **Effort: S–M** — a scheduled workflow template over the Testing Lab handoff that already exists; the
  classifier and regen are built. Net-new = the template + the threshold UX.
- **Guardrail:** auto-regen produces **drafts** (approval before they spend on a send); the loop biases
  style toward winners, never fabricates facts (integrations §7 honest boundary).

### F11 — Brand-Voice + Compliance Pre-Send Check (safety net, surfaced)
- **Value (medium, trust/cost-saving):** before any send, a cheap local check flags off-brand tone or
  risky claims (RERA/"guaranteed returns"/medical-cure) for review — prevents a WhatsApp-quality-rating hit
  or a policy strike that would cost the number.
- **Where it plugs in:** the **safety prefilter already specced** (`creative-whatsapp-creative.md` §6.6 +
  RED-TEAM) surfaced as a visible "1 issue flagged" chip on the template card, not a silent backend gate.
- **Reuses:** the existing denylist prefilter + the master NO-INVENT guardrails; the approval gate.
- **Effort: S** — surface the existing prefilter result in the UI; no new logic.
- **Honest bound:** first-line only — not a substitute for Meta's own policy review (kept honest per §10).

### F12 — Reusable Campaign Snapshots (clone a whole winning campaign) 
- **Value (medium-high):** the master's "templates/creatives/campaign structures are reusable assets
  (clone/optimize/repurpose)." One click clones a past winning campaign (audience + creative set + sequence
  + send-time) into a new draft to tweak and relaunch.
- **Where it plugs in:** a "Clone campaign" action that snapshots the campaign's workflow-graph + attached
  approved `AssetRef`s + audience filter into a new draft. It's a **copy of existing records**, not a new
  store.
- **Reuses:** the workflow def versioning (workflow-studio's 6 tables already version defs/runs); the asset
  library `AssetRef`s (versioned, campaign-linked); the audience filter from Run-Campaign.
- **Effort: S–M** — a snapshot/clone over existing versioned records.

---

## 2. TOP-5 FOR PHASE-1 (the prioritized set — highest value ÷ effort, max reuse, least bloat)

> Selection logic: each must (a) be a top-tier **revenue or learning** lever, (b) ride **only existing
> seams** (no new engine/money-path/store), (c) be **S–M effort**, and (d) **compound** with the others into
> a coherent autonomous-campaign story. The five below form one loop: **personalize → sequence → measure →
> reuse winners → promote to ads**, with voice+WhatsApp as Famit's unique cross-channel edge.

| # | Feature | Value | Effort | Seam it rides (zero new engine) | Why Phase-1 |
|---|---|---|---|---|---|
| **1** | **AI Auto Follow-Up Sequences** (F1) | ★★★★★ biggest reply/booking lever | **M** | Workflow trigger/delay/condition/action + WhatsApp reply webhook + suppression/meter | One send underconverts; auto follow-ups are the highest-ROI add and pure node composition. |
| **2** | **WhatsApp + Voice-Call Combined Sequences** (F4) | ★★★★★ uniquely Famit | **M** | Already-specced post-call kit send (`send_creative_package`) + `call.completed` trigger + CTA-click | Famit owns BOTH channels — the cross-channel loop is the moat; the post-call send is already designed. |
| **3** | **Per-Lead Personalized Banner + Message** (F3) | ★★★★ 1:1 feel, conversion | **M** | `creative.generate(segment, campaign_id)` + kit `angle` + CRM lead-stage + NO-INVENT guard | Stage-aware creative is the master DNA and what makes it feel personal, not mailmerge. Bounded cost (per-segment). |
| **4** | **Template Performance Leaderboard + 1-Click Reuse** (F2) | ★★★★ learning made visible | **S–M** | Testing Lab scoreboard read-join (channel=whatsapp) + `creative.search(sort=top_reply)` + regen | Closes the learning loop in the UI; mostly a read-join over data the Testing Lab already computes. |
| **5** | **One-Click "Turn Winning Template into an Ad"** (F5) | ★★★★ compounding flywheel | **S–M** | `creative.send_to_adbot` (approved-only) → ads-engine `propose_experiment` (owns spend) | WhatsApp becomes the cheap A/B lab that feeds paid spend only proven winners — founder's explicit ask. |

**Why these five together (the compounding story):** #3 makes each touch *personal*, #1 makes it a
*sequence*, #4 *measures* which template/angle wins, #5 *promotes* the winner to paid ads, and #2 fuses it
with Famit's voice plane into a cross-channel loop no single-channel competitor can match. They share one
contract (`creative.*`), one money-path (wallet), one audit channel, one library — **maximum new value,
minimum new surface.** Each is independently shippable and dormant-safe (degrades to `not_configured` until
creds), so they can land one verifiable unit at a time.

**Phase-1 build order (small verifiable units, all dormant-safe):**
1. **F2 leaderboard** first (S–M, read-only) — it's the lowest-risk, surfaces value immediately, and its
   `variant_id` plumbing is the substrate the others measure against.
2. **F1 follow-ups** (M) — the highest-ROI lever; a workflow template + reply-condition + workspace toggle.
3. **F3 per-segment creative** (M) — the segment→angle generate loop into the builder.
4. **F4 voice+WhatsApp** (M) — surface the already-designed post-call kit send as a sequence node + the
   `call.completed`/CTA-click triggers. (Needs the approved Meta template — founder-side, per GOLIVE.)
5. **F5 promote-to-ad** (S–M) — the `send_to_adbot` button on a winning leaderboard row.

---

## 3. PHASE-2+ BACKLOG (valuable, defer until the top-5 land)

F6 Drip/Journey full canvas (the general form of F1/F4 — ship after the two named journeys prove out) ·
F7 Quick-reply/button automation (high value; needs the button→event router) · F8 Multi-language
auto-variants (high in-market value; a language fan-out) · F9 AI best-send-time (start as a transparent
heuristic, not ML) · F10 auto-regenerate-winners (scheduled loop over the Testing Lab handoff) ·
F11 brand/compliance pre-send chip (surface the existing prefilter) · F12 reusable campaign snapshots
(clone over versioned records). **All ride existing seams** — none is rejected, just sequenced behind the
revenue-critical five.

---

## 4. WHAT I DELIBERATELY REJECTED (anti-bloat — features that would grow a new engine)

| Tempting feature | Why rejected (would violate the no-new-engine rule) |
|---|---|
| A bespoke **ML send-time prediction service** | A new model/training/inference engine for marginal lift. F9 instead uses a transparent per-tenant heuristic over data we already ingest — same direction, ₹0 new infra. |
| A **second analytics/metrics store** for WhatsApp | The Testing Lab + status webhook + per-message meter already hold every signal. A leaderboard (F2) is a read-join, not a new store. |
| A **template marketplace / cross-tenant sharing** | RLS isolation is sacrosanct (tenant-from-token, FORCE-RLS). Cross-tenant template sharing is a security + data-governance project, not a quick add — out of scope. |
| **Autonomous bidding / spend optimization inside WhatsApp** | The ads-engine owns spend, the bandit, and kill/scale. WhatsApp emits `variant_id` signals and hands winners over (F5); it never bids. (Explicitly out per `creative-whatsapp-creative.md` R5.) |
| **Fire-and-forget mass blaster** (no approval, no caps) | Violates the approval gate + rate caps + opt-out + consent posture; tanks WhatsApp quality rating; policy/DLT risk. Every send stays gated. |
| **Arbitrary button menus / chatbot NLU in-thread** | WhatsApp's interactive limits (≤3 quick-reply, single CTA) are hard; deep conversational NLU is the AI-Manager's job, not a WhatsApp-campaign feature. F7 stays within the platform's real button limits. |

---

## 5. SECURITY / HONESTY POSTURE (every feature inherits these — no exceptions)

- **One money-path:** generation credits via `wallet.py` (idempotent, no-double-spend); WhatsApp send cost
  via the per-message meter; ad spend via the ads-engine envelope. No feature opens a second spend door.
- **Tenant from token, never body;** FORCE-RLS on `ai_asset_*`; every handoff re-asserts ownership.
- **Approval = the content-policy firewall** before any machine-made creative spends money or faces Meta
  review; default biases safe (human-approved, no auto-launch).
- **Suppression + opt-out enforced before EVERY send** (legal/trust, non-negotiable); rate caps + optional
  rupee stop-loss bound autonomous template spend.
- **Dormant-until-creds everywhere** — no Meta/OpenRouter key → features degrade to `not_configured`,
  never raise into a call/workflow/dial loop.
- **Honest, never overclaimed:** sequences/leaderboards/best-send-time **bias and assist**; they don't
  guarantee conversions, never fabricate facts (price/RERA/claims), and cold-start tenants fall back to
  industry/heuristic defaults — shown as honest empty states (the no-fake-percentage rule), not invented numbers.
- **Real-vs-hype line (carried from GOLIVE):** cold WhatsApp sends need a Meta-approved media-header
  template (founder-side); `hello_world` is test-only; the post-call window is opened by an inbound WhatsApp
  message, not a voice call — so cross-channel (F4) cold sends take the billed template path until that
  template is approved.

---

## 15-LINE SUMMARY (for the orchestrator)

1. This doc proposes + prioritizes **out-of-the-box WhatsApp-campaign features** that ride ONLY existing
   seams (the `creative.*` contract, WhatsApp kit/delivery, Workflow Studio, Testing Lab, Adbot, wallet/
   audit/RLS, the live `/whatsapp/send`+`/inbound`) — **no new engine, money-path, or asset store.**
2. The anti-bloat filter: a feature ships only if it's a **composition of seams that already exist** — a
   workflow graph, a read-join, a prompt-builder input, or a workspace card; anything needing a net-new
   engine is rejected (§4).
3. **12 candidates** scored by value · plug-in seam · effort (S/M only — no XL survives the filter).
4. **TOP-5 for Phase-1:** F1 Auto Follow-Up Sequences · F4 WhatsApp+Voice Combined Sequences · F3 Per-Lead
   Personalized Banner+Message · F2 Template Performance Leaderboard+1-click-reuse · F5 One-Click
   Winning-Template→Ad.
5. They form ONE compounding loop: **personalize → sequence → measure → reuse winners → promote to ads**,
   with voice+WhatsApp as Famit's unique cross-channel moat.
6. **F1 (follow-ups)** = highest-ROI lever; a Workflow template (trigger→delay→condition→action) over the
   reply webhook + suppression/meter. Effort M, no new engine (durable Delay = native Hatchet).
7. **F4 (voice+WhatsApp)** = uniquely Famit; the post-call kit send (`send_creative_package`) is ALREADY
   designed — this exposes it as a composable sequence + the `call.completed`/CTA-click triggers. Effort M.
8. **F3 (personalized creative)** = stage-aware banner+copy per segment via `creative.generate(segment,
   campaign_id)`; bounded cost (per-segment, not per-lead); NO-INVENT guard holds. Effort M.
9. **F2 (leaderboard)** = a read-join over the Testing Lab scoreboard (channel=whatsapp) + `creative.search
   (sort=top_reply)` + one-click "5 more like this." Mostly UI; the metrics already exist. Effort S–M.
10. **F5 (promote-to-ad)** = `creative.send_to_adbot` on an approved winning row → ads-engine owns the spend;
    WhatsApp becomes the cheap A/B lab feeding paid only proven winners. Effort S–M.
11. **Build order:** F2 (read-only, lowest risk) → F1 → F3 → F4 → F5; each a verifiable, dormant-safe unit.
12. **Phase-2 backlog (all ride existing seams):** F6 drip/journey full canvas, F7 quick-reply/button
    automation, F8 multi-language auto-variants, F9 AI best-send-time (transparent heuristic, not ML),
    F10 auto-regenerate-winners, F11 brand/compliance pre-send chip, F12 reusable campaign snapshots.
13. **Rejected (anti-bloat):** bespoke ML send-time service, a second WhatsApp metrics store, cross-tenant
    template marketplace, in-WhatsApp autonomous bidding, fire-and-forget blaster, arbitrary button NLU.
14. **Security/honesty inherited by all:** one money-path, tenant-from-token, FORCE-RLS, approval =
    content-policy firewall, suppression-before-every-send, dormant-until-creds, never fabricate facts.
15. **UI:** every feature lands in the premium Apple-like WhatsApp Campaign Workspace, reusing
    `core-2-dashboard-builder-react` components, Inter Display, single `text-h4` heading (no subtitle), zero
    raw hex, the dark dot-matrix loader for any generation step. **Components mandatory; layouts intentional.**
```
