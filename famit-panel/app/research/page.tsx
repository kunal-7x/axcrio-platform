"use client";

// FAMIT RESEARCH — the premium "instrumented conversation science" lab.
//
// Every other voice-AI dashboard shows you WHAT happened (connected, lead hot, duration). Famit
// Research measures the DYNAMICS of HOW it happened: a calibrated, per-speaker-baselined Arousal /
// Friction latent state WITH real uncertainty bands, prosody time-series, regime flags, and a
// closed-loop view of which trajectory shapes actually move outcomes.
//
// Design-system native: ONE Layout title, plain Tabs (Overview / Call Detail / Outcomes Lab), the
// shared Card / KpiCard / Recharts chrome. Tabs + selected-call live in the URL (?tab=, ?call=) so
// the page is shareable and back-button friendly. All data wiring is in _lib.ts; charts in _charts.tsx.

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Layout from "@/components/Layout";
import Tabs from "@/components/Tabs";
import { TabsOption } from "@/types/tabs";
import OverviewTab from "./_overview";
import CallDetailTab from "./_call";
import OutcomesTab from "./_outcomes";

const TABS: (TabsOption & { key: string })[] = [
    { id: 1, name: "Overview", key: "overview" },
    { id: 2, name: "Call Detail", key: "call" },
    { id: 3, name: "Outcomes Lab", key: "outcomes" },
];

export default function ResearchPage() {
    return (
        <Suspense fallback={null}>
            <Research />
        </Suspense>
    );
}

function Research() {
    const router = useRouter();
    const search = useSearchParams();

    const tabKey = search.get("tab") || "overview";
    const callId = search.get("call") || "";
    const minutes = Number(search.get("range") || 1440);
    const active = TABS.find((t) => t.key === tabKey) || TABS[0];

    const setTab = (opt: TabsOption) => {
        const t = TABS.find((x) => x.id === opt.id) || TABS[0];
        const q = new URLSearchParams();
        if (t.key !== "overview") q.set("tab", t.key);
        if (t.key === "call" && callId) q.set("call", callId);
        const qs = q.toString();
        router.replace(qs ? `/research?${qs}` : "/research", { scroll: false });
    };

    const openCall = (id: string) => {
        router.replace(`/research?tab=call&call=${encodeURIComponent(id)}`, { scroll: false });
    };

    return (
        <Layout title="Famit Research">
            <Tabs className="mb-5" items={TABS} value={active} setValue={setTab} />

            {active.key === "overview" && <OverviewTab minutes={minutes} onOpenCall={openCall} />}
            {active.key === "call" && <CallDetailTab callId={callId} minutes={minutes} onOpenCall={openCall} />}
            {active.key === "outcomes" && <OutcomesTab minutes={minutes} />}
        </Layout>
    );
}
