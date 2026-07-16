"use client";

import { useEffect } from "react";
import { beaconOnLoad } from "@/lib/monitor";

// Mounted once in the authenticated app shell (providers.tsx). Fires a single
// best-effort monitoring beacon (location/device) per load. Renders nothing and
// never throws — monitoring must never affect the app.
export default function SessionBeacon() {
    useEffect(() => {
        if (typeof window === "undefined") return;
        if (!localStorage.getItem("famit_token")) return;
        void beaconOnLoad();
    }, []);
    return null;
}
