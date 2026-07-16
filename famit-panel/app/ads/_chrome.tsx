"use client";

// Ad Automation — shared page chrome (V2-W5).
//
// The toast host (the page owns the timer) + the right-aligned "engine status +
// Refresh" cluster every sub-page carries under its title. Lifted here so all four
// pages share the SAME rhythm with zero duplication. Token-pure.

import { useCallback, useState, type ReactElement } from "react";
import Icon from "@/components/Icon";
import type { Toast, ToastFn } from "./_shared";

export function useToast(): { toast: Toast | null; showToast: ToastFn; ToastHost: () => ReactElement | null } {
    const [toast, setToast] = useState<Toast | null>(null);
    const showToast = useCallback<ToastFn>((msg, type = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4600);
    }, []);
    const ToastHost = () =>
        toast ? (
            <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                <span className="flex items-center gap-2">
                    <span className="size-1.5 rounded-full bg-current" />
                    {toast.msg}
                </span>
                <button
                    onClick={() => setToast(null)}
                    className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none"
                >
                    ×
                </button>
            </div>
        ) : null;
    return { toast, showToast, ToastHost };
}

// The status dot + label + matching Refresh pill, aligned right under the title.
export function StatusRefresh({
    status,
    onRefresh,
    busy,
}: {
    status: { label: string; tone: string };
    onRefresh: () => void;
    busy: boolean;
}) {
    return (
        <div className="ml-auto flex items-center gap-3">
            <span className="inline-flex items-center gap-2 text-caption text-t-tertiary max-md:hidden">
                <span className="size-1.5 rounded-full shrink-0" style={{ background: status.tone }} />
                {status.label}
            </span>
            <button
                onClick={onRefresh}
                disabled={busy}
                className="shrink-0 inline-flex items-center justify-center gap-2 h-10 px-4 rounded-full bg-b-surface2 ring-1 ring-s-subtle ring-inset text-button text-t-secondary transition-all hover:text-t-primary hover:ring-s-highlight hover:shadow-widget active:scale-[0.98] disabled:opacity-50"
            >
                <Icon name="clock" className={`size-4 fill-current ${busy ? "animate-spin" : ""}`} />
                <span className="max-md:hidden">Refresh</span>
            </button>
        </div>
    );
}
