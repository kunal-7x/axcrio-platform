"use client";

/**
 * UploadAssetModal — "Upload image / Upload video" into Creative Studio.
 *
 * The founder asked the Asset Library to accept their OWN media, not just
 * AI-generated assets. The only real upload path the AI Asset service exposes
 * today is POST /variation-from-upload (multipart) — it ingests the uploaded
 * file as a REFERENCE and produces a library asset from it. So this modal posts
 * the chosen image/video through `variationFromUpload`; the resulting asset lands
 * in the library (the gallery re-fetches via the parent's reloadToken).
 *
 * BACKEND DEPENDENCY: a true "store this file as-is" library endpoint (a plain
 * POST /assets/upload that persists the uploaded media verbatim, with a presigned
 * GET URL) would be the cleaner home for raw uploads — `variation-from-upload`
 * routes through generation. Until that exists this is the honest, real path:
 * the upload is genuinely sent + persisted, never a fake/no-op.
 */

import { useRef, useState } from "react";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Icon from "@/components/Icon";
import { variationFromUpload } from "@/lib/assets";
import type { SelectOption } from "@/types/select";

type UploadAssetModalProps = {
    open: boolean;
    onClose: () => void;
    /** called after a successful upload so the gallery can re-fetch. */
    onUploaded: () => void;
    /** campaigns to optionally tag the upload against. */
    campaignOptions: SelectOption[];
};

// 25 MB image / 200 MB video — calm client guard before we hit the network.
const MAX_IMAGE = 25 * 1024 * 1024;
const MAX_VIDEO = 200 * 1024 * 1024;

const UploadAssetModal = ({
    open,
    onClose,
    onUploaded,
    campaignOptions,
}: UploadAssetModalProps) => {
    const imageInputRef = useRef<HTMLInputElement>(null);
    const videoInputRef = useRef<HTMLInputElement>(null);

    const [file, setFile] = useState<File | null>(null);
    const [kind, setKind] = useState<"image" | "video">("image");
    const [campaign, setCampaign] = useState<SelectOption | null>(null);
    const [instruction, setInstruction] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    const reset = () => {
        setFile(null);
        setCampaign(null);
        setInstruction("");
        setError("");
        setBusy(false);
        if (imageInputRef.current) imageInputRef.current.value = "";
        if (videoInputRef.current) videoInputRef.current.value = "";
    };

    const close = () => {
        if (busy) return; // don't drop an in-flight upload
        reset();
        onClose();
    };

    const pick = (f: File | null, asKind: "image" | "video") => {
        setError("");
        if (!f) return;
        const cap = asKind === "video" ? MAX_VIDEO : MAX_IMAGE;
        if (f.size > cap) {
            setError(
                `That ${asKind} is too large (max ${asKind === "video" ? "200" : "25"} MB).`
            );
            return;
        }
        setKind(asKind);
        setFile(f);
    };

    const submit = async () => {
        if (!file) return;
        setBusy(true);
        setError("");
        try {
            await variationFromUpload(file, {
                campaign_id: campaign?.name || undefined,
                asset_type: kind,
                instruction: instruction.trim() || undefined,
            });
            onUploaded();
            reset();
            onClose();
        } catch (e) {
            setError(
                e instanceof Error
                    ? e.message
                    : "Upload failed — please try again."
            );
            setBusy(false);
        }
    };

    return (
        <Modal open={open} onClose={close}>
            <div className="text-h5 mb-1">Upload to library</div>
            <p className="text-body-2 text-t-secondary mb-6">
                Add your own image or video. It is ingested into Creative Studio
                and lands in your asset library.
            </p>

            {/* media-type + file pickers */}
            <div className="grid grid-cols-2 gap-3 mb-5 max-md:grid-cols-1">
                <button
                    type="button"
                    onClick={() => imageInputRef.current?.click()}
                    className={`flex flex-col items-center justify-center h-28 rounded-3xl border transition-colors ${
                        file && kind === "image"
                            ? "border-primary-01 bg-primary-01/[0.06]"
                            : "border-s-stroke2 hover:border-s-highlight"
                    }`}
                >
                    <Icon name="camera-stroke" className="size-7 fill-t-secondary mb-1.5" />
                    <span className="text-button text-t-primary">Upload image</span>
                    <span className="text-caption text-t-tertiary">PNG, JPG, WebP</span>
                </button>
                <button
                    type="button"
                    onClick={() => videoInputRef.current?.click()}
                    className={`flex flex-col items-center justify-center h-28 rounded-3xl border transition-colors ${
                        file && kind === "video"
                            ? "border-primary-01 bg-primary-01/[0.06]"
                            : "border-s-stroke2 hover:border-s-highlight"
                    }`}
                >
                    <Icon name="video" className="size-7 fill-t-secondary mb-1.5" />
                    <span className="text-button text-t-primary">Upload video</span>
                    <span className="text-caption text-t-tertiary">MP4, MOV, WebM</span>
                </button>
            </div>

            <input
                ref={imageInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => pick(e.target.files?.[0] ?? null, "image")}
            />
            <input
                ref={videoInputRef}
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(e) => pick(e.target.files?.[0] ?? null, "video")}
            />

            {/* chosen-file row */}
            {file && (
                <div className="flex items-center gap-2.5 p-3 mb-5 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset">
                    <Icon
                        name={kind === "video" ? "video" : "camera-stroke"}
                        className="size-4 fill-primary-01 shrink-0"
                    />
                    <span className="text-body-2 text-t-primary truncate mr-auto">
                        {file.name}
                    </span>
                    <span className="text-caption text-t-tertiary tabular-nums shrink-0">
                        {(file.size / (1024 * 1024)).toFixed(1)} MB
                    </span>
                    <button
                        type="button"
                        onClick={() => {
                            setFile(null);
                            if (imageInputRef.current) imageInputRef.current.value = "";
                            if (videoInputRef.current) videoInputRef.current.value = "";
                        }}
                        className="shrink-0 text-t-tertiary transition-colors hover:text-t-primary"
                        aria-label="Remove file"
                    >
                        <Icon name="close" className="size-4 fill-current" />
                    </button>
                </div>
            )}

            {campaignOptions.length > 0 && (
                <Select
                    className="mb-5"
                    label="Tag to campaign (optional)"
                    value={campaign}
                    onChange={setCampaign}
                    options={campaignOptions}
                    placeholder="No campaign"
                />
            )}

            <Field
                className="mb-5"
                label="Note (optional)"
                placeholder="e.g. Hero banner for the Diwali sale"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
            />

            {error && (
                <div className="flex items-center gap-2 p-3 mb-5 rounded-2xl bg-primary-03/8 text-primary-03 text-body-2">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                    {error}
                </div>
            )}

            <div className="flex items-center gap-3">
                <Button isStroke className="flex-1" onClick={close} disabled={busy}>
                    Cancel
                </Button>
                <Button
                    isBlack
                    className="flex-1"
                    onClick={submit}
                    disabled={!file || busy}
                >
                    {busy ? "Uploading…" : "Upload"}
                </Button>
            </div>
        </Modal>
    );
};

export default UploadAssetModal;
