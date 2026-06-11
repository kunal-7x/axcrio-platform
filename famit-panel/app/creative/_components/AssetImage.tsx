"use client";

/**
 * AssetImage — the ONE browser-loadable preview for every creative asset.
 *
 * WHY a native <img> and not <Image> (next/image): the AI Asset Service now hands
 * the panel a PRESIGNED DigitalOcean Spaces GET URL (24h, the bucket stays
 * private) in the asset's `url`/`thumb_url`. next/image validates the remote
 * hostname against `images.remotePatterns` in next.config — an un-listed host
 * (capsy-recordings.sgp1.digitaloceanspaces.com) makes it THROW and the preview
 * never renders (the "broken-image icon + empty space" the founder saw). A plain
 * <img> loads any URL the browser can fetch — exactly what a presigned URL is —
 * and lets us own a graceful onError placeholder. The presigned URL needs no auth
 * header, so an <img src> renders it directly (the old `/raw` proxy needed
 * X-Auth, which an <img> can't send → 401 → broken image).
 *
 * Behaviour: a token shimmer while loading, the image fades in on load, and a
 * calm camera-glyph placeholder if the URL fails (expired signature / network).
 * Token-pure (reuses the `.skeleton` shimmer + Icon), fills its positioned parent
 * (`fill`), object-cover. Drop-in for the asset <Image fill> sites.
 */

import { useEffect, useState } from "react";
import Icon from "@/components/Icon";

type AssetImageProps = {
    /** the browser-loadable (presigned) URL; falsy → placeholder immediately */
    src?: string | null;
    alt?: string;
    className?: string;
    /** rounding to match the slot (cards use rounded-3xl, strips rounded-2xl) */
    rounded?: string;
};

const AssetImage = ({
    src,
    alt = "Creative asset",
    className = "",
    rounded = "rounded-3xl",
}: AssetImageProps) => {
    const [loaded, setLoaded] = useState(false);
    const [failed, setFailed] = useState(false);

    // reset the load/fail state whenever the source changes (e.g. a new version,
    // a refreshed presigned URL) so a previously-failed slot can recover.
    useEffect(() => {
        setLoaded(false);
        setFailed(false);
    }, [src]);

    const showPlaceholder = !src || failed;

    if (showPlaceholder) {
        return (
            <div
                className={`absolute inset-0 flex items-center justify-center ${rounded} bg-b-surface1 fill-t-tertiary dark:bg-shade-04/40 ${className}`}
            >
                <Icon name="camera-stroke" />
            </div>
        );
    }

    return (
        <>
            {/* shimmer placeholder under the image until it has loaded */}
            {!loaded && (
                <div className={`absolute inset-0 skeleton ${rounded}`} aria-hidden />
            )}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
                src={src}
                alt={alt}
                className={`absolute inset-0 size-full object-cover ${rounded} transition-opacity duration-300 ${
                    loaded ? "opacity-100" : "opacity-0"
                } ${className}`}
                loading="lazy"
                decoding="async"
                onLoad={() => setLoaded(true)}
                onError={() => setFailed(true)}
            />
        </>
    );
};

export default AssetImage;
