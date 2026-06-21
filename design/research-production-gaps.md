# PRODUCTION-READINESS + SELLABILITY AUDIT — the complete connected lifecycle

> **Status:** READ-ONLY audit + web research. No code, no deploy, no git, no box changes.
> Written 2026-06-12. Companion to the inbound voice plans (`INBOUND-PIPELINE-MASTER-PLAN.md`
> + `-V2.md`, `plan-feature-inventory.md`) and the infra spec (`obs-sec-cost.md`,
> `docs/architecture/04-deployment.md`). **Those plans cover the inbound VOICE BRAIN deeply and
> well — this doc deliberately does NOT repeat them.** It audits the *other* axis: what makes the
> WHOLE pipeline a **production-grade, sellable product a vendor pays for and trusts** —
> reliability/observability, self-serve onboarding, panel-backend completeness, billing
> productization, security/compliance for sale, scale, and "LLM everywhere".
>
> **The pipeline being judged (one connected lifecycle):** outbound AI call → per-person
> memory/context saved → WhatsApp follow-up (template → LLM conversation) → inbound call-back with
> FULL history (call + WhatsApp) → when hot, warm-transfer to a human + WhatsApp the hot lead to the
> team. The whole loop must be reliable, observable, self-serviceable, metered, compliant, and
> infused with LLM at every surface.
>
> ## 🟥 #1 RULE (unchanged, absolute) — NEVER BREAK THE OUTBOUND EARNER
> Every fix below is **ADDITIVE + ISOLATED**, behind a flag, reversible, regression-gated. No step
> edits `agent.py`, the outbound trunks `ST_fmtVmNJmpzKa`/`ST_LH8ighJJtHSi`, the dispatch, or
> `build_system_prompt`. The earner was just **restored after an infra mistake** — that incident is
> the spine of the RELIABILITY section below: the lesson is *observability + egress-lock + per-unit
> regression gate*, and it must become a permanent guarantee, not a one-off recovery.

---

## 0. HEADLINE VERDICT (read this first)

The system is **~70% of a sellable product on the engine side and ~40% on the trust/operability
side.** The voice/inbound brain, billing meter, control layer, and 18+ backend modules are
genuinely strong (see the inbound plans). **The gap to "sellable" is NOT more features — it is the
unglamorous product skin that makes a stranger trust it with their phone line and their money:**

1. **It can go silent and nobody is paged.** Observability infra (Prometheus/Grafana/Sentry/Langfuse)
   is *designed and keys exist* but **NOT deployed**; there is no alerting, no on-call, no status
   page, no error budget. The recent infra incident proved the blast radius; the monitoring that
   would have caught it is still on paper.
2. **A new vendor cannot self-serve.** There is **no signup, no guided onboarding, no
   connect-your-WhatsApp/number wizard, no "go live in minutes" path.** Every tenant today is
   created by an admin by hand. This single gap caps the business at "founder-onboards-each-customer".
3. **Many panel pages look built but have no working backend.** Verified frontend-only / dormant:
   **Funnels, Ads, Workflows, Booking, Forms, Support, Payments, Creative (partial), AI-Manager (7
   pages, backend un-mounted), Settings→Handoff (absent).** The UI is premium; the wires are missing.
4. **Billing isn't productized for sale.** The cost METER is real (per-vendor COGS), but there is
   **no customer-facing top-up / payment-gateway / invoice / plan-purchase / credit-wallet-on-the-
   panel** flow — pricing tiers exist on slides, not in software.
5. **Security/compliance is strong on isolation, thin on the paperwork a buyer asks for.** RLS +
   control-layer + audit are real; **SOC2-style posture, DPDP delete-my-data, DLT/TRAI enforcement,
   recording consent + retention, and a public trust/status page are missing.**
6. **LLM is in the voice call but absent from the rest of the product.** Template writing, campaign
   setup, banner copy, lead scoring rationale, reply drafting, call summaries-in-panel, a vendor
   copilot — all are places a 2026 buyer expects AI and finds none.

The good news mirrors the inbound audit: **most fixes are WIRING + a thin product skin over engines
that already exist**, plus standing up monitoring/onboarding that is pure additive infra on the
panel box (never the earner).

---

## 1. RELIABILITY / OBSERVABILITY — "the never-silent guarantee" (SEVERITY: CRITICAL)

> Web-confirmed production principle (2026): *"If a critical component fails, the agent must deliver a
> fallback prompt within 1.5s and either transfer, offer a callback, or end cleanly — silence is not
> an option,"* and *"if you rely on customer complaints to find issues, your observability isn't fast
> enough."* (Altersquare, Galileo, FutureAGI — see Sources.)

| # | Gap | State on this system | Severity | Fix (additive, panel-box-first) |
|---|---|---|---|---|
| R1 | **No deployed monitoring stack** | `obs.py` exposes `/metrics` in-proc (real); Prometheus+Grafana are **fully designed in `obs-sec-cost.md` but NOT stood up**. Sentry (3 DSNs) + Langfuse keys exist in `.env.local`, **not wired**. | 🟥 CRIT | Execute `obs-sec-cost.md` O1/O2 **on the panel box** (`10.122.0.2`, scrape backend over VPC — zero firewall change, zero load on the voice box). Add Sentry to caller/agent/panel; Langfuse for LLM traces. |
| R2 | **No alerting / on-call** | Alert RULES are written (`alert.rules.yml`: TTS p95, 5xx, call-error-rate, scrape-down, cost-spike) but no Alertmanager → no Slack/PagerDuty. `SLACK_WEBHOOK_URL`/`DISCORD_WEBHOOK_URL` exist unused. | 🟥 CRIT | Wire Alertmanager → the existing Slack webhook. **The single highest-ROI item:** "famit-agent down" or "scrape down" must page within minutes — exactly what the infra incident lacked. |
| R3 | **The "never-silent" guarantee isn't systemic** | P0 silence bug (Sarvam `max_retry=0`) is the inbound headline; outbound has the apology guard but **no liveness/readiness probe, no auto-restart-on-stuck, no synthetic canary call.** | 🟥 CRIT | systemd `Restart=always` + a **synthetic canary** (a scheduled real test call every N min that asserts greet→hear→reply, alerts on fail) = automated, continuous proof the earner is alive. This *operationalizes* the manual regression gate. |
| R4 | **No error budget / SLOs / uptime tracking** | No SLO doc, no error budget, no historical uptime. Buyers ask "what's your uptime?". | 🟧 HIGH | Define SLOs (call-answer success %, p95 turn latency ≤1.6s, API 5xx <2%, WhatsApp delivery %). Track in Grafana. Publish a 30/90-day uptime number. |
| R5 | **No public status page** | None. A down product with no status page = support storm + lost trust. | 🟧 HIGH | A simple status page (Statuspage/Upptime/Better Stack) driven off the canary + scrape health. Cheap, high trust signal. |
| R6 | **Retry/backoff inconsistent across the loop** | Voice STT retry is the known P0; WhatsApp send, webhook delivery, vendor-cost sync, callback dispatch each have their own ad-hoc retry. | 🟧 HIGH | Standardize exponential-backoff-with-jitter + a dead-letter view per async leg (WA, webhook, dial, sync). Surface failures in the panel, not just logs. |
| R7 | **Incident runbook + backups not codified** | The infra recovery was heroic but ad-hoc; no documented runbook, no tested DB/PITR restore, no config backup automation beyond dated `.bak`. | 🟧 HIGH | Write a runbook (the FORTRESS docs are the seed); automate Postgres backups + test a restore; snapshot `var/` + `.env`. A buyer's #1 fear is "what if it breaks". |
| R8 | **Single-box failure domain** | The backend box runs API + voice + DB + LiveKit + SIP — one box down = total outage (voice is out-of-band of CF so a panel outage doesn't stop calls, but a backend-box outage stops everything). | 🟨 MED | Document the failure domain honestly for sales; plan read-replica/DB-offload + a warm-standby voice worker as the scale story (see §5). Not a day-1 blocker, but name it. |

**The incident lesson, made permanent:** egress-lock (done on the panel box) + deployed monitoring
(R1) + paging (R2) + canary (R3) + tested backups (R7) together convert "we got lucky and recovered"
into "we detect and contain in minutes." This is the spine of the trust story.

---

## 2. ONBOARDING — a new vendor self-serves and goes live in minutes (SEVERITY: CRITICAL for sale)

This is the **single biggest blocker to selling without the founder in the loop.** Today every
tenant is admin-created by hand (`POST /tenants`); there is **no signup page, no onboarding wizard,
no self-service connect flows.**

| # | Gap | State | Severity | Fix |
|---|---|---|---|---|
| O1 | **No self-serve signup** | `/login` only; tenant creation is admin-only. | 🟥 CRIT | A signup → email-verify → tenant-provision flow (Logto is deployed on the hatchet box for exactly this but **DNS not live + not wired**; finish `auth.famit.in` + adopt it, or ship a thin signup over the existing tenant store as the stopgap). |
| O2 | **No guided onboarding wizard** | New tenant lands on an empty panel. | 🟥 CRIT | A 5-step "go live" wizard: (1) business profile (auto-fill the Business Brain via LLM from a website URL), (2) connect WhatsApp, (3) connect/claim a number, (4) upload knowledge (brochure/price → RAG corpus), (5) first campaign + test call. Progress checklist on the dashboard. |
| O3 | **WhatsApp connect is not self-serve** | Meta WA keys are single-tenant in `.env`; no per-vendor Embedded Signup / BSP onboarding; WA is dormant. | 🟥 CRIT | Per-vendor WhatsApp onboarding (Meta Embedded Signup or a BSP). Until then, a guided "give us your WABA details" form + status. **This unblocks the entire WhatsApp leg of the lifecycle for every vendor.** |
| O4 | **Number/DID provisioning is manual** | DIDs are procured via Vobiz by the founder; no per-vendor number claim; `var/inbound_dids.json` is a design. | 🟧 HIGH | A "get a number" flow (buy/assign from a pool) + the DID→tenant/campaign map UI. Multi-carrier keys exist (Vobiz/Plivo/Exotel/Jio/Airtel) — pick one self-serve provisioning path. |
| O5 | **No knowledge-upload UI (RAG corpus stays empty)** | `POST /brain/knowledge` exists; **no panel page calls it**; corpus = 0 rows, so RAG can never help a real vendor. | 🟧 HIGH | A drag-drop "upload your brochure/price-sheet/FAQ" page → `brain.add_knowledge` → `kb.ingest`. This is what makes the AI actually *know the vendor's business* — a headline sellable moment. |
| O6 | **No sandbox / test-drive before paying** | No demo mode, no test call to yourself, no sample campaign. | 🟧 HIGH | A "call yourself a test call" button + a seeded demo campaign so a prospect experiences the product in 60s. The single best conversion lever for a voice product. |
| O7 | **No in-product guidance / empty states / sample data** | Pages render empty with no next-step. | 🟨 MED | Empty-state CTAs, tooltips, a help drawer. Cheap, big activation lift. |

---

## 3. PANEL COMPLETENESS — "looks built but isn't wired" (SEVERITY: HIGH — credibility)

**Verified by reading the panel + its API clients (`lib/api.ts`, `ai-manager/_lib.ts`) and grepping
every `page.tsx`.** The UI is premium and consistent; the founder's instinct is **correct** — a
large fraction of pages are frontend-only shells that degrade to an honest "coming soon / not
configured" state. Classification:

**✅ FULLY WIRED (real backend, live):** Dashboard, Campaigns, Leads, Run-a-Campaign, Call Logs +
detail, Billing (overview/vendors/explorer/audit — real COGS meter), Suppression/DND, Callbacks,
Webhooks, Usage, Analytics (funnel), Super-Admin (vendors/flags/plans/usage/audit — control layer
LIVE), WhatsApp send/log (engine live, Meta creds gate actual delivery).

**🟡 PARTIAL — engine exists, panel reads a status and degrades to "coming soon":** Creative Studio
(AI-Asset service **IS live** at `/api/assets/*`; some sub-tabs dormant), Workflows (reads engine
status, shows "Engine coming soon" until wired), CRM (contact-360 engine exists; some tabs partial),
Support (grounded-or-escalate engine exists; page dormant).

**🟥 FRONTEND-ONLY / BACKEND UN-MOUNTED (the founder's real concern):**
| Page | Evidence | Severity |
|---|---|---|
| **Funnels** | `page.tsx:13` *"every read degrades to a premium coming soon path"*; 6× "Coming soon" badges; no engine. | 🟥 |
| **Ads** | `page.tsx:13-16` *"not configured / coming soon path is the PRIMARY state"*; approvals throw *"step-up — coming soon"*. | 🟥 |
| **AI-Manager (all 7 pages)** | `ai-manager/_lib.ts:203` every mutation throws *"the AI Manager backend is not configured"*; reads degrade to dormant — the `ai_manager` router is **not mounted in caller.py** (matches the inbound plan's "endpoints.py NOT mounted"). | 🟥 |
| **Booking** | `booking/page.tsx:13` dormant activation panel; engine (`booking/core.py`) exists + mounted but **voice/panel never call it**; calendar sync "coming soon". | 🟥 (engine ready) |
| **Forms / Forms[id]** | 23+11 "coming soon/placeholder" hits; builder shell, no working submit→lead pipe wired to panel. | 🟧 |
| **Payments** | 14 dormant hits; `payments/core.py` exists but **no gateway keys** (no Razorpay/Stripe in `.env`) → cannot transact. | 🟧 (blocker = keys) |
| **Settings → Human Handoff** | The handoff-list card (founder ask #1 storage) is **absent**; `/settings/page.tsx` has no `/brain`/handoff wiring. | 🟧 |

**Fix:** a panel-completeness sprint that, per page, either (a) wires it to its existing engine
(Booking, CRM tabs, Support, Workflows, AI-Manager router mount, Settings-handoff over `PUT /brain`),
or (b) **hides it behind the control-layer entitlement** so a prospect never sees a dead page (the
control layer already supports HIDE=404 — use it to gate un-shipped pages out of the nav per plan
instead of showing "coming soon"). **A buyer clicking a "Coming soon" tile during a demo is a trust
leak; either wire it or hide it.**

---

## 4. BILLING / CREDITS / USAGE METERING FOR SALE (SEVERITY: HIGH)

The **internal meter is excellent** (per-call per-vendor COGS, Vobiz CDR join, ACID wallet ledger
with proven no-double-spend, billing pages). **What's missing is the *commercial* layer a customer
self-serves.**

| # | Gap | State | Severity | Fix |
|---|---|---|---|---|
| B1 | **No customer top-up / payment gateway** | Wallet ledger exists; `setBilling` topup is **admin-only**; no Razorpay/Stripe keys; no checkout. | 🟥 CRIT | Wire Razorpay (India-first) → wallet credit. A vendor must be able to **add money themselves**. Without this, billing is a spreadsheet. |
| B2 | **No plan purchase / self-serve upgrade** | Plans exist in the control layer (`/admin/plans`) but are **admin-assigned**; no pricing page, no "choose Starter/Growth/Enterprise" checkout. | 🟥 CRIT | A pricing page + self-serve plan selection → assign plan + provision caps. The 3-tier model (₹9,999/₹24,999/custom from the sales research) lives on slides, not software. |
| B3 | **No invoices / receipts / GST** | None. Indian B2B buyers require GST invoices. | 🟧 HIGH | Auto-generate GST-compliant invoices + receipts per top-up/cycle. Table-stakes for selling to a business. |
| B4 | **Usage transparency thin for the customer** | `/usage` + `/billing/overview` show COGS; the customer wants "what did I spend, on what, am I about to run out". | 🟧 HIGH | A customer-facing usage+credits dashboard with **low-balance alerts** (don't let calls silently stop), spend-by-campaign, projected runway. |
| B5 | **Two balance systems confuse** | `billing.balance` (prepaid) vs `wallet_accounts` (prepaid_wallet) are **separate balances by plan** (noted in memory). | 🟨 MED | Unify or clearly delineate in UI; one "credits" number the customer trusts. |
| B6 | **No revenue/margin visibility for the founder** | COGS is metered but there's no founder P&L view (revenue − COGS per tenant). | 🟨 MED | A founder margin dashboard off the existing meter — know which tenants are profitable. |

---

## 5. SECURITY / COMPLIANCE FOR SALE (SEVERITY: HIGH — the buyer's checklist)

Isolation + control-plane are **genuinely strong** (FORCE-RLS, control layer LIVE + 18-probe tested,
immutable audit, egress-locked panel box, Cloudflare Full-Strict, legacy-password excluded from
`/admin/*`). **The gaps are the *paperwork and posture* a buyer's procurement asks for** — and the
India-specific regulatory enforcement that is configured-but-not-enforced.

| # | Gap | State | Severity | Fix |
|---|---|---|---|---|
| S1 | **No SOC2-style posture / trust page** | Strong controls, **no documented framework, no trust/security page, no DPA template.** | 🟧 HIGH | A trust page (encryption at rest/transit, RLS isolation, audit, RBAC, backups, sub-processors list) + a DPA template. 2026 Indian SaaS buyers expect this; tools (Sprinto/Vanta) automate later. |
| S2 | **DPDP delete-my-data missing** | RLS gives isolation; **no purpose-limit doc, no deletion-on-request path** for transcripts/recordings/CRM (personal data under DPDP). | 🟧 HIGH | One delete-my-data endpoint + a data-handling/retention policy. DPDP (India) governs what you DO with call data, distinct from TRAI's permission-to-call. |
| S3 | **DLT/TRAI configured but not enforced** | `TRAI_DLT_PRINCIPAL_ENTITY_ID`, `TRAI_DLT_HEADER` exist in `.env`; **not enforced in the dial path**; AI-disclosure is configurable, not mandatory. | 🟧 HIGH | Enforce DLT header/template + **mandatory natural AI-disclosure** at call start (TRAI synthetic-voice mandate). Correct 140-promo/160-service DID series. Sell as "compliant by default". |
| S4 | **Recording consent + retention absent** | Recorder is a `_NullRecorder` no-op; no Egress, no consent line, no 90-day Indian-region retention. | 🟧 HIGH | Inbound plan Phase 5 (Egress→DO Spaces) + a spoken consent line + 90-day Indian-region retention + PIN-span pause. Legal recording is a sellable feature, not just storage. |
| S5 | **No pen-test / vuln-scan cadence; BOLA proof not automated** | `obs-sec-cost.md` S3 designs a cross-tenant BOLA harness; not run on a schedule. | 🟨 MED | Run the BOLA/isolation harness in CI + a periodic external scan. Evidence beats claims. |
| S6 | **Secrets management half-done** | `config.py` supports Doppler/Infisical; **Vault keys exist in `.env` unused**; secrets still live in `.env` on the box. | 🟨 MED | Move to one secrets manager (Vault is half-provisioned). Reduces the blast radius the incident exposed. |
| S7 | **Per-vendor PIN / firewall step-up still single-box** | One box PIN; per-vendor PIN is a Phase-6 deliverable. | 🟨 MED | Per-tenant PINs + Argon2id (already in the inbound plan); needed before true multi-vendor command access. |

---

## 6. SCALE / MODULAR ARCHITECTURE (SEVERITY: MEDIUM — name it before it bites)

The architecture is a **clean modular monolith** (18+ flag-gated, import-safe, RLS-scoped modules) —
the right shape. The scale risks are concentration + a couple of god-files.

| # | Gap | State | Severity | Fix |
|---|---|---|---|---|
| SC1 | **One backend box = API + voice + DB + LiveKit + SIP** | Single failure + resource domain; voice is CPU-sensitive and shares the box with Postgres + API. | 🟧 HIGH | Plan DB offload (managed PG / read-replica) + a separate voice-worker box as concurrency grows. Document concurrency ceiling (`VOBIZ_MAX_CONCURRENT_CALLS`). |
| SC2 | **`caller.py` is a 258KB god-router; `agent.py` has the brain inlined** | Hard to extend safely; every change risks the earner. | 🟧 HIGH | The inbound V2 plan's `voice_core/` spine + capability registry + the gated `voice_brain/` lib extraction (byte-identical, behind a flag). Adopt incrementally. |
| SC3 | **JSON stores for tenant/brain/numbers/DIDs** | `var/*.json` + JSONL for config; fine for now, not for many vendors. | 🟨 MED | Consolidate to PG + FORCE-RLS (Phase-6) keeping JSON as the degrade fallback. |
| SC4 | **Hatchet built but not in the request path** | Durable-orchestration spine exists (`famit-hatchet`), `:7077` filtered, cutover deferred. | 🟨 MED | Cut the async legs (campaign runs, WA blasts, follow-up ticks) onto Hatchet for durable retries at scale. |
| SC5 | **No load/concurrency test evidence** | No documented "we handled N concurrent calls / M campaigns". | 🟨 MED | A load test → a published concurrency number. Buyers and the founder both need the ceiling. |

---

## 7. "LLM EVERYWHERE" — where AI is missing (SEVERITY: HIGH — the 2026 product expectation)

> Web-confirmed (2026): LLMs have *"moved upstream from prompt-helpers to embedded collaborators
> inside the CMS, editor, analytics, and design suite — proactive help, context-aware drafts,
> real-time optimization,"* and *"30%+ of enterprise content teams have embedded LLMs, doubling by
> 2026."* Lead-gen best practice: *"enrich + score for fit+intent so sales only sees high-quality,
> route high-intent instantly."* (Wellows, Therankmasters — see Sources.)

LLM today lives **only inside the voice call** (and Creative/AI-Asset image gen). Every other surface
is a classic form-and-table. Where it should be embedded (all additive, reuse the existing LLM keys —
Groq/OpenRouter/Anthropic/Gemini are all in `.env`):

| # | Surface | Today | LLM opportunity (the fix) | Severity |
|---|---|---|---|---|
| L1 | **Onboarding business profile** | Manual form. | "Paste your website URL" → LLM auto-fills the Business Brain (USPs, FAQs, objections, persona). Instant magic moment. | 🟥 HIGH |
| L2 | **WhatsApp template creation** | Manual template authoring. | LLM drafts compliant template variants from a goal ("re-engage cold leads"); checks Meta policy; suggests params. | 🟥 HIGH |
| L3 | **Campaign / script setup** | `/extract` exists for the call brief (good!) — but not extended. | Extend LLM authoring to objection banks, qualifying questions, A/B opener variants, per-language tone. | 🟧 HIGH |
| L4 | **Banner / ad copy** | Image gen exists (AI-Asset); copy is manual. | LLM ad/banner copy + headline variants tied to the campaign + the Meta CAPI signal loop. | 🟧 HIGH |
| L5 | **Lead scoring + rationale** | Post-call interest 0-100 exists; no *fit* score, no explanation. | LLM lead score = intent (have) + fit (new) + a one-line *why this lead is hot* the human reads before calling. | 🟥 HIGH |
| L6 | **Call summaries in the panel** | `_summarize_transcript` exists for hot-flag; not surfaced as rich panel summaries. | Show the LLM summary + next-best-action + sentiment on every call/contact card. Near-zero cost, high trust. |  🟧 HIGH |
| L7 | **WhatsApp reply drafting (human-in-loop)** | Auto follow-up exists; no assisted replies. | When a lead replies, LLM drafts the response for the human to approve/send — the "LLM conversation" leg of the lifecycle. | 🟥 HIGH |
| L8 | **Per-call production QA score** | `eval/scorers` is an offline release gate only. | A slim per-call QA score + flags (monologue, language-match, guard) on every record — coaching + trust. | 🟧 HIGH |
| L9 | **Vendor copilot ("ask your data")** | None. | A panel copilot: "how did Diwali campaign do?", "which leads to call today?", "draft a follow-up". Reuse RAG + the AIM brain. **The flagship 2026 differentiator.** (Guard module `copilot_guard.py` already designed in `obs-sec-cost.md` S4.) | 🟧 HIGH |
| L10 | **Knowledge-gap learning loop** | None. | Mine unhandled asks/objections → LLM drafts KB chunks → vendor approves → re-ingest. Closes `eval/`+`kb/`. | 🟨 MED |
| L11 | **Analytics narratives** | Charts only. | LLM "what changed and why + what to do" narrative over the funnel/cost data. | 🟨 MED |

---

## 8. THE SELLABILITY LENS — what a vendor pays for and TRUSTS (synthesis)

A buyer's actual purchase checklist (web-grounded), mapped to this system:

1. **"Will it work and not embarrass me?"** → reliability + never-silent + status page (§1) — *biggest gap*.
2. **"Can I set it up myself today?"** → self-serve onboarding + connect-WhatsApp/number (§2) — *biggest gap*.
3. **"Does it actually know MY business?"** → RAG corpus upload + LLM profile autofill (§2 O5, §7 L1) — *un-wired*.
4. **"Can I pay and top up myself, with a GST invoice?"** → billing productization (§4) — *un-wired*.
5. **"Is my data safe and legal (DPDP/DLT/recording)?"** → compliance posture + trust page (§5) — *thin*.
6. **"Is it actually AI, everywhere I look?"** → LLM-everywhere (§7) — *mostly absent outside the call*.
7. **"Will someone fix it fast if it breaks?"** → runbook + backups + on-call (§1 R2/R7) — *ad-hoc*.

**The product is engine-rich and skin-poor.** The fastest path to "sellable" is not more engines — it
is: deploy monitoring + paging, build the onboarding/connect/upload flows, wire-or-hide the dead
pages, add top-up + invoices, write the compliance/trust posture, and sprinkle LLM across the panel.
All additive. None touches the earner.

---

## 9. SOURCES (web research, 2026)
- Altersquare — *Voice Agent Production Readiness Checklist* (six pillars, never-silent 1.5s fallback, liveness/readiness probes, stress tests).
- Galileo — *Production Readiness Checklist for AI Agent Reliability* (traces per decision, proactive monitoring).
- Hamming AI — *Voice Agent QA Framework + Evaluation Metrics* (SLI formulas, release gates, 30-day rollout).
- Haptik — *Voice AI Enterprise Deployment Checklist*.
- FutureAGI — *Implementing Voice AI Observability for Real-Time Production Monitoring*.
- Konfirmity / Cybersecify / GRCDesk / Sprinto — *SOC 2 for SaaS (India 2026)*; *DPDP Compliance for SaaS (India 2026)* (ConsentOS); *SaaS Compliance Checklist 2026* (Zylo).
- Wellows — *LLM Content Creation Strategy 2026*; Therankmasters — *Best AI Tools for Lead Generation 2026* (enrich+score fit+intent, instant routing); Microsoft 365 Copilot docs (embedded-copilot pattern).

---

## 10. EVIDENCE INDEX (read-only, this audit)
- **Panel wiring map:** `famit-panel/lib/api.ts` (every wired endpoint), `famit-panel/app/ai-manager/_lib.ts:203` (AIM backend "not configured"), `app/funnels/page.tsx:13`, `app/ads/page.tsx:13-16`, `app/booking/page.tsx:13`, `app/workflows/page.tsx:13`, `app/creative/page.tsx:12` (reads live `/api/assets/status`), `app/settings/page.tsx` (no handoff wiring).
- **Integration surface (key NAMES only, secrets never read):** `.env.local` — Meta WA, Sentry×3, Langfuse, Slack/Discord webhooks, SES, DO Spaces, Vault, multi-carrier (Vobiz/Plivo/Exotel/Jio/Airtel), Cal.com, TRAI_DLT_*, RERA; **no Razorpay/Stripe gateway keys** (billing-checkout blocker).
- **Infra topology:** `docs/architecture/04-deployment.md` (3 boxes, VPC, CF Full-Strict, egress-lock, single-backend-box failure domain).
- **Designed-not-deployed:** `obs-sec-cost.md` (Prometheus/Grafana/Alertmanager/Sentry/Infisical/BOLA-harness/copilot-guard — all spec, not live).
- **Inbound lifecycle (do not duplicate):** `INBOUND-PIPELINE-MASTER-PLAN.md` + `-V2.md`, `plan-feature-inventory.md` (handoff, hot-lead-WA, RAG, booking, modular spine).
- **Control layer LIVE:** `memory/brain/control-layer.md` (entitlements HIDE/LOCK/ON — the tool to hide dead pages).
