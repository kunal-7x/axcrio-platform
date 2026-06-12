// WhatsApp / Meta status + error surfacing — the TRUTH layer.
//
// Two calm, premium surfaces (no error walls, Signal tokens only):
//   • <MetaReadinessHint/>  — a calm "WhatsApp account status" line near the
//     send/submit area. Credentials ARE set, so it reflects readiness honestly:
//     connected, delivery may be pending Meta verification. Dormant-safe.
//   • <MetaErrorNote/>      — surfaces a FAILED send/submit in plain language,
//     mapping Meta's real reason (payment block / verification / template not
//     registered / hello_world) to a friendly note, with Meta's own raw
//     error_user_msg + code in a small muted debug line.
//
// Both reuse the existing inline-note archetype (NoInventNote / DeliveryStep),
// so they match the panel's premium style and carry zero raw hex.

import Icon from "@/components/Icon";
import { type MetaExplain } from "../_lib/waapi";

// tone → Signal-token ring + icon fill (token-pure, no raw hex)
function toneStyle(tone: MetaExplain["tone"]) {
    switch (tone) {
        case "danger":
            return { ring: "border-primary-03/40", fill: "fill-primary-03", icon: "block" };
        case "warning":
            return { ring: "border-primary-05/40", fill: "fill-primary-05", icon: "info" };
        default:
            return { ring: "border-s-subtle", fill: "fill-t-secondary", icon: "info" };
    }
}

// Surface a failed send/submit with Meta's real reason in plain language.
export function MetaErrorNote({
    explain,
    className,
}: {
    explain: MetaExplain;
    className?: string;
}) {
    const s = toneStyle(explain.tone);
    return (
        <div
            className={`flex items-start gap-3 p-4 rounded-3xl bg-b-surface2 border ${s.ring} ${className || ""}`}
        >
            <Icon className={`shrink-0 mt-0.5 ${s.fill}`} name={s.icon} />
            <div className="min-w-0">
                <div className="text-body-2 text-t-primary font-medium">{explain.title}</div>
                <div className="mt-0.5 text-body-2 text-t-secondary">{explain.detail}</div>
                {explain.debug && (
                    <div className="mt-1.5 text-caption text-t-tertiary break-words">{explain.debug}</div>
                )}
            </div>
        </div>
    );
}

// A calm readiness hint near the send/submit area. Honest about the real state:
// the account IS connected (credentials set), delivery may still be pending Meta
// business verification. `delivers` (a real successful send was observed) flips
// it to the fully-green line. Never an error wall.
export function MetaReadinessHint({
    delivers,
    className,
}: {
    delivers?: boolean;
    className?: string;
}) {
    if (delivers) {
        return (
            <div
                className={`flex items-start gap-2.5 p-3.5 rounded-3xl bg-b-surface1 text-caption text-t-tertiary ${className || ""}`}
            >
                <Icon className="shrink-0 mt-px fill-primary-02 !size-4" name="check-circle-fill" />
                <span>
                    <span className="text-t-secondary">WhatsApp connected.</span> Messages on
                    approved templates are delivering.
                </span>
            </div>
        );
    }
    return (
        <div
            className={`flex items-start gap-2.5 p-3.5 rounded-3xl bg-b-surface1 text-caption text-t-tertiary ${className || ""}`}
        >
            <Icon className="shrink-0 mt-px fill-primary-05 !size-4" name="info" />
            <span>
                <span className="text-t-secondary">WhatsApp connected.</span> Credentials are
                set — delivery to all recipients unlocks once Meta finishes verifying your
                business. Approved templates send today.
            </span>
        </div>
    );
}
