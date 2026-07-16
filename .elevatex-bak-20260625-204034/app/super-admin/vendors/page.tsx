"use client";

// Vendors — the Super Admin fleet list (CL-F1, design/control-ui.md §2.2).
//
// Archetype: List/Table with search + status tabs. Ported from the Core_2
// Customers/CustomerList/CustomerListPage header rhythm (title + Search + Tabs)
// onto our `data-table` Signal style, rewired onto GET /admin/vendors (which
// gracefully composes from /usage/all + /tenants until the richer endpoint
// ships). Row click → /super-admin/vendors/[id] (the Vendor Workspace, a later
// unit; the route is authored here so the list is navigation-ready).
//
// ADMIN PLANE: nav-gated `roles:"admin"` + the backend require_super_admin is
// the real boundary. This page is a read-only fleet list.

import { useEffect, useMemo, useState, useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import { getFleetVendors, type FleetVendor, type VendorAccountStatus } from "@/lib/api";
import { AdminHeader, ErrorBanner, ghostBtnCls, StatusPill, SuperAdminGuard, num, ago } from "../_shared";

// Status filter tabs (design §2.2). "all" is the default lens.
const STATUS_TABS: { key: "all" | VendorAccountStatus; label: string }[] = [
    { key: "all", label: "All" },
    { key: "active", label: "Active" },
    { key: "trial", label: "Trial" },
    { key: "suspended", label: "Suspended" },
    { key: "disabled", label: "Disabled" },
    { key: "expired", label: "Expired" },
];

type SortKey = "name" | "calls_30d" | "minutes_30d" | "last_active";

function VendorsInner() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const focus = searchParams.get("focus") || "";

    const [vendors, setVendors] = useState<FleetVendor[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [query, setQuery] = useState("");
    const [tab, setTab] = useState<"all" | VendorAccountStatus>("all");
    const [sort, setSort] = useState<SortKey>("calls_30d");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getFleetVendors()
            .then((r) => setVendors(r.vendors))
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load vendors"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // Deep-link from the Overview leaderboard: ?focus=<tenant_id> prefills the
    // search so the linked vendor is immediately surfaced.
    useEffect(() => {
        if (focus) {
            const v = vendors.find((x) => x.tenant_id === focus);
            if (v) setQuery(v.name);
        }
    }, [focus, vendors]);

    // Per-tab counts for the tab pills.
    const counts = useMemo(() => {
        const c: Record<string, number> = { all: vendors.length };
        for (const v of vendors) {
            const s = v.status ?? "active";
            c[s] = (c[s] ?? 0) + 1;
        }
        return c;
    }, [vendors]);

    const filtered = useMemo(() => {
        const q = query.trim().toLowerCase();
        let rows = vendors.filter((v) => {
            if (tab !== "all" && (v.status ?? "active") !== tab) return false;
            if (!q) return true;
            return (
                v.name.toLowerCase().includes(q) ||
                (v.email || "").toLowerCase().includes(q) ||
                (v.plan || "").toLowerCase().includes(q) ||
                v.tenant_id.toLowerCase().includes(q)
            );
        });
        rows = [...rows].sort((a, b) => {
            switch (sort) {
                case "name":
                    return a.name.localeCompare(b.name);
                case "minutes_30d":
                    return (b.usage_summary?.minutes_30d ?? 0) - (a.usage_summary?.minutes_30d ?? 0);
                case "last_active": {
                    const at = new Date(a.health?.last_activity || a.health?.last_call_at || 0).getTime();
                    const bt = new Date(b.health?.last_activity || b.health?.last_call_at || 0).getTime();
                    return bt - at;
                }
                case "calls_30d":
                default:
                    return (b.usage_summary?.calls_30d ?? 0) - (a.usage_summary?.calls_30d ?? 0);
            }
        });
        return rows;
    }, [vendors, query, tab, sort]);

    return (
        <Layout title="Vendors">
            <AdminHeader
                actions={
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                        {loading ? "Refreshing…" : "Refresh"}
                    </button>
                }
            />
            <ErrorBanner msg={error} />

            {/* Toolbar — search + status tabs (the CustomerListPage header) */}
            <div className="flex items-center gap-3 mb-4 flex-wrap">
                <div className="relative flex-1 min-w-60 max-w-100">
                    <Icon
                        name="search"
                        className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 fill-t-tertiary pointer-events-none"
                    />
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search vendors by name, email or plan…"
                        className="input-base w-full h-10 pl-10 pr-4 rounded-2xl text-body-2"
                    />
                    {query && (
                        <button
                            onClick={() => setQuery("")}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-t-tertiary hover:text-t-primary text-lg leading-none"
                            aria-label="Clear search"
                        >
                            ×
                        </button>
                    )}
                </div>
                <div className="flex items-center gap-1 overflow-x-auto scrollbar-none">
                    {STATUS_TABS.map((t) => {
                        const active = tab === t.key;
                        const count = counts[t.key] ?? 0;
                        return (
                            <button
                                key={t.key}
                                onClick={() => setTab(t.key)}
                                className={`shrink-0 inline-flex items-center gap-1.5 h-10 px-4 rounded-full border text-button transition-colors hover:text-t-primary ${
                                    active
                                        ? "border-s-stroke2 text-t-primary"
                                        : "border-transparent text-t-secondary"
                                }`}
                            >
                                {t.label}
                                <span className={`text-caption tabular-nums ${active ? "text-t-secondary" : "text-t-tertiary"}`}>
                                    {count}
                                </span>
                            </button>
                        );
                    })}
                </div>
            </div>

            <Card
                title="Fleet"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="profile" className="size-3.5 fill-t-tertiary" />
                        {loading ? "Loading…" : `${filtered.length} of ${vendors.length}`}
                    </span>
                }
            >
                <div className="overflow-x-auto px-3 pb-2">
                    <table className="data-table is-clickable">
                        <thead>
                            <tr>
                                <SortTh label="Vendor" k="name" sort={sort} setSort={setSort} />
                                <th>Plan</th>
                                <th>Status</th>
                                <SortTh label="Calls · 30d" k="calls_30d" sort={sort} setSort={setSort} align="right" />
                                <SortTh label="Minutes" k="minutes_30d" sort={sort} setSort={setSort} align="right" />
                                <SortTh label="Last active" k="last_active" sort={sort} setSort={setSort} />
                            </tr>
                        </thead>
                        <tbody>
                            {loading && vendors.length === 0 ? (
                                [...Array(6)].map((_, i) => (
                                    <tr key={i}>
                                        <td><div className="skeleton h-4 w-36" /></td>
                                        <td><div className="skeleton h-4 w-16" /></td>
                                        <td><div className="skeleton h-5 w-16 rounded-md" /></td>
                                        <td><div className="skeleton h-4 w-12 ml-auto" /></td>
                                        <td><div className="skeleton h-4 w-12 ml-auto" /></td>
                                        <td><div className="skeleton h-4 w-20" /></td>
                                    </tr>
                                ))
                            ) : filtered.length === 0 ? (
                                <tr>
                                    <td colSpan={6}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name={query || tab !== "all" ? "search" : "profile"} className="fill-inherit" />
                                            </span>
                                            <div className="state-title">
                                                {query || tab !== "all" ? "No matching vendors" : "No vendors yet"}
                                            </div>
                                            <div className="state-sub">
                                                {query || tab !== "all"
                                                    ? "Try a different search term or status filter."
                                                    : "Vendor accounts appear here as they are onboarded to the platform."}
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                filtered.map((v) => (
                                    <tr
                                        key={v.tenant_id}
                                        className={`cursor-pointer ${focus && v.tenant_id === focus ? "bg-b-surface1/60 dark:bg-shade-04/30" : ""}`}
                                        onClick={() => router.push(`/super-admin/vendors/${v.tenant_id}`)}
                                    >
                                        <td>
                                            <div className="flex items-center gap-2.5">
                                                <span className="grid place-items-center size-8 shrink-0 rounded-xl bg-b-surface1 text-button text-t-secondary dark:bg-shade-04/60">
                                                    {(v.name || "?").charAt(0).toUpperCase()}
                                                </span>
                                                <span className="min-w-0">
                                                    <span className="block font-medium text-t-primary truncate">{v.name}</span>
                                                    {v.email && <span className="block text-caption text-t-tertiary truncate">{v.email}</span>}
                                                </span>
                                            </div>
                                        </td>
                                        <td>
                                            {v.plan ? (
                                                <Badge variant="neutral">{v.plan}</Badge>
                                            ) : (
                                                <span className="text-t-tertiary">—</span>
                                            )}
                                        </td>
                                        <td><StatusPill status={v.status} /></td>
                                        <td className="td-num text-right font-medium text-t-primary">{num(v.usage_summary?.calls_30d ?? 0)}</td>
                                        <td className="td-num text-right text-t-secondary">{num(v.usage_summary?.minutes_30d ?? 0)}</td>
                                        <td className="text-t-secondary whitespace-nowrap">
                                            {ago(v.health?.last_activity || v.health?.last_call_at)}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>
        </Layout>
    );
}

// Sortable column header — clicking sets the active sort key.
function SortTh({
    label,
    k,
    sort,
    setSort,
    align,
}: {
    label: string;
    k: SortKey;
    sort: SortKey;
    setSort: (k: SortKey) => void;
    align?: "right";
}) {
    const active = sort === k;
    return (
        <th className={align === "right" ? "text-right" : undefined}>
            <button
                onClick={() => setSort(k)}
                className={`inline-flex items-center gap-1 text-overline transition-colors hover:text-t-primary ${
                    active ? "text-t-primary" : ""
                } ${align === "right" ? "flex-row-reverse" : ""}`}
            >
                {label}
                <Icon
                    name="chevron"
                    className={`size-3 fill-current transition-opacity ${active ? "opacity-100" : "opacity-0"}`}
                />
            </button>
        </th>
    );
}

// useSearchParams requires a Suspense boundary in the App Router. Admin-gated
// (cosmetic — the backend require_super_admin is the real boundary).
export default function VendorsPage() {
    return (
        <SuperAdminGuard>
            <Suspense fallback={<Layout title="Vendors"><div className="state-block"><div className="skeleton h-6 w-40" /></div></Layout>}>
                <VendorsInner />
            </Suspense>
        </SuperAdminGuard>
    );
}
