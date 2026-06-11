"use client";

import Logo from "@/components/Logo";
import { RemoveScroll } from "react-remove-scroll";
import ThemeButton from "@/components/ThemeButton";
import NavLink from "@/components/NavLink";
import Button from "@/components/Button";
import Dropdown from "./Dropdown";

import { navigation } from "@/contstants/navigation";
import { useMe, isAdmin, canWrite } from "@/lib/auth";
import { useEntitlements, modeOfIn, type EntMode } from "@/lib/entitlements";
import type { EntitlementsPayload } from "@/lib/api";

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
};
type NavItem = {
    title: string;
    icon: string;
    href?: string;
    roles?: string;
    feature_key?: string;
    list?: NavChild[];
    section?: string;
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
    for (const item of items) {
        if (!navVisible(item, me)) continue;
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
    // While role is unknown (no cache yet), show only the always-visible items
    // to avoid flashing admin-only links to a vendor. Cache makes this instant
    // on subsequent loads. resolveNav also filters group CHILDREN by role +
    // entitlement (HIDE drops, LOCK dims), and drops a group left with no
    // visible children. The entitlement map defaults permissive (all-ON) until
    // it loads, so nav never flickers items away before we KNOW they're hidden.
    const entOf = (key?: string) => modeOfIn(payload as EntitlementsPayload, key);
    const items = resolveNav(navigation as NavItem[], me, entOf);
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
