"use client";

import { useRef, useState, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Search from "@/components/Search";
import Table from "@/components/Table";
import Select from "@/components/Select";
import Modal from "@/components/Modal";
import VirtualRows from "@/components/VirtualRows";
import { StatusBadge, LeadBadge } from "@/lib/badges";
// Shared temperature classification — the SAME source CRM uses, so the
// Hot/Warm/Cold/Dead column + filter never drift between the two pages.
import { TempBadge, tempOf, type Temperature } from "@/app/crm/_ui";
import {
    addLeads,
    deleteLead,
    deleteLeadsBulk,
    deleteAllLeads,
    type Lead,
} from "@/lib/api";
import { useLeadsInfinite } from "@/lib/queries";
import { useMe, canWrite } from "@/lib/auth";
import { type SelectOption } from "@/types/select";

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

// Temperature filter (replaces the old All/Hot tab strip). `key` carries the
// canonical temperature; "all" = no filter. Backend GET /leads only knows `hot`,
// so Hot can use the server-side fast path; the rest are derived client-side via
// tempOf over the already-loaded pages (degrades gracefully).
const TEMP_VIEWS: (SelectOption & { key: "all" | Temperature })[] = [
    { id: 1, name: "All", key: "all" },
    { id: 2, name: "Hot", key: "hot" },
    { id: 3, name: "Warm", key: "warm" },
    { id: 4, name: "Cold", key: "cold" },
    { id: 5, name: "Dead", key: "dead" },
];

// ROUND-5 LANE A — CLICK-TO-SORT column headers (mirrors CRM exactly). Every
// header is clickable; clicking sorts across ALL records via the backend
// `sort_by`/`order` params (same contract CRM uses), with a client-side sort over
// the loaded pages as the graceful fallback. The sortable columns + the backend
// sort_by key each maps to. The `added` column maps to the box's recency sort.
type LeadSortKey =
    | "name"
    | "phone"
    | "temperature"
    | "status"
    | "score"
    | "last_outcome"
    | "added_at";

// Every column header is clickable. `className` mirrors the responsive
// hide-on-narrow rules already on the body cells so header + cell stay aligned.
const LEAD_COLS: { label: string; key: LeadSortKey; className?: string }[] = [
    { label: "Name", key: "name" },
    { label: "Phone", key: "phone" },
    { label: "Temperature", key: "temperature" },
    { label: "Status", key: "status", className: "max-md:hidden" },
    { label: "Lead", key: "score" },
    { label: "Last outcome", key: "last_outcome", className: "max-lg:hidden" },
    { label: "Added", key: "added_at", className: "text-right" },
];

// Temperature ordering for the client-side fallback sort (hot is "highest").
const LEAD_TEMP_RANK: Record<string, number> = { hot: 4, warm: 3, cold: 2, dead: 1 };

// Map a sort key + direction onto the backend GET /leads `sort` token (the legacy
// param the box already understands) so the server-side fast path stays wired even
// where `sort_by`/`order` are not yet honored.
function legacySortToken(key: LeadSortKey, dir: "asc" | "desc"): string | undefined {
    if (key === "added_at") return dir === "asc" ? "oldest" : "recent";
    if (key === "name") return "name";
    if (key === "status") return "status";
    if (key === "score" || key === "temperature") return "score";
    return undefined;
}

export default function LeadsPage() {
    const [text, setText] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const [adding, setAdding] = useState(false);
    const [toast, setToast] = useState("");
    const [toastErr, setToastErr] = useState(false);
    const [view, setView] = useState<SelectOption>(TEMP_VIEWS[0]);
    // ROUND-5 LANE A — click-to-sort header state (mirrors CRM). Default = newest
    // added first.
    const [sortKey, setSortKey] = useState<LeadSortKey>("added_at");
    const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
    const [query, setQuery] = useState("");
    // ── Multi-select + delete state ──
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [deleting, setDeleting] = useState(false);
    const [confirmAllOpen, setConfirmAllOpen] = useState(false);
    const [confirmText, setConfirmText] = useState("");
    const fileInputRef = useRef<HTMLInputElement>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    const { me } = useMe();
    const writable = canWrite(me);
    const queryClient = useQueryClient();

    const tempKey = (TEMP_VIEWS.find((v) => v.id === view.id) ?? TEMP_VIEWS[0]).key;
    // Hot uses the server-side fast path; warm/cold/dead are derived client-side.
    const hotOnly = tempKey === "hot";

    // Click-to-sort header toggle (identical UX to CRM): clicking the active column
    // flips direction; clicking a new column selects it ascending.
    function handleSort(key: LeadSortKey) {
        if (sortKey === key) {
            setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        } else {
            setSortKey(key);
            setSortDir("asc");
        }
    }

    // PERF UNIT-4: cursor-paged read keyed by the hot filter + sort. Loads ONE
    // page (~60 rows) at a time and fetches the next as you scroll near the end.
    // ROUND-5: the active column + direction re-key the query so a header click
    // starts a fresh page-0 fetch ordered across ALL records (sort_by/order, like
    // CRM); `sort` carries the legacy token for the box's server-side fast path.
    const {
        data,
        isLoading,
        fetchNextPage,
        hasNextPage,
        isFetchingNextPage,
    } = useLeadsInfinite({
        pageSize: 60,
        hot: hotOnly,
        sort: legacySortToken(sortKey, sortDir),
        sort_by: sortKey,
        order: sortDir,
    });
    const leads: Lead[] = useMemo(
        () => (data?.pages ?? []).flatMap((p) => p.leads),
        [data]
    );
    const total = data?.pages?.[0]?.total;
    const loading = isLoading && leads.length === 0;

    function refreshLeads() {
        queryClient.invalidateQueries({ queryKey: ["leads-infinite"] });
        queryClient.invalidateQueries({ queryKey: ["leads"] });
    }

    async function handleAdd() {
        setAdding(true);
        setToast("");
        try {
            const result = await addLeads(text, file);
            setToastErr(false);
            // Dedup result: the backend skips phone-duplicate rows server-side. It
            // may report the skipped count under any of these keys; if it does, we
            // show "Added N · M duplicates skipped", otherwise just the added count
            // (graceful degrade until the backend returns a duplicate tally).
            const extra = result as Record<string, unknown>;
            const dupRaw =
                extra.duplicates ??
                extra.skipped ??
                extra.duplicate ??
                extra.ignored;
            const dup = typeof dupRaw === "number" ? dupRaw : Number(dupRaw);
            const added = result.added ?? 0;
            const parts = [`Added ${added} ${added === 1 ? "lead" : "leads"}`];
            if (Number.isFinite(dup) && dup > 0) {
                parts.push(`${dup} duplicate${dup === 1 ? "" : "s"} skipped`);
            }
            parts.push(`Total: ${result.total}`);
            setToast(parts.join(" · "));
            setText("");
            setFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
            refreshLeads();
        } catch (e: unknown) {
            setToastErr(true);
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
    // Temperature filter (client-side for warm/cold/dead; hot already came filtered
    // from the server). Active when not "all" and not the hot fast-path.
    const tempFiltering = tempKey !== "all" && tempKey !== "hot";
    const visibleLeads = useMemo(() => {
        let rows = leads;
        if (tempFiltering) {
            rows = rows.filter((l) => tempOf(l) === tempKey);
        }
        const q = query.trim().toLowerCase();
        if (q) {
            rows = rows.filter(
                (l) =>
                    l.name?.toLowerCase().includes(q) ||
                    l.phone?.toLowerCase().includes(q)
            );
        }
        // ROUND-5 client-side sort fallback (mirrors CRM): the backend sort_by/order
        // orders across ALL records; this re-orders the loaded set so a header click
        // is instant and stays correct even when the box ignores the params.
        const dir = sortDir === "asc" ? 1 : -1;
        return [...rows].sort((a, b) => {
            switch (sortKey) {
                case "name":
                    return dir * (a.name || "").localeCompare(b.name || "");
                case "phone":
                    return dir * (a.phone || "").localeCompare(b.phone || "");
                case "temperature":
                    return (
                        dir *
                        ((LEAD_TEMP_RANK[tempOf(a)] ?? 0) -
                            (LEAD_TEMP_RANK[tempOf(b)] ?? 0))
                    );
                case "status":
                    return dir * (a.status || "").localeCompare(b.status || "");
                case "score":
                    return dir * ((a.score ?? 0) - (b.score ?? 0));
                case "last_outcome":
                    return dir * (a.last_outcome || "").localeCompare(b.last_outcome || "");
                case "added_at":
                    return dir * ((a.added_at || "").localeCompare(b.added_at || ""));
                default:
                    return 0;
            }
        });
    }, [leads, query, tempFiltering, tempKey, sortKey, sortDir]);

    // ── Selection helpers (scoped to the currently visible/loaded rows) ──
    const allVisibleSelected =
        visibleLeads.length > 0 && visibleLeads.every((l) => selected.has(l.id));
    function toggleSelectAll(on: boolean) {
        setSelected((prev) => {
            const next = new Set(prev);
            for (const l of visibleLeads) {
                if (on) next.add(l.id);
                else next.delete(l.id);
            }
            return next;
        });
    }
    function toggleRow(id: string) {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    }
    function clearSelection() {
        setSelected(new Set());
    }

    async function handleDeleteRow(id: string) {
        if (deleting) return;
        setDeleting(true);
        setToast("");
        try {
            await deleteLead(id);
            setSelected((prev) => {
                const next = new Set(prev);
                next.delete(id);
                return next;
            });
            setToastErr(false);
            setToast("Lead deleted.");
            refreshLeads();
        } catch (e: unknown) {
            setToastErr(true);
            setToast(e instanceof Error ? e.message : "Failed to delete lead");
        } finally {
            setDeleting(false);
        }
    }

    async function handleDeleteSelected() {
        const ids = [...selected];
        if (ids.length === 0 || deleting) return;
        setDeleting(true);
        setToast("");
        try {
            const r = await deleteLeadsBulk(ids);
            clearSelection();
            setToastErr(false);
            setToast(`Deleted ${r.deleted} ${r.deleted === 1 ? "lead" : "leads"}.`);
            refreshLeads();
        } catch (e: unknown) {
            setToastErr(true);
            setToast(e instanceof Error ? e.message : "Failed to delete leads");
        } finally {
            setDeleting(false);
        }
    }

    async function handleDeleteAll() {
        if (deleting) return;
        setDeleting(true);
        setToast("");
        try {
            const r = await deleteAllLeads();
            clearSelection();
            setConfirmAllOpen(false);
            setConfirmText("");
            setToastErr(false);
            setToast(`Deleted all ${r.deleted} ${r.deleted === 1 ? "lead" : "leads"}.`);
            refreshLeads();
        } catch (e: unknown) {
            setToastErr(true);
            setToast(e instanceof Error ? e.message : "Failed to delete all leads");
        } finally {
            setDeleting(false);
        }
    }

    const toastOk = !toastErr;
    const selCount = selected.size;

    const tableHead = (
        <>
            {writable && <th className="w-10" />}
            <th>Name</th>
            <th>Phone</th>
            <th>Temperature</th>
            <th className="max-md:hidden">Status</th>
            <th>Lead</th>
            <th className="max-lg:hidden">Last outcome</th>
            <th className="text-right">Added</th>
            {writable && <th className="w-12 text-right" />}
        </>
    );
    const colCount = writable ? 9 : 7;

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
                                {tempKey === "all" ? "All leads" : `${view.name} leads`}
                            </div>
                            <Search
                                className="w-56 ml-6 mr-4 max-md:w-full max-md:ml-3 max-md:mr-0"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search name or phone"
                                isGray
                            />
                            <Select
                                className="w-40 mr-4 max-md:w-full max-md:mr-0"
                                classButton="!h-10"
                                value={view}
                                onChange={setView}
                                options={TEMP_VIEWS}
                            />
                            {/* ROUND-5: the sort Select is gone — every column header
                                below is click-to-sort (Name/Phone/Temperature/Status/
                                Lead/Last outcome/Added), sorting across ALL records. */}
                        </div>

                        {/* ── Bulk action toolbar (writable only) ── */}
                        {writable && (
                            <div className="flex items-center gap-3 flex-wrap pl-5 pr-4 pt-3 max-lg:pl-3">
                                {selCount > 0 ? (
                                    <>
                                        <span className="text-caption text-t-secondary">
                                            {selCount} selected
                                        </span>
                                        <Button
                                            isStroke
                                            className="!h-9 !px-4 text-button"
                                            onClick={handleDeleteSelected}
                                            disabled={deleting}
                                        >
                                            <Icon
                                                name="trash"
                                                className="size-4 fill-primary-03 mr-1.5"
                                            />
                                            {deleting ? "Deleting…" : "Delete selected"}
                                        </Button>
                                        <button
                                            type="button"
                                            className="text-caption text-t-tertiary hover:text-t-primary transition-colors"
                                            onClick={clearSelection}
                                        >
                                            Clear
                                        </button>
                                    </>
                                ) : (
                                    leads.length > 0 && (
                                        <button
                                            type="button"
                                            className="inline-flex items-center gap-1.5 text-caption text-t-tertiary hover:text-primary-03 transition-colors"
                                            onClick={() => {
                                                setConfirmText("");
                                                setConfirmAllOpen(true);
                                            }}
                                        >
                                            <Icon
                                                name="trash"
                                                className="size-3.5 fill-current"
                                            />
                                            Delete all leads
                                        </button>
                                    )
                                )}
                            </div>
                        )}

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
                            className="mt-3 max-h-[calc(100vh-19rem)] overflow-auto scrollbar-thin"
                        >
                            {loading ? (
                                <Table cellsThead={tableHead}>
                                    {[...Array(8)].map((_, i) => (
                                        <tr key={i}>
                                            {[...Array(colCount)].map((__, j) => (
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
                                            : tempKey === "hot"
                                            ? "No hot leads yet"
                                            : tempKey !== "all"
                                            ? `No ${view.name.toLowerCase()} leads`
                                            : "No leads yet"}
                                    </div>
                                    <div className="state-sub">
                                        {query
                                            ? `Nothing matches “${query}”. Try a different name or number.`
                                            : tempKey === "hot"
                                            ? "Leads scoring 70+ on a call surface here automatically."
                                            : tempKey !== "all"
                                            ? `No leads are ${view.name.toLowerCase()} right now — try another temperature.`
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
                                        <tr>
                                            {writable && (
                                                <th className="w-10">
                                                    <input
                                                        type="checkbox"
                                                        className="size-4 rounded cursor-pointer accent-primary-01"
                                                        checked={allVisibleSelected}
                                                        onChange={(e) =>
                                                            toggleSelectAll(e.target.checked)
                                                        }
                                                        aria-label="Select all loaded leads"
                                                    />
                                                </th>
                                            )}
                                            {/* ROUND-5: every column header click-to-sorts
                                                across ALL records (same UX as CRM). */}
                                            {LEAD_COLS.map((col) => {
                                                const active = sortKey === col.key;
                                                return (
                                                    <th
                                                        key={col.label}
                                                        className={`cursor-pointer select-none ${col.className ?? ""}`}
                                                        onClick={() => handleSort(col.key)}
                                                        aria-sort={
                                                            active
                                                                ? sortDir === "asc"
                                                                    ? "ascending"
                                                                    : "descending"
                                                                : "none"
                                                        }
                                                    >
                                                        <span
                                                            className={`inline-flex items-center gap-1 ${
                                                                col.className?.includes("text-right")
                                                                    ? "justify-end"
                                                                    : ""
                                                            }`}
                                                        >
                                                            {col.label}
                                                            <span className="text-t-tertiary text-caption">
                                                                {active
                                                                    ? sortDir === "asc"
                                                                        ? "↑"
                                                                        : "↓"
                                                                    : ""}
                                                            </span>
                                                        </span>
                                                    </th>
                                                );
                                            })}
                                            {writable && <th className="w-12 text-right" />}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <VirtualRows
                                            items={visibleLeads}
                                            rowKey={(l) => l.id}
                                            scrollRef={scrollRef}
                                            colSpan={colCount}
                                            estimateRowH={65}
                                            onEndReached={
                                                searching || !hasNextPage || isFetchingNextPage
                                                    ? undefined
                                                    : () => fetchNextPage()
                                            }
                                            renderRow={(l) =>
                                                renderLeadRow(l, {
                                                    writable,
                                                    selected: selected.has(l.id),
                                                    onToggle: () => toggleRow(l.id),
                                                    onDelete: () => handleDeleteRow(l.id),
                                                    deleting,
                                                })
                                            }
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
                                        Upload CSV or Excel
                                    </label>
                                    <div className="relative flex flex-col items-center justify-center gap-2 h-28 rounded-2xl border border-dashed border-s-stroke2 bg-b-surface1/50 transition-colors hover:border-primary-01/50 cursor-pointer dark:bg-shade-04/30">
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            accept=".csv,text/csv,.xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
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
                                                    Drop CSV / Excel or{" "}
                                                    <span className="font-medium text-t-primary">
                                                        browse
                                                    </span>
                                                </span>
                                            </>
                                        )}
                                    </div>
                                    <div className="mt-1.5 text-caption text-t-tertiary">
                                        .csv, .xlsx or .xls — duplicates are skipped automatically.
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

            {/* ── Delete-all type-to-confirm modal (strong destructive guard) ── */}
            <Modal
                open={confirmAllOpen}
                onClose={() => {
                    if (!deleting) setConfirmAllOpen(false);
                }}
            >
                <div className="flex justify-center items-center size-16 mb-8 bg-primary-03/15 rounded-full">
                    <Icon name="trash" className="size-6 fill-primary-03" />
                </div>
                <div className="mb-4 text-h4 max-md:text-h5">
                    Delete all leads?
                </div>
                <div className="mb-6 text-body-2 font-medium text-t-tertiary">
                    This permanently deletes{" "}
                    <span className="text-t-primary">all of your leads</span>
                    {total != null ? ` (${total})` : ""}. Only your own leads are
                    removed — this can&apos;t be undone. Type{" "}
                    <span className="font-semibold text-t-primary">DELETE</span> to
                    confirm.
                </div>
                <input
                    type="text"
                    autoFocus
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    placeholder="Type DELETE"
                    className="w-full h-12 px-4 mb-2 rounded-2xl border border-s-stroke2 text-body-2 text-t-primary outline-none transition-colors bg-transparent hover:border-s-highlight focus:border-primary-03/60 placeholder:text-t-secondary/50"
                />
                <div className="flex justify-end gap-3 mt-6">
                    <Button
                        className="flex-1"
                        isStroke
                        onClick={() => setConfirmAllOpen(false)}
                        disabled={deleting}
                    >
                        Cancel
                    </Button>
                    <Button
                        className="flex-1"
                        isBlack
                        onClick={handleDeleteAll}
                        disabled={deleting || confirmText.trim().toUpperCase() !== "DELETE"}
                    >
                        {deleting ? "Deleting…" : "Delete all"}
                    </Button>
                </div>
            </Modal>
        </Layout>
    );
}

// One lead row as a plain <tr> (so the virtualizer can attach its measurement ref).
// Classes mirror the Core_2 <TableRow> + shared <Table> cell rules — look unchanged.
function renderLeadRow(
    l: Lead,
    opts: {
        writable: boolean;
        selected: boolean;
        onToggle: () => void;
        onDelete: () => void;
        deleting: boolean;
    }
) {
    const isHot = (l.score ?? 0) >= 70;
    return (
        <tr
            className={`group relative [&_td:not(:first-child)]:relative [&_td]:z-2 [&_td]:border-t [&_td]:border-s-subtle [&_td]:pl-5 [&_td]:py-4 [&_td]:first:pl-4 [&_td]:last:pr-4 max-lg:[&_td]:first:pl-3 max-md:[&_td]:p-3 ${
                opts.selected ? "bg-primary-01/5" : ""
            }`}
        >
            {opts.writable && (
                <td className="w-10">
                    <input
                        type="checkbox"
                        className="size-4 rounded cursor-pointer accent-primary-01"
                        checked={opts.selected}
                        onChange={opts.onToggle}
                        aria-label={`Select ${l.name}`}
                    />
                </td>
            )}
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
                {/* Hot/Warm/Cold/Dead heat — same tempOf source as CRM */}
                <TempBadge row={l} />
            </td>
            <td className="max-md:hidden">
                <StatusBadge status={l.status} />
            </td>
            <td>
                {/* W15 §4 — business-friendly tier (Hot/Warm/Cold/…), not a raw score */}
                <LeadBadge lead={l} />
            </td>
            <td className="text-t-secondary text-caption capitalize max-lg:hidden">
                {l.last_outcome ? l.last_outcome.replace(/_/g, " ") : "—"}
            </td>
            <td className="text-t-secondary td-num text-right">
                {fmtDate(l.added_at)}
            </td>
            {opts.writable && (
                <td className="w-12 text-right">
                    <button
                        type="button"
                        onClick={opts.onDelete}
                        disabled={opts.deleting}
                        aria-label={`Delete ${l.name}`}
                        className="inline-grid place-items-center size-8 rounded-full text-t-tertiary transition-colors hover:bg-primary-03/10 hover:text-primary-03 disabled:opacity-40 disabled:pointer-events-none md:opacity-0 md:group-hover:opacity-100"
                    >
                        <Icon name="trash" className="size-4 fill-current" />
                    </button>
                </td>
            )}
        </tr>
    );
}
