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

            {/* the resolved pipeline: STT → LLM → TTS (dynamic from the triple),
                each node carrying the real provider logo + a flowing red signal
                labelled "Famit Infra". */}
            <div className="overflow-x-auto pt-6 pb-2 scrollbar scrollbar-thumb-t-tertiary/30 scrollbar-track-transparent">
                <div className="mx-auto flex w-max items-center">
                    <PipeNode role="STT" provider={stt} name={pretty(stt)} />
                    <PipeConnector />
                    <PipeNode role="LLM" provider={llm} name={pretty(llm)} />
                    <PipeConnector />
                    <PipeNode role="TTS" provider={tts} name={pretty(tts)} />
                </div>
            </div>
            {voice && (
                <div className="mt-3 inline-flex items-center gap-1.5 h-8 px-3 rounded-full bg-primary-01/8 border border-primary-01/20 text-caption">
                    <Icon name="profile" className="size-3.5 fill-primary-01" />
                    <span className="text-t-tertiary">Voice</span>
                    <span className="text-t-primary font-medium truncate max-w-44">
                        {voice}
                    </span>
                </div>
            )}

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

// ── one pipeline node (matches the Figma): a large dark pill with the provider
// logo inside a dark circle on the left + a BIG role + the provider name. ──
function PipeNode({
    role,
    provider,
    name,
}: {
    role: string;
    provider: string;
    name: string;
}) {
    return (
        <div className="pipe-node flex shrink-0 items-center gap-3.5 rounded-full py-2.5 pl-2.5 pr-6 ring-1 ring-white/[0.06] ring-inset">
            <span className="pipe-badge grid size-12 shrink-0 place-items-center rounded-full ring-1 ring-white/[0.08] ring-inset">
                <ProviderGlyph id={provider} />
            </span>
            <span className="leading-none">
                <span className="block text-[1.6rem] font-light leading-none tracking-tight text-white">
                    {role}
                </span>
                <span className="mt-1 block truncate max-w-[7rem] text-[0.76rem] text-white/45">
                    {name}
                </span>
            </span>
        </div>
    );
}

// ── the "Famit Infra" connector: a calm hairline track with a travelling
// signal comet + soft glowing end-nodes (premium, not a garish red band). ──
function PipeConnector() {
    return (
        <div
            className="relative flex shrink-0 items-center"
            style={{ width: "6rem" }}
        >
            <span className="pipe-dot" aria-hidden />
            <span className="pipe-line" aria-hidden>
                <span className="pipe-comet" aria-hidden />
                <span className="pipe-comet pipe-comet-2" aria-hidden />
            </span>
            <span className="pipe-dot" aria-hidden />
            <span className="pointer-events-none absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap text-[0.74rem] font-medium text-t-tertiary">
                Famit Infra
            </span>
        </div>
    );
}

// ── provider logo (dynamic). Known providers render their real brand SVG as a
// white CSS mask, sized to sit inside the node's circle; else a monogram. ──
function ProviderGlyph({ id }: { id: string }) {
    const s = (id || "").toLowerCase();
    const mask = (file: string, w: string, h: string) => (
        <span
            aria-hidden
            className="prov-logo block shrink-0"
            style={{
                width: w,
                height: h,
                WebkitMaskImage: `url(/provider-logos/${file})`,
                maskImage: `url(/provider-logos/${file})`,
            }}
        />
    );
    if (s.includes("sarvam")) return mask("sarvam.svg", "1.7rem", "1.7rem");
    if (s.includes("groq")) return mask("groq.svg", "2.15rem", "0.79rem");
    if (s.includes("eleven"))
        return mask("elevenlabs-mark.svg", "0.62rem", "1.5rem");
    const ch = (id || "?").trim().charAt(0).toUpperCase() || "?";
    return <span className="text-base font-semibold leading-none text-white">{ch}</span>;
}
