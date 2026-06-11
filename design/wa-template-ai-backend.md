# DESIGN SPEC — WHATSAPP **AI TEMPLATE-GENERATION BACKEND** (`whatsapp-builder`)

> **Status:** EXECUTION-READY DESIGN (READ-ONLY wave — this doc writes NO app code, edits no
> `caller.py`/`agent.py`/`whatsapp.py`, does NO git). It specifies the **AI brain** that, when a vendor
> selects a campaign in the WhatsApp Campaign Builder, **auto-generates** WhatsApp **template suggestions,
> message variations, CTAs, personalization tokens, media recommendations, and campaign structures** —
> from the campaign's objectives / audience / offer / products / business-context / brand — and then
> **validates** every output against **Meta's WhatsApp template-format + category rules** before it can be
> submitted, sent, or attached to a Creative-Studio banner.
>
> **Date:** 2026-06-11. Grounded in live code under `C:\Users\kunal\Desktop\caps\droplet_work\` and the
> shipped sibling design docs. **Reuse discipline:** this doc adds **no new LLM client, no new WhatsApp
> client, no new money path, no new asset store** — it CONTRACTS a thin generation layer on top of the
> already-live primitives (the Groq/OpenRouter LLM seam, `whatsapp.py`, `wallet.py`, `audit.py`, the
> Asset Library, the `creative.*` contract).

---

## 0. THE ONE-PARAGRAPH MODEL (read first)

A vendor picks a campaign in the WhatsApp Campaign Builder. The backend loads that campaign's stored
business data (`Org` profile, `Campaign` row, products, offer, audience segment, brand kit), assembles a
**read-only generation context**, and calls the **existing LLM seam** (Groq → OpenRouter fallback) **once**
with a strict, schema-constrained prompt carrying the **master-spec NO-INVENT guardrails**. The model
returns a **proposal bundle**: 3–5 WhatsApp **template suggestions** (each a Meta-compliant
header/body/footer/buttons skeleton with `{{1}}`/`{{2}}` placeholders), per-template **message variations**
(angle-labeled: benefit / urgency / social-proof / offer / trust …), **CTA recommendations** matched to the
campaign goal, a **personalization-token plan** (`name` / `city` / `lead_stage` / `product` → which
placeholder maps to which lead field), **media recommendations** (what banner kind to attach, routed to the
`creative.*` contract — never generated here), and a **campaign structure** (sequence of templates across
lead stages + suggested timing). **Every** generated template is then passed through a deterministic
**Meta-compliance validator** (the model is INPUT, the validator is AUTHORITY) that enforces the 2026 Cloud
API template grammar and **auto-classifies the Meta category** (MARKETING / UTILITY / AUTHENTICATION). The
bundle is **stored draft, credit-gated, RLS-scoped, audited**; nothing leaves the builder until a human (or
an explicit auto-mode toggle) **approves** it, at which point it can be submitted to Meta for template
approval, attached to a Creative-Studio banner, and sent via the live `whatsapp.py` path. The whole thing is
**dormant-until-creds** (no LLM key → deterministic templated fallback; no Meta token → generate+store-only)
and **fully offline-testable**.

```
 vendor picks a campaign  ──►  whatsapp-builder.generate_templates(campaign_id)
                                        │
            ┌───────────────────────────┼────────────────────────────────────┐
            ▼                           ▼                                      ▼
   context.build(campaign_id)   wallet.reserve(gen credits)         performance_summary (library)
   (Org/Campaign/products/       (idempotent, INR paise)            (winning angle/CTA bias — §7)
    offer/audience/brand)                │
            └───────────────┬────────────┘
                            ▼
              LLM seam (Groq → OpenRouter)  ──schema-constrained, NO-INVENT──►  raw proposal JSON
                            │
                            ▼
              META-COMPLIANCE VALIDATOR (deterministic — the authority)
              · grammar (header/body/footer/buttons, {{n}} placeholders, char limits)
              · category auto-classify (MARKETING | UTILITY | AUTHENTICATION)
              · personalization-token → lead-field binding (name/city/lead_stage/product)
              · NO-INVENT scrub (no fabricated price/RERA/discount/claim)
                            │
                            ▼
         ai_wa_templates / ai_wa_variations / ai_wa_personalization / ai_wa_suggestions
         (status=draft, FORCE-RLS ai_wa_* schema)  ──audit channel="whatsapp_builder"──
                            │
        list / select / approve  ──(human or auto-mode)──►  submit-to-Meta · attach banner (creative.*) · send (whatsapp.py)
```

---

## 1. WHERE THIS LIVES (the placement decision)

**Decision: a thin `whatsapp-builder` MODULE inside the monolith, NOT a new service.** Rationale, against
the project's exact constraints:

- It is **pure orchestration of things that already exist** — the LLM seam, `whatsapp.py` config, the Asset
  Library / `creative.*` contract, `wallet.py`, `audit.py`. It owns **no GPU, no long render queue, no
  provider fleet** (that is the **AI Asset Service**, which is correctly a dedicated service). A template is
  a few KB of JSON the LLM returns in one call — there is nothing to extract into its own process.
- The DO droplet limit is **3/3 full** (memory: Hatchet box used the 3rd). A new service has nowhere to run.
- The **AI-Manager precedent** is in-process composition (`mod-ai-manager.md`: in-process, not cross-plane
  HTTP). The builder follows the same pattern: it is a module the monolith mounts, calling the LLM and
  `whatsapp.py` **in-process**, and the Asset Service over the **authenticated localhost loopback** (the only
  cross-service hop, and only for banners).
- It is **co-located with, but distinct from, the existing WhatsApp module.** The live `whatsapp.py` owns
  *send/receive/webhook* (`POST /whatsapp/send`, `GET|POST /whatsapp/inbound` at `caller.py:4313/4352/4406`).
  The `creative/whatsapp/` module owns *packaging + media delivery* (`creative-whatsapp-creative.md`). The
  **builder owns *generation + compliance + campaign-structure* only** — the upstream brain. It **imports
  `whatsapp.py`'s config helpers, never edits them** (same rule the creative-whatsapp module follows).

**Code path:** `droplet_work/whatsapp_builder/` (NEW files only; bare imports, no `droplet_work.` prefix —
the deploy root `/opt/famit-agent/` IS the `droplet_work/` contents, per `caller.py:34` convention).

```
droplet_work/whatsapp_builder/
  __init__.py            # PUBLIC API (§3) — generate_templates / list / get / select / approve / submit_status / status
  README.md
  models.py              # Pydantic v2: AiWaTemplate, AiWaVariation, AiWaPersonalization, AiWaSuggestionBundle, GenSpec
  context.py             # READ-ONLY campaign-context builder (Org/Campaign/products/offer/audience/brand) — the dropdown source
  prompt.py              # the schema-constrained LLM prompt (NO-INVENT guardrails baked in) + few-shot per industry pack
  llm.py                 # thin wrapper over the EXISTING Groq/OpenRouter seam (reuse — no new client); JSON-mode, retry, dormant-safe
  generate.py            # orchestrates: context -> wallet.reserve -> llm -> validate -> persist -> settle/release
  validate.py            # DETERMINISTIC Meta-compliance validator + category auto-classifier (the authority) + NO-INVENT scrub
  personalize.py         # personalization-token plan: {{n}} <-> lead field (name/city/lead_stage/product) binding + sample render
  structure.py           # campaign-structure generator (template sequence across lead stages + timing)
  store.py               # ai_wa_* persistence (Postgres FORCE-RLS) + JSONL fallback when DB unreachable (offline-safe)
  credit.py              # wallet.reserve/settle/release wrapper (reuse F4 — no new money path)
  audit_hook.py          # thin -> audit.record(channel="whatsapp_builder"); no-op if absent
  meta_submit.py         # DORMANT submit-template-to-Meta seam (POST /{waba}/message_templates) — no-op without creds
  router.py              # DEFERRED FastAPI APIRouter(prefix="/whatsapp/campaign") — DESCRIBED, orchestrator mounts later
  fixtures/              # canned campaign rows + a golden proposal bundle (for the offline test)
  tests/
    test_builder_offline.py   # the acceptance test — ZERO network, no LLM/Meta key needed
```

---

## 2. THE GENERATION CONTEXT (campaign-aware, NO-INVENT) — `context.py`

`context.build(tenant_id, campaign_id)` assembles a **read-only** dict from stored data ONLY (it never asks
the model to supply facts the platform doesn't have — the master §17/§20 NO-INVENT rule). Sources (all live):

| Context field | Source (live) | Used for |
|---|---|---|
| `business` (name, industry, tone, language) | `db/models.py` `Org:44` | brand voice, industry pack, language |
| `campaign` (objective, goal, offer, audience segment) | `db/models.py` `Campaign:87` | angle selection, CTA, structure |
| `products[]` (name, price, USP, photo) | campaign/product store | body copy, media recommendation, personalization `product` |
| `audience` (lead_stage mix: cold/warm/hot, city distribution) | `db/models.py` `Lead:106` | per-stage variations, `city`/`lead_stage` tokens |
| `brand` (logo, palette, preferred CTA, do-not-use words) | brand-kit (Asset Library `kind=logo` + Org prefs) | tone, banner kind, banned phrases |
| `offer` (price string, discount, validity — **only if stored**) | `Campaign.offer` | offer-angle body — **never invented** |
| `performance_summary` (winning angle/CTA/language for this tenant+industry) | `library.performance_summary` (§7) | bias the generation toward what converted |

**The NO-INVENT contract is enforced in TWO places:** (a) the prompt instructs the model to use ONLY
supplied facts and to emit `{{n}}` placeholders or omit a line when a fact is missing; (b) `validate.py`
**scrubs** any output containing a numeric price / "RERA" / "% off" / "guaranteed" / phone number that is NOT
present verbatim in the context — flagging it `needs_fact` and stripping the fabricated token rather than
trusting the model. The model proposes *structure and style*; it may never *introduce a fact*.

---

## 3. PUBLIC API (the surface the orchestrator wires; `router.py` mounts under `/whatsapp/campaign`)

Auth via the live `resolve_tenant(request)` (`caller.py:551` — **tenant from TOKEN, never body**) +
`can(tenant,"write")` (`caller.py:849`) on mutations. Every mutation calls `audit_hook`. Every generating
call obeys the §5 credit contract. All routes **tenant-scoped**, dormant-safe, never-raise.

| Method · Path | Body / Query | Returns | Money? | Risk | What it does |
|---|---|---|---|---|---|
| **`POST /whatsapp/campaign/{id}/generate-templates`** | `GenSpec` (optional: `n`, `angles[]`, `language`, `include_structure`, `idem_key`) | `AiWaSuggestionBundle` (`{bundle_id, status:"accepted", templates[], variations[], personalization, media_recs[], structure}`) | **yes** (LLM credits) | `spend` | The headline call. Campaign-aware AI generation of templates + variations + CTAs + tokens + media recs + structure. Async-capable (returns `bundle_id`; poll). |
| `GET /whatsapp/campaign/{id}/templates` | `?status&angle&limit&offset` | `SearchPage[AiWaTemplate]` | no | safe | List generated templates for a campaign (newest-first, tenant-scoped). The builder's gallery. |
| `GET /whatsapp/campaign/templates/{tid}` | – | `AiWaTemplate` (+ its variations + personalization plan + a sample render) | no | safe | One template, fully expanded with a **sample personalized preview**. |
| `POST /whatsapp/campaign/templates/{tid}/select` | `{variation_id}` | `AiWaTemplate` | no | safe | Pick the winning variation as the template's active body. |
| `POST /whatsapp/campaign/templates/{tid}/regenerate` | `{mode:"more_like_this"\|"new_angle"\|"simpler"\|"language:<lc>", n}` | `AiWaSuggestionBundle` | **yes** | `spend` | "5 more like this" / new-angle / simpler / translate — a NEW set (originals kept, versioned). |
| **`POST /whatsapp/campaign/templates/{tid}/approve`** | – | `AiWaTemplate` (`status=approved`) | no | `destructive`* | The gate that lets a template leave the builder (submit / attach / send). Mirrors `creative.approve`. |
| `POST /whatsapp/campaign/templates/{tid}/reject` | `{reason}` | `AiWaTemplate` (`status=rejected`) | no | safe | Reject (feeds the §7 learning loop: do-not-repeat). |
| `POST /whatsapp/campaign/templates/{tid}/submit-to-meta` | – | `{status:"submitted"\|"not_configured", meta_template_id}` | no** | `destructive` | DORMANT: submit an **approved** template to `POST /{waba}/message_templates` for Meta approval (cred-gated). |
| `POST /whatsapp/campaign/templates/{tid}/attach-banner` | `{asset_id}` | `AiWaTemplate` | no | safe | Bind an **approved** Creative-Studio asset (`creative.get`, `status=approved`, tenant-checked) as the header media. |
| `GET /whatsapp/campaign/templates/{tid}/meta-status` | – | `{review_status, rejection_reason}` | no | safe | Poll Meta template review status (dormant w/o creds). |
| `GET /whatsapp/campaign/builder/status` | – | `status()` dict | no | safe | `{llm:"ready"\|"not_configured", whatsapp:"...", credits_required, require_approval}`. |

\* `approve` is `destructive` because it is the irreversible "this may now be submitted to Meta and sent to
customers" gate — it gets a step-up posture in auto-flows (mirrors the `creative.approve` / WhatsApp
send-approval gates). \*\* `submit-to-meta` spends nothing (template approval is free); the eventual **send**
carries its own per-message cost on the `whatsapp.py` path — **never double-charged here**.

### 3.1 As a workforce `ToolSpec` (AI-Manager + Workflow nodes — reuse, do not duplicate)

The same generation is registered ONCE as `whatsapp.generate_templates` in the AI-Manager/`ai-workforce`
`ToolRegistry` (money/`spend` risk metadata), so voice ("make WhatsApp templates for the Diwali campaign")
and Workflow **Action nodes** hit the **same module, same risk table, same wallet path, same audit channel**.
No second generation door. (This mirrors how `creative.*` is exposed as both tools and HTTP routes in
`creative-studio-integrations.md` §1.)

---

## 4. DATA MODEL (`ai_wa_*` Postgres schema — FORCE-RLS, admin-GUC; JSONL fallback offline)

Follows the **exact** live RLS pattern from `db/ddl_wallet.sql` (admin-GUC escape hatch, `famit_app`
NOSUPERUSER/NOBYPASSRLS, `FORCE ROW LEVEL SECURITY`, idempotent `CREATE ... IF NOT EXISTS`, applied
standalone like `ddl_wallet.sql` — off the live Alembic chain). `tenant_id TEXT == org_id`. Timestamps =
IST ISO. With no DB reachable, `store.py` falls back to `var/whatsapp_builder/*.jsonl` (offline-safe, the
established `index.jsonl` shape) so the offline test needs zero Postgres.

### 4.1 `ai_wa_suggestion_bundles` — one generation run (the proposal envelope)
```
bundle_id        TEXT PRIMARY KEY   -- "wab_<uuid4hex>"
tenant_id        TEXT NOT NULL      -- == org_id (RLS key)
campaign_id      TEXT NOT NULL
spec             JSONB              -- the GenSpec used (n, angles, language, include_structure)
context_digest   JSONB              -- redacted snapshot of the campaign context the LLM saw (provenance)
model            TEXT               -- "groq:llama-3.x" | "openrouter:<model>" | "fallback:templated"
status           TEXT NOT NULL DEFAULT 'draft'  -- draft|partial|generated|error
credit_hold_id   BIGINT NULL        -- the wallet hold (F4)
estimate_minor   BIGINT             -- reserved credits (INR paise)
actual_minor     BIGINT             -- settled credits
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

### 4.2 `ai_wa_templates` — one Meta-shaped template skeleton (the core record)
```
template_id      TEXT PRIMARY KEY   -- "wat_<uuid4hex>"
tenant_id        TEXT NOT NULL      -- RLS key
campaign_id      TEXT NOT NULL
bundle_id        TEXT NOT NULL      -- parent generation run
name             TEXT               -- snake_case, <=512 chars, [a-z0-9_] (Meta name rule)
language         TEXT NOT NULL DEFAULT 'en'         -- BCP-47-ish lang code (en|hi|en_US|...)
category         TEXT NOT NULL      -- MARKETING|UTILITY|AUTHENTICATION  (auto-classified §6.3)
-- Meta component skeleton (§6.1) --
header           JSONB              -- {format:"TEXT"|"IMAGE"|"VIDEO"|"DOCUMENT", text?, example?}
body             JSONB              -- {text, placeholders:[{n,token}], example:[...]}
footer           JSONB NULL         -- {text<=60}
buttons          JSONB              -- [{type:"QUICK_REPLY"|"URL"|"PHONE_NUMBER"|"COPY_CODE", text, url?, phone?}]
angle            TEXT               -- benefit|urgency|social_proof|offer|trust|... (the selected angle)
selected_variation_id TEXT NULL     -- which variation is the active body
attached_asset_id     TEXT NULL     -- Creative-Studio banner bound as header media (approved only)
compliance       JSONB              -- {valid:bool, errors:[], warnings:[], category_reason, no_invent_flags:[]}
score            JSONB NULL         -- clarity/cta/brand_match/policy_safety (heuristic §6.5)
status           TEXT NOT NULL DEFAULT 'draft'  -- draft|approved|rejected|submitted|live|paused
meta_template_id TEXT DEFAULT ''    -- Meta's id after submit (dormant)
meta_review      TEXT DEFAULT ''    -- PENDING|APPROVED|REJECTED (from Meta, dormant)
metrics          JSONB DEFAULT '{}' -- writeback: sent/delivered/read/click/booking (§7), keyed for learning
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

### 4.3 `ai_wa_variations` — message variations per template (the angle alternatives)
```
variation_id     TEXT PRIMARY KEY   -- "wav_<uuid4hex>"
tenant_id        TEXT NOT NULL      -- RLS key
template_id      TEXT NOT NULL
angle            TEXT               -- benefit|urgency|social_proof|offer|trust|problem_solution|...
body_text        TEXT               -- the variation body WITH {{n}} placeholders
cta_text         TEXT               -- the variation's CTA button text (<=25 chars, Meta button limit)
hypothesis       TEXT               -- testing hypothesis (for A/B + the ads/learning loop)
language         TEXT NOT NULL DEFAULT 'en'
compliance       JSONB              -- per-variation grammar/char-limit check
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

### 4.4 `ai_wa_personalization` — the token plan (placeholder ↔ lead field binding)
```
plan_id          TEXT PRIMARY KEY   -- "wap_<uuid4hex>"
tenant_id        TEXT NOT NULL      -- RLS key
template_id      TEXT NOT NULL
component        TEXT               -- "body"|"header"|"button_url"
position         INT                -- the {{n}} index (1-based, Meta rule: sequential from 1)
token            TEXT               -- "name"|"city"|"lead_stage"|"product"|"price"|"booking_url"|"custom"
lead_field       TEXT               -- the resolved Lead/Org column the token reads (Lead.name, Lead.city, Lead.stage, product.name, campaign.offer, campaign.booking_url)
fallback         TEXT               -- value when the lead field is empty (Meta requires a sample/default)
sample_value     TEXT               -- the example Meta requires in the template submission
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

> **Storage size note:** these are small JSON records (a bundle ≈ a few KB), not media — they live in
> Postgres alongside `wallet_*`, NOT in the Asset Library (which is for *binary* assets). A generated
> template that gets approved + bound to a banner is the join: `ai_wa_templates.attached_asset_id` →
> `AssetRef.asset_id`. The two stores stay distinct (template text vs. banner bytes), linked by id.

### 4.5 RLS (verbatim the `ddl_wallet.sql` shape — admin-GUC, FORCE-RLS)
```sql
ALTER TABLE ai_wa_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_wa_templates FORCE  ROW LEVEL SECURITY;
CREATE POLICY ai_wa_templates_rls ON ai_wa_templates
  USING      ( current_setting('app.is_admin',true)='1'
               OR tenant_id = current_setting('app.tenant_id',true) )
  WITH CHECK ( current_setting('app.is_admin',true)='1'
               OR tenant_id = current_setting('app.tenant_id',true) );
-- identical policy on ai_wa_suggestion_bundles / ai_wa_variations / ai_wa_personalization
```
Every read/write runs inside `eng.session(tenant_id=..., is_admin=...)` (the `wallet.py:228` pattern) so a
cross-tenant template is invisible. Zero `%`-format DDL; tenant from the token GUC, never a body field.

---

## 5. THE CREDIT + ASYNC CONTRACT (reuse F4 verbatim — one money path)

A generation call is **LLM credits**, gated through `wallet.py` exactly like every other spend:

1. **Estimate → reserve.** `generate.py` estimates the LLM cost (≈ tokens × rate, a small fixed estimate per
   bundle, e.g. ~2–4 credits for a 3–5 template bundle) and calls
   `wallet.reserve(tenant_id, amount_minor:int, resource_type="wa_template_gen", resource_id=bundle_id,
   idem_key=<gen-key>)` → `hold_id|None` (the live `wallet.py:214` signature — **INTEGER PAISE, INR**). The
   UI shows "Generate 5 templates ≈ 3 credits. Continue?" before the call. `None` (insufficient funds) →
   `status="error:insufficient_credits"`, no LLM call, audited.
2. **The LLM call.** `llm.py` calls the existing Groq seam first, OpenRouter on fallback (the live
   round-robin key pool from the FORTRESS report), JSON-mode/structured-output, short timeout, retry on
   429/5xx, **never raises** (returns `(ok, json, err)` like `vendors/_http.py`). A bundle is **one** LLM
   call (all templates + variations in a single structured response) — cost-efficient.
3. **Settle / refund.** On success `wallet.settle(hold_id, actual_minor, idem_key=...)` (the
   `wallet.py:277` signature); on any failure `wallet.release(hold_id, ...)` (`wallet.py:344`) — refund the
   unused reserve. The hold backend is tagged so settle/release hit the same backend (the `media-gen.md`
   seam-bug lesson). **A failed generation never charges.**
4. **Async option.** For a big multi-language / multi-stage structure, the route schedules `generate.py` on
   a FastAPI `BackgroundTask` (the `creative-whatsapp-creative.md` §5 fire-and-forget pattern) and returns
   `{bundle_id, status:"accepted"}`; the UI polls `GET .../templates?bundle_id=`. A single 3–5 template
   bundle is fast enough to return inline.
5. **Audit.** `audit.record(actor=tenant_id, action="wa_builder.generate|approve|reject|submit|attach",
   object_type="wa_template", object_id=<template_id>, channel="whatsapp_builder", tenant_id=tenant_id,
   meta={campaign_id, n, model, category, est_credits})` (the live `audit.py:60` signature — **`actor`
   first positional**). Best-effort, never raises, secrets redacted.

> **Double-charge guard (AI-Manager path):** when this generation is invoked via the AI Manager, the
> adapter passes the AIM's `idem_key` down to `wallet.reserve` so the hold is idempotent against the AIM's
> `cost_guard` reserve (F4 `ON CONFLICT` — one logical hold). Same discipline as
> `creative-studio-integrations.md` §4.3.

---

## 6. WHATSAPP TEMPLATE-FORMAT COMPLIANCE (the validator is the AUTHORITY — `validate.py`)

The model proposes; `validate.py` **decides**. Every generated template passes a deterministic check against
the **2026 WhatsApp Cloud API Message-Template grammar** before it can be approved/submitted. Grounded in
the live Meta docs (`graph.facebook.com/{waba}/message_templates`).

### 6.1 Template structure (header / body / footer / buttons) — the grammar enforced
| Component | Meta 2026 rule the validator enforces |
|---|---|
| **name** | lowercase `[a-z0-9_]`, ≤ 512 chars, unique per WABA. Auto-snake_cased from the campaign+angle. |
| **language** | a valid Meta language code (`en`, `en_US`, `hi`, …). |
| **category** | exactly one of **MARKETING / UTILITY / AUTHENTICATION** (auto-classified §6.3). |
| **header** (optional, ≤1) | format ∈ `TEXT` (≤60 chars, ≤1 variable) **or** `IMAGE`/`VIDEO`/`DOCUMENT` (media header → bound to a Creative-Studio banner via `attach_asset_id`). |
| **body** (required, 1) | text ≤ **1024 chars**; `{{n}}` placeholders **sequential from 1, no gaps, no duplicates**; no two placeholders adjacent (`{{1}}{{2}}` is rejected); cannot start/end with a placeholder; each placeholder needs an `example`. |
| **footer** (optional, ≤1) | text ≤ **60 chars**, **no variables** (Meta rule). |
| **buttons** (optional, ≤10; ≤2 URL, ≤1 phone) | `QUICK_REPLY` (text ≤25) / `URL` (text ≤25, valid https URL, ≤1 variable at the end) / `PHONE_NUMBER` (valid E.164) / `COPY_CODE`. The CTA recommendations (§6.4) map here. |

Any violation → `compliance.valid=false` + a specific `errors[]` entry; the template stays `draft` and
**cannot be approved** until the model regenerates or the vendor edits. Warnings (e.g. body > 600 chars =
"long for WhatsApp") are non-blocking.

### 6.2 Personalization placeholders (`{{1}}`, `{{2}}` …) — the token plan
The model emits **named tokens** (`{{name}}`, `{{city}}`, `{{lead_stage}}`, `{{product}}`, `{{price}}`,
`{{booking_url}}`); `personalize.py` **renumbers** them to Meta's required **positional** `{{1}}`/`{{2}}`
(sequential, 1-based, gap-free) and records the **binding** in `ai_wa_personalization` (§4.4): each position
→ a real `Lead`/`Org`/`Campaign` column + a **fallback** (Meta requires a default for empty values) + a
**sample value** (Meta requires an example in the submission). At send time `whatsapp.py` fills the
positional params from the lead row, falling back to the stored default — so a missing `city` never sends a
literal "`{{2}}`". `name` → `Lead.name`, `city` → `Lead.city`, `lead_stage` → `Lead.stage`, `product` →
product name, `price`/`booking_url` → campaign fields (**only if stored** — NO-INVENT §2).

### 6.3 Meta category auto-classification (MARKETING / UTILITY / AUTHENTICATION) — the cost+policy gate
Deterministic classifier (the model *suggests* a category; the validator *decides* it — mis-categorization
is itself a Meta violation, so it is never chosen to dodge cost):
- **AUTHENTICATION** — body is an OTP/verification-code pattern (a `{{n}}` code + "do not share"). The
  builder **does not generate these** by default (no marketing value); if detected, classified AUTH and the
  variation set is suppressed.
- **UTILITY** — transactional / post-interaction intent the recipient expects: "your enquiry details", "your
  booking is confirmed", "you asked us to send the brochure", appointment reminders, order/account updates.
  **~6–8× cheaper** (≈₹0.11–0.145, 2026 India) and **lower policy risk**. **Default for post-call follow-ups**
  where the content legitimately qualifies (the consent-aware default from
  `creative-whatsapp-creative.md` RED-TEAM B4).
- **MARKETING** — promotions, offers, new-product announcements, re-engagement, upsell (≈₹0.86). Used only
  when the campaign objective is genuinely promotional **and** a `wa_marketing_optin` flag is on record
  (else held for human approval — the consent gate).

The classifier surfaces `category_reason` in `compliance` so the vendor sees *why* it's MARKETING vs UTILITY
(transparency + the cost difference). This drives the per-message meter on the eventual send.

### 6.4 CTA recommendations (goal-matched — `structure.py` / `generate.py`)
The CTA is derived **from the campaign goal**, not invented (master §11): real-estate → "Book Site Visit"
(URL button to booking link); salon → "Book Appointment"; clinic → "Book Consultation"; coaching → "Book
Free Demo"; ecommerce → "Shop Now"; cafe → "Order Now" / "Visit Us". Mapped to a Meta `URL` button
(booking/landing link, `{{1}}` variable allowed at the URL end) or `QUICK_REPLY` (for a reply-driven flow).
Each CTA respects the ≤25-char button limit and the ≤2-URL-button rule.

### 6.5 NO-INVENT scrub + a heuristic score
`validate.py` runs the **NO-INVENT scrub** (§2): any price/discount/RERA/guarantee/phone/award token NOT in
the context is stripped and flagged `no_invent_flags[]` → the template drops to `needs_fact` (cannot be
approved with a fabricated claim). It also computes a cheap heuristic **score** (clarity = char count band;
cta_present; brand_match = uses preferred CTA/language; policy_safety = no denylisted phrases) so the gallery
can rank suggestions — a first-line signal, not a guarantee.

---

## 7. PERFORMANCE-LEARNING FEEDBACK (close the loop — reuse the library's summary)

Every send of an approved template (via `whatsapp.py` / the `creative/whatsapp` plane) carries the
template's `template_id` + `campaign_id` + (if attached) the banner's `variant_id`. When delivery / read /
click / booking signals return on the **existing** `POST /whatsapp/inbound` status webhook
(`caller.py:4406`), the builder's `metrics` field accumulates them (keyed by `template_id`, and the banner's
metrics roll up to the `AssetRef` per `creative-studio-integrations.md` §2.4). On the **next**
`generate-templates` call, `context.build` reads `library.performance_summary(tenant_id, industry,
campaign_id)` (the §7 contract) + the builder's own template metrics → the prompt **over-weights the angle /
CTA / language that historically drove replies+bookings** and **down-weights rejected/low-read** ones.
**Honest boundary:** this biases *style/angle/CTA/language*, never *facts*; cold-start tenants fall back to
the industry-pack defaults; it proposes performance-informed variants for testing, it does not guarantee a
winning template.

---

## 8. SECURITY / ISOLATION (the boundary every call respects)

- **Tenant from TOKEN, never body** — `resolve_tenant` (`caller.py:551`) on every route; `attach-banner`
  and `submit-to-meta` re-assert ownership (`AssetRef.tenant_id == token tenant`; `ai_wa_templates.tenant_id
  == token tenant`). The negative control: a body `tenant_id`/`campaign_id` must FAIL to forge cross-tenant.
- **FORCE-RLS `ai_wa_*`** — admin-GUC policy (§4.5), `famit_app` NOSUPERUSER/NOBYPASSRLS, every op inside the
  tenant GUC. A search never leaks another tenant's template.
- **One money path** — generation credits via `wallet.py` (idempotent, no-double-spend, F4); the eventual
  per-message send cost is the `whatsapp.py` meter's job — the builder spends **only** on generation, never
  on send.
- **Approval is the content-policy firewall** — `approve` (or an explicit auto-mode toggle) is the human
  gate before a machine-made template is submitted to Meta or sent to customers. **Default biases safe**
  (human-approved, no auto-submit). A MARKETING template to a contact with no `wa_marketing_optin` is **held
  for approval** (the consent + India-DLT gate, `creative-whatsapp-creative.md` B4).
- **Meta is the final gate** — the builder cannot conjure an approved template; `submit-to-meta` only queues
  it for **Meta's** review (the founder/Meta own that). Honest: "templates generated" ≠ "template approved".
- **NO-INVENT enforced deterministically** — the validator scrub (§6.5), not model trust, prevents fabricated
  price/RERA/medical/guarantee claims (master §41 NEVER list; clinic packs block medical-cure claims).
- **Immutable audit, channel=`whatsapp_builder`** — every generate/approve/reject/submit/attach rows to
  `audit.py`; secrets redacted; cross-references the `creative` audit when a banner is attached.
- **Dormant-until-creds** — no LLM key → `generate-templates` returns a **deterministic templated fallback**
  (industry-pack skeletons with the right structure/category, no AI copy) and `status:"not_configured"` on
  the AI portion; no Meta token → generate+store works, `submit-to-meta` returns `not_configured`. Never
  raises into a request.

---

## 9. OFFLINE ACCEPTANCE TEST (`tests/test_builder_offline.py`) — ZERO external calls

Temp `var/whatsapp_builder/`, a fixture `Org`+`Campaign`+`Lead` set, **LLM + Meta + DB env UNSET**,
`wallet`/`audit` monkeypatched to in-memory, **`httpx` patched to RAISE if touched** (proves zero network).
A `fake` LLM returns a canned golden proposal bundle. Exits non-zero on any failure (CI-gateable).

1. **Dormant status:** all env unset → `status()` shows `llm:"not_configured"`; `generate-templates` returns
   the **deterministic templated fallback** bundle (valid Meta structure, no AI copy), nothing raises.
2. **Generate via fake LLM:** `generate_templates(campaign_id="c1", n=3)` → bundle with 3 templates, each
   with ≥2 variations, a personalization plan, ≥1 CTA, ≥1 media_rec; all `status="draft"`.
3. **Meta grammar validation:** a template with body > 1024 chars / adjacent `{{1}}{{2}}` / a footer variable
   / a 30-char button → `compliance.valid=false` with the **specific** error; a clean one → `valid=true`.
4. **Placeholder renumbering:** named tokens `{{name}}`/`{{city}}` → positional `{{1}}`/`{{2}}` sequential
   from 1; `ai_wa_personalization` binds each to the right `Lead` field with a fallback + sample.
5. **Category auto-classify:** a promo body → `MARKETING`; an "your enquiry details" body → `UTILITY`; an OTP
   body → `AUTHENTICATION`; each with a `category_reason`. (Decision is the validator's, not the model's.)
6. **NO-INVENT scrub:** a model output with "₹50L" / "RERA Approved" NOT in the context → stripped, flagged
   `no_invent_flags`, template → `needs_fact`, cannot be approved.
7. **Credit contract:** `wallet.reserve` called with `resource_type="wa_template_gen"` + `idem_key`; on fake
   LLM success `settle` called; on a forced LLM error `release` called (refund) — asserted via spies; a
   second call with the same `idem_key` does not double-reserve.
8. **Select + approve gate:** `select(variation_id)` sets the active body; `approve` only succeeds on a
   `valid=true` non-`needs_fact` template → `status=approved`; an invalid template `approve` → refused.
9. **Attach banner (tenant-checked):** `attach-banner(asset_id of another tenant)` → refused; an approved
   own-tenant asset → bound as the header.
10. **RLS scoping:** a second tenant's templates are invisible to `list`/`get` (tenant GUC enforced).
11. **Submit dormant:** `submit-to-meta` with no creds → `not_configured`, no network; with a fake Meta
    transport → the correct `POST /{waba}/message_templates` body shape is built.
12. **Learning bias:** with a fake `performance_summary` favoring "urgency", the next `generate-templates`
    prompt over-weights urgency; a previously rejected angle is down-weighted (assert via the prompt builder
    output, no model needed).
13. **Never-raises fuzz:** empty spec, n=999, unknown campaign, malformed LLM JSON, oversized inputs → each
    returns a typed bundle/template with an `invalid`/clamped status, no exception.

The whole pipeline (context → reserve → llm → validate → classify → personalize → persist → settle → audit)
runs with **zero credentials and zero network**.

---

## 10. BUILD ORDER (small verifiable units, no git — orchestrator commits)

1. `models.py` + `store.py` (ai_wa_* DDL + JSONL fallback) + `config.py` → test #1, #10.
2. `validate.py` (Meta grammar + category classifier + NO-INVENT scrub) → tests #3, #5, #6. **Build this
   FIRST after models** — it is the authority; everything else feeds it.
3. `personalize.py` (token renumber + lead-field binding + sample render) → test #4.
4. `context.py` (read-only campaign context) + `prompt.py` (NO-INVENT schema prompt + industry few-shots).
5. `llm.py` (reuse Groq/OpenRouter seam, JSON-mode, dormant) + `generate.py` (orchestration) + `credit.py`
   (wallet reserve/settle/release) → tests #2, #7.
6. `structure.py` (campaign-structure sequence across lead stages) + CTA mapping → bundle completeness (#2).
7. `audit_hook.py` + select/approve/reject mutators → test #8.
8. `meta_submit.py` (dormant submit seam) + attach-banner (creative.* tenant-checked) → tests #9, #11.
9. Performance-learning read into `context.build` → test #12.
10. `router.py` (deferred APIRouter) + full `test_builder_offline.py` green (#1–#13) → STOP (orchestrator
    mounts routes, registers the `ToolSpec`, wires the status-webhook metric writeback, commits).

---

## 11. CREDENTIALS THE FOUNDER MUST PROVIDE (mostly already present)

| # | What | Env var(s) | Status (per WHATSAPP_GOLIVE.md) | Needed for | Cost |
|---|---|---|---|---|---|
| 1 | **LLM (Groq + OpenRouter)** | `GROQ_API_KEY` (round-robin pool), `OPENROUTER_API_KEY` | **PRESENT** — OpenRouter image-gen already proven live; Groq pool live on the box | AI template generation (else deterministic templated fallback) | per-token, ~paise per bundle |
| 2 | **Meta WhatsApp Cloud API** | `META_WA_TOKEN` (`EAA…`), `META_WA_PHONE_NUMBER_ID`, `META_WA_BUSINESS_ACCOUNT_ID`, `META_WA_APP_SECRET`, `META_WA_VERIFY_TOKEN` | **PRESENT** — real send proven; webhook live (box `.env` token update pending per GO-LIVE §BACKEND) | `submit-to-meta` + the eventual send | template approval free; send per-category |
| 3 | **Wallet credit balance** | (none — uses `wallet_accounts`) | live (F4) | gating generation spend | – |
| 4 | **Approved Meta template(s)** | (Meta-side; `WA_*_TEMPLATE` names) | only `hello_world` (test-only) → **need a real approved template** | actually SENDING a generated+approved template to cold contacts | free to create |

> **Net:** the AI generation + validation + storage + credit gate run **today** with the keys already on the
> box (#1, #3). Generation works with **zero new creds** (deterministic fallback even without #1). To
> *deliver* a generated template to a cold contact still needs **Meta's approval of that specific template**
> (#4) — Meta's gate, the founder's one-time submit; the builder queues it via `submit-to-meta`.

---

## 12. REAL-vs-HYPE (honest, bounded)

| Claim | Reality |
|---|---|
| "Select a campaign → AI writes your WhatsApp templates" | True — campaign-aware generation of compliant template skeletons + variations + CTAs + token plan + structure, from stored data. It does **not** invent facts (validator scrub) and templates are **draft** until a human approves. |
| "Templates are ready to send" | They are ready to **submit to Meta**; Meta must **approve** the template before a cold (outside-24h) send works. The builder queues; Meta decides; the founder owns that gate. |
| "It picks the right Meta category" | A deterministic classifier auto-sets MARKETING/UTILITY/AUTHENTICATION (cost + policy aware, consent-gated for MARKETING). It never mis-categorizes to dodge cost (itself a violation). |
| "Personalization just works" | `{{n}}` tokens are bound to real lead fields with fallbacks + samples; a missing field sends the fallback, never a literal placeholder. Bounded by what lead data exists. |
| "It learns and improves" | It biases generation toward historically winning angle/CTA/language and away from rejected ones (a real deterministic loop). It does **not** guarantee a winning template; cold-start falls back to industry defaults. |
| "Works offline / dormant" | The context build, validation, category classification, personalization, credit gate, and storage are pure logic and offline-testable; only the *AI copy quality* needs an LLM key, and *delivery* needs Meta's template approval. |

---

## 15-LINE SUMMARY (for the orchestrator)

1. **What:** an AI **template-generation brain** for the WhatsApp Campaign Builder — pick a campaign → the
   backend auto-generates Meta-compliant **template suggestions + message variations + CTAs + personalization
   tokens + media recommendations + campaign structures** from the campaign's objectives/audience/offer/
   products/business-context/brand, with the master-spec **NO-INVENT** guardrails.
2. **Where:** a thin **`whatsapp-builder` MODULE in the monolith** (not a new service — no GPU/queue/provider
   fleet, droplets 3/3 full; AI-Manager in-process precedent). Distinct from the live `whatsapp.py`
   (send/receive) and the `creative/whatsapp` packaging module; it **imports `whatsapp.py` config, never
   edits it**. Code path `droplet_work/whatsapp_builder/`.
3. **The brain is two-layer:** the LLM (reused Groq→OpenRouter seam) **proposes**; a deterministic
   **Meta-compliance validator is the AUTHORITY** — it enforces the 2026 Cloud API template grammar
   (header/body/footer/buttons, `{{n}}` placeholders, char limits), auto-classifies the Meta **category**
   (MARKETING/UTILITY/AUTHENTICATION), binds personalization tokens to lead fields, and **scrubs fabricated
   facts** (the model never introduces a price/RERA/claim).
4. **Data model:** four FORCE-RLS `ai_wa_*` Postgres tables (the live `ddl_wallet.sql` admin-GUC pattern) —
   `ai_wa_suggestion_bundles` (a generation run + credit hold), `ai_wa_templates` (the Meta-shaped skeleton +
   category + compliance + metrics), `ai_wa_variations` (angle-labeled body alternatives + CTA + hypothesis),
   `ai_wa_personalization` (`{{n}}` ↔ lead-field binding + fallback + sample). Small JSON, not media; JSONL
   fallback offline.
5. **Headline API:** `POST /whatsapp/campaign/{id}/generate-templates` (the generation, credit-gated,
   `spend`) → `list`/`get`/`select`/`regenerate`/`approve`/`reject`/`submit-to-meta`/`attach-banner`/
   `meta-status`/`builder/status`. Also one `ToolSpec` (`whatsapp.generate_templates`) for AI-Manager +
   Workflow nodes — same module, same gates.
6. **Credit:** generation = LLM credits via `wallet.reserve(resource_type="wa_template_gen", idem_key=…)` →
   `settle` on success / `release` (refund) on failure — the F4 no-double-spend path verbatim; a failed gen
   never charges; idem_key passed down from the AIM to avoid double-reserve.
7. **Meta compliance (the load-bearing part):** name/language/category rules; header (TEXT≤60 or media);
   body ≤1024 + sequential gap-free non-adjacent `{{n}}`; footer ≤60 no-variable; buttons ≤10 (≤2 URL/≤1
   phone, text ≤25). Violations block approval. Category auto-classified for cost + policy (UTILITY default
   for post-call, MARKETING only with opt-in else held).
8. **Personalization:** named tokens → positional `{{1}}`/`{{2}}` (Meta sequential rule) bound to
   `Lead.name`/`Lead.city`/`Lead.stage`/product/campaign fields with a **fallback + sample** Meta requires;
   a missing field sends the fallback, never a literal `{{2}}`.
9. **Media recommendations** route to the **`creative.*`** contract (`creative.generate(kind="wa_poster")` /
   attach an approved `AssetRef`) — banners are **never generated here**; the template only references/binds
   the approved asset id (`attach-banner`, tenant-checked).
10. **Approval gate** (`approve`, classed `destructive`) is the content-policy firewall: only an approved,
    Meta-valid, non-fabricated template can be submitted to Meta / attached / sent. Default biases safe
    (human-approved, no auto-submit); MARKETING without opt-in is held.
11. **Learning loop:** sent-template delivery/read/click/booking write back to `ai_wa_templates.metrics` (via
    the existing `/whatsapp/inbound` status webhook) + the banner's `AssetRef`; the next generation reads
    `library.performance_summary` → over-weights winning angle/CTA/language, down-weights rejected — biases
    STYLE, never invents facts.
12. **Security:** tenant from token (never body), FORCE-RLS `ai_wa_*`, ownership re-checked on attach/submit,
    one money path (generation only), approval = the firewall, immutable `whatsapp_builder` audit,
    dormant-until-creds (no LLM → templated fallback; no Meta → store-only).
13. **Honest:** "AI writes your templates" = compliant **drafts** a human approves; **Meta** still approves
    the template before cold sends; the loop biases, doesn't guarantee; only AI *copy quality* needs the LLM
    key and *delivery* needs Meta's template approval.
14. **Reuse discipline:** NO new LLM client, NO new WhatsApp client, NO new money path, NO new asset store —
    it contracts a generation+compliance layer over the live Groq/OpenRouter seam, `whatsapp.py`, `wallet.py`,
    `audit.py`, the Asset Library, and the `creative.*` contract. The only net-new is the `ai_wa_*` schema +
    the validator/classifier + the prompt.
15. **Build = 10 small dormant-safe, offline-testable units** (validator first — it's the authority); the
    full `test_builder_offline.py` runs with zero credentials and zero network; wiring (route mount, ToolSpec
    register, status-webhook metric writeback, caller.py send) is the orchestrator's deferred step.
```
