"use client";

// ============================================================================
// Active Stack — the permanent, live "what's serving calls right now" card at the
// top of /super-admin/services. Shows the voice pipeline (STT → LLM → TTS), the
// provider currently serving each stage, real-time network latency (color-graded
// signal bars + ms), the combined pipeline RTT, and — on selecting a provider —
// its detailed metrics (keys live/cooling, picks, reachability). You can change
// the stack right here: the healthiest ENABLED provider serves each stage, so the
// per-provider switch is the real lever (disable Groq → SambaNova takes over).
//
// Data: GET /providers/health (real TCP-RTT, no quota) + the live key-pool status.
// Dormant-safe: every field degrades to "—" / red when a backend is unreachable.
// White-labeled. True end-to-end p95 (turn-detect → STT → LLM → TTS) lands in
// Voice Analytics once enabled; this card is the always-on network/health view.
// ============================================================================

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Select from "@/components/Select";
import Switch from "@/components/Switch";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import ProviderLogo from "@/components/ProviderLogo";
import { getProviderHealth, type ProviderHealth, type ProviderKeyStatusRow, type ProviderName, type CustomProvider } from "@/lib/api";
import { n, fmtNum } from "../_obs";

const HEX: Record<string, string> = { green: "#00A656", yellow: "#EF9D0E", red: "#FF6A55" };

// Voice pipeline stages, in order. `builtins` are the platform providers that serve
// each stage (LLM is a fallback chain — first healthy one wins). Custom providers of
// the matching kind join their stage automatically.
const STAGES: { key: "stt" | "llm" | "tts"; label: string; short: string; builtins: string[] }[] = [
    { key: "stt", label: "Speech-to-text", short: "STT", builtins: ["sarvam"] },
    { key: "llm", label: "Language model", short: "LLM", builtins: ["groq", "sambanova", "openrouter"] },
    { key: "tts", label: "Text-to-speech", short: "TTS", builtins: ["elevenlabs"] },
];

const HEALTH_IDS = ["sarvam", "groq", "sambanova", "openrouter", "elevenlabs"];

type Candidate = {
    id: string;            // provider key ("groq") or "cp:<id>" for custom
    provider?: ProviderName; // present for built-ins that live in the key store
    healthId?: string;     // id used by /providers/health (built-ins only)
    label: string;
    isCustom: boolean;
    envOnly: boolean;      // server-config only (e.g. ElevenLabs) — not toggleable here
    health?: ProviderHealth;
    rows: ProviderKeyStatusRow[]; // key-pool rows (built-ins only)
};

function gradeMs(ms: number | null | undefined): "green" | "yellow" | "red" {
    if (ms == null) return "red";
    if (ms <= 220) return "green";
    if (ms <= 800) return "yellow";
    return "red";
}

function SignalBars({ bars, status, big }: { bars: number; status: string; big?: boolean }) {
    const hex = HEX[status] || "#8A8A8A";
    const h = big ? [8, 12, 16, 20, 24] : [5, 8, 11, 14, 17];
    return (
        <span className="inline-flex items-end gap-[3px]" title={`${status} · ${bars}/5`} aria-label={`signal ${bars} of 5`}>
            {[0, 1, 2, 3, 4].map((i) => (
                <span key={i} className="w-[3px] rounded-full transition-colors"
                    style={{ height: h[i], background: i < bars ? hex : "currentColor", opacity: i < bars ? 1 : 0.18 }} />
            ))}
        </span>
    );
}

export default function ActiveStack({ status, custom, onToggleProvider, onToggleCustom, busy }: {
    status: Partial<Record<ProviderName, ProviderKeyStatusRow[]>>;
    custom: CustomProvider[];
    onToggleProvider: (p: ProviderName, enabled: boolean) => void;
    onToggleCustom: (id: string, enabled: boolean) => void;
    busy: boolean;
}) {
    const [health, setHealth] = useState<Record<string, ProviderHealth>>({});
    const [stageKey, setStageKey] = useState<"stt" | "llm" | "tts">("llm");
    const [inspect, setInspect] = useState<Record<string, string>>({}); // stageKey -> candidate id

    const pollHealth = useCallback(async () => {
        const rows = await getProviderHealth(HEALTH_IDS);
        const map: Record<string, ProviderHealth> = {};
        for (const r of rows) map[r.id] = r;
        setHealth(map);
    }, []);
    useEffect(() => {
        pollHealth();
        const t = setInterval(pollHealth, 8000);
        return () => clearInterval(t);
    }, [pollHealth]);

    // Build the candidate list per stage (built-ins in fallback order, then custom of that kind).
    const candidatesByStage = useMemo(() => {
        const out: Record<string, Candidate[]> = {};
        for (const st of STAGES) {
            const list: Candidate[] = [];
            for (const b of st.builtins) {
                const isStore = b !== "elevenlabs"; // elevenlabs is env-only (no key-store rows)
                list.push({
                    id: b, provider: isStore ? (b as ProviderName) : undefined, healthId: b,
                    label: health[b]?.label || b.charAt(0).toUpperCase() + b.slice(1),
                    isCustom: false, envOnly: !isStore, health: health[b],
                    rows: isStore ? (status[b as ProviderName] || []) : [],
                });
            }
            for (const c of custom) {
                if (c.kind === st.key) list.push({
                    id: `cp:${c.id}`, label: c.name, isCustom: true, envOnly: false,
                    rows: [], health: undefined,
                });
            }
            out[st.key] = list;
        }
        return out;
    }, [health, status, custom]);

    // Per-candidate rollup (live keys, cooling, picks, latency, "in stack").
    const roll = useCallback((c: Candidate) => {
        if (c.isCustom) {
            const cp = custom.find((x) => `cp:${x.id}` === c.id);
            return { live: cp?.available ? 1 : 0, total: cp?.available ? 1 : 0, cooling: 0, picks: 0,
                latency: null as number | null, gstatus: "red", bars: cp?.enabled ? 3 : 0, inStack: !!cp?.enabled, toggleable: true };
        }
        const live = c.rows.filter((r) => r.available).length;
        const cooling = c.rows.filter((r) => r.cooling).length;
        const picks = c.rows.reduce((a, r) => a + n(r.pick_count), 0);
        const storeRows = c.rows.filter((r) => r.source === "store");
        const inStack = c.health?.available ?? live > 0;
        const ms = c.health?.latency_ms ?? null;
        return {
            live, total: c.rows.length, cooling, picks, latency: ms,
            gstatus: c.health?.status || gradeMs(ms), bars: c.health?.bars ?? (inStack ? 3 : 0),
            inStack, toggleable: !c.envOnly && storeRows.length > 0,
        };
    }, [custom]);

    // The provider actively serving each stage = first available candidate (fallback order).
    const activeByStage = useMemo(() => {
        const out: Record<string, Candidate | undefined> = {};
        for (const st of STAGES) {
            const cands = candidatesByStage[st.key] || [];
            out[st.key] = cands.find((c) => roll(c).inStack) || cands[0];
        }
        return out;
    }, [candidatesByStage, roll]);

    // Combined pipeline RTT = sum of the active provider latency across the 3 stages.
    const combined = useMemo(() => {
        let sum = 0, known = 0;
        for (const st of STAGES) {
            const a = activeByStage[st.key];
            const ms = a ? roll(a).latency : null;
            if (ms != null) { sum += ms; known += 1; }
        }
        if (known === 0) return { ms: null as number | null, status: "red" };
        const status = sum <= 660 ? "green" : sum <= 2400 ? "yellow" : "red";
        return { ms: Math.round(sum), status };
    }, [activeByStage, roll]);

    const stage = STAGES.find((s) => s.key === stageKey)!;
    const cands = candidatesByStage[stageKey] || [];
    const activeCand = activeByStage[stageKey];
    const inspectId = inspect[stageKey] || activeCand?.id || cands[0]?.id;
    const inspectCand = cands.find((c) => c.id === inspectId) || activeCand || cands[0];
    const options = cands.map((c, i) => ({ id: i, name: c.label }));
    const selectedOpt = options.find((o) => cands[o.id]?.id === inspectId) || options[0] || null;

    const ir = inspectCand ? roll(inspectCand) : null;

    return (
        <div className="rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4 mb-4">
            <div className="flex items-center gap-2 mb-3">
                <span className="grid size-7 place-items-center rounded-full bg-primary-01/12"><Icon name="layers" className="size-4 fill-primary-01" /></span>
                <span className="text-button text-t-primary">Active voice stack</span>
                <Badge variant="success" dot>live</Badge>
                <span className="ml-auto flex items-center gap-2">
                    <span className="text-caption text-t-tertiary">combined RTT</span>
                    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-caption tabular-nums font-medium"
                        style={{ color: HEX[combined.status], background: `${HEX[combined.status]}1a` }}>
                        <span className="size-1.5 rounded-full" style={{ background: HEX[combined.status] }} />
                        {combined.ms == null ? "—" : `${combined.ms} ms`}
                    </span>
                </span>
            </div>

            {/* pipeline: STT → LLM → TTS */}
            <div className="flex items-stretch gap-2 max-md:flex-col">
                {STAGES.map((st, idx) => {
                    const a = activeByStage[st.key];
                    const r = a ? roll(a) : null;
                    const sel = st.key === stageKey;
                    const hex = HEX[r?.gstatus || "red"];
                    return (
                        <div key={st.key} className="contents">
                            <button onClick={() => setStageKey(st.key)}
                                className={`group flex-1 text-left rounded-2xl p-3 ring-1 ring-inset transition-colors ${sel ? "bg-b-surface3 ring-s-highlight" : "bg-b-surface1 ring-s-subtle hover:ring-s-highlight dark:bg-shade-04/30"}`}>
                                <div className="flex items-center justify-between">
                                    <span className="text-caption text-t-tertiary uppercase tracking-wide">{st.short}</span>
                                    <SignalBars bars={r?.bars ?? 0} status={r?.gstatus || "red"} />
                                </div>
                                <div className="mt-2 flex items-center gap-2">
                                    {a && <ProviderLogo provider={a.isCustom ? a.label : (a.healthId || a.id)} size={22} className="shrink-0" />}
                                    <span className="truncate text-body-2 text-t-primary">{a?.label || "—"}</span>
                                </div>
                                <div className="mt-1.5 flex items-center justify-between">
                                    <span className="text-caption tabular-nums" style={{ color: hex }}>
                                        {r?.latency == null ? (a?.isCustom ? "custom" : "offline") : `${Math.round(r.latency)} ms`}
                                    </span>
                                    <span className="text-caption text-t-tertiary">
                                        {r ? (r.total === 0 && !a?.isCustom ? (a?.envOnly ? "server-config" : "no key") : `${r.live}/${Math.max(r.total, r.live)} live${r.cooling ? ` · ${r.cooling} cooling` : ""}`) : "—"}
                                    </span>
                                </div>
                            </button>
                            {idx < STAGES.length - 1 && (
                                <span className="self-center px-0.5 text-t-tertiary max-md:rotate-90 max-md:py-1"><Icon name="arrow" className="size-4 fill-current" /></span>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* inspector — pick any provider in the selected stage; see its live metrics + change the stack */}
            <div className="mt-3 rounded-2xl bg-b-surface1 ring-1 ring-inset ring-s-subtle p-3 dark:bg-shade-04/30">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-caption text-t-tertiary">{stage.label} —</span>
                    <Select className="min-w-[12rem]" value={selectedOpt} options={options}
                        onChange={(o) => setInspect((x) => ({ ...x, [stageKey]: cands[o.id]?.id || "" }))} />
                    {inspectCand && activeCand?.id === inspectCand.id && <Badge variant="success" dot>serving now</Badge>}
                    {inspectCand && (
                        <span className="ml-auto flex items-center gap-2.5">
                            <span className="text-caption text-t-tertiary">{ir?.inStack ? "in the active stack" : "standby"}</span>
                            <Switch checked={!!ir?.inStack} disabled={busy || !ir?.toggleable}
                                onChange={(v: boolean) => {
                                    if (!ir?.toggleable) return;
                                    if (inspectCand.isCustom) onToggleCustom(inspectCand.id.slice(3), v);
                                    else if (inspectCand.provider) onToggleProvider(inspectCand.provider, v);
                                }} />
                        </span>
                    )}
                </div>
                {ir && (
                    <div className="mt-3 grid grid-cols-4 gap-2 max-md:grid-cols-2">
                        <Metric label="Latency" value={ir.latency == null ? "—" : `${Math.round(ir.latency)} ms`} tone={HEX[ir.gstatus]}
                            extra={<SignalBars bars={ir.bars} status={ir.gstatus} />} />
                        <Metric label="Keys live" value={inspectCand?.isCustom ? (ir.inStack ? "ready" : "no key") : `${ir.live}/${ir.total}`} />
                        <Metric label="Cooling" value={fmtNum(ir.cooling)} tone={ir.cooling > 0 ? HEX.yellow : undefined} />
                        <Metric label="Picks" value={fmtNum(ir.picks)} />
                    </div>
                )}
                {inspectCand?.envOnly && (
                    <p className="mt-2 text-caption text-t-tertiary">Server-config provider (env key) — manage it from the deployment, not here.</p>
                )}
                {inspectCand && !inspectCand.isCustom && !inspectCand.envOnly && ir && !ir.toggleable && !ir.inStack && (
                    <p className="mt-2 text-caption text-t-tertiary">Add a key below to put {inspectCand.label} in the stack.</p>
                )}
                {inspectCand && !inspectCand.isCustom && !inspectCand.envOnly && ir && !ir.toggleable && ir.inStack && (
                    <p className="mt-2 text-caption text-t-tertiary">Serving on server-config keys — add a managed key below to control it here.</p>
                )}
            </div>

            <p className="mt-2 text-caption text-t-tertiary">
                Latency is real network RTT to each provider. The healthiest enabled provider serves each stage; disable one to fail over. True end-to-end p95 (turn-detect → STT → LLM → TTS) appears in Voice Analytics once enabled.
            </p>
        </div>
    );
}

function Metric({ label, value, tone, extra }: { label: string; value: string; tone?: string; extra?: ReactNode }) {
    return (
        <div className="rounded-xl bg-b-surface2 ring-1 ring-inset ring-s-subtle px-3 py-2">
            <div className="flex items-center justify-between">
                <span className="text-caption text-t-tertiary">{label}</span>
                {extra}
            </div>
            <div className="mt-0.5 text-body-1 tabular-nums" style={tone ? { color: tone } : undefined}>{value}</div>
        </div>
    );
}
