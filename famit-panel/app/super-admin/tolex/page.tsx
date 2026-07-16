"use client";

// ============================================================================
// Tolex — Agent Tooling & Capability Console (super-admin, PLATFORM scope).
// Sets the platform-wide default + per-campaign grants that tenants inherit unless they override
// (tenants manage their own under Grow → Agent Tools). The console body is shared (TolexConsole).
// ============================================================================

import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import TolexConsole from "@/components/TolexConsole";
import { TolexApiAdmin } from "@/lib/api";
import { SuperAdminGuard, SuperAdminHeaderF3 } from "../_shared";

const RUNTIME_NOTE = (
    <div className="mb-4 flex items-center gap-2 rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-3.5 text-body-2 text-t-secondary">
        <Icon name="info" className="size-4 fill-t-secondary shrink-0" />
        Control plane is live — configure grants now. The agent runtime hook is off; set
        <span className="font-mono text-caption mx-1">TOLEX_ENABLED=1</span> on the voice worker to let calls use these tools.
    </div>
);

export default function TolexPage() {
    return (
        <SuperAdminGuard>
            <Layout title="Tolex — Agent Tooling">
                <SuperAdminHeaderF3 />
                <TolexConsole api={TolexApiAdmin} runtimeNote={RUNTIME_NOTE} scopeLabel="Platform default" />
            </Layout>
        </SuperAdminGuard>
    );
}
