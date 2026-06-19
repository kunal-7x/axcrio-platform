import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    Menu,
    MenuButton,
    MenuItem,
    MenuItems,
    MenuSeparator,
} from "@headlessui/react";
import Image from "@/components/Image";
import Icon from "@/components/Icon";
import Modal from "@/components/Modal";
import Login from "@/components/Login";
import { navigationUser } from "@/contstants/navigation";
// ROUND-6 LANE 4 — the navbar avatar mirrors the user's chosen Profile photo /
// preset / emoji (lib/profile), updating live when Settings saves (same-tab event
// + cross-tab storage event). Falls back to the template avatar when unset.
import { getProfile, avatarSrc, PROFILE_EVENT, type Profile } from "@/lib/profile";

const User = ({}) => {
    const [isOpen, setIsOpen] = useState(false);
    const pathname = usePathname();
    const isActive = (href: string) => pathname === href;

    // Live profile (hydrated client-side; SSR renders the default to avoid a flash).
    const [profile, setProfile] = useState<Profile | null>(null);
    useEffect(() => {
        const sync = () => setProfile(getProfile());
        sync();
        window.addEventListener(PROFILE_EVENT, sync);
        window.addEventListener("storage", sync);
        return () => {
            window.removeEventListener(PROFILE_EVENT, sync);
            window.removeEventListener("storage", sync);
        };
    }, []);
    const isEmoji = profile?.avatarKind === "emoji";
    const customSrc = profile ? avatarSrc(profile) : "";

    return (
        <>
            <Menu className="group" as="div">
                <div className="fixed inset-0 z-30 bg-b-surface1/70 invisible opacity-0 transition-all group-[[data-open]]:visible group-[[data-open]]:opacity-100"></div>
                <MenuButton className="relative z-40 w-12 h-12 rounded-full overflow-hidden transition-colors after:absolute after:inset-[0.09375rem] after:border-[0.15625rem] after:border-b-surface2 after:rounded-full data-[hover]:bg-primary-01 data-[active]:bg-primary-01">
                    {isEmoji ? (
                        <span className="grid place-items-center size-10 rounded-full bg-b-surface1 text-xl mx-auto">
                            {profile?.emoji}
                        </span>
                    ) : customSrc && customSrc.startsWith("data:") ? (
                        // Uploaded photo (data URL) — Next/Image can't optimize a
                        // data URL, so render a plain <img>.
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                            className="size-10 rounded-full object-cover opacity-100 mx-auto"
                            src={customSrc}
                            width={40}
                            height={40}
                            alt="avatar"
                        />
                    ) : (
                        <Image
                            className="size-10 rounded-full object-cover opacity-100"
                            src={customSrc || "/images/avatar-sm.png"}
                            width={40}
                            height={40}
                            alt="avatar"
                            priority={true}
                            quality={100}
                        />
                    )}
                </MenuButton>
                <MenuItems
                    className="z-100 w-67.5 p-3 rounded-4xl bg-b-surface2 border-1 border-s-subtle outline-none shadow-dropdown [--anchor-gap:0.625rem] [--anchor-offset:0.625rem] origin-top transition duration-300 ease-out data-[closed]:scale-95 data-[closed]:opacity-0 max-md:w-[calc(100vw-1.5rem)] max-md:[--anchor-offset:0]"
                    anchor="bottom end"
                    transition
                >
                    {navigationUser.map((link, index) => (
                        <MenuItem key={index}>
                            <Link
                                className={`group/item relative flex items-center h-12 px-3 text-button text-t-secondary transition-colors data-[focus]:text-t-primary before:absolute before:inset-0 before:rounded-[16px] before:bg-linear-to-b before:from-shade-09 before:to-[#ebebeb] before:opacity-0 before:transition-opacity after:absolute after:inset-0.25 after:bg-b-pop after:rounded-[15px] after:opacity-0 after:transition-opacity ${
                                    link.title === "Upgrade to Pro"
                                        ? "!text-primary-01"
                                        : ""
                                } ${
                                    isActive(link.href)
                                        ? "!text-t-primary before:opacity-100 after:opacity-100 dark:before:opacity-[0.075]"
                                        : ""
                                }`}
                                href={link.href}
                            >
                                <Icon
                                    className={`relative z-2 mr-4 fill-t-secondary transition-colors group-[[data-focus]]/item:fill-t-primary ${
                                        link.title === "Upgrade to Pro"
                                            ? "!fill-primary-01"
                                            : ""
                                    } ${
                                        isActive(link.href)
                                            ? "!fill-t-primary"
                                            : ""
                                    }`}
                                    name={link.icon}
                                />
                                <div className="relative z-2">{link.title}</div>
                            </Link>
                        </MenuItem>
                    ))}
                    <MenuSeparator className="-mx-3 my-3 h-px bg-s-subtle" />
                    <MenuItem>
                        <button
                            className="group/item flex items-center w-full h-12 px-3 text-button text-t-secondary transition-colors data-[focus]:text-t-primary"
                            onClick={() => setIsOpen(true)}
                        >
                            <Icon
                                className="mr-4 fill-t-secondary transition-colors group-[[data-focus]]/item:fill-t-primary"
                                name="logout"
                            />
                            Log out
                        </button>
                    </MenuItem>
                </MenuItems>
            </Menu>
            <Modal
                classWrapper="!max-w-120 p-16 bg-b-surface2"
                open={isOpen}
                onClose={() => setIsOpen(false)}
            >
                <Login />
            </Modal>
        </>
    );
};

export default User;
