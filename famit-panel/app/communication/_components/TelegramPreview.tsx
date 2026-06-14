"use client";

// The pinned TELEGRAM message PREVIEW — the founder's "real preview, always
// visible". A Card framed to a phone aspect with a fixed Telegram-chrome header
// and a message bubble (media header -> body -> inline URL buttons -> timestamp +
// single check). A RESTYLE of the WhatsApp PhonePreview pattern for Telegram —
// introduces NO new component family: Card + Image + Icon composed. Token-only
// (zero raw hex). {variable} tokens resolve to a sample so the preview shows what
// the contact actually sees.

import Image from "@/components/Image";
import Icon from "@/components/Icon";

export type PreviewButton = { text: string; url?: string };

export type TelegramPreviewDraft = {
    body: string;
    asset_url?: string;
    asset_kind?: "photo" | "video" | "document";
    buttons?: PreviewButton[];
    botName?: string;
};

function resolveTokens(body: string, sample: Record<string, string>): string {
    if (!body) return "";
    // {name}, {{1}}, {phone} … -> sample value (or a soft placeholder).
    return body
        .replace(/\{\{\s*\d+\s*\}\}/g, sample.name || "Asha")
        .replace(/\{(\w+)\}/g, (_m, k) => sample[k] || `{${k}}`);
}

const TelegramPreview = ({
    draft,
    sample = { name: "Asha", phone: "+91 98••• ••210" },
    className,
}: {
    draft: TelegramPreviewDraft;
    sample?: Record<string, string>;
    className?: string;
}) => {
    const body = resolveTokens(draft.body, sample);
    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const buttons = (draft.buttons || []).filter((b) => b.text);

    return (
        <div className={`card !p-0 overflow-hidden w-90 max-3xl:w-76 max-lg:w-full ${className || ""}`}>
            {/* Telegram chat header */}
            <div className="flex items-center gap-3 px-4 py-3 bg-b-surface1 border-b border-s-subtle">
                <div className="flex justify-center items-center size-9 rounded-full bg-primary-01/12">
                    <Icon className="fill-primary-01 !size-4.5" name="send" />
                </div>
                <div className="min-w-0">
                    <div className="text-button text-t-primary truncate">{draft.botName || "Riya · your assistant"}</div>
                    <div className="flex items-center gap-1.5 text-caption text-t-tertiary">
                        <span className="size-1.5 rounded-full bg-primary-02" />
                        bot
                    </div>
                </div>
                <Icon className="ml-auto fill-t-tertiary !size-4.5" name="dots" />
            </div>

            {/* Chat canvas */}
            <div className="px-3 py-5 bg-b-surface1 min-h-90">
                {/* the outbound bubble — Telegram tints the sender's own bubble */}
                <div className="ml-auto max-w-[88%] rounded-3xl rounded-tr-md bg-primary-01/10 ring-1 ring-primary-01/15 shadow-sm overflow-hidden">
                    {/* header media */}
                    {draft.asset_url ? (
                        draft.asset_kind === "document" ? (
                            <div className="flex items-center gap-3 px-3.5 py-3 bg-b-surface1/70 border-b border-s-subtle">
                                <span className="flex justify-center items-center size-9 rounded-xl bg-primary-01/12 shrink-0">
                                    <Icon className="fill-primary-01 !size-4.5" name="upload" />
                                </span>
                                <div className="min-w-0">
                                    <div className="text-button text-t-primary truncate">Attachment.pdf</div>
                                    <div className="text-caption text-t-tertiary">Document</div>
                                </div>
                            </div>
                        ) : (
                            <div className="relative h-40 w-full bg-b-surface1">
                                <Image className="object-cover" src={draft.asset_url} alt="Media preview" fill sizes="320px" />
                                {draft.asset_kind === "video" && (
                                    <span className="absolute inset-0 flex items-center justify-center">
                                        <span className="flex justify-center items-center size-11 rounded-full bg-shade-10/45 backdrop-blur-sm">
                                            <Icon className="fill-t-light !size-5" name="video" />
                                        </span>
                                    </span>
                                )}
                            </div>
                        )
                    ) : null}

                    <div className="px-3.5 py-2.5">
                        <div className="text-body-2 text-t-primary whitespace-pre-wrap leading-relaxed">
                            {body || <span className="text-t-tertiary">Your message appears here…</span>}
                        </div>
                        <div className="flex items-center justify-end gap-1 mt-1.5 text-caption text-t-tertiary">
                            {now}
                            <Icon className="fill-primary-01 !size-3.5" name="check" />
                        </div>
                    </div>

                    {/* inline URL buttons (Telegram stacks them under the bubble) */}
                    {buttons.length > 0 && (
                        <div className="border-t border-primary-01/15 divide-y divide-primary-01/10">
                            {buttons.map((b, i) => (
                                <div
                                    key={i}
                                    className="flex items-center justify-center gap-1.5 w-full py-2.5 text-button text-primary-01 fill-primary-01"
                                >
                                    <Icon className="fill-inherit !size-4" name="link-1" />
                                    {b.text}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default TelegramPreview;
