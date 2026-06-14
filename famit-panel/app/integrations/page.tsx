"use client";

// ============================================================================
// /integrations — the Universal Connector / Provider registry (the vendor view).
// design crazy-ui-security §B + PROVIDER-FRAMEWORK-PLAN §9. ONE page, four views
// (Providers / Self-hosted / Health / Audit) via a sub-nav pill-strip. Video
// Studio is the FIRST consumer of this registry; WhatsApp-AI / voice-LLM / RAG /
// image plug in next by declaring a capability.
//
// SECURITY / TRUST: every backend route is RLS-scoped + the real boundary; this is
// the management surface. A vendor adds a Hosted-API provider + their OWN key
// (encrypted, revealable via PIN step-up); self-hosted is super-admin-only (the
// twin). EntitlementGuard mirrors the HIDE/LOCK cosmetics; the backend 404/402 is
// authoritative. Dormant-safe: a 404 (flag off / not entitled) renders a calm
// coming-soon card, never an error wall. Core_2, Inter Display, zero raw hex.
// ============================================================================

import Layout from "@/components/Layout";
import EntitlementGuard from "@/components/EntitlementGuard";
import { IntegrationsBody } from "./_body";

export default function IntegrationsPage() {
    return (
        <EntitlementGuard featureKey="integrations.providers" featureLabel="Integrations">
            <Layout title="Integrations">
                <IntegrationsBody admin={false} />
            </Layout>
        </EntitlementGuard>
    );
}
