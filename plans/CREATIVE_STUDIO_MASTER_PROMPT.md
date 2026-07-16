# CREATIVE STUDIO + AI ASSET SERVICE — MASTER SPEC (founder-authored, 2026-06-10)

> Canonical spec for **Creative Studio** (the user-facing premium creative workspace) powered by the
> **AI Asset Service** (a dedicated coarse SERVICE for all asset generation). Phase 1 = Image / Banner /
> Ad-image only. Reuse design-system COMPONENTS (mandatory); layouts are intentionally designed per
> workflow (NOT blind layout reuse). Port from `C:\Users\kunal\Desktop\core-2-dashboard-builder-react`.

## ARCHITECTURE DECISION (orchestrator's call, founder approved "you take the call")
- **AI Asset Service = a dedicated coarse SERVICE** (own process, own Postgres schema `ai_asset_*` FORCE-RLS, own port, own deploy/scale unit). Handles ALL asset generation/transformation/optimization/storage/versioning/provider-management — image now; video/thumbnail/banner/creative later — behind ONE unified API. NOT separate microservices per media type. Co-located on an existing box now (DO droplet limit 3/3); extractable to its own (GPU-capable) droplet later. Uses **Hatchet** (F3) for the async job queue, **DO Spaces** for storage (interim: box filesystem until Spaces creds land), and reuses `wallet.py` (credit holds), `audit.py`, RLS.
- Creative Studio (the UI) stays in the modular-monolith panel; the generation ENGINE is the AI Asset Service. Model-agnostic: **OpenRouter is one provider implementation, not the architecture.** A unified `Provider` abstraction supports OpenRouter now + Leonardo/Flux/OpenAI-images/Google/Stability/future later — swap models without UI/workflow changes.
- Companion services: AI Manager (done), Hatchet (workflow engine), voice plane. Integrations Hub + Analytics stay in the monolith until scaling demands; Foundation Control Layer stays core (inline entitlement boundary).

## 1. WHAT IT IS
A **campaign-aware AI design engine** — an AI designer + AI copywriter + AI ad-creative strategist working together. When a vendor asks to create a banner / ad image / WhatsApp poster / Meta or Google creative / offer poster / landing hero / any STATIC marketing visual, it creates it FROM the campaign's existing business data. NOT a random image generator. The vendor should just say "Create banner for this campaign" — the system infers product, audience, text, size, CTA, style. If the campaign has the data, USE it; only ask when required info is missing.

## 2. SCOPE (Phase 1 = static visuals ONLY)
IN: ad banners, image/Meta/IG-post/IG-story/FB ads, Google display, WhatsApp posters/follow-up images, offer/product/campaign posters, landing hero, website section images, retargeting images, festival/event/site-visit/appointment/lead-gen banners, carousel slides, square/vertical/horizontal/thumbnail static creatives. OUT (route elsewhere): full video → Video AI; brochure PDF → Brochure AI; website/landing build → Landing Page AI; voiceover → Voice. (May create a banner-for-brochure / video-thumbnail / landing-hero image — the cover only.)

## 3-6. CORE BEHAVIOR
On "Create Banner" / "Create ad image for this campaign": understand intent → identify campaign/product → read campaign data → understand audience+offer → pick creative angle → banner text → platform size → visual style → generate MULTIPLE variants → show in Creative Studio → vendor approve/reject/edit/regenerate/resize/use → save to asset library → make available to WhatsApp/Adbot/workflow/campaign. **Campaign-based generation is the #1 DNA**: pull business name/campaign/product/location/price/offer/audience/goal/benefits/images/logo/brand-style/lead-type/platform automatically; don't re-ask what's already there. Before creating, AI understands: business context, campaign objective, target audience, funnel stage, platform, offer, brand style.

## 7. BANNER TYPES (must support, platform-aware)
Meta ad, IG story (9:16), WhatsApp poster (mobile-first simple), Google display (horizontal, less text), carousel slides (1 point each), offer banner, retargeting banner, lead-follow-up banner (stage-aware), landing hero, event/appointment banner.

## 8-9. CREATIVE ANGLES + VARIANT DNA
Per request generate ~5 DIFFERENT MARKETING ANGLES (not 5 random): price, location, emotion, urgency, trust, problem-solution, benefit, offer, retargeting, comparison. Each variant carries: purpose, angle, headline, subheadline, CTA, visual direction, platform size, expected use, preview image, editable text — labeled clearly (Variant 1: Price Focus, etc.) + a testing hypothesis (for Adbot).

## 10-12. TEXT / CTA / VISUAL STYLE DNA
Text: 3-8 word headline, short subhead, clear CTA, no clutter; hierarchy = headline → detail → CTA → brand. CTA matches goal (real-estate→Book Site Visit; salon→Book Appointment; clinic→Book Consultation; coaching→Book Free Demo; ecommerce→Shop Now; cafe→Order/Visit). Visual style chosen by business+goal: premium / local-business / bold-offer / emotional-lifestyle / trust / minimal-modern.

## 13-16. BRAND / LANGUAGE / PLATFORM / SIZE DNA
Brand memory: logo, colors, design style, tone, preferred CTA/language, approved+rejected creatives, best-performing style, do-not-use words/styles (don't make cheap discount banners for a premium brand unless asked). Language: English / Hindi / Hinglish / Gujarati-style local — natural, not robotic. Platform-aware (Meta feed ≠ IG story ≠ WhatsApp ≠ Google ≠ hero). Sizes: 1:1, 4:5, 9:16, 16:9, Google display, carousel, WhatsApp square/vertical, web hero wide, thumbnail, custom; defaults if platform unset.

## 17-20. INTELLIGENCE + GUARDRAILS
Campaign-field → banner transform (price→"From ₹58L", location→"Near Satellite", goal→CTA, USP→headline, tone→style) done by AI, not the vendor. Missing-detail: generate directly if enough data; ask only key missing items (which campaign? WhatsApp or Meta? premium or offer style? include price?) — never demand a full re-spec. Quality: clean/readable/professional/brand-matching/mobile-friendly/platform-ready/conversion-focused, not cluttered/fake/generic/AI-arty; avoid distorted/unreadable text, wrong logo, weird hands/faces, watermark. **Text accuracy (critical): NEVER invent price/discount/location/phone/RERA/guarantees/amenities/claims/testimonials/awards** — omit or ask. No fake "RERA Approved", "50% Off", "100% guaranteed".

## 21-25. INDUSTRY + CHANNEL + STAGE DNA
Industry packs: real-estate (location/price/possession/site-visit/trust), salon (transformation/appointment/festive/bridal), clinic (trust/consultation/no medical-cure claims), coaching (results/demo/batch/seats), cafe (craving/combo/visit), D2C (benefit/offer/lifestyle), agency (result/pain/consultation). WhatsApp banners = simpler, low-text, stage-aware (hot/warm/missed-call/reminder), pair with WA message copy. Ad banners = multi-angle for testing, each with a hypothesis. Retargeting = direct, "you already interacted." Lead-stage: cold (hook), warm (reasons), hot (push/urgency), existing (loyalty/upsell).

## 26-31. EDIT / REGEN / APPROVAL / LIBRARY / SCORE / LEARNING
Natural-language editing ("make it premium", "less text", "remove price", "add my logo", "change CTA to Book Site Visit", "story size", "Hinglish", "5 more like this") → new VERSION (original kept). Regeneration = variations (same angle new layout, new size, new CTA, new language, cleaner/simpler, new angle, "5 more like winner"). Approval status: draft/needs-review/approved/rejected/used/archived; only approved → Adbot (unless auto mode); rejections teach the system. Asset library: every asset saved with preview/campaign/type/platform/size/angle/headline/CTA/status/score/cost/date/used-in/performance; filter by campaign/platform/type/status/best-performing/date/size/vertical/angle. Creative SCORE (clarity/readability/CTA/brand-match/platform-fit/quality/conversion/relevance/text-amount/offer-visibility). Performance learning: track impressions/clicks/CTR/leads/CPL/conversions/WA-replies/bookings/cost/quality/edits → improve future banners.

## 32-35. INTEGRATIONS
Adbot loop: Campaign → banner variants → Adbot low-budget test → kill losers/scale winners → performance back → more variants from winners. AI Manager: voice routes static-image commands here ("create 5 ad banners for this campaign", "WhatsApp poster for hot leads", "make it premium", "send approved banner to WhatsApp campaign"); video→Video AI, brochure→Brochure AI. Workflow automation: asset generation as workflow nodes (new campaign → make 5 Meta + 3 WA banners → save → approve → Adbot; lead hot → select/create hot-lead poster → send → wait → remind). Billing/credit: estimate + reserve (wallet hold) before large generation, settle actual, refund unused on failure; "Generating 10 banners ≈ 30 credits. Continue?"

## 36-38. UX + PAGE SECTIONS + COMMANDS
UX must feel "I tell what I need, AI creates it" — NOT a complicated design tool. Premium creative WORKSPACE (not a form). Sections: Create Banner (instruction + campaign/platform/asset-type selectors + model selector + command box + generate), Campaign Context Panel (what data AI is using), Generated Variants Grid (rich cards), Asset Detail Panel (preview/headline/CTA/angle/platform/score/status/edit), Brand Kit Panel, Performance Insight Panel, Asset Library, Generation Queue with **premium live/"liquid"-wave loading states** (like ChatGPT image gen — animated placeholder until the image streams in). Upload-an-image-for-variation flow ("create this kind of banner" + an uploaded reference → generate). Commands: "create banner [for this campaign]", "Meta/WhatsApp/IG-story/Google/offer/retargeting/carousel/hero", "5 variants", "use my brand color", "make it premium/simple", "add/remove price", "change CTA", "Hinglish version", "square/story size", "more like this", "use in ad campaign", "send to WhatsApp leads".

## KEY FLOW
Campaign → AI Prompt Builder (rich prompt from campaign data) → Image Model (via provider abstraction) → Asset Library → WhatsApp Template / Adbot / Workflow → Approval → Publish → Analytics → Optimization → Reuse. (Two-stage: an LLM builds the rich prompt from campaign context; the prompt → an image model renders the banner.)

## WHATSAPP MODULE CHANGES (founder ask)
No manual banner management. From WhatsApp, browse/preview/search/filter and directly ATTACH Creative Studio assets to templates; AI can create the template from the campaign + attach the banner; select which image, preview, attach, build the text template, send. The current 2-card WhatsApp page → a premium multi-card "Apple-like" layout (many small/large cards, intentional placement). Every asset stays linked to its originating campaign for performance tracking + reuse.

## 41. NEVER
generate random/unrelated images, ignore campaign data, ask too many questions, unreadable text, fake price/offer/location/testimonial/cert/RERA/medical-claims/before-after, celebrity images, offensive/cluttered/low-quality, wrong brand/logo, overwrite old assets, auto-launch ads without approval, treat banner-gen as video/brochure gen.

## BLOCKERS (founder-side, need.md)
- **OpenRouter API key** — provided (in `.env.local`; confirm + check OpenRouter's image-generation model support). Phase-1 testing provider.
- **DO Spaces** (key/secret/bucket/region) for production asset storage — interim = box filesystem for testing.
- Later image providers (Leonardo/Flux/Stability/OpenAI-images/Google) — optional, via the provider abstraction.
- Meta WhatsApp creds (to actually publish WA templates) — already in need.md.
