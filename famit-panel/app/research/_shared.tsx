"use client";

// Famit Research — shared honesty/method UI. The credibility moat is intellectual honesty made
// visible: a demo badge when the data is synthetic, in-product citations to the published methods,
// and an explicit "one weak modality, not ground truth" note. More convincing to a sophisticated
// buyer than a confident fake "stress score".

export function DemoPill({ demo, enabled }: { demo?: boolean; enabled?: boolean }) {
    if (!demo)
        return (
            <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
                style={{ background: "color-mix(in srgb, var(--chart-green) 16%, transparent)", color: "var(--text-secondary)" }}>
                <span className="size-1.5 rounded-full" style={{ background: "var(--chart-green)" }} />
                Live data
            </span>
        );
    return (
        <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium"
            style={{ background: "color-mix(in srgb, var(--primary-05) 45%, transparent)", color: "var(--text-secondary)" }}
            title={
                enabled === false
                    ? "FAMIT_RESEARCH_ENABLED is off and/or no calls have been analysed yet. Showing the real affect filter run over scripted archetype calls — sample data, clearly labelled, not a live tenant's numbers."
                    : "No analysed calls in range yet — showing sample data (the real filter over scripted archetype calls)."
            }>
            <span className="size-1.5 rounded-full" style={{ background: "var(--primary-01)" }} />
            Sample data
        </span>
    );
}

export function MethodNote({ children }: { children?: React.ReactNode }) {
    return (
        <div className="rounded-2xl border p-4 text-caption leading-relaxed text-t-secondary"
            style={{ borderColor: "var(--stroke-stroke2)", background: "var(--backgrounds-surface3)" }}>
            {children}
        </div>
    );
}

export function Citations() {
    const items = [
        { t: "Online affect tracking · Kalman filter", s: "Somandepalli et al., AVEC-2016" },
        { t: "Acoustic feature set · eGeMAPS", s: "Eyben et al. / openSMILE" },
        { t: "Speech-rate · syllable nuclei", s: "de Jong & Wempe, 2009" },
        { t: "Mean-reversion dynamics · Ornstein-Uhlenbeck", s: "leaky-integrator (EWMA)" },
    ];
    return (
        <div className="flex flex-wrap gap-2">
            {items.map((i) => (
                <span key={i.t} className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px]"
                    style={{ background: "var(--backgrounds-surface3)", color: "var(--text-tertiary)" }}>
                    <span style={{ color: "var(--text-secondary)" }}>{i.t}</span>
                    <span>· {i.s}</span>
                </span>
            ))}
        </div>
    );
}

export function fmtTrend(v: number): { text: string; color: string } {
    const r = Math.round(v * 10) / 10;
    if (r > 0.5) return { text: `▲ +${r}`, color: "var(--chart-green)" };
    if (r < -0.5) return { text: `▼ ${r}`, color: "var(--primary-03)" };
    return { text: `→ ${r}`, color: "var(--text-tertiary)" };
}

export function OutcomeBadge({
    outcome,
    converted,
    has_outcome,
}: {
    outcome: string;
    converted: boolean | number;
    has_outcome?: boolean | number;
}) {
    const won = converted === true || converted === 1;
    // outcome-unknown (has_outcome explicitly 0/false) is NOT a loss — show it as Pending, never as a
    // lost call (the backend persists unknown as converted=0, so the UI must distinguish them).
    const pending = has_outcome === false || has_outcome === 0;
    const color = won ? "var(--chart-green)" : pending ? "var(--primary-04)" : outcome === "warm" ? "var(--primary-05)" : "var(--primary-04)";
    return (
        <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium capitalize"
            style={{ background: `color-mix(in srgb, ${color} 18%, transparent)`, color: "var(--text-secondary)" }}>
            <span className="size-1.5 rounded-full" style={{ background: color }} />
            {won ? "Won" : pending ? "Pending" : outcome || "open"}
        </span>
    );
}
