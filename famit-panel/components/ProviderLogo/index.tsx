"use client";

// ProviderLogo — a single reusable vendor brand mark.
//
// Replaces the ad-hoc colour-blob placeholders that stood in for vendor logos
// (ElevenLabs / Sarvam / Vobiz / Groq / SambaNova / OpenRouter …). The REAL
// brand mark ships as a static SVG under /public/vendors/<slug>.svg and is
// rendered with a plain <img> (no next/image host allow-listing, no runtime
// sharp — the build ships images.unoptimized so the .svg is pure-static and
// Linux-portable). The SVGs use `currentColor`, so the brand-accent class on
// the wrapper tints them and they stay dark-mode safe. If the file is missing
// the inline <Mark/> geometry is the fallback so a logo never blanks out.
//
// Unknown providers fall back to a tidy monogram chip (first letter on the
// surface token) — never a raw coloured blob.

import { useState } from "react";

type ProviderLogoProps = {
    /** provider slug/name — case-insensitive, spaces/underscores tolerated */
    provider: string;
    className?: string;
    /** chip size in px (square). default 36 */
    size?: number;
    /** render the bare glyph without the surface chip */
    bare?: boolean;
};

// Normalise "Eleven Labs", "elevenlabs", "ELEVEN_LABS" -> "elevenlabs".
function slug(p: string): string {
    return (p || "").toLowerCase().replace(/[\s_-]+/g, "");
}

// Providers that have a REAL brand SVG shipped under /public/vendors/<slug>.svg.
// Aliases (e.g. "11labs") normalise to the canonical file slug.
const SVG_ALIAS: Record<string, string> = {
    elevenlabs: "elevenlabs",
    "11labs": "elevenlabs",
    eleven: "elevenlabs",
    groq: "groq",
    sarvam: "sarvam",
    sarvamai: "sarvam",
    vobiz: "vobiz",
    sambanova: "sambanova",
    openrouter: "openrouter",
};

// Brand marks. Kept compact + monochromatic-friendly; brand hue only where it
// reads as the logo, otherwise currentColor so it inherits the chip foreground.
function Mark({ id, size }: { id: string; size: number }) {
    const common = { width: size, height: size, viewBox: "0 0 24 24", "aria-hidden": true } as const;
    switch (id) {
        case "elevenlabs":
            // ElevenLabs — the two-bar "ll" mark.
            return (
                <svg {...common} className="fill-current">
                    <rect x="7" y="4" width="3.4" height="16" rx="1.2" />
                    <rect x="13.6" y="4" width="3.4" height="16" rx="1.2" />
                </svg>
            );
        case "groq":
            // Groq — rounded "Q" ring with a tail.
            return (
                <svg {...common} className="fill-none stroke-current" strokeWidth="2.2">
                    <circle cx="12" cy="11" r="6.2" />
                    <line x1="15" y1="14.5" x2="18.5" y2="18.5" strokeLinecap="round" />
                </svg>
            );
        case "sarvam":
            // Sarvam — concentric speech rings (STT/speech).
            return (
                <svg {...common} className="fill-none stroke-current" strokeWidth="2" strokeLinecap="round">
                    <path d="M12 7v10" />
                    <path d="M8 9v6" />
                    <path d="M16 9v6" />
                    <path d="M4.5 11v2" />
                    <path d="M19.5 11v2" />
                </svg>
            );
        case "vobiz":
            // Vobiz — telephony handset.
            return (
                <svg {...common} className="fill-current">
                    <path d="M6.6 3.8c.6-.3 1.4-.1 1.8.5l1.4 2.2c.3.5.2 1.1-.2 1.5l-1 1c-.2.2-.2.4-.1.6.7 1.5 1.9 2.7 3.4 3.4.2.1.5 0 .6-.1l1-1c.4-.4 1-.5 1.5-.2l2.2 1.4c.6.4.8 1.2.5 1.8l-.8 1.6c-.4.8-1.3 1.2-2.2 1C9.9 17.6 6.4 14.1 5 9.4c-.2-.9.2-1.8 1-2.2l.6-.3z" />
                </svg>
            );
        case "sambanova":
            // SambaNova — stacked chevrons.
            return (
                <svg {...common} className="fill-none stroke-current" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M6 8l6 4 6-4" />
                    <path d="M6 13l6 4 6-4" />
                </svg>
            );
        case "openrouter":
            // OpenRouter — routing nodes.
            return (
                <svg {...common} className="fill-current">
                    <circle cx="5" cy="12" r="2.2" />
                    <circle cx="19" cy="6.5" r="2.2" />
                    <circle cx="19" cy="17.5" r="2.2" />
                    <path d="M6.8 11l9-3.6M6.8 13l9 3.6" className="stroke-current" strokeWidth="1.6" fill="none" />
                </svg>
            );
        default:
            return null;
    }
}

// Brand accent (used for the bare-glyph foreground so the mark reads as the logo).
const ACCENT: Record<string, string> = {
    elevenlabs: "text-t-primary",
    groq: "text-[#F55036]",
    sarvam: "text-[#1F7AE0]",
    vobiz: "text-primary-02",
    sambanova: "text-[#6C4DF6]",
    openrouter: "text-t-primary",
};

const ProviderLogo = ({ provider, className, size = 36, bare }: ProviderLogoProps) => {
    const id = slug(provider);
    const fileSlug = SVG_ALIAS[id];
    const glyphSize = Math.round(size * 0.56);
    const accent = ACCENT[fileSlug ?? id] || "text-t-secondary";
    const hasMark = (fileSlug ?? id) in ACCENT;

    // If a real brand SVG exists, render it (tinted via currentColor by `accent`),
    // and fall back to the inline <Mark/> only if the file fails to load.
    const [imgFailed, setImgFailed] = useState(false);

    const glyph = fileSlug && !imgFailed ? (
        <span className={`inline-grid place-items-center ${accent}`}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
                src={`/vendors/${fileSlug}.svg`}
                alt={`${provider} logo`}
                width={glyphSize}
                height={glyphSize}
                onError={() => setImgFailed(true)}
                style={{ width: glyphSize, height: glyphSize }}
            />
        </span>
    ) : hasMark ? (
        <span className={accent}>
            <Mark id={fileSlug ?? id} size={glyphSize} />
        </span>
    ) : (
        // tidy monogram fallback — never a raw colour blob
        <span className="text-button font-semibold text-t-secondary uppercase">
            {(provider || "?").trim().charAt(0) || "?"}
        </span>
    );

    if (bare) return glyph;

    return (
        <span
            className={`grid place-items-center shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle ${className || ""}`}
            style={{ width: size, height: size }}
            title={provider}
        >
            {glyph}
        </span>
    );
};

export default ProviderLogo;
