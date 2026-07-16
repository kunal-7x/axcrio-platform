"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Card from "@/components/Card";
import Tabs from "@/components/Tabs";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import { getFeed, getSources, type FeedEvent } from "../client";
import { SourceIcon, fmtRelative, CHANNEL_LABEL } from "../_ui";

const TABS = [
    { id: 1, name: "All", key: "" },
    { id: 2, name: "Accepted", key: "accepted" },
    { id: 3, name: "Rejected", key: "rejected" },
];

export default function Feed() {
    const [tab, setTab] = useState(TABS[0]);
    const sourcesQ = useQuery({ queryKey: ["auto-lead", "sources"], queryFn: getSources });
    const iconByType = new Map((sourcesQ.data?.sources ?? []).map((s) => [s.type, s.icon]));

    const q = useQuery({
        queryKey: ["auto-lead", "feed", tab.key],
        queryFn: () => getFeed({ status: tab.key, limit: 150 }),
        refetchInterval: 4000,
    });
    const events: FeedEvent[] = q.data?.events ?? [];

    return (
        <div className="card">
            <div className="flex items-center min-h-12 px-2 py-2 max-md:flex-wrap gap-2">
                <div className="pl-3 text-h6 mr-auto max-md:w-full">Live feed</div>
                <div className="flex items-center gap-2 pr-1">
                    <span className="flex items-center gap-1.5 text-caption text-t-tertiary">
                        <span className="size-1.5 rounded-full bg-primary-02 animate-pulse" />
                        live
                    </span>
                    <Tabs items={TABS} value={tab} setValue={(v) => setTab(TABS.find((t) => t.id === v.id) ?? TABS[0])} />
                </div>
            </div>

            {q.isLoading ? (
                <div className="p-5 flex flex-col gap-2">
                    {[...Array(6)].map((_, i) => (
                        <div key={i} className="skeleton h-14 rounded-2xl" />
                    ))}
                </div>
            ) : events.length === 0 ? (
                <div className="py-16 text-center max-md:py-12">
                    <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                        <Icon name="promote" className="fill-t-tertiary" />
                    </span>
                    <div className="text-h6 mb-1">No activity yet</div>
                    <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                        Connect a source and leads will stream in here the instant they arrive — each one
                        validated and routed in real time.
                    </div>
                </div>
            ) : (
                <div className="flex flex-col px-2 pb-2">
                    {events.map((e) => (
                        <div
                            key={e.id}
                            className="flex items-center gap-3 px-3 py-3 rounded-2xl transition-colors hover:bg-b-surface1"
                        >
                            <SourceIcon icon={iconByType.get(e.source_type) || "chain"} type={e.source_type} size={11} />
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2">
                                    <span className="truncate text-sub-title-1 text-t-primary">
                                        {e.name || e.phone || e.email || "Unknown lead"}
                                    </span>
                                    {e.actions?.includes("crm_synced") && (
                                        <Icon name="chart" className="size-3.5 fill-primary-01 shrink-0" />
                                    )}
                                </div>
                                <div className="text-caption text-t-tertiary truncate">
                                    {[e.phone, e.email].filter(Boolean).join(" · ") || "—"} · {e.source_name}
                                    {e.channel ? ` · ${CHANNEL_LABEL[e.channel] || e.channel}` : ""}
                                </div>
                            </div>
                            <div className="text-right shrink-0">
                                {e.accepted ? (
                                    <Badge variant="success" dot>
                                        Imported
                                    </Badge>
                                ) : (
                                    <Badge variant="danger">{e.reason || "Rejected"}</Badge>
                                )}
                                <div className="text-caption text-t-tertiary mt-1">{fmtRelative(e.at)}</div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
