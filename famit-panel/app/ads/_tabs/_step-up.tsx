"use client";

// ============================================================================
// _step-up — the reusable PIN step-up challenge for SPEND-class ad actions.
//
// Launching a campaign moves real budget, so the backend fail-closes any
// /ads/campaigns/{id}/approve (and guardrails-save / leads-import) that arrives
// without a valid `X-Step-Up` token. This modal obtains that token the SAME way
// the live provider-secret reveal does (app/integrations/_reveal-pin.tsx →
// lib/integrations.ts:verifyPin → POST /firewall/verify-pin, Form-encoded
// pin+scope), differing only in that it asks for the `spend` scope and HANDS THE
// MINTED TOKEN BACK to the caller (via onToken) so the caller can replay it.
//
// SECURITY: the PIN is local component state only; it is wiped on close/unmount/
// success and never logged. The minted token is single-use + short-TTL server-
// side — the caller spends it immediately on one approve call.
//
// Token-pure Core_2 (zero raw hex — only globals.css tokens). Reuses Modal +
// Button + Icon. Pure presentational + the one mintStepUp call.
// ============================================================================

import { useCallback, useEffect, useState } from "react";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import { mintStepUp } from "../_lib";

export type StepUpModalProps = {
    open: boolean;
    onClose: () => void;
    // Called with a freshly-minted, short-TTL step-up token once the PIN verifies.
    // The caller replays it as `X-Step-Up` on its spend action, then this closes.
    onToken: (token: string) => void | Promise<void>;
    // The firewall scope to mint. Spend-class ad actions use "spend" (the default).
    scope?: string;
    title?: string;
    description?: string;
    // The label echoed on the confirm button (keeps the verb consistent with the
    // action it unlocks, e.g. "Approve & launch").
    actionLabel?: string;
};

export default function StepUpModal({
    open,
    onClose,
    onToken,
    scope = "spend",
    title = "Confirm with your PIN",
    description = "Launching spends real budget. Enter your security PIN to authorise it — this is required once per launch.",
    actionLabel = "Confirm & launch",
}: StepUpModalProps) {
    const [pin, setPin] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState("");

    // Wipe the PIN whenever the modal closes — it never outlives a session.
    useEffect(() => {
        if (!open) {
            setPin("");
            setErr("");
            setBusy(false);
        }
    }, [open]);

    const submit = useCallback(async () => {
        if (busy || pin.length < 4) return;
        setBusy(true);
        setErr("");
        try {
            const token = await mintStepUp(pin, scope);
            setPin("");
            await onToken(token);
            onClose();
        } catch (e) {
            setErr(e instanceof Error ? e.message : "Couldn't verify that PIN. Try again.");
        } finally {
            setBusy(false);
        }
    }, [busy, pin, scope, onToken, onClose]);

    return (
        <Modal open={open} onClose={onClose} classWrapper="!max-w-100">
            <div className="space-y-5">
                {/* lock badge — the one quiet signature; everything else stays calm */}
                <div className="flex flex-col items-center text-center">
                    <span className="grid place-items-center size-14 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                        <Icon name="lock" className="size-6 fill-inherit" />
                    </span>
                    <h2 className="mt-4 text-h6 text-t-primary">{title}</h2>
                    <p className="mt-1.5 text-body-2 text-t-secondary max-w-72">{description}</p>
                </div>

                <div>
                    <label htmlFor="stepup-pin" className="sr-only">
                        Security PIN
                    </label>
                    <input
                        id="stepup-pin"
                        type="password"
                        inputMode="numeric"
                        autoComplete="off"
                        autoFocus
                        value={pin}
                        onChange={(e) => {
                            setErr("");
                            setPin(e.target.value.replace(/[^0-9]/g, "").slice(0, 8));
                        }}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") submit();
                            if (e.key === "Escape") onClose();
                        }}
                        placeholder="••••••"
                        className="w-full h-14 px-4 text-center rounded-2xl bg-b-surface2 border border-s-subtle text-h6 text-t-primary tabular-nums tracking-[0.4em] focus:outline-none focus:border-s-highlight transition-colors"
                    />
                    {err ? (
                        <p className="mt-2.5 flex items-start gap-1.5 text-caption text-primary-03">
                            <Icon name="info" className="size-3.5 fill-primary-03 shrink-0 mt-px" />
                            {err}
                        </p>
                    ) : (
                        <p className="mt-2.5 text-caption text-t-tertiary text-center">
                            Your PIN is verified securely and never stored in this browser.
                        </p>
                    )}
                </div>

                <div className="flex items-center gap-3">
                    <Button isStroke className="flex-1 justify-center" type="button" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button
                        isBlack
                        className="flex-1 justify-center"
                        icon="lock"
                        type="button"
                        onClick={submit}
                        disabled={busy || pin.length < 4}
                    >
                        {busy ? "Verifying…" : actionLabel}
                    </Button>
                </div>
            </div>
        </Modal>
    );
}
