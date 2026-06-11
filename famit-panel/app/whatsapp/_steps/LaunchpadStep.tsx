// ① LAUNCHPAD — the campaign home (HomePage 2-col archetype). KPI strip +
// "Your WhatsApp campaigns" cards (col-left) + Winning-templates reuse +
// Needs-approval (col-right). Selecting a campaign advances to ② pre-filled.
//
// LIVE: campaigns via /api/campaigns + KPIs derived from the message log.
// DORMANT-SAFE: the "Winning templates" reuse gallery reads creative.search and
// degrades to a calm empty state when :8310 is dormant (never an error).

"use client";

import { useEffect, useState } from "react";
import KpiCard from "@/components/KpiCard";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Image from "@/components/Image";
import { getCampaigns, getWhatsAppLog, type Campaign, type WhatsAppLogEntry } from "@/lib/api";
import { searchAssets } from "../_lib/waapi";
import { contextFromCampaign } from "../_lib/waapi";
import { type StepCtx, type AssetRef } from "../_lib/types";

export default function LaunchpadStep({ setCampaign, goTo }: StepCtx) {
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [log, setLog] = useState<WhatsAppLogEntry[]>([]);
    const [winners, setWinners] = useState<AssetRef[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let active = true;
        Promise.all([
            getCampaigns().catch(() => ({ campaigns: [] as Campaign[] })),
            getWhatsAppLog().catch(() => ({ log: [] as WhatsAppLogEntry[] })),
        ]).then(([c, l]) => {
            if (!active) return;
            setCampaigns(c.campaigns || []);
            setLog(l.log || []);
            setLoading(false);
        });
        // dormant-safe winners gallery
        searchAssets({ status: "winner", sort: "top_ctr" }).then((r) => {
            if (active && r.configured) setWinners(r.items.slice(0, 4));
        });
        return () => {
            active = false;
        };
    }, []);

    const sent30 = log.length;
    const delivered = log.filter((l) => l.ok).length;
    const readRate = sent30 ? Math.round((delivered / sent30) * 100) : 0;

    const pick = (c: Campaign) => {
        setCampaign(c, contextFromCampaign(c));
        goTo("campaign");
    };

    return (
        <div className="flex flex-col gap-3">
            {/* KPI strip */}
            <div className="flex gap-3 max-md:flex-col">
                <KpiCard className="flex-1" label="Active campaigns" value={campaigns.length} icon="promote" tone="info" />
                <KpiCard className="flex-1" label="Messages sent (30d)" value={sent30} icon="chat" tone="neutral" />
                <KpiCard className="flex-1" label="Delivered" value={delivered} icon="check-circle" tone="success" />
                <KpiCard className="flex-1" label="Read rate" value={`${readRate}%`} icon="arrow-percent" tone="success" meter={readRate / 100} />
            </div>

            <div className="flex gap-3 max-lg:flex-col">
                {/* col-left: campaign cards */}
                <div className="flex-1 min-w-0">
                    <Card
                        title="Your WhatsApp campaigns"
                        headContent={
                            <Button isBlack icon="plus" onClick={() => goTo("campaign")}>
                                New campaign
                            </Button>
                        }
                    >
                        {loading ? (
                            <div className="py-16"><Spinner /></div>
                        ) : campaigns.length === 0 ? (
                            <div className="flex flex-col items-center text-center py-16 px-5">
                                <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-secondary" name="promote" />
                                </div>
                                <div className="text-sub-title-1 text-t-primary">Create your first campaign</div>
                                <div className="mt-1 max-w-80 text-body-2 text-t-secondary">
                                    Pick a campaign and the AI writes WhatsApp templates from its real data.
                                </div>
                            </div>
                        ) : (
                            <div className="grid grid-cols-2 gap-3 p-3 pt-1 max-md:grid-cols-1">
                                {campaigns.map((c) => (
                                    <button
                                        key={c.id}
                                        onClick={() => pick(c)}
                                        className="flex flex-col items-start text-left p-4 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle transition-shadow hover:shadow-depth"
                                    >
                                        <div className="flex items-center w-full gap-2">
                                            <div className="grow text-sub-title-1 text-t-primary truncate">{c.name}</div>
                                            <Badge variant={c.status === "active" ? "success" : "neutral"}>{c.status}</Badge>
                                        </div>
                                        <div className="mt-1 text-body-2 text-t-secondary truncate w-full">
                                            {c.product || c.company || "—"}
                                        </div>
                                    </button>
                                ))}
                            </div>
                        )}
                    </Card>
                </div>

                {/* col-right: winning templates + needs approval */}
                <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0 flex flex-col gap-3">
                    <Card title="Winning templates">
                        {winners.length === 0 ? (
                            <div className="px-5 py-10 text-center max-lg:px-3">
                                <div className="flex justify-center items-center size-12 mx-auto mb-3 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-tertiary !size-5" name="star-stroke" />
                                </div>
                                <div className="text-body-2 text-t-secondary max-w-72 mx-auto">
                                    Top-performing template + banner combos appear here to clone for new campaigns.
                                </div>
                            </div>
                        ) : (
                            <div className="flex flex-col gap-2 p-3 pt-1">
                                {winners.map((w) => (
                                    <div key={w.id} className="flex items-center gap-3 p-2 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle">
                                        <div className="relative size-12 shrink-0 rounded-xl overflow-hidden bg-b-surface1">
                                            {w.thumb_url && <Image className="object-cover" src={w.thumb_url} alt="" fill sizes="48px" />}
                                        </div>
                                        <div className="grow min-w-0">
                                            <div className="text-button text-t-primary truncate">{w.title || "Winning combo"}</div>
                                            <div className="text-caption text-t-tertiary">
                                                {w.metrics?.ctr != null ? `${w.metrics.ctr}% CTR` : "Top performer"}
                                            </div>
                                        </div>
                                        <Button isStroke onClick={() => goTo("campaign")}>Clone</Button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Card>

                    <Card title="Needs approval">
                        <div className="px-5 py-8 text-center text-body-2 text-t-secondary max-lg:px-3">
                            Drafts awaiting content-policy approval show here.{" "}
                            <button onClick={() => goTo("approval")} className="text-t-primary underline underline-offset-2">
                                Open approvals
                            </button>
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
}
