import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    eslint: { ignoreDuringBuilds: true },
    typescript: { ignoreBuildErrors: true },
    images: {
        // Creative Studio assets are served as PRESIGNED DigitalOcean Spaces GET
        // URLs (the bucket stays private). next/image rejects an un-listed remote
        // host, so allow the Spaces endpoints and DISABLE optimization for them —
        // presigned URLs are signed per-fetch and must pass through untouched (the
        // optimizer can't re-fetch a one-time signature). The asset previews
        // themselves now use a native <img> (AssetImage), but this keeps any other
        // next/image consumer of a Spaces URL from throwing.
        unoptimized: true,
        remotePatterns: [
            { protocol: "https", hostname: "**.digitaloceanspaces.com" },
            { protocol: "https", hostname: "**.cdn.digitaloceanspaces.com" },
        ],
    },
};

export default nextConfig;
