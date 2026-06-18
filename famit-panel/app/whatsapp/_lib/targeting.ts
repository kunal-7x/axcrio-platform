// W16 — WhatsApp audience TARGETING signals (beyond temperature).
// EXTENDS the reused run-campaign audience lib (_lib/audience.ts) with the founder's
// richer targets: Dead, requested-brochure, follow-up-pending, campaign-X, agent-Y,
// and named custom segments. Pure, client-side, truthful preview — same posture as
// the run-campaign audience builder. We DERIVE the behavioural signals from the
// existing Lead fields (status / last_outcome / tags) so this works today; when the
// voice_ops/whatsapp audience API mounts, the same predicate maps to its AudienceSpec.

import { type Lead } from "@/lib/api";
import { tempOf, type Temp } from "./audience";

// The full temperature set incl. Dead (the run lib classifies hot/warm/cold; Dead
// is a status/outcome signal layered on top).
export type WaTemp = Temp | "dead";

const DEAD_WORDS = ["dead", "lost", "opt_out", "opted_out", "not_interested", "do_not_call", "dnc"];
const BROCHURE_WORDS = ["brochure", "requested_brochure", "send_brochure", "pdf"];
const FOLLOWUP_WORDS = ["callback", "follow_up", "followup", "follow-up", "pending"];

function blob(l: Lead): string {
    return [l.status, l.last_outcome, ...(l.tags || [])].filter(Boolean).join(" ").toLowerCase();
}

export function waTempOf(l: Lead): WaTemp {
    if (DEAD_WORDS.some((w) => blob(l).includes(w))) return "dead";
    return tempOf(l);
}

export function isRequestedBrochure(l: Lead): boolean {
    return BROCHURE_WORDS.some((w) => blob(l).includes(w));
}

export function isFollowUpPending(l: Lead): boolean {
    return FOLLOWUP_WORDS.some((w) => blob(l).includes(w));
}

// The campaign/agent dimensions a lead belongs to (derived from tags/batch).
export function campaignOf(l: Lead): string {
    return l.batch_id || (l.tags || []).find((t) => t.startsWith("campaign:"))?.slice(9) || "";
}
export function agentOf(l: Lead): string {
    return (l.tags || []).find((t) => t.startsWith("agent:"))?.slice(6) || "";
}

// The composable W16 targeting spec (a superset of the run AudienceFilter).
export type WaTargeting = {
    temps: Set<WaTemp>;
    requestedBrochure: boolean;
    followUpPending: boolean;
    campaign: string; // "" = any
    agent: string; // "" = any
    segment: string; // "" = any (matches a tag literally)
    query: string;
};

export const EMPTY_TARGETING: WaTargeting = {
    temps: new Set(),
    requestedBrochure: false,
    followUpPending: false,
    campaign: "",
    agent: "",
    segment: "",
    query: "",
};

// True if ANY positive targeting signal is set (else the audience is empty —
// fail-closed: the founder must positively choose a target, never "send to all").
export function hasTarget(t: WaTargeting): boolean {
    return (
        t.temps.size > 0 ||
        t.requestedBrochure ||
        t.followUpPending ||
        !!t.campaign ||
        !!t.agent ||
        !!t.segment
    );
}

// Resolve the targeting spec over a lead pool. AND across active dimensions.
export function applyTargeting(pool: Lead[], t: WaTargeting, manual: Set<string>): Lead[] {
    // hand-picked rows always win (union), like the run-campaign builder.
    if (manual.size > 0) return pool.filter((l) => manual.has(l.id));
    if (!hasTarget(t)) return [];
    return pool.filter((l) => {
        if (t.temps.size > 0 && !t.temps.has(waTempOf(l))) return false;
        if (t.requestedBrochure && !isRequestedBrochure(l)) return false;
        if (t.followUpPending && !isFollowUpPending(l)) return false;
        if (t.campaign && campaignOf(l) !== t.campaign) return false;
        if (t.agent && agentOf(l) !== t.agent) return false;
        if (t.segment && !(l.tags || []).includes(t.segment)) return false;
        return true;
    });
}

export type WaBreakdown = { hot: number; warm: number; cold: number; dead: number; total: number };
export function waBreakdown(audience: Lead[]): WaBreakdown {
    const b: WaBreakdown = { hot: 0, warm: 0, cold: 0, dead: 0, total: audience.length };
    for (const l of audience) b[waTempOf(l)]++;
    return b;
}

// Distinct campaigns / agents present in the pool (for the filter dropdowns).
export function distinctCampaigns(pool: Lead[]): string[] {
    return Array.from(new Set(pool.map(campaignOf).filter(Boolean))).sort();
}
export function distinctAgents(pool: Lead[]): string[] {
    return Array.from(new Set(pool.map(agentOf).filter(Boolean))).sort();
}
