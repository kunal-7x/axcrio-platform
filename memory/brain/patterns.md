# Build / Orchestration Patterns (durable; append, never delete)

Cross-wave reusable patterns for famit-panel work. Each entry = a pattern proven
or specified in a real wave, with file refs.

---

## PATTERN: UI overhaul = PORT the reference kit, never approximate (2026-06-10)

Synthesized plan: `C:\Users\kunal\Desktop\caps\UI_OVERHAUL_PLAN.md`. Combines 4
design docs (`design/ui-ref-kit-inventory.md`, `ui-page-port-map.md`,
`ui-design-principles.md`, `ui-font-heading-plan.md`) into one wave runbook.

**The rule:** for every page, find the matching reference template in
`core-2-dashboard-builder-react` FIRST, copy its real JSX+Tailwind, swap only
data/labels. Founder repeatedly rejects from-scratch lookalikes. Anything we
invented (Signal `PageHeader`, AIM pill-rail, Gilroy) = delete.

**The 3 root causes (all 4 docs independently confirmed — high confidence):**
1. FONT "didn't change" = missing-weights fallback, NOT cache. Gilroy free ships
   only 300/800; our type scale uses 400/500/600/700 → ~95% of text silently
   falls back to InterDisplay. FIX = drop Gilroy, adopt Inter Display app-wide
   (its 5 woff2 300-700 already in `famit-panel/public/fonts/`). Then the change
   is finally visible. Bug sites: `layout.tsx:33-52`, `globals.css:204,283`.
2. HEADINGS = reference renders the title ONCE in `Header` as `text-h4` via
   `<Layout title>`; no eyebrow/glyph/accent/subtitle. Our `components/PageHeader`
   invents all of it (`globals.css:740-760`). FIX = simplify PageHeader to
   `{title,actions}`, sweep callers to drop `subtitle=`/`eyebrow=`.
3. TOO MANY PAGES/JARGON = collapse Billing 5→1 (tabs), AI-Manager 7→3, cut the 4
   "Create Studio" stubs + duplicate Vendors from nav, rename jargon to plain nouns.

**Wave shape (reusable for any big UI port):**
- **W1 = design-system foundation, SERIAL, ONE owner.** Global files only
  (`layout.tsx`, `globals.css`, `PageHeader`, `navigation.tsx`, shell components).
  MUST land + build-green before any page work — else page agents collide on
  shared files and inherit the old font. Font swap → type tokens → clean
  PageHeader → shell+logo reconcile → nav. Commit per unit.
- **W2 = page ports, PARALLEL, partitioned by `app/*` directory.** One agent per
  disjoint dir group, NO shared-file overlap (W1 already owns the globals).
  Hard/NEEDS-COMPOSE pages (AI-Manager, Run, Workflows, Forms) → opus;
  REUSE-DIRECT/ADAPT → sonnet (mechanical port + data swap). Every page must pass
  the §7 acceptance checklist before "done". Counts: REUSE-DIRECT 11, ADAPT 12,
  NEEDS-COMPOSE 3 (27 routes).
- **W3 = integrate → build green → frontend-design review → local visual QA →
  deploy → verify live.** Disjoint dirs ⇒ near-zero merge conflict.

**Key orchestration learnings:**
- The shell (Layout/Sidebar/Header/Card/Table/Tabs) is ALREADY ported from the
  older `Core_2-Capsy-Dashboard`; divergence is page COMPOSITION + the extra
  PageHeader/Gilroy, not the shell. Reconcile shell against the NEW kit, don't
  rebuild.
- Partition page agents so none touch `globals.css`/`layout.tsx`/`navigation.tsx`/
  `PageHeader` — those are W1's. Two agents on one file = the recurring failure.
- AI-Manager target (founder's #1 "too complex"): ONE title + 3 tabs
  (Home / Try it / Setup), reference `Tabs`, kill the 8-tab pill-rail + spinner
  redirect, show Safe/Needs-approval/Blocked badges not raw L0-L4.

**SCHEDULING CONSTRAINT (load-bearing):** this UI build and the **Control-Layer
build both edit `famit-panel` and both deploy** to panel.famit.in → they CANNOT
overlap (shared globals + single deploy pipeline). UI build runs AFTER the
Control Layer is merged+deployed; first action = rebase onto its tip, then branch.

---

## PATTERN: Investor pitch-deck structure blueprint (2026-06-11)

Research-only deliverable for a VC-grade INVESTOR pitch deck (raise money / company-
as-investment) for Famit/Axcrio — distinct from the customer SALES proposal under
`caps/sales/`. Blueprint written to `C:\Users\kunal\Desktop\caps\investor\research-deck-structure.md`.

Canonical seed AI-SaaS slide order (12–14 core slides, then appendix):
Title/one-liner → Problem → Solution → Why-Now → Product/how-it-works →
**Moat (Revenue-Truth Signal Loop)** → Traction → Market (bottom-up) → Business model →
Go-to-market → Competition (2×2) → Team → Vision → The Ask.

Make-or-break slides for THIS raise: (1) MOAT — does ~30% of underwriting work for any
AI pitch; our signal-loop + data network effect is the whole venture-scale thesis;
(2) TRACTION — real LIVE proof (96 calls, 8 campaigns, billing meter, 18/18 isolation
probes) de-risks the bet; (3) PROBLEM — specific bleeding scenario, not abstract;
(4) WHY-NOW — surgical recent shift (multilingual real-time voice + conversions API);
(5) TITLE — first 4 slides get ~60% of attention (2:14 skim test, 15-slide cliff).

Design rules: one idea per slide (headline = takeaway), big numbers as heroes, minimal
text, show-don't-diagram (moat = the one diagram), Signal blue #2A85FF + Inter, dark
premium + white logo mark, ≤14 core, every claim real-or-tagged-roadmap, printable
1-slide-per-page. Sources: YC seed/Series-A guides, Sequoia template, a16z guidelines,
peony.ink 2026 funded-deck analysis. Deck output target: self-contained interactive
HTML under `caps/investor/` (NO git), base64-embedded logo.

---

## DELIVERED: Famit/Axcrio investor pitch deck — interactive HTML (2026-06-11)

Built the VC-grade investor deck per the blueprint above. Single self-contained file:
`C:\Users\kunal\Desktop\caps\investor\Famit-Investor-Pitch-Deck.html` (~77KB, no deps).

- **Self-contained:** inline CSS+JS, both logos base64-embedded (downscaled 1454²→320²
  via PIL = ~10KB each PNG, lean), Inter + Space-Mono via Google-Fonts CDN with full
  system-font fallback stack. Opens offline by double-click.
- **Format:** 14 full-screen 16:9 slides; nav = ArrowLeft/Right + Space/PageDn/Home/End,
  on-screen prev/next, click-left/right-half, touch-swipe; counter `n/14`; top progress
  bar. `@media print` = one slide per landscape page (1280×720, page-break-after) for a
  clean PDF — every slide is a standalone page (no hover/anim dependency).
- **Aesthetic:** confident institutional minimalism (a16z/Sequoia) — near-black canvas
  `#05070d`, single Signal-blue accent `#2A85FF`, faint masked grid texture, big mono
  numbers as heroes, generous whitespace. Inputs from the 3 research docs in `investor/`.
- **Custom visuals (show-don't-diagram):** animated closed-loop ring (orbiting spark +
  6 nodes, signal-loop hop highlighted) on Solution; TAM/SAM/SOM concentric circles
  ($240B→$5-9B→$45-90M) on Market; competition 2×2 with us alone top-right + a vs-table;
  4-up traction strip (96 / 8 / 18-of-18 / ₹68-mo); use-of-funds bar chart.
- **Truth discipline:** every metric real or chip-tagged (live=green pulse / roadmap=
  purple). Raise amount, valuation, runway, team = clearly-labeled `[founder to fill]`
  dashed-blue placeholders (6 of them) — never invented.

Slide order matches the canonical blueprint: Title→Problem→Solution→Why-Now→Product→
Moat→Traction→Market→Business-model→GTM→Competition→Team→Vision→Ask.

Reusable build notes: base64-embed downscaled logos (don't ship 280KB source PNGs);
inject b64 via a post-write Python replace of `__WHITE_B64__`/`__DARK_B64__` placeholders
(keeps the Write call small); validate via static lint (PNG headers decode, balanced
section/svg/table tags, balanced JS braces/parens, every custom class has a CSS rule).
Chrome-MCP screenshot verify was unavailable (extension not connected) — static lint
substituted.
