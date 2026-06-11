"use client";

// Legacy route — Setup is now the "Setup" tab of /ai-manager.
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
