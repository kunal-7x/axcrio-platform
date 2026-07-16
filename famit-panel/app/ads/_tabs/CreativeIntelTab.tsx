"use client";

// Ad Automation › Command › Creative Intelligence (V2-W5) — the MOAT view.
//
// The signature Triple-Whale / Madgicx "Creative Cockpit" reimagined around the
// one metric no click-based competitor can surface: COST PER QUALIFIED CALL by
// creative. Each variant is a card with a thumbnail + a color-bar percentile rank
// across the fleet (green = top quartile, clay/red = bottom) on the four creative
// signals — Hook Rate, Hold Rate, CTR, and the moat metric. Sort by any signal.
//
// Reads GET /ads/analytics/per-ad (the real per-creative endpoint). Loose at the
// edges — the backend shape is additive — so every metric is plucked defensively
// and absent values render "—", never a fabricated 0. Dormant-safe: a 404/501/503
// renders the premium DormantPanel, never an error wall. Token-pure, zero raw hex.

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import Card from "@/components/Card";
import { DormantPanel, type ToastFn } from "../_shared";
import {
    getAdsAnalytics,
    useRealtimeRefresh,
    fmtMoney,
    type AdsAnalyticsResponse,
    type ReadResult,
} from "../_lib";

type Props = {
    writable: boolean;
    loading: boolean;
    toast: ToastFn;
    refresh: () => void;
    currency: string;
};

// One creative's normalized signals. Everything optional — the engine fills what
// it has; we never invent a metric. `score` keys are 0..1 percentile ranks we
// compute across the loaded fleet for the color bars.
type Creative = {
    id: string;
    label: string;
    thumb?: string;
    spendMinor: number;
    leads: number;
    qualified: number;
    hookRate?: number; // 0..100
    holdRate?: number; // 0..100
    ctr?: number; // 0..100
    cplMinor?: number | null;
    costPerQualMinor?: number | null; // the moat metric (paise)
};

function pluckNum(bag: Record<string, unknown>, ...keys: string[]): number | undefined {
    for (const k of keys) {
        const v = bag[k];
        if (typeof v === "number" && Number.isFinite(v)) return v;
    }
    return undefined;
}
function pluckStr(bag: Record<string, unknown>, ...keys: string[]): string | undefined {
    for (const k of keys) {
        const v = bag[k];
        if (typeof v === "string" && v.trim()) return v.trim();
    }
    return undefined;
}

function normalize(rows: Array<Record<string, unknown>>): Creative[] {
    return rows.map((r, i) => {
        const spendMinor = pluckNum(r, "spend_minor", "spend") ?? 0;
        const leads = pluckNum(r, "leads", "lead", "lead_count") ?? 0;
        const qualified = pluckNum(r, "qualified", "qualified_calls", "qualified_count") ?? 0;
        const cplMinor = pluckNum(r, "cpl_minor") ?? null;
        // moat metric: prefer an explicit field, else derive from spend / qualified.
        let costPerQualMinor = pluckNum(r, "cost_per_qualified_call_minor", "cpqc_minor") ?? null;
        if (costPerQualMinor === null && qualified > 0 && spendMinor > 0) {
            costPerQualMinor = Math.round(spendMinor / qualified);
        }
        return {
            id: pluckStr(r, "ad_id", "variant_id", "variant") ?? `ad-${i + 1}`,
            label: pluckStr(r, "headline", "name", "variant", "placement") ?? `Variant ${i + 1}`,
            thumb: pluckStr(r, "thumb_url", "url", "image_url"),
            spendMinor,
            leads,
            qualified,
            hookRate: pluckNum(r, "hook_rate", "thumb_stop_rate"),
            holdRate: pluckNum(r, "hold_rate"),
            ctr: pluckNum(r, "ctr"),
            cplMinor,
            costPerQualMinor,
        };
    });
}

// Percentile rank (0..1) of `v` within `all` — higher value = higher rank. For
// inverse metrics (cost: lower is better) pass invert=true so a low cost ranks high.
function percentile(v: number | null | undefined, all: number[], invert = false): number | null {
    if (v === null || v === undefined) return null;
    const xs = all.filter((x) => Number.isFinite(x));
    if (xs.length < 2) return null;
    const below = xs.filter((x) => (invert ? x > v : x < v)).length;
    return below / (xs.length - 1 || 1);
}

// Token color ramp for a 0..1 rank: top quartile = the success token, mid = clay,
// bottom = warm/red. Pure tokens.
function rankColor(rank: number | null): string {
    if (rank === null) return "var(--stroke2)";
    if (rank >= 0.75) return "var(--primary-02)";
    if (rank >= 0.4) return "var(--primary-01)";
    return "var(--primary-03)";
}

type SortKey = "costPerQual" | "hookRate" | "holdRate" | "ctr" | "spend";

const SORTS: { key: SortKey; label: string }[] = [
    { key: "costPerQual", label: "Cost / qualified call" },
    { key: "hookRate", label: "Hook rate" },
    { key: "holdRate", label: "Hold rate" },
    { key: "ctr", label: "CTR" },
    { key: "spend", label: "Spend" },
];

export default function CreativeIntelTab({ currency }: Props) {
    const [res, setRes] = useState<ReadResult<AdsAnalyticsResponse> | null>(null);
    const [busy, setBusy] = useState(true);
    const [sort, setSort] = useState<SortKey>("costPerQual");

    const load = useCallback(() => {
        setBusy(true);
        getAdsAnalytics("per-ad")
            .then(setRes)
            .finally(() => setBusy(false));
    }, []);
    useEffect(load, [load]);
    useRealtimeRefresh(load, 45000);

    const creatives = useMemo<Creative[]>(() => {
        if (res?.kind !== "ok") return [];
        return normalize(res.data.rows || []);
    }, [res]);

    // fleet arrays for percentile ranks
    const ranks = useMemo(() => {
        const hooks = creatives.map((c) => c.hookRate ?? NaN);
        const holds = creatives.map((c) => c.holdRate ?? NaN);
        const ctrs = creatives.map((c) => c.ctr ?? NaN);
        const cpq = creatives.map((c) => c.costPerQualMinor ?? NaN);
        return creatives.map((c) => ({
            id: c.id,
            hook: percentile(c.hookRate, hooks),
            hold: percentile(c.holdRate, holds),
            ctr: percentile(c.ctr, ctrs),
            cpq: percentile(c.costPerQualMinor ?? null, cpq, true),
        }));
    }, [creatives]);

    const sorted = useMemo(() => {
        const val = (c: Creative): number => {
            switch (sort) {
                case "costPerQual":
                    return c.costPerQualMinor ?? Number.POSITIVE_INFINITY;
                case "hookRate":
                    return -(c.hookRate ?? -1);
                case "holdRate":
                    return -(c.holdRate ?? -1);
                case "ctr":
                    return -(c.ctr ?? -1);
                case "spend":
                    return -c.spendMinor;
            }
        };
        return [...creatives].sort((a, b) => val(a) - val(b));
    }, [creatives, sort]);

    if (res?.kind === "dormant") {
        return (
            <DormantPanel
                icon="camera"
                title="Creative intelligence wakes up with your first spend"
                sub="Once campaigns run, every creative is ranked here by hook rate, hold rate, and the one signal no other platform measures — cost per qualified call. The winners rise to the top automatically."
            />
        );
    }

    return (
        <Card
            title="Creative intelligence"
            headContent={
                <div className="ml-auto flex items-center gap-2 max-md:hidden">
                    <span className="text-caption text-t-tertiary">Sort by</span>
                    <div className="flex items-center gap-1">
                        {SORTS.map((sopt) => (
                            <button
                                key={sopt.key}
                                onClick={() => setSort(sopt.key)}
                                className={`h-8 px-3 rounded-full text-caption transition-colors ${
                                    sort === sopt.key
                                        ? "bg-b-surface1 text-t-primary ring-1 ring-s-subtle dark:bg-shade-04"
                                        : "text-t-secondary hover:text-t-primary"
                                }`}
                            >
                                {sopt.label}
                            </button>
                        ))}
                    </div>
                </div>
            }
        >
            <div className="px-1 pb-2">
                {busy && creatives.length === 0 ? (
                    <div className="grid grid-cols-3 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1 p-3">
                        {Array.from({ length: 6 }).map((_, i) => (
                            <div key={i} className="h-64 rounded-3xl skeleton" />
                        ))}
                    </div>
                ) : creatives.length === 0 ? (
                    <div className="state-block m-3">
                        <span className="grid place-items-center size-12 rounded-2xl bg-b-surface2 mb-3">
                            <Icon name="camera" className="size-6 fill-t-tertiary" />
                        </span>
                        <div className="text-button text-t-primary">No creatives have spent yet</div>
                        <p className="text-caption text-t-tertiary mt-1 max-w-sm">
                            Launch a campaign and the engine ranks each variant here as soon as it
                            gathers signal — by hook rate, hold rate, and cost per qualified call.
                        </p>
                    </div>
                ) : (
                    <div className="grid grid-cols-3 gap-4 max-lg:grid-cols-2 max-sm:grid-cols-1 p-3">
                        {sorted.map((c, idx) => {
                            const rank = ranks.find((r) => r.id === c.id);
                            const isWinner = idx === 0 && (c.qualified > 0 || c.spendMinor > 0);
                            return (
                                <div
                                    key={c.id}
                                    className="group flex flex-col rounded-3xl bg-b-surface2 ring-1 ring-s-subtle overflow-hidden transition-shadow hover:shadow-widget"
                                >
                                    <div
                                        className="relative aspect-[16/10] bg-cover bg-center bg-b-surface1 dark:bg-shade-04/40"
                                        style={c.thumb ? { backgroundImage: `url(${c.thumb})` } : undefined}
                                    >
                                        {!c.thumb && (
                                            <span className="absolute inset-0 grid place-items-center">
                                                <Icon name="image" className="size-7 fill-t-tertiary/60" />
                                            </span>
                                        )}
                                        {isWinner && (
                                            <span className="absolute top-2.5 left-2.5 pill pill-success !py-0.5 !px-2 text-caption">
                                                Top performer
                                            </span>
                                        )}
                                    </div>
                                    <div className="flex flex-col gap-3 p-4">
                                        <div className="min-w-0">
                                            <div className="text-button text-t-primary line-clamp-1">{c.label}</div>
                                            <div className="text-caption text-t-tertiary mt-0.5">
                                                {fmtMoney(c.spendMinor, currency)} spent · {c.qualified} qualified
                                            </div>
                                        </div>

                                        {/* the moat metric, front and center */}
                                        <div className="flex items-end justify-between gap-2 pb-1 border-b border-s-subtle">
                                            <span className="text-caption text-t-tertiary">Cost / qualified call</span>
                                            <span className="text-h6 text-t-primary tabular-nums">
                                                {c.costPerQualMinor != null
                                                    ? fmtMoney(c.costPerQualMinor, currency)
                                                    : "—"}
                                            </span>
                                        </div>

                                        <RankBar label="Hook rate" pct={c.hookRate} rank={rank?.hook ?? null} suffix="%" />
                                        <RankBar label="Hold rate" pct={c.holdRate} rank={rank?.hold ?? null} suffix="%" />
                                        <RankBar label="CTR" pct={c.ctr} rank={rank?.ctr ?? null} suffix="%" />
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </Card>
    );
}

// A labeled metric row with a color-bar whose fill width = the metric and whose
// color = the fleet percentile rank (green top, clay mid, warm bottom).
function RankBar({
    label,
    pct,
    rank,
    suffix,
}: {
    label: string;
    pct?: number;
    rank: number | null;
    suffix?: string;
}) {
    const has = pct !== undefined && pct !== null;
    const width = has ? Math.max(4, Math.min(100, pct as number)) : 0;
    return (
        <div>
            <div className="flex items-center justify-between text-caption mb-1">
                <span className="text-t-tertiary">{label}</span>
                <span className="text-t-secondary tabular-nums">
                    {has ? `${Math.round((pct as number) * 10) / 10}${suffix || ""}` : "—"}
                </span>
            </div>
            <div className="h-1.5 rounded-full bg-b-surface1 dark:bg-shade-04/60 overflow-hidden">
                <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${width}%`, background: rankColor(rank) }}
                />
            </div>
        </div>
    );
}
