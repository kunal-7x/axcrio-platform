// ⑧ AUDIENCE SELECTION (CustomerList list+select + PromotePage Insights strip).
// REUSES the run-campaign audience filters (spec §2 ⑧). col-left = a filterable
// lead table with select-all + temperature filters; col-right = audience-insight
// cards (segment donut, reachable/suppressed KPIs, an AI target suggestion).
// DNC auto-excluded server-side. LIVE: /api/leads + /api/suppression.

"use client";

import { useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Search from "@/components/Search";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Checkbox from "@/components/Checkbox";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import KpiCard from "@/components/KpiCard";
import CardChartPie from "@/components/CardChartPie";
import { getLeads, getSuppression, type Lead } from "@/lib/api";
import {
    tempOf,
    applyTempFilter,
    applyQuery,
    resolveAudience,
    breakdownOf,
    TEMP_DEFS,
    type Temp,
    type AudienceFilter,
} from "../_lib/audience";
import { type StepCtx } from "../_lib/types";

export default function AudienceStep({ goTo, notify }: StepCtx) {
    const [leads, setLeads] = useState<Lead[]>([]);
    const [suppressed, setSuppressed] = useState(0);
    const [loading, setLoading] = useState(true);
    const [temps, setTemps] = useState<Set<Temp>>(new Set());
    const [query, setQuery] = useState("");

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

    const filter: AudienceFilter = useMemo(
        () => ({ temps, useBand: false, band: [0, 100], query }),
        [temps, query]
    );

    const tempFiltered = useMemo(() => applyTempFilter(leads, filter), [leads, filter]);
    const visible = useMemo(() => applyQuery(tempFiltered, query), [tempFiltered, query]);

    // Manual hand-pick selection — a Set<string> (lead ids are strings), the same
    // pattern the run-campaign audience builder uses (resolveAudience: hand-picked
    // rows win; else everything that passed the temperature filter).
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const allVisibleSelected = visible.length > 0 && visible.every((l) => selectedIds.has(l.id));

    const toggleRow = (id: string, on: boolean) => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (on) next.add(id);
            else next.delete(id);
            return next;
        });
    };
    const toggleAll = () => {
        setSelectedIds((prev) => {
            if (allVisibleSelected) {
                const next = new Set(prev);
                visible.forEach((l) => next.delete(l.id));
                return next;
            }
            const next = new Set(prev);
            visible.forEach((l) => next.add(l.id));
            return next;
        });
    };

    const audience = useMemo(
        () => resolveAudience(tempFiltered, selectedIds),
        [tempFiltered, selectedIds]
    );
    const bd = breakdownOf(audience);

    const toggleTemp = (t: Temp) => {
        setTemps((prev) => {
            const next = new Set(prev);
            if (next.has(t)) next.delete(t);
            else next.add(t);
            return next;
        });
    };

    const donut = [
        { name: "Hot", value: bd.hot },
        { name: "Warm", value: bd.warm },
        { name: "Cold", value: bd.cold },
    ].filter((d) => d.value > 0);

    const hotCount = leads.filter((l) => tempOf(l) === "hot").length;

    return (
        <div className="flex gap-3 max-lg:flex-col">
            {/* lead list + select */}
            <div className="flex-1 min-w-0">
                <Card
                    title="Audience"
                    headContent={
                        <Search className="w-56 max-md:w-40" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name or phone" isGray />
                    }
                >
                    {/* temperature filter chips */}
                    <div className="flex flex-wrap items-center gap-2 px-5 pb-3 max-lg:px-3">
                        {TEMP_DEFS.map((t) => (
                            <Button
                                key={t.key}
                                className="!h-9 !px-3.5 !text-body-2 !font-normal"
                                isBlack={temps.has(t.key)}
                                isStroke={!temps.has(t.key)}
                                onClick={() => toggleTemp(t.key)}
                            >
                                {t.label}
                            </Button>
                        ))}
                    </div>

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
                            <Table
                                selectAll={allVisibleSelected}
                                onSelectAll={toggleAll}
                                cellsThead={<><th>Name</th><th>Phone</th><th>Score</th><th>Stage</th></>}
                            >
                                {visible.map((l) => (
                                    <TableRow
                                        key={l.id}
                                        selectedRows={selectedIds.has(l.id)}
                                        onRowSelect={(v) => toggleRow(l.id, v)}
                                    >
                                        <td className="text-t-primary">{l.name || "—"}</td>
                                        <td className="text-t-secondary tabular-nums">{l.phone}</td>
                                        <td className="text-t-secondary tabular-nums">{l.score ?? "—"}</td>
                                        <td>
                                            <Badge variant={tempOf(l) === "hot" ? "danger" : tempOf(l) === "warm" ? "warning" : "neutral"}>
                                                {tempOf(l)}
                                            </Badge>
                                        </td>
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
                    <KpiCard className="flex-1" label="Reachable" value={bd.total} icon="profile" tone="info" />
                    <KpiCard className="flex-1" label="Suppressed (DNC)" value={suppressed} icon="block" tone="warning" />
                </div>

                {donut.length > 0 && (
                    <CardChartPie title="Segment split" data={donut} />
                )}

                {/* AI target suggestion */}
                {hotCount > 0 && (
                    <Card title="Suggestion">
                        <div className="flex items-start gap-3 px-5 pb-5 pt-1 max-lg:px-3">
                            <Icon className="shrink-0 mt-0.5 fill-primary-01" name="magic-pencil" />
                            <div className="grow">
                                <div className="text-body-2 text-t-primary">
                                    Hot leads reply far more — start with {hotCount} hot lead{hotCount === 1 ? "" : "s"}?
                                </div>
                                <Button isStroke className="mt-3" onClick={() => setTemps(new Set(["hot"]))}>
                                    Target hot leads
                                </Button>
                            </div>
                        </div>
                    </Card>
                )}

                <Button isBlack className="w-full" disabled={bd.total === 0} onClick={() => { notify(`${bd.total} recipients selected`, "success"); goTo("schedule"); }}>
                    Continue with {bd.total} recipient{bd.total === 1 ? "" : "s"}
                </Button>
            </div>
        </div>
    );
}
