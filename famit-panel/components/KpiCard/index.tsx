// Hero KPI / metric card (feat/premium-ui). Big tabular number + overline
// label + optional glyph, sparkline, sub-line and a thin cap meter. Every
// optional slot is REAL data only — no fabricated deltas (no prior-period
// data exists in the API). Additive component; nothing existing changed.

import Icon from "@/components/Icon";
import Sparkline from "@/components/Sparkline";

type Tone = "neutral" | "success" | "danger" | "warning" | "info";

const TONE_FILL: Record<Tone, string> = {
    neutral: "fill-t-secondary",
    success: "fill-primary-02",
    danger: "fill-primary-03",
    warning: "fill-primary-05",
    info: "fill-primary-01",
};

const TONE_VAR: Record<Tone, string> = {
    neutral: "var(--chart-min)",
    success: "var(--chart-green)",
    danger: "var(--primary-03)",
    warning: "var(--primary-05)",
    info: "var(--primary-01)",
};

type KpiCardProps = {
    label: string;
    value: React.ReactNode;
    icon?: string;
    tone?: Tone;
    sub?: React.ReactNode; // small footnote line under the value
    spark?: number[]; // real series for an inline sparkline
    // thin cap meter: provide a 0..1 ratio + optional accent tone
    meter?: number | null;
    className?: string;
    style?: React.CSSProperties;
};

const KpiCard = ({
    label,
    value,
    icon,
    tone = "neutral",
    sub,
    spark,
    meter,
    className,
    style,
}: KpiCardProps) => {
    const meterPct =
        meter == null ? null : Math.max(0, Math.min(100, meter * 100));
    return (
        <div className={`kpi rise-in ${className || ""}`} style={style}>
            <div className="flex items-start justify-between gap-3">
                <div className="kpi-label">
                    {icon && (
                        <span className={`kpi-glyph ${TONE_FILL[tone]}`}>
                            <Icon name={icon} className="fill-inherit" />
                        </span>
                    )}
                    {label}
                </div>
            </div>

            <div className="flex items-end justify-between gap-4">
                <div className="kpi-value">{value}</div>
                {spark && spark.length > 1 && (
                    <Sparkline
                        data={spark}
                        color={TONE_VAR[tone]}
                        className="shrink-0 max-md:hidden"
                    />
                )}
            </div>

            {sub && <div className="kpi-foot">{sub}</div>}

            {meterPct != null && (
                <div className="meter mt-1">
                    <div
                        className="meter-fill"
                        style={{
                            width: `${meterPct}%`,
                            background: TONE_VAR[tone],
                        }}
                    />
                </div>
            )}
        </div>
    );
};

export default KpiCard;
