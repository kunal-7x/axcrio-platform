// Premium "coming soon" / not_configured card — the DORMANT-SAFE state for the
// AI-template-gen + Creative-attach surfaces (spec §5). Renders a calm, branded
// activation panel — NEVER an error wall — when /api/whatsapp/templates/generate
// or /api/assets/* answer 404/503 (the parallel backend wave hasn't landed).
//
// Pure reuse: Card chrome + Icon + Button. Token-only, zero raw hex.

import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";

type ComingSoonProps = {
    title: string;
    /** the one-line explanation of what unlocks when wired */
    body: string;
    /** glyph (defaults to magic-pencil — the AI-generation motif) */
    icon?: string;
    /** an in-place fallback the user CAN do today (e.g. "write one manually") */
    fallbackLabel?: string;
    onFallback?: () => void;
};

const ComingSoon = ({
    title,
    body,
    icon = "magic-pencil",
    fallbackLabel,
    onFallback,
}: ComingSoonProps) => (
    <Card title={title}>
        <div className="flex flex-col items-center text-center px-5 py-14 max-lg:px-3 max-md:py-10">
            <div className="flex justify-center items-center size-18 mb-5 rounded-full bg-b-surface1 ring-1 ring-s-stroke2">
                <Icon className="fill-t-secondary !size-7" name={icon} />
            </div>
            <div className="text-h6 text-t-primary">Coming soon</div>
            <div className="mt-2 max-w-100 text-body-2 text-t-secondary">{body}</div>
            <div className="mt-4 inline-flex items-center gap-2 px-3 h-8 rounded-full bg-b-surface1 text-caption text-t-tertiary">
                <span className="size-1.5 rounded-full bg-primary-05" />
                Activates automatically once the engine is connected
            </div>
            {fallbackLabel && onFallback && (
                <Button className="mt-7" isStroke onClick={onFallback}>
                    {fallbackLabel}
                </Button>
            )}
        </div>
    </Card>
);

export default ComingSoon;
