"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "@/components/Icon";
import Button from "@/components/Button";
import {
    getCampaign,
    updateCampaign,
    getPromptPreview,
    dryRunCampaign,
    type ScriptMeta,
    type DryRunResult,
    type CampaignFields,
} from "@/lib/api";

// ─────────────────────────────────────────────────────────────────────────────
// SCRIPT STUDIO — author a vendor's free-form SCRIPT for a campaign, see the
// parsed persona hints, preview the EXACT rendered brain the inbound agent adopts
// (GET /prompt-preview), and DRY-RUN one turn (POST /dry-run — free Groq, no DID,
// no real call). The vendor's full script is stored LOSSLESSLY in fields.raw_script;
// the agent ADOPTS it. Flag-gated + earner-safe on the backend (legacy campaigns
// with no raw_script render byte-identical).
// ─────────────────────────────────────────────────────────────────────────────

type Props = {
    campaignId: string;
    campaignName: string;
    writable: boolean;
    onClose: () => void;
    onSaved?: () => void;
};

type Banner = { kind: "success" | "error" | "info"; msg: string } | null;

const SAMPLE_PROMPTS = [
    "Hello, mujhe iske baare mein jaanna tha",
    "Hi, what is this about?",
    "Price kya hai?",
    "I'm not interested, sorry",
];

export default function ScriptStudio({
    campaignId,
    campaignName,
    writable,
    onClose,
    onSaved,
}: Props) {
    // ── source-of-truth: the campaign's full fields (we patch raw_script onto it) ──
    const [fields, setFields] = useState<CampaignFields | null>(null);
    const [loading, setLoading] = useState(true);
    const [loadErr, setLoadErr] = useState("");

    // editor
    const [script, setScript] = useState("");
    const [savedScript, setSavedScript] = useState(""); // last persisted value
    const [scriptMeta, setScriptMeta] = useState<ScriptMeta>({});
    const [saving, setSaving] = useState(false);
    const [banner, setBanner] = useState<Banner>(null);

    // preview (rendered system prompt)
    const [preview, setPreview] = useState("");
    const [previewChars, setPreviewChars] = useState(0);
    const [previewActive, setPreviewActive] = useState(false);
    const [previewLoading, setPreviewLoading] = useState(false);
    const [previewErr, setPreviewErr] = useState("");
    const [previewStale, setPreviewStale] = useState(false);

    // dry-run
    const [sample, setSample] = useState(SAMPLE_PROMPTS[0]);
    const [asReturning, setAsReturning] = useState(false);
    const [dryRunning, setDryRunning] = useState(false);
    const [dryResult, setDryResult] = useState<DryRunResult | null>(null);
    const [dryErr, setDryErr] = useState("");

    const dirty = script !== savedScript;

    const flash = useCallback((b: Banner) => {
        setBanner(b);
        if (b) setTimeout(() => setBanner(null), 4000);
    }, []);

    // ── load the campaign's current fields + first preview ──
    const loadPreview = useCallback(async () => {
        setPreviewLoading(true);
        setPreviewErr("");
        try {
            const p = await getPromptPreview(campaignId);
            setPreview(p.system_prompt || "");
            setPreviewChars(p.chars || (p.system_prompt || "").length);
            setPreviewActive(p.vendor_script_active_in_preview);
            setPreviewStale(false);
        } catch (e: unknown) {
            setPreviewErr(e instanceof Error ? e.message : "Could not render preview");
        } finally {
            setPreviewLoading(false);
        }
    }, [campaignId]);

    useEffect(() => {
        let alive = true;
        (async () => {
            setLoading(true);
            setLoadErr("");
            try {
                const c = await getCampaign(campaignId);
                if (!alive) return;
                const f = (c?.fields ?? {}) as CampaignFields;
                setFields(f);
                const raw =
                    typeof f.raw_script === "string" ? (f.raw_script as string) : "";
                setScript(raw);
                setSavedScript(raw);
                setScriptMeta((f.script_meta as ScriptMeta) ?? {});
            } catch (e: unknown) {
                if (alive)
                    setLoadErr(e instanceof Error ? e.message : "Could not load campaign");
            } finally {
                if (alive) setLoading(false);
            }
            if (alive) loadPreview();
        })();
        return () => {
            alive = false;
        };
    }, [campaignId, loadPreview]);

    // mark preview stale once the script diverges from the loaded value
    useEffect(() => {
        if (dirty) setPreviewStale(true);
    }, [dirty]);

    // Esc-to-close + focus trap entry
    const panelRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", onKey);
        return () => document.removeEventListener("keydown", onKey);
    }, [onClose]);

    // ── save: PATCH raw_script onto the FULL fields (backend replaces wholesale) ──
    async function handleSave() {
        if (!writable || !fields) return;
        setSaving(true);
        setBanner(null);
        try {
            const next: Record<string, unknown> = { ...fields, raw_script: script };
            await updateCampaign(campaignId, next);
            setSavedScript(script);
            setFields(next as CampaignFields);
            flash({ kind: "success", msg: "Script saved — the inbound agent now adopts it." });
            onSaved?.();
            // re-render the brain + refresh the (sanitized) parsed meta from the server
            await loadPreview();
            try {
                const c = await getCampaign(campaignId);
                setScriptMeta((c?.fields?.script_meta as ScriptMeta) ?? {});
            } catch {
                /* meta refresh is best-effort */
            }
        } catch (e: unknown) {
            flash({ kind: "error", msg: e instanceof Error ? e.message : "Save failed" });
        } finally {
            setSaving(false);
        }
    }

    async function handleDryRun() {
        if (!sample.trim()) return;
        setDryRunning(true);
        setDryErr("");
        try {
            const r = await dryRunCampaign(campaignId, sample.trim(), asReturning);
            setDryResult(r);
        } catch (e: unknown) {
            setDryErr(e instanceof Error ? e.message : "Dry-run failed");
        } finally {
            setDryRunning(false);
        }
    }

    function handleBackdrop(e: React.MouseEvent<HTMLDivElement>) {
        if (e.target === e.currentTarget) onClose();
    }

    const metaChips = useMemo(() => buildMetaChips(scriptMeta), [scriptMeta]);
    const doList = (scriptMeta.do ?? scriptMeta.do_list ?? []) as string[];
    const dontList = (scriptMeta.dont ?? scriptMeta.dont_list ?? []) as string[];
    const scriptHasContent = script.trim().length > 0;

    return (
        <div
            className="fixed inset-0 z-50 flex items-stretch justify-center bg-shade-01/60 p-3 backdrop-blur-sm max-md:p-0"
            onClick={handleBackdrop}
            role="dialog"
            aria-modal="true"
            aria-label={`Script Studio — ${campaignName}`}
        >
            <div
                ref={panelRef}
                className="surface flex w-full max-w-6xl flex-col overflow-hidden rise-in max-md:rounded-none"
            >
                {/* ── header ── */}
                <header className="flex shrink-0 items-center gap-3 border-b border-s-subtle px-5 py-4">
                    <span className="flex size-9 items-center justify-center rounded-xl bg-primary-01/10 fill-primary-01">
                        <Icon name="magic-pencil" className="size-5 fill-inherit" />
                    </span>
                    <div className="mr-auto min-w-0">
                        <div className="flex items-center gap-2">
                            <h2 className="truncate text-h6 text-t-primary">Script Studio</h2>
                            <span className="pill pill-info">
                                <span className="pill-dot" />
                                Inbound persona
                            </span>
                        </div>
                        <p className="truncate text-caption text-t-secondary">
                            {campaignName} · paste a brief, preview the brain, dry-run a turn
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        aria-label="Close"
                        className="flex size-8 shrink-0 items-center justify-center rounded-full fill-t-secondary transition-colors hover:bg-b-surface1 hover:fill-t-primary dark:hover:bg-shade-04"
                    >
                        <Icon name="close" className="size-5 fill-inherit" />
                    </button>
                </header>

                {/* ── banner ── */}
                {banner && (
                    <div
                        className={`mx-5 mt-3 flex items-center gap-2 rounded-2xl p-3 text-body-2 ${
                            banner.kind === "success"
                                ? "bg-primary-02/8 text-primary-02"
                                : banner.kind === "error"
                                  ? "bg-primary-03/8 text-primary-03"
                                  : "bg-primary-01/8 text-primary-01"
                        }`}
                    >
                        <span className="size-1.5 rounded-full bg-current" />
                        {banner.msg}
                    </div>
                )}

                {/* ── body: two panes ── */}
                <div className="grid min-h-0 flex-1 grid-cols-2 gap-0 overflow-hidden max-lg:grid-cols-1 max-lg:overflow-y-auto">
                    {/* LEFT — script editor + parsed meta */}
                    <section className="flex min-h-0 flex-col gap-4 overflow-y-auto border-r border-s-subtle p-5 max-lg:overflow-visible max-lg:border-r-0 max-lg:border-b">
                        {loading ? (
                            <div className="space-y-3">
                                <div className="skeleton h-4 w-40" />
                                <div className="skeleton h-48 w-full rounded-2xl" />
                                <div className="skeleton h-4 w-32" />
                            </div>
                        ) : loadErr ? (
                            <div className="flex items-center gap-2 rounded-2xl bg-primary-03/8 p-3.5 text-body-2 text-primary-03">
                                <span className="size-1.5 rounded-full bg-current" />
                                {loadErr}
                            </div>
                        ) : (
                            <>
                                <div className="flex items-center justify-between">
                                    <label
                                        htmlFor="script-editor"
                                        className="flex items-center gap-2 text-button text-t-primary"
                                    >
                                        <Icon
                                            name="feather"
                                            className="size-4 fill-t-secondary"
                                        />
                                        Vendor script
                                    </label>
                                    <span className="text-caption text-t-tertiary tabular-nums">
                                        {script.length.toLocaleString()} chars
                                    </span>
                                </div>

                                <textarea
                                    id="script-editor"
                                    value={script}
                                    onChange={(e) => setScript(e.target.value)}
                                    disabled={!writable}
                                    spellCheck={false}
                                    placeholder={
                                        "Paste the full brief here — how the agent should greet, what to ask, the tone, the language, dos and don'ts. For example:\n\n“Greet warmly: ‘SkyHigh Realty mein aapka swaagat hai!’ Speak Hinglish, stay friendly and unhurried. Always pitch Palm Grove Villas first. Never quote a final price — book a site visit instead.”"
                                    }
                                    className="min-h-[260px] flex-1 resize-none rounded-2xl border border-s-stroke2 bg-transparent px-4 py-3.5 font-mono text-[13px] leading-relaxed text-t-primary outline-none transition-colors placeholder:text-t-secondary/45 hover:border-s-highlight focus:border-s-highlight disabled:opacity-60 max-lg:min-h-[200px]"
                                />

                                <p className="flex items-start gap-2 text-caption text-t-tertiary">
                                    <Icon
                                        name="lock"
                                        className="mt-0.5 size-3.5 shrink-0 fill-t-tertiary"
                                    />
                                    Stored losslessly &amp; injection-guarded — the full
                                    script reaches the live turn, loaded once at
                                    call-connect. Inbound only until promoted to trusted.
                                </p>

                                {/* parsed persona hints */}
                                {(metaChips.length > 0 ||
                                    doList.length > 0 ||
                                    dontList.length > 0) && (
                                    <div className="rounded-2xl border border-s-subtle bg-b-surface1/50 p-4 dark:bg-shade-04/30">
                                        <div className="mb-3 flex items-center gap-2 text-overline text-t-tertiary">
                                            <Icon
                                                name="list"
                                                className="size-3.5 fill-t-tertiary"
                                            />
                                            Parsed persona hints
                                        </div>
                                        {metaChips.length > 0 && (
                                            <div className="mb-3 flex flex-wrap gap-2">
                                                {metaChips.map((c) => (
                                                    <span
                                                        key={c.label}
                                                        className="pill pill-neutral"
                                                        title={c.value}
                                                    >
                                                        <span className="text-t-tertiary">
                                                            {c.label}
                                                        </span>
                                                        <span className="max-w-44 truncate text-t-secondary">
                                                            {c.value}
                                                        </span>
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                        {(doList.length > 0 || dontList.length > 0) && (
                                            <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
                                                {doList.length > 0 && (
                                                    <MetaList
                                                        title="Do"
                                                        tone="success"
                                                        items={doList}
                                                    />
                                                )}
                                                {dontList.length > 0 && (
                                                    <MetaList
                                                        title="Don't"
                                                        tone="danger"
                                                        items={dontList}
                                                    />
                                                )}
                                            </div>
                                        )}
                                        <p className="mt-3 text-caption text-t-tertiary/80">
                                            Hints are a convenience projection — the verbatim
                                            script above is the single source of truth.
                                        </p>
                                    </div>
                                )}

                                {writable && (
                                    <div className="flex items-center gap-3 pt-1">
                                        <Button
                                            isBlack
                                            className="justify-center"
                                            onClick={handleSave}
                                            disabled={saving || !dirty}
                                        >
                                            {saving ? (
                                                <Spinner label="Saving…" />
                                            ) : dirty ? (
                                                "Save script"
                                            ) : (
                                                <span className="inline-flex items-center gap-1.5">
                                                    <Icon
                                                        name="check"
                                                        className="size-4 fill-current"
                                                    />
                                                    Saved
                                                </span>
                                            )}
                                        </Button>
                                        {dirty && (
                                            <button
                                                onClick={() => setScript(savedScript)}
                                                className="text-caption text-t-secondary transition-colors hover:text-t-primary"
                                            >
                                                Revert
                                            </button>
                                        )}
                                        <span className="ml-auto text-caption text-t-tertiary">
                                            {dirty ? "Unsaved changes" : "In sync"}
                                        </span>
                                    </div>
                                )}
                            </>
                        )}
                    </section>

                    {/* RIGHT — preview + dry-run */}
                    <section className="flex min-h-0 flex-col gap-4 overflow-y-auto p-5 max-lg:overflow-visible">
                        {/* prompt preview */}
                        <div className="flex min-h-0 flex-col rounded-2xl border border-s-subtle">
                            <div className="flex items-center gap-2 border-b border-s-subtle px-4 py-3">
                                <Icon name="font" className="size-4 fill-t-secondary" />
                                <span className="text-button text-t-primary">
                                    Rendered brain
                                </span>
                                {previewActive ? (
                                    <span className="pill pill-success">
                                        <span className="pill-dot" />
                                        persona on
                                    </span>
                                ) : (
                                    <span className="pill pill-neutral">base render</span>
                                )}
                                <div className="ml-auto flex items-center gap-3">
                                    {previewChars > 0 && (
                                        <span className="text-caption text-t-tertiary tabular-nums">
                                            {previewChars.toLocaleString()} chars
                                        </span>
                                    )}
                                    <button
                                        onClick={loadPreview}
                                        disabled={previewLoading}
                                        className="flex items-center gap-1 text-caption text-t-secondary transition-colors hover:text-t-primary disabled:opacity-50"
                                    >
                                        <Icon
                                            name="reply"
                                            className={`size-3.5 fill-current ${
                                                previewLoading ? "animate-spin" : ""
                                            }`}
                                        />
                                        Refresh
                                    </button>
                                </div>
                            </div>

                            {previewStale && !previewLoading && (
                                <div className="flex items-center gap-2 border-b border-s-subtle bg-primary-01/6 px-4 py-2 text-caption text-primary-01">
                                    <Icon name="info" className="size-3.5 fill-current" />
                                    Save the script, then Refresh to render the updated brain.
                                </div>
                            )}

                            <div className="min-h-[140px] flex-1 overflow-y-auto p-4 max-lg:max-h-72">
                                {previewLoading ? (
                                    <div className="space-y-2">
                                        {[...Array(6)].map((_, i) => (
                                            <div
                                                key={i}
                                                className="skeleton h-3"
                                                style={{ width: `${90 - i * 8}%` }}
                                            />
                                        ))}
                                    </div>
                                ) : previewErr ? (
                                    <div className="flex items-center gap-2 text-body-2 text-primary-03">
                                        <span className="size-1.5 rounded-full bg-current" />
                                        {previewErr}
                                    </div>
                                ) : preview ? (
                                    <pre className="whitespace-pre-wrap break-words font-mono text-[12.5px] leading-relaxed text-t-secondary">
                                        {preview}
                                    </pre>
                                ) : (
                                    <p className="text-body-2 text-t-tertiary">
                                        No prompt rendered yet.
                                    </p>
                                )}
                            </div>
                        </div>

                        {/* dry-run */}
                        <div className="rounded-2xl border border-s-subtle">
                            <div className="flex items-center gap-2 border-b border-s-subtle px-4 py-3">
                                <Icon name="chat-think" className="size-4 fill-t-secondary" />
                                <span className="text-button text-t-primary">
                                    Dry-run a turn
                                </span>
                                <span className="pill pill-neutral ml-auto">
                                    free · no call
                                </span>
                            </div>

                            <div className="space-y-3 p-4">
                                <div className="flex flex-wrap gap-1.5">
                                    {SAMPLE_PROMPTS.map((s) => (
                                        <button
                                            key={s}
                                            onClick={() => setSample(s)}
                                            className={`rounded-full px-2.5 py-1 text-caption transition-colors ${
                                                sample === s
                                                    ? "bg-primary-01/12 text-primary-01"
                                                    : "bg-b-surface1 text-t-secondary hover:text-t-primary dark:bg-shade-04/50"
                                            }`}
                                        >
                                            {s}
                                        </button>
                                    ))}
                                </div>

                                <div className="flex items-end gap-2 max-sm:flex-col max-sm:items-stretch">
                                    <div className="flex-1">
                                        <label
                                            htmlFor="dry-sample"
                                            className="mb-1.5 block text-caption text-t-secondary"
                                        >
                                            Caller says
                                        </label>
                                        <input
                                            id="dry-sample"
                                            value={sample}
                                            onChange={(e) => setSample(e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.key === "Enter" && !dryRunning)
                                                    handleDryRun();
                                            }}
                                            placeholder="Type what a caller might say…"
                                            className="h-10 w-full rounded-xl border border-s-stroke2 bg-transparent px-3 text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight"
                                        />
                                    </div>
                                    <Button
                                        isBlack
                                        className="justify-center max-sm:w-full"
                                        onClick={handleDryRun}
                                        disabled={dryRunning || !sample.trim()}
                                    >
                                        {dryRunning ? (
                                            <Spinner label="Running…" />
                                        ) : (
                                            <span className="inline-flex items-center gap-1.5">
                                                <Icon
                                                    name="send"
                                                    className="size-4 fill-current"
                                                />
                                                Run
                                            </span>
                                        )}
                                    </Button>
                                </div>

                                <label className="flex w-fit cursor-pointer items-center gap-2 text-caption text-t-secondary">
                                    <input
                                        type="checkbox"
                                        className="size-3.5 rounded"
                                        checked={asReturning}
                                        onChange={(e) => setAsReturning(e.target.checked)}
                                    />
                                    Treat caller as a returning lead
                                </label>

                                {dryErr && (
                                    <div className="flex items-center gap-2 rounded-xl bg-primary-03/8 p-3 text-body-2 text-primary-03">
                                        <span className="size-1.5 rounded-full bg-current" />
                                        {dryErr}
                                    </div>
                                )}

                                {dryResult && (
                                    <div className="space-y-2 step-reveal">
                                        {/* caller bubble — right */}
                                        <div className="flex justify-end">
                                            <div className="max-w-[80%] rounded-2xl rounded-br-md bg-primary-01/12 px-3.5 py-2.5 text-body-2 text-t-primary">
                                                {dryResult.sample_user}
                                            </div>
                                        </div>
                                        {/* agent bubble — left */}
                                        <div className="flex justify-start">
                                            <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-b-surface1 px-3.5 py-2.5 text-body-2 text-t-primary ring-1 ring-s-subtle dark:bg-shade-04/50">
                                                {dryResult.agent_reply}
                                            </div>
                                        </div>
                                        <div className="flex flex-wrap items-center gap-2 pt-1">
                                            {dryResult.vendor_script_active_in_preview && (
                                                <span className="pill pill-success">
                                                    <span className="pill-dot" />
                                                    persona adopted
                                                </span>
                                            )}
                                            <span className="pill pill-neutral">
                                                {dryResult.used_llm
                                                    ? `${dryResult.provider} · ${dryResult.model}`
                                                    : "fallback (LLM down)"}
                                            </span>
                                            <span className="text-caption text-t-tertiary">
                                                {dryResult.note}
                                            </span>
                                        </div>
                                    </div>
                                )}

                                {!dryResult && !dryErr && (
                                    <p className="text-caption text-t-tertiary">
                                        {scriptHasContent
                                            ? "Run a sample line to see the adopted greeting and response."
                                            : "Tip: this campaign has no script yet — it will dry-run the default inbound brain. Paste a script on the left to shape it."}
                                    </p>
                                )}
                            </div>
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}

// ── small helpers ──

function Spinner({ label }: { label: string }) {
    return (
        <span className="inline-flex items-center gap-2">
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                />
                <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
            </svg>
            {label}
        </span>
    );
}

function MetaList({
    title,
    tone,
    items,
}: {
    title: string;
    tone: "success" | "danger";
    items: string[];
}) {
    return (
        <div>
            <div
                className={`mb-1.5 text-caption font-medium ${
                    tone === "success" ? "text-primary-02" : "text-primary-03"
                }`}
            >
                {title}
            </div>
            <ul className="space-y-1">
                {items.map((it, i) => (
                    <li
                        key={i}
                        className="flex items-start gap-1.5 text-caption text-t-secondary"
                    >
                        <span
                            className={`mt-1.5 size-1 shrink-0 rounded-full ${
                                tone === "success" ? "bg-primary-02" : "bg-primary-03"
                            }`}
                        />
                        {it}
                    </li>
                ))}
            </ul>
        </div>
    );
}

function buildMetaChips(meta: ScriptMeta): { label: string; value: string }[] {
    const order: [string, string][] = [
        ["greeting", "Greeting"],
        ["tone", "Tone"],
        ["persona", "Persona"],
        ["language", "Language"],
        ["style", "Style"],
    ];
    const out: { label: string; value: string }[] = [];
    for (const [key, label] of order) {
        const v = meta[key];
        if (typeof v === "string" && v.trim()) out.push({ label, value: v.trim() });
    }
    return out;
}
