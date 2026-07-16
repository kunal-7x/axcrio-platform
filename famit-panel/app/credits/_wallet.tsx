"use client";

import { useEffect, useState, useCallback } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import KpiCard from "@/components/KpiCard";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import NoFound from "@/components/NoFound";
import {
    getCreditsHealth,
    getCreditsWallet,
    getCreditsLedger,
    type CreditWallet,
    type CreditLedgerEntry,
} from "@/lib/api";
import { cr, inr, fmtDate, NotEnabledPanel, HubBanner } from "./_shared";

function signedCr(n: number): React.ReactNode {
    const pos = n >= 0;
    return (
        <span className={pos ? "text-primary-02" : "text-t-primary"}>
            {pos ? "+" : ""}
            {cr(n)}
        </span>
    );
}

function kindBadge(kind: CreditLedgerEntry["kind"]) {
    if (kind === "topup") return <Badge variant="success">Top-up</Badge>;
    if (kind === "grant") return <Badge variant="info">Grant</Badge>;
    if (kind === "adjust") return <Badge variant="warning">Adjustment</Badge>;
    return <Badge variant="neutral">Usage</Badge>;
}

const ACT_HEAD = ["When", "Activity", "Detail", "Credits", "₹"];

export default function WalletTab() {
    const [wallet, setWallet] = useState<CreditWallet | null>(null);
    const [ledger, setLedger] = useState<CreditLedgerEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        Promise.all([getCreditsHealth(), getCreditsWallet(), getCreditsLedger(10)])
            .then(([health, w, l]) => {
                if (!health && !w) {
                    setDormant(true);
                    return;
                }
                setDormant(false);
                setWallet(w);
                setLedger(l.ledger || []);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load wallet"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    if (dormant) return <NotEnabledPanel />;

    return (
        <>
            <HubBanner msg={error} />

            {wallet?.low_balance && (
                <HubBanner
                    tone="warning"
                    msg={`Low balance — ${cr(wallet.balance_credits)} (${inr(
                        wallet.balance_inr
                    )}) left. Top up to keep calls, messages and AI services running.`}
                />
            )}

            {/* Hero balance + KPIs */}
            <div className="card mb-3 p-5 max-lg:p-3">
                <div className="flex items-end justify-between gap-4 flex-wrap">
                    <div>
                        <div className="text-overline text-t-tertiary mb-1">Available balance</div>
                        <div className="text-h2 tabular-nums max-lg:text-h3">
                            {loading ? "—" : cr(wallet?.balance_credits)}
                        </div>
                        <div className="text-body-2 text-t-tertiary mt-1">
                            {loading ? "" : `${inr(wallet?.balance_inr)} · 1 credit = ₹${wallet?.credit_rate_inr ?? 1}`}
                            {wallet?.held_credits ? ` · ${cr(wallet.held_credits)} on hold` : ""}
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        {wallet?.plan && (
                            <Badge variant={wallet.plan === "prepaid" ? "info" : "neutral"}>
                                {wallet.plan === "prepaid" ? "Prepaid" : "Postpaid"}
                            </Badge>
                        )}
                        <Button as="link" href="/credits?tab=buy" isBlack icon="plus">
                            Buy credits
                        </Button>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-3 max-lg:grid-cols-3 max-md:grid-cols-1">
                <KpiCard
                    label="Spent this month"
                    icon="chart"
                    tone="info"
                    value={loading ? "—" : cr(wallet?.mtd_spend_credits)}
                    sub={loading ? "" : inr(wallet?.mtd_spend_inr)}
                />
                <KpiCard
                    label="Lifetime top-ups"
                    icon="arrow-up-right"
                    tone="success"
                    value={loading ? "—" : cr(wallet?.lifetime_topup_credits)}
                    sub={loading ? "" : inr(wallet?.lifetime_topup_inr)}
                />
                <KpiCard
                    label="Lifetime spend"
                    icon="wallet"
                    tone="neutral"
                    value={loading ? "—" : cr(wallet?.lifetime_spend_credits)}
                    sub={loading ? "" : inr(wallet?.lifetime_spend_inr)}
                />
            </div>

            {/* Recent activity */}
            <Card
                title="Recent activity"
                headContent={
                    <Button as="link" href="/credits?tab=usage" isStroke className="ml-3 !h-9 !px-4 max-md:hidden">
                        View usage
                    </Button>
                }
            >
                {!loading && ledger.length === 0 ? (
                    <NoFound title="No activity yet" />
                ) : (
                    <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                        <Table
                            cellsThead={ACT_HEAD.map((h) => (
                                <th
                                    className="!h-12.5 nth-4:text-right last:text-right"
                                    key={h}
                                >
                                    {h}
                                </th>
                            ))}
                            isMobileVisibleTHead
                        >
                            {(loading ? PLACEHOLDER : ledger).map((e, idx) => (
                                <TableRow key={e.id || idx}>
                                    <td className="text-t-secondary whitespace-nowrap">
                                        {e.at ? fmtDate(e.at) : "—"}
                                    </td>
                                    <td>{e.id ? kindBadge(e.kind) : "—"}</td>
                                    <td className="text-t-secondary max-md:hidden">
                                        {e.description || "—"}
                                    </td>
                                    <td className="text-right tabular-nums text-sub-title-2">
                                        {e.id ? signedCr(e.amount_credits) : "—"}
                                    </td>
                                    <td className="text-right tabular-nums text-t-secondary">
                                        {e.id ? inr(Math.abs(e.amount_inr)) : "—"}
                                    </td>
                                </TableRow>
                            ))}
                        </Table>
                    </div>
                )}
            </Card>
        </>
    );
}

const PLACEHOLDER: CreditLedgerEntry[] = [...Array(6)].map(() => ({
    id: "",
    kind: "debit",
    service: "",
    description: "",
    amount_inr: 0,
    amount_credits: 0,
    status: "",
    ref: "",
    at: "",
}));
