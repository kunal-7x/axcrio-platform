"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { signupStart, signupVerify } from "@/lib/api";
import { seedMeFromLogin } from "@/lib/auth";
import { HapticMark } from "@/components/Logo";

const inputCls =
    "w-full h-12 px-4 rounded-xl bg-[#f4f5f7] border border-transparent text-body-2 text-[#0b0b0f] placeholder:text-black/35 outline-none transition-colors focus:border-[#0b0b0f]/30 focus:bg-white";

export default function SignupPage() {
    const router = useRouter();
    const [step, setStep] = useState<"details" | "otp">("details");
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [show, setShow] = useState(false);
    const [sentTo, setSentTo] = useState("");
    const [otp, setOtp] = useState(["", "", "", ""]);
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const boxes = useRef<Array<HTMLInputElement | null>>([]);

    async function startSignup(e: React.FormEvent) {
        e.preventDefault();
        setError("");
        setLoading(true);
        try {
            const r = await signupStart({ email, password, name });
            setSentTo(r.sent_to || email);
            setStep("otp");
            setOtp(["", "", "", ""]);
            setTimeout(() => boxes.current[0]?.focus(), 80);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Could not send the code.");
        } finally {
            setLoading(false);
        }
    }

    async function verify(code: string) {
        setError("");
        setLoading(true);
        try {
            const res = await signupVerify(email, code);
            localStorage.setItem("famit_token", res.token);
            seedMeFromLogin({ ...res, email });
            router.push("/");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Verification failed.");
            setOtp(["", "", "", ""]);
            setTimeout(() => boxes.current[0]?.focus(), 60);
        } finally {
            setLoading(false);
        }
    }

    function setDigit(i: number, v: string) {
        const d = v.replace(/\D/g, "");
        if (!d) {
            const next = [...otp];
            next[i] = "";
            setOtp(next);
            return;
        }
        const next = [...otp];
        // support pasting all 4 at once
        if (d.length > 1) {
            for (let k = 0; k < 4; k++) next[k] = d[k] || "";
            setOtp(next);
            const code = next.join("");
            if (code.length === 4) verify(code);
            else boxes.current[Math.min(d.length, 3)]?.focus();
            return;
        }
        next[i] = d;
        setOtp(next);
        if (i < 3) boxes.current[i + 1]?.focus();
        const code = next.join("");
        if (code.length === 4 && next.every((x) => x)) verify(code);
    }

    function onKey(i: number, e: React.KeyboardEvent<HTMLInputElement>) {
        if (e.key === "Backspace" && !otp[i] && i > 0) boxes.current[i - 1]?.focus();
    }

    async function resend() {
        setError("");
        try {
            await signupStart({ email, password, name });
            setOtp(["", "", "", ""]);
            boxes.current[0]?.focus();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Could not resend.");
        }
    }

    return (
        <div className="min-h-screen w-full bg-white p-3 sm:p-4 lg:p-5">
            <div className="flex min-h-[calc(100vh-1.5rem)] sm:min-h-[calc(100vh-2rem)] gap-4 max-lg:gap-0">
                {/* Hero (left) — same brand card as login */}
                <aside className="relative hidden lg:flex w-[46%] max-2xl:w-[42%] rounded-[1.75rem] overflow-hidden">
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
                                Create your account and launch your first AI calling campaign in minutes.
                            </p>
                        </div>
                    </div>
                </aside>

                {/* Form (right) */}
                <main className="relative flex flex-1 flex-col bg-white text-[#0b0b0f]">
                    <div className="flex justify-center pt-10">
                        <div className="flex items-center gap-2.5">
                            <span className="flex items-center justify-center size-8 rounded-xl bg-[#0b0b0f]">
                                <HapticMark className="size-5 text-white" />
                            </span>
                            <span className="flex flex-col leading-none">
                                <span className="text-button font-semibold tracking-[-0.02em] text-[#0b0b0f]">Haptica AI</span>
                                <span className="mt-0.5 text-[0.5625rem] font-medium uppercase tracking-[0.14em] text-black/40">by Famit</span>
                            </span>
                        </div>
                    </div>

                    <div className="flex flex-1 items-center justify-center px-6 py-10">
                        <div className="w-full max-w-[26rem]">
                            {step === "details" ? (
                                <>
                                    <h1 className="text-center font-serif text-[2.5rem] leading-tight tracking-tight">Create your account</h1>
                                    <p className="mt-2 mb-9 text-center text-body-2 text-black/50">
                                        We&apos;ll email you a 4-digit code to verify it&apos;s you.
                                    </p>
                                    <form onSubmit={startSignup} className="space-y-5">
                                        <div>
                                            <label className="block text-button mb-2">Name</label>
                                            <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" />
                                        </div>
                                        <div>
                                            <label className="block text-button mb-2">Email</label>
                                            <input type="email" required className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
                                        </div>
                                        <div>
                                            <label className="block text-button mb-2">Password</label>
                                            <div className="relative">
                                                <input
                                                    type={show ? "text" : "password"}
                                                    required
                                                    className="w-full h-12 pl-4 pr-12 rounded-xl bg-[#f4f5f7] border border-transparent text-body-2 text-[#0b0b0f] placeholder:text-black/35 outline-none transition-colors focus:border-[#0b0b0f]/30 focus:bg-white"
                                                    value={password}
                                                    onChange={(e) => setPassword(e.target.value)}
                                                    placeholder="At least 6 characters"
                                                    autoComplete="new-password"
                                                />
                                                <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center justify-center size-7 rounded-md text-black/40 hover:text-black/70" aria-label="Toggle password">
                                                    {show ? "🙈" : "👁"}
                                                </button>
                                            </div>
                                        </div>
                                        {error && (
                                            <div className="rounded-xl bg-[#fdecec] border border-[#f3c9c9] px-4 py-3 text-body-2 text-[#b42323]">{error}</div>
                                        )}
                                        <button type="submit" disabled={loading} className="w-full h-12 rounded-xl bg-[#0b0b0f] text-white text-button transition-all hover:opacity-90 active:scale-[0.99] disabled:opacity-60">
                                            {loading ? "Sending code…" : "Send verification code"}
                                        </button>
                                    </form>
                                    <p className="mt-10 text-center text-body-2 text-black/50">
                                        Already have an account?{" "}
                                        <Link href="/login" className="font-semibold text-[#0b0b0f] hover:opacity-70">Sign in</Link>
                                    </p>
                                </>
                            ) : (
                                <>
                                    <h1 className="text-center font-serif text-[2.5rem] leading-tight tracking-tight">Verify your email</h1>
                                    <p className="mt-2 mb-9 text-center text-body-2 text-black/50">
                                        Enter the 4-digit code we sent to <span className="font-semibold text-[#0b0b0f]">{sentTo}</span>
                                    </p>
                                    <div className="flex items-center justify-center gap-3">
                                        {otp.map((d, i) => (
                                            <input
                                                key={i}
                                                ref={(el) => {
                                                    boxes.current[i] = el;
                                                }}
                                                inputMode="numeric"
                                                maxLength={4}
                                                value={d}
                                                onChange={(e) => setDigit(i, e.target.value)}
                                                onKeyDown={(e) => onKey(i, e)}
                                                disabled={loading}
                                                className="size-16 max-sm:size-14 text-center text-[1.75rem] font-semibold rounded-2xl bg-[#f4f5f7] border-2 border-transparent text-[#0b0b0f] outline-none transition-all focus:border-[#0b0b0f] focus:bg-white disabled:opacity-60"
                                            />
                                        ))}
                                    </div>
                                    {error && (
                                        <div className="mt-5 rounded-xl bg-[#fdecec] border border-[#f3c9c9] px-4 py-3 text-body-2 text-[#b42323] text-center">{error}</div>
                                    )}
                                    <button
                                        type="button"
                                        disabled={loading || otp.join("").length !== 4}
                                        onClick={() => verify(otp.join(""))}
                                        className="mt-7 w-full h-12 rounded-xl bg-[#0b0b0f] text-white text-button transition-all hover:opacity-90 active:scale-[0.99] disabled:opacity-50"
                                    >
                                        {loading ? "Verifying…" : "Verify & create account"}
                                    </button>
                                    <div className="mt-5 flex items-center justify-center gap-4 text-body-2 text-black/50">
                                        <button type="button" onClick={() => { setStep("details"); setError(""); }} className="hover:text-[#0b0b0f]">← Change details</button>
                                        <span className="text-black/20">·</span>
                                        <button type="button" onClick={resend} className="font-medium text-[#0b0b0f] hover:opacity-70">Resend code</button>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </main>
            </div>
        </div>
    );
}
