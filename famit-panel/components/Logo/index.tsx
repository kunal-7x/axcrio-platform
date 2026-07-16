import Link from "next/link";

type LogoProps = {
    className?: string;
};

// Haptica AI brand mark — a MONOCHROME "split-stripe" disc (left = vertical bars,
// right = horizontal bars), drawn as inline SVG so it scales, stays crisp, and
// uses currentColor (no raster, no multicolor — core design-system aligned).
// "by Famit" sits small under the Haptica AI wordmark.
export function HapticMark({ className }: { className?: string }) {
    return (
        <svg viewBox="0 0 64 64" className={className} role="img" aria-label="Haptica AI">
            <defs>
                <clipPath id="haptic-disc">
                    <circle cx="32" cy="32" r="30" />
                </clipPath>
            </defs>
            <g clipPath="url(#haptic-disc)" fill="currentColor">
                {/* left — vertical bars */}
                <rect x="10.5" y="0" width="6" height="64" />
                <rect x="20.5" y="0" width="8.5" height="64" />
                {/* right — horizontal bars */}
                <rect x="33" y="6" width="31" height="6" />
                <rect x="33" y="18" width="31" height="6" />
                <rect x="33" y="30" width="31" height="6" />
                <rect x="33" y="42" width="31" height="6" />
                <rect x="33" y="54" width="31" height="6" />
            </g>
        </svg>
    );
}

const Logo = ({ className }: LogoProps) => {
    return (
        <Link
            className={`group flex items-center gap-2.5 w-fit ${className || ""}`}
            href="/"
            aria-label="Haptica AI by Famit"
        >
            <span
                className="relative flex items-center justify-center size-9 shrink-0 rounded-[0.7rem] bg-shade-01 overflow-hidden
                    shadow-[inset_0_1px_0_0_rgba(255,255,255,0.08)] ring-1 ring-s-subtle dark:ring-shade-04"
            >
                <HapticMark className="size-5 text-white" />
            </span>
            <span className="flex flex-col leading-none">
                <span className="text-h6 font-semibold tracking-[-0.02em] text-t-primary">
                    Haptica AI
                </span>
                <span className="mt-1 text-[0.625rem] font-medium uppercase tracking-[0.14em] text-t-tertiary">
                    by Famit
                </span>
            </span>
        </Link>
    );
};

export default Logo;
