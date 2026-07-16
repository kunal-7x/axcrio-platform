"use client";

import { useQuery } from "@tanstack/react-query";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import { getOverview, type Overview as OverviewT } from "../client";
import { SourceIcon, fmtRelative } from "../_ui";

export default function Overview({ onAddSource }: { onAddSource: () => void }) {
    const q = useQuery({ queryKey: ["auto-lead", "overview"], queryFn: getOverview, refetchInterval: 8000 });
    const o: OverviewT | undefined = q.data;
    const loading = q.isLoading;

    if (!loading && o && o.total_sources === 0) {
        return (
            <Card title="Auto Lead">
                <div className="grid place-items-center py-16 px-6 text-center max-md:py-12">
                    <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-primary-01/12">
                        <Icon name="promote" className="fill-primary-01" />
                    </span>
                    <div className="text-h5 mb-2">Capture every lead, automatically</div>
                    <div className="max-w-lg text-body-2 text-t-secondary">
                        Connect WhatsApp, email, Meta &amp; Google ads, your website, Apollo or any tool —
                        Auto Lead watches them in real time, validates each new lead, and routes it
                        straight to calling &amp; follow-up. No manual exports, ever.
                    </div>
                    <Button isBlack className="mt-6" onClick={onAddSource}>
                        Connect your first source
                    </Button>
                </div>
            </Card>
        );
    }

    return (
        <div className="flex flex-col gap-3">
            <Card title="Overview">
                <div className="flex gap-8 px-5 pb-5 pt-1 max-lg:gap-6 max-lg:px-3 max-lg:overflow-auto max-lg:scrollbar-none">
                    <Metric icon="promote" title="Active sources" value={loading ? "—" : o?.active_sources ?? 0} accent />
                    <Metric icon="profile" title="Leads today" value={loading ? "—" : o?.accepted_today ?? 0}
                        sub={loading ? undefined : `${o?.rejected_today ?? 0} rejected today`} />
                    <Metric icon="check-circle" title="Imported (all-time)" value={loading ? "—" : o?.total_accepted ?? 0} />
                    <Metric icon="block" title="Rejected" value={loading ? "—" : o?.total_rejected ?? 0}
                        sub={loading ? undefined : "invalid / duplicate"} />
                </div>
            </Card>

            <div className="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
                {/* by source */}
                <Card title="By source">
                    {(o?.by_source ?? []).length === 0 ? (
                        <div className="px-5 pb-6 text-body-2 text-t-tertiary max-lg:px-3">No sources yet.</div>
                    ) : (
                        <div className="flex flex-col px-2 pb-2">
                            {(o?.by_source ?? []).map((s) => (
                                <div key={s.id} className="flex items-center gap-3 px-3 py-2.5">
                                    <SourceIcon icon={s.icon} type={s.type} size={10} />
                                    <span className="truncate text-body-2 text-t-primary flex-1">{s.name}</span>
                                    {!s.enabled && <Badge variant="neutral">Paused</Badge>}
                                    <span className="text-button text-t-primary tabular-nums">{s.accepted}</span>
                                    <span className="text-caption text-t-tertiary">/ {s.ingested}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </Card>

                {/* recent */}
                <Card title="Latest leads">
                    {(o?.recent ?? []).length === 0 ? (
                        <div className="px-5 pb-6 text-body-2 text-t-tertiary max-lg:px-3">Nothing yet.</div>
                    ) : (
                        <div className="flex flex-col px-2 pb-2">
                            {(o?.recent ?? []).map((e) => (
                                <div key={e.id} className="flex items-center gap-3 px-3 py-2.5">
                                    <span className="min-w-0 flex-1">
                                        <span className="block truncate text-body-2 text-t-primary">
                                            {e.name || e.phone || e.email || "Unknown"}
                                        </span>
                                        <span className="block truncate text-caption text-t-tertiary">{e.source_name}</span>
                                    </span>
                                    {e.accepted ? (
                                        <Badge variant="success" dot>
                                            Imported
                                        </Badge>
                                    ) : (
                                        <Badge variant="danger">{e.reason}</Badge>
                                    )}
                                    <span className="text-caption text-t-tertiary shrink-0 w-14 text-right">{fmtRelative(e.at)}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </Card>
            </div>
        </div>
    );
}

function Metric({
    icon,
    title,
    value,
    sub,
    accent,
}: {
    icon: string;
    title: string;
    value: React.ReactNode;
    sub?: React.ReactNode;
    accent?: boolean;
}) {
    return (
        <div className="flex-1 min-w-40 pr-8 border-r border-s-subtle last:border-r-0 last:pr-0 max-lg:shrink-0">
            <div className={`flex items-center justify-center size-12 mb-6 rounded-full ${accent ? "bg-primary-01/12" : "bg-b-surface1"}`}>
                <Icon className={accent ? "fill-primary-01" : "fill-t-primary"} name={icon} />
            </div>
            <div className="text-sub-title-1 text-t-secondary mb-2">{title}</div>
            <div className="text-h3 tabular-nums">{value}</div>
            {sub && <div className="mt-2 text-body-2 text-t-tertiary">{sub}</div>}
        </div>
    );
}
