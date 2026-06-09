"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";

// The Billing area is now a collapsible sidebar group with separate sub-pages
// (overview / vendors / explorer / audit / plan). This landing route just
// redirects to the Overview sub-page.
export default function BillingIndexPage() {
    const router = useRouter();
    useEffect(() => {
        router.replace("/billing/overview");
    }, [router]);
    return (
        <Layout title="Billing">
            <div className="flex items-center justify-center py-16 text-t-secondary">
                Redirecting to Billing Overview…
            </div>
        </Layout>
    );
}
