# DESIGN SPEC — Creative Batch Generator (`droplet_work/creative/batch/`)

> **Status:** EXECUTION-READY. A build agent implements this verbatim, one UNIT at a time,
> committing + running the offline acceptance test before the next. **NON-BREAKING + crash-safe.**
> **NO git** (orchestrator commits). **NEW files ONLY under `droplet_work/creative/`** — NOT
> `automation/`. This module is the LLM **orchestrator** that fans out across into the media
> studios under `droplet_work/automation/{image,video,threed,ads,marketing}`.
> **DO NOT edit `caller.py` / `agent.py`** (backend spine; final wiring deferred — endpoints below
> are *described*, not implemented). Every integration is **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS**:
> a no-op returning `{"status":"not_configured"}` that **NEVER raises** until the founder pastes keys —
> exactly like `droplet_work/whatsapp.py` (the canonical pattern this spec mirrors).
> **Verifiable OFFLINE** — the acceptance test makes ZERO live external calls and does **not** require
> any sibling automation module to exist on disk.

Research date: 2026-06-09. All chosen tools verified ACTIVE in 2026 (cited §10). Verified against live
source under `C:\Users\kunal\Desktop\caps\droplet_work\` and the sibling design docs.

---

## 0. WHAT THIS IS (one paragraph, honest)

`creative-batch` is the **Creative Studio orchestrator**. A vendor selects a product/campaign from a
**dropdown**; using their stored business + product + campaign data, this module assembles a single
**master creative brief**, then auto-generates a full **TESTING BATCH** of variants — *the founder's
exact counts*: **10 hooks, ad copy per hook, 10 banner concepts, 5 video scripts, 5 landing
headlines, 5 WhatsApp angles** (all configurable). It is the **fan-out hub**: text deliverables it
produces itself (via the spine's metered LLM seam); media (banners → images, scripts → MP4s, hero
objects → 3D) and paid launches it **delegates** to the sibling automation studios. It does **not**
re-implement those studios, and it does **not** own the ad-optimization loop (that is `ads` +
`aimanager`) — it produces **creative-tagged variants** and hands them off so the revenue loop
(ads → leads → CRM → voice → WhatsApp → analytics) can attribute performance back to each tag.

**Real-vs-hype, stated up front.** With **zero credentials** the module is *not* a dead no-op — it
still produces the **entire text batch + all media briefs** offline (Phase 1, below). Media rendering
and ad launch are the **dormant async layer on top** (Phase 2). This honesty is structural: it falls
directly out of the two-phase split that is the spine of this design.

---

## 1. GROUND TRUTH — the seams this orchestrates (verified on disk 2026-06-09)

| Asset | Path / location | What creative-batch uses |
|---|---|---|
| Dormant-until-creds template | `whatsapp.py` | EXACT pattern: env read at call time, `is_configured()`, no-op `{"status":"not_configured"}`, never raises, sync+async twins. **Copied for the LLM seam and every studio adapter.** |
| Spine wiring pattern | `caller.py:35-37` | `try: import X except Exception: X=None`. **This is also how we import each sibling studio** — absent module ⇒ `mod=None` ⇒ typed placeholder, never crash. |
| Metered LLM seam (text gen) | `llm_router_processor.py:9-18`, `LLM_ROUTER_URL` (default `http://llm-router:8111`) | ⚠️ **CORRECTED (red-team §12):** `POST /v1/llm/generate` returns the voice agent's `{"brain": <BrainOutput>}` and *requires* `user_turn` — it is **NOT** a generic "give me 10 hooks as JSON" generator (line 18 of the cited source: "NOT called by default"). The **only real text path that ships today is `CREATIVE_LLM=none` → deterministic templates.** A real-LLM creative path needs a net-new generic-generation seam (it may reuse the already-pasted Groq/Sarvam keys, but `vendors/*_meter` expose NO `generate()`, so this seam does not exist yet). No new LLM *vendor* required; a new *generation call* is. |
| Vendor cost meters | `vendors/groq_meter.py`, `vendors/sarvam_meter.py` | `status()`, `cost_for_tokens()`, `summarize()` — **cost estimation only** (they expose NO `generate()`; that is why text gen goes through llm-router). |
| Immutable audit | `audit.py` → `audit.record(actor, action, object_type, object_id, channel, meta)` (append-only JSONL, never raises) + `tail(action_prefix=)` | Every batch + approval + fan-out logged. New channel `"creative"`, action prefix `creative.*`. Does **not** reinvent. |
| Stored campaign data (DB) | `db/models.py:87` `Campaign(id, org_id, name, company, product, status, voice_id, system_prompt, …)` ; `Org`, `User`, `Lead` | The dropdown's row. `org_id` == tenant_id (RLS-scoped). |
| Rich "what am I selling" shape | `campaign.py` `GODREJ_ARISTOCRAT` dict (`product_description`, `offer`, `talking_points[]`, `objection_handling[]`, `qualifying_questions[]`, persona, language) | The **master-brief feedstock** — this is the canonical structured product/business profile. |
| JSON/JSONL persistence | `caller.py:108/444/450` `_read/_write` under `VAR=Path(os.getenv("FAMIT_VAR","/opt/famit-agent/var"))`, `_STORE_LOCK`, lazy `mkdir(parents=True, exist_ok=True)`; marketing/video `store.py` (atomic write + append) | Batch records live under `var/creative/`. |
| Auth / RBAC / approval | `resolve_tenant` `:371`, `need_auth` `:403`, `can(tenant,"write")` `:608`, `_forbidden` `:620`, `_audit` `:713`; firewall **step-up** (`design/credit-ledger-firewall.md`) | Phase-2 release reuses the **firewall step-up** gate — does NOT invent a new gate. |
| Spend ledger / holds | `caller.py:1383` `_charge_call` + `LEDGER_DIR`; `design/credit-ledger-firewall.md` | Phase-2 cost estimate + holds reuse the existing ledger; this module **aggregates** child holds, never double-charges. |

### 1.1 The sibling studios it fans out to (interfaces from their design docs — **referenced, not re-specced**)

| Studio | Package (under `automation/`) | Entry points creative-batch calls | Asset types |
|---|---|---|---|
| Image | `automation/image/` | `generate(brief)` / `generate_async(brief)` → `ImageResult`; `providers_status()` | banners, social cards, product creatives, logos/SVG |
| Video | `automation/video/` | `submit_video_job(brief)` / `poll_video_job(job)` (async) | ad MP4s from scripts |
| 3D | `automation/threed/` | submit-task → poll → `.glb` (async, same shape) | hero-object 3D / 360° spin for listings |
| Marketing | `automation/marketing/` | `content.generate(kind, template, vars)`; channel senders are NOT called here | reuses our text for email/SMS/social copy downstream |
| Ads | `automation/ads/` | `propose_campaign(tenant, brief)` → plan; `approve_campaign(...)`; `optimize(...)` | paid launch of the tagged variants (DRAFT/PAUSED) |
| AI Ops manager | `automation/aimanager/` | (no direct call) consumes our tagged variants via the funnel | autonomous scale/pause/reallocate |

> **Scope boundary (mirrors the ads↔marketing "zero overlap" rule):** creative-batch owns ONLY
> master-brief assembly, the batch manifest/matrix, the fan-out, status aggregation, and the
> **creative-tag taxonomy**. It does NOT redesign any studio and does NOT own the optimizer loop.

---

## 2. THE DECISIONS THAT DEFINE THIS MODULE (read before coding)

### 2.1 TWO PHASES — this split is the spine of the whole design

> **PHASE 1 — FREE · INSTANT · ZERO-CRED · OFFLINE-PROVABLE.** On one dropdown click the batch
> *always* produces the **complete manifest + every TEXT deliverable** (hooks, ad copy, landing
> headlines, WhatsApp angles) AND every **media brief** (banner concepts, video scripts, 3D
> object specs) — ready to hand off. This runs with **no sibling module present** and **no LLM key**
> (the LLM seam degrades to a deterministic template/passthrough, §4.2). **This is exactly what the
> acceptance test exercises.** Cost to run: ₹0.

> **PHASE 2 — GATED · ASYNC · COSTS MONEY.** Rendering media (image/video/3D) and launching paid
> ads delegates to the child studios. It is released ONLY after **one batch-level approval**
> (firewall step-up) and within the existing HARD spend caps. Each delegated job is an async child
> ref the batch tracks and aggregates.

This split *is* the honest dormancy story: zero creds ⇒ founder still gets a full text batch + briefs;
media/ads are the dormant layer on top. It also satisfies the spend invariant (§2.3).

### 2.2 Text generation: **reuse the spine's metered LLM seam — introduce NO new LLM vendor**

The repo already meters Groq/Sarvam and routes voice-turn LLM calls through an HTTP **llm-router**
(`LLM_ROUTER_URL`). Creative-batch's text generator is gated behind
`CREATIVE_LLM ∈ {none(default), router, groq, sarvam}`. With `none` (default until wired) it
returns deterministic **template-filled** variants (offline, pure) so the pipeline is fully provable
with no key. ⚠️ **HONESTY CORRECTION (red-team §12): only `none` is a working path today.** The
`router` mode cannot reuse `POST /v1/llm/generate` verbatim — that endpoint returns the voice
`BrainOutput` and requires `user_turn` (§1), so wiring `router`/`groq`/`sarvam` to real creative
generation is **unbuilt net-new work**, NOT a free reuse. A build agent implements `CREATIVE_LLM=none`
only; the other modes are described-not-built placeholders that MUST fall back to the template path
until a generic generation seam exists. **No Claude/Anthropic, no new vendor** (matches the marketing doc's established line).
**Structured output**: variants must be valid JSON. We validate every LLM payload against a
**Pydantic v2** schema (already a repo dependency) and **repair-or-fallback** on malformed output
(never raise). **`instructor` (567-labs, last release 2026-01-29, 3M+ monthly downloads, multi-provider
incl. Groq — §10) is an OPTIONAL enhancement** behind `CREATIVE_STRUCTURED=instructor`; default is the
zero-dependency Pydantic-validate-then-repair path so the module has **no net-new hard dependency**.
For any self-hosted constrained-decoding model, `outlines` (dottxt-ai, ACTIVE 2026 — §10) is the
documented option, also env-gated and optional.

### 2.3 Spend gate on the fan-out — one click must NOT silently spawn $50 of renders

"5 videos × 10 banners" through the media studios is real money. Therefore:
1. Phase-1 text + briefs generate immediately, free, no gate.
2. The module computes a **Phase-2 cost estimate** (sums each studio's per-asset estimate ×
   requested counts; studios expose cost via their own estimators / our `vendors/*_meter`).
3. Releasing Phase 2 requires **ONE batch-level approval** = the existing **firewall step-up**
   (`require_step_up(scope="spend")`, `design/credit-ledger-firewall.md`) — **not a new gate**. On
   approval, the module places/*delegates* per-studio holds (each studio already reserves its own
   ledger hold) and submits the child jobs.
   ⚠️ **FAIL-CLOSED (red-team §12):** `firewall.py` does **not exist yet** and `FIREWALL_ENABLED`
   **defaults OFF** (then `require_step_up` is a pass-through no-op). So creative-batch must NOT trust
   "the gate will catch it." Phase-2 media release **default-DENIES** when the firewall guard is
   unavailable OR `FIREWALL_ENABLED` is off OR no PIN is set — it returns `{"status":"stepup_required"}`
   rather than fanning out renders. (Real ad *spend* is separately safe: ads emits DRAFT/PAUSED and never
   auto-activates — see §2.5/§7 — which also keeps us inside Meta/Google automation ToS. The real
   exposure this fail-closed rule protects is **media-render cost**: image/video/3D are real money.)
4. A global **kill-switch** (`CREATIVE_KILLSWITCH=1` env OR `POST /creative/killswitch`) blocks all
   Phase-2 release, mirroring `aimanager`.

### 2.4 The creative-tag taxonomy — what closes the revenue loop

Every variant carries a **creative tag set** so downstream ads-analytics can attribute CTR/CPC/ROI
back to creative DNA (the "tag → metric" pattern from 2026 multivariate-testing practice, §10). Tags:
`{angle, hook_style, format, cta, persona, language, offer_emphasis, asset_kind, batch_id, variant_id}`.
**Counts are authoritative, NOT the Cartesian product.** The founder's fixed counts (10 hooks, 5
videos, …) decide how many variants exist; the matrix dimensions (`angles`, `hook_styles`, `ctas`) are
**distributed across those N variants** (round-robin / sampled), so every dimension value appears at
least once but we do NOT expand to an 18-cell grid that would contradict "10 hooks". The batch follows
the **isolate-one-variable** discipline (a hooks-only test batch holds visual/format tags constant,
varying only `hook_style`/`angle`), so winners stay interpretable. `ads.propose_campaign` receives the
tagged variants; `aimanager`/ads then scale the winning tags and pause losers. Tags are persisted on
every variant and echoed into the ad plan's `name`/`tracking` fields.

### 2.5 Async pattern (for the media fan-out)

`submit → poll/webhook → store-artifact`, identical to the video/image studios. The **batch record**
holds a list of **child job refs** `{studio, job_id, status, cost_est, artifact_url}`. A
batch-status aggregator rolls child statuses up into a single batch progress
(`queued|generating_text|awaiting_approval|rendering|partial|complete|failed`). Media artifacts live in
the studios' own DO Spaces buckets; the batch stores only **references**, never bytes (mirrors video).
Webhooks land on the **studios'** existing callback endpoints; the batch reconciles via a
`reconcile_batch(batch_id)` poller (deferred cron hook, like `aimanager.run_tick`).

---

## 3. PACKAGE LAYOUT (NEW files, ALL under `droplet_work/creative/`)

```
droplet_work/creative/
  __init__.py
  batch/
    __init__.py            # public surface: generate_batch / get_batch / approve_batch / reconcile_batch / status
    brief.py               # MasterBrief assembly from a Campaign row + campaign.py-shaped profile
    matrix.py              # multivariate matrix → variant slots; founder counts; creative-tag builder
    generate.py            # Phase-1 text gen (hooks/copy/headlines/WA angles) + media-brief synthesis
    llm.py                 # dormant LLM seam: CREATIVE_LLM router/groq/sarvam/none; Pydantic-validate+repair
    studios.py             # studio adapter seam: import-safe wrappers over image/video/threed/ads/marketing
    cost.py                # Phase-2 cost estimate (counts × per-asset est); ledger-hold aggregation
    approve.py             # firewall step-up gate + kill-switch; releases Phase 2
    store.py               # atomic JSON/JSONL helpers scoped to var/creative/ (mirrors marketing/video store)
    models.py              # Pydantic: MasterBrief, BatchRequest, VariantSlot, BatchRecord, ChildJobRef, BatchResult
    schemas/               # JSON-schema files for the LLM structured-output contract
    router.py              # DEFERRED FastAPI APIRouter (described §6; NOT mounted by this module)
  tests/
    test_batch_offline.py  # the offline acceptance test (§8) — zero network, no sibling module needed
    fixtures/              # a sample Campaign row + campaign.py-shaped profile
```

`creative/__init__.py` re-exports `batch.generate_batch` etc. Nothing here imports `caller.py`/`agent.py`.

---

## 4. PUBLIC SURFACE (callables — every one NEVER raises)

### 4.1 batch/__init__.py
```python
def status(*, tenant_id: str = "") -> dict
    # {ok, llm: <status>, studios: {image:..,video:..,threed:..,ads:..,marketing:..}, killswitch: bool}

def generate_batch(req: "BatchRequest | dict", *, tenant_id: str, actor: str = "") -> "BatchResult"
async def generate_batch_async(...) -> "BatchResult"
    # PHASE 1 only: assemble MasterBrief → build matrix → generate ALL text + media briefs.
    # Persists a BatchRecord (status="awaiting_approval" if any Phase-2 assets requested, else "complete").
    # NEVER submits a paid job here. Returns the full text batch + briefs + Phase-2 cost estimate.

def get_batch(batch_id: str, *, tenant_id: str) -> "BatchRecord | dict"     # tenant-scoped read
def list_batches(*, tenant_id: str, limit: int = 50, offset: int = 0) -> list  # newest-first

def approve_batch(batch_id: str, *, tenant_id: str, actor: str, stepup_token: str) -> dict
async def approve_batch_async(...) -> dict
    # PHASE 2 release. Validates firewall step-up + kill-switch + spend cap. On pass: fan out media
    # jobs to image/video/threed (submit-only) and (optionally) ads.propose_campaign(DRAFT/PAUSED).
    # Records child job refs. NEVER auto-activates ad spend (ads keeps its own approval invariant).

def reconcile_batch(batch_id: str, *, tenant_id: str) -> "BatchRecord | dict"
    # Poll each child studio for terminal status; settle/refund holds; roll up batch status.
    # Idempotent. Deferred-cron callable (like aimanager.run_tick).

def killswitch(on: bool, *, actor: str = "") -> dict   # blocks all Phase-2 release
```

### 4.2 batch/llm.py — the dormant text-gen seam
```python
def llm_status() -> str          # "configured:<provider>" | "not_configured"
def generate_text(kind: str, schema_name: str, prompt_vars: dict, *, n: int) -> list[dict]
    # kind ∈ {hooks, ad_copy, landing_headlines, wa_angles, banner_concepts, video_scripts, threed_specs}
    # CREATIVE_LLM=none -> deterministic template fill from prompt_vars (pure, offline, valid against schema).
    # CREATIVE_LLM=router|groq|sarvam -> POST {LLM_ROUTER_URL}/v1/llm/generate, then Pydantic-validate;
    #   on malformed/HTTP error -> repair once -> else fall back to the template path. NEVER raises.
```

### 4.3 batch/studios.py — import-safe studio adapters (the load-bearing dormancy seam)
```python
# Each studio is imported defensively; absence OR no-creds -> typed placeholder, never raise.
# Import string MUST match the spine: caller.py:35 does a BARE `import whatsapp as wa_mod`
# because the deploy root /opt/famit-agent/ IS the droplet_work/ contents (no `droplet_work.`
# prefix). So use `from automation import …`, NOT `from droplet_work.automation import …`
# (the latter ImportErrors in prod and would silently strand every studio in `module_absent`).
try:    from automation import image as _image
except Exception:  _image = None      # mirrors caller.py:35-37 (bare import + None on failure)

def image_generate(brief: dict) -> dict
    # _image is None  -> {"status":"module_absent","kind":"image"}     (Phase-1 still emitted the concept)
    # not configured  -> {"status":"not_configured","kind":"image"}
    # else            -> _image.generate(ImageBrief(**brief))  (submit; result/job ref captured)
# ... video_submit, threed_submit, ads_propose, marketing_content analogous.
```

> **This adapter is why the offline test needs no sibling module:** every adapter resolves to a typed
> dict whether the studio is missing, dormant, or live. Phase 1 never touches an adapter for text.

---

## 5. DATA MODEL (Pydantic + files under `var/creative/`)

**Pydantic (models.py):**
- `MasterBrief` — `{tenant_id, campaign_id, company, product, product_description, offer,
  talking_points[], objections[], persona, language, audience, channels[], constraints}` — assembled
  from the `Campaign` row + the `campaign.py`-shaped profile (brief.py).
- `BatchRequest` — `{campaign_id, counts:{hooks:10,ad_copy:10,banners:10,videos:5,landing_headlines:5,
  wa_angles:5,threed:0}, matrix:{angles:[…],hook_styles:[…],ctas:[…]}, want_media:bool, want_ads:bool}`
  (counts + matrix both configurable; defaults are the founder's exact numbers).
- `VariantSlot` — `{variant_id, asset_kind, tags:{…}, text|brief, status}`.
- `ChildJobRef` — `{studio, job_id, status, cost_est_minor, artifact_url, error}`.
- `BatchRecord` — `{batch_id, tenant_id, campaign_id, created_ts, status, variants:[VariantSlot],
  child_jobs:[ChildJobRef], phase2_cost_est_minor, approved_by, approved_ts, audit_ref}`.
- `BatchResult` — the API-facing view of a `BatchRecord`.

**Files (atomic write / JSONL append, all under `var/creative/`, created on demand):**
- `var/creative/batches/<batch_id>.json` — the full `BatchRecord`.
- `var/creative/index.jsonl` — one line per batch (id, tenant, campaign, status, ts) for fast listing.
- `var/creative/<batch_id>/variants/<variant_id>.json` — per-variant text/brief + tags.
- All reads/writes under a `_STORE_LOCK` (mirrors caller.py), tenant-scoped on read.

---

## 6. DEFERRED HTTP SURFACE (described — NOT mounted; orchestrator wires later)

Powers the **Creative Studio** sidebar section (multi-page, like Billing). Auth via `resolve_tenant` +
`need_auth` + `can(tenant,"write")`; every mutating route calls `_audit(...)`.

| Method · Path | Role | Behavior |
|---|---|---|
| `GET /creative/campaigns` | read | Dropdown source: tenant's `Campaign` rows (id, name, product). |
| `POST /creative/batches` | write | Body=`BatchRequest`. **Phase 1.** Returns `BatchResult` + `phase2_cost_est`. Unconfigured LLM ⇒ template batch (still 200). |
| `GET /creative/batches` | read | List tenant batches, newest-first (mirrors `/whatsapp/log`). |
| `GET /creative/batches/{id}` | read | One `BatchRecord` (tenant-scoped). |
| `POST /creative/batches/{id}/approve` | **manager+ · step-up** | **Phase 2 release.** Requires `stepup_token`. Fans out media + ad-plan jobs. |
| `POST /creative/batches/{id}/reconcile` | read/write | Poll children, settle holds, roll up status. Idempotent. |
| `POST /creative/batches/{id}/reject` | manager+ | Refund any held estimate; status `cancelled`. |
| `POST /creative/killswitch` | admin | `{on:bool}` — blocks all Phase-2 release. |
| `GET /creative/batches/{id}/variant/{vid}/asset` | read | Proxy to the owning studio's artifact (when rendered). |

`router.py` builds these on an `APIRouter` but the spine include is a **deferred, un-applied** wiring
note (no `caller.py` edit), exactly like the sibling docs.

---

## 7. HOW IT CONNECTS TO THE REST (the revenue loop)

```
 dropdown (Campaign row + campaign.py profile)
        │  brief.py
        ▼
   MasterBrief ──► matrix.py ──► tagged VariantSlots
        │                              │
        │ PHASE 1 (free, offline)      │ creative tags
        ▼                              ▼
  TEXT: hooks, ad copy, landing      BRIEFS: banner concepts, video
  headlines, WhatsApp angles          scripts, 3D object specs
        │                              │
        └──────────── approve_batch (firewall step-up) ────────────┐
                              PHASE 2 (gated, async, $)            │
        ┌─────────────────────────────┼───────────────────────────┘
        ▼            ▼                 ▼                ▼
   image.generate  video.submit   threed.submit   ads.propose_campaign(DRAFT/PAUSED)
   (banners)       (MP4 ads)      (.glb/360)        with creative tags
        │            │                 │                │
        └── artifacts in DO Spaces ────┘                ▼
                                            aimanager + ads.optimize()
                                            scale winners / pause losers
                                                        │
   tagged ads ──► leads (CRM/db.Lead) ──► voice (caller.py/agent.py)
            ──► WhatsApp follow-up (whatsapp.py) ──► analytics (CTR/CPC/ROI by creative tag)
```

- **Ads/leads/CRM:** tagged variants → `ads.propose_campaign` → on activation drive leads into the
  existing `Lead` table; CTR/CPC/ROI attribute back to `tags` for the optimizer.
- **Voice:** the same `MasterBrief` (talking_points/objections) is already what `campaign.py` feeds
  the voice agent — creative-batch reads it, never edits the spine.
- **WhatsApp:** the **WhatsApp angles** become `marketing.content` / `whatsapp.py` template inputs.
- **Analytics:** `audit.tail(action_prefix="creative")` + child-studio ledgers give per-batch cost and
  per-tag performance for the billing/analytics surfaces.

---

## 8. OFFLINE ACCEPTANCE TEST (`tests/test_batch_offline.py` — ZERO network, no sibling needed)

Uses a temp `var/creative/`, a temp audit file, a fixture `Campaign` row + `campaign.py`-shaped profile,
`CREATIVE_LLM=none`, all studio adapters resolving to `module_absent` (siblings not imported).
**Monkeypatch `httpx` to RAISE if touched** — proves zero network.

1. **Dormant status:** `status()` → `llm:"not_configured"`, every studio `module_absent|not_configured`,
   `killswitch:false`. No raise.
2. **Phase-1 full batch offline:** `generate_batch(BatchRequest(default counts))` →
   - `result.status == "awaiting_approval"` (media/ads requested), variants include **exactly**
     10 hooks, 10 ad_copy, 10 banner_concepts (briefs), 5 video_scripts, 5 landing_headlines,
     5 wa_angles; every variant has a complete `tags` set with a valid `batch_id`/`variant_id`.
   - all text is deterministic template-fill (valid against each JSON schema), `phase2_cost_est_minor >= 0`.
   - `BatchRecord` + `index.jsonl` + per-variant files written; `audit.tail("creative")` has a
     `creative.batch.generate` line.
3. **Matrix discipline (counts-authoritative):** assert each requested `angles`/`hook_styles`/`ctas`
   value appears **at least once** across the hook variants (distribution, NOT a full Cartesian grid —
   10 hooks must NOT explode to 18 cells), and that a single-variable (hooks-only) batch holds the
   visual/format tags constant while varying only `hook_style`/`angle`.
4. **Approval gate:** `approve_batch(batch_id, stepup_token="")` (missing token) →
   `{"status":"stepup_required"}`, **no** child job submitted, status unchanged. With a valid fake
   step-up token AND all studios `module_absent` → child refs recorded as
   `{"status":"module_absent"}`, batch `status:"partial"`, **no network, no raise**.
5. **Kill-switch:** `killswitch(True)` then `approve_batch(...)` → `{"status":"blocked_killswitch"}`.
6. **Reconcile idempotency:** `reconcile_batch` twice → identical terminal record, no duplicate holds.
7. **Never-raises fuzz:** empty BatchRequest, unknown campaign_id, garbage counts → all return typed
   dicts, none raise.

Test passes with **no keys, no sibling modules, no network**. That is the dormancy + offline bar.

---

## 9. BUILD UNITS (each: implement → run offline test → orchestrator commits → next)

1. `store.py` + `var/creative/` atomic helpers + `models.py` Pydantic models (+ unit test of write/append). 
2. `brief.py` MasterBrief assembly from fixture Campaign + campaign.py profile (+ test).
3. `matrix.py` matrix → tagged VariantSlots; founder counts; tag builder (+ test of the grid).
4. `llm.py` dormant seam (`CREATIVE_LLM=none` template path + Pydantic validate/repair) (+ test).
5. `generate.py` Phase-1 text + media-brief synthesis; `generate_batch` persists BatchRecord (+ test §8.2/8.3).
6. `studios.py` import-safe adapters (all resolve to typed dicts) (+ test §8.4 module_absent path).
7. `cost.py` Phase-2 estimate + hold aggregation; `approve.py` step-up + kill-switch + fan-out (+ test §8.4/8.5).
8. `reconcile_batch` aggregator (+ test §8.6); `router.py` deferred APIRouter (described, un-mounted).
9. Full `test_batch_offline.py` green end-to-end (§8.1–8.7).

---

## 10. CREDENTIALS THE FOUNDER MUST PROVIDE

### 10.1 creative-batch's OWN net-new creds — **effectively ZERO**
The orchestrator reuses the spine's metered LLM. Its only knobs (all OPTIONAL; blank ⇒ Phase-1 still
works fully offline):

| Env var | Default | Effect when blank | When to set |
|---|---|---|---|
| `CREATIVE_LLM` | `none` | Text is deterministic template-fill (offline). | Set `router` to use the existing llm-router (no new key — reuses spine LLM creds). `groq`/`sarvam` reuse the **already-pasted** spine keys. |
| `LLM_ROUTER_URL` | `http://llm-router:8111` | n/a (already a spine default). | Only if the router host differs. |
| `CREATIVE_STRUCTURED` | `pydantic` | Zero-dep validate+repair. | `instructor` to enable richer structured output (adds the optional `instructor` pip dep). |
| `CREATIVE_KILLSWITCH` | unset | Phase-2 release allowed. | Set `1` to freeze all paid fan-out. |
| `FAMIT_VAR` | `/opt/famit-agent/var` | (spine default). | already set in prod. |

> **Net: the founder pastes NOTHING for creative-batch itself.** It works the moment it ships
> (Phase-1 text batch), and gets smarter when the spine LLM is wired.

### 10.2 Which CHILD-STUDIO creds light up which asset types (pointer table — full cred lists live in each child doc)
Creative-batch stays dormant-graceful for whatever is unconfigured; **no cred ⇒ that asset stays a brief/concept, never an error.**

| To unlock | Set creds in (child doc) | If blank, creative-batch still gives you |
|---|---|---|
| **Banners / images / logos** | `automation-image.md` (e.g. Ideogram / FLUX / Recraft / self-host) | the 10 **banner concepts** (text briefs) |
| **Video ads (MP4)** | `automation-video.md` (fal.ai / Replicate / self-host Wan 2.2) | the 5 **video scripts** |
| **3D / 360° hero objects** | `automation-threed.md` (Meshy / Tripo / Rodin / self-host) | the 3D **object specs** |
| **Paid launch (Meta/Google)** | `automation-ads.md` (Meta + Google Ads SDK creds) | the tagged variants as an exportable plan |
| **Email/SMS/social distribution** | `automation-marketing.md` | the ad copy / WhatsApp angles as ready content |
| **Richer copy LLM (optional)** | spine LLM (`CREATIVE_LLM=router`, no new key) | deterministic template copy |

### 10.3 Sources (ACTIVE-in-2026, cited)
- **Instructor** — 567-labs, structured LLM outputs, **latest release v1.15.1, 2026-04-03** (verified on
  PyPI 2026-06-09; ACTIVE), multi-provider incl. Groq/Anthropic/Ollama (`instructor.from_provider("groq/…")`).
  [github.com/567-labs/instructor], [pypi.org/project/instructor], [python.useinstructor.com].
  (Used OPTIONALLY; not a hard dep.)
- **Outlines** — dottxt-ai, constrained/structured decoding, Pydantic-first, Rust core, ACTIVE 2026.
  [github.com/dottxt-ai/outlines]. (Optional, self-host constrained decoding only.)
- **Pydantic v2** — JSON-schema generation + validation, existing repo dependency. [docs.pydantic.dev].
- **2026 multivariate creative-testing practice** (matrix = hooks × visuals × CTAs; isolate-one-variable;
  creative-tag → metric attribution; min-impression thresholds; brand knowledge vault → on-brand variants):
  [segwise.ai/blog/ai-powered-creative-testing-2026], [sovran.ai/blog/multivariate-ad-testing-tool],
  [syntermedia.ai/blog/automate-ad-creative-variations], [cometly.com/post/ai-ad-variation-generator].
- **In-house seam (no new vendor):** `llm_router_processor.py` (llm-router `POST /v1/llm/generate`),
  marketing's `MKT_CONTENT_LLM` dormancy pattern (`design/automation-marketing.md` §1.5/§3.4).

---

## 11. WHICH CREATIVE-STUDIO SUB-PAGE THIS POWERS

Creative Studio is a **sidebar section with multiple sub-pages** (the Billing multi-page pattern). This
module powers the **two foundational sub-pages**:

1. **"Creative Batch Generator"** (primary) — the **dropdown → Generate** page. Vendor picks a
   product/campaign; one click runs Phase 1 and shows the full testing batch (10 hooks, copy, 10 banner
   concepts, 5 video scripts, 5 landing headlines, 5 WhatsApp angles) with their creative tags, plus the
   Phase-2 cost estimate. Backed by `GET /creative/campaigns` + `POST /creative/batches`.

2. **"Batch Review & Approve"** — the founder reviews variants, sees the Phase-2 cost + spend headroom,
   and **approves once** (firewall step-up) to release media rendering + ad-plan creation; then watches
   live batch progress as child jobs complete. Backed by `GET /creative/batches/{id}`,
   `POST /creative/batches/{id}/approve`, `/reconcile`, `/reject`, `/killswitch`.

The downstream media-gallery, ads-launch, and analytics sub-pages are owned by the
image/video/threed/ads/aimanager studios respectively; creative-batch **feeds** them.

---

## 12. RED-TEAM FIXES (folded)

Adversarial review 2026-06-09, every claim checked against live source under `droplet_work/`. Two
honesty corrections folded inline above (not just listed here, so the spec stays self-consistent);
the rest confirm the design holds.

**FIX 1 — "the only text-gen path" was false; corrected §1 + §2.2.** The cited endpoint
`POST {LLM_ROUTER_URL}/v1/llm/generate` is the voice agent's per-turn brain: it returns
`{"brain": <BrainOutput>}`, *requires* `user_turn`, and line 18 of the cited source
(`llm_router_processor.py`) marks it "NOT called by default." It cannot be coerced into "give me 10 ad
hooks as JSON." Separately, `vendors/groq_meter.py` / `sarvam_meter.py` expose `status/cost_for_tokens/
summarize` and **no `generate()`** (verified). **Net real-vs-hype:** of `CREATIVE_LLM ∈ {none,router,
groq,sarvam}`, only **`none` (deterministic templates) is a working creative path today.** A real-LLM
creative copy path is **net-new unbuilt work** (a generic generation seam — it may reuse the
already-pasted Groq/Sarvam keys, but the call itself does not exist). The build agent ships `none` only;
`router/groq/sarvam` are described placeholders that fall back to templates. *This does not affect the
offline test or dormancy* (default is `none`), but the spec no longer over-claims a free LLM reuse.

**FIX 2 — Phase-2 spend gate was a pass-through; made fail-closed §2.3.** `firewall.py` does **not exist
yet** (it is a `design/credit-ledger-firewall.md` deliverable), step-up is verified as an `X-Step-Up`
**header** (not a body `stepup_token` — implementers note), and **`FIREWALL_ENABLED` defaults OFF**,
under which `require_step_up` returns `None` (no gating). So "one approval gate" would be a no-op until
firewall ships + flag on + tenant PIN set. Corrected so Phase-2 media release **default-DENIES** when the
guard is absent/off/no-PIN. **Autonomous ad-spend safety is otherwise real:** the `ads` studio emits
DRAFT/PAUSED and never auto-activates (creative-batch explicitly does not own the optimizer loop), so no
single creative-batch click can launch live paid spend — this also keeps the design inside Meta/Google
**automation ToS** (human/API activation stays in `ads`). The exposure the fail-closed rule actually
protects is **media-render cost** (image/video/3D = real money on one click).

**FIX 3 — stale OSS date, corrected §10.3.** Instructor latest is **v1.15.1 (2026-04-03)**, not the
2026-01-29 the spec listed — still ACTIVE/multi-provider/Groq, just refreshed. Outlines confirmed ACTIVE
(dottxt-ai, v1.3.0 2026-05-13, Pydantic-first, used by NVIDIA/Cohere/HuggingFace/vLLM). Both remain
**OPTIONAL, env-gated, not hard deps** — claim holds.

**CONFIRMED-OK (no change needed):**
- **Dormant + non-breaking + offline-provable:** verified. `automation/` exists but is empty (no sibling
  studios on disk) — exactly the `module_absent` path the spec is built for; `creative/` is absent (this
  spec creates it). The `whatsapp.py` pattern (`{"status":"not_configured"}`, never raises, env-read at
  call time) is mirrored accurately.
- **Import convention is correct and load-bearing:** `caller.py:35` is a *bare* `import whatsapp as
  wa_mod` and `from vendors import groq_meter` — confirming `from automation import image` (NOT
  `from droplet_work.automation import …`) is the right string for prod where the deploy root *is* the
  package root. The spec's warning is accurate.
- **Cited spine seams all exist at the cited lines:** `audit.record(...)`/`tail(action_prefix=)`,
  `can()` `:608`, `resolve_tenant` `:371`, `need_auth` `:403`, `_forbidden` `:620`, `_audit` `:713`,
  `db/models.py` `Campaign`, `campaign.py` profile, `vendors/*_meter` — all verified.
- **Async pattern is sound:** submit→poll/webhook→store-ref, batch holds only child job refs (never
  bytes), aggregator rolls child statuses up; mirrors the video/image studio shape. No new infra invented.
- **3D and autonomous bidding are honest:** 3D degrades to an object *spec* with no creds (never an
  error); autonomous bidding is explicitly disclaimed (owned by `ads`+`aimanager`, consumed via the
  funnel). Neither is over-sold.
- **Creds/cost:** creative-batch's own net-new creds are genuinely ~zero (all knobs optional, blank ⇒
  full Phase-1). Child-studio cred pointer table is accurate. *Caveat per FIX 1:* the "richer copy LLM —
  no new key" row promises more than exists today (the generation call is unbuilt), but it correctly
  requires no new *key*.

**RESIDUAL RISKS (accepted, non-blocking):**
1. **Real-LLM creative copy is unbuilt** — only deterministic templates work today; `router/groq/sarvam`
   modes need a net-new generic-generation seam before they produce real copy.
2. **Phase-2 media-spend safety depends on `firewall.py` shipping + `FIREWALL_ENABLED=true` + a tenant
   PIN.** Mitigated by the fail-closed rule (FIX 2): no firewall ⇒ no media fan-out, by default.
3. **`router`/HTTP paths are described-not-built** — a verbatim build is safe *only* because the default
   is `CREATIVE_LLM=none` and all studio adapters resolve to typed dicts; do not enable non-default LLM
   modes until the generation seam exists.
