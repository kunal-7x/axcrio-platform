"use client";

// Legacy route — Approvals now live on the Home tab of /ai-manager.
// Thin redirect so old bookmarks/links keep working.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Redirect() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/ai-manager");
    }, [router]);
    return null;
}
