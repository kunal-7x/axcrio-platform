/**
 * GenerationLoader — "Signal Aurora" WebGL fragment-shader field (no npm dep).
 *
 * A single full-quad fragment shader renders a living, brand-tinted aurora:
 * domain-warped fractal simplex-ish noise advected over time, mapped to a tight
 * 3-stop palette anchored on Signal blue, with a soft central bloom, a slow
 * conic shimmer sweep, and a film-grain dither that kills colour banding.
 *
 * ONE draw call per frame — all work on the user's GPU, nothing per-pixel on the
 * CPU. Token-pure: the three palette stops + bloom are passed IN as uniforms
 * (resolved from CSS vars by index.tsx), never literals here.
 *
 * Public surface:
 *   createAurora(canvas)  -> AuroraHandle | null   (null = no WebGL; caller degrades)
 *   handle.setColors(a,b,c)                          (each [r,g,b] in 0..1)
 *   handle.render(timeSec, intensity, bloom, dpr)    (drive from the RAF loop)
 *   handle.resize(cssW, cssH, dpr)
 *   handle.sampleLuma(nx, ny, timeSec, intensity)    (CPU mirror -> couples sparks)
 *   handle.dispose()
 *
 * The CPU `sampleLuma` is a cheap analytic mirror of the shader's brightness so
 * the spark layer can shimmer *with* the flow without reading pixels back off the
 * GPU (which would stall the pipeline).
 */

export type RGB01 = [number, number, number];

export type AuroraHandle = {
    setColors: (a: RGB01, b: RGB01, c: RGB01) => void;
    render: (timeSec: number, intensity: number, bloom: number, dpr: number) => void;
    resize: (cssW: number, cssH: number, dpr: number) => void;
    /** Analytic luminance mirror at normalised coords (-1..1), for spark coupling. */
    sampleLuma: (nx: number, ny: number, timeSec: number, intensity: number) => number;
    dispose: () => void;
};

const VERT = `
attribute vec2 aPos;
varying vec2 vUv;
void main() {
    vUv = aPos * 0.5 + 0.5;
    gl_Position = vec4(aPos, 0.0, 1.0);
}`;

/**
 * Fragment shader. Domain-warped FBM over value-noise, mapped to a 3-stop palette,
 * radial bloom toward centre, conic shimmer sweep, vignette, and a hash grain.
 */
const FRAG = `
precision highp float;

varying vec2 vUv;
uniform vec2  uRes;       // pixel resolution (for aspect + grain)
uniform float uTime;
uniform float uIntensity; // 0..1 -> speed + saturation + warp depth
uniform float uBloom;     // 0..1 -> central bloom strength
uniform vec3  uColorA;    // deep base (indigo-black)
uniform vec3  uColorB;    // signal blue
uniform vec3  uColorC;    // cool white highlight

// ---- hash / value noise (cheap, GPU-friendly) ----
float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float vnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f); // smoothstep
    float a = hash(i + vec2(0.0, 0.0));
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// fractal brownian motion (4 octaves)
float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.55;
    mat2 rot = mat2(0.80, 0.60, -0.60, 0.80);
    for (int i = 0; i < 4; i++) {
        v += amp * vnoise(p);
        p = rot * p * 2.02 + 11.7;
        amp *= 0.5;
    }
    return v;
}

void main() {
    // aspect-correct centred coords (-1..1 on the short axis)
    vec2 uv = vUv;
    vec2 p = (uv - 0.5);
    float aspect = uRes.x / max(uRes.y, 1.0);
    p.x *= aspect;

    float t = uTime * (0.06 + 0.10 * uIntensity); // slow advection, faster when active
    float warpAmt = 0.55 + 0.45 * uIntensity;

    // domain warp: two fbm fields offset the sample point -> organic flow
    vec2 q = vec2(
        fbm(p * 1.8 + vec2(0.0, t)),
        fbm(p * 1.8 + vec2(5.2, -t) + 1.7)
    );
    vec2 r = vec2(
        fbm(p * 1.8 + warpAmt * q + vec2(1.7 - t * 0.5, 9.2)),
        fbm(p * 1.8 + warpAmt * q + vec2(8.3, 2.8 + t * 0.5))
    );
    float n = fbm(p * 1.8 + warpAmt * r);

    // shape the field: lift contrast, bias toward darker base so blue reads as "energy"
    float field = smoothstep(0.18, 0.92, n);
    field = pow(field, 1.25);

    // central radial falloff -> energy concentrates in the middle (the "engine")
    float dist = length(p);
    float core = smoothstep(1.05, 0.0, dist);

    // ---- palette: base -> signal blue -> cool white highlight ----
    float fb = field * (0.55 + 0.55 * core);
    fb = clamp(fb, 0.0, 1.0);
    vec3 col = mix(uColorA, uColorB, smoothstep(0.0, 0.62, fb));
    col = mix(col, uColorC, smoothstep(0.66, 1.0, fb) * (0.55 + 0.45 * uIntensity));

    // central bloom: additive soft glow toward centre, brighter when intensity high
    float bloom = uBloom * core * core * (0.45 + 0.55 * uIntensity);
    col += uColorB * bloom * 0.6;
    col += uColorC * bloom * 0.25;

    // slow conic shimmer sweep (a scanning highlight pass ~ every 7s)
    float ang = atan(p.y, p.x);
    float sweep = ang / 6.2831853 + 0.5;          // 0..1 around the circle
    float sweepPos = fract(uTime * 0.14);          // rotating
    float sweepBand = smoothstep(0.06, 0.0, abs(fract(sweep - sweepPos + 0.5) - 0.5));
    col += uColorC * sweepBand * 0.10 * (0.4 + 0.6 * uIntensity) * core;

    // saturate a touch toward blue when active (keeps it brand, not grey)
    float lum = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(lum), col, 1.0 + 0.25 * uIntensity);

    // vignette so the field melts into the dark card inset
    float vig = smoothstep(1.25, 0.25, dist);
    col *= 0.16 + 0.84 * vig;

    // film grain: 2-3% animated dither -> no banding, premium texture
    float g = hash(uv * uRes + uTime * 60.0);
    col += (g - 0.5) * 0.035;

    gl_FragColor = vec4(max(col, 0.0), 1.0);
}`;

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader | null {
    const sh = gl.createShader(type);
    if (!sh) return null;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        gl.deleteShader(sh);
        return null;
    }
    return sh;
}

export function createAurora(canvas: HTMLCanvasElement): AuroraHandle | null {
    let gl: WebGLRenderingContext | null = null;
    try {
        gl =
            (canvas.getContext("webgl", {
                alpha: false,
                antialias: false,
                depth: false,
                stencil: false,
                premultipliedAlpha: false,
                powerPreference: "low-power",
                preserveDrawingBuffer: false,
            }) as WebGLRenderingContext | null) ||
            (canvas.getContext("experimental-webgl") as WebGLRenderingContext | null);
    } catch {
        return null;
    }
    if (!gl) return null;

    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return null;

    const prog = gl.createProgram();
    if (!prog) return null;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        gl.deleteProgram(prog);
        return null;
    }
    gl.useProgram(prog);

    // full-screen quad (two triangles)
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([-1, -1, 3, -1, -1, 3]), // single oversized tri covers the quad
        gl.STATIC_DRAW
    );
    const aPos = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    const uRes = gl.getUniformLocation(prog, "uRes");
    const uTime = gl.getUniformLocation(prog, "uTime");
    const uIntensity = gl.getUniformLocation(prog, "uIntensity");
    const uBloom = gl.getUniformLocation(prog, "uBloom");
    const uColorA = gl.getUniformLocation(prog, "uColorA");
    const uColorB = gl.getUniformLocation(prog, "uColorB");
    const uColorC = gl.getUniformLocation(prog, "uColorC");

    let colA: RGB01 = [0.04, 0.05, 0.09];
    let colB: RGB01 = [0.165, 0.522, 1.0]; // #2a85ff
    let colC: RGB01 = [0.82, 0.9, 1.0];

    // smoothed uniforms so phase changes ease instead of snapping
    let curIntensity = 0.3;
    let curBloom = 0.4;

    let lost = false;
    const onLost = (e: Event) => {
        e.preventDefault();
        lost = true;
    };
    canvas.addEventListener("webglcontextlost", onLost, false);

    function resize(cssW: number, cssH: number, dpr: number) {
        if (!gl) return;
        const w = Math.max(1, Math.floor(cssW * dpr));
        const h = Math.max(1, Math.floor(cssH * dpr));
        if (canvas.width !== w) canvas.width = w;
        if (canvas.height !== h) canvas.height = h;
        gl.viewport(0, 0, w, h);
    }

    function render(timeSec: number, intensity: number, bloom: number, _dpr: number) {
        if (!gl || lost) return;
        // ease toward the target so phase escalation is fluid
        curIntensity += (intensity - curIntensity) * 0.06;
        curBloom += (bloom - curBloom) * 0.06;

        gl.useProgram(prog);
        gl.uniform2f(uRes, canvas.width, canvas.height);
        gl.uniform1f(uTime, timeSec);
        gl.uniform1f(uIntensity, curIntensity);
        gl.uniform1f(uBloom, curBloom);
        gl.uniform3f(uColorA, colA[0], colA[1], colA[2]);
        gl.uniform3f(uColorB, colB[0], colB[1], colB[2]);
        gl.uniform3f(uColorC, colC[0], colC[1], colC[2]);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    // ---- CPU analytic mirror of the shader brightness (no GPU readback) ----
    // A 2-octave value-noise FBM that tracks the field's coarse structure so
    // sparks brighten where the aurora is bright. Cheap; called per-spark.
    const h2 = (x: number, y: number) => {
        let px = (x * 123.34) % 1;
        let py = (y * 456.21) % 1;
        if (px < 0) px += 1;
        if (py < 0) py += 1;
        const d = px * (px + 45.32) + py * (py + 45.32);
        px = (px + d) % 1;
        py = (py + d) % 1;
        return ((px * py) % 1 + 1) % 1;
    };
    const vn = (x: number, y: number) => {
        const ix = Math.floor(x);
        const iy = Math.floor(y);
        const fx = x - ix;
        const fy = y - iy;
        const ux = fx * fx * (3 - 2 * fx);
        const uy = fy * fy * (3 - 2 * fy);
        const a = h2(ix, iy);
        const b = h2(ix + 1, iy);
        const c = h2(ix, iy + 1);
        const d = h2(ix + 1, iy + 1);
        return (a + (b - a) * ux) * (1 - uy) + (c + (d - c) * ux) * uy;
    };

    function sampleLuma(nx: number, ny: number, timeSec: number, intensity: number): number {
        const t = timeSec * (0.06 + 0.1 * intensity);
        // mirror the domain warp coarsely (1 warp pass, 2 octaves)
        const qx = vn(nx * 1.8, ny * 1.8 + t);
        const qy = vn(nx * 1.8 + 5.2, ny * 1.8 - t + 1.7);
        const wx = nx * 1.8 + (0.55 + 0.45 * intensity) * qx;
        const wy = ny * 1.8 + (0.55 + 0.45 * intensity) * qy;
        let v = 0.6 * vn(wx, wy) + 0.4 * vn(wx * 2.02 + 11.7, wy * 2.02 + 11.7);
        v = Math.min(1, Math.max(0, (v - 0.18) / 0.74));
        const dist = Math.hypot(nx, ny);
        const core = Math.max(0, Math.min(1, 1 - dist / 1.05));
        return Math.min(1, v * (0.55 + 0.55 * core));
    }

    function setColors(a: RGB01, b: RGB01, c: RGB01) {
        colA = a;
        colB = b;
        colC = c;
    }

    function dispose() {
        canvas.removeEventListener("webglcontextlost", onLost, false);
        if (!gl) return;
        try {
            gl.deleteBuffer(buf);
            gl.deleteProgram(prog);
            gl.deleteShader(vs as WebGLShader);
            gl.deleteShader(fs as WebGLShader);
            const ext = gl.getExtension("WEBGL_lose_context");
            ext?.loseContext();
        } catch {
            /* best-effort cleanup */
        }
    }

    return { setColors, render, resize, sampleLuma, dispose };
}
