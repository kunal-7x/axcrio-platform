"use client";

// Premium waveform audio player (core dashboard theme): circular play/pause, a
// DRAGGABLE click-to-seek waveform that fills smoothly (rAF + clip-path), an
// accurate current/total time, a speed control and a download.
//
// Duration: the backend's recorded length (`durationFallback`, seconds) is the
// AUTHORITATIVE total — streamed OGG/Opus often reports a wrong/Infinity metadata
// duration, so we trust the backend number and only fall back to the element's
// duration (with the Infinity-resolve hack) when no backend value exists.
// `audioRef` is forwarded so the calls page can drive its synced transcript;
// `onTime` mirrors the playhead at ~60fps so that highlight moves smoothly.

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchRecordingBlob } from "@/lib/api";

const RATES = [1, 1.25, 1.5, 2];
const BARS = 56;

function fmt(s: number): string {
    if (!isFinite(s) || s < 0) s = 0;
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, "0")}`;
}

function waveform(seed: string): number[] {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < seed.length; i++) {
        h ^= seed.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    const out: number[] = [];
    for (let i = 0; i < BARS; i++) {
        h ^= h << 13;
        h ^= h >>> 17;
        h ^= h << 5;
        h >>>= 0;
        const r = (h % 1000) / 1000;
        const edge = Math.sin((i / (BARS - 1)) * Math.PI);
        out.push(0.16 + r * 0.84 * (0.5 + 0.5 * edge));
    }
    return out;
}

type Props = {
    src: string;
    durationFallback?: number | null;
    audioRef?: React.MutableRefObject<HTMLAudioElement | null> | React.RefObject<HTMLAudioElement | null>;
    onTime?: (t: number) => void;
    onDuration?: (d: number) => void;
    download?: boolean;
    className?: string;
};

const AudioPlayer = ({ src, durationFallback, audioRef, onTime, onDuration, download = true, className }: Props) => {
    const innerRef = useRef<HTMLAudioElement | null>(null);
    const waveRef = useRef<HTMLDivElement | null>(null);
    const draggingRef = useRef(false);
    const [playing, setPlaying] = useState(false);
    const [cur, setCur] = useState(0);
    const [dur, setDur] = useState<number>(durationFallback && durationFallback > 0 ? durationFallback : 0);
    const [rate, setRate] = useState(1);
    const [scrub, setScrub] = useState<number | null>(null);
    const heights = useMemo(() => waveform(src || ""), [src]);

    // Full-buffer fix: fetch the whole recording via the same-origin proxy → object URL → play from
    // memory, so it doesn't stutter streaming cross-region from Singapore. Falls back to the streaming
    // src while loading / on any failure. Revokes the object URL on src change / unmount.
    const [blobUrl, setBlobUrl] = useState("");
    useEffect(() => {
        if (!src) { setBlobUrl(""); return; }
        let dead = false; let made = "";
        fetchRecordingBlob(src).then((u) => { if (!dead && u) { made = u; setBlobUrl(u); } });
        return () => { dead = true; setBlobUrl(""); if (made) { try { URL.revokeObjectURL(made); } catch { /* ignore */ } } };
    }, [src]);

    const setRefs = useCallback(
        (el: HTMLAudioElement | null) => {
            innerRef.current = el;
            if (audioRef) (audioRef as React.MutableRefObject<HTMLAudioElement | null>).current = el;
        },
        [audioRef]
    );

    useEffect(() => {
        setCur(0);
        setPlaying(false);
        setScrub(null);
        const d = durationFallback && durationFallback > 0 ? durationFallback : 0;
        setDur(d);
        if (d > 0) onDuration?.(d);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [src, durationFallback]);

    // Trust the backend length (streamed OGG/Opus often reports a wildly inflated
    // metadata duration); only use the element's own duration when none is given.
    const applyDur = (d: number) => {
        setDur(d);
        onDuration?.(d);
    };
    const refreshDur = () => {
        if (durationFallback && durationFallback > 0) {
            applyDur(durationFallback);
            return;
        }
        const a = innerRef.current;
        if (!a) return;
        if (isFinite(a.duration) && a.duration > 0) {
            applyDur(a.duration);
        } else if (a.duration === Infinity) {
            // streamed file with no duration header — force the browser to resolve it
            try {
                a.currentTime = 1e7;
            } catch {
                /* ignore */
            }
        }
    };

    // The local waveform updates every frame (cheap — memoised bars), but the
    // EXTERNAL onTime (which drives the calls page's transcript highlight and
    // re-renders that big component) is throttled to ~8/s so it stays smooth and
    // never janks. `force` fires it immediately (seek / drag-end / play toggle).
    const lastEmit = useRef(0);
    const pushTime = (t: number, force = false) => {
        setCur(t);
        const now = typeof performance !== "undefined" ? performance.now() : 0;
        if (force || now - lastEmit.current >= 120) {
            lastEmit.current = now;
            onTime?.(t);
        }
    };

    // Smooth 60fps playhead while playing (timeupdate alone is ~4Hz → choppy).
    useEffect(() => {
        if (!playing) return;
        let raf = 0;
        const loop = () => {
            const a = innerRef.current;
            if (a && !draggingRef.current) pushTime(a.currentTime);
            raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
        return () => cancelAnimationFrame(raf);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [playing]);

    const toggle = () => {
        const a = innerRef.current;
        if (!a) return;
        if (a.paused) void a.play();
        else a.pause();
    };
    const cycleRate = () => {
        const next = RATES[(RATES.indexOf(rate) + 1) % RATES.length];
        setRate(next);
        if (innerRef.current) innerRef.current.playbackRate = next;
    };

    // ── drag-to-seek (pointer events = mouse + touch) ─────────────────────────
    const fracFromEvent = (clientX: number): number => {
        const r = waveRef.current?.getBoundingClientRect();
        if (!r || r.width === 0) return 0;
        return Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    };
    const onDown = (e: React.PointerEvent) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        draggingRef.current = true;
        setScrub(fracFromEvent(e.clientX));
    };
    const onMove = (e: React.PointerEvent) => {
        if (draggingRef.current) setScrub(fracFromEvent(e.clientX));
    };
    const endDrag = (e: React.PointerEvent) => {
        if (!draggingRef.current) return;
        draggingRef.current = false;
        const f = fracFromEvent(e.clientX);
        const a = innerRef.current;
        if (a && dur) {
            const t = f * dur;
            a.currentTime = t;
            pushTime(t, true);
        }
        setScrub(null);
    };

    const playProg = dur > 0 ? Math.max(0, Math.min(1, cur / dur)) : 0;
    const prog = scrub != null ? scrub : playProg;
    const shownCur = scrub != null ? scrub * dur : cur;

    return (
        <div
            className={`flex items-center gap-3 p-2 pr-3 rounded-full bg-b-surface1 ring-1 ring-s-subtle ring-inset max-sm:gap-2 ${
                className || ""
            }`}
        >
            <audio
                ref={setRefs}
                src={blobUrl || src}
                preload="auto"
                className="hidden"
                onLoadedMetadata={refreshDur}
                onDurationChange={refreshDur}
                onTimeUpdate={() => {
                    const a = innerRef.current;
                    if (a && !draggingRef.current && !playing) pushTime(a.currentTime);
                }}
                onSeeked={() => {
                    const a = innerRef.current;
                    // reset after the Infinity-resolve hack
                    if (a && a.currentTime > 1e6) {
                        a.currentTime = 0;
                        pushTime(0);
                    }
                }}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onEnded={() => {
                    setPlaying(false);
                    pushTime(0);
                }}
            />

            <button
                type="button"
                onClick={toggle}
                aria-label={playing ? "Pause" : "Play"}
                className="grid place-items-center size-11 shrink-0 rounded-full bg-primary-01 text-white fill-white shadow-[0_4px_12px_-4px_rgba(42,133,255,0.6)] transition-all active:scale-95 hover:brightness-110 max-sm:size-10"
            >
                {playing ? <PauseIcon /> : <PlayIcon />}
            </button>

            <div
                ref={waveRef}
                onPointerDown={onDown}
                onPointerMove={onMove}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
                aria-label="Seek"
                className="relative h-9 flex-1 min-w-0 cursor-pointer select-none touch-none"
            >
                <Bars heights={heights} accent={false} />
                <div
                    className="absolute inset-0"
                    style={{
                        clipPath: `inset(0 ${(1 - prog) * 100}% 0 0)`,
                        // NO css transition while playing: the rAF loop already drives prog at 60fps, and
                        // a 90ms transition on top fights it (restarts every frame) → the bar lags + "sticks".
                        // Transition ONLY when idle/seeking (a single smooth jump after a seek-release).
                        transition: scrub != null || playing ? "none" : "clip-path 90ms linear",
                    }}
                >
                    <Bars heights={heights} accent />
                </div>
                <div
                    className="absolute top-0 bottom-0 w-[2px] -ml-px rounded-full bg-primary-01 shadow-[0_0_8px_rgba(42,133,255,0.7)]"
                    style={{
                        left: `${prog * 100}%`,
                        transition: scrub != null || playing ? "none" : "left 90ms linear",
                    }}
                />
            </div>

            <span className="shrink-0 text-caption tabular-nums text-t-secondary whitespace-nowrap max-sm:hidden">
                {fmt(shownCur)} <span className="text-t-tertiary">/ {fmt(dur)}</span>
            </span>

            <button
                type="button"
                onClick={cycleRate}
                aria-label="Playback speed"
                className="shrink-0 h-7 px-2 rounded-full text-caption font-medium tabular-nums text-t-secondary transition-colors hover:text-t-primary hover:bg-b-surface2"
            >
                {rate}x
            </button>

            {download && (
                <a
                    href={blobUrl || src}
                    download="recording.mp3"
                    target="_blank"
                    rel="noreferrer"
                    aria-label="Download recording"
                    className="grid place-items-center size-8 shrink-0 rounded-full border border-s-subtle text-t-secondary fill-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary hover:fill-t-primary"
                >
                    <DownloadIcon />
                </a>
            )}
        </div>
    );
};

export default AudioPlayer;

// Memoised: the bar layout depends only on `heights` (stable), so 60fps progress
// updates only re-style the clip-path + playhead, never the 56 bars.
const Bars = memo(({ heights, accent }: { heights: number[]; accent: boolean }) => (
    <div className="flex items-center gap-[2px] w-full h-full pointer-events-none">
        {heights.map((h, i) => (
            <span
                key={i}
                className={`flex-1 rounded-full ${accent ? "bg-primary-01" : "bg-t-tertiary/30"}`}
                style={{ height: `${Math.round(h * 100)}%`, minWidth: 2 }}
            />
        ))}
    </div>
));
Bars.displayName = "Bars";

const PlayIcon = () => (
    <svg viewBox="0 0 24 24" className="size-5 ml-0.5 fill-current" aria-hidden>
        <path d="M8 5.14v13.72c0 .86.94 1.39 1.68.95l11.04-6.86c.72-.45.72-1.49 0-1.94L9.68 4.19C8.94 3.74 8 4.28 8 5.14z" />
    </svg>
);
const PauseIcon = () => (
    <svg viewBox="0 0 24 24" className="size-5 fill-current" aria-hidden>
        <rect x="6.5" y="5" width="3.6" height="14" rx="1.4" />
        <rect x="13.9" y="5" width="3.6" height="14" rx="1.4" />
    </svg>
);
const DownloadIcon = () => (
    <svg viewBox="0 0 24 24" className="size-4 fill-current" aria-hidden>
        <path d="M12 3a1 1 0 0 1 1 1v8.59l2.3-2.3a1 1 0 1 1 1.4 1.42l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.42l2.3 2.3V4a1 1 0 0 1 1-1zM5 19a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H6a1 1 0 0 1-1-1z" />
    </svg>
);
