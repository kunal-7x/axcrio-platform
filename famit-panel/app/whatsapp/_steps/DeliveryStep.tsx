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

function statusVariant(l: WhatsAppLogEntry): "success" | "warning" | "danger" | "neutral" {
    if (l.ok) return "success";
    if (l.status === "skipped_no_config") return "warning";
    return "danger";
}

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

    const sent = log.length;
    const delivered = log.filter((l) => l.ok).length;
    const readRate = sent ? Math.round((delivered / sent) * 100) : 0;
    // A real successful send proves WhatsApp delivers today (not just "wired").
    const delivers = delivered > 0;
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

            <div className="flex gap-3 max-md:flex-col">
                <KpiCard className="flex-1" label="Sent" value={sent} icon="send" tone="neutral" />
                <KpiCard className="flex-1" label="Delivered" value={delivered} icon="check-circle" tone="success" />
                <KpiCard className="flex-1" label="Read rate" value={`${readRate}%`} icon="arrow-percent" tone="success" meter={readRate / 100} />
                <KpiCard className="flex-1" label="Failed" value={log.filter((l) => !l.ok && l.status !== "skipped_no_config").length} icon="block" tone="danger" />
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
                        <Table cellsThead={<><th>When</th><th>Phone</th><th>Template</th><th>Kind</th><th>Status</th></>}>
                            {filtered.map((l, i) => (
                                <TableRow key={i}>
                                    <td className="text-t-secondary whitespace-nowrap">{fmt(l.at)}</td>
                                    <td className="text-t-primary tabular-nums">{l.phone}</td>
                                    <td className="text-t-secondary">{l.template || "—"}</td>
                                    <td><Badge variant="neutral">{l.kind}</Badge></td>
                                    <td><Badge variant={statusVariant(l)}>{l.status}</Badge></td>
                                </TableRow>
                            ))}
                        </Table>
                    </div>
                )}
            </Card>
        </div>
    );
}
