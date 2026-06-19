"use client";

/**
 * S9 / L1–L10 — THE ASSET LIBRARY. The canonical filterable gallery of every
 * asset (cs-asset-library §3). Thin page shell: the heavy lifting (gallery, card,
 * filter rail, bulk bar, list view, applied-filter chips, all states) lives in
 * <LibraryGallery>, which is the SAME component reused as the embedded picker
 * (L9) on the WhatsApp/Ads/Workflow surfaces.
 *
 * Opens the L5 detail drawer (<AssetDetail>) on card click, and the L7 "Use →"
 * picker (<UsePicker>) on the Use action. Dormant-safe: <LibraryGallery> resolves
 * a 503 to its empty state; this page also shows the calm <DormantCard> when the
 * whole surface is off. Single <Layout title="Asset Library">, no PageHeader.
 */

import { useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Spinner from "@/components/Spinner";
import Button from "@/components/Button";
import useAssetStatus from "../_hooks/useAssetStatus";
import DormantCard from "../_components/DormantCard";
import LibraryGallery from "../_components/LibraryGallery";
import AssetDetail from "../_components/AssetDetail";
import UsePicker from "../_components/UsePicker";
import UploadAssetModal from "../_components/UploadAssetModal";
import { getCampaigns, type Campaign } from "@/lib/api";
import type { SelectOption } from "@/types/select";
import type { Asset } from "@/lib/assets";

const Page = () => {
    const { enabled, loading } = useAssetStatus();
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);

    const [detailAsset, setDetailAsset] = useState<Asset | null>(null);
    const [detailOpen, setDetailOpen] = useState(false);
    const [useAsset, setUseAsset] = useState<Asset | null>(null);
    const [usePickerOpen, setUsePickerOpen] = useState(false);
    // Upload-your-own-media control + a token bumped after a successful upload to
    // force the gallery to re-fetch so the new asset appears.
    const [uploadOpen, setUploadOpen] = useState(false);
    const [reloadToken, setReloadToken] = useState(0);

    useEffect(() => {
        getCampaigns()
            .then(({ campaigns }) => setCampaigns(campaigns))
            .catch(() => setCampaigns([]));
    }, []);

    const campaignOptions: SelectOption[] = useMemo(
        () => campaigns.map((c, i) => ({ id: i + 1, name: c.name })),
        [campaigns]
    );

    const openDetail = (a: Asset) => {
        setDetailAsset(a);
        setDetailOpen(true);
    };
    const openUse = (a: Asset) => {
        setUseAsset(a);
        setUsePickerOpen(true);
    };

    return (
        <Layout title="Asset Library">
            {loading ? (
                <div className="py-24">
                    <Spinner />
                </div>
            ) : !enabled ? (
                <DormantCard
                    title="Your asset library activates with Creative Studio"
                    message="Every creative the AI generates lands here — filterable, comparable across versions, and reusable across WhatsApp, ads and workflows."
                    icon="grid"
                />
            ) : (
                <>
                    <LibraryGallery
                        campaignOptions={campaignOptions}
                        onOpen={openDetail}
                        onUse={openUse}
                        reloadToken={reloadToken}
                        headerExtra={
                            <Button
                                isStroke
                                icon="upload"
                                onClick={() => setUploadOpen(true)}
                            >
                                Upload
                            </Button>
                        }
                    />
                    <AssetDetail
                        asset={detailAsset}
                        open={detailOpen}
                        onClose={() => setDetailOpen(false)}
                    />
                    <UsePicker
                        asset={useAsset}
                        open={usePickerOpen}
                        onClose={() => setUsePickerOpen(false)}
                    />
                    <UploadAssetModal
                        open={uploadOpen}
                        onClose={() => setUploadOpen(false)}
                        onUploaded={() => setReloadToken((n) => n + 1)}
                        campaignOptions={campaignOptions}
                    />
                </>
            )}
        </Layout>
    );
};

export default Page;
