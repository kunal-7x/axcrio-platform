"use client";
// Zustand store for the Property Studio (Brainwave shell). Centralizes UI state +
// every pmodel call, so the rails / dock / canvas talk without prop-drilling.
import { create } from "zustand";
import {
    analyzeImage,
    buildFromSample,
    buildFromText,
    createProject,
    deleteProject,
    generateFurniture as apiGenFurniture,
    getProject,
    getSamples,
    getStatus,
    listProjects,
    PModelError,
    renderHd as apiRenderHd,
    renderStatus,
    setShare,
    type BuildResult,
    type ProjectSummary,
    type RenderJob,
    type SampleInfo,
    type SceneSpec,
} from "@/lib/pmodel";

import type { View } from "../_components/ModelViewer";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const DEFAULT_VIEW: View = { mode: "orbit", day: true, furnish: true, ceiling: false, labels: true, tour: false };

export type Notice = { kind: "warn" | "info"; text: string } | null;
export type PromptMode = "describe" | "upload";

function friendly(e: unknown): string {
    const code = e instanceof PModelError ? e.code : "";
    if (code.includes("not_configured"))
        return "The AI model isn't configured yet (set OPENROUTER_API_KEY). Templates still work with no keys.";
    if (code === "no_rooms_detected")
        return "Couldn't read rooms from that plan — try a clearer, top-down floor plan.";
    if (code === "no_file") return "Choose a floor plan image first.";
    if (code === "no_prompt") return "Describe the home first.";
    return "Something went wrong building the model. Please try again.";
}

interface StudioState {
    enabled: boolean | null;
    vision: boolean;
    visionProvider: string;
    assets3d: boolean;
    hdrender: boolean;
    samples: SampleInfo[];
    projects: ProjectSummary[];
    activeId: string | null;
    activeProject: ProjectSummary | null;
    scene: SceneSpec | null;
    busy: boolean;
    notice: Notice;
    promptMode: PromptMode;
    render: RenderJob | null;
    furnishing: boolean;
    view: View;
    leftTab: "templates" | "scene";
    rightTab: "design" | "share";

    boot: () => Promise<void>;
    setView: (patch: Partial<View>) => void;
    setLeftTab: (t: "templates" | "scene") => void;
    setRightTab: (t: "design" | "share") => void;
    genFurniture: () => Promise<void>;
    renderHd: () => Promise<void>;
    refresh: () => Promise<ProjectSummary[]>;
    setPromptMode: (m: PromptMode) => void;
    setNotice: (n: Notice) => void;
    buildSample: (kind: string, name?: string) => Promise<void>;
    buildUpload: (file: File | null, name?: string) => Promise<void>;
    buildText: (prompt: string, name?: string) => Promise<void>;
    open: (id: string) => Promise<void>;
    remove: (id: string) => Promise<void>;
    setSharePublic: (pub: boolean) => Promise<void>;
}

export const useStudio = create<StudioState>((set, get) => ({
    enabled: null,
    vision: false,
    visionProvider: "openrouter",
    assets3d: false,
    hdrender: false,
    samples: [],
    projects: [],
    activeId: null,
    activeProject: null,
    scene: null,
    busy: false,
    notice: null,
    promptMode: "describe",
    render: null,
    furnishing: false,
    view: DEFAULT_VIEW,
    leftTab: "templates",
    rightTab: "design",

    setView: (patch) => set((s) => ({ view: { ...s.view, ...patch } })),
    setLeftTab: (t) => set({ leftTab: t }),
    setRightTab: (t) => set({ rightTab: t }),

    boot: async () => {
        const s = await getStatus();
        set({
            enabled: s.enabled,
            vision: s.vision,
            visionProvider: s.vision_provider || "openrouter",
            assets3d: !!s.assets3d,
            hdrender: !!s.hdrender,
        });
        if (!s.enabled) return;
        const [samples, projects] = await Promise.all([getSamples(), listProjects()]);
        set({ samples, projects });
    },

    genFurniture: async () => {
        const id = get().activeId;
        if (!id || get().furnishing) return;
        set({ furnishing: true, notice: null });
        try {
            await apiGenFurniture(id);
            await get().open(id); // re-fetch scene; now carries presigned glb urls
        } catch {
            set({ notice: { kind: "warn", text: "Couldn't generate realistic furniture." } });
        } finally {
            set({ furnishing: false });
        }
    },

    renderHd: async () => {
        const id = get().activeId;
        if (!id) return;
        set({ render: { state: "queued" } });
        try {
            const job = await apiRenderHd(id);
            if (!job.job) {
                set({ render: { state: "failed", error: job.error } });
                return;
            }
            for (let i = 0; i < 120; i++) {
                await sleep(2500);
                const st = await renderStatus(job.job);
                set({ render: st });
                if (st.state === "done" || st.state === "failed") return;
            }
            set({ render: { state: "failed", error: "timeout" } });
        } catch {
            set({ render: { state: "failed", error: "render_failed" } });
        }
    },

    refresh: async () => {
        const projects = await listProjects();
        set({ projects });
        return projects;
    },

    setPromptMode: (m) => set({ promptMode: m }),
    setNotice: (n) => set({ notice: n }),

    open: async (id) => {
        try {
            const full = await getProject(id);
            if (full.scene) {
                set({
                    scene: full.scene,
                    activeId: id,
                    activeProject: get().projects.find((p) => p.id === id) || null,
                    notice: null,
                });
            }
        } catch {
            /* ignore */
        }
    },

    remove: async (id) => {
        await deleteProject(id);
        if (id === get().activeId) set({ scene: null, activeId: null, activeProject: null });
        await get().refresh();
    },

    setSharePublic: async (pub) => {
        const id = get().activeId;
        if (!id) return;
        try {
            const r = await setShare(id, pub);
            set((st) => ({
                activeProject: st.activeProject
                    ? { ...st.activeProject, public: r.public, share_token: r.share_token }
                    : st.activeProject,
            }));
            await get().refresh();
        } catch {
            /* keep calm */
        }
    },

    buildSample: (kind, name) =>
        runBuild(set, get, async () => {
            const title =
                name || get().samples.find((s) => s.kind === kind)?.title || "Sample home";
            const p = await createProject(title);
            return buildFromSample(p.id, kind);
        }),

    buildUpload: (file, name) =>
        runBuild(set, get, async () => {
            if (!file) throw new PModelError("no_file");
            const p = await createProject(name || file.name.replace(/\.[^.]+$/, ""));
            return analyzeImage(p.id, file);
        }),

    buildText: (prompt, name) =>
        runBuild(set, get, async () => {
            if (!prompt.trim()) throw new PModelError("no_prompt");
            const p = await createProject(name || prompt.slice(0, 40));
            return buildFromText(p.id, prompt.trim());
        }),
}));

async function runBuild(
    set: (p: Partial<StudioState>) => void,
    get: () => StudioState,
    fn: () => Promise<BuildResult>,
) {
    set({ busy: true, notice: null });
    try {
        const r = await fn();
        set({ scene: r.scene, activeId: r.id });
        const projects = await get().refresh();
        set({ activeProject: projects.find((p) => p.id === r.id) || null });
    } catch (e) {
        set({ notice: { kind: "warn", text: friendly(e) } });
    } finally {
        set({ busy: false });
    }
}
