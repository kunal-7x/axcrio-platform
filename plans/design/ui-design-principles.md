# UI Design Principles + Per-Page Acceptance Checklist

READ-ONLY DESIGN WAVE. This file is the objective bar every ported page must pass.
Authoritative reference (the founder's real design, as React code):
`C:\Users\kunal\Desktop\core-2-dashboard-builder-react` (Core 2.0 — "Core Dashboard Builder 2.0").
Our app to map onto it: `C:\Users\kunal\Desktop\caps\famit-panel`.

THE ONE RULE THAT OVERRIDES EVERYTHING: **PORT, DON'T APPROXIMATE.** If a reference
page/section/component exists, copy its real JSX + Tailwind and swap our data. Never
hand-build a lookalike. Every "premium" thing we invented from scratch (the Signal
`PageHeader`, the AIM tab-rail, Gilroy) is what the founder is rejecting.

---

## 0. ROOT CAUSES of "so bad, so complex, jargon, too many pages, all messed up"

Concrete, evidence-backed findings from comparing our app to the reference:

1. **Invented masthead (`components/PageHeader`).** We built a "Signal" header with a
   blue accent rule (`.page-head::before`), an OVERLINE EYEBROW, a big title, AND a
   subtitle (`globals.css:740-760`). The reference has **none of this** — it renders the
   page title exactly once, in the sticky `Header`, as `text-h4` (`Header/index.tsx:50`,
   `templates/HomePage/index.tsx:15` → `<Layout title="Dashboard">`). Our masthead is the
   single biggest "looks different / busier / messier" signal on every page.

2. **Subtitles everywhere.** `PageHeader` renders a `subtitle` paragraph under every
   heading. The reference NEVER puts descriptive text under a heading. This is the
   founder's explicit fix #1.

3. **Font is a muddy Gilroy/Inter mix.** `globals.css:204` sets
   `--font-inter: var(--font-gilroy), var(--font-inter-display)`. Gilroy free ships only
   300 + 800, so weights 400/500/600/700 silently fall back to InterDisplay → the type
   reads inconsistent and "unchanged." The reference is **pure Inter Display**
   (`--font-inter: var(--font-inter-display)`, 5 weights 300-700, `layout.tsx`). The
   InterDisplay woff2 files are ALREADY in our `public/fonts`.

4. **Too many pages / jargon.** Reference nav = 8 simple groups, ≤5 children, plain nouns
   (Dashboard, Products, Customers, Shop, Income, Promote). Our nav
   (`contstants/navigation.tsx`) = 9 groups, ~30 leaves, with jargon: "Cost Explorer",
   "Plan & Ledger", "Suppression / Do-Not-Call", "Capabilities", "Command Center", plus a
   whole **"Create Studio" group that is 4 coming-soon stubs**.

5. **AI Manager is a maze.** 9 route files and an **8-tab pill rail** (`_shared.tsx`:
   Overview / Test Console / Command History / Approvals / Capabilities / Setup /
   Authorized Users / Command Center), `/ai-manager` is a spinner redirect, and the rail
   uses its own bespoke chrome on top of the invented PageHeader. This is the page the
   founder singled out as "too complex."

---

## 1. THE TEN RULES (the objective bar)

1. **Reference-first.** Find the matching reference page/template BEFORE writing any
   markup. Port its real structure; only the data/labels change. No new component when a
   reference one exists (`Card`, `Table`, `Tabs`, `Select`, `Dropdown`, `Header`,
   `Sidebar`, `Filters`, `Search`, `Field`, `Button`, `NoFound`, `Spinner` all exist in
   both kits — use them).

2. **One heading, no subtitle.** The page title is set ONLY via `<Layout title="...">`
   and rendered once by `Header` as `text-h4`. **Delete `PageHeader` usage** — no eyebrow,
   no accent rule, no subtitle paragraph. If a page truly needs a one-line context, it
   lives as muted `text-body-2 text-t-secondary` inside the first card, never under the H1.

3. **Inter Display app-wide, clean.** Set `--font-inter: var(--font-inter-display)` (drop
   Gilroy from the font stack). Remove the Gilroy `localFont` + `--font-gilroy` from the
   body className. The reference type ramp is the law (below). This is what finally makes
   the font "change" visibly and consistently.

4. **Use the reference token system only.** Color/space/shadow/radius come from the
   `@theme` tokens in `globals.css` (`t-primary`, `t-secondary`, `b-surface1/2`,
   `s-subtle`, `s-border`, `primary-01..05`, `shadow-depth`, `rounded-3xl`). **Zero raw
   hex** in page code. Brand blue = `primary-01` (#2A85FF). Status: success `primary-02`,
   danger `primary-03`, warning `primary-05`.

5. **Everything lives in a `Card`.** Sections are `Card` with a 48px (`h-12`) header row,
   title in `text-h6`, content padded `pt-3` (`components/Card`). No bare divs with custom
   borders/shadows. One card = one idea.

6. **Two-column page rhythm.** Match the reference layout grammar: `flex max-lg:block`
   with `.col-left` (primary, ~2/3) and `.col-right` (secondary, ~1/3) wrapped by
   `Layout`. Don't invent bespoke grids. Stack on mobile (`max-lg:block`).

7. **Restrained color.** Surfaces are near-grey (`b-surface1/2`); color is reserved for
   ONE primary action and status badges. No multi-color gradient cards, no colored panel
   backgrounds, no decorative accent rules. If a screen has >2 saturated colors competing,
   it's wrong.

8. **Plain-language labels, fewer pages.** No internal jargon in the UI. Rename per the
   glossary in §4. Collapse near-duplicate routes (one Billing page with tabs, not five
   sidebar leaves). Hide/cut coming-soon stubs from nav entirely.

9. **Real empty / loading / error states.** Every data surface has: a `Spinner`-based
   loading state, a `NoFound`-style empty state (icon + one line + one action), and a
   single inline error banner using tokens (not `bg-red-50`). No blank flashes, no raw
   "undefined".

10. **Density discipline & spacing.** Follow the reference spacing scale (card gap 4/5,
    section `mb-5`, list rows comfortable). Don't cram 6 KPIs + 3 tables + a chart on one
    screen. Max ~3-4 primary sections per page; push the rest behind a tab or a row click.
    Tables over dense card-grids for list data.

---

## 2. TYPOGRAPHY — the reference ramp (copy verbatim, do not invent sizes)

Family: **Inter Display** only. Tailwind utility `font-inter`. Weights 300/400/500/600/700.

| Token (Tailwind) | Size | Weight | Use |
|---|---|---|---|
| `text-h4` | 2rem | 600 | the page title (in Header) — the ONLY H1-level on a page |
| `text-h5` | 1.5rem | 500 | section title on small screens / hero number |
| `text-h6` | 1.25rem | 600 | **Card titles** |
| `text-sub-title-1` | 1rem | 600 | sub-section labels |
| `text-body-1` | 1rem | 400 | default body |
| `text-body-2` | 0.875rem | 400 | secondary body, table cells, muted context |
| `text-button` | 0.875rem | 600 | buttons, tabs |
| `text-caption` | 0.75rem | 400 | metadata, timestamps |
| `text-overline` | 0.625rem | 500 | tiny labels (use sparingly; NOT as a page eyebrow) |

Rules: never use a heading bigger than `text-h4` inside the content area. Never stack two
headings. Muted text = `text-t-secondary`/`text-t-tertiary`, never grey hex.

---

## 3. COLOR / SURFACE / SHADOW (from `@theme`)

- Page background `bg-b-surface1`; cards `bg-b-surface2` (the `.card` class already does
  radius `rounded-3xl` + `shadow-depth` + `p-4`).
- Text: `t-primary` (near-black/near-white), `t-secondary`, `t-tertiary`. Links/brand:
  `t-blue` = `primary-01`.
- Borders: `s-subtle` (hairlines), `s-border`, `s-stroke2`. Default border width 1.5px.
- Status badges (reuse `components/Badge`): success→`primary-02`, info→`primary-01`,
  warning→`primary-05`, danger→`primary-03`, neutral→shade. One semantic map, used
  everywhere (the AIM `_shared` risk/role maps are fine to keep — just feed them the
  tokens).
- Shadows are token-only (`shadow-depth`, `shadow-widget`, `shadow-dropdown`). No ad-hoc
  `box-shadow`.

---

## 4. INFORMATION ARCHITECTURE — cut the jargon, cut the pages

Rename in UI (keep routes/data as-is; only labels change where listed):

| Current (jargon) | Use instead |
|---|---|
| Suppression / Do-Not-Call | **Do-Not-Call list** |
| Cost Explorer | **Spending** (or a tab under Billing) |
| Plan & Ledger | **Plan** |
| Capabilities | **What it can do** (or fold into Setup) |
| Command Center | (remove — legacy; not a user concept) |
| Command History | **History** |
| Authorized Users | **Team** |
| Test Console | **Try it** |
| Create Studio (4 stubs) | **remove from nav entirely until built** |

Page consolidation targets:
- **Billing**: one page, internal `Tabs` (Overview / Spending / Vendors / Plan / Audit) —
  not 5 sidebar leaves.
- **AI Manager**: see §6 — collapse 8 tabs → 3.
- **Vendors** appears twice (Money group + Foundation group) — keep one.
- Cut coming-soon stubs from the sidebar; a feature shows up when it's real.

Nav target: ~7-8 groups, ≤5 children each, plain nouns — mirror the reference's shape.

---

## 5. COMPONENT REUSE MAP (use these, do not rebuild)

Both kits share the component library. Always reach for the existing component:

- Page shell → `Layout` (sets title + sidebar + sticky header).
- Section → `Card` (title `text-h6`, optional `headContent`/`Select`).
- Lists → `Table` + `TableRow` (not card-grids for tabular data).
- Filtering/search → `Filters`, `Search`, `Select`, `Dropdown`.
- Forms → `Field`, `FieldImage`, `FieldFiles`, `Checkbox`, `Switch`, `Range`, `Editor`.
- Tabs within a page → `Tabs`.
- Empty state → `NoFound`. Loading → `Spinner`. Status → `Badge`.
- KPIs → reference `Overview`/`Percentage`/`CardChartPie` patterns (our `KpiCard`/
  `Sparkline` are OK only if they render with reference tokens and live inside a `Card`).

If a needed component is missing from the reference, look in
`C:\Users\kunal\Desktop\Core_2-Capsy-Dashboard` (secondary) before building anything new.

---

## 6. AI MANAGER SIMPLIFICATION PLAN (the founder's #1 complaint)

Current: `/ai-manager` is a spinner redirect into a 9-file section with an 8-tab pill rail
(Overview, Test Console, Command History, Approvals, Capabilities, Setup, Authorized Users,
Command Center) on top of the invented PageHeader. This is the "too complex" page.

Target — **ONE page title "AI Manager", THREE plain tabs, reference `Tabs` component, no
eyebrow/subtitle, no pill-rail, no Command Center:**

1. **Home** (was Overview + Command Center, merged) — a single `<Layout title="AI Manager">`
   with a 2-column reference layout:
   - col-left: one "Recent activity" `Card` (the command/session log as a `Table`: time,
     who, what it did, result badge). One status strip of ≤3 KPIs (commands today, pending
     approvals, success rate) as a single `Overview`-style card — not 6 tiles.
   - col-right: "Pending approvals" `Card` (list + approve/deny inline) and a small
     "Try a command" entry that opens the Try-it surface.
2. **Try it** (was Test Console) — one `Card`: a single input + send, and the response.
   No console jargon, no multi-panel debugger.
3. **Setup** (Setup + Capabilities + Team merged via in-page `Tabs` or sections) — what the
   manager is allowed to do, who can use it, PIN/risk thresholds. One page.

Removals: delete the `_shared.tsx` pill-rail and its `AimHeader` (drop `PageHeader`); delete
the `/ai-manager` redirect (make Home the index); remove "Command Center", "Capabilities",
"Command History", "Authorized Users" as separate sidebar/tabs entries (folded above).
Sidebar shows just **AI Manager** (+ optionally the 3 tabs as children, max).

Language: "Approvals" stays (clear); everything else uses the plain words in §4. No "risk
L0-L4" raw codes in the primary UI — show "Safe / Needs approval / Blocked" with the badge
tone; keep the L-code only in a tooltip/detail.

Result the founder should feel: open AI Manager → see what it did, what's waiting, try a
command — three things, one clean screen, same look as the reference Dashboard.

---

## 7. PER-PAGE ACCEPTANCE CHECKLIST (every ported page must pass ALL)

Structure & reuse
- [ ] A matching reference page/template was found and its structure was ported (not
      re-derived). If none exists, reference components were composed in the reference's
      layout grammar.
- [ ] Page is wrapped in `Layout` with a single `title`. No second top-level heading in
      the content.
- [ ] Sections are `Card`s (title `text-h6`, content `pt-3`). No bare custom panels.
- [ ] Two-column rhythm (`col-left`/`col-right`) or a single reference grid; stacks on
      mobile.

Headings & type
- [ ] **No `PageHeader`, no eyebrow, no accent rule, no subtitle paragraph** anywhere.
- [ ] All type uses the reference ramp tokens; nothing bigger than `text-h4` in content;
      no two stacked headings.
- [ ] Font renders as Inter Display throughout (Gilroy removed from the stack).

Color & surface
- [ ] Zero raw hex in the page; only `@theme` tokens.
- [ ] ≤2 saturated colors competing; color reserved for one primary action + status.
- [ ] Shadows/radii are token-based (`.card`, `shadow-*`, `rounded-3xl`).

Content & language
- [ ] Labels are plain language (per §4 glossary); no internal jargon visible.
- [ ] Information density is restrained (≤3-4 primary sections); overflow goes behind a
      tab or a row click.
- [ ] Tabular data is a `Table`, not a card-grid.

States
- [ ] Loading uses `Spinner`; empty uses a `NoFound`-style block (icon + one line + one
      action); error is one token-based inline banner.
- [ ] No raw "undefined"/null flashes; numbers/dates are formatted.

Nav & routing
- [ ] The page earns its place in nav (no coming-soon stub, no duplicate route).
- [ ] Active nav state is correct; the sidebar group/label matches the simplified IA.

---

## 8. FRONTEND-DESIGN SKILL TAKEAWAYS (applied to THIS project)

The skill pushes a bold, distinctive, intentional aesthetic and warns against generic
"AI-slop" (Inter-on-white, purple gradients, predictable layouts). Applied here:
- **Intentionality over intensity.** The reference IS the committed aesthetic: refined,
  restrained, near-monochrome surfaces with a single decisive blue. Our job is to execute
  THAT vision with precision — not to add our own flourishes (the Signal eyebrow/accent
  rule was exactly the kind of un-asked-for decoration to cut).
- **Typography as the identity.** Inter *Display* (not plain Inter, not a fallback mix) is
  the chosen face; the tight letter-spacing + display cut is the character. Get the ramp
  and weights exact and the whole product reads premium — this is the highest-leverage fix.
- **Restraint is the design.** For a refined/minimal direction the skill says elegance
  comes from spacing, hierarchy, and subtlety. So our "polish" budget goes into consistent
  spacing, clean empty states, and token discipline — not gradients or motion.
- **One memorable thing, done well.** Keep the reference's depth-shadow cards + decisive
  blue + airy two-column rhythm as the signature; don't dilute it with competing accents.
- **Match complexity to vision.** This is a minimal direction → less code, fewer effects,
  more precision. Resist maximalist embellishment.

---

## 9. SOURCES (file:line evidence)

- Reference font: `core-2-dashboard-builder-react/app/layout.tsx` (InterDisplay 300-700,
  `--font-inter-display`); tokens map `--font-inter: var(--font-inter-display)` in its
  `app/globals.css` `@theme`.
- Reference single-title pattern: `components/Header/index.tsx:50` (`text-h4`),
  `templates/HomePage/index.tsx` (`<Layout title=...>`, two-column `col-left/col-right`).
- Reference type ramp: `app/globals.css` `@theme` (`--text-h4..--text-overline`).
- Reference Card: `components/Card/index.tsx` (`h-12` header, `text-h6` title, `pt-3`).
- Our font bug: `famit-panel/app/globals.css:204`, `app/layout.tsx:37-50,68`.
- Our invented masthead: `components/PageHeader/index.tsx`, `globals.css:740-760`.
- Our AIM maze: `app/ai-manager/_shared.tsx:18-65` (8 tabs), `app/ai-manager/page.tsx`
  (spinner redirect), 9 route files under `app/ai-manager/`.
- Our nav sprawl/jargon: `contstants/navigation.tsx` (9 groups, ~30 leaves, Create Studio
  stubs).
