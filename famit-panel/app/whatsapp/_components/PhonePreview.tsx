// The pinned WhatsApp phone PREVIEW (spec §3) — the founder's "real WhatsApp
// message preview, always visible". A Card framed to a phone aspect with a fixed
// WhatsApp-chrome header and a message bubble (a RESTYLE of the chat-bubble
// pattern — media header → body → CTA chips → timestamp + double blue tick).
//
// Introduces NO new component family: it's Card + Image + Icon composed into the
// WhatsApp lockup. Token-only (zero raw hex). Tokens in the body resolve to
// sample values when `useReal` is off; the parent swaps to a selected lead.

import Icon from "@/components/Icon";
import { type TemplateDraft } from "../_lib/types";

// Is the attached header media a video? Prefer the structured media[] ref
// (kind/content_type), then fall back to sniffing the URL extension.
function isVideoAsset(draft: TemplateDraft): boolean {
    const m = draft.media?.find((x) => x.url && x.url === draft.asset_url) || draft.media?.[0];
    if (m?.kind === "video") return true;
    if (m?.content_type?.startsWith("video/")) return true;
    const url = draft.asset_url || "";
    return /\.(mp4|mov|webm|m4v|ogg)(\?|$)/i.test(url);
}

type PhonePreviewProps = {
    draft: TemplateDraft;
    /** when true, {{1}} resolves to the supplied sample (real lead name) */
    sampleName?: string;
    className?: string;
};

// Resolve {{1}}, {{2}}… personalization tokens to a sample value so the preview
// shows what the customer actually sees.
function resolveTokens(body: string, name: string): string {
    if (!body) return "";
    return body.replace(/\{\{\s*\d+\s*\}\}/g, name);
}

const PhonePreview = ({ draft, sampleName = "Kunal", className }: PhonePreviewProps) => {
    const body = resolveTokens(draft.body, sampleName);
    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    return (
        <div
            className={`card !p-0 overflow-hidden w-90 max-3xl:w-76 max-lg:w-full ${className || ""}`}
        >
            {/* WhatsApp chat header */}
            <div className="flex items-center gap-3 px-4 py-3 bg-b-surface1 border-b border-s-subtle">
                <div className="flex justify-center items-center size-9 rounded-full bg-b-surface2 ring-1 ring-s-stroke2">
                    <Icon className="fill-t-secondary !size-4.5" name="profile" />
                </div>
                <div className="min-w-0">
                    <div className="text-button text-t-primary truncate">Your business</div>
                    <div className="flex items-center gap-1.5 text-caption text-t-tertiary">
                        <span className="size-1.5 rounded-full bg-primary-02" />
                        online
                    </div>
                </div>
                <Icon className="ml-auto fill-t-tertiary !size-4.5" name="camera-video" />
            </div>

            {/* Chat canvas */}
            <div className="px-3 py-5 bg-b-surface1 min-h-90">
                {/* the outbound bubble */}
                <div className="ml-auto max-w-[88%] rounded-3xl rounded-tr-md bg-b-surface2 ring-1 ring-s-subtle shadow-sm overflow-hidden">
                    {/* header media — native <img>/<video> so any stored or
                        presigned Spaces URL renders (next/image would reject an
                        un-allowlisted host). */}
                    {draft.asset_url ? (
                        isVideoAsset(draft) ? (
                            <div className="relative h-40 w-full bg-shade-10">
                                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                                <video
                                    src={draft.asset_url}
                                    className="h-full w-full object-cover"
                                    muted
                                    playsInline
                                    preload="metadata"
                                />
                                <span className="absolute inset-0 flex items-center justify-center pointer-events-none">
                                    <span className="flex justify-center items-center size-11 rounded-full bg-shade-10/45 backdrop-blur-sm">
                                        <Icon className="fill-t-light !size-5" name="camera-video" />
                                    </span>
                                </span>
                            </div>
                        ) : (
                            <div className="relative h-40 w-full bg-b-surface1">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                    src={draft.asset_url}
                                    alt="Banner preview"
                                    className="h-full w-full object-cover"
                                />
                            </div>
                        )
                    ) : (
                        <div className="flex flex-col items-center justify-center h-32 w-full bg-b-surface1 text-t-tertiary">
                            <Icon className="fill-t-tertiary mb-1" name="camera" />
                            <span className="text-caption">No banner attached</span>
                        </div>
                    )}

                    <div className="px-3.5 py-2.5">
                        {/* body copy with tokens resolved */}
                        <div className="text-body-2 text-t-primary whitespace-pre-wrap leading-relaxed">
                            {body || (
                                <span className="text-t-tertiary">
                                    Your message copy appears here…
                                </span>
                            )}
                        </div>

                        {/* timestamp + double blue tick */}
                        <div className="flex items-center justify-end gap-1 mt-1.5 text-caption text-t-tertiary">
                            {now}
                            <Icon className="fill-primary-01 !size-3.5" name="check" />
                        </div>
                    </div>

                    {/* CTA quick-reply / URL chips */}
                    {(draft.cta || draft.cta_url) && (
                        <div className="border-t border-s-subtle">
                            <button
                                type="button"
                                className="flex items-center justify-center gap-1.5 w-full py-2.5 text-button text-primary-01 fill-primary-01 cursor-default"
                            >
                                <Icon className="fill-inherit !size-4" name="link-1" />
                                {draft.cta || "Book now"}
                            </button>
                        </div>
                    )}
                </div>

                {draft.footer && (
                    <div className="ml-auto max-w-[88%] mt-1 pr-1 text-right text-caption text-t-tertiary">
                        {draft.footer}
                    </div>
                )}
            </div>
        </div>
    );
};

export default PhonePreview;
