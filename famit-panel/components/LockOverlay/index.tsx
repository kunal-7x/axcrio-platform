"use client";

// ============================================================
// LockOverlay (CL-F0) — vendor page LOCK upsell overlay
//
// Renders the real page chrome BLURRED + non-interactive behind a centered
// premium upsell card. The founder's "visible but a disabled overlay with
// upsell messaging, no interaction" (design/control-ui.md §4.3).
//
// Assembled ONLY from existing primitives — Card surface (.card), Modal-style
// backdrop, Button (isBlack CTA / isStroke secondary), Badge, Icon(lock).
// NOT from scratch. No focus trap: the page shows through, dimmed, so the
// curiosity/upsell reads premium rather than as a hard wall.
//
// COSMETIC ONLY (spec §9.1): even if a user deletes this overlay in devtools,
// the underlying /api/* route still 402s — no data leaks. This is UX, the
// backend 402 is the lock.
// ============================================================

import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";

type LockOverlayProps = {
    // Human label of the locked feature, e.g. "Call Logs". Drives the copy.
    feature?: string;
    // The page beneath — rendered blurred + pointer-events-none.
    children?: React.ReactNode;
    // Where "Upgrade" routes. Defaults to the plan/billing page.
    upgradeHref?: string;
    // Optional override copy.
    title?: string;
    description?: string;
    className?: string;
};

const LockOverlay = ({
    feature,
    children,
    upgradeHref = "/billing/plan",
    title,
    description,
    className,
}: LockOverlayProps) => {
    const heading = title || "This feature is locked";
    const sub =
        description ||
        (feature
            ? `Upgrade your plan to unlock ${feature}.`
            : "Upgrade your plan to unlock this feature.");

    return (
        <div className={`relative ${className || ""}`}>
            {/* The real page, dimmed + blurred + fully inert behind the panel. */}
            {children != null && (
                <div
                    className="pointer-events-none select-none blur-[3px] opacity-50 saturate-[0.85]"
                    aria-hidden
                    inert
                >
                    {children}
                </div>
            )}

            {/* Backdrop + centered upsell card (Modal look, no focus trap). */}
            <div
                className="absolute inset-0 z-20 flex items-center justify-center p-6 bg-shade-04/40 backdrop-blur-[2px] dark:bg-shade-09/55"
                role="dialog"
                aria-modal="false"
                aria-label={heading}
            >
                <div className="card max-w-105 w-full !mb-0 p-8 text-center max-md:p-6 shadow-depth">
                    {/* Lock glyph in a soft brand-amber medallion (LOCK = amber). */}
                    <div className="inline-flex items-center justify-center size-16 mb-5 rounded-full border border-[#EF9D0E]/20 bg-[#EF9D0E]/8">
                        <Icon className="size-8 fill-[#C77E08] dark:fill-[#EF9D0E]" name="lock" />
                    </div>

                    <div className="mb-3 flex justify-center">
                        <Badge variant="warning">Locked</Badge>
                    </div>

                    <h3 className="mb-2 text-h5 max-md:text-h6 text-t-primary">{heading}</h3>
                    <p className="mx-auto mb-6 max-w-80 text-body-2 text-t-secondary">{sub}</p>

                    <div className="flex items-center justify-center gap-3 max-md:flex-col">
                        <Button as="link" href={upgradeHref} isBlack icon="arrow-up-right">
                            Upgrade plan
                        </Button>
                        <Button as="link" href="/support" isStroke>
                            Contact us
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default LockOverlay;
