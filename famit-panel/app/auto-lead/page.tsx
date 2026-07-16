"use client";

import { useState } from "react";
import Layout from "@/components/Layout";
import Tabs from "@/components/Tabs";
import Overview from "./_components/Overview";
import Sources from "./_components/Sources";
import Feed from "./_components/Feed";

const TABS = [
    { id: 1, name: "Overview", key: "overview" as const },
    { id: 2, name: "Sources", key: "sources" as const },
    { id: 3, name: "Live Feed", key: "feed" as const },
];

export default function AutoLeadPage() {
    const [tab, setTab] = useState(TABS[0]);

    return (
        <Layout title="Auto Lead">
            <div className="flex flex-col gap-3">
                <div className="card">
                    <div className="flex items-center gap-3 px-2 py-2 max-md:flex-wrap">
                        <div className="overflow-x-auto scrollbar-none">
                            <Tabs items={TABS} value={tab} setValue={(v) => setTab(TABS.find((t) => t.id === v.id) ?? TABS[0])} />
                        </div>
                        <div className="ml-auto pr-2 text-caption text-t-tertiary max-md:hidden">
                            Real-time lead capture → validate → call
                        </div>
                    </div>
                </div>

                {tab.key === "overview" && <Overview onAddSource={() => setTab(TABS[1])} />}
                {tab.key === "sources" && <Sources />}
                {tab.key === "feed" && <Feed />}
            </div>
        </Layout>
    );
}
