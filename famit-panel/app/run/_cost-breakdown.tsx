"use client";

// ============================================================================
// WAVE C · Real (HONEST) per-call cost breakdown.
//
// 🟥 PRICING HONESTY (founder is furious about fake numbers — RUN-PLATFORM-MASTER-PLAN §1):
//   • Every per-component ₹ comes ONLY from the Wave-A *sourced* rate-card:
//       STT  Sarvam Saarika ₹0.50/min
//       TTS  Sarvam Bulbul v2 ₹15/10k · v3 ₹30/10k · ElevenLabs Flash ₹4.76/1k chars
//       LLM  Groq (USD→INR 95.2)
//   • TELEPHONY (Vobiz) has NO verified per-min rate → it is ALWAYS rendered as
//       "est. — pending your real Vobiz CDR", NEVER a fabricated ₹. (telephony_verified
//       must be true AND a >0 rate present before any number shows.)
//   • Premium (ElevenLabs) runs near/below COGS → a "platform-fee model" note, not a
//       per-minute-margin claim.
//
// Pure client-side math over the rate_card the backend already serves (/tiers). Dormant-safe:
// missing rate_card → a calm "rates loading" state, never an error. Token-pure Core_2.
// ============================================================================

import { useMemo, useState } from "react";
import Icon from "@/components/Icon";
import { type RateCard, type Tier, type CampaignTier } from "@/lib/api";

function inr(n: number, dp?: number): string {
    if (!isFinite(n)) return "—";
    const d = dp ?? (n < 1 ? 2 : n < 10 ? 2 : 0);
    return `₹${n.toFixed(d)}`;
}

type Row = {
    key: string;
    label: string;
    detail: string; // the rate + unit, e.g. "₹15 / 10k chars · Sarvam v2"
    perCall: number | null; // null ⇒ unverified → no number shown
    source?: string;
    estimate?: boolean; // render "est." chip (telephony)
};

type Props = {
    rateCard: RateCard | null;
    tier: CampaignTier;
    tierObj?: Tier; // the resolved tier (gives the per-role rate_key)
    // advanced/custom override rate keys (when tier === "custom")
    sttKey?: string;
    llmKey?: string;
    ttsKey?: string;
    avgMin: number;
    audienceCount: number;
    // monthly platform fee for the plan this tier maps to (anchor, optional)
    platformFeeInr?: number;
    planLabel?: string;
};

const DEFAULT_SOURCES: Record<string, string> = {
    stt: "Sarvam pricing · docs.sarvam.ai · 2026-06-14",
    llm: "Groq pricing · groq.com (USD→INR 95.2) · 2026-06-14",
    "sarvam-bulbul-v2": "Sarvam Bulbul v2 ₹15/10k · docs.sarvam.ai · 2026-06-14",
    "sarvam-bulbul-v3": "Sarvam Bulbul v3 ₹30/10k · docs.sarvam.ai · 2026-06-14",
    "elevenlabs-flash-v2.5":
        "ElevenLabs Flash v2.5 ~₹4.76/1k · elevenlabs.io/pricing · 2026-06-14",
    telephony: "Vobiz SIP — NO published per-min rate; pending your real CDR",
};

export default function CostBreakdown({
    rateCard,
    tier,
    tierObj,
    sttKey,
    llmKey,
    ttsKey,
    avgMin,
    audienceCount,
    platformFeeInr,
    planLabel,
}: Props) {
    const [open, setOpen] = useState<string>("");

    const data = useMemo(() => {
        if (!rateCard) return null;
        const a = rateCard.assumptions;
        // resolve the per-role rate keys: prefer the tier's, fall back to custom picks
        const sk = tierObj?.stt.rate_key || sttKey || "sarvam";
        const lk = tierObj?.llm.rate_key || llmKey || "groq-llama-3.3-70b";
        const tk =
            tierObj?.tts.rate_key ||
            ttsKey ||
            (tier === "premium" ? "elevenlabs-flash-v2.5" : "sarvam-bulbul-v3");

        const sttRate = rateCard.stt[sk]?.inr_per_min ?? 0.5;
        const sttLabel = rateCard.stt[sk]?.label ?? "Sarvam Saarika";
        const sttPerMin = sttRate;

        const llmMtok = rateCard.llm[lk]?.inr_per_mtok ?? 57;
        const llmLabel = rateCard.llm[lk]?.label ?? "Groq";
        const llmPerMin = (llmMtok * a.llm_tokens_per_min) / 1_000_000;

        const tts1k = rateCard.tts[tk]?.inr_per_1k ?? 3;
        const ttsLabel = rateCard.tts[tk]?.label ?? "Sarvam Bulbul";
        const ttsPerMin = (tts1k * a.tts_chars_per_min) / 1000;

        const m = avgMin || a.default_avg_call_min || 1.5;

        // TELEPHONY — only show a number if a real verified rate exists.
        const telVerified =
            !!rateCard.telephony_verified &&
            (rateCard.telephony_inr_per_min ?? 0) > 0;
        const telPerMin = telVerified ? rateCard.telephony_inr_per_min : null;

        const sources = rateCard.sources || {};

        const rows: Row[] = [
            {
                key: "telephony",
                label: "Telephony (carrier)",
                detail: "Vobiz SIP · same on every tier",
                perCall: telPerMin != null ? telPerMin * m : null,
                source: sources.telephony || DEFAULT_SOURCES.telephony,
                estimate: true,
            },
            {
                key: "tts",
                label: "Voice (TTS)",
                detail: `${inr(tts1k, 2)} / 1k chars · ${ttsLabel}`,
                perCall: ttsPerMin * m,
                source: sources[tk] || DEFAULT_SOURCES[tk] || DEFAULT_SOURCES.stt,
            },
            {
                key: "stt",
                label: "Transcription (STT)",
                detail: `${inr(sttRate, 2)} / min · ${sttLabel}`,
                perCall: sttPerMin * m,
                source: sources.stt || DEFAULT_SOURCES.stt,
            },
            {
                key: "llm",
                label: "Brain (LLM)",
                detail: `${inr(llmMtok, 0)} / Mtok · ${llmLabel}`,
                perCall: llmPerMin * m,
                source: sources.llm || DEFAULT_SOURCES.llm,
            },
        ];

        // Known (non-telephony) per-call COGS
        const knownCogs = rows
            .filter((r) => r.key !== "telephony" && r.perCall != null)
            .reduce((s, r) => s + (r.perCall as number), 0);

        return {
            rows,
            knownCogs,
            telVerified,
            isPremium: tier === "premium" || tk === "elevenlabs-flash-v2.5",
            avgMin: m,
        };
    }, [rateCard, tier, tierObj, sttKey, llmKey, ttsKey, avgMin]);

    if (!rateCard || !data) {
        return (
            <div className="rounded-2xl bg-b-surface1 border border-s-subtle p-4 dark:bg-shade-04/30 text-caption text-t-tertiary">
                Loading sourced rates…
            </div>
        );
    }

    const { rows, knownCogs, telVerified, isPremium } = data;
    const projected = knownCogs * (audienceCount || 0);

    return (
        <div className="rounded-2xl border border-s-subtle bg-b-surface1 p-4 dark:bg-shade-04/30">
            <div className="flex items-center justify-between gap-3 mb-3">
                <div className="flex items-center gap-2">
                    <span className="grid place-items-center size-7 rounded-full bg-b-surface2 text-t-secondary">
                        <Icon name="income" className="size-4 fill-current" />
                    </span>
                    <div className="leading-tight">
                        <div className="text-button text-t-primary">
                            Real cost per call
                        </div>
                        <div className="text-caption text-t-tertiary">
                            Sourced rates · {inr(data.avgMin, 1)}-min call
                        </div>
                    </div>
                </div>
                <div className="text-right">
                    <div className="text-h5 text-t-primary tabular-nums leading-none">
                        ≈ {inr(knownCogs, 2)}
                        {!telVerified && (
                            <span className="text-caption text-t-tertiary font-normal">
                                {" "}
                                + tel.
                            </span>
                        )}
                    </div>
                    <div className="text-caption text-t-tertiary mt-0.5">
                        per call
                    </div>
                </div>
            </div>

            {/* honest per-component rows */}
            <div className="divide-y divide-s-subtle rounded-xl overflow-hidden border border-s-subtle">
                {rows.map((r) => {
                    const expanded = open === r.key;
                    const unverified = r.perCall == null;
                    return (
                        <div key={r.key} className="bg-b-surface2">
                            <button
                                type="button"
                                onClick={() => setOpen(expanded ? "" : r.key)}
                                className="w-full flex items-center justify-between gap-3 px-3.5 py-2.5 text-left transition-colors hover:bg-b-surface1 dark:hover:bg-shade-04/40"
                            >
                                <div className="min-w-0">
                                    <div className="flex items-center gap-1.5">
                                        <span className="text-body-2 text-t-primary">
                                            {r.label}
                                        </span>
                                        <Icon
                                            name="info"
                                            className={`size-3.5 fill-t-tertiary transition-transform ${
                                                expanded ? "rotate-180" : ""
                                            }`}
                                        />
                                    </div>
                                    <div className="text-caption text-t-tertiary truncate">
                                        {r.detail}
                                    </div>
                                </div>
                                <div className="text-right shrink-0">
                                    {unverified ? (
                                        <span className="inline-flex items-center gap-1 px-2 h-6 rounded-full bg-primary-05/10 text-primary-05 text-caption font-medium">
                                            est. — pending CDR
                                        </span>
                                    ) : (
                                        <span className="text-body-2 text-t-primary tabular-nums">
                                            {inr(r.perCall as number, 2)}
                                        </span>
                                    )}
                                </div>
                            </button>
                            {expanded && r.source && (
                                <div className="px-3.5 pb-2.5 -mt-0.5">
                                    <p className="text-caption text-t-tertiary leading-relaxed">
                                        <span className="text-t-secondary">
                                            Source:{" "}
                                        </span>
                                        {r.source}
                                    </p>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* telephony honesty caption (always, when unverified) */}
            {!telVerified && (
                <div className="mt-2.5 flex items-start gap-2 p-2.5 rounded-xl bg-primary-05/8">
                    <Icon
                        name="info"
                        className="size-4 fill-primary-05 shrink-0 mt-0.5"
                    />
                    <p className="text-caption text-t-secondary leading-relaxed">
                        <span className="text-t-primary">Telephony is an estimate.</span>{" "}
                        Vobiz publishes no per-minute rate — the real carrier cost
                        comes from <span className="text-t-primary">your Vobiz CDR/invoice</span>.
                        We will never show you a made-up number here.
                    </p>
                </div>
            )}

            {/* projected + platform-fee anchor */}
            <div className="mt-3 pt-3 border-t border-s-subtle flex items-end justify-between gap-3">
                <div>
                    <div className="eyebrow mb-0.5">
                        Projected · {audienceCount || 0} leads
                    </div>
                    <div className="text-body-1 text-t-primary tabular-nums">
                        ≈ {inr(projected, projected < 100 ? 2 : 0)}
                        {!telVerified && (
                            <span className="text-caption text-t-tertiary font-normal">
                                {" "}
                                + telephony
                            </span>
                        )}
                    </div>
                </div>
                {platformFeeInr != null && platformFeeInr > 0 && (
                    <div className="text-right">
                        <div className="eyebrow mb-0.5">
                            {planLabel || "Plan"} fee
                        </div>
                        <div className="text-body-2 text-t-secondary tabular-nums">
                            ₹{platformFeeInr.toLocaleString("en-IN")}/mo
                        </div>
                    </div>
                )}
            </div>

            {/* Premium-near-COGS honesty note */}
            {isPremium && (
                <p className="mt-2.5 text-caption text-t-tertiary leading-relaxed">
                    Premium (ElevenLabs) runs{" "}
                    <span className="text-t-secondary">near or below cost</span> per
                    minute — the value is in the platform, not a per-minute margin.
                </p>
            )}
        </div>
    );
}
