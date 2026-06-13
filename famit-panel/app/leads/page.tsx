"use client";

import { useRef, useState, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Search from "@/components/Search";
import Tabs from "@/components/Tabs";
import Table from "@/components/Table";
import VirtualRows from "@/components/VirtualRows";
import { StatusBadge, ScoreBadge } from "@/lib/badges";
import { addLeads, type Lead } from "@/lib/api";
import { useLeadsInfinite } from "@/lib/queries";
import { useMe, canWrite } from "@/lib/auth";
import { type TabsOption } from "@/types/tabs";

function fmtDate(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString();
    } catch {
        return d;
    }
}

function initials(name?: string): string {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const VIEWS: TabsOption[] = [
    { id: 1, name: "All" },
    { id: 2, name: "Hot" },
];

export default function LeadsPage() {
    const [text, setText] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const [adding, setAdding] = useState(false);
    const [toast, setToast] = useState("");
    const [view, setView] = useState<TabsOption>(VIEWS[0]);
    const [query, setQuery] = useState("");
    const fileInputRef = useRef<HTMLInputElement>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const { me } = useMe();
    const writable = canWrite(me);
    const queryClient = useQueryClient();

    const hotOnly = view.id === 2;

    // PERF UNIT-4: cursor-paged read keyed by the hot filter. Loads ONE page
    // (~60 rows) at a time and fetches the next as you scroll near the end — the
    // leads page no longer loads every lead at once. Switching All<->Hot and
    // tab-back are instant (react-query keeps fetched pages cached + revalidates).
    const {
        data,
        isLoading,
        fetchNextPage,
        hasNextPage,
        isFetchingNextPage,
    } = useLeadsInfinite({ pageSize: 60, hot: hotOnly });
    const leads: Lead[] = useMemo(
        () => (data?.pages ?? []).flatMap((p) => p.leads),
        [data]
    );
    const total = data?.pages?.[0]?.total;
    const loading = isLoading && leads.length === 0;

    async function handleAdd() {
        setAdding(true);
        setToast("");
        try {
            const result = await addLeads(text, file);
            setToast(`Added ${result.added} leads. Total: ${result.total}`);
            setText("");
            setFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
            // Refresh every cached leads view (paged All + Hot, and any flat reads)
            // after a write, so the new leads appear without a manual reload.
            queryClient.invalidateQueries({ queryKey: ["leads-infinite"] });
            queryClient.invalidateQueries({ queryKey: ["leads"] });
        } catch (e: unknown) {
            setToast(e instanceof Error ? e.message : "Failed to add leads");
        } finally {
            setAdding(false);
        }
    }

    // Real count signals over the loaded set (no fabricated deltas).
    const hotCount = useMemo(
        () => leads.filter((l) => (l.score ?? 0) >= 70).length,
        [leads]
    );

    // Client-side search over the already-fetched pages (no API change). Active
    // search pauses infinite-scroll fetching (the user is narrowing the loaded set).
    const searching = query.trim().length > 0;
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

    const tableHead = (
        <>
            <th>Name</th>
            <th>Phone</th>
            <th>Status</th>
            <th>Score</th>
            <th className="max-lg:hidden">Last outcome</th>
            <th className="text-right">Added</th>
        </>
    );

    return (
        <Layout title="Leads">
            {toast && (
                <div
                    className={`mb-3 flex items-center gap-2 p-3.5 rounded-3xl text-body-2 ${
                        toastOk
                            ? "bg-primary-02/8 text-primary-02"
                            : "bg-primary-03/8 text-primary-03"
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

            <div className="flex max-lg:block">
                {/* ── Leads list ── */}
                <div className={writable ? "col-left" : "w-full"}>
                    <div className="card">
                        <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                            <div className="mr-auto pl-5 text-h6 max-lg:pl-3">
                                {hotOnly ? "Hot leads" : "All leads"}
                            </div>
                            <Search
                                className="w-64 ml-6 mr-6 max-md:w-full max-md:ml-3 max-md:mr-0"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search name or phone"
                                isGray
                            />
                            <Tabs items={VIEWS} value={view} setValue={setView} />
                        </div>

                        {!loading && leads.length > 0 && (
                            <div className="flex items-center gap-3 pl-5 pr-4 pt-3 text-caption text-t-tertiary max-lg:pl-3">
                                <span>
                                    {query
                                        ? `${visibleLeads.length} of ${leads.length} loaded`
                                        : total != null
                                        ? `${leads.length} of ${total} ${total === 1 ? "lead" : "leads"}`
                                        : `${leads.length} ${leads.length === 1 ? "lead" : "leads"}`}
                                </span>
                                {hotCount > 0 && !hotOnly && (
                                    <span className="flex items-center gap-1.5">
                                        <span className="size-1.5 rounded-full bg-primary-02" />
                                        {hotCount} hot
                                    </span>
                                )}
                            </div>
                        )}

                        {/* PERF UNIT-4: bounded, sticky-header scroll box the
                            virtualizer drives. Only the ~30 visible <tr>s mount;
                            scrolling near the end fetches the next cursor page. */}
                        <div
                            ref={scrollRef}
                            className="mt-3 max-h-[calc(100vh-17rem)] overflow-auto scrollbar-thin"
                        >
                            {loading ? (
                                <Table cellsThead={tableHead}>
                                    {[...Array(8)].map((_, i) => (
                                        <tr key={i}>
                                            {[...Array(6)].map((__, j) => (
                                                <td key={j}>
                                                    <div className="skeleton h-4 w-20" />
                                                </td>
                                            ))}
                                        </tr>
                                    ))}
                                </Table>
                            ) : visibleLeads.length === 0 ? (
                                <div className="state-block">
                                    <span className="state-glyph">
                                        <Icon
                                            name={query ? "search" : "profile"}
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
                                            ? "Leads scoring 70+ on a call surface here automatically."
                                            : writable
                                            ? "Paste or upload leads on the right to get started."
                                            : "Leads added by your team appear here."}
                                    </div>
                                    {query && (
                                        <Button
                                            isStroke
                                            className="!h-10 !px-5 mt-1"
                                            onClick={() => setQuery("")}
                                        >
                                            Clear search
                                        </Button>
                                    )}
                                </div>
                            ) : (
                                <table className="w-full text-body-2 [&_th]:h-14 [&_th,&_td]:pl-5 [&_th,&_td]:py-4 [&_th,&_td]:first:pl-4 [&_th,&_td]:last:pr-4 [&_th]:align-middle [&_th]:text-left [&_th]:text-overline [&_th]:uppercase [&_th]:tracking-[0.06em] [&_th]:text-t-tertiary [&_th]:font-semibold [&_thead]:border-b [&_thead]:border-s-subtle max-lg:[&_th,&_td]:first:pl-3 max-md:[&_th,&_td]:p-3 max-md:[&_th]:h-13 max-md:[&_th]:border-b max-md:[&_th]:border-s-subtle">
                                    <thead className="sticky top-0 z-10 bg-b-surface2 max-md:hidden">
                                        <tr>{tableHead}</tr>
                                    </thead>
                                    <tbody>
                                        <VirtualRows
                                            items={visibleLeads}
                                            rowKey={(l) => l.id}
                                            scrollRef={scrollRef}
                                            colSpan={6}
                                            estimateRowH={65}
                                            onEndReached={
                                                searching || !hasNextPage || isFetchingNextPage
                                                    ? undefined
                                                    : () => fetchNextPage()
                                            }
                                            renderRow={(l) => renderLeadRow(l)}
                                        />
                                    </tbody>
                                </table>
                            )}
                            {isFetchingNextPage && (
                                <div className="flex items-center justify-center gap-2 py-3 text-caption text-t-tertiary">
                                    <span className="size-3.5 rounded-full border-2 border-s-subtle border-t-primary-01 animate-spin" />
                                    Loading more…
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* ── Add leads (hidden for read-only agents) ── */}
                {writable && (
                    <div className="col-right">
                        <Card title="Add leads">
                            <div className="px-5 pb-5 space-y-4 max-lg:px-3">
                                <div>
                                    <label className="block text-button mb-2.5 text-t-primary">
                                        Paste leads
                                    </label>
                                    <textarea
                                        className="w-full h-32 px-4 py-3 rounded-2xl border border-s-stroke2 text-body-2 text-t-primary outline-none transition-colors resize-none bg-transparent hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/60"
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
                                    {adding ? "Adding…" : "Add leads"}
                                </Button>
                            </div>
                        </Card>
                    </div>
                )}
            </div>
        </Layout>
    );
}

// One lead row as a plain <tr> (so the virtualizer can attach its measurement ref).
// Classes mirror the Core_2 <TableRow> + shared <Table> cell rules — look unchanged.
function renderLeadRow(l: Lead) {
    const isHot = (l.score ?? 0) >= 70;
    return (
        <tr className="group relative [&_td:not(:first-child)]:relative [&_td]:z-2 [&_td]:border-t [&_td]:border-s-subtle [&_td]:pl-5 [&_td]:py-4 [&_td]:first:pl-4 [&_td]:last:pr-4 max-lg:[&_td]:first:pl-3 max-md:[&_td]:p-3">
            <td className="text-sub-title-1">
                <div className="flex items-center gap-3">
                    <span
                        className={`grid place-items-center size-9 shrink-0 rounded-full text-caption font-semibold ${
                            isHot
                                ? "bg-primary-02/12 text-primary-02"
                                : "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                        }`}
                    >
                        {initials(l.name)}
                    </span>
                    <span className="truncate max-w-44">{l.name}</span>
                </div>
            </td>
            <td className="text-t-secondary td-num">{l.phone}</td>
            <td>
                <StatusBadge status={l.status} />
            </td>
            <td>
                <ScoreBadge score={l.score} />
            </td>
            <td className="text-t-secondary text-caption capitalize max-lg:hidden">
                {l.last_outcome ? l.last_outcome.replace(/_/g, " ") : "—"}
            </td>
            <td className="text-t-secondary td-num text-right">
                {fmtDate(l.added_at)}
            </td>
        </tr>
    );
}
