"use client";

// Famit Research — data wiring + presentation helpers (parallel to ai-manager/_lib.ts).
// React Query hooks over the tenant-scoped /research/* endpoints, plus the small transforms the
// scientific charts need (uncertainty-band geometry, regime/source metadata, on-brand colours).
// An OFFLINE sample keeps the premium dashboard alive even with no backend running (next dev alone),
// so a demo is always possible — clearly labelled, never passed off as a real tenant's data.

import { useQuery } from "@tanstack/react-query";
import {
    getResearchCall,
    getResearchDashboard,
    type ResearchCallDetail,
    type ResearchCallSummary,
    type ResearchDashboard,
    type ResearchTurn,
} from "@/lib/api";

// ── colours (all on-brand CSS vars) ──────────────────────────────────────────
export const C = {
    arousal: "var(--primary-01)", // Book Cloth clay — energy/activation
    friction: "var(--primary-03)", // Geist error red — resistance/friction
    engagement: "var(--chart-green)", // engagement/entrainment
    risk: "var(--primary-03)", // conversion risk (danger)
    pitch: "var(--primary-02)", // Kraft
    rate: "var(--chart-purple)", // Cloud medium
    pause: "var(--primary-05)", // Manilla
    muted: "var(--text-tertiary)",
};

export const REGIME_META: Record<
    string,
    { label: string; color: string; desc: string }
> = {
    steady: { label: "Steady", color: "var(--text-tertiary)", desc: "State stable around the caller's baseline." },
    warming: { label: "Warming", color: "var(--chart-green)", desc: "Arousal rising while friction stays low — engagement building." },
    rising_friction: { label: "Rising friction", color: "var(--primary-03)", desc: "Friction climbing turn-over-turn — an unhandled objection." },
    disengaging: { label: "Disengaging", color: "var(--primary-05)", desc: "Arousal falling with friction up — the caller is checking out." },
    resolving: { label: "Resolving", color: "var(--primary-02)", desc: "Friction receding after a peak — an objection being handled." },
};

export const SOURCE_META: Record<string, { label: string; tone: string; desc: string }> = {
    asr_metadata: { label: "ASR-metadata", tone: "warning", desc: "Cheap in-call signal: speech rate + pause timing from the transcript. No acoustic pitch/loudness." },
    acoustic_pyin: { label: "Acoustic (pYIN)", tone: "info", desc: "Post-call F0 (pYIN), loudness (RMS) and de Jong-Wempe speech rate from the recording." },
    egemaps: { label: "eGeMAPS", tone: "success", desc: "Full eGeMAPS functional set (openSMILE) aggregated per voiced turn." },
    demo: { label: "Demo", tone: "neutral", desc: "The real affect filter run over scripted archetype calls — sample data, not a live tenant." },
    sample: { label: "Offline sample", tone: "neutral", desc: "Local placeholder (backend not reachable). Connect the backend to see real data." },
};

export function regimeMeta(r: string) {
    return REGIME_META[r] || REGIME_META.steady;
}

// ── uncertainty-band geometry for a Recharts ComposedChart ───────────────────
// The filter covariance → a ±1σ band. We use the robust stacked-area trick: an invisible `lo`
// area + a translucent `span` (=hi-lo) area, with the mean drawn as a Line on top.
export type BandPoint = {
    t: number;
    turn: number;
    center: number;
    lo: number;
    span: number;
    regime: string;
    confidence: number;
};

export function riskCurve(turns: ResearchTurn[]): { t: number; turn: number; risk: number; intervene: boolean }[] {
    return (turns || []).map((t) => ({
        t: Number(t.t_sec ?? t.turn_num ?? 0),
        turn: Number(t.turn_num ?? 0),
        risk: Number(t.conversion_risk ?? 0),
        intervene: !!t.intervene,
    }));
}

export function bandData(
    turns: ResearchTurn[],
    valueKey: "arousal" | "friction" | "engagement",
    varKey: "arousal_var" | "friction_var" | "engagement_var"
): BandPoint[] {
    return (turns || []).map((t) => {
        const center = Number(t[valueKey] ?? 50);
        const sigma = Math.sqrt(Math.max(0, Number(t[varKey] ?? 0)));
        const lo = Math.max(0, center - sigma);
        const hi = Math.min(100, center + sigma);
        return {
            t: Number(t.t_sec ?? t.turn_num ?? 0),
            turn: Number(t.turn_num ?? 0),
            center: Math.round(center * 10) / 10,
            lo: Math.round(lo * 10) / 10,
            span: Math.round((hi - lo) * 10) / 10,
            regime: t.regime || "steady",
            confidence: Number(t.confidence ?? 0),
        };
    });
}

export function asRegimes(r: string[] | string | undefined): string[] {
    if (!r) return [];
    return Array.isArray(r) ? r : r.split(",").map((x) => x.trim()).filter(Boolean);
}

export function isConverted(c: ResearchCallSummary): boolean {
    return c.converted === true || c.converted === 1;
}

// The backend persists a tri-state: won / lost / outcome-unknown (has_outcome=0). An unknown call is
// stored as converted=0 too, so WITHOUT this guard it is indistinguishable from a real loss. Default
// true when the field is absent (demo / older payloads) so their math is unchanged.
export function hasOutcome(c: ResearchCallSummary): boolean {
    return c.has_outcome === undefined ? true : c.has_outcome === true || c.has_outcome === 1;
}

// ── hooks (offline sample on fetch failure so the page is never blank) ────────
export function useResearchDashboard(minutes: number) {
    return useQuery<ResearchDashboard>({
        queryKey: ["research", "dashboard", minutes],
        queryFn: () => getResearchDashboard(minutes).catch(() => sampleDashboard()),
        staleTime: 30_000,
        refetchOnWindowFocus: false,
    });
}

export function useResearchCall(callId: string | null) {
    return useQuery<ResearchCallDetail>({
        queryKey: ["research", "call", callId],
        enabled: !!callId,
        queryFn: () => getResearchCall(callId as string).catch(() => sampleCall(callId as string)),
        staleTime: 30_000,
        refetchOnWindowFocus: false,
    });
}

// ── OFFLINE sample (smooth placeholder curves; clearly source:"sample") ───────
const _ARCHES: Record<string, { ar: number[]; fr: number[]; outcome: string; won: boolean; deal: number }> = {
    "sample-7741": { ar: kf([50, 61, 65, 60, 57], 11), fr: kf([49, 48, 58, 52, 47], 11), outcome: "hot", won: true, deal: 120000 },
    "sample-7740": { ar: kf([50, 54, 62, 71, 77], 13), fr: kf([50, 48, 45, 41, 37], 13), outcome: "hot", won: true, deal: 85000 },
    "sample-7739": { ar: kf([50, 55, 60, 54, 49], 11), fr: kf([49, 50, 58, 66, 72], 11), outcome: "warm", won: false, deal: 0 },
    "sample-7738": { ar: kf([50, 48, 44, 33, 20], 12), fr: kf([49, 51, 58, 66, 75], 12), outcome: "cold", won: false, deal: 0 },
};

function kf(keys: number[], n: number): number[] {
    const out: number[] = [];
    for (let i = 0; i < n; i++) {
        const p = (i / (n - 1)) * (keys.length - 1);
        const a = Math.floor(p);
        const b = Math.min(a + 1, keys.length - 1);
        const f = p - a;
        out.push(Math.round((keys[a] + (keys[b] - keys[a]) * f) * 10) / 10);
    }
    return out;
}

function sampleTurns(ar: number[], fr: number[]): ResearchTurn[] {
    return ar.map((a, i) => ({
        turn_num: i + 1,
        t_sec: i * 3.6,
        speaker: "caller",
        f0_mean_hz: 168 + (a - 50) * 1.1,
        f0_range_hz: 30 + Math.abs(a - 50) * 0.6,
        f0_slope_hz_s: (a - (ar[i - 1] ?? a)) * 1.5,
        f0_var_hz: 12,
        loudness_db: -26 + (a - 50) * 0.18,
        speech_rate_sps: Math.max(2, 4.2 + (a - 50) * 0.04 - (fr[i] - 50) * 0.03),
        pause_ratio: Math.min(0.7, Math.max(0.04, 0.18 + (fr[i] - 50) * 0.006)),
        turn_latency_ms: 520 + (fr[i] - 50) * 9,
        voiced_sec: 2.6,
        arousal: a,
        arousal_var: 18,
        friction: fr[i],
        friction_var: 22,
        engagement: Math.max(0, Math.min(100, 50 + (50 - fr[i]) * 0.7 + (a - 50) * 0.2)),
        engagement_var: 24,
        valence_hint: Math.max(-1, Math.min(1, (a - fr[i]) / 40)),
        intent: fr[i] >= 62 ? "price-resistant" : fr[i] >= 56 ? "objecting" : a > 56 && fr[i] < 50 ? "interested" : "neutral",
        conversion_risk: Math.max(0, Math.min(100, 50 + (fr[i] - 50) * 1.5 - (a - 50) * 0.3)),
        intervene: fr[i] >= 64,
        confidence: 0.6,
        source: "sample",
        regime:
            fr[i] >= 60 && fr[i] > (fr[i - 1] ?? fr[i]) ? "rising_friction"
                : a < (ar[i - 1] ?? a) - 3 ? "disengaging"
                : a > (ar[i - 1] ?? a) + 3 && fr[i] < 56 ? "warming"
                : "steady",
        low_conf: true,
        transcript: "",
    }));
}

function sampleSummary(id: string): ResearchCallSummary {
    const a = _ARCHES[id] || _ARCHES["sample-7741"];
    const turns = sampleTurns(a.ar, a.fr);
    const regimes = Array.from(new Set(turns.map((t) => t.regime).filter((r) => r !== "steady")));
    const eng = turns.map((t) => t.engagement);
    return {
        call_id: id, turns: turns.length, duration_s: turns.length * 3.6,
        arousal_mean: avg(a.ar), arousal_peak: Math.max(...a.ar),
        friction_mean: avg(a.fr), friction_peak: Math.max(...a.fr),
        arousal_trend: a.ar[a.ar.length - 1] - a.ar[0],
        friction_trend: a.fr[a.fr.length - 1] - a.fr[0],
        engagement_mean: avg(eng), engagement_peak: Math.max(...eng),
        engagement_trend: Math.round((eng[eng.length - 1] - eng[0]) * 10) / 10,
        conversion_risk: turns[turns.length - 1].conversion_risk ?? 0,
        intervene: turns.some((t) => t.intervene),
        top_intent: a.won ? "interested" : a.fr[a.fr.length - 1] >= 60 ? "price-resistant" : "neutral",
        f0_mean_hz: 168, speech_rate_sps: 4.2, pause_ratio: 0.22,
        confidence: 0.6, source: "sample", regimes,
        outcome: a.outcome, converted: a.won, has_outcome: 1, deal_value: a.deal,
    };
}

function avg(xs: number[]) {
    return Math.round((xs.reduce((s, x) => s + x, 0) / xs.length) * 10) / 10;
}

export function sampleCall(id: string): ResearchCallDetail {
    const key = _ARCHES[id] ? id : "sample-7741";
    const a = _ARCHES[key];
    return { demo: true, call: sampleSummary(key), turns: sampleTurns(a.ar, a.fr) };
}

export function sampleDashboard(): ResearchDashboard {
    const calls = Object.keys(_ARCHES).map(sampleSummary);
    const labelled = calls.filter(hasOutcome);
    const won = labelled.filter((c) => c.converted);
    const lost = labelled.filter((c) => !c.converted);
    const regime_counts: Record<string, number> = {};
    calls.forEach((c) => asRegimes(c.regimes).forEach((r) => (regime_counts[r] = (regime_counts[r] || 0) + 1)));
    const arm = (cs: ResearchCallSummary[]) => ({
        n: cs.length,
        avg_friction_peak: avg(cs.map((c) => c.friction_peak)),
        avg_arousal_trend: avg(cs.map((c) => c.arousal_trend)),
        avg_friction_trend: avg(cs.map((c) => c.friction_trend)),
    });
    return {
        demo: true,
        enabled: false,
        range: { minutes: 1440 },
        summary: {
            calls: calls.length,
            turns: calls.reduce((s, c) => s + c.turns, 0),
            avg_arousal: avg(calls.map((c) => c.arousal_mean)),
            avg_friction: avg(calls.map((c) => c.friction_mean)),
            peak_friction: Math.max(...calls.map((c) => c.friction_peak)),
            avg_engagement: avg(calls.map((c) => c.engagement_mean ?? 50)),
            avg_conversion_risk: avg(calls.map((c) => c.conversion_risk ?? 0)),
            intervened: calls.filter((c) => c.intervene).length,
            avg_speech_rate: 4.2,
            confidence: 0.6,
            converted: won.length,
            conversion_rate: labelled.length ? Math.round((100 * won.length) / labelled.length) : 0,
        },
        outcomes: { won: arm(won), lost: arm(lost) },
        regime_counts,
        calls,
    };
}
