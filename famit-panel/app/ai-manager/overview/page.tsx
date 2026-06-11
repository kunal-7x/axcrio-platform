"use client";

// Legacy route — AI Manager collapsed to ONE page (/ai-manager) with three tabs.
// This sub-route now redirects to the Home tab. Kept as a thin redirect so old
// bookmarks/links keep working.

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Redirect() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/ai-manager");
    }, [router]);
    return null;
}
