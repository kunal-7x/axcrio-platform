"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import NoFound from "@/components/NoFound";
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
import { outcomeVariant, ErrorBanner, BillingTabs } from "../_shared";

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

const ledgerHead = ["When", "Phone", "Outcome", "Duration", "Cost"];

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
        <Layout title="Plan">
            <BillingTabs />

            {toast && (
                <div
                    className={`mb-4 p-3.5 rounded-3xl text-body-2 flex items-center justify-between gap-3 border ${
                        toast.type === "success"
                            ? "bg-primary-02/8 text-primary-02 border-primary-02/20"
                            : "bg-primary-03/8 text-primary-03 border-primary-03/20"
                    }`}
                >
                    <span className="flex items-center gap-2">
                        <Icon
                            name={toast.type === "success" ? "check-circle" : "info"}
                            className="size-4 fill-current shrink-0"
                        />
                        {toast.msg}
                    </span>
                    <button
                        onClick={() => setToast(null)}
                        className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none"
                    >
                        ×
                    </button>
                </div>
            )}

            <ErrorBanner msg={loadError} />

            {lowBalance && (
                <div className="mb-4 p-3.5 rounded-3xl bg-primary-05/8 text-primary-05 text-body-2 border border-primary-05/20 flex items-center gap-2">
                    <Icon name="info" className="size-4 fill-current shrink-0" />
                    Insufficient balance — top up to continue placing calls. Calls are blocked while
                    your prepaid balance is at or below zero.
                </div>
            )}

            <div className="flex max-lg:block">
                <div className="col-left">
                    {/* Plan summary — ported from UpgradeToProPage Pricing card */}
                    <Card title="Your plan">
                        <div className="p-5 pt-3 max-lg:p-3">
                            <div className="border border-s-stroke2 rounded-3xl shadow-depth p-6 max-lg:p-4">
                                <div className="flex items-center justify-between gap-3 mb-5">
                                    <div className="flex items-center gap-3">
                                        <div className="text-h4 capitalize">
                                            {billing?.plan ?? "—"}
                                        </div>
                                        {billing?.plan && (
                                            <Badge
                                                variant={
                                                    billing.plan === "prepaid" ? "info" : "neutral"
                                                }
                                            >
                                                {billing.plan === "prepaid"
                                                    ? "Prepaid"
                                                    : "Postpaid"}
                                            </Badge>
                                        )}
                                    </div>
                                    <div className="text-right">
                                        <div
                                            className={`text-h4 tabular-nums ${
                                                lowBalance ? "text-primary-03" : ""
                                            }`}
                                        >
                                            {money(billing?.balance, currency)}
                                        </div>
                                        <div className="text-caption text-t-tertiary">
                                            {billing?.plan === "prepaid"
                                                ? "Prepaid balance"
                                                : "Billed in arrears"}
                                        </div>
                                    </div>
                                </div>
                                <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
                                    <Fact
                                        label="Rate / min"
                                        value={money(billing?.rate_per_min, currency)}
                                    />
                                    <Fact
                                        label="Rate / call"
                                        value={money(billing?.rate_per_call, currency)}
                                    />
                                    <Fact
                                        label="Included min"
                                        value={`${billing?.included_minutes ?? 0}`}
                                    />
                                    <Fact
                                        label="This month"
                                        value={`${billing?.month_to_date?.minutes ?? 0} min · ${
                                            billing?.month_to_date?.calls ?? 0
                                        } calls`}
                                    />
                                    <Fact
                                        label="This month cost"
                                        value={money(billing?.month_to_date?.cost, currency)}
                                    />
                                </div>
                            </div>
                        </div>
                    </Card>

                    {/* Ledger — ported from EarningPage Transactions */}
                    <Card
                        title="Recent charges"
                        headContent={
                            <span className="ml-3 text-caption text-t-tertiary max-md:hidden">
                                {money(billing?.rate_per_min, currency)}/min +{" "}
                                {money(billing?.rate_per_call, currency)}/call
                            </span>
                        }
                    >
                        {!loading && ledger.length === 0 ? (
                            <NoFound title="No charges yet" />
                        ) : (
                            <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                                <Table
                                    cellsThead={ledgerHead.map((head) => (
                                        <th
                                            className="!h-12.5 last:text-right nth-4:text-right max-md:nth-2:hidden"
                                            key={head}
                                        >
                                            {head}
                                        </th>
                                    ))}
                                    isMobileVisibleTHead
                                >
                                    {(loading ? PLACEHOLDER : ledger).map((e, idx) => (
                                        <TableRow key={e.id || idx}>
                                            <td className="text-t-secondary whitespace-nowrap">
                                                {e.at ? fmt(e.at) : "—"}
                                            </td>
                                            <td className="text-t-secondary tabular-nums max-md:hidden">
                                                {e.phone || "—"}
                                            </td>
                                            <td>
                                                {e.outcome ? (
                                                    <Badge variant={outcomeVariant(e.outcome)}>
                                                        {e.outcome.replace(/_/g, " ")}
                                                    </Badge>
                                                ) : (
                                                    <span className="text-t-tertiary">—</span>
                                                )}
                                            </td>
                                            <td className="text-right text-t-secondary tabular-nums">
                                                {e.duration_s != null && e.id ? `${e.duration_s}s` : "—"}
                                            </td>
                                            <td className="text-right text-sub-title-2 tabular-nums">
                                                {e.id ? money(e.cost, e.currency || currency) : "—"}
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        )}
                    </Card>
                </div>

                {admin && (
                    <div className="col-right">
                        <AdminBillingPanel
                            onSaved={(b) => {
                                setBillingState(b);
                                showToast("Billing updated", "success");
                            }}
                            onError={(m) => showToast(m, "error")}
                        />
                    </div>
                )}
            </div>
        </Layout>
    );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div>
            <div className="text-caption text-t-tertiary mb-1">{label}</div>
            <div className="text-sub-title-2 tabular-nums">{value}</div>
        </div>
    );
}

function AdminBillingPanel({
    onSaved,
    onError,
}: {
    onSaved: (b: Billing) => void;
    onError: (m: string) => void;
}) {
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

    const labelCls = "block text-button text-t-secondary mb-2";
    const inputCls =
        "w-full h-12 px-4 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none bg-transparent transition-colors hover:border-s-highlight focus:border-s-focus";

    return (
        <Card title="Set plan & rates">
            <form onSubmit={handleSave} className="px-5 pb-5 pt-2 space-y-4 max-lg:px-3">
                <div>
                    <label className={labelCls}>Tenant</label>
                    <select
                        value={tenantId}
                        onChange={(e) => setTenantId(e.target.value)}
                        className={inputCls}
                    >
                        {tenants.map((t) => (
                            <option key={t.tenant_id} value={t.tenant_id}>
                                {t.name} ({t.tenant_id})
                            </option>
                        ))}
                    </select>
                </div>
                <div>
                    <label className={labelCls}>Plan</label>
                    <select
                        value={plan}
                        onChange={(e) => setPlan(e.target.value as "prepaid" | "postpaid")}
                        className={inputCls}
                    >
                        <option value="postpaid">postpaid</option>
                        <option value="prepaid">prepaid</option>
                    </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className={labelCls}>Rate / min</label>
                        <input
                            type="number"
                            step="0.01"
                            value={ratePerMin}
                            onChange={(e) => setRatePerMin(e.target.value)}
                            placeholder="0.00"
                            className={inputCls}
                        />
                    </div>
                    <div>
                        <label className={labelCls}>Rate / call</label>
                        <input
                            type="number"
                            step="0.01"
                            value={ratePerCall}
                            onChange={(e) => setRatePerCall(e.target.value)}
                            placeholder="0.00"
                            className={inputCls}
                        />
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className={labelCls}>Currency</label>
                        <input
                            type="text"
                            value={currency}
                            onChange={(e) => setCurrency(e.target.value)}
                            placeholder="INR"
                            className={inputCls}
                        />
                    </div>
                    <div>
                        <label className={labelCls}>Included mins</label>
                        <input
                            type="number"
                            value={includedMinutes}
                            onChange={(e) => setIncludedMinutes(e.target.value)}
                            placeholder="0"
                            className={inputCls}
                        />
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className={labelCls}>Set balance</label>
                        <input
                            type="number"
                            step="0.01"
                            value={balance}
                            onChange={(e) => setBalance(e.target.value)}
                            placeholder="absolute"
                            className={inputCls}
                        />
                    </div>
                    <div>
                        <label className={labelCls}>Top up (+)</label>
                        <input
                            type="number"
                            step="0.01"
                            value={topup}
                            onChange={(e) => setTopup(e.target.value)}
                            placeholder="adds"
                            className={inputCls}
                        />
                    </div>
                </div>
                <Button isBlack className="w-full justify-center" disabled={saving}>
                    {saving ? "Saving…" : "Save billing"}
                </Button>
            </form>
        </Card>
    );
}

const PLACEHOLDER: LedgerEntry[] = [...Array(6)].map(() => ({
    id: "",
    call_id: "",
    phone: "",
    campaign_id: "",
    duration_s: 0,
    cost: 0,
    currency: "",
    outcome: "",
    at: "",
}));
