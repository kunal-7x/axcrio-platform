"use client";
import { useCallback, useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Button from "@/components/Button";
import { getVoiceTuning, saveVoiceTuning, type VoiceTuning } from "@/lib/api";
import { SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, ghostBtnCls } from "../_shared";

const SLIDERS: { key: keyof VoiceTuning; label: string; min: number; max: number; step: number; hint: string }[] = [
    { key: "el_speed", label: "Speaking speed", min: 0.7, max: 1.2, step: 0.01, hint: "1.0 = normal, higher = faster. ~1.1 is a natural brisk pace." },
    { key: "el_stability", label: "Stability", min: 0, max: 1, step: 0.05, hint: "Lower = more expressive/varied; higher = flatter/consistent." },
    { key: "el_similarity", label: "Similarity boost", min: 0, max: 1, step: 0.05, hint: "How closely it hugs the original voice timbre." },
    { key: "el_style", label: "Style", min: 0, max: 1, step: 0.05, hint: "Style exaggeration. 0 is fastest (adds latency above 0)." },
];

function VoiceTuningInner() {
    const [cfg, setCfg] = useState<VoiceTuning | null>(null);
    const [err, setErr] = useState("");
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);

    const load = useCallback(async () => {
        try { setErr(""); setCfg(await getVoiceTuning()); }
        catch (e) { setErr(e instanceof Error ? e.message : "Failed to load voice settings"); }
    }, []);
    useEffect(() => { void load(); }, [load]);

    const set = (k: keyof VoiceTuning, v: string) => { setSaved(false); setCfg((c) => (c ? { ...c, [k]: v } : c)); };

    const save = async () => {
        if (!cfg) return;
        setSaving(true); setErr("");
        try { setCfg(await saveVoiceTuning(cfg)); setSaved(true); setTimeout(() => setSaved(false), 2500); }
        catch (e) { setErr(e instanceof Error ? e.message : "Failed to save"); }
        finally { setSaving(false); }
    };

    const isEL = !cfg || cfg.tts_provider !== "sarvam";

    return (
        <Layout title="Voice Tuning">
            <SuperAdminHeaderF3 actions={
                <button className={ghostBtnCls} onClick={() => void load()}>
                    <Icon name="clock" className="size-4 fill-current" /> Reload
                </button>
            } />
            <ErrorBanner msg={err} />
            {!cfg ? (
                <div className="card p-6 text-t-tertiary">Loading voice settings…</div>
            ) : (
                <div className="flex flex-col gap-5 max-w-2xl">
                    <div className="card p-5 flex flex-col gap-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="text-h6 text-t-primary">TTS engine</div>
                                <div className="text-caption text-t-tertiary">Applies live on the next call — no restart.</div>
                            </div>
                            <select className="input-base w-44" value={cfg.tts_provider}
                                onChange={(e) => set("tts_provider", e.target.value)}>
                                <option value="elevenlabs">ElevenLabs (flash v2.5)</option>
                                <option value="sarvam">Sarvam Bulbul (India)</option>
                            </select>
                        </div>
                    </div>

                    {isEL && (
                        <div className="card p-5 flex flex-col gap-5">
                            <div className="text-h6 text-t-primary">ElevenLabs voice</div>
                            {SLIDERS.map((s) => {
                                const val = parseFloat(cfg[s.key] || "0") || 0;
                                return (
                                    <label key={s.key} className="block">
                                        <div className="flex items-center justify-between mb-1">
                                            <span className="text-body-2 text-t-secondary">{s.label}</span>
                                            <span className="text-caption tabular-nums text-t-primary font-medium">{val.toFixed(2)}</span>
                                        </div>
                                        <input type="range" className="w-full accent-[var(--primary-01)]"
                                            min={s.min} max={s.max} step={s.step} value={val}
                                            onChange={(e) => set(s.key, e.target.value)} />
                                        <div className="text-caption text-t-quaternary mt-0.5">{s.hint}</div>
                                    </label>
                                );
                            })}
                            <label className="flex items-center gap-2.5 cursor-pointer select-none">
                                <input type="checkbox" className="size-4 accent-[var(--primary-01)]"
                                    checked={cfg.el_speaker_boost === "1"}
                                    onChange={(e) => set("el_speaker_boost", e.target.checked ? "1" : "0")} />
                                <span className="text-body-2 text-t-secondary">Speaker boost (louder/clearer; adds a little latency)</span>
                            </label>
                            <label className="block">
                                <span className="text-caption text-t-tertiary">Voice ID (blank = default)</span>
                                <input className="input-base mt-1 w-full font-mono" placeholder="e.g. QTKSa2Iyv0yoxvXY2V8a"
                                    value={cfg.voice_id} onChange={(e) => set("voice_id", e.target.value)} />
                            </label>
                        </div>
                    )}

                    {!isEL && (
                        <div className="card p-5 flex flex-col gap-4">
                            <div className="text-h6 text-t-primary">Sarvam Bulbul</div>
                            <label className="block">
                                <span className="text-caption text-t-tertiary">Speaker</span>
                                <input className="input-base mt-1 w-full" placeholder="anushka / suhani / …"
                                    value={cfg.sarvam_tts_speaker} onChange={(e) => set("sarvam_tts_speaker", e.target.value)} />
                            </label>
                            <label className="block">
                                <span className="text-caption text-t-tertiary">Model</span>
                                <input className="input-base mt-1 w-full font-mono" placeholder="bulbul:v2 / bulbul:v3"
                                    value={cfg.sarvam_tts_model} onChange={(e) => set("sarvam_tts_model", e.target.value)} />
                            </label>
                            <div className="text-caption text-t-quaternary">Speed knobs above apply to ElevenLabs; Sarvam pace is env-managed for now.</div>
                        </div>
                    )}

                    <div className="flex items-center gap-3">
                        <Button isBlack disabled={saving} onClick={() => void save()}>
                            {saving ? "Saving…" : "Save — applies next call"}
                        </Button>
                        {saved && <span className="text-body-2 text-status-success">✓ Saved. Your next call uses these settings.</span>}
                    </div>
                </div>
            )}
        </Layout>
    );
}

export default function VoiceTuningPage() {
    return <SuperAdminGuard><VoiceTuningInner /></SuperAdminGuard>;
}
