"use client";

// Ad Automation — the SHARED data spine (V2-W5).
//
// The four sub-pages (Command & Analytics, Run a Campaign, Creative, Connections)
// each need the same two reads — GET /ads/health + GET /ads/campaigns — plus the
// derived cockpit numbers (active/pending counts, currency, today's spend) and the
// visibility-gated realtime poll. This hook lifts that spine OUT of the old
// monolithic page.tsx so every page shares ONE source of truth (no drift, no
// duplicated fetch logic). Pure data; renders nothing.

import { useCallback, useEffect, useState } from "react";
import {
    getAdsHealth,
    getAdsCampaigns,
    useRealtimeRefresh,
    type AdsHealth,
    type AdsCampaign,
    type AdsStatusResponse,
    type ReadResult,
} from "./_lib";

export type AdsSpine = {
    hc: AdsHealth | null;
    health: ReadResult<AdsHealth> | null;
    camps: ReadResult<AdsStatusResponse> | null;
    campData: AdsStatusResponse | null;
    rows: AdsCampaign[];
    loading: boolean;
    moduleDormant: boolean;
    activeCount: number;
    pendingCount: number;
    totalCount: number;
    currency: string;
    spendTodayMinor: number;
    /** honest engine status for the page-head hint (3 states, token tones) */
    engineStatus: { label: string; tone: string };
    refreshAll: () => void;
    healthLoading: boolean;
    campsLoading: boolean;
};

export function useAdsSpine(pollMs = 30000): AdsSpine {
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

    useRealtimeRefresh(refreshAll, pollMs);

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

    const anyProvider =
        hc?.providers.meta === "configured" || hc?.providers.google === "configured";
    const engineStatus: { label: string; tone: string } = !hc
        ? { label: "Connecting…", tone: "var(--text-tertiary)" }
        : !anyProvider
        ? { label: "Awaiting ad accounts", tone: "var(--text-tertiary)" }
        : hc.dry_run
        ? { label: "Test mode · no real spend", tone: "var(--primary-01)" }
        : { label: "Live spend", tone: "var(--primary-02)" };

    const loading = (healthLoading && !hc) || (campsLoading && !campData);

    return {
        hc,
        health,
        camps,
        campData,
        rows,
        loading,
        moduleDormant,
        activeCount,
        pendingCount,
        totalCount: rows.length,
        currency,
        spendTodayMinor: campData?.spend_today_minor ?? 0,
        engineStatus,
        refreshAll,
        healthLoading,
        campsLoading,
    };
}
