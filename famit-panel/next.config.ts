import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    eslint: { ignoreDuringBuilds: true },
    typescript: { ignoreBuildErrors: true },
    // Proxy the panel's /api/* calls to the caller.py backend (same-origin -> no
    // CORS). Backend serves routes at root (/login, /run, ...), so strip /api.
    // BACKEND_ORIGIN is env-driven: defaults to local dev (127.0.0.1:8091); the
    // Docker deploy sets it to the backend container (http://backend:8091).
    async rewrites() {
        const backend = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8091";
        // Use `fallback` (NOT the default afterFiles array): afterFiles rewrites are matched BEFORE
        // dynamic app routes, so a catch-all `/api/:path*` would shadow our slow-AI proxy route at
        // app/api/campaigns/[cid]/script/[action]/route.ts (which uses fetch to survive ~40s Sonnet
        // generations — the built-in rewrite proxy resets after ~30s -> http_500). `fallback` runs
        // AFTER dynamic routes, so that route wins for the two Script Studio endpoints and every other
        // /api/* path still proxies straight through here, unchanged.
        return {
            fallback: [
                { source: "/api/:path*", destination: `${backend}/:path*` },
            ],
        };
    },
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
