# UI Font + Heading Plan — make the type change VISIBLE, match the reference

READ-ONLY design wave. This doc specifies the font + heading fix. No app code
edited here. Companion to `ui-reuse-core2-never-from-scratch.md` (2026-06-10).

Reference kit (authoritative look): `C:\Users\kunal\Desktop\core-2-dashboard-builder-react`
Our app: `C:\Users\kunal\Desktop\caps\famit-panel`

---

## 1. WHY the founder says "the font still did not change" (root cause, proven)

It is **not** a caching/build problem — it is a **missing-weights fallback**.

- `famit-panel/app/layout.tsx:37-52` registers Gilroy with **only two faces**:
  `Gilroy-Light.otf` mapped to weight **300** and `Gilroy-ExtraBold.otf` mapped
  to weight **800**. Confirmed on disk — `famit-panel/public/fonts/` contains
  exactly `Gilroy-Light.otf` + `Gilroy-ExtraBold.otf` and nothing else. The free
  Gilroy release genuinely ships only these 2 weights.
- The font stack is `--font-inter: var(--font-gilroy), var(--font-inter-display)`
  (`app/globals.css:204`) and `html { font-family: var(--font-gilroy), … }`
  (`globals.css:283`). So Gilroy is *first* in the cascade.
- BUT almost all UI text is rendered at weights **400 / 500 / 600 / 700**:
  body = 400 (`--text-body-1--font-weight:400`), captions 500, sub-titles/buttons
  600, most headings 600 (`--text-h1..h6--font-weight:600`). Gilroy has **no
  face at 400/500/600/700**. The browser will not synthesize them from the
  300/800 faces in a useful way; with two distant weights it snaps each request
  to the **nearest available Gilroy weight or, more commonly, falls through to
  the next family in the stack** — `InterDisplay`. Net effect: the overwhelming
  majority of text (all body, all 600-weight headings) renders in **Inter, not
  Gilroy**. Only true 300 and true 800 text could pick up Gilroy.
- The code even *documents* this trap in its own comments (`layout.tsx:34-36`):
  "ships only Light (300) + ExtraBold (800)… InterDisplay remains the fallback
  so the missing mid-weights render as Inter rather than snapping to Gilroy."

**Conclusion:** the app is, for ~95% of its visible text, already rendering
Inter. Adding/removing Gilroy at 300/800 changes almost nothing the founder
looks at — hence "the font didn't change." Any fix that keeps a 2-weight Gilroy
as the primary family will keep looking identical.

---

## 2. What the REFERENCE kit actually uses (so we match it, not guess)

- `core-2-dashboard-builder-react/app/layout.tsx:7-31` loads **one** typeface:
  **InterDisplay**, with the **full weight set 300 / 400 / 500 / 600 / 700**
  (`InterDisplay-Light/Regular/Medium/SemiBold/Bold.woff2`).
- `core-2-dashboard-builder-react/app/globals.css:204`:
  `--font-inter: var(--font-inter-display);` — InterDisplay IS the whole app
  font. There is **no Gilroy** anywhere in the reference. The premium look the
  founder approves of is **Inter Display**, used at the right weights.
- Reference heading weights (`globals.css:206-228`): h1 = 300, h2/h3/h5 = 500,
  h4/h6 = 600. It leans on Inter's light/medium faces for big display headings —
  which is exactly why it reads clean and premium, and exactly the faces our
  app is currently *missing* in Gilroy.

So the reference's "designed" feel comes from **Inter Display with all five
weights present** — and our app already ships those five woff2 files in
`famit-panel/public/fonts/`. The premium font is already in the box; Gilroy is
the thing breaking it.

---

## 3. DECISION — adopt the reference font app-wide (Option A)

**Adopt InterDisplay (the reference kit's font) as the single app-wide family.
Remove Gilroy from the primary cascade.** This is decisive, free, already
bundled, ships complete weights, and makes our type **identical to the look the
founder approved**. Picking Option A because:

- It is the *actual* reference font — per the HARD RULE we PORT his kit, we do
  not approximate. Matching his font = matching his design, not a lookalike.
- It is free, OSS-licensed, and **already present** in our repo (5 woff2 files,
  300-700). Zero new assets, zero founder-blocked downloads.
- It has every weight our type scale requests (400/500/600/700) — so the change
  is **visible everywhere**, not just at 300/800.
- It removes the silent Inter-fallback bug entirely.

Option B (keep Gilroy, buy/obtain the full 6-weight commercial Gilroy and load
400-700) is **rejected**: it is founder-blocked (paid/missing weights), adds
new assets, and still only reaches parity with a font we already ship. Not worth
it. (If the founder later insists on the Gilroy *brand* face, it can return as a
**display-only** font for the wordmark/logo lockup at 800 — never as body.)

### Exact wiring (the change to make in the build wave, not now)

`famit-panel/app/layout.tsx`
- **Delete** the entire `gilroy = localFont({…})` block (lines 33-52) and its
  `${gilroy.variable}` from the `<body>` className (line 68). Keep only
  `interDisplay`. Body becomes:
  `className={\`${interDisplay.variable} bg-b-surface1 font-inter text-body-1 text-t-primary antialiased\`}`

`famit-panel/app/globals.css`
- Line 204: `--font-inter: var(--font-inter-display);`  (drop the Gilroy var —
  matches reference exactly).
- Lines 283-285: `html { font-family: var(--font-inter-display), ui-sans-serif,
  system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }`
  (drop `var(--font-gilroy)`).

Result: every weight from 300-700 resolves to a real InterDisplay face. The
change is immediately, globally visible. (Optionally keep the two Gilroy .otf
files on disk only if a Gilroy display wordmark is wanted later; nothing in the
cascade should reference them.)

---

## 4. Heading typography — clean header, NO subtitle (founder fix #1)

The reference page title is a single line — `components/Header/index.tsx:100`:
`<div className="mr-auto text-h4 max-lg:text-h5 max-md:hidden">{title}</div>`.
**No eyebrow, no accent bar, no subtitle, no description.** That is the founder's
explicit ask: "HEADINGS must have NO description/subtitle below them."

### What is wrong in our app today
`famit-panel/components/PageHeader/index.tsx` renders an **eyebrow + animated
signal glyph + a brand-blue accent rule (`.page-head::before`) + a subtitle
(`.page-head-sub`)** on top of the title. Pages pass `subtitle="…"` and
`eyebrow="…"` (e.g. `app/billing/_shared.tsx:46`). This is the over-decorated,
"too complex / jargon" header the founder is rejecting.

### Target heading spec (port the reference exactly)

Use a **stripped masthead**: just the title (and an optional right-aligned
actions slot). No eyebrow, no glyph, no accent bar, **no subtitle**.

```tsx
// components/PageHeader/index.tsx — simplified to match the reference
type PageHeaderProps = {
    title: string;
    actions?: React.ReactNode;   // right-aligned slot ONLY
    className?: string;
};

const PageHeader = ({ title, actions, className }: PageHeaderProps) => (
    <div className={`flex items-start justify-between gap-4 mb-6 max-md:mb-4 ${className || ""}`}>
        <h1 className="text-h4 max-lg:text-h5 text-t-primary">{title}</h1>
        {actions && (
            <div className="flex items-center gap-3 shrink-0 max-md:hidden">
                {actions}
            </div>
        )}
    </div>
);
```

- **Drop** the `eyebrow` and `subtitle` props entirely (and the
  `signal-glyph`/accent-bar markup). Drop `.page-head*` CSS usage from the
  masthead; callers must stop passing `subtitle=` / `eyebrow=`.
- **Heading size/weight = the reference's `text-h4` (→ `text-h5` under lg).**
  After Option A, align our `app/globals.css` `--text-h*` tokens to the
  reference's values so headings match pixel-for-pixel:
  - `--text-h4: 2rem; line-height: 1.45; letter-spacing: 0.003em; font-weight: 600;`
  - `--text-h5: 1.5rem; line-height: 1.45; letter-spacing: -0.01em; font-weight: 500;`
  - (and h1 300 / h2 500 / h3 500 / h6 600 as in the reference if/when those
    sizes are used). Our current tokens use a different scale + all-600 weights;
    moving to the reference scale is what makes headings *feel* like the kit.
- Any contextual labeling the eyebrow used to carry (e.g. "Billing") belongs in
  the **sidebar/section nav or the sticky `<Layout>` header**, not stacked above
  the page title.

---

## 5. Handoff checklist for the build wave (do later, not in this read-only wave)

1. `layout.tsx`: remove Gilroy localFont block + `gilroy.variable`. Keep
   InterDisplay only.
2. `globals.css:204` + `:283-285`: point font vars/stack to InterDisplay only.
3. Align `--text-h4` / `--text-h5` (and h1-h3,h6) tokens to the reference values.
4. Simplify `components/PageHeader/index.tsx` to {title, actions} — no eyebrow,
   no subtitle, no signal glyph, no accent bar.
5. Sweep callers (`app/billing/_shared.tsx`, all `app/ai-manager/*`,
   `app/run`, `app/funnels`, `app/workflows`, `app/booking`, `app/login`, etc.)
   to drop `subtitle=` / `eyebrow=` props.
6. Visual check: body + 600-weight headings now render InterDisplay (no Inter
   fallback because there is no missing-weight gap) → the change is finally
   visible to the founder.
