"use client";

// ============================================================================
// WAVE C · Provider-lock banner — the founder's #1 demand, made HONEST + visible.
//
// Shows the exact {STT · LLM · TTS} + voice triple that the campaign is CONFIGURED
// to run, with one of three truthful states (RUN-PLATFORM-MASTER-PLAN §5):
//
//   • CONFIG-ONLY  (today's truth, default): "You selected these. Voice + tier are
//     saved now. The live OUTBOUND engine still honours its configured provider
//     until the provider-lock wave ships (founder sign-off + clean DID)."
//   • LIVE         (ob_prov_live:true): "This triple runs AND is billed every call."
//   • MISMATCH     (Run-Report only — not surfaced here yet).
//
// Inbound provider-lock is label-truthful NOW; OUTBOUND honoring is gated. We say
// so plainly. Token-pure Core_2 (Inter Display, zero raw hex). Dormant-safe: with
// no resolved providers it shows a calm "—" row, never an error.
// ============================================================================

import Icon from "@/components/Icon";

export type ProviderLockState = "config-only" | "live";

type Chip = { role: string; label: string; provider: string };

type Props = {
    state: ProviderLockState;
    stt: string;
    llm: string;
    tts: string;
    voice: string; // resolved voice name (falls back to id)
    // true when the inbound provider-lock label is already live (session-log truthful)
    inboundLive?: boolean;
};

function pretty(p: string): string {
    const s = (p || "").toLowerCase();
    if (s.includes("eleven")) return "ElevenLabs";
    if (s.includes("sarvam")) return "Sarvam";
    if (s.includes("groq")) return "Groq";
    if (s.includes("deepgram")) return "Deepgram";
    if (!p) return "—";
    return p.charAt(0).toUpperCase() + p.slice(1);
}

export default function ProviderLock({
    state,
    stt,
    llm,
    tts,
    voice,
    inboundLive,
}: Props) {
    const live = state === "live";

    const chips: Chip[] = [
        { role: "STT", label: pretty(stt), provider: stt },
        { role: "LLM", label: pretty(llm), provider: llm },
        { role: "TTS", label: pretty(tts), provider: tts },
    ];

    return (
        <div
            className={`rounded-2xl border p-4 ${
                live
                    ? "border-primary-02/30 bg-primary-02/8"
                    : "border-s-subtle bg-b-surface1 dark:bg-shade-04/30"
            }`}
        >
            {/* header row: state pill + headline */}
            <div className="flex items-center justify-between gap-3 mb-3">
                <div className="flex items-center gap-2">
                    <span
                        className={`grid place-items-center size-7 rounded-full ${
                            live
                                ? "bg-primary-02/15 text-primary-02"
                                : "bg-b-surface2 text-t-secondary"
                        }`}
                    >
                        <Icon
                            name={live ? "check-circle-fill" : "lock"}
                            className="size-4 fill-current"
                        />
                    </span>
                    <div className="leading-tight">
                        <div className="text-button text-t-primary">
                            Provider lock
                        </div>
                        <div className="text-caption text-t-tertiary">
                            What this campaign is set to run
                        </div>
                    </div>
                </div>
                <span
                    className={`inline-flex items-center gap-1.5 h-7 px-2.5 rounded-full text-caption font-medium ${
                        live
                            ? "bg-primary-02/15 text-primary-02"
                            : "bg-b-surface2 text-t-secondary border border-s-subtle"
                    }`}
                >
                    <span
                        className={`size-1.5 rounded-full ${
                            live ? "bg-primary-02" : "bg-primary-05"
                        }`}
                    />
                    {live ? "LIVE" : "CONFIG-ONLY"}
                </span>
            </div>

            {/* the resolved triple + voice */}
            <div className="flex flex-wrap items-center gap-2">
                {chips.map((c) => (
                    <span
                        key={c.role}
                        className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full bg-b-surface2 border border-s-subtle text-caption"
                    >
                        <span className="text-t-tertiary">{c.role}</span>
                        <span className="text-t-primary font-medium">
                            {c.label}
                        </span>
                    </span>
                ))}
                {voice && (
                    <span className="inline-flex items-center gap-1.5 h-8 px-3 rounded-full bg-primary-01/8 border border-primary-01/20 text-caption">
                        <Icon
                            name="profile"
                            className="size-3.5 fill-primary-01"
                        />
                        <span className="text-t-primary font-medium truncate max-w-40">
                            {voice}
                        </span>
                    </span>
                )}
            </div>

            {/* honest state explainer */}
            <p className="mt-3 text-caption text-t-secondary leading-relaxed">
                {live ? (
                    <>
                        <span className="text-primary-02 font-medium">
                            This triple runs and is billed
                        </span>{" "}
                        on every outbound call in this campaign.
                    </>
                ) : (
                    <>
                        Saved to this campaign now (voice + tier apply immediately).{" "}
                        <span className="text-t-primary font-medium">
                            The live outbound engine still honours its configured
                            provider
                        </span>{" "}
                        until the provider-lock wave ships (needs founder sign-off +
                        a clean dialing number).
                        {inboundLive && (
                            <>
                                {" "}
                                Inbound calls already log this selection truthfully.
                            </>
                        )}
                    </>
                )}
            </p>
        </div>
    );
}
