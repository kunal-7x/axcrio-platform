"use client";

/**
 * useGenerationJob(jobId) — thin page-level owner of the AI Asset Service job
 * stream, mapped to <GenerationLoader /> props.
 *
 * The loader is PRESENTATIONAL and opens no socket itself. This hook owns the
 * `EventSource` over `GET /api/assets/jobs/{id}/stream` (asset-service-backend
 * §8), parses each event into {state, phase, progress, variant}, and exposes
 * them ready to spread onto the loader. It falls back to polling
 * `GET /api/assets/jobs/{id}` when EventSource is unsupported, and degrades
 * cleanly (stays in "loading") when the backend is dormant — so the loader
 * still runs on its own timer with zero backend.
 *
 * NOTE: EventSource cannot set custom headers, so the auth token (stored as
 * `famit_token`, sent elsewhere as the `X-Auth` header) is passed as a `token`
 * query param; the stream endpoint accepts either.
 */

import { useEffect, useRef, useState } from "react";
import type {
    GenerationLoaderState,
    GenerationLoaderPhase,
} from "@/components/GenerationLoader";

const BASE =
    typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE
        ? process.env.NEXT_PUBLIC_API_BASE
        : "/api";

export type GenerationJob = {
    state: GenerationLoaderState;
    phase?: GenerationLoaderPhase;
    progress?: { total: number; done: number; streamingVariant?: string };
    /** the id of the last variant that finished streaming, if any */
    variant?: string;
    /** human error copy when the backend reports a failure */
    errorMessage?: string;
};

type BackendEvent = {
    state?: string;
    status?: string;
    phase?: string;
    progress?: { total?: number; done?: number; streaming_variant?: string };
    variant?: string;
    error?: string;
    message?: string;
};

const PHASES: GenerationLoaderPhase[] = [
    "queued",
    "reading_campaign",
    "building_prompts",
    "rendering",
    "scoring",
    "storing",
    "done",
];

/** Map a backend event onto the loader-facing job shape. */
function mapEvent(e: BackendEvent, prev: GenerationJob): GenerationJob {
    const raw = (e.state || e.status || "").toLowerCase();

    let state: GenerationLoaderState = prev.state;
    if (raw === "done" || raw === "succeeded" || raw === "completed") {
        state = "completed";
    } else if (raw === "failed" || raw === "error") {
        state = "failed";
    } else if (raw === "cancelled" || raw === "canceled") {
        state = "cancelled";
    } else if (raw === "queued" || raw === "running" || raw === "processing") {
        state = "loading";
    }

    const phase =
        e.phase && PHASES.includes(e.phase as GenerationLoaderPhase)
            ? (e.phase as GenerationLoaderPhase)
            : prev.phase;

    let progress = prev.progress;
    if (
        e.progress &&
        typeof e.progress.total === "number" &&
        typeof e.progress.done === "number"
    ) {
        progress = {
            total: e.progress.total,
            done: e.progress.done,
            streamingVariant: e.progress.streaming_variant,
        };
    }

    return {
        state,
        phase,
        progress,
        variant: e.variant ?? prev.variant,
        errorMessage: e.error || e.message || prev.errorMessage,
    };
}

export function useGenerationJob(jobId: string | null | undefined): GenerationJob {
    const [job, setJob] = useState<GenerationJob>({ state: "loading" });
    const jobRef = useRef<GenerationJob>(job);
    jobRef.current = job;

    useEffect(() => {
        if (!jobId) return;

        // reset on a new job id
        setJob({ state: "loading" });

        const token =
            typeof window !== "undefined"
                ? localStorage.getItem("famit_token")
                : null;
        const url = `${BASE}/assets/jobs/${encodeURIComponent(jobId)}/stream${
            token ? `?token=${encodeURIComponent(token)}` : ""
        }`;

        // --- SSE path ---
        if (typeof EventSource !== "undefined") {
            let es: EventSource | null = null;
            try {
                es = new EventSource(url);
            } catch {
                es = null;
            }

            if (es) {
                const onMessage = (ev: MessageEvent) => {
                    let parsed: BackendEvent;
                    try {
                        parsed = JSON.parse(ev.data);
                    } catch {
                        return; // ignore keep-alive / non-JSON frames
                    }
                    setJob((prev) => mapEvent(parsed, prev));
                };
                es.onmessage = onMessage;
                es.addEventListener("phase", onMessage as EventListener);
                es.addEventListener("progress", onMessage as EventListener);
                es.addEventListener("done", onMessage as EventListener);
                es.addEventListener("failed", onMessage as EventListener);
                es.onerror = () => {
                    // Terminal states close the stream; do NOT flip to failed on
                    // a normal close. Leave the last known state intact so the
                    // loader keeps its own timer if the backend is dormant.
                    if (
                        es &&
                        es.readyState === EventSource.CLOSED &&
                        jobRef.current.state === "loading"
                    ) {
                        // dormant / unreachable -> stay loading (timer-driven)
                    }
                };
                return () => es?.close();
            }
        }

        // --- polling fallback (no EventSource) ---
        let active = true;
        const poll = async () => {
            try {
                const headers: HeadersInit = token ? { "X-Auth": token } : {};
                const res = await fetch(
                    `${BASE}/assets/jobs/${encodeURIComponent(jobId)}`,
                    { headers }
                );
                if (!res.ok) return;
                const data: BackendEvent = await res.json();
                if (active) setJob((prev) => mapEvent(data, prev));
            } catch {
                // dormant backend -> leave loader on its own timer
            }
        };
        const id = setInterval(() => {
            if (
                jobRef.current.state === "completed" ||
                jobRef.current.state === "failed" ||
                jobRef.current.state === "cancelled"
            ) {
                clearInterval(id);
                return;
            }
            poll();
        }, 1500);
        poll();
        return () => {
            active = false;
            clearInterval(id);
        };
    }, [jobId]);

    return job;
}

export default useGenerationJob;
