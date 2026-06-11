"use client";

// AI MANAGER — HOME tab (Overview + History + Approvals merged).
//
// The at-a-glance command-center pulse: live status + the AI Manager number, a
// KPI strip of real engine aggregates, and an inner two-tab area for the recent
// command Activity and the human-in-the-loop Approvals queue. No masthead/eyebrow
// — the page title is the single `<Layout title="AI Manager">` in page.tsx and
// the section switch is the reference `Tabs`. Risk is shown in plain language
// (Safe / Needs approval / Blocked) via the shared parseRiskLabel, never raw L-codes.
//
// All data wiring stays in _lib.ts; this is presentation only. Backend is
// DEFINED-NOT-MOUNTED today -> every read degrades to a premium dormant view.

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import { useMe, canWrite } from "@/lib/auth";
import {
    AimStat,
    ErrorBanner,
    parseRiskVariant,
    parseRiskLabel,
    rupees,
    fmt,
    statusVariant,
} from "./_shared";
import {
    getAimSummary,
    getAimStatus,
    getAimCommandHistory,
    confirmCommand,
    executeCommand,
    cancelCommand,
    commandId,
    commandText,
    commandIntent,
    channelGlyph,
    type AimSummary,
    type AimStatus,
    type AimHistoryCommand,
    type ReadResult,
} from "./_lib";

type Toast = { msg: string; type: "success" | "error" };

function needsPin(c: AimHistoryCommand): boolean {
    return !!(c.pin_required || c.requires_pin || /needs_pin/i.test(c.status || ""));
}
function rowCostMinor(c: AimHistoryCommand): number | null {
    if (typeof c.cost_minor === "number") return c.cost_minor;
    if (typeof c.cost_estimate_minor === "number") return c.cost_estimate_minor;
    if (typeof c.cost_actual_minor === "number") return c.cost_actual_minor;
    return null;
}

export default function HomeTab() {
    const router = useRouter();
    const { me } = useMe();
    const writable = canWrite(me);

    const [summary, setSummary] = useState<ReadResult<AimSummary> | null>(null);
    const [status, setStatus] = useState<ReadResult<AimStatus> | null>(null);
    const [history, setHistory] = useState<ReadResult<{ commands: AimHistoryCommand[] }> | null>(null);
    const [pending, setPending] = useState<ReadResult<{ commands: AimHistoryCommand[] }> | null>(null);
    const [loading, setLoading] = useState(true);
    const [sub, setSub] = useState<"activity" | "approvals">("activity");
    const [toast, setToast] = useState<Toast | null>(null);
    const [busyId, setBusyId] = useState("");

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4200);
    };

    const load = useCallback(() => {
        setLoading(true);
        Promise.all([
            getAimSummary().then(setSummary),
            getAimStatus().then(setStatus),
            getAimCommandHistory({ limit: 25 }).then(setHistory),
            getAimCommandHistory({
                status: "needs_confirmation,needs_pin,needs_review,pending",
                limit: 50,
            }).then(setPending),
        ]).finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const s = summary?.kind === "ok" ? summary.data : null;
    const st = status?.kind === "ok" ? status.data : null;
    const historyRows = history?.kind === "ok" ? history.data.commands || [] : [];
    const pendingRows = useMemo(
        () => (pending?.kind === "ok" ? pending.data.commands || [] : []),
        [pending]
    );

    const dormant = summary?.kind === "dormant" && status?.kind === "dormant";
    const summaryErr = summary?.kind === "error" ? summary.message : "";

    const enabled = !!(s?.enabled ?? st?.enabled);
    const sip = (s?.sip ?? st?.sip) === "configured";
    const phone = s?.phone_number || st?.agent_name;
    const voiceLive = enabled && sip;

    async function approve(c: AimHistoryCommand) {
        const id = commandId(c);
        setBusyId(id);
        try {
            await confirmCommand(id);
            await executeCommand(id);
            showToast("Approved and executed.");
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Approve failed", "error");
        } finally {
            setBusyId("");
        }
    }
    async function deny(c: AimHistoryCommand) {
        const id = commandId(c);
        setBusyId(id);
        try {
            await cancelCommand(id);
            showToast("Denied — command cancelled.");
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Deny failed", "error");
        } finally {
            setBusyId("");
        }
    }

    return (
        <>
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">
                        ×
                    </button>
                </div>
            )}

            <ErrorBanner msg={summaryErr} />

            {/* Two-column rhythm: primary (left) + secondary (right) */}
            <div className="flex gap-4 max-lg:flex-col">
                <div className="flex-1 min-w-0 space-y-3">
                    {/* Status + phone strip */}
                    <div className="card overflow-hidden">
                        <div className="relative flex items-center gap-4 p-5 max-lg:p-4 max-sm:flex-col max-sm:items-start">
                            <span
                                className={`relative grid place-items-center size-12 shrink-0 rounded-2xl ring-1 ring-s-subtle ${
                                    voiceLive ? "bg-primary-02/10 fill-primary-02" : "bg-b-surface2 fill-primary-01"
                                }`}
                            >
                                <Icon name="mobile" className="size-6 fill-inherit" />
                            </span>
                            <div className="relative min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <span className="text-body-2 text-t-secondary">AI Manager line</span>
                                    <Badge variant={voiceLive ? "success" : "info"} dot>
                                        {voiceLive ? "Live" : "Coming soon"}
                                    </Badge>
                                </div>
                                <div className="text-h5 text-t-primary mt-0.5 truncate">
                                    {phone && voiceLive ? phone : "Not provisioned yet"}
                                </div>
                                <div className="text-caption text-t-tertiary mt-0.5">
                                    {voiceLive
                                        ? "Registered managers can call this number and command by voice."
                                        : "The inbound line lights up once telephony and the service token are provisioned."}
                                </div>
                            </div>
                            <button
                                onClick={load}
                                disabled={loading}
                                className="relative shrink-0 inline-flex items-center justify-center gap-2 h-10 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary hover:shadow-widget active:scale-[0.98] disabled:opacity-50"
                            >
                                <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                                Refresh
                            </button>
                        </div>
                    </div>

                    {/* KPI strip — real engine aggregates, plain language */}
                    <div className="grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                        <AimStat
                            label="Commands today"
                            glyph="dashboard"
                            glyphClass="fill-primary-01"
                            accent="var(--primary-01)"
                            loading={loading && !s}
                            value={s?.commands_today ?? 0}
                            foot="Across all channels"
                        />
                        <AimStat
                            label="Succeeded"
                            glyph="check-circle"
                            glyphClass="fill-primary-02"
                            accent="var(--primary-02)"
                            delay={50}
                            loading={loading && !s}
                            value={s?.commands_succeeded ?? 0}
                            foot="Executed cleanly"
                        />
                        <AimStat
                            label="Needs approval"
                            glyph="lock"
                            glyphClass="fill-primary-04"
                            accent="var(--primary-04)"
                            delay={100}
                            loading={loading && !s}
                            value={s?.pending_approvals ?? pendingRows.length}
                            foot="Awaiting confirm / PIN"
                        />
                        <AimStat
                            label="Credit impact"
                            glyph="wallet"
                            glyphClass="fill-primary-05"
                            accent="var(--primary-05)"
                            delay={150}
                            loading={loading && !s}
                            value={rupees(s?.credit_impact_minor ?? 0)}
                            foot={
                                s?.wallet_balance_minor != null
                                    ? `Balance ${rupees(s.wallet_balance_minor)}`
                                    : "Spent by the AI Manager today"
                            }
                        />
                    </div>

                    {/* Activity / Approvals — inner reference Tabs */}
                    <Card
                        title={sub === "activity" ? "Recent activity" : "Pending approvals"}
                        headContent={
                            <div className="ml-auto flex items-center gap-1 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle">
                                {(["activity", "approvals"] as const).map((v) => (
                                    <button
                                        key={v}
                                        onClick={() => setSub(v)}
                                        className={`inline-flex items-center gap-1.5 h-8 px-3.5 rounded-full text-button capitalize transition-colors ${
                                            sub === v
                                                ? "bg-b-surface1 text-t-primary shadow-widget dark:bg-shade-04"
                                                : "text-t-secondary hover:text-t-primary"
                                        }`}
                                    >
                                        {v}
                                        {v === "approvals" && pendingRows.length > 0 && (
                                            <span className="pill pill-warning !px-1.5 !py-0 text-caption">
                                                {pendingRows.length}
                                            </span>
                                        )}
                                    </button>
                                ))}
                            </div>
                        }
                    >
                        {sub === "activity" ? (
                            <ActivityTable
                                rows={historyRows}
                                loading={loading && !history}
                                dormant={history?.kind === "dormant"}
                            />
                        ) : (
                            <ApprovalsList
                                rows={pendingRows}
                                loading={loading && !pending}
                                dormant={pending?.kind === "dormant"}
                                writable={writable}
                                busyId={busyId}
                                onApprove={approve}
                                onDeny={deny}
                            />
                        )}
                    </Card>
                </div>

                {/* Right column — quick test + configuration */}
                <div className="w-80 shrink-0 max-lg:w-full space-y-3">
                    <QuickTest onRun={(t) => router.push(`/ai-manager?tab=tryit${t ? `&q=${encodeURIComponent(t)}` : ""}`)} />

                    <Card title="Configuration">
                        <div className="px-5 pb-5 max-lg:px-3">
                            <div className="divide-y divide-s-subtle">
                                <ConfigRow icon="dashboard" label="Command engine" hint="Master switch">
                                    {enabled ? <Badge variant="success" dot>On</Badge> : <Badge variant="neutral">Off</Badge>}
                                </ConfigRow>
                                <ConfigRow icon="mobile" label="Phone line" hint="The number managers call">
                                    {sip ? <Badge variant="info" dot>Ready</Badge> : <Badge variant="neutral">Not set</Badge>}
                                </ConfigRow>
                                <ConfigRow icon="chat" label="Understanding" hint="Turns speech into a command">
                                    {st?.llm_provider && st.llm_provider !== "none" ? (
                                        <Badge variant="info" dot>{pretty(st.llm_provider)}</Badge>
                                    ) : (
                                        <Badge variant="neutral">Offline matcher</Badge>
                                    )}
                                </ConfigRow>
                            </div>
                            {(dormant || !voiceLive) && (
                                <p className="text-caption text-t-tertiary mt-4">
                                    The engine is built and safe to test now. Counts and the live line fill in once
                                    telephony and the intent model are provisioned.
                                </p>
                            )}
                        </div>
                    </Card>
                </div>
            </div>
        </>
    );
}

/* --------------------------------------------------------------- pieces */

function pretty(p?: string | null): string {
    if (!p || p === "none") return "Not set";
    return p.charAt(0).toUpperCase() + p.slice(1);
}

function QuickTest({ onRun }: { onRun: (text: string) => void }) {
    const [quick, setQuick] = useState("");
    return (
        <Card title="Try a command">
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    onRun(quick.trim());
                }}
                className="px-5 pb-5 max-lg:px-3 space-y-2.5"
            >
                <input
                    value={quick}
                    onChange={(e) => setQuick(e.target.value)}
                    placeholder='e.g. "How many hot leads today?"'
                    className="w-full h-11 px-4 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-primary-01/60 focus:ring-2 focus:ring-primary-01/30 placeholder:text-t-secondary/50"
                />
                <Button isBlack type="submit" icon="send" className="w-full justify-center h-11">
                    Try it
                </Button>
            </form>
        </Card>
    );
}

function ActivityTable({
    rows,
    loading,
    dormant,
}: {
    rows: AimHistoryCommand[];
    loading: boolean;
    dormant: boolean;
}) {
    return (
        <div className="overflow-x-auto">
            <table className="data-table">
                <thead>
                    <tr>
                        <th>When</th>
                        <th>Command</th>
                        <th>Risk</th>
                        <th>Result</th>
                        <th className="text-right pr-5">Cost</th>
                    </tr>
                </thead>
                <tbody>
                    {loading ? (
                        [...Array(5)].map((_, i) => (
                            <tr key={i}>
                                {[...Array(5)].map((__, j) => (
                                    <td key={j}><div className="skeleton h-4 w-20" /></td>
                                ))}
                            </tr>
                        ))
                    ) : rows.length === 0 ? (
                        <tr>
                            <td colSpan={5}>
                                <MiniEmpty
                                    icon={dormant ? "list" : "chat"}
                                    title={dormant ? "Activity appears once the engine runs" : "No commands yet"}
                                    sub={
                                        dormant
                                            ? "Every parsed command — voice, WhatsApp or this dashboard — lands here with its risk and outcome."
                                            : "Run a command from Try it and it shows up here with its risk and result."
                                    }
                                />
                            </td>
                        </tr>
                    ) : (
                        rows.map((c) => {
                            const cm = rowCostMinor(c);
                            const stt = c.status || c.result_status;
                            return (
                                <tr key={commandId(c) || Math.random()}>
                                    <td className="text-t-secondary whitespace-nowrap">{fmt(c.created_at)}</td>
                                    <td className="max-w-[20rem]">
                                        <div className="flex items-center gap-2 min-w-0">
                                            <Icon name={channelGlyph(c.channel)} className="size-3.5 fill-t-tertiary shrink-0" />
                                            <span className="text-body-2 text-t-primary truncate" title={commandText(c)}>
                                                {commandText(c) || commandIntent(c) || "—"}
                                            </span>
                                        </div>
                                    </td>
                                    <td>
                                        <Badge variant={parseRiskVariant(c.risk_level)}>
                                            {parseRiskLabel(c.risk_level)}
                                        </Badge>
                                    </td>
                                    <td>
                                        <Badge variant={statusVariant(stt)}>
                                            {(stt || "—").replace(/_/g, " ")}
                                        </Badge>
                                    </td>
                                    <td className="text-right pr-5 tabular-nums text-t-secondary whitespace-nowrap">
                                        {cm == null ? "—" : rupees(cm)}
                                    </td>
                                </tr>
                            );
                        })
                    )}
                </tbody>
            </table>
        </div>
    );
}

function ApprovalsList({
    rows,
    loading,
    dormant,
    writable,
    busyId,
    onApprove,
    onDeny,
}: {
    rows: AimHistoryCommand[];
    loading: boolean;
    dormant: boolean;
    writable: boolean;
    busyId: string;
    onApprove: (c: AimHistoryCommand) => void;
    onDeny: (c: AimHistoryCommand) => void;
}) {
    return (
        <div className="px-5 pb-5 max-lg:px-3 space-y-2.5">
            {loading ? (
                [...Array(3)].map((_, i) => <div key={i} className="skeleton h-20 w-full rounded-2xl" />)
            ) : rows.length === 0 ? (
                <MiniEmpty
                    icon="check-circle"
                    title={dormant ? "Approvals appear when commands need sign-off" : "All clear — nothing pending"}
                    sub={
                        dormant
                            ? "Risky commands — bulk calls, spend changes, exports — park here for your confirm or PIN. Nothing risky runs without a human."
                            : "No commands are waiting on a confirm or step-up PIN right now."
                    }
                />
            ) : (
                rows.map((c) => {
                    const pin = needsPin(c);
                    const cm = rowCostMinor(c);
                    const requester = c.actor || c.caller_id || c.caller_phone || "—";
                    return (
                        <div
                            key={commandId(c)}
                            className="rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-4 flex items-start gap-3 max-md:flex-col"
                        >
                            <span className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-t-secondary dark:bg-shade-04">
                                <Icon name={channelGlyph(c.channel)} className="size-4.5 fill-inherit" />
                            </span>
                            <div className="min-w-0 flex-1">
                                <div className="text-body-2 text-t-primary">&ldquo;{commandText(c) || commandIntent(c)}&rdquo;</div>
                                <div className="flex items-center gap-2 flex-wrap mt-2">
                                    <Badge variant={parseRiskVariant(c.risk_level)}>{parseRiskLabel(c.risk_level)}</Badge>
                                    {pin ? <Badge variant="danger" dot>Needs PIN</Badge> : <Badge variant="warning">Needs confirm</Badge>}
                                    {cm != null && <span className="text-caption text-t-secondary tabular-nums">est {rupees(cm)}</span>}
                                </div>
                                <div className="text-caption text-t-tertiary mt-1.5">
                                    From {requester}
                                    {c.created_at && <span className="ml-2">· {fmt(c.created_at)}</span>}
                                </div>
                            </div>
                            {writable ? (
                                <div className="flex items-center gap-2 shrink-0 max-md:w-full">
                                    <button
                                        onClick={() => onDeny(c)}
                                        disabled={busyId === commandId(c)}
                                        className="inline-flex items-center gap-1 h-9 px-3.5 rounded-full border border-s-subtle text-button text-primary-03 fill-primary-03 transition-colors hover:bg-primary-03/8 disabled:opacity-50 max-md:flex-1 max-md:justify-center"
                                    >
                                        <Icon name="close" className="size-3.5 fill-current" />
                                        Deny
                                    </button>
                                    <button
                                        onClick={() => onApprove(c)}
                                        disabled={busyId === commandId(c)}
                                        className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full bg-t-primary text-b-surface1 text-button fill-b-surface1 transition-all hover:opacity-90 active:scale-[0.98] disabled:opacity-50 max-md:flex-1 max-md:justify-center"
                                    >
                                        <Icon name={pin ? "lock" : "check"} className="size-3.5 fill-current" />
                                        {busyId === commandId(c) ? "…" : "Approve"}
                                    </button>
                                </div>
                            ) : (
                                <Badge variant="neutral">view only</Badge>
                            )}
                        </div>
                    );
                })
            )}
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

function MiniEmpty({ icon, title, sub }: { icon: string; title: string; sub: string }) {
    return (
        <div className="state-block">
            <span className="state-glyph">
                <Icon name={icon} className="fill-inherit" />
            </span>
            <div className="state-title">{title}</div>
            <div className="state-sub max-w-md mx-auto">{sub}</div>
        </div>
    );
}
