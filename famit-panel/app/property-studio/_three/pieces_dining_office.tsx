"use client";
// Procedural furniture — DINING + OFFICE + MISC group.
// Each piece is centred on its local origin in X/Z with its base on y=0 (floor).
// FRONT faces +Z, BACK faces -Z. Parent applies world position + Y-rotation.
// Built from many small primitives (legs, frames, drawers, knobs, books, shades…).
import { RoundedBox } from "@react-three/drei";

const C = {
    woodDark: "#6b4f34",
    wood: "#9c6b3f",
    woodLite: "#b07d4a",
    fabric: "#7d8aa5",
    fabricLite: "#aab4c8",
    white: "#eef1f6",
    metal: "#b9bfc9",
    metalDark: "#3c424b",
    steel: "#cdd3db",
    // book spines
    bRed: "#8a3b2e",
    bNavy: "#2e3d5a",
    bGreen: "#3f6b4a",
    bMustard: "#c79a3c",
    bGrey: "#6b7280",
    bCream: "#d8cdb4",
    // lamp glow
    shade: "#ffe7bf",
    bulb: "#fff4d6",
    warmGlow: "#ffcf87",
};

type Vec3 = [number, number, number];

function Box({
    a,
    p,
    color,
    rough = 0.85,
    metal = 0,
    opacity = 1,
    rot = [0, 0, 0],
    emissive = "#000000",
    emissiveIntensity = 0,
}: {
    a: Vec3;
    p: Vec3;
    color: string;
    rough?: number;
    metal?: number;
    opacity?: number;
    rot?: Vec3;
    emissive?: string;
    emissiveIntensity?: number;
}) {
    const minDim = Math.min(a[0], a[1], a[2]);
    const radius = Math.max(0.004, Math.min(0.03, minDim * 0.2));
    return (
        <RoundedBox args={a} radius={radius} smoothness={3} steps={1} position={p} rotation={rot} castShadow receiveShadow>
            <meshStandardMaterial
                color={color}
                roughness={rough}
                metalness={metal}
                envMapIntensity={0.85}
                transparent={opacity < 1}
                opacity={opacity}
                emissive={emissive}
                emissiveIntensity={emissiveIntensity}
            />
        </RoundedBox>
    );
}

function Cyl({
    r,
    h,
    p,
    color,
    rough = 0.8,
    metal = 0,
    rTop,
    rot = [0, 0, 0],
    segs = 20,
    opacity = 1,
    emissive = "#000000",
    emissiveIntensity = 0,
}: {
    r: number;
    h: number;
    p: Vec3;
    color: string;
    rough?: number;
    metal?: number;
    rTop?: number;
    rot?: Vec3;
    segs?: number;
    opacity?: number;
    emissive?: string;
    emissiveIntensity?: number;
}) {
    return (
        <mesh position={p} rotation={rot} castShadow receiveShadow>
            <cylinderGeometry args={[rTop ?? r, r, h, segs]} />
            <meshStandardMaterial
                color={color}
                roughness={rough}
                metalness={metal}
                envMapIntensity={0.85}
                transparent={opacity < 1}
                opacity={opacity}
                emissive={emissive}
                emissiveIntensity={emissiveIntensity}
            />
        </mesh>
    );
}

// A single detailed chair — reused by Chair and DiningTable. Front faces +Z, back at -Z.
function ChairUnit({ p = [0, 0, 0] as Vec3, rotY = 0 }: { p?: Vec3; rotY?: number }) {
    return (
        <group position={p} rotation={[0, rotY, 0]}>
            {/* seat board + soft cushion */}
            <Box a={[0.46, 0.05, 0.44]} p={[0, 0.44, 0]} color={C.woodDark} rough={0.6} />
            <Box a={[0.42, 0.06, 0.4]} p={[0, 0.49, 0.01]} color={C.fabric} rough={1} />
            {/* four legs */}
            <Box a={[0.05, 0.44, 0.05]} p={[-0.19, 0.22, 0.18]} color={C.woodDark} rough={0.6} />
            <Box a={[0.05, 0.44, 0.05]} p={[0.19, 0.22, 0.18]} color={C.woodDark} rough={0.6} />
            <Box a={[0.05, 0.44, 0.05]} p={[-0.19, 0.22, -0.18]} color={C.woodDark} rough={0.6} />
            <Box a={[0.05, 0.44, 0.05]} p={[0.19, 0.22, -0.18]} color={C.woodDark} rough={0.6} />
            {/* reclined backrest pivoting at the seat's rear edge */}
            <group position={[0, 0.46, -0.2]} rotation={[-0.09, 0, 0]}>
                <Box a={[0.05, 0.52, 0.05]} p={[-0.19, 0.26, 0]} color={C.woodDark} rough={0.6} />
                <Box a={[0.05, 0.52, 0.05]} p={[0.19, 0.26, 0]} color={C.woodDark} rough={0.6} />
                <Box a={[0.46, 0.07, 0.06]} p={[0, 0.52, 0]} color={C.woodDark} rough={0.6} />
                <Box a={[0.36, 0.12, 0.03]} p={[0, 0.3, 0.005]} color={C.fabricLite} rough={1} />
            </group>
        </group>
    );
}

export function DiningTable() {
    return (
        <group>
            {/* top */}
            <Box a={[1.7, 0.08, 1.0]} p={[0, 0.74, 0]} color={C.wood} rough={0.45} />
            {/* apron rails just under the top */}
            <Box a={[1.5, 0.1, 0.06]} p={[0, 0.66, 0.42]} color={C.woodDark} />
            <Box a={[1.5, 0.1, 0.06]} p={[0, 0.66, -0.42]} color={C.woodDark} />
            <Box a={[0.06, 0.1, 0.78]} p={[-0.78, 0.66, 0]} color={C.woodDark} />
            <Box a={[0.06, 0.1, 0.78]} p={[0.78, 0.66, 0]} color={C.woodDark} />
            {/* four legs */}
            <Box a={[0.08, 0.66, 0.08]} p={[-0.75, 0.33, -0.4]} color={C.woodDark} />
            <Box a={[0.08, 0.66, 0.08]} p={[0.75, 0.33, -0.4]} color={C.woodDark} />
            <Box a={[0.08, 0.66, 0.08]} p={[-0.75, 0.33, 0.4]} color={C.woodDark} />
            <Box a={[0.08, 0.66, 0.08]} p={[0.75, 0.33, 0.4]} color={C.woodDark} />
            {/* four chairs facing the table */}
            <ChairUnit p={[0, 0, 0.95]} rotY={Math.PI} />
            <ChairUnit p={[0, 0, -0.95]} rotY={0} />
            <ChairUnit p={[1.05, 0, 0]} rotY={-Math.PI / 2} />
            <ChairUnit p={[-1.05, 0, 0]} rotY={Math.PI / 2} />
        </group>
    );
}

export function Desk() {
    return (
        <group>
            {/* worktop */}
            <Box a={[1.4, 0.05, 0.7]} p={[0, 0.74, 0]} color={C.wood} rough={0.45} />
            {/* two legs on the left side */}
            <Box a={[0.06, 0.72, 0.06]} p={[-0.6, 0.36, 0.3]} color={C.woodDark} />
            <Box a={[0.06, 0.72, 0.06]} p={[-0.6, 0.36, -0.3]} color={C.woodDark} />
            {/* modesty / back panel */}
            <Box a={[0.95, 0.35, 0.03]} p={[0, 0.52, -0.32]} color={C.woodDark} rough={0.7} />
            {/* drawer pedestal on the right */}
            <Box a={[0.46, 0.66, 0.62]} p={[0.6, 0.345, 0]} color={C.woodDark} />
            {/* three drawer fronts + bar pulls (front faces +Z) */}
            <Box a={[0.4, 0.18, 0.02]} p={[0.6, 0.6, 0.315]} color={C.woodLite} rough={0.5} />
            <Box a={[0.4, 0.18, 0.02]} p={[0.6, 0.4, 0.315]} color={C.woodLite} rough={0.5} />
            <Box a={[0.4, 0.18, 0.02]} p={[0.6, 0.2, 0.315]} color={C.woodLite} rough={0.5} />
            <Box a={[0.14, 0.02, 0.02]} p={[0.6, 0.6, 0.34]} color={C.metal} metal={0.7} rough={0.3} />
            <Box a={[0.14, 0.02, 0.02]} p={[0.6, 0.4, 0.34]} color={C.metal} metal={0.7} rough={0.3} />
            <Box a={[0.14, 0.02, 0.02]} p={[0.6, 0.2, 0.34]} color={C.metal} metal={0.7} rough={0.3} />
        </group>
    );
}

export function Chair() {
    return (
        <group>
            <ChairUnit />
        </group>
    );
}

export function Shelf() {
    return (
        <group>
            {/* carcass: two sides, back, top + bottom boards */}
            <Box a={[0.04, 2.0, 0.32]} p={[-0.43, 1.0, 0]} color={C.woodDark} />
            <Box a={[0.04, 2.0, 0.32]} p={[0.43, 1.0, 0]} color={C.woodDark} />
            <Box a={[0.86, 2.0, 0.025]} p={[0, 1.0, -0.145]} color={C.wood} rough={0.7} />
            <Box a={[0.9, 0.04, 0.32]} p={[0, 1.98, 0]} color={C.woodDark} />
            <Box a={[0.9, 0.06, 0.32]} p={[0, 0.04, 0]} color={C.woodDark} />
            {/* three internal shelves */}
            <Box a={[0.84, 0.04, 0.3]} p={[0, 0.6, 0.005]} color={C.wood} rough={0.6} />
            <Box a={[0.84, 0.04, 0.3]} p={[0, 1.14, 0.005]} color={C.wood} rough={0.6} />
            <Box a={[0.84, 0.04, 0.3]} p={[0, 1.68, 0.005]} color={C.wood} rough={0.6} />

            {/* books — bottom compartment (board top ≈ 0.07) */}
            <Box a={[0.05, 0.28, 0.18]} p={[-0.3, 0.21, 0]} color={C.bRed} rough={0.8} />
            <Box a={[0.045, 0.26, 0.18]} p={[-0.24, 0.2, 0]} color={C.bNavy} rough={0.8} />
            <Box a={[0.05, 0.24, 0.18]} p={[-0.18, 0.19, 0]} color={C.bGreen} rough={0.8} />
            <Box a={[0.045, 0.27, 0.18]} p={[-0.11, 0.2, 0]} color={C.bMustard} rough={0.8} rot={[0, 0, 0.18]} />
            <Box a={[0.2, 0.05, 0.16]} p={[0.22, 0.095, 0]} color={C.bGrey} rough={0.8} />
            <Box a={[0.18, 0.045, 0.15]} p={[0.22, 0.14, 0]} color={C.bCream} rough={0.8} />

            {/* books — middle compartment (board top ≈ 0.62) */}
            <Box a={[0.05, 0.26, 0.18]} p={[-0.28, 0.75, 0]} color={C.bNavy} rough={0.8} />
            <Box a={[0.05, 0.28, 0.18]} p={[-0.22, 0.76, 0]} color={C.bRed} rough={0.8} />
            <Box a={[0.045, 0.24, 0.18]} p={[-0.16, 0.74, 0]} color={C.bMustard} rough={0.8} />
            <Box a={[0.05, 0.25, 0.18]} p={[0.25, 0.745, 0]} color={C.bGreen} rough={0.8} rot={[0, 0, -0.16]} />

            {/* books — upper compartment (board top ≈ 1.16) */}
            <Box a={[0.05, 0.26, 0.18]} p={[-0.3, 1.29, 0]} color={C.bGrey} rough={0.8} />
            <Box a={[0.05, 0.24, 0.18]} p={[-0.24, 1.28, 0]} color={C.bRed} rough={0.8} />
            <Box a={[0.22, 0.05, 0.16]} p={[0.15, 1.185, 0]} color={C.bNavy} rough={0.8} />
            <Box a={[0.2, 0.045, 0.15]} p={[0.15, 1.23, 0]} color={C.bMustard} rough={0.8} />
        </group>
    );
}

export function Console() {
    return (
        <group>
            {/* slim top */}
            <Box a={[1.0, 0.04, 0.35]} p={[0, 0.78, 0]} color={C.wood} rough={0.45} />
            {/* drawer apron */}
            <Box a={[0.86, 0.16, 0.3]} p={[0, 0.68, 0]} color={C.wood} />
            {/* drawer front + two knobs (front faces +Z) */}
            <Box a={[0.5, 0.12, 0.02]} p={[0, 0.68, 0.155]} color={C.woodDark} rough={0.5} />
            <mesh position={[-0.12, 0.68, 0.18]} castShadow>
                <sphereGeometry args={[0.022, 16, 16]} />
                <meshStandardMaterial color={C.metal} metalness={0.7} roughness={0.3} envMapIntensity={0.85} />
            </mesh>
            <mesh position={[0.12, 0.68, 0.18]} castShadow>
                <sphereGeometry args={[0.022, 16, 16]} />
                <meshStandardMaterial color={C.metal} metalness={0.7} roughness={0.3} envMapIntensity={0.85} />
            </mesh>
            {/* four tapered legs + a low stretcher shelf */}
            <Box a={[0.05, 0.76, 0.05]} p={[-0.45, 0.38, 0.14]} color={C.woodDark} />
            <Box a={[0.05, 0.76, 0.05]} p={[0.45, 0.38, 0.14]} color={C.woodDark} />
            <Box a={[0.05, 0.76, 0.05]} p={[-0.45, 0.38, -0.14]} color={C.woodDark} />
            <Box a={[0.05, 0.76, 0.05]} p={[0.45, 0.38, -0.14]} color={C.woodDark} />
            <Box a={[0.86, 0.025, 0.28]} p={[0, 0.18, 0]} color={C.woodDark} rough={0.6} />
        </group>
    );
}

export function Lamp() {
    return (
        <group>
            {/* weighted base */}
            <Cyl r={0.18} h={0.03} p={[0, 0.015, 0]} color={C.metalDark} metal={0.6} rough={0.45} />
            <Cyl r={0.12} h={0.05} p={[0, 0.05, 0]} color={C.metalDark} metal={0.6} rough={0.45} />
            {/* thin pole */}
            <Cyl r={0.022} h={1.5} p={[0, 0.78, 0]} color={C.metal} metal={0.7} rough={0.3} />
            {/* glowing bulb inside the shade */}
            <mesh position={[0, 1.5, 0]}>
                <sphereGeometry args={[0.07, 18, 18]} />
                <meshStandardMaterial color={C.bulb} emissive={C.warmGlow} emissiveIntensity={2.4} roughness={0.4} />
            </mesh>
            {/* tapered drum shade — softly emissive so it reads as lit */}
            <Cyl
                r={0.22}
                rTop={0.16}
                h={0.3}
                p={[0, 1.55, 0]}
                color={C.shade}
                rough={0.6}
                opacity={0.92}
                emissive={C.warmGlow}
                emissiveIntensity={0.35}
            />
            {/* finial */}
            <mesh position={[0, 1.73, 0]} castShadow>
                <sphereGeometry args={[0.03, 14, 14]} />
                <meshStandardMaterial color={C.metal} metalness={0.7} roughness={0.3} envMapIntensity={0.85} />
            </mesh>
        </group>
    );
}
