"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import { getBillingOverview, type BillingOverview } from "@/lib/api";
import {
    money,
    fmt,
    StatusBadge,
    ErrorBanner,
    ghostBtnCls,
    HeroCard,
    CostDonut,
    ShareRow,
    VENDOR_COLORS,
    BillingHeader,
} from "../_shared";

export default function BillingOverviewPage() {
    const [data, setData] = useState<BillingOverview | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getBillingOverview()
            .then(setData)
            .catch((e) =>
                setError(
                    e instanceof Error
                        ? e.message
                        : "Failed to load billing overview"
                )
            )
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const currency = data?.currency || "";
    const vendors = useMemo(() => data?.per_vendor ?? [], [data]);

    // Real signals only — no fabricated period deltas.
    const grandTotal = data?.grand_total ?? 0;
    const configuredCount = vendors.filter((v) => v.status === "configured").length;
    const sorted = useMemo(
        () => [...vendors].sort((a, b) => b.cost - a.cost),
        [vendors]
    );
    const topVendor = sorted[0];
    const totalForShare = sorted.reduce((s, v) => s + Math.max(v.cost, 0), 0);
    const donutSlices = sorted.map((v, i) => ({
        name: v.display_name,
        value: Math.max(v.cost, 0),
        color: VENDOR_COLORS[i % VENDOR_COLORS.length],
    }));

    return (
        <Layout title="Billing · Overview">
            <BillingHeader
                title="Billing Overview"
                subtitle="Real metered spend across every vendor — telephony, voice, language and LLM — rolled up for this period."
                actions={
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon
                            name="clock"
                            className={`size-4 fill-current ${loading ? "animate-spin" : ""}`}
                        />
                        {loading ? "Refreshing…" : "Refresh"}
                    </button>
                }
            />
            <ErrorBanner msg={error} />

            {data && (
                <div className="flex items-center gap-2 mb-3 text-caption text-t-tertiary">
                    <span className="relative flex size-1.5">
                        <span className="absolute inline-flex h-full w-full rounded-full bg-primary-02 opacity-60 animate-ping" />
                        <span className="relative inline-flex size-1.5 rounded-full bg-primary-02" />
                    </span>
                    Live · updated {fmt(data.updated_at)}
                </div>
            )}

            {/* Hero metrics — three premium KPI cards with real signals */}
            <div className="grid grid-cols-3 gap-3 mb-3 max-lg:grid-cols-1">
                <HeroCard
                    label="Grand Total Cost"
                    glyph="wallet"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    loading={loading && !data}
                    value={money(grandTotal, currency)}
                    foot={
                        <>
                            <Icon name="usd-circle" className="size-3.5 fill-t-tertiary" />
                            All-time metered vendor spend
                        </>
                    }
                />
                <HeroCard
                    label="Month to Date"
                    glyph="income"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={70}
                    loading={loading && !data}
                    value={money(data?.month_to_date, currency)}
                    foot={
                        <>
                            <Icon name="calendar" className="size-3.5 fill-t-tertiary" />
                            Current billing period
                        </>
                    }
                />
                <HeroCard
                    label="Top Cost Driver"
                    glyph="chart"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    delay={140}
                    loading={loading && !data}
                    value={
                        topVendor ? (
                            <span className="flex items-baseline gap-2">
                                {money(topVendor.cost, currency)}
                            </span>
                        ) : (
                            "—"
                        )
                    }
                    foot={
                        topVendor && totalForShare > 0 ? (
                            <>
                                <span className="font-medium text-t-secondary">
                                    {topVendor.display_name}
                                </span>
                                · {((topVendor.cost / totalForShare) * 100).toFixed(0)}% of spend
                            </>
                        ) : (
                            <>
                                <Icon name="info" className="size-3.5 fill-t-tertiary" />
                                No vendor spend yet
                            </>
                        )
                    }
                />
            </div>

            {/* Composition — donut + real cost-share breakdown */}
            <Card
                title="Cost by Vendor"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                        {configuredCount}/{vendors.length || 0} live
                    </span>
                }
            >
                <div className="p-3 max-lg:p-2">
                    {loading && !data ? (
                        <div className="flex gap-8 items-center max-lg:flex-col max-lg:items-stretch">
                            <div className="skeleton size-[168px] rounded-full shrink-0 mx-auto" />
                            <div className="flex-1 space-y-4 w-full">
                                {[...Array(4)].map((_, i) => (
                                    <div key={i} className="space-y-2">
                                        <div className="skeleton h-4 w-40" />
                                        <div className="skeleton h-1.5 w-full" />
                                    </div>
                                ))}
                            </div>
                        </div>
                    ) : vendors.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="wallet" className="fill-inherit" />
                            </span>
                            <div className="state-title">No vendor data yet</div>
                            <div className="state-sub">
                                Vendor costs appear here once calls have been metered.
                            </div>
                        </div>
                    ) : (
                        <div className="flex gap-8 items-center max-lg:flex-col max-lg:items-stretch max-lg:gap-6">
                            <div className="mx-auto rise-in">
                                <CostDonut
                                    slices={donutSlices}
                                    centerValue={money(grandTotal, currency)}
                                    centerLabel="total"
                                />
                            </div>
                            <div className="flex-1 w-full space-y-4 min-w-0">
                                {sorted.map((v, i) => (
                                    <ShareRow
                                        key={v.vendor}
                                        label={v.display_name}
                                        value={money(v.cost, currency)}
                                        pct={totalForShare > 0 ? (Math.max(v.cost, 0) / totalForShare) * 100 : 0}
                                        color={VENDOR_COLORS[i % VENDOR_COLORS.length]}
                                        delay={i * 50}
                                        badge={
                                            v.status !== "configured" ? (
                                                <StatusBadge status={v.status} />
                                            ) : undefined
                                        }
                                    />
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </Card>

            {/* Per-vendor drill-down cards */}
            <Card title="Vendor Detail">
                <div className="p-3 grid grid-cols-3 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    {loading && !data ? (
                        [...Array(3)].map((_, i) => (
                            <div
                                key={i}
                                className="flex flex-col gap-3 p-4 rounded-2xl ring-1 ring-s-subtle ring-inset"
                            >
                                <div className="skeleton h-4 w-24" />
                                <div className="skeleton h-7 w-20" />
                                <div className="skeleton h-5 w-16" />
                            </div>
                        ))
                    ) : vendors.length === 0 ? (
                        <div className="col-span-full state-block">
                            <span className="state-glyph">
                                <Icon name="cube" className="fill-inherit" />
                            </span>
                            <div className="state-title">Nothing to drill into</div>
                            <div className="state-sub">
                                Per-vendor breakdowns unlock once spend is recorded.
                            </div>
                        </div>
                    ) : (
                        sorted.map((v, i) => (
                            <Link
                                key={v.vendor}
                                href={`/billing/vendors/${v.vendor}`}
                                className="lift group relative flex flex-col gap-3 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset overflow-hidden dark:bg-shade-04/30 rise-in"
                                style={{ animationDelay: `${i * 50}ms` }}
                            >
                                <span
                                    aria-hidden
                                    className="absolute left-0 top-4 bottom-4 w-[3px] rounded-full"
                                    style={{ background: VENDOR_COLORS[i % VENDOR_COLORS.length] }}
                                />
                                <div className="flex items-center justify-between gap-2 pl-2">
                                    <div className="text-sub-title-2 text-t-primary truncate">
                                        {v.display_name}
                                    </div>
                                    <Icon
                                        name="arrow-up-right"
                                        className="size-4 fill-t-tertiary opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0"
                                    />
                                </div>
                                <div className="text-h5 text-t-primary tabular-nums pl-2">
                                    {money(v.cost, currency)}
                                </div>
                                <div className="flex items-center justify-between gap-2 pl-2">
                                    <StatusBadge status={v.status} />
                                    {totalForShare > 0 && (
                                        <span className="text-caption text-t-tertiary tabular-nums">
                                            {((Math.max(v.cost, 0) / totalForShare) * 100).toFixed(0)}% of spend
                                        </span>
                                    )}
                                </div>
                            </Link>
                        ))
                    )}
                </div>
            </Card>
        </Layout>
    );
}
