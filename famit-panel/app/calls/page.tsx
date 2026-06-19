"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Card from "@/components/Card";
import Field from "@/components/Field";
import Spinner from "@/components/Spinner";
import Search from "@/components/Search";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import Tabs from "@/components/Tabs";
import VirtualRows from "@/components/VirtualRows";
import ConfirmDeleteModal from "@/components/ConfirmDeleteModal";
import { StatusBadge, OutcomeBadge, InterestBadge } from "@/lib/badges";
import { useCallsInfinite } from "@/lib/queries";
import {
    getCalls,
    getCallDetail,
    getCallRecording,
    getCallbacks,
    addCallback,
    cancelCallback,
    getSuppression,
    addSuppression,
    deleteSuppression,
    type CallLog,
    type CallDetail,
    type CallRecording,
    type CallbackEntry,
    type CallTranscriptTurn,
    type SuppressionEntry,
} from "@/lib/api";
import { type TabsOption } from "@/types/tabs";

/* ------------------------------------------------------------------ */
/* Formatting helpers                                                  */
/* ------------------------------------------------------------------ */

// Backend timestamps are frequently NAIVE (no timezone, stored as UTC but
// serialized without a `Z`). `new Date("2026-06-19T09:00:00")` is parsed as
// LOCAL time by JS — which shifts every call several hours and breaks the
// "Xh ago" relative line. toUTC() appends `Z` to a naive ISO string so it is
// parsed as UTC (CRM + dashboard already apply this exact fix).
function toUTC(d: string): string {
    if (!d) return d;
    // Already has an explicit zone (Z, +05:30, -0800 …) → leave it alone.
    if (/[zZ]$/.test(d) || /[+-]\d{2}:?\d{2}$/.test(d)) return d;
    // Looks like a bare ISO datetime (date + time, no zone) → mark it UTC.
    if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(d)) {
        return d.replace(" ", "T") + "Z";
    }
    return d;
}

// Compact "Jun 9, 3:42 PM" — calmer than a full locale string in dense cells.
function fmtShort(d: string) {
    if (!d) return "—";
    const dt = new Date(toUTC(d));
    if (isNaN(dt.getTime())) return d;
    return dt.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

// "1h 04m" / "3m 12s" / "48s" — human duration from seconds.
function fmtDuration(s?: number | null) {
    if (s == null) return "—";
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const sec = s % 60;
    if (m < 60) return `${m}m ${String(sec).padStart(2, "0")}s`;
    const h = Math.floor(m / 60);
    return `${h}h ${String(m % 60).padStart(2, "0")}m`;
}

// "0:48" / "3:12" / "1:04:09" — mm:ss clock for the audio player / recording cell.
function fmtClock(s?: number | null) {
    if (s == null || s < 0 || isNaN(s)) return "0:00";
    const total = Math.floor(s);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const sec = total % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
    return `${m}:${String(sec).padStart(2, "0")}`;
}

// Relative "2h ago" for recency — purely from real timestamps (UTC-corrected).
function fmtRelative(d: string) {
    if (!d) return "";
    const dt = new Date(toUTC(d)).getTime();
    if (isNaN(dt)) return "";
    const diff = Date.now() - dt;
    if (diff < 0) return "";
    const min = Math.round(diff / 60000);
    if (min < 1) return "just now";
    if (min < 60) return `${min}m ago`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const day = Math.round(hr / 24);
    if (day < 30) return `${day}d ago`;
    return "";
}

const LIVE = new Set(["calling", "in_progress"]);

/* ------------------------------------------------------------------ */
/* Recording + transcript-timing helpers (additive / back-compat)      */
/* ------------------------------------------------------------------ */

// The backend will (eventually) attach a presigned recording URL to a call.
// It may live on the slim CallLog row or on the call object inside CallDetail.
// We read it defensively off whatever shape the backend ships — the UI degrades
// silently (no Recording cell / no player) when it is absent. See "BACKEND
// DEPENDENCY" note at the bottom of this file.
function recordingUrlOf(c?: Partial<CallLog> | null): string | null {
    if (!c) return null;
    const rec = c as Record<string, unknown>;
    const url =
        rec.recording_presigned_url ??
        rec.recording_url ??
        rec.recordingUrl ??
        rec.audio_url ??
        rec.recording;
    return typeof url === "string" && url.length > 0 ? url : null;
}

// Karaoke needs per-turn timing. Turns MAY carry optional t0/t1 (seconds) once
// the backend emits them; until then this returns null and we render the plain
// (non-synced) bubble list. A turn is "timed" only if it has a numeric t0.
type TimedTurn = CallTranscriptTurn & { t0?: number; t1?: number };
function turnStart(turn: TimedTurn): number | null {
    const t0 = (turn as Record<string, unknown>).t0;
    return typeof t0 === "number" && !isNaN(t0) ? t0 : null;
}
function turnEnd(turn: TimedTurn): number | null {
    const t1 = (turn as Record<string, unknown>).t1;
    return typeof t1 === "number" && !isNaN(t1) ? t1 : null;
}

/* ================================================================== */
/* DETAIL MODAL                                                        */
/* ================================================================== */

function CallDetailModal({
    callId,
    onClose,
}: {
    callId: string;
    onClose: () => void;
}) {
    const [detail, setDetail] = useState<CallDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    // The recording is served by a SEPARATE endpoint (GET /calls/{id}/recording)
    // that mints the presigned player URL — the /calls/{id} detail does NOT carry
    // it. We fetch it alongside the detail and POLL while it is not yet playable so
    // the player appears within seconds of the call ending (the .ogg lands in
    // Spaces almost immediately after hangup, then self-heals on read).
    const [recording, setRecording] = useState<CallRecording | null>(null);

    // Audio playback state drives the karaoke highlight + auto-scroll.
    const audioRef = useRef<HTMLAudioElement>(null);
    const [playhead, setPlayhead] = useState(0);

    useEffect(() => {
        getCallDetail(callId)
            .then(setDetail)
            .catch((e) =>
                setError(e instanceof Error ? e.message : "Failed to load")
            )
            .finally(() => setLoading(false));
    }, [callId]);

    // Fetch + poll the recording until it is playable (or the modal closes). Once
    // playable we stop polling. A still-live / just-ended call may take a few
    // seconds to upload + finalize, so we re-check every 5s up to ~2 min.
    useEffect(() => {
        let cancelled = false;
        let timer: ReturnType<typeof setTimeout> | undefined;
        let attempts = 0;
        const MAX_ATTEMPTS = 24; // ~2 min at 5s

        const tick = () => {
            getCallRecording(callId)
                .then((rec) => {
                    if (cancelled) return;
                    setRecording(rec);
                    attempts += 1;
                    if (!rec.playable && attempts < MAX_ATTEMPTS) {
                        timer = setTimeout(tick, 5000);
                    }
                })
                .catch(() => {
                    if (cancelled) return;
                    attempts += 1;
                    if (attempts < MAX_ATTEMPTS) timer = setTimeout(tick, 5000);
                });
        };
        tick();
        return () => {
            cancelled = true;
            if (timer) clearTimeout(timer);
        };
    }, [callId]);

    function handleBackdrop(e: React.MouseEvent<HTMLDivElement>) {
        if (e.target === e.currentTarget) onClose();
    }

    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", handler);
        return () => document.removeEventListener("keydown", handler);
    }, [onClose]);

    const call = detail?.call;
    const t = detail?.transcript;
    const turns = (t?.turns ?? []) as TimedTurn[];
    const turnCount = turns.length;
    // PRIMARY source: the dedicated /calls/{id}/recording presigned URL (polled).
    // FALLBACK: any URL the detail row happens to carry (belt-and-suspenders).
    const recordingUrl =
        (recording?.playable && recording.recording_presigned_url) ||
        recordingUrlOf(call);
    // Still waiting on the recording to finalize+upload (call may have just ended).
    const recordingPending = !recordingUrl && recording != null && !recording.playable;

    // Karaoke is available ONLY when we have audio AND every turn carries a
    // numeric t0. Otherwise we render the existing (non-synced) bubble list.
    const karaokeReady =
        !!recordingUrl &&
        turnCount > 0 &&
        turns.every((turn) => turnStart(turn) != null);

    // Which turn is "active" for the current playhead (last turn whose t0 <= now,
    // bounded by t1 when present). -1 = none yet.
    const activeIdx = useMemo(() => {
        if (!karaokeReady) return -1;
        let idx = -1;
        for (let i = 0; i < turns.length; i++) {
            const start = turnStart(turns[i]);
            if (start == null) continue;
            if (start <= playhead + 0.15) {
                const end = turnEnd(turns[i]);
                // If we have an end and we're past it AND a later turn has started,
                // the later turn wins (handled naturally by the loop overwriting idx).
                if (end != null && playhead > end + 0.5) {
                    // keep as candidate only if no later turn starts before now
                    idx = i;
                } else {
                    idx = i;
                }
            } else {
                break;
            }
        }
        return idx;
    }, [karaokeReady, turns, playhead]);

    // Auto-scroll the active turn into view as the audio plays.
    const turnRefs = useRef<(HTMLDivElement | null)[]>([]);
    useEffect(() => {
        if (activeIdx < 0) return;
        const el = turnRefs.current[activeIdx];
        if (el)
            el.scrollIntoView({
                behavior: "smooth",
                block: "nearest",
            });
    }, [activeIdx]);

    // Click a turn → seek the audio to its start (karaoke is two-way).
    const seekTo = useCallback((sec: number | null) => {
        if (sec == null || !audioRef.current) return;
        audioRef.current.currentTime = sec;
        setPlayhead(sec);
        void audioRef.current.play().catch(() => {});
    }, []);

    const initials = call?.name
        ? call.name
              .split(" ")
              .map((w) => w[0])
              .slice(0, 2)
              .join("")
              .toUpperCase()
        : "—";

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-shade-01/50 backdrop-blur-sm"
            onClick={handleBackdrop}
        >
            <div className="surface w-full max-w-2xl max-h-[90vh] flex flex-col rise-in overflow-hidden">
                {/* ---- Hero header ---- */}
                <div className="relative shrink-0 px-6 pt-6 pb-5 border-b border-s-subtle">
                    {/* soft brand wash */}
                    <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-br from-primary-01/10 to-transparent opacity-60" />
                    <div className="relative flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3.5 min-w-0">
                            <span className="flex items-center justify-center size-12 shrink-0 rounded-2xl bg-primary-01/12 text-primary-01 text-sub-title-2 font-semibold tabular-nums">
                                {loading ? (
                                    <Icon
                                        name="chat"
                                        className="size-5 fill-primary-01"
                                    />
                                ) : (
                                    initials
                                )}
                            </span>
                            <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                    <h2 className="text-h6 text-t-primary truncate">
                                        {loading
                                            ? "Loading call…"
                                            : call?.name || "Call detail"}
                                    </h2>
                                </div>
                                <div className="flex items-center gap-2 mt-0.5 text-caption text-t-secondary">
                                    {call?.phone && (
                                        <span className="tabular-nums">
                                            {call.phone}
                                        </span>
                                    )}
                                    {call?.phone && call?.campaign_name && (
                                        <span className="text-t-tertiary">·</span>
                                    )}
                                    {call?.campaign_name && (
                                        <span className="truncate">
                                            {call.campaign_name}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="flex items-center justify-center size-8 shrink-0 rounded-full text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary dark:hover:bg-shade-04/60"
                            aria-label="Close"
                        >
                            <Icon name="close" className="size-4 fill-current" />
                        </button>
                    </div>

                    {/* status / outcome row */}
                    {!loading && detail && (
                        <div className="relative flex flex-wrap items-center gap-2 mt-4">
                            <StatusBadge status={call?.status} />
                            {t?.opt_out && (
                                <Badge variant="danger" dot>
                                    Opted out / DND
                                </Badge>
                            )}
                            <OutcomeBadge outcome={t?.outcome ?? ""} />
                            <InterestBadge interest={t?.interest ?? ""} />
                        </div>
                    )}
                </div>

                {/* ---- Body ---- */}
                <div className="overflow-y-auto px-6 py-5 space-y-5 scrollbar-thin">
                    {loading && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-3 gap-3">
                                <div className="skeleton h-16" />
                                <div className="skeleton h-16" />
                                <div className="skeleton h-16" />
                            </div>
                            <div className="skeleton h-20" />
                            <div className="skeleton h-32" />
                        </div>
                    )}

                    {error && (
                        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 text-primary-03 text-body-2">
                            <Icon
                                name="info"
                                className="size-4 fill-primary-03 shrink-0"
                            />
                            {error}
                        </div>
                    )}

                    {detail && (
                        <>
                            {/* Stat chips */}
                            <div className="grid grid-cols-3 gap-3 max-sm:grid-cols-1">
                                <StatChip
                                    icon="clock"
                                    label="Duration"
                                    value={fmtDuration(call?.duration_s)}
                                />
                                <StatChip
                                    icon="chat"
                                    label="Exchanges"
                                    value={
                                        turnCount > 0 ? String(turnCount) : "—"
                                    }
                                />
                                <StatChip
                                    icon="calendar"
                                    label="Placed"
                                    value={
                                        call?.started_at
                                            ? fmtShort(call.started_at)
                                            : "—"
                                    }
                                />
                            </div>

                            {/* ---- Recording playback row ---- */}
                            {/* Appears as soon as the backend exposes a recording URL.
                                Native <audio> drives the karaoke highlight via timeupdate. */}
                            {recordingUrl ? (
                                <div className="p-4 rounded-2xl bg-b-surface1/70 dark:bg-shade-04/30">
                                    <div className="flex items-center gap-2 mb-3">
                                        <Icon
                                            name="video"
                                            className="size-3.5 fill-t-tertiary"
                                        />
                                        <div className="eyebrow">Recording</div>
                                        {karaokeReady && (
                                            <span className="ml-auto inline-flex items-center gap-1.5 text-caption text-primary-01">
                                                <span className="size-1.5 rounded-full bg-primary-01" />
                                                Synced transcript
                                            </span>
                                        )}
                                    </div>
                                    <audio
                                        ref={audioRef}
                                        src={recordingUrl}
                                        controls
                                        preload="metadata"
                                        className="w-full"
                                        onTimeUpdate={(e) =>
                                            setPlayhead(
                                                e.currentTarget.currentTime
                                            )
                                        }
                                        onSeeked={(e) =>
                                            setPlayhead(
                                                e.currentTarget.currentTime
                                            )
                                        }
                                    >
                                        Your browser does not support audio
                                        playback.
                                    </audio>
                                </div>
                            ) : (
                                // Recording not (yet) attached to this call. While
                                // we are still polling for it (recordingPending) we
                                // show a calm "preparing" state with a spinner — it
                                // flips to the player automatically the moment the
                                // upload + finalize completes (no refresh needed).
                                !loading && (
                                    <div className="flex items-center gap-2.5 p-3.5 rounded-2xl bg-b-surface1/50 dark:bg-shade-04/20 text-caption text-t-tertiary">
                                        {recordingPending ? (
                                            <span className="size-3.5 shrink-0 rounded-full border-2 border-s-subtle border-t-primary-01 animate-spin" />
                                        ) : (
                                            <Icon
                                                name="clock"
                                                className="size-3.5 fill-t-tertiary shrink-0"
                                            />
                                        )}
                                        {recordingPending
                                            ? "Preparing recording — it appears here automatically the moment the call audio uploads."
                                            : "Recording not available yet — it appears here automatically once processed."}
                                    </div>
                                )
                            )}

                            {/* AI Summary */}
                            {t?.summary && (
                                <div className="p-4 rounded-2xl bg-b-surface1/70 dark:bg-shade-04/30">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Icon
                                            name="feather"
                                            className="size-3.5 fill-t-tertiary"
                                        />
                                        <div className="eyebrow">AI summary</div>
                                    </div>
                                    <p className="text-body-2 text-t-primary leading-relaxed">
                                        {t.summary}
                                    </p>
                                </div>
                            )}

                            {/* Next Action */}
                            {t?.next_action && (
                                <div className="flex gap-3 p-4 rounded-2xl bg-primary-01/[0.06]">
                                    <span className="flex items-center justify-center size-8 shrink-0 rounded-xl bg-primary-01/12">
                                        <Icon
                                            name="reply"
                                            className="size-4 fill-primary-01"
                                        />
                                    </span>
                                    <div>
                                        <div className="eyebrow text-primary-01 mb-1">
                                            Recommended next action
                                        </div>
                                        <p className="text-body-2 text-t-primary">
                                            {t.next_action}
                                        </p>
                                    </div>
                                </div>
                            )}

                            {/* Transcript — karaoke when timed, plain bubbles else */}
                            {turns.length > 0 && (
                                <div>
                                    <div className="flex items-center justify-between mb-3">
                                        <div className="eyebrow">
                                            Transcript
                                            {karaokeReady && (
                                                <span className="ml-2 normal-case tracking-normal text-caption text-t-tertiary">
                                                    tap a line to jump there
                                                </span>
                                            )}
                                        </div>
                                        <span className="text-caption text-t-tertiary tabular-nums">
                                            {turnCount} turn
                                            {turnCount === 1 ? "" : "s"}
                                        </span>
                                    </div>
                                    <div className="relative space-y-3 pl-1">
                                        {turns.map((turn, i) => {
                                            // Backend normalises roles to `ai`/`customer`
                                            // (also accept agent/assistant + user/caller/lead).
                                            // AI → LEFT, customer/lead → RIGHT (mirrors the
                                            // CRM ChatBubble convention).
                                            const role = (
                                                turn.role || ""
                                            ).toLowerCase();
                                            const isCustomer =
                                                role === "customer" ||
                                                role === "user" ||
                                                role === "caller" ||
                                                role === "lead";
                                            const isAI = !isCustomer;
                                            const custLabel =
                                                call?.name || "Customer";
                                            const start = turnStart(turn);
                                            const isActive =
                                                karaokeReady && i === activeIdx;
                                            const isPast =
                                                karaokeReady &&
                                                activeIdx >= 0 &&
                                                i < activeIdx;
                                            return (
                                                <div
                                                    key={i}
                                                    ref={(el) => {
                                                        turnRefs.current[i] = el;
                                                    }}
                                                    onClick={
                                                        karaokeReady
                                                            ? () => seekTo(start)
                                                            : undefined
                                                    }
                                                    className={`flex gap-2.5 rounded-3xl transition-all duration-300 ${
                                                        isAI
                                                            ? "flex-row"
                                                            : "flex-row-reverse"
                                                    } ${
                                                        karaokeReady
                                                            ? "cursor-pointer px-1.5 py-1 -mx-1.5"
                                                            : ""
                                                    } ${
                                                        isActive
                                                            ? "bg-primary-01/[0.06] ring-1 ring-primary-01/20"
                                                            : ""
                                                    } ${
                                                        isPast && !isActive
                                                            ? "opacity-60"
                                                            : ""
                                                    }`}
                                                >
                                                    <span
                                                        className={`shrink-0 flex items-center justify-center size-7 rounded-full text-caption font-semibold ${
                                                            isAI
                                                                ? "bg-b-surface2 ring-1 ring-s-subtle text-t-secondary dark:bg-shade-04/60"
                                                                : "bg-primary-01/12 text-primary-01"
                                                        }`}
                                                        title={
                                                            isAI
                                                                ? "AI"
                                                                : custLabel
                                                        }
                                                    >
                                                        {isAI
                                                            ? "AI"
                                                            : (custLabel[0] ||
                                                                  "C").toUpperCase()}
                                                    </span>
                                                    <div
                                                        className={`flex flex-col gap-1 max-w-[80%] ${
                                                            isAI
                                                                ? "items-start"
                                                                : "items-end"
                                                        }`}
                                                    >
                                                        <div className="flex items-center gap-2 px-1 text-caption text-t-tertiary">
                                                            <span>
                                                                {isAI
                                                                    ? "AI agent"
                                                                    : custLabel}
                                                            </span>
                                                            {karaokeReady &&
                                                                start != null && (
                                                                    <span className="tabular-nums text-t-tertiary/70">
                                                                        {fmtClock(
                                                                            start
                                                                        )}
                                                                    </span>
                                                                )}
                                                        </div>
                                                        <div
                                                            className={`px-3.5 py-2.5 text-body-2 text-t-primary leading-relaxed whitespace-pre-wrap break-words ${
                                                                isAI
                                                                    ? "bg-b-surface2 ring-1 ring-s-subtle ring-inset rounded-3xl rounded-bl-lg dark:bg-shade-04/60"
                                                                    : "bg-primary-01/12 rounded-3xl rounded-br-lg"
                                                            }`}
                                                        >
                                                            {turn.content}
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}

                            {/* No transcript */}
                            {(!t?.turns || t.turns.length === 0) &&
                                !t?.summary && (
                                    <div className="state-block">
                                        <span className="state-glyph">
                                            <Icon
                                                name="chat"
                                                className="fill-inherit"
                                            />
                                        </span>
                                        <div className="state-title">
                                            No transcript available
                                        </div>
                                        <div className="state-sub">
                                            This call didn’t produce a recorded
                                            conversation.
                                        </div>
                                    </div>
                                )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

function StatChip({
    icon,
    label,
    value,
}: {
    icon: string;
    label: string;
    value: React.ReactNode;
}) {
    return (
        <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-b-surface1/60 dark:bg-shade-04/30">
            <span className="flex items-center justify-center size-9 shrink-0 rounded-xl bg-b-surface2 fill-t-secondary dark:bg-shade-04/60">
                <Icon name={icon} className="size-4 fill-inherit" />
            </span>
            <div className="min-w-0">
                <div className="eyebrow">{label}</div>
                <div className="text-body-2 font-medium text-t-primary tabular-nums truncate">
                    {value}
                </div>
            </div>
        </div>
    );
}

/* ================================================================== */
/* LIST PAGE                                                           */
/* ================================================================== */

// W15 — Call Logs is the ONE call surface. /callbacks folds in here as a tab
// (design/W15-UI-IA-PLAN.md §1, dest #3). Do-Not-Call (the old /suppression
// page) folds in as the 3rd tab. Tabs are URL-driven (?tab=callbacks|dnc) so
// deep-links + the /callbacks & /suppression redirect aliases resolve here.
const CALL_TABS: TabsOption[] = [
    { id: 1, name: "Calls" },
    { id: 4, name: "Warm leads" },
    { id: 2, name: "Callbacks" },
    { id: 3, name: "Do-Not-Call" },
];

export default function CallLogsPage() {
    return (
        <Suspense fallback={<Layout title="Call logs"><div /></Layout>}>
            <CallLogsInner />
        </Suspense>
    );
}

function CallLogsInner() {
    const router = useRouter();
    const params = useSearchParams();
    const tabParam = params.get("tab");
    const byId = (id: number) =>
        CALL_TABS.find((t) => t.id === id) ?? CALL_TABS[0];
    const tab =
        tabParam === "warm"
            ? byId(4)
            : tabParam === "callbacks"
              ? byId(2)
              : tabParam === "dnc" || tabParam === "do-not-call"
                ? byId(3)
                : byId(1);
    const setTab = (t: TabsOption) => {
        const sp = new URLSearchParams(params.toString());
        if (t.id === 4) sp.set("tab", "warm");
        else if (t.id === 2) sp.set("tab", "callbacks");
        else if (t.id === 3) sp.set("tab", "dnc");
        else sp.delete("tab");
        const qs = sp.toString();
        router.replace(qs ? `/calls?${qs}` : "/calls", { scroll: false });
    };

    return (
        <Layout title="Call logs">
            <div className="mb-3 flex items-center">
                <Tabs items={CALL_TABS} value={tab} setValue={setTab} />
            </div>
            {tab.id === 4 ? (
                <WarmLeadsPanel />
            ) : tab.id === 2 ? (
                <CallbacksPanel />
            ) : tab.id === 3 ? (
                <DoNotCallPanel />
            ) : (
                <CallsListPanel />
            )}
        </Layout>
    );
}

/* ------------------------------------------------------------------ */
/* Sorting                                                             */
/* ------------------------------------------------------------------ */

type SortKey = "lead" | "campaign" | "status" | "placed" | "duration" | "score";
type SortDir = "asc" | "desc";

// Map the UI sort key onto the backend sort_by column so the cursor query sorts
// across ALL records server-side (the client sort stays as a graceful fallback).
const SORT_COLUMN: Record<SortKey, string> = {
    lead: "name",
    campaign: "campaign_name",
    status: "status",
    placed: "started_at",
    duration: "duration_s",
    score: "interest",
};

function cmp(a: number | string, b: number | string): number {
    if (typeof a === "number" && typeof b === "number") return a - b;
    return String(a).localeCompare(String(b));
}

function sortKeyValue(c: CallLog, key: SortKey): number | string {
    switch (key) {
        case "lead":
            return (c.name || "").toLowerCase();
        case "campaign":
            return (c.campaign_name || "").toLowerCase();
        case "status":
            return (c.status || "").toLowerCase();
        case "placed":
            return c.started_at ? new Date(toUTC(c.started_at)).getTime() : 0;
        case "duration":
            return c.duration_s ?? -1;
        case "score":
            return c.interest ?? -1;
    }
}

// Sortable <th> — click to sort, click again to flip direction.
function SortTh({
    label,
    sortKey,
    active,
    dir,
    onSort,
    className = "",
}: {
    label: string;
    sortKey: SortKey;
    active: boolean;
    dir: SortDir;
    onSort: (k: SortKey) => void;
    className?: string;
}) {
    return (
        <th className={className}>
            <button
                type="button"
                onClick={() => onSort(sortKey)}
                className={`group/sort inline-flex items-center gap-1 select-none transition-colors hover:text-t-primary ${
                    active ? "text-t-primary" : ""
                }`}
            >
                {label}
                <Icon
                    name="chevron"
                    className={`size-3 fill-current transition-all ${
                        active
                            ? dir === "asc"
                                ? "rotate-180 opacity-100"
                                : "opacity-100"
                            : "opacity-0 group-hover/sort:opacity-40"
                    }`}
                />
            </button>
        </th>
    );
}

function CallsListPanel() {
    const [query, setQuery] = useState("");
    const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
    const [sortKey, setSortKey] = useState<SortKey>("placed");
    const [sortDir, setSortDir] = useState<SortDir>("desc");
    // The bounded scroll box the table virtualizes against (sticky <thead> on top).
    const scrollRef = useRef<HTMLDivElement>(null);

    // PERF UNIT-4: cursor-paged newest-first slim pages (backend UNIT-1 contract).
    // Loads ONE page (~60 slim rows) at a time and fetches the next as you scroll
    // near the end — the call-logs page no longer loads every row at once. Tab-back
    // is instant (react-query keeps the fetched pages cached + revalidates in bg).
    // Map the clicked column onto the backend sort column so sorting spans ALL
    // records (not just the loaded pages). A new sort re-keys the cursor query →
    // fresh page-0 fetch in the chosen order; the client sort below is the fallback
    // for a backend that ignores sort_by.
    const {
        data,
        isLoading,
        fetchNextPage,
        hasNextPage,
        isFetchingNextPage,
    } = useCallsInfinite({
        pageSize: 60,
        sort_by: SORT_COLUMN[sortKey],
        order: sortDir,
    });

    // Flatten the cursor pages into one row list for the virtualizer.
    const calls: CallLog[] = useMemo(
        () => (data?.pages ?? []).flatMap((p) => p.calls),
        [data]
    );
    const total = data?.pages?.[0]?.total;
    // First load (no cached page yet) shows the skeleton; a background revalidate
    // keeps the existing rows on screen.
    const loading = isLoading && calls.length === 0;

    const liveCount = useMemo(
        () => calls.filter((c) => LIVE.has(c.status)).length,
        [calls]
    );

    function onSort(k: SortKey) {
        if (k === sortKey) {
            setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        } else {
            setSortKey(k);
            // Sensible default direction: text asc, numeric/time desc.
            setSortDir(k === "lead" || k === "campaign" || k === "status" ? "asc" : "desc");
        }
    }

    // Client-side search over the already-fetched pages (no API change). When a
    // search OR a non-default sort is active we disable infinite-scroll fetching
    // (the user is narrowing / reordering what's loaded, not paging further).
    const searching = query.trim().length > 0;
    const customSort = !(sortKey === "placed" && sortDir === "desc");
    const visibleCalls = useMemo(() => {
        const q = query.trim().toLowerCase();
        let rows = calls;
        if (q) {
            rows = rows.filter(
                (c) =>
                    c.name?.toLowerCase().includes(q) ||
                    c.phone?.toLowerCase().includes(q) ||
                    c.campaign_name?.toLowerCase().includes(q)
            );
        }
        if (customSort) {
            rows = [...rows].sort((a, b) => {
                const r = cmp(
                    sortKeyValue(a, sortKey),
                    sortKeyValue(b, sortKey)
                );
                return sortDir === "asc" ? r : -r;
            });
        }
        return rows;
    }, [calls, query, sortKey, sortDir, customSort]);

    const tableHead = (
        <>
            <SortTh label="Lead" sortKey="lead" active={sortKey === "lead"} dir={sortDir} onSort={onSort} />
            <SortTh label="Campaign" sortKey="campaign" active={sortKey === "campaign"} dir={sortDir} onSort={onSort} className="max-lg:hidden" />
            <SortTh label="Status" sortKey="status" active={sortKey === "status"} dir={sortDir} onSort={onSort} />
            <SortTh label="Placed" sortKey="placed" active={sortKey === "placed"} dir={sortDir} onSort={onSort} />
            <th className="text-right max-md:hidden">Recording</th>
            <SortTh label="Duration" sortKey="duration" active={sortKey === "duration"} dir={sortDir} onSort={onSort} className="text-right [&>button]:flex-row-reverse" />
            <SortTh label="Score" sortKey="score" active={sortKey === "score"} dir={sortDir} onSort={onSort} className="text-right max-md:hidden [&>button]:flex-row-reverse" />
        </>
    );

    return (
        <>
            {selectedCallId && (
                <CallDetailModal
                    callId={selectedCallId}
                    onClose={() => setSelectedCallId(null)}
                />
            )}

            <div className="card">
                <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                    <div className="mr-auto pl-5 text-h6 max-lg:pl-3">
                        All calls
                    </div>
                    {liveCount > 0 && (
                        <span className="inline-flex items-center gap-2 h-7 pl-2.5 pr-3 mr-3 rounded-full bg-primary-02/10 text-primary-02 text-caption font-medium">
                            <span className="relative flex size-2">
                                <span className="absolute inline-flex h-full w-full rounded-full bg-primary-02 opacity-60 animate-ping" />
                                <span className="relative inline-flex size-2 rounded-full bg-primary-02" />
                            </span>
                            {liveCount} live now
                        </span>
                    )}
                    <Search
                        className="w-64 max-md:w-full max-md:ml-3"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search lead, number or campaign"
                        isGray
                    />
                </div>

                {!loading && total != null && (
                    <div className="pl-5 pt-3 text-caption text-t-tertiary tabular-nums max-lg:pl-3">
                        {query
                            ? `${visibleCalls.length} of ${calls.length} loaded`
                            : `${calls.length} of ${total} call${total === 1 ? "" : "s"}`}
                    </div>
                )}

                {/* PERF UNIT-4: bounded, sticky-header scroll box the virtualizer
                    drives. Only the ~30 visible <tr>s mount; scrolling near the end
                    fetches the next cursor page. */}
                <div
                    ref={scrollRef}
                    className="mt-3 max-h-[calc(100vh-15rem)] overflow-auto scrollbar-thin"
                >
                    {loading ? (
                        <Table cellsThead={tableHead}>
                            {[...Array(8)].map((_, i) => (
                                <tr key={i}>
                                    {[...Array(7)].map((__, j) => (
                                        <td key={j}>
                                            <div className="skeleton h-4 w-20" />
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </Table>
                    ) : visibleCalls.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="chat" className="fill-inherit" />
                            </span>
                            <div className="state-title">
                                {query ? "No matching calls" : "No calls yet"}
                            </div>
                            <div className="state-sub">
                                {query
                                    ? `Nothing matches “${query}”.`
                                    : "Run a campaign to see results here — each row opens the full transcript."}
                            </div>
                        </div>
                    ) : (
                        <table className="w-full text-body-2 [&_th]:h-14 [&_th,&_td]:pl-5 [&_th,&_td]:py-4 [&_th,&_td]:first:pl-4 [&_th,&_td]:last:pr-4 [&_th]:align-middle [&_th]:text-left [&_th]:text-overline [&_th]:uppercase [&_th]:tracking-[0.06em] [&_th]:text-t-tertiary [&_th]:font-semibold [&_thead]:border-b [&_thead]:border-s-subtle max-lg:[&_th,&_td]:first:pl-3 max-md:[&_th,&_td]:p-3 max-md:[&_th]:h-13 max-md:[&_th]:border-b max-md:[&_th]:border-s-subtle">
                            <thead className="sticky top-0 z-10 bg-b-surface2 max-md:hidden">
                                <tr>{tableHead}</tr>
                            </thead>
                            <tbody>
                                <VirtualRows
                                    items={visibleCalls}
                                    rowKey={(c) => c.id}
                                    scrollRef={scrollRef}
                                    colSpan={7}
                                    estimateRowH={73}
                                    onEndReached={
                                        searching || !hasNextPage || isFetchingNextPage
                                            ? undefined
                                            : () => fetchNextPage()
                                    }
                                    renderRow={(c) => renderCallRow(c, setSelectedCallId)}
                                />
                            </tbody>
                        </table>
                    )}
                    {isFetchingNextPage && (
                        <div className="flex items-center justify-center gap-2 py-3 text-caption text-t-tertiary">
                            <span className="size-3.5 rounded-full border-2 border-s-subtle border-t-primary-01 animate-spin" />
                            Loading more…
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}

/* ------------------------------------------------------------------ */
/* Callback status + reason derivation (ROUND5 lane-B)                 */
/* ------------------------------------------------------------------ */
/* The backend callback/retry row carries no explicit `status`; it is   */
/* derived from next_attempt_at (future = scheduled, past = due now)    */
/* and attempts vs max_attempts (exhausted). A row whose reason is       */
/* literally "callback" is an explicit in-call "call me at X" / panel    */
/* request; any OTHER reason (no_answer, busy, warm follow-up, …) is an  */
/* AI-auto-scheduled retry/follow-up. Both are surfaced in one section.  */

type CbStatus = "scheduled" | "due" | "exhausted";

function cbStatus(item: CallbackEntry): CbStatus {
    if (
        typeof item.attempts === "number" &&
        typeof item.max_attempts === "number" &&
        item.max_attempts > 0 &&
        item.attempts >= item.max_attempts
    )
        return "exhausted";
    const at = item.next_attempt_at
        ? new Date(toUTC(item.next_attempt_at)).getTime()
        : NaN;
    if (!isNaN(at) && at <= Date.now()) return "due";
    return "scheduled";
}

const CB_STATUS_META: Record<
    CbStatus,
    { label: string; variant: "info" | "warning" | "neutral" }
> = {
    scheduled: { label: "Scheduled", variant: "info" },
    due: { label: "Due now", variant: "warning" },
    exhausted: { label: "Exhausted", variant: "neutral" },
};

function CbStatusBadge({ item }: { item: CallbackEntry }) {
    const { label, variant } = CB_STATUS_META[cbStatus(item)];
    return (
        <Badge variant={variant} dot={variant === "info"}>
            {label}
        </Badge>
    );
}

// Human reason + whether this row is an AI-auto-scheduled follow-up (vs an
// explicit "callback" request the customer/agent asked for).
function cbReason(item: CallbackEntry): { label: string; auto: boolean } {
    const r = (item.reason || "").toLowerCase();
    if (r === "callback") return { label: "Callback requested", auto: false };
    const MAP: Record<string, string> = {
        no_answer: "Auto follow-up · no answer",
        busy: "Auto follow-up · line busy",
        failed: "Auto follow-up · call failed",
        voicemail: "Auto follow-up · voicemail",
        warm: "Warm-lead follow-up",
        warm_lead: "Warm-lead follow-up",
        follow_up: "Warm-lead follow-up",
    };
    return {
        label: MAP[r] || `Auto follow-up${r ? ` · ${r.replace(/_/g, " ")}` : ""}`,
        auto: true,
    };
}

// W15 — Callbacks panel (folded in from the old /callbacks page). Same Core_2
// Card + Tabs + Table chrome. Lists explicit "call me at X" callbacks AND the
// AI-auto-scheduled warm-lead / retry follow-ups the dialer queued, each with a
// derived live status (Scheduled / Due now / Exhausted). Real-time: polls every
// 20s so a callback an in-call agent just queued appears without a refresh.
function CallbacksPanel() {
    const [items, setItems] = useState<CallbackEntry[]>([]);
    const [loading, setLoading] = useState(true);
    // Default to the full follow-up view so AI-auto-scheduled warm follow-ups are
    // visible alongside explicit callback requests (the section's whole point).
    const [showAll, setShowAll] = useState(true);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    const [cancelTarget, setCancelTarget] = useState<string | null>(null);

    const VIEWS: TabsOption[] = useMemo(
        () => [
            { id: 2, name: "All follow-ups" },
            { id: 1, name: "Callback requests" },
        ],
        []
    );
    const view = showAll ? VIEWS[0] : VIEWS[1];

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(
        (silent = false) => {
            if (!silent) setLoading(true);
            getCallbacks(showAll)
                .then((r) => setItems(r.items))
                .catch(() => {})
                .finally(() => setLoading(false));
        },
        [showAll]
    );

    useEffect(() => {
        load();
        // Real-time: background refresh so a just-queued callback/follow-up appears
        // within seconds (no manual reload). Silent = keeps current rows on screen.
        const t = setInterval(() => load(true), 20000);
        return () => clearInterval(t);
    }, [load]);

    async function confirmCancel() {
        const id = cancelTarget;
        if (!id) return;
        setCancelTarget(null);
        try {
            await cancelCallback(id);
            showToast("Cancelled");
            load();
        } catch {
            showToast("Failed to cancel", false);
        }
    }

    const tableHead = (
        <>
            <th>Lead</th>
            <th>Scheduled for</th>
            <th>Reason</th>
            <th>Status</th>
            <th className="max-lg:hidden">Attempts</th>
            <th className="text-right">Action</th>
        </>
    );

    return (
        <>
            {toast && (
                <div
                    className={`mb-3 flex items-center gap-2 p-3.5 rounded-3xl text-body-2 ${
                        toast.ok
                            ? "bg-primary-02/8 text-primary-02"
                            : "bg-primary-03/8 text-primary-03"
                    }`}
                >
                    <Icon
                        name={toast.ok ? "check-circle" : "info"}
                        className={`size-4 shrink-0 ${toast.ok ? "fill-primary-02" : "fill-primary-03"}`}
                    />
                    {toast.msg}
                </div>
            )}

            <div className="card">
                <div className="flex items-center min-h-12 max-md:flex-wrap">
                    <div className="mr-auto pl-5 max-lg:pl-3">
                        <div className="text-h6">Callbacks &amp; follow-ups</div>
                        <div className="text-caption text-t-tertiary">
                            Scheduled callbacks and AI-auto-scheduled warm-lead
                            follow-ups the dialer will dial automatically
                        </div>
                    </div>
                    <Tabs items={VIEWS} value={view} setValue={(t) => setShowAll(t.id === 2)} />
                </div>

                <div className="pt-3 overflow-x-auto">
                    {loading ? (
                        <div className="px-1 max-lg:px-0">
                            <Table cellsThead={tableHead}>
                                {[...Array(4)].map((_, i) => (
                                    <TableRow key={i}>
                                        {[...Array(6)].map((__, j) => (
                                            <td key={j}>
                                                <div className="skeleton h-4 w-20" />
                                            </td>
                                        ))}
                                    </TableRow>
                                ))}
                            </Table>
                        </div>
                    ) : items.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="calendar" className="fill-inherit" />
                            </span>
                            <div className="state-title">
                                {showAll
                                    ? "No callbacks or follow-ups scheduled"
                                    : "No callback requests"}
                            </div>
                            <div className="state-sub">
                                {showAll
                                    ? "Explicit callbacks (“call me at 5pm”) and AI-auto-scheduled warm-lead follow-ups appear here the moment the dialer queues them."
                                    : "When a lead asks to be called back at a specific time, it lands here. Switch to All follow-ups to see AI-scheduled retries."}
                            </div>
                        </div>
                    ) : (
                        <div className="px-1 max-lg:px-0">
                            <Table cellsThead={tableHead}>
                                {items.map((item) => {
                                    const reason = cbReason(item);
                                    return (
                                        <TableRow key={item.id}>
                                            <td className="text-sub-title-1">
                                                <div className="truncate">
                                                    {item.name || "Unknown"}
                                                </div>
                                                <div className="text-caption text-t-tertiary td-num">
                                                    {item.phone}
                                                </div>
                                            </td>
                                            <td className="text-t-secondary whitespace-nowrap">
                                                <div>{fmtShort(item.next_attempt_at)}</div>
                                                {fmtRelative(item.next_attempt_at) && (
                                                    <div className="text-caption text-t-tertiary">
                                                        {fmtRelative(item.next_attempt_at)}
                                                    </div>
                                                )}
                                            </td>
                                            <td>
                                                <span className="text-body-2 text-t-secondary">
                                                    {reason.label}
                                                </span>
                                                {reason.auto && (
                                                    <span className="ml-2 inline-flex items-center gap-1 text-caption text-primary-01 align-middle">
                                                        <Icon
                                                            name="feather"
                                                            className="size-3 fill-primary-01"
                                                        />
                                                        AI
                                                    </span>
                                                )}
                                            </td>
                                            <td>
                                                <CbStatusBadge item={item} />
                                            </td>
                                            <td className="text-t-secondary td-num max-lg:hidden">
                                                {item.attempts} / {item.max_attempts}
                                            </td>
                                            <td className="text-right">
                                                <Button
                                                    isStroke
                                                    className="!h-9 !px-4"
                                                    onClick={() => setCancelTarget(item.id)}
                                                >
                                                    Cancel
                                                </Button>
                                            </td>
                                        </TableRow>
                                    );
                                })}
                            </Table>
                        </div>
                    )}
                </div>
            </div>

            <ConfirmDeleteModal
                open={!!cancelTarget}
                onClose={() => setCancelTarget(null)}
                onConfirm={confirmCancel}
                title="Cancel this follow-up?"
                message="This cancels the scheduled callback/retry. It won't be dialed."
                confirmLabel="Cancel it"
                cancelLabel="Keep"
            />
        </>
    );
}

/* ================================================================== */
/* WARM LEADS panel (ROUND4 B4)                                        */
/* ------------------------------------------------------------------ */
/* A "warm" lead is a contact whose AI-scored interest sits in the 40–69 */
/* band (Hot is 70+, Cold is <40). This view surfaces those mid-interest  */
/* contacts — the ones most worth a human/AI follow-up — with the call's  */
/* AI summary (lazy-fetched from the call detail) and a one-click         */
/* "Schedule follow-up" that drops a callback into the dialer queue.      */
/* Dormant-safe: no warm calls → calm empty state; summary/callback gaps  */
/* degrade quietly. Reuses the same CallDetailModal as the Calls tab.     */

const WARM_LO = 40;
const WARM_HI = 69;

type WarmSort = "score" | "recent";

function WarmLeadsPanel() {
    const [calls, setCalls] = useState<CallLog[]>([]);
    const [loading, setLoading] = useState(true);
    const [query, setQuery] = useState("");
    const [sort, setSort] = useState<WarmSort>("score");
    const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
    // Lazy per-call AI summaries keyed by call id (fetched on expand/hover-in).
    const [summaries, setSummaries] = useState<Record<string, string>>({});
    const [expanded, setExpanded] = useState<Set<string>>(new Set());
    // Per-call scheduling state: "idle" | "saving" | "done" | "error".
    const [sched, setSched] = useState<Record<string, string>>({});
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        // Pull a generous newest-first window; we filter to the warm band client-side.
        getCalls({ limit: 500, order: "desc", slim: true })
            .then((r) => !cancelled && setCalls(r.calls))
            .catch(() => !cancelled && setCalls([]))
            .finally(() => !cancelled && setLoading(false));
        return () => {
            cancelled = true;
        };
    }, []);

    // Warm band, de-duplicated to the most-recent call per phone (so a lead that
    // was dialed twice shows once, with its latest interest score + timestamp).
    const warm = useMemo(() => {
        const inBand = calls.filter(
            (c) =>
                c.interest != null &&
                c.interest >= WARM_LO &&
                c.interest <= WARM_HI
        );
        const byPhone = new Map<string, CallLog>();
        for (const c of inBand) {
            const key = c.phone || c.id;
            const prev = byPhone.get(key);
            const t = c.started_at
                ? new Date(toUTC(c.started_at)).getTime()
                : 0;
            const pt = prev?.started_at
                ? new Date(toUTC(prev.started_at)).getTime()
                : -1;
            if (!prev || t >= pt) byPhone.set(key, c);
        }
        let rows = Array.from(byPhone.values());
        const q = query.trim().toLowerCase();
        if (q) {
            rows = rows.filter(
                (c) =>
                    c.name?.toLowerCase().includes(q) ||
                    c.phone?.toLowerCase().includes(q) ||
                    c.campaign_name?.toLowerCase().includes(q)
            );
        }
        rows.sort((a, b) => {
            if (sort === "recent") {
                const at = a.started_at
                    ? new Date(toUTC(a.started_at)).getTime()
                    : 0;
                const bt = b.started_at
                    ? new Date(toUTC(b.started_at)).getTime()
                    : 0;
                return bt - at;
            }
            return (b.interest ?? 0) - (a.interest ?? 0);
        });
        return rows;
    }, [calls, query, sort]);

    // Lazy-load the AI summary for a call the first time its row is expanded.
    const loadSummary = useCallback(
        (id: string) => {
            if (summaries[id] !== undefined) return;
            setSummaries((p) => ({ ...p, [id]: "" })); // mark in-flight
            getCallDetail(id)
                .then((d) =>
                    setSummaries((p) => ({
                        ...p,
                        [id]: d.transcript?.summary || "—",
                    }))
                )
                .catch(() =>
                    setSummaries((p) => ({ ...p, [id]: "—" }))
                );
        },
        [summaries]
    );

    const toggleExpand = (id: string) => {
        setExpanded((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else {
                next.add(id);
                loadSummary(id);
            }
            return next;
        });
    };

    // Schedule a follow-up callback ~1 day out (next morning), dropped into the
    // dialer's callback queue. The scheduler clamps to the 9 AM–9 PM window +
    // skips Do-Not-Call numbers, so this is safe to fire directly from the row.
    async function scheduleFollowUp(c: CallLog) {
        setSched((p) => ({ ...p, [c.id]: "saving" }));
        const when = new Date();
        when.setDate(when.getDate() + 1);
        when.setHours(11, 0, 0, 0); // 11 AM local, inside the legal window
        try {
            await addCallback(c.phone, "", when.toISOString());
            setSched((p) => ({ ...p, [c.id]: "done" }));
            showToast(`Follow-up scheduled for ${c.name || c.phone}`);
        } catch {
            setSched((p) => ({ ...p, [c.id]: "error" }));
            showToast("Couldn't schedule — try the Callbacks tab", false);
        }
    }

    return (
        <>
            {selectedCallId && (
                <CallDetailModal
                    callId={selectedCallId}
                    onClose={() => setSelectedCallId(null)}
                />
            )}

            {toast && (
                <div
                    className={`mb-3 flex items-center gap-2 p-3.5 rounded-3xl text-body-2 ${
                        toast.ok
                            ? "bg-primary-02/8 text-primary-02"
                            : "bg-primary-03/8 text-primary-03"
                    }`}
                >
                    <Icon
                        name={toast.ok ? "check-circle" : "info"}
                        className={`size-4 shrink-0 ${
                            toast.ok ? "fill-primary-02" : "fill-primary-03"
                        }`}
                    />
                    {toast.msg}
                </div>
            )}

            <div className="card">
                <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                    <div className="mr-auto pl-5 max-lg:pl-3">
                        <div className="text-h6">Warm leads</div>
                        <div className="text-caption text-t-tertiary">
                            Interest {WARM_LO}–{WARM_HI} — mid-intent contacts
                            worth a follow-up
                        </div>
                    </div>
                    <div className="flex items-center gap-2 max-md:w-full max-md:px-3">
                        <Tabs
                            items={WARM_SORT_TABS}
                            value={
                                sort === "recent"
                                    ? WARM_SORT_TABS[1]
                                    : WARM_SORT_TABS[0]
                            }
                            setValue={(t) =>
                                setSort(t.id === 2 ? "recent" : "score")
                            }
                            classButton="!h-10 !px-4"
                        />
                        <Search
                            className="w-56 max-md:flex-1"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Search lead, number or campaign"
                            isGray
                        />
                    </div>
                </div>

                <div className="pt-3">
                    {loading ? (
                        <div className="py-16">
                            <Spinner />
                        </div>
                    ) : warm.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="chat" className="fill-inherit" />
                            </span>
                            <div className="state-title">
                                {query
                                    ? "No matching warm leads"
                                    : "No warm leads yet"}
                            </div>
                            <div className="state-sub">
                                {query
                                    ? `Nothing matches “${query}”.`
                                    : "Leads the AI scores 40–69 (interested but not committed) land here after a call — ready for a follow-up."}
                            </div>
                        </div>
                    ) : (
                        <div className="px-1 pb-2 max-lg:px-0 flex flex-col gap-2">
                            {warm.map((c) => {
                                const isOpen = expanded.has(c.id);
                                const sum = summaries[c.id];
                                const sState = sched[c.id] || "idle";
                                return (
                                    <div
                                        key={c.id}
                                        className="rounded-2xl border border-s-subtle bg-b-surface2 transition-colors hover:border-s-stroke2"
                                    >
                                        <div className="flex items-center gap-3 p-3.5 max-md:flex-wrap">
                                            <span className="flex items-center justify-center size-10 shrink-0 rounded-xl bg-primary-05/12 text-primary-05 text-caption font-semibold">
                                                {c.name
                                                    ? c.name
                                                          .trim()
                                                          .charAt(0)
                                                          .toUpperCase()
                                                    : "?"}
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => toggleExpand(c.id)}
                                                className="flex-1 min-w-0 text-left"
                                            >
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sub-title-1 truncate">
                                                        {c.name || "Unknown"}
                                                    </span>
                                                    <ScorePill
                                                        score={c.interest ?? 0}
                                                    />
                                                </div>
                                                <div className="flex items-center gap-2 text-caption text-t-tertiary">
                                                    <span className="tabular-nums">
                                                        {c.phone}
                                                    </span>
                                                    {c.campaign_name && (
                                                        <>
                                                            <span>·</span>
                                                            <span className="truncate">
                                                                {c.campaign_name}
                                                            </span>
                                                        </>
                                                    )}
                                                    {c.started_at && (
                                                        <>
                                                            <span>·</span>
                                                            <span className="whitespace-nowrap">
                                                                {fmtShort(
                                                                    c.started_at
                                                                )}
                                                            </span>
                                                        </>
                                                    )}
                                                </div>
                                            </button>
                                            <div className="flex items-center gap-2 shrink-0 max-md:w-full max-md:justify-end">
                                                <Button
                                                    isStroke
                                                    className="!h-9 !px-4"
                                                    onClick={() =>
                                                        setSelectedCallId(c.id)
                                                    }
                                                >
                                                    View call
                                                </Button>
                                                <Button
                                                    isBlack
                                                    className="!h-9 !px-4"
                                                    onClick={() =>
                                                        scheduleFollowUp(c)
                                                    }
                                                    disabled={
                                                        sState === "saving" ||
                                                        sState === "done"
                                                    }
                                                >
                                                    {sState === "saving"
                                                        ? "Scheduling…"
                                                        : sState === "done"
                                                          ? "Scheduled ✓"
                                                          : "Schedule follow-up"}
                                                </Button>
                                            </div>
                                        </div>

                                        {isOpen && (
                                            <div className="px-3.5 pb-3.5 -mt-1">
                                                <div className="p-3.5 rounded-2xl bg-b-surface1/70 dark:bg-shade-04/30">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        <Icon
                                                            name="feather"
                                                            className="size-3.5 fill-t-tertiary"
                                                        />
                                                        <div className="eyebrow">
                                                            AI summary
                                                        </div>
                                                    </div>
                                                    {sum === undefined ||
                                                    sum === "" ? (
                                                        <div className="flex items-center gap-2 text-caption text-t-tertiary">
                                                            <span className="size-3.5 rounded-full border-2 border-s-subtle border-t-primary-01 animate-spin" />
                                                            Loading summary…
                                                        </div>
                                                    ) : (
                                                        <p className="text-body-2 text-t-primary leading-relaxed">
                                                            {sum}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
            </div>
        </>
    );
}

const WARM_SORT_TABS: TabsOption[] = [
    { id: 1, name: "Hottest" },
    { id: 2, name: "Recent" },
];

/* ------------------------------------------------------------------ */
/* DO-NOT-CALL panel — ported inline from the old /suppression page    */
/* (same Core_2 Card + Table + Field + Search chrome; logic preserved).*/
/* ------------------------------------------------------------------ */

function DncReasonBadge({ reason }: { reason: string }) {
    const variant =
        reason === "opt_out_call"
            ? "danger"
            : reason === "manual"
              ? "warning"
              : reason === "api"
                ? "info"
                : "neutral";
    return <Badge variant={variant}>{(reason || "").replace(/_/g, " ")}</Badge>;
}

function DoNotCallPanel() {
    const [entries, setEntries] = useState<SuppressionEntry[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [text, setText] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const [adding, setAdding] = useState(false);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    const [delTarget, setDelTarget] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        getSuppression()
            .then((r) => {
                setEntries(r.numbers);
                setTotal(r.total);
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    async function handleAdd() {
        if (!text.trim() && !file) return;
        setAdding(true);
        try {
            const r = await addSuppression(text, file);
            showToast(`Added ${r.added} number(s). Total: ${r.total}`);
            setText("");
            setFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
            load();
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : "Failed to add", false);
        } finally {
            setAdding(false);
        }
    }

    async function confirmDelete() {
        const phone = delTarget;
        if (!phone) return;
        setDelTarget(null);
        try {
            await deleteSuppression(phone);
            showToast(`Removed ${phone}`);
            load();
        } catch {
            showToast("Delete failed", false);
        }
    }

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return entries;
        return entries.filter((e) => (e.phone || "").toLowerCase().includes(q));
    }, [entries, search]);

    return (
        <>
            {toast && (
                <div
                    className={`mb-3 flex items-center gap-2 p-3.5 rounded-3xl text-body-2 ${
                        toast.ok
                            ? "bg-primary-02/8 text-primary-02"
                            : "bg-primary-03/8 text-primary-03"
                    }`}
                >
                    <Icon
                        name={toast.ok ? "check-circle" : "info"}
                        className={`size-4 shrink-0 ${toast.ok ? "fill-primary-02" : "fill-primary-03"}`}
                    />
                    {toast.msg}
                </div>
            )}

            <div className="flex gap-3 max-lg:flex-col">
                {/* Left: suppression list */}
                <div className="flex-1 min-w-0">
                    <div className="card">
                        <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                            <div className="pl-5 text-h6 max-lg:pl-3 mr-auto">
                                Suppressed numbers
                                <span className="ml-2 text-body-2 text-t-tertiary tabular-nums">
                                    {total}
                                </span>
                            </div>
                            <Search
                                className="w-64 max-md:w-full max-md:order-3"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Search by number"
                                isGray
                            />
                        </div>

                        {loading ? (
                            <div className="py-16">
                                <Spinner />
                            </div>
                        ) : filtered.length === 0 ? (
                            <div className="flex flex-col items-center text-center py-16 px-5">
                                <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-secondary" name="block" />
                                </div>
                                <div className="text-sub-title-1 text-t-primary">
                                    {search
                                        ? "No numbers match your search"
                                        : "No suppressed numbers"}
                                </div>
                                <div className="mt-1 text-body-2 text-t-secondary max-w-80">
                                    Add numbers on the right, or they appear here
                                    automatically when a lead opts out. Suppressed
                                    numbers are never dialed.
                                </div>
                            </div>
                        ) : (
                            <div className="p-1 pt-3 max-lg:px-0">
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Phone</th>
                                            <th>Reason</th>
                                            <th>Source</th>
                                            <th>Added</th>
                                            <th className="text-right">Action</th>
                                        </>
                                    }
                                >
                                    {filtered.map((e) => (
                                        <TableRow key={e.phone}>
                                            <td className="font-medium text-t-primary tabular-nums">
                                                {e.phone}
                                            </td>
                                            <td>
                                                <DncReasonBadge reason={e.reason} />
                                            </td>
                                            <td className="text-t-secondary">
                                                {e.source || "—"}
                                            </td>
                                            <td className="text-t-secondary whitespace-nowrap">
                                                {fmtShort(e.added_at)}
                                            </td>
                                            <td className="text-right">
                                                <Button
                                                    isStroke
                                                    className="!h-9 !px-4 !text-body-2 !font-normal hover:!border-primary-03/40 hover:!text-primary-03"
                                                    onClick={() => setDelTarget(e.phone)}
                                                >
                                                    Remove
                                                </Button>
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Add numbers */}
                <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0">
                    <Card title="Add to Do-Not-Call">
                        <div className="flex flex-col gap-6 p-5 pt-3 max-lg:px-3">
                            <Field
                                label="Paste numbers (Name, Phone or bare phone per line)"
                                textarea
                                classInput="!h-32"
                                placeholder={"+919876543210\nJohn Doe, +918765432109"}
                                value={text}
                                onChange={(e) => setText(e.target.value)}
                            />

                            <div>
                                <div className="mb-4 text-button">Or upload CSV</div>
                                <div className="relative flex flex-col justify-center items-center h-32 bg-b-surface3 border border-transparent rounded-4xl overflow-hidden transition-colors hover:border-s-highlight">
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".csv,text/csv"
                                        className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                                    />
                                    <Icon className="mb-2 size-8 fill-t-secondary" name="upload" />
                                    <div className="text-body-2 text-t-secondary">
                                        {file ? (
                                            <span className="font-bold text-t-primary">
                                                {file.name}
                                            </span>
                                        ) : (
                                            <>
                                                Drop CSV, or{" "}
                                                <span className="font-bold text-t-primary">
                                                    Browse
                                                </span>
                                            </>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <Button
                                isBlack
                                className="w-full"
                                onClick={handleAdd}
                                disabled={adding || (!text.trim() && !file)}
                            >
                                {adding ? "Adding…" : "Add to Do-Not-Call"}
                            </Button>
                        </div>
                    </Card>
                </div>
            </div>

            <ConfirmDeleteModal
                open={!!delTarget}
                onClose={() => setDelTarget(null)}
                onConfirm={confirmDelete}
                title="Remove from Do-Not-Call?"
                message={
                    <>
                        Remove{" "}
                        <span className="text-t-primary tabular-nums">
                            {delTarget}
                        </span>{" "}
                        from the Do-Not-Call list? This number can be dialed
                        again.
                    </>
                }
                confirmLabel="Remove"
            />
        </>
    );
}

function ScorePill({ score }: { score: number }) {
    const variant =
        score >= 70 ? "success" : score >= 40 ? "warning" : "neutral";
    return (
        <Badge variant={variant} dot={score >= 70}>
            {score}
        </Badge>
    );
}

// One call row as a plain <tr> (so the virtualizer can attach its measurement ref —
// a native <tr> forwards refs; the <TableRow> wrapper does not). Classes mirror the
// Core_2 <TableRow> + the shared <Table> cell rules so the look is unchanged.
function renderCallRow(c: CallLog, onOpen: (id: string) => void) {
    const status = c.status ?? "";
    const isLive = LIVE.has(status);
    const recUrl = recordingUrlOf(c);
    return (
        <tr
            className="group relative cursor-pointer [&_td:not(:first-child)]:relative [&_td]:z-2 [&_td]:border-t [&_td]:border-s-subtle [&_td]:pl-5 [&_td]:py-4 [&_td]:first:pl-4 [&_td]:last:pr-4 max-lg:[&_td]:first:pl-3 max-md:[&_td]:p-3"
            onClick={() => onOpen(c.id)}
        >
            <td className="text-sub-title-1">
                <div className="flex items-center gap-3">
                    <span
                        className={`flex items-center justify-center size-9 shrink-0 rounded-xl text-caption font-semibold ${
                            isLive
                                ? "bg-primary-02/12 text-primary-02"
                                : "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                        }`}
                    >
                        {c.name ? c.name.trim().charAt(0).toUpperCase() : "?"}
                    </span>
                    <div className="min-w-0">
                        <div className="truncate">{c.name || "Unknown"}</div>
                        <div className="text-caption text-t-tertiary tabular-nums">
                            {c.phone}
                        </div>
                    </div>
                </div>
            </td>
            <td className="text-t-secondary max-lg:hidden">
                {c.campaign_name || "—"}
            </td>
            <td>
                <StatusBadge status={status} />
            </td>
            <td>
                <div className="text-t-secondary">
                    {c.started_at ? fmtShort(c.started_at) : "—"}
                </div>
                {c.started_at && fmtRelative(c.started_at) && (
                    <div className="text-caption text-t-tertiary">
                        {fmtRelative(c.started_at)}
                    </div>
                )}
            </td>
            {/* Recording — icon + clock when a recording exists, em-dash else.
                The row click opens the detail modal where it actually plays. */}
            <td className="text-right max-md:hidden">
                {recUrl ? (
                    <span className="inline-flex items-center gap-1.5 text-t-secondary tabular-nums">
                        <Icon
                            name="video"
                            className="size-3.5 fill-primary-01"
                        />
                        {fmtClock(c.duration_s)}
                    </span>
                ) : (
                    <span className="text-t-tertiary">—</span>
                )}
            </td>
            <td className="text-t-secondary td-num text-right">
                {fmtDuration(c.duration_s)}
            </td>
            <td className="text-right max-md:hidden">
                {c.interest != null ? (
                    <ScorePill score={c.interest} />
                ) : (
                    <span className="text-t-tertiary">—</span>
                )}
            </td>
        </tr>
    );
}
