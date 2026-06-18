// W16 — reusable media uploader + saved-library picker (Core_2 Card/Button).
// Shared by MediaLibraryStep (banner/image/video) and BrochureStep (PDF). Upload
// from device, preview, OR pick a previously-saved asset. Dormant-safe: when the
// WA media backend is off, an upload previews locally and the saved gallery is
// empty — the founder can still build + preview a campaign today.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Image from "@/components/Image";
import Badge from "@/components/Badge";
import Spinner from "@/components/Spinner";
import { type WaMedia, type WaMediaKind } from "../_lib/types";
import {
    acceptFor,
    listMedia,
    uploadMedia,
    deleteMedia,
    prettyBytes,
} from "../_lib/wamedia";

function KindThumb({ m, className = "" }: { m: WaMedia; className?: string }) {
    if (m.kind === "video") {
        return (
            <div className={`flex items-center justify-center bg-b-surface1 ${className}`}>
                <Icon className="fill-t-secondary !size-7" name="video" />
            </div>
        );
    }
    if (m.kind === "brochure") {
        return (
            <div className={`flex flex-col items-center justify-center bg-b-surface1 ${className}`}>
                <Icon className="fill-primary-03 !size-7" name="feather" />
                <span className="mt-1 text-caption text-t-tertiary">PDF</span>
            </div>
        );
    }
    return m.url ? (
        <Image src={m.url} alt={m.title || m.kind} width={120} height={120} className={`object-cover ${className}`} />
    ) : (
        <div className={`flex items-center justify-center bg-b-surface1 ${className}`}>
            <Icon className="fill-t-tertiary" name="camera" />
        </div>
    );
}

export default function MediaUploader({
    kind,
    title,
    hint,
    multiple = false,
    selected,
    onChange,
    notify,
}: {
    kind: WaMediaKind;
    title: string;
    hint: string;
    multiple?: boolean;
    selected: WaMedia[];
    onChange: (next: WaMedia[]) => void;
    notify: (msg: string, type?: "success" | "error") => void;
}) {
    const inputRef = useRef<HTMLInputElement | null>(null);
    const [saved, setSaved] = useState<WaMedia[]>([]);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);

    const refresh = useCallback(() => {
        setLoading(true);
        listMedia(kind)
            .then((r) => setSaved(r.media))
            .finally(() => setLoading(false));
    }, [kind]);

    useEffect(() => { refresh(); }, [refresh]);

    const isSelected = (id: string) => selected.some((s) => s.id === id);

    const toggle = (m: WaMedia) => {
        if (isSelected(m.id)) {
            onChange(selected.filter((s) => s.id !== m.id));
        } else {
            onChange(multiple ? [...selected, m] : [m]);
        }
    };

    const onFiles = async (files: FileList | null) => {
        if (!files || files.length === 0) return;
        setBusy(true);
        const picked = multiple ? Array.from(files) : [files[0]];
        const next: WaMedia[] = [];
        for (const f of picked) {
            const r = await uploadMedia(kind, f, { title: f.name });
            if (r.error) {
                notify(r.error, "error");
                continue;
            }
            next.push(r.asset);
            if (!r.configured) {
                notify("Previewing locally — saves to your library when WhatsApp connects", "success");
            }
        }
        if (next.length) {
            onChange(multiple ? [...selected, ...next] : next.slice(-1));
            refresh();
        }
        setBusy(false);
        if (inputRef.current) inputRef.current.value = "";
    };

    const removeSaved = async (id: string) => {
        const ok = await deleteMedia(id);
        if (ok) {
            setSaved((prev) => prev.filter((m) => m.id !== id));
            onChange(selected.filter((s) => s.id !== id));
            notify("Removed", "success");
        }
    };

    return (
        <Card
            title={title}
            headContent={
                <Button isStroke icon="upload" onClick={() => inputRef.current?.click()} disabled={busy}>
                    {busy ? "Uploading…" : multiple ? "Upload files" : "Upload"}
                </Button>
            }
        >
            <input
                ref={inputRef}
                type="file"
                accept={acceptFor(kind)}
                multiple={multiple}
                className="hidden"
                onChange={(e) => onFiles(e.target.files)}
            />

            <div className="px-5 pb-5 max-lg:px-3">
                <p className="text-body-2 text-t-secondary mb-4">{hint}</p>

                {/* Selected (attached to this campaign) */}
                {selected.length > 0 && (
                    <div className="mb-5">
                        <div className="text-caption text-t-tertiary uppercase tracking-wide mb-2">Attached</div>
                        <div className="flex flex-wrap gap-3">
                            {selected.map((m) => (
                                <div key={m.id} className="relative w-28 group">
                                    <div className="overflow-hidden rounded-2xl border border-primary-02 size-28">
                                        <KindThumb m={m} className="size-full" />
                                    </div>
                                    <button
                                        onClick={() => toggle(m)}
                                        className="absolute -top-2 -right-2 flex items-center justify-center size-6 rounded-full bg-shade-01 text-shade-10 dark:bg-shade-10 dark:text-shade-01 shadow"
                                        title="Detach"
                                    >
                                        <Icon className="!size-3.5 fill-current" name="close" />
                                    </button>
                                    <div className="mt-1 truncate text-caption text-t-secondary">{m.title || m.kind}</div>
                                    {m.local && <Badge variant="warning" className="mt-1">Local preview</Badge>}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Saved library — pick to reuse */}
                <div className="text-caption text-t-tertiary uppercase tracking-wide mb-2">Your library</div>
                {loading ? (
                    <div className="py-10"><Spinner /></div>
                ) : saved.length === 0 ? (
                    <button
                        onClick={() => inputRef.current?.click()}
                        className="flex flex-col items-center justify-center w-full py-10 rounded-3xl border border-dashed border-s-stroke2 text-center hover:border-primary-02 transition-colors"
                    >
                        <div className="flex items-center justify-center size-12 mb-3 rounded-full bg-b-surface1">
                            <Icon className="fill-t-secondary" name="upload" />
                        </div>
                        <div className="text-sub-title-2 text-t-primary">Upload your first {kind}</div>
                        <div className="mt-1 text-body-2 text-t-secondary">Drag from your device, reuse it across campaigns</div>
                    </button>
                ) : (
                    <div className="grid grid-cols-4 max-2xl:grid-cols-3 max-md:grid-cols-2 gap-3">
                        {saved.map((m) => (
                            <button
                                key={m.id}
                                onClick={() => toggle(m)}
                                className={`group relative text-left rounded-2xl border overflow-hidden transition-colors ${
                                    isSelected(m.id) ? "border-primary-02" : "border-s-subtle hover:border-s-stroke2"
                                }`}
                            >
                                <div className="aspect-square">
                                    <KindThumb m={m} className="size-full" />
                                </div>
                                <div className="p-2.5">
                                    <div className="truncate text-body-2 text-t-primary">{m.title || m.kind}</div>
                                    <div className="flex items-center gap-2 mt-0.5 text-caption text-t-tertiary">
                                        <span>{prettyBytes(m.size_bytes)}</span>
                                        {!!m.used_count && <span>· used {m.used_count}×</span>}
                                    </div>
                                </div>
                                {isSelected(m.id) && (
                                    <span className="absolute top-2 right-2 flex items-center justify-center size-6 rounded-full bg-shade-01 text-shade-10 dark:bg-shade-10 dark:text-shade-01">
                                        <Icon className="!size-3.5 fill-current" name="check" />
                                    </span>
                                )}
                                <span
                                    onClick={(e) => { e.stopPropagation(); removeSaved(m.id); }}
                                    className="absolute top-2 left-2 flex items-center justify-center size-6 rounded-full bg-b-surface2/90 opacity-0 group-hover:opacity-100 transition-opacity"
                                    title="Delete"
                                >
                                    <Icon className="!size-3.5 fill-t-secondary" name="trash" />
                                </span>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </Card>
    );
}
