// Token-based semantic pill (feat/premium-ui). Replaces the per-page
// hand-rolled bg-green-100 badges with one consistent component built on
// the .pill-* utilities in globals.css. Additive — no existing API touched.

export type BadgeVariant =
    | "success"
    | "danger"
    | "warning"
    | "info"
    | "neutral";

type BadgeProps = {
    variant?: BadgeVariant;
    children: React.ReactNode;
    dot?: boolean;
    className?: string;
};

const VARIANT_CLASS: Record<BadgeVariant, string> = {
    success: "pill-success",
    danger: "pill-danger",
    warning: "pill-warning",
    info: "pill-info",
    neutral: "pill-neutral",
};

const Badge = ({ variant = "neutral", children, dot, className }: BadgeProps) => (
    <span className={`pill ${VARIANT_CLASS[variant]} ${className || ""}`}>
        {dot && <span className="pill-dot" />}
        {children}
    </span>
);

export default Badge;
