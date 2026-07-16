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
import { useRealtimeRefresh } from "@/app/ads/_lib";
import { AdminHeader, ErrorBanner, ghostBtnCls, StatusPill, SuperAdminGuard, HeroCard, num, ago } from "../_shared";
import {
    getVendorsAdRoi,
    deriveRoiTotals,
    healthMeta,
    fmtMoney,
    fmtRoas,
    type VendorAdRoi,
    type VendorsAdRoiResponse,
} from "./_ads-roi";

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

// The two lenses over the same fleet: the operational Fleet list (calls/minutes/
// status) and the cross-tenant Ad ROI god-view (spend/leads/qualified/ROAS/health).
// Both read-only; Ad ROI is super-admin-only + audited server-side.
type Lens = "fleet" | "ad-roi";

// Ad-ROI sortable columns.
type RoiSortKey = "spend" | "leads" | "qualified" | "roas";

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

    // Ad-ROI lens state — its own dormant-safe read, kept separate from the fleet
    // list so the operational view never regresses if the ROI route is dormant.
    const [lens, setLens] = useState<Lens>("fleet");
    const [roi, setRoi] = useState<VendorsAdRoiResponse | null>(null);
    const [roiState, setRoiState] = useState<"loading" | "ok" | "dormant" | "error">("loading");
    const [roiError, setRoiError] = useState("");
    const [roiSort, setRoiSort] = useState<RoiSortKey>("spend");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getFleetVendors()
            .then((r) => setVendors(r.vendors))
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load vendors"))
            .finally(() => setLoading(false));
    }, []);

    // Cross-tenant Ad-ROI read — dormant-safe (never throws). Renders the premium
    // DormantPanel until /admin/ads/roi is mounted; a real non-200 → error block.
    const loadRoi = useCallback(() => {
        getVendorsAdRoi().then((r) => {
            if (r.kind === "ok") {
                setRoi(r.data);
                setRoiState("ok");
                setRoiError("");
            } else if (r.kind === "dormant") {
                setRoiState("dormant");
            } else {
                setRoiError(r.message);
                setRoiState("error");
            }
        });
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // Load the ROI rollup once the admin switches to that lens (lazy — the fleet
    // list is the default landing).
    useEffect(() => {
        if (lens === "ad-roi" && !roi && roiState !== "error") loadRoi();
    }, [lens, roi, roiState, loadRoi]);

    // 30s visibility-gated realtime: refresh whichever lens is showing so live
    // spend/ROAS and calls stay fresh without a manual click (Idiom 1).
    useRealtimeRefresh(lens === "ad-roi" ? loadRoi : load, 30000);

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

    // Ad-ROI rows: same search box (name/tenant), sorted by the active ROI column.
    const roiVendors = roi?.vendors ?? [];
    const roiTotals = useMemo(
        () => roi?.totals ?? deriveRoiTotals(roiVendors),
        [roi?.totals, roiVendors]
    );
    const roiCurrency = roi?.currency || "INR";
    const roiFiltered = useMemo(() => {
        const q = query.trim().toLowerCase();
        let rows = roiVendors.filter((v) => {
            if (!q) return true;
            return (v.name || "").toLowerCase().includes(q) || v.tenant_id.toLowerCase().includes(q);
        });
        rows = [...rows].sort((a, b) => {
            switch (roiSort) {
                case "leads":
                    return (b.leads_30d ?? 0) - (a.leads_30d ?? 0);
                case "qualified":
                    return (b.qualified_30d ?? 0) - (a.qualified_30d ?? 0);
                case "roas":
                    return (b.roas ?? 0) - (a.roas ?? 0);
                case "spend":
                default:
                    return (b.spend_30d_minor ?? 0) - (a.spend_30d_minor ?? 0);
            }
        });
        return rows;
    }, [roiVendors, query, roiSort]);

    return (
        <Layout title="Vendors">
            <AdminHeader
                actions={
                    <button
                        onClick={() => (lens === "ad-roi" ? loadRoi() : load())}
                        className={ghostBtnCls}
                        disabled={lens === "fleet" ? loading : roiState === "loading"}
                    >
                        <Icon
                            name="clock"
                            className={`size-4 fill-current ${(lens === "fleet" ? loading : roiState === "loading") ? "animate-spin" : ""}`}
                        />
                        {(lens === "fleet" ? loading : roiState === "loading") ? "Refreshing…" : "Refresh"}
                    </button>
                }
            />
            <ErrorBanner msg={lens === "fleet" ? error : ""} />

            {/* Lens toggle — the operational Fleet list vs the cross-tenant Ad ROI
                god-view. Same transparent-pill idiom as the status tabs below. */}
            <div className="flex items-center gap-1 mb-4">
                {([
                    { key: "fleet", label: "Fleet" },
                    { key: "ad-roi", label: "Ad ROI" },
                ] as { key: Lens; label: string }[]).map((l) => {
                    const active = lens === l.key;
                    return (
                        <button
                            key={l.key}
                            onClick={() => setLens(l.key)}
                            className={`shrink-0 inline-flex items-center gap-1.5 h-10 px-4 rounded-full border text-button transition-colors hover:text-t-primary ${
                                active ? "border-s-stroke2 text-t-primary" : "border-transparent text-t-secondary"
                            }`}
                        >
                            {l.key === "ad-roi" && (
                                <Icon name="chart" className="size-4 fill-current" />
                            )}
                            {l.label}
                        </button>
                    );
                })}
            </div>

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
                        placeholder={
                            lens === "ad-roi"
                                ? "Search vendors by name or tenant…"
                                : "Search vendors by name, email or plan…"
                        }
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
                {lens === "fleet" && (
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
                )}
            </div>

            {lens === "fleet" && (
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
            )}

            {/* ───────── Ad ROI lens — cross-tenant god-view (read-only, audited) ───────── */}
            {lens === "ad-roi" && (
                <AdRoiView
                    state={roiState}
                    error={roiError}
                    totals={roiTotals}
                    currency={roiCurrency}
                    rows={roiFiltered}
                    totalCount={roiVendors.length}
                    sort={roiSort}
                    setSort={setRoiSort}
                    searching={query.trim().length > 0}
                    onRetry={() => {
                        setRoiState("loading");
                        setRoiError("");
                        loadRoi();
                    }}
                    onRowClick={(id) => router.push(`/super-admin/vendors/${id}`)}
                />
            )}
        </Layout>
    );
}

// ───────── Ad ROI god-view body ─────────
// Cross-tenant aggregate ad spend / ROAS / campaign-health per vendor. Read-only
// by contract (no write controls) — the super-admin oversight path. Dormant-safe:
// an unmounted /admin/ads/roi route renders the premium "coming soon" panel, a
// real non-200 renders an inline error with Retry, never an error wall.
function AdRoiView({
    state,
    error,
    totals,
    currency,
    rows,
    totalCount,
    sort,
    setSort,
    searching,
    onRetry,
    onRowClick,
}: {
    state: "loading" | "ok" | "dormant" | "error";
    error: string;
    totals: NonNullable<VendorsAdRoiResponse["totals"]>;
    currency: string;
    rows: VendorAdRoi[];
    totalCount: number;
    sort: RoiSortKey;
    setSort: (k: RoiSortKey) => void;
    searching: boolean;
    onRetry: () => void;
    onRowClick: (id: string) => void;
}) {
    // Dormant — the ROI route isn't mounted yet (FEATURE_ADS=0). Premium explainer,
    // never an error. Names what the admin controls to light it up.
    if (state === "dormant") {
        return (
            <Card title="Ad ROI">
                <div className="px-3 pb-3">
                    <div className="state-block">
                        <span className="state-glyph">
                            <Icon name="chart" className="fill-inherit" />
                        </span>
                        <div className="state-title">Ad ROI is warming up</div>
                        <div className="state-sub">
                            Once vendors connect a Meta or Google ad account and start spending, their
                            cross-tenant spend, leads, and ROAS roll up here.
                        </div>
                    </div>
                </div>
            </Card>
        );
    }

    // Real failure — state what happened + how to recover.
    if (state === "error") {
        return (
            <Card title="Ad ROI">
                <div className="px-3 pb-3">
                    <div className="state-block">
                        <span className="state-glyph">
                            <Icon name="info" className="fill-inherit" />
                        </span>
                        <div className="state-title">Couldn&apos;t load ad ROI</div>
                        <div className="state-sub">{error || "The roll-up didn't come back. Try again."}</div>
                        <button onClick={onRetry} className={`${ghostBtnCls} mt-4`}>
                            <Icon name="clock" className="size-4 fill-current" />
                            Try again
                        </button>
                    </div>
                </div>
            </Card>
        );
    }

    const loading = state === "loading";

    return (
        <>
            {/* Fleet-wide KPI strip — the blended cross-tenant picture (30d). */}
            <div className="grid grid-cols-5 max-xl:grid-cols-3 max-md:grid-cols-2 gap-3 mb-4">
                <HeroCard
                    label="Spend · 30d"
                    glyph="usd-circle"
                    accent="var(--primary-01)"
                    value={fmtMoney(totals.spend_30d_minor, currency)}
                    loading={loading}
                    delay={0}
                />
                <HeroCard
                    label="Revenue · 30d"
                    glyph="wallet"
                    value={fmtMoney(totals.revenue_30d_minor, currency)}
                    loading={loading}
                    delay={40}
                />
                <HeroCard
                    label="Blended ROAS"
                    glyph="chart"
                    value={fmtRoas(totals.roas)}
                    loading={loading}
                    delay={80}
                />
                <HeroCard
                    label="Leads · 30d"
                    glyph="profile"
                    value={num(totals.leads_30d ?? 0)}
                    foot={`${num(totals.qualified_30d ?? 0)} qualified`}
                    loading={loading}
                    delay={120}
                />
                <HeroCard
                    label="Active vendors"
                    glyph="dashboard"
                    value={num(totals.active_vendors ?? 0)}
                    foot="spending in last 30d"
                    loading={loading}
                    delay={160}
                />
            </div>

            <Card
                title="Ad ROI by vendor"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="profile" className="size-3.5 fill-t-tertiary" />
                        {loading ? "Loading…" : `${rows.length} of ${totalCount}`}
                    </span>
                }
            >
                <div className="overflow-x-auto px-3 pb-2">
                    <table className="data-table is-clickable">
                        <thead>
                            <tr>
                                <th>Vendor</th>
                                <RoiSortTh label="Spend · 30d" k="spend" sort={sort} setSort={setSort} align="right" />
                                <RoiSortTh label="Leads" k="leads" sort={sort} setSort={setSort} align="right" />
                                <RoiSortTh label="Qualified" k="qualified" sort={sort} setSort={setSort} align="right" />
                                <th className="text-right">CPL</th>
                                <RoiSortTh label="ROAS" k="roas" sort={sort} setSort={setSort} align="right" />
                                <th>Campaign health</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && rows.length === 0 ? (
                                [...Array(6)].map((_, i) => (
                                    <tr key={i}>
                                        <td><div className="skeleton h-4 w-36" /></td>
                                        <td><div className="skeleton h-4 w-16 ml-auto" /></td>
                                        <td><div className="skeleton h-4 w-12 ml-auto" /></td>
                                        <td><div className="skeleton h-4 w-12 ml-auto" /></td>
                                        <td><div className="skeleton h-4 w-14 ml-auto" /></td>
                                        <td><div className="skeleton h-4 w-12 ml-auto" /></td>
                                        <td><div className="skeleton h-5 w-20 rounded-md" /></td>
                                    </tr>
                                ))
                            ) : rows.length === 0 ? (
                                <tr>
                                    <td colSpan={7}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name={searching ? "search" : "chart"} className="fill-inherit" />
                                            </span>
                                            <div className="state-title">
                                                {searching ? "No matching vendors" : "No ad spend yet"}
                                            </div>
                                            <div className="state-sub">
                                                {searching
                                                    ? "Try a different search term."
                                                    : "Vendor ad spend and ROAS appear here once campaigns go live."}
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                rows.map((v) => {
                                    const h = healthMeta(v.campaign_health);
                                    return (
                                        <tr
                                            key={v.tenant_id}
                                            className="cursor-pointer"
                                            onClick={() => onRowClick(v.tenant_id)}
                                        >
                                            <td>
                                                <div className="flex items-center gap-2.5">
                                                    <span className="grid place-items-center size-8 shrink-0 rounded-xl bg-b-surface1 text-button text-t-secondary dark:bg-shade-04/60">
                                                        {(v.name || "?").charAt(0).toUpperCase()}
                                                    </span>
                                                    <span className="min-w-0">
                                                        <span className="block font-medium text-t-primary truncate">{v.name || v.tenant_id}</span>
                                                        <span className="block text-caption text-t-tertiary truncate">
                                                            {num(v.active_campaigns ?? 0)} active campaign{(v.active_campaigns ?? 0) === 1 ? "" : "s"}
                                                        </span>
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="td-num text-right font-medium text-t-primary">{fmtMoney(v.spend_30d_minor, v.currency || currency)}</td>
                                            <td className="td-num text-right text-t-secondary">{num(v.leads_30d ?? 0)}</td>
                                            <td className="td-num text-right text-t-secondary">{num(v.qualified_30d ?? 0)}</td>
                                            <td className="td-num text-right text-t-secondary">{fmtMoney(v.cpl_minor, v.currency || currency)}</td>
                                            <td className="td-num text-right font-medium text-t-primary">{fmtRoas(v.roas)}</td>
                                            <td><Badge variant={h.variant} dot={h.dot}>{h.label}</Badge></td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>
        </>
    );
}

// Sortable column header for the Ad-ROI table (numeric, descending lenses).
function RoiSortTh({
    label,
    k,
    sort,
    setSort,
    align,
}: {
    label: string;
    k: RoiSortKey;
    sort: RoiSortKey;
    setSort: (k: RoiSortKey) => void;
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
