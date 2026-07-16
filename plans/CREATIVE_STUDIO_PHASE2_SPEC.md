# CREATIVE STUDIO PHASE-2 SPEC — Loading UI + WhatsApp Campaign Builder (founder, 2026-06-11)

> Companion to `CREATIVE_STUDIO_MASTER_PROMPT.md`. Two new asks: (1) the premium AI-generation
> LOADING experience, (2) the AI-powered WhatsApp Campaign Builder with deep Creative Studio
> integration. Reuse design-system COMPONENTS; port from `core-2-dashboard-builder-react`;
> layouts intentional per workflow. Consult the `frontend-design` skill.

## 1. PREMIUM AI-GENERATION LOADING UI (reusable component)
The moment a user clicks Create Image / Create Banner / any Creative Studio generation action, they must NEVER see an empty box or a boring spinner. Show a premium AI-engine loading state:
- **Look:** dark full-screen or preview-area state; a large rounded CHARCOAL card centered on a black background. Small muted "Thinking" text; a bold title inside the card ("Creating image" / "Creating banner"); a beautiful animated **dot-matrix** visual in the middle — many soft grey/white dots in a circular field, center dots larger+brighter, outer dots smaller+faded, slowly pulsing/breathing/shimmering/drifting like a neural energy field. Minimal, premium, futuristic, smooth. NOT colorful, NOT childish, NOT a normal SaaS loader. (Reference feel: ChatGPT / Google Flow image+video generation.)
- **Behavior:** appears INSTANTLY on generation start; stays while the async backend generates; smoothly FADES into the final image/banner when ready. If real backend progress exists → show subtle progress; if not → DO NOT fake a percentage, just the animated state. Cycle small status lines: "Understanding campaign" → "Designing visual direction" → "Composing layout" → "Rendering creative" → "Finalizing output".
- **States:** loading, completed (fade to result), failed, retry, optional cancel.
- **Quality:** reusable across image / banner / ad-creative / brochure-cover / video-thumbnail generation. Responsive (mobile+desktop). Dark/light if the app has both. Respect `prefers-reduced-motion` (degrade to a calm static/low-motion state). Reuse existing theme/buttons/cards; change NOTHING unrelated. Implementation should be GPU-friendly (CSS transforms / canvas / a lightweight particle field), not janky.

## 2. AI-POWERED WHATSAPP CAMPAIGN BUILDER (+ Creative Studio integration)
The WhatsApp module becomes an INTELLIGENT CAMPAIGN BUILDER, not a manual template editor.
- **Flow:** Campaign Selection → AI Template Generation → Creative Selection → Banner Generation/Selection → Template Preview → Approval → Audience Selection → Scheduling → WhatsApp Delivery → Analytics → Optimization → Reuse winning templates.
- **AI template generation:** on selecting a campaign, the platform analyzes objectives/audience/offer/products/business-context/brand and AI auto-generates: WhatsApp template suggestions, message variations, CTAs, personalization tokens, media recommendations, and campaign structures. (Reuse the LLM — Groq/OpenRouter — + campaign data, with the master-spec NO-INVENT guardrails.)
- **Creative Studio integration (deep):** if a banner is needed, launch Creative Studio DIRECTLY from the WhatsApp workflow; after generating/editing, the asset auto-stores in the Asset Library and is immediately available in the WhatsApp template builder. Browse/preview/search/filter/compare versions, select, and ATTACH to a template WITHOUT manual upload. Every asset stays linked to its campaign.
- **UI:** a premium CAMPAIGN WORKSPACE (not forms) — visual template cards, creative previews, audience insights, campaign recommendations, AI-generated suggestions, performance indicators, asset galleries, contextual actions, visual workflow. The current 2-card WhatsApp page → an Apple-like multi-card layout (many small/large cards, intentional placement).
- **Learning loop:** templates/creatives/campaign structures are reusable assets (clone/optimize/repurpose); every banner+template+campaign stays connected to analytics so the platform learns which combinations yield the highest engagement/response/conversion and surfaces winning templates.
- Key flow: Campaign → AI Generates Template → Create/Select Banner (Creative Studio) → Preview WhatsApp Message → Select Audience → Schedule/Send → Track Performance → Learn → Reuse Winners.

## 3. CREATIVE STUDIO (recap — see master spec)
Model-agnostic asset factory (OpenRouter now; Leonardo/Flux/OpenAI/Google/Stability later via the Provider abstraction). Generation + transformation (generate from campaign OR upload-a-reference → "make this kind of banner" → variations/redesign/rebrand/resize/localize). Premium creative workspace: dynamic cards, asset galleries, generation queue (with the §1 loader), prompt-intelligence panel, model-selection controls, asset performance insights, template recommendations, workflow shortcuts. Future Video AI / Ad AI / Thumbnail AI plug into the same architecture. Assets are reusable across WhatsApp/ads/funnels/landing/workflows.

## 4. "OUT OF THE BOX" — founder invites proactive additions
"Add new features out of the box no matter if I have told or not." So the design must proactively propose high-value additions (e.g. brand-kit auto-extraction, A/B creative testing surfaced in-UI, one-click "make all sizes", campaign-performance → auto-regenerate-winners, asset version timeline, AI copy+image co-generation, template marketplace) — proposed + prioritized, built where they fit the architecture without bloat.
