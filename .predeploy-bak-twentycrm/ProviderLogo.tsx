// ProviderLogo — the REAL vendor brand logo (not a colour box).
//
// Each mark is the actual company logo saved under /public/images/vendors
// (official simple-icons SVG where available, else the brand favicon). They
// render on a consistent light chip so both colour and black logos stay legible
// in light AND dark themes — the way a vendor row should look. Unknown vendors
// fall back to a clean monogram chip (never a raw colour blob).

type ProviderLogoProps = {
    /** provider slug/name — case-insensitive, spaces/underscores tolerated */
    provider: string;
    className?: string;
    /** chip size in px (square). default 36 */
    size?: number;
    /** render the bare logo without the surface chip */
    bare?: boolean;
};

// Normalise "Eleven Labs", "elevenlabs", "ELEVEN_LABS" -> "elevenlabs".
function slug(p: string): string {
    return (p || "").toLowerCase().replace(/[\s_-]+/g, "");
}

// Real brand assets. Add a file under /public/images/vendors + a line here to
// onboard a new vendor logo.
const LOGO: Record<string, string> = {
    elevenlabs: "/images/vendors/elevenlabs.svg",
    groq: "/images/vendors/groq.png",
    livekit: "/images/vendors/livekit.svg",
    openrouter: "/images/vendors/openrouter.svg",
    sarvam: "/images/vendors/sarvam.png",
    sambanova: "/images/vendors/sambanova.png",
};

const ProviderLogo = ({ provider, className, size = 36, bare }: ProviderLogoProps) => {
    const id = slug(provider);
    const src = LOGO[id];
    const glyph = Math.round(size * 0.62);

    const inner = src ? (
        // plain <img>: local /public asset (incl. SVG) — no next/image host
        // allow-listing or dangerouslyAllowSVG needed.
        // eslint-disable-next-line @next/next/no-img-element
        <img
            src={src}
            alt={provider}
            width={glyph}
            height={glyph}
            style={{ width: glyph, height: glyph }}
            className="object-contain"
        />
    ) : (
        // tidy monogram fallback — never a raw colour blob
        <span className="text-button font-semibold text-t-secondary uppercase">
            {(provider || "?").trim().charAt(0) || "?"}
        </span>
    );

    if (bare) return inner;

    return (
        <span
            className={`grid place-items-center shrink-0 rounded-xl bg-white ring-1 ring-s-subtle overflow-hidden ${className || ""}`}
            style={{ width: size, height: size }}
            title={provider}
        >
            {inner}
        </span>
    );
};

export default ProviderLogo;
