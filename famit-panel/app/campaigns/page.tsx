"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
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

function statusBadge(status: string) {
    const map: Record<string, string> = {
        active: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
        inactive: "bg-b-surface3 text-t-secondary",
        draft: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
    };
    return (
        <span
            className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${map[status] || "bg-b-surface3 text-t-secondary"}`}
        >
            {status}
        </span>
    );
}

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
            {/* Toast */}
            {toast && (
                <div
                    className={`mb-4 p-3 rounded-2xl text-body-2 flex items-center justify-between gap-3 ${
                        toast.type === "success"
                            ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                            : "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                    }`}
                >
                    <span>{toast.msg}</span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Left: Campaigns table */}
                <div className="flex-1 min-w-0">
                    <Card title="All Campaigns">
                        {loadError && (
                            <div className="mx-5 mb-3 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">
                                {loadError}
                            </div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Company</th>
                                        <th>Product</th>
                                        <th>Status</th>
                                        <th>Created</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        <tr>
                                            <td
                                                colSpan={6}
                                                className="py-8 text-center text-t-secondary"
                                            >
                                                <span className="inline-flex items-center gap-2">
                                                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                                    </svg>
                                                    Loading campaigns…
                                                </span>
                                            </td>
                                        </tr>
                                    ) : campaigns.length === 0 ? (
                                        <tr>
                                            <td
                                                colSpan={6}
                                                className="py-12 text-center text-t-secondary"
                                            >
                                                <div className="flex flex-col items-center gap-2">
                                                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="opacity-30">
                                                        <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                                                    </svg>
                                                    <span className="text-t-tertiary">No campaigns yet — create one on the right</span>
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        campaigns.map((c) => (
                                            <tr
                                                key={c.id}
                                                className="border-t border-s-subtle hover:bg-b-surface2/50 transition-colors"
                                            >
                                                <td className="font-medium">
                                                    {c.name}
                                                </td>
                                                <td className="text-t-secondary">
                                                    {c.company}
                                                </td>
                                                <td className="text-t-secondary">
                                                    {c.product}
                                                </td>
                                                <td>
                                                    {statusBadge(c.status)}
                                                </td>
                                                <td className="text-t-secondary">
                                                    {fmtDate(c.created_at)}
                                                </td>
                                                <td>
                                                    <div className="flex items-center gap-3 justify-end">
                                                        <button
                                                            onClick={() => setAbCampaignId(c.id)}
                                                            className="text-caption text-t-secondary hover:text-t-primary transition-colors"
                                                        >
                                                            A/B
                                                        </button>
                                                        {writable && (
                                                            <button
                                                                onClick={() =>
                                                                    handleDelete(c.id)
                                                                }
                                                                className="text-caption text-red-500 hover:text-red-700 transition-colors"
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
                                                            <button type="button" onClick={() => removeVariant(idx)} className="text-caption text-red-500 hover:text-red-700">✕</button>
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
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={handleBackdrop}>
            <div className="bg-b-surface1 rounded-3xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-xl">
                <div className="flex items-center justify-between p-6 border-b border-s-subtle shrink-0">
                    <h2 className="text-h6 text-t-primary">A/B Results</h2>
                    <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-b-surface2 transition-colors text-t-secondary">×</button>
                </div>
                <div className="overflow-y-auto p-6">
                    {loading && <div className="py-12 text-center text-t-secondary">Loading…</div>}
                    {error && <div className="p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">{error}</div>}
                    {data && (
                        data.variants.length === 0 ? (
                            <div className="py-8 text-center text-t-tertiary">No variants defined for this campaign.</div>
                        ) : (
                            <div className="overflow-x-auto">
                                <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-4 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                                    <thead>
                                        <tr>
                                            <th>Variant</th>
                                            <th>Weight</th>
                                            <th>Dialed</th>
                                            <th>Connected</th>
                                            <th>Interested</th>
                                            <th>Qualified</th>
                                            <th>Avg Interest</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {data.variants.map((v) => (
                                            <tr key={v.id} className={`border-t border-s-subtle ${winnerId === v.id ? "bg-green-50 dark:bg-green-900/20" : ""}`}>
                                                <td className="font-medium">
                                                    {v.label}
                                                    {winnerId === v.id && (
                                                        <span className="ml-2 inline-flex px-2 py-0.5 rounded-full text-caption font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">winner</span>
                                                    )}
                                                </td>
                                                <td className="text-t-secondary">{v.weight}</td>
                                                <td className="text-t-secondary">{v.dialed}</td>
                                                <td className="text-t-secondary">{v.connected}</td>
                                                <td className="text-t-secondary">{v.interested}</td>
                                                <td className="text-t-secondary">{v.qualified}</td>
                                                <td className="font-medium">{v.avg_interest != null ? v.avg_interest.toFixed(1) : "—"}</td>
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
