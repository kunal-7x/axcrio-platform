import { useState, useEffect } from "react";
import Button from "@/components/Button";
import Select from "@/components/Select";
import Logo from "@/components/Logo";
import User from "./User";

const times = [
    { id: 1, name: "Publish now" },
    { id: 2, name: "Publish tomorrow" },
    { id: 3, name: "Publish later" },
];

type HeaderProps = {
    className?: string;
    title?: string;
    newProduct?: boolean;
    hideSidebar?: boolean;
    onToggleSidebar?: () => void;
};

const Header = ({
    className,
    title,
    newProduct,
    hideSidebar,
    onToggleSidebar,
}: HeaderProps) => {
    const [time, setTime] = useState(times[0]);
    const [hasOverflowHidden, setHasOverflowHidden] = useState(false);

    useEffect(() => {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.attributeName === "style") {
                    const htmlElement = document.documentElement;
                    const isOverflowHidden =
                        window.getComputedStyle(htmlElement).overflow ===
                        "hidden";
                    setHasOverflowHidden(isOverflowHidden);
                }
            });
        });

        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["style"],
        });

        return () => observer.disconnect();
    }, []);

    return (
        <header
            className={`fixed top-0 right-0 z-20 bg-b-surface1 max-lg:!right-0 ${
                hasOverflowHidden
                    ? "right-[calc(0px+var(--scrollbar-width))]"
                    : ""
            } ${
                hideSidebar
                    ? "left-0"
                    : "left-85 max-4xl:left-70 max-3xl:left-60 max-xl:left-0"
            } ${className || ""}`}
        >
            <div
                className={`flex items-center h-22 max-md:h-18 ${
                    hideSidebar ? "center max-w-full" : "center-with-sidebar"
                } ${
                    newProduct
                        ? "max-md:flex-wrap max-md:!h-auto max-md:p-3"
                        : ""
                }`}
            >
                <div
                    className={`mr-3 gap-3 max-md:mr-auto ${
                        hideSidebar ? "flex" : "hidden max-xl:flex"
                    }`}
                >
                    <Logo />
                    <Button
                        className="flex-col gap-[4.5px] shrink-0 before:w-4.5 before:h-[1.5px] before:rounded-full before:bg-t-secondary before:transition-colors after:w-4.5 after:h-[1.5px] after:rounded-full after:bg-t-secondary after:transition-colors hover:before:bg-t-primary hover:after:bg-t-primary"
                        onClick={onToggleSidebar}
                        isCircle
                        isWhite
                    />
                </div>
                {/* The page title is intentionally NOT rendered here — each page
                    shows its own <PageHeader> masthead below the navbar, so a
                    title in the navbar would duplicate it. */}
                <div
                    className={`flex items-center gap-3 ml-auto ${
                        newProduct ? "hidden max-md:flex" : ""
                    } ${
                        hideSidebar ? "grow max-lg:grow-0 max-lg:ml-auto justify-end" : ""
                    }`}
                >
                    {/* A real, working primary action: jump to Run a campaign.
                        (Replaces the template's dead "Create -> /products/new"
                        link + the non-functional global search.) */}
                    {!newProduct && (
                        <Button
                            className="max-md:hidden"
                            isBlack
                            href="/run"
                            as="link"
                            icon="send"
                        >
                            Run a Campaign
                        </Button>
                    )}
                    {/* Theme toggle removed from the top navbar (lives in the
                        sidebar footer / floating toggle instead). */}
                    <User />
                </div>
                {newProduct && (
                    <div className="flex items-center gap-3 max-md:gap-0 max-md:w-[calc(100%+0.75rem)] max-md:mt-3 max-md:-mx-1.5">
                        <Button
                            className="max-md:w-[calc(50%-0.75rem)] max-md:mx-1.5"
                            isWhite
                        >
                            Save draft
                        </Button>
                        <Select
                            className="min-w-36 max-md:w-[calc(50%-0.75rem)] max-md:mx-1.5"
                            value={time}
                            onChange={setTime}
                            options={times}
                            isBlack
                        />
                    </div>
                )}
            </div>
        </header>
    );
};

export default Header;
