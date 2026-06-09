"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
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
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load billing overview"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    const currency = data?.currency || "";

    return (
        <Layout title="Billing · Overview">
            <ErrorBanner msg={error} />

            <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
                <div className="text-caption text-t-tertiary">
                    {data ? `Last updated ${fmt(data.updated_at)}` : ""}
                </div>
                <button onClick={load} className={btnCls}>
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
            </div>

            {/* Grand total + month-to-date */}
            <div className="grid grid-cols-2 gap-4 mb-6 max-sm:grid-cols-1">
                <div className="card p-5 flex flex-col gap-1">
                    <div className="text-caption text-t-tertiary">Grand Total Cost</div>
                    <div className="text-h4 text-t-primary">
                        {loading ? "…" : money(data?.grand_total, currency)}
                    </div>
                </div>
                <div className="card p-5 flex flex-col gap-1">
                    <div className="text-caption text-t-tertiary">Month to Date</div>
                    <div className="text-h4 text-t-primary">
                        {loading ? "…" : money(data?.month_to_date, currency)}
                    </div>
                </div>
            </div>

            {/* Per-vendor cost cards */}
            <Card title="Cost by Vendor">
                <div className="p-5 grid grid-cols-3 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    {loading && !data ? (
                        <div className="col-span-full py-8 text-center text-t-secondary">Loading…</div>
                    ) : (data?.per_vendor ?? []).length === 0 ? (
                        <div className="col-span-full py-8 text-center text-t-tertiary">No vendor data yet</div>
                    ) : (
                        data!.per_vendor.map((v) => (
                            <Link
                                key={v.vendor}
                                href={`/billing/vendors/${v.vendor}`}
                                className="flex flex-col gap-2 p-4 rounded-2xl border border-s-stroke2 hover:border-s-highlight transition-colors"
                            >
                                <div className="flex items-center justify-between gap-2">
                                    <div className="text-button text-t-primary">{v.display_name}</div>
                                </div>
                                <div className="text-h5 text-t-primary">
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
