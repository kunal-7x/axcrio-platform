// ProviderLogo — premium monochrome vendor mark (real logo where available).
//
// Delegates to the shared <BrandMark> so Money/billing matches Auto Lead: the real
// company logo as a single-colour (foreground) mark on a neutral squircle, with a
// clean monogram for vendors that have no vector mark (never a colour blob). To
// onboard a vendor's real logo, add its monochrome SVG path to BRAND_PATHS in
// components/BrandMark.
import BrandMark from "@/components/BrandMark";

type ProviderLogoProps = {
    /** provider slug/name — case-insensitive, spaces/underscores tolerated */
    provider: string;
    className?: string;
    /** chip size in px (square). default 36 */
    size?: number;
    /** render the bare logo without the surface chip */
    bare?: boolean;
};

const ProviderLogo = ({ provider, className, size = 36, bare }: ProviderLogoProps) => (
    // BrandMark size is in tailwind units (×0.25rem = 4px), so px → units = size/4.
    <BrandMark name={provider} label={provider} size={size / 4} bare={bare} className={className} />
);

export default ProviderLogo;
