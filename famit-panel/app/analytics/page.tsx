"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import { getAnalytics, getCampaigns, type AnalyticsFunnel, type Campaign } from "@/lib/api";
import { SelectOption } from "@/types/select";
import {
    ResponsiveContainer,
    FunnelChart,
    Funnel,
    LabelList,
    Cell,
    Tooltip,
} from "recharts";

// Brand-blue funnel ramp (token-driven). A calm primary-01 -> lighter-blue
// descent so the funnel reads as Famit, not a generic AI chart.
const FUNNEL_COLORS = [
    "var(--primary-01)",
    "color-mix(in srgb, var(--primary-01) 82%, var(--backgrounds-surface2))",
    "color-mix(in srgb, var(--primary-01) 64%, var(--backgrounds-surface2))",
    "color-mix(in srgb, var(--primary-01) 48%, var(--backgrounds-surface2))",
    "color-mix(in srgb, var(--primary-01) 34%, var(--backgrounds-surface2))",
    "color-mix(in srgb, var(--primary-01) 22%, var(--backgrounds-surface2))",
    "color-mix(in srgb, var(--primary-01) 14%, var(--backgrounds-surface2))",
];

const ALL_CAMPAIGNS: SelectOption = { id: 0, name: "All campaigns" };

export default function AnalyticsPage() {
    const [data, setData] = useState<AnalyticsFunnel | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [campaign, setCampaign] = useState<SelectOption>(ALL_CAMPAIGNS);

    const campaignOptions = useMemo<SelectOption[]>(
        () => [ALL_CAMPAIGNS, ...campaigns.map((c, i) => ({ id: i + 1, name: c.name, _id: c.id } as SelectOption & { _id: string }))],
        [campaigns]
    );
    const selectedCampaignId =
        campaign.id === 0 ? "" : (campaignOptions.find((o) => o.id === campaign.id) as { _id?: string })?._id ?? "";

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getAnalytics(selectedCampaignId ? { campaign_id: selectedCampaignId } : undefined)
            .then(setData)
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load analytics"))
            .finally(() => setLoading(false));
    }, [selectedCampaignId]);

    useEffect(() => {
        getCampaigns()
            .then((r) => setCampaigns(r.campaigns))
            .catch(() => {});
    }, []);

    useEffect(() => { load(); }, [load]);

    // Auto-refresh every 30s
    useEffect(() => {
        const t = setInterval(load, 30000);
        return () => clearInterval(t);
    }, [load]);

    const funnelData = data?.funnel ?? [];
    const convRate = data && data.dialed > 0
        ? `${((data.answered / data.dialed) * 100).toFixed(1)}%`
        : "—";
    const qualRate = data && data.answered > 0
        ? `${((data.qualified / data.answered) * 100).toFixed(1)}%`
        : "—";

    const kpis = data
        ? [
              { label: "Dialed", value: data.dialed, sub: "leads attempted" },
              { label: "Answered", value: data.answered, sub: `${convRate} connect rate` },
              { label: "Qualified", value: data.qualified, sub: `${qualRate} of answered` },
              { label: "Callbacks", value: data.callback, sub: "scheduled" },
          ]
        : [];

    return (
        <Layout title="Analytics">
            {error && (
                <div className="mb-4 flex items-center gap-3 p-4 rounded-3xl bg-b-surface2 border border-primary-03/40 text-body-2 text-t-secondary">
                    <Icon className="shrink-0 fill-primary-03" name="info" />
                    <span className="text-t-primary">{error}</span>
                </div>
            )}

            {loading && !data ? (
                <div className="py-24"><Spinner /></div>
            ) : (
                <div className="flex flex-col gap-3">
                    {/* KPI strip */}
                    <Card title="Overview">
                        <div className="flex max-md:flex-col px-5 pb-2 max-lg:px-3">
                            {kpis.map((k, i) => (
                                <div
                                    key={k.label}
                                    className={`flex-1 py-2 ${i > 0 ? "pl-6 border-l border-s-subtle max-md:pl-0 max-md:border-l-0 max-md:border-t max-md:pt-4 max-md:mt-2" : ""}`}
                                >
                                    <div className="text-caption text-t-tertiary">{k.label}</div>
                                    <div className="mt-1 text-h4 text-t-primary tabular-nums">{k.value}</div>
                                    <div className="mt-1 text-caption text-t-secondary">{k.sub}</div>
                                </div>
                            ))}
                        </div>
                    </Card>

                    {/* Funnel chart */}
                    <Card
                        title="Conversion funnel"
                        selectOptions={campaignOptions as { id: number; name: string }[]}
                        selectValue={campaign as { id: number; name: string }}
                        selectOnChange={(v) => setCampaign(v)}
                    >
                        {funnelData.length > 0 ? (
                            <div className="px-4 pb-4 h-80">
                                <ResponsiveContainer width="100%" height="100%">
                                    <FunnelChart>
                                        <Tooltip
                                            contentStyle={{
                                                background: "var(--backgrounds-surface2)",
                                                border: "1px solid var(--stroke-stroke2)",
                                                borderRadius: "12px",
                                            }}
                                        />
                                        <Funnel dataKey="count" data={funnelData} isAnimationActive>
                                            {funnelData.map((_, i) => (
                                                <Cell key={i} fill={FUNNEL_COLORS[i % FUNNEL_COLORS.length]} />
                                            ))}
                                            <LabelList
                                                position="right"
                                                fill="var(--text-secondary)"
                                                stroke="none"
                                                dataKey="stage"
                                                style={{ fontSize: "12px" }}
                                            />
                                        </Funnel>
                                    </FunnelChart>
                                </ResponsiveContainer>
                            </div>
                        ) : (
                            <div className="flex flex-col items-center text-center py-16 px-5">
                                <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-secondary" name="chart" />
                                </div>
                                <div className="text-sub-title-1 text-t-primary">No funnel data yet</div>
                                <div className="mt-1 text-body-2 text-t-secondary max-w-80">
                                    Once leads are dialed, your end-to-end conversion funnel appears here.
                                </div>
                            </div>
                        )}
                    </Card>

                    {/* Funnel details table */}
                    {funnelData.length > 0 && (
                        <Card title="Funnel details">
                            <div className="p-1 pt-3 max-lg:px-0">
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Stage</th>
                                            <th>Count</th>
                                            <th className="text-right">% of dialed</th>
                                        </>
                                    }
                                >
                                    {funnelData.map((row, i) => (
                                        <TableRow key={i}>
                                            <td className="font-medium text-t-primary capitalize">{row.stage.replace(/_/g, " ")}</td>
                                            <td className="text-t-primary tabular-nums">{row.count}</td>
                                            <td className="text-t-secondary tabular-nums text-right">
                                                {data && data.dialed > 0 ? `${((row.count / data.dialed) * 100).toFixed(1)}%` : "—"}
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        </Card>
                    )}
                </div>
            )}
        </Layout>
    );
}
