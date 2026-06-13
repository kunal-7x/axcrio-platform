"use client";

// ============================================================================
// Run-page Stepper — a refined, Core_2-composed horizontal stepper.
//
// A confident Linear/Stripe-grade progress spine for the 4-step Run flow:
//   ① Campaign & Audience  ② Voice & Providers  ③ Pacing & Handoff  ④ Review & Launch
//
// Behaviour:
//   • completed steps are clickable (jump back); the current step is current.
//   • LOCK-AHEAD — a step ahead of the furthest-reached step is disabled until
//     the steps before it are valid (the parent passes `maxReachable`).
//   • a completed step shows a check-circle-fill; the active step a filled index
//     chip; a locked future step a hairline index chip.
//
// Accessibility: role="tablist" on the rail, each stop is a real <button>
//   carrying aria-current="step" when active + aria-disabled when locked, and a
//   focus-visible ring. Mobile (max-lg) collapses to a compact "Step N of M"
//   pill + a dot row (NO horizontal scroll), mirroring the proven segmented
//   pattern in _voice-providers.tsx:362-401.
//
// Token-pure Core_2 (Inter Display, zero raw hex — only globals.css tokens).
// Pure presentational: it owns no flow state, it just renders `step` and calls
// `onStep`. Composed from Icon + tokens, no new primitive invented.
// ============================================================================

import Icon from "@/components/Icon";

export type Step = {
    // short label shown on the rail
    label: string;
    // one-line helper shown under the label on wide screens
    hint?: string;
};

type StepperProps = {
    steps: Step[];
    // 0-based index of the active step
    step: number;
    // 0-based index of the furthest step the user may jump FORWARD to
    // (everything <= this is unlocked; beyond it is locked-ahead)
    maxReachable: number;
    onStep: (index: number) => void;
};

export default function Stepper({ steps, step, maxReachable, onStep }: StepperProps) {
    const total = steps.length;

    return (
        <div className="surface p-2 max-lg:p-3">
            {/* ── WIDE: full horizontal rail ── */}
            <div
                role="tablist"
                aria-label="Run a campaign — steps"
                aria-orientation="horizontal"
                className="hidden lg:flex items-stretch gap-1"
            >
                {steps.map((s, i) => {
                    const done = i < step;
                    const active = i === step;
                    const locked = i > maxReachable;
                    const clickable = !active && !locked;
                    return (
                        <div key={s.label} className="flex items-center flex-1 min-w-0">
                            <button
                                type="button"
                                role="tab"
                                aria-current={active ? "step" : undefined}
                                aria-selected={active}
                                aria-disabled={locked || undefined}
                                disabled={locked}
                                onClick={() => clickable && onStep(i)}
                                className={`group flex items-center gap-3 flex-1 min-w-0 h-14 px-3.5 rounded-2xl text-left outline-none transition-all focus-visible:ring-2 focus-visible:ring-primary-01/40 focus-visible:ring-offset-2 focus-visible:ring-offset-b-surface2 ${
                                    active
                                        ? "bg-b-surface1 shadow-depth dark:bg-shade-04/50"
                                        : locked
                                        ? "cursor-not-allowed"
                                        : "cursor-pointer hover:bg-b-surface1/60 dark:hover:bg-shade-04/30"
                                }`}
                            >
                                {/* index / status chip */}
                                <span className="shrink-0">
                                    {done ? (
                                        <Icon
                                            name="check-circle-fill"
                                            className="size-7 fill-primary-02"
                                        />
                                    ) : (
                                        <span
                                            className={`grid place-items-center size-7 rounded-full text-caption font-semibold tabular-nums transition-colors ${
                                                active
                                                    ? "bg-b-dark1 text-t-light dark:bg-shade-09 dark:text-shade-01"
                                                    : locked
                                                    ? "border border-s-subtle text-t-tertiary"
                                                    : "border border-s-stroke2 text-t-secondary group-hover:text-t-primary"
                                            }`}
                                        >
                                            {i + 1}
                                        </span>
                                    )}
                                </span>
                                {/* label + hint */}
                                <span className="min-w-0">
                                    <span
                                        className={`block text-button leading-tight truncate ${
                                            active
                                                ? "text-t-primary"
                                                : locked
                                                ? "text-t-tertiary"
                                                : "text-t-secondary group-hover:text-t-primary"
                                        }`}
                                    >
                                        {s.label}
                                    </span>
                                    {s.hint && (
                                        <span className="block text-caption text-t-tertiary leading-tight truncate">
                                            {s.hint}
                                        </span>
                                    )}
                                </span>
                            </button>
                            {/* connector between stops */}
                            {i < total - 1 && (
                                <span
                                    aria-hidden
                                    className={`h-px w-6 mx-0.5 shrink-0 rounded-full transition-colors ${
                                        i < step ? "bg-primary-02/50" : "bg-s-subtle"
                                    }`}
                                />
                            )}
                        </div>
                    );
                })}
            </div>

            {/* ── MOBILE: compact "Step N of M" pill + dot row (no scroll) ── */}
            <div className="lg:hidden">
                <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                        <div className="eyebrow mb-0.5">
                            Step {step + 1} of {total}
                        </div>
                        <div className="text-button text-t-primary truncate">
                            {steps[step]?.label}
                        </div>
                    </div>
                    <div
                        role="tablist"
                        aria-label="Run a campaign — steps"
                        className="flex items-center gap-1.5 shrink-0"
                    >
                        {steps.map((s, i) => {
                            const done = i < step;
                            const active = i === step;
                            const locked = i > maxReachable;
                            return (
                                <button
                                    key={s.label}
                                    type="button"
                                    role="tab"
                                    aria-label={`Step ${i + 1}: ${s.label}`}
                                    aria-current={active ? "step" : undefined}
                                    aria-selected={active}
                                    aria-disabled={locked || undefined}
                                    disabled={locked || active}
                                    onClick={() => !active && !locked && onStep(i)}
                                    className={`rounded-full outline-none transition-all focus-visible:ring-2 focus-visible:ring-primary-01/40 focus-visible:ring-offset-2 focus-visible:ring-offset-b-surface2 ${
                                        active
                                            ? "h-2 w-6 bg-b-dark1 dark:bg-shade-09"
                                            : done
                                            ? "size-2 bg-primary-02 cursor-pointer"
                                            : locked
                                            ? "size-2 bg-s-subtle cursor-not-allowed"
                                            : "size-2 bg-s-stroke2 cursor-pointer"
                                    }`}
                                />
                            );
                        })}
                    </div>
                </div>
            </div>
        </div>
    );
}
