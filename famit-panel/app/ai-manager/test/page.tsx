"use client";

// Legacy route — the Test Console is now the "Try it" tab of /ai-manager.
// Redirects there, forwarding any ?q= seed. Thin redirect for old links.

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function Redirect() {
    const router = useRouter();
    const search = useSearchParams();
    useEffect(() => {
        const q = search.get("q");
        router.replace(`/ai-manager?tab=tryit${q ? `&q=${encodeURIComponent(q)}` : ""}`);
    }, [router, search]);
    return null;
}

export default function Page() {
    return (
        <Suspense fallback={null}>
            <Redirect />
        </Suspense>
    );
}
