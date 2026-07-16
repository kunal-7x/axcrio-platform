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
    getProviderHealth,
    getVoices,
    getCampaign,
    updateCampaign,
    voicePreviewUrl,
    getCampaignCPL,
    type ProviderHealth,
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
import { getVerticals, type VerticalLanguage } from "@/lib/verticals";
import ProviderLock, { type ProviderLockState } from "./_provider-lock";
import CostBreakdown from "./_cost-breakdown";
import {
    CURATED_VOICES,
    VOICE_META,
    prettyAccent,
    accentFlags,
    gradientImage,
    cardBase,
} from "./_voice-catalog";

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

const langLabel = (l: VerticalLanguage): string =>
    l.international
        ? `${l.name} (${l.native}) · International`
        : l.native && l.native !== l.name
          ? `${l.name} (${l.native})`
          : l.name;

export default function VoiceProviders({ campaignId, audienceCount, writable }: Props) {
    const [tiersData, setTiersData] = useState<TiersPayload | null>(null);
    const [byRole, setByRole] = useState<ProvidersByRole>({ stt: [], llm: [], tts: [] });
    const [providersAvail, setProvidersAvail] = useState<Record<string, boolean>>({});
    // realtime per-provider network health (signal bars + latency), keyed by provider id
    const [healthMap, setHealthMap] = useState<Record<string, ProviderHealth>>({});

    // campaign-persisted config
    const [tier, setTier] = useState<CampaignTier>("lean");
    const [voiceId, setVoiceId] = useState<string>("");
    const [language, setLanguage] = useState<string>("");           // call language (regional + international)
    const [langCat, setLangCat] = useState<VerticalLanguage[]>([]);
    const [sttP, setSttP] = useState<string>("");
    const [llmP, setLlmP] = useState<string>("");
    const [llmModel, setLlmModel] = useState<string>(""); // per-campaign Groq model (advanced)
    const [ttsP, setTtsP] = useState<string>("");
    const [avgMin, setAvgMin] = useState<number>(1.5);

    // base campaign fields we must preserve on save (backend replaces `fields` wholesale)
    const baseFields = useRef<CampaignFields>({});

    const [voices, setVoices] = useState<Voice[]>([]);
    const [voiceProvider, setVoiceProvider] = useState<VoiceProvider>("elevenlabs");
    // true when the live ElevenLabs list came back empty and we fell back to the
    // curated catalogue — surfaced as a calm caption (never an error wall).
    const [usingFallback, setUsingFallback] = useState(false);
    // gallery filters
    const [voiceQuery, setVoiceQuery] = useState("");
    const [genderFilter, setGenderFilter] = useState<"all" | "female" | "male">("all");
    const [advanced, setAdvanced] = useState(false);
    const [saving, setSaving] = useState(false);
    const [savedNote, setSavedNote] = useState("");
    const [loaded, setLoaded] = useState(false);

    const audioRef = useRef<HTMLAudioElement | null>(null);
    // last voice_id whose preview we attempted (so <audio onError> knows which row to flag)
    const attemptedId = useRef<string>("");
    // object URL for the buffered preview clip (revoked before each new play / on unmount)
    const objUrlRef = useRef<string>("");
    // monotonic play-request id — every togglePlay captures it; an older in-flight
    // request bails as soon as a newer one starts (rapid clicks / provider swap).
    const playReqRef = useRef(0);
    // synchronous mirror of playingId so the stop-guard is correct even before the
    // async setPlayingId has committed (avoids the stale-closure double-fetch).
    const playingRef = useRef<string>("");
    // true while we're reassigning <audio>.src — suppresses the implicit "pause"
    // the media element fires on src change (which would flash the equalizer off).
    const swapRef = useRef(false);
    const [playingId, setPlayingId] = useState<string>("");
    // voice_id whose preview is buffering (avatar shows a spinner)
    const [loadingId, setLoadingId] = useState<string>("");
    // voice_id whose preview failed (network / unsupported / 502) -> show an inline caption
    const [previewError, setPreviewError] = useState<string>("");

    // WAVE C: campaign-level CPL (cost ÷ qualified) — dormant-safe, nulls hide the line.
    const [cpl, setCpl] = useState<CampaignCPL | null>(null);

    // ── stop / reset any in-flight or playing preview (provider/campaign switch,
    // unmount). Defined early so the load + campaign effects can depend on it. ──
    const stopPreview = useCallback(() => {
        playReqRef.current++; // invalidate any in-flight togglePlay
        if (audioRef.current) audioRef.current.pause();
        if (objUrlRef.current) {
            URL.revokeObjectURL(objUrlRef.current);
            objUrlRef.current = "";
        }
        playingRef.current = "";
        setPlayingId("");
        setLoadingId("");
        setPreviewError("");
    }, []);

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
                const t = (f.tier as CampaignTier) || "lean";
                setTier(t);
                setVoiceId(typeof f.voice_id === "string" ? f.voice_id : "");
                setSttP(typeof f.stt_provider === "string" ? f.stt_provider : "");
                setLlmP(typeof f.llm_provider === "string" ? f.llm_provider : "");
                setLlmModel(typeof f.llm_model === "string" ? f.llm_model : "");
                setTtsP(typeof f.tts_provider === "string" ? f.tts_provider : "");
                setAvgMin(typeof f.est_avg_call_min === "number" ? f.est_avg_call_min : 1.5);
                setLanguage(typeof f.language === "string" ? f.language : "");
                setAdvanced(t === "custom");
            })
            .catch(() => {})
            .finally(() => !cancelled && setLoaded(true));
        return () => {
            cancelled = true;
        };
    }, [campaignId]);

    // ── call-language catalogue (regional + international); dormant-safe ──
    useEffect(() => {
        getVerticals().then((c) => setLangCat(c.languages)).catch(() => {});
    }, []);

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

    // STT options for the Advanced dropdown: the live backend list wins (keeps its
    // real `available`/key state), then we append any built-in STT the backend
    // didn't enumerate — so Deepgram (a first-class agent STT now) is always
    // selectable alongside Sarvam/ElevenLabs even on a dormant /providers list.
    const sttOptions = useMemo(() => {
        const seen = new Set(byRole.stt.map((o) => o.id));
        return [...byRole.stt, ...BUILTIN_STT.filter((o) => !seen.has(o.id))];
    }, [byRole.stt]);

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

    // ── realtime provider network health: poll the resolved {llm,tts,stt} every 5s ──
    // Best-effort; a fetch failure just leaves the last-known bars in place (never an error).
    const healthIds = useMemo(
        () => Array.from(new Set([resolved.llm, resolved.tts, resolved.stt].filter(Boolean))),
        [resolved]
    );
    const healthKey = healthIds.join(",");
    useEffect(() => {
        if (!campaignId || !healthKey) return;
        let cancelled = false;
        const ids = healthKey.split(",");
        const tick = () => {
            getProviderHealth(ids)
                .then((rows) => {
                    if (cancelled) return;
                    setHealthMap((prev) => {
                        const m = { ...prev };
                        for (const r of rows) m[r.id] = r;
                        return m;
                    });
                })
                .catch(() => {});
        };
        tick();
        const iv = setInterval(tick, 5000);
        return () => {
            cancelled = true;
            clearInterval(iv);
        };
    }, [campaignId, healthKey]);

    // resolved voice display name (fall back to the id so the banner is never blank)
    const resolvedVoiceName = useMemo(() => {
        const v = voices.find((x) => x.voice_id === voiceId);
        return v?.name || voiceId || "";
    }, [voices, voiceId]);

    // the currently-selected voice object (for the always-visible header bar).
    // If the saved voiceId isn't in the current list (e.g. a live/cloned id that
    // falls outside the curated fallback set), synthesise a minimal entry so the
    // selection is never silently dropped from the UI.
    const selectedVoice = useMemo<Voice | null>(() => {
        if (!voiceId) return null;
        return (
            voices.find((x) => x.voice_id === voiceId) || {
                voice_id: voiceId,
                name: resolvedVoiceName || voiceId,
            }
        );
    }, [voices, voiceId, resolvedVoiceName]);

    // gallery view: search (name / accent / persona) + gender filter
    const galleryVoices = useMemo(() => {
        const q = voiceQuery.trim().toLowerCase();
        return voices.filter((v) => {
            if (genderFilter !== "all") {
                // exact match (NOT .includes — "female".includes("male") is true!);
                // voices with no gender label stay visible under any filter.
                const g = (v.gender || "").toLowerCase();
                if (g && g !== genderFilter) return false;
            }
            if (!q) return true;
            const hay = [v.name, v.accent, VOICE_META[v.voice_id]?.persona]
                .filter(Boolean)
                .join(" ")
                .toLowerCase();
            return hay.includes(q);
        });
    }, [voices, voiceQuery, genderFilter]);

    // CONFIG-ONLY is today's truth; flips to LIVE only when the backend says ob_prov_live.
    const lockState: ProviderLockState = tiersData?.ob_prov_live
        ? "live"
        : "config-only";

    // ── load the voice list for the active TTS provider ──
    // When the live ElevenLabs catalogue comes back empty (no key on the box),
    // fall back to the curated set so the gallery is never an empty "0 voices"
    // wall. The live list ALWAYS wins when it has anything in it.
    useEffect(() => {
        const prov: VoiceProvider =
            activeTtsProvider === "elevenlabs" ? "elevenlabs" : "sarvam";
        // switching the catalogue → silence + reset any preview from the old provider
        stopPreview();
        setVoiceProvider(prov);
        let cancelled = false;
        const fallback = () => {
            if (cancelled) return;
            if (prov === "elevenlabs") {
                setVoices(CURATED_VOICES);
                setUsingFallback(true);
            } else {
                setVoices([]);
                setUsingFallback(false);
            }
        };
        getVoices(prov)
            .then((r) => {
                if (cancelled) return;
                if (r.voices && r.voices.length > 0) {
                    setVoices(r.voices);
                    setUsingFallback(false);
                } else {
                    fallback();
                }
            })
            .catch(fallback);
        return () => {
            cancelled = true;
        };
    }, [activeTtsProvider, stopPreview]);

    // stop audio + free the buffered clip when the campaign changes OR on unmount
    // (the component is NOT remounted on campaign switch, so a playing preview
    // would otherwise keep sounding from the prior campaign).
    useEffect(() => stopPreview, [campaignId, stopPreview]);

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
        // Big cold list -> protect budget with Lean. Small/qualified list -> Premium reads as worth it.
        // Standard is the safe middle default.
        if (audienceCount >= 200) return "lean";
        if (audienceCount > 0 && audienceCount <= 25) return "premium";
        return "standard";
    }, [audienceCount]);

    // ── play / stop a voice preview through ONE shared <audio> ──
    // Strategy (all FREE, no synthesis): when a voice carries a public preview_url
    // we BUFFER the clip and force Content-Type audio/mpeg via a Blob — this is the
    // load-bearing fix for Safari/iOS, which refuses the text/plain bytes EL serves
    // for a raw <audio src>. If the cross-origin fetch is blocked we fall back to a
    // direct <audio src>, then to the backend /voice-preview proxy. Any total
    // failure surfaces a calm inline caption — never a thrown error.
    const togglePlay = useCallback(
        async (v: Voice) => {
            const el = audioRef.current;
            if (!el) return;
            // toggle-stop: read the synchronous ref, never the (possibly stale)
            // playingId closure, so a second tap reliably stops the right voice.
            if (playingRef.current === v.voice_id && !el.paused) {
                playingRef.current = "";
                el.pause();
                setPlayingId("");
                return;
            }

            const myReq = ++playReqRef.current;
            const stale = () => myReq !== playReqRef.current;
            setPreviewError(""); // clear any prior failure on a fresh attempt
            attemptedId.current = v.voice_id;
            setLoadingId(v.voice_id);

            // free any previously buffered clip
            if (objUrlRef.current) {
                URL.revokeObjectURL(objUrlRef.current);
                objUrlRef.current = "";
            }

            const playSrc = async (src: string) => {
                swapRef.current = true; // ignore the implicit pause from the src swap
                el.src = src;
                try {
                    await el.play();
                } finally {
                    swapRef.current = false;
                }
            };

            const succeed = () => {
                playingRef.current = v.voice_id;
                setPlayingId(v.voice_id);
            };

            const triedProxyFirst = !v.preview_url;
            try {
                const previewUrl = v.preview_url;
                if (previewUrl) {
                    try {
                        const resp = await fetch(previewUrl, { mode: "cors" });
                        if (stale()) return;
                        if (!resp.ok) throw new Error(`preview ${resp.status}`);
                        const buf = await resp.arrayBuffer();
                        if (stale()) return;
                        const url = URL.createObjectURL(
                            new Blob([buf], { type: "audio/mpeg" })
                        );
                        if (stale()) {
                            URL.revokeObjectURL(url);
                            return;
                        }
                        objUrlRef.current = url;
                        await playSrc(url);
                    } catch {
                        // cross-origin fetch blocked → try the raw URL directly
                        if (stale()) return;
                        await playSrc(previewUrl);
                    }
                } else {
                    await playSrc(voicePreviewUrl(voiceProvider, v.voice_id));
                }
                if (stale()) return;
                succeed();
            } catch (err) {
                if (stale()) return;
                // last resort: the same-origin backend proxy — but skip it when the
                // primary attempt WAS already the proxy (Sarvam), to avoid a
                // redundant identical second request against a failing URL.
                if (!triedProxyFirst) {
                    try {
                        await playSrc(voicePreviewUrl(voiceProvider, v.voice_id));
                        if (stale()) return;
                        succeed();
                        return;
                    } catch (err2) {
                        if (stale()) return;
                        console.error("voice preview failed", v.voice_id, voiceProvider, err, err2);
                    }
                } else {
                    console.error("voice preview failed", v.voice_id, voiceProvider, err);
                }
                playingRef.current = "";
                setPlayingId("");
                setPreviewError(v.voice_id);
            } finally {
                if (!stale()) setLoadingId("");
            }
        },
        [voiceProvider]
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
                llm_model: llmModel,
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
        [campaignId, writable, tier, voiceId, sttP, llmP, llmModel, ttsP, avgMin]
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

    const order = tiersData?.order || ["lean", "standard", "premium"];
    const noCampaign = !campaignId;

    // provider-health row: the campaign's RESOLVED {LLM, TTS, STT} providers, each shown with a
    // realtime signal-strength meter + latency from /providers/health (polled above).
    const roleEntries: { role: string; label: string; pid: string }[] = [
        { role: "llm", label: "LLM", pid: resolved.llm },
        { role: "tts", label: "TTS", pid: resolved.tts },
        { role: "stt", label: "STT", pid: resolved.stt },
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
        <div className="flex flex-col gap-4">
            {/* shared hidden audio element for ALL voice previews */}
            <audio
                ref={audioRef}
                onEnded={() => {
                    playingRef.current = "";
                    setPlayingId("");
                }}
                onPause={() => {
                    // ignore the implicit pause fired while we reassign src mid-play
                    // (that would flash the equalizer off when switching voices)
                    if (swapRef.current) return;
                    playingRef.current = "";
                    setPlayingId("");
                }}
                onError={() => {
                    // Stop the equalizer if the media element errors mid-load. The
                    // failure CAPTION is owned solely by togglePlay's fallback
                    // cascade (proxy retry) — setting previewError here too would
                    // flash "unavailable" even when the proxy retry then succeeds.
                    console.error(
                        "voice preview <audio> error",
                        attemptedId.current,
                        voiceProvider
                    );
                    playingRef.current = "";
                    setPlayingId("");
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
                            <div className="grid grid-cols-3 gap-1.5 p-1 rounded-full bg-b-surface1 border border-s-subtle dark:bg-shade-04/40">
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
                                            className={`relative flex flex-col items-center justify-center h-14 rounded-full text-center transition-all ${
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
                                            <span className="mt-1 text-caption text-t-tertiary tabular-nums leading-none">
                                                ≈ {inr(t.est_inr_per_min)}/min
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

                        {/* ── call language (regional + international) ── */}
                        {langCat.length > 0 && (
                            <div className="mb-5">
                                <div className="flex items-center justify-between mb-3">
                                    <span className="text-sub-title-1">Call language</span>
                                    <span className="text-caption text-t-tertiary tabular-nums">{langCat.length} languages</span>
                                </div>
                                <div className={!writable ? "pointer-events-none opacity-60" : ""}>
                                    <Select
                                        value={(() => {
                                            const i = langCat.findIndex((l) => l.code === language);
                                            return i >= 0 ? { id: i, name: langLabel(langCat[i]) } : null;
                                        })()}
                                        onChange={(o) => {
                                            const code = langCat[o.id as number]?.code;
                                            if (code !== undefined) { setLanguage(code); void persist({ language: code }); }
                                        }}
                                        options={langCat.map((l, i) => ({ id: i, name: langLabel(l) }))}
                                        placeholder="Choose language (default Hinglish)"
                                    />
                                </div>
                                {(() => {
                                    const l = langCat.find((x) => x.code === language);
                                    if (l && !l.el_speakable)
                                        return <p className="mt-1.5 text-caption text-primary-03">{l.name} is spoken on the Sarvam engine only — set TTS to Sarvam (Advanced) for native audio.</p>;
                                    if (l && l.international)
                                        return <p className="mt-1.5 text-caption text-t-tertiary">International — the agent converses in {l.name} for the whole call.</p>;
                                    return <p className="mt-1.5 text-caption text-t-tertiary">Hindi / English / Hinglish, Indic and 20+ international languages supported.</p>;
                                })()}
                            </div>
                        )}

                        {/* ── premium voice gallery ── */}
                        <VoiceGallery
                            voices={voices}
                            galleryVoices={galleryVoices}
                            selectedVoice={selectedVoice}
                            voiceId={voiceId}
                            voiceProvider={voiceProvider}
                            usingFallback={usingFallback}
                            playingId={playingId}
                            loadingId={loadingId}
                            previewError={previewError}
                            voiceQuery={voiceQuery}
                            setVoiceQuery={setVoiceQuery}
                            genderFilter={genderFilter}
                            setGenderFilter={setGenderFilter}
                            onPreview={togglePlay}
                            onPick={onVoice}
                            writable={writable}
                        />
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

                {/* ══ CARD ③ — PROVIDERS ════════════════════════════════════════ */}
                <Card title="Providers">
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

                        {/* ── realtime provider network health (signal bars + latency) ── */}
                        <div className="flex items-center gap-x-5 gap-y-2 flex-wrap text-body-2 text-t-secondary">
                            <span className="text-t-tertiary">Live status:</span>
                            {roleEntries.map(({ role, label, pid }) => {
                                const h = healthMap[pid];
                                const avail = providersAvail[pid];
                                // fall back to the key-availability dot until the first health poll lands
                                const bars = h ? h.bars : avail ? 4 : 0;
                                const status: "green" | "yellow" | "red" = h
                                    ? h.status
                                    : avail
                                    ? "green"
                                    : "red";
                                const name = prettyProvider(pid);
                                return (
                                    <span
                                        key={role}
                                        className="inline-flex items-center gap-2"
                                        title={
                                            h
                                                ? `${label} · ${name} · ${
                                                      h.latency_ms != null
                                                          ? Math.round(h.latency_ms) + "ms"
                                                          : h.note || "—"
                                                  }`
                                                : `${label} · ${name}`
                                        }
                                    >
                                        <SignalBars bars={bars} status={status} />
                                        <span className="inline-flex items-baseline gap-1.5">
                                            <span className="text-overline text-t-tertiary">
                                                {label}
                                            </span>
                                            <span className="text-t-secondary">{name}</span>
                                            {h && h.latency_ms != null && (
                                                <span className="text-caption text-t-tertiary tabular-nums">
                                                    {Math.round(h.latency_ms)}ms
                                                </span>
                                            )}
                                            {h && h.latency_ms == null && h.note && (
                                                <span className="text-caption text-t-tertiary">
                                                    {h.note}
                                                </span>
                                            )}
                                        </span>
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
                                        options={sttOptions}
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
                                    {(llmP || resolved.llm) === "groq" && (
                                        <RoleSelect
                                            label="LLM model (Groq) — speed ↔ quality"
                                            value={llmModel || "meta-llama/llama-4-scout-17b-16e-instruct"}
                                            options={GROQ_MODELS}
                                            onChange={(id) => { setLlmModel(id); persist({ llm_model: id }); }}
                                            writable={writable}
                                        />
                                    )}
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

                        {/* ── Phase-2 honesty note ── */}
                        {tiersData?.ob_prov_pending && (
                            <div className="flex items-start gap-2 p-3 rounded-2xl bg-primary-05/8 text-body-2">
                                <Icon
                                    name="info"
                                    className="size-4 fill-primary-05 shrink-0 mt-0.5"
                                />
                                <span className="text-caption text-t-secondary">
                                    Voice selection and tier config apply now.
                                    Switching the live-call STT/LLM/TTS{" "}
                                    <span className="text-t-primary">provider</span>{" "}
                                    on the outbound leg (e.g. Sarvam → ElevenLabs)
                                    is coming in Phase 2 (needs founder approval).
                                </span>
                            </div>
                        )}
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
    if (!rateCard || tiers.length === 0) return null;
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
            <div className="grid grid-cols-3 gap-2">
                {tiers.map((t) => {
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

// Groq LLM models offered in Advanced — the speed↔quality lever. All three stream tokens in
// realtime over Groq's API; first-token latency rises with model size. Ids match Groq's API.
const GROQ_MODELS: { id: string; name: string; builtin: boolean; available: boolean }[] = [
    { id: "llama-3.1-8b-instant", name: "Fastest — Llama 3.1 8B · lowest latency", builtin: true, available: true },
    { id: "meta-llama/llama-4-scout-17b-16e-instruct", name: "Balanced — Llama 4 Scout 17B · default", builtin: true, available: true },
    { id: "llama-3.3-70b-versatile", name: "Best quality — Llama 3.3 70B · richer Hinglish, slower", builtin: true, available: true },
];

// Built-in STT providers offered in Advanced. The agent ships these first-class
// (Sarvam Saarika + Deepgram Nova via STT_PROVIDER), so they're always selectable
// even when the backend /providers list hasn't enumerated them yet. Shape matches
// the {id,name,builtin,available} the RoleSelect/byRole options use.
const BUILTIN_STT: { id: string; name: string; builtin: boolean; available: boolean }[] = [
    { id: "sarvam", name: "Sarvam", builtin: true, available: true },
    { id: "deepgram", name: "Deepgram", builtin: true, available: true },
    { id: "elevenlabs", name: "ElevenLabs", builtin: true, available: true },
];

// capitalize a single token (gender etc.) without touching multi-word strings
const cap = (s?: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");

// provider id -> display name for the Live-status row (falls back to a capitalized id)
const PROVIDER_NAME: Record<string, string> = {
    groq: "Groq",
    elevenlabs: "ElevenLabs",
    sarvam: "Sarvam",
    deepgram: "Deepgram",
    sambanova: "SambaNova",
    openrouter: "OpenRouter",
};
const prettyProvider = (id: string) => PROVIDER_NAME[id] || (id ? cap(id) : "—");

// ── mobile-network-style signal-strength meter: 5 ascending bars, coloured by health.
// green = fast/healthy, yellow = degraded, red = down / no key. `bars` (0-5) are filled; the
// rest sit dim. Pure presentation. ──
function SignalBars({ bars, status }: { bars: number; status: "green" | "yellow" | "red" }) {
    const tone =
        status === "green"
            ? "bg-[#00A656]"
            : status === "yellow"
            ? "bg-[#EF9D0E]"
            : "bg-[#FF6A55]";
    const heights = ["h-1.5", "h-2", "h-2.5", "h-3", "h-3.5"];
    return (
        <span className="inline-flex items-end gap-[2px]" aria-hidden>
            {heights.map((h, i) => (
                <span
                    key={i}
                    className={`w-[3px] rounded-[1px] transition-colors ${h} ${
                        i < bars ? tone : "bg-t-tertiary/25"
                    }`}
                />
            ))}
        </span>
    );
}

// ── animated 4-bar equalizer (reuses the brand .signal-glyph waveform).
// Bars inherit currentColor so they read on both tinted avatars and the solid
// terracotta "playing" button. ──
function EqualizerGlyph() {
    return (
        <span className="signal-glyph [&_i]:bg-current" aria-hidden>
            <i />
            <i />
            <i />
            <i />
        </span>
    );
}

// ── tiny buffering spinner (inherits the avatar's foreground colour) ──
function Spinner() {
    return (
        <span
            className="size-4 rounded-full border-2 border-current/30 border-t-current animate-spin"
            aria-hidden
        />
    );
}

// ════════════════════════════════════════════════════════════════════════
// VOICE GALLERY — the premium voice picker.
//   • always-visible "Selected voice" anchor with a big play button
//   • search + gender filter (only once there are enough voices to warrant it)
//   • a responsive grid of voice cards: avatar-as-play, persona, meta, tags
//   • a calm fallback caption when the curated catalogue is in play
// Pure presentation — selection persists through the parent's onPick.
// ════════════════════════════════════════════════════════════════════════
function VoiceGallery({
    voices,
    galleryVoices,
    selectedVoice,
    voiceId,
    voiceProvider,
    usingFallback,
    playingId,
    loadingId,
    previewError,
    voiceQuery,
    setVoiceQuery,
    genderFilter,
    setGenderFilter,
    onPreview,
    onPick,
    writable,
}: {
    voices: Voice[];
    galleryVoices: Voice[];
    selectedVoice: Voice | null;
    voiceId: string;
    voiceProvider: VoiceProvider;
    usingFallback: boolean;
    playingId: string;
    loadingId: string;
    previewError: string;
    voiceQuery: string;
    setVoiceQuery: (s: string) => void;
    genderFilter: "all" | "female" | "male";
    setGenderFilter: (g: "all" | "female" | "male") => void;
    onPreview: (v: Voice) => void;
    onPick: (id: string) => void;
    writable: boolean;
}) {
    const providerLabel = voiceProvider === "elevenlabs" ? "ElevenLabs" : "Sarvam";
    const isFiltered = galleryVoices.length !== voices.length;
    const showFilters = voices.length > 4;
    const GENDERS: ("all" | "female" | "male")[] = ["all", "female", "male"];

    return (
        <div>
            {/* header */}
            <div className="flex items-center justify-between mb-3">
                <span className="text-sub-title-1">
                    Voice{" "}
                    <span className="text-t-tertiary font-normal">
                        ({providerLabel})
                    </span>
                </span>
                <span className="text-caption text-t-tertiary tabular-nums">
                    {isFiltered
                        ? `${galleryVoices.length} of ${voices.length}`
                        : `${voices.length} ${
                              voices.length === 1 ? "voice" : "voices"
                          }`}
                </span>
            </div>

            {/* always-visible selected-voice anchor */}
            {selectedVoice && (
                <SelectedVoiceBar
                    v={selectedVoice}
                    playing={playingId === selectedVoice.voice_id}
                    loading={loadingId === selectedVoice.voice_id}
                    onPreview={() => onPreview(selectedVoice)}
                />
            )}

            {/* search + gender filter */}
            {showFilters && (
                <div className="flex items-center gap-2 mb-3 max-md:flex-col max-md:items-stretch">
                    <div className="relative flex-1 min-w-0">
                        <Icon
                            name="search"
                            className="absolute left-3 top-1/2 -translate-y-1/2 size-4 fill-t-tertiary pointer-events-none"
                        />
                        <input
                            type="text"
                            value={voiceQuery}
                            onChange={(e) => setVoiceQuery(e.target.value)}
                            placeholder="Search by name, accent or style…"
                            className="input-base w-full h-10 pl-9 pr-3 rounded-full text-body-2"
                        />
                    </div>
                    <div className="flex items-center gap-1 p-1 rounded-full bg-b-surface1 border border-s-subtle shrink-0 dark:bg-shade-04/40">
                        {GENDERS.map((g) => (
                            <button
                                key={g}
                                type="button"
                                onClick={() => setGenderFilter(g)}
                                className={`h-8 px-3.5 rounded-full text-caption font-medium transition-colors ${
                                    genderFilter === g
                                        ? "bg-b-surface2 shadow-depth text-t-primary"
                                        : "text-t-secondary hover:text-t-primary"
                                }`}
                            >
                                {g === "all" ? "All" : cap(g)}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* the grid */}
            {galleryVoices.length === 0 ? (
                <div className="px-4 py-10 text-center rounded-2xl border border-s-subtle bg-b-surface1 dark:bg-shade-04/30">
                    <div className="text-sub-title-2 text-t-primary">
                        {voices.length === 0
                            ? "No voices available yet"
                            : "No matching voices"}
                    </div>
                    <div className="mt-1 text-caption text-t-tertiary">
                        {voices.length === 0
                            ? `${providerLabel} voices will appear here once the provider is connected.`
                            : "Try a different search term or filter."}
                    </div>
                </div>
            ) : (
                <div className="relative">
                    <div className="max-h-[26rem] overflow-y-auto pb-6 pr-1 -mr-1 scrollbar scrollbar-thumb-t-tertiary/40 scrollbar-track-transparent">
                        <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3 max-[380px]:grid-cols-1">
                            {galleryVoices.map((v) => (
                                <VoiceCard
                                    key={v.voice_id}
                                    v={v}
                                    selected={voiceId === v.voice_id}
                                    playing={playingId === v.voice_id}
                                    loading={loadingId === v.voice_id}
                                    errored={previewError === v.voice_id}
                                    onSelect={() => onPick(v.voice_id)}
                                    onPreview={() => onPreview(v)}
                                    writable={writable}
                                />
                            ))}
                        </div>
                    </div>
                    {/* soft blurred fade so the half-row at the bottom melts away
                        and invites scrolling (premium, ~1.5 rows visible) */}
                    <div className="gallery-fade pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-b-surface2 via-b-surface2/40 to-transparent backdrop-blur-[3px]" />
                </div>
            )}

            {/* footer notes */}
            <div className="mt-3 space-y-1.5">
                <p className="text-body-2 text-t-tertiary">
                    Tap a voice to hear a free sample — your pick applies on the
                    next outbound call. The multilingual engine speaks the
                    selected Call language — Hindi / English / Hinglish, Indic and
                    20+ international languages.
                </p>
                {usingFallback && (
                    <p className="flex items-start gap-1.5 text-caption text-t-tertiary">
                        <Icon
                            name="info"
                            className="size-3.5 fill-t-tertiary shrink-0 mt-0.5"
                        />
                        Showing Famit&apos;s curated ElevenLabs voices. Your
                        account&apos;s full library loads automatically once the
                        ElevenLabs key is connected.
                    </p>
                )}
            </div>
        </div>
    );
}

// ── always-visible "Selected voice" anchor with its own play control ──
function SelectedVoiceBar({
    v,
    playing,
    loading,
    onPreview,
}: {
    v: Voice;
    playing: boolean;
    loading: boolean;
    onPreview: () => void;
}) {
    const meta = VOICE_META[v.voice_id];
    const sub = [meta?.persona, prettyAccent(v.accent), cap(v.gender)]
        .filter(Boolean)
        .join(" · ");
    return (
        <div className="flex items-center gap-3 p-2.5 mb-3 rounded-2xl border border-primary-01/30 bg-primary-01/[0.07] dark:bg-primary-01/[0.14]">
            <button
                type="button"
                onClick={onPreview}
                aria-label={`${playing ? "Stop" : "Play"} ${v.name} sample`}
                className={`grid place-items-center size-10 shrink-0 rounded-full transition-colors ${
                    playing
                        ? "bg-primary-01 text-shade-10"
                        : "bg-b-surface2 text-primary-01 ring-1 ring-primary-01/30 hover:bg-primary-01 hover:text-shade-10"
                }`}
            >
                {playing ? (
                    <EqualizerGlyph />
                ) : loading ? (
                    <Spinner />
                ) : (
                    <PlayGlyph playing={false} />
                )}
            </button>
            <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                    <span className="text-overline text-t-tertiary">
                        Selected voice
                    </span>
                    {meta?.recommended && (
                        <Icon
                            name="star-fill"
                            className="size-3 fill-primary-02 shrink-0"
                        />
                    )}
                </div>
                <div className="flex items-baseline gap-2">
                    <span className="font-medium text-t-primary truncate">
                        {v.name}
                    </span>
                    {sub && (
                        <span className="text-caption text-t-tertiary truncate">
                            {sub}
                        </span>
                    )}
                </div>
            </div>
            <button
                type="button"
                onClick={onPreview}
                className="shrink-0 inline-flex items-center h-8 px-3 rounded-full bg-b-surface2 border border-s-stroke2 text-caption font-medium text-t-secondary transition-colors hover:text-t-primary hover:border-s-highlight"
            >
                {playing ? "Playing…" : loading ? "Loading…" : "Play sample"}
            </button>
        </div>
    );
}

// ── one premium VOICE card matching the Figma: a fluid-gradient IMAGE block on
// top + a SEPARATE dark panel overlapping its bottom (the "split" two-card look),
// generous curves, stacked Name+flags / Gender / use-case / tone, and a play
// button that animates while playing. Whole card selects; play button previews. ──
function VoiceCard({
    v,
    selected,
    playing,
    loading,
    errored,
    onSelect,
    onPreview,
    writable,
}: {
    v: Voice;
    selected: boolean;
    playing: boolean;
    loading: boolean;
    errored: boolean;
    onSelect: () => void;
    onPreview: () => void;
    writable: boolean;
}) {
    const meta = VOICE_META[v.voice_id];
    const flags = accentFlags(v.accent);
    const img = gradientImage(v.voice_id);
    return (
        <div
            className={`voice-poster group relative aspect-[5/7] transition-transform duration-300 ease-out hover:-translate-y-1 ${
                playing ? "is-playing" : ""
            }`}
        >
            {/* full-card SELECT control (above the art, below the play btn) */}
            <button
                type="button"
                disabled={!writable}
                onClick={onSelect}
                aria-label={`Select ${v.name}`}
                aria-pressed={selected}
                className="absolute inset-0 z-[1] rounded-3xl outline-none focus-visible:ring-2 focus-visible:ring-white/70 disabled:cursor-default"
            />

            {/* ── TOP: the fluid-gradient image card ── */}
            <div
                className={`va-img inset-x-0 top-0 h-[70%] rounded-3xl ring-1 transition-shadow ${
                    selected
                        ? "ring-primary-01/70"
                        : "ring-white/10 group-hover:ring-white/25"
                }`}
                style={{ backgroundColor: cardBase(v.voice_id) }}
                aria-hidden
            >
                <div
                    className="va-img-inner"
                    style={{ backgroundImage: `url(${img})` }}
                />
                {/* scrim so the art melts into the dark panel below */}
                <div className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-b from-transparent to-black/55" />
            </div>

            {/* recommended pill (on the art) */}
            {meta?.recommended && (
                <span className="pointer-events-none absolute left-3 top-3 z-10 inline-flex h-6 items-center gap-1 rounded-full bg-black/45 px-2 text-[0.62rem] font-medium text-white ring-1 ring-white/15 backdrop-blur-sm">
                    <Icon name="star-fill" className="size-2.5 fill-[#FACC15]" />
                    Top pick
                </span>
            )}
            {/* selected check */}
            {selected && (
                <span className="pointer-events-none absolute right-3 top-3 z-10 grid size-6 place-items-center rounded-full bg-primary-01 text-shade-10">
                    <Icon name="check" className="size-4 fill-current" />
                </span>
            )}

            {/* ── BOTTOM: the separate dark panel, overlapping the art ── */}
            <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[2] flex h-[48%] flex-col rounded-3xl bg-[#161618] p-4 shadow-[0_-8px_24px_-12px_rgba(0,0,0,0.8)] ring-1 ring-white/10">
                <div className="min-w-0 flex-1">
                    <div className="truncate text-[1.05rem] font-semibold leading-tight text-white/90">
                        {v.name}{" "}
                        <span className="align-middle text-[0.85rem]">{flags}</span>
                    </div>
                    {v.gender && (
                        <div className="mt-1 text-[0.82rem] capitalize leading-snug text-white/55">
                            {cap(v.gender)}
                        </div>
                    )}
                    {meta?.useCase && (
                        <div className="text-[0.82rem] leading-snug text-white/55">
                            {meta.useCase}
                        </div>
                    )}
                    {meta?.tone && (
                        <div className="text-[0.82rem] leading-snug text-white/40">
                            {meta.tone}
                        </div>
                    )}
                </div>
                {errored && (
                    <div className="text-[0.62rem] text-[#fda4af]">
                        Preview unavailable
                    </div>
                )}
            </div>

            {/* play / pause button (on the dark panel) */}
            <button
                type="button"
                onClick={(e) => {
                    e.stopPropagation();
                    onPreview();
                }}
                aria-label={`${playing ? "Stop" : "Preview"} ${v.name}`}
                className={`absolute bottom-4 right-4 z-10 grid size-11 place-items-center rounded-full bg-black/90 text-white ring-1 ring-white/15 shadow-[0_8px_22px_-6px_rgba(0,0,0,0.8)] backdrop-blur-sm transition-transform hover:scale-110 active:scale-95 ${
                    playing ? "voice-play-pulse" : ""
                }`}
            >
                {loading ? (
                    <Spinner />
                ) : playing ? (
                    <EqualizerGlyph />
                ) : (
                    <PlayGlyph playing={false} />
                )}
            </button>
        </div>
    );
}
