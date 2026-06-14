"use client";

/**
 * FilterRail (L2) — the founder's named facets. A right `Modal isSlidePanel`
 * (the ExploreCreatorsPage/Filters grammar) with a scrollable stack of Selects +
 * a "Winners only" Switch + a Reset/Apply footer (cs-asset-library §4). Only the
 * facet set is ours: campaign / platform / type / status / winners / date / size
 * / angle + sort. The rail is pure UI state → one fetch on Apply.
 *
 * Token-pure; reuses Select / Switch / Field / Button / Modal. The applied-filter
 * chips render in the gallery head (LibraryGallery), not here.
 */

import { useEffect, useState } from "react";
import Modal from "@/components/Modal";
import Select from "@/components/Select";
import Switch from "@/components/Switch";
import Field from "@/components/Field";
import Button from "@/components/Button";
import type { SelectOption } from "@/types/select";

export type AssetFilters = {
    campaign?: SelectOption;
    platform?: SelectOption;
    kind?: SelectOption;
    status?: SelectOption;
    size?: SelectOption;
    angle?: SelectOption;
    sort?: SelectOption;
    winners?: boolean;
    from?: string;
    to?: string;
};

type FilterRailProps = {
    open: boolean;
    onClose: () => void;
    value: AssetFilters;
    onApply: (filters: AssetFilters) => void;
    campaignOptions: SelectOption[];
};

export const PLATFORM_OPTS: SelectOption[] = [
    { id: 0, name: "All platforms" },
    { id: 1, name: "Meta" },
    { id: 2, name: "WhatsApp" },
    { id: 3, name: "IG Story" },
    { id: 4, name: "Google" },
    { id: 5, name: "Carousel" },
    { id: 6, name: "Hero" },
];

export const KIND_OPTS: SelectOption[] = [
    { id: 0, name: "All types" },
    { id: 1, name: "Banner" },
    { id: 2, name: "Image" },
    { id: 3, name: "Social" },
    { id: 4, name: "Offer" },
    { id: 5, name: "Poster" },
    { id: 6, name: "Product" },
    { id: 7, name: "Logo" },
    { id: 8, name: "Video" },
];

export const STATUS_OPTS: SelectOption[] = [
    { id: 0, name: "All statuses" },
    { id: 1, name: "Draft" },
    { id: 2, name: "Needs review" },
    { id: 3, name: "Approved" },
    { id: 4, name: "Rejected" },
    { id: 5, name: "Used" },
    { id: 6, name: "Archived" },
];

export const SIZE_OPTS: SelectOption[] = [
    { id: 0, name: "All sizes" },
    { id: 1, name: "1:1 · 1080×1080" },
    { id: 2, name: "4:5" },
    { id: 3, name: "9:16 · Story" },
    { id: 4, name: "16:9" },
    { id: 5, name: "Google display" },
    { id: 6, name: "Hero" },
];

export const ANGLE_OPTS: SelectOption[] = [
    { id: 0, name: "All angles" },
    { id: 1, name: "Price" },
    { id: 2, name: "Location" },
    { id: 3, name: "Emotion" },
    { id: 4, name: "Urgency" },
    { id: 5, name: "Trust" },
    { id: 6, name: "Problem-solution" },
    { id: 7, name: "Benefit" },
    { id: 8, name: "Offer" },
    { id: 9, name: "Retargeting" },
    { id: 10, name: "Comparison" },
];

export const SORT_OPTS: SelectOption[] = [
    { id: 1, name: "Newest" },
    { id: 2, name: "Oldest" },
    { id: 3, name: "Best score" },
    { id: 4, name: "Best CTR" },
    { id: 5, name: "Most used" },
    { id: 6, name: "Cheapest" },
];

const FilterRail = ({ open, onClose, value, onApply, campaignOptions }: FilterRailProps) => {
    const campaignFacet: SelectOption[] = [{ id: 0, name: "All campaigns" }, ...campaignOptions];

    const [draft, setDraft] = useState<AssetFilters>(value);

    // re-seed the draft each time the rail opens (so an un-applied edit resets)
    useEffect(() => {
        if (open) setDraft(value);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const set = (patch: Partial<AssetFilters>) => setDraft((d) => ({ ...d, ...patch }));

    const reset = () => {
        const cleared: AssetFilters = { sort: SORT_OPTS[0] };
        setDraft(cleared);
    };

    return (
        <Modal open={open} onClose={onClose} isSlidePanel classWrapper="!w-96 max-md:!w-full">
            <div className="flex flex-col h-svh">
                <div className="px-6 pt-6 pb-3">
                    <div className="text-h6">Filters</div>
                </div>
                <div className="grow overflow-y-auto px-6 pb-4 space-y-5 scrollbar-none">
                    <Select
                        label="Sort by"
                        value={draft.sort || SORT_OPTS[0]}
                        onChange={(v) => set({ sort: v })}
                        options={SORT_OPTS}
                    />
                    <Select
                        label="Campaign"
                        value={draft.campaign || campaignFacet[0]}
                        onChange={(v) => set({ campaign: v })}
                        options={campaignFacet}
                    />
                    <Select
                        label="Platform"
                        value={draft.platform || PLATFORM_OPTS[0]}
                        onChange={(v) => set({ platform: v })}
                        options={PLATFORM_OPTS}
                    />
                    <Select
                        label="Asset type"
                        value={draft.kind || KIND_OPTS[0]}
                        onChange={(v) => set({ kind: v })}
                        options={KIND_OPTS}
                    />
                    <Select
                        label="Status"
                        value={draft.status || STATUS_OPTS[0]}
                        onChange={(v) => set({ status: v })}
                        options={STATUS_OPTS}
                    />
                    <Select
                        label="Size"
                        value={draft.size || SIZE_OPTS[0]}
                        onChange={(v) => set({ size: v })}
                        options={SIZE_OPTS}
                    />
                    <Select
                        label="Angle"
                        value={draft.angle || ANGLE_OPTS[0]}
                        onChange={(v) => set({ angle: v })}
                        options={ANGLE_OPTS}
                    />
                    <div className="grid grid-cols-2 gap-3">
                        <Field
                            label="From"
                            type="date"
                            value={draft.from || ""}
                            onChange={(e) => set({ from: e.target.value })}
                        />
                        <Field
                            label="To"
                            type="date"
                            value={draft.to || ""}
                            onChange={(e) => set({ to: e.target.value })}
                        />
                    </div>
                    <div className="flex items-center justify-between pt-1">
                        <span className="text-button">Winners only</span>
                        <Switch
                            checked={!!draft.winners}
                            onChange={(c) => set({ winners: c })}
                        />
                    </div>
                </div>
                <div className="shrink-0 flex items-center gap-3 px-6 py-4 border-t border-s-subtle">
                    <Button isStroke className="flex-1" onClick={reset}>
                        Reset
                    </Button>
                    <Button
                        isBlack
                        className="flex-1"
                        onClick={() => {
                            onApply(draft);
                            onClose();
                        }}
                    >
                        Apply
                    </Button>
                </div>
            </div>
        </Modal>
    );
};

/** Translate the UI facet draft into the lib/assets AssetQuery params. */
export function filtersToQuery(f: AssetFilters): {
    campaign?: string;
    platform?: string;
    kind?: string;
    status?: string;
    size?: string;
    angle?: string;
    sort?: string;
    winners?: boolean;
    from?: string;
    to?: string;
} {
    const pick = (o?: SelectOption) => (o && o.id !== 0 ? o.name : undefined);
    const sortMap: Record<number, string> = {
        1: "newest",
        2: "oldest",
        3: "best_score",
        4: "best_ctr",
        5: "most_used",
        6: "cheapest",
    };
    const statusMap: Record<string, string> = {
        Draft: "draft",
        "Needs review": "needs_review",
        Approved: "approved",
        Rejected: "rejected",
        Used: "used",
        Archived: "archived",
    };
    const statusName = pick(f.status);
    return {
        campaign: pick(f.campaign),
        platform: pick(f.platform)?.toLowerCase(),
        kind: pick(f.kind)?.toLowerCase(),
        status: statusName ? statusMap[statusName] : undefined,
        size: pick(f.size),
        angle: pick(f.angle)?.toLowerCase().replace(/[\s-]+/g, "_"),
        sort: f.sort ? sortMap[f.sort.id] : undefined,
        winners: f.winners || undefined,
        from: f.from || undefined,
        to: f.to || undefined,
    };
}

export default FilterRail;
