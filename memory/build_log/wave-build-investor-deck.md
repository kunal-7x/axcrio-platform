# Wave — Investor Pitch Deck (VC seed raise)

Self-contained interactive HTML pitch deck for **raising money** (company-as-
investment), distinct from the customer-facing sales proposal in `caps/sales/`.

**Artifact:** `caps/investor/Famit-Investor-Pitch-Deck.html` (~78 KB, NO git).
**Companion README:** `caps/investor/README.md` (how to present + Ctrl/Cmd+P PDF).
**Source research:** `investor/research-{business-moat,market-sizing,deck-structure}.md`.

## Structure (14 slides, one idea each)
1 Title · 2 Problem · 3 Solution (animated closed-loop diagram) · 4 Why Now
(Andromeda / WhatsApp $2B / Voice×India) · 5 Product (live engines grid) ·
6 **Moat** (Revenue-Truth Signal Loop — "your calls teach your ads") ·
7 Traction (honest pilot-scale KPIs) · 8 Market (TAM/SAM/SOM concentric +
bottom-up India SOM math) · 9 Business Model (4 layers, outcome-billing star) ·
10 GTM (Land/Expand/Scale) · 11 Competition (vs-table + 2×2 matrix) ·
12 Team (founder-to-fill cards) · 13 Vision ($500M thesis) · 14 The Ask
(raise/runway founder-to-fill).

## Aesthetic
a16z/Sequoia institutional minimalism. Near-black canvas `--ink #05070d`,
single Signal brand-blue `#2A85FF`, Inter (CDN + full system fallback) +
Space Mono for numerals. Animated SVG orbit on the loop; live/roadmap chips
(green/violet). Big-number heroes. Custom CSS diagrams (no images except logo).

## QA + FINALIZE pass (this wave) — all PASS
- **Self-contained / offline-safe:** ✅ both logos base64-embedded inline
  (`LOGO_WHITE` 14.5KB, `LOGO_DARK` 12.3KB) — both decode to valid PNG headers
  (`\x89PNG`). White-on-dark used everywhere (all 14 slides are dark canvas).
  Font fallback chain present (`'Inter',-apple-system,…,sans-serif`).
- **Navigation:** ✅ arrow keys (← →), Space/PageUp/PageDown, Home/End,
  click left/right half, on-screen buttons, touch-swipe. `node --check` on the
  embedded JS = clean.
- **Counter / progress:** ✅ `total` is set dynamically from `slides.length`
  (14 sections == counter `id="total">14`); progress bar width = `(idx+1)/total`.
- **Print → PDF:** ✅ `@page{size:1280px 720px landscape}`, each `.slide` pinned
  `1280×720` `page-break-after:always` `overflow:hidden` (last-resort clip guard).
  HARDENED this pass: fixed-px padding `56/84`, viewport-relative `clamp()` type
  pinned to fixed px for print (heads 54/40, title 76, sub 17, kpi 38, pull 30),
  tightened vertical rhythm on dense slides (traction/competition) so nothing
  overflows the 720px box. One clean slide per landscape page.
- **One idea + premium visuals per slide:** ✅.
- **Placeholders clearly marked:** ✅ all `[ Founder to fill ]` (team ×3) and
  `$[ amount ]` / `$[ ___ ]` / `[ __ mo ]` (ask: raise/runway) rendered in the
  dashed-blue `.fill` style; valuation noted "founder to fill". No invented
  team, raise, or valuation.
- **Structure intact:** 14/14 `<section>`, 274/274 `<div>` balanced.

## Fixes applied this pass
- Hardened the `@media print` block (deterministic 1280×720 page, fixed-px
  padding, pinned all `vw/vh` clamp() type to px, tightened dense-slide rhythm)
  so the PDF never clips regardless of the on-screen viewport height.
- Added `@media (prefers-reduced-motion:reduce)` guard (kills orbit/pulse/slide
  transitions for accessibility + clean screen-share).
- Content fix slide 6: replaced confusing "starts with the posterior of
  hundreds" with plain-English "starts smart on day one — inherits what hundreds
  of similar businesses already learned" (cross-tenant network-effect, Roadmap).

## FOUNDER-TO-FILL (must complete before sending)
- Slide 12 Team: 3× real name/background (CEO, founding eng, GTM/advisor).
- Slide 14 Ask: raise amount, runway months, valuation. Never invent.

All metrics in the deck are real/sourced or tagged Roadmap; traction = honest
pilot scale (96 calls, 8 campaigns, 18/18 isolation, metered COGS). No git.
