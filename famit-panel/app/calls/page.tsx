"use client";

import { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import { getCalls, getCallDetail, type CallLog, type CallDetail } from "@/lib/api";

function statusBadge(status: string) {
    const map: Record<string, string> = {
        answered: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        done: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
        no_answer: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
        busy: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
        calling: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        voicemail: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
        no_human: "bg-b-surface3 text-t-secondary",
        suppressed: "bg-b-surface3 text-t-tertiary",
    };
    return (
        <span
            className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[status] || "bg-b-surface3 text-t-secondary"}`}
        >
            {status}
        </span>
    );
}

function outcomeBadge(outcome: string) {
    const map: Record<string, string> = {
        interested: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        not_interested: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
        callback: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        no_answer: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
        voicemail: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
        no_human: "bg-b-surface3 text-t-secondary",
        opt_out: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    };
    if (!outcome) return null;
    return (
        <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[outcome] || "bg-b-surface3 text-t-secondary"}`}>
            {outcome.replace(/_/g, " ")}
        </span>
    );
}

function interestBadge(interest: string) {
    const map: Record<string, string> = {
        high: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        medium: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
        low: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    };
    if (!interest) return null;
    return (
        <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[interest] || "bg-b-surface3 text-t-secondary"}`}>
            {interest} interest
        </span>
    );
}

function fmt(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

function CallDetailModal({ callId, onClose }: { callId: string; onClose: () => void }) {
    const [detail, setDetail] = useState<CallDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        getCallDetail(callId)
            .then(setDetail)
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
            .finally(() => setLoading(false));
    }, [callId]);

    // Close on backdrop click
    function handleBackdrop(e: React.MouseEvent<HTMLDivElement>) {
        if (e.target === e.currentTarget) onClose();
    }

    // Close on Escape
    useEffect(() => {
        const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
        document.addEventListener("keydown", handler);
        return () => document.removeEventListener("keydown", handler);
    }, [onClose]);

    return (
        <div
            className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
            onClick={handleBackdrop}
        >
            <div className="bg-b-surface1 rounded-3xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-xl">
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-s-subtle shrink-0">
                    <h2 className="text-h6 text-t-primary">Call Detail</h2>
                    <button
                        onClick={onClose}
                        className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-b-surface2 transition-colors text-t-secondary"
                    >
                        ×
                    </button>
                </div>

                {/* Body */}
                <div className="overflow-y-auto p-6 space-y-5">
                    {loading && (
                        <div className="flex items-center justify-center py-12 text-t-secondary gap-2">
                            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                            </svg>
                            Loading…
                        </div>
                    )}

                    {error && (
                        <div className="p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">
                            {error}
                        </div>
                    )}

                    {detail && (
                        <>
                            {/* Call info */}
                            <div className="grid grid-cols-2 gap-3 text-body-2">
                                <div>
                                    <span className="text-t-tertiary text-caption">Name</span>
                                    <div className="font-medium text-t-primary">{detail.call.name}</div>
                                </div>
                                <div>
                                    <span className="text-t-tertiary text-caption">Phone</span>
                                    <div className="text-t-primary">{detail.call.phone}</div>
                                </div>
                                <div>
                                    <span className="text-t-tertiary text-caption">Campaign</span>
                                    <div className="text-t-primary">{detail.call.campaign_name}</div>
                                </div>
                                <div>
                                    <span className="text-t-tertiary text-caption">Duration</span>
                                    <div className="text-t-primary">{detail.call.duration_s != null ? `${detail.call.duration_s}s` : "—"}</div>
                                </div>
                            </div>

                            {/* Outcome + Interest badges + opt-out */}
                            <div className="flex flex-wrap gap-2">
                                {detail.transcript?.opt_out && (
                                    <span className="inline-flex px-2 py-0.5 rounded-full text-caption font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
                                        Opted out / DND
                                    </span>
                                )}
                                {outcomeBadge(detail.transcript?.outcome ?? "")}
                                {interestBadge(detail.transcript?.interest ?? "")}
                            </div>

                            {/* AI Summary */}
                            {detail.transcript?.summary && (
                                <div className="bg-b-surface2 rounded-2xl p-4">
                                    <div className="text-caption text-t-tertiary mb-2 font-medium uppercase tracking-wide">AI Summary</div>
                                    <p className="text-body-2 text-t-primary leading-relaxed">{detail.transcript.summary}</p>
                                </div>
                            )}

                            {/* Next Action */}
                            {detail.transcript?.next_action && (
                                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-2xl p-4">
                                    <div className="text-caption text-blue-600 dark:text-blue-400 mb-1 font-medium uppercase tracking-wide">Next Action</div>
                                    <p className="text-body-2 text-t-primary">{detail.transcript.next_action}</p>
                                </div>
                            )}

                            {/* Transcript */}
                            {detail.transcript?.turns && detail.transcript.turns.length > 0 && (
                                <div>
                                    <div className="text-caption text-t-tertiary mb-3 font-medium uppercase tracking-wide">Transcript</div>
                                    <div className="space-y-3">
                                        {detail.transcript.turns.map((turn, i) => (
                                            <div
                                                key={i}
                                                className={`flex gap-3 ${turn.role === "agent" ? "flex-row" : "flex-row-reverse"}`}
                                            >
                                                <div className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-caption font-medium ${
                                                    turn.role === "agent"
                                                        ? "bg-b-surface3 text-t-secondary"
                                                        : "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400"
                                                }`}>
                                                    {turn.role === "agent" ? "A" : "L"}
                                                </div>
                                                <div className={`max-w-[80%] px-4 py-2 rounded-2xl text-body-2 ${
                                                    turn.role === "agent"
                                                        ? "bg-b-surface2 text-t-primary"
                                                        : "bg-blue-50 text-blue-900 dark:bg-blue-900/20 dark:text-blue-100"
                                                }`}>
                                                    {turn.content}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* No transcript state */}
                            {(!detail.transcript?.turns || detail.transcript.turns.length === 0) &&
                             !detail.transcript?.summary && (
                                <div className="text-center py-6 text-t-secondary text-body-2">
                                    No transcript available for this call
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
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

    // Outcome breakdown
    const breakdown = calls.reduce<Record<string, number>>((acc, c) => {
        acc[c.status] = (acc[c.status] || 0) + 1;
        return acc;
    }, {});

    return (
        <Layout title="Call Logs">
            {selectedCallId && (
                <CallDetailModal
                    callId={selectedCallId}
                    onClose={() => setSelectedCallId(null)}
                />
            )}

            {/* Outcome breakdown */}
            {calls.length > 0 && (
                <div className="grid grid-cols-4 gap-4 mb-6 max-lg:grid-cols-2 max-sm:grid-cols-2">
                    {Object.entries(breakdown).map(([status, count]) => (
                        <div
                            key={status}
                            className="card p-4 flex flex-col gap-1"
                        >
                            <div className="text-caption text-t-tertiary capitalize">
                                {status.replace(/_/g, " ")}
                            </div>
                            <div className="text-h5 text-t-primary">
                                {count}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Main table */}
            <Card title="All Calls">
                <div className="overflow-x-auto">
                    <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Campaign</th>
                                <th>Status</th>
                                <th>Started</th>
                                <th>Ended</th>
                                <th>Duration</th>
                                <th>Score</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td
                                        colSpan={8}
                                        className="py-8 text-center text-t-secondary"
                                    >
                                        <span className="inline-flex items-center gap-2">
                                            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                            </svg>
                                            Loading calls…
                                        </span>
                                    </td>
                                </tr>
                            ) : calls.length === 0 ? (
                                <tr>
                                    <td
                                        colSpan={8}
                                        className="py-12 text-center text-t-secondary"
                                    >
                                        <div className="flex flex-col items-center gap-2">
                                            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="opacity-30">
                                                <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 8.63 19.79 19.79 0 01.01 2.02 2 2 0 012 0h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 14.92z"/>
                                            </svg>
                                            <span className="text-t-tertiary">No calls yet — run a campaign to see results here</span>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                calls.map((c) => (
                                    <tr
                                        key={c.id}
                                        className="border-t border-s-subtle hover:bg-b-surface2/50 transition-colors cursor-pointer"
                                        onClick={() => setSelectedCallId(c.id)}
                                        title="Click to view transcript"
                                    >
                                        <td className="font-medium">
                                            {c.name}
                                        </td>
                                        <td className="text-t-secondary">
                                            {c.phone}
                                        </td>
                                        <td className="text-t-secondary">
                                            {c.campaign_name}
                                        </td>
                                        <td>{statusBadge(c.status)}</td>
                                        <td className="text-t-secondary">
                                            {fmt(c.started_at)}
                                        </td>
                                        <td className="text-t-secondary">
                                            {fmt(c.ended_at)}
                                        </td>
                                        <td className="text-t-secondary">
                                            {c.duration_s != null
                                                ? `${c.duration_s}s`
                                                : "—"}
                                        </td>
                                        <td>
                                            {c.interest != null ? (
                                                <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${
                                                    c.interest >= 70 ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                                    : c.interest >= 40 ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                                                    : "bg-b-surface3 text-t-secondary"
                                                }`}>{c.interest}</span>
                                            ) : "—"}
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
