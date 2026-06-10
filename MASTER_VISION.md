# MASTER VISION — Famit / Axcrio: the Autonomous Business OS / AI Revenue Workforce

> **What this file is:** the canonical product vision. It names the whole platform — the core
> revenue loop, all ~54 modules/systems, the AI workforce, the AI Manager command layer, the
> Workflow Automation Studio, and the platform-wide safety model — organized so every later doc
> (module map, roadmap, specs) references *this* as the single source of product truth.
>
> **What this file is NOT:** an architecture re-design. The architecture is **settled** —
> `ARCHITECTURE_DECISION.md` (coarse planes + modular monolith, strangle-and-evolve) and
> `EXECUTION_PLAN.md` (the unit-level build sequence) are the binding inputs. This vision layers the
> full product *on top of* that settled foundation. It does not re-open any boundary.
>
> **Grounding:** the OCEAN master plan, `ARCHITECTURE_DECISION.md`, `EXECUTION_PLAN.md`, the live
> `/api` contract (HANDOFF), and the build_log of what already ships. The companion
> `MASTER_PLATFORM_ROADMAP.md` turns this vision into the module map + sequenced build.

---

## 0. THE ONE-LINE NORTH STAR

**Famit/Axcrio is an Autonomous Business OS: a vendor enters their business, products, pricing,
offers, leads and goals once — and an AI WORKFORCE then runs growth, sales, marketing, creative,
ads, follow-up, booking, payments, support and analytics on its own**, replacing the manual
telecaller / salesperson / designer / copywriter / ad-manager / support / CRM / booking / analytics
teams a business would otherwise hire. The operator steers by exception (and by *voice*, via the AI
Manager), not by doing the work.

It is **business-vertical-agnostic**: real-estate, salon, clinic, coaching, D2C, ecommerce, cafe,
agency — the same engine, configured by the **Business Brain** and shipped per-vertical by **Industry
Packs**.

---

## 1. THE CORE LOOP (the moat — the closed revenue loop)

Every module exists to serve, or to be orchestrated inside, this single loop. The differentiator is
that Famit **owns the whole loop end-to-end** (so it can bill on *outcomes*, carry *one cross-channel
memory per lead*, and let the AI workforce optimize the loop itself):

```
  Business data (Brain) ─► Campaign ─► Creative ─► Ads / WhatsApp / Landing page
        ▲                                                        │
        │                                                        ▼
   Analytics ◄─ Optimize ◄─ Review/Referral ◄─ Support      Lead capture
        ▲                          ▲                              │
        │                          │                              ▼
   Revenue attribution     Book / Pay  ◄── Qualify ◄── WhatsApp follow-up ◄── AI VOICE CALL
                                                                                   ▲
                                                          (unified per-lead memory across ALL hops)
```

**Loop in words:** business data → campaign → creative → ads/WhatsApp/landing → lead capture →
AI voice call → WhatsApp follow-up → qualify → book/pay → support → review/referral → analytics →
optimize → repeat. A **Lifecycle Trigger Engine** re-enters the loop proactively on each business's
service cycle (re-engage, upsell, win-back). **Human handover is exception-only**, always with an AI
summary. **Revenue Attribution** closes the accounting on every loop.

---

## 2. THE AI WORKFORCE (the cross-cutting layer that runs the loop)

A roster of **AI worker roles**, each a configured agent that reads the **Business Brain + Knowledge
Base** and acts through the platform's modules under the safety model. They are not 54 separate apps;
they are *operators* of the modules.

| AI worker role | Replaces | Primary modules it drives |
|---|---|---|
| **AI Telecaller** | telecaller / SDR | AI Voice Calls, CRM, Leads |
| **WhatsApp Salesperson** | chat sales rep | WhatsApp Automation, CRM |
| **Support Agent** | support team | Customer Support, Knowledge Base, Inbox |
| **Campaign Strategist** | marketing manager | Campaigns, Funnels, Segmentation |
| **Creative Producer** | designer / copywriter / video | Creative Studio, 3D Studio |
| **Ad Operator** | performance-marketing / ad-ops | Ad Automation, Funnels |
| **CRM Manager** | CRM admin / RevOps | CRM, Sales Pipeline, Contacts |
| **Booking Assistant** | front-desk / scheduler | Booking/Appointments |
| **Billing Manager** | finance / collections | Payments/Collections, Wallet |
| **Analytics Manager** | data analyst | Analytics, Attribution, Conversation Intelligence |
| **Ops Manager** | operations lead | Workflow Builder, Task Manager, Integrations |

**Shared substrate every worker reads:** the **Business Brain** (business/products/pricing/offers/
goals/voice/persona) + the **Knowledge Base** (docs/FAQ/policy → RAG). **Orchestrated by:** the AI
Manager + the Workflow Automation Studio. **Bounded by:** the safety model (§6). **Handover:** any
worker can escalate to a human with a full AI summary; humans never start cold.

---

## 3. THE AI MANAGER — voice-first command center

The operator's primary interface. The vendor registers phone numbers, **calls the AI Manager**, and
gives natural commands ("call all hot leads", "launch a campaign for my 2BHK", "increase budget on
the best ad", "what's today's revenue?"). The AI Manager:

1. **Understands intent** (NLU over the Business Brain context).
2. **Verifies permission** (RBAC — the caller's role may not allow the action).
3. **Gates risky actions** behind a preset **4-digit PIN / OTP** — any action that spends money,
   sends in bulk, launches/pauses ads, mass-calls, or touches price/refund/export/delete.
4. **Delegates** the work to the appropriate AI workforce roles (it does not do the work itself — it
   *orchestrates*).
5. **Writes every decision** to the immutable Audit Ledger with its reason.

It is **omnichannel** (voice / WhatsApp / chat) and controls **every module**, reducing dashboard
dependency. It is the human-facing front of the AI workforce + the Workflow engine + the safety model.

---

## 4. THE WORKFLOW AUTOMATION STUDIO (visual orchestration over everything)

An **n8n / React-Flow-style visual builder** that wires together ALL internal features + AI agents
into automations. It **does not execute spend or voice itself** — it emits events into the Hatchet
orchestration spine, which runs the durable work under the same safety gates.

**Node types:** `Trigger` · `Condition` · `AI-Agent` · `Action` · **`BUDGET`** (spend caps) ·
**`APPROVAL`** (human / PIN gate) · `Delay/Wait` · `Data/Memory` · `Integration` · `Error-Handling`.

**Capabilities:** multi-agent workflows; per-industry templates; a template **marketplace**;
per-workflow analytics; **versioning**; per-workflow permissions.

**Hard safety rules baked into the engine (non-negotiable):** no bulk send / no spend / no refund /
no DND violation / no out-of-hours calling / no data export — *without* an APPROVAL node + a BUDGET
node + an audit entry. The engine refuses to compile a workflow that violates these.

---

## 5. THE FULL MODULE INVENTORY (~54 modules / systems)

Grouped by the sidebar IA (§7). Each module's EXISTS/EXTEND/NEW status + plane + dependencies live in
`MASTER_PLATFORM_ROADMAP.md`; here is the canonical *list* and what each is.

### 5.1 The 34 sidebar modules
1. **Dashboard** — the operator's home: KPIs, AI workforce activity, today's revenue, alerts.
2. **Business Brain** — the canonical business/products/pricing/offers/goals/persona store every AI worker reads.
3. **AI Manager** — voice-first command center (§3).
4. **CRM** — accounts/contacts/deals/timeline, the system of record for relationships.
5. **Leads** — lead capture, scoring, hot-list, source attribution.
6. **Contacts** — people/companies directory, dedupe, enrichment.
7. **Campaigns** — multi-channel campaign definition + orchestration.
8. **AI Voice Calls** — the LiveKit telecaller: dial, converse, transcribe, summarize, classify.
9. **WhatsApp Automation** — outbound follow-up + inbound multi-turn AI conversation.
10. **Customer Support** — AI support agent + ticketing over the Knowledge Base.
11. **Creative Studio** — AI ad-copy / image / video / landing creative generation.
12. **Ad Automation** — Meta/Google ad create/run/optimize under spend caps.
13. **Website / Landing Pages** — hosted landing pages + lead-capture forms.
14. **Funnels** — multi-step conversion funnels across channels.
15. **Workflow Builder** — the Workflow Automation Studio (§4).
16. **Booking / Appointments / Site-Visits** — calendar + booking + reminders.
17. **Sales Pipeline** — stages, deal movement, forecast.
18. **Payments / Collections** — invoices, payment links, dunning.
19. **Billing / Credits / Wallet** — the customer-facing credit wallet + plan + ledger (platform billing).
20. **Analytics / Reports** — cross-module reporting + funnel + cohort.
21. **Business Digital Twin** — a simulatable model of the business for what-if planning.
22. **Experimentation Lab** — A/B / multivariate tests across calls, copy, offers, ads.
23. **Research / Competitor Intelligence** — market + competitor + keyword research agent.
24. **3D Product / Property Studio** — 3D/360 product & property visualization.
25. **Reviews / Reputation** — review solicitation + response + reputation monitoring.
26. **Assets / Documents** — media + document library.
27. **Knowledge Base** — the RAG corpus the workforce answers from.
28. **Integrations** — outbound webhooks + inbound connectors + third-party APIs.
29. **Compliance / DND / Consent** — suppression, consent, calling-window, DLT/TRAI, DPDP.
30. **Team / Roles / Permissions** — users, RBAC, org membership.
31. **AI Quality Review** — eval/replay harness + human review of AI conversations.
32. **Admin / Super-Admin** — tenant management, platform ops, vendor provisioning.
33. **Settings** — per-tenant configuration, branding, integrations keys.
34. **Industry Packs** — vertical templates (prompts, flows, KB, creatives) per business type.

### 5.2 Cross-cutting systems (the workforce + the spine)
35. **AI Workforce runtime** — the agent-role registry + executor (§2).
36. **Lifecycle Trigger Engine** — proactive re-engagement by each business's service cycle.
37. **Human Handover** — exception-only escalation with AI summary.
38. **Revenue Attribution** — ties revenue back to campaign/creative/call/channel.
39. **Conversation Intelligence** — mines calls/chats for signals, objections, sentiment.
40. **Notifications / Omnichannel Inbox** — one inbox across voice/WA/email/web + alerts.
41. **AI Task Manager** — the workforce's task queue + the operator's approvals queue.

### 5.3 The +20 additional modules
42. **Form / Lead-Capture Builder** · 43. **Survey / Feedback Engine** · 44. **Omnichannel Inbox**
(unified with #40) · 45. **AI Task Manager** (unified with #41) · 46. **Proposal / Quotation
Generator** · 47. **Document / Contract Automation** · 48. **Inventory / Capacity Management** ·
49. **Offer / Discount Engine** · 50. **Referral Engine** · 51. **Loyalty / Membership** ·
52. **Customer Segmentation** · 53. **Revenue Attribution Ledger** (the durable store behind #38) ·
54. **Conversation Intelligence** (unified with #39) · 55. **AI Training / Improvement Center**
(unified with AI Quality Review #31) · 56. **Template Library** · 57. **Public Customer Portal** ·
58. **Agency / Multi-Client Mode** · 59. **White-Label Mode** · 60. **Marketplace / App-Store** ·
61. **Mobile App**.

> *Numbering exceeds 54 because several "+20" items are the same system as a cross-cutting one
> (Omnichannel Inbox, AI Task Manager, Conversation Intelligence, Revenue Attribution, AI
> Training); they are listed once in the module map and cross-referenced. The deduped count of
> distinct buildable systems is **~54**.*

---

## 6. THE SAFETY MODEL (platform-level, non-negotiable)

Every AI action — whether triggered by the AI Manager, a Workflow, or a worker on its own — passes
through the **same** gates. This is a *foundational* system (built before the leaf modules that
depend on it), not a per-module feature.

1. **RBAC / least-privilege** — every actor (human or AI worker) has a role; actions are authorized
   at the API boundary. (Already live: admin/manager/agent.)
2. **PIN / OTP step-up** for risky AI-Manager / workflow actions: spend, bulk messaging,
   launch/pause ads, mass calls, price/refund/export/delete.
3. **Approval + Budget gates** — the APPROVAL and BUDGET workflow nodes; the Action Firewall enforces
   them server-side so a workflow cannot route around them.
4. **Immutable Audit Ledger** — every AI decision recorded with its *reason*, append-only, tamper-evident.
5. **Secrets management** — provider keys in a secrets store, never in code/repo (gitleaks-gated).
6. **DND / consent / calling-window compliance** — suppression list, consent capture, TRAI calling
   window, DPDP — enforced in the dial path and the workflow engine, not optional.
7. **Twice-enforced tenant isolation** — `tenant_id` from the token at the API boundary AND Postgres
   Row-Level Security in the database. A leaked token still cannot read another tenant's rows.

---

## 7. THE SIDEBAR INFORMATION ARCHITECTURE (8 collapsible sections)

The 34 sidebar modules are grouped into **8 collapsible sections** using the **exact pattern already
shipped for Billing** (`contstants/navigation.tsx`: a parent with no `href` + a `list` of child
routes, rendered by `Sidebar/Dropdown` / `AnimateHeight`). This is non-breaking: every currently-live
route (`/`, `/campaigns`, `/leads`, `/run`, `/calls`, `/suppression`, `/callbacks`, `/analytics`,
`/whatsapp`, `/webhooks`, `/billing/*`, `/vendors`) is absorbed into a section — the redesign is a
**regroup, not a rebuild**; no live page is orphaned.

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

**Modes that wrap the whole sidebar (not sections):** Agency/Multi-Client Mode, White-Label Mode,
Public Customer Portal, Marketplace/App-Store, Mobile App, 3D Studio — these are *surfaces/modes*,
reachable contextually, not eighth-of-the-list nav rows.

> The 8-section grouping sits at the low end of the "8-10" target so each section stays scannable
> (sub-modules expand inside the collapsible parent); A–H map cleanly to the core loop's phases
> (Command → Grow → Sell → Engage → Automate → Money → Intelligence → Foundation).

---

## 8. HOW THIS RIDES THE SETTLED ARCHITECTURE (no redesign)

This vision changes **zero** architecture. Mapping the big product concepts onto the already-decided
planes and the already-sketched phases (so nothing here re-opens a boundary):

- **AI Manager** = the planned **AI copilot** (OCEAN Tier-0 / Phase 7), now voice-first — runs in the
  control-plane API, dispatches to the voice plane + Hatchet, gated by the Action Firewall + audit.
- **Workflow Builder** = the planned **Phase 9 workflow engine** — a graph that emits into Hatchet;
  never executes spend/voice itself.
- **Ad Automation** = the planned **Phase 8 autonomous ads** — and the GPU/render side is the *one
  named future service* (the ads/video engine in `ARCHITECTURE_DECISION.md`).
- **Business Brain + Knowledge Base** = the dynamic-context + pgvector RAG substrate (Phase 2) plus a
  structured business-config store — the shared context every worker reads.
- **AI Workforce** parallelism comes from **code modularity (per-domain routers/schemas), not network
  separation** — exactly the decision's thesis. Workers are roles in the modular monolith + the voice
  plane, not microservices.
- **Safety model** = Logto auth + Action Firewall + immutable audit ledger + wallet (Phase 4) +
  twice-enforced RLS (Phase 1) — all *foundational* phases that ship before the leaf modules.

The roadmap (`MASTER_PLATFORM_ROADMAP.md`) sequences this: the in-flight technical foundation
(P0→P4) **is** the foundation tier; the 54-module rollout is the expansion of Phases 5–9.

---

*Canonical product vision. Architecture is settled (`ARCHITECTURE_DECISION.md`); build sequence is
settled (`EXECUTION_PLAN.md`). This file is the product source of truth those docs serve. Companion:
`MASTER_PLATFORM_ROADMAP.md` (module map + prioritized roadmap).*
