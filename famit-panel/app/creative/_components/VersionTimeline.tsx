"use client";

/**
 * VersionTimeline (L6 / S6 version strip) — edits as versions, rollback.
 *
 * Backend models every edit/regenerate as a NEW immutable version; the original
 * is never overwritten and Restore flips current_version_id (cs-asset-library §8).
 * This is a read+restore+compare surface (NO edit happens here — edits are the
 * Studio NL-edit spend action). A horizontal thumbnail strip (newest-left), each
 * chip captioned with the NL edit_instruction that spawned it, plus a selected-
 * version detail + Restore + Compare. Compare opens a centered Modal showing two
 * previews side-by-side.
 *
 * Token-pure; reuses Image / Badge / Button / Modal. No new components.
 */

import { useState } from "react";
import AssetImage from "./AssetImage";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Icon from "@/components/Icon";
import { assetRawUrl, toCredits, type Asset, type AssetVersion } from "@/lib/assets";

type VersionTimelineProps = {
    asset: Asset;
    onRestore?: (versionId: string) => void;
    restoring?: boolean;
};

const VersionTimeline = ({ asset, onRestore, restoring }: VersionTimelineProps) => {
    const versions = asset.versions || [];
    const currentId = asset.current_version_id;
    const [selectedId, setSelectedId] = useState<string | undefined>(currentId || versions[0]?.id);
    const [compareOpen, setCompareOpen] = useState(false);

    if (versions.length === 0) {
        return (
            <div className="px-1 py-8 text-center">
                <p className="text-body-2 text-t-secondary">No edits yet — this is the original.</p>
            </div>
        );
    }

    const selected = versions.find((v) => v.id === selectedId) || versions[0];
    const current = versions.find((v) => v.id === currentId);
    const isSelectedCurrent = selected.id === currentId;

    const thumb = (v: AssetVersion) => v.thumb_url || v.url || assetRawUrl(asset.id, v.id);

    return (
        <div className="px-1">
            {/* horizontal strip, newest-left */}
            <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-none">
                {versions.map((v) => {
                    const isCurrent = v.id === currentId;
                    const isSel = v.id === selected.id;
                    return (
                        <button
                            key={v.id}
                            className={`shrink-0 w-28 text-left transition-opacity ${
                                isSel ? "opacity-100" : "opacity-70 hover:opacity-100"
                            }`}
                            onClick={() => setSelectedId(v.id)}
                        >
                            <div
                                className={`relative h-24 rounded-2xl overflow-hidden ring-1 ring-inset ${
                                    isSel ? "ring-primary-01/60" : "ring-s-subtle"
                                }`}
                            >
                                <AssetImage
                                    src={thumb(v)}
                                    alt={`Version ${v.version_no}`}
                                    rounded="rounded-2xl"
                                />
                                {isCurrent && (
                                    <div className="absolute top-1.5 left-1.5">
                                        <Badge variant="success">Current</Badge>
                                    </div>
                                )}
                            </div>
                            <div className="mt-1.5 text-caption text-t-primary">
                                v{v.version_no}
                                {v.version_no === 1 ? " · original" : ""}
                            </div>
                            <div className="text-caption text-t-tertiary line-clamp-1">
                                {v.edit_instruction || "generated"}
                            </div>
                        </button>
                    );
                })}
            </div>

            {/* selected version detail */}
            <div className="mt-4 pt-4 border-t border-s-subtle">
                <div className="grid grid-cols-2 gap-2 text-caption">
                    <DetailRow label="Edit" value={selected.edit_instruction || "Original generation"} />
                    <DetailRow label="Model" value={selected.model || "—"} />
                    <DetailRow label="Cost" value={toCredits(selected.cost_minor) || "—"} />
                    <DetailRow label="Created" value={fmtDate(selected.created_at)} />
                </div>
                <div className="flex flex-wrap gap-2 mt-4">
                    {!isSelectedCurrent && onRestore && (
                        <Button
                            isStroke
                            className="!h-10 !px-4 !text-body-2"
                            onClick={() => onRestore(selected.id)}
                            disabled={restoring}
                        >
                            {restoring ? "Restoring…" : "Restore this version"}
                        </Button>
                    )}
                    {current && !isSelectedCurrent && (
                        <Button
                            isStroke
                            className="!h-10 !px-4 !text-body-2"
                            onClick={() => setCompareOpen(true)}
                        >
                            Compare to current
                        </Button>
                    )}
                </div>
            </div>

            {/* compare modal — side by side */}
            {current && (
                <Modal open={compareOpen} onClose={() => setCompareOpen(false)} classWrapper="max-w-180">
                    <div className="text-h6 mb-5">Compare versions</div>
                    <div className="grid grid-cols-2 gap-5 max-md:grid-cols-1">
                        <ComparePane title={`v${selected.version_no}`} version={selected} assetId={asset.id} />
                        <ComparePane
                            title={`v${current.version_no} · current`}
                            version={current}
                            assetId={asset.id}
                        />
                    </div>
                </Modal>
            )}
        </div>
    );
};

const DetailRow = ({ label, value }: { label: string; value: string }) => (
    <div>
        <div className="text-t-tertiary">{label}</div>
        <div className="text-body-2 text-t-primary line-clamp-2">{value}</div>
    </div>
);

const ComparePane = ({
    title,
    version,
    assetId,
}: {
    title: string;
    version: AssetVersion;
    assetId: string;
}) => (
    <div>
        <div className="flex items-center gap-2 mb-3">
            <Icon className="!size-4 fill-t-secondary" name="layers" />
            <span className="text-button">{title}</span>
        </div>
        <div className="relative h-64 rounded-3xl overflow-hidden ring-1 ring-s-subtle ring-inset">
            <AssetImage
                src={version.thumb_url || version.url || assetRawUrl(assetId, version.id)}
                alt={title}
                rounded="rounded-3xl"
            />
        </div>
        <p className="mt-2 text-caption text-t-secondary line-clamp-2">
            {version.edit_instruction || "Original generation"}
        </p>
    </div>
);

function fmtDate(iso?: string): string {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default VersionTimeline;
