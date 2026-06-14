"use client";

// Analytics view — omnichannel engagement at a glance. KPIs are derived from REAL
// session data (no fabricated deltas — there's no prior-period series). The
// out-of-box features the master plan approved (savings ticker, cost guards, CAPI
// signal closure) are surfaced as honest "what's coming" cards so the founder sees
// the roadmap without a fake number. Master-plan §6/§7. Core_2, zero raw hex.

import { useMemo } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import KpiCard from "@/components/KpiCard";
import Badge from "@/components/Badge";
import { useSessions, type CommSession } from "@/lib/communication";

function turnCount(s: CommSession): number {
    if (typeof s.turn_count === "number") return s.turn_count;
    return s.turns?.length || 0;
}

export default function AnalyticsView() {
    const { sessions, loading } = useSessions({});

    const stats = useMemo(() => {
        const total = sessions.length;
        const replied = sessions.filter((s) => turnCount(s) > 0).length;
        const hot = sessions.filter((s) => (s.interest ?? 0) >= 70).length;
        const msgs = sessions.reduce((a, s) => a + turnCount(s), 0);
        return { total, replied, hot, msgs, replyRate: total ? Math.round((replied / total) * 100) : 0 };
    }, [sessions]);

    return (
        <div className="flex flex-col gap-5">
            <div className="grid grid-cols-4 gap-4 max-3xl:grid-cols-2 max-md:grid-cols-1">
                <KpiCard
                    label="Conversations"
                    value={loading ? "—" : stats.total.toLocaleString()}
                    icon="chat"
                    tone="info"
                    sub="across all channels"
                />
                <KpiCard
                    label="Replied"
                    value={loading ? "—" : `${stats.replyRate}%`}
                    icon="reply"
                    tone="success"
                    sub={`${stats.replied} of ${stats.total} engaged`}
                    meter={stats.total ? stats.replied / stats.total : 0}
                />
                <KpiCard
                    label="Hot leads"
                    value={loading ? "—" : stats.hot.toLocaleString()}
                    icon="bell"
                    tone="warning"
                    sub="interest ≥ 70 / 100"
                />
                <KpiCard
                    label="Messages"
                    value={loading ? "—" : stats.msgs.toLocaleString()}
                    icon="send"
                    tone="neutral"
                    sub="total turns exchanged"
                />
            </div>

            <Card title="Channel mix">
                <div className="px-5 pb-5 max-lg:px-3">
                    <ChannelBar
                        label="Telegram"
                        icon="send"
                        value={sessions.filter((s) => (s.channel || "telegram") === "telegram").length}
                        total={Math.max(stats.total, 1)}
                        live
                    />
                    <ChannelBar label="WhatsApp" icon="chat-think" value={0} total={Math.max(stats.total, 1)} live />
                    <ChannelBar label="Email" icon="envelope" value={0} total={Math.max(stats.total, 1)} />
                    <ChannelBar label="SMS" icon="chat" value={0} total={Math.max(stats.total, 1)} />
                </div>
            </Card>

            <Card title="On the roadmap">
                <div className="px-5 pb-5 max-lg:px-3 grid grid-cols-3 gap-4 max-3xl:grid-cols-1">
                    <RoadmapCard
                        icon="usd-circle"
                        title="Honest savings ticker"
                        desc="Every send stores its cost and the next-cheapest deliverable channel — savings you can audit, not assert."
                        wave="Wave 3"
                    />
                    <RoadmapCard
                        icon="block"
                        title="Cost guards"
                        desc="Per-tenant daily budget, per-contact frequency cap, and a spend-anomaly alert that auto-throttles a runaway."
                        wave="Wave 3"
                    />
                    <RoadmapCard
                        icon="arrow-up-right"
                        title="Revenue-signal closure"
                        desc="Outcomes flow back to Meta / Google so the ads learn to hunt buyers who answer and pay — the moat."
                        wave="Wave 6"
                    />
                </div>
            </Card>
        </div>
    );
}

function ChannelBar({
    label,
    icon,
    value,
    total,
    live,
}: {
    label: string;
    icon: string;
    value: number;
    total: number;
    live?: boolean;
}) {
    const pct = Math.round((value / total) * 100);
    return (
        <div className="flex items-center gap-4 py-3">
            <span className="flex justify-center items-center size-9 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle shrink-0">
                <Icon name={icon} className="!size-4 fill-t-secondary" />
            </span>
            <div className="grow min-w-0">
                <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-button text-t-primary">{label}</span>
                    {!live && <Badge variant="neutral">Soon</Badge>}
                    <span className="ml-auto text-caption text-t-secondary tabular-nums">{value}</span>
                </div>
                <div className="meter">
                    <div
                        className="meter-fill"
                        style={{ width: `${pct}%`, background: "var(--primary-01)" }}
                    />
                </div>
            </div>
        </div>
    );
}

function RoadmapCard({ icon, title, desc, wave }: { icon: string; title: string; desc: string; wave: string }) {
    return (
        <div className="flex flex-col gap-2.5 p-4 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
            <div className="flex items-center justify-between">
                <span className="flex justify-center items-center size-9 rounded-2xl bg-primary-01/10">
                    <Icon name={icon} className="!size-4.5 fill-primary-01" />
                </span>
                <span className="text-caption text-t-tertiary px-2 py-0.5 rounded-full bg-b-surface1 ring-1 ring-s-subtle">
                    {wave}
                </span>
            </div>
            <div className="text-button text-t-primary">{title}</div>
            <p className="text-body-2 text-t-secondary">{desc}</p>
        </div>
    );
}
