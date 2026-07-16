"use client";
// Optional generated-mesh furniture. When a furniture item carries a `glb` url
// (from the assets3d backend), load it via useGLTF, normalize it to the kind's
// target footprint, and render it; on ANY miss/error it falls back to the
// procedural <FurniturePiece>. Gated by NEXT_PUBLIC_PMODEL_ASSETS3D so the default
// build never even attempts a network GLB.
import { Component, ReactNode, Suspense, useMemo } from "react";
import * as THREE from "three";
import { useGLTF, Clone } from "@react-three/drei";
import { SkeletonUtils } from "three-stdlib";
import FurniturePiece from "./Furniture";

export const ASSETS3D_ON =
    typeof process !== "undefined" &&
    String(process.env.NEXT_PUBLIC_PMODEL_ASSETS3D || "") === "1";

class GLBBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
    state = { failed: false };
    static getDerivedStateFromError() {
        return { failed: true };
    }
    componentDidCatch() {
        /* swallow — we render the procedural fallback */
    }
    render() {
        return this.state.failed ? this.props.fallback : this.props.children;
    }
}

function Fitted({ url, target }: { url: string; target: [number, number, number] }) {
    const { scene } = useGLTF(url);
    const cloned = useMemo(() => SkeletonUtils.clone(scene), [scene]);
    const { scale, offset } = useMemo(() => {
        const box = new THREE.Box3().setFromObject(cloned);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const s = Math.min(
            target[0] / (size.x || 1),
            target[1] / (size.y || 1),
            target[2] / (size.z || 1),
        );
        const off = new THREE.Vector3(
            -center.x * s,
            -(center.y - size.y / 2) * s, // base on y=0 (matches Furniture.tsx authoring)
            -center.z * s,
        );
        return { scale: s, offset: off };
    }, [cloned, target]);
    return (
        <group position={offset.toArray()} scale={scale}>
            <Clone object={cloned} castShadow receiveShadow />
        </group>
    );
}

export default function FurnitureGLB({
    url,
    kind,
    target,
}: {
    url?: string;
    kind: string;
    target: [number, number, number];
}) {
    const fallback = <FurniturePiece kind={kind} />;
    if (!ASSETS3D_ON || !url) return fallback;
    return (
        <GLBBoundary fallback={fallback}>
            <Suspense fallback={fallback}>
                <Fitted url={url} target={target} />
            </Suspense>
        </GLBBoundary>
    );
}
