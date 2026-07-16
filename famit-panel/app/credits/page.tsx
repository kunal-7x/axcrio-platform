"use client";

// CREDITS hub — the renamed "Money" home. One <Layout title="Credits"> with the unified hub strip
// and four query-param panels (Wallet / Buy Credits / Usage / Pricing). The billing tabs in the same
// strip route to their own pages. Suspense wraps the body because the panels read ?tab via
// useSearchParams.

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Layout from "@/components/Layout";
import { CreditsHubTabs } from "./_shared";
import WalletTab from "./_wallet";
import BuyTab from "./_buy";
import UsageTab from "./_usage";
import PricingTab from "./_pricing";

export default function CreditsPage() {
    return (
        <Suspense fallback={null}>
            <CreditsHub />
        </Suspense>
    );
}

function CreditsHub() {
    const search = useSearchParams();
    const tab = search.get("tab") || "wallet";
    return (
        <Layout title="Credits">
            <CreditsHubTabs />
            {tab === "wallet" && <WalletTab />}
            {tab === "buy" && <BuyTab />}
            {tab === "usage" && <UsageTab />}
            {tab === "pricing" && <PricingTab />}
        </Layout>
    );
}
