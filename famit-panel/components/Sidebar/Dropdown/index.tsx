import { useState } from "react";
import { usePathname } from "next/navigation";
import AnimateHeight from "react-animate-height";
import Icon from "@/components/Icon";
import NavLink from "@/components/NavLink";

type DropdownChild = {
    title: string;
    href?: string;
    counter?: number;
    comingSoon?: boolean;
    roles?: string;
    // CL-F0: set by Sidebar/resolveNav when this child's feature_key resolves to
    // LOCK. Renders the dimmed non-link row with a "Locked" pill (mirrors the
    // comingSoon precedent). Cosmetic — the backend 402 is the real lock.
    locked?: boolean;
    // Stage pill (Super-Admin Sidebar Builder, applyNavConfig): cosmetic
    // "Beta"/"Premium" label on an otherwise-normal child.
    _stage?: "beta" | "premium";
};

type DropdownProps = {
    value: {
        title: string;
        icon: string;
        href?: string;
        list?: DropdownChild[];
    };
};

const Dropdown = ({ value }: DropdownProps) => {
    const pathname = usePathname();
    // Active if the current path equals a child href or is nested under it
    // (segment-boundary match, so "/billing/vendors" does NOT activate the
    // "/vendors" child — avoids two groups co-expanding on prefix collisions).
    const isActive = value.list?.some(
        (item) =>
            item.href &&
            (pathname === item.href ||
                pathname.startsWith(item.href + "/"))
    );
    const [height, setHeight] = useState<number | "auto">(
        isActive ? "auto" : 0
    );
    const isOpen = height !== 0;

    return (
        <div className="relative">
            <button
                className={`group relative flex items-center gap-3 w-full h-12 px-3 text-button transition-colors hover:text-t-primary ${
                    isOpen || isActive ? "text-t-primary" : "text-t-secondary"
                }`}
                onClick={() => setHeight(isOpen ? 0 : "auto")}
                aria-expanded={isOpen}
            >
                {/* A collapsed group whose route is active shows a quiet signal
                    dot so the operator can see which section they're in even
                    when it's folded shut. */}
                {isActive && !isOpen && (
                    <span
                        className="absolute left-0 top-1/2 -translate-y-1/2 size-1.5 rounded-full bg-primary-01 shadow-[0_0_8px_-1px_var(--primary-01)]"
                        aria-hidden
                    />
                )}
                <Icon
                    className={`relative z-2 transition-colors group-hover:fill-t-primary ${
                        isOpen || isActive ? "fill-t-primary" : "fill-t-secondary"
                    }`}
                    name={value.icon}
                />
                <div className="relative z-2">{value.title}</div>
                <Icon
                    className={`relative z-2 ml-auto transition-transform duration-300 group-hover:fill-t-primary ${
                        isOpen ? "fill-t-primary rotate-180" : "fill-t-secondary"
                    }`}
                    name="chevron"
                />
            </button>
            <AnimateHeight duration={500} height={height}>
                <div className="relative flex flex-col pl-9 before:absolute before:top-0 before:left-[1.4375rem] before:bottom-12 before:w-[1.5px] before:bg-s-stroke2">
                    {value.list?.map((item) => (
                        <div className="relative" key={item.title}>
                            <div className="absolute top-0 -left-[0.8125rem] bottom-[calc(50%-0.75px)] w-[0.8125rem] border-l border-b border-s-stroke2 rounded-bl-[10px]"></div>
                            {item.comingSoon || item.locked || !item.href ? (
                                // Dimmed, non-clickable row. Two cases share this
                                // branch (deliberately NOT a <Link> so it can
                                // never navigate to a route the user can't use):
                                //   • comingSoon -> "Soon" pill (unbuilt route)
                                //   • locked     -> "Locked" pill (entitlement
                                //     LOCK; backend 402s the route — upsell). The
                                //     pill carries a calm amber cue, distinct
                                //     from the brand-blue roadmap "Soon".
                                <div
                                    className="flex items-center gap-2 h-11 px-3 text-button text-t-secondary/45 cursor-default select-none"
                                    aria-disabled="true"
                                    title={item.locked ? "Locked — upgrade to unlock" : undefined}
                                >
                                    <span className="truncate">{item.title}</span>
                                    {item.locked ? (
                                        <span className="nav-locked ml-auto">Locked</span>
                                    ) : (
                                        <span className="nav-soon ml-auto">Soon</span>
                                    )}
                                </div>
                            ) : (
                                <NavLink
                                    value={{
                                        title: item.title,
                                        href: item.href,
                                        counter: item.counter,
                                        badge: item._stage,
                                    }}
                                    onClick={() => setHeight("auto")}
                                />
                            )}
                        </div>
                    ))}
                </div>
            </AnimateHeight>
        </div>
    );
};

export default Dropdown;
