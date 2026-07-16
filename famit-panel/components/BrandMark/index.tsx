// BrandMark — a premium logo tile showing the REAL, full-colour company logo.
//
// One consistent treatment for Auto Lead sources AND Money/billing vendors: the
// actual brand SVG (full colour) centred on a clean white "app-icon" tile with a
// soft shadow + hairline ring. Generic, non-brand sources show a tidy neutral
// glyph; unknown brands fall back to a clean monogram. Add a brand by dropping its
// SVG/PNG in /public/images/brands (or /vendors) + one line in BRAND_IMG.

import Icon from "@/components/Icon";

// normalised slug -> real logo asset (full colour).
const BRAND_IMG: Record<string, string> = {
    // Auto Lead sources
    meta: "/images/brands/meta.svg",
    googleads: "/images/brands/google-ads.svg",
    whatsapp: "/images/brands/whatsapp.svg",
    zapier: "/images/brands/zapier.svg",
    apollo: "/images/brands/apollo.svg",
    gmail: "/images/brands/gmail.svg",
    // Money / billing vendors
    groq: "/images/brands/groq.svg",
    openrouter: "/images/brands/openrouter.svg",
    elevenlabs: "/images/vendors/elevenlabs.svg",
    livekit: "/images/vendors/livekit.svg",
    sarvam: "/images/vendors/sarvam.png",
    sambanova: "/images/vendors/sambanova.png",
};

function normalize(name?: string): string {
    return (name || "").toLowerCase().replace(/[\s_-]+/g, "");
}

/** Whether a brand has a real logo asset (callers can branch on it). */
export function hasBrandMark(name?: string): boolean {
    return !!BRAND_IMG[normalize(name)];
}

type BrandMarkProps = {
    /** brand/vendor/source slug — resolves to a real logo, else a monogram */
    name?: string;
    /** fallback registry glyph for generic (non-brand) sources */
    icon?: string;
    /** label used for the monogram fallback (first letter) */
    label?: string;
    /** tile size in tailwind units (×0.25rem). default 14 = 56px */
    size?: number;
    /** "squircle" (rounded-2xl, default) or "circle" */
    shape?: "squircle" | "circle";
    /** render only the glyph (no tile) */
    bare?: boolean;
    className?: string;
};

const BrandMark = ({ name, icon, label, size = 14, shape = "squircle", bare, className }: BrandMarkProps) => {
    const dim = `${size * 0.25}rem`;
    const glyph = `${size * 0.25 * 0.6}rem`;
    const src = BRAND_IMG[normalize(name)];

    const inner = src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={label || name || ""} style={{ width: glyph, height: glyph }} className="object-contain" />
    ) : icon ? (
        <span style={{ width: glyph, height: glyph }} className="grid place-items-center [&_svg]:!w-full [&_svg]:!h-full">
            <Icon name={icon} fill="#5B6473" />
        </span>
    ) : (
        <span className="font-semibold uppercase" style={{ color: "#5B6473", fontSize: `calc(${dim} * 0.4)` }}>
            {(label || name || "?").trim().charAt(0) || "?"}
        </span>
    );

    if (bare) return inner;

    return (
        <span
            className={`grid place-items-center shrink-0 overflow-hidden bg-white ring-1 ring-black/[0.06] shadow-[0_1px_2px_rgba(16,24,40,0.06),0_6px_16px_-6px_rgba(16,24,40,0.18)] ${
                shape === "circle" ? "rounded-full" : "rounded-2xl"
            } ${className || ""}`}
            style={{ width: dim, height: dim }}
            title={label || name}
        >
            {inner}
        </span>
    );
};

export default BrandMark;
