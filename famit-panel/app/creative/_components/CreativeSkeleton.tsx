"use client";

/**
 * CreativeSkeleton — the PER-CARD "this slot is developing" loader.
 *
 * The companion to <GenerationLoader /> (the batch hero). When a generation job
 * fans out, N of these stream into the variant grid in the SAME slots the
 * finished cards will occupy (so cards don't jump), each showing its angle label
 * + a small spinner immediately — then morph IN PLACE into the real S5 card as
 * each variant's bytes land ("develops like a photo").
 *
 * CSS-only (no canvas, no new npm dep), token-pure (reuses the `.skeleton`
 * shimmer + `--gl-dot` field language already in globals.css from W1), dark-mode
 * by default, and prefers-reduced-motion safe (the shimmer stops). 4 states:
 * queued · generating · ready(morph-out) · error.
 *
 * Lives in app/creative/_components (this unit owns only its page dirs; the
 * shared shell components/ are W1's). Presentational only — zero network I/O.
 */

import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Spinner from "@/components/Spinner";
import Icon from "@/components/Icon";

export type CreativeSkeletonState = "queued" | "generating" | "ready" | "error";

export type CreativeSkeletonProps = {
    /** The angle label shown immediately (informative): "Variant 2 · Urgency". */
    label?: string;
    state?: CreativeSkeletonState;
    /** Calm human error copy for the error state. */
    errorMessage?: string;
    onRetry?: () => void;
    className?: string;
};

const CreativeSkeleton = ({
    label = "Variant",
    state = "generating",
    errorMessage = "Couldn't create this one.",
    onRetry,
    className = "",
}: CreativeSkeletonProps) => {
    const isError = state === "error";

    return (
        <div
            className={`cs-skel ${className}`}
            role="status"
            aria-live="polite"
            aria-busy={state === "queued" || state === "generating"}
            aria-label={`${label}: ${isError ? "failed" : state}`}
        >
            {/* The developing preview area — the token shimmer reused as a
                breathing "developing" field (no new CSS; globals.css is W1's). */}
            <div
                className={`relative h-57.5 rounded-3xl overflow-hidden ${
                    isError ? "bg-b-surface1 dark:bg-shade-04/40" : "skeleton !rounded-3xl"
                }`}
            >
                {/* angle badge over the field — shown the instant the slot appears */}
                <div className="absolute top-3 left-3 z-2">
                    <Badge variant={isError ? "danger" : "neutral"}>{label}</Badge>
                </div>

                {/* centre status glyph */}
                <div className="absolute inset-0 flex items-center justify-center">
                    {isError ? (
                        <div className="flex flex-col items-center gap-3 text-center px-4">
                            <span className="flex items-center justify-center size-10 rounded-2xl bg-b-surface2 fill-t-tertiary">
                                <Icon name="close" />
                            </span>
                            <p className="text-body-2 text-t-secondary max-w-44">
                                {errorMessage}
                            </p>
                        </div>
                    ) : (
                        <div className="flex flex-col items-center gap-2">
                            <Spinner />
                            <span className="text-caption text-t-tertiary">
                                {state === "queued" ? "Queued" : "Creating…"}
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* the meta-row placeholders (or a retry on error) */}
            {isError ? (
                <div className="mt-3 flex items-center gap-2">
                    {onRetry && (
                        <Button isStroke className="!h-9 !px-4 !text-body-2" onClick={onRetry}>
                            Try again
                        </Button>
                    )}
                </div>
            ) : (
                <div className="mt-3 space-y-2">
                    <div className="skeleton h-4 w-3/5" />
                    <div className="skeleton h-3 w-2/5" />
                </div>
            )}
        </div>
    );
};

export default CreativeSkeleton;
