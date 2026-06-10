"use client";

// Workflow Studio — the visual automation CANVAS (the connective tissue).
//
// A native (NOT n8n — fair-code licence landmine for a reseller) visual builder:
// Triggers -> Conditions -> AI-Agent/Action/Integration steps -> with Budget /
// Approval / Delay / Data / Error nodes, wired into a durable, multi-tenant,
// crash-safe automation that runs on the Hatchet spine with HARD, code-enforced
// safety rails. This page is the STUDIO surface for that engine.
//
// The backend (the durable interpreter + the 6 Postgres tables + the additive
// /workflows router) is DEFINED-NOT-MOUNTED today — it ships behind a deferred,
// un-applied wiring diff. So the graceful "not configured / coming soon" path is
// the PRIMARY state: every read degrades to a premium dormant view, never an
// error wall, and the canvas renders a real sample / template definition as an
// honest preview of the studio. Built entirely on the in-app "Signal" component
// language (Layout / PageHeader / Card / Badge / Icon / Button) + the verified
// globals.css utilities. Edits only this route's own files.

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import { useMe, canWrite } from "@/lib/auth";
import WorkflowCanvas from "./_canvas";
import {
    getWfStatus,
    getWorkflows,
    getWfRuns,
    getWfTemplates,
    instantiateTemplate,
    NODE_GROUPS,
    nodeMeta,
    SAMPLE_WORKFLOW,
    TEMPLATES,
    fmtDate,
    runStatusVariant,
    type ReadResult,
    type WfStatus,
    type WfDefinition,
    type WfRun,
    type WfTemplate,
} from "./_lib";

type Toast = { msg: string; type: "success" | "error" };
type TabKey = "studio" | "runs" | "templates";

/* ----------------------------------------------------------- shared bits */

// The premium "coming soon / not configured" panel — the PRIMARY state until the
// engine is mounted and creds land. Distinct, on-brand, never an error.
function DormantPanel({
    icon = "cube",
    title,
    sub,
    children,
}: {
    icon?: string;
    title: string;
    sub: string;
    children?: React.ReactNode;
}) {
    return (
        <div className="state-block">
            <span className="state-glyph">
                <Icon name={icon} className="fill-inherit" />
            </span>
            <div className="state-title">{title}</div>
            <div className="state-sub max-w-md mx-auto">{sub}</div>
            {children}
        </div>
    );
}

function HeroStat({
    label,
    glyph,
    glyphClass,
    value,
    foot,
    accent,
    delay = 0,
    loading,
}: {
    label: string;
    glyph: string;
    glyphClass?: string;
    value: React.ReactNode;
    foot?: React.ReactNode;
    accent?: string;
    delay?: number;
    loading?: boolean;
}) {
    return (
        <div className="kpi rise-in group" style={delay ? { animationDelay: `${delay}ms` } : undefined}>
            {accent && (
                <span
                    aria-hidden
                    className="pointer-events-none absolute -top-16 -right-16 size-40 rounded-full opacity-[0.13] blur-2xl transition-opacity duration-500 group-hover:opacity-20"
                    style={{ background: accent }}
                />
            )}
            <div className="flex items-start justify-between gap-3">
                <div className="kpi-label">
                    <span className={`kpi-glyph ${glyphClass || ""}`}>
                        <Icon name={glyph} className="fill-inherit" />
                    </span>
                    {label}
                </div>
            </div>
            {loading ? (
                <div className="skeleton h-9 w-28 mt-1" />
            ) : (
                <div className="kpi-value relative z-1 !text-h4">{value}</div>
            )}
            {foot && <div className="kpi-foot relative z-1">{foot}</div>}
        </div>
    );
}

/* ============================================================== the page */

export default function WorkflowStudioPage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [tab, setTab] = useState<TabKey>("studio");
    const [toast, setToast] = useState<Toast | null>(null);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4200);
    };

    const [status, setStatus] = useState<ReadResult<WfStatus> | null>(null);
    const [statusLoading, setStatusLoading] = useState(true);
    const loadStatus = useCallback(() => {
        setStatusLoading(true);
        getWfStatus()
            .then(setStatus)
            .finally(() => setStatusLoading(false));
    }, []);

    const [workflows, setWorkflows] = useState<ReadResult<{ workflows: WfDefinition[] }> | null>(null);
    const [wfLoading, setWfLoading] = useState(true);
    const loadWorkflows = useCallback(() => {
        setWfLoading(true);
        getWorkflows()
            .then(setWorkflows)
            .finally(() => setWfLoading(false));
    }, []);

    const [runs, setRuns] = useState<ReadResult<{ runs: WfRun[] }> | null>(null);
    const [runsLoading, setRunsLoading] = useState(true);
    const loadRuns = useCallback(() => {
        setRunsLoading(true);
        getWfRuns()
            .then(setRuns)
            .finally(() => setRunsLoading(false));
    }, []);

    const [templates, setTemplates] = useState<ReadResult<{ templates: WfTemplate[] }> | null>(null);
    const loadTemplates = useCallback(() => {
        getWfTemplates().then(setTemplates);
    }, []);

    useEffect(() => {
        loadStatus();
        loadWorkflows();
        loadRuns();
        loadTemplates();
    }, [loadStatus, loadWorkflows, loadRuns, loadTemplates]);

    const st = status?.kind === "ok" ? status.data : null;
    const wfRows = workflows?.kind === "ok" ? workflows.data.workflows : [];
    const runRows = runs?.kind === "ok" ? runs.data.runs : [];

    // Live templates if the API ever serves them; else the shipped library.
    const tplRows =
        templates?.kind === "ok" && templates.data.templates.length > 0
            ? templates.data.templates
            : TEMPLATES;

    // The whole module reads as dormant when nothing is mounted server-side.
    const moduleDormant =
        status?.kind === "dormant" && workflows?.kind === "dormant" && runs?.kind === "dormant";

    const engineLive = !!st && st.enabled && st.engine === "configured" && st.store === "configured";

    const awaiting = runRows.filter((r) => r.status === "awaiting_approval").length;

    const TABS: { key: TabKey; label: string; icon: string; badge?: number }[] = [
        { key: "studio", label: "Canvas Studio", icon: "dashboard" },
        { key: "runs", label: "Runs", icon: "clock", badge: awaiting },
        { key: "templates", label: "Templates", icon: "layers" },
    ];

    const refreshing = statusLoading || wfLoading || runsLoading;

    return (
        <Layout title="Workflow Studio">
            <PageHeader
                eyebrow="Automation"
                title="Workflow Studio"
                subtitle="Compose your AI workforce into governed, money-safe automations on a visual canvas — Triggers, Conditions, AI-Agent and Action steps, gated by hard Budget and Approval nodes with an immutable audit on every step."
                actions={
                    <button
                        onClick={() => {
                            loadStatus();
                            loadWorkflows();
                            loadRuns();
                        }}
                        className="inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50"
                        disabled={refreshing}
                    >
                        <Icon
                            name="clock"
                            className={`size-4 fill-current ${refreshing ? "animate-spin" : ""}`}
                        />
                        Refresh
                    </button>
                }
            />

            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button
                        onClick={() => setToast(null)}
                        className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none"
                    >
                        ×
                    </button>
                </div>
            )}

            {/* Tab strip — pill rail matching the AI-Manager / billing premium tabs */}
            <div className="flex items-center gap-1 mb-5 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle w-fit max-w-full overflow-x-auto scrollbar-none">
                {TABS.map((t) => {
                    const active = tab === t.key;
                    return (
                        <button
                            key={t.key}
                            onClick={() => setTab(t.key)}
                            className={`shrink-0 inline-flex items-center gap-2 h-9 px-3.5 rounded-full text-button transition-colors ${
                                active
                                    ? "bg-b-surface1 text-t-primary shadow-widget dark:bg-shade-04"
                                    : "text-t-secondary hover:text-t-primary"
                            }`}
                        >
                            <Icon
                                name={t.icon}
                                className={`size-4 ${active ? "fill-t-primary" : "fill-t-secondary"}`}
                            />
                            {t.label}
                            {!!t.badge && t.badge > 0 && (
                                <span className="pill pill-warning !px-1.5 !py-0 text-caption">{t.badge}</span>
                            )}
                        </button>
                    );
                })}
            </div>

            {tab === "studio" && (
                <StudioTab
                    status={status}
                    st={st}
                    loading={statusLoading}
                    engineLive={engineLive}
                    moduleDormant={moduleDormant}
                    workflowCount={wfRows.length}
                    publishedCount={wfRows.filter((w) => w.status === "published").length}
                    runCount={runRows.length}
                />
            )}

            {tab === "runs" && (
                <RunsTab result={runs} rows={runRows} loading={runsLoading} engineLive={engineLive} />
            )}

            {tab === "templates" && (
                <TemplatesTab
                    rows={tplRows}
                    writable={writable}
                    engineLive={engineLive}
                    toast={showToast}
                />
            )}
        </Layout>
    );
}

/* ===================================================== TAB 1 — Canvas Studio */

function StudioTab({
    status,
    st,
    loading,
    engineLive,
    moduleDormant,
    workflowCount,
    publishedCount,
    runCount,
}: {
    status: ReadResult<WfStatus> | null;
    st: WfStatus | null;
    loading: boolean;
    engineLive: boolean;
    moduleDormant: boolean;
    workflowCount: number;
    publishedCount: number;
    runCount: number;
}) {
    return (
        <div className="space-y-3">
            {/* Hero KPI strip — real config signals + honest counts only */}
            <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <HeroStat
                    label="Engine"
                    glyph="cube"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    loading={loading && !st}
                    value={engineLive ? "Live" : "Coming soon"}
                    foot={engineLive ? "Durable on the Hatchet spine" : "Awaiting durable-engine provisioning"}
                />
                <HeroStat
                    label="Workflows"
                    glyph="dashboard"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={60}
                    loading={loading && !status}
                    value={String(workflowCount)}
                    foot={
                        publishedCount > 0
                            ? `${publishedCount} published`
                            : workflowCount === 0
                            ? "None built yet"
                            : "All drafts"
                    }
                />
                <HeroStat
                    label="Safety Rails"
                    glyph="lock"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    delay={120}
                    loading={loading && !st}
                    value="Budget + Approval"
                    foot="No spend without a cap + PIN step-up"
                />
                <HeroStat
                    label="Runs"
                    glyph="clock"
                    glyphClass="fill-primary-05"
                    accent="var(--primary-05)"
                    delay={180}
                    loading={loading && !status}
                    value={String(runCount)}
                    foot={runCount === 0 ? "No runs recorded yet" : "Durable, replayable executions"}
                />
            </div>

            {/* The honest "what this is / coming soon" explainer */}
            {(moduleDormant || !engineLive) && (
                <div className="card overflow-hidden">
                    <div className="relative p-6 max-lg:p-4">
                        <span
                            aria-hidden
                            className="pointer-events-none absolute -top-20 -right-16 size-56 rounded-full opacity-[0.10] blur-3xl"
                            style={{ background: "var(--primary-01)" }}
                        />
                        <div className="relative flex items-start gap-4 max-sm:flex-col">
                            <span className="grid place-items-center size-12 shrink-0 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                                <Icon name="dashboard" className="size-6 fill-inherit" />
                            </span>
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h3 className="text-h6 text-t-primary">The canvas is in preview</h3>
                                    <Badge variant="info" dot>
                                        In setup
                                    </Badge>
                                </div>
                                <p className="text-body-2 text-t-secondary mt-2 max-w-2xl">
                                    The studio is a native engine — not n8n — so it can run the safety nodes
                                    no off-the-shelf tool can: a Budget node holds a real wallet reservation,
                                    an Approval node demands a PIN-verified human step-up, and every node writes
                                    an immutable audit row. The canvas below previews a real workflow; building,
                                    publishing and running light up once the durable engine, the workflow tables
                                    and the tool registry are provisioned on the server.
                                </p>
                                <div className="mt-4 grid grid-cols-3 gap-3 max-md:grid-cols-1">
                                    <FlowStep n={1} icon="feather" title="Compose" text="Drag Triggers, AI-Agent and Action nodes onto the canvas and wire the path." />
                                    <FlowStep n={2} icon="lock" title="Govern" text="Publish is refused unless every money node is dominated by a Budget — and an Approval over cap." />
                                    <FlowStep n={3} icon="cube" title="Run" text="A single durable interpreter on Hatchet executes the graph, crash-safe and replayable." />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* The canvas + node palette — the premium centerpiece */}
            <div className="flex gap-3 max-xl:flex-col">
                <div className="flex-1 min-w-0">
                    <Card
                        title="Hot-lead 5-touch nurture"
                        headContent={
                            <span className="ml-3 inline-flex items-center gap-2 max-md:hidden">
                                <Badge variant="info">{SAMPLE_WORKFLOW.industry_pack}</Badge>
                                <span className="text-caption text-t-tertiary">
                                    v{SAMPLE_WORKFLOW.version} · preview
                                </span>
                            </span>
                        }
                    >
                        <div className="px-3 pb-3 max-lg:px-2">
                            <WorkflowCanvas def={SAMPLE_WORKFLOW} className="h-[460px] max-sm:h-[360px]" />
                            {/* Guard ribbon — the workflow-level hard safety defaults */}
                            <div className="mt-3 flex flex-wrap items-center gap-2">
                                <GuardChip icon="filters" label={`Max ${SAMPLE_WORKFLOW.guards.max_actions} actions`} />
                                <GuardChip icon="clock" label={SAMPLE_WORKFLOW.guards.calling_window} />
                                {SAMPLE_WORKFLOW.guards.respect_dnd && <GuardChip icon="block" label="Respects DND" />}
                                {SAMPLE_WORKFLOW.guards.respect_consent && (
                                    <GuardChip icon="check-circle" label="Consent-gated" />
                                )}
                                <GuardChip icon="lock" label="Audited per step" />
                            </div>
                        </div>
                    </Card>
                </div>

                {/* Node palette rail */}
                <div className="w-72 max-xl:w-full shrink-0">
                    <Card
                        title="Node Palette"
                        headContent={
                            <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary max-md:hidden">
                                <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                                10 types
                            </span>
                        }
                    >
                        <div className="px-3 pb-4 max-lg:px-2 space-y-4">
                            {NODE_GROUPS.map((grp) => (
                                <div key={grp.group}>
                                    <div className="text-overline text-t-tertiary px-1 mb-2">{grp.group}</div>
                                    <div className="space-y-1.5">
                                        {grp.types.map((t) => {
                                            const m = nodeMeta(t);
                                            return (
                                                <div
                                                    key={t}
                                                    className="lift group flex items-center gap-2.5 p-2.5 rounded-xl bg-b-surface2 ring-1 ring-s-subtle ring-inset cursor-grab dark:bg-shade-04/30"
                                                    title={m.blurb}
                                                >
                                                    <span
                                                        className="grid place-items-center size-8 shrink-0 rounded-lg bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04"
                                                        style={{ fill: m.accent }}
                                                    >
                                                        <Icon name={m.icon} className="size-4 fill-inherit" />
                                                    </span>
                                                    <div className="min-w-0 flex-1">
                                                        <div className="text-body-2 text-t-primary truncate">
                                                            {m.label}
                                                        </div>
                                                        <div className="text-caption text-t-tertiary truncate">
                                                            {m.gate}
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </Card>
                </div>
            </div>

            {/* Configuration board — every dormant dependency surfaced honestly */}
            <Card
                title="Engine & Dependencies"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary max-md:hidden">
                        <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                        Server-side · dormant until provisioned
                    </span>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {loading && !st ? (
                        <div className="space-y-3">
                            {[...Array(6)].map((_, i) => (
                                <div key={i} className="flex items-center justify-between">
                                    <div className="skeleton h-4 w-44" />
                                    <div className="skeleton h-5 w-24" />
                                </div>
                            ))}
                        </div>
                    ) : status?.kind === "error" ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="info" className="fill-inherit" />
                            </span>
                            <div className="state-title">Couldn&apos;t load engine status</div>
                            <div className="state-sub">{status.message}</div>
                        </div>
                    ) : (
                        <div className="divide-y divide-s-subtle">
                            <ConfigRow icon="cube" label="Durable engine" hint="Hatchet worker-spine runs the interpreter">
                                <ConfigPill on={st?.engine === "configured"} />
                            </ConfigRow>
                            <ConfigRow icon="layers" label="Workflow store" hint="Postgres + RLS — defs, versions, runs">
                                <ConfigPill on={st?.store === "configured"} />
                            </ConfigRow>
                            <ConfigRow icon="wallet" label="Wallet ledger" hint="Backs the Budget node's run-scoped hold">
                                <ConfigPill on={st?.wallet === "configured"} />
                            </ConfigRow>
                            <ConfigRow icon="lock" label="Action firewall" hint="PIN step-up for the Approval node">
                                <ConfigPill on={st?.firewall === "configured"} />
                            </ConfigRow>
                            <ConfigRow icon="list" label="Audit log" hint="Immutable row on every node + gate">
                                <ConfigPill on={st?.audit === "configured"} />
                            </ConfigRow>
                            <ConfigRow icon="feather" label="Tool registry" hint="AI-Manager tools for Action / AI-Agent nodes">
                                <ConfigPill on={st?.registry === "configured"} />
                            </ConfigRow>
                        </div>
                    )}
                </div>
            </Card>
        </div>
    );
}

function FlowStep({ n, icon, title, text }: { n: number; icon: string; title: string; text: string }) {
    return (
        <div className="relative p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
            <div className="flex items-center gap-2 mb-1.5">
                <span className="grid place-items-center size-7 rounded-full bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                    <Icon name={icon} className="size-4 fill-inherit" />
                </span>
                <span className="text-caption text-t-tertiary tabular-nums">Step {n}</span>
            </div>
            <div className="text-sub-title-2 text-t-primary">{title}</div>
            <div className="text-caption text-t-secondary mt-1">{text}</div>
        </div>
    );
}

function GuardChip({ icon, label }: { icon: string; label: string }) {
    return (
        <span className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-caption text-t-secondary">
            <Icon name={icon} className="size-3.5 fill-t-tertiary" />
            {label}
        </span>
    );
}

function ConfigPill({ on }: { on?: boolean }) {
    return on ? (
        <Badge variant="success" dot>
            Configured
        </Badge>
    ) : (
        <Badge variant="neutral">Not configured</Badge>
    );
}

function ConfigRow({
    icon,
    label,
    hint,
    children,
}: {
    icon: string;
    label: string;
    hint: string;
    children: React.ReactNode;
}) {
    return (
        <div className="flex items-center justify-between gap-4 py-3.5">
            <div className="flex items-center gap-3 min-w-0">
                <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                    <Icon name={icon} className="size-4.5 fill-inherit" />
                </span>
                <div className="min-w-0">
                    <div className="text-body-2 text-t-primary truncate">{label}</div>
                    <div className="text-caption text-t-tertiary truncate">{hint}</div>
                </div>
            </div>
            <div className="shrink-0">{children}</div>
        </div>
    );
}

/* ===================================================== TAB 2 — Runs */

function RunsTab({
    result,
    rows,
    loading,
    engineLive,
}: {
    result: ReadResult<{ runs: WfRun[] }> | null;
    rows: WfRun[];
    loading: boolean;
    engineLive: boolean;
}) {
    const dormant = result?.kind === "dormant";
    const error = result?.kind === "error" ? result.message : "";

    return (
        <Card
            title="Workflow Runs"
            headContent={
                <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary max-md:hidden">
                    <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                    Replayable · audited
                </span>
            }
        >
            {error && (
                <div className="mx-5 mb-3 toast toast-error">
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {error}
                    </span>
                </div>
            )}
            <div className="overflow-x-auto">
                <table className="data-table">
                    <thead>
                        <tr>
                            <th>Workflow</th>
                            <th>Trigger</th>
                            <th>Started</th>
                            <th className="text-right">Steps</th>
                            <th className="text-right">Spend</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            [...Array(3)].map((_, i) => (
                                <tr key={i}>
                                    {[...Array(6)].map((__, j) => (
                                        <td key={j}>
                                            <div className="skeleton h-4 w-20" />
                                        </td>
                                    ))}
                                </tr>
                            ))
                        ) : dormant || !engineLive ? (
                            <tr>
                                <td colSpan={6}>
                                    <DormantPanel
                                        icon="clock"
                                        title="No runs yet"
                                        sub="Every execution lands here as a durable, replayable run — which nodes fired, the spend against each Budget hold, where an Approval paused it, and the immutable audit trail. Runs appear once the engine is live and a published workflow triggers."
                                    />
                                </td>
                            </tr>
                        ) : rows.length === 0 ? (
                            <tr>
                                <td colSpan={6}>
                                    <DormantPanel
                                        icon="dashboard"
                                        title="No runs recorded"
                                        sub="Publish a workflow and trigger it — manually, on a schedule, or from a lifecycle event — and its run history will appear here."
                                    />
                                </td>
                            </tr>
                        ) : (
                            rows.map((r) => (
                                <tr key={r.run_id}>
                                    <td className="font-medium text-t-primary">{r.workflow_name || r.workflow_id}</td>
                                    <td className="text-t-secondary">{r.trigger_kind || "—"}</td>
                                    <td className="text-t-secondary whitespace-nowrap">{fmtDate(r.started_at)}</td>
                                    <td className="text-t-secondary td-num text-right">
                                        {typeof r.steps === "number" ? r.steps : "—"}
                                    </td>
                                    <td className="text-t-secondary td-num text-right">
                                        {typeof r.spend_minor === "number"
                                            ? `₹${(r.spend_minor / 100).toLocaleString()}`
                                            : "—"}
                                    </td>
                                    <td>
                                        <Badge variant={runStatusVariant(r.status)} dot={r.status !== "completed"}>
                                            {r.status.replace(/_/g, " ")}
                                        </Badge>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </Card>
    );
}

/* ===================================================== TAB 3 — Templates */

function TemplatesTab({
    rows,
    writable,
    engineLive,
    toast,
}: {
    rows: WfTemplate[];
    writable: boolean;
    engineLive: boolean;
    toast: (msg: string, type?: "success" | "error") => void;
}) {
    const [busyId, setBusyId] = useState<string>("");
    const [preview, setPreview] = useState<WfTemplate | null>(null);

    async function useTemplate(t: WfTemplate) {
        setBusyId(t.template_id);
        try {
            await instantiateTemplate(t.template_id);
            toast(`"${t.name}" added to your workflows as a draft`);
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't use this template", "error");
        } finally {
            setBusyId("");
        }
    }

    return (
        <div className="space-y-3">
            <div className="card overflow-hidden">
                <div className="relative flex items-center gap-3 p-4 max-lg:p-3">
                    <span className="grid place-items-center size-10 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                        <Icon name="layers" className="size-5 fill-inherit" />
                    </span>
                    <div className="min-w-0">
                        <div className="text-body-1 text-t-primary">Industry-pack templates</div>
                        <div className="text-caption text-t-secondary">
                            Start from a proven, pre-governed automation — every money node already wrapped in a
                            Budget and (over cap) an Approval. Clone one into a draft, then tune it on the canvas.
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-3 max-xl:grid-cols-2 max-md:grid-cols-1">
                {rows.map((t) => (
                    <div
                        key={t.template_id}
                        className="card lift !mb-0 flex flex-col overflow-hidden cursor-pointer"
                        onClick={() => setPreview(t)}
                    >
                        <div className="p-4 flex-1">
                            <div className="flex items-start justify-between gap-3">
                                <span className="grid place-items-center size-11 shrink-0 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                                    <Icon name={t.icon} className="size-5 fill-inherit" />
                                </span>
                                <Badge variant="neutral">{t.industry_pack}</Badge>
                            </div>
                            <div className="text-sub-title-1 text-t-primary mt-3">{t.name}</div>
                            <p className="text-caption text-t-secondary mt-1.5 line-clamp-3">{t.summary}</p>
                            <div className="flex flex-wrap items-center gap-1.5 mt-3">
                                <span className="inline-flex items-center gap-1 text-caption text-t-tertiary">
                                    <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                                    {t.node_count} nodes
                                </span>
                                {t.has_money && <Badge variant="success" dot>budgeted</Badge>}
                                {t.has_approval && <Badge variant="warning">approval</Badge>}
                            </div>
                        </div>
                        <div className="flex items-center gap-2 px-4 py-3 border-t border-s-subtle">
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setPreview(t);
                                }}
                                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full border border-s-subtle text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary"
                            >
                                <Icon name="dashboard" className="size-3.5 fill-current" />
                                Preview
                            </button>
                            {writable && (
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        useTemplate(t);
                                    }}
                                    disabled={busyId === t.template_id}
                                    className="ml-auto inline-flex items-center gap-1.5 h-8 px-3 rounded-full border border-transparent bg-primary-01/12 text-primary-01 fill-primary-01 text-button transition-colors hover:bg-primary-01/20 disabled:opacity-50"
                                    title={engineLive ? "Clone into a draft" : "Available once the engine is live"}
                                >
                                    <Icon name="plus" className="size-3.5 fill-current" />
                                    {busyId === t.template_id ? "Adding…" : "Use template"}
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            {/* Preview modal — renders the template's real graph on the canvas */}
            {preview && (
                <div
                    className="fixed inset-0 z-50 bg-shade-01/60 backdrop-blur-sm flex items-center justify-center p-4 max-sm:p-0"
                    onClick={() => setPreview(null)}
                >
                    <div
                        className="surface w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col p-0"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="flex items-center gap-3 p-4 border-b border-s-subtle">
                            <span className="grid place-items-center size-10 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                                <Icon name={preview.icon} className="size-5 fill-inherit" />
                            </span>
                            <div className="min-w-0 flex-1">
                                <div className="text-h6 text-t-primary truncate">{preview.name}</div>
                                <div className="text-caption text-t-tertiary">
                                    {preview.industry_pack} · {preview.node_count} nodes
                                </div>
                            </div>
                            {writable && (
                                <Button
                                    isBlack
                                    onClick={() => {
                                        useTemplate(preview);
                                        setPreview(null);
                                    }}
                                >
                                    Use template
                                </Button>
                            )}
                            <button
                                onClick={() => setPreview(null)}
                                className="grid place-items-center size-9 rounded-full text-t-tertiary hover:text-t-primary hover:bg-b-surface2"
                            >
                                <Icon name="close" className="size-4 fill-current" />
                            </button>
                        </div>
                        <div className="p-4 overflow-auto">
                            <WorkflowCanvas def={preview.definition} className="h-[440px] max-sm:h-[320px]" />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
