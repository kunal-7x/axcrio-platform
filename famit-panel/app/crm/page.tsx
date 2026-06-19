"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Search from "@/components/Search";
import Tabs from "@/components/Tabs";
import Select from "@/components/Select";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import ConfirmDeleteModal from "@/components/ConfirmDeleteModal";
import {
    getContacts,
    getSegments,
    deleteContact,
    CrmDormantError,
    isDormantResponse,
    type ContactListItem,
    type ContactsResponse,
    type Segment,
} from "./client";
import { StageBadge, TempBadge, tempOf, initials, fmtRelative } from "./_ui";

// Stage filter tabs (mirrors §4.1 derivation order). "all" is special.
// ROUND-6 LANE 4 — "Won"/"Lost" REMOVED from the stage filter per founder: the
// active pipeline stages are new → contacted → engaged → qualified (Booked kept
// as the conversion stage). Won/Lost are terminal outcomes shown elsewhere, not
// a working-pipeline filter. The `won`/`lost` STAGE VALUES still render via
// StageBadge if a contact carries them; only the FILTER options are trimmed.
const STAGE_TABS = [
    { id: 1, name: "All", key: "all" },
    { id: 2, name: "New", key: "new" },
    { id: 3, name: "Contacted", key: "contacted" },
    { id: 4, name: "Engaged", key: "engaged" },
    { id: 5, name: "Qualified", key: "qualified" },
];

// Lifecycle/heat filter — maps to the contact's lifecycle_state field.
// All = no filter; the rest pass as lifecycle= query param AND post-filter.
const LIFECYCLE_TABS = [
    { id: 1, name: "All", key: "all" },
    { id: 2, name: "Hot", key: "hot" },
    { id: 3, name: "Warm", key: "warm" },
    { id: 4, name: "Cold", key: "cold" },
    { id: 5, name: "Dead", key: "dead" },
];

// Cursor page size (Lane C SPEED) — one "Show more" fetches this many more rows.
const CRM_PAGE = 60;

// Sortable columns — clicking the header toggles asc/desc.
type SortKey =
    | "name"
    | "temperature"
    | "stage"
    | "campaign"
    | "score"
    | "last_outcome"
    | "last_activity_at";

// Temperature ordering for sorting (hot is "highest").
const TEMP_RANK: Record<string, number> = { hot: 4, warm: 3, cold: 2, dead: 1 };

// Campaign label off a contact row — tolerant of either field name, "—" if absent.
function campaignOf(c: ContactListItem): string {
    return (c.campaign || c.campaign_name || "").trim();
}

const tableHead: { label: string; key: SortKey; className?: string }[] = [
    { label: "Contact", key: "name" },
    { label: "Temperature", key: "temperature" },
    { label: "Stage", key: "stage", className: "max-md:hidden" },
    { label: "Campaign", key: "campaign", className: "max-lg:hidden" },
    { label: "Score", key: "score", className: "max-md:hidden" },
    { label: "Last Outcome", key: "last_outcome", className: "max-xl:hidden" },
    { label: "Last Activity", key: "last_activity_at", className: "text-right max-md:hidden" },
];

export default function CrmWorkspacePage() {
    return (
        <Suspense fallback={<Layout title="CRM"><div /></Layout>}>
            <CrmWorkspaceInner />
        </Suspense>
    );
}

function CrmWorkspaceInner() {
    // W15 — honor the shared ?status= deep-link (the Dashboard "Hot leads" + the
    // Leads page link here with ?status=hot). status=hot lands on the Hot/lifecycle view.
    const params = useSearchParams();
    const statusParam = (params.get("status") || "").toLowerCase();

    const queryClient = useQueryClient();

    // Filters (server-driven so they reflect the real read-model once mounted).
    const [stageTab, setStageTab] = useState(
        () => STAGE_TABS.find((t) => t.key === statusParam) ?? STAGE_TABS[0]
    );
    // Lifecycle/heat filter — "hot" from ?status=hot maps here.
    const [lifecycleTab, setLifecycleTab] = useState(
        () => LIFECYCLE_TABS.find((t) => t.key === statusParam) ?? LIFECYCLE_TABS[0]
    );
    const [segment, setSegment] = useState<{ id: number; name: string } | null>(
        null
    );
    const [query, setQuery] = useState("");
    // Sort state: key + direction
    const [sortKey, setSortKey] = useState<SortKey>("last_activity_at");
    const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
    // Delete in-progress set
    const [deleting, setDeleting] = useState<Set<string>>(new Set());
    const [deleteError, setDeleteError] = useState("");
    const [delTarget, setDelTarget] = useState<{ id: string; name: string } | null>(null);

    const [segments, setSegments] = useState<Segment[]>([]);

    const stage = stageTab.key;
    const lifecycle = lifecycleTab.key;
    // option.id (1-based) maps to segments[id-1]; id 0 = "All segments".
    const segmentId =
        segment && segment.id > 0 ? segments[segment.id - 1]?.id : undefined;

    // Sort header toggle
    const handleSort = (key: SortKey) => {
        if (sortKey === key) {
            setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        } else {
            setSortKey(key);
            setSortDir("asc");
        }
    };

    // Delete row handler — role-gated upstream; degrade gracefully on 403.
    const handleDelete = async (id: string) => {
        setDeleting((s) => new Set(s).add(id));
        setDeleteError("");
        try {
            await deleteContact(id);
            queryClient.invalidateQueries({ queryKey: ["contacts"] });
        } catch (e) {
            setDeleteError(e instanceof Error ? e.message : "Delete failed");
        } finally {
            setDeleting((s) => {
                const n = new Set(s);
                n.delete(id);
                return n;
            });
        }
    };

    // Lane C SPEED — cursor-paged contacts (was a single limit:500 load-all that
    // got slow on big books). Loads ONE page (~60) and a "Show more" fetches the
    // next; the active filters + sort key/dir re-key the query so a new filter or a
    // header click starts a fresh page-0 fetch. Backend sort_by/order sort across
    // ALL records; the client sort below is the graceful fallback. Cache keeps the
    // tab instant on return; 10 s bg refresh for near-live updates.
    const contactsQuery = useInfiniteQuery<ContactsResponse, Error>({
        queryKey: ["contacts", { stage, lifecycle, segmentId, sortKey, sortDir }],
        queryFn: async ({ pageParam }) => {
            try {
                return await getContacts({
                    stage: stage !== "all" ? stage : undefined,
                    lifecycle: lifecycle !== "all" ? lifecycle : undefined,
                    segment: segmentId,
                    sort: sortKey,
                    sort_by: sortKey,
                    order: sortDir,
                    limit: CRM_PAGE,
                    offset: (pageParam as number) ?? 0,
                });
            } catch (e) {
                if (e instanceof CrmDormantError) {
                    return { contacts: [], total: 0, note: "dormant" } as ContactsResponse;
                }
                throw e;
            }
        },
        initialPageParam: 0,
        // Prefer the backend-echoed `next`; else derive it (offset+len) and stop
        // once a short/empty page proves we hit the end (legacy flat-list backend).
        getNextPageParam: (last, all) => {
            if (last.next != null) return last.next;
            const loaded = all.reduce((n, p) => n + (p.contacts?.length ?? 0), 0);
            if ((last.contacts?.length ?? 0) < CRM_PAGE) return undefined;
            if (last.total != null && loaded >= last.total) return undefined;
            return loaded;
        },
        refetchInterval: 10_000,
    });

    const pages = contactsQuery.data?.pages;
    const firstPage = pages?.[0];
    const dormant = !!firstPage && isDormantResponse(firstPage);
    const rawContacts: ContactListItem[] = useMemo(
        () => (dormant ? [] : (pages ?? []).flatMap((p) => p.contacts ?? [])),
        [pages, dormant]
    );
    const total = dormant ? 0 : firstPage?.total ?? rawContacts.length;
    const error = (contactsQuery.error
        ? contactsQuery.error instanceof Error
            ? contactsQuery.error.message
            : "Failed to load contacts"
        : "") || deleteError;
    const loading = contactsQuery.isLoading && rawContacts.length === 0;

    // Client-side temperature post-filter — uses the SAME tempOf deriver the
    // Temperature column renders, so the filter and the badge never disagree
    // (degrades gracefully when the explicit lifecycle field is absent).
    const contacts: ContactListItem[] = useMemo(() => {
        if (lifecycle === "all") return rawContacts;
        return rawContacts.filter((c) => tempOf(c) === lifecycle);
    }, [rawContacts, lifecycle]);

    // Segments are a nice-to-have filter; failure (incl. dormant) is silent.
    useEffect(() => {
        getSegments()
            .then((r) => setSegments(r.segments || []))
            .catch(() => setSegments([]));
    }, []);

    // Client-side search over the loaded page (no extra round-trip for typing).
    const visible = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return contacts;
        return contacts.filter(
            (c) =>
                c.name?.toLowerCase().includes(q) ||
                c.phone_display?.toLowerCase().includes(q)
        );
    }, [contacts, query]);

    // Client-side sort — applies after search filter so toggling a header is instant.
    const sorted = useMemo(() => {
        const dir = sortDir === "asc" ? 1 : -1;
        return [...visible].sort((a, b) => {
            switch (sortKey) {
                case "name":
                    return dir * (a.name || "").localeCompare(b.name || "");
                case "temperature":
                    return dir * ((TEMP_RANK[tempOf(a)] ?? 0) - (TEMP_RANK[tempOf(b)] ?? 0));
                case "campaign":
                    return dir * (campaignOf(a) || "").localeCompare(campaignOf(b) || "");
                case "stage":
                    return dir * (a.stage || "").localeCompare(b.stage || "");
                case "score":
                    return dir * ((a.score ?? 0) - (b.score ?? 0));
                case "last_outcome":
                    return dir * (a.last_outcome || "").localeCompare(b.last_outcome || "");
                case "last_activity_at":
                    return (
                        dir *
                        ((a.last_activity_at || "").localeCompare(
                            b.last_activity_at || ""
                        ))
                    );
                default:
                    return 0;
            }
        });
    }, [visible, sortKey, sortDir]);

    // Real summary signals from the loaded set (never a fabricated delta).
    const summary = useMemo(() => {
        const n = rawContacts.length;
        const hot = rawContacts.filter((c) => c.hot || (c.score ?? 0) >= 70).length;
        const qualified = rawContacts.filter((c) =>
            ["qualified", "booked", "won"].includes(c.stage)
        ).length;
        const engaged = rawContacts.filter((c) =>
            ["engaged", "qualified", "booked", "won"].includes(c.stage)
        ).length;
        const scored = rawContacts.filter((c) => (c.score ?? 0) > 0);
        const avg =
            scored.length > 0
                ? Math.round(
                      scored.reduce((a, c) => a + (c.score ?? 0), 0) /
                          scored.length
                  )
                : null;
        return { n, hot, qualified, engaged, avg };
    }, [rawContacts]);

    const segmentOptions = useMemo(
        () => [
            { id: 0, name: "All segments" },
            ...segments.map((s, i) => ({ id: i + 1, name: s.name })),
        ],
        [segments]
    );

    const activeFilters =
        !!query || stage !== "all" || lifecycle !== "all" || (segment && segment.id !== 0);

    const clearFilters = () => {
        setQuery("");
        setStageTab(STAGE_TABS[0]);
        setLifecycleTab(LIFECYCLE_TABS[0]);
        setSegment(null);
    };

    return (
        <Layout title="CRM">
            {/* ── Dormant: the read-model isn't switched on yet ─────────── */}
            {dormant ? (
                <Card title="Customer 360">
                    <DormantBody />
                </Card>
            ) : (
                <div className="flex flex-col gap-3">
                    {/* ── Overview metric strip (Core_2 Overview archetype) ── */}
                    <Card title="Overview">
                        <div className="flex gap-8 px-5 pb-5 pt-1 max-lg:gap-6 max-lg:px-3 max-lg:overflow-auto max-lg:scrollbar-none">
                            <MetricItem
                                icon="profile"
                                title="Contacts"
                                value={loading ? "—" : total}
                                sub={
                                    loading
                                        ? undefined
                                        : total === 0
                                        ? "Awaiting first contacts"
                                        : `${summary.engaged} engaged or better`
                                }
                            />
                            <MetricItem
                                icon="star-fill"
                                title="Hot · 70+"
                                value={loading ? "—" : summary.hot}
                                sub={
                                    loading || summary.n === 0
                                        ? undefined
                                        : `${Math.round(
                                              (summary.hot / summary.n) * 100
                                          )}% of loaded`
                                }
                                accent
                            />
                            <MetricItem
                                icon="check-circle"
                                title="Qualified+"
                                value={loading ? "—" : summary.qualified}
                                sub={
                                    loading || summary.n === 0
                                        ? undefined
                                        : `${Math.round(
                                              (summary.qualified / summary.n) * 100
                                          )}% reached qualified`
                                }
                            />
                            <MetricItem
                                icon="chart"
                                title="Avg Score"
                                value={
                                    loading
                                        ? "—"
                                        : summary.avg != null
                                        ? summary.avg
                                        : "—"
                                }
                                sub={
                                    loading
                                        ? undefined
                                        : summary.avg == null
                                        ? "No scored contacts yet"
                                        : "0–100 interest scale"
                                }
                            />
                        </div>
                    </Card>

                    {/* ── List/Table archetype (Core_2 CustomerListPage) ── */}
                    <div className="card">
                        <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                            <div className="pl-5 text-h6 max-lg:pl-3 max-md:w-full">
                                Contacts
                            </div>
                            <Search
                                className="w-70 ml-6 mr-auto max-lg:w-56 max-md:w-full max-md:ml-0"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search name or phone"
                                isGray
                            />
                            {/* Stage filter — right-side dropdown (was a tab strip) */}
                            <Select
                                className="w-44 mr-4 max-md:w-full max-md:mr-0"
                                classButton="!h-10"
                                value={stageTab}
                                onChange={(v) => {
                                    const next =
                                        STAGE_TABS.find((t) => t.id === v.id) ?? STAGE_TABS[0];
                                    setStageTab(next);
                                }}
                                options={STAGE_TABS}
                            />
                        </div>

                        {/* Lifecycle / temperature filter row (Hot/Warm/Cold/Dead) */}
                        {query === "" && (
                            <div className="px-2 pt-1 overflow-x-auto scrollbar-none">
                                <Tabs
                                    items={LIFECYCLE_TABS}
                                    value={lifecycleTab}
                                    setValue={(v) =>
                                        setLifecycleTab(v as (typeof LIFECYCLE_TABS)[number])
                                    }
                                />
                            </div>
                        )}

                        {/* Segment select — only when segments exist */}
                        {query === "" && segments.length > 0 && (
                            <div className="flex items-center justify-end px-5 pt-3 max-lg:px-3">
                                <Select
                                    className="min-w-44"
                                    value={segment ?? segmentOptions[0]}
                                    onChange={setSegment}
                                    options={segmentOptions}
                                />
                            </div>
                        )}

                        {error && (
                            <div className="mx-5 mt-3 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03 max-lg:mx-3">
                                <Icon
                                    name="info"
                                    className="size-4 shrink-0 fill-primary-03"
                                />
                                {error}
                            </div>
                        )}

                        <div className="p-1 pt-3 max-lg:px-0">
                            {loading ? (
                                <TableSkeleton />
                            ) : sorted.length === 0 ? (
                                <EmptyState
                                    query={query}
                                    lifecycleLabel={lifecycleTab.name}
                                    stageLabel={stageTab.name}
                                    isAll={stage === "all" && lifecycle === "all"}
                                    canClear={!!activeFilters}
                                    onClear={clearFilters}
                                />
                            ) : (
                                <Table
                                    cellsThead={[
                                        ...tableHead.map((col) => (
                                            <th
                                                key={col.key}
                                                className={`cursor-pointer select-none ${col.className ?? ""}`}
                                                onClick={() => handleSort(col.key)}
                                            >
                                                <span className="inline-flex items-center gap-1">
                                                    {col.label}
                                                    <span className="text-t-tertiary text-caption">
                                                        {sortKey === col.key
                                                            ? sortDir === "asc"
                                                                ? "↑"
                                                                : "↓"
                                                            : ""}
                                                    </span>
                                                </span>
                                            </th>
                                        )),
                                        <th key="_del" className="w-10" />,
                                    ]}
                                >
                                    {sorted.map((c) => {
                                        const isHot =
                                            c.hot || (c.score ?? 0) >= 70;
                                        const isDeleting = deleting.has(c.id);
                                        return (
                                            <TableRow key={c.id}>
                                                <td className="font-medium text-t-primary">
                                                    <Link
                                                        href={`/crm/${encodeURIComponent(
                                                            c.id
                                                        )}`}
                                                        className="flex items-center gap-3"
                                                    >
                                                        <span
                                                            className={`grid place-items-center size-11 shrink-0 rounded-full text-button font-semibold ${
                                                                isHot
                                                                    ? "bg-primary-02/12 text-primary-02"
                                                                    : "bg-b-surface1 text-t-secondary"
                                                            }`}
                                                        >
                                                            {initials(c.name)}
                                                        </span>
                                                        <span className="min-w-0">
                                                            <span className="block truncate max-w-48 text-sub-title-1 text-t-primary">
                                                                {c.name ||
                                                                    "Unknown"}
                                                            </span>
                                                            <span className="block truncate max-w-48 text-body-2 text-t-tertiary">
                                                                {c.phone_display ||
                                                                    "—"}
                                                            </span>
                                                        </span>
                                                    </Link>
                                                </td>
                                                <td>
                                                    <TempBadge row={c} />
                                                </td>
                                                <td className="max-md:hidden">
                                                    <StageBadge
                                                        stage={c.stage}
                                                    />
                                                </td>
                                                <td className="text-t-secondary max-lg:hidden">
                                                    {campaignOf(c) || (
                                                        <span className="text-t-tertiary">—</span>
                                                    )}
                                                </td>
                                                <td className="max-md:hidden">
                                                    <ScoreCell
                                                        score={c.score}
                                                        hot={isHot}
                                                    />
                                                </td>
                                                <td className="text-t-secondary capitalize max-xl:hidden">
                                                    {c.last_outcome
                                                        ? c.last_outcome.replace(
                                                              /_/g,
                                                              " "
                                                          )
                                                        : "—"}
                                                </td>
                                                <td className="text-t-secondary text-right max-md:hidden">
                                                    {fmtRelative(
                                                        c.last_activity_at
                                                    )}
                                                </td>
                                                <td className="w-10">
                                                    <button
                                                        type="button"
                                                        disabled={isDeleting}
                                                        onClick={() =>
                                                            setDelTarget({
                                                                id: c.id,
                                                                name:
                                                                    c.name ||
                                                                    "this contact",
                                                            })
                                                        }
                                                        className="inline-flex items-center justify-center size-7 rounded-full text-t-tertiary hover:text-primary-03 hover:bg-primary-03/10 transition-colors disabled:opacity-40"
                                                        title="Delete contact"
                                                        aria-label={`Delete ${c.name || "contact"}`}
                                                    >
                                                        <Icon
                                                            name="trash"
                                                            className="size-3.5 fill-current"
                                                        />
                                                    </button>
                                                </td>
                                            </TableRow>
                                        );
                                    })}
                                </Table>
                            )}
                            {!loading && sorted.length > 0 && contactsQuery.hasNextPage && (
                                <div className="flex justify-center py-4">
                                    <Button
                                        isStroke
                                        onClick={() => contactsQuery.fetchNextPage()}
                                        disabled={contactsQuery.isFetchingNextPage}
                                    >
                                        {contactsQuery.isFetchingNextPage
                                            ? "Loading…"
                                            : `Show more${
                                                  total > rawContacts.length
                                                      ? ` (${rawContacts.length} of ${total})`
                                                      : ""
                                              }`}
                                    </Button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <ConfirmDeleteModal
                open={!!delTarget}
                onClose={() => setDelTarget(null)}
                onConfirm={() => {
                    if (delTarget) handleDelete(delTarget.id);
                    setDelTarget(null);
                }}
                title="Delete this contact?"
                message={
                    <>
                        Delete{" "}
                        <span className="text-t-primary">
                            {delTarget?.name}
                        </span>{" "}
                        from your CRM? This action cannot be undone.
                    </>
                }
            />
        </Layout>
    );
}

// ── Core_2 Overview metric tile (ported inline; same structure as
// templates/Products/OverviewPage/Overview/Item, minus the mock chart) ──
function MetricItem({
    icon,
    title,
    value,
    sub,
    accent,
}: {
    icon: string;
    title: string;
    value: React.ReactNode;
    sub?: React.ReactNode;
    accent?: boolean;
}) {
    return (
        <div className="flex-1 min-w-44 pr-8 border-r border-s-subtle last:border-r-0 last:pr-0 max-lg:shrink-0">
            <div
                className={`flex items-center justify-center size-12 mb-6 rounded-full ${
                    accent ? "bg-primary-02/12" : "bg-b-surface1"
                }`}
            >
                <Icon
                    className={accent ? "fill-primary-02" : "fill-t-primary"}
                    name={icon}
                />
            </div>
            <div className="text-sub-title-1 text-t-secondary mb-2">{title}</div>
            <div className="text-h3">{value}</div>
            {sub && (
                <div className="mt-2 text-body-2 text-t-tertiary">{sub}</div>
            )}
        </div>
    );
}

// Score chip — token-based, mirrors lib/badges ScoreBadge styling.
function ScoreCell({ score, hot }: { score?: number | null; hot?: boolean }) {
    if (score == null || score === 0)
        return <span className="text-t-tertiary">—</span>;
    const tone =
        score >= 70
            ? "bg-primary-02/12 text-primary-02"
            : score >= 40
            ? "bg-primary-05/12 text-primary-05"
            : "bg-b-surface1 text-t-secondary";
    return (
        <span
            className={`inline-flex items-center gap-1.5 px-2.5 h-7 rounded-full text-button font-semibold ${tone}`}
        >
            {hot && <span className="size-1.5 rounded-full bg-primary-02" />}
            {score}
        </span>
    );
}

function TableSkeleton() {
    return (
        <Table
            cellsThead={[
                ...tableHead.map((col) => <th key={col.key}>{col.label}</th>),
                <th key="_del" className="w-10" />,
            ]}
        >
            {[...Array(7)].map((_, i) => (
                <TableRow key={i}>
                    {[...Array(tableHead.length + 1)].map((__, j) => (
                        <td key={j}>
                            <div
                                className={`skeleton h-4 rounded-lg ${
                                    j === 0
                                        ? "w-44"
                                        : j === tableHead.length - 1
                                        ? "w-16 ml-auto"
                                        : j === tableHead.length
                                        ? "w-6"
                                        : "w-20"
                                }`}
                            />
                        </td>
                    ))}
                </TableRow>
            ))}
        </Table>
    );
}

function EmptyState({
    query,
    lifecycleLabel,
    stageLabel,
    isAll,
    canClear,
    onClear,
}: {
    query: string;
    lifecycleLabel: string;
    stageLabel: string;
    isAll: boolean;
    canClear: boolean;
    onClear: () => void;
}) {
    const titleParts = ["No contacts in", stageLabel, lifecycleLabel !== "All" ? "\u00B7 " + lifecycleLabel : ""].filter(Boolean);
    return (
        <div className="py-16 text-center max-md:py-12">
            <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                <Icon
                    name={query ? "search" : "profile"}
                    className="fill-t-tertiary"
                />
            </span>
            <div className="text-h6 mb-1">
                {query
                    ? "No matching contacts"
                    : !isAll
                    ? titleParts.join(" ")
                    : "No contacts yet"}
            </div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                {query
                    ? ["Nothing matches", query, ". Try a different name or number."].join(" ")
                    : "Contacts appear here as people are called or message you \u2014 each one builds its own unified timeline."}
            </div>
            {canClear && (
                <Button className="mt-5" isStroke onClick={onClear}>
                    Clear filters
                </Button>
            )}
        </div>
    );
}
function DormantBody() {
    return (
        <div className="py-16 text-center max-md:py-12">
            <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                <Icon name="profile" className="fill-t-tertiary" />
            </span>
            <div className="text-h6 mb-1">CRM workspace is being prepared</div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                The unified contact spine is part of the Customer&nbsp;360 rollout.
                It stitches your leads, calls, and WhatsApp into one timeline per
                person. This view lights up automatically the moment the module is
                enabled for your workspace — nothing for you to do.
            </div>
            <span className="inline-block mt-5 px-3 h-8 leading-8 rounded-full bg-b-surface1 text-button text-t-secondary">
                Coming soon
            </span>
        </div>
    );
}
