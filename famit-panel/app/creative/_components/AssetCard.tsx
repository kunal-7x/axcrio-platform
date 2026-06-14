"use client";

/**
 * AssetCard — the ONE rich creative tile, reused EVERYWHERE.
 *
 * The same card renders in Studio variants (S5), the Library grid (L1/L3), and
 * every embedded picker (L9) — one component so the product looks identical and
 * premium throughout (cs-asset-library §5). Ports `components/GridProduct`'s
 * anatomy verbatim (corner Checkbox on hover/selection, Image preview, angle/
 * status Badges over the image, a title row with a score chip, a default info
 * row, a hover-reveal actions row) reskinned to the creative record.
 *
 * Token-pure: angle/status colours via Badge variants + label classes, zero raw
 * hex. The preview uses the asset's raw-bytes URL (local_path never exposed).
 */

import { useState } from "react";
import AssetMedia from "./AssetMedia";
import Checkbox from "@/components/Checkbox";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import {
    assetRawUrl,
    angleLabel,
    statusLabel,
    statusVariant,
    isVideoAsset,
    fmtDuration,
    type Asset,
} from "@/lib/assets";

type AssetCardProps = {
    asset: Asset;
    /** selection (L4 bulk / picker). When omitted, the corner checkbox is hidden. */
    selected?: boolean;
    onSelect?: (enabled: boolean) => void;
    /** open the detail drawer (S6 / L5). */
    onOpen?: (asset: Asset) => void;
    /** pick-mode (L9): clicking the card selects+returns it to the host. */
    selectMode?: "browse" | "pick";
    onPick?: (asset: Asset) => void;
    /** hover actions (S5/L3 grammar). Each optional so callers compose the set. */
    onApprove?: (asset: Asset) => void;
    onEdit?: (asset: Asset) => void;
    onVersions?: (asset: Asset) => void;
    onUse?: (asset: Asset) => void;
};

const AssetCard = ({
    asset,
    selected,
    onSelect,
    onOpen,
    selectMode = "browse",
    onPick,
    onApprove,
    onEdit,
    onVersions,
    onUse,
}: AssetCardProps) => {
    const [visible, setVisible] = useState(false);

    const isVideo = isVideoAsset(asset);
    // For a video the GRID shows the presigned POSTER (no clip bytes — egress-safe);
    // the clip src is fetched only on hover-preview. For an image it's the usual src.
    const src = asset.url || assetRawUrl(asset.id, asset.current_version_id);
    const poster = asset.poster_url || asset.thumb_url || (isVideo ? undefined : src);
    const score = asset.score?.overall;
    const isApproved = (asset.status || "").toLowerCase() === "approved";

    const handleCardClick = () => {
        setVisible((v) => !v);
        if (selectMode === "pick") {
            onPick?.(asset);
        } else {
            onOpen?.(asset);
        }
    };

    // stop a control click from bubbling to the card open/pick handler
    const stop = (e: React.MouseEvent) => e.stopPropagation();

    return (
        <div
            className="group w-[calc(20%-1.5rem)] mt-6 mx-3 max-4xl:w-[calc(25%-1.5rem)] max-[1539px]:w-[calc(33.333%-1.5rem)] max-lg:w-[calc(50%-1.5rem)] max-md:w-[calc(100%-1.5rem)]"
            onClick={handleCardClick}
        >
            <div className="relative h-57.5">
                {onSelect && (
                    <div className="absolute top-4 left-4 z-5" onClick={stop}>
                        <Checkbox
                            className={`invisible opacity-0 transition-all group-hover:visible group-hover:opacity-100 max-md:hidden data-[checked]:!visible data-[checked]:!opacity-100 ${
                                visible ? "max-lg:visible max-lg:opacity-100" : ""
                            }`}
                            classTick="bg-b-surface2"
                            checked={selected || false}
                            onChange={onSelect}
                        />
                    </div>
                )}

                {/* angle badge (top-left) */}
                <div className="absolute top-3 left-3 z-2 group-hover:left-13 transition-all">
                    <Badge variant="neutral">{angleLabel(asset.angle)}</Badge>
                </div>
                {/* status pip (top-right) */}
                <div className="absolute top-3 right-3 z-2">
                    <Badge variant={statusVariant(asset.status)} dot>
                        {statusLabel(asset.status)}
                    </Badge>
                </div>

                <AssetMedia
                    src={src}
                    poster={poster}
                    isVideo={isVideo}
                    mode="grid"
                    alt={asset.headline || "Creative asset"}
                    rounded="rounded-3xl"
                    durationLabel={isVideo ? fmtDuration(asset.duration_s) : undefined}
                    withAudio={isVideo ? asset.with_audio : undefined}
                />
            </div>

            {/* title + score */}
            <div className="flex items-start mt-3">
                <div className="grow pt-0.5 text-sub-title-1 line-clamp-1">
                    {asset.headline || "Untitled creative"}
                </div>
                {typeof score === "number" && (
                    <div className="shrink-0 ml-3 label label-green">{score}</div>
                )}
            </div>

            {/* default info row <-> hover actions (the GridProduct swap) */}
            <div className="relative min-h-6 mt-1">
                <div
                    className={`absolute top-0 left-0 flex items-center gap-2 transition-all group-hover:invisible group-hover:opacity-0 ${
                        visible ? "max-lg:invisible max-lg:opacity-0" : ""
                    }`}
                >
                    <span className="text-caption text-t-secondary">
                        {[asset.platform, asset.size].filter(Boolean).join(" · ") || "—"}
                    </span>
                    {asset.usage && asset.usage.length > 0 && (
                        <span className="flex items-center gap-1">
                            {asset.usage.slice(0, 3).map((u, i) => (
                                <Badge key={`${u.channel}-${i}`} variant="info">
                                    {usedInLabel(u.channel)}
                                </Badge>
                            ))}
                        </span>
                    )}
                </div>
                <div
                    className={`flex flex-wrap gap-2 mt-0.5 -ml-1 invisible opacity-0 transition-all group-hover:visible group-hover:opacity-100 ${
                        visible ? "max-lg:visible max-lg:opacity-100" : ""
                    }`}
                    onClick={stop}
                >
                    {onApprove && !isApproved && (
                        <button className="action" onClick={() => onApprove(asset)}>
                            <Icon name="check" /> Approve
                        </button>
                    )}
                    {onEdit && (
                        <button className="action" onClick={() => onEdit(asset)}>
                            <Icon name="edit" /> Edit
                        </button>
                    )}
                    {onVersions && (
                        <button className="action" onClick={() => onVersions(asset)}>
                            <Icon name="layers" /> Versions
                        </button>
                    )}
                    {onUse && (
                        <button className="action" onClick={() => onUse(asset)}>
                            <Icon name="send" /> Use
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

function usedInLabel(channel: string): string {
    switch ((channel || "").toLowerCase()) {
        case "whatsapp":
            return "WA";
        case "meta_ads":
            return "Meta";
        case "landing":
            return "Funnel";
        case "workflow":
            return "Flow";
        default:
            return channel;
    }
}

export default AssetCard;
