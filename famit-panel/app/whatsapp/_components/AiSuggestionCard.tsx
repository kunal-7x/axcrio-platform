// ③ AI Template suggestion card (spec §2 ③) — a COMPOSE piece, not a new
// component family: Card chrome + Badge (angle) + Button (actions) + token text.
// Shows the AI-written template: name · WhatsApp body (with {{1}} tokens
// highlighted) · CTA label · marketing-angle badge · media recommendation.

import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import { type TemplateSuggestion } from "../_lib/types";

type AiSuggestionCardProps = {
    suggestion: TemplateSuggestion;
    onUse: () => void;
    onRegenerate?: () => void;
    onMore?: () => void;
    // Direct "Submit to Meta" on the card (approve → submit-to-Meta on THIS row).
    onSubmitMeta?: () => void;
    submitting?: boolean;
    // live Meta review state for this template (badge): none|pending|approved|rejected
    review?: "none" | "pending" | "approved" | "rejected";
    busy?: boolean;
};

const REVIEW_BADGE: Record<
    NonNullable<AiSuggestionCardProps["review"]>,
    { variant: "success" | "danger" | "warning" | "neutral"; label: string } | null
> = {
    none: null,
    pending: { variant: "warning", label: "Pending Meta" },
    approved: { variant: "success", label: "Approved by Meta" },
    rejected: { variant: "danger", label: "Rejected by Meta" },
};

// Highlight {{n}} personalization tokens inline (master: tokens are real merge
// fields, shown so the user knows what gets personalized).
function renderBody(body: string): React.ReactNode {
    const parts = body.split(/(\{\{\s*\d+\s*\}\})/g);
    return parts.map((p, i) =>
        /^\{\{\s*\d+\s*\}\}$/.test(p) ? (
            <span
                key={i}
                className="px-1 mx-0.5 rounded-md bg-b-surface1 text-primary-01 text-caption font-medium align-middle"
            >
                {p}
            </span>
        ) : (
            <span key={i}>{p}</span>
        )
    );
}

const AiSuggestionCard = ({
    suggestion,
    onUse,
    onRegenerate,
    onMore,
    onSubmitMeta,
    submitting,
    review = "none",
    busy,
}: AiSuggestionCardProps) => {
    const reviewBadge = REVIEW_BADGE[review];
    return (
    <div className="flex flex-col p-5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
        <div className="flex items-start gap-3">
            <div className="grow min-w-0">
                <div className="text-sub-title-1 text-t-primary truncate">{suggestion.name}</div>
                <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                    {suggestion.angle && <Badge variant="info">{suggestion.angle}</Badge>}
                    {reviewBadge && <Badge variant={reviewBadge.variant}>{reviewBadge.label}</Badge>}
                </div>
            </div>
        </div>

        <div className="mt-3 text-body-2 text-t-secondary whitespace-pre-wrap leading-relaxed">
            {renderBody(suggestion.body)}
        </div>

        {suggestion.cta && (
            <div className="flex items-center gap-2 mt-3 text-button text-t-primary">
                <Icon className="fill-t-secondary !size-4" name="link-1" />
                {suggestion.cta}
            </div>
        )}

        {suggestion.media_rec && (
            <div className="flex items-center gap-2 mt-3 text-caption text-t-tertiary">
                <Icon className="fill-t-tertiary !size-3.5" name="camera" />
                {suggestion.media_rec}
            </div>
        )}

        <div className="flex flex-wrap gap-2 mt-5">
            <Button isBlack onClick={onUse} disabled={busy}>
                Use this
            </Button>
            {onSubmitMeta && review !== "approved" && review !== "pending" && (
                <Button isStroke icon="upload" onClick={onSubmitMeta} disabled={busy || submitting}>
                    {submitting ? "Submitting…" : review === "rejected" ? "Resubmit to Meta" : "Submit to Meta"}
                </Button>
            )}
            {onRegenerate && (
                <Button isStroke icon="magic-pencil" onClick={onRegenerate} disabled={busy}>
                    Regenerate
                </Button>
            )}
            {onMore && (
                <Button isStroke onClick={onMore} disabled={busy}>
                    More variations
                </Button>
            )}
        </div>
    </div>
    );
};

export default AiSuggestionCard;
