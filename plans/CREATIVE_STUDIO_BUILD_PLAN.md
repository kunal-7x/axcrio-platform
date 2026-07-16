# CREATIVE STUDIO — Build Plan

Status date: 2026-06-09 · Verified against `droplet_work/`, `design/`, and `famit-panel/` on disk.

> **One-line product:** a campaign dropdown turns a single intent into a **batch of
> AI-generated ad creatives** (video / image / 3D / brochure / landing / WhatsApp),
> fanned out as **async media render jobs**, collected into an **Asset Library**, launched
> as **multi-variant ad experiments**, then **autonomously scaled / killed / reallocated**
> under hard spend caps + a human approval gate, with **revenue stitched back to
> leads → CRM → voice → WhatsApp** — all orchestrated by an **AI Marketing Manager brain**.

This plan has five parts: (1) the sidebar multi-page structure, (2) the end-to-end
autonomous flow, (3) the AI Marketing Manager brain, (4) scaffolded-vs-to-build + sequence +
deps, (5) the credential blockers.

---

## 0. The organizing axis — UPPER (scaffolded) vs LOWER (to-build)

Everything resolves onto two layers. This is *why nothing is live yet*: the coupling
points exist but resolve to deterministic fakes / `module_absent` until the lower layer
and the credentials land.

```
UPPER   droplet_work/creative/        ← SCAFFOLDED, dormant. 10 sub-page modules + shared infra.
        (the PRODUCT / orchestration)   Endpoints DEFINED-not-mounted. Never-raises. fake engines.
                                         With no env keys every entry point returns {"status":"not_configured"}.
                │  the ONLY coupling: defensive try/except import of the sibling, else fake
                ▼
LOWER   droplet_work/automation/       ← TO-BUILD. Directory is EMPTY (count: 0).
        (the real ENGINES + the BRAIN)   Real provider clients (automation.video/image/threed/ads),
                                         the spend/firewall rails, AND the aimanager brain.
                                         All DESIGNED (design/automation-*.md) — none scaffolded.
```

- **UPPER is real on disk:** `creative/` has 10 module packages + `shared/` + `tests/`,
  all import-clean offline, all offline-tested. They are **dormant**: zero network, never
  raise, redact secrets, mirror the live `whatsapp.py` `{"status":"not_configured"}` contract.
- **LOWER does not exist yet:** `droplet_work/automation/` is an empty dir. The studios
  fan out through `creative/batch/studios.py`, which imports `from automation import video / image / threed / ads` **defensively** — when absent it returns `{"status":"module_absent"}` and the pipeline runs on a fake engine.
- **The spine is untouched:** no `creative/*` endpoint is mounted into `caller.py`; the
  orchestrator mounts them later. `caller.py` / `agent.py` were not edited by any wave.

---

## 1. Sidebar structure — the CREATIVE STUDIO multi-page section

Mirrors **Billing's** collapsible-dropdown pattern exactly
(`famit-panel/contstants/navigation.tsx:65-93`): a single collapsible **parent with no
`href`** and a `list:` of children, each child its own route under `/creative/...`. Same
mechanism as the core-2 "Income → …" expandable group. `roles: "manager"` gates the
section (spend-bearing), matching how WhatsApp/Webhooks are gated.

### 1.1 Proposed nav entry (drop into `navigation.tsx`, after Billing)

```js
{
  // Collapsible parent (no href) — rendered via the Sidebar/Dropdown expandable group,
  // identical to the Billing block above. Each child is its own route under /creative/.
  title: "Creative Studio",
  icon: "promote",
  roles: "manager",
  list: [
    { title: "Create",            href: "/creative/create"     }, // dropdown → batch fan-out (the landing/Overview page)
    { title: "Video Studio",      href: "/creative/video"      },
    { title: "Image & Banner",    href: "/creative/image"      },
    { title: "Brochures & Catalogs", href: "/creative/brochures" },
    { title: "Landing Pages",     href: "/creative/landing"    },
    { title: "3D Products",       href: "/creative/3d"         },
    { title: "WhatsApp Creative", href: "/creative/whatsapp"   },
    { title: "Asset Library",     href: "/creative/library"    },
    { title: "Autonomous Ads",    href: "/creative/ads"        },
    { title: "Testing Lab",       href: "/creative/lab"        },
  ],
}
```

### 1.2 Page ↔ module mapping (each page = one scaffolded UPPER module)

| Sidebar sub-page | Route | Backend module (`creative/…`) | API prefix (defined, unmounted) | Role |
|---|---|---|---|---|
| **Create** (landing / Overview) | `/creative/create` | `batch` | `/creative` (batch router) | dropdown → batch fan-out **backbone**; mirrors Billing's "Overview" |
| **Video Studio** | `/creative/video` | `video_studio` | `/creative/video` | text→video ad render (fal/Wan/Kling/Veo/Seedance) |
| **Image & Banner** | `/creative/image` | `image_banner_studio` | `/creative/image` | static/banner images (GPT Image 2 / Recraft / FLUX / Ideogram) |
| **Brochures & Catalogs** | `/creative/brochures` | `brochure_catalog` | `/creative/brochures` | PDF assembly (WeasyPrint/Gotenberg/Typst) |
| **Landing Pages** | `/creative/landing` | `landing` | `/landing` | schema→render→publish landing pages (Puck/GrapesJS) |
| **3D Products** | `/creative/3d` | `threed_model` | `/threed-model` | multi-image→.glb mesh + video→splat (Meshy/Tripo/Luma) |
| **WhatsApp Creative** | `/creative/whatsapp` | `whatsapp_creative` | (under WA send) | WA creative kits + template-fallback sends |
| **Asset Library** | `/creative/library` | `asset_library` | `/creative/assets` | DO-Spaces-backed searchable asset store (the sink) |
| **Autonomous Ads** | `/creative/ads` | `ads_engine` | `/creative/ads` | multi-variant experiment loop: launch/scale/kill/reallocate |
| **Testing Lab** | `/creative/lab` | `testinglab` | `/creative/lab` | cross-channel creative scoreboard, promote/flag-weak |

**Infrastructure, not a page:** `creative/shared/` (config, asset-library primitives,
audit wrapper, cost/spend-guard shim, LLM seam) — reused by the studios, has no design
doc and no nav row. **`batch` is the backbone**, surfaced as the **"Create"** landing
page (the dropdown lives here); it is *not* a separate "batch" tab.

> **Frontend reality:** the Billing dropdown *pattern* exists and is the template, but
> **no `/creative/*` routes or pages exist in `famit-panel` yet.** The entire frontend
> (1 nav entry + 10 route pages) is a distinct **to-build** workstream (see §4).

---

## 2. End-to-end AUTONOMOUS flow

```
[1] DROPDOWN  (Create page, /creative/create)
      Founder picks campaign + product + objective + channels + variant count.
      → POST /creative/batches  (batch.generate_batch)

[2] AI AD-SCRIPT / ANGLES  (CREATIVE_LLM seam; deterministic templates when no LLM key)
      One intent → N creative briefs (hooks / angles / copy), one brief per intended variant.
      Today: CREATIVE_LLM=none → deterministic templates (a working path). Real-LLM copy is to-build.

[3] BATCH FAN-OUT → ASYNC MEDIA  (batch.studios → the LOWER engines)
      Each brief is dispatched to the right studio submit():
        video_studio / image_banner_studio / threed_model / brochure_catalog / landing / whatsapp_creative
      Each returns a job_id immediately (status="awaiting_asset"/"queued"). No variant
      launches without a real resolved asset. submit → park job_id → poll/webhook → resolve.

[4] COLLECT → ASSET LIBRARY  (asset_library.register)
      Resolved render URLs are registered as AssetRef rows (DO Spaces object storage),
      indexed + searchable. The library is a passive SINK — studios call register() from
      their own poll callbacks; it never drives.

[5] MULTI-VARIANT AD TEST  (ads_engine.propose_experiment → automation/ads rails)
      Ingest the batch: 1 asset → 1 ad variant, across Meta / Google / YouTube.
      Each variant launches at a SMALL test budget. Persist Experiment at
      status="pending_approval" (or "awaiting_asset" while jobs pend).
      ❗ Net-NEW spend (the launch) is HUMAN-APPROVED (firewall step-up gate).

[6] AUTO SCALE / KILL / REALLOCATE  (ads_engine.optimizer — THE core loop)
      poll_and_enforce (automation/ads cap+CPL breaker, Layer 2)
        → bandit.decide() (deterministic Thompson/ε-greedy + significance gate)
        → apply AUTONOMOUS actions; PARK any net-NEW-spend action for approval.
      Significance gate: act only when conversions ≥ MIN_CONVERSIONS (default 15);
      below the gate the bandit only EXPLORES — it never kills on noise.

[7] ANALYTICS / SCOREBOARD  (testinglab + ads_engine.dashboard)
      Per-variant spend / CTR / CPC / CPL / conversions / ROAS vs cap + winners/flags.
      Testing Lab joins cross-channel exposures (paid + WhatsApp + voice + organic),
      promotes winners, flags weak creatives.

[8] REVENUE CONNECTION  (ads_engine.attribution → spine_link → the funnel)
      ad → lead → CRM → conversion stitching, ROI/ROAS rollup.
      Winners feed back into the existing funnel: leads → voice agent calls → WhatsApp
      follow-up, via the spine (AIMANAGER_SERVICE_TOKEN service auth into caller.py routes).
```

### 2.1 The three autonomy tiers (the "fully autonomous" ⇄ "approval gate" tension, resolved)

Enforced deterministically in `ads_engine/guardrails.py` — **never delegated to an LLM**
(`design/creative-ads-engine.md` §0.3):

| Action | Autonomy | Why |
|---|---|---|
| Pause / kill a losing variant | **fully autonomous** | de-risking; only ever *reduces* spend |
| Reallocate budget **within** the approved experiment total (loser → winner, net-zero) | **fully autonomous** | total spend unchanged; inside the approved envelope |
| Scale a winner **UP but still within** the approved ceiling | **fully autonomous** | already inside the human-approved cap |
| **Scale UP past the experiment's approved envelope (net-NEW spend)** | **HUMAN-APPROVED** | increases real-money exposure beyond the envelope |

> "Fully autonomous optimization, **human-approved spend envelope**." Defensible, not hype.
> Hard caps are enforced via a **Postgres atomic decrement, fail-closed**; an immutable
> audit trail logs every decision; a global kill-switch (`pause_all`) pauses every variant.

---

## 3. The AI MARKETING MANAGER brain

**Primary source:** `design/automation-aimanager.md` (DESIGNED — **not yet scaffolded**;
`droplet_work/automation/` is empty). **This is a distinct module from `ads_engine`.**

- `automation/aimanager` = the **general autonomous operations manager** for the whole
  Famit revenue funnel — a meta-agent that decides *what to run, who to call, where to
  spend* and executes via the existing Famit API surface (60+ `caller.py` routes become
  typed tools).
- `creative/ads_engine` = the **creative-variant specialist** the general manager would
  otherwise lack (the bandit / experiment loop). The manager orchestrates; the ads-engine
  is the per-experiment optimizer it can call.

### 3.1 The loop — `orchestrator.run_tick(tenant_id, mode)`: plan → approve → execute

1. **PLAN** — pluggable LLM proposes a funded `Plan` (objectives → actions → budget). LLM
   is **dormant by default** (`AIMANAGER_LLM_PROVIDER=none` → deterministic `StubPlanner`,
   a valid canned plan; recommended live model is **`claude-opus-4-8`** with adaptive
   thinking). The loop **never requires** an LLM — gates/audit/idempotency are exercisable offline.
2. **APPROVAL GATE** — any plan whose external (real-money) spend exceeds
   `AIMANAGER_APPROVAL_THRESHOLD_INR` (**default `0` = all external spend human-approved**,
   the safest default) is parked as a `Decision{requires_approval:true}` and **cannot
   execute** without a recorded human approve. The Anthropic-SDK "human-in-the-loop approval
   before each tool execution" interrupt pattern.
3. **EXECUTE** — only after approval; idempotent (idempotency key per action so a re-tick
   never double-spends); **atomic spend decrement** against the cap (Postgres table noted
   optional, JSONL today). Internal actions that draw on the **already-metered credit
   ledger** (calls / WhatsApp, below threshold) can run **autonomously**.

### 3.2 Guardrails (`aimanager/guardrails.py`) — money actions are typed, gated, audited

| Guardrail | Env | Default |
|---|---|---|
| Per-action external spend ceiling | `AIMANAGER_MAX_ACTION_INR` | ₹2000 |
| Daily external spend (rolling 24h) | `AIMANAGER_MAX_DAILY_INR` | ₹5000 |
| Weekly external spend (rolling 7d) | `AIMANAGER_MAX_WEEKLY_INR` | ₹25000 |
| Approval threshold | `AIMANAGER_APPROVAL_THRESHOLD_INR` | ₹0 (all external spend approved) |
| Global kill-switch | (config flag) | active |

- **Money actions are narrow typed tools** (`create_campaign`, `set_budget`,
  `pause_campaign`, `get_spend`) — on purpose, so the harness can gate + audit each one,
  rather than a generic HTTP/bash escape hatch.
- **Audit:** writes to the existing `audit.py` (`audit.record(actor, action, …)`,
  append-only JSONL, never raises) with **new action names** — it does not reinvent the log.
  Every plan / approval / decision is also kept in aimanager's own append-only JSONL
  (`var/aimanager_state.jsonl`).
- **Real-vs-hype (stated up front in the source):** this is *augmentation with approval
  gates*, **not** an autonomous replacement of the ad team. The agent proposes a funded
  plan; a human approves anything spending real money above threshold; everything is logged
  and reversible where the platform allows.

---

## 4. SCAFFOLDED vs TO-BUILD + sequence + deps

### 4.1 SCAFFOLDED (UPPER — on disk, dormant, offline-tested)

All 10 modules under `droplet_work/creative/` (+ `shared/`, `tests/`). Each: imports
clean with no keys, returns `{"status":"not_configured"}`, never raises, redacts secrets,
defines a FastAPI `APIRouter` that is **NOT mounted**, drives a deterministic **fake engine**.

| Module | Public surface (entry points) | Notes |
|---|---|---|
| `batch` | `generate_batch[_async]`, `approve_batch`, `get_batch`, `reconcile_batch`, `killswitch`, `status` | dropdown→fan-out backbone (the "Create" page) |
| `video_studio` | schema/script/brief/engine/batch/service/endpoints (+ `fake_engine`) | text→video; engine seam to `automation.video` |
| `image_banner_studio` | `generate[_async]`, `generate_batch`, `expand_batch`, `approve_batch`, `providers_status`, `status` | multi-provider image |
| `brochure_catalog` | `build[_async]`, `approve`, `publish`, `get_job`, `engines_status`, `status` | local PDF floor works keyless |
| `landing` | `generate`, `render`, `preview`, `publish[_async]`, `submit_lead`, `serve_published`, `status` | consent-gated lead capture |
| `threed_model` | `create_capture`, `poll`, `approve_capture`, `viewer_html`, `share`, `capabilities`, `status` | mesh + splat paths |
| `whatsapp_creative` | `assemble_kit/angles`, `send_kit[_async]`, `send_creative_package`, `approve_kit`, `status` | WA creative kits |
| `asset_library` | `register`, search/index/facets, `router`, `status` | DO-Spaces sink |
| `ads_engine` | `propose_experiment`, `experiment_status`, `dashboard`, `pause_all`, `attribution_rollup`, `status` (calls `automation-ads`'s `poll_and_enforce` breaker) | the autonomous loop |
| `testinglab` | `scoreboard`, `flag_weak`, `promote_winner`, `decisions`, `health`, `status` | cross-channel scoreboard |
| `shared` | config / library / audit / cost-guard / llm seam | infra (no page) |

### 4.2 TO-BUILD

**A. LOWER automation layer (`droplet_work/automation/` — currently empty).** Designed in
`design/automation-{video,image,threed,ads,marketing,aimanager}.md`; none scaffolded:
- `automation/video`, `automation/image`, `automation/threed` — real async render clients
  (providers, webhooks, wallet holds, DO Spaces, license + content-safety).
- `automation/ads` — the real ad-spend **rails**: Meta `facebook-business` + Google
  `google-ads` SDKs, per-platform CRUD, the polling spend/CPL **circuit-breaker**, hard
  caps, the firewall/step-up approval gate, `MetricsSnapshot` normalization.
- **`automation/aimanager` — the brain (§3).**
- `automation/marketing` — WhatsApp/sequence enrollment the landing builder enrolls into.

**B. Spend firewall / step-up gate.** `firewall.py` does **not** exist yet and
`FIREWALL_ENABLED` defaults OFF; the design mandates the Phase-2 media-release and ad-launch
gate **fail-closed** (default-DENY when the guard is absent/off/no-PIN).

**C. Frontend.** Nav entry (§1.1) + **10 route pages** in `famit-panel` (none exist). Each
binds to its module's defined endpoints once mounted.

**D. Mount endpoints + wire revenue spine.** Mount every `creative/*` router into
`caller.py`; wire `spine_link` (AIMANAGER service auth) so attribution/handoff reach the
live funnel.

**E. Real-LLM creative copy.** Today only `CREATIVE_LLM=none` (deterministic templates) is
a working path; real-LLM ad-script/angles is net-new.

### 4.3 Dependencies (what gates what)

| Dep | Gates |
|---|---|
| **Postgres** | aimanager + ads-engine **atomic spend decrement** (fail-closed money cap); experiment/decision state |
| **Auth** | service-token (`AIMANAGER_SERVICE_TOKEN`) for spine_link; `roles:"manager"` nav gating |
| **Wallet / credit-ledger firewall** | the spend-guard / step-up gate (B); internal vs external-money split |
| **Object storage (DO Spaces)** | asset persistence (Asset Library is the sink; studios upload here) |

### 4.4 Build / wiring SEQUENCE (lead from the tightest constraint)

1. **Infra deps first** — Postgres (atomic decrement), wallet/credit-ledger firewall +
   `firewall.py` (fail-closed), DO Spaces bucket + creds, service-token auth. *Nothing
   spends money safely without these.*
2. **LOWER automation engines + the aimanager brain** — scaffold `automation/{video,image,
   threed,ads,aimanager,marketing}` from their design docs. This flips the studios from
   `module_absent`/fake to live; it is the single biggest unlock.
3. **Mount endpoints into the spine** — add the `creative/*` routers to `caller.py`; wire
   `spine_link` for revenue stitching.
4. **Frontend pages** — nav entry + 10 route pages bound to the now-mounted endpoints.
5. **Per-provider credential wiring** — drop keys to flip each dormant studio/platform
   `not_configured → live`, one provider at a time, smoke-testing each.

---

## 5. CREDENTIAL BLOCKERS (dormant until provided)

Every key below is read **at call time**; absent → module stays `not_configured`, no
network, never raises. Grouped by what each unblocks. (Status reports expose **booleans**
only — key values are redacted.)

### 5.1 Ad platforms (blocks Autonomous Ads + revenue loop)
- **Meta Ads:** `META_ADS_ACCESS_TOKEN`, `META_ADS_ACCOUNT_ID` (+ `facebook-business` SDK, business verification / ad account)
- **Google Ads:** `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CUSTOMER_ID` (+ OAuth client/refresh; `google-ads 31.0.0`)
- **YouTube ads** = Google Ads video campaigns (same Google Ads credentials)

### 5.2 Video / image / 3D media generation API keys
- **Video:** `FAL_KEY` (fal.ai gateway → Wan / Kling / Veo / Seedance), `REPLICATE_API_TOKEN`, `HIGGSFIELD_API_KEY`, `VIDEO_API_KEY` / `VIDEO_SELFHOST_TOKEN`
- **Image:** `OPENAI_API_KEY` (GPT Image 2), `RECRAFT_API_KEY`, `BFL_API_KEY` (+ `BFL_COMMERCIAL_LICENSE` — note: FLUX.2 Klein-9B is non-commercial), `IDEOGRAM_API_KEY`, `REPLICATE_API_TOKEN`
- **3D:** `MESHY_API_KEY` (Pro plan), `TRIPO_API_KEY`, `LUMA_API_KEY` (video→splat), `THREED_SELFHOST_TOKEN` (TRELLIS/Hunyuan self-host)
- **Creative LLM (copy/angles):** `CREATIVE_LLM` + `OPENAI_API_KEY`/`OPENAI_BASE_URL` (or the aimanager `AIMANAGER_LLM_PROVIDER` Claude path)

### 5.3 Object storage — DO Spaces (blocks Asset Library + asset persistence)
- `DO_SPACES_KEY`, `DO_SPACES_SECRET`, `DO_SPACES_ENDPOINT`, `DO_SPACES_REGION`, `DO_SPACES_BUCKET`, `DO_SPACES_CDN_BASE`
- (per-studio S3 aliases also accepted: `IMAGE_S3_*`, `BROCHURE_S3_BUCKET`, `LP_S3_BUCKET`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`)

### 5.4 The brain + spine auth (blocks autonomy + revenue connection)
- `AIMANAGER_SERVICE_TOKEN` (service auth into `caller.py` routes for attribution/handoff)
- `AIMANAGER_LLM_PROVIDER` (`claude`/`groq`/`none`) + provider key for the planner LLM
- Spend caps / approval thresholds are config (have safe defaults), **not** blockers

### 5.5 Landing tracking + WhatsApp (channel activation)
- **Landing pixels:** `LP_META_PIXEL_ID`, `LP_META_CAPI_TOKEN` (consent-gated)
- **WhatsApp:** `META_WA_TOKEN`, `META_WA_PHONE_NUMBER_ID`, `META_WA_BUSINESS_ACCOUNT_ID`, `META_WA_APP_SECRET` (the spine's existing WA creds; reused)
- **Optional publish hosts:** `NETLIFY_AUTH_TOKEN`, `CF_API_TOKEN` (landing publish targets)
