"use client";
// Brainwave-2.0-style 3D studio, DARK. Full-bleed canvas with floating chrome
// (top toolbar, left Scene panel, right Design panel, zoom rail, bottom prompt dock)
// containerized inside the haptica <Layout>. All view controls live in the chrome and
// drive the store's `view`; the canvas stays clean.
import { useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import Spinner from "@/components/Spinner";
import DormantCard from "../_components/DormantCard";
import { useStudio } from "./store";
import type { ViewController } from "../_components/ModelViewer";
import ScenePanel from "./ScenePanel";
import DesignPanel from "./DesignPanel";
import PromptDock from "./PromptDock";
import TopToolbar from "./TopToolbar";
import ZoomRail from "./ZoomRail";
import Ico from "./icons";

const ModelViewer = dynamic(() => import("../_components/ModelViewer"), {
    ssr: false,
    loading: () => <div className="absolute inset-0 flex items-center justify-center bg-[#0b0c0f] text-white/50">Loading 3D engine…</div>,
});

export default function StudioShell() {
    const enabled = useStudio((s) => s.enabled);
    const boot = useStudio((s) => s.boot);
    const scene = useStudio((s) => s.scene);
    const busy = useStudio((s) => s.busy);
    const view = useStudio((s) => s.view);
    const setView = useStudio((s) => s.setView);
    const controller = useRef<ViewController | null>(null);

    useEffect(() => {
        boot();
    }, [boot]);

    if (enabled === null)
        return <div className="flex h-[60vh] items-center justify-center"><Spinner /></div>;
    if (!enabled) return <DormantCard />;

    return (
        <div className="pstudio">
            {/* desktop floating studio */}
            <div className="bw-host bw-rise relative h-[calc(100vh-7.5rem)] min-h-[640px] max-[1180px]:hidden">
                {/* full-bleed canvas */}
                <div className="bw-canvas absolute inset-0">
                    {scene ? (
                        <ModelViewer scene={scene} className="!absolute inset-0 !rounded-none" view={view} onView={setView} controllerRef={controller} hud={false} />
                    ) : (
                        <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center text-white/70">
                            <div className="mb-4 flex size-16 items-center justify-center rounded-2xl bg-white/[0.06] text-white"><Ico name="cube" size={30} /></div>
                            <div className="text-[18px] font-semibold text-white">Your 3D home appears here</div>
                            <p className="mt-1 max-w-sm text-[13px] text-white/50">Pick a template on the left, or describe / upload a floor plan below — the model builds in seconds and you can share a walkthrough link with customers.</p>
                        </div>
                    )}
                    {busy && (
                        <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/55 backdrop-blur-[2px]">
                            <div className="flex items-center gap-3 rounded-full bg-[var(--bw-surface-01)] px-5 py-2.5 text-[13px] font-semibold text-white shadow-[var(--bw-shadow-pop)]">
                                <Ico name="spinner" size={18} className="bw-spin text-[var(--bw-accent)]" /> Building your 3D model…
                            </div>
                        </div>
                    )}
                </div>

                {/* floating chrome */}
                <div className="absolute top-3 left-1/2 z-20 -translate-x-1/2"><TopToolbar controller={controller} /></div>
                <ScenePanel className="absolute left-3 top-3 bottom-3 z-20 w-[244px]" />
                <DesignPanel className="absolute right-3 top-3 bottom-3 z-20 w-[260px]" />
                {scene && view.mode === "orbit" && !view.tour && (
                    <div className="absolute right-[280px] top-1/2 z-20 -translate-y-1/2"><ZoomRail controller={controller} /></div>
                )}
                <PromptDock className="absolute bottom-4 left-1/2 z-20 w-[min(540px,calc(100%-560px))] -translate-x-1/2" />
            </div>

            {/* narrow-screen fallback */}
            <div className="min-[1181px]:hidden">
                <div className="surface flex flex-col items-center justify-center rounded-3xl px-6 py-16 text-center">
                    <div className="mb-3 flex size-14 items-center justify-center rounded-2xl bg-b-surface1"><Ico name="cube" size={26} /></div>
                    <div className="text-h6 mb-1">Property Studio is best on a wider screen</div>
                    <p className="text-body-2 text-t-secondary max-w-sm">The 3D studio needs a desktop-width window. Open this on a larger display to generate and share interactive property models.</p>
                </div>
            </div>
        </div>
    );
}
