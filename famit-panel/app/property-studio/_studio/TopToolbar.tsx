"use client";
// Floating top-center toolbar (Brainwave grammar): view-mode tools + reset + export.
import { MutableRefObject, useState } from "react";
import { useStudio } from "./store";
import type { ViewController } from "../_components/ModelViewer";
import Ico from "./icons";

export default function TopToolbar({ controller }: { controller: MutableRefObject<ViewController | null> }) {
    const view = useStudio((s) => s.view);
    const setView = useStudio((s) => s.setView);
    const scene = useStudio((s) => s.scene);
    const [exportOpen, setExportOpen] = useState(false);

    const disabled = !scene;
    const Tool = ({ name, active, onClick, title }: { name: string; active?: boolean; onClick: () => void; title: string }) => (
        <button type="button" title={title} disabled={disabled} onClick={onClick} className={`bw-tool ${active ? "is-active" : ""}`}>
            <Ico name={name} size={19} />
        </button>
    );

    return (
        <div className="bw-toolbar">
            <Tool name="cursor" title="Dollhouse / orbit" active={view.mode === "orbit" && !view.tour} onClick={() => setView({ mode: "orbit", tour: false })} />
            <Tool name="walk" title="Walkthrough (WASD + drag)" active={view.mode === "walk" && !view.tour} onClick={() => setView({ mode: "walk", tour: false })} />
            <Tool name="play" title="Cinematic tour" active={view.tour} onClick={() => setView({ tour: !view.tour })} />
            <span className="bw-divider" />
            <Tool name="frame" title="Reset camera" onClick={() => controller.current?.reset()} />
            <span className="bw-divider" />
            <div className="relative">
                <button type="button" disabled={disabled} onClick={() => setExportOpen((v) => !v)} className="bw-btn bw-btn-light !h-9 !px-3.5">
                    <Ico name="download" size={16} /> Export
                </button>
                {exportOpen && (
                    <>
                        <div className="fixed inset-0 z-10" onClick={() => setExportOpen(false)} />
                        <div className="absolute right-0 top-11 z-20 w-40 rounded-xl border border-[var(--bw-border-1)] bg-[var(--bw-surface-01)] p-1.5 shadow-[var(--bw-shadow-pop)]">
                            <button type="button" className="bw-row w-full !py-2 text-[13px]" onClick={() => { controller.current?.shot(); setExportOpen(false); }}>
                                <span className="bw-row-ic !size-7"><Ico name="image" size={15} /></span> PNG snapshot
                            </button>
                            <button type="button" className="bw-row w-full !py-2 text-[13px]" onClick={() => { controller.current?.glb(); setExportOpen(false); }}>
                                <span className="bw-row-ic !size-7"><Ico name="download" size={15} /></span> 3D model (.glb)
                            </button>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
