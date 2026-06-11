"use client";

// ============================================================
// EntitlementToggle (CL-F2) — THE 3-state permission row (the heart)
//
// The founder's HIDE vs LOCK vs ON, per feature, as ONE reusable row. Used in
// the Vendor Workspace Permissions tab (per-vendor override) and — later —
// Feature Flags (global default) and the Plans editor. Assembled ONLY from
// existing primitives (Badge provenance pill + Icon + a Tabs-style segmented
// control). NOT from scratch. Design of record: design/control-ui.md §3.
//
// Row anatomy (left -> right):
//   [feature label + kind chip] [provenance pill] [ On | Lock | Hide ] [Reset]
//
// - On   = green active  (feature fully available)
// - Lock = amber active  (visible-but-locked; the vendor sees the LockOverlay)
// - Hide = grey active   (gone everywhere; backend 404s the route)
//
// - Provenance pill tells the admin WHERE the current effective mode comes from
//   (the resolution chain): global / plan / override / status / parent.
// - An explicit per-vendor "override" shows a small Reset that clears it
//   (reverts to plan/global).
// - is_core rows (login/settings/billing-pay/dashboard): Lock + Hide are
//   DISABLED with a tooltip — the self-lockout floor (a core feature can never
//   be hidden, else the tenant loses the only path back in).
// - A row whose mode is FORCED by a hidden/locked parent module ("parent") or a
//   suspended/disabled status ("status") renders the segmented control disabled
//   with a caption, since the effective value isn't the admin's to set here.
//
// COSMETIC + OPTIMISTIC: the parent owns the write (PUT .../entitlements/{key})
// and passes a `busy` flag + the resolved row; this component is presentational.
// The BACKEND middleware is the only real boundary (spec §9.1).
// ============================================================

import Badge, { type BadgeVariant } from "@/components/Badge";
import Icon from "@/components/Icon";
import type { FeatureMode, ResolvedEntitlement, EntitlementProvenance } from "@/lib/api";

type EntitlementToggleProps = {
    row: ResolvedEntitlement;
    // Called when the admin picks a new mode for this feature. Optimistic — the
    // parent flips the row immediately and reconciles on resolve/failure.
    onSet: (mode: FeatureMode) => void;
    // Called when the admin clears an explicit per-vendor override (Reset).
    onReset?: () => void;
    // A write is in flight for this row — disables the control + shows a spinner.
    busy?: boolean;
    // Indent depth (0 = module, 1 = page, 2 = action) for the tree hierarchy.
    depth?: number;
};

const PROVENANCE_META: Record<
    EntitlementProvenance,
    { label: string; variant: BadgeVariant; hint: string }
> = {
    global: { label: "Global", variant: "neutral", hint: "Inherited from the global default for this feature." },
    plan: { label: "Plan", variant: "info", hint: "Set by the vendor's plan." },
    override: { label: "Override", variant: "warning", hint: "An explicit per-vendor override. Reset to revert to plan / global." },
    status: { label: "Status", variant: "danger", hint: "Forced by the vendor's account status (suspended / disabled / expired)." },
    parent: { label: "Inherited", variant: "neutral", hint: "Rolled down from a hidden / locked parent module." },
};

const KIND_LABEL: Record<string, string> = {
    module: "Module",
    page: "Page",
    feature: "Feature",
    action: "Action",
    integration: "Integration",
    ai_agent: "AI agent",
    api: "API",
};

// One segment of the [ On | Lock | Hide ] control.
const SEGMENTS: { mode: FeatureMode; label: string; icon: string; active: string; ring: string }[] = [
    {
        mode: "on",
        label: "On",
        icon: "check",
        // green active
        active: "bg-[#1FB16B]/12 text-[#0F8F53] fill-[#0F8F53] dark:text-[#3FD089] dark:fill-[#3FD089]",
        ring: "ring-[#1FB16B]/30",
    },
    {
        mode: "locked",
        label: "Lock",
        icon: "lock",
        // amber active
        active: "bg-[#EF9D0E]/14 text-[#C77E08] fill-[#C77E08] dark:text-[#EF9D0E] dark:fill-[#EF9D0E]",
        ring: "ring-[#EF9D0E]/30",
    },
    {
        mode: "hidden",
        label: "Hide",
        icon: "block",
        // grey active
        active: "bg-shade-07/8 text-t-secondary fill-t-secondary dark:bg-shade-04",
        ring: "ring-s-stroke2",
    },
];

const EntitlementToggle = ({ row, onSet, onReset, busy, depth = 0 }: EntitlementToggleProps) => {
    const isCore = !!row.is_core;
    const prov = PROVENANCE_META[row.provenance] ?? PROVENANCE_META.global;
    // A mode FORCED by status or a parent rolldown isn't editable on this row.
    const forced = row.provenance === "status" || row.provenance === "parent";
    const hasOverride = row.override != null;

    return (
        <div
            className={`flex items-center gap-3 py-3.5 px-4 max-md:flex-col max-md:items-stretch max-md:gap-3 ${
                forced ? "opacity-70" : ""
            }`}
            style={depth ? { paddingLeft: `${16 + depth * 18}px` } : undefined}
        >
            {/* Label + kind chip + (for forced rows) the reason caption */}
            <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                    {depth > 0 && (
                        <span className="text-t-tertiary fill-t-tertiary shrink-0" aria-hidden>
                            <Icon className="size-4 fill-inherit rotate-90 opacity-50" name="arrow" />
                        </span>
                    )}
                    <span className="text-button text-t-primary truncate">{row.label}</span>
                    <Badge variant="neutral" className="!text-caption !px-2 !py-0.5">
                        {KIND_LABEL[row.kind] ?? row.kind}
                    </Badge>
                    {isCore && (
                        <span title="Core feature — can be locked but never hidden (anti-lockout).">
                            <Badge variant="info" className="!text-caption !px-2 !py-0.5">Core</Badge>
                        </span>
                    )}
                </div>
                {row.nav_href && (
                    <div className="mt-0.5 text-caption text-t-tertiary truncate font-mono">{row.nav_href}</div>
                )}
                {row.provenance === "parent" && (
                    <div className="mt-0.5 text-caption text-t-tertiary">Hidden / locked by parent module</div>
                )}
                {row.provenance === "status" && (
                    <div className="mt-0.5 text-caption text-t-tertiary">Forced by account status</div>
                )}
            </div>

            {/* Provenance pill */}
            <div className="shrink-0 max-md:order-3" title={prov.hint}>
                <Badge variant={prov.variant} className="!px-2.5">{prov.label}</Badge>
            </div>

            {/* The 3-state segmented control */}
            <div
                className={`shrink-0 inline-flex items-center gap-0.5 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle ${
                    busy || forced ? "opacity-60 pointer-events-none" : ""
                }`}
                role="radiogroup"
                aria-label={`Access for ${row.label}`}
            >
                {SEGMENTS.map((seg) => {
                    const isActive = row.mode === seg.mode;
                    // Lock/Hide disabled on a core feature; Hide also disabled on the
                    // module floor handled by is_core upstream. On is always allowed.
                    const disabled =
                        (isCore && (seg.mode === "hidden" || seg.mode === "locked")) || busy || forced;
                    const coreBlocked = isCore && (seg.mode === "hidden" || seg.mode === "locked");
                    return (
                        <button
                            key={seg.mode}
                            type="button"
                            role="radio"
                            aria-checked={isActive}
                            disabled={disabled}
                            title={coreBlocked ? "Core feature — cannot be hidden or locked." : undefined}
                            onClick={() => !isActive && onSet(seg.mode)}
                            className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-button transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                                isActive
                                    ? `${seg.active} ring-1 ${seg.ring} shadow-sm`
                                    : "text-t-secondary fill-t-secondary hover:text-t-primary hover:fill-t-primary"
                            }`}
                        >
                            <Icon className="size-4 fill-inherit" name={seg.icon} />
                            <span className="max-sm:hidden">{seg.label}</span>
                        </button>
                    );
                })}
            </div>

            {/* Reset (only when an explicit per-vendor override exists) */}
            <div className="shrink-0 w-9 flex justify-center max-md:order-4">
                {busy ? (
                    <svg className="animate-spin h-4 w-4 text-t-tertiary" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                ) : hasOverride && onReset && !forced ? (
                    <button
                        type="button"
                        onClick={onReset}
                        title="Reset to plan / global"
                        aria-label={`Reset ${row.label} to plan or global`}
                        className="inline-flex items-center justify-center size-8 rounded-full border border-s-stroke2 text-t-secondary fill-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary hover:fill-t-primary"
                    >
                        <Icon className="size-4 fill-inherit" name="reply" />
                    </button>
                ) : null}
            </div>
        </div>
    );
};

export default EntitlementToggle;
