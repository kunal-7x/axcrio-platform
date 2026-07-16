"use client";
// Right-edge vertical zoom rail (Brainwave ViewController). Dolly the orbit camera
// in/out via the viewer controller.
import { MutableRefObject } from "react";
import type { ViewController } from "../_components/ModelViewer";
import Ico from "./icons";

export default function ZoomRail({ controller }: { controller: MutableRefObject<ViewController | null> }) {
    return (
        <div className="bw-zoomrail">
            <button type="button" title="Zoom in" className="bw-icon !size-8" onClick={() => controller.current?.zoomBy(1.18)}>
                <Ico name="plus" size={16} />
            </button>
            <div className="flex flex-col items-center gap-1 py-1">
                {[0, 1, 2, 3].map((i) => (
                    <span key={i} className="h-px w-3 bg-[var(--bw-border-2)]" />
                ))}
            </div>
            <button type="button" title="Zoom out" className="bw-icon !size-8" onClick={() => controller.current?.zoomBy(1 / 1.18)}>
                <Ico name="minus" size={16} />
            </button>
        </div>
    );
}
