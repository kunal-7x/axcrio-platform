"use client";

// Legacy route — "What it can do" is now a section of the Setup tab.
// Thin redirect so old bookmarks/links keep working.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Redirect() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/ai-manager?tab=setup");
    }, [router]);
    return null;
}
