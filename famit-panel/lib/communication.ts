"use client";

// ============================================================================
// lib/communication.ts — typed client for the omnichannel COMMUNICATION surface
// (communication/COMMUNICATION-MASTER-PLAN.md §7). Telegram is the first live
// channel (Email/SMS land in W3/W5 — their cards render a calm "coming soon").
//
// The LIVE backend mounts the comm router under `/comm` (caller.py W1-P2). The
// panel proxies caller.py at `/api`, so every call here is `/api/comm/*`. Auth is
// the same `X-Auth` header the rest of the panel uses.
//
// DORMANT-SAFE (the law): when `COMM_ENABLED` is OFF for the box (or the tenant is
// not entitled), every route 404s. Every READ here returns a calm empty shape on a
// non-2xx (never throws for a list/status read) so the page renders a coming-soon
// card, never an error wall. MUTATIONS surface a typed CommError so a form can show
// a precise message.
//
// SECURITY: the bot token is NEVER returned by any read — only a getMe identity
// check (`Test`) proves it works. The webhook secret_token is derived server-side
// (never client-supplied). Deep-links are signed single-use server-side (S5).
// ============================================================================

import { useCallback, useEffect, useRef, useState } from "react";

// ---- transport (mirrors lib/integrations.ts) -------------------------------
const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("famit_token");
}

function authHeaders(extra?: Record<string, string>): HeadersInit {
    const token = getToken();
    return {
        ...(token ? { "X-Auth": token } : {}),
        ...(extra || {}),
    };
}

export class CommError extends Error {
    status: number;
    code: string;
    constructor(message: string, status: number, code = "") {
        super(message);
        this.name = "CommError";
        this.status = status;
        this.code = code;
    }
}

// A read that degrades to a fallback on ANY non-2xx (dormant-safe). The boolean
// `disabled` flag tells the page the surface is off (404) vs. a transient error.
async function readJson<T>(path: string, fallback: T): Promise<{ data: T; disabled: boolean }> {
    try {
        const res = await fetch(`${BASE}${path}`, { headers: authHeaders(), cache: "no-store" });
        if (res.status === 404) return { data: fallback, disabled: true };
        if (!res.ok) return { data: fallback, disabled: false };
        return { data: (await res.json()) as T, disabled: false };
    } catch {
        return { data: fallback, disabled: false };
    }
}

// A mutation that throws a typed CommError on a non-2xx so the form can render the
// precise reason. A 404 here means COMM_ENABLED is off — surfaced as `dormant`.
async function writeJson<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    let json: Record<string, unknown> = {};
    try {
        json = (await res.json()) as Record<string, unknown>;
    } catch {
        /* empty body */
    }
    if (!res.ok) {
        const raw = String(json.error || json.reason || json.error_code || "");
        throw new CommError(humanizeError(raw, res.status), res.status, raw || (res.status === 404 ? "dormant" : ""));
    }
    return json as T;
}

export function humanizeError(raw: string, status: number): string {
    if (raw === "phone required") return "Enter the contact's phone number first.";
    if (raw === "to_ref required") return "Enter where to send (a Telegram chat id).";
    if (raw === "no_channel_or_token" || raw === "not_configured")
        return "No bot token is connected yet — paste your BotFather token above.";
    if (raw === "no_founder_chat_id")
        return "Tap Start on your bot once, then press “Find my chat”.";
    if (raw === "timeout") return "Telegram didn't respond in time. Try again.";
    if (raw === "channel_not_enabled") return "This channel isn't switched on for your workspace.";
    if (status === 404) return "Communication isn't enabled for your workspace yet.";
    if (status === 403) return "You don't have permission for that.";
    if (status === 402) return "This feature is locked on your plan.";
    return raw || "Something went wrong. Please try again.";
}

// ---- types (match comm/endpoints.py responses) -----------------------------
export type ChannelKind = "telegram" | "email" | "sms" | "whatsapp";

export type CommChannel = {
    channel: ChannelKind;
    enabled: boolean;
    configured: boolean;
    founder_alert?: boolean;
    followup?: boolean;
};

export type ChannelsResult = {
    channels: CommChannel[];
    flags: Record<string, unknown>;
    disabled: boolean;
};

export type TestResult = { ok: boolean; username: string };
export type ChatIdResult = { chat_id: string; found: boolean };
export type WebhookResult = { ok: boolean; provider_def_id?: string; error?: string };
export type DeeplinkResult = { payload: string; link: string; ok: boolean };

export type SendResult = {
    ok: boolean;
    status: string;
    channel: string;
    external_id?: string;
    error_code?: string;
    cost_minor?: number;
};

export type SessionTurn = {
    role: "user" | "assistant" | "customer" | "ai" | string;
    text: string;
    at?: string | null;
};

export type CommSession = {
    id: string;
    channel: string;
    external_chat_id?: string;
    status?: string;
    contact_name?: string | null;
    contact_phone?: string | null;
    last_message_at?: string | null;
    call_summary?: string | null;
    next_action?: string | null;
    outcome?: string | null;
    interest?: number | null;
    turns?: SessionTurn[];
    turn_count?: number;
    [key: string]: unknown;
};

export type SendBody = {
    to_ref: string;
    text?: string;
    kind?: string;
    purpose?: string;
    media?: { url: string; kind?: string; caption?: string }[];
    buttons?: { text: string; url: string }[];
    session_id?: string;
};

// ============================================================================
// READS (dormant-safe)
// ============================================================================
export async function getChannels(): Promise<ChannelsResult> {
    const { data, disabled } = await readJson<{ channels: CommChannel[]; flags: Record<string, unknown> }>(
        "/comm/channels",
        { channels: [], flags: {} },
    );
    return { channels: data.channels || [], flags: data.flags || {}, disabled };
}

export async function getSessions(opts?: {
    channel?: string;
    status?: string;
    limit?: number;
    offset?: number;
}): Promise<{ sessions: CommSession[]; total: number; disabled: boolean }> {
    const qs = new URLSearchParams();
    if (opts?.channel) qs.set("channel", opts.channel);
    if (opts?.status) qs.set("status", opts.status);
    qs.set("limit", String(opts?.limit ?? 50));
    qs.set("offset", String(opts?.offset ?? 0));
    const { data, disabled } = await readJson<{ sessions: CommSession[]; total: number }>(
        `/comm/sessions?${qs.toString()}`,
        { sessions: [], total: 0 },
    );
    return { sessions: data.sessions || [], total: data.total || 0, disabled };
}

export async function getSession(id: string): Promise<{ session: CommSession | null; disabled: boolean }> {
    const { data, disabled } = await readJson<{ session: CommSession }>(
        `/comm/sessions/${encodeURIComponent(id)}`,
        { session: null as unknown as CommSession },
    );
    return { session: data.session || null, disabled };
}

// ============================================================================
// MUTATIONS (typed errors)
// ============================================================================
export function testTelegram(): Promise<TestResult> {
    return writeJson<TestResult>("/comm/channels/telegram/test");
}

export function deriveChatId(force = false): Promise<ChatIdResult> {
    return writeJson<ChatIdResult>("/comm/channels/telegram/derive-chat-id", { force });
}

export function setWebhook(webhook_url: string): Promise<WebhookResult> {
    return writeJson<WebhookResult>("/comm/channels/telegram/set-webhook", { webhook_url });
}

export function mintDeeplink(phone: string, bot_username = ""): Promise<DeeplinkResult> {
    return writeJson<DeeplinkResult>("/comm/channels/telegram/deeplink", { phone, bot_username });
}

export function sendMessage(body: SendBody): Promise<SendResult> {
    return writeJson<SendResult>("/comm/send", body);
}

// ============================================================================
// HOOKS
// ============================================================================
export function useChannels() {
    const [channels, setChannels] = useState<CommChannel[]>([]);
    const [flags, setFlags] = useState<Record<string, unknown>>({});
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);

    const reload = useCallback(async () => {
        const res = await getChannels();
        setChannels(res.channels);
        setFlags(res.flags);
        setDormant(res.disabled);
        setLoading(false);
    }, []);

    useEffect(() => {
        let alive = true;
        (async () => {
            const res = await getChannels();
            if (!alive) return;
            setChannels(res.channels);
            setFlags(res.flags);
            setDormant(res.disabled);
            setLoading(false);
        })();
        return () => {
            alive = false;
        };
    }, []);

    return { channels, flags, loading, dormant, reload };
}

export function useSessions(opts?: { channel?: string; pollMs?: number }) {
    const channel = opts?.channel || "";
    const pollMs = opts?.pollMs ?? 0;
    const [sessions, setSessions] = useState<CommSession[]>([]);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const timer = useRef<ReturnType<typeof setInterval> | null>(null);

    const load = useCallback(async () => {
        const res = await getSessions({ channel });
        setSessions(res.sessions);
        setDormant(res.disabled);
        setLoading(false);
    }, [channel]);

    useEffect(() => {
        let alive = true;
        const poll = async () => {
            const res = await getSessions({ channel });
            if (!alive) return;
            setSessions(res.sessions);
            setDormant(res.disabled);
            setLoading(false);
        };
        poll();
        if (pollMs > 0) timer.current = setInterval(poll, pollMs);
        return () => {
            alive = false;
            if (timer.current) clearInterval(timer.current);
        };
    }, [channel, pollMs]);

    return { sessions, loading, dormant, reload: load };
}

// ---- display dictionaries (single source of truth) -------------------------
export const CHANNEL_LABEL: Record<ChannelKind, string> = {
    telegram: "Telegram",
    email: "Email",
    sms: "SMS",
    whatsapp: "WhatsApp",
};

// Glyph ground-truth honored (only icons that exist in the kit). Telegram=send,
// Email=envelope, SMS=chat, WhatsApp=chat-think.
export const CHANNEL_ICON: Record<ChannelKind, string> = {
    telegram: "send",
    email: "envelope",
    sms: "chat",
    whatsapp: "chat-think",
};

// Wave a channel ships in (drives the "coming soon" copy on not-yet-live cards).
export const CHANNEL_WAVE: Record<ChannelKind, string> = {
    telegram: "live",
    email: "Coming soon",
    sms: "Coming soon",
    whatsapp: "live",
};

export function fmtRelative(iso?: string | null): string {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        const diff = Date.now() - d.getTime();
        const m = Math.floor(diff / 60000);
        if (m < 1) return "just now";
        if (m < 60) return `${m}m ago`;
        const h = Math.floor(m / 60);
        if (h < 24) return `${h}h ago`;
        const days = Math.floor(h / 24);
        if (days < 7) return `${days}d ago`;
        return d.toLocaleDateString();
    } catch {
        return "—";
    }
}
