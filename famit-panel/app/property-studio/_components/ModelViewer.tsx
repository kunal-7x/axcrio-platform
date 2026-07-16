"use client";
// The interactive 3D viewer. Two modes:
//  • self-contained (share page): owns its view state + a light floating HUD.
//  • controlled (studio): `view` + `onView` drive it from the Brainwave chrome, the
//    HUD is hidden (hud=false), and imperative actions (shot/glb/reset/zoom) are
//    exposed via `controllerRef` so the top toolbar / zoom rail can call them.
import { MutableRefObject, useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import type { SceneSpec } from "@/lib/pmodel";
import Stage, { Bridge } from "../_three/Stage";

export type View = {
    mode: "orbit" | "walk";
    day: boolean;
    furnish: boolean;
    ceiling: boolean;
    labels: boolean;
    tour: boolean;
};
export type ViewController = {
    shot: () => void;
    glb: () => void;
    reset: () => void;
    zoomBy: (f: number) => void;
};

const DEFAULT_VIEW: View = { mode: "orbit", day: true, furnish: true, ceiling: false, labels: true, tour: false };

function download(url: string, name: string) {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
}

function Btn({ active, onClick, title, children }: { active?: boolean; onClick: () => void; title: string; children: React.ReactNode }) {
    return (
        <button
            type="button"
            title={title}
            onClick={onClick}
            className={`h-9 px-3 rounded-full text-[13px] font-semibold transition-colors backdrop-blur-md border ${
                active
                    ? "bg-[#2A85FF] text-white border-transparent shadow-[0_4px_14px_rgba(42,133,255,.35)]"
                    : "bg-white/80 text-[#1a1d29] border-black/5 hover:bg-white"
            }`}
        >
            {children}
        </button>
    );
}

export default function ModelViewer({
    scene,
    title,
    footer,
    className,
    view,
    onView,
    controllerRef,
    hud = true,
}: {
    scene: SceneSpec;
    title?: string;
    footer?: React.ReactNode;
    className?: string;
    view?: View;
    onView?: (patch: Partial<View>) => void;
    controllerRef?: MutableRefObject<ViewController | null>;
    hud?: boolean;
}) {
    const [internal, setInternal] = useState<View>(DEFAULT_VIEW);
    const v = view ?? internal;
    const set = (patch: Partial<View>) => (onView ? onView(patch) : setInternal((s) => ({ ...s, ...patch })));

    const [tourRoom, setTourRoom] = useState("");
    const [nonce, setNonce] = useState(0);
    const bridge = useRef<Bridge>({});

    const d = scene.cameras.dollhouse.position;

    function shot() {
        const b = bridge.current;
        if (!b.gl || !b.scene || !b.camera) return;
        b.gl.render(b.scene, b.camera);
        download(b.gl.domElement.toDataURL("image/png"), `${title || scene.meta.title}.png`);
    }
    async function glb() {
        const b = bridge.current;
        if (!b.root) return;
        const mod = await import("three/examples/jsm/exporters/GLTFExporter.js");
        const exporter = new mod.GLTFExporter();
        exporter.parse(
            b.root,
            (out) => download(URL.createObjectURL(new Blob([out as ArrayBuffer], { type: "model/gltf-binary" })), `${title || scene.meta.title}.glb`),
            (err) => console.error("GLB export failed", err),
            { binary: true },
        );
    }
    function reset() {
        set({ tour: false, mode: "orbit" });
        setNonce((n) => n + 1);
    }
    function zoomBy(f: number) {
        const b = bridge.current;
        if (!b.camera) return;
        const target = (b.controls && b.controls.target) || new THREE.Vector3(0, 0.6, 0);
        const offset = b.camera.position.clone().sub(target).multiplyScalar(1 / f);
        const dist = offset.length();
        if (dist < 1.5 || dist > 240) return;
        b.camera.position.copy(target.clone().add(offset));
        b.controls?.update?.();
    }

    useEffect(() => {
        if (controllerRef) controllerRef.current = { shot, glb, reset, zoomBy };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    });

    const m = scene.meta;
    return (
        <div className={`relative w-full overflow-hidden rounded-2xl bg-[#0b0c0f] ${className || ""}`}>
            <Canvas
                shadows
                dpr={[1, 2]}
                gl={{ antialias: true, preserveDrawingBuffer: true, toneMapping: THREE.ACESFilmicToneMapping }}
                camera={{ fov: 55, near: 0.05, far: 2000, position: [d[0], d[1], d[2]] }}
            >
                <Stage
                    scene={scene}
                    mode={v.mode}
                    day={v.day}
                    furnish={v.furnish}
                    ceiling={v.ceiling}
                    labels={v.labels}
                    tour={v.tour}
                    bridge={bridge}
                    viewNonce={nonce}
                    onWaypoint={(name) => setTourRoom(name)}
                    onTourDone={() => {
                        set({ tour: false });
                        setTourRoom("");
                    }}
                />
            </Canvas>

            {hud && (
                <>
                    <div className="pointer-events-none absolute left-3 top-3 select-none">
                        <div className="rounded-xl bg-black/45 px-3 py-2 text-white backdrop-blur-md">
                            <div className="text-[15px] font-semibold leading-tight">{title || m.title}</div>
                            <div className="text-[12px] opacity-80">
                                {m.rooms} rooms · {m.bedrooms} bed · {m.baths} bath · {Math.round(m.area_sqft)} ft²
                            </div>
                        </div>
                    </div>
                    <div className="absolute right-3 top-3 flex flex-wrap justify-end gap-2">
                        <Btn active={v.mode === "orbit" && !v.tour} onClick={() => set({ tour: false, mode: "orbit" })} title="Dollhouse / orbit view">Dollhouse</Btn>
                        <Btn active={v.mode === "walk" && !v.tour} onClick={() => set({ tour: false, mode: "walk" })} title="First-person walkthrough">Walk</Btn>
                        <Btn active={v.tour} onClick={() => set({ tour: !v.tour })} title="Cinematic auto-tour">{v.tour ? "Stop tour" : "▶ Tour"}</Btn>
                    </div>
                    <div className="absolute bottom-3 left-3 flex flex-wrap gap-2">
                        <Btn active={v.day} onClick={() => set({ day: !v.day })} title="Day / night">{v.day ? "☀ Day" : "☾ Night"}</Btn>
                        <Btn active={v.furnish} onClick={() => set({ furnish: !v.furnish })} title="Furniture">Furnish</Btn>
                        <Btn active={v.ceiling} onClick={() => set({ ceiling: !v.ceiling })} title="Ceilings">Ceiling</Btn>
                        {v.mode === "orbit" && <Btn active={v.labels} onClick={() => set({ labels: !v.labels })} title="Room labels">Labels</Btn>}
                        <Btn onClick={reset} title="Reset camera">Reset</Btn>
                    </div>
                    <div className="absolute bottom-3 right-3 flex gap-2">
                        <Btn onClick={shot} title="Save PNG">⤓ PNG</Btn>
                        <Btn onClick={glb} title="Download GLB">⤓ GLB</Btn>
                    </div>
                </>
            )}

            {/* walk / tour hint (shown in both modes — small, informative) */}
            {(v.mode === "walk" && !v.tour) || v.tour ? (
                <div className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2">
                    <div className="rounded-full bg-black/55 px-4 py-1.5 text-[12px] font-medium text-white backdrop-blur-md">
                        {v.tour ? (tourRoom ? `Touring · ${tourRoom}` : "Starting tour…") : "Click to look · W A S D to move · Esc to release"}
                    </div>
                </div>
            ) : null}

            {footer}
        </div>
    );
}
