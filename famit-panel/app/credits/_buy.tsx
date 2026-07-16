"use client";

import { useEffect, useState, useCallback } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import {
    getCreditsPackages,
    createCreditsCheckout,
    type CreditPackages,
    type CreditPackage,
    type CreditCheckoutResult,
} from "@/lib/api";
import { cr, inr, NotEnabledPanel, HubBanner } from "./_shared";

// Razorpay's hosted checkout widget (loaded on demand; no bundle weight unless used).
function loadRazorpay(): Promise<boolean> {
    return new Promise((resolve) => {
        if (typeof window === "undefined") return resolve(false);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        if ((window as any).Razorpay) return resolve(true);
        const s = document.createElement("script");
        s.src = "https://checkout.razorpay.com/v1/checkout.js";
        s.onload = () => resolve(true);
        s.onerror = () => resolve(false);
        document.body.appendChild(s);
    });
}

export default function BuyTab() {
    const [data, setData] = useState<CreditPackages | null>(null);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [busy, setBusy] = useState<string | null>(null);
    const [provider, setProvider] = useState<string>("");
    const [custom, setCustom] = useState("");
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        getCreditsPackages()
            .then((d) => {
                if (!d) {
                    setDormant(true);
                    return;
                }
                setData(d);
                setProvider(d.default_gateway || "");
            })
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
        if (typeof window !== "undefined") {
            const t = new URLSearchParams(window.location.search).get("topup");
            if (t === "cancel") setError("Top-up cancelled — no charge was made.");
        }
    }, [load]);

    const gateways = data?.gateways || {};
    const enabled = !!data?.topup_enabled;
    const liveProviders = Object.entries(gateways).filter(([, g]) => g.configured);

    async function checkout(input: { package_id?: string; amount_inr?: number; credits?: number }, key: string) {
        setError("");
        setSuccess("");
        setBusy(key);
        try {
            const res: CreditCheckoutResult = await createCreditsCheckout({ ...input, provider });
            if (res.status === "not_configured") {
                setError(
                    "Online top-up isn’t enabled yet. Ask your administrator to add a payment gateway, or to grant credits directly."
                );
                return;
            }
            if (res.status !== "created") {
                setError(typeof res.message === "string" ? res.message : "Couldn’t start checkout. Try again.");
                return;
            }
            if (res.provider === "stripe" && res.checkout_url) {
                window.location.href = res.checkout_url;
                return;
            }
            if (res.provider === "razorpay" && res.order_id) {
                const ok = await loadRazorpay();
                if (!ok) {
                    setError("Couldn’t load the Razorpay checkout. Check your connection and retry.");
                    return;
                }
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const rzp = new (window as any).Razorpay({
                    key: res.key_id,
                    order_id: res.order_id,
                    amount: res.amount_minor,
                    currency: res.currency || "INR",
                    name: "Haptica",
                    description: `${res.credits ?? ""} credits top-up`,
                    theme: { color: "#cc785c" },
                    handler: () => {
                        setSuccess("Payment received — your balance updates within a few seconds.");
                    },
                    modal: { ondismiss: () => setBusy(null) },
                });
                rzp.open();
                return;
            }
            setError("Checkout could not be started.");
        } catch {
            setError("Something went wrong starting checkout.");
        } finally {
            setBusy(null);
        }
    }

    if (dormant) return <NotEnabledPanel />;

    return (
        <>
            <HubBanner msg={error} />
            <HubBanner msg={success} tone="success" />

            {!enabled && !loading && (
                <HubBanner
                    tone="warning"
                    msg="No payment gateway is connected yet — these packages are shown for reference. An administrator can connect Razorpay/Stripe or grant credits directly."
                />
            )}

            {/* Gateway state + provider switch */}
            <div className="card mb-3 p-5 max-lg:p-3">
                <div className="flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-overline text-t-tertiary mr-1">Pay with</span>
                        {Object.entries(gateways).map(([id, g]) => (
                            <Badge key={id} variant={g.configured ? "success" : "neutral"} dot={g.configured}>
                                {g.display_name}
                                {g.configured ? "" : " · off"}
                            </Badge>
                        ))}
                        {Object.keys(gateways).length === 0 && (
                            <span className="text-body-2 text-t-tertiary">—</span>
                        )}
                    </div>
                    {liveProviders.length > 1 && (
                        <div className="flex items-center gap-1">
                            {liveProviders.map(([id, g]) => (
                                <button
                                    key={id}
                                    onClick={() => setProvider(id)}
                                    className={`h-9 px-4 rounded-full border text-button transition-colors ${
                                        provider === id
                                            ? "border-s-stroke2 text-t-primary"
                                            : "border-transparent text-t-secondary hover:text-t-primary"
                                    }`}
                                >
                                    {g.display_name}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Packages */}
            <div className="grid grid-cols-4 gap-3 mb-3 max-2xl:grid-cols-2 max-md:grid-cols-1">
                {(loading ? PLACEHOLDER : data?.packages || []).map((p, i) => (
                    <PackageCard
                        key={p.id || i}
                        pkg={p}
                        loading={loading}
                        busy={busy === `pkg:${p.id}`}
                        disabled={!enabled || !!busy}
                        onBuy={() => checkout({ package_id: p.id }, `pkg:${p.id}`)}
                    />
                ))}
            </div>

            {/* Custom amount */}
            <Card title="Custom amount">
                <div className="px-5 pb-5 pt-2 max-lg:px-3">
                    <p className="text-body-2 text-t-tertiary mb-4">
                        Buy any amount of credits. 1 credit = ₹{data?.credit_rate_inr ?? 1}.
                        {data?.min_topup_inr ? ` Minimum ${inr(data.min_topup_inr)}.` : ""}
                    </p>
                    <div className="flex items-end gap-3 max-md:flex-col max-md:items-stretch">
                        <div className="grow">
                            <label className="block text-button text-t-secondary mb-2">Amount (₹)</label>
                            <input
                                type="number"
                                inputMode="decimal"
                                min={data?.min_topup_inr || 1}
                                value={custom}
                                onChange={(e) => setCustom(e.target.value)}
                                placeholder={`${data?.min_topup_inr || 100}`}
                                className="w-full h-12 px-4 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none bg-transparent transition-colors hover:border-s-highlight focus:border-s-focus"
                            />
                        </div>
                        <div className="text-body-2 text-t-tertiary pb-3 whitespace-nowrap max-md:pb-0">
                            {custom && Number(custom) > 0
                                ? `= ${cr(Number(custom) / (data?.credit_rate_inr || 1))}`
                                : ""}
                        </div>
                        <Button
                            isBlack
                            className="justify-center max-md:w-full"
                            disabled={
                                !enabled ||
                                !!busy ||
                                !custom ||
                                Number(custom) < (data?.min_topup_inr || 1)
                            }
                            onClick={() => checkout({ amount_inr: Number(custom) }, "custom")}
                        >
                            {busy === "custom" ? "Starting…" : "Buy credits"}
                        </Button>
                    </div>
                </div>
            </Card>
        </>
    );
}

function PackageCard({
    pkg,
    loading,
    busy,
    disabled,
    onBuy,
}: {
    pkg: CreditPackage;
    loading: boolean;
    busy: boolean;
    disabled: boolean;
    onBuy: () => void;
}) {
    return (
        <div
            className={`card !mb-0 p-5 flex flex-col gap-4 ${
                pkg.popular ? "ring-2 ring-primary-01" : ""
            }`}
        >
            <div className="flex items-center justify-between">
                <Icon name="wallet" className="size-6 fill-t-secondary" />
                {pkg.popular && <Badge variant="info">Popular</Badge>}
            </div>
            <div>
                <div className="text-h4 tabular-nums">{loading ? "—" : cr(pkg.total_credits)}</div>
                <div className="text-caption text-t-tertiary mt-0.5">
                    {pkg.bonus > 0 ? `${cr(pkg.credits)} + ${cr(pkg.bonus)} bonus` : "credits"}
                </div>
            </div>
            <div className="mt-auto">
                <div className="text-h6 tabular-nums">{loading ? "—" : inr(pkg.price_inr)}</div>
                {pkg.bonus_pct > 0 && (
                    <div className="text-caption text-primary-02">+{pkg.bonus_pct}% bonus</div>
                )}
            </div>
            <Button
                isBlack
                className="w-full justify-center"
                disabled={disabled || loading}
                onClick={onBuy}
            >
                {busy ? "Starting…" : "Buy"}
            </Button>
        </div>
    );
}

const PLACEHOLDER: CreditPackage[] = [...Array(4)].map((_, i) => ({
    id: `ph${i}`,
    credits: 0,
    bonus: 0,
    popular: false,
    price_inr: 0,
    total_credits: 0,
    bonus_pct: 0,
}));
