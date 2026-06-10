"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import {
    getBillingExplorer,
    getCampaigns,
    type BillingExplorerRow,
    type Campaign,
} from "@/lib/api";
import {
    money,
    fmt,
    ErrorBanner,
    selectCls,
    ghostBtnCls,
    HeroCard,
    outcomeVariant,
    BillingHeader,
} from "../_shared";

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

    // Real summary signals computed from the returned rows.
    const sumCost = useMemo(() => rows.reduce((s, r) => s + (r.total_cost || 0), 0), [rows]);
    const avgCost = rows.length ? sumCost / rows.length : 0;
    const hasFilter = !!(from || to || campaignId);

    const labelCls = "block text-overline text-t-tertiary mb-1.5";

    return (
        <Layout title="Billing · Cost Explorer">
            <BillingHeader
                title="Cost Explorer"
                subtitle="Drill into every call's metered cost broken down by vendor — filter by date range and campaign."
            />
            <ErrorBanner msg={error} />

            {/* Summary heroes — real sums over the filtered result set */}
            <div className="grid grid-cols-3 gap-3 mb-3 max-lg:grid-cols-1">
                <HeroCard
                    label="Calls in View"
                    glyph="chat"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    loading={loading && rows.length === 0}
                    value={rows.length.toLocaleString()}
                    foot={
                        total > rows.length
                            ? `of ${total.toLocaleString()} matching`
                            : hasFilter
                              ? "Matching current filters"
                              : "All metered calls"
                    }
                />
                <HeroCard
                    label="Total Cost"
                    glyph="wallet"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={70}
                    loading={loading && rows.length === 0}
                    value={money(sumCost, currency)}
                    foot="Summed across calls in view"
                />
                <HeroCard
                    label="Avg / Call"
                    glyph="usd-circle"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    delay={140}
                    loading={loading && rows.length === 0}
                    value={money(avgCost, currency)}
                    foot="Mean per-call cost"
                />
            </div>

            {/* Filters */}
            <div className="surface p-4 mb-3">
                <div className="flex items-end gap-4 flex-wrap">
                    <div>
                        <label className={labelCls}>From</label>
                        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={selectCls} />
                    </div>
                    <div>
                        <label className={labelCls}>To</label>
                        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={selectCls} />
                    </div>
                    <div>
                        <label className={labelCls}>Campaign</label>
                        <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} className={selectCls}>
                            <option value="">All Campaigns</option>
                            {campaigns.map((c) => (
                                <option key={c.id} value={c.id}>{c.name}</option>
                            ))}
                        </select>
                    </div>
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon name="filters" className="size-4 fill-current" />
                        {loading ? "Loading…" : "Apply"}
                    </button>
                    {hasFilter && (
                        <button
                            onClick={() => { setFrom(""); setTo(""); setCampaignId(""); }}
                            className="text-caption text-t-tertiary hover:text-t-primary transition-colors pb-2.5"
                        >
                            Clear
                        </button>
                    )}
                </div>
            </div>

            <Card title="Per-Call Cost Breakdown">
                <div className="overflow-x-auto px-3 pb-2">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>When</th>
                                <th>Name</th>
                                <th>Phone</th>
                                <th>Campaign</th>
                                <th>Outcome</th>
                                <th className="text-right">Duration</th>
                                <th className="text-right">Total Cost</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && rows.length === 0 ? (
                                [...Array(6)].map((_, i) => (
                                    <tr key={i}>
                                        {[...Array(7)].map((_, j) => (
                                            <td key={j}><div className="skeleton h-4 w-20" /></td>
                                        ))}
                                    </tr>
                                ))
                            ) : rows.length === 0 ? (
                                <tr>
                                    <td colSpan={7}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name="filters" className="fill-inherit" />
                                            </span>
                                            <div className="state-title">No calls for these filters</div>
                                            <div className="state-sub">
                                                Widen the date range or clear filters to see metered calls.
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                rows.map((r) => (
                                    <tr key={r.call_id || r.room}>
                                        <td className="text-t-secondary whitespace-nowrap">{fmt(r.ts)}</td>
                                        <td className="text-t-primary font-medium">{r.name || "—"}</td>
                                        <td className="text-t-secondary tabular-nums">{r.phone || "—"}</td>
                                        <td className="text-t-secondary">{r.campaign_name || "—"}</td>
                                        <td>
                                            {r.outcome ? (
                                                <Badge variant={outcomeVariant(r.outcome)}>
                                                    {r.outcome.replace(/_/g, " ")}
                                                </Badge>
                                            ) : (
                                                <span className="text-t-tertiary">—</span>
                                            )}
                                        </td>
                                        <td className="td-num text-right text-t-secondary">
                                            {r.duration_s != null ? `${r.duration_s}s` : "—"}
                                        </td>
                                        <td
                                            className="td-num text-right font-medium text-t-primary"
                                            title={Object.entries(r.by_vendor || {}).map(([v, c]) => `${v}: ${money(c, currency)}`).join("\n")}
                                        >
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
