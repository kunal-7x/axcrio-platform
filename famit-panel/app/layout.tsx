import { headers } from "next/headers";
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import Providers from "./providers";
import "./globals.css";

const interDisplay = localFont({
    src: [
        {
            path: "../public/fonts/InterDisplay-Light.woff2",
            weight: "300",
        },
        {
            path: "../public/fonts/InterDisplay-Regular.woff2",
            weight: "400",
        },
        {
            path: "../public/fonts/InterDisplay-Medium.woff2",
            weight: "500",
        },
        {
            path: "../public/fonts/InterDisplay-SemiBold.woff2",
            weight: "600",
        },
        {
            path: "../public/fonts/InterDisplay-Bold.woff2",
            weight: "700",
        },
    ],
    variable: "--font-inter-display",
});

// Gilroy (FULL version) — the app-wide brand font, all weights 100–900 + italics,
// self-hosted from /public/fonts/gilroy. The full release fixes the weight-gap that
// caused Gilroy's earlier removal (free version only had 300/800). Exposed as
// --font-gilroy and made primary in globals.css; Inter Display + system stack remain
// as fallbacks (incl. Devanagari coverage, since Gilroy is Latin-only).
const gilroy = localFont({
    src: [
        { path: "../public/fonts/gilroy/Gilroy-Thin.woff2", weight: "100", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-ThinItalic.woff2", weight: "100", style: "italic" },
        { path: "../public/fonts/gilroy/Gilroy-UltraLight.woff2", weight: "200", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-UltraLightItalic.woff2", weight: "200", style: "italic" },
        { path: "../public/fonts/gilroy/Gilroy-Light.woff2", weight: "300", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-LightItalic.woff2", weight: "300", style: "italic" },
        { path: "../public/fonts/gilroy/Gilroy-Regular.woff2", weight: "400", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-RegularItalic.woff2", weight: "400", style: "italic" },
        { path: "../public/fonts/gilroy/Gilroy-Medium.woff2", weight: "500", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-MediumItalic.woff2", weight: "500", style: "italic" },
        { path: "../public/fonts/gilroy/Gilroy-Semibold.woff2", weight: "600", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-SemiboldItalic.woff2", weight: "600", style: "italic" },
        { path: "../public/fonts/gilroy/Gilroy-Bold.woff2", weight: "700", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-BoldItalic.woff2", weight: "700", style: "italic" },
        { path: "../public/fonts/gilroy/Gilroy-Extrabold.woff2", weight: "800", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-ExtraboldItalic.woff2", weight: "800", style: "italic" },
        { path: "../public/fonts/gilroy/Gilroy-Black.woff2", weight: "900", style: "normal" },
        { path: "../public/fonts/gilroy/Gilroy-BlackItalic.woff2", weight: "900", style: "italic" },
    ],
    variable: "--font-gilroy",
    display: "swap",
});

export const metadata: Metadata = {
    title: "Haptica AI",
    description: "Haptica AI — Voice Telecaller (by Famit)",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html
            lang="en"
            className={`${gilroy.variable} ${interDisplay.variable}`}
            suppressHydrationWarning
        >
            <head />
            <body
                className={`${gilroy.variable} ${interDisplay.variable} bg-b-surface1 font-inter text-body-1 text-t-primary antialiased`}
            >
                <Providers>{children}</Providers>
            </body>
        </html>
    );
}

export async function generateViewport(): Promise<Viewport> {
    const userAgent = (await headers()).get("user-agent");
    const isiPhone = /iphone/i.test(userAgent ?? "");
    return isiPhone
        ? {
              width: "device-width",
              initialScale: 1,
              maximumScale: 1, // disables auto-zoom on ios safari
          }
        : {};
}
