"use client";

import { useEffect, useState } from "react";
import { useMe } from "@/lib/auth";
import { getMe } from "@/lib/api";

function fmt(total: number): string {
    const s = Math.max(0, Math.floor(total));
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

function expireSession() {
    try {
        localStorage.removeItem("famit_token");
        localStorage.removeItem("famit_me");
    } catch {
        /* ignore */
    }
    if (typeof window !== "undefined") window.location.href = "/login";
}

/**
 * Realtime "Demo Account MM:SS" badge for demo clients. Counts down every second,
 * re-syncs with the server every 30s (so an admin reset / extension is reflected),
 * and logs the client out the instant the clock hits zero.
 */
const DemoBadge = () => {
    const { me } = useMe();
    const isDemo = !!me?.demo;
    const [left, setLeft] = useState<number | null>(null);

    // seed / refresh from /me
    useEffect(() => {
        if (!isDemo) {
            setLeft(null);
            return;
        }
        setLeft(Math.max(0, me?.demo_remaining_s ?? 0));
    }, [isDemo, me?.demo_remaining_s]);

    // tick down once per second; expire at zero
    useEffect(() => {
        if (left == null) return;
        if (left <= 0) {
            expireSession();
            return;
        }
        const t = setTimeout(() => setLeft((v) => (v == null ? v : v - 1)), 1000);
        return () => clearTimeout(t);
    }, [left]);

    // re-sync with the server every 30s to correct drift / admin resets
    useEffect(() => {
        if (!isDemo) return;
        const iv = setInterval(() => {
            getMe()
                .then((m) => {
                    if (m.demo) setLeft(Math.max(0, m.demo_remaining_s ?? 0));
                })
                .catch(() => {
                    /* keep local countdown on transient failure */
                });
        }, 30000);
        return () => clearInterval(iv);
    }, [isDemo]);

    if (!isDemo || left == null) return null;

    const low = left <= 60;
    return (
        <div
            title="Demo account — access ends when the timer reaches 0:00"
            className={`flex items-center gap-2 h-9 px-3 rounded-full border text-button max-md:px-2.5 ${
                low
                    ? "border-[#BF4D43]/30 bg-[#BF4D43]/10 text-[#BF4D43]"
                    : "border-primary-01/30 bg-primary-01/10 text-primary-01"
            }`}
        >
            <span
                className={`size-2 rounded-full animate-pulse ${
                    low ? "bg-[#BF4D43]" : "bg-primary-01"
                }`}
            />
            <span className="max-md:hidden">Demo Account</span>
            <span className="tabular-nums font-semibold td-num">{fmt(left)}</span>
        </div>
    );
};

export default DemoBadge;
