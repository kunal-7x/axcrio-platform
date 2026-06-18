"use client";

// W15 — the ONE shared filter bar mounted on every data page (Dashboard, Reports,
// Leads & CRM, Call Logs, Bookings, Billing). design/W15-UI-IA-PLAN.md §3.
//
// The single biggest consistency win: before this, every page re-rolled its own
// date/campaign/status filter (or had none). This composes EXISTING Core_2 kit
// primitives ONLY — `Select` (date-range presets + lead status), `CampaignSelect`
// (the live campaign dropdown), `Tabs` — into one row. NOTHING is built from
// scratch; it is a composition + a URL-state binder.
//
// State lives in URL query params (`?range=7d&campaign=…&status=hot&from=…&to=…`) so
// it PERSISTS across the Dashboard → Reports → Call Logs drill-down and is
// shareable. Default range = Today everywhere (founder rule).
//
// It is designed to drop into a `Card`'s `headContent` slot (Core_2's native
// in-card chrome row) — no new layout primitive. On narrow screens it wraps.

import { useCallback, useMemo } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import Select from "@/components/Select";
import CampaignSelect from "@/components/CampaignSelect";
import { type SelectOption } from "@/types/select";
import {
    RANGE_PRESETS,
    type RangePreset,
    resolveRange,
    type ResolvedRange,
} from "@/lib/report";
import { type Campaign } from "@/lib/api";

// Business-friendly lead-status filter (the ONE badge vocabulary, §4).
const STATUS_OPTIONS: { id: string; name: string }[] = [
    { id: "", name: "All statuses" },
    { id: "hot", name: "Hot" },
    { id: "warm", name: "Warm" },
    { id: "cold", name: "Cold" },
    { id: "dead", name: "Dead" },
    { id: "booked", name: "Booked" },
    { id: "callback", name: "Callback" },
    { id: "interested", name: "Interested" },
];

export type GlobalFilterState = {
    range: ResolvedRange;
    campaign: string; // campaign id ("" = all)
    status: string; // lead-status filter ("" = all)
};

// Read the current filters off the URL (the single source of truth). Default
// preset = today. Custom carries ?from&to.
export function useGlobalFilters(): GlobalFilterState {
    const params = useSearchParams();
    return useMemo(() => {
        const preset = (params.get("range") as RangePreset) || "today";
        const valid = RANGE_PRESETS.some((p) => p.id === preset);
        const p: RangePreset = valid ? preset : "today";
        const range = resolveRange(p, {
            from: params.get("from") || undefined,
            to: params.get("to") || undefined,
        });
        return {
            range,
            campaign: params.get("campaign") || "",
            status: params.get("status") || "",
        };
    }, [params]);
}

type GlobalFiltersProps = {
    // Which controls to show — a page that has no per-lead status hides it, etc.
    show?: { range?: boolean; campaign?: boolean; status?: boolean };
    className?: string;
};

const GlobalFilters = ({ show, className }: GlobalFiltersProps) => {
    const router = useRouter();
    const pathname = usePathname();
    const params = useSearchParams();
    const { range, campaign, status } = useGlobalFilters();

    const showRange = show?.range ?? true;
    const showCampaign = show?.campaign ?? true;
    const showStatus = show?.status ?? false;

    // Merge a patch into the URL query, preserving everything else (so the bar
    // composes with a page's own params). Replace (not push) so back-button isn't
    // spammed with every filter tweak.
    const patch = useCallback(
        (next: Record<string, string | null>) => {
            const sp = new URLSearchParams(params.toString());
            for (const [k, v] of Object.entries(next)) {
                if (v == null || v === "") sp.delete(k);
                else sp.set(k, v);
            }
            const qs = sp.toString();
            router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
        },
        [params, pathname, router]
    );

    // ── Range select ──
    const rangeOptions: SelectOption[] = useMemo(
        () => RANGE_PRESETS.map((p, i) => ({ id: i + 1, name: p.label })),
        []
    );
    const rangeValue: SelectOption = useMemo(() => {
        const idx = RANGE_PRESETS.findIndex((p) => p.id === range.preset);
        return rangeOptions[idx >= 0 ? idx : 0];
    }, [range.preset, rangeOptions]);
    const onRange = (opt: SelectOption) => {
        const preset = RANGE_PRESETS[opt.id - 1]?.id ?? "today";
        // Leaving custom clears the explicit dates; entering it seeds today.
        if (preset === "custom") {
            patch({ range: "custom" });
        } else {
            patch({ range: preset === "today" ? null : preset, from: null, to: null });
        }
    };

    // ── Status select ──
    const statusOptions: SelectOption[] = useMemo(
        () => STATUS_OPTIONS.map((s, i) => ({ id: i + 1, name: s.name })),
        []
    );
    const statusValue: SelectOption = useMemo(() => {
        const idx = STATUS_OPTIONS.findIndex((s) => s.id === status);
        return statusOptions[idx >= 0 ? idx : 0];
    }, [status, statusOptions]);
    const onStatus = (opt: SelectOption) => {
        const id = STATUS_OPTIONS[opt.id - 1]?.id ?? "";
        patch({ status: id || null });
    };

    // ── Campaign select (reuses the live CampaignSelect) ──
    // W-FRONTEND-RECONCILE §3 Fix 4 — the empty-id "All campaigns" row clears the
    // URL param so the campaign filter can RESET (previously it stuck once picked).
    const onCampaign = (c: Campaign) => {
        patch({ campaign: c.id ? c.id : null });
    };

    return (
        <div className={`flex flex-wrap items-center gap-2 ${className || ""}`}>
            {showRange && (
                <Select
                    className="min-w-40 max-md:min-w-32"
                    value={rangeValue}
                    onChange={onRange}
                    options={rangeOptions}
                />
            )}
            {range.preset === "custom" && (
                <div className="flex items-center gap-2">
                    <input
                        type="date"
                        value={range.from}
                        onChange={(e) => patch({ from: e.target.value || null })}
                        className="h-12 px-3 border border-s-stroke2 rounded-3xl bg-transparent text-body-2 text-t-primary outline-none focus:border-primary-01/60"
                        aria-label="From date"
                    />
                    <span className="text-t-tertiary">–</span>
                    <input
                        type="date"
                        value={range.to}
                        onChange={(e) => patch({ to: e.target.value || null })}
                        className="h-12 px-3 border border-s-stroke2 rounded-3xl bg-transparent text-body-2 text-t-primary outline-none focus:border-primary-01/60"
                        aria-label="To date"
                    />
                </div>
            )}
            {showCampaign && (
                <CampaignSelect
                    className="min-w-44 max-md:min-w-36"
                    value={campaign || undefined}
                    onSelect={onCampaign}
                    label=""
                    placeholder="All campaigns"
                />
            )}
            {showStatus && (
                <Select
                    className="min-w-36 max-md:min-w-32"
                    value={statusValue}
                    onChange={onStatus}
                    options={statusOptions}
                />
            )}
        </div>
    );
};

export default GlobalFilters;
