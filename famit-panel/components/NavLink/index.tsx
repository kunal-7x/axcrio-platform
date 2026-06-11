import { useMemo } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "@/components/Icon";

type NavLinkProps = {
    value: {
        href: string;
        title: string;
        icon?: string;
        counter?: number;
    };
    onClick?: () => void;
};

const NavLink = ({ value, onClick }: NavLinkProps) => {
    const pathname = usePathname();

    // Active when the path equals the href OR is nested under it
    // (segment-boundary match so "/billing" never lights "/" and
    // "/calls" never lights "/callbacks").
    const isActive = useMemo(() => {
        if (value.href === "/") return pathname === "/";
        return (
            pathname === value.href ||
            pathname.startsWith(value.href + "/")
        );
    }, [pathname, value.href]);

    return (
        <Link
            className={`group relative flex items-center shrink-0 gap-3 h-12 px-3 text-button transition-colors hover:text-t-primary ${
                value.icon ? "h-12" : "h-11"
            } ${isActive ? "text-t-primary" : "text-t-secondary"}`}
            href={value.href}
            key={value.title}
            onClick={onClick}
        >
            {isActive && (
                <>
                    <div className="absolute inset-0 gradient-menu rounded-xl shadow-depth-menu">
                        <div className="absolute inset-0.25 bg-b-pop rounded-[0.6875rem]"></div>
                    </div>
                    {/* Signal accent — the brand through-line on the active item */}
                    <span className="nav-active-bar" aria-hidden />
                </>
            )}
            {value.icon && (
                <Icon
                    className={`relative z-2 transition-colors group-hover:fill-t-primary ${
                        isActive ? "fill-t-primary" : "fill-t-secondary"
                    }`}
                    name={value.icon}
                />
            )}
            <div className="relative z-2 mr-3">{value.title}</div>
            {value.counter && (
                <div className="relative z-2 flex justify-center items-center min-w-6 h-6 px-1.5 ml-auto rounded-lg bg-primary-01/12 text-button text-primary-01 tabular-nums">
                    {value.counter}
                </div>
            )}
        </Link>
    );
};

export default NavLink;
