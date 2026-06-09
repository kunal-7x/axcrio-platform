"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import { getCallbacks, cancelCallback, type CallbackEntry } from "@/lib/api";

function reasonBadge(reason: string) {
    const map: Record<string, string> = {
        callback: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        no_answer: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
        voicemail: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
        busy: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
    };
    return (
        <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[reason] || "bg-b-surface3 text-t-secondary"}`}>
            {reason.replace(/_/g, " ")}
        </span>
    );
}

function fmt(d: string) {
    if (!d) return "—";
    try { return new Date(d).toLocaleString(); } catch { return d; }
}

export default function CallbacksPage() {
    const [items, setItems] = useState<CallbackEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [showAll, setShowAll] = useState(false);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        getCallbacks(showAll)
            .then((r) => setItems(r.items))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [showAll]);

    useEffect(() => { load(); }, [load]);

    async function handleCancel(id: string) {
        if (!confirm("Cancel this scheduled callback/retry?")) return;
        try {
            await cancelCallback(id);
            showToast("Cancelled");
            load();
        } catch {
            showToast("Failed to cancel", false);
        }
    }

    return (
        <Layout title="Callbacks">
            {toast && (
                <div className={`mb-4 p-3 rounded-2xl text-body-2 ${toast.ok ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400" : "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"}`}>
                    {toast.msg}
                </div>
            )}

            <div className="flex items-center justify-between mb-4">
                <div className="text-body-2 text-t-secondary">
                    {showAll ? "Showing all retries + callbacks" : "Showing callbacks only"}
                </div>
                <label className="flex items-center gap-2 cursor-pointer text-body-2 text-t-primary">
                    <input
                        type="checkbox"
                        className="w-4 h-4 rounded"
                        checked={showAll}
                        onChange={(e) => setShowAll(e.target.checked)}
                    />
                    Show all retries
                </label>
            </div>

            <Card title={`Scheduled Callbacks & Retries (${items.length})`}>
                <div className="overflow-x-auto">
                    <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Campaign</th>
                                <th>Scheduled For</th>
                                <th>Reason</th>
                                <th>Attempts</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan={7} className="py-8 text-center text-t-secondary">
                                        <span className="inline-flex items-center gap-2">
                                            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                            </svg>
                                            Loading…
                                        </span>
                                    </td>
                                </tr>
                            ) : items.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="py-12 text-center text-t-secondary">
                                        <div className="flex flex-col items-center gap-2">
                                            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="opacity-30">
                                                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
                                            </svg>
                                            <span className="text-t-tertiary">No scheduled callbacks yet</span>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                items.map((item) => (
                                    <tr key={item.id} className="border-t border-s-subtle">
                                        <td className="font-medium">{item.name || "—"}</td>
                                        <td className="text-t-secondary">{item.phone}</td>
                                        <td className="text-t-secondary text-caption">{item.campaign_id}</td>
                                        <td className="text-t-secondary">{fmt(item.next_attempt_at)}</td>
                                        <td>{reasonBadge(item.reason)}</td>
                                        <td className="text-t-secondary">
                                            {item.attempts} / {item.max_attempts}
                                        </td>
                                        <td>
                                            <button
                                                onClick={() => handleCancel(item.id)}
                                                className="text-caption text-red-500 hover:text-red-700 transition-colors"
                                            >
                                                Cancel
                                            </button>
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
