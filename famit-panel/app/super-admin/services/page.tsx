"use client";

// ============================================================
// Service Control Center — /super-admin/services
// Full superadmin control over the AI providers, on the WORKING legacy key store + custom-provider
// registry (no extra infra needed): manage keys for the built-in providers (Groq / SambaNova /
// Sarvam / OpenRouter), and ADD ANY service of your own (custom OpenAI-compatible STT/LLM/TTS
// endpoint). Compact cards; click one to manage its keys below. White-labeled; dormant-safe.
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Switch from "@/components/Switch";
import Select from "@/components/Select";
import ProviderLogo from "@/components/ProviderLogo";
import {
    getProviderKeys, getProviderKeyStatus, addProviderKey, updateProviderKey, deleteProviderKey,
    getCustomProviders, addCustomProvider, updateCustomProvider, deleteCustomProvider,
    fetchCompanyLogo,
    SERVICE_KINDS,
    type ProviderName, type ProviderKeyRow, type ProviderKeyStatusRow, type CustomProvider, type ServiceKind,
} from "@/lib/api";
import { SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, ghostBtnCls } from "../_shared";
import { useAutoRefresh, n, fmtNum } from "../_obs";
import ActiveStack from "./_active-stack";

type Builtin = { id: ProviderName; name: string; role: string; blurb: string; config: string[] };
const BUILTINS: Builtin[] = [
    { id: "groq", name: "Groq", role: "LLM", blurb: "Primary LLM — fastest. Add keys from several accounts to multiply the pool + fail over.", config: ["llama-4-scout-17b", "temp 0.3"] },
    { id: "sambanova", name: "SambaNova", role: "LLM", blurb: "Final LLM fallback (Llama-3.3-70B) after every Groq key is cooling.", config: ["llama-3.3-70b"] },
    { id: "sarvam", name: "Sarvam", role: "STT", blurb: "Speech-to-text — rotated so one rate-limited key never stalls a call.", config: ["saarika:v2.5"] },
    { id: "openrouter", name: "OpenRouter", role: "LLM", blurb: "Free emergency LLM fallback, used last.", config: ["fallback"] },
];
const ROLE_TONE: Record<string, "info" | "success" | "warning" | "neutral"> = { LLM: "info", STT: "success", TTS: "warning" };
const KIND_TONE = ROLE_TONE;
const inputCls = "input-base h-10 w-full rounded-xl px-3 text-body-2";

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
    return (
        <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
            <div className="text-caption text-t-tertiary">{label}</div>
            <div className="mt-1 text-h5 tabular-nums leading-none" style={tone ? { color: tone } : { color: "var(--text-primary)" }}>{value}</div>
            {sub && <div className="mt-1.5 text-caption text-t-tertiary">{sub}</div>}
        </div>
    );
}

function ServicesInner() {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [keys, setKeys] = useState<Partial<Record<ProviderName, ProviderKeyRow[]>>>({});
    const [status, setStatus] = useState<Partial<Record<ProviderName, ProviderKeyStatusRow[]>>>({});
    const [custom, setCustom] = useState<CustomProvider[]>([]);
    const [open, setOpen] = useState<string | null>(null); // selected card id (provider id or "cp:<id>")
    const [draftKey, setDraftKey] = useState<Record<string, { key: string; label: string }>>({});
    const [showAddService, setShowAddService] = useState(false);
    const [fetchingLogo, setFetchingLogo] = useState(false);
    const [svc, setSvc] = useState<{ name: string; kind: ServiceKind; base_url: string; model: string; key: string; website: string; logo_url: string }>(
        { name: "", kind: "llm", base_url: "", model: "", key: "", website: "", logo_url: "" });
    const kindOptions = useMemo(() => SERVICE_KINDS.map((k, i) => ({ id: i, name: k.label })), []);
    const kindValue = useMemo(() => {
        const i = SERVICE_KINDS.findIndex((k) => k.id === svc.kind);
        return i >= 0 ? kindOptions[i] : kindOptions[0];
    }, [svc.kind, kindOptions]);

    const load = useCallback(() => {
        setLoading(true);
        Promise.all([getProviderKeys(), getProviderKeyStatus(), getCustomProviders()])
            .then(([k, s, c]) => {
                setKeys(k.providers || {});
                setStatus(s.status || {});
                setCustom(c.custom_providers || []);
                setErr("");
            })
            .catch(() => setErr("Couldn't load providers — retry."))
            .finally(() => setLoading(false));
    }, []);
    useEffect(() => { load(); }, [load]);
    const Auto = useAutoRefresh(load, 15000);
    const toast = (m: string) => { setNote(m); setTimeout(() => setNote(""), 2500); };

    // ── KPI rollup across built-ins ──
    const kpi = useMemo(() => {
        let total = 0, live = 0, cooling = 0;
        for (const b of BUILTINS) {
            for (const r of (status[b.id] || [])) {
                total += 1;
                if (r.available) live += 1;
                if (r.cooling) cooling += 1;
            }
        }
        return { total, live, cooling, custom: custom.length };
    }, [status, custom]);

    const statusOf = useCallback((p: ProviderName) => {
        const rows = status[p] || [];
        const live = rows.filter((r) => r.available).length;
        const cooling = rows.filter((r) => r.cooling).length;
        return { count: rows.length, live, cooling };
    }, [status]);

    // ── mutations ──
    const addKey = useCallback(async (p: ProviderName) => {
        const d = draftKey[p]; if (!d || !d.key.trim()) return;
        setBusy(true);
        try { await addProviderKey(p, d.key.trim(), d.label.trim()); toast("Key added — live in rotation."); setDraftKey((x) => ({ ...x, [p]: { key: "", label: "" } })); load(); }
        catch (e) { toast(e instanceof Error ? e.message : "Couldn't add key"); }
        finally { setBusy(false); }
    }, [draftKey, load]);
    const toggleKey = useCallback(async (id: string, enabled: boolean) => {
        setBusy(true); try { await updateProviderKey(id, { enabled }); load(); } finally { setBusy(false); }
    }, [load]);
    // Enable/disable a whole built-in provider in the active stack = flip all its store keys
    // (env-seeded keys are server-config and untouched). The Active Stack card's switch.
    const toggleProviderAll = useCallback(async (p: ProviderName, enabled: boolean) => {
        const rows = keys[p] || [];
        if (rows.length === 0) { toast("No editable keys — add one first."); return; }
        setBusy(true);
        try { await Promise.all(rows.map((r) => updateProviderKey(r.id, { enabled }))); toast(enabled ? "Provider enabled" : "Provider disabled"); load(); }
        catch { toast("Couldn't update provider"); }
        finally { setBusy(false); }
    }, [keys, load]);
    const removeKey = useCallback(async (id: string) => {
        setBusy(true); try { await deleteProviderKey(id); load(); } finally { setBusy(false); }
    }, [load]);
    const addService = useCallback(async () => {
        if (!svc.name.trim() || !svc.base_url.trim()) { toast("Name and base URL are required."); return; }
        setBusy(true);
        try { await addCustomProvider(svc); toast("Service added."); setSvc({ name: "", kind: "llm", base_url: "", model: "", key: "", website: "", logo_url: "" }); setShowAddService(false); load(); }
        catch (e) { toast(e instanceof Error ? e.message : "Couldn't add service"); }
        finally { setBusy(false); }
    }, [svc, load]);
    const fetchLogo = useCallback(async () => {
        if (!svc.website.trim()) { toast("Enter a website first."); return; }
        setFetchingLogo(true);
        try {
            const r = await fetchCompanyLogo(svc.website.trim());
            if (r.logo_url) { setSvc((x) => ({ ...x, logo_url: r.logo_url })); toast("Logo fetched."); }
            else { toast("No logo found for that site."); }
        }
        catch { toast("Couldn't fetch logo."); }
        finally { setFetchingLogo(false); }
    }, [svc.website]);
    const toggleService = useCallback(async (id: string, enabled: boolean) => {
        setBusy(true); try { await updateCustomProvider(id, { enabled }); load(); } finally { setBusy(false); }
    }, [load]);
    const removeService = useCallback(async (id: string) => {
        setBusy(true); try { await deleteCustomProvider(id); load(); } finally { setBusy(false); }
    }, [load]);

    return (
        <Layout title="Service Control Center">
            <SuperAdminHeaderF3 actions={
                <div className="flex items-center gap-2">
                    <Auto />
                    <button onClick={load} className={ghostBtnCls} disabled={loading}>
                        <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />{loading ? "…" : "Refresh"}
                    </button>
                </div>
            } />
            <ErrorBanner msg={err} />
            {note && <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-b-surface3 px-4 py-2 text-caption text-t-secondary"><Icon name="check-circle" className="size-4 fill-current" />{note}</div>}

            {/* KPI strip */}
            <div className="grid grid-cols-4 gap-3 mb-4 max-md:grid-cols-2">
                <Stat label="Keys" value={fmtNum(kpi.total)} sub={`${fmtNum(kpi.live)} in rotation`} />
                <Stat label="Cooling" value={fmtNum(kpi.cooling)} tone={kpi.cooling > 0 ? "#EF9D0E" : undefined} />
                <Stat label="Built-in providers" value={String(BUILTINS.length)} />
                <Stat label="Custom services" value={fmtNum(kpi.custom)} />
            </div>

            {/* ── Active voice stack — live pipeline, latency & control ── */}
            <ActiveStack status={status} custom={custom} busy={busy}
                onToggleProvider={toggleProviderAll} onToggleCustom={toggleService} />

            {/* ── built-in provider cards (compact grid) ── */}
            <div className="grid grid-cols-3 gap-3 max-xl:grid-cols-2 max-md:grid-cols-1">
                {BUILTINS.map((b) => {
                    const st = statusOf(b.id);
                    const tone = st.count === 0 ? "neutral" : st.cooling > 0 ? "warning" : "success";
                    const sel = open === b.id;
                    return (
                        <div key={b.id} className="flex flex-col rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4">
                            <div className="flex items-center gap-2.5">
                                <ProviderLogo provider={b.id} size={30} className="shrink-0" />
                                <span className="text-button text-t-primary">{b.name}</span>
                                <Badge variant={ROLE_TONE[b.role] || "neutral"}>{b.role}</Badge>
                                <Badge variant={tone as "neutral" | "warning" | "success"} dot className="ml-auto">
                                    {st.count === 0 ? "no keys" : `${st.live}/${st.count} live`}
                                </Badge>
                            </div>
                            <p className="mt-2 text-caption text-t-tertiary line-clamp-2 min-h-[2.4em]">{b.blurb}</p>
                            <div className="mt-2 flex flex-wrap gap-1">
                                {b.config.map((c) => <span key={c} className="rounded-full bg-b-surface3 px-2 py-0.5 text-caption text-t-secondary">{c}</span>)}
                            </div>
                            <button onClick={() => setOpen(sel ? null : b.id)}
                                className="mt-3 inline-flex items-center justify-center gap-1.5 rounded-full bg-b-surface3 py-2 text-caption text-t-secondary transition-colors hover:text-t-primary">
                                <Icon name={sel ? "chevron" : "edit"} className={`size-3.5 fill-current ${sel ? "rotate-180" : ""}`} />
                                {sel ? "Hide keys" : `Manage keys (${st.count})`}
                            </button>
                        </div>
                    );
                })}
            </div>

            {/* ── selected built-in: key manager (below the grid) ── */}
            {open && !open.startsWith("cp:") && (() => {
                const p = open as ProviderName;
                const rows = keys[p] || [];
                const stById: Record<string, ProviderKeyStatusRow> = {};
                for (const r of (status[p] || [])) stById[r.id] = r;
                const d = draftKey[p] || { key: "", label: "" };
                return (
                    <div className="mt-3 rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4">
                        <div className="mb-3 flex items-center gap-2">
                            <ProviderLogo provider={p} size={24} />
                            <span className="text-button text-t-primary">{BUILTINS.find((x) => x.id === p)?.name} keys</span>
                        </div>
                        {rows.length === 0 ? (
                            <div className="rounded-2xl bg-b-surface1 px-4 py-4 text-body-2 text-t-tertiary dark:bg-shade-04/30">No keys yet — add one below; it joins the live rotation immediately (encrypted at rest).</div>
                        ) : (
                            <div className="flex flex-col divide-y divide-s-subtle overflow-hidden rounded-2xl ring-1 ring-inset ring-s-subtle">
                                {rows.map((k) => {
                                    const s = stById[k.id];
                                    return (
                                        <div key={k.id} className="flex items-center gap-3 px-3.5 py-2.5">
                                            <span className="font-mono text-caption text-t-secondary">{k.masked || "••••"}</span>
                                            {k.label && <span className="text-caption text-t-tertiary">{k.label}</span>}
                                            {s?.cooling ? <Badge variant="warning" dot>cooling {Math.round(n(s.cooldown_remaining_s))}s</Badge>
                                                : <Badge variant={k.enabled ? "success" : "neutral"} dot={k.enabled}>{k.enabled ? "live" : "disabled"}</Badge>}
                                            {s && n(s.pick_count) > 0 && <span className="text-caption text-t-tertiary tabular-nums">{fmtNum(n(s.pick_count))} picks</span>}
                                            <span className="ml-auto flex items-center gap-3">
                                                <Switch checked={k.enabled} onChange={(v: boolean) => toggleKey(k.id, v)} />
                                                <button disabled={busy} onClick={() => removeKey(k.id)} className="grid size-8 place-items-center rounded-full fill-t-tertiary hover:fill-primary-03 hover:bg-primary-03/10"><Icon name="trash" className="size-4 fill-inherit" /></button>
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                        <div className="mt-3 flex items-center gap-2 flex-wrap">
                            <input type="password" value={d.key} placeholder={`Add a ${BUILTINS.find((x) => x.id === p)?.name} key…`}
                                className={`${inputCls} flex-1 min-w-[12rem]`} onChange={(e) => setDraftKey((x) => ({ ...x, [p]: { ...d, key: e.target.value } }))} />
                            <input type="text" value={d.label} placeholder="Label (optional)" className={`${inputCls} w-40`} onChange={(e) => setDraftKey((x) => ({ ...x, [p]: { ...d, label: e.target.value } }))} />
                            <button disabled={busy || !d.key.trim()} onClick={() => addKey(p)} className="inline-flex h-10 items-center rounded-full bg-primary-01 px-5 text-button text-white disabled:opacity-50">Add key</button>
                        </div>
                    </div>
                );
            })()}

            {/* ── custom services ("add any service") ── */}
            <div className="mt-5 flex items-center gap-2">
                <span className="text-h6 text-t-primary">Your services</span>
                <span className="text-caption text-t-tertiary">any AI service — LLM / STT / TTS / embeddings / rerank / telephony / webhook (OpenAI-compatible)</span>
                <button onClick={() => setShowAddService((s) => !s)} className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-primary-01 px-4 py-2 text-button text-white">
                    <Icon name="plus" className="size-4 fill-current" />Add a service
                </button>
            </div>

            {showAddService && (
                <div className="mt-3 rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4">
                    <div className="grid grid-cols-2 gap-2 max-md:grid-cols-1">
                        <input className={inputCls} placeholder="Name (e.g. My OpenAI)" value={svc.name} onChange={(e) => setSvc({ ...svc, name: e.target.value })} />
                        <Select className="w-full" classButton="!h-10" placeholder="Category"
                            value={kindValue} options={kindOptions}
                            onChange={(o) => setSvc({ ...svc, kind: SERVICE_KINDS[o.id].id })} />
                        <input className={inputCls} placeholder="Base URL (https://…/v1)" value={svc.base_url} onChange={(e) => setSvc({ ...svc, base_url: e.target.value })} />
                        <input className={inputCls} placeholder="Model id (optional)" value={svc.model} onChange={(e) => setSvc({ ...svc, model: e.target.value })} />
                        <input className={`${inputCls} col-span-2 max-md:col-span-1`} type="password" placeholder="API key" value={svc.key} onChange={(e) => setSvc({ ...svc, key: e.target.value })} />
                        <div className="col-span-2 max-md:col-span-1 flex items-center gap-2">
                            <input className={`${inputCls} flex-1`} placeholder="Website (for logo)" value={svc.website} onChange={(e) => setSvc({ ...svc, website: e.target.value })} />
                            <button type="button" disabled={fetchingLogo || !svc.website.trim()} onClick={fetchLogo} className={ghostBtnCls}>
                                <Icon name={fetchingLogo ? "clock" : "magic-pencil"} className={`size-4 fill-current ${fetchingLogo ? "animate-spin" : ""}`} />{fetchingLogo ? "…" : "Fetch logo"}
                            </button>
                            {svc.logo_url && (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={svc.logo_url} alt="logo preview" className="size-8 shrink-0 rounded-lg object-contain ring-1 ring-inset ring-s-subtle" />
                            )}
                        </div>
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                        <button disabled={busy} onClick={addService} className="inline-flex h-10 items-center rounded-full bg-primary-01 px-5 text-button text-white disabled:opacity-50">Add service</button>
                        <button onClick={() => setShowAddService(false)} className={ghostBtnCls}>Cancel</button>
                        <span className="text-caption text-t-tertiary">Stored encrypted, isolated from the platform pool. Routing live calls through it is per-campaign (Advanced).</span>
                    </div>
                </div>
            )}

            <div className="mt-3 grid grid-cols-3 gap-3 max-xl:grid-cols-2 max-md:grid-cols-1">
                {custom.length === 0 && !showAddService && (
                    <div className="col-span-full rounded-3xl border border-dashed border-s-stroke2 px-4 py-8 text-center text-body-2 text-t-tertiary">No custom services yet — click “Add a service” to register any AI service endpoint.</div>
                )}
                {custom.map((c) => (
                    <div key={c.id} className="flex flex-col rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4">
                        <div className="flex items-center gap-2.5">
                            {c.logo_url ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img src={c.logo_url} alt={c.name} className="size-[30px] shrink-0 rounded-lg object-contain" />
                            ) : (
                                <ProviderLogo provider={c.name} size={30} className="shrink-0" />
                            )}
                            <span className="truncate text-button text-t-primary">{c.name}</span>
                            <Badge variant={KIND_TONE[c.kind.toUpperCase()] || "neutral"}>{c.kind.toUpperCase()}</Badge>
                            <Badge variant={c.available ? "success" : "neutral"} dot={c.available} className="ml-auto">{c.available ? "ready" : "no key"}</Badge>
                        </div>
                        <div className="mt-2 truncate text-caption text-t-tertiary" title={c.base_url}>{c.base_url}</div>
                        <div className="text-caption text-t-tertiary">model: <span className="text-t-secondary">{c.model || "—"}</span> · key {c.masked || "—"}</div>
                        <div className="mt-3 flex items-center gap-3">
                            <Switch checked={c.enabled} onChange={(v: boolean) => toggleService(c.id, v)} />
                            <span className="text-caption text-t-tertiary">{c.enabled ? "enabled" : "disabled"}</span>
                            <button disabled={busy} onClick={() => removeService(c.id)} className="ml-auto grid size-8 place-items-center rounded-full fill-t-tertiary hover:fill-primary-03 hover:bg-primary-03/10"><Icon name="trash" className="size-4 fill-inherit" /></button>
                        </div>
                    </div>
                ))}
            </div>
        </Layout>
    );
}

export default function ServicesPage() {
    return <SuperAdminGuard><ServicesInner /></SuperAdminGuard>;
}
