"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import {
    getBillingAudit,
    postBillingSync,
    type BillingAuditVendor,
} from "@/lib/api";
import { useMe, isAdmin } from "@/lib/auth";
import { money, fmt, StatusBadge, ErrorBanner, btnCls } from "../_shared";

export default function BillingAuditPage() {
    const { me } = useMe();
    const admin = isAdmin(me);

    const [vendors, setVendors] = useState<BillingAuditVendor[]>([]);
    const [currency, setCurrency] = useState("");
    const [note, setNote] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [syncing, setSyncing] = useState(false);
    const [syncMsg, setSyncMsg] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getBillingAudit()
            .then((r) => { setVendors(r.vendors); setCurrency(r.currency); setNote(r.note); })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load audit"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    async function handleSync() {
        setSyncing(true);
        setSyncMsg("");
        try {
            const r = await postBillingSync();
            setSyncMsg(`Synced at ${fmt(r.synced_at)}`);
            load();
        } catch (e) {
            setSyncMsg(e instanceof Error ? e.message : "Sync failed");
        } finally {
            setSyncing(false);
        }
    }

    return (
        <Layout title="Billing · Audit">
            <ErrorBanner msg={error} />

            <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
                <div className="text-caption text-t-tertiary">{note}</div>
                <div className="flex items-center gap-3">
                    {syncMsg && <span className="text-caption text-t-secondary">{syncMsg}</span>}
                    <button onClick={load} className={btnCls}>{loading ? "Refreshing…" : "Refresh"}</button>
                    {admin && (
                        <Button isBlack onClick={handleSync} disabled={syncing}>
                            {syncing ? "Syncing…" : "Sync now"}
                        </Button>
                    )}
                </div>
            </div>

            <Card title="Vendor Sync Status">
                <div className="overflow-x-auto">
                    <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                        <thead>
                            <tr>
                                <th>Vendor</th>
                                <th>Status</th>
                                <th>Last Sync</th>
                                <th>Internal (ledger)</th>
                                <th>Vendor-reported</th>
                                <th>Notes</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && vendors.length === 0 ? (
                                <tr><td colSpan={6} className="py-8 text-center text-t-secondary">Loading…</td></tr>
                            ) : vendors.length === 0 ? (
                                <tr><td colSpan={6} className="py-12 text-center text-t-tertiary">No vendors</td></tr>
                            ) : (
                                vendors.map((v) => (
                                    <tr key={v.vendor} className="border-t border-s-subtle">
                                        <td className="font-medium text-t-primary">{v.display_name}</td>
                                        <td><StatusBadge status={v.status} stale={v.stale} /></td>
                                        <td className="text-t-secondary">{fmt(v.synced_at)}</td>
                                        <td className="font-medium">{money(v.internal_ledger_cost, currency)}</td>
                                        <td className="text-t-secondary">
                                            {v.vendor_reported == null ? "—" : money(v.vendor_reported, currency)}
                                        </td>
                                        <td className="text-t-secondary">
                                            {v.error
                                                ? <span className="text-red-500">{v.error}</span>
                                                : v.stale ? "Stale — last snapshot kept" : "OK"}
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
