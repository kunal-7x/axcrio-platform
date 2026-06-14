"use client";

/**
 * VideoCreatePanel (W9, S2 twin) — the hero command bar for Video Studio. Mirrors
 * the image CreatePanel grammar (campaign → tier → aspect → count → command box →
 * Generate) but for video: TierTabs is the signature control (composite default),
 * AspectTabs picks the ad-ready ratio, the cost meter reads the HONEST cost-truth
 * ($0 gen-key for composite + metered TTS; "paid" for hosted gen / EL voiceover),
 * and the BYO-key picker (a view over the provider registry) appears for paid tiers.
 *
 * Binds POST /api/creative/video/batches. Dormant-safe: not_configured surfaces a
 * calm inline note, never an error wall. Token-pure, Inter Display, zero raw hex.
 */

import { useMemo, useState } from "react";
import Card from "@/components/Card";
import Field from "@/components/Field";
import Tabs from "@/components/Tabs";
import Switch from "@/components/Switch";
import Select from "@/components/Select";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import CampaignSelect from "@/components/CampaignSelect";
import type { TabsOption } from "@/types/tabs";
import type { SelectOption } from "@/types/select";
import type { Campaign } from "@/lib/api";
import TierTabs, { TIERS } from "./TierTabs";
import ByoKeyPicker from "./ByoKeyPicker";
import {
    proposeBatch,
    VideoError,
    type VideoTier,
    type VideoAspect,
    type TtsProvider,
    type VideoBatch,
} from "@/lib/video";

type VideoCreatePanelProps = {
    enabled: boolean;
    composite: boolean;
    onProposed: (batch: VideoBatch, meta: { count: number }) => void;
    onUpload: () => void;
};

// Ad-ready aspect ratios (the templates an ad needs).
const ASPECTS: { tab: TabsOption; value: VideoAspect; note: string }[] = [
    { tab: { id: 1, name: "9:16" }, value: "9:16", note: "Reels · Stories · Status" },
    { tab: { id: 2, name: "1:1" }, value: "1:1", note: "Feed · Square" },
    { tab: { id: 3, name: "16:9" }, value: "16:9", note: "YouTube · Landscape" },
];

const COUNTS: TabsOption[] = [
    { id: 1, name: "1" },
    { id: 2, name: "2" },
    { id: 3, name: "3" },
    { id: 4, name: "4" },
    { id: 5, name: "5" },
];

const LANGUAGES: SelectOption[] = [
    { id: 1, name: "Auto" },
    { id: 2, name: "Hindi" },
    { id: 3, name: "Hinglish" },
    { id: 4, name: "English" },
    { id: 5, name: "Tamil" },
    { id: 6, name: "Gujarati" },
];

const ROUTES: SelectOption[] = [
    { id: 1, name: "Hook reel" },
    { id: 2, name: "Offer" },
    { id: 3, name: "Social proof" },
    { id: 4, name: "Founder voice" },
];
const routeKey = (o: SelectOption) =>
    ({ 1: "hook", 2: "offer", 3: "social_proof", 4: "founder_voice" }[o.id] || "hook");

const PLACEHOLDERS = [
    "5 vertical hook reels for hot leads, Hinglish, with my product shot",
    "A 6-second offer reel — festive discount, clear CTA",
    "Founder-voice testimonial reel, calm and premium",
    "Social-proof reel from our reviews, Hindi voiceover",
];

const VideoCreatePanel = ({ enabled, composite, onProposed, onUpload }: VideoCreatePanelProps) => {
    const [campaign, setCampaign] = useState<Campaign | null>(null);
    const [tier, setTier] = useState<VideoTier>("composite");
    const [aspect, setAspect] = useState<TabsOption>(ASPECTS[0].tab);
    const [count, setCount] = useState<TabsOption>(COUNTS[0]);
    const [route, setRoute] = useState<SelectOption>(ROUTES[0]);
    const [language, setLanguage] = useState<SelectOption>(LANGUAGES[0]);
    const [withAudio, setWithAudio] = useState(true);
    const [elVoiceover, setElVoiceover] = useState(false); // ElevenLabs = paid, opt-in
    const [instruction, setInstruction] = useState("");
    const [advanced, setAdvanced] = useState(false);
    const [genProviderId, setGenProviderId] = useState("");
    const [hasGenKey, setHasGenKey] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [notice, setNotice] = useState<{ kind: "warning" | "info"; text: string } | null>(null);
    const [phIndex] = useState(() => Math.floor(Math.random() * PLACEHOLDERS.length));

    const tierDef = TIERS.find((t) => t.id === tier)!;
    const aspectDef = ASPECTS.find((a) => a.tab.id === aspect.id)!;
    const isPaidTier = tierDef.paid;
    // EL voiceover is a paid path even on the free composite tier (cost-truth H1).
    const isPaid = isPaidTier || elVoiceover;
    const ttsProvider: TtsProvider = elVoiceover ? "elevenlabs" : "sarvam";

    // HONEST cost meter — composite = ₹0.25/clip floor; paid = a per-sec range.
    const costLabel = useMemo(() => {
        const n = count.id;
        if (!isPaidTier) {
            const tts = elVoiceover ? " + ElevenLabs voiceover (paid)" : "";
            return `≈ ${n} clip${n === 1 ? "" : "s"} · ₹${(0.25 * n).toFixed(2)} · composite${tts}`;
        }
        return `${n} clip${n === 1 ? "" : "s"} · ${tierDef.cost} · paid`;
    }, [count.id, isPaidTier, elVoiceover, tierDef.cost]);

    const canGenerate = enabled && !!campaign && instruction.trim().length > 0 && !submitting;

    const handleGenerate = async () => {
        if (!canGenerate) return;
        setNotice(null);
        setSubmitting(true);
        try {
            const batch = await proposeBatch({
                campaign_id: campaign!.id,
                size: count.id,
                with_audio: withAudio,
                aspect: aspectDef.value,
                route: routeKey(route),
                tier,
                tts_provider: ttsProvider,
            });
            // a paid batch returns awaiting_approval (the 1-paid-test gate) — that's
            // expected and surfaced by BatchProgress, not an error.
            onProposed(batch, { count: count.id });
        } catch (e) {
            if (e instanceof VideoError && e.code === "not_configured") {
                setNotice({
                    kind: "info",
                    text:
                        tier === "composite"
                            ? "The free composite tier isn't enabled on this box yet. Add a provider key, or check back soon."
                            : e.message,
                });
            } else if (e instanceof VideoError && e.code === "over_budget") {
                setNotice({ kind: "warning", text: e.message });
            } else if (e instanceof VideoError && e.code === "paid_gate") {
                setNotice({ kind: "info", text: e.message });
            } else {
                setNotice({ kind: "warning", text: "Couldn't start that. Try again in a moment." });
            }
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <Card title="Create video">
            <div className="px-5 max-lg:px-3">
                {/* campaign */}
                <div className="flex flex-wrap items-end gap-3 mb-4">
                    <CampaignSelect className="min-w-52 grow" value={campaign?.id} onSelect={(c) => setCampaign(c)} />
                </div>

                {/* TIER — the signature control */}
                <div className="mb-4">
                    <div className="flex items-center gap-2 mb-3">
                        <span className="text-button">Render tier</span>
                        <Badge variant="info">Composite is free</Badge>
                    </div>
                    <TierTabs value={tier} onChange={setTier} hasGenKey={hasGenKey} />
                </div>

                {/* aspect + count */}
                <div className="grid grid-cols-2 gap-4 mb-4 max-md:grid-cols-1">
                    <div>
                        <div className="text-button mb-3">Aspect ratio</div>
                        <Tabs items={ASPECTS.map((a) => a.tab)} value={aspect} setValue={setAspect} />
                        <p className="mt-2 text-caption text-t-tertiary">{aspectDef.note}</p>
                    </div>
                    <div>
                        <div className="text-button mb-3">How many?</div>
                        <Tabs items={COUNTS} value={count} setValue={setCount} />
                    </div>
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

                {/* voiceover row */}
                <div className="flex items-center justify-between mt-4 p-3.5 rounded-2xl bg-b-surface2 border border-s-subtle">
                    <div className="flex items-center gap-2.5">
                        <span className="flex items-center justify-center size-8 rounded-xl bg-b-surface1 fill-t-secondary dark:bg-shade-04/40">
                            <Icon className="!size-4 fill-inherit" name="camera-video" />
                        </span>
                        <div>
                            <div className="text-sub-title-2 text-t-primary">Voiceover &amp; captions</div>
                            <p className="text-caption text-t-tertiary">
                                Sarvam Hindi/regional voice + burned-in captions. Free.
                            </p>
                        </div>
                    </div>
                    <Switch checked={withAudio} onChange={setWithAudio} />
                </div>

                {/* BYO-key picker for paid tiers */}
                {isPaidTier && (
                    <ByoKeyPicker
                        value={genProviderId}
                        onChange={(id) => setGenProviderId(id)}
                        onAvailability={setHasGenKey}
                    />
                )}

                {/* Advanced — language / route / ElevenLabs */}
                <button
                    className="flex items-center gap-1.5 mt-3 text-button text-t-secondary fill-t-secondary transition-colors hover:text-t-primary hover:fill-t-primary"
                    onClick={() => setAdvanced((a) => !a)}
                >
                    <Icon className={`!size-4 fill-inherit transition-transform ${advanced ? "rotate-180" : ""}`} name="chevron" />
                    Advanced
                </button>
                {advanced && (
                    <div className="mt-3 space-y-3">
                        <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                            <Select label="Angle" value={route} onChange={setRoute} options={ROUTES} />
                            <Select label="Voice language" value={language} onChange={setLanguage} options={LANGUAGES} />
                        </div>
                        <div className="flex items-center justify-between p-3.5 rounded-2xl bg-b-surface2 border border-s-subtle">
                            <div className="flex items-center gap-2.5">
                                <span className="text-sub-title-2 text-t-primary">Premium voiceover (ElevenLabs)</span>
                                <Badge variant="warning">Paid</Badge>
                            </div>
                            <Switch checked={elVoiceover} onChange={setElVoiceover} />
                        </div>
                        {elVoiceover && (
                            <p className="text-caption text-t-tertiary">
                                ElevenLabs is ~66× the cost of the free Sarvam voice. Your first paid render runs
                                one short test clip before the full batch unlocks.
                            </p>
                        )}
                    </div>
                )}

                {/* notice */}
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

                {/* actions + cost meter */}
                <div className="flex items-center gap-3 mt-5 max-md:flex-col max-md:items-stretch">
                    <Button isStroke icon="upload" onClick={onUpload} disabled={!enabled}>
                        Upload your clip
                    </Button>
                    <div className="ml-auto flex items-center gap-3 max-md:ml-0 max-md:flex-col-reverse max-md:items-stretch">
                        <span className="flex items-center gap-2 text-body-2 text-t-secondary max-md:justify-center">
                            <Badge variant={isPaid ? "warning" : "success"}>{isPaid ? "Paid" : "Free"}</Badge>
                            <span className="tabular-nums">{costLabel}</span>
                        </span>
                        <Button isBlack icon="send" onClick={handleGenerate} disabled={!canGenerate}>
                            {submitting ? "Starting…" : "Generate batch"}
                        </Button>
                    </div>
                </div>

                {!enabled && (
                    <p className="mt-3 text-caption text-t-tertiary">
                        Video Studio activates once your workspace is enabled.
                    </p>
                )}
            </div>
        </Card>
    );
};

export default VideoCreatePanel;
