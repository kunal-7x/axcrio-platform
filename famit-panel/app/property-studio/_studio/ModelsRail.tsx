"use client";
// Right rail — the active model's stats + customer share link, and the library of
// saved models. Share publishes the public /share/property/{token} page the voice
// agent can text mid-call.
import { useEffect, useState } from "react";
import { useStudio } from "./store";
import Ico from "./icons";

const SRC: Record<string, string> = { image: "Plan", text: "Brief", sample: "Template" };

function ShareControls() {
    const project = useStudio((s) => s.activeProject);
    const setSharePublic = useStudio((s) => s.setSharePublic);
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);
    const isPublic = !!project?.public;

    useEffect(() => setCopied(false), [project?.id]);
    if (!project) return null;

    const link =
        typeof window !== "undefined"
            ? `${window.location.origin}/share/property/${project.share_token}`
            : "";

    async function toggle() {
        setBusy(true);
        await setSharePublic(!isPublic);
        setBusy(false);
    }
    async function copy() {
        try {
            await navigator.clipboard.writeText(link);
            setCopied(true);
            setTimeout(() => setCopied(false), 1600);
        } catch {
            /* ignore */
        }
    }

    return (
        <div className="mt-3 rounded-[0.85rem] border border-[var(--bw-border-1)] bg-[var(--bw-surface-02)] p-3">
            <div className="mb-2 flex items-center gap-2">
                <span className={`bw-dot ${isPublic ? "bg-[var(--bw-green)]" : "bg-[var(--bw-border-2)]"}`} />
                <span className="text-[12px] font-semibold">
                    {isPublic ? "Shared with customers" : "Private"}
                </span>
                <button
                    type="button"
                    onClick={toggle}
                    disabled={busy}
                    className="bw-btn bw-btn-ghost ml-auto !h-8 !px-3 !text-[12px]"
                >
                    {isPublic ? "Make private" : "Publish link"}
                </button>
            </div>
            {isPublic && (
                <div className="flex items-center gap-1.5">
                    <input readOnly value={link} className="bw-field !h-9 flex-1 !text-[11px]" />
                    <button type="button" onClick={copy} className="bw-icon !size-9" title="Copy link">
                        <Ico name={copied ? "check" : "copy"} size={16} />
                    </button>
                    <a
                        href={link}
                        target="_blank"
                        rel="noreferrer"
                        className="bw-icon !size-9"
                        title="Open share page"
                    >
                        <Ico name="link" size={16} />
                    </a>
                </div>
            )}
        </div>
    );
}

function ProActions() {
    const assets3d = useStudio((s) => s.assets3d);
    const hdrender = useStudio((s) => s.hdrender);
    const furnishing = useStudio((s) => s.furnishing);
    const render = useStudio((s) => s.render);
    const genFurniture = useStudio((s) => s.genFurniture);
    const renderHd = useStudio((s) => s.renderHd);
    if (!assets3d && !hdrender) return null; // dormant → nothing shown (default)

    const rendering = render?.state === "queued" || render?.state === "running";
    return (
        <div className="mt-3 rounded-[0.85rem] border border-[var(--bw-border-1)] bg-[var(--bw-surface-02)] p-3">
            <div className="bw-muted mb-2 text-[11px] font-semibold uppercase tracking-[0.06em]">
                Studio Pro
            </div>
            <div className="flex flex-col gap-2">
                {assets3d && (
                    <button
                        type="button"
                        onClick={genFurniture}
                        disabled={furnishing}
                        className="bw-btn bw-btn-ghost !h-9 w-full !text-[12px]"
                    >
                        {furnishing ? (
                            <Ico name="spinner" size={15} className="bw-spin" />
                        ) : (
                            <Ico name="sparkle" size={15} />
                        )}
                        {furnishing ? "Generating meshes…" : "Realistic AI furniture"}
                    </button>
                )}
                {hdrender && (
                    <button
                        type="button"
                        onClick={renderHd}
                        disabled={rendering}
                        className="bw-btn bw-btn-dark !h-9 w-full !text-[12px]"
                    >
                        {rendering ? (
                            <Ico name="spinner" size={15} className="bw-spin" />
                        ) : (
                            <Ico name="image" size={15} />
                        )}
                        {rendering ? "Rendering in HD…" : "Render in HD (Blender)"}
                    </button>
                )}
                {render?.state === "done" && render.url && (
                    <a href={render.url} target="_blank" rel="noreferrer" className="block">
                        <img
                            src={render.url}
                            alt="HD render"
                            className="w-full rounded-[0.7rem] border border-[var(--bw-border-1)]"
                        />
                        <span className="bw-muted mt-1 block text-center text-[11px]">
                            HD render ready — click to open
                        </span>
                    </a>
                )}
                {render?.state === "failed" && (
                    <div className="bw-notice bw-notice-warn">HD render failed. Check the worker.</div>
                )}
            </div>
        </div>
    );
}

export default function ModelsRail({ className = "" }: { className?: string }) {
    const scene = useStudio((s) => s.scene);
    const projects = useStudio((s) => s.projects);
    const activeId = useStudio((s) => s.activeId);
    const open = useStudio((s) => s.open);
    const remove = useStudio((s) => s.remove);
    const m = scene?.meta;

    return (
        <aside className={`bw-rail ${className}`}>
            <div className="bw-rail-head">
                <span className="flex size-7 items-center justify-center rounded-lg bg-[var(--bw-surface-03)] text-[var(--bw-secondary)]">
                    <Ico name="layers" size={16} />
                </span>
                <span className="bw-rail-title">Models</span>
                <span className="bw-muted ml-auto text-[11px]">{projects.length}</span>
            </div>

            <div className="bw-rail-body bw-scroll">
                {/* active model meta + share */}
                {m && (
                    <div className="mb-3 rounded-[0.85rem] border border-[var(--bw-border-1)] bg-[var(--bw-surface-01)] p-3">
                        <div className="text-[13px] font-semibold">{m.title}</div>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                            <span className="bw-chip">{m.rooms} rooms</span>
                            <span className="bw-chip">{m.bedrooms} bed</span>
                            <span className="bw-chip">{m.baths} bath</span>
                            <span className="bw-chip">{Math.round(m.area_sqft)} ft²</span>
                        </div>
                        <ShareControls />
                        <ProActions />
                    </div>
                )}

                {/* saved library */}
                <div className="bw-muted mb-1.5 px-1 text-[11px] font-semibold uppercase tracking-[0.06em]">
                    Saved
                </div>
                {projects.length === 0 ? (
                    <div className="bw-muted px-1 py-3 text-[12px]">
                        No models yet — generate one to build your library.
                    </div>
                ) : (
                    <div className="flex flex-col gap-1">
                        {projects.map((p) => (
                            <div
                                key={p.id}
                                onClick={() => open(p.id)}
                                className={`group flex cursor-pointer items-center gap-2 rounded-[0.7rem] px-2.5 py-2 transition-colors ${
                                    activeId === p.id
                                        ? "bg-[var(--bw-accent-soft)]"
                                        : "hover:bg-[var(--bw-surface-03)]"
                                }`}
                            >
                                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-[var(--bw-surface-03)] text-[var(--bw-secondary)]">
                                    <Ico name="home" size={15} />
                                </span>
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-1.5">
                                        <span className="truncate text-[12.5px] font-semibold">{p.name}</span>
                                        {p.public && <span className="bw-dot bg-[var(--bw-green)]" />}
                                    </div>
                                    <div className="bw-muted truncate text-[11px]">
                                        {p.state === "ready"
                                            ? `${p.rooms} rooms · ${Math.round(p.area_sqft)} ft²`
                                            : p.state}
                                        {p.source ? ` · ${SRC[p.source] || p.source}` : ""}
                                    </div>
                                </div>
                                <button
                                    type="button"
                                    title="Delete"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        if (confirm(`Delete “${p.name}”?`)) remove(p.id);
                                    }}
                                    className="bw-icon !size-7 shrink-0 opacity-0 transition-opacity hover:!text-[#e0483a] group-hover:opacity-100"
                                >
                                    <Ico name="trash" size={15} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </aside>
    );
}
