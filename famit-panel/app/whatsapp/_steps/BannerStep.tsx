// ⑤ BANNER STUDIO — generate/refine the banner in-context (NewProductPage 2-col).
// col-left = a compact Creative-Studio panel (instruction + size + Generate).
// col-right = the variants grid + the §6-PHASE2 dot-matrix GenerationLoader while
// rendering. NL-edit chips. Credit-gate Modal before a large gen (master §35).
//
// DORMANT-SAFE: no provider key / :8310 dormant (404/503) → ComingSoon.

"use client";

import { useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Modal from "@/components/Modal";
import Image from "@/components/Image";
import Icon from "@/components/Icon";
import dynamic from "next/dynamic";
import { type GenerationLoaderState } from "@/components/GenerationLoader";
// The "Signal Aurora" loader bundles framer-motion + a WebGL field. Code-split it
// (ssr:false) so the WebGL/animation cost never lands in the global bundle — it
// loads its own chunk only while a generation is actually running.
const GenerationLoader = dynamic(() => import("@/components/GenerationLoader"), {
    ssr: false,
});
import { type SelectOption } from "@/types/select";
import ComingSoon from "../_components/ComingSoon";
import NoInventNote from "../_components/NoInventNote";
import { generateBanner, getJobAssets } from "../_lib/waapi";
import { type StepCtx, type AssetRef } from "../_lib/types";

const SIZE_OPTS: SelectOption[] = [
    { id: 1, name: "WhatsApp poster (square)" },
    { id: 2, name: "Story card (9:16)" },
    { id: 3, name: "Landscape (16:9)" },
];
const NL_CHIPS = ["Make it premium", "Remove price", "Hinglish", "Story size", "Brighter"];

export default function BannerStep({ campaign, draft, setDraft, goTo, notify }: StepCtx) {
    const [instruction, setInstruction] = useState("");
    const [size, setSize] = useState<SelectOption>(SIZE_OPTS[0]);
    const [phase, setPhase] = useState<"idle" | "confirm" | "loading" | "ready" | "dormant">("idle");
    const [loaderState, setLoaderState] = useState<GenerationLoaderState>("loading");
    const [jobId, setJobId] = useState<string | null>(null);
    const [variants, setVariants] = useState<AssetRef[]>([]);

    async function startGen() {
        setPhase("loading");
        setLoaderState("loading");
        const r = await generateBanner({ campaign_id: campaign?.id, instruction, size: size.name });
        if (!r.configured) {
            setPhase("dormant");
            return;
        }
        setJobId(r.job_id);
        // poll once the loader signals completion (the loader owns the stream via
        // useGenerationJob in a fully-wired build; here we resolve assets on done)
        const assets = await getJobAssets(r.job_id);
        if (assets.configured) setVariants(assets.assets);
        setLoaderState("completed");
    }

    const attach = (a: AssetRef) => {
        setDraft({ asset_id: a.id, asset_url: a.url || a.thumb_url, asset_approved: a.status === "approved" || a.status === "winner" });
        notify("Banner attached", "success");
        goTo("preview");
    };

    if (phase === "dormant") {
        return (
            <ComingSoon
                title="Banner studio"
                body="Connect the image engine to generate on-brand WhatsApp banners from a single instruction — variants stream in live, edit with one tap, and they auto-save to your Asset Library."
                icon="camera"
                fallbackLabel="Pick an existing banner"
                onFallback={() => goTo("creative")}
            />
        );
    }

    return (
        <>
            <div className="flex gap-3 max-lg:flex-col">
                {/* left: studio controls */}
                <div className="w-110 max-3xl:w-96 max-lg:w-full shrink-0">
                    <Card title="Create a banner">
                        <div className="flex flex-col gap-5 px-5 pb-5 pt-1 max-lg:px-3">
                            <Field
                                label="What should it show?"
                                textarea
                                placeholder="A premium poster for our 2BHK launch offer, festive mood…"
                                value={instruction}
                                onChange={(e) => setInstruction(e.target.value)}
                            />
                            <Select label="Size" value={size} onChange={setSize} options={SIZE_OPTS} />
                            <div>
                                <div className="mb-3 text-button">Quick edits</div>
                                <div className="flex flex-wrap gap-2">
                                    {NL_CHIPS.map((c) => (
                                        <Button key={c} isStroke className="!h-9 !px-3.5 !text-body-2 !font-normal" onClick={() => setInstruction((p) => (p ? `${p}, ${c.toLowerCase()}` : c))}>
                                            {c}
                                        </Button>
                                    ))}
                                </div>
                            </div>
                            <NoInventNote />
                            <Button isBlack icon="magic-pencil" className="w-full" disabled={phase === "loading"} onClick={() => setPhase("confirm")}>
                                Generate banners
                            </Button>
                        </div>
                    </Card>
                </div>

                {/* right: variants / loader */}
                <div className="flex-1 min-w-0">
                    <Card title="Variants">
                        <div className="p-3">
                            {phase === "loading" ? (
                                <GenerationLoader
                                    title="Creating your banners"
                                    label="Thinking"
                                    state={loaderState}
                                    onCompleted={() => setPhase("ready")}
                                />
                            ) : variants.length > 0 ? (
                                <div className="grid grid-cols-2 gap-4 p-2 max-md:grid-cols-1">
                                    {variants.map((v) => (
                                        <div key={v.id} className="group flex flex-col rounded-3xl overflow-hidden bg-b-surface2 ring-1 ring-s-subtle">
                                            <div className="relative h-48 w-full bg-b-surface1">
                                                {(v.thumb_url || v.url) && <Image className="object-cover" src={(v.thumb_url || v.url) as string} alt="" fill sizes="320px" />}
                                            </div>
                                            <div className="flex items-center gap-2 p-3">
                                                <div className="grow text-button text-t-primary truncate">{v.title || "Variant"}</div>
                                                <Button isBlack onClick={() => attach(v)}>Use this</Button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div className="flex flex-col items-center text-center py-16 px-5">
                                    <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                        <Icon className="fill-t-secondary" name="camera" />
                                    </div>
                                    <div className="text-sub-title-1 text-t-primary">Describe your banner</div>
                                    <div className="mt-1 max-w-80 text-body-2 text-t-secondary">Variants appear here as they render.</div>
                                </div>
                            )}
                        </div>
                    </Card>
                </div>
            </div>

            {/* credit-gate confirm (master §35) */}
            <Modal open={phase === "confirm"} onClose={() => setPhase("idle")}>
                <div className="text-center">
                    <div className="flex justify-center items-center size-14 mx-auto mb-5 rounded-full bg-b-surface2">
                        <Icon className="fill-t-secondary" name="usd-circle" />
                    </div>
                    <div className="text-h5 text-t-primary">Generate 4 banners?</div>
                    <div className="mt-2 text-body-2 text-t-secondary max-w-90 mx-auto">
                        This uses credits from your wallet. You can edit or regenerate any variant after.
                    </div>
                    <div className="flex gap-3 justify-center mt-8">
                        <Button isStroke onClick={() => setPhase("idle")}>Cancel</Button>
                        <Button isBlack onClick={startGen}>Continue</Button>
                    </div>
                </div>
            </Modal>
        </>
    );
}
