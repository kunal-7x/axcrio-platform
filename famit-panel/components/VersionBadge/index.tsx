"use client";

import { APP_VERSION } from "@/lib/version";

// Subtle app version chip, fixed bottom-right. pointer-events-none so it never
// blocks a click; uses tokens so it adapts to light/dark. Reflects the current
// build — bump lib/version.ts (or NEXT_PUBLIC_APP_VERSION) on each release.
const VersionBadge = () => (
    <div
        className="fixed right-3 bottom-3 z-30 inline-flex items-center h-6 px-2 rounded-full bg-b-surface2/70 backdrop-blur-sm text-caption text-t-tertiary ring-1 ring-s-subtle ring-inset pointer-events-none select-none max-md:right-2 max-md:bottom-2"
        aria-hidden
    >
        v{APP_VERSION}
    </div>
);

export default VersionBadge;
