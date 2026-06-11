# CREATIVE STUDIO — OUT-OF-THE-BOX FEATURE STRATEGY (senior product designer, 2026-06-11)

> **READ-ONLY DESIGN.** The founder explicitly invites proactive additions
> (`CREATIVE_STUDIO_PHASE2_SPEC.md §4`: *"Add new features out of the box no matter if
> I have told or not."*). This doc proposes + prioritizes high-value Creative Studio
> features **beyond** the explicit spec that fit the **model-agnostic asset-factory**
> architecture WITHOUT bloat. Every feature below plugs into surfaces that ALREADY
> exist in the design — the `ai_asset_*` schema, the two-stage LLM→image pipeline, the
> Provider abstraction, the S1–S11 + W1 screens, the Core_2 reference components.
>
> **Conforms to:** `CREATIVE_STUDIO_MASTER_PROMPT.md` (42 DNA sections),
> `CREATIVE_STUDIO_PHASE2_SPEC.md`, `design/creative-studio-ui.md` (S1–W1),
> `design/asset-service-backend.md` (schema/pipeline/API), `design/ui-design-principles.md`
> (the iron reuse + token rules). **Ground truth:** reference kit
> `C:\Users\kunal\Desktop\core-2-dashboard-builder-react`, panel `famit-panel/`.
>
> **The discipline (so this is additive, not bloat):** a feature qualifies ONLY if it
> (a) advances the ONE principle — *"I tell what I need, AI creates it"* — or the
> campaign→test→learn→reuse loop; (b) reuses an existing component/endpoint/table
> (≤1 additive column or endpoint each, never a new page unless it earns one); (c)
> stays dormant-safe (degrades to a calm empty state when its data/creds are absent).
> Anything failing all three is listed in §C (REJECTED / defer) and NOT built.

---

## 0. DESIGN LENS — why these and not a hundred others

The asset factory's real moat is the **loop**, not the image model: *campaign data →
N angle-labelled variants (each a hypothesis) → test → performance back → regenerate
winners → reuse everywhere*. The model is swappable (OpenRouter today, Flux/Ideogram/
Recraft/GPT-Image tomorrow — `ai_asset_providers` registry). So the highest-leverage
"out of the box" features are the ones that **deepen the loop and exploit
model-agnosticism**, because those compound and can't be copied by a thin
wrapper-over-one-API competitor. Pretty-but-shallow toys (filters, stickers, a manual
canvas editor) are explicitly OUT — they contradict the "not a design tool" principle.

Two structural multipliers shape the whole list:
- **The schema already supports versioning, scoring, usage, brand memory, metrics.**
  Most features below are a *view* + a *prompt-builder bias* on data the backend
  already persists — cheap to add, high perceived value.
- **The Provider abstraction makes "side-by-side", "make all sizes", and
  "auto-pick-best-model" nearly free** — they're fan-outs over the SAME `route()`
  ladder + `BatchSpec` cross-product that already exist.

---

## A. THE FEATURE CATALOG (15)

Each: **what it is · user value · where it plugs in (UI + architecture) · effort ·
verdict.** Effort = S (≤1 build unit, view/bias only) · M (1 endpoint or 1 schema
col + a panel) · L (new pipeline behavior + UI). "Plugs in" cites the real surface.

---

### F1 ⭐ Brand-Kit Auto-Extraction (logo / website → brand kit in one step)
- **What:** instead of the vendor hand-filling the Brand Kit (S7), they drop a **logo**
  or paste a **website / Instagram URL**; the system extracts the **palette** (dominant
  colors via a cheap pixel-quantize on the logo), **logo** (background-removed), **fonts/
  tone hint**, and **default CTA language** and pre-fills `ai_brand_kits`. One click,
  done. Vendor edits if wrong.
- **Value:** removes the single most tedious setup step; the AI immediately composites
  on-brand creatives → first generation already looks "theirs", not generic. This is the
  difference between "wow" and "meh" on the very first banner.
- **Plugs in:** **S7 Brand Kit** gets a top card "Set up from my logo / website"
  (`FieldImage` dropzone + a `Field` URL input + `Button isBlack` "Extract"). Backend:
  a new `POST /brand-kits/extract` (multipart logo OR url) → palette-quantize (pure
  Python/Pillow, no paid call for the logo path) + the existing `shared/llm` for tone/
  CTA inference + the background-remover already noted for the real HD logo. Writes the
  existing `ai_brand_kits` columns (`palette/logo_url/tone/default_cta/language_pref`).
  URL path uses the `spine_link` loopback `httpx` pattern to fetch + an LLM summarize.
- **Effort: M.** **Verdict: BUILD — TOP 5 (#1).** Highest first-impression leverage;
  reuses S7 + `ai_brand_kits` verbatim; logo-color path needs zero model spend.

---

### F2 ⭐ One-Click "Make All Sizes" (campaign-size pack from one approved creative)
- **What:** on any approved variant, **"Make all sizes →"** fans the winning concept out
  to the full platform size matrix in one action — Meta 1:1 + 4:5, IG Story 9:16, Google
  1200×628, WhatsApp square + vertical, web hero 16:9, thumbnail — re-composing layout
  per aspect (not a dumb crop). Returns a labelled **size pack**.
- **Value:** the #1 real-world chore in performance marketing is resizing one good
  creative into every placement. Doing it in one click (and re-laying-out, not cropping)
  is a headline time-saver and a direct conversion driver (correct placement sizes).
- **Plugs in:** **S11 "Resize" `Dropdown`** gains an "All sizes (pack)" item; **S6 footer**
  gets a "Make all sizes" `Button isStroke`. Architecture: this is the EXISTING
  `BatchSpec` cross-product (`creative-image-banner-studio.md §3` already expands
  job_type × sizes) re-seeded from one parent version's brief, each a new
  `ai_asset_versions` row tagged with its `size`/`platform`. Wallet estimate already
  handles N-variant holds. Library filters by `size` already exist (§12 facets).
- **Effort: M.** **Verdict: BUILD — TOP 5 (#2).** Near-free given the cross-product
  engine; enormous perceived value; pure reuse of versions + sizes + wallet.

---

### F3 ⭐ In-UI A/B Creative Test (turn a variant set into a tracked experiment)
- **What:** the angle-labelled variant set is ALREADY a testing set (each carries a
  `hypothesis`). This surfaces an **"A/B test these"** action that registers the chosen
  variants as an experiment, then shows a **live leaderboard** (impressions/CTR/CPL/leads
  per angle) once the ads/WhatsApp loop reports back — and a one-tap **"Promote winner →
  5 more like this"**.
- **Value:** closes the loop the founder cares about (test → kill losers → scale winners)
  *inside the studio*, so the vendor sees WHY an angle won and compounds it. This is the
  asset factory's actual moat made visible.
- **Plugs in:** **S5 grid** multi-select → "A/B test" `Button`; **S8 Performance** becomes
  the leaderboard (a `Tabs` "Experiment" view, `Percentage`/`CardChartPie` per angle).
  Architecture: reuses `POST /assets/{id}/attach {channel:"meta_ads", experiment_id}`
  (§7) into `ads_engine`'s existing bandit/experiment/attribution; metrics flow back to
  `ai_asset_usage.metrics` + `ai_assets.metrics` (§10). **Honesty guardrail (engine FIX
  1):** the studio only *reports*; budget caps + kill-switch stay in the ads module.
- **Effort: M (UI) / reuse (engine).** **Verdict: BUILD — TOP 5 (#3).** It's the loop;
  the engine pieces already exist; UI is a select + a leaderboard view.

---

### F4 ⭐ Model-Comparison "Generate with 2 models side-by-side"
- **What:** a power-user toggle in the **Advanced** disclosure: "Compare models" → the
  same VariantBrief renders on **two providers at once** (e.g. Ideogram vs GPT-Image vs
  the OpenRouter default), shown in paired cards so the vendor (and the system) sees which
  model wins for THIS business/style. Pick the better, the loser is discarded (or kept).
- **Value:** directly monetizes model-agnosticism — the vendor gets the best of multiple
  models without knowing model names, and the system learns a per-tenant **best model**
  for the brand kit. A thin single-API competitor literally cannot do this.
- **Plugs in:** **S2 Advanced** model selector gains a "+ compare" affordance (renders two
  `Select`s); **S5** lays paired variant cards with a small provider `Badge`. Architecture:
  the `router.route()` ladder + Provider protocol already support N providers; this just
  fans the SAME brief to two `provider_id`s (a `compare:[p1,p2]` field on the
  `GenerateSpec`/`request` JSONB). Cost = 2× per compared variant — the wallet estimate
  already sums per-variant `cost_minor`, so the "≈ credits?" gate states it honestly.
  Winner can write `ai_brand_kits.best_style`/a learned best-model bias (§10).
- **Effort: M.** **Verdict: BUILD — TOP 5 (#4).** The clearest expression of the
  architecture's value; near-free on the engine; gated behind Advanced so it never
  complicates the happy path.

---

### F5 ⭐ Asset Version Timeline (visual lineage of every edit/regenerate)
- **What:** the schema already keeps **every render as an immutable `ai_asset_versions`
  row** with `parent_version_id` lineage + the `edit_instruction` that spawned it. This
  surfaces it as a **horizontal version timeline** in S6: thumbnails left→right, each
  labelled with its edit ("premium", "remove price", "Hinglish", "9:16"), with **compare
  any two** and **roll back to any version** (flips `current_version_id`).
- **Value:** the vendor never loses a good earlier version; they can branch fearlessly
  ("make it premium" then revert), and SEE the creative evolve. Trust + exploration.
- **Plugs in:** **S6 Asset Detail** bottom — the spec already calls for a "version strip";
  this upgrades it to a true timeline with compare + rollback. Architecture: pure VIEW of
  `ai_asset_versions` (lineage, `version_no`, `edit_instruction`) + the existing approve/
  rollback that flips `ai_assets.current_version_id`. **Zero new backend** beyond a
  `GET /assets/{id}` already returning all versions.
- **Effort: S.** **Verdict: BUILD — TOP 5 (#5).** Highest value-to-effort ratio in the
  list: it's a render of data the backend ALREADY stores, and it makes the "every edit is
  a new version, original never overwritten" guarantee (master §26/§41) tangible.

---

### F6  AI Copy + Image Co-Generation (the copy is first-class, editable, exportable)
- **What:** the pipeline already generates `headline/subhead/cta` per variant. This makes
  the **copy a first-class deliverable**: a "Copy" tab on each variant with 3–5 headline/
  CTA alternates the vendor can swap *without re-rendering the image* (re-render only on
  request), plus **export copy** (for WhatsApp text, ad primary text, email subject).
- **Value:** one generation yields both the visual AND a copy bank → the vendor fills the
  ad's text fields and the WhatsApp message from the same act. Copy is where conversions
  actually move; surfacing alternates is high ROI and cheap (LLM stage 1, no image spend).
- **Plugs in:** **S6** gains a "Copy" tab (alternates as one-tap chips); **W1** "Ask AI to
  write this" pulls from it. Architecture: extends the **AIPromptBuilder** (stage 1, cheap
  text) to emit `headline_alts[]`/`cta_alts[]` into the variant brief / `ai_assets` meta;
  swapping copy is a text-layer re-render only when the vendor asks (master §10 "real text
  layer"). No new table (lives in `ai_assets`/version `meta`).
- **Effort: M.** **Verdict: BUILD (Phase-1 stretch, just below top-5).** Cheap, on-strategy,
  feeds W1 — strong #6.

---

### F7  Starter Template / Style Gallery (industry-pack quick-starts)
- **What:** a **gallery of starter styles** keyed to the master spec's industry packs
  (real-estate / salon / clinic / coaching / cafe / D2C / agency) + the 6 visual styles
  (premium / local / bold-offer / emotional / trust / minimal). Vendor picks a tile →
  it pre-seeds the instruction + style + platform so generation is one click from a cold
  start. NOT static stock images — each tile is a **prompt preset**, rendered live on the
  vendor's OWN campaign data.
- **Value:** solves the blank-command-box cold-start; gives non-marketers a confident
  starting point; teaches the product's range. Premium onboarding.
- **Plugs in:** **S1** empty state + an "Inspiration" row above the variants grid (an
  `ExploreCreatorsPage`-grid of preset tiles). Architecture: presets are **config**
  (a seeded JSON of `{industry, style, platform, instruction_template, angles}`) consumed
  by the AIPromptBuilder — the industry packs (master §21) already exist as logic; this is
  their UI front door. No schema change.
- **Effort: M.** **Verdict: BUILD (Phase-1.5).** High onboarding value; pure config + a
  reused grid. Just outside top-5 because F1–F5 deepen the loop more.

---

### F8  Batch Generation across campaigns ("make the whole week's creatives")
- **What:** select **multiple campaigns** (or lead segments) and generate the full set in
  one queued batch — e.g. "3 Meta + 2 WhatsApp banners for each of my 4 active campaigns".
  The Generation Queue (S4) shows it streaming in, grouped by campaign.
- **Value:** turns a day of work into one action for the agency/multi-campaign vendor —
  the high-ACV power user. Scales the factory.
- **Plugs in:** **S2** campaign `Select` → multi-select; **S4 queue** groups by campaign.
  Architecture: N parallel `ai_generation_jobs` (the queue + Hatchet fan-out already
  handle many concurrent jobs); one combined wallet estimate ("≈ 120 credits · 20 banners.
  Continue?"). No new mechanism — it's the existing job model at higher cardinality.
- **Effort: M.** **Verdict: BUILD (Phase-2).** Clear value but skewed to power users;
  the queue + wallet already support it. Defer until single-campaign flow is solid.

---

### F9  Performance → Auto-Regenerate Winners (the compounding loop, suggested-not-auto)
- **What:** when an asset's metrics cross a "winner" threshold, the studio **proactively
  surfaces** "This is winning — generate 5 more like it?" (one tap → seeds the next batch
  from the winner's brief, biased toward its angle). **Suggested, vendor-approved** — NOT
  silently auto-spending.
- **Value:** the platform gets smarter on its own and keeps the vendor in winning
  territory — the "it works while I sleep" feel, safely. This is §10 perf-learning made
  actionable.
- **Plugs in:** **S8 / Library "Winners" facet** → a "Winners" card with the one-tap CTA;
  a dashboard nudge. Architecture: reads `ai_assets.metrics` (Adbot write-back, §10),
  applies the existing "more like the winner" prompt-bias; generation is the normal gated
  `POST /generate`. **Safety:** suggestion only — the engine FIX-1 rule (studio never moves
  ad budget) holds; a real auto-mode would sit behind an explicit per-tenant flag + wallet
  cap, deferred.
- **Effort: M.** **Verdict: BUILD (Phase-2, suggested-mode first).** On-strategy and
  compounding, but depends on live ad metrics flowing — sequence after F3 ships the loop.

---

### F10  Localization Presets (Hinglish / Gujarati / Hindi one-tap variants)
- **What:** one-tap **language variants** of any approved creative — "Hinglish version",
  "Gujarati version" — re-rendering the copy layer in the local language while keeping the
  visual. The master spec already mandates EN/HI/Hinglish/Gujarati-local; this makes it a
  one-tap creative multiplier, not a setting buried in Advanced.
- **Value:** India-market killer feature — the same creative, localized per audience, in
  one tap. Directly lifts WhatsApp/local-ad response. On-brand with the customer base.
- **Plugs in:** **S6 NL-edit quick-chips** + **S11** already list "Hinglish"; this elevates
  it to a **"Localize ▸" `Dropdown`** (Hinglish · Hindi · Gujarati · English) producing a
  labelled new version each. Architecture: the AIPromptBuilder + `language` field already
  exist (`ai_assets.language`, brand-kit `language_pref`); each output is a new
  `ai_asset_versions` row. **No-invent guardrail (§20) still applies** to translated copy.
- **Effort: S.** **Verdict: BUILD (Phase-1.5).** Cheap (text-layer re-render), high
  India-market value, reuses the language field everywhere. Strong honorable-mention.

---

### F11  Smart Credit Estimator + "what-if" preview (before you spend)
- **What:** before Generate, an **interactive estimate**: as the vendor changes count /
  model / "compare" / "all sizes", the credit line updates live ("≈ 30 credits · 5
  banners · Auto model"). Plus a per-tenant **monthly spend meter** (a small ring) so they
  feel in control. Honest, never a fake percentage.
- **Value:** trust + no bill-shock; nudges efficient choices. Premium fintech-grade
  transparency on a money action.
- **Plugs in:** **S2 estimate line** (already specced) made live + a `CardChartPie` spend
  ring in S1 col-right or the Library head. Architecture: pure read of the existing
  `GET /status` budget snapshot + the per-variant `cost_minor` sum the wallet estimate
  already computes; no new endpoint. Caps already exist (`AIASSET_DAILY/MONTHLY_CAP_INR`).
- **Effort: S.** **Verdict: BUILD (Phase-1).** Tiny, reuses the wallet/status data, and
  makes the spend gate feel premium instead of scary. Bundle with the S2 build.

---

### F12  "From this →" Reuse / Remix (any asset becomes a reference)
- **What:** any Library or variant card → **"From this →"** opens S2 with that image pinned
  as the reference + "make this kind of banner for [campaign]". Remix a past winner, a
  competitor banner, or a product photo into on-brand creatives.
- **Value:** turns the whole library into reusable creative DNA — the vendor's best work
  compounds. Reuse is explicitly a founder ask (master §28/§53 "reuse").
- **Plugs in:** **S9/S5 card action** "From this →" → **S10** upload-reference flow (both
  already specced). Architecture: the `reference_image` already flows through
  `ImageBrief.reference_image` to the provider (§3); a library asset's bytes are the
  reference instead of an upload. No new mechanism.
- **Effort: S.** **Verdict: BUILD (Phase-1).** Already 90% in the S10 spec — this is just
  wiring the Library card action to it. Essentially free; ship with S9/S10.

---

### F13  Creative Score "why" + fix-it suggestions (actionable QA)
- **What:** the creative score (§29: clarity/readability/CTA/brand-fit/platform-fit…) is
  already computed per version. This adds a **one-line "why"** per sub-score and a **fix-it
  chip** ("Text too dense → simplify?", "CTA weak → strengthen?") that, tapped, fires the
  matching NL edit. The score becomes a coach, not a number.
- **Value:** teaches the vendor what makes a creative convert and gives a one-tap fix —
  turning a passive metric into an action. Raises output quality automatically.
- **Plugs in:** **S6 score card** — each sub-score gets a "why" + an optional fix `Button
  isStroke` that calls `POST /assets/{id}/edit` with the canned instruction. Architecture:
  the `ai_creative_scores.notes` field + the scorer (`score.py`) already exist; map low
  sub-scores → canned edit instructions (config). No new table.
- **Effort: M.** **Verdict: BUILD (Phase-2).** On-strategy quality lift, but layered on
  the scorer — sequence after the core generate/edit loop is solid.

---

### F14  Voice/Chat command bridge from AI Manager (already an integration target)
- **What:** the AI Manager can already route static-image commands here (master §33). This
  makes the studio **deep-link aware**: "create 5 ad banners for the Galaxy campaign" spoken
  to AIM lands the vendor IN the S4 queue watching it stream, PIN-gated through AIM.
- **Value:** the founder's flagship voice-command-brain commands the asset factory hands-
  free — a marquee cross-product demo. Reuses two finished systems.
- **Plugs in:** **S1** accepts a deep-link (`?campaign=&instruction=&autostart=1`) that
  pre-fills + starts; **AIM Command History** links to the resulting job. Architecture:
  AIM's risk table already classifies `creative.generate_*` as money-risk → PIN/step-up,
  then calls `POST /generate` (§7); this is the UI return path. No new backend.
- **Effort: S.** **Verdict: BUILD (Phase-2).** Cheap (a deep-link contract) but depends on
  AIM dispatch being wired; sequence after the studio stands alone.

---

### F15  Template Marketplace / shared style packs (cross-tenant, curated)
- **What:** a curated marketplace of **style packs / template presets** (extends F7) that
  vendors could browse/clone, and eventually a place high-performing anonymized presets
  surface. A growth/community surface.
- **Value:** network effects + onboarding, long-term. Real but not core to the loop.
- **Plugs in:** would need a new cross-tenant `app/creative/marketplace` page + a shared/
  curated table + a publish/clone flow + moderation. Architecture: this BREAKS the per-
  tenant FORCE-RLS posture (cross-tenant read) and needs new tables, moderation, IP/safety
  review — material new surface, not a reuse.
- **Effort: L.** **Verdict: DEFER (Phase-3+).** Genuinely valuable but it's a NEW
  cross-tenant subsystem with security implications — exactly the kind of bloat to keep
  out of Phase-1. Start with F7 (per-tenant presets) which delivers 80% of the value with
  zero new security surface.

---

## B. TOP-5 TO BUILD IN PHASE-1 (the prioritized cut)

Ranked by **(loop-deepening × first-impression) ÷ effort**, all pure-reuse, all dormant-safe:

| # | Feature | Why it's top-5 | Effort | Primary plug-in |
|---|---|---|---|---|
| **1** | **F1 Brand-Kit Auto-Extraction** | Best first-impression lever — first banner looks "theirs"; kills the worst setup chore. | M | S7 + `POST /brand-kits/extract` → `ai_brand_kits` |
| **2** | **F2 One-Click "Make All Sizes"** | Removes the #1 marketing chore; near-free on the existing `BatchSpec` cross-product. | M | S11 Resize / S6 footer → `ai_asset_versions` |
| **3** | **F3 In-UI A/B Creative Test** | IS the moat (test→winner→scale) made visible; engine pieces already exist. | M (reuse engine) | S5 select + S8 leaderboard → `attach`/`ads_engine`/`metrics` |
| **4** | **F4 Model-Comparison (2 models side-by-side)** | The clearest payoff of model-agnosticism; impossible for a single-API competitor. | M | S2 Advanced + S5 paired cards → `router` fan-out |
| **5** | **F5 Asset Version Timeline** | Best value-to-effort — a VIEW of data already stored; makes "never overwritten" tangible. | S | S6 timeline → `ai_asset_versions` lineage |

**Bundle-with (essentially free, ship alongside the above in Phase-1):** **F11** smart
estimator (with S2), **F12** "From this →" reuse (with S9/S10) — both are tiny reuses of
already-specced surfaces and lift the premium feel for near-zero cost.

**Phase-1.5 / 2 backlog (built once the loop is live):** F6 copy co-gen → F10 localization
presets → F7 starter gallery → F13 score-coach → F9 auto-regen-winners (suggested) → F8
batch-across-campaigns → F14 AIM voice bridge.

**Deferred (Phase-3+, NOT bloat-in-Phase-1):** F15 template marketplace (new cross-tenant
subsystem + security surface).

---

## C. REJECTED / EXPLICITLY OUT (keeps the product un-bloated)

Per the §0 discipline + the master spec's "NOT a design tool" / §41 NEVER list:
- **Manual layer/canvas editor, drag-handles, font picker, color wheel** — contradicts the
  ONE principle ("I tell what I need, AI creates it", UI §0). Editing is natural-language
  only (S6 NL box).
- **Stickers / filters / meme generator / clip-art library** — off-brand, low-value,
  invites clutter (master §20/§41 "not cluttered/childish/AI-arty").
- **Stock-photo search / generic image bank** — the studio generates FROM campaign data; a
  stock bank dilutes the campaign-aware DNA (master §41 "never random/unrelated images").
- **Full video / brochure-PDF / landing-page builders** — explicitly OUT of Phase-1 scope
  (master §2); they route to Video AI / Brochure AI / Landing AI. The architecture already
  reserves `modality` for video later — don't pull it forward.
- **Silent auto-spend on ads / auto-launch winners without approval** — master §41 NEVER +
  engine FIX-1. F9 is suggestion-only for exactly this reason.
- **Per-media-type microservices** — the architecture decision is ONE coarse asset service;
  don't fragment it.

---

## D. CROSS-CUTTING (every feature above inherits)

- **Reuse-only:** every UI surface is a Core_2 reference component (`Card`/`Tabs`/`Select`/
  `Button`/`GridProduct`/`Filters`/`Modal`/`CardChartPie`/`Percentage`/`FieldImage`); the
  ONLY new component remains `CreativeSkeleton` (the liquid loader). Inter Display, semantic
  `@theme` tokens, ZERO raw hex, single `<Layout title>` heading, no `PageHeader`.
- **Dormant-safe:** each feature degrades to a calm `NoFound`/empty state when its data or
  creds are absent (no providers, no metrics, no brand kit) — never an error wall.
- **No-invent guardrail (§20) is inherited** by every copy-producing feature (F6/F10/F13):
  the deterministic validator strips any price/claim/RERA/phone not present in campaign
  context — the LLM is never the authority on facts.
- **Money-safe:** every generate-spawning feature (F2/F4/F8/F9/F10) goes through the same
  wallet estimate→hold→settle→refund gate; the credit line states cost honestly before the
  vendor commits.
- **Schema cost of the top-5:** F1 = reuse `ai_brand_kits` (0 new cols) + 1 endpoint; F2 =
  reuse `ai_asset_versions` (0); F3 = reuse `ai_asset_usage`/`metrics` (0); F4 = 1 field on
  the `request` JSONB (0 columns); F5 = pure view (0). **Net new schema for all 5: zero
  tables, zero columns** — only F1 adds one additive endpoint. This is the proof they're
  additive, not bloat.

---

## E. SOURCES / GROUND TRUTH
- Founder invite + seed list: `CREATIVE_STUDIO_PHASE2_SPEC.md §4`.
- Architecture (provider abstraction, two-stage pipeline, loop): `CREATIVE_STUDIO_MASTER_PROMPT.md`
  §1–9, §13, §17, §20, §26–35, §41, §52–53.
- Schema/pipeline/API the features plug into: `design/asset-service-backend.md` §2 (tables:
  `ai_brand_kits`, `ai_generation_jobs`, `ai_assets`, `ai_asset_versions`, `ai_creative_scores`,
  `ai_asset_usage`), §3 (pipeline + AIPromptBuilder + §20 no-invent), §6 (wallet gate),
  §7 (attach/Adbot/workflow/AIM integrations), §8 (API surface), §10 (brand memory + perf
  learning).
- UI surfaces the features attach to (S1–S11 + W1): `design/creative-studio-ui.md`.
- Reuse + token discipline: `design/ui-design-principles.md`; reference templates verified
  on disk under `core-2-dashboard-builder-react/templates/*` (ExploreCreatorsPage, DraftsPage/
  Grid, SettingsPage, Customers/OverviewPage, MessagesPage, Customers/CustomerList/DetailsPage).
- Engine FIX-1 (studio reports, never moves ad budget): `design/creative-image-banner-studio.md`.
