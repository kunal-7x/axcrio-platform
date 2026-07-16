"use client";

// ============================================================
// Groq Token Budget card (Service Control Center).
//
// The dead-air-on-quota glitch: a Groq key hit its ~100k-tokens/DAY free-tier wall mid-campaign and
// every retry 429'd. This panel lets super-admin (1) add MULTIPLE Groq keys as fallback and (2) see
// each key's LIVE remaining daily token budget. The agent worker writes today's per-key usage after
// each call and PROACTIVELY rotates OFF a key whose remaining budget drops below the low threshold —
// so the next call rides a healthy key BEFORE the wall, not after. Raw keys never leave the server.
// ============================================================

import { useCallback, useEffect, useState } from "react";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import { getGroqBudget, saveGroqBudget, type GroqBudgetView, type GroqBudgetKey } from "@/lib/api";

const fmt = (n: number) => (n || 0).toLocaleString("en-IN");
const STATUS_TONE: Record<string, "success" | "warning" | "neutral"> = {
    healthy: "success", low: "warning", exhausted: "neutral",
};
const inputCls = "input-base h-9 rounded-xl px-3 text-body-2";

export default function GroqBudgetCard() {
    const [view, setView] = useState<GroqBudgetView>({ keys: [], summary: {} });
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [adding, setAdding] = useState(false);
    const [draft, setDraft] = useState({ key: "", label: "", tpd_limit: "" });

    const load = useCallback(async () => {
        setLoading(true);
        try {
            setView(await getGroqBudget());
            setErr("");
        } catch {
            setErr("Could not load Groq budget");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { void load(); }, [load]);

    const mutate = useCallback(async (action: Parameters<typeof saveGroqBudget>[0]) => {
        setBusy(true);
        try {
            setView(await saveGroqBudget(action));
            setErr("");
            return true;
        } catch {
            setErr("Save failed");
            return false;
        } finally {
            setBusy(false);
        }
    }, []);

    const s = view.summary || {};
    const keys = view.keys || [];

    const onAdd = async () => {
        const key = draft.key.trim();
        if (key.length < 8) { setErr("Paste a valid Groq key (gsk_…)"); return; }
        const ok = await mutate({
            add_key: {
                key,
                label: draft.label.trim() || undefined,
                tpd_limit: draft.tpd_limit ? Math.max(1000, parseInt(draft.tpd_limit, 10) || 0) : undefined,
            },
        });
        if (ok) { setDraft({ key: "", label: "", tpd_limit: "" }); setAdding(false); }
    };

    return (
        <div className="mt-4 rounded-3xl bg-b-surface1 ring-1 ring-s-subtle ring-inset p-5 dark:bg-shade-04/30">
            <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
                <div className="flex items-center gap-2.5">
                    <span className="grid place-items-center size-9 rounded-2xl bg-b-surface3 text-t-secondary">
                        <Icon name="wallet" className="size-4 fill-current" />
                    </span>
                    <div className="leading-tight">
                        <div className="text-button text-t-primary">LLM token budget · Groq</div>
                        <div className="text-caption text-t-tertiary">
                            Multi-key fallback + proactive rotation before the daily-token wall
                        </div>
                    </div>
                </div>
                <button onClick={load} disabled={loading || busy}
                    className="inline-flex items-center gap-1.5 h-9 px-3 rounded-xl bg-b-surface2 ring-1 ring-s-subtle text-button text-t-secondary hover:text-t-primary">
                    <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                    {loading ? "…" : "Validate now"}
                </button>
            </div>

            {err && (
                <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-primary-05/10 px-3 py-1.5 text-caption text-primary-05">
                    <Icon name="info" className="size-3.5 fill-current" />{err}
                </div>
            )}

            {/* summary strip */}
            <div className="grid grid-cols-3 gap-3 mb-4 max-md:grid-cols-1">
                <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3.5">
                    <div className="text-caption text-t-tertiary">Tokens left today</div>
                    <div className="mt-1 text-h5 tabular-nums leading-none text-t-primary">
                        {fmt(s.total_remaining || 0)}
                    </div>
                    <div className="mt-1 text-caption text-t-tertiary">across {fmt(s.key_count || 0)} key(s)</div>
                </div>
                <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3.5">
                    <div className="text-caption text-t-tertiary">Healthy keys</div>
                    <div className="mt-1 text-h5 tabular-nums leading-none"
                        style={{ color: s.all_low ? "#FF6A55" : "var(--text-primary)" }}>
                        {fmt(s.healthy_keys || 0)} / {fmt(s.key_count || 0)}
                    </div>
                    <div className="mt-1 text-caption text-t-tertiary">
                        {s.all_low ? "All low — add a key / upgrade tier" : "ready to rotate"}
                    </div>
                </div>
                <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3.5">
                    <div className="text-caption text-t-tertiary">Per-key daily limit</div>
                    <div className="mt-1 text-h5 tabular-nums leading-none text-t-primary">{fmt(s.tpd_limit_default || 0)}</div>
                    <div className="mt-1 text-caption text-t-tertiary">rotate under {fmt(s.low_threshold || 0)} left</div>
                </div>
            </div>

            {/* key list */}
            <div className="divide-y divide-s-subtle rounded-2xl overflow-hidden ring-1 ring-s-subtle">
                {keys.length === 0 && !loading && (
                    <div className="bg-b-surface2 px-4 py-4 text-caption text-t-tertiary">
                        No Groq key found. Keys from the .env (GROQ_API_KEY / _2…) appear here automatically;
                        add more below as fallback.
                    </div>
                )}
                {keys.map((k) => (
                    <KeyRow key={k.fingerprint} k={k} busy={busy}
                        onRemove={() => mutate({ remove_fingerprint: k.fingerprint })}
                        onLimit={(lim) => mutate({ update_key: { fingerprint: k.fingerprint, tpd_limit: lim } })} />
                ))}
            </div>

            {/* add key + settings */}
            <div className="mt-3 flex items-center justify-between gap-3 flex-wrap">
                {!adding ? (
                    <button onClick={() => setAdding(true)}
                        className="inline-flex items-center gap-1.5 h-9 px-3 rounded-xl bg-b-surface2 ring-1 ring-s-subtle text-button text-t-secondary hover:text-t-primary">
                        <Icon name="plus" className="size-4 fill-current" /> Add Groq key
                    </button>
                ) : (
                    <div className="flex items-center gap-2 flex-wrap">
                        <input className={`${inputCls} w-64`} placeholder="gsk_… (paste new key)" value={draft.key}
                            onChange={(e) => setDraft({ ...draft, key: e.target.value })} />
                        <input className={`${inputCls} w-32`} placeholder="Label" value={draft.label}
                            onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
                        <input className={`${inputCls} w-32`} placeholder="Limit/day" inputMode="numeric" value={draft.tpd_limit}
                            onChange={(e) => setDraft({ ...draft, tpd_limit: e.target.value.replace(/[^0-9]/g, "") })} />
                        <button onClick={onAdd} disabled={busy}
                            className="h-9 px-3 rounded-xl bg-primary-01 text-button text-white disabled:opacity-50">Add</button>
                        <button onClick={() => { setAdding(false); setDraft({ key: "", label: "", tpd_limit: "" }); }}
                            className="h-9 px-3 rounded-xl bg-b-surface2 ring-1 ring-s-subtle text-button text-t-secondary">Cancel</button>
                    </div>
                )}
                <DefaultsEditor s={s} busy={busy}
                    onSave={(tpd, low) => mutate({ tpd_limit_default: tpd, low_threshold: low })} />
            </div>
        </div>
    );
}

function KeyRow({ k, busy, onRemove, onLimit }: {
    k: GroqBudgetKey; busy: boolean; onRemove: () => void; onLimit: (lim: number) => void;
}) {
    const [editing, setEditing] = useState(false);
    const [lim, setLim] = useState(String(k.tpd_limit));
    const pct = k.tpd_limit > 0 ? Math.min(100, Math.round((k.used_today / k.tpd_limit) * 100)) : 0;
    const barColor = k.status === "exhausted" ? "#FF6A55" : k.status === "low" ? "#EF9D0E" : "#00A656";

    return (
        <div className="bg-b-surface2 px-4 py-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2.5 min-w-0">
                    <Badge variant={STATUS_TONE[k.status] || "neutral"}>{k.status}</Badge>
                    <span className="font-mono text-caption text-t-secondary">{k.masked || "••••"}</span>
                    <span className="text-caption text-t-tertiary truncate">
                        {k.label}{k.source === "env" ? " · .env" : ""}
                    </span>
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-caption text-t-tertiary tabular-nums">
                        {fmt(k.used_today)} / {fmt(k.tpd_limit)} used · {fmt(k.remaining)} left · {fmt(k.calls_today)} calls
                    </span>
                    {editing ? (
                        <span className="flex items-center gap-1.5">
                            <input className="input-base h-8 w-28 rounded-lg px-2 text-caption" inputMode="numeric"
                                value={lim} onChange={(e) => setLim(e.target.value.replace(/[^0-9]/g, ""))} />
                            <button disabled={busy} onClick={() => { onLimit(Math.max(1000, parseInt(lim, 10) || 0)); setEditing(false); }}
                                className="h-8 px-2.5 rounded-lg bg-primary-01 text-caption text-white">Save</button>
                        </span>
                    ) : (
                        <button onClick={() => { setLim(String(k.tpd_limit)); setEditing(true); }}
                            className="text-caption text-t-tertiary hover:text-t-primary">Limit</button>
                    )}
                    {k.source === "store" && (
                        <button onClick={onRemove} disabled={busy}
                            className="grid place-items-center size-7 rounded-lg hover:bg-primary-05/10 text-t-tertiary hover:text-primary-05">
                            <Icon name="trash" className="size-4 fill-current" />
                        </button>
                    )}
                </div>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-b-surface3 overflow-hidden">
                <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: barColor }} />
            </div>
        </div>
    );
}

function DefaultsEditor({ s, busy, onSave }: {
    s: Partial<{ tpd_limit_default: number; low_threshold: number }>;
    busy: boolean; onSave: (tpd: number, low: number) => void;
}) {
    const [open, setOpen] = useState(false);
    const [tpd, setTpd] = useState(String(s.tpd_limit_default ?? 100000));
    const [low, setLow] = useState(String(s.low_threshold ?? 10000));
    useEffect(() => {
        setTpd(String(s.tpd_limit_default ?? 100000));
        setLow(String(s.low_threshold ?? 10000));
    }, [s.tpd_limit_default, s.low_threshold]);

    if (!open) {
        return (
            <button onClick={() => setOpen(true)}
                className="inline-flex items-center gap-1.5 text-caption text-t-tertiary hover:text-t-primary">
                <Icon name="filters" className="size-3.5 fill-current" /> Limits
            </button>
        );
    }
    return (
        <div className="flex items-center gap-2 flex-wrap">
            <label className="text-caption text-t-tertiary">Default/day</label>
            <input className="input-base h-9 w-28 rounded-xl px-2 text-body-2" inputMode="numeric"
                value={tpd} onChange={(e) => setTpd(e.target.value.replace(/[^0-9]/g, ""))} />
            <label className="text-caption text-t-tertiary">Rotate under</label>
            <input className="input-base h-9 w-24 rounded-xl px-2 text-body-2" inputMode="numeric"
                value={low} onChange={(e) => setLow(e.target.value.replace(/[^0-9]/g, ""))} />
            <button disabled={busy}
                onClick={() => { onSave(Math.max(1000, parseInt(tpd, 10) || 0), Math.max(0, parseInt(low, 10) || 0)); setOpen(false); }}
                className="h-9 px-3 rounded-xl bg-primary-01 text-button text-white disabled:opacity-50">Save</button>
        </div>
    );
}
