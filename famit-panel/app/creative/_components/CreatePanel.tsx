"use client";

/**
 * CreatePanel (S2) — the hero command bar. The whole happy path: pick a campaign,
 * type ONE instruction, Generate. Ports the `NewProductPage` head grammar (a row
 * of selectors above a primary input) as one calm command surface (cs-workspace §4).
 *
 * Progressive disclosure (the "keep it SIMPLE" mandate): only Campaign + command
 * box + Generate are prominent. Asset-type/platform sit in one quieter row.
 * "Advanced" hides model · count · sizes · language — default everything to "Auto".
 *
 * Binds POST /api/assets/generate. Dormant-safe: when disabled, Generate is
 * disabled with a calm token note (the page renders <DormantCard> around this).
 * over_budget (402) / needs_input (422) surface as inline token banners, never a
 * raw error. Idempotent (sends an idempotency_key to dedupe double-click).
 */

import { useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Field from "@/components/Field";
import Select from "@/components/Select";
import CampaignSelect from "@/components/CampaignSelect";
import Tabs from "@/components/Tabs";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import type { SelectOption } from "@/types/select";
import type { TabsOption } from "@/types/tabs";
import {
    generate,
    getProviders,
    toCredits,
    AssetDormantError,
    AssetGuardError,
    type AssetProvider,
    type GenerateResult,
    type CampaignContextSnapshot,
} from "@/lib/assets";
import type { Campaign } from "@/lib/api";

type CreatePanelProps = {
    /** kept for API-compat with the page; CampaignSelect now self-fetches the list */
    campaigns?: Campaign[];
    enabled: boolean;
    /** brand kit id from the page (fallback when the snapshot carries none) */
    brandKitId?: string;
    /** preset platform (e.g. WhatsApp deep-link) */
    presetPlatform?: string;
    onCampaignChange?: (campaignId?: string) => void;
    /** fired with the new job id when Generate succeeds */
    onGenerated: (result: GenerateResult, meta: { count: number; assetType: string }) => void;
    onUploadReference?: () => void;
};

const ASSET_TYPES: TabsOption[] = [
    { id: 1, name: "Banner" },
    { id: 2, name: "Social" },
    { id: 3, name: "Story" },
    { id: 4, name: "Poster" },
    { id: 5, name: "Logo" },
];

const PLATFORMS: SelectOption[] = [
    { id: 1, name: "Meta" },
    { id: 2, name: "WhatsApp" },
    { id: 3, name: "IG Story" },
    { id: 4, name: "Google" },
    { id: 5, name: "Hero" },
    { id: 6, name: "Custom" },
];

// Variant count — founder mandate: allow ONE image (no hard min-3). N = 1..5.
// The backend honours n=1 and produces exactly one (ai_asset jobs.py _spec_count).
const COUNTS: SelectOption[] = [
    { id: 1, name: "1 image" },
    { id: 2, name: "2 variants" },
    { id: 3, name: "3 variants" },
    { id: 4, name: "4 variants" },
    { id: 5, name: "5 variants" },
];

// Short labels for the primary segmented count control (1/2/3/4/5).
const COUNTS_TABS: TabsOption[] = COUNTS.map((c) => ({ id: c.id, name: String(c.id) }));

const SIZES: SelectOption[] = [
    { id: 1, name: "Auto (recommended)" },
    { id: 2, name: "1:1 · 1080×1080" },
    { id: 3, name: "4:5 · 1080×1350" },
    { id: 4, name: "9:16 · Story" },
    { id: 5, name: "16:9 · Landscape" },
];

const LANGUAGES: SelectOption[] = [
    { id: 1, name: "Auto" },
    { id: 2, name: "English" },
    { id: 3, name: "Hindi" },
    { id: 4, name: "Hinglish" },
    { id: 5, name: "Gujarati" },
];

const STYLES: SelectOption[] = [
    { id: 1, name: "Auto" },
    { id: 2, name: "Premium" },
    { id: 3, name: "Local" },
    { id: 4, name: "Bold offer" },
    { id: 5, name: "Emotional" },
    { id: 6, name: "Trust" },
    { id: 7, name: "Minimal" },
];

const PLACEHOLDERS = [
    "Create 5 ad banners for this campaign",
    "WhatsApp poster for hot leads, Hinglish",
    "Make it premium, no price",
    "Festive offer banner with a clear CTA",
];

const CreatePanel = ({
    enabled,
    brandKitId,
    presetPlatform,
    onCampaignChange,
    onGenerated,
    onUploadReference,
}: CreatePanelProps) => {
    // CampaignSelect self-fetches the list and, on pick, auto-fetches the detail
    // snapshot — selection + detail-fetch are now ONE action (no manual paste).
    const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
    // brand_kit_id resolved from the campaign's own detail snapshot; falls back to
    // the page-level brandKitId prop when the snapshot carries none (dormant path).
    const [snapBrandKitId, setSnapBrandKitId] = useState<string | undefined>(undefined);
    const [assetType, setAssetType] = useState<TabsOption>(ASSET_TYPES[0]);
    const [platform, setPlatform] = useState<SelectOption>(PLATFORMS[0]);
    // default to ONE image (founder mandate) — the count is steerable below.
    const [count, setCount] = useState<SelectOption>(COUNTS[0]);
    const [size, setSize] = useState<SelectOption>(SIZES[0]);
    const [language, setLanguage] = useState<SelectOption>(LANGUAGES[0]);
    const [style, setStyle] = useState<SelectOption>(STYLES[0]);
    const [model, setModel] = useState<SelectOption>({ id: 0, name: "Auto (recommended)" });
    const [instruction, setInstruction] = useState("");
    const [advanced, setAdvanced] = useState(false);
    const [providers, setProviders] = useState<AssetProvider[]>([]);
    const [submitting, setSubmitting] = useState(false);
    const [notice, setNotice] = useState<{ kind: "warning" | "info"; text: string } | null>(null);
    const [phIndex] = useState(() => Math.floor(Math.random() * PLACEHOLDERS.length));

    // preset platform (WhatsApp deep-link from the WA builder)
    useEffect(() => {
        if (!presetPlatform) return;
        const match = PLATFORMS.find((p) => p.name.toLowerCase() === presetPlatform.toLowerCase());
        if (match) setPlatform(match);
    }, [presetPlatform]);

    // load the model registry for the Advanced selector (Auto stays default)
    useEffect(() => {
        if (!enabled) return;
        getProviders().then(({ providers }) => setProviders(providers));
    }, [enabled]);

    const modelOptions: SelectOption[] = useMemo(
        () => [
            { id: 0, name: "Auto (recommended)" },
            ...providers.map((p, i) => ({ id: i + 1, name: p.display_name })),
        ],
        [providers]
    );

    // fired by CampaignSelect after it auto-fetches the campaign's detail snapshot
    const handleCampaignSelect = (c: Campaign, detail: CampaignContextSnapshot) => {
        setSelectedCampaign(c);
        setSnapBrandKitId(detail.brand_kit_id);
        onCampaignChange?.(c.id);
    };

    const estCredits = useMemo(() => {
        // a light client-side estimate (the live cost confirmation arrives on submit)
        const per = 6;
        return per * (count.id || 5);
    }, [count]);

    const canGenerate =
        enabled && !!selectedCampaign && instruction.trim().length > 0 && !submitting;

    const handleGenerate = async () => {
        if (!canGenerate) return;
        setNotice(null);
        setSubmitting(true);
        try {
            const result = await generate({
                campaign_id: selectedCampaign?.id,
                platform: platform.name,
                asset_type: assetType.name,
                count: count.id || 5,
                instruction: instruction.trim(),
                language: language.name === "Auto" ? undefined : language.name,
                model: model.id === 0 ? undefined : providers[model.id - 1]?.provider_id,
                // prefer the campaign's own brand kit (from its detail snapshot);
                // fall back to the page-level brand kit when the snapshot has none.
                brand_kit_id: snapBrandKitId ?? brandKitId,
            });
            if (result.state === "needs_input") {
                setNotice({
                    kind: "info",
                    text:
                        result.clarify?.map((c) => c.question).join(" · ") ||
                        "I need a little more to make these well.",
                });
                return;
            }
            onGenerated(result, { count: count.id || 5, assetType: assetType.name });
        } catch (e) {
            if (e instanceof AssetDormantError) {
                setNotice({ kind: "warning", text: e.message });
            } else if (e instanceof AssetGuardError && e.code === "over_budget") {
                setNotice({ kind: "warning", text: e.message });
            } else if (e instanceof AssetGuardError && e.code === "needs_input") {
                setNotice({ kind: "info", text: e.message });
            } else {
                setNotice({ kind: "warning", text: "Couldn't start that. Try again in a moment." });
            }
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <Card title="Create">
            <div className="px-5 max-lg:px-3">
                {/* quieter selector row: campaign + asset type + platform */}
                <div className="flex flex-wrap items-end gap-3 mb-4">
                    <CampaignSelect
                        className="min-w-52 grow"
                        value={selectedCampaign?.id}
                        onSelect={handleCampaignSelect}
                    />
                    <Select
                        className="min-w-40"
                        label="Platform"
                        value={platform}
                        onChange={setPlatform}
                        options={PLATFORMS}
                    />
                </div>

                <div className="mb-4">
                    <div className="text-button mb-3">Asset type</div>
                    <Tabs items={ASSET_TYPES} value={assetType} setValue={setAssetType} />
                </div>

                {/* How many — a primary, steerable count (1 = one image; up to 5). */}
                <div className="mb-4">
                    <div className="text-button mb-3">How many?</div>
                    <Tabs
                        items={COUNTS_TABS}
                        value={count}
                        setValue={setCount}
                    />
                </div>

                {/* the hero command box */}
                <Field
                    textarea
                    label="What should I make?"
                    placeholder={PLACEHOLDERS[phIndex]}
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    classInput="!h-28"
                />

                {/* Advanced disclosure — model / count / size / language / style */}
                <button
                    className="flex items-center gap-1.5 mt-3 text-button text-t-secondary fill-t-secondary transition-colors hover:text-t-primary hover:fill-t-primary"
                    onClick={() => setAdvanced((a) => !a)}
                >
                    <Icon
                        className={`!size-4 fill-inherit transition-transform ${advanced ? "rotate-180" : ""}`}
                        name="chevron"
                    />
                    Advanced
                </button>
                {advanced && (
                    <div className="grid grid-cols-2 gap-3 mt-3 max-md:grid-cols-1">
                        <Select label="Model" value={model} onChange={setModel} options={modelOptions} />
                        <Select label="Size" value={size} onChange={setSize} options={SIZES} />
                        <Select label="Language" value={language} onChange={setLanguage} options={LANGUAGES} />
                        <Select label="Style" value={style} onChange={setStyle} options={STYLES} />
                    </div>
                )}

                {/* notice banner (over-budget / needs-input / dormant) — token-styled */}
                {notice && (
                    <div
                        className={`flex items-start gap-2.5 mt-4 p-3.5 rounded-2xl border text-body-2 ${
                            notice.kind === "warning"
                                ? "border-primary-05/20 bg-primary-05/10 text-primary-05"
                                : "border-primary-01/20 bg-primary-01/10 text-primary-01"
                        }`}
                    >
                        <Icon className="!size-4 shrink-0 mt-0.5 fill-current" name="info" />
                        <span>{notice.text}</span>
                    </div>
                )}

                {/* actions + estimate */}
                <div className="flex items-center gap-3 mt-5 max-md:flex-col max-md:items-stretch">
                    {onUploadReference && (
                        <Button isStroke icon="upload" onClick={onUploadReference} disabled={!enabled}>
                            Upload reference
                        </Button>
                    )}
                    <div className="ml-auto flex items-center gap-3 max-md:ml-0 max-md:flex-col-reverse max-md:items-stretch">
                        <span className="flex items-center gap-2 text-body-2 text-t-secondary max-md:justify-center">
                            <Badge variant="neutral">≈ {toCredits(estCredits * 100)}</Badge>
                            {count.id} {assetType.name.toLowerCase()}
                            {count.id === 1 ? "" : "s"}
                        </span>
                        <Button isBlack onClick={handleGenerate} disabled={!canGenerate}>
                            {submitting ? "Starting…" : "Generate"}
                        </Button>
                    </div>
                </div>

                {!enabled && (
                    <p className="mt-3 text-caption text-t-tertiary">
                        Creative Studio activates once your workspace is enabled.
                    </p>
                )}
            </div>
        </Card>
    );
};

export default CreatePanel;
