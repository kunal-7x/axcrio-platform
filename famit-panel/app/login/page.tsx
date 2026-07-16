"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { login } from "@/lib/api";
import { seedMeFromLogin } from "@/lib/auth";
import { HapticMark } from "@/components/Logo";

// Premium split login (reference-aligned): a big white rounded card on the right
// (Welcome Back + form), a tall image hero card on the left ("Spark the Voice of
// AI"). The hero uses /images/login-hero.png if present, with a rich gradient
// fallback so it always looks premium. NOTE: this colourful hero is the ONE
// intentional exception to the app-wide monochrome system (it's the brand front
// door); everything inside the app stays monochrome.
export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [show, setShow] = useState(false);
    const [remember, setRemember] = useState(true);
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
        } catch (err) {
            setError(
                err instanceof Error && err.message
                    ? err.message
                    : "Invalid email or password. Please try again."
            );
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="min-h-screen w-full bg-white p-3 sm:p-4 lg:p-5">
            <div className="flex min-h-[calc(100vh-1.5rem)] sm:min-h-[calc(100vh-2rem)] gap-4 max-lg:gap-0">
                {/* ── Hero card (left) — the prism brand card, floating on white ── */}
                <aside className="relative hidden lg:flex w-[46%] max-2xl:w-[42%] rounded-[1.75rem] overflow-hidden">
                    {/* prism hero: real image if dropped at /images/login-hero.png, else a
                        premium iridescent gradient fallback. */}
                    <div
                        className="absolute inset-0"
                        aria-hidden
                        style={{
                            background:
                                "url('/images/login-hero.png') center/cover no-repeat, " +
                                "linear-gradient(150deg,#15102e 0%,#3a1d72 26%,#7b34c9 46%,#c8487f 64%,#3b2475 84%,#120b22 100%)",
                        }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-transparent to-black/25" aria-hidden />

                    <div className="relative flex flex-col justify-between p-10 text-white">
                        <div className="flex items-center gap-3 text-caption font-medium uppercase tracking-[0.22em] text-white/70">
                            Haptica AI
                            <span className="h-px w-12 bg-white/40" />
                        </div>

                        <div className="max-w-md">
                            <h2 className="font-serif text-[2.75rem] leading-[1.05] tracking-tight text-white">
                                Spark the voice of your business with Famit AI
                            </h2>
                            <p className="mt-4 text-body-2 text-white/65">
                                Launch campaigns, dial leads at scale, and watch every
                                conversation, outcome and rupee — in one console.
                            </p>
                        </div>
                    </div>
                </aside>

                {/* ── Sign-in panel (right) ── */}
                <main className="relative flex flex-1 flex-col bg-white text-[#0b0b0f]">
                    {/* brand top */}
                    <div className="flex justify-center pt-10">
                        <div className="flex items-center gap-2.5">
                            <span className="flex items-center justify-center size-8 rounded-xl bg-[#0b0b0f]">
                                <HapticMark className="size-5 text-white" />
                            </span>
                            <span className="flex flex-col leading-none">
                                <span className="text-button font-semibold tracking-[-0.02em] text-[#0b0b0f]">
                                    Haptica AI
                                </span>
                                <span className="mt-0.5 text-[0.5625rem] font-medium uppercase tracking-[0.14em] text-black/40">
                                    by Famit
                                </span>
                            </span>
                        </div>
                    </div>

                    <div className="flex flex-1 items-center justify-center px-6 py-10">
                        <div className="w-full max-w-[26rem]">
                            <h1 className="text-center font-serif text-[2.5rem] leading-tight tracking-tight text-[#0b0b0f]">
                                Welcome Back
                            </h1>
                            <p className="mt-2 mb-9 text-center text-body-2 text-black/50">
                                Enter your email and password to access your account
                            </p>

                            <form onSubmit={handleSubmit} className="space-y-5">
                                <div>
                                    <label className="block text-button mb-2 text-[#0b0b0f]">Email</label>
                                    <input
                                        type="email"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        className="w-full h-12 px-4 rounded-xl bg-[#f4f5f7] border border-transparent text-body-2 text-[#0b0b0f] placeholder:text-black/35 outline-none transition-colors focus:border-[#0b0b0f]/30 focus:bg-white"
                                        placeholder="Enter your email"
                                        required
                                        autoComplete="email"
                                    />
                                </div>

                                <div>
                                    <label className="block text-button mb-2 text-[#0b0b0f]">Password</label>
                                    <div className="relative">
                                        <input
                                            type={show ? "text" : "password"}
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            className="w-full h-12 pl-4 pr-12 rounded-xl bg-[#f4f5f7] border border-transparent text-body-2 text-[#0b0b0f] placeholder:text-black/35 outline-none transition-colors focus:border-[#0b0b0f]/30 focus:bg-white"
                                            placeholder="Enter your password"
                                            required
                                            autoComplete="current-password"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShow((s) => !s)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center justify-center size-7 rounded-md text-black/40 hover:text-black/70"
                                            aria-label={show ? "Hide password" : "Show password"}
                                        >
                                            {show ? "🙈" : "👁"}
                                        </button>
                                    </div>
                                </div>

                                <div className="flex items-center justify-between text-body-2">
                                    <label className="flex items-center gap-2 cursor-pointer text-black/60 select-none">
                                        <input
                                            type="checkbox"
                                            checked={remember}
                                            onChange={(e) => setRemember(e.target.checked)}
                                            className="size-4 rounded border-black/20 accent-[#0b0b0f]"
                                        />
                                        Remember me
                                    </label>
                                    <button
                                        type="button"
                                        onClick={() => setError("Password reset isn't available yet — contact your admin.")}
                                        className="font-medium text-[#0b0b0f] hover:opacity-70"
                                    >
                                        Forgot Password
                                    </button>
                                </div>

                                {error && (
                                    <div className="rounded-xl bg-[#fdecec] border border-[#f3c9c9] px-4 py-3 text-body-2 text-[#b42323]">
                                        {error}
                                    </div>
                                )}

                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="w-full h-12 rounded-xl bg-[#0b0b0f] text-white text-button transition-all hover:opacity-90 active:scale-[0.99] disabled:opacity-60"
                                >
                                    {loading ? "Signing in…" : "Sign In"}
                                </button>

                                <button
                                    type="button"
                                    onClick={() => setError("Google sign-in is coming soon — use email for now.")}
                                    className="w-full h-12 rounded-xl bg-white border border-black/15 text-button text-[#0b0b0f] inline-flex items-center justify-center gap-2.5 transition-colors hover:bg-black/[0.03]"
                                >
                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                    <img src="/images/google.svg" alt="" width={18} height={18} className="size-[18px]" />
                                    Sign In with Google
                                </button>
                            </form>

                            <p className="mt-10 text-center text-body-2 text-black/50">
                                Don&apos;t have an account?{" "}
                                <Link href="/signup" className="font-semibold text-[#0b0b0f] hover:opacity-70">
                                    Create one
                                </Link>
                            </p>
                        </div>
                    </div>
                </main>
            </div>
        </div>
    );
}
