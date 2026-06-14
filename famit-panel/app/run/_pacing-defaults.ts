// ============================================================================
// WAVE C · Pacing defaults — pure, side-effect-free helpers.
//
// The single hardcoded outbound DID was carrier-blocked once by a 486-spam storm,
// so SANE, DID-PROTECTIVE pacing defaults matter. These are DEFAULTS the founder
// can always override (the Run page never overwrites a manual edit — it only
// *suggests* via a one-click chip). Two layers, audience wins when present:
//
//   1. PLAN floor (Starter / Growth / Enterprise) — entitlement-shaped ceilings.
//   2. AUDIENCE-aware override — a big cold list can pace up; a tiny list paces down.
//
// Source of the numbers: design/RUN-PLATFORM-MASTER-PLAN.md §1d (per-plan caps +
// the audience override table). Pure functions only — no fetch, no state.
// ============================================================================

export type PlanKey = "starter" | "growth" | "enterprise";

export type Pacing = {
    concurrency: number;
    hourlyCap: number; // 0 = no cap
    dailyCap: number; // 0 = no cap
};

// Per-plan baseline (RUN-PLATFORM-MASTER-PLAN §1d).
export const PLAN_PACING: Record<PlanKey, Pacing> = {
    starter: { concurrency: 2, hourlyCap: 60, dailyCap: 200 },
    growth: { concurrency: 3, hourlyCap: 120, dailyCap: 500 },
    enterprise: { concurrency: 3, hourlyCap: 240, dailyCap: 0 },
};

// Map a campaign/account tier-ish hint to a plan key. We don't have a hard
// "plan" field on the client, so we infer conservatively (Starter is the safe
// floor) and let the audience layer + the founder's edit refine it.
export function planFromTier(tier?: string): PlanKey {
    switch ((tier || "").toLowerCase()) {
        case "premium":
        case "enterprise":
            return "enterprise";
        case "standard":
        case "growth":
            return "growth";
        default:
            return "starter";
    }
}

// Audience-aware suggestion. NEVER overrides a manual edit — the caller decides
// when to apply this. Protects the single DID from 486-spam (small list → conc 1,
// no cap; large list → pace up but stay inside the plan ceiling).
//   audience >= 200 → conc 3 / hourly 120
//   26–199          → conc 2 / hourly 60
//   <= 25           → conc 1 / no cap
export function suggestPacing(plan: PlanKey, audienceCount: number): Pacing {
    const ceil = PLAN_PACING[plan];
    let base: Pacing;
    if (audienceCount >= 200) {
        base = { concurrency: 3, hourlyCap: 120, dailyCap: ceil.dailyCap };
    } else if (audienceCount >= 26) {
        base = { concurrency: 2, hourlyCap: 60, dailyCap: ceil.dailyCap };
    } else {
        // tiny list → gentle, no throttle needed
        base = { concurrency: 1, hourlyCap: 0, dailyCap: 0 };
    }
    // Never exceed the plan ceiling on concurrency / hourly.
    return {
        concurrency: Math.min(base.concurrency, ceil.concurrency),
        hourlyCap:
            ceil.hourlyCap === 0
                ? base.hourlyCap
                : base.hourlyCap === 0
                ? 0
                : Math.min(base.hourlyCap, ceil.hourlyCap),
        dailyCap: ceil.dailyCap === 0 ? base.dailyCap : Math.min(base.dailyCap || ceil.dailyCap, ceil.dailyCap),
    };
}

// A short human label for the suggestion chip.
export function pacingLabel(p: Pacing): string {
    const parts = [`${p.concurrency} concurrent`];
    if (p.hourlyCap > 0) parts.push(`${p.hourlyCap}/hr`);
    if (p.dailyCap > 0) parts.push(`${p.dailyCap}/day`);
    else parts.push("no daily cap");
    return parts.join(" · ");
}

// Why-this-suggestion microcopy (DID-protective rationale, founder-readable).
export function pacingReason(audienceCount: number): string {
    if (audienceCount >= 200)
        return "Large list — paced up, capped to protect the number from carrier blocks.";
    if (audienceCount >= 26)
        return "Medium list — a steady 2-at-a-time keeps the line healthy.";
    return "Small list — one at a time, no throttle needed.";
}
