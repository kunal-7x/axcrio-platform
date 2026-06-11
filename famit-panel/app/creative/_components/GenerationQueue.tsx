"use client";

/**
 * GenerationQueue (S4 + S5) — the signature. Binds the W1 <GenerationLoader />
 * (batch hero) + useGenerationJob SSE hook, composing the lifecycle:
 *   1. job queued/reading_campaign  -> the GenerationLoader hero (dot-matrix field)
 *   2. job streaming                -> the hero collapses -> a grid of N
 *      <CreativeSkeleton /> cards (same DraftsPage/Grid slots, no jump)
 *   3. each variant lands           -> that skeleton morphs IN PLACE into a real
 *      <AssetCard /> (S5)
 *   4. failed/over_budget/cancelled -> a token retry state, never an error-wall
 *
 * Lives inside the S1 "Generation" Card. The header strip (headContent) shows
 * "k of N ready" + segment Tabs once results exist. No fabricated % — the loader
 * shows a real hairline ONLY when the job's progress.total is known.
 */

import { useEffect, useMemo, useState } from "react";
import GenerationLoader from "@/components/GenerationLoader";
import Card from "@/components/Card";
import Tabs from "@/components/Tabs";
import Button from "@/components/Button";
import type { TabsOption } from "@/types/tabs";
import { useGenerationJob } from "@/hooks/useGenerationJob";
import CreativeSkeleton from "./CreativeSkeleton";
import AssetCard from "./AssetCard";
import { getJob, listAssets, type Asset } from "@/lib/assets";

type GenerationQueueProps = {
    /** the active job (null = nothing generating; show recent/empty) */
    jobId: string | null;
    expectedCount: number;
    assetTypeLabel?: string;
    /** recent assets to show when no job is active (the "wall" persists) */
    recentAssets: Asset[];
    enabled: boolean;
    onOpenAsset: (asset: Asset) => void;
    onApprove: (asset: Asset) => void;
    onUse: (asset: Asset) => void;
    onRetry: () => void;
    onJobDone: () => void;
    onFocusCommand?: () => void;
};

const SEGMENTS: TabsOption[] = [
    { id: 1, name: "All" },
    { id: 2, name: "Approved" },
    { id: 3, name: "Drafts" },
];

const GenerationQueue = ({
    jobId,
    expectedCount,
    assetTypeLabel = "banner",
    recentAssets,
    enabled,
    onOpenAsset,
    onApprove,
    onUse,
    onRetry,
    onJobDone,
    onFocusCommand,
}: GenerationQueueProps) => {
    const job = useGenerationJob(jobId);
    const [segment, setSegment] = useState<TabsOption>(SEGMENTS[0]);
    const [variants, setVariants] = useState<Asset[]>([]);
    const [collapsed, setCollapsed] = useState(false);

    // reset per job
    useEffect(() => {
        setVariants([]);
        setCollapsed(false);
    }, [jobId]);

    // once the job is streaming/succeeded, pull the job's asset ids -> the grid
    useEffect(() => {
        if (!jobId) return;
        if (job.state === "completed" || (job.progress && job.progress.done > 0)) {
            getJob(jobId)
                .then(async (j) => {
                    if (j.asset_ids && j.asset_ids.length) {
                        // fetch the freshly-created assets for this campaign (newest-first)
                        const page = await listAssets({ limit: Math.max(expectedCount, j.asset_ids.length) });
                        const byId = new Map(page.assets.map((a) => [a.id, a]));
                        const ordered = j.asset_ids
                            .map((id) => byId.get(id))
                            .filter((a): a is Asset => !!a);
                        if (ordered.length) setVariants(ordered);
                    }
                })
                .catch(() => {
                    /* dormant / not ready — keep showing skeletons */
                });
        }
        if (job.state === "completed") onJobDone();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [job.state, job.progress?.done, jobId]);

    const isGenerating = !!jobId && job.state === "loading";
    const isFailed = job.state === "failed";

    const filtered = useMemo(() => {
        const src = variants.length ? variants : recentAssets;
        if (segment.id === 2) return src.filter((a) => (a.status || "").toLowerCase() === "approved");
        if (segment.id === 3) return src.filter((a) => (a.status || "").toLowerCase() === "draft");
        return src;
    }, [variants, recentAssets, segment]);

    const doneCount = job.progress?.done ?? variants.length;
    const totalCount = job.progress?.total ?? expectedCount;

    // The header strip — segment Tabs + progress count (only with an active job).
    const head = (
        <div className="flex items-center gap-3 ml-auto">
            {jobId && !isFailed && (
                <span className="text-caption text-t-tertiary max-md:hidden">
                    {doneCount} of {totalCount} ready
                </span>
            )}
            {(variants.length > 0 || recentAssets.length > 0) && (
                <Tabs items={SEGMENTS} value={segment} setValue={setSegment} />
            )}
        </div>
    );

    return (
        <Card title="Generation" headContent={head}>
            <div className="p-1 pt-3 max-lg:px-0">
                {/* PHASE 1+2: the hero loader, until it collapses */}
                {isGenerating && !collapsed && (
                    <div className="px-4 py-2 max-md:px-2">
                        <GenerationLoader
                            state="loading"
                            title={`Creating ${assetTypeLabel}s`}
                            phase={job.phase}
                            progress={job.progress}
                            onCancel={onRetry}
                            onCompleted={() => setCollapsed(true)}
                        />
                    </div>
                )}

                {/* PHASE 2+3: the skeleton/variant grid (same slots, morph in place) */}
                {isGenerating && collapsed && (
                    <div className="flex flex-wrap">
                        {Array.from({ length: expectedCount }).map((_, i) => {
                            const v = variants[i];
                            return v ? (
                                <AssetCard
                                    key={v.id}
                                    asset={v}
                                    onOpen={onOpenAsset}
                                    onApprove={onApprove}
                                    onUse={onUse}
                                />
                            ) : (
                                <div
                                    key={`skel-${i}`}
                                    className="w-[calc(20%-1.5rem)] mt-6 mx-3 max-4xl:w-[calc(25%-1.5rem)] max-[1539px]:w-[calc(33.333%-1.5rem)] max-lg:w-[calc(50%-1.5rem)] max-md:w-[calc(100%-1.5rem)]"
                                >
                                    <CreativeSkeleton
                                        label={`Variant ${i + 1}`}
                                        state={job.progress?.done && job.progress.done > i ? "ready" : "generating"}
                                    />
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* FAILED: a single retry state, never an error-wall */}
                {isFailed && (
                    <div className="px-4 py-2 max-md:px-2">
                        <GenerationLoader
                            state="failed"
                            errorMessage={job.errorMessage || "Couldn't create those."}
                            onRetry={onRetry}
                        />
                    </div>
                )}

                {/* IDLE: the result wall (or the first-visit empty state) */}
                {!jobId && (
                    filtered.length > 0 ? (
                        <div className="flex flex-wrap">
                            {filtered.map((a) => (
                                <AssetCard
                                    key={a.id}
                                    asset={a}
                                    onOpen={onOpenAsset}
                                    onApprove={onApprove}
                                    onUse={onUse}
                                />
                            ))}
                        </div>
                    ) : (
                        <div className="pt-16 pb-20 text-center max-md:py-12">
                            <div className="inline-block mb-2 text-h5">
                                {enabled
                                    ? "Pick a campaign and tell me what to make"
                                    : "Creative Studio is almost ready"}
                            </div>
                            <p className="text-body-2 text-t-secondary max-w-90 mx-auto">
                                {enabled
                                    ? "Your variants stream in here as the engine designs them — angle-labelled, scored, ready to approve."
                                    : "Once your workspace is enabled, your generated creatives appear here."}
                            </p>
                            {enabled && onFocusCommand && (
                                <div className="mt-6">
                                    <Button isBlack onClick={onFocusCommand}>
                                        Start creating
                                    </Button>
                                </div>
                            )}
                        </div>
                    )
                )}
            </div>
        </Card>
    );
};

export default GenerationQueue;
