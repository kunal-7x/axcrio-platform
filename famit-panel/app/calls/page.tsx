"use client";

import { useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import { StatusBadge, OutcomeBadge, InterestBadge } from "@/lib/badges";
import {
    getCalls,
    getCallDetail,
    type CallLog,
    type CallDetail,
} from "@/lib/api";

function fmt(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

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

    return (
        <div
            className="fixed inset-0 z-50 bg-shade-01/50 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={handleBackdrop}
        >
            <div className="surface w-full max-w-2xl max-h-[90vh] flex flex-col rise-in">
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-s-subtle shrink-0">
                    <div className="flex items-center gap-3">
                        <span className="flex items-center justify-center size-9 rounded-xl bg-b-surface1 fill-t-secondary dark:bg-shade-04/60">
                            <Icon name="chat" className="size-4 fill-inherit" />
                        </span>
                        <h2 className="text-h6 text-t-primary">Call Detail</h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="flex items-center justify-center size-8 rounded-full text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary dark:hover:bg-shade-04/60"
                        aria-label="Close"
                    >
                        <Icon name="close" className="size-4 fill-current" />
                    </button>
                </div>

                {/* Body */}
                <div className="overflow-y-auto p-5 space-y-5 scrollbar-thin">
                    {loading && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-3">
                                <div className="skeleton h-12" />
                                <div className="skeleton h-12" />
                                <div className="skeleton h-12" />
                                <div className="skeleton h-12" />
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
                            {/* Call info grid */}
                            <div className="grid grid-cols-2 gap-3">
                                <InfoCell label="Name" value={detail.call.name} strong />
                                <InfoCell
                                    label="Phone"
                                    value={detail.call.phone}
                                    mono
                                />
                                <InfoCell
                                    label="Campaign"
                                    value={detail.call.campaign_name}
                                />
                                <InfoCell
                                    label="Duration"
                                    value={
                                        detail.call.duration_s != null
                                            ? `${detail.call.duration_s}s`
                                            : "—"
                                    }
                                    mono
                                />
                            </div>

                            {/* Outcome / interest / opt-out */}
                            <div className="flex flex-wrap gap-2">
                                {detail.transcript?.opt_out && (
                                    <Badge variant="danger">Opted out / DND</Badge>
                                )}
                                <OutcomeBadge
                                    outcome={detail.transcript?.outcome ?? ""}
                                />
                                <InterestBadge
                                    interest={detail.transcript?.interest ?? ""}
                                />
                            </div>

                            {/* AI Summary */}
                            {detail.transcript?.summary && (
                                <div className="p-4 rounded-2xl bg-b-surface1/70 border border-s-subtle dark:bg-shade-04/30">
                                    <div className="eyebrow mb-2">AI Summary</div>
                                    <p className="text-body-2 text-t-primary leading-relaxed">
                                        {detail.transcript.summary}
                                    </p>
                                </div>
                            )}

                            {/* Next Action */}
                            {detail.transcript?.next_action && (
                                <div className="p-4 rounded-2xl bg-primary-01/6 border border-primary-01/20">
                                    <div className="eyebrow mb-1 text-primary-01">
                                        Next Action
                                    </div>
                                    <p className="text-body-2 text-t-primary">
                                        {detail.transcript.next_action}
                                    </p>
                                </div>
                            )}

                            {/* Transcript */}
                            {detail.transcript?.turns &&
                                detail.transcript.turns.length > 0 && (
                                    <div>
                                        <div className="eyebrow mb-3">
                                            Transcript
                                        </div>
                                        <div className="space-y-3">
                                            {detail.transcript.turns.map(
                                                (turn, i) => {
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
                                                                className={`shrink-0 flex items-center justify-center size-7 rounded-full text-caption font-medium ${
                                                                    isAgent
                                                                        ? "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                                                                        : "bg-primary-01/12 text-primary-01"
                                                                }`}
                                                            >
                                                                {isAgent
                                                                    ? "AI"
                                                                    : "L"}
                                                            </span>
                                                            <div
                                                                className={`max-w-[78%] px-3.5 py-2.5 rounded-2xl text-body-2 ${
                                                                    isAgent
                                                                        ? "bg-b-surface1 text-t-primary dark:bg-shade-04/40"
                                                                        : "bg-primary-01/10 text-t-primary"
                                                                }`}
                                                            >
                                                                {turn.content}
                                                            </div>
                                                        </div>
                                                    );
                                                }
                                            )}
                                        </div>
                                    </div>
                                )}

                            {/* No transcript */}
                            {(!detail.transcript?.turns ||
                                detail.transcript.turns.length === 0) &&
                                !detail.transcript?.summary && (
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

function InfoCell({
    label,
    value,
    strong,
    mono,
}: {
    label: string;
    value: React.ReactNode;
    strong?: boolean;
    mono?: boolean;
}) {
    return (
        <div className="flex flex-col gap-1 p-3 rounded-2xl bg-b-surface1/60 dark:bg-shade-04/30">
            <span className="eyebrow">{label}</span>
            <span
                className={`text-body-2 text-t-primary ${
                    strong ? "font-medium" : ""
                } ${mono ? "tabular-nums" : ""}`}
            >
                {value}
            </span>
        </div>
    );
}

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

    // Real derived signals from the loaded calls.
    const summary = useMemo(() => {
        const total = calls.length;
        const answered = calls.filter(
            (c) => c.status === "answered" || c.status === "done"
        ).length;
        const breakdown = calls.reduce<Record<string, number>>((acc, c) => {
            acc[c.status] = (acc[c.status] || 0) + 1;
            return acc;
        }, {});
        const answerRate = total > 0 ? Math.round((answered / total) * 100) : 0;
        return { total, answered, answerRate, breakdown };
    }, [calls]);

    return (
        <Layout title="Call Logs">
            {selectedCallId && (
                <CallDetailModal
                    callId={selectedCallId}
                    onClose={() => setSelectedCallId(null)}
                />
            )}

            {/* Summary KPIs */}
            {!loading && calls.length > 0 && (
                <div className="grid grid-cols-4 gap-3 mb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    <MetricTile
                        label="Total Calls"
                        value={summary.total}
                        tone="info"
                    />
                    <MetricTile
                        label="Answered"
                        value={summary.answered}
                        tone="success"
                    />
                    <MetricTile
                        label="Answer Rate"
                        value={`${summary.answerRate}%`}
                        tone="success"
                        meter={summary.answerRate / 100}
                    />
                    <MetricTile
                        label="No Answer"
                        value={summary.breakdown["no_answer"] ?? 0}
                        tone="warning"
                    />
                </div>
            )}

            {/* Main table */}
            <Card title="All Calls">
                <div className="overflow-x-auto">
                    <table className="data-table is-clickable">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Campaign</th>
                                <th>Status</th>
                                <th>Started</th>
                                <th>Ended</th>
                                <th className="text-right">Duration</th>
                                <th className="text-right">Score</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                [...Array(6)].map((_, i) => (
                                    <tr key={i}>
                                        {[...Array(8)].map((__, j) => (
                                            <td key={j}>
                                                <div className="skeleton h-4 w-16" />
                                            </td>
                                        ))}
                                    </tr>
                                ))
                            ) : calls.length === 0 ? (
                                <tr>
                                    <td colSpan={8}>
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
                                calls.map((c) => (
                                    <tr
                                        key={c.id}
                                        onClick={() => setSelectedCallId(c.id)}
                                        title="View transcript"
                                    >
                                        <td className="font-medium text-t-primary">
                                            {c.name}
                                        </td>
                                        <td className="text-t-secondary td-num">
                                            {c.phone}
                                        </td>
                                        <td className="text-t-secondary">
                                            {c.campaign_name}
                                        </td>
                                        <td>
                                            <StatusBadge status={c.status} />
                                        </td>
                                        <td className="text-t-secondary">
                                            {fmt(c.started_at)}
                                        </td>
                                        <td className="text-t-secondary">
                                            {fmt(c.ended_at)}
                                        </td>
                                        <td className="text-t-secondary td-num text-right">
                                            {c.duration_s != null
                                                ? `${c.duration_s}s`
                                                : "—"}
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
                                ))
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
    return <Badge variant={variant}>{score}</Badge>;
}

function MetricTile({
    label,
    value,
    tone,
    meter,
}: {
    label: string;
    value: number | string;
    tone: "info" | "success" | "warning" | "neutral";
    meter?: number;
}) {
    const toneVar =
        tone === "success"
            ? "var(--chart-green)"
            : tone === "warning"
            ? "var(--primary-05)"
            : tone === "info"
            ? "var(--primary-01)"
            : "var(--chart-min)";
    return (
        <div className="kpi rise-in">
            <div className="eyebrow">{label}</div>
            <div className="kpi-value">{value}</div>
            {meter != null && (
                <div className="meter">
                    <div
                        className="meter-fill"
                        style={{
                            width: `${Math.min(100, meter * 100)}%`,
                            background: toneVar,
                        }}
                    />
                </div>
            )}
        </div>
    );
}
