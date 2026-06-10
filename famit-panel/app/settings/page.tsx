"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import PageHeader from "@/components/PageHeader";

export default function SettingsPage() {
    const router = useRouter();
    const [showConfirm, setShowConfirm] = useState(false);

    function handleLogout() {
        if (typeof window !== "undefined") {
            localStorage.removeItem("famit_token");
        }
        router.push("/login");
    }

    return (
        <Layout title="Settings">
            <PageHeader
                eyebrow="Account"
                title="Settings"
                subtitle="Manage your session and review platform details."
            />
            <div className="max-w-2xl space-y-6">
                {/* Account section */}
                <Card title="Account">
                    <div className="px-5 pb-5 space-y-4">
                        <div className="flex items-center justify-between py-3 border-b border-s-subtle">
                            <div>
                                <div className="text-body-2 font-medium text-t-primary">Session</div>
                                <div className="text-caption text-t-tertiary mt-0.5">You are currently signed in</div>
                            </div>
                            {!showConfirm ? (
                                <Button
                                    isStroke
                                    className="h-9 px-5 !text-primary-03 !border-primary-03/30 hover:!border-primary-03 hover:!text-primary-03"
                                    onClick={() => setShowConfirm(true)}
                                >
                                    Sign out
                                </Button>
                            ) : (
                                <div className="flex items-center gap-2">
                                    <span className="text-caption text-t-secondary">Confirm?</span>
                                    <button
                                        onClick={handleLogout}
                                        className="inline-flex items-center h-8 px-3 rounded-full text-caption font-medium border border-[#FF6A55]/20 bg-[#FF6A55]/10 text-[#FF6A55] transition-colors hover:bg-[#FF6A55]/20"
                                    >
                                        Yes, sign out
                                    </button>
                                    <button
                                        onClick={() => setShowConfirm(false)}
                                        className="inline-flex items-center h-8 px-3 rounded-full text-caption font-medium border border-s-stroke2 bg-b-surface1 text-t-secondary transition-colors hover:text-t-primary dark:bg-shade-04/50"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </Card>

                {/* About section */}
                <Card title="About Famit">
                    <div className="px-5 pb-5 space-y-3 text-body-2 text-t-secondary">
                        <div className="flex items-center justify-between">
                            <span>Product</span>
                            <span className="text-t-primary font-medium">Famit AI Tele-Calling</span>
                        </div>
                        <div className="flex items-center justify-between border-t border-s-subtle pt-3">
                            <span>Agent</span>
                            <span className="text-t-primary font-medium">Riya (Hindi/Hinglish)</span>
                        </div>
                        <div className="flex items-center justify-between border-t border-s-subtle pt-3">
                            <span>Backend</span>
                            <span className="text-t-primary font-medium">panel.famit.in</span>
                        </div>
                        <div className="flex items-center justify-between border-t border-s-subtle pt-3">
                            <span>Version</span>
                            <span className="text-t-primary font-medium">core-2</span>
                        </div>
                    </div>
                </Card>

                {/* Quick links */}
                <Card title="Navigation">
                    <div className="px-5 pb-5 grid grid-cols-2 gap-3">
                        {[
                            { label: "Dashboard", href: "/" },
                            { label: "Campaigns", href: "/campaigns" },
                            { label: "Leads", href: "/leads" },
                            { label: "Run", href: "/run" },
                            { label: "Call Logs", href: "/calls" },
                            { label: "Vendors", href: "/vendors" },
                        ].map((link) => (
                            <a
                                key={link.href}
                                href={link.href}
                                className="flex items-center gap-2 p-3 rounded-2xl bg-b-surface2 hover:bg-b-surface3 transition-colors text-body-2 text-t-primary"
                            >
                                <span>{link.label}</span>
                            </a>
                        ))}
                    </div>
                </Card>
            </div>
        </Layout>
    );
}
