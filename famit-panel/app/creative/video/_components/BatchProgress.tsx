"use client";

/**
 * BatchProgress (W9) — the Video Studio "Generation" surface. The video twin of
 * GenerationQueue: it polls an in-flight batch (useBatchPoll), shows N liquid
 * <CreativeSkeleton> slots that morph IN PLACE into real <video> variant cards as
 * each render lands (collected into the live library by the bridge), and surfaces
 * the APPROVAL GATE for a paid batch (composite + Sarvam renders free, so it's not
 * gated; a paid batch parks "awaiting approval" with the forced 1-paid-test posture).
 *
 * Each finished variant is a first-class Asset (media_type=video) → it renders with
 * the SAME AssetCard the image library uses (one component, one look). Dormant/error
 * states are calm, never an error-wall. Token-pure, zero raw hex.
 */

import { useEffect } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import CreativeSkeleton from "@/app/creative/_components/CreativeSkeleton";
import AssetCard from "@/app/creative/_components/AssetCard";
import { useBatchPoll, approveBatch, rejectBatch, cancelBatch, variantLabel, type VideoBatch } from "@/lib/video";
import type { Asset } from "@/lib/assets";

type BatchProgressProps = {
    batchId: string | null;
    expectedCount: number;
    /** finished video assets pulled from the library (media_type=video) for this batch */
    finished: Asset[];
    onOpenAsset: (a: Asset) => void;
    onUse: (a: Asset) => void;
    onBatchChange?: (b: VideoBatch | null) => void;
    onDone?: () => void;
    /** idle: the recent-videos wall (when no batch is running) */
    recent: Asset[];
    enabled: boolean;
};

const slotCls =
    "w-[calc(20%-1.5rem)] mt-6 mx-3 max-4xl:w-[calc(25%-1.5rem)] max-[1539px]:w-[calc(33.333%-1.5rem)] max-lg:w-[calc(50%-1.5rem)] max-md:w-[calc(100%-1.5rem)]";

const BatchProgress = ({
    batchId,
    expectedCount,
    finished,
    onOpenAsset,
    onUse,
    onBatchChange,
    onDone,
    recent,
    enabled,
}: BatchProgressProps) => {
    const batch = useBatchPoll(batchId);

    // bubble the live batch up (cost meter / status chip in the parent)
    useEffect(() => {
        onBatchChange?.(batch);
        const s = (batch?.status || "").toLowerCase();
        if (s === "complete" || s === "completed") onDone?.();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [batch?.status]);

    const jobs = batch?.jobs || [];
    const doneCount = jobs.filter((j) => (j.status || "").toLowerCase() === "succeeded").length;
    const total = batch ? jobs.length || expectedCount : expectedCount;
    const status = (batch?.status || "").toLowerCase();
    const awaiting = status === "awaiting_approval";
    const isRunning = !!batchId && !["complete", "completed", "cancelled", "rejected"].includes(status) && !status.startsWith("error");
    const failed = status.startsWith("error");

    // map finished assets onto their slot index (by order)
    const byIndex = (i: number): Asset | undefined => finished[i];

    const head = (
        <div className="flex items-center gap-3 ml-auto">
            {batchId && !failed && (
                <span className="text-caption text-t-tertiary max-md:hidden tabular-nums">
                    {doneCount} of {total} ready
                </span>
            )}
            {batch?.estimated_cost_usd && batchId && (
                <Badge variant="neutral">${batch.estimated_cost_usd}</Badge>
            )}
        </div>
    );

    return (
        <Card title="Generation" headContent={head}>
            <div className="p-1 pt-3 max-lg:px-0">
                {/* APPROVAL GATE — a paid batch parks here (1-paid-test posture) */}
                {awaiting && batch && (
                    <div className="mx-3 mt-3 p-4 rounded-2xl border border-primary-02/25 bg-primary-02/8">
                        <div className="flex items-start gap-3">
                            <span className="flex items-center justify-center size-9 shrink-0 rounded-xl bg-primary-02/15 fill-primary-02">
                                <Icon className="!size-4.5 fill-inherit" name="info" />
                            </span>
                            <div className="grow">
                                <div className="text-sub-title-2 text-t-primary">Approval needed</div>
                                <p className="mt-1 text-body-2 text-t-secondary">
                                    {batch.approval?.reason ||
                                        "This is a paid render. Your first paid batch runs one short test clip before the full batch unlocks."}
                                    {batch.estimated_cost_usd ? ` Estimated ${"$" + batch.estimated_cost_usd}.` : ""}
                                </p>
                                <div className="flex items-center gap-2.5 mt-3">
                                    <Button isBlack className="!h-10 !px-5 !text-body-2" onClick={() => batchId && approveBatch(batchId)}>
                                        Approve &amp; render
                                    </Button>
                                    <Button isStroke className="!h-10 !px-5 !text-body-2" onClick={() => batchId && rejectBatch(batchId)}>
                                        Discard
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* RUNNING / DONE — the variant grid (skeletons morph into <video> cards) */}
                {(isRunning || (finished.length > 0 && batchId)) && !awaiting && (
                    <div className="flex flex-wrap">
                        {Array.from({ length: total }).map((_, i) => {
                            const v = byIndex(i);
                            if (v) {
                                return <AssetCard key={v.id} asset={v} onOpen={onOpenAsset} onUse={onUse} />;
                            }
                            const job = jobs[i];
                            const jobDone = (job?.status || "").toLowerCase() === "succeeded";
                            const jobFailed = ["failed", "error", "cancelled"].includes((job?.status || "").toLowerCase());
                            return (
                                <div key={`skel-${i}`} className={slotCls}>
                                    <CreativeSkeleton
                                        label={variantLabel(job?.variant_key || job?.angle) + ` ${i + 1}`}
                                        state={jobFailed ? "error" : jobDone ? "ready" : "generating"}
                                    />
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* FAILED */}
                {failed && (
                    <div className="px-5 py-10 text-center max-lg:px-3">
                        <p className="text-body-2 text-t-secondary max-w-90 mx-auto">
                            Couldn&apos;t render that batch. Try again, or switch to the free composite tier.
                        </p>
                        {batchId && (
                            <Button isStroke className="mt-4" onClick={() => cancelBatch(batchId)}>
                                Clear
                            </Button>
                        )}
                    </div>
                )}

                {/* IDLE — the recent-videos wall / first-visit empty state */}
                {!batchId && (
                    recent.length > 0 ? (
                        <div className="flex flex-wrap">
                            {recent.map((a) => (
                                <AssetCard key={a.id} asset={a} onOpen={onOpenAsset} onUse={onUse} />
                            ))}
                        </div>
                    ) : (
                        <div className="pt-16 pb-20 text-center max-md:py-12">
                            <div className="inline-flex items-center justify-center size-12 rounded-2xl bg-b-surface1 fill-t-tertiary mb-3 dark:bg-shade-04/40">
                                <Icon name="camera-video" />
                            </div>
                            <div className="inline-block mb-2 text-h5">
                                {enabled ? "Pick a campaign and describe your reel" : "Video Studio is almost ready"}
                            </div>
                            <p className="text-body-2 text-t-secondary max-w-90 mx-auto">
                                {enabled
                                    ? "Your variant clips stream in here as the studio writes the script, voices it, burns captions, and renders — angle-labelled and ready to reuse."
                                    : "Once your workspace is enabled, your generated videos appear here."}
                            </p>
                        </div>
                    )
                )}
            </div>
        </Card>
    );
};

export default BatchProgress;
