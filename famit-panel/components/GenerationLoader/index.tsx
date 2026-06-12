"use client";

/**
 * GenerationLoader — the premium AI-generation loading hero.
 *
 * A deep charcoal card on black with a breathing dot-matrix neural-energy field
 * (canvas, §3/§5 of design/cs-loading-component.md). Shown the instant a user
 * clicks Generate, holds while the AI Asset Service renders, then collapses the
 * dots inward and cross-fades into the result.
 *
 * PRESENTATIONAL ONLY — performs ZERO network I/O. The page owns the job stream
 * (see `useGenerationJob` below) and feeds `state` / `phase` / `progress` in as
 * props; the loader emits `onRetry` / `onCancel` / `onCompleted` callbacks only.
 *
 * Token-pure: every colour is a token (`--gl-dot` / `--gl-dot-soft` aliases +
 * `b-dark*` / `t-*` / `primary-01`). No raw hex. No new npm dep. Honours
 * prefers-reduced-motion (CSS-fallback field, no collapse), pauses RAF when the
 * tab is hidden or the component is off-screen, and never fabricates a %.
 */

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import {
    buildField,
    drawFrame,
    parseRGB,
    type FieldDot,
    type DrawConfig,
} from "./field";
import { createAurora, type AuroraHandle, type RGB01 } from "./aurora";

export type GenerationLoaderState =
    | "loading"
    | "completed"
    | "failed"
    | "retry"
    | "cancelled";

export type GenerationLoaderPhase =
    | "queued"
    | "reading_campaign"
    | "building_prompts"
    | "rendering"
    | "scoring"
    | "storing"
    | "done";

export type GenerationLoaderProps = {
    /** Overall lifecycle state (controlled by the page). Default "loading". */
    state?: GenerationLoaderState;
    /** Bold title inside the card. Default "Creating image". */
    title?: string;
    /** Muted label above the title. Default "Thinking". */
    label?: string;
    /** Real backend phase from the job stream — drives the status line (real).
     *  If omitted, the lines cycle on a timer. */
    phase?: GenerationLoaderPhase;
    /** Override the cycling lines (reuse for brochure/video-thumbnail copy). */
    statusLines?: string[];
    /** Real progress from SSE. total known -> hairline + "k of N"; undefined ->
     *  NO percentage shown (never faked). */
    progress?: { total: number; done: number; streamingVariant?: string };
    /** Field motion intensity. "calm" disables ripple + twinkle. Default "energy". */
    intensity?: "calm" | "energy";
    /** Force the low-motion CSS field. prefers-reduced-motion forces this too. */
    lowPower?: boolean;
    /** "inline" fills the container; "fullscreen" is a scrim modal. Default "inline". */
    mode?: "inline" | "fullscreen";
    /** Calm human error copy for the failed state. */
    errorMessage?: string;
    onRetry?: () => void;
    onCancel?: () => void;
    /** Fired after the collapse-exit finishes (page reveals the result). */
    onCompleted?: () => void;
    className?: string;
};

/** The 5 default status lines (PHASE2_SPEC §1), in order. */
const DEFAULT_LINES = [
    "Understanding campaign",
    "Designing visual direction",
    "Composing layout",
    "Rendering creative",
    "Finalizing output",
];

/** backend phase enum -> status-line index (real-data path, §4.2). */
const PHASE_TO_LINE: Record<GenerationLoaderPhase, number> = {
    queued: 0,
    reading_campaign: 0,
    building_prompts: 1,
    rendering: 3,
    scoring: 4,
    storing: 4,
    done: 4,
};

/** backend phase enum -> aurora intensity 0..1 (the 4-stage visual escalation).
 *  queued/reading = calm low energy; building = warming; rendering/scoring = peak;
 *  storing/done = cooling toward the collapse. */
const PHASE_TO_INTENSITY: Record<GenerationLoaderPhase, number> = {
    queued: 0.22,
    reading_campaign: 0.3,
    building_prompts: 0.55,
    rendering: 1.0,
    scoring: 0.85,
    storing: 0.5,
    done: 0.4,
};

const COLLAPSE_MS = 360;
const REDUCED_FADE_MS = 200;

/** Normalise an [r,g,b] 0..255 triple to 0..1 for shader uniforms. */
const to01 = (c: [number, number, number]): RGB01 => [
    c[0] / 255,
    c[1] / 255,
    c[2] / 255,
];

const GenerationLoader: React.FC<GenerationLoaderProps> = ({
    state = "loading",
    title = "Creating image",
    label = "Thinking",
    phase,
    statusLines = DEFAULT_LINES,
    progress,
    intensity = "energy",
    lowPower = false,
    mode = "inline",
    errorMessage = "Couldn't create that one.",
    onRetry,
    onCancel,
    onCompleted,
    className = "",
}) => {
    const cardRef = useRef<HTMLDivElement>(null);
    const zoneRef = useRef<HTMLDivElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const auroraCanvasRef = useRef<HTMLCanvasElement>(null);

    // RAF/lifecycle state kept in refs so the loop never re-creates.
    const rafRef = useRef<number | null>(null);
    const startRef = useRef<number>(0);
    const dotsRef = useRef<FieldDot[]>([]);
    const cfgRef = useRef<DrawConfig | null>(null);
    const pausedRef = useRef<boolean>(false);
    const collapseStartRef = useRef<number | null>(null);
    const auroraRef = useRef<AuroraHandle | null>(null);
    // Smoothed flow intensity driven by phase/state (eased for fluid escalation).
    const intensityRef = useRef<number>(0.3);
    const targetIntensityRef = useRef<number>(0.3);

    const [reduceMotion, setReduceMotion] = useState(false);
    const [lineIndex, setLineIndex] = useState(0);
    const [swapKey, setSwapKey] = useState(0); // re-triggers the crossfade keyframe

    const useCssField = lowPower || reduceMotion;

    // ---- prefers-reduced-motion ----
    useEffect(() => {
        if (typeof window === "undefined" || !window.matchMedia) return;
        const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
        const apply = () => setReduceMotion(mq.matches);
        apply();
        mq.addEventListener?.("change", apply);
        return () => mq.removeEventListener?.("change", apply);
    }, []);

    // ---- dispose the WebGL aurora on unmount (free GPU context) ----
    useEffect(() => {
        return () => {
            auroraRef.current?.dispose();
            auroraRef.current = null;
        };
    }, []);

    // When we switch to the CSS field (reduced-motion/lowPower toggled on at
    // runtime), tear the aurora down so we don't keep a GPU context alive.
    useEffect(() => {
        if (useCssField && auroraRef.current) {
            auroraRef.current.dispose();
            auroraRef.current = null;
        }
    }, [useCssField]);

    // ---- drive the aurora intensity target from phase/state (4-stage escalation) ----
    useEffect(() => {
        if (state === "failed") {
            targetIntensityRef.current = 0; // freeze + desaturate
        } else if (state === "completed" || state === "cancelled") {
            targetIntensityRef.current = 0.15; // cool + settle on the way out
        } else if (phase) {
            targetIntensityRef.current = PHASE_TO_INTENSITY[phase] ?? 0.4;
        } else {
            // No real phase: a gentle mid-energy "thinking" baseline.
            targetIntensityRef.current = intensity === "calm" ? 0.32 : 0.62;
        }
    }, [state, phase, intensity]);

    // ---- status line: real phase drives it; else timer cycles ----
    useEffect(() => {
        if (state !== "loading" && state !== "retry") return;

        // Real-data path: phase pins the line (never advances past real phase).
        if (phase) {
            const idx = PHASE_TO_LINE[phase] ?? 0;
            setLineIndex((prev) => {
                if (prev !== idx) setSwapKey((k) => k + 1);
                return idx;
            });
            // During a long phase we still gently nudge the ellipsis (handled by
            // CSS), but we do NOT advance the line index past `idx`.
            return;
        }

        // Fallback timer cycle (no real phase yet).
        const id = setInterval(() => {
            setLineIndex((prev) => {
                const next = (prev + 1) % statusLines.length;
                setSwapKey((k) => k + 1);
                return next;
            });
        }, 2200);
        return () => clearInterval(id);
    }, [state, phase, statusLines.length]);

    // Reset the cycle when (re)entering a fresh loading/retry.
    useEffect(() => {
        if (state === "retry" || (state === "loading" && !phase)) {
            setLineIndex(0);
            setSwapKey((k) => k + 1);
        }
    }, [state]);

    // ---- read tokens from the card (colour only; never a literal in JS) ----
    const readConfig = (zoneW: number, zoneH: number): DrawConfig => {
        const cs = cardRef.current
            ? getComputedStyle(cardRef.current)
            : null;
        const coreRaw = cs?.getPropertyValue("--gl-dot") ?? "";
        const softRaw = cs?.getPropertyValue("--gl-dot-soft") ?? "";
        const tintRaw = cs?.getPropertyValue("--gl-spark-tint") ?? "";
        return {
            fieldR: Math.min(zoneW, zoneH) * 0.46,
            cx: zoneW / 2,
            cy: zoneH / 2,
            coreRGB: parseRGB(coreRaw, [253, 253, 253]),
            softRGB: parseRGB(softRaw, [123, 123, 123]),
            tintRGB: parseRGB(tintRaw, [42, 133, 255]),
            sampleLuma: auroraRef.current?.sampleLuma,
            flow: intensityRef.current,
            intensity,
        };
    };

    // ---- resolve the 3 aurora palette stops from tokens and push to the shader ----
    const applyAuroraColors = () => {
        const a = auroraRef.current;
        if (!a || !cardRef.current) return;
        const cs = getComputedStyle(cardRef.current);
        a.setColors(
            to01(parseRGB(cs.getPropertyValue("--gl-aur-a"), [10, 13, 23])),
            to01(parseRGB(cs.getPropertyValue("--gl-aur-b"), [42, 133, 255])),
            to01(parseRGB(cs.getPropertyValue("--gl-aur-c"), [209, 229, 255]))
        );
    };

    // ---- canvas sizing + (re)build field ----
    const sizeAndBuild = () => {
        const canvas = canvasRef.current;
        const zone = zoneRef.current;
        if (!canvas || !zone) return;
        const rect = zone.getBoundingClientRect();
        const w = Math.max(1, Math.floor(rect.width));
        const h = Math.max(1, Math.floor(rect.height));
        const dpr = Math.min(window.devicePixelRatio || 1, 2);

        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;

        const ctx = canvas.getContext("2d");
        if (ctx) {
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // crisp on retina
        }

        // Lazily create the WebGL aurora; size it to match the field zone.
        const aCanvas = auroraCanvasRef.current;
        if (aCanvas) {
            if (!auroraRef.current) {
                auroraRef.current = createAurora(aCanvas);
                if (auroraRef.current) applyAuroraColors();
            }
            if (auroraRef.current) {
                aCanvas.style.width = `${w}px`;
                aCanvas.style.height = `${h}px`;
                auroraRef.current.resize(w, h, dpr);
            }
        }

        const cfg = readConfig(w, h);
        cfgRef.current = cfg;
        dotsRef.current = buildField(cfg.fieldR, 1, intensity);
    };

    // ---- the RAF loop (canvas path only) ----
    useEffect(() => {
        if (useCssField) return; // CSS fallback handles motion
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
            // No 2D context -> degrade to CSS field next render.
            setReduceMotion(true);
            return;
        }

        const supportsCanvas = !!ctx;
        if (!supportsCanvas) return;

        sizeAndBuild();
        startRef.current = performance.now();
        collapseStartRef.current = null;

        const loop = (now: number) => {
            const cfg = cfgRef.current;
            const c = canvasRef.current?.getContext("2d");
            if (cfg && c) {
                const t = (now - startRef.current) / 1000;

                // ease the flow intensity toward its phase target (fluid escalation)
                intensityRef.current +=
                    (targetIntensityRef.current - intensityRef.current) * 0.045;
                const flow = intensityRef.current;
                cfg.flow = flow;

                // collapse progress for the completed/cancelled exit
                let collapse = 0;
                const frozen = state === "failed";
                if (
                    (state === "completed" || state === "cancelled") &&
                    collapseStartRef.current !== null
                ) {
                    collapse = Math.min(
                        1,
                        (now - collapseStartRef.current) / COLLAPSE_MS
                    );
                }

                // render the aurora behind the sparks (bloom rises with flow,
                // condenses to centre as we collapse out)
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                const bloom = frozen
                    ? 0.05
                    : Math.min(1, 0.35 + 0.65 * flow + collapse * 0.4);
                auroraRef.current?.render(t, frozen ? 0.02 : flow, bloom, dpr);

                c.clearRect(0, 0, c.canvas.width, c.canvas.height);
                drawFrame(c, dotsRef.current, t, cfg, collapse, frozen);

                if (
                    (state === "completed" || state === "cancelled") &&
                    collapse >= 1
                ) {
                    // exit finished — fire the reveal callback once, stop.
                    if (rafRef.current) cancelAnimationFrame(rafRef.current);
                    rafRef.current = null;
                    onCompleted?.();
                    return;
                }
            }
            if (!pausedRef.current) {
                rafRef.current = requestAnimationFrame(loop);
            }
        };

        // For failed: draw a single frozen frame, no continuous loop needed.
        if (state === "failed") {
            const cfg = cfgRef.current;
            if (cfg) {
                const dpr = Math.min(window.devicePixelRatio || 1, 2);
                auroraRef.current?.render(0, 0.02, 0.05, dpr); // dim, desaturated
                ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
                drawFrame(ctx, dotsRef.current, 0, cfg, 0, true);
            }
            return () => {
                if (rafRef.current) cancelAnimationFrame(rafRef.current);
            };
        }

        if (state === "completed" || state === "cancelled") {
            collapseStartRef.current = performance.now();
        }

        rafRef.current = requestAnimationFrame(loop);

        return () => {
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
            rafRef.current = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [useCssField, state, intensity]);

    // Reduced-motion / completed exit: plain opacity fade -> fire onCompleted.
    useEffect(() => {
        if (!useCssField) return;
        if (state === "completed" || state === "cancelled") {
            const id = setTimeout(() => onCompleted?.(), REDUCED_FADE_MS);
            return () => clearTimeout(id);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [useCssField, state]);

    // ---- resize ----
    useEffect(() => {
        if (useCssField) return;
        const zone = zoneRef.current;
        if (!zone || typeof ResizeObserver === "undefined") return;
        let raf = 0;
        const ro = new ResizeObserver(() => {
            cancelAnimationFrame(raf);
            raf = requestAnimationFrame(() => sizeAndBuild());
        });
        ro.observe(zone);
        return () => {
            cancelAnimationFrame(raf);
            ro.disconnect();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [useCssField]);

    // ---- pause on hidden tab / off-screen ----
    useEffect(() => {
        if (useCssField) return;
        const resume = () => {
            if (!pausedRef.current) return;
            pausedRef.current = false;
            if (rafRef.current === null && state === "loading") {
                rafRef.current = requestAnimationFrame(function tick(now) {
                    // restart the loop by re-driving sizeAndBuild's loop pattern:
                    const cfg = cfgRef.current;
                    const c = canvasRef.current?.getContext("2d");
                    if (cfg && c) {
                        const t = (now - startRef.current) / 1000;
                        intensityRef.current +=
                            (targetIntensityRef.current -
                                intensityRef.current) *
                            0.045;
                        const flow = intensityRef.current;
                        cfg.flow = flow;
                        const dpr = Math.min(window.devicePixelRatio || 1, 2);
                        auroraRef.current?.render(
                            t,
                            flow,
                            Math.min(1, 0.35 + 0.65 * flow),
                            dpr
                        );
                        c.clearRect(0, 0, c.canvas.width, c.canvas.height);
                        drawFrame(c, dotsRef.current, t, cfg, 0, false);
                    }
                    if (!pausedRef.current)
                        rafRef.current = requestAnimationFrame(tick);
                });
            }
        };
        const pause = () => {
            pausedRef.current = true;
            if (rafRef.current) {
                cancelAnimationFrame(rafRef.current);
                rafRef.current = null;
            }
        };

        const onVis = () => (document.hidden ? pause() : resume());
        document.addEventListener("visibilitychange", onVis);

        let io: IntersectionObserver | null = null;
        if (typeof IntersectionObserver !== "undefined" && cardRef.current) {
            io = new IntersectionObserver(
                (entries) => {
                    const e = entries[0];
                    if (!e) return;
                    e.isIntersecting ? resume() : pause();
                },
                { threshold: 0.01 }
            );
            io.observe(cardRef.current);
        }
        return () => {
            document.removeEventListener("visibilitychange", onVis);
            io?.disconnect();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [useCssField, state]);

    // ---- theme change: re-read --gl-dot* (colour only) ----
    useEffect(() => {
        if (useCssField || typeof MutationObserver === "undefined") return;
        const target = document.documentElement;
        const mo = new MutationObserver(() => {
            const cfg = cfgRef.current;
            if (!cfg || !cardRef.current) return;
            const cs = getComputedStyle(cardRef.current);
            cfg.coreRGB = parseRGB(cs.getPropertyValue("--gl-dot"), cfg.coreRGB);
            cfg.softRGB = parseRGB(
                cs.getPropertyValue("--gl-dot-soft"),
                cfg.softRGB
            );
            cfg.tintRGB = parseRGB(
                cs.getPropertyValue("--gl-spark-tint"),
                cfg.tintRGB ?? [42, 133, 255]
            );
            applyAuroraColors();
        });
        mo.observe(target, { attributes: true, attributeFilter: ["data-theme", "class"] });
        return () => mo.disconnect();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [useCssField]);

    // ---- derived ----
    const isFailed = state === "failed";
    const isExiting = state === "completed" || state === "cancelled";
    const currentLine =
        state === "cancelled"
            ? "Cancelled"
            : statusLines[lineIndex] ?? statusLines[0];
    const showProgress =
        !!progress && Number.isFinite(progress.total) && progress.total > 0;
    const pct = showProgress
        ? Math.min(100, Math.round((progress!.done / progress!.total) * 100))
        : 0;

    const card = (
        <div
            ref={cardRef}
            role="status"
            aria-live="polite"
            aria-busy={state === "loading" || state === "retry"}
            aria-label={`${label}: ${title}`}
            className={`gl-card ${isExiting ? "gl-card-out" : ""} ${
                mode === "fullscreen" ? "w-[min(34rem,92vw)]" : "w-full"
            } ${className}`}
        >
            {/* Thinking overline + pulsing dot */}
            <div className="flex items-center gap-2">
                <span
                    className={`gl-think-dot ${
                        useCssField ? "gl-think-dot--static" : ""
                    }`}
                    aria-hidden
                />
                <span className="text-overline text-t-tertiary">{label}</span>
            </div>

            {/* Title — one clean line, no subtitle */}
            <h3 className="mt-1 text-h5 max-md:text-h6 font-semibold text-t-light">
                {title}
            </h3>

            {/* The hero field: WebGL aurora behind a flow-coupled spark canvas. */}
            <div
                ref={zoneRef}
                className="gl-field-zone"
                aria-hidden
            >
                {useCssField ? (
                    <div className="gl-field--mesh" />
                ) : (
                    <>
                        <canvas
                            ref={auroraCanvasRef}
                            className="gl-aurora-canvas"
                        />
                        <canvas ref={canvasRef} className="gl-canvas" />
                        {/* film-grain + edge-fade overlay for premium depth */}
                        <div className="gl-grain" />
                        <div className="gl-vignette" />
                    </>
                )}

                {isFailed && (
                    <div className="gl-fail-glyph" aria-hidden>
                        <Icon name="close" />
                    </div>
                )}
            </div>

            {/* Status / error line */}
            {isFailed ? (
                <p className="gl-status text-body-2 text-t-secondary">
                    {errorMessage}
                </p>
            ) : reduceMotion ? (
                <p
                    key={swapKey}
                    className="gl-status text-body-2 text-t-secondary"
                >
                    {currentLine}
                </p>
            ) : (
                <div className="gl-status relative h-6 overflow-hidden">
                    <AnimatePresence mode="popLayout" initial={false}>
                        <motion.p
                            key={swapKey}
                            initial={{ opacity: 0, y: 8, filter: "blur(4px)" }}
                            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                            exit={{ opacity: 0, y: -8, filter: "blur(4px)" }}
                            transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
                            className="absolute inset-x-0 text-body-2 text-t-secondary"
                        >
                            {currentLine}
                            {!isExiting && (
                                <span className="gl-ellipsis" aria-hidden>
                                    …
                                </span>
                            )}
                        </motion.p>
                    </AnimatePresence>
                </div>
            )}

            {/* Real-progress hairline — ONLY when total is known (never faked) */}
            {showProgress && !isFailed && (
                <div className="mt-4 w-full max-w-xs mx-auto">
                    <div className="meter">
                        <div
                            className="meter-fill bg-primary-01"
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                    <p className="mt-1.5 text-caption text-t-tertiary text-center">
                        {progress!.done} of {progress!.total} ready
                    </p>
                </div>
            )}

            {/* Actions */}
            {isFailed && (
                <div className="mt-5 flex items-center justify-center gap-2">
                    {onRetry && (
                        <Button isBlack autoFocus onClick={onRetry}>
                            Try again
                        </Button>
                    )}
                    {onCancel && (
                        <Button isStroke onClick={onCancel}>
                            Back
                        </Button>
                    )}
                </div>
            )}
            {!isFailed && !isExiting && onCancel && (
                <div className="mt-5 flex items-center justify-center">
                    <Button isStroke onClick={onCancel}>
                        Cancel
                    </Button>
                </div>
            )}
        </div>
    );

    if (mode === "fullscreen") {
        return (
            <div
                className="fixed inset-0 z-50 flex items-center justify-center bg-b-dark2/95 backdrop-blur-sm p-4"
                onKeyDown={(e) => {
                    if (e.key === "Escape") onCancel?.();
                }}
            >
                {card}
            </div>
        );
    }

    return card;
};

export default GenerationLoader;
