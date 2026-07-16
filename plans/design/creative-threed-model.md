# DESIGN SPEC — CREATIVE STUDIO ▸ **3D PRODUCT MODEL** sub-page (`droplet_work/creative/threed_model/`)

> **Module id:** `threed-model` · **Code path:** `droplet_work/creative/threed_model/`
> **Creative-Studio sub-page it powers:** **"3D Product Model"** — the spatial-asset sub-page of the
> Creative Studio sidebar section (siblings: Ad Copy/Hooks, Image & Banner Studio, Video Studio,
> Landing Pages, Brochure/Catalog, plus the Creative-Batch orchestrator).
>
> **What this is (one line):** a vendor records a **multi-angle product/property video** → the module
> turns it into an **interactive 3D asset** (textured `.glb` mesh *or* a Gaussian-splat scene) → hosts a
> self-contained **VIEWER page** (rotate / zoom / inspect / AR) → emits a **shareable link** that drops
> into WhatsApp, the website, ad creatives and the catalog.
>
> **Status:** EXECUTION-READY DESIGN (no code shipped by this pass). A build agent implements this
> verbatim, one UNIT at a time, running the OFFLINE acceptance test (§9) before the next.
>
> **Constraints honored (verbatim from the brief + global rules):**
> - **NEW files ONLY under `droplet_work/creative/`.** This module does **not** live under `automation/`.
> - **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS:** a graceful NO-OP returning `{"status":"not_configured"}`
>   that **NEVER raises** until the founder pastes keys — the exact `droplet_work/whatsapp.py` pattern.
> - **DO NOT edit `caller.py` / `agent.py`** (backend spine; wiring deferred — endpoints below are
>   *described*, not implemented).
> - **NO git** (orchestrator commits). **Verifiable fully OFFLINE** (zero external calls, no GPU).
> - Compose **ACTIVE/maintained 2026 OSS + vendor APIs**; cost-optimized; self-host on DO where it wins.
>
> Research date: 2026-06-09. All chosen tools verified ACTIVE in 2026 (cited §8). Verified against live
> source under `C:\Users\kunal\Desktop\caps\droplet_work\` and the sibling design docs.

---

## 0. THE ONE DECISION THAT DEFINES THIS MODULE — engine vs. sub-page (read first)

There are **two threed specs** in `design/` and they are **not** duplicates. Keeping them straight is
the spine of this design:

| | `automation-threed.md` (sibling, already spec'd) | **`creative-threed-model.md` (THIS doc)** |
|---|---|---|
| Layer | **Low-level ENGINE** | **User-facing Creative-Studio SUB-PAGE** |
| Code home | `droplet_work/automation/threed/` | `droplet_work/creative/threed_model/` |
| Input | a single product **photo** / text prompt | a vendor's **multi-angle video** (the founder's exact flow) |
| Output | a `.glb` mesh | a hosted **viewer page** + **shareable link** (consumes the mesh) |
| Owns | provider adapters (Meshy/Tripo/Rodin/TRELLIS/Hunyuan), task→poll→`.glb` | **video→frames** extraction, **viewer hosting**, **share links**, **Gaussian-splat (property) path**, revenue wiring |

> **Layering rule (mirrors how `creative-batch` fans out to `automation/*`, and how the Video Studio
> sits on the video engine):** this sub-page **owns the multi-image generation call itself** (via its
> own `providers/`, §4.3) — it does **not** route the generate call through `automation/threed`, because
> that engine's public entry (`generate_3d(image_url | image_b64, …)`, single image — verified in
> `automation-threed.md §4.1`) takes ONE image, whereas PATH A fuses **3–4 frames in a single
> multi-image call**; calling a single-image entry four times does not yield one fused mesh. What this
> sub-page **delegates** to `automation/threed` when present (one `try: import … except: =None` seam) is
> the **shared infrastructure** the engine already owns: the resolved **provider key**, the
> **`THREED_SELFHOST_URL`** for the DO GPU droplet, and the **per-provider cost map** — so the two
> threed modules share one set of creds instead of duplicating them. *(Alternative, decided at wire-time:
> have `automation/threed` add a multi-image entry `generate_3d(image_urls=[…])` and delegate the call
> too; recorded as the integration contract, not assumed here.)* On top of generation this sub-page adds
> the **three things the engine does not do at all**: (1) turn a *video* into the multi-image input,
> (2) **host an interactive viewer page**, (3) mint a **shareable link** into the revenue loop. When the
> engine is **absent**, this module is fully self-contained (its own `providers/` + cost map) so it is
> testable standalone — it does **not** require the sibling to exist on disk (same independence rule
> `creative-batch` follows).

This avoids re-implementing provider adapters here while still delivering the founder's stated
end-to-end experience (record video → shareable 3D link).

---

## 1. HONEST FEASIBILITY — what works in 2026, and the property nuance (read second)

The brief names photogrammetry / 3D-reconstruction from a **multi-angle video** for **products AND
properties**. The 2026 evidence (cited §8) splits cleanly into **TWO production-real paths** — and the
property case, which mesh reconstruction famously fails, is **rescued by a different technology**:

**PATH A — OBJECT → textured `.glb` MESH (products, furniture, appliances, packaged goods, vehicles, decor).**
- No 2026 engine ingests *raw video*; the mature, production path is **multi-image-to-3D from 3–4
  angle frames** — described by Meshy itself as "the closest thing to photogrammetry without the rigor —
  you don't need 50+ overlapping photos or a turntable; 3–4 angles is usually enough" [Meshy — §8].
- So PATH A = **sample N clean frames from the vendor's turn-around video** (deterministic, offline,
  ffmpeg) → feed them to **Meshy-5 multi-image-to-3D** / **Tripo v2.5+ multiview-to-3D** /
  self-host **TRELLIS.2 / Hunyuan3D-2.1** → textured `.glb`. **GREEN — ship this.**

**PATH B — SCENE / PROPERTY → GAUSSIAN-SPLAT capture (apartments, interiors, a shop, a plot, a building
exterior — the real-estate "walk around it" experience).**
- Mesh engines **cannot** reconstruct a whole interior/building from a phone video — multi-view
  inconsistency is "AI's Achilles heel," outputs carry "architectural impossibilities" [Ravelin3D,
  Chaos — §8]. The sibling engine spec correctly **REFUSES** `building/house/interior/floorplan`.
- BUT the property case is **production-real via a different technology**: **NeRF / 3D Gaussian
  Splatting** (Luma 3D Capture). Point a phone, walk around the space 30–60 s, upload the video → Luma
  returns a photorealistic, *navigable* splat scene in minutes; it is embeddable on the web [Luma — §8].
  This is **capture, not reconstruction** — no mesh, no "impossibilities," and it is exactly what
  real-estate clients want. **GREEN for "view this property/space," not for "edit a BIM model."**

**The honesty gate, structural (not a footnote):** the sub-page asks the vendor to pick a **capture
kind**. `kind="object"` → PATH A (mesh). `kind="space"|"property"|"interior"` → PATH B (splat). PATH A
will **refuse** a `space` input (returns a typed error, no spend) and steer the user to PATH B; PATH B
is unavailable until a splat provider key exists, in which case the UI says so rather than producing a
broken mesh. **We never turn a house video into a fake 3D house mesh.** What we *do* is give properties a
real, navigable splat tour and products a real rotatable mesh — both genuinely automatable in 2026.

**RED — the module hard-refuses (typed error, no spend), so the UI cannot over-promise:**
- "Video of a house → editable/walkable BIM/Revit model" (splat is a *view*, not parametric geometry).
- "Guaranteed game-ready / rigged topology unattended" — meshes are flagged `topology:auto_unverified`.

---

## 2. WHERE IT FITS (architecture — purely additive, non-breaking by construction)

```
droplet_work/
  creative/
    threed_model/                    # NEW — this sub-page module (greenfield)
      __init__.py                    # DISPLAY_NAMES, redact(), KINDS, PATHS  (mirrors vendors/__init__.py)
      service.py                     # PUBLIC surface: create_capture(), status(), poll(), share(), capabilities()
      frames.py                      # video -> N sampled frames (ffmpeg if present; deterministic; offline)
      engine.py                      # mesh path: delegates to automation.threed if present, else self-contained
      splat.py                       # property path: Luma 3D Capture adapter (NeRF/Gaussian splat) — dormant
      providers/                     # used only when automation/threed is ABSENT (standalone fallback)
        __init__.py
        meshy_mv.py                  # Meshy-5 multi-image create/poll/parse  (pure funcs, offline-testable)
        tripo_mv.py                  # Tripo v2.5+ multiview create/poll/parse
        selfhost_mv.py               # TRELLIS.2 / Hunyuan3D-2.1 multi-image HTTP contract (one shape, both models)
      viewer/
        glb_viewer.html              # <model-viewer> template (mesh; rotate/zoom/AR) — self-contained, no backend
        splat_viewer.html            # Spark (Three.js) splat viewer template — self-contained
        share.py                     # mint share token + build shareable URL + WhatsApp/catalog/ad payloads
      _test_threed_model.py          # OFFLINE acceptance test (stdlib unittest; zero network, no GPU)
  var/
    creative/
      threed_model/                  # OUTPUT store (mirrors var/campaigns, var/creative/* disk pattern)
        jobs/<job_id>.json           # job record: tenant, kind, provider, status, asset paths, cost, share, audit ts
        frames/<job_id>/*.png        # sampled video frames (PATH A input)
        assets/<job_id>.glb          # mesh (PATH A)   |  assets/<job_id>.spz|.ply  (PATH B splat)
        thumbs/<job_id>.png          # poster image for share previews / catalog tiles
        shares/<token>.json          # public-share index: token -> job_id, kind, expiry, scope
```

**Why this shape is safe:**
- **Purely additive:** a new package under the already-greenfield `creative/` tree + a new
  `var/creative/threed_model/` store. Nothing imports it yet (wiring deferred). Importing it with no
  keys set is side-effect-free.
- It mirrors patterns the codebase already trusts: **dormant adapter** = `whatsapp.py`; **disk-as-IPC
  store** = `var/campaigns/<id>.json` + the `creative/*` `store.py` (atomic write + append); **spine
  import seam** = `caller.py:35-37` `try: import X except: X=None`.
- **Async-first** (the eventual call site `caller.py` is async; capture is a long poll, 30 s–minutes):
  the adapters never block the event loop — create → return `job_id` → poll/webhook later.

---

## 3. THE DORMANT-UNTIL-CREDS CONTRACT (the core requirement)

Identical philosophy to `whatsapp.py` and every `automation/*` adapter:

- **`is_configured()` / `status()` / `capabilities()` read env only.** Nothing set → `"not_configured"`.
  The module **never raises** into a caller and **never makes a live external call** when unconfigured.
- **`create_capture(...)` with no creds** returns `{"status":"not_configured","kind":…,"provider":…}`
  immediately — no network, no exception, exactly like `send_whatsapp` returning the no-op dict.
- **Per-path dormancy is independent:** the mesh path can be live (Meshy key set) while the splat/property
  path is dormant (no Luma key) — `capabilities()` reports each separately so the UI greys out only the
  missing one. If `automation/threed` is present, the mesh path simply delegates to it.
- **Self-host path also dormant:** provider = `trellis`/`hunyuan` but `THREED_SELFHOST_URL` unset → same
  graceful `not_configured`; URL set but unreachable → typed `error:selfhost_unreachable` (never a crash).
- **Secrets redacted** in every log (first/last 4 only) via the shared `redact()` helper copied from
  `vendors/__init__.py`.
- **Offline by default in tests:** absence of any key (or `THREED_OFFLINE=1`) short-circuits all I/O so
  the §9 acceptance test runs with **zero external calls**, deterministically. **Frame sampling and
  viewer-page generation run fully offline** regardless of creds — they need no vendor at all.

---

## 4. PUBLIC INTERFACE (files / functions / endpoints / data)

### 4.1 `creative/threed_model/service.py` — the single public surface

```python
# --- configuration (env only; all blank today => dormant) ---
def status() -> str            # "not_configured" | "configured" | "error"
def is_configured() -> bool    # True if EITHER mesh OR splat path is usable
def capabilities() -> dict     # {mesh:{can_generate,provider,selfhost}, splat:{can_capture,provider}, can_view:True, can_share:True}

# --- core (async; never raises) ---
async def create_capture(
    *, tenant_id: str, campaign_id: str | None = None,
    video_path: str | None = None,      # the vendor's multi-angle recording (PATH A samples frames; PATH B uploads whole)
    image_urls: list[str] | None = None,# alt: pre-shot 3-4 angle stills (skip frame sampling)
    kind: str = "object",               # GATE: "object|product|decor|vehicle|furniture|appliance" (mesh) | "space|property|interior" (splat)
    options: dict | None = None,        # {texture:bool, pbr:bool, frames:int=4, target_polycount:int, splat_quality:"draft|high"}
) -> dict
# -> {"status":"queued|not_configured|refused_unsupported_kind|budget_exceeded|error:...",
#     "job_id": str|None, "path":"mesh|splat", "provider": str, "external_task_id": str|None}

async def poll(job_id: str) -> dict
# -> {"status":"PENDING|IN_PROGRESS|SUCCEEDED|FAILED|not_configured|error:...",
#     "path":"mesh|splat", "asset_path": str|None, "asset_kind":"glb|spz|ply",
#     "thumbnail": str|None, "topology":"auto_unverified|remeshed|na",
#     "cost":{"unit":…, "amount":…, "usd_est":…}|None, "provider": str}

def viewer_html(job_id: str) -> str
# returns a self-contained viewer page: <model-viewer> for a .glb, Spark splat-viewer for a .spz/.ply.
# Pure string templating from the on-disk asset — NO backend dependency, generated fully offline.

def share(job_id: str, *, channels: list[str] | None = None, expires_days: int = 30) -> dict
# mints a share token, writes shares/<token>.json, returns:
# -> {"status":"ok|not_ready|not_configured", "token":str, "viewer_url":str,
#     "whatsapp_payload":{...}, "catalog_card":{...}, "ad_asset_ref":{...}}
# channels in {"whatsapp","website","ad","catalog"} shape the payloads; NO message is sent here
# (handoff to whatsapp.py / catalog / ads is the orchestrator's wiring, kept dormant).
```

### 4.2 Capture-kind GATE (structural honesty — §1 enforced in code, before any spend)

```python
MESH_KINDS  = {"object","product","decor","vehicle","furniture","appliance"}
SPLAT_KINDS = {"space","property","interior","room","exterior","shop","plot"}
# kind in MESH_KINDS  -> PATH A (multi-image -> .glb)
# kind in SPLAT_KINDS -> PATH B (video -> Gaussian splat). If splat provider absent -> {"status":"not_configured","path":"splat"}.
# kind == mesh but engine asked to build a "house" -> refused upstream; a SPLAT_KIND sent to PATH A -> {"status":"refused_unsupported_kind"}.
# unknown kind -> {"status":"refused_unsupported_kind"}  (no external call, no spend)
```
This makes "don't fake a 3D house mesh; route properties to splat" a **runtime guarantee**, not a
footnote.

### 4.3 Mesh-path resolution (own-the-generate; share infra with the engine)

The multi-image generate call is **owned here** (the engine's public entry is single-image, §0). The
sibling engine, when present, is imported only to **share creds/cost infra**, not to run generate:

```python
# engine.py
try:
    from automation import threed as _engine           # imported for SHARED INFRA, not the generate call
except Exception:
    _engine = None
# resolve_key()      = _engine's provider key if present, else this module's own env (MESHY_API_KEY, …)
# resolve_selfhost() = _engine's THREED_SELFHOST_URL if present, else this module's env
# cost_map()         = _engine's per-provider price map if present, else this module's own
# generation ALWAYS runs through providers/{meshy_mv,tripo_mv,selfhost_mv}.py (multi-image) — never _engine.generate_3d.
# (wire-time alt: if automation/threed gains generate_3d(image_urls=[...]) we may delegate the call too — contract noted, not assumed.)
```
Provider adapter contract (`providers/<id>.py`, **pure functions, no I/O — offline-testable**):
```python
BASE: str
def create_request(image_refs, options, key) -> (url, headers, json_body)   # multi-image POST shape
def parse_create(resp_json) -> external_task_id
def poll_request(task_id, key) -> (url, headers)
def parse_poll(resp_json) -> {"status","glb_url","thumbnail","cost"}         # normalized to our schema
```
Concrete, research-verified shapes (so wiring needs no re-research; treat non-Meshy as wire-time-verify):
- **meshy_mv** — Meshy-5 **multi-image-to-3D** (3–4 angles, >4 ignored): `Authorization: Bearer <key>`;
  status ∈ {PENDING,IN_PROGRESS,SUCCEEDED,FAILED}; asset in `model_urls.glb`. Cost = **5 credits mesh +
  10 credits texture** [Meshy — §8].
- **tripo_mv** — Tripo **multiview-to-3D** (2–4 reference images), v2.5+/v3.x; `Authorization: Bearer
  <key>`; output `data.output.pbr_model`/`model`; ~$0.20–0.40/model on fal [Tripo/fal — §8]. *(Re-verify
  live request/response shape at wire-time.)*
- **selfhost_mv** — `THREED_SELFHOST_URL` (+ optional `THREED_SELFHOST_TOKEN`): `POST {url}/infer`
  (multipart N images) → `{task_id}`; `GET {url}/result/{id}` → `{status,glb_url}`. One shape serves
  both TRELLIS.2 and Hunyuan3D-2.1; the DO GPU droplet server adapts each (recipe in
  `automation-threed.md §5`).

### 4.4 Splat-path adapter (`splat.py` — PATH B, dormant)

- Default provider `LUMA` (managed) — **Luma 3D Capture**: REST submit-job → `job_id` → poll/webhook →
  Gaussian-splat scene; embeddable viewer [Luma — §8]. Upload the **whole** walk-around video (no frame
  sampling). Output stored as `.spz`/`.ply` under `assets/`; thumbnail = a rendered poster frame.
- Dormant until `LUMA_API_KEY` (note: **API credits are separate from web credits** — Luma bills the API
  independently [Luma — §8]).
- Self-host alternative is **deferred** (full 3DGS training, e.g. COLMAP + gsplat, is a heavier GPU
  pipeline than mesh inference; documented as a future `.md`, not built now).

### 4.5 Viewer + share (PATH-agnostic, zero credentials, offline)

- **Mesh viewer** — Google **`<model-viewer>`** web component (**Apache-2.0**; renders `.glb`, rotate/
  zoom/auto-rotate, **AR** via SceneViewer on Android / Quick Look on iOS) [Google — §8]. Self-hosted
  single web component, **no backend, no key**.
- **Splat viewer** — **Spark** (sparkjsdev/spark; OSS, Three.js/WebGL2; supports `.spz/.ply/.splat`,
  Spark 2.0 adds streaming LoD for big scenes) [Spark — §8], **or** Luma's own embeddable iframe as a
  zero-effort fallback. Self-hosted, no key.
- **Share** = mint an unguessable token → `shares/<token>.json` (token→job_id, kind, expiry, tenant
  scope) → public `viewer_url` = `/threed-model/v/<token>`. `share()` also returns ready-made
  **WhatsApp** (link + poster), **catalog card** (thumb + viewer_url for the Brochure/Catalog sub-page),
  and **ad asset ref** (viewer_url + poster for the ad creative) payloads — but **sends nothing**; the
  actual send is the orchestrator's dormant wiring into `whatsapp.py` / catalog / ads.

### 4.6 Dormant HTTP endpoints (DESIGN ONLY — orchestrator adds to `caller.py` later)

Mirrors the existing `POST /whatsapp/send` rail; all return `{"status":"not_configured"}` until keys
exist. Spec'd so wiring is mechanical; all tenant-scoped via existing RBAC (`resolve_tenant`,
`need_auth`, `can(tenant,"write")`).

| Method & path | Auth | Body / query | Returns |
|---|---|---|---|
| `POST /threed-model/capture` | write | `tenant_id, campaign_id?, video(upload)\|image_urls, kind, options` | `{status, job_id, path}` |
| `GET /threed-model/jobs/{job_id}` | read | — | full job record (status, asset_path, cost, share) |
| `GET /threed-model/asset/{job_id}` | read (token or RBAC) | — | the `.glb`/`.spz` file (or 404) |
| `POST /threed-model/share/{job_id}` | write | `{channels, expires_days}` | `{token, viewer_url, payloads}` |
| `GET /threed-model/v/{token}` | **public (token)** | — | the rendered **viewer page** (mesh or splat) |
| `GET /threed-model/status` | read | — | `capabilities()` (drives UI enable/disable per path) |
| `GET /threed-model/jobs` | read | `tenant?, campaign?, limit, offset` | recent jobs (tenant-scoped) |

### 4.7 Data shape (disk = source of truth, mirrors `var/` stores)

`var/creative/threed_model/jobs/<job_id>.json`:
```json
{ "job_id":"tdm_ab12cd", "tenant_id":"t_x", "campaign_id":"cmp_7",
  "created":"2026-06-09T..+05:30", "kind":"product", "path":"mesh", "provider":"meshy",
  "input":{"video":"frames/tdm_ab12cd","frames":4,"image_urls":null},
  "options":{"texture":true,"pbr":true},
  "external_task_id":"...", "status":"SUCCEEDED",
  "asset_path":"var/creative/threed_model/assets/tdm_ab12cd.glb", "asset_kind":"glb",
  "thumbnail":"...png", "topology":"auto_unverified",
  "cost":{"unit":"credits","amount":15,"usd_est":0.20},
  "share":{"token":"sh_9f...","viewer_url":"/threed-model/v/sh_9f...","expires":"2026-07-09"},
  "approved":true,"approved_by":"t_x","audit_ref":"<audit_log line ts>" }
```

---

## 5. HOW IT CONNECTS TO THE REST (ads / leads / CRM / voice / WhatsApp / analytics)

Everything is **revenue-connected**; the 3D asset is a node in the existing funnel, attributed by a
**creative tag** so performance flows back (same taxonomy `creative-batch` defines):

- **Creative Batch** selects `kind=object/space` and calls `create_capture(...)` as one fan-out target
  (alongside image/video/landing); the returned `job_id` + share token become a **tagged variant**.
- **Ads** — `share(channels=["ad"])` returns an `ad_asset_ref` (poster + interactive `viewer_url`); the
  `automation/ads` module can launch a "View in 3D / 360°" ad variant. CTR/engagement on that variant
  feed the autonomous optimizer (scale/pause) — the 3D link is just another tagged asset in the loop.
- **Leads → CRM** — a click on a shared viewer link is an engagement signal; the share token carries the
  `campaign_id` so a captured lead is attributed to the 3D asset (consumed by the existing lead/CRM rail,
  `db/models.py Lead`).
- **Voice** — when the AI voice agent (caller/agent spine — **not edited here**) is on a call, the share
  link is a follow-up artifact ("I'll WhatsApp you a 3D view of the unit") the orchestrator can hand to
  the dormant WhatsApp send.
- **WhatsApp** — `share(channels=["whatsapp"])` returns a `whatsapp_payload` (link + poster) ready for
  `whatsapp.py.send_whatsapp(...)`; sending stays dormant (no creds) until wired.
- **Catalog / Landing / Brochure** — `catalog_card` (thumb + `viewer_url`) embeds into the
  Brochure/Catalog and Landing-Page sub-pages so a product/property card carries a live 3D view.
- **Analytics** — viewer-page loads + share-link clicks are logged (per token, per tenant) through the
  existing audit/metering rails so 3D engagement shows up in the same analytics/billing UI.

All of the above are **described handoffs** — this module produces the assets, links and payloads; the
orchestrator does the cross-module wiring later. Nothing here calls the spine.

---

## 6. THE ASYNC-JOB PATTERN (for media gen)

Capture is long-running (mesh 30 s–2 min; splat minutes); the module is **fire-and-forget + poll/webhook**,
never blocking:
1. `create_capture` (a) GATEs the kind, (b) PATH A: samples N frames from the video offline (ffmpeg) or
   takes provided stills, PATH B: stages the whole video; (c) pre-flight cost check (§7); (d) submits to
   the engine/splat provider; (e) writes a `jobs/<job_id>.json` record `status:queued` and returns the
   `job_id` immediately.
2. Result returns **automatically** by either path: a **poller** (`poll(job_id)` with backoff, driven by a
   small worker / the existing scheduler) **or** a provider **webhook** (Luma/Meshy support callbacks) →
   on success, download asset to `assets/`, render `thumbs/<job_id>.png`, flip the record to `SUCCEEDED`.
3. The viewer page and share token are generated **on demand** from the finished asset (pure, offline) —
   so a completed job is instantly shareable with zero extra vendor calls.
4. **Idempotent + crash-safe:** the disk record is the source of truth; a re-poll after a crash reconciles
   from `external_task_id`; partial frame dirs are safe to regenerate (deterministic).

This is the same async shape every sibling media studio uses (submit → poll → asset), so the orchestrator
drives all of them uniformly.

---

## 7. SPEND / APPROVAL / AUDIT GUARDRAILS (production-grade — reuses existing rails)

Capture costs real money per asset, so guardrails are first-class and **reuse existing infra** (audit,
ratelimit, ledger, tenant-limits, firewall step-up), never re-invented:

1. **Pre-flight cost estimate + hard per-job cap.** `create_capture` computes the credit/USD estimate
   from a per-provider price map (mesh: Meshy 15 credits textured ≈ $0.20; Tripo ~$0.20–0.40; splat:
   Luma per-job) and **refuses before any spend** if it exceeds `THREED_MAX_USD_PER_JOB` (default $1) or
   the tenant's remaining 3D budget.
2. **Per-tenant monthly 3D budget** stored beside the existing tenant-limits mechanism
   (`POST /tenants/{tid}/limits`, `caller.py`). Over budget → `{"status":"budget_exceeded"}`, zero call.
3. **Approval gate** (`THREED_REQUIRE_APPROVAL=1`, reuses the **firewall step-up** gate from
   `design/credit-ledger-firewall.md`): job created `awaiting_approval`, **no provider call** until a
   manager-role approves. Default off for self-serve mesh; **recommended on for the splat/property path**
   (higher per-job cost) and for un-vetted tenants.
4. **Audit every mutating action** through the existing append-only `audit.record(...)` — actions
   `threed_model.capture`, `.approve`, `.share` — same immutable JSONL as `whatsapp.send`. Each job +
   each share stores its `audit_ref` (submitter recorded → misuse traceable).
5. **Rate-limit** capture + share via existing `ratelimit.py` (per-tenant token bucket) — prevents a
   runaway loop draining credits / minting unbounded public links.
6. **Spend metering** rides the existing billing meter family (`vendors/` + `/billing/vendors`): add a
   `threed_model` line so 3D spend shows in the same billing UI. Self-host mesh = $0 marginal.
7. **Share-link safety:** tokens are unguessable, **expiring** (`expires_days`, default 30) and
   **tenant-scoped**; a public viewer hit is rate-limited and logged; revocation = delete `shares/<token>.json`.
8. **Content/abuse note (wire-time requirement, flagged not solved):** generating 3D from arbitrary
   uploads invites IP/trademark misuse (3D-scanning a competitor's product) — add a documented
   Acceptable-Use note ("capture only assets you own/have rights to") and route un-vetted tenants through
   the approval gate. Spend guardrails = real/verified; ToS/abuse guardrails = partial, surfaced here.
9. **Secret hygiene:** keys in env only, never in `var/` records, redacted in logs.

---

## 8. SOURCES (web research, June 2026 — ACTIVE tools only)

- Meshy **multi-image-to-3D** ("3–4 angles ≈ photogrammetry without the rigor"; >4 ignored) + credits
  (5 mesh / 10 texture; API on $20/mo Pro+; free tier CC-BY) — https://www.meshy.ai/api ,
  https://docs.meshy.ai/en/api/image-to-3d , https://docs.meshy.ai/en/api/pricing ,
  https://fal.ai/models/fal-ai/meshy/v5/multi-image-to-3d/api , https://www.meshy.ai/pricing
- Tripo **multiview-to-3D** (2–4 reference images; v2.5/v3.x; commercial; ~$0.20–0.40/model on fal) —
  https://fal.ai/models/tripo3d/tripo/v2.5/multiview-to-3d/api , https://www.tripo3d.ai/api ,
  https://wavespeed.ai/models/tripo3d/v2.5/image-to-3d
- TRELLIS.2 (**MIT**, 4B image-to-3D, ≥24 GB VRAM) & Hunyuan3D-2.1 (Tencent Community License,
  EU/UK/KR carve-out + 1M-MAU trigger; 6/16 GB VRAM) — self-host engines (see `automation-threed.md §5/§7`) —
  https://huggingface.co/microsoft/TRELLIS.2-4B , https://github.com/tencent-hunyuan/hunyuan3d-2.1
- Luma **3D Capture / Genie** (REST submit→job_id→poll/webhook; video walk-around → NeRF/Gaussian splat
  in minutes; embeddable viewer; **API credits separate from web credits**; commercial from Plus $29.99/mo;
  Genie = text-to-3D, Pro tier) — https://lumalabs.ai/pricing , https://lumalabs.ai/luma-web-library ,
  https://www.llmreference.com/provider/luma-api/genie-3d , https://www.thefuture3d.com/software/luma-ai/
- **`<model-viewer>`** (Google, **Apache-2.0**; glTF/glb; rotate/zoom; AR via SceneViewer/Quick Look;
  self-host, no backend) — https://github.com/google/model-viewer , https://modelviewer.dev/docs/faq.html ,
  https://web.dev/articles/model-viewer , https://developers.google.com/ar/develop/webxr/model-viewer
- **Spark** splat renderer (OSS; Three.js/WebGL2; `.spz/.ply/.splat`; Spark 2.0 streaming LoD) —
  https://sparkjs.dev/ , https://github.com/sparkjsdev/spark , https://www.worldlabs.ai/blog/spark-2.0
- Real-estate mesh-reconstruction limits (why properties go SPLAT, not mesh) —
  https://ravelin3d.com/blog/ai-in-architectural-visualization-revolution-or-hype-2025-2026-reality-check.html ,
  https://blog.chaos.com/best-ai-rendering-tools-for-architects-compared

---

## 9. OFFLINE ACCEPTANCE TEST (no live external calls, no GPU — must pass before wiring)

`creative/threed_model/_test_threed_model.py` (stdlib `unittest`, runnable as
`python -m creative.threed_model._test_threed_model`):

1. **Dormant import** — `import creative.threed_model.service` with **no env set** does not raise;
   `status()=="not_configured"`, `is_configured() is False`,
   `capabilities()["mesh"]["can_generate"] is False` and `["splat"]["can_capture"] is False`,
   `["can_view"] is True`, `["can_share"] is True`.
2. **No-op capture** — `await create_capture(tenant_id="t", kind="product", image_urls=[...])` returns
   `{"status":"not_configured","path":"mesh",...}` and makes **zero** network calls (monkeypatched HTTP
   fails the test if invoked).
3. **Kind GATE** — `kind="house"`/unknown → `refused_unsupported_kind` (no call, no spend);
   `kind="property"` with no splat key → `{"status":"not_configured","path":"splat"}` (steers to splat,
   never builds a fake house mesh).
4. **Frame sampling is offline + deterministic** — given a tiny fixture video (or stubbed ffmpeg), N
   frames land in a temp `frames/<job_id>/` with stable names; with ffmpeg absent, returns
   `error:ffmpeg_unavailable` (no crash) and the test asserts the contract.
5. **Provider-shape unit tests (pure, offline)** — for meshy_mv/tripo_mv/selfhost_mv,
   `create_request(refs,opts,"FAKEKEY")` yields the documented URL + `Authorization: Bearer FAKEKEY` +
   correctly-shaped multi-image body; `parse_poll(<canned SUCCEEDED json>)` returns a normalized record
   with the `.glb` URL. **Canned JSON fixtures, never the network.**
6. **Viewer generation is offline + correct** — `viewer_html(job_id)` for a fixture `.glb` contains a
   `<model-viewer src=…>` tag; for a fixture `.spz` contains the Spark viewer scaffold. No network, no key.
7. **Share mint** — `share(job_id, channels=["whatsapp","catalog","ad"])` writes `shares/<token>.json`,
   returns an unguessable token + `viewer_url` + a `whatsapp_payload` / `catalog_card` / `ad_asset_ref`,
   and **sends nothing** (monkeypatched `whatsapp.send` is asserted NOT called).
8. **Cost-cap guardrail** — a job whose estimate exceeds `THREED_MAX_USD_PER_JOB` returns
   `budget_exceeded` with **no** provider call.
9. **Own-generate; share-infra** — generation **always** runs through this module's multi-image
   `providers/*` (assert `_engine.generate_3d` is **NOT** called) in **both** cases: (a) with
   `automation.threed` importable (stub exposing a key / `THREED_SELFHOST_URL` / cost map) → assert the
   shared key/cost are picked up from the stub; (b) with it absent → assert this module's own env + cost
   map are used. Both reach a `SUCCEEDED` job via mocked create→poll, write the job record, and call the
   audit hook. **Still zero real network.**
10. **Redaction** — `redact("sk-abcd...wxyz")` shows only first/last 4; a fake log line never contains
    the full key.

Pass criteria: all 10 green with **no network access and no GPU** — the whole sub-page is provable on a
laptop, fully offline, before any key or droplet exists.

---

## 10. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

All blank today ⇒ the sub-page is dormant (but frame sampling, viewer pages and share tokens already
work offline). Provide creds **per path** — you can light up products (mesh) and properties (splat)
independently.

**A. PRODUCT / OBJECT path (mesh `.glb`) — pick ONE to go live fast (recommended: Meshy):**
- `THREED_PROVIDER` = `meshy` (or `tripo` / self-host `trellis`/`hunyuan`)
- `MESHY_API_KEY` — Meshy **Pro plan ($20/mo)+** (API requires Pro+; paid assets privately licensed, no
  attribution; **+ ~$0.20/asset in credits** — 15 credits textured). Account: https://www.meshy.ai
- *(if tripo)* `TRIPO_API_KEY` — Tripo **Pro tier** (commercial rights). https://platform.tripo3d.ai
- *(if self-host)* `THREED_SELFHOST_URL` (+ optional `THREED_SELFHOST_TOKEN`) → DO GPU droplet running
  TRELLIS.2 (MIT, ≥24 GB VRAM) or Hunyuan3D-2.1 (cheaper GPU, license carve-outs). Recipe lives in
  `automation-threed.md §5`. **$0 marginal per asset once up.**
> *If `automation/threed` is already deployed, the mesh path inherits ITS provider key — no separate key
> needed here.*

**B. PROPERTY / SPACE path (Gaussian splat) — for real-estate "walk-around" tours:**
- `THREED_SPLAT_PROVIDER` = `luma`
- `LUMA_API_KEY` — Luma API key for **3D Capture** (commercial from **Plus $29.99/mo**; **API credits are
  billed separately from web credits** — buy API credits). Account: https://lumalabs.ai

**C. Viewer + sharing — NO account needed:** Google `<model-viewer>` (Apache-2.0) for mesh, Spark
(OSS, Three.js) for splat, both self-hosted. Frame sampling = **ffmpeg** (free, one-time `apt install`).

**D. Guardrail knobs (optional; sane defaults if unset):**
- `THREED_MAX_USD_PER_JOB` (default `1.00`) — hard per-job spend cap.
- `THREED_REQUIRE_APPROVAL` (`0`/`1`, default `0`) — human approval before any paid capture
  (recommend `1` for the splat path + un-vetted tenants).
- `THREED_OFFLINE` (`1` to force the no-network/no-op mode used by tests).

---

## RED-TEAM FIXES (folded)

Adversarial review 2026-06-09. The spec was checked against live source under `droplet_work/` and
re-verified against 2026 web sources. **Verdict: GO for PATH A (mesh) + viewer/share/guardrails; PATH B
(splat) is GO-but-corrected below.** The following fixes are folded into the spec; where a fix changes a
contract, the relevant section is the authority and this block records the correction + residual risk.

**R1 · Luma PATH B — the citation bound to the WRONG Luma product (honesty fix, no safety impact).**
The spec's §8/§10 referenced **Luma "Genie"** (the `genie-3d` URL; "Genie = text-to-3D, Pro tier").
**Genie is text-to-3D — the wrong capability for "video walk-around → splat" regardless of its status**
(and it was *reportedly* sunset around 2026-01-01; in any case it was never the right binding for PATH B).
The *correct, still-live* product for PATH B is Luma's **"Video to 3D" API / "3D Capture" /
"Interactive Scenes"**: upload a 30–60 s walk-around video → interactive Gaussian-splat/NeRF scene,
**billed dollar-per-capture** (not the web "$29.99/mo Plus" tier, and not "API vs web credits").
**PATH B is therefore production-real, but the provider binding must be the Video-to-3D capture endpoint,
NOT Genie.** Authoritative corrections:
  - §4.4 `splat.py`: provider `LUMA` = **Luma Video-to-3D / 3D Capture API** (submit video-capture job →
    `job_id` → poll/webhook → splat scene). **Remove all Genie wording.** Billing model = **per-capture
    USD** (treat as `cost.unit="capture"`, `usd_est=<per-capture price>`), not monthly-tier credits.
  - §8 sources: **drop the `llmreference.com/.../genie-3d` link and "Genie = text-to-3D" note.** Replace
    with the Video-to-3D / Interactive-Scenes capability (lumalabs.ai/api, lumalabs.ai/interactive-scenes).
  - §10-B: `LUMA_API_KEY` lights up **Luma Video-to-3D capture** (dollar-per-capture); drop "Genie/web
    credits" framing. Because per-capture price > typical mesh credit cost, **keep §7's recommendation
    that `THREED_REQUIRE_APPROVAL=1` defaults ON for the splat path.**
  - **Residual (wire-time, flagged not closed):** the live Video-to-3D request/response shape + exact
    per-capture price were confirmed via Luma's API surface and aggregators, **not** a clean fetch of
    Luma's own endpoint reference. Treat the splat adapter's request shape + price as **WIRE-TIME-VERIFY**
    (same status the spec already gives Tripo). **Also confirm the API returns a downloadable splat
    (`.spz/.ply`) that Spark can render, vs. embed-only** — Luma's capture exports have historically
    favored mesh formats (USDZ/glTF/OBJ) + a Luma-hosted "interactive scene" embed; if the API hands back
    only an embed, use the Luma iframe fallback (already in §4.5) and the Spark dependency drops for PATH B.
    If at wire-time Luma has no self-serve Video-to-3D REST endpoint at all, PATH B downgrades to
    **deferred** (self-host COLMAP+gsplat, already noted §4.4) — and since PATH B is
    dormant-until-`LUMA_API_KEY`, this changes nothing that ships and breaks nothing.

**R2 · Autonomous ad-spend authority — make the zero-authority boundary explicit (the task's safety gate).**
This module **never spends ad budget and never bids.** Its only spend is **3D-asset generation** (Meshy
credits / Luma per-capture), fully capped by §7 (`THREED_MAX_USD_PER_JOB`, per-tenant 3D budget, approval
gate, rate-limit, metering). §5's "feeds the autonomous optimizer (scale/pause)" and "launch a 3D ad
variant" are **handoffs of an asset reference only** — the ad launch, budget control and any autonomous
bidding/scale-pause guardrails live entirely in **`automation/ads`**, not here. Folded as a hard
invariant: **this sub-page has ZERO ad-spend and ZERO bidding authority; it emits `ad_asset_ref`
payloads and stops.** Any money this module can cause to move is 3D-generation credits, which are capped
and approval-gateable before any provider call. (Verified against §5/§7: no code path here touches an ad
budget; honest as written, now stated as an invariant.)

**R3 · Self-host "$0 marginal" hides a standing GPU bill (missing-cost fix).**
§1/§7/§10 call self-host (TRELLIS.2 / Hunyuan3D-2.1) "**$0 marginal per asset**" — true **per asset**,
but it omits the **standing cost of an always-on DO GPU droplet** (TRELLIS.2 needs ≥24 GB VRAM;
Hunyuan3D-2.1 ~6–16 GB). That is a real recurring bill (a 24 GB-class GPU droplet is a non-trivial
monthly cost) plus ops. Honest framing, folded: self-host is **"$0 per-asset marginal but a fixed
monthly GPU-droplet cost"** — economically it wins only above a break-even volume vs. Meshy's
~$0.20/asset; below that, the managed Meshy key is cheaper. The founder should treat self-host as a
**volume play**, and §10-A should read "**$0 per-asset marginal, but a standing GPU-droplet bill —
worth it only at high volume.**" (Recommended default to ship: managed **Meshy** key; self-host later.)

**R4 · Provider/version drift vs. the sibling engine (cosmetic, note only).**
This doc says **"Meshy-5"**; the sibling `automation-threed.md` says **"Meshy 6"** and also lists **Rodin
v2.5**. Provider *versions move*; the adapter is version-agnostic (it reads `model_urls.glb` regardless),
so this is non-load-bearing. Fix: treat the concrete provider version as **wire-time-current** ("Meshy
latest multi-image-to-3D"), and keep the two threed docs' provider lists reconciled at wire-time. No
contract change.

**What was checked and held (no fix needed):**
  - **Dormant + non-breaking:** confirmed against live `whatsapp.py` (returns `{"status":"not_configured"}`,
    never raises) and the `caller.py:34-37` `try: import … except: =None` seam — the spec's pattern is
    exact. Importing this greenfield package with no env is side-effect-free; it touches nothing under the
    spine. **TRUE.**
  - **Layering (own-generate vs. delegate):** verified the sibling engine's public entry is
    `generate_3d(image_url|image_b64, prompt, …)` — **single-image** (`automation-threed.md §4.1`). The
    spec's core claim ("we own the multi-image fuse call; we import the engine only for shared
    key/`THREED_SELFHOST_URL`/cost map") is **technically correct** — four single-image calls do not fuse
    one mesh. §0/§4.3 and the §9-item-9 test are internally consistent on this. **SOUND.**
  - **Guardrails are real:** `audit.record(actor, action, …)`, `ratelimit.allow(tenant_id, …)` and the
    redact helper (`first/last-4`) all exist in live source as cited; §7's spend caps/approval/metering
    reuse them. **TRUE.** (ToS/abuse guardrail honestly self-labels "partial, surfaced not solved" in
    §7.8 — keep that label.)
  - **Async pattern:** submit→`job_id`→poll/webhook, disk-record-as-truth, idempotent re-poll from
    `external_task_id` — matches the codebase's `var/*` store pattern and the async `caller.py` call site.
    **SOUND.**
  - **Meshy multi-image API + commercial rights:** active in 2026; API gated to **Pro tier ($20/mo)+**;
    **paid tiers grant private, customer-owned commercial license (no attribution)**; free tier is CC-BY.
    Credits 5 (mesh) + 10 (texture). Spec's §8/§10 match the live ToS. **TRUE.**
  - **Viewer stack:** `<model-viewer>` (Apache-2.0, AR-capable) is well-established, self-hosted,
    key-free — **TRUE.** **Spark** (OSS Three.js splat) is asserted active/self-hosted/key-free and
    **swappable for Luma's embed** but was **NOT re-verified this pass** — low-risk because it is
    swappable (per R1, PATH B may use Luma's iframe and drop Spark entirely). **Verify Spark is
    maintained at wire-time.**

**Self-host model licenses — VERIFICATION STATUS (ToS is in scope, so stated honestly):**
  - **Hunyuan3D-2.1 license — RE-VERIFIED this pass (2026-06-09):** the Tencent Hunyuan 3D 2.1 Community
    License defines "Territory" as **worldwide EXCLUDING the European Union, United Kingdom and South
    Korea** — i.e. the model **may not be used commercially in EU/UK/SK** under the community license, and
    larger commercial deployments must request a separate license from `hunyuan3d@tencent.com`. **The
    spec's carve-out claim is CORRECT** (the precise "1M-MAU trigger" figure is the one detail not
    re-confirmed — treat as approximate). **Material ToS risk if a tenant/operator is in EU/UK/SK →
    prefer Meshy (managed) or TRELLIS.2 (MIT) there.**
  - **TRELLIS.2 = MIT:** **NOT re-verified this pass** — inherited from `automation-threed.md §8`. MIT
    would be permissive/safe, but **confirm the exact license + VRAM floor before any self-host deploy.**
  - General rule folded: **no self-host model ships until its current license is confirmed for the
    operator's jurisdiction** (Hunyuan's EU/UK/SK exclusion is the live example of why this matters).

---

### TL;DR for the founder
This sub-page is the **"3D Product Model"** page of Creative Studio. A vendor **records a multi-angle
video**; the platform turns it into an **interactive 3D asset** and gives back a **shareable link** that
drops into WhatsApp, the website, ads and the catalog. Two real 2026 paths: **products** become a
rotatable, AR-ready **`.glb`** (sample 3–4 frames → Meshy/Tripo/self-host); **properties/interiors**
become a navigable **Gaussian-splat tour** (Luma 3D Capture). Viewer + sharing are **free + self-hosted**
(`<model-viewer>` / Spark). Paste **one** key — `MESHY_API_KEY` (Meshy Pro, $20/mo) — to light up
products; add `LUMA_API_KEY` to light up property tours. It **refuses** to fake a "3D house mesh" on
purpose. Until a key is pasted, the whole module is a safe no-op — yet frame-sampling, viewer pages and
share links already work offline.
