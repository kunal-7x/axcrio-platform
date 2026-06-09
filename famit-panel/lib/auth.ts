"use client";

import { useEffect, useState } from "react";
import { getMe, type Me, type Role } from "@/lib/api";

const ME_KEY = "famit_me";

// ---- localStorage cache of the current user (role/is_admin/...) ----
export function getCachedMe(): Me | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = localStorage.getItem(ME_KEY);
        return raw ? (JSON.parse(raw) as Me) : null;
    } catch {
        return null;
    }
}

export function setCachedMe(me: Me) {
    if (typeof window === "undefined") return;
    try {
        localStorage.setItem(ME_KEY, JSON.stringify(me));
    } catch {
        /* ignore */
    }
}

export function clearCachedMe() {
    if (typeof window === "undefined") return;
    localStorage.removeItem(ME_KEY);
}

// Optionally seed the cache from a /login response (which carries role/is_admin
// but not email — good enough for immediate gating; refreshed by /me on load).
export function seedMeFromLogin(data: { tenant_id: string; name: string; is_admin: boolean; role?: Role; email?: string }) {
    setCachedMe({
        tenant_id: data.tenant_id,
        email: data.email ?? "",
        name: data.name,
        role: data.role ?? (data.is_admin ? "admin" : "manager"),
        is_admin: data.is_admin,
    });
}

// ---- Role helpers ----
// Default to the most permissive sane value while /me is loading, BUT never
// while we already know the role. Mutations are guarded server-side too (403),
// so a brief optimistic render can't actually break anything.
export function isAdmin(me: Me | null): boolean {
    return !!me && (me.is_admin || me.role === "admin");
}

// manager+ : can perform tenant write actions (run, create/delete, webhooks, WA send)
export function canWrite(me: Me | null): boolean {
    if (!me) return false;
    return me.role === "admin" || me.role === "manager";
}

// agent : read-only
export function isReadOnly(me: Me | null): boolean {
    return !!me && me.role === "agent";
}

// ---- Hook: load /me on mount, with cache for instant gating ----
export function useMe(): { me: Me | null; loading: boolean } {
    const [me, setMe] = useState<Me | null>(() => getCachedMe());
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let alive = true;
        getMe()
            .then((m) => {
                if (!alive) return;
                setMe(m);
                setCachedMe(m);
            })
            .catch(() => {
                // /me failed (offline / older backend) — keep cached value if any.
            })
            .finally(() => {
                if (alive) setLoading(false);
            });
        return () => {
            alive = false;
        };
    }, []);

    return { me, loading };
}
