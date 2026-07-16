"use client";

// Ad-Engine · Creative Studio tab (W7.5).
//
// The ad-side home for ad creative: browse the asset wall, generate new variants
// from one instruction, upload your own media, and read each variant's MODERATION
// verdict (the fail-closed RERA/Housing/brand/broken-text gate) before it can
// spend. EMBEDS the Creative Studio pieces verbatim (app/creative/_components):
// CreatePanel + UploadAssetModal + GenerationQueue (the 2000ms job poller) +
// LibraryGallery (the reused wall) + UsePicker + AssetCard + AssetDetail. No new
// look — it renders inside the same `col-left`/`col-right` grammar as the Studio
// page, every colour via tokens.
//
// Two data planes, both dormant-safe:
//   • the asset library (lib/assets.ts — listAssets / getBrandKits / status probe)
//     drives the gallery + generate/upload happy path.
//   • the ad-engine moderation feed (_lib: getCreativeVariants / moderateVariant /
//     submitCreative / getCreativeJobs) drives the per-asset moderation Badge +
//     the Approve / Block controls (gated `writable`).
// When the media engine is off (status.enabled === false) the whole body folds to
// the calm <DormantCard> — never an error wall.

import { useCallback, useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Spinner from "@/components/Spinner";

import DormantCard from "@/app/creative/_components/DormantCard";
import CreatePanel from "@/app/creative/_components/CreatePanel";
import GenerationQueue from "@/app/creative/_components/GenerationQueue";
import LibraryGallery from "@/app/creative/_components/LibraryGallery";
import AssetDetail from "@/app/creative/_components/AssetDetail";
import UsePicker from "@/app/creative/_components/UsePicker";
import UploadAssetModal from "@/app/creative/_components/UploadAssetModal";
import { useAssetStatus } from "@/app/creative/_hooks/useAssetStatus";

import { getCampaigns, type Campaign } from "@/lib/api";
import {
    getBrandKits,
    approveAsset,
    type Asset,
    type BrandKit,
    type GenerateResult,
} from "@/lib/assets";
import type { SelectOption } from "@/types/select";

import {
    getCreativeVariants,
    moderateVariant,
    useRealtimeRefresh,
    type CreativeVariant,
    type ReadResult,
} from "../_lib";
import type { AdsTabProps } from "../_shared";

/* --------------------------------------------------- moderation → Badge */

// The fail-closed gate verdict → a Badge tone + a human label. `pending` is the
// default resting state (info, not danger) — a variant can't spend until it's
// approved, but "awaiting review" is normal, not an error.
function moderationVariant(s?: string): "success" | "danger" | "warning" | "info" | "neutral" {
    const v = (s || "pending").toLowerCase();
    if (v === "approved") return "success";
    if (v === "blocked" || v.startsWith("blocked")) return "danger";
    if (v === "pending" || v === "review") return "info";
    return "neutral";
}

function moderationLabel(s?: string): string {
    const map: Record<string, string> = {
        approved: "Approved",
        blocked: "Blocked",
        pending: "In review",
        review: "In review",
    };
    return map[(s || "pending").toLowerCase()] || (s as string);
}

// A campaign list → Select options for the gallery filter rail + upload tagger.
// id 0 reads as "All campaigns" inside FilterRail's chip logic, so the live
// campaigns start at id 1.
function toCampaignOptions(campaigns: Campaign[]): SelectOption[] {
    return campaigns.map((c, i) => ({ id: i + 1, name: c.name }));
}

/* =============================================================== the tab */

export default function CreativeTab({ writable, toast, refresh }: AdsTabProps) {
    // The media-engine dormancy probe (the only un-gated asset route). While it
    // resolves we hold a Spinner; if it says disabled the whole body folds to the
    // calm DormantCard — byte-identical-to-live, never an error wall.
    const { enabled, loading: statusLoading } = useAssetStatus();

    /* ---- shared library context (campaigns + brand kit) ---- */
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [brandKit, setBrandKit] = useState<BrandKit | null>(null);

    useEffect(() => {
        getCampaigns()
            .then(({ campaigns }) => setCampaigns(campaigns))
            .catch(() => setCampaigns([]));
    }, []);

    useEffect(() => {
        if (!enabled) return;
        getBrandKits()
            .then(({ brand_kits }) => setBrandKit(brand_kits[0] || null))
            .catch(() => setBrandKit(null));
    }, [enabled]);

    const campaignOptions = useMemo(() => toCampaignOptions(campaigns), [campaigns]);

    /* ---- generation job (left column) ---- */
    const [jobId, setJobId] = useState<string | null>(null);
    const [jobMeta, setJobMeta] = useState<{ count: number; assetType: string }>({
        count: 1,
        assetType: "Banner",
    });
    const [reloadToken, setReloadToken] = useState(0);

    const onGenerated = (result: GenerateResult, meta: { count: number; assetType: string }) => {
        setJobMeta(meta);
        setJobId(result.job_id);
    };

    /* ---- detail + use + upload modals ---- */
    const [detailAsset, setDetailAsset] = useState<Asset | null>(null);
    const [detailOpen, setDetailOpen] = useState(false);
    const [useAsset, setUseAsset] = useState<Asset | null>(null);
    const [usePickerOpen, setUsePickerOpen] = useState(false);
    const [uploadOpen, setUploadOpen] = useState(false);

    const openDetail = (a: Asset) => {
        setDetailAsset(a);
        setDetailOpen(true);
    };

    const handleApprove = async (a: Asset) => {
        try {
            await approveAsset(a.id);
            setReloadToken((t) => t + 1);
            toast("Creative approved");
        } catch {
            toast("Couldn't approve that creative. Try again in a moment.", "error");
        }
    };

    const handleUse = (a: Asset) => {
        setUseAsset(a);
        setUsePickerOpen(true);
    };

    // After an upload / generation lands, re-pull both the gallery wall AND the
    // moderation feed so a fresh variant shows its review verdict immediately.
    const refreshLibrary = useCallback(() => {
        setReloadToken((t) => t + 1);
        refresh();
    }, [refresh]);

    /* ---- moderation feed (ad-variant verdicts) ---- */
    // The ad-engine's per-variant moderation verdicts. Dormant-safe: a 404 (router
    // not mounted) degrades to an empty strip, never an error — the gallery wall on
    // the right is the primary surface and stands on its own.
    const [mod, setMod] = useState<ReadResult<{ ok: boolean; variants: CreativeVariant[] }> | null>(
        null
    );
    const [modLoading, setModLoading] = useState(true);
    const loadModeration = useCallback(() => {
        setModLoading(true);
        getCreativeVariants()
            .then(setMod)
            .finally(() => setModLoading(false));
    }, []);

    useEffect(() => {
        if (enabled) loadModeration();
    }, [enabled, loadModeration]);

    // 30s visibility-gated poll (the page idiom) keeps the moderation queue fresh
    // while a reviewer is on the tab; the manual Refresh button still re-pulls now.
    useRealtimeRefresh(loadModeration, 30000);

    const variants: CreativeVariant[] = mod?.kind === "ok" ? mod.data.variants || [] : [];
    const pending = variants.filter(
        (v) => (v.moderation_status || "pending").toLowerCase() === "pending"
    );

    const decide = async (v: CreativeVariant, decision: "approved" | "blocked") => {
        if (!writable) return;
        try {
            await moderateVariant(v.variant_id, decision);
            toast(decision === "approved" ? "Variant approved" : "Variant blocked");
            loadModeration();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't update that variant.", "error");
        }
    };

    /* ----------------------------------------------------------- render */

    if (statusLoading) {
        return (
            <div className="py-24">
                <Spinner />
            </div>
        );
    }

    if (!enabled) {
        // The media engine is off for this tenant — the calm coming-soon body.
        return (
            <DormantCard
                title="Creative Studio is warming up"
                message="Connect the media engine to generate and upload ad creative here. Every variant runs the moderation gate — RERA, Housing, brand and broken-text checks — before it can spend."
                icon="camera"
                actionLabel="Refresh"
                onAction={refresh}
            />
        );
    }

    return (
        <>
            <div className="flex max-lg:block">
                {/* LEFT — generate / upload + the live generation queue */}
                <div className="col-left">
                    <CreatePanel
                        campaigns={campaigns}
                        enabled={enabled}
                        brandKitId={brandKit?.id}
                        onGenerated={onGenerated}
                        onUploadReference={writable ? () => setUploadOpen(true) : undefined}
                    />
                    <GenerationQueue
                        jobId={jobId}
                        expectedCount={jobMeta.count}
                        assetTypeLabel={jobMeta.assetType.toLowerCase()}
                        recentAssets={[]}
                        enabled={enabled}
                        onOpenAsset={openDetail}
                        onApprove={handleApprove}
                        onUse={handleUse}
                        onRetry={() => setJobId(null)}
                        onJobDone={() => {
                            refreshLibrary();
                            setJobId(null);
                        }}
                    />
                </div>

                {/* RIGHT — the moderation queue + the full gallery wall */}
                <div className="col-right">
                    <Card
                        title="Moderation"
                        headContent={
                            pending.length > 0 ? (
                                <span className="ml-auto pill pill-info !px-2 text-caption">
                                    {pending.length} awaiting review
                                </span>
                            ) : undefined
                        }
                    >
                        {modLoading && mod === null ? (
                            <div className="p-3 space-y-2">
                                {[0, 1, 2].map((i) => (
                                    <div key={i} className="skeleton h-14 rounded-2xl" />
                                ))}
                            </div>
                        ) : mod?.kind === "error" ? (
                            <div className="px-5 py-8 text-center max-lg:px-3">
                                <p className="text-body-2 text-t-secondary mb-4">{mod.message}</p>
                                <Button isStroke onClick={loadModeration}>
                                    Try again
                                </Button>
                            </div>
                        ) : variants.length === 0 ? (
                            <div className="px-5 py-8 text-center max-lg:px-3">
                                <p className="text-body-2 text-t-secondary">
                                    No variants in the queue. Generate ad creative on the left and each
                                    one lands here for review before it can spend.
                                </p>
                            </div>
                        ) : (
                            <div className="px-2 pb-2 space-y-2 max-lg:px-0">
                                {variants.map((v) => (
                                    <div
                                        key={v.variant_id}
                                        className="flex items-center gap-3 p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30"
                                    >
                                        <span
                                            className="size-11 shrink-0 rounded-xl bg-cover bg-center bg-b-surface1 dark:bg-shade-04/40"
                                            style={
                                                v.url ? { backgroundImage: `url(${v.url})` } : undefined
                                            }
                                        />
                                        <div className="min-w-0 flex-1">
                                            <div className="text-body-2 text-t-primary line-clamp-1">
                                                {v.headline || "Untitled variant"}
                                            </div>
                                            <div className="mt-1 flex items-center gap-2">
                                                <Badge variant={moderationVariant(v.moderation_status)} dot>
                                                    {moderationLabel(v.moderation_status)}
                                                </Badge>
                                                {v.moderation_reason && (
                                                    <span className="text-caption text-t-tertiary line-clamp-1">
                                                        {v.moderation_reason}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                        {writable &&
                                            (v.moderation_status || "pending").toLowerCase() !==
                                                "approved" && (
                                                <div className="flex items-center gap-1.5 shrink-0">
                                                    <Button
                                                        isStroke
                                                        icon="check"
                                                        className="!h-9 !px-3 !text-caption"
                                                        onClick={() => decide(v, "approved")}
                                                    >
                                                        Approve
                                                    </Button>
                                                    {(v.moderation_status || "pending").toLowerCase() !==
                                                        "blocked" && (
                                                        <Button
                                                            isStroke
                                                            icon="close"
                                                            className="!h-9 !px-3 !text-caption"
                                                            onClick={() => decide(v, "blocked")}
                                                        >
                                                            Block
                                                        </Button>
                                                    )}
                                                </div>
                                            )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </Card>

                    <LibraryGallery
                        campaignOptions={campaignOptions}
                        showBulk={writable}
                        reloadToken={reloadToken}
                        onOpen={openDetail}
                        onUse={writable ? handleUse : undefined}
                        headerExtra={
                            writable ? (
                                <Button
                                    isStroke
                                    icon="upload"
                                    className="!h-10 !px-4 !text-body-2"
                                    onClick={() => setUploadOpen(true)}
                                >
                                    Upload
                                </Button>
                            ) : undefined
                        }
                    />
                </div>
            </div>

            {/* asset detail drawer */}
            <AssetDetail
                asset={detailAsset}
                open={detailOpen}
                onClose={() => setDetailOpen(false)}
                onChanged={() => setReloadToken((t) => t + 1)}
            />

            {/* cross-platform "Use this →" picker (approve-and-attach) */}
            <UsePicker
                asset={useAsset}
                open={usePickerOpen}
                onClose={() => setUsePickerOpen(false)}
                onAttached={refreshLibrary}
                onApproved={() => setReloadToken((t) => t + 1)}
            />

            {/* upload your own image / video into the library */}
            <UploadAssetModal
                open={uploadOpen}
                onClose={() => setUploadOpen(false)}
                onUploaded={refreshLibrary}
                campaignOptions={campaignOptions}
            />
        </>
    );
}
