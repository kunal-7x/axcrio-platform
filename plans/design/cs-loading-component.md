# DESIGN SPEC — `GenerationLoader` (the premium AI-generation loading component)

> **READ-ONLY DESIGN WAVE.** This is the pixel-accurate, buildable spec for the **hero loading detail** of
> Creative Studio: the dark charcoal card on black with the **dot-matrix neural-energy field** that appears
> the instant a user clicks *Create Image / Create Banner / any generation action*, holds while the AI Asset
> Service renders, and fades smoothly into the result. Reference feel: ChatGPT / Google Flow image+video gen.
>
> Conforms to `CREATIVE_STUDIO_PHASE2_SPEC.md §1` and the founder UI rules (`design/ui-design-principles.md`,
> `design/creative-studio-ui.md`). Backend contract = `design/asset-service-backend.md` §5/§8 (job state +
> SSE stream). Built into `famit-panel` on the existing **Signal** premium-UI token system (`app/globals.css`).
>
> **Relationship to `CreativeSkeleton` (don't confuse them):** `CreativeSkeleton` (`creative-studio-ui.md §9`)
> is the **per-card liquid skeleton** that fills *each variant grid slot* and morphs in place into one finished
> image. `GenerationLoader` (THIS doc) is the **full-area hero state** — one large charcoal card with the
> dot-matrix field + cycling status lines — shown over the *whole* preview/generation area while the batch
> spins up (before any single variant has bytes). They COMPOSE: `GenerationLoader` is the batch-level "the
> engine is thinking" surface; `CreativeSkeleton` is the per-image "this slot is developing" surface. A page
> may show `GenerationLoader` first (job `queued`/`running`), then dissolve it into a grid of `CreativeSkeleton`
> cards as variants begin streaming. Both are token-built, reduced-motion-safe, zero-raw-hex. This component is
> reusable across image / banner / ad-creative / brochure-cover / video-thumbnail generation.

---

## 0. THE ONE IMPRESSION

> A user clicks **Generate**. Instantly the area goes to a **deep charcoal rounded card floating on black**.
> Tiny muted **"Thinking"** label, a bold **"Creating image"** title, and below it a **breathing field of
> soft grey-white dots** — dense and bright at the centre, sparse and faded at the edges, slowly pulsing,
> shimmering and drifting like a neural energy field. One cycling status line underneath ("Designing visual
> direction…"). No spinner-as-afterthought, no fake percentage, no colourful toy. It feels like an *engine*
> is working. When the image is ready, the dots **collapse inward and the card cross-fades into the result.**

Minimal, premium, futuristic, smooth, calm. NOT colourful, NOT childish, NOT a normal SaaS loader.

---

## 1. WHERE IT LIVES (file + reuse)

- **New component:** `famit-panel/components/GenerationLoader/index.tsx` (+ a small co-located
  `field.ts` canvas helper, see §5). This is a **second new component** alongside `CreativeSkeleton`
  (`creative-studio-ui.md §9`) — both are the only genuinely-new components in Creative Studio; everything
  else PORTS `core-2-dashboard-builder-react`.
- **Tokens / surfaces it reuses (zero new colour):** `.surface` / `.card` (the charcoal panel),
  `shadow-widget` / `shadow-depth`, `b-surface1/2`, `b-dark1/2`, `t-primary/secondary/tertiary`,
  `primary-01` (the lone brand-blue accent), `.meter`/`.meter-fill` (optional real progress),
  `rounded-3xl`/`rounded-4xl`, the existing `@media (prefers-reduced-motion: reduce)` block, and the
  `Button` component (`isBlack`/`isStroke`/`isCircle`, `icon=`) for retry/cancel. **No new npm dep.**
- **CSS keyframes** for the CSS-fallback field + the chrome (Thinking dot, status-line crossfade, card
  fade-in/out) are added to `app/globals.css` under the existing `@layer components` "Signal" section,
  named `gl-*` (GenerationLoader). The canvas path needs **no** keyframes (JS-driven).
- **Dark/light:** the card is intentionally **charcoal-on-black in BOTH themes** (it is a focused
  "engine" moment, like a media viewer) — built from `b-dark1`/`b-dark2`/`shade-*` tokens so it stays
  on-brand without a raw hex. The dots derive their colour from `--gl-dot` (a token alias, §3.3) so the
  field is theme-independent by design but still swaps cleanly if a light variant is ever wanted.

---

## 2. ANATOMY (the charcoal card)

```
┌─ black scrim (optional, modal/full-bleed mode) ──────────────────────────────────┐
│                                                                                   │
│        ┌─ charcoal card  (.gl-card — rounded-4xl, b-dark, shadow-depth) ──────┐   │
│        │                                                                       │   │
│        │   • Thinking                       (muted overline + pulsing dot)     │   │
│        │   Creating image                   (bold title, text-h5/h4)           │   │
│        │                                                                       │   │
│        │            · · ∙ ∙ • ● ● ● • ∙ ∙ · ·                                   │   │
│        │          · ∙ • ● ●  ◉ ◉ ◉  ● ● • ∙ ·          ← DOT-MATRIX FIELD       │   │
│        │            · · ∙ ∙ • ● ● ● • ∙ ∙ · ·             (canvas, §5)          │   │
│        │                                                                       │   │
│        │   Designing visual direction…       (cycling status line, §4)         │   │
│        │   ▱▱▱▱▱▱▱▱▱▱  (optional real progress hairline — only if SSE total)    │   │
│        │                                                                       │   │
│        │                         [Cancel]            (optional, §6)            │   │
│        └───────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

- **Card** (`.gl-card`): `rounded-4xl` (2rem), padding `p-8 max-md:p-6`, `bg-b-dark2` body with a
  `bg-b-dark1` inner field zone, `shadow-depth`, a hairline `ring-1 ring-white/[0.04]` top edge for the
  premium "lit from above" feel. Centred content, `min-h` set so the field has room (see §7 sizing).
- **"Thinking" label:** `text-overline text-t-tertiary` (uppercase via the existing `.text-overline`
  rule) + a 5px **pulsing dot** in `primary-01` to its left (`.gl-think-dot`, opacity-pulse 0.4→1 over
  ~1.6s). This is the muted "Thinking" the spec asks for.
- **Title:** `text-h5 max-md:text-h6 font-semibold text-t-light` — the bold "Creating image" / "Creating
  banner" (driven by the `title` prop, §8). One clean line, no subtitle (founder rule).
- **Dot-matrix field:** the hero — a `<canvas>` (default) sized to fill the field zone (§5).
- **Status line:** `text-body-2 text-t-secondary` centred, crossfades between the 5 lines (§4).
- **Progress hairline:** the existing `.meter` / `.meter-fill` (`primary-01`), shown **only** when real
  SSE progress (`total`) is known (§4.2). Never a fabricated number.
- **Cancel / Retry:** `Button isStroke` (cancel) / `Button isBlack` + `Button isStroke` (retry/back) —
  rendered only in the relevant states (§6).

---

## 3. THE DOT-MATRIX NEURAL FIELD — exact visual model

### 3.1 Render approach decision (canvas vs CSS) — **CANVAS, with a CSS-grid fallback**
- **Primary = a single lightweight `<canvas>` particle field.** Chosen over a CSS-transform dot grid
  because the look requires **~120–220 independently-animated dots** each with its own size, opacity ramp,
  pulse phase and slow drift. Doing that in CSS means 200 DOM nodes each running 2–3 keyframe animations =
  hundreds of composited layers and real jank on mid-range Android (the founder's audience). One canvas
  draws all dots per frame on the GPU-backed 2D context with **zero layout/DOM cost** and trivially honours
  reduced-motion by not starting the RAF loop. It is the smoothest, most GPU-friendly, no-jank option.
- **Fallback = a pure-CSS radial dot grid** (`gl-field--css`, §5.4) used when: `prefers-reduced-motion`,
  no canvas/2D context, or `lowPower` prop. It is a static-to-gentle CSS field (a `radial-gradient`
  dot-pattern mask + one slow opacity breathe), visually consistent but motion-minimal. So the component
  **degrades gracefully and is always token-pure.**
- **No new dependency, no WebGL** (overkill + battery cost). Plain 2D canvas + `requestAnimationFrame`.

### 3.2 Field geometry (concrete params)
The field is a **circular point cloud** centred in the field zone. Build it ONCE on mount (deterministic,
seedable) into a `dots[]` array; the RAF loop only animates per-frame opacity/scale/offset — positions are
fixed (cheap, no re-layout, no per-frame allocation).

| Param | Value | Notes |
|---|---|---|
| `FIELD_R` | `min(zoneW, zoneH) * 0.46` | field radius in px (responsive; recompute on resize) |
| `RINGS` | `7` | concentric rings from centre to edge |
| `dotsPerRing` | `[1, 8, 14, 20, 26, 30, 34]` (≈133 dots) | denser outward but **brightness falls**, so centre reads densest visually |
| jitter | each dot angle/radius jittered ±`6%` | breaks the perfect-ring look → organic "neural", not a target |
| `DOT_R_CENTER` | `2.6px` (CSS px; multiply by DPR) | centre dots largest |
| `DOT_R_EDGE` | `0.8px` | edge dots smallest |
| dot radius ramp | `r = lerp(DOT_R_CENTER, DOT_R_EDGE, ease(t))`, `t = ringIndex/(RINGS-1)`, `ease = t*t` (quadratic) | size shrinks faster near the edge |
| `OPACITY_CENTER` | `0.92` | centre brightest |
| `OPACITY_EDGE` | `0.06` | edge nearly faded out |
| opacity ramp | `o = lerp(OPACITY_CENTER, OPACITY_EDGE, smoothstep(t))` | smooth bright→faint radial falloff |
| max dot count cap | hard cap **220** | guards huge desktop fields; downscale `dotsPerRing` proportionally if `FIELD_R` is large; clamp to ≥80 on small mobile |

All sizes are **CSS px**; on draw, multiply geometry by `devicePixelRatio` (canvas backing store scaled,
context `scale(dpr,dpr)`) so dots are crisp on retina without blurring.

### 3.3 Dot colour (token-driven, zero raw hex)
- Define `--gl-dot: var(--shade-10)` (near-white `#fdfdfd`) and `--gl-dot-soft: var(--shade-07)` in the
  `.gl-card` scope in `globals.css`. The canvas reads them via
  `getComputedStyle(card).getPropertyValue('--gl-dot')` once on mount (re-read on theme change) →
  so the field is **driven by tokens, never a literal colour in JS**.
- Per-dot colour = the resolved `--gl-dot` at the dot's computed opacity (centre) blending toward
  `--gl-dot-soft` at the edge — a subtle grey→white gradient across the radius (`mixToward(soft, t)`),
  giving the "white core, grey halo" premium look. Brand-blue is **NOT** used in the dots (keeps it calm
  and non-colourful per spec); `primary-01` appears only in the Thinking dot + the progress hairline.

### 3.4 The four motions (what makes it "alive") — all subtle, layered, GPU-cheap
Each runs continuously while `state="loading"`; each dot carries its own random **phase** so the field never
pulses in unison (the key to "energy field", not "blinking grid"). Per-frame, for each dot:

1. **Breathe (global):** the whole field's base opacity eases `0.85 → 1.0 → 0.85` over `~3.2s`
   (`sin`-driven). Slow, calm — the "breathing" the spec names.
2. **Pulse (per-dot shimmer):** `opacity *= 0.6 + 0.4*sin(time*PULSE_SPEED + dot.phase)`,
   `PULSE_SPEED ≈ 0.9 rad/s`. Staggered phases → a shimmer rippling across the cloud.
3. **Drift (per-dot):** each dot orbits its home point on a tiny lissajous:
   `x = home.x + sin(time*0.3 + phaseX) * DRIFT`, `y = home.y + cos(time*0.27 + phaseY) * DRIFT`,
   `DRIFT ≈ 1.4px`. Imperceptible individually, but the cloud "swims" gently.
4. **Twinkle (sparse highlight):** ~`6%` of dots, chosen randomly, briefly brighten to ~`1.0` and grow
   `+30%` radius on a slow random timer (every `2.5–5s` per twinkler) — the occasional bright spark that
   reads as "thinking". Keeps the eye engaged without being busy.

**Wave/ripple option (subtle, on by default):** a soft radial **energy pulse** emanates from centre every
`~4s` — a band of `+0.15` opacity that expands outward over `~1.6s` then fades. Implemented as a distance-
based term `ripple(dist, time)` added to each dot's opacity. This is the "neural energy" signature; can be
disabled via `intensity="calm"`.

**Performance contract:** one `clearRect` + one loop over `dots[]` doing `arc`+`fill` per frame (or a single
`Path2D` per opacity-bucket to batch fills — see §5.3). Target **60fps**; the loop **pauses** when the tab is
hidden (`document.visibilitychange`) or the component is off-screen (`IntersectionObserver`), and **stops
entirely** on `ready`/`failed`/unmount. No per-frame allocations (reuse the `dots[]` objects).

---

## 4. STATUS LINES + REAL-PROGRESS BINDING

### 4.1 The cycling lines (exact copy, in order — from `PHASE2_SPEC §1`)
```
1. Understanding campaign
2. Designing visual direction
3. Composing layout
4. Rendering creative
5. Finalizing output
```
- Rendered one at a time under the field, **crossfading** (200ms out / 200ms in, `gl-status-swap`
  keyframe: opacity + 4px translateY). Each line holds ~**2.2s** before advancing.
- **Trailing animated ellipsis** ("…") via a tiny `gl-ellipsis` keyframe (3 dots fading in sequence) so the
  line feels live even between phase changes.
- The lines are passed as a `statusLines` prop (default = the 5 above) so the same component reads
  "Creating banner" copy for banners, or a custom set for brochure/video-thumbnail reuse.

### 4.2 Binding to REAL job phase (never fake) — the key honesty rule
The component accepts a `phase` prop (optional) sourced from the AI Asset Service job stream
(`asset-service-backend.md §5`). The backend `ai_generation_jobs.phase` enum maps **1:1** to the status
lines, so when real data is present the line reflects the actual engine stage:

| backend `phase` | shown status line |
|---|---|
| `queued` / `reading_campaign` | Understanding campaign |
| `building_prompts` | Designing visual direction |
| (prompt→render handoff) | Composing layout |
| `rendering` | Rendering creative |
| `scoring` / `storing` | Finalizing output |
| `done` | → triggers `ready`/`completed` (§6) |

- **If `phase` IS provided** → the status line is **driven by it** (real), not the timer. The timer-cycle is
  only the *fallback* used until the first phase arrives, and to gently advance *within* a long `rendering`
  phase (so it never looks frozen) — but it never advances **past** the real phase.
- **Progress hairline (`.meter`):** shown **only** when `progress.total` and `progress.done` are known from
  SSE (`GET /jobs/{id}/stream`); `meter-fill` width = `done/total`. **If total is unknown, the hairline is
  hidden entirely** — we show the animated field + status text, never a fabricated percentage (PHASE2_SPEC §1
  "if not → DO NOT fake a percentage"). A subtle "3 of 5 ready" count (`text-caption text-t-tertiary`) may
  accompany it when `total` is real.
- **Stream wiring (reference, for the build agent):** the page owns the `EventSource`
  (`GET /api/assets/jobs/{id}/stream`); on each event it updates local `phase` + `progress` state and passes
  them as props. The loader is **purely presentational** — it does NOT open the socket itself (testable,
  reusable, no side-effects). A thin `useGenerationJob(jobId)` hook (page-level, not part of this component)
  is the recommended owner; documented in §9.

---

## 5. CANVAS IMPLEMENTATION (the buildable core)

### 5.1 Structure
```
components/GenerationLoader/
  index.tsx        — the component (chrome + states + canvas mount + reduced-motion/visibility logic)
  field.ts         — buildField(opts) → dots[]  +  drawFrame(ctx, dots, t, cfg)  (pure, unit-testable)
```
`field.ts` holds **all** geometry/animation math (pure functions, no React, no DOM beyond the passed ctx) so
it can be unit-tested headless and so `index.tsx` stays a thin lifecycle shell.

### 5.2 Lifecycle (in `index.tsx`)
1. On mount, if motion allowed + canvas supported: read `--gl-dot`/`--gl-dot-soft` from the card,
   size the canvas to the field zone × DPR, call `buildField()` once, start the RAF loop.
2. RAF loop: `t = (now - start)/1000`; `clearRect`; `drawFrame(ctx, dots, t, cfg)`; `raf = requestAnimationFrame(loop)`.
3. **Resize** (`ResizeObserver` on the field zone): debounced re-size + `buildField()` rebuild (positions
   depend on `FIELD_R`).
4. **Pause** on `document.hidden` or `IntersectionObserver` not-intersecting; **resume** on return.
5. **Theme change** (observe `data-theme` on `<html>` via `MutationObserver`, or a passed `theme` prop):
   re-read the `--gl-dot*` tokens (colour only; geometry unchanged).
6. On `state` ≠ `loading` (ready/failed) or unmount: `cancelAnimationFrame`, disconnect observers.

### 5.3 Draw cost optimisation (so mid-range Android stays 60fps)
- Batch fills by **opacity bucket** (round each dot's alpha to ~12 buckets); one `ctx.globalAlpha` set +
  one `Path2D` of all dots in that bucket per frame → ~12 `fill()` calls instead of ~133. Big win on slow GPUs.
- Or, simplest correct version: a single loop with `ctx.beginPath(); ctx.arc(); ctx.fill()` per dot — fine
  at ≤150 dots on most devices; ship this first, switch to bucketing only if a device profiles slow.
- Never read layout in the loop; never allocate in the loop.

### 5.4 CSS fallback field (`gl-field--css`) — for reduced-motion / no-canvas / lowPower
A token-only static-to-gentle field, no canvas:
```css
/* in @layer components, globals.css */
.gl-field--css {
  /* concentric soft dots via stacked radial-gradients on a masked circle */
  background:
    radial-gradient(circle, var(--gl-dot) 0 1px, transparent 1.5px) 0 0 / 14px 14px;
  -webkit-mask-image: radial-gradient(circle at 50% 50%,
      black 0%, black 38%, transparent 72%);
          mask-image: radial-gradient(circle at 50% 50%,
      black 0%, black 38%, transparent 72%);
  opacity: 0.55;
  animation: gl-breathe 3.6s ease-in-out infinite;
}
@keyframes gl-breathe { 0%,100%{opacity:.45} 50%{opacity:.7} }
@media (prefers-reduced-motion: reduce) { .gl-field--css { animation: none; opacity:.5; } }
```
The dot-grid + the centre-bright radial mask reproduce the "dense bright centre, faded edge" look with one
element and one cheap keyframe. Reduced-motion → no animation, a calm static field (the required low-motion
fallback). This is the same visual language as the canvas, so swapping between them is seamless.

---

## 6. STATES (the full lifecycle)

A single `state` prop drives the component (controlled by the page). Five states:

| `state` | Field | Chrome | Transition |
|---|---|---|---|
| **`loading`** | live dot-matrix (canvas) animating, status lines cycling | Thinking + title + (optional progress) + (optional Cancel) | default |
| **`completed`** | dots **collapse inward** toward centre + fade (300–400ms `gl-collapse`), card cross-fades out | title swaps to a brief "Done" tick (optional), then unmount / reveal result | **fade-to-result** (§6.1) |
| **`failed`** | field freezes + desaturates to a calm static state (stops RAF), a small muted glyph replaces centre | `text-t-secondary` line "Couldn't create that one." + **Retry** (`Button isBlack`) + optional **Back** (`Button isStroke`) | no error dump; one calm line |
| **`retry`** (transient) | field restarts (rebuild + RAF) | resets status to line 1 | identical to `loading` (it's `loading` re-entered) — exposed as a convenience the page sets after the Retry click re-submits the job |
| **`cancelled`** (optional) | field collapses (like completed but no result) | brief "Cancelled" line, then unmount | only if Cancel used (§6.2) |

### 6.1 `completed` → fade-to-result (the signature exit)
- On `state="completed"` (page sets it when the job/variant bytes are ready): play `gl-collapse` (dots
  scale toward centre + global opacity → 0 over ~360ms) **simultaneously** with a `gl-card-out`
  opacity/scale(0.98) on the card; then call the `onCompleted` callback / unmount so the **real image**
  (or the grid of `CreativeSkeleton`→image cards) cross-fades in underneath. The handoff is a clean
  "the engine resolved into the picture" — exactly the ChatGPT-image-gen reveal.
- Reduced-motion: skip the collapse, do a plain 200ms opacity cross-fade.

### 6.2 `cancel` (optional)
- A `Button isStroke` "Cancel" appears only if `onCancel` is provided. Click → `onCancel()` (page calls
  `POST /jobs/{id}/cancel`, which releases the wallet hold per backend §6) → page sets `state="cancelled"`
  → field collapses → unmount. The loader itself performs **no** network I/O.

### 6.3 `failed` → retry
- `Button isBlack` "Try again" → `onRetry()` (page re-submits `POST /generate`) → page sets `state="loading"`
  (or `"retry"`). The field rebuilds and the cycle restarts. The failure line stays calm and human
  ("Couldn't create that one. Try again." / a passed `errorMessage`), **never** a stack/JSON (founder §41).

---

## 7. RESPONSIVE + SIZING

- **Modes (`mode` prop):**
  - `"inline"` (default) — fills its container's preview/generation card; `min-h-[22rem] max-md:min-h-[18rem]`,
    field zone = the card body minus the header/status rows.
  - `"fullscreen"` — fixed black scrim (`fixed inset-0 z-50 bg-b-dark2/95 backdrop-blur-sm`) centring the
    charcoal card (`w-[min(34rem,92vw)]`); used for a single-asset "generate & wait" modal. Reuses the
    `Modal` scrim pattern but is its own light surface (the dot field is the point).
- **Field zone size** drives `FIELD_R`; on mount + `ResizeObserver` the canvas matches the zone. Mobile:
  smaller card padding (`p-6`), `dotsPerRing` auto-downscaled (cap respects `clamp(80, …, 220)`), title
  `text-h6`. Desktop: `p-8`, up to 220 dots, title `text-h5`.
- **DPR-aware** canvas sizing (§3.2) so it's crisp on retina/high-density phones.
- Layout never reflows during animation (canvas is a fixed-size element; only its pixels change).

---

## 8. COMPONENT API (props — so a build agent implements it pixel-accurate)

```ts
type GenerationLoaderState =
  | "loading" | "completed" | "failed" | "retry" | "cancelled";

type GenerationLoaderPhase =
  | "queued" | "reading_campaign" | "building_prompts"
  | "rendering" | "scoring" | "storing" | "done";   // backend ai_generation_jobs.phase

type GenerationLoaderProps = {
  /** Overall lifecycle state (controlled by the page). Default "loading". */
  state?: GenerationLoaderState;

  /** Bold title inside the card. Default "Creating image". e.g. "Creating banner". */
  title?: string;

  /** Muted label above the title. Default "Thinking". */
  label?: string;

  /** Real backend phase from the job stream. If provided, drives the status line
   *  (real, not the timer). If omitted, the 5 lines cycle on a timer. */
  phase?: GenerationLoaderPhase;

  /** Override the cycling lines (reuse for brochure/video-thumbnail copy). */
  statusLines?: string[];   // default = the 5 PHASE2_SPEC lines

  /** Real progress from SSE. If total is known → show the hairline + "k of N".
   *  If undefined → NO percentage is shown (never faked). */
  progress?: { total: number; done: number; streamingVariant?: string };

  /** Visual intensity of the field motion. Default "energy". */
  intensity?: "calm" | "energy";      // "calm" disables the ripple + twinkle, slower pulse

  /** Force the low-motion CSS field (battery / explicit). prefers-reduced-motion
   *  forces this regardless. Default false. */
  lowPower?: boolean;

  /** Layout. "inline" fills the container; "fullscreen" is a scrim modal. Default "inline". */
  mode?: "inline" | "fullscreen";

  /** Calm human error copy for the failed state. Default "Couldn't create that one." */
  errorMessage?: string;

  /** Callbacks — the component performs NO network I/O itself. */
  onRetry?: () => void;     // shown as "Try again" in failed state
  onCancel?: () => void;    // shown as "Cancel" in loading state (optional)
  onCompleted?: () => void; // fired after the collapse-exit finishes (page reveals the result)

  className?: string;
};
```

**Defaults chosen so `<GenerationLoader />` with no props already looks right** (loading, "Creating image",
"Thinking", energy, inline, timer-cycled lines). The page upgrades it to real-progress by feeding `phase` +
`progress` from the job stream.

---

## 9. INTEGRATION (how the page binds it to the AI Asset job stream)

> The component is presentational; the **page** owns the data. Recommended thin hook (page-level, NOT part
> of the component — documented here so the build agent wires it once):

```
useGenerationJob(jobId):
  - opens EventSource('/api/assets/jobs/{jobId}/stream')   (asset-service-backend.md §8)
  - on message: parse {state, phase, progress, variant?}   (ai_generation_jobs fields)
  - returns { state, phase, progress }  → mapped to GenerationLoader props
  - on 'done'/'succeeded' → set state="completed"; on 'failed' → "failed"
  - falls back to GET /jobs/{id} polling if EventSource unsupported (backend offers both)
```

- **Happy path:** click Generate → `POST /generate` returns `{job_id, state:"queued"}` → page renders
  `<GenerationLoader state="loading" title="Creating banner" phase={…} progress={…} onCancel={cancel} />`
  → SSE drives phase/progress → on `done`, page sets `state="completed"` → loader collapses → variant grid
  (each card a `CreativeSkeleton` then the image) cross-fades in.
- **Over-budget / not-enabled:** `POST /generate` returns `over_budget`/`503` → page does **not** mount the
  loader; shows the inline token banner instead (loader is only for an *accepted* job).
- **No SSE / dormant backend:** loader still runs on its **own timer** (phase omitted, no progress) — it is
  fully functional with zero backend, so it demos offline and never blocks on creds.

---

## 10. ACCESSIBILITY + REDUCED MOTION

- Card root: `role="status"` `aria-live="polite"` `aria-busy="true"` (so the current status line is
  announced); `aria-label` = `${label}: ${title}` (e.g. "Thinking: Creating banner"). On `completed` set
  `aria-busy="false"`; on `failed` announce the error line via the live region.
- **`prefers-reduced-motion: reduce`** (detected via `matchMedia`, and the existing globals.css media block):
  the canvas RAF loop does **not** start → render the `gl-field--css` calm field (a single slow breathe, or
  fully static), status lines **cross-fade gently but do not animate the ellipsis/ripple/twinkle**, the
  Thinking dot is static, and the completed exit is a plain opacity fade (no collapse). This is the required
  "calm low-motion" fallback — the spec is honoured, the meaning is preserved, the motion is gone.
- Field decoration is `aria-hidden` (it carries no info the live region doesn't already announce).
- Focus: in `failed`, focus moves to the "Try again" button; in `fullscreen` mode the scrim traps focus and
  `Esc` triggers `onCancel` (if provided) — reuse the `Modal` focus-trap behaviour.

---

## 11. WHAT THIS COMPONENT MUST NOT DO (guardrails)

- **No raw hex.** Every colour is a token (`--gl-dot`/`--gl-dot-soft` are token aliases to `shade-10`/
  `shade-07`; chrome uses `b-dark*`/`t-*`/`primary-01`). The canvas reads tokens via `getComputedStyle`.
- **No fake percentage** — the hairline appears only with a real `progress.total`.
- **No network I/O** inside the component — `onRetry/onCancel/onCompleted` callbacks only; the page owns the
  job stream and the wallet/cancel calls.
- **No new npm dependency**, no WebGL, no heavy particle lib — plain 2D canvas + RAF + CSS fallback.
- **Changes nothing unrelated** — additive: one new component dir + a small `gl-*` block appended to the
  existing `@layer components` in `globals.css`. No edits to any other component, page, or token.
- **One brand accent** — `primary-01` only on the Thinking dot + progress hairline; the dot field itself
  stays grey→white (calm, non-colourful, per spec).

---

## 12. BUILD ORDER (small verifiable units, for the later frontend wave)

1. `gl-*` keyframes + `--gl-dot*` tokens + `.gl-card`/`.gl-field--css` in `globals.css` (no JS) → visually
   verify the static charcoal card + CSS fallback field in light/dark + reduced-motion.
2. `field.ts` pure module (`buildField`, `drawFrame`) → headless unit test: dot count within cap, radial
   opacity/size ramp monotonic, deterministic with a seed.
3. `index.tsx` canvas mount + RAF + DPR + ResizeObserver/visibility pause → the live field at 60fps; profile
   on a throttled mobile (DevTools 4× CPU) → no jank.
4. Status-line cycle (timer) + Thinking dot + title from props → the default `<GenerationLoader />` looks
   right with zero props.
5. `phase`/`progress` binding (real-data path) + the optional hairline + "k of N" → drive it from a mocked
   stream; confirm no fake % when total absent.
6. States: `completed` collapse-exit + `failed`/retry + optional `cancel`/`fullscreen` scrim → each verified.
7. Reduced-motion path forces `gl-field--css` + no collapse → verified via `matchMedia` override.
8. Wire the page `useGenerationJob` hook against `GET /api/assets/jobs/{id}/stream` (the real backend) in the
   Creative Studio S4 surface; dissolve into `CreativeSkeleton` variant cards on `completed`.

Acceptance: smooth 60fps dot field on mid-range mobile, crisp on retina, real-phase status when streamed,
no fabricated %, calm reduced-motion fallback, token-pure (zero raw hex), and a clean collapse-to-result exit
that feels like ChatGPT / Google Flow image generation.

---

## 13. SOURCES / GROUND TRUTH
- Founder ask: `CREATIVE_STUDIO_PHASE2_SPEC.md §1` (the dot-matrix loading UI, status lines, states, quality bar).
- Sibling per-card loader (compose, don't duplicate): `design/creative-studio-ui.md §9` (`CreativeSkeleton`).
- Backend job/stream contract (phase enum, SSE `GET /jobs/{id}/stream`, `progress{total,done,streaming_variant}`,
  states, wallet-hold cancel): `design/asset-service-backend.md §5, §6, §8` + `memory/brain/creative-studio.md`
  (A3: 18 frozen routes incl. `/jobs/{id}/stream`).
- Token system + existing utilities reused (`.surface`/`.card`/`.skeleton`/`.meter`/reduced-motion block/
  Signal layer): `famit-panel/app/globals.css`. `Button`/`Spinner` APIs: `famit-panel/components/{Button,Spinner}`.
- UI rules (no subtitle, one title, zero raw hex, Inter Display, real loading state): `design/ui-design-principles.md`,
  `design/creative-studio-ui.md §16`.
```
