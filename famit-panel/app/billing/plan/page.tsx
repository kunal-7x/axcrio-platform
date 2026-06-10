"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import {
    getBilling,
    getBillingLedger,
    setBilling,
    getTenants,
    type Billing,
    type LedgerEntry,
    type Tenant,
} from "@/lib/api";
import { useMe, isAdmin } from "@/lib/auth";
import { HeroCard, outcomeVariant, BillingHeader } from "../_shared";

type Toast = { msg: string; type: "success" | "error" };

function money(n: number | undefined, currency: string) {
    if (n == null) return "—";
    return `${currency || ""} ${n.toFixed(2)}`.trim();
}

function fmt(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

export default function BillingPlanPage() {
    const { me } = useMe();
    const admin = isAdmin(me);

    const [billing, setBillingState] = useState<Billing | null>(null);
    const [ledger, setLedger] = useState<LedgerEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        setLoadError("");
        Promise.all([getBilling(), getBillingLedger(100)])
            .then(([b, l]) => {
                setBillingState(b);
                setLedger(l.ledger);
            })
            .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load billing"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const currency = billing?.currency || "";
    const lowBalance = billing?.plan === "prepaid" && (billing?.balance ?? 0) <= 0;

    return (
        <Layout title="Billing · Plan & Ledger">
            <BillingHeader
                title="Plan & Ledger"
                subtitle="Your plan, rates and balance, plus a line-by-line ledger of every charged call."
            />
            {toast && (
                <div
                    className={`mb-3 p-3.5 rounded-2xl text-body-2 flex items-center justify-between gap-3 ring-1 ring-inset ${
                        toast.type === "success"
                            ? "bg-primary-02/8 text-primary-02 ring-primary-02/20"
                            : "bg-primary-03/8 text-primary-03 ring-primary-03/20"
                    }`}
                >
                    <span className="flex items-center gap-2">
                        <Icon
                            name={toast.type === "success" ? "check-circle" : "info"}
                            className="size-4 fill-current shrink-0"
                        />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            {loadError && (
                <div className="mb-3 p-3.5 rounded-2xl bg-primary-03/8 text-primary-03 text-body-2 ring-1 ring-inset ring-primary-03/20 flex items-center gap-2">
                    <Icon name="info" className="size-4 fill-current shrink-0" />
                    {loadError}
                </div>
            )}

            {lowBalance && (
                <div className="mb-3 p-3.5 rounded-2xl bg-primary-05/8 text-primary-05 text-body-2 ring-1 ring-inset ring-primary-05/20 flex items-center gap-2">
                    <Icon name="info" className="size-4 fill-current shrink-0" />
                    Insufficient balance — top up to continue placing calls. Calls are blocked while your prepaid balance is at or below zero.
                </div>
            )}

            {/* Summary heroes */}
            <div className="grid grid-cols-4 gap-3 mb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <HeroCard
                    label="Plan"
                    glyph="cube"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    loading={loading}
                    value={
                        <span className="capitalize flex items-center gap-2">
                            {billing?.plan ?? "—"}
                            {billing?.plan && (
                                <Badge variant={billing.plan === "prepaid" ? "info" : "neutral"}>
                                    {billing.plan === "prepaid" ? "Prepaid" : "Postpaid"}
                                </Badge>
                            )}
                        </span>
                    }
                    foot={`${money(billing?.rate_per_min, currency)}/min · ${money(billing?.rate_per_call, currency)}/call`}
                />
                <HeroCard
                    label="Balance"
                    glyph="wallet"
                    glyphClass={lowBalance ? "fill-primary-03" : "fill-primary-02"}
                    accent={lowBalance ? "var(--primary-03)" : "var(--primary-02)"}
                    delay={70}
                    loading={loading}
                    value={
                        <span className={lowBalance ? "text-primary-03" : undefined}>
                            {money(billing?.balance, currency)}
                        </span>
                    }
                    foot={billing?.plan === "prepaid" ? "Prepaid balance" : "Postpaid — billed in arrears"}
                />
                <HeroCard
                    label="MTD Minutes / Calls"
                    glyph="clock"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    delay={140}
                    loading={loading}
                    value={`${billing?.month_to_date?.minutes ?? 0} / ${billing?.month_to_date?.calls ?? 0}`}
                    foot={`${billing?.included_minutes ?? 0} included min`}
                />
                <HeroCard
                    label="MTD Cost"
                    glyph="income"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={210}
                    loading={loading}
                    value={money(billing?.month_to_date?.cost, currency)}
                    foot="Current billing period"
                />
            </div>

            <div className="flex gap-3 max-lg:flex-col">
                {/* Ledger */}
                <div className="flex-1 min-w-0">
                    <Card
                        title="Recent Charges"
                        headContent={
                            <span className="ml-3 text-caption text-t-tertiary">
                                {money(billing?.rate_per_min, currency)}/min + {money(billing?.rate_per_call, currency)}/call
                            </span>
                        }
                    >
                        <div className="overflow-x-auto px-3 pb-2">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>When</th>
                                        <th>Phone</th>
                                        <th>Outcome</th>
                                        <th className="text-right">Duration</th>
                                        <th className="text-right">Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        [...Array(6)].map((_, i) => (
                                            <tr key={i}>
                                                {[...Array(5)].map((_, j) => (
                                                    <td key={j}><div className="skeleton h-4 w-20" /></td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : ledger.length === 0 ? (
                                        <tr>
                                            <td colSpan={5}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon name="income" className="fill-inherit" />
                                                    </span>
                                                    <div className="state-title">No charges yet</div>
                                                    <div className="state-sub">
                                                        Per-call charges appear here as calls are metered.
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        ledger.map((e) => (
                                            <tr key={e.id}>
                                                <td className="text-t-secondary whitespace-nowrap">{fmt(e.at)}</td>
                                                <td className="text-t-secondary tabular-nums">{e.phone}</td>
                                                <td>
                                                    {e.outcome ? (
                                                        <Badge variant={outcomeVariant(e.outcome)}>
                                                            {e.outcome.replace(/_/g, " ")}
                                                        </Badge>
                                                    ) : (
                                                        <span className="text-t-tertiary">—</span>
                                                    )}
                                                </td>
                                                <td className="td-num text-right text-t-secondary">
                                                    {e.duration_s != null ? `${e.duration_s}s` : "—"}
                                                </td>
                                                <td className="td-num text-right font-medium text-t-primary">
                                                    {money(e.cost, e.currency || currency)}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>

                {/* Admin config */}
                {admin && (
                    <div className="w-96 max-lg:w-full shrink-0">
                        <AdminBillingPanel onSaved={(b) => { setBillingState(b); showToast("Billing updated", "success"); }} onError={(m) => showToast(m, "error")} />
                    </div>
                )}
            </div>
        </Layout>
    );
}

function AdminBillingPanel({ onSaved, onError }: { onSaved: (b: Billing) => void; onError: (m: string) => void }) {
    const [tenants, setTenants] = useState<Tenant[]>([]);
    const [tenantId, setTenantId] = useState("");
    const [plan, setPlan] = useState<"prepaid" | "postpaid">("postpaid");
    const [ratePerMin, setRatePerMin] = useState("");
    const [ratePerCall, setRatePerCall] = useState("");
    const [currency, setCurrency] = useState("");
    const [balance, setBalance] = useState("");
    const [includedMinutes, setIncludedMinutes] = useState("");
    const [topup, setTopup] = useState("");
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        getTenants()
            .then((r) => {
                setTenants(r.tenants);
                if (r.tenants.length > 0) setTenantId(r.tenants[0].tenant_id);
            })
            .catch(() => {});
    }, []);

    async function handleSave(e: React.FormEvent) {
        e.preventDefault();
        if (!tenantId) return;
        setSaving(true);
        try {
            const payload: Record<string, unknown> = { plan };
            if (ratePerMin !== "") payload.rate_per_min = parseFloat(ratePerMin);
            if (ratePerCall !== "") payload.rate_per_call = parseFloat(ratePerCall);
            if (currency !== "") payload.currency = currency;
            if (balance !== "") payload.balance = parseFloat(balance);
            if (includedMinutes !== "") payload.included_minutes = parseInt(includedMinutes);
            if (topup !== "") payload.topup = parseFloat(topup);
            const updated = await setBilling(tenantId, payload);
            onSaved(updated);
            setTopup("");
            setBalance("");
        } catch (err: unknown) {
            onError(err instanceof Error ? err.message : "Failed to update billing");
        } finally {
            setSaving(false);
        }
    }

    const labelCls = "block text-overline text-t-tertiary mb-1.5";
    const inputCls =
        "w-full h-10 px-3 input-base rounded-2xl text-body-2";

    return (
        <Card title="Admin · Set Plan & Rates">
            <form onSubmit={handleSave} className="px-5 pb-5 space-y-4">
                <div>
                    <label className={labelCls}>Tenant</label>
                    <select value={tenantId} onChange={(e) => setTenantId(e.target.value)} className={inputCls}>
                        {tenants.map((t) => (
                            <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label className={labelCls}>Plan</label>
                    <select value={plan} onChange={(e) => setPlan(e.target.value as "prepaid" | "postpaid")} className={inputCls}>
                        <option value="postpaid">postpaid</option>
                        <option value="prepaid">prepaid</option>
                    </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className={labelCls}>Rate / min</label>
                        <input type="number" step="0.01" value={ratePerMin} onChange={(e) => setRatePerMin(e.target.value)} placeholder="0.00" className={inputCls} />
                    </div>
                    <div>
                        <label className={labelCls}>Rate / call</label>
                        <input type="number" step="0.01" value={ratePerCall} onChange={(e) => setRatePerCall(e.target.value)} placeholder="0.00" className={inputCls} />
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className={labelCls}>Currency</label>
                        <input type="text" value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="INR" className={inputCls} />
                    </div>
                    <div>
                        <label className={labelCls}>Included mins</label>
                        <input type="number" value={includedMinutes} onChange={(e) => setIncludedMinutes(e.target.value)} placeholder="0" className={inputCls} />
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className={labelCls}>Set balance</label>
                        <input type="number" step="0.01" value={balance} onChange={(e) => setBalance(e.target.value)} placeholder="absolute" className={inputCls} />
                    </div>
                    <div>
                        <label className={labelCls}>Top up (+)</label>
                        <input type="number" step="0.01" value={topup} onChange={(e) => setTopup(e.target.value)} placeholder="adds" className={inputCls} />
                    </div>
                </div>
                <Button isBlack className="w-full justify-center" disabled={saving}>
                    {saving ? "Saving…" : "Save Billing"}
                </Button>
            </form>
        </Card>
    );
}
