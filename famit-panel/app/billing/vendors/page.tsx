"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import { getBillingVendors, type BillingVendorRow } from "@/lib/api";
import { money, fmt, StatusBadge, ErrorBanner, btnCls } from "../_shared";

export default function BillingVendorsPage() {
    const router = useRouter();
    const [vendors, setVendors] = useState<BillingVendorRow[]>([]);
    const [currency, setCurrency] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getBillingVendors()
            .then((r) => { setVendors(r.vendors); setCurrency(r.currency); })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load vendors"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    return (
        <Layout title="Billing · Vendors">
            <ErrorBanner msg={error} />
            <div className="flex justify-end mb-4">
                <button onClick={load} className={btnCls}>{loading ? "Refreshing…" : "Refresh"}</button>
            </div>
            <Card title="Vendors">
                <div className="overflow-x-auto">
                    <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                        <thead>
                            <tr>
                                <th>Vendor</th>
                                <th>Status</th>
                                <th>Cost</th>
                                <th>Last Sync</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && vendors.length === 0 ? (
                                <tr><td colSpan={4} className="py-8 text-center text-t-secondary">Loading…</td></tr>
                            ) : vendors.length === 0 ? (
                                <tr><td colSpan={4} className="py-12 text-center text-t-tertiary">No vendors</td></tr>
                            ) : (
                                vendors.map((v) => (
                                    <tr
                                        key={v.vendor}
                                        className="border-t border-s-subtle hover:bg-b-surface2/50 transition-colors cursor-pointer"
                                        onClick={() => router.push(`/billing/vendors/${v.vendor}`)}
                                    >
                                        <td className="font-medium text-t-primary">
                                            {v.display_name}
                                            {v.estimated && (
                                                <span className="ml-2 text-caption text-t-tertiary">(estimated)</span>
                                            )}
                                        </td>
                                        <td><StatusBadge status={v.status} stale={v.stale} /></td>
                                        <td className="font-medium">{money(v.cost, currency)}</td>
                                        <td className="text-t-secondary">{fmt(v.synced_at)}</td>
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
