"use client";

/**
 * VIDEO STUDIO (W9 / U6) — the flagship video workspace. The video twin of the
 * Creative Studio S1 page: one screen where the vendor commands a BATCH of variant
 * ad clips and watches them render in place. Two-column HomePage grammar:
 *
 *   col-left  : <VideoCreatePanel> (tier/aspect/command) + <BatchProgress> (queue → <video> cards)
 *   col-right : "How it works" provenance card + a Recent-videos mini-wall
 *
 * Dormant-safe: probes the studio (useVideoStatus — the whole /creative/video
 * surface 404s when FEATURE_VIDEO_STUDIO is OFF) and renders a calm coming-soon
 * <DormantCard> body, byte-identical-to-live. Videos land in the SAME ai_asset_*
 * library images live in (the bridge §5), read via lib/assets media_type=video.
 * Single <Layout title="Video Studio">, Inter Display, zero raw hex.
 */

import { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import DormantCard from "../_components/DormantCard";
import AssetDetail from "../_components/AssetDetail";
import UsePicker from "../_components/UsePicker";
import AssetCard from "../_components/AssetCard";
import VideoCreatePanel from "./_components/VideoCreatePanel";
import BatchProgress from "./_components/BatchProgress";
import UploadClip from "./_components/UploadClip";
import { useVideoStatus, type VideoBatch } from "@/lib/video";
import { listAssets, type Asset } from "@/lib/assets";
import { useEntitlement } from "@/lib/entitlements";

const HOW_IT_WORKS = [
    { glyph: "magic-pencil", title: "Write the script", note: "AI drafts N distinct-angle ad scripts from your campaign." },
    { glyph: "camera-video", title: "Voice & caption", note: "Sarvam voiceover + burned-in captions — free, no key." },
    { glyph: "video", title: "Render the batch", note: "Composite or AI-motion clips in your ad-ready ratio." },
    { glyph: "send", title: "Reuse everywhere", note: "Attach a winner to WhatsApp, ads or a workflow." },
];

const Page = () => {
    const { enabled, composite, loading } = useVideoStatus();
    // Super-admin per-vendor LOCK/HIDE on the render brain (compose/render). This
    // is cosmetic only — the backend choke-point (402/404) is the real boundary —
    // but it spares the vendor a feature they can't use and drives the upsell.
    const renderEnt = useEntitlement("creative.render_brain");

    const [batchId, setBatchId] = useState<string | null>(null);
    const [expected, setExpected] = useState(1);
    const [finished, setFinished] = useState<Asset[]>([]);
    const [recent, setRecent] = useState<Asset[]>([]);
    const [, setLiveBatch] = useState<VideoBatch | null>(null);

    const [detailAsset, setDetailAsset] = useState<Asset | null>(null);
    const [detailOpen, setDetailOpen] = useState(false);
    const [useAsset, setUseAsset] = useState<Asset | null>(null);
    const [usePickerOpen, setUsePickerOpen] = useState(false);
    const [uploadOpen, setUploadOpen] = useState(false);

    // recent videos (the library, scoped to media_type=video)
    const refreshRecent = () => {
        listAssets({ limit: 8, sort: "newest", media_type: "video" })
            .then((p) => setRecent(p.assets))
            .catch(() => setRecent([]));
    };
    useEffect(() => {
        if (enabled) refreshRecent();
    }, [enabled]);

    // pull the finished videos for the active batch as they land
    const refreshFinished = () => {
        listAssets({ limit: Math.max(expected, 8), sort: "newest", media_type: "video" })
            .then((p) => setFinished(p.assets.slice(0, expected)))
            .catch(() => undefined);
    };

    const onProposed = (batch: VideoBatch, meta: { count: number }) => {
        setExpected(meta.count);
        setFinished([]);
        setBatchId(batch.batch_id || null);
    };

    const openDetail = (a: Asset) => {
        setDetailAsset(a);
        setDetailOpen(true);
    };
    const openUse = (a: Asset) => {
        setUseAsset(a);
        setUsePickerOpen(true);
    };

    if (loading) {
        return (
            <Layout title="Video Studio">
                <div className="py-24">
                    <Spinner />
                </div>
            </Layout>
        );
    }

    return (
        <Layout title="Video Studio">
            {renderEnt === "HIDE" ? (
                // Admin HID the render brain for this vendor — render the same calm
                // "does not exist" surface as a dormant feature (never an error wall).
                <DormantCard
                    title="Video Studio isn't part of your plan"
                    message="The render brain isn't enabled on your workspace. Talk to your account manager to add AI video rendering."
                    icon="camera-video"
                />
            ) : renderEnt === "LOCK" ? (
                // Admin LOCKED it — visible upsell, feature dimmed but discoverable.
                <DormantCard
                    title="Video rendering is locked"
                    message="The render brain is available on a higher plan. Upgrade to compose and render ad-ready video clips from your campaigns."
                    icon="lock"
                />
            ) : !enabled ? (
                <DormantCard
                    title="Video Studio activates with Creative Studio"
                    message="Describe a reel and watch the AI write the script, voice it, burn captions and render a batch of ad-ready clips — composite-cheap by default, AI-motion when you want it. They land in your library, ready to reuse on WhatsApp and ads."
                    icon="camera-video"
                />
            ) : (
                <>
                    <div className="flex max-lg:block">
                        <div className="col-left">
                            <VideoCreatePanel
                                enabled={enabled}
                                composite={composite}
                                onProposed={onProposed}
                                onUpload={() => setUploadOpen(true)}
                            />
                            <BatchProgress
                                batchId={batchId}
                                expectedCount={expected}
                                finished={finished}
                                recent={recent}
                                enabled={enabled}
                                onOpenAsset={openDetail}
                                onUse={openUse}
                                onBatchChange={(b) => {
                                    setLiveBatch(b);
                                    if (b) refreshFinished();
                                }}
                                onDone={() => {
                                    refreshFinished();
                                    refreshRecent();
                                    setBatchId(null);
                                }}
                            />
                        </div>
                        <div className="col-right">
                            <Card title="How it works">
                                <div className="px-5 pb-2 max-lg:px-3">
                                    <div className="space-y-4">
                                        {HOW_IT_WORKS.map((s, i) => (
                                            <div key={s.title} className="flex items-start gap-3">
                                                <span className="flex items-center justify-center size-9 shrink-0 rounded-xl bg-b-surface1 fill-t-secondary dark:bg-shade-04/40">
                                                    <Icon className="!size-4.5 fill-inherit" name={s.glyph} />
                                                </span>
                                                <div>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-caption text-t-tertiary tabular-nums">
                                                            {i + 1}
                                                        </span>
                                                        <span className="text-sub-title-2 text-t-primary">
                                                            {s.title}
                                                        </span>
                                                    </div>
                                                    <p className="text-caption text-t-secondary">{s.note}</p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                    <div className="flex items-center gap-2 mt-5 pt-4 border-t border-s-subtle">
                                        <Badge variant="success">Composite is free</Badge>
                                        <span className="text-caption text-t-tertiary">
                                            No gen-key required.
                                        </span>
                                    </div>
                                </div>
                            </Card>

                            <Card
                                title="Recent videos"
                                headContent={
                                    <Button
                                        as="link"
                                        href="/creative/library"
                                        isStroke
                                        className="ml-auto !h-10 !px-4 !text-body-2"
                                    >
                                        View all
                                    </Button>
                                }
                            >
                                {recent.length === 0 ? (
                                    <div className="px-5 py-8 text-center max-lg:px-3">
                                        <p className="text-body-2 text-t-secondary">
                                            Your latest reels show up here.
                                        </p>
                                    </div>
                                ) : (
                                    <div className="flex flex-wrap px-2">
                                        {recent.slice(0, 4).map((a) => (
                                            <AssetCard key={a.id} asset={a} onOpen={openDetail} onUse={openUse} />
                                        ))}
                                    </div>
                                )}
                            </Card>
                        </div>
                    </div>

                    <AssetDetail
                        asset={detailAsset}
                        open={detailOpen}
                        onClose={() => setDetailOpen(false)}
                        onChanged={(a) =>
                            setRecent((prev) => prev.map((x) => (x.id === a.id ? a : x)))
                        }
                    />
                    <UsePicker
                        asset={useAsset}
                        open={usePickerOpen}
                        onClose={() => setUsePickerOpen(false)}
                        onAttached={refreshRecent}
                    />
                    <UploadClip open={uploadOpen} onClose={() => setUploadOpen(false)} />
                </>
            )}
        </Layout>
    );
};

export default Page;
