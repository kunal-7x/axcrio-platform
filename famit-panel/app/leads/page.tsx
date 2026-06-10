"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import PageHeader from "@/components/PageHeader";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import KpiCard from "@/components/KpiCard";
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
    const [query, setQuery] = useState("");
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

    // ── Real summary signals from the currently loaded set ──────────────
    // All derived from the leads actually returned by /leads — never a
    // fabricated prior-period delta (no such data exists in the API).
    const summary = useMemo(() => {
        const total = leads.length;
        const scored = leads.filter((l) => l.score != null);
        const hot = leads.filter((l) => (l.score ?? 0) >= 70).length;
        const warm = leads.filter(
            (l) => (l.score ?? 0) >= 40 && (l.score ?? 0) < 70
        ).length;
        const fresh = leads.filter((l) => l.status === "new").length;
        const contacted = leads.filter(
            (l) => !!l.last_call_at || l.status !== "new"
        ).length;
        const avgScore =
            scored.length > 0
                ? Math.round(
                      scored.reduce((a, l) => a + (l.score ?? 0), 0) /
                          scored.length
                  )
                : null;

        // Score distribution histogram (10 buckets, 0-9 … 90-100) over the
        // scored leads — a real inline shape, not a faked time series.
        const dist = new Array(10).fill(0) as number[];
        for (const l of scored) {
            const s = Math.max(0, Math.min(100, l.score ?? 0));
            const b = Math.min(9, Math.floor(s / 10));
            dist[b] += 1;
        }

        return {
            total,
            hot,
            warm,
            fresh,
            contacted,
            scoredCount: scored.length,
            avgScore,
            dist,
            hotRatio: total > 0 ? hot / total : 0,
            contactRatio: total > 0 ? contacted / total : 0,
        };
    }, [leads]);

    // Client-side search over the already-fetched set (no API change).
    const visibleLeads = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return leads;
        return leads.filter(
            (l) =>
                l.name?.toLowerCase().includes(q) ||
                l.phone?.toLowerCase().includes(q)
        );
    }, [leads, query]);

    const toastOk = toast.startsWith("Added");

    return (
        <Layout title="Leads">
            <PageHeader
                eyebrow="Outreach"
                title="Leads"
                subtitle="Your lead list with live scores — hot leads (70+) rise to the top automatically after each call."
            />
            {toast && (
                <div
                    className={`mb-4 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 border rise-in ${
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

            {/* ── Hero KPI row — big numbers + real meters / distribution ── */}
            <div className="grid grid-cols-4 gap-3 mb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <KpiCard
                    label={hotOnly ? "Hot Leads" : "Total Leads"}
                    value={loading ? "—" : summary.total}
                    icon="profile"
                    tone="info"
                    sub={
                        loading
                            ? undefined
                            : summary.scoredCount > 0
                            ? `${summary.scoredCount} scored on a call`
                            : "Awaiting first calls"
                    }
                    style={{ animationDelay: "0ms" }}
                />
                <KpiCard
                    label="Hot · 70+"
                    value={loading ? "—" : summary.hot}
                    icon="star-fill"
                    tone="success"
                    sub={
                        loading || summary.total === 0 ? undefined : (
                            <span className="text-primary-02">
                                {Math.round(summary.hotRatio * 100)}% of all leads
                            </span>
                        )
                    }
                    meter={loading ? null : summary.hotRatio}
                    style={{ animationDelay: "60ms" }}
                />
                <KpiCard
                    label="Avg Score"
                    value={
                        loading
                            ? "—"
                            : summary.avgScore != null
                            ? summary.avgScore
                            : "—"
                    }
                    icon="chart"
                    tone="warning"
                    sub={
                        loading
                            ? undefined
                            : summary.avgScore == null
                            ? "No scored leads yet"
                            : summary.warm > 0
                            ? `${summary.warm} warm · ${summary.hot} hot`
                            : `${summary.hot} hot · 0-100 scale`
                    }
                    meter={
                        loading || summary.avgScore == null
                            ? null
                            : summary.avgScore / 100
                    }
                    style={{ animationDelay: "120ms" }}
                />
                <KpiCard
                    label="Contacted"
                    value={loading ? "—" : summary.contacted}
                    icon="chat"
                    tone="neutral"
                    sub={
                        loading || summary.total === 0
                            ? undefined
                            : `${summary.fresh} new · ${Math.round(
                                  summary.contactRatio * 100
                              )}% reached`
                    }
                    meter={loading ? null : summary.contactRatio}
                    style={{ animationDelay: "180ms" }}
                />
            </div>

            <div className="flex gap-3 max-lg:flex-col">
                {/* ── Left: leads workspace ──────────────────────────── */}
                <div className="flex-1 min-w-0">
                    <Card
                        title={hotOnly ? "Hot Leads" : "All Leads"}
                        headContent={
                            <div className="flex items-center gap-2.5 max-md:gap-2">
                                {/* Search over loaded set */}
                                <label className="relative hidden sm:flex items-center">
                                    <Icon
                                        name="search"
                                        className="absolute left-3 size-4 fill-t-tertiary pointer-events-none"
                                    />
                                    <input
                                        value={query}
                                        onChange={(e) =>
                                            setQuery(e.target.value)
                                        }
                                        placeholder="Search name or phone"
                                        className="input-base h-9 w-56 max-lg:w-40 pl-9 pr-3 rounded-full text-body-2"
                                    />
                                </label>
                                {/* Segmented hot filter */}
                                <div className="inline-flex p-1 rounded-full bg-b-surface1 border border-s-subtle dark:bg-shade-04/40">
                                    <SegBtn
                                        active={!hotOnly}
                                        onClick={() => setHotOnly(false)}
                                    >
                                        All
                                    </SegBtn>
                                    <SegBtn
                                        active={hotOnly}
                                        onClick={() => setHotOnly(true)}
                                    >
                                        Hot
                                    </SegBtn>
                                </div>
                            </div>
                        }
                    >
                        {/* Count strip */}
                        {!loading && leads.length > 0 && (
                            <div className="flex items-center justify-between px-5 pb-3 max-lg:px-3">
                                <span className="eyebrow">
                                    {visibleLeads.length}
                                    {query
                                        ? ` of ${leads.length}`
                                        : ""}{" "}
                                    {visibleLeads.length === 1
                                        ? "lead"
                                        : "leads"}
                                </span>
                                {summary.hot > 0 && !hotOnly && (
                                    <span className="flex items-center gap-1.5 text-caption text-t-tertiary">
                                        <span className="size-1.5 rounded-full bg-primary-02" />
                                        {summary.hot} hot
                                    </span>
                                )}
                            </div>
                        )}

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
                                        [...Array(7)].map((_, i) => (
                                            <tr key={i}>
                                                {[...Array(6)].map((__, j) => (
                                                    <td key={j}>
                                                        <div
                                                            className={`skeleton h-4 ${
                                                                j === 0
                                                                    ? "w-32"
                                                                    : j === 5
                                                                    ? "w-16 ml-auto"
                                                                    : "w-20"
                                                            }`}
                                                        />
                                                    </td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : visibleLeads.length === 0 ? (
                                        <tr>
                                            <td colSpan={6}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon
                                                            name={
                                                                query
                                                                    ? "search"
                                                                    : "profile"
                                                            }
                                                            className="fill-inherit"
                                                        />
                                                    </span>
                                                    <div className="state-title">
                                                        {query
                                                            ? "No matching leads"
                                                            : hotOnly
                                                            ? "No hot leads yet"
                                                            : "No leads yet"}
                                                    </div>
                                                    <div className="state-sub">
                                                        {query
                                                            ? `Nothing matches “${query}”. Try a different name or number.`
                                                            : hotOnly
                                                            ? "Leads scoring 70+ on a call will surface here automatically."
                                                            : writable
                                                            ? "Paste or upload leads on the right to get started."
                                                            : "Leads added by your team will appear here."}
                                                    </div>
                                                    {query && (
                                                        <Button
                                                            isStroke
                                                            className="mt-1"
                                                            onClick={() =>
                                                                setQuery("")
                                                            }
                                                        >
                                                            Clear search
                                                        </Button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        visibleLeads.map((l, i) => {
                                            const isHot = (l.score ?? 0) >= 70;
                                            return (
                                                <tr
                                                    key={l.id}
                                                    className="rise-in"
                                                    style={{
                                                        animationDelay: `${Math.min(
                                                            i * 25,
                                                            300
                                                        )}ms`,
                                                    }}
                                                >
                                                    <td className="font-medium text-t-primary">
                                                        <div className="flex items-center gap-2.5">
                                                            <span
                                                                className={`grid place-items-center size-8 shrink-0 rounded-full text-caption font-semibold ${
                                                                    isHot
                                                                        ? "bg-primary-02/12 text-primary-02"
                                                                        : "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                                                                }`}
                                                            >
                                                                {initials(
                                                                    l.name
                                                                )}
                                                            </span>
                                                            <span className="truncate max-w-44">
                                                                {l.name}
                                                            </span>
                                                        </div>
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
                                            );
                                        })
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>

                {/* ── Right: Add leads (hidden for read-only agents) ── */}
                {writable && (
                    <div className="w-96 max-lg:w-full shrink-0">
                        <Card title="Add Leads">
                            <div className="px-5 pb-5 space-y-4">
                                <div>
                                    <label className="block text-button mb-2.5 text-t-primary">
                                        Paste leads
                                    </label>
                                    <textarea
                                        className="input-base w-full h-32 px-4 py-3 rounded-2xl text-body-2 resize-none bg-transparent"
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
                                    <div className="relative flex flex-col items-center justify-center gap-2 h-28 rounded-2xl border border-dashed border-s-stroke2 bg-b-surface1/50 transition-colors hover:border-primary-01/50 cursor-pointer dark:bg-shade-04/30">
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

function initials(name?: string): string {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
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
            className={`px-3.5 h-8 rounded-full text-button transition-all ${
                active
                    ? "bg-b-surface2 text-t-primary shadow-widget"
                    : "text-t-secondary hover:text-t-primary"
            }`}
        >
            {children}
        </button>
    );
}
