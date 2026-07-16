"use client";
// Procedural PBR textures generated IN-CODE (canvas) — zero external assets / CDN, so
// it stays self-hosted-safe. Wood + tile floors get a colour map AND a normal map
// (surface relief), walls get a subtle plaster normal. Lazily generated once and
// cached (only touches `document` in the browser, at first use).
import * as THREE from "three";

function mkCanvas(size: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
    const c = document.createElement("canvas");
    c.width = c.height = size;
    return [c, c.getContext("2d")!];
}

// value-noise heightmap (tileable-ish) → Float32 0..1
function valueNoise(size: number, cells: number, seed = 1): Float32Array {
    const g = new Float32Array(cells * cells);
    let s = seed * 9301 + 49297;
    const rnd = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
    for (let i = 0; i < g.length; i++) g[i] = rnd();
    const out = new Float32Array(size * size);
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const fx = (x / size) * cells;
            const fy = (y / size) * cells;
            const x0 = Math.floor(fx) % cells;
            const y0 = Math.floor(fy) % cells;
            const x1 = (x0 + 1) % cells;
            const y1 = (y0 + 1) % cells;
            const tx = fx - Math.floor(fx);
            const ty = fy - Math.floor(fy);
            const a = g[y0 * cells + x0];
            const b = g[y0 * cells + x1];
            const c = g[y1 * cells + x0];
            const d = g[y1 * cells + x1];
            const sx = tx * tx * (3 - 2 * tx);
            const sy = ty * ty * (3 - 2 * ty);
            out[y * size + x] = a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
        }
    }
    return out;
}

// heightmap → normal map texture (Sobel)
function heightToNormal(height: Float32Array, size: number, strength: number): THREE.DataTexture {
    const data = new Uint8Array(size * size * 4);
    const at = (x: number, y: number) => height[((y + size) % size) * size + ((x + size) % size)];
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const dx = (at(x - 1, y) - at(x + 1, y)) * strength;
            const dy = (at(x, y - 1) - at(x, y + 1)) * strength;
            const nx = dx;
            const ny = dy;
            const nz = 1;
            const len = Math.hypot(nx, ny, nz);
            const i = (y * size + x) * 4;
            data[i] = ((nx / len) * 0.5 + 0.5) * 255;
            data[i + 1] = ((ny / len) * 0.5 + 0.5) * 255;
            data[i + 2] = ((nz / len) * 0.5 + 0.5) * 255;
            data[i + 3] = 255;
        }
    }
    const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.needsUpdate = true;
    return tex;
}

function colorTexture(cv: HTMLCanvasElement): THREE.CanvasTexture {
    const t = new THREE.CanvasTexture(cv);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 8;
    return t;
}

// ---------------- wood ----------------
function buildWood(base: string) {
    const size = 512;
    const [cv, ctx] = mkCanvas(size);
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, size, size);
    const planks = 5;
    const ph = size / planks;
    const height = new Float32Array(size * size).fill(0.6);
    for (let p = 0; p < planks; p++) {
        const y = p * ph;
        const tone = 0.86 + ((p * 53) % 30) / 100; // per-plank tone
        ctx.fillStyle = `rgba(0,0,0,${(1 - tone) * 0.35})`;
        ctx.fillRect(0, y, size, ph);
        // plank seam (recessed dark line)
        ctx.fillStyle = "rgba(40,24,10,0.55)";
        ctx.fillRect(0, y, size, 2);
        for (let x = 0; x < size; x++) height[Math.floor(y) * size + x] = 0.1;
        // grain — wavy thin darker strokes along the plank
        for (let g = 0; g < 22; g++) {
            const gy = y + 6 + Math.random() * (ph - 10);
            ctx.strokeStyle = `rgba(60,38,18,${0.04 + Math.random() * 0.08})`;
            ctx.lineWidth = 0.6 + Math.random();
            ctx.beginPath();
            ctx.moveTo(0, gy);
            for (let x = 0; x <= size; x += 32) ctx.lineTo(x, gy + Math.sin(x * 0.02 + g) * 1.6);
            ctx.stroke();
        }
    }
    // subtle grain height
    const n = valueNoise(size, 64, 7);
    for (let i = 0; i < height.length; i++) height[i] = height[i] * 0.5 + n[i] * 0.5;
    return { map: colorTexture(cv), normalMap: heightToNormal(height, size, 2.0) };
}

// ---------------- tile ----------------
function buildTile(base: string, grout: string) {
    const size = 512;
    const [cv, ctx] = mkCanvas(size);
    ctx.fillStyle = grout;
    ctx.fillRect(0, 0, size, size);
    const n = 3;
    const gap = size * 0.02;
    const ts = (size - gap * (n + 1)) / n;
    const height = new Float32Array(size * size).fill(0.2); // grout low
    for (let r = 0; r < n; r++)
        for (let c = 0; c < n; c++) {
            const x = gap + c * (ts + gap);
            const y = gap + r * (ts + gap);
            const tone = 0.94 + Math.random() * 0.1;
            ctx.fillStyle = base;
            ctx.globalAlpha = tone;
            ctx.fillRect(x, y, ts, ts);
            ctx.globalAlpha = 1;
            for (let yy = Math.floor(y); yy < y + ts; yy++)
                for (let xx = Math.floor(x); xx < x + ts; xx++) height[yy * size + xx] = 0.85;
        }
    // faint speckle
    const sp = valueNoise(size, 128, 3);
    const id = ctx.getImageData(0, 0, size, size);
    for (let i = 0; i < sp.length; i++) {
        const v = (sp[i] - 0.5) * 14;
        id.data[i * 4] += v;
        id.data[i * 4 + 1] += v;
        id.data[i * 4 + 2] += v;
    }
    ctx.putImageData(id, 0, 0);
    return { map: colorTexture(cv), normalMap: heightToNormal(height, size, 3.5) };
}

// ---------------- plaster wall normal ----------------
let _plaster: THREE.DataTexture | null = null;
export function plasterNormal(): THREE.DataTexture {
    if (_plaster) return _plaster;
    const size = 256;
    const n = valueNoise(size, 90, 11);
    _plaster = heightToNormal(n, size, 0.5);
    _plaster.repeat.set(3, 2);
    return _plaster;
}

const _floorCache: Record<string, { map: THREE.Texture; normalMap: THREE.Texture }> = {};
export function floorTextures(material: string): { map: THREE.Texture; normalMap: THREE.Texture } | null {
    if (_floorCache[material]) return _floorCache[material];
    let t: { map: THREE.Texture; normalMap: THREE.Texture } | null = null;
    if (material === "wood" || material === "carpet") t = buildWood(material === "carpet" ? "#b3ada3" : "#a9743f");
    else if (material === "tile" || material === "stone") t = buildTile(material === "stone" ? "#c4c8d2" : "#dadfe7", "#a7adb8");
    else if (material === "deck") t = buildWood("#946b42");
    if (t) {
        // floor UVs are in world metres → tile the texture every ~1.4 m
        const rep = 0.7;
        t.map.repeat.set(rep, rep);
        t.normalMap.repeat.set(rep, rep);
        _floorCache[material] = t;
    }
    return t;
}
