"use client";

// Shared helpers for the Billing sub-pages. Kept tiny + presentational so each
// page stays focused on its own endpoint.

import type { VendorStatus } from "@/lib/api";

export function money(n: number | null | undefined, currency: string): string {
    if (n == null) return "—";
    return `${currency || ""} ${n.toFixed(2)}`.trim();
}

export function fmt(d: string | undefined): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

export function StatusBadge({ status, stale }: { status: VendorStatus; stale?: boolean }) {
    const map: Record<VendorStatus, { label: string; cls: string }> = {
        configured: {
            label: stale ? "Live · stale" : "Live",
            cls: stale
                ? "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400"
                : "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400",
        },
        not_configured: {
            label: "Not configured — add keys on server",
            cls: "bg-b-surface1 text-t-tertiary border border-s-stroke2",
        },
        error: {
            label: "Error",
            cls: "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400",
        },
    };
    const s = map[status] ?? map.error;
    return (
        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-caption font-medium ${s.cls}`}>
            {s.label}
        </span>
    );
}

export function ErrorBanner({ msg }: { msg: string }) {
    if (!msg) return null;
    return (
        <div className="mb-4 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">
            {msg}
        </div>
    );
}

export const selectCls =
    "h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent hover:border-s-highlight focus:border-s-highlight";

export const btnCls =
    "h-10 px-4 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary hover:border-s-highlight transition-colors disabled:opacity-50";
