"use client";

// ============================================================================
// _health-table — the Health tab (design crazy-ui-security §B). A live table of
// every provider's circuit-state + latency, fed by /provider-registry/health
// (or /admin/health) polled every 30s (health is cheap-but-not-free, NOT 5s).
// An ok/recovering/down count strip sits above. Reuses the HealthBadge trust
// signal. Dormant-safe: a 404 surface shows a calm empty card.
// ============================================================================

import { useMemo } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import { useProviderHealth, type CircuitState, type HealthRow } from "@/lib/integrations";
import { HealthBadge } from "./_shared";

function circuitOf(r: HealthRow): CircuitState {
    if (r.circuit) return r.circuit;
    if (r.healthy === true) return "closed";
    if (r.healthy === false) return "open";
    if (r.status === "ok" || r.status === "healthy") return "closed";
    if (r.status === "open" || r.status === "down") return "open";
    return "unknown";
}

export default function HealthTable({ admin = false }: { admin?: boolean }) {
    const { rows, dormant } = useProviderHealth({ admin });

    const counts = useMemo(() => {
        let ok = 0,
            recovering = 0,
            down = 0;
        rows.forEach((r) => {
            const c = circuitOf(r);
            if (c === "closed") ok += 1;
            else if (c === "half_open") recovering += 1;
            else if (c === "open") down += 1;
        });
        return { ok, recovering, down };
    }, [rows]);

    if (dormant) {
        return (
            <Card title="Provider health">
                <div className="rounded-3xl border border-dashed border-s-subtle px-5 py-8 text-center text-body-2 text-t-secondary">
                    Health monitoring is off for this workspace.
                </div>
            </Card>
        );
    }

    return (
        <Card title="Provider health">
            <div className="px-1 mb-4 flex items-center gap-2 flex-wrap text-caption">
                <Badge variant="success" dot>
                    {counts.ok} healthy
                </Badge>
                <Badge variant="warning" dot>
                    {counts.recovering} recovering
                </Badge>
                <Badge variant="danger">{counts.down} down</Badge>
                <span className="text-t-tertiary ml-2 inline-flex items-center gap-1.5">
                    <Icon name="clock-1" className="size-3.5 fill-t-tertiary" />
                    refreshes every 30s
                </span>
            </div>

            {rows.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-s-subtle px-5 py-8 text-center text-body-2 text-t-secondary">
                    No providers to monitor yet.
                </div>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full text-body-2">
                        <thead>
                            <tr className="text-caption text-t-tertiary text-left">
                                <th className="font-normal py-2 pr-4">Provider</th>
                                <th className="font-normal py-2 pr-4">Status</th>
                                <th className="font-normal py-2 pr-4 tabular-nums">Latency</th>
                                <th className="font-normal py-2 pr-4">Detail</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-s-subtle">
                            {rows.map((r, i) => (
                                <tr key={r.provider_id || r.slug || i}>
                                    <td className="py-3 pr-4 text-t-primary">
                                        {r.display_name || r.slug || r.provider_id || "—"}
                                    </td>
                                    <td className="py-3 pr-4">
                                        <HealthBadge circuit={circuitOf(r)} />
                                    </td>
                                    <td className="py-3 pr-4 tabular-nums text-t-secondary">
                                        {r.latency_ms != null ? `${r.latency_ms}ms` : "—"}
                                    </td>
                                    <td className="py-3 pr-4 text-t-tertiary font-mono text-caption truncate max-w-[16rem]">
                                        {r.detail || "—"}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </Card>
    );
}
