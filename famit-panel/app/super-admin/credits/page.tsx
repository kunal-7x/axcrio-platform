"use client";

// SUPER ADMIN → Credits control plane. Three surfaces in one page:
//   1) Fleet KPIs — outstanding credits, MTD revenue (top-ups), MTD cost, MTD margin.
//   2) Tenant balances — per-tenant wallet + a one-click credit grant.
//   3) Service costing matrix — edit the COST BASIS + MARGIN per service; price auto-derives.
// All backed by /credits/admin/* (require_super_admin + Action-Firewall step-up on writes). Cosmetic
// gate via SuperAdminGuard; the backend choke-point is the real boundary. Dormant-safe: when the
// credits backend isn't mounted, every reader returns null and the page shows a calm empty state.

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Select from "@/components/Select";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import NoFound from "@/components/NoFound";
import {
    getCreditsAdminOverview,
    getCreditsAdminPricing,
    saveCreditsPricing,
    grantCredits,
    type CreditAdminOverview,
    type CreditAdminTenant,
    type CreditPricingService,
} from "@/lib/api";
import {
    AdminHeader,
    SuperAdminGuard,
    HeroCard,
    ErrorBanner,
    ghostBtnCls,
    ToastView,
    type Toast,
} from "../_shared";
import { cr, inr } from "../../credits/_shared";

export default function SuperAdminCreditsPage() {
    return (
        <SuperAdminGuard>
            <Layout title="Credits">
                <AdminCredits />
            </Layout>
        </SuperAdminGuard>
    );
}

function AdminCredits() {
    const [ov, setOv] = useState<CreditAdminOverview | null>(null);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getCreditsAdminOverview()
            .then((d) => {
                if (!d) {
                    setDormant(true);
                    return;
                }
                setDormant(false);
                setOv(d);
                if (d.error) setError(d.error);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load credits overview"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    return (
        <>
            <AdminHeader
                actions={
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        Refresh
                    </button>
                }
            />

            <ToastView toast={toast} onClose={() => setToast(null)} />
            <ErrorBanner msg={error} />

            {dormant ? (
                <div className="card p-8 text-center">
                    <div className="inline-flex items-center justify-center size-16 mb-5 rounded-full bg-b-surface1">
                        <Icon name="wallet" className="size-8 fill-t-secondary" />
                    </div>
                    <h3 className="mb-2 text-h6 text-t-primary">Credits backend not mounted</h3>
                    <p className="mx-auto max-w-120 text-body-2 text-t-secondary">
                        Deploy the backend with <code className="px-1.5 py-0.5 rounded bg-b-surface1 text-caption">FEATURE_CREDITS=1</code> to
                        manage wallets, grants and the costing matrix here.
                    </p>
                </div>
            ) : (
                <>
                    {/* Fleet KPIs */}
                    <div className="grid grid-cols-4 gap-3 mb-3 max-2xl:grid-cols-2 max-md:grid-cols-1">
                        <HeroCard
                            label="Outstanding credits"
                            glyph="wallet"
                            accent="var(--primary-01)"
                            loading={loading}
                            value={cr(ov?.outstanding_credits)}
                            foot={inr(ov?.outstanding_inr)}
                        />
                        <HeroCard
                            label="Revenue (MTD)"
                            glyph="arrow-up-right"
                            glyphClass="fill-primary-02"
                            accent="var(--chart-green)"
                            loading={loading}
                            value={inr(ov?.mtd_revenue_inr)}
                            foot="top-ups this month"
                        />
                        <HeroCard
                            label="Cost (MTD)"
                            glyph="chart"
                            accent="var(--primary-04)"
                            loading={loading}
                            value={inr(ov?.mtd_cost_inr)}
                            foot="metered spend this month"
                        />
                        <HeroCard
                            label="Margin (MTD)"
                            glyph="income"
                            glyphClass={ov && ov.mtd_margin_inr >= 0 ? "fill-primary-02" : "fill-primary-03"}
                            accent={ov && ov.mtd_margin_inr >= 0 ? "var(--chart-green)" : "var(--primary-03)"}
                            loading={loading}
                            value={inr(ov?.mtd_margin_inr)}
                            foot="revenue − cost"
                        />
                    </div>

                    <div className="flex max-xl:block">
                        <div className="col-left">
                            <TenantBalances
                                ov={ov}
                                loading={loading}
                                onGranted={(name, credits) => {
                                    showToast(`Granted ${cr(credits)} to ${name}`);
                                    load();
                                }}
                                onError={(m) => showToast(m, "error")}
                            />
                        </div>
                        <div className="col-right">
                            <GrantPanel
                                tenants={ov?.tenants || []}
                                rate={ov?.credit_rate_inr || 1}
                                onGranted={(name, credits) => {
                                    showToast(`Granted ${cr(credits)} to ${name}`);
                                    load();
                                }}
                                onError={(m) => showToast(m, "error")}
                            />
                        </div>
                    </div>

                    <CostingMatrix onSaved={() => showToast("Costing matrix saved")} onError={(m) => showToast(m, "error")} />
                </>
            )}
        </>
    );
}

const TENANT_HEAD = ["Client", "Plan", "Balance", "MTD spend", ""];

function TenantBalances({
    ov,
    loading,
    onGranted,
    onError,
}: {
    ov: CreditAdminOverview | null;
    loading: boolean;
    onGranted: (name: string, credits: number) => void;
    onError: (m: string) => void;
}) {
    const [busy, setBusy] = useState<string | null>(null);
    const tenants = ov?.tenants || [];

    async function quickGrant(t: CreditAdminTenant) {
        const raw = window.prompt(`Grant credits to ${t.name} (1 credit = ₹${ov?.credit_rate_inr ?? 1}).\nEnter a credit amount (negative to deduct):`, "1000");
        if (raw == null) return;
        const credits = Number(raw);
        if (!credits || Number.isNaN(credits)) return;
        setBusy(t.tenant_id);
        const res = await grantCredits({ tenant_id: t.tenant_id, credits, note: "admin grant" });
        setBusy(null);
        if (res.ok) onGranted(t.name, credits);
        else onError("Grant failed — a PIN step-up may be required (Action Firewall).");
    }

    return (
        <Card title="Client balances">
            {!loading && tenants.length === 0 ? (
                <NoFound title="No client wallets yet" />
            ) : (
                <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                    <Table
                        cellsThead={TENANT_HEAD.map((h, i) => (
                            <th key={i} className={`!h-12.5 ${i === 2 || i === 3 ? "text-right" : ""}`}>
                                {h}
                            </th>
                        ))}
                        isMobileVisibleTHead
                    >
                        {(loading ? PLACEHOLDER : tenants).map((t, idx) => (
                            <TableRow key={t.tenant_id || idx}>
                                <td>
                                    <div className="text-t-primary">{t.name || "—"}</div>
                                    {t.email && (
                                        <div className="text-caption text-t-tertiary truncate max-md:hidden">
                                            {t.email}
                                        </div>
                                    )}
                                </td>
                                <td className="text-t-secondary capitalize">{t.plan || "—"}</td>
                                <td className="text-right tabular-nums text-sub-title-2">
                                    {t.tenant_id ? (
                                        <span className={t.low_balance ? "text-primary-03" : ""}>
                                            {cr(t.balance_credits)}
                                        </span>
                                    ) : (
                                        "—"
                                    )}
                                    {t.low_balance && t.tenant_id && (
                                        <Badge variant="warning" className="ml-2">
                                            Low
                                        </Badge>
                                    )}
                                </td>
                                <td className="text-right tabular-nums text-t-secondary">
                                    {t.tenant_id ? inr(t.mtd_spend_inr) : "—"}
                                </td>
                                <td className="text-right">
                                    {t.tenant_id && (
                                        <button
                                            onClick={() => quickGrant(t)}
                                            disabled={busy === t.tenant_id}
                                            className={ghostBtnCls + " !h-9 !px-3"}
                                        >
                                            {busy === t.tenant_id ? "…" : "Grant"}
                                        </button>
                                    )}
                                </td>
                            </TableRow>
                        ))}
                    </Table>
                </div>
            )}
        </Card>
    );
}

function GrantPanel({
    tenants,
    rate,
    onGranted,
    onError,
}: {
    tenants: CreditAdminTenant[];
    rate: number;
    onGranted: (name: string, credits: number) => void;
    onError: (m: string) => void;
}) {
    const [idx, setIdx] = useState(0);
    const [credits, setCredits] = useState("");
    const [note, setNote] = useState("");
    const [saving, setSaving] = useState(false);

    const options = tenants.map((t, i) => ({ id: i, name: `${t.name} (${t.tenant_id})` }));
    const labelCls = "block text-button text-t-secondary mb-2";
    const inputCls =
        "w-full h-12 px-4 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none bg-transparent transition-colors hover:border-s-highlight focus:border-s-focus";

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        const t = tenants[idx];
        const c = Number(credits);
        if (!t || !c || Number.isNaN(c)) return;
        setSaving(true);
        const res = await grantCredits({ tenant_id: t.tenant_id, credits: c, note });
        setSaving(false);
        if (res.ok) {
            onGranted(t.name, c);
            setCredits("");
            setNote("");
        } else {
            onError("Grant failed — a PIN step-up may be required (Action Firewall).");
        }
    }

    return (
        <Card title="Grant credits">
            <form onSubmit={submit} className="px-5 pb-5 pt-2 space-y-4 max-lg:px-3">
                <div>
                    <label className={labelCls}>Client</label>
                    <Select
                        className="w-full"
                        value={options[idx] || null}
                        onChange={(o) => setIdx(o.id)}
                        options={options}
                        placeholder="Select client"
                    />
                </div>
                <div>
                    <label className={labelCls}>Credits (negative to deduct)</label>
                    <input
                        type="number"
                        value={credits}
                        onChange={(e) => setCredits(e.target.value)}
                        placeholder="1000"
                        className={inputCls}
                    />
                    {credits && Number(credits) !== 0 && (
                        <div className="mt-1.5 text-caption text-t-tertiary">
                            = {inr(Number(credits) * rate)}
                        </div>
                    )}
                </div>
                <div>
                    <label className={labelCls}>Note (optional)</label>
                    <input
                        type="text"
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="reason / reference"
                        className={inputCls}
                    />
                </div>
                <Button isBlack className="w-full justify-center" disabled={saving || !credits}>
                    {saving ? "Granting…" : "Grant credits"}
                </Button>
                <p className="text-caption text-t-tertiary">
                    Spend-sensitive — your Action-Firewall PIN may be required.
                </p>
            </form>
        </Card>
    );
}

type EditRow = CreditPricingService & { _basis: string; _markup: string };
const MATRIX_HEAD = ["Service", "Basis ₹", "Markup %", "Price", "Margin", "Tracked"];

function CostingMatrix({ onSaved, onError }: { onSaved: () => void; onError: (m: string) => void }) {
    const [rows, setRows] = useState<EditRow[]>([]);
    const [rate, setRate] = useState(1);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [dirty, setDirty] = useState(false);

    const load = useCallback(() => {
        setLoading(true);
        getCreditsAdminPricing()
            .then((m) => {
                if (!m) return;
                setRate(m.credit_rate_inr || 1);
                setRows(m.services.map((s) => ({ ...s, _basis: String(s.basis_inr), _markup: String(s.markup_pct) })));
            })
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    function edit(key: string, field: "_basis" | "_markup" | "metered", value: string | boolean) {
        setDirty(true);
        setRows((prev) =>
            prev.map((r) => (r.key === key ? { ...r, [field]: value } : r))
        );
    }

    function previewPrice(r: EditRow): { credits: number; inr: number; margin: number } {
        const basis = Number(r._basis) || 0;
        const markup = Number(r._markup) || 0;
        const price = basis * (1 + markup / 100);
        return { credits: price / rate, inr: price, margin: price - basis };
    }

    async function save() {
        setSaving(true);
        const overrides: Record<string, Partial<CreditPricingService>> = {};
        for (const r of rows) {
            overrides[r.key] = {
                basis_inr: Number(r._basis) || 0,
                markup_pct: Number(r._markup) || 0,
                metered: r.metered,
            };
        }
        const res = await saveCreditsPricing(overrides);
        setSaving(false);
        if ("ok" in res && res.ok === false) {
            onError("Save failed — a PIN step-up may be required (Action Firewall).");
            return;
        }
        setDirty(false);
        onSaved();
        load();
    }

    return (
        <Card
            title="Service costing matrix"
            headContent={
                <div className="ml-auto flex items-center gap-3">
                    <span className="text-caption text-t-tertiary max-md:hidden">1 credit = ₹{rate}</span>
                    <Button isBlack className="!h-9 !px-4" disabled={saving || !dirty} onClick={save}>
                        {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
                    </Button>
                </div>
            }
        >
            <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0 overflow-x-auto">
                <Table
                    cellsThead={MATRIX_HEAD.map((h, i) => (
                        <th key={i} className={`!h-12.5 ${i >= 1 && i <= 4 ? "text-right" : ""} last:text-right`}>
                            {h}
                        </th>
                    ))}
                    isMobileVisibleTHead
                >
                    {(loading ? PLACEHOLDER_ROWS : rows).map((r, idx) => {
                        const p = "key" in r && r.key ? previewPrice(r as EditRow) : { credits: 0, inr: 0, margin: 0 };
                        return (
                            <TableRow key={(r as EditRow).key || idx}>
                                <td className="min-w-44">
                                    <div className="text-t-primary">{(r as EditRow).label || "—"}</div>
                                    <div className="text-caption text-t-tertiary">
                                        {(r as EditRow).category}
                                        {(r as EditRow).unit ? ` · per ${(r as EditRow).unit}` : ""}
                                    </div>
                                </td>
                                <td className="text-right">
                                    {(r as EditRow).key ? (
                                        <input
                                            type="number"
                                            step="0.01"
                                            value={(r as EditRow)._basis}
                                            onChange={(e) => edit((r as EditRow).key, "_basis", e.target.value)}
                                            className="w-24 h-9 px-3 text-right border border-s-stroke2 rounded-xl text-body-2 bg-transparent tabular-nums outline-none focus:border-s-focus"
                                        />
                                    ) : (
                                        "—"
                                    )}
                                </td>
                                <td className="text-right">
                                    {(r as EditRow).key ? (
                                        <input
                                            type="number"
                                            step="1"
                                            value={(r as EditRow)._markup}
                                            onChange={(e) => edit((r as EditRow).key, "_markup", e.target.value)}
                                            className="w-20 h-9 px-3 text-right border border-s-stroke2 rounded-xl text-body-2 bg-transparent tabular-nums outline-none focus:border-s-focus"
                                        />
                                    ) : (
                                        "—"
                                    )}
                                </td>
                                <td className="text-right tabular-nums">
                                    {(r as EditRow).key ? (
                                        <div>
                                            <div className="text-sub-title-2">{cr(p.credits)}</div>
                                            <div className="text-caption text-t-tertiary">{inr(p.inr)}</div>
                                        </div>
                                    ) : (
                                        "—"
                                    )}
                                </td>
                                <td className="text-right tabular-nums text-t-secondary">
                                    {(r as EditRow).key ? inr(p.margin) : "—"}
                                </td>
                                <td className="text-right">
                                    {(r as EditRow).key && (
                                        <button
                                            type="button"
                                            onClick={() => edit((r as EditRow).key, "metered", !(r as EditRow).metered)}
                                            title="Toggle live metering"
                                        >
                                            <Badge variant={(r as EditRow).metered ? "success" : "neutral"} dot={(r as EditRow).metered}>
                                                {(r as EditRow).metered ? "Tracked" : "Off"}
                                            </Badge>
                                        </button>
                                    )}
                                </td>
                            </TableRow>
                        );
                    })}
                </Table>
            </div>
        </Card>
    );
}

const PLACEHOLDER: CreditAdminTenant[] = [...Array(5)].map(() => ({
    tenant_id: "",
    name: "",
    email: "",
    plan: "",
    balance_inr: 0,
    balance_credits: 0,
    mtd_spend_inr: 0,
    low_balance: false,
}));

const PLACEHOLDER_ROWS: EditRow[] = [...Array(6)].map(() => ({
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
    _basis: "",
    _markup: "",
}));
