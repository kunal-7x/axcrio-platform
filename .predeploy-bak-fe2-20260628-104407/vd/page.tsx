"use client";

// ============================================================
// Voice Defaults — /super-admin/voice-defaults
//
// The per-component STT/LLM/TTS picker that USED to live on each client's Run page is now HERE, set
// once by the operator. Clients pick only the quality tier (Lean/Standard/Premium); the exact engine
// each tier maps to — plus the telephony rate — is controlled centrally on this page. Writes
// VAR/tier_overrides.json (deep-merged over the static defaults by GET /tiers), so changes take effect
// on the Run-page slider + cost meter immediately, with NO deploy. Real provider names shown (operator
// console); the client UI white-labels them to Haptica names. Super-admin gated; dormant-safe.
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import {
    getTierConfig, saveTierConfig, type TierConfigView, type TiersPayload, type Tier, type RateCard,
} from "@/lib/api";
import { SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, ghostBtnCls } from "../_shared";

type RoleOpt = { provider: string; model: string; rate_key: string; label: string };

// Curated engine options per role (real provider names — operator console). value === rate_key.
const STT_OPTS: RoleOpt[] = [
    { provider: "sarvam", model: "saarika:v2.5", rate_key: "sarvam", label: "Sarvam Saarika · ₹0.50/min" },
    { provider: "deepgram", model: "nova-3", rate_key: "deepgram", label: "Deepgram Nova-3 · ₹0.55/min" },
];
const LLM_OPTS: RoleOpt[] = [
    { provider: "groq", model: "gpt-oss-20b", rate_key: "groq-gpt-oss-20b", label: "Groq gpt-oss-20B · fast/cheap" },
    { provider: "groq", model: "llama-3.3-70b", rate_key: "groq-llama-3.3-70b", label: "Groq Llama-3.3-70B · best quality" },
];
const TTS_OPTS: RoleOpt[] = [
    { provider: "sarvam", model: "bulbul:v2", rate_key: "sarvam-bulbul-v2", label: "Sarvam Bulbul v2 · ₹1.5/1k" },
    { provider: "sarvam", model: "bulbul:v3", rate_key: "sarvam-bulbul-v3", label: "Sarvam Bulbul v3 · ₹3.0/1k" },
    { provider: "elevenlabs", model: "eleven_flash_v2_5", rate_key: "elevenlabs-flash-v2.5", label: "ElevenLabs Flash v2.5 · ₹4.73/1k" },
];
const ROLE_OPTS: Record<"stt" | "llm" | "tts", RoleOpt[]> = { stt: STT_OPTS, llm: LLM_OPTS, tts: TTS_OPTS };

const selectCls = "input-base h-10 w-full rounded-xl px-3 text-body-2";

function perMin(t: Tier, rc: RateCard): number {
    const a = rc.assumptions;
    const stt = rc.stt[t.stt.rate_key]?.inr_per_min ?? 0;
    const llm = ((rc.llm[t.llm.rate_key]?.inr_per_mtok ?? 0) * a.llm_tokens_per_min) / 1_000_000;
    const tts = ((rc.tts[t.tts.rate_key]?.inr_per_1k ?? 0) * a.tts_chars_per_min) / 1000;
    const tel = rc.telephony_verified && (rc.telephony_inr_per_min ?? 0) > 0 ? rc.telephony_inr_per_min : 0;
    return tel + stt + llm + tts;
}

function VoiceDefaultsInner() {
    const [cfg, setCfg] = useState<TierConfigView>({ overrides: {}, effective: {} });
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [note, setNote] = useState("");

    const load = useCallback(async () => {
        setLoading(true);
        try { setCfg(await getTierConfig()); setErr(""); }
        catch { setErr("Could not load voice defaults"); }
        finally { setLoading(false); }
    }, []);
    useEffect(() => { void load(); }, [load]);

    const eff = (cfg.effective || {}) as Partial<TiersPayload>;
    const tiers = (eff.tiers || []) as Tier[];
    const rc = eff.rate_card as RateCard | undefined;

    const save = useCallback(async (partial: Record<string, unknown>, msg: string) => {
        setBusy(true);
        try {
            setCfg(await saveTierConfig(partial));
            setErr(""); setNote(msg);
            window.setTimeout(() => setNote(""), 2500);
        } catch { setErr("Save failed"); }
        finally { setBusy(false); }
    }, []);

    const onRole = (tierKey: string, role: "stt" | "llm" | "tts", rateKey: string) => {
        const opt = ROLE_OPTS[role].find((o) => o.rate_key === rateKey);
        if (!opt) return;
        void save(
            { tiers: { [tierKey]: { [role]: { provider: opt.provider, model: opt.model, rate_key: opt.rate_key } } } },
            `${tierKey} ${role.toUpperCase()} → ${opt.label.split(" · ")[0]}`,
        );
    };

    const tel = rc?.telephony_inr_per_min ?? 0.4;
    const [telDraft, setTelDraft] = useState("");
    useEffect(() => { setTelDraft(String(rc?.telephony_inr_per_min ?? 0.4)); }, [rc?.telephony_inr_per_min]);

    const overrideCount = useMemo(() => Object.keys(cfg.overrides || {}).length, [cfg.overrides]);

    return (
        <Layout title="Voice Defaults">
            <SuperAdminHeaderF3 actions={
                <button onClick={load} className={ghostBtnCls} disabled={loading}>
                    <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />{loading ? "…" : "Refresh"}
                </button>
            } />
            <ErrorBanner msg={err} />
            {note && (
                <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-b-surface3 px-4 py-2 text-caption text-t-secondary">
                    <Icon name="check-circle" className="size-4 fill-current" />{note}
                </div>
            )}

            <div className="mb-4 flex items-start gap-2 p-3.5 rounded-2xl bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04/30">
                <Icon name="info" className="size-4 fill-t-tertiary shrink-0 mt-0.5" />
                <p className="text-caption text-t-secondary leading-relaxed">
                    These are the engines each <span className="text-t-primary">quality tier</span> maps to on the
                    client Run page. Clients only pick the tier — they never see these provider names (the Run page
                    white-labels them to Haptica). Changes apply to the slider + cost meter immediately.
                    {overrideCount > 0 && <span className="text-t-tertiary"> · {overrideCount} override group(s) active</span>}
                </p>
            </div>

            {/* telephony rate */}
            <div className="mb-4 rounded-3xl bg-b-surface1 ring-1 ring-s-subtle ring-inset p-5 dark:bg-shade-04/30">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div>
                        <div className="text-button text-t-primary">Telephony rate · Famit AI Telecom Infrastructure</div>
                        <div className="text-caption text-t-tertiary">Flat per-minute SIP cost included in the all-in total on every tier.</div>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="text-caption text-t-tertiary">₹</span>
                        <input className="input-base h-10 w-28 rounded-xl px-3 text-body-2 tabular-nums" inputMode="decimal"
                            value={telDraft} onChange={(e) => setTelDraft(e.target.value.replace(/[^0-9.]/g, ""))} />
                        <span className="text-caption text-t-tertiary">/min</span>
                        <button disabled={busy}
                            onClick={() => save({ telephony_inr_per_min: Math.max(0, parseFloat(telDraft) || 0), telephony_verified: true }, "Telephony rate saved")}
                            className="h-10 px-4 rounded-xl bg-primary-01 text-button text-white disabled:opacity-50">Save</button>
                    </div>
                </div>
            </div>

            {/* per-tier engine pickers */}
            {tiers.length === 0 && !loading ? (
                <div className="rounded-3xl bg-b-surface1 ring-1 ring-s-subtle p-6 text-caption text-t-tertiary">
                    Tier data unavailable. Check the backend GET /tiers route.
                </div>
            ) : (
                <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-1">
                    {tiers.map((t) => (
                        <div key={t.key} className="rounded-3xl bg-b-surface1 ring-1 ring-s-subtle ring-inset p-5 dark:bg-shade-04/30">
                            <div className="flex items-center justify-between mb-3">
                                <div>
                                    <div className="text-button text-t-primary">{t.name}</div>
                                    <div className="text-caption text-t-tertiary">{t.quality}</div>
                                </div>
                                {rc && (
                                    <div className="text-right">
                                        <div className="text-h6 text-t-primary tabular-nums leading-none">≈ ₹{perMin(t, rc).toFixed(2)}</div>
                                        <div className="text-caption text-t-tertiary">/min all-in</div>
                                    </div>
                                )}
                            </div>
                            <div className="space-y-3">
                                {(["stt", "llm", "tts"] as const).map((role) => (
                                    <label key={role} className="block">
                                        <span className="text-caption text-t-tertiary">
                                            {role === "stt" ? "Speech-to-text" : role === "llm" ? "Language model" : "Text-to-speech"}
                                        </span>
                                        <select className={`${selectCls} mt-1`} disabled={busy}
                                            value={t[role].rate_key}
                                            onChange={(e) => onRole(t.key, role, e.target.value)}>
                                            {/* current value may not be in the curated list → show it so it isn't lost */}
                                            {!ROLE_OPTS[role].some((o) => o.rate_key === t[role].rate_key) && (
                                                <option value={t[role].rate_key}>{t[role].provider} · {t[role].model}</option>
                                            )}
                                            {ROLE_OPTS[role].map((o) => (
                                                <option key={o.rate_key} value={o.rate_key}>{o.label}</option>
                                            ))}
                                        </select>
                                    </label>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </Layout>
    );
}

export default function VoiceDefaultsPage() {
    return <SuperAdminGuard><VoiceDefaultsInner /></SuperAdminGuard>;
}
