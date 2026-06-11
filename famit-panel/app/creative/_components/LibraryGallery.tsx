"use client";

/**
 * LibraryGallery (L1 + L3 + L4 + L9 + L10) — the filterable visual wall, and the
 * SAME component reused as an embedded picker. Ports the `Products/DraftsPage`
 * shell verbatim: one `.card`, a head that SWAPS to a bulk-action bar the moment
 * a tile is selected (the `selectedRows.length === 0 ? … : …` ternary), status
 * Tabs, a grid/list view toggle, a NoFound empty state (cs-asset-library §3–6).
 *
 * Grid = the ONE <AssetCard /> (also used in Studio S5). List = a Table view.
 * Filter rail = <FilterRail /> → query params + applied-filter chips. Bulk bar =
 * Approve / Use → / Archive over a string-id selection (assets are ca_<hex>, so
 * selection is local string-keyed, not the numeric useSelection hook).
 *
 * `selectMode="pick"` turns it into the cross-platform chooser (L9): clicking a
 * card returns it to the host instead of opening the drawer. Dormant-safe: an
 * empty/disabled surface renders the calm empty state, never an error-wall.
 */

import { useEffect, useMemo, useState } from "react";
import Search from "@/components/Search";
import Tabs from "@/components/Tabs";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import type { TabsOption } from "@/types/tabs";
import type { SelectOption } from "@/types/select";
import AssetCard from "./AssetCard";
import FilterRail, { AssetFilters, filtersToQuery, SORT_OPTS } from "./FilterRail";
import {
    listAssets,
    approveAsset,
    attachAsset,
    assetRawUrl,
    angleLabel,
    statusLabel,
    statusVariant,
    type Asset,
} from "@/lib/assets";

type LibraryGalleryProps = {
    /** "browse" opens the detail drawer; "pick" returns the asset to the host. */
    selectMode?: "browse" | "pick";
    onOpen?: (asset: Asset) => void;
    onPick?: (asset: Asset) => void;
    onUse?: (asset: Asset) => void;
    campaignOptions: SelectOption[];
    /** scope the picker (e.g. WA pre-filters to platform=whatsapp). */
    presetFilters?: AssetFilters;
    /** the gallery owns its own selection unless told otherwise. */
    showBulk?: boolean;
};

const STATUS_TABS: TabsOption[] = [
    { id: 1, name: "All" },
    { id: 2, name: "Approved" },
    { id: 3, name: "Drafts" },
    { id: 4, name: "Used" },
    { id: 5, name: "Winners" },
];

const VIEW_TABS: TabsOption[] = [
    { id: 1, name: "grid" },
    { id: 2, name: "list" },
];

const PAGE = 20;

const LibraryGallery = ({
    selectMode = "browse",
    onOpen,
    onPick,
    onUse,
    campaignOptions,
    presetFilters,
    showBulk = true,
}: LibraryGalleryProps) => {
    const [search, setSearch] = useState("");
    const [statusTab, setStatusTab] = useState<TabsOption>(STATUS_TABS[0]);
    const [view, setView] = useState<TabsOption>(VIEW_TABS[0]);
    const [filterOpen, setFilterOpen] = useState(false);
    const [filters, setFilters] = useState<AssetFilters>(presetFilters || { sort: SORT_OPTS[0] });

    const [assets, setAssets] = useState<Asset[]>([]);
    const [total, setTotal] = useState(0);
    const [offset, setOffset] = useState(0);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [error, setError] = useState(false);
    const [selected, setSelected] = useState<string[]>([]);

    // the status tab maps onto the status param (quick filters, no rail needed)
    const statusFromTab = useMemo(() => {
        switch (statusTab.id) {
            case 2:
                return { status: "approved" as const };
            case 3:
                return { status: "draft" as const };
            case 4:
                return { status: "used" as const };
            case 5:
                return { winners: true };
            default:
                return {};
        }
    }, [statusTab]);

    const baseQuery = useMemo(
        () => ({ ...filtersToQuery(filters), ...statusFromTab, q: search || undefined }),
        [filters, statusFromTab, search]
    );

    // fetch page 0 on any query change
    useEffect(() => {
        let active = true;
        setLoading(true);
        setError(false);
        setOffset(0);
        listAssets({ ...baseQuery, limit: PAGE, offset: 0 })
            .then((page) => {
                if (!active) return;
                setAssets(page.assets);
                setTotal(page.total);
            })
            .catch(() => active && setError(true))
            .finally(() => active && setLoading(false));
        return () => {
            active = false;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [JSON.stringify(baseQuery)]);

    const loadMore = async () => {
        const next = offset + PAGE;
        setLoadingMore(true);
        try {
            const page = await listAssets({ ...baseQuery, limit: PAGE, offset: next });
            setAssets((prev) => [...prev, ...page.assets]);
            setOffset(next);
        } catch {
            /* keep what we have */
        } finally {
            setLoadingMore(false);
        }
    };

    const toggleSelect = (id: string) =>
        setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    const deselect = () => setSelected([]);

    const bulkApprove = async () => {
        await Promise.allSettled(selected.map((id) => approveAsset(id)));
        setAssets((prev) =>
            prev.map((a) => (selected.includes(a.id) ? { ...a, status: "approved" } : a))
        );
        deselect();
    };
    const bulkArchive = async () => {
        // Archive = a status flip (NO hard delete — backend grants no DELETE).
        await Promise.allSettled(
            selected.map((id) => attachAsset(id, "workflow").catch(() => undefined))
        );
        // reflect locally as archived; the next fetch reconciles
        setAssets((prev) =>
            prev.map((a) => (selected.includes(a.id) ? { ...a, status: "archived" } : a))
        );
        deselect();
    };

    const hasFilters =
        !!baseQuery.campaign ||
        !!baseQuery.platform ||
        !!baseQuery.kind ||
        !!baseQuery.size ||
        !!baseQuery.angle ||
        !!baseQuery.winners ||
        !!baseQuery.from ||
        !!baseQuery.to;

    const clearFilters = () => {
        setFilters({ sort: SORT_OPTS[0] });
        setStatusTab(STATUS_TABS[0]);
    };

    const showSelectionHead = showBulk && selected.length > 0;
    const isFiltered = !!search || hasFilters || statusTab.id !== 1;

    return (
        <div className="card">
            {/* HEAD — browse state OR bulk-bar (the DraftsPage swap) */}
            {showSelectionHead ? (
                <div className="flex items-center max-md:flex-wrap max-md:gap-2">
                    <div className="mr-6 pl-5 text-h6 max-lg:pl-3">
                        {selected.length} asset{selected.length !== 1 ? "s" : ""} selected
                    </div>
                    <Button className="mr-auto" isStroke onClick={deselect}>
                        Deselect
                    </Button>
                    <Button isStroke className="mr-2" icon="check" onClick={bulkApprove}>
                        Approve {selected.length}
                    </Button>
                    {onUse && (
                        <Button
                            isStroke
                            className="mr-2"
                            icon="send"
                            onClick={() => {
                                const first = assets.find((a) => a.id === selected[0]);
                                if (first) onUse(first);
                            }}
                        >
                            Use →
                        </Button>
                    )}
                    <Button isStroke icon="trash" onClick={bulkArchive}>
                        Archive
                    </Button>
                </div>
            ) : (
                <div className="flex items-center gap-3 max-md:flex-wrap">
                    <div className="pl-5 text-h6 max-lg:pl-3 max-md:w-full">Assets</div>
                    <Search
                        className="w-64 max-md:w-full"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search assets"
                        isGray
                    />
                    <Tabs
                        className="mr-auto max-md:w-full max-md:overflow-x-auto"
                        items={STATUS_TABS}
                        value={statusTab}
                        setValue={setStatusTab}
                    />
                    <Button isWhite isCircle icon="filters" onClick={() => setFilterOpen(true)} />
                    <Tabs items={VIEW_TABS} value={view} setValue={setView} isOnlyIcon />
                </div>
            )}

            {/* applied-filter chips */}
            {hasFilters && !showSelectionHead && (
                <div className="flex flex-wrap items-center gap-2 px-5 mt-3 max-lg:px-3">
                    {chipLabels(filters).map((c) => (
                        <Badge key={c} variant="neutral">
                            {c}
                        </Badge>
                    ))}
                    <button
                        className="text-caption text-t-secondary transition-colors hover:text-t-primary"
                        onClick={clearFilters}
                    >
                        Clear all
                    </button>
                </div>
            )}

            {/* BODY */}
            <div className="p-1 pt-3 max-lg:px-0">
                {loading ? (
                    <div className="py-16">
                        <Spinner />
                    </div>
                ) : error ? (
                    <div className="px-5 py-12 text-center max-lg:px-3">
                        <p className="text-body-2 text-t-secondary">
                            Couldn&apos;t load assets right now. Try again in a moment.
                        </p>
                    </div>
                ) : assets.length === 0 ? (
                    <EmptyState filtered={isFiltered} onClear={clearFilters} />
                ) : view.id === 1 ? (
                    <>
                        <div className="flex flex-wrap">
                            {assets.map((a) => (
                                <AssetCard
                                    key={a.id}
                                    asset={a}
                                    selectMode={selectMode}
                                    selected={selected.includes(a.id)}
                                    onSelect={showBulk ? () => toggleSelect(a.id) : undefined}
                                    onOpen={onOpen}
                                    onPick={onPick}
                                    onUse={onUse}
                                />
                            ))}
                        </div>
                        {assets.length < total && (
                            <div className="flex justify-center pt-6 pb-2">
                                <Button isStroke onClick={loadMore} disabled={loadingMore}>
                                    {loadingMore ? "Loading…" : "Load more"}
                                </Button>
                            </div>
                        )}
                    </>
                ) : (
                    <ListView
                        assets={assets}
                        onOpen={selectMode === "pick" ? onPick : onOpen}
                    />
                )}
            </div>

            <FilterRail
                open={filterOpen}
                onClose={() => setFilterOpen(false)}
                value={filters}
                onApply={setFilters}
                campaignOptions={campaignOptions}
            />
        </div>
    );
};

const EmptyState = ({ filtered, onClear }: { filtered: boolean; onClear: () => void }) => (
    <div className="pt-16 pb-20 text-center max-md:py-12">
        <div className="inline-block mb-2 text-h5">
            {filtered ? "No assets match these filters" : "No assets yet"}
        </div>
        <p className="text-body-2 text-t-secondary max-w-90 mx-auto">
            {filtered
                ? "Try a different filter, or clear them to see everything."
                : "Create your first creative in the Studio — it lands here, ready to reuse everywhere."}
        </p>
        <div className="mt-6">
            {filtered ? (
                <Button isStroke onClick={onClear}>
                    Clear filters
                </Button>
            ) : (
                <Button as="link" href="/creative" isBlack>
                    Open Studio
                </Button>
            )}
        </div>
    </div>
);

const ListView = ({
    assets,
    onOpen,
}: {
    assets: Asset[];
    onOpen?: (asset: Asset) => void;
}) => (
    <Table
        cellsThead={
            <>
                <th>Asset</th>
                <th className="max-md:hidden">Platform / Size</th>
                <th className="max-md:hidden">Angle</th>
                <th>Status</th>
                <th className="max-md:hidden">Score</th>
                <th className="max-md:hidden">Created</th>
            </>
        }
    >
        {assets.map((a) => (
            <TableRow
                className="cursor-pointer hover:[&_td]:bg-b-surface1/60 dark:hover:[&_td]:bg-shade-04/30"
                key={a.id}
                onClick={() => onOpen?.(a)}
            >
                <td>
                    <div className="flex items-center gap-3">
                        <span
                            className="size-10 shrink-0 rounded-xl bg-cover bg-center bg-b-surface1 dark:bg-shade-04/40"
                            style={{
                                backgroundImage: `url(${a.thumb_url || assetRawUrl(a.id, a.current_version_id)})`,
                            }}
                        />
                        <span className="text-body-2 text-t-primary line-clamp-1">
                            {a.headline || "Untitled creative"}
                        </span>
                    </div>
                </td>
                <td className="max-md:hidden text-t-secondary">
                    {[a.platform, a.size].filter(Boolean).join(" · ") || "—"}
                </td>
                <td className="max-md:hidden">
                    <Badge variant="neutral">{angleLabel(a.angle)}</Badge>
                </td>
                <td>
                    <Badge variant={statusVariant(a.status)} dot>
                        {statusLabel(a.status)}
                    </Badge>
                </td>
                <td className="max-md:hidden">
                    {typeof a.score?.overall === "number" ? `${a.score.overall}` : "—"}
                </td>
                <td className="max-md:hidden text-t-secondary">{fmtDate(a.created_at)}</td>
            </TableRow>
        ))}
    </Table>
);

function chipLabels(f: AssetFilters): string[] {
    const out: string[] = [];
    const add = (o?: SelectOption) => o && o.id !== 0 && out.push(o.name);
    add(f.campaign);
    add(f.platform);
    add(f.kind);
    add(f.size);
    add(f.angle);
    if (f.winners) out.push("Winners");
    if (f.from || f.to) out.push([f.from, f.to].filter(Boolean).join(" → "));
    return out;
}

function fmtDate(iso?: string): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default LibraryGallery;
