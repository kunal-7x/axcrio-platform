"use client";

import { useEffect, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import KpiCard from "@/components/KpiCard";
import Sparkline from "@/components/Sparkline";
import {
    getSupportHealth,
    getTickets,
    getTicketDetail,
    draftReply,
    sendReply,
    escalateTicket,
    claimTicket,
    resolveTicket,
    getCachedRole,
    canWrite,
    SupportActionError,
    type SupportTicket,
    type SupportMessage,
    type SupportHealth,
    type TicketDetail,
} from "./api";

/* ------------------------------------------------------------------ */
/* Formatting helpers                                                  */
/* ------------------------------------------------------------------ */

function fmtShort(d?: string | null) {
    if (!d) return "—";
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return "—";
    return dt.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function fmtRelative(d?: string | null) {
    if (!d) return "";
    const dt = new Date(d).getTime();
    if (isNaN(dt)) return "";
    const diff = Date.now() - dt;
    if (diff < 0) return "";
    const min = Math.round(diff / 60000);
    if (min < 1) return "just now";
    if (min < 60) return `${min}m ago`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const day = Math.round(hr / 24);
    if (day < 30) return `${day}d ago`;
    return "";
}

function initials(name: string, fallback: string) {
    const n = (name || "").trim();
    if (!n) return fallback;
    return n
        .split(/\s+/)
        .map((w) => w[0])
        .slice(0, 2)
        .join("")
        .toUpperCase();
}

/* ------------------------------------------------------------------ */
/* Semantic mappers (page-local — the shared lib/badges.tsx is         */
/* call-specific, so support builds its own status language).          */
/* ------------------------------------------------------------------ */

const STATUS_META: Record<string, { label: string; variant: BadgeVariant; dot?: boolean }> = {
    open: { label: "Open", variant: "info", dot: true },
    pending_human: { label: "Needs human", variant: "warning", dot: true },
    resolved: { label: "Resolved", variant: "success" },
    closed: { label: "Closed", variant: "neutral" },
};

function StatusBadge({ status }: { status?: string }) {
    const m = STATUS_META[status || ""] ?? {
        label: status || "—",
        variant: "neutral" as BadgeVariant,
    };
    return (
        <Badge variant={m.variant} dot={m.dot}>
            {m.label}
        </Badge>
    );
}

const PRIORITY_META: Record<string, { label: string; variant: BadgeVariant; dot?: boolean }> = {
    low: { label: "Low", variant: "neutral" },
    normal: { label: "Normal", variant: "neutral" },
    high: { label: "High", variant: "warning", dot: true },
    urgent: { label: "Urgent", variant: "danger", dot: true },
};

function PriorityBadge({ priority }: { priority?: string }) {
    const m = PRIORITY_META[priority || ""];
    if (!m || priority === "normal" || priority === "low") return null;
    return (
        <Badge variant={m.variant} dot={m.dot}>
            {m.label}
        </Badge>
    );
}

const SENTIMENT_META: Record<
    string,
    { label: string; variant: BadgeVariant; icon: string }
> = {
    positive: { label: "Positive", variant: "success", icon: "emoji" },
    neutral: { label: "Neutral", variant: "neutral", icon: "emoji" },
    negative: { label: "Negative", variant: "warning", icon: "emoji" },
    angry: { label: "Angry", variant: "danger", icon: "emoji" },
};

function SentimentBadge({ sentiment }: { sentiment?: string }) {
    const m = SENTIMENT_META[sentiment || ""];
    if (!m || sentiment === "neutral") return null;
    return <Badge variant={m.variant}>{m.label}</Badge>;
}

const CHANNEL_META: Record<string, { label: string; icon: string }> = {
    whatsapp: { label: "WhatsApp", icon: "chat" },
    voice: { label: "Voice", icon: "chat-think" },
    email: { label: "Email", icon: "envelope" },
    web: { label: "Web", icon: "desktop" },
};

function channelLabel(ch?: string) {
    return CHANNEL_META[ch || ""]?.label ?? (ch || "Web");
}
function channelIcon(ch?: string) {
    return CHANNEL_META[ch || ""]?.icon ?? "chat";
}

/* ================================================================== */
/* DETAIL MODAL — ticket thread + AI summary + agent actions          */
/* ================================================================== */

function TicketModal({
    ticketId,
    canAct,
    onClose,
    onChanged,
}: {
    ticketId: string;
    canAct: boolean;
    onClose: () => void;
    onChanged: () => void;
}) {
    const [detail, setDetail] = useState<TicketDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState<string>("");
    const [notice, setNotice] = useState<{ kind: "ok" | "warn"; text: string } | null>(null);
    const [replyText, setReplyText] = useState("");

    async function load() {
        try {
            const d = await getTicketDetail(ticketId);
            setDetail(d);
        } catch (e) {
            setError(
                e instanceof SupportActionError && e.code === "dormant"
                    ? "This ticket isn't available yet — the support service is still being configured."
                    : e instanceof Error
                    ? e.message
                    : "Failed to load ticket"
            );
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [ticketId]);

    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        document.addEventListener("keydown", handler);
        return () => document.removeEventListener("keydown", handler);
    }, [onClose]);

    function handleBackdrop(e: React.MouseEvent<HTMLDivElement>) {
        if (e.target === e.currentTarget) onClose();
    }

    async function runAction(
        key: string,
        fn: () => Promise<unknown>,
        okMsg: string
    ) {
        setBusy(key);
        setNotice(null);
        try {
            await fn();
            setNotice({ kind: "ok", text: okMsg });
            setReplyText("");
            await load();
            onChanged();
        } catch (e) {
            const msg =
                e instanceof SupportActionError
                    ? e.message
                    : e instanceof Error
                    ? e.message
                    : "Something went wrong";
            setNotice({ kind: "warn", text: msg });
        } finally {
            setBusy("");
        }
    }

    const ticket = detail?.ticket;
    const messages = detail?.messages ?? [];
    const lastInbound = useMemo(
        () => [...messages].reverse().find((m) => m.direction === "inbound"),
        [messages]
    );

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-shade-01/50 backdrop-blur-sm"
            onClick={handleBackdrop}
        >
            <div className="surface w-full max-w-2xl max-h-[90vh] flex flex-col rise-in overflow-hidden">
                {/* ---- Hero header ---- */}
                <div className="relative shrink-0 px-6 pt-6 pb-5 border-b border-s-subtle">
                    <div
                        className="pointer-events-none absolute inset-x-0 top-0 h-24 opacity-60"
                        style={{
                            background:
                                "radial-gradient(120% 100% at 0% 0%, rgba(42,133,255,0.10), transparent 70%)",
                        }}
                    />
                    <div className="relative flex items-start justify-between gap-4">
                        <div className="flex items-center gap-3.5 min-w-0">
                            <span className="flex items-center justify-center size-12 shrink-0 rounded-2xl bg-primary-01/12 text-primary-01 text-sub-title-2 font-semibold tabular-nums">
                                {loading ? (
                                    <Icon name="chat" className="size-5 fill-primary-01" />
                                ) : (
                                    initials(ticket?.contact_name || "", "?")
                                )}
                            </span>
                            <div className="min-w-0">
                                <h2 className="text-h6 text-t-primary truncate">
                                    {loading
                                        ? "Loading ticket…"
                                        : ticket?.subject ||
                                          ticket?.contact_name ||
                                          "Support ticket"}
                                </h2>
                                <div className="flex items-center gap-2 mt-0.5 text-caption text-t-secondary">
                                    {ticket?.contact_name && (
                                        <span className="truncate">{ticket.contact_name}</span>
                                    )}
                                    {ticket?.contact_name &&
                                        (ticket?.contact_phone || ticket?.contact_email) && (
                                            <span className="text-t-tertiary">·</span>
                                        )}
                                    {(ticket?.contact_phone || ticket?.contact_email) && (
                                        <span className="truncate tabular-nums">
                                            {ticket?.contact_phone || ticket?.contact_email}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="flex items-center justify-center size-8 shrink-0 rounded-full text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary dark:hover:bg-shade-04/60"
                            aria-label="Close"
                        >
                            <Icon name="close" className="size-4 fill-current" />
                        </button>
                    </div>

                    {!loading && ticket && (
                        <div className="relative flex flex-wrap items-center gap-2 mt-4">
                            <StatusBadge status={ticket.status} />
                            <PriorityBadge priority={ticket.priority} />
                            <SentimentBadge sentiment={ticket.sentiment} />
                            <span className="inline-flex items-center gap-1.5 h-6 pl-2 pr-2.5 rounded-full bg-b-surface1 text-caption text-t-secondary dark:bg-shade-04/60">
                                <Icon
                                    name={channelIcon(ticket.channel)}
                                    className="size-3 fill-t-tertiary"
                                />
                                {channelLabel(ticket.channel)}
                            </span>
                            {ticket.assigned_to && ticket.assigned_to !== "ai" && (
                                <span className="text-caption text-t-tertiary">
                                    Assigned to {ticket.assigned_to}
                                </span>
                            )}
                            {ticket.assigned_to === "ai" && (
                                <span className="inline-flex items-center gap-1 text-caption text-primary-01">
                                    <Icon name="feather" className="size-3 fill-primary-01" />
                                    Handled by AI
                                </span>
                            )}
                        </div>
                    )}
                </div>

                {/* ---- Body ---- */}
                <div className="overflow-y-auto px-6 py-5 space-y-5 scrollbar-thin">
                    {loading && (
                        <div className="space-y-4">
                            <div className="skeleton h-20" />
                            <div className="skeleton h-16" />
                            <div className="skeleton h-16" />
                        </div>
                    )}

                    {error && (
                        <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2">
                            <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                            {error}
                        </div>
                    )}

                    {detail && ticket && (
                        <>
                            {/* AI handover summary */}
                            {ticket.ai_summary && (
                                <div className="p-4 rounded-2xl bg-b-surface1/70 border border-s-subtle dark:bg-shade-04/30">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Icon name="feather" className="size-3.5 fill-t-tertiary" />
                                        <div className="text-overline uppercase tracking-[0.06em] text-t-tertiary">AI Summary</div>
                                    </div>
                                    <p className="text-body-2 text-t-primary leading-relaxed">
                                        {ticket.ai_summary}
                                    </p>
                                </div>
                            )}

                            {/* Escalation banner */}
                            {ticket.escalated && (
                                <div className="flex gap-3 p-4 rounded-2xl bg-primary-05/[0.08] border border-primary-05/25">
                                    <span className="flex items-center justify-center size-8 shrink-0 rounded-xl bg-primary-05/15">
                                        <Icon name="bell" className="size-4 fill-primary-05" />
                                    </span>
                                    <div>
                                        <div className="text-overline uppercase tracking-[0.06em] text-primary-05 mb-1">
                                            Escalated to a human
                                        </div>
                                        <p className="text-body-2 text-t-primary">
                                            Reason:{" "}
                                            {ticket.escalation_reason.replace(/_/g, " ") ||
                                                "human requested"}
                                        </p>
                                    </div>
                                </div>
                            )}

                            {/* Thread */}
                            <div>
                                <div className="flex items-center justify-between mb-3">
                                    <div className="text-overline uppercase tracking-[0.06em] text-t-tertiary">Conversation</div>
                                    <span className="text-caption text-t-tertiary tabular-nums">
                                        {messages.length} message
                                        {messages.length === 1 ? "" : "s"}
                                    </span>
                                </div>
                                {messages.length === 0 ? (
                                    <div className="state-block">
                                        <span className="state-glyph">
                                            <Icon name="chat" className="fill-inherit" />
                                        </span>
                                        <div className="state-title">No messages yet</div>
                                        <div className="state-sub">
                                            Inbound customer turns and replies will appear here.
                                        </div>
                                    </div>
                                ) : (
                                    <div className="space-y-3 pl-1">
                                        {messages.map((m) => (
                                            <ThreadBubble key={m.id} m={m} />
                                        ))}
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </div>

                {/* ---- Action footer ---- */}
                {detail && ticket && (
                    <div className="shrink-0 border-t border-s-subtle px-6 py-4 space-y-3">
                        {notice && (
                            <div
                                className={`flex items-center gap-2 px-3 py-2 rounded-xl text-caption ${
                                    notice.kind === "ok"
                                        ? "bg-primary-02/10 text-primary-02"
                                        : "bg-primary-05/10 text-primary-05"
                                }`}
                            >
                                <Icon
                                    name={notice.kind === "ok" ? "check-circle" : "info"}
                                    className="size-3.5 fill-current shrink-0"
                                />
                                {notice.text}
                            </div>
                        )}

                        {!canAct && (
                            <div className="text-caption text-t-tertiary">
                                You have read-only access — ask a manager to act on this ticket.
                            </div>
                        )}

                        {canAct && (
                            <>
                                {/* Human reply composer */}
                                <div className="flex items-end gap-2">
                                    <textarea
                                        value={replyText}
                                        onChange={(e) => setReplyText(e.target.value)}
                                        rows={2}
                                        placeholder="Write a reply to the customer…"
                                        className="flex-1 resize-none rounded-2xl border border-s-subtle bg-b-surface1/60 px-3.5 py-2.5 text-body-2 text-t-primary placeholder:text-t-tertiary outline-none focus:border-primary-01/40 dark:bg-shade-04/30"
                                    />
                                    <button
                                        disabled={!replyText.trim() || busy !== ""}
                                        onClick={() =>
                                            runAction(
                                                "reply",
                                                () => sendReply(ticket.id, replyText.trim()),
                                                "Reply sent."
                                            )
                                        }
                                        className="shrink-0 h-10 px-4 rounded-2xl bg-primary-01 text-white text-button font-medium transition-opacity disabled:opacity-40 hover:opacity-90"
                                    >
                                        {busy === "reply" ? "Sending…" : "Send"}
                                    </button>
                                </div>

                                {/* Quick actions */}
                                <div className="flex flex-wrap items-center gap-2">
                                    <ActionButton
                                        icon="feather"
                                        label="AI draft"
                                        busy={busy === "draft"}
                                        disabled={busy !== ""}
                                        onClick={() =>
                                            runAction(
                                                "draft",
                                                () =>
                                                    draftReply(
                                                        ticket.id,
                                                        lastInbound?.body || undefined
                                                    ),
                                                "AI draft generated."
                                            )
                                        }
                                    />
                                    {ticket.assigned_to === "ai" && (
                                        <ActionButton
                                            icon="check-circle"
                                            label="Claim"
                                            busy={busy === "claim"}
                                            disabled={busy !== ""}
                                            onClick={() =>
                                                runAction(
                                                    "claim",
                                                    () => claimTicket(ticket.id),
                                                    "Ticket claimed."
                                                )
                                            }
                                        />
                                    )}
                                    {!ticket.escalated && (
                                        <ActionButton
                                            icon="bell"
                                            label="Escalate"
                                            tone="warn"
                                            busy={busy === "escalate"}
                                            disabled={busy !== ""}
                                            onClick={() =>
                                                runAction(
                                                    "escalate",
                                                    () => escalateTicket(ticket.id),
                                                    "Ticket escalated to a human."
                                                )
                                            }
                                        />
                                    )}
                                    {ticket.status !== "resolved" &&
                                        ticket.status !== "closed" && (
                                            <ActionButton
                                                icon="check-circle"
                                                label="Resolve"
                                                tone="success"
                                                busy={busy === "resolve"}
                                                disabled={busy !== ""}
                                                onClick={() =>
                                                    runAction(
                                                        "resolve",
                                                        () => resolveTicket(ticket.id),
                                                        "Ticket resolved."
                                                    )
                                                }
                                            />
                                        )}
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

function ThreadBubble({ m }: { m: SupportMessage }) {
    const isInbound = m.direction === "inbound";
    const isAi = m.author === "ai";
    const avatarLabel = isInbound ? "C" : isAi ? "AI" : "H";
    return (
        <div className={`flex gap-2.5 ${isInbound ? "flex-row" : "flex-row-reverse"}`}>
            <span
                className={`shrink-0 flex items-center justify-center size-7 rounded-full text-caption font-semibold ${
                    isInbound
                        ? "bg-b-surface1 text-t-secondary dark:bg-shade-04/60"
                        : "bg-primary-01/12 text-primary-01"
                }`}
            >
                {avatarLabel}
            </span>
            <div className={`flex flex-col gap-1 max-w-[80%] ${isInbound ? "" : "items-end"}`}>
                <div
                    className={`px-3.5 py-2.5 rounded-2xl text-body-2 leading-relaxed ${
                        isInbound
                            ? "bg-b-surface1 text-t-primary rounded-tl-md dark:bg-shade-04/40"
                            : "bg-primary-01/10 text-t-primary rounded-tr-md"
                    }`}
                >
                    {m.body}
                </div>
                <div className="flex items-center gap-1.5 px-1 text-caption text-t-tertiary">
                    <span>{isInbound ? "Customer" : isAi ? "AI agent" : m.author || "Agent"}</span>
                    {m.kb_grounded && (
                        <span className="inline-flex items-center gap-1 text-primary-02">
                            <Icon name="check-circle" className="size-3 fill-primary-02" />
                            KB
                        </span>
                    )}
                    {!isInbound && m.confidence > 0 && (
                        <span className="tabular-nums">· {m.confidence}% conf.</span>
                    )}
                    {m.at && <span>· {fmtRelative(m.at)}</span>}
                </div>
            </div>
        </div>
    );
}

function ActionButton({
    icon,
    label,
    onClick,
    busy,
    disabled,
    tone = "neutral",
}: {
    icon: string;
    label: string;
    onClick: () => void;
    busy?: boolean;
    disabled?: boolean;
    tone?: "neutral" | "success" | "warn";
}) {
    const toneCls =
        tone === "success"
            ? "fill-primary-02"
            : tone === "warn"
            ? "fill-primary-05"
            : "fill-t-secondary";
    return (
        <button
            onClick={onClick}
            disabled={disabled}
            className="inline-flex items-center gap-1.5 h-9 px-3 rounded-2xl border border-s-subtle bg-b-surface1/60 text-button text-t-primary transition-colors hover:bg-b-surface1 disabled:opacity-40 dark:bg-shade-04/30 dark:hover:bg-shade-04/50"
        >
            <Icon name={icon} className={`size-3.5 ${toneCls}`} />
            {busy ? "…" : label}
        </button>
    );
}

/* ================================================================== */
/* COMING-SOON / DORMANT STATE (premium, not generic)                 */
/* ================================================================== */

function ComingSoon() {
    return (
        <div className="surface p-10 rise-in text-center max-w-2xl mx-auto">
            <div
                className="pointer-events-none absolute"
                aria-hidden
            />
            <span className="mx-auto flex items-center justify-center size-16 rounded-3xl bg-primary-01/10 mb-5">
                <Icon name="chat-think" className="size-7 fill-primary-01" />
            </span>
            <h2 className="text-h5 text-t-primary mb-2">AI Customer Support is on the way</h2>
            <p className="text-body-2 text-t-secondary max-w-md mx-auto mb-6">
                Your AI support agent will answer customers across WhatsApp, voice, email and web —
                grounded in your Knowledge Base — and escalate to a human the moment it matters. The
                workspace is ready; it activates as soon as the service is configured.
            </p>
            <div className="grid grid-cols-3 gap-3 max-sm:grid-cols-1 text-left">
                {[
                    {
                        icon: "feather",
                        title: "KB-grounded replies",
                        sub: "Answers cite your own knowledge, or escalate when unsure.",
                    },
                    {
                        icon: "chat",
                        title: "Omnichannel inbox",
                        sub: "WhatsApp, voice, email and web in one ticket stream.",
                    },
                    {
                        icon: "bell",
                        title: "Smart handover",
                        sub: "Angry, legal or refund cases route to a human with a summary.",
                    },
                ].map((f) => (
                    <div
                        key={f.title}
                        className="p-4 rounded-2xl bg-b-surface1/60 border border-s-subtle dark:bg-shade-04/30"
                    >
                        <span className="flex items-center justify-center size-9 rounded-xl bg-b-surface2 mb-2.5 dark:bg-shade-04/60">
                            <Icon name={f.icon} className="size-4 fill-t-secondary" />
                        </span>
                        <div className="text-body-2 font-medium text-t-primary mb-1">{f.title}</div>
                        <div className="text-caption text-t-tertiary leading-relaxed">{f.sub}</div>
                    </div>
                ))}
            </div>
            <div className="mt-6 inline-flex items-center gap-2 h-8 px-3.5 rounded-full bg-b-surface1 text-caption text-t-secondary dark:bg-shade-04/60">
                <span className="relative flex size-2">
                    <span className="absolute inline-flex h-full w-full rounded-full bg-primary-05 opacity-60 animate-ping" />
                    <span className="relative inline-flex size-2 rounded-full bg-primary-05" />
                </span>
                Not configured yet
            </div>
        </div>
    );
}

/* ================================================================== */
/* MAIN PAGE                                                           */
/* ================================================================== */

const STATUS_FILTERS: { key: string; label: string }[] = [
    { key: "", label: "All" },
    { key: "open", label: "Open" },
    { key: "pending_human", label: "Needs human" },
    { key: "resolved", label: "Resolved" },
    { key: "closed", label: "Closed" },
];

export default function SupportPage() {
    const [health, setHealth] = useState<SupportHealth | null>(null);
    const [healthChecked, setHealthChecked] = useState(false);
    const [tickets, setTickets] = useState<SupportTicket[]>([]);
    const [loading, setLoading] = useState(true);
    const [statusFilter, setStatusFilter] = useState("");
    const [selected, setSelected] = useState<string | null>(null);
    const [role] = useState(() => getCachedRole());

    const canAct = canWrite(role);

    async function refresh() {
        const t = await getTickets({ limit: 200 });
        setTickets(t);
    }

    useEffect(() => {
        let alive = true;
        (async () => {
            const h = await getSupportHealth();
            if (!alive) return;
            setHealth(h);
            setHealthChecked(true);
            if (h) {
                await refresh();
            }
            if (alive) setLoading(false);
        })();
        return () => {
            alive = false;
        };
    }, []);

    const visible = useMemo(
        () => (statusFilter ? tickets.filter((t) => t.status === statusFilter) : tickets),
        [tickets, statusFilter]
    );

    /* ---- Real derived metrics (no fabricated deltas) ---- */
    const m = useMemo(() => {
        const total = tickets.length;
        const open = tickets.filter((t) => t.status === "open").length;
        const needsHuman = tickets.filter((t) => t.status === "pending_human").length;
        const resolved = tickets.filter(
            (t) => t.status === "resolved" || t.status === "closed"
        ).length;
        const aiHandled = tickets.filter((t) => t.assigned_to === "ai").length;
        const escalated = tickets.filter((t) => t.escalated).length;
        const negative = tickets.filter(
            (t) => t.sentiment === "negative" || t.sentiment === "angry"
        ).length;

        const resolutionRate = total > 0 ? Math.round((resolved / total) * 100) : 0;
        const aiRate = total > 0 ? Math.round((aiHandled / total) * 100) : 0;

        // Channel mix segments (real counts).
        const byChannel = tickets.reduce<Record<string, number>>((acc, t) => {
            const ch = t.channel || "web";
            acc[ch] = (acc[ch] || 0) + 1;
            return acc;
        }, {});
        const channelColors: Record<string, string> = {
            whatsapp: "var(--chart-green)",
            voice: "var(--primary-01)",
            email: "var(--primary-04)",
            web: "var(--primary-05)",
        };
        const segments = Object.entries(byChannel)
            .map(([key, value]) => ({
                key,
                label: channelLabel(key),
                value,
                color: channelColors[key] || "var(--chart-min)",
            }))
            .sort((a, b) => b.value - a.value);

        // Tickets-per-day time series for the volume sparkline.
        const byDay = new Map<string, number>();
        for (const t of tickets) {
            const src = t.created_at;
            if (!src) continue;
            const dt = new Date(src);
            if (isNaN(dt.getTime())) continue;
            const key = dt.toISOString().slice(0, 10);
            byDay.set(key, (byDay.get(key) || 0) + 1);
        }
        const days = [...byDay.keys()].sort();
        const volumeSeries = days.map((d) => byDay.get(d)!);
        const activeDays = days.length;

        return {
            total,
            open,
            needsHuman,
            resolved,
            aiHandled,
            escalated,
            negative,
            resolutionRate,
            aiRate,
            segments,
            volumeSeries,
            activeDays,
        };
    }, [tickets]);

    const dormant = healthChecked && health === null;
    const hasData = !loading && !dormant && tickets.length > 0;

    return (
        <Layout title="Customer Support">
            {selected && (
                <TicketModal
                    ticketId={selected}
                    canAct={canAct}
                    onClose={() => setSelected(null)}
                    onChanged={refresh}
                />
            )}

            {/* Dormant / not-configured */}
            {dormant && <ComingSoon />}

            {/* Loading skeleton */}
            {!dormant && loading && (
                <div className="grid grid-cols-4 gap-3 mb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    {[...Array(4)].map((_, i) => (
                        <div key={i} className="skeleton h-28" />
                    ))}
                </div>
            )}

            {/* Configured but empty */}
            {!dormant && !loading && tickets.length === 0 && (
                <Card title="Tickets">
                    <div className="state-block">
                        <span className="state-glyph">
                            <Icon name="chat" className="fill-inherit" />
                        </span>
                        <div className="state-title">No tickets yet</div>
                        <div className="state-sub">
                            Support is live. New customer conversations across WhatsApp, voice, email
                            and web will appear here as tickets.
                        </div>
                    </div>
                </Card>
            )}

            {/* ---- Context strip ---- */}
            {hasData && (
                <div className="flex items-center justify-between gap-4 mb-3 px-1 rise-in">
                    <div className="flex items-center gap-2 text-body-2 text-t-secondary">
                        <span className="text-t-primary font-medium tabular-nums">{m.total}</span>
                        ticket{m.total === 1 ? "" : "s"}
                        {m.activeDays > 0 && (
                            <>
                                <span className="text-t-tertiary">·</span>
                                <span>
                                    {m.activeDays} active day{m.activeDays === 1 ? "" : "s"}
                                </span>
                            </>
                        )}
                    </div>
                    {m.needsHuman > 0 && (
                        <span className="inline-flex items-center gap-2 h-7 pl-2.5 pr-3 rounded-full bg-primary-05/10 text-primary-05 text-caption font-medium">
                            <span className="relative flex size-2">
                                <span className="absolute inline-flex h-full w-full rounded-full bg-primary-05 opacity-60 animate-ping" />
                                <span className="relative inline-flex size-2 rounded-full bg-primary-05" />
                            </span>
                            {m.needsHuman} awaiting a human
                        </span>
                    )}
                </div>
            )}

            {/* ---- KPI cards ---- */}
            {hasData && (
                <div className="grid grid-cols-4 gap-3 mb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                    <KpiCard
                        label="Open Tickets"
                        value={m.open.toLocaleString()}
                        icon="chat"
                        tone="info"
                        spark={m.volumeSeries.length > 1 ? m.volumeSeries : undefined}
                        sub={
                            m.needsHuman > 0
                                ? `${m.needsHuman} need a human`
                                : "all being handled"
                        }
                    />
                    <KpiCard
                        label="Resolution Rate"
                        value={`${m.resolutionRate}%`}
                        icon="check-circle"
                        tone="success"
                        meter={m.resolutionRate / 100}
                        sub={`${m.resolved.toLocaleString()} of ${m.total.toLocaleString()} closed`}
                    />
                    <KpiCard
                        label="AI Handled"
                        value={`${m.aiRate}%`}
                        icon="feather"
                        tone="neutral"
                        meter={m.aiRate / 100}
                        sub={`${m.aiHandled.toLocaleString()} resolved by AI`}
                    />
                    <KpiCard
                        label="Needs Attention"
                        value={(m.escalated + m.negative).toLocaleString()}
                        icon="bell"
                        tone="warning"
                        sub={`${m.escalated} escalated · ${m.negative} unhappy`}
                    />
                </div>
            )}

            {/* ---- Activity strip ---- */}
            {hasData && m.volumeSeries.length > 1 && m.segments.length > 0 && (
                <div className="grid grid-cols-3 gap-3 mb-3 max-lg:grid-cols-1">
                    <Card
                        className="col-span-2 max-lg:col-span-1"
                        title="Ticket volume"
                        headContent={
                            <span className="ml-auto kpi-glyph fill-primary-01">
                                <Icon name="chart" className="fill-inherit" />
                            </span>
                        }
                    >
                        <div className="px-5 pb-5 max-lg:px-3">
                            <div className="text-body-2 text-t-secondary mb-4">
                                New tickets over the last {m.activeDays} active day
                                {m.activeDays === 1 ? "" : "s"}
                            </div>
                            <Sparkline
                                data={m.volumeSeries}
                                color="var(--primary-01)"
                                width={640}
                                height={88}
                                strokeWidth={2}
                                className="w-full h-auto"
                            />
                        </div>
                    </Card>

                    <Card title="Channel mix">
                        <div className="px-5 pb-5 max-lg:px-3">
                            <div className="text-body-2 text-t-secondary mb-4">
                                Where {m.total} ticket{m.total === 1 ? "" : "s"} came from
                            </div>
                            <div className="flex h-2.5 w-full rounded-full overflow-hidden bg-b-surface1 dark:bg-shade-04/60">
                                {m.segments.map((s) => (
                                    <div
                                        key={s.key}
                                        title={`${s.label}: ${s.value}`}
                                        style={{
                                            width: `${(s.value / m.total) * 100}%`,
                                            background: s.color,
                                        }}
                                    />
                                ))}
                            </div>
                            <div className="mt-4 space-y-2.5">
                                {m.segments.map((s) => (
                                    <div
                                        key={s.key}
                                        className="flex items-center gap-2.5 text-body-2"
                                    >
                                        <span
                                            className="size-2.5 shrink-0 rounded-full"
                                            style={{ background: s.color }}
                                        />
                                        <span className="text-t-secondary mr-auto">{s.label}</span>
                                        <span className="text-t-primary font-medium tabular-nums">
                                            {s.value}
                                        </span>
                                        <span className="text-t-tertiary tabular-nums w-10 text-right">
                                            {Math.round((s.value / m.total) * 100)}%
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </Card>
                </div>
            )}

            {/* ---- Ticket table ---- */}
            {!dormant && !loading && tickets.length > 0 && (
                <Card
                    title="Tickets"
                    headContent={
                        <div className="flex items-center gap-1.5 mr-3 max-md:hidden">
                            {STATUS_FILTERS.map((f) => {
                                const active = statusFilter === f.key;
                                return (
                                    <button
                                        key={f.key || "all"}
                                        onClick={() => setStatusFilter(f.key)}
                                        className={`h-8 px-3 rounded-full text-caption font-medium transition-colors ${
                                            active
                                                ? "bg-primary-01/12 text-primary-01"
                                                : "text-t-secondary hover:bg-b-surface1 dark:hover:bg-shade-04/50"
                                        }`}
                                    >
                                        {f.label}
                                    </button>
                                );
                            })}
                        </div>
                    }
                >
                    <div className="overflow-x-auto">
                        <table className="data-table is-clickable">
                            <thead>
                                <tr>
                                    <th>Customer</th>
                                    <th>Subject</th>
                                    <th>Channel</th>
                                    <th>Status</th>
                                    <th>Updated</th>
                                    <th className="text-right">Messages</th>
                                </tr>
                            </thead>
                            <tbody>
                                {visible.length === 0 ? (
                                    <tr>
                                        <td colSpan={6}>
                                            <div className="state-block">
                                                <span className="state-glyph">
                                                    <Icon name="filters" className="fill-inherit" />
                                                </span>
                                                <div className="state-title">
                                                    No tickets match this filter
                                                </div>
                                                <div className="state-sub">
                                                    Try a different status above.
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    visible.map((t) => (
                                        <tr
                                            key={t.id}
                                            onClick={() => setSelected(t.id)}
                                            title="Open ticket"
                                        >
                                            <td>
                                                <div className="flex items-center gap-3">
                                                    <span className="flex items-center justify-center size-9 shrink-0 rounded-xl bg-b-surface1 text-caption font-semibold text-t-secondary dark:bg-shade-04/60">
                                                        {initials(t.contact_name, "?")}
                                                    </span>
                                                    <div className="min-w-0">
                                                        <div className="font-medium text-t-primary truncate">
                                                            {t.contact_name || "Unknown"}
                                                        </div>
                                                        <div className="text-caption text-t-tertiary truncate tabular-nums">
                                                            {t.contact_phone ||
                                                                t.contact_email ||
                                                                "—"}
                                                        </div>
                                                    </div>
                                                </div>
                                            </td>
                                            <td className="max-w-[16rem]">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-t-primary truncate">
                                                        {t.subject || "(no subject)"}
                                                    </span>
                                                    <PriorityBadge priority={t.priority} />
                                                    <SentimentBadge sentiment={t.sentiment} />
                                                </div>
                                            </td>
                                            <td>
                                                <span className="inline-flex items-center gap-1.5 text-t-secondary">
                                                    <Icon
                                                        name={channelIcon(t.channel)}
                                                        className="size-3.5 fill-t-tertiary"
                                                    />
                                                    {channelLabel(t.channel)}
                                                </span>
                                            </td>
                                            <td>
                                                <StatusBadge status={t.status} />
                                            </td>
                                            <td>
                                                <div className="text-t-secondary">
                                                    {fmtShort(t.updated_at)}
                                                </div>
                                                {fmtRelative(t.updated_at) && (
                                                    <div className="text-caption text-t-tertiary">
                                                        {fmtRelative(t.updated_at)}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="text-right td-num text-t-secondary tabular-nums">
                                                {t.msg_count ?? 0}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </Card>
            )}
        </Layout>
    );
}
