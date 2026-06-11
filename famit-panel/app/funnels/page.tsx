"use client";

// Funnels — the multi-step conversion-funnel builder (roadmap P9 / row 79).
//
// A FUNNEL connects ad -> landing -> lead -> call -> WhatsApp -> booking ->
// payment -> review as a single definition OVER the existing workflow engine,
// with per-STAGE conversion analytics. It is NOT a new engine: a funnel COMPILES
// DOWN to the workflow DSL and DELEGATES publish/run to the durable interpreter,
// which owns every safety gate (budget dominators, approval, immutable audit,
// idempotent replay, wallet/firewall). The money stage (ad spend) is auto-gated.
//
// The backend router is DEFINED-NOT-MOUNTED today (it needs a token-deriving
// build_router before it can mount safely), so the graceful "not configured /
// coming soon" path is the PRIMARY state — every read degrades to a premium
// dormant view rather than an error wall. The stage pipeline + starter templates
// are rendered from STATIC, cred-free knowledge so the dormant state is rich and
// educational, with live funnels overlaid when the backend lights up.
//
// Built entirely on the reference Core_2 kit primitives (Layout / Card / Tabs /
// Table / TableRow / Badge / Button / Icon) — single Layout title, no PageHeader.
// Edits only this route's own files.

import { useCallback, useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Button from "@/components/Button";
import Tabs from "@/components/Tabs";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import { useMe, canWrite } from "@/lib/auth";
import {
    getFunnelStatus,
    getFunnels,
    instantiateTemplate,
    publishFunnel,
    runFunnel,
    STAGES,
    STARTER_TEMPLATES,
    stageMeta,
    rowStages,
    fmtDate,
    type ReadResult,
    type FunnelStatus,
    type FunnelRow,
    type StageMeta,
    type FunnelTemplate,
} from "./_lib";

/* ----------------------------------------------------------------- helpers */

type Toast = { msg: string; type: "success" | "error" };
type TabKey = "overview" | "templates" | "funnels";

const FUNNEL_TABS = [
    { id: 1, name: "Overview", key: "overview" as TabKey },
    { id: 2, name: "Starter Templates", key: "templates" as TabKey },
    { id: 3, name: "My Funnels", key: "funnels" as TabKey },
];

function statusVariant(s: string): BadgeVariant {
    if (s === "published") return "success";
    if (s === "draft") return "warning";
    if (s === "archived") return "neutral";
    return "neutral";
}

function stageRiskTag(s: StageMeta): { label: string; variant: BadgeVariant } | null {
    if (s.placeholder) return { label: "Coming soon", variant: "neutral" };
    if (s.money) return { label: "Money · gated", variant: "danger" };
    if (s.bulk) return { label: "Bulk · gated", variant: "warning" };
    return null;
}

/* ------------------------------------------------------------ empty / dormant */

// The premium "coming soon / not configured" panel — the PRIMARY state until the
// backend router is mounted. Distinct, on-brand, never an error.
function DormantPanel({
    icon = "filters",
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
        <div className="py-16 text-center max-md:py-12">
            <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                <Icon name={icon} className="fill-t-tertiary" />
            </span>
            <div className="text-h6 mb-1">{title}</div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                {sub}
            </div>
            {children}
        </div>
    );
}

/* ============================================================== the page */

export default function FunnelsPage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [tabOpt, setTabOpt] = useState(FUNNEL_TABS[0]);
    const tab = tabOpt.key;
    const setTab = (key: TabKey) =>
        setTabOpt(FUNNEL_TABS.find((t) => t.key === key) ?? FUNNEL_TABS[0]);
    const [toast, setToast] = useState<Toast | null>(null);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4200);
    };

    // ---- status ----
    const [status, setStatus] = useState<ReadResult<FunnelStatus> | null>(null);
    const [statusLoading, setStatusLoading] = useState(true);

    const loadStatus = useCallback(() => {
        setStatusLoading(true);
        getFunnelStatus()
            .then(setStatus)
            .finally(() => setStatusLoading(false));
    }, []);

    // ---- funnels list ----
    const [funnels, setFunnels] = useState<ReadResult<{ funnels: FunnelRow[] }> | null>(null);
    const [funnelsLoading, setFunnelsLoading] = useState(true);

    const loadFunnels = useCallback(() => {
        setFunnelsLoading(true);
        getFunnels()
            .then(setFunnels)
            .finally(() => setFunnelsLoading(false));
    }, []);

    useEffect(() => {
        loadStatus();
        loadFunnels();
    }, [loadStatus, loadFunnels]);

    const st = status?.kind === "ok" ? status.data : null;
    const rows = funnels?.kind === "ok" ? funnels.data.funnels : [];

    const moduleDormant =
        status?.kind === "dormant" && (funnels?.kind === "dormant" || funnels === null);

    const engineLive = !!st?.config?.workflow_engine_present;
    const published = rows.filter((r) => r.status === "published").length;

    return (
        <Layout title="Funnels">
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

            {/* Tab strip + refresh — Core_2 Tabs */}
            <div className="flex items-center gap-3 mb-5 max-md:flex-wrap">
                <Tabs
                    className="overflow-x-auto scrollbar-none"
                    items={FUNNEL_TABS}
                    value={tabOpt}
                    setValue={(v) => setTabOpt(v as (typeof FUNNEL_TABS)[number])}
                />
                <Button
                    className="ml-auto !h-10 max-md:ml-0"
                    isStroke
                    icon="clock"
                    onClick={() => {
                        loadStatus();
                        loadFunnels();
                    }}
                    disabled={statusLoading || funnelsLoading}
                >
                    Refresh
                </Button>
            </div>

            {tab === "overview" && (
                <OverviewTab
                    status={status}
                    st={st}
                    loading={statusLoading}
                    moduleDormant={moduleDormant}
                    engineLive={engineLive}
                    funnelCount={rows.length}
                    published={published}
                    onUseTemplate={() => setTab("templates")}
                />
            )}

            {tab === "templates" && (
                <TemplatesTab writable={writable} dormant={moduleDormant} toast={showToast} onCreated={loadFunnels} />
            )}

            {tab === "funnels" && (
                <FunnelsTab
                    result={funnels}
                    rows={rows}
                    loading={funnelsLoading}
                    writable={writable}
                    onChanged={loadFunnels}
                    toast={showToast}
                    onUseTemplate={() => setTab("templates")}
                />
            )}
        </Layout>
    );
}

/* ===================================================== TAB 1 — Overview */

function OverviewTab({
    status,
    st,
    loading,
    moduleDormant,
    engineLive,
    funnelCount,
    published,
    onUseTemplate,
}: {
    status: ReadResult<FunnelStatus> | null;
    st: FunnelStatus | null;
    loading: boolean;
    moduleDormant: boolean;
    engineLive: boolean;
    funnelCount: number;
    published: number;
    onUseTemplate: () => void;
}) {
    const landingOn = st?.config?.integrations?.landing_publish === "configured";
    const reviewOn = st?.config?.integrations?.review_request === "configured";

    return (
        <div className="space-y-3">
            {/* Overview metric strip (Core_2 Overview archetype) */}
            <Card title="Overview">
                <div className="flex gap-8 px-5 pb-5 pt-1 max-lg:gap-6 max-lg:px-3 max-lg:overflow-auto max-lg:scrollbar-none">
                    <MetricItem
                        icon="cube"
                        title="Engine"
                        loading={loading && !st}
                        value={engineLive ? "Ready" : "Coming soon"}
                        sub={
                            engineLive
                                ? "Durable workflow interpreter"
                                : "Awaiting engine provisioning"
                        }
                        accent
                    />
                    <MetricItem
                        icon="filters"
                        title="Funnels"
                        loading={loading}
                        value={String(funnelCount)}
                        sub={
                            funnelCount === 0
                                ? "None built yet"
                                : `${published} published`
                        }
                    />
                    <MetricItem
                        icon="layers"
                        title="Stages"
                        value={String(STAGES.length)}
                        sub="ad → … → review"
                    />
                    <MetricItem
                        icon="lock"
                        title="Safety"
                        value="Auto-gated"
                        sub="Budget cap + approval on spend"
                    />
                </div>
            </Card>

            {/* The signature stage-pipeline visualization */}
            <Card
                title="The conversion pipeline"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="layers" className="size-3.5 fill-t-tertiary" />
                        Each stage compiles to a workflow node
                    </span>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    <StagePipeline landingOn={landingOn} reviewOn={reviewOn} />
                </div>
            </Card>

            {/* The honest "what this is / coming soon" explainer */}
            {(moduleDormant || !engineLive) && (
                <div className="card overflow-hidden">
                    <div className="relative p-6 max-lg:p-4">
                        <span
                            aria-hidden
                            className="pointer-events-none absolute -top-20 -right-16 size-56 rounded-full opacity-[0.10] blur-3xl"
                            style={{ background: "var(--primary-02)" }}
                        />
                        <div className="relative flex items-start gap-4 max-sm:flex-col">
                            <span className="grid place-items-center size-12 shrink-0 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-02">
                                <Icon name="filters" className="size-6 fill-inherit" />
                            </span>
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h3 className="text-h6 text-t-primary">The funnel builder is coming soon</h3>
                                    <Badge variant="info" dot>
                                        In setup
                                    </Badge>
                                </div>
                                <p className="text-body-2 text-t-secondary mt-2 max-w-2xl">
                                    A funnel is not a new engine — it compiles down to the durable workflow
                                    interpreter, which already owns every safety gate: budget dominators on
                                    spend, human approval, an immutable audit trail and idempotent crash-replay.
                                    The builder lights up once the workflow engine and its authenticated route are
                                    provisioned on the server. Until then, explore the stage pipeline and the
                                    starter templates below.
                                </p>
                                <div className="mt-4 grid grid-cols-3 gap-3 max-md:grid-cols-1">
                                    <FlowStep
                                        n={1}
                                        icon="layers"
                                        title="Compose"
                                        text="Pick the stages — ad, call, WhatsApp, booking, payment — into one ordered funnel."
                                    />
                                    <FlowStep
                                        n={2}
                                        icon="lock"
                                        title="Auto-gate"
                                        text="Money and bulk stages get a budget cap + approval node injected automatically."
                                    />
                                    <FlowStep
                                        n={3}
                                        icon="chart"
                                        title="Measure"
                                        text="Every stage reports entered → converted, so you see exactly where leads drop off."
                                    />
                                </div>
                                <div className="mt-5">
                                    <Button isStroke onClick={onUseTemplate} className="h-10 !rounded-full">
                                        <Icon name="grid" className="size-4 fill-inherit mr-1.5" />
                                        Browse starter templates
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Configuration board — dormant dependencies, surfaced honestly */}
            <Card
                title="Configuration"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                        Server-side · dormant until provisioned
                    </span>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {loading && !st ? (
                        <div className="space-y-3">
                            {[...Array(4)].map((_, i) => (
                                <div key={i} className="flex items-center justify-between">
                                    <div className="skeleton h-4 w-40" />
                                    <div className="skeleton h-5 w-24" />
                                </div>
                            ))}
                        </div>
                    ) : status?.kind === "error" ? (
                        <div className="py-10 text-center">
                            <span className="inline-grid place-items-center size-12 mb-3 rounded-full bg-b-surface1">
                                <Icon name="info" className="fill-t-tertiary" />
                            </span>
                            <div className="text-sub-title-1 mb-1">
                                Couldn&apos;t load configuration
                            </div>
                            <div className="text-body-2 text-t-secondary">
                                {status.message}
                            </div>
                        </div>
                    ) : (
                        <div className="divide-y divide-s-subtle">
                            <ConfigRow
                                icon="cube"
                                label="Workflow engine"
                                hint="The durable interpreter a funnel compiles into"
                            >
                                {engineLive ? (
                                    <Badge variant="success" dot>
                                        Present
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Not configured</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow
                                icon="desktop"
                                label="Landing-page publisher"
                                hint="Hosts the funnel's landing stage (Website module)"
                            >
                                {landingOn ? (
                                    <Badge variant="info" dot>
                                        Configured
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Coming soon</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow
                                icon="heart"
                                label="Review request channel"
                                hint="Sends the closing review-request stage"
                            >
                                {reviewOn ? (
                                    <Badge variant="info" dot>
                                        Configured
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Coming soon</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow
                                icon="lock"
                                label="Money & approval gates"
                                hint="Owned by the workflow engine — funnels add none"
                            >
                                <Badge variant="success" dot>
                                    Inherited
                                </Badge>
                            </ConfigRow>
                        </div>
                    )}
                </div>
            </Card>
        </div>
    );
}

// The horizontal connected stage pipeline — the page's signature visual.
function StagePipeline({ landingOn, reviewOn }: { landingOn: boolean; reviewOn: boolean }) {
    return (
        <div className="flex items-stretch gap-0 overflow-x-auto scrollbar-none pb-1 -mx-1 px-1">
            {STAGES.map((s, i) => {
                // landing / review are inert placeholders until their sibling module ships,
                // but reflect a live integration flag when one is present.
                const live = s.key === "landing" ? landingOn : s.key === "review" ? reviewOn : true;
                const tag = stageRiskTag(s);
                return (
                    <div key={s.key} className="flex items-stretch shrink-0">
                        <div className="lift group relative w-44 max-sm:w-40 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
                            <span
                                aria-hidden
                                className="pointer-events-none absolute -top-10 -right-8 size-24 rounded-full opacity-[0.12] blur-2xl transition-opacity duration-500 group-hover:opacity-20"
                                style={{ background: s.accent }}
                            />
                            <div className="relative flex items-center justify-between">
                                <span
                                    className="grid place-items-center size-9 rounded-xl bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04"
                                    style={{ fill: s.accent }}
                                >
                                    <Icon name={s.icon} className="size-4.5 fill-inherit" />
                                </span>
                                <span className="text-caption text-t-tertiary tabular-nums">
                                    {String(i + 1).padStart(2, "0")}
                                </span>
                            </div>
                            <div className="relative text-sub-title-2 text-t-primary mt-3">{s.display}</div>
                            <div className="relative font-mono text-caption text-t-tertiary mt-1 truncate">
                                {s.compilesTo}
                            </div>
                            <div className="relative mt-2.5 flex items-center gap-1.5 flex-wrap">
                                {s.placeholder || !live ? (
                                    <Badge variant="neutral">Coming soon</Badge>
                                ) : tag ? (
                                    <Badge variant={tag.variant}>{tag.label}</Badge>
                                ) : (
                                    <Badge variant="success" dot>
                                        Ready
                                    </Badge>
                                )}
                            </div>
                        </div>
                        {i < STAGES.length - 1 && (
                            <div className="flex items-center px-1 shrink-0" aria-hidden>
                                <Icon name="arrow" className="size-4 fill-t-tertiary -rotate-90" />
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

// Core_2 Overview metric tile (ported inline; same as crm/forms pages).
function MetricItem({
    icon,
    title,
    value,
    sub,
    accent,
    loading,
}: {
    icon: string;
    title: string;
    value: React.ReactNode;
    sub?: React.ReactNode;
    accent?: boolean;
    loading?: boolean;
}) {
    return (
        <div className="flex-1 min-w-44 pr-8 border-r border-s-subtle last:border-r-0 last:pr-0 max-lg:shrink-0">
            <div
                className={`flex items-center justify-center size-12 mb-6 rounded-full ${
                    accent ? "bg-primary-02/12" : "bg-b-surface1"
                }`}
            >
                <Icon
                    className={accent ? "fill-primary-02" : "fill-t-primary"}
                    name={icon}
                />
            </div>
            <div className="text-sub-title-1 text-t-secondary mb-2">{title}</div>
            {loading ? (
                <div className="skeleton h-8 w-28 rounded-lg" />
            ) : (
                <div className="text-h3">{value}</div>
            )}
            {sub && (
                <div className="mt-2 text-body-2 text-t-tertiary">{sub}</div>
            )}
        </div>
    );
}

function FlowStep({ n, icon, title, text }: { n: number; icon: string; title: string; text: string }) {
    return (
        <div className="relative p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
            <div className="flex items-center gap-2 mb-1.5">
                <span className="grid place-items-center size-7 rounded-full bg-b-surface1 ring-1 ring-s-subtle fill-primary-02 dark:bg-shade-04">
                    <Icon name={icon} className="size-4 fill-inherit" />
                </span>
                <span className="text-caption text-t-tertiary tabular-nums">Step {n}</span>
            </div>
            <div className="text-sub-title-2 text-t-primary">{title}</div>
            <div className="text-caption text-t-secondary mt-1">{text}</div>
        </div>
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

/* ===================================================== TAB 2 — Templates */

function TemplatesTab({
    writable,
    dormant,
    toast,
    onCreated,
}: {
    writable: boolean;
    dormant: boolean;
    toast: (msg: string, type?: "success" | "error") => void;
    onCreated: () => void;
}) {
    const [busyId, setBusyId] = useState<string>("");

    async function applyTemplate(t: FunnelTemplate) {
        setBusyId(t.id);
        try {
            const res = await instantiateTemplate(t.id);
            if (res.ok) {
                toast(`Created "${t.name}" as a draft funnel`);
                onCreated();
            } else {
                toast(res.reason || "Couldn't create from template", "error");
            }
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't create from template", "error");
        } finally {
            setBusyId("");
        }
    }

    return (
        <div className="space-y-3">
            {dormant && (
                <div className="p-3 rounded-2xl border border-s-subtle bg-b-surface2 text-caption text-t-secondary flex items-center gap-2">
                    <Icon name="info" className="size-4 fill-t-tertiary shrink-0" />
                    The builder backend isn&apos;t live yet — these starter templates preview what you&apos;ll be
                    able to launch in one click. Instantiating becomes available once the Funnels service is
                    provisioned.
                </div>
            )}
            <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-2 max-md:grid-cols-1">
                {STARTER_TEMPLATES.map((t, idx) => (
                    <TemplateCard
                        key={t.id}
                        t={t}
                        delay={idx * 70}
                        canUse={writable && !dormant}
                        busy={busyId === t.id}
                        onUse={() => applyTemplate(t)}
                    />
                ))}
            </div>
        </div>
    );
}

function TemplateCard({
    t,
    delay,
    canUse,
    busy,
    onUse,
}: {
    t: FunnelTemplate;
    delay: number;
    canUse: boolean;
    busy: boolean;
    onUse: () => void;
}) {
    const moneyStages = t.stages.filter((k) => stageMeta(k)?.money).length;
    return (
        <div
            className="card rise-in flex flex-col p-5 max-lg:p-4"
            style={delay ? { animationDelay: `${delay}ms` } : undefined}
        >
            <div className="flex items-start justify-between gap-3">
                <span className="grid place-items-center size-10 shrink-0 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-02">
                    <Icon name="filters" className="size-5 fill-inherit" />
                </span>
                <span className="pill pill-neutral capitalize">{t.industry_pack.replace(/_/g, " ")}</span>
            </div>
            <div className="text-sub-title-1 text-t-primary mt-3">{t.name}</div>
            <p className="text-caption text-t-secondary mt-1.5 flex-1">{t.blurb}</p>

            {/* mini stage chips */}
            <div className="flex flex-wrap gap-1.5 mt-4">
                {t.stages.map((k) => {
                    const m = stageMeta(k);
                    if (!m) return null;
                    return (
                        <span
                            key={k}
                            className="inline-flex items-center gap-1 h-6 px-2 rounded-full bg-b-surface2 ring-1 ring-s-subtle ring-inset text-caption text-t-secondary"
                            title={m.display}
                        >
                            <span style={{ fill: m.accent }} className="inline-flex">
                                <Icon name={m.icon} className="size-3 fill-inherit" />
                            </span>
                            {m.display}
                        </span>
                    );
                })}
            </div>

            <div className="flex items-center justify-between mt-4 pt-4 border-t border-s-subtle">
                <span className="text-caption text-t-tertiary">
                    {t.stages.length} stages
                    {moneyStages > 0 && (
                        <>
                            {" · "}
                            <span className="text-primary-03">{moneyStages} money-gated</span>
                        </>
                    )}
                </span>
                {canUse ? (
                    <Button
                        className="!h-9 !px-3.5 !text-button"
                        isStroke
                        icon="plus"
                        onClick={onUse}
                        disabled={busy}
                    >
                        {busy ? "Creating…" : "Use"}
                    </Button>
                ) : (
                    <span className="text-caption text-t-tertiary inline-flex items-center gap-1">
                        <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                        Preview
                    </span>
                )}
            </div>
        </div>
    );
}

/* ===================================================== TAB 3 — My Funnels */

function FunnelsTab({
    result,
    rows,
    loading,
    writable,
    onChanged,
    toast,
    onUseTemplate,
}: {
    result: ReadResult<{ funnels: FunnelRow[] }> | null;
    rows: FunnelRow[];
    loading: boolean;
    writable: boolean;
    onChanged: () => void;
    toast: (msg: string, type?: "success" | "error") => void;
    onUseTemplate: () => void;
}) {
    const dormant = result?.kind === "dormant";
    const error = result?.kind === "error" ? result.message : "";
    const [busyId, setBusyId] = useState<string>("");

    async function doPublish(f: FunnelRow) {
        setBusyId(f.funnel_id + ":pub");
        try {
            const res = await publishFunnel(f.funnel_id);
            if (res.ok) {
                toast(`"${f.name}" published (v${res.version ?? "?"})`);
                onChanged();
            } else if (res.reason === "workflow_validation_failed") {
                toast(`Validation failed: ${(res.errors || []).join("; ") || "ungated step"}`, "error");
            } else {
                toast(res.reason || "Publish failed", "error");
            }
        } catch (e) {
            toast(e instanceof Error ? e.message : "Publish failed", "error");
        } finally {
            setBusyId("");
        }
    }

    async function doRun(f: FunnelRow) {
        setBusyId(f.funnel_id + ":run");
        try {
            const res = await runFunnel(f.funnel_id);
            if (res.ok) {
                toast(`"${f.name}" run started${res.run_id ? ` (${res.run_id})` : ""}`);
                onChanged();
            } else {
                toast(res.reason || "Run failed", "error");
            }
        } catch (e) {
            toast(e instanceof Error ? e.message : "Run failed", "error");
        } finally {
            setBusyId("");
        }
    }

    return (
        <Card
            title="My Funnels"
            headContent={
                <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                    <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                    Published funnels run on the durable engine
                </span>
            }
        >
            {error && (
                <div className="mx-5 mb-3 mt-3 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03 max-lg:mx-3">
                    <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                    {error}
                </div>
            )}

            <div className="p-1 pt-3 max-lg:px-0">
                {loading ? (
                    <Table cellsThead={funnelHead(writable)}>
                        {[...Array(3)].map((_, i) => (
                            <TableRow key={i}>
                                {[...Array(writable ? 5 : 4)].map((__, j) => (
                                    <td key={j}>
                                        <div className="skeleton h-4 w-24 rounded-lg" />
                                    </td>
                                ))}
                            </TableRow>
                        ))}
                    </Table>
                ) : dormant ? (
                    <DormantPanel
                        icon="filters"
                        title="The funnel builder is coming soon"
                        sub="Once the Funnels service is provisioned on the server, the funnels you build from a template or from scratch appear here — each one compiling down to the durable workflow engine, with per-stage conversion analytics."
                    >
                        <Button className="mt-5" isStroke icon="grid" onClick={onUseTemplate}>
                            Browse starter templates
                        </Button>
                    </DormantPanel>
                ) : rows.length === 0 ? (
                    <DormantPanel
                        icon="plus"
                        title="No funnels yet"
                        sub="Start from a proven industry template, then tweak the per-stage knobs. The builder injects the budget and approval gates for you."
                    >
                        <Button className="mt-5" isStroke icon="grid" onClick={onUseTemplate}>
                            Browse starter templates
                        </Button>
                    </DormantPanel>
                ) : (
                    <Table cellsThead={funnelHead(writable)}>
                        {rows.map((f) => {
                            const stages = rowStages(f);
                            return (
                                <TableRow key={f.funnel_id}>
                                    <td>
                                        <div className="text-sub-title-1 text-t-primary">
                                            {f.name}
                                        </div>
                                        <div className="text-body-2 text-t-tertiary mt-0.5">
                                            {f.industry_pack
                                                ? f.industry_pack.replace(/_/g, " ")
                                                : "custom"}
                                            {f.updated_at ? ` · ${fmtDate(f.updated_at)}` : ""}
                                        </div>
                                    </td>
                                    <td className="max-lg:hidden">
                                        {stages.length === 0 ? (
                                            <span className="text-t-tertiary">—</span>
                                        ) : (
                                            <div className="flex items-center gap-1">
                                                {stages.slice(0, 6).map((k) => {
                                                    const m = stageMeta(k);
                                                    if (!m) return null;
                                                    return (
                                                        <span
                                                            key={k}
                                                            title={m.display}
                                                            className="grid place-items-center size-6 rounded-md bg-b-surface1 ring-1 ring-s-subtle ring-inset"
                                                            style={{ fill: m.accent }}
                                                        >
                                                            <Icon
                                                                name={m.icon}
                                                                className="size-3 fill-inherit"
                                                            />
                                                        </span>
                                                    );
                                                })}
                                                {stages.length > 6 && (
                                                    <span className="text-body-2 text-t-tertiary">
                                                        +{stages.length - 6}
                                                    </span>
                                                )}
                                            </div>
                                        )}
                                    </td>
                                    <td>
                                        <Badge
                                            variant={statusVariant(f.status)}
                                            dot={f.status === "published"}
                                        >
                                            {f.status}
                                        </Badge>
                                    </td>
                                    <td className="text-t-secondary max-md:hidden">
                                        {f.current_version ? `v${f.current_version}` : "—"}
                                    </td>
                                    {writable && (
                                        <td className="text-right">
                                            <div className="inline-flex items-center gap-2">
                                                <Button
                                                    className="!h-9 !px-3.5 !text-button"
                                                    isStroke
                                                    icon="check"
                                                    onClick={() => doPublish(f)}
                                                    disabled={!!busyId}
                                                    title="Compile + validate + freeze a version on the workflow engine"
                                                >
                                                    {busyId === f.funnel_id + ":pub" ? "…" : "Publish"}
                                                </Button>
                                                <Button
                                                    className="!h-9 !px-3.5 !text-button"
                                                    isStroke
                                                    icon="send"
                                                    onClick={() => doRun(f)}
                                                    disabled={!!busyId || f.status !== "published"}
                                                    title={
                                                        f.status === "published"
                                                            ? "Trigger a run on the durable engine"
                                                            : "Publish the funnel before running it"
                                                    }
                                                >
                                                    {busyId === f.funnel_id + ":run" ? "…" : "Run"}
                                                </Button>
                                            </div>
                                        </td>
                                    )}
                                </TableRow>
                            );
                        })}
                    </Table>
                )}
            </div>
        </Card>
    );
}

function funnelHead(writable: boolean) {
    return (
        <>
            <th>Funnel</th>
            <th className="max-lg:hidden">Pipeline</th>
            <th>Status</th>
            <th className="max-md:hidden">Version</th>
            {writable && <th className="text-right">Actions</th>}
        </>
    );
}
