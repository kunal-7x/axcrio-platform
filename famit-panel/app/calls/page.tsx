"use client";

import { useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Search from "@/components/Search";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
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
    const [query, setQuery] = useState("");
    const [selectedCallId, setSelectedCallId] = useState<string | null>(null);

    useEffect(() => {
        getCalls()
            .then((r) => setCalls(r.calls))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const liveCount = useMemo(
        () => calls.filter((c) => LIVE.has(c.status)).length,
        [calls]
    );

    // Client-side search over the loaded set (no API change).
    const visibleCalls = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return calls;
        return calls.filter(
            (c) =>
                c.name?.toLowerCase().includes(q) ||
                c.phone?.toLowerCase().includes(q) ||
                c.campaign_name?.toLowerCase().includes(q)
        );
    }, [calls, query]);

    const tableHead = (
        <>
            <th>Lead</th>
            <th className="max-lg:hidden">Campaign</th>
            <th>Status</th>
            <th>Placed</th>
            <th className="text-right">Duration</th>
            <th className="text-right max-md:hidden">Score</th>
        </>
    );

    return (
        <Layout title="Call logs">
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

                <div className="pt-3 overflow-x-auto">
                    {loading ? (
                        <Table cellsThead={tableHead}>
                            {[...Array(6)].map((_, i) => (
                                <TableRow key={i}>
                                    {[...Array(6)].map((__, j) => (
                                        <td key={j}>
                                            <div className="skeleton h-4 w-20" />
                                        </td>
                                    ))}
                                </TableRow>
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
                        <Table cellsThead={tableHead}>
                            {visibleCalls.map((c) => {
                                const isLive = LIVE.has(c.status);
                                return (
                                    <TableRow
                                        key={c.id}
                                        className="cursor-pointer"
                                        onClick={() => setSelectedCallId(c.id)}
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
                                                    {c.name
                                                        ? c.name
                                                              .trim()
                                                              .charAt(0)
                                                              .toUpperCase()
                                                        : "?"}
                                                </span>
                                                <div className="min-w-0">
                                                    <div className="truncate">
                                                        {c.name || "Unknown"}
                                                    </div>
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
                                            <StatusBadge status={c.status} />
                                        </td>
                                        <td>
                                            <div className="text-t-secondary">
                                                {c.started_at
                                                    ? fmtShort(c.started_at)
                                                    : "—"}
                                            </div>
                                            {c.started_at &&
                                                fmtRelative(c.started_at) && (
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
                                        <td className="text-right max-md:hidden">
                                            {c.interest != null ? (
                                                <ScorePill score={c.interest} />
                                            ) : (
                                                <span className="text-t-tertiary">
                                                    —
                                                </span>
                                            )}
                                        </td>
                                    </TableRow>
                                );
                            })}
                        </Table>
                    )}
                </div>
            </div>
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
