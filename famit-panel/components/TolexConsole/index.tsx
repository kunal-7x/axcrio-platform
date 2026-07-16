"use client";

// ============================================================================
// TolexConsole — shared agent-tooling console body, used by BOTH the super-admin Tolex page
// (platform scope) and the tenant "Agent Tools" page in Grow (tenant scope). The ONLY difference is
// the `api` object passed in (admin /admin/tolex/* vs tenant /tolex/*), so the two surfaces can never
// drift. Renders no page chrome (Layout/header) — the page provides that.
// ============================================================================

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Switch from "@/components/Switch";
import Select from "@/components/Select";
import {
    getCampaigns,
    type TolexApi, type TolexTool, type TolexToolGrant, type TolexMode, type TolexCriticality, type TolexOp, type Campaign,
} from "@/lib/api";

const ghostBtnCls = "inline-flex items-center gap-1.5 h-10 px-4 rounded-full text-button text-t-secondary ring-1 ring-inset ring-s-subtle hover:text-t-primary transition-colors disabled:opacity-50";
const fmtNum = (n: number) => { try { return new Intl.NumberFormat().format(n); } catch { return String(n); } };
function fmtTs(iso?: string): string {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); }
    catch { return iso; }
}

const CATS: { key: string; label: string }[] = [
    { key: "info", label: "Information" },
    { key: "data", label: "Lead data" },
    { key: "scheduling", label: "Scheduling" },
    { key: "comms", label: "Communication" },
    { key: "handoff", label: "Handoff" },
    { key: "transaction", label: "Transactions" },
];
const CRIT_HEX: Record<TolexCriticality, string> = { normal: "#8A8A8A", sensitive: "#EF9D0E", critical: "#FF6A55" };
const MODE_OPTS: { id: number; name: string; value: TolexMode }[] = [
    { id: 0, name: "Allow", value: "allow" },
    { id: 1, name: "Confirm first", value: "confirm" },
    { id: 2, name: "Require PIN", value: "pin" },
    { id: 3, name: "Human approval", value: "approve" },
];
const defaultMode = (c: TolexCriticality): TolexMode => (c === "critical" ? "approve" : c === "sensitive" ? "confirm" : "allow");

function CritChip({ c }: { c: TolexCriticality }) {
    return (
        <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-caption capitalize"
            style={{ color: CRIT_HEX[c], background: `${CRIT_HEX[c]}1a` }}>
            <span className="size-1.5 rounded-full" style={{ background: CRIT_HEX[c] }} />{c}
        </span>
    );
}
function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
    return (
        <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4">
            <div className="text-caption text-t-tertiary">{label}</div>
            <div className="mt-1 text-h5 tabular-nums leading-none" style={tone ? { color: tone } : { color: "var(--text-primary)" }}>{value}</div>
            {sub && <div className="mt-1.5 text-caption text-t-tertiary">{sub}</div>}
        </div>
    );
}

export default function TolexConsole({ api, runtimeNote, scopeLabel = "Default profile" }: {
    api: TolexApi;
    runtimeNote?: ReactNode;       // shown when the agent runtime is off (page-specific wording)
    scopeLabel?: string;           // label for the no-campaign scope (default profile)
}) {
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [catalog, setCatalog] = useState<TolexTool[]>([]);
    const [runtimeOn, setRuntimeOn] = useState(false);
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [cid, setCid] = useState("");
    const [enabled, setEnabled] = useState(false);
    const [tools, setTools] = useState<Record<string, TolexToolGrant>>({});
    const [inherited, setInherited] = useState(false);
    const [ops, setOps] = useState<TolexOp[]>([]);
    const [dirty, setDirty] = useState(false);

    const toast = (m: string) => { setNote(m); setTimeout(() => setNote(""), 2500); };

    useEffect(() => {
        Promise.all([api.getCatalog(), getCampaigns()])
            .then(([c, cs]) => { setCatalog(c.catalog || []); setRuntimeOn(!!c.runtime_enabled); setCampaigns(cs.campaigns || []); })
            .catch(() => setErr("Couldn't load agent tools — retry."));
    }, [api]);

    const loadGrants = useCallback((forCid: string) => {
        setLoading(true);
        Promise.all([api.getGrants(forCid), api.getOps(forCid, 50)])
            .then(([g, o]) => {
                setEnabled(!!g.grants.enabled); setTools(g.grants.tools || {}); setInherited(!!g.grants.inherited);
                setOps(o.ops || []); setDirty(false); setErr("");
            })
            .catch(() => setErr("Couldn't load grants — retry."))
            .finally(() => setLoading(false));
    }, [api]);
    useEffect(() => { loadGrants(cid); }, [cid, loadGrants]);

    const modeOf = (key: string): TolexMode => (tools[key]?.mode as TolexMode) || "off";
    const isGranted = (key: string) => modeOf(key) !== "off";
    const setToolMode = (key: string, mode: TolexMode) => { setTools((p) => ({ ...p, [key]: { ...(p[key] || {}), mode } })); setDirty(true); };
    const setToolField = (key: string, patch: Partial<TolexToolGrant>) => { setTools((p) => ({ ...p, [key]: { ...(p[key] || { mode: "allow" }), ...patch } })); setDirty(true); };
    const toggleTool = (t: TolexTool, on: boolean) => setToolMode(t.key, on ? defaultMode(t.criticality) : "off");

    const save = useCallback(async () => {
        setBusy(true);
        try {
            const res = await api.saveGrants({ campaign_id: cid, enabled, tools });
            setEnabled(!!res.grants.enabled); setTools(res.grants.tools || {}); setInherited(false); setDirty(false);
            toast("Saved — live for new calls.");
        } catch (e) { toast(e instanceof Error ? e.message : "Couldn't save"); }
        finally { setBusy(false); }
    }, [api, cid, enabled, tools]);

    const enableRecommended = useCallback(async () => {
        setBusy(true);
        try {
            const res = await api.enableRecommended(cid);
            setEnabled(!!res.grants.enabled); setTools(res.grants.tools || {}); setInherited(false); setDirty(false);
            toast("Recommended profile enabled.");
            api.getOps(cid, 50).then((o) => setOps(o.ops || [])).catch(() => {});
        } catch (e) { toast(e instanceof Error ? e.message : "Couldn't enable"); }
        finally { setBusy(false); }
    }, [api, cid]);

    const kpi = useMemo(() => {
        let on = 0, crit = 0;
        for (const t of catalog) if (isGranted(t.key)) { on += 1; if (t.criticality === "critical") crit += 1; }
        return { on, total: catalog.length, crit };
    }, [catalog, tools]); // eslint-disable-line react-hooks/exhaustive-deps

    const campOpts = useMemo(
        () => [{ id: 0, name: scopeLabel, value: "" }, ...campaigns.map((c, i) => ({ id: i + 1, name: c.name || c.id, value: c.id }))],
        [campaigns, scopeLabel]);
    const campValue = campOpts.find((o) => o.value === cid) || campOpts[0];

    return (
        <>
            <div className="mb-4 flex items-center justify-end gap-2">
                {note && <span className="mr-auto inline-flex items-center gap-2 rounded-full bg-b-surface3 px-4 py-2 text-caption text-t-secondary"><Icon name="check-circle" className="size-4 fill-current" />{note}</span>}
                <button onClick={() => loadGrants(cid)} className={ghostBtnCls} disabled={loading}>
                    <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />{loading ? "…" : "Refresh"}
                </button>
            </div>
            {err && <div className="mb-4 rounded-2xl bg-primary-03/10 px-4 py-3 text-body-2 text-primary-03">{err}</div>}

            {!runtimeOn && (runtimeNote ?? (
                <div className="mb-4 flex items-center gap-2 rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-3.5 text-body-2 text-t-secondary">
                    <Icon name="info" className="size-4 fill-t-secondary shrink-0" />
                    Configure capabilities now — they apply to your calls once the agent tooling runtime is switched on.
                </div>
            ))}

            {/* scope + master controls */}
            <div className="rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-4 mb-4">
                <div className="flex items-center gap-3 flex-wrap">
                    <span className="grid size-7 place-items-center rounded-full bg-primary-01/12"><Icon name="cube" className="size-4 fill-primary-01" /></span>
                    <span className="text-button text-t-primary">Capabilities for</span>
                    <Select className="min-w-[14rem]" classButton="!h-10" value={campValue} options={campOpts}
                        onChange={(o) => setCid(campOpts[o.id]?.value ?? "")} />
                    <span className="ml-auto flex items-center gap-2.5">
                        <span className="text-caption text-t-tertiary">Agent tooling</span>
                        <Switch checked={enabled} disabled={busy} onChange={(v) => { setEnabled(v); setDirty(true); }} />
                    </span>
                </div>
                {inherited && cid && (
                    <p className="mt-2 text-caption text-t-tertiary">This campaign inherits the {scopeLabel} — edits here create a campaign-specific override on save.</p>
                )}
                <div className="mt-3 flex items-center gap-2 flex-wrap">
                    <button disabled={busy} onClick={enableRecommended} className="inline-flex h-10 items-center gap-1.5 rounded-full bg-primary-01 px-4 text-button text-white disabled:opacity-50">
                        <Icon name="magic-pencil" className="size-4 fill-current" />Enable recommended
                    </button>
                    <span className="text-caption text-t-tertiary">One click: a safe profile — everyday actions allowed, messages confirm first, money needs approval.</span>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-4 max-md:grid-cols-1">
                <Stat label="Capabilities on" value={`${fmtNum(kpi.on)}/${fmtNum(kpi.total)}`} sub={enabled ? "agent tooling enabled" : "agent tooling off"} tone={enabled ? "#00A656" : undefined} />
                <Stat label="Critical gated" value={fmtNum(kpi.crit)} sub="money/handoff need approval" tone={kpi.crit > 0 ? "#EF9D0E" : undefined} />
                <Stat label="Runtime" value={runtimeOn ? "on" : "off"} sub={runtimeOn ? "calls can use tools" : "not switched on yet"} tone={runtimeOn ? "#00A656" : "#FF6A55"} />
            </div>

            <div className="flex flex-col gap-4">
                {CATS.map((cat) => {
                    const items = catalog.filter((t) => t.category === cat.key);
                    if (!items.length) return null;
                    return (
                        <div key={cat.key}>
                            <div className="mb-2 text-caption uppercase tracking-wide text-t-tertiary">{cat.label}</div>
                            <div className="grid grid-cols-2 gap-3 max-lg:grid-cols-1">
                                {items.map((t) => {
                                    const granted = isGranted(t.key);
                                    const g = tools[t.key] || { mode: "off" as TolexMode };
                                    const modeOpt = MODE_OPTS.find((m) => m.value === g.mode) || MODE_OPTS[0];
                                    return (
                                        <div key={t.key} className={`rounded-3xl ring-1 ring-inset p-4 transition-colors ${granted ? "bg-b-surface2 ring-s-subtle" : "bg-b-surface1 ring-s-subtle dark:bg-shade-04/30"}`}>
                                            <div className="flex items-start gap-2.5">
                                                <div className="min-w-0 flex-1">
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        <span className="text-button text-t-primary">{t.name}</span>
                                                        <CritChip c={t.criticality} />
                                                    </div>
                                                    <p className="mt-1 text-caption text-t-tertiary">{t.description}</p>
                                                </div>
                                                <Switch checked={granted} disabled={busy} onChange={(v) => toggleTool(t, v)} />
                                            </div>
                                            {granted && (
                                                <div className="mt-3 flex items-center gap-2 flex-wrap">
                                                    <span className="text-caption text-t-tertiary">Policy</span>
                                                    <Select className="min-w-[11rem]" classButton="!h-9" value={modeOpt} options={MODE_OPTS}
                                                        onChange={(o) => setToolMode(t.key, MODE_OPTS[o.id]?.value || "allow")} />
                                                    {t.criticality === "critical" && (
                                                        <span className="inline-flex items-center gap-1.5">
                                                            <span className="text-caption text-t-tertiary">Max ₹</span>
                                                            <input type="number" min={0} value={g.max_amount ?? 0}
                                                                onChange={(e) => setToolField(t.key, { max_amount: Number(e.target.value) || 0 })}
                                                                className="input-base h-9 w-28 rounded-xl px-3 text-body-2" placeholder="0 = no cap" />
                                                        </span>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })}
            </div>

            <div className="mt-6">
                <div className="mb-2 flex items-center gap-2">
                    <span className="text-h6 text-t-primary">Recent operations</span>
                    <span className="text-caption text-t-tertiary">what the agent actually did under policy</span>
                </div>
                <div className="rounded-3xl bg-b-surface2 ring-1 ring-inset ring-s-subtle overflow-hidden">
                    {ops.length === 0 ? (
                        <div className="px-4 py-8 text-center text-body-2 text-t-tertiary">No operations yet — they appear here as the agent uses its tools on calls.</div>
                    ) : (
                        <div className="flex flex-col divide-y divide-s-subtle">
                            {ops.map((o) => (
                                <div key={o.id} className="flex items-center gap-3 px-4 py-2.5 flex-wrap sm:flex-nowrap">
                                    <span className="text-body-2 text-t-primary truncate min-w-0 flex-1">{o.name || o.tool}</span>
                                    {o.criticality && <CritChip c={o.criticality} />}
                                    <Badge variant={o.result === "executed" ? "success" : o.result === "queued" ? "warning" : "neutral"} dot>{o.result || o.action}</Badge>
                                    {o.phone && <span className="text-caption text-t-tertiary truncate hidden sm:inline">{o.phone}</span>}
                                    <span className="text-caption text-t-tertiary tabular-nums">{fmtTs(o.ts)}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {dirty && (
                <div className="sticky bottom-4 mt-4 flex items-center gap-3 rounded-full bg-b-surface3 ring-1 ring-inset ring-s-subtle px-4 py-2.5 shadow-depth w-fit ml-auto">
                    <span className="text-caption text-t-secondary">Unsaved changes</span>
                    <button disabled={busy} onClick={save} className="inline-flex h-9 items-center rounded-full bg-primary-01 px-5 text-button text-white disabled:opacity-50">Save</button>
                    <button disabled={busy} onClick={() => loadGrants(cid)} className={ghostBtnCls}>Discard</button>
                </div>
            )}
        </>
    );
}
