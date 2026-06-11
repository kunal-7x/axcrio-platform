/**
 * GenerationLoader — dot-matrix neural-energy field (pure math, no React/DOM).
 *
 * `buildField()` deterministically lays out a circular point cloud ONCE (cheap,
 * no per-frame allocation). `drawFrame()` animates per-frame opacity/scale/offset
 * only — positions are fixed. All geometry/animation lives here so `index.tsx`
 * stays a thin lifecycle shell and this module is headless-unit-testable.
 *
 * Visual model (design/cs-loading-component.md §3):
 *   - 7 concentric rings, ~133 dots (clamped 80..220).
 *   - centre bright (0.92) + large (2.6px) -> edge faded (0.06) + small (0.8px).
 *   - four layered motions: breathe (global), pulse (per-dot), drift (per-dot),
 *     twinkle (sparse), plus an optional radial energy ripple.
 *   - grey->white colour across the radius (white core, grey halo).
 *
 * Token-pure: colours are passed IN (resolved from CSS vars by the component),
 * never literals here.
 */

export type FieldDot = {
    /** home position in CSS px relative to field centre */
    hx: number;
    hy: number;
    /** distance from centre normalised 0..1 (0 = centre, 1 = edge) */
    t: number;
    /** base radius in CSS px */
    r: number;
    /** base opacity 0..1 */
    o: number;
    /** per-dot random phases so the cloud never pulses in unison */
    phase: number;
    phaseX: number;
    phaseY: number;
    /** twinkle timing (seconds): next time this dot sparks + its period */
    twinkleAt: number;
    twinklePeriod: number;
    isTwinkler: boolean;
};

export type FieldConfig = {
    /** field radius in CSS px (= min(zoneW, zoneH) * 0.46) */
    fieldR: number;
    /** white core colour as "r,g,b" channels (resolved from --gl-dot) */
    coreRGB: [number, number, number];
    /** grey halo colour as "r,g,b" channels (resolved from --gl-dot-soft) */
    softRGB: [number, number, number];
    /** "energy" (ripple + twinkle on) | "calm" (no ripple/twinkle, slower pulse) */
    intensity: "calm" | "energy";
};

export type DrawConfig = FieldConfig & {
    /** centre of the field in canvas CSS px (zoneW/2, zoneH/2) */
    cx: number;
    cy: number;
};

// Typed as `number` (not the literal `7`) so the defensive `RINGS === 1` guards
// below type-check — a 1-ring field is a valid degenerate config, not dead code.
const RINGS: number = 7;
const DOTS_PER_RING = [1, 8, 14, 20, 26, 30, 34]; // ~133 dots
const JITTER = 0.06; // ±6% angle/radius jitter -> organic, not a target
const DOT_R_CENTER = 2.6;
const DOT_R_EDGE = 0.8;
const OPACITY_CENTER = 0.92;
const OPACITY_EDGE = 0.06;
const MAX_DOTS = 220;
const MIN_DOTS = 80;

const DRIFT = 1.4; // px per-dot orbit amplitude
const PULSE_SPEED = 0.9; // rad/s

// ---- math helpers (pure) ----
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp = (v: number, lo: number, hi: number) =>
    v < lo ? lo : v > hi ? hi : v;
const smoothstep = (t: number) => t * t * (3 - 2 * t);

/**
 * Deterministic mulberry32 PRNG so the field is seedable / reproducible
 * (the spec requires "deterministic with a seed" for the headless test).
 */
function rng(seed: number): () => number {
    let a = seed >>> 0;
    return () => {
        a |= 0;
        a = (a + 0x6d2b79f5) | 0;
        let r = Math.imul(a ^ (a >>> 15), 1 | a);
        r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
        return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
    };
}

/**
 * Build the dot cloud once. Pure + deterministic for a given (fieldR, seed).
 * Downscales the per-ring counts proportionally when the field is small so the
 * total stays within [MIN_DOTS, MAX_DOTS]; on a huge desktop field it never
 * exceeds the 220 cap.
 */
export function buildField(fieldR: number, seed = 1, intensity: "calm" | "energy" = "energy"): FieldDot[] {
    const rand = rng(seed);

    // Base total from the canonical per-ring table.
    const baseTotal = DOTS_PER_RING.reduce((s, n) => s + n, 0);
    // Scale dot density gently with field size, then clamp to the cap band.
    const targetTotal = clamp(
        Math.round(baseTotal * clamp(fieldR / 150, 0.6, 1.65)),
        MIN_DOTS,
        MAX_DOTS
    );
    const scale = targetTotal / baseTotal;

    const dots: FieldDot[] = [];

    for (let ring = 0; ring < RINGS; ring++) {
        const t = RINGS === 1 ? 0 : ring / (RINGS - 1); // 0 centre .. 1 edge
        const ringR = fieldR * (RINGS === 1 ? 0 : ring / (RINGS - 1));

        // size shrinks faster near the edge (quadratic ease)
        const r = lerp(DOT_R_CENTER, DOT_R_EDGE, t * t);
        // smooth bright -> faint radial falloff
        const o = lerp(OPACITY_CENTER, OPACITY_EDGE, smoothstep(t));

        const count =
            ring === 0
                ? 1
                : Math.max(1, Math.round(DOTS_PER_RING[ring] * scale));

        for (let i = 0; i < count; i++) {
            if (dots.length >= MAX_DOTS) break;

            const baseAngle = ring === 0 ? 0 : (i / count) * Math.PI * 2;
            const angle = baseAngle + (rand() - 0.5) * 2 * JITTER * Math.PI;
            const jitteredR = ringR * (1 + (rand() - 0.5) * 2 * JITTER);

            const isTwinkler = intensity === "energy" && rand() < 0.06;

            dots.push({
                hx: Math.cos(angle) * jitteredR,
                hy: Math.sin(angle) * jitteredR,
                t,
                r,
                o,
                phase: rand() * Math.PI * 2,
                phaseX: rand() * Math.PI * 2,
                phaseY: rand() * Math.PI * 2,
                twinklePeriod: lerp(2.5, 5, rand()),
                twinkleAt: lerp(0, 5, rand()),
                isTwinkler,
            });
        }
    }

    return dots;
}

/**
 * Per-frame opacity for a single dot at time `time` (seconds). Pure — exposed
 * for unit testing the animation envelope without a canvas.
 */
export function dotAlpha(dot: FieldDot, time: number, cfg: DrawConfig): number {
    // 1. Breathe (global): 0.85 -> 1.0 -> 0.85 over ~3.2s
    const breathe = 0.925 + 0.075 * Math.sin((time / 3.2) * Math.PI * 2);

    // 2. Pulse (per-dot shimmer)
    const pulseSpeed = cfg.intensity === "calm" ? PULSE_SPEED * 0.6 : PULSE_SPEED;
    const pulse = 0.6 + 0.4 * Math.sin(time * pulseSpeed + dot.phase);

    let alpha = dot.o * breathe * pulse;

    // 4 (+ ripple) only in "energy" mode
    if (cfg.intensity === "energy") {
        // Twinkle: sparse highlight, brief brighten on a slow per-dot timer.
        if (dot.isTwinkler) {
            const local = time % dot.twinklePeriod;
            const sparkWindow = 0.5;
            if (local < sparkWindow) {
                const k = 1 - local / sparkWindow; // 1 -> 0 over the window
                alpha = Math.min(1, alpha + 0.4 * k);
            }
        }
        // Radial energy ripple: a band of +0.15 opacity expanding from centre
        // every ~4s over ~1.6s.
        const dist = Math.hypot(dot.hx, dot.hy);
        const period = 4;
        const local = time % period;
        const rippleDur = 1.6;
        if (local < rippleDur) {
            const front = (local / rippleDur) * cfg.fieldR; // expanding radius
            const band = cfg.fieldR * 0.18;
            const d = Math.abs(dist - front);
            if (d < band) {
                const k = (1 - d / band) * (1 - local / rippleDur);
                alpha += 0.15 * k;
            }
        }
    }

    return clamp(alpha, 0, 1);
}

/**
 * Per-frame radius for a dot (base radius + twinkle growth).
 */
export function dotRadius(dot: FieldDot, time: number, cfg: DrawConfig): number {
    if (cfg.intensity === "energy" && dot.isTwinkler) {
        const local = time % dot.twinklePeriod;
        const sparkWindow = 0.5;
        if (local < sparkWindow) {
            const k = 1 - local / sparkWindow;
            return dot.r * (1 + 0.3 * k); // +30% radius on a spark
        }
    }
    return dot.r;
}

/**
 * Draw one animated frame. `collapse` in [0,1] drives the completed-exit
 * (dots scale toward centre + global fade): 0 = normal, 1 = fully collapsed.
 * `frozen` desaturates/holds for the failed state (no motion term).
 */
export function drawFrame(
    ctx: CanvasRenderingContext2D,
    dots: FieldDot[],
    time: number,
    cfg: DrawConfig,
    collapse = 0,
    frozen = false
): void {
    const { cx, cy, coreRGB, softRGB } = cfg;
    const inv = 1 - collapse; // 1 -> 0 as we collapse
    const globalFade = inv; // whole field fades out on collapse

    for (let i = 0; i < dots.length; i++) {
        const dot = dots[i];

        // drift orbit (paused when frozen)
        const dx = frozen ? 0 : Math.sin(time * 0.3 + dot.phaseX) * DRIFT;
        const dy = frozen ? 0 : Math.cos(time * 0.27 + dot.phaseY) * DRIFT;

        // collapse: pull each dot toward centre
        const px = cx + (dot.hx + dx) * inv;
        const py = cy + (dot.hy + dy) * inv;

        let alpha = frozen
            ? dot.o * 0.5 // calm static state for "failed"
            : dotAlpha(dot, time, cfg);
        alpha *= globalFade;
        if (alpha <= 0.002) continue;

        const r = dotRadius(dot, time, cfg) * (frozen ? 1 : 1);

        // grey -> white across the radius: white core (t=0) -> soft grey (t=1)
        const cr = Math.round(lerp(coreRGB[0], softRGB[0], dot.t));
        const cg = Math.round(lerp(coreRGB[1], softRGB[1], dot.t));
        const cb = Math.round(lerp(coreRGB[2], softRGB[2], dot.t));

        ctx.globalAlpha = alpha;
        ctx.fillStyle = `rgb(${cr},${cg},${cb})`;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalAlpha = 1;
}

/** Parse a CSS colour value (#rrggbb / #rgb / rgb(...)) into [r,g,b] channels. */
export function parseRGB(value: string, fallback: [number, number, number]): [number, number, number] {
    const v = value.trim();
    if (!v) return fallback;
    if (v.startsWith("#")) {
        let hex = v.slice(1);
        if (hex.length === 3) {
            hex = hex
                .split("")
                .map((c) => c + c)
                .join("");
        }
        if (hex.length >= 6) {
            const n = parseInt(hex.slice(0, 6), 16);
            return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
        }
        return fallback;
    }
    const m = v.match(/rgba?\(([^)]+)\)/i);
    if (m) {
        const parts = m[1].split(",").map((p) => parseFloat(p));
        if (parts.length >= 3) {
            return [
                clamp(parts[0], 0, 255),
                clamp(parts[1], 0, 255),
                clamp(parts[2], 0, 255),
            ];
        }
    }
    return fallback;
}
