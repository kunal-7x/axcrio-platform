"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import NoFound from "@/components/NoFound";
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
    StatStrip,
    StatItem,
    BillingTabs,
    outcomeVariant,
} from "../_shared";

const tableHead = ["When", "Name", "Phone", "Campaign", "Outcome", "Duration", "Cost"];
const labelCls = "block text-button text-t-secondary mb-2";
const inputCls =
    "h-12 px-4 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none bg-transparent transition-colors hover:border-s-highlight focus:border-s-focus";

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
            .then((r) => {
                setRows(r.rows);
                setTotal(r.total);
                setCurrency(r.currency);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load spending"))
            .finally(() => setLoading(false));
    }, [from, to, campaignId]);

    useEffect(() => {
        getCampaigns().then((r) => setCampaigns(r.campaigns)).catch(() => {});
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const sumCost = useMemo(() => rows.reduce((s, r) => s + (r.total_cost || 0), 0), [rows]);
    const avgCost = rows.length ? sumCost / rows.length : 0;
    const hasFilter = !!(from || to || campaignId);

    return (
        <Layout title="Spending">
            <BillingTabs />
            <ErrorBanner msg={error} />

            {/* Statistics strip — ported from StatementsPage Statistics */}
            <StatStrip>
                <StatItem
                    title="Calls in view"
                    icon="chat"
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
                <StatItem
                    title="Total cost"
                    icon="wallet"
                    loading={loading && rows.length === 0}
                    value={money(sumCost, currency)}
                    foot="Summed across calls in view"
                />
                <StatItem
                    title="Avg / call"
                    icon="usd-circle"
                    loading={loading && rows.length === 0}
                    value={money(avgCost, currency)}
                    foot="Mean per-call cost"
                />
            </StatStrip>

            {/* Filters */}
            <Card title="Filters">
                <div className="flex items-end gap-4 flex-wrap p-5 pt-3 max-lg:p-3">
                    <div>
                        <label className={labelCls}>From</label>
                        <input
                            type="date"
                            value={from}
                            onChange={(e) => setFrom(e.target.value)}
                            className={inputCls}
                        />
                    </div>
                    <div>
                        <label className={labelCls}>To</label>
                        <input
                            type="date"
                            value={to}
                            onChange={(e) => setTo(e.target.value)}
                            className={inputCls}
                        />
                    </div>
                    <div>
                        <label className={labelCls}>Campaign</label>
                        <select
                            value={campaignId}
                            onChange={(e) => setCampaignId(e.target.value)}
                            className={inputCls}
                        >
                            <option value="">All campaigns</option>
                            {campaigns.map((c) => (
                                <option key={c.id} value={c.id}>
                                    {c.name}
                                </option>
                            ))}
                        </select>
                    </div>
                    <Button isBlack onClick={load} disabled={loading}>
                        {loading ? "Loading…" : "Apply"}
                    </Button>
                    {hasFilter && (
                        <Button
                            isStroke
                            onClick={() => {
                                setFrom("");
                                setTo("");
                                setCampaignId("");
                            }}
                        >
                            Clear
                        </Button>
                    )}
                </div>
            </Card>

            {/* Per-call cost table — ported from StatementsPage Transactions */}
            <Card title="Per-call cost">
                {!loading && rows.length === 0 ? (
                    <NoFound title="No calls for these filters" />
                ) : (
                    <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                        <Table
                            cellsThead={tableHead.map((head) => (
                                <th
                                    className="!h-12.5 last:text-right nth-6:text-right max-lg:nth-2:hidden max-lg:nth-3:hidden max-md:nth-4:hidden"
                                    key={head}
                                >
                                    {head}
                                </th>
                            ))}
                            isMobileVisibleTHead
                        >
                            {(loading ? PLACEHOLDER : rows).map((r, idx) => (
                                <TableRow key={r.call_id || r.room || idx}>
                                    <td className="text-t-secondary whitespace-nowrap">
                                        {r.ts ? fmt(r.ts) : "—"}
                                    </td>
                                    <td className="text-sub-title-2 max-lg:hidden">
                                        {r.name || "—"}
                                    </td>
                                    <td className="text-t-secondary tabular-nums max-lg:hidden">
                                        {r.phone || "—"}
                                    </td>
                                    <td className="text-t-secondary max-md:hidden">
                                        {r.campaign_name || "—"}
                                    </td>
                                    <td>
                                        {r.outcome ? (
                                            <Badge variant={outcomeVariant(r.outcome)}>
                                                {r.outcome.replace(/_/g, " ")}
                                            </Badge>
                                        ) : (
                                            <span className="text-t-tertiary">—</span>
                                        )}
                                    </td>
                                    <td className="text-right text-t-secondary tabular-nums">
                                        {r.duration_s != null && r.ts ? `${r.duration_s}s` : "—"}
                                    </td>
                                    <td
                                        className="text-right text-sub-title-2 tabular-nums"
                                        title={Object.entries(r.by_vendor || {})
                                            .map(([v, c]) => `${v}: ${money(c, currency)}`)
                                            .join("\n")}
                                    >
                                        {r.ts ? money(r.total_cost, currency) : "—"}
                                    </td>
                                </TableRow>
                            ))}
                        </Table>
                    </div>
                )}
            </Card>
        </Layout>
    );
}

const PLACEHOLDER: BillingExplorerRow[] = [...Array(6)].map(() => ({
    call_id: "",
    room: "",
    tenant_id: "",
    campaign_id: "",
    ts: "",
    total_cost: 0,
    by_vendor: {},
    name: "",
    phone: "",
    campaign_name: "",
    outcome: "",
    duration_s: 0,
}));
