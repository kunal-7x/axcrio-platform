"use client";
// Self-contained inline icon set for the Brainwave studio shell (Lucide-style,
// 24x24 stroke). Decoupled from haptica's token-styled Icon component.
import { SVGProps } from "react";

const P = (d: string) => d;

const PATHS: Record<string, string[]> = {
    cube: [P("M21 7.5 12 2 3 7.5v9L12 22l9-5.5v-9Z"), P("M3 7.5 12 13l9-5.5"), P("M12 13v9")],
    sparkle: [
        P("M12 3v4M12 17v4M3 12h4M17 12h4"),
        P("M12 8.5a3.5 3.5 0 0 0 3.5 3.5A3.5 3.5 0 0 0 12 15.5 3.5 3.5 0 0 0 8.5 12 3.5 3.5 0 0 0 12 8.5Z"),
    ],
    upload: [P("M12 16V4"), P("m7 9 5-5 5 5"), P("M5 20h14")],
    arrow: [P("M5 12h14"), P("m13 6 6 6-6 6")],
    layers: [P("m12 3 9 5-9 5-9-5 9-5Z"), P("m3 13 9 5 9-5"), P("M3 18l9 5 9-5")],
    trash: [P("M4 7h16"), P("M9 7V5h6v2"), P("M6 7l1 13h10l1-13"), P("M10 11v6M14 11v6")],
    share: [
        P("M16 6l-4-4-4 4"),
        P("M12 2v13"),
        P("M5 13H4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5a2 2 0 0 0-2-2h-1"),
    ],
    link: [
        P("M9 12a4 4 0 0 0 4 4h2a4 4 0 0 0 0-8h-1"),
        P("M15 12a4 4 0 0 0-4-4H9a4 4 0 0 0 0 8h1"),
    ],
    copy: [P("M9 9h10v10H9z"), P("M5 15H4V4h11v1")],
    check: [P("m5 12 5 5 9-11")],
    image: [P("M3 5h18v14H3z"), P("M8 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"), P("m3 17 5-5 4 4 3-3 6 6")],
    x: [P("M6 6l12 12M18 6 6 18")],
    download: [P("M12 4v10"), P("m8 11 4 4 4-4"), P("M5 19h14")],
    spinner: [P("M12 3a9 9 0 1 0 9 9")],
    bed: [P("M3 10V6M3 18v-4h18v4M3 14h18v-2a3 3 0 0 0-3-3H9a3 3 0 0 0-3 3v0"), P("M21 14v4")],
    home: [P("m3 11 9-7 9 7"), P("M5 10v10h14V10"), P("M10 20v-6h4v6")],
    grid: [P("M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z")],
    cursor: [P("m4 3 7.5 18 2.4-7.1L21 11.5z")],
    hand: [P("M6 9 3 12l3 3"), P("M18 9l3 3-3 3"), P("M9 6l3-3 3 3"), P("M9 18l3 3 3-3"), P("M3 12h18"), P("M12 3v18")],
    play: [P("m7 4 13 8-13 8z")],
    sun: [P("M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z"), P("M12 2v2M12 20v2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M18.4 5.6l1.4-1.4M4.2 19.8l1.4-1.4")],
    moon: [P("M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8Z")],
    camera: [P("M3 8h3l2-2.5h8L18 8h3v12H3z"), P("M12 17a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z")],
    walk: [P("M13 5a1.6 1.6 0 1 0 0-3.2A1.6 1.6 0 0 0 13 5Z"), P("M11 8l4 1.5 2.5 3"), P("M11 8l-2.5 3.5L11 14l1 7"), P("M12 14l-3 7")],
    eye: [P("M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z"), P("M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z")],
    plus: [P("M12 5v14M5 12h14")],
    minus: [P("M5 12h14")],
    mic: [P("M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z"), P("M5 11a7 7 0 0 0 14 0"), P("M12 18v3")],
    sliders: [P("M4 7h9M17 7h3"), P("M4 17h3M11 17h9"), P("M14 4v6M8 14v6")],
    frame: [P("M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5")],
    flash: [P("M13 2 4 14h6l-1 8 9-12h-6z")],
};

export default function Ico({
    name,
    size = 18,
    className,
    ...rest
}: { name: string; size?: number } & SVGProps<SVGSVGElement>) {
    const paths = PATHS[name] || [];
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.7}
            strokeLinecap="round"
            strokeLinejoin="round"
            className={className}
            aria-hidden
            {...rest}
        >
            {paths.map((d, i) => (
                <path key={i} d={d} />
            ))}
        </svg>
    );
}
