"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import { getBillingOverview, type BillingOverview } from "@/lib/api";
import { money, fmt, StatusBadge, ErrorBanner, btnCls } from "../_shared";

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

    return (
        <Layout title="Billing · Overview">
            <ErrorBanner msg={error} />

            <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
                <div className="flex items-center gap-2 text-caption text-t-tertiary">
                    {data && (
                        <>
                            <span className="size-1.5 rounded-full bg-primary-02" />
                            Last updated {fmt(data.updated_at)}
                        </>
                    )}
                </div>
                <button onClick={load} className={btnCls}>
                    <Icon
                        name="clock"
                        className={`size-4 fill-current ${
                            loading ? "animate-spin" : ""
                        }`}
                    />
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
            </div>

            {/* Hero totals */}
            <div className="grid grid-cols-2 gap-3 mb-3 max-sm:grid-cols-1">
                <div className="kpi rise-in">
                    <div className="kpi-label">
                        <span className="kpi-glyph fill-primary-04">
                            <Icon name="wallet" className="fill-inherit" />
                        </span>
                        Grand Total Cost
                    </div>
                    {loading && !data ? (
                        <div className="skeleton h-10 w-40" />
                    ) : (
                        <div className="kpi-value">
                            {money(data?.grand_total, currency)}
                        </div>
                    )}
                    <div className="kpi-foot">All-time vendor spend</div>
                </div>
                <div className="kpi rise-in" style={{ animationDelay: "60ms" }}>
                    <div className="kpi-label">
                        <span className="kpi-glyph fill-primary-02">
                            <Icon name="income" className="fill-inherit" />
                        </span>
                        Month to Date
                    </div>
                    {loading && !data ? (
                        <div className="skeleton h-10 w-40" />
                    ) : (
                        <div className="kpi-value">
                            {money(data?.month_to_date, currency)}
                        </div>
                    )}
                    <div className="kpi-foot">Current billing period</div>
                </div>
            </div>

            {/* Per-vendor cost cards */}
            <Card title="Cost by Vendor">
                <div className="p-3 grid grid-cols-3 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    {loading && !data ? (
                        [...Array(3)].map((_, i) => (
                            <div
                                key={i}
                                className="flex flex-col gap-3 p-4 rounded-2xl border border-s-subtle"
                            >
                                <div className="skeleton h-4 w-24" />
                                <div className="skeleton h-7 w-20" />
                                <div className="skeleton h-5 w-16" />
                            </div>
                        ))
                    ) : (data?.per_vendor ?? []).length === 0 ? (
                        <div className="col-span-full state-block">
                            <span className="state-glyph">
                                <Icon name="wallet" className="fill-inherit" />
                            </span>
                            <div className="state-title">No vendor data yet</div>
                            <div className="state-sub">
                                Vendor costs appear here once calls have been
                                metered.
                            </div>
                        </div>
                    ) : (
                        data!.per_vendor.map((v) => (
                            <Link
                                key={v.vendor}
                                href={`/billing/vendors/${v.vendor}`}
                                className="group relative flex flex-col gap-3 p-4 rounded-2xl bg-b-surface1/50 border border-s-subtle transition-all hover:border-s-highlight hover:shadow-widget dark:bg-shade-04/30"
                            >
                                <div className="flex items-center justify-between gap-2">
                                    <div className="text-sub-title-2 text-t-primary">
                                        {v.display_name}
                                    </div>
                                    <Icon
                                        name="arrow-up-right"
                                        className="size-4 fill-t-tertiary opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0"
                                    />
                                </div>
                                <div className="text-h5 text-t-primary tabular-nums">
                                    {money(v.cost, currency)}
                                </div>
                                <StatusBadge status={v.status} />
                            </Link>
                        ))
                    )}
                </div>
            </Card>
        </Layout>
    );
}
