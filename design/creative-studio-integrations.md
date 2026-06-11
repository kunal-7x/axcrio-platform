# DESIGN SPEC — CREATIVE STUDIO ▸ **PLATFORM INTEGRATIONS** (master spec §32–34)

> **Status:** EXECUTION-READY DESIGN (READ-ONLY wave — this doc writes NO app code, edits no
> `caller.py`/`agent.py`, does NO git). It specifies **how the dedicated AI Asset Service plugs into the
> rest of the platform** — WhatsApp, Adbot/ads-engine, AI Manager, Workflow automation,
> performance-learning, and the cross-platform asset library. It is the **connective-tissue** spec that
> sits ABOVE the already-shipped sibling design docs and **wires them together without re-specifying what
> they own**.
>
> **Authoritative parent:** `CREATIVE_STUDIO_MASTER_PROMPT.md` (42 DNA sections + the architecture
> decision). **The decided architecture (do not relitigate):** the **AI Asset Service is a dedicated
> coarse SERVICE** — own process, own Postgres schema `ai_asset_*` (FORCE-RLS, admin-GUC), own port,
> Hatchet (F3) async job queue, DO Spaces storage (interim = box filesystem), a **model-agnostic
> `Provider` abstraction** (OpenRouter = the FIRST impl, not the architecture). Creative Studio (the UI)
> stays in the panel. It REUSES `wallet.py` (credit holds), `audit.py`, RLS, and Hatchet. Co-located on
> the live box now (droplet 3/3), extractable later.
>
> **Siblings this doc connects (already designed — cite, do not duplicate):**
> `design/creative-asset-library.md` (the canonical asset store + `AssetRef`),
> `design/creative-ads-engine.md` (the variant→test→scale→kill autonomous loop = "Adbot"),
> `design/creative-whatsapp-creative.md` (WhatsApp kit packaging + delivery),
> `design/platform-ai-manager.md` + `design/aim-architecture.md` (voice/chat command brain, `creative.py`
> adapter + `creative_pack` worker + `target_module='creative'`),
> `design/platform-ai-workforce.md` (the `creative` role + `ToolSpec` registry),
> `design/platform-workflow-studio.md` (the durable node engine; Action nodes call `ToolSpec` tools),
> `design/automation-image.md`/`-video.md` (the media engines), `design/media-gen.md` (engine layer).

Research/verification date: 2026-06-11. Verified against the live sibling docs + `memory/brain/*.md`.

---

## 0. THE ONE-PARAGRAPH MODEL (read first — this is the whole integration in plain words)

Every platform plane (WhatsApp, Adbot, AI Manager, Workflows, Campaigns, Funnels, Landing) talks to the
AI Asset Service through **exactly two surfaces and never more**: (1) a small **`creative.*` tool/HTTP
contract** to *generate, edit, approve, and fetch* assets, and (2) the **Asset Library** as the
*canonical, tenant-scoped, cross-platform store* every plane reads from and writes performance back into.
Generation is **campaign-aware** (the master DNA): a caller passes a `campaign_id` (or `product_id`) and
the service infers product/audience/text/size/CTA/style from stored business data. Generation is
**async** (Hatchet job → `job_id` → poll/callback) and **credit-gated** (`wallet.py` reserve → settle).
Every asset carries `campaign_id` + `batch_id` + `variant_id`, so when it later runs as a WhatsApp send
or an ad variant, the **performance flows back to the exact asset** — and that performance becomes a
generation *input* for the next round (the learning loop). **Only `status="approved"` assets leave the
studio** (to Adbot or a WhatsApp blast) unless the tenant explicitly enables auto-mode. That is the
entire integration; the rest of this doc is the precise contract for each plane.

```
                         ┌──────────────────────────────────────────────────────────┐
   voice/chat command ──►│                 AI ASSET SERVICE (dedicated)             │
   (AI Manager)          │  Provider abstraction (OpenRouter→Leonardo/Flux/…)        │
                         │  2-stage: LLM prompt-builder ◄─campaign ctx─┐  ►image model│
   workflow node ───────►│  Hatchet async jobs · wallet holds · audit  │             │
   (Workflow Studio)     │  ai_asset_* PG schema (FORCE-RLS)           │             │
                         └───────────────┬───────────────────────┬─────┘             │
   Creative Studio UI ──►│ generate/edit/approve  (creative.* API)  │   registers     │
                         └───────────────┼───────────────────────┼─────┘             │
                                         ▼                       ▼
                              ┌─────────────────────────────────────────────┐
                              │  ASSET LIBRARY  (creative-asset-library.md)  │  ← canonical store
                              │  AssetRef{campaign_id,batch_id,variant_id,    │     (cross-platform)
                              │           status, ad_refs[], metrics{}}      │
                              └───┬───────────────┬───────────────┬──────────┘
              approved/winner ────┘   browse/attach │   read+writeback│ search/reuse
                                ▼                   ▼                 ▼
                        ADBOT / ads-engine    WhatsApp Creatives   Campaigns/Funnels/Landing
                        (variants→test→       (template+kit+       (any plane reuses an asset
                         scale/kill→metrics)    send→delivery)       by campaign/kind/platform)
                                │  CTR/CPC/ROI/conversions │ delivered/read/click/booking
                                └──────────► update_metrics() / set_status(winner|trashed) ──┐
                                                                                             ▼
                                            PERFORMANCE-LEARNING FEEDBACK  ──► next generation round
```

---

## 1. THE UNIFIED `creative.*` CONTRACT (the ONE surface every plane calls — net-new, this doc owns it)

Every integration below routes through **one** small, gated, audited, dormant-safe contract. It exists in
**two mirrored forms** so each plane uses its native calling convention, but they hit the **same service
and the same gates** — there is never a second money-path or a second tool surface:

- **As workforce `ToolSpec`s** (for the AI Manager + Workflow Action/AI-Agent nodes): registered in the
  AI-Manager / `ai-workforce` `ToolRegistry` so the deterministic risk/permission/wallet gates already
  built apply unchanged.
- **As HTTP routes** (for the Creative Studio UI + the ads-engine batch fetch + WhatsApp browse/attach):
  an `APIRouter(prefix="/creative")` on the dedicated service, auth via token-derived tenant (NEVER body
  vendor_id), `can(tenant,"write")` on mutations, audited.

### 1.1 The tool/route set (canonical names — siblings bind to THESE)

| `creative.*` tool (workforce scope) | HTTP route | Money? | Risk class | What it does |
|---|---|---|---|---|
| `creative.generate` | `POST /creative/generate` | **yes** (gen credits) | `spend` | Campaign-aware async gen of N variants of a `kind` (banner/ad_image/wa_poster/…). Returns `{job_id, batch_id, estimate_minor}`. |
| `creative.generate_video` | (routes to **Video AI**, §4.4) | yes | `spend` | NOT this service — handed to the video engine; kept in the contract only as the **router target** so the AI Manager can say "make a video". |
| `creative.edit` | `POST /creative/assets/{id}/edit` | yes | `spend` | NL edit ("make it premium", "remove price", "Hinglish", "story size") → a NEW asset VERSION (original kept). |
| `creative.regenerate` | `POST /creative/assets/{id}/regenerate` | yes | `spend` | "5 more like this" / new-angle variations. |
| `creative.approve` | `POST /creative/assets/{id}/approve` | no | `destructive`* | Flip `status` draft→approved (the gate that lets an asset leave the studio). |
| `creative.reject` | `POST /creative/assets/{id}/reject` | no | safe | Flip to rejected (feeds the learning loop §5). |
| `creative.list` / `creative.search` | `GET /creative/assets` | no | safe (read) | Tenant-scoped library search (§6) — the browse/attach + Adbot-pick surface. |
| `creative.get` | `GET /creative/assets/{id}` | no | safe (read) | One `AssetRef`. |
| `creative.send_to_whatsapp` | `POST /creative/assets/{id}/to-whatsapp` | no** | `bulk` | Hand an approved asset to the WhatsApp-creative plane (§2) — not a generation, a routing. |
| `creative.send_to_adbot` | `POST /creative/assets/{id}/to-adbot` | no** | `bulk`/`spend` | Hand approved variants to the ads-engine (§3) — the actual ad spend is gated THERE. |

\* `creative.approve` is classed `destructive` because approval is the irreversible "this may now spend
money downstream" gate — it deserves a confirm/step-up posture in auto-flows, mirroring the
ads-engine/whatsapp approval gates. \*\* the *handoff* tool itself spends nothing; the **downstream** send
(WhatsApp template) or ad launch carries its own money gate — never double-charged here.

### 1.2 The async + credit contract (every generating call obeys this — reused, not reinvented)

1. **Estimate → reserve.** Before a large gen, the service computes an estimate and calls
   `wallet.reserve(tenant_id, amount_minor:int, resource_type="creative_gen", resource_id=batch_id,
   idem_key=<run-key>)` → `hold_id|None` (the F4 signature, INTEGER PAISE, INR; see `media-gen.md` brain
   for the no-double-spend discipline). The UI/AI-Manager shows "Generating 10 banners ≈ 30 credits.
   Continue?" — the master §35 contract.
2. **Async job on Hatchet.** The service submits a durable job (F3); the caller gets `job_id` immediately
   and polls `GET /creative/jobs/{job_id}` (or receives the sibling's callback). A variant whose asset is
   still rendering stays `awaiting_asset` and **never** flows downstream.
3. **Settle / refund.** On completion `wallet.settle(hold_id, actual_minor, idem_key=...)`; on failure
   `wallet.release(hold_id)` (refund unused — master §35). `hold_backend` is tagged so settle/release hit
   the SAME minting backend (the `media-gen.md` seam-bug lesson — a JSON hold must never hit
   `wallet.settle(int)`).
4. **Audit.** `audit.record(actor=<tenant>, action="creative.generate|edit|approve|...",
   object_type="asset", object_id=<asset_id>, channel="creative", tenant_id=<tenant>, meta={...})` — the
   immutable PG `events` leg when present. Never raises.

> **Why one contract matters:** the AI Manager, every Workflow node, the ads-engine, and WhatsApp all
> generate/approve through these exact names → **one risk table, one wallet path, one audit channel, one
> RLS boundary.** No plane gets its own creative spend door. This is the §32–34 integration discipline.

---

## 2. WHATSAPP INTEGRATION (master §33 — asset → template → approval → publish; browse/attach; stays linked)

**Owner of the WhatsApp mechanics:** `creative-whatsapp-creative.md` (packaging + media/interactive
delivery + post-call trigger + per-message metering + suppression/approval gates). **This doc owns the
*seam* between that plane and the Asset Service** — the four founder-asked behaviors:

### 2.1 Browse / preview / search / filter / **attach** an asset to a WA template (no manual management)
The WhatsApp page calls `creative.search` (§6) scoped to the tenant (filter by campaign / platform=`whatsapp`
/ status=`approved` / kind=`wa_poster|banner`). The vendor picks an asset; the WhatsApp plane resolves its
bytes via the asset's `url`/`media_id` (upload-once cache, keyed `(phone_number_id, file_sha)` per the WA
spec) and **attaches it as the media header** of a template message — the founder never hand-manages files.

### 2.2 AI creates the template **from the campaign** + attaches the banner
`creative.generate(kind="wa_poster", campaign_id=...)` produces the poster; the WhatsApp plane's
`assemble_kit` composes the caption + booking-link CTA from the same campaign data and builds the **text
template** around the attached banner. One campaign → poster + template + CTA, assembled, ready to submit
to Meta for approval (template approval remains **Meta's gate** — the founder registers it; the service
cannot conjure an approved template).

### 2.3 Approval → publish flow (the asset's own gate composes with WhatsApp's)
Two gates, in order: (a) **asset approval** — only `status="approved"` assets are attachable (the
Creative Studio gate, §1.1 `creative.approve`); (b) **send approval** — the WhatsApp plane's own
`WA_CREATIVE_REQUIRE_APPROVAL` + suppression + rate caps + per-message metering. The Asset Service does
**not** re-implement WhatsApp's gates; it just refuses to surface an unapproved asset for attach.

### 2.4 The asset stays linked to its campaign (performance attribution)
Every WhatsApp send carries the asset's `campaign_id` + `batch_id` + `variant_id` (the WA spec already
tags sends this way). When delivery/read/click/booking signals return on the status webhook, the WhatsApp
plane calls `creative.update_metrics(asset_id, {delivered, read, clicks, bookings, ...})` so the **library
record of the exact poster** accumulates its WhatsApp performance — reusable and rankable next time
(`search(sort=top_ctr, platform=whatsapp)`).

> **Seam (deferred wiring, no spine edit):** the WhatsApp plane already imports the library/`AssetRef`
> contract; the only new binding is that its `assemble_kit` fetches asset bytes by `creative.get`/library
> `url` instead of re-generating, and writes back via `creative.update_metrics`. The post-call auto-send
> (`send_creative_package`, caller.py ~1248) can pull a campaign's approved poster the same way.

---

## 3. ADBOT / ADS-ENGINE INTEGRATION (master §32 — the growth loop; only approved assets go to Adbot)

**Owner of the loop:** `creative-ads-engine.md` (the variant-level experiment loop: ingest a batch →
1 ad variant per asset at small budget → measure per-variant → **scale winners / kill losers / reallocate**
under hard caps + approval gate + audit; the deterministic bandit; the 3-tier autonomy model). **This doc
owns the seam: how a creative BATCH becomes the ads-engine's input, and how performance returns.**

### 3.1 Campaign → variants → Adbot (the feed-in)
`creative.generate(kind="ad_image", campaign_id=..., n=5)` produces a labeled batch (each variant carries
its **marketing angle** + a **testing hypothesis** per master §8/§9). The ads-engine's `batch_link.fetch()`
resolves this batch — it consumes a **list of approved `AssetRef`s**, NOT raw generation. Concretely:
`creative.send_to_adbot(asset_ids[], experiment_selection)` (or the ads-engine reads
`creative.search(status="approved", campaign_id=...)` directly, exactly as `creative-asset-library.md` §8
specifies: `ads.propose_experiment()` picks `search(status="approved")` assets).

### 3.2 **Only approved assets go to Adbot** (the hard rule — master §28/§41)
The ads-engine MUST filter on `status ∈ {approved, winner}`. A `draft`/`needs-review`/`rejected` asset is
**invisible** to `propose_experiment` (it queries the approved set). Auto-mode (tenant-enabled) may relax
this to auto-approve high-score drafts, but the **default is human-approved**. This is the same content-
policy firewall the ads-engine names in its FIX A: a human (or an explicit auto-mode toggle) is always the
last gate before machine-made creative spends money or faces platform content review.

### 3.3 Kill losers / scale winners / performance back (the loop closes on the asset)
The ads-engine optimizer runs its bandit; for each variant it calls back onto the asset:
- `creative.update_metrics(asset_id, {ctr, cpc, roi, conversions, spend, impressions, synced_at})` — the
  library's `attach_ad_ref` + `update_metrics` (library §4.3), keyed by `variant_id`.
- `creative.set_status(asset_id, "winner")` for a scaled winner; `set_status(asset_id, "trashed")` (or
  `paused`) for a killed loser. The library now reflects which creative scaled vs died
  (`search(sort=top_roi)`, `search(status="winner")`).

### 3.4 More variants from winners (the growth flywheel)
When a variant is marked `winner`, the Creative Studio (or an AI-Manager/workflow trigger) calls
`creative.regenerate(asset_id, mode="more_like_winner", n=5)` — "5 more like the winner" (master §27) —
seeding the next experiment round from what actually worked. This is the **growth loop** the master spec
draws: campaign → variants → Adbot low-budget test → kill/scale → performance back → more variants from
winners.

> **Honest boundary (inherited from ads-engine §12):** the platforms' own auto-bidding owns *within-campaign*
> ML; our edge is the *cross-variant* kill/promote + the creative-regeneration-from-winners flywheel — not
> out-optimizing Meta. Net-new ad spend is human-approved; the asset's `approve`/`winner` status is the
> creative-side gate that composes with the ads-engine's spend envelope + step-up approval.

---

## 4. AI MANAGER INTEGRATION (master §33 — route `creative.*` voice/chat commands to the service)

**Owner of the command brain:** `platform-ai-manager.md` + `aim-architecture.md`. The AI-Manager already
has the exact seams: a **`creative` workforce role**, a **`creative.py` module adapter**
(`aim-architecture.md` §3.1 `adapters/creative.py`), a **`creative_pack` Hatchet worker workflow**, and
`target_module='creative'` in its action schema. The "parked creative adapters" the task references are
**these** — built as dormant seams awaiting this service. **This doc specifies how they call the new
service.**

### 4.1 Intent → `creative.*` routing (the NLU/risk/permission path, unchanged)
The AI-Manager NLU maps utterances to `creative.*` intents; the deterministic **risk table** (NOT the
model) classifies them (`aim-nlu-policy-security.md`): `creative.generate/edit/regenerate/send_to_adbot`
→ **money/`spend`** (credit-debited) → `requires_pin` per the spend ceiling; `creative.send_to_whatsapp`
→ **`bulk`** (fan-out floor); `creative.approve` → **`destructive`** (step-up). The
`AIManagerExecutionRouter` dispatches to `adapters/creative.py`, which calls the **§1 contract**. The
model is input, never authority — risk is recomputed every call.

Example voice commands (master §36) and their routing:
| Vendor says | Intent | Routes to |
|---|---|---|
| "Create 5 ad banners for this campaign" | `creative.generate(kind=ad_image,n=5,campaign_id)` | Asset Service §1 |
| "WhatsApp poster for hot leads" | `creative.generate(kind=wa_poster, segment=hot)` | Asset Service §1 |
| "Make it premium" / "remove price" / "Hinglish" | `creative.edit(asset_id, instruction)` | Asset Service §1 (new version) |
| "Send approved banner to the WhatsApp campaign" | `creative.send_to_whatsapp(asset_id)` | WhatsApp plane (§2) |
| "Make a video for this campaign" | `creative.generate_video` | **Video AI** (§4.4 routing) |
| "Make a brochure for this product" | `creative.generate_brochure` | **Brochure AI** (§4.4 routing) |

### 4.2 The adapter call shape (in-process or HTTP, per the deployment)
`adapters/creative.py` is a `ModuleAdapter` (the AIM ABC). Today the AI-Manager is in-process with the
monolith (`mod-ai-manager.md`: in-process composition, not cross-plane HTTP). Because the Asset Service is
a **dedicated service on the same box**, the adapter calls it over the **authenticated localhost loopback**
(the AIM `monolith_client.py` pattern with a scoped tenant token) — NOT a body-vendor call. The
**`creative_pack` Hatchet worker** is the durable path for bulk/long creative jobs ("make 10 banners +
5 WA angles for every active campaign") so a worker crash resumes (F3 durable) and the AIM action_run row
tracks queued→succeeded.

### 4.3 Credit + step-up reconciliation (two gates, by design)
The AI-Manager's `cost_guard` reserves on the wallet for the WHOLE command; the Asset Service ALSO holds
per its §1.2 contract. To avoid double-reserve, the **adapter passes the AIM's `idem_key`** down to
`creative.generate` so the service's reserve is idempotent against the AIM's (one logical hold, F4
`ON CONFLICT` idempotency). Step-up: a money/destructive creative command gets a firewall step-up token at
the AIM (sub==caller, F3, 300s); the Asset Service trusts the AIM's authorization for the in-process call
(the AIM is the higher-privilege gate). The service still re-checks RLS + its own wallet hold (defense in
depth — the runner re-enforces caps, `mod-ai-manager.md`).

### 4.4 Media-type routing (video → Video AI, brochure → Brochure AI — master §33/§2 OUT scope)
The Asset Service is **Phase-1 static visuals ONLY**. The AI-Manager's intent classifier routes:
`creative.generate_video` → the **Video AI** engine (`automation-video.md` / `media-gen.md` `video/client`
`submit_video_job`); `creative.generate_brochure` → **Brochure AI** (`creative-brochure-catalog.md`).
The Asset Service may produce a **cover/thumbnail/hero image** for a video or brochure (master §2 — "the
cover only"), but never the full video/PDF. This routing lives in the AIM `_INTENT_ROLE`/adapter map so the
vendor just says "make a video" and the right engine runs — the Asset Service is one target among several.

---

## 5. WORKFLOW AUTOMATION INTEGRATION (master §34 — asset gen + send as workflow nodes)

**Owner of the engine:** `platform-workflow-studio.md` (durable Hatchet interpreter; 10 node types;
Action/AI-Agent/Integration nodes call **exact `ToolSpec` tools**; the publish-time DOMINATOR safety check;
BUDGET + APPROVAL nodes). **This doc specifies the creative nodes + the two founder-named flows.**

### 5.1 Creative actions ARE workflow nodes (no new node type needed)
Because the §1 `creative.*` tools are registered `ToolSpec`s, they are usable in an **Action node**
out-of-the-box — the workflow studio "only needs the `ToolSpec`" (its §6.4 note). A "make banners" step is
an Action node wrapping `creative.generate`; "send" is an Action node wrapping `creative.send_to_whatsapp`
or `creative.send_to_adbot`. The node executor inherits the tool's `money`/`risk_class` metadata, so the
**compiler's dominator check** forces a BUDGET node (and, for the money/send steps, an APPROVAL node) on
every path — the creative spend is gated by the SAME static + runtime safety the workflow engine enforces
for any money tool. Risk is read from the `ToolSpec`, never the tenant JSON.

### 5.2 The two founder flows (master §34), as concrete graphs
**Flow A — new campaign → creative batch → approve → Adbot:**
```
Trigger(campaign.created) → [BUDGET cap=N credits] → Action(creative.generate kind=ad_image n=5)
   → Action(creative.generate kind=wa_poster n=3) → Wait(jobs done)
   → [APPROVAL human/PIN] → Action(creative.approve each) → Action(creative.send_to_adbot)
```
(The master's "new campaign → make 5 Meta + 3 WA banners → save → approve → Adbot".)

**Flow B — lead hot → select/create poster → send → wait → remind:**
```
Trigger(lead.stage=hot) → Condition(has approved hot-lead poster?)
   ─yes→ Action(creative.search status=approved kind=wa_poster segment=hot) → pick
   ─no →  [BUDGET] → Action(creative.generate kind=wa_poster segment=hot campaign_id) → [APPROVAL]
   → Action(creative.send_to_whatsapp to=lead) → Delay(1d) → Action(whatsapp.send reminder)
```
The Condition node uses `creative.search`; "select OR create" is a branch, exactly the master's
"lead hot → select/create hot-lead poster → send → wait → remind".

### 5.3 Durability + dormancy (inherited, not rebuilt)
The workflow engine is dormant-until-creds: with no Hatchet token the same interpreter runs in-process;
with the Asset Service dormant (no provider key), a `creative.generate` Action node returns
`not_configured` and the run parks/branches gracefully — never crashes. A long render parks as
`awaiting_asset` and the Wait node holds (durable `aio_wait_for_event`) until the job callback fires. The
budget node's hold_id is persisted on the run so a resumed run past the BUDGET node still sees the cap
(workflow-studio's hard-won learning).

---

## 6. THE ASSET LIBRARY AS THE CROSS-PLATFORM REUSABLE STORE (master §29/§6 — campaigns/ads/funnels/landing/WA)

**Owner:** `creative-asset-library.md` (the single canonical store; `AssetRef` superset; local-first +
DO Spaces dormant; tenant-scoped search; performance write-back). **This doc states the cross-platform
reuse contract** — the library is the substrate EVERY plane reads from and writes into, so an asset made
once is reusable everywhere and revenue-attributable.

### 6.1 One store, every plane (the reuse matrix)
| Plane | Reads (search facets) | Writes back |
|---|---|---|
| **Creative Studio** (UI) | everything (gallery + filters) | `creative.generate/edit/approve` → new `AssetRef`s |
| **WhatsApp** (§2) | `kind∈{wa_poster,banner}`, `status=approved`, `platform=whatsapp`, `campaign_id` | `update_metrics` (delivered/read/click/booking), `ad_refs` |
| **Adbot/ads-engine** (§3) | `status∈{approved,winner}`, `platform∈{meta,google,youtube}`, `sort=top_roi` | `attach_ad_ref`, `update_metrics`, `set_status(winner|trashed)` |
| **Campaigns / Run-Campaign** | `campaign_id`, `kind=banner`, `status=approved` | (reuse only) |
| **Funnels** (`mod-funnels`) | `campaign_id`, `kind∈{banner,landing_hero}` | (reuse — funnel-step creative) |
| **Landing pages** | `kind∈{landing_hero,section_image}`, `campaign_id` | (reuse hero/section images) |
| **AI Manager** (§4) | any (voice "show my banners for X") | drives generate/approve via §1 |

### 6.2 Reuse semantics (the rules that make it cross-platform-safe)
- **Tenant-scoped ALWAYS** (RLS GUC) — a search never leaks another tenant's asset; a handoff (`to-adbot`,
  `to-whatsapp`) re-checks `AssetRef.tenant_id == token tenant`.
- **Linked forever to its campaign** — `campaign_id` is set at generation and never lost, so every reuse
  and every performance signal rolls up to the originating campaign (master §29: "every asset stays linked
  to its campaign for performance tracking + reuse").
- **Versions, not overwrites** — `creative.edit`/`regenerate` create NEW `AssetRef`s (master §41 NEVER
  overwrite old assets); the library keeps the lineage so a reused asset is always a specific version.
- **Status is the cross-plane visibility control** — `draft` is studio-only; `approved` is reusable by any
  plane; `winner` is preferred (search default-ranks winners); `trashed`/`rejected` is hidden but kept for
  audit + learning.
- **One search API** — `creative.search`/`GET /creative/assets` (the library's canonical endpoint) is what
  every plane calls; there is no per-plane asset store (the library §12 reconciliation: the video doc's
  `/creative/video/assets` is a thin alias == `?kind=video`).

---

## 7. PERFORMANCE-LEARNING FEEDBACK INTO FUTURE GENERATION (master §30/§31 — close the loop)

This is the integration that turns the platform from a generator into a **learning** designer. The signals
already flow back into each `AssetRef` (§2.4, §3.3): WhatsApp delivered/read/click/booking; ads
CTR/CPC/ROI/conversions/CPL; plus the human signals approve/reject/edit and the creative SCORE (master §30).
**This doc specifies how that history becomes a generation INPUT.**

### 7.1 The brand-performance memory (the prompt-builder's new context source)
The Asset Service's **stage-1 LLM prompt-builder** (master KEY FLOW: "an LLM builds the rich prompt from
campaign context") gains a `performance_context` input drawn from the library:
- **Best-performing style/angle for this tenant+industry** — `search(sort=top_roi|top_ctr, campaign∈tenant)`
  → the winning angle/style/CTA/language become *preferred* in the next prompt (master §13 brand memory:
  "best-performing style").
- **Rejected/trashed patterns** — assets the human rejected or the bandit trashed become a **do-not-repeat**
  signal (master §28 "rejections teach the system", §13 "do-not-use words/styles").
- **Per-angle win-rate** — the variant-angle labels (`price|location|emotion|urgency|trust|...`, master §8)
  carry their measured win-rate, so the next batch over-weights angles that historically converted for this
  vertical and under-weights losers.

### 7.2 The feedback contract (how it's wired — deterministic, not magic)
- `creative.generate` reads `performance_context = library.performance_summary(tenant_id, industry,
  campaign_id)` BEFORE building the prompt. This is a **read of the library's own `metrics`/`status`/`score`
  fields** — no new model, no new store. It biases the prompt (preferred angle/style/CTA); it never
  fabricates a claim (master §20 text-accuracy: never invent price/offer/RERA/testimonial — the learning
  loop tunes *style*, never invents *facts*).
- **Honest boundary:** the loop learns *style/angle/CTA/language* preferences from real performance; it is
  a *bias on generation*, not a guarantee of a better creative. Quality of learning is bounded by how much
  real performance data the tenant has (cold start → fall back to the industry-pack defaults, master §21).
  We never claim "AI guarantees a winning ad" — it proposes performance-informed variants for testing.

### 7.3 The full loop (one sentence)
generate (performance-informed) → approve → WhatsApp/Adbot → measure → write metrics + winner/trashed back
to the `AssetRef` → that history feeds the next `creative.generate`'s prompt-builder → **better-targeted
variants over time**. Every arrow in this loop is one of the §1 contract calls + a library read/write —
nothing bespoke per plane.

---

## 8. SECURITY / ISOLATION POSTURE FOR THE INTEGRATIONS (the boundary every seam respects)

- **Tenant from TOKEN, never body** — every `creative.*` call (tool or HTTP) derives tenant from the
  authenticated token; handoffs (`to-adbot`/`to-whatsapp`) re-assert `AssetRef.tenant_id == token tenant`
  (the `media-gen.md` dual-channel trap: overwrite `body["tenant_id"]=token`, enforce ownership on
  by-id routes). The negative control: reading vendor_id from the body must FAIL to forge cross-tenant.
- **FORCE-RLS on `ai_asset_*`** — the service owns its schema with admin-GUC RLS, like `ai_manager_*`.
  Cross-plane reads (ads-engine picking approved assets, WhatsApp browsing) run inside the tenant GUC.
- **One money-path** — generation credits via `wallet.py` (idempotent, no-double-spend); ad spend via the
  ads-engine's envelope+step-up; WhatsApp send cost via its per-message meter. No plane invents a second
  creative spend door.
- **Approval is the content-policy firewall** — `creative.approve` (or an explicit auto-mode toggle) is the
  human gate before machine-made creative spends money or faces platform review (ads-engine FIX A,
  whatsapp §6 approval gate). The default biases safe (human-approved, no auto-launch — master §41).
- **Immutable audit, channel=`creative`** — every generate/edit/approve/send/handoff/metric-writeback rows
  to `audit.py` (PG `events` leg when present); secrets redacted; the AI-Manager's decision audit
  (channel=`ai_manager`) cross-references the creative `object_id`.
- **Dormant-until-creds everywhere** — no OpenRouter key → `creative.generate` returns `not_configured`
  and every downstream plane degrades gracefully (skip-that-asset, park-the-node, show coming-soon) — never
  raises into a voice call, a workflow run, or the dial loop.

---

## 9. BUILD/WIRING SEQUENCE FOR THE INTEGRATIONS (deferred — orchestrator wires; this doc only contracts them)

Each is a small verifiable seam; none edits the spine destructively; all dormant-safe + offline-testable.
1. **Register the `creative.*` `ToolSpec`s** in the AI-Manager/`ai-workforce` `ToolRegistry` (the §1 set,
   with money/risk metadata) → the AIM + workflow Action nodes can name them. *Test: risk table classifies
   each correctly; an unapproved asset can't be sent.*
2. **Wire `adapters/creative.py`** in the AI-Manager to call the Asset Service over the loopback (scoped
   token, idem_key pass-through) + the `creative_pack` Hatchet worker. *Test: voice "make 5 banners" →
   parked-for-credit → step-up → generate; cross-tenant forge → 404.*
3. **Wire the ads-engine feed-in/feedback** — `propose_experiment` reads `creative.search(status=approved)`;
   optimizer calls `update_metrics`/`set_status(winner|trashed)`; "more like winner" via `regenerate`.
   *Test: only approved assets enter; metrics write back to the right `variant_id`; winner regen works.*
4. **Wire the WhatsApp browse/attach + writeback** — `assemble_kit` fetches by `creative.get`/library `url`;
   status webhook → `update_metrics`. *Test: attach an approved poster; suppression still blocks; metrics
   roll up to the asset.*
5. **Expose the creative nodes in the Workflow palette** (Action nodes over the `ToolSpec`s) + ship the two
   founder flows as templates; compiler dominator check forces BUDGET/APPROVAL. *Test: a money creative
   node without a dominating BUDGET node is REJECTED at publish.*
6. **Wire the performance-learning read** — `creative.generate` pulls `library.performance_summary(...)`
   into the prompt-builder. *Test: a tenant with a winning "urgency" angle gets urgency-weighted next batch;
   a rejected style is down-weighted; no fabricated facts.*

---

## 10. HONEST REAL-vs-HYPE (the integration claims, bounded)

| Claim | Reality |
|---|---|
| "One command makes + approves + launches an ad campaign" | The command **generates draft variants + assembles the package**; a human (or explicit auto-mode) **approves** before any spend or platform review. Net-new ad spend is human-gated (ads-engine §0.3). |
| "Assets auto-flow to WhatsApp/Adbot" | They flow **only when `approved`**, and the downstream send/launch carries its OWN gate (WhatsApp template approval is Meta's; ad spend is the envelope+step-up). The Asset Service routes; it doesn't bypass. |
| "It learns and gets better" | It biases generation toward **historically winning style/angle/CTA** and away from rejected ones — a real, deterministic feedback loop. It does **not** guarantee a winning creative, and cold-start tenants fall back to industry defaults. It never invents facts to "improve" a banner. |
| "Cross-platform reuse, nothing lost" | True — one tenant-scoped library, every asset linked to its campaign, versioned not overwritten, reusable by every plane. Bounded by DO Spaces being dormant until creds (local-first works ₹0 meanwhile). |
| "Voice command spends safely" | Money/destructive creative commands hit the AIM deterministic risk table → PIN/step-up + a wallet hold (idempotent). The model never authorizes; the gate does. |
| "Works offline / dormant" | The seams, gates, risk classification, and library reads/writes are pure logic and offline-testable; only the *generation quality* needs an OpenRouter (or other provider) key — the *safety + integration machinery* does not. |

---

## 15-LINE SUMMARY (for the orchestrator)

1. The AI Asset Service plugs into every plane via exactly TWO surfaces: a unified **`creative.*`
   tool/HTTP contract** (generate/edit/approve/search/handoff) and the **Asset Library** as the canonical
   cross-platform store — never a second money-path or tool surface.
2. The `creative.*` set exists as both workforce **`ToolSpec`s** (for AI-Manager + Workflow nodes) and
   **HTTP routes** (for UI/ads/WhatsApp), hitting the SAME service, risk table, wallet path, and audit.
3. Every generating call is **async (Hatchet job_id) + credit-gated (`wallet.reserve→settle/release`,
   idempotent, INR paise) + audited (channel=`creative`)** — reusing F3/F4 verbatim.
4. **WhatsApp (§33):** browse/preview/filter approved assets → attach as a template media header; AI builds
   the template from the campaign; two gates (asset-approval + WhatsApp send-approval); the asset stays
   `campaign_id`/`variant_id`-linked so delivery/read/click/booking write back via `update_metrics`.
5. **Adbot (§32):** `creative.generate(ad_image,n=5)` → ads-engine `propose_experiment` reads
   `search(status=approved)` → bandit test/scale/kill → `update_metrics` + `set_status(winner|trashed)` →
   `regenerate(more_like_winner)` — the growth flywheel. **Only approved assets reach Adbot.**
6. **AI Manager (§33):** the parked `creative` role + `adapters/creative.py` + `creative_pack` worker call
   the §1 contract over the loopback; deterministic risk (spend/bulk/destructive) gates each; idem_key is
   passed down so the wallet hold is single-charged; the model is input, never authority.
7. **Media routing:** `creative.generate_video` → **Video AI**, `creative.generate_brochure` → **Brochure
   AI** (Phase-1 service is static-visuals only; it may make the cover/hero image, never the full asset).
8. **Workflows (§34):** the `creative.*` `ToolSpec`s are Action nodes out-of-the-box; the compiler's
   DOMINATOR check forces BUDGET (+ APPROVAL on money/send) on every path — same safety as any money tool.
9. Two founder flows ship as templates: **new-campaign→make banners→approve→Adbot** and
   **lead-hot→select/create poster→send→remind** (Condition node uses `creative.search` for select-or-create).
10. **Library (§29/§6):** one tenant-scoped, RLS-forced store; assets linked-forever to their campaign,
    **versioned not overwritten**, status-gated visibility (`draft`=studio-only, `approved`=any plane,
    `winner`=preferred). One search API; no per-plane asset store.
11. **Performance-learning (§30/§31):** WhatsApp + ads + human (approve/reject/edit) + score signals write
    back to each `AssetRef`; `creative.generate` reads `library.performance_summary` into the prompt-builder
    → next batch over-weights winning angles/styles, down-weights rejected — biases STYLE, never invents facts.
12. **Security:** tenant from token (never body), FORCE-RLS `ai_asset_*`, ownership re-checked on every
    handoff, one money-path, approval = the content-policy firewall, immutable `creative` audit, dormant-safe.
13. **Honest:** "one-command campaign" is generate-draft + human-approve (not fire-and-forget); learning
    biases, doesn't guarantee; reuse is real; only generation *quality* needs a provider key.
14. **Reuse discipline:** this doc adds NO new media engine, ad adapter, WhatsApp client, or workflow node
    type — it CONTRACTS the seams between the already-designed siblings; the only net-new is the `creative.*`
    contract + the performance-feedback read.
15. **Wiring is deferred** (orchestrator-owned, §9): 6 small dormant-safe, offline-testable seams; no
    destructive spine edit; every seam degrades to `not_configured` until the provider/creds land.

### THE INTEGRATION POINTS (one-line each)
- **WhatsApp:** `creative.search`/`get` (browse+attach approved asset → template media header) +
  `creative.update_metrics` (delivery/read/click/booking writeback) — asset stays campaign-linked.
- **Adbot/ads-engine:** `creative.search(status=approved)` feed-in + `attach_ad_ref`/`update_metrics`/
  `set_status(winner|trashed)` writeback + `regenerate(more_like_winner)` flywheel; only approved go live.
- **AI Manager:** `adapters/creative.py` + `creative` role + `creative_pack` worker → §1 contract over
  loopback; risk-gated (spend/bulk/destructive); video→Video AI, brochure→Brochure AI routing.
- **Workflow Studio:** `creative.*` `ToolSpec`s as Action nodes (BUDGET/APPROVAL dominator-enforced); two
  templates (new-campaign→banners→approve→Adbot; lead-hot→poster→send→remind).
- **Performance-learning:** signals → `AssetRef.metrics/status/score` → `library.performance_summary` →
  `creative.generate` prompt-builder bias (winning angles up, rejected down; never fabricates facts).
- **Asset Library:** the canonical tenant-scoped RLS store every plane reads/writes; `creative.search` is
  the one query API; assets versioned, campaign-linked, status-gated for cross-plane visibility.
</content>
</invoke>
