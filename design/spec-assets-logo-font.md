# Asset Spec — Logo + Font (for the Foundation agent)

Author: Asset-Locator agent · Date: 2026-06-10
Scope: locate founder's real logo, plan background removal + placement, confirm Gilroy
font and write the exact `next/font/local` registration. Figma access check.

---

## 1. LOGO — CHOSEN ASSET

**Source of truth (founder's real, current brand mark):**
- `C:\Users\kunal\Desktop\LOGO.zip` (dated **2026-06-04**, most recent) contains exactly two files:
  - `dark_mode_logo_main.png`  — 1254x1254, **WHITE** glyph (for dark backgrounds)
  - `light_mode_logo_main.png` — 1254x1254, **BLACK** glyph (for light backgrounds)
- Loose identical copies also at `D:\Downloads\dark_mode_logo_main.png` and `D:\Downloads\light_mode_logo_main.png`.
- **Byte-identical copies are ALREADY in the repo:**
  - `famit-panel/public/images/logo-dark.png`  (= dark_mode_logo_main.png)
  - `famit-panel/public/images/logo-light.png` (= light_mode_logo_main.png)

**The mark:** an abstract rounded-rectangle envelope / message glyph with a folded
top-left corner (a "page/chat" cut-out). Clean, geometric, premium. This is the brand
mark that must REPLACE the current "signal-glyph" equalizer/waveform bars.

**Background state — NEEDS REMOVAL:** both source PNGs are `mode=RGB` with **NO alpha
channel**, painted on a **solid near-white background** (corner pixels ~253,253,254 and
~241,241,241). Not checkerboard, not transparent. So as-is they cannot sit on the dark
sidebar (white-on-white) or on tinted panels.

### Background removal — ALREADY DONE (ready-to-use transparent PNGs produced)

`rembg` is NOT installed; `PIL (Pillow 12.2.0)` IS. rembg is unnecessary here anyway —
the two files are a clean black/white inverse pair, so I derived a crisp alpha mask from
the black-on-white `light` file via inverse-luminance keying (lum<=30 fully opaque,
>=255 transparent) and painted two ink colors. Output (verified visually, clean edges,
no halo/checkerboard):

| File (in `design/logo-out/`) | Ink | Use on | Size |
|---|---|---|---|
| `famit-mark-dark.png`       | near-black `#111113` | LIGHT backgrounds | 1254x1254 (full-frame, original padding) |
| `famit-mark-white.png`      | white `#FFFFFF`      | DARK backgrounds  | 1254x1254 (full-frame) |
| `famit-mark-dark-trim.png`  | near-black `#111113` | LIGHT backgrounds | 1454x1454 (auto-cropped + 8% pad — **use these for tight badge tiles**) |
| `famit-mark-white-trim.png` | white `#FFFFFF`      | DARK backgrounds  | 1454x1454 (auto-cropped + 8% pad) |

Regeneration command (if needed) is the PIL snippet that reads
`logo-light.png`, ramps alpha from luminance, and writes both inks + autocropped variants.

> If the founder later says these auto-derived edges aren't perfect, the fallback is to
> ask him for a native transparent PNG/SVG export. But the current output is crisp and
> production-ready — no founder action required.

### Placement plan (Foundation agent does this)

The current placeholder glyph (the "signal-glyph" eq bars) appears in **TWO code sites**,
both must be swapped:

1. **`famit-panel/components/Logo/index.tsx`** — the reusable Logo (used by Sidebar at
   `components/Sidebar/index.tsx:88` and Header at `components/Header/index.tsx`).
   - Inside the `<span ...size-9 rounded-[0.7rem] bg-shade-01...>` tile, REMOVE the
     `signal-glyph` block (`<span class="signal-glyph"><i/><i/><i/><i/></span>`) and the
     `brand-glow` layer, and render the mark instead.
   - Recommendation: copy the two trim PNGs into `public/images/` (e.g.
     `famit-mark-white-trim.png` for the dark `bg-shade-01` tile) and use
     `next/image`:
     ```tsx
     import Image from "next/image";
     ...
     <span className="relative flex items-center justify-center size-9 shrink-0 rounded-[0.7rem] bg-shade-01 overflow-hidden ring-1 ring-s-subtle dark:ring-shade-04">
       <Image src="/images/famit-mark-white-trim.png" alt="" width={22} height={22} className="object-contain" priority />
     </span>
     ```
     (The tile is dark `bg-shade-01`, so the WHITE-ink mark is correct. Mark renders ~22px
     inside the 36px/`size-9` tile.) Keep the existing `wordmark` "Famit" text + dot as-is.

2. **`famit-panel/app/login/page.tsx`** — login HARD-CODES the same eq-bar `signal-glyph`
   inline in **three places** (it does NOT import the Logo component):
   - ~line 54–55: left brand panel, big tile `size-11 rounded-2xl bg-white/5` (DARK panel → **white-ink** mark)
   - ~line 105–107: right sign-in panel, tile `size-10 rounded-2xl bg-shade-01` (DARK tile → **white-ink** mark)
   - ~line 121: a small `signal-glyph !h-3` decorative instance (can be dropped or replaced with a tiny mark)
   Swap each `signal-glyph` span for the same `<Image src="/images/famit-mark-white-trim.png">` pattern, sized to the tile.

3. After swap, the now-unused `.signal-glyph` / `.brand-glow` CSS in `globals.css` can stay
   (harmless) or be cleaned up later — not blocking.

**Sizing guide:** sidebar/header tile mark ≈ 20–24px inside a 36–44px tile; login left
big tile ≈ 26–28px inside 44px; favicon/OG can reuse `famit-mark-dark-trim.png` on white.

---

## 2. FONT — GILROY

**Zip confirmed:** `D:\Downloads\gilroy-font.zip` exists (dated 2026-06-10).

**Weights inside — ONLY TWO (this is the Gilroy FREE release):**
- `gilroy-font/Gilroy-FREE/Gilroy-Light.otf`     → weight **300**
- `gilroy-font/Gilroy-FREE/Gilroy-ExtraBold.otf` → weight **800**
- (plus a EULA pdf + macOS junk; no other weights — NO Regular/Medium/SemiBold/Bold ship in the free pack)

> ⚠️ CONSTRAINT TO FLAG: only Light(300) + ExtraBold(800) are available. The app's type
> scale uses 300/400/500/600/700. With only two real files, `next/font/local` will pick the
> nearest declared weight; intermediate weights (400–700) will render as the closest of the
> two (so body text → Light-ish, anything 600+ → ExtraBold). This is acceptable for a first
> pass but looks "either thin or very heavy." **If the founder wants the full Gilroy ramp,
> he must supply the paid weights (Regular/Medium/SemiBold/Bold .otf).** Record this as an
> open item; do NOT block the shell on it.

### Exact `next/font/local` registration plan

Current font wiring (do NOT rip out — extend/replace cleanly):
- `app/layout.tsx` registers `interDisplay = localFont({...})` from `public/fonts/InterDisplay-*.woff2`,
  exposes CSS var `--font-inter-display`, body className uses `${interDisplay.variable} ... font-inter`.
- `app/globals.css:204` maps `--font-inter: var(--font-inter-display);` and
  `globals.css:283` sets `font-family: var(--font-inter-display), ui-sans-serif, ...`.

**Steps:**
1. Unzip the two OTFs into `famit-panel/public/fonts/`:
   - `public/fonts/Gilroy-Light.otf`
   - `public/fonts/Gilroy-ExtraBold.otf`
   (next/font/local accepts .otf; no conversion needed. Optional: convert to .woff2 for
   smaller payload, but not required.)
2. In `app/layout.tsx`, add a Gilroy `localFont` and make it the app default. Keep Inter as
   fallback var if desired, but point `--font-inter` / the body family at Gilroy. Minimal change:
   ```tsx
   const gilroy = localFont({
     src: [
       { path: "../public/fonts/Gilroy-Light.otf",     weight: "300", style: "normal" },
       { path: "../public/fonts/Gilroy-ExtraBold.otf", weight: "800", style: "normal" },
     ],
     variable: "--font-gilroy",
     display: "swap",
   });
   ```
   Then on `<body>` add `${gilroy.variable}` and, in `globals.css`, change
   `--font-inter: var(--font-inter-display);` →
   `--font-inter: var(--font-gilroy), var(--font-inter-display);`
   and update the `font-family:` at globals.css:283 to lead with `var(--font-gilroy)`.
   This makes Gilroy app-wide default with InterDisplay as the graceful fallback for the
   missing 400/500/600/700 weights (so mid-weight text stays legible rather than snapping
   to ExtraBold).
3. (Optional polish, recommended given only 2 weights) — explicitly use Gilroy ExtraBold
   only for display/headings (`.wordmark`, `h1–h3`, KPI numbers) and let body keep Inter,
   so you get Gilroy's character on the marketing-grade type without the thin/heavy gap on
   paragraphs. Decide with founder; safe default = step 2 (Gilroy everywhere, Inter fallback).

---

## 3. FIGMA ACCESS — NOT POSSIBLE (as expected)

- `.fig` files are binary; no Figma MCP server is connected in this harness (the available
  MCP servers are claude-in-chrome, Shopify, meta-ads, context7 — none is Figma).
- Therefore Figma kits (`D:\Downloads\Core Dashboard Builder 2.0.fig`, the Flowaxon kit)
  remain UNREADABLE. Design source of truth stays the **Core_2 code kit**
  (`C:\Users\kunal\Desktop\Core_2-Capsy-Dashboard`) per the IRON RULE.

---

## 4. Rejected / non-brand candidates (for the record)

These were found by name but are NOT the brand — do not use:
- `D:\Downloads\logo2.png`, `logo1-removebg-preview.png`, `logo2-removebg-preview.png` —
  unrelated old experiments (a red/black dagger-shield emblem; chrome interlocking rings).
- `D:\Downloads\created_2d_logo.png` — 512x512 but effectively blank (white on white, 2.4KB).
- `D:\Downloads\GPT_Image_1_create_a_logo_...png`, `Flux_Dev_*`, `gemini-2.5-flash-image_*` —
  AI logo-generation experiments, not the chosen brand.
- `D:\Downloads\logo kunal.jpg` — personal/unrelated.

---

## TL;DR for Foundation agent
1. Use `design/logo-out/famit-mark-white-trim.png` (white ink, transparent) on the dark
   sidebar/header/login tiles; `famit-mark-dark-trim.png` (dark ink) for any light surface
   / favicon / OG. Copy chosen file(s) into `famit-panel/public/images/`.
2. Replace the `signal-glyph` eq-bars in `components/Logo/index.tsx` AND the THREE inline
   instances in `app/login/page.tsx` with `<Image>` of the mark.
3. Unzip Gilroy Light + ExtraBold into `public/fonts/`, register via `next/font/local`,
   set as app default with InterDisplay fallback (only 2 weights exist — flag for paid set).
4. Figma stays unreadable; Core_2 code remains the design source.
