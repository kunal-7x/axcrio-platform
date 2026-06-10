"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import PageHeader from "@/components/PageHeader";
import Icon from "@/components/Icon";
import { StatusBadge } from "@/lib/badges";
import { getCallbacks, cancelCallback, type CallbackEntry } from "@/lib/api";

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
            <PageHeader
                eyebrow="Activity"
                title="Callbacks & Retries"
                subtitle="Every scheduled callback and automatic retry, with its reason, attempt count and next dial time."
            />
            {toast && (
                <div className={`toast ${toast.ok ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
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
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Campaign</th>
                                <th>Scheduled For</th>
                                <th>Reason</th>
                                <th>Attempts</th>
                                <th className="text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                [...Array(4)].map((_, i) => (
                                    <tr key={i}>
                                        {[...Array(7)].map((__, j) => (
                                            <td key={j}><div className="skeleton h-4 w-20" /></td>
                                        ))}
                                    </tr>
                                ))
                            ) : items.length === 0 ? (
                                <tr>
                                    <td colSpan={7}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name="calendar" className="fill-inherit" />
                                            </span>
                                            <div className="state-title">No scheduled callbacks</div>
                                            <div className="state-sub">
                                                Callbacks and automatic retries scheduled by the dialer will appear here.
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                items.map((item) => (
                                    <tr key={item.id}>
                                        <td className="font-medium text-t-primary">{item.name || "—"}</td>
                                        <td className="text-t-secondary td-num">{item.phone}</td>
                                        <td className="text-t-secondary text-caption">{item.campaign_id}</td>
                                        <td className="text-t-secondary whitespace-nowrap">{fmt(item.next_attempt_at)}</td>
                                        <td><StatusBadge status={item.reason} /></td>
                                        <td className="text-t-secondary td-num">
                                            {item.attempts} / {item.max_attempts}
                                        </td>
                                        <td>
                                            <div className="flex justify-end">
                                                <button
                                                    onClick={() => handleCancel(item.id)}
                                                    className="action hover:!text-primary-03 hover:!border-primary-03/30"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
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
