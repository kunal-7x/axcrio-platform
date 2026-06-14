"use client";

// ============================================================================
// app/communication/_body — the Communication shell. ONE page, four views
// (Channels / Builder / Inbox / Analytics) via the SubNav segmented control, with
// a ChannelPicker scoping the active channel. The whole omnichannel surface lives
// here; Telegram is live, Email/SMS render coming-soon, WhatsApp deep-links out.
//
// Extracted from page.tsx (named export) to avoid the Next.js route-type checker
// rejecting a non-default export from the page module — same pattern as
// integrations/_body.tsx.
//
// DORMANT-SAFE: when COMM_ENABLED is off (channels read 404s), render a calm
// coming-soon card, never an error wall. Core_2, Inter Display, zero raw hex.
// ============================================================================

import { useMemo, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import { useMe, canWrite } from "@/lib/auth";
import { useChannels, type ChannelKind } from "@/lib/communication";
import { SubNav, ChannelPicker, type CommView } from "./_shared";
import ChannelsView from "./_views/ChannelsView";
import BuilderView from "./_views/BuilderView";
import InboxView from "./_views/InboxView";
import AnalyticsView from "./_views/AnalyticsView";

type Toast = { msg: string; type: "success" | "error" };

export function CommunicationBody() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [view, setView] = useState<CommView>("channels");
    const [channel, setChannel] = useState<ChannelKind>("telegram");
    const [toast, setToast] = useState<Toast | null>(null);

    const { channels, loading, dormant, reload } = useChannels();

    const flash = (msg: string, type: Toast["type"] = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    const configuredMap = useMemo(() => {
        const m: Partial<Record<ChannelKind, boolean>> = { whatsapp: true };
        for (const c of channels) m[c.channel] = c.configured;
        return m;
    }, [channels]);

    // ---- dormant (flag off / not entitled) -> calm coming-soon card ----------
    if (!loading && dormant) {
        return (
            <Card title="Communication">
                <div className="flex flex-col items-center text-center py-16 gap-3">
                    <span className="inline-flex items-center justify-center size-14 rounded-full bg-b-surface2">
                        <Icon name="send" className="size-6 fill-t-secondary" />
                    </span>
                    <div className="text-h6 text-t-primary">Reach every lead, on every channel</div>
                    <p className="text-body-2 text-t-secondary max-w-md">
                        Telegram, Email and SMS — one builder, one inbox, one brain. Hot-lead alerts to your phone and
                        an after-call summary to the contact, automatically. This workspace isn&apos;t enabled for
                        Communication yet.
                    </p>
                </div>
            </Card>
        );
    }

    return (
        <>
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button
                        onClick={() => setToast(null)}
                        className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none"
                    >
                        ×
                    </button>
                </div>
            )}

            <SubNav view={view} onChange={setView} />

            {/* the channel picker scopes the Channels / Builder / Inbox views */}
            {view !== "analytics" && (
                <ChannelPicker channel={channel} onChange={setChannel} configuredMap={configuredMap} />
            )}

            {loading ? (
                <div className="flex items-center justify-center py-32">
                    <Spinner />
                </div>
            ) : view === "channels" ? (
                <ChannelsView channels={channels} writable={writable} onToast={flash} onChanged={reload} />
            ) : view === "builder" ? (
                <BuilderView writable={writable} onToast={flash} />
            ) : view === "inbox" ? (
                <InboxView onToast={flash} />
            ) : (
                <AnalyticsView />
            )}
        </>
    );
}
