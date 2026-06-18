// ⑥ MEDIA — the WhatsApp Media Library (W16).
// Upload a banner + images + a video from the device, preview, OR pick previously-
// saved assets to REUSE. Attaches an ordered media set to the draft (banner first,
// then images, then video). The brochure (PDF) is its OWN next step. DORMANT-SAFE:
// uploads preview locally + saved-asset reuse activates when the WA media backend
// (voice_ops/whatsapp) is mounted — zero UI change.

"use client";

import { useMemo } from "react";
import MediaUploader from "../_components/MediaUploader";
import Button from "@/components/Button";
import { type StepCtx, type WaMedia } from "../_lib/types";

export default function MediaStep({ draft, setDraft, goTo, notify }: StepCtx) {
    const media = useMemo<WaMedia[]>(() => draft.media || [], [draft.media]);

    const setKind = (kind: WaMedia["kind"], next: WaMedia[]) => {
        const others = media.filter((m) => m.kind !== kind);
        // keep a stable order: banner -> image -> video
        const order = { banner: 0, image: 1, video: 2, brochure: 3 } as const;
        const merged = [...others, ...next].sort((a, b) => order[a.kind] - order[b.kind]);
        setDraft({ media: merged });
    };

    const banners = media.filter((m) => m.kind === "banner");
    const images = media.filter((m) => m.kind === "image");
    const videos = media.filter((m) => m.kind === "video");
    const total = media.length;

    return (
        <div className="flex flex-col gap-3">
            <MediaUploader
                kind="banner"
                title="Banner"
                hint="The hero image at the top of the message. One banner per send (replaces if you pick another)."
                multiple={false}
                selected={banners}
                onChange={(next) => setKind("banner", next)}
                notify={notify}
            />

            <MediaUploader
                kind="image"
                title="Images"
                hint="Add property photos, floor shots, amenity images — reuse from your library or upload new."
                multiple
                selected={images}
                onChange={(next) => setKind("image", next)}
                notify={notify}
            />

            <MediaUploader
                kind="video"
                title="Video"
                hint="A short walkthrough or reel. One video per send."
                multiple={false}
                selected={videos}
                onChange={(next) => setKind("video", next)}
                notify={notify}
            />

            <div className="flex items-center justify-between gap-3 card !py-4">
                <div className="text-body-2 text-t-secondary">
                    {total === 0 ? "No media attached yet — you can still continue." : `${total} media item${total === 1 ? "" : "s"} attached`}
                </div>
                <Button isBlack onClick={() => goTo("brochure")}>
                    Next: brochure
                </Button>
            </div>
        </div>
    );
}
