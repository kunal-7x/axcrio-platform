"use client";

// ============================================================================
// Agent Tools (Grow → Agent Tools) — TENANT surface of the agent tooling system.
// A tenant grants + gates what THEIR voice agent can do, scoped to their own campaigns (server-
// enforced isolation). Shares the console with the super-admin page; only the API wiring differs.
// ============================================================================

import Layout from "@/components/Layout";
import TolexConsole from "@/components/TolexConsole";
import { TolexApiTenant } from "@/lib/api";

export default function AgentToolsPage() {
    return (
        <Layout title="Agent Tools">
            <TolexConsole api={TolexApiTenant} scopeLabel="All campaigns (default)" />
        </Layout>
    );
}
