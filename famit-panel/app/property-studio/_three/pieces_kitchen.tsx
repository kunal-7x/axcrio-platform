"use client";
// Procedural KITCHEN furniture — counter + fridge.
// Conventions: Y-up, metres. Each piece centred on local origin in X/Z, base on y=0.
// FRONT faces +Z, BACK faces -Z. Parent applies world position + Y-rotation.
import { RoundedBox } from "@react-three/drei";

const C = {
    cabinet: "#eef1f6", // bright lacquered door fronts
    carcass: "#dfe3ea", // slightly cooler cabinet body
    upper: "#e6e9f0",
    stone: "#d7dbe2", // quartz countertop slab
    steel: "#cdd3db", // stainless body
    steelDark: "#9aa1ab", // sink basin interior
    metal: "#b9bfc9", // handles / faucet
    cooktop: "#1b2130", // dark glass cooktop
    burner: "#3a3f48",
    toe: "#4a4f57", // recessed toe kick / base
    panel: "#222733", // fridge dispenser face
};

type Vec3 = [number, number, number];

function Box({
    a,
    p,
    color,
    rough = 0.7,
    metal = 0,
    opacity = 1,
    rot,
    emissive,
    emissiveIntensity,
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
        <RoundedBox
            args={a}
            radius={radius}
            smoothness={3}
            steps={1}
            position={p}
            rotation={rot}
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
    rough = 0.3,
    metal = 0.7,
    rot,
}: {
    r: number;
    h: number;
    p: Vec3;
    color: string;
    rough?: number;
    metal?: number;
    rot?: Vec3;
}) {
    return (
        <mesh position={p} rotation={rot} castShadow receiveShadow>
            <cylinderGeometry args={[r, r, h, 20]} />
            <meshStandardMaterial color={color} roughness={rough} metalness={metal} envMapIntensity={0.85} />
        </mesh>
    );
}

function Burner({ p }: { p: Vec3 }) {
    return (
        <mesh position={p} rotation={[-Math.PI / 2, 0, 0]} castShadow receiveShadow>
            <torusGeometry args={[0.07, 0.012, 10, 24]} />
            <meshStandardMaterial color={C.burner} roughness={0.5} metalness={0.6} envMapIntensity={0.85} />
        </mesh>
    );
}

// counter: ~2.2w x 0.9h x 0.6d — base cabinets, stone top, inset sink + faucet,
// dark-glass cooktop with burner rings, and a floating run of upper cabinets.
export function Counter() {
    // four base doors paired around the two central gaps (-0.54 and +0.54)
    const doors: { x: number; hx: number }[] = [
        { x: -0.81, hx: -0.6 },
        { x: -0.27, hx: -0.48 },
        { x: 0.27, hx: 0.48 },
        { x: 0.81, hx: 0.6 },
    ];
    return (
        <group>
            {/* recessed toe kick */}
            <Box a={[2.1, 0.1, 0.46]} p={[0, 0.05, -0.03]} color={C.toe} rough={0.9} />
            {/* base cabinet carcass */}
            <Box a={[2.18, 0.72, 0.56]} p={[0, 0.46, 0]} color={C.carcass} rough={0.55} />
            {/* stone countertop slab (overhangs front + sides) */}
            <Box a={[2.26, 0.06, 0.64]} p={[0, 0.85, 0.01]} color={C.stone} rough={0.35} metal={0.05} />

            {/* door fronts + slim metal bar handles */}
            {doors.map((d, i) => (
                <Box key={i} a={[0.5, 0.64, 0.03]} p={[d.x, 0.46, 0.3]} color={C.cabinet} rough={0.45} />
            ))}
            {doors.map((d, i) => (
                <Cyl key={`h${i}`} r={0.012} h={0.3} p={[d.hx, 0.46, 0.31]} color={C.metal} rough={0.3} metal={0.8} />
            ))}

            {/* inset stainless sink (rim flush with top, recessed basin below) */}
            <Box a={[0.52, 0.04, 0.42]} p={[0.55, 0.865, 0.02]} color={C.steel} rough={0.3} metal={0.6} />
            <Box a={[0.44, 0.12, 0.34]} p={[0.55, 0.8, 0.02]} color={C.steelDark} rough={0.35} metal={0.5} />
            {/* faucet: thin post + forward gooseneck spout */}
            <Cyl r={0.016} h={0.26} p={[0.55, 1.0, -0.13]} color={C.metal} rough={0.25} metal={0.85} />
            <Cyl
                r={0.016}
                h={0.2}
                p={[0.55, 1.12, -0.03]}
                rot={[Math.PI / 2, 0, 0]}
                color={C.metal}
                rough={0.25}
                metal={0.85}
            />

            {/* dark-glass cooktop with four burner rings */}
            <Box a={[0.6, 0.03, 0.5]} p={[-0.55, 0.875, 0.02]} color={C.cooktop} rough={0.2} metal={0.3} />
            <Burner p={[-0.68, 0.9, -0.09]} />
            <Burner p={[-0.42, 0.9, -0.09]} />
            <Burner p={[-0.68, 0.9, 0.13]} />
            <Burner p={[-0.42, 0.9, 0.13]} />

            {/* floating upper cabinets against the back wall */}
            <Box a={[2.0, 0.62, 0.34]} p={[0, 1.8, -0.13]} color={C.upper} rough={0.55} />
            <Box a={[0.94, 0.56, 0.03]} p={[-0.5, 1.8, 0.045]} color={C.cabinet} rough={0.45} />
            <Box a={[0.94, 0.56, 0.03]} p={[0.5, 1.8, 0.045]} color={C.cabinet} rough={0.45} />
            <Cyl r={0.011} h={0.22} p={[-0.06, 1.62, 0.07]} color={C.metal} rough={0.3} metal={0.8} />
            <Cyl r={0.011} h={0.22} p={[0.06, 1.62, 0.07]} color={C.metal} rough={0.3} metal={0.8} />
        </group>
    );
}

// fridge: ~0.72w x 1.8h x 0.7d — stainless French-door (two top doors split at
// centre) over a freezer drawer, two long vertical handles + base kick.
export function Fridge() {
    return (
        <group>
            {/* recessed base kick */}
            <Box a={[0.7, 0.08, 0.6]} p={[0, 0.04, -0.03]} color={C.toe} rough={0.9} />
            {/* stainless body */}
            <Box a={[0.72, 1.72, 0.68]} p={[0, 0.94, 0]} color={C.steel} rough={0.4} metal={0.5} />

            {/* bottom freezer drawer front */}
            <Box a={[0.7, 0.5, 0.04]} p={[0, 0.36, 0.34]} color={C.steel} rough={0.38} metal={0.55} />
            {/* two French doors split at centre */}
            <Box a={[0.345, 1.12, 0.04]} p={[-0.18, 1.2, 0.35]} color={C.steel} rough={0.38} metal={0.55} />
            <Box a={[0.345, 1.12, 0.04]} p={[0.18, 1.2, 0.35]} color={C.steel} rough={0.38} metal={0.55} />

            {/* recessed water/ice dispenser panel (faintly lit) */}
            <Box
                a={[0.16, 0.3, 0.015]}
                p={[-0.18, 1.25, 0.375]}
                color={C.panel}
                rough={0.4}
                metal={0.3}
                emissive="#3a4a6a"
                emissiveIntensity={0.45}
            />

            {/* long vertical door handles near the centre split */}
            <Cyl r={0.018} h={0.95} p={[-0.06, 1.2, 0.4]} color={C.metal} rough={0.25} metal={0.85} />
            <Cyl r={0.018} h={0.95} p={[0.06, 1.2, 0.4]} color={C.metal} rough={0.25} metal={0.85} />
            {/* horizontal freezer handle */}
            <Cyl
                r={0.018}
                h={0.5}
                p={[0, 0.56, 0.4]}
                rot={[0, 0, Math.PI / 2]}
                color={C.metal}
                rough={0.25}
                metal={0.85}
            />
        </group>
    );
}