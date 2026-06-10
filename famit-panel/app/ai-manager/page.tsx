"use client";

// AI Manager — the voice-first (and chat) COMMAND CENTER.
//
// A registered phone number speaks a natural command; the platform verifies WHO
// is calling -> loads business context -> checks permission -> demands a fresh
// scoped PIN/OTP for risky actions -> delegates to the AI workforce -> executes
// -> reads the result back. This page is the DASHBOARD surface for that engine:
// register/govern the numbers that may command, watch the dormancy/config of the
// voice front, and review past voice sessions (PIN-masked).
//
// The backend router is DEFINED-NOT-MOUNTED today, so the graceful "not
// configured / coming soon" path is the PRIMARY state — every read degrades to a
// premium dormant view rather than an error wall. Built entirely on the in-app
// "Signal" component language (Layout/PageHeader/Card/KpiCard/Badge/Tabs/Icon/
// Button) + the verified globals.css utilities. Edits only this route's files.

import { useCallback, useEffect, useState } from "react";
import Layout from "@/components/Layout";
import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Button from "@/components/Button";
import { useMe, canWrite, isAdmin } from "@/lib/auth";
import {
    getAimStatus,
    getAimNumbers,
    getAimSessions,
    registerAimNumber,
    verifyAimNumber,
    revokeAimNumber,
    KNOWN_GRANTS,
    AIM_ROLES,
    AIM_VERIFY_MODES,
    type AimStatus,
    type AimNumber,
    type AimSession,
    type AimRole,
    type AimVerifyMode,
    type ReadResult,
} from "./_lib";

/* ----------------------------------------------------------------- helpers */

type Toast = { msg: string; type: "success" | "error" };
type TabKey = "command" | "numbers" | "sessions";

function fmt(d?: string): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

function prettyProvider(p?: string): string {
    if (!p || p === "none") return "Not set";
    return p.charAt(0).toUpperCase() + p.slice(1);
}

function durationOf(a?: string, b?: string): string {
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

// A small status chip used across the page for config rows.
function ConfigPill({
    on,
    onLabel,
    offLabel,
    tone = "info",
}: {
    on: boolean;
    onLabel: string;
    offLabel: string;
    tone?: BadgeVariant;
}) {
    return on ? (
        <Badge variant={tone} dot>
            {onLabel}
        </Badge>
    ) : (
        <Badge variant="neutral">{offLabel}</Badge>
    );
}

function numberStatusVariant(s: string): BadgeVariant {
    if (s === "active") return "success";
    if (s === "locked") return "warning";
    if (s === "revoked") return "danger";
    return "neutral";
}

function riskVariant(r?: string): BadgeVariant {
    const x = (r || "").toLowerCase();
    if (x === "money" || x === "destructive") return "danger";
    if (x === "bulk") return "warning";
    if (x === "safe") return "success";
    return "neutral";
}

/* ------------------------------------------------------------ empty / dormant */

// The premium "coming soon / not configured" panel — the PRIMARY state until the
// backend router is mounted and creds land. Distinct, on-brand, never an error.
function DormantPanel({
    icon = "mobile",
    title,
    sub,
    children,
}: {
    icon?: string;
    title: string;
    sub: string;
    children?: React.ReactNode;
}) {
    return (
        <div className="state-block">
            <span className="state-glyph">
                <Icon name={icon} className="fill-inherit" />
            </span>
            <div className="state-title">{title}</div>
            <div className="state-sub max-w-md mx-auto">{sub}</div>
            {children}
        </div>
    );
}

/* ============================================================== the page */

export default function AiManagerPage() {
    const { me } = useMe();
    const writable = canWrite(me);
    const admin = isAdmin(me);

    const [tab, setTab] = useState<TabKey>("command");
    const [toast, setToast] = useState<Toast | null>(null);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4200);
    };

    // ---- status ----
    const [status, setStatus] = useState<ReadResult<AimStatus> | null>(null);
    const [statusLoading, setStatusLoading] = useState(true);

    const loadStatus = useCallback(() => {
        setStatusLoading(true);
        getAimStatus()
            .then(setStatus)
            .finally(() => setStatusLoading(false));
    }, []);

    // ---- numbers ----
    const [numbers, setNumbers] = useState<ReadResult<{ numbers: AimNumber[] }> | null>(null);
    const [numbersLoading, setNumbersLoading] = useState(true);

    const loadNumbers = useCallback(() => {
        setNumbersLoading(true);
        getAimNumbers()
            .then(setNumbers)
            .finally(() => setNumbersLoading(false));
    }, []);

    // ---- sessions ----
    const [sessions, setSessions] = useState<ReadResult<{ sessions: AimSession[] }> | null>(null);
    const [sessionsLoading, setSessionsLoading] = useState(true);

    const loadSessions = useCallback(() => {
        setSessionsLoading(true);
        getAimSessions()
            .then(setSessions)
            .finally(() => setSessionsLoading(false));
    }, []);

    useEffect(() => {
        loadStatus();
        loadNumbers();
        loadSessions();
    }, [loadStatus, loadNumbers, loadSessions]);

    const st = status?.kind === "ok" ? status.data : null;
    const numberRows = numbers?.kind === "ok" ? numbers.data.numbers : [];
    const sessionRows = sessions?.kind === "ok" ? sessions.data.sessions : [];

    // Whether the whole module reads as dormant (router not mounted / not deployed).
    const moduleDormant =
        status?.kind === "dormant" && numbers?.kind === "dormant";

    const activeNumbers = numberRows.filter((n) => n.status === "active" && n.verified).length;
    const pendingNumbers = numberRows.filter((n) => !n.verified).length;

    const TABS: { key: TabKey; label: string; icon: string }[] = [
        { key: "command", label: "Command Center", icon: "dashboard" },
        { key: "numbers", label: "Registered Numbers", icon: "mobile" },
        { key: "sessions", label: "Voice Sessions", icon: "chat" },
    ];

    return (
        <Layout title="AI Manager">
            <PageHeader
                eyebrow="Voice Command Center"
                title="AI Manager"
                subtitle="Run your business by voice. Call a number, speak a command, and the AI Manager verifies you, checks permissions, demands a PIN for anything risky, then executes across campaigns, leads, calls, WhatsApp and ads — and reads the result back."
                actions={
                    <button
                        onClick={() => {
                            loadStatus();
                            loadNumbers();
                            loadSessions();
                        }}
                        className="inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50"
                        disabled={statusLoading || numbersLoading || sessionsLoading}
                    >
                        <Icon
                            name="clock"
                            className={`size-4 fill-current ${
                                statusLoading || numbersLoading || sessionsLoading ? "animate-spin" : ""
                            }`}
                        />
                        Refresh
                    </button>
                }
            />

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

            {/* Tab strip — pill rail matching the billing area's premium tabs */}
            <div className="flex items-center gap-1 mb-5 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle w-fit max-w-full overflow-x-auto scrollbar-none">
                {TABS.map((t) => {
                    const active = tab === t.key;
                    return (
                        <button
                            key={t.key}
                            onClick={() => setTab(t.key)}
                            className={`shrink-0 inline-flex items-center gap-2 h-9 px-3.5 rounded-full text-button transition-colors ${
                                active
                                    ? "bg-b-surface1 text-t-primary shadow-widget dark:bg-shade-04"
                                    : "text-t-secondary hover:text-t-primary"
                            }`}
                        >
                            <Icon
                                name={t.icon}
                                className={`size-4 ${active ? "fill-t-primary" : "fill-t-secondary"}`}
                            />
                            {t.label}
                            {t.key === "numbers" && pendingNumbers > 0 && (
                                <span className="pill pill-warning !px-1.5 !py-0 text-caption">
                                    {pendingNumbers}
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>

            {tab === "command" && (
                <CommandCenter
                    status={status}
                    st={st}
                    loading={statusLoading}
                    activeNumbers={activeNumbers}
                    pendingNumbers={pendingNumbers}
                    totalNumbers={numberRows.length}
                    sessionCount={sessionRows.length}
                    moduleDormant={moduleDormant}
                />
            )}

            {tab === "numbers" && (
                <NumbersTab
                    result={numbers}
                    rows={numberRows}
                    loading={numbersLoading}
                    writable={writable}
                    admin={admin}
                    onChanged={loadNumbers}
                    toast={showToast}
                />
            )}

            {tab === "sessions" && (
                <SessionsTab result={sessions} rows={sessionRows} loading={sessionsLoading} />
            )}
        </Layout>
    );
}

/* ===================================================== TAB 1 — Command Center */

function CommandCenter({
    status,
    st,
    loading,
    activeNumbers,
    pendingNumbers,
    totalNumbers,
    sessionCount,
    moduleDormant,
}: {
    status: ReadResult<AimStatus> | null;
    st: AimStatus | null;
    loading: boolean;
    activeNumbers: number;
    pendingNumbers: number;
    totalNumbers: number;
    sessionCount: number;
    moduleDormant: boolean;
}) {
    const sipOn = st?.sip === "configured";
    const llmOn = !!st && st.llm_provider !== "none" && !!st.llm_provider;
    const otpOn = !!st && st.otp_provider !== "none" && !!st.otp_provider;
    const enabled = !!st?.enabled;

    // The voice front-door is "live" only when the feature is enabled AND SIP is
    // provisioned. Everything short of that is an honest "coming soon".
    const voiceLive = enabled && sipOn;

    return (
        <div className="space-y-3">
            {/* Hero KPI strip — real config signals only */}
            <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <HeroStat
                    label="Voice Front-Door"
                    glyph="mobile"
                    glyphClass="fill-primary-01"
                    accent="var(--primary-01)"
                    loading={loading && !st}
                    value={voiceLive ? "Live" : "Coming soon"}
                    foot={
                        voiceLive
                            ? `Agent "${st?.agent_name || "manager"}" on inbound SIP`
                            : "Awaiting telephony provisioning"
                    }
                />
                <HeroStat
                    label="Registered Numbers"
                    glyph="check-circle"
                    glyphClass="fill-primary-02"
                    accent="var(--primary-02)"
                    delay={60}
                    loading={loading && !status}
                    value={String(activeNumbers)}
                    foot={
                        pendingNumbers > 0
                            ? `${pendingNumbers} awaiting verification`
                            : totalNumbers === 0
                            ? "None registered yet"
                            : "All verified"
                    }
                />
                <HeroStat
                    label="Risk Gate"
                    glyph="lock"
                    glyphClass="fill-primary-04"
                    accent="var(--primary-04)"
                    delay={120}
                    loading={loading && !st}
                    value="PIN + Step-up"
                    foot={
                        st
                            ? `${st.max_pin_attempts} attempts · ${Math.round((st.lock_ttl_s || 0) / 60)}m lockout`
                            : "Fresh PIN per risky action"
                    }
                />
                <HeroStat
                    label="Voice Sessions"
                    glyph="chat"
                    glyphClass="fill-primary-05"
                    accent="var(--primary-05)"
                    delay={180}
                    loading={loading && !status}
                    value={String(sessionCount)}
                    foot={sessionCount === 0 ? "No calls recorded yet" : "PIN-masked transcripts"}
                />
            </div>

            {/* The honest "what this is / coming soon" explainer */}
            {(moduleDormant || !voiceLive) && (
                <div className="card overflow-hidden">
                    <div className="relative p-6 max-lg:p-4">
                        <span
                            aria-hidden
                            className="pointer-events-none absolute -top-20 -right-16 size-56 rounded-full opacity-[0.10] blur-3xl"
                            style={{ background: "var(--primary-01)" }}
                        />
                        <div className="relative flex items-start gap-4 max-sm:flex-col">
                            <span className="grid place-items-center size-12 shrink-0 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                                <Icon name="mobile" className="size-6 fill-inherit" />
                            </span>
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h3 className="text-h6 text-t-primary">The voice command center is coming soon</h3>
                                    <Badge variant="info" dot>
                                        In setup
                                    </Badge>
                                </div>
                                <p className="text-body-2 text-t-secondary mt-2 max-w-2xl">
                                    The safety engine is built and offline-verified — identity, permission,
                                    PIN/OTP step-up, deterministic risk classification and an immutable audit
                                    trail. The inbound phone line lights up once telephony, the intent model and
                                    the dashboard service token are provisioned on the server. Until then you can
                                    pre-register the numbers that will be allowed to command.
                                </p>
                                <div className="mt-4 grid grid-cols-3 gap-3 max-md:grid-cols-1">
                                    <FlowStep n={1} icon="check-circle" title="Verify" text="Caller-ID is a hint — a fresh PIN proves the human before any data is spoken." />
                                    <FlowStep n={2} icon="lock" title="Authorize" text="Every risky action demands its own scoped step-up PIN, then a spoken confirm." />
                                    <FlowStep n={3} icon="send" title="Delegate" text="Hands the verified intent to the AI workforce, which re-checks caps and executes." />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Configuration board — every dormant dependency, surfaced honestly */}
            <Card
                title="Configuration"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                        Server-side · dormant until creds
                    </span>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {loading && !st ? (
                        <div className="space-y-3">
                            {[...Array(5)].map((_, i) => (
                                <div key={i} className="flex items-center justify-between">
                                    <div className="skeleton h-4 w-40" />
                                    <div className="skeleton h-5 w-24" />
                                </div>
                            ))}
                        </div>
                    ) : status?.kind === "error" ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="info" className="fill-inherit" />
                            </span>
                            <div className="state-title">Couldn&apos;t load configuration</div>
                            <div className="state-sub">{status.message}</div>
                        </div>
                    ) : (
                        <div className="divide-y divide-s-subtle">
                            <ConfigRow
                                icon="dashboard"
                                label="Command center"
                                hint="Master feature flag (AIM_ENABLED)"
                            >
                                <ConfigPill on={enabled} onLabel="Enabled" offLabel="Disabled" tone="success" />
                            </ConfigRow>
                            <ConfigRow
                                icon="mobile"
                                label="Inbound telephony (SIP)"
                                hint="The phone number managers call"
                            >
                                <ConfigPill on={sipOn} onLabel="Configured" offLabel="Not configured" />
                            </ConfigRow>
                            <ConfigRow
                                icon="chat"
                                label="Intent model"
                                hint="Parses speech into a closed-enum command"
                            >
                                {llmOn ? (
                                    <Badge variant="info" dot>
                                        {prettyProvider(st?.llm_provider)}
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Keyword matcher (offline)</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow
                                icon="send"
                                label="OTP delivery"
                                hint="SMS / WhatsApp one-time codes"
                            >
                                {otpOn ? (
                                    <Badge variant="info" dot>
                                        {prettyProvider(st?.otp_provider)}
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Spoken PIN fallback</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow
                                icon="lock"
                                label="Control-plane link"
                                hint="How the voice box reaches the firewall + engine"
                            >
                                <Badge variant="neutral">
                                    {st?.cross_plane === "configured" ? "Cross-plane" : "In-process"}
                                </Badge>
                            </ConfigRow>
                        </div>
                    )}
                </div>
            </Card>

            {/* What you can command, once live — the closed command vocabulary */}
            <Card title="Commands the AI Manager understands">
                <div className="px-5 pb-5 max-lg:px-3 grid grid-cols-2 gap-3 max-md:grid-cols-1">
                    <CommandExample
                        icon="send"
                        risk="bulk"
                        utterance="Call all my hot leads"
                        maps="leads.enqueue_calls"
                    />
                    <CommandExample
                        icon="wallet"
                        risk="money"
                        utterance="Bump the budget on my best ad to ₹1,500 a day"
                        maps="ads.set_budget"
                    />
                    <CommandExample
                        icon="chat"
                        risk="bulk"
                        utterance="Send the festive offer on WhatsApp to my Gurgaon segment"
                        maps="whatsapp.send"
                    />
                    <CommandExample
                        icon="chart"
                        risk="safe"
                        utterance="What's today's revenue and how many calls connected?"
                        maps="analytics.read"
                    />
                </div>
            </Card>
        </div>
    );
}

function HeroStat({
    label,
    glyph,
    glyphClass,
    value,
    foot,
    accent,
    delay = 0,
    loading,
}: {
    label: string;
    glyph: string;
    glyphClass?: string;
    value: React.ReactNode;
    foot?: React.ReactNode;
    accent?: string;
    delay?: number;
    loading?: boolean;
}) {
    return (
        <div className="kpi rise-in group" style={delay ? { animationDelay: `${delay}ms` } : undefined}>
            {accent && (
                <span
                    aria-hidden
                    className="pointer-events-none absolute -top-16 -right-16 size-40 rounded-full opacity-[0.13] blur-2xl transition-opacity duration-500 group-hover:opacity-20"
                    style={{ background: accent }}
                />
            )}
            <div className="flex items-start justify-between gap-3">
                <div className="kpi-label">
                    <span className={`kpi-glyph ${glyphClass || ""}`}>
                        <Icon name={glyph} className="fill-inherit" />
                    </span>
                    {label}
                </div>
            </div>
            {loading ? (
                <div className="skeleton h-9 w-28 mt-1" />
            ) : (
                <div className="kpi-value relative z-1 !text-h4">{value}</div>
            )}
            {foot && <div className="kpi-foot relative z-1">{foot}</div>}
        </div>
    );
}

function FlowStep({ n, icon, title, text }: { n: number; icon: string; title: string; text: string }) {
    return (
        <div className="relative p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
            <div className="flex items-center gap-2 mb-1.5">
                <span className="grid place-items-center size-7 rounded-full bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                    <Icon name={icon} className="size-4 fill-inherit" />
                </span>
                <span className="text-caption text-t-tertiary tabular-nums">Step {n}</span>
            </div>
            <div className="text-sub-title-2 text-t-primary">{title}</div>
            <div className="text-caption text-t-secondary mt-1">{text}</div>
        </div>
    );
}

function ConfigRow({
    icon,
    label,
    hint,
    children,
}: {
    icon: string;
    label: string;
    hint: string;
    children: React.ReactNode;
}) {
    return (
        <div className="flex items-center justify-between gap-4 py-3.5">
            <div className="flex items-center gap-3 min-w-0">
                <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                    <Icon name={icon} className="size-4.5 fill-inherit" />
                </span>
                <div className="min-w-0">
                    <div className="text-body-2 text-t-primary truncate">{label}</div>
                    <div className="text-caption text-t-tertiary truncate">{hint}</div>
                </div>
            </div>
            <div className="shrink-0">{children}</div>
        </div>
    );
}

function CommandExample({
    icon,
    risk,
    utterance,
    maps,
}: {
    icon: string;
    risk: string;
    utterance: string;
    maps: string;
}) {
    return (
        <div className="lift group flex items-start gap-3 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30">
            <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                <Icon name={icon} className="size-4.5 fill-inherit" />
            </span>
            <div className="min-w-0 flex-1">
                <div className="text-body-2 text-t-primary">&ldquo;{utterance}&rdquo;</div>
                <div className="flex items-center gap-2 mt-2">
                    <span className="font-mono text-caption text-t-tertiary truncate">{maps}</span>
                    <Badge variant={riskVariant(risk)}>{risk}</Badge>
                </div>
            </div>
        </div>
    );
}

/* ===================================================== TAB 2 — Numbers */

function NumbersTab({
    result,
    rows,
    loading,
    writable,
    admin,
    onChanged,
    toast,
}: {
    result: ReadResult<{ numbers: AimNumber[] }> | null;
    rows: AimNumber[];
    loading: boolean;
    writable: boolean;
    admin: boolean;
    onChanged: () => void;
    toast: (msg: string, type?: "success" | "error") => void;
}) {
    const dormant = result?.kind === "dormant";
    const error = result?.kind === "error" ? result.message : "";

    const [busyId, setBusyId] = useState<string>("");

    async function doVerify(n: AimNumber) {
        setBusyId(n.number_id);
        try {
            await verifyAimNumber(n.number_id);
            toast(`${n.phone} marked verified`);
            onChanged();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Verify failed", "error");
        } finally {
            setBusyId("");
        }
    }

    async function doRevoke(n: AimNumber) {
        setBusyId(n.number_id);
        try {
            await revokeAimNumber(n.number_id);
            toast(`${n.phone} revoked`);
            onChanged();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Revoke failed", "error");
        } finally {
            setBusyId("");
        }
    }

    return (
        <div className="flex gap-6 max-lg:flex-col">
            <div className="flex-1 min-w-0">
                <Card
                    title="Registered Numbers"
                    headContent={
                        <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                            Role + grant must both allow
                        </span>
                    }
                >
                    {error && (
                        <div className="mx-5 mb-3 toast toast-error">
                            <span className="flex items-center gap-2">
                                <span className="size-1.5 rounded-full bg-current" />
                                {error}
                            </span>
                        </div>
                    )}
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Number</th>
                                    <th>Role</th>
                                    <th>Verify</th>
                                    <th>Grants</th>
                                    <th>Status</th>
                                    {writable && <th className="text-right pr-5">Actions</th>}
                                </tr>
                            </thead>
                            <tbody>
                                {loading ? (
                                    [...Array(3)].map((_, i) => (
                                        <tr key={i}>
                                            {[...Array(writable ? 6 : 5)].map((__, j) => (
                                                <td key={j}>
                                                    <div className="skeleton h-4 w-20" />
                                                </td>
                                            ))}
                                        </tr>
                                    ))
                                ) : dormant ? (
                                    <tr>
                                        <td colSpan={writable ? 6 : 5}>
                                            <DormantPanel
                                                icon="mobile"
                                                title="Number registry coming soon"
                                                sub="Once the AI Manager backend is provisioned on the server, register the manager phone numbers allowed to command your business by voice here — each scoped by role and a per-number capability allow-list."
                                            />
                                        </td>
                                    </tr>
                                ) : rows.length === 0 ? (
                                    <tr>
                                        <td colSpan={writable ? 6 : 5}>
                                            <DormantPanel
                                                icon="plus"
                                                title="No numbers registered"
                                                sub="Add the first manager phone number on the right. It is ownership-verified by a one-time code before it can issue any command."
                                            />
                                        </td>
                                    </tr>
                                ) : (
                                    rows.map((n) => (
                                        <tr key={n.number_id}>
                                            <td>
                                                <div className="flex items-center gap-2">
                                                    <span className="font-mono text-body-2 text-t-primary td-num">
                                                        {n.phone}
                                                    </span>
                                                </div>
                                                {n.label && (
                                                    <div className="text-caption text-t-tertiary mt-0.5">
                                                        {n.label}
                                                    </div>
                                                )}
                                            </td>
                                            <td>
                                                <span className="pill pill-neutral capitalize">{n.role}</span>
                                            </td>
                                            <td className="text-t-secondary">
                                                {n.verify_mode === "otp" ? "OTP" : "Voice PIN"}
                                            </td>
                                            <td>
                                                <div className="flex flex-wrap gap-1 max-w-[16rem]">
                                                    {(n.grants || []).length === 0 ? (
                                                        <span className="text-caption text-t-tertiary">—</span>
                                                    ) : (
                                                        n.grants.slice(0, 4).map((g) => (
                                                            <span
                                                                key={g}
                                                                className="pill pill-neutral !px-2 text-caption"
                                                            >
                                                                {g}
                                                            </span>
                                                        ))
                                                    )}
                                                    {(n.grants || []).length > 4 && (
                                                        <span className="text-caption text-t-tertiary">
                                                            +{n.grants.length - 4}
                                                        </span>
                                                    )}
                                                </div>
                                            </td>
                                            <td>
                                                <div className="flex items-center gap-1.5">
                                                    <Badge variant={numberStatusVariant(n.status)} dot>
                                                        {n.status}
                                                    </Badge>
                                                    {!n.verified && (
                                                        <Badge variant="warning">unverified</Badge>
                                                    )}
                                                </div>
                                            </td>
                                            {writable && (
                                                <td className="text-right pr-5">
                                                    <div className="inline-flex items-center gap-2">
                                                        {!n.verified && (
                                                            <button
                                                                onClick={() => doVerify(n)}
                                                                disabled={busyId === n.number_id}
                                                                className="inline-flex items-center gap-1 h-8 px-3 rounded-full border border-s-subtle text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary disabled:opacity-50"
                                                            >
                                                                <Icon name="check" className="size-3.5 fill-current" />
                                                                Verify
                                                            </button>
                                                        )}
                                                        {admin && n.status !== "revoked" && (
                                                            <button
                                                                onClick={() => doRevoke(n)}
                                                                disabled={busyId === n.number_id}
                                                                className="inline-flex items-center gap-1 h-8 px-3 rounded-full border border-s-subtle text-button text-primary-03 fill-primary-03 transition-colors hover:bg-primary-03/8 disabled:opacity-50"
                                                                title="Revoking is firewall-gated and may require a step-up PIN"
                                                            >
                                                                <Icon name="block" className="size-3.5 fill-current" />
                                                                Revoke
                                                            </button>
                                                        )}
                                                    </div>
                                                </td>
                                            )}
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </Card>
            </div>

            {/* Register form — manager+ only, mirrors the whatsapp page's side panel */}
            {writable && (
                <div className="w-96 max-lg:w-full shrink-0">
                    <RegisterForm onRegistered={onChanged} toast={toast} disabled={dormant} />
                </div>
            )}
        </div>
    );
}

function RegisterForm({
    onRegistered,
    toast,
    disabled,
}: {
    onRegistered: () => void;
    toast: (msg: string, type?: "success" | "error") => void;
    disabled: boolean;
}) {
    const [phone, setPhone] = useState("");
    const [label, setLabel] = useState("");
    const [role, setRole] = useState<AimRole>("manager");
    const [verifyMode, setVerifyMode] = useState<AimVerifyMode>("voice_pin");
    const [grants, setGrants] = useState<string[]>(["analytics"]);
    const [saving, setSaving] = useState(false);

    const inputCls = "input-base w-full h-11 px-4 rounded-2xl text-body-2";
    const selectCls = `${inputCls} appearance-none`;

    function toggleGrant(g: string) {
        setGrants((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));
    }

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        if (!phone.trim()) return;
        setSaving(true);
        try {
            await registerAimNumber({
                phone: phone.trim(),
                label: label.trim() || undefined,
                role,
                verify_mode: verifyMode,
                grants,
            });
            toast(`${phone.trim()} registered — verify the one-time code to activate`);
            setPhone("");
            setLabel("");
            setGrants(["analytics"]);
            onRegistered();
        } catch (e2) {
            toast(e2 instanceof Error ? e2.message : "Registration failed", "error");
        } finally {
            setSaving(false);
        }
    }

    return (
        <Card title="Register a Number">
            <form onSubmit={submit} className="px-5 pb-5 space-y-4">
                {disabled && (
                    <div className="p-3 rounded-2xl border border-s-subtle bg-b-surface2 text-caption text-t-secondary">
                        The backend isn&apos;t live yet — registrations will be accepted once the AI Manager
                        service is provisioned on the server.
                    </div>
                )}
                <div>
                    <label className="block text-button mb-3 text-t-primary">Phone (caller-ID)</label>
                    <input
                        type="text"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="+919876543210"
                        className={inputCls}
                        required
                    />
                </div>
                <div>
                    <label className="block text-button mb-3 text-t-primary">Label</label>
                    <input
                        type="text"
                        value={label}
                        onChange={(e) => setLabel(e.target.value)}
                        placeholder="Owner mobile"
                        className={inputCls}
                    />
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="block text-button mb-3 text-t-primary">Role</label>
                        <select
                            value={role}
                            onChange={(e) => setRole(e.target.value as AimRole)}
                            className={selectCls}
                        >
                            {AIM_ROLES.map((r) => (
                                <option key={r} value={r}>
                                    {r}
                                </option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <label className="block text-button mb-3 text-t-primary">Verify by</label>
                        <select
                            value={verifyMode}
                            onChange={(e) => setVerifyMode(e.target.value as AimVerifyMode)}
                            className={selectCls}
                        >
                            {AIM_VERIFY_MODES.map((v) => (
                                <option key={v} value={v}>
                                    {v === "otp" ? "OTP" : "Voice PIN"}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>
                <div>
                    <label className="block text-button mb-3 text-t-primary">Capability grants</label>
                    <div className="flex flex-wrap gap-2">
                        {KNOWN_GRANTS.map((g) => {
                            const on = grants.includes(g);
                            return (
                                <button
                                    type="button"
                                    key={g}
                                    onClick={() => toggleGrant(g)}
                                    className={`inline-flex items-center gap-1 h-8 px-3 rounded-full border text-button transition-colors ${
                                        on
                                            ? "border-transparent bg-primary-01/12 text-primary-01 fill-primary-01"
                                            : "border-s-subtle text-t-secondary hover:border-s-highlight hover:text-t-primary"
                                    }`}
                                >
                                    {on && <Icon name="check" className="size-3 fill-current" />}
                                    {g}
                                </button>
                            );
                        })}
                    </div>
                    <p className="text-caption text-t-tertiary mt-2">
                        Effective permission = role allows AND grant allows. Default-deny.
                    </p>
                </div>
                <Button isBlack className="w-full justify-center" disabled={saving}>
                    {saving ? "Registering…" : "Register number"}
                </Button>
            </form>
        </Card>
    );
}

/* ===================================================== TAB 3 — Sessions */

function SessionsTab({
    result,
    rows,
    loading,
}: {
    result: ReadResult<{ sessions: AimSession[] }> | null;
    rows: AimSession[];
    loading: boolean;
}) {
    const dormant = result?.kind === "dormant";
    const error = result?.kind === "error" ? result.message : "";

    return (
        <Card
            title="Voice Sessions"
            headContent={
                <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                    <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                    PIN-masked · immutable
                </span>
            }
        >
            {error && (
                <div className="mx-5 mb-3 toast toast-error">
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {error}
                    </span>
                </div>
            )}
            <div className="overflow-x-auto">
                <table className="data-table">
                    <thead>
                        <tr>
                            <th>When</th>
                            <th>Caller</th>
                            <th>Auth</th>
                            <th>Actions</th>
                            <th>Duration</th>
                            <th>Outcome</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            [...Array(3)].map((_, i) => (
                                <tr key={i}>
                                    {[...Array(6)].map((__, j) => (
                                        <td key={j}>
                                            <div className="skeleton h-4 w-20" />
                                        </td>
                                    ))}
                                </tr>
                            ))
                        ) : dormant ? (
                            <tr>
                                <td colSpan={6}>
                                    <DormantPanel
                                        icon="chat"
                                        title="No voice sessions yet"
                                        sub="Every command call is recorded here as an immutable, PIN-masked session — who called, what they asked, which actions ran and whether each cleared its step-up gate. Sessions appear once the voice line is live."
                                    />
                                </td>
                            </tr>
                        ) : rows.length === 0 ? (
                            <tr>
                                <td colSpan={6}>
                                    <DormantPanel
                                        icon="chat"
                                        title="No sessions recorded"
                                        sub="When a registered number calls and issues commands, the full session — transcript, actions and audit — lands here with the PIN always masked."
                                    />
                                </td>
                            </tr>
                        ) : (
                            rows.map((s) => {
                                const actions = s.actions || [];
                                return (
                                    <tr key={s.session_id}>
                                        <td className="text-t-secondary whitespace-nowrap">
                                            {fmt(s.started_at)}
                                        </td>
                                        <td className="font-mono text-body-2 text-t-primary td-num">
                                            {s.caller_id || "—"}
                                        </td>
                                        <td>
                                            {s.authed ? (
                                                <Badge variant="success" dot>
                                                    {s.auth_method === "otp" ? "OTP" : "PIN"}
                                                </Badge>
                                            ) : (
                                                <Badge variant="danger">failed</Badge>
                                            )}
                                        </td>
                                        <td>
                                            <div className="flex flex-wrap items-center gap-1">
                                                {actions.length === 0 ? (
                                                    <span className="text-caption text-t-tertiary">
                                                        read-only
                                                    </span>
                                                ) : (
                                                    actions.slice(0, 3).map((a, i) => (
                                                        <span
                                                            key={i}
                                                            className="inline-flex items-center gap-1"
                                                            title={a.intent}
                                                        >
                                                            <Badge variant={riskVariant(a.risk)}>
                                                                {a.intent || a.risk || "action"}
                                                            </Badge>
                                                        </span>
                                                    ))
                                                )}
                                                {actions.length > 3 && (
                                                    <span className="text-caption text-t-tertiary">
                                                        +{actions.length - 3}
                                                    </span>
                                                )}
                                            </div>
                                        </td>
                                        <td className="text-t-secondary whitespace-nowrap">
                                            {durationOf(s.started_at, s.ended_at)}
                                        </td>
                                        <td>
                                            <Badge
                                                variant={
                                                    (s.outcome || "").includes("ok")
                                                        ? "success"
                                                        : (s.outcome || "").includes("reject") ||
                                                          (s.outcome || "").includes("lockout")
                                                        ? "danger"
                                                        : "neutral"
                                                }
                                            >
                                                {s.outcome || "—"}
                                            </Badge>
                                        </td>
                                    </tr>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>
        </Card>
    );
}
