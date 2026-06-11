"use client";

/**
 * DormantCard — the calm "Creative Studio isn't enabled yet" state.
 *
 * Rendered whenever `GET /api/assets/status` says enabled:false (or a parallel
 * backend wave hasn't landed a sub-surface yet). NEVER an error — a premium
 * coming-soon card, token-styled, so the panel stays byte-identical-to-live when
 * AIASSET_ENABLED is off for a tenant (cs-workspace §3 / §17). Used as the whole
 * page body in the dormant path, and as the per-surface fallback for the
 * dormant-safe WhatsApp AI-template + attach surfaces (project brief).
 */

import Icon from "@/components/Icon";
import Button from "@/components/Button";

type DormantCardProps = {
    title?: string;
    message?: string;
    icon?: string;
    /** Optional action (e.g. a "Refresh" or a deep-link). */
    actionLabel?: string;
    onAction?: () => void;
    className?: string;
};

const DormantCard = ({
    title = "Creative Studio activates once your workspace is enabled",
    message = "Your AI design engine is ready to switch on. Once enabled, you'll create campaign-aware banners, ads and posters from a single instruction.",
    icon = "magic-pencil",
    actionLabel,
    onAction,
    className = "",
}: DormantCardProps) => (
    <div className={`card ${className}`}>
        <div className="flex flex-col items-center justify-center gap-4 py-20 px-6 text-center max-md:py-14">
            <span className="flex items-center justify-center size-14 rounded-3xl bg-b-surface1 fill-t-secondary dark:bg-shade-04/50">
                <Icon name={icon} />
            </span>
            <div className="max-w-100">
                <div className="text-sub-title-1 text-t-primary">{title}</div>
                <p className="mt-2 text-body-2 text-t-secondary">{message}</p>
            </div>
            {actionLabel && onAction && (
                <Button isStroke onClick={onAction}>
                    {actionLabel}
                </Button>
            )}
        </div>
    </div>
);

export default DormantCard;
