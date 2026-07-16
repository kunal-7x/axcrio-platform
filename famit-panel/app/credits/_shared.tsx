"use client";

// Shared primitives for the CREDITS hub. The hub is one tabbed surface that leads with the
// credit wallet (Wallet / Buy Credits / Usage / Pricing) and FOLDS IN the existing billing tabs
// (Overview / Vendors / Spending / Plan / Audit / Payments) via ONE strip — so every page in the
// money area reads as a single hub. The strip is the SINGLE SOURCE OF TRUTH for the tab list;
// billing/_shared.tsx renders the same strip (active state from pathname there).
//
// IMPORTANT: this module must NOT import from ../billing/_shared (billing/_shared imports the strip
// FROM here — importing back would create a cycle). Page files may import both freely.

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import Icon from "@/components/Icon";

// One credit = ₹credit_rate (server-driven; 1 by default). Formatting helpers used across the hub.
export function cr(n: number | null | undefined): string {
    if (n == null || Number.isNaN(n)) return "—";
    const frac = Math.abs(n) % 1 === 0 ? 0 : 2;
    return `${n.toLocaleString("en-IN", { maximumFractionDigits: frac })} cr`;
}

export function inr(n: number | null | undefined): string {
    if (n == null || Number.isNaN(n)) return "—";
    return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function fmtDate(d: string | undefined | null): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

// The unified hub tab list. Credit tabs are query-param panels of /credits; billing tabs are real
// routes that still resolve standalone (no 404s).
export const HUB_TABS: { label: string; href: string }[] = [
    { label: "Wallet", href: "/credits" },
    { label: "Buy Credits", href: "/credits?tab=buy" },
    { label: "Usage", href: "/credits?tab=usage" },
    { label: "Pricing", href: "/credits?tab=pricing" },
    { label: "Overview", href: "/billing/overview" },
    { label: "Vendors", href: "/billing/vendors" },
    { label: "Spending", href: "/billing/explorer" },
    { label: "Plan", href: "/billing/plan" },
    { label: "Audit", href: "/billing/audit" },
    { label: "Payments", href: "/payments" },
];

// Presentational strip. `activeTab` is the resolved /credits panel key (wallet|buy|usage|pricing)
// when rendered INSIDE the credits page; null elsewhere (billing pages), where only the route-based
// tabs light up. usePathname is SSR-safe everywhere; useSearchParams is NOT used here on purpose so
// billing pages don't need a Suspense boundary.
export function HubTabsView({ activeTab }: { activeTab: string | null }) {
    const pathname = usePathname();
    return (
        <div className="flex flex-wrap gap-1 mb-5 max-md:mb-4">
            {HUB_TABS.map((t) => {
                const [base, q] = t.href.split("?");
                const hrefTab = q ? new URLSearchParams(q).get("tab") : null;
                let active: boolean;
                if (base === "/credits") {
                    active = activeTab != null && pathname === "/credits" && (hrefTab || "wallet") === activeTab;
                } else {
                    active =
                        pathname === base ||
                        (base.includes("/vendors") && pathname.startsWith("/billing/vendors"));
                }
                return (
                    <Link
                        key={t.href}
                        href={t.href}
                        className={`flex justify-center items-center h-12 px-5.5 rounded-full border text-button transition-colors hover:text-t-primary ${
                            active
                                ? "border-s-stroke2 text-t-primary"
                                : "border-transparent text-t-secondary"
                        }`}
                    >
                        {t.label}
                    </Link>
                );
            })}
        </div>
    );
}

// Used inside the /credits page (which IS wrapped in <Suspense>), so reading the active panel via
// useSearchParams is safe here.
export function CreditsHubTabs() {
    const search = useSearchParams();
    const tab = search.get("tab") || "wallet";
    return <HubTabsView activeTab={tab} />;
}

// Calm dormant panel shown when the credits backend isn't mounted yet (FEATURE_CREDITS off / older
// box -> every reader returned null). Never an error wall.
export function NotEnabledPanel() {
    return (
        <div className="card p-8 text-center max-md:p-6">
            <div className="inline-flex items-center justify-center size-16 mb-5 rounded-full bg-b-surface1">
                <Icon name="wallet" className="size-8 fill-t-secondary" />
            </div>
            <h3 className="mb-2 text-h6 text-t-primary">Credits aren’t switched on yet</h3>
            <p className="mx-auto mb-1 max-w-120 text-body-2 text-t-secondary">
                The credit wallet runs once the backend is deployed with{" "}
                <code className="px-1.5 py-0.5 rounded bg-b-surface1 text-caption">FEATURE_CREDITS=1</code>.
                Until then your existing billing, vendor spend and payment-collection tabs keep working
                from the strip above.
            </p>
        </div>
    );
}

// One inline error/info banner, token-based (mirrors billing's ErrorBanner so the hub is uniform).
export function HubBanner({
    msg,
    tone = "danger",
}: {
    msg: string;
    tone?: "danger" | "warning" | "success";
}) {
    if (!msg) return null;
    const cls =
        tone === "success"
            ? "bg-primary-02/8 border-primary-02/20 text-primary-02"
            : tone === "warning"
              ? "bg-primary-05/8 border-primary-05/20 text-primary-05"
              : "bg-primary-03/8 border-primary-03/20 text-primary-03";
    return (
        <div className={`mb-4 flex items-center gap-2 p-3.5 rounded-3xl border text-body-2 ${cls}`}>
            <Icon name="info" className="size-4 fill-current shrink-0" />
            <span>{msg}</span>
        </div>
    );
}
