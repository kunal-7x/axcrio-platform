"use client";

/**
 * AssetMedia (W9) — the ONE browser-loadable preview for BOTH images and videos.
 *
 * The superset of AssetImage: it renders the existing presigned `<img>` for image
 * assets, and a `<video>` for video assets — same graceful shimmer + onError, same
 * `fill`/object-cover slot. AssetImage stays for image-only callers; this is the
 * media-aware drop-in the AssetCard / AssetDetail use so a video tile renders where
 * an image one did.
 *
 * ⚡ EGRESS DISCIPLINE (master plan §10b / R4): in the GRID a video must NOT fetch
 * its bytes — it shows the PRESIGNED POSTER frame only, with a play affordance,
 * `preload="none"`. Bytes are fetched on demand (hover-preview or the detail
 * drawer, where `controls`/`autoPlay` are explicit). A wall of autoplaying clips
 * would blow the egress bill (egress is 60–90% of the cost).
 *
 * The play overlay is a CSS triangle (the Icon set has no `play` glyph). Token-pure,
 * dark-mode + prefers-reduced-motion safe.
 */

import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";

type AssetMediaProps = {
    /** the browser-loadable (presigned) media URL (image src OR video src) */
    src?: string | null;
    /** for video: the presigned poster frame shown in the grid (no byte fetch) */
    poster?: string | null;
    isVideo?: boolean;
    alt?: string;
    className?: string;
    rounded?: string;
    /** grid mode = poster-only + play badge (egress-safe). detail mode = real player. */
    mode?: "grid" | "player";
    /** detail player: show controls. */
    controls?: boolean;
    /** duration pill text ("0:06") — rendered bottom-right over the poster. */
    durationLabel?: string;
    /** speaker chip when the video carries a voiceover. */
    withAudio?: boolean;
};

const AssetMedia = ({
    src,
    poster,
    isVideo = false,
    alt = "Creative asset",
    className = "",
    rounded = "rounded-3xl",
    mode = "grid",
    controls = false,
    durationLabel,
    withAudio,
}: AssetMediaProps) => {
    const [loaded, setLoaded] = useState(false);
    const [failed, setFailed] = useState(false);
    const [hoverPlay, setHoverPlay] = useState(false);
    const videoRef = useRef<HTMLVideoElement | null>(null);

    useEffect(() => {
        setLoaded(false);
        setFailed(false);
        setHoverPlay(false);
    }, [src, poster]);

    const showPlaceholder = (!src && !poster) || failed;

    // ---- placeholder (no URL / load failed) ----
    if (showPlaceholder) {
        return (
            <div
                className={`absolute inset-0 flex items-center justify-center ${rounded} bg-b-surface1 fill-t-tertiary dark:bg-shade-04/40 ${className}`}
            >
                <Icon name={isVideo ? "camera-video" : "camera-stroke"} />
            </div>
        );
    }

    // ---- VIDEO ----
    if (isVideo) {
        // GRID: poster-only + a play badge. Hover loads + plays muted preview (one
        // clip at a time; the user's hover is the explicit intent, not a wall).
        if (mode === "grid") {
            return (
                <div
                    className={`absolute inset-0 ${rounded} overflow-hidden bg-b-surface1 dark:bg-shade-04/40 ${className}`}
                    onMouseEnter={() => setHoverPlay(true)}
                    onMouseLeave={() => {
                        setHoverPlay(false);
                        videoRef.current?.pause();
                    }}
                >
                    {/* shimmer until poster loads */}
                    {!loaded && !hoverPlay && <div className={`absolute inset-0 skeleton ${rounded}`} aria-hidden />}
                    {/* the poster frame (no byte fetch of the clip) */}
                    {poster && !hoverPlay && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                            src={poster}
                            alt={alt}
                            className={`absolute inset-0 size-full object-cover transition-opacity duration-300 ${
                                loaded ? "opacity-100" : "opacity-0"
                            }`}
                            loading="lazy"
                            decoding="async"
                            onLoad={() => setLoaded(true)}
                            onError={() => setFailed(true)}
                        />
                    )}
                    {/* hover preview — only this card fetches bytes, muted, looped */}
                    {hoverPlay && src && (
                        <video
                            ref={videoRef}
                            src={src}
                            poster={poster || undefined}
                            className="absolute inset-0 size-full object-cover"
                            muted
                            loop
                            autoPlay
                            playsInline
                            preload="none"
                            onError={() => setFailed(true)}
                        />
                    )}
                    {/* play badge (CSS triangle — no `play` glyph in the set) */}
                    {!hoverPlay && (
                        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                            <span className="flex items-center justify-center size-12 rounded-full bg-b-surface2/85 shadow-depth backdrop-blur-sm transition-transform group-hover:scale-110">
                                <span className="play-tri" aria-hidden />
                            </span>
                        </div>
                    )}
                    {/* duration pill + audio chip */}
                    <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5 pointer-events-none">
                        {withAudio && (
                            <span className="flex items-center justify-center size-6 rounded-full bg-b-surface2/85 fill-t-secondary backdrop-blur-sm">
                                <Icon className="!size-3.5" name="camera-video" />
                            </span>
                        )}
                        {durationLabel && (
                            <span className="px-2 py-0.5 rounded-full bg-b-surface2/85 text-caption text-t-primary backdrop-blur-sm tabular-nums">
                                {durationLabel}
                            </span>
                        )}
                    </div>
                </div>
            );
        }

        // PLAYER (detail drawer): a real <video controls>, bytes fetched on open.
        return (
            <video
                ref={videoRef}
                src={src || undefined}
                poster={poster || undefined}
                className={`absolute inset-0 size-full object-contain bg-shade-09/5 dark:bg-shade-01/40 ${rounded} ${className}`}
                controls={controls}
                playsInline
                preload="metadata"
                onError={() => setFailed(true)}
            />
        );
    }

    // ---- IMAGE (the original AssetImage path) ----
    return (
        <>
            {!loaded && <div className={`absolute inset-0 skeleton ${rounded}`} aria-hidden />}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
                src={src || poster || undefined}
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

export default AssetMedia;
