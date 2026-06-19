"use client";

// ============================================================================
// PVS Phase-1 · "Voice & Providers" — Run-page left-rail card
//
// A premium, big-company cost/quality control for OUTBOUND calls, per campaign:
//   • a 3-stop LEAN · STANDARD · PREMIUM segmented slider (writes campaign field `tier`)
//   • a live ₹/min cost-meter + projected campaign spend (PURE CLIENT-SIDE math — zero burn)
//   • a "Recommended for this campaign" badge (cheap client heuristic)
//   • a real-time provider-health row (ElevenLabs / Groq / Sarvam ✓) from /providers
//   • a Voice dropdown (scrollable rows: name · accent/gender) each with a ▶ Play button
//     driving ONE shared <audio> at the FREE /voice-preview proxy
//   • an Advanced disclosure: 3 per-role provider selects + a manual voice -> tier:"custom"
//
// HONESTY: the live-call PROVIDER swap on the OUTBOUND leg is Phase 2 (OB-PROV, needs founder
// approval). VOICE selection (within ElevenLabs) + the tier config APPLY NOW. Surfaced inline.
//
// Token-pure Core_2 (Inter Display, zero raw hex). Dormant-safe: any backend gap degrades to a
// calm, usable card — never an error wall. Persists via POST /campaigns/{cid} (updateCampaign).
// ============================================================================

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Card from "@/components/Card";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Select from "@/components/Select";
import {
    getTiers,
    getProviders,
    getVoices,
    getCampaign,
    updateCampaign,
    voicePreviewUrl,
    getCampaignCPL,
    type TiersPayload,
    type Tier,
    type RateCard,
    type ProvidersByRole,
    type Voice,
    type VoiceProvider,
    type CampaignFields,
    type CampaignTier,
    type CampaignCPL,
} from "@/lib/api";
import { type SelectOption } from "@/types/select";
import ProviderLock, { type ProviderLockState } from "./_provider-lock";
import CostBreakdown from "./_cost-breakdown";

// WAVE C: monthly platform-fee anchors per tier (RUN-PLATFORM-MASTER-PLAN §1c).
// Shown beside the cost meter as the honest "margin lives in the platform fee" anchor.
const PLAN_FEE: Record<string, { fee: number; label: string }> = {
    lean: { fee: 9999, label: "Starter" },
    standard: { fee: 24999, label: "Growth" },
    premium: { fee: 75000, label: "Enterprise" },
};

// ── small inline play/pause triangle (icon registry has no "play") ──────────
function PlayGlyph({ playing }: { playing: boolean }) {
    return playing ? (
        <svg viewBox="0 0 24 24" className="size-3.5 fill-current" aria-hidden>
            <rect x="6" y="5" width="4" height="14" rx="1" />
            <rect x="14" y="5" width="4" height="14" rx="1" />
        </svg>
    ) : (
        <svg viewBox="0 0 24 24" className="size-3.5 fill-current" aria-hidden>
            <path d="M8 5.14v13.72c0 .79.87 1.27 1.54.84l10.6-6.86a1 1 0 0 0 0-1.68L9.54 4.3A1 1 0 0 0 8 5.14z" />
        </svg>
    );
}

function inr(n: number, dp?: number): string {
    if (!isFinite(n)) return "—";
    if (dp != null) return `₹${n.toFixed(dp)}`;
    return n < 1 ? `₹${n.toFixed(2)}` : `₹${n.toFixed(n < 10 ? 2 : 0)}`;
}

// quality pill tone per tier
const QUALITY_TONE: Record<string, "neutral" | "info" | "success"> = {
    lean: "neutral",
    standard: "info",
    premium: "success",
};

type Props = {
    // campaign id resolved by the Run page (empty when nothing selected)
    campaignId: string;
    // #leads in the resolved audience preview — drives projected campaign spend
    audienceCount: number;
    writable: boolean;
};

export default function VoiceProviders({ campaignId, audienceCount, writable }: Props) {
    const [tiersData, setTiersData] = useState<TiersPayload | null>(null);
    const [byRole, setByRole] = useState<ProvidersByRole>({ stt: [], llm: [], tts: [] });
    const [providersAvail, setProvidersAvail] = useState<Record<string, boolean>>({});

    // campaign-persisted config
    const [tier, setTier] = useState<CampaignTier>("standard");
    const [voiceId, setVoiceId] = useState<string>("");
    const [sttP, setSttP] = useState<string>("");
    const [llmP, setLlmP] = useState<string>("");
    const [ttsP, setTtsP] = useState<string>("");
    const [avgMin, setAvgMin] = useState<number>(1.5);

    // base campaign fields we must preserve on save (backend replaces `fields` wholesale)
    const baseFields = useRef<CampaignFields>({});

    const [voices, setVoices] = useState<Voice[]>([]);
    const [voiceProvider, setVoiceProvider] = useState<VoiceProvider>("elevenlabs");
    const [advanced, setAdvanced] = useState(false);
    const [saving, setSaving] = useState(false);
    const [savedNote, setSavedNote] = useState("");
    const [loaded, setLoaded] = useState(false);

    const audioRef = useRef<HTMLAudioElement | null>(null);
    // last voice_id whose preview we attempted (so <audio onError> knows which row to flag)
    const attemptedId = useRef<string>("");
    const [playingId, setPlayingId] = useState<string>("");
    // voice_id whose preview failed (network / unsupported / 502) -> show an inline caption
    const [previewError, setPreviewError] = useState<string>("");

    // WAVE C: campaign-level CPL (cost ÷ qualified) — dormant-safe, nulls hide the line.
    const [cpl, setCpl] = useState<CampaignCPL | null>(null);

    // ── load the tier catalogue + provider health once ──
    useEffect(() => {
        getTiers().then(setTiersData).catch(() => {});
        getProviders()
            .then((r) => {
                setByRole(r.by_role);
                const avail: Record<string, boolean> = {};
                for (const p of r.providers) avail[p.id] = p.available;
                setProvidersAvail(avail);
            })
            .catch(() => {});
    }, []);

    // ── hydrate from the selected campaign's saved fields ──
    useEffect(() => {
        setLoaded(false);
        setSavedNote("");
        if (!campaignId) {
            baseFields.current = {};
            setLoaded(true);
            return;
        }
        let cancelled = false;
        getCampaign(campaignId)
            .then((c) => {
                if (cancelled) return;
                const f = (c?.fields ?? {}) as CampaignFields;
                baseFields.current = f;
                // "lean" is retired → present it as Standard (only Standard + Premium offered).
                const t = ((f.tier as CampaignTier) === "lean" || !f.tier
                    ? "standard"
                    : (f.tier as CampaignTier));
                setTier(t);
                setVoiceId(typeof f.voice_id === "string" ? f.voice_id : "");
                setSttP(typeof f.stt_provider === "string" ? f.stt_provider : "");
                setLlmP(typeof f.llm_provider === "string" ? f.llm_provider : "");
                setTtsP(typeof f.tts_provider === "string" ? f.tts_provider : "");
                setAvgMin(typeof f.est_avg_call_min === "number" ? f.est_avg_call_min : 1.5);
                setAdvanced(t === "custom");
            })
            .catch(() => {})
            .finally(() => !cancelled && setLoaded(true));
        return () => {
            cancelled = true;
        };
    }, [campaignId]);

    // ── WAVE C: load this campaign's cost-per-lead (dormant-safe) ──
    useEffect(() => {
        if (!campaignId) {
            setCpl(null);
            return;
        }
        let cancelled = false;
        getCampaignCPL(campaignId)
            .then((r) => !cancelled && setCpl(r))
            .catch(() => !cancelled && setCpl(null));
        return () => {
            cancelled = true;
        };
    }, [campaignId]);

    const tierMap = useMemo(() => {
        const m: Record<string, Tier> = {};
        (tiersData?.tiers || []).forEach((t) => (m[t.key] = t));
        return m;
    }, [tiersData]);

    // The TTS provider of the active mix decides which voice catalogue to load.
    const activeTtsProvider = useMemo(() => {
        if (tier === "custom") return ttsP || "sarvam";
        return tierMap[tier]?.tts.provider || "sarvam";
    }, [tier, ttsP, tierMap]);

    // ── WAVE C: the resolved {STT·LLM·TTS} triple this campaign is SET to run ──
    const resolved = useMemo(() => {
        if (tier === "custom") {
            return {
                stt: sttP || "sarvam",
                llm: llmP || "groq",
                tts: ttsP || "sarvam",
            };
        }
        const t = tierMap[tier];
        return {
            stt: t?.stt.provider || "sarvam",
            llm: t?.llm.provider || "groq",
            tts: t?.tts.provider || "sarvam",
        };
    }, [tier, tierMap, sttP, llmP, ttsP]);

    // resolved voice display name (fall back to the id so the banner is never blank)
    const resolvedVoiceName = useMemo(() => {
        const v = voices.find((x) => x.voice_id === voiceId);
        return v?.name || voiceId || "";
    }, [voices, voiceId]);

    // CONFIG-ONLY is today's truth; flips to LIVE only when the backend says ob_prov_live.
    const lockState: ProviderLockState = tiersData?.ob_prov_live
        ? "live"
        : "config-only";

    // ── load the voice list for the active TTS provider ──
    useEffect(() => {
        const prov: VoiceProvider =
            activeTtsProvider === "elevenlabs" ? "elevenlabs" : "sarvam";
        setVoiceProvider(prov);
        getVoices(prov)
            .then((r) => setVoices(r.voices))
            .catch(() => setVoices([]));
    }, [activeTtsProvider]);

    // stop audio when unmounting
    useEffect(
        () => () => {
            if (audioRef.current) audioRef.current.pause();
        },
        []
    );

    // ── cost-meter math (pure client-side; the per-tier headline is the source of truth) ──
    const perMin = useMemo(() => {
        if (tier !== "custom") return tierMap[tier]?.est_inr_per_min ?? 0;
        // custom mix: sum the rate-card per-component estimate for the chosen providers/models.
        // We approximate from the tier whose role provider matches (rate keys live on the tier roles).
        const rc = tiersData?.rate_card;
        if (!rc) return 0;
        const a = rc.assumptions;
        // pick a representative rate key per role from the providers chosen
        const sttKey = sttP === "sarvam" || !sttP ? "sarvam" : "sarvam";
        const llmKey = llmP === "groq" || !llmP ? "groq-llama-3.3-70b" : "groq-llama-3.3-70b";
        const ttsKey =
            ttsP === "elevenlabs"
                ? "elevenlabs-flash-v2.5"
                : "sarvam-bulbul-v3";
        const stt = rc.stt[sttKey]?.inr_per_min ?? 0.5;
        const llm = ((rc.llm[llmKey]?.inr_per_mtok ?? 57) * a.llm_tokens_per_min) / 1_000_000;
        const tts = ((rc.tts[ttsKey]?.inr_per_1k ?? 3) * a.tts_chars_per_min) / 1000;
        return Math.round((stt + llm + tts) * 100) / 100;
    }, [tier, tierMap, tiersData, sttP, llmP, ttsP]);

    // WAVE C: the headline cost meter is now the CostBreakdown card (per-component,
    // honest, telephony-as-estimate). We keep `perMin` only for the "saving vs Premium"
    // micro-callout next to the avg-call input.
    const premiumPerMin = tierMap["premium"]?.est_inr_per_min ?? 1.6;
    const savingsVsPremium = Math.max(0, premiumPerMin - perMin);

    // ── recommended-tier heuristic (cheap, client-side) ──
    const recommended = useMemo<string>(() => {
        // Only Standard + Premium are offered. Small/qualified list -> Premium reads
        // as worth it; otherwise Standard is the safe default.
        if (audienceCount > 0 && audienceCount <= 25) return "premium";
        return "standard";
    }, [audienceCount]);

    // ── play / stop a voice preview through ONE shared <audio> ──
    const togglePlay = useCallback(
        (v: Voice) => {
            const el = audioRef.current;
            if (!el) return;
            if (playingId === v.voice_id && !el.paused) {
                el.pause();
                setPlayingId("");
                return;
            }
            setPreviewError(""); // clear any prior failure on a fresh attempt
            attemptedId.current = v.voice_id;
            el.src = voicePreviewUrl(voiceProvider, v.voice_id);
            el.play()
                .then(() => setPlayingId(v.voice_id))
                .catch((err) => {
                    // Surface the failure instead of swallowing it: log + show an inline caption.
                    console.error("voice preview failed", v.voice_id, voiceProvider, err);
                    setPlayingId("");
                    setPreviewError(v.voice_id);
                });
        },
        [playingId, voiceProvider]
    );

    // ── persist to the campaign ──
    const persist = useCallback(
        async (next: Partial<CampaignFields>) => {
            if (!campaignId || !writable) return;
            const merged: Record<string, unknown> = {
                ...baseFields.current,
                tier,
                voice_id: voiceId,
                stt_provider: sttP,
                llm_provider: llmP,
                tts_provider: ttsP,
                est_avg_call_min: avgMin,
                ...next,
            };
            baseFields.current = merged as CampaignFields;
            setSaving(true);
            setSavedNote("");
            try {
                await updateCampaign(campaignId, merged);
                setSavedNote("Saved");
                setTimeout(() => setSavedNote(""), 2000);
            } catch {
                setSavedNote("Couldn't save — retry");
            } finally {
                setSaving(false);
            }
        },
        [campaignId, writable, tier, voiceId, sttP, llmP, ttsP, avgMin]
    );

    // ── slider stop click ──
    const pickTier = (key: CampaignTier) => {
        if (!writable) return;
        setTier(key);
        setAdvanced(false);
        const t = tierMap[key];
        // auto-fill the advanced selects + reset voice to the tier's default voice (within its provider)
        const nextStt = t?.stt.provider || "";
        const nextLlm = t?.llm.provider || "";
        const nextTts = t?.tts.provider || "";
        const nextVoice = t?.voice.voice_id || "";
        setSttP(nextStt);
        setLlmP(nextLlm);
        setTtsP(nextTts);
        setVoiceId(nextVoice);
        persist({
            tier: key,
            stt_provider: nextStt,
            llm_provider: nextLlm,
            tts_provider: nextTts,
            voice_id: nextVoice,
        });
    };

    const onVoice = (v: string) => {
        setVoiceId(v);
        persist({ voice_id: v });
    };

    const onAvgMin = (n: number) => {
        const clamped = Math.min(30, Math.max(0.1, n || 1.5));
        setAvgMin(clamped);
        persist({ est_avg_call_min: clamped });
    };

    // touching a per-role select flips to custom
    const onRole = (role: "stt" | "llm" | "tts", id: string) => {
        if (role === "stt") setSttP(id);
        if (role === "llm") setLlmP(id);
        if (role === "tts") setTtsP(id);
        setTier("custom");
        persist({
            tier: "custom",
            stt_provider: role === "stt" ? id : sttP,
            llm_provider: role === "llm" ? id : llmP,
            tts_provider: role === "tts" ? id : ttsP,
        });
    };

    // Only Standard + Premium are offered. The legacy "lean" tier is hidden from
    // the picker (and from the compare strip) — campaigns still on "lean" are
    // shown/persisted as Standard.
    const order = (tiersData?.order || ["lean", "standard", "premium"]).filter(
        (k) => k !== "lean"
    );
    const noCampaign = !campaignId;

    // provider-health row: only the three headline providers used by the tiers
    const healthProviders = [
        { id: "elevenlabs", label: "ElevenLabs" },
        { id: "groq", label: "Groq" },
        { id: "sarvam", label: "Sarvam" },
    ];

    // B3 (ROUND4): the one-big jargon card is split into THREE clear cards —
    // ① Quality & Voice  ② Cost estimate  ③ Providers — with bigger, calmer copy.
    // The empty / loading states still render as a single calm card so the step
    // never shows three skeletons at once.
    if (noCampaign || !loaded) {
        return (
            <>
                <audio ref={audioRef} className="hidden" />
                <Card title="Voice & Providers">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <div className="p-4 rounded-2xl bg-b-surface1 border border-s-subtle text-body-2 text-t-tertiary dark:bg-shade-04/30">
                            {noCampaign
                                ? "Select a campaign above to set its voice, quality tier and live cost estimate."
                                : "Loading this campaign’s settings…"}
                        </div>
                    </div>
                </Card>
            </>
        );
    }

    return (
        <div className="grid grid-cols-2 gap-4 items-start max-lg:grid-cols-1">
            {/* shared hidden audio element for ALL voice previews */}
            <audio
                ref={audioRef}
                onEnded={() => setPlayingId("")}
                onPause={() => setPlayingId("")}
                onError={() => {
                    // unsupported content-type / network / 502 -> flag the attempted row
                    console.error(
                        "voice preview <audio> error",
                        attemptedId.current,
                        voiceProvider
                    );
                    setPlayingId("");
                    if (attemptedId.current)
                        setPreviewError(attemptedId.current);
                }}
                className="hidden"
            />

            {/* ══ CARD ① — QUALITY & VOICE ══════════════════════════════════ */}
            <Card title="Quality & voice">
                <div className="px-5 pb-5 max-lg:px-3 space-y-5">
                        {/* ── 3-stop segmented tier slider ── */}
                        <div>
                            <div className="flex items-center justify-between mb-2.5">
                                <span className="text-sub-title-1">Quality tier</span>
                                {savedNote && (
                                    <span
                                        className={`text-caption ${
                                            savedNote === "Saved"
                                                ? "text-primary-02"
                                                : "text-primary-03"
                                        }`}
                                    >
                                        {savedNote}
                                    </span>
                                )}
                            </div>
                            <div className="grid grid-cols-2 gap-1.5 p-1 rounded-full bg-b-surface1 border border-s-subtle dark:bg-shade-04/40">
                                {order.map((key) => {
                                    const t = tierMap[key];
                                    if (!t) return null;
                                    const on = tier === key;
                                    const rec = recommended === key;
                                    return (
                                        <button
                                            key={key}
                                            type="button"
                                            disabled={!writable || saving}
                                            onClick={() => pickTier(key as CampaignTier)}
                                            className={`relative flex flex-col items-center justify-center h-12 rounded-full text-center transition-all ${
                                                on
                                                    ? "bg-b-surface2 shadow-depth text-t-primary"
                                                    : "text-t-secondary hover:text-t-primary"
                                            } ${
                                                !writable
                                                    ? "cursor-default"
                                                    : "cursor-pointer"
                                            }`}
                                        >
                                            <span className="text-button leading-none">
                                                {t.name}
                                            </span>
                                            {rec && (
                                                <span className="absolute -top-2 right-1.5">
                                                    <Icon
                                                        name="check-circle-fill"
                                                        className="size-4 fill-primary-02"
                                                    />
                                                </span>
                                            )}
                                        </button>
                                    );
                                })}
                            </div>
                            <div className="mt-2 flex items-center gap-2 flex-wrap">
                                {tier === "custom" ? (
                                    <Badge variant="info">Custom mix</Badge>
                                ) : (
                                    <>
                                        <Badge variant={QUALITY_TONE[tier] || "neutral"}>
                                            {tierMap[tier]?.quality} quality
                                        </Badge>
                                        <span className="inline-flex items-center gap-1 text-caption text-primary-02">
                                            <span className="size-1.5 rounded-full bg-primary-02" />
                                            &lt;800ms · natural
                                        </span>
                                    </>
                                )}
                                {recommended === tier && tier !== "custom" && (
                                    <span className="text-caption text-t-tertiary">
                                        Recommended for this audience
                                    </span>
                                )}
                            </div>
                            {tier !== "custom" && tierMap[tier]?.blurb && (
                                <p className="mt-2 text-body-2 text-t-tertiary">
                                    {tierMap[tier]?.blurb}
                                </p>
                            )}
                        </div>

                        {/* ── voice dropdown + per-row play ── */}
                        <div>
                            <div className="flex items-center justify-between mb-2.5">
                                <span className="text-sub-title-1">
                                    Voice{" "}
                                    <span className="text-t-tertiary font-normal">
                                        ({voiceProvider === "elevenlabs"
                                            ? "ElevenLabs"
                                            : "Sarvam"})
                                    </span>
                                </span>
                                <span className="text-caption text-t-tertiary">
                                    {voices.length} voices
                                </span>
                            </div>
                            <div className="max-h-56 overflow-y-auto rounded-2xl border border-s-subtle divide-y divide-s-subtle scrollbar scrollbar-thumb-t-tertiary/40 scrollbar-track-transparent">
                                {voices.length === 0 ? (
                                    <div className="px-4 py-6 text-center text-caption text-t-tertiary">
                                        No voices available for this provider.
                                    </div>
                                ) : (
                                    voices.map((v) => {
                                        const sel = voiceId === v.voice_id;
                                        const meta = [v.accent, v.gender]
                                            .filter(Boolean)
                                            .join(" · ");
                                        return (
                                            <div
                                                key={v.voice_id}
                                                className={`flex items-center gap-2.5 px-3 py-2.5 transition-colors ${
                                                    sel
                                                        ? "bg-primary-01/8"
                                                        : "hover:bg-b-surface1 dark:hover:bg-shade-04/40"
                                                }`}
                                            >
                                                <button
                                                    type="button"
                                                    aria-label={`Preview ${v.name}`}
                                                    onClick={() => togglePlay(v)}
                                                    className={`grid place-items-center size-8 shrink-0 rounded-full transition-colors ${
                                                        playingId === v.voice_id
                                                            ? "bg-primary-01 text-t-light"
                                                            : "bg-b-surface1 text-t-secondary hover:text-t-primary dark:bg-shade-04/60"
                                                    }`}
                                                >
                                                    <PlayGlyph
                                                        playing={
                                                            playingId ===
                                                            v.voice_id
                                                        }
                                                    />
                                                </button>
                                                <button
                                                    type="button"
                                                    disabled={!writable}
                                                    onClick={() =>
                                                        onVoice(v.voice_id)
                                                    }
                                                    className="flex-1 min-w-0 text-left"
                                                >
                                                    <div className="font-medium text-t-primary truncate">
                                                        {v.name}
                                                    </div>
                                                    {meta && (
                                                        <div className="text-caption text-t-tertiary truncate capitalize">
                                                            {meta}
                                                        </div>
                                                    )}
                                                    {previewError ===
                                                        v.voice_id && (
                                                        <div className="text-caption text-primary-03 truncate">
                                                            Preview unavailable —
                                                            press ▶ to retry
                                                        </div>
                                                    )}
                                                </button>
                                                {sel && (
                                                    <Icon
                                                        name="check-circle-fill"
                                                        className="size-4 fill-primary-01 shrink-0"
                                                    />
                                                )}
                                            </div>
                                        );
                                    })
                                )}
                            </div>
                            <p className="mt-2 text-body-2 text-t-tertiary">
                                Press ▶ to hear a free sample. Your voice choice
                                applies on the next outbound call.
                            </p>
                        </div>
                    </div>
                </Card>

                {/* ══ CARD ② — COST ESTIMATE ════════════════════════════════════ */}
                <Card title="Cost estimate">
                    <div className="px-5 pb-5 max-lg:px-3 space-y-5">
                        {/* ── WAVE C: real (honest) per-call cost breakdown ── */}
                        <div>
                            <div className="flex items-center justify-between gap-2 mb-2">
                                <label className="flex items-center gap-2 text-body-2 text-t-secondary">
                                    Avg call length
                                    <input
                                        type="number"
                                        min={0.1}
                                        max={30}
                                        step={0.5}
                                        value={avgMin}
                                        disabled={!writable}
                                        onChange={(e) =>
                                            setAvgMin(
                                                parseFloat(e.target.value) || 0
                                            )
                                        }
                                        onBlur={(e) =>
                                            onAvgMin(parseFloat(e.target.value))
                                        }
                                        className="w-16 h-8 px-2 rounded-xl bg-b-surface2 border border-s-stroke2 text-body-2 text-t-primary tabular-nums outline-none focus:border-primary-01/60"
                                    />
                                    min
                                </label>
                                {tier !== "premium" && savingsVsPremium > 0 && (
                                    <span className="text-caption text-primary-02">
                                        Saving ≈ {inr(savingsVsPremium)}/min vs Premium
                                    </span>
                                )}
                            </div>
                            <CostBreakdown
                                rateCard={tiersData?.rate_card ?? null}
                                tier={tier}
                                tierObj={tier !== "custom" ? tierMap[tier] : undefined}
                                sttKey={sttP}
                                llmKey={llmP}
                                ttsKey={ttsP}
                                avgMin={avgMin}
                                audienceCount={audienceCount}
                                platformFeeInr={PLAN_FEE[tier]?.fee}
                                planLabel={PLAN_FEE[tier]?.label}
                            />
                        </div>

                        {/* ── WAVE C: inline per-tier compare strip ── */}
                        <TierCompare
                            tiers={tiersData?.tiers || []}
                            rateCard={tiersData?.rate_card ?? null}
                            avgMin={avgMin}
                            audienceCount={audienceCount}
                            active={tier}
                            onPick={(k) => pickTier(k as CampaignTier)}
                            writable={writable}
                        />

                        {/* ── WAVE C: campaign cost-per-lead (CPL) — hides until data exists ── */}
                        {cpl && (cpl.cpl != null || cpl.cpc != null) && (
                            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 rounded-2xl bg-b-surface1 border border-s-subtle px-4 py-3 dark:bg-shade-04/30">
                                <div className="flex items-center gap-1.5 text-caption text-t-tertiary">
                                    <Icon
                                        name="chart"
                                        className="size-4 fill-t-tertiary"
                                    />
                                    So far this campaign
                                </div>
                                {cpl.cpl != null && (
                                    <div className="flex items-baseline gap-1.5">
                                        <span className="text-body-1 text-t-primary tabular-nums">
                                            {inr(cpl.cpl)}
                                        </span>
                                        <span className="text-caption text-t-secondary">
                                            / qualified lead
                                        </span>
                                    </div>
                                )}
                                {cpl.cpc != null && (
                                    <div className="flex items-baseline gap-1.5">
                                        <span className="text-body-2 text-t-secondary tabular-nums">
                                            {inr(cpl.cpc)}
                                        </span>
                                        <span className="text-caption text-t-tertiary">
                                            / call · {cpl.calls} calls
                                        </span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </Card>

                {/* ══ CARD ③ — PROVIDERS (full-width below the 2-up row) ═════════ */}
                <Card title="Providers" className="col-span-2 max-lg:col-span-1">
                    <div className="px-5 pb-5 max-lg:px-3 space-y-5">
                        {/* ── WAVE C: provider-lock banner (CONFIG-ONLY today) ── */}
                        <ProviderLock
                            state={lockState}
                            stt={resolved.stt}
                            llm={resolved.llm}
                            tts={resolved.tts}
                            voice={resolvedVoiceName}
                            inboundLive={tiersData?.inbound_prov_lock}
                        />

                        {/* ── provider health ── */}
                        <div className="flex items-center gap-3 flex-wrap text-body-2 text-t-secondary">
                            <span className="text-t-tertiary">Live status:</span>
                            {healthProviders.map((p) => {
                                const ok = providersAvail[p.id];
                                return (
                                    <span
                                        key={p.id}
                                        className="inline-flex items-center gap-1.5"
                                    >
                                        <span
                                            className={`size-1.5 rounded-full ${
                                                ok
                                                    ? "bg-primary-02"
                                                    : "bg-t-tertiary/60"
                                            }`}
                                        />
                                        {p.label}
                                    </span>
                                );
                            })}
                        </div>

                        {/* ── Advanced disclosure ── */}
                        <div className="border-t border-s-subtle pt-3">
                            <button
                                type="button"
                                onClick={() => setAdvanced((a) => !a)}
                                className="flex items-center gap-1.5 text-button text-t-secondary hover:text-t-primary transition-colors"
                            >
                                <Icon
                                    name="chevron"
                                    className={`size-4 fill-inherit transition-transform ${
                                        advanced ? "rotate-180" : ""
                                    }`}
                                />
                                Advanced — choose each component
                            </button>
                            {advanced && (
                                <div className="mt-3 space-y-3">
                                    <RoleSelect
                                        label="Speech-to-text (STT)"
                                        value={sttP}
                                        options={byRole.stt}
                                        onChange={(id) => onRole("stt", id)}
                                        writable={writable}
                                    />
                                    <RoleSelect
                                        label="Language model (LLM)"
                                        value={llmP}
                                        options={byRole.llm}
                                        onChange={(id) => onRole("llm", id)}
                                        writable={writable}
                                    />
                                    <RoleSelect
                                        label="Text-to-speech (TTS)"
                                        value={ttsP}
                                        options={byRole.tts}
                                        onChange={(id) => onRole("tts", id)}
                                        writable={writable}
                                    />
                                    <p className="text-caption text-t-tertiary">
                                        Picking components by hand switches this
                                        campaign to a Custom mix.
                                    </p>
                                </div>
                            )}
                        </div>

                    </div>
                </Card>
        </div>
    );
}

// ── WAVE C: inline per-tier cost compare strip ──
// Shows each tier's honest per-call COGS for THIS audience side-by-side, so the
// founder can see the trade-off without leaving the step. Click a column to apply.
function TierCompare({
    tiers,
    rateCard,
    avgMin,
    audienceCount,
    active,
    onPick,
    writable,
}: {
    tiers: Tier[];
    rateCard: RateCard | null;
    avgMin: number;
    audienceCount: number;
    active: string;
    onPick: (key: string) => void;
    writable: boolean;
}) {
    // Only Standard + Premium are offered — drop the retired "lean" column.
    const shownTiers = tiers.filter((t) => t.key !== "lean");
    if (!rateCard || shownTiers.length === 0) return null;
    const a = rateCard.assumptions;
    const m = avgMin || a.default_avg_call_min || 1.5;
    const perCall = (t: Tier): number => {
        const stt = rateCard.stt[t.stt.rate_key]?.inr_per_min ?? 0.5;
        const llm =
            ((rateCard.llm[t.llm.rate_key]?.inr_per_mtok ?? 57) *
                a.llm_tokens_per_min) /
            1_000_000;
        const tts =
            ((rateCard.tts[t.tts.rate_key]?.inr_per_1k ?? 3) *
                a.tts_chars_per_min) /
            1000;
        return (stt + llm + tts) * m;
    };
    return (
        <div>
            <div className="flex items-center justify-between mb-2">
                <span className="text-sub-title-1">Compare tiers · this audience</span>
                <span className="text-caption text-t-tertiary">
                    voice cost only — telephony extra
                </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
                {shownTiers.map((t) => {
                    const on = active === t.key;
                    const pc = perCall(t);
                    const proj = pc * (audienceCount || 0);
                    return (
                        <button
                            key={t.key}
                            type="button"
                            disabled={!writable}
                            onClick={() => onPick(t.key)}
                            className={`flex flex-col items-start gap-0.5 rounded-2xl border p-3 text-left transition-all ${
                                on
                                    ? "border-primary-01/40 bg-primary-01/8"
                                    : "border-s-subtle bg-b-surface2 hover:border-s-stroke2"
                            } ${writable ? "cursor-pointer" : "cursor-default"}`}
                        >
                            <span className="text-caption text-t-tertiary">
                                {t.name}
                            </span>
                            <span className="text-body-1 text-t-primary tabular-nums leading-tight">
                                {inr(pc, 2)}
                            </span>
                            <span className="text-caption text-t-tertiary">
                                /call
                            </span>
                            {(audienceCount || 0) > 0 && (
                                <span className="mt-1 text-caption text-t-secondary tabular-nums">
                                    ≈ {inr(proj, proj < 100 ? 2 : 0)} total
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

// ── one per-role provider select (Advanced mode) ──
function RoleSelect({
    label,
    value,
    options,
    onChange,
    writable,
}: {
    label: string;
    value: string;
    options: { id: string; name: string; builtin: boolean; available: boolean }[];
    onChange: (id: string) => void;
    writable: boolean;
}) {
    const opts: SelectOption[] = options.map((o, i) => ({
        id: i,
        name: o.available ? o.name : `${o.name} · no key`,
    }));
    const idx = options.findIndex((o) => o.id === value);
    const selected: SelectOption | null =
        idx >= 0 ? { id: idx, name: opts[idx].name } : null;
    return (
        <div className={!writable ? "pointer-events-none opacity-60" : ""}>
            <Select
                label={label}
                value={selected}
                onChange={(o) => {
                    const picked = options[o.id as number];
                    if (picked) onChange(picked.id);
                }}
                options={opts}
                placeholder="Choose provider"
            />
        </div>
    );
}
