# DESIGN SPEC — CREATIVE STUDIO ▸ **VIDEO STUDIO** sub-page (campaign → AI script → ad-video BATCH, async, asset library)

> **Status:** EXECUTION-READY design. No code shipped by this pass. Verified against live source under
> `C:\Users\kunal\Desktop\caps\droplet_work\` and the sibling design `design/automation-video.md`,
> 2026-06-09.
>
> **What this is (one line):** the **Video Studio** is a sub-page of the new **CREATIVE STUDIO** sidebar
> section. A vendor picks a **product/campaign from a dropdown**; using their stored business + product +
> campaign data the AI auto-writes an **ad SCRIPT**, then renders a **TESTING BATCH of ad-creative videos**
> (e.g. 5 clips × hook/angle variants) as **ASYNC jobs** whose results return to the platform and land in a
> shared **Asset Library** — ready to flow into Autonomous Ads → leads → CRM → voice → WhatsApp → analytics.
>
> **House rules honored (non-negotiable):**
> - NEW code ONLY under **`droplet_work/creative/`** (this module's home — greenfield; does not exist yet).
> - **DO NOT edit `caller.py` / `agent.py`** (the backend spine). Endpoints below are *described*; final
>   wiring into the spine is deferred to the orchestrator (delivered later as an un-applied diff).
> - **NO git** (the orchestrator commits).
> - **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS:** with no keys every entry point returns
>   `{"status":"not_configured"}`, does zero network I/O, and **NEVER raises** — byte-for-byte the
>   `whatsapp.py` contract.
> - **Compose ACTIVE/maintained 2026 OSS + vendor APIs** (cited §3). Self-host on DO only where it
>   provably wins.
> - **Verifiable OFFLINE:** the acceptance test (§11) makes zero live external calls; a built-in `fake`
>   backend drives the whole pipeline (script → batch fan-out → job store → asset library → spend guard →
>   audit) without a key or a socket.

---

## 0. WHERE THIS SITS — Creative Studio sidebar map + the layering that avoids duplication

CREATIVE STUDIO is **one sidebar tab that expands to multiple sub-pages** (exactly the multi-page pattern the
founder asked for — the same shape as Billing Meter's nested pages). This spec owns **one** of those sub-pages:

```
SIDEBAR ▸ Creative Studio   (one expandable tab)
  ├─ Studio Home        (campaign dropdown → "Generate Batch" → batch dashboard)   ← shared shell
  ├─ Asset Library      (every generated asset: video/image/banner/copy, by campaign)  ← shared shell
  ├─ ▶ VIDEO STUDIO     ← THIS SPEC: ad-video from an AI script, async, returns to library
  ├─ Image Studio       (banners/social/product — design/automation-image.md)
  ├─ 3D Studio          (product → glb/360 — design/automation-threed.md)
  ├─ Copy & Hooks       (ad copy / hooks / headlines — LLM seam)
  └─ Landing / WhatsApp creatives, Brochures/Catalogs   (later sub-pages)
```

**The load-bearing layering decision (settled — read before coding):**

> There are **two layers**, and this spec is the **upper** one.
> - **Lower layer = the async video *engine*** — already fully specced in **`design/automation-video.md`**
>   (provider-agnostic `submit_video_job` / `poll_video_job` over fal/Replicate/Luma/Higgsfield/self-host
>   Wan; job store; DO Spaces artifacts; reserve→settle→release wallet holds; per-provider webhook verify;
>   license gate; content-safety screen). **That engine is the rendering primitive. We do NOT re-implement
>   it.**
> - **Upper layer = THIS module, `creative/video_studio/`** — the **Creative-Studio orchestration** that the
>   founder's vision actually describes: **campaign dropdown → AI ad-script → BATCH fan-out of N variant
>   video jobs → collect results → Asset Library → hand off to Autonomous Ads.** It is a thin orchestrator
>   that *calls* the lower engine through one stable seam.

**Why two layers, not one fat module:** the engine is reusable by Image/3D/voice too and is dollar-/webhook-
heavy infra; the studio is product UX + batch logic + the revenue loop. Splitting them keeps each testable in
isolation and lets the studio ship even before the orchestrator finalizes the engine — because the studio
talks to the engine **through an injected adapter** (`render_fn`) that defaults to the real engine when
present and a `fake` renderer otherwise (this is what makes the offline test real; §11).

> **Build-agent note:** if `automation-video.md`'s engine is not yet on disk when this is built, the studio
> still ships and tests green against the `fake` renderer. The `render_fn` adapter (§4 `engine.py`) is the
> ONLY coupling point; wire it to `automation.video.client.submit_video_job` when that exists, else to the
> built-in fake. **No duplication of provider/webhook/wallet code in this module.**

---

## 1. GROUND TRUTH (verified against live source — cite before editing)

Live backend: FastAPI `caller:app` on the agent droplet (`/opt/famit-agent/`, service `famit-caller`,
uvicorn `:8209`, venv py3.12). Public base `https://panel.famit.in/api` (nginx strips `/api/`). Local source
of truth: `C:\Users\kunal\Desktop\caps\droplet_work\`. **The patterns this module reuses (all verified to
EXIST on disk):**

| Reused asset | Path | What this module borrows |
|---|---|---|
| Dormant-until-creds sender | `whatsapp.py` | EXACT shape: env read at call time, `is_configured()` gate, returns `{"status":"not_configured"}` + never-raises (`try/except Exception` around all I/O), sync + `_async` twins. |
| JSON persistence | `caller.py` `VAR=Path(os.getenv("FAMIT_VAR",...))`, `_read`/`_write`, `_STORE_LOCK`, per-entity dirs `.mkdir(parents=True, exist_ok=True)` | the batch + job-link store under `VAR/creative/`. (Grep the symbols — line numbers drift, per `automation-video.md` RTF-6.) |
| Auth / RBAC / audit | `caller.py` `resolve_tenant` / `need_auth` / `can(tenant,"write")` / `_forbidden` / `_audit(request,tenant,action,object_type,object_id,channel=,meta=)` | the studio endpoints use these identically; `_audit` records every batch/approve/spend event. |
| Spend metering precedent | `caller.py` `_charge_call` + `LEDGER_DIR`; `vendors/*_meter.py` → `usage_events.json` | video spend is metered onto the **same** ledger/usage stream so it shows in the Billing Meter UI beside Groq/ElevenLabs/Vobiz. |
| LLM seam (for the script) | in-house **`llm-router`** HTTP service (`LLM_ROUTER_URL`, default `http://llm-router:8111`), wrapped by `llm_router_processor.py`; batch endpoint `POST /v1/llm/generate` | ad-script + hook generation calls this via an **injected callable** — **no new LLM vendor, no new key** (same decision as the ads/marketing specs). |
| Campaign data (the dropdown source) | `caller.py` `/campaigns`, `campaign.py`, `models.py` `Campaign` | the dropdown reads existing campaigns; the script generator reads campaign + product fields as context. **READ-only; adds no spine columns.** |
| Lower video engine (the renderer) | `design/automation-video.md` → (future) `automation/video/client.py` | called via injected `render_fn`; this module does NOT re-implement providers/webhooks/holds. |

---

## 2. THE PIPELINE (the whole sub-page in one paragraph)

Vendor opens **Creative Studio ▸ Video Studio**, picks a **campaign from the dropdown**, sets a **batch size**
(default 5 clips) and toggles **with-audio / vertical**, and clicks **Generate Batch**. The studio loads that
campaign's stored business/product/offer/hook fields, calls the **LLM seam** to write **N script variants**
(distinct angles: pain-point, social-proof, offer-led, urgency, founder-voice), turns each script into a
**`VideoBrief`** (prompt + optional product `image_url` + duration + aspect + model), estimates cost for the
whole batch, checks the **per-tenant daily/monthly cap** and the **approval threshold**, and — if cleared —
**fans out N async render jobs** through the injected engine. Each job is tracked in a **batch record**; as
results return (webhook or poller, owned by the engine), finished MP4s are registered as **assets in the Asset
Library** tagged to the campaign, with a `winner`/`paused`/`draft` status. The library hands assets to
**Autonomous Ads** (`design/automation-ads.md`) as creatives; downstream the ad → lead → CRM → voice → WhatsApp
→ analytics loop closes (§9). With **no creds**, every step returns `not_configured`, generates **no** script
via network, spends **nothing**, and the batch parks as a dormant record — fully exercised offline by the
`fake` renderer + `fake` LLM.

---

## 3. RESEARCH — CHOSEN TOOLS + WHY (2026, ACTIVE, cited)

This module is an **orchestrator**, so its "tools" are (a) the model routing it requests from the engine and
(b) the LLM seam for the script. The deep provider/pricing/webhook research lives in `automation-video.md`
(References there); below is the **studio-specific** research that drives model *routing by job* and the
script layer. All verified active June 2026.

### 3a. Model routing — "best model per ad-job", not one model (the studio sets the engine's `model` string)

Ad-creative video is not one problem; the studio routes the engine's model per the brief's job type. Verified
2026 rankings:

| Ad job (studio route) | Default model (set on engine) | Why — 2026 evidence | Reach via |
|---|---|---|---|
| **Product hero clip w/ dialogue+SFX** (highest-fidelity ad spot) | **Seedance 2.0** (ByteDance) | Apr-2026 release; **#1 on the Artificial Analysis image-to-video leaderboard (Elo 1,351)**, ahead of Veo 3, Sora 2, Runway 4.5; ships dialogue with **precise lip-sync + timed SFX + ambient in one pass** [R1,R2]. | fal / Replicate / WaveSpeed |
| **Hook / multi-shot story (5 langs incl. Hindi)** | **Kling 3.0 Omni / Turbo** | native audio + **lip-sync in 5 languages**, shared audio timeline across **multi-shot storyboards** — ideal for vertical hook reels; ~**$0.029/s** (Kling 3.0) cheapest flagship per-second [R2,R5]. | fal / Replicate |
| **Clean vertical w/ native audio (premium)** | **Veo 3.1 / 3.1 Fast** | "quality pick for ultra-clean vertical output with native audio"; Fast 720p **$0.10/s**, 4K **$0.30/s** [R3,R5]. | fal / Replicate |
| **Image→video w/ brand character consistency** | **Runway Gen-4.5** | "strongest pick for marketers" — reference-image control, **character/brand consistency**, fast Turbo, editor workflow [R2]. | fal / Replicate / Runway |
| **First/last-frame control, cheap drafts, self-host** | **Wan 2.7** (Alibaba, **Apache-2.0**) | first-and-last-frame control, clip continuation, audio sync; **clean commercial license** → the only self-host default for paid ad output; ~**$0.05/s** hosted [R5]. | fal / self-host (DO GPU) |
| **Higgsfield-style social motion** (founder named it) | **Higgsfield DoP** (`dop-lite`/`dop-turbo`/`dop-preview`) | first-party API, header key, **$0.10/s direct**; text-to-video / image-to-video / Soul modes; aimed at social/marketing creators [R6,R7]. | Higgsfield direct **or** via fal (prefer fal to avoid a 2nd key). |

> **The route is an env-overridable map** (`VIDEO_ROUTE_<job>` → model id). Rankings shift monthly; the
> provider-agnostic engine makes a re-rank a **one-string config change**, not a code change. The studio
> never hardcodes a vendor name in business logic — it emits a job type, a default model, and lets the engine
> (and the founder's env) resolve it.

### 3b. The script/hook layer — REUSE the in-house LLM seam, NO new vendor

Ad **scripts, hooks, angles, headlines, captions** are generated through the existing **`llm-router`**
(`POST /v1/llm/generate` on `LLM_ROUTER_URL`), wrapped via an **injected callable** into `script.py`. No new
LLM dependency, no new key, and the offline test passes a **fake** LLM fn so it's network-free. (Same decision
the ads/marketing/image specs already made — keep the seam singular and dormant-safe.)

### 3c. Why BATCH is the product, not a single clip (the founder's "testing batch" — validated)

Performance-marketing 2026 reality, verified: **winning teams test 20–50 creatives/month** (vs 3–5 for
laggards); **Meta's algorithm now favors accounts rotating 15–25 ad variants per ad-set per week**; AI agents
"generate 15–20 variations in minutes, run structured tests, scale winners" [R8,R9]. This is *exactly* the
"TESTING batch → launch at small budgets → auto-scale winners, trash losers" loop in the brief. So the studio's
unit of work is a **BATCH of variants**, each a distinct angle, fanned out as parallel async jobs — not a
single hero render. The batch is the bridge between Creative Studio and Autonomous Ads.

### 3d. Self-host honesty (defer to the engine's breakeven)

Self-host (Wan 2.7 on a DO GPU droplet) is a **dormant** engine backend, **not** the default: a DO L40S bills
~$1.57/hr whether or not it renders, so hosted fal (~$0.30/6s clip, **zero idle cost**) wins until there's a
**sustained queue (~30–40 clips/GPU-hr)**. The breakeven math + Apache-2.0 license gate (Hunyuan **refused**
for ad output: EU/UK/South-Korea territory ban + 100M-MAU ceiling) live in `automation-video.md` §2d/§8/§2e.
The studio inherits all of it for free by routing through the engine. **Do not re-litigate self-host here.**

---

## 4. FILES & PACKAGE LAYOUT (NEW — all under `droplet_work/creative/`)

```
droplet_work/creative/
  __init__.py                  # import-safe with empty env
  README.md                    # "Creative Studio — orchestration over automation engines; dormant-until-creds"
  shared/
    __init__.py
    config.py                  # env reads for the whole Creative Studio (LLM_ROUTER_URL, caps, route map, SPACES_* passthrough). is_configured()/which_engine().
    library.py                 # ASSET LIBRARY: register/list/tag assets under VAR/creative/assets/. _STORE_LOCK-safe. Shared by video/image/3d sub-pages.
    audit.py                   # thin wrapper that calls caller._audit when wired, else appends to VAR/creative/audit.jsonl (offline-safe).
    cost.py                    # batch-level estimate + per-tenant daily/monthly cap check; reserve/settle/release SHIM that delegates to the engine's wallet hold when present, else a JSON hold-store (mirrors automation-video.md RTF-3).
    llm.py                     # injected LLM callable wrapper -> POST /v1/llm/generate on LLM_ROUTER_URL. Fake fn for tests. Never raises.
  video_studio/
    __init__.py
    config.py                  # VIDEO_STUDIO_* knobs: batch size, default route, with_audio, aspect, approval threshold, caps.
    script.py                  # campaign+product -> N ScriptVariant (angles). Uses shared.llm. Deterministic angle templates + LLM fill. Offline-safe with fake LLM.
    brief.py                   # ScriptVariant -> VideoBrief (prompt, image_url, duration, aspect, model from route map).
    engine.py                  # THE ONLY engine coupling: render_fn(brief)->job_ref and poll_fn(job_ref)->status. Defaults: automation.video.client if importable, else `fake`. NEVER raises; not_configured passthrough.
    batch.py                   # generate_batch(campaign_id, opts) -> BatchRecord: script -> briefs -> cost gate -> approval gate -> fan-out render_fn. collect_batch(batch_id) -> updates job links + registers finished assets in shared.library.
    store.py                   # JSON batch store under VAR/creative/video_batches/<batch_id>.json. create/read/update/list. _STORE_LOCK-safe.
    schema.py                  # dataclasses/TypedDicts: ScriptVariant, VideoBrief (compatible w/ engine), BatchRecord, BatchStatus enum, AssetRef.
    service.py                 # the pure callables the spine wires later (§6): propose_batch / approve_batch / batch_status / list_assets / promote_winner / cancel_batch. sync + _async.
    endpoints.py               # FastAPI APIRouter(prefix="/creative/video") — DEFINED here, MOUNTED later by the orchestrator. Not imported by caller.py now.
    fake_engine.py             # built-in deterministic fake renderer (instant "succeeded" + a fixture MP4 URL) for the offline test.
    tests/
      test_dormant.py          # OFFLINE acceptance (§11) — the gate. Zero network.
      test_batch_offline.py    # batch fan-out / collect / asset-register / cost-gate with fake LLM + fake engine.
      fixtures/                # canned campaign, canned LLM script JSON, canned engine job responses.
```

**Nothing here is imported by `caller.py`/`agent.py`.** The orchestrator mounts §6 later. Until then the
package is fully testable in isolation (§11). `shared/` is intentionally factored so Image/3D/Copy sub-pages
reuse `library.py`, `cost.py`, `audit.py`, `llm.py` (one Asset Library, one spend gate across the studio).

---

## 5. DATA MODEL

### 5a. `ScriptVariant` (LLM output, one per batch slot)
```python
@dataclass
class ScriptVariant:
    angle: str            # "pain_point" | "social_proof" | "offer_led" | "urgency" | "founder_voice" | ...
    hook: str             # 1-line scroll-stopper (first 2s)
    script: str           # 5-8s scene/voiceover script
    caption: str          # on-screen text / ad primary text
    cta: str              # call to action
    lang: str = "auto"    # "en"|"hi"|"hinglish"|... (campaign-driven; honors the multilingual brief)
```

### 5b. `VideoBrief` (handed to the engine — schema-compatible with `automation-video.md` §5a)
```python
@dataclass
class VideoBrief:
    tenant_id: str
    prompt: str                 # built from ScriptVariant.script + product context
    image_url: str = ""         # optional product shot -> image-to-video
    duration_s: int = 6
    aspect_ratio: str = "9:16"  # vertical ad default
    model: str = ""             # resolved from the route map (§3a); else engine default
    with_audio: bool = True
    extra: dict = field(default_factory=dict)   # passthrough (job angle, batch_id, campaign_id)
```

### 5c. `BatchRecord` (persisted — `VAR/creative/video_batches/<batch_id>.json`)
```python
{
  "batch_id": "vb_<uuid4hex>",
  "tenant_id": "...",
  "campaign_id": "...",
  "size": 5,
  "status": "draft|awaiting_approval|submitted|partial|complete|failed|cancelled|not_configured",
  "options": {"with_audio": true, "aspect": "9:16", "route": "hook", "duration_s": 6},
  "scripts": [ {...ScriptVariant...}, ... ],          # N entries
  "jobs": [ {"angle":"pain_point","job_ref":"vj_...","status":"running","asset_id":""}, ... ],
  "estimated_cost_usd": "1.50",                        # Decimal-as-string, whole batch
  "hold_id": "",                                       # set when reserved against wallet; "" when dormant
  "approval": {"required": true, "by": "", "at": "", "decision": ""},
  "asset_ids": [],                                     # populated as jobs finish
  "error": "", "created_at": "...", "updated_at": "..."
}
```

### 5d. `AssetRef` (Asset Library — `VAR/creative/assets/<asset_id>.json`, shared across the studio)
```python
{
  "asset_id": "ca_<uuid4hex>",
  "tenant_id": "...", "campaign_id": "...", "batch_id": "vb_...",
  "kind": "video",                 # video|image|banner|copy|threed|landing
  "url": "https://<spaces>/...mp4", "thumb_url": "",
  "meta": {"angle":"hook","model":"fal-ai/kling-3.0","duration_s":6,"with_audio":true,"lang":"hinglish"},
  "status": "draft|approved|winner|paused|trashed",   # set by human or by Ads auto-optimizer
  "ad_refs": [],                   # platform creative/ad ids once launched (links to automation-ads.md)
  "metrics": {},                   # CTR/CPC/ROI snapshot synced back from Ads analytics
  "created_at": "...", "updated_at": "..."
}
```

### 5e. Status lifecycle (batch)
```
generate_batch → script(N) → briefs(N) → estimate_cost(batch) → reserve hold
   → [cost > threshold OR AUTO_APPROVE=0] → awaiting_approval ──approve──┐
   → [cost ≤ threshold] ─────────────────────────────────────────────────┤
                                                                          ▼
                                  fan-out N render_fn  → submitted → (engine: running…)
   collect_batch (webhook/poll, engine-owned) → per-job succeeded → register AssetRef → partial → complete → settle hold
                                                 per-job failed → release that job's share of the hold
   (no creds at generate) → not_configured (no script-network, no hold, no spend, no raise)
```

---

## 6. ENDPOINTS (DESCRIBED ONLY — orchestrator wires into the spine later; DO NOT edit `caller.py` now)

`router = APIRouter(prefix="/creative/video", tags=["creative-video"])`. All mirror WhatsApp conventions
(`resolve_tenant`→`need_auth`/`can(t,"write")`→`_forbidden`; `_audit(...)`):

| Method + path | Role | Behavior |
|---|---|---|
| `GET /creative/video/campaigns` | read | Dropdown source: the caller-tenant's campaigns (id, name) — the picker the founder described. (Reads existing `/campaigns`; no new store.) |
| `POST /creative/video/batches` | write | Body: `{campaign_id, size?, with_audio?, aspect?, route?, duration_s?}`. Builds scripts, briefs, estimates cost, reserves hold; **parks `awaiting_approval`** if over threshold else fans out. Returns `{batch_id, status, estimated_cost_usd, scripts, configured}`. Unconfigured → `200 {status:"not_configured"}`. |
| `GET /creative/video/batches` | read | List caller-tenant batches, newest first. |
| `GET /creative/video/batches/{batch_id}` | read | One batch record incl. per-job status + asset links. |
| `POST /creative/video/batches/{batch_id}/approve` | **manager+** | Approve an `awaiting_approval` batch → fans out the render jobs. `_audit(...,"creative.video.approve",...)`. |
| `POST /creative/video/batches/{batch_id}/reject` | manager+ | Reject → release hold, status `cancelled`. |
| `POST /creative/video/batches/{batch_id}/cancel` | write | Best-effort cancel of pending jobs + release remaining hold. |
| `POST /creative/video/collect/{batch_id}` | read/internal | Idempotent poll: ask the engine for each job's status, register finished assets. (Fallback when the engine's webhook path isn't wired.) |
| `GET /creative/video/assets` | read | Asset Library list (filter by `campaign_id`,`kind=video`,`status`). Shared library; serves the Asset Library sub-page. |
| `POST /creative/video/assets/{asset_id}/promote` | write | Set `status=winner` / `paused` / `trashed` (manual). The Ads auto-optimizer may also set these via the Ads module. `_audit`. |

> **No webhook endpoint here.** Provider webhooks (fal ED25519 / Replicate HMAC) are the **engine's**
> responsibility (`automation-video.md` §6 + RTF-4). The studio only *reads* job status via the engine seam
> and the idempotent `collect` fallback. This keeps signature-verification in exactly one place.

The poll/collect worker is a lightweight async loop (orchestrator may run it as a spine background task or
`python -m creative.video_studio.collector`). **Not implemented in `caller.py` by this spec.**

---

## 7. SPEND / APPROVAL / AUDIT GUARDRAILS (the dollar-heavy part — batch-level)

A **batch multiplies spend by N**, so the guardrails are enforced **on the whole batch before any job fans out**:

1. **Estimate the BATCH before spend.** `cost.estimate_batch(briefs)` = Σ per-clip estimate, where per-clip
   uses the engine's per-model pricing **mode** (`per_second` × duration, or `per_generation` flat — see
   `automation-video.md` RTF-5; Wan bills flat ~$0.20–$0.40/gen, Veo audio/4K is stepped) × `VIDEO_COST_SAFETY=1.25`.
   Never fan out without a batch estimate.
2. **Reserve → settle → release (wallet firewall).** On approve/submit, `cost.reserve(tenant, batch_estimate)`
   places ONE hold for the batch via the engine's wallet seam (`reserve()/settle()/release()` from
   `design/credit-ledger-firewall.md` — note it is **`release()`, not `refund()`**). Each finished job
   settles its share at the engine's actual billed amount; each failed job releases its share. **Until the PG
   firewall exists, `shared/cost.py` keeps a JSON hold-store** (`VAR/creative/holds/<hold_id>.json`,
   `_STORE_LOCK`-guarded; sum-open-holds checked vs cap) — the same honest degrade as `automation-video.md`
   RTF-3 (cap + approval + post-hoc charge; TOCTOU window narrowed by the lock, not eliminated).
3. **Per-tenant daily + monthly spend cap.** `VIDEO_STUDIO_DAILY_CAP_USD` (default 20) /
   `VIDEO_STUDIO_MONTHLY_CAP_USD` (default 300). A batch whose estimate would breach the cap is refused with
   `{"status":"error:cap_exceeded"}` — **a runaway batch cannot drain the wallet.**
4. **Human approval gate.** A batch with `estimated_cost_usd > VIDEO_STUDIO_APPROVAL_THRESHOLD_USD`
   (default 1.00) — which a 5-clip batch will routinely cross — parks `awaiting_approval` and does NOT fan out
   until a manager+ calls `/approve`. `VIDEO_STUDIO_AUTO_APPROVE=0` (default) forces approval for **every**
   batch regardless of cost (hard manual gate, the founder's "approval gate" requirement).
5. **Content / AUP safety screen BEFORE spend (shared key blast-radius).** One `FAL_KEY`/`REPLICATE_TOKEN`
   fronts every tenant; an AUP-tripping prompt can suspend the **shared** account for all tenants. The studio
   runs each `ScriptVariant.script`/`hook` (and any `image_url`) through the **engine's `safety.py` screen**
   (denylist + pluggable `VIDEO_MODERATION_URL`, dormant-until-configured) **before** reserve/fan-out; a
   blocked variant returns `{"status":"error:content_blocked"}` and is dropped from the batch with **no spend,
   no provider call**. (Inherited from `automation-video.md` RTF-1; BYO-key per-tenant override is the
   structural fix at scale.)
6. **Audit every state change.** `_audit(request, t, "creative.video.batch|approve|reject|asset.promote|
   spend", "creative_video", batch_id, channel="creative", meta={route,size,cost,status,...})` — the same call
   every mutating spine endpoint uses. Full AI-decision + spend trail.
7. **Idempotency.** `propose_batch` accepts an optional `idempotency_key`; a repeat key returns the existing
   batch (no double script-gen, no double charge).

---

## 8. THE ASYNC-JOB PATTERN (for media gen — why the whole thing is async)

A single 5–8s clip costs **$0.05–$0.50/s** (or flat $0.20–$0.40 for Wan) and takes **30s–6min** to render; a
**batch of 5 is 5×** that, in parallel. So the surface is **propose → (approve) → fan-out submit → engine
renders → results return → register assets → notify**, never a synchronous call:

- **Fan-out submit.** `batch.generate_batch` calls `engine.render_fn(brief)` once per variant; each returns a
  `job_ref` (the engine's `{job_id, status_url, ...}`). The batch stores the N `job_ref`s and returns
  immediately with `status="submitted"` — the HTTP request never blocks on rendering.
- **Results return automatically.** The **engine** owns the return path (provider webhook with per-provider
  signature verify, or its poller). When a job reaches `succeeded`, the engine writes the artifact to **DO
  Spaces**; the studio's `collect_batch` (driven by the engine's webhook hook OR the idempotent
  `/collect/{batch_id}` poll) reads the finished `artifact_url` and calls `shared.library.register(AssetRef)`
  — the asset **appears in the Asset Library automatically**, exactly the "result returns to the platform"
  requirement.
- **Notify.** On batch `complete`, optionally push a Famit notification ("Your 5-video batch for *Campaign X*
  is ready") — reuse the existing notification/message seam; dormant-safe.
- **Large artifacts never touch JSON.** MP4s live in DO Spaces (S3-compatible, engine-owned); the studio
  stores only **URLs + metadata**. Job/batch state is small JSON under `VAR/creative/`.
- **Partial completion is first-class.** A batch can be `partial` (3 of 5 done); the library shows ready
  assets immediately; failures release their hold share and are flagged per-job without failing the batch.

---

## 9. HOW IT CONNECTS TO THE REST (ads / leads / CRM / voice / WhatsApp / analytics)

The studio is **revenue-connected by construction** — every asset is a node in the funnel:

1. **→ Autonomous Ads (`design/automation-ads.md`).** A batch's `AssetRef`s are the **creatives** the Ads
   module attaches to ad variants. Ads launches all variants at **small test budgets**, then its deterministic
   optimizer + platform auto-bidding **auto-scale winners / pause losers / reallocate budget within the hard
   cap** — and writes the platform `ad_ref` + CTR/CPC/ROI **back onto the `AssetRef.metrics`/`status`**, so the
   Asset Library shows which creative is a `winner` vs `trashed`. (The "launch test batch → scale winners →
   trash losers" loop in the brief is **Studio produces variants, Ads runs the experiment**.) The Ads module
   owns the spend guardrails/approval gate for *ad money*; the studio owns them for *generation money* — two
   separate caps, both audited.
2. **→ Leads / CRM.** Ad clicks become **leads** in the existing `/leads` store; the winning creative's
   `asset_id` is tagged on the lead's source, so analytics can attribute leads → creative → campaign.
3. **→ Voice (`agent.py`/`caller.py`).** Leads flow into the existing AI **voice-call** pipeline (campaign
   knowledge + per-lead memory). The script the studio wrote for the ad and the call's opening can share the
   same campaign hooks (one source of truth = the campaign record), keeping the brand voice consistent across
   ad → call.
4. **→ WhatsApp (`whatsapp.py`).** Post-call follow-up can attach the **same campaign video asset** (the
   library URL) as a WhatsApp creative/brochure — the studio's assets are reusable across channels, not
   single-use for ads.
5. **→ Analytics / Billing Meter.** Generation spend is metered onto the existing `usage_events.json` /
   ledger so it shows in the **Billing Meter** beside Groq/ElevenLabs/Vobiz (cost-per-lead now includes
   creative cost). Ad performance + creative status feed the analytics/funnel charts. The loop —
   **asset → ad → lead → call → WhatsApp → revenue, with full cost attribution** — is closed.

> **Wiring is deferred:** these connections are *described* and exposed as pure callables / `AssetRef` fields.
> The orchestrator wires the Ads↔Library and Lead↔asset links when it un-defers spine wiring. The studio
> ships and tests **without** any of these live (dormant-safe).

---

## 10. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

> Until these are blank the module is a no-op (`not_configured`). Provide **only fal.ai + DO Spaces** to go
> live cheaply; everything else is optional. **Nothing here is needed for the offline acceptance test.** Most
> of these are the **engine's** creds (`automation-video.md` §9) — the studio adds almost none of its own.

**TIER 1 — minimum to go live (hosted, cheapest path) — these are the ENGINE's creds:**
| Env var | What it is | Where |
|---|---|---|
| `VIDEO_PROVIDER=fal` | selects the fal engine backend | (after key exists) |
| `FAL_KEY` | fal.ai API key (fronts Seedance/Kling/Veo/Wan/Runway) | fal.ai → dashboard → API Keys; add credits |
| `SPACES_KEY`,`SPACES_SECRET`,`SPACES_BUCKET`,`SPACES_REGION`,`SPACES_ENDPOINT` | DO Spaces (S3) for finished MP4s | DO console → Spaces → bucket + keys |
| `LLM_ROUTER_URL` | the in-house llm-router for scripts (likely already set) | existing infra; default `http://llm-router:8111` |

**TIER 2 — optional alternate engine backends (only if wanted):**
| Env var | For |
|---|---|
| `REPLICATE_API_TOKEN` (+ model id) | Replicate backend |
| `LUMA_API_KEY` (`luma-…`, Pro plan for full API) | Luma direct |
| `HIGGSFIELD_API_KEY` (+ `HIGGSFIELD_API_URL`) | Higgsfield direct ($0.10/s; the founder-named connector). Prefer reaching it via `FAL_KEY` to avoid a 2nd key. |
| `VIDEO_API_URL`,`VIDEO_API_KEY` | the engine's `generic` catch-all for any future vendor |

**TIER 3 — self-host (only when the engine's breakeven is hit):** DO **GPU quota** request +
`VIDEO_SELFHOST_URL`/`_TOKEN`/`_MODEL` (must be on the Apache-2.0 allowlist `wan*`/`cogvideox*`/`ltx*`/`mochi*`;
Hunyuan **refused** for ad output). See `automation-video.md` §9 Tier 3.

**STUDIO knobs (have safe defaults; founder may tune):**
`VIDEO_STUDIO_BATCH_SIZE` (5), `VIDEO_STUDIO_APPROVAL_THRESHOLD_USD` (1.00), `VIDEO_STUDIO_AUTO_APPROVE` (0),
`VIDEO_STUDIO_DAILY_CAP_USD` (20), `VIDEO_STUDIO_MONTHLY_CAP_USD` (300), `VIDEO_STUDIO_DEFAULT_ASPECT` (9:16),
`VIDEO_STUDIO_DEFAULT_DURATION_S` (6), `VIDEO_COST_SAFETY` (1.25), and the route map
`VIDEO_ROUTE_HOOK`/`_HERO`/`_PREMIUM`/`_SELFHOST` → model ids (defaults per §3a; verify exact ids in fal's
catalog at deploy — they drift).

> **Founder-side lead time (flag loudly):** fal/Higgsfield keys are instant; **DO GPU quota** (Tier 3) needs a
> support request; **DO Spaces** is instant. Ad-platform creds (Meta/Google) are the **Ads** module's
> multi-day approvals (`automation-ads.md` §6) — not needed to *generate* a batch, only to *launch* it.

---

## 11. OFFLINE ACCEPTANCE TEST (the gate — no creds, no network, no external calls)

`creative/video_studio/tests/` — must pass with **all env unset** and **no network**:

1. **Config gate:** `shared.config.is_configured()` is `False` with no env; `video_studio.config.which_route()`
   resolves defaults without raising.
2. **Dormant propose:** `service.propose_batch(tenant="t1", campaign_id="c1", size=5)` returns
   `{"status":"not_configured", ...}`, **does NOT raise**, makes **no LLM network call**, places **no hold**,
   writes **no** spend, and writes a batch record with `status="not_configured"`.
3. **Fake-engine happy path (the real coverage):** with a **fake LLM fn** (returns 5 canned `ScriptVariant`s)
   and the **`fake_engine`** injected as `render_fn`/`poll_fn`, `propose_batch`→`approve_batch`→`collect_batch`
   runs end-to-end: 5 scripts generated, 5 briefs built, batch estimate computed, hold reserved (JSON
   hold-store), 5 fake jobs "succeed", 5 `AssetRef`s registered in `shared.library`, batch → `complete`, hold
   settled — **all offline, zero sockets.**
4. **Script-angle determinism:** `script.build_variants(canned_campaign, size=5)` yields 5 **distinct angles**
   (`pain_point/social_proof/offer_led/urgency/founder_voice`) and honors `lang` from the campaign
   (multilingual brief). Pure-function with the fake LLM.
5. **Brief mapping:** `brief.from_variant(variant, route="hook")` sets the right `model` from the route map and
   `aspect_ratio="9:16"`, `with_audio` per options — golden-dict compare, no send.
6. **Cost / approval / cap guards (deterministic, offline):** batch estimate = Σ per-clip (per-second AND
   flat-rate modes both tested); a batch over `APPROVAL_THRESHOLD` yields `approval.required=True` and does NOT
   fan out until `approve_batch`; a batch over `DAILY_CAP` is refused `error:cap_exceeded` with **no fan-out**.
7. **Content-safety-before-spend:** a variant containing a denylisted term returns `error:content_blocked`,
   is **dropped from the batch before reserve/fan-out**, and the fake engine's `render_fn` is **never called**
   for it (assert call-count).
8. **Partial completion + release:** fake engine fails 2 of 5 jobs → batch ends `partial`, 3 `AssetRef`s
   registered, the 2 failed jobs **release** (not "refund") their hold share; settle = 3-job actual.
9. **Asset Library:** `service.list_assets(campaign_id="c1", kind="video")` returns the 3–5 registered assets,
   filterable by `status`; `promote_winner(asset_id)` flips `status="winner"` and `_audit` records it (fake
   audit sink).
10. **Never-raises invariant:** monkeypatch the LLM fn AND the engine `render_fn` to throw → every public
    function still returns a dict with an `error:`/`not_configured` status, never propagates (mirrors
    `whatsapp.py`'s `try/except Exception`).

Run: `pytest droplet_work/creative/video_studio/tests -q`. **Green with zero network = acceptance.** The
dormant no-op path + the fake-engine/fake-LLM path together prove the whole studio offline.

---

## 12. HONEST REAL-vs-HYPE

- **REAL:** fal/Replicate are genuine one-key gateways to every 2026 flagship (Seedance 2.0, Kling 3.0 Omni,
  Veo 3.1, Runway 4.5, Wan 2.7); free queue wait + pay-per-use; the async-queue shape is stable; Wan 2.7 is
  genuinely Apache-2.0 and self-hostable; Higgsfield has a first-party API; **batch creative testing is the
  actual winning 2026 ad playbook** (15–25 variants/ad-set/week). LLM ad-script drafting is genuinely useful.
- **HYPE / traps (resisted in the design):**
  - **"AI makes the finished ad in one tap."** No — it makes **draft variants**. The batch is a *testing*
    batch; a human approves spend, and the *market* (Ads CTR/ROI) picks the winner. We position it as a
    draft/variation + experiment engine with an approval gate, not a fire-and-forget agency.
  - **"Self-host is cheaper."** False at bursty ad volume — the GPU bills idle; hosted wins until a sustained
    queue (engine §8). Don't lead with self-host.
  - **"Just use HunyuanVideo."** License trap — output banned in EU/UK/South Korea + 100M-MAU ceiling;
    refused for ad output. Use Wan/CogVideoX/LTX (Apache-2.0).
  - **"It's instant."** No — 30s–6min/clip, ×N for a batch. The whole module is async *because* of this.
  - **"Flagship audio/4K at $0.05/s."** No — cheap tiers (Wan/Veo-Fast) are for drafts; flagship audio/4K is
    **5–10× dearer**. The batch cost estimator + caps + approval gate exist precisely because model choice
    swings spend by an order of magnitude — a 5-clip Veo-4K-audio batch is real money.
  - **"Consistency across shots is solved."** Still the weak spot; Runway Gen-4.5's reference/character
    control is the best lever, kept one route-string away.

---

## 13. BUILD SEQUENCE (units a build agent ships, each crash-safe + offline-verifiable)

1. `shared/{config,library,cost,audit,llm}.py` + `video_studio/schema.py` + `store.py` → unit test:
   create/read/list a batch + register/list an asset offline. ✅ commit.
2. `script.py` (fake-LLM angle generation) + `brief.py` (route map → VideoBrief) → angle/brief goldens. ✅ commit.
3. `engine.py` (render_fn/poll_fn adapter: real `automation.video.client` if importable, else `fake_engine`)
   + `fake_engine.py` → never-raises + not_configured passthrough. ✅ commit.
4. `batch.py` `generate_batch`/`collect_batch` + `service.py` callables + `test_batch_offline.py`
   (fan-out/collect/asset-register, fake engine). ✅ commit.
5. `cost.py` batch estimate + JSON hold-store + caps/approval + content-safety-before-spend + guard tests. ✅ commit.
6. `test_dormant.py` full dormant + never-raises invariant green; `endpoints.py` router DEFINED (not mounted). ✅ commit.
7. Hand the §6 endpoint table + §9 Ads/Library link points to the orchestrator for spine wiring (DO NOT edit
   `caller.py` here).

> Every unit is green offline before the next starts. An interruption costs at most one unit. No edits to
> `caller.py`/`agent.py`. No git (orchestrator commits). No duplication of engine provider/webhook/wallet code.

---

## 14. REFERENCES (sources, accessed 2026-06-09)

Studio-specific sources. The deep provider/pricing/webhook/license references live in
`design/automation-video.md` §13 (R: fal queue API, Replicate predictions, fal/Replicate webhook signatures,
HunyuanVideo license, DO GPU pricing, Wan flat-rate, etc.) — inherited, not repeated.

- **R1. Seedance 2.0 #1 image-to-video leaderboard (Elo 1,351), dialogue+lipsync+SFX in one pass (Apr 2026):**
  https://wavespeed.ai/blog/posts/introducing-bytedance-seedance-2-0-image-to-video-on-wavespeedai/ ;
  https://lipsync.video/seedance-2
- **R2. 2026 model picks for marketers — Seedance/Kling Omni/Veo 3.1/Runway Gen-4.5, audio/lipsync/consistency:**
  https://www.teamday.ai/blog/best-ai-video-models-2026 ; https://pixflow.net/blog/best-ai-video-generator/
- **R3. AI video API per-second pricing (Veo 3.1 Fast $0.10/s 720p / $0.30 4K, Sora 2, Kling, Runway), Apr 2026:**
  https://www.buildmvpfast.com/api-costs/ai-video
- **R4. fal.ai queue API + webhooks + prepaid/pay-per-use, free queue wait, 600+ models incl. all flagships:**
  https://fal.ai/pricing ; https://fal.ai/docs/documentation/model-apis/pricing
- **R5. Per-second cross-vendor (Wan 2.5 $0.05/s, Kling 2.5 Turbo $0.07/s, Kling 3.0 ~$0.029/s; Wan 2.7
  first/last-frame + audio sync):** https://devtk.ai/en/blog/ai-video-generation-pricing-2026/ ;
  https://vidflux.ai/ai-video-generator
- **R6. Higgsfield first-party API — header key, $0.10/s direct, text/image/Soul modes, dop-lite/turbo/preview:**
  https://www.pixazo.ai/models/higgsfield ; https://wavespeed.ai/docs/docs-api/higgsfield/higgsfield-dop-image-to-video
- **R7. Higgsfield image-to-video API docs (Segmind, $0.16–$0.70/gen):** https://www.segmind.com/models/higgsfield-image2video/api
- **R8. Ad-creative batch testing is the 2026 winning playbook — 20–50 creatives/mo, Meta favors 15–25
  variants/ad-set/week:** https://www.adstellar.ai/blog/automated-instagram-ad-creative-generation ;
  https://www.get-ryze.ai/blog/ai-creative-meta-ads-agents-generate-test-variations
- **R9. AI agents generate 15–20 variations in minutes, structured test, scale winners:**
  https://www.imagine.art/blogs/how-to-use-ai-to-test-ad-creative-variations
- **R10. Sibling/inherited specs (local):** `design/automation-video.md` (the async video ENGINE this studio
  calls), `design/automation-ads.md` (Autonomous Ads — the experiment runner), `design/automation-image.md`
  + `design/automation-threed.md` (sibling Creative-Studio sub-pages), `design/credit-ledger-firewall.md`
  (`reserve/settle/release` wallet seam).

---

## 15. RED-TEAM SELF-CHECK (folded — adversarial pass, 2026-06-09)

- **RTC-1 — No duplication of the engine.** This module deliberately does NOT re-implement provider switches,
  webhook signature verification, wallet holds, DO Spaces upload, the license gate, or the content-safety
  screen — all live in `automation-video.md`'s engine and are reached via the single `engine.py` `render_fn`
  seam. The studio's only new infra is **batch orchestration + Asset Library + script layer**. If a reviewer
  finds this module re-coding a provider body, that is a bug against this spec.
- **RTC-2 — Coupling risk if the engine isn't built yet.** Mitigated: `engine.py` imports
  `automation.video.client` lazily in `try/except`; on ImportError it falls back to `fake_engine`. The studio
  is therefore shippable and **fully testable before the engine exists**, and "upgrades transparently" when it
  does. The offline test exercises the fake path; a thin integration test (engine present, still dormant
  without keys) is added when the engine lands.
- **RTC-3 — Line-number drift in `caller.py` seams.** Per `automation-video.md` RTF-6, all cited spine symbols
  (`resolve_tenant`, `need_auth`, `can`, `_audit`, `_charge_call`, `VAR`/`_read`/`_write`, `whatsapp.is_configured`)
  are located by **grepping the symbol**, never a line number. The build agent must do the same.
- **RTC-4 — `release()` not `refund()`.** The wallet seam exposes `reserve/settle/release`; "release the hold"
  everywhere, `refund` is only a ledger `kind` string. (`automation-video.md` RTF-2.)
- **RTC-5 — Batch cost is N×, so guards are batch-level.** The approval gate + caps + estimate operate on the
  **whole batch before fan-out**, not per-clip — a 5-clip Veo-audio batch is real money and must be gated as a
  unit. Verified in §7.
- **RTC-6 — Model ids drift monthly.** The route map ships **defaults**, but the build agent/founder MUST
  verify exact fal model ids at deploy (e.g. `fal-ai/seedance-2.0/...`, `fal-ai/kling-3.0/...`); the
  provider-agnostic engine makes any rename a one-string env change. Stated in §3a/§10.
- **RTC-7 — LLM seam is `llm-router` `/v1/llm/generate`, injected, fake-able.** No new LLM vendor/key; the
  offline test uses a fake LLM fn so script generation is network-free. (Matches the ads/marketing/image
  specs.)

**Verdict: GO.** Tools are real and ACTIVE in 2026; the dormant-until-creds contract is non-breaking by
construction (greenfield `creative/`, nothing imported by `caller.py`/`agent.py`); spend/approval/audit guards
are batch-level and real; the engine is reused not duplicated; the whole studio is verifiable offline via the
fake renderer + fake LLM. This powers the **Creative Studio ▸ Video Studio** sub-page and feeds the
Asset Library → Autonomous Ads revenue loop.

---

## RED-TEAM FIXES (folded)

> External adversarial pass (2026-06-09), **distinct from §15's internal-consistency self-check**. §15 verified
> the claims the doc *makes*; this section attacks what the doc *omits* and what it *cannot verify from inside*.
> Disk + web verification was actually run (results below); the fixes are folded as binding requirements on the
> build agent. **None of these block — verdict stays GO** — but they are mandatory caveats, not nice-to-haves.

### RTX-1 — LIKENESS / CONSENT / SYNTHETIC-MEDIA GATE (the real gap; the content denylist does NOT cover it)
The doc leans hard on **lip-sync** (Kling "5 languages incl. Hindi", Seedance "precise lip-sync"), on
`image_url` → image-to-video, **and on a "founder_voice" angle** — i.e. putting an **identifiable real
person's face/voice** into AI video. The §7.5 safety screen is a **denylist for prohibited *content*** (sex,
violence, hate, etc.); it is **NOT a likeness/right-of-publicity/consent gate**, and the design never
mentioned this distinction. This is a legal + provider-ToS exposure independent of the content denylist:
provider ToS (fal/Replicate/Veo/Kling) routinely **prohibit generating identifiable real people without
consent**, and right-of-publicity / synthetic-media statutes apply regardless of which provider rendered it. A
shared `FAL_KEY` means **one tenant's non-consented face render can suspend the account for all tenants** (same
blast-radius logic the doc already uses for content AUP — but likeness was missed).
**FOLDED FIX (binding):**
- `VideoBrief` gains **`person_image: bool = False`** and **`likeness_consent: bool = False`**. If a brief's
  `image_url` is a **person** (or the angle is `founder_voice` with a voice/face reference), the studio
  **MUST NOT fan out** unless `likeness_consent=True` is explicitly recorded (with `consenter` + `at` in the
  audit trail). Absent consent → `{"status":"error:likeness_consent_required"}`, dropped before reserve/spend.
- **Default-safe posture:** `image_url` is treated as a **non-person product shot** by default; person uploads
  are an explicit, consent-gated opt-in. The acceptance test (§11) adds a case: person-image brief without
  consent is dropped **before** `render_fn` (assert call-count 0), mirroring the content-blocked test (§11.7).
- The engine's `safety.py` screen stays; this is an **additional** gate layered in `cost.py`/`brief.py` before
  reserve. It is dormant-safe (no consent field set on legacy briefs ⇒ only blocks person-image briefs).

### RTX-2 — AI-DISCLOSURE FLAG MUST RIDE THE ASSET → ADS HANDOFF (regulatory, currently absent)
Meta and Google now **require AI-generated-content disclosure on ads** in multiple jurisdictions (and label
synthetic media). Every asset this studio produces is **100% AI-generated**, yet `AssetRef` (§5d) carries no
disclosure signal, so the Ads module (§9.1) cannot set the platform's AI-content flag at launch.
**FOLDED FIX (binding):** `AssetRef.meta` gains **`"ai_generated": true`** (always true for studio output) and
an optional **`"disclosure_required_region": []`**. The §9.1 Ads handoff MUST read `ai_generated` and set the
platform's AI-content disclosure flag when launching the creative. One field; closes a compliance hole that
would otherwise surface only after an ad rejection or a regulator notice.

### RTX-3 — "VERIFIED ACTIVE" MODEL CLAIMS ARE POST-CUTOFF; THE SEAM (not the numbers) IS THE MITIGATION
The Seedance-2.0 / Kling-3.0 / Veo-3.1 rankings, Elo figures, and per-second prices (§3a) are **April-2026
facts** stated with a **January-2026 knowledge cutoff** — they were originally cross-checked only against the
doc's own citations (R1–R9), which is **circular**. This pass ran **independent web verification (2026-06-09)**:
- **Wan 2.7 = Apache-2.0, commercial use, no territory/MAU cap — CONFIRMED** (multiple independent 2026
  sources). The load-bearing "safe for paid ad output worldwide" basis **holds**.
- **fal.ai fronts Seedance 2.0 (live 2026-04-09), Kling 3.0 (~$0.029/s), Veo 3.1, Wan — CONFIRMED.** The
  one-key-gateway claim and the headline per-second prices **hold** as of mid-2026.
- **CAVEAT:** the exact **Elo numbers and the "#1 on the *image-to-video* leaderboard" superlative are
  point-in-time and leaderboard-specific** (independent sources surface different Elos on the *text-to-video*
  board — not a contradiction, a different board). **Do not treat any specific Elo/rank/price as durable.** The
  **real, honest mitigation is the provider-agnostic seam**: model id, rank, and price are an **env-overridable
  one-string change** (`VIDEO_ROUTE_*`), so a monthly re-rank or price move is config, not code. **Frame the
  §3a table as "cited, point-in-time, env-overridable," never as a guarantee.** The build agent MUST re-verify
  exact fal model ids + live prices at deploy (already stated §3a/RTC-6 — reinforced here).

### RTX-4 — GROUND-TRUTH NIT: campaigns are JSON-dir backed, not a `models.py Campaign` class
§1's table cites the dropdown source as "`models.py` `Campaign`". Verified on disk: campaigns are served by
`GET /campaigns` (`caller.py:1868`) via `list_campaigns()` (`caller.py:843`) over a **JSON dir**
(`CAMPAIGN_DIR = VAR/"campaigns"`, `caller.py:109`) — there is **no `models.py Campaign` ORM class** in the
live tree. Harmless to the design (the dropdown reads `GET /campaigns` either way, READ-only, adds no columns),
but the build agent MUST read the campaign **JSON shape via `list_campaigns()`**, not hunt for an ORM model.

### RTX-5 — 3D HYPE IS OUT OF SCOPE HERE (task asked; closing the loop)
The review brief flags "3D + autonomous bidding" hype. **This is the *video* spec** — it makes **no substantive
3D claim** (3D appears only as a sibling row in the §0 sidebar map). 3D real-vs-hype belongs to
`design/automation-threed.md` and is **not adjudicated here**. **Autonomous bidding** *is* touched (§9.1) and is
honestly scoped: verified against `design/automation-ads.md`, the "autonomous" optimizer is **platform-native
Meta/Google auto-bidding + a deterministic rules engine under a HARD cap with a PAUSED-by-default human
approval gate** (its INVARIANT A/B) — **no black-box AI agent moves spend**. The studio's "two separate caps"
claim (generation money here, ad money there, both audited) is structurally correct and verified.

### Verification log (run this pass, on disk + web — not inherited)
- `droplet_work/creative/` **does not exist** → greenfield / non-breaking claim **holds** (Glob, empty).
- Spine symbols all present: `resolve_tenant`:371, `need_auth`:403, `can`:608, `_forbidden`:620, `_audit`:713
  (signature `(request, tenant, action, object_type, object_id, channel, meta)` matches §6/§7.6 exactly),
  `_charge_call`:1383, `VAR`:108, `_read`:444/`_write`:450, `_STORE_LOCK`:259, `LEDGER_DIR`:122 (`caller.py`).
- `whatsapp.py`: `is_configured()`:107, `not_configured` returns, `try/except Exception` round all I/O, env
  read at call time → the dormant contract this module mirrors is **real**, byte-for-byte.
- `credit-ledger-firewall.md`: methods are `reserve()/settle()/release()/topup()/balance()` — **`release()` not
  `refund()`** confirmed; studio (RTC-4) already uses `release()`. ✔
- `automation-ads.md`: INVARIANT A (hard cap), INVARIANT B (PAUSED→human approval), deterministic optimizer —
  the autonomous-spend guardrails the studio defers to **exist and are real**. ✔
- Web (2026-06-09): Wan 2.7 Apache-2.0 ✔; fal fronts Seedance 2.0/Kling 3.0/Veo 3.1/Wan ✔; exact Elo/price =
  point-in-time, seam is the mitigation (RTX-3).
```
