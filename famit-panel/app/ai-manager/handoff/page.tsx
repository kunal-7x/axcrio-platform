"use client";

// HANDOFF TEAM — the dedicated management view (/ai-manager/handoff).
//
// The home for managing the human-escalation roster: the people the AI warm-
// transfers a live caller to (and WhatsApps a hot lead to). The whole surface is
// the reusable <HandoffTeam> manager (list / add / reorder / enable / delete),
// wired to the LIVE /brain/handoff* backend. Manager-gated by the AI Manager nav
// group; read-only roles see the list but no edit controls (the component self-
// gates). Premium reference-kit, Inter Display, zero raw hex. Touches no app-wide
// component, no globals.css.

import Layout from "@/components/Layout";
import HandoffTeam from "../_handoff";

export default function HandoffPage() {
    return (
        <Layout title="Handoff Team">
            <div className="max-w-3xl">
                <HandoffTeam />
            </div>
        </Layout>
    );
}
