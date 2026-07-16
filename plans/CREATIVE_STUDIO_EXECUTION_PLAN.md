# CREATIVE STUDIO + AI ASSET SERVICE — BUILD EXECUTION PLAN

> **Role of this doc:** the SINGLE crash-safe build plan that synthesizes the five design docs into ordered,
> parallelizable WAVES with owners/models/gates/rollback. It does NOT re-specify the designs — it sequences them.
> **READ-ONLY planning wave** (this doc writes nothing live; no app code, no deploy, no git).
>
> **Source designs (authoritative — build to these, do not relitigate):**
> - `design/asset-service-architecture.md` — the SERVICE shape, microservice verdict, deploy/RLS/wallet/Hatchet map.
> - `design/asset-service-backend.md` — `ai_asset_*` schema (8 tables), pipeline, Hatchet jobs, billing, API, the 12 build units (U1–U12).
> - `design/asset-provider-research.md` — OpenRouter image-gen facts (the answer to "can OpenRouter do images").
> - `design/creative-studio-ui.md` — the 12 screens (S1–S11 + W1), component port map, the liquid loader.
> - `design/creative-studio-integrations.md` — the `creative.*` contract + WhatsApp/Adbot/AI-Manager/Workflow seams.
> - Parent spec: `CREATIVE_STUDIO_MASTER_PROMPT.md` (42 DNA sections + the architecture decision).
>
> **Ground truth (verified on box `famit@168.144.153.145`):** `media_gen/` dormant (FEATURE_MEDIA off → byte-identical
> live); the real image engine `creative/image_banner_studio/` is BUILT but UNDEPLOYED in the local repo
> `droplet_work/`; `wallet.py`/`audit.py`/`firewall.py`/`db.engine` are live reusable libs; Hatchet F3 box is up but
> cross-box gRPC not yet reachable; no `OPNEROUTER_API_KEY`/`SPACES_*` on the box `.env` today.

---

## 0. THE ANSWER: CAN OPENROUTER GENERATE IMAGES? — **YES (confirmed).**

Verified by the provider-research wave (`design/asset-provider-research.md`):
- **Mechanism:** the SAME chat endpoint `POST https://openrouter.ai/api/v1/chat/completions` with top-level
  `"modalities":["image","text"]`. There is NO separate `/images` route.
- **Output:** the image returns SYNCHRONOUSLY as a **base64 data-URL** at
  `choices[0].message.images[0].image_url.url` (`data:image/png;base64,…`). Decode → PNG bytes.
- **Default model:** `google/gemini-2.5-flash-image` ("Nano Banana"), ~$0.039/image. Edit/variation/reference-image
  = the same mechanism (input image in `messages` + `image_config.strength`). Synchronous; no webhook.
- **⚠ Env var is the founder typo `OPNEROUTER_API_KEY`** ("OPNE"). The adapter reads
  `OPNEROUTER_API_KEY or OPENROUTER_API_KEY`. Key value is present in `C:\Users\kunal\Desktop\caps\.env.local` but is
  **NOT on the box `.env`** — the founder pastes it server-side at activation.
- **⚠ Pricing:** read live `usage` and settle ACTUAL — do NOT hard-code per-image cost (model page says
  $2.50/M output tokens but per-image works out to ~$0.039 / 1290 img-tokens).
- **Architecturally:** OpenRouter is the FIRST `ImageProvider` impl, NOT the architecture. The Provider ABC already
  exists (`creative/image_banner_studio/providers/base.py`); the only gap is adding `providers/openrouter.py` (clone
  `gpt_image.py`'s b64 parse) + one registry line + the stage-1 prompt-builder. Swapping Leonardo/Flux/Stability/
  OpenAI-Images/Google later = a new file, no UI/workflow change. So even the worst-case ("OpenRouter image model
  unavailable for a tenant") is a one-file fall-through, never a rearchitecture.

**Net:** image generation works through OpenRouter today; the build plan treats it as the reference provider behind a
provider-agnostic ABC, with `fake`/`MockProvider` keeping the whole pipeline exercisable offline at ₹0.

---

## 1. THE FIVE WAVES (A–E) + WHAT EACH OWNS

| Wave | Name | Lane | Owner files (root) | Model | Can start when |
|---|---|---|---|---|---|
| **A** | AI Asset Service BACKEND | NEW service dir `/opt/famit-aiasset/` + local `droplet_work/ai_asset/*` (non-colliding with caller.py/frontend) | schema, providers, pipeline, jobs, billing, API, isolation | **opus** (hard: RLS/wallet/safety/idempotency) for U1–U2,U5,U6,U7,U10,U12; **sonnet** for U3,U4,U8,U9,U11 | **NOW** — design has landed; does NOT touch the frontend lane or `caller.py` run-path |
| **B** | Creative Studio FRONTEND | `famit-panel/app/creative/*` + `components/CreativeSkeleton` + nav | S1–S11 screens + liquid loader | **opus** for the liquid loader + S1/S4/S6 orchestration; **sonnet** for S7/S9 ports | **AFTER** the in-flight UI-overhaul + Control-Layer FRONTEND waves clear the `famit-panel` lane |
| **C** | WhatsApp page upgrade + asset-attach | `famit-panel/app/whatsapp/page.tsx` (+ shared asset-browser component) | W1 | **sonnet** | **AFTER** B's asset-browser + Library list exist (shares the GridProduct browser); same frontend lane as B |
| **D** | AI Manager `creative.*` wiring + Adbot + Workflow | `ai_manager/adapters/creative.py`, workforce `ToolRegistry`, `ads_engine` seam, workflow templates | the 6 integration seams (`integrations` §9) | **opus** (risk-table + idem_key + cross-tenant correctness) | **AFTER** A ships the `/api/assets` (a.k.a. `creative.*`) contract live-testable; parallel to B/C (different lane) |
| **E** | LIVE TEST + security gate | the box `.env`, nginx (frontend box), systemd, isolation suite run on live PG | real banner from a real campaign via founder OpenRouter key; the 9-probe isolation suite | **opus** (security) drives; founder pastes keys | **AFTER** A (and ideally D) land; final wiring unit |

**The lane rule (the #1 collision-avoidance decision):** there are exactly **two write-lanes** — the **backend lane**
(NEW service dir + monolith adapters; never edits `caller.py`/`agent.py` run-path) and the **frontend lane**
(`famit-panel`). Wave A + Wave D live in the backend lane and are LARGELY NON-COLLIDING with everything else, so they
start now. Wave B + Wave C share the frontend lane with the in-flight UI-overhaul + Control-Layer build, so they MUST
serialize behind those (one agent per frontend file; never two agents editing `famit-panel` at once).

---

## 2. DEPENDENCY GRAPH + PARALLELIZATION MAP

```
                 design lands (DONE, this wave)
                          │
        ┌─────────────────┼──────────────────────────────────────┐
        ▼                 │                                        ▼
  ┌───────────┐           │                               (frontend lane is BUSY:
  │  WAVE A    │  backend lane — START NOW                  UI-overhaul + Control-Layer
  │  BACKEND   │  (new service dir; no caller.py run edits) building famit-panel)
  └─────┬─────┘           │                                        │
        │ contract live   │                                        │ those waves CLEAR
        │ (creative.* / /api/assets)                               ▼
        ├──────────────► ┌───────────┐                      ┌───────────┐
        │                │  WAVE D    │  backend lane        │  WAVE B    │  frontend lane
        │                │  AI-MGR/   │  (parallel to B/C)   │  CREATIVE  │  (serialized behind
        │                │  ADBOT/WF  │                      │  STUDIO UI │   UI-overhaul + Control)
        │                └─────┬─────┘                      └─────┬─────┘
        │                      │                                  │ asset-browser + Library exist
        │                      │                                  ▼
        │                      │                            ┌───────────┐
        │                      │                            │  WAVE C    │  frontend lane
        │                      │                            │  WHATSAPP  │  (after B's browser)
        │                      │                            └─────┬─────┘
        └──────────┬───────────┴──────────────────────────────────┘
                   ▼
            ┌───────────┐
            │  WAVE E    │  LIVE TEST + security gate
            │  ACTIVATE  │  (founder key → real banner; 9-probe isolation suite green → flip AIASSET_ENABLED)
            └───────────┘
```

**What is PARALLELIZABLE:**
- **A and (B/C) run in parallel** — different lanes (backend service dir vs `famit-panel`), zero shared files. The
  ONLY coupling is the API contract, which is fixed by design (`/api/assets/*` ↔ the UI's `/creatives/*` calls — see
  §3 reconciliation), so the frontend can build against a mocked contract while A finishes.
- **D runs in parallel with B/C** — D is the backend lane (monolith adapters + `ads_engine` + workflow templates), B/C
  are the frontend lane. D depends only on A's contract being live-testable, not on the UI.
- **Within A:** U1→U2 serial first (schema then store); then **U3/U4/U5 parallel** (disjoint files: providers /
  campaign-reader / prompt-builder); U6→U7 serial (billing before jobs); **U8/U9 parallel** (scorer / versioning);
  U10 composes; U11/U12 last. (This is `asset-service-backend.md` §11 sequencing, adopted verbatim.)
- **Within B:** the `CreativeSkeleton` liquid loader (B-unit 2) is independent and can be built/verified in isolation
  first; S2/S3/S4-S5/S6/S9/S7 are mostly sequential (S4-S5 depends on S2's generate call), but S7 Brand Kit + S9
  Library are disjoint from the S1 flagship and can be a second parallel sub-agent IF the lane allows one-agent-per-file.

**What MUST serialize (hard ordering):**
1. **A before E** — you cannot live-test generation or run the isolation suite until the service exists.
2. **UI-overhaul + Control-Layer frontend waves before B** — they own `famit-panel`'s `globals.css`, `layout.tsx`,
   `Sidebar`, navigation, and the token system B builds on top of. B designs ON TOP of the look they establish
   (`creative-studio-ui.md` §0). Starting B early = guaranteed merge conflicts in the shared shell files.
3. **B's asset-browser + Library list before C** — W1's WhatsApp "Creative assets" rail reuses the SAME GridProduct
   browser + `GET /creatives` Library list that B builds. Building C first would duplicate or fork that component.
4. **A's contract live before D** — D's adapters/seams call `creative.*`; they need the routes to exist to test against.
5. **A (+ D ideally) before E** — E flips `AIASSET_ENABLED` only after the 9-probe isolation suite is green on live PG.

**Crash-safe discipline (every wave):** ADDITIVE + dormant-first; one agent per file/domain; commit per verified unit;
mark intent "IN PROGRESS"→"DONE" in the wave's STATE file; the live platform stays byte-identical until Wave E's final
flip. A dead agent is reconciled by `git log`/`git status`, not memory.

---

## 3. CONTRACT RECONCILIATION (the one cross-lane seam B/C/D and A must agree on)

The design docs use two route prefixes that name the SAME service: the **backend/architecture/integrations** docs use
`/api/assets/*` (nginx) and `creative.*` (tools); the **UI** doc was written against `/creatives/*`. **The architecture
doc wins on transport** (`asset-service-backend.md` §0 explicitly: "where the two diverge on transport, the architecture
doc wins"). **Resolution for the build:**
- **Public HTTP base = `/api/assets/*`** (frontend-box nginx `location /api/assets/ → 127.0.0.1:8310`). The UI's
  `/creatives/*` calls in `creative-studio-ui.md` §17 map 1:1 onto `/api/assets/*` (e.g. UI `GET /creatives/status`
  → `GET /api/assets/status`; UI `POST /creatives/batch` → `POST /api/assets/generate`; UI `GET /creatives/batch/{id}`
  → `GET /api/assets/jobs/{id}` + `/jobs/{id}/stream`; UI `GET /creatives` → `GET /api/assets/assets`).
- **Tool names = `creative.*`** (workforce `ToolSpec`s for D's AI-Manager + Workflow nodes), which call the same
  service routes. One service, two calling conventions (the integrations doc's §1 model).
- **ACTION FOR WAVE A, UNIT U10:** publish the FROZEN route table (path, method, request/response JSON) as the contract
  artifact the frontend (B/C) and the adapters (D) build against. Freeze it BEFORE B starts so the UI mocks match.
  Until then B uses the §17 mapping above as the stand-in contract.

---

## 4. WAVE A — AI ASSET SERVICE BACKEND (start NOW; backend lane)

**Scope:** the NEW dedicated service: scaffold + `ai_asset_*` schema + provider abstraction + OpenRouter image provider
+ campaign→prompt→image pipeline + Hatchet jobs + wallet/credit + isolation probes. This is the 12-unit plan from
`asset-service-backend.md` §11, sequenced for crash-safety. **All units offline-provable at ₹0 via `fake`/`MockLLM`.**

| Order | Unit (design ref) | Owner files | Model | Verify (the GATE) | Parallel? |
|---|---|---|---|---|---|
| A1 | **Scaffold + flag-gate** (arch §3,§5.1) | `ai_asset/{main,config}.py`, systemd units, `.env.example`, `requirements.txt` | opus | service starts; `GET /status`→`{enabled:false}`; every gen endpoint→`not_configured` 200, zero side effects; live platform byte-identical | serial (first) |
| A2 | **Schema** U1 (backend §2) | `db/ddl_ai_asset.sql` (8 tables + FORCE-RLS + indexes + grants, idempotent) | opus | apply as `famit_app`; assert 8 tables, FORCE-RLS + admin-GUC policy present, `DELETE` NOT granted | serial (after A1) |
| A3 | **Store core** U2 (backend §2) | `ai_asset/store.py` (one `engine.session(tenant_id)` per op; CRUD/idempotency/version-append/status-flip; `public_dict()` drops `local_path`) | opus | RLS cross-tenant probe (1/2/9) green; degrades to []/None on PG down | serial (after A2) |
| A4 | **Provider + OpenRouter** U3 (backend §3.2, provider-research) | reuse `image_banner_studio/providers/*`; ADD `providers/openrouter.py` + register row | sonnet | provider `status()` dormant w/o key; `fake` renders; routing-ladder unit test; b64 data-URL→bytes parse | **∥ with A5,A6** |
| A5 | **Campaign Reader** U4 (backend §4) | `ai_asset/campaign.py` (fill `enrich`, authed loopback reads, `CampaignContext`+provenance) | sonnet | dormant w/o service token; mocked monolith JSON→correct context; never-raises fuzz | **∥ with A4,A6** |
| A6 | **PromptBuilder + no-invent** U5 (backend §3.1, §20) | `ai_asset/prompt_builder.py` (N-angle VariantBriefs via `shared/llm` + the deterministic no-invent validator) | opus | `fake_llm`→N distinct angles; **negative control: invented "₹58L/50% OFF" not in context → STRIPPED** (probe 7); bad-JSON retry→fallback | **∥ with A4,A5** |
| A7 | **Billing** U6 (backend §6) | `ai_asset/billing.py` (estimate/reserve/settle/release via `wallet.py`; hold-backend tag; ceil-never-under-reserve; prepaid-vs-prepaid_wallet branch) | opus | seam-signature guard (`reserve` has `amount_minor`+`idem_key`); over_budget path clean (no 500); double-settle charged once (probe 8) | serial (after A3) |
| A8 | **Jobs + Hatchet** U7 (backend §5) | `ai_asset/jobs.py` + `workflow.py` (state machine; phases; **inline-fallback runner**; SSE progress) | opus | inline runner drives queued→…→succeeded offline; cancel releases hold; crash→wallet TTL-sweep reconcile | serial (after A7) |
| A9 | **Scorer** U8 (backend §3,§30) | `ai_asset/score.py` (rule-based creative score → `ai_creative_scores`) | sonnet | deterministic 0–100, denormalized to `ai_assets.score`; never-raises | **∥ with A10** |
| A10 | **Versioning/edit/regen** U9 (backend §2,§3) | edit/regenerate→new `ai_asset_versions`; original immutable; approve flips `current_version_id` | sonnet | original kept after edit; lineage `parent_version_id`; rollback works | **∥ with A9** |
| A11 | **API router + FROZEN contract** U10 (backend §8, §3 of this plan) | `ai_asset/endpoints.py` (`build_router(resolve_tenant,can,need_auth,forbidden,firewall)` — token-deriving, NOT a module-level router) | opus | full forge matrix (probes 2/3/4); `AIASSET_ENABLED` gate→503; `/status` un-gated; **publish the frozen route table** | composes (after A4–A10) |
| A12 | **Integrations seams** U11 (backend §7) | attach (whatsapp/meta_ads/workflow)→`ai_asset_usage` + `handoff.jsonl`; perf write-back | sonnet | usage rows; approved-only attach; handoff drained-by-spine contract | serial (after A11) |
| A13 | **Isolation suite** U12 (backend §9) | `ai_asset/tests/test_isolation.py` (9 probes + negative controls) | opus | **all 9 probes green on live PG** (incl. the body-override negative control that PROVES teeth) — this is the gate for Wave E | last (before E) |

**Regression / isolation gate (Wave A overall):** (1) live platform byte-identical with `AIASSET_ENABLED=0` (no
`caller.py`/`agent.py` run-path edit; router include is additive + gated); (2) the 9-probe isolation suite green incl.
the negative control; (3) no-double-spend proven through the asset path (reuses `test_wallet_concurrency.py`
guarantees); (4) no-invent validator negative control green. **Rollback:** the whole service is a separate dir + a
disabled systemd unit + an un-applied nginx location + `AIASSET_ENABLED=0`; rollback = `systemctl stop/disable
famit-aiasset*` + leave the nginx location commented. Schema is additive `ai_asset_*` (no live table touched);
`DROP SCHEMA`-equivalent is `DROP TABLE ai_asset_*` if ever needed. `.env.*bak.*` for any env edit.

---

## 5. WAVE B — CREATIVE STUDIO FRONTEND (after UI-overhaul + Control-Layer clear the frontend lane)

**Scope:** the 12 screens (`creative-studio-ui.md` S1–S11) + the ONE new component `CreativeSkeleton` (the liquid
loader). **Iron rule: PORT reference-kit components verbatim** (`core-2-dashboard-builder-react`); the ONLY hand-built
component is `CreativeSkeleton`. Build order = `creative-studio-ui.md` §18.

| Order | Unit (UI ref) | Owner files | Model | Verify (the GATE) |
|---|---|---|---|---|
| B1 | Route group + nav shells (S1/S9/S7 `NoFound` states) | `app/creative/{page,library/page,brand/page}.tsx`, `contstants/navigation.tsx` | sonnet | renders; nav active-state correct; `<Layout title>` once, no PageHeader |
| B2 | **`CreativeSkeleton` liquid loader** (UI §9) | `components/CreativeSkeleton/index.tsx` + `globals.css` keyframes | **opus** | 4 states (queued→generating→ready→error); 60fps CSS-only (animate position/opacity/transform); reduced-motion fallback; dark-mode; morphs in-place no reflow |
| B3 | S2 Create hero | S1 col-left (`Select`/`Tabs`/`Field`/`Button isBlack`) | sonnet | selectors + command box; Generate wired to `POST /api/assets/generate`; credit-estimate line; model selector default "Auto" under Advanced |
| B4 | S3 Campaign context | S1 col-right | sonnet | reads campaign + `context.enrich`; provenance chips; missing-field "AI will ask" chip (no blank) |
| B5 | S4 queue + S5 variants grid | S1 col-left bottom (`GridProduct` port) | opus | poll `GET /api/assets/jobs/{id}` (+SSE); skeleton→variant morph in-place; angle Badge; score; status Badge; "3 of 5 ready" |
| B6 | S6 Asset Detail slide-over + NL edit | `Modal isSlidePanel` (DetailsPage port) | opus | NL edit → NEW version (original kept); version strip; status control; score sub-scores; quick-chip pills |
| B7 | S9 Library | `ExploreCreatorsPage` + `Filters` + `Search` (port) | sonnet | grid + facets (campaign/platform/type/status/angle/size/date/score) against `GET /api/assets/assets`; same card as S5 |
| B8 | S7 Brand Kit + S8 performance tab | `SettingsPage` port | sonnet | logo/palette/tone/CTA/do-not-use CRUD; honest empty perf until ads loop reports |
| B9 | S10 upload-reference + S11 use→destination | `FieldImage`→command box; `Dropdown` destination picker | sonnet | reference image → `reference_image`; Use→WhatsApp/Ads/Workflow/Download |

**Regression / acceptance gate (Wave B):** the `ui-design-principles.md` §7 checklist per page — ONE `Layout` title
(no PageHeader/eyebrow/subtitle), everything in `Card`s, **zero raw hex / semantic tokens only**, Inter Display, real
loading (the liquid state) / empty (`NoFound`) / error (one token banner), progressive disclosure, vendor-simple happy
path. **Reference-component-only** (the only new component is `CreativeSkeleton`). **Rollback:** new route group + new
nav entry — delete `app/creative/` + the nav line; no existing page is modified by B (W1 is Wave C).

---

## 6. WAVE C — WHATSAPP PAGE UPGRADE + ASSET-ATTACH (after B's browser; frontend lane)

**Scope:** W1 (`creative-studio-ui.md` §15) — turn `app/whatsapp/page.tsx` (2 flat cards + deprecated `PageHeader` +
raw `<table>`) into the premium 2-col multi-card creative-aware console.

| Order | Unit | Owner files | Model | Verify (the GATE) |
|---|---|---|---|---|
| C1 | Strip + restructure | `app/whatsapp/page.tsx` | sonnet | remove `PageHeader` import+usage (L7,96–100); 2-col `HomePage` grammar; `<Layout title="WhatsApp">` only |
| C2 | Creative-assets browser (col-right) | reuse B7's GridProduct browser + `Filters`+`Search` | sonnet | shows `GET /api/assets/assets` filtered campaign/platform/status; click→preview→Attach |
| C3 | Compose + attach + live preview | `Field`/`Select`/`Editor` + WhatsApp-bubble mock | sonnet | attached-banner preview; "Ask AI to write this"; deep-link "Make a poster for hot leads"→S1; live bubble preview |
| C4 | Sent-log port | `Table`/`TableRow` + `Badge` | sonnet | raw `<table>`→`Table`; raw-hex amber banner (L112–114)→token classes; `sendWhatsApp` unchanged |

**Regression gate (Wave C):** same §7 acceptance checklist; existing `sendWhatsApp` behavior + the dormant
not-configured banner preserved (just token-styled, not raw-hex). **Rollback:** `app/whatsapp/page.tsx` is a single
file — `git checkout` it to revert; no shared-file edits beyond reusing B's already-shipped browser component.

---

## 7. WAVE D — AI MANAGER `creative.*` + ADBOT + WORKFLOW WIRING (parallel to B/C; backend lane)

**Scope:** the 6 deferred integration seams from `creative-studio-integrations.md` §9 — wires the existing parked AIM
`creative` adapters, the `ads_engine` loop, and the Workflow palette to A's live contract. **Each seam is dormant-safe
+ offline-testable; no destructive spine edit.**

| Order | Seam (integrations §9) | Owner files | Model | Verify (the GATE) |
|---|---|---|---|---|
| D1 | Register `creative.*` `ToolSpec`s | workforce `ToolRegistry` (the §1.1 set + money/risk metadata) | opus | risk table classifies each correctly (generate/edit/regenerate/send_to_adbot=`spend`; send_to_whatsapp=`bulk`; approve=`destructive`); an unapproved asset can't be sent |
| D2 | Wire `adapters/creative.py` | `ai_manager/adapters/creative.py` + `creative_pack` Hatchet worker | opus | voice "make 5 banners"→parked-for-credit→step-up→generate; **idem_key passed down (single wallet hold)**; cross-tenant forge→404 |
| D3 | Adbot feed-in/feedback | `ads_engine` seam (`propose_experiment` reads `creative.search(status=approved)`; optimizer `update_metrics`/`set_status(winner\|trashed)`; `regenerate(more_like_winner)`) | opus | **only approved assets enter**; metrics write back to the right `variant_id`; winner-regen works |
| D4 | WhatsApp browse/attach + writeback (backend side) | WhatsApp plane `assemble_kit` fetches by `creative.get`/library `url`; status webhook→`update_metrics` | sonnet | attach an approved poster; suppression still blocks; metrics roll up to the asset (C is the UI; D4 is the backend seam) |
| D5 | Workflow creative nodes + 2 templates | Workflow palette Action nodes over the `ToolSpec`s; ship Flow A (campaign→banners→approve→Adbot) + Flow B (lead-hot→poster→send→remind) | opus | a money creative node WITHOUT a dominating BUDGET node is **REJECTED at publish** (compiler dominator check); APPROVAL forced on send |
| D6 | Performance-learning read | `creative.generate` pulls `library.performance_summary(...)` into the prompt-builder | sonnet | a tenant with a winning "urgency" angle → urgency-weighted next batch; rejected style down-weighted; **no fabricated facts** |

**Regression gate (Wave D):** one money-path (no plane gets a second creative spend door); tenant-from-token (body
forge fails); FORCE-RLS holds across plane handoffs; AIM in-process composition unchanged when the service is dormant
(`not_configured` degrades a voice call / workflow run / dial loop gracefully — never raises). **Rollback:** each seam
is additive + flag/registry-gated; un-register the `ToolSpec`s + revert the adapter wiring file; the parked adapters
return to dormant. No `caller.py` run-path edit.

---

## 8. WAVE E — LIVE TEST + SECURITY GATE (after A; final wiring)

**Scope:** generate a REAL banner from a REAL campaign via the founder's OpenRouter key, interim local-fs storage, then
the security gate that flips `AIASSET_ENABLED` for ONE test tenant.

| Order | Step | Action | Model | Verify (the GATE) |
|---|---|---|---|---|
| E1 | Isolation suite on live PG | run A13's 9-probe suite (incl. negative controls) on the live cluster | opus (security) | **all 9 green** — body-override forge fails (teeth proven); no-invent strip works; no-double-spend holds; raw `local_path` never leaks |
| E2 | Wiring (un-applied diffs) | install `famit-aiasset` + `-worker` systemd units (disabled); add the frontend-box nginx `location /api/assets/`; reuse AIM `mint-scoped-token` | opus | service reachable on `127.0.0.1:8310`; nginx routes `/api/assets/*`; `/status`→ready when enabled |
| E3 | Founder activation | founder pastes `OPNEROUTER_API_KEY` (+`AIASSET_SERVICE_TOKEN`) server-side; set `AIASSET_ENABLED=1` for ONE test tenant | opus + founder | `GET /api/assets/status`→providers configured |
| E4 | **The real-banner proof** | pick a real campaign → `POST /api/assets/generate {kind:banner, n:1}` → inline/Hatchet render → OpenRouter `google/gemini-2.5-flash-image` → b64→PNG → box-fs `var/assets/<vendor>/…` → `ai_assets` row | opus | a REAL banner file exists on disk + a library row; wallet reserved→settled ACTUAL (read live `usage`); audit `asset.generate` row; UI shows it |
| E5 | Security review | run `/security-review` on the diff; confirm tenant-from-token, FORCE-RLS, one-money-path, immutable audit, dormant-safe | opus (security) | no finding; then roll out vendor-by-vendor |

**Regression / rollback (Wave E):** if E1 fails any probe, DO NOT enable — fix in Wave A and re-run. The flip is
per-tenant (`ai_asset_provider_state` row or `AIASSET_ENABLED` scoped) so blast radius = one test tenant; rollback =
`AIASSET_ENABLED=0` + `systemctl stop famit-aiasset*` + comment the nginx location → live platform byte-identical
again. Interim storage = box fs (no Spaces dependency to roll back). Never auto-launch a paid ad from this gate (the
RED-TEAM caveat — this gate caps image-GENERATION cost only; ad spend lives in `ads_engine`).

---

## 9. FOUNDER BLOCKERS (appended to `need.md`; recorded, not design-blocking)

| # | Blocker | Status / interim | Blocks |
|---|---|---|---|
| 1 | **OpenRouter API key** (`OPNEROUTER_API_KEY` — note the typo) | **PROVIDED** in `.env.local`; NOT on box `.env`. Founder pastes server-side at E3. | Wave E real-banner proof (generation QUALITY only; pipeline runs offline via `fake`) |
| 2 | **DO Spaces creds** (`SPACES_*`) | **INTERIM = box filesystem** `var/assets/` (`spaces.py` dormant until set). | Nothing now; only durable/CDN storage + extraction later |
| 3 | **Hatchet cross-box gRPC** (open tcp/7077 from backend priv IP + `SERVER_GRPC_BROADCAST_ADDRESS` + **regen token**) | **INTERIM = inline/threaded fallback runner** drives small jobs. Shared prereq with AI Manager. | Live async batch rendering at scale (not the demo) |
| 4 | **`AIASSET_SERVICE_TOKEN`** (a real manager/admin tenant token for loopback campaign reads) | Founder/orchestrator sets at E2; dormant-until-set (Campaign Reader returns `not_configured`). | Campaign-context enrichment (pipeline runs on explicit spec without it) |
| 5 | **Reasoning LLM key** for the stage-1 prompt-builder (reuse box `GROQ_API_KEY*` or Claude) | **INTERIM = `MockLLM`** + the deterministic `DEFAULT_ANGLES` fallback. | Prompt QUALITY only |
| 6 | **DO droplet limit (3/3)** | **Co-located** on the backend box (works now). | True extraction to a GPU droplet (self-host image/video models) |
| 7 | **Meta WhatsApp** (phone-number-id + permanent token + approved template) | Already a top-4 `need.md` blocker; WhatsApp ATTACH/preview UI (Wave C) builds dormant-safe. | Live WhatsApp PUBLISH of an attached asset (template approval is Meta's gate) |

**Activation is incremental:** with `AIASSET_ENABLED=0` the live platform is byte-identical; flipping it + pasting the
OpenRouter key turns on Creative Studio for ONE test tenant, then vendor-by-vendor. Only #1 (+ optionally #5) is needed
for the real-banner proof; the rest are quality/scale/storage upgrades.

---

## 10. ONE-SCREEN SUMMARY

- **Can OpenRouter generate images? YES** — same `/v1/chat/completions` + `"modalities":["image"]`, base64 PNG out,
  default `google/gemini-2.5-flash-image`, ~$0.039/img; env var typo `OPNEROUTER_API_KEY`; it's the FIRST provider
  behind an existing ABC, not the architecture.
- **5 waves:** **A** backend service (start NOW, backend lane, non-colliding) · **B** Creative Studio frontend (after
  UI-overhaul + Control-Layer clear `famit-panel`) · **C** WhatsApp upgrade (after B's browser, same frontend lane) ·
  **D** AI-Manager/Adbot/Workflow wiring (parallel to B/C, backend lane) · **E** live real-banner test + security gate.
- **Parallelizable:** A ∥ (B/C) ∥ D — two lanes (backend service dir vs `famit-panel`); A's frozen contract is the only
  cross-lane seam. **Serialize:** UI-overhaul+Control→B; B's browser→C; A's contract→D; A+suite→E.
- **The gate everywhere:** ADDITIVE + dormant-first; `AIASSET_ENABLED=0` keeps live byte-identical; 9-probe isolation
  suite (with the body-override negative control) gates the flip; no-double-spend + no-invent proven offline at ₹0.
- **Founder blockers:** OpenRouter key (provided, paste server-side) · Spaces=interim box-fs · Hatchet gRPC=interim
  inline runner · service token · LLM key=MockLLM · droplet limit=co-located · Meta WhatsApp for live publish.
```
