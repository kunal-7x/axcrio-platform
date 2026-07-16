# WHATSAPP CREATIVE STUDIO — Execution-Ready Design Spec

> **Module id:** `whatsapp-creative`  ·  **Code path:** `droplet_work/creative/whatsapp/`
> **Creative-Studio sub-page it powers:** **"WhatsApp Creatives"** (the WhatsApp-channel sub-page of
> the Creative Studio sidebar section — siblings: Image & Banner Studio, Ad Copy/Hooks, Video, 3D,
> Landing Pages, Brochure/Catalog).
> **Date:** 2026-06-09  ·  Research sources inline + listed in §13.

> **For the build agent — implement this verbatim.** This is a NEW module of the Famit Autonomous
> Business OS **Creative Studio**: the **WhatsApp packaging + delivery + post-call-trigger** layer.
> It turns a vendor's stored **business + product + campaign** data (selected via a **dropdown**) into
> a ready-to-send **WhatsApp creative KIT** — banner + product card + offer image + brochure PDF +
> short video + caption + booking-link CTA — and then **sends that kit over WhatsApp**, most importantly
> **auto-sent after an interested AI voice call** (banner + brochure + price + booking link).

---

## 0. THE FRAMING THAT DEFINES THIS MODULE (read first)

**This module DELEGATES generation; its unique job is WhatsApp packaging + delivery + the post-call
trigger.** The brief lists outputs as "WhatsApp banners / product cards / offer images / brochure
attachments / short videos" — but **every one of those already has an owner** in the Creative Studio:

| Asset | Owner module (already specced) | This module's role |
|---|---|---|
| banners / product cards / offer images | `creative/image/` (`generate(ImageBrief)`) | request WhatsApp sizes, composite price+link+logo, **send** |
| brochure / catalog PDF | `creative/brochure/` | attach as a WhatsApp document, **send** |
| short video | `creative/video/` | attach as a WhatsApp video, **send** |
| ad copy / hooks / captions | marketing `content.py` / LLM seam | use as the message caption, **send** |

If this spec re-generated images/PDFs/videos it would **duplicate three modules**. It must not. Drawing
the same boundary the `creative-brochure-catalog.md` spec drew ("I am the assembler, I delegate"), this
module's **three genuinely-new responsibilities** are:

1. **WhatsApp-channel PACKAGING** — request WhatsApp aspect ratios/sizes from the sibling generators,
   then **deterministically composite** (Pillow) the price, booking link/QR, and logo onto a card, and
   assemble a **kit** (banner + product card + offer image + brochure PDF + short video + caption + CTA).
2. **WhatsApp media DELIVERY** — the capability that **genuinely does not exist yet**. `whatsapp.py`
   sends only text + text-param templates; it **cannot** send an image/document/video message or an
   interactive CTA-URL button. This module builds that, **reusing `whatsapp.py`'s config without
   editing it**.
3. **Post-call TRIGGER orchestration** — `interested`/`callback` AI voice call → assemble kit → send
   the banner+brochure+price+booking-link package, seeding the WhatsApp thread caller.py already manages.

**Hard rules from the project brief (do NOT violate):**
- NEW code ONLY under `droplet_work/creative/`. **Do NOT edit `caller.py` / `agent.py` / `whatsapp.py`**
  — backend spine; final wiring deferred to the orchestrator. This module **reuses** `whatsapp.py`'s
  config helpers by import; it never modifies them.
- **NO git** (the orchestrator commits).
- Every integration is **PROVIDER-AGNOSTIC + DORMANT-UNTIL-CREDS**: a graceful no-op returning
  `{"status":"not_configured"}` that **NEVER raises** until the founder pastes keys — byte-for-byte the
  `droplet_work/whatsapp.py` pattern.
- **Verifiable OFFLINE**: the acceptance test makes **zero live external calls**. A built-in `fake`
  WhatsApp transport + the sibling `fake` generators prove the whole pipeline (enrich → assemble →
  composite → suppression-check → approval-gate → send → meter → audit → store) with no key and no paisa.
- Cost-optimized; self-host on DigitalOcean where it wins; production-grade, scalable.
- **REVENUE-CONNECTED**: every send carries `batch_id` + `variant_id` so analytics can attribute which
  WhatsApp angle drives bookings.

---

## 1. CHOSEN TOOLS + WHY (researched 2026-06, all ACTIVE; sources §13)

| Need | Chosen tool | Why (evidence) | Price / Licence |
|---|---|---|---|
| **WhatsApp media + interactive delivery** | **Meta WhatsApp Cloud API** (`graph.facebook.com`, native — the founder's actual BSP per `whatsapp.py`) | Native image/video/document messages + **interactive CTA-URL buttons with media headers**; same host/token `whatsapp.py` already uses → we extend, not re-onboard | per-message billing (see meter §6); API free |
| **Deterministic composite (price / logo / booking link / QR onto a card)** | **Pillow** (PIL fork, 12.x, June 2026) | The standard, actively-maintained Python imaging lib; `ImageDraw.text()`, `alpha_composite()`, custom-font loading, text-wrap → exact, repeatable lockups. We **do NOT** ask an AI model to bake price/legal text (unreliable — see image spec §10) | **PIL/MIT-HPND** (free commercial) |
| **Booking-link QR (optional, on the card)** | **`qrcode`** (Python, BSD) | Tiny, offline, deterministic QR for the booking URL when a scannable code is wanted on the image | **BSD** |
| **Banner / card / offer image bytes** | **REUSE `creative/image/`** | Already provider-agnostic, dormant-until-creds, metered, audited. Don't duplicate Ideogram/Recraft/FLUX routing | reuse |
| **Brochure / catalog PDF attachment** | **REUSE `creative/brochure/`** | Already a full PDF assembler (WeasyPrint/Gotenberg/Typst). We just attach its output | reuse |
| **Short video attachment** | **REUSE `creative/video/`** | Already the async video engine. We attach its rendered MP4 | reuse |
| **Caption / hook / CTA copy** | **REUSE marketing `content.py` / LLM seam** | "Reuse the existing LLM seam; no new vendor." Degrade to templated copy if unconfigured | reuse |
| **HTTP (retry, no-raise)** | **REUSE `vendors/_http.py`** | `request_json` → `(ok, json, err)`; redact secrets via `vendors.redact()` | reuse |

**2026 WhatsApp Cloud API facts that shape the design (verified, §13):**
- **Two ways to attach media:** (a) a **public HTTPS `link`**, or (b) a **`media_id`** obtained by
  `POST /{phone_number_id}/media` (multipart upload). Uploaded media is **stored 90 days**, validated
  once, and is **faster for repeat sends** — so a kit reused across many recipients uploads **once** and
  reuses the `media_id`. We support **both**; default = upload-once → `media_id`.
- **Interactive CTA-URL button** message supports an optional **media header** (image/video/document) +
  body (≤1024 chars) + a **single** URL button (text ≤20 bytes). This is the booking-link button.
- **24-hour customer-service window — opened ONLY by an inbound WhatsApp message** (or a click-to-WhatsApp
  ad), **NOT by a phone/voice call.** A WhatsApp session is a WhatsApp-channel event; the AI voice call is
  on the telephony channel and does **not** open it. So free-form media is allowed (and billed **free** as
  a SERVICE message) **only when the contact has already messaged this WhatsApp number** (open session).
  For a cold contact who never WhatsApp'd you, a free-form media message is **rejected** (Meta error
  **131047 "re-engagement required"**) — not billed-free, just undelivered.
- **No open session (the common cold post-call case):** the conversation MUST be opened with an
  **approved template**, which can carry a **media header** (image/video/document) + quick-reply/CTA
  buttons. This bills as a **MARKETING** (≈₹0.86 India, Jan 2026) or **UTILITY** (≈₹0.11–0.145) message.
- **Therefore the sender DETECTS session state** (recent inbound from this contact?) and picks the path —
  it never blindly assumes the window is open. Both paths are built (§4); the meter (§6) reflects which fired.

---

## 2. FILES TO CREATE (all NEW, under `droplet_work/creative/whatsapp/`)

```
droplet_work/creative/whatsapp/
  __init__.py                     # PUBLIC API (see §3)
  README.md                       # what it does, cred list, how to run the offline test
  types.py                        # WaKitSpec, WaKit, WaAsset, WaSendResult, WaBatchResult dataclasses + validate/normalize
  context.py                      # pull tenant business/product/campaign data (the dropdown source) -> kit defaults (brand, price, booking_url)
  assemble.py                     # build a WaKit: call sibling generators (image/brochure/video) + compose caption + CTA; tag batch/variant
  compose.py                      # Pillow deterministic layer: overlay price + logo + booking link/QR onto the card (offline, free)
  angles.py                       # expand N WhatsApp "angles" (benefit/urgency/social-proof/price-drop/scarcity) -> variant kits (the "5 angles")
  transport.py                    # WhatsApp media/interactive SENDER (reuses whatsapp.py config; builds bodies whatsapp.py can't)
  media_upload.py                 # POST /{phone}/media -> media_id (upload-once cache keyed by file hash); link fallback
  asset_url.py                    # resolve a var/creatives asset -> public HTTPS link (Cloudflare-fronted) OR upload->media_id
  suppression.py                  # opt-out / suppression check BEFORE every send (mirrors caller.py _WA_OPTOUT_WORDS + suppression list)
  budget.py                       # send-rate caps + approval gate (distribution gate; NOT a per-image $ ceiling)
  meter.py                        # wa-conversation meter: per-message category cost -> usage_events (vendor="whatsapp_creative")
  status_hook.py                  # ingest Meta status webhooks (sent/delivered/read) + CTA clicks -> per-variant analytics
  audit_hook.py                   # thin wrapper -> droplet_work/audit.py if importable, else no-op
  storage.py                      # write kit manifest + send log to var/creatives/wa/, index.jsonl
  trigger.py                      # send_creative_package(...): the post-call entrypoint the orchestrator wires into caller.py ~1248
  transports/
    __init__.py                   # TRANSPORT REGISTRY: id -> sender; resolve()
    base.py                       # Transport protocol: status(), send_media(), send_interactive(), send_template(), upload()
    meta.py                       # native Meta Cloud API transport (dormant w/o META_WA_* — reuses whatsapp._meta_cfg)
    fake.py                       # OFFLINE transport: records calls in-memory, zero network — powers the test
  tests/
    __init__.py
    test_whatsapp_creative_offline.py   # THE acceptance test — fully offline against the fake transport + fake siblings
```

**Reuse, don't reinvent** (verified against repo source):
- never-raise / no-op-when-unconfigured + native-Meta config → `whatsapp.py`
  (`meta_configured()`, `_meta_cfg()`, `_meta_url()`, `is_configured()`). **Imported, never edited.**
- retry/no-raise HTTP + secret redaction → `vendors/_http.py`, `vendors.redact()`.
- internal metering → usage_events (no billing API; cost = count × category rate card, `estimated:True`)
  → mirror `vendors/groq_meter.py`.
- append-only best-effort audit, IST timestamps, swallows all exceptions → `audit.py` (`record(actor,
  action, object_type=…, object_id=…, channel=…, meta=…)`).
- opt-out words + suppression → caller.py `_WA_OPTOUT_WORDS` and its suppression store (re-read, not
  re-implemented logic).
- config: read env fresh inside functions via `os.getenv` (config.py merges Doppler into `os.environ`).

---

## 3. PUBLIC INTERFACE (the only surface the orchestrator imports)

```python
# droplet_work/creative/whatsapp/__init__.py
from .types import WaKitSpec, WaKit, WaAsset, WaSendResult, WaBatchResult

def status() -> dict: ...
    # {"status":"ready"|"not_configured", "transport":"meta"|"fake", "siblings":{image:..,brochure:..,video:..},
    #  "require_approval":bool, "rate_caps":{...}}

def transports_status() -> dict: ...
    # {"meta":"configured"|"not_configured"|"error", "fake":"configured"}

def assemble_kit(spec: "WaKitSpec | dict", *, tenant_id: str = "") -> "WaKit": ...
    #   1. context.enrich(spec, tenant_id) -> brand, price, booking_url, product photos from stored vendor data
    #   2. request banner/card/offer (creative/image), brochure PDF (creative/brochure), short video (creative/video)
    #      -- each DELEGATED & dormant-safe: if a sibling is not_configured, that asset is skipped, kit still builds
    #   3. compose.overlay(...) -> deterministic price + logo + booking-link/QR card (Pillow, offline)
    #   4. caption/CTA from LLM seam (or templated fallback)
    #   5. WaKit(kit_id, assets=[WaAsset...], caption, cta_url, batch_id, variant_id)

def assemble_angles(spec: "WaKitSpec | dict", *, n: int = 5, tenant_id: str = "") -> "WaBatchResult": ...
    #   the "5 WhatsApp angles" testing batch: angles.expand() -> N variant kits, each tagged variant_id.
    #   No send -- returns the batch of kits for the autonomous-ads / manual review surface.

def send_kit(kit: "WaKit | dict", to: str, *, tenant_id: str = "", inside_window: bool | None = None,
             dry_run: bool = False) -> "WaSendResult": ...
    #   1. suppression.check(tenant_id, to) -> if opted-out: WaSendResult(status="suppressed"), NO send, audited
    #   2. budget.check(tenant_id) -> rate cap / approval gate -> "over_rate" | "pending_approval" | ok
    #   3. window = inside_window if not None else session_open(to)  # DETECT: recent inbound WA from `to`?
    #      open  -> free-form media + interactive CTA (SERVICE, free)
    #      closed-> send_template with a media header + CTA button (MARKETING/UTILITY, billed; needs cred #2)
    #   4. resolve each asset -> media_id (upload-once) or public link  (asset_url + media_upload)
    #   5. transport.send_*(...) per path above
    #   6. meter.record(category) ; audit_hook.log(...) ; storage.log(...)
    #   7. WaSendResult(ok, status, message_ids=[...], category, est_cost_inr, batch_id, variant_id)

async def send_kit_async(...) -> "WaSendResult": ...   # async twin (FastAPI loop)

def send_creative_package(tenant_id: str, contact: dict, outcome: str, camp_fields: dict,
                          *, inside_window: bool | None = None) -> "WaSendResult": ...
    #   THE POST-CALL ENTRYPOINT (trigger.py). What the orchestrator wires into caller.py ~1248 after the
    #   interested/callback gate. Dormant-safe: returns {"status":"not_configured"} when WA env absent.
    #   = assemble_kit(from camp_fields/product) -> send_kit(to=contact.phone). inside_window defaults to
    #   DETECTION (session_open) -- a voice call does NOT open the WA window, so a cold contact takes the
    #   billed template path (needs an approved template, cred #2). NEVER raises into the call loop.

def ingest_status(payload: dict) -> dict: ...
    #   status_hook: Meta message-status webhook (sent/delivered/read/failed) + CTA-click events ->
    #   update per-variant analytics counters. Wired into the existing caller.py /whatsapp/inbound webhook.
```

### `WaKitSpec` (dropdown-driven input) — `types.py`
```python
@dataclass
class WaKitSpec:
    tenant_id: str
    product_id: str = ""              # selected from the Creative Studio dropdown
    campaign_id: str = ""             # selected from the dropdown (optional)
    angle: str = "benefit"            # benefit|urgency|social-proof|price-drop|scarcity (drives caption + overlay)
    language: str = "en"              # en|hi|... (non-Latin headline -> sibling image routes to gpt_image)
    include: list[str] | None = None  # which assets: ["banner","product_card","offer_image","brochure","video"]
    price: str = ""                   # the price string composited onto the card (from product data)
    booking_url: str = ""             # the CTA URL (booking/landing link); auto-filled by context.enrich
    brand: dict | None = None         # {logo_url, palette, font}; auto-filled by context.enrich
    batch_id: str = ""                # set by assemble_angles for the variant batch
    variant_id: str = ""              # set by assemble_angles; lets analytics attribute the winning angle
```

### `WaAsset` — one attachment in the kit
```python
@dataclass
class WaAsset:
    kind: str                         # image|document|video
    path: str                         # local var/creatives path (source of bytes)
    link: str = ""                    # resolved public HTTPS URL (if link-mode)
    media_id: str = ""                # resolved Meta media_id (if upload-mode)
    mime: str = "image/png"
    filename: str = ""                # for documents (brochure.pdf)
    role: str = ""                    # banner|product_card|offer_image|brochure|video (analytics label)
```

### `WaKit` / `WaSendResult` / `WaBatchResult`
```python
@dataclass
class WaKit:
    ok: bool
    status: str                       # ready|partial|not_configured|invalid|error:<...>
    kit_id: str                       # time-sortable; names var/creatives/wa/<kit_id>/
    assets: list[WaAsset]
    caption: str
    cta_text: str = "Book now"        # <=20 bytes (WhatsApp CTA-button limit)
    cta_url: str = ""
    tenant_id: str = ""
    batch_id: str = ""
    variant_id: str = ""
    meta: dict = None                 # {product_id,campaign_id,angle,language,siblings_used}

@dataclass
class WaSendResult:
    ok: bool
    status: str                       # sent|suppressed|over_rate|pending_approval|not_configured|invalid|error:<...>
    to: str
    message_ids: list[str]            # Meta wamid(s) -- one per asset + one for the interactive message
    category: str                     # service|marketing|utility (drives the meter)
    est_cost_inr: float               # 0.0 only on the free-form SERVICE path (open session); billed on the template path
    estimated: bool                   # True (rate-card based)
    kit_id: str = ""
    batch_id: str = ""
    variant_id: str = ""
    meta: dict = None

@dataclass
class WaBatchResult:                  # output of assemble_angles
    ok: bool
    status: str
    batch_id: str
    tenant_id: str
    requested: int
    produced: int
    kits: list["WaKit"]
    meta: dict = None
```

---

## 4. TRANSPORT — the media/interactive SENDER `whatsapp.py` lacks

`transport.py` + `transports/meta.py` implement the WhatsApp send shapes `whatsapp.py` does **not** have,
**reusing** `whatsapp.py`'s native-Meta config (`whatsapp.meta_configured()`, `whatsapp._meta_cfg()`,
`whatsapp._meta_url()`) so there is **one source of truth for creds** and **zero edits** to the spine.
Every method is dormant-when-unconfigured and **never raises** (mirror `vendors/_http.py`: short timeout,
retry on 429/5xx, return an error string not an exception; redact secrets in logs).

```python
# transports/base.py
class Transport(Protocol):
    id: str
    def status(self) -> str: ...                                   # configured|not_configured|error
    def upload(self, path: str, mime: str) -> tuple[str, str]: ...  # -> (media_id, err)
    def send_media(self, to, kind, *, media_id="", link="", caption="", filename="") -> dict: ...
    def send_interactive(self, to, *, header_asset=None, body="", cta_text="", cta_url="") -> dict: ...
    def send_template(self, to, name, lang, *, header_asset=None, body_params=None, buttons=None) -> dict: ...
```

**Meta request shapes built here (the new capability):**
- **Upload (once):** `POST {graph}/{version}/{phone_id}/media` multipart `{messaging_product:"whatsapp",
  file, type}` → `{id}` (the `media_id`). Cached by file SHA so a kit reused across recipients uploads once.
- **Image message:** `{"messaging_product":"whatsapp","to":..,"type":"image",
  "image":{"id":<media_id> | "link":<url>, "caption":..}}`
- **Document (brochure):** `…"type":"document","document":{"id"|"link":..,"caption":..,"filename":"brochure.pdf"}`
- **Video (short video):** `…"type":"video","video":{"id"|"link":..,"caption":..}`
- **Interactive CTA-URL (booking button + media header):**
  `{"type":"interactive","interactive":{"type":"cta_url","header":{"type":"image","image":{"id"|"link":..}},
  "body":{"text":..},"action":{"name":"cta_url","parameters":{"display_text":<=20b,"url":<booking_url>}}}}`
- **Template w/ media header (outside-24h path):** `{"type":"template","template":{"name":..,
  "language":{"code":..},"components":[{"type":"header","parameters":[{"type":"image","image":{"id"|"link":..}}]},
  {"type":"body","parameters":[…]}, {"type":"button",…}]}}`

`transports/fake.py` records every call in memory, returns synthetic `wamid`s, **no network** — powers the
offline test and every unconfigured fallback. If `META_WA_*` is unset → `status()=="not_configured"`,
`send_*` returns `{"ok":False,"status":"not_configured"}`, logs one line, never calls out.

---

## 5. ASYNC-JOB PATTERN (media gen results return automatically)

The slow part is **asset GENERATION** (the sibling image/video/brochure jobs), not the send. The pattern:

- **`assemble_kit()` delegates to the siblings' own async-job machinery.** `creative/image` and
  `creative/video` already return jobs whose results land in `var/creatives/…` automatically (their
  spec §5). `assemble_kit` requests those assets and, for fast/fake providers, gets bytes immediately;
  for async providers it **polls the sibling's `GET /creatives/batch/{id}`** (bounded by
  `WA_ASSET_POLL_TIMEOUT`) or registers for the sibling's webhook, then proceeds. No new queue/Redis —
  consistent with the in-process choice across the Creative Studio.
- **The HTTP layer is fire-and-forget.** `POST /whatsapp-creatives/send` schedules `assemble_kit` +
  `send_kit` on a FastAPI `BackgroundTask` and returns `{kit_id, status:"accepted"}` immediately;
  completion is written to `var/creatives/wa/<kit_id>/result.json` and `index.jsonl`. The UI polls
  `GET /whatsapp-creatives/{kit_id}`.
- **The POST-CALL trigger is itself fire-and-forget** — `send_creative_package` is awaited as a
  best-effort task off the call loop (exactly how caller.py already treats `_wa_ai_followup`), so a slow
  asset render never blocks the voice pipeline. NEVER raises into the loop.
- **Crash-safety:** the kit manifest is written incrementally; assets already produced are reused on
  retry (idempotent by `variant_id` + asset `role`). An uploaded `media_id` is cached (90-day Meta TTL)
  so a re-send doesn't re-upload. **A `media_id` is scoped to the sending `phone_number_id`, not global**
  — key the upload-once cache by `(phone_number_id, file_sha)` so it stays correct if multi-tenant ever
  uses multiple WhatsApp numbers.

---

## 6. GUARDRAILS — RIGHT-SIZED for a WhatsApp SENDER (not the ads $-cap)

This is **not** the ads module, so it does **not** carry a per-image spend ceiling. The controls that
actually matter for sending customer-facing creative over WhatsApp (mirroring the brochure spec's
"distribution gate" reasoning):

1. **OPT-OUT / SUPPRESSION — enforced BEFORE every send (the control a naive copy would miss).**
   `suppression.py` checks the same suppression store + `_WA_OPTOUT_WORDS` semantics caller.py already
   uses (`stop`, `unsubscribe`, `band karo`, …). If the contact opted out → `status="suppressed"`,
   **no send**, audited `wa_creative.suppressed`. **Legal + trust requirement, non-negotiable.**

2. **APPROVAL GATE before SENDING customer-facing creative (off by default).**
   `WA_CREATIVE_REQUIRE_APPROVAL=1` → the kit is held in `var/creatives/wa/pending/<kit_id>.json` and
   `send_kit` returns `{"status":"pending_approval"}`; a later
   `POST /whatsapp-creatives/{kit_id}/approve` (manager role) releases it. **`fake`/dry-run jobs skip the
   gate** so today's testing is never blocked. This is the ad-/distribution-approval control the brief asks for.

3. **SEND-RATE CAPS — `budget.py`.** Per-tenant `WA_CREATIVE_DAILY_SEND_CAP` (default e.g. 500) +
   `WA_CREATIVE_PER_MIN_CAP` (anti-blast throttle). Over cap → `{"status":"over_rate"}`, no send, audited.
   Protects WhatsApp quality rating (which a spammy blast would tank) and spend. **Per-contact restraint:**
   a kit can hold 5–6 assets, but firing six separate messages at one person hurts quality rating and (on
   the template path) multiplies cost. The composited **card already carries price + booking-link + logo**,
   so the default send is **few messages** (e.g. card-as-CTA-header + brochure document), not all six;
   `WA_CREATIVE_MAX_MSGS_PER_CONTACT` (default ~3) clamps it.

4. **CONVERSATION-COST METERING — `meter.py` (mirrors `vendors/groq_meter.py`).** 2026 WhatsApp is
   **per-message** billed by **category**; we meter the **category the send actually used**, not a per-image $:
   - **open session** (contact already messaged us) → free-form **SERVICE = ₹0** (free).
   - **closed session** (cold post-call — the common case) → an **approved template** opens it:
     **MARKETING** ≈ **₹0.86** (India, Jan 2026) or **UTILITY** ≈ **₹0.11–0.145** per the template's category.
   The category is decided by `session_open()` detection (§3), not assumed — so the metered cost is honest.
   After each send, append a usage event so WhatsApp spend shows in the existing billing UI:
   ```json
   {"ts":"<IST>","vendor":"whatsapp_creative","category":"service","tenant_id":"<t>",
    "kit_id":"<k>","batch_id":"<b>","variant_id":"<v>","assets":4,"messages":2,
    "unit":"message","est_cost_inr":0.0,"estimated":true}
   ```
   `wa_creative_meter.summarize(usage_events)` sums `vendor=="whatsapp_creative"` rows → same shape the
   other meters expose. Rates overridable via `WA_RATE_MARKETING_INR` / `WA_RATE_UTILITY_INR`;
   `WA_USD_INR` for FX. Every cost flagged `estimated:true` (honest — like the Groq meter).

5. **AUDIT every send/suppress/approve — `audit_hook.py`.** Best-effort import of `droplet_work/audit.py`;
   `record(action="wa_creative.send"|"wa_creative.suppressed"|"wa_creative.pending_approval"|
   "wa_creative.refused_rate", object_type="creative", object_id=kit_id, channel="whatsapp",
   meta={angle,assets,category,est_cost_inr,variant_id})`. No-op if audit.py absent. Secrets NEVER logged.

6. **Safety prefilter (cheap, local).** Before send, a small denylist blocks obviously disallowed
   captions/claims (explicit, hateful, "guaranteed returns"/RERA-risky real-estate claims flagged for
   human review) → `status="blocked"`, no send, audited. First-line only, not a substitute for Meta's
   own policy review.

---

## 7. STORAGE & DATA (`storage.py`) — `var/creatives/wa/`

```
/opt/famit-agent/var/creatives/wa/
  <kit_id>/
    spec.json           # normalized WaKitSpec
    kit.json            # the WaKit (assets w/ roles, caption, cta_url, batch/variant ids)
    result.json         # the WaSendResult (message_ids, category, cost)
    card.png            # the composited price+logo+booking-card (Pillow output; the new bytes we own)
    (sibling assets referenced by path/URL — NOT copied; banner/brochure/video live in their own dirs)
  pending/<kit_id>.json # only when the approval gate holds a kit
  media_cache.json      # {file_sha -> media_id, uploaded_at} (upload-once cache; 90-day TTL)
  status/<wamid>.json   # delivery/read/click events from the status webhook (per-variant analytics)
  index.jsonl           # append-only one-line-per-kit index (tenant, angle, batch_id, variant_id, category, cost, ts)
```
- `kit_id` = time-sortable `YYYYMMDD-HHMMSS-<rand>` (IST). Dirs created lazily; failures swallowed
  (best-effort, like `audit.py`) and downgrade `status` to `error:storage` without raising.
- We **do not duplicate** sibling bytes — the kit references the image/brochure/video by their existing
  `var/creatives/...` path/URL; only the **composited card** (our own output) is written here.
- Listing reads `index.jsonl` newest-first with offset/limit, tenant-scoped — same shape as `audit.tail()`.

---

## 8. HOW IT CONNECTS TO THE REST (ads / leads / CRM / voice / WhatsApp / analytics)

This module is the **WhatsApp delivery head** of the revenue loop. It does not edit the spine; it produces
tagged sends and exposes functions the orchestrator wires.

- **← Voice (caller.py).** **The headline integration.** After an `interested`/`callback` AI voice call,
  caller.py (~line 1248, the existing `_wa_ai_followup` gate) currently sends only **text**. The
  orchestrator adds a deferred call to **`send_creative_package(tenant_id, contact, outcome, camp_fields)`**
  right after that gate to also send the **banner + brochure + price + booking-link** kit. It **detects**
  the WhatsApp session: open session (contact already messaged us) → free-form (free SERVICE); otherwise —
  the common cold case, since a **voice call does NOT open the WA 24h window** — it opens with an **approved
  media-header template** (billed, needs cred #2). Either way it seeds the same WhatsApp thread caller.py
  manages, so an inbound reply continues the chat. Dormant-safe; never raises into the loop. **DO NOT edit
  caller.py here — wiring is the orchestrator's one-line `await`.** (caller.py's existing `_wa_ai_followup`
  carries the same optimistic "inside 24h" comment; `session_open()` detection is the correct behaviour to
  converge on.)
- **→ WhatsApp pipeline.** Reuses the founder's existing Meta Cloud API creds (`META_WA_*`) and the
  thread/opt-out machinery; this module only adds the media/interactive send shapes.
- **→ Autonomous Ads.** WhatsApp is itself a test surface: `assemble_angles(n=5)` produces the **"5
  WhatsApp angles"** as `variant_id`-tagged kits. The ads/analytics layer reads back which angle drove
  delivered/read/click/booking, keyed by `variant_id`, to scale the winning angle (closing the loop).
- **→ Leads / CRM.** Every send is logged with `tenant_id` + `campaign_id` + `variant_id` + contact phone,
  so the CRM attributes a booking back to the exact WhatsApp creative that drove it. CTA-URL clicks
  (status webhook) become lead-intent signals.
- **→ Analytics / Billing.** Per-send `usage_events` rows (`vendor:"whatsapp_creative"`) flow into the
  existing billing meter → the multi-tab billing UI (WhatsApp spend beside Groq/ElevenLabs/Vobiz).
  Delivery/read/click counts flow into the analytics dashboard, joinable on `variant_id`.
- **← Creative siblings.** Pulls bytes from `creative/image`, `creative/brochure`, `creative/video` via
  their public `generate*` APIs; degrades gracefully (skips that asset) if a sibling is not_configured.
- **`context.py`** is the dropdown bridge: given `tenant_id` + `product_id` + `campaign_id` it loads the
  vendor's stored business profile / product price / booking URL / brand kit (best-effort, dormant if the
  store isn't reachable) so "pick a product → get a ready WhatsApp kit" works.

---

## 9. ENDPOINTS (designed now, **wired later by the orchestrator** — DO NOT edit `caller.py`)

| Method/Path | Body / Query | Returns | Notes |
|---|---|---|---|
| `POST /whatsapp-creatives/assemble` | `WaKitSpec` JSON | `WaKit` | dropdown→kit; dormant-safe; `fake` siblings when unconfigured |
| `POST /whatsapp-creatives/angles` | `WaKitSpec` + `?n=5` | `WaBatchResult` | the "5 WhatsApp angles" testing batch |
| `POST /whatsapp-creatives/send` | `{kit_id|spec, to, inside_window}` | `{kit_id,status:"accepted"}` | async; suppression+gate+rate enforced |
| `GET /whatsapp-creatives/{kit_id}` | – | `WaKit` + `WaSendResult` | poll surface |
| `POST /whatsapp-creatives/{kit_id}/approve` | – | `WaSendResult` | only when approval gate on; manager role |
| `GET /whatsapp-creatives/status` | – | `status()` dict | transport + sibling readiness, caps |
| `GET /whatsapp-creatives` | `?limit&offset&batch_id` | list from `index.jsonl` | newest-first, tenant-scoped |

Status webhooks (`sent/delivered/read/failed` + CTA clicks) arrive on the **existing**
`caller.py` `/whatsapp/inbound` webhook; the orchestrator routes status payloads to `ingest_status()`.
All write/send/approve paths call `audit_hook`. Auth/tenant scoping reuses `auth.py` middleware.

---

## 10. REAL-vs-HYPE (honest, no overclaim)

**Real in 2026 (ship it):** native WhatsApp image/document/video sends + interactive CTA-URL booking
button with a media header (Meta Cloud API); deterministic, pixel-exact price/logo/booking-card via
Pillow (we composite — we don't ask a model to bake the price); free post-call sends inside the 24h
window; per-variant delivery/read/click analytics; reuse of proven sibling generators.

**Hype / needs a human (the approval gate exists for this):** "one click → a finished, on-brand,
compliant WhatsApp campaign with zero human" — no. Brand-exact lockups beyond logo+price → human review.
Marketing-template approval is **Meta's** gate (templates must be pre-approved by Meta before the
outside-window path works) — we cannot conjure an approved template; the founder registers them. Claims
(RERA, "guaranteed returns", competitor mentions) → human/legal review; the safety prefilter is
first-line only. WhatsApp **quality rating / messaging limits** are Meta-governed — blasting lowers them;
the rate caps + opt-out enforcement protect the number, but a human still owns campaign cadence.

**Positioning:** a WhatsApp creative-kit assembler + compliant sender with opt-out enforcement, send-rate
caps, and a human approval gate — auto-firing the right package after an interested voice call — **not** a
fire-and-forget mass blaster.

---

## 11. OFFLINE ACCEPTANCE TEST (`tests/test_whatsapp_creative_offline.py`) — ZERO external calls

```
pytest droplet_work/creative/whatsapp/tests/test_whatsapp_creative_offline.py -q
# or:  python -m droplet_work.creative.whatsapp.tests.test_whatsapp_creative_offline
```
Runs on any Python 3.11+; **no keys, no network**. Uses the `fake` transport + the siblings' `fake`
generators. Exits non-zero on any failure (CI-gateable).

**Assertions (each maps to a guarantee above):**
1. **Dormant-safe:** all WA + sibling env unset → `status()["status"]=="not_configured"`;
   `transports_status()` shows `meta` `"not_configured"`, `fake` `"configured"`. **Nothing raises.**
2. **Assemble via fakes:** `assemble_kit(WaKitSpec(product_id="p1", include=["banner","brochure"]))` →
   `ok=True`, a composited `card.png` exists in `var/creatives/wa/<kit_id>/` (PNG magic-byte check), kit
   manifest written, missing/unconfigured siblings skipped (not fatal).
3. **Compose layer (pure, offline):** `compose.overlay(base_png, price="₹49,999", booking_url=..,
   logo=..)` returns a valid PNG with deterministic output (same inputs → same bytes / same size); no network.
4. **Angles batch:** `assemble_angles(WaKitSpec(...), n=5)` → `produced==5`, each kit a unique
   `variant_id` + distinct `angle`, no send performed.
5. **Send via fake transport — BOTH session paths via detection:**
   (a) **open session** (`session_open` faked True, or `inside_window=True`) → `status=="sent"`,
   `category=="service"`, `est_cost_inr==0.0`, free-form media + interactive CTA sent; fake transport
   recorded the exact bodies (image has caption, document has filename, interactive has cta_url ≤ button-limit).
   (b) **closed session** (`session_open` faked False, default detection) → the sender takes the **template
   path**: `transport.send_template` called with a media header + CTA button, `category=="marketing"`,
   `est_cost_inr>0`. A `131047`-style transport error on a free-form send to a no-session contact is handled
   (status surfaced, never raised). `result.json` written in both cases.
6. **Upload-once cache:** sending the same kit to two recipients calls `transport.upload` **once** per
   asset (media_cache hit on the 2nd) — spy asserts a single upload per file SHA.
7. **Suppression gate (the must-not-miss control):** mark `+9199...` opted-out → `send_kit` →
   `status=="suppressed"`, transport `send_*` **never called** (spy), audited `wa_creative.suppressed`.
8. **Approval gate:** `WA_CREATIVE_REQUIRE_APPROVAL=1` + configured (faked) transport →
   `status=="pending_approval"`, `var/creatives/wa/pending/<kit_id>.json` exists, transport NOT called;
   then `approve()` → `status=="sent"`.
9. **Rate cap:** daily cap = 1, send twice → 2nd `status=="over_rate"`, transport not called, audited.
10. **Meter:** a marketing-template send (outside window, faked) writes a `usage_events` row
    `vendor=="whatsapp_creative"`, `category=="marketing"`, `est_cost_inr≈0.86`; a service send writes
    `est_cost_inr==0.0`; `wa_creative_meter.summarize([...])` sums them; `estimated is True`.
11. **Status webhook → analytics:** `ingest_status({delivered/read/click for variant v})` updates the
    per-variant counters in `var/creatives/wa/status/`; `read` and CTA-`click` counted under `variant_id`.
12. **Safety prefilter:** a denylisted caption → `status=="blocked"`, no send, audited.
13. **Never-raises fuzz:** malformed inputs (empty spec, unknown asset kind, missing phone, n=999,
    non-dict, oversized caption/cta_text) → each returns a `WaKit`/`WaSendResult` with an
    `invalid`/clamped status, **no exception**.

All "configured"/"paid" cases use the `fake` transport + monkeypatch → **no real HTTP**. The whole
pipeline (enrich → assemble → compose → suppress → gate → send → meter → audit → store) runs with **zero
credentials and zero network**.

---

## 12. BUILD ORDER (small verifiable units, no git)

1. `types.py` + `transports/base.py` + `transports/fake.py` + `__init__.py` skeleton → tests #1, #5 (send shape).
2. `compose.py` (Pillow overlay) → tests #2 (card), #3.
3. `assemble.py` + `angles.py` (delegating to sibling `fake` generators) → tests #2, #4.
4. `suppression.py` + `budget.py` (approval + rate) → tests #7, #8, #9.
5. `meter.py` + `audit_hook.py` → tests #10, #12.
6. `media_upload.py` + `asset_url.py` + upload-once cache → test #6.
7. `storage.py` + `index.jsonl` + `status_hook.py` → tests #2, #11.
8. `transports/meta.py` (native Meta media/interactive/template; dormant; HTTP via `_http` helper) →
   `transports_status()` shape, real send shapes built (asserted via fake-equivalence).
9. `context.py` (dropdown enrichment, best-effort/dormant) + `trigger.py`
   (`send_creative_package` post-call entrypoint).
10. Run the full offline test → green → STOP (orchestrator wires endpoints + the caller.py ~1248 call + commits).

---

## 13. EXACT CREDENTIALS / ACCOUNTS THE FOUNDER MUST PROVIDE

**The module runs and is fully testable with NONE of these (dormant-until-creds).** It also **inherits**
the WhatsApp creds already documented for `whatsapp.py` — if WhatsApp is live for the voice follow-up, the
**core send path is already credentialed**; only the sibling generators need their own keys for richer kits.

| # | What to get | Env var(s) | Where / how (founder steps) | Needed for | Cost |
|---|---|---|---|---|---|
| 1 | **Meta WhatsApp Cloud API** (ALREADY the founder's BSP) | `META_WA_PHONE_NUMBER_ID`, `META_WA_TOKEN`, `META_WA_BUSINESS_ACCOUNT_ID`, `META_WA_VERIFY_TOKEN`, `META_WA_APP_SECRET` | Meta Business / WhatsApp Manager → app → system-user permanent token + phone-number-id (same as whatsapp.py) | **All WhatsApp sends** (media, interactive, template) | per-message: service=free, marketing≈₹0.86, utility≈₹0.11–0.145 (India 2026) |
| 2 | **Approved template(s)** w/ media header + CTA button | (none — Meta-side) `WA_CREATIVE_TEMPLATE_*` (template names) | WhatsApp Manager → Message Templates → create + submit for Meta approval | **Any send to a contact with NO open WhatsApp session** — i.e. the cold post-call case (a voice call does NOT open the window) AND all campaign blasts. Only sends to a contact who already messaged us can skip this | template approval is free; sends billed per category (marketing ≈₹0.86 / utility ≈₹0.11–0.145) |
| 3 | **Public asset host** (for link-mode media) | `WA_ASSET_BASE_URL` (e.g. the Cloudflare-fronted panel domain) | Point at the existing `/creatives/{job}/asset` route (already Cloudflare-fronted per FORTRESS) | link-mode sends (alternative to upload→media_id) | free (uses existing infra) |
| 4 | **Sibling generator keys** (optional — richer kits) | `IDEOGRAM_API_KEY` / `RECRAFT_API_KEY` / `OPENAI_API_KEY` / `FAL_KEY`… (image); brochure + video keys | per `creative-image-banner-studio.md` §12 etc. | banner/card/offer/brochure/video bytes (else kit degrades to text+composited card from stored photos) | per their specs |
| 5 | **Guardrail caps (recommended, not secret)** | `WA_CREATIVE_DAILY_SEND_CAP`, `WA_CREATIVE_PER_MIN_CAP`, opt `WA_CREATIVE_REQUIRE_APPROVAL=1`, `WA_RATE_MARKETING_INR`, `WA_RATE_UTILITY_INR`, `WA_USD_INR` | set in `/opt/famit-agent/.env` | – | send-rate caps / approval gate / meter rates | free |

> **Recommended minimum:** **#1 is already present** if the WhatsApp voice follow-up is live, so the
> machinery (assemble → Pillow-composited card → send) works **today** with no new keys. **But** the
> headline auto-send-after-a-call reaches a **cold** contact (a voice call does NOT open the WhatsApp 24h
> window), so to actually **deliver** that kit you need **#2 — one approved media-header template** (free to
> create; sends billed per category). Without it, the post-call send only reaches contacts who already
> messaged your WhatsApp number. Add **#4** to enrich kits with AI-generated banners/videos.

**Sources (2026 web research):**
- https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media/  (media: link vs media_id; 90-day storage; upload-once)
- https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-cta-url-messages/  (CTA-URL button + media header; ≤20-byte button, ≤1024-char body, single URL)
- https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing  (per-message pricing; categories)
- https://www.blueticks.co/blog/whatsapp-business-api-pricing-2026  (2026 per-message model, service-window free)
- https://uniquedigitaloutreach.in/2026/02/16/whatsapp-business-api-pricing-in-2026-a-complete-guide/  (India Jan-2026 marketing ≈₹0.86, utility ≈₹0.11–0.145)
- https://zernio.com/blog/whatsapp-api-tutorial-how-to-send-messages-and-templates  (2026 media/template send shapes)
- https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html  (Pillow 12.x ImageDraw/composite — the offline overlay layer)
- (reused, in-repo) `droplet_work/whatsapp.py` (native Meta config), `vendors/_http.py`, `vendors/groq_meter.py`, `audit.py`, `caller.py` `_wa_ai_followup`/`_WA_OPTOUT_WORDS`
```

---

## RED-TEAM FIXES (folded)

> Adversarial review 2026-06-09. Every in-repo reuse claim was verified against live source; every
> volatile WhatsApp/Meta fact was re-checked on the 2026 web. **Verdict: GO** (dormant, non-breaking,
> honestly scoped). The items below are folded corrections + the residual risks the build agent and
> the founder must carry. Nothing here blocks the build.

### A. VERIFIED TRUE (kept as-is — recorded so a future reviewer needn't re-dig)
- **Every reused in-repo symbol exists with the claimed shape:** `whatsapp.meta_configured()` /
  `_meta_cfg()` / `_meta_url()` / `is_configured()` (whatsapp.py:101/89/115/107); `vendors._http.request_json`
  (_http.py:16); `vendors.redact` (vendors/__init__.py:26); `audit.record(actor, action, object_type=,
  object_id=, channel=, meta=)` (audit.py:60) + `audit.tail` (102); `groq_meter.summarize(usage_events)`
  (groq_meter.py:27) + `status()`; `caller._WA_OPTOUT_WORDS` (caller.py:1087); `_wa_ai_followup`
  (caller.py:1247, called at 1578). Sibling `creative/image` exposes `generate(ImageBrief)` and the
  `GET /creatives/batch/{id}` poll surface this spec polls (image spec:173/351). **All reuse claims hold.**
- **The central factual correction is grounded in a REAL code defect, not just doctrine.** `caller.py:1267`
  literally reads `# Free-form text inside the (just-ended call -> within 24h) CS window.` — the live code
  *assumes* the call opened the window. Web-verified: Meta error **131047 "re-engagement required"** fires
  on a free-form send when >24h since the contact's **last inbound WhatsApp message**; the window is opened
  by an *inbound WhatsApp message* (or click-to-WA ad), never by telephony. So this spec's session-detection +
  template-fallback design is correct **and** it documents a bug the orchestrator should fix at the wiring
  site (caller.py:1267 comment + its optimistic text path). Flagged, not silently inherited.
- **External rate-card sanity-checked:** per-message billing since 2025-07-01 ✓; service=free, India
  marketing ≈ $0.0094/msg (≈₹0.81 at ~₹86/USD — the spec's ₹0.86 is fine/slightly conservative), utility
  range covers the spec's ₹0.11–0.145 ✓. CTA-URL: body+action required, header optional (image/video/
  document/text), button text ≤20 bytes, single URL button ✓. 90-day media storage ✓. All flagged
  `estimated:true`, which is honest.

### B. CORRECTIONS FOLDED
1. **WhatsApp has FOUR billable categories, not three.** The meter (§6.4) models `service|marketing|utility`
   only. Meta's fourth category is **AUTHENTICATION** (OTP templates). This module never sends auth
   templates, so omission is acceptable — **but `meter.py` MUST treat an unrecognized category as
   `estimated:true, est_cost_inr=0.0, category:"unknown"` and still write the row** rather than KeyError or
   silently drop it, so a future auth-template send can't crash the meter. (Defensive default, not a new feature.)
2. **`audit.record()` requires a positional `actor` as its FIRST arg.** §6.5 shows
   `record(action=…, object_type=…, …)` with no actor. `audit_hook.log(...)` MUST pass
   `actor=tenant_id` (the data-owner id) as the first positional, e.g.
   `audit.record(tenant_id, "wa_creative.send", object_type="creative", object_id=kit_id,
   channel="whatsapp", tenant_id=tenant_id, meta={…})`. Without an actor the call is malformed. Wiring
   detail; audit is best-effort/never-raises so it won't crash, but it would log a blank actor — fix it.
3. **The post-call send IS an autonomous-money action — name it as such.** The brief's "autonomous ad spend
   safety" concern lands HERE: when `send_creative_package` hits a **cold** contact (the common case, since
   a voice call doesn't open the window) it auto-fires a **billed MARKETING template (≈₹0.86)** with no human
   in the loop by default (`WA_CREATIVE_REQUIRE_APPROVAL` is off-by-default). Per call that is small; across
   an autonomous campaign it is real, unbounded-by-$ spend. **Folded mitigations the build agent MUST honor:**
   (a) the rate caps (`WA_CREATIVE_DAILY_SEND_CAP`, `WA_CREATIVE_PER_MIN_CAP`) are the de-facto spend ceiling
   — enforce them on the **template path specifically**, since that is the only path that costs money;
   (b) add an **optional hard rupee ceiling `WA_CREATIVE_DAILY_COST_CAP_INR`** (default unset/∞) checked in
   `budget.py` against the day's metered template cost — over it ⇒ `status="over_rate"`, no send, audited.
   This gives the founder a true money stop-loss without turning this into the ads module. The free SERVICE
   path (open session) is uncapped-by-cost because it is genuinely ₹0.
4. **ToS / consent posture made explicit.** Auto-sending a **marketing** template to a contact who only ever
   spoke on a *phone call* and never opted into WhatsApp marketing is a **policy + DLT/consent risk** (Meta
   marketing-category rules + India DLT/DND for promotional messaging). Mitigation already in-spec (opt-out
   suppression before every send, safety prefilter, human approval gate) is correct **but the default should
   bias safe**: when the post-call contact has **no prior WhatsApp opt-in on record**, prefer a **UTILITY**
   framing (booking confirmation / "you asked us to send details on the call") over MARKETING where the
   content legitimately qualifies — utility is ~6–8× cheaper AND lower policy-risk. The category decision
   must be driven by genuine message intent, never chosen just to dodge cost (mis-categorization is itself a
   Meta violation). `context.enrich` should surface a `wa_marketing_optin` flag; absent it, do not send a
   MARKETING template autonomously — hold for approval.

### C. RESIDUAL RISKS (carried — accept with eyes open)
- **R1 — Template approval is Meta's gate and is NOT dormant-testable.** The headline auto-send to a cold
  contact is *undeliverable* until the founder creates AND Meta approves a media-header template (cred #2).
  The offline test proves the *send shape*, never real delivery. Honestly disclosed in §10/§13; just don't
  let "tests green" read as "post-call delivery works." **It works only once #2 is approved.**
- **R2 — `media_id` scoping unconfirmed by primary doc, but design is safe either way.** Web search confirmed
  90-day storage but did not surface an authoritative line on per-phone-number-id scoping. The spec already
  keys the upload-once cache by `(phone_number_id, file_sha)` — strictly safe whether scoping is per-number
  or global (over-keying only ever causes a redundant re-upload, never a wrong-number send). No action.
- **R3 — Link-mode media requires a PUBLIC HTTPS host (`WA_ASSET_BASE_URL`).** Per FORTRESS the panel is
  egress-locked + Cloudflare-fronted; exposing a `/creatives/{job}/asset` route publicly must not leak other
  tenants' assets. Default to **upload→media_id** (already the spec's default) so link-mode — and its
  public-exposure surface — stays off unless the founder explicitly opts in. Treat `asset_url.py` as the
  tenant-isolation chokepoint: it must refuse to emit a public link for an asset outside the caller's tenant.
- **R4 — 3D sibling is mentioned but not wired (correctly).** §0/§1 list "3D" only as a Creative-Studio
  sibling for context; this module never requests 3D assets (WhatsApp has no native 3D message type). That is
  the right call — 3D-over-WhatsApp would be hype. No GLB/USDZ is sent; a 3D *render* would arrive only as an
  ordinary image/video via the image/video siblings. Kept as-is; flagged so no one "adds 3D delivery" later.
- **R5 — Autonomous bidding is OUT of scope and stays out.** This module produces `variant_id`-tagged kits
  and emits delivery/read/click signals; it does **not** bid, allocate budget, or scale spend. The ads engine
  owns that. The spec is honest (§6 opener, §8 "→ Autonomous Ads", §10). Do not let `assemble_angles(n=5)`
  drift into auto-launching paid sends — it returns kits for review/attribution, never sends.
- **R6 — Per-contact message-cap vs. the 6-asset kit.** `WA_CREATIVE_MAX_MSGS_PER_CONTACT` (~3) is the right
  instinct; ensure it is enforced **before** the meter so a clamped kit is also billed-as-clamped, and that
  the composited card (price+link+logo in one image) is always preferred over firing six separate messages —
  both for quality-rating and (template path) cost. Already in §6.3; just don't regress it.

### D. GO / NO-GO
**GO.** The module is dormant-until-creds, never-raises, edits no spine file, reuses only verified symbols,
and its async/fire-and-forget pattern matches the existing `_wa_ai_followup` best-effort-off-the-call-loop
model. The single factual error a naive build would inherit (call opens the WA window) is corrected here AND
traced to the live bug at `caller.py:1267`. Real-vs-hype is honest (no 3D-over-WhatsApp, no autonomous
bidding, template approval owned by Meta + founder). Build it; fold corrections B1–B4; carry residual risks
R1–R6. The only true money-spend surface (autonomous billed templates) is now bounded by rate caps + an
optional rupee stop-loss + a consent-aware category default.
