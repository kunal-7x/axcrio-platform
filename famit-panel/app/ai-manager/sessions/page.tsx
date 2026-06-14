"use client";

// AI Manager — INBOUND CALL HISTORY (ai_manager_sessions)
//
// Lists every inbound call session for this tenant (GET /ai-manager/sessions, RLS-
// scoped from the auth token). Clicking a row opens the full ordered transcript as a
// chat view: AI agent turns on the LEFT (neutral surface), customer turns on the RIGHT
// (primary tint) — the same bubble convention as the CRM call-transcript chat-view.
//
// The transcript is fetched via GET /calls/{session_id}/transcript which resolves
// inbound session IDs through the ai_manager_session_turns table (already proven live:
// 25 turns returned for session vs_07c19d8f8b0b). Dormant-safe throughout: 404/503/
// network failures degrade to an empty list / calm "no sessions yet" state.

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Modal from "@/components/Modal";
import { getAimSessions, sessionId, sessionCaller, type AimSession } from "../_lib";
import { fmt } from "../_shared";

// ── Transcript types (mirrors crm/client.ts) ─────────────────────────────────

type TranscriptRole = "ai" | "customer";

type TranscriptTurn = {
    role: TranscriptRole;
    text: string;
    ts: string;
    seq: number;
};

type CallTranscript = {
    call_id: string;
    direction: string;
    phone: string;
    name: string;
    turns: TranscriptTurn[];
    total: number;
};

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

function authHeaders(): HeadersInit {
    const t = getToken();
    return t ? { "X-Auth": t } : {};
}

function normRole(role: string): TranscriptRole {
    const r = (role || "").toLowerCase().trim();
    return r === "user" || r === "customer" || r === "human" || r === "caller" || r === "lead"
        ? "customer"
        : "ai";
}

async function fetchTranscript(sessionIdStr: string): Promise<CallTranscript> {
    const empty: CallTranscript = { call_id: sessionIdStr, direction: "inbound", phone: "", name: "", turns: [], total: 0 };
    if (!sessionIdStr) return empty;
    try {
        const res = await fetch(`${BASE}/calls/${encodeURIComponent(sessionIdStr)}/transcript`, {
            headers: authHeaders(),
        });
        if (res.status === 401 && typeof window !== "undefined") {
            localStorage.removeItem("famit_token");
            localStorage.removeItem("famit_me");
            window.location.href = "/login";
            return empty;
        }
        if (!res.ok) return empty;
        const data = (await res.json()) as Record<string, unknown>;
        const rawTurns = Array.isArray((data as { turns?: unknown }).turns)
            ? (data as { turns: Record<string, unknown>[] }).turns
            : [];
        const turns: TranscriptTurn[] = rawTurns
            .map((t, i) => {
                const text = String(t.text ?? t.content ?? "").trim();
                if (!text) return null;
                const seq = Number(t.seq);
                return {
                    role: normRole(String(t.role ?? "")),
                    text,
                    ts: String(t.ts ?? t.created_at ?? ""),
                    seq: Number.isFinite(seq) ? seq : i,
                } as TranscriptTurn;
            })
            .filter((t): t is TranscriptTurn => t !== null);
        return {
            call_id: String(data.call_id ?? sessionIdStr),
            direction: String(data.direction ?? "inbound"),
            phone: String(data.phone ?? ""),
            name: String(data.name ?? ""),
            turns,
            total: Number.isFinite(Number(data.total)) ? Number(data.total) : turns.length,
        };
    } catch {
        return empty;
    }
}

// ── Formatters ───────────────────────────────────────────────────────────────

function fmtDuration(a?: string | null, b?: string | null): string {
    if (!a || !b) return "—";
    try {
        const ms = new Date(b).getTime() - new Date(a).getTime();
        if (!Number.isFinite(ms) || ms < 0) return "—";
        const s = Math.round(ms / 1000);
        if (s < 60) return `${s}s`;
        return `${Math.floor(s / 60)}m ${s % 60}s`;
    } catch {
        return "—";
    }
}

function fmtRelative(d?: string | null): string {
    if (!d) return "—";
    try {
        const ms = Date.now() - new Date(d).getTime();
        if (ms < 0) return new Date(d).toLocaleString();
        const s = Math.round(ms / 1000);
        if (s < 60) return "just now";
        const m = Math.round(s / 60);
        if (m < 60) return `${m}m ago`;
        const h = Math.round(m / 60);
        if (h < 24) return `${h}h ago`;
        const dy = Math.round(h / 24);
        return `${dy}d ago`;
    } catch {
        return "—";
    }
}

function statusVariant(s?: string): { bg: string; text: string } {
    const t = (s || "").toLowerCase();
    if (t === "completed") return { bg: "bg-primary-04/12", text: "text-primary-04" };
    if (t === "active") return { bg: "bg-primary-01/12", text: "text-primary-01" };
    if (t === "failed") return { bg: "bg-primary-03/12", text: "text-primary-03" };
    return { bg: "bg-b-surface1 dark:bg-shade-04/60", text: "text-t-secondary" };
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AimSessionsPage() {
    const [sessions, setSessions] = useState<AimSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState("");

    // Transcript slide-over state
    const [selectedSession, setSelectedSession] = useState<AimSession | null>(null);
    const [transcript, setTranscript] = useState<CallTranscript | null>(null);
    const [transcriptLoading, setTranscriptLoading] = useState(false);

    useEffect(() => {
        setLoading(true);
        getAimSessions({ limit: 100 }).then((r) => {
            if (r.kind === "dormant") {
                setDormant(true);
            } else if (r.kind === "error") {
                setError(r.message);
            } else {
                setSessions(r.data.sessions ?? []);
            }
        }).finally(() => setLoading(false));
    }, []);

    const openTranscript = useCallback((s: AimSession) => {
        const id = sessionId(s);
        if (!id) return;
        setSelectedSession(s);
        setTranscript(null);
        setTranscriptLoading(true);
        fetchTranscript(id)
            .then((t) => setTranscript(t))
            .finally(() => setTranscriptLoading(false));
    }, []);

    const closeTranscript = useCallback(() => {
        setSelectedSession(null);
        setTranscript(null);
        setTranscriptLoading(false);
    }, []);

    const phoneOf = (s: AimSession) => {
        const raw = sessionCaller(s);
        return raw || "—";
    };

    return (
        <Layout title="Inbound Call History">
            {/* Breadcrumb */}
            <div className="mb-4 flex items-center gap-2 text-caption text-t-tertiary">
                <Link
                    href="/ai-manager"
                    className="hover:text-t-secondary transition-colors"
                >
                    AI Manager
                </Link>
                <Icon name="arrow" className="size-3 fill-t-tertiary" />
                <span className="text-t-secondary">Inbound Calls</span>
            </div>

            <Card
                title="Inbound Call Sessions"
                headContent={
                    !loading && sessions.length > 0 ? (
                        <span className="ml-auto text-caption text-t-tertiary pr-5 td-num">
                            {sessions.length}
                        </span>
                    ) : undefined
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {loading ? (
                        <div className="space-y-3 pt-1">
                            {[...Array(5)].map((_, i) => (
                                <div key={i} className="skeleton h-14 w-full rounded-2xl" />
                            ))}
                        </div>
                    ) : dormant ? (
                        <EmptyState
                            icon="chat"
                            title="Inbound call sessions coming soon"
                            sub="Once the AI Manager voice agent handles inbound calls, each session — caller, transcript, commands executed, and outcome — will appear here."
                        />
                    ) : error ? (
                        <div className="flex items-start gap-2 p-3 rounded-xl bg-primary-03/8 text-primary-03 text-body-2">
                            <Icon name="info" className="size-4 fill-primary-03 shrink-0 mt-0.5" />
                            {error}
                        </div>
                    ) : sessions.length === 0 ? (
                        <EmptyState
                            icon="chat"
                            title="No sessions yet"
                            sub="Every inbound call from a registered number will appear here — caller, channel, transcript, and any commands the AI Manager executed."
                        />
                    ) : (
                        <div className="overflow-x-auto -mx-5 max-lg:-mx-3">
                            <table className="w-full min-w-[640px] text-body-2 border-collapse">
                                <thead>
                                    <tr className="border-b border-s-subtle">
                                        <th className="text-left text-caption text-t-tertiary font-medium py-2 px-5 max-lg:px-3">Caller</th>
                                        <th className="text-left text-caption text-t-tertiary font-medium py-2 px-3">Started</th>
                                        <th className="text-left text-caption text-t-tertiary font-medium py-2 px-3">Duration</th>
                                        <th className="text-left text-caption text-t-tertiary font-medium py-2 px-3">Status</th>
                                        <th className="text-left text-caption text-t-tertiary font-medium py-2 px-3">Outcome</th>
                                        <th className="text-right text-caption text-t-tertiary font-medium py-2 px-5 max-lg:px-3">Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {sessions.map((s) => {
                                        const id = sessionId(s);
                                        const { bg, text } = statusVariant(s.status);
                                        return (
                                            <tr
                                                key={id}
                                                className="border-b border-s-subtle last:border-0 hover:bg-b-surface1 dark:hover:bg-shade-04/30 transition-colors cursor-pointer"
                                                onClick={() => openTranscript(s)}
                                            >
                                                <td className="py-3.5 px-5 max-lg:px-3">
                                                    <div className="flex items-center gap-2.5">
                                                        <span className="grid place-items-center size-8 shrink-0 rounded-full bg-primary-01/12">
                                                            <Icon name="profile" className="size-4 fill-primary-01" />
                                                        </span>
                                                        <div>
                                                            <div className="font-medium text-t-primary td-num">{phoneOf(s)}</div>
                                                            {s.channel && s.channel !== "phone" && (
                                                                <div className="text-caption text-t-tertiary capitalize">{s.channel}</div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="py-3.5 px-3 text-t-secondary td-num whitespace-nowrap">
                                                    <span title={fmt(s.started_at)}>
                                                        {fmtRelative(s.started_at)}
                                                    </span>
                                                </td>
                                                <td className="py-3.5 px-3 text-t-secondary td-num">
                                                    {fmtDuration(s.started_at, s.ended_at)}
                                                </td>
                                                <td className="py-3.5 px-3">
                                                    <span className={`inline-flex items-center px-2 h-5 rounded-full text-caption font-medium capitalize ${bg} ${text}`}>
                                                        {s.status || "—"}
                                                    </span>
                                                </td>
                                                <td className="py-3.5 px-3 text-t-secondary capitalize">
                                                    {s.outcome || "—"}
                                                </td>
                                                <td className="py-3.5 px-5 max-lg:px-3 text-right">
                                                    <button
                                                        type="button"
                                                        className="inline-flex items-center gap-1.5 text-caption text-primary-01 hover:text-primary-01/80 transition-colors"
                                                        onClick={(e) => { e.stopPropagation(); openTranscript(s); }}
                                                    >
                                                        <Icon name="chat-think" className="size-3.5 fill-primary-01" />
                                                        View transcript
                                                    </button>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </Card>

            {/* Call transcript slide-over */}
            <TranscriptModal
                open={!!selectedSession}
                onClose={closeTranscript}
                session={selectedSession}
                loading={transcriptLoading}
                transcript={transcript}
            />
        </Layout>
    );
}

// ── Transcript slide-over ─────────────────────────────────────────────────────
// AI agent turns LEFT (neutral), customer turns RIGHT (primary tint).

function TranscriptModal({
    open,
    onClose,
    session,
    loading,
    transcript,
}: {
    open: boolean;
    onClose: () => void;
    session: AimSession | null;
    loading: boolean;
    transcript: CallTranscript | null;
}) {
    const turns = transcript?.turns ?? [];
    const phone = sessionCaller(session ?? {});
    const startedAt = session?.started_at ?? "";

    return (
        <Modal open={open} onClose={onClose} isSlidePanel>
            <div className="flex flex-col h-svh">
                {/* header */}
                <div className="shrink-0 px-6 pt-6 pb-4 border-b border-s-subtle max-md:px-4">
                    <div className="flex items-center gap-2.5">
                        <span className="grid place-items-center size-9 shrink-0 rounded-full bg-primary-01/12">
                            <Icon name="chat-think" className="size-4.5 fill-primary-01" />
                        </span>
                        <div className="min-w-0">
                            <div className="text-sub-title-1 text-t-primary truncate">
                                Inbound call transcript
                            </div>
                            <div className="flex items-center gap-2 text-caption text-t-tertiary">
                                {phone && phone !== "—" && (
                                    <span className="td-num">{phone}</span>
                                )}
                                {startedAt && (
                                    <span className="td-num" title={fmt(startedAt)}>
                                        {phone && phone !== "—" ? "· " : ""}
                                        {fmtRelative(startedAt)}
                                    </span>
                                )}
                            </div>
                        </div>
                    </div>
                </div>

                {/* chat body */}
                <div className="grow overflow-y-auto px-5 py-5 scrollbar-none max-md:px-4">
                    {loading ? (
                        <div className="grid place-items-center h-full">
                            <Spinner className="!size-10" />
                        </div>
                    ) : turns.length === 0 ? (
                        <div className="grid place-items-center h-full text-center px-4">
                            <div>
                                <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1 dark:bg-shade-04/60">
                                    <Icon name="chat" className="fill-t-tertiary" />
                                </span>
                                <div className="text-body-1-str font-semibold text-t-primary mb-1">
                                    No transcript for this call
                                </div>
                                <div className="max-w-xs mx-auto text-body-2 text-t-secondary">
                                    This call has no saved turns yet. Transcripts appear once a call is
                                    answered and conversation turns are captured.
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {turns.map((turn) => (
                                <ChatBubble key={turn.seq} turn={turn} />
                            ))}
                        </div>
                    )}
                </div>

                {/* footer legend */}
                {!loading && turns.length > 0 && (
                    <div className="shrink-0 flex items-center justify-center gap-5 px-6 py-3 border-t border-s-subtle text-caption text-t-tertiary max-md:px-4">
                        <span className="inline-flex items-center gap-1.5">
                            <span className="size-2.5 rounded-full bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04/80" />
                            AI agent
                        </span>
                        <span className="inline-flex items-center gap-1.5">
                            <span className="size-2.5 rounded-full bg-primary-01" />
                            Customer
                        </span>
                    </div>
                )}
            </div>
        </Modal>
    );
}

function ChatBubble({ turn }: { turn: TranscriptTurn }) {
    const isCustomer = turn.role === "customer";
    return (
        <div className={`flex ${isCustomer ? "justify-end" : "justify-start"}`}>
            <div className="max-w-[82%]">
                <div className={`mb-1 px-1 text-caption text-t-tertiary ${isCustomer ? "text-right" : ""}`}>
                    {isCustomer ? "Customer" : "AI agent"}
                </div>
                <div
                    className={`px-3.5 py-2.5 text-body-2 text-t-primary whitespace-pre-wrap break-words ${
                        isCustomer
                            ? "bg-primary-01/12 rounded-3xl rounded-br-lg"
                            : "bg-b-surface2 ring-1 ring-s-subtle ring-inset rounded-3xl rounded-bl-lg dark:bg-shade-04/60"
                    }`}
                >
                    {turn.text}
                </div>
                {turn.ts && (
                    <div className={`mt-0.5 px-1 text-caption text-t-tertiary td-num ${isCustomer ? "text-right" : ""}`}>
                        {fmtRelative(turn.ts)}
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Empty / dormant state ─────────────────────────────────────────────────────

function EmptyState({ icon, title, sub }: { icon: string; title: string; sub: string }) {
    return (
        <div className="py-16 text-center max-md:py-10">
            <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1 dark:bg-shade-04/60">
                <Icon name={icon} className="fill-t-tertiary" />
            </span>
            <div className="text-h6 mb-1 text-t-primary">{title}</div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">{sub}</div>
        </div>
    );
}
