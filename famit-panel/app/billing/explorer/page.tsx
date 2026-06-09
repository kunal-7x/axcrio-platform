"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import {
    getBillingExplorer,
    getCampaigns,
    type BillingExplorerRow,
    type Campaign,
} from "@/lib/api";
import { money, fmt, ErrorBanner, selectCls, btnCls } from "../_shared";

export default function BillingExplorerPage() {
    const [rows, setRows] = useState<BillingExplorerRow[]>([]);
    const [total, setTotal] = useState(0);
    const [currency, setCurrency] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [from, setFrom] = useState("");
    const [to, setTo] = useState("");
    const [campaignId, setCampaignId] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getBillingExplorer({
            from: from || undefined,
            to: to || undefined,
            campaign_id: campaignId || undefined,
        })
            .then((r) => { setRows(r.rows); setTotal(r.total); setCurrency(r.currency); })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load cost explorer"))
            .finally(() => setLoading(false));
    }, [from, to, campaignId]);

    useEffect(() => {
        getCampaigns().then((r) => setCampaigns(r.campaigns)).catch(() => {});
    }, []);

    useEffect(() => { load(); }, [load]);

    const inputCls = selectCls;

    return (
        <Layout title="Billing · Cost Explorer">
            <ErrorBanner msg={error} />

            {/* Filters */}
            <div className="flex items-end gap-4 mb-6 flex-wrap">
                <div>
                    <label className="block text-caption text-t-secondary mb-1">From</label>
                    <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={inputCls} />
                </div>
                <div>
                    <label className="block text-caption text-t-secondary mb-1">To</label>
                    <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={inputCls} />
                </div>
                <div>
                    <label className="block text-caption text-t-secondary mb-1">Campaign</label>
                    <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} className={selectCls}>
                        <option value="">All Campaigns</option>
                        {campaigns.map((c) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                    </select>
                </div>
                <button onClick={load} className={btnCls}>{loading ? "Loading…" : "Apply"}</button>
                <span className="text-caption text-t-tertiary pb-2.5">{total} call{total === 1 ? "" : "s"}</span>
            </div>

            <Card title="Per-Call Cost Breakdown">
                <div className="overflow-x-auto">
                    <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                        <thead>
                            <tr>
                                <th>When</th>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Campaign</th>
                                <th>Outcome</th>
                                <th>Duration</th>
                                <th>Total Cost</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && rows.length === 0 ? (
                                <tr><td colSpan={7} className="py-8 text-center text-t-secondary">Loading…</td></tr>
                            ) : rows.length === 0 ? (
                                <tr><td colSpan={7} className="py-12 text-center text-t-tertiary">No calls for these filters</td></tr>
                            ) : (
                                rows.map((r) => (
                                    <tr key={r.call_id || r.room} className="border-t border-s-subtle hover:bg-b-surface2/50 transition-colors">
                                        <td className="text-t-secondary">{fmt(r.ts)}</td>
                                        <td className="text-t-primary">{r.name || "—"}</td>
                                        <td className="text-t-secondary">{r.phone || "—"}</td>
                                        <td className="text-t-secondary">{r.campaign_name || "—"}</td>
                                        <td className="text-t-secondary capitalize">{(r.outcome || "").replace(/_/g, " ") || "—"}</td>
                                        <td className="text-t-secondary">{r.duration_s != null ? `${r.duration_s}s` : "—"}</td>
                                        <td className="font-medium" title={Object.entries(r.by_vendor || {}).map(([v, c]) => `${v}: ${money(c, currency)}`).join("\n")}>
                                            {money(r.total_cost, currency)}
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
