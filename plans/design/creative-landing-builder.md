# DESIGN SPEC — Landing Page Builder (`droplet_work/creative/landing/`)

> **Status:** EXECUTION-READY. A build agent implements this verbatim, ONE UNIT at a time,
> running the offline acceptance test before the next. **NON-BREAKING + crash-safe.**
> **NO git** (the orchestrator commits). **NEW files ONLY under `droplet_work/creative/`.**
> **DO NOT edit `caller.py` / `agent.py`** (backend spine; final wiring deferred to a later phase).
> Every integration is **PROVIDER-AGNOSTIC** + **DORMANT-UNTIL-CREDS**: a no-op that returns
> `{"status": "not_configured"}` and **NEVER raises** until the founder pastes keys — exactly
> like the existing `droplet_work/whatsapp.py` (the canonical pattern this spec mirrors).
> **Verifiable OFFLINE** — the acceptance test makes **zero** live external calls and needs **no Node**.

Date: 2026-06-09. Research sources are inline and listed in §12.

---

## 0. TL;DR — the decisions that define this module (read before coding)

1. **This is `schema → render → publish`, NOT a drag-and-drop site builder.** The canonical artifact
   is a **Python-defined page schema** (a small fixed set of sections: hero, benefits, testimonials,
   FAQ, lead-form, CTA, tracking) and a **pure-Python renderer** that emits a static, fast HTML file.
   "Build me a landing page for Product X" = generate that schema from the tenant's stored
   business/product/campaign data, render it, preview it, and (behind approval) publish it.

2. **The JS visual editor (Puck / GrapesJS) is the Creative-Studio SUB-PAGE editing surface — NOT a
   runtime dependency of generate/render/publish.** Generation, rendering and publishing are **pure
   Python** so the offline test needs zero Node and zero network. The browser editor loads the SAME
   JSON schema for human tweaks and posts it back; if the founder never touches the editor, the
   Python path still produces a complete page. **This render boundary is the architectural keystone
   — violating it (e.g. making a Node render service mandatory) breaks the offline guarantee.**

3. **`generate()` produces a real, complete page with ZERO LLM creds.** Default = deterministic fill
   of the canonical template from stored product/campaign data (offline, no key). An LLM is an
   **optional copy enhancer** behind the **existing** seam `LP_COPY_LLM ∈ {none(default), groq, sarvam}`
   — **no new LLM vendor** (consistent with `automation-marketing.md` §1.5 / `automation-image.md`:
   "Anthropic/Claude NOT used here"; it slots in later as another value if ever wanted).

4. **Default publish target = `local` (zero creds).** `LP_PUBLISH_PROVIDER ∈ {local, do_spaces,
   cloudflare, netlify, s3, generic}`. `local` serves the page at `/l/<slug>` (or writes the static
   file under `var/landing/published/`) and works dormant with **no account** — so the module is
   useful and testable before any cred. **Publish is the irreversible public action** → it sits
   behind the **approval gate + audit**, with an **unpublish/takedown** path.

5. **Revenue-connected via thin BRIDGES, never by importing the spine.** The lead-form POST writes a
   `{phone,email,name,...}` contact to an **append-only leads hand-off JSONL** (exactly like
   marketing's `voice_bridge`/`wa_bridge`; **no `import caller.py`**), and can `enroll()` that contact
   into the existing marketing **sequencer** for WhatsApp + voice follow-up. Tracking pixels
   (Meta/GA4) are dormant until the tenant pastes IDs. **Lead submit is the conversion signal** that
   feeds analytics and the ads optimizer (`automation-ads.md`). One flow satisfies the whole
   "ads → leads → CRM → voice → WhatsApp → analytics" loop.

6. **Embedded media (hero image, product video, 3D) is the ONLY async part — and it reuses the
   existing modules.** The hero/section images come from `automation/image` (its own job-id/results
   pattern, `automation-image.md`); video/3D from `automation/video` + `automation/threed`. This
   module **references** those job ids and renders a placeholder until the async result returns; it
   **does not** re-implement media generation or its own job queue.

---

## 0.1 The non-negotiable house contract (verified against `whatsapp.py`, `audit.py`, `config.py`, `vendors/groq_meter.py`)

Every public function obeys ALL of:
1. **Never raises.** Wrap all I/O in `try/except Exception` → return a result dict (`whatsapp.py:196`,
   `audit.py` both swallow with `# noqa: BLE001`).
2. **Dormant-until-creds.** If the chosen provider's env vars are blank → return
   `{"ok": False, "status": "not_configured", "provider": <p>, ...}` with **zero network I/O**
   (`whatsapp.py:254`). *(Note: `generate`/`render` work WITHOUT any cred — only `publish` to a
   remote provider and tracking-pixel firing depend on creds.)*
3. **Provider-agnostic.** A `provider` switch builds the request per vendor; unknown/blank → a
   `generic` flat-JSON path (`whatsapp.py:_build_body`). Applies to publish + tracking.
4. **Config via `os.getenv` read fresh inside the function** (a later `.env` paste + restart takes
   effect with no code change). `config.get()` Doppler passthrough is automatic; fall back to
   `os.getenv` if `config` isn't importable in this package.
5. **3rd-party imports optional.** `try: import httpx except: httpx=None` → `error:httpx_unavailable`
   (`whatsapp.py:73`). **Jinja2 same:** `try: import jinja2 except: jinja2=None` → fall back to the
   built-in stdlib `string.Template` renderer (so the offline test needs nothing installed).
6. **Async + sync variants** where the FastAPI loop will call it (mirror `send_whatsapp` /
   `send_whatsapp_async`). Publishing + tracking fire-and-forget get async twins.
7. **Audit every mutating action** best-effort via `audit.record(...)` channel `"landing"`, never
   letting an audit failure break the action.

---

## 1. CHOSEN TOOLS + WHY (researched 2026-06; all ACTIVE, none abandoned)

### 1.1 Page schema + renderer — **build in-process Python; do NOT take a JS render runtime as a dep**
The page is a **small, fixed-vocabulary block document** (≈8 section types), not an arbitrary website.
That is ~150 lines of dataclasses + a template-per-section renderer, deterministic and offline-testable,
tightly coupled to existing per-tenant state (product data, leads, audit). A general web/page builder
runtime as the *generation/render spine* is the wrong altitude and would drag Node into the offline
test. So **the schema + renderer live in this package** (`schema.py` + `render.py`). This mirrors the
in-process decision already made for the marketing sequencer (`automation-marketing.md` §1.1).

### 1.2 Visual editor (the Creative-Studio sub-page surface) — **Puck (preferred) / GrapesJS (alt)**
For human tweaks, the Creative-Studio "Landing Pages" sub-page embeds a visual editor that loads and
saves the **same JSON schema**. Researched 2026, both ACTIVE, both permissive, both JSON-native:
- **Puck** — **MIT**, **v0.21.3 (2026-06-08)**, 12.8k★. "Modular open-source visual editor for React";
  `initialData` in / `onPublish(data)` out are **plain JSON objects** that map 1:1 to our schema. **Pick
  Puck if the Famit panel frontend is React/Next** (it embeds INTO the existing app — no separate CMS
  service to run). ([Puck GitHub], verified license+version+JSON model via fetch.)
- **GrapesJS** — **BSD-3-Clause** (core), **v0.22.16 (2026)**, framework-agnostic (vanilla JS),
  TypeScript-rewritten, regular commits. **Pick GrapesJS only if the panel is NOT React** or you want
  zero framework coupling. ([GrapesJS GitHub] / [GrapesJS LICENSE].)
- **Decision rule:** confirm the panel's stack before choosing; **default Puck** (its data model is
  the closest to our schema). **Either way the editor is FRONTEND-ONLY** — it never runs server-side,
  is never a Python dependency, and is out of scope for the offline test. The backend only stores and
  re-renders the JSON it returns. (`aipage.dev` (MIT) noted as an AI-page reference; not adopted —
  we own the schema.)

### 1.3 Copy generation — **reuse the existing LLM seam; no new vendor**
Headlines, subheads, benefit bullets, FAQ Q&A, CTA text, WhatsApp/call CTA labels. Default path is a
**deterministic template fill** from stored campaign data (offline, no key). Optional LLM rewrite under
length caps behind `LP_COPY_LLM ∈ {none(default), groq, sarvam}` reuses the **existing**
`GROQ_API_KEY`/`SARVAM_API_KEY` the spine already meters — **no new account** (consistent across the
design docs). On any LLM error → fall back to the deterministic copy. **`generate()` NEVER depends on
an LLM key.**

### 1.4 Hosting / publish — **`local` default; DO Spaces / Cloudflare Pages / Netlify / S3 / generic**
A landing page is **static HTML/CSS/JS** → host cheaply as static assets. Adapter
`LP_PUBLISH_PROVIDER`:
- **`local`** (default, **zero creds**): write the rendered file to `var/landing/published/<slug>.html`;
  the spine later serves it at `GET /l/<slug>`. Works fully dormant — the module is useful day one.
- **`do_spaces`** (recommended cheap CDN-fronted at scale): DO Spaces (S3-compatible) + the existing
  Cloudflare front already in the infra. Keys: `DO_SPACES_KEY/SECRET/BUCKET/REGION/ENDPOINT`.
- **`cloudflare`** (Cloudflare Pages direct API), **`netlify`** (Netlify deploy API), **`s3`**
  (AWS S3 + CloudFront), **`generic`** (flat PUT to any object store / static host).
- All remote providers are **dormant until their creds exist**; `local` always works. Custom domains
  are a per-tenant DNS chore (CNAME), called out in the cred list — not automated here.

### 1.5 Embedded media — **call the existing automation modules; do NOT re-implement**
- **Images** (hero, og:image, section art) → `creative` calls `automation.image.generate(...)`
  (`automation-image.md`) which owns the job lifecycle. We store the returned image path/url in the
  schema; if a job is still running we render a placeholder and patch on completion (§6 async pattern).
- **Video** (hero/product loop) → `automation.video`; **3D** → `automation.threed`. Same reference
  pattern. **No new media vendor or queue here.**

---

## 2. PACKAGE LAYOUT (new files only; everything under `droplet_work/creative/`)

> **FOLDER NOTE (flagged for the orchestrator):** the brief pins NEW creative modules under
> `droplet_work/creative/`. The sibling automation specs (marketing/image/aimanager) live under
> `droplet_work/automation/`. **This module follows the explicit instruction → `creative/`.** It
> imports siblings (`automation.image`, marketing `sequencer`) by **bare top-level name** with
> cwd = `droplet_work/` (see §2.1), so the `creative/` ↔ `automation/` boundary works as long as both
> are top-level packages on the path — confirm/keep this convention when wiring.

```
droplet_work/creative/
  __init__.py                  # exports public surface; imports cleanly with empty env
  landing/
    __init__.py                # public API: generate(), render(), preview(), publish(), unpublish(),
                               #             submit_lead(), status() (+ async twins)
    schema.py                  # PageSchema + Section dataclasses (hero/benefits/testimonials/faq/
                               #   lead_form/cta/tracking/media) + normalize/validate/to_dict/from_dict
    generate.py                # build PageSchema from tenant product/campaign data (deterministic) +
                               #   optional LLM copy enhance (LP_COPY_LLM) — NEVER needs a key
    render.py                  # PageSchema -> static HTML (Jinja2 if importable, else string.Template).
                               #   Inlines minimal CSS; injects lead-form POST + tracking pixels.
    templates/                 # section + page templates (also valid under the stdlib fallback)
      page.html  hero.html  benefits.html  testimonials.html  faq.html
      lead_form.html  cta.html  tracking.html
    publish/
      __init__.py              # registry: provider id -> adapter; resolve()
      base.py                  # Publisher protocol: status(), put(slug, html, assets), delete(slug)
      local.py                 # writes var/landing/published/<slug>.html (default, zero creds)
      do_spaces.py  cloudflare.py  netlify.py  s3.py  generic.py   # dormant until creds
    product_source.py          # GUARDED read of stored product/campaign/brand by (product_ref,
                               #   tenant_id) from the spine campaign store; stubbable offline.
    leads.py                   # submit_lead(): validate -> anti-abuse -> append leads hand-off JSONL
                               #   -> optional marketing.sequencer.enroll() -> audit. NO caller import.
    tracking.py                # build pixel/script snippets (Meta Pixel, GA4) — dormant until IDs;
                               #   server-side conversion ping optional + dormant
    media.py                   # thin bridge: request hero/section media from automation.image|video|
                               #   threed; poll/patch when an async job completes (NO new queue)
    guardrails.py              # publish approval gate, per-tenant page cap, lead-form rate/anti-abuse,
                               #   PII note, kill switch; spend defers to image/video module budgets
    meter.py                   # cost rollup: page=₹0 (compute only); media cost is owned+metered by the
                               #   image/video modules — we only reference their job ids
    store.py                   # JSONL/JSON helpers (atomic write, append) scoped to var/landing/
    editor_bridge.py           # to_editor(schema)->json / from_editor(json)->schema for the ONE chosen
                               #   editor (Puck component-tree JSON, OR GrapesJS html/css model — they
                               #   differ; pick one per §1.2, not both). Pure data mapping, NO server JS.
    endpoints.py               # OPTIONAL FastAPI APIRouter (NOT mounted by caller.py here)
    config_help.py             # cred checklist + per-provider status (for /landing/status)
  tests/
    __init__.py
    test_landing_offline.py    # the offline acceptance test (no network, no Node); also __main__-runnable
  __init__.py is required at creative/ AND creative/tests/ (so `python -m creative.tests...` resolves)
```

### 2.1 Packaging & imports (PINNED — verified against `caller.py`)
The spine runs **flat with `droplet_work/` as the sys.path root**: `caller.py` does `import whatsapp`,
`import audit`, `from config import get`, `from vendors import groq_meter` (no `droplet_work.` prefix).
This module follows the identical convention:
- Reach spine deps by **bare name**: `import audit`, `from config import get`, `from whatsapp import
  send_whatsapp` (only if ever needed — prefer the bridge). Do **not** prefix with `droplet_work.`.
- Reach sibling packages by **bare top-level name**: `from automation.image import generate as
  image_generate`, `from automation.marketing.sequencer import enroll`. Internally prefer relative
  imports (`from .publish import local`, `from . import guardrails`) so the package is self-consistent.
- **Optional sibling imports are guarded:** `try: from automation.image import generate ... except
  Exception: image_generate = None` — so `creative` imports cleanly even if `automation` is absent in a
  bare test env (the offline test does not require the image module to be present).
- **Test invocation:** cwd = `droplet_work/`, `python -m creative.tests.test_landing_offline` (NOT
  `python -m droplet_work.creative.…` — that breaks the bare `import audit`). The test self-inserts
  `droplet_work/` on `sys.path` so it runs from any cwd.

**Import safety:** every submodule imports cleanly with an empty env; no module-level network calls, no
Node, no `require()` at import.

---

## 3. INTERFACES (exact signatures — a build agent codes to these)

All return a **result dict** of shape:
`{"ok": bool, "status": str, "provider": str, **extra}`.
`status` vocabulary: `ok | not_configured | invalid | blocked_needs_approval | blocked_paused |
blocked_rate | blocked_suppressed | published:<url> | unpublished | queued:<id> | dry_run | error:<...>`.

### 3.1 landing/__init__.py — public surface
```python
def generate(brief: "dict | PageBrief", *, tenant_id: str = "") -> dict:
    """Build a complete PageSchema from stored product/campaign data + the brief.
       Deterministic; NEVER needs an LLM/publish key. Optional copy enhance via LP_COPY_LLM.
       Returns {"ok":True,"status":"ok","schema":{...},"slug":"...","page_id":"..."}.
       Persists the schema to var/landing/pages/<page_id>.json (draft)."""

def render(page_id_or_schema, *, inline_css: bool = True) -> dict:
    """PageSchema -> static HTML string. Pure Python (Jinja2 or stdlib fallback). No network.
       Returns {"ok":True,"status":"ok","html":"<!doctype...","slug":"..."}."""

def preview(page_id: str, *, tenant_id: str = "") -> dict:
    """Render + write to var/landing/preview/<slug>.html for an unauthenticated-but-unlisted
       preview at /l/preview/<slug>. NOT public/indexed. No approval needed (no live publish)."""

def publish(page_id: str, *, tenant_id: str, approved_by: str = "",
            dry_run: bool | None = None) -> dict:
    """Render -> guardrails (approval gate + kill switch) -> publish via LP_PUBLISH_PROVIDER ->
       audit. The IRREVERSIBLE public action. Returns {"status":"published:<url>"} or a block
       status. dry_run/local make it safe to exercise offline."""

def unpublish(page_id: str, *, tenant_id: str, actor: str = "") -> dict:
    """Takedown: delete from the publish target + mark schema unpublished + audit. Never raises."""

def submit_lead(slug: str, form: dict, *, tenant_id: str = "",
                source_meta: dict | None = None) -> dict:
    """Public lead-form handler (see leads.py). Anti-abuse + suppression + append hand-off JSONL +
       optional sequencer enroll + audit. Returns {"ok":True,"status":"ok","lead_id":"..."}."""

def status() -> dict:
    """{"status":"ready", "publish_provider":..., "publish_configured":bool, "copy_llm":...,
        "tracking":{"meta":bool,"ga4":bool}, "guardrails":{...}}  — NO secret values."""

# async twins where the FastAPI loop calls them:
async def publish_async(...) -> dict: ...
async def submit_lead_async(...) -> dict: ...
```

### 3.2 schema.py — the page document (the heart of the module)
```python
@dataclass
class Section:
    type: str          # hero|benefits|testimonials|faq|lead_form|cta|media|tracking|raw_html
    data: dict         # type-specific payload (see below)
    id: str = ""       # stable id (for editor round-trip)

@dataclass
class PageSchema:
    page_id: str
    tenant_id: str
    slug: str                       # url-safe; see SLUG-SCOPE rule below (tenant-scoped public path)
    title: str                      # <title> + og:title
    meta_description: str
    product_ref: str = ""           # which stored product/campaign this was generated from
    lang: str = "en"                # en|hi|... (drives copy + RTL/script handling)
    theme: dict | None = None       # {primary, accent, font, logo_url} from tenant brand
    sections: list = field(default_factory=list)   # ordered Section list
    status: str = "draft"           # draft|preview|published|unpublished
    published_url: str = ""
    created_ts: str = ""; updated_ts: str = ""
    # validate(): non-empty slug/title, allowed section types, exactly one lead_form (or a CTA that
    #   deep-links to WhatsApp/call), size caps; to_dict()/from_dict() are loss-less JSON round-trips.
```
> **🔴 SLUG-SCOPE RULE (cross-tenant collision = data leak).** A bare global `/l/<slug>` lets two
> tenants both pick `summer-sale` and overwrite/serve each other's page (integrity + cross-tenant PII
> leak). Therefore the **public path and stored filename are tenant-scoped**: URL = `/l/<tenant>/<slug>`
> and `local` writes `published/<tenant>/<slug>.html`. Uniqueness is enforced on `(tenant_id, slug)`;
> on collision within a tenant, `generate` auto-suffixes (`summer-sale-2`). The form action becomes
> `/l/<tenant>/<slug>/lead` accordingly. `<tenant>` is the opaque tenant id (or a per-tenant published
> subdomain when `LP_DOMAIN_BASE` is set), never PII.

Canonical section `data` shapes (fixed vocabulary — the LLM/editor fills these, never invents types):
- `hero`: `{headline, subhead, media:{kind:image|video|none, ref|url|job_id}, primary_cta, secondary_cta}`
- `benefits`: `{heading, items:[{icon, title, body}]}`
- `testimonials`: `{heading, items:[{quote, author, role, avatar_url}]}`
- `faq`: `{heading, items:[{q, a}]}`
- `lead_form`: `{heading, fields:[{name,label,type,required}], submit_label, success_msg,
   enroll_sequence_id, wa_cta:bool, call_cta:bool}`
- `cta`: `{heading, body, button_label, wa_number, call_number, utm:{...}}`
- `media`: `{kind:image|video|threed, ref|url|job_id, caption}`
- `tracking`: `{meta_pixel_id, ga4_id, conversion_event}` (rendered only when IDs present)

### 3.2.1 product_source.py — the INPUT seam (where stored product/campaign/brand data is read)
```python
def load(product_ref: str, *, tenant_id: str) -> dict:
    """Return {"product":{...}, "campaign":{...}|None, "brand":{logo_url,palette,font,...}} for the
       tenant's selected dropdown item. Reads the spine's campaign store (campaign.py / db) by
       (product_ref, tenant_id). GUARDED + stubbable exactly like the LLM/media seams:
         try: from campaign import get_product_campaign as _src   # bare-name, spine
         except Exception: _src = None
       If _src is None or lookup fails -> return {} (and generate() falls back to brief-only fill).
       NEVER raises. Offline test injects a stub _src returning a fixed product dict."""
def configured() -> bool: ...   # True when the spine campaign source is importable
```
> This is the **dropdown→generate input**. `generate()` calls `product_source.load(product_ref,
> tenant_id)` first; with no spine source it degrades to building from the `brief` alone (so the
> module is still useful/testable headless). Final binding to the real campaign store is a wiring
> detail for the deferred spine phase — the seam is fixed here so a build agent knows the read path.

### 3.3 generate.py
```python
def build(brief: dict, product: dict, campaign: dict | None, *, tenant_id: str) -> PageSchema:
    """Deterministic: pick a section blueprint by goal (lead-gen default), fill copy from product/
       campaign fields, set theme from tenant brand, request hero media via media.py (async-safe),
       wire the lead-form to enroll into the campaign's follow-up sequence. NO key required."""
def enhance_copy(schema: PageSchema) -> PageSchema:
    """If LP_COPY_LLM in {groq,sarvam}: rewrite headline/subhead/benefit bodies/FAQ under length caps
       (headline<=70, subhead<=160). NEVER raises; on any LLM error returns schema unchanged.
       With LP_COPY_LLM unset/'none' -> pure pass-through (offline)."""
```
Env: `LP_COPY_LLM ∈ {none(default), groq, sarvam}` (reuses existing vendor keys; no new account).

### 3.4 render.py
```python
def render_html(schema: PageSchema, *, inline_css: bool = True) -> str:
    """Pure-Python static HTML. Jinja2 if importable else string.Template (offline-safe). Emits:
       semantic, mobile-first, accessible HTML; minimal inlined CSS; the lead-form as a real <form>
       POSTing to {LP_FORM_ACTION or /l/<slug>/lead}; WhatsApp (wa.me) + tel: CTAs; tracking snippets
       only when IDs present; og:/twitter: meta. NO external JS framework, NO network at render time."""
```
Env: `LP_FORM_ACTION` (default `/l/{slug}/lead`), `LP_ASSET_BASE` (CDN/base url for media),
`LP_API_ORIGIN` (absolute Famit API origin, e.g. `https://panel.famit.in`), all optional.

> **🔴 ABSOLUTE-ORIGIN RULE (load-bearing — a relative action breaks leads on remote hosts).** A
> static host (DO Spaces / S3 / Netlify / Cloudflare Pages) **cannot process a POST**, so a *relative*
> `/l/<slug>/lead` would post to the CDN origin and the lead would be **lost**. Therefore: when
> `LP_PUBLISH_PROVIDER != local`, `render_html` MUST emit an **absolute** form action, tracking-pixel
> endpoint, and asset base rooted at `LP_API_ORIGIN` (the Famit panel API). If `LP_PUBLISH_PROVIDER`
> is remote and `LP_API_ORIGIN` is unset → `publish` returns `error:missing_api_origin` (refuse to
> ship a page whose form is dead). Relative `/l/<slug>/lead` is valid **only** for `local` (same
> origin). The lead form must also POST cross-origin-safely (the spine's `/l/<slug>/lead` route sets
> permissive CORS for published origins). **§11 test #6b** asserts a remote-provider render produces an
> absolute action and that a remote publish with no `LP_API_ORIGIN` is refused.

### 3.5 publish/ — adapter seam
```python
# publish/base.py
class Publisher(Protocol):
    id: str
    def status(self) -> str: ...                          # configured|not_configured|error
    def put(self, slug: str, html: str, assets: list | None = None) -> dict: ...   # -> {url} ; never raises
    def delete(self, slug: str) -> dict: ...              # takedown ; never raises
```
- `local` (default): `put` writes `var/landing/published/<slug>.html`; url = `/l/<slug>`; always configured.
- Remote adapters dormant until creds (env per §6). `generic` = flat PUT to `LP_PUBLISH_API_URL`.

### 3.6 leads.py — the revenue bridge (mirrors marketing `voice_bridge`/`wa_bridge`)
```python
def submit_lead(slug: str, form: dict, *, tenant_id: str = "",
                source_meta: dict | None = None) -> dict:
    """1. validate + normalize {name,phone,email,...}; 2. anti-abuse (honeypot, per-IP/min rate,
       email/phone sanity); 3. suppression check (shared opt-out store); 4. append a contact row to
       var/landing/leads.jsonl  (the spine drains this into CRM later — NO caller.py import);
       5. if the page's lead_form has enroll_sequence_id AND the marketing pkg is importable:
          marketing.sequencer.enroll(seq_id, contact, tenant_id=...)  (-> WhatsApp/voice follow-up);
       6. audit.record(action='landing.lead', channel='landing'); return {lead_id}.
       NEVER raises. The lead row IS the conversion signal analytics/ads read."""
```
Lead row shape (matches the marketing/voice contact contract — `{phone,email,name,...}`):
`{"lead_id","tenant_id","slug","page_id","contact":{"name","phone","email","extra":{...}},
  "utm":{...},"ts","status":"new","enrolled_seq":"<id or ''>"}`.

### 3.7 tracking.py
```python
def head_snippet(schema) -> str:   # GA4 + Meta Pixel <script>/<noscript>, only if IDs present
def conversion_ping(event: str, lead: dict, *, tenant_id: str) -> dict:  # server-side CAPI, dormant
```
Env: `LP_META_PIXEL_ID`, `LP_GA4_ID` (or per-tenant via `__<TENANT>` suffix, like marketing RTF-1);
`LP_META_CAPI_TOKEN` for server-side conversions (dormant until set). No ID → no snippet, no ping.

### 3.8 guardrails.py
```python
def can_publish(tenant_id: str, *, approved_by: str = "", dry_run: bool | None = None) -> dict:
    """Order: kill switch LP_PAUSE_ALL -> blocked_paused; dry-run (LP_DRY_RUN) -> dry_run;
       approval gate LP_REQUIRE_APPROVAL=1 & not approved -> blocked_needs_approval;
       per-tenant published-page cap LP_MAX_PAGES -> blocked_rate; else allow."""
def lead_allowed(slug, ip, contact_key, *, tenant_id) -> dict:
    """suppression + per-IP/min rate + honeypot -> blocked_* or allow (anti-abuse for the PUBLIC form)."""
def approve(page_id: str, *, tenant_id: str, actor: str) -> dict: ...   # flips a pending publish live
```
Env (safe defaults): `LP_REQUIRE_APPROVAL` (default `1`), `LP_DRY_RUN` (default `0` — render/preview
are free & non-spending; publish-to-`local` is reversible, so dry-run defaults OFF but is available),
`LP_PAUSE_ALL` (kill switch, default `0`), `LP_MAX_PAGES` (default `50`/tenant),
`LP_LEAD_RATE_PER_MIN` (default `20`/IP).

> **Spend note:** rendering/publishing a page costs **₹0** (compute + static hosting). The only money
> is **embedded media generation**, which is gated + metered by the **image/video/3D modules' own
> budgets** (`automation-image.md` §5). This module does **not** duplicate a spend cap for media — it
> calls those modules, which refuse over-budget. Publish guardrails here are about **public exposure +
> PII + approval**, not ad/media spend.

### 3.9 meter.py
`page_cost = 0.0` (compute only, `estimated:False`). `summarize()` reports page counts + references the
media job ids whose cost lives in the image/video meters. Keeps billing single-sourced (no double count).

### 3.10 endpoints.py (DEFINED here, MOUNTED later by the spine — NOT in this phase)
`router = APIRouter(prefix="/landing")` (guarded: `try: from fastapi import APIRouter except Exception:
router = None`). Routes:
`POST /landing/generate`, `POST /landing/render`, `GET /landing/preview/{page_id}`,
`POST /landing/publish`, `POST /landing/unpublish`, `POST /landing/approve`,
`GET /landing/status`, `GET /landing/{page_id}` (schema), `GET /landing` (list, tenant-scoped),
`POST /l/{slug}/lead` (PUBLIC lead-form sink → `submit_lead`), `GET /l/{slug}` (serve published HTML),
`GET /landing/audit` (`audit.tail(action_prefix="landing")`).
**Must import without FastAPI side effects and must NOT be imported by `caller.py` this phase.**

---

## 4. DATA MODEL (files under `var/landing/`)

| File | Shape (one JSON / JSONL row) | Role |
|---|---|---|
| `pages/<page_id>.json` | full `PageSchema` (draft/preview/published) | the page document, editor round-trips this |
| `published/<slug>.html` | rendered static HTML | what `local` publish serves at `/l/<slug>` |
| `preview/<slug>.html` | rendered HTML (unlisted) | preview surface, not indexed |
| `index.jsonl` | `{page_id, tenant_id, slug, status, published_url, ts}` | append-only list (newest-first, tenant-scoped) |
| `leads.jsonl` | the lead row of §3.6 | **CRM hand-off** the spine drains; conversion signal |
| `approvals.json` | `{page_id:{tenant_id, approved_by, ts}}` | approval-gate ledger |

`page_id`/`lead_id` = time-sortable IST ids (`YYYYMMDD-HHMMSS-<rand>`). Dirs created lazily; storage
failures are swallowed and downgrade `status` to `error:storage` (best-effort, like `audit.py`).
Append-only logs mirror `audit.py`'s immutability discipline.

---

## 5. CONTROL FLOW — one page, end to end (the whole product in one paragraph)

Vendor picks a product from the dropdown → `generate(brief, tenant_id)` loads that product/campaign +
tenant brand → `generate.build()` fills the canonical schema deterministically (and, if
`LP_COPY_LLM≠none`, `enhance_copy` rewrites copy under length caps, falling back to deterministic on
error) → `media.request_hero()` asks `automation.image` for a hero (async; placeholder until the job
returns) → schema saved as `draft`. Vendor optionally opens the **Creative-Studio "Landing Pages"**
sub-page editor (Puck/GrapesJS), tweaks, saves the JSON back via `editor_bridge.from_editor` →
`preview()` renders an unlisted preview → vendor hits **Publish** → `guardrails.can_publish` (kill
switch → dry-run → approval gate → page cap) → on allow, `render.render_html()` → `publish` adapter
`put(slug, html)` → `audit.record('landing.publish')` → status `published:<url>`. A visitor on the live
page submits the lead form → `POST /l/<slug>/lead` → `submit_lead` (anti-abuse → suppression → append
`leads.jsonl` → optional `sequencer.enroll` for WhatsApp+voice follow-up → fire conversion pixel/CAPI
if configured → audit). That lead row is read by CRM (drained by the spine), by the **voice/WhatsApp**
follow-up (via the sequencer), and by **analytics/ads** as the conversion that the autonomous optimizer
scales/pauses against.

---

## 6. ASYNC-JOB PATTERN for embedded media (reuse, don't reinvent)

Page generation/render/publish are **synchronous**. The only async work is media:
1. `generate.build()` calls `media.request_image(brief, tenant_id)` →
   `automation.image.generate(...)` returns an `ImageResult` with a `job_id` (and, for fast/`fake`
   providers, an immediate path). The hero section stores `{kind:image, job_id, url:<maybe-empty>}`.
2. **If the job is pending** (hosted async video/3D especially), `render_html` emits a **placeholder**
   (skeleton/blur or a default brand image) and the schema marks the section `media_pending:true`.
3. When the media module's job completes, its result lands in **its own** `var/creatives/` store. A
   light reconcile — `media.patch_completed(page_id)` (called by preview/publish, or by a later cron) —
   scans for completed `job_id`s, patches the schema's `url`, re-renders, and (if published) re-pushes.
4. **No new queue, no new worker, no new vendor here.** The image/video/3D modules own the job
   lifecycle; this module only references job ids and patches results in. This is the single async seam.

---

## 7. SPEND / APPROVAL / AUDIT / SAFETY GUARDRAILS (summary table)

| Guardrail | Mechanism | Default (empty `.env`) |
|---|---|---|
| **No accidental public exposure** | `LP_REQUIRE_APPROVAL=1`; publish sits `blocked_needs_approval` until `approve()` | ON |
| **Kill switch** | `LP_PAUSE_ALL=1` blocks all publishes instantly | OFF (available) |
| **Reversible publish** | default provider `local`; `unpublish()` takedown on every provider | ON |
| **Page cap** | `LP_MAX_PAGES`/tenant | 50 |
| **Lead-form anti-abuse (PUBLIC surface)** | honeypot + per-IP/min rate + suppression check before accept | ON |
| **PII handling** | leads stored locally (append-only), suppression honored, no PII in logs/audit meta | ON |
| **Media spend** | delegated to image/video/3D module budgets (NOT double-capped here) | their caps |
| **Audit trail** | `audit.record(action='landing.*', channel='landing')` → append-only; readable via `audit.tail(action_prefix='landing')` | ON |
| **Dormant publish** | remote providers `not_configured` until creds; `local` always safe | ON |

> **Safety posture:** with an empty `.env`, the module **generates, renders, previews, and publishes
> to `local`** (reversible, on-droplet) but **cannot push to a public CDN/host** (every remote provider
> `not_configured`) and **cannot fire a tracking pixel** (no IDs) and **publish is held at the approval
> gate** (`LP_REQUIRE_APPROVAL=1`). The founder consciously turns on remote publish (creds) and flips
> approval. Public pages collect PII → approval-before-public + audit + takedown are first-class.

---

## 8. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

> The module **runs and is fully testable with NONE of these** (dormant-until-creds; `local` publish +
> deterministic copy work day one). Paste only what you want live. Add to `/opt/famit-agent/.env`
> (or Doppler) and restart — no code change.

| # | What to get | Env var(s) | Where / how (founder steps) | Needed for |
|---|---|---|---|---|
| 1 | **Publish target** (pick ONE; `local` needs nothing) | `LP_PUBLISH_PROVIDER` = `local`(default)\|`do_spaces`\|`cloudflare`\|`netlify`\|`s3`\|`generic` | see rows below | where the live page is hosted |
| 1a | DO Spaces (recommended cheap CDN, fits existing Cloudflare front) | `DO_SPACES_KEY`, `DO_SPACES_SECRET`, `DO_SPACES_BUCKET`, `DO_SPACES_REGION`, `DO_SPACES_ENDPOINT` | DO console → Spaces → create bucket + access keys | public hosting |
| 1b | Cloudflare Pages | `CF_API_TOKEN`, `CF_ACCOUNT_ID`, `CF_PAGES_PROJECT` | Cloudflare dash → Pages project + scoped API token | public hosting |
| 1c | Netlify | `NETLIFY_AUTH_TOKEN`, `NETLIFY_SITE_ID` | app.netlify.com → site + personal access token | public hosting |
| 1d | AWS S3 + CloudFront | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `LP_S3_BUCKET`, `LP_S3_REGION`, opt `LP_CDN_BASE` | AWS console → S3 bucket (static website) + CloudFront | public hosting |
| 1e | generic static host | `LP_PUBLISH_API_URL`, `LP_PUBLISH_API_KEY` | any object store / static host with an upload endpoint | public hosting |
| 1f | **Famit API origin** (REQUIRED for any REMOTE publish) | `LP_API_ORIGIN` (e.g. `https://panel.famit.in`) | the Famit panel base URL | makes the lead form + tracking on a CDN-hosted page POST back to Famit (else leads are lost) |
| 2 | **Custom domain** (optional) | `LP_DOMAIN_BASE` | point a CNAME to the publish target (per-tenant DNS chore) | branded URLs (else `/l/<tenant>/<slug>`) |
| 3 | **Meta Pixel** (optional) | `LP_META_PIXEL_ID` (+ opt `LP_META_CAPI_TOKEN` for server-side conversions) | Meta Events Manager → pixel id (+ CAPI token) | ad conversion tracking → ads optimizer |
| 4 | **Google Analytics 4** (optional) | `LP_GA4_ID` | analytics.google.com → GA4 measurement id | page analytics |
| 5 | **AI copy** (optional) | `LP_COPY_LLM` = `none`(default)\|`groq`\|`sarvam` | **reuses existing** `GROQ_API_KEY`/`SARVAM_API_KEY` — **no new account** | better headlines/copy (else deterministic) |
| 6 | **Guardrails** (recommended, not secret) | `LP_REQUIRE_APPROVAL`(1), `LP_PAUSE_ALL`, `LP_MAX_PAGES`, `LP_LEAD_RATE_PER_MIN` | set in `.env` | approval/kill-switch/anti-abuse |
| 7 | **Embedded media** (optional) | none here — configure the **image/video/3D modules** per `automation-image.md` etc. | those modules' creds (Ideogram/fal/etc.) | hero images/videos/3D on the page |

**Recommended minimum to go live:** keep `LP_PUBLISH_PROVIDER=local` (works now), then add **#1a DO
Spaces** (cheap public hosting on existing infra) + **#3 Meta Pixel** (so leads feed the ads optimizer).
Everything else is optional polish.

> **Per-tenant isolation (mirrors marketing RTF-1):** support `LP_*__<TENANT_ID>` env overrides so one
> tenant's pixel/host can be isolated from another's. Adapters resolve the per-tenant key first, fall
> back to the global key, stay dormant if neither is set. This makes isolation a config choice, not a
> rewrite.

---

## 9. HOW IT CONNECTS TO THE REST (ads → leads → CRM → voice → WhatsApp → analytics)

- **ADS:** published pages are the **destination URL** for the autonomous ads module
  (`automation-ads.md`). Each variant page carries UTM + the Meta Pixel, so the ads optimizer attributes
  CTR/CPC/**conversions (= lead submits)** per creative and scales/pauses accordingly. The landing
  builder produces the **testing batch** of page variants (e.g. 5 landing headlines) the ads module
  A/B-tests at small budgets.
- **LEADS / CRM:** `submit_lead` appends a `{phone,email,name,...}` contact to `var/landing/leads.jsonl`
  — the **same contact contract** the voice/campaign flow uses — which the spine drains into CRM. **No
  `caller.py` import** (bridge pattern, like marketing).
- **VOICE + WHATSAPP:** a lead with `enroll_sequence_id` is `enroll()`ed into the marketing
  **sequencer** (`automation-marketing.md` §3.5), which runs the multi-touch drip across **WhatsApp**
  (`whatsapp.py`) and **voice** (the existing telecaller) — so a form fill auto-triggers an AI call +
  WhatsApp follow-up.
- **ANALYTICS:** GA4 (page) + Meta Pixel/CAPI (conversion) client-side; server-side, every lead is an
  audited conversion row that analytics/billing read. Page list + lead counts surface in the
  Creative-Studio analytics.
- **MEDIA:** hero/section images/video/3D come from `automation/image|video|threed` (their async jobs),
  referenced by `job_id` and patched in on completion (§6).

---

## 10. WHICH CREATIVE-STUDIO SUB-PAGE THIS POWERS

**Creative Studio → "Landing Pages" sub-page** (one of the multi-page sidebar sections, mirroring
Billing's multi-page pattern). That sub-page provides: a **product dropdown → Generate** action
(calls `generate`), a **page list** (drafts/preview/published with status + lead counts, from
`index.jsonl`), the embedded **visual editor** (Puck/GrapesJS loading the page JSON), **Preview** and
**Publish/Unpublish** buttons (with the approval gate), and a per-page **leads/conversions** panel. It
is the human surface over this Python backend; the backend is fully functional headless (API-only) too.

---

## 11. OFFLINE ACCEPTANCE TEST (`tests/test_landing_offline.py`) — ZERO network, ZERO Node

Runnable (cwd = `droplet_work/`) as `python -m creative.tests.test_landing_offline` and under pytest.
The test self-inserts `droplet_work/` on `sys.path`. With an **empty environment** it asserts:

1. **Import safety:** every module imports with empty env; no Node, no network, no FastAPI required
   (`endpoints.py` import is guarded). `landing.status()` returns `publish_provider=="local"`,
   `publish_configured=True` (local always), remote providers `not_configured`.
2. **Generate works with NO creds:** `generate({"goal":"lead-gen","product_ref":"gym-x"})` returns
   `ok=True`, a valid `PageSchema` with hero+benefits+lead_form+cta sections, deterministic copy filled
   from a stubbed product dict, **no LLM call** (monkeypatch the LLM seam to explode if touched).
3. **Render is pure Python:** `render(page_id)` returns valid HTML (`<!doctype html`, a real `<form
   method="post" action="/l/<slug>/lead">`, a `wa.me`/`tel:` CTA), using the **stdlib fallback**
   (monkeypatch `jinja2=None` to force it) — proving no Jinja2/Node dependency.
4. **Copy enhancer fallback:** `LP_COPY_LLM=groq` + monkeypatched LLM that raises → `generate` still
   returns the deterministic copy unchanged, **never raises**.
5. **Dormant publish:** with `LP_PUBLISH_PROVIDER=do_spaces` and no DO keys → `publish` returns
   `status=="not_configured"`, **no httpx call** (monkeypatch httpx to explode), nothing published.
6. **Local publish (reversible) + tenant-scoped slug:** `LP_PUBLISH_PROVIDER=local` + approve →
   `publish` writes `var/landing/published/<tenant>/<slug>.html`, returns `published:/l/<tenant>/<slug>`;
   `unpublish` deletes it. Two tenants with the same slug do **not** collide (separate paths).
6b. **Absolute-origin rule:** with a remote provider (`do_spaces`) **and** `LP_API_ORIGIN` set, the
   rendered HTML's form action + tracking endpoint are **absolute** (rooted at `LP_API_ORIGIN`); with a
   remote provider and **no** `LP_API_ORIGIN` → `publish` → `error:missing_api_origin`, nothing shipped.
6c. **Product source seam:** `generate` with a stub `product_source.load` returning a fixed product
   builds copy from it; with `product_source` unconfigured it degrades to brief-only fill, **no raise**.
7. **Approval gate:** `LP_REQUIRE_APPROVAL=1` + no approval → `publish` → `blocked_needs_approval`,
   nothing written; after `approve(page_id)` → publishes.
8. **Kill switch:** `LP_PAUSE_ALL=1` → `publish` → `blocked_paused`, nothing written.
9. **Lead capture + bridge:** `submit_lead("<slug>", {"name":"A","phone":"+9199...","email":"a@b.c"})`
   appends exactly one row to `var/landing/leads.jsonl` with the `{contact:{name,phone,email}}` shape,
   returns a `lead_id`; **idempotency/anti-abuse:** a honeypot-filled or over-rate submit →
   `blocked_*`, no row appended.
10. **Sequencer enroll is optional + guarded:** with the marketing pkg ABSENT (monkeypatch import to
    None), `submit_lead` still succeeds and writes the lead (enroll just skipped). With a stub
    `sequencer.enroll` present, it is called once with the contact.
11. **Media async-safe:** with `automation.image` absent/stubbed to return a pending `job_id`, `render`
    emits a placeholder and marks `media_pending`; a stub "completed" patch fills the url and
    re-renders — **no real media call**.
12. **Tracking dormant:** with no `LP_META_PIXEL_ID`/`LP_GA4_ID` → rendered HTML contains **no** pixel
    script; with IDs set → the snippet appears. `conversion_ping` with no CAPI token → `not_configured`,
    no network.
13. **Audit wired:** a (local) publish + a lead submit each append a `landing.*` row retrievable via
    `audit.tail(action_prefix="landing")`.
14. **Never-raises fuzz:** feed malformed briefs/forms (empty, wrong-type, `None`, huge) → each returns
    an `invalid`/`error:`/`blocked_*` dict, **no exception**.

The test uses a temp `var/landing/` + temp audit file and **monkeypatches `httpx` (and the LLM/media
seams) to raise if any code path tries a real call** while dormant — proving the guarantees mechanically.
Exit non-zero on any failure (the orchestrator gates on it).

---

## 12. BUILD ORDER (one verifiable UNIT each; test after every unit; NO git)

1. `schema.py` (dataclasses + validate + JSON round-trip) + `store.py` + `creative/__init__.py` →
   tests #1 partial (import safety) + schema round-trip.
2. `render.py` + `templates/` (Jinja2-or-stdlib) → tests #3, #12 (tracking off), placeholder path.
3. `product_source.py` (guarded read seam, stubbable) + `generate.py` (deterministic build; LLM
   enhance optional) → tests #2, #4, #6c.
4. `guardrails.py` + `meter.py` → tests #7, #8.
5. `publish/` (`local` first, then dormant remote adapters + `generic`) → tests #5, #6.
6. `leads.py` + `tracking.py` → tests #9, #10, #12 (tracking on), #13.
7. `media.py` (bridge to `automation.image`, async patch) → test #11.
8. `editor_bridge.py` + `endpoints.py` (router defined, **unmounted**) + `config_help.py` + exports.
9. `tests/test_landing_offline.py` — the full §11 suite green. **Gate.**

Wiring `endpoints.py` into the spine (mounting routes, serving `/l/<slug>`, draining `leads.jsonl` into
CRM, the media-completion cron) is a **separate, later, explicitly-scoped phase** that touches
`caller.py` — **out of scope here** (do not edit the spine).

Reuse, don't reinvent: the dormant `is_configured()/not_configured` + never-raise + httpx-optional
pattern from `whatsapp.py`; the append-only `record()`/`tail()` contract from `audit.py`; the meter
shape from `vendors/groq_meter.py`; the bridge + sequencer `enroll()` contract from
`automation-marketing.md`; the media job-id pattern from `automation-image.md`. Read secrets via
`config.get()` with an `os.getenv` fallback.

---

## 13. REAL-vs-HYPE (honest, no overclaim)

- **REAL now (offline-verifiable):** schema, deterministic copy fill, pure-Python render to fast static
  HTML, local publish + takedown, lead capture + CRM hand-off, sequencer enroll, approval/kill-switch/
  anti-abuse guardrails, dormant remote publish + tracking, audit. All pure logic, tested with no
  network and no Node.
- **REAL but needs the founder's accounts (chores, not hype):** public hosting (DO Spaces/Cloudflare/
  Netlify/S3 keys + optional custom-domain DNS), conversion tracking (Meta Pixel + CAPI token, GA4 id),
  AI copy (reuses existing Groq/Sarvam — no new account), embedded media (the image/video/3D modules'
  own vendor keys).
- **HYPE to avoid:** "AI writes a perfect, on-brand, legally-cleared converting page from one prompt" —
  no. Generation is **template-anchored** with optional LLM copy under length caps and a **human
  preview/edit + approval gate** before anything goes public; brand-exact lockups and legal/claims
  review (RERA, "guaranteed returns", competitor marks) stay human. "Drag-drop builder = the product" —
  no; the editor is an optional surface over a schema, and the schema+render is the actual engine.
  "One key publishes everywhere" — no; each host is its own account, and custom domains are a DNS chore.
- **Deliverability/conversion is a marketing game, not a code feature** — the module renders a fast,
  mobile, tracked, form-wired page; CTR/conversion still depend on offer, audience and creative (which
  the ads module optimizes against real data).

---

## 14. SOURCES (2026, active projects only)

- Puck (MIT, v0.21.3 2026-06-08, 12.8k★, JSON `initialData`/`onPublish` data model — embeddable React
  visual editor): https://github.com/measuredco/puck
- GrapesJS (BSD-3-Clause core, v0.22.16 2026, TypeScript-rewritten, framework-agnostic, actively
  maintained): https://github.com/GrapesJS/grapesjs ; license: https://github.com/GrapesJS/grapesjs/blob/dev/LICENSE
- OSS page-builder landscape 2026 (Puck vs GrapesJS vs Webstudio/Webiny/Plasmic; self-host + React):
  https://dev.to/fede_bonel_tozzi/top-5-page-builders-for-react-190g ;
  https://www.opensourcealternatives.to/blog/best-open-source-website-builders
- AI landing-page generation landscape 2026 (prompt→sections workflow; aipage.dev OSS reference):
  https://github.com/zinedkaloc/aipage.dev ;
  https://www.nxcode.io/resources/news/ai-landing-page-generator-2026
- House patterns this spec mirrors (verified against source): `droplet_work/whatsapp.py` (dormant /
  never-raise / provider-agnostic / httpx-optional), `droplet_work/audit.py` (`record`/`tail`),
  `droplet_work/vendors/groq_meter.py` (meter shape), `design/automation-marketing.md`
  (bridge + sequencer `enroll`, RTF-1 per-tenant creds), `design/automation-image.md` (media job-id
  async pattern), `design/automation-ads.md` (ads optimizer reads conversions).

---

## RED-TEAM FIXES (folded)

> Adversarial review 2026-06-09. Each item below is a **binding spec delta** that OVERRIDES any
> contradicting earlier text. A build agent applies these verbatim. Severity: 🔴 blocker, 🟠 must-fix,
> 🟡 minor. The OSS/API and house-pattern claims were source-verified (see VERIFIED, end of section).

### RTF-1 🔴 BLOCKER — `lead_form` MUST carry explicit consent before any voice/WhatsApp enroll or pixel fire
The spec auto-enrolls a **public** form-fill into **voice + WhatsApp** follow-up (`sequencer.enroll`)
and fires Meta Pixel on a PII-collecting page, with anti-abuse = honeypot/rate/suppression only — **none
of which is consent**. For an Indian SaaS auto-dialing/WhatsApp-ing form-fills, that is a regulatory
exposure (promotional voice/WA needs prior opt-in; DPDP-style notice) AND a platform-ToS violation
(Meta Pixel + Lead Ads require a *visible* privacy-policy link; WhatsApp Business API forbids
un-opted-in marketing). This is folded as a HARD REQUIREMENT, not optional:
- **Schema delta (§3.2 `lead_form.data`):** add required fields
  `consent:{required:bool(default True), label:str, checkbox:bool(default True)}` and
  `privacy_policy_url:str`. `PageSchema.validate()` MUST FAIL (`status:"invalid"`) if a page contains a
  `lead_form` whose `enroll_sequence_id` is set OR whose page has any tracking ID, but
  `privacy_policy_url` is empty.
- **Render delta (§3.4):** `render_html` MUST emit (a) a visible consent **checkbox** (required attr)
  inside the `<form>` when `consent.required`, and (b) a visible **privacy-policy link** in the form
  footer + page footer whenever a `lead_form` or any tracking pixel is present. No pixel `<script>` is
  emitted unless `privacy_policy_url` is non-empty.
- **Enroll gate (§3.6 `submit_lead`):** `sequencer.enroll(...)` is called **only if** the submitted
  form carries `consent == true` (the checkbox value). Absent/false consent → still store the lead row
  (with `consent:false`), but **skip enroll** and skip any marketing conversion ping. The lead row gains
  a `"consent": bool` field. Suppression/opt-out still wins over consent.
- **Cred delta (§8):** new optional `LP_PRIVACY_POLICY_URL` (per-tenant via `__<TENANT>`) as a default
  when a page omits its own; if neither page nor env supplies one, pixels/enroll stay dormant (fail
  closed). Add to the cred table as a **recommended-before-going-public** row.
- **Test delta (§11):** new **#15** — a `lead_form` with `enroll_sequence_id` and empty
  `privacy_policy_url` → `generate`/`validate` returns `invalid`; a submit with `consent:false` writes
  the lead but does **not** call the stubbed `sequencer.enroll` and fires no conversion ping; rendered
  HTML with a pixel ID present but no privacy URL emits **no** pixel script.

### RTF-2 🔴 BLOCKER — propagate the SLUG-SCOPE rule everywhere (the §3.2 fix is not wired through)
The cross-tenant-collision/PII-leak rule in §3.2 (URL `/l/<tenant>/<slug>`, file
`published/<tenant>/<slug>.html`, key `(tenant_id, slug)`) is **contradicted** by every other section,
which still specifies bare `/l/<slug>` and `published/<slug>.html` (§0.4 line ~38, §1.4 lines ~120-121,
§2 `local.py` note, §3.4 form action, §3.5 `local` adapter + `published/<slug>.html`, §3.10 routes
`GET /l/{slug}` & `POST /l/{slug}/lead`, §4 data-model table, §5 control-flow, §11 test #3, §12 wiring).
A build agent coding to §3.5/§3.10 **reintroduces the exact leak the rule closes.** Binding delta — the
tenant-scoped form is CANONICAL; replace every bare-slug occurrence:
- **Public path:** `GET /l/<tenant>/<slug>`; lead sink `POST /l/<tenant>/<slug>/lead`.
- **`local` adapter (§3.5):** writes `var/landing/published/<tenant>/<slug>.html`; `put`/`delete` take
  `(tenant_id, slug)`; url returned = `/l/<tenant>/<slug>`. The `Publisher` protocol signatures gain
  `tenant_id` (`put(self, tenant_id, slug, html, assets=None)`, `delete(self, tenant_id, slug)`).
- **`status` vocabulary (§3 intro):** `published:/l/<tenant>/<slug>`.
- **Render (§3.4):** default form action = `/l/<tenant>/<slug>/lead` (and absolute per RTF/ABSOLUTE-
  ORIGIN when remote). `LP_FORM_ACTION` default updated to `/l/{tenant}/{slug}/lead`.
- **Routes (§3.10):** `POST /l/{tenant}/{slug}/lead`, `GET /l/{tenant}/{slug}`.
- **Test #3 + #6 (§11):** assert the rendered form action is `/l/<tenant>/<slug>/lead`; #6 already
  asserts the tenant-scoped file path — make #3 consistent.
- `<tenant>` is the opaque tenant id (or `LP_DOMAIN_BASE` subdomain), never PII — unchanged.

### RTF-3 🟠 MUST-FIX — `audit.record(...)` calls are missing the required first positional `actor`
Verified against `droplet_work/audit.py:60`: the real signature is
`record(actor, action, object_type="", object_id="", ip="", channel="api", tenant_id=None, ...)`.
Every call site in this spec (§0.1 item 7, §3.6 step 6, §5, §7 audit row) writes
`audit.record(action='landing.*', channel='landing')` — i.e. **no `actor`**. That is a `TypeError`
raised at the CALL site, *before* entering `record()`, so `record`'s internal swallow does NOT catch
it; the house-contract `try/except` around the mutating action then **silently eats it** → **every
landing audit write becomes a no-op**, turning the audit guardrail off and **failing test #13** (which
asserts a `landing.*` row is retrievable via `audit.tail(action_prefix='landing')`). Binding delta — all
call sites become:
```python
audit.record(tenant_id, "landing.publish", channel="landing",
             object_type="page", object_id=page_id, meta={...})   # publish
audit.record(tenant_id, "landing.lead", channel="landing",
             object_type="lead", object_id=lead_id, meta={...})    # lead (no raw PII in meta)
```
`actor` = the acting tenant/user id (for a PUBLIC lead submit with no auth principal, use `tenant_id`
as actor and set `ip` from `source_meta`). Test #13 stands and now actually exercises a real write.

### RTF-4 🟠 MUST-FIX — interactive 3D is NOT "no external JS / offline render"; state it honestly
§3.4 render asserts *"NO external JS framework, NO network at render time,"* yet §3.2/§5 support
`media:{kind:threed}`. An **interactive** 3D model in HTML requires a JS viewer (`<model-viewer>` web
component or three.js) + a CDN/script and a runtime fetch of the `.glb` — which **breaks both the
no-JS and the offline-render claims.** Binding delta (honest scoping, no overclaim):
- The pure-Python render guarantee ("no external JS framework, no network at render time") applies to
  **text + image + the lead form** — the conversion-critical surface. It remains literally true for
  those.
- `kind:threed` (and `kind:video` for hosted players) renders as **either** (a) a static poster image
  (the model/video's `automation.threed`/`automation.video` thumbnail) with a click-to-load, **or**
  (b) an OPTIONAL `<model-viewer>` embed gated behind `LP_ENABLE_3D_VIEWER=1`. When enabled, the page
  carries a **documented external JS dependency** (`<script type="module" src="…model-viewer…">`) and a
  runtime asset fetch — this is explicitly NOT the offline/no-JS path and is called out in §13 HYPE.
- **Default = poster image** (offline-safe, no JS). The offline acceptance test only ever exercises the
  poster path; `LP_ENABLE_3D_VIEWER` defaults OFF so test #11's "placeholder/patch" path is unchanged
  and still requires no JS. §13 gains a line: *"interactive on-page 3D needs a JS viewer + CDN script
  and a model fetch — it is opt-in (`LP_ENABLE_3D_VIEWER`), not part of the offline/no-JS guarantee;
  the default is a static poster."*

### RTF-5 🟡 MINOR — media-completion re-push of a PUBLISHED page must respect the approval gate
§6 step 3 says `media.patch_completed` re-renders and "(if published) re-pushes." A page approved+
published with a **placeholder** hero could then auto-swap to a real (possibly off-brand/unreviewed)
hero on a public URL with no human in the loop. Binding delta: a re-push that changes **visible media**
on an already-published page is treated as a publish mutation → it goes through `guardrails.can_publish`
(kill switch + approval gate if `LP_REQUIRE_APPROVAL=1`); if approval is required it is **queued**
(`status:"blocked_needs_approval"`) and the live page keeps its current (placeholder or prior) asset
until approved. Re-renders that touch only text never need this. Also: prefer generating/awaiting the
hero before first publish where latency allows, so the common path doesn't ship a skeleton.

### RTF-6 🟡 MINOR — GrapesJS version is stale in §1.2/§14 (cosmetic; editor is out-of-scope)
Source check 2026-06-09: GrapesJS latest is **v0.23.2 (2026-06-02)**, BSD-3-Clause, actively maintained
(repo shows ongoing 2026 releases) — the spec cites v0.22.16. Bump the two references to v0.23.2. No
functional impact (the editor is frontend-only, never a Python/test dependency, per §1.2). Puck is
correct as cited (MIT, v0.21.3 2026-06-08, JSON `initialData`/`onPublish` — re-verified).

### VERIFIED (held up under adversarial check — recorded so these don't read as unexamined)
- **OSS active/maintained + licenses:** Puck MIT v0.21.3 (2026-06-08), JSON `initialData`/`onPublish`
  data model — verified on GitHub. GrapesJS BSD-3-Clause, v0.23.2 (2026-06-02), actively maintained —
  verified (spec's pinned minor is one behind; see RTF-6). Both are embeddable, permissive, and
  correctly scoped as **frontend-only** — never a server/runtime/offline-test dependency. ✔
- **House patterns mirror real source:** `whatsapp.py` dormant/never-raise/`not_configured`/httpx-
  optional/`_build_body` confirmed at the cited lines (73, 196, 254, 146); `audit.record`/`audit.tail`
  with `action_prefix` confirmed; `caller.py` bare-name flat imports confirmed (so §2.1 packaging is
  right). The marketing `enroll(seq_id, contact, *, tenant_id)` and `automation.image.generate(brief,
  *, tenant_id)->ImageResult{job_id}` contracts the bridges/media call are confirmed against
  `automation-marketing.md:244` and `automation-image.md:206`. ✔
- **Autonomous AD-SPEND safety:** correctly OUT OF SCOPE — this module produces destination pages; it
  triggers **no bid/budget action**. Spend safety lives in `automation-ads.md` (which this only feeds
  conversions to) and embedded-media spend is delegated, not duplicated, to the image/video/3D module
  budgets. No autonomous-spend surface exists here to guard. ✔
- **Async pattern:** sound — generate/render/publish are synchronous; the single async seam is media,
  which **references** existing `automation.image|video|threed` job-ids and patches on completion (no
  new queue/worker/vendor). The only added rule is RTF-5 (gate a published-page media re-push). ✔
- **Truly dormant + non-breaking:** confirmed — new files only under `creative/`, no `caller.py`/
  `agent.py` edits, `endpoints.py` defined-but-unmounted, every remote provider `not_configured` until
  creds, `local`+deterministic copy work with an empty `.env`, all guarded optional imports. ✔
- **Creds/cost honesty:** the cred table (§8) is complete and per-provider; page render/publish cost is
  genuinely ₹0 (compute + static host) with media cost single-sourced to the media modules' meters —
  no hidden vendor. RTF-1 adds the one missing cred (`LP_PRIVACY_POLICY_URL`). ✔
