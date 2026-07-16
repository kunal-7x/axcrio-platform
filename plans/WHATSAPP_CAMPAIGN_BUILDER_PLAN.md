# WHATSAPP CAMPAIGN BUILDER — MASTER BUILD PLAN (crash-safe, wave-sequenced)

> **Status:** EXECUTION-READY BUILD PLAN (synthesis wave — READ-ONLY DESIGN: this doc consolidates the five
> design specs into ONE buildable plan; it writes NO app code, edits no `caller.py`/`agent.py`/`whatsapp.py`,
> does NO git, does NOT deploy). It is the orchestrator's single source of truth for sequencing the WhatsApp
> Campaign Builder build.
>
> **Date:** 2026-06-11. **Synthesizes the five authoritative design docs** (each already adversarially
> grounded against live code):
> 1. `design/wa-builder-frontend.md` — the premium 11-step campaign WORKSPACE (the page/UI).
> 2. `design/wa-template-ai-backend.md` — the AI template-generation BRAIN (the `whatsapp-builder` module).
> 3. `design/wa-creative-integration.md` — the WhatsApp ⇄ Creative-Studio no-upload ATTACH seam.
> 4. `design/wa-delivery-analytics.md` — the SEND-SIDE engine (audience → schedule → deliver → track → learn).
> 5. `design/wa-out-of-box.md` — the top-5 out-of-the-box FEATURES (and the anti-bloat reject list).
>
> **WhatsApp is LIVE end-to-end** (real send proven; webhook `GET|POST /api/whatsapp/inbound` verified; image
> gen + DO Spaces creds proven — `WHATSAPP_GOLIVE.md`). So this build is **NOT dormant-first**: the send/log
> path is real today; AI-gen + creative-attach + analytics surfaces degrade to premium `not_configured` cards
> until their seams light up. **Hard reuse rule** ([[ui-reuse-core2-never-from-scratch]]): port the kit
> `C:\Users\kunal\Desktop\core-2-dashboard-builder-react` COMPONENTS verbatim; Inter Display app-wide; single
> `Layout title`, NO subtitle; zero raw hex (Signal tokens only); dark dot-matrix loader for all generation.

---

## 0. THE ONE-SCREEN MODEL (read first)

The WhatsApp Campaign Builder is **one route** (`/whatsapp`) = a premium **campaign WORKSPACE** driven by an
11-step Tabs rail, sitting on top of **two backend lanes that can build in parallel before the frontend even
starts**:

```
                          ┌──────────────────────────────────────────────────────────────┐
   BACKEND LANE  ────────►│  whatsapp-builder MODULE   +   wa_campaign SEND-SIDE ENGINE   │  (no frontend needed
   (builds NOW, in        │  (AI template gen + Meta-compliance validator)  (audience/     │   to build or test —
    parallel, dormant-    │  (4 ai_wa_* tables)        schedule/deliver/track/analyze/     │   offline-testable)
    safe, offline-test)   │                            learn — 5 wa_campaign_* tables)     │
                          └───────────────────────────────────┬──────────────────────────┘
                                                              │  contracts (HTTP routes + ToolSpecs)
   ─────────────────────────────────────────────────────────┼──────────────────────────────────────────────
                                                              ▼  the frontend CONSUMES these contracts
   FRONTEND LANE  ──►  /whatsapp WORKSPACE  (11-step rail)  ──── runs AFTER ────►  [UI overhaul] + [Creative
   (runs after the UI-overhaul + Creative-Studio frontend clear the lane)         Studio frontend] land first
       ① Launchpad → ② Campaign → ③ AI Templates → ④ Creative → ⑤ Banner Studio →
       ⑥ Preview → ⑦ Approval → ⑧ Audience → ⑨ Schedule → ⑩ Delivery → ⑪ Analytics
```

**The split that makes this fast + crash-safe:** the **AI-template backend** and the **Meta media-template
wiring** are NON-frontend — they build, test, and commit in the **backend lane TODAY** (dormant-safe,
offline-testable, zero new creds), independent of any UI. The **frontend workspace** is gated: it runs only
**after the global UI-overhaul lane + the Creative-Studio frontend** clear (it ports the same Core_2 archetypes
and consumes the `creative.*` contract those waves establish). The two lanes meet at the **HTTP-route /
ToolSpec contract** the backend publishes, which the frontend calls. **The LIVE send path is never broken** at
any wave — today's `/whatsapp/send` + message-log keep working until the workspace elevates them.

---

## 1. THE TWO BUILD LANES + WHY THEY PARALLELIZE

| Lane | What it builds | Depends on | Can start | Reuse spine |
|---|---|---|---|---|
| **BACKEND lane** (non-frontend) | `whatsapp-builder` module (AI gen + validator + `ai_wa_*`) · `wa_campaign` send-side engine (`wa_campaign_*`) · Meta media-template wiring (`media_id` + `header_handle`) | only live primitives (LLM seam, `whatsapp.py`, `wallet.py`, `audit.py`, Hatchet, Asset Library) — **all present** | **NOW** (parallel to the UI-overhaul) | `wallet.py` (F4), `audit.py`, `resolve_tenant`/`can` (`caller.py:551/849`), `ddl_wallet.sql` FORCE-RLS pattern, Groq→OpenRouter seam, `creative-whatsapp-creative.send_kit()` |
| **FRONTEND lane** | the 11-step `/whatsapp` premium workspace (page + pinned phone preview + picker/drawer + dashboards) | the **UI-overhaul lane** (W1 shell shipped; Inter Display + tokens live) **AND** the **Creative-Studio frontend** (the `creative.*` UI surfaces + Asset Library it embeds) **AND** the backend contracts above | **AFTER** those clear | Core_2 archetypes (`HomePage`/`MessagesPage`/`DraftsPage`/`PromotePage`/`NewProductPage`/`Income/*`), `frontend-design` skill |

**Hard dependency edges (the only ones that gate parallelism):**
- Backend `validate.py` (Meta-compliance validator) is the **authority** → build it FIRST in the backend lane;
  everything downstream feeds it (per `wa-template-ai-backend.md` §10).
- Frontend ③④⑤⑥ (AI-templates / creative / banner-studio / preview) need the **Creative-Studio frontend +
  Asset Library** already mounted (they embed its picker/drawer) → frontend cannot start those until that lane
  lands. Frontend ①②⑨⑩ (launchpad / campaign-select / schedule / delivery) need only the live send path + the
  campaign API → they can build the moment the UI-overhaul shell is ready.
- The **send last-mile** (resolve `asset_id` → Meta media upload → IMAGE-header template) is owned by the
  WhatsApp transport (`creative-whatsapp-creative.md` `media_upload.py`); the builder TRIGGERS it. Build the
  resolve/upload/template-create seam in the **backend lane**; the frontend only reflects status chips.

---

## 2. THE WAVES (dependency-ordered, each a verifiable + committable unit)

Every wave = a small set of crash-safe units. Each unit has an explicit acceptance test the agent runs and
**commits before the next** (per the global CRASH-SAFE protocol). Waves B1–B3 (backend) and F0 (UI-overhaul,
already partly shipped) run in **parallel lanes**; F1–F4 (frontend) are strictly sequential behind their gates.

### WAVE B0 — BACKEND FOUNDATION (the schema + the authority) · lane: BACKEND · parallel: YES
> Source: `wa-template-ai-backend.md` §4/§6/§10 units 1–3.

- **B0.1 `ai_wa_*` schema + store** — 4 FORCE-RLS Postgres tables (`ai_wa_suggestion_bundles`/`templates`/
  `variations`/`personalization`) via the `ddl_wallet.sql` admin-GUC pattern + JSONL offline fallback
  (`store.py`). **Verify:** cross-tenant read fails; FORCE-RLS proven; zero-`%` DDL (offline test #1, #10).
- **B0.2 `validate.py` — THE META-COMPLIANCE VALIDATOR (build FIRST after schema, it is the authority)** —
  deterministic 2026 Cloud-API grammar (name/lang/category; header TEXT≤60 or media; body ≤1024 + `{{n}}`
  sequential-gapfree-non-adjacent; footer ≤60 no-variable; buttons ≤10/≤2 URL/≤1 phone/text ≤25), category
  auto-classifier (MARKETING/UTILITY/AUTH), and the **NO-INVENT scrub** (strip fabricated price/RERA/%/claim →
  `needs_fact`). **Verify:** offline tests #3, #5, #6 — bad template → specific error; promo→MARKETING,
  enquiry→UTILITY; "₹50L" not in context → stripped + `needs_fact`.
- **B0.3 `personalize.py`** — named tokens → positional `{{1}}`/`{{2}}` (Meta sequential), bound to
  `Lead.name/city/stage`/product/campaign fields + fallback + sample. **Verify:** offline test #4.

### WAVE B1 — AI TEMPLATE GENERATION BRAIN · lane: BACKEND · parallel: YES (after B0)
> Source: `wa-template-ai-backend.md` §2/§3/§5/§7, units 4–9.

- **B1.1 context + prompt** — `context.py` (read-only campaign context: Org/Campaign/products/offer/audience/
  brand) + `prompt.py` (schema-constrained NO-INVENT prompt + industry few-shots).
- **B1.2 LLM + generate + credit** — `llm.py` (REUSE Groq→OpenRouter seam, JSON-mode, dormant, never-raises) +
  `generate.py` (context→reserve→llm→validate→persist→settle/release) + `credit.py` (`wallet.reserve(
  resource_type="wa_template_gen", idem_key)`→settle/release, F4 no-double-spend). **Verify:** tests #2, #7 —
  fake LLM → 3 templates each ≥2 variations; settle on success, release(refund) on failure; same idem_key no
  double-reserve.
- **B1.3 structure + CTA** — `structure.py` (template sequence across lead stages + timing) + goal-matched CTA
  mapping. **Verify:** bundle completeness (#2).
- **B1.4 mutators + audit** — `audit_hook.py` (channel=`whatsapp_builder`) + select/approve(`destructive`)/
  reject. **Verify:** test #8 — approve only succeeds on a valid non-`needs_fact` template.
- **B1.5 learning read** — `library.performance_summary` into `context.build` (over-weight winning angle/CTA/
  language, down-weight rejected). **Verify:** test #12.
- **B1.6 router + ToolSpec (deferred-mount)** — `router.py` `APIRouter(prefix="/whatsapp/campaign")` (the
  `generate-templates`/list/get/select/regenerate/approve/reject/submit-to-meta/attach-banner/meta-status/
  status surface) + ONE `ToolSpec` `whatsapp.generate_templates` for AIM + Workflow nodes. **Verify:** full
  `test_builder_offline.py` green (#1–#13), ZERO network/creds. **STOP — orchestrator mounts the route.**

### WAVE B2 — META MEDIA-TEMPLATE WIRING (the last mile) · lane: BACKEND · parallel: YES (after B1, with B3)
> Source: `wa-creative-integration.md` §6 + `wa-template-ai-backend.md` `meta_submit.py`.

- **B2.1 attach-banner seam** — bind an **approved** `AssetRef` (`creative.get`, tenant-checked) as the
  template header (`attach_asset_id`), re-asserting ownership. **Verify:** offline test #9 — other-tenant asset
  refused; own approved asset bound.
- **B2.2 resolve → Meta media upload (the KEY SUBTLETY)** — at template-CREATE produce a Graph **resumable
  `header_handle`**; at each SEND produce a `media_id` from `POST /{phone_id}/media`, **cached by
  `(phone_number_id, file_sha256)`** (upload once). **TWO media refs from the SAME bytes.** Owned by the
  WhatsApp transport (`media_upload.py`); the builder triggers it. **Verify:** the `POST /{waba}/
  message_templates` IMAGE-header body shape + the `POST /{phone_id}/messages type=template` send shape match
  `WHATSAPP_GOLIVE` TEST-1 (offline test #11, fake Meta transport — zero network).
- **B2.3 submit-to-meta (dormant seam)** — `meta_submit.py` queues an approved template to Meta for review;
  `not_configured` without creds; never auto-submits. **Verify:** test #11 dormant path.

### WAVE B3 — SEND-SIDE ENGINE (audience → schedule → deliver → track → learn) · lane: BACKEND · parallel: YES (after B0, with B2)
> Source: `wa-delivery-analytics.md` §2–§10, all 7 units.

- **B3.1 audience resolver + consent gate** — PORT the run-campaign filter model verbatim (stored ∪ CSV/XLSX
  → temp hot≥70/warm40-69/cold<40 → saved segment → manual − DND/opt-out) + the **WhatsApp consent/session gate**
  (open-session free SERVICE vs opt-in TEMPLATE vs excluded; NO MARKETING without `wa_marketing_optin`) +
  per-recipient frequency cap. **Verify:** mixed list → correct open-session/opt-in/excluded counts; STOP
  excluded; preview==recipients.
- **B3.2 `wa_campaign_*` schema + RLS** — 5 FORCE-RLS tables (`wa_campaigns`/`segments`/`sends`/**`cells`**/
  `events`); `cells` = the rollup per `(template × creative × audience)`. **Verify:** cross-tenant read fails;
  zero-`%` DDL.
- **B3.3 scheduler + pacing + quality-tier throttle** — now/at/drip/best-time/recurring under a **hard
  quality-tier throttle** (1K/10K/100K/∞ cap; auto-throttle+alert on YELLOW/RED — the #1 deliverability rule)
  + India DLT/DND quiet-hours + warm-up ramp; Hatchet-durable, dormant→in-process. **Verify:** 1k list paced
  to cap; quiet-hours defer; RED halves rate; recurring re-resolves a segment.
- **B3.4 durable Sender** — per-recipient walk that **REUSES `creative-whatsapp-creative.send_kit()`** (never
  re-implements the wire), re-checks consent, detects session (free SERVICE vs billed TEMPLATE, UTILITY-bias),
  wallet reserve→send→settle/refund, tags every `wamid` with `campaign×template×creative×segment×recipient`,
  A/B variant assign, Meta-error-graceful (`131047`→template fallback). **Verify (fake transport):** no
  double-send/charge on resume; SERVICE=₹0; variant tagged.
- **B3.5 tracking rollup** — route the TWO already-live webhooks (status + inbound, NO new endpoint) into the
  funnel state machine (queued→sent→delivered→read→replied→clicked→landing→booked→converted); reply-classify
  via the LLM seam; CTA `?wa_send_id=` tagging. **Verify:** transitions idempotent; STOP suppresses; click ties
  to the exact send.
- **B3.6 analytics rollup** — `cells` rollup + derived metrics (delivery/read/reply/CTR/booking/conversion +
  cost-per-X + ROI/ROAS + stop-rate penalty + quality-trend); attribution labeled **tagged|inferred**; empty
  cell = "—" (never fabricated). **Verify:** rates correct; no fabrication; per-segment/per-creative
  leaderboards correct.
- **B3.7 learning loop** — Bayesian-smoothed cell score (low-N NOT crowned; opt-out penalty), ★winner badges,
  `creative.update_metrics`/`set_status(winner)` writeback to the Asset Library, clone/optimize
  (`regenerate(more_like_winner)`)/repurpose (`send_to_adbot`). **Verify:** low-N not crowned; winner writes
  back; "more like winner" regen works; L2 reuse requires approval.

### WAVE F0 — UI-OVERHAUL FOUNDATION (the gate the frontend waits on) · lane: FRONTEND · parallel: with backend
> Source: [[ui-reuse-core2-never-from-scratch]] (W1 shipped) + the Creative-Studio frontend lane.

- **F0.1 design-system shell** — **DONE (W1 shipped):** Inter Display app-wide, `--text-h*` aligned,
  PageHeader neutralized, nav cleaned. The shell the workspace ports its archetypes from is live.
- **F0.2 Creative-Studio frontend + Asset Library (PREREQUISITE)** — the `creative.*` UI surfaces + the Asset
  Library gallery the WhatsApp builder embeds in steps ④⑤ (`cs-asset-library.md` L9 embedded picker). **This
  is the explicit gate** — the WhatsApp creative steps cannot build until this lands. *(Owned by the Creative
  Studio frontend wave, not this plan — listed here as the dependency edge.)*

### WAVE F1 — WORKSPACE SHELL + SPINE + LIVE DELIVERY · lane: FRONTEND · after F0.1 (NOT blocked on creative)
> Source: `wa-builder-frontend.md` §6 build-order steps 1–3. **These steps need only the live send path +
> campaign API — they build the moment the UI shell is ready, ahead of the creative-dependent steps.**

- **F1.1 shell + 11-step rail + ① Launchpad** — `Layout`+`Tabs` stepper over the pipeline; `HomePage` 2-col
  launchpad (KPI strip + campaign cards + winning-template reuse gallery + needs-approval). **Verify:** renders;
  nav works; zero raw hex; dormant-safe.
- **F1.2 ② Campaign select + ⑥ Preview + the pinned PHONE MOCK (the "feels real" spine)** — `CustomerList`
  campaign list+select + read-only Campaign Context panel; the **restyled `Message` bubble phone preview**
  (media header + body tokens + CTA chips + double-tick), live-updating from sample data. **Verify:** select
  hydrates context; preview re-renders on edit; tokens render.
- **F1.3 ⑩ Delivery + ⑨ Schedule (elevate the LIVE send/log)** — `Income/StatementsPage` per-recipient status
  table + webhook-driven KPI strip; `ScheduledPage`/`ScheduleProduct` send-now/schedule. **Verify:** the
  existing message-log is elevated into the campaign view; LIVE send still works.

### WAVE F2 — AI + CREATIVE SEAMS · lane: FRONTEND · after F0.2 (Creative-Studio frontend) + B1/B2
> Source: `wa-builder-frontend.md` step 4 + `wa-creative-integration.md` §2/§3/§5 (the 7-unit FE seam).

- **F2.1 ③ AI Template Generation** — `PromotePage` AI-suggestion cards (copy/CTA/angle Badge/tokens/media
  rec) over `POST /whatsapp/campaign/{id}/generate-templates` (B1.6) + the **§6-PHASE2 dot-matrix loader**;
  NO-INVENT guardrail note on the surface; dormant → "write one manually" fallback. **Verify:** cards render
  from a stub bundle; loader cycles; dormant card shows.
- **F2.2 ④ Creative picker (Door B)** — `DraftsPage` Grid + Search + Filters over `GET /creative/assets`
  (default scope `campaign_id&platform=whatsapp&kind=wa_poster,banner&status=approved&sort=top_ctr`); preview +
  attach. **Verify:** scope correct; tenant-scoped; empty state.
- **F2.3 attach flow + version-compare** — bind `asset_id` on the draft header (NO bytes, reversible, audited);
  two-gate pre-check; compare-tray modal + version-timeline over `search(root_asset_id, sort=version)`.
  **Verify:** draft asset blocks attach until approved; remove clears; lineage ordered by version.
- **F2.4 ⑤ Banner Studio (Door A drawer)** — Creative Studio `NewProductPage` 2-col in a drawer pre-seeded by
  campaign → `POST /creative/generate` → loader → edit/regenerate (new versions) → approve → "Use this";
  credit-gate Modal. **Verify:** dormant → activation panel; loader cycles; approve unlocks "Use".

### WAVE F3 — GATES + AUDIENCE + ANALYTICS + LEARNING CARDS · lane: FRONTEND · after F1+F2+B3
> Source: `wa-builder-frontend.md` step 5 + `wa-delivery-analytics.md` §6 dashboards.

- **F3.1 ⑦ Approval (two gates)** — `CommentsPage`+`Modal`: asset-approve (`creative.approve`) → WA
  send-approve + quality checklist + Meta status chip (never faked); step-up for non-writers
  (`EntitlementGuard`+`canWrite`). **Verify:** gates render in order; Meta status surfaced honestly.
- **F3.2 ⑧ Audience + insights** — `CustomerList` lead list+select + audience-insight cards (segment donut,
  reachable/suppressed KPIs, AI "target hot leads" suggestion); the consent breakdown chips from B3.1; DNC
  auto-excluded. **Verify:** counts match B3.1 preview; DNC excluded.
- **F3.3 ⑪ Analytics + Optimization** — `Income/EarningPage`+`ProductActivity`: KPI strip + funnel
  `CardChartPie` + per-variant table with `set_status(winner)` + reuse-winner / "5 more like this" cards.
  **Verify:** rates from B3.6 (no fabrication); winner action writes back.

### WAVE F4 — OUT-OF-THE-BOX TOP-5 CHAINS · lane: FRONTEND+BACKEND · after F1–F3 + B3
> Source: `wa-out-of-box.md` §2 top-5, build order **F2→F1→F3→F4→F5** (out-of-box ids). Each rides ONLY
> existing seams; each a dormant-safe verifiable unit.

- **OOB-1 Template Performance Leaderboard + 1-click reuse** (out-of-box F2, build FIRST — lowest risk,
  read-only) — read-join over the `cells` rollup / Testing Lab scoreboard (channel=whatsapp) + `creative.search
  (sort=top_reply)` + "5 more like this".
- **OOB-2 AI Auto Follow-Up Sequences** (out-of-box F1) — a Workflow Studio template
  (`trigger→delay→condition(replied?)→action`) over the reply webhook + suppression/meter; reply at any step
  exits. (Needs the Workflow Studio engine — already built.)
- **OOB-3 Per-Lead Personalized Banner + Message** (out-of-box F3) — `creative.generate(segment, campaign_id)`
  **once per segment** (bounded cost) + kit `angle` + CRM lead-stage; NO-INVENT guard.
- **OOB-4 WhatsApp + Voice-Call Combined Sequences** (out-of-box F4 — Famit's moat) — surface the
  already-designed post-call `send_creative_package` as a sequence node + `call.completed`/CTA-click triggers.
- **OOB-5 One-Click "Turn Winning Template into an Ad"** (out-of-box F5) — `creative.send_to_adbot` on an
  approved winning leaderboard row → ads-engine owns the spend (human-approved DRAFT).

> **Also fold the P0/P1 in-flow chains** noted across the frontend doc + integration doc: AI copy+banner
> co-generation (③→⑤ bridge — "Use this" hands back caption+CTA), A/B template test (⑧+⑪), reuse-winner clone
> (①+⑪), brand-kit auto-apply (⑤). These are chained existing surfaces, no new engine.

---

## 3. PARALLELIZATION + DEPENDENCY MAP (one picture)

```
TIME ───────────────────────────────────────────────────────────────────────────────────────────►

BACKEND LANE   B0 ─► B1 ─► B2 ───────────────┐
(starts NOW,        └────► B3 ───────────────┤  (B2 + B3 parallel after their B0/B1 deps)
 dormant-safe)                               │
                                             │  publishes HTTP-route + ToolSpec CONTRACTS
                                             ▼
FRONTEND LANE  F0.1(W1 ✓) ─► F1 ─────────────────────────────► F3 ─► F4
(gated)             │                                          ▲      ▲
                    └─ F0.2 (Creative-Studio FE + Asset Lib) ─► F2 ───┘      │
                       (the hard gate for F2's creative steps) │            (F4 needs F1–F3 + B3)
                                                               └─ F2 needs F0.2 + B1 + B2
```

**Parallel sets (safe to run concurrently — disjoint files/domains, one agent each):**
- **Set A (backend, NOW):** B0 → then B1; then B2 ∥ B3 (different modules: `whatsapp_builder/` vs `wa_campaign`/
  send-side). ONE agent per module; never two agents on the same file.
- **Set B (frontend, gated):** F1 can start as soon as F0.1 (W1 shell, shipped) is in place — it does NOT wait
  on creative. F2 waits on **F0.2 (Creative-Studio frontend) + B1 + B2**. F3 waits on F1+F2+B3. F4 last.

**The single most important sequencing rule (carried from every doc):** **`validate.py` (B0.2) is the
authority — build it FIRST after the schema.** The model only proposes; the validator decides. Nothing
downstream (generate, approve, submit, attach) is correct until the validator is.

**The LIVE-path invariant:** at NO wave is today's `/whatsapp/send` + message-log broken. F1.3 *elevates* the
live log into the campaign view; it does not replace the working send. Backend waves are all dormant-safe +
flag-gated (`FEATURE_WHATSAPP`/`WHATSAPP_ENABLED` OFF → live path untouched).

---

## 4. CRASH-SAFE EXECUTION DISCIPLINE (per global CRASH-SAFE protocol)

- **One agent per module/domain** (`whatsapp_builder/` ≠ `wa_campaign` send-side ≠ frontend `app/whatsapp/`).
  Shared files (e.g. a route mount in `caller.py`) are the **orchestrator's** serial step, never an agent's.
- **Every unit = build → run its named offline test → commit → next.** Never batch. The offline tests
  (`test_builder_offline.py` 13 assertions; the send-side `fake` transport tests) run with ZERO creds/network,
  so every unit is CI-gateable on the laptop.
- **Mark intent before each unit** in a per-lane STATE file (`droplet_work/whatsapp_builder/STATE.md`,
  `<send-side>/STATE.md`, `app/whatsapp/STATE.md`): the unit + "IN PROGRESS" → flip "DONE" after its test
  passes. After a crash, the one "IN PROGRESS" line is the exact resume point.
- **Model routing:** validator/compliance + the learning loop + the architecture-sensitive send orchestration =
  **opus**; the straight ports (schema/store, the Core_2 page ports, dashboards) = **sonnet**; mechanical
  fixtures/test scaffolds = **haiku**.
- **Dormant-safe + never-raises** is a build constraint, not an afterthought: every backend unit returns a
  typed `not_configured`/clamped result with no creds and never raises into a request/webhook/dial loop.

---

## 5. THE BACKEND CONTRACTS THE FRONTEND CONSUMES (the lane seam)

| Surface | Route(s) / ToolSpec | Owner wave | Frontend step that calls it |
|---|---|---|---|
| AI template generation | `POST /whatsapp/campaign/{id}/generate-templates` (+ list/get/select/regenerate/approve/reject/meta-status/status) | B1.6 | ③ AI Templates |
| Template → Meta submit + attach | `submit-to-meta` · `attach-banner` | B2 | ⑤/⑦ |
| Creative browse/generate/attach | the `creative.*` contract (`GET /creative/assets`, `POST /creative/generate|edit|regenerate|approve`, `update_metrics`/`set_status`) | Creative Studio (F0.2) + B2 trigger | ④⑤⑦⑪ |
| Audience preview + segments | `POST /wa-campaigns/preview-audience` · `POST|GET /wa-campaigns/segments` | B3.1 | ⑧ Audience |
| Campaign launch + control | `POST /wa-campaigns` · `/{id}/launch|pause|resume|cancel` | B3.3/B3.4 | ⑨ Schedule |
| Live delivery + analytics | `GET /wa-campaigns/{id}` · `/{id}/cells` · `/analytics` · `/{id}/reuse` | B3.5/B3.6/B3.7 | ⑩ Delivery, ⑪ Analytics |
| Webhooks (NO new endpoint) | the existing `GET|POST /api/whatsapp/inbound` (status + inbound) routed into B3.5 + the builder `metrics` writeback | orchestrator wiring | ⑩⑪ (live KPI strip) |
| AIM / Workflow node | ONE `ToolSpec` `whatsapp.generate_templates` + the `creative.*` Action nodes | B1.6 + integration §8 | OOB-2/OOB-4 sequences |

**One money path, always:** generation = LLM credits via `wallet.reserve(resource_type="wa_template_gen")`;
banner gen = `creative.*` credits; per-message send = the WhatsApp meter. Attach is free. **No second spend
door** anywhere. **Tenant from TOKEN never body**, FORCE-RLS on every `ai_wa_*`/`wa_campaign_*` table,
ownership re-checked on by-id/attach/submit, immutable audit (channels `whatsapp_builder`/`whatsapp`/
`wa_campaign`/`creative`).

---

## 6. FOUNDER GO-LIVE PREREQUISITES (the box-side gate for LIVE cold sends — founder action)

**Everything in waves B0–B3 + F1–F4 builds, tests, and ships with the creds ALREADY on the box** (LLM +
wallet + Meta token proven live, image-gen + DO Spaces proven — `WHATSAPP_GOLIVE.md`). The residual gate is
ONLY for **business-initiated (cold, outside-24h) list sends**. These are **founder / orchestrator box-wiring
actions**, applied in a careful wave AFTER the Control-Layer build, NOT a builder-UI task:

| # | Prerequisite | Action | Why it gates | Status |
|---|---|---|---|---|
| 1 | **New `EAA…` WhatsApp token on the box** | replace the OLD `4234…` value in `/opt/famit-agent/.env` `META_WA_TOKEN` with the proven permanent `EAA…` token | the in-app `/whatsapp/send` path (the #1 box fix) | token VALID (real send proven externally); **box `.env` still holds the OLD token** |
| 2 | **One approved real Meta template (IMAGE header + body + CTA)** | Meta → WhatsApp → Message Templates → create + submit a UTILITY (and a MARKETING) template; wire its name/language into the send config | **THE #1 launch blocker** — cold list sends require an APPROVED template; `hello_world` is test-number-only | only `hello_world` (test-only) → **need a real approved template** |
| 3 | **`FEATURE_WHATSAPP` / `WHATSAPP_ENABLED` flag set** | set the activation flag in `/opt/famit-agent/.env` + `systemctl restart famit-caller` | flips the module from dormant-safe to live in-app send | none set today (module dormant-safe by design) |
| 4 | **Webhook subscribed to `messages`** | Meta → Configuration → Callback `https://panel.famit.in/api/whatsapp/inbound`, verify token `evsaivoiceagent`, subscribe the **`messages`** field | delivery/read/reply/click tracking (the analytics + learning loop) | endpoint VERIFIED (200 + challenge echo); founder must subscribe `messages` |
| 5 | **Confirm the WABA/number** | confirm "MedFlow" / **+91 97550 40013** is the intended Famit WhatsApp number before scale | sending identity | registered on Cloud API; **confirm it's intended** |
| 6 | **(recommended) caps/consent config** | set `WA_CAMPAIGN_PER_MIN/HOUR/DAILY`, `WA_CAMPAIGN_MAX_PER_CONTACT_PER_WEEK`, DLT/quiet-hours, daily cost cap in `.env` | pacing / quality-rating protection / spend stop-loss | optional, set at activation |

> **Net:** the **whole builder (AI gen + validator + send engine + analytics + the workspace) builds and
> offline-passes with ZERO new creds.** To deliver a generated template to a COLD contact, the founder still
> needs **#1 (box token) + #2 (one approved template) + #3 (flag) + #4 (subscribe `messages`)**. Open-session
> sends (to someone who messaged the number in the last 24h) work TODAY via the free-form path.

---

## 7. HONEST REAL-vs-HYPE (carried from all five docs, one line each)

- "Select a campaign → AI writes your WhatsApp templates" — **true**, as compliant **drafts** a human approves;
  the validator scrub means it never invents a price/RERA/claim; **Meta** still approves the template before
  cold sends.
- "No manual upload, ever" — **true** for library/generated/uploaded assets (attach binds an `asset_id`, not
  bytes); the only file-intake is the Asset Library's own upload surface.
- "Blast to thousands in one click" — it's a **compliant, paced, quality-throttled, consent-gated** sender;
  cold contacts need an approved template (Meta's gate); opt-out/STOP always excluded.
- "It learns which template/banner/audience wins" — **real** deterministic per-cell scoring (Bayesian-smoothed,
  low-N not crowned, opt-out penalized) that biases the next round + writes back to the Asset Library; it does
  **not** guarantee a winner and never fabricates a metric.
- "Works today, offline" — the whole pipeline (gen → validate → personalize → audience → schedule → send-shape
  → track → analyze → learn) is offline-testable with ₹0/no network; only AI *copy quality* needs the LLM key
  and real *delivery* needs the box token + an approved template.

---

## 18-LINE SUMMARY (the wave breakdown + parallelization + founder go-live prerequisites)

1. The WhatsApp Campaign Builder = **two backend lanes (build NOW, dormant-safe, offline-testable) + one gated
   frontend workspace**, synthesized from the five design docs into wave-ordered, crash-safe units.
2. **BACKEND lane (parallel to the UI-overhaul, zero new creds):** the `whatsapp-builder` AI-template module
   (`ai_wa_*` schema) + the `wa_campaign` send-side engine (`wa_campaign_*` schema) + the Meta media-template
   wiring — all NON-frontend, so they build/test/commit immediately.
3. **WAVE B0 (foundation):** `ai_wa_*` FORCE-RLS schema/store → then **`validate.py`, the Meta-compliance
   validator, built FIRST as the authority** → `personalize.py` token binding.
4. **WAVE B1 (AI brain):** context+prompt → LLM(reuse Groq→OpenRouter)+generate+credit(F4 reserve/settle/
   release) → structure/CTA → mutators+audit → learning read → router+ToolSpec; `test_builder_offline.py`
   green (#1–#13).
5. **WAVE B2 (last mile):** attach approved `AssetRef` as header → resolve bytes → Meta media upload (the KEY
   SUBTLETY: a resumable `header_handle` at template-create + a cached `media_id` per send, TWO refs from the
   same bytes) → dormant submit-to-meta.
6. **WAVE B3 (send-side engine):** ported run-campaign audience + consent/session gate → `wa_campaign_*` schema
   → scheduler + hard quality-tier throttle → durable Sender (REUSES `send_kit()`) → webhook tracking funnel →
   `cells` analytics → learning loop (winner writeback, clone/optimize/repurpose).
7. **B2 ∥ B3 run in parallel** (different modules) once their B0/B1 deps clear; ONE agent per module, never two
   on the same file.
8. **FRONTEND lane is GATED:** it runs AFTER **F0.1 (the UI-overhaul shell — W1 already shipped)** + **F0.2
   (the Creative-Studio frontend + Asset Library it embeds)** + the backend contracts.
9. **WAVE F1 (spine, needs only the live send path):** shell + 11-step rail + ① Launchpad → ② Campaign + ⑥
   Preview + the pinned WhatsApp phone-mock → ⑨ Schedule + ⑩ Delivery (elevate the LIVE log) — these build the
   moment the shell is ready, ahead of the creative steps.
10. **WAVE F2 (needs Creative-Studio FE + B1/B2):** ③ AI-template cards → ④ Creative picker (Door B) → attach +
    version-compare → ⑤ Banner Studio drawer (Door A).
11. **WAVE F3 (needs F1+F2+B3):** ⑦ two-gate Approval → ⑧ Audience + insight cards → ⑪ Analytics + learning
    reuse cards.
12. **WAVE F4 (out-of-the-box top-5, build order F2→F1→F3→F4→F5):** Leaderboard+reuse → Auto Follow-Up
    Sequences → Per-Lead Personalized creative → WhatsApp+Voice Combined Sequences (Famit's moat) → Promote
    Winner to Ad — each rides only existing seams.
13. **Parallelization:** Set A = backend B0→B1→(B2 ∥ B3), starts NOW; Set B = frontend F1 (after the shipped
    shell) ∥ F0.2-gated F2 → F3 → F4. The only hard edges: validator-first; creative steps wait on the
    Creative-Studio FE; F4 waits on F1–F3+B3.
14. **The LIVE send path is never broken** at any wave — every backend wave is flag-gated (`FEATURE_WHATSAPP`
    OFF → live path untouched); F1.3 *elevates* the live log, never replaces the working send.
15. **One money path** (LLM gen via `wallet`, banner gen via `creative.*`, per-message send via the meter;
    attach free), **tenant-from-token never body**, **FORCE-RLS** everywhere, immutable audit — a build
    constraint on every unit.
16. **Crash-safe discipline:** one agent per module, build→offline-test→commit per unit, an "IN PROGRESS"
    line in a per-lane STATE file, opus for validator/learning/orchestration and sonnet for the ports.
17. **The whole builder builds + offline-passes with ZERO new creds.** The founder go-live prerequisites gate
    ONLY cold (outside-24h) list sends: **(1) the new `EAA…` token on the box `.env`, (2) ONE approved real
    Meta template (IMAGE header) — the #1 blocker, (3) the `FEATURE_WHATSAPP` flag + restart, (4) subscribe
    the webhook to `messages`, (5) confirm the "MedFlow" / +91 97550 40013 number, (6) optional caps/consent
    config.**
18. **Honest bounds:** AI writes compliant DRAFTS a human approves; Meta still approves the template; the
    learning loop biases style (never fabricates facts); open-session sends work today, cold list sends wait on
    prerequisite #2. Plan file: `C:\Users\kunal\Desktop\caps\WHATSAPP_CAMPAIGN_BUILDER_PLAN.md`.
