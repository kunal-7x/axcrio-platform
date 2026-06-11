"use client";

/**
 * UsePicker (L7 / L8 / S11) — the cross-platform reuse engine. The founder's
 * headline: assets are PICKED into WhatsApp templates / ads / funnels / workflows.
 * The backend exposes ONE verb — POST /api/assets/{id}/attach {channel, ref_id}.
 * This gives that verb a premium, consistent "Use this →" picker (cs-asset-library §9).
 *
 * Two views in one centered Modal:
 *   - destination grid (WhatsApp / Ads / Funnel / Workflow / Download)
 *   - the "Attach to WhatsApp" flow (L8): pick/AI-write a template + a live
 *     token-styled WhatsApp-bubble preview, then attach.
 *
 * approved-only gate: a draft first prompts "Approve & use?" (one tap = approve
 * then attach) so the vendor isn't blocked but the gate holds. Dormant-safe.
 */

import { useState } from "react";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Icon from "@/components/Icon";
import Image from "@/components/Image";
import type { SelectOption } from "@/types/select";
import {
    approveAsset,
    attachAsset,
    assetRawUrl,
    AssetDormantError,
    AssetGuardError,
    type Asset,
    type AttachChannel,
} from "@/lib/assets";

type UsePickerProps = {
    asset: Asset | null;
    open: boolean;
    onClose: () => void;
    onAttached?: (asset: Asset, channel: AttachChannel) => void;
    onApproved?: (asset: Asset) => void;
};

type Destination = {
    id: AttachChannel | "download";
    label: string;
    desc: string;
    icon: string;
};

const DESTINATIONS: Destination[] = [
    { id: "whatsapp", label: "WhatsApp template", desc: "Attach to a message template", icon: "chat" },
    { id: "meta_ads", label: "Ad campaign", desc: "Add to a Meta ad test set", icon: "promote" },
    { id: "landing", label: "Funnel", desc: "Use as a funnel-step image", icon: "layers" },
    { id: "workflow", label: "Workflow", desc: "Bind to a workflow asset node", icon: "chain" },
    { id: "download", label: "Download", desc: "Export the raw render", icon: "upload" },
];

const TEMPLATES: SelectOption[] = [
    { id: 1, name: "Choose a template…" },
    { id: 2, name: "Site visit invite" },
    { id: 3, name: "Festive offer" },
    { id: 4, name: "Follow-up nudge" },
];

const UsePicker = ({ asset, open, onClose, onAttached, onApproved }: UsePickerProps) => {
    const [view, setView] = useState<"pick" | "whatsapp">("pick");
    const [template, setTemplate] = useState<SelectOption>(TEMPLATES[0]);
    const [message, setMessage] = useState(
        "Hi {{name}}, here's something for you from our latest campaign."
    );
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!asset) return null;
    const isApproved = (asset.status || "").toLowerCase() === "approved";

    const reset = () => {
        setView("pick");
        setError(null);
        setBusy(false);
    };

    const ensureApproved = async (): Promise<boolean> => {
        if (isApproved) return true;
        try {
            await approveAsset(asset.id);
            onApproved?.(asset);
            return true;
        } catch (e) {
            setError(approveError(e));
            return false;
        }
    };

    const doAttach = async (channel: AttachChannel, refId?: string) => {
        setBusy(true);
        setError(null);
        try {
            if (!(await ensureApproved())) return;
            await attachAsset(asset.id, channel, refId);
            onAttached?.(asset, channel);
            reset();
            onClose();
        } catch (e) {
            setError(attachError(e));
        } finally {
            setBusy(false);
        }
    };

    const handleDestination = (d: Destination) => {
        setError(null);
        if (d.id === "download") {
            window.open(assetRawUrl(asset.id, asset.current_version_id), "_blank");
            return;
        }
        if (d.id === "whatsapp") {
            setView("whatsapp");
            return;
        }
        doAttach(d.id);
    };

    const src = asset.thumb_url || asset.url || assetRawUrl(asset.id, asset.current_version_id);

    return (
        <Modal
            open={open}
            onClose={() => {
                reset();
                onClose();
            }}
            classWrapper="max-w-150"
        >
            {view === "pick" ? (
                <>
                    <div className="text-h6">Use this creative</div>
                    {!isApproved && (
                        <p className="mt-1.5 text-body-2 text-t-secondary">
                            This is a draft — picking a live channel will approve it first.
                        </p>
                    )}
                    <div className="grid grid-cols-2 gap-3 mt-6 max-md:grid-cols-1">
                        {DESTINATIONS.map((d) => (
                            <button
                                key={d.id}
                                className="flex items-start gap-3 p-4 text-left rounded-3xl border border-s-subtle transition-colors hover:border-s-highlight disabled:opacity-50"
                                onClick={() => handleDestination(d)}
                                disabled={busy}
                            >
                                <span className="flex items-center justify-center size-10 shrink-0 rounded-2xl bg-b-surface1 fill-t-secondary dark:bg-shade-04/50">
                                    <Icon name={d.icon} />
                                </span>
                                <span>
                                    <span className="block text-button text-t-primary">{d.label}</span>
                                    <span className="block text-caption text-t-secondary">{d.desc}</span>
                                </span>
                            </button>
                        ))}
                    </div>
                    {error && <ErrorNote text={error} />}
                </>
            ) : (
                <>
                    <button
                        className="flex items-center gap-1.5 text-button text-t-secondary fill-t-secondary transition-colors hover:text-t-primary hover:fill-t-primary"
                        onClick={() => setView("pick")}
                    >
                        <Icon className="!size-4 fill-inherit rotate-180" name="arrow" /> Back
                    </button>
                    <div className="text-h6 mt-3">Attach to WhatsApp</div>

                    <div className="flex items-center gap-3 mt-5 p-3 rounded-3xl bg-b-surface1 dark:bg-shade-04/30">
                        <div className="relative size-14 shrink-0 rounded-2xl overflow-hidden">
                            {src && (
                                <Image
                                    className="object-cover opacity-100"
                                    src={src}
                                    alt={asset.headline || "asset"}
                                    fill
                                    sizes="56px"
                                    unoptimized
                                />
                            )}
                        </div>
                        <div className="min-w-0">
                            <div className="text-button text-t-primary line-clamp-1">
                                {asset.headline || "Creative"}
                            </div>
                            <div className="text-caption text-t-secondary line-clamp-1">
                                {[asset.cta, asset.campaign_name].filter(Boolean).join(" · ")}
                            </div>
                        </div>
                    </div>

                    <div className="mt-5">
                        <Select
                            label="Template"
                            value={template}
                            onChange={setTemplate}
                            options={TEMPLATES}
                        />
                        <button className="mt-2 text-caption text-primary-01 transition-opacity hover:opacity-80">
                            + Ask AI to write a template from this campaign
                        </button>
                    </div>

                    <Field
                        className="mt-4"
                        textarea
                        label="Message"
                        value={message}
                        onChange={(e) => setMessage(e.target.value)}
                    />

                    {/* live WhatsApp bubble preview — token-styled, no raw hex */}
                    <div className="mt-5">
                        <div className="text-overline text-t-tertiary mb-2">Preview</div>
                        <div className="p-4 rounded-3xl bg-b-surface1 dark:bg-shade-04/30">
                            <div className="max-w-72 ml-auto rounded-2xl overflow-hidden bg-b-surface2 ring-1 ring-s-subtle ring-inset shadow-widget">
                                {src && (
                                    <div className="relative h-36">
                                        <Image
                                            className="object-cover opacity-100"
                                            src={src}
                                            alt="preview"
                                            fill
                                            sizes="288px"
                                            unoptimized
                                        />
                                    </div>
                                )}
                                <div className="p-3">
                                    <p className="text-body-2 text-t-primary whitespace-pre-wrap">{message}</p>
                                    {asset.cta && (
                                        <div className="mt-2.5 pt-2.5 border-t border-s-subtle text-center text-button text-primary-01">
                                            {asset.cta}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>

                    {error && <ErrorNote text={error} />}

                    <div className="flex items-center justify-end gap-3 mt-6">
                        <Button isStroke onClick={() => setView("pick")}>
                            Cancel
                        </Button>
                        <Button isBlack onClick={() => doAttach("whatsapp", String(template.id))} disabled={busy}>
                            {busy ? "Attaching…" : "Attach & continue"}
                        </Button>
                    </div>
                </>
            )}
        </Modal>
    );
};

const ErrorNote = ({ text }: { text: string }) => (
    <div className="flex items-start gap-2.5 mt-4 p-3.5 rounded-2xl border border-primary-05/20 bg-primary-05/10 text-primary-05 text-body-2">
        <Icon className="!size-4 shrink-0 mt-0.5 fill-current" name="info" />
        <span>{text}</span>
    </div>
);

function approveError(e: unknown): string {
    if (e instanceof AssetDormantError) return e.message;
    return "Couldn't approve this asset. Try again.";
}
function attachError(e: unknown): string {
    if (e instanceof AssetDormantError) return e.message;
    if (e instanceof AssetGuardError && e.code === "not_approved")
        return "This asset must be approved before it can be used.";
    return "Couldn't attach this asset. Try again.";
}

export default UsePicker;
