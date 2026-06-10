import Link from "next/link";

type LogoProps = {
    className?: string;
};

// The Famit wordmark (premium-ui wave 2 — "Signal").
// A real, token-based wordmark + the brand-blue signal glyph (3 animated
// equalizer bars) — the panel's signature, replacing the generic PNG mark.
// Fully token-driven so it renders correctly in light + dark mode.
const Logo = ({ className }: LogoProps) => {
    return (
        <Link
            className={`group flex items-center gap-2.5 w-fit ${className || ""}`}
            href="/"
            aria-label="Famit"
        >
            <span
                className="relative flex items-center justify-center size-9 shrink-0 rounded-[0.7rem] bg-shade-01 overflow-hidden
                    shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08)] ring-1 ring-s-subtle dark:ring-shade-04"
            >
                <span className="absolute inset-0 brand-glow opacity-60" aria-hidden />
                <span className="signal-glyph relative" aria-hidden>
                    <i />
                    <i />
                    <i />
                    <i />
                </span>
            </span>
            <span className="wordmark">
                Famit
                <span className="size-1.5 rounded-full bg-primary-01 -ml-0.5 mb-3 shadow-[0_0_8px_0_var(--primary-01)]" />
            </span>
        </Link>
    );
};

export default Logo;
