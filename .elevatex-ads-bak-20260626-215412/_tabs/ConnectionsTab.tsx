"use client";

// Ad-Engine · Connections / Vault tab (W7.8).
//
// A THIN HOST. The whole connector surface — provider cards (Meta / Google /
// WhatsApp / telephony), OAuth connect, reveal-secret PIN step-up, the health
// table and the audit drawer — already exists at /integrations and is RLS-scoped
// + dormant-safe by construction. W7.8 does NOT rebuild any of it: it EMBEDS the
// verbatim `IntegrationsBody` (which composes _provider-card / _add-provider-modal
// / _reveal-pin / _health-table / _audit-drawer) inside the ad-engine tab shell,
// wrapped in the SAME `EntitlementGuard featureKey="integrations.providers"` the
// integrations page uses. The user connects an ad account without ever leaving
// /ads.
//
// PIXEL-IDENTICAL by reuse: the embedded body IS the integrations page body, so
// every surface, badge, modal and the loading / empty / dormant states render
// exactly as they do at /integrations — same Core_2 kit, same tokens, zero raw
// hex here. The ONLY thing this file owns is the embed + the page-level realtime
// tick shared by every other ad-engine tab.
//
// Layering note: page.tsx already wraps the whole tab set in <Layout>, so — unlike
// app/integrations/page.tsx — this host renders the EntitlementGuard + body WITHOUT
// a second Layout. Data flows through lib/integrations.ts unchanged.
//
// Dormant-safe: when the workspace isn't entitled for integrations the body itself
// renders its calm "Connect any AI model or tool" coming-soon card (a 404 → dormant),
// never an error wall; EntitlementGuard mirrors HIDE/LOCK cosmetics on top.
// Vendor view → admin={false} (RLS keeps it tenant-scoped; self-hosted stays
// admin-managed). Write controls inside the body (add / edit / reveal / connect)
// are surfaced for managers+; the read-only `writable=false` case still sees the
// cards and health, just without the mutating affordances the body gates itself.

import { useCallback } from "react";
import EntitlementGuard from "@/components/EntitlementGuard";
import { IntegrationsBody } from "@/app/integrations/_body";
import { useRealtimeRefresh } from "../_lib";
import type { AdsTabProps } from "../_shared";
import AdConnectPresets from "./_connect-presets";
import OAuthConnectPanel from "./_oauth-connect-panel";

export default function ConnectionsTab({ toast, refresh }: AdsTabProps) {
    // Visibility-gated 30s tick — the shared ad-engine realtime spine. Keeps the
    // page-level state warm on focus alongside the embedded body's own react-query
    // freshness; the body owns its provider/health reloads internally.
    const tick = useCallback(() => refresh(), [refresh]);
    useRealtimeRefresh(tick, 30000);

    return (
        <EntitlementGuard featureKey="integrations.providers" featureLabel="Integrations">
            <div className="flex flex-col gap-6">
                {/* The ad-specific "paste your keys → Connected" wizard (BLINDSPOTS B2/B3/B15):
                    guided Meta / Google / WhatsApp presets that set named_provider + capability and
                    write the exact credential blob each connector reads, then verify it round-trips. */}
                {/* One-click OAuth connect + lead-source claim + leadgen subscribe + vendor-own-card
                    funding (BLINDSPOTS B4/B16/B17/B13-B15). Complements the paste-key presets below. */}
                <OAuthConnectPanel toast={toast} refresh={refresh} />
                <AdConnectPresets toast={toast} refresh={refresh} />
                {/* The full generic provider/health/reveal surface, reused verbatim from /integrations. */}
                <IntegrationsBody admin={false} />
            </div>
        </EntitlementGuard>
    );
}
