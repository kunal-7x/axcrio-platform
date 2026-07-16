"use client";

// AI MANAGER — TRY IT tab (was "Test Console").
//
// A chat box that hits the SAME command engine the inbound phone line uses. You
// type a natural-language command; the engine classifies it (intent · action ·
// risk · confirm/PIN gate · entities · missing fields · summary · safety) and
// replies — proving the engine works WITHOUT a phone, telephony or LLM creds.
//
// Lifecycle (master §12): test -> parse -> (confirm if needed) -> (PIN if needed)
// -> execute -> result. Risk is shown in plain language (Safe / Low / Medium /
// High / Blocked) via the shared parseRiskLabel — no raw L-codes. No masthead:
// the title is the single `<Layout title>` in page.tsx; this is the tab body.
//
// The /commands/test route is DEFERRED backend wiring, so the page degrades to a
// premium dormant view + the static command vocabulary — never an error wall.
// Data wiring stays in _lib.ts; presentation only.

import { useCallback, useEffect, useRef, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Select from "@/components/Select";
import {
    parseRiskVariant,
    parseRiskLabel,
    parseRiskLevel,
    rupees,
    fmt,
} from "./_shared";
import {
    testCommand,
    confirmCommand,
    cancelCommand,
    executeCommand,
    getAimSessions,
    AIM_CHANNELS,
    type AimChannel,
    type AimParse,
    type AimSession,
    type ReadResult,
} from "./_lib";

/* ----------------------------------------------------------------- types */

type TurnStage =
    | "parsed"
    | "confirming"
    | "executing"
    | "executed"
    | "not_done" // ran, but nothing actually landed (module off / parked / failed)
    | "cancelled"
    | "blocked"
    | "error";

type Turn =
    | { id: string; role: "user"; text: string }
    | {
          id: string;
          role: "ai";
          parse: AimParse;
          stage: TurnStage;
          busy?: boolean;
          note?: string;
      };

let TURN_SEQ = 0;
const nextId = () => `t${Date.now()}-${++TURN_SEQ}`;

// Channel picker options for the design-system Select (id === array index; the
// parallel `value` carries the AimChannel token the state setter expects).
const CHANNEL_OPTS = AIM_CHANNELS.map((c, i) => ({ id: i, name: c.label, value: c.value }));

/* ----------------------------------------------------- execution outcome */

// Read a status token off the parse OR off the nested execution_result blob the
// backend returns ({status, executed, reason, ...}). Tolerant of either shape so
// the chat stays honest regardless of which leg carried the verdict.
function execStatus(p: AimParse): string {
    const top = (p.status || "").toLowerCase();
    const er = p.execution_result;
    const inner =
        er && typeof er === "object" && !Array.isArray(er)
            ? String(
                  (er as Record<string, unknown>).status ??
                      (er as Record<string, unknown>).result_status ??
                      "",
              ).toLowerCase()
            : "";
    return inner || top;
}

// Did the action TRULY land? `executed`/`done` only — and only if nothing in the
// result flags it as parked / not-configured / failed (A2 truth-in-reporting).
function ranSucceeded(p: AimParse): boolean {
    const er = p.execution_result;
    const obj = er && typeof er === "object" && !Array.isArray(er) ? (er as Record<string, unknown>) : null;
    if (obj) {
        if (obj.executed === false || obj.ok === false) return false;
        const reason = String(obj.reason ?? "").toLowerCase();
        if (/not_configured|parked|disabled|unrouted|unauthorized|401|403/.test(reason)) return false;
    }
    const s = execStatus(p);
    if (/^(failed|needs_review|not_configured|parked|denied|error)$/.test(s)) return false;
    return /^(executed|done|success|succeeded|complete|ok)$/.test(s) || (obj?.executed === true);
}

// Reason a run didn't land, pulled from whatever the backend phrased it as.
function notDoneReason(p: AimParse): string {
    const er = p.execution_result;
    const obj = er && typeof er === "object" && !Array.isArray(er) ? (er as Record<string, unknown>) : null;
    const raw =
        (obj && (obj.reason ?? obj.detail ?? obj.message)) ?? p.error ?? "";
    const r = String(raw || "").toLowerCase();
    if (/not_configured|parked|disabled/.test(r))
        return "That module isn't switched on for your account yet, so nothing was changed.";
    if (/unauthorized|401|403|scope|permission/.test(r))
        return "I wasn't allowed to complete that action, so nothing was changed.";
    if (/unrouted/.test(r))
        return "I understood the request but couldn't route it to an action yet — nothing was changed.";
    if (raw) return String(raw);
    return "I couldn't complete that just now, so nothing was changed.";
}

/* =============================================================== the tab */

export default function TryItTab({ seedQuery = "" }: { seedQuery?: string }) {
    const [channel, setChannel] = useState<AimChannel>("dashboard");
    const [turns, setTurns] = useState<Turn[]>([]);
    const [input, setInput] = useState(seedQuery);
    const [thinking, setThinking] = useState(false);
    const [view, setView] = useState<"chat" | "trace">("chat");
    const [dormant, setDormant] = useState(false);

    const [pinFor, setPinFor] = useState<{ id: string; summary: string } | null>(null);
    const [sessions, setSessions] = useState<ReadResult<{ sessions: AimSession[] }> | null>(null);

    const threadRef = useRef<HTMLDivElement>(null);

    const loadSessions = useCallback(() => {
        getAimSessions({ limit: 20 }).then(setSessions);
    }, []);
    useEffect(() => {
        loadSessions();
    }, [loadSessions]);

    useEffect(() => {
        const el = threadRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [turns, thinking]);

    function pushTurn(t: Turn) {
        setTurns((prev) => [...prev, t]);
    }
    function patchTurn(id: string, patch: Partial<Extract<Turn, { role: "ai" }>>) {
        setTurns((prev) =>
            prev.map((t) => (t.id === id && t.role === "ai" ? { ...t, ...patch } : t))
        );
    }

    function stageOf(p: AimParse): TurnStage {
        const s = (p.status || "").toLowerCase();
        if (p.block_reason || parseRiskLevel(p.risk_level) >= 4 || s === "blocked") return "blocked";
        if (s === "cancelled") return "cancelled";
        if (s === "denied" || s === "error") return "error";

        // An execution attempt happened if the backend reports a terminal status
        // or returned an execution_result and no further gate is pending.
        const ran =
            /^(executed|done|failed|needs_review|not_configured|parked)$/.test(s) ||
            (p.execution_result != null && !p.requires_confirmation && !p.requires_pin);
        if (ran) {
            // Honest reporting: a run only counts as "Done" when the action truly
            // landed. A parked / not-configured / failed run (A2) must NOT show a
            // green success — it shows the human "couldn't do that yet" line.
            return ranSucceeded(p) ? "executed" : "not_done";
        }
        return "parsed";
    }

    async function send(text: string) {
        const utterance = text.trim();
        if (!utterance || thinking) return;
        setInput("");
        pushTurn({ id: nextId(), role: "user", text: utterance });
        setThinking(true);
        try {
            const parse = await testCommand(utterance, channel);
            setDormant(false);
            pushTurn({ id: nextId(), role: "ai", parse, stage: stageOf(parse) });
        } catch (e) {
            const msg = e instanceof Error ? e.message : "The engine could not parse that.";
            if (/not available yet|not configured/i.test(msg)) setDormant(true);
            pushTurn({
                id: nextId(),
                role: "ai",
                parse: { user_facing_summary: msg },
                stage: "error",
                note: msg,
            });
        } finally {
            setThinking(false);
        }
    }

    async function doConfirm(turn: Extract<Turn, { role: "ai" }>) {
        const id = turn.parse.command_id;
        if (!id) return;
        patchTurn(turn.id, { busy: true, stage: "confirming", note: undefined });
        try {
            const parse = await confirmCommand(id);
            const merged = { ...turn.parse, ...parse };
            if (parse.requires_pin || (parse.status || "").toLowerCase() === "needs_pin") {
                patchTurn(turn.id, { parse: merged, busy: false, stage: "parsed" });
                setPinFor({ id, summary: merged.user_facing_summary || "this action" });
            } else {
                patchTurn(turn.id, { parse: merged, busy: false, stage: stageOf(merged) });
                loadSessions();
            }
        } catch (e) {
            patchTurn(turn.id, {
                busy: false,
                stage: "parsed",
                note: e instanceof Error ? e.message : "Confirm failed",
            });
        }
    }

    async function doCancel(turn: Extract<Turn, { role: "ai" }>) {
        const id = turn.parse.command_id;
        if (!id) {
            patchTurn(turn.id, { stage: "cancelled" });
            return;
        }
        patchTurn(turn.id, { busy: true, note: undefined });
        try {
            await cancelCommand(id);
            patchTurn(turn.id, { busy: false, stage: "cancelled" });
        } catch (e) {
            patchTurn(turn.id, {
                busy: false,
                note: e instanceof Error ? e.message : "Cancel failed",
            });
        }
    }

    async function doExecute(turn: Extract<Turn, { role: "ai" }>) {
        const id = turn.parse.command_id;
        if (!id) return;
        patchTurn(turn.id, { busy: true, stage: "executing", note: undefined });
        try {
            const parse = await executeCommand(id);
            const merged = { ...turn.parse, ...parse };
            if (parse.requires_pin || (parse.status || "").toLowerCase() === "needs_pin") {
                patchTurn(turn.id, { parse: merged, busy: false, stage: "parsed" });
                setPinFor({ id, summary: merged.user_facing_summary || "this action" });
            } else {
                patchTurn(turn.id, { parse: merged, busy: false, stage: stageOf(merged) });
                loadSessions();
            }
        } catch (e) {
            patchTurn(turn.id, {
                busy: false,
                stage: "parsed",
                note: e instanceof Error ? e.message : "Execution failed",
            });
        }
    }

    async function submitPin(pin: string) {
        const target = pinFor;
        if (!target) return;
        setPinFor(null);
        const turn = turns.find(
            (t) => t.role === "ai" && t.parse.command_id === target.id
        ) as Extract<Turn, { role: "ai" }> | undefined;
        if (turn) patchTurn(turn.id, { busy: true, stage: "executing", note: undefined });
        try {
            const parse = await executeCommand(target.id, pin);
            if (turn) {
                const merged = { ...turn.parse, ...parse };
                patchTurn(turn.id, { parse: merged, busy: false, stage: stageOf(merged) });
            }
            loadSessions();
        } catch (e) {
            const msg = e instanceof Error ? e.message : "PIN did not match";
            if (turn) patchTurn(turn.id, { busy: false, stage: "parsed", note: msg });
        }
    }

    const sessionRows = sessions?.kind === "ok" ? sessions.data.sessions : [];

    return (
        <div className="flex gap-4 max-lg:flex-col">
            {/* Left rail — past test/voice sessions */}
            <div className="w-72 shrink-0 max-lg:w-full">
                <Card
                    title="Sessions"
                    headContent={
                        <span className="ml-auto inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                            masked
                        </span>
                    }
                >
                    <div className="px-3 pb-3 space-y-1.5 max-h-[28rem] overflow-y-auto scrollbar-none max-lg:max-h-56">
                        {sessionRows.length === 0 ? (
                            <div className="px-2 py-6 text-center text-caption text-t-tertiary">
                                No sessions yet. Your test commands and live calls appear here.
                            </div>
                        ) : (
                            sessionRows.map((s) => (
                                <div
                                    key={s.session_id}
                                    className="lift p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset"
                                >
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="font-mono text-caption text-t-primary truncate">
                                            {s.caller_id || "dashboard"}
                                        </span>
                                        <Badge variant={s.authed ? "success" : "neutral"}>
                                            {s.authed ? (s.auth_method === "otp" ? "OTP" : "PIN") : "—"}
                                        </Badge>
                                    </div>
                                    <div className="text-caption text-t-tertiary mt-1 truncate">
                                        {fmt(s.started_at)}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </Card>
            </div>

            {/* Right — the chat thread (the hero) */}
            <div className="flex-1 min-w-0">
                <Card
                    className="p-0 overflow-hidden"
                    title="Command thread"
                    headContent={
                        <div className="ml-auto flex items-center gap-2">
                            <Select
                                classButton="!h-8 !px-3 !rounded-full !border-s-stroke2 !text-caption !text-t-secondary !bg-transparent"
                                value={CHANNEL_OPTS.find((o) => o.value === channel) ?? null}
                                options={CHANNEL_OPTS}
                                onChange={(o) => setChannel(CHANNEL_OPTS[o.id].value)}
                            />
                            <div className="flex items-center gap-1 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle">
                                {(["chat", "trace"] as const).map((v) => (
                                    <button
                                        key={v}
                                        onClick={() => setView(v)}
                                        className={`h-7 px-3 rounded-full text-caption capitalize transition-colors ${
                                            view === v
                                                ? "bg-b-surface1 text-t-primary shadow-widget dark:bg-shade-04"
                                                : "text-t-secondary hover:text-t-primary"
                                        }`}
                                    >
                                        {v === "trace" ? "JSON trace" : "Chat"}
                                    </button>
                                ))}
                            </div>
                        </div>
                    }
                >
                    <div
                        ref={threadRef}
                        className="px-5 max-lg:px-3 h-[30rem] overflow-y-auto scrollbar-none"
                    >
                        {turns.length === 0 && !thinking ? (
                            <EmptyThread dormant={dormant} />
                        ) : view === "trace" ? (
                            <TraceView turns={turns} />
                        ) : (
                            <div className="py-4 space-y-4">
                                {turns.map((t) =>
                                    t.role === "user" ? (
                                        <UserBubble key={t.id} text={t.text} />
                                    ) : (
                                        <AiBubble
                                            key={t.id}
                                            turn={t}
                                            onConfirm={() => doConfirm(t)}
                                            onCancel={() => doCancel(t)}
                                            onExecute={() => doExecute(t)}
                                        />
                                    )
                                )}
                                {thinking && <ThinkingBubble />}
                            </div>
                        )}
                    </div>

                    {/* Composer */}
                    <div className="border-t border-s-subtle p-3 max-lg:p-2 bg-b-surface2/40">
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                send(input);
                            }}
                            className="flex items-end gap-2"
                        >
                            <textarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter" && !e.shiftKey) {
                                        e.preventDefault();
                                        send(input);
                                    }
                                }}
                                rows={1}
                                disabled={thinking}
                                placeholder="Type a command in your own words — Enter to send, Shift+Enter for a new line"
                                className="flex-1 min-h-11 max-h-32 px-4 py-2.5 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none resize-none transition-colors hover:border-s-highlight focus:border-primary-01/60 focus:ring-2 focus:ring-primary-01/30 placeholder:text-t-secondary/50 disabled:opacity-60"
                            />
                            <Button
                                isBlack
                                type="submit"
                                icon="send"
                                disabled={thinking || !input.trim()}
                                className="h-11 shrink-0"
                            >
                                Send
                            </Button>
                        </form>
                    </div>
                </Card>
            </div>

            {pinFor && (
                <PinModal
                    summary={pinFor.summary}
                    onCancel={() => setPinFor(null)}
                    onSubmit={submitPin}
                />
            )}
        </div>
    );
}

/* ------------------------------------------------------------ empty state */

function EmptyThread({ dormant }: { dormant: boolean }) {
    return (
        <div className="py-10 flex flex-col items-center text-center">
            <span className="grid place-items-center size-14 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                <Icon name="chat" className="size-7 fill-inherit" />
            </span>
            <div className="text-sub-title-1 text-t-primary mt-4">
                {dormant ? "Engine not configured yet" : "Type a command to test the engine"}
            </div>
            <p className="text-body-2 text-t-secondary mt-1.5 max-w-md">
                {dormant
                    ? "The command engine lights up once the AI Manager service token and intent model are provisioned on the server."
                    : "Speak to it like you would to a smart office manager, in your own words. It will work out the intent, score the risk, and ask for a confirm or PIN before doing anything that spends money or touches many records."}
            </p>
        </div>
    );
}

/* ------------------------------------------------------------- chat turns */

function UserBubble({ text }: { text: string }) {
    return (
        <div className="flex justify-end">
            <div className="max-w-[80%] rounded-2xl rounded-tr-md px-4 py-2.5 bg-primary-01 text-t-light text-body-2 shadow-sm">
                {text}
            </div>
        </div>
    );
}

function ThinkingBubble() {
    return (
        <div className="flex justify-start">
            <div className="inline-flex items-center gap-2 rounded-2xl rounded-tl-md px-4 py-3 bg-b-surface2 ring-1 ring-s-subtle ring-inset">
                <span className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                        <span
                            key={i}
                            className="size-1.5 rounded-full bg-t-tertiary animate-bounce"
                            style={{ animationDelay: `${i * 120}ms` }}
                        />
                    ))}
                </span>
                <span className="text-caption text-t-tertiary">Thinking…</span>
            </div>
        </div>
    );
}

function AiBubble({
    turn,
    onConfirm,
    onCancel,
    onExecute,
}: {
    turn: Extract<Turn, { role: "ai" }>;
    onConfirm: () => void;
    onCancel: () => void;
    onExecute: () => void;
}) {
    const p = turn.parse;
    const blocked = turn.stage === "blocked";
    const errored = turn.stage === "error";

    if (blocked) {
        return (
            <div className="flex justify-start">
                <div className="max-w-[88%] w-full rounded-2xl rounded-tl-md p-4 bg-primary-03/8 border border-primary-03/25">
                    <div className="flex items-center gap-2">
                        <Icon name="lock" className="size-4 fill-primary-03" />
                        <span className="text-sub-title-2 text-primary-03">Refused</span>
                        <Badge variant="danger" dot>
                            Blocked
                        </Badge>
                    </div>
                    <p className="text-body-2 text-t-primary mt-2">
                        {p.user_facing_summary || "This command is not permitted."}
                    </p>
                    {p.block_reason && (
                        <p className="text-caption text-t-tertiary mt-1.5">
                            Reason: {p.block_reason}
                        </p>
                    )}
                </div>
            </div>
        );
    }

    if (errored) {
        return (
            <div className="flex justify-start">
                <div className="max-w-[88%] w-full rounded-2xl rounded-tl-md p-4 bg-b-surface2 ring-1 ring-s-subtle ring-inset">
                    <div className="flex items-center gap-2">
                        <Icon name="info" className="size-4 fill-primary-03" />
                        <span className="text-body-2 text-t-primary">
                            {turn.note || p.user_facing_summary || "The engine couldn't handle that."}
                        </span>
                    </div>
                </div>
            </div>
        );
    }

    const entityRows = Object.entries(p.entities || {}).filter(
        ([, v]) => v != null && v !== ""
    );
    const needsConfirm = !!p.requires_confirmation && turn.stage === "parsed";
    const needsPin = !!p.requires_pin && turn.stage === "parsed";
    const canExecuteNow =
        turn.stage === "parsed" &&
        !p.requires_confirmation &&
        !p.requires_pin &&
        p.safe_to_execute !== false &&
        !!p.command_id;
    const executed = turn.stage === "executed";
    const notDone = turn.stage === "not_done";
    const cancelled = turn.stage === "cancelled";

    return (
        <div className="flex justify-start">
            <div className="max-w-[88%] w-full rounded-2xl rounded-tl-md p-4 bg-b-surface2 ring-1 ring-s-subtle ring-inset space-y-3">
                <div className="flex items-center gap-2 flex-wrap">
                    {p.intent && (
                        <span className="font-mono text-caption px-2 py-0.5 rounded-md bg-b-surface1 ring-1 ring-s-subtle text-t-secondary dark:bg-shade-04/50">
                            {p.intent}
                        </span>
                    )}
                    <Badge variant={parseRiskVariant(p.risk_level)} dot>
                        {parseRiskLabel(p.risk_level)}
                    </Badge>
                    {p.action_type && (
                        <span className="text-caption text-t-tertiary capitalize">{p.action_type}</span>
                    )}
                    {typeof p.confidence === "number" && (
                        <span className="text-caption text-t-tertiary ml-auto">
                            {Math.round(p.confidence * 100)}% sure
                        </span>
                    )}
                </div>

                {/* The parse summary. Suppressed once a terminal result panel
                    below carries its own human line (executed / not_done), so the
                    same sentence isn't shown twice. */}
                {p.user_facing_summary && !executed && !notDone && (
                    <p className="text-body-2 text-t-primary">{p.user_facing_summary}</p>
                )}

                {entityRows.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                        {entityRows.map(([k, v]) => (
                            <span
                                key={k}
                                className="inline-flex items-center gap-1 h-6 px-2 rounded-md bg-b-surface1 ring-1 ring-s-subtle text-caption text-t-secondary dark:bg-shade-04/50"
                            >
                                <span className="text-t-tertiary">{k}:</span>
                                <span className="text-t-primary">{String(v)}</span>
                            </span>
                        ))}
                    </div>
                )}

                {(p.missing_fields || []).length > 0 && (
                    <div className="text-caption text-t-secondary">
                        <span className="text-t-tertiary">Needs:</span>{" "}
                        {(p.missing_fields || []).join(", ")}
                    </div>
                )}

                {typeof p.cost_estimate_minor === "number" && p.cost_estimate_minor > 0 && (
                    <div className="inline-flex items-center gap-1.5 text-caption text-t-secondary">
                        <Icon name="wallet" className="size-3.5 fill-t-tertiary" />
                        Est. cost {rupees(p.cost_estimate_minor)}
                    </div>
                )}

                {executed && (
                    <div className="rounded-xl bg-primary-02/8 border border-primary-02/20 p-3">
                        <div className="flex items-center gap-2">
                            <Icon name="check-circle" className="size-4 fill-primary-02" />
                            <span className="text-sub-title-2 text-t-primary">Done</span>
                            {typeof p.cost_actual_minor === "number" && p.cost_actual_minor > 0 && (
                                <Badge variant="info">{rupees(p.cost_actual_minor)}</Badge>
                            )}
                        </div>
                        {/* Human result line — the spoken-style summary the engine
                            re-emits post-execute. NEVER the raw JSON (that lives in
                            the "JSON trace" tab for power users). */}
                        <p className="text-body-2 text-t-primary mt-1.5">
                            {p.user_facing_summary || "All done — the action completed."}
                        </p>
                        {p.action_run_id && (
                            <div className="font-mono text-caption text-t-tertiary mt-1.5">
                                run {p.action_run_id}
                            </div>
                        )}
                    </div>
                )}

                {notDone && (
                    <div className="rounded-xl bg-primary-03/6 border border-primary-03/20 p-3">
                        <div className="flex items-center gap-2">
                            <Icon name="info" className="size-4 fill-primary-03" />
                            <span className="text-sub-title-2 text-t-primary">Couldn&rsquo;t complete that</span>
                            <Badge variant="warning" dot>
                                Nothing changed
                            </Badge>
                        </div>
                        {/* Honest, human reason — no false "Executed", no raw JSON. */}
                        <p className="text-body-2 text-t-primary mt-1.5">
                            {p.user_facing_summary || notDoneReason(p)}
                        </p>
                        {p.action_run_id && (
                            <div className="font-mono text-caption text-t-tertiary mt-1.5">
                                run {p.action_run_id}
                            </div>
                        )}
                    </div>
                )}

                {cancelled && (
                    <div className="inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="close" className="size-3.5 fill-t-tertiary" />
                        Cancelled — nothing was executed.
                    </div>
                )}

                {turn.note && (
                    <div className="text-caption text-primary-03">{turn.note}</div>
                )}

                {(needsConfirm || needsPin || canExecuteNow) && (
                    <div className="flex items-center gap-2 pt-1">
                        {needsPin ? (
                            <Button
                                isBlack
                                icon="lock"
                                className="h-9"
                                disabled={turn.busy}
                                onClick={onExecute}
                            >
                                Enter PIN &amp; run
                            </Button>
                        ) : needsConfirm ? (
                            <Button
                                isBlack
                                icon="check"
                                className="h-9"
                                disabled={turn.busy}
                                onClick={onConfirm}
                            >
                                {turn.busy ? "Confirming…" : "Confirm"}
                            </Button>
                        ) : (
                            <Button
                                isBlack
                                icon="send"
                                className="h-9"
                                disabled={turn.busy}
                                onClick={onExecute}
                            >
                                {turn.busy ? "Running…" : "Run it"}
                            </Button>
                        )}
                        <Button
                            isStroke
                            className="h-9"
                            disabled={turn.busy}
                            onClick={onCancel}
                        >
                            Cancel
                        </Button>
                    </div>
                )}
            </div>
        </div>
    );
}

/* ---------------------------------------------------------------- trace */

function TraceView({ turns }: { turns: Turn[] }) {
    const ai = turns.filter((t) => t.role === "ai") as Extract<Turn, { role: "ai" }>[];
    if (ai.length === 0) {
        return (
            <div className="py-10 text-center text-caption text-t-tertiary">
                The raw engine JSON for each turn appears here once you send a command.
            </div>
        );
    }
    return (
        <div className="py-4 space-y-3">
            {ai.map((t) => (
                <pre
                    key={t.id}
                    className="text-caption text-t-secondary p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset overflow-x-auto whitespace-pre-wrap break-words font-mono"
                >
                    {JSON.stringify(t.parse, null, 2)}
                </pre>
            ))}
        </div>
    );
}

/* ------------------------------------------------------------- PIN modal */

function PinModal({
    summary,
    onCancel,
    onSubmit,
}: {
    summary: string;
    onCancel: () => void;
    onSubmit: (pin: string) => void;
}) {
    const [pin, setPin] = useState("");
    const ref = useRef<HTMLInputElement>(null);
    useEffect(() => {
        ref.current?.focus();
    }, []);
    return (
        <div
            className="fixed inset-0 z-50 grid place-items-center p-4 bg-shade-01/40 backdrop-blur-sm"
            onClick={onCancel}
        >
            <div
                className="w-full max-w-sm rounded-3xl bg-b-surface1 ring-1 ring-s-subtle shadow-depth p-6 rise-in"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="flex items-center gap-2">
                    <span className="grid place-items-center size-10 rounded-2xl bg-primary-04/10 fill-primary-04">
                        <Icon name="lock" className="size-5 fill-inherit" />
                    </span>
                    <div>
                        <div className="text-sub-title-1 text-t-primary">Step-up PIN required</div>
                        <div className="text-caption text-t-tertiary">This action is risky.</div>
                    </div>
                </div>
                <p className="text-body-2 text-t-secondary mt-3">{summary}</p>
                <form
                    onSubmit={(e) => {
                        e.preventDefault();
                        if (pin.trim()) onSubmit(pin.trim());
                    }}
                    className="mt-4 space-y-4"
                >
                    <input
                        ref={ref}
                        type="password"
                        inputMode="numeric"
                        autoComplete="off"
                        value={pin}
                        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                        placeholder="••••"
                        maxLength={8}
                        className="w-full h-12 px-4 text-center tracking-[0.5em] text-h6 border border-s-stroke2 rounded-2xl text-t-primary outline-none transition-colors focus:border-primary-01/60 focus:ring-2 focus:ring-primary-01/30"
                    />
                    <p className="text-caption text-t-tertiary">
                        The PIN is verified on the server and never stored or logged. A wrong PIN reveals
                        nothing and the action does not run.
                    </p>
                    <div className="flex items-center gap-2">
                        <Button
                            isBlack
                            type="submit"
                            className="flex-1 justify-center"
                            disabled={!pin.trim()}
                        >
                            Verify &amp; run
                        </Button>
                        <Button isStroke type="button" onClick={onCancel}>
                            Cancel
                        </Button>
                    </div>
                </form>
            </div>
        </div>
    );
}
