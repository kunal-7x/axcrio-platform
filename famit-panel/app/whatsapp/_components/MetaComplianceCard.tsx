// Meta-compliance status panel — the LOCAL pre-check verdict for a hand-written
// (or AI) template, shown on the Preview step so the founder SEES whether the
// template they just created is likely to pass Meta review BEFORE submitting.
// This is a lint, not Meta's gate (that stays in ApprovalStep). Token-only.

import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import { type ComplianceReport, type ComplianceLevel } from "../_lib/meta";

const ROW_ICON: Record<ComplianceLevel, { name: string; fill: string }> = {
    pass: { name: "check-circle-fill", fill: "fill-primary-02" },
    warn: { name: "info", fill: "fill-primary-05" },
    fail: { name: "block", fill: "fill-primary-03" },
};

const OVERALL: Record<
    ComplianceLevel,
    { variant: "success" | "warning" | "danger"; label: string }
> = {
    pass: { variant: "success", label: "Likely to pass Meta" },
    warn: { variant: "warning", label: "Review before submitting" },
    fail: { variant: "danger", label: "Won't pass Meta yet" },
};

const MetaComplianceCard = ({ report }: { report: ComplianceReport }) => {
    const o = OVERALL[report.overall];
    return (
        <div className="flex flex-col gap-3 p-4 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
            <div className="flex items-center gap-2.5">
                <Icon className="fill-primary-01 !size-4.5" name="check-circle" />
                <span className="text-button text-t-primary grow">Meta compliance</span>
                <Badge variant={o.variant}>{o.label}</Badge>
            </div>
            <div className="flex flex-col gap-2">
                {report.rules.map((r) => {
                    const ic = ROW_ICON[r.level];
                    return (
                        <div key={r.id} className="flex items-start gap-2.5">
                            <Icon className={`shrink-0 mt-px !size-4 ${ic.fill}`} name={ic.name} />
                            <div className="min-w-0">
                                <span className="text-body-2 text-t-primary">{r.label}</span>
                                <span className="ml-2 text-caption text-t-tertiary">{r.detail}</span>
                            </div>
                        </div>
                    );
                })}
            </div>
            <div className="text-caption text-t-tertiary">
                This is a local pre-check. Meta&apos;s own approval is shown live on the Approval step — never faked.
            </div>
        </div>
    );
};

export default MetaComplianceCard;
