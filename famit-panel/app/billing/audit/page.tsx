"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import {
    getBillingAudit,
    postBillingSync,
    type BillingAuditVendor,
} from "@/lib/api";
import { useMe, isAdmin } from "@/lib/auth";
import { money, fmt, StatusBadge, ErrorBanner, ghostBtnCls, BillingHeader } from "../_shared";

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
            <BillingHeader
                title="Billing Audit"
                subtitle="Reconcile the internal metered ledger against each vendor's reported spend, and flag stale syncs."
            />
            <ErrorBanner msg={error} />

            <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
                <div className="flex items-center gap-2 text-caption text-t-tertiary max-w-2xl">
                    <Icon name="info" className="size-3.5 fill-t-tertiary shrink-0" />
                    {note || "Reconciles the internal metered ledger against each vendor's reported spend."}
                </div>
                <div className="flex items-center gap-3">
                    {syncMsg && <span className="text-caption text-t-secondary">{syncMsg}</span>}
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                        {loading ? "Refreshing…" : "Refresh"}
                    </button>
                    {admin && (
                        <Button isBlack onClick={handleSync} disabled={syncing}>
                            {syncing ? "Syncing…" : "Sync now"}
                        </Button>
                    )}
                </div>
            </div>

            <Card title="Vendor Sync Status">
                <div className="overflow-x-auto px-3 pb-2">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Vendor</th>
                                <th>Status</th>
                                <th>Last Sync</th>
                                <th className="text-right">Internal (ledger)</th>
                                <th className="text-right">Vendor-reported</th>
                                <th className="text-right">Δ</th>
                                <th>Notes</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && vendors.length === 0 ? (
                                [...Array(4)].map((_, i) => (
                                    <tr key={i}>
                                        {[...Array(7)].map((_, j) => (
                                            <td key={j}><div className="skeleton h-4 w-20" /></td>
                                        ))}
                                    </tr>
                                ))
                            ) : vendors.length === 0 ? (
                                <tr>
                                    <td colSpan={7}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name="check-circle" className="fill-inherit" />
                                            </span>
                                            <div className="state-title">Nothing to reconcile</div>
                                            <div className="state-sub">
                                                Vendor sync status appears here once a sync runs.
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                vendors.map((v) => {
                                    const delta =
                                        v.vendor_reported == null
                                            ? null
                                            : v.vendor_reported - v.internal_ledger_cost;
                                    return (
                                        <tr key={v.vendor}>
                                            <td className="font-medium text-t-primary">{v.display_name}</td>
                                            <td><StatusBadge status={v.status} stale={v.stale} /></td>
                                            <td className="text-t-secondary whitespace-nowrap">{fmt(v.synced_at)}</td>
                                            <td className="td-num text-right font-medium text-t-primary">
                                                {money(v.internal_ledger_cost, currency)}
                                            </td>
                                            <td className="td-num text-right text-t-secondary">
                                                {v.vendor_reported == null ? "—" : money(v.vendor_reported, currency)}
                                            </td>
                                            <td className="td-num text-right">
                                                {delta == null ? (
                                                    <span className="text-t-tertiary">—</span>
                                                ) : Math.abs(delta) < 0.005 ? (
                                                    <span className="text-primary-02">matched</span>
                                                ) : (
                                                    <span className={delta > 0 ? "text-primary-05" : "text-primary-01"}>
                                                        {delta > 0 ? "+" : ""}{money(delta, currency)}
                                                    </span>
                                                )}
                                            </td>
                                            <td>
                                                {v.error ? (
                                                    <Badge variant="danger">{v.error}</Badge>
                                                ) : v.stale ? (
                                                    <Badge variant="warning">Stale snapshot</Badge>
                                                ) : (
                                                    <Badge variant="success" dot>OK</Badge>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>
        </Layout>
    );
}
