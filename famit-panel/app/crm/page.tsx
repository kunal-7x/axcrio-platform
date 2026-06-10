"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import PageHeader from "@/components/PageHeader";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import KpiCard from "@/components/KpiCard";
import {
    getContacts,
    getSegments,
    CrmDormantError,
    isDormantResponse,
    type ContactListItem,
    type Segment,
} from "./client";
import { StageBadge, initials, fmtRelative } from "./_ui";

// Stage filter chips (mirrors §4.1 derivation order). "all" + hot are special.
const STAGE_FILTERS: { id: string; label: string }[] = [
    { id: "all", label: "All" },
    { id: "new", label: "New" },
    { id: "contacted", label: "Contacted" },
    { id: "engaged", label: "Engaged" },
    { id: "qualified", label: "Qualified" },
    { id: "booked", label: "Booked" },
    { id: "won", label: "Won" },
    { id: "dormant", label: "Dormant" },
];

export default function CrmWorkspacePage() {
    const [contacts, setContacts] = useState<ContactListItem[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState("");

    // Filters (server-driven so they reflect the real read-model once mounted).
    const [stage, setStage] = useState("all");
    const [hotOnly, setHotOnly] = useState(false);
    const [segment, setSegment] = useState("");
    const [query, setQuery] = useState("");

    const [segments, setSegments] = useState<Segment[]>([]);

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getContacts({
            stage: stage !== "all" ? stage : undefined,
            hot: hotOnly || undefined,
            segment: segment || undefined,
            sort: "last_activity_at",
            limit: 500,
        })
            .then((r) => {
                // The live API answers 200 with a `note` (not a 404) when the
                // module / its PG is down — treat that as dormant, not an empty list.
                if (isDormantResponse(r)) {
                    setDormant(true);
                    setContacts([]);
                    setTotal(0);
                    return;
                }
                setContacts(r.contacts || []);
                setTotal(r.total ?? (r.contacts || []).length);
                setDormant(false);
            })
            .catch((e: unknown) => {
                if (e instanceof CrmDormantError) {
                    setDormant(true);
                    setContacts([]);
                    setTotal(0);
                } else {
                    setError(e instanceof Error ? e.message : "Failed to load contacts");
                }
            })
            .finally(() => setLoading(false));
    }, [stage, hotOnly, segment]);

    useEffect(() => {
        load();
    }, [load]);

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
                      scored.reduce((a, c) => a + (c.score ?? 0), 0) / scored.length
                  )
                : null;
        return {
            n,
            hot,
            qualified,
            engaged,
            dormantCount,
            avg,
            hotRatio: n > 0 ? hot / n : 0,
            qualifiedRatio: n > 0 ? qualified / n : 0,
            engagedRatio: n > 0 ? engaged / n : 0,
        };
    }, [contacts]);

    const activeSegmentName =
        segment && segments.find((s) => s.id === segment)?.name;

    return (
        <Layout title="CRM">
            <PageHeader
                eyebrow="Customer 360"
                title="CRM Workspace"
                subtitle="One spine per person — every call, message, and outcome unified, with a live stage, score, and next-best action."
            />

            {/* ── Dormant: the read-model isn't switched on yet ─────────── */}
            {dormant ? (
                <Card title="Customer 360">
                    <div className="state-block py-16">
                        <span className="state-glyph">
                            <Icon name="profile" className="fill-inherit" />
                        </span>
                        <div className="state-title">CRM workspace is being prepared</div>
                        <div className="state-sub max-w-md">
                            The unified contact spine is part of the Customer&nbsp;360
                            rollout. It stitches your leads, calls, and WhatsApp into one
                            timeline per person. This view lights up automatically the
                            moment the module is enabled for your workspace — nothing for
                            you to do.
                        </div>
                        <span className="nav-soon mt-1">Coming soon</span>
                    </div>
                </Card>
            ) : (
                <>
                    {/* ── Hero KPI row — real meters over the loaded set ── */}
                    <div className="grid grid-cols-4 gap-3 mb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                        <KpiCard
                            label="Contacts"
                            value={loading ? "—" : total}
                            icon="profile"
                            tone="info"
                            sub={
                                loading
                                    ? undefined
                                    : total === 0
                                    ? "Awaiting first contacts"
                                    : `${summary.engaged} engaged or better`
                            }
                            meter={loading ? null : summary.engagedRatio}
                            style={{ animationDelay: "0ms" }}
                        />
                        <KpiCard
                            label="Hot · 70+"
                            value={loading ? "—" : summary.hot}
                            icon="star-fill"
                            tone="success"
                            sub={
                                loading || summary.n === 0 ? undefined : (
                                    <span className="text-primary-02">
                                        {Math.round(summary.hotRatio * 100)}% of loaded
                                    </span>
                                )
                            }
                            meter={loading ? null : summary.hotRatio}
                            style={{ animationDelay: "60ms" }}
                        />
                        <KpiCard
                            label="Qualified+"
                            value={loading ? "—" : summary.qualified}
                            icon="check-circle"
                            tone="warning"
                            sub={
                                loading || summary.n === 0
                                    ? undefined
                                    : `${Math.round(summary.qualifiedRatio * 100)}% reached qualified`
                            }
                            meter={loading ? null : summary.qualifiedRatio}
                            style={{ animationDelay: "120ms" }}
                        />
                        <KpiCard
                            label="Avg Score"
                            value={loading ? "—" : summary.avg != null ? summary.avg : "—"}
                            icon="chart"
                            tone="neutral"
                            sub={
                                loading
                                    ? undefined
                                    : summary.dormantCount > 0
                                    ? `${summary.dormantCount} dormant to re-engage`
                                    : summary.avg == null
                                    ? "No scored contacts yet"
                                    : "0-100 interest scale"
                            }
                            meter={
                                loading || summary.avg == null ? null : summary.avg / 100
                            }
                            style={{ animationDelay: "180ms" }}
                        />
                    </div>

                    <Card
                        title="Contacts"
                        headContent={
                            <div className="flex items-center gap-2.5 max-md:gap-2">
                                <label className="relative hidden sm:flex items-center">
                                    <Icon
                                        name="search"
                                        className="absolute left-3 size-4 fill-t-tertiary pointer-events-none"
                                    />
                                    <input
                                        value={query}
                                        onChange={(e) => setQuery(e.target.value)}
                                        placeholder="Search name or phone"
                                        className="input-base h-9 w-56 max-lg:w-40 pl-9 pr-3 rounded-full text-body-2"
                                    />
                                </label>
                                {/* Segment filter — only shown when segments exist */}
                                {segments.length > 0 && (
                                    <select
                                        value={segment}
                                        onChange={(e) => setSegment(e.target.value)}
                                        className="input-base h-9 px-3 rounded-full text-body-2 max-md:hidden"
                                        aria-label="Filter by segment"
                                    >
                                        <option value="">All segments</option>
                                        {segments.map((s) => (
                                            <option key={s.id} value={s.id}>
                                                {s.name}
                                            </option>
                                        ))}
                                    </select>
                                )}
                                <div className="inline-flex p-1 rounded-full bg-b-surface1 border border-s-subtle dark:bg-shade-04/40">
                                    <SegBtn active={!hotOnly} onClick={() => setHotOnly(false)}>
                                        All
                                    </SegBtn>
                                    <SegBtn active={hotOnly} onClick={() => setHotOnly(true)}>
                                        Hot
                                    </SegBtn>
                                </div>
                            </div>
                        }
                    >
                        {/* Stage filter chips */}
                        <div className="flex items-center gap-1.5 px-5 pb-3 overflow-x-auto max-lg:px-3">
                            {STAGE_FILTERS.map((s) => (
                                <button
                                    key={s.id}
                                    onClick={() => setStage(s.id)}
                                    className={`shrink-0 px-3 h-8 rounded-full text-button transition-all ${
                                        stage === s.id
                                            ? "bg-b-surface2 text-t-primary shadow-widget ring-1 ring-s-subtle"
                                            : "text-t-secondary hover:text-t-primary hover:bg-b-surface1 dark:hover:bg-shade-04/40"
                                    }`}
                                >
                                    {s.label}
                                </button>
                            ))}
                        </div>

                        {/* Count strip */}
                        {!loading && contacts.length > 0 && (
                            <div className="flex items-center justify-between px-5 pb-3 max-lg:px-3">
                                <span className="eyebrow">
                                    {visible.length}
                                    {query ? ` of ${contacts.length}` : ""}{" "}
                                    {visible.length === 1 ? "contact" : "contacts"}
                                    {activeSegmentName ? ` · ${activeSegmentName}` : ""}
                                </span>
                                {summary.hot > 0 && !hotOnly && (
                                    <span className="flex items-center gap-1.5 text-caption text-t-tertiary">
                                        <span className="size-1.5 rounded-full bg-primary-02" />
                                        {summary.hot} hot
                                    </span>
                                )}
                            </div>
                        )}

                        {error && (
                            <div className="mx-5 mb-3 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03 max-lg:mx-3">
                                <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                                {error}
                            </div>
                        )}

                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Contact</th>
                                        <th>Stage</th>
                                        <th>Score</th>
                                        <th>Last Outcome</th>
                                        <th className="text-right">Last Activity</th>
                                        <th className="w-8" />
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
                                                                    ? "w-40"
                                                                    : j === 4
                                                                    ? "w-16 ml-auto"
                                                                    : "w-20"
                                                            }`}
                                                        />
                                                    </td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : visible.length === 0 ? (
                                        <tr>
                                            <td colSpan={6}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon
                                                            name={query ? "search" : "profile"}
                                                            className="fill-inherit"
                                                        />
                                                    </span>
                                                    <div className="state-title">
                                                        {query
                                                            ? "No matching contacts"
                                                            : hotOnly
                                                            ? "No hot contacts yet"
                                                            : stage !== "all"
                                                            ? `No contacts in “${
                                                                  STAGE_FILTERS.find(
                                                                      (s) => s.id === stage
                                                                  )?.label ?? stage
                                                              }”`
                                                            : "No contacts yet"}
                                                    </div>
                                                    <div className="state-sub">
                                                        {query
                                                            ? `Nothing matches “${query}”. Try a different name or number.`
                                                            : "Contacts appear here as people are called or message you — each one builds its own unified timeline."}
                                                    </div>
                                                    {(query || stage !== "all" || hotOnly || segment) && (
                                                        <Button
                                                            isStroke
                                                            className="mt-1"
                                                            onClick={() => {
                                                                setQuery("");
                                                                setStage("all");
                                                                setHotOnly(false);
                                                                setSegment("");
                                                            }}
                                                        >
                                                            Clear filters
                                                        </Button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        visible.map((c, i) => {
                                            const isHot = c.hot || (c.score ?? 0) >= 70;
                                            return (
                                                <tr
                                                    key={c.id}
                                                    className="rise-in is-clickable group"
                                                    style={{
                                                        animationDelay: `${Math.min(i * 25, 300)}ms`,
                                                    }}
                                                >
                                                    <td className="font-medium text-t-primary">
                                                        <Link
                                                            href={`/crm/${encodeURIComponent(c.id)}`}
                                                            className="flex items-center gap-2.5"
                                                        >
                                                            <span
                                                                className={`grid place-items-center size-9 shrink-0 rounded-full text-caption font-semibold ${
                                                                    isHot
                                                                        ? "bg-primary-02/12 text-primary-02"
                                                                        : "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                                                                }`}
                                                            >
                                                                {initials(c.name)}
                                                            </span>
                                                            <span className="min-w-0">
                                                                <span className="block truncate max-w-48 text-t-primary">
                                                                    {c.name || "Unknown"}
                                                                </span>
                                                                <span className="block truncate max-w-48 text-caption text-t-tertiary td-num">
                                                                    {c.phone_display || "—"}
                                                                </span>
                                                            </span>
                                                        </Link>
                                                    </td>
                                                    <td>
                                                        <StageBadge stage={c.stage} />
                                                    </td>
                                                    <td>
                                                        <ScoreCell score={c.score} hot={isHot} />
                                                    </td>
                                                    <td className="text-t-secondary text-caption capitalize">
                                                        {c.last_outcome
                                                            ? c.last_outcome.replace(/_/g, " ")
                                                            : "—"}
                                                    </td>
                                                    <td className="text-t-secondary td-num text-right">
                                                        {fmtRelative(c.last_activity_at)}
                                                    </td>
                                                    <td className="text-right">
                                                        <Link
                                                            href={`/crm/${encodeURIComponent(c.id)}`}
                                                            className="inline-grid place-items-center size-7 rounded-full text-t-tertiary opacity-0 group-hover:opacity-100 transition-opacity hover:bg-b-surface1 dark:hover:bg-shade-04/60"
                                                            aria-label="Open profile"
                                                        >
                                                            <Icon
                                                                name="arrow"
                                                                className="size-4 fill-t-secondary"
                                                            />
                                                        </Link>
                                                    </td>
                                                </tr>
                                            );
                                        })
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </>
            )}
        </Layout>
    );
}

// Score chip — token-based, mirrors lib/badges ScoreBadge styling without
// touching the shared module.
function ScoreCell({ score, hot }: { score?: number | null; hot?: boolean }) {
    if (score == null || score === 0)
        return <span className="text-t-tertiary">—</span>;
    const tone =
        score >= 70
            ? "bg-primary-02/12 text-primary-02"
            : score >= 40
            ? "bg-primary-05/12 text-primary-05"
            : "bg-b-surface1 text-t-secondary dark:bg-shade-04/60";
    return (
        <span
            className={`inline-flex items-center gap-1.5 px-2.5 h-6 rounded-full text-caption font-semibold td-num ${tone}`}
        >
            {hot && <span className="size-1.5 rounded-full bg-primary-02" />}
            {score}
        </span>
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
