"use client";

// Inbox view — the unified conversation surface. A two-pane layout: the session
// list (one row per contact, channel as a column) on the left, the chat
// transcript on the right (CONTACT on the RIGHT / primary tint, Riya on the LEFT —
// the exact CRM ChatBubble pattern). The brain's grounding (call summary / next
// action / outcome / interest) shows as a context header. A one-tap human-takeover
// composer is surfaced (W4 wires the live send-as-human). Master-plan §7.
// Dormant-safe + keyset-friendly; Core_2, zero raw hex.

import { useEffect, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Badge from "@/components/Badge";
import {
    useSessions,
    getSession,
    type CommSession,
    type SessionTurn,
    CHANNEL_ICON,
    fmtRelative,
} from "@/lib/communication";
import { ConsentBadge, textBtnCls } from "../_shared";

type Toast = (msg: string, type?: "success" | "error") => void;

export default function InboxView({ onToast }: { onToast: Toast }) {
    const { sessions, loading } = useSessions({ pollMs: 20000 });
    const [activeId, setActiveId] = useState<string>("");
    const [detail, setDetail] = useState<CommSession | null>(null);
    const [loadingDetail, setLoadingDetail] = useState(false);

    useEffect(() => {
        if (!activeId && sessions.length) setActiveId(sessions[0].id);
    }, [sessions, activeId]);

    useEffect(() => {
        if (!activeId) return;
        let alive = true;
        setLoadingDetail(true);
        (async () => {
            const r = await getSession(activeId);
            if (!alive) return;
            setDetail(r.session);
            setLoadingDetail(false);
        })();
        return () => {
            alive = false;
        };
    }, [activeId]);

    return (
        <div className="grid grid-cols-[22rem_1fr] gap-5 max-lg:grid-cols-1 items-start">
            {/* LIST */}
            <Card title="Conversations" classHead="!h-11">
                <div className="px-2 pb-3 max-lg:px-1 max-h-[34rem] overflow-y-auto scrollbar scrollbar-thin scrollbar-thumb-t-tertiary/30">
                    {loading ? (
                        <div className="flex justify-center py-16">
                            <Spinner />
                        </div>
                    ) : sessions.length === 0 ? (
                        <EmptyList />
                    ) : (
                        <div className="flex flex-col gap-0.5">
                            {sessions.map((s) => (
                                <SessionRow
                                    key={s.id}
                                    s={s}
                                    active={s.id === activeId}
                                    onClick={() => setActiveId(s.id)}
                                />
                            ))}
                        </div>
                    )}
                </div>
            </Card>

            {/* TRANSCRIPT */}
            <Card
                title={detail ? detail.contact_name || detail.external_chat_id || "Conversation" : "Transcript"}
                headContent={
                    detail ? (
                        <div className="mr-4 flex items-center gap-2">
                            <span className="inline-flex items-center gap-1.5 text-caption text-t-secondary capitalize">
                                <Icon name={CHANNEL_ICON[(detail.channel as "telegram") || "telegram"] || "send"} className="!size-3.5 fill-t-secondary" />
                                {detail.channel}
                            </span>
                            <button className={textBtnCls} onClick={() => onToast("Human takeover ships in Wave 4.")}>
                                <Icon name="profile" className="size-3.5 fill-inherit" />
                                Take over
                            </button>
                        </div>
                    ) : undefined
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {!activeId ? (
                        <div className="flex flex-col items-center text-center gap-2 py-20 text-t-tertiary">
                            <Icon name="chat" className="!size-7 fill-t-tertiary" />
                            <span className="text-body-2">Pick a conversation to read the transcript.</span>
                        </div>
                    ) : loadingDetail ? (
                        <div className="flex justify-center py-20">
                            <Spinner />
                        </div>
                    ) : detail ? (
                        <Transcript session={detail} onToast={onToast} />
                    ) : (
                        <div className="py-20 text-center text-body-2 text-t-tertiary">Couldn&apos;t load this conversation.</div>
                    )}
                </div>
            </Card>
        </div>
    );
}

function SessionRow({ s, active, onClick }: { s: CommSession; active: boolean; onClick: () => void }) {
    const title = s.contact_name || s.external_chat_id || "Contact";
    const last = (s.turns && s.turns.length ? s.turns[s.turns.length - 1].text : s.call_summary) || "—";
    return (
        <button
            onClick={onClick}
            className={`flex items-start gap-3 w-full text-left px-3 py-3 rounded-2xl transition-colors ${
                active ? "bg-b-surface2 ring-1 ring-s-subtle" : "hover:bg-b-surface1 dark:hover:bg-shade-04/40"
            }`}
        >
            <span className="flex justify-center items-center size-9 rounded-full bg-primary-01/10 shrink-0 mt-0.5">
                <Icon name={CHANNEL_ICON[(s.channel as "telegram") || "telegram"] || "send"} className="!size-4 fill-primary-01" />
            </span>
            <div className="grow min-w-0">
                <div className="flex items-center gap-2">
                    <span className="text-button text-t-primary truncate">{title}</span>
                    <span className="ml-auto shrink-0 text-caption text-t-tertiary">{fmtRelative(s.last_message_at)}</span>
                </div>
                <div className="text-body-2 text-t-secondary truncate">{last}</div>
            </div>
        </button>
    );
}

function Transcript({ session, onToast }: { session: CommSession; onToast: Toast }) {
    const turns = session.turns || [];
    return (
        <div>
            {/* grounding header — what the brain knows */}
            {(session.call_summary || session.outcome || session.interest != null) && (
                <div className="mb-4 p-4 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
                    <div className="flex items-center gap-2 mb-2">
                        <Icon name="chat-think" className="!size-4 fill-t-secondary" />
                        <span className="text-button text-t-primary">From the call</span>
                        {session.interest != null && (
                            <Badge variant={session.interest >= 70 ? "success" : "neutral"}>
                                interest {session.interest}/100
                            </Badge>
                        )}
                        <ConsentBadge purpose="service" />
                    </div>
                    {session.call_summary && <p className="text-body-2 text-t-secondary">{session.call_summary}</p>}
                    {session.next_action && (
                        <p className="mt-1.5 text-caption text-t-tertiary">Next: {session.next_action}</p>
                    )}
                </div>
            )}

            {/* the chat — contact RIGHT, Riya LEFT (CRM pattern) */}
            {turns.length === 0 ? (
                <div className="py-12 text-center text-body-2 text-t-tertiary">
                    No messages yet. When the contact replies, the thread appears here.
                </div>
            ) : (
                <div className="flex flex-col gap-3 max-h-[24rem] overflow-y-auto scrollbar scrollbar-thin scrollbar-thumb-t-tertiary/30 pr-1">
                    {turns.map((t, i) => (
                        <ChatBubble key={i} turn={t} />
                    ))}
                </div>
            )}

            {/* takeover composer (visual only in W1; live send in W4) */}
            <div className="mt-4 flex items-center gap-2 p-2 rounded-full bg-b-surface2 ring-1 ring-s-subtle">
                <input
                    className="grow bg-transparent px-3 text-body-2 text-t-primary outline-none placeholder:text-t-tertiary"
                    placeholder="Reply as a human… (Wave 4)"
                    disabled
                />
                <button
                    className="flex justify-center items-center size-9 rounded-full bg-primary-01/12 fill-primary-01 shrink-0 opacity-60"
                    onClick={() => onToast("Human takeover send ships in Wave 4.")}
                >
                    <Icon name="send" className="!size-4 fill-inherit" />
                </button>
            </div>
        </div>
    );
}

// CONTACT on the RIGHT (primary tint), Riya/AI on the LEFT — the CRM ChatBubble.
function ChatBubble({ turn }: { turn: SessionTurn }) {
    const isContact = turn.role === "user" || turn.role === "customer";
    return (
        <div className={`flex ${isContact ? "justify-end" : "justify-start"}`}>
            <div className="max-w-[82%]">
                <div className={`mb-1 px-1 text-caption text-t-tertiary ${isContact ? "text-right" : ""}`}>
                    {isContact ? "Contact" : "Riya"}
                </div>
                <div
                    className={`px-3.5 py-2.5 text-body-2 text-t-primary whitespace-pre-wrap break-words ${
                        isContact
                            ? "bg-primary-01/12 rounded-3xl rounded-br-lg"
                            : "bg-b-surface2 ring-1 ring-s-subtle ring-inset rounded-3xl rounded-bl-lg dark:bg-shade-04/60"
                    }`}
                >
                    {turn.text}
                </div>
            </div>
        </div>
    );
}

function EmptyList() {
    return (
        <div className="flex flex-col items-center text-center gap-2 py-16 px-4 text-t-tertiary">
            <Icon name="chat" className="!size-6 fill-t-tertiary" />
            <span className="text-body-2">No conversations yet.</span>
            <span className="text-caption">They appear when a contact messages your bot.</span>
        </div>
    );
}
