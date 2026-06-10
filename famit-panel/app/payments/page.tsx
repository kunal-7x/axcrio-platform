"use client";

// Payments / Collections — Section F "Money".
//
// The money a tenant collects FROM their end-customers (invoices + payment
// links), distinct from the vendor wallet (the tenant's prepaid spend with
// Famit, which lives under /billing). Wired to the dormant-until-creds
// `/payments/*` backend: with no Razorpay/Stripe keys connected the page shows
// a calm "gateway not connected" state and treats draft intents as such —
// nothing errors. Premium "Signal" language, reusing the Billing visual system
// (HeroCard / data-table / state-block / pills) without touching any shared
// file or globals.css.

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import {
    getPaymentsHealth,
    getPaymentLinks,
    getFollowups,
    createPaymentLink,
    markPaid,
    refundLink,
    pickIntents,
    pickFollowups,
    PaymentsUnavailable,
    type PaymentsHealth,
    type PaymentIntent,
    type Followup,
    type ProviderStatus,
} from "./_api";
import {
    PaymentsHeader,
    HeroCard,
    ShareRow,
    IntentBadge,
    NotConfiguredPanel,
    ErrorBanner,
    money,
    fmt,
    fmtRelative,
    ghostBtnCls,
    PAY_COLORS,
} from "./_shared";

const STATUS_FILTERS = [
    { label: "All", value: "" },
    { label: "Pending", value: "issued" },
    { label: "Paid", value: "paid" },
    { label: "Failed", value: "failed" },
    { label: "Refunded", value: "refunded" },
];

export default function PaymentsPage() {
    const [health, setHealth] = useState<PaymentsHealth | null>(null);
    const [intents, setIntents] = useState<PaymentIntent[]>([]);
    const [followups, setFollowups] = useState<Followup[]>([]);
    const [currency, setCurrency] = useState("INR");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [statusFilter, setStatusFilter] = useState("");

    // create-link drawer state
    const [createOpen, setCreateOpen] = useState(false);

    // per-row action in flight
    const [acting, setActing] = useState<string>("");
    const [toast, setToast] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        Promise.allSettled([
            getPaymentsHealth(),
            getPaymentLinks({ limit: 100 }),
            getFollowups({ limit: 50 }),
        ])
            .then(([h, l, f]) => {
                // A 404 on any call means the module isn't mounted yet -> treat
                // as dormant (same calm UX as not_configured; keyed off `connected`).
                const any404 = [h, l, f].some(
                    (r) => r.status === "rejected" && r.reason instanceof PaymentsUnavailable
                );
                if (h.status === "fulfilled") setHealth(h.value);
                if (l.status === "fulfilled") {
                    setIntents(pickIntents(l.value));
                    if (l.value.currency) setCurrency(l.value.currency);
                }
                if (f.status === "fulfilled") setFollowups(pickFollowups(f.value));

                // surface a genuine (non-dormant) error if everything failed
                const realErr = [h, l, f].find(
                    (r) => r.status === "rejected" && !(r.reason instanceof PaymentsUnavailable)
                );
                if (realErr && realErr.status === "rejected" && !any404) {
                    setError(
                        realErr.reason instanceof Error
                            ? realErr.reason.message
                            : "Failed to load payments"
                    );
                }
            })
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        if (!toast) return;
        const t = setTimeout(() => setToast(null), 4000);
        return () => clearTimeout(t);
    }, [toast]);

    const healthCurrency = health?.currency || currency;
    const overallStatus: ProviderStatus =
        (health?.status as ProviderStatus) ||
        (health?.configured ? "configured" : "not_configured");
    const connected = overallStatus === "configured";

    // Provider list for the dormant panel — from health.providers if present,
    // else the two known providers default to not_configured.
    const providerRows = useMemo(() => {
        const fromHealth = health?.providers
            ? Object.entries(health.providers).map(([id, p]) => ({
                  label: p.display_name || labelFor(id),
                  status: p.status,
              }))
            : null;
        return (
            fromHealth || [
                { label: "Razorpay · INR", status: "not_configured" as ProviderStatus },
                { label: "Stripe", status: "not_configured" as ProviderStatus },
            ]
        );
    }, [health]);

    // ---- real KPIs (no fabricated deltas) ----
    const collected = useMemo(
        () =>
            intents
                .filter((i) => i.status === "paid")
                .reduce((s, i) => s + (i.amount || 0), 0),
        [intents]
    );
    const outstanding = useMemo(
        () =>
            intents
                .filter((i) => i.status === "issued" || i.status === "created")
                .reduce((s, i) => s + (i.amount || 0), 0),
        [intents]
    );
    const refunded = useMemo(
        () =>
            intents
                .filter((i) => i.status === "refunded" || i.status === "partially_refunded")
                .reduce((s, i) => s + (i.amount_refunded || i.amount || 0), 0),
        [intents]
    );
    const paidCount = intents.filter((i) => i.status === "paid").length;
    const totalCount = intents.length;
    const successRate = totalCount > 0 ? (paidCount / totalCount) * 100 : 0;

    // composition for the share meters (paid / pending / failed / refunded)
    const buckets = useMemo(() => {
        const sum = (pred: (i: PaymentIntent) => boolean) =>
            intents.filter(pred).reduce((s, i) => s + (i.amount || 0), 0);
        const paid = sum((i) => i.status === "paid");
        const pending = sum((i) => i.status === "issued" || i.status === "created");
        const failed = sum((i) => i.status === "failed" || i.status === "expired");
        const refundedAmt = sum(
            (i) => i.status === "refunded" || i.status === "partially_refunded"
        );
        const total = paid + pending + failed + refundedAmt;
        return [
            { label: "Collected", value: paid, color: PAY_COLORS[0] },
            { label: "Outstanding", value: pending, color: PAY_COLORS[1] },
            { label: "Failed / expired", value: failed, color: PAY_COLORS[2] },
            { label: "Refunded", value: refundedAmt, color: PAY_COLORS[3] },
        ].map((b) => ({ ...b, pct: total > 0 ? (b.value / total) * 100 : 0, total }));
    }, [intents]);

    const visibleIntents = useMemo(
        () => (statusFilter ? intents.filter((i) => i.status === statusFilter) : intents),
        [intents, statusFilter]
    );

    const onCreated = (msg: string) => {
        setToast({ kind: "success", msg });
        setCreateOpen(false);
        load();
    };

    const doMarkPaid = async (id: string) => {
        setActing(id);
        try {
            await markPaid(id);
            setToast({ kind: "success", msg: "Marked as paid." });
            load();
        } catch (e) {
            setToast({ kind: "error", msg: e instanceof Error ? e.message : "Failed" });
        } finally {
            setActing("");
        }
    };

    const doRefund = async (id: string) => {
        setActing(id);
        try {
            await refundLink(id);
            setToast({ kind: "success", msg: "Refund initiated." });
            load();
        } catch (e) {
            setToast({ kind: "error", msg: e instanceof Error ? e.message : "Failed" });
        } finally {
            setActing("");
        }
    };

    return (
        <Layout title="Payments">
            <PaymentsHeader
                title="Payments & Collections"
                subtitle="Issue payment links and invoices, track what your customers owe, and recover failed payments — all in one place."
                actions={
                    <>
                        <button onClick={load} className={ghostBtnCls} disabled={loading}>
                            <Icon
                                name="clock"
                                className={`size-4 fill-current ${loading ? "animate-spin" : ""}`}
                            />
                            {loading ? "Refreshing…" : "Refresh"}
                        </button>
                        <Button isBlack onClick={() => setCreateOpen(true)} className="h-9 px-5">
                            <Icon name="plus" className="size-4 fill-inherit mr-1.5" />
                            New payment link
                        </Button>
                    </>
                }
            />

            <ErrorBanner msg={error} />

            {/* live/connection status line */}
            {!loading && (
                <div className="flex items-center gap-2 mb-3 text-caption text-t-tertiary">
                    {connected ? (
                        <>
                            <span className="relative flex size-1.5">
                                <span className="absolute inline-flex h-full w-full rounded-full bg-primary-02 opacity-60 animate-ping" />
                                <span className="relative inline-flex size-1.5 rounded-full bg-primary-02" />
                            </span>
                            Gateway connected · {String(health?.default_provider || "razorpay")}
                        </>
                    ) : (
                        <>
                            <span className="inline-flex size-1.5 rounded-full bg-t-tertiary" />
                            Gateway not connected — links are saved as drafts
                        </>
                    )}
                </div>
            )}

            {/* dormant graceful state */}
            {!loading && !connected && (
                <div className="mb-3">
                    <NotConfiguredPanel providers={providerRows} />
                </div>
            )}

            {/* Hero KPIs — real collections signals */}
            <div className="grid grid-cols-4 gap-3 mb-3 max-xl:grid-cols-2 max-sm:grid-cols-1">
                <HeroCard
                    label="Collected"
                    glyph="income"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    loading={loading && !totalCount}
                    value={money(collected, healthCurrency)}
                    foot={
                        <>
                            <Icon name="check-circle" className="size-3.5 fill-t-tertiary" />
                            {paidCount} paid {paidCount === 1 ? "invoice" : "invoices"}
                        </>
                    }
                />
                <HeroCard
                    label="Outstanding"
                    glyph="clock"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    delay={70}
                    loading={loading && !totalCount}
                    value={money(outstanding, healthCurrency)}
                    foot={
                        <>
                            <Icon name="link" className="size-3.5 fill-t-tertiary" />
                            Awaiting payment
                        </>
                    }
                />
                <HeroCard
                    label="Success Rate"
                    glyph="chart"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    delay={140}
                    loading={loading && !totalCount}
                    value={totalCount > 0 ? `${successRate.toFixed(0)}%` : "—"}
                    foot={
                        <>
                            <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                            {paidCount}/{totalCount || 0} links paid
                        </>
                    }
                />
                <HeroCard
                    label="Refunded"
                    glyph="wallet"
                    glyphClass="fill-primary-05"
                    accent="var(--primary-05)"
                    delay={210}
                    loading={loading && !totalCount}
                    value={money(refunded, healthCurrency)}
                    foot={
                        <>
                            <Icon name="info" className="size-3.5 fill-t-tertiary" />
                            Returned to customers
                        </>
                    }
                />
            </div>

            {/* composition of collections + dunning side-by-side */}
            <div className="grid grid-cols-3 gap-3 mb-3 max-lg:grid-cols-1">
                <Card
                    className="col-span-2 max-lg:col-span-1"
                    title="Collections Breakdown"
                    headContent={
                        <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="layers" className="size-3.5 fill-t-tertiary" />
                            {totalCount} {totalCount === 1 ? "link" : "links"}
                        </span>
                    }
                >
                    <div className="p-4 max-lg:p-3">
                        {loading && !totalCount ? (
                            <div className="space-y-4">
                                {[...Array(4)].map((_, i) => (
                                    <div key={i} className="space-y-2">
                                        <div className="skeleton h-4 w-40" />
                                        <div className="skeleton h-1.5 w-full" />
                                    </div>
                                ))}
                            </div>
                        ) : totalCount === 0 ? (
                            <div className="state-block">
                                <span className="state-glyph">
                                    <Icon name="income" className="fill-inherit" />
                                </span>
                                <div className="state-title">No collections yet</div>
                                <div className="state-sub">
                                    Create a payment link to start collecting — the split of paid,
                                    outstanding and refunded amounts shows up here.
                                </div>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {buckets.map((b, i) => (
                                    <ShareRow
                                        key={b.label}
                                        label={b.label}
                                        value={b.total > 0 ? money(b.value, healthCurrency) : "—"}
                                        pct={b.pct}
                                        color={b.color}
                                        delay={i * 50}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                </Card>

                <Card
                    title="Recovery Queue"
                    headContent={
                        <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="bell" className="size-3.5 fill-t-tertiary" />
                            {followups.length}
                        </span>
                    }
                >
                    <div className="p-4 max-lg:p-3">
                        {loading && !followups.length ? (
                            <div className="space-y-3">
                                {[...Array(3)].map((_, i) => (
                                    <div key={i} className="skeleton h-12 w-full rounded-2xl" />
                                ))}
                            </div>
                        ) : followups.length === 0 ? (
                            <div className="state-block">
                                <span className="state-glyph">
                                    <Icon name="check-circle" className="fill-inherit" />
                                </span>
                                <div className="state-title">Nothing to recover</div>
                                <div className="state-sub">
                                    Failed or expired payments queue here for automatic follow-up.
                                </div>
                            </div>
                        ) : (
                            <div className="space-y-2.5">
                                {followups.slice(0, 6).map((f) => (
                                    <div
                                        key={f.id}
                                        className="flex items-center justify-between gap-3 p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30 rise-in"
                                    >
                                        <div className="min-w-0">
                                            <div className="text-body-2 font-medium text-t-primary truncate">
                                                {f.customer || f.intent_id}
                                            </div>
                                            <div className="text-caption text-t-tertiary">
                                                Attempt {f.attempts}/{f.max_attempts}
                                                {f.next_attempt_at
                                                    ? ` · next ${fmtRelative(f.next_attempt_at)}`
                                                    : ""}
                                            </div>
                                        </div>
                                        <span className="shrink-0 text-body-2 font-medium text-t-primary tabular-nums">
                                            {money(f.amount, f.currency || healthCurrency)}
                                        </span>
                                    </div>
                                ))}
                                {followups.length > 6 && (
                                    <div className="pt-1 text-center text-caption text-t-tertiary">
                                        +{followups.length - 6} more in queue
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </Card>
            </div>

            {/* Payment links table */}
            <Card
                title="Payment Links"
                headContent={
                    <div className="ml-3 flex items-center gap-1 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle max-md:hidden">
                        {STATUS_FILTERS.map((s) => {
                            const active = statusFilter === s.value;
                            return (
                                <button
                                    key={s.value}
                                    onClick={() => setStatusFilter(s.value)}
                                    className={`shrink-0 inline-flex items-center h-7 px-3 rounded-full text-caption transition-colors ${
                                        active
                                            ? "bg-b-surface1 text-t-primary shadow-widget dark:bg-shade-04"
                                            : "text-t-secondary hover:text-t-primary"
                                    }`}
                                >
                                    {s.label}
                                </button>
                            );
                        })}
                    </div>
                }
            >
                <div className="overflow-x-auto">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Customer</th>
                                <th>Description</th>
                                <th className="text-right">Amount</th>
                                <th>Status</th>
                                <th>Created</th>
                                <th className="text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading && !totalCount ? (
                                [...Array(5)].map((_, i) => (
                                    <tr key={i}>
                                        <td><div className="skeleton h-4 w-28" /></td>
                                        <td><div className="skeleton h-4 w-40" /></td>
                                        <td className="text-right"><div className="skeleton h-4 w-16 ml-auto" /></td>
                                        <td><div className="skeleton h-5 w-16" /></td>
                                        <td><div className="skeleton h-4 w-20" /></td>
                                        <td className="text-right"><div className="skeleton h-7 w-20 ml-auto" /></td>
                                    </tr>
                                ))
                            ) : visibleIntents.length === 0 ? (
                                <tr>
                                    <td colSpan={6}>
                                        <div className="state-block">
                                            <span className="state-glyph">
                                                <Icon name="link" className="fill-inherit" />
                                            </span>
                                            <div className="state-title">
                                                {statusFilter
                                                    ? "No links match this filter"
                                                    : "No payment links yet"}
                                            </div>
                                            <div className="state-sub">
                                                {statusFilter
                                                    ? "Try a different status filter."
                                                    : "Create your first payment link to bill a customer — it appears here with live status."}
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                visibleIntents.map((it) => {
                                    const isPending =
                                        it.status === "issued" || it.status === "created";
                                    const isPaid = it.status === "paid";
                                    const busy = acting === it.id;
                                    return (
                                        <tr key={it.id}>
                                            <td className="font-medium text-t-primary">
                                                {it.customer_name || it.customer || it.customer_phone || "—"}
                                            </td>
                                            <td className="text-t-secondary max-w-[20rem] truncate">
                                                {it.description || "—"}
                                            </td>
                                            <td className="text-right td-num text-t-primary font-medium">
                                                {money(it.amount, it.currency || healthCurrency)}
                                            </td>
                                            <td><IntentBadge status={it.status} /></td>
                                            <td className="text-t-tertiary">{fmt(it.created_at)}</td>
                                            <td className="text-right">
                                                <div className="inline-flex items-center gap-1.5">
                                                    {it.pay_url ? (
                                                        <a
                                                            href={it.pay_url}
                                                            target="_blank"
                                                            rel="noreferrer"
                                                            className="action"
                                                            title="Open payment link"
                                                        >
                                                            <Icon name="link" className="size-3.5 fill-current" />
                                                            Link
                                                        </a>
                                                    ) : null}
                                                    {isPending && (
                                                        <button
                                                            onClick={() => doMarkPaid(it.id)}
                                                            disabled={busy}
                                                            className="action"
                                                            title="Mark as paid (manual / offline)"
                                                        >
                                                            <Icon name="check" className="size-3.5 fill-current" />
                                                            {busy ? "…" : "Mark paid"}
                                                        </button>
                                                    )}
                                                    {isPaid && (
                                                        <button
                                                            onClick={() => doRefund(it.id)}
                                                            disabled={busy}
                                                            className="action"
                                                            title="Refund this payment"
                                                        >
                                                            <Icon name="reply" className="size-3.5 fill-current" />
                                                            {busy ? "…" : "Refund"}
                                                        </button>
                                                    )}
                                                    {!isPending && !isPaid && !it.pay_url && (
                                                        <span className="text-t-tertiary text-caption">—</span>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </Card>

            {/* create-link slide panel */}
            <CreateLinkPanel
                open={createOpen}
                onClose={() => setCreateOpen(false)}
                connected={connected}
                defaultCurrency={healthCurrency}
                onCreated={onCreated}
            />

            {/* toast */}
            {toast && (
                <div className="fixed bottom-6 right-6 z-50 max-w-sm">
                    <div className={`toast ${toast.kind === "success" ? "toast-success" : "toast-error"}`}>
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </div>
                </div>
            )}
        </Layout>
    );
}

function labelFor(id: string): string {
    if (id === "razorpay") return "Razorpay · INR";
    if (id === "stripe") return "Stripe";
    return id.charAt(0).toUpperCase() + id.slice(1);
}

// ------------------------------------------------------------------ //
// Create-link slide panel                                            //
// ------------------------------------------------------------------ //

function CreateLinkPanel({
    open,
    onClose,
    connected,
    defaultCurrency,
    onCreated,
}: {
    open: boolean;
    onClose: () => void;
    connected: boolean;
    defaultCurrency: string;
    onCreated: (msg: string) => void;
}) {
    const [amount, setAmount] = useState("");
    const [description, setDescription] = useState("");
    const [customer, setCustomer] = useState("");
    const [phone, setPhone] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [err, setErr] = useState("");

    useEffect(() => {
        if (open) {
            setAmount("");
            setDescription("");
            setCustomer("");
            setPhone("");
            setErr("");
        }
    }, [open]);

    const valid = Number(amount) > 0;

    const submit = async () => {
        if (!valid) {
            setErr("Enter an amount greater than zero.");
            return;
        }
        setSubmitting(true);
        setErr("");
        try {
            const r = await createPaymentLink({
                amount: amount.trim(),
                currency: defaultCurrency,
                description: description.trim(),
                customer: customer.trim(),
                customer_phone: phone.trim(),
            });
            if (r.status === "not_configured") {
                onCreated(
                    "Draft saved. Connect a payment provider to generate a live link and collect."
                );
            } else if (r.status === "error") {
                setErr(r.message || "Could not create the payment link.");
            } else {
                onCreated(
                    r.pay_url
                        ? "Payment link created and ready to share."
                        : "Payment link created."
                );
            }
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Failed to create payment link.");
        } finally {
            setSubmitting(false);
        }
    };

    const inputCls = "input-base w-full h-12 px-4 rounded-2xl text-body-2";

    return (
        <Modal open={open} onClose={onClose} isSlidePanel>
            <div className="flex h-full flex-col">
                <div className="px-6 pt-6 pb-4 border-b border-s-subtle">
                    <div className="page-head-eyebrow">
                        <span className="signal-glyph !h-3" aria-hidden>
                            <i /><i /><i />
                        </span>
                        New payment link
                    </div>
                    <h2 className="mt-1 text-h6 text-t-primary">Bill a customer</h2>
                    <p className="mt-1 text-body-2 text-t-secondary">
                        {connected
                            ? "Generates a shareable payment link your customer can pay instantly."
                            : "No provider connected yet — this saves a draft you can issue once a gateway is connected."}
                    </p>
                </div>

                <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
                    <Field label="Amount" hint={`In ${defaultCurrency}`}>
                        <input
                            type="number"
                            min="0"
                            step="0.01"
                            inputMode="decimal"
                            value={amount}
                            onChange={(e) => setAmount(e.target.value)}
                            placeholder="0.00"
                            className={inputCls}
                        />
                    </Field>
                    <Field label="Description" optional>
                        <input
                            type="text"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            placeholder="e.g. Annual plan — Acme Co."
                            className={inputCls}
                        />
                    </Field>
                    <Field label="Customer name" optional>
                        <input
                            type="text"
                            value={customer}
                            onChange={(e) => setCustomer(e.target.value)}
                            placeholder="Who is this for?"
                            className={inputCls}
                        />
                    </Field>
                    <Field label="Customer phone" optional hint="For follow-up / receipts">
                        <input
                            type="tel"
                            value={phone}
                            onChange={(e) => setPhone(e.target.value)}
                            placeholder="+91…"
                            className={inputCls}
                        />
                    </Field>

                    {err && (
                        <div className="toast toast-error">
                            <span className="size-1.5 rounded-full bg-current" />
                            {err}
                        </div>
                    )}
                </div>

                <div className="px-6 py-4 border-t border-s-subtle flex items-center gap-3">
                    <Button isStroke onClick={onClose} className="h-11 flex-1">
                        Cancel
                    </Button>
                    <Button
                        isBlack
                        onClick={submit}
                        disabled={!valid || submitting}
                        className="h-11 flex-1"
                    >
                        {submitting ? "Creating…" : connected ? "Create link" : "Save draft"}
                    </Button>
                </div>
            </div>
        </Modal>
    );
}

function Field({
    label,
    hint,
    optional,
    children,
}: {
    label: string;
    hint?: string;
    optional?: boolean;
    children: React.ReactNode;
}) {
    return (
        <label className="block">
            <div className="mb-1.5 flex items-center justify-between">
                <span className="text-button text-t-primary">{label}</span>
                {optional ? (
                    <span className="text-caption text-t-tertiary">Optional</span>
                ) : hint ? (
                    <span className="text-caption text-t-tertiary">{hint}</span>
                ) : null}
            </div>
            {children}
            {!optional && hint ? (
                <div className="mt-1 text-caption text-t-tertiary">{hint}</div>
            ) : null}
        </label>
    );
}
