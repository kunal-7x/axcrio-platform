"use client";

// ============================================================================
// Client-side error capture -> System Logs.
//
// Why this exists: the backend "System Logs" store only ever saw backend + voice-agent
// events. A real error in the panel (a render crash, a thrown promise, a failed fetch) had
// NO path to the operator — which is exactly the "I hit an error but nothing showed in System
// Logs" gap. This module captures three classes of client error and POSTs them to
// /admin/logs/client (source forced to "frontend" server-side):
//   • React render/lifecycle errors  — ClientErrorBoundary
//   • synchronous JS errors           — window 'error'
//   • async promise rejections        — window 'unhandledrejection'
//
// DESIGN LAWS (mirror the backend logging_service): IMPORT-GUARDED, BEST-EFFORT (never throws
// into the app), and DORMANT-SAFE (no token -> no-op, since the ingest route needs a tenant).
// Reporting is de-duped + lightly throttled so a render-loop can't flood the store or the network.
// ============================================================================

import React from "react";
import { BASE, authHeaders } from "./api";

export type ClientErrorKind = "error" | "unhandledrejection" | "render" | "fetch";

export type ClientErrorPayload = {
    message: string;
    stack?: string;
    url?: string;
    kind?: ClientErrorKind;
    error_type?: string;
    level?: "warning" | "error" | "critical";
    context?: Record<string, unknown>;
};

// collapse a burst of the SAME error (key = kind|first-120-chars) within the session, and cap
// the dedup set so it can't grow unbounded. A JS Set preserves insertion order, so we evict the
// OLDEST keys past the cap (LRU-ish) rather than wiping the whole set — wiping would reset dedup
// state and let a long-lived error re-report after the 101st distinct error.
const _recent = new Set<string>();
const _RECENT_CAP = 200;

/** Best-effort: POST a client error to System Logs. NEVER throws. No-op when unauthenticated. */
export function reportClientError(p: ClientErrorPayload): void {
    try {
        if (typeof window === "undefined") return;
        // the ingest route requires a tenant; on the login screen there's no token -> skip silently.
        if (!localStorage.getItem("famit_token")) return;

        const key = (p.kind || "error") + "|" + (p.message || "").slice(0, 120);
        if (_recent.has(key)) return; // already reported this exact error this session
        _recent.add(key);
        while (_recent.size > _RECENT_CAP) {
            const oldest = _recent.values().next().value; // insertion order -> oldest first
            if (oldest === undefined) break;
            _recent.delete(oldest);
        }

        const body = JSON.stringify({
            message: (p.message || "client error").slice(0, 1000),
            stack: (p.stack || "").slice(0, 1500),
            url: p.url || window.location.href,
            kind: p.kind || "error",
            error_type: p.error_type || "ClientError",
            level: p.level || "error",
            context: p.context || {},
        });

        // keepalive => a report fired during navigation/unmount still flushes.
        fetch(`${BASE}/admin/logs/client`, {
            method: "POST",
            headers: { ...authHeaders(), "Content-Type": "application/json" },
            body,
            keepalive: true,
        }).catch(() => { /* network failure on a log report is itself swallowed */ });
    } catch {
        /* error reporting must never break the app */
    }
}

let _installed = false;

/** Attach the global window listeners ONCE (idempotent). Safe to call on every mount. */
export function installGlobalErrorCapture(): void {
    if (typeof window === "undefined" || _installed) return;
    _installed = true;
    window.addEventListener("error", (e: ErrorEvent) => {
        reportClientError({
            message: e.message || String((e.error && e.error.message) || "window error"),
            stack: e.error?.stack,
            error_type: e.error?.name || "Error",
            kind: "error",
            context: { filename: e.filename, lineno: e.lineno, colno: e.colno },
        });
    });
    window.addEventListener("unhandledrejection", (e: PromiseRejectionEvent) => {
        const reason = e.reason as { message?: string; stack?: string; name?: string } | undefined;
        reportClientError({
            message: reason?.message || String(e.reason ?? "unhandled rejection"),
            stack: reason?.stack,
            error_type: reason?.name || "UnhandledRejection",
            kind: "unhandledrejection",
        });
    });
}

type EBProps = { children: React.ReactNode };
type EBState = { hasError: boolean };

/** Catches render/lifecycle errors anywhere below it, reports them, and shows an on-brand
 *  fallback (card chrome from DESIGN_LANGUAGE.md: rounded-3xl + hairline ring + b-surface2). */
export class ClientErrorBoundary extends React.Component<EBProps, EBState> {
    constructor(props: EBProps) {
        super(props);
        this.state = { hasError: false };
    }
    static getDerivedStateFromError(): EBState {
        return { hasError: true };
    }
    componentDidCatch(error: Error, info: React.ErrorInfo) {
        reportClientError({
            message: error?.message || "render error",
            stack: error?.stack || info?.componentStack || "",
            error_type: error?.name || "RenderError",
            kind: "render",
            level: "error",
        });
    }
    private reset = () => {
        this.setState({ hasError: false });
        if (typeof window !== "undefined") window.location.reload();
    };
    render() {
        if (this.state.hasError) {
            return (
                <div className="min-h-[60vh] flex items-center justify-center p-6">
                    <div className="relative w-full max-w-md rounded-3xl bg-b-surface2 p-6 text-center ring-1 ring-inset ring-s-subtle">
                        <div className="text-h6 text-t-primary mb-1">Something went wrong</div>
                        <div className="text-body-2 text-t-secondary mb-4">
                            This screen hit an unexpected error. It has been logged to System Logs for the team.
                        </div>
                        <button
                            type="button"
                            onClick={this.reset}
                            className="inline-flex h-10 items-center justify-center rounded-full bg-primary-01 px-5 text-button text-white transition active:scale-[0.98]"
                        >
                            Reload page
                        </button>
                    </div>
                </div>
            );
        }
        return this.props.children;
    }
}
