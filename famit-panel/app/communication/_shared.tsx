"use client";

// ============================================================================
// app/communication/_shared — chrome + primitives for the omnichannel
// Communication surface (communication/COMMUNICATION-MASTER-PLAN.md §7).
//
// REUSE, never approximate: same "Signal" vocabulary as the rest of the panel —
// Core_2 Card/Badge/Icon + semantic @theme tokens, zero raw hex. Mirrors
// app/integrations/_shared.tsx (SubNav pill-strip, InfoStrip, ghost buttons) so
// the two channel/connector surfaces feel like one product.
//
// Glyph ground-truth honored (only kit icons): Telegram=send, Email=envelope,
// SMS=chat, WhatsApp=chat-think, alert=bell, copy/Test=reply or a text button.
// ============================================================================

import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import {
    type ChannelKind,
    CHANNEL_LABEL,
    CHANNEL_ICON,
    CHANNEL_WAVE,
} from "@/lib/communication";

// Ghost (icon + label) action button — the shared affordance (matches integrations).
export const ghostBtnCls =
    "inline-flex items-center gap-2 h-10 px-4 rounded-full text-button text-t-secondary border border-s-subtle transition-all hover:border-s-highlight hover:text-t-primary disabled:opacity-50 disabled:cursor-not-allowed";

// A quiet text button (Test / Copy / Find — kit has no copy glyph).
export const textBtnCls =
    "inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-caption text-t-secondary border border-s-subtle transition-all hover:border-s-highlight hover:text-t-primary disabled:opacity-50 disabled:cursor-not-allowed";

// ---- the section TAB strip (Channels / Builder / Inbox / Analytics) ---------
// A routed-within-one-shell segmented control (not <Tabs>) — same pattern the
// integrations page uses for its sub-views.
export type CommView = "channels" | "builder" | "inbox" | "analytics";

const VIEWS: { id: CommView; label: string; icon: string }[] = [
    { id: "channels", label: "Channels", icon: "layers" },
    { id: "builder", label: "Builder", icon: "magic-pencil" },
    { id: "inbox", label: "Inbox", icon: "chat" },
    { id: "analytics", label: "Analytics", icon: "chart" },
];

export function SubNav({
    view,
    onChange,
    actions,
}: {
    view: CommView;
    onChange: (v: CommView) => void;
    actions?: React.ReactNode;
}) {
    return (
        <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
            <div className="flex items-center gap-1 w-fit max-w-full overflow-x-auto scrollbar-none">
                {VIEWS.map((v) => {
                    const active = v.id === view;
                    return (
                        <button
                            key={v.id}
                            onClick={() => onChange(v.id)}
                            className={`shrink-0 inline-flex items-center gap-2 h-10 px-4 rounded-full border text-button transition-colors hover:text-t-primary ${
                                active
                                    ? "border-s-stroke2 text-t-primary"
                                    : "border-transparent text-t-secondary"
                            }`}
                        >
                            <Icon name={v.icon} className={`!size-4 ${active ? "fill-t-primary" : "fill-t-secondary"}`} />
                            {v.label}
                        </button>
                    );
                })}
            </div>
            {actions && <div className="flex items-center gap-3 shrink-0">{actions}</div>}
        </div>
    );
}

// ---- ChannelPicker — the row of channel chips that scope the active view -----
// Telegram is live; WhatsApp deep-links to its own live page; Email/SMS render a
// "coming soon" disabled chip (dormant-safe — never an error wall).
export const ALL_CHANNELS: ChannelKind[] = ["telegram", "whatsapp", "email", "sms"];

export function ChannelPicker({
    channel,
    onChange,
    configuredMap,
}: {
    channel: ChannelKind;
    onChange: (c: ChannelKind) => void;
    configuredMap?: Partial<Record<ChannelKind, boolean>>;
}) {
    return (
        <div className="flex items-center gap-2.5 mb-5 flex-wrap">
            {ALL_CHANNELS.map((c) => {
                const live = CHANNEL_WAVE[c] === "live";
                const active = c === channel;
                const configured = configuredMap?.[c];
                return (
                    <button
                        key={c}
                        onClick={() => live && onChange(c)}
                        disabled={!live}
                        title={live ? CHANNEL_LABEL[c] : `${CHANNEL_LABEL[c]} — coming soon`}
                        className={`group relative inline-flex items-center gap-2.5 h-11 pl-3 pr-4 rounded-2xl border transition-all ${
                            active
                                ? "border-s-highlight bg-b-surface1 shadow-widget text-t-primary"
                                : live
                                ? "border-s-subtle bg-b-surface2 text-t-secondary hover:text-t-primary hover:border-s-highlight"
                                : "border-s-subtle/60 bg-b-surface2 text-t-tertiary cursor-not-allowed opacity-70"
                        }`}
                    >
                        <span
                            className={`flex justify-center items-center size-7 rounded-xl transition-colors ${
                                active ? "bg-primary-01/12" : "bg-b-surface2 ring-1 ring-s-subtle"
                            }`}
                        >
                            <Icon
                                name={CHANNEL_ICON[c]}
                                className={`!size-4 ${active ? "fill-primary-01" : "fill-t-secondary"}`}
                            />
                        </span>
                        <span className="text-button">{CHANNEL_LABEL[c]}</span>
                        {live ? (
                            configured ? (
                                <span className="size-1.5 rounded-full bg-primary-02" title="Connected" />
                            ) : null
                        ) : (
                            <span className="text-caption text-t-tertiary px-1.5 py-0.5 rounded-full bg-b-surface2 ring-1 ring-s-subtle">
                                Soon
                            </span>
                        )}
                    </button>
                );
            })}
        </div>
    );
}

// ---- ConsentBadge — the (channel × purpose) compliance pill ------------------
// Service-implicit (post-call summary) = the defensible lane; marketing = opt-in.
export function ConsentBadge({ purpose = "service" }: { purpose?: string }) {
    const map: Record<string, { label: string; variant: BadgeVariant }> = {
        service: { label: "Service", variant: "info" },
        transactional: { label: "Transactional", variant: "neutral" },
        marketing: { label: "Marketing — opt-in", variant: "warning" },
    };
    const c = map[purpose] || map.service;
    return <Badge variant={c.variant}>{c.label}</Badge>;
}

// ---- StatusDot — small connected/idle indicator ------------------------------
export function StatusDot({ ok, label }: { ok: boolean; label?: string }) {
    return (
        <span className="inline-flex items-center gap-1.5 text-caption text-t-secondary">
            <span className={`size-1.5 rounded-full ${ok ? "bg-primary-02" : "bg-t-tertiary"}`} />
            {label || (ok ? "Connected" : "Not connected")}
        </span>
    );
}

// Inline info strip (matches the integrations / api-keys live-banner grammar).
export function InfoStrip({ children }: { children: React.ReactNode }) {
    return (
        <div className="mb-5 flex items-start gap-2 p-3.5 rounded-3xl bg-b-surface2 border border-s-subtle text-body-2 text-t-secondary">
            <Icon name="info" className="size-4 fill-t-secondary shrink-0 mt-0.5" />
            <div>{children}</div>
        </div>
    );
}

export function fmtDateTime(d?: string | null): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}
