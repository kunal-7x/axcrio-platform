"use client";
// Property Studio — 2D floor plan → interactive 3D model, in a Brainwave-2.0-styled
// workspace embedded inside the haptica dashboard. All UI state + pmodel calls live
// in _studio/store.ts; the shell is fully scoped under .pstudio (studio.css) so the
// core dashboard is untouched.
import Layout from "@/components/Layout";
import StudioShell from "./_studio/StudioShell";
import "./studio.css";

export default function Page() {
    return (
        <Layout title="Property Studio">
            <StudioShell />
        </Layout>
    );
}
