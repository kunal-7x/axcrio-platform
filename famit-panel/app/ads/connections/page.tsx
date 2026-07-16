"use client";

// Ad Automation › Connections & Vault (V2-W5).
//
// Everything that arms the engine, behind the app-native TRANSPARENT <Tabs>:
//   Ad Accounts    → connect Meta / Google / WhatsApp keys + OAuth (ConnectionsTab)
//   Funds & Budget → paise balance, fund intent, ledger (BudgetPanel)
//   Autopilot      → the autonomous orchestrator toggle + phase timeline
//                    (AutopilotPanel — lifted OUT of the Run wizard, where a buried
//                    toggle was the wrong home)
//   Guardrails     → hard caps, CPL breaker, approval gate (GuardrailsTab)
//
// All data wiring stays on the live /ads/* endpoints via the shared _spine hook.

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Layout from "@/components/Layout";
import Tabs from "@/components/Tabs";
import { TabsOption } from "@/types/tabs";
import { useMe, canWrite } from "@/lib/auth";
import { useAdsSpine } from "../_spine";
import { useToast, StatusRefresh } from "../_chrome";
import ConnectionsTab from "../_tabs/ConnectionsTab";
import BudgetPanel from "../_tabs/_budget-panel";
import AutopilotPanel from "../_tabs/_autopilot-panel";
import GuardrailsTab from "../_tabs/GuardrailsTab";

const TABS: (TabsOption & { key: string })[] = [
    { id: 1, name: "Ad Accounts", key: "accounts" },
    { id: 2, name: "Funds & Budget", key: "budget" },
    { id: 3, name: "Autopilot", key: "autopilot" },
    { id: 4, name: "Guardrails", key: "guardrails" },
];

export default function AdsConnectionsPage() {
    return (
        <Suspense fallback={<Layout title="Connections & Vault"><div className="py-24" /></Layout>}>
            <ConnectionsInner />
        </Suspense>
    );
}

function ConnectionsInner() {
    const router = useRouter();
    const search = useSearchParams();
    const { me } = useMe();
    const writable = canWrite(me);
    const { showToast, ToastHost } = useToast();
    const s = useAdsSpine();

    const tabKey = search.get("tab") || "accounts";
    const active = TABS.find((t) => t.key === tabKey) || TABS[0];
    const setTab = (opt: TabsOption) => {
        const t = TABS.find((x) => x.id === opt.id) || TABS[0];
        router.replace(
            t.key === "accounts" ? "/ads/connections" : `/ads/connections?tab=${t.key}`,
            { scroll: false },
        );
    };

    return (
        <Layout title="Connections & Vault">
            <ToastHost />

            <div className="flex items-center gap-3 mb-5 max-lg:flex-col max-lg:items-stretch">
                <Tabs
                    className="max-w-full overflow-x-auto scrollbar-none"
                    items={TABS}
                    value={active}
                    setValue={setTab}
                />
                <StatusRefresh
                    status={s.engineStatus}
                    onRefresh={s.refreshAll}
                    busy={s.healthLoading || s.campsLoading}
                />
            </div>

            {active.key === "accounts" && (
                <ConnectionsTab writable={writable} loading={s.loading} toast={showToast} refresh={s.refreshAll} />
            )}

            {active.key === "budget" && (
                <BudgetPanel currency={s.currency} writable={writable} toast={showToast} onFunded={s.refreshAll} />
            )}

            {active.key === "autopilot" && <AutopilotPanel writable={writable} toast={showToast} />}

            {active.key === "guardrails" && (
                <GuardrailsTab hc={s.hc} health={s.health} loading={s.loading} currency={s.currency} />
            )}
        </Layout>
    );
}
