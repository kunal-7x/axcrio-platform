"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import { getSuppression, addSuppression, deleteSuppression, type SuppressionEntry } from "@/lib/api";

function reasonBadge(reason: string) {
    const map: Record<string, string> = {
        upload: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        opt_out_call: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
        manual: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
        api: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    };
    return (
        <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[reason] || "bg-b-surface3 text-t-secondary"}`}>
            {reason.replace(/_/g, " ")}
        </span>
    );
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
            {toast && (
                <div className={`mb-4 p-3 rounded-2xl text-body-2 ${toast.ok ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400" : "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"}`}>
                    {toast.msg}
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Left: suppression list */}
                <div className="flex-1 min-w-0">
                    <Card title={`DND / Suppression List (${total})`}>
                        <div className="overflow-x-auto">
                            <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                                <thead>
                                    <tr>
                                        <th>Phone</th>
                                        <th>Reason</th>
                                        <th>Source</th>
                                        <th>Added</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        <tr>
                                            <td colSpan={5} className="py-8 text-center text-t-secondary">
                                                <span className="inline-flex items-center gap-2">
                                                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                                    </svg>
                                                    Loading…
                                                </span>
                                            </td>
                                        </tr>
                                    ) : entries.length === 0 ? (
                                        <tr>
                                            <td colSpan={5} className="py-12 text-center text-t-secondary">
                                                <div className="flex flex-col items-center gap-2">
                                                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="opacity-30">
                                                        <circle cx="12" cy="12" r="10"/><path d="M4.93 4.93l14.14 14.14"/>
                                                    </svg>
                                                    <span className="text-t-tertiary">No suppressed numbers yet</span>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        entries.map((e) => (
                                            <tr key={e.phone} className="border-t border-s-subtle">
                                                <td className="font-medium">{e.phone}</td>
                                                <td>{reasonBadge(e.reason)}</td>
                                                <td className="text-t-secondary text-caption">{e.source || "—"}</td>
                                                <td className="text-t-secondary">{fmtDate(e.added_at)}</td>
                                                <td>
                                                    <button
                                                        onClick={() => handleDelete(e.phone)}
                                                        className="text-caption text-red-500 hover:text-red-700 transition-colors"
                                                    >
                                                        Remove
                                                    </button>
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
                                    className="w-full h-32 px-4 py-3 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none transition-colors resize-none hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
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
