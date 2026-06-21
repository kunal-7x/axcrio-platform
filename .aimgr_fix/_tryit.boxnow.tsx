"use client";

// AI MANAGER — TRY IT (the assistant chat).
//
// A ChatGPT-style assistant for your business. Type ANY question in plain words
// ("how many leads do I have?", "what happened today?", "call my hot leads") and
// it answers naturally — it reads your live data and replies in a sentence, no
// jargon, no risk codes, no engine internals. It only ever asks you to confirm /
// enter a PIN when an action genuinely changes something (spends money / touches
// many records). Everything else just answers.
//
// Presentation lives here; data wiring (the same command engine the phone line
// uses) lives in _lib.ts. The backend already returns a clean natural-language
// `user_facing_summary` — this view renders ONLY that, as a chat bubble.

import { useCallback, useEffect, useRef, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import { fmt } from "./_shared";
import {
    testCommand,
    confirmCommand,
    cancelCommand,
    executeCommand,
    sendSlotReply,
    getAimSessions,
    type AimParse,
    type AimSession,
    type ReadResult,
} from "./_lib";

/* ----------------------------------------------------------------- types */

// A turn is either what the person said, or what the assistant replied. The
// assistant turn keeps the raw parse so the lifecycle (confirm/PIN/execute) can
// act on it — but the BUBBLE only ever shows the natural-language summary.
type Turn =
    | { id: string; role: "user"; text: string }
    | {
          id: string;
          role: "ai";
          parse: AimParse;
          busy?: boolean;
          note?: string;
      };

let TURN_SEQ = 0;
const nextId = () => `t${Date.now()}-${++TURN_SEQ}`;

/* -------------------------------------------------- conversational verdicts */

// Does this reply need the person to APPROVE a write (confirm / PIN)? This is the
// ONLY time the chat shows action chips — every read just answers.
function pendingAction(p: AimParse): "confirm" | "pin" | null {
    const s = (p.status || "").toLowerCase();
    if (p.requires_pin || s === "needs_pin") return "pin";
    if (p.requires_confirmation || s === "needs_confirmation") return "confirm";
    return null;
}

// Is the assistant asking the person a follow-up question (slot-fill)? Then the
// next thing they type should be sent as the answer to that question, not as a
// brand-new command.
function isAsking(p: AimParse): boolean {
    return (p.status || "").toLowerCase() === "eliciting" && !!p.command_id;
}

// A write the person isn't allowed to run (or that's blocked) — shown as a plain,
// gentle sentence, never a red "REFUSED / Blocked" card.
function isRefused(p: AimParse): boolean {
    const s = (p.status || "").toLowerCase();
    return s === "blocked" || s === "denied" || !!p.block_reason;
}

// The natural sentence to show. Always prefer the backend's user_facing_summary;
// fall back to a friendly line so a bubble is never empty.
function bubbleText(p: AimParse, fallback?: string): string {
    const t = (p.user_facing_summary || "").trim();
    if (t) return t;
    if (p.block_reason) return p.block_reason;
    return fallback || "Okay.";
}

/* =============================================================== the tab */

export default function TryItTab({ seedQuery = "" }: { seedQuery?: string }) {
    const [turns, setTurns] = useState<Turn[]>([]);
    const [input, setInput] = useState(seedQuery);
    const [thinking, setThinking] = useState(false);
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

    // The last assistant turn that's still waiting for a typed answer (a slot
    // question). If present, the person's next message answers THAT, in-context.
    function openQuestion(): Extract<Turn, { role: "ai" }> | null {
        for (let i = turns.length - 1; i >= 0; i--) {
            const t = turns[i];
            if (t.role === "ai") return isAsking(t.parse) ? t : null;
            if (t.role === "user") return null;
        }
        return null;
    }

    async function send(text: string) {
        const utterance = text.trim();
        if (!utterance || thinking) return;
        setInput("");
        pushTurn({ id: nextId(), role: "user", text: utterance });
        setThinking(true);

        // If the assistant just asked something, answer it in-context (slot reply)
        // so a back-and-forth feels like a real conversation.
        const q = openQuestion();
        try {
            const parse = q?.parse.command_id
                ? await sendSlotReply(q.parse.command_id, utterance)
                : await testCommand(utterance, "dashboard");
            pushTurn({ id: nextId(), role: "ai", parse });
            if (pendingAction(parse) === "pin") {
                setPinFor({ id: parse.command_id || "", summary: bubbleText(parse, "this action") });
            }
        } catch (e) {
            const msg = e instanceof Error ? e.message : "Sorry, I couldn't process that. Try rephrasing?";
            pushTurn({ id: nextId(), role: "ai", parse: { user_facing_summary: msg } });
        } finally {
            setThinking(false);
            loadSessions();
        }
    }

    async function doConfirm(turn: Extract<Turn, { role: "ai" }>) {
        const id = turn.parse.command_id;
        if (!id) return;
        patchTurn(turn.id, { busy: true, note: undefined });
        try {
            const parse = await confirmCommand(id);
            const merged = { ...turn.parse, ...parse };
            patchTurn(turn.id, { parse: merged, busy: false });
            if (pendingAction(merged) === "pin") {
                setPinFor({ id, summary: bubbleText(merged, "this action") });
            } else {
                loadSessions();
            }
        } catch (e) {
            patchTurn(turn.id, { busy: false, note: e instanceof Error ? e.message : "Couldn't confirm that." });
        }
    }

    async function doExecute(turn: Extract<Turn, { role: "ai" }>) {
        const id = turn.parse.command_id;
        if (!id) return;
        patchTurn(turn.id, { busy: true, note: undefined });
        try {
            const parse = await executeCommand(id);
            const merged = { ...turn.parse, ...parse };
            patchTurn(turn.id, { parse: merged, busy: false });
            if (pendingAction(merged) === "pin") {
                setPinFor({ id, summary: bubbleText(merged, "this action") });
            } else {
                loadSessions();
            }
        } catch (e) {
            patchTurn(turn.id, { busy: false, note: e instanceof Error ? e.message : "Couldn't run that." });
        }
    }

    async function doCancel(turn: Extract<Turn, { role: "ai" }>) {
        const id = turn.parse.command_id;
        if (!id) return;
        patchTurn(turn.id, { busy: true, note: undefined });
        try {
            await cancelCommand(id);
        } catch {
            /* best-effort */
        }
        // Replace the pending action with a friendly acknowledgement.
        patchTurn(turn.id, {
            busy: false,
            parse: { ...turn.parse, requires_confirmation: false, requires_pin: false, status: "cancelled",
                     user_facing_summary: "No problem — I won't do that." },
        });
    }

    async function submitPin(pin: string) {
        const target = pinFor;
        if (!target) return;
        setPinFor(null);
        const turn = turns.find(
            (t) => t.role === "ai" && t.parse.command_id === target.id
        ) as Extract<Turn, { role: "ai" }> | undefined;
        if (turn) patchTurn(turn.id, { busy: true, note: undefined });
        try {
            const parse = await executeCommand(target.id, pin);
            if (turn) patchTurn(turn.id, { parse: { ...turn.parse, ...parse }, busy: false });
            loadSessions();
        } catch (e) {
            const msg = e instanceof Error ? e.message : "That PIN didn't match — nothing ran.";
            if (turn) patchTurn(turn.id, { busy: false, note: msg });
        }
    }

    const sessionRows = sessions?.kind === "ok" ? sessions.data.sessions : [];

    return (
        <div className="flex gap-4 max-lg:flex-col">
            {/* Left rail — recent conversations / calls (masked) */}
            <div className="w-72 shrink-0 max-lg:w-full">
                <Card
                    title="Recent"
                    headContent={
                        <span className="ml-auto inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                            masked
                        </span>
                    }
                >
                    <div className="px-3 pb-3 space-y-1.5 max-h-[30rem] overflow-y-auto scrollbar-none max-lg:max-h-56">
                        {sessionRows.length === 0 ? (
                            <div className="px-2 py-6 text-center text-caption text-t-tertiary">
                                Your chats and AI calls show up here.
                            </div>
                        ) : (
                            sessionRows.map((s) => (
                                <div
                                    key={s.session_id}
                                    className="lift p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset"
                                >
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="font-mono text-caption text-t-primary truncate">
                                            {s.caller_id || "chat"}
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

            {/* Right — the assistant chat (the hero) */}
            <div className="flex-1 min-w-0">
                <Card className="p-0 overflow-hidden" title="Assistant">
                    <div
                        ref={threadRef}
                        className="px-5 max-lg:px-3 h-[32rem] overflow-y-auto scrollbar-none"
                    >
                        {turns.length === 0 && !thinking ? (
                            <EmptyThread onPick={(q) => send(q)} />
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
                                placeholder="Ask me anything about your business — Enter to send"
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

const SUGGESTIONS = [
    "How many leads do I have?",
    "What happened today?",
    "Show me my hot leads",
    "How many calls did we make this week?",
];

function EmptyThread({ onPick }: { onPick: (q: string) => void }) {
    return (
        <div className="py-10 flex flex-col items-center text-center">
            <span className="grid place-items-center size-14 rounded-2xl bg-primary-01/10 ring-1 ring-primary-01/20 fill-primary-01">
                <Icon name="chat" className="size-7 fill-inherit" />
            </span>
            <div className="text-sub-title-1 text-t-primary mt-4">Ask your AI Manager anything</div>
            <p className="text-body-2 text-t-secondary mt-1.5 max-w-md">
                Talk to it like a smart office manager. It reads your live data and answers in plain words —
                and only asks you to confirm when something actually needs doing.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-2 max-w-lg">
                {SUGGESTIONS.map((q) => (
                    <button
                        key={q}
                        onClick={() => onPick(q)}
                        className="h-9 px-4 rounded-full border border-s-subtle text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary"
                    >
                        {q}
                    </button>
                ))}
            </div>
        </div>
    );
}

/* ------------------------------------------------------------- chat turns */

function UserBubble({ text }: { text: string }) {
    return (
        <div className="flex justify-end">
            <div className="max-w-[80%] rounded-2xl rounded-tr-md px-4 py-2.5 bg-primary-01 text-t-light text-body-2 shadow-sm whitespace-pre-wrap">
                {text}
            </div>
        </div>
    );
}

function ThinkingBubble() {
    return (
        <div className="flex justify-start items-end gap-2">
            <AiAvatar />
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
            </div>
        </div>
    );
}

function AiAvatar() {
    return (
        <span className="grid place-items-center size-8 shrink-0 rounded-full bg-primary-01/12 ring-1 ring-primary-01/20 fill-primary-01">
            <Icon name="magic-pencil" className="size-4 fill-inherit" />
        </span>
    );
}

// The assistant message: a plain natural-language bubble. The ONLY structured
// element is a subtle action row — shown solely when a real write needs the
// person's approval (confirm / PIN). Reads just answer.
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
    const action = pendingAction(p);
    const refused = isRefused(p) && !action;

    return (
        <div className="flex justify-start items-end gap-2">
            <AiAvatar />
            <div className="max-w-[82%] min-w-0">
                <div className="rounded-2xl rounded-tl-md px-4 py-2.5 bg-b-surface2 ring-1 ring-s-subtle ring-inset text-body-2 text-t-primary whitespace-pre-wrap">
                    {bubbleText(p, refused ? "I can't do that one." : undefined)}
                </div>

                {/* A real write that needs approval — the one place we show controls. */}
                {action && (
                    <div className="flex items-center gap-2 mt-2">
                        {action === "pin" ? (
                            <Button isBlack icon="lock" className="h-9" disabled={turn.busy} onClick={onExecute}>
                                Enter PIN &amp; do it
                            </Button>
                        ) : (
                            <Button isBlack icon="check" className="h-9" disabled={turn.busy} onClick={onConfirm}>
                                {turn.busy ? "Working…" : "Yes, do it"}
                            </Button>
                        )}
                        <Button isStroke className="h-9" disabled={turn.busy} onClick={onCancel}>
                            No
                        </Button>
                    </div>
                )}

                {turn.note && <div className="text-caption text-primary-03 mt-1.5">{turn.note}</div>}
            </div>
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
                        <div className="text-sub-title-1 text-t-primary">Quick PIN check</div>
                        <div className="text-caption text-t-tertiary">Just to be safe before I do this.</div>
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
                        Your PIN is checked on the server and never stored. A wrong PIN simply cancels — nothing runs.
                    </p>
                    <div className="flex items-center gap-2">
                        <Button isBlack type="submit" className="flex-1 justify-center" disabled={!pin.trim()}>
                            Verify &amp; do it
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
