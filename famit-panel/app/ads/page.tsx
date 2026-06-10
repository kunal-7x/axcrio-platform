"use client";

// Ads — the autonomous PAID-ADS command center.
//
// The AI drafts a Meta / Google campaign from a one-line brief, freezes a HARD
// spend cap onto it, and parks it as a DRAFT. Nothing goes live without a human
// step-up approval; a polling breaker pauses any campaign that breaches its cap
// or CPL; every decision is audited. This page is the DASHBOARD surface for that
// engine: propose briefs, watch spend vs cap, approve / pause, and run the
// deterministic optimizer.
//
// The backend router (ads_engine) is DEFINED-NOT-MOUNTED and dormant-until-creds
// (Meta/Google), so the graceful "not configured / coming soon" path is the
// PRIMARY state — every read degrades to a premium dormant view, never an error
// wall. Approve is fail-closed server-side (no step-up seam yet) so the button
// surfaces "step-up required — coming soon" honestly instead of faking a launch.
//
// Built entirely on the in-app "Signal" component language (Layout / PageHeader /
// Card / Icon / Badge / Button) + verified globals.css utilities. Edits only this
// route's own files (app/ads/*).

import { useCallback, useEffect, useState } from "react";
import Layout from "@/components/Layout";
import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Button from "@/components/Button";
import { useMe, canWrite } from "@/lib/auth";
import {
    getAdsHealth,
    getAdsCampaigns,
    proposeCampaign,
    approveCampaign,
    pauseCampaign,
    runOptimize,
    fmtMoney,
    ADS_OBJECTIVES,
    type AdsHealth,
    type AdsCampaign,
    type AdsStatusResponse,
    type AdsStatus,
    type AdsBrief,
    type AdsObjective,
    type OptimizeResponse,
    type ReadResult,
} from "./_lib";

/* ----------------------------------------------------------------- helpers */

type Toast = { msg: string; type: "success" | "error" };
type TabKey = "overview" | "campaigns" | "optimizer";

// Map a backend status -> a Badge tone + a human label.
function statusVariant(s: AdsStatus): BadgeVariant {
    if (s === "active") return "success";
    if (s === "paused") return "warning";
    if (s === "pending_approval") return "info";
    if (s === "dry_run") return "info";
    if (typeof s === "string" && s.startsWith("blocked")) return "danger";
    return "neutral";
}

function statusLabel(s: AdsStatus): string {
    const map: Record<string, string> = {
        active: "Live",
        paused: "Paused",
        pending_approval: "Awaiting approval",
        dry_run: "Dry run",
        not_configured: "Not configured",
        draft: "Draft",
        blocked_cap_exceeded: "Cap reached",
        blocked_cpl_breach: "CPL breach",
        blocked_no_conversion_tracking: "No CPL tracking",
        blocked_not_approved: "Step-up needed",
        blocked_insufficient_funds: "Low balance",
    };
    return map[s] || s;
}

function objectiveLabel(o: string): string {
    return (o || "")
        .replace(/^OUTCOME_/, "")
        .toLowerCase()
        .replace(/^\w/, (c) => c.toUpperCase());
}

function providerLabel(p?: string): string {
    if (!p || p === "noop" || p === "not_configured") return "Not connected";
    return p.charAt(0).toUpperCase() + p.slice(1);
}

function providerIcon(p?: string): string {
    if (p === "meta") return "facebook";
    if (p === "google") return "earth";
    return "promote";
}

function moveVariant(m: string): BadgeVariant {
    if (m === "scale_winner") return "success";
    if (m === "kill_loser") return "danger";
    return "neutral";
}

function moveLabel(m: string): string {
    const map: Record<string, string> = {
        scale_winner: "Scale winner",
        kill_loser: "Kill loser",
        hold: "Hold",
    };
    return map[m] || m;
}

function moveReason(r: string): string {
    const map: Record<string, string> = {
        cpl_at_or_below_target: "CPL at or below target",
        cpl_above_target: "CPL above target",
        below_min_sample: "Sample too small to act",
        blocked_no_conversion_tracking: "No conversion tracking",
    };
    return map[r] || r.replace(/_/g, " ");
}

/* ------------------------------------------------------------ shared bits */

// The premium "coming soon / not configured" panel — the PRIMARY state until the
// backend router is mounted and ad-platform creds land. On-brand, never an error.
function DormantPanel({
    icon = "promote",
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

/* ============================================================== the page */

export default function AdsPage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [tab, setTab] = useState<TabKey>("overview");
    const [toast, setToast] = useState<Toast | null>(null);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4600);
    };

    // ---- health ----
    const [health, setHealth] = useState<ReadResult<AdsHealth> | null>(null);
    const [healthLoading, setHealthLoading] = useState(true);
    const loadHealth = useCallback(() => {
        setHealthLoading(true);
        getAdsHealth()
            .then(setHealth)
            .finally(() => setHealthLoading(false));
    }, []);

    // ---- campaigns ----
    const [camps, setCamps] = useState<ReadResult<AdsStatusResponse> | null>(null);
    const [campsLoading, setCampsLoading] = useState(true);
    const loadCamps = useCallback(() => {
        setCampsLoading(true);
        getAdsCampaigns()
            .then(setCamps)
            .finally(() => setCampsLoading(false));
    }, []);

    useEffect(() => {
        loadHealth();
        loadCamps();
    }, [loadHealth, loadCamps]);

    const refreshAll = () => {
        loadHealth();
        loadCamps();
    };

    // health can come from /ads/health OR be embedded on the campaigns payload.
    const hc: AdsHealth | null =
        health?.kind === "ok"
            ? health.data
            : camps?.kind === "ok"
            ? camps.data.config
            : null;
    const campData = camps?.kind === "ok" ? camps.data : null;
    const rows: AdsCampaign[] = campData?.campaigns || [];

    const moduleDormant = health?.kind === "dormant" && camps?.kind === "dormant";

    const activeCount = rows.filter((r) => r.status === "active").length;
    const pendingCount = rows.filter((r) => r.status === "pending_approval").length;
    const currency = hc?.caps.currency || "INR";

    const TABS: { key: TabKey; label: string; icon: string; badge?: number }[] = [
        { key: "overview", label: "Overview", icon: "dashboard" },
        { key: "campaigns", label: "Campaigns", icon: "promote", badge: pendingCount },
        { key: "optimizer", label: "Optimizer", icon: "magic-pencil" },
    ];

    const loading = (healthLoading && !hc) || (campsLoading && !campData);

    return (
        <Layout title="Ads">
            <PageHeader
                eyebrow="Paid-Ads Command Center"
                title="Ads"
                subtitle="Brief the AI once and it drafts a full Meta or Google campaign — copy, audience and objective — under a hard spend cap. Nothing goes live without your approval; a breaker auto-pauses any campaign that blows its budget or cost-per-lead; every decision is logged."
                actions={
                    <button
                        onClick={refreshAll}
                        className="inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50"
                        disabled={healthLoading || campsLoading}
                    >
                        <Icon
                            name="clock"
                            className={`size-4 fill-current ${healthLoading || campsLoading ? "animate-spin" : ""}`}
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

            {/* Tab strip — pill rail matching the AI Manager / billing premium tabs */}
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
                            {t.key === "campaigns" && (t.badge || 0) > 0 && (
                                <span className="pill pill-info !px-1.5 !py-0 text-caption">{t.badge}</span>
                            )}
                        </button>
                    );
                })}
            </div>

            {tab === "overview" && (
                <Overview
                    hc={hc}
                    health={health}
                    loading={loading}
                    moduleDormant={moduleDormant}
                    activeCount={activeCount}
                    pendingCount={pendingCount}
                    totalCount={rows.length}
                    spendTodayMinor={campData?.spend_today_minor ?? 0}
                    currency={currency}
                />
            )}

            {tab === "campaigns" && (
                <CampaignsTab
                    result={camps}
                    rows={rows}
                    loading={campsLoading}
                    writable={writable}
                    currency={currency}
                    hc={hc}
                    onChanged={refreshAll}
                    toast={showToast}
                />
            )}

            {tab === "optimizer" && (
                <OptimizerTab
                    writable={writable}
                    dormant={moduleDormant}
                    activeCount={activeCount}
                    currency={currency}
                    hc={hc}
                    toast={showToast}
                />
            )}
        </Layout>
    );
}

/* ===================================================== TAB 1 — Overview */

function Overview({
    hc,
    health,
    loading,
    moduleDormant,
    activeCount,
    pendingCount,
    totalCount,
    spendTodayMinor,
    currency,
}: {
    hc: AdsHealth | null;
    health: ReadResult<AdsHealth> | null;
    loading: boolean;
    moduleDormant: boolean;
    activeCount: number;
    pendingCount: number;
    totalCount: number;
    spendTodayMinor: number;
    currency: string;
}) {
    const metaOn = hc?.providers.meta === "configured";
    const googleOn = hc?.providers.google === "configured";
    const anyProvider = metaOn || googleOn;
    const liveSpend = anyProvider && !hc?.dry_run;
    const dailyCap = hc?.caps.daily_cap_minor ?? 0;

    return (
        <div className="space-y-3">
            {/* Hero KPI strip — real config + spend signals only */}
            <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <HeroStat
                    label="Ad Platforms"
                    glyph="promote"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    loading={loading && !hc}
                    value={anyProvider ? `${[metaOn && "Meta", googleOn && "Google"].filter(Boolean).join(" + ")}` : "Not connected"}
                    foot={anyProvider ? "Marketing API linked" : "Awaiting Meta / Google credentials"}
                />
                <HeroStat
                    label="Live Campaigns"
                    glyph="feather"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={60}
                    loading={loading && !hc}
                    value={String(activeCount)}
                    foot={
                        pendingCount > 0
                            ? `${pendingCount} awaiting approval`
                            : totalCount === 0
                            ? "No campaigns yet"
                            : "All reviewed"
                    }
                />
                <HeroStat
                    label="Spend Today"
                    glyph="wallet"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    delay={120}
                    loading={loading && !hc}
                    value={liveSpend ? fmtMoney(spendTodayMinor, currency) : fmtMoney(0, currency)}
                    foot={
                        dailyCap > 0
                            ? `of ${fmtMoney(dailyCap, currency)} hard cap`
                            : liveSpend
                            ? "across active campaigns"
                            : "Dry-run — nothing spends yet"
                    }
                />
                <HeroStat
                    label="Spend Guard"
                    glyph="lock"
                    glyphClass="fill-primary-05"
                    accent="var(--primary-05)"
                    delay={180}
                    loading={loading && !hc}
                    value={hc?.require_approval ? "Approval + breaker" : "Breaker"}
                    foot={
                        hc
                            ? `Auto-pause every ${hc.caps.poll_minutes}m on breach`
                            : "Human approval before any spend"
                    }
                />
            </div>

            {/* The honest "what this is / coming soon" explainer */}
            {(moduleDormant || !anyProvider) && (
                <div className="card overflow-hidden">
                    <div className="relative p-6 max-lg:p-4">
                        <span
                            aria-hidden
                            className="pointer-events-none absolute -top-20 -right-16 size-56 rounded-full opacity-[0.10] blur-3xl"
                            style={{ background: "var(--primary-01)" }}
                        />
                        <div className="relative flex items-start gap-4 max-sm:flex-col">
                            <span className="grid place-items-center size-12 shrink-0 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                                <Icon name="promote" className="size-6 fill-inherit" />
                            </span>
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h3 className="text-h6 text-t-primary">Autonomous ads are coming soon</h3>
                                    <Badge variant="info" dot>
                                        In setup
                                    </Badge>
                                </div>
                                <p className="text-body-2 text-t-secondary mt-2 max-w-2xl">
                                    The spend-safety engine is built and offline-verified — hard daily caps,
                                    a cost-per-lead breaker, a human approval gate and an immutable audit
                                    trail. The platforms light up once your Meta or Google Ads account is
                                    connected on the server. Until then you can draft campaigns safely: in
                                    dry-run nothing can spend a rupee.
                                </p>
                                <div className="mt-4 grid grid-cols-3 gap-3 max-md:grid-cols-1">
                                    <FlowStep
                                        n={1}
                                        icon="magic-pencil"
                                        title="Brief"
                                        text="Describe the campaign in a line. The AI drafts copy, audience and objective — capped to your budget."
                                    />
                                    <FlowStep
                                        n={2}
                                        icon="lock"
                                        title="Approve"
                                        text="Nothing goes live without a human step-up. The draft waits, paused, until you sign off."
                                    />
                                    <FlowStep
                                        n={3}
                                        icon="feather"
                                        title="Auto-pilot"
                                        text="A breaker pauses any campaign that blows its budget or CPL; the optimizer scales winners, kills losers."
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Configuration board — every dependency, surfaced honestly */}
            <Card
                title="Configuration"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                        Server-side · dormant until creds
                    </span>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {loading && !hc ? (
                        <div className="space-y-3">
                            {[...Array(5)].map((_, i) => (
                                <div key={i} className="flex items-center justify-between">
                                    <div className="skeleton h-4 w-40" />
                                    <div className="skeleton h-5 w-24" />
                                </div>
                            ))}
                        </div>
                    ) : health?.kind === "error" ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="info" className="fill-inherit" />
                            </span>
                            <div className="state-title">Could not load configuration</div>
                            <div className="state-sub">{health.message}</div>
                        </div>
                    ) : (
                        <div className="divide-y divide-s-subtle">
                            <ConfigRow icon="facebook" label="Meta Ads" hint="Facebook & Instagram Marketing API">
                                {metaOn ? (
                                    <Badge variant="success" dot>
                                        Connected
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Not configured</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow icon="earth" label="Google Ads" hint="Search & display via the Google Ads API">
                                {googleOn ? (
                                    <Badge variant="success" dot>
                                        Connected
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Not configured</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow icon="wallet" label="Spend mode" hint="Whether real money can move">
                                {hc?.dry_run ? (
                                    <Badge variant="info" dot>
                                        Dry-run (safe)
                                    </Badge>
                                ) : (
                                    <Badge variant="warning" dot>
                                        Live spend
                                    </Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow icon="lock" label="Approval gate" hint="Human step-up before activation">
                                <Badge variant={hc?.require_approval ? "success" : "neutral"} dot={hc?.require_approval}>
                                    {hc?.require_approval ? "Required" : "Off"}
                                </Badge>
                            </ConfigRow>
                            <ConfigRow icon="usd-circle" label="Hard daily cap" hint="The real spend floor, set on the platform">
                                <span className="text-body-2 text-t-primary tabular-nums">
                                    {dailyCap > 0 ? fmtMoney(dailyCap, currency) : "Not set"}
                                </span>
                            </ConfigRow>
                        </div>
                    )}
                </div>
            </Card>

            {/* The defense-in-depth guardrails, told as a board */}
            <Card title="How your spend is protected">
                <div className="px-5 pb-5 max-lg:px-3 grid grid-cols-2 gap-3 max-md:grid-cols-1">
                    <GuardCard
                        icon="usd-circle"
                        title="Platform hard cap"
                        body="A daily budget set ≤ your cap at create-time. Meta and Google will not spend past it — the strongest, on-platform floor."
                    />
                    <GuardCard
                        icon="clock"
                        title="Polling breaker"
                        body={`Every ${hc?.caps.poll_minutes ?? 30} minutes the engine pulls live spend and pauses any campaign at or over its cap.`}
                    />
                    <GuardCard
                        icon="arrow-percent"
                        title="CPL breaker"
                        body={`Pauses a campaign whose cost-per-lead blows the target — only once it has ≥ ${hc?.caps.cpl_min_conversions ?? 15} conversions, never on a tiny sample.`}
                    />
                    <GuardCard
                        icon="lock"
                        title="Approval + audit"
                        body="Nothing activates without a human step-up, and every propose, approve and pause is written to an immutable ledger."
                    />
                </div>
            </Card>
        </div>
    );
}

function GuardCard({ icon, title, body }: { icon: string; title: string; body: string }) {
    return (
        <div className="lift group flex items-start gap-3 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
            <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                <Icon name={icon} className="size-4.5 fill-inherit" />
            </span>
            <div className="min-w-0 flex-1">
                <div className="text-sub-title-2 text-t-primary">{title}</div>
                <div className="text-caption text-t-secondary mt-1">{body}</div>
            </div>
        </div>
    );
}

/* ===================================================== TAB 2 — Campaigns */

function CampaignsTab({
    result,
    rows,
    loading,
    writable,
    currency,
    hc,
    onChanged,
    toast,
}: {
    result: ReadResult<AdsStatusResponse> | null;
    rows: AdsCampaign[];
    loading: boolean;
    writable: boolean;
    currency: string;
    hc: AdsHealth | null;
    onChanged: () => void;
    toast: (msg: string, type?: "success" | "error") => void;
}) {
    const dormant = result?.kind === "dormant";
    const error = result?.kind === "error" ? result.message : "";
    const [busyId, setBusyId] = useState<string>("");

    async function doApprove(c: AdsCampaign) {
        setBusyId(c.plan_id);
        try {
            // No step-up token seam yet — the backend gate is fail-closed, so this
            // returns a `blocked_*` / dry_run status we surface honestly.
            const res = await approveCampaign(c.plan_id);
            if (res.status === "active") {
                toast(`${c.name} is live`);
            } else if (res.status === "dry_run" || res.status === "not_configured") {
                toast(`${c.name} approved — held in dry-run until ad platforms are connected`);
            } else if (res.status === "blocked_not_approved") {
                toast("Approval needs a step-up PIN — coming soon once the security gate is wired", "error");
            } else {
                toast(`${c.name}: ${statusLabel(res.status)}`, "error");
            }
            onChanged();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Approve failed", "error");
        } finally {
            setBusyId("");
        }
    }

    async function doPause(c: AdsCampaign) {
        setBusyId(c.plan_id);
        try {
            await pauseCampaign(c.plan_id);
            toast(`${c.name} paused`);
            onChanged();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Pause failed", "error");
        } finally {
            setBusyId("");
        }
    }

    return (
        <div className="flex gap-6 max-lg:flex-col">
            <div className="flex-1 min-w-0">
                <Card
                    title="Campaigns"
                    headContent={
                        <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                            Capped · approval-gated
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
                                    <th>Campaign</th>
                                    <th>Platform</th>
                                    <th>Objective</th>
                                    <th>Spend / Cap</th>
                                    <th>CPL</th>
                                    <th>Status</th>
                                    {writable && <th className="text-right pr-5">Actions</th>}
                                </tr>
                            </thead>
                            <tbody>
                                {loading ? (
                                    [...Array(3)].map((_, i) => (
                                        <tr key={i}>
                                            {[...Array(writable ? 7 : 6)].map((__, j) => (
                                                <td key={j}>
                                                    <div className="skeleton h-4 w-20" />
                                                </td>
                                            ))}
                                        </tr>
                                    ))
                                ) : dormant ? (
                                    <tr>
                                        <td colSpan={writable ? 7 : 6}>
                                            <DormantPanel
                                                icon="promote"
                                                title="Campaigns coming soon"
                                                sub="Once the Ads engine is provisioned on the server, every drafted, live and paused campaign appears here with its live spend against the hard cap, its cost-per-lead and one-tap approve / pause controls."
                                            />
                                        </td>
                                    </tr>
                                ) : rows.length === 0 ? (
                                    <tr>
                                        <td colSpan={writable ? 7 : 6}>
                                            <DormantPanel
                                                icon="magic-pencil"
                                                title="No campaigns yet"
                                                sub="Draft your first campaign on the right. The AI builds the copy, audience and objective and parks it as a capped draft — nothing spends until you approve it."
                                            />
                                        </td>
                                    </tr>
                                ) : (
                                    rows.map((c) => {
                                        const cap = c.daily_cap_minor || hc?.caps.daily_cap_minor || 0;
                                        const spend = c.spend_today_minor || 0;
                                        const pct = cap > 0 ? Math.min(100, Math.round((spend / cap) * 100)) : 0;
                                        return (
                                            <tr key={c.plan_id}>
                                                <td>
                                                    <div className="text-body-2 text-t-primary truncate max-w-[14rem]">
                                                        {c.name}
                                                    </div>
                                                    {c.pause_reason && c.status === "paused" && (
                                                        <div className="text-caption text-t-tertiary mt-0.5 truncate max-w-[14rem]">
                                                            {c.pause_reason.replace(/_/g, " ")}
                                                        </div>
                                                    )}
                                                </td>
                                                <td>
                                                    <span className="inline-flex items-center gap-1.5 text-body-2 text-t-secondary">
                                                        <Icon
                                                            name={providerIcon(c.provider)}
                                                            className="size-4 fill-t-tertiary"
                                                        />
                                                        {providerLabel(c.provider)}
                                                    </span>
                                                </td>
                                                <td className="text-t-secondary">{objectiveLabel(c.objective)}</td>
                                                <td>
                                                    <div className="text-body-2 text-t-primary tabular-nums whitespace-nowrap">
                                                        {fmtMoney(spend, currency)}
                                                        <span className="text-t-tertiary">
                                                            {" "}
                                                            / {cap > 0 ? fmtMoney(cap, currency) : "—"}
                                                        </span>
                                                    </div>
                                                    {cap > 0 && (
                                                        <div className="mt-1.5 h-1.5 w-24 rounded-full bg-b-surface2 overflow-hidden">
                                                            <div
                                                                className="h-full rounded-full transition-all"
                                                                style={{
                                                                    width: `${pct}%`,
                                                                    background:
                                                                        pct >= 90
                                                                            ? "var(--primary-03)"
                                                                            : "var(--primary-02)",
                                                                }}
                                                            />
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="text-t-secondary tabular-nums whitespace-nowrap">
                                                    {c.last_cpl_minor != null
                                                        ? fmtMoney(c.last_cpl_minor, currency)
                                                        : "—"}
                                                </td>
                                                <td>
                                                    <Badge
                                                        variant={statusVariant(c.status)}
                                                        dot={c.status === "active"}
                                                    >
                                                        {statusLabel(c.status)}
                                                    </Badge>
                                                </td>
                                                {writable && (
                                                    <td className="text-right pr-5">
                                                        <div className="inline-flex items-center gap-2">
                                                            {c.status === "pending_approval" && (
                                                                <button
                                                                    onClick={() => doApprove(c)}
                                                                    disabled={busyId === c.plan_id}
                                                                    className="inline-flex items-center gap-1 h-8 px-3 rounded-full border border-s-subtle text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary disabled:opacity-50"
                                                                    title="Activation is step-up gated and may require a PIN"
                                                                >
                                                                    <Icon name="check-circle" className="size-3.5 fill-current" />
                                                                    Approve
                                                                </button>
                                                            )}
                                                            {c.status === "active" && (
                                                                <button
                                                                    onClick={() => doPause(c)}
                                                                    disabled={busyId === c.plan_id}
                                                                    className="inline-flex items-center gap-1 h-8 px-3 rounded-full border border-s-subtle text-button text-primary-03 fill-primary-03 transition-colors hover:bg-primary-03/8 disabled:opacity-50"
                                                                >
                                                                    <Icon name="block" className="size-3.5 fill-current" />
                                                                    Pause
                                                                </button>
                                                            )}
                                                        </div>
                                                    </td>
                                                )}
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                </Card>
            </div>

            {/* Propose form — manager+ only */}
            {writable && (
                <div className="w-96 max-lg:w-full shrink-0">
                    <ProposeForm onProposed={onChanged} toast={toast} disabled={dormant} currency={currency} />
                </div>
            )}
        </div>
    );
}

function ProposeForm({
    onProposed,
    toast,
    disabled,
    currency,
}: {
    onProposed: () => void;
    toast: (msg: string, type?: "success" | "error") => void;
    disabled: boolean;
    currency: string;
}) {
    const [name, setName] = useState("");
    const [objective, setObjective] = useState<AdsObjective>("leads");
    const [geo, setGeo] = useState("");
    const [audience, setAudience] = useState("");
    const [budget, setBudget] = useState(""); // major units, e.g. "1500"
    const [variants, setVariants] = useState(3);
    const [saving, setSaving] = useState(false);

    const inputCls = "input-base w-full h-11 px-4 rounded-2xl text-body-2";
    const selectCls = `${inputCls} appearance-none`;

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        if (!name.trim()) return;
        setSaving(true);
        const brief: AdsBrief = {
            name: name.trim(),
            objective,
            variants,
        };
        const budgetMajor = parseFloat(budget);
        if (Number.isFinite(budgetMajor) && budgetMajor > 0) {
            brief.budget_daily_minor = Math.round(budgetMajor * 100);
        }
        if (geo.trim()) {
            brief.geo = geo
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean);
        }
        if (audience.trim()) {
            brief.audience = { description: audience.trim() };
        }
        try {
            await proposeCampaign(brief);
            toast(`${name.trim()} drafted — review and approve it to go live`);
            setName("");
            setGeo("");
            setAudience("");
            setBudget("");
            onProposed();
        } catch (e2) {
            toast(e2 instanceof Error ? e2.message : "Draft failed", "error");
        } finally {
            setSaving(false);
        }
    }

    return (
        <Card title="Draft a Campaign">
            <form onSubmit={submit} className="px-5 pb-5 space-y-4">
                {disabled && (
                    <div className="p-3 rounded-2xl border border-s-subtle bg-b-surface2 text-caption text-t-secondary">
                        The backend is not live yet — drafts will be accepted once the Ads engine is
                        provisioned on the server. In dry-run nothing can spend.
                    </div>
                )}
                <div>
                    <label className="block text-button mb-3 text-t-primary">Campaign name / product</label>
                    <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Diwali offer — 2BHK Gurgaon"
                        className={inputCls}
                        required
                    />
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-button mb-3 text-t-primary">Objective</label>
                        <select
                            value={objective}
                            onChange={(e) => setObjective(e.target.value as AdsObjective)}
                            className={selectCls}
                        >
                            {ADS_OBJECTIVES.map((o) => (
                                <option key={o} value={o}>
                                    {o.charAt(0).toUpperCase() + o.slice(1)}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-button mb-3 text-t-primary">
                            Daily budget ({currency === "INR" ? "₹" : currency})
                        </label>
                        <input
                            type="number"
                            min="0"
                            step="1"
                            value={budget}
                            onChange={(e) => setBudget(e.target.value)}
                            placeholder="1500"
                            className={inputCls}
                        />
                    </div>
                </div>
                <div>
                    <label className="block text-button mb-3 text-t-primary">Locations</label>
                    <input
                        type="text"
                        value={geo}
                        onChange={(e) => setGeo(e.target.value)}
                        placeholder="Gurgaon, Delhi NCR"
                        className={inputCls}
                    />
                    <p className="text-caption text-t-tertiary mt-2">Comma-separated.</p>
                </div>
                <div>
                    <label className="block text-button mb-3 text-t-primary">Audience</label>
                    <input
                        type="text"
                        value={audience}
                        onChange={(e) => setAudience(e.target.value)}
                        placeholder="Home buyers, 28–45, ready to move"
                        className={inputCls}
                    />
                </div>
                <div>
                    <label className="block text-button mb-3 text-t-primary">
                        Creative variants — {variants}
                    </label>
                    <input
                        type="range"
                        min={1}
                        max={5}
                        value={variants}
                        onChange={(e) => setVariants(parseInt(e.target.value, 10))}
                        className="w-full accent-primary-01"
                    />
                    <p className="text-caption text-t-tertiary mt-2">
                        The optimizer tests these, scales the winner and kills the losers.
                    </p>
                </div>
                <p className="text-caption text-t-tertiary">
                    The budget is clamped to your hard cap. The draft is parked at
                    <span className="text-t-secondary"> awaiting approval</span> — nothing spends until
                    you sign off.
                </p>
                <Button isBlack className="w-full justify-center" disabled={saving}>
                    {saving ? "Drafting…" : "Draft campaign"}
                </Button>
            </form>
        </Card>
    );
}

/* ===================================================== TAB 3 — Optimizer */

function OptimizerTab({
    writable,
    dormant,
    activeCount,
    currency,
    hc,
    toast,
}: {
    writable: boolean;
    dormant: boolean;
    activeCount: number;
    currency: string;
    hc: AdsHealth | null;
    toast: (msg: string, type?: "success" | "error") => void;
}) {
    const [result, setResult] = useState<OptimizeResponse | null>(null);
    const [running, setRunning] = useState(false);

    async function runDry() {
        setRunning(true);
        try {
            const res = await runOptimize(true);
            setResult(res);
            if ((res.moves || []).length === 0) {
                toast("No moves to suggest — no active campaigns with enough data yet");
            } else {
                toast(`${res.moves.length} suggestion${res.moves.length === 1 ? "" : "s"} ready`);
            }
        } catch (e) {
            toast(e instanceof Error ? e.message : "Optimize failed", "error");
        } finally {
            setRunning(false);
        }
    }

    const winners = (result?.moves || []).filter((m) => m.move === "scale_winner").length;
    const losers = (result?.moves || []).filter((m) => m.move === "kill_loser").length;

    return (
        <div className="space-y-3">
            <Card
                title="Optimizer"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="magic-pencil" className="size-3.5 fill-t-tertiary" />
                        Deterministic · explainable
                    </span>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    <div className="flex items-start gap-4 max-sm:flex-col">
                        <div className="min-w-0 flex-1">
                            <p className="text-body-2 text-t-secondary max-w-2xl">
                                A transparent rules pass — no black-box agent moves your money. It ranks your
                                live campaigns by cost-per-lead, flags winners to scale and losers to kill,
                                and suggests shifting budget within your cap. Run it as a dry-run to preview
                                every move with its reason before anything changes.
                            </p>
                            <div className="mt-4 flex flex-wrap items-center gap-2">
                                <span className="pill pill-neutral">
                                    {activeCount} active campaign{activeCount === 1 ? "" : "s"}
                                </span>
                                <span className="pill pill-neutral">
                                    Min {hc?.caps.cpl_min_conversions ?? 15} conversions to act
                                </span>
                            </div>
                        </div>
                        {writable && (
                            <Button
                                isBlack
                                className="shrink-0"
                                onClick={runDry}
                                disabled={running || dormant}
                            >
                                {running ? "Analyzing…" : "Run dry-run"}
                            </Button>
                        )}
                    </div>
                </div>
            </Card>

            {dormant && !result ? (
                <Card title="Suggestions">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <DormantPanel
                            icon="magic-pencil"
                            title="Optimizer coming soon"
                            sub="Once campaigns are live, the optimizer will rank them by cost-per-lead and propose scale / kill / budget-shift moves here — each shown with its reason, and never applied without your say-so."
                        />
                    </div>
                </Card>
            ) : result ? (
                <>
                    {result.moves.length > 0 && (
                        <div className="grid grid-cols-3 gap-3 max-sm:grid-cols-1">
                            <HeroStat
                                label="Winners to scale"
                                glyph="star-fill"
                                glyphClass="fill-primary-02"
                                accent="var(--primary-02)"
                                value={String(winners)}
                                foot="CPL at or below target"
                            />
                            <HeroStat
                                label="Losers to kill"
                                glyph="trash-think"
                                glyphClass="fill-primary-03"
                                accent="var(--primary-03)"
                                delay={60}
                                value={String(losers)}
                                foot="CPL above target"
                            />
                            <HeroStat
                                label="Mode"
                                glyph="lock"
                                glyphClass="fill-primary-05"
                                accent="var(--primary-05)"
                                delay={120}
                                value={result.dry_run ? "Preview" : "Applied"}
                                foot="No spend changed in a dry-run"
                            />
                        </div>
                    )}
                    <Card title="Suggested moves">
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Campaign</th>
                                        <th>Move</th>
                                        <th>CPL</th>
                                        <th>Reason</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {result.moves.length === 0 ? (
                                        <tr>
                                            <td colSpan={4}>
                                                <DormantPanel
                                                    icon="check-circle"
                                                    title="Nothing to change"
                                                    sub="No active campaign has enough data to act on yet, or every campaign is already performing at or below its target cost-per-lead."
                                                />
                                            </td>
                                        </tr>
                                    ) : (
                                        result.moves.map((m, i) => (
                                            <tr key={`${m.plan_id}-${i}`}>
                                                <td className="font-mono text-caption text-t-secondary td-num">
                                                    {m.plan_id}
                                                </td>
                                                <td>
                                                    <Badge variant={moveVariant(m.move)}>{moveLabel(m.move)}</Badge>
                                                </td>
                                                <td className="text-t-secondary tabular-nums whitespace-nowrap">
                                                    {m.cpl_minor != null ? fmtMoney(m.cpl_minor, currency) : "—"}
                                                </td>
                                                <td className="text-t-secondary">{moveReason(m.reason)}</td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </>
            ) : (
                <Card title="Suggestions">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <DormantPanel
                            icon="magic-pencil"
                            title="No analysis yet"
                            sub="Run a dry-run to preview the optimizer's scale / kill / budget-shift suggestions for your live campaigns. Every move is shown with its reason; nothing is applied automatically."
                        />
                    </div>
                </Card>
            )}
        </div>
    );
}
