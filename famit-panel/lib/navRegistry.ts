// ============================================================================
// ROUND-6 LANE 4 — DYNAMIC permission registry derived from the LIVE sidebar nav.
//
// The super-admin Permissions matrix (app/super-admin/vendors/[id]) renders the
// lockable module/page list from FEATURE_REGISTRY (lib/api.ts). That seed was a
// HAND-MAINTAINED snapshot that drifted from the actual sidebar: it was missing
// Creative Studio, Message/WhatsApp, the campaign SCRIPT/render-brain entitlements,
// Revenue Tools, Knowledge Base, Integrations, etc. — so a super-admin could not
// lock features the founder could see in the rail.
//
// This module DERIVES registry nodes straight from contstants/navigation.tsx so the
// matrix AUTO-UPDATES whenever the nav changes — never hand-maintained again. Each
// nav GROUP with a `feature_key` becomes a `module` node; each child with a
// `feature_key` becomes a `page` node parented to its group's module (or null when
// the group itself is unkeyed). We key by the SAME `feature_key` the nav authors,
// which is the SAME key the backend /me/entitlements `modes` map uses (the nav
// comments mandate they stay in lockstep), so backend 404/402 enforcement still
// lines up 1:1. Admin-only / role-gated entries are EXCLUDED (role-gated, never
// entitlement-gated). Nodes already present in the static seed are skipped, so the
// derivation only ADDS the missing surfaces — additive, never destructive.
//
// We also surface the campaign SCRIPT-lock + render-brain-lock keys that the
// backend registry.json already enforces (ROUND-5 P4b: grow.campaigns.script /
// grow.campaigns.render_brain) so they appear as toggles under Campaigns.
// ============================================================================

import { navigation } from "@/contstants/navigation";
import type { FeatureRegistryNode } from "@/lib/api";

// The structural shape of a nav entry we read (a subset of navigation.tsx). Kept
// loose so a future nav change can't break the build over an extra field.
type NavChild = {
    title: string;
    href?: string;
    feature_key?: string;
    roles?: string;
    comingSoon?: boolean;
};
type NavEntry = {
    title: string;
    icon?: string;
    href?: string;
    feature_key?: string;
    roles?: string;
    list?: NavChild[];
};

// Extra entitlement keys the backend already enforces but the nav does not author
// as its own rail child (they gate IN-PAGE actions, not a route). Parented to the
// owning page so they render nested under it in the matrix.
const EXTRA_ACTION_NODES: FeatureRegistryNode[] = [
    {
        key: "grow.campaigns.script",
        kind: "action",
        parent_key: "grow.campaigns",
        label: "Campaign Script → Brain",
        sort_order: 215,
    },
    {
        key: "grow.campaigns.render_brain",
        kind: "action",
        parent_key: "grow.campaigns",
        label: "Render-Brain (dry-run)",
        sort_order: 216,
    },
];

// Map a nav group's sort position to a stable sort_order band (×100) so derived
// modules interleave predictably with the static seed without colliding.
function moduleSortBase(index: number): number {
    return 200 + index * 100;
}

// Build the full nav-derived node list (modules + their keyed children).
export function navDerivedRegistry(): FeatureRegistryNode[] {
    const out: FeatureRegistryNode[] = [];
    const nav = navigation as unknown as NavEntry[];

    nav.forEach((group, gi) => {
        // Skip admin-only groups entirely — role-gated, never entitlement-gated.
        if (group.roles === "admin") return;

        const base = moduleSortBase(gi);

        // A keyed GROUP becomes a module node; the children parent to it. An
        // UNKEYED group still contributes its keyed children (parent = null) so a
        // page like Creative's items or a top-level keyed link still appears.
        const moduleKey = group.feature_key || null;
        if (moduleKey) {
            out.push({
                key: moduleKey,
                kind: "module",
                parent_key: null,
                label: group.title,
                sort_order: base,
            });
        }

        // A top-level LINK (no `list`) that itself carries a feature_key becomes a
        // page node (e.g. AI Manager single link). If it also was the module above,
        // skip the duplicate.
        if (!group.list && group.feature_key && group.href) {
            // already pushed as a module above; also expose as a page so it locks
            // as a leaf the admin can toggle directly.
            out.push({
                key: `${group.feature_key}.page`,
                kind: "page",
                parent_key: group.feature_key,
                label: group.title,
                nav_href: group.href,
                sort_order: base + 1,
            });
            return;
        }

        (group.list || []).forEach((child, ci) => {
            if (child.roles === "admin") return; // admin-only child excluded
            if (!child.feature_key) return; // unkeyed (core) child → never lockable
            out.push({
                key: child.feature_key,
                kind: "page",
                parent_key: moduleKey,
                label: child.title,
                nav_href: child.href ?? null,
                sort_order: base + ci + 1,
            });
        });
    });

    out.push(...EXTRA_ACTION_NODES);
    return out;
}

// Merge the nav-derived nodes into an existing seed, ADDING only keys not already
// present (additive, dedup by key). The seed wins on label/parent for any key it
// already defines (preserves the backend-aligned authoring), so this purely fills
// the gaps the static seed missed.
export function mergeNavRegistry(
    seed: FeatureRegistryNode[]
): FeatureRegistryNode[] {
    const have = new Set(seed.map((n) => n.key));
    const additions = navDerivedRegistry().filter((n) => !have.has(n.key));
    // Dedup additions among themselves (a key can appear once).
    const seenAdd = new Set<string>();
    const uniqueAdditions = additions.filter((n) => {
        if (seenAdd.has(n.key)) return false;
        seenAdd.add(n.key);
        return true;
    });
    return [...seed, ...uniqueAdditions];
}
