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
        <div className="min-h-screen flex items-center justify-center bg-b-surface1">
            <div className="w-full max-w-sm">
                <div className="mb-8 text-center">
                    <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-linear-to-br from-[#2C2C2C] to-[#1a1a1a] text-white text-2xl font-bold mb-4 dark:from-shade-07 dark:to-shade-08">
                        F
                    </div>
                    <h1 className="text-h4 text-t-primary">Famit</h1>
                    <p className="mt-2 text-body-2 text-t-secondary">
                        AI Tele-Calling Panel
                    </p>
                </div>

                <div className="card p-8">
                    <h2 className="text-h6 mb-6 text-t-primary">Sign in</h2>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label className="block text-button mb-3 text-t-primary">
                                Email
                            </label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full h-12 px-4.5 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
                                placeholder="you@company.com"
                                required
                                autoComplete="email"
                            />
                        </div>

                        <div>
                            <label className="block text-button mb-3 text-t-primary">
                                Password
                            </label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full h-12 px-4.5 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent"
                                placeholder="Enter password"
                                required
                                autoComplete="current-password"
                            />
                        </div>

                        {error && (
                            <p className="text-caption text-red-500">{error}</p>
                        )}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full inline-flex items-center justify-center h-12 px-7 border-0 rounded-3xl text-button transition-all cursor-pointer disabled:pointer-events-none relative bg-linear-to-b from-[#2C2C2C] to-[#282828] shadow-[inset_2px_0px_8px_2px_rgba(248,248,248,0.20)] text-t-light fill-t-light after:absolute after:inset-0 after:border-[1.5px] after:border-white/20 after:rounded-3xl after:[mask-image:linear-gradient(to_top,transparent_0,black_100%)] dark:from-shade-10 dark:to-[#DEDEDE] gap-2"
                        >
                            {loading && (
                                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                                </svg>
                            )}
                            {loading ? "Signing in..." : "Sign in"}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}
