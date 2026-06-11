"use client";

// Legacy route — the "Command Center" board is removed (not a user concept).
// Redirects to the unified /ai-manager Home tab. Thin redirect for old links.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Redirect() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/ai-manager");
    }, [router]);
    return null;
}
