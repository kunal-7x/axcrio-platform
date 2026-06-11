// Run-Campaign Audience Builder — pure audience-resolution logic.
//
// The four "source" tabs are composable filters layered over one base pool,
// resolved entirely client-side so the preview count is ALWAYS truthful
// (spec §3). We then send the resolved lead_ids to /run so the backend dials
// exactly the previewed set.
//
//   BASE POOL  = stored leads ∪ leads from selected uploaded batches
//        ↓ TEMPERATURE FILTER (hot/warm/cold + optional custom score band)
//        ↓ MANUAL OVERRIDE   (hand-picked rows win; else everything that passed)
//        ↓ minus SUPPRESSION (backend pre-filters; we only show the count)
//   PREVIEW: "N leads will be called"

import { type Lead } from "@/lib/api";
import { type Temp } from "./types";

// ── Temperature classification — identical bands to app/leads/page.tsx ──
export function tempOf(lead: Lead): Temp {
    const s = lead.score ?? 0;
    if (s >= 70) return "hot";
    if (s >= 40) return "warm";
    return "cold";
}

export function inBand(lead: Lead, band: [number, number]): boolean {
    const s = lead.score ?? 0;
    return s >= band[0] && s <= band[1];
}

// ── Filter spec captured from the UI ──
export type AudienceFilter = {
    // Selected temperatures (empty ⇒ no temp constraint = all temps).
    temps: Set<Temp>;
    // Optional custom score band (only applied when `useBand` is on).
    useBand: boolean;
    band: [number, number];
    // Free-text search over name/phone (applied to the manual picker view).
    query: string;
};

// Apply temperature + custom-band filters to a pool.
export function applyTempFilter(pool: Lead[], f: AudienceFilter): Lead[] {
    const hasTemp = f.temps.size > 0;
    if (!hasTemp && !f.useBand) return pool;
    return pool.filter((l) => {
        if (hasTemp && !f.temps.has(tempOf(l))) return false;
        if (f.useBand && !inBand(l, f.band)) return false;
        return true;
    });
}

// Client-side name/phone search (used by the manual picker table).
export function applyQuery(pool: Lead[], query: string): Lead[] {
    const q = query.trim().toLowerCase();
    if (!q) return pool;
    return pool.filter(
        (l) =>
            l.name?.toLowerCase().includes(q) ||
            l.phone?.toLowerCase().includes(q)
    );
}

// Final resolved audience: hand-picked rows win; otherwise everything that
// passed the temperature/band filters.
export function resolveAudience(
    filtered: Lead[],
    manualSelected: Set<string>
): Lead[] {
    if (manualSelected.size === 0) return filtered;
    return filtered.filter((l) => manualSelected.has(l.id));
}

// Breakdown chips for the preview bar: counts by temperature.
export type Breakdown = { hot: number; warm: number; cold: number; total: number };

export function breakdownOf(audience: Lead[]): Breakdown {
    let hot = 0,
        warm = 0,
        cold = 0;
    for (const l of audience) {
        const t = tempOf(l);
        if (t === "hot") hot++;
        else if (t === "warm") warm++;
        else cold++;
    }
    return { hot, warm, cold, total: audience.length };
}

// De-dupe a merged pool by lead id (stored ∪ batch leads can overlap).
export function dedupeById(leads: Lead[]): Lead[] {
    const seen = new Set<string>();
    const out: Lead[] = [];
    for (const l of leads) {
        if (l.id && seen.has(l.id)) continue;
        if (l.id) seen.add(l.id);
        out.push(l);
    }
    return out;
}
