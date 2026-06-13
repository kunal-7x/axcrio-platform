"use client";

/**
 * AssetDetail (S6 / L5) — the deep-edit + full-record slide-over. Opened as a
 * right slide-panel (`Modal isSlidePanel`) so the vendor never leaves the
 * workspace (cs-workspace §8 / cs-asset-library §7). Structurally ports the
 * Customers/DetailsPage master-detail stack.
 *
 * Holds: large preview · Tabs(Details/Versions/Performance) · meta rows · score
 * block · status control (approve/reject) · the ⭐ NATURAL-LANGUAGE EDIT box with
 * quick-chip pills (each /edit → a NEW version, original kept) · the version strip
 * (VersionTimeline) · footer Use-this (opens UsePicker).
 *
 * Fetches GET /api/assets/{id} (owner-checked). Dormant/error -> calm states.
 */

import { useEffect, useState } from "react";
import Modal from "@/components/Modal";
import Tabs from "@/components/Tabs";
import Field from "@/components/Field";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Spinner from "@/components/Spinner";
import Icon from "@/components/Icon";
import type { TabsOption } from "@/types/tabs";
import AssetImage from "./AssetImage";
import VersionTimeline from "./VersionTimeline";
import UsePicker from "./UsePicker";
import {
    getAsset,
    editAsset,
    approveAsset,
    rejectAsset,
    restoreVersion,
    assetRawUrl,
    angleLabel,
    statusLabel,
    statusVariant,
    toCredits,
    AssetDormantError,
    type Asset,
} from "@/lib/assets";

type AssetDetailProps = {
    /** the asset to show (may be a card-light record; we refetch the full one) */
    asset: Asset | null;
    open: boolean;
    onClose: () => void;
    /** bubble status/version changes back so the gallery re-renders */
    onChanged?: (asset: Asset) => void;
};

const TABS: TabsOption[] = [
    { id: 1, name: "Details" },
    { id: 2, name: "Versions" },
    { id: 3, name: "Performance" },
];

const QUICK_EDITS = [
    "Make it premium",
    "Simpler",
    "Remove price",
    "Add my logo",
    "Story size",
    "Hinglish",
    "5 more like this",
];

const AssetDetail = ({ asset, open, onClose, onChanged }: AssetDetailProps) => {
    const [full, setFull] = useState<Asset | null>(asset);
    const [tab, setTab] = useState<TabsOption>(TABS[0]);
    const [loading, setLoading] = useState(false);
    const [editText, setEditText] = useState("");
    const [editing, setEditing] = useState(false);
    const [restoring, setRestoring] = useState(false);
    const [usePickerOpen, setUsePickerOpen] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // refetch the full record when a new asset opens
    useEffect(() => {
        if (!asset || !open) return;
        setFull(asset);
        setTab(TABS[0]);
        setError(null);
        setLoading(true);
        getAsset(asset.id)
            .then((a) => setFull(a))
            .catch((e) => {
                if (e instanceof AssetDormantError) setError(e.message);
                // otherwise keep the card-light record we already have
            })
            .finally(() => setLoading(false));
    }, [asset, open]);

    if (!asset) return null;
    const a = full || asset;
    // Prefer a presigned, browser-loadable URL: the asset's own url/thumb_url (now
    // folded from the current version server-side), else the current/newest version's
    // presigned url. Only fall back to the auth-gated /raw proxy as a last resort —
    // an <img src> can't send X-Auth so /raw 401s and the preview goes blank.
    const currentVersion =
        a.versions?.find((v) => v.is_current || v.id === a.current_version_id) ||
        a.versions?.[0];
    const src =
        a.thumb_url ||
        a.url ||
        currentVersion?.thumb_url ||
        currentVersion?.url ||
        assetRawUrl(a.id, a.current_version_id);
    const isApproved = (a.status || "").toLowerCase() === "approved";

    const refetch = async () => {
        try {
            const fresh = await getAsset(a.id);
            setFull(fresh);
            onChanged?.(fresh);
        } catch {
            /* keep current */
        }
    };

    const runEdit = async (text: string) => {
        if (!text.trim()) return;
        setEditing(true);
        setError(null);
        try {
            const updated = await editAsset(a.id, text.trim());
            setFull(updated);
            onChanged?.(updated);
            setEditText("");
            setTab(TABS[1]); // jump to Versions to show the new version landed
        } catch (e) {
            setError(e instanceof Error ? e.message : "Couldn't apply that edit.");
        } finally {
            setEditing(false);
        }
    };

    const doApprove = async () => {
        try {
            await approveAsset(a.id);
            await refetch();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Couldn't approve.");
        }
    };
    const doReject = async () => {
        try {
            await rejectAsset(a.id);
            await refetch();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Couldn't reject.");
        }
    };
    const doRestore = async (versionId: string) => {
        setRestoring(true);
        try {
            await restoreVersion(a.id, versionId);
            await refetch();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Couldn't restore.");
        } finally {
            setRestoring(false);
        }
    };

    const onAttached = () => {
        refetch();
    };

    return (
        <>
            <Modal open={open} onClose={onClose} isSlidePanel>
                <div className="flex flex-col h-svh">
                    <div className="grow overflow-y-auto px-6 pt-6 pb-4 scrollbar-none max-md:px-4">
                        {/* large preview */}
                        <div className="relative h-72 rounded-3xl overflow-hidden ring-1 ring-s-subtle ring-inset bg-b-surface1 dark:bg-shade-04/40">
                            <AssetImage src={src} alt={a.headline || "asset"} rounded="rounded-3xl" />
                        </div>

                        {/* headline + badges */}
                        <div className="flex items-start gap-3 mt-4">
                            <div className="grow">
                                <div className="text-sub-title-1 text-t-primary">
                                    {a.headline || "Untitled creative"}
                                </div>
                                <div className="flex flex-wrap items-center gap-2 mt-2">
                                    <Badge variant="neutral">{angleLabel(a.angle)}</Badge>
                                    <Badge variant={statusVariant(a.status)} dot>
                                        {statusLabel(a.status)}
                                    </Badge>
                                    {typeof a.score?.overall === "number" && (
                                        <span className="label label-green">{a.score.overall}</span>
                                    )}
                                </div>
                            </div>
                            {loading && <Spinner className="!size-9 shrink-0" />}
                        </div>

                        {/* tabs */}
                        <div className="mt-5">
                            <Tabs items={TABS} value={tab} setValue={setTab} />
                        </div>

                        {error && (
                            <div className="flex items-start gap-2.5 mt-4 p-3.5 rounded-2xl border border-primary-05/20 bg-primary-05/10 text-primary-05 text-body-2">
                                <Icon className="!size-4 shrink-0 mt-0.5 fill-current" name="info" />
                                <span>{error}</span>
                            </div>
                        )}

                        {/* DETAILS tab */}
                        {tab.id === 1 && (
                            <div className="mt-5">
                                {/* editable copy */}
                                <Field
                                    label="Headline"
                                    defaultValue={a.headline || ""}
                                    placeholder="Headline"
                                />
                                <Field
                                    className="mt-3"
                                    label="CTA"
                                    defaultValue={a.cta || ""}
                                    placeholder="Book Site Visit"
                                />

                                {/* meta rows */}
                                <div className="grid grid-cols-2 gap-x-4 gap-y-3 mt-5 pt-5 border-t border-s-subtle">
                                    <Meta label="Campaign" value={a.campaign_name} />
                                    <Meta label="Platform" value={a.platform} />
                                    <Meta label="Size" value={a.size} />
                                    <Meta label="Language" value={a.language} />
                                    <Meta label="Model" value={a.model} />
                                    <Meta label="Cost" value={toCredits(a.cost_minor)} />
                                </div>

                                {/* score block */}
                                {a.score?.sub && a.score.sub.length > 0 && (
                                    <div className="mt-5 pt-5 border-t border-s-subtle">
                                        <div className="text-overline text-t-tertiary mb-3">Creative score</div>
                                        <div className="space-y-2.5">
                                            {a.score.sub.slice(0, 6).map((s) => (
                                                <ScoreBar key={s.label} label={s.label} value={s.value} />
                                            ))}
                                        </div>
                                        {a.score.why && (
                                            <p className="mt-3 text-caption text-t-secondary">{a.score.why}</p>
                                        )}
                                    </div>
                                )}

                                {/* used-in */}
                                {a.usage && a.usage.length > 0 && (
                                    <div className="mt-5 pt-5 border-t border-s-subtle">
                                        <div className="text-overline text-t-tertiary mb-2.5">Used in</div>
                                        <div className="flex flex-wrap gap-2">
                                            {a.usage.map((u, i) => (
                                                <Badge key={i} variant="info">
                                                    {u.label || u.channel}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* ⭐ natural-language edit box + quick chips */}
                                <div className="mt-5 pt-5 border-t border-s-subtle">
                                    <div className="text-overline text-t-tertiary mb-2.5">
                                        Tell me what to change
                                    </div>
                                    <div className="flex flex-wrap gap-2 mb-3">
                                        {QUICK_EDITS.map((q) => (
                                            <button
                                                key={q}
                                                className="action !h-8 !px-2.5"
                                                onClick={() => runEdit(q)}
                                                disabled={editing}
                                            >
                                                {q}
                                            </button>
                                        ))}
                                    </div>
                                    <Field
                                        textarea
                                        placeholder="e.g. make it premium, remove price, change CTA to Book Site Visit"
                                        value={editText}
                                        onChange={(e) => setEditText(e.target.value)}
                                    />
                                    <div className="flex justify-end mt-3">
                                        <Button
                                            isStroke
                                            icon="send"
                                            onClick={() => runEdit(editText)}
                                            disabled={editing || !editText.trim()}
                                        >
                                            {editing ? "Working…" : "Apply edit"}
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* VERSIONS tab */}
                        {tab.id === 2 && (
                            <div className="mt-5">
                                <VersionTimeline asset={a} onRestore={doRestore} restoring={restoring} />
                            </div>
                        )}

                        {/* PERFORMANCE tab — honest empty until the asset is Used */}
                        {tab.id === 3 && <PerformanceTab asset={a} />}
                    </div>

                    {/* sticky footer */}
                    <div className="shrink-0 flex items-center gap-2 px-6 py-4 border-t border-s-subtle max-md:px-4">
                        {isApproved ? (
                            <Button isStroke onClick={doReject}>
                                Reject
                            </Button>
                        ) : (
                            <Button isStroke icon="check" onClick={doApprove}>
                                Approve
                            </Button>
                        )}
                        <Button className="ml-auto" isBlack icon="send" onClick={() => setUsePickerOpen(true)}>
                            Use this
                        </Button>
                    </div>
                </div>
            </Modal>

            <UsePicker
                asset={a}
                open={usePickerOpen}
                onClose={() => setUsePickerOpen(false)}
                onAttached={onAttached}
                onApproved={() => refetch()}
            />
        </>
    );
};

const Meta = ({ label, value }: { label: string; value?: string }) => (
    <div>
        <div className="text-caption text-t-tertiary">{label}</div>
        <div className="text-body-2 text-t-primary">{value || "—"}</div>
    </div>
);

const ScoreBar = ({ label, value }: { label: string; value: number }) => (
    <div>
        <div className="flex items-center justify-between text-caption mb-1">
            <span className="text-t-secondary">{label}</span>
            <span className="text-t-primary">{value}</span>
        </div>
        <div className="meter">
            <div className="meter-fill bg-primary-02" style={{ width: `${Math.min(100, value)}%` }} />
        </div>
    </div>
);

const PerformanceTab = ({ asset }: { asset: Asset }) => {
    const m = asset.metrics || {};
    const hasData = Object.keys(m).length > 0;
    if (!hasData) {
        return (
            <div className="mt-5 px-1 py-10 text-center">
                <p className="text-body-2 text-t-secondary max-w-72 mx-auto">
                    Performance appears here once this creative is used and the ads loop reports back.
                </p>
            </div>
        );
    }
    const tiles: { label: string; key: string }[] = [
        { label: "Impressions", key: "impressions" },
        { label: "Clicks", key: "clicks" },
        { label: "CTR", key: "ctr" },
        { label: "Leads", key: "leads" },
        { label: "CPL", key: "cpl" },
        { label: "Replies", key: "wa_replies" },
    ];
    return (
        <div className="mt-5 grid grid-cols-2 gap-3">
            {tiles.map((t) => (
                <div key={t.key} className="p-4 rounded-2xl bg-b-surface1 dark:bg-shade-04/30">
                    <div className="text-caption text-t-tertiary">{t.label}</div>
                    <div className="text-sub-title-1 text-t-primary">{m[t.key] ?? "—"}</div>
                </div>
            ))}
        </div>
    );
};

export default AssetDetail;
