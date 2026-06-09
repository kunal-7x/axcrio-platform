"use client";

import { ThemeProvider } from "next-themes";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

function AuthGuard({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();

    useEffect(() => {
        if (pathname === "/login") return;
        const token = localStorage.getItem("famit_token");
        if (!token) {
            router.replace("/login");
        }
    }, [pathname, router]);

    return <>{children}</>;
}

const Providers = ({ children }: { children: React.ReactNode }) => {
    return (
        <ThemeProvider disableTransitionOnChange>
            <AuthGuard>{children}</AuthGuard>
        </ThemeProvider>
    );
};

export default Providers;
