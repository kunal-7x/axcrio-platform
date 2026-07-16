"use client";

// Ad Automation › Creative (V2-W5).
//
// This page CURATES — it does not rebuild the Image Studio. One generation surface
// in the app, not two. Behind the app-native TRANSPARENT <Tabs>:
//   Library      → the vendor's own ad creatives (Image Studio assets, platform=meta),
//                  read/curate only, with a deep-link card to the full Creative Studio
//   Moderation   → the ad engine's UNIQUE value: per-variant RERA / Housing / brand
//                  verdicts from /ads/creative/variants
//   Health Score → a pre-flight scorer that ranks variants 0–100 before they spend
//
// Heavy generation/editing lives in /creative (Creative Studio); the link-card
// deep-links there. Token-pure, dormant-safe.

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Layout from "@/components/Layout";
import Tabs from "@/components/Tabs";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import { TabsOption } from "@/types/tabs";
import { listAssets, type Asset } from "@/lib/assets";
import { DormantPanel } from "../_shared";
import {
    getCreativeVariants,
    useRealtimeRefresh,
    type CreativeVariant,
    type ReadResult,
} from "../_lib";

const TABS: (TabsOption & { key: string })[] = [
    { id: 1, name: "Library", key: "library" },
    { id: 2, name: "Moderation", key: "moderation" },
    { id: 3, name: "Health Score", key: "health" },
];

export default function AdsCreativePage() {
    return (
        <Suspense fallback={<Layout title="Creative"><div className="py-24" /></Layout>}>
            <CreativeInner />
        </Suspense>
    );
}

function CreativeInner() {
    const router = useRouter();
    const search = useSearchParams();

    const tabKey = search.get("tab") || "library";
    const active = TABS.find((t) => t.key === tabKey) || TABS[0];
    const setTab = (opt: TabsOption) => {
        const t = TABS.find((x) => x.id === opt.id) || TABS[0];
        router.replace(t.key === "library" ? "/ads/creative" : `/ads/creative?tab=${t.key}`, {
            scroll: false,
        });
    };

    return (
        <Layout title="Creative">
            <Tabs className="mb-5 max-w-full overflow-x-auto scrollbar-none" items={TABS} value={active} setValue={setTab} />

            {active.key === "library" && <LibraryPanel />}
            {active.key === "moderation" && <ModerationPanel />}
            {active.key === "health" && <HealthScorePanel />}
        </Layout>
    );
}

/* ----------------------------------------------------------------- Library */

function LibraryPanel() {
    const [assets, setAssets] = useState<Asset[] | null>(null);
    const [busy, setBusy] = useState(true);

    useEffect(() => {
        setBusy(true);
        listAssets({ platform: "meta", limit: 24, sort: "newest" })
            .then((p) => setAssets(p.assets || []))
            .catch(() => setAssets([]))
            .finally(() => setBusy(false));
    }, []);

    return (
        <div className="space-y-5">
            <StudioLinkCard />
            <Card title="Ad creative library">
                <div className="p-3">
                    {busy && !assets ? (
                        <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-3 max-sm:grid-cols-2">
                            {Array.from({ length: 8 }).map((_, i) => (
                                <div key={i} className="aspect-square rounded-2xl skeleton" />
                            ))}
                        </div>
                    ) : !assets || assets.length === 0 ? (
                        <div className="state-block">
                            <span className="grid place-items-center size-12 rounded-2xl bg-b-surface2 mb-3">
                                <Icon name="image" className="size-6 fill-t-tertiary" />
                            </span>
                            <div className="text-button text-t-primary">No ad creatives yet</div>
                            <p className="text-caption text-t-tertiary mt-1 max-w-sm">
                                Generate on-brand banners in the Creative Studio, or let the Run-a-Campaign
                                wizard make a set from your campaign brief. Approved creatives appear here.
                            </p>
                        </div>
                    ) : (
                        <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-3 max-sm:grid-cols-2">
                            {assets.map((a) => (
                                <div
                                    key={a.id}
                                    className="group relative aspect-square rounded-2xl overflow-hidden bg-b-surface1 ring-1 ring-s-subtle bg-cover bg-center dark:bg-shade-04/40"
                                    style={a.thumb_url || a.url ? { backgroundImage: `url(${a.thumb_url || a.url})` } : undefined}
                                    title={a.headline || a.kind || "creative"}
                                >
                                    {a.moderation_status && (
                                        <span className="absolute top-2 left-2">
                                            <Badge variant={modVariant(a.moderation_status)} dot>
                                                {modLabel(a.moderation_status)}
                                            </Badge>
                                        </span>
                                    )}
                                    <span className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-shade-09/70 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                                        <span className="block text-caption text-t-light line-clamp-1">
                                            {a.headline || a.kind || "Creative"}
                                        </span>
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </Card>
        </div>
    );
}

function StudioLinkCard() {
    return (
        <div className="flex items-center gap-4 p-5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle max-sm:flex-col max-sm:items-stretch">
            <span className="grid place-items-center size-12 rounded-2xl bg-b-surface1 shrink-0 dark:bg-shade-04">
                <Icon name="magic-pencil" className="size-6 fill-primary-01" />
            </span>
            <div className="min-w-0 flex-1">
                <div className="text-button text-t-primary">Generate or edit in Creative Studio</div>
                <p className="text-caption text-t-tertiary mt-0.5">
                    The full design engine — batch banners from a brief, edit, brand-kit, video.
                    This page curates what you ship to ads.
                </p>
            </div>
            <Button as="link" href="/creative" isStroke icon="arrow" className="!h-10 shrink-0">
                Open Creative Studio
            </Button>
        </div>
    );
}

/* -------------------------------------------------------------- Moderation */

function ModerationPanel() {
    const [res, setRes] = useState<ReadResult<{ ok: boolean; variants: CreativeVariant[] }> | null>(null);
    const [busy, setBusy] = useState(true);

    const load = useCallback(() => {
        setBusy(true);
        getCreativeVariants()
            .then(setRes)
            .finally(() => setBusy(false));
    }, []);
    useEffect(load, [load]);
    useRealtimeRefresh(load, 30000);

    const variants = res?.kind === "ok" ? res.data.variants || [] : [];

    if (res?.kind === "dormant") {
        return (
            <DormantPanel
                icon="filters"
                title="Moderation runs the moment creatives are generated"
                sub="Every ad variant clears an India-native gate — RERA, Housing, brand safety, broken-text — before a single rupee can run behind it. The verdicts appear here per variant."
            />
        );
    }

    return (
        <Card title="Creative moderation">
            <div className="p-3">
                {busy && variants.length === 0 ? (
                    <div className="space-y-2">
                        {Array.from({ length: 4 }).map((_, i) => (
                            <div key={i} className="h-16 rounded-2xl skeleton" />
                        ))}
                    </div>
                ) : variants.length === 0 ? (
                    <div className="state-block">
                        <span className="grid place-items-center size-12 rounded-2xl bg-b-surface2 mb-3">
                            <Icon name="filters" className="size-6 fill-t-tertiary" />
                        </span>
                        <div className="text-button text-t-primary">Nothing in the moderation queue</div>
                        <p className="text-caption text-t-tertiary mt-1 max-w-sm">
                            Generate variants in the Run-a-Campaign wizard; each clears the compliance gate
                            here before it can spend.
                        </p>
                    </div>
                ) : (
                    <div className="space-y-2">
                        {variants.map((v) => {
                            const status = (v.moderation_status || "pending").toLowerCase();
                            return (
                                <div
                                    key={v.variant_id}
                                    className="flex items-center gap-3 p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle"
                                >
                                    <span
                                        className="size-12 shrink-0 rounded-xl bg-cover bg-center bg-b-surface1 dark:bg-shade-04/40"
                                        style={v.url ? { backgroundImage: `url(${v.url})` } : undefined}
                                    />
                                    <div className="min-w-0 flex-1">
                                        <div className="text-body-2 text-t-primary line-clamp-1">
                                            {v.headline || "Untitled variant"}
                                        </div>
                                        {v.moderation_reason && (
                                            <div className="text-caption text-t-tertiary line-clamp-1 mt-0.5">
                                                {v.moderation_reason}
                                            </div>
                                        )}
                                    </div>
                                    <Badge
                                        variant={status === "approved" ? "success" : status.startsWith("blocked") || status === "blocked" ? "danger" : "warning"}
                                        dot
                                    >
                                        {status === "approved" ? "Approved" : status.startsWith("blocked") || status === "blocked" ? "Blocked" : "In review"}
                                    </Badge>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </Card>
    );
}

/* ------------------------------------------------------------- Health Score */

// A transparent pre-flight scorer: it rewards a clear headline, supporting body
// copy, a clean moderation pass, and a present visual. It is an ESTIMATE shown
// before spend — it graduates to a trained scorer on our own performance data.
function scoreVariant(v: CreativeVariant): { score: number; notes: { ok: boolean; text: string }[] } {
    const notes: { ok: boolean; text: string }[] = [];
    let score = 40; // base

    const headline = (v.headline || "").trim();
    const goodHeadline = headline.length >= 6 && headline.length <= 60;
    if (goodHeadline) score += 20;
    notes.push({
        ok: goodHeadline,
        text: goodHeadline ? "Headline length is scannable" : "Headline is missing or too long",
    });

    const hasBody = !!(v.primary_text && v.primary_text.trim().length >= 10);
    if (hasBody) score += 15;
    notes.push({ ok: hasBody, text: hasBody ? "Supporting copy present" : "Add supporting body copy" });

    const hasVisual = !!v.url;
    if (hasVisual) score += 15;
    notes.push({ ok: hasVisual, text: hasVisual ? "Visual attached" : "No visual yet" });

    const status = (v.moderation_status || "pending").toLowerCase();
    const passed = status === "approved";
    if (passed) score += 10;
    else if (status.startsWith("blocked") || status === "blocked") score -= 20;
    notes.push({
        ok: passed,
        text: passed ? "Cleared compliance" : status === "blocked" ? "Blocked by compliance" : "Awaiting moderation",
    });

    return { score: Math.max(0, Math.min(100, score)), notes };
}

function HealthScorePanel() {
    const [res, setRes] = useState<ReadResult<{ ok: boolean; variants: CreativeVariant[] }> | null>(null);
    const [busy, setBusy] = useState(true);

    const load = useCallback(() => {
        setBusy(true);
        getCreativeVariants()
            .then(setRes)
            .finally(() => setBusy(false));
    }, []);
    useEffect(load, [load]);

    const scored = useMemo(() => {
        if (res?.kind !== "ok") return [];
        return (res.data.variants || [])
            .map((v) => ({ v, ...scoreVariant(v) }))
            .sort((a, b) => b.score - a.score);
    }, [res]);

    if (res?.kind === "dormant") {
        return (
            <DormantPanel
                icon="star"
                title="Creative health scoring is ready"
                sub="Before a creative spends, it gets a 0–100 pre-flight score — headline clarity, supporting copy, visual, compliance — so the strongest variants run first. Generate a set to see it work."
            />
        );
    }

    return (
        <Card title="Creative health score" headContent={<span className="ml-auto text-caption text-t-tertiary max-md:hidden">Pre-flight estimate · graduates on your own data</span>}>
            <div className="p-3">
                {busy && scored.length === 0 ? (
                    <div className="space-y-2">
                        {Array.from({ length: 3 }).map((_, i) => (
                            <div key={i} className="h-24 rounded-2xl skeleton" />
                        ))}
                    </div>
                ) : scored.length === 0 ? (
                    <div className="state-block">
                        <span className="grid place-items-center size-12 rounded-2xl bg-b-surface2 mb-3">
                            <Icon name="star" className="size-6 fill-t-tertiary" />
                        </span>
                        <div className="text-button text-t-primary">No variants to score yet</div>
                        <p className="text-caption text-t-tertiary mt-1 max-w-sm">
                            Generate creatives and each gets a health score here, ranked strongest-first.
                        </p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {scored.map(({ v, score, notes }) => (
                            <div key={v.variant_id} className="flex items-start gap-4 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle">
                                <ScoreDial score={score} />
                                <div className="min-w-0 flex-1">
                                    <div className="text-button text-t-primary line-clamp-1">
                                        {v.headline || "Untitled variant"}
                                    </div>
                                    <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 max-sm:grid-cols-1">
                                        {notes.map((n, i) => (
                                            <li key={i} className="flex items-center gap-1.5 text-caption">
                                                <Icon
                                                    name={n.ok ? "check-circle-fill" : "info"}
                                                    className={`size-3.5 ${n.ok ? "fill-primary-02" : "fill-t-tertiary"}`}
                                                />
                                                <span className={n.ok ? "text-t-secondary" : "text-t-tertiary"}>{n.text}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </Card>
    );
}

function ScoreDial({ score }: { score: number }) {
    const tone =
        score >= 75 ? "var(--primary-02)" : score >= 50 ? "var(--primary-01)" : "var(--primary-03)";
    return (
        <div className="relative shrink-0 grid place-items-center size-16">
            <svg viewBox="0 0 36 36" className="size-16 -rotate-90">
                <circle cx="18" cy="18" r="15.5" fill="none" stroke="var(--stroke-subtle)" strokeWidth="3" />
                <circle
                    cx="18"
                    cy="18"
                    r="15.5"
                    fill="none"
                    stroke={tone}
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeDasharray={`${(score / 100) * 97.4} 97.4`}
                />
            </svg>
            <span className="absolute text-button text-t-primary tabular-nums">{score}</span>
        </div>
    );
}

function modVariant(s?: string): "success" | "warning" | "danger" | "neutral" {
    const v = (s || "").toLowerCase();
    if (v === "approved") return "success";
    if (v === "blocked" || v.startsWith("blocked")) return "danger";
    if (v === "pending") return "warning";
    return "neutral";
}
function modLabel(s?: string): string {
    const v = (s || "").toLowerCase();
    if (v === "approved") return "Approved";
    if (v === "blocked" || v.startsWith("blocked")) return "Blocked";
    if (v === "pending") return "In review";
    return s || "—";
}
