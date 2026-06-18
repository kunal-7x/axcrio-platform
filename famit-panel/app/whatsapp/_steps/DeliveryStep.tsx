// ⑩ DELIVERY — live send status (Income/StatementsPage status-table archetype).
// The existing message-log table ELEVATED into a campaign-scoped delivery view:
// per-recipient status + a top delivery-KPI strip. LIVE: /api/whatsapp/log.

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Search from "@/components/Search";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import KpiCard from "@/components/KpiCard";
import { getWhatsAppLog, type WhatsAppLogEntry } from "@/lib/api";
import { explainMetaError } from "../_lib/waapi";
import { MetaErrorNote, MetaReadinessHint } from "../_components/MetaStatusNote";
import { type StepCtx } from "../_lib/types";

function fmt(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

// W16: derive the per-row delivery stage from the funnel fields when present,
// else fall back to the legacy ok/status. This is what the founder sees per row.
type Stage = "sent" | "delivered" | "read" | "failed" | "opted_out" | "skipped";
function stageOf(l: WhatsAppLogEntry): Stage {
    if (l.opted_out || l.delivery_status === "opted_out") return "opted_out";
    if (l.delivery_status) {
        if (l.delivery_status === "skipped_no_config") return "skipped";
        if (["read", "delivered", "sent", "failed"].includes(l.delivery_status)) return l.delivery_status as Stage;
    }
    if (l.read_at) return "read";
    if (l.delivered_at) return "delivered";
    if (l.status === "skipped_no_config") return "skipped";
    if (!l.ok) return "failed";
    return "sent";
}

const STAGE_VARIANT: Record<Stage, "success" | "warning" | "danger" | "neutral"> = {
    read: "success",
    delivered: "success",
    sent: "neutral",
    skipped: "warning",
    opted_out: "warning",
    failed: "danger",
};
const STAGE_LABEL: Record<Stage, string> = {
    read: "Read",
    delivered: "Delivered",
    sent: "Sent",
    skipped: "Pending creds",
    opted_out: "Opted out",
    failed: "Failed",
};

export default function DeliveryStep({ goTo }: StepCtx) {
    const [log, setLog] = useState<WhatsAppLogEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [q, setQ] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setErr("");
        getWhatsAppLog()
            .then((r) => setLog(r.log || []))
            .catch((e) => setErr(e instanceof Error ? e.message : "Failed to load delivery log"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    // W16 delivery funnel counts (sent/delivered/read/failed/opt-out).
    const stages = useMemo(() => log.map(stageOf), [log]);
    const went = stages.filter((s) => s === "sent" || s === "delivered" || s === "read").length;
    const deliveredN = stages.filter((s) => s === "delivered" || s === "read").length;
    const readN = stages.filter((s) => s === "read").length;
    const failedN = stages.filter((s) => s === "failed").length;
    const optedN = stages.filter((s) => s === "opted_out").length;
    const sent = went || log.length;
    const readRate = went ? Math.round((readN / went) * 100) : 0;
    // A real successful send proves WhatsApp delivers today (not just "wired").
    const delivers = deliveredN > 0;
    // Surface the MOST RECENT failed row's real Meta reason (log is newest-first
    // server-side; fall back to a scan). Skipped-no-config rows are the only ones
    // that mean "no provider"; everything else is a real Meta error worth showing.
    const lastFailed = useMemo(
        () => log.find((l) => !l.ok),
        [log]
    );
    const failExplain = lastFailed
        ? explainMetaError({
              error: lastFailed.error,
              status: lastFailed.status,
              meta_error: lastFailed.meta_error,
          })
        : null;

    const filtered = useMemo(() => {
        const s = q.trim().toLowerCase();
        if (!s) return log;
        return log.filter(
            (l) => (l.phone || "").toLowerCase().includes(s) || (l.template || "").toLowerCase().includes(s)
        );
    }, [log, q]);

    return (
        <div className="flex flex-col gap-3">
            {/* Truthful Meta status — credentials ARE set; show real readiness
                + (if any recent send failed) Meta's own reason in plain language. */}
            {failExplain ? (
                <MetaErrorNote explain={failExplain} />
            ) : (
                <MetaReadinessHint delivers={delivers} />
            )}

            <div className="flex gap-3 max-md:flex-col flex-wrap">
                <KpiCard className="flex-1 min-w-36" label="Sent" value={sent} icon="send" tone="neutral" />
                <KpiCard className="flex-1 min-w-36" label="Delivered" value={deliveredN} icon="check-circle" tone="success" />
                <KpiCard className="flex-1 min-w-36" label="Read" value={readN} icon="search" tone="success" />
                <KpiCard className="flex-1 min-w-36" label="Read rate" value={`${readRate}%`} icon="arrow-percent" tone="success" meter={readRate / 100} />
                <KpiCard className="flex-1 min-w-36" label="Failed" value={failedN} icon="block" tone="danger" />
                <KpiCard className="flex-1 min-w-36" label="Opted out" value={optedN} icon="profile" tone="warning" />
            </div>

            <Card
                title="Delivery"
                headContent={
                    <div className="flex items-center gap-2">
                        <Search className="w-56 max-md:w-36" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search phone or template" isGray />
                        <Button isStroke isCircle icon="arrow" onClick={load} />
                    </div>
                }
            >
                {err ? (
                    <div className="mx-5 my-4 flex items-center gap-3 p-4 rounded-3xl bg-b-surface2 border border-primary-03/40 text-body-2 text-t-secondary max-lg:mx-3">
                        <Icon className="shrink-0 fill-primary-03" name="info" />
                        <span className="text-t-primary">{err}</span>
                    </div>
                ) : loading ? (
                    <div className="py-16"><Spinner /></div>
                ) : filtered.length === 0 ? (
                    <div className="flex flex-col items-center text-center py-16 px-5">
                        <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                            <Icon className="fill-t-secondary" name="chat" />
                        </div>
                        <div className="text-sub-title-1 text-t-primary">{q ? "No messages match" : "No messages yet"}</div>
                        <div className="mt-1 max-w-80 text-body-2 text-t-secondary">Sent messages and their delivery status appear here.</div>
                        <Button isStroke className="mt-6" onClick={() => goTo("schedule")}>Go to schedule</Button>
                    </div>
                ) : (
                    <div className="p-1 pt-3 max-lg:px-0">
                        <Table cellsThead={<><th>When</th><th>Phone</th><th>Template</th><th>Delivery</th><th>Detail</th></>}>
                            {filtered.map((l, i) => {
                                const st = stageOf(l);
                                return (
                                    <TableRow key={i}>
                                        <td className="text-t-secondary whitespace-nowrap">{fmt(l.at)}</td>
                                        <td className="text-t-primary tabular-nums">{l.phone}</td>
                                        <td className="text-t-secondary">{l.template || "—"}</td>
                                        <td><Badge variant={STAGE_VARIANT[st]}>{STAGE_LABEL[st]}</Badge></td>
                                        <td className="text-t-tertiary max-w-72 truncate" title={l.error || ""}>
                                            {st === "failed" ? (l.meta_error?.error_user_msg || l.error || "Delivery failed") :
                                             st === "read" ? fmt(l.read_at || "") :
                                             st === "delivered" ? fmt(l.delivered_at || "") : "—"}
                                        </td>
                                    </TableRow>
                                );
                            })}
                        </Table>
                    </div>
                )}
            </Card>
        </div>
    );
}
