"use client";
// Procedural LIVING-ROOM furniture. Each kind is one PascalCase component, centred
// on the local origin in X/Z with its base on y=0. FRONT faces +Z, BACK faces -Z.
// Parent applies world position + Y-rotation, so no world position is baked in here.
import { RoundedBox } from "@react-three/drei";

const C = {
    woodDark: "#6b4f34",
    wood: "#9c6b3f",
    fabricDark: "#5f6c84",
    fabric: "#6f7d97",
    fabricLite: "#8593ac",
    accent: "#c98b6e",
    pillow: "#b6c1d4",
    metal: "#b9bfc9",
    metalDark: "#8d93a0",
    screenBody: "#13161d",
    screenEmiss: "#1f3f63",
    soundbar: "#262a31",
    rugBorder: "#a8674f",
    rugField: "#cf8a72",
    rugStripe: "#e6c4ab",
    ceramic: "#e8e1d5",
    rim: "#d9d0c2",
    soil: "#3a2e24",
    trunk: "#7a5a3a",
    leaf1: "#4f8f5b",
    leaf2: "#3e7a4a",
    leaf3: "#5fa06a",
    leaf4: "#6fae73",
};

function Box({
    a,
    p,
    color,
    rot = [0, 0, 0],
    rough = 0.85,
    metal = 0,
    opacity = 1,
}: {
    a: [number, number, number];
    p: [number, number, number];
    color: string;
    rot?: [number, number, number];
    rough?: number;
    metal?: number;
    opacity?: number;
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
            />
        </RoundedBox>
    );
}

function Cyl({
    r,
    h,
    p,
    color,
    rot = [0, 0, 0],
    rough = 0.8,
    metal = 0,
}: {
    r: number;
    h: number;
    p: [number, number, number];
    color: string;
    rot?: [number, number, number];
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

// ~2.1w x 0.8h x 0.95d — soft fabric three-seater.
export function Sofa() {
    return (
        <group>
            {/* tapered metal feet */}
            <Cyl r={0.045} h={0.14} p={[-0.9, 0.07, 0.36]} color={C.metalDark} metal={0.7} rough={0.35} />
            <Cyl r={0.045} h={0.14} p={[0.9, 0.07, 0.36]} color={C.metalDark} metal={0.7} rough={0.35} />
            <Cyl r={0.045} h={0.14} p={[-0.9, 0.07, -0.36]} color={C.metalDark} metal={0.7} rough={0.35} />
            <Cyl r={0.045} h={0.14} p={[0.9, 0.07, -0.36]} color={C.metalDark} metal={0.7} rough={0.35} />
            {/* base plinth + seat platform */}
            <Box a={[2.0, 0.18, 0.92]} p={[0, 0.21, 0]} color={C.fabricDark} rough={1} />
            <Box a={[1.64, 0.12, 0.84]} p={[0, 0.33, 0.02]} color={C.fabric} rough={1} />
            {/* 3 seat cushions */}
            <Box a={[0.5, 0.22, 0.82]} p={[-0.55, 0.45, 0.03]} color={C.fabricLite} rough={1} />
            <Box a={[0.5, 0.22, 0.82]} p={[0, 0.45, 0.03]} color={C.fabricLite} rough={1} />
            <Box a={[0.5, 0.22, 0.82]} p={[0.55, 0.45, 0.03]} color={C.fabricLite} rough={1} />
            {/* back frame + 3 back cushions (slight recline) */}
            <Box a={[2.1, 0.62, 0.16]} p={[0, 0.49, -0.4]} color={C.fabricDark} rough={1} />
            <Box a={[0.52, 0.36, 0.16]} p={[-0.55, 0.62, -0.3]} rot={[-0.09, 0, 0]} color={C.fabric} rough={1} />
            <Box a={[0.52, 0.36, 0.16]} p={[0, 0.62, -0.3]} rot={[-0.09, 0, 0]} color={C.fabric} rough={1} />
            <Box a={[0.52, 0.36, 0.16]} p={[0.55, 0.62, -0.3]} rot={[-0.09, 0, 0]} color={C.fabric} rough={1} />
            {/* padded arms + rolled tops */}
            <Box a={[0.2, 0.5, 0.92]} p={[-0.95, 0.39, 0]} color={C.fabricDark} rough={1} />
            <Box a={[0.2, 0.5, 0.92]} p={[0.95, 0.39, 0]} color={C.fabricDark} rough={1} />
            <Cyl r={0.1} h={0.92} p={[-0.95, 0.62, 0]} rot={[Math.PI / 2, 0, 0]} color={C.fabric} rough={1} />
            <Cyl r={0.1} h={0.92} p={[0.95, 0.62, 0]} rot={[Math.PI / 2, 0, 0]} color={C.fabric} rough={1} />
            {/* throw pillows */}
            <Box a={[0.4, 0.4, 0.14]} p={[-0.58, 0.58, -0.04]} rot={[-0.2, 0.25, 0.22]} color={C.accent} rough={1} />
            <Box a={[0.4, 0.4, 0.14]} p={[0.56, 0.58, -0.04]} rot={[-0.2, -0.25, -0.22]} color={C.pillow} rough={1} />
        </group>
    );
}

// ~1.0 x 0.45h x 0.55 — wood top + lower shelf + 4 legs.
export function CoffeeTable() {
    return (
        <group>
            {/* legs */}
            <Box a={[0.07, 0.42, 0.07]} p={[-0.44, 0.21, -0.22]} color={C.woodDark} rough={0.6} />
            <Box a={[0.07, 0.42, 0.07]} p={[0.44, 0.21, -0.22]} color={C.woodDark} rough={0.6} />
            <Box a={[0.07, 0.42, 0.07]} p={[-0.44, 0.21, 0.22]} color={C.woodDark} rough={0.6} />
            <Box a={[0.07, 0.42, 0.07]} p={[0.44, 0.21, 0.22]} color={C.woodDark} rough={0.6} />
            {/* side aprons tying legs together */}
            <Box a={[0.05, 0.06, 0.42]} p={[-0.44, 0.36, 0]} color={C.woodDark} rough={0.6} />
            <Box a={[0.05, 0.06, 0.42]} p={[0.44, 0.36, 0]} color={C.woodDark} rough={0.6} />
            {/* lower shelf */}
            <Box a={[0.86, 0.04, 0.46]} p={[0, 0.13, 0]} color={C.wood} rough={0.55} />
            {/* top */}
            <Box a={[1.0, 0.06, 0.55]} p={[0, 0.42, 0]} color={C.wood} rough={0.5} />
        </group>
    );
}

// ~1.7w low cabinet w/ drawers + wall-mounted flat TV + slim soundbar.
export function TvUnit() {
    return (
        <group>
            {/* feet */}
            <Box a={[0.08, 0.06, 0.08]} p={[-0.78, 0.03, 0.15]} color={C.woodDark} rough={0.6} />
            <Box a={[0.08, 0.06, 0.08]} p={[0.78, 0.03, 0.15]} color={C.woodDark} rough={0.6} />
            <Box a={[0.08, 0.06, 0.08]} p={[-0.78, 0.03, -0.15]} color={C.woodDark} rough={0.6} />
            <Box a={[0.08, 0.06, 0.08]} p={[0.78, 0.03, -0.15]} color={C.woodDark} rough={0.6} />
            {/* cabinet body + top trim */}
            <Box a={[1.7, 0.34, 0.4]} p={[0, 0.23, 0]} color={C.wood} rough={0.6} />
            <Box a={[1.74, 0.03, 0.44]} p={[0, 0.415, 0]} color={C.woodDark} rough={0.55} />
            {/* 3 drawer fronts + knobs */}
            <Box a={[0.52, 0.24, 0.02]} p={[-0.56, 0.23, 0.205]} color={C.woodDark} rough={0.55} />
            <Box a={[0.52, 0.24, 0.02]} p={[0, 0.23, 0.205]} color={C.woodDark} rough={0.55} />
            <Box a={[0.52, 0.24, 0.02]} p={[0.56, 0.23, 0.205]} color={C.woodDark} rough={0.55} />
            <mesh position={[-0.56, 0.23, 0.225]} castShadow>
                <sphereGeometry args={[0.022, 16, 16]} />
                <meshStandardMaterial color={C.metal} metalness={0.8} roughness={0.3} envMapIntensity={0.85} />
            </mesh>
            <mesh position={[0, 0.23, 0.225]} castShadow>
                <sphereGeometry args={[0.022, 16, 16]} />
                <meshStandardMaterial color={C.metal} metalness={0.8} roughness={0.3} envMapIntensity={0.85} />
            </mesh>
            <mesh position={[0.56, 0.23, 0.225]} castShadow>
                <sphereGeometry args={[0.022, 16, 16]} />
                <meshStandardMaterial color={C.metal} metalness={0.8} roughness={0.3} envMapIntensity={0.85} />
            </mesh>
            {/* wall mount bracket */}
            <Box a={[0.1, 0.22, 0.04]} p={[0, 1.18, -0.19]} color={C.metalDark} metal={0.6} rough={0.4} />
            {/* TV bezel + emissive screen (faces +Z) */}
            <Box a={[1.3, 0.8, 0.05]} p={[0, 1.18, -0.16]} color={C.screenBody} rough={0.4} metal={0.3} />
            <mesh position={[0, 1.18, -0.13]} castShadow>
                <boxGeometry args={[1.22, 0.72, 0.005]} />
                <meshStandardMaterial
                    color={C.screenBody}
                    emissive={C.screenEmiss}
                    emissiveIntensity={0.4}
                    roughness={0.25}
                    metalness={0.1}
                    envMapIntensity={0.85}
                />
            </mesh>
            {/* slim soundbar above the cabinet */}
            <Box a={[1.05, 0.08, 0.09]} p={[0, 0.66, -0.12]} color={C.soundbar} rough={0.5} metal={0.2} />
        </group>
    );
}

// flat 2.3 x 0.02 x 1.7 with a slightly raised inner field + accent stripes.
export function Rug() {
    return (
        <group>
            <Box a={[2.3, 0.02, 1.7]} p={[0, 0.01, 0]} color={C.rugBorder} rough={1} />
            <Box a={[2.06, 0.026, 1.46]} p={[0, 0.013, 0]} color={C.rugField} rough={1} />
            <Box a={[1.9, 0.028, 0.12]} p={[0, 0.015, 0.45]} color={C.rugStripe} rough={1} />
            <Box a={[1.9, 0.028, 0.12]} p={[0, 0.015, -0.45]} color={C.rugStripe} rough={1} />
        </group>
    );
}

// ceramic pot + trunk + layered foliage clusters in varied greens.
export function Plant() {
    return (
        <group>
            {/* tapered ceramic pot */}
            <mesh position={[0, 0.18, 0]} castShadow receiveShadow>
                <cylinderGeometry args={[0.22, 0.16, 0.36, 24]} />
                <meshStandardMaterial color={C.ceramic} roughness={0.4} metalness={0.05} envMapIntensity={0.85} />
            </mesh>
            {/* rim */}
            <mesh position={[0, 0.355, 0]} castShadow>
                <cylinderGeometry args={[0.235, 0.235, 0.04, 24]} />
                <meshStandardMaterial color={C.rim} roughness={0.4} metalness={0.05} envMapIntensity={0.85} />
            </mesh>
            {/* soil */}
            <mesh position={[0, 0.35, 0]} receiveShadow>
                <cylinderGeometry args={[0.2, 0.2, 0.05, 20]} />
                <meshStandardMaterial color={C.soil} roughness={1} envMapIntensity={0.85} />
            </mesh>
            {/* trunk */}
            <Cyl r={0.035} h={0.5} p={[0, 0.6, 0]} color={C.trunk} rough={0.9} />
            {/* layered foliage */}
            <mesh position={[0, 1.18, 0]} castShadow>
                <icosahedronGeometry args={[0.3, 1]} />
                <meshStandardMaterial color={C.leaf1} roughness={1} flatShading envMapIntensity={0.85} />
            </mesh>
            <mesh position={[-0.22, 0.98, 0.1]} castShadow>
                <icosahedronGeometry args={[0.22, 1]} />
                <meshStandardMaterial color={C.leaf2} roughness={1} flatShading envMapIntensity={0.85} />
            </mesh>
            <mesh position={[0.24, 1.0, -0.08]} castShadow>
                <icosahedronGeometry args={[0.24, 1]} />
                <meshStandardMaterial color={C.leaf3} roughness={1} flatShading envMapIntensity={0.85} />
            </mesh>
            <mesh position={[0.06, 1.35, 0.04]} castShadow>
                <icosahedronGeometry args={[0.2, 1]} />
                <meshStandardMaterial color={C.leaf4} roughness={1} flatShading envMapIntensity={0.85} />
            </mesh>
            <mesh position={[-0.12, 1.42, -0.1]} castShadow>
                <coneGeometry args={[0.16, 0.34, 12]} />
                <meshStandardMaterial color={C.leaf3} roughness={1} flatShading envMapIntensity={0.85} />
            </mesh>
            <mesh position={[0.18, 1.28, 0.18]} castShadow>
                <coneGeometry args={[0.14, 0.3, 12]} />
                <meshStandardMaterial color={C.leaf1} roughness={1} flatShading envMapIntensity={0.85} />
            </mesh>
        </group>
    );
}
