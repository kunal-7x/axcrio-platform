"use client";

// ============================================================
// Globe — a premium, self-contained three.js WebGL globe for the Control Overview (#26).
//
// Renders a dark graticule sphere + atmosphere fresnel glow, then plots REAL recent-call activity
// as glowing city markers (sized by call weight) with animated arcs flowing from the busiest hub.
// Auto-rotates, drag-to-spin, retina-aware, fully cleaned up on unmount. No texture assets needed
// (graticule + procedural glow sprites), so it ships with zero new files. Degrades gracefully: with
// no points it still renders the spinning globe (an honest "awaiting geo signal" state).
//
// Uses `three` (already a dependency). All THREE objects are created inside the effect so nothing
// touches the server render; the outer component is a plain client wrapper.
// ============================================================

import { useEffect, useRef } from "react";
import * as THREE from "three";

export type GlobePoint = { city: string; lat: number; lng: number; calls: number; weight: number };
type Props = {
    points: GlobePoint[];
    hub?: { lat: number; lng: number; label: string };
    className?: string;
    /** brand accent (city markers + arcs). Defaults to Haptica blue. */
    accent?: string;
    /** secondary accent (atmosphere + graticule). */
    glow?: string;
};

const R = 1; // globe radius (world units)

// lat/lng (degrees) -> point on a sphere of radius `r`. Standard equirectangular mapping; +lng east.
function llToVec3(lat: number, lng: number, r: number): THREE.Vector3 {
    const phi = (90 - lat) * (Math.PI / 180);
    const theta = (lng + 180) * (Math.PI / 180);
    return new THREE.Vector3(
        -r * Math.sin(phi) * Math.cos(theta),
        r * Math.cos(phi),
        r * Math.sin(phi) * Math.sin(theta),
    );
}

// A soft round radial-gradient sprite texture (procedural — no asset). Used for the city glows + comets.
function makeGlowTexture(): THREE.Texture {
    const s = 64;
    const c = document.createElement("canvas");
    c.width = c.height = s;
    const g = c.getContext("2d")!;
    const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
    grad.addColorStop(0, "rgba(255,255,255,1)");
    grad.addColorStop(0.25, "rgba(255,255,255,0.85)");
    grad.addColorStop(0.55, "rgba(255,255,255,0.25)");
    grad.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, s, s);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
}

// Lat/long graticule as a single LineSegments — the "wireframe earth" without a texture.
function makeGraticule(color: THREE.Color): THREE.LineSegments {
    const pts: number[] = [];
    const seg = 90;
    // parallels (lines of latitude)
    for (let lat = -60; lat <= 60; lat += 30) {
        for (let i = 0; i < seg; i++) {
            const a = (i / seg) * Math.PI * 2;
            const b = ((i + 1) / seg) * Math.PI * 2;
            const r = Math.cos((lat * Math.PI) / 180) * R;
            const y = Math.sin((lat * Math.PI) / 180) * R;
            pts.push(r * Math.cos(a), y, r * Math.sin(a), r * Math.cos(b), y, r * Math.sin(b));
        }
    }
    // meridians (lines of longitude)
    for (let lng = 0; lng < 360; lng += 30) {
        for (let i = 0; i < seg; i++) {
            const a = (i / seg) * Math.PI - Math.PI / 2;
            const b = ((i + 1) / seg) * Math.PI - Math.PI / 2;
            const t = (lng * Math.PI) / 180;
            const p1 = new THREE.Vector3(Math.cos(a) * Math.cos(t), Math.sin(a), Math.cos(a) * Math.sin(t)).multiplyScalar(R);
            const p2 = new THREE.Vector3(Math.cos(b) * Math.cos(t), Math.sin(b), Math.cos(b) * Math.sin(t)).multiplyScalar(R);
            pts.push(p1.x, p1.y, p1.z, p2.x, p2.y, p2.z);
        }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
    const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.22 });
    return new THREE.LineSegments(geo, mat);
}

export default function Globe({ points, hub, className, accent = "#5C5CFF", glow = "#0EA5E9" }: Props) {
    const mountRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        const mount = mountRef.current;
        if (!mount) return;

        const accentC = new THREE.Color(accent);
        const glowC = new THREE.Color(glow);
        let width = mount.clientWidth || 360;
        let height = mount.clientHeight || 360;

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 100);
        camera.position.set(0, 0.25, 3.2);

        const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.setSize(width, height);
        renderer.setClearColor(0x000000, 0);
        mount.appendChild(renderer.domElement);
        renderer.domElement.style.cursor = "grab";
        renderer.domElement.style.touchAction = "pan-y";

        // rotating group holds everything that should spin with the globe
        const group = new THREE.Group();
        scene.add(group);

        // base sphere — dark, faintly emissive so the planet reads as a body, not a hole
        const base = new THREE.Mesh(
            new THREE.SphereGeometry(R * 0.997, 64, 64),
            new THREE.MeshPhongMaterial({ color: 0x0b1020, emissive: new THREE.Color(glowC).multiplyScalar(0.05), shininess: 8, transparent: true, opacity: 0.92 }),
        );
        group.add(base);
        group.add(makeGraticule(glowC));

        // atmosphere — backside fresnel glow shell
        const atmo = new THREE.Mesh(
            new THREE.SphereGeometry(R * 1.18, 64, 64),
            new THREE.ShaderMaterial({
                transparent: true,
                blending: THREE.AdditiveBlending,
                side: THREE.BackSide,
                depthWrite: false,
                uniforms: { uColor: { value: glowC } },
                vertexShader: `varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
                fragmentShader: `varying vec3 vN; uniform vec3 uColor; void main(){ float i = pow(0.72 - dot(vN, vec3(0.0,0.0,1.0)), 3.0); gl_FragColor = vec4(uColor, clamp(i,0.0,1.0) * 0.9); }`,
            }),
        );
        scene.add(atmo);

        // lighting
        const key = new THREE.DirectionalLight(0xffffff, 1.1);
        key.position.set(2, 1.5, 2.5);
        scene.add(key);
        scene.add(new THREE.AmbientLight(0x4060ff, 0.35));

        const glowTex = makeGlowTexture();
        const disposables: { dispose: () => void }[] = [glowTex];

        // city markers (glow sprite + solid pin), sized by weight
        for (const p of points) {
            const pos = llToVec3(p.lat, p.lng, R * 1.01);
            const w = Math.max(0.12, Math.min(1, p.weight || 0.2));
            const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: accentC, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.95 }));
            const sc = 0.07 + w * 0.16;
            sprite.scale.set(sc, sc, sc);
            sprite.position.copy(pos);
            group.add(sprite);
            const pin = new THREE.Mesh(
                new THREE.SphereGeometry(0.012 + w * 0.018, 12, 12),
                new THREE.MeshBasicMaterial({ color: accentC }),
            );
            pin.position.copy(pos);
            group.add(pin);
        }

        // arcs from the hub to each city — quadratic bezier lifted off the surface; animated comets
        const comets: { sprite: THREE.Sprite; curve: THREE.QuadraticBezierCurve3; t: number; speed: number }[] = [];
        if (hub && points.length) {
            const hubPos = llToVec3(hub.lat, hub.lng, R * 1.01);
            for (const p of points.slice(0, 14)) {
                const dst = llToVec3(p.lat, p.lng, R * 1.01);
                if (dst.distanceTo(hubPos) < 1e-3) continue;
                const mid = hubPos.clone().add(dst).multiplyScalar(0.5);
                const lift = 1 + 0.28 + hubPos.distanceTo(dst) * 0.25;
                mid.normalize().multiplyScalar(R * lift);
                const curve = new THREE.QuadraticBezierCurve3(hubPos, mid, dst);
                const geo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(48));
                const mat = new THREE.LineBasicMaterial({ color: accentC, transparent: true, opacity: 0.18 + 0.32 * (p.weight || 0.2) });
                group.add(new THREE.Line(geo, mat));
                const comet = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: accentC, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
                comet.scale.setScalar(0.05);
                group.add(comet);
                comets.push({ sprite: comet, curve, t: Math.random(), speed: 0.12 + 0.18 * (p.weight || 0.2) });
            }
        }

        // orient so India (~78°E, 22°N) faces the camera at rest
        const hub0 = hub ?? { lat: 22.5, lng: 78.9 };
        group.rotation.y = -((hub0.lng + 180) * (Math.PI / 180)) + Math.PI;
        group.rotation.x = 0.18;

        // drag-to-spin
        let dragging = false;
        let lastX = 0;
        let lastY = 0;
        let velY = 0;
        const onDown = (e: PointerEvent) => { dragging = true; lastX = e.clientX; lastY = e.clientY; renderer.domElement.style.cursor = "grabbing"; };
        const onMove = (e: PointerEvent) => {
            if (!dragging) return;
            const dx = e.clientX - lastX;
            const dy = e.clientY - lastY;
            lastX = e.clientX; lastY = e.clientY;
            group.rotation.y += dx * 0.005;
            group.rotation.x = Math.max(-0.7, Math.min(0.7, group.rotation.x + dy * 0.005));
            velY = dx * 0.005;
        };
        const onUp = () => { dragging = false; renderer.domElement.style.cursor = "grab"; };
        renderer.domElement.addEventListener("pointerdown", onDown);
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);

        const clock = new THREE.Clock();
        let raf = 0;
        const tick = () => {
            const dt = clock.getDelta();
            if (!dragging) {
                velY *= 0.95;
                group.rotation.y += 0.06 * dt + velY;
            }
            for (const c of comets) {
                c.t = (c.t + c.speed * dt) % 1;
                c.sprite.position.copy(c.curve.getPoint(c.t));
                const fade = Math.sin(c.t * Math.PI);
                (c.sprite.material as THREE.SpriteMaterial).opacity = 0.2 + 0.8 * fade;
            }
            renderer.render(scene, camera);
            raf = requestAnimationFrame(tick);
        };
        tick();

        const onResize = () => {
            if (!mount) return;
            width = mount.clientWidth || width;
            height = mount.clientHeight || height;
            camera.aspect = width / height;
            camera.updateProjectionMatrix();
            renderer.setSize(width, height);
        };
        const ro = new ResizeObserver(onResize);
        ro.observe(mount);

        return () => {
            cancelAnimationFrame(raf);
            ro.disconnect();
            renderer.domElement.removeEventListener("pointerdown", onDown);
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onUp);
            scene.traverse((o) => {
                const m = o as THREE.Mesh;
                if (m.geometry) m.geometry.dispose();
                const mat = (m as THREE.Mesh).material;
                if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
                else if (mat) (mat as THREE.Material).dispose();
            });
            for (const d of disposables) d.dispose();
            renderer.dispose();
            if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
        };
    }, [points, hub, accent, glow]);

    return <div ref={mountRef} className={className} />;
}
