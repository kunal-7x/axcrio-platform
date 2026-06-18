// ⑩ AUDIENCE SELECTION (W16 upgraded). NOT "send to all" — the founder targets a
// real segment: Hot/Warm/Cold/Dead, requested-brochure, follow-up-pending, a
// specific campaign or agent, or a hand-picked set. REUSES the run-campaign
// audience builder for the temperature bands + the W15 shared LeadBadge for the
// row pill. LIVE: /api/leads + /api/suppression (truthful client-side preview).

"use client";

import { useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Search from "@/components/Search";
import Select from "@/components/Select";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import KpiCard from "@/components/KpiCard";
import CardChartPie from "@/components/CardChartPie";
import { getLeads, getSuppression, type Lead } from "@/lib/api";
import { applyQuery } from "../_lib/audience";
import { LeadBadge } from "@/lib/badges";
import {
    EMPTY_TARGETING,
    applyTargeting,
    waBreakdown,
    distinctCampaigns,
    distinctAgents,
    type WaTargeting,
    type WaTemp,
} from "../_lib/targeting";
import { type StepCtx } from "../_lib/types";

const TEMP_CHIPS: { key: WaTemp; label: string }[] = [
    { key: "hot", label: "Hot" },
    { key: "warm", label: "Warm" },
    { key: "cold", label: "Cold" },
    { key: "dead", label: "Dead" },
];

const SIGNAL_CHIPS: { key: "requestedBrochure" | "followUpPending"; label: string; icon: string }[] = [
    { key: "requestedBrochure", label: "Requested brochure", icon: "feather" },
    { key: "followUpPending", label: "Follow-up pending", icon: "calendar" },
];

const ANY = { id: 0, name: "Any" };

export default function AudienceStep({ goTo, notify }: StepCtx) {
    const [leads, setLeads] = useState<Lead[]>([]);
    const [suppressed, setSuppressed] = useState(0);
    const [loading, setLoading] = useState(true);
    const [t, setT] = useState<WaTargeting>(EMPTY_TARGETING);
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

    useEffect(() => {
        Promise.all([
            getLeads().catch(() => ({ leads: [] as Lead[] })),
            getSuppression().catch(() => ({ numbers: [], total: 0 })),
        ]).then(([l, s]) => {
            setLeads(l.leads || []);
            setSuppressed(s.total || 0);
            setLoading(false);
        });
    }, []);

    const campaigns = useMemo(() => distinctCampaigns(leads), [leads]);
    const agents = useMemo(() => distinctAgents(leads), [leads]);

    // resolved audience (targeting + manual override) and the table-visible subset.
    const audience = useMemo(() => applyTargeting(leads, t, selectedIds), [leads, t, selectedIds]);
    const visible = useMemo(() => {
        // Always show the WHOLE pool (filtered by the search box) so the user can
        // hand-pick rows even before choosing a target segment. The right-hand
        // "Targeted" count reflects the resolved audience, not the table view.
        return applyQuery(leads, t.query);
    }, [leads, t.query]);
    const bd = waBreakdown(audience);

    const toggleTemp = (k: WaTemp) =>
        setT((p) => {
            const temps = new Set(p.temps);
            temps.has(k) ? temps.delete(k) : temps.add(k);
            return { ...p, temps };
        });
    const toggleSignal = (k: "requestedBrochure" | "followUpPending") =>
        setT((p) => ({ ...p, [k]: !p[k] }));

    const allVisibleSelected = visible.length > 0 && visible.every((l) => selectedIds.has(l.id));
    const toggleRow = (id: string, on: boolean) =>
        setSelectedIds((prev) => {
            const next = new Set(prev);
            on ? next.add(id) : next.delete(id);
            return next;
        });
    const toggleAll = () =>
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (allVisibleSelected) visible.forEach((l) => next.delete(l.id));
            else visible.forEach((l) => next.add(l.id));
            return next;
        });

    const donut = [
        { name: "Hot", value: bd.hot },
        { name: "Warm", value: bd.warm },
        { name: "Cold", value: bd.cold },
        { name: "Dead", value: bd.dead },
    ].filter((d) => d.value > 0);

    return (
        <div className="flex gap-3 max-lg:flex-col">
            <div className="flex-1 min-w-0">
                <Card
                    title="Audience"
                    headContent={
                        <Search className="w-56 max-md:w-40" value={t.query} onChange={(e) => setT((p) => ({ ...p, query: e.target.value }))} placeholder="Search name or phone" isGray />
                    }
                >
                    {/* TEMPERATURE chips */}
                    <div className="flex flex-wrap items-center gap-2 px-5 pb-2 max-lg:px-3">
                        {TEMP_CHIPS.map((c) => (
                            <Button key={c.key} className="!h-9 !px-3.5 !text-body-2 !font-normal" isBlack={t.temps.has(c.key)} isStroke={!t.temps.has(c.key)} onClick={() => toggleTemp(c.key)}>
                                {c.label}
                            </Button>
                        ))}
                    </div>

                    {/* BEHAVIOURAL signal chips */}
                    <div className="flex flex-wrap items-center gap-2 px-5 pb-2 max-lg:px-3">
                        {SIGNAL_CHIPS.map((c) => (
                            <Button key={c.key} className="!h-9 !px-3.5 !text-body-2 !font-normal" isBlack={t[c.key]} isStroke={!t[c.key]} onClick={() => toggleSignal(c.key)}>
                                <Icon className="!size-4 mr-1.5 fill-current" name={c.icon} />
                                {c.label}
                            </Button>
                        ))}
                    </div>

                    {/* CAMPAIGN / AGENT dimension selects */}
                    {(campaigns.length > 0 || agents.length > 0) && (
                        <div className="flex flex-wrap items-center gap-3 px-5 pb-3 max-lg:px-3">
                            {campaigns.length > 0 && (
                                <Select
                                    className="min-w-44"
                                    label="Campaign"
                                    value={t.campaign ? { id: 1, name: t.campaign } : ANY}
                                    onChange={(o) => setT((p) => ({ ...p, campaign: o.name === "Any" ? "" : o.name }))}
                                    options={[ANY, ...campaigns.map((c, i) => ({ id: i + 1, name: c }))]}
                                />
                            )}
                            {agents.length > 0 && (
                                <Select
                                    className="min-w-44"
                                    label="Agent"
                                    value={t.agent ? { id: 1, name: t.agent } : ANY}
                                    onChange={(o) => setT((p) => ({ ...p, agent: o.name === "Any" ? "" : o.name }))}
                                    options={[ANY, ...agents.map((a, i) => ({ id: i + 1, name: a }))]}
                                />
                            )}
                        </div>
                    )}

                    {loading ? (
                        <div className="py-16"><Spinner /></div>
                    ) : visible.length === 0 ? (
                        <div className="flex flex-col items-center text-center py-16 px-5">
                            <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                <Icon className="fill-t-secondary" name="profile" />
                            </div>
                            <div className="text-sub-title-1 text-t-primary">No leads match</div>
                        </div>
                    ) : (
                        <div className="p-1 pt-2 max-lg:px-0">
                            <Table selectAll={allVisibleSelected} onSelectAll={toggleAll} cellsThead={<><th>Name</th><th>Phone</th><th>Score</th><th>Stage</th></>}>
                                {visible.map((l) => (
                                    <TableRow key={l.id} selectedRows={selectedIds.has(l.id)} onRowSelect={(v) => toggleRow(l.id, v)}>
                                        <td className="text-t-primary">{l.name || "—"}</td>
                                        <td className="text-t-secondary tabular-nums">{l.phone}</td>
                                        <td className="text-t-secondary tabular-nums">{l.score ?? "—"}</td>
                                        <td><LeadBadge lead={l} /></td>
                                    </TableRow>
                                ))}
                            </Table>
                        </div>
                    )}
                </Card>
            </div>

            {/* audience insights */}
            <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0 flex flex-col gap-3">
                <div className="flex gap-3">
                    <KpiCard className="flex-1" label="Targeted" value={bd.total} icon="profile" tone="info" />
                    <KpiCard className="flex-1" label="Suppressed (DNC)" value={suppressed} icon="block" tone="warning" />
                </div>

                {donut.length > 0 && <CardChartPie title="Segment split" data={donut} />}

                <Card title="Quick targets">
                    <div className="flex flex-wrap gap-2 px-5 pb-5 pt-1 max-lg:px-3">
                        <Button isStroke onClick={() => setT({ ...EMPTY_TARGETING, temps: new Set<WaTemp>(["hot"]) })}>Hot only</Button>
                        <Button isStroke onClick={() => setT({ ...EMPTY_TARGETING, requestedBrochure: true })}>Requested brochure</Button>
                        <Button isStroke onClick={() => setT({ ...EMPTY_TARGETING, followUpPending: true })}>Follow-up pending</Button>
                        <Button isStroke onClick={() => { setT(EMPTY_TARGETING); setSelectedIds(new Set()); }}>Clear</Button>
                    </div>
                </Card>

                <Button isBlack className="w-full" disabled={bd.total === 0 && selectedIds.size === 0} onClick={() => { notify(`${bd.total} recipients selected`, "success"); goTo("schedule"); }}>
                    Continue with {bd.total} recipient{bd.total === 1 ? "" : "s"}
                </Button>
            </div>
        </div>
    );
}
