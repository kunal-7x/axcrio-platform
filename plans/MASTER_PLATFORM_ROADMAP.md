# MASTER PLATFORM ROADMAP — Module Map + Prioritized Build Sequence

> **What this file is:** (1) a **MODULE MAP** — every one of the ~54 modules/systems mapped to
> EXISTS(reuse) / EXTEND / NEW, to its architectural plane, to its dependencies, and to its sidebar
> section; and (2) a **PRIORITIZED, FOUNDATIONAL-FIRST ROADMAP** — the cross-cutting systems before
> the leaf modules, each phase shippable + non-breaking, reusing the head-start.
>
> **Binding inputs (not re-opened here):** `MASTER_VISION.md` (the product), `ARCHITECTURE_DECISION.md`
> (coarse planes + modular monolith), `EXECUTION_PLAN.md` (the in-flight P0→P4 unit sequence), the live
> `/api` contract (HANDOFF), and the build_log. **This roadmap INHERITS the in-flight technical
> foundation (P0→P4) as its foundation tier** — it does not author a parallel sequence. The 54-module
> rollout is the expansion of the already-sketched Phases 5–9.

---

## 0. THE FOUR PLANES (where every module lives)

From `ARCHITECTURE_DECISION.md` — committed, not re-opened:

- **CP** = **Control-plane API** (modular monolith, FastAPI, Postgres+RLS). Almost every module's
  CRUD/business logic lives here as a per-domain `APIRouter` + per-domain schema.
- **VP** = **Voice / media plane** (LiveKit `agent.py` + SIP). Latency-critical, already its own process.
- **OS** = **Orchestration spine** (Hatchet). Durable multi-step/async/scheduled work + retries.
- **AE** = **Ads / video / render engine** — the *one named future service* (GPU/batch). Only the
  heavy creative/render path.
- **PANEL** = the Next.js panel (own deploy unit). Every module also has a PANEL surface.

A module's "plane" below names where its **core logic** runs; nearly all also have a PANEL page.

---

## 0a. SIDEBAR INFORMATION ARCHITECTURE (8 collapsible sections)

> The canonical IA. (`MASTER_VISION.md §7` carries the prose; this table is the binding grouping the
> roadmap's "§7 sidebar regroup" refers to.) The 34 sidebar modules group into **8 collapsible
> sections** using the **exact pattern already shipped for Billing** (`contstants/navigation.tsx`:
> a parent with no `href` + a `list` of child routes, rendered by `Sidebar/Dropdown`/`AnimateHeight`).
> **Non-breaking by construction:** every currently-live route is absorbed into a section — a
> **regroup, not a rebuild**; no live page is orphaned. A–H map to the core-loop phases.

| # | Section (collapsible parent) | Modules grouped under it | Absorbs live routes |
|---|---|---|---|
| **A** | **Command** | Dashboard, AI Manager, AI Task Manager, Omnichannel Inbox, Notifications | `/` |
| **B** | **Grow** (Marketing) | Campaigns, Creative Studio, Ad Automation, Funnels, Website/Landing, Form Builder, Research/Competitor Intel | `/campaigns` |
| **C** | **Sell** (Revenue) | Leads, CRM, Contacts, Sales Pipeline, Segmentation, Offer/Discount, Proposal/Quotation, Referral, Loyalty | `/leads` |
| **D** | **Engage** (Conversations) | AI Voice Calls, Run, Call Logs, WhatsApp Automation, Customer Support, Booking/Appointments, Reviews/Reputation, Callbacks | `/run`, `/calls`, `/whatsapp`, `/callbacks` |
| **E** | **Automate** | Workflow Builder, Lifecycle Triggers, AI Workforce, Industry Packs, Template Library, Integrations | `/webhooks` |
| **F** | **Money** | Payments/Collections, Billing/Credits/Wallet, Revenue Attribution | `/billing/*` |
| **G** | **Intelligence** | Analytics/Reports, Conversation Intelligence, Experimentation Lab, AI Quality Review, Business Digital Twin, Survey/Feedback | `/analytics` |
| **H** | **Foundation** | Business Brain, Knowledge Base, Assets/Documents, Compliance/DND/Consent, Team/Roles, Settings, Admin/Super-Admin, Integrations (keys) | `/suppression`, `/vendors`, `/settings` |

**Modes that WRAP the whole sidebar (not nav rows):** Agency/Multi-Client, White-Label, Public
Customer Portal, Marketplace/App-Store, Mobile App, 3D Studio — surfaces/modes reached contextually.

---

## 1. MODULE MAP (all ~54 modules / systems)

**Status legend:** **EXISTS** = already built & live, reuse as-is · **EXTEND** = built but partial /
dormant / needs widening · **NEW** = not built. *(Honest accounting: the head-start genuinely covers
~12 of 54; most are NEW. Where a module is split, the split is called out.)*

### Section A — Command

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| Dashboard | **EXTEND** | CP+PANEL | Analytics, all modules | Live `/` + `/stats`; extend to AI-workforce activity + revenue. |
| AI Manager (voice command center) | **NEW (designed)** | VP+CP+OS | Auth, Action Firewall, Audit, Business Brain, AI Workforce | Voice-first copilot; spec `platform-ai-manager.md` (delegates to workforce runner; audio PIN-leak closed). |
| AI Task Manager | **NEW** | CP+OS | Hatchet, Audit, RBAC | Workforce task queue + operator approvals queue. |
| Omnichannel Inbox / Notifications | **NEW** | CP | WhatsApp, Voice, Support, Conversation Intel | Unifies #40/#44; one inbox across channels. |

### Section B — Grow (Marketing)

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| Campaigns | **EXISTS** | CP+PANEL | Leads, Voice, Business Brain | Live: `/campaigns`, extract-from-brief, A/B variants. |
| Creative Studio | **NEW** | AE+CP | Business Brain, Assets, Ad Automation | AI copy/image/video; render = ads/video engine. |
| Ad Automation | **NEW** | CP+OS(+AE) | Auth, Action Firewall, Wallet/Budget, Integrations | = OCEAN Phase-8; spend-capped Meta/Google. |
| Funnels | **NEW** | CP+PANEL | Campaigns, Landing, Forms, Attribution | Multi-step conversion funnels. |
| Website / Landing Pages | **NEW** | CP+PANEL | Forms, Assets, Funnels | Hosted pages + lead capture. |
| Form / Lead-Capture Builder | **NEW** | CP+PANEL | Leads, Landing | Feeds the loop's lead-capture hop. |
| Research / Competitor Intelligence | **NEW** | CP+OS | Business Brain, KB | Research agent; async via Hatchet. |

### Section C — Sell (Revenue)

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| Leads | **EXISTS** | CP+PANEL | Campaigns, CRM | Live: `/leads`, scoring, hot-list, dedupe. |
| CRM | **NEW (designed)** | CP+PANEL | Leads, Contacts, Pipeline, per-lead memory | System of record; spec `platform-crm-core.md` (canonical-phone fix; shared admission gate). |
| Contacts | **EXTEND** | CP+PANEL | Leads, WhatsApp threads | Thin today (phone→lead resolve); extend to directory. |
| Sales Pipeline | **NEW** | CP+PANEL | CRM, Booking, Payments | Stages, forecast. |
| Customer Segmentation | **NEW** | CP | Leads, CRM, Analytics | Audience segments for campaigns. |
| Offer / Discount Engine | **NEW** | CP | Campaigns, Payments | Offer logic + redemption. |
| Proposal / Quotation Generator | **NEW** | CP+AE | Business Brain, CRM, Documents | AI-drafted quotes. |
| Referral Engine | **NEW** | CP | CRM, WhatsApp, Payments | Referral loops. |
| Loyalty / Membership | **NEW** | CP | CRM, Payments | Retention layer. |

### Section D — Engage (Conversations)

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| AI Voice Calls | **EXISTS** | VP | LiveKit, SIP, prompt, memory | Live; the crown jewel. Semantic-turn/RAG = EXTEND (Phase 2). |
| Run (dial dispatch) | **EXISTS** | CP+OS | Campaigns, Leads, scheduler | Live `/run`; cutover to Hatchet = Phase 3. |
| Call Logs | **EXISTS** | CP+PANEL | Voice, transcripts | Live `/calls`, `/calls/{id}` transcript+summary. |
| WhatsApp Automation | **EXTEND** | CP | Meta creds, Groq, threads | Built + DORMANT; flips live on Meta creds. |
| Customer Support | **NEW** | CP+OS | Knowledge Base (RAG), Inbox | AI support agent + tickets. |
| Booking / Appointments / Site-Visits | **NEW** | CP+OS | CRM, calendar, Notifications | Calendar + reminders via Hatchet. |
| Callbacks | **EXISTS** | CP+OS | scheduler, Voice | Live `/callbacks` + scheduler dispatch. |
| Reviews / Reputation | **NEW** | CP+OS | CRM, WhatsApp, Integrations | Solicit + respond + monitor. |

### Section E — Automate

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| Workflow Builder (Automation Studio) | **NEW (designed)** | CP+OS+PANEL | Hatchet, Action Firewall, Audit, all modules | Spec `platform-workflow-studio.md`; graph emits into Hatchet, reuses AI-Manager tool registry. |
| Lifecycle Trigger Engine | **NEW** | CP+OS | Hatchet, Business Brain, CRM | Proactive re-engagement by service cycle. |
| AI Workforce runtime | **NEW (FOUNDATIONAL, designed)** | CP+OS+VP | Business Brain, KB, Auth, Firewall, Audit | Spec `platform-ai-workforce.md`; roles-as-data over one `AgentRunner`. |
| Industry Packs | **NEW** | CP | Business Brain, KB, Templates | Per-vertical prompt/flow/KB/creative bundles. |
| Template Library | **NEW** | CP | Workflow, Campaigns, Creative | Reusable templates + marketplace seed. |
| Integrations | **EXTEND (designed)** | CP | webhooks engine, Auth | Live: outbound webhooks (HMAC). Spec `platform-integrations-hub.md` extends to inbound + OAuth connector vault. |

### Section F — Money

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| Billing / Credits / Wallet | **SPLIT: meter EXISTS / wallet NEW** | CP | Postgres (ACID), Auth, Payments | Vendor-cost **meter** is LIVE (`/billing/*`, real Vobiz/Groq/Sarvam/EL cost). The customer-facing **ACID credit wallet** is NEW — the *build-don't-compose* exception (Phase 4, schema-first). |
| Payments / Collections | **NEW** | CP+OS | Razorpay/Stripe creds, Wallet | Invoices, links, dunning. |
| Revenue Attribution (+ Ledger) | **NEW (FOUNDATIONAL-ish)** | CP | Campaigns, Voice, Payments, Analytics | Ties revenue to source; durable attribution ledger. |

### Section G — Intelligence

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| Analytics / Reports | **EXISTS** | CP+PANEL | calls, leads, billing | Live `/analytics` funnel + `/stats`. Extend to cross-module. |
| Conversation Intelligence | **NEW** | CP+OS | transcripts, RAG, Analytics | Mines calls/chats for signals/sentiment/objections. |
| Experimentation Lab | **EXTEND** | CP+PANEL | A/B engine, Analytics | A/B variants engine EXISTS (`/campaigns/{id}/ab`); extend to multivariate across channels. |
| AI Quality Review | **EXTEND** | OS(offline)+PANEL | eval/replay harness | Eval harness scaffolded (`[WT:eval]`); add human-review UI. |
| Business Digital Twin | **NEW** | CP+OS | Business Brain, Analytics, Attribution | Simulatable what-if model. |
| Survey / Feedback Engine | **NEW** | CP+PANEL | WhatsApp, Forms, CRM | Post-interaction surveys. |
| 3D Product / Property Studio | **NEW** | AE+PANEL | Assets, Creative Studio | 3D/360 product & property viz; render via ads/video engine. (Sidebar module #24; reachable contextually.) |

### Section-spanning / operational modules

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| Document / Contract Automation | **NEW** | CP+AE | Business Brain, CRM, Assets, Proposal | Generate/fill/e-sign contracts; attaches to Sell + Engage. |
| Inventory / Capacity Management | **NEW** | CP | Booking, Sales Pipeline | Stock/slot/capacity tracking; gates Booking + Offers. |

### Modes & Surfaces (wrap the whole platform — not nav rows, but still mapped)

| Module | Status | Plane | Depends on | Attaches to |
|---|---|---|---|---|
| Agency / Multi-Client Mode | **NEW** | CP+PANEL | Auth/orgs, RBAC, all modules | A super-tenant managing many client tenants. |
| White-Label Mode | **NEW** | CP+PANEL | Settings, Auth, branding | Per-tenant branding/domain over the whole UI. |
| Public Customer Portal | **NEW** | CP+PANEL | CRM, Booking, Payments, Support | The end-customer-facing surface (self-serve). |
| Marketplace / App-Store | **NEW** | CP+PANEL | Template Library, Workflow, Integrations | Sell/install workflow + integration + pack templates. |
| Mobile App | **NEW** | PANEL(native) | the CP `/api` contract | Operator app over the same API. |

### Section H — Foundation (operator-facing config of the foundational systems)

| Module | Status | Plane | Depends on | Notes |
|---|---|---|---|---|
| Business Brain | **NEW (FOUNDATIONAL, designed)** | CP | Postgres, RAG | Spec `platform-business-brain.md`. Canonical business config every worker reads; create-time snapshot into prompts. |
| Knowledge Base | **NEW (FOUNDATIONAL, designed)** | CP | pgvector RAG (F2) | Spec `platform-knowledge-rag.md`. The RAG corpus the workforce answers from; voice corpus is a scoped subset. |
| Assets / Documents | **NEW** | CP | DO Spaces, Auth | Media + document library. |
| Compliance / DND / Consent | **EXTEND** | CP+VP | suppression, calling-window | DND suppression + window EXIST; extend to consent + DLT/DPDP-as-product. |
| Team / Roles / Permissions | **EXISTS** | CP | Auth | Live: admin/manager/agent RBAC, `/tenants`, `/me`. |
| Settings | **EXTEND** | CP+PANEL | Auth, all modules | Live `/settings`; extend to per-tenant config/branding/keys. |
| Admin / Super-Admin | **EXISTS** | CP+PANEL | Auth (admin) | Live: `/tenants`, `/vendors`, usage-all, limits. |

### Cross-cutting foundational systems (the spine — built BEFORE the leaves)

> **Now all DESIGNED.** Each row points to its durable, adversarially-red-teamed spec under
> `design/`. "NEW (FOUNDATIONAL)" = no code yet, but the build spec exists and is GO.

| System | Status | Plane | Design spec + notes |
|---|---|---|---|
| **Postgres + RLS substrate** | **EXTEND (in-flight)** | CP | `p1-postgres.md`. P1 keystone; `store.py` seam in, leads `dual`, shadow_diff==0. Only at U1-in-progress — the dominant blocker. |
| **Auth / RBAC / orgs (Logto) + twice-enforced isolation** | **EXTEND** | CP | `auth-logto.md`. RBAC + JWT + tenants LIVE; Logto OIDC + JIT = F4. |
| **Action Firewall (PIN/OTP) + immutable Audit Ledger** | **NEW (FOUNDATIONAL)** | CP | `credit-ledger-firewall.md`. F4. The gate every AI action passes through. *Prereq fold (business-brain RT-2): a Brain identity/pricing/disclosure write is a NEW `brain.write` scope that must be registered before any AI-Manager Brain-write ships.* |
| **Credit / Wallet ledger (money custody)** | **NEW (FOUNDATIONAL)** | CP | `credit-ledger-firewall.md`. F4 build-don't-compose exception; ACID, schema-gated on P1 (G0 hard gate: no JSON wallet). |
| **Hatchet orchestration spine + eval harness** | **EXTEND (engine-startable)** | OS | `orchestration-hatchet.md` + `eval-harness.md`. Engine deploy parallel now; write-path cutovers (H5/H7) gate on P1 finalize write-set. |
| **Business Brain + Knowledge Base (RAG)** | **NEW (FOUNDATIONAL)** | CP | `platform-business-brain.md` + `platform-knowledge-rag.md` + `dynamic-context-rag.md`. The shared context every worker reads; create-time snapshot into prompts (brain edits don't rewrite live campaigns — RT-3). |
| **AI Workforce runtime** | **NEW (FOUNDATIONAL)** | CP+OS+VP | `platform-ai-workforce.md`. Roles-as-data over one `AgentRunner`; resource-stable idempotency `<run_id>:<tool>:<resource_id>` (RT-2); BUDGET + APPROVAL are two separate gates. |
| **AI Manager (voice command center)** | **NEW (FOUNDATIONAL)** | VP+CP+OS | `platform-ai-manager.md`. Owns the voice front-door; delegates to the workforce runner (does NOT re-implement it). Audio-channel PIN-leak handled (recorder-pause + DTMF/OTP). |
| **Workflow Automation engine** | **NEW (FOUNDATIONAL)** | CP+OS | `platform-workflow-studio.md`. Graph over Hatchet; reuses the AI-Manager tool registry (one money-path, one gate, one audit) — engine refuses to compile a BUDGET/APPROVAL violation. |
| **Integrations Hub (credential vault + connectors)** | **NEW (FOUNDATIONAL)** | CP | `platform-integrations-hub.md`. OAuth/API-key vault (Fernet-encrypted), provider-agnostic adapters, inbound webhook verify. Money tools refuse to execute outside the budget-gated runner (RTF-1). |
| **CRM core (system-of-record + lifecycle)** | **NEW (FOUNDATIONAL-ish)** | CP+OS | `platform-crm-core.md`. Canonical-phone fix; shared `_admission_gate` so workforce/lifecycle spend is admission-checked, not just `/run` (RTF-1). |
| **Omnichannel Inbox / Notifications + Lifecycle Trigger Engine** | **NEW** | CP+OS | Proactive + unified-comms backbone (lifecycle spine specced in `platform-crm-core.md §lifecycle`). |
| **Revenue Attribution + Conversation Intelligence** | **NEW** | CP+OS | The closing-the-loop analytics spine. |

**Honest tally:** EXISTS ≈ 11 (Campaigns, Leads, AI Voice Calls, Run, Call Logs, Callbacks,
Analytics, Team/RBAC, Admin, multi-tenant, vendor-cost meter) · EXTEND ≈ 10 (Dashboard, Contacts,
WhatsApp, Integrations/webhooks, Experimentation/A-B, AI Quality/eval, Compliance/DND, Settings,
Postgres+RLS, Auth/Logto) · **NEW ≈ 41** (everything else, incl. 3D Studio, Document/Contract,
Inventory/Capacity, and the 5 Modes & Surfaces). The head-start is a real spine for the
**Engage + Grow + Sell** loop core; the **AI workforce, AI Manager, workflows, ads, creative,
booking, payments, support, KB/Brain** are the new build.

---

## 2. PRIORITIZED BUILD ROADMAP (foundational-first; each phase shippable + non-breaking)

**Sequencing law:** cross-cutting systems BEFORE the leaf modules that read/write through them. A
leaf built before its foundation rebuilds that foundation as glue (the failure mode). Every phase is
additive, behind a feature flag, non-breaking — `panel.famit.in` keeps earning throughout (the
strangler guarantee). **The foundation tier (Phases F0–F4) IS the in-flight `EXECUTION_PLAN.md`
sequence — inherited verbatim, not re-authored.**

### FOUNDATION TIER — inherited from EXECUTION_PLAN (P0→P4); the spine everything reads through

| Phase | What | Status | Unblocks | Spec |
|---|---|---|---|---|
| **F0** | Secrets-gate → git → CI; voice quick-wins (semantic turn-detector + barge-in) | **DONE** (infra/git) + voice in-flight | safe iteration; human-voice priority #1 | `p0-foundation.md`, `voice-quickwins.md` |
| **F1** | **Postgres + RLS keystone** (`store.py`, dual-mirror, shadow_diff==0, RLS proof) | **IN-FLIGHT** (U1) | wallet, RAG/KB, Hatchet cutovers, auth-JIT — and EVERY new module's data | `p1-postgres.md` |
| **F2** | **Dynamic voice context + pgvector RAG** = the **Business Brain + Knowledge Base** substrate | gated on F1 U2 | every AI worker's shared context | `dynamic-context-rag.md`, `platform-business-brain.md`, `platform-knowledge-rag.md` |
| **F3** | **Hatchet spine + eval harness** (durable runs/retries; AI Quality base) | engine startable; cutovers gate on F1 | every async/scheduled/multi-step workflow | `orchestration-hatchet.md`, `eval-harness.md` |
| **F4** | **Auth (Logto) + Action Firewall (PIN/OTP) + Audit Ledger + Credit Wallet** | gated on F1 | the SAFETY MODEL every AI action passes through + money custody | `auth-logto.md`, `credit-ledger-firewall.md` |

> Nothing in the product tier below ships its AI-acting parts before F4's firewall+audit, or its
> data before F1, or its shared context before F2, or its async work before F3. That is the whole
> point of foundational-first.

### PRODUCT TIER — the 54-module rollout (expansion of OCEAN Phases 5–9), each gated on the tier above

| Phase | Theme | Ships (modules) | Hard prereq | Why here |
|---|---|---|---|---|
| **P5** | **Frontend parity + 8-section IA + world-best UI** | The §7 sidebar regroup (non-breaking); surface every EXISTS/EXTEND module; premium UI pass (branch already staged) | F0 | Make what's already built legible + grouped before adding leaves. Pure frontend; zero backend risk. |
| **P6** | **AI Workforce runtime + Business Brain UI + Lifecycle Triggers** | Business Brain (first-class), Knowledge Base UI, AI Workforce registry/executor, Lifecycle Trigger Engine, AI Task Manager | F1,F2,F3,F4 | The runtime ALL workers share — built once, before any worker-driven leaf. |
| **P7** | **AI Manager (voice command center) + WhatsApp full + Support + Inbox** | AI Manager, WhatsApp Automation (flip live), Customer Support, Omnichannel Inbox, Conversation Intelligence | P6 + Meta creds | The operator's command layer + the conversational workforce, on the runtime. |
| **P8** | **Revenue engine: CRM + Pipeline + Booking + Payments + Wallet UI + Attribution** | CRM, Sales Pipeline, Booking/Appointments, Payments/Collections, Billing/Wallet UI, Revenue Attribution, Segmentation, Offer/Referral/Loyalty | F4 + Razorpay/Stripe creds | Close the book/pay/repeat half of the loop with money flowing through the wallet+firewall. |
| **P9** | **Autonomous Ads + Creative Studio + Funnels + Landing + Forms** | Ad Automation (spend-capped), Creative Studio, 3D Studio (ads/video ENGINE = the one new service), Funnels, Website/Landing, Form Builder, Research | F4 (budget/firewall) + ad-account OAuth | The acquisition half of the loop; the GPU render engine is the named future service. |
| **P10** | **Workflow Automation Studio + Marketplace + Industry Packs + advanced Intelligence** | Workflow Builder (visual), Template Library/Marketplace, Industry Packs, Business Digital Twin, Experimentation Lab (multivariate), AI Quality Review UI, Survey/Feedback | P6,P7,P8,P9 | The visual orchestration + vertical packaging that compose ALL the now-built modules. |
| **P11** | **Modes & surfaces** | Agency/Multi-Client Mode, White-Label Mode, Public Customer Portal, Mobile App, Marketplace/App-Store, Proposal/Document automation, Inventory/Capacity | the relevant leaves | Wrappers/surfaces over a complete platform; last because they multiply an already-working core. |

### THE FIRST 5 BUILD PHASES (what to do, in order)

1. **F0 — Foundation + secrets-gate + voice quick-wins.** *(largely DONE; finish voice.)* Git/CI/
   secrets-gate is in; finish the semantic turn-detector + adaptive barge-in behind flags (priority
   #1 human-voice). Non-breaking; live site untouched.
2. **F1 — Complete the Postgres + RLS keystone.** *(in-flight — the dominant unblocker.)* Drive
   `store.py` / dual-mirror / `shadow_diff==0` / RLS proof across the remaining stores. Unblocks the
   wallet, RAG/KB, Hatchet cutovers, auth-JIT — and the data layer of *every* new module.
3. **F2 — Dynamic voice context + pgvector RAG = Business Brain + Knowledge Base substrate.** The
   shared context every AI worker will read. Gated on F1 U2 (pgvector + RLS).
4. **F3 — Hatchet orchestration spine + eval/replay harness.** Durable runs/retries/crons (the
   backbone of every workflow, lifecycle trigger, booking, dunning) + the AI-quality eval base.
   Engine deploy is parallel-startable now; write-path cutovers rejoin after F1.
5. **F4 — Auth (Logto) + Action Firewall (PIN/OTP) + immutable Audit Ledger + Credit Wallet.** The
   safety model every AI action passes through, plus money custody (the build-don't-compose ACID
   wallet, schema-gated on F1). After this, AI-acting leaf modules are safe to build.

*(Then the product tier P5→P11 layers the 54 modules on top, each reusing this foundation.)*

### ⭐ THE SINGLE RECOMMENDED NEXT PHASE (right after the Postgres keystone)

> **F2 — pgvector RAG + Business Brain + Knowledge Base substrate.**

**Why F2 and nothing else next:** on the settled sequential spine (`EXECUTION_PLAN.md §2`:
`P1 U3-U9 → RAG-3 → …`), F2 is the very next mainline step. It is the **highest-leverage** thing
buildable: it is the **shared context every AI worker reads** — the Telecaller, WhatsApp salesperson,
Support agent, Campaign strategist all ground on it — so it must exist before any worker-driven leaf.
It needs **zero founder credentials** (LLM/embedding keys are platform-side, already held). And it is
**partly de-coupled from the keystone finishing**: it gates only on **F1 U2** (which provisions
`CREATE EXTENSION vector` + RLS scaffolding), so the embedder/ingestion work can begin *before* the
full `store.py` cutover lands — F2 is the natural place to flow the moment U2 is green.

**Concretely the next unit of work:** stand up `dynamic-context-rag.md` (embedder → `kb_chunks`
corpus → ANN retrieval with per-scope budget), then the `platform-business-brain.md` store (the
structured business config, snapshotted into prompts) and `platform-knowledge-rag.md` (the
voice-RAG corpus becomes a scoped subset of the one KB). **Then** F3 (Hatchet spine — the backbone of
every workflow/lifecycle/booking/dunning) → **then** F4 (Auth + Action Firewall + Audit + Wallet — the
safety model + money custody). After F4, AI-acting leaf modules are safe to build (P5 frontend parity
can run in parallel the whole time — it has no backend dependency).

---

## 2a. CREDENTIAL / ACCOUNT BLOCKERS (what gates which phase — and what to start NOW)

**The load-bearing fact:** the **entire foundation tier (F0→F4) AND frontend parity (P5) need ZERO
founder credentials.** Everything they touch — Postgres, RAG/KB, Hatchet, Logto (self-hosted),
firewall, wallet, the IA regroup, the premium UI — uses platform-side keys already held (Anthropic,
Groq, Sarvam, ElevenLabs, Vobiz) or self-hosted infra. **Founder credentials gate only the
product-tier leaves (P7–P9).** So nothing below blocks the next ~5 phases of work.

**But two have real calendar lead-time — START THESE NOW, in parallel, even though they ship in P9:**
- **Google Ads developer-token approval** (Basic→Standard access review) — multi-day-to-weeks.
- **Meta Advanced-Access app review + Business Verification** (`ads_management` + 2026 ≥500-call
  rule) — multi-day-to-weeks. (`automation-ads.md §R1`.)

| Blocker (provider class) | Gates phase | What the founder must obtain | Lead-time |
|---|---|---|---|
| **WhatsApp (Meta BSP / Cloud API)** — phone-number-id + permanent token + verified business | **P7** (flip WhatsApp live, Support, Inbox) | Meta WABA + number + system-user token | days (verification) |
| **Payments — Razorpay** (primary, INR) **/ Stripe** (2nd) — key-id + secret + webhook secret | **P8** (Payments/Collections, Wallet top-up) | Razorpay account + KYC; Stripe optional | days (KYC) |
| **Calendar — Google Calendar** OAuth client (id+secret) | **P8** (Booking/Appointments/Site-Visits) | Google Cloud project + OAuth consent | hours–days |
| **Ads — Meta Marketing API** — app id/secret, **System-User token**, Ad-Account id, **Page id, Pixel + CAPI token**, payment method on the ad account | **P9** (Ad Automation) | Meta App + Advanced Access + Business Verification; **billing on the ad account** | **weeks — START NOW** |
| **Ads — Google Ads API** — **developer token**, OAuth client + refresh token, customer id, billing on the account | **P9** (Ad Automation) | Google Ads account + dev-token approval; **billing on the account** | **weeks — START NOW** |
| **Creative gen — image** (e.g. fal/Replicate/Recraft/Ideogram-class) | **P9** (Creative Studio image) | one managed image-gen API key | minutes |
| **Creative gen — video** (e.g. Runway/Luma/Kling/Veo-class via fal/Replicate) | **P9** (Creative/Video Studio) | one managed video-gen API key | minutes |
| **Creative gen — 3D** (Meshy default / Tripo-class) | **P9 / 3D Studio** | one managed 3D API key (Meshy commercial tier) | minutes |
| **Email / SMS** (Listmonk SMTP / an SMS provider) | **P8–P10** (lifecycle, marketing) | SMTP creds / SMS provider key | hours |
| **Shopify / other store connectors** (OAuth) | **P10** (Integrations) | per-merchant OAuth connect (self-serve) | minutes |

**Platform-infra credentials (founder-side but NOT product blockers; some already provisioned):**
- **Cloudflare re-scoped API token** — PENDING per `fortress/HANDOVER_REPORT.md` (frontend not yet
  Cloudflare-fronted). One-time infra task.
- **DigitalOcean Spaces / R2** (asset + KB-document storage), **Logto** (self-hosted OIDC — no external
  account), **LLM/voice keys** (Anthropic, Groq, Sarvam, ElevenLabs, Vobiz — held; rotated post-FORTRESS).

> **Action for the founder this week:** kick off the **Meta Advanced-Access app review +
> Business Verification** and the **Google Ads developer-token** request — they are the only
> long-lead items, and the ads modules (P9) cannot ship live without them. Everything else is
> paste-a-key-when-you-get-there and does not stall the build.

---

## 3. CROSS-CUTTING GUARANTEES (every phase, every module)

Inherited from `EXECUTION_PLAN.md` §4 — restated so the product tier honors them too:

1. **Flag-off-is-byte-identical** — every new module/capability ships behind a flag defaulting OFF;
   flag off = provably current behavior + the rollback path.
2. **Non-breaking IA** — the §7 sidebar regroup absorbs every live route; no page 404s.
3. **Twice-enforced tenant isolation** — token `tenant_id` + Postgres RLS on every new table.
4. **Through the firewall** — any AI-acting module routes spend/bulk/destructive actions through the
   Action Firewall + audit ledger; the workflow engine refuses to compile a violation.
5. **Crash-safe per-unit** — backup → small change → test → deploy → regression-gate-200 → build_log
   → commit → flip DONE. A kill costs ≤1 unit.
6. **Reuse the head-start** — EXISTS modules are reused, EXTEND modules widened in place; no rebuild.
7. **Scale by replicate + shard, never decompose** — the one named future service is the ads/video
   render engine (P9); everything else stays in the modular monolith + the three existing planes.

---

*Module map + foundational-first roadmap, now refined with the **completed foundational designs**
(all 12 spine specs under `design/` are authored and adversarially red-teamed: `p0-foundation`,
`voice-quickwins`, `p1-postgres`, `auth-logto`, `credit-ledger-firewall`, `orchestration-hatchet`,
`eval-harness`, `dynamic-context-rag`, `platform-business-brain`, `platform-knowledge-rag`,
`platform-ai-workforce`, `platform-ai-manager`, `platform-workflow-studio`, `platform-integrations-hub`,
`platform-crm-core`). Inherits the in-flight P0→P4 technical foundation as the foundation tier; layers
the 54-module product (OCEAN Phases 5–9) on top. Architecture and build sequence are settled inputs
(`ARCHITECTURE_DECISION.md`, `EXECUTION_PLAN.md`); product source of truth is `MASTER_VISION.md`. This
file sequences and maps; it does not re-design.*
