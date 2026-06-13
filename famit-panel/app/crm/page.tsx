"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
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
import {
    getContacts,
    getSegments,
    CrmDormantError,
    isDormantResponse,
    type ContactListItem,
    type ContactsResponse,
    type Segment,
} from "./client";
import { StageBadge, initials, fmtRelative } from "./_ui";

// Stage filter tabs (mirrors §4.1 derivation order). "all" + hot are special.
const STAGE_TABS = [
    { id: 1, name: "All", key: "all" },
    { id: 2, name: "New", key: "new" },
    { id: 3, name: "Contacted", key: "contacted" },
    { id: 4, name: "Engaged", key: "engaged" },
    { id: 5, name: "Qualified", key: "qualified" },
    { id: 6, name: "Booked", key: "booked" },
    { id: 7, name: "Won", key: "won" },
    { id: 8, name: "Dormant", key: "dormant" },
];

const HOT_TABS = [
    { id: 1, name: "All" },
    { id: 2, name: "Hot" },
];

const tableHead = ["Contact", "Stage", "Score", "Last Outcome", "Last Activity"];

export default function CrmWorkspacePage() {
    // Filters (server-driven so they reflect the real read-model once mounted).
    const [stageTab, setStageTab] = useState(STAGE_TABS[0]);
    const [hotTab, setHotTab] = useState(HOT_TABS[0]);
    const [segment, setSegment] = useState<{ id: number; name: string } | null>(
        null
    );
    const [query, setQuery] = useState("");

    const [segments, setSegments] = useState<Segment[]>([]);

    const stage = stageTab.key;
    const hotOnly = hotTab.id === 2;
    // option.id (1-based) maps to segments[id-1]; id 0 = "All segments".
    const segmentId =
        segment && segment.id > 0 ? segments[segment.id - 1]?.id : undefined;

    // PERF UNIT-3: cached contacts list keyed by the active filters — switching
    // stage/hot/segment tabs and tab-back are instant (cache + bg revalidate),
    // and keepPreviousData keeps the current rows on screen while a new filter
    // loads. The queryFn normalises a thrown CrmDormantError into a dormant-marked
    // response so the existing dormant/empty rendering is preserved unchanged.
    const contactsQuery = useQuery<ContactsResponse>({
        queryKey: ["contacts", { stage, hotOnly, segmentId }],
        queryFn: async () => {
            try {
                return await getContacts({
                    stage: stage !== "all" ? stage : undefined,
                    hot: hotOnly || undefined,
                    segment: segmentId,
                    sort: "last_activity_at",
                    limit: 500,
                });
            } catch (e) {
                if (e instanceof CrmDormantError) {
                    return { contacts: [], total: 0, note: "dormant" } as ContactsResponse;
                }
                throw e;
            }
        },
        placeholderData: keepPreviousData,
    });

    const resp = contactsQuery.data;
    const dormant = !!resp && isDormantResponse(resp);
    const contacts: ContactListItem[] = useMemo(
        () => (dormant ? [] : resp?.contacts ?? []),
        [resp, dormant]
    );
    const total = dormant ? 0 : resp?.total ?? contacts.length;
    const error = contactsQuery.error
        ? contactsQuery.error instanceof Error
            ? contactsQuery.error.message
            : "Failed to load contacts"
        : "";
    const loading = contactsQuery.isLoading && contacts.length === 0;

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

    // Real summary signals from the loaded set (never a fabricated delta).
    const summary = useMemo(() => {
        const n = contacts.length;
        const hot = contacts.filter((c) => c.hot || (c.score ?? 0) >= 70).length;
        const qualified = contacts.filter((c) =>
            ["qualified", "booked", "won"].includes(c.stage)
        ).length;
        const engaged = contacts.filter((c) =>
            ["engaged", "qualified", "booked", "won"].includes(c.stage)
        ).length;
        const dormantCount = contacts.filter((c) => c.stage === "dormant").length;
        const scored = contacts.filter((c) => (c.score ?? 0) > 0);
        const avg =
            scored.length > 0
                ? Math.round(
                      scored.reduce((a, c) => a + (c.score ?? 0), 0) /
                          scored.length
                  )
                : null;
        return { n, hot, qualified, engaged, dormantCount, avg };
    }, [contacts]);

    const segmentOptions = useMemo(
        () => [
            { id: 0, name: "All segments" },
            ...segments.map((s, i) => ({ id: i + 1, name: s.name })),
        ],
        [segments]
    );

    const activeFilters =
        !!query || stage !== "all" || hotOnly || (segment && segment.id !== 0);

    const clearFilters = () => {
        setQuery("");
        setStageTab(STAGE_TABS[0]);
        setHotTab(HOT_TABS[0]);
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
                                        : summary.dormantCount > 0
                                        ? `${summary.dormantCount} dormant to re-engage`
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
                            {query === "" && (
                                <Tabs
                                    className="max-md:w-full"
                                    items={HOT_TABS}
                                    value={hotTab}
                                    setValue={setHotTab}
                                />
                            )}
                        </div>

                        {/* Stage filter tabs */}
                        {query === "" && (
                            <div className="px-2 pt-1 overflow-x-auto scrollbar-none">
                                <Tabs
                                    items={STAGE_TABS}
                                    value={stageTab}
                                    setValue={(v) =>
                                        setStageTab(v as (typeof STAGE_TABS)[number])
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
                            ) : visible.length === 0 ? (
                                <EmptyState
                                    query={query}
                                    hotOnly={hotOnly}
                                    stageLabel={stageTab.name}
                                    isAll={stage === "all"}
                                    canClear={!!activeFilters}
                                    onClear={clearFilters}
                                />
                            ) : (
                                <Table
                                    cellsThead={tableHead.map((head) => (
                                        <th
                                            className={
                                                head === "Last Activity"
                                                    ? "text-right max-md:hidden"
                                                    : head === "Last Outcome"
                                                    ? "max-lg:hidden"
                                                    : head === "Score"
                                                    ? "max-md:hidden"
                                                    : ""
                                            }
                                            key={head}
                                        >
                                            {head}
                                        </th>
                                    ))}
                                >
                                    {visible.map((c) => {
                                        const isHot =
                                            c.hot || (c.score ?? 0) >= 70;
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
                                                    <StageBadge
                                                        stage={c.stage}
                                                    />
                                                </td>
                                                <td className="max-md:hidden">
                                                    <ScoreCell
                                                        score={c.score}
                                                        hot={isHot}
                                                    />
                                                </td>
                                                <td className="text-t-secondary capitalize max-lg:hidden">
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
                                            </TableRow>
                                        );
                                    })}
                                </Table>
                            )}
                        </div>
                    </div>
                </div>
            )}
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
            cellsThead={tableHead.map((head) => (
                <th key={head}>{head}</th>
            ))}
        >
            {[...Array(7)].map((_, i) => (
                <TableRow key={i}>
                    {[...Array(5)].map((__, j) => (
                        <td key={j}>
                            <div
                                className={`skeleton h-4 rounded-lg ${
                                    j === 0 ? "w-44" : j === 4 ? "w-16 ml-auto" : "w-20"
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
    hotOnly,
    stageLabel,
    isAll,
    canClear,
    onClear,
}: {
    query: string;
    hotOnly: boolean;
    stageLabel: string;
    isAll: boolean;
    canClear: boolean;
    onClear: () => void;
}) {
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
                    : hotOnly
                    ? "No hot contacts yet"
                    : !isAll
                    ? `No contacts in “${stageLabel}”`
                    : "No contacts yet"}
            </div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                {query
                    ? `Nothing matches “${query}”. Try a different name or number.`
                    : "Contacts appear here as people are called or message you — each one builds its own unified timeline."}
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
