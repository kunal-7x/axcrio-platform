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
//
// W7-spine: page.tsx is now a THIN SHELL. Every reusable helper/widget lives in
// `./_shared`; every tab body lives in its own `./_tabs/*` file and is rendered
// uniformly below. The shell owns only the data spine (health + campaigns reads,
// the 30s visibility-gated poll) + the pill strip + props threading.

import { Suspense, useCallback, useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import { useMe, canWrite } from "@/lib/auth";
import {
    getAdsHealth,
    getAdsCampaigns,
    useRealtimeRefresh,
    type AdsHealth,
    type AdsCampaign,
    type AdsStatusResponse,
    type ReadResult,
} from "./_lib";
import type { Toast } from "./_shared";

// The full Ad-Engine tab set (FRONTEND_ARCHITECTURE §0). `command` carries the
// hero ROI cockpit; `campaigns` the live table + propose/approve/pause;
// `decisions` the optimizer moves feed; `guardrails` the caps/breaker/approval
// config; the remaining four are W7.0 dormant stubs filled by later waves. Each
// tab body lives in its own `_tabs/*` file — page.tsx renders them uniformly.
import CommandTab from "./_tabs/CommandTab";
import CampaignsTab from "./_tabs/CampaignsTab";
import CreativeTab from "./_tabs/CreativeTab";
import LeadsTab from "./_tabs/LeadsTab";
import AnalyticsTab from "./_tabs/AnalyticsTab";
import DecisionsTab from "./_tabs/DecisionsTab";
import GuardrailsTab from "./_tabs/GuardrailsTab";
import ConnectionsTab from "./_tabs/ConnectionsTab";

/* ----------------------------------------------------------------- types */

type TabKey =
    | "command"
    | "campaigns"
    | "creative"
    | "leads"
    | "analytics"
    | "decisions"
    | "guardrails"
    | "connections";

/* ============================================================== the page */

// The Leads / Analytics / Command tabs render <GlobalFilters/>, which calls
// useSearchParams() (?range/campaign/from/to). Under Next 15 static prerender
// that bails CSR unless a Suspense boundary sits above it — the same idiom the
// Dashboard (app/page.tsx) and Reports (app/analytics/page.tsx) already use. So
// the default export is a thin Suspense wrapper; AdsPageInner holds the body.
export default function AdsPage() {
    return (
        <Suspense fallback={<Layout title="Ad Engine"><div className="py-24" /></Layout>}>
            <AdsPageInner />
        </Suspense>
    );
}

function AdsPageInner() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [tab, setTab] = useState<TabKey>("command");
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

    const refreshAll = useCallback(() => {
        loadHealth();
        loadCamps();
    }, [loadHealth, loadCamps]);

    // Page-level realtime spine — visibility-gated 30s poll (the verified
    // analytics idiom, app/analytics/page.tsx:128-141). Keeps spend-vs-cap, ROAS
    // and the funnel fresh without draining in a background tab; the manual
    // Refresh button below still gives an instant re-pull. `refreshAll` is
    // useCallback-stable so the interval isn't torn down every render.
    useRealtimeRefresh(refreshAll, 30000);

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
        { key: "command", label: "Command", icon: "dashboard" },
        { key: "campaigns", label: "Campaigns", icon: "bag", badge: pendingCount },
        { key: "creative", label: "Creative", icon: "camera" },
        { key: "leads", label: "Leads", icon: "income" },
        { key: "analytics", label: "Analytics", icon: "chart" },
        { key: "decisions", label: "Decisions", icon: "help-think" },
        { key: "guardrails", label: "Guardrails", icon: "filters" },
        { key: "connections", label: "Connections", icon: "link" },
    ];

    const loading = (healthLoading && !hc) || (campsLoading && !campData);

    return (
        <Layout title="Ad Engine">
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

            {/* Section tabs + refresh (title is the single Layout heading) */}
            <div className="flex items-center gap-3 mb-5 max-sm:flex-col max-sm:items-stretch">
                <div className="flex items-center gap-1 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle w-fit max-w-full overflow-x-auto scrollbar-none">
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
                <button
                    onClick={refreshAll}
                    className="ml-auto max-sm:ml-0 inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50"
                    disabled={healthLoading || campsLoading}
                >
                    <Icon
                        name="clock"
                        className={`size-4 fill-current ${healthLoading || campsLoading ? "animate-spin" : ""}`}
                    />
                    Refresh
                </button>
            </div>

            {/* Command — the hero ROI cockpit (KPI strip + coming-soon explainer);
                W7.2 grows it into the full funnel + ROAS + pacing cockpit. */}
            {tab === "command" && (
                <CommandTab
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

            {/* Campaigns — the live table + propose/approve/pause. */}
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

            {tab === "creative" && (
                <CreativeTab writable={writable} loading={loading} toast={showToast} refresh={refreshAll} />
            )}

            {tab === "leads" && (
                <LeadsTab writable={writable} loading={loading} toast={showToast} refresh={refreshAll} />
            )}

            {tab === "analytics" && (
                <AnalyticsTab writable={writable} loading={loading} toast={showToast} refresh={refreshAll} />
            )}

            {/* Decisions — the optimizer's "Suggested moves" feed; W7.6 grows it
                into the full append-only AI decision log + guard-chain trace. */}
            {tab === "decisions" && (
                <DecisionsTab
                    writable={writable}
                    dormant={moduleDormant}
                    activeCount={activeCount}
                    currency={currency}
                    hc={hc}
                    toast={showToast}
                />
            )}

            {/* Guardrails — the caps/breaker/approval config board; W7.7 makes it
                editable (step-up save). */}
            {tab === "guardrails" && (
                <GuardrailsTab hc={hc} health={health} loading={loading} currency={currency} />
            )}

            {tab === "connections" && (
                <ConnectionsTab writable={writable} loading={loading} toast={showToast} refresh={refreshAll} />
            )}
        </Layout>
    );
}
