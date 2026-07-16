"use client";
// Procedural BEDROOM furniture for the interior viewer.
// Conventions: Y-up, metres. Each piece is centred on the local origin in X/Z with its
// base on y=0. FRONT faces +Z, BACK faces -Z (bed headboard / wardrobe back are at -Z).
// The parent applies world position + Y-rotation, so no world position is baked in here.
import { RoundedBox } from "@react-three/drei";

const C = {
    woodDark: "#6b4f34",
    wood: "#9c6b3f",
    woodWarm: "#8a5e38",
    mattress: "#e7e3da",
    sheet: "#dde4ee",
    duvet: "#7f90ab",
    duvetFold: "#9aa9c1",
    pillow: "#eef2f8",
    pillowAlt: "#e2e8f2",
    headboard: "#6f7c93",
    metal: "#b9bfc9",
    knob: "#c7ccd4",
    panel: "#92633a",
};

// Soft-edged box. radius follows the house formula (capped at 0.03).
function Box({
    a,
    p,
    r = [0, 0, 0],
    color,
    rough = 0.8,
    metal = 0,
    opacity = 1,
}: {
    a: [number, number, number];
    p: [number, number, number];
    r?: [number, number, number];
    color: string;
    rough?: number;
    metal?: number;
    opacity?: number;
}) {
    const radius = Math.max(0.004, Math.min(0.03, Math.min(a[0], a[1], a[2]) * 0.2));
    return (
        <RoundedBox
            args={a}
            radius={radius}
            smoothness={3}
            steps={1}
            position={p}
            rotation={r}
            castShadow
            receiveShadow
        >
            <meshStandardMaterial
                color={color}
                roughness={rough}
                metalness={metal}
                envMapIntensity={0.85}
                transparent={opacity < 1}
                opacity={opacity}
            />
        </RoundedBox>
    );
}

function Cyl({
    r,
    h,
    p,
    rot = [0, 0, 0],
    color,
    rough = 0.4,
    metal = 0.7,
}: {
    r: number;
    h: number;
    p: [number, number, number];
    rot?: [number, number, number];
    color: string;
    rough?: number;
    metal?: number;
}) {
    return (
        <mesh position={p} rotation={rot} castShadow receiveShadow>
            <cylinderGeometry args={[r, r, h, 20]} />
            <meshStandardMaterial color={color} roughness={rough} metalness={metal} envMapIntensity={0.85} />
        </mesh>
    );
}

function Knob({ p }: { p: [number, number, number] }) {
    return (
        <mesh position={p} castShadow receiveShadow>
            <sphereGeometry args={[0.025, 18, 18]} />
            <meshStandardMaterial color={C.knob} roughness={0.3} metalness={0.7} envMapIntensity={0.85} />
        </mesh>
    );
}

// ── BED ─ 1.7w x 2.05d, headboard at -Z ──────────────────────────────────────
export function Bed() {
    // tufting buttons across the padded headboard (front face at z ≈ -0.94)
    const tufts: [number, number, number][] = [
        [-0.5, 0.62, -0.93],
        [0, 0.62, -0.93],
        [0.5, 0.62, -0.93],
        [-0.5, 0.97, -0.93],
        [0, 0.97, -0.93],
        [0.5, 0.97, -0.93],
    ];
    return (
        <group>
            {/* short legs */}
            <Box a={[0.1, 0.2, 0.1]} p={[-0.76, 0.1, -0.9]} color={C.woodDark} rough={0.6} />
            <Box a={[0.1, 0.2, 0.1]} p={[0.76, 0.1, -0.9]} color={C.woodDark} rough={0.6} />
            <Box a={[0.1, 0.2, 0.1]} p={[-0.76, 0.1, 0.9]} color={C.woodDark} rough={0.6} />
            <Box a={[0.1, 0.2, 0.1]} p={[0.76, 0.1, 0.9]} color={C.woodDark} rough={0.6} />

            {/* slat deck + frame rails (mattress sits recessed inside) */}
            <Box a={[1.66, 0.1, 2.0]} p={[0, 0.25, 0]} color={C.wood} rough={0.6} />
            <Box a={[0.09, 0.28, 2.05]} p={[-0.81, 0.34, 0]} color={C.woodWarm} rough={0.55} />
            <Box a={[0.09, 0.28, 2.05]} p={[0.81, 0.34, 0]} color={C.woodWarm} rough={0.55} />
            <Box a={[1.7, 0.28, 0.09]} p={[0, 0.34, 0.99]} color={C.woodWarm} rough={0.55} />

            {/* recessed mattress + thin top sheet under the pillows */}
            <Box a={[1.58, 0.22, 1.9]} p={[0, 0.41, 0.02]} color={C.mattress} rough={0.92} />
            <Box a={[1.6, 0.04, 0.32]} p={[0, 0.54, -0.45]} color={C.sheet} rough={0.95} />

            {/* duvet — slightly rumpled top box + a folded edge near the foot */}
            <Box a={[1.64, 0.12, 1.42]} p={[0, 0.56, 0.24]} r={[0.012, 0, 0.02]} color={C.duvet} rough={0.96} />
            <Box a={[1.64, 0.09, 0.32]} p={[0, 0.6, 0.9]} r={[-0.2, 0, 0]} color={C.duvetFold} rough={0.96} />

            {/* two pillows leaning on the headboard */}
            <Box a={[0.66, 0.18, 0.4]} p={[-0.4, 0.62, -0.7]} r={[-0.15, 0.05, 0]} color={C.pillow} rough={0.95} />
            <Box a={[0.66, 0.18, 0.4]} p={[0.4, 0.62, -0.7]} r={[-0.15, -0.05, 0]} color={C.pillowAlt} rough={0.95} />

            {/* tall padded headboard at -Z + side posts + top trim */}
            <Box a={[1.6, 1.0, 0.12]} p={[0, 0.72, -1.0]} color={C.headboard} rough={0.95} />
            <Box a={[0.1, 1.05, 0.14]} p={[-0.83, 0.72, -1.0]} color={C.woodDark} rough={0.6} />
            <Box a={[0.1, 1.05, 0.14]} p={[0.83, 0.72, -1.0]} color={C.woodDark} rough={0.6} />
            <Box a={[1.74, 0.08, 0.16]} p={[0, 1.24, -1.0]} color={C.woodDark} rough={0.6} />
            {tufts.map((t, i) => (
                <mesh key={i} position={t} castShadow receiveShadow>
                    <sphereGeometry args={[0.022, 14, 14]} />
                    <meshStandardMaterial color="#5d6a80" roughness={0.85} envMapIntensity={0.85} />
                </mesh>
            ))}
        </group>
    );
}

// ── NIGHTSTAND ─ 0.5 x 0.45h x 0.42 ──────────────────────────────────────────
export function Nightstand() {
    return (
        <group>
            {/* legs */}
            <Box a={[0.06, 0.13, 0.06]} p={[-0.2, 0.065, -0.16]} color={C.woodDark} rough={0.6} />
            <Box a={[0.06, 0.13, 0.06]} p={[0.2, 0.065, -0.16]} color={C.woodDark} rough={0.6} />
            <Box a={[0.06, 0.13, 0.06]} p={[-0.2, 0.065, 0.16]} color={C.woodDark} rough={0.6} />
            <Box a={[0.06, 0.13, 0.06]} p={[0.2, 0.065, 0.16]} color={C.woodDark} rough={0.6} />

            {/* body + top surface */}
            <Box a={[0.46, 0.32, 0.4]} p={[0, 0.29, 0]} color={C.wood} rough={0.6} />
            <Box a={[0.52, 0.03, 0.44]} p={[0, 0.465, 0]} color={C.woodWarm} rough={0.45} />

            {/* two drawer faces with round knobs */}
            <Box a={[0.4, 0.13, 0.02]} p={[0, 0.37, 0.205]} color={C.woodWarm} rough={0.55} />
            <Box a={[0.4, 0.13, 0.02]} p={[0, 0.21, 0.205]} color={C.woodWarm} rough={0.55} />
            <Knob p={[0, 0.37, 0.225]} />
            <Knob p={[0, 0.21, 0.225]} />
        </group>
    );
}

// ── WARDROBE ─ 1.8w x 2.0h x 0.6d, two doors with centre seam ─────────────────
export function Wardrobe() {
    return (
        <group>
            {/* base plinth + main body + top cornice */}
            <Box a={[1.8, 0.1, 0.6]} p={[0, 0.05, 0]} color={C.woodDark} rough={0.6} />
            <Box a={[1.76, 1.78, 0.58]} p={[0, 0.99, 0]} color={C.wood} rough={0.6} />
            <Box a={[1.86, 0.1, 0.66]} p={[0, 1.93, 0]} color={C.woodDark} rough={0.55} />

            {/* two doors (gap down the middle = seam) */}
            <Box a={[0.84, 1.7, 0.04]} p={[-0.44, 0.99, 0.29]} color={C.woodWarm} rough={0.55} />
            <Box a={[0.84, 1.7, 0.04]} p={[0.44, 0.99, 0.29]} color={C.woodWarm} rough={0.55} />

            {/* recessed decorative panels on each door */}
            <Box a={[0.64, 0.74, 0.015]} p={[-0.44, 1.32, 0.305]} color={C.panel} rough={0.6} />
            <Box a={[0.64, 0.74, 0.015]} p={[-0.44, 0.5, 0.305]} color={C.panel} rough={0.6} />
            <Box a={[0.64, 0.74, 0.015]} p={[0.44, 1.32, 0.305]} color={C.panel} rough={0.6} />
            <Box a={[0.64, 0.74, 0.015]} p={[0.44, 0.5, 0.305]} color={C.panel} rough={0.6} />

            {/* vertical handles flanking the seam */}
            <Cyl r={0.013} h={0.5} p={[-0.07, 0.99, 0.33]} color={C.metal} />
            <Cyl r={0.013} h={0.5} p={[0.07, 0.99, 0.33]} color={C.metal} />
        </group>
    );
}
