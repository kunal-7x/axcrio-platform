"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import NoFound from "@/components/NoFound";
import ProviderLogo from "@/components/ProviderLogo";
import { getBillingOverview, type BillingOverview } from "@/lib/api";
import {
    money,
    fmt,
    StatusBadge,
    ErrorBanner,
    BarRow,
    StatStrip,
    StatItem,
    BillingTabs,
} from "../_shared";

const tableHead = ["Vendor", "Status", "Cost", "Share"];

export default function BillingOverviewPage() {
    const router = useRouter();
    const [data, setData] = useState<BillingOverview | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getBillingOverview()
            .then(setData)
            .catch((e) =>
                setError(e instanceof Error ? e.message : "Failed to load billing overview")
            )
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const currency = data?.currency || "";
    const vendors = useMemo(() => data?.per_vendor ?? [], [data]);
    const grandTotal = data?.grand_total ?? 0;
    const configuredCount = vendors.filter((v) => v.status === "configured").length;
    const sorted = useMemo(() => [...vendors].sort((a, b) => b.cost - a.cost), [vendors]);
    const topVendor = sorted[0];
    const totalForShare = sorted.reduce((s, v) => s + Math.max(v.cost, 0), 0);

    return (
        <Layout title="Billing">
            <BillingTabs />
            <ErrorBanner msg={error} />

            <div className="flex max-lg:block">
                <div className="col-left">
                    {/* Balance / spend strip — ported from EarningPage Balance */}
                    <StatStrip>
                        <StatItem
                            title="Total spend"
                            icon="wallet"
                            loading={loading && !data}
                            value={money(grandTotal, currency)}
                            foot="All-time metered vendor spend"
                        />
                        <StatItem
                            title="This month"
                            icon="calendar"
                            loading={loading && !data}
                            value={money(data?.month_to_date, currency)}
                            foot="Current billing period"
                        />
                        <StatItem
                            title="Top driver"
                            icon="chart"
                            loading={loading && !data}
                            value={topVendor ? money(topVendor.cost, currency) : "—"}
                            foot={
                                topVendor && totalForShare > 0
                                    ? `${topVendor.display_name} · ${((topVendor.cost / totalForShare) * 100).toFixed(0)}% of spend`
                                    : "No vendor spend yet"
                            }
                        />
                    </StatStrip>

                    {/* Per-vendor table — ported from EarningPage Transactions */}
                    <Card
                        title="Vendor spend"
                        headContent={
                            <Button
                                className="ml-auto"
                                isStroke
                                icon="clock"
                                onClick={load}
                                disabled={loading}
                            >
                                {loading ? "Refreshing…" : "Refresh"}
                            </Button>
                        }
                    >
                        {!loading && vendors.length === 0 ? (
                            <NoFound title="No vendor data yet" />
                        ) : (
                            <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                                <Table
                                    cellsThead={tableHead.map((head) => (
                                        <th
                                            className="!h-12.5 nth-3:text-right max-md:nth-4:hidden"
                                            key={head}
                                        >
                                            {head}
                                        </th>
                                    ))}
                                    isMobileVisibleTHead
                                >
                                    {(loading ? PLACEHOLDER : sorted).map((v, i) => {
                                        const pct =
                                            totalForShare > 0
                                                ? (Math.max(v.cost, 0) / totalForShare) * 100
                                                : 0;
                                        return (
                                            <TableRow
                                                key={v.vendor || i}
                                                className="cursor-pointer"
                                                onClick={
                                                    loading
                                                        ? undefined
                                                        : () => router.push(`/billing/vendors/${v.vendor}`)
                                                }
                                            >
                                                <td>
                                                    <div className="flex items-center gap-3">
                                                        {v.vendor ? (
                                                            <ProviderLogo provider={v.vendor} size={38} className="!rounded-xl" />
                                                        ) : (
                                                            <span className="size-7 rounded-lg bg-b-surface1 shrink-0" />
                                                        )}
                                                        <span className="text-sub-title-2">
                                                            {v.display_name || "—"}
                                                        </span>
                                                    </div>
                                                </td>
                                                <td>
                                                    {v.vendor && <StatusBadge status={v.status} />}
                                                </td>
                                                <td className="text-right text-sub-title-2 tabular-nums">
                                                    {v.vendor ? money(v.cost, currency) : "—"}
                                                </td>
                                                <td className="text-t-secondary tabular-nums max-md:hidden">
                                                    {v.vendor ? `${pct.toFixed(0)}%` : "—"}
                                                </td>
                                            </TableRow>
                                        );
                                    })}
                                </Table>
                            </div>
                        )}
                    </Card>
                </div>

                {/* Cost-share breakdown — ported from EarningPage Countries */}
                <div className="col-right">
                    <Card
                        classHead="!pl-3"
                        title="Cost by vendor"
                        headContent={
                            <span className="ml-3 text-caption text-t-tertiary">
                                {configuredCount}/{vendors.length || 0} live
                            </span>
                        }
                    >
                        <div className="flex flex-col gap-5 p-3 pb-5">
                            {loading && !data ? (
                                [...Array(4)].map((_, i) => (
                                    <div
                                        key={i}
                                        className="h-9 rounded-lg bg-b-surface1 animate-pulse"
                                    />
                                ))
                            ) : vendors.length === 0 ? (
                                <div className="py-8 text-center text-body-2 text-t-tertiary">
                                    Vendor costs appear here once calls have been metered.
                                </div>
                            ) : (
                                sorted.map((v) => (
                                    <BarRow
                                        key={v.vendor}
                                        provider={v.vendor}
                                        label={v.display_name}
                                        value={money(v.cost, currency)}
                                        pct={
                                            totalForShare > 0
                                                ? (Math.max(v.cost, 0) / totalForShare) * 100
                                                : 0
                                        }
                                        color="var(--primary-01)"
                                        badge={
                                            v.status !== "configured" ? (
                                                <StatusBadge status={v.status} />
                                            ) : undefined
                                        }
                                    />
                                ))
                            )}
                        </div>
                    </Card>

                    {data && (
                        <div className="mt-3 px-2 text-caption text-t-tertiary">
                            Updated {fmt(data.updated_at)}
                        </div>
                    )}
                </div>
            </div>
        </Layout>
    );
}

// Skeleton placeholder rows used while the table loads. Empty vendor strings
// render as muted dashes (no raw "undefined").
const PLACEHOLDER = [...Array(4)].map(() => ({
    vendor: "",
    display_name: "",
    cost: 0,
    status: "not_configured" as const,
}));
