"use client";

import { useEffect, useState } from "react";
import Logo from "@/components/Logo";
import { RemoveScroll } from "react-remove-scroll";
import ThemeButton from "@/components/ThemeButton";
import NavLink from "@/components/NavLink";
import Button from "@/components/Button";
import Dropdown from "./Dropdown";

import { navigation } from "@/contstants/navigation";
import { useMe, isAdmin, canWrite } from "@/lib/auth";
import { useEntitlements, modeOfIn, type EntMode } from "@/lib/entitlements";
import { getMyNavConfig, type EntitlementsPayload, type NavConfig } from "@/lib/api";

// Stable nav keys — MUST match the Super-Admin Sidebar Builder so the saved config
// lines up with what the sidebar renders. Top-level: href, else "group:<title>".
export function navKey(item: { href?: string; title: string }): string {
    return item.href ? item.href : "group:" + item.title;
}
export function childKey(c: { href?: string; title: string }): string {
    return c.href ? c.href : c.title;
}

// Apply a per-tenant sidebar config (from /me/nav-config) ON TOP of the already
// role+entitlement-resolved nav. Supports: HIDE, RELABEL, REORDER (top-level +
// children), MOVE a child to a different category (parentOf), and admin-CREATED
// links/sections (custom). Empty/absent config -> unchanged default nav. Cosmetic
// only — the backend 404/402 choke-point stays the real boundary.
function applyNavConfig(items: NavItem[], cfg: NavConfig | null): NavItem[] {
    if (!cfg) return items;
    const hidden = new Set(cfg.hidden || []);
    // "Unavailable" (Sidebar Builder) = not exposed to the end user → fold into
    // the hidden set so the item never renders for them.
    for (const k of cfg.unavailable || []) hidden.add(k);
    const stage = cfg.stage || {}; // key -> "beta" | "premium" (cosmetic pill)
    const labels = cfg.labels || {};
    const childOrder = cfg.childOrder || {};
    const order = cfg.order || [];
    const parentOf = cfg.parentOf || {};
    const custom = cfg.custom || [];
    const has =
        hidden.size ||
        order.length ||
        Object.keys(labels).length ||
        Object.keys(childOrder).length ||
        Object.keys(parentOf).length ||
        Object.keys(stage).length ||
        custom.length;
    if (!has) return items;

    const sk = (s: NavItem) => s._navKey || navKey(s);
    const ck = (c: NavChild) => c._navKey || childKey(c);

    // clone sections + tag with stable keys; copy lists so children can be moved
    const sections: NavItem[] = items.map((it) => ({
        ...it,
        _navKey: navKey(it),
        list: it.list ? it.list.map((c) => ({ ...c, _navKey: childKey(c) })) : undefined,
    }));
    const byKey = new Map<string, NavItem>();
    for (const s of sections) byKey.set(sk(s), s);

    // custom SECTIONS -> new top-level groups (empty, filled in the redistribute pass)
    for (const c of custom) {
        if (c.isSection && !byKey.has(c.key)) {
            const sec: NavItem = { title: c.label, icon: c.icon || "grid", list: [], _navKey: c.key };
            sections.push(sec);
            byKey.set(c.key, sec);
        }
    }

    // pool every child with its current parent, add custom LINKS, then redistribute
    // by parentOf (move-to-another-category). Falls back to the original parent if a
    // target section no longer exists.
    const pool: { child: NavChild; from: string }[] = [];
    for (const s of sections) {
        if (s.list) {
            for (const c of s.list) pool.push({ child: c, from: sk(s) });
            s.list = [];
        }
    }
    for (const c of custom) {
        if (!c.isSection && c.href) {
            pool.push({ child: { title: c.label, href: c.href, _navKey: c.key }, from: c.parent || "" });
        }
    }
    for (const { child, from } of pool) {
        const target = parentOf[ck(child)] || from;
        const sec = byKey.get(target) || byKey.get(from);
        if (sec && sec.list) sec.list.push(child);
    }

    // hide + relabel + child order + drop empty groups
    const asStage = (v: unknown): "beta" | "premium" | undefined =>
        v === "beta" || v === "premium" ? v : undefined;
    let out: NavItem[] = [];
    for (const s of sections) {
        const key = sk(s);
        if (hidden.has(key)) continue;
        const next: NavItem = { ...s };
        if (labels[key]) next.title = labels[key];
        const secStage = asStage(stage[key]);
        if (secStage) next._stage = secStage;
        if (next.list) {
            let kids = next.list
                .filter((c) => !hidden.has(ck(c)))
                .map((c) => {
                    const st = asStage(stage[ck(c)]);
                    const relabel = labels[ck(c)] ? { title: labels[ck(c)] } : null;
                    return relabel || st ? { ...c, ...(relabel || {}), ...(st ? { _stage: st } : {}) } : c;
                });
            const co = childOrder[key];
            if (co && co.length) {
                const ci = (c: NavChild) => {
                    const i = co.indexOf(ck(c));
                    return i === -1 ? 999 : i;
                };
                kids = [...kids].sort((a, b) => ci(a) - ci(b));
            }
            if (kids.length === 0) continue; // group emptied by hiding/moving
            next.list = kids;
        }
        out.push(next);
    }

    // top-level order (stable: unlisted keep relative order)
    if (order.length) {
        const oi = (it: NavItem) => {
            const i = order.indexOf(sk(it));
            return i === -1 ? 999 : i;
        };
        out = [...out].sort((a, b) => oi(a) - oi(b));
    }
    return out;
}

type SidebarProps = {
    visibleSidebar?: boolean;
    hideSidebar?: boolean;
    onCloseSidebar?: () => void;
};

// Decide if a nav item (top-level OR a group child) is visible for the role.
// `roles: "admin"`   -> admins only
// `roles: "manager"` -> managers + admins (hidden for read-only agents)
// no `roles`         -> everyone
function navVisible(item: { roles?: string }, me: ReturnType<typeof useMe>["me"]): boolean {
    if (!item.roles) return true;
    if (item.roles === "admin") return isAdmin(me);
    if (item.roles === "manager") return canWrite(me);
    return true;
}

type NavChild = {
    title: string;
    href?: string;
    comingSoon?: boolean;
    roles?: string;
    // CL-F0: the registry feature_key gating this child. HIDE drops it; LOCK
    // marks it `locked` so the Dropdown renders the dimmed "Locked" pill.
    feature_key?: string;
    // Injected by resolveNav when feature_key resolves to LOCK (not authored).
    locked?: boolean;
    // Stable nav key (applyNavConfig) — preserves identity for custom/moved items.
    _navKey?: string;
    // Stage pill (applyNavConfig, from the per-tenant nav config): cosmetic
    // "Beta"/"Premium" label set in the Super-Admin Sidebar Builder.
    _stage?: "beta" | "premium";
};
type NavItem = {
    title: string;
    icon: string;
    href?: string;
    roles?: string;
    feature_key?: string;
    list?: NavChild[];
    section?: string;
    _navKey?: string;
    _stage?: "beta" | "premium";
};

// Entitlement resolver passed into the (otherwise pure) resolveNav. Maps a
// feature_key -> "ON" | "LOCK" | "HIDE" off the current entitlement payload.
type EntResolver = (key?: string) => EntMode;

// Filter a nav entry for the current role AND entitlement:
//  - top-level gated entries hidden as before (role);
//  - a COLLAPSIBLE GROUP has its CHILDREN filtered by their own `roles` AND
//    entitlement: a child whose feature_key resolves to HIDE is dropped exactly
//    like an out-of-role child; a child resolving to LOCK survives but is
//    flagged `locked` (the Dropdown renders the dimmed "Locked" pill). The whole
//    group is dropped if no visible children remain, OR if the group's own
//    feature_key resolves to HIDE. Coming-soon children carry no key and always
//    survive. ENT FILTER IS COSMETIC — the backend 404/402 is the real boundary.
function resolveNav(
    items: NavItem[],
    me: ReturnType<typeof useMe>["me"],
    entOf: EntResolver
): NavItem[] {
    const out: NavItem[] = [];
    const restricted = new Set(me?.restricted || []);
    for (const item of items) {
        if (!navVisible(item, me)) continue;
        // Per-client restriction (set by Super Admin -> Clients): hide whole sections.
        if (restricted.has(item.title) || (item.feature_key && restricted.has(item.feature_key))) continue;
        if (entOf(item.feature_key) === "HIDE") continue; // whole group hidden
        if (item.list) {
            const list: NavChild[] = [];
            for (const c of item.list) {
                if (!navVisible(c, me)) continue;
                const m = entOf(c.feature_key);
                if (m === "HIDE") continue; // dropped like an out-of-role child
                list.push(m === "LOCK" ? { ...c, locked: true } : c);
            }
            if (list.length === 0) continue;
            out.push({ ...item, list });
        } else {
            out.push(item);
        }
    }
    return out;
}

const Sidebar = ({
    visibleSidebar,
    hideSidebar,
    onCloseSidebar,
}: SidebarProps) => {
    const { me } = useMe();
    const { payload } = useEntitlements();
    // Per-tenant sidebar config (Super-Admin Sidebar Builder). Null until loaded =
    // render the default nav; applied (hide/reorder/relabel) once it arrives.
    const [navCfg, setNavCfg] = useState<NavConfig | null>(null);
    useEffect(() => {
        let alive = true;
        getMyNavConfig()
            .then((r) => {
                if (alive) setNavCfg(r.config || {});
            })
            .catch(() => {});
        return () => {
            alive = false;
        };
    }, []);
    // While role is unknown (no cache yet), show only the always-visible items
    // to avoid flashing admin-only links to a vendor. Cache makes this instant
    // on subsequent loads. resolveNav also filters group CHILDREN by role +
    // entitlement (HIDE drops, LOCK dims), and drops a group left with no
    // visible children. The entitlement map defaults permissive (all-ON) until
    // it loads, so nav never flickers items away before we KNOW they're hidden.
    const entOf = (key?: string) => modeOfIn(payload as EntitlementsPayload, key);
    const items = applyNavConfig(resolveNav(navigation as NavItem[], me, entOf), navCfg);
    return (
    <div
        className={`fixed top-0 left-0 bottom-0 flex flex-col w-85 p-5 bg-b-surface1 transition-transform duration-300 max-4xl:w-70 max-3xl:w-60 max-xl:w-74 max-md:p-3 ${
            visibleSidebar
                ? `${
                      hideSidebar
                          ? "z-40 translate-x-0"
                          : "max-xl:z-40 max-xl:translate-x-0"
                  }`
                : `${
                      hideSidebar
                          ? "z-40 -translate-x-full"
                          : "max-xl:z-40 max-xl:-translate-x-full"
                  }`
        }`}
    >
        <Logo className="mb-5" />
        <Button
            className={`group absolute top-5 right-5 max-md:top-3 max-md:right-3 ${
                hideSidebar ? "flex" : "!hidden max-xl:!flex"
            }`}
            icon="close"
            onClick={onCloseSidebar}
            isCircle
            isWhite
        />
        <RemoveScroll
            className="flex flex-col gap-1 grow overflow-auto -mx-5 px-5 scrollbar scrollbar-thin scrollbar-thumb-t-tertiary/30 scrollbar-track-transparent max-md:-mx-3 max-md:px-3"
            enabled={visibleSidebar}
        >
            {items.map((item) => (
                <div key={item.title} className="contents">
                    {item.href ? (
                        <NavLink
                            value={{
                                title: item.title,
                                href: item.href,
                                icon: item.icon,
                                badge: item._stage,
                            }}
                        />
                    ) : (
                        <Dropdown value={item} />
                    )}
                </div>
            ))}
        </RemoveScroll>
        <div className="mt-auto pt-6 max-md:pt-4 border-t border-s-subtle">
            <ThemeButton
                className={`mt-4 ${hideSidebar ? "hidden max-lg:block" : ""}`}
            />
        </div>
    </div>
    );
};

export default Sidebar;
