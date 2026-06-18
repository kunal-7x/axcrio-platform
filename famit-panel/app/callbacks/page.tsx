"use client";

// W15 — /callbacks folded into Call Logs as a tab (design/W15-UI-IA-PLAN.md §1a).
// This route is kept ALIVE as a redirect alias so muscle-memory + deep links never
// 404 — it forwards to the consolidated Call Logs page's Callbacks tab.
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";

export default function CallbacksRedirect() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/calls?tab=callbacks");
    }, [router]);
    return (
        <Layout title="Callbacks">
            <div className="flex items-center justify-center gap-2 py-16 text-caption text-t-tertiary">
                <span className="size-3.5 rounded-full border-2 border-s-subtle border-t-primary-01 animate-spin" />
                Opening Call Logs…
            </div>
        </Layout>
    );
}
