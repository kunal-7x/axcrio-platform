"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import { StatusBadge, ScoreBadge } from "@/lib/badges";
import { getLeads, addLeads, type Lead } from "@/lib/api";
import { useMe, canWrite } from "@/lib/auth";

function fmtDate(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString();
    } catch {
        return d;
    }
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

    // Real summary signals from the currently loaded set.
    const summary = useMemo(() => {
        const total = leads.length;
        const hot = leads.filter((l) => (l.score ?? 0) >= 70).length;
        const fresh = leads.filter((l) => l.status === "new").length;
        return { total, hot, fresh };
    }, [leads]);

    const toastOk = toast.startsWith("Added");

    return (
        <Layout title="Leads">
            {toast && (
                <div
                    className={`mb-4 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 border ${
                        toastOk
                            ? "bg-primary-02/8 border-primary-02/20 text-primary-02"
                            : "bg-primary-03/8 border-primary-03/20 text-primary-03"
                    }`}
                >
                    <Icon
                        name={toastOk ? "check-circle" : "info"}
                        className={`size-4 shrink-0 ${
                            toastOk ? "fill-primary-02" : "fill-primary-03"
                        }`}
                    />
                    {toast}
                </div>
            )}

            {/* Summary + filter row */}
            <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
                <div className="flex gap-3 max-sm:w-full">
                    <MiniStat label="Total" value={summary.total} />
                    <MiniStat label="Hot · 70+" value={summary.hot} tone="success" />
                    <MiniStat label="New" value={summary.fresh} tone="info" />
                </div>
                {/* Segmented hot filter */}
                <div className="inline-flex p-1 rounded-2xl bg-b-surface1 border border-s-subtle dark:bg-shade-04/40">
                    <SegBtn active={!hotOnly} onClick={() => setHotOnly(false)}>
                        All leads
                    </SegBtn>
                    <SegBtn active={hotOnly} onClick={() => setHotOnly(true)}>
                        Hot only
                    </SegBtn>
                </div>
            </div>

            <div className="flex gap-3 max-lg:flex-col">
                {/* Left: leads table */}
                <div className="flex-1 min-w-0">
                    <Card title={hotOnly ? "Hot Leads" : "All Leads"}>
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Phone</th>
                                        <th>Status</th>
                                        <th>Score</th>
                                        <th>Last Outcome</th>
                                        <th className="text-right">Added</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        [...Array(6)].map((_, i) => (
                                            <tr key={i}>
                                                {[...Array(6)].map((__, j) => (
                                                    <td key={j}>
                                                        <div className="skeleton h-4 w-16" />
                                                    </td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : leads.length === 0 ? (
                                        <tr>
                                            <td colSpan={6}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon
                                                            name="profile"
                                                            className="fill-inherit"
                                                        />
                                                    </span>
                                                    <div className="state-title">
                                                        {hotOnly
                                                            ? "No hot leads yet"
                                                            : "No leads yet"}
                                                    </div>
                                                    <div className="state-sub">
                                                        {hotOnly
                                                            ? "Leads scoring 70+ on a call will appear here."
                                                            : "Paste or upload leads on the right to get started."}
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        leads.map((l) => (
                                            <tr key={l.id}>
                                                <td className="font-medium text-t-primary">
                                                    {l.name}
                                                </td>
                                                <td className="text-t-secondary td-num">
                                                    {l.phone}
                                                </td>
                                                <td>
                                                    <StatusBadge
                                                        status={l.status}
                                                    />
                                                </td>
                                                <td>
                                                    <ScoreBadge
                                                        score={l.score}
                                                    />
                                                </td>
                                                <td className="text-t-secondary text-caption capitalize">
                                                    {l.last_outcome
                                                        ? l.last_outcome.replace(
                                                              /_/g,
                                                              " "
                                                          )
                                                        : "—"}
                                                </td>
                                                <td className="text-t-secondary td-num text-right">
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
                                    <label className="block text-button mb-2.5 text-t-primary">
                                        Paste leads
                                    </label>
                                    <textarea
                                        className="w-full h-32 px-4 py-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none transition-colors resize-none hover:border-s-highlight focus:border-s-focus placeholder:text-t-tertiary/60 bg-transparent"
                                        placeholder={
                                            "John Doe, +919876543210\nJane Smith, +918765432109"
                                        }
                                        value={text}
                                        onChange={(e) => setText(e.target.value)}
                                    />
                                    <div className="mt-1.5 text-caption text-t-tertiary">
                                        One lead per line — Name, Phone.
                                    </div>
                                </div>

                                <div className="flex items-center gap-3">
                                    <div className="h-px flex-1 bg-s-subtle" />
                                    <span className="text-caption text-t-tertiary">
                                        or
                                    </span>
                                    <div className="h-px flex-1 bg-s-subtle" />
                                </div>

                                <div>
                                    <label className="block text-button mb-2.5 text-t-primary">
                                        Upload CSV
                                    </label>
                                    <div className="relative flex flex-col items-center justify-center gap-2 h-28 rounded-2xl border border-dashed border-s-stroke2 bg-b-surface1/50 transition-colors hover:border-s-highlight cursor-pointer dark:bg-shade-04/30">
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
                                        {file ? (
                                            <>
                                                <Icon
                                                    name="check-circle"
                                                    className="size-5 fill-primary-02"
                                                />
                                                <span className="text-body-2 font-medium text-t-primary truncate max-w-[80%]">
                                                    {file.name}
                                                </span>
                                            </>
                                        ) : (
                                            <>
                                                <Icon
                                                    name="upload"
                                                    className="size-5 fill-t-tertiary"
                                                />
                                                <span className="text-body-2 text-t-secondary">
                                                    Drop CSV or{" "}
                                                    <span className="font-medium text-t-primary">
                                                        browse
                                                    </span>
                                                </span>
                                            </>
                                        )}
                                    </div>
                                </div>

                                <Button
                                    isBlack
                                    className="w-full justify-center"
                                    onClick={handleAdd}
                                    disabled={adding || (!text.trim() && !file)}
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

function MiniStat({
    label,
    value,
    tone,
}: {
    label: string;
    value: number;
    tone?: "success" | "info";
}) {
    const dot =
        tone === "success"
            ? "bg-primary-02"
            : tone === "info"
            ? "bg-primary-01"
            : "bg-shade-06";
    return (
        <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-2xl bg-b-surface2 shadow-widget dark:shadow-[inset_0_0_0_1.5px_rgba(229,229,229,0.04)]">
            <span className={`size-2 rounded-full ${dot}`} />
            <span className="text-h6 text-t-primary tabular-nums">{value}</span>
            <span className="eyebrow">{label}</span>
        </div>
    );
}

function SegBtn({
    active,
    onClick,
    children,
}: {
    active: boolean;
    onClick: () => void;
    children: React.ReactNode;
}) {
    return (
        <button
            onClick={onClick}
            className={`px-4 h-9 rounded-xl text-button transition-all ${
                active
                    ? "bg-b-surface2 text-t-primary shadow-widget"
                    : "text-t-secondary hover:text-t-primary"
            }`}
        >
            {children}
        </button>
    );
}
