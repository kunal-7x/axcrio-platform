// ⑪ ANALYTICS + OPTIMIZATION (EarningPage + ProductActivity archetype). KPI
// strip + funnel CardChartPie + per-variant table with set_status(winner) +
// reuse-winner / "more like this" cards (the learning loop).
//
// DORMANT-SAFE: performance writeback (creative.update_metrics) lands with the
// parallel wave — until then this degrades to a calm ComingSoon, while basic
// send/delivery counts (LIVE) still surface from the message log.

"use client";

import { useEffect, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import KpiCard from "@/components/KpiCard";
import CardChartPie from "@/components/CardChartPie";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import ComingSoon from "../_components/ComingSoon";
import { getCampaignPerformance, type VariantPerf } from "../_lib/waapi";
import { getWhatsAppLog, type WhatsAppLogEntry } from "@/lib/api";
import { type StepCtx } from "../_lib/types";

export default function AnalyticsStep({ campaign, goTo }: StepCtx) {
    const [phase, setPhase] = useState<"loading" | "ready" | "dormant">("loading");
    const [variants, setVariants] = useState<VariantPerf[]>([]);
    const [funnel, setFunnel] = useState<{ stage: string; count: number }[]>([]);
    const [log, setLog] = useState<WhatsAppLogEntry[]>([]);

    useEffect(() => {
        let active = true;
        getWhatsAppLog().then((r) => active && setLog(r.log || [])).catch(() => {});
        getCampaignPerformance(campaign?.id).then((r) => {
            if (!active) return;
            if (!r.configured) {
                setPhase("dormant");
                return;
            }
            setVariants(r.variants);
            setFunnel(r.funnel);
            setPhase("ready");
        });
        return () => { active = false; };
    }, [campaign?.id]);

    // LIVE basic counts (always available from the message log)
    const sent = log.length;
    const delivered = log.filter((l) => l.ok).length;
    const readRate = sent ? Math.round((delivered / sent) * 100) : 0;

    if (phase === "loading") return <div className="py-20"><Spinner /></div>;

    if (phase === "dormant") {
        return (
            <div className="flex flex-col gap-3">
                {/* the LIVE counts still render above the dormant deep-analytics card */}
                <div className="flex gap-3 max-md:flex-col">
                    <KpiCard className="flex-1" label="Sent" value={sent} icon="send" tone="neutral" />
                    <KpiCard className="flex-1" label="Delivered" value={delivered} icon="check-circle" tone="success" />
                    <KpiCard className="flex-1" label="Read rate" value={`${readRate}%`} icon="arrow-percent" tone="success" meter={readRate / 100} />
                </div>
                <ComingSoon
                    title="Campaign analytics"
                    body="Per-variant read/reply/conversion analytics and the winning-template learning loop activate once performance writeback is connected. Send and delivery counts above are live today."
                    icon="chart"
                />
            </div>
        );
    }

    const funnelData = funnel.map((f) => ({ name: f.stage, value: f.count }));

    return (
        <div className="flex flex-col gap-3">
            <div className="flex gap-3 max-md:flex-col">
                <KpiCard className="flex-1" label="Delivered" value={delivered} icon="check-circle" tone="success" />
                <KpiCard className="flex-1" label="Read rate" value={`${readRate}%`} icon="arrow-percent" tone="success" meter={readRate / 100} />
                <KpiCard className="flex-1" label="Variants" value={variants.length} icon="layers" tone="info" />
            </div>

            <div className="flex gap-3 max-lg:flex-col">
                {funnelData.length > 0 && (
                    <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0">
                        <CardChartPie title="Funnel" data={funnelData} />
                    </div>
                )}

                <div className="flex-1 min-w-0">
                    <Card title="Per-variant performance">
                        {variants.length === 0 ? (
                            <div className="px-5 py-16 text-center text-body-2 text-t-secondary max-lg:px-3">
                                No variant data yet — it accrues as messages are read and replied to.
                            </div>
                        ) : (
                            <div className="p-1 pt-3 max-lg:px-0">
                                <Table cellsThead={<><th>Variant</th><th>Angle</th><th>Delivered</th><th>Read</th><th>Reply</th><th></th></>}>
                                    {variants.map((v) => (
                                        <TableRow key={v.asset_id}>
                                            <td className="text-t-primary">{v.title}</td>
                                            <td className="text-t-secondary">{v.angle || "—"}</td>
                                            <td className="text-t-secondary tabular-nums">{v.delivered ?? "—"}</td>
                                            <td className="text-t-secondary tabular-nums">{v.read ?? "—"}</td>
                                            <td className="text-t-secondary tabular-nums">{v.replied ?? "—"}</td>
                                            <td className="text-right">
                                                {v.status === "winner" ? (
                                                    <Badge variant="success">Winner</Badge>
                                                ) : (
                                                    <Button isStroke>Mark winner</Button>
                                                )}
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        )}
                    </Card>
                </div>
            </div>

            {/* learning-loop reuse cards */}
            <Card title="Optimization">
                <div className="flex flex-wrap gap-3 px-5 pb-5 pt-1 max-lg:px-3">
                    <div className="flex items-center gap-3 grow p-3.5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
                        <Icon className="shrink-0 fill-primary-02" name="star-fill" />
                        <div className="grow">
                            <div className="text-button text-t-primary">Reuse the winner</div>
                            <div className="text-caption text-t-tertiary">Clone the best combo for another campaign.</div>
                        </div>
                        <Button isStroke onClick={() => goTo("launchpad")}>Clone</Button>
                    </div>
                    <div className="flex items-center gap-3 grow p-3.5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
                        <Icon className="shrink-0 fill-primary-01" name="magic-pencil" />
                        <div className="grow">
                            <div className="text-button text-t-primary">Make more like this</div>
                            <div className="text-caption text-t-tertiary">Generate 5 variations of the winning banner.</div>
                        </div>
                        <Button isStroke onClick={() => goTo("banner")}>Generate</Button>
                    </div>
                </div>
            </Card>
        </div>
    );
}
