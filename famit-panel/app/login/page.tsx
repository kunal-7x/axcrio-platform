"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { seedMeFromLogin } from "@/lib/auth";

export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            const res = await login(email, password);
            localStorage.setItem("famit_token", res.token);
            seedMeFromLogin({ ...res, email });
            router.push("/");
        } catch {
            setError("Invalid email or password. Please try again.");
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="min-h-screen flex bg-b-surface1">
            {/* ── Brand panel (left) — the signature, hidden on small screens ── */}
            <aside className="relative hidden lg:flex w-[44%] max-2xl:w-[40%] flex-col justify-between overflow-hidden bg-shade-01 p-12 text-shade-10">
                {/* atmosphere: brand glow + a faint signal grid */}
                <div className="absolute inset-0 brand-glow opacity-80" aria-hidden />
                <div
                    className="absolute inset-0 opacity-[0.06]"
                    aria-hidden
                    style={{
                        backgroundImage:
                            "linear-gradient(var(--primary-01) 1px, transparent 1px), linear-gradient(90deg, var(--primary-01) 1px, transparent 1px)",
                        backgroundSize: "44px 44px",
                    }}
                />
                <div
                    className="absolute -right-24 -top-24 size-72 rounded-full blur-3xl opacity-30"
                    aria-hidden
                    style={{ background: "var(--primary-01)" }}
                />

                {/* wordmark */}
                <div className="relative flex items-center gap-3">
                    <span className="relative flex items-center justify-center size-11 rounded-2xl bg-white/5 ring-1 ring-white/10 overflow-hidden">
                        <span className="signal-glyph relative" aria-hidden>
                            <i />
                            <i />
                            <i />
                            <i />
                        </span>
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-h5 font-semibold tracking-[-0.02em] text-white">
                        Famit
                        <span className="size-1.5 rounded-full bg-primary-01 mb-3 shadow-[0_0_8px_0_var(--primary-01)]" />
                    </span>
                </div>

                {/* headline */}
                <div className="relative max-w-md">
                    <h2 className="text-h3 font-semibold tracking-[-0.02em] text-white">
                        AI voice agents that
                        <br />
                        actually sell.
                    </h2>
                    <p className="mt-4 text-body-1 text-white/55">
                        Launch campaigns, dial leads at scale, and watch every
                        conversation, outcome and rupee in one console.
                    </p>

                    <div className="mt-8 flex flex-wrap gap-2.5">
                        {["Live call analytics", "Per-campaign voices", "A/B testing", "Real cost metering"].map(
                            (f) => (
                                <span
                                    key={f}
                                    className="inline-flex items-center gap-2 h-8 px-3 rounded-full bg-white/5 ring-1 ring-white/10 text-caption text-white/70"
                                >
                                    <span className="size-1.5 rounded-full bg-primary-01" />
                                    {f}
                                </span>
                            )
                        )}
                    </div>
                </div>

                <div className="relative text-caption text-white/40">
                    © {new Date().getFullYear()} Famit · AI Tele-Calling Platform
                </div>
            </aside>

            {/* ── Sign-in panel (right) ── */}
            <main className="relative flex flex-1 items-center justify-center p-6">
                <div className="w-full max-w-sm rise-in">
                    {/* compact wordmark for small screens */}
                    <div className="mb-8 flex items-center gap-2.5 lg:hidden">
                        <span className="relative flex items-center justify-center size-10 rounded-2xl bg-shade-01 overflow-hidden ring-1 ring-s-subtle">
                            <span className="absolute inset-0 brand-glow opacity-60" aria-hidden />
                            <span className="signal-glyph relative" aria-hidden>
                                <i />
                                <i />
                                <i />
                                <i />
                            </span>
                        </span>
                        <span className="wordmark text-h6">
                            Famit
                            <span className="size-1.5 rounded-full bg-primary-01 -ml-0.5 mb-3" />
                        </span>
                    </div>

                    <div className="page-head-eyebrow mb-2">
                        <span className="signal-glyph !h-3" aria-hidden>
                            <i />
                            <i />
                            <i />
                        </span>
                        Welcome back
                    </div>
                    <h1 className="text-h4 text-t-primary">Sign in to Famit</h1>
                    <p className="mt-2 mb-8 text-body-2 text-t-secondary">
                        Enter your credentials to access the panel.
                    </p>

                    <form onSubmit={handleSubmit} className="space-y-5">
                        <div>
                            <label className="block text-button mb-2.5 text-t-primary">
                                Email
                            </label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="input-base w-full h-12 px-4.5 rounded-2xl text-body-2"
                                placeholder="you@company.com"
                                required
                                autoComplete="email"
                            />
                        </div>

                        <div>
                            <label className="block text-button mb-2.5 text-t-primary">
                                Password
                            </label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="input-base w-full h-12 px-4.5 rounded-2xl text-body-2"
                                placeholder="Enter password"
                                required
                                autoComplete="current-password"
                            />
                        </div>

                        {error && (
                            <div className="toast toast-error !mb-0">
                                <span className="flex items-center gap-2">
                                    <span className="size-1.5 rounded-full bg-current" />
                                    {error}
                                </span>
                            </div>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="group relative w-full inline-flex items-center justify-center gap-2 h-12 px-7 rounded-2xl text-button cursor-pointer transition-all active:scale-[0.99] disabled:pointer-events-none disabled:opacity-60 bg-linear-to-b from-[#2C2C2C] to-[#282828] shadow-[inset_2px_0px_8px_2px_rgba(248,248,248,0.20)] text-t-light fill-t-light after:absolute after:inset-0 after:border-[1.5px] after:border-white/20 after:rounded-2xl after:[mask-image:linear-gradient(to_top,transparent_0,black_100%)] hover:shadow-none dark:from-shade-10 dark:to-[#DEDEDE]"
                        >
                            {loading && (
                                <svg
                                    className="animate-spin h-4 w-4"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                >
                                    <circle
                                        className="opacity-25"
                                        cx="12"
                                        cy="12"
                                        r="10"
                                        stroke="currentColor"
                                        strokeWidth="4"
                                    />
                                    <path
                                        className="opacity-75"
                                        fill="currentColor"
                                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                                    />
                                </svg>
                            )}
                            {loading ? "Signing in..." : "Sign in"}
                        </button>
                    </form>

                    <p className="mt-8 text-caption text-t-tertiary">
                        Secured access · contact your administrator for an account.
                    </p>
                </div>
            </main>
        </div>
    );
}
