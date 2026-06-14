"use client";

// ============================================================================
// /super-admin/integrations — the super-admin TWIN of the Integrations registry
// (design crazy-ui-security §B). Same surface, ADMIN scope: lists the `_global`
// platform catalogue + every tenant's providers (via /provider-registry/admin/*),
// can register a self-hosted endpoint (SSRF-validated, super-admin-only), and adds
// platform keys (scope='ai_provider', masked-only to vendors). The backend
// require_super_admin (which EXCLUDES the legacy static password — control-security
// #1) is the real boundary; SuperAdminGuard is the cosmetic gate.
// ============================================================================

import Layout from "@/components/Layout";
import { SuperAdminGuard, SuperAdminHeaderF3 } from "../_shared";
import { IntegrationsBody } from "../../integrations/page";

export default function SuperAdminIntegrationsPage() {
    return (
        <SuperAdminGuard>
            <Layout title="Integrations">
                <SuperAdminHeaderF3 />
                <IntegrationsBody admin />
            </Layout>
        </SuperAdminGuard>
    );
}
