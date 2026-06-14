"use client";

// Channels view — the per-channel setup surface. Telegram is live (the full
// connect flow + automation toggles + a contact deep-link minter); WhatsApp links
// to its own live page; Email/SMS render calm coming-soon cards (W3/W5).
// Master-plan §7 (Channel Setup is the Wave-1 FE). Core_2, zero raw hex.

import { useState } from "react";
import Link from "next/link";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Field from "@/components/Field";
import Spinner from "@/components/Spinner";
import { type CommChannel, CHANNEL_LABEL, CHANNEL_ICON } from "@/lib/communication";
import TelegramSetup, { useContactDeeplink } from "../_components/TelegramSetup";
import { ghostBtnCls, textBtnCls, ConsentBadge } from "../_shared";

type Toast = (msg: string, type?: "success" | "error") => void;

export default function ChannelsView({
    channels,
    writable,
    onToast,
    onChanged,
}: {
    channels: CommChannel[];
    writable: boolean;
    onToast: Toast;
    onChanged: () => void;
}) {
    const telegram = channels.find((c) => c.channel === "telegram");

    return (
        <div className="flex flex-col gap-5">
            <TelegramSetup channel={telegram} writable={writable} onToast={onToast} onChanged={onChanged} />

            <AutomationCard channel={telegram} />

            <DeeplinkCard writable={writable} onToast={onToast} />

            {/* WhatsApp — earner-safe: deep-link to the live page, no duplicated Meta logic */}
            <Card title="WhatsApp">
                <div className="px-5 pb-5 max-lg:px-3 flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-3">
                        <span className="flex justify-center items-center size-10 rounded-2xl bg-primary-02/12">
                            <Icon name="chat-think" className="!size-5 fill-primary-02" />
                        </span>
                        <div>
                            <div className="text-button text-t-primary">WhatsApp campaigns</div>
                            <div className="text-body-2 text-t-secondary">Managed in the dedicated WhatsApp workspace.</div>
                        </div>
                    </div>
                    <Link href="/whatsapp" className={ghostBtnCls}>
                        Open WhatsApp
                        <Icon name="arrow" className="size-4 fill-inherit" />
                    </Link>
                </div>
            </Card>

            {/* Email + SMS — coming soon (W3 / W5) */}
            <div className="grid grid-cols-2 gap-5 max-lg:grid-cols-1">
                <ComingSoonChannel channel="email" wave="Wave 3 · needs a Resend key + a verified domain" />
                <ComingSoonChannel channel="sms" wave="Wave 5 · needs MSG91 + DLT registration (TRAI)" />
            </div>
        </div>
    );
}

function AutomationCard({ channel }: { channel?: CommChannel }) {
    const on = (v?: boolean) =>
        v ? (
            <span className="inline-flex items-center gap-1.5 text-caption text-primary-02">
                <span className="size-1.5 rounded-full bg-primary-02" /> On
            </span>
        ) : (
            <span className="inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                <span className="size-1.5 rounded-full bg-t-tertiary" /> Off
            </span>
        );
    const rows = [
        {
            icon: "bell",
            title: "Founder hot-lead alert",
            desc: "When a call ends hot, ping your Telegram with the score + a tap-to-open link.",
            state: channel?.founder_alert,
            purpose: "service",
        },
        {
            icon: "reply",
            title: "Post-call auto-summary",
            desc: "Text the contact a short summary of the call (only when they've opted in).",
            state: channel?.followup,
            purpose: "service",
        },
    ];
    return (
        <Card title="Automations">
            <div className="px-5 pb-2 max-lg:px-3 flex flex-col divide-y divide-s-subtle">
                {rows.map((r) => (
                    <div key={r.title} className="flex items-center gap-4 py-4">
                        <span className="flex justify-center items-center size-10 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle shrink-0">
                            <Icon name={r.icon} className="!size-5 fill-t-secondary" />
                        </span>
                        <div className="grow min-w-0">
                            <div className="flex items-center gap-2">
                                <span className="text-button text-t-primary">{r.title}</span>
                                <ConsentBadge purpose={r.purpose} />
                            </div>
                            <div className="text-body-2 text-t-secondary">{r.desc}</div>
                        </div>
                        <div className="shrink-0">{on(r.state)}</div>
                    </div>
                ))}
            </div>
            <div className="px-5 pb-5 max-lg:px-3 text-caption text-t-tertiary">
                These are controlled by your workspace flags. Ask your admin to flip them — they fire on the live call
                pipeline, fully off the voice hot path.
            </div>
        </Card>
    );
}

function DeeplinkCard({ writable, onToast }: { writable: boolean; onToast: Toast }) {
    const [phone, setPhone] = useState("");
    const { busy, link, mint, setLink } = useContactDeeplink(onToast);
    return (
        <Card title="Invite a contact to chat">
            <div className="px-5 pb-5 max-lg:px-3">
                <p className="mb-4 text-body-2 text-t-secondary max-w-xl">
                    Mint a signed, single-use link. When the contact taps it, they start a Telegram chat with Riya
                    grounded in their last call — and consent is captured automatically.
                </p>
                <div className="flex items-end gap-3 flex-wrap">
                    <Field
                        className="w-64 max-md:w-full"
                        label="Contact phone"
                        placeholder="+91 98765 43210"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                    />
                    <button
                        className={ghostBtnCls}
                        onClick={() => mint(phone)}
                        disabled={!writable || busy}
                    >
                        {busy ? <Spinner /> : <Icon name="link-1" className="size-4 fill-inherit" />}
                        Create link
                    </button>
                </div>
                {link && (
                    <div className="mt-4 flex items-center gap-2 p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle">
                        <Icon name="chain" className="size-4 fill-t-secondary shrink-0" />
                        <code className="grow min-w-0 truncate text-caption text-t-secondary">{link}</code>
                        <button
                            className={textBtnCls}
                            onClick={() => {
                                if (typeof navigator !== "undefined" && navigator.clipboard) {
                                    navigator.clipboard.writeText(link);
                                    onToast("Copied.");
                                }
                                setLink("");
                            }}
                        >
                            Copy
                        </button>
                    </div>
                )}
            </div>
        </Card>
    );
}

function ComingSoonChannel({ channel, wave }: { channel: "email" | "sms"; wave: string }) {
    return (
        <Card title={CHANNEL_LABEL[channel]}>
            <div className="px-5 pb-6 max-lg:px-3 flex flex-col items-center text-center gap-2.5 py-4">
                <span className="flex justify-center items-center size-12 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle">
                    <Icon name={CHANNEL_ICON[channel]} className="!size-5 fill-t-secondary" />
                </span>
                <div className="text-button text-t-primary">{CHANNEL_LABEL[channel]} is on the roadmap</div>
                <p className="text-body-2 text-t-secondary max-w-xs">{wave}</p>
                <span className="mt-1 text-caption text-t-tertiary px-2.5 py-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle">
                    Coming soon
                </span>
            </div>
        </Card>
    );
}
