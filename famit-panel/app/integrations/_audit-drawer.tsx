"use client";

// ============================================================================
// _audit-drawer — the Audit tab (design crazy-ui-security §B). An append-only
// table of provider.* registry events (create / update / delete / credential /
// reveal / test) with an Export CSV button (SIEM / SOC-2 / B2B-procurement gate)
// and a right slide-over drawer for a single event's detail. Reads the existing
// /audit feed (getControlAudit) and filters to provider.* actions, so it shares
// the immutable control-audit leg — no new endpoint.
//
// Export uses a text button (download glyph doesn't exist — glyph ground-truth).
// The plaintext key is NEVER in the audit (the backend logs only key_masked).
// ============================================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Modal from "@/components/Modal";
import Spinner from "@/components/Spinner";
import { getControlAudit, type AuditEvent } from "@/lib/api";
import { textBtnCls, fmtDateTime } from "./_shared";

function actionTone(action: string): "success" | "warning" | "danger" | "neutral" | "info" {
    if (action.includes("delete")) return "danger";
    if (action.includes("reveal")) return "warning";
    if (action.includes("create") || action.includes("credential")) return "success";
    if (action.includes("test") || action.includes("health")) return "info";
    return "neutral";
}

function humanAction(action: string): string {
    return action
        .replace(/^provider\./, "")
        .split(/[._]/)
        .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
        .join(" ");
}

export default function AuditDrawer() {
    const [events, setEvents] = useState<AuditEvent[]>([]);
    const [loading, setLoading] = useState(true);
    const [active, setActive] = useState<AuditEvent | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            // pull a generous window and filter client-side to provider.* (the
            // /audit action filter is an exact match; provider.* is a family).
            const page = await getControlAudit({ limit: 200, channel: "control" });
            const rows = (page.events || []).filter((e) => (e.action || "").startsWith("provider."));
            setEvents(rows);
        } catch {
            setEvents([]);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const exportCsv = useCallback(() => {
        const header = ["timestamp", "actor", "action", "object_id", "ip"];
        const lines = events.map((e) =>
            [fmtDateTime(e.ts), e.actor, e.action, e.object_id || "", e.ip || ""]
                .map((v) => `"${String(v).replace(/"/g, '""')}"`)
                .join(","),
        );
        const csv = [header.join(","), ...lines].join("\n");
        const blob = new Blob([csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `integrations-audit-${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }, [events]);

    const head = useMemo(
        () => (
            <button className={textBtnCls} onClick={exportCsv} disabled={!events.length}>
                Export CSV
            </button>
        ),
        [events.length, exportCsv],
    );

    return (
        <Card title="Access &amp; change log" headContent={head}>
            {loading ? (
                <div className="flex items-center justify-center py-16">
                    <Spinner />
                </div>
            ) : events.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-s-subtle px-5 py-8 text-center text-body-2 text-t-secondary">
                    No provider activity yet — adds, key reveals and connection tests will appear here.
                </div>
            ) : (
                <div className="flex flex-col divide-y divide-s-subtle">
                    {events.map((e, i) => (
                        <button
                            key={`${e.epoch || e.ts || i}-${i}`}
                            onClick={() => setActive(e)}
                            className="flex items-center gap-3 py-3 text-left hover:bg-b-surface2/60 -mx-2 px-2 rounded-xl transition-colors"
                        >
                            <Badge variant={actionTone(e.action)}>{humanAction(e.action)}</Badge>
                            <span className="text-body-2 text-t-secondary truncate flex-1">
                                {e.actor}
                                {e.object_id ? ` · ${e.object_id.slice(0, 8)}` : ""}
                            </span>
                            <span className="text-caption text-t-tertiary tabular-nums shrink-0">
                                {fmtDateTime(e.ts)}
                            </span>
                            <Icon name="chevron" className="size-4 fill-t-tertiary -rotate-90 shrink-0" />
                        </button>
                    ))}
                </div>
            )}

            <Modal classWrapper="max-w-md" open={!!active} onClose={() => setActive(null)} isSlidePanel>
                {active && (
                    <>
                        <div className="text-h6 text-t-primary mb-1">{humanAction(active.action)}</div>
                        <p className="text-body-2 text-t-secondary mb-5">{fmtDateTime(active.ts)}</p>
                        <dl className="flex flex-col gap-3 text-body-2">
                            <Detail label="Actor" value={active.actor} />
                            {active.actor_role && <Detail label="Role" value={active.actor_role} />}
                            <Detail label="Action" value={active.action} mono />
                            {active.object_id && <Detail label="Provider" value={active.object_id} mono />}
                            {active.ip && <Detail label="IP" value={active.ip} mono />}
                            <Detail label="Channel" value={active.channel} />
                            {active.meta && Object.keys(active.meta).length > 0 && (
                                <Detail label="Meta" value={JSON.stringify(active.meta, null, 0)} mono />
                            )}
                        </dl>
                        <div className="mt-5 flex items-center gap-2 text-caption text-t-tertiary">
                            <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                            Append-only · plaintext keys are never logged.
                        </div>
                    </>
                )}
            </Modal>
        </Card>
    );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
    return (
        <div className="flex items-start gap-3">
            <dt className="text-caption text-t-tertiary w-20 shrink-0 pt-0.5">{label}</dt>
            <dd className={`text-t-primary break-all ${mono ? "font-mono text-caption" : ""}`}>{value}</dd>
        </div>
    );
}
