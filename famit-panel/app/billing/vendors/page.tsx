"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import NoFound from "@/components/NoFound";
import { getBillingVendors, type BillingVendorRow } from "@/lib/api";
import {
    money,
    fmt,
    StatusBadge,
    ErrorBanner,
    BillingTabs,
    VENDOR_COLORS,
} from "../_shared";

const tableHead = ["Vendor", "Status", "Cost", "Share", "Last sync"];

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
            .then((r) => {
                setVendors(r.vendors);
                setCurrency(r.currency);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load vendors"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const sorted = useMemo(() => [...vendors].sort((a, b) => b.cost - a.cost), [vendors]);
    const total = useMemo(
        () => sorted.reduce((s, v) => s + Math.max(v.cost, 0), 0),
        [sorted]
    );

    return (
        <Layout title="Vendors">
            <BillingTabs />
            <ErrorBanner msg={error} />

            <Card
                title="Vendors"
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
                    <NoFound title="No vendors yet" />
                ) : (
                    <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                        <Table
                            cellsThead={tableHead.map((head) => (
                                <th
                                    className="!h-12.5 nth-3:text-right max-lg:nth-4:hidden max-md:nth-5:hidden"
                                    key={head}
                                >
                                    {head}
                                </th>
                            ))}
                            isMobileVisibleTHead
                        >
                            {(loading ? PLACEHOLDER : sorted).map((v, i) => {
                                const pct = total > 0 ? (Math.max(v.cost, 0) / total) * 100 : 0;
                                const color = VENDOR_COLORS[i % VENDOR_COLORS.length];
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
                                                <span
                                                    className="size-3 rounded-sm shrink-0"
                                                    style={{ background: color }}
                                                />
                                                <span className="text-sub-title-2">
                                                    {v.display_name || "—"}
                                                </span>
                                                {v.estimated && (
                                                    <span className="text-caption text-t-tertiary">
                                                        (est.)
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td>
                                            {v.vendor && (
                                                <StatusBadge status={v.status} stale={v.stale} />
                                            )}
                                        </td>
                                        <td className="text-right text-sub-title-2 tabular-nums">
                                            {v.vendor ? money(v.cost, currency) : "—"}
                                        </td>
                                        <td className="max-lg:hidden">
                                            <div className="flex items-center gap-3 w-44">
                                                <div className="relative grow h-3 rounded-[2px] bg-shade-09 dark:bg-shade-04">
                                                    <div
                                                        className="absolute top-0 left-0 bottom-0 rounded-[2px]"
                                                        style={{
                                                            width: `${Math.max(pct, 2)}%`,
                                                            background: color,
                                                            opacity: 0.85,
                                                        }}
                                                    />
                                                </div>
                                                <span className="shrink-0 text-caption text-t-tertiary tabular-nums w-8 text-right">
                                                    {v.vendor ? `${pct.toFixed(0)}%` : "—"}
                                                </span>
                                            </div>
                                        </td>
                                        <td className="text-t-secondary max-md:hidden">
                                            {v.vendor ? fmt(v.synced_at) : "—"}
                                        </td>
                                    </TableRow>
                                );
                            })}
                        </Table>
                    </div>
                )}
            </Card>
        </Layout>
    );
}

const PLACEHOLDER = [...Array(4)].map(() => ({
    vendor: "",
    display_name: "",
    status: "not_configured" as const,
    cost: 0,
    synced_at: "",
    stale: false,
    estimated: false,
}));
