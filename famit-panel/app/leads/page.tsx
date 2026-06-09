"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import { getLeads, addLeads, type Lead } from "@/lib/api";
import { useMe, canWrite } from "@/lib/auth";

function scoreBadge(score?: number) {
    if (score == null) return null;
    const cls = score >= 70
        ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
        : score >= 40
        ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
        : "bg-b-surface3 text-t-secondary";
    const label = score >= 70 ? `${score} hot` : String(score);
    return (
        <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${cls}`}>
            {label}
        </span>
    );
}

function fmtDate(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString();
    } catch {
        return d;
    }
}

function statusBadge(status: string) {
    const map: Record<string, string> = {
        new: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
        called: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
    };
    return (
        <span
            className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[status] || "bg-b-surface3 text-t-secondary"}`}
        >
            {status}
        </span>
    );
}

export default function LeadsPage() {
    const [leads, setLeads] = useState<Lead[]>([]);
    const [loading, setLoading] = useState(true);
    const [text, setText] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const [adding, setAdding] = useState(false);
    const [toast, setToast] = useState("");
    const [hotOnly, setHotOnly] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const { me } = useMe();
    const writable = canWrite(me);

    const loadLeads = useCallback(() => {
        setLoading(true);
        getLeads(hotOnly ? { hot: true } : undefined)
            .then((r) => setLeads(r.leads))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [hotOnly]);

    useEffect(() => {
        loadLeads();
    }, [loadLeads]);

    async function handleAdd() {
        setAdding(true);
        setToast("");
        try {
            const result = await addLeads(text, file);
            setToast(`Added ${result.added} leads. Total: ${result.total}`);
            setText("");
            setFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
            loadLeads();
        } catch (e: unknown) {
            setToast(e instanceof Error ? e.message : "Failed to add leads");
        } finally {
            setAdding(false);
        }
    }

    return (
        <Layout title="Leads">
            {toast && (
                <div
                    className={`mb-4 p-3 rounded-2xl text-body-2 ${toast.startsWith("Added") ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400" : "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"}`}
                >
                    {toast}
                </div>
            )}

            {/* Hot only toggle */}
            <div className="flex items-center gap-3 mb-4">
                <label className="flex items-center gap-2 cursor-pointer text-body-2 text-t-primary">
                    <input
                        type="checkbox"
                        className="w-4 h-4 rounded"
                        checked={hotOnly}
                        onChange={(e) => setHotOnly(e.target.checked)}
                    />
                    Hot leads only (score ≥ 70)
                </label>
            </div>

            <div className="flex gap-6 max-lg:flex-col">
                {/* Left: leads table */}
                <div className="flex-1 min-w-0">
                    <Card title={hotOnly ? "Hot Leads" : "All Leads"}>
                        <div className="overflow-x-auto">
                            <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Phone</th>
                                        <th>Status</th>
                                        <th>Score</th>
                                        <th>Last Outcome</th>
                                        <th>Added</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        <tr>
                                            <td
                                                colSpan={6}
                                                className="py-8 text-center text-t-secondary"
                                            >
                                                Loading…
                                            </td>
                                        </tr>
                                    ) : leads.length === 0 ? (
                                        <tr>
                                            <td
                                                colSpan={6}
                                                className="py-8 text-center text-t-secondary"
                                            >
                                                {hotOnly ? "No hot leads yet" : "No leads yet"}
                                            </td>
                                        </tr>
                                    ) : (
                                        leads.map((l) => (
                                            <tr
                                                key={l.id}
                                                className="border-t border-s-subtle"
                                            >
                                                <td className="font-medium">
                                                    {l.name}
                                                </td>
                                                <td className="text-t-secondary">
                                                    {l.phone}
                                                </td>
                                                <td>
                                                    {statusBadge(l.status)}
                                                </td>
                                                <td>
                                                    {scoreBadge(l.score)}
                                                </td>
                                                <td className="text-t-secondary text-caption">
                                                    {l.last_outcome ? l.last_outcome.replace(/_/g, " ") : "—"}
                                                </td>
                                                <td className="text-t-secondary">
                                                    {fmtDate(l.added_at)}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>

                {/* Right: Add leads (hidden for read-only agents) */}
                {writable && (
                <div className="w-96 max-lg:w-full shrink-0">
                    <Card title="Add Leads">
                        <div className="px-5 pb-5 space-y-4">
                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Paste leads (Name, Phone per line)
                                </label>
                                <textarea
                                    className="w-full h-32 px-4 py-3 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none transition-colors resize-none hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
                                    placeholder={"John Doe, +919876543210\nJane Smith, +918765432109"}
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
                                        onChange={(e) =>
                                            setFile(
                                                e.target.files?.[0] ?? null
                                            )
                                        }
                                    />
                                    <div className="text-body-2 text-t-secondary">
                                        {file ? (
                                            <span className="font-bold text-t-primary">
                                                {file.name}
                                            </span>
                                        ) : (
                                            <>
                                                Drop CSV or{" "}
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
                                className="w-full justify-center"
                                onClick={handleAdd}
                                disabled={
                                    adding || (!text.trim() && !file)
                                }
                            >
                                {adding ? "Adding…" : "Add Leads"}
                            </Button>
                        </div>
                    </Card>
                </div>
                )}
            </div>
        </Layout>
    );
}
