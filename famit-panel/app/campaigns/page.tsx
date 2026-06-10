"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import PageHeader from "@/components/PageHeader";
import Icon from "@/components/Icon";
import { StatusBadge } from "@/lib/badges";
import {
    getCampaigns,
    extract,
    saveCampaign,
    deleteCampaign,
    getVoices,
    getCampaignAB,
    type Campaign,
    type ExtractedFields,
    type Voice,
    type CampaignVariant,
    type ABResults,
} from "@/lib/api";
import { useMe, canWrite } from "@/lib/auth";

function fmtDate(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleDateString();
    } catch {
        return d;
    }
}

type Toast = { msg: string; type: "success" | "error" };

export default function CampaignsPage() {
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");

    // Create campaign state
    const [brief, setBrief] = useState("");
    const [extracting, setExtracting] = useState(false);
    const [extracted, setExtracted] = useState<ExtractedFields | null>(null);
    const [fieldsJson, setFieldsJson] = useState("");
    const [saving, setSaving] = useState(false);
    const [toast, setToast] = useState<Toast | null>(null);

    // Voice
    const [voices, setVoices] = useState<Voice[]>([]);
    const [selectedVoice, setSelectedVoice] = useState("");

    // Calling window
    const [windowStart, setWindowStart] = useState("09:00");
    const [windowEnd, setWindowEnd] = useState("21:00");

    // Retry
    const [retryMax, setRetryMax] = useState(3);
    const [retryBackoff, setRetryBackoff] = useState("120,360,1440");

    // A/B variants (optional)
    const [variants, setVariants] = useState<CampaignVariant[]>([]);

    // WhatsApp follow-up (per campaign)
    const [waFollowup, setWaFollowup] = useState(false);
    const [waTemplateInterested, setWaTemplateInterested] = useState("");
    const [waTemplateCallback, setWaTemplateCallback] = useState("");

    // A/B results modal
    const [abCampaignId, setAbCampaignId] = useState<string | null>(null);

    // RBAC
    const { me } = useMe();
    const writable = canWrite(me);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    const loadCampaigns = useCallback(() => {
        setLoading(true);
        setLoadError("");
        getCampaigns()
            .then((r) => setCampaigns(r.campaigns))
            .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load campaigns"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        loadCampaigns();
        getVoices()
            .then((r) => {
                setVoices(r.voices);
                if (r.voices.length > 0) setSelectedVoice(r.voices[0].voice_id);
            })
            .catch(() => {});
    }, [loadCampaigns]);

    async function handleExtract() {
        if (!brief.trim()) return;
        setExtracting(true);
        setToast(null);
        try {
            const fields = await extract(brief);
            setExtracted(fields);
            setFieldsJson(JSON.stringify(fields, null, 2));
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : "Extract failed", "error");
        } finally {
            setExtracting(false);
        }
    }

    async function handleSave() {
        if (!fieldsJson.trim()) return;
        setSaving(true);
        setToast(null);
        try {
            let fields: Record<string, unknown>;
            try {
                fields = JSON.parse(fieldsJson);
            } catch {
                showToast("Invalid JSON — please fix the fields before saving", "error");
                setSaving(false);
                return;
            }
            if (selectedVoice) {
                fields.voice_id = selectedVoice;
            }
            fields.call_window_start = windowStart;
            fields.call_window_end = windowEnd;
            fields.retry_max_attempts = retryMax;
            fields.retry_backoff_mins = retryBackoff.split(",").map((x) => parseInt(x.trim())).filter(Boolean);
            // A/B variants — only attach when at least one is defined; otherwise
            // omit so a plain campaign behaves exactly as before.
            const cleanVariants = variants
                .filter((v) => (v.label || "").trim())
                .map((v) => ({
                    label: v.label.trim(),
                    weight: v.weight && v.weight >= 1 ? v.weight : 1,
                    fields_override: Object.fromEntries(
                        Object.entries(v.fields_override).filter(([, val]) => val != null && String(val).trim() !== "")
                    ),
                }));
            if (cleanVariants.length > 0) {
                fields.variants = cleanVariants;
            }
            // WhatsApp follow-up (default OFF)
            fields.wa_followup = waFollowup;
            if (waTemplateInterested.trim()) fields.wa_template_interested = waTemplateInterested.trim();
            if (waTemplateCallback.trim()) fields.wa_template_callback = waTemplateCallback.trim();
            const result = await saveCampaign(fields);
            showToast(`Campaign "${result.name}" saved successfully!`, "success");
            setBrief("");
            setExtracted(null);
            setFieldsJson("");
            setVariants([]);
            setWaFollowup(false);
            setWaTemplateInterested("");
            setWaTemplateCallback("");
            loadCampaigns();
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : "Save failed", "error");
        } finally {
            setSaving(false);
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Delete this campaign?")) return;
        try {
            await deleteCampaign(id);
            showToast("Campaign deleted", "success");
            loadCampaigns();
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : "Delete failed", "error");
        }
    }

    // ---- A/B variant editor helpers ----
    function addVariant() {
        setVariants((prev) => [
            ...prev,
            { label: `Variant ${String.fromCharCode(65 + prev.length)}`, weight: 1, fields_override: {} },
        ]);
    }
    function removeVariant(idx: number) {
        setVariants((prev) => prev.filter((_, i) => i !== idx));
    }
    function updateVariant(idx: number, patch: Partial<CampaignVariant>) {
        setVariants((prev) => prev.map((v, i) => (i === idx ? { ...v, ...patch } : v)));
    }
    function updateOverride(idx: number, key: string, val: string) {
        setVariants((prev) => prev.map((v, i) => (i === idx ? { ...v, fields_override: { ...v.fields_override, [key]: val } } : v)));
    }

    return (
        <Layout title="Campaigns">
            <PageHeader
                eyebrow="Outreach"
                title="Campaigns"
                subtitle="Paste a brief, let AI extract the pitch, and launch a voice campaign with your chosen agent voice, calling window and A/B variants."
            />

            {/* Toast */}
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Left: Campaigns table */}
                <div className="flex-1 min-w-0">
                    <Card title="All Campaigns">
                        {loadError && (
                            <div className="mx-5 mb-3 toast toast-error">
                                <span className="flex items-center gap-2">
                                    <span className="size-1.5 rounded-full bg-current" />
                                    {loadError}
                                </span>
                            </div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Company</th>
                                        <th>Product</th>
                                        <th>Status</th>
                                        <th>Created</th>
                                        <th className="text-right">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        [...Array(4)].map((_, i) => (
                                            <tr key={i}>
                                                {[...Array(6)].map((__, j) => (
                                                    <td key={j}>
                                                        <div className="skeleton h-4 w-20" />
                                                    </td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : campaigns.length === 0 ? (
                                        <tr>
                                            <td colSpan={6}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon name="promote" className="fill-inherit" />
                                                    </span>
                                                    <div className="state-title">No campaigns yet</div>
                                                    <div className="state-sub">
                                                        Create your first campaign on the right — paste a brief and we extract the pitch for you.
                                                    </div>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        campaigns.map((c) => (
                                            <tr key={c.id}>
                                                <td className="font-medium text-t-primary">
                                                    {c.name}
                                                </td>
                                                <td className="text-t-secondary">
                                                    {c.company}
                                                </td>
                                                <td className="text-t-secondary">
                                                    {c.product}
                                                </td>
                                                <td>
                                                    <StatusBadge status={c.status} />
                                                </td>
                                                <td className="text-t-secondary whitespace-nowrap">
                                                    {fmtDate(c.created_at)}
                                                </td>
                                                <td>
                                                    <div className="flex items-center gap-2 justify-end">
                                                        <button
                                                            onClick={() => setAbCampaignId(c.id)}
                                                            className="action"
                                                        >
                                                            A/B
                                                        </button>
                                                        {writable && (
                                                            <button
                                                                onClick={() =>
                                                                    handleDelete(c.id)
                                                                }
                                                                className="action hover:!text-primary-03 hover:!border-primary-03/30"
                                                            >
                                                                Delete
                                                            </button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>

                {/* Right: Create campaign (hidden for read-only agents) */}
                {writable && (
                <div className="w-96 max-lg:w-full shrink-0">
                    <Card title="Create Campaign">
                        <div className="px-5 pb-5 space-y-4">
                            <div>
                                <label className="block text-button mb-3 text-t-primary">
                                    Campaign Brief
                                </label>
                                <textarea
                                    className="w-full h-32 px-4 py-3 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none transition-colors resize-none hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
                                    placeholder="Describe the campaign: company, product, target audience, goals..."
                                    value={brief}
                                    onChange={(e) => setBrief(e.target.value)}
                                />
                            </div>

                            <Button
                                isBlack
                                className="w-full justify-center"
                                onClick={handleExtract}
                                disabled={extracting || !brief.trim()}
                            >
                                {extracting ? (
                                    <span className="inline-flex items-center gap-2">
                                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                        </svg>
                                        Extracting…
                                    </span>
                                ) : "Extract Fields"}
                            </Button>

                            {extracted && (
                                <>
                                    {voices.length > 0 && (
                                        <div>
                                            <label className="block text-button mb-3 text-t-primary">
                                                AI Voice
                                            </label>
                                            <select
                                                value={selectedVoice}
                                                onChange={(e) => setSelectedVoice(e.target.value)}
                                                className="w-full h-11 px-4 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight bg-transparent"
                                            >
                                                {voices.map((v) => (
                                                    <option key={v.voice_id} value={v.voice_id}>
                                                        {v.name}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    )}

                                    {/* Calling Window */}
                                    <div>
                                        <label className="block text-button mb-3 text-t-primary">
                                            Calling Window (IST)
                                        </label>
                                        <div className="flex gap-3 items-center">
                                            <input
                                                type="time"
                                                value={windowStart}
                                                onChange={(e) => setWindowStart(e.target.value)}
                                                className="flex-1 h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                            />
                                            <span className="text-t-secondary text-body-2">to</span>
                                            <input
                                                type="time"
                                                value={windowEnd}
                                                onChange={(e) => setWindowEnd(e.target.value)}
                                                className="flex-1 h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                            />
                                        </div>
                                    </div>

                                    {/* Retry policy */}
                                    <div className="grid grid-cols-2 gap-3">
                                        <div>
                                            <label className="block text-caption text-t-secondary mb-2">
                                                Max Retries
                                            </label>
                                            <input
                                                type="number"
                                                min="0"
                                                max="10"
                                                value={retryMax}
                                                onChange={(e) => setRetryMax(parseInt(e.target.value) || 0)}
                                                className="w-full h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                            />
                                        </div>
                                        <div>
                                            <label className="block text-caption text-t-secondary mb-2">
                                                Backoff (mins, comma-sep)
                                            </label>
                                            <input
                                                type="text"
                                                value={retryBackoff}
                                                onChange={(e) => setRetryBackoff(e.target.value)}
                                                placeholder="120,360,1440"
                                                className="w-full h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                            />
                                        </div>
                                    </div>

                                    {/* A/B Variants (optional) */}
                                    <div className="border-t border-s-subtle pt-4">
                                        <div className="flex items-center justify-between mb-3">
                                            <label className="block text-button text-t-primary">A/B Variants (optional)</label>
                                            <button type="button" onClick={addVariant} className="text-caption text-t-secondary hover:text-t-primary transition-colors">+ Add variant</button>
                                        </div>
                                        {variants.length === 0 ? (
                                            <p className="text-caption text-t-tertiary">No variants — campaign runs a single version.</p>
                                        ) : (
                                            <div className="space-y-3">
                                                {variants.map((v, idx) => (
                                                    <div key={idx} className="border border-s-stroke2 rounded-2xl p-3 space-y-2">
                                                        <div className="flex items-center gap-2">
                                                            <input
                                                                type="text"
                                                                value={v.label}
                                                                onChange={(e) => updateVariant(idx, { label: e.target.value })}
                                                                placeholder="Label"
                                                                className="flex-1 h-9 px-3 border border-s-stroke2 rounded-xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                                            />
                                                            <input
                                                                type="number"
                                                                min="1"
                                                                value={v.weight}
                                                                onChange={(e) => updateVariant(idx, { weight: parseInt(e.target.value) || 1 })}
                                                                title="Weight"
                                                                className="w-16 h-9 px-2 border border-s-stroke2 rounded-xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                                            />
                                                            <button type="button" onClick={() => removeVariant(idx)} className="text-caption text-t-tertiary transition-colors hover:text-primary-03">✕</button>
                                                        </div>
                                                        <input
                                                            type="text"
                                                            value={(v.fields_override.agent_name as string) || ""}
                                                            onChange={(e) => updateOverride(idx, "agent_name", e.target.value)}
                                                            placeholder="agent_name override (optional)"
                                                            className="w-full h-9 px-3 border border-s-stroke2 rounded-xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                                        />
                                                        <select
                                                            value={(v.fields_override.voice_id as string) || ""}
                                                            onChange={(e) => updateOverride(idx, "voice_id", e.target.value)}
                                                            className="w-full h-9 px-3 border border-s-stroke2 rounded-xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                                        >
                                                            <option value="">voice_id override (default)</option>
                                                            {voices.map((vo) => (
                                                                <option key={vo.voice_id} value={vo.voice_id}>{vo.name}</option>
                                                            ))}
                                                        </select>
                                                        <textarea
                                                            value={(v.fields_override.opener as string) || ""}
                                                            onChange={(e) => updateOverride(idx, "opener", e.target.value)}
                                                            placeholder="opener override (optional)"
                                                            className="w-full h-16 px-3 py-2 border border-s-stroke2 rounded-xl text-body-2 text-t-primary outline-none resize-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                                        />
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>

                                    {/* WhatsApp follow-up */}
                                    <div className="border-t border-s-subtle pt-4">
                                        <label className="flex items-center gap-3 cursor-pointer mb-3">
                                            <input type="checkbox" className="w-4 h-4 rounded" checked={waFollowup} onChange={(e) => setWaFollowup(e.target.checked)} />
                                            <span className="text-body-2 text-t-primary">WhatsApp follow-up after calls</span>
                                        </label>
                                        {waFollowup && (
                                            <div className="space-y-2">
                                                <input
                                                    type="text"
                                                    value={waTemplateInterested}
                                                    onChange={(e) => setWaTemplateInterested(e.target.value)}
                                                    placeholder="wa_template_interested (template name)"
                                                    className="w-full h-9 px-3 border border-s-stroke2 rounded-xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                                />
                                                <input
                                                    type="text"
                                                    value={waTemplateCallback}
                                                    onChange={(e) => setWaTemplateCallback(e.target.value)}
                                                    placeholder="wa_template_callback (template name)"
                                                    className="w-full h-9 px-3 border border-s-stroke2 rounded-xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight"
                                                />
                                                <p className="text-caption text-t-tertiary">Fires only when WhatsApp creds are configured on the server.</p>
                                            </div>
                                        )}
                                    </div>

                                    <div>
                                        <label className="block text-button mb-3 text-t-primary">
                                            Extracted Fields (editable JSON)
                                        </label>
                                        <textarea
                                            className="w-full h-64 px-4 py-3 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none transition-colors resize-none hover:border-s-highlight focus:border-s-highlight bg-transparent font-mono text-xs"
                                            value={fieldsJson}
                                            onChange={(e) =>
                                                setFieldsJson(e.target.value)
                                            }
                                        />
                                    </div>

                                    <Button
                                        isBlack
                                        className="w-full justify-center"
                                        onClick={handleSave}
                                        disabled={saving}
                                    >
                                        {saving ? (
                                            <span className="inline-flex items-center gap-2">
                                                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                                </svg>
                                                Saving…
                                            </span>
                                        ) : "Save Campaign"}
                                    </Button>
                                </>
                            )}
                        </div>
                    </Card>
                </div>
                )}
            </div>

            {abCampaignId && (
                <ABResultsModal campaignId={abCampaignId} onClose={() => setAbCampaignId(null)} />
            )}
        </Layout>
    );
}

function ABResultsModal({ campaignId, onClose }: { campaignId: string; onClose: () => void }) {
    const [data, setData] = useState<ABResults | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        getCampaignAB(campaignId)
            .then(setData)
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
            .finally(() => setLoading(false));
    }, [campaignId]);

    useEffect(() => {
        const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
        document.addEventListener("keydown", handler);
        return () => document.removeEventListener("keydown", handler);
    }, [onClose]);

    function handleBackdrop(e: React.MouseEvent<HTMLDivElement>) {
        if (e.target === e.currentTarget) onClose();
    }

    // Winner = highest avg_interest among variants that were actually dialed.
    const winnerId = (() => {
        if (!data) return null;
        const dialed = data.variants.filter((v) => v.dialed > 0);
        if (dialed.length < 2) return null;
        return dialed.reduce((best, v) => (v.avg_interest > best.avg_interest ? v : best)).id;
    })();

    return (
        <div className="fixed inset-0 z-50 bg-shade-01/60 backdrop-blur-sm flex items-center justify-center p-4" onClick={handleBackdrop}>
            <div className="surface w-full max-w-3xl max-h-[90vh] flex flex-col rise-in">
                <div className="flex items-center justify-between p-5 border-b border-s-subtle shrink-0">
                    <div className="flex items-center gap-2.5">
                        <span className="signal-glyph !h-3.5" aria-hidden><i /><i /><i /></span>
                        <h2 className="text-h6 text-t-primary">A/B Results</h2>
                    </div>
                    <button onClick={onClose} className="flex items-center justify-center size-8 rounded-full text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary dark:hover:bg-shade-04">×</button>
                </div>
                <div className="overflow-y-auto p-5">
                    {loading && <div className="py-12 text-center text-t-secondary">Loading…</div>}
                    {error && <div className="toast toast-error"><span className="flex items-center gap-2"><span className="size-1.5 rounded-full bg-current" />{error}</span></div>}
                    {data && (
                        data.variants.length === 0 ? (
                            <div className="state-block"><div className="state-sub">No variants defined for this campaign.</div></div>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="data-table">
                                    <thead>
                                        <tr>
                                            <th>Variant</th>
                                            <th>Weight</th>
                                            <th>Dialed</th>
                                            <th>Connected</th>
                                            <th>Interested</th>
                                            <th>Qualified</th>
                                            <th className="text-right">Avg Interest</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {data.variants.map((v) => (
                                            <tr key={v.id} className={winnerId === v.id ? "bg-[#00A656]/8" : ""}>
                                                <td className="font-medium text-t-primary">
                                                    {v.label}
                                                    {winnerId === v.id && (
                                                        <span className="pill pill-success ml-2">winner</span>
                                                    )}
                                                </td>
                                                <td className="text-t-secondary td-num">{v.weight}</td>
                                                <td className="text-t-secondary td-num">{v.dialed}</td>
                                                <td className="text-t-secondary td-num">{v.connected}</td>
                                                <td className="text-t-secondary td-num">{v.interested}</td>
                                                <td className="text-t-secondary td-num">{v.qualified}</td>
                                                <td className="font-medium text-t-primary td-num text-right">{v.avg_interest != null ? v.avg_interest.toFixed(1) : "—"}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )
                    )}
                </div>
            </div>
        </div>
    );
}
