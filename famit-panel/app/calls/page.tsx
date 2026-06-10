"use client";

import { useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import PageHeader from "@/components/PageHeader";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import KpiCard from "@/components/KpiCard";
import Sparkline from "@/components/Sparkline";
import { StatusBadge, OutcomeBadge, InterestBadge } from "@/lib/badges";
import {
    getCalls,
    getCallDetail,
    type CallLog,
    type CallDetail,
} from "@/lib/api";

/* ------------------------------------------------------------------ */
/* Formatting helpers                                                  */
/* ------------------------------------------------------------------ */

// Compact "Jun 9, 3:42 PM" — calmer than a full locale string in dense cells.
function fmtShort(d: string) {
    if (!d) return "—";
    const dt = new Date(d);
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

// Relative "2h ago" for recency — purely from real timestamps.
function fmtRelative(d: string) {
    if (!d) return "";
    const dt = new Date(d).getTime();
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

const ANSWERED = new Set(["answered", "done", "called", "qualified", "interested"]);
const LIVE = new Set(["calling", "in_progress"]);

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

    useEffect(() => {
        getCallDetail(callId)
            .then(setDetail)
            .catch((e) =>
                setError(e instanceof Error ? e.message : "Failed to load")
            )
            .finally(() => setLoading(false));
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
    const turnCount = t?.turns?.length ?? 0;
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
                    <div
                        className="pointer-events-none absolute inset-x-0 top-0 h-24 opacity-60"
                        style={{
                            background:
                                "radial-gradient(120% 100% at 0% 0%, rgba(42,133,255,0.10), transparent 70%)",
                        }}
                    />
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
                        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2">
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

                            {/* AI Summary */}
                            {t?.summary && (
                                <div className="p-4 rounded-2xl bg-b-surface1/70 border border-s-subtle dark:bg-shade-04/30">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Icon
                                            name="feather"
                                            className="size-3.5 fill-t-tertiary"
                                        />
                                        <div className="eyebrow">AI Summary</div>
                                    </div>
                                    <p className="text-body-2 text-t-primary leading-relaxed">
                                        {t.summary}
                                    </p>
                                </div>
                            )}

                            {/* Next Action */}
                            {t?.next_action && (
                                <div className="flex gap-3 p-4 rounded-2xl bg-primary-01/[0.06] border border-primary-01/20">
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

                            {/* Transcript */}
                            {t?.turns && t.turns.length > 0 && (
                                <div>
                                    <div className="flex items-center justify-between mb-3">
                                        <div className="eyebrow">Transcript</div>
                                        <span className="text-caption text-t-tertiary tabular-nums">
                                            {turnCount} turn
                                            {turnCount === 1 ? "" : "s"}
                                        </span>
                                    </div>
                                    <div className="relative space-y-3 pl-1">
                                        {t.turns.map((turn, i) => {
                                            const isAgent =
                                                turn.role === "agent";
                                            return (
                                                <div
                                                    key={i}
                                                    className={`flex gap-2.5 ${
                                                        isAgent
                                                            ? "flex-row"
                                                            : "flex-row-reverse"
                                                    }`}
                                                >
                                                    <span
                                                        className={`shrink-0 flex items-center justify-center size-7 rounded-full text-caption font-semibold ${
                                                            isAgent
                                                                ? "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                                                                : "bg-primary-01/12 text-primary-01"
                                                        }`}
                                                    >
                                                        {isAgent ? "AI" : "L"}
                                                    </span>
                                                    <div className="flex flex-col gap-1 max-w-[80%]">
                                                        <div
                                                            className={`px-3.5 py-2.5 rounded-2xl text-body-2 leading-relaxed ${
                                                                isAgent
                                                                    ? "bg-b-surface1 text-t-primary rounded-tl-md dark:bg-shade-04/40"
                                                                    : "bg-primary-01/10 text-t-primary rounded-tr-md"
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

export default function CallLogsPage() {
    const [calls, setCalls] = useState<CallLog[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedCallId, setSelectedCallId] = useState<string | null>(null);

    useEffect(() => {
        getCalls()
            .then((r) => setCalls(r.calls))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    /* ---- Real derived signals (no fabricated deltas) ---- */
    const m = useMemo(() => {
        const total = calls.length;
        const answered = calls.filter((c) => ANSWERED.has(c.status)).length;
        const live = calls.filter((c) => LIVE.has(c.status)).length;
        const answerRate = total > 0 ? Math.round((answered / total) * 100) : 0;

        const breakdown = calls.reduce<Record<string, number>>((acc, c) => {
            acc[c.status] = (acc[c.status] || 0) + 1;
            return acc;
        }, {});

        // Talk time only over calls that actually connected & have a duration.
        const durations = calls
            .map((c) => c.duration_s)
            .filter((d): d is number => typeof d === "number" && d > 0);
        const totalTalk = durations.reduce((a, b) => a + b, 0);
        const avgTalk = durations.length
            ? Math.round(totalTalk / durations.length)
            : 0;

        // Interest / score signals.
        const scored = calls.filter((c) => typeof c.interest === "number");
        const hot = scored.filter((c) => (c.interest as number) >= 70).length;
        const avgScore = scored.length
            ? Math.round(
                  scored.reduce((a, c) => a + (c.interest as number), 0) /
                      scored.length
              )
            : 0;

        // Calls-per-day real time series (oldest -> newest) for sparklines.
        const byDay = new Map<string, { count: number; answered: number }>();
        for (const c of calls) {
            if (!c.started_at) continue;
            const dt = new Date(c.started_at);
            if (isNaN(dt.getTime())) continue;
            const key = dt.toISOString().slice(0, 10);
            const cur = byDay.get(key) || { count: 0, answered: 0 };
            cur.count += 1;
            if (ANSWERED.has(c.status)) cur.answered += 1;
            byDay.set(key, cur);
        }
        const days = [...byDay.keys()].sort();
        const volumeSeries = days.map((d) => byDay.get(d)!.count);
        const answeredSeries = days.map((d) => byDay.get(d)!.answered);
        const activeDays = days.length;

        // Status distribution segments for the activity bar (real counts).
        const segOrder: {
            key: string;
            label: string;
            color: string;
        }[] = [
            { key: "answered", label: "Connected", color: "var(--chart-green)" },
            { key: "no_answer", label: "No answer", color: "var(--primary-05)" },
            { key: "voicemail", label: "Voicemail", color: "var(--primary-04)" },
            { key: "failed", label: "Failed", color: "var(--primary-03)" },
        ];
        const segMap: Record<string, number> = {
            answered:
                (breakdown["answered"] || 0) +
                (breakdown["done"] || 0) +
                (breakdown["called"] || 0) +
                (breakdown["qualified"] || 0) +
                (breakdown["interested"] || 0),
            no_answer: breakdown["no_answer"] || 0,
            voicemail: breakdown["voicemail"] || 0,
            failed: breakdown["failed"] || 0,
        };
        const segCovered = Object.values(segMap).reduce((a, b) => a + b, 0);
        const other = Math.max(0, total - segCovered);
        const segments = segOrder
            .map((s) => ({ ...s, value: segMap[s.key] }))
            .concat(
                other > 0
                    ? [
                          {
                              key: "other",
                              label: "Other",
                              color: "var(--chart-min)",
                              value: other,
                          },
                      ]
                    : []
            )
            .filter((s) => s.value > 0);

        return {
            total,
            answered,
            answerRate,
            live,
            totalTalk,
            avgTalk,
            hot,
            avgScore,
            scoredCount: scored.length,
            noAnswer: breakdown["no_answer"] ?? 0,
            volumeSeries,
            answeredSeries,
            activeDays,
            segments,
        };
    }, [calls]);

    const hasData = !loading && calls.length > 0;

    return (
        <Layout title="Call Logs">
            {selectedCallId && (
                <CallDetailModal
                    callId={selectedCallId}
                    onClose={() => setSelectedCallId(null)}
                />
            )}

            <PageHeader
                eyebrow="Activity"
                title="Call Logs"
                subtitle="Every call with its outcome, interest and duration — click a row to read the AI summary and full transcript."
            />

            {/* ---- Page context strip ---- */}
            {hasData && (
                <div className="flex items-center justify-between gap-4 mb-3 px-1 rise-in">
                    <div className="flex items-center gap-2 text-body-2 text-t-secondary">
                        <span className="text-t-primary font-medium tabular-nums">
                            {m.total}
                        </span>
                        call{m.total === 1 ? "" : "s"}
                        {m.activeDays > 0 && (
                            <>
                                <span className="text-t-tertiary">·</span>
                                <span>
                                    {m.activeDays} active day
                                    {m.activeDays === 1 ? "" : "s"}
                                </span>
                            </>
                        )}
                    </div>
                    {m.live > 0 && (
                        <span className="inline-flex items-center gap-2 h-7 pl-2.5 pr-3 rounded-full bg-primary-02/10 text-primary-02 text-caption font-medium">
                            <span className="relative flex size-2">
                                <span className="absolute inline-flex h-full w-full rounded-full bg-primary-02 opacity-60 animate-ping" />
                                <span className="relative inline-flex size-2 rounded-full bg-primary-02" />
                            </span>
                            {m.live} live now
                        </span>
                    )}
                </div>
            )}

            {/* ---- Hero metric cards ---- */}
            {hasData && (
                <div className="grid grid-cols-4 gap-3 mb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    <KpiCard
                        label="Total Calls"
                        value={m.total.toLocaleString()}
                        icon="chat"
                        tone="info"
                        spark={
                            m.volumeSeries.length > 1
                                ? m.volumeSeries
                                : undefined
                        }
                        sub={
                            m.activeDays > 1
                                ? `across ${m.activeDays} days`
                                : "all time"
                        }
                    />
                    <KpiCard
                        label="Answer Rate"
                        value={`${m.answerRate}%`}
                        icon="check-circle"
                        tone="success"
                        meter={m.answerRate / 100}
                        spark={
                            m.answeredSeries.length > 1
                                ? m.answeredSeries
                                : undefined
                        }
                        sub={`${m.answered.toLocaleString()} of ${m.total.toLocaleString()} connected`}
                    />
                    <KpiCard
                        label="Avg Talk Time"
                        value={fmtDuration(m.avgTalk)}
                        icon="clock"
                        tone="neutral"
                        sub={`${fmtDuration(m.totalTalk)} total on calls`}
                    />
                    <KpiCard
                        label="Hot Leads"
                        value={m.hot.toLocaleString()}
                        icon="income"
                        tone="warning"
                        meter={
                            m.scoredCount > 0 ? m.hot / m.scoredCount : undefined
                        }
                        sub={
                            m.scoredCount > 0
                                ? `avg score ${m.avgScore} · ${m.scoredCount} scored`
                                : "no scores yet"
                        }
                    />
                </div>
            )}

            {/* ---- Activity strip: volume sparkline + status mix ---- */}
            {hasData && m.volumeSeries.length > 1 && (
                <div className="grid grid-cols-3 gap-3 mb-3 max-lg:grid-cols-1">
                    <div className="surface col-span-2 max-lg:col-span-1 p-5 rise-in">
                        <div className="flex items-start justify-between gap-4 mb-4">
                            <div>
                                <div className="eyebrow mb-1">Call Volume</div>
                                <div className="text-body-2 text-t-secondary">
                                    Daily activity over the last{" "}
                                    {m.activeDays} active day
                                    {m.activeDays === 1 ? "" : "s"}
                                </div>
                            </div>
                            <span className="kpi-glyph fill-primary-01">
                                <Icon name="chart" className="fill-inherit" />
                            </span>
                        </div>
                        <Sparkline
                            data={m.volumeSeries}
                            color="var(--primary-01)"
                            width={640}
                            height={88}
                            strokeWidth={2}
                            className="w-full h-auto"
                        />
                    </div>

                    <div className="surface p-5 rise-in">
                        <div className="eyebrow mb-1">Outcome Mix</div>
                        <div className="text-body-2 text-t-secondary mb-4">
                            How {m.total} call{m.total === 1 ? "" : "s"} resolved
                        </div>
                        {/* segmented meter — real status counts */}
                        <div className="flex h-2.5 w-full rounded-full overflow-hidden bg-b-surface1 dark:bg-shade-04/60">
                            {m.segments.map((s) => (
                                <div
                                    key={s.key}
                                    title={`${s.label}: ${s.value}`}
                                    style={{
                                        width: `${(s.value / m.total) * 100}%`,
                                        background: s.color,
                                    }}
                                />
                            ))}
                        </div>
                        <div className="mt-4 space-y-2.5">
                            {m.segments.map((s) => (
                                <div
                                    key={s.key}
                                    className="flex items-center gap-2.5 text-body-2"
                                >
                                    <span
                                        className="size-2.5 shrink-0 rounded-full"
                                        style={{ background: s.color }}
                                    />
                                    <span className="text-t-secondary mr-auto">
                                        {s.label}
                                    </span>
                                    <span className="text-t-primary font-medium tabular-nums">
                                        {s.value}
                                    </span>
                                    <span className="text-t-tertiary tabular-nums w-10 text-right">
                                        {Math.round((s.value / m.total) * 100)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* ---- Main table ---- */}
            <Card title="All Calls">
                <div className="overflow-x-auto">
                    <table className="data-table is-clickable">
                        <thead>
                            <tr>
                                <th>Lead</th>
                                <th>Campaign</th>
                                <th>Status</th>
                                <th>Placed</th>
                                <th className="text-right">Duration</th>
                                <th className="text-right">Score</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                [...Array(6)].map((_, i) => (
                                    <tr key={i}>
                                        {[...Array(6)].map((__, j) => (
                                            <td key={j}>
                                                <div className="skeleton h-4 w-20" />
                                            </td>
                                        ))}
                                    </tr>
                                ))
                            ) : calls.length === 0 ? (
                                <tr>
                                    <td colSpan={6}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon
                                                    name="chat"
                                                    className="fill-inherit"
                                                />
                                            </span>
                                            <div className="state-title">
                                                No calls yet
                                            </div>
                                            <div className="state-sub">
                                                Run a campaign to see results
                                                here — each row opens the full
                                                transcript.
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                calls.map((c) => {
                                    const isLive = LIVE.has(c.status);
                                    return (
                                        <tr
                                            key={c.id}
                                            onClick={() =>
                                                setSelectedCallId(c.id)
                                            }
                                            title="View transcript"
                                        >
                                            {/* Lead identity — name + phone stacked */}
                                            <td>
                                                <div className="flex items-center gap-3">
                                                    <span
                                                        className={`flex items-center justify-center size-9 shrink-0 rounded-xl text-caption font-semibold ${
                                                            isLive
                                                                ? "bg-primary-02/12 text-primary-02"
                                                                : "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                                                        }`}
                                                    >
                                                        {c.name
                                                            ? c.name
                                                                  .trim()
                                                                  .charAt(0)
                                                                  .toUpperCase()
                                                            : "?"}
                                                    </span>
                                                    <div className="min-w-0">
                                                        <div className="font-medium text-t-primary truncate">
                                                            {c.name || "Unknown"}
                                                        </div>
                                                        <div className="text-caption text-t-tertiary tabular-nums">
                                                            {c.phone}
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="text-t-secondary">
                                                {c.campaign_name || "—"}
                                            </td>
                                            <td>
                                                <StatusBadge
                                                    status={c.status}
                                                />
                                            </td>
                                            <td>
                                                <div className="text-t-secondary">
                                                    {c.started_at
                                                        ? fmtShort(c.started_at)
                                                        : "—"}
                                                </div>
                                                {c.started_at &&
                                                    fmtRelative(
                                                        c.started_at
                                                    ) && (
                                                        <div className="text-caption text-t-tertiary">
                                                            {fmtRelative(
                                                                c.started_at
                                                            )}
                                                        </div>
                                                    )}
                                            </td>
                                            <td className="text-t-secondary td-num text-right">
                                                {fmtDuration(c.duration_s)}
                                            </td>
                                            <td className="text-right">
                                                {c.interest != null ? (
                                                    <ScorePill
                                                        score={c.interest}
                                                    />
                                                ) : (
                                                    <span className="text-t-tertiary">
                                                        —
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>
        </Layout>
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
