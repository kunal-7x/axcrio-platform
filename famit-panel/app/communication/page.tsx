"use client";

// ============================================================================
// /communication — the omnichannel Communication tab (new Engage-nav section,
// alongside WhatsApp). communication/COMMUNICATION-MASTER-PLAN.md §7.
//
// ONE page, four views (Channels / Builder / Inbox / Analytics) behind a SubNav,
// scoped by a ChannelPicker. Telegram is the live channel (W1-2: founder hot-lead
// alert + post-call auto-summary + the LLM brain reply); Email/SMS are coming-soon
// (W3/W5); WhatsApp deep-links to its own live workspace (earner-safe — no
// duplicated Meta logic). EntitlementGuard mirrors the HIDE/LOCK cosmetics; the
// backend 404 (COMM_ENABLED off) is the real boundary -> a calm coming-soon card.
// Core_2, Inter Display, zero raw hex.
// ============================================================================

import Layout from "@/components/Layout";
import EntitlementGuard from "@/components/EntitlementGuard";
import { CommunicationBody } from "./_body";

export default function CommunicationPage() {
    return (
        <EntitlementGuard featureKey="engage.communication" featureLabel="Communication">
            <Layout title="Communication">
                <CommunicationBody />
            </Layout>
        </EntitlementGuard>
    );
}
