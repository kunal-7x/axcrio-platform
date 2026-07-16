"use client";
// Procedural furniture — each `kind` from the builder is drawn here as a small group
// of primitives, centred on its local origin (parent applies world position + rotationY).
// Coarse but readable: enough to make every room look lived-in.
import { ReactNode } from "react";

const C = {
    woodDark: "#6b4f34",
    wood: "#9c6b3f",
    fabric: "#7d8aa5",
    fabricLite: "#aab4c8",
    white: "#eef1f6",
    metal: "#b9bfc9",
    steel: "#cdd3db",
    glass: "#bfe0ef",
    green: "#4f8f5b",
    pot: "#8a5a3c",
    mattress: "#e7e3da",
    sheet: "#d7e0ec",
    screen: "#1b2130",
    rug: "#c8806c",
    stone: "#d7dbe2",
    pillow: "#eef2f8",
};

function Box({
    a,
    p,
    color,
    rough = 0.85,
    metal = 0,
    opacity = 1,
}: {
    a: [number, number, number];
    p: [number, number, number];
    color: string;
    rough?: number;
    metal?: number;
    opacity?: number;
}) {
    return (
        <mesh position={p} castShadow receiveShadow>
            <boxGeometry args={a} />
            <meshStandardMaterial
                color={color}
                roughness={rough}
                metalness={metal}
                transparent={opacity < 1}
                opacity={opacity}
            />
        </mesh>
    );
}

function Cyl({
    r,
    h,
    p,
    color,
    rough = 0.8,
    metal = 0,
}: {
    r: number;
    h: number;
    p: [number, number, number];
    color: string;
    rough?: number;
    metal?: number;
}) {
    return (
        <mesh position={p} castShadow receiveShadow>
            <cylinderGeometry args={[r, r, h, 18]} />
            <meshStandardMaterial color={color} roughness={rough} metalness={metal} />
        </mesh>
    );
}

function Chair({ p, rot = 0 }: { p: [number, number, number]; rot?: number }) {
    return (
        <group position={p} rotation={[0, rot, 0]}>
            <Box a={[0.45, 0.06, 0.45]} p={[0, 0.45, 0]} color={C.woodDark} />
            <Box a={[0.45, 0.5, 0.06]} p={[0, 0.7, -0.2]} color={C.woodDark} />
            <Box a={[0.05, 0.45, 0.05]} p={[-0.18, 0.22, -0.18]} color={C.woodDark} />
            <Box a={[0.05, 0.45, 0.05]} p={[0.18, 0.22, -0.18]} color={C.woodDark} />
            <Box a={[0.05, 0.45, 0.05]} p={[-0.18, 0.22, 0.18]} color={C.woodDark} />
            <Box a={[0.05, 0.45, 0.05]} p={[0.18, 0.22, 0.18]} color={C.woodDark} />
        </group>
    );
}

export default function FurniturePiece({ kind }: { kind: string }): ReactNode {
    switch (kind) {
        case "bed":
            return (
                <group>
                    <Box a={[1.7, 0.3, 2.05]} p={[0, 0.15, 0]} color={C.wood} />
                    <Box a={[1.6, 0.22, 1.95]} p={[0, 0.42, 0.02]} color={C.mattress} />
                    <Box a={[1.5, 0.12, 1.0]} p={[0, 0.5, 0.45]} color={C.sheet} />
                    <Box a={[1.8, 0.8, 0.12]} p={[0, 0.55, -1.0]} color={C.woodDark} />
                    <Box a={[0.7, 0.18, 0.4]} p={[-0.42, 0.58, -0.75]} color={C.pillow} />
                    <Box a={[0.7, 0.18, 0.4]} p={[0.42, 0.58, -0.75]} color={C.pillow} />
                </group>
            );
        case "nightstand":
            return <Box a={[0.5, 0.45, 0.42]} p={[0, 0.22, 0]} color={C.woodDark} />;
        case "wardrobe":
            return (
                <group>
                    <Box a={[1.8, 2.0, 0.6]} p={[0, 1.0, 0]} color={C.wood} />
                    <Box a={[0.04, 1.8, 0.02]} p={[-0.02, 1.0, 0.31]} color={C.metal} metal={0.6} rough={0.4} />
                </group>
            );
        case "rug":
            return <Box a={[2.3, 0.02, 1.7]} p={[0, 0.011, 0]} color={C.rug} rough={1} />;
        case "sofa":
            return (
                <group>
                    <Box a={[2.1, 0.4, 0.95]} p={[0, 0.2, 0]} color={C.fabric} rough={1} />
                    <Box a={[2.1, 0.55, 0.2]} p={[0, 0.5, -0.37]} color={C.fabric} rough={1} />
                    <Box a={[0.22, 0.5, 0.95]} p={[-0.94, 0.45, 0]} color={C.fabricLite} rough={1} />
                    <Box a={[0.22, 0.5, 0.95]} p={[0.94, 0.45, 0]} color={C.fabricLite} rough={1} />
                    <Box a={[0.9, 0.18, 0.8]} p={[-0.5, 0.49, 0.04]} color={C.fabricLite} rough={1} />
                    <Box a={[0.9, 0.18, 0.8]} p={[0.5, 0.49, 0.04]} color={C.fabricLite} rough={1} />
                </group>
            );
        case "coffee_table":
            return (
                <group>
                    <Box a={[1.0, 0.08, 0.55]} p={[0, 0.4, 0]} color={C.wood} rough={0.5} />
                    <Box a={[0.07, 0.4, 0.07]} p={[-0.42, 0.2, -0.2]} color={C.woodDark} />
                    <Box a={[0.07, 0.4, 0.07]} p={[0.42, 0.2, -0.2]} color={C.woodDark} />
                    <Box a={[0.07, 0.4, 0.07]} p={[-0.42, 0.2, 0.2]} color={C.woodDark} />
                    <Box a={[0.07, 0.4, 0.07]} p={[0.42, 0.2, 0.2]} color={C.woodDark} />
                </group>
            );
        case "tv_unit":
            return (
                <group>
                    <Box a={[1.7, 0.4, 0.4]} p={[0, 0.2, 0]} color={C.woodDark} />
                    <Box a={[1.3, 0.75, 0.05]} p={[0, 1.0, -0.12]} color={C.screen} rough={0.3} />
                </group>
            );
        case "plant":
            return (
                <group>
                    <Cyl r={0.22} h={0.34} p={[0, 0.17, 0]} color={C.pot} />
                    <mesh position={[0, 0.62, 0]} castShadow>
                        <icosahedronGeometry args={[0.35, 1]} />
                        <meshStandardMaterial color={C.green} roughness={1} flatShading />
                    </mesh>
                </group>
            );
        case "counter":
            return (
                <group>
                    <Box a={[2.2, 0.85, 0.6]} p={[0, 0.43, 0]} color={C.white} />
                    <Box a={[2.26, 0.06, 0.64]} p={[0, 0.88, 0]} color={C.stone} rough={0.4} />
                    <Box a={[0.05, 0.25, 0.05]} p={[0.5, 1.0, -0.1]} color={C.metal} metal={0.7} rough={0.3} />
                </group>
            );
        case "fridge":
            return (
                <group>
                    <Box a={[0.72, 1.8, 0.7]} p={[0, 0.9, 0]} color={C.steel} metal={0.5} rough={0.4} />
                    <Box a={[0.05, 0.5, 0.04]} p={[-0.3, 1.2, 0.36]} color={C.metal} metal={0.8} rough={0.3} />
                </group>
            );
        case "dining_table":
            return (
                <group>
                    <Box a={[1.7, 0.08, 1.0]} p={[0, 0.74, 0]} color={C.wood} rough={0.5} />
                    <Box a={[0.08, 0.74, 0.08]} p={[-0.75, 0.37, -0.4]} color={C.woodDark} />
                    <Box a={[0.08, 0.74, 0.08]} p={[0.75, 0.37, -0.4]} color={C.woodDark} />
                    <Box a={[0.08, 0.74, 0.08]} p={[-0.75, 0.37, 0.4]} color={C.woodDark} />
                    <Box a={[0.08, 0.74, 0.08]} p={[0.75, 0.37, 0.4]} color={C.woodDark} />
                    <Chair p={[0, 0, 0.85]} rot={Math.PI} />
                    <Chair p={[0, 0, -0.85]} rot={0} />
                    <Chair p={[1.05, 0, 0]} rot={-Math.PI / 2} />
                    <Chair p={[-1.05, 0, 0]} rot={Math.PI / 2} />
                </group>
            );
        case "toilet":
            return (
                <group>
                    <Cyl r={0.26} h={0.42} p={[0, 0.21, 0.05]} color={C.white} rough={0.3} />
                    <Box a={[0.5, 0.55, 0.2]} p={[0, 0.5, -0.28]} color={C.white} rough={0.3} />
                </group>
            );
        case "sink":
            return (
                <group>
                    <Cyl r={0.13} h={0.6} p={[0, 0.3, 0]} color={C.white} rough={0.3} />
                    <Box a={[0.55, 0.18, 0.42]} p={[0, 0.7, 0]} color={C.white} rough={0.3} />
                    <Box a={[0.04, 0.18, 0.04]} p={[0, 0.85, -0.12]} color={C.metal} metal={0.8} rough={0.2} />
                </group>
            );
        case "tub":
            return (
                <group>
                    <Box a={[1.7, 0.55, 0.75]} p={[0, 0.28, 0]} color={C.white} rough={0.25} />
                    <Box a={[1.5, 0.2, 0.58]} p={[0, 0.45, 0]} color={C.glass} rough={0.1} opacity={0.5} />
                </group>
            );
        case "shower":
            return (
                <group>
                    <Box a={[0.95, 0.06, 0.95]} p={[0, 0.03, 0]} color={C.stone} />
                    <Box a={[0.95, 1.9, 0.05]} p={[0, 0.95, -0.45]} color={C.glass} opacity={0.35} rough={0.05} />
                    <Box a={[0.05, 1.9, 0.95]} p={[0.45, 0.95, 0]} color={C.glass} opacity={0.35} rough={0.05} />
                </group>
            );
        case "desk":
            return (
                <group>
                    <Box a={[1.4, 0.05, 0.7]} p={[0, 0.74, 0]} color={C.wood} rough={0.5} />
                    <Box a={[0.05, 0.72, 0.6]} p={[-0.66, 0.36, 0]} color={C.woodDark} />
                    <Box a={[0.05, 0.72, 0.6]} p={[0.66, 0.36, 0]} color={C.woodDark} />
                </group>
            );
        case "chair":
            return <Chair p={[0, 0, 0]} />;
        case "shelf":
            return (
                <group>
                    <Box a={[0.9, 2.0, 0.32]} p={[0, 1.0, 0]} color={C.woodDark} />
                    <Box a={[0.86, 0.04, 0.3]} p={[0, 0.6, 0.01]} color={C.wood} />
                    <Box a={[0.86, 0.04, 0.3]} p={[0, 1.2, 0.01]} color={C.wood} />
                    <Box a={[0.86, 0.04, 0.3]} p={[0, 1.7, 0.01]} color={C.wood} />
                </group>
            );
        case "console":
            return <Box a={[1.0, 0.8, 0.35]} p={[0, 0.4, 0]} color={C.wood} />;
        case "lamp":
            return (
                <group>
                    <Cyl r={0.05} h={1.4} p={[0, 0.7, 0]} color={C.metal} metal={0.6} rough={0.4} />
                    <mesh position={[0, 1.45, 0]} castShadow>
                        <coneGeometry args={[0.22, 0.3, 18]} />
                        <meshStandardMaterial color={C.pillow} roughness={0.7} />
                    </mesh>
                </group>
            );
        default:
            return null;
    }
}
