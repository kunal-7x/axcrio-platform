# Wave build — Sales Proposal (customer-facing "sell-anything" HTML)

Deliverable: `caps/sales/Famit-AI-Revenue-Platform-Proposal.html` — a single,
self-contained, offline, printable interactive proposal the founder hands a
prospective buyer (real-estate / salon / clinic / coaching / D2C / agency) to
BUY Famit/Axcrio. Built from `sales/research-{product-truth,positioning-pricing,
proposal-bestpractice}.md`. NO git. Companion to the `investor/` VC deck.

---

## VISUAL QA + FINALIZE pass — 2026-06-11 (ROLE: visual QA + finalize)

Method: headless Google Chrome driven over the DevTools Protocol via a tiny
zero-dependency Node WebSocket client (the env has no puppeteer/playwright).
Rendered at true window sizes + CDP device emulation; captured full-page
desktop/mobile screenshots, print-media-emulated screenshots, and a real
`--print-to-pdf` PDF.

### QA results (per item)
- **Self-contained / offline:** PASS. Logo is base64-embedded; decoded to a valid
  1454x1454 RGBA PNG, **89,378 bytes — byte-identical to source**
  `design/logo-out/famit-mark-dark-trim.png` (used twice: nav + footer, recolored
  via CSS filter). Only external refs = Google Fonts CDN (with full system-font
  fallback in `--ff-sans`/`--ff-display`), `panel.famit.in` CTAs, and a `mailto:`.
  Nothing else fails offline. `inter_loaded=true` when online; system fallback when not.
- **ROI calculator JS:** PASS. Computes live on input. Defaults (500 leads, 5%->6.25%
  conv, Rs15k/customer, Rs30k x1 telecaller, Growth Rs24,999, loop off) →
  **Net Rs98,751/mo · 5.0x · ~6 days payback · Rs11.85L/yr** — matches the static
  headline exactly (verified independently with `node -e`). `node --check` on the
  extracted script = OK.
- **Print / PDF stylesheet:** PASS (after fix). Real headless PDF = **8 pages, clean**.
  In print media: nav + sticky CTA `display:none`, **0 `.reveal` elements stuck at
  opacity:0** (so nothing is invisible if printed without scrolling), dark cards keep
  colour via `print-color-adjust:exact`.
- **Links / CTAs:** PASS. Nav anchors (#problem #loop #moat #roi #pricing #cta #top)
  all resolve to real IDs; CTAs → `https://panel.famit.in`; demo → `mailto:hello@famit.in`.
- **Mobile + desktop premium:** PASS (after fix). `overflow_px=0` at both 390-ish and
  1440 true windows; full-page screenshots look premium top-to-bottom both sizes.
- **No placeholders:** PASS. No lorem/TODO/FIXME/placeholder; tags balanced 347/347 div,
  11/11 section.

### Fixes applied (directly in the file)
1. **Mobile horizontal overflow (18px → 0).** Root cause: `.card-moat{grid-column:span 6}`
   stayed active when `.bento` collapsed to 1 column on mobile — CSS Grid auto-created
   5 *implicit* columns to satisfy the span, dragging the card to ~380px inside a 334px
   track. Fix: base `.card-moat` → `grid-column:1 / -1` (spans the full row at any column
   count, never creates implicit tracks). Added `min-width:0` to `.bento>*`, `.card-moat>*`,
   and `.sigflow-row .t` as belt-and-suspenders against grid/flex min-content overflow.
   (Body already had `overflow-x:hidden`; the decorative `.aurora` bleed is contained by
   `.hero{overflow:hidden}` and does not scroll.)
2. **Print page-breaks.** `.section{page-break-inside:avoid}` forced whole oversized
   sections → big blank gaps; and `.roi-shell` (1338px, taller than a printable page) was
   in the `break-inside:avoid` list → would cut/gap. Fix: sections + large containers
   (`.roi-shell,.loop-stage,.bento,.tiers,.steps`) → `break-inside:auto`; kept
   `break-inside:avoid` only on small components (`.card,.tier,.pstat,.step,.assure-card,
   .artifact,.cmp-card,.proof-stats,.faq-item,.roi-out`).
3. **Static/JS consistency.** ROI "extra customers" static default `+6` → `+6.3` (matches
   what the JS writes on load and in print).

### Also produced
- `sales/README.md` — founder how-to (open in browser; Ctrl/Cmd+P → Save as PDF with
  Background graphics ON; personalise the headline token + sliders; how to swap in a new
  base64 logo / real testimonials / pricing later — each a small text edit).
- Removed the `_qa/` scratch dir (chrome profiles, screenshots, CDP scripts, test PDFs) so
  `sales/` ships clean: proposal HTML + 3 research MDs + README.

### One-line how-to-use
Open `Famit-AI-Revenue-Platform-Proposal.html` in a browser to present it; to make a
leave-behind PDF press Ctrl/Cmd+P → Save as PDF (A4, Background graphics ON).
