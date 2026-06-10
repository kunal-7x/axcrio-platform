"use client";

// Survey Insights tab — renders the DETERMINISTIC rollups from core.survey_insights
// (NPS, CSAT avg, response count, promoter/passive/detractor split, per-question
// counts / numeric averages). NO metered call on this path. Built on KpiCard
// meters + the shared pill language; the LLM summary slot stays dormant until
// FORMS_INSIGHTS_LLM is enabled server-side (insights.llm_enabled).

import Icon from "@/components/Icon";
import KpiCard from "@/components/KpiCard";
import type { Insights, QuestionInsight } from "../client";
import { fieldTypeMeta } from "../_ui";

export default function InsightsPanel({
    insights,
    kind,
}: {
    insights: Insights;
    kind: string;
}) {
    const isSurvey = kind === "survey";
    const s = insights.sentiment || { promoter: 0, passive: 0, detractor: 0 };
    const sentTotal = s.promoter + s.passive + s.detractor;
    const responses = insights.responses || 0;

    if (responses === 0) {
        return (
            <div className="state-block py-16">
                <span className="state-glyph">
                    <Icon name="chart" className="fill-inherit" />
                </span>
                <div className="state-title">No responses yet</div>
                <div className="state-sub max-w-md">
                    {isSurvey
                        ? "Once people respond, this tab shows your NPS, CSAT and a per-question breakdown — all computed deterministically, no AI cost."
                        : "Insights light up as submissions arrive — a live per-question breakdown of every answer."}
                </div>
            </div>
        );
    }

    const questions = Object.entries(insights.questions || {});

    return (
        <div className="px-5 pb-5 max-lg:px-3">
            {/* Headline meters */}
            <div className="grid grid-cols-4 gap-3 mb-4 max-lg:grid-cols-2 max-sm:grid-cols-1">
                <KpiCard
                    label="Responses"
                    value={responses}
                    icon="list"
                    tone="info"
                    style={{ animationDelay: "0ms" }}
                />
                {isSurvey && (
                    <KpiCard
                        label="NPS"
                        value={insights.nps == null ? "—" : insights.nps}
                        icon="promote"
                        tone={
                            insights.nps == null
                                ? "neutral"
                                : insights.nps >= 0
                                ? "success"
                                : "danger"
                        }
                        sub={
                            insights.nps == null
                                ? "Add an NPS field"
                                : "−100 to +100 scale"
                        }
                        // NPS −100..100 mapped to a 0..1 meter
                        meter={
                            insights.nps == null
                                ? null
                                : (insights.nps + 100) / 200
                        }
                        style={{ animationDelay: "60ms" }}
                    />
                )}
                {isSurvey && (
                    <KpiCard
                        label="CSAT avg"
                        value={
                            insights.csat_avg == null
                                ? "—"
                                : insights.csat_avg.toFixed(2)
                        }
                        icon="heart"
                        tone="warning"
                        sub={
                            insights.csat_avg == null
                                ? "Add a CSAT field"
                                : "Average score"
                        }
                        style={{ animationDelay: "120ms" }}
                    />
                )}
                <KpiCard
                    label="Promoters"
                    value={sentTotal ? s.promoter : "—"}
                    icon="check-circle"
                    tone="success"
                    sub={
                        sentTotal
                            ? `${Math.round(
                                  (s.promoter / sentTotal) * 100
                              )}% of scored`
                            : "No scored responses"
                    }
                    meter={sentTotal ? s.promoter / sentTotal : null}
                    style={{ animationDelay: "180ms" }}
                />
            </div>

            {/* Sentiment split (surveys with scored responses) */}
            {isSurvey && sentTotal > 0 && (
                <div className="p-4 rounded-3xl border border-s-subtle bg-b-surface2 shadow-widget mb-4">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-button text-t-primary">
                            Sentiment split
                        </span>
                        <span className="text-caption text-t-tertiary">
                            {sentTotal} scored
                        </span>
                    </div>
                    <div className="flex h-3 rounded-full overflow-hidden bg-b-surface1 dark:bg-shade-04/60">
                        <Bar n={s.promoter} total={sentTotal} className="bg-primary-02" />
                        <Bar n={s.passive} total={sentTotal} className="bg-primary-05" />
                        <Bar n={s.detractor} total={sentTotal} className="bg-primary-03" />
                    </div>
                    <div className="flex items-center gap-5 mt-3 flex-wrap">
                        <Legend color="bg-primary-02" label="Promoters" n={s.promoter} />
                        <Legend color="bg-primary-05" label="Passives" n={s.passive} />
                        <Legend color="bg-primary-03" label="Detractors" n={s.detractor} />
                    </div>
                </div>
            )}

            {/* Per-question rollups */}
            <div className="text-button text-t-primary mb-3 px-1">
                Per-question breakdown
            </div>
            {questions.length === 0 ? (
                <div className="text-body-2 text-t-tertiary px-1">
                    No analysable questions on this form.
                </div>
            ) : (
                <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                    {questions.map(([key, q]) => (
                        <QuestionCard key={key} fieldKey={key} q={q} />
                    ))}
                </div>
            )}

            {/* LLM summary slot — dormant until enabled server-side */}
            {isSurvey && (
                <div className="mt-4 flex items-start gap-3 p-4 rounded-3xl border border-dashed border-s-stroke2 text-body-2 text-t-secondary">
                    <Icon
                        name="magic-pencil"
                        className="size-5 shrink-0 fill-t-tertiary mt-0.5"
                    />
                    <div>
                        <div className="text-button text-t-primary mb-0.5">
                            AI summary
                        </div>
                        {insights.llm_summary ? (
                            <p>{insights.llm_summary}</p>
                        ) : (
                            <p className="text-t-tertiary">
                                {insights.llm_enabled
                                    ? "No summary available for this response set yet."
                                    : "A natural-language summary of open-text feedback appears here once AI insights are enabled for your workspace."}
                            </p>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

function Bar({
    n,
    total,
    className,
}: {
    n: number;
    total: number;
    className: string;
}) {
    if (!n) return null;
    return (
        <div
            className={className}
            style={{ width: `${(n / total) * 100}%` }}
            title={`${n}`}
        />
    );
}

function Legend({
    color,
    label,
    n,
}: {
    color: string;
    label: string;
    n: number;
}) {
    return (
        <span className="flex items-center gap-1.5 text-caption text-t-secondary">
            <span className={`size-2.5 rounded-full ${color}`} />
            {label}
            <span className="td-num text-t-tertiary">{n}</span>
        </span>
    );
}

function QuestionCard({ fieldKey, q }: { fieldKey: string; q: QuestionInsight }) {
    const meta = fieldTypeMeta(q.type);
    const counts = q.counts ? Object.entries(q.counts) : [];
    const maxCount = counts.reduce((m, [, v]) => Math.max(m, v), 0);
    const isNumeric = q.avg != null || q.count != null;

    return (
        <div className="p-4 rounded-3xl border border-s-subtle bg-b-surface2 shadow-widget rise-in">
            <div className="flex items-center gap-2.5 mb-3">
                <span className="grid place-items-center size-8 shrink-0 rounded-full bg-b-surface1 fill-t-secondary dark:bg-shade-04/60">
                    <Icon name={meta.icon} className="size-4 fill-inherit" />
                </span>
                <div className="min-w-0">
                    <div className="text-button text-t-primary truncate">
                        {q.label || fieldKey}
                    </div>
                    <div className="text-caption text-t-tertiary">
                        {meta.label} · {q.answered} answered
                    </div>
                </div>
            </div>

            {isNumeric ? (
                <div className="flex items-baseline gap-2">
                    <span className="text-h4 td-num text-t-primary">
                        {q.avg == null ? "—" : q.avg}
                    </span>
                    <span className="text-caption text-t-tertiary">
                        avg · {q.count ?? 0} value
                        {(q.count ?? 0) === 1 ? "" : "s"}
                    </span>
                </div>
            ) : counts.length > 0 ? (
                <div className="flex flex-col gap-2">
                    {counts
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 8)
                        .map(([opt, n]) => (
                            <div key={opt}>
                                <div className="flex items-center justify-between text-caption mb-1">
                                    <span className="text-t-secondary truncate max-w-[70%]">
                                        {opt}
                                    </span>
                                    <span className="td-num text-t-tertiary">
                                        {n}
                                    </span>
                                </div>
                                <div className="meter">
                                    <div
                                        className="meter-fill bg-primary-01"
                                        style={{
                                            width: `${
                                                maxCount
                                                    ? (n / maxCount) * 100
                                                    : 0
                                            }%`,
                                        }}
                                    />
                                </div>
                            </div>
                        ))}
                </div>
            ) : (
                <div className="text-body-2 text-t-tertiary">
                    Free-text answers — see the Submissions tab.
                </div>
            )}
        </div>
    );
}
