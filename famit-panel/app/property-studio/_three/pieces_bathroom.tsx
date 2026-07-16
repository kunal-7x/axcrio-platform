"use client";
// Procedural BATHROOM fixtures — white ceramics + chrome.
// Conventions: Y-up, metres. Each piece centred on local X/Z origin, base on y=0.
// FRONT faces +Z, BACK faces -Z (toilet tank / shower walls / mirror live at -Z).
// Parent applies world position + rotationY; no world position baked here.
import { RoundedBox } from "@react-three/drei";

type V3 = [number, number, number];

const C = {
    white: "#eef1f6",
    ceramic: "#f3f5f9",
    ceramicDark: "#d6dae2",
    chrome: "#cdd3db",
    metal: "#b9bfc9",
    stone: "#d7dbe2",
    glass: "#cfe6f1",
    water: "#dceef4",
    mirror: "#dbe7ef",
    seat: "#e9ecf2",
};

function Box({
    a,
    p,
    color,
    rough = 0.4,
    metal = 0,
    opacity = 1,
    rot,
}: {
    a: V3;
    p: V3;
    color: string;
    rough?: number;
    metal?: number;
    opacity?: number;
    rot?: V3;
}) {
    const radius = Math.max(0.004, Math.min(0.03, Math.min(a[0], a[1], a[2]) * 0.2));
    return (
        <RoundedBox args={a} radius={radius} smoothness={3} position={p} rotation={rot} castShadow receiveShadow>
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
    r2,
    h,
    p,
    color,
    rough = 0.3,
    metal = 0,
    rot,
    seg = 20,
}: {
    r: number;
    r2?: number;
    h: number;
    p: V3;
    color: string;
    rough?: number;
    metal?: number;
    rot?: V3;
    seg?: number;
}) {
    return (
        <mesh position={p} rotation={rot} castShadow receiveShadow>
            <cylinderGeometry args={[r, r2 ?? r, h, seg]} />
            <meshStandardMaterial color={color} roughness={rough} metalness={metal} envMapIntensity={0.85} />
        </mesh>
    );
}

function Torus({
    r,
    t,
    p,
    color,
    rough = 0.3,
    metal = 0,
    rot,
}: {
    r: number;
    t: number;
    p: V3;
    color: string;
    rough?: number;
    metal?: number;
    rot?: V3;
}) {
    return (
        <mesh position={p} rotation={rot} castShadow receiveShadow>
            <torusGeometry args={[r, t, 16, 32]} />
            <meshStandardMaterial color={color} roughness={rough} metalness={metal} envMapIntensity={0.85} />
        </mesh>
    );
}

// Shorthand chrome helpers keep the fixtures consistent.
const CHROME = { color: C.chrome, metal: 0.85, rough: 0.15 } as const;

export function Toilet() {
    return (
        <group>
            {/* tapered pedestal foot */}
            <Cyl r={0.13} r2={0.2} h={0.42} p={[0, 0.21, 0.04]} color={C.white} rough={0.35} />
            {/* bowl exterior */}
            <Box a={[0.38, 0.22, 0.5]} p={[0, 0.44, 0.06]} color={C.white} rough={0.3} />
            {/* inner basin recess */}
            <Cyl r={0.15} r2={0.11} h={0.16} p={[0, 0.46, 0.09]} color={C.ceramicDark} rough={0.25} />
            {/* seat ring */}
            <Torus r={0.165} t={0.03} p={[0, 0.555, 0.09]} color={C.seat} rough={0.35} rot={[Math.PI / 2, 0, 0]} />
            {/* lid, raised back against the tank */}
            <Box a={[0.37, 0.42, 0.04]} p={[0, 0.74, -0.13]} color={C.white} rough={0.3} rot={[-0.12, 0, 0]} />
            {/* cistern / tank at -Z */}
            <Box a={[0.5, 0.5, 0.18]} p={[0, 0.62, -0.33]} color={C.white} rough={0.3} />
            {/* tank lid */}
            <Box a={[0.54, 0.05, 0.22]} p={[0, 0.89, -0.33]} color={C.white} rough={0.3} />
            {/* dual flush button */}
            <Cyl r={0.045} h={0.03} p={[0, 0.915, -0.33]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            <Cyl r={0.022} h={0.035} p={[0.02, 0.917, -0.33]} color={C.metal} metal={0.8} rough={0.2} />
        </group>
    );
}

export function Sink() {
    return (
        <group>
            {/* vanity cabinet */}
            <Box a={[0.6, 0.68, 0.45]} p={[0, 0.34, 0]} color={C.ceramic} rough={0.4} />
            {/* two cabinet doors */}
            <Box a={[0.27, 0.58, 0.02]} p={[-0.145, 0.36, 0.23]} color={C.white} rough={0.35} />
            <Box a={[0.27, 0.58, 0.02]} p={[0.145, 0.36, 0.23]} color={C.white} rough={0.35} />
            {/* chrome bar handles */}
            <Cyl r={0.012} h={0.12} p={[-0.02, 0.36, 0.25]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} rot={[0, 0, Math.PI / 2]} />
            <Cyl r={0.012} h={0.12} p={[0.02, 0.36, 0.25]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} rot={[0, 0, Math.PI / 2]} />
            {/* stone countertop */}
            <Box a={[0.66, 0.05, 0.5]} p={[0, 0.705, 0]} color={C.stone} rough={0.3} />
            {/* vessel basin + inner recess */}
            <Cyl r={0.17} r2={0.14} h={0.13} p={[0, 0.795, 0.03]} color={C.white} rough={0.25} />
            <Cyl r={0.14} r2={0.1} h={0.1} p={[0, 0.815, 0.03]} color={C.ceramicDark} rough={0.2} />
            {/* faucet neck + curved spout + handle */}
            <Cyl r={0.022} h={0.2} p={[0, 0.83, -0.13]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            <Cyl r={0.018} h={0.13} p={[0, 0.93, -0.07]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} rot={[Math.PI / 2.4, 0, 0]} />
            <Box a={[0.07, 0.02, 0.02]} p={[0.06, 0.84, -0.13]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            {/* wall mirror at -Z: chrome frame + reflective glass */}
            <Box a={[0.52, 0.72, 0.03]} p={[0, 1.35, -0.215]} color={C.chrome} metal={0.8} rough={0.2} />
            <Box a={[0.46, 0.66, 0.012]} p={[0, 1.35, -0.2]} color={C.mirror} metal={0.95} rough={0.05} />
        </group>
    );
}

export function Tub() {
    return (
        <group>
            {/* outer tub body */}
            <Box a={[1.7, 0.5, 0.75]} p={[0, 0.25, 0]} color={C.white} rough={0.3} />
            {/* rolled rim lip */}
            <Box a={[1.74, 0.07, 0.79]} p={[0, 0.5, 0]} color={C.white} rough={0.28} />
            {/* recessed inner well (reads as the basin) */}
            <Box a={[1.46, 0.34, 0.56]} p={[0, 0.36, 0]} color={C.water} rough={0.15} />
            {/* faucet base + curved spout over the well */}
            <Cyl r={0.03} h={0.14} p={[-0.74, 0.56, 0]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            <Cyl r={0.022} h={0.2} p={[-0.66, 0.63, 0]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} rot={[0, 0, Math.PI / 2.3]} />
            {/* hot / cold tap knobs */}
            <Cyl r={0.025} h={0.05} p={[-0.74, 0.55, 0.13]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            <Cyl r={0.025} h={0.05} p={[-0.74, 0.55, -0.13]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            {/* base plinth */}
            <Box a={[1.6, 0.06, 0.65]} p={[0, 0.03, 0]} color={C.ceramicDark} rough={0.5} />
        </group>
    );
}

export function Shower() {
    return (
        <group>
            {/* tray + white lip + drain */}
            <Box a={[0.95, 0.08, 0.95]} p={[0, 0.04, 0]} color={C.stone} rough={0.4} />
            <Box a={[0.93, 0.02, 0.93]} p={[0, 0.085, 0]} color={C.white} rough={0.3} />
            <Cyl r={0.04} h={0.012} p={[0, 0.095, 0]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            {/* back glass panel (-Z) and side glass panel (+X) */}
            <Box a={[0.95, 1.9, 0.03]} p={[0, 1.05, -0.46]} color={C.glass} rough={0.05} metal={0.1} opacity={0.28} />
            <Box a={[0.03, 1.9, 0.95]} p={[0.46, 1.05, 0]} color={C.glass} rough={0.05} metal={0.1} opacity={0.28} />
            {/* corner post + top rails framing the glass */}
            <Cyl r={0.02} h={1.95} p={[0.455, 1.05, -0.455]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            <Box a={[0.95, 0.03, 0.04]} p={[0, 2.0, -0.45]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            <Box a={[0.04, 0.03, 0.95]} p={[0.45, 2.0, 0]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} />
            {/* shower head: arm from back wall + tilted disc */}
            <Cyl r={0.018} h={0.22} p={[-0.2, 1.85, -0.36]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} rot={[Math.PI / 2, 0, 0]} />
            <Cyl r={0.09} h={0.03} p={[-0.2, 1.82, -0.22]} color={CHROME.color} metal={CHROME.metal} rough={0.2} rot={[0.25, 0, 0]} />
            {/* mixer control: wall plate + handle */}
            <Cyl r={0.06} h={0.03} p={[-0.2, 1.05, -0.44]} color={CHROME.color} metal={CHROME.metal} rough={CHROME.rough} rot={[Math.PI / 2, 0, 0]} />
            <Cyl r={0.015} h={0.1} p={[-0.2, 1.05, -0.4]} color={C.metal} metal={0.8} rough={0.2} rot={[Math.PI / 2, 0, 0]} />
        </group>
    );
}
