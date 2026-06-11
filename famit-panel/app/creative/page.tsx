"use client";

/**
 * S1 — THE STUDIO WORKSPACE (flagship). One screen where the vendor commands a
 * generation and watches it happen (cs-workspace §3). Two-column reference
 * grammar (HomePage `col-left`/`col-right`): Create + Generation on the left;
 * Campaign context + Recent assets on the right.
 *
 *   col-left  : <CreatePanel> (S2) + <GenerationQueue> (S4 loader → S5 variants)
 *   col-right : <CampaignContext> (S3 provenance) + Recent assets mini-wall
 *
 * Dormant-safe: the page calls GET /api/assets/status first and renders a calm
 * <DormantCard> body when disabled — byte-identical-to-live (§17). All data binds
 * to the LIVE /api/assets/*. Single <Layout title="Creative Studio">, no
 * PageHeader, Inter Display, zero raw hex.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Spinner from "@/components/Spinner";
import useAssetStatus from "./_hooks/useAssetStatus";
import DormantCard from "./_components/DormantCard";
import CreatePanel from "./_components/CreatePanel";
import CampaignContext from "./_components/CampaignContext";
import GenerationQueue from "./_components/GenerationQueue";
import AssetDetail from "./_components/AssetDetail";
import UsePicker from "./_components/UsePicker";
import AssetCard from "./_components/AssetCard";
import { getCampaigns, type Campaign } from "@/lib/api";
import {
    getBrandKits,
    listAssets,
    approveAsset,
    type Asset,
    type BrandKit,
    type GenerateResult,
} from "@/lib/assets";

const Page = () => {
    const router = useRouter();
    const { enabled, loading: statusLoading } = useAssetStatus();

    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [brandKit, setBrandKit] = useState<BrandKit | null>(null);
    const [activeCampaign, setActiveCampaign] = useState<string | undefined>(undefined);

    const [jobId, setJobId] = useState<string | null>(null);
    const [jobMeta, setJobMeta] = useState<{ count: number; assetType: string }>({
        count: 5,
        assetType: "Banner",
    });

    const [recent, setRecent] = useState<Asset[]>([]);
    const [detailAsset, setDetailAsset] = useState<Asset | null>(null);
    const [detailOpen, setDetailOpen] = useState(false);
    const [useAsset, setUseAsset] = useState<Asset | null>(null);
    const [usePickerOpen, setUsePickerOpen] = useState(false);

    // load campaigns + brand kit + recent assets once enabled
    useEffect(() => {
        getCampaigns()
            .then(({ campaigns }) => setCampaigns(campaigns))
            .catch(() => setCampaigns([]));
    }, []);

    useEffect(() => {
        if (!enabled) return;
        getBrandKits().then(({ brand_kits }) => setBrandKit(brand_kits[0] || null));
        refreshRecent();
    }, [enabled]);

    const refreshRecent = () => {
        listAssets({ limit: 6, sort: "newest" })
            .then((page) => setRecent(page.assets))
            .catch(() => setRecent([]));
    };

    const onGenerated = (result: GenerateResult, meta: { count: number; assetType: string }) => {
        setJobMeta(meta);
        setJobId(result.job_id);
    };

    const openDetail = (a: Asset) => {
        setDetailAsset(a);
        setDetailOpen(true);
    };

    const handleApprove = async (a: Asset) => {
        try {
            await approveAsset(a.id);
            setRecent((prev) => prev.map((x) => (x.id === a.id ? { ...x, status: "approved" } : x)));
        } catch {
            /* surfaced in the detail drawer normally; the card approve is best-effort */
        }
    };

    const handleUse = (a: Asset) => {
        setUseAsset(a);
        setUsePickerOpen(true);
    };

    // ---- DORMANT path: a calm coming-soon body (byte-identical-to-live) ----
    if (statusLoading) {
        return (
            <Layout title="Creative Studio">
                <div className="py-24">
                    <Spinner />
                </div>
            </Layout>
        );
    }

    return (
        <Layout title="Creative Studio">
            {!enabled ? (
                <DormantCard />
            ) : (
                <>
                    <div className="flex max-lg:block">
                        <div className="col-left">
                            <CreatePanel
                                campaigns={campaigns}
                                enabled={enabled}
                                brandKitId={brandKit?.id}
                                onCampaignChange={setActiveCampaign}
                                onGenerated={onGenerated}
                                onUploadReference={undefined}
                            />
                            <GenerationQueue
                                jobId={jobId}
                                expectedCount={jobMeta.count}
                                assetTypeLabel={jobMeta.assetType.toLowerCase()}
                                recentAssets={recent}
                                enabled={enabled}
                                onOpenAsset={openDetail}
                                onApprove={handleApprove}
                                onUse={handleUse}
                                onRetry={() => setJobId(null)}
                                onJobDone={() => {
                                    refreshRecent();
                                    setJobId(null);
                                }}
                            />
                        </div>
                        <div className="col-right">
                            <CampaignContext
                                campaignId={activeCampaign}
                                brandKit={brandKit}
                                onEditBrand={() => router.push("/creative/brand")}
                            />
                            <Card
                                title="Recent assets"
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
                                            Your latest creatives show up here.
                                        </p>
                                    </div>
                                ) : (
                                    <div className="flex flex-wrap px-2">
                                        {recent.slice(0, 4).map((a) => (
                                            <AssetCard key={a.id} asset={a} onOpen={openDetail} />
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
                        onChanged={(a) => {
                            setRecent((prev) => prev.map((x) => (x.id === a.id ? a : x)));
                        }}
                    />
                    <UsePicker
                        asset={useAsset}
                        open={usePickerOpen}
                        onClose={() => setUsePickerOpen(false)}
                        onAttached={() => refreshRecent()}
                    />
                </>
            )}
        </Layout>
    );
};

export default Page;
