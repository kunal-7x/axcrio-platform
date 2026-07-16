"use client";

// ============================================================
// Verticals — /super-admin/verticals
//
// Browse + (no-deploy) extend the multi-vertical / persona / language catalogue that
// the voice agent's `verticals/` package exposes. The agent reads it only when
// FEATURE_VERTICALS=1; a campaign opts in via fields.vertical/sub_option/persona/language.
//
// Overrides are deep-merged over the static registry on the box (VAR/verticals_overrides.json),
// same idiom as Voice Defaults' tier_overrides.json. Super-admin gated; dormant-safe (if the
// /admin/verticals-config route isn't wired yet, the browser still renders from the live/static
// catalogue and saving reports it clearly).
// ============================================================

import { useCallback, useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import {
    getVerticalsConfig, saveVerticalsConfig, type VerticalsConfigView,
} from "@/lib/verticals";
import { SuperAdminGuard, SuperAdminHeaderF3, ErrorBanner, ghostBtnCls } from "../_shared";

const EMPTY: VerticalsConfigView = {
    overrides: {},
    effective: { version: "", fields: [], personas: [], languages: [] },
};

function Badge({ ok, children }: { ok: boolean; children: React.ReactNode }) {
    return (
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-caption font-medium ${
            ok ? "bg-[#00A656]/15 text-[#00A656]" : "bg-b-surface3 text-t-tertiary"}`}>
            {children}
        </span>
    );
}

function VerticalsInner() {
    const [cfg, setCfg] = useState<VerticalsConfigView>(EMPTY);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [note, setNote] = useState("");
    const [draft, setDraft] = useState("{}");

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const c = await getVerticalsConfig();
            setCfg(c);
            setDraft(JSON.stringify(c.overrides ?? {}, null, 2));
            setErr("");
        } catch { setErr("Could not load verticals catalogue"); }
        finally { setLoading(false); }
    }, []);
    useEffect(() => { void load(); }, [load]);

    const cat = cfg.effective;

    const saveOverrides = useCallback(async () => {
        let partial: Record<string, unknown>;
        try { partial = JSON.parse(draft || "{}"); }
        catch { setErr("Overrides is not valid JSON"); return; }
        setBusy(true);
        try {
            const c = await saveVerticalsConfig(partial);
            setCfg(c);
            setDraft(JSON.stringify(c.overrides ?? {}, null, 2));
            setErr(""); setNote("Overrides saved");
            window.setTimeout(() => setNote(""), 2500);
        } catch (e) {
            setErr(e instanceof Error && /404/.test(e.message)
                ? "Backend route /admin/verticals-config is not wired yet — overrides can't be saved from here. Edit VAR/verticals_overrides.json on the box, or add the endpoint."
                : "Save failed");
        } finally { setBusy(false); }
    }, [draft]);

    return (
        <Layout title="Verticals">
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

            {/* enablement */}
            <div className="mb-4 flex items-start gap-2 p-3.5 rounded-2xl bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04/30">
                <Icon name="info" className="size-4 fill-t-tertiary shrink-0 mt-0.5" />
                <p className="text-caption text-t-secondary leading-relaxed">
                    One agent, any industry. Enable with <code className="text-t-primary">FEATURE_VERTICALS=1</code> on the
                    voice service; each campaign opts in via <code className="text-t-primary">fields.vertical / sub_option / persona / language</code>{" "}
                    (set from the campaign form). Default-off &amp; byte-identical when off. Catalogue v{cat.version || "—"} ·{" "}
                    {cat.fields.length} fields · {cat.personas.length} personas · {cat.languages.length} languages.
                </p>
            </div>

            {/* FIELDS */}
            <div className="mb-3 text-button text-t-primary">Fields &amp; use-cases</div>
            <div className="grid grid-cols-2 gap-3 max-lg:grid-cols-1 mb-6">
                {cat.fields.map((f) => (
                    <div key={f.key} className="rounded-3xl bg-b-surface1 ring-1 ring-s-subtle ring-inset p-5 dark:bg-shade-04/30">
                        <div className="flex items-center justify-between mb-1">
                            <div className="text-button text-t-primary">{f.label}</div>
                            <span className="text-caption text-t-tertiary font-mono">{f.key}</span>
                        </div>
                        <div className="text-caption text-t-tertiary mb-3">
                            tone: {f.tone} · persona: {f.default_persona ?? "—"} · lang: {f.default_languages.join("/")}
                        </div>
                        <ul className="space-y-1.5">
                            {f.sub_options.map((s) => (
                                <li key={s.key} className="text-caption text-t-secondary">
                                    <span className="text-t-primary">{s.label}</span> — {s.goal}
                                </li>
                            ))}
                        </ul>
                    </div>
                ))}
                {cat.fields.length === 0 && !loading && (
                    <div className="rounded-3xl bg-b-surface1 ring-1 ring-s-subtle p-6 text-caption text-t-tertiary">
                        Catalogue unavailable. The agent GET /verticals route and the static mirror are both empty.
                    </div>
                )}
            </div>

            {/* PERSONAS */}
            <div className="mb-3 text-button text-t-primary">Personas</div>
            <div className="grid grid-cols-3 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1 mb-6">
                {cat.personas.map((p) => (
                    <div key={p.key} className="rounded-2xl bg-b-surface1 ring-1 ring-s-subtle ring-inset p-4 dark:bg-shade-04/30">
                        <div className="flex items-center justify-between">
                            <div className="text-body-2 text-t-primary">{p.display}</div>
                            <Badge ok={p.gender === "female"}>{p.gender}</Badge>
                        </div>
                        <div className="text-caption text-t-tertiary mt-1">{p.tone}</div>
                        <div className="text-caption text-t-tertiary mt-2">voice: <span className="text-t-secondary">{p.sarvam_voice ?? "—"}</span> (Sarvam)</div>
                    </div>
                ))}
            </div>

            {/* LANGUAGES */}
            <div className="mb-3 text-button text-t-primary">Languages</div>
            <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1 mb-6">
                {cat.languages.map((l) => (
                    <div key={l.code} className="rounded-2xl bg-b-surface1 ring-1 ring-s-subtle ring-inset p-4 dark:bg-shade-04/30">
                        <div className="flex items-center justify-between">
                            <div className="text-body-2 text-t-primary">{l.name}</div>
                            <span className="text-caption text-t-tertiary">{l.native}</span>
                        </div>
                        <div className="mt-2 flex gap-1.5 flex-wrap">
                            <Badge ok={l.el_speakable}>ElevenLabs {l.el_speakable ? "✓" : "✕"}</Badge>
                            <Badge ok={l.sarvam_speakable}>Sarvam {l.sarvam_speakable ? "✓" : "✕"}</Badge>
                        </div>
                    </div>
                ))}
            </div>

            {/* OVERRIDES editor */}
            <div className="rounded-3xl bg-b-surface1 ring-1 ring-s-subtle ring-inset p-5 dark:bg-shade-04/30">
                <div className="flex items-center justify-between mb-2">
                    <div>
                        <div className="text-button text-t-primary">Overrides (no-deploy)</div>
                        <div className="text-caption text-t-tertiary">
                            Deep-merged over the static registry. Keys: <code>fields</code>, <code>personas</code>, <code>languages</code>.
                        </div>
                    </div>
                    <button onClick={saveOverrides} disabled={busy}
                        className="h-10 px-4 rounded-xl bg-primary-01 text-button text-white disabled:opacity-50">
                        {busy ? "Saving…" : "Save overrides"}
                    </button>
                </div>
                <textarea value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false}
                    className="w-full h-56 px-3 py-2 rounded-2xl input-base text-body-2 font-mono text-xs outline-none resize-y"
                    placeholder='{ "fields": { "legal": { "label": "Legal", "sub_options": { ... } } } }' />
                <p className="text-caption text-t-tertiary mt-2">
                    Example — add a sub-option to an existing field:{" "}
                    <code>{'{ "fields": { "medical": { "sub_options": { "vaccination_reminder": { "label": "Vaccination reminder", "goal": "…", "directive": "…" } } } } }'}</code>
                </p>
            </div>
        </Layout>
    );
}

export default function VerticalsPage() {
    return <SuperAdminGuard><VerticalsInner /></SuperAdminGuard>;
}
