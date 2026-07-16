"use client";

import { useEffect, useState, useCallback } from "react";
import Card from "@/components/Card";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import { getCreditsPricing, type CreditPricingMatrix, type CreditPricingService } from "@/lib/api";
import { cr, inr, NotEnabledPanel, HubBanner } from "./_shared";

const HEAD = ["Service", "Category", "Per", "Price", "₹", "Tracked"];

export default function PricingTab() {
    const [data, setData] = useState<CreditPricingMatrix | null>(null);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getCreditsPricing()
            .then((d) => {
                if (!d) {
                    setDormant(true);
                    return;
                }
                setData(d);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load pricing"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    if (dormant) return <NotEnabledPanel />;

    const services = data?.services || [];

    return (
        <>
            <HubBanner msg={error} />

            <div className="card mb-3 p-5 max-lg:p-3">
                <div className="flex items-start gap-3">
                    <span className="flex items-center justify-center size-10 rounded-full bg-b-surface1 shrink-0">
                        <Icon name="wallet" className="size-5 fill-t-secondary" />
                    </span>
                    <div>
                        <div className="text-sub-title-1 mb-1">What credits cost</div>
                        <p className="text-body-2 text-t-tertiary max-w-160">
                            Every Haptica service draws from your credit balance at the rates below. 1 credit
                            = ₹{data?.credit_rate_inr ?? 1}. “Tracked” services meter real usage to your wallet
                            today; the rest are listed at their published rate and meter as they go live.
                        </p>
                    </div>
                </div>
            </div>

            <Card title="Service pricing">
                <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                    <Table
                        cellsThead={HEAD.map((h) => (
                            <th key={h} className="!h-12.5 nth-4:text-right nth-5:text-right last:text-right">
                                {h}
                            </th>
                        ))}
                        isMobileVisibleTHead
                    >
                        {(loading ? PLACEHOLDER : services).map((s, idx) => (
                            <TableRow key={s.key || idx}>
                                <td className="max-w-90">
                                    <div className="text-t-primary">{s.label || "—"}</div>
                                    {s.description && (
                                        <div className="text-caption text-t-tertiary truncate max-md:hidden">
                                            {s.description}
                                        </div>
                                    )}
                                </td>
                                <td>{s.category ? <Badge variant="neutral">{s.category}</Badge> : "—"}</td>
                                <td className="text-t-secondary max-md:hidden">{s.unit || "—"}</td>
                                <td className="text-right tabular-nums text-sub-title-2">
                                    {s.key ? cr(s.price_credits) : "—"}
                                </td>
                                <td className="text-right tabular-nums text-t-secondary">
                                    {s.key ? inr(s.price_inr) : "—"}
                                </td>
                                <td className="text-right">
                                    {s.key ? (
                                        s.metered ? (
                                            <Badge variant="success" dot>
                                                Tracked
                                            </Badge>
                                        ) : (
                                            <Badge variant="neutral">Soon</Badge>
                                        )
                                    ) : (
                                        "—"
                                    )}
                                </td>
                            </TableRow>
                        ))}
                    </Table>
                </div>
            </Card>
        </>
    );
}

const PLACEHOLDER: CreditPricingService[] = [...Array(6)].map(() => ({
    key: "",
    label: "",
    category: "",
    unit: "",
    basis_inr: 0,
    markup_pct: 0,
    price_inr: 0,
    price_credits: 0,
    margin_inr: 0,
    margin_pct: null,
    metered: false,
    description: "",
}));
