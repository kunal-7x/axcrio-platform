"use client";

// Advanced monitoring client. Gathers browser signals at app load and beacons
// them to the backend, which joins them with IP-geolocation + device parsing.
// Precise GPS is privacy-respecting: the auto-beacon only reads a position that
// the user has ALREADY granted (never prompts); an explicit opt-in flow on the
// Profile page is the only thing that triggers the browser permission prompt.
import { sendSessionBeacon, type BeaconPayload, type SessionRow } from "./api";

function baseSignals(): BeaconPayload {
    const p: BeaconPayload = {};
    try {
        p.tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch {
        /* */
    }
    try {
        p.locale = navigator.language || "";
    } catch {
        /* */
    }
    try {
        const uaPlat = (navigator as unknown as { userAgentData?: { platform?: string } })
            .userAgentData?.platform;
        p.platform = uaPlat || navigator.platform || "";
    } catch {
        /* */
    }
    try {
        p.screen = `${window.screen.width}x${window.screen.height}`;
    } catch {
        /* */
    }
    return p;
}

type Coords = { lat: number; lon: number; acc: number };

// Read GPS only if permission is ALREADY granted — never prompts.
async function silentGps(): Promise<Coords | null> {
    try {
        if (!("geolocation" in navigator)) return null;
        if (!("permissions" in navigator)) return null;
        const st = await (
            navigator as unknown as {
                permissions: { query: (d: { name: PermissionName }) => Promise<{ state: string }> };
            }
        ).permissions.query({ name: "geolocation" as PermissionName });
        if (st.state !== "granted") return null;
        return await new Promise<Coords | null>((resolve) => {
            navigator.geolocation.getCurrentPosition(
                (pos) =>
                    resolve({
                        lat: pos.coords.latitude,
                        lon: pos.coords.longitude,
                        acc: pos.coords.accuracy,
                    }),
                () => resolve(null),
                { timeout: 6000, maximumAge: 600000, enableHighAccuracy: false }
            );
        });
    } catch {
        return null;
    }
}

// Fire-and-forget beacon for the authed app shell. IP-geo + device always;
// precise GPS only if already granted.
export async function beaconOnLoad(): Promise<void> {
    const payload = baseSignals();
    const gps = await silentGps();
    if (gps) {
        payload.geo_lat = gps.lat;
        payload.geo_lon = gps.lon;
        payload.geo_acc = gps.acc;
    }
    await sendSessionBeacon(payload);
}

// Explicit precise-location capture (Profile "Enable precise location" button).
// This DOES prompt the browser for permission. Returns the saved session or null.
export async function capturePreciseLocation(): Promise<SessionRow | null> {
    const payload = baseSignals();
    const coords = await new Promise<Coords | null>((resolve) => {
        if (!("geolocation" in navigator)) return resolve(null);
        navigator.geolocation.getCurrentPosition(
            (pos) =>
                resolve({
                    lat: pos.coords.latitude,
                    lon: pos.coords.longitude,
                    acc: pos.coords.accuracy,
                }),
            () => resolve(null),
            { timeout: 10000, enableHighAccuracy: true }
        );
    });
    if (coords) {
        payload.geo_lat = coords.lat;
        payload.geo_lon = coords.lon;
        payload.geo_acc = coords.acc;
    }
    const r = await sendSessionBeacon(payload);
    return r?.session ?? null;
}
