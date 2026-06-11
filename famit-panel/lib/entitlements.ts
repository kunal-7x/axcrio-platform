"use client";

// ============================================================
// CL-F0 — Entitlement client (the shared real-time plumbing)
//
// Mirrors lib/auth.ts (fetch + localStorage cache + a mount hook), but adds the
// versioned-ETag short-poll + opportunistic revalidation that makes a control
// write felt near-instantly across active tabs. Design of record:
//   design/control-realtime-enforcement.md §1.3 (client behaviour)
//   design/control-ui.md §4 (vendor-side HIDE/LOCK)
//
// SECURITY NOTE (non-negotiable, spec §9.1): everything here is COSMETIC. The
// backend choke-point (path -> feature_key -> 404 hidden / 402 locked,
// fail-closed) is the only real boundary. This module spares the user a flash
// of a page they can't use and drives the upsell UX; it NEVER grants access. A
// forged localStorage map changes nothing server-side.
//
// Shape: ONE module-level store (single source of truth) + a tiny pub/sub.
// `EntitlementProvider` mounts the poller ONCE (like useMe); every
// `useEntitlement(key)` consumer subscribes to the same store. This avoids N
// pollers and keeps every gated surface in lockstep on a change.
// ============================================================

import { createElement, Fragment, useEffect, useSyncExternalStore } from "react";
import {
    getEntitlements,
    type EntitlementMode,
    type EntitlementsPayload,
} from "@/lib/api";

// The 3-state verdict a consumer acts on. UI-facing alias of EntitlementMode.
//   ON   -> render normally
//   LOCK -> render the LockOverlay / dimmed "Locked" nav pill (upsell)
//   HIDE -> drop the nav item / redirect the route (does-not-exist UX)
export type EntMode = "ON" | "LOCK" | "HIDE";

const ENT_KEY = "famit_ent";
const ETAG_KEY = "famit_ent_etag";
const POLL_MS = (() => {
    const raw =
        typeof process !== "undefined"
            ? process.env.NEXT_PUBLIC_ENT_POLL_MS
            : undefined;
    const n = raw ? parseInt(raw, 10) : NaN;
    return Number.isFinite(n) && n >= 5000 ? n : 25_000; // default 25s, floor 5s
})();

// Resting-state default: an empty map resolves every key to ON (control off /
// pre-ship parity). status "active" so suspension banners stay quiet until a
// real backend says otherwise.
const DEFAULT_PAYLOAD: EntitlementsPayload = {
    version: 0,
    status: "active",
    plan: "",
    modes: {},
};

// ---- module-level store (single source of truth) -----------------------------
type StoreState = {
    payload: EntitlementsPayload;
    etag: string | null;
    loading: boolean;
    loaded: boolean; // a real 200/404 has resolved at least once
};

let state: StoreState = {
    payload: readCache() ?? DEFAULT_PAYLOAD,
    etag: readEtag(),
    loading: true,
    loaded: false,
};

const listeners = new Set<() => void>();

function emit() {
    for (const l of listeners) l();
}

function setState(patch: Partial<StoreState>) {
    state = { ...state, ...patch };
    emit();
}

function subscribe(fn: () => void): () => void {
    listeners.add(fn);
    return () => listeners.delete(fn);
}

function getSnapshot(): StoreState {
    return state;
}

// SSR snapshot — never touches window. Resting permissive default.
const SERVER_STATE: StoreState = {
    payload: DEFAULT_PAYLOAD,
    etag: null,
    loading: false,
    loaded: false,
};
function getServerSnapshot(): StoreState {
    return SERVER_STATE;
}

// ---- cache (localStorage; advisory only) -------------------------------------
function readCache(): EntitlementsPayload | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = localStorage.getItem(ENT_KEY);
        return raw ? (JSON.parse(raw) as EntitlementsPayload) : null;
    } catch {
        return null;
    }
}

function writeCache(p: EntitlementsPayload, etag: string | null) {
    if (typeof window === "undefined") return;
    try {
        localStorage.setItem(ENT_KEY, JSON.stringify(p));
        if (etag) localStorage.setItem(ETAG_KEY, etag);
        else localStorage.removeItem(ETAG_KEY);
    } catch {
        /* ignore quota / disabled storage */
    }
}

function readEtag(): string | null {
    if (typeof window === "undefined") return null;
    try {
        return localStorage.getItem(ETAG_KEY);
    } catch {
        return null;
    }
}

export function clearEntitlementsCache() {
    if (typeof window === "undefined") return;
    try {
        localStorage.removeItem(ENT_KEY);
        localStorage.removeItem(ETAG_KEY);
    } catch {
        /* ignore */
    }
    state = { payload: DEFAULT_PAYLOAD, etag: null, loading: false, loaded: false };
    emit();
}

// ---- the one fetch path everything shares ------------------------------------
// A conditional GET. 304 -> no-op (cheap). 200 -> swap the map + cache + notify
// every subscriber, so a downgrade-while-viewing re-renders the nav and bounces
// the active page on the next tick. Failures are swallowed: we keep the cached
// map (fail-closed to core-only is handled at the consumer when nothing loaded).
let inFlight: Promise<void> | null = null;

export async function revalidateEntitlements(): Promise<void> {
    if (typeof window === "undefined") return;
    if (inFlight) return inFlight;
    inFlight = (async () => {
        try {
            const res = await getEntitlements(state.etag);
            if (res.notModified) {
                // ETag still current — only flip the loading/loaded flags.
                if (state.loading || !state.loaded) {
                    setState({ loading: false, loaded: true, etag: res.etag ?? state.etag });
                }
                return;
            }
            writeCache(res.payload, res.etag);
            setState({
                payload: res.payload,
                etag: res.etag,
                loading: false,
                loaded: true,
            });
        } catch {
            // Network/transient — keep the cached map; just clear the spinner.
            setState({ loading: false });
        } finally {
            inFlight = null;
        }
    })();
    return inFlight;
}

// Called by data-fetch error paths (the self-healing hook). A 402/404/401 from
// any page fetch means the server's view changed under us -> re-pull + reconcile
// the UI. Cheap (conditional GET); de-duped via inFlight.
export function onAccessSignal(status: number) {
    if (status === 402 || status === 404 || status === 401) {
        void revalidateEntitlements();
    }
}

// ---- resolution: feature_key -> 3-state --------------------------------------
function modeToEnt(m: EntitlementMode | undefined): EntMode {
    if (m === "hidden") return "HIDE";
    if (m === "locked") return "LOCK";
    return "ON"; // "on" OR unknown-key -> ON (permissive cosmetics; backend is authority)
}

// Pure resolver against an explicit payload (used by the SSR-safe hook + by
// non-React callers, e.g. the Sidebar resolveNav filter).
export function modeOfIn(payload: EntitlementsPayload, key?: string): EntMode {
    if (!key) return "ON";
    return modeToEnt(payload.modes[key]);
}

// ============================================================================
// PUBLIC HOOKS
// ============================================================================

// Mount-once provider: owns the single poller + every revalidation trigger.
// Place high in the tree (alongside AuthGuard in app/providers.tsx). Renders
// children unchanged — it's pure side-effect.
export function EntitlementProvider({
    children,
}: {
    children: React.ReactNode;
}): React.ReactElement {
    useEffect(() => {
        // 1) initial revalidate (cache already painted instantly from module init)
        void revalidateEntitlements();

        // 2) interval short-poll (conditional GET; a 304 is a few bytes)
        const id = window.setInterval(() => {
            void revalidateEntitlements();
        }, POLL_MS);

        // 3) on tab refocus -> immediate refresh (felt latency ~0 without a stream)
        const onVis = () => {
            if (document.visibilityState === "visible") void revalidateEntitlements();
        };
        document.addEventListener("visibilitychange", onVis);

        return () => {
            window.clearInterval(id);
            document.removeEventListener("visibilitychange", onVis);
        };
    }, []);

    // Pure side-effect wrapper — render children unchanged. createElement (not
    // JSX) keeps this a .ts module as the design names it (lib/entitlements.ts).
    return createElement(Fragment, null, children);
}

// Subscribe to the whole store (payload/status/version/loading). For consumers
// that need the status (suspension banner) or want to react to any change.
export function useEntitlements() {
    const snap = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
    return {
        payload: snap.payload,
        status: snap.payload.status,
        version: snap.payload.version,
        plan: snap.payload.plan,
        modes: snap.payload.modes,
        loading: snap.loading,
        loaded: snap.loaded,
    };
}

// THE primary consumer API: useEntitlement(feature_key) -> "ON" | "LOCK" | "HIDE".
// Re-renders the calling component whenever a control write flips this key.
export function useEntitlement(key?: string): EntMode {
    const snap = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
    return modeOfIn(snap.payload, key);
}

// Route-change revalidate. A page (or a guard) calls this with its pathname so a
// navigation re-pulls the map — pairs with the interval + focus triggers so the
// felt staleness on entering a downgraded page is near-zero. Self-contained: it
// reads usePathname itself so callers just mount <RevalidateOnRoute/> once, or
// call useEntitlementRoute() inside the guard.
export function useEntitlementRoute(pathname: string | null) {
    useEffect(() => {
        void revalidateEntitlements();
    }, [pathname]);
}

// Non-hook snapshot read (for imperative code paths that can't use a hook).
export function snapshotMode(key?: string): EntMode {
    return modeOfIn(state.payload, key);
}

// A convenience hook some pages prefer over reading status off useEntitlements.
export function useEntitlementStatus(): { status: string; loaded: boolean } {
    const snap = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
    return { status: snap.payload.status, loaded: snap.loaded };
}

// Backwards-friendly default value while nothing has loaded — exported so a
// consumer can decide its own fail-closed cosmetics if it wants to.
export { DEFAULT_PAYLOAD };
export type { EntitlementMode, EntitlementsPayload };
