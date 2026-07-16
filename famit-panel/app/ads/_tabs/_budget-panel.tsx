"use client";

// Ad-Engine · BUDGET panel (Wave 2).
//
// The vendor's own ad-budget wallet: a balance hero, a "Fund" flow that opens
// the Razorpay checkout (vendor-own-card model — money is funded on the gateway,
// credited to the paise balance server-side after the signature is verified), a
// spent-vs-funded pacing meter, and the credit/debit ledger.
//
// Reuses the design system verbatim — Card / KpiCard / Table / TableRow / Badge /
// Button / state-block / skeleton / meter. Zero raw hex; every colour a token.
// Money stays minor units (paise) end-to-end; fmtMoney renders it.
//
// Dormant-safe: reads degrade to {kind:"dormant"} (404 until the router mounts /
// a gateway key lands) and render the honest "connect a gateway" state — never an
// error wall. The fund/confirm mutations throw a friendly message the toast shows.

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import Card from "@/components/Card";
import KpiCard from "@/components/KpiCard";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import { SkeletonStats, SkeletonTableRows } from "@/components/Skeleton";
import {
    fmtMoney,
    fmtTs,
    getBudgetBalance,
    getBudgetLedger,
    fundBudget,
    confirmBudget,
    useRealtimeRefresh,
    type BudgetBalance,
    type BudgetLedgerRow,
    type ReadResult,
} from "../_lib";
import type { ToastFn } from "../_shared";

// The Razorpay checkout typings + a tiny lazy script loader. We only touch the
// gateway when the vendor actually funds, so the script loads on demand.
type RazorpayHandlerResponse = {
    razorpay_payment_id: string;
    razorpay_order_id: string;
    razorpay_signature: string;
};
type RazorpayOptions = {
    key: string;
    order_id: string;
    amount: number;
    currency: string;
    name?: string;
    description?: string;
    handler: (r: RazorpayHandlerResponse) => void;
    modal?: { ondismiss?: () => void };
    theme?: { color?: string };
    prefill?: Record<string, string>;
};
type RazorpayInstance = { open: () => void };
declare global {
    interface Window {
        Razorpay?: new (o: RazorpayOptions) => RazorpayInstance;
    }
}

function loadRazorpay(): Promise<boolean> {
    return new Promise((resolve) => {
        if (typeof window === "undefined") return resolve(false);
        if (window.Razorpay) return resolve(true);
        const s = document.createElement("script");
        s.src = "https://checkout.razorpay.com/v1/checkout.js";
        s.onload = () => resolve(true);
        s.onerror = () => resolve(false);
        document.body.appendChild(s);
    });
}

// Preset top-up amounts (in major rupees) the vendor can one-tap.
const PRESETS_MAJOR = [1000, 5000, 10000, 25000];

export type BudgetPanelProps = {
    currency?: string;
    writable: boolean;
    toast: ToastFn;
    // Optional: bubble a balance change up so a parent (wizard budget step) can react.
    onFunded?: () => void;
};

export default function BudgetPanel({ currency = "INR", writable, toast, onFunded }: BudgetPanelProps) {
    const [balRes, setBalRes] = useState<ReadResult<BudgetBalance> | null>(null);
    const [ledgerRes, setLedgerRes] = useState<ReadResult<{ ok: boolean; ledger: BudgetLedgerRow[] }> | null>(null);
    const [busy, setBusy] = useState(true);

    const load = useCallback(() => {
        setBusy(true);
        Promise.all([getBudgetBalance(), getBudgetLedger()])
            .then(([b, l]) => {
                setBalRes(b);
                setLedgerRes(l);
            })
            .finally(() => setBusy(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);
    useRealtimeRefresh(load, 30000);

    const balance = balRes?.kind === "ok" ? balRes.data : null;
    const ccy = balance?.currency || currency;
    const gatewayReady = !!balance?.gateway?.configured;
    const dormant = balRes?.kind === "dormant" && ledgerRes?.kind === "dormant";

    const ledger: BudgetLedgerRow[] = ledgerRes?.kind === "ok" ? ledgerRes.data.ledger || [] : [];

    // Spent-vs-funded pacing — the share of lifetime funding already spent.
    const funded = balance?.funded_total_minor ?? 0;
    const spent = balance?.spent_total_minor ?? 0;
    const spentRatio = funded > 0 ? Math.min(1, spent / funded) : 0;
    const spentPct = Math.round(spentRatio * 100);

    // ---- fund flow ----
    const [fundOpen, setFundOpen] = useState(false);
    const [amountMajor, setAmountMajor] = useState<string>("5000");
    const [funding, setFunding] = useState(false);

    const amountMinor = useMemo(() => {
        const n = Number(amountMajor.replace(/[^\d.]/g, ""));
        return Number.isFinite(n) && n > 0 ? Math.round(n * 100) : 0;
    }, [amountMajor]);

    const startFund = useCallback(async () => {
        if (amountMinor <= 0) {
            toast("Enter an amount above zero.", "error");
            return;
        }
        setFunding(true);
        try {
            const intent = await fundBudget(amountMinor, { currency: ccy });
            if (intent.needs_setup || intent.status === "not_configured" || !intent.public_key) {
                toast("Connect a payment gateway first, then fund your ad budget.", "error");
                return;
            }
            const ok = await loadRazorpay();
            if (!ok || !window.Razorpay) {
                toast("Couldn't reach the payment checkout. Try again shortly.", "error");
                return;
            }
            const rzp = new window.Razorpay({
                key: intent.public_key,
                order_id: intent.order_id,
                amount: intent.amount_minor,
                currency: intent.currency || ccy,
                name: "Ad budget",
                description: "Top up your autonomous ad-engine budget",
                handler: async (r) => {
                    try {
                        const res = await confirmBudget(
                            intent.intent_id,
                            r.razorpay_payment_id,
                            r.razorpay_signature,
                        );
                        if (res.ok) {
                            toast(`Added ${fmtMoney(res.credited_minor ?? amountMinor, ccy)} to your budget.`, "success");
                            setFundOpen(false);
                            load();
                            onFunded?.();
                        } else {
                            toast("Payment received — confirming your balance is taking a moment. Refresh shortly.", "error");
                        }
                    } catch (e) {
                        toast(e instanceof Error ? e.message : "Couldn't confirm the payment.", "error");
                    }
                },
                modal: { ondismiss: () => setFunding(false) },
            });
            rzp.open();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't start funding.", "error");
        } finally {
            setFunding(false);
        }
    }, [amountMinor, ccy, toast, load, onFunded]);

    return (
        <Card
            title="Ad budget"
            headContent={
                <Badge variant={gatewayReady ? "success" : "neutral"} dot className="mr-3">
                    {gatewayReady ? "Gateway connected" : "Gateway not set"}
                </Badge>
            }
        >
            <div className="px-3 pb-2 space-y-3">
                {busy && !balance ? (
                    <SkeletonStats count={3} />
                ) : (
                    <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-1">
                        <KpiCard
                            label="Available balance"
                            icon="wallet"
                            tone="info"
                            value={fmtMoney(balance?.balance_minor ?? 0, ccy)}
                            sub={gatewayReady ? "Ready to spend on ads" : "Connect a gateway to fund"}
                            meter={funded > 0 ? 1 - spentRatio : null}
                        />
                        <KpiCard
                            label="Funded to date"
                            icon="plus"
                            tone="neutral"
                            value={fmtMoney(funded, ccy)}
                            sub="Total topped up across all time"
                        />
                        <KpiCard
                            label="Spent to date"
                            icon="chart"
                            tone="neutral"
                            value={fmtMoney(spent, ccy)}
                            sub={funded > 0 ? `${spentPct}% of funding used` : "No spend yet"}
                            meter={funded > 0 ? spentRatio : null}
                        />
                    </div>
                )}

                {/* Fund control + the honest gateway hint */}
                <div className="flex items-center justify-between gap-3 flex-wrap pt-1">
                    <p className="text-caption text-t-tertiary max-w-md">
                        You fund your own ad budget through your payment gateway. Money only
                        leaves once a campaign goes live — in dry-run nothing spends.
                    </p>
                    {writable && (
                        <Button
                            isBlack
                            icon="plus"
                            onClick={() => setFundOpen(true)}
                            disabled={dormant}
                        >
                            Fund budget
                        </Button>
                    )}
                </div>

                {/* Ledger */}
                <div className="pt-2">
                    <div className="text-overline uppercase tracking-[0.06em] text-t-tertiary pl-2 mb-1">
                        Recent activity
                    </div>
                    {busy && !ledger.length ? (
                        <Table
                            cellsThead={
                                <>
                                    <th>When</th>
                                    <th>Type</th>
                                    <th className="text-right">Amount</th>
                                    <th className="text-right">Balance</th>
                                </>
                            }
                        >
                            <SkeletonTableRows rows={4} cols={4} />
                        </Table>
                    ) : ledger.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="wallet" className="fill-inherit" />
                            </span>
                            <div className="state-title">
                                {dormant ? "Budget funding is coming soon" : "No budget activity yet"}
                            </div>
                            <div className="state-sub max-w-md mx-auto">
                                {dormant
                                    ? "Once your payment gateway is connected on the server, you'll fund and track your ad budget here."
                                    : "Top up your ad budget to see credits, and live spend as it draws down."}
                            </div>
                        </div>
                    ) : (
                        <Table
                            cellsThead={
                                <>
                                    <th>When</th>
                                    <th>Type</th>
                                    <th className="text-right">Amount</th>
                                    <th className="text-right">Balance</th>
                                </>
                            }
                        >
                            {ledger.map((row, i) => {
                                const credit = row.kind === "credit";
                                return (
                                    <TableRow key={`${row.ts}-${i}`}>
                                        <td className="text-t-secondary whitespace-nowrap">{fmtTs(row.ts)}</td>
                                        <td>
                                            <Badge variant={credit ? "success" : "neutral"}>
                                                {credit ? "Top-up" : "Ad spend"}
                                            </Badge>
                                        </td>
                                        <td className="text-right tabular-nums text-t-primary whitespace-nowrap">
                                            {credit ? "+" : "−"}
                                            {fmtMoney(Math.abs(row.delta_minor), row.currency || ccy)}
                                        </td>
                                        <td className="text-right tabular-nums text-t-secondary whitespace-nowrap">
                                            {fmtMoney(row.balance_after_minor, row.currency || ccy)}
                                        </td>
                                    </TableRow>
                                );
                            })}
                        </Table>
                    )}
                </div>
            </div>

            {/* Fund modal — preset chips + custom amount */}
            <Modal open={fundOpen} onClose={() => setFundOpen(false)}>
                <div className="text-h5 text-t-primary">Fund your ad budget</div>
                <p className="text-body-2 text-t-secondary mt-2">
                    Choose how much to add. You&apos;ll complete payment on your gateway; the balance
                    updates the moment it&apos;s confirmed.
                </p>
                <div className="grid grid-cols-4 gap-2 mt-5 max-sm:grid-cols-2">
                    {PRESETS_MAJOR.map((p) => {
                        const active = amountMajor === String(p);
                        return (
                            <button
                                key={p}
                                onClick={() => setAmountMajor(String(p))}
                                className={`h-11 rounded-2xl text-button transition-all ring-1 ring-inset ${
                                    active
                                        ? "bg-b-surface1 text-t-primary ring-s-highlight shadow-widget dark:bg-shade-04"
                                        : "bg-b-surface2 text-t-secondary ring-s-subtle hover:text-t-primary"
                                }`}
                            >
                                {fmtMoney(p * 100, ccy)}
                            </button>
                        );
                    })}
                </div>
                <label className="block mt-4">
                    <span className="text-caption text-t-tertiary">Or enter a custom amount</span>
                    <div className="mt-1.5 flex items-center h-12 px-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset focus-within:ring-s-highlight">
                        <span className="text-t-tertiary mr-1">{ccy === "INR" ? "₹" : ""}</span>
                        <input
                            inputMode="decimal"
                            value={amountMajor}
                            onChange={(e) => setAmountMajor(e.target.value)}
                            className="w-full bg-transparent outline-none text-body-1 text-t-primary tabular-nums"
                            placeholder="5000"
                        />
                    </div>
                </label>
                {!gatewayReady && (
                    <div className="mt-4 flex items-start gap-2 text-caption text-t-secondary p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset">
                        <Icon name="info" className="size-4 shrink-0 fill-primary-05 mt-0.5" />
                        <span>
                            No payment gateway is connected yet. Add one in your payment settings, then
                            funding will go through here.
                        </span>
                    </div>
                )}
                <div className="flex items-center justify-end gap-3 mt-6">
                    <Button isStroke onClick={() => setFundOpen(false)}>
                        Cancel
                    </Button>
                    <Button isBlack onClick={startFund} disabled={funding || amountMinor <= 0}>
                        {funding ? "Opening checkout…" : `Add ${fmtMoney(amountMinor, ccy)}`}
                    </Button>
                </div>
            </Modal>
        </Card>
    );
}
