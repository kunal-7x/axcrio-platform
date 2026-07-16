"use client";

// Super-Admin · cross-tenant Ad-ROI client (W7.9).
//
// WHY local (not lib/api.ts, not app/ads/_lib.ts): this is the ONE cross-tenant
// god-view read in the whole ad-engine surface — it reads aggregate ad spend/ROI
// for EVERY vendor at once, which is a super-admin-only path. The vendor-scoped
// app/ads/_lib.ts client is `X-Auth`-tenant-scoped and BYTE-STABLE; we must not
// couple this cross-tenant read into it. So the Vendors god-view owns its own
// thin client here, mirroring lib/api.ts auth EXACTLY (BASE = NEXT_PUBLIC_API_BASE
// || "/api", `X-Auth` from localStorage `famit_token`, 401 -> /login) and the
// ads `_lib.ts` DORMANCY idiom (a non-200 / unmounted route -> {kind:"dormant"}
// so the page renders the premium "coming soon" panel, NEVER an error wall).
//
// READ-ONLY + audited server-side: the backend GET /admin/ads/roi is
// require_super_admin and emits a control-audit entry per read. No mutations
// live here — the super-admin oversight path is read-only by contract
// (TENANCY §W1). Money stays `_minor` (paise) end-to-end.
//
// GRACEFUL: until /admin/ads/roi is mounted (FEATURE_ADS=0), the read returns
// {kind:"dormant"} and the page shows the DormantPanel.

import { BASE, authHeaders } from "@/lib/api";
import type { BadgeVariant } from "@/components/Badge";

/* ----------------------------------------------------------------- types */

// One vendor's cross-tenant ad-ROI rollup. Every metric optional so a partial
// backend degrades gracefully (the page renders "—" for a missing figure).
// `spend_30d_minor` / `revenue_30d_minor` are PAISE; `roas` is a plain ratio
// (revenue / spend) the backend computes once so every client agrees.
export type VendorAdRoi = {
    tenant_id: string;
    name?: string;
    spend_30d_minor?: number;
    revenue_30d_minor?: number;
    leads_30d?: number;
    qualified_30d?: number;
    roas?: number | null; // revenue / spend (blended)
    cpl_minor?: number | null; // cost per lead
    cpq_minor?: number | null; // cost per qualified
    active_campaigns?: number;
    // Overall campaign health for this vendor: the worst live signal across its
    // campaigns (a cap breach / CPL breaker beats a green "healthy").
    campaign_health?: AdRoiHealth;
    currency?: string;
};

// The single campaign-health vocabulary the column + the drill-down share.
export type AdRoiHealth =
    | "healthy"
    | "warming"
    | "no_spend"
    | "cap_reached"
    | "cpl_breach"
    | "blocked"
    | string;

export type VendorsAdRoiResponse = {
    ok: boolean;
    vendors: VendorAdRoi[];
    currency?: string;
    // Fleet-wide rollup the KPI strip reads directly (derived client-side when omitted).
    totals?: {
        spend_30d_minor?: number;
        revenue_30d_minor?: number;
        leads_30d?: number;
        qualified_30d?: number;
        roas?: number | null;
        active_vendors?: number;
    };
};

// Per-vendor drill-down ad-spend/usage panel (the [id] page reads this).
export type VendorAdUsageResponse = {
    ok: boolean;
    tenant_id: string;
    spend_30d_minor?: number;
    spend_today_minor?: number;
    revenue_30d_minor?: number;
    leads_30d?: number;
    qualified_30d?: number;
    roas?: number | null;
    cpl_minor?: number | null;
    cpq_minor?: number | null;
    active_campaigns?: number;
    daily_cap_minor?: number;
    campaign_health?: AdRoiHealth;
    currency?: string;
};

/* ------------------------------------------- discriminated read result (dormant-safe) */

export type RoiRead<T> =
    | { kind: "ok"; data: T }
    | { kind: "dormant"; reason: string }
    | { kind: "error"; message: string };

async function read<T>(path: string): Promise<RoiRead<T>> {
    let res: Response;
    try {
        res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
    } catch {
        // Network / not-deployed — treat as dormant, not a hard error.
        return { kind: "dormant", reason: "unreachable" };
    }
    if (res.status === 401 && typeof window !== "undefined") {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
        window.location.href = "/login";
        return { kind: "error", message: "Unauthorized" };
    }
    // 404 (route not mounted) / 501 / 503 (feature off) => dormant, never an error wall.
    if (res.status === 404 || res.status === 501 || res.status === 503) {
        return { kind: "dormant", reason: `http_${res.status}` };
    }
    if (!res.ok) {
        let msg = `Couldn't load ad ROI (${res.status})`;
        try {
            const b = await res.json();
            if (b && typeof b.detail === "string") msg = b.detail;
            else if (b && typeof b.error === "string") msg = b.error;
        } catch {
            /* non-JSON */
        }
        return { kind: "error", message: msg };
    }
    try {
        return { kind: "ok", data: (await res.json()) as T };
    } catch {
        return { kind: "error", message: "The ad-ROI response was malformed." };
    }
}

/* ------------------------------------------------------------------- reads */

// GET /admin/ads/roi — cross-tenant aggregate ad ROI for every vendor (read-only,
// audited, super-admin). Dormant-safe.
export const getVendorsAdRoi = () => read<VendorsAdRoiResponse>("/admin/ads/roi");

// GET /admin/ads/roi/{tenant_id} — one vendor's ad-spend/usage drill-down panel.
export const getVendorAdUsage = (id: string) =>
    read<VendorAdUsageResponse>(`/admin/ads/roi/${encodeURIComponent(id)}`);

/* --------------------------------------------------------------- formatters */

// minor units (paise) -> "₹1,500". null/undefined render "—". Mirrors the ads
// _lib.ts fmtMoney so every money figure in the panel reads identically.
export function fmtMoney(minor?: number | null, currency = "INR"): string {
    if (minor === null || minor === undefined) return "—";
    const major = minor / 100;
    const symbol = currency === "INR" ? "₹" : currency === "USD" ? "$" : "";
    try {
        return `${symbol}${major.toLocaleString(undefined, {
            minimumFractionDigits: major % 1 === 0 ? 0 : 2,
            maximumFractionDigits: 2,
        })}`;
    } catch {
        return `${symbol}${major}`;
    }
}

// A ROAS ratio -> "3.2×". null / no-spend renders "—".
export function fmtRoas(roas?: number | null): string {
    if (roas === null || roas === undefined || !Number.isFinite(roas)) return "—";
    return `${roas.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 1 })}×`;
}

// Campaign-health -> Badge tone + human label. The worst live signal wins, so
// a cap breach reads "danger" even if other campaigns are green. Mirrors the
// ads _shared.tsx statusVariant vocabulary so health reads identically panel-wide.
const HEALTH_MAP: Record<string, { label: string; variant: BadgeVariant; dot?: boolean }> = {
    healthy: { label: "Healthy", variant: "success", dot: true },
    warming: { label: "Warming up", variant: "info", dot: true },
    no_spend: { label: "No spend", variant: "neutral" },
    cap_reached: { label: "Cap reached", variant: "warning", dot: true },
    cpl_breach: { label: "CPL breach", variant: "danger", dot: true },
    blocked: { label: "Blocked", variant: "danger" },
};

export function healthMeta(health?: AdRoiHealth): { label: string; variant: BadgeVariant; dot?: boolean } {
    if (!health) return { label: "—", variant: "neutral" };
    return HEALTH_MAP[health] ?? { label: health.replace(/_/g, " "), variant: "neutral" };
}

// Derive the fleet-wide totals client-side when the backend omits them, so the
// KPI strip always has a real figure (no fabricated values — pure aggregation).
export function deriveRoiTotals(vendors: VendorAdRoi[]): NonNullable<VendorsAdRoiResponse["totals"]> {
    const spend = vendors.reduce((s, v) => s + (v.spend_30d_minor ?? 0), 0);
    const revenue = vendors.reduce((s, v) => s + (v.revenue_30d_minor ?? 0), 0);
    return {
        spend_30d_minor: spend,
        revenue_30d_minor: revenue,
        leads_30d: vendors.reduce((s, v) => s + (v.leads_30d ?? 0), 0),
        qualified_30d: vendors.reduce((s, v) => s + (v.qualified_30d ?? 0), 0),
        roas: spend > 0 ? revenue / spend : null,
        active_vendors: vendors.filter((v) => (v.spend_30d_minor ?? 0) > 0).length,
    };
}
