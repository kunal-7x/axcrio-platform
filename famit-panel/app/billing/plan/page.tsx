"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
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
            {toast && (
                <div
                    className={`mb-4 p-3 rounded-2xl text-body-2 flex items-center justify-between gap-3 ${
                        toast.type === "success"
                            ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                            : "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                    }`}
                >
                    <span>{toast.msg}</span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            {loadError && (
                <div className="mb-4 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">
                    {loadError}
                </div>
            )}

            {lowBalance && (
                <div className="mb-4 p-3 rounded-2xl bg-amber-50 text-amber-700 text-body-2 dark:bg-amber-900/20 dark:text-amber-400">
                    Insufficient balance — top up to continue placing calls. (Calls are blocked while your prepaid balance is at or below zero.)
                </div>
            )}

            {/* Summary cards */}
            <div className="grid grid-cols-4 gap-4 mb-6 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <div className="card p-4 flex flex-col gap-1">
                    <div className="text-caption text-t-tertiary">Plan</div>
                    <div className="text-h5 text-t-primary capitalize">{loading ? "…" : billing?.plan ?? "—"}</div>
                </div>
                <div className="card p-4 flex flex-col gap-1">
                    <div className="text-caption text-t-tertiary">Balance</div>
                    <div className={`text-h5 ${lowBalance ? "text-red-500" : "text-t-primary"}`}>
                        {loading ? "…" : money(billing?.balance, currency)}
                    </div>
                </div>
                <div className="card p-4 flex flex-col gap-1">
                    <div className="text-caption text-t-tertiary">MTD Minutes / Calls</div>
                    <div className="text-h5 text-t-primary">
                        {loading ? "…" : `${billing?.month_to_date?.minutes ?? 0} / ${billing?.month_to_date?.calls ?? 0}`}
                    </div>
                </div>
                <div className="card p-4 flex flex-col gap-1">
                    <div className="text-caption text-t-tertiary">MTD Cost</div>
                    <div className="text-h5 text-t-primary">
                        {loading ? "…" : money(billing?.month_to_date?.cost, currency)}
                    </div>
                </div>
            </div>

            <div className="flex gap-6 max-lg:flex-col">
                {/* Ledger */}
                <div className="flex-1 min-w-0">
                    <Card title="Recent Charges">
                        <div className="px-5 pb-2 text-caption text-t-tertiary">
                            Rates: {money(billing?.rate_per_min, currency)}/min + {money(billing?.rate_per_call, currency)}/call ·
                            {" "}Included minutes: {billing?.included_minutes ?? 0}
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                                <thead>
                                    <tr>
                                        <th>When</th>
                                        <th>Phone</th>
                                        <th>Outcome</th>
                                        <th>Duration</th>
                                        <th>Cost</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        <tr><td colSpan={5} className="py-8 text-center text-t-secondary">Loading…</td></tr>
                                    ) : ledger.length === 0 ? (
                                        <tr><td colSpan={5} className="py-12 text-center text-t-tertiary">No charges yet</td></tr>
                                    ) : (
                                        ledger.map((e) => (
                                            <tr key={e.id} className="border-t border-s-subtle hover:bg-b-surface2/50 transition-colors">
                                                <td className="text-t-secondary">{fmt(e.at)}</td>
                                                <td className="text-t-secondary">{e.phone}</td>
                                                <td className="text-t-secondary capitalize">{(e.outcome || "").replace(/_/g, " ") || "—"}</td>
                                                <td className="text-t-secondary">{e.duration_s != null ? `${e.duration_s}s` : "—"}</td>
                                                <td className="font-medium">{money(e.cost, e.currency || currency)}</td>
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

    const inputCls = "w-full h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight";

    return (
        <Card title="Admin · Set Plan & Rates">
            <form onSubmit={handleSave} className="px-5 pb-5 space-y-4">
                <div>
                    <label className="block text-caption text-t-secondary mb-2">Tenant</label>
                    <select value={tenantId} onChange={(e) => setTenantId(e.target.value)} className={inputCls}>
                        {tenants.map((t) => (
                            <option key={t.tenant_id} value={t.tenant_id}>{t.name} ({t.tenant_id})</option>
                        ))}
                    </select>
                </div>
                <div>
                    <label className="block text-caption text-t-secondary mb-2">Plan</label>
                    <select value={plan} onChange={(e) => setPlan(e.target.value as "prepaid" | "postpaid")} className={inputCls}>
                        <option value="postpaid">postpaid</option>
                        <option value="prepaid">prepaid</option>
                    </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-caption text-t-secondary mb-2">Rate / min</label>
                        <input type="number" step="0.01" value={ratePerMin} onChange={(e) => setRatePerMin(e.target.value)} placeholder="0.00" className={inputCls} />
                    </div>
                    <div>
                        <label className="block text-caption text-t-secondary mb-2">Rate / call</label>
                        <input type="number" step="0.01" value={ratePerCall} onChange={(e) => setRatePerCall(e.target.value)} placeholder="0.00" className={inputCls} />
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-caption text-t-secondary mb-2">Currency</label>
                        <input type="text" value={currency} onChange={(e) => setCurrency(e.target.value)} placeholder="INR" className={inputCls} />
                    </div>
                    <div>
                        <label className="block text-caption text-t-secondary mb-2">Included mins</label>
                        <input type="number" value={includedMinutes} onChange={(e) => setIncludedMinutes(e.target.value)} placeholder="0" className={inputCls} />
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-caption text-t-secondary mb-2">Set balance</label>
                        <input type="number" step="0.01" value={balance} onChange={(e) => setBalance(e.target.value)} placeholder="absolute" className={inputCls} />
                    </div>
                    <div>
                        <label className="block text-caption text-t-secondary mb-2">Top up (+)</label>
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
