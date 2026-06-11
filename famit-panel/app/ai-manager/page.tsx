"use client";

// AI MANAGER — the single page (was 7 sub-routes + an 8-tab pill rail).
//
// Per the design system: ONE page title via `<Layout title="AI Manager">`, plain
// tabs using the reference `Tabs` rhythm — Home / Calls / Try it / Setup. No
// eyebrow, no subtitle, no pill-rail, no Command Center. Home folds in the old
// Overview + Command History + Approvals; Calls is the inbound-call history (each
// call -> Session Detail with transcript + commands + recording); Try it is the
// test console; Setup folds in Setup + Capabilities + Team. Risk is shown as Safe /
// Needs approval / Blocked (plain language), never raw L0–L4 codes in the primary UI.
//
// All data wiring stays in _lib.ts; the tab bodies are _home/_calls/_tryit/_setup.

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Layout from "@/components/Layout";
import Tabs from "@/components/Tabs";
import { TabsOption } from "@/types/tabs";
import HomeTab from "./_home";
import CallsTab from "./_calls";
import TryItTab from "./_tryit";
import SetupTab from "./_setup";

const TABS: (TabsOption & { key: string })[] = [
    { id: 1, name: "Home", key: "home" },
    { id: 2, name: "Calls", key: "calls" },
    { id: 3, name: "Try it", key: "tryit" },
    { id: 4, name: "Setup", key: "setup" },
];

export default function AiManagerPage() {
    return (
        <Suspense fallback={null}>
            <AiManager />
        </Suspense>
    );
}

function AiManager() {
    const router = useRouter();
    const search = useSearchParams();

    const tabKey = search.get("tab") || "home";
    const seedQuery = search.get("q") || "";
    const active = TABS.find((t) => t.key === tabKey) || TABS[0];

    const setTab = (opt: TabsOption) => {
        const t = TABS.find((x) => x.id === opt.id) || TABS[0];
        router.replace(t.key === "home" ? "/ai-manager" : `/ai-manager?tab=${t.key}`, { scroll: false });
    };

    return (
        <Layout title="AI Manager">
            <Tabs className="mb-5" items={TABS} value={active} setValue={setTab} />

            {active.key === "home" && <HomeTab />}
            {active.key === "calls" && <CallsTab />}
            {active.key === "tryit" && <TryItTab seedQuery={seedQuery} />}
            {active.key === "setup" && <SetupTab />}
        </Layout>
    );
}
