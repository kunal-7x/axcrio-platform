"use client";

/**
 * useAssetStatus — the Creative Studio dormancy probe.
 *
 * Every screen calls this FIRST. It hits the ONLY un-gated route
 * (`GET /api/assets/status`) and resolves to `{ enabled }`. The whole rest of the
 * surface is 503-gated by AIASSET_ENABLED, so when this says `enabled:false` every
 * screen renders its calm dormant state (a <DormantCard />) instead of an
 * error-wall — the byte-identical-to-live guarantee (cs-workspace §3 / §17).
 *
 * `loading` is true only on the very first probe so the page can hold a Spinner
 * for a beat rather than flashing the dormant card before the probe lands.
 */

import { useEffect, useState } from "react";
import { getAssetStatus, type AssetStatus } from "@/lib/assets";

export type UseAssetStatus = {
    status: AssetStatus | null;
    enabled: boolean;
    loading: boolean;
};

export function useAssetStatus(): UseAssetStatus {
    const [status, setStatus] = useState<AssetStatus | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let active = true;
        getAssetStatus()
            .then((s) => {
                if (active) setStatus(s);
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => {
            active = false;
        };
    }, []);

    return { status, enabled: !!status?.enabled, loading };
}

export default useAssetStatus;
