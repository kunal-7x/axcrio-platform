"use client";
// Everything that lives *inside* the <Canvas>: geometry, lighting, environment,
// room labels, and the three camera rigs (orbit dollhouse / first-person walk /
// cinematic tour). Pure interpreter of the SceneSpec from lib/pmodel.
import { useEffect, useMemo, useRef, MutableRefObject } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import {
    OrbitControls,
    PointerLockControls,
    Environment,
    Lightformer,
    ContactShadows,
    Sky,
    Html,
} from "@react-three/drei";
import * as THREE from "three";
import type { SceneSpec } from "@/lib/pmodel";
import FurnitureGLB from "./FurnitureGLB";

// Approx target footprint [w,h,d] (m) used to normalize a generated GLB to the room.
const FURN_TARGET: Record<string, [number, number, number]> = {
    bed: [1.7, 0.6, 2.05], nightstand: [0.5, 0.45, 0.42], wardrobe: [1.8, 2.0, 0.6],
    sofa: [2.1, 0.8, 0.95], coffee_table: [1.0, 0.45, 0.55], tv_unit: [1.7, 1.2, 0.4],
    dining_table: [1.7, 0.75, 1.0], fridge: [0.72, 1.8, 0.7], counter: [2.2, 0.9, 0.6],
    toilet: [0.5, 0.7, 0.6], sink: [0.55, 0.85, 0.42], tub: [1.7, 0.55, 0.75],
    shower: [0.95, 1.9, 0.95], desk: [1.4, 0.75, 0.7], chair: [0.45, 0.85, 0.45],
    shelf: [0.9, 2.0, 0.32], console: [1.0, 0.8, 0.35], plant: [0.45, 0.95, 0.45],
};

export interface Bridge {
    gl?: THREE.WebGLRenderer;
    scene?: THREE.Scene;
    camera?: THREE.Camera;
    root?: THREE.Group | null;
    // OrbitControls instance (when in orbit mode) — used by the zoom rail.
    controls?: { target: THREE.Vector3; update?: () => void } | null;
}

// ---------------------------------------------------------------- geometry
function Walls({ scene }: { scene: SceneSpec }) {
    const wall = scene.palette.wall;
    const trim = scene.palette.trim;
    return (
        <group>
            {scene.walls.flatMap((w, wi) =>
                w.panels.map((p, pi) => (
                    <mesh
                        key={`${wi}-${pi}`}
                        position={p.position}
                        rotation={[0, p.rotationY, 0]}
                        castShadow
                        receiveShadow
                    >
                        <boxGeometry args={p.size} />
                        <meshStandardMaterial
                            color={p.kind === "solid" ? wall : trim}
                            roughness={0.92}
                            metalness={0}
                        />
                    </mesh>
                )),
            )}
        </group>
    );
}

function Floors({ scene }: { scene: SceneSpec }) {
    const geoms = useMemo(
        () =>
            scene.floors.map((f) => {
                const shape = new THREE.Shape();
                f.polygon.forEach(([x, z], i) => {
                    // Shape lives in local XY; mesh is rotated -90° about X so
                    // (u,v) -> world (u, 0, -v). Feed (x, -z) to land at (x,0,z).
                    if (i === 0) shape.moveTo(x, -z);
                    else shape.lineTo(x, -z);
                });
                shape.closePath();
                return { geom: new THREE.ShapeGeometry(shape), f };
            }),
        [scene],
    );
    return (
        <group>
            {geoms.map(({ geom, f }, i) => (
                <mesh
                    key={i}
                    geometry={geom}
                    rotation={[-Math.PI / 2, 0, 0]}
                    position={[0, 0.01, 0]}
                    receiveShadow
                >
                    <meshStandardMaterial
                        color={scene.palette.floor[f.material] || scene.palette.floor.wood}
                        roughness={0.6}
                        metalness={0.05}
                        side={THREE.DoubleSide}
                    />
                </mesh>
            ))}
        </group>
    );
}

function Ceilings({ scene, visible }: { scene: SceneSpec; visible: boolean }) {
    const h = scene.walls[0]?.height || 2.7;
    const geoms = useMemo(
        () =>
            scene.floors.map((f) => {
                const shape = new THREE.Shape();
                f.polygon.forEach(([x, z], i) =>
                    i === 0 ? shape.moveTo(x, -z) : shape.lineTo(x, -z),
                );
                shape.closePath();
                return new THREE.ShapeGeometry(shape);
            }),
        [scene],
    );
    if (!visible) return null;
    return (
        <group>
            {geoms.map((geom, i) => (
                <mesh key={i} geometry={geom} rotation={[Math.PI / 2, 0, 0]} position={[0, h - 0.02, 0]}>
                    <meshStandardMaterial color="#f3f4f8" roughness={1} side={THREE.DoubleSide} />
                </mesh>
            ))}
        </group>
    );
}

function Openings({ scene }: { scene: SceneSpec }) {
    return (
        <group>
            {scene.openings.map((o, i) => {
                const w = o.width * 0.94;
                if (o.kind === "window") {
                    return (
                        <group key={i} position={o.position} rotation={[0, o.rotationY, 0]}>
                            <mesh castShadow>
                                <boxGeometry args={[w, o.height, o.thickness * 0.3]} />
                                <meshStandardMaterial
                                    color={scene.palette.glass}
                                    transparent
                                    opacity={0.32}
                                    roughness={0.05}
                                    metalness={0.1}
                                />
                            </mesh>
                            {/* frame */}
                            <mesh position={[0, o.height / 2 + 0.03, 0]}>
                                <boxGeometry args={[w + 0.1, 0.06, o.thickness * 0.6]} />
                                <meshStandardMaterial color={scene.palette.trim} />
                            </mesh>
                            <mesh position={[0, -o.height / 2 - 0.03, 0]}>
                                <boxGeometry args={[w + 0.1, 0.06, o.thickness * 0.6]} />
                                <meshStandardMaterial color={scene.palette.trim} />
                            </mesh>
                        </group>
                    );
                }
                // door slab (kind door / arch)
                return (
                    <group key={i} position={o.position} rotation={[0, o.rotationY, 0]}>
                        <mesh castShadow receiveShadow>
                            <boxGeometry args={[w, o.height, o.thickness * 0.5]} />
                            <meshStandardMaterial color={scene.palette.door} roughness={0.7} />
                        </mesh>
                        <mesh position={[w * 0.35, 0, o.thickness * 0.35]}>
                            <sphereGeometry args={[0.04, 12, 12]} />
                            <meshStandardMaterial color="#d8b15a" metalness={0.8} roughness={0.3} />
                        </mesh>
                    </group>
                );
            })}
        </group>
    );
}

function Furniture({ scene, visible }: { scene: SceneSpec; visible: boolean }) {
    if (!visible) return null;
    return (
        <group>
            {scene.furniture.map((f, i) => (
                <group key={i} position={f.position} rotation={[0, f.rotationY, 0]}>
                    <FurnitureGLB
                        url={f.glb}
                        kind={f.kind}
                        target={FURN_TARGET[f.kind] || [0.6, 0.6, 0.6]}
                    />
                </group>
            ))}
        </group>
    );
}

function RoomLabels({ scene }: { scene: SceneSpec }) {
    return (
        <group>
            {scene.floors.map((f, i) => (
                <Html
                    key={i}
                    position={[f.center[0], 1.4, f.center[1]]}
                    center
                    distanceFactor={11}
                    zIndexRange={[10, 0]}
                >
                    <div
                        style={{
                            background: "rgba(17,22,34,0.78)",
                            color: "#fff",
                            padding: "3px 9px",
                            borderRadius: 999,
                            fontSize: 12,
                            fontWeight: 600,
                            whiteSpace: "nowrap",
                            boxShadow: "0 4px 14px rgba(0,0,0,.25)",
                            pointerEvents: "none",
                            userSelect: "none",
                        }}
                    >
                        {f.name}
                        <span style={{ opacity: 0.6, fontWeight: 400 }}>
                            {"  "}
                            {Math.round(f.area_sqm * 10.764)} ft²
                        </span>
                    </div>
                </Html>
            ))}
        </group>
    );
}

// ---------------------------------------------------------------- lighting
function Lights({ scene, day }: { scene: SceneSpec; day: boolean }) {
    const sun = scene.lights.find((l) => l.kind === "sun");
    const ceil = scene.lights.filter((l) => l.kind === "ceiling");
    const span = Math.max(scene.bounds.width, scene.bounds.depth) * 0.75 + 4;
    return (
        <group>
            <ambientLight intensity={day ? 0.5 : 0.16} />
            <hemisphereLight args={[day ? "#dfeaff" : "#26304a", "#b08c63", day ? 0.55 : 0.18]} />
            {sun && (
                <directionalLight
                    position={sun.position}
                    intensity={day ? sun.intensity : 0.12}
                    color={day ? sun.color : "#9fb4e0"}
                    castShadow
                    shadow-mapSize={[2048, 2048]}
                    shadow-bias={-0.0004}
                    shadow-camera-near={0.5}
                    shadow-camera-far={span * 4}
                    shadow-camera-left={-span}
                    shadow-camera-right={span}
                    shadow-camera-top={span}
                    shadow-camera-bottom={-span}
                />
            )}
            {!day &&
                ceil.map((l, i) => (
                    <pointLight
                        key={i}
                        position={[l.position[0], l.position[1], l.position[2]]}
                        intensity={l.intensity * 6}
                        distance={6}
                        decay={2}
                        color={l.color}
                    />
                ))}
        </group>
    );
}

// ---------------------------------------------------------------- camera rigs
function OrbitRig({ scene }: { scene: SceneSpec }) {
    const { camera } = useThree();
    useEffect(() => {
        const d = scene.cameras.dollhouse.position;
        camera.position.set(d[0], d[1], d[2]);
    }, [scene, camera]);
    const c = scene.bounds.center;
    const maxd = Math.max(scene.bounds.width, scene.bounds.depth) * 2.6 + 6;
    return (
        <OrbitControls
            makeDefault
            target={[c[0], 0.6, c[1]]}
            enableDamping
            dampingFactor={0.08}
            maxPolarAngle={Math.PI / 2.04}
            minDistance={2}
            maxDistance={maxd}
        />
    );
}

function WalkRig({ scene }: { scene: SceneSpec }) {
    const { camera } = useThree();
    const keys = useRef<Record<string, boolean>>({});
    useEffect(() => {
        const wp = scene.cameras.waypoints[0];
        const eye = scene.meta.eye_height || 1.6;
        if (wp) camera.position.set(wp.position[0], eye, wp.position[2]);
        const dn = (e: KeyboardEvent) => (keys.current[e.code] = true);
        const up = (e: KeyboardEvent) => (keys.current[e.code] = false);
        window.addEventListener("keydown", dn);
        window.addEventListener("keyup", up);
        return () => {
            window.removeEventListener("keydown", dn);
            window.removeEventListener("keyup", up);
        };
    }, [scene, camera]);
    useFrame((_, dt) => {
        const eye = scene.meta.eye_height || 1.6;
        const speed = 2.8 * Math.min(dt, 0.05);
        const dir = new THREE.Vector3();
        camera.getWorldDirection(dir);
        dir.y = 0;
        if (dir.lengthSq() > 0) dir.normalize();
        const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0));
        const move = new THREE.Vector3();
        const k = keys.current;
        if (k["KeyW"] || k["ArrowUp"]) move.add(dir);
        if (k["KeyS"] || k["ArrowDown"]) move.sub(dir);
        if (k["KeyD"] || k["ArrowRight"]) move.add(right);
        if (k["KeyA"] || k["ArrowLeft"]) move.sub(right);
        if (move.lengthSq() > 0) {
            move.normalize().multiplyScalar(speed);
            camera.position.add(move);
        }
        camera.position.y = eye;
        const b = scene.bounds;
        const m = 1.2;
        camera.position.x = Math.max(b.min[0] - m, Math.min(b.max[0] + m, camera.position.x));
        camera.position.z = Math.max(b.min[1] - m, Math.min(b.max[1] + m, camera.position.z));
    });
    return <PointerLockControls makeDefault />;
}

function TourRig({
    scene,
    onWaypoint,
    onDone,
}: {
    scene: SceneSpec;
    onWaypoint?: (name: string) => void;
    onDone?: () => void;
}) {
    const { camera } = useThree();
    const t = useRef(0);
    const seg = useRef(0);
    const wps = scene.cameras.waypoints;
    useEffect(() => {
        t.current = 0;
        seg.current = 0;
        if (wps[0]) camera.position.set(...wps[0].position);
    }, [scene, camera, wps]);
    useFrame((_, dt) => {
        if (wps.length < 2) {
            onDone?.();
            return;
        }
        t.current += Math.min(dt, 0.05) / 3.2; // ~3.2s per room
        if (t.current >= 1) {
            t.current = 0;
            seg.current += 1;
            const nm = wps[seg.current % wps.length]?.name;
            if (nm) onWaypoint?.(nm);
            if (seg.current >= wps.length) {
                onDone?.();
                return;
            }
        }
        const a = wps[seg.current % wps.length];
        const b = wps[(seg.current + 1) % wps.length];
        const e = t.current < 0.5 ? 2 * t.current * t.current : 1 - Math.pow(-2 * t.current + 2, 2) / 2;
        camera.position.lerpVectors(
            new THREE.Vector3(...a.position),
            new THREE.Vector3(...b.position),
            e,
        );
        const tgt = new THREE.Vector3().lerpVectors(
            new THREE.Vector3(...a.target),
            new THREE.Vector3(...b.target),
            e,
        );
        camera.lookAt(tgt);
    });
    return null;
}

function CaptureBridge({ bridge, rootRef }: { bridge: MutableRefObject<Bridge>; rootRef: MutableRefObject<THREE.Group | null> }) {
    const gl = useThree((s) => s.gl);
    const scene = useThree((s) => s.scene);
    const camera = useThree((s) => s.camera);
    const controls = useThree((s) => s.controls);
    useEffect(() => {
        bridge.current.gl = gl;
        bridge.current.scene = scene;
        bridge.current.camera = camera;
        bridge.current.root = rootRef.current;
        bridge.current.controls = (controls as unknown as Bridge["controls"]) || null;
    });
    return null;
}

// ---------------------------------------------------------------- composite
export default function Stage({
    scene,
    mode,
    day,
    furnish,
    ceiling,
    labels,
    tour,
    bridge,
    viewNonce = 0,
    onWaypoint,
    onTourDone,
}: {
    scene: SceneSpec;
    mode: "orbit" | "walk";
    day: boolean;
    furnish: boolean;
    ceiling: boolean;
    labels: boolean;
    tour: boolean;
    bridge: MutableRefObject<Bridge>;
    viewNonce?: number;
    onWaypoint?: (name: string) => void;
    onTourDone?: () => void;
}) {
    const rootRef = useRef<THREE.Group>(null);
    const span = Math.max(scene.bounds.width, scene.bounds.depth);
    return (
        <>
            <color attach="background" args={[day ? "#dce6f5" : "#0c1018"]} />
            {day ? (
                <Sky sunPosition={[80, 40, 60]} turbidity={6} rayleigh={1.2} />
            ) : (
                <fog attach="fog" args={["#0c1018", span * 1.2, span * 4]} />
            )}
            <Lights scene={scene} day={day} />
            <Environment resolution={256}>
                <Lightformer intensity={day ? 1.2 : 0.4} position={[0, 6, 0]} scale={[10, 10, 1]} color="#ffffff" />
                <Lightformer intensity={day ? 0.6 : 0.2} position={[6, 3, 6]} scale={[6, 6, 1]} color="#cfe0ff" />
            </Environment>

            <group ref={rootRef}>
                <Floors scene={scene} />
                <Walls scene={scene} />
                <Openings scene={scene} />
                <Ceilings scene={scene} visible={ceiling} />
                <Furniture scene={scene} visible={furnish} />
            </group>

            {/* soft grounding for the dollhouse */}
            {day && (
                <ContactShadows
                    position={[scene.bounds.center[0], 0, scene.bounds.center[1]]}
                    scale={span * 2.2}
                    opacity={0.45}
                    blur={2.4}
                    far={6}
                />
            )}

            {labels && mode === "orbit" && !tour && <RoomLabels scene={scene} />}

            {tour ? (
                <TourRig scene={scene} onWaypoint={onWaypoint} onDone={onTourDone} />
            ) : mode === "orbit" ? (
                <OrbitRig key={viewNonce} scene={scene} />
            ) : (
                <WalkRig key={viewNonce} scene={scene} />
            )}

            <CaptureBridge bridge={bridge} rootRef={rootRef} />
        </>
    );
}
