"use client";

// LaunchPreflight — an INLINE, premium pre-launch readiness panel that renders right below the
// Launch summary rail (not a popup). On Launch we run REAL checks before any call fires: the
// operator's network round-trip, the AI providers the campaign rides (LLM/STT/TTS TCP-RTT), the
// voice infra (LiveKit), and this campaign's recent call latency. All fast -> flashes "All systems
// go" and launches automatically; latency high (>~1.5-2s) or something down -> warns inline with a
// "Start anyway" / "Cancel" choice. Every signal is real (GET /campaigns/{cid}/preflight).
import { useEffect, useState } from "react";
import { motion, AnimatePresence, useMotionValue, animate } from "framer-motion";
import { getPreflight, type PreflightResult } from "@/lib/api";

type Status = "green" | "yellow" | "red";
type Phase = "pending" | "running" | "done";
type Verdict = "ok" | "slow" | "down";
type Row = {
    id: string;
    label: string;
    phase: Phase;
    status?: Status;
    latency_ms?: number | null;
    detail?: string;
};

const INITIAL: Row[] = [
    { id: "network", label: "Your network", phase: "pending" },
    { id: "providers", label: "AI providers", phase: "pending" },
    { id: "voice_infra", label: "Voice infrastructure", phase: "pending" },
    { id: "recent", label: "Recent call latency", phase: "pending" },
];

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const patch = (rows: Row[], id: string, next: Partial<Row>) =>
    rows.map((r) => (r.id === id ? { ...r, ...next } : r));

const DOT: Record<Status, string> = {
    green: "bg-emerald-400",
    yellow: "bg-amber-400",
    red: "bg-rose-400",
};
const BADGE: Record<Status, string> = {
    green: "text-emerald-400 bg-emerald-400/10",
    yellow: "text-amber-400 bg-amber-400/10",
    red: "text-rose-400 bg-rose-400/10",
};

async function measureNetworkRtt(): Promise<number | null> {
    const samples: number[] = [];
    for (let i = 0; i < 3; i++) {
        const t0 = performance.now();
        try {
            await fetch(`/api/health?deep=0&_=${i}_${Math.floor(t0)}`, { cache: "no-store" });
        } catch {
            return null;
        }
        samples.push(performance.now() - t0);
    }
    samples.sort((a, b) => a - b);
    return Math.round(samples[Math.floor(samples.length / 2)]);
}

function StatusOrb({ phase, status }: { phase: Phase; status?: Status }) {
    if (phase === "pending")
        return <span className="h-2 w-2 rounded-full bg-t-tertiary/40" />;
    if (phase === "running")
        return (
            <motion.span
                className="h-3.5 w-3.5 rounded-full border-2 border-t-tertiary/30 border-t-t-primary/70"
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 0.7, ease: "linear" }}
            />
        );
    const c = DOT[status ?? "green"];
    return (
        <span className="relative flex h-3 w-3 items-center justify-center">
            <motion.span
                className={`absolute h-3 w-3 rounded-full ${c}`}
                animate={{ scale: [1, 2.2], opacity: [0.4, 0] }}
                transition={{ repeat: Infinity, duration: 1.7, ease: "easeOut" }}
            />
            <span className={`h-2 w-2 rounded-full ${c}`} />
        </span>
    );
}

function CountUp({ value }: { value: number }) {
    const mv = useMotionValue(0);
    const [n, setN] = useState(0);
    useEffect(() => {
        const controls = animate(mv, value, {
            duration: 0.7,
            ease: "easeOut",
            onUpdate: (v) => setN(Math.round(v)),
        });
        return () => controls.stop();
    }, [value, mv]);
    return <>{n}</>;
}

export default function LaunchPreflight({
    campaignId,
    campaignName,
    onProceed,
    onClose,
}: {
    campaignId: string;
    campaignName?: string;
    onProceed: () => void;
    onClose: () => void;
}) {
    const [rows, setRows] = useState<Row[]>(INITIAL);
    const [phase, setPhase] = useState<"checking" | "done">("checking");
    const [verdict, setVerdict] = useState<Verdict | null>(null);

    useEffect(() => {
        let cancelled = false;
        setRows(INITIAL.map((r) => ({ ...r })));
        setVerdict(null);
        setPhase("checking");

        (async () => {
            setRows((rs) => patch(rs, "network", { phase: "running" }));
            const rtt = await measureNetworkRtt();
            if (cancelled) return;
            const netStatus: Status =
                rtt == null ? "red" : rtt < 400 ? "green" : rtt < 1200 ? "yellow" : "red";
            const conn =
                typeof navigator !== "undefined"
                    ? (navigator as unknown as { connection?: { effectiveType?: string } }).connection
                          ?.effectiveType
                    : undefined;
            setRows((rs) =>
                patch(rs, "network", {
                    phase: "done",
                    status: netStatus,
                    latency_ms: rtt,
                    detail:
                        rtt == null
                            ? "offline / server unreachable"
                            : `${rtt}ms round-trip${conn ? ` · ${conn}` : ""}`,
                })
            );

            setRows((rs) => rs.map((r) => (r.id !== "network" ? { ...r, phase: "running" } : r)));
            let backend: PreflightResult | null = null;
            try {
                backend = await getPreflight(campaignId);
            } catch {
                backend = null;
            }
            if (cancelled) return;
            if (backend) {
                for (const c of backend.checks) {
                    await sleep(300);
                    if (cancelled) return;
                    setRows((rs) =>
                        patch(rs, c.id, {
                            phase: "done",
                            status: c.status,
                            latency_ms: c.latency_ms,
                            detail: c.detail,
                        })
                    );
                }
            } else {
                for (const id of ["providers", "voice_infra", "recent"]) {
                    setRows((rs) => patch(rs, id, { phase: "done", status: "red", detail: "check unavailable" }));
                }
            }
            if (cancelled) return;

            const v: Verdict =
                backend?.verdict === "down" || rtt == null
                    ? "down"
                    : backend?.verdict === "slow" || netStatus !== "green"
                    ? "slow"
                    : "ok";
            setVerdict(v);
            setPhase("done");
            if (v === "ok") {
                await sleep(1100);
                if (!cancelled) onProceed();
            }
        })();

        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [campaignId]);

    const doneCount = rows.filter((r) => r.phase === "done").length;
    const pct = Math.round((doneCount / rows.length) * 100);
    const isWarn = phase === "done" && (verdict === "slow" || verdict === "down");
    const accent = isWarn ? "bg-amber-400" : verdict === "ok" ? "bg-emerald-400" : "bg-indigo-400";

    return (
        <motion.div
            className="surface relative overflow-hidden p-5 max-lg:p-4"
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ type: "spring", stiffness: 320, damping: 26 }}
        >
            {/* soft top glow */}
            <motion.div
                className="pointer-events-none absolute -top-16 left-1/2 h-32 w-[160%] -translate-x-1/2 rounded-full blur-3xl"
                style={{
                    background: isWarn
                        ? "radial-gradient(closest-side, rgba(251,191,36,0.35), transparent)"
                        : verdict === "ok"
                        ? "radial-gradient(closest-side, rgba(52,211,153,0.32), transparent)"
                        : "radial-gradient(closest-side, rgba(99,102,241,0.4), transparent)",
                }}
                animate={{ opacity: [0.25, 0.45, 0.25] }}
                transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
            />

            {/* header */}
            <div className="relative flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="eyebrow mb-1">Pre-launch check</div>
                    <div className="text-body-1 font-semibold text-t-primary leading-tight">
                        {phase === "checking"
                            ? "Checking readiness…"
                            : verdict === "ok"
                            ? "All systems go"
                            : verdict === "down"
                            ? "Some systems are down"
                            : "Networks look slow"}
                    </div>
                    {campaignName ? (
                        <div className="mt-0.5 truncate text-caption text-t-tertiary">{campaignName}</div>
                    ) : null}
                </div>
                {phase === "done" ? (
                    <button
                        onClick={onClose}
                        className="-mr-1 -mt-1 rounded-full p-1.5 text-t-tertiary transition-colors hover:bg-b-surface2 hover:text-t-primary"
                        aria-label="Close"
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M18 6 6 18M6 6l12 12" strokeLinecap="round" />
                        </svg>
                    </button>
                ) : null}
            </div>

            {/* progress */}
            <div className="relative mt-3 h-[3px] w-full overflow-hidden rounded-full bg-b-surface2">
                <motion.div
                    className={`h-full rounded-full ${accent}`}
                    animate={{ width: `${pct}%` }}
                    transition={{ ease: "easeOut", duration: 0.5 }}
                />
            </div>

            {/* rows */}
            <div className="relative mt-3 space-y-0.5">
                {rows.map((r, i) => (
                    <motion.div
                        key={r.id}
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className={`flex items-center gap-3 rounded-xl px-2 py-2 transition-colors ${
                            r.phase === "done" ? "bg-b-surface2/50" : ""
                        }`}
                    >
                        <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                            <StatusOrb phase={r.phase} status={r.status} />
                        </span>
                        <div className="min-w-0 flex-1">
                            <div className="text-button text-t-primary leading-tight">{r.label}</div>
                            <AnimatePresence mode="wait">
                                {r.phase === "done" && r.detail ? (
                                    <motion.div
                                        key="detail"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="mt-0.5 text-caption leading-tight text-t-tertiary line-clamp-2"
                                    >
                                        {r.detail}
                                    </motion.div>
                                ) : (
                                    <div className="mt-0.5 text-caption leading-tight text-t-tertiary/60">
                                        {r.phase === "running" ? "checking…" : "queued"}
                                    </div>
                                )}
                            </AnimatePresence>
                        </div>
                        {r.phase === "done" && r.latency_ms != null ? (
                            <div className={`shrink-0 rounded-md px-1.5 py-1 text-caption font-semibold tabular-nums ${BADGE[r.status ?? "green"]}`}>
                                <CountUp value={r.latency_ms} />
                                ms
                            </div>
                        ) : null}
                    </motion.div>
                ))}
            </div>

            {/* footer */}
            <div className="relative mt-4">
                {phase === "checking" ? (
                    <div className="flex items-center justify-center gap-2 text-caption text-t-tertiary">
                        <motion.span
                            className="h-1.5 w-1.5 rounded-full bg-indigo-400"
                            animate={{ opacity: [0.3, 1, 0.3] }}
                            transition={{ repeat: Infinity, duration: 1.1 }}
                        />
                        Running real network &amp; provider checks
                    </div>
                ) : verdict === "ok" ? (
                    <motion.div
                        className="flex items-center justify-center gap-2 text-button font-medium text-emerald-400"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                    >
                        <motion.svg
                            width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                            initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 420, damping: 16 }}
                        >
                            <path d="M20 6 9 17l-5-5" />
                        </motion.svg>
                        Launching campaign…
                    </motion.div>
                ) : (
                    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                        <div
                            className={`mb-3 rounded-xl border px-3 py-2.5 text-caption leading-snug ${
                                verdict === "down"
                                    ? "border-rose-400/25 bg-rose-400/5 text-rose-300"
                                    : "border-amber-400/25 bg-amber-400/5 text-amber-300"
                            }`}
                        >
                            {verdict === "down"
                                ? "A provider or the voice infrastructure is unreachable — calls may fail or break up. Launching now isn't recommended."
                                : "Latency is high right now — calls may lag or break up. Better to wait for a stronger connection, but you can start anyway."}
                        </div>
                        <div className="flex gap-2.5">
                            <button
                                onClick={onClose}
                                className="h-10 flex-1 rounded-2xl border border-s-stroke2 text-button text-t-secondary transition-colors hover:text-t-primary hover:border-s-highlight"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={onProceed}
                                className={`h-10 flex-1 rounded-2xl text-button font-semibold text-black transition-transform active:scale-[0.98] ${
                                    verdict === "down" ? "bg-rose-300 hover:bg-rose-200" : "bg-amber-300 hover:bg-amber-200"
                                }`}
                            >
                                Start anyway
                            </button>
                        </div>
                    </motion.div>
                )}
            </div>
        </motion.div>
    );
}
