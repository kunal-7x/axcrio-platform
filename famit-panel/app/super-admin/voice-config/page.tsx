"use client";

// ============================================================
// Voice Config — /super-admin/voice-config
// Pick the live speech-to-text (STT) provider the voice agent uses and manage
// the per-provider API keys. Two providers today:
//   • Deepgram — snappier turn-detection (~0.3s), best when latency is king.
//   • Sarvam   — best Hinglish / Indic accuracy, the default for this fleet.
// Reads GET /admin/voice-config on mount (masked keys), POSTs a PARTIAL body to
// save. Mirrors the Service Control Center visual language (same Layout shell,
// SuperAdminHeaderF3 tab strip, rounded-3xl bg-b-surface2 cards, token colours).
// White-labeled; dormant-safe (a 404 backend resolves to a clean default).
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import ProviderLogo from "@/components/ProviderLogo";
import {
    getVoiceConfig, saveVoiceConfig,
    type VoiceConfig, type VoiceSttProvider,
} from "@/lib/api";
import { SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, ghostBtnCls } from "../_shared";

const inputCls = "input-base h-10 w-full rounded-xl px-3 text-body-2";

type SttOption = {
    id: VoiceSttProvider;
    name: string;
    role: string;
    tagline: string;
    why: string;
    logo: string; // ProviderLogo provider key
    keyField: "deepgram_api_key" | "sarvam_api_key";
    keyHint: string;
};

const STT_OPTIONS: SttOption[] = [
    {
        id: "deepgram",
        name: "Deepgram",
        role: "STT",
        tagline: "Snappier — fastest turn-detection",
        why: "≈ 0.3s end-of-turn detection. Pick this when latency is king — the agent starts replying sooner, calls feel more natural.",
        logo: "deepgram",
        keyField: "deepgram_api_key",
        keyHint: "Deepgram API key (dg_…)",
    },
    {
        id: "sarvam",
        name: "Sarvam",
        role: "STT",
        tagline: "Best Hinglish — highest Indic accuracy",
        why: "Tuned for Hinglish / Indic speech. Pick this when accuracy on mixed Hindi-English matters more than the last fraction of a second.",
        logo: "sarvam",
        keyField: "sarvam_api_key",
        keyHint: "Sarvam API key",
    },
];

function VoiceConfigInner() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [cfg, setCfg] = useState<VoiceConfig | null>(null);

    // working selection + draft keys (only sent when non-empty)
    const [stt, setStt] = useState<VoiceSttProvider>("sarvam");
    const [draftKeys, setDraftKeys] = useState<Record<string, string>>({});

    const load = useCallback(() => {
        setLoading(true);
        getVoiceConfig()
            .then((c) => {
                setCfg(c);
                const p = (c.stt_provider as VoiceSttProvider) || "sarvam";
                setStt(p === "deepgram" ? "deepgram" : "sarvam");
                setErr("");
            })
            .catch(() => setErr("Couldn't load voice config — retry."))
            .finally(() => setLoading(false));
    }, []);
    useEffect(() => { load(); }, [load]);

    const toast = (m: string) => { setNote(m); setTimeout(() => setNote(""), 2800); };

    // masked existing key per provider (display-only)
    const maskedOf = useCallback((opt: SttOption): string => {
        const pc = cfg?.providers?.[opt.id];
        if (pc?.key_masked) return pc.key_masked;
        if (pc?.configured) return "configured";
        return "";
    }, [cfg]);

    // dirty when STT changed OR any draft key entered
    const dirty = useMemo(() => {
        const sttChanged = cfg ? (cfg.stt_provider || "sarvam") !== stt : false;
        const anyKey = Object.values(draftKeys).some((v) => (v || "").trim());
        return sttChanged || anyKey;
    }, [cfg, stt, draftKeys]);

    const save = useCallback(async () => {
        setBusy(true);
        try {
            const body: Record<string, string> = { stt_provider: stt };
            for (const opt of STT_OPTIONS) {
                const v = (draftKeys[opt.keyField] || "").trim();
                if (v) body[opt.keyField] = v;
            }
            const next = await saveVoiceConfig(body);
            setCfg(next);
            setStt(((next.stt_provider as VoiceSttProvider) === "deepgram" ? "deepgram" : "sarvam"));
            setDraftKeys({});
            toast("Voice config saved — live on the next call.");
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't save voice config");
        } finally {
            setBusy(false);
        }
    }, [stt, draftKeys]);

    // Save a SINGLE provider key immediately (the clear "add this key" action).
    const saveKey = useCallback(async (opt: SttOption) => {
        const v = (draftKeys[opt.keyField] || "").trim();
        if (!v) return;
        setBusy(true);
        try {
            const next = await saveVoiceConfig({ [opt.keyField]: v });
            setCfg(next);
            setDraftKeys((x) => ({ ...x, [opt.keyField]: "" }));
            toast(`${opt.name} key saved — live on the next call.`);
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't save key");
        } finally {
            setBusy(false);
        }
    }, [draftKeys]);

    const active = STT_OPTIONS.find((o) => o.id === stt) ?? STT_OPTIONS[0];

    return (
        <Layout title="Voice Config">
            <SuperAdminHeaderF3 actions={
                <button onClick={load} className={ghostBtnCls} disabled={loading}>
                    <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />{loading ? "…" : "Refresh"}
                </button>
            } />
            <ErrorBanner msg={err} />
            {note && <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-b-surface3 px-4 py-2 text-caption text-t-secondary"><Icon name="check-circle" className="size-4 fill-current" />{note}</div>}

            {/* intro */}
            <div className="mb-4 rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4">
                <div className="flex items-center gap-2.5">
                    <span className="text-button text-t-primary">Speech-to-text (STT) provider</span>
                    <Badge variant="success">STT</Badge>
                    <Badge variant={stt === "deepgram" ? "info" : "neutral"} dot className="ml-auto">live: {active.name}</Badge>
                </div>
                <p className="mt-2 text-caption text-t-tertiary">
                    This is what transcribes the caller in real time. It is the single biggest lever on how <em>snappy</em> vs how <em>accurate</em> the agent feels. Pick one, drop in its key, save — it is live on the next call.
                </p>
            </div>

            {/* ── segmented STT picker (two clean cards) ── */}
            <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                {STT_OPTIONS.map((opt) => {
                    const sel = stt === opt.id;
                    const masked = maskedOf(opt);
                    return (
                        <button
                            key={opt.id}
                            type="button"
                            onClick={() => setStt(opt.id)}
                            className={`flex flex-col items-start rounded-3xl p-4 text-left ring-1 ring-inset transition-all ${
                                sel
                                    ? "bg-b-surface2 ring-2 ring-primary-01"
                                    : "bg-b-surface2 ring-s-subtle hover:ring-s-highlight"
                            }`}
                        >
                            <div className="flex w-full items-center gap-2.5">
                                <ProviderLogo provider={opt.logo} size={30} className="shrink-0" />
                                <span className="text-button text-t-primary">{opt.name}</span>
                                <Badge variant="success">{opt.role}</Badge>
                                <span className="ml-auto">
                                    {sel
                                        ? <Badge variant="success" dot>selected</Badge>
                                        : <Badge variant="neutral">tap to select</Badge>}
                                </span>
                            </div>
                            <span className="mt-2 text-body-2 text-t-secondary">{opt.tagline}</span>
                            <p className="mt-1.5 text-caption text-t-tertiary">{opt.why}</p>
                            <div className="mt-2.5">
                                {masked
                                    ? <span className="inline-flex items-center gap-1.5 rounded-full bg-b-surface3 px-2.5 py-1 text-caption text-t-secondary"><Icon name="check-circle" className="size-3.5 fill-current" />key {masked === "configured" ? "configured" : <span className="font-mono">{masked}</span>}</span>
                                    : <span className="inline-flex items-center gap-1.5 rounded-full bg-b-surface3 px-2.5 py-1 text-caption text-t-tertiary"><Icon name="info" className="size-3.5 fill-current" />no key yet</span>}
                            </div>
                        </button>
                    );
                })}
            </div>

            {/* ── provider keys ── */}
            <div className="mt-4 rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4">
                <div className="mb-3 flex items-center gap-2">
                    <Icon name="key" className="size-4 fill-t-secondary" />
                    <span className="text-button text-t-primary">Provider keys</span>
                    <span className="text-caption text-t-tertiary">stored encrypted on the box · the live key is never shown</span>
                </div>
                <div className="flex flex-col gap-3">
                    {STT_OPTIONS.map((opt) => {
                        const masked = maskedOf(opt);
                        const isLive = stt === opt.id;
                        return (
                            <div key={opt.id} className="flex flex-col gap-2 rounded-2xl bg-b-surface1 p-3.5 ring-1 ring-inset ring-s-subtle dark:bg-shade-04/30 sm:flex-row sm:items-center">
                                <div className="flex min-w-[10rem] items-center gap-2">
                                    <ProviderLogo provider={opt.logo} size={22} className="shrink-0" />
                                    <span className="text-body-2 text-t-primary">{opt.name}</span>
                                    {isLive && <Badge variant="success" dot>live</Badge>}
                                </div>
                                <input
                                    type="password"
                                    className={`${inputCls} flex-1`}
                                    placeholder={masked ? `Replace key (current ${masked === "configured" ? "set" : masked})` : opt.keyHint}
                                    value={draftKeys[opt.keyField] || ""}
                                    onChange={(e) => setDraftKeys((x) => ({ ...x, [opt.keyField]: e.target.value }))}
                                    onKeyDown={(e) => { if (e.key === "Enter") saveKey(opt); }}
                                />
                                <button
                                    type="button"
                                    disabled={busy || !(draftKeys[opt.keyField] || "").trim()}
                                    onClick={() => saveKey(opt)}
                                    className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-xl bg-primary-01 px-4 text-button text-white transition-all hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
                                >
                                    <Icon name="check-circle" className="size-4 fill-current" />
                                    {masked ? "Update" : "Add key"}
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* ── custom STT provider ── */}
            <div className="mt-4 rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <Icon name="plus" className="size-4 fill-t-secondary" />
                            <span className="text-button text-t-primary">Custom STT provider</span>
                        </div>
                        <p className="mt-1 text-caption text-t-tertiary">
                            Need an STT engine that is not listed here? Add it as a custom service in the Service Control Center — its key lives alongside everything else and the agent can use it once configured.
                        </p>
                    </div>
                    <Link href="/super-admin/services" className={`${ghostBtnCls} shrink-0 sm:ml-auto`}>
                        <Icon name="plus" className="size-4 fill-current" />
                        Add a custom provider
                    </Link>
                </div>
            </div>

            {/* ── save bar ── */}
            <div className="mt-4 flex items-center gap-3">
                <button
                    disabled={busy || loading || !dirty}
                    onClick={save}
                    className="inline-flex h-10 items-center rounded-full bg-primary-01 px-6 text-button text-white disabled:opacity-50"
                >
                    {busy ? "Saving…" : "Save voice config"}
                </button>
                <span className="text-caption text-t-tertiary">
                    {dirty ? "Unsaved changes — STT and any entered keys will be applied." : "Nothing to save — everything is up to date."}
                </span>
            </div>
        </Layout>
    );
}

export default function VoiceConfigPage() {
    return <SuperAdminGuard><VoiceConfigInner /></SuperAdminGuard>;
}
