# BROCHURE AI + CATALOG / PRODUCT-SHEET STUDIO — Execution-Ready Design Spec

> **For the build agent:** implement this verbatim. This is a NEW module of the Famit **Creative
> Studio** — the "brochure / catalog / PDF" pillar of the Autonomous Business OS. It turns a
> vendor's stored **business + product + campaign** data into finished, print-ready and
> share-ready **PDF documents**: business & **real-estate brochures**, **product catalogs /
> product sheets**, **PDF offers**, and **pitch decks** — each from a dropdown selection, in a
> testing **batch** (e.g. 5 brochure layout variants, 3 catalog skins), flowing into the rest of
> the revenue loop (ads / leads / CRM / voice / WhatsApp / analytics).
>
> **The single most important framing (read first):** unlike the `automation/image` module, the
> core of THIS module is **NOT dormant-until-creds**. A PDF assembly engine needs **zero
> credentials** and runs **fully offline and free** (HTML/CSS or Typst → PDF, all OSS). So:
> - **CORE = ALWAYS-ON, local, free PDF assembly** (template + data-binding + render + store).
>   With no keys at all, the module still produces real multi-page PDFs.
> - **DORMANT-UNTIL-CREDS layer = only the optional AI ENRICHMENT** (LLM-written copy, AI hero
>   imagery / floor-plan beautification). When those keys are absent, enrichment is skipped and
>   the brochure is built from the vendor's raw stored data + a stock/templated layout — it never
>   no-ops the whole document, and it **never raises**.
>
> **Hard rules from the project brief (do not violate):**
> - NEW code ONLY under `droplet_work/creative/`. **Do NOT edit `caller.py` / `agent.py`** — final
>   wiring into the backend spine is deferred to the orchestrator.
> - NO git operations (the orchestrator commits).
> - Provider-agnostic; the AI-enrichment integrations are **dormant-until-creds** (skipped + a
>   status flag, never an exception), exactly like `whatsapp.py`.
> - **Verifiable offline**: the acceptance test makes **zero live external calls** — it renders a
>   real multi-page PDF from a template + fixture data and asserts valid PDF bytes. No keys, no
>   Docker, no network.
> - Cost-optimized; self-host on DigitalOcean where it wins; production-grade, scalable.
> - **REVENUE-CONNECTED**: every asset is addressable so it can be attached to ads, sent over
>   WhatsApp, linked from a landing page, handed to the voice agent, and counted in analytics.

---

## 0. TL;DR — the decisions that define this module

1. **Three PDF engines behind one interface; default is in-process and free.** PDF rendering is a
   solved OSS problem in 2026 — there is no reason to pay a SaaS or self-host Chromium for the
   common case. The module ships a `PdfEngine` abstraction with three backends, picked per job:
   - **`weasyprint` (DEFAULT, always available)** — a Python library (BSD-3), **no Chromium, no
     Docker, no network**. *(Not literally "pure-Python": the layout engine is Python, but it
     links native **Pango / HarfBuzz / fontconfig / glib** system libs for text shaping — a
     one-time `apt install`, free, present by default on the Linux droplet. See §12 row 0 / §14.)*
     Renders HTML+CSS (CSS Paged Media: running headers/footers, page numbers, `@page`, PDF/A).
     This is the engine the **offline acceptance test** uses and the fallback for every deployment
     that hasn't stood up a render box. Slower on very large image-heavy docs, but correct and
     credential-free. *(WeasyPrint 69, June 2026.)*
   - **`gotenberg` (OPTIONAL, self-hosted, high-fidelity)** — a **MIT-licensed**, Docker-based
     **headless-Chromium** render service on a DO droplet. Decisive for **designer-authored,
     visually rich brochures** (web fonts, gradients, JS-driven charts, pixel-faithful layout)
     and because it natively does **PDF/A compliance, AES-256 encryption (QPDF), merge/split,
     and metadata** — capabilities a brochure pipeline genuinely needs and no other Chromium tool
     bundles. Env-gated by `BROCHURE_GOTENBERG_URL`; when unset, the module never reaches for it.
   - **`typst` (OPTIONAL, data-dense)** — **Apache-2.0**, a fast programmable typesetting system,
     ideal for **large product catalogs / price lists / spec sheets** (hundreds of SKUs, tables,
     repeating cells) where WeasyPrint gets slow and Chromium is overkill. Env-gated by a
     `typst` binary being present (`BROCHURE_TYPST_BIN`).

   **Explicitly rejected: `wkhtmltopdf`.** It was **archived in Jan 2023**, last release 2020 on a
   ~2012 WebKit, and carries **CVE-2022-35583 (CVSS 9.8, SSRF)** — using it to render
   user/vendor-supplied HTML is a live security hole. **Do not use it anywhere in this module.**

2. **This module is the ASSEMBLER, not the content/imagery generator — it delegates.** It does
   layout + data-binding + pagination + PDF assembly + storage. It does **not** re-implement copy
   generation or image generation:
   - **Marketing copy / headlines / amenity blurbs** → call the **existing LLM seam** (the
     marketing module's `content.py` / the LLM router). If that seam isn't configured, the
     brochure uses the vendor's raw stored fields and templated boilerplate (degrade, don't fail).
   - **Hero images / lifestyle shots / floor-plan beautification** → call the **existing
     `droplet_work/automation/image` module** (`generate(ImageBrief)`). If image gen is
     not_configured, use the vendor's uploaded photos or a neutral placeholder block.
   This boundary is what keeps the spec focused and avoids duplicating two other modules.

3. **Templates are data-driven and themeable, not hard-coded layouts.** A document = a **template
   pack** (`document_type` × `theme`) + a **typed data context** built from the vendor's stored
   business/product/campaign records. The same real-estate data renders into N theme variants for
   the testing batch. Templates live as files (Jinja2-HTML for WeasyPrint/Gotenberg, `.typ` for
   Typst), so adding a brochure style = adding a template pack, no code change.

4. **Async-job pattern is real here, not cosmetic.** A multi-page, image-heavy catalog render (or
   one that waits on AI imagery) is **slow** — it must not block an HTTP request. Every build is a
   **job**: `queued → rendering → (enriching) → rendered → stored` (or `failed`), addressable by
   `job_id`, pollable, with the finished PDF fetchable by URL. A synchronous fast-path exists for
   tiny single-page offers.

5. **Guardrails are right-sized for a (mostly free) PDF engine.** PDF render itself costs ₹0, so
   per-image spend ceilings are **not** the headline control here — any AI-enrichment spend is
   already gated by the `image`/LLM meters this module delegates to. The controls that matter:
   - **AUDIT every generation** (append-only, like `audit.py`).
   - **APPROVAL GATE before a brochure is PUBLISHED / SENT** to a customer (WhatsApp, public link,
     ad asset) — a manager must sign off on a customer-facing document. Drafting is free and
     ungated; *distribution* of a finished asset is gated.
   - **RERA / compliance enforcement** for real-estate documents (see §7) — a legal requirement,
     not optional.

6. **Real-vs-hype, honest (§9).** What ships: genuinely good, on-template, multi-page PDFs from
   structured data, with optional AI copy/imagery and a human approval gate. What does NOT ship:
   "one click → a finished, legally-cleared, pixel-perfect agency brochure with zero human." Final
   sign-off, brand-exact lockups, and legal/RERA claims remain human-gated.

---

## 1. EVIDENCE — chosen tools + why (2026 web research, sources cited)

> Researched June 2026. Where a marketing blog contradicted a primary/source-of-truth page, the
> primary source wins. License facts taken from each project's own repo/site.

| Need | Chosen tool | Why (evidence) | License / cost |
|---|---|---|---|
| **Default engine: in-process, free, offline, no Docker** | **WeasyPrint 69** (Python lib + native Pango/HarfBuzz/fontconfig) | HTML+CSS → PDF with full **CSS Paged Media** (running headers/footers, page numbers, `@page`, PDF/A, CMYK); no Chromium dependency; image ~200–400 MB; ideal for invoices/brochures/reports. Needs system Pango/HarfBuzz/fontconfig libs (one-time `apt`, free), but **zero credentials, no external services, no network** → powers the offline test. Actively maintained by CourtBouillon (latest June 2, 2026). | **BSD-3** (free commercial) |
| **High-fidelity designer brochures (self-host)** | **Gotenberg** (Docker, headless Chromium + LibreOffice) | Renders **exactly like a browser** (web fonts, gradients, JS charts); **uniquely bundles PDF/A (1a/2b/3b), AES-256 encryption via QPDF, merge/split, metadata** — all things a brochure pipeline needs. 70M+ Docker pulls, ~2M+/month, 7,500+ stars; self-host on a DO droplet. Also converts DOCX/PPTX→PDF (vendor-supplied decks). | **MIT** (free); infra ≈ 0.5–1 GB RAM per Chromium instance on a small DO box |
| **Data-dense catalogs / price lists / spec sheets** | **Typst** | Fast programmable typesetting; scales to hundreds of SKUs / large tables where WeasyPrint slows and Chromium is wasteful; embeddable compiler; clean templating with a real scripting layer. | **Apache-2.0** (free commercial) |
| **Copy generation (headlines, blurbs, CTAs)** | **Existing LLM seam** (marketing `content.py` / LLM router) | Brief rule: "reuse the existing LLM seam; no new vendor." No new dependency, spend already metered. | reuse |
| **Hero / lifestyle / floor-plan imagery** | **Existing `automation/image` module** | Already provider-agnostic, dormant-until-creds, metered, audited. Don't duplicate it. | reuse |
| **Charts/graphs inside catalogs (optional)** | server-side SVG (e.g. matplotlib/`pygal`-style → SVG) embedded into the template | SVG embeds cleanly in all three engines; no JS runtime needed for WeasyPrint/Typst. | OSS |
| ~~HTML→PDF via wkhtmltopdf~~ | **REJECTED** | **Archived Jan 2023**; last release 2020 (WebKit ~2012); **CVE-2022-35583 CVSS 9.8 SSRF** on user-supplied HTML. Security incident, not a tool choice. | do not use |

**Engine selection rule baked into the router (§3):**
- `BROCHURE_ENGINE` env can pin one globally; otherwise per-`document_type`:
  `catalog`/`product_sheet`/`price_list` (data-dense) → **typst** if available, else weasyprint;
  `brochure`/`pitch_deck`/`offer` (visual) → **gotenberg** if `BROCHURE_GOTENBERG_URL` set, else
  **weasyprint**; vendor-supplied DOCX/PPTX → **gotenberg** (LibreOffice path) if available, else
  `status="needs_gotenberg"`.
- **WeasyPrint is the universal floor** — every deployment can render *something* with no setup.

**Sources:**
- https://gotenberg.dev/ and https://github.com/gotenberg/gotenberg (MIT; Chromium+LibreOffice; PDF/A, QPDF encryption, merge/split, metadata)
- https://hub.docker.com/r/gotenberg/gotenberg (Docker pulls / scale)
- https://pypi.org/project/weasyprint/ and https://doc.courtbouillon.org/weasyprint/stable/ (BSD-3; v69 June 2026; CSS Paged Media, PDF/A, CMYK, Grid)
- https://github.com/typst/typst and https://typst.app/open-source/ (Apache-2.0; embeddable compiler; programmable)
- https://news.speedata.de/2026/02/10/typesetting-benchmark/ (Typst scales; WeasyPrint slow on large/complex docs)
- https://doc.doppio.sh/article/wkhtmltopdf-is-now-abandonware (archived Jan 2023; abandonware)
- https://docraptor.com/wkhtmltopdf-alternatives and CVE-2022-35583 (CVSS 9.8 SSRF — do not use)
- https://ironsoftware.com/suite/blog/comparison/html-to-pdf-2026-guide/ (2026 landscape; Chromium tools cost 6–11× CPU/RAM vs lightweight)
- https://pdfnoodle.com/blog/best-pdf-generation-apis (2026 PDF API/engine landscape)

---

## 2. FILES TO CREATE (all NEW, under `droplet_work/creative/`)

```
C:\Users\kunal\Desktop\caps\droplet_work\creative\
  __init__.py
  README.md                       # what it does, the cred list, how to run the offline test
  brochure_catalog\
    __init__.py                   # PUBLIC API: build(), build_async(), status(), engines_status(),
                                  #             list_templates(), get_job(), approve(), publish()
    types.py                      # DocSpec, DocContext, BuildResult, JobRecord dataclasses + validate/normalize
    context.py                    # builds a typed DocContext from vendor business/product/campaign data
    router.py                     # document_type + env -> PdfEngine selection (weasyprint|gotenberg|typst)
    enrich.py                     # OPTIONAL AI enrichment: copy via LLM seam, imagery via automation/image
                                  #   (dormant-until-creds: skipped + flagged, never raises)
    templates_registry.py         # discovers template packs (document_type x theme); list_templates()
    jobs.py                       # async job lifecycle: queued->rendering->enriching->rendered->stored/failed
    store.py                      # write PDF + brief/result/manifest under var/creatives/brochures/<job_id>/
    meter.py                      # brochure_meter: status() + (mostly ₹0) cost rollup; usage_event passthrough
    audit_hook.py                 # thin wrapper around droplet_work/audit.py if importable, else no-op
    guardrails.py                 # approval gate (publish/send), RERA/compliance check, safety prefilter
    engines\
      __init__.py                 # ENGINE REGISTRY: id -> engine module; resolve()
      base.py                     # PdfEngine protocol: id, available()->bool, render(html|typ, assets)->bytes
      weasyprint_engine.py        # DEFAULT in-process engine (no network). render HTML+CSS -> PDF bytes
      gotenberg_engine.py         # optional: POST to BROCHURE_GOTENBERG_URL (Chromium). dormant w/o URL
      typst_engine.py             # optional: shell out to typst binary (BROCHURE_TYPST_BIN). dormant w/o bin
    templates\
      html\                       # Jinja2 + CSS Paged Media packs (used by weasyprint & gotenberg)
        brochure_business\        # base.html, theme overrides, print.css, partials/
        brochure_realestate\      # project/location/amenities/floorplan/pricing/possession/RERA/CTA blocks
        catalog_grid\             # product grid catalog
        product_sheet\            # single-product spec sheet
        offer_flyer\              # single-page PDF offer
        pitch_deck\               # multi-slide deck (one @page per slide)
      typ\                        # Typst packs for data-dense catalogs/price lists
        catalog_dense\            # main.typ + theme.typ
        price_list\
      _shared\                    # fonts (incl. Devanagari), brand css vars, base partials, placeholder.png
  tests\
    __init__.py
    test_brochure_offline.py      # THE acceptance test — renders a real multi-page PDF, ZERO network/keys/Docker
    fixtures\
      realestate_project.json     # a full real-estate data context fixture (incl. RERA no.)
      product_catalog.json        # a multi-SKU catalog fixture
  selfhost\
    README.md                     # founder click-by-click: stand up Gotenberg on a DO droplet (optional)
    docker-compose.gotenberg.yml  # gotenberg service on the private VPC (commented; deploy later)
```

Mirror conventions already in the repo (verified against source):
- **never-raise / graceful-degrade when a *dependency* is unconfigured** → `whatsapp.py`
  (`is_configured()`, returns a status dict, never raises). Here it's the AI-enrichment layer that
  degrades, not the whole document.
- **internal metering → usage_events** (cost = metered × rate card, `estimated:True`,
  `status()=="configured"`) → `vendors/groq_meter.py`.
- **append-only audit, best-effort, IST timestamps, swallow all exceptions; `record(actor, action,
  object_type, object_id, channel, tenant_id, meta)`** → `audit.py`.
- **shared no-raise HTTP** (Gotenberg call) → reuse `vendors/_http.py`'s retry/timeout pattern.
- **secret/config resolver** → `config.py` (`get()`/`require()`); use `config.get()` with an
  `os.getenv` fallback so Doppler works later without a hard dependency.

---

## 3. PUBLIC INTERFACE (the only surface `caller.py` will later import)

```python
# droplet_work/creative/brochure_catalog/__init__.py
from .types import DocSpec, DocContext, BuildResult, JobRecord

def status() -> dict: ...
    # {"status":"ready",                       # ALWAYS ready — weasyprint is built-in
    #  "engines":{"weasyprint":"available","gotenberg":"available|not_configured","typst":...},
    #  "default_engine":"weasyprint",
    #  "enrichment":{"copy":"configured|not_configured","imagery":"configured|not_configured"},
    #  "approval_required_for_publish": bool}

def engines_status() -> dict: ...            # {"weasyprint":"available", "gotenberg":..., "typst":...}

def list_templates(document_type: str = "") -> list[dict]: ...
    # [{"document_type":"brochure_realestate","theme":"navy","engine":"weasyprint"}, ...]

def build(spec: "DocSpec | dict", *, tenant_id: str = "", sync: bool = False) -> "BuildResult": ...
    #   1. normalize+validate DocSpec (document_type, theme, language, data ref, batch n)
    #   2. context.build(spec, tenant_id) -> DocContext  (pull vendor business/product/campaign data)
    #   3. guardrails.compliance_check(context)          (RERA etc. for real-estate -> may flag)
    #   4. (optional) enrich.apply(context)              (LLM copy + automation/image imagery; skipped if not_configured)
    #   5. router.select(spec) -> engine_id
    #   6. for each theme variant in the batch: render template -> PDF bytes -> store.save(...)
    #   7. meter.record(...) ; audit_hook.log("brochure.build") ; return BuildResult
    #   sync=True renders inline (fast-path for 1-page offers); else enqueues a job and returns job_id

async def build_async(spec, *, tenant_id="") -> "JobRecord": ...   # enqueue; returns queued JobRecord

def get_job(job_id: str, *, tenant_id: str = "") -> "JobRecord": ...   # poll status + asset urls

def approve(job_id: str, *, tenant_id: str, approver: str) -> "BuildResult": ...
    # flips a pending-publish asset to approved (manager role); audited "brochure.approved"

def publish(job_id: str, *, tenant_id: str, channel: str, target: str = "") -> dict: ...
    # channel in {"whatsapp","link","ad_asset","crm"}; GATED by approval if required; audited.
    # Does NOT itself send — returns a {"asset_url":..., "ready_to_attach":True} handoff the
    # spine routes to whatsapp.py / ads / landing-page module. (No spine edits here.)
```

### `DocSpec` (input contract) — `types.py`
```python
@dataclass
class DocSpec:
    document_type: str                 # brochure_business|brochure_realestate|catalog_grid|
                                       #   product_sheet|offer_flyer|pitch_deck|price_list
    theme: str = "default"             # template-pack theme; "*" or list -> batch of variants
    themes: list[str] | None = None    # explicit batch of themes (testing batch); overrides `theme`
    language: str = "en"               # en|hi|ta|... (selects fonts; Devanagari bundled in _shared)
    data_ref: dict | None = None       # {kind:"product"|"campaign"|"project", id:"..."} -> context.py resolves
    inline_data: dict | None = None    # OR pass the data context directly (used by the offline test/fixtures)
    page_size: str = "A4"              # A4|Letter|A5|Legal
    engine: str = ""                   # optional hard override of the router
    enrich: bool = True                # allow AI copy/imagery enrichment (no-op if keys absent)
    pdf_a: bool = False                # request PDF/A (archival) output (gotenberg/weasyprint)
    encrypt: bool = False              # password-protect (gotenberg only; ignored elsewhere w/ flag)
    n_variants: int = 1                # if theme=="*", how many themes to render (testing batch cap)
    brand: dict | None = None          # {logo_url, palette:[...], font, company, contact, watermark}
    tenant_id: str = ""
```

### `DocContext` (the typed, template-ready data) — `context.py`
A normalized dict the templates bind to. For **real-estate** it REQUIRES (validated in §7):
`project_name, developer, location, configurations[], price_from, amenities[], floor_plans[],
possession_date, rera_number, contact, site_visit_cta, whatsapp_number, disclaimer`. For
**catalog/product**: `products[]` each `{sku, name, image, price, specs{}, description}`. `context.py`
pulls these from the vendor's stored business/product/campaign records (the same store the rest of
the platform uses); for the offline test they come straight from a fixture JSON.

### `BuildResult` / `JobRecord` (output contract)
```python
@dataclass
class BuildResult:
    ok: bool
    status: str                        # rendered|queued|rendering|enriching|stored|failed|
                                       #   needs_gotenberg|compliance_block|pending_approval|invalid
    job_id: str                        # time-sortable; names var/creatives/brochures/<job_id>/
    document_type: str
    engine: str                        # which PdfEngine actually rendered
    assets: list[dict]                 # [{"theme":"navy","path":...,"url":...,"pages":12,"bytes":...,
                                       #   "format":"pdf","approved":bool}]
    est_cost_inr: float                # 0.0 for pure render; >0 only if AI enrichment ran (passthrough)
    estimated: bool                    # True when any AI-enrichment cost is included
    enrichment_used: dict              # {"copy":bool,"imagery":bool}  (False when those keys absent)
    compliance: dict                   # {"rera_ok":bool, "notes":[...]} for real-estate
    latency_ms: int
    meta: dict                         # {themes, language, page_size, route_reason}

@dataclass
class JobRecord:
    job_id: str; status: str; document_type: str
    assets: list[dict]; created_ts: str; updated_ts: str; error: str = ""
```

### Engine selection (`router.py`) — deterministic, env-overridable
```
override order:  spec.engine  >  BROCHURE_ENGINE (global pin)  >  per-document_type default ladder
per-type ladder (only engines whose available()==True are eligible; weasyprint is always available):
  document_type in (catalog_grid, product_sheet, price_list)  -> typst if available else weasyprint
  document_type in (brochure_*, pitch_deck, offer_flyer)       -> gotenberg if URL set else weasyprint
  vendor-supplied DOCX/PPTX source                             -> gotenberg (LibreOffice) else status="needs_gotenberg"
universal floor: weasyprint (in-process, no setup). route_reason records the choice.
```
Env overrides (all optional): `BROCHURE_ENGINE`, `BROCHURE_ROUTE_CATALOG`, `BROCHURE_ROUTE_BROCHURE`,
`BROCHURE_GOTENBERG_URL`, `BROCHURE_TYPST_BIN`.

---

## 4. ENGINE ADAPTERS — interface + per-engine behavior

```python
# engines/base.py
class PdfEngine(Protocol):
    id: str
    def available(self) -> bool: ...                       # weasyprint: import ok; gotenberg: URL set; typst: bin found
    def render(self, *, html: str | None = None, typ: str | None = None,
               assets_dir: str | None = None, page_size: str = "A4",
               pdf_a: bool = False, encrypt: str = "") -> tuple[bool, bytes | None, str]: ...
               # returns (ok, pdf_bytes, error); NEVER raises
```

**`weasyprint_engine` (DEFAULT, always-on, no network).** `available()` = `import weasyprint`
succeeds. `render()` runs `weasyprint.HTML(string=html, base_url=assets_dir).write_pdf(...)` with a
CSS for `@page`/PDF/A. Pure in-process; the **offline test runs entirely through this**. No keys.

**`gotenberg_engine` (optional, self-hosted Chromium).** `available()` = `BROCHURE_GOTENBERG_URL`
set. `render()` POSTs the HTML bundle (and assets) to `{URL}/forms/chromium/convert/html`
(multipart) using the `vendors/_http.py`-style no-raise client; for DOCX/PPTX uses
`/forms/libreoffice/convert`; applies PDF/A and encryption via Gotenberg's native options. Dormant
(returns `(False, None, "gotenberg_not_configured")`) when the URL is unset — **router never routes
here unless available**, so this is a clean degrade, not a user-facing error.

**`typst_engine` (optional, data-dense).** `available()` = `BROCHURE_TYPST_BIN` resolves to a
runnable `typst` binary. `render()` writes the `.typ` + data JSON to a temp dir and runs
`typst compile main.typ out.pdf` (subprocess, timeout, no shell-injection — args list, never a
shell string). Dormant when the binary is absent.

> All three are pure functions of (template-rendered input → PDF bytes). **No engine knows about
> tenants, spend, or audit** — those live in the orchestration layer (`build()`), so engines stay
> swappable and individually testable.

---

## 5. AI ENRICHMENT — the ONLY dormant-until-creds layer (`enrich.py`)

`enrich.apply(context, spec) -> (context, enrichment_used: dict)`. **Best-effort, never raises,
degrades silently:**

- **Copy** (`enrichment_used["copy"]`): if the LLM seam (marketing `content.py` / LLM router) is
  importable AND configured, generate/upgrade headline, sub-head, amenity blurbs, product
  descriptions, and CTAs from the raw data context (kept short; brand voice from `spec.brand`).
  If not configured → leave the vendor's raw fields / templated boilerplate as-is, set
  `copy=False`. **Any LLM spend is metered by that module, not re-metered here.**
- **Imagery** (`enrichment_used["imagery"]`): if `droplet_work/automation/image` reports
  `status()=="ready"`, request a hero/lifestyle image (`ImageBrief(job_type="banner"/"product",
  language=spec.language, brand=...)`) and/or floor-plan beautification; drop the returned asset
  path into the context. If image gen is `not_configured` → use the vendor's uploaded photos or
  `_shared/placeholder.png`, set `imagery=False`. **Image spend is gated + metered by the image
  module's own budget/meter** — this module does not duplicate per-image caps.

Crucially: **with NO enrichment keys at all, `build()` still returns a real, complete PDF** from the
vendor's data + templated layout. Enrichment makes it *better*, never *possible*.

---

## 6. ASYNC-JOB PATTERN (`jobs.py`) — for slow / image-heavy renders

```
build(sync=False) / build_async():
  1. create JobRecord{job_id, status:"queued"} -> store var/creatives/brochures/jobs/<job_id>.json
  2. a worker (in-process ThreadPool today; swappable for the platform's queue later) picks it up:
       status:"rendering" -> (if enrich) "enriching" -> render each theme -> "stored"
     each transition is persisted (crash-safe: a killed worker leaves a readable last state)
  3. get_job(job_id) returns the JobRecord (status + asset urls); the spine/UI POLLS this
  4. on any engine error -> status:"failed", error set, audited; partial assets kept
```
- **Idempotent & crash-safe:** the job file IS the source of truth; re-running a `queued`/`failed`
  job is safe. Mirrors the "small verifiable unit, persist state, then continue" house rule.
- **Sync fast-path** (`sync=True`): single-page `offer_flyer` with no AI imagery renders inline in
  the request (sub-second with weasyprint) and returns `status:"rendered"` directly.
- The worker abstraction is deliberately thin so the orchestrator can later back it with the
  platform's real job queue (e.g. the Hatchet orchestration in `orchestration-hatchet.md`) by
  swapping one module — **no interface change**.

---

## 7. GUARDRAILS — audit, approval-to-publish, RERA/compliance, safety (`guardrails.py`)

Right-sized: render is free, so the controls protect **distribution** and **legal claims**, not
per-pixel spend.

**1. AUDIT (always).** Every `build`, `approve`, `publish`, `compliance_block`, and `failed`
appends via `audit_hook` → `audit.record(actor=tenant_id, action="brochure.build"|"brochure.approved"
|"brochure.published"|"brochure.compliance_block", object_type="creative", object_id=job_id,
channel="api", tenant_id=..., meta={document_type, engine, themes, est_cost_inr})`. Best-effort;
never breaks a build.

**2. APPROVAL GATE — before PUBLISH/SEND, not before draft.** Building/previewing a brochure is
free and ungated. **`publish()` to a customer channel (whatsapp/link/ad_asset) requires manager
approval** when `BROCHURE_REQUIRE_PUBLISH_APPROVAL=1` (recommended default ON for real-estate). An
unapproved asset publish returns `status="pending_approval"` and writes
`var/creatives/brochures/pending/<job_id>.json`; `approve(job_id, approver=...)` flips it. This is
the "approval gate" the brief requires — placed at the *spend/reputation/legal* boundary
(distribution), which is where it actually protects the business.

**3. RERA / COMPLIANCE (real-estate — legally required, NOT optional).** For
`document_type == brochure_realestate`, `compliance_check(context)` **requires**:
- `rera_number` present and non-empty (else `status="compliance_block"`, **no PDF emitted**,
  audited) — Indian real-estate advertising legally must carry the RERA registration number.
- the **RERA disclaimer block** is force-injected into the template footer (the template cannot
  omit it).
- a denylist scan for prohibited/over-promising claims ("guaranteed returns", "assured
  appreciation", "100% safe investment") → flagged in `compliance.notes`, and such a doc **cannot
  be published without explicit manager approval** even if the publish gate is otherwise off.
- price/possession/floor-plan figures are rendered verbatim from the vendor's data (no AI
  fabrication of legal/financial figures — enrichment is barred from editing these fields).

**4. SAFETY PREFILTER (cheap, local).** Before AI enrichment, a small denylist blocks obviously
disallowed briefs (explicit, hateful, real-person-likeness of a named public figure, etc.) →
enrichment skipped, flagged; the document still renders from raw data. First-line only, not a
substitute for the underlying providers' moderation.

**5. SPEND (passthrough only).** Pure render = ₹0. Any AI-enrichment cost is incurred and capped by
the **image/LLM modules' own budget gates**; this module just records the returned `est_cost_inr`
into the usage stream (§ meter) so brochure-attributed AI spend shows up in billing — it does not
add a second, conflicting cap.

---

## 8. STORAGE & DATA (`store.py`) — `var/creatives/brochures/`

```
/opt/famit-agent/var/creatives/brochures/
  <job_id>/
    spec.json            # normalized DocSpec + route_reason + tenant
    context.json         # the DocContext actually rendered (auditable: exactly what went into the PDF)
    <theme>.pdf          # one finished PDF per theme variant in the batch
    manifest.json        # BuildResult (engine, themes, pages, bytes, cost, compliance, approved flags)
  jobs/<job_id>.json     # live JobRecord (async status source of truth)
  pending/<job_id>.json  # only when publish-approval gate holds an asset
  index.jsonl            # append-only one-line-per-job index (tenant, document_type, themes, ts, cost)
```
- `job_id` = time-sortable `YYYYMMDD-HHMMSS-<rand>` (IST). Dirs created lazily; storage failures are
  swallowed best-effort (like `audit.py`) and downgrade `status` to `failed:storage` without raising.
- PDFs stored locally on the droplet first; an optional DO Spaces / S3 sink (`BROCHURE_S3_*`) is a
  **later follow-up** (interface stub present, dormant). Listing reads `index.jsonl` newest-first,
  tenant-scoped, with offset/limit (same shape as `audit.tail()`).
- **Every asset is addressable by URL** → this is the hook that makes brochures revenue-connected
  (§ below).

---

## 9. HOW IT CONNECTS TO THE REST (revenue loop)

The module emits **addressable PDF assets + structured metadata**; the spine routes them. No spine
edits here — these are the documented handoffs the orchestrator wires later:

- **→ ADS:** a brochure/offer PDF (or its first-page render as an image) becomes an `ad_asset` via
  `publish(channel="ad_asset")`; the ads module attaches it to a campaign variant. Catalog pages
  feed product-feed ads.
- **→ LEADS / CRM:** every published asset carries `{job_id, tenant_id, document_type, campaign_id}`
  so a click/scan/WhatsApp-request on it can be attributed to a lead and written to CRM.
- **→ WHATSAPP:** `publish(channel="whatsapp")` returns an `asset_url` the spine hands to
  `whatsapp.py` as a document message (real-estate brochure / catalog / offer) — gated by approval.
- **→ VOICE:** the voice agent (caller.py/agent.py) can reference "I've sent you the brochure on
  WhatsApp" — the asset_url is available in the lead record for the agent to mention/trigger.
- **→ ANALYTICS:** `index.jsonl` + audit events + per-asset URLs give which document_type/theme was
  built, published, on which channel, at what cost → feeds the autonomous-ads analytics loop
  (which creative variant drove leads/conversions, so winners scale and losers are trashed).
- **→ CREATIVE STUDIO UI:** see the sub-page mapping below.

---

## 10. WHICH CREATIVE-STUDIO SUB-PAGE THIS POWERS

Creative Studio is a sidebar section with multiple sub-pages (Billing's multi-page pattern). This
module powers the **"Brochures & Catalogs"** sub-page (alongside sibling sub-pages: Banners/Images,
Videos, Ad Copy/Hooks, Landing Pages, 3D). On that sub-page the vendor:
1. picks a **document type** from a dropdown (Business Brochure / Real-Estate Brochure / Product
   Catalog / Product Sheet / PDF Offer / Pitch Deck / Price List),
2. picks the **product/project/campaign** (dropdown over stored data) and a **theme** (or "generate
   a testing batch of N variants"),
3. clicks **Generate Batch** → async jobs render N themed PDFs,
4. **previews** each PDF, **approves** the winner, and **publishes** it to WhatsApp / a public link /
   an ad asset / CRM — all from this one sub-page.

The endpoints in §11 are the sub-page's backend contract.

---

## 11. ENDPOINTS (designed now, **wired later by the orchestrator** — DO NOT edit `caller.py`)

The module exposes plain functions; mounting is a thin `add_api_route` later.

| Method/Path | Body / Query | Returns | Notes |
|---|---|---|---|
| `POST /creatives/brochures/build` | `DocSpec` JSON | `BuildResult`/`JobRecord` | always renders ≥ weasyprint; `sync` for 1-page |
| `GET /creatives/brochures/status` | – | `status()` | engine + enrichment readiness |
| `GET /creatives/brochures/templates` | `?document_type` | `list_templates()` | dropdown source for the sub-page |
| `GET /creatives/brochures/jobs/{job_id}` | – | `JobRecord` | poll async render; tenant-scoped |
| `GET /creatives/brochures/{job_id}` | – | `manifest.json` | finished assets list |
| `GET /creatives/brochures/{job_id}/asset/{theme}` | – | PDF bytes | `Content-Type: application/pdf` |
| `GET /creatives/brochures` | `?limit&offset` | list from `index.jsonl` | newest-first, tenant-scoped |
| `POST /creatives/brochures/{job_id}/approve` | `{theme?}` | `BuildResult` | manager role; flips pending → approved |
| `POST /creatives/brochures/{job_id}/publish` | `{channel,target?}` | handoff dict | approval-gated; routes to whatsapp/ads/crm |

All write/approve/publish paths call `audit_hook`. Auth/tenant scoping reuses the existing
`auth.py`/middleware the spine already applies — not re-implemented here.

---

## 12. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

**The module renders real, complete, multi-page PDFs with NONE of these** (WeasyPrint is built-in
and free). Add only to unlock fidelity / AI enrichment. Set in `/opt/famit-agent/.env`, then
`sudo systemctl restart famit-*`.

| # | What | Env var(s) | Where / how (founder steps) | Unlocks | Cost |
|---|---|---|---|---|---|
| 0 | **Nothing** (default) — one-time system libs only | – | One-time on the agent box: `apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libfontconfig1` (WeasyPrint's text-shaping libs; present by default on most Linux droplets) | Full local PDF brochures/catalogs via **WeasyPrint** | **₹0 / free** |
| 1 | **Gotenberg render box** (optional) | `BROCHURE_GOTENBERG_URL` | Create a small DO droplet on the private VPC, run the provided `selfhost/docker-compose.gotenberg.yml`, paste its **internal** URL (e.g. `http://10.x.x.x:3000`) | Browser-fidelity visual brochures + DOCX/PPTX→PDF + PDF/A + encryption | DO droplet ≈ **$6–12/mo** (small box; 0.5–1 GB RAM/Chromium) |
| 2 | **Typst binary** (optional) | `BROCHURE_TYPST_BIN` | `apt`/release-install the `typst` binary on the agent box; set its path | Fast data-dense catalogs / price lists at scale | **₹0 / free** |
| 3 | **AI copy** (optional) | *(none new)* — reuses the existing LLM seam / `GROQ_API_KEY` etc. already in `.env` | already configured for voice/marketing | AI-written headlines, blurbs, product descriptions | metered by existing LLM meter |
| 4 | **AI imagery** (optional) | *(none new)* — reuses `droplet_work/automation/image` creds (`IDEOGRAM_API_KEY`, `OPENAI_API_KEY`, `FAL_KEY`, …) | configured in the image module | AI hero/lifestyle images, floor-plan beautification | metered by the image module's budget |
| 5 | **Guardrail toggles** (recommended) | `BROCHURE_REQUIRE_PUBLISH_APPROVAL=1`, optional `BROCHURE_S3_*` for off-box storage | set in `.env` | Manager approval before customer send; off-box asset storage | free |
| 6 | **Indic fonts** (bundled) | – (shipped in `templates/_shared`) | none — Devanagari/Indic fonts ship with the module | Hindi/Indic brochures render correctly | free |

**Recommended minimum:** **nothing** — it works free out of the box. Add **#1 (Gotenberg)** when
the founder wants designer-grade visual brochures / DOCX→PDF, and **#2 (Typst)** when catalogs grow
large. AI copy/imagery (#3/#4) reuse creds already present from voice/marketing/image — **no new
account needed** for those.

---

## 13. REAL-vs-HYPE (honest, no overclaim)

**Real in 2026 (ship it):**
- Genuinely good **multi-page, on-template PDFs** (brochures, catalogs, product sheets, offers,
  decks) from structured vendor data — running headers/footers, page numbers, floor-plan grids,
  amenity blocks, price tables — all **free, offline, deterministic** (WeasyPrint).
- **Browser-fidelity** visual brochures + DOCX/PPTX→PDF + PDF/A + encryption when Gotenberg is up.
- **Fast large catalogs** (hundreds of SKUs) when Typst is present.
- **AI-upgraded copy and imagery** as an *enrichment*, cleanly degradable.
- **Indic/Hindi** brochures (bundled fonts; copy via the LLM seam).

**Hype / still needs a human (the approval gate exists for exactly this):**
- "One click → a finished, legally-cleared, pixel-perfect agency brochure, zero human." No. Final
  sign-off, brand-exact logo lockups/safe-zones, and licensed-font fidelity stay human-reviewed;
  AI output is a **draft/variation**, the real logo/legal line is composited deterministically.
- **RERA / financial / claims compliance** for real-estate is **enforced structurally** (required
  reg-no, forced disclaimer, claim denylist) but still **requires human/legal sign-off before
  publish** — the module blocks/flags, it does not certify.
- **Perfect brand consistency across a campaign** needs brand-kit templates + (optional) a trained
  image LoRA via the image module — not free out-of-the-box.

Positioning: a **data-driven, multi-engine PDF brochure/catalog factory** with optional AI
enrichment, an audit trail, and a human approval-to-publish gate — not a fire-and-forget art
director or a legal-compliance authority.

---

## 14. OFFLINE ACCEPTANCE TEST (`tests/test_brochure_offline.py`) — ZERO external calls

**No keys, no Docker, no network.** Proves the whole pipeline by rendering a **real multi-page PDF**
through the built-in WeasyPrint engine. **Run it on the Linux droplet (or WSL)**, not bare Windows:
WeasyPrint needs the system Pango/HarfBuzz/fontconfig libs (§12 row 0) present to render — trivial
on the droplet, painful on a Windows dev box, so the build agent should run this test on the
droplet/WSL. Page-count and RERA-string assertions use **`pypdf`** (pure-Python) as the only test
dependency for PDF parsing.

```
pytest droplet_work/creative/tests/test_brochure_offline.py -q
# or:  python -m droplet_work.creative.tests.test_brochure_offline
```

**Assertions (each maps to a guarantee above):**
1. **Always-ready core:** with ALL brochure/enrichment env vars unset, `status()["status"]=="ready"`,
   `engines_status()["weasyprint"]=="available"`, gotenberg/typst `"not_configured"`,
   `enrichment` both `"not_configured"`. **Nothing raises.**
2. **Real PDF from data (the headline test):** `build(DocSpec(document_type="brochure_realestate",
   inline_data=fixtures/realestate_project.json, theme="navy"), sync=True)` returns `ok=True`,
   `engine=="weasyprint"`, writes `var/creatives/brochures/<job_id>/navy.pdf`, and the file
   **starts with `%PDF-`**, has **> 1 page** (parse the page count), `est_cost_inr==0.0`,
   `enrichment_used=={"copy":False,"imagery":False}`.
3. **Batch of variants:** `theme="*"`, `n_variants=3` → 3 PDFs written, one per theme, distinct bytes.
4. **Catalog path:** `build(document_type="catalog_grid", inline_data=fixtures/product_catalog.json)`
   renders a multi-SKU PDF via weasyprint (typst path covered by a separate, skipped-if-bin-absent test).
5. **Engine routing (no network):** monkeypatch `gotenberg.available()`/`typst.available()` → assert
   `router.select`: `catalog_grid`→`typst`(if avail), `brochure_realestate`→`gotenberg`(if URL),
   and with both unavailable → **weasyprint** (route_reason records the choice).
6. **RERA compliance block:** a real-estate context with `rera_number` **missing** →
   `status=="compliance_block"`, **no PDF written**, audited `brochure.compliance_block`. With a
   valid rera_number → renders, and the **RERA disclaimer string is present in the PDF text**.
7. **Claim denylist:** a context containing "guaranteed returns" → `compliance.notes` flags it and
   (with publish-approval default) the asset is **not auto-publishable**.
8. **Approval-to-publish gate:** `BROCHURE_REQUIRE_PUBLISH_APPROVAL=1` → `publish(channel="whatsapp")`
   on an unapproved asset returns `status=="pending_approval"`, writes `pending/<job_id>.json`, and
   returns **no asset_url**; after `approve(...)`, `publish` returns `ready_to_attach=True`.
9. **Enrichment degrades, never fails:** with the LLM seam + image module both unconfigured,
   `enrich.apply` returns `copy=False,imagery=False`, uses `_shared/placeholder.png`, and the build
   still succeeds (proves enrichment is optional, not load-bearing).
10. **Meter:** a build with a mocked enrichment cost writes a `usage_events` row `vendor=="image"`/
    `"llm"` with the passthrough cost; a pure render writes `est_cost_inr==0.0`; `estimated` honest.
11. **Async job lifecycle:** `build_async(...)` returns a `queued` JobRecord; after the worker runs,
    `get_job(job_id).status=="stored"` with asset urls; a forced engine error → `status=="failed"`,
    `error` set, partial state readable (crash-safe).
12. **Never-raises fuzz:** malformed specs (unknown document_type, `n_variants=999`, empty data,
    bad page_size, non-dict) → each returns a `BuildResult` with `invalid`/clamped status, **no
    exception**.

All "configured"/"paid"/"gotenberg"/"typst" cases use **monkeypatch/mocks** → the test makes **no
real HTTP call and needs no binary**. The weasyprint render path uses no network at all. Exit
non-zero on any failure (CI-gateable).

---

## 15. BUILD ORDER (for the implementing agent — small verifiable units, no git)

1. `types.py` + `engines/base.py` + `engines/weasyprint_engine.py` + a minimal
   `templates/html/brochure_realestate/` + `__init__.py` skeleton → **test #1, #2 pass** (real PDF).
2. `templates_registry.py` + `context.py` + remaining HTML template packs → **tests #3, #4**.
3. `router.py` + `engines/gotenberg_engine.py` + `engines/typst_engine.py` (dormant) → **test #5**.
4. `guardrails.py` (RERA, claim denylist, approval gate) + `audit_hook.py` → **tests #6, #7, #8**.
5. `enrich.py` (LLM seam + image-module delegation, dormant-safe) + `meter.py` → **tests #9, #10**.
6. `jobs.py` (async lifecycle) + `store.py` finalize + `index.jsonl` → **test #11**.
7. Typst `.typ` packs + `selfhost/` (Gotenberg compose + founder README) — docs/templates only, no deploy.
8. Run the full offline test → green → **STOP** (orchestrator wires endpoints + commits).

Reuse, don't reinvent: copy the no-raise/retry HTTP pattern from `vendors/_http.py` (Gotenberg
call); the meter shape from `vendors/groq_meter.py`; the audit `record()` contract from `audit.py`;
the dormant/degrade pattern from `whatsapp.py`; read secrets via `config.get()` with an `os.getenv`
fallback. Delegate copy to the marketing LLM seam and imagery to `automation/image` — **do not
re-implement either** (but see RED-TEAM FIX R3: those modules do **not exist as code yet** — the
import MUST be defensive/optional, never a hard dependency).

---

## RED-TEAM FIXES (folded)

> Adversarial review, 2026-06-09. Verdict at the end. Each fix below is **binding on the build
> agent** and supersedes any conflicting text above. Findings are ordered by severity. External
> claims were re-verified against primary sources (cited inline); the engine licenses
> (WeasyPrint BSD-3, Gotenberg MIT, Typst Apache-2.0) and the wkhtmltopdf rejection
> (CVE-2022-35583, CVSS 9.8 SSRF, repo archived 2023-01-02) all **check out** — those are kept.

### R1 (CRITICAL — security) — The engines this spec KEEPS have the same SSRF/LFI class it rejects wkhtmltopdf for. Lock the fetcher.
The spec rejects wkhtmltopdf for **CVE-2022-35583** (SSRF: user HTML embeds `<iframe src="http://internal-ip">` and exfiltrates internal assets). But it then renders **vendor-supplied AND AI-generated HTML** through WeasyPrint/Gotenberg with **no `url_fetcher` restriction** — which is the *identical* threat class, and it is documented for the chosen engines, not hypothetical:
- **WeasyPrint CVE-2024-28184** — attacker can "attach the content of arbitrary files and URLs to a generated PDF **even when `url_fetcher` is configured to restrict access**" (affects ≥61.0, fixed **61.2**). I.e. `<img src="file:///opt/famit-agent/.env">`, `<img src="http://169.254.169.254/metadata/v1/...">` (DO droplet metadata), or `@import`/`url()` pointing at the private VPC, all get *baked into the PDF bytes* and shipped to the customer/WhatsApp. This is credential + internal-network exfiltration through a "free, offline" engine.
- **WeasyPrint CVE-2026-49452** (the v69 / 2026-06-02 release) — CSS injection via `--presentational-hints` when rendering untrusted HTML with restricted CSS. The spec's "WeasyPrint 69" line sells this release as a *feature* date and never mentions it is a **security release in this exact threat model**.

**MANDATORY FIX (all three engines):**
1. **Never pass raw vendor/AI HTML to an engine.** Templates are trusted (repo files); the **data context** is untrusted. Bind data through Jinja2 with autoescape **on** and **strip/disallow** any field that can introduce a URL-bearing element. Treat AI-generated copy as data too (autoescaped text only — never raw HTML).
2. **WeasyPrint: pass a hardened `url_fetcher`** that allows ONLY (a) bundled `_shared/` assets and the per-job `assets_dir`, and (b) the vendor's own already-validated uploaded image paths. **Deny by default**: `file://` outside the job dir, ALL `http(s)://` to private/link-local ranges (`10/8`, `127/8`, `169.254/16`, `172.16/12`, `192.168/16`, `::1`, `fd00::/8`, and the DO metadata IP `169.254.169.254`), and any scheme not in {`https`(public), the job's local file allowlist}. Do NOT pass `presentational_hints=True`. Pin **WeasyPrint ≥ 69** in requirements (gets both the 28184 and 49452 fixes) and re-pin on each CVE.
3. **Gotenberg: it runs Chromium and will fetch whatever the HTML references.** Deploy it on the private VPC **with egress firewalled to deny the link-local/metadata range and the rest of the VPC** (the fortress egress-lock pattern already used on `famit-panel-2`), and send assets as multipart parts, not as URLs the container resolves. Without this, Gotenberg is a worse SSRF box than wkhtmltopdf.
4. **Test #13 (NEW, offline):** a fixture whose data context contains `file:///etc/passwd`, `http://169.254.169.254/...`, and `http://10.0.0.5/` in image/link fields → assert **none** of those bytes/resources appear in the output PDF and the fetcher denied them. This is the gate that proves R1 is real, not aspirational.

### R2 (HIGH — correctness) — `pdf_a=True` + `encrypt=True` is a hard 400 on Gotenberg; DocSpec lets you ask for both.
Gotenberg's QPDF path makes **PDF/A and encryption mutually exclusive — requesting both returns 400 Bad Request** (verified, gotenberg.dev / QPDF module). `DocSpec` exposes `pdf_a` and `encrypt` as independent bools with no guard, so a caller can request an impossible combo and get a raw engine 400 instead of a clean `BuildResult`. **FIX:** `types.py` validation rejects `pdf_a and encrypt` up front → `status="invalid"`, `meta.reason="pdf_a_and_encrypt_mutually_exclusive"`. Add to the never-raises fuzz (test #12).

### R3 (HIGH — missing dependency / honesty) — The two modules this spec "reuses" do NOT exist as code. Only design docs do.
`droplet_work/automation/` is an **empty directory**; there is **no `automation/image` package** and **no marketing `content.py`**. What exists is the *sibling design specs* `design/automation-image.md` and `design/automation-marketing.md`, and `llm_router_processor.py` — which is a **Pipecat voice-pipeline frame processor**, not a callable copy-generation seam. So every "reuses the **existing** image module / the **existing** LLM seam / **already** configured" claim (§0.2, §1 rows, §5, §12 rows 3–4, §15) is **aspirational, not factual today**. This does **not** break the module *if* the imports are defensive — which the dormant-until-creds design already implies — but the framing is hype and must be corrected so the build agent doesn't `import` a non-existent package and hard-fail.
**FIX (binding):** `enrich.py` MUST wrap both delegations in `try/except (ImportError, Exception)` and treat **module-absent exactly like creds-absent** → `copy=False`/`imagery=False`, placeholder used, build still succeeds. Add **test #9b:** with `automation.image` and the marketing seam **not importable at all** (not merely unconfigured), `build()` still returns a real PDF. Reword §0/§1/§5/§12 to say "delegates to the image/marketing modules **when present**; both are **planned siblings, optional at runtime**," not "existing/already configured."

### R4 (MEDIUM — guardrail realism) — The approval gate and RERA block are only as strong as `enrich` being barred from legal fields; assert it, and fix the denylist's bypassability.
The §7 controls are sound in intent, but two holes:
- **(a) Enrichment must be structurally barred from legal/financial fields**, not just by convention. `enrich.apply` must operate on a field allowlist (headline, sub-head, amenity *blurbs*, product *descriptions*, CTAs) and be **incapable** of writing `price_from`, `rera_number`, `possession_date`, `floor_plans`, `configurations`, or the disclaimer. Enforce by passing enrichment only a projection of the context and merging back only allowlisted keys. **Test #14 (NEW):** a build where the mocked LLM tries to rewrite `price_from`/`rera_number` → asserts the rendered PDF still shows the vendor's verbatim figures.
- **(b) The claim denylist is trivially bypassable** (substring match on "guaranteed returns" misses "guaranteed‐returns", "g​uaranteed", Hindi/Tamil equivalents, "assured ROI"). Keep it as a **flag-and-route-to-human** signal (which it is) — but the spec must NOT imply it *prevents* non-compliant claims. It raises a review flag; the **human approval gate is the real control**. Make that explicit so no one treats the denylist as compliance certification. (The spec's §13 honesty section already says "blocks/flags, does not certify" — good; propagate that caveat to §7.3.)

### R5 (MEDIUM — async/crash-safety realism) — "In-process ThreadPool" loses queued jobs on restart; reconcile on boot.
§6 persists each transition (good), but an in-process ThreadPool means: a process restart abandons every `queued`/`rendering` job with no worker to resume them, and the spec calls them "crash-safe" because the *file* is readable. Readable ≠ resumed. **FIX:** on module import/boot, `jobs.py` runs a **reconcile pass** — any job left `queued`/`rendering`/`enriching` with no live worker is either re-enqueued (idempotent re-render is safe, the spec says so) or flipped to `failed:interrupted` with a clear error, so the UI never polls a zombie forever. Add **test #11b:** a job persisted as `rendering` with no worker, after `reconcile()`, becomes `queued` (re-enqueued) or `failed:interrupted` — never stuck. Also bound the worker pool and the per-render subprocess (Typst) and HTTP (Gotenberg) timeouts explicitly so one giant catalog can't wedge the pool.

### R6 (LOW — cost/ops honesty) — "Mostly ₹0" hides the real bills; one-time libs aren't always one `apt`; PDFs accumulate.
- **Render is ₹0 only for WeasyPrint/Typst.** Gotenberg is a **standing $6–12/mo droplet** (correctly noted in §12) **plus** RAM headroom — and it is the engine the spec *routes visual brochures to by default when the URL is set*, so for a founder who stands it up, the "mostly free" headline is optimistic. Keep the WeasyPrint floor as the honest default and say Gotenberg is a *recurring* cost, not a one-time one.
- **AI enrichment is metered passthrough — real money.** Imagery via the image module is the dominant cost driver of a "batch of N themed brochures with AI heroes." The spec correctly doesn't double-cap, but it must state plainly: **a batch of N variants × AI hero each = N image-generations billed.** Surface the *projected* batch cost to the UI **before** the user clicks Generate Batch (the image module's per-image estimate × N), so autonomous/bulk batches can't silently run up the image budget. (This is the closest thing here to the brief's "autonomous ad-spend safety" concern — there is **no autonomous bidding or ad spend in THIS module**; it only emits an `ad_asset` handoff. Autonomous-spend safety lives in the ads module, correctly out of scope here. Do not claim this module gates ad spend.)
- **Storage grows unbounded.** `var/creatives/brochures/<job_id>/` with N PDFs per batch fills the droplet disk over time. Add a retention/cleanup note (TTL or count cap on stored batches; the dormant S3 sink helps but isn't the answer to local growth).
- **§12 row 0 is too breezy:** "present by default on most Linux droplets" is not reliably true on minimal/slim base images or containers — Pango/HarfBuzz/fontconfig frequently must be installed, and the **Indic (Devanagari/Tamil) shaping** further needs the bundled fonts to actually be on the fontconfig path. Keep the `apt` line as a **required setup step**, not an "it's probably already there" aside, or the headline test fails on a clean box with blank/`□□□` glyphs.

### R7 (LOW — ToS) — Self-hosted engines are ToS-clean; the ToS surface is entirely in the delegated AI + the OUTPUT, and is unaddressed.
WeasyPrint/Gotenberg/Typst are permissively licensed and self-hosted → **no third-party ToS risk** from the engines themselves (verified). The real ToS/legal surface is: (a) **AI providers' usage policies** for the copy/imagery — owned by the image/LLM modules' own safety, fine; the §7.4 prefilter is a thin first line and the spec says so; (b) **fonts** — the bundled Indic/brand fonts MUST be license-cleared for embedding-in-PDF and redistribution (many "free" fonts are not OFL/embed-permitted); add a one-line check that `_shared/` fonts are OFL/Apache/embeddable. (c) **Customer-facing legal output** (RERA) is human-gated — correct. **FIX:** add a font-license assertion to the build-order checklist (engines clean; fonts are the actual redistribution-ToS risk).

### Verdict: **GO** — design is sound and honestly framed on most axes; ship it with R1 + R2 + R3 folded in as blocking, R4–R7 as required-but-not-blocking.
The core architecture (always-on free WeasyPrint floor, dormant-until-creds enrichment that degrades-not-fails, real async jobs, audit + approval-at-publish, structural RERA enforcement, offline keyless acceptance test) is correct, well-evidenced, and genuinely non-breaking (NEW files only under `creative/`, no `caller.py`/`agent.py` edits, no git). The honesty section (§13) is largely accurate and does **not** overclaim 3D or autonomous bidding (both correctly out of scope — 3D is a sibling sub-page, bidding lives in the ads module).

**Residual risks after fixes:**
1. **SSRF/LFI (R1) is the one that can actually hurt a customer/the infra** — it is only closed if the build agent implements the hardened `url_fetcher` + Gotenberg egress-lock AND the new test #13 passes. If the agent skips it as "non-blocking polish," the module ships an exfiltration hole. Treat R1 as a release gate, not advice.
2. **Dependency-on-vapor (R3):** the module is correct in isolation but cannot deliver *any* AI enrichment until the image/marketing modules actually exist; until then it is a (very capable) raw-data PDF factory only. Set founder expectations accordingly.
3. **WeasyPrint CVE cadence:** this engine has had file/URL-exfil and CSS-injection CVEs in 2024 and 2026; it requires **active version pinning + monitoring**, not set-and-forget. Bake a "re-pin on advisory" note into ops.
4. **Untested fidelity claims:** "designer-grade" Gotenberg output and "fast at hundreds of SKUs" Typst are vendor/benchmark claims, not validated on *this* module's templates — true risk is low but unproven until real template packs exist.
5. **Indic rendering** is asserted but only proven by the offline test if the bundled fonts + system shaping libs are actually present on the CI/droplet box (R6 last bullet) — a clean-box run is the only proof.

**Sources (re-verified):** WeasyPrint v69 / 2026-06-02 + CVE-2026-49452 (doc.courtbouillon.org changelog; Kozea/WeasyPrint releases); WeasyPrint CVE-2024-28184 file/URL exfil, fixed 61.2 (vulert / NVD); Gotenberg MIT + QPDF AES-256 + PDF/A and the **PDF/A⊕encryption 400** (gotenberg.dev; pkg.go.dev qpdf module); Typst Apache-2.0 embeddable (typst.app/open-source, github.com/typst/typst); wkhtmltopdf CVE-2022-35583 CVSS 9.8 SSRF + repo archived 2023-01-02 (NVD; GitHub advisory GHSA-v2fj-q75c-65mr). Repo facts (`automation/` empty, `llm_router_processor.py` is a Pipecat processor, `whatsapp.py` never-raise pattern) verified against the working tree at `C:\Users\kunal\Desktop\caps\droplet_work\`.
