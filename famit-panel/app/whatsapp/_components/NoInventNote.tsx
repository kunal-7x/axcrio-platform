// The master §20 NO-INVENT guardrail note, rendered inline on every AI surface
// (spec §5: "every AI surface renders the master §20 guardrail note; the UI
// never shows a price/offer/claim the campaign didn't provide").

import Icon from "@/components/Icon";

const NoInventNote = ({ className }: { className?: string }) => (
    <div
        className={`flex items-start gap-2.5 p-3.5 rounded-3xl bg-b-surface1 text-caption text-t-tertiary ${
            className || ""
        }`}
    >
        <Icon className="shrink-0 mt-px fill-t-tertiary !size-4" name="info" />
        <span>
            AI uses only your campaign&apos;s real data — it never invents a price,
            offer, or claim you didn&apos;t provide.
        </span>
    </div>
);

export default NoInventNote;
