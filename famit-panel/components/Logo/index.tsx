import Link from "next/link";
import Image from "next/image";

type LogoProps = {
    className?: string;
};

// The Famit wordmark (premium-ui foundation wave).
// The founder's REAL brand mark (transparent white-ink PNG) on the always-dark
// bg-shade-01 tile, plus the token wordmark. Replaces the placeholder signal
// (eq-bar) glyph. The mark is white-on-dark so it stays crisp in light + dark.
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
                <Image
                    src="/images/famit-mark-white-trim.png"
                    alt=""
                    width={22}
                    height={22}
                    className="relative object-contain"
                    priority
                />
            </span>
            <span className="wordmark">
                Famit
                <span className="size-1.5 rounded-full bg-primary-01 -ml-0.5 mb-3 shadow-[0_0_8px_0_var(--primary-01)]" />
            </span>
        </Link>
    );
};

export default Logo;
