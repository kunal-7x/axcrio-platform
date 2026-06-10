"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import PageHeader from "@/components/PageHeader";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";

import { getSuppression, addSuppression, deleteSuppression, type SuppressionEntry } from "@/lib/api";

// DND reasons -> ONE badge language (token-based, no raw colors).
function ReasonBadge({ reason }: { reason: string }) {
    const variant =
        reason === "opt_out_call" ? "danger"
        : reason === "manual" ? "warning"
        : reason === "api" ? "info"
        : "neutral";
    return <Badge variant={variant}>{reason.replace(/_/g, " ")}</Badge>;
}

function fmtDate(d: string) {
    if (!d) return "—";
    try { return new Date(d).toLocaleDateString(); } catch { return d; }
}

export default function SuppressionPage() {
    const [entries, setEntries] = useState<SuppressionEntry[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [text, setText] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const [adding, setAdding] = useState(false);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        getSuppression()
            .then((r) => { setEntries(r.numbers); setTotal(r.total); })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

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

    async function handleDelete(phone: string) {
        if (!confirm(`Remove ${phone} from DND list?`)) return;
        try {
            await deleteSuppression(phone);
            showToast(`Removed ${phone}`);
            load();
        } catch {
            showToast("Delete failed", false);
        }
    }

    return (
        <Layout title="Do-Not-Call">
            <PageHeader
                eyebrow="Activity"
                title="Do-Not-Call"
                subtitle="Numbers on this suppression list are never dialed. Add them by paste or CSV; opt-outs land here automatically."
            />
            {toast && (
                <div className={`toast ${toast.ok ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Left: suppression list */}
                <div className="flex-1 min-w-0">
                    <Card title={`DND / Suppression List (${total})`}>
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Phone</th>
                                        <th>Reason</th>
                                        <th>Source</th>
                                        <th>Added</th>
                                        <th className="text-right">Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        [...Array(4)].map((_, i) => (
                                            <tr key={i}>
                                                {[...Array(5)].map((__, j) => (
                                                    <td key={j}><div className="skeleton h-4 w-20" /></td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : entries.length === 0 ? (
                                        <tr>
                                            <td colSpan={5}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon name="block" className="fill-inherit" />
                                                    </span>
                                                    <div className="state-title">No suppressed numbers</div>
                                                    <div className="state-sub">
                                                        Add numbers on the right, or they&apos;ll appear here automatically when a lead opts out.
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        entries.map((e) => (
                                            <tr key={e.phone}>
                                                <td className="font-medium text-t-primary td-num">{e.phone}</td>
                                                <td><ReasonBadge reason={e.reason} /></td>
                                                <td className="text-t-secondary text-caption">{e.source || "—"}</td>
                                                <td className="text-t-secondary whitespace-nowrap">{fmtDate(e.added_at)}</td>
                                                <td>
                                                    <div className="flex justify-end">
                                                        <button
                                                            onClick={() => handleDelete(e.phone)}
                                                            className="action hover:!text-primary-03 hover:!border-primary-03/30"
                                                        >
                                                            Remove
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
                </div>

                {/* Right: Add numbers */}
                <div className="w-96 max-lg:w-full shrink-0">
                    <Card title="Add to DND List">
                        <div className="px-5 pb-5 space-y-4">
                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Paste numbers (Name, Phone or bare phone per line)
                                </label>
                                <textarea
                                    className="input-base w-full h-32 px-4 py-3 rounded-2xl text-body-2 resize-none"
                                    placeholder={"+919876543210\nJohn Doe, +918765432109"}
                                    value={text}
                                    onChange={(e) => setText(e.target.value)}
                                />
                            </div>

                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Or upload CSV
                                </label>
                                <div className="relative flex flex-col justify-center items-center h-24 bg-b-surface3 border border-transparent rounded-3xl overflow-hidden transition-colors hover:border-s-highlight cursor-pointer">
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".csv,text/csv"
                                        className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                                    />
                                    <div className="text-body-2 text-t-secondary">
                                        {file ? (
                                            <span className="font-bold text-t-primary">{file.name}</span>
                                        ) : (
                                            <>Drop CSV or <span className="font-bold text-t-primary">Browse</span></>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <Button
                                isBlack
                                className="w-full justify-center"
                                onClick={handleAdd}
                                disabled={adding || (!text.trim() && !file)}
                            >
                                {adding ? "Adding…" : "Add to DND"}
                            </Button>
                        </div>
                    </Card>
                </div>
            </div>
        </Layout>
    );
}
