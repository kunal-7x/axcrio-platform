"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Select from "@/components/Select";
import Icon from "@/components/Icon";
import Search from "@/components/Search";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import { StatusBadge } from "@/lib/badges";
import {
    extract,
    saveCampaign,
    deleteCampaign,
    getVoices,
    getCampaignAB,
    fetchCompanyLogo,
    type Campaign,
    type ExtractedFields,
    type Voice,
    type CampaignVariant,
    type ABResults,
} from "@/lib/api";
import { useCampaigns } from "@/lib/queries";
import { useMe, canWrite } from "@/lib/auth";
import ScriptStudio from "./_script-studio";

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
    const queryClient = useQueryClient();
    // PERF UNIT-3: cached campaigns list — tab-back is instant. invalidate after
    // a save/delete to refresh.
    const { data: campaignsData, isLoading, error: campaignsErr } = useCampaigns();
    const campaigns: Campaign[] = useMemo(
        () => campaignsData?.campaigns ?? [],
        [campaignsData]
    );
    const loadError = campaignsErr
        ? campaignsErr instanceof Error
            ? campaignsErr.message
            : "Failed to load campaigns"
        : "";
    const loading = isLoading && campaigns.length === 0;
    const refreshCampaigns = () =>
        queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    const [query, setQuery] = useState("");

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

    // Script Studio (vendor free-form script → adopted inbound persona)
    const [studioCampaign, setStudioCampaign] = useState<{ id: string; name: string } | null>(null);

    // Vendor script for the CREATE flow (optional — pasted with the new campaign)
    const [rawScript, setRawScript] = useState("");

    // Company website → logo (optional). On blur / "Fetch logo" we resolve the
    // company's logo from its site and stash it on the campaign's `company_logo`
    // field (inside the editable Extracted-Fields JSON). Best-effort: a failure
    // just leaves the logo empty — it never blocks saving the campaign.
    const [companyWebsite, setCompanyWebsite] = useState("");
    const [companyLogo, setCompanyLogo] = useState("");
    const [fetchingLogo, setFetchingLogo] = useState(false);

    // RBAC
    const { me } = useMe();
    const writable = canWrite(me);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    useEffect(() => {
        // Voices feed the dropdown + default-select; keep this as a one-shot read
        // (the cached campaigns list is handled by useCampaigns above).
        getVoices()
            .then((r) => {
                setVoices(r.voices);
                if (r.voices.length > 0) setSelectedVoice(r.voices[0].voice_id);
            })
            .catch(() => {});
    }, []);

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

    // Merge a logo URL into the editable Extracted-Fields JSON as `company_logo`
    // (and the website as `company_website`). Tolerant of invalid JSON: if the
    // textarea can't be parsed we leave it untouched and just keep the preview
    // state — handleSave will re-attach company_logo at save time as a fallback.
    function mergeLogoIntoFields(logoUrl: string, website: string) {
        setFieldsJson((prev) => {
            if (!prev.trim()) return prev;
            try {
                const obj = JSON.parse(prev);
                if (logoUrl) obj.company_logo = logoUrl;
                if (website) obj.company_website = website;
                return JSON.stringify(obj, null, 2);
            } catch {
                return prev; // don't clobber half-typed JSON
            }
        });
    }

    async function handleFetchLogo() {
        const url = companyWebsite.trim();
        if (!url || fetchingLogo) return;
        setFetchingLogo(true);
        try {
            const { logo_url } = await fetchCompanyLogo(url);
            if (logo_url) {
                setCompanyLogo(logo_url);
                mergeLogoIntoFields(logo_url, url);
                showToast("Logo fetched from website", "success");
            } else {
                // Graceful: no logo found — keep the form usable, just no preview.
                mergeLogoIntoFields("", url);
                showToast("No logo found for that website", "error");
            }
        } catch {
            // Never crash the form on a logo-fetch failure.
            showToast("Couldn't fetch logo — you can still save", "error");
        } finally {
            setFetchingLogo(false);
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
            // Company website → logo (fallback): attach whatever we have so the
            // logo persists even if it was fetched after the JSON last parsed.
            if (companyWebsite.trim() && !fields.company_website) fields.company_website = companyWebsite.trim();
            if (companyLogo && !fields.company_logo) fields.company_logo = companyLogo;
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
            // Vendor script (optional) — stored losslessly; the inbound agent adopts it.
            // Omit entirely when blank so a plain campaign renders byte-identical.
            if (rawScript.trim()) fields.raw_script = rawScript;
            const result = await saveCampaign(fields);
            showToast(`Campaign "${result.name}" saved successfully!`, "success");
            setBrief("");
            setExtracted(null);
            setFieldsJson("");
            setVariants([]);
            setWaFollowup(false);
            setWaTemplateInterested("");
            setWaTemplateCallback("");
            setRawScript("");
            setCompanyWebsite("");
            setCompanyLogo("");
            refreshCampaigns();
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
            refreshCampaigns();
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

    const visibleCampaigns = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return campaigns;
        return campaigns.filter(
            (c) =>
                c.name?.toLowerCase().includes(q) ||
                c.company?.toLowerCase().includes(q) ||
                c.product?.toLowerCase().includes(q)
        );
    }, [campaigns, query]);

    const tableHead = (
        <>
            <th>Name</th>
            <th className="max-lg:hidden">Company</th>
            <th className="max-xl:hidden">Product</th>
            <th>Status</th>
            <th className="max-md:hidden">Created</th>
            <th className="text-right">Actions</th>
        </>
    );

    return (
        <Layout title="Campaigns">
            {/* Toast */}
            {toast && (
                <div
                    className={`mb-3 flex items-center justify-between gap-2 p-3.5 rounded-3xl text-body-2 ${
                        toast.type === "success"
                            ? "bg-primary-02/8 text-primary-02"
                            : "bg-primary-03/8 text-primary-03"
                    }`}
                >
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="flex max-lg:block">
                {/* Left: Campaigns table */}
                <div className={writable ? "col-left" : "w-full"}>
                    <div className="card">
                        <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                            <div className="mr-auto pl-5 text-h6 max-lg:pl-3">
                                All campaigns
                            </div>
                            <Search
                                className="w-64 max-md:w-full max-md:ml-3"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search name, company or product"
                                isGray
                            />
                        </div>

                        {loadError && (
                            <div className="mx-4 mt-3 flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 text-primary-03 text-body-2">
                                <span className="size-1.5 rounded-full bg-current" />
                                {loadError}
                            </div>
                        )}

                        <div className="pt-3 overflow-x-auto">
                            {loading ? (
                                <Table cellsThead={tableHead}>
                                    {[...Array(4)].map((_, i) => (
                                        <TableRow key={i}>
                                            {[...Array(6)].map((__, j) => (
                                                <td key={j}>
                                                    <div className="skeleton h-4 w-20" />
                                                </td>
                                            ))}
                                        </TableRow>
                                    ))}
                                </Table>
                            ) : visibleCampaigns.length === 0 ? (
                                <div className="state-block">
                                    <span className="state-glyph">
                                        <Icon
                                            name={query ? "search" : "promote"}
                                            className="fill-inherit"
                                        />
                                    </span>
                                    <div className="state-title">
                                        {query
                                            ? "No matching campaigns"
                                            : "No campaigns yet"}
                                    </div>
                                    <div className="state-sub">
                                        {query
                                            ? `Nothing matches “${query}”.`
                                            : "Create your first campaign on the right — paste a brief and we extract the pitch for you."}
                                    </div>
                                </div>
                            ) : (
                                <Table cellsThead={tableHead}>
                                    {visibleCampaigns.map((c) => (
                                        <TableRow key={c.id}>
                                            <td className="text-sub-title-1">
                                                {c.name}
                                            </td>
                                            <td className="text-t-secondary max-lg:hidden">
                                                {c.company}
                                            </td>
                                            <td className="text-t-secondary max-xl:hidden">
                                                {c.product}
                                            </td>
                                            <td>
                                                <StatusBadge status={c.status} />
                                            </td>
                                            <td className="text-t-secondary whitespace-nowrap max-md:hidden">
                                                {fmtDate(c.created_at)}
                                            </td>
                                            <td className="text-right">
                                                <div className="flex items-center gap-2 justify-end">
                                                    <Button
                                                        isStroke
                                                        className="!h-9 !px-4 max-md:!px-3"
                                                        onClick={() =>
                                                            setStudioCampaign({ id: c.id, name: c.name })
                                                        }
                                                    >
                                                        <span className="inline-flex items-center gap-1.5">
                                                            <Icon name="magic-pencil" className="size-4 fill-current" />
                                                            <span className="max-md:hidden">Script</span>
                                                        </span>
                                                    </Button>
                                                    <Button
                                                        isStroke
                                                        className="!h-9 !px-4"
                                                        onClick={() =>
                                                            setAbCampaignId(c.id)
                                                        }
                                                    >
                                                        A/B
                                                    </Button>
                                                    {writable && (
                                                        <Button
                                                            isStroke
                                                            className="!h-9 !px-4 hover:!border-primary-03/30 hover:!text-primary-03"
                                                            onClick={() =>
                                                                handleDelete(c.id)
                                                            }
                                                        >
                                                            Delete
                                                        </Button>
                                                    )}
                                                </div>
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            )}
                        </div>
                    </div>
                </div>

                {/* Right: Create campaign (hidden for read-only agents) */}
                {writable && (
                <div className="col-right">
                    <Card title="Create campaign">
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
                                            {(() => {
                                                const VOICE_OPTS = voices.map((v, i) => ({ id: i, name: v.name, value: v.voice_id }));
                                                return (
                                                    <Select
                                                        className="w-full"
                                                        classButton="!h-11"
                                                        value={VOICE_OPTS.find((o) => o.value === selectedVoice) ?? null}
                                                        options={VOICE_OPTS}
                                                        onChange={(o) => setSelectedVoice(VOICE_OPTS[o.id].value as string)}
                                                    />
                                                );
                                            })()}
                                        </div>
                                    )}

                                    {/* Company website → logo */}
                                    <div>
                                        <label className="block text-button mb-3 text-t-primary">
                                            Company website
                                        </label>
                                        <div className="flex gap-3 items-center">
                                            <input
                                                type="url"
                                                value={companyWebsite}
                                                onChange={(e) => setCompanyWebsite(e.target.value)}
                                                onBlur={handleFetchLogo}
                                                placeholder="https://acme.com"
                                                className="flex-1 h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50"
                                            />
                                            <Button
                                                isStroke
                                                className="!h-10 !px-4 shrink-0"
                                                onClick={handleFetchLogo}
                                                disabled={fetchingLogo || !companyWebsite.trim()}
                                            >
                                                {fetchingLogo ? (
                                                    <span className="inline-flex items-center gap-2">
                                                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                                        </svg>
                                                        Fetching…
                                                    </span>
                                                ) : "Fetch logo"}
                                            </Button>
                                        </div>
                                        {companyLogo ? (
                                            <div className="mt-3 flex items-center gap-3">
                                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                                <img
                                                    src={companyLogo}
                                                    alt="Company logo"
                                                    className="size-10 rounded-xl object-contain bg-b-surface2 ring-1 ring-inset ring-s-subtle p-1"
                                                    onError={() => setCompanyLogo("")}
                                                />
                                                <span className="text-caption text-t-tertiary">Logo found — saved to the campaign.</span>
                                            </div>
                                        ) : (
                                            <p className="mt-2 text-caption text-t-tertiary">
                                                Optional — we’ll grab the company logo from the site (used in reports &amp; WhatsApp). Leave blank to skip.
                                            </p>
                                        )}
                                    </div>

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
                                                        {(() => {
                                                            const VOICE_OVERRIDE_OPTS = [
                                                                { id: 0, name: "voice_id override (default)", value: "" },
                                                                ...voices.map((vo, i) => ({ id: i + 1, name: vo.name, value: vo.voice_id })),
                                                            ];
                                                            const current = (v.fields_override.voice_id as string) || "";
                                                            return (
                                                                <Select
                                                                    className="w-full"
                                                                    classButton="!h-9"
                                                                    value={VOICE_OVERRIDE_OPTS.find((o) => o.value === current) ?? null}
                                                                    options={VOICE_OVERRIDE_OPTS}
                                                                    onChange={(o) => updateOverride(idx, "voice_id", VOICE_OVERRIDE_OPTS[o.id].value as string)}
                                                                />
                                                            );
                                                        })()}
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

                                    {/* Vendor script (optional) — adopted inbound persona */}
                                    <div className="border-t border-s-subtle pt-4">
                                        <label className="mb-2 flex items-center gap-2 text-button text-t-primary">
                                            <Icon name="magic-pencil" className="size-4 fill-t-secondary" />
                                            Vendor script (optional)
                                        </label>
                                        <p className="mb-3 text-caption text-t-tertiary">
                                            Paste a free-form brief — how to greet, ask, behave, the tone &amp; language. The inbound agent adopts it losslessly. Refine &amp; dry-run it any time from <span className="text-t-secondary">Script Studio</span> on the campaign row.
                                        </p>
                                        <textarea
                                            value={rawScript}
                                            onChange={(e) => setRawScript(e.target.value)}
                                            placeholder="“Greet warmly: ‘…mein aapka swaagat hai!’ Speak Hinglish, stay friendly. Always pitch our flagship first. Never quote a final price — book a visit instead.”"
                                            className="h-28 w-full resize-none rounded-2xl border border-s-stroke2 bg-transparent px-4 py-3 text-body-2 text-t-primary outline-none transition-colors placeholder:text-t-secondary/45 hover:border-s-highlight focus:border-s-highlight"
                                        />
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

            {studioCampaign && (
                <ScriptStudio
                    campaignId={studioCampaign.id}
                    campaignName={studioCampaign.name}
                    writable={writable}
                    onClose={() => setStudioCampaign(null)}
                    onSaved={refreshCampaigns}
                />
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
                    <h2 className="text-h6 text-t-primary">A/B results</h2>
                    <button onClick={onClose} className="flex items-center justify-center size-8 rounded-full text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary dark:hover:bg-shade-04">×</button>
                </div>
                <div className="overflow-y-auto p-5">
                    {loading && <div className="py-12 text-center text-t-secondary">Loading…</div>}
                    {error && <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 text-primary-03 text-body-2"><span className="size-1.5 rounded-full bg-current" />{error}</div>}
                    {data && (
                        data.variants.length === 0 ? (
                            <div className="state-block"><div className="state-sub">No variants defined for this campaign.</div></div>
                        ) : (
                            <div className="overflow-x-auto">
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Variant</th>
                                            <th>Weight</th>
                                            <th>Dialed</th>
                                            <th>Connected</th>
                                            <th>Interested</th>
                                            <th>Qualified</th>
                                            <th className="text-right">Avg interest</th>
                                        </>
                                    }
                                >
                                    {data.variants.map((v) => (
                                        <TableRow key={v.id} className={winnerId === v.id ? "bg-primary-02/8" : ""}>
                                            <td className="text-sub-title-1">
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
                                            <td className="text-sub-title-1 td-num text-right">{v.avg_interest != null ? v.avg_interest.toFixed(1) : "—"}</td>
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        )
                    )}
                </div>
            </div>
        </div>
    );
}
