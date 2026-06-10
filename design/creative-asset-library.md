# DESIGN SPEC — CREATIVE STUDIO ▸ **ASSET LIBRARY** (`droplet_work/creative/shared/library.py` + DO Spaces)

> **Status:** EXECUTION-READY. A build agent implements this verbatim, one UNIT at a time, running the
> offline acceptance test (§9) before the next. **NON-BREAKING + crash-safe. NO git** (orchestrator
> commits). **NEW files ONLY under `droplet_work/creative/`.** **DO NOT edit `caller.py` / `agent.py`**
> (backend spine; final wiring deferred — endpoints in §7 are *described*, not implemented).
> Every external integration (DO Spaces, search engine) is **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS**:
> a no-op that **NEVER raises** until the founder pastes keys — exactly like `droplet_work/whatsapp.py`.
> **Verifiable OFFLINE** — the acceptance test makes ZERO live external calls and needs no sibling module.

Research date: 2026-06-09. All chosen tools verified ACTIVE in 2026 (cited §10). Verified against live
source under `C:\Users\kunal\Desktop\caps\droplet_work\` and the shipped sibling design docs.

---

## 0. WHAT THIS IS (one paragraph, honest)

The **Asset Library** is the **single canonical store for EVERY creative asset** in Famit — generated
*or* uploaded: banners, images, videos, ad scripts, ad copy, hooks, brochures, catalogs, PDFs, landing
pages, 3D/GLB, logos, product photos, WhatsApp templates. It is **not a new competing store** — it is
the **formalization of the `shared/library.py` + `AssetRef` contract that `creative-video-studio.md`
already references** ("one Asset Library shared across video/image/3d", §4/§5d of that doc). Every
studio (image/video/threed/landing/brochure/batch) **delegates registration to this one owner** instead
of scattering its own `var/creatives/` + "DO Spaces sink later" stubs. The library owns: (a) the
canonical `AssetRef` metadata record, (b) the **DO Spaces upload seam** (dormant → local-first when no
keys), (c) **ingest of founder-uploaded** assets (logos, product photos), (d) **rich tenant-scoped
search** by campaign / product / client / format / platform / kind / date / status / performance, and
(e) **performance write-back** (`metrics`, `ad_refs`) so nothing is lost and every asset is reusable and
revenue-attributable. With **zero credentials** it is fully functional: assets land on the local droplet,
metadata is recorded, and search/tag/status all work offline. DO Spaces is the **dormant durability +
CDN layer on top**.

**Real-vs-hype, stated up front.** No DO Spaces keys ⇒ the library is NOT a dead no-op: it stores bytes
locally under `var/creative/assets/`, records full metadata, and serves search/list/tag/status with zero
network. Cloud durability + CDN delivery + cross-droplet sharing are the dormant layer that lights up the
moment `DO_SPACES_*` is pasted. This honesty is structural — it falls out of the local-first/Spaces-sink
split (§2.2).

---

## 1. GROUND TRUTH — what already exists that this MUST stay compatible with (verified on disk 2026-06-09)

| Asset | Path / location | What the library reuses / must match |
|---|---|---|
| **Already-pinned `AssetRef` shape** | `design/creative-video-studio.md` §5d (`VAR/creative/assets/<asset_id>.json`) | This module OWNS that file path + record. The new schema is a **backward-compatible SUPERSET** — every existing field kept; new fields additive. |
| **Already-referenced `library.py`** | `design/creative-video-studio.md` §4 line 169 (`shared/library.py` — "register/list/tag assets … shared by video/image/3d") | The import path `creative/shared/library.py` is kept **intact** so existing sibling references resolve. |
| Dormant-until-creds template | `whatsapp.py` | EXACT pattern: env read at call time, `is_configured()`/`spaces_configured()`, no-op `{"status":"not_configured"}`, never raises, sync+async twins. Copied for the Spaces uploader. |
| Spine import pattern | `caller.py:35-37` `try: import X except: X=None` | How siblings import the library: bare `from creative.shared import library` (deploy root `/opt/famit-agent/` IS the `droplet_work/` contents — **no `droplet_work.` prefix**, or it ImportErrors in prod). |
| Atomic JSON / JSONL store + lock | `store.py` (`write` atomic-tmp-rename `:590`, `awrite` `:616`, `_STORE_LOCK`), `caller.py:108/444/450` `_read/_write` under `VAR=Path(os.getenv("FAMIT_VAR","/opt/famit-agent/var"))`, lazy `mkdir(parents=True, exist_ok=True)` | Library store mirrors this exactly: atomic write, JSONL append index, `_STORE_LOCK`, lazy mkdir, best-effort (never raises). |
| Immutable audit | `audit.record(actor, action, object_type, object_id, ip, channel, tenant_id, actor_role, meta)` (append-only, never raises) + `tail(limit, offset, tenant_id, action_prefix)` | Every register / upload / tag / status / delete logged. Channel `"creative"`, action prefix `asset.*`. NOT reinvented. |
| Tenant / campaign / lead DB | `db/models.py`: `Org :44`, `User :55`, `Campaign :87`, `Lead :106` | `tenant_id == org_id` (RLS-scoped). `campaign_id` = `Campaign.id`. Search joins these for the dropdown facets. |
| Listing/pagination convention | `audit.tail()` + image `index.jsonl` (`automation-image.md` §6) + `/whatsapp/log` | Search/list = read `index.jsonl` newest-first, tenant-scoped, offset/limit — same shape, with added filter predicates. |
| Per-studio local stores TODAY (to be unified) | image `var/creatives/<job>/0.png` (`automation-image.md` §6); video uploads to Spaces itself, passes URL (`automation-video.md` `artifacts.py`); landing `do_spaces` publisher (`creative-landing-builder.md` §1.4) | Library accepts BOTH `put(bytes/local_path)` (uploads) AND `register(url)` (already-hosted) — §4.2. This is what unifies the scattered "DO Spaces sink later" stubs into one owner. |

### 1.1 Who writes into the library (the studios delegate; this module does not call them)

| Producer | What it registers | Path used |
|---|---|---|
| Image studio (`automation/image`) | banners, social cards, product creatives, logos/SVG bytes | `put(bytes,…)` or `register(url)` |
| Video studio (`automation/video`) | ad MP4s (already on Spaces) | `register(url, kind="video")` |
| 3D studio (`automation/threed`) | `.glb` / 360 spins (async) | `register(url, kind="threed")` |
| Landing builder (`creative/landing`) | published page URL + HTML snapshot | `register(url, kind="landing")` |
| Brochure/catalog (`creative/brochure`) | PDF bytes | `put(bytes, kind="brochure"|"catalog"|"pdf")` |
| Creative-batch (`creative/batch`) | text deliverables: hooks/ad_copy/headlines/wa_angles/scripts | `register_text(...)` (§4.2) |
| **Founder upload (UI)** | logos, product photos, brand assets | `ingest_upload(bytes, filename,…)` (§4.2) |
| Ads optimizer (`automation/ads` + `aimanager`) | `ad_refs`, `metrics` write-back | `attach_ad_ref(...)`, `update_metrics(...)` (§4.3) |

> **Scope boundary:** the library owns ONLY storage, metadata, search, and performance write-back. It
> does NOT generate assets, does NOT run the ads optimizer, does NOT own spend gates (those are the
> studios + `credit-ledger-firewall.md`). It imports **no** sibling studio.

---

## 2. THE DECISIONS THAT DEFINE THIS MODULE (read before coding)

### 2.1 Canonical owner, additive schema — never redefine the pinned `AssetRef`
The video doc froze `AssetRef`. This spec keeps **every** frozen field and only **adds** fields. Concrete
mapping of the founder's required search axes to fields (gaps closed by additive fields, bold = NEW):

| Search axis | Field | Status |
|---|---|---|
| campaign | `campaign_id` | existing |
| client | `tenant_id` | existing |
| date | `created_at` / `updated_at` | existing |
| performance | `metrics` (CTR/CPC/ROI/conversions) | existing |
| format | **`format`** (file ext: png/svg/mp4/glb/pdf/html) + **`mime`** | NEW (distinct from `kind`) |
| product | **`product_id`** + **`product`** (denormalized name) | NEW |
| platform | **`platforms[]`** (meta/google/youtube/whatsapp/landing) — also derivable from `ad_refs` | NEW |
| free-text | **`title`**, **`text`** (for copy/scripts), **`tags[]`** | NEW |

### 2.2 Local-first + DO Spaces sink — the dormancy spine
> **TIER 0 — ZERO-CRED · LOCAL · OFFLINE-PROVABLE.** Bytes written via `put()` land under
> `var/creative/assets/<asset_id>/<filename>`; the `AssetRef` `url` is a **local-serve path**
> (`/creative/assets/<asset_id>/raw`, served by the deferred router §7). Metadata, search, tag, status all
> work with **no key, no network**. This is exactly what the acceptance test exercises. Cost: ₹0.

> **TIER 1 — DORMANT · DURABLE · CDN.** With `DO_SPACES_*` set, `put()` uploads to Spaces (boto3
> S3-compatible) and the `url` becomes the Spaces/Cloudflare-fronted public/presigned URL; `register(url)`
> records an already-hosted URL as-is. No keys ⇒ upload is skipped, local path kept, `status` unaffected,
> **never raises**. (Mirrors `automation-video.md artifacts.py` "no-op if `SPACES_*` unset".)

### 2.3 ENV-VAR PRECEDENCE — reconcile the three shipped conventions (do NOT silently pick one)
Three creds names exist in shipped docs: `DO_SPACES_*` (landing-builder), `SPACES_*` (automation-video),
`IMAGE_S3_*` (automation-image). The library declares **`DO_SPACES_*` canonical** and **accepts the
others as aliases** so every studio's already-documented creds light up the one uploader. Resolution
order per key (first non-empty wins):

| Logical key | Precedence (first non-empty wins) |
|---|---|
| access key | `DO_SPACES_KEY` → `SPACES_KEY` → `IMAGE_S3_KEY` → `AWS_ACCESS_KEY_ID` |
| secret | `DO_SPACES_SECRET` → `SPACES_SECRET` → `IMAGE_S3_SECRET` → `AWS_SECRET_ACCESS_KEY` |
| bucket | `DO_SPACES_BUCKET` → `SPACES_BUCKET` → `IMAGE_S3_BUCKET` |
| region | `DO_SPACES_REGION` → `SPACES_REGION` → `IMAGE_S3_REGION` (default `blr1`) |
| endpoint | `DO_SPACES_ENDPOINT` → `SPACES_ENDPOINT` → `IMAGE_S3_ENDPOINT` (e.g. `https://blr1.digitaloceanspaces.com`) |
| public/CDN base | `DO_SPACES_CDN_BASE` (optional; Cloudflare-fronted) |

`spaces_configured()` ⇒ True only when access+secret+bucket+endpoint all resolve non-empty.

### 2.4 Extended `kind` enum — "store EVERY asset" must be literally true
Frozen enum was `video|image|banner|copy|threed|landing`. Extended (additive, superset):
`image | banner | video | threed | landing | copy | ad_copy | hook | script | brochure | catalog |
pdf | logo | product_photo | wa_template | doc | other`. Unknown kinds coerce to `other` (never reject).

### 2.5 Search — offline-provable default, optional real engine
Default search = in-process filter over `index.jsonl` (tenant-scoped, newest-first, offset/limit) with
predicate matching on every facet in §2.1 + a simple substring scan of `title`/`text`/`tags`. This is the
repo's established `audit.tail()` shape and needs **zero network**. A real search engine is an **OPTIONAL
env-gated upgrade, NOT a hard dep**: `ASSET_SEARCH_ENGINE ∈ {jsonl(default), meilisearch, typesense,
pg}`. When set + configured, writes mirror to the engine and `search()` queries it; otherwise the JSONL
path is authoritative. The offline test runs on `jsonl` only — zero network preserved.

### 2.6 Async results land automatically
Async studios (video/3D) call `register(url)` from their **own** webhook/poll callback when a job
finishes — so "results return to the platform automatically" is satisfied by the studio's existing
async loop writing one library record. The library itself has no poller; it is the sink, not the driver.

---

## 3. PACKAGE LAYOUT (NEW files, ALL under `droplet_work/creative/`)

```
droplet_work/creative/
  __init__.py
  shared/
    __init__.py
    library.py        # PUBLIC SURFACE (§4): register / put / register_text / ingest_upload / get /
                      #   list / search / tag / set_status / attach_ad_ref / update_metrics / delete / status
    models.py         # Pydantic v2: AssetRef (superset), AssetQuery, UploadResult, SearchPage
    storage.py        # local-first byte store under VAR/creative/assets/ ; atomic write ; _STORE_LOCK
    spaces.py         # DORMANT DO Spaces (boto3 S3-compat) uploader: spaces_configured(), put_bytes(),
                      #   presign(); no-op {"status":"not_configured"} when unset; never raises; sync+async
    index.py          # index.jsonl writer + the offline JSONL search/filter engine (facet predicates)
    searchx.py        # OPTIONAL engine adapters (meilisearch/typesense/pg) behind ASSET_SEARCH_ENGINE; dormant
    audit.py          # thin wrapper -> caller._audit when wired, else append VAR/creative/audit.jsonl (offline-safe)
    config.py         # env reads (DO_SPACES_* precedence §2.3, FAMIT_VAR, search engine knob); is_configured()
    router.py         # DEFERRED FastAPI APIRouter (§7) — DESCRIBED, NOT mounted by this module
  tests/
    test_library_offline.py   # the offline acceptance test (§9) — zero network, no sibling needed
    fixtures/                 # a sample Campaign row + a few canned assets (png bytes, an mp4 URL, a copy blob)
```

`creative/shared/__init__.py` re-exports `library` so `from creative.shared import library` resolves.
Nothing here imports `caller.py`/`agent.py` or any sibling studio.

---

## 4. PUBLIC SURFACE (`library.py` — every callable NEVER raises; sync + `_async` twins where I/O)

### 4.1 Status
```python
def status(*, tenant_id: str = "") -> dict
    # {ok, storage:"local", spaces:"configured:<bucket>"|"not_configured",
    #  search_engine:"jsonl"|"meilisearch:configured"|..., asset_count: int (tenant-scoped if given)}
```

### 4.2 INGESTION (the dual path the advisor flagged — uploads, generated-bytes, hosted-URLs, text)
```python
def put(bytes_or_path, *, tenant_id, kind, campaign_id="", product_id="", batch_id="",
        filename="", mime="", title="", meta=None, tags=None, platforms=None,
        status="draft", actor="") -> "AssetRef"
async def put_async(...) -> "AssetRef"
    # GENERATED bytes / local file from a studio. Writes locally (always), then uploads to DO Spaces
    # IF spaces_configured() (else local-only). Computes format from filename/mime. Records AssetRef +
    # index line + audit. Returns the AssetRef. NEVER raises.

def register(url, *, tenant_id, kind, campaign_id="", product_id="", batch_id="",
             thumb_url="", mime="", title="", meta=None, tags=None, platforms=None,
             status="draft", actor="") -> "AssetRef"
    # ALREADY-HOSTED artifact (video studio's Spaces URL, landing page URL, 3D .glb URL). Records the URL
    # as the canonical url; no upload. Used by async studio callbacks so results land automatically.

def register_text(text, *, tenant_id, kind="copy", campaign_id="", product_id="", batch_id="",
                  title="", meta=None, tags=None, actor="") -> "AssetRef"
    # TEXT deliverables (hooks/ad_copy/scripts/headlines/wa_angles from creative-batch). Stores the text
    # inline in the AssetRef (`text` field, indexed as `text_snippet`) + optionally a .txt/.json blob via
    # put(). `kind` defaults to "copy".

def ingest_upload(bytes_, *, tenant_id, filename, kind="", campaign_id="", product_id="",
                  title="", actor="", mime="", tags=None) -> "UploadResult"
async def ingest_upload_async(...) -> "UploadResult"
    # FOUNDER-UPLOADED asset from the UI (logos, product photos, brand assets). Sniffs kind from extension
    # when kind="" (png/jpg->product_photo or logo by hint; pdf->pdf; mp4->video). Delegates to put().
```

### 4.3 READ / SEARCH / MUTATE
```python
def get(asset_id, *, tenant_id) -> "AssetRef | dict"                 # tenant-scoped; {} if not owned
def list_assets(*, tenant_id, kind="", campaign_id="", limit=50, offset=0) -> "SearchPage"  # newest-first (name matches creative-video-studio.md service.list_assets)
def search(query: "AssetQuery | dict", *, tenant_id) -> "SearchPage"
    # Facets (all optional, AND-combined): kind, kinds[], campaign_id, product_id, format, mime,
    #   platform, status, batch_id, created_after, created_before, text (substring over title/tags/text_snippet),
    #   min_ctr/min_roi (over metrics), sort ∈ {newest, oldest, top_ctr, top_roi}, limit, offset.
    # Tenant-scoped ALWAYS. jsonl engine by default; mirrors to optional engine when configured.

def tag(asset_id, add=None, remove=None, *, tenant_id, actor="") -> "AssetRef | dict"
def set_status(asset_id, status, *, tenant_id, actor="") -> "AssetRef | dict"
    # status ∈ draft|approved|winner|paused|trashed (set by human OR Ads auto-optimizer). Audited.
def attach_ad_ref(asset_id, ad_ref: dict, *, tenant_id, actor="") -> "AssetRef | dict"
    # ad_ref = {platform, campaign_id, ad_id, creative_id}. Closes the revenue loop; also fills platforms[].
def update_metrics(asset_id, metrics: dict, *, tenant_id, actor="") -> "AssetRef | dict"
    # metrics = {ctr, cpc, roi, conversions, spend, impressions, synced_at}. From ads/aimanager analytics.
def delete(asset_id, *, tenant_id, actor="", hard=False) -> dict
    # soft by default (status->trashed, kept for reuse/audit). hard=True removes bytes+record (audited).
```

> **Never-raises guarantee:** every function wraps its body; on any error returns a typed dict
> (`{"ok":False,"status":"error:..."}`) or the unchanged record, and audits best-effort. Storage failures
> downgrade status to `error:storage` (mirrors `automation-image.md` §6), never propagate.

---

## 5. DATA MODEL

### 5.1 `AssetRef` (Pydantic v2 — superset of the frozen `creative-video-studio.md` §5d shape)
```python
{
  # ── FROZEN (kept verbatim) ──────────────────────────────────────────────
  "asset_id": "ca_<uuid4hex>",
  "tenant_id": "...", "campaign_id": "...", "batch_id": "vb_...|cb_...|''",
  "kind": "image|banner|video|threed|landing|copy|ad_copy|hook|script|brochure|catalog|pdf|logo|product_photo|wa_template|doc|other",
  "url": "https://<cdn-or-spaces>/...  | /creative/assets/<asset_id>/raw  (local-serve)",
  "thumb_url": "",
  "meta": {...},                       # free-form per-kind (angle, model, duration_s, lang, dimensions…)
  "status": "draft|approved|winner|paused|trashed",
  "ad_refs": [ {"platform":"meta","campaign_id":"...","ad_id":"...","creative_id":"..."} ],
  "metrics": {"ctr":..,"cpc":..,"roi":..,"conversions":..,"spend":..,"impressions":..,"synced_at":".."},
  "created_at": "...", "updated_at": "...",
  # ── ADDED (additive; close the search-axis gaps §2.1) ───────────────────
  "product_id": "", "product": "",     # product facet (id + denormalized name)
  "format": "", "mime": "",            # file format/ext + MIME (distinct from kind)
  "platforms": [],                     # ["meta","google","youtube","whatsapp","landing"] (also from ad_refs)
  "title": "", "text": "",             # human title; inline text for copy/scripts (searchable)
  "tags": [],                          # free user/auto tags (creative-tag taxonomy values land here)
  "source": "generated|uploaded|registered",   # provenance
  "storage": "local|spaces",           # where bytes physically live
  "bytes": 0, "sha256": "",            # size + content hash (dedupe / integrity; best-effort)
  "local_path": ""                     # absolute on-droplet path when storage=local (not exposed via API)
}
```
- `asset_id` = `"ca_" + uuid4().hex` (matches the frozen `ca_<uuid4hex>` convention).
- Timestamps = IST ISO (`datetime.now(IST).isoformat(timespec="seconds")`), matching `audit.py`.

### 5.2 Files (atomic write / JSONL append, all under `var/creative/`, created on demand)
```
/opt/famit-agent/var/creative/
  assets/
    <asset_id>.json                 # the full AssetRef
    <asset_id>/<filename>           # the actual bytes (when source=generated/uploaded & storage=local)
  index.jsonl                       # one compact line per asset (search facets) — the offline search source
  audit.jsonl                       # offline audit fallback (when caller._audit not wired)
```
- `index.jsonl` line = `{asset_id, tenant_id, campaign_id, product_id, kind, format, status, platforms,
  title, tags, text_snippet, ctr, roi, created_at}` — enough to satisfy every §4.3 filter (including the
  `text` substring search) **without opening per-asset files**. `text_snippet` = first 200 chars of the
  asset's `text`/`title` (so inline copy/hooks/scripts are searchable from the index alone); the `text`
  predicate scans `title` + `tags` + `text_snippet`.
- All reads/writes under `_STORE_LOCK`; tenant-scoped on read; lazy `mkdir`; best-effort (never raises).

---

## 6. DO SPACES UPLOADER (`spaces.py` — dormant, S3-compatible, boto3)

```python
def spaces_configured() -> bool                       # §2.3 precedence all-resolved
def put_bytes(key, data, *, content_type="", public=True) -> dict
    # {"ok":bool,"status":"uploaded|not_configured|error:...","url":<cdn-or-spaces-url>}
    # not_configured -> caller keeps local path; NEVER raises. boto3 client built lazily from §2.3 creds.
def presign(key, *, expires=3600) -> str              # signed GET url for private buckets ("" if unset)
async def put_bytes_async(...) -> dict                 # thread-offloaded boto3 (boto3 is sync)
```
- Object key layout: `creative/<tenant_id>/<kind>/<asset_id>/<filename>`.
- Public URL = `DO_SPACES_CDN_BASE` (Cloudflare-fronted) if set, else
  `https://<bucket>.<region>.digitaloceanspaces.com/<key>`.
- boto3 imported defensively (`try: import boto3 except: boto3=None`) — absent ⇒ behaves as not_configured.

---

## 7. DEFERRED HTTP SURFACE (DESCRIBED — NOT mounted; orchestrator wires later; DO NOT edit `caller.py`)

Powers the shared **"Asset Library"** Creative-Studio sub-page (gallery/browse/search). Auth via
`resolve_tenant` + `need_auth` + `can(tenant,"write")` for mutating routes; every mutation calls `_audit`.

| Method · Path | Role | Behavior |
|---|---|---|
| `GET /creative/assets` | read | Search/list (query = `AssetQuery` facets). Tenant-scoped, newest-first, paginated. Powers the gallery + filters. |
| `GET /creative/assets/{id}` | read | One `AssetRef` (tenant-scoped). |
| `GET /creative/assets/{id}/raw` | read | Serve bytes (local store) or 302 → Spaces/CDN url. `Content-Type` per `mime`. |
| `POST /creative/assets/upload` | write | Founder upload (multipart) → `ingest_upload`. Returns `AssetRef`. |
| `POST /creative/assets/{id}/tag` | write | add/remove tags. |
| `POST /creative/assets/{id}/status` | write | set status (draft/approved/winner/paused/trashed). |
| `POST /creative/assets/{id}/metrics` | write (system) | ads/aimanager write-back (CTR/CPC/ROI). |
| `DELETE /creative/assets/{id}` | manager+ | soft delete (default) / hard delete. |
| `GET /creative/assets/facets` | read | Distinct campaigns/products/kinds/platforms for filter dropdowns. |

`router.py` builds these on an `APIRouter(prefix="/creative/assets")`; the spine include is a deferred,
un-applied wiring note (no `caller.py` edit), exactly like the sibling docs.

> **Canonical-endpoint note (reconciles `creative-video-studio.md` §6).** `GET /creative/assets` is the
> **canonical** Asset Library endpoint. The video doc's `GET /creative/video/assets` is a **thin alias** ==
> `GET /creative/assets?kind=video` (it reads the same shared library this module owns; it does not own a
> separate store). The shared "Asset Library" sub-page is served by `/creative/assets`.

---

## 8. HOW IT CONNECTS TO THE REST (the revenue loop)

```
  studios (image/video/3d/landing/brochure)        founder UPLOAD (logos, product photos)
  + creative-batch (text deliverables)                       │
            │  put()/register()/register_text()              │ ingest_upload()
            └───────────────┬───────────────────────────────-┘
                            ▼
                    ASSET LIBRARY (AssetRef + bytes; local-first, DO Spaces dormant)
                            │  search/list/tag/status  ── powers the "Asset Library" sub-page
                            ▼
   ads.propose_campaign() picks approved/winner assets  ─► Autonomous Ads (Meta/Google/YouTube)
                            │                                         │ CTR/CPC/ROI/conversions
                            │  attach_ad_ref() / update_metrics()  ◄──┘  (ads + aimanager analytics)
                            ▼
   set_status(winner|trashed)  ─► library reflects which creative scaled vs trashed
                            │
   ads ─► leads (db.Lead / CRM) ─► voice (caller.py/agent.py) ─► WhatsApp follow-up (whatsapp.py)
                            └─────────────────────────► analytics (per-asset CTR/CPC/ROI; billing surfaces)
```

- **Ads/leads/CRM:** `ads` reads `search(status="approved")` to pick creatives; on launch calls
  `attach_ad_ref`; the optimizer calls `update_metrics` + `set_status(winner|trashed)`. Performance is now
  searchable (`sort=top_roi`, `min_ctr`).
- **Voice/WhatsApp:** `wa_template` and `script`/`copy` assets are reusable inputs to `whatsapp.py` /
  `marketing.content` — pulled by `kind`/`campaign_id`, never re-created.
- **Analytics/billing:** `audit.tail(action_prefix="asset")` + per-asset `metrics` give per-campaign/
  per-creative cost & performance for the billing/analytics surfaces. Nothing is lost; everything reusable.

---

## 9. OFFLINE ACCEPTANCE TEST (`tests/test_library_offline.py` — ZERO network, no sibling needed)

Temp `var/creative/`, temp audit file, a fixture `Campaign` row, **`DO_SPACES_*` UNSET**,
`ASSET_SEARCH_ENGINE=jsonl`. **Monkeypatch `boto3` AND `httpx` to RAISE if touched** — proves zero network.

1. **Dormant status:** `status()` → `storage:"local"`, `spaces:"not_configured"`, `search_engine:"jsonl"`.
   No raise.
2. **Put bytes offline (generated):** `put(b"\x89PNG…", kind="banner", campaign_id="c1", filename="0.png")`
   → `AssetRef.storage=="local"`, `url=="/creative/assets/<id>/raw"`, `format=="png"`, bytes>0, file on
   disk, `index.jsonl` + `assets/<id>.json` written, `audit.tail("asset")` has `asset.register`.
3. **Register hosted URL (async studio result):** `register("https://x/v.mp4", kind="video", campaign_id="c1")`
   → `source=="registered"`, url unchanged, no bytes written, recorded + indexed.
4. **Register text (creative-batch):** `register_text("Tired of slow…", kind="hook", campaign_id="c1")` →
   `kind=="hook"`, `text` populated and searchable.
5. **Founder upload:** `ingest_upload(b"…", filename="logo.svg", tenant_id="t1")` → kind sniffed
   (`logo`), `source=="uploaded"`, stored locally.
6. **Search facets:** `search({"campaign_id":"c1"})` returns all c1 assets newest-first; `search({"kind":"video"})`
   only #3; `search({"text":"Tired"})` only #4; `search({"format":"png"})` only #2; tenant-scoping proven
   (a second tenant's asset is invisible). Pagination (limit/offset) correct.
7. **Tag / status:** `tag(id, add=["urgency"])` then `search({"text":"urgency"})` finds it;
   `set_status(id,"winner")` reflected; both audited.
8. **Performance write-back + sort:** `attach_ad_ref(id,{"platform":"meta",…})` fills `platforms=["meta"]`;
   `update_metrics(id,{"ctr":0.08,"roi":3.1})`; `search({"sort":"top_roi","min_ctr":0.05})` ranks it first.
9. **Dormant Spaces no-op:** with `DO_SPACES_*` still unset, `put()` did NOT call boto3 (would have raised);
   `spaces.put_bytes("k",b"x")` → `{"status":"not_configured"}`, no raise.
10. **Soft + hard delete:** `delete(id)` → `status=="trashed"`, still searchable with `status="trashed"`;
    `delete(id, hard=True)` removes bytes + record; `get(id)` → `{}`.
11. **Never-raises fuzz:** unknown asset_id, garbage kind (→`other`), empty bytes, cross-tenant get, huge
    query → all return typed dicts/records, none raise.

Passes with **no keys, no sibling modules, no network.** That is the dormancy + offline bar.

---

## 10. BUILD UNITS (each: implement → run offline test → orchestrator commits → next)

1. `config.py` (DO_SPACES_* precedence §2.3, FAMIT_VAR, search-engine knob) + `models.py` (`AssetRef`
   superset, `AssetQuery`, `SearchPage`) (+ unit test of precedence + schema defaults).
2. `storage.py` local-first byte store + `index.py` `index.jsonl` writer (+ test §9.2 atomic write/append).
3. `library.py` core: `put`/`register`/`register_text`/`ingest_upload`/`get`/`list` + audit wiring
   (+ test §9.2–9.5).
4. `index.py` JSONL search engine: facet predicates + sort + pagination + tenant scope (+ test §9.6).
5. `library.py` mutators: `tag`/`set_status`/`attach_ad_ref`/`update_metrics`/`delete` (+ test §9.7/9.8/9.10).
6. `spaces.py` dormant DO Spaces uploader (boto3, §2.3 creds, presign) — no-op when unset (+ test §9.9).
7. `searchx.py` OPTIONAL engine adapters behind `ASSET_SEARCH_ENGINE` (dormant; jsonl stays authoritative).
8. `router.py` deferred APIRouter (§7, described, un-mounted); full `test_library_offline.py` green
   end-to-end (§9.1–9.11).

---

## 11. CREDENTIALS THE FOUNDER MUST PROVIDE

### 11.1 The Asset Library's OWN net-new creds — **DO Spaces only (and it's OPTIONAL)**
Everything works offline (local-first) with **nothing pasted**. DO Spaces unlocks durable cloud storage +
CDN delivery + cross-droplet sharing. **Canonical names = `DO_SPACES_*`; the video/image studios'
`SPACES_*`/`IMAGE_S3_*` are accepted as aliases (§2.3)** — so if the founder already set those for video,
the library uses them automatically.

| Env var | Required? | Where to get it | Effect when blank |
|---|---|---|---|
| `DO_SPACES_KEY` | for cloud | DO console → **Spaces Object Storage → Access Keys → Generate New Key** | local-only storage |
| `DO_SPACES_SECRET` | for cloud | (shown once when the key is generated — copy immediately) | local-only storage |
| `DO_SPACES_BUCKET` | for cloud | DO console → **Spaces → Create a Spaces Bucket** (name it e.g. `famit-creative`) | local-only storage |
| `DO_SPACES_REGION` | for cloud | the bucket's region slug (e.g. `blr1`, `nyc3`). Default `blr1`. | local-only storage |
| `DO_SPACES_ENDPOINT` | for cloud | `https://<region>.digitaloceanspaces.com` (e.g. `https://blr1.digitaloceanspaces.com`) | local-only storage |
| `DO_SPACES_CDN_BASE` | optional | the bucket's **CDN (Edge) endpoint** (DO console → Spaces → Settings → CDN), ideally Cloudflare-fronted | falls back to the direct Spaces URL |
| `ASSET_SEARCH_ENGINE` | optional | `jsonl` (default, zero-dep) \| `meilisearch` \| `typesense` \| `pg` | offline JSONL search (fully functional) |
| `ASSET_SEARCH_URL` / `ASSET_SEARCH_KEY` | only if engine≠jsonl | the chosen engine's host + admin key | n/a (jsonl) |
| `FAMIT_VAR` | already set | spine default `/opt/famit-agent/var` | spine default |

> **Net for the founder: paste the 5 `DO_SPACES_*` values once (a 5-minute DO-console chore) to get
> durable cloud storage + CDN. Until then the library is fully usable on the droplet's local disk.**
> If video storage was already configured with `SPACES_*`, the library lights up with **zero** new paste.

### 11.2 Click-by-click for the founder (non-technical) — getting the 5 DO Spaces values
1. DigitalOcean console → left sidebar **Spaces Object Storage** → **Create a Spaces Bucket** → pick region
   **Bangalore (blr1)** → name it `famit-creative` → Create. → that name is `DO_SPACES_BUCKET`,
   region slug `blr1` is `DO_SPACES_REGION`, endpoint is `https://blr1.digitaloceanspaces.com`.
2. Same page → **Access Keys** (or **API → Spaces Keys**) → **Generate New Key** → name it `famit-creative`
   → it shows a **Key** (`DO_SPACES_KEY`) and a **Secret** (`DO_SPACES_SECRET`) — **copy the secret now,
   it is shown only once.**
3. (Optional CDN) bucket → **Settings → Enable CDN** → copy the **Edge endpoint** → `DO_SPACES_CDN_BASE`.
4. Hand those 5 (+ optional CDN) to the platform; nothing else changes.

### 11.3 Sources (ACTIVE-in-2026, cited)
- **DigitalOcean Spaces** — S3-compatible object storage + built-in CDN, active product 2026.
  [docs.digitalocean.com/products/spaces], [digitalocean.com/products/spaces].
- **boto3** — AWS SDK for Python; standard S3-compatible client for DO Spaces (set `endpoint_url`);
  active, AWS-maintained 2026. [boto3.amazonaws.com/v1/documentation], [github.com/boto/boto3].
- **Pydantic v2** — JSON-schema + validation, existing repo dependency. [docs.pydantic.dev].
- **Meilisearch** (MIT, ACTIVE 2026, fast typo-tolerant search) [github.com/meilisearch/meilisearch];
  **Typesense** (GPL/commercial, ACTIVE 2026) [github.com/typesense/typesense] — OPTIONAL search upgrades.
- **In-repo seams (no new vendor for core path):** `store.py` atomic JSON/JSONL, `audit.py`
  (`record`/`tail`), `db/models.py` (`Campaign`/`Org`/`Lead`), and the frozen `AssetRef` in
  `design/creative-video-studio.md` §5d that this module formalizes.

---

## 12. WHICH CREATIVE-STUDIO SUB-PAGE THIS POWERS

Creative Studio is a **sidebar section with multiple sub-pages** (the Billing multi-page pattern). This
module powers the **shared "Asset Library" sub-page** — the cross-cutting gallery that every other
sub-page writes into and reads from:

- **"Asset Library"** (shared) — a searchable/filterable **gallery of every asset** (banners, images,
  videos, scripts, brochures, PDFs, landing pages, 3D, logos, product photos, ad copy, WhatsApp
  templates), with filters by **campaign / product / client / format / platform / kind / date / status /
  performance**, a **founder upload** button (logos, product photos), and per-asset **tag / approve /
  mark-winner / trash** actions. Backed by `GET /creative/assets`, `/assets/{id}`, `/assets/upload`,
  `/assets/{id}/tag|status|metrics`, `/assets/facets`.

It is the **substrate** beneath the Creative Batch, Image/Banner, Video, 3D, Landing, and Brochure
sub-pages (each registers its output here) and beneath the Autonomous Ads sub-pages (which read approved
assets, write back `ad_refs`/`metrics`, and flip status to winner/trashed). One library, every asset,
nothing lost, all reusable.

---

## RED-TEAM FIXES (folded)

Adversarial review 2026-06-09 against live source under `droplet_work/` and the shipped sibling design
docs. **Verdict: GO** (execution-ready). Every load-bearing compatibility claim was checked against
primary source and holds (see "Verified" below). The items here are split into (A) **robustness fixes
this review FOLDS INTO the spec** — they are now binding on the build agent — and (B) **residual risks
accepted** (stated, not blocking). These are NOT the pre-applied editorial fixes (list_assets rename,
text_snippet, kind default, etc.) — those are already in §4/§5 and were re-verified as correct.

### A. FIXES FOLDED (binding on the build — implement + test these, not just §9)

**A1 — Spaces-CONFIGURED-but-upload-FAILS path (the gap §9 structurally cannot catch).** §9's offline
test monkeypatches boto3 to RAISE and asserts it is never called — so it only proves the **unset** path.
The real production failure (founder pastes keys, then 403 / missing bucket / blocked egress / timeout)
is untested and unspecified. **Binding rule:** because `put()`/`put_bytes_async()` write locally FIRST
(§4.2/§2.2), an upload error MUST: keep the local copy, leave `storage="local"` and the local-serve
`url`, return the AssetRef normally, audit `meta.spaces_error=<short>`, and **NEVER raise and NEVER
downgrade `status` to `error:storage`** (a failed *cloud mirror* is not a storage failure — the bytes
are safe on disk). `spaces.put_bytes()` already returns `{"ok":False,"status":"error:..."}` on failure
(§6); `put()` MUST treat that branch identically to `not_configured` (local-only), differing only in the
audited reason. **Add §9 test 9.12:** monkeypatch `spaces.put_bytes` to return `error:403` with
`spaces_configured()` forced True → assert asset still registered, `storage=="local"`, no raise, no
`error:storage`.

**A2 — `delete(hard=True)` must not orphan the Spaces object.** §6's `spaces.py` surface is
`put_bytes`/`presign`/`spaces_configured` only — no delete seam. Once Tier-1 is live, `delete(hard=True)`
(§4.3) reclaims local bytes but leaves the cloud object → recurring storage cost **and a real
data-deletion / "right to erasure" gap for founder-uploaded logos/product photos**. **Binding rule:**
add a dormant `spaces.delete_object(key) -> dict` (no-op `{"status":"not_configured"}` when unset, never
raises, sync + `_async`); `delete(hard=True)` calls it best-effort when `storage=="spaces"`. Cloud-delete
failure is logged, never raised, and never blocks the local hard-delete. (Test optional offline; the
contract is what matters.)

**A3 — Canonical `AssetRef` type ownership (integration seam).** `creative-video-studio.md` §schema (line
181) lists its OWN `AssetRef` dataclass, yet line 349 calls `shared.library.register(AssetRef)`. This
module is now the **canonical owner** (`shared/models.py`, §5.1). **Binding note for the orchestrator:**
the video studio's build MUST `from creative.shared.models import AssetRef` and NOT redefine it, or two
divergent types drift apart. The video `schema.py` `AssetRef` entry is hereby superseded by this module's
superset. (No code change here — a wiring constraint recorded so the seam doesn't silently fork.)

**A4 — `sha256` wording corrected (no phantom feature).** §5.1 comments `sha256` as "dedupe / integrity".
There is no dedup-on-hash path in `put()` and adding one is out of scope. **Folded:** `sha256` is for
**integrity only** (best-effort content hash); dedupe is explicitly a non-feature unless a future unit
adds a hash-index lookup before write. Don't let "dedupe" imply behavior that isn't built.

### B. RESIDUAL RISKS ACCEPTED (stated; do NOT block GO)

- **B1 — Egress dependency for Tier-1 (deploy-time, real).** The panel/agent droplets are **egress-locked
  at the DO Cloud firewall** (`fortress/fortress-harden.sh` line 5/60: "egress handled by DO cloud
  firewall"; UFW allows outbound but the cloud firewall is the gate). Tier-1 Spaces uploads need outbound
  **HTTPS 443 to `*.digitaloceanspaces.com`** (and the chosen region endpoint) allow-listed in the DO
  Cloud firewall, else every upload silently takes the A1 local-only path. **Action when the founder
  enables Spaces:** add the Spaces endpoint host to the egress allowlist (prefer DO's private/regional
  endpoint where available). Until then, library is fully functional local-only — non-breaking. Add to
  `fortress/HUMAN_TASKS.md` at cred-paste time.
- **B2 — DO Spaces recurring cost not stated in §11.** §11 frames Spaces as a "5-minute chore" but omits
  $: DO Spaces base is **~$5/mo** (includes 250 GB storage + 1 TB outbound transfer), then overage on
  storage/transfer; CDN egress is metered. Trivial at this scale but it is a recurring bill, not free.
  Local-first (Tier 0) remains ₹0. (Vendor APIs themselves — boto3, Meilisearch/Typesense OSS — are free;
  the only cost is DO storage/transfer + any managed search host the founder opts into.)
- **B3 — `text_snippet` truncation (search completeness).** §5.2 indexes `text_snippet` = first 200 chars,
  so long scripts/ad-copy are not fully substring-searchable via the zero-network jsonl engine (a tail of
  a long script won't match). Honest limitation, acceptable for the offline default; the optional
  Meilisearch/Typesense engine (§2.5) closes it by indexing full `text`. Stated, not fixed.
- **B4 — No ToS / autonomous-bidding / 3D hype exposure HERE (by construction).** This module is a
  **passive recorder**: `register(url, kind="threed")`, `attach_ad_ref`, `update_metrics`, `set_status`.
  It **cannot bid, cannot spend, cannot generate 3D, cannot touch a platform API** — so platform-ToS risk
  and "autonomous bidding" / "3D generation" real-vs-hype simply do not live in this spec. Those risks are
  owned by `automation-ads.md` and `automation-threed.md`. (Review confirmed `automation-ads.md` carries a
  genuine defense-in-depth spend-safety design — platform-native daily cap as the real floor, a polling
  CPL/spend circuit-breaker, a human approval gate, full audit, `pause_all` kill switch, `ADS_DRY_RUN=1`
  default — and is **honest about the inter-poll overshoot window** rather than claiming a to-the-cent
  guarantee. The library's deferral of all spend gates to that doc is therefore legitimate, not
  hand-waving.)

### Verified against primary source (why this is GO, not faith)
- **Tools ACTIVE 2026:** DO Spaces (S3-compatible object storage + CDN), boto3 (AWS-maintained S3 client,
  `endpoint_url` for Spaces), Pydantic v2 (existing dep), Meilisearch (MIT) / Typesense (optional) — all
  current; no dead/abandoned dependency; core path adds **no new vendor** (reuses in-repo `store.py` /
  `audit.py`).
- **Dormancy pattern is real & matched:** `whatsapp.py` reads env at **call time** (`_cfg()`/`_meta_cfg()`),
  gates on `meta_configured()`/`is_configured()`, returns `{"status":"not_configured"}`, never raises —
  exactly the template §6 copies. `automation-video.md` line 156 confirms the "push to DO Spaces (boto3);
  no-op if `SPACES_*` unset" precedent and the `register(url)` (pass provider URL) path.
- **Truly non-breaking + crash-safe:** NEW files only under `creative/`; no edit to `caller.py`/`agent.py`;
  reuses `caller.py:108` `VAR=Path(os.getenv("FAMIT_VAR","/opt/famit-agent/var"))`, `store.py` atomic
  write + `_STORE_LOCK`, `audit.record/tail` (signatures match §1 verbatim, incl. `action_prefix`/
  `tenant_id`). Bare-import convention (`caller.py:34` `import whatsapp`) honored — no `droplet_work.`
  prefix.
- **`AssetRef` is a true backward-compatible superset:** `creative-video-studio.md` §5d frozen shape (11
  fields) is kept verbatim in §5.1; the `kind` enum `video|image|banner|copy|threed|landing` is preserved
  and extended additively; new fields are all additive. `batch_id` widened `vb_...` → `vb_...|cb_...|''`
  is additive (broader accepted set), not a breaking redefinition.
- **DB facets exist:** `db/models.py` `Org:44 / User:55 / Campaign:87 / Lead:106` — exact line matches; the
  search-facet joins are real. `credit-ledger-firewall.md` (hold/reserve/cap) exists as the financial-hold
  deferral target.
- **Async pattern sound:** the library is a **sink, not a driver** (§2.6) — async studios call
  `register(url)` from their own webhook/poll callback (`creative-video-studio.md` §collect_batch line
  266/349), so "results return automatically" is satisfied without the library running any poller. No
  hidden background loop, no thread it must own. Correct and minimal.

**Residual-risk summary (post-fold):** B1 (egress allowlist — a deploy-time founder/ops task, recorded for
cred-paste time), B2 (~$5/mo DO Spaces when enabled), B3 (200-char jsonl search truncation — closed by the
optional engine). None block execution. A1–A4 are now binding on the build agent.
