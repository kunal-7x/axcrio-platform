"use client";

// ============================================================================
// API Keys has been folded into the unified Service Control Center
// (/super-admin/services), which manages the same platform provider keys
// (Groq / SambaNova / Sarvam / OpenRouter) PLUS custom services and the live
// Active Stack. This route now redirects there so there is one canonical place
// for full provider control. Kept as a redirect for any old bookmarks / deep links.
// ============================================================================

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ApiKeysRedirect() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/super-admin/services");
    }, [router]);
    return (
        <div className="flex items-center justify-center py-32 text-body-2 text-t-secondary">
            Redirecting to the Service Control Center…
        </div>
    );
}
