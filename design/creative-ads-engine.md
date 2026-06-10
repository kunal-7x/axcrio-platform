# DESIGN SPEC — Creative Studio + Autonomous ADS ENGINE (`droplet_work/creative/`)

> **For the build agent: implement this verbatim, one verifiable UNIT at a time.**
> This is the **ads-engine** pillar of Famit's "Autonomous Business OS" — the layer that turns a
> generated creative **BATCH** into **autonomously test-launched, measured, scaled, killed and
> rebalanced ad variants** across Meta / Google / YouTube, under **HARD spend caps + an approval
> gate + an immutable audit trail**. The **auto-optimization loop is the core** of this module.
>
> **Hard rules from the project brief (do NOT violate):**
> - NEW code ONLY under `droplet_work/creative/`. **Do NOT edit `caller.py` / `agent.py`** (the
>   backend spine) — final wiring is deferred to the orchestrator (documented seam only).
> - **NO git** (the orchestrator commits).
> - Every integration is **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS**: a no-op that returns
>   `{"status": "not_configured"}` and **NEVER raises** until the founder pastes keys — exactly
>   like the existing `droplet_work/whatsapp.py` (the canonical pattern; verified on disk).
> - **Verifiable OFFLINE**: the acceptance test makes **zero** live external calls. A `fake`/local
>   ad provider + injected metrics prove the whole loop (variants → launch → measure → scale →
>   kill → reallocate → cap-breaker → audit) without spending a paisa or needing a key.
> - Cost-optimized; self-host on DigitalOcean where it wins; production-grade, scalable.

Research date: **2026-06-09**. All chosen tools verified ACTIVE (release dates cited inline, §1/§13).
On-disk reuse seams verified against `C:\Users\kunal\Desktop\caps\droplet_work\` 2026-06-09 (§2.2).

---

## 0. WHAT THIS IS, AND WHAT IT IS **NOT** (read before coding — this prevents duplication)

The vision: a vendor picks a product/campaign from a **dropdown**; the AI auto-generates a full
creative **TESTING BATCH** (≈10 banners, 5 videos, 10 hooks, 5 landing headlines, 5 WhatsApp
angles); then **autonomous ads** launch every variant at **small test budgets**, continuously
analyze CTR/CPC/ROI/conversions/engagement, **AUTO-SCALE winners, PAUSE/trash losers, REALLOCATE
budget** — fully autonomous within guardrails, revenue-connected end to end (ads → leads → CRM →
voice → WhatsApp → analytics).

That vision spans **four** already-designed modules. This doc owns exactly **ONE slice** of it and
**references the rest**. The slice it owns is the genuine gap:

> **THIS DOC = the autonomous, variant-level EXPERIMENT loop: ingest a batch → spin up one ad
> variant per asset at small budget → measure per-variant → SCALE winners / KILL losers /
> REALLOCATE budget continuously, under hard caps + approval gate + audit. Plus the
> revenue-connection seam (ads → leads → CRM → voice → WhatsApp → analytics) and the one
> Creative-Studio sub-page it powers.**

### 0.1 REUSE vs NET-NEW (the boundary — the #1 thing that keeps this non-redundant)

| Concern | Owner | This module's relationship |
|---|---|---|
| **Ad-platform spend rails** (Meta `facebook-business` + Google `google-ads` SDKs), per-platform CRUD, the **polling spend/CPL circuit-breaker**, hard caps, the firewall/step-up approval gate, the `MetricsSnapshot` normalization | **`automation-ads.md`** (`droplet_work/automation/ads/`) | **REUSE — do NOT re-spec or re-implement.** This module calls that module's `AdProvider` interface + `poll_and_enforce` breaker. We are a *client* of the spend layer, not a second copy of it. (§2.1) |
| **General funnel-ops autonomy** (plan→approve→execute, spend caps, kill-switch, `THRESHOLD` autonomy model, idempotent execute, Postgres atomic spend decrement) | **`automation-aimanager.md`** (`droplet_work/automation/aimanager/`) | **REUSE the patterns** (approval `THRESHOLD`, idempotency key, audit action-naming, Postgres atomic decrement for the money cap). Our optimizer is the *creative-variant specialist* the general manager would otherwise lack. (§2.1, §6) |
| **The creative BATCH** (banners/logos via `automation-image.md`; videos via `automation-video.md`; 3D via `automation-threed.md`; ad copy/hooks/landing/WhatsApp angles via the in-house LLM seam + `automation-marketing.md`) | **the media-gen + marketing modules** | **REUSE — they PRODUCE the batch.** We **consume** a list of generated assets via a thin **batch-ingestion seam** (§4.2). We do NOT generate images/videos/copy ourselves. |
| **Leads / CRM / voice calls / WhatsApp / analytics** | the **existing spine** (`caller.py` routes: `/leads`, `/run`, `/whatsapp/send`, `/analytics`, `/stats`) + `whatsapp.py` | **CONNECT via the loopback/handoff seam** (§7). We do NOT touch `caller.py`; the revenue-connection is a documented event/handoff contract. |
| **NET-NEW (what THIS module owns)** | — | the **experiment/variant data model** (§4); the **autonomous scale/kill/reallocate optimization loop** (§5, the core); the **batch→ad-variant ingestion seam** (§4.2); the **revenue-attribution + downstream-handoff seam** (§7); the **Creative-Studio "Autonomous Ads" sub-page** (§8). |

> **Two adapter designs already exist** (`automation-ads.md`'s `providers/{meta,google}` and
> `automation-aimanager.md`'s `ads/{google_ads,meta_ads}`). **We add NO third ad adapter.** We bind
> to **`automation-ads.md`'s `AdProvider`** as the canonical spend layer (it is the more complete,
> breaker-first design). If that module is not yet built, we depend on its **interface** and run on
> a `noop`/`fake` provider — exactly the "sibling-may-not-exist-yet" decoupling `automation-ads.md`
> itself adopted (its FIX 2). No hard build-order chain. (§2.1)

### 0.2 The `creative/` vs `automation/` reconciliation (load-bearing directory decision)

The siblings live under `droplet_work/automation/`; the brief mandates **this** module under
`droplet_work/creative/`. We **honor `creative/`** and express the cross-module relationship as a
**dependency on an interface, not a path**:

- `creative/` imports the ad spend layer through a small **adapter resolver** (`creative/ads_link.py`,
  §2.1) that tries, in order: (a) `from automation.ads.providers import get_provider` if present;
  (b) an injected provider (offline test); (c) a built-in **`fake`/`noop`** provider. So `creative/`
  builds, imports, and passes its offline test **whether or not `automation/ads/` exists yet**.
- Same posture for the batch source: `creative/batch_link.py` resolves the media-gen modules
  (`automation.image/video/...`) if present, else accepts a caller-supplied asset list. Dormant +
  offline-safe either way.

### 0.3 The autonomy ⇄ approval tension, resolved EXPLICITLY (do not leave ambiguous)

The brief says **"fully autonomous"** AND **"approval gate"**. These are reconciled with the
**aimanager `THRESHOLD` model** (mirrors `automation-aimanager.md` §7, `automation-ads.md` Inv B):

> **The optimization loop acts AUTONOMOUSLY *within already-approved, hard-capped budget* —
> reallocating, pausing, and scaling-DOWN need no per-action approval (they reduce or hold risk).
> Any action that INCREASES net spend above the approved envelope (scale-UP past the experiment's
> approved ceiling, or launching the batch live) trips the human APPROVAL GATE.**

Concretely (the three autonomy tiers, enforced in `guardrails.py`, never delegated to an LLM):

| Action class | Autonomy | Why |
|---|---|---|
| **Pause / kill a losing variant** | **fully autonomous** | de-risking; only ever *reduces* spend |
| **Reallocate budget *within* the experiment's approved total** (shift ₹ from loser → winner, net-zero) | **fully autonomous** | total spend unchanged; bounded by the approved envelope |
| **Scale a winner UP** but **still within** the approved experiment ceiling | **fully autonomous** | already inside the human-approved cap |
| **Launch the batch live** / **raise the experiment's total budget ceiling** (net-NEW external spend) | **APPROVAL GATE** (firewall step-up) | new money leaves the building |

This is "fully autonomous optimization, human-approved spend envelope" — defensible, not hype.

---

## 1. CHOSEN TOOLS + WHY (web-researched 2026-06; ACTIVE, cited; none abandoned)

**Headline decision (settled, do not relitigate):** there is **no production-grade self-hostable
OSS "autonomous creative-ad optimizer"** in 2026 (confirmed again 2026-06-09; the landscape is thin
SDK wrappers / MCP servers / prompt-packs — `meta-ads-kit`, `claude-ads`, `awesome-agentic-advertising`
— none is a money-grade optimizer). So the engine is **COMPOSED**, not adopted:

> **Official spend SDKs (the rails, via `automation-ads.md`) + the platforms' own auto-bidding (the
> real ML, free) + a small DETERMINISTIC multi-armed-bandit / rules optimizer we own (the variant
> selection + reallocation) + the in-house LLM seam (creative text, no new vendor).**

### 1.1 Spend rails — **REUSE `automation-ads.md`'s official SDKs** (do not re-pick)
Meta **`facebook-business`** (v25.x, Marketing API v25, maintained by Meta) and Google
**`google-ads`** (PyPI **31.0.0, 2026-05-13**, monthly cadence, Python ≥3.9, maintained by Google).
**API version is an env knob in that module** (`META_ADS_API_VERSION` ~`v25`, `GOOGLE_ADS_API_VERSION`
≥`v22` mid-2026) because both vendors ship quarterly/monthly and any hardcoded version rots. We do
not duplicate this; we call it. (Sources: §13.)

### 1.2 **YouTube** — it is a **Google Ads video campaign**, NOT a separate API/credential (honest fact)
The brief names "Meta/Google/YouTube". **YouTube ads are bought through the Google Ads API as
`advertising_channel_type = VIDEO` campaigns** (formats: in-stream / in-feed / Shorts / bumper),
served on YouTube. There is **no separate "YouTube Ads API" and no separate credential** — the same
`google-ads` client + the same Google Ads developer token + the same billing account. (The *YouTube
Data API v3* is a different thing — it manages channel content/uploads, not paid ads — and is **out
of scope** here; it belongs to `automation-video.md` if/when organic uploads are added.) So in our
model **"YouTube" is a `platform` value that maps to `google` with `channel=VIDEO`** (§4.1). State
this to the founder so they are NOT told to get a "YouTube Ads API key." (Source: §13.)

### 1.3 The variant SELECTOR — **deterministic Thompson-sampling / epsilon-greedy bandit + rules**, we own it
Multi-variant test→scale→kill IS a **multi-armed-bandit** problem, and the honest engineering choice
is a **small deterministic bandit we own**, not a heavyweight OSS framework:
- **Why not a framework:** the live ad platforms *already run the within-campaign ML* (Meta
  Advantage+ / Google Smart Bidding optimize *delivery* inside each variant for free, better than we
  could). Our job is the **cross-variant** decision: which variants get more budget, which die. That
  is ~150 lines of explainable, auditable, **offline-testable** bandit math (Thompson sampling on a
  Beta posterior over each variant's conversion rate, with an **epsilon-greedy floor** so every arm
  keeps a minimum test budget until it reaches statistical sufficiency). No black box decides spend.
- **Statistical-significance guard (anti-hype, load-bearing):** a variant is only declared
  winner/loser once it clears a **minimum-sample gate** (impressions ≥ `MIN_IMPRESSIONS`,
  conversions ≥ `MIN_CONVERSIONS`, default 15 — same min-sample discipline as `automation-ads.md`'s
  CPL breaker). Below the gate, the bandit only **explores** (keeps small equal budgets); it never
  kills on noise. This is the difference between a real optimizer and a coin-flip.
- **Libraries:** uses only `random` + arithmetic in the offline core (zero deps, deterministic with a
  seed for the test). `numpy`/`scipy` are an **optional** accelerator imported defensively
  (`try/except → None`), never required — the pure-Python path is the source of truth.
- **Sources:** standard contextual-bandit / Thompson-sampling literature for ad allocation; the
  platforms' own auto-bidding docs (Meta Advantage+, Google Smart Bidding). (§13.)

> **GRANULARITY HONESTY — variant = ADSET (not micro-campaign), and the CBO collision (load-bearing).**
> The naive "1 variant = 1 micro-budget *campaign*" makes a 25-arm batch into 25 tiny campaigns that
> **fight the platform**: each campaign/adset needs ~50 conversions/week to exit the **learning phase**,
> and micro-budgets fragment delivery. Worse, **Meta CBO / Advantage+ already reallocates budget
> *across adsets within one campaign*** — so a cross-*campaign* bandit partly **collides** with the
> platform's own reallocation. Therefore: a `campaign_ref` in our model **resolves to an ADSET under
> ONE parent campaign** where the platform supports it (the reused `AdProvider` budget verb operates
> at whichever level the adapter targets; conventional multi-variant testing is **adset-level**). And
> the carve-out above is restated honestly: **the platform optimizes delivery + intra-campaign budget;
> our bandit's durable edge is the cross-arm KILL / PROMOTE decision and a VALUE-based reward (ROAS),
> not out-reallocating CBO.** Running many micro-budget arms keeps each in the learning phase — so the
> bandit's significance gate (below) is what makes the decisions sound, not the budget-splitting itself.
> (Also flagged in §12 REAL-vs-HYPE.)

### 1.4 Creative text & the BATCH — **REUSE the in-house LLM seam + media-gen modules; NO new vendor**
Ad copy / hooks / landing headlines / WhatsApp angles come from the existing **in-house `llm-router`
HTTP service** (`LLM_ROUTER_URL`, default `http://llm-router:8111`, batch endpoint
`POST /v1/llm/generate`) via an **injected callable** — same decision as `automation-ads.md` FIX 3
and `automation-marketing.md` §1.5. Banners/images come from `automation-image.md`; videos from
`automation-video.md`; 3D from `automation-threed.md`. **This module introduces ZERO new media/LLM
vendor** — it ingests their outputs (§4.2).

### 1.5 The async-media-job pattern — **REUSE the media modules' async jobs; we poll their job ids**
Video/image/3D generation are **async** (minutes-long vendor jobs). Those modules already define the
job pattern (submit → `job_id` → poll/callback → asset lands in `var/creatives/`). We do **not**
re-invent it; the batch-ingestion seam (§4.2) accepts **either** a ready asset list **or** a list of
**pending `job_id`s** and our `batch.poll()` resolves them to assets before a variant goes live. A
variant whose asset is still rendering stays in `status:"awaiting_asset"` and never launches. (§5.1)

---

## 2. ARCHITECTURE & PACKAGE LAYOUT (all NEW under `droplet_work/creative/`)

### 2.1 The cross-module seams (interface-not-path dependencies — the decoupling that keeps us offline-safe)

```
creative/ads_link.py     -> resolves the SPEND layer:
                            1) automation.ads.providers.get_provider(name)  [if built]
                            2) injected provider                            [offline test]
                            3) built-in FakeAdProvider / NoopAdProvider      [default / dormant]
                            Exposes the SAME AdProvider verbs automation-ads.md defines:
                              create_campaign(plan, paused=True) / set_budget(ref, daily_minor, lifetime_minor)
                              / set_status(ref, "ACTIVE"|"PAUSED") / insights(ref, window) -> MetricsSnapshot
                            We CALL automation-ads.md's poll_and_enforce breaker as our Layer-2 cap
                            guard; we never re-implement caps/breaker.

creative/batch_link.py   -> resolves the BATCH source:
                            1) automation.image/video/... generate()/poll() [if built]
                            2) caller-supplied asset list / job-id list     [API / test]
                            3) deterministic fake assets                     [offline test]

creative/spine_link.py   -> resolves the REVENUE-CONNECTION (read-only + handoff), NEVER imports caller.py:
                            - leads/CRM/analytics reads via authenticated localhost loopback
                              (http://127.0.0.1:<port>/leads|/stats|/analytics) using AIMANAGER-style
                              AIMANAGER_SERVICE_TOKEN (a real admin/manager tenant token, dormant-until-set)
                            - downstream voice/WhatsApp via a HANDOFF JSONL the spine drains later
                              (no direct caller.py import; identical to marketing voice_bridge posture)
```

All three resolvers are **import-safe, never raise, and fall back to fake/dormant** so `creative/`
imports cleanly and the offline test runs with **zero network** whether or not any sibling exists.

### 2.2 On-disk reuse seams (VERIFIED 2026-06-09 — a build agent codes against these real symbols)

| Reuse | Symbol (verified) | Use |
|---|---|---|
| Dormancy pattern | `whatsapp.py` `_cfg()` / `is_configured()` / returns `{"status":"not_configured"}` / `# noqa: BLE001` never-raises / lazy `httpx` | copy shape for every adapter |
| Immutable audit | `audit.record(actor, action, object_type, object_id, …, meta=)` (L60), `audit.tail(limit, action_prefix=)` (L102), `audit.init(path)` (L36) — append-only JSONL, never raises | write `creative.*` actions; read for the sub-page |
| Config resolver | `config.get(key, default)` (L100), `config.require(key)` (L107), `config.source()` (L118) — Doppler-over-env | read all knobs (so a later `.env` paste works) |
| Secret hygiene | `vendors.redact(secret)` (first/last-4), `vendors.DISPLAY_NAMES` | redact every key in logs |
| Approval primitive | `auth.issue_pair(tenant)` (L128) + `auth._VERIFY_PASSWORD(email,password)` (L46/179) | mint/verify the firewall step-up token (§6.2) — same as `automation-ads.md` FIX 1 ("build on auth.py", there is **no** `firewall.py`) |

### 2.3 Directory tree (NEW; nothing outside `droplet_work/creative/`)

```
droplet_work/creative/
  __init__.py                 # import-safe with empty env; exports the public surface
  README.md                   # what it does, cred list, how to run the offline test
  config.py                   # env reads + *_configured() gates (whatsapp.py style)
  ads_link.py                 # SPEND-layer resolver (automation.ads | injected | fake/noop) — §2.1
  batch_link.py               # BATCH-source resolver (media-gen | supplied | fake) — §2.1, §4.2
  spine_link.py               # revenue-connection resolver (loopback reads + handoff JSONL) — §7
  experiment.py               # Experiment / Variant data model + lifecycle (§4) — the NET-NEW core state
  ingest.py                   # batch -> ad-variant plan (1 asset = 1 variant); resolves async job ids
  optimizer.py                # THE LOOP: bandit selection + scale/kill/reallocate (§5) — the core
  bandit.py                   # deterministic Thompson/epsilon-greedy + significance gate (pure, seeded)
  guardrails.py               # 3-tier autonomy, HARD caps, approval gate, kill-switch (§0.3, §6)
  metrics.py                  # pull per-variant MetricsSnapshot via ads_link; normalize (reuses ads shape)
  attribution.py              # ad -> lead -> CRM -> conversion stitching (§7) + ROI/ROAS rollup
  meter.py                    # spend estimate (estimated:True, groq_meter style)
  store.py                    # JSONL/JSON state under var/creative/ (atomic write/append)
  service.py                  # ORCHESTRATION facade: the pure callables the spine wires later (§3)
  endpoints.py                # FastAPI APIRouter — DEFINED here, MOUNTED later by the spine (deferred)
  tests/
    __init__.py
    test_creative_ads_offline.py   # ZERO-network acceptance test (§10)
```

**Import safety & packaging (PINNED — matches the spine's flat `droplet_work/`-as-root convention,
verified against `caller.py` imports in the sibling specs):** reach spine deps by **bare name**
(`import audit`, `from config import get`, `from auth import issue_pair`); reach the ad sibling by
its top-level package name **inside a `try/except`** (`try: from automation.ads.providers import
get_provider except Exception: get_provider = None`). Run the test (cwd = `droplet_work/`) as
`python -m creative.tests.test_creative_ads_offline`; the test self-inserts `droplet_work/` on
`sys.path` so it runs from any cwd. No module-level network, no `require()` at import.

---

## 3. PUBLIC INTERFACE — `service.py` (the pure callables the spine wires later)

`status` vocabulary (extends `automation-ads.md`'s):
`not_configured | draft | awaiting_asset | pending_approval | running | optimizing | scaled |
killed | reallocated | paused | completed | blocked_cap_exceeded | blocked_not_approved |
blocked_no_conversion_tracking | dry_run | error:<...>`

```python
def propose_experiment(tenant_id: str, dropdown_selection: dict, *, llm=None,
                       batch=None, provider=None) -> dict
    # dropdown_selection: {"product_id"|"campaign_id", "platforms":["meta","google","youtube"],
    #                      "test_budget_total_minor": int, "objective": "leads"|"sales"|...}
    # 1) batch_link.fetch(selection) -> assets (or pending job_ids)  [media-gen | supplied | fake]
    # 2) ingest.plan() -> one VARIANT per asset (banner/video/hook/landing/WA angle)
    # 3) persist an Experiment at status="pending_approval" (or "awaiting_asset" if jobs pending)
    # NEVER touches a platform. Pure + offline-safe. Audited (creative.experiment.propose).

def approve_experiment(tenant_id: str, experiment_id: str, actor: str, stepup_token: str) -> dict
    # Firewall step-up gate (Inv B / §6.2). On success: for each ready variant ->
    # provider.create_campaign(paused=True) -> set_budget(daily<=per-variant test cap) -> ACTIVE.
    # Honors dry_run/not_configured. Audited (creative.experiment.approve).

def optimize(tenant_id: str, experiment_id: str = "", *, now=None, provider=None,
             dry_run=False) -> dict
    # THE CORE LOOP (§5). For each running experiment: pull per-variant metrics ->
    # call automation-ads.md poll_and_enforce (cap/CPL breaker, Layer 2) ->
    # bandit.decide() -> apply AUTONOMOUS actions (kill loser / reallocate / scale-within-cap);
    # PARK any net-NEW-spend action for approval. Deterministic; injectable metrics. Audited.
    # dry_run=True returns the action plan WITHOUT mutating (preview + offline test).

def experiment_status(tenant_id: str, experiment_id: str = "") -> dict
    # experiments + per-variant spend/CTR/CPC/CPL/conversions/ROAS + budget vs cap + flags + winners.

def pause_all(tenant_id: str, reason: str) -> dict   # kill switch — pauses every variant
def attribution_rollup(tenant_id: str, experiment_id: str = "") -> dict  # ad->lead->CRM->ROI (§7)
```

All have `_async` twins where the spine loop calls them. `llm`, `batch`, `provider`, `now`, and the
store read/write fns are **injected** (default to real impls) so the offline test runs with fakes and
**zero network**.

---

## 4. DATA MODEL (NET-NEW — the variant/experiment store; files under `var/creative/`, JSON/JSONL)

### 4.1 `Experiment` + `Variant` (`var/creative/experiments.json`) — the core state this module owns
```json
{
  "experiment_id": "ex_<ulid>",
  "tenant_id": "<org>",
  "source": {"kind": "product|campaign", "ref_id": "<id>", "selection": {...}},
  "objective": "leads|sales|traffic|engagement",
  "platforms": ["meta", "google", "youtube"],
  "approved_budget_total_minor": 500000,     // the human-approved ENVELOPE (the autonomy ceiling)
  "test_budget_per_variant_minor": 20000,    // small per-variant launch budget
  "status": "pending_approval|awaiting_asset|running|optimizing|completed|paused|killed",
  "created_ts": "...", "approved_by": "", "approved_ts": "",
  "variants": [
    {
      "variant_id": "vr_<ulid>",
      "asset": {"kind": "banner|video|hook|landing|wa_angle|threed",
                "asset_id": "<creative job_id/path/url>", "job_id": "<pending media job|null>",
                "text": "<copy/hook/headline if textual>"},
      "platform": "meta|google|youtube",       // youtube => google adapter, channel=VIDEO (§1.2)
      "channel": "feed|search|video|...",
      "campaign_ref": "<platform id|null>",     // set after create_campaign
      "status": "awaiting_asset|pending|active|paused|killed|scaled|winner|loser",
      "budget_minor": 20000,
      "metrics": { /* latest MetricsSnapshot, §4.3 */ },
      "bandit": {"alpha": 1, "beta": 1, "score": 0.0, "samples": 0}  // Beta posterior state
    }
  ]
}
```

### 4.2 Batch-ingestion contract (`ingest.py` + `batch_link.py`) — how a BATCH becomes variants
`batch_link.fetch(selection)` returns a list of **AssetRefs**, each either **ready**
(`{kind, asset_id, url|path, text}`) or **pending** (`{kind, job_id}` for an async media job, §1.5).
`ingest.plan(experiment, assets)` maps **1 asset → 1 Variant** (a 10-banner / 5-video / 10-hook batch
⇒ up to 25 variants, distributed across the selected platforms by `asset.kind`→`channel`). Pending
assets create variants at `status:"awaiting_asset"`; `batch.poll()` (called by `optimize`) resolves
finished `job_id`s to assets and flips them to `pending` (launch-ready). **A variant never launches
until its asset is real.**

### 4.3 `MetricsSnapshot` (the BASE shape is reused from `automation-ads.md`; the rest is DERIVED/enriched in `metrics.py`)
```python
{"provider","campaign_ref","window","spend_minor":int,"impressions":int,"clicks":int,
 "conversions":int,"cpl_minor":int|None,"ctr":float,"cpc_minor":int|None,
 "revenue_minor":int|None,"roas":float|None,"currency":"INR","fetched_ts"}
```
> **Provenance (so a build agent does NOT wait forever for fields the ad adapter never emits):** the
> **base** fields (`spend_minor`, `impressions`, `clicks`, `conversions`, `cpl_minor`) come straight
> from `ads_link.insights()` (the reused `automation-ads.md` adapter shape). The **extras** are
> produced by **`metrics.py`**, not the ad adapter: `ctr` = `clicks/impressions` and `cpc_minor` =
> `spend_minor/clicks` are **derived** (free, always available); `revenue_minor`/`roas` are
> **enriched** only when **conversion-VALUE tracking** exists (Meta purchase/value events or a Google
> value-based conversion action) — neither sibling adapter fetches value by default, so `metrics.py`
> reads it from the value-bearing insight field when present and leaves it `None` otherwise.

`cpl_minor=None`/`revenue_minor=None` ⇒ no conversion/value tracking ⇒ ROAS/CPL rules self-disable
(`blocked_no_conversion_tracking`); the bandit falls back to **CTR/CPC** as the reward signal and the
cap-breaker still enforces spend. (Honest: we never fabricate a conversion or a CPL — same discipline
as `automation-ads.md` §1.5.)

### 4.4 `var/creative/` files
`experiments.json` (state, atomic write) · `variant_metrics.jsonl` (append-only per-poll snapshots —
the bandit + audit source) · `decisions.jsonl` (every kill/scale/reallocate with its reason + sample
counts — explainability) · `stepup.json` (single-use approval tokens, short TTL, §6.2) ·
`handoff.jsonl` (downstream voice/WhatsApp hand-offs the spine drains, §7). Append-only logs mirror
`audit.py`'s immutability discipline.

---

## 5. THE OPTIMIZATION LOOP — `optimizer.optimize()` (THE CORE; deterministic; offline-testable)

One tick over a running experiment (a deferred scheduler calls this every `OPT_POLL_MINUTES`,
default 30 — wiring deferred, NOT done here):

```
optimize(tenant, exp, now, provider, dry_run):
  0. KILL-SWITCH: if guardrails.killed(tenant): audit(creative.killswitch); return halted
  1. RESOLVE ASSETS: batch.poll() -> flip any "awaiting_asset" variant whose media job finished to
     launch-ready; (newly-ready variants are launched only via approve_experiment, never here)
  2. MEASURE: for each ACTIVE variant -> ads_link.insights(campaign_ref) -> MetricsSnapshot;
     append to variant_metrics.jsonl. Update each variant's Beta posterior (alpha+=conv,
     beta+=(clicks-conv) or impressions-based) in bandit.py.
  3. CAP-BREAKER (Layer 2, REUSED): call automation-ads.md poll_and_enforce(tenant) -> it pauses any
     variant breaching the hard daily/lifetime cap or CPL (min-sample met). We do NOT re-implement
     this; we consume its actions and record them.
  4. SIGNIFICANCE GATE: a variant is eligible for win/lose judgement ONLY if
     samples >= MIN_CONVERSIONS (def 15) AND impressions >= MIN_IMPRESSIONS. Below the gate ->
     keep exploring (equal small budgets); NEVER kill on noise.
  5. BANDIT DECIDE (bandit.decide(variants)) -> for eligible variants:
       - LOSER  (posterior clearly below the field / CPL above max / CTR in bottom band):
             AUTONOMOUS -> set_status(PAUSED) -> status="killed"  (de-risking; reduces spend)
       - WINNER (posterior clearly best, ROAS/CPL strong):
             desired_budget = clamp(scale_factor * current, <= per-variant cap,
                                    SUBJECT TO experiment envelope headroom)
             if desired increases NET experiment spend ABOVE approved envelope -> PARK for approval
             else AUTONOMOUS -> set_budget(winner, desired)  (scale within approved ceiling)
       - REALLOCATE: budget freed by killed losers is redistributed to winners by Thompson weight,
             NET-ZERO against the approved envelope -> AUTONOMOUS set_budget calls.
  6. RECORD: every action -> decisions.jsonl {variant, action, reason, samples, before/after budget}
     + audit.record(creative.optimize.<action>) + guardrails.record_spend (atomic, §6.1).
  7. RETURN {experiment_id, measured, killed:[...], scaled:[...], reallocated:[...],
             parked_for_approval:[...], spend_today_minor, headroom_minor}
  (dry_run=True: run 0-5, compute 7's plan, apply NOTHING — preview + the offline test path.)
```

**Safety properties baked in (mirrors aimanager §6):** measure before mutate; the significance gate
prevents killing on noise; reallocation is net-zero against the approved envelope; **scale-UP past the
envelope is the ONLY path that needs approval and it is gated deterministically in code**, not by the
bandit; every action is idempotent by `(experiment_id, variant_id, tick)`; a failed money action
halts the rest of that experiment's money actions (fail-safe); the kill-switch short-circuits at
step 0 and is re-checked before each `set_budget` increase.

---

## 6. SPEND / APPROVAL / AUDIT GUARDRAILS — the spine (defense-in-depth; the highest-risk surface)

External ad budget is **real, irreversible money paid to third parties.** The guardrail stack is
designed before the "AI runs ads" layer. **Three of these are REUSED from `automation-ads.md`; the
NET-NEW piece is the per-experiment ENVELOPE + the 3-tier autonomy gate.**

| Layer | Mechanism | Owner | Default |
|---|---|---|---|
| **L0 — nothing spends** | `CREATIVE_DRY_RUN=1` + ad provider `not_configured` (double lock) | this module | ON |
| **L1 — platform daily budget (the REAL floor)** | platform daily budget set ≤ cap at `create_campaign` | `automation-ads.md` | enforced on activate |
| **L2 — polling cap/CPL breaker** | `automation-ads.md` `poll_and_enforce` pauses on snapshot ≥ cap or CPL breach (min-sample) | `automation-ads.md` | every 30 min |
| **L3 — per-experiment ENVELOPE** | `approved_budget_total_minor`; the loop can reallocate/scale only WITHIN it; exceeding it parks for approval | **NET-NEW (this module)** | required |
| **L4 — approval gate (Inv B)** | firewall step-up (§6.2) on `approve_experiment` AND on any net-NEW-spend optimize action | this module (built on `auth.py`) | required |
| **L5 — immutable audit (Inv C)** | `audit.record(creative.*)` on every propose/approve/kill/scale/reallocate/cap-block | reuse `audit.py` | always |
| **L6 — kill switch** | `pause_all(tenant)` / `CREATIVE_KILLSWITCH=1` pauses every variant | this module | OFF (available) |

### 6.1 The money cap is an ATOMIC decrement (REUSE aimanager's fix — do NOT ship JSONL-only)
The spend envelope's "remaining" is the money path, so it **must** have a single-writer guarantee
(a cron tick + a manual optimize could both read `remaining` and both authorize — the exact
double-authorize aimanager §7.1/FIX 4 calls out). **Use the spine's Postgres atomic decrement**
`UPDATE … SET remaining = remaining - :amt WHERE experiment_id=:e AND remaining >= :amt RETURNING
remaining` inside one transaction (the spine is Postgres-backed). If Postgres is unavailable, the
cap check **FAILS CLOSED** (treat remaining=0, park for approval) rather than trusting a non-atomic
file. The JSONL store holds the *narrative* (decisions/metrics/audit), never the authority for
"remaining spend." The check-and-debit + kill-switch read are ONE critical section.

### 6.2 The approval gate primitive (BUILD on `auth.py` — there is NO `firewall.py`)
Same correction as `automation-ads.md` FIX 1: there is no `firewall.py` / step-up mechanism in the
repo. `guardrails.require_approval(tenant_id, experiment_id, actor, stepup_token)` verifies a
**fresh single-use step-up token** minted by re-checking the manager's password via `auth`'s
`_VERIFY_PASSWORD` (or requiring a JWT with `role=="manager"`/`is_admin` whose `iat` is < N minutes
old). Token stored in `var/creative/stepup.json` (single-use, short TTL, bound to `(actor,
experiment_id)`). Import-safe, offline-testable with a fake verifier.

### 6.3 HONEST residual-overshoot statement (REUSED verbatim from `automation-ads.md` §5.5 — keep loud)
> The platform **daily budget** (L1) is the real cap. Our polling breaker (L2) + envelope (L3) are
> additional lines of defense, and because they poll on an interval there is a **latency window
> between polls in which spend can overshoot the breaker's view** (the platform's own daily budget
> still bounds it). This **reduces** overshoot risk and adds per-variant + envelope protection the
> platform budget alone does not; it is **not** a to-the-cent guarantee. Anyone who tells you a
> polling optimizer guarantees the cap to the rupee is selling hype.

---

## 7. HOW IT CONNECTS — ads → leads → CRM → voice → WhatsApp → analytics (the revenue loop)

Everything is **revenue-connected**, but the connection is a **seam, not a `caller.py` edit**
(`spine_link.py`, §2.1).

- **ads → leads:** a launched variant carries a tracking tag (`utm`/Meta lead-form id / Google
  conversion action). Inbound leads already land in the spine (`/leads`, `/webhooks`). `attribution.py`
  **reads** leads via the loopback (`GET /leads`, `GET /analytics`) and **stitches** lead →
  `experiment_id`/`variant_id` by the tracking tag → builds the per-variant **conversion + ROAS**
  signal that feeds the bandit's reward (§4.3). No new lead store; we read the spine's.
- **leads → CRM → voice:** when a variant produces a hot lead, `creative` writes a **hand-off row**
  to `var/creative/handoff.jsonl` (`{action:"enqueue_call"|"whatsapp", lead_id, experiment_id,
  variant_id, template}`); the spine's existing dialer/WhatsApp path drains it later (deferred
  wiring; identical posture to `automation-marketing.md`'s `voice_bridge`/`wa_bridge` — NO direct
  `caller.py`/`agent.py` import).
- **→ WhatsApp:** WhatsApp creative *angles* are variants too; sends go through the existing
  **`whatsapp.send_whatsapp`** (already provider-agnostic + dormant) via `spine_link`, never a new
  WhatsApp client.
- **→ analytics:** `experiment_status` + `attribution_rollup` expose per-variant CTR/CPC/CPL/ROAS +
  the winner/loser ledger; the sub-page (§8) renders it; `audit.tail(action_prefix="creative")` gives
  the immutable decision history. Image/ad spend is metered into the **same `usage_events`** stream
  the other meters use (`meter.py`, `estimated:True`) so it shows up in the existing Billing UI.

**Honest dependency:** ad→revenue attribution is only as real as the founder's conversion tracking
(Meta Pixel+CAPI / Google conversion action). Absent it, the loop optimizes on **CTR/CPC**
(engagement) and reports `blocked_no_conversion_tracking` for ROAS — it never invents revenue.

---

## 8. THE CREATIVE-STUDIO SUB-PAGE THIS POWERS

Creative Studio is a **sidebar SECTION** following the **Billing multi-page pattern** (verified in
`famit-panel/contstants/navigation.tsx`: `Billing` is a sidebar **dropdown group** whose children
are routes `/billing/{overview,vendors,explorer,audit,plan}` with a shared `_shared.tsx`). Creative
Studio mirrors this exactly: a `Creative Studio` dropdown group with children under
`/creative-studio/` — e.g. `studio` (the dropdown → batch generator), `gallery` (generated assets),
**`autonomous-ads`** (THIS module), `landing` (pages), `analytics` (revenue rollup).

> **This module powers the `Creative Studio → Autonomous Ads` sub-page** (`/creative-studio/autonomous-ads`).
> It renders: the **dropdown** (product/campaign select + platforms + test budget) → a **batch
> preview** (variants to launch) → an **APPROVE button** (firewall step-up) → and the live
> **experiment board**: per-variant CTR/CPC/CPL/ROAS/spend, the **winner/loser/scaling** status,
> the autonomous **decision log** (why each variant was killed/scaled/reallocated), spend-vs-envelope
> bars, and the **kill-switch**. It is backed entirely by the §3 `service.py` callables exposed via
> the §9 endpoints. (Backend spec only — the frontend page is a separate UI unit; this doc names and
> contracts it, it does not build it.)

---

## 9. ENDPOINTS (DEFINED here, MOUNTED later by the orchestrator — DO NOT edit `caller.py`)

`router = APIRouter(prefix="/creative/ads", tags=["creative-ads"])`, `manager`-scoped except reads.
`endpoints.py` guards `try: from fastapi import APIRouter except Exception: router = None` so the
package imports cleanly without FastAPI.

| Method/Path | → service fn | Auth |
|---|---|---|
| `POST /creative/ads/experiments/propose` | `propose_experiment` | manager |
| `GET  /creative/ads/experiments` / `/{id}` | `experiment_status` | manager (read) |
| `POST /creative/ads/experiments/{id}/approve` (step-up) | `approve_experiment` | manager/admin |
| `POST /creative/ads/experiments/{id}/optimize` (dry_run default off via flag) | `optimize` | manager/admin |
| `POST /creative/ads/experiments/{id}/pause` | `pause_all` (scoped) | manager |
| `GET  /creative/ads/experiments/{id}/attribution` | `attribution_rollup` | manager (read) |
| `GET  /creative/ads/health` | provider/seam `status()` map | public (read) |

Docstring wiring note (deferred): the spine will `app.include_router(router)` and add a
`scheduler_loop` tick calling `optimize` every `OPT_POLL_MINUTES` — **NOT done here**.

---

## 10. OFFLINE ACCEPTANCE TEST (`tests/test_creative_ads_offline.py` — ZERO network)

Run (cwd `droplet_work/`): `python -m creative.tests.test_creative_ads_offline` or
`pytest droplet_work/creative/tests/ -q`. With an **empty env**, monkeypatching `httpx`/SDKs to a
sentinel that raises if called (proves zero network while dormant), it asserts:

1. **Import-safe & dormant:** `import creative`; `status()=="not_configured"`; `ads_link` resolves to
   the `fake`/`noop` provider; `propose_experiment` / `approve_experiment` / `optimize` /
   `experiment_status` each return a `status` in `{not_configured, dry_run, awaiting_asset}`, raise
   nothing, and make **no** network call.
2. **Batch → variants (no media-gen built):** with `batch_link` supplied a fake asset list
   (3 banners + 2 videos + 5 hooks), `propose_experiment` creates **10 variants** with the correct
   `platform`/`channel` mapping; a pending `job_id` asset yields a `status:"awaiting_asset"` variant
   that does **not** launch.
3. **YouTube mapping:** a variant with `platform:"youtube"` resolves to the `google` adapter with
   `channel:"video"` (§1.2) — asserts no "youtube" provider is ever requested.
4. **Approval gate:** `approve_experiment` with missing/invalid step-up token → `blocked_not_approved`,
   provider `create_campaign` **never called**; with a valid fake token → provider called
   `paused=True` then `ACTIVE` per ready variant.
5. **Significance gate (anti-noise):** inject variants with `conversions=3` → `optimize` kills **none**
   (keeps exploring); with `conversions>=15` and a clearly losing posterior → that variant is
   `killed` (`set_status(PAUSED)` recorded). The min-sample honesty test.
6. **Bandit reallocation is net-zero:** kill one loser (budget X freed) → assert the freed X is
   redistributed to winners and `sum(variant budgets)` is **unchanged** (≤ approved envelope).
7. **Scale-up gating (the autonomy/approval reconciliation):** a winner whose desired scale-up stays
   **within** the envelope → applied **autonomously** (no approval); a scale-up that would exceed the
   envelope → **parked** `pending_approval`, `set_budget` for the excess **never called**. (§0.3/§5.5)
8. **Cap-breaker delegation:** with a fake `poll_and_enforce` recording calls, a variant snapshot
   `spend>=cap` → assert the breaker is invoked and its PAUSE is reflected (we don't re-implement it).
9. **No-conversion-tracking fallback:** all snapshots `cpl_minor=None`/`revenue_minor=None` →
   `attribution_rollup`/ROAS rules report `blocked_no_conversion_tracking`; the bandit still optimizes
   on CTR and the cap-breaker still runs.
10. **Idempotency & kill-switch:** re-running the same `optimize` tick produces no duplicate
    `decisions`/budget mutations; `CREATIVE_KILLSWITCH=1` → `optimize` returns `halted`, zero adapter
    calls.
11. **Audit & meter:** every propose/approve/kill/scale writes a `creative.*` row via an injected fake
    audit sink; a (dry) paid step writes a `usage_events` row `vendor=="image|ads"` with `estimated:True`.
12. **Never-raises fuzz:** malformed selections (empty batch, `n=999`, bad platform, non-dict) each
    return an `error:`/`invalid` dict, no exception.

Exit non-zero on any failure (orchestrator-gateable).

---

## 11. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

> **The module builds and passes its offline test with NONE of these (dormant-until-creds).** All
> blank ⇒ graceful NO-OP, nothing spends. Paste into `/opt/famit-agent/.env` (or Doppler) and
> restart — no code change. **⏳ = real, multi-day, founder-side lead time (the valuable part).**

### 11.1 Ad spend — **same creds as `automation-ads.md` / `automation-aimanager.md`** (do NOT re-issue)
This module **reuses the ad sibling's credentials**; it does not define its own ad-platform keys.
- **Meta:** `META_ADS_APP_ID`/`SECRET`, `META_ADS_ACCESS_TOKEN` (System-User token w/ `ads_management`,
  `ads_read`, `business_management`), `META_ADS_ACCOUNT_ID`, `META_ADS_PAGE_ID`, `META_PIXEL_ID` +
  `META_CAPI_TOKEN` (⏳ for conversion/ROAS tracking — CAPI only; offline-conversions API dead
  2025-05-14), `META_ADS_API_VERSION` (~`v25`). On-platform: **Business Verification + Advanced-Access
  App Review** (⏳⏳ multi-day) + **payment method on the ad account**.
- **Google (covers YouTube/VIDEO too — §1.2):** `GOOGLE_ADS_DEVELOPER_TOKEN` (⏳⏳ approval),
  `GOOGLE_ADS_CLIENT_ID`/`SECRET`, `GOOGLE_ADS_REFRESH_TOKEN` (⚠️ **2FA required** on the owning
  Google account to mint/use after 2026-04-21), `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (MCC),
  `GOOGLE_ADS_CUSTOMER_ID`, `GOOGLE_ADS_API_VERSION` (≥`v22`). On-platform: a **conversion action**
  (⏳ for CPL/ROAS) + **billing set up**. **No separate YouTube key.**

### 11.2 Creative BATCH — **same creds as the media-gen modules** (reused, not re-issued)
Images: `IDEOGRAM_API_KEY` / `RECRAFT_API_KEY` / `OPENAI_API_KEY` (Hindi) / FLUX (`FAL_KEY` |
`REPLICATE_API_TOKEN` | `BFL_API_KEY`) — per `automation-image.md`. Video/3D per `automation-video.md`
/ `automation-threed.md`. Ad copy/hooks: the in-house LLM seam (`LLM_ROUTER_URL`) — **no new key.**
With none set, `batch_link` runs on caller-supplied or `fake` assets (dormant).

### 11.3 Revenue connection
`AIMANAGER_SERVICE_TOKEN` — a real **admin/manager tenant access token** minted via `auth.issue_pair()`
(server-side only, never logged/committed) so `spine_link` can read `/leads`/`/analytics` over the
authenticated loopback. Dormant-until-set; absent ⇒ attribution runs on injected/fake data and the
sub-page shows "connect to enable revenue attribution."

### 11.4 Module flags (founder-tunable, safe defaults)
`CREATIVE_DRY_RUN=1` (default — nothing spends), `CREATIVE_KILLSWITCH=0`,
`CREATIVE_REQUIRE_APPROVAL=1` (default — launch & scale-up gated), `OPT_POLL_MINUTES=30`,
`MIN_CONVERSIONS=15`, `MIN_IMPRESSIONS` (e.g. 1000), `TEST_BUDGET_PER_VARIANT_MINOR`,
`CREATIVE_SCALE_FACTOR` (e.g. 1.5), `CREATIVE_ENVELOPE_DEFAULT_MINOR`, plus the reused ad caps
(`ADS_DAILY_CAP_MINOR`, `ADS_LIFETIME_CAP_MINOR`, `ADS_CPL_MAX_MINOR`, `ADS_ORG_DAILY_CAP_MINOR`).

---

## 12. HONEST REAL-vs-HYPE

| Claim | Reality |
|---|---|
| "AI runs ads fully autonomously" | **Within a human-approved, hard-capped envelope, yes** (kill/reallocate/scale-within-cap are autonomous); **net-NEW spend is human-approved** (§0.3). "Fully autonomous, unbounded spend" is hype we explicitly do **not** ship. |
| "AI auto-generates the whole creative batch" | The batch is produced by the media-gen modules (Ideogram/FLUX/etc.) — **draft quality**, routed per job; **a human still approves** the launch. It's a draft/variation engine, not a fire-and-forget art director. |
| "It out-optimizes Meta/Google" | **No.** The within-campaign ML is the platforms' auto-bidding (free, better than ours). We own only the **cross-variant** budget decision (a deterministic bandit) — explainable + auditable, not a black box. |
| "Spin up 25 micro-budget arms and let the bandit reallocate" | Half-true: **Meta CBO / Advantage+ already reallocates across adsets in one campaign**, and micro-budgets keep each arm in the platform **learning phase** (~50 conv/wk to exit). So variants are modeled as **adsets under one campaign**, and the bandit's durable edge is the cross-arm **kill/promote** decision + **ROAS-based** reward, **not** out-reallocating CBO (§1.3). |
| "Auto-scale/kill is instant & exact" | Polling-interval based; the platform daily budget is the real floor; an inter-poll overshoot window exists (§6.3). We reduce risk + add per-variant/envelope control; we do not guarantee the cap to the rupee. |
| "ROI/ROAS optimization out of the box" | Only as real as the founder's Pixel+CAPI / conversion action. Absent it, we optimize on **CTR/CPC** and report `blocked_no_conversion_tracking` — we never fabricate revenue. |
| "Statistically sound winners" | Guarded: no variant is killed/scaled until it clears the **min-sample significance gate** (§1.3/§5.4) — never on 3 clicks. |
| "Plug-and-play" | **Lead time is real:** Google developer-token + 2FA, Meta Advanced-Access + Business Verification, conversion tracking setup, and ad-account billing are all multi-day, founder-side, and gate go-live. |
| "Works offline" | The loop, gates, bandit, attribution stitching, audit, and idempotency are pure logic and fully offline-tested; reasoning/spend quality needs the real keys — the **safety machinery does not**. |

---

## 13. BUILD ORDER (one verifiable UNIT each; test after every unit)

1. `config.py` + `store.py` + `ads_link.py`/`batch_link.py`/`spine_link.py` resolvers (fake/noop
   fallbacks) + package skeleton → **import-safe, dormant; test §10.1**.
2. `experiment.py` (data model) + `ingest.py` (batch→variants, async job ids) → **test §10.2-10.3**.
3. `bandit.py` (pure Thompson/epsilon + significance gate, seeded) → **unit-test §10.5-10.6 in isolation**.
4. `guardrails.py` (3-tier autonomy, envelope, Postgres atomic decrement, step-up on `auth.py`,
   kill-switch) → **test §10.7, §10.10**.
5. `metrics.py` + `optimizer.optimize` (the loop) wired to injected fake provider + metrics →
   **the core loop test §10.5-10.10**.
6. `service.propose_experiment` + `approve_experiment` (step-up) → **test §10.4**.
7. `attribution.py` + `meter.py` + `spine_link` handoff → **test §10.9, §10.11; §7 seam**.
8. `endpoints.py` (router DEFINED, FastAPI-guarded, NOT mounted) + `__init__.py` exports + full
   `test_creative_ads_offline.py` green. **Gate.**
9. Document the deferred spine seams (router mount + scheduler tick + handoff drain) in `endpoints.py`
   docstring — **do not touch `caller.py`/`agent.py`**.

Ship 1–5 first: that delivers the entire NET-NEW safety + optimization spine, fully tested, with no
external dependency and no dependency on whether the ad/media siblings are built yet.

---

## RED-TEAM FIXES (folded)

Adversarial review 2026-06-09. On-disk seams, ToS posture, async pattern, dormancy, and real-vs-hype
re-checked against `droplet_work/` and the sibling specs. **Verdict: GO.** The reuse contract,
dormant-until-creds posture, 3-tier autonomy/approval reconciliation, and defense-in-depth spend
stack are sound and verified. The following corrections are folded; none changes the architecture.

### FIX A — Autonomous ad spend IS ToS-permitted; frame the approval gate as the CONTENT-policy firewall (was unstated)
Programmatic budget/bid/campaign management via the **official Meta Marketing API + Google Ads API**
is **explicitly supported** — it is the core purpose of those APIs, and commercial autobidders
(Revealbot, Smartly, Madgicx) run on them. So the autonomous **kill / reallocate / scale-within-cap**
loop is **ToS-compliant**, not a gray area. The real platform-*policy* exposure is **not** the
bidding — it is **ad-content review of AI-generated creative** (Meta Advertising Standards / Google
Ads policies on misleading or low-quality creative). **That risk is exactly what the human
launch-approval gate (§0.3 tier-4, `approve_experiment`, L4) firewalls:** no AI-generated variant
goes live without a manager's step-up approval, so a human is always the last gate before
machine-made creative spends money or faces content review. This connection is now explicit:
**the approval gate is both the net-NEW-spend gate AND the content-policy firewall.** Residual ToS/access
items to list to the founder: Google requires **"standard" (production) developer-token access** —
basic/test access cannot manage arbitrary live accounts (⏳ approval, already in §11.1); and at
**25 variants × 30-min polling** the loop must respect Google Ads / Meta **API rate limits** (the
reused `automation-ads.md` adapter owns backoff; our optimizer must not poll tighter than
`OPT_POLL_MINUTES` and should batch insights calls per account, not per-variant).

### FIX B — 3D is a creative SOURCE, not a native ad format (the missing real-vs-hype row)
The model carries `threed` as a variant `asset.kind` (§4.1) but §12 had **no 3D row**, leaving the
3D claim unbounded. Honest fact: **there is no native interactive-3D ad placement** on Meta or Google
feed / search / video inventory. A `threed` asset is a creative *source* that is **rendered down to a
standard image or video** before it can become an ad variant — it is NOT an interactive 3D ad unit.
So in this engine a 3D asset enters the batch only as a rendered image/video variant; the bandit and
spend rails treat it identically to any other image/video. **We ship no "3D ads" capability and claim
none** — 3D is an upstream `automation-threed.md` render input, nothing more. (Add this as a §12 row
in spirit; stated here to bound the claim.)

### FIX C — On-disk symbol corrections (verified 2026-06-09; build agent must use the REAL signatures)
- **`audit.init`** is `init(audit_file: Path)` — **not** `init(path)` as §2.2 cites. Call it
  `audit.init(Path("var/creative/audit.jsonl"))` (or reuse the spine's already-initialized audit).
- **`auth._VERIFY_PASSWORD`** is at **L62** (the doc cited L46/179; L46 is the *default* lambda
  declaration, L62 is the `init()` assignment). It is an **injected module-global callable that
  defaults to `lambda e,p: None`** and is wired only when **`caller.py` calls `auth.init()`**.
  Implication (load-bearing for the offline test): in a **dormant/standalone `creative/` context
  `auth.init()` has NOT run**, so the global returns `None` for every credential — i.e. **fail-closed**
  (no approval can pass), which is the safe direction. Therefore the step-up verifier in `guardrails.py`
  MUST be an **injected verifier** (default = the real `auth` path *after* the spine wires it), and the
  offline test injects a **fake verifier** — it must **never call `auth._VERIFY_PASSWORD` directly at
  import or in the test**. §6.2 already says "offline-testable with a fake verifier," so this is a
  clarification, not a contradiction; it is now explicit *why* (the global is dormant until `caller.init`).
- All other cited symbols **verified present**: `audit.record`(L60)/`tail`(L102); `config.get`(L100)/
  `require`(L107)/`source`(L118); `auth.issue_pair`(L128); `vendors.redact`(L26)/`DISPLAY_NAMES`(L11);
  `whatsapp.py` `_cfg`(L79)/`is_configured`(L107)/`send_whatsapp`(L241)/`# noqa: BLE001`/`not_configured`.
  The `automation-ads.md` bind targets (`AdProvider`, `get_provider`, `poll_and_enforce`,
  `create_campaign`, `insights`, `MetricsSnapshot`, `require_approval`) all exist in that spec, and its
  FIX 1/2/3 (firewall→`auth.py`, sibling-decoupling, LLM-seam label) are the SAME corrections this
  module inherits — confirmed consistent. The Billing dropdown-group nav pattern (§8) is verified in
  `navigation.tsx` (collapsible parent, no `href`, children under `/billing/`).

### FIX D — Async: assets that finish AFTER approval do not auto-launch (state as a known, safe limitation)
The async-media pattern (§1.5/§4.2) is sound: pending `job_id`s park as `awaiting_asset` and
`batch.poll()` resolves them. One honest boundary, now stated: a slow media job (e.g. a long video
render) that finishes **after** the experiment is already `running` does **not** auto-inject and
auto-launch its variant into the live experiment — `optimize` step-1 only flips it to launch-ready;
**actual launch still requires `approve_experiment`** (a second step-up). This is a deliberate
**safety choice** (no new creative spends without a human gate), not a bug — late assets queue for the
next approval, they never silently go live. The offline test §10.2's `awaiting_asset` assertion covers
the park; the no-auto-launch-post-approval behavior is the intended fail-safe.

### FIX E — Forward-dated vendor facts are INHERITED, GO is conditional on the sibling's sourcing
The version/date specifics (`google-ads 31.0.0 / 2026-05-13`; Meta CAPI-only since 2025-05-14; Google
dev-token 2FA-after-2026-04-21; `META_ADS_API_VERSION ~v25`) are **inherited verbatim from
`automation-ads.md` §13** and several post-date this design's research window. `google-ads 31.0.0
(2026-05-13)` was **independently re-confirmed on PyPI 2026-06-09**; the remaining dates are scoped to
the sibling spec and are **not re-litigated here** (the doc correctly defers them). **GO is conditional
on `automation-ads.md` keeping those facts current** — this module reuses the credential/version knobs,
it does not own them, so a vendor change is a one-line env edit (`*_API_VERSION`), never a code change.

### RESIDUAL RISKS (accepted, not blockers)
1. **Inter-poll overshoot** (§6.3) — real and honestly stated; the platform daily budget (L1) is the
   true floor, not the poller.
2. **CBO/learning-phase collision** (§1.3/§12) — honestly bounded; the bandit's edge is cross-arm
   kill/promote + ROAS reward, not out-reallocating the platform.
3. **ROAS only as real as conversion tracking** — fail-safe via `blocked_no_conversion_tracking` +
   CTR/CPC fallback; never fabricated.
4. **Step-up depends on the spine wiring `auth.init()`** (FIX C) — until then approval **fails closed**
   (safe); the module cannot approve real spend standalone, which is correct for a dormant module.
5. **Inherited forward-dated vendor facts** (FIX E) — mitigated by env-knob versioning + sibling ownership.
6. **AI-creative content-policy review** (FIX A) — mitigated by the mandatory human launch-approval gate;
   not eliminable (platform discretion).

---

## SOURCES (2026-06-09)
- **REUSED ad-platform facts** (Meta `facebook-business` v25 / Marketing API v25; Google `google-ads`
  31.0.0 2026-05-13 monthly cadence + version-sunset; Meta CAPI-only since 2025-05-14; Google dev-token
  approval + 2FA-after-2026-04-21) — see `design/automation-ads.md` §13 + `design/automation-aimanager.md`
  Sources (primary: developers.facebook.com/docs/marketing-api ; pypi.org/project/google-ads ;
  developers.google.com/google-ads/api/docs/sunset-dates). Not re-litigated here.
- **YouTube ads = Google Ads VIDEO campaigns** (no separate API/credential; YouTube Data API v3 is
  content-management, not ads) — developers.google.com/google-ads/api/docs/video-campaigns ;
  developers.google.com/youtube/v3 (the latter explicitly NOT for ads).
- **Multi-armed-bandit / Thompson sampling for ad budget allocation** — standard bandit literature;
  platform auto-bidding context: Meta Advantage+ (facebook.com/business/help) and Google Smart Bidding
  (support.google.com/google-ads) — we orchestrate cross-variant on top of their per-campaign ML.
- **OSS landscape (wrappers/MCP, no self-hostable optimizer)** — github.com/jshorwitz/awesome-agentic-advertising
  ; github.com/TheMattBerman/meta-ads-kit ; github.com/AgriciDaniel/claude-ads (all 2025-26 wrappers).
- **In-repo prior art (verified on disk 2026-06-09)** — `droplet_work/whatsapp.py` (dormancy),
  `audit.py` (record/tail/init), `config.py` (get/require/source), `vendors/__init__.py` (redact),
  `auth.py` (issue_pair/_VERIFY_PASSWORD); `famit-panel/contstants/navigation.tsx` + `app/billing/*`
  (the multi-page sidebar pattern this sub-page mirrors); sibling specs `design/automation-{ads,
  aimanager,image,video,threed,marketing}.md`.
```
