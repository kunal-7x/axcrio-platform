# DESIGN SPEC — BUSINESS BRAIN (per-business knowledge/identity store)

> The FOUNDATIONAL subsystem every AI worker reads before acting. It is the single
> source of truth for *who the business is* (identity, brand, products, pricing,
> offers, audience, policies, FAQs, objection-handling, docs) and the place from
> which **campaigns, voice, WhatsApp, support, creative, and the AI Manager all
> derive their context**. Today that context is re-typed per campaign; Business
> Brain makes it write-once-per-business, inherited-everywhere, versioned, and
> retrievable.
>
> **Verdict:** STRANGLE & EVOLVE. This does NOT replace `prompt.py`,
> `build_system_prompt`, the campaign store, or the RAG plane — it **feeds** them.
> Flag-gated, additive, byte-identical when off. The live site keeps earning.
>
> Author: staff-eng design pass, grounded in live source (`droplet_work/`) +
> design/{p1-postgres, dynamic-context-rag, p0-foundation, automation-aimanager}.md.
> Last updated: 2026-06-09. Status: READY TO BUILD.

---

## 0. THE ONE LOAD-BEARING IDEA (read first — everything follows from it)

There is already a "business context" object in the system: the **campaign field
dict** `f` consumed by `prompt.py:253 build_system_prompt(f)`. Verified keys it
reads: `agent_name, company_name, product_name, product_summary, location,
price_offer, usps[], talking_points[], qualifying_questions[], objections[{q,a}],
objection_bank, negotiation_ladder, closing_lines[], escalation_rules, persona,
disclose_ai, ai_disclosure, language` (`prompt.py:253-307`). The same dict is
normalised by `caller.py:1876 _coerce_fields` and persisted by `save_campaign`.

**Problem:** that context lives PER CAMPAIGN. A salon with 4 campaigns re-types
its brand voice, AI-disclosure policy, objection bank, and FAQ four times; the
WhatsApp salesperson, support agent, and creative producer each re-derive it
again from scratch. Nothing is shared, versioned, or retrievable as "the
business".

**Business Brain = hoist that context up one level — to the BUSINESS (org_id) —
and make every worker inherit it.** Concretely:

1. A new per-org store (`business_brain` + child tables on Postgres) holds the
   business identity/knowledge ONCE.
2. A pure function **`brain.resolve_campaign_defaults(org_id) -> dict`** returns a
   field dict in **exactly the `_coerce_fields` shape**. Campaign creation merges
   `{**brain_defaults, **user_fields}` so a campaign *inherits* the brand voice,
   objection bank, disclosure policy, persona, FAQ — and overrides only what's
   campaign-specific (this product, this price, these leads). **Zero change to
   `build_system_prompt`.** It still receives a flat dict; the dict is now
   pre-filled from the Brain.
3. Long-form knowledge (brochures, FAQ, policy docs, price sheets) lands in the
   **existing `campaign_knowledge_chunks` pgvector corpus** — extended with a
   `scope` so a chunk can belong to the *business* (all campaigns) not just one
   campaign. Voice/WhatsApp/support retrieve it through the **already-designed**
   dial-time precompute path (`dynamic-context-rag.md §4`). No new hot-path.
4. Every other AI worker (WhatsApp salesperson, support agent, campaign
   strategist, creative producer, AI Manager) reads the Brain through **one
   in-process API** (`brain.get_profile`, `brain.resolve_*`, `brain.retrieve`)
   — never its own bespoke query.

This is why Business Brain is *foundational but cheap*: it reuses the prompt
builder, the campaign store, the RAG corpus, the Postgres+RLS plane, and the
strangler `store.py` seam. It adds **identity tables + one resolver + one read
facade**, not a new engine.

---

## 0a. OSS LANDSCAPE — DELIBERATE BUILD-MINIMAL DECISION (web-researched 2026-06-09)

The 2026 OSS in this space — **WeKnora** (Tencent; doc→queryable-RAG + ReAct agent
+ self-maintaining wiki), **LlamaIndex** (100+ connectors, agentic-RAG pipelines),
**Onyx** (AI search over 50+ sources) — are heavyweight *document-RAG / knowledge
platforms*. They solve a DIFFERENT problem than Business Brain: they ingest large
corpora and make them queryable. Business Brain is a **structured per-tenant
identity/defaults store** whose primary job is to *feed an existing prompt-builder
field dict and the already-chosen pgvector/BGE-M3 retrieval plane* — not to be a
new RAG engine. Adopting WeKnora/LlamaIndex/Onyx would duplicate the settled RAG
plane (`dynamic-context-rag.md`), add a heavy service, and fork the Postgres+RLS
isolation model — net negative under STRANGLE & EVOLVE. **Decision: do NOT adopt a
knowledge-platform OSS.** Compose the already-settled OSS (pgvector + BGE-M3
embeddings + Hatchet) and add only the thin identity/resolver/facade layer this
spec defines. LlamaIndex's *chunking heuristics* are a useful reference for the
doc-chunker only (already covered in `dynamic-context-rag.md §4a`). Sources:
[WeKnora](https://github.com/Tencent/WeKnora),
[Firecrawl — Best Open-Source RAG Frameworks 2026](https://www.firecrawl.dev/blog/best-open-source-rag-frameworks),
[Atlan — Enterprise LLM Knowledge Base governance](https://atlan.com/know/enterprise-llm-knowledge-base/).

---

## 1. HOW IT SITS ON THE SETTLED FOUNDATION

| Foundation piece (already built / designed) | Business Brain's use of it |
|---|---|
| **Postgres + RLS** (`p1-postgres.md §3-5`): every tenant table has `org_id text NOT NULL`, `ENABLE`+`FORCE ROW LEVEL SECURITY`, policy `org_id = current_setting('app.tenant_id')`, restricted `famit_app` role, `SET LOCAL app.tenant_id` per txn. | All Brain tables follow this verbatim. `business_brain.id == org_id == tenant_id` (1 brain per business). |
| **`db/models.py` conventions**: text PKs = app ids, `data jsonb` catch-all = full record, promote-to-column only what you index/filter/RLS, `*_raw` for byte-stable timestamps, Alembic `0001_init` is DDL source of truth. | New models `BusinessBrain`, `BrainProduct`, `BrainDocument`, `BrainFaq`, `BrainObjection` added as a new Alembic revision `0003_business_brain.py` (P1 already owns 0001/0002). |
| **Strangler `store.py`** (per-store MODE ∈ {json,dual,pg}, default json, import-safe degrade). | Brain registers as store name `brain` (and `brain_*` children). Default `json` → `var/brain/<org_id>.json`, mirrors the campaign-store pattern the agent already trusts. Flip to `dual`→`pg` once shadow_diff==0. **No PG dependency to ship.** |
| **pgvector RAG corpus** `campaign_knowledge_chunks` + `vendors/embeddings.py` (BGE-M3, import-safe-degrade) + dial-time precompute (`dynamic-context-rag.md`). | Brain documents are chunked/embedded into the SAME table with `campaign_id = '__brain__'` (business-scoped). Retrieval already folds business-scope + campaign-scope (one extra `OR campaign_id='__brain__'` in the WHERE). **No new vector table, no new hot-path.** |
| **`prompt.py:build_system_prompt(f)`** — the STABLE Groq-cached prefix. | UNCHANGED. The Brain feeds its input dict; it never mutates the function. (Critical: do NOT inject per-lead Brain text into the cached prefix — that breaks the cache moat. Per-lead/retrieved Brain content rides the per-call SUFFIX rail, exactly as RAG does — `dynamic-context-rag.md §1`.) |
| **Hatchet worker-spine** (`orchestration-hatchet.md`). | Heavy Brain work (embed a 40-page policy PDF, OCR a brochure, summarise into facts) is a Hatchet task, not inline in the API loop — same event-loop-safety rule as RAG indexing (`dynamic-context-rag.md §3` EVENT-LOOP SAFETY box). Dormant-degrade: if Hatchet absent, fall back to `asyncio.to_thread`. |
| **Control-plane modular monolith** (`caller.py` + siblings). | New sibling module `brain.py` (import-safe, mirrors `auth.py`/`config.py` shape: `init()`, `available()`, no module-level env reads, no top-level network). Read endpoints added to `caller.py`. |
| **AI Manager** (`automation-aimanager.md`) | Its tools (`launch_campaign`, `update_pricing`, etc.) read the Brain via `brain.get_profile(org_id)` to fill defaults and to ground intent ("launch a campaign for my 2BHK" → resolves "2BHK" against `BrainProduct`). |
| **Audit log** (`audit.py`). | Every Brain write emits `audit.record("brain.<verb>", "brain", org_id, meta)`. Brain edits are versioned (§5) — risky for the AI to silently rewrite a business's identity/pricing. |

---

## 2. DATA MODEL

One parent + four children. **Promote-to-column only what is indexed/filtered/RLS'd;
everything else in `data jsonb`** (P1 rule). All tables: `org_id text NOT NULL`,
`ENABLE`+`FORCE ROW LEVEL SECURITY`, policy on `org_id`.

### 2.1 `business_brain` — the identity/policy core (one row per business)

```sql
CREATE TABLE business_brain (
  id            text PRIMARY KEY,                 -- == org_id == tenant_id (1:1)
  org_id        text NOT NULL,                    -- == id (kept for uniform RLS policy)
  industry      text NOT NULL DEFAULT '',         -- real_estate|salon|clinic|coaching|d2c|ecom|cafe|agency|...
  industry_pack text NOT NULL DEFAULT '',         -- which Industry Pack seeded defaults (provenance)
  legal_name    text NOT NULL DEFAULT '',
  display_name  text NOT NULL DEFAULT '',         -- -> company_name
  -- IDENTITY / BRAND (drives persona + tone of EVERY worker)
  brand_tone    text NOT NULL DEFAULT '',         -- "warm, premium, no hard-sell" -> persona/SHARED_RULES
  languages     text NOT NULL DEFAULT 'Hinglish', -- default reply language
  agent_name    text NOT NULL DEFAULT 'Riya',
  voice_id      text NOT NULL DEFAULT '',
  -- POLICY (compliance + disclosure the AI must honour)
  disclose_ai   boolean NOT NULL DEFAULT true,
  ai_disclosure text NOT NULL DEFAULT '',
  call_window_start text NOT NULL DEFAULT '09:00',
  call_window_end   text NOT NULL DEFAULT '21:00',
  call_window_tz    text NOT NULL DEFAULT 'Asia/Kolkata',
  -- COMPLETENESS / GOVERNANCE
  version       int  NOT NULL DEFAULT 1,          -- bumped on every write (cache-bust + audit)
  completeness  int  NOT NULL DEFAULT 0,          -- 0..100 readiness score (§4.3)
  status        text NOT NULL DEFAULT 'draft',    -- draft|active
  data          jsonb NOT NULL DEFAULT '{}',      -- FULL record: audience{}, usps[], talking_points[],
                                                  -- qualifying_questions[], closing_lines[], escalation_rules,
                                                  -- negotiation_ladder, persona, offers[],
                                                  -- policies{refund,shipping,...}, links{}
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  updated_at_raw text NOT NULL DEFAULT ''         -- byte-stable ISO for shadow_diff (P1 rule)
);
-- RLS (verbatim P1 pattern)
ALTER TABLE business_brain ENABLE ROW LEVEL SECURITY;
ALTER TABLE business_brain FORCE  ROW LEVEL SECURITY;
CREATE POLICY brain_tenant ON business_brain
  USING (org_id = current_setting('app.tenant_id', true))
  WITH CHECK (org_id = current_setting('app.tenant_id', true));
```

> **Why only these columns are promoted:** `industry`, `status`, `version`,
> `completeness` are filtered/sorted in the dashboard + used for cache-bust;
> `org_id` is the RLS key. Everything a worker reads as *content* (usps,
> talking_points, audience, offers, policies, persona) lives in `data jsonb` —
> it is never queried by value, only loaded whole by `org_id`. This keeps the
> resolver one indexed point-read.

### 2.2 `brain_product` — catalog (products/services/properties/plans)

```sql
CREATE TABLE brain_product (
  id          text PRIMARY KEY,                   -- uuid4().hex[:10] (matches app id style)
  org_id      text NOT NULL,
  sku         text NOT NULL DEFAULT '',
  name        text NOT NULL DEFAULT '',
  category    text NOT NULL DEFAULT '',
  price       numeric NOT NULL DEFAULT 0,
  currency    text NOT NULL DEFAULT 'INR',
  price_text  text NOT NULL DEFAULT '',           -- human "₹85L onwards" -> price_offer
  active      boolean NOT NULL DEFAULT true,
  data        jsonb NOT NULL DEFAULT '{}',        -- summary, specs{}, usps[], offers[], media_ids[], variants[]
  updated_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE brain_product ENABLE ROW LEVEL SECURITY;
ALTER TABLE brain_product FORCE  ROW LEVEL SECURITY;
CREATE POLICY brain_product_tenant ON brain_product
  USING (org_id = current_setting('app.tenant_id', true))
  WITH CHECK (org_id = current_setting('app.tenant_id', true));
CREATE INDEX brain_product_org ON brain_product (org_id, active);
```

### 2.3 `brain_document` — raw long-form knowledge (the RAG source)

```sql
CREATE TABLE brain_document (
  id          text PRIMARY KEY,
  org_id      text NOT NULL,
  title       text NOT NULL DEFAULT '',
  kind        text NOT NULL DEFAULT 'doc',        -- brochure|faq|policy|pricesheet|script|legal|doc
  scope       text NOT NULL DEFAULT 'business',   -- business (all campaigns) | product:<id> | campaign:<id>
  source      text NOT NULL DEFAULT 'paste',      -- paste|upload|url|generated
  content     text NOT NULL DEFAULT '',           -- extracted plain text (what gets chunked/embedded)
  chunked     boolean NOT NULL DEFAULT false,     -- has it been embedded into campaign_knowledge_chunks?
  kb_version  int  NOT NULL DEFAULT 0,            -- bumped on re-index (busts RAG cache, mirrors §4 doc)
  data        jsonb NOT NULL DEFAULT '{}',        -- {file_ref, mime, bytes, ocr:bool, summary}
  updated_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE brain_document ENABLE ROW LEVEL SECURITY;
ALTER TABLE brain_document FORCE  ROW LEVEL SECURITY;
CREATE POLICY brain_document_tenant ON brain_document
  USING (org_id = current_setting('app.tenant_id', true))
  WITH CHECK (org_id = current_setting('app.tenant_id', true));
CREATE INDEX brain_document_org ON brain_document (org_id, scope);
```

### 2.4 `brain_faq` + `brain_objection` — structured Q&A (NOT vectorized by default)

These are small, structured, and injected wholesale into the prompt suffix /
WhatsApp/support context (mirrors how `prompt.py:286 objs` already injects the
campaign objection bank as text — `dynamic-context-rag.md §2c` says do NOT
per-turn-vectorize a campaign's own small objection set). They are key-loaded by
`org_id`, not similarity-searched.

```sql
CREATE TABLE brain_faq (
  id text PRIMARY KEY, org_id text NOT NULL,
  q text NOT NULL DEFAULT '', a text NOT NULL DEFAULT '',
  tags text NOT NULL DEFAULT '', sort int NOT NULL DEFAULT 0,
  data jsonb NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE brain_objection (
  id text PRIMARY KEY, org_id text NOT NULL,
  q text NOT NULL DEFAULT '', a text NOT NULL DEFAULT '',     -- objection -> approved rebuttal
  sort int NOT NULL DEFAULT 0,
  data jsonb NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now()
);
-- both: ENABLE+FORCE RLS, policy on org_id, INDEX (org_id) — verbatim P1 pattern.
```

> **Relationship to `objection_vectors`** (`dynamic-context-rag.md §2c`): that table
> is for the *cross-campaign learned* corpus (harvested from transcripts, Phase 3).
> `brain_objection` is the *authored* bank the business curates. A future harvester
> can promote a learned rebuttal into `brain_objection` after human approval — but
> that is out of scope here; `brain_objection` ships as the authored source.

### 2.5 JSON fallback shape (`var/brain/<org_id>.json`) — MODE=json default

Identical fields, one file per org (mirrors `var/campaigns/<id>.json`). This is
what ships first; PG is the later strangler target. Example:

```json
{ "id":"org_abc","industry":"salon","display_name":"Glow Studio",
  "brand_tone":"warm, premium, never pushy","languages":"Hinglish",
  "agent_name":"Riya","disclose_ai":true,"version":7,"completeness":82,"status":"active",
  "audience":{"who":"women 25-45, South Delhi","pains":["time","trust"]},
  "usps":["Senior stylists","Organic products","Same-week slots"],
  "talking_points":["Festive package live","Free skin consult"],
  "closing_lines":["Book a slot this week?","WhatsApp you the package?"],
  "escalation_rules":"...","negotiation_ladder":[...],"persona":"...",
  "offers":[{"name":"Festive 20%","valid_to":"2026-07-01"}],
  "policies":{"refund":"...","cancellation":"..."},
  "products":[{"id":"p1","name":"Bridal package","price_text":"₹25k","summary":"..."}],
  "faqs":[{"q":"Parking?","a":"Valet available"}],
  "objections":[{"q":"Too pricey","a":"..."}],
  "documents":[{"id":"d1","kind":"policy","scope":"business","kb_version":2}] }
```

---

## 3. INTERFACES — `brain.py` (the ONE read/write facade)

New sibling module, import-safe (mirrors `auth.py`: `init()`, `available()`, no
module-level env reads, graceful no-op when store/PG/embeddings absent). It is the
**only** thing campaigns / voice-precompute / WhatsApp / support / AI Manager call.

### 3.1 Read surface (what every worker consumes)

```python
def get_profile(org_id: str) -> dict:
    """Full merged Brain (parent + products + faqs + objections + doc index).
    One point-read (file or indexed PG). {} if no brain yet. NEVER raises."""

def merge_defaults(defaults: dict, user: dict) -> dict:
    """Fill-when-MISSING-OR-EMPTY merge (NOT shallow {**d,**u}). For each known
    field, take user[k] only if non-empty (str != '', non-empty list/dict),
    else fall back to defaults[k]. This is what makes inheritance survive a form
    that posts blank fields as ''/[]. Unknown keys pass through from user."""

def resolve_campaign_defaults(org_id: str) -> dict:
    """THE KEY FUNCTION. Returns a dict in EXACTLY the _coerce_fields shape:
    {company_name, agent_name, product_name, product_summary, location, price_offer,
     usps[], talking_points[], qualifying_questions[], objections[{q,a}],
     negotiation_ladder, closing_lines[], escalation_rules, persona, disclose_ai,
     ai_disclosure, language, call_window_*}.
    Built from business_brain + the business's products/faqs/objections.
    Empty business -> {} (campaign creation behaves exactly as today)."""

def resolve_worker_context(org_id: str, role: str, channel: str = "") -> dict:
    """Channel-shaped context for non-campaign workers. role in
    {whatsapp_sales, support, creative, strategist, booking}. Returns
    {identity, brand_tone, languages, usps[], offers[], faqs[], objections[],
     policies{}, products[], do_not[]} trimmed for that role. Support gets FAQ+policy
     heavy; creative gets brand+USP+offer heavy; etc."""

def retrieve(org_id: str, query: str, k: int = 4,
             scope: str = "business", campaign_id: str = "") -> list[dict]:
    """Thin wrapper over rag.retrieve (dynamic-context-rag.md §4b) that ALSO matches
    business-scoped chunks (campaign_id='__brain__'). Returns [{content,section}].
    [] when embeddings degraded -> callers no-op. NOT called on the voice hot path
    (voice uses the precomputed blob); used by WhatsApp/support/strategist live."""
```

### 3.2 Write surface (dashboard + AI Manager + Industry Packs)

```python
def upsert_profile(org_id, patch: dict, actor: str) -> dict   # merges, bumps version, audits
def upsert_product(org_id, product: dict, actor: str) -> dict
def add_document(org_id, doc: dict, actor: str) -> dict        # stores raw -> enqueues index (Hatchet)
def upsert_faq(org_id, faq: dict, actor: str) -> dict
def upsert_objection(org_id, obj: dict, actor: str) -> dict
def seed_from_industry_pack(org_id, pack: str, actor: str) -> dict  # §6
def completeness(org_id) -> dict   # {score, missing:[...]} (§4.3)
```

Every write: validate → write through `store.py` (MODE-routed) → `version += 1` →
if it changes knowledge text, mark affected docs `chunked=false` + bump `kb_version`
(busts RAG cache, `dynamic-context-rag.md §4b`) → enqueue re-index → `audit.record`.

> ⚠️ **CACHE-INVALIDATION SCOPE — a business-scope reindex must bust EVERY
> campaign's RAG cache, not one.** The RAG cache is keyed
> `(tenant_id, campaign_id, stage)` (`dynamic-context-rag.md §4b`). A *brain*
> document (`scope='business'`, `campaign_id='__brain__'`) is retrieved into
> retrieval for ALL of that tenant's campaigns, so a per-campaign `kb_version`
> bump does NOT cover it. **Rule:** a business-scope (`__brain__`) reindex bumps a
> **tenant-level `brain_kb_version`** that participates in EVERY campaign's cache
> key (effective key = `(tenant_id, campaign_id, stage, campaign_kb_version,
> brain_kb_version)`). One brain-doc edit therefore invalidates all of that
> tenant's precomputed blobs and they recompute lazily on next dial. (Product- or
> campaign-scoped docs keep using the existing per-campaign bump.)

### 3.3 Endpoints (added to `caller.py`, RBAC + tenant-scoped)

```
GET    /brain                      -> get_profile(tenant)              (read role ok)
PUT    /brain                      -> upsert_profile (write role)      [audited]
GET    /brain/products             | POST /brain/products              [write]
GET    /brain/documents            | POST /brain/documents (paste/upload/url)
GET    /brain/faqs    | POST /brain/faqs
GET    /brain/objections | POST /brain/objections
POST   /brain/seed-industry        -> seed_from_industry_pack          [write]
GET    /brain/completeness         -> {score, missing[]}
POST   /brain/reindex              -> re-embed all docs (Hatchet)      [write]
```

`resolve_tenant(request)` gates all (P1: tenants.json is auth source of record);
`can(t,"write")` gates writes (RBAC already in `caller.py`).

---

## 4. HOW EACH AI WORKER CONSUMES THE BRAIN

### 4.1 Campaign creation / Campaign Strategist (the primary reuse)

`POST /campaigns` (`caller.py:1949`) changes by a few flag-gated lines:

```python
fields = _coerce_fields(raw)
if BRAIN_DEFAULTS_ENABLED and brain.available():
    defaults = brain.resolve_campaign_defaults(t["tenant_id"])   # never raises, {} if no brain
    fields = _coerce_fields(brain.merge_defaults(defaults, raw)) # fill-only-when-MISSING-OR-EMPTY
```

> ⚠️ **MERGE SEMANTICS — load-bearing, do NOT use a shallow `{**defaults, **raw}`.**
> The campaign form posts a *full* JSON; fields the user left blank arrive as
> `""` / `[]` / `{}`, NOT as absent keys. A shallow spread lets those empties
> **clobber** the brain defaults, silently defeating inheritance. `merge_defaults`
> is therefore a **per-field fill-when-missing-or-empty** merge: take the user
> value only if it is non-empty (`!= ""`, non-empty list/dict), else fall back to
> the brain default. (Verify against how the live frontend actually serialises a
> blank field before locking the rule; if the form omits blanks entirely a shallow
> spread would suffice, but the safe default is the empty-aware merge.) The §9.2
> acceptance test MUST exercise a `raw` that includes `price_offer:""` and
> `usps:[]` and assert the brain values survive — the naive test that only passes
> the keys it wants would hide this bug.

Result: a campaign inherits brand voice, agent name, AI-disclosure policy, call
window, objection bank, persona, closing lines, default USPs — the vendor only
supplies what's new (this product, this price, these leads). `build_system_prompt`
is untouched; it just receives a richer `f`. **Flag off ⇒ `fields = raw` ⇒
identical to today.** This is the write-once-inherit-everywhere win and the single
biggest unblock (every campaign across every module).

The **Campaign Strategist** agent calls `get_profile` + `retrieve` to propose
campaigns grounded in the real catalog/offers instead of a free-text brief — and
the existing `extract_fields` (`caller.py:773`) can be seeded with the Brain so its
Groq extraction starts from real business data, not a blank brief.

### 4.2 Voice (AI Telecaller) — NO new hot-path

Brand/persona/objections arrive via 4.1 (already baked into the campaign `f`, in
the **cached prefix**). Deep document knowledge arrives via the **existing**
dial-time RAG precompute (`dynamic-context-rag.md §4b`), which now also retrieves
business-scoped chunks (`campaign_id IN (<cid>, '__brain__')`). The agent still
just reads `var/rag_context/<room>.json` and injects once at the recap seam
(`agent.py:372-378`). **The agent imports nothing new; zero hot-path change**
(this is the non-negotiable constraint from `dynamic-context-rag.md §0`).

### 4.3 WhatsApp salesperson / Support agent — live read

These run in `caller.py`/Hatchet (NOT the latency-critical voice loop), so they may
call `brain.resolve_worker_context(org_id, role)` + `brain.retrieve(org_id, query)`
**live** to ground each reply. The existing WhatsApp AI draft path
(`caller.py:799 _groq_chat`, `caller.py:1143-1170` which already pulls
`company_name`/`product_summary` from campaign fields) gets its system message
prefixed with the Brain identity/FAQ/policy block. Support answers FAQ/policy from
`brain_faq`+`brain_document` first, escalates to human only on miss (Human
Handover with an AI summary).

### 4.4 Creative / Ads / Landing — brand-grounded generation

`resolve_worker_context(org_id, "creative")` returns identity + brand_tone +
USPs + offers + product media → fed as the grounding prompt to the creative
engines (`creative-*.md` docs). Ensures every ad/banner/landing/brochure uses the
real business name, tone, offer, and pricing — no hallucinated brand.

### 4.5 AI Manager — intent grounding + defaults

AI Manager tools (`automation-aimanager.md`) call `get_profile` to (a) fill action
defaults and (b) **resolve natural-language intent against real data**: "launch a
campaign for my 2BHK" → match against `brain_product` (category/name); "increase
the festive offer" → match `offers[]`. Risky writes (pricing, offers, identity)
still go through the AI Manager's PIN/approval + budget gates; the Brain is the
*read* context, not a bypass.

### 4.6 Completeness score (onboarding + safety)

`completeness(org_id)` returns `{score 0..100, missing:[...]}` from presence of:
identity, ≥1 product w/ price, ≥1 FAQ, objection bank, brand_tone, disclosure
policy, call window. Drives the onboarding checklist AND a **safety gate**: an AI
worker may refuse/soft-degrade an autonomous action when the Brain is too sparse to
act faithfully (e.g. "no pricing on record → don't quote a number; offer a
callback"). This is the platform-level guard against confident hallucination.

---

## 5. SAFETY / GUARDRAILS

1. **Tenant isolation (hard).** Every table `FORCE ROW LEVEL SECURITY`, policy
   `org_id = current_setting('app.tenant_id')`, app runs as NOSUPERUSER/NOBYPASSRLS
   `famit_app`, `SET LOCAL app.tenant_id` inside each txn (P1 §1.4). The Brain is
   the highest-value tenant data — one bug here leaks a competitor's pricing/leads.
   RLS is enforced *and* tested (acceptance §9 includes a cross-tenant read attempt
   that must return zero rows). JSON-mode files are per-org (`var/brain/<org_id>.json`)
   — no shared file key (avoids the `memory.py` cross-tenant-bleed class of bug,
   `p1-postgres.md §0`).
2. **Versioned identity, audited writes.** Identity/pricing/policy are load-bearing
   for autonomous AI; a silent rewrite is dangerous. Every write bumps `version`,
   stores the prior `data` snapshot (in an append-only `var/brain/<org>.history.jsonl`
   / future `brain_version` table) and emits `audit.record("brain.<verb>", ...)`.
   The AI Manager can read freely but every Brain WRITE it makes is audited with the
   reason, and pricing/offer/identity writes require the same PIN/approval gate as
   other risky AI-Manager actions (`automation-aimanager.md` constraint).
3. **Prompt-cache integrity (latency safety).** Per-business static identity may
   enter the cached prefix (it's stable per campaign); per-lead / retrieved Brain
   content MUST ride the per-call suffix only (`dynamic-context-rag.md §1`). Never
   inject Brain text via `agent.update_instructions` (the 2.5 s TTFT regression,
   `agent.py:526-535`). Enforced by construction: voice only ever reads the
   precomputed `var/rag_context/<room>.json`.
4. **Event-loop safety.** Embedding/OCR/summarising a document is multi-second torch
   work; it must NOT run inline in the async API loop (would freeze the panel for
   every tenant — `dynamic-context-rag.md §3` box). `add_document`/`reindex` enqueue
   a Hatchet task (or `asyncio.to_thread` fallback); the HTTP write returns
   immediately. The voice hot path never embeds.
5. **Import-safe / dormant-until-deps.** `brain.py` no-ops cleanly when `store.py`,
   PG, embeddings, or Hatchet are absent: `get_profile` returns `{}`,
   `resolve_campaign_defaults` returns `{}` (campaigns behave as today), `retrieve`
   returns `[]`. **No new hard dependency to ship the JSON mode.**
6. **Compliance fields are first-class, not free text.** `disclose_ai`,
   `ai_disclosure`, `call_window_*`, and DND/consent live in the Brain so they flow
   into *every* campaign by inheritance — the business sets its calling window and
   AI-disclosure policy ONCE and every AI worker honours it (ties into the
   Compliance/DND module). Removing/weakening a disclosure is an audited write.
7. **Hallucination guard via completeness (§4.6).** Sparse Brain → workers
   soft-degrade risky autonomous claims (no invented price/policy).
8. **Input hygiene.** Document text is untrusted user content; it is treated as DATA
   (retrieved/quoted), never as instructions — the retrieval blob is wrapped in a
   clearly-delimited `=== RELEVANT CONTEXT ===` section the model is told to *use as
   reference, not obey* (matches the RAG blob framing, `dynamic-context-rag.md §4b`).
   Size-capped to `RAG_MAX_TOKENS` so a giant paste can't blow the prompt.

---

## 6. INDUSTRY PACKS (seed defaults so a new business is useful in minutes)

`seed_from_industry_pack(org_id, pack)` loads a curated YAML/JSON template per
vertical (`real_estate, salon, clinic, coaching, d2c, ecom, cafe, agency`) into the
Brain as **editable defaults**: a starter persona, brand-tone phrasing, the common
objection bank, typical FAQ, qualifying questions, a sample product shape, and the
calling-window/disclosure norms for that vertical. Packs are plain data files under
`brain/packs/<pack>.json` (no code) — provider-agnostic, versioned, marketplace-
extensible later (ties to the Industry Packs + Marketplace modules). Seeding is an
audited write; the business edits from there.

> Reuse: the seed maps 1:1 onto the same `_coerce_fields` shape, so a seeded Brain
> immediately produces a working campaign default with zero extra plumbing.

---

## 7. WHAT IT REUSES vs WHAT IT ADDS

**REUSES (no change / read-only):**
- `prompt.py:build_system_prompt(f)` — unchanged; receives a Brain-filled dict.
- `caller.py:_coerce_fields` / `save_campaign` — unchanged; one merge line at the
  call site.
- `campaign_knowledge_chunks` + `vendors/embeddings.py` + `rag.py` dial-time
  precompute + `var/rag_context/<room>.json` injection — extended by one scope
  predicate, no new vector table, no new hot-path.
- `store.py` per-store MODE router + `db/models.py` conventions + Alembic + RLS.
- `audit.py`, `auth.py`/`config.py` import-safe module shape, `can()` RBAC.
- Hatchet spine for heavy indexing (with `to_thread` fallback).
- AI Manager tool registry, WhatsApp `_groq_chat` draft path, creative engines.

**ADDS (new, surgical):**
- `brain.py` (the facade) + `brain/packs/<vertical>.json` data files.
- 5 Postgres tables + Alembic `0003_business_brain.py` + RLS lines (verbatim
  pattern) — but JSON-mode (`var/brain/<org_id>.json`) ships first; PG is strangler.
- New endpoints under `/brain/*` in `caller.py`.
- Two flag-gated lines in `POST /campaigns` (4.1).
- One extra scope predicate in `rag.retrieve` (`campaign_id IN (cid,'__brain__')`).
- Completeness scorer + version history (append-only JSONL → later `brain_version`).

Net new hard dependencies to SHIP (JSON mode): **none.** PG/pgvector/Hatchet are
the same dormant-until-creds plane the rest of the platform already targets.

---

## 8. DEPENDENCIES

- **Hard, already present:** Python stdlib, `store.py` (or its JSON fallback),
  `audit.py`, FastAPI/uvicorn (`caller.py`), `resolve_tenant`/`can` RBAC.
- **Soft (dormant-degrade):** Postgres+pgvector + `db/engine.py` (PG mode),
  `vendors/embeddings.py` BGE-M3 (document RAG; absent → docs stored but not
  retrievable, structured Brain still works), Hatchet (heavy indexing; absent →
  `asyncio.to_thread`), file/OCR libs for uploads (absent → paste/url only).
- **No new vendor key required to ship.** Embeddings are self-hosted BGE-M3
  (`dynamic-context-rag.md §3`); the platform's existing Groq key powers the
  optional Brain-assisted extraction.

---

## 9. OFFLINE ACCEPTANCE TEST (no network, no LLM key, no live box)

A deterministic pytest suite (`backend/tests/test_brain.py`) that runs with
`STORE_MODES` unset (JSON mode) and `EMBED_PROVIDER` unconfigured (RAG degrades
cleanly) — proving the ship-first path works with zero external deps.

1. **Degrade-to-today (the non-breaking proof).** With no brain file present:
   `brain.resolve_campaign_defaults("org_x") == {}`; feeding `POST /campaigns`
   logic `{**{}, **raw}` yields a campaign byte-identical to today. **Asserts the
   flag-off / empty-brain path changes nothing.**
2. **Inherit-and-override + EMPTY-CLOBBER GUARD.** Seed `var/brain/org_x.json` with
   brand_tone, agent name, an objection bank, a USP list. `resolve_campaign_defaults`
   returns them in `_coerce_fields` shape. Build a **realistic form `raw`** that
   includes BOTH a populated override AND blanks the user left empty:
   `{"product_name":"2BHK","price_offer":"₹85L","usps":[],"company_name":"",
   "objections":[]}`. `merge_defaults(defaults, raw)` MUST: keep
   `product_name/price_offer` from the user, BUT preserve `usps`/`company_name`/
   `objections` from the brain (the `''`/`[]` must NOT clobber). Assert this
   explicitly — a shallow `{**defaults, **raw}` FAILS this case and the test must
   catch it. Then `_coerce_fields` → `build_system_prompt` → assert the rendered
   prompt contains the inherited company/tone/objections AND the user's product/
   price (proves the prompt seam consumes the correctly-merged Brain content).
3. **Worker context shaping.** `resolve_worker_context(org_x,"support")` returns a
   FAQ/policy-heavy dict; `(...,"creative")` returns a brand/USP/offer-heavy dict;
   assert role-appropriate keys present/absent.
4. **RLS / isolation (logic-level).** With two org files `org_a`,`org_b`,
   `get_profile("org_a")` never returns `org_b` content; the JSON path is per-org
   keyed (no shared file). (PG-mode RLS test — cross-tenant SELECT returns 0 rows —
   runs in the P1 RLS integration suite when PG is present, skipped offline.)
5. **Versioning + audit.** `upsert_profile` bumps `version`, appends a history
   record, and calls `audit.record` with `action="brain.update"` (assert via a stub
   audit sink). A second write bumps to v3 and the prior snapshot is recoverable.
6. **Completeness.** Empty brain → low score + `missing` lists identity/products/
   pricing/disclosure; a fully-seeded brain → score ≥ threshold and `missing == []`.
7. **Industry pack seed.** `seed_from_industry_pack(org_y,"salon")` produces a Brain
   whose `resolve_campaign_defaults` yields a non-empty, coercible field dict
   (round-trips through `_coerce_fields` without error).
8. **RAG degrade.** With embeddings unconfigured, `add_document` stores the doc and
   `retrieve()` returns `[]` (no crash); the structured Brain (FAQ/objection/
   identity) is unaffected. **Asserts document-RAG is dormant-safe.**

All eight are pure-function / in-memory; none touches the box, a socket, or a model.

---

## 10. BUILD ORDER (crash-safe units, each independently verifiable)

1. **U1 — `brain.py` JSON core + read facade** (`get_profile`,
   `resolve_campaign_defaults`, `resolve_worker_context`, `completeness`) over
   `store.py` JSON mode. Verify: acceptance §1,§2,§3,§6. *Ships value alone — campaign
   inheritance works with zero PG.*
2. **U2 — write facade + endpoints + versioning + audit** (`/brain/*`). Verify §5,
   §endpoints, RBAC.
3. **U3 — campaign merge wiring** (2 flag-gated lines in `POST /campaigns`) + flag
   `BRAIN_DEFAULTS_ENABLED`. Verify §1,§2 end-to-end; flag-off byte-identical.
4. **U4 — Industry Packs** (`brain/packs/*.json` + `seed_from_industry_pack`).
   Verify §7.
5. **U5 — document RAG bridge** (`add_document` → chunk/embed into
   `campaign_knowledge_chunks` w/ `campaign_id='__brain__'`; `retrieve` scope
   predicate; voice precompute folds business scope). Verify §8 + the RAG
   acceptance from `dynamic-context-rag.md`. Off the loop (Hatchet/to_thread).
6. **U6 — Postgres tables + Alembic `0003` + RLS + backfill + shadow_diff** (strangle
   JSON→dual→pg). Verify shadow_diff==0 before any cutover (P1 protocol).
7. **U7 — worker integrations** (WhatsApp/support/creative/AI-Manager call
   `resolve_worker_context`/`retrieve`). Each behind its own flag; verify per worker.

Stop after any unit and the system is consistent (every unit is flag-gated and
degrades to today).

---

## 11. MODULES THIS UNBLOCKS

Directly: **Business Brain** (this module's UI), **Campaigns** (inherited defaults),
**AI Voice Calls** (grounded prefix + business-scope RAG), **WhatsApp Automation**
(grounded drafts), **Customer Support** (FAQ/policy answers + handover),
**Creative Studio / Ad Automation / Website-Landing / 3D Studio** (brand-grounded
generation), **AI Manager** (intent grounding + defaults), **Industry Packs**
(seed source), **Knowledge Base** (the document store IS the KB), **Compliance/DND/
Consent** (disclosure + call-window inheritance). Indirectly every workforce role
(Campaign Strategist, Creative Producer, CRM/Booking/Billing/Analytics managers)
that "reads the Business Brain before acting" now has a concrete API to read.

---

## RED-TEAM FIXES (folded)

An adversarial review verified the load-bearing source claims against live
`droplet_work/` and the sibling design docs, and folded the findings below as
**decisions** (not open questions). Verdict: **GO with conditions.** Nothing here
is architectural; all are surgical and consistent with STRANGLE & EVOLVE.

**RT-0 — Source citations corrected (claims verified, line numbers were stale).**
The *facts* in this spec check out against live source, but three line refs were
wrong and are corrected here so a builder doesn't chase ghosts:
- `build_system_prompt` **`prompt.py:253`** ✓; its field list (`usps,
  talking_points, qualifying_questions, objections, objection_bank,
  negotiation_ladder, closing_lines, escalation_rules, persona, disclose_ai,
  ai_disclosure, ...`) ✓ verified `prompt.py:253-307`.
- `_coerce_fields` **`caller.py:1876`** ✓ — and note it **always fills every key
  with a default** (e.g. `agent_name→"Riya"`, `usps→[]`, `objections→[]`). This is
  *why* `merge_defaults` MUST run on the **un-coerced `raw`** (RT-1), before
  defaults mask the user's blanks.
- `POST /campaigns` create handler **`caller.py:1949`** ✓; it coerces at line 1964.
  There is also a **`POST /campaigns/{cid}` update handler at `caller.py:2040`**
  that re-coerces + `build_system_prompt` — see RT-3.
- The RAG/agent seam refs were stale: the recap-injection seam is
  **`agent.py:466-472`** (appends to `base_instructions`, not `update_instructions`),
  and the "`update_instructions` ⇒ 2.5 s TTFT regression" note lives at
  **`agent.py:660`** (this spec cited 372-378 / 526-535). The *mechanism* the spec
  relies on — inject by extending the static instruction block, never via
  `update_instructions` — is correct; only the addresses were wrong.

**RT-1 — Empty-aware merge is correct AND order-critical (decision, not a maybe).**
The §4.1 caveat "verify how the frontend serialises a blank field before locking
the rule" is downgraded to a note: the **empty-aware `merge_defaults` is the chosen
rule unconditionally**, because it is robust under *both* serialisations (form
posts blanks as `""`/`[]`, OR omits them entirely) — a shallow `{**d,**u}` is only
safe under one. Additionally, **`merge_defaults(defaults, raw)` MUST run on the raw
pre-coercion dict**; running it after `_coerce_fields` would let coercion's own
defaults (`"Riya"`, `[]`) clobber the brain (a custom `agent_name` would be
overwritten by `"Riya"`). The §4.1 snippet already does this correctly
(`_coerce_fields(brain.merge_defaults(defaults, raw))`); this fix makes the
ordering a hard invariant and the §9.2 empty-clobber test the gate on it.

**RT-2 — `brain.write` is a NEW firewall scope; "same PIN gate" is a BUILD
PREREQUISITE, not a freebie (binding safety condition).** The reused Action
Firewall (`credit-ledger-firewall.md` → `firewall.py`, `require_step_up(scope)` /
`mint_step_up`) today registers **money/outreach** scopes only (`campaigns.create`,
`ads.set_budget`, `whatsapp.send`, …). A Brain identity/pricing/policy write is
*not* in that registry. **Decision:** a new scope **`brain.write`** is registered in
`require_step_up` and **no AI-Manager Brain-write path (U2 write surface used by the
Manager, U7) ships until that scope exists.** Furthermore, **compliance writes are
gated harder than spend**: flipping `disclose_ai → false`, editing `ai_disclosure`,
or widening `call_window_*` silently re-grounds *every* worker and can breach
DND/disclosure law across *all* campaigns — strictly more dangerous than a single
ad-budget bump. These specific fields require **explicit re-confirmation + audit
with the prior value**, not merely a `version` bump. The Brain remains a *read*
context for the AI Manager; every *write* it makes is `brain.write`-gated, audited
with reason, and reversible from version history.

**RT-3 — Inheritance is CREATE-TIME SNAPSHOT, not live mutation (scope-honesty
headline; corrects "inherited everywhere").** `build_system_prompt` feeds the
Groq-**cached prefix**, which must be stable per campaign. Therefore brain defaults
are **resolved and baked into the campaign's stored `fields` at create-time**
(`POST /campaigns`, `caller.py:1949`). A *later* brain edit does **NOT**
retroactively rewrite existing campaigns' prompts. This is the deliberate, correct
semantic and it resolves the update-handler gap: the **`POST /campaigns/{cid}`
update handler (`caller.py:2040`) intentionally does NOT brain-merge** — it edits
the campaign's own (already-inherited) snapshot, so editing a campaign never
silently re-pulls or drops brain defaults. Live propagation of a brain edit reaches
running operations through exactly three honest channels: **(a)** new campaigns
inherit the new defaults; **(b)** RAG retrieval re-grounds via the `brain_kb_version`
bust (§3.2) — documents/knowledge ARE live; **(c)** live-read workers
(WhatsApp/support/creative/AI-Manager) call `resolve_worker_context`/`retrieve` per
action and see edits immediately. The over-broad "inherited-everywhere, instantly"
reading is corrected to: **structured identity/voice fields = snapshot-at-create;
knowledge + live-channel context = live.**

**RT-4 — Folding `__brain__` into the ANN top-k changes RANKING, not just rows
(retrieval-quality guard).** §4.2's "one extra `OR campaign_id='__brain__'`" is not
cost-free: the live retrieval is `ORDER BY embedding <=> qvec LIMIT RAG_TOP_K`
(`dynamic-context-rag.md §4b`, `campaign_knowledge_chunks`), so business chunks now
**compete with campaign chunks for the same `TOP_K` slots** — rich brain docs could
crowd out campaign-specific content (or vice-versa). **Decision:** retrieval uses a
**per-scope budget**, not a blind union — reserve the majority of `TOP_K` for
`campaign_id=<cid>` and a small fixed quota (e.g. 1 of 4) for `__brain__`, OR run
two scoped queries and merge; the campaign's own content stays dominant. The
`brain_kb_version` cache-bust (§3.2) stands and is required because the new-lead
cache collapses by `(tenant_id, campaign_id, stage='new')` with no per-doc version
(`dynamic-context-rag.md §4b`, finding F6).

**RT-5 — JSON-mode isolation is CALL-SITE convention, not enforced RLS (ship-first
honesty).** §5.1's FORCE-RLS guarantee only fires in **PG mode, which ships later**
(U6). In the **ship-first JSON path**, tenant isolation is by-construction:
**`org_id` is ALWAYS derived from `resolve_tenant(request)` and NEVER read from a
request body/param** — no endpoint accepts a caller-supplied `org_id`. The PG
cutover then adds the *enforced* backstop (FORCE RLS + `NOBYPASSRLS famit_app`).
The §9.4 isolation test is extended to assert that no `/brain/*` endpoint honours a
body-supplied `org_id` (i.e. a tenant cannot read another's brain by spoofing the
field), not only that the facade doesn't cross-read.

**RT-6 — Load-whole-profile assumes a SMALL catalog; large catalogs (ecom/d2c) need
a query path (residual inconsistency, named).** `get_profile` /
`resolve_campaign_defaults` load the **entire** brain (all `brain_product` rows from
`data jsonb`) on every campaign-create and worker-read, and stuff products into the
field dict. That is correct for salon/clinic/real-estate/coaching (a handful of
SKUs) but **breaks for the `ecom`/`d2c` verticals §6 lists** — a real catalog is
thousands of SKUs, which blows both the point-read and the prompt size.
**Decision:** the load-all model is explicitly scoped to **small-catalog
businesses** for the shipping phases; large catalogs use a **`brain_product` query
path (by `category`/`sku`/active, index `(org_id,active)` already defined §2.2)**
fronted by `retrieve()` over product docs — products are *retrieved by relevance*,
not loaded whole, exactly as documents are. `resolve_campaign_defaults` caps the
inlined product list (e.g. top-N by recency/active) and never inlines a full ecom
catalog. Tracked as the one known scaling boundary; non-blocking for the first
verticals.

### VERDICT: GO (conditions binding)

Reuse is genuine, not a rebuild: the spec **feeds** `build_system_prompt`, the
campaign store, the `store.py` strangler, the pgvector/BGE-M3 RAG plane, and the
`firewall.py`/wallet gates — all verified in live source or the settled design
docs. It sits on the foundation, is flag-gated/byte-identical-off, and is honestly
scoped after the corrections above.

**Conditions that MUST hold (build-order gates):**
1. **RT-2** — register `brain.write` step-up scope (and harden compliance-field
   writes) **before** any AI-Manager Brain-write unit ships. *(Highest priority —
   this is the spend/PIN safety the module turns on.)*
2. **RT-3** — implement inheritance as create-time snapshot; do NOT brain-merge the
   update handler; document the three live-propagation channels in the UI copy so
   the founder isn't surprised that editing the brain doesn't rewrite live campaign
   prompts.
3. **RT-1** — `merge_defaults` runs on un-coerced `raw`; the §9.2 empty-clobber
   test is the gate.
4. **RT-4** — per-scope retrieval budget (don't let `__brain__` evict campaign
   chunks); ship only after the RAG precompute plane (`dynamic-context-rag.md`)
   actually exists — U5 depends on a *built*, not merely *designed*, RAG plane.

**Residual risks (accepted, non-blocking):** RT-6 large-catalog load-all boundary
(ecom/d2c); the spec layers on RAG + firewall + `brain_kb_version` planes that are
**designed but not yet built** — sequence accordingly (U1–U4 stand alone on JSON
mode and the existing campaign/prompt seam; U5/U7 wait on their upstream planes).
