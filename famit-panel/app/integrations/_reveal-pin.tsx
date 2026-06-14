"use client";

// ============================================================================
// _reveal-pin — the inline PIN-pad + countdown-ring REVEAL for a vendor's OWN
// (scope='integration') provider credential (design crazy-ui-security §B/§E).
//
// SECURITY MODEL (non-negotiable):
//   • PLAINTEXT NEVER ENTERS REACT STATE. It lives in a useRef, is rendered into
//     the DOM only while revealed, and is WIPED on timeout / unmount / close.
//   • The flow is 3 steps: verify-pin (PIN pad) → reveal-init (aud-bound, single-
//     use token) → reveal (X-Step-Up → plaintext, once). Replay → 403.
//   • Copy-without-revealing: the user can copy the key straight to the clipboard
//     WITHOUT ever seeing it on screen (and the clipboard read still uses the ref).
//   • A 30s countdown ring auto-masks. This is defence-in-depth — the server reveal
//     token is single-use + 60s TTL; the FE never holds a revealable token.
//   • ai_provider (platform) credentials never render this — the caller hides it.
//
// Glyphs: lock (reveal) exists; eye/copy/key DO NOT — so this uses the `lock`
// glyph + TEXT buttons (Reveal / Copy / Hide), exactly per the glyph ground-truth.
// ============================================================================

import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { verifyPin, revealFlow, humanizeError, IntegrationError } from "@/lib/integrations";

const AUTO_MASK_S = 30;

type Phase = "idle" | "pin" | "revealed";

export default function RevealPin({
    providerId,
    onToast,
}: {
    providerId: string;
    onToast: (msg: string, type?: "success" | "error") => void;
}) {
    const [phase, setPhase] = useState<Phase>("idle");
    const [pin, setPin] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");
    const [remaining, setRemaining] = useState(AUTO_MASK_S);

    // plaintext lives ONLY here — never in useState, never serialized.
    const secretRef = useRef<string>("");
    const tick = useRef<ReturnType<typeof setInterval> | null>(null);

    const wipe = useCallback(() => {
        secretRef.current = "";
        if (tick.current) {
            clearInterval(tick.current);
            tick.current = null;
        }
    }, []);

    // wipe on unmount — the plaintext never outlives the component.
    useEffect(() => () => wipe(), [wipe]);

    const close = useCallback(() => {
        wipe();
        setPhase("idle");
        setPin("");
        setErr("");
        setRemaining(AUTO_MASK_S);
    }, [wipe]);

    const startCountdown = useCallback(() => {
        setRemaining(AUTO_MASK_S);
        if (tick.current) clearInterval(tick.current);
        tick.current = setInterval(() => {
            setRemaining((r) => {
                if (r <= 1) {
                    close(); // auto-mask + wipe
                    return AUTO_MASK_S;
                }
                return r - 1;
            });
        }, 1000);
    }, [close]);

    const doReveal = useCallback(async () => {
        if (busy) return;
        setBusy(true);
        setErr("");
        try {
            const ok = await verifyPin(pin, "provider.reveal");
            if (!ok) {
                setErr("That PIN didn't match. Try again.");
                setBusy(false);
                return;
            }
            const plaintext = await revealFlow(providerId);
            secretRef.current = plaintext;
            setPin("");
            setPhase("revealed");
            startCountdown();
        } catch (e) {
            const msg =
                e instanceof IntegrationError ? e.message : humanizeError(String((e as Error)?.message || ""), 0);
            setErr(msg);
        } finally {
            setBusy(false);
        }
    }, [busy, pin, providerId, startCountdown]);

    const copy = useCallback(async () => {
        try {
            await navigator.clipboard.writeText(secretRef.current);
            onToast("Key copied to clipboard.");
        } catch {
            onToast("Couldn't copy — your browser blocked clipboard access.", "error");
        }
    }, [onToast]);

    // ---- idle: a plain "Reveal" text button -------------------------------
    if (phase === "idle") {
        return (
            <button
                onClick={() => setPhase("pin")}
                className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-caption text-t-secondary border border-s-subtle hover:border-s-highlight hover:text-t-primary transition-all"
            >
                <Icon name="lock" className="size-3.5 fill-inherit" />
                Reveal
            </button>
        );
    }

    // ---- pin pad ----------------------------------------------------------
    if (phase === "pin") {
        return (
            <div className="inline-flex items-center gap-2 flex-wrap">
                <div className="inline-flex items-center gap-1.5 px-1">
                    <Icon name="lock" className="size-3.5 fill-t-secondary" />
                    <span className="text-caption text-t-secondary">PIN</span>
                </div>
                <input
                    type="password"
                    inputMode="numeric"
                    autoComplete="off"
                    autoFocus
                    value={pin}
                    onChange={(e) => setPin(e.target.value.replace(/[^0-9]/g, ""))}
                    onKeyDown={(e) => {
                        if (e.key === "Enter") doReveal();
                        if (e.key === "Escape") close();
                    }}
                    placeholder="••••••"
                    className="w-24 h-8 px-3 rounded-full bg-b-surface2 border border-s-subtle text-body-2 text-t-primary tabular-nums tracking-widest focus:outline-none focus:border-s-highlight"
                />
                <button
                    onClick={doReveal}
                    disabled={busy || pin.length < 4}
                    className="inline-flex items-center h-8 px-3 rounded-full text-caption text-t-primary border border-s-highlight hover:bg-b-surface2 transition-all disabled:opacity-50"
                >
                    {busy ? "…" : "Unlock"}
                </button>
                <button
                    onClick={close}
                    className="inline-flex items-center h-8 px-2.5 rounded-full text-caption text-t-secondary hover:text-t-primary transition-colors"
                >
                    Cancel
                </button>
                {err && <span className="text-caption text-primary-03 max-w-[16rem]">{err}</span>}
            </div>
        );
    }

    // ---- revealed: plaintext (from ref) + countdown ring + copy/hide ------
    const frac = remaining / AUTO_MASK_S;
    return (
        <div className="inline-flex items-center gap-2.5 flex-wrap">
            <span className="font-mono text-body-2 text-t-primary tabular-nums break-all max-w-[20rem] px-2.5 py-1 rounded-xl bg-b-surface2 border border-s-subtle">
                {secretRef.current}
            </span>
            {/* countdown ring (SVG, token-coloured — no raw hex) */}
            <span
                className="relative inline-flex items-center justify-center size-7 shrink-0"
                title={`Auto-hides in ${remaining}s`}
                aria-label={`Auto-hides in ${remaining} seconds`}
            >
                <svg viewBox="0 0 36 36" className="size-7 -rotate-90">
                    <circle cx="18" cy="18" r="15" fill="none" strokeWidth="3" className="stroke-s-subtle" />
                    <circle
                        cx="18"
                        cy="18"
                        r="15"
                        fill="none"
                        strokeWidth="3"
                        strokeLinecap="round"
                        className="stroke-t-secondary transition-[stroke-dashoffset] duration-1000 ease-linear"
                        strokeDasharray={2 * Math.PI * 15}
                        strokeDashoffset={2 * Math.PI * 15 * (1 - frac)}
                    />
                </svg>
                <span className="absolute text-[0.6rem] text-t-secondary tabular-nums">{remaining}</span>
            </span>
            <button
                onClick={copy}
                className="inline-flex items-center h-8 px-3 rounded-full text-caption text-t-secondary border border-s-subtle hover:border-s-highlight hover:text-t-primary transition-all"
            >
                Copy
            </button>
            <button
                onClick={close}
                className="inline-flex items-center h-8 px-3 rounded-full text-caption text-t-secondary hover:text-t-primary transition-colors"
            >
                Hide
            </button>
        </div>
    );
}
