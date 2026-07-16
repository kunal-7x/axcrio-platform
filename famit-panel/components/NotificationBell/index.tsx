"use client";

// NotificationBell — top-right (next to the profile) real-time-ish feed of new system
// logs & errors, for super-admins only. Polls /admin/notifications; the unread badge is
// computed against a client-side "last seen" cursor in localStorage (no server read-state).
// Clicking through opens the white-labeled System Logs page. Renders NOTHING for non-admins.

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Icon from "@/components/Icon";
import { useMe, isAdmin } from "@/lib/auth";
import { getNotifications, type SystemEvent, type NotificationFeed } from "@/lib/api";
import { ago } from "@/app/super-admin/_shared";

const SEEN_KEY = "famit_notif_seen_seq";
const POLL_MS = 25_000;

function levelDot(level?: string): string {
    const l = (level || "").toLowerCase();
    if (l === "critical" || l === "error") return "bg-primary-03";
    if (l === "warning") return "bg-[#EF9D0E]";
    if (l === "info") return "bg-primary-01";
    return "bg-t-tertiary";
}

const NotificationBell = () => {
    const { me } = useMe();
    const admin = isAdmin(me);
    const router = useRouter();

    const [feed, setFeed] = useState<NotificationFeed>({ events: [], latest_seq: 0, unread: 0, unread_errors: 0 });
    const [open, setOpen] = useState(false);
    const [seen, setSeen] = useState(0);
    const wrapRef = useRef<HTMLDivElement | null>(null);

    // hydrate the last-seen cursor from localStorage
    useEffect(() => {
        if (typeof window === "undefined") return;
        const v = parseInt(window.localStorage.getItem(SEEN_KEY) || "0", 10);
        setSeen(Number.isFinite(v) ? v : 0);
    }, []);

    const poll = useCallback(() => {
        if (!admin) return;
        getNotifications({ after: seen, limit: 30 }).then(setFeed).catch(() => {});
    }, [admin, seen]);

    // poll on mount + interval (only for admins)
    useEffect(() => {
        if (!admin) return;
        poll();
        const id = setInterval(poll, POLL_MS);
        return () => clearInterval(id);
    }, [admin, poll]);

    // close on outside click
    useEffect(() => {
        if (!open) return;
        const onDown = (e: MouseEvent) => {
            if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
        };
        document.addEventListener("mousedown", onDown);
        return () => document.removeEventListener("mousedown", onDown);
    }, [open]);

    const markAllRead = useCallback(() => {
        const latest = feed.latest_seq || 0;
        setSeen(latest);
        if (typeof window !== "undefined") window.localStorage.setItem(SEEN_KEY, String(latest));
        setFeed((f) => ({ ...f, unread: 0, unread_errors: 0 }));
    }, [feed.latest_seq]);

    const goToLogs = useCallback(() => {
        markAllRead();
        setOpen(false);
        router.push("/super-admin/system-logs");
    }, [markAllRead, router]);

    if (!admin) return null;

    const unread = feed.unread || 0;
    const hasErrors = (feed.unread_errors || 0) > 0;

    return (
        <div className="relative" ref={wrapRef}>
            <button
                type="button"
                aria-label="Notifications"
                onClick={() => {
                    setOpen((o) => !o);
                    if (!open) poll();
                }}
                className="relative grid place-items-center size-11 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-t-secondary transition-colors hover:text-t-primary hover:ring-s-highlight max-md:size-10"
            >
                <Icon name="bell" className="size-5 fill-current" />
                {unread > 0 && (
                    <span
                        className={`absolute -top-0.5 -right-0.5 min-w-5 h-5 px-1 grid place-items-center rounded-full text-[11px] font-semibold text-white tabular-nums ring-2 ring-b-surface1 ${
                            hasErrors ? "bg-primary-03" : "bg-primary-01"
                        }`}
                    >
                        {unread > 99 ? "99+" : unread}
                    </span>
                )}
            </button>

            {open && (
                <div className="absolute right-0 mt-2 w-96 max-md:w-80 max-h-[70vh] overflow-hidden flex flex-col rounded-3xl bg-b-surface1 ring-1 ring-s-subtle shadow-2xl z-50">
                    <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-s-subtle">
                        <div className="text-button text-t-primary">Notifications</div>
                        {unread > 0 && (
                            <button onClick={markAllRead} className="text-caption text-t-tertiary hover:text-t-primary transition-colors">
                                Mark all read
                            </button>
                        )}
                    </div>

                    <div className="overflow-y-auto">
                        {feed.events.length === 0 ? (
                            <div className="px-4 py-10 text-center">
                                <Icon name="check-circle" className="size-6 fill-t-tertiary mx-auto mb-2" />
                                <div className="text-body-2 text-t-secondary">You&apos;re all caught up</div>
                                <div className="text-caption text-t-tertiary">No recent system events.</div>
                            </div>
                        ) : (
                            <div className="divide-y divide-s-subtle">
                                {feed.events.map((e: SystemEvent) => {
                                    const isNew = (e.seq || 0) > seen;
                                    return (
                                        <button
                                            key={e.id}
                                            onClick={goToLogs}
                                            className={`w-full flex items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-b-surface2/60 ${
                                                isNew ? "bg-primary-01/[0.04]" : ""
                                            }`}
                                        >
                                            <span className={`shrink-0 mt-1.5 size-2 rounded-full ${levelDot(e.level)}`} />
                                            <div className="min-w-0 flex-1">
                                                <div className="text-body-2 text-t-primary truncate">{e.message}</div>
                                                <div className="flex items-center gap-2 mt-0.5 text-caption text-t-tertiary">
                                                    <span className="font-mono">{e.source}</span>
                                                    <span>·</span>
                                                    <span>{ago(e.ts)}</span>
                                                </div>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                    </div>

                    <button
                        onClick={goToLogs}
                        className="shrink-0 px-4 py-3 border-t border-s-subtle text-button text-primary-01 hover:bg-b-surface2/60 transition-colors text-center"
                    >
                        View all in System Logs
                    </button>
                </div>
            )}
        </div>
    );
};

export default NotificationBell;
