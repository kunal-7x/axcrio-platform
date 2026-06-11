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

// FONT (W1 decision, design/ui-font-heading-plan.md §3): Inter Display is the
// single app-wide family — it ships all five weights (300–700) the type scale
// requests, so every weight resolves to a real face. Gilroy was removed from the
// cascade: its free release ships only 300/800, so 400/500/600/700 silently fell
// through to Inter — "the font never changed." If a Gilroy brand wordmark is ever
// wanted, load it as a display-only face for the logo lockup, never as body.

export const metadata: Metadata = {
    title: "Famit",
    description: "Famit AI Tele-Calling Panel",
};

export default function RootLayout({
    children,
}: Readonly<{
    children: React.ReactNode;
}>) {
    return (
        <html lang="en" suppressHydrationWarning>
            <head />
            <body
                className={`${interDisplay.variable} bg-b-surface1 font-inter text-body-1 text-t-primary antialiased`}
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
