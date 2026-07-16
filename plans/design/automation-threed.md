# DESIGN SPEC — 3D Modeling Automation ("threed") for Famit Revenue OS

> A **provider-agnostic, dormant-until-creds** module that turns a product/listing photo (or text
> prompt) into a textured 3D asset (`.glb`) usable in ads, listings and a 360° web viewer — composed
> from ACTIVE/maintained 2026 OSS + vendor APIs. Like the WhatsApp module, it is a graceful **NO-OP**
> returning `{"status":"not_configured"}` until the founder pastes keys. **Verifiable fully offline.**

Status: DESIGN — READY TO BUILD (no code shipped by this pass).
Scope rule honored: **NEW files only under `droplet_work/automation/`**. Does **NOT** edit
`caller.py` / `agent.py` (backend spine; final wiring deferred to the orchestrator).
Author: staff-eng research+design pass. Last updated: 2026-06-09.

---

## 0. HONEST FEASIBILITY — REAL vs HYPE (read this first)

The brief asks for "honest feasibility for real-estate/ads." The evidence (cited §7) splits sharply
into a **GREEN zone that works in production today** and a **RED zone that is still hype**. Building
the wrong one wastes the founder's money, so the module is deliberately scoped to the GREEN zone and
**refuses** (returns a typed error, never a bad asset) for the RED zone.

**GREEN — works today, ship this:**
- **Single discrete OBJECT from one photo** → textured `.glb`: furniture, appliances, a product, a
  packaged good, a car, a single piece of decor. 2026 image-to-3D (Meshy 6 / Tripo v2.5+ / Rodin
  v2.5 / Hunyuan3D-2.1 / TRELLIS.2) produces **production-grade meshes with PBR textures** for these
  in ~30–120 s [Meshy, Tripo, Hunyuan3D-2.1, TRELLIS.2 — §7].
- **360° spin / "view in 3D" / AR-place** for an e-commerce or real-estate *listing item* (a sofa, a
  modular kitchen, an appliance the developer is selling). This is the Google "shoppable 3D" pattern
  and is a proven revenue lever [Google Research — §7].
- **Ad creative B-roll**: a clean rotating hero object on a generated/branded background. The 3D asset
  is the durable part; turntable render + compositing is deterministic.

**RED — DO NOT promise (the module hard-refuses these inputs):**
- **A whole building / apartment / interior scene from a photo.** Multi-view consistency is "AI's
  Achilles heel" — you cannot get 8–12 coordinated, materially-identical renderings of the *same*
  building, and outputs contain "architectural impossibilities" needing heavy cleanup
  [Ravelin3D, Chaos — §7]. This is concept/feasibility-stage tooling, **not** a production renderer.
- **Floor-plan → walkable BIM model.** Outputs lack Revit-native parametric data; "significant cleanup
  pass before presentable" [Chaos/Revit note — §7].
- **Guaranteed game-ready / animation-ready topology** unattended. AI meshes still often need
  retopology + UV cleanup; auto-retopo (Tripo/Meshy remesh) helps but is **not** a zero-touch
  guarantee for rigging [uMCAD, Alpha3D — §7]. The module exposes a `remesh`/`quad` option but flags
  the result `topology:"auto_unverified"`.

**Net honest verdict:** Build a **"photo of a thing → rotatable/AR 3D asset for ads & listings"**
pipeline. That is genuinely automatable and revenue-relevant for Famit's real-estate/ads clients.
Do **not** build "photo of a house → 3D house," and do not let the UI imply it. The module enforces
this in code via an input-type gate (§4.4), so the honesty is structural, not just documentation.

---

## 1. CHOSEN TOOLS + WHY (provider-agnostic, with a self-host win)

The module is **multi-provider behind one interface** (`THREED_PROVIDER` selects). Every provider
listed is ACTIVE in 2026 (avoiding abandoned projects per the brief). All converge on the *same
async shape* (POST create-task → poll task → download `.glb`), which is exactly why one adapter fits
all of them — the WhatsApp `_build_body(provider, …)` pattern generalizes cleanly.

| Provider id | Tool | Hosting | License / commercial | Why chosen / role |
|---|---|---|---|---|
| `meshy` | **Meshy 6** | Vendor API | Paid-plan assets privately licensed, **no attribution**; free plan is CC-BY (avoid for commercial) [§7] | **Default managed API.** Mature REST, predictable credits, retex/remesh/rig/animate built in. |
| `tripo` | **Tripo v2.5+** | Vendor API | **Pro tier required** for commercial; free plan non-commercial [§7] | Strong geometry + built-in retopology; good price/quality. Secondary managed option. |
| `rodin` | **Hyper3D Rodin v2.5** | Vendor API (direct or via fal/WaveSpeed) | Commercial OK on Business plan/API; pay-per-gen ~$0.30–0.40/run [§7] | Best for clean UVs + quad/high-poly when topology matters. |
| `trellis` | **Microsoft TRELLIS.2 (4B)** | **SELF-HOST** (DO GPU droplet) | **MIT** — commercial, no royalties [§7] | **The self-host win.** Released Dec 2025, SOTA image-to-3D, MIT. Zero per-asset vendor cost once the GPU is up; full data control. |
| `hunyuan` | **Tencent Hunyuan3D-2.1** | **SELF-HOST** (DO GPU droplet) | **Tencent Hunyuan 3D 2.1 Community License** (NOT Apache-2.0); open weights, production PBR materials [§7]. ⚠️ **License explicitly does NOT apply in EU/UK/South Korea** (territory carve-out, verified in LICENSE) | Self-host alternative to TRELLIS; 6 GB VRAM shape / 16 GB shape+texture — cheaper GPU. Fine for India-based Famit; the geo carve-out is a real legal constraint, flagged in the cred sheet. **If a clean OSI license matters, prefer `trellis` (MIT).** |

**Decision logic baked into the module:**
- **Founder's fastest path to value** = a managed API (`meshy` default) — paste one key, working in
  minutes, no GPU.
- **Cost-optimized at scale** (the brief's explicit "self-host on DigitalOcean where it wins") =
  flip `THREED_PROVIDER=trellis` (or `hunyuan`) and point `THREED_SELFHOST_URL` at a DO GPU droplet
  running the model's HTTP server. Break-even math in §6.
- **Provider-agnostic by construction:** the founder swaps providers with one env var; no code change.
  Real names now (Meshy/Tripo/Rodin/TRELLIS/Hunyuan) live in a `DISPLAY_NAMES` map exactly like
  `vendors/__init__.py`, so swapping to abstract labels later = edit one dict.

**Renderer (for the 360°/turntable + ad B-roll), self-hosted, no per-asset cost:**
- **Blender 4.x headless** (`blender -b -P render_turntable.py`) on CPU/GPU — deterministic, free,
  battle-tested. Produces a 36-frame turntable PNG sequence + optional MP4 (ffmpeg). This is the
  "compose deterministic, offline-testable" piece. Online web viewer = **`<model-viewer>`** (Google,
  MIT) — a single web component that renders `.glb` with AR on mobile, **zero backend**.

---

## 2. WHERE IT FITS (architecture, non-breaking by construction)

```
droplet_work/
  automation/                      # NEW namespace (this module + future automation modules)
    __init__.py                    # DISPLAY_NAMES, redact(), PROVIDER_IDS  (mirrors vendors/__init__.py)
    threed.py                      # the public module — generate_3d(), status(), poll(), render_turntable()
    _http_async.py                 # async POST/GET w/ retry+backoff, never-raises (mirrors vendors/_http.py, async)
    providers/
      __init__.py
      meshy.py                     # build_create_body / parse / urls   (per-provider request shapes)
      tripo.py
      rodin.py
      selfhost.py                  # TRELLIS.2 / Hunyuan3D-2.1 HTTP server contract (one shape for both)
    render/
      render_turntable.py          # Blender headless script (stdlib + bpy); offline, deterministic
    selfhost/
      trellis_server.md            # exact DO GPU droplet recipe (image, GPU, systemd, /infer contract)
      hunyuan_server.md
  var/
    threed/                        # OUTPUT store (mirrors var/campaigns, var/rag_context disk pattern)
      jobs/<job_id>.json           # job record: input, provider, status, asset paths, cost, audit ts
      assets/<job_id>.glb          # the mesh
      renders/<job_id>/*.png|mp4   # turntable frames + video
```

**Why this shape is safe:**
- It is **purely additive**: a new top-level `automation/` package + a new `var/threed/` store. Nothing
  imports it yet (wiring deferred). Importing `automation.threed` with no keys set is side-effect-free.
- It mirrors three patterns the codebase already trusts: (a) the **dormant adapter** = `whatsapp.py`;
  (b) the **vendor adapter family** = `vendors/` (`__init__.py` display-names + `_http.py` never-raise
  client + per-vendor file); (c) the **disk-as-IPC store** = `var/campaigns/<id>.json` /
  `var/rag_context/<room>.json` (`dynamic-context-rag.md:38`). The 3D job/asset store is the same idea.
- **Async-first** because the eventual call site is FastAPI (`caller.py` is async) and 3D gen is a
  long poll (30–120 s). The adapter never blocks the event loop; it polls with backoff and can also be
  driven fire-and-forget (create → return `job_id` → webhook/poll later).

---

## 3. THE DORMANT-UNTIL-CREDS CONTRACT (the core requirement)

Identical philosophy to `whatsapp.py` and the `vendors/*` adapters:

- **`is_configured()` / `status()`** read env only. With nothing set → `"not_configured"`. The module
  **never raises** into a caller and **never makes a live external call** when unconfigured.
- **`generate_3d(...)` with no creds** returns `{"status":"not_configured","provider":<id>,...}`
  immediately — no network, no exception, exactly like `send_whatsapp` returning the no-op dict.
- **Secrets are redacted** in every log (first/last 4 only) via the shared `redact()` helper copied
  from `vendors/__init__.py`.
- **Self-host path is also dormant:** if `THREED_PROVIDER=trellis` but `THREED_SELFHOST_URL` is unset,
  same graceful `not_configured`. If the URL is set but unreachable, a typed `error:selfhost_unreachable`
  (never a crash).
- **Offline by default in tests:** a `THREED_OFFLINE=1` (or absence of any key) short-circuits all I/O
  and lets the acceptance test (§8) run with **zero external calls**, deterministically.

---

## 4. PUBLIC INTERFACE (files / functions / endpoints / data)

### 4.1 `automation/threed.py` — the single public surface

```python
# --- configuration (env only; all blank today => dormant) ---
def status() -> str            # "not_configured" | "configured" | "error"
def is_configured() -> bool
def provider() -> str          # current THREED_PROVIDER (default "meshy")
def capabilities() -> dict     # {provider, can_generate, can_render, can_view, selfhost} for the UI

# --- core (async; never raises) ---
async def generate_3d(
    *, image_url: str | None = None, image_b64: str | None = None,
    prompt: str | None = None,            # text-to-3D path
    input_kind: str = "object",           # GATE: must be "object"|"product"|"decor"|"vehicle"
    options: dict | None = None,          # {texture:bool, pbr:bool, remesh:"quad"|None, target_polycount:int}
) -> dict
# -> {"status": "queued"|"not_configured"|"error:...", "job_id": str|None,
#     "provider": str, "external_task_id": str|None}

async def poll(job_id: str) -> dict
# -> {"status":"PENDING|IN_PROGRESS|SUCCEEDED|FAILED|not_configured|error:...",
#     "glb_path": str|None, "thumbnail": str|None, "topology": "auto_unverified"|"remeshed",
#     "credits_or_cost": float|None, "provider": str}

def render_turntable(job_id: str, *, frames: int = 36, fmt: str = "mp4") -> dict
# -> {"status":"ok|error:...", "frames_dir": str, "video_path": str|None}   # Blender headless, offline-safe

def viewer_html(job_id: str) -> str
# returns a self-contained <model-viewer> snippet pointing at /threed/asset/<job_id>.glb (no backend dep)
```

### 4.2 Input-type GATE (structural honesty — §0 enforced in code)

`generate_3d` rejects RED-zone inputs **before any spend**:
```python
ALLOWED_KINDS = {"object", "product", "decor", "vehicle", "furniture", "appliance"}
REFUSED_KINDS = {"building", "house", "interior", "floorplan", "scene", "room"}
# input_kind in REFUSED_KINDS -> {"status":"refused_unsupported_kind", ...}  (no external call, no spend)
```
This makes the "don't promise 3D houses" verdict a **runtime guarantee**, not a footnote.

### 4.3 Provider adapter contract (`providers/<id>.py`)

Each provider module is pure functions (no I/O — testable offline):
```python
BASE: str                                   # e.g. "https://api.meshy.ai"
def create_request(payload, key) -> (url, headers, json_body)   # POST shape for this provider
def parse_create(resp_json) -> external_task_id
def poll_request(task_id, key) -> (url, headers)
def parse_poll(resp_json) -> {"status","glb_url","thumbnail","cost"}   # normalized to our schema
```
Concrete, verified shapes (so the orchestrator can wire real keys without re-researching):
- **meshy**: `BASE=https://api.meshy.ai`; create `POST /openapi/v2/image-to-3d` (or `/text-to-3d`);
  header `Authorization: Bearer <key>`; poll `GET /openapi/v2/image-to-3d/{id}`; status field `status`
  ∈ {PENDING, IN_PROGRESS, SUCCEEDED, FAILED, CANCELED}; asset in `model_urls.glb`. [§7]
- **tripo**: `BASE=https://api.tripo3d.ai`; create `POST /v2/openapi/task` (`type:"image_to_model"`);
  header `Authorization: Bearer <key>`; poll `GET /v2/openapi/task/{task_id}`; status in `data.status`;
  output in `data.output.pbr_model`/`model`. [§7]
- **rodin**: `BASE=https://hyper3d.ai/api` (or fal/WaveSpeed proxy); Bearer; create→poll→glb. [§7]
- **selfhost** (TRELLIS.2 / Hunyuan3D-2.1): `THREED_SELFHOST_URL` + optional `THREED_SELFHOST_TOKEN`;
  create `POST {url}/infer` (multipart image or `{prompt}`) → returns `{task_id}`; poll
  `GET {url}/result/{task_id}` → `{status, glb_url}`. One shape serves both self-host models; the
  droplet server (§5) adapts each model to it.

### 4.4 Dormant HTTP endpoints (DESIGN ONLY — orchestrator adds to `caller.py` later)

Mirrors the existing `POST /whatsapp/send` + `GET /whatsapp/log` rail; all return
`{"status":"not_configured"}` until keys exist. Spec'd here so wiring is mechanical:

| Method & path | Auth (existing RBAC) | Body / query | Returns |
|---|---|---|---|
| `POST /threed/generate` | write role | `image_url\|image_b64\|prompt, input_kind, options` | `{status, job_id}` |
| `GET /threed/jobs/{job_id}` | read role | — | full job record (status, glb_path, cost) |
| `POST /threed/render/{job_id}` | write role | `{frames, fmt}` | `{status, video_path}` |
| `GET /threed/asset/{job_id}.glb` | read role | — | the `.glb` file (or 404) |
| `GET /threed/status` | read role | — | `capabilities()` (drives UI enable/disable) |
| `GET /threed/jobs` | read role | `tenant?, limit, offset` | recent jobs (tenant-scoped) |

### 4.5 Data shapes (disk = source of truth, mirrors `var/` stores)

`var/threed/jobs/<job_id>.json`:
```json
{ "job_id":"3d_ab12cd", "tenant_id":"t_x", "actor":"t_x", "created":"2026-06-09T..+05:30",
  "provider":"meshy", "input_kind":"product", "input":{"image_url":"...", "prompt":null},
  "options":{"texture":true,"pbr":true,"remesh":null},
  "external_task_id":"...", "status":"SUCCEEDED",
  "glb_path":"var/threed/assets/3d_ab12cd.glb", "thumbnail":"...png",
  "topology":"auto_unverified", "cost":{"unit":"credits","amount":30,"usd_est":0.42},
  "approved":true, "approved_by":"t_x", "audit_ref":"<audit_log line ts>" }
```

---

## 5. SELF-HOST RECIPE (the DigitalOcean win) — `automation/selfhost/*.md`

**When it wins (the honest number, §6):** an *always-on* GPU droplet only beats managed API at **high
volume**. Rough break-even vs Meshy Studio (~$60/mo / 4000 credits ≈ $0.45 per textured asset at ~30
credits/asset): a 24 GB-class DO GPU droplet runs on the order of **~$1k/mo always-on**, so break-even
is **~2,000+ assets/month** — NOT a few hundred. Self-host therefore only wins **with the idle-shutdown /
batch-spin pattern below** (pay GPU-hours, not 24×7): at, say, 2 GPU-hours/day the droplet cost drops
~10×, pushing break-even down to the low hundreds/month. So: **API first; self-host only once volume is
real AND idle-shutdown is in place.** The non-cost wins (full data control — client photos never leave
infra; MIT licensing on TRELLIS = no vendor lock) apply at any volume.

**TRELLIS.2 (4B, MIT) droplet:**
- DO GPU droplet with **NVIDIA L40S / A100 (≥24 GB VRAM)** — TRELLIS needs ≥24 GB (verified on A100/H100);
  Linux only [§7]. Hunyuan3D-2.1 alternative needs only **6 GB shape / 16 GB shape+texture** → a
  **smaller, cheaper** GPU (e.g. L4-class), the cost-optimized default for shape-only or modest texture.
- Wrap the model's inference in a tiny FastAPI server exposing the §4.3 `selfhost` contract
  (`POST /infer`, `GET /result/{id}`), `systemd`-managed, **bound to the private VPC** + DO firewall
  (egress-locked, same hardening posture as `fortress/FORTRESS_DEPLOY.md`). Famit's `caller.py` reaches
  it over `THREED_SELFHOST_URL=http://10.x.x.x:8080`.
- Cost-control: an **idle-shutdown** cron (power off droplet after N idle minutes) or DO's hourly
  billing + a queue that batches jobs and spins the droplet only when work exists (documented in the
  `.md`, since the founder is non-technical — click-by-click).

The two `.md` files are founder-followable deploy guides; the code contract is identical, so swapping
TRELLIS↔Hunyuan is an env flip.

---

## 6. SPEND / APPROVAL / AUDIT GUARDRAILS (production-grade, reuses existing rails)

3D gen costs real money per asset, so guardrails are first-class. **Reuse what already exists** rather
than inventing new infra (the codebase already has audit, ratelimit, billing, tenant limits):

1. **Pre-flight cost estimate + hard cap.** `generate_3d` computes the credit/USD estimate from a
   per-provider price map and refuses if it would exceed `THREED_MAX_USD_PER_JOB` (default e.g. $1) or
   the tenant's remaining 3D budget. No spend on a refused job.
2. **Per-tenant monthly budget**, stored beside the existing tenant-limits mechanism
   (`POST /tenants/{tid}/limits` already exists, `caller.py:2542`). New key `threed_monthly_usd`.
   Over budget → `{"status":"budget_exceeded"}`, zero external call.
3. **Approval gate (optional, env `THREED_REQUIRE_APPROVAL=1`).** Job is created `status:"awaiting_approval"`
   and **no provider call is made** until a manager-role hits `POST /threed/jobs/{id}/approve`. Default
   off for managed self-serve; on for high-cost self-host batch runs.
4. **Audit every mutating action** through the existing append-only `audit.py` (`record(...)`) — actions
   `threed.generate`, `threed.approve`, `threed.render` — same JSONL immutable log as `whatsapp.send`
   (`caller.py:2959`). Each job stores its `audit_ref`.
5. **Rate-limit** generate calls via existing `ratelimit.py` (per-tenant token bucket) — prevents a
   runaway loop from draining credits.
6. **Spend metering** rides the existing billing meter family (`vendors/` + `/billing/vendors`): add a
   `threed` line so 3D spend shows in the same billing UI. Self-host = $0 marginal (droplet flat cost).
7. **Secret hygiene:** keys in env only, never in `var/` job records, redacted in logs.

This means the founder gets a per-job cap, a per-tenant monthly budget, an optional human-approval
switch, a full immutable audit trail, and unified billing visibility — **before** a single credit is spent.

---

## 7. SOURCES (web research, June 2026 — ACTIVE tools only)

- Meshy pricing/credits/license — https://www.meshy.ai/pricing , https://docs.meshy.ai/en/api/pricing
- Meshy API base/auth/endpoints/polling — https://docs.meshy.ai/en/api/text-to-3d , https://www.meshy.ai/api
- Tripo pricing + commercial-tier requirement — https://www.tripo3d.ai/pricing , https://lorphic.com/tripo-ai-pricing-explained-guide/ , https://platform.tripo3d.ai/docs/billing
- Tripo API auth/endpoints — https://platform.tripo3d.ai/docs/generation , https://apidog.com/blog/how-to-use-tripo-3d-api/
- Rodin/Hyper3D v2.5 pricing + commercial — https://hyper3d.ai/pricing , https://fal.ai/models/fal-ai/hyper3d/rodin , https://wavespeed.ai/models/hyper3d/rodin-v2.5/image-to-3d
- TRELLIS.2 (**MIT** — verified on the HF model card; 4B, image-to-3D, ≥24 GB VRAM, Linux, Dec 2025) — https://huggingface.co/microsoft/TRELLIS.2-4B , https://github.com/microsoft/TRELLIS.2 , https://comfyui-wiki.com/en/news/2025-12-18-microsoft-trellis2-3d-generation
- Hunyuan3D-2.1 (**Tencent Hunyuan 3D 2.1 Community License — NOT Apache-2.0**; LICENSE verified: "DOES NOT APPLY IN THE EUROPEAN UNION, UNITED KINGDOM AND SOUTH KOREA"; open weights, 6/16 GB VRAM) — https://github.com/tencent-hunyuan/hunyuan3d-2.1 , https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-2.1/main/LICENSE
- Real-estate/arch-viz feasibility limits (multi-view inconsistency, not a production renderer) — https://ravelin3d.com/blog/ai-in-architectural-visualization-revolution-or-hype-2025-2026-reality-check.html , https://blog.chaos.com/best-ai-rendering-tools-for-architects-compared
- Topology/retopo reality + e-commerce 360° shoppable 3D — https://www.umcad.com/a58507 , https://www.alpha3d.io/kb/3d-modelling/ai-retopology/ , https://research.google/blog/bringing-3d-shoppable-products-online-with-generative-ai/

---

## 8. OFFLINE ACCEPTANCE TEST (no live external calls — must pass before wiring)

A `automation/_test_threed.py` (stdlib `unittest`, runnable as `python -m automation._test_threed`):

1. **Dormant import** — `import automation.threed` with **no env set** does not raise; `status()=="not_configured"`,
   `is_configured() is False`, `capabilities()["can_generate"] is False`.
2. **No-op generate** — `await generate_3d(image_url="http://x/p.png", input_kind="product")` returns
   `{"status":"not_configured",...}` and makes **zero** network calls (assert via a monkeypatched
   `_http_async` that fails the test if invoked).
3. **RED-zone refusal** — `input_kind="house"` (and "interior","floorplan") returns
   `{"status":"refused_unsupported_kind"}` with **no** external call and **no** spend — proves the
   honesty gate (§0/§4.2) is structural.
4. **Provider-shape unit tests (pure, offline)** — for each of meshy/tripo/rodin/selfhost,
   `create_request(payload,"FAKEKEY")` yields the documented URL + `Authorization: Bearer FAKEKEY`
   header + correctly-shaped body; `parse_poll(<canned SUCCEEDED json>)` returns a normalized record
   with the `.glb` URL. Uses **canned JSON fixtures**, never the network.
5. **Cost-cap guardrail** — a job whose estimate exceeds `THREED_MAX_USD_PER_JOB` returns
   `budget_exceeded` and triggers **no** provider call.
6. **Redaction** — `redact("sk-abcd...wxyz")` shows only first/last 4; a fake log line never contains the
   full key.
7. **Configured-but-mocked happy path** — set `THREED_PROVIDER=meshy`, `MESHY_API_KEY=FAKE`, monkeypatch
   `_http_async` to return canned create→poll JSON; assert a `job_id` is created, the job record is written
   to a temp `var/threed/jobs/`, `poll()` reaches `SUCCEEDED` with a `glb_path`, and the audit hook was
   called. **Still zero real network.**
8. **Renderer dormancy** — `render_turntable` with Blender absent returns `error:blender_unavailable`
   (no crash); the test asserts the contract, not an actual render (keeps CI dependency-free).

Pass criteria: all 8 green with **no network access and no GPU** — the whole module is provable on a
laptop, fully offline, before any key or droplet exists.

---

## 9. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

All blank today ⇒ module is dormant. Provide **one** managed provider to start (Meshy is the
fast path); add self-host later only if volume justifies it (§6).

**A. Pick ONE managed API to go live fast (recommended: Meshy):**
- `THREED_PROVIDER` = `meshy` (or `tripo` / `rodin`)
- `MESHY_API_KEY` — from a Meshy **Pro plan ($20/mo) or above** (API requires Pro+; paid assets are
  privately licensed, no attribution). Account: https://www.meshy.ai
- *(if tripo)* `TRIPO_API_KEY` — Tripo **Pro tier** (commercial rights require Pro; free is non-commercial).
  Account: https://platform.tripo3d.ai
- *(if rodin)* `RODIN_API_KEY` — Hyper3D **Business plan ($120/mo)** for commercial + API.
  Account: https://hyper3d.ai

**B. Optional self-host (only when volume beats API credits — §6):**
- `THREED_PROVIDER` = `trellis` (**MIT** — recommended for clean licensing) or `hunyuan`
  (**Tencent Hunyuan 3D 2.1 Community License**, NOT Apache; EU/UK/KR carve-out — see below)
- `THREED_SELFHOST_URL` — private URL of the DO GPU droplet (e.g. `http://10.x.x.x:8080`)
- `THREED_SELFHOST_TOKEN` — shared secret for that server (optional but recommended)
- **DigitalOcean GPU droplet** — TRELLIS.2 needs **≥24 GB VRAM (A100/L40S-class, Linux only)** (verified);
  Hunyuan3D-2.1 needs only **6 GB shape / 16 GB shape+texture** (cheaper GPU). ⚠️ **Hunyuan's license
  explicitly does NOT apply in the EU/UK/South Korea** (verified in the LICENSE file) — acceptable for
  India-based Famit, but a real legal constraint if a client/render target is in those regions. **Prefer
  `trellis` (MIT) unless the cheaper Hunyuan GPU footprint is decisive.**

**C. Guardrail knobs (optional; sane defaults if unset):**
- `THREED_MAX_USD_PER_JOB` (default e.g. `1.00`) — hard per-job spend cap.
- `THREED_REQUIRE_APPROVAL` (`0`/`1`, default `0`) — human approval before any paid generation.
- `THREED_OFFLINE` (`1` to force the no-network/no-op mode used by tests).

**D. No new account needed for rendering/viewing:** Blender (headless, free) + Google
`<model-viewer>` web component (MIT) are self-hosted with zero credentials.

---

### TL;DR for the founder
Paste **one** key — `THREED_PROVIDER=meshy` + `MESHY_API_KEY` (Meshy Pro, $20/mo) — and Famit can turn
a **product/listing-item photo into a rotatable, AR-ready 3D asset** for ads and listings. It will
**refuse** "turn this house photo into a 3D house" on purpose (that's still hype). When volume grows,
flip to a self-hosted **TRELLIS.2 (MIT)** or **Hunyuan3D-2.1 (Tencent Hunyuan 3D 2.1 Community License —
NOT Apache-2.0; EU/UK/KR carve-out + 1M-MAU re-license trigger)** DO GPU droplet for ~$0
marginal cost. Until a key is pasted, the whole module is a safe no-op.

---

## RED-TEAM FIXES (folded)

Adversarial review pass (2026-06-09). Each external claim was re-verified against the primary source;
each codebase rail was confirmed to exist on disk. **Verdict: GO** — every issue below is a doc/guardrail
fold-in, none is an architectural showstopper. Fixes are applied inline above and summarized here.

**Verified TRUE (no change needed):**
- **Tools are active + maintained in 2026.** TRELLIS.2-4B = MIT, released Dec 2025 (HF card + GitHub
  confirmed). Hunyuan3D-2.1 active (Tencent GitHub/HF). Meshy 6 / Tripo / Rodin are live commercial APIs.
- **License facts in the body (§1, §7) are correct.** TRELLIS.2 = MIT (clean OSI). Hunyuan3D-2.1 =
  Tencent Hunyuan 3D 2.1 Community License with the verified EU/UK/South Korea territory carve-out.
- **Codebase rails cited by §6 genuinely exist** (so guardrail reuse is real, not aspirational):
  `audit.record(...)` at `droplet_work/audit.py:60`; `POST /tenants/{tid}/limits` at
  `droplet_work/caller.py:2542`; rate-limit `allow(tenant_id, route_class)` in `droplet_work/ratelimit.py`;
  dormant no-op pattern matches `droplet_work/whatsapp.py` (`{"status":"not_configured"}`, never raises).
- **Dormant-until-creds + non-breaking is real.** Purely additive (`automation/` + `var/threed/`),
  nothing imports it, env-only config, offline acceptance test needs no network/GPU.

**FIX 1 — Factual license error in the TL;DR (corrected inline).** The TL;DR previously read
"Hunyuan3D-2.1 (Apache-2.0)", contradicting the corrected body. Hunyuan3D-2.1 is **NOT** Apache-2.0; it is
the Tencent Hunyuan 3D 2.1 Community License. Corrected in the TL;DR above to match §1/§7. *(This is the
single hard factual error found in the spec.)*

**FIX 2 — Hunyuan self-host carries TWO unstated license obligations (added).** Beyond the EU/UK/KR
carve-out already flagged, the LICENSE (verified at the primary source) also imposes: (a) a **1,000,000
monthly-active-user threshold** above which Licensee "must request a license from Tencent" — Famit must
re-license if any product using Hunyuan output crosses 1M MAU; and (b) an **Exhibit A acceptable-use /
prohibited-use policy** (no unlawful use, misinformation for elections, malware, impersonation, military
use, high-stakes automated decisions, unlicensed professional practice). These bind the self-host path.
Mitigation: the cred sheet (§9-B) must surface both; **prefer `trellis` (MIT, none of these strings
attached)** unless Hunyuan's cheaper GPU footprint is decisive. No code impact — a licensing/ops note.

**FIX 3 — "Safety guardrails" in §6 are SPEND-only; content/abuse guardrails are absent (gap flagged).**
This directly answers the review question "are safety guardrails real?": the spend guardrails (per-job USD
cap, per-tenant monthly budget, optional approval, immutable audit, rate-limit) are **real and verified**.
But §6 has **no content/abuse guardrail** — nothing inspects *what image* a tenant submits. The §4.2
input-kind gate filters object-vs-building (a *feasibility* gate), **not** an abuse gate. Real exposure:
generating 3D assets from arbitrary uploaded photos invites **IP / trademark-knockoff** misuse (a tenant
3D-scanning a competitor's branded product) and, on the Hunyuan self-host path, violation of Exhibit A.
Mitigation to add at wire-time (does not block this design): (a) a documented Acceptable-Use note that
3D generation is for assets the tenant owns/has rights to; (b) optionally route uploads through the
existing approval gate (`THREED_REQUIRE_APPROVAL=1`) for un-vetted tenants; (c) record the submitter in
the audit line (already specified) so misuse is traceable. **Honest answer: spend guardrails = real;
ToS/abuse guardrails = partial-to-absent, now flagged as a wire-time requirement.**

**FIX 4 — Meshy operating-cost framing understated (clarified).** Sources confirm Meshy API access is
**gated behind the Pro tier (~$20/mo)** AND generation is **pay-before-you-go credits purchased
separately** (Meshy-6 image-to-3D *with texture* = **30 credits/asset**, confirmed; cheaper non-6 models
= 15 credits textured). So the real cost is **$20/mo floor + per-asset credits**, not a flat $20/mo. The
TL;DR's "paste one key, $20/mo and you're going" understates operating spend. The §5/§4.5 break-even math
(~30 credits/asset, ~$0.42–0.45/textured asset) is **correct for Meshy-6** and stands; the cheaper
non-6 path would roughly halve per-asset cost and push self-host break-even *higher* — which only
strengthens the spec's "API first" conclusion. No design change; cost expectation clarified.

**FIX 5 — Provider endpoint shapes are research-grade, not integration-tested (residual).** The Meshy
endpoints (`/openapi/v2/image-to-3d`, Bearer auth, `model_urls.glb`) and the 5/10/15/30-credit costs are
confirmed from Meshy docs. The **Tripo** create/poll endpoint shape (`/v2/openapi/task`, `data.output`)
could **not** be re-confirmed (docs are a JS SPA opaque to fetch) — treat as unverified until integration.
This is contained by design: §4.3 provider modules are **pure functions with offline unit tests** (§8.4),
so a wrong URL fails a cheap offline test, never a live spend. **Residual: verify Tripo (and Rodin)
request/response shapes against live docs at wire-time before enabling those providers.**

### RESIDUAL RISKS (accept-and-track; none block GO)
1. **Tripo / Rodin endpoint shapes unconfirmed** — verify against live API docs at integration (FIX 5).
2. **Content/abuse guardrail not yet implemented** — add Acceptable-Use note + optional approval routing
   for un-vetted tenants before exposing generation to self-serve tenants (FIX 3).
3. **Hunyuan self-host licensing** — EU/UK/KR carve-out, 1M-MAU re-license trigger, Exhibit A AUP all
   apply; default to TRELLIS (MIT) to avoid them (FIX 2).
4. **Meshy operating cost** — budget $20/mo floor **plus** ~$0.42/textured asset (Meshy-6), not flat $20
   (FIX 4).
5. **Self-host $/mo is order-of-magnitude** — the ~$1k/mo 24GB-GPU figure is indicative; confirm current
   DO GPU droplet pricing before committing. Does not change the "API-first, self-host only with
   idle-shutdown at real volume" conclusion.
6. **`auto_unverified` topology** — meshes are not guaranteed rig/game-ready unattended; already disclosed
   in §0 and surfaced in the job record, but downstream consumers must not assume clean topology.
