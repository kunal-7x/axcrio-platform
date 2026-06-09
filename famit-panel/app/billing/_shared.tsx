"use client";

// Shared helpers for the Billing sub-pages. Kept tiny + presentational so each
// page stays focused on its own endpoint.

import type { VendorStatus } from "@/lib/api";
import Badge, { type BadgeVariant } from "@/components/Badge";
import Icon from "@/components/Icon";

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

// Vendor-config status, now on the shared token-based Badge so it matches the
// pills used across Dashboard / Calls / Leads. Same props as before.
export function StatusBadge({ status, stale }: { status: VendorStatus; stale?: boolean }) {
    const map: Record<VendorStatus, { label: string; variant: BadgeVariant; dot?: boolean }> = {
        configured: stale
            ? { label: "Live · stale", variant: "warning", dot: true }
            : { label: "Live", variant: "success", dot: true },
        not_configured: { label: "Not configured", variant: "neutral" },
        error: { label: "Error", variant: "danger" },
    };
    const s = map[status] ?? map.error;
    return (
        <Badge variant={s.variant} dot={s.dot}>
            {s.label}
        </Badge>
    );
}

export function ErrorBanner({ msg }: { msg: string }) {
    if (!msg) return null;
    return (
        <div className="mb-4 flex items-center gap-2 p-3.5 rounded-2xl bg-primary-03/8 border border-primary-03/20 text-primary-03 text-body-2">
            <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
            {msg}
        </div>
    );
}

export const selectCls =
    "h-10 px-3 border border-s-stroke2 rounded-2xl text-body-2 text-t-primary outline-none bg-transparent transition-colors hover:border-s-highlight focus:border-s-focus";

export const btnCls =
    "inline-flex items-center justify-center gap-2 h-10 px-4 border border-s-stroke2 rounded-2xl text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary disabled:opacity-50";
