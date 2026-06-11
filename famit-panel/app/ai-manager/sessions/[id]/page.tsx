"use client";

// AI Manager — SESSION DETAIL (master §14 "Session Detail", DB ai_manager_sessions
// + commands + audit_logs + action_runs §8).
//
// The full record of one command session: header summary (caller, channel, auth,
// outcome, duration, providers) · the transcript thread (PIN-masked per §7) · the
// command chain / execution timeline (each command = intent · risk · permission ·
// pin · status · cost · result) · immutable audit logs · async action runs (job_id,
// output, error) · provider metadata · a link to the voice recording player.
//
// Archetype: Two-pane record detail. Built on the in-app Signal language (Layout /
// AimHeader / Card / Badge / Icon) + verified globals.css utilities, reusing
// _shared.tsx helpers. Three parallel reads (session / audit-logs / action-runs)
// each degrade independently to a premium dormant view — never an error wall.
// Edits ONLY this route's file. No shared component touched.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import {
    DormantPanel,
    ErrorBanner,
    fmt,
    parseRiskVariant,
    parseRiskLabel,
    statusVariant,
    rupees,
} from "../../_shared";
import {
    getAimSessionDetail,
    getAimAuditLogs,
    getAimActionRuns,
    commandId,
    commandText,
    commandIntent,
    channelGlyph,
    type AimSessionDetail,
    type AimHistoryCommand,
    type AimAuditLog,
    type AimActionRun,
    type AimTurn,
    type ReadResult,
} from "../../_lib";

/* ----------------------------------------------------------------- helpers */

function durationOf(a?: string | null, b?: string | null): string {
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

function severityVariant(s?: string): "success" | "danger" | "warning" | "info" | "neutral" {
    const t = (s || "").toLowerCase();
    if (/(critical|error|alert|fatal)/.test(t)) return "danger";
    if (/(warn|notice)/.test(t)) return "warning";
    if (/(info|debug)/.test(t)) return "info";
    return "neutral";
}

function runStatusVariant(s?: string): "success" | "danger" | "warning" | "info" | "neutral" {
    const t = (s || "").toLowerCase();
    if (/(succeeded|done|complete)/.test(t)) return "success";
    if (/(failed|error|cancelled)/.test(t)) return "danger";
    if (/(running|queued|retried|retry|pending)/.test(t)) return "warning";
    return "neutral";
}

function rowCostMinor(c: AimHistoryCommand): number | null {
    if (typeof c.cost_minor === "number") return c.cost_minor;
    if (typeof c.cost_actual_minor === "number") return c.cost_actual_minor;
    if (typeof c.cost_estimate_minor === "number") return c.cost_estimate_minor;
    return null;
}

// Pretty-print a small JSON blob for the audit/run detail rows.
function tinyJson(v: unknown): string {
    if (v == null) return "";
    if (typeof v === "string") return v;
    try {
        return JSON.stringify(v);
    } catch {
        return String(v);
    }
}

/* ============================================================== the page */

export default function AimSessionDetailPage() {
    const params = useParams();
    const id = String(params?.id || "");

    const [session, setSession] = useState<ReadResult<AimSessionDetail> | null>(null);
    const [audit, setAudit] = useState<ReadResult<{ logs: AimAuditLog[] }> | null>(null);
    const [runs, setRuns] = useState<ReadResult<{ runs: AimActionRun[] }> | null>(null);
    const [loading, setLoading] = useState(true);

    const load = useCallback(() => {
        if (!id) return;
        setLoading(true);
        Promise.all([
            getAimSessionDetail(id).then(setSession),
            getAimAuditLogs({ session_id: id }).then(setAudit),
            getAimActionRuns({ session_id: id }).then(setRuns),
        ]).finally(() => setLoading(false));
    }, [id]);

    useEffect(() => {
        load();
    }, [load]);

    const s = session?.kind === "ok" ? session.data : null;
    const sessionDormant = session?.kind === "dormant";
    const sessionError = session?.kind === "error" ? session.message : "";

    const turns: AimTurn[] = useMemo(() => {
        if (!s) return [];
        if (s.turns && s.turns.length) return s.turns;
        // tolerate the list-shape {role,text}[] too
        return [];
    }, [s]);

    const commands: AimHistoryCommand[] = s?.commands || [];
    const logs = audit?.kind === "ok" ? audit.data.logs || [] : [];
    const runRows = runs?.kind === "ok" ? runs.data.runs || [] : [];

    const caller = s?.caller_id || s?.caller_phone || "—";
    const recordingUrl = s?.recording_url;

    return (
        <Layout title="Session">
            {/* Back + refresh row (title is the single Layout heading) */}
            <div className="flex items-center gap-2 mb-5">
                <Link
                    href="/ai-manager"
                    className="inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget"
                >
                    <Icon name="arrow" className="size-4 fill-current rotate-180" />
                    Back to AI Manager
                </Link>
                <button
                    onClick={load}
                    disabled={loading}
                    className="ml-auto inline-flex items-center justify-center gap-2 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50"
                >
                    <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </button>
            </div>

            <ErrorBanner msg={sessionError} />

            {/* ---- Header summary block ---- */}
            <div className="card overflow-hidden mb-3">
                <div className="relative p-5 max-lg:p-4">
                    {loading && !session ? (
                        <div className="grid grid-cols-5 gap-4 max-md:grid-cols-2">
                            {[...Array(5)].map((_, i) => (
                                <div key={i}>
                                    <div className="skeleton h-3 w-16 mb-2" />
                                    <div className="skeleton h-5 w-24" />
                                </div>
                            ))}
                        </div>
                    ) : sessionDormant || !s ? (
                        <div className="flex items-center gap-3">
                            <span className="grid place-items-center size-10 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-t-secondary">
                                <Icon name="chat" className="size-5 fill-inherit" />
                            </span>
                            <div>
                                <div className="text-h6 text-t-primary">Session {id ? id.slice(0, 12) : ""}</div>
                                <div className="text-caption text-t-tertiary">
                                    {sessionDormant
                                        ? "Sessions appear once the voice line is live."
                                        : "This session could not be found."}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="grid grid-cols-5 gap-4 max-lg:grid-cols-3 max-md:grid-cols-2">
                            <SummaryItem label="Caller" value={<span className="font-mono td-num">{caller}</span>} />
                            <SummaryItem
                                label="Channel"
                                value={
                                    <span className="inline-flex items-center gap-1.5 capitalize">
                                        <Icon name={channelGlyph(s.channel)} className="size-3.5 fill-t-tertiary" />
                                        {s.channel || "—"}
                                    </span>
                                }
                            />
                            <SummaryItem
                                label="Auth"
                                value={
                                    s.authed ? (
                                        <Badge variant="success" dot>
                                            {s.auth_method === "otp" ? "OTP" : "PIN"}
                                        </Badge>
                                    ) : (
                                        <Badge variant="danger">failed</Badge>
                                    )
                                }
                            />
                            <SummaryItem label="Duration" value={durationOf(s.started_at, s.ended_at)} />
                            <SummaryItem
                                label="Outcome"
                                value={
                                    <Badge variant={statusVariant(s.outcome || s.status)}>
                                        {(s.outcome || s.status || "—").replace(/_/g, " ")}
                                    </Badge>
                                }
                            />
                        </div>
                    )}

                    {/* Provider metadata strip + recording link */}
                    {s && (
                        <div className="mt-4 pt-4 border-t border-s-subtle flex flex-wrap items-center gap-x-5 gap-y-2">
                            <ProviderChip label="STT" value={s.stt_provider} />
                            <ProviderChip label="TTS" value={s.tts_provider} />
                            <ProviderChip label="LLM" value={s.llm_provider} />
                            {s.started_at && (
                                <span className="text-caption text-t-tertiary">Started {fmt(s.started_at)}</span>
                            )}
                            {recordingUrl && (
                                <Link
                                    href={`/ai-manager/sessions/${encodeURIComponent(id)}/play`}
                                    className="ml-auto inline-flex items-center gap-1.5 h-8 px-3 rounded-full border border-s-subtle text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary"
                                >
                                    <Icon name="camera-video" className="size-3.5 fill-current" />
                                    Open in Player
                                </Link>
                            )}
                        </div>
                    )}
                </div>
            </div>

            <div className="flex gap-3 max-lg:flex-col">
                {/* ---- LEFT: transcript thread ---- */}
                <div className="flex-1 min-w-0">
                    <Card
                        title="Transcript"
                        headContent={
                            <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                                <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                                PIN-masked
                            </span>
                        }
                    >
                        <div className="px-5 max-lg:px-3 pb-5 space-y-3">
                            {loading && !session ? (
                                [...Array(4)].map((_, i) => (
                                    <div key={i} className={`flex ${i % 2 ? "justify-end" : ""}`}>
                                        <div className="skeleton h-12 w-2/3 rounded-2xl" />
                                    </div>
                                ))
                            ) : sessionDormant || turns.length === 0 ? (
                                <DormantPanel
                                    icon="chat"
                                    title={sessionDormant ? "No transcript yet" : "No transcript on this session"}
                                    sub="Each spoken or typed turn appears here in order, with any PIN or secret masked. Transcripts land once the voice line is live."
                                />
                            ) : (
                                turns.map((t, i) => <TranscriptTurn key={i} turn={t} />)
                            )}
                        </div>
                    </Card>
                </div>

                {/* ---- RIGHT: command chain + audit + runs ---- */}
                <div className="w-[26rem] max-lg:w-full shrink-0 space-y-3">
                    {/* Command chain / execution timeline */}
                    <Card title="Command chain">
                        <div className="px-5 max-lg:px-3 pb-5">
                            {loading && !session ? (
                                <div className="space-y-3">
                                    {[...Array(3)].map((_, i) => (
                                        <div key={i} className="skeleton h-16 w-full rounded-2xl" />
                                    ))}
                                </div>
                            ) : sessionDormant || commands.length === 0 ? (
                                <DormantPanel
                                    icon="layers"
                                    title="No commands in this session"
                                    sub="When the caller issues commands, each one appears here as a timeline step — intent, risk, the step-up result and its outcome."
                                />
                            ) : (
                                <ol className="relative space-y-3">
                                    {commands.map((c, i) => (
                                        <CommandStep key={commandId(c) || i} c={c} last={i === commands.length - 1} />
                                    ))}
                                </ol>
                            )}
                        </div>
                    </Card>

                    {/* Action runs */}
                    <Card title="Action runs">
                        <div className="px-5 max-lg:px-3 pb-5 space-y-2">
                            {loading && !runs ? (
                                [...Array(2)].map((_, i) => <div key={i} className="skeleton h-12 w-full rounded-2xl" />)
                            ) : runs?.kind === "dormant" || runRows.length === 0 ? (
                                <div className="text-caption text-t-tertiary py-3 text-center">
                                    No async action runs recorded.
                                </div>
                            ) : (
                                runRows.map((r) => <ActionRunRow key={r.id} r={r} />)
                            )}
                        </div>
                    </Card>

                    {/* Audit logs */}
                    <Card
                        title="Audit log"
                        headContent={
                            <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                                <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                                Immutable
                            </span>
                        }
                    >
                        <div className="px-5 max-lg:px-3 pb-5 space-y-2">
                            {loading && !audit ? (
                                [...Array(3)].map((_, i) => <div key={i} className="skeleton h-10 w-full rounded-2xl" />)
                            ) : audit?.kind === "dormant" || logs.length === 0 ? (
                                <div className="text-caption text-t-tertiary py-3 text-center">
                                    No audit events for this session.
                                </div>
                            ) : (
                                logs.map((l) => <AuditRow key={l.id} l={l} />)
                            )}
                        </div>
                    </Card>
                </div>
            </div>
        </Layout>
    );
}

/* ----------------------------------------------------------- sub-components */

function SummaryItem({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div className="min-w-0">
            <div className="text-caption text-t-tertiary mb-1">{label}</div>
            <div className="text-body-2 text-t-primary truncate">{value}</div>
        </div>
    );
}

function ProviderChip({ label, value }: { label: string; value?: string }) {
    return (
        <span className="inline-flex items-center gap-1.5 text-caption">
            <span className="text-t-tertiary">{label}</span>
            <span className="font-mono text-t-secondary">{value || "—"}</span>
        </span>
    );
}

function TranscriptTurn({ turn }: { turn: AimTurn }) {
    const isUser = (turn.role || "").toLowerCase() === "user";
    const isSystem = (turn.role || "").toLowerCase() === "system";
    if (isSystem) {
        return (
            <div className="flex justify-center">
                <span className="px-3 py-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-caption text-t-tertiary">
                    {turn.text}
                </span>
            </div>
        );
    }
    return (
        <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
            <div
                className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-body-2 ${
                    isUser
                        ? "bg-primary-01/10 text-t-primary rounded-br-md"
                        : "bg-b-surface2 ring-1 ring-s-subtle text-t-primary rounded-bl-md"
                }`}
            >
                <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-caption text-t-tertiary capitalize">{isUser ? "Caller" : "AI Manager"}</span>
                    {turn.masked && <Badge variant="neutral">masked</Badge>}
                </div>
                {turn.text}
                {turn.at && <div className="text-caption text-t-tertiary mt-1">{fmt(turn.at)}</div>}
            </div>
        </div>
    );
}

function CommandStep({ c, last }: { c: AimHistoryCommand; last: boolean }) {
    const cm = rowCostMinor(c);
    const st = c.status || c.result_status;
    const perm = c.permission_result;
    const allowed = perm?.allowed;
    return (
        <li className="relative pl-7">
            {/* timeline rail */}
            <span
                className={`absolute left-2 top-1.5 size-2.5 rounded-full ring-2 ring-b-surface1 ${
                    /succeeded|executed/i.test(st || "")
                        ? "bg-primary-02"
                        : /denied|failed|blocked|cancelled/i.test(st || "")
                        ? "bg-primary-03"
                        : "bg-primary-05"
                }`}
            />
            {!last && <span className="absolute left-[11px] top-4 bottom-[-12px] w-px bg-s-subtle" />}
            <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-caption text-t-secondary">{commandIntent(c) || "command"}</span>
                    <Badge variant={parseRiskVariant(c.risk_level)}>{parseRiskLabel(c.risk_level)}</Badge>
                    <Badge variant={statusVariant(st)}>{(st || "—").replace(/_/g, " ")}</Badge>
                </div>
                {commandText(c) && (
                    <div className="text-body-2 text-t-primary mt-1.5">&ldquo;{commandText(c)}&rdquo;</div>
                )}
                <div className="flex items-center gap-x-3 gap-y-1 flex-wrap mt-2 text-caption text-t-tertiary">
                    {perm && (
                        <span className="inline-flex items-center gap-1">
                            <Icon
                                name={allowed ? "check" : "block"}
                                className={`size-3 ${allowed ? "fill-primary-02" : "fill-primary-03"}`}
                            />
                            {allowed ? "permission allowed" : perm.reason || "permission denied"}
                        </span>
                    )}
                    {c.pin_required && (
                        <span className="inline-flex items-center gap-1">
                            <Icon
                                name="lock"
                                className={`size-3 ${c.pin_verified ? "fill-primary-02" : "fill-primary-05"}`}
                            />
                            {c.pin_verified ? "PIN verified" : "PIN required"}
                        </span>
                    )}
                    {cm != null && <span className="tabular-nums">{rupees(cm)}</span>}
                </div>
                {c.error_message && (
                    <div className="text-caption text-primary-03 mt-1.5">{c.error_message}</div>
                )}
            </div>
        </li>
    );
}

function ActionRunRow({ r }: { r: AimActionRun }) {
    const err = typeof r.error === "string" ? r.error : tinyJson(r.error);
    return (
        <div className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-3">
            <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-caption text-t-secondary">
                    {r.action_type || r.target_module || "run"}
                </span>
                <Badge variant={runStatusVariant(r.status)}>{r.status || "—"}</Badge>
                {r.job_id && <span className="font-mono text-caption text-t-tertiary">#{r.job_id}</span>}
            </div>
            <div className="text-caption text-t-tertiary mt-1.5 flex flex-wrap gap-x-3">
                {r.started_at && <span>start {fmt(r.started_at)}</span>}
                {r.completed_at && <span>done {fmt(r.completed_at)}</span>}
            </div>
            {err && <div className="text-caption text-primary-03 mt-1">{err}</div>}
        </div>
    );
}

function AuditRow({ l }: { l: AimAuditLog }) {
    return (
        <div className="flex items-start gap-2.5 py-1.5">
            <Badge variant={severityVariant(l.severity)} className="mt-0.5 shrink-0">
                {l.severity || "info"}
            </Badge>
            <div className="min-w-0 flex-1">
                <div className="text-body-2 text-t-primary">
                    {l.message || l.event_type || "event"}
                </div>
                <div className="text-caption text-t-tertiary">
                    {l.event_type && <span className="font-mono">{l.event_type}</span>}
                    {l.created_at && <span className="ml-2">{fmt(l.created_at)}</span>}
                </div>
            </div>
        </div>
    );
}
