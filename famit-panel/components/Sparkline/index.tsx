// Tiny inline sparkline (feat/premium-ui). Pure SVG, no recharts — keeps KPI
// cards crisp and dependency-free. Renders a smooth area+line from a numeric
// series. Used only with REAL data (e.g. Stats.series); never fabricated.

type SparklineProps = {
    data: number[];
    className?: string;
    width?: number;
    height?: number;
    color?: string; // CSS color / var; defaults to the brand green
    strokeWidth?: number;
};

const Sparkline = ({
    data,
    className,
    width = 120,
    height = 36,
    color = "var(--chart-green)",
    strokeWidth = 1.75,
}: SparklineProps) => {
    if (!data || data.length === 0) return null;
    // A single point can't draw a line — render a flat baseline dot.
    const pad = strokeWidth;
    const w = width;
    const h = height;
    const max = Math.max(...data);
    const min = Math.min(...data);
    const range = max - min || 1;
    const n = data.length;
    const x = (i: number) =>
        n === 1 ? w / 2 : pad + (i * (w - pad * 2)) / (n - 1);
    const y = (v: number) => h - pad - ((v - min) / range) * (h - pad * 2);

    const linePts = data.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    const areaPts = `${x(0)},${h} ${linePts} ${x(n - 1)},${h}`;
    const gradId = `spark-grad-${Math.round(width)}-${n}-${Math.round(max)}`;

    return (
        <svg
            className={className}
            width={w}
            height={h}
            viewBox={`0 0 ${w} ${h}`}
            fill="none"
            preserveAspectRatio="none"
            aria-hidden
        >
            <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity="0.18" />
                    <stop offset="100%" stopColor={color} stopOpacity="0" />
                </linearGradient>
            </defs>
            <polygon points={areaPts} fill={`url(#${gradId})`} />
            <polyline
                points={linePts}
                fill="none"
                stroke={color}
                strokeWidth={strokeWidth}
                strokeLinejoin="round"
                strokeLinecap="round"
            />
        </svg>
    );
};

export default Sparkline;
