# Famit / Axcrio — Investor Pitch Deck

A self-contained, offline-safe HTML slide deck for raising a **seed round**
(the company as an investment — distinct from the customer-facing sales
proposal in `caps/sales/`).

**File:** `Famit-Investor-Pitch-Deck.html` — open it in any modern browser.
Everything is inlined (CSS, JS, both logos as base64). No internet needed;
the Google Inter/Space-Mono fonts load from CDN when online and fall back to
system fonts (Segoe UI / -apple-system) offline.

---

## How to present

1. **Open** `Famit-Investor-Pitch-Deck.html` in Chrome / Edge / Safari.
2. **Navigate:**
   - `→` / `Space` / `PageDown` = next slide
   - `←` / `PageUp` = previous slide
   - `Home` = first slide, `End` = last slide
   - **Click** the right half of the screen to advance, left half to go back
   - On a touchscreen: swipe left/right
   - On-screen arrow buttons (bottom-left) also work
3. **Slide counter** is bottom-right (`n / 14`); a blue progress bar sits at the top.
4. **Full-screen** for the room: press `F11` (Windows) / `Ctrl+Cmd+F` (Mac) after opening.

## Export to PDF (one slide per page, landscape)

1. Press **`Ctrl+P`** (Windows) / **`Cmd+P`** (Mac).
2. **Destination:** "Save as PDF".
3. **Layout:** **Landscape**.
4. **Margins:** None. **Paper size:** default is fine (the deck pins each page
   to a 1280×720 landscape frame).
5. Under "More settings", turn **ON** "Background graphics" (so the dark canvas
   and blue accents print).
6. Save. You get a clean 14-page PDF, one slide per page, nothing cut off.

---

## ⚠️ BEFORE YOU SEND — fill these placeholders

The deck deliberately leaves the numbers and people **blank** — never invent
them. Search the HTML for `[ Founder to fill ]` / `[ amount ]` / `[ ___ ]`:

| Slide | What to fill |
|-------|--------------|
| **12 · Team** | Three `[ Founder to fill ]` cards — your real name + background (Founder/CEO), founding engineer, GTM/advisor. Add/remove cards as needed. |
| **14 · The Ask** | `$[ amount ]` (headline raise), `$[ ___ ]` (RAISE), `[ __ mo ]` (RUNWAY). **Valuation** is referenced as "founder to fill" — add it if you're naming one. |

Everything else (metrics, market math, moat) is **real or sourced** and
already filled. Roadmap items are clearly tagged `Roadmap`/`Ready`; live items
are tagged `Live`. Do not change traction numbers — they are honest pilot-scale
figures (96 real AI calls, 8 campaigns, 18/18 isolation probes, metered COGS).

## Editing tips

- All styling/JS is in the single `<style>` and `<script>` block — no build step.
- To add a slide: copy a `<section class="slide">…</section>` block; the counter
  total updates automatically from the slide count (no manual number to change).
- Brand blue is `--signal: #2A85FF`; the dark canvas is `--ink`.
