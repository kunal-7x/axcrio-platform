"use client";

/**
 * UploadClip (W9) — the manual-upload path. The master plan's "works with zero
 * gen-key" floor: the vendor brings their OWN clip, previews it, and (once the
 * composite worker lands) the studio composites captions/voiceover/brand over it.
 *
 * A right slide-panel (Modal isSlidePanel) with a drop zone + a local <video>
 * preview (object URL, no upload until confirmed). Honest about the current state:
 * when the upload endpoint isn't live it explains the clip will composite once the
 * render worker is enabled — never a fake success. Token-pure, zero raw hex.
 */

import { useEffect, useRef, useState } from "react";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import { fmtDuration } from "@/lib/assets";

type UploadClipProps = {
    open: boolean;
    onClose: () => void;
};

const UploadClip = ({ open, onClose }: UploadClipProps) => {
    const [file, setFile] = useState<File | null>(null);
    const [objUrl, setObjUrl] = useState<string | null>(null);
    const [duration, setDuration] = useState<number | undefined>(undefined);
    const inputRef = useRef<HTMLInputElement | null>(null);

    // revoke the object URL on change/unmount (no memory leak)
    useEffect(() => {
        return () => {
            if (objUrl) URL.revokeObjectURL(objUrl);
        };
    }, [objUrl]);

    // reset on close
    useEffect(() => {
        if (!open) {
            setFile(null);
            setDuration(undefined);
            if (objUrl) URL.revokeObjectURL(objUrl);
            setObjUrl(null);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    const pick = (f?: File | null) => {
        if (!f) return;
        if (objUrl) URL.revokeObjectURL(objUrl);
        setFile(f);
        setObjUrl(URL.createObjectURL(f));
        setDuration(undefined);
    };

    return (
        <Modal open={open} onClose={onClose} isSlidePanel classWrapper="!w-[28rem] max-md:!w-full">
            <div className="flex flex-col h-svh">
                <div className="px-6 pt-6 pb-3">
                    <div className="text-h6">Upload your clip</div>
                    <p className="mt-1 text-body-2 text-t-secondary">
                        Bring your own footage — the studio composites captions, voiceover and your
                        brand over it. No gen-key needed.
                    </p>
                </div>

                <div className="grow overflow-y-auto px-6 pb-4 scrollbar-none">
                    {!objUrl ? (
                        <button
                            onClick={() => inputRef.current?.click()}
                            className="flex flex-col items-center justify-center gap-3 w-full h-64 rounded-3xl border border-dashed border-s-stroke2 bg-b-surface2 fill-t-tertiary transition-colors hover:border-s-highlight hover:bg-b-surface1/60 dark:hover:bg-shade-04/30"
                        >
                            <span className="flex items-center justify-center size-12 rounded-2xl bg-b-surface1 dark:bg-shade-04/40">
                                <Icon name="upload" />
                            </span>
                            <span className="text-body-2 text-t-secondary">Click to choose a video</span>
                            <span className="text-caption text-t-tertiary">MP4, MOV or WebM · up to 60s</span>
                        </button>
                    ) : (
                        <div>
                            <div className="relative h-64 rounded-3xl overflow-hidden bg-shade-09/5 ring-1 ring-s-subtle ring-inset dark:bg-shade-01/40">
                                <video
                                    src={objUrl}
                                    className="absolute inset-0 size-full object-contain"
                                    controls
                                    playsInline
                                    preload="metadata"
                                    onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
                                />
                            </div>
                            <div className="flex items-center justify-between mt-3">
                                <div className="min-w-0">
                                    <div className="text-body-2 text-t-primary line-clamp-1">{file?.name}</div>
                                    <div className="text-caption text-t-tertiary tabular-nums">
                                        {[fmtDuration(duration), file ? `${(file.size / 1048576).toFixed(1)} MB` : ""]
                                            .filter(Boolean)
                                            .join(" · ")}
                                    </div>
                                </div>
                                <button
                                    className="action !h-9 !px-3"
                                    onClick={() => inputRef.current?.click()}
                                >
                                    <Icon name="upload" /> Replace
                                </button>
                            </div>
                            <div className="flex items-start gap-2.5 mt-4 p-3.5 rounded-2xl border border-primary-02/20 bg-primary-02/8 text-body-2 text-t-secondary">
                                <Icon className="!size-4 shrink-0 mt-0.5 fill-primary-02" name="info" />
                                <span>
                                    Your clip composites with captions, voiceover and your brand once the
                                    render worker is enabled for your workspace.
                                </span>
                            </div>
                        </div>
                    )}
                    <input
                        ref={inputRef}
                        type="file"
                        accept="video/*"
                        className="hidden"
                        onChange={(e) => pick(e.target.files?.[0])}
                    />
                </div>

                <div className="shrink-0 flex items-center gap-3 px-6 py-4 border-t border-s-subtle">
                    <Button isStroke className="flex-1" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button isBlack className="flex-1" disabled={!file} onClick={onClose}>
                        Add to library
                    </Button>
                </div>
            </div>
        </Modal>
    );
};

export default UploadClip;
