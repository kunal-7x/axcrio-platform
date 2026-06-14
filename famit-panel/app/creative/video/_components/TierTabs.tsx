"use client";

/**
 * TierTabs (W9, the signature control) — the composite-vs-AI toggle NO competitor
 * ships (master plan §10a/§12.1). Three render tiers as a row of rich selectable
 * cards, COMPOSITE the DEFAULT (cost-correct + needs no key):
 *
 *   COMPOSITE  — $0 gen-key floor (FFmpeg + Sarvam TTS + Whisper captions). Free of
 *                a gen API; metered TTS only. The honest cost-truth label.
 *   AI MOTION  — hosted gen (Kling / Hailuo via fal). PAID, BYO-key.
 *   PREMIUM    — Runway / Veo, approval-gated. PAID, hero-spot only.
 *
 * Token-pure (semantic tokens only, zero raw hex), keyboard-selectable, dark-mode +
 * reduced-motion safe. The selected tier drives the cost meter + the paid-gate copy
 * in VideoCreatePanel.
 */

import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import type { VideoTier } from "@/lib/video";

type TierDef = {
    id: VideoTier;
    name: string;
    glyph: string;
    cost: string;
    note: string;
    paid: boolean;
};

export const TIERS: TierDef[] = [
    {
        id: "composite",
        name: "Composite",
        glyph: "magic-pencil",
        cost: "≈ ₹0.25 / clip",
        note: "Product + voiceover + captions. No key needed.",
        paid: false,
    },
    {
        id: "ai_motion",
        name: "AI motion",
        glyph: "video",
        cost: "≈ $0.03 / sec",
        note: "Kling / Hailuo. AI b-roll & motion.",
        paid: true,
    },
    {
        id: "premium",
        name: "Premium",
        glyph: "star-fill",
        cost: "$0.05–0.30 / sec",
        note: "Runway / Veo. Hero spot, approval-gated.",
        paid: true,
    },
];

type TierTabsProps = {
    value: VideoTier;
    onChange: (tier: VideoTier) => void;
    /** when a paid tier has no BYO-key yet, the card shows a "needs key" hint */
    hasGenKey?: boolean;
};

const TierTabs = ({ value, onChange, hasGenKey = false }: TierTabsProps) => (
    <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1" role="radiogroup" aria-label="Render tier">
        {TIERS.map((t) => {
            const active = t.id === value;
            const needsKey = t.paid && !hasGenKey;
            return (
                <button
                    key={t.id}
                    role="radio"
                    aria-checked={active}
                    onClick={() => onChange(t.id)}
                    className={`group relative flex flex-col gap-1.5 p-3.5 text-left rounded-2xl border transition-all focus-ring ${
                        active
                            ? "border-primary-01/60 bg-primary-01/8 shadow-depth"
                            : "border-s-subtle bg-b-surface2 hover:border-s-stroke2 hover:bg-b-surface1/60 dark:hover:bg-shade-04/30"
                    }`}
                >
                    <div className="flex items-center gap-2">
                        <span
                            className={`flex items-center justify-center size-8 rounded-xl transition-colors ${
                                active
                                    ? "bg-primary-01/15 fill-primary-01"
                                    : "bg-b-surface1 fill-t-secondary dark:bg-shade-04/40"
                            }`}
                        >
                            <Icon className="!size-4.5 fill-inherit" name={t.glyph} />
                        </span>
                        <span className="text-sub-title-2 text-t-primary">{t.name}</span>
                        {!t.paid ? (
                            <Badge className="ml-auto" variant="success">
                                Free
                            </Badge>
                        ) : (
                            <Badge className="ml-auto" variant="warning">
                                Paid
                            </Badge>
                        )}
                    </div>
                    <div className="text-caption text-t-secondary tabular-nums">{t.cost}</div>
                    <div className="text-caption text-t-tertiary line-clamp-2">{t.note}</div>
                    {needsKey && (
                        <div className="flex items-center gap-1 mt-0.5 text-caption text-t-tertiary fill-t-tertiary">
                            <Icon className="!size-3.5 fill-inherit" name="lock" />
                            Add a key below
                        </div>
                    )}
                </button>
            );
        })}
    </div>
);

export default TierTabs;
