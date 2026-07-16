"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Link, Element } from "react-scroll";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Switch from "@/components/Switch";
import Icon from "@/components/Icon";

const sections = [
    { title: "Account", icon: "logout", description: "Session & sign out", to: "account" },
    { title: "Notifications", icon: "bell", description: "How you get alerts", to: "notifications" },
    { title: "About", icon: "info", description: "Platform details", to: "about" },
];

const ElementWithOffset = ({ name, children }: { name: string; children: React.ReactNode }) => (
    <div className="relative">
        <Element className="absolute -top-22 left-0 right-0" name={name} />
        {children}
    </div>
);

export default function SettingsPage() {
    const router = useRouter();
    const [showConfirm, setShowConfirm] = useState(false);
    const [callAlerts, setCallAlerts] = useState(true);
    const [dailyDigest, setDailyDigest] = useState(false);
    const [approvals, setApprovals] = useState(true);

    function handleLogout() {
        if (typeof window !== "undefined") {
            localStorage.removeItem("famit_token");
        }
        router.push("/login");
    }

    const prefs = [
        { id: 1, title: "Call outcome alerts", checked: callAlerts, onChange: setCallAlerts },
        { id: 2, title: "Daily digest email", checked: dailyDigest, onChange: setDailyDigest },
        { id: 3, title: "Approval requests", checked: approvals, onChange: setApprovals },
    ];

    return (
        <Layout title="Settings">
            <div className="flex items-start max-lg:block">
                {/* Sticky section menu */}
                <div className="card sticky top-22 shrink-0 w-80 max-3xl:w-72 max-2xl:w-64 max-lg:hidden">
                    <div className="flex flex-col gap-1">
                        {sections.map((item) => (
                            <Link
                                key={item.to}
                                className="group relative flex items-center h-16 px-3 cursor-pointer"
                                activeClass="[&_.box-hover]:!visible [&_.box-hover]:!opacity-100"
                                to={item.to}
                                smooth
                                duration={500}
                                spy
                                offset={-100}
                            >
                                <div className="box-hover" />
                                <div className="relative z-2 flex justify-center items-center shrink-0 size-11 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-secondary" name={item.icon} />
                                </div>
                                <div className="relative z-2 w-[calc(100%-2.75rem)] pl-4">
                                    <div className="text-button">{item.title}</div>
                                    <div className="mt-1 truncate text-caption text-t-secondary">{item.description}</div>
                                </div>
                            </Link>
                        ))}
                    </div>
                </div>

                {/* Section cards */}
                <div className="flex flex-col gap-3 w-[calc(100%-20rem)] pl-3 max-3xl:w-[calc(100%-18rem)] max-2xl:w-[calc(100%-16rem)] max-lg:w-full max-lg:pl-0">
                    <ElementWithOffset name="account">
                        <Card title="Account">
                            <div className="flex justify-between items-center gap-6 px-5 pb-5 pt-2 max-lg:px-3">
                                <div>
                                    <div className="text-button text-t-primary">Session</div>
                                    <div className="mt-1 text-caption text-t-secondary">You are currently signed in.</div>
                                </div>
                                {!showConfirm ? (
                                    <Button
                                        isStroke
                                        className="shrink-0 !h-10 !px-5 hover:!border-primary-03/40 hover:!text-primary-03"
                                        onClick={() => setShowConfirm(true)}
                                    >
                                        Sign out
                                    </Button>
                                ) : (
                                    <div className="flex items-center gap-3 shrink-0">
                                        <span className="text-caption text-t-secondary">Confirm?</span>
                                        <Button
                                            isStroke
                                            className="!h-10 !px-4 !border-primary-03/40 !text-primary-03 hover:!border-primary-03"
                                            onClick={handleLogout}
                                        >
                                            Yes, sign out
                                        </Button>
                                        <Button
                                            isStroke
                                            className="!h-10 !px-4"
                                            onClick={() => setShowConfirm(false)}
                                        >
                                            Cancel
                                        </Button>
                                    </div>
                                )}
                            </div>
                        </Card>
                    </ElementWithOffset>

                    <ElementWithOffset name="notifications">
                        <Card title="Notifications">
                            <div className="px-5 max-lg:px-3">
                                {prefs.map((p) => (
                                    <div
                                        key={p.id}
                                        className="flex justify-between items-center gap-6 py-5 border-b border-s-subtle last:border-b-0"
                                    >
                                        <div className="text-button text-t-primary">{p.title}</div>
                                        <Switch
                                            className="shrink-0"
                                            checked={p.checked}
                                            onChange={() => p.onChange(!p.checked)}
                                        />
                                    </div>
                                ))}
                            </div>
                        </Card>
                    </ElementWithOffset>

                    <ElementWithOffset name="about">
                        <Card title="About Haptica AI">
                            <div className="px-5 pb-5 pt-2 max-lg:px-3">
                                {[
                                    ["Product", "Haptica AI Voice Telecaller"],
                                    ["Agent", "Riya (Hindi/Hinglish)"],
                                    ["Backend", "panel.famit.in"],
                                    ["Version", "core-2"],
                                ].map(([k, v]) => (
                                    <div
                                        key={k}
                                        className="flex justify-between items-center gap-6 py-4 border-b border-s-subtle last:border-b-0 text-body-2"
                                    >
                                        <span className="text-t-secondary">{k}</span>
                                        <span className="text-t-primary font-medium">{v}</span>
                                    </div>
                                ))}
                            </div>
                        </Card>
                    </ElementWithOffset>
                </div>
            </div>
        </Layout>
    );
}
