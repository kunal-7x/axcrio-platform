"use client";

import { useEffect, useState, useCallback } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import KpiCard from "@/components/KpiCard";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import NoFound from "@/components/NoFound";
import { getCreditsUsage, type CreditUsage } from "@/lib/api";
import { Sparkline } from "../billing/_shared";
import { cr, inr, NotEnabledPanel, HubBanner } from "./_shared";

const HEAD = ["Service", "Category", "Usage", "Credits", "₹"];

export default function UsageTab() {
    const [data, setData] = useState<CreditUsage | null>(null);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getCreditsUsage()
            .then((d) => {
                if (!d) {
                    setDormant(true);
                    return;
                }
                setData(d);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load usage"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    if (dormant) return <NotEnabledPanel />;

    const services = data?.services || [];
    const top = services[0];
    const spark = (data?.series || []).map((p) => ({ cost: p.cost_inr }));

    return (
        <>
            <HubBanner msg={error} />

            <div className="grid grid-cols-3 gap-3 mb-3 max-md:grid-cols-1">
                <KpiCard
                    label="Spent this month"
                    icon="chart"
                    tone="info"
                    value={loading ? "—" : cr(data?.total_credits)}
                    sub={loading ? "" : inr(data?.total_inr)}
                    spark={(data?.series || []).map((p) => p.cost_inr)}
                />
                <KpiCard
                    label="Top service"
                    icon="wallet"
                    tone="neutral"
                    value={loading ? "—" : top ? top.label : "—"}
                    sub={top ? `${cr(top.cost_credits)} · ${inr(top.cost_inr)}` : "No usage yet"}
                />
                <KpiCard
                    label="Services used"
                    icon="layers"
                    tone="success"
                    value={loading ? "—" : `${services.length}`}
                    sub="this billing period"
                />
            </div>

            <Card
                title="Usage by service"
                headContent={
                    spark.length > 1 ? (
                        <div className="ml-auto mr-3 max-md:hidden">
                            <Sparkline data={spark} />
                        </div>
                    ) : undefined
                }
            >
                {!loading && services.length === 0 ? (
                    <NoFound title="No usage this period" />
                ) : (
                    <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                        <Table
                            cellsThead={HEAD.map((h) => (
                                <th key={h} className="!h-12.5 nth-4:text-right last:text-right">
                                    {h}
                                </th>
                            ))}
                            isMobileVisibleTHead
                        >
                            {(loading ? PLACEHOLDER : services).map((s, idx) => (
                                <TableRow key={s.service || idx}>
                                    <td className="text-t-primary">{s.label || "—"}</td>
                                    <td>
                                        {s.category ? (
                                            <Badge variant="neutral">{s.category}</Badge>
                                        ) : (
                                            "—"
                                        )}
                                    </td>
                                    <td className="text-t-secondary tabular-nums max-md:hidden">
                                        {s.count ? `${s.count} ${s.count === 1 ? "event" : "events"}` : "—"}
                                    </td>
                                    <td className="text-right tabular-nums text-sub-title-2">
                                        {s.label ? cr(s.cost_credits) : "—"}
                                    </td>
                                    <td className="text-right tabular-nums text-t-secondary">
                                        {s.label ? inr(s.cost_inr) : "—"}
                                    </td>
                                </TableRow>
                            ))}
                        </Table>
                    </div>
                )}
            </Card>

            <div className="mt-3">
                <Button as="link" href="/credits?tab=pricing" isStroke>
                    See per-service pricing
                </Button>
            </div>
        </>
    );
}

const PLACEHOLDER: CreditUsage["services"] = [...Array(5)].map(() => ({
    service: "",
    label: "",
    category: "",
    unit: "",
    qty: 0,
    count: 0,
    cost_inr: 0,
    cost_credits: 0,
}));
