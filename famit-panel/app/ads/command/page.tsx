"use client";

// Ad Automation › Command & Analytics (V2-W5).
//
// The cockpit page. Opens on the live KPI hero (Overview) and folds the old
// Command / Analytics / Decisions / Leads tabs into ONE page driven by the
// app-native TRANSPARENT <Tabs> (components/Tabs — flat on the surface, NO pill
// container). The 8-tab custom pill rail from the old monolith is gone.
//
//   Overview              → the P0 cockpit: alert strip → 6-tile KPI hero →
//                           gradient trend → per-platform breakdown (CommandTab)
//   Performance           → per-ad / per-platform analytics (AnalyticsTab)
//   Creative Intelligence → Hook/Hold rate + color-bar ranking + the MOAT metric
//                           "cost per qualified call by creative" (CreativeIntelTab)
//   Decisions             → the AI decision feed with per-entry rollback
//   Leads                 → ad-lead table + consent + import
//
// All data wiring stays on the live /ads/* endpoints via the shared _spine hook.

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Layout from "@/components/Layout";
import Tabs from "@/components/Tabs";
import { TabsOption } from "@/types/tabs";
import { useAdsSpine } from "../_spine";
import { useToast, StatusRefresh } from "../_chrome";
import { useMe, canWrite } from "@/lib/auth";
import CommandTab from "../_tabs/CommandTab";
import AnalyticsTab from "../_tabs/AnalyticsTab";
import DecisionsTab from "../_tabs/DecisionsTab";
import LeadsTab from "../_tabs/LeadsTab";
import CreativeIntelTab from "../_tabs/CreativeIntelTab";

const TABS: (TabsOption & { key: string })[] = [
    { id: 1, name: "Overview", key: "overview" },
    { id: 2, name: "Performance", key: "performance" },
    { id: 3, name: "Creative Intelligence", key: "creative-intel" },
    { id: 4, name: "Decisions", key: "decisions" },
    { id: 5, name: "Leads", key: "leads" },
];

export default function AdsCommandPage() {
    return (
        <Suspense fallback={<Layout title="Command & Analytics"><div className="py-24" /></Layout>}>
            <CommandInner />
        </Suspense>
    );
}

function CommandInner() {
    const router = useRouter();
    const search = useSearchParams();
    const { me } = useMe();
    const writable = canWrite(me);
    const { showToast, ToastHost } = useToast();

    const s = useAdsSpine();

    const tabKey = search.get("tab") || "overview";
    const active = TABS.find((t) => t.key === tabKey) || TABS[0];
    const setTab = (opt: TabsOption) => {
        const t = TABS.find((x) => x.id === opt.id) || TABS[0];
        router.replace(t.key === "overview" ? "/ads/command" : `/ads/command?tab=${t.key}`, {
            scroll: false,
        });
    };

    return (
        <Layout title="Command & Analytics">
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

            {active.key === "overview" && (
                <CommandTab
                    hc={s.hc}
                    health={s.health}
                    loading={s.loading}
                    moduleDormant={s.moduleDormant}
                    activeCount={s.activeCount}
                    pendingCount={s.pendingCount}
                    totalCount={s.totalCount}
                    spendTodayMinor={s.spendTodayMinor}
                    currency={s.currency}
                    writable={writable}
                    toast={showToast}
                />
            )}

            {active.key === "performance" && (
                <AnalyticsTab writable={writable} loading={s.loading} toast={showToast} refresh={s.refreshAll} />
            )}

            {active.key === "creative-intel" && (
                <CreativeIntelTab writable={writable} loading={s.loading} toast={showToast} refresh={s.refreshAll} currency={s.currency} />
            )}

            {active.key === "decisions" && (
                <DecisionsTab
                    writable={writable}
                    dormant={s.moduleDormant}
                    activeCount={s.activeCount}
                    currency={s.currency}
                    hc={s.hc}
                    toast={showToast}
                />
            )}

            {active.key === "leads" && (
                <LeadsTab writable={writable} loading={s.loading} toast={showToast} refresh={s.refreshAll} />
            )}
        </Layout>
    );
}
