"use client";
// Right panel (Brainwave RightSidebar): Design tab (camera / lighting / display /
// materials / pro) + Share tab (publish link + saved models). All view controls live
// here in the chrome (the canvas stays clean), driving the store's `view`.
import { useEffect, useState } from "react";
import { useStudio } from "./store";
import Ico from "./icons";

const SRC: Record<string, string> = { image: "Plan", text: "Brief", sample: "Template" };
const MAT_COLORS: Record<string, string> = { wood: "#caa472", tile: "#dfe3ea", stone: "#c8ccd4", deck: "#b08c63", carpet: "#b9b3ab" };

function Switch({ on, onClick }: { on: boolean; onClick: () => void }) {
    return <button type="button" onClick={onClick} className={`bw-switch ${on ? "is-on" : ""}`} aria-pressed={on} />;
}

function ShareBlock() {
    const project = useStudio((s) => s.activeProject);
    const setSharePublic = useStudio((s) => s.setSharePublic);
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);
    const isPublic = !!project?.public;
    useEffect(() => setCopied(false), [project?.id]);
    if (!project) return null;
    const link = typeof window !== "undefined" ? `${window.location.origin}/share/property/${project.share_token}` : "";

    return (
        <div className="bw-section">
            <div className="bw-section-h">Customer share</div>
            <div className="mb-2 flex items-center gap-2">
                <span className={`bw-dot ${isPublic ? "bg-[var(--bw-green)]" : "bg-[var(--bw-faint)]"}`} />
                <span className="text-[12.5px] font-semibold">{isPublic ? "Shared with customers" : "Private"}</span>
                <button type="button" disabled={busy} onClick={async () => { setBusy(true); await setSharePublic(!isPublic); setBusy(false); }} className="bw-btn bw-btn-ghost ml-auto !h-8 !px-3 !text-[12px]">
                    {isPublic ? "Make private" : "Publish link"}
                </button>
            </div>
            {isPublic && (
                <div className="flex items-center gap-1.5">
                    <input readOnly value={link} className="bw-field !h-9 flex-1 !text-[11px]" />
                    <button type="button" onClick={async () => { try { await navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch {} }} className="bw-icon !size-9" title="Copy"><Ico name={copied ? "check" : "copy"} size={15} /></button>
                    <a href={link} target="_blank" rel="noreferrer" className="bw-icon !size-9" title="Open"><Ico name="link" size={15} /></a>
                </div>
            )}
        </div>
    );
}

function ProBlock() {
    const assets3d = useStudio((s) => s.assets3d);
    const hdrender = useStudio((s) => s.hdrender);
    const furnishing = useStudio((s) => s.furnishing);
    const render = useStudio((s) => s.render);
    const genFurniture = useStudio((s) => s.genFurniture);
    const renderHd = useStudio((s) => s.renderHd);
    if (!assets3d && !hdrender) return null;
    const rendering = render?.state === "queued" || render?.state === "running";
    return (
        <div className="bw-section">
            <div className="bw-section-h">Studio Pro</div>
            <div className="flex flex-col gap-2">
                {assets3d && (
                    <button type="button" onClick={genFurniture} disabled={furnishing} className="bw-btn bw-btn-ghost !h-9 w-full !text-[12px]">
                        <Ico name={furnishing ? "spinner" : "sparkle"} size={15} className={furnishing ? "bw-spin" : ""} /> {furnishing ? "Generating…" : "Realistic AI furniture"}
                    </button>
                )}
                {hdrender && (
                    <button type="button" onClick={renderHd} disabled={rendering} className="bw-btn bw-btn-light !h-9 w-full !text-[12px]">
                        <Ico name={rendering ? "spinner" : "image"} size={15} className={rendering ? "bw-spin" : ""} /> {rendering ? "Rendering…" : "Render in HD"}
                    </button>
                )}
                {render?.state === "done" && render.url && (
                    <a href={render.url} target="_blank" rel="noreferrer"><img src={render.url} alt="HD render" className="w-full rounded-[0.7rem] border border-[var(--bw-border-1)]" /></a>
                )}
            </div>
        </div>
    );
}

export default function DesignPanel({ className = "" }: { className?: string }) {
    const scene = useStudio((s) => s.scene);
    const view = useStudio((s) => s.view);
    const setView = useStudio((s) => s.setView);
    const projects = useStudio((s) => s.projects);
    const activeId = useStudio((s) => s.activeId);
    const open = useStudio((s) => s.open);
    const remove = useStudio((s) => s.remove);
    const tab = useStudio((s) => s.rightTab);
    const setTab = useStudio((s) => s.setRightTab);
    const m = scene?.meta;

    return (
        <aside className={`bw-panel ${className}`}>
            <div className="bw-phead">
                <span className="bw-rail-title text-[13.5px] font-semibold">Inspector</span>
                <span className="bw-chip ml-auto"><Ico name="layers" size={12} /> {projects.length}</span>
            </div>
            <div className="border-b border-[var(--bw-border-1)] px-3 py-2.5">
                <div className="bw-tabs">
                    <button className={`bw-tab ${tab === "design" ? "is-active" : ""}`} onClick={() => setTab("design")}>Design</button>
                    <button className={`bw-tab ${tab === "share" ? "is-active" : ""}`} onClick={() => setTab("share")}>Share</button>
                </div>
            </div>

            <div className="bw-pbody bw-scroll !p-0">
                {!scene ? (
                    <div className="bw-faint p-6 text-center text-[12px]">Generate a model to edit it here.</div>
                ) : tab === "design" ? (
                    <>
                        <div className="bw-section">
                            <div className="bw-section-h">Camera</div>
                            <div className="bw-seg mb-2">
                                <button className={`bw-seg-item ${view.mode === "orbit" && !view.tour ? "is-active" : ""}`} onClick={() => setView({ mode: "orbit", tour: false })}>Dollhouse</button>
                                <button className={`bw-seg-item ${view.mode === "walk" && !view.tour ? "is-active" : ""}`} onClick={() => setView({ mode: "walk", tour: false })}>Walk</button>
                            </div>
                            <button className={`bw-btn w-full !h-9 !text-[12px] ${view.tour ? "bw-btn-primary" : "bw-btn-ghost"}`} onClick={() => setView({ tour: !view.tour })}>
                                <Ico name="play" size={14} /> {view.tour ? "Stop tour" : "Play cinematic tour"}
                            </button>
                        </div>

                        <div className="bw-section">
                            <div className="bw-section-h">Lighting</div>
                            <div className="bw-seg">
                                <button className={`bw-seg-item ${view.day ? "is-active" : ""}`} onClick={() => setView({ day: true })}>☀ Day</button>
                                <button className={`bw-seg-item ${!view.day ? "is-active" : ""}`} onClick={() => setView({ day: false })}>☾ Night</button>
                            </div>
                        </div>

                        <div className="bw-section">
                            <div className="bw-section-h">Display</div>
                            <div className="bw-toggle-row"><span>Furniture</span><Switch on={view.furnish} onClick={() => setView({ furnish: !view.furnish })} /></div>
                            <div className="bw-toggle-row"><span>Ceilings</span><Switch on={view.ceiling} onClick={() => setView({ ceiling: !view.ceiling })} /></div>
                            <div className="bw-toggle-row"><span>Room labels</span><Switch on={view.labels} onClick={() => setView({ labels: !view.labels })} /></div>
                        </div>

                        <div className="bw-section">
                            <div className="bw-section-h">Materials</div>
                            <div className="bw-swatches">
                                {Object.entries(MAT_COLORS).map(([k, c]) => (
                                    <div key={k} className="bw-swatch" style={{ background: c }} title={k} />
                                ))}
                            </div>
                        </div>

                        <ProBlock />
                    </>
                ) : (
                    <>
                        {m && (
                            <div className="bw-section">
                                <div className="text-[13px] font-semibold">{m.title}</div>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                    <span className="bw-chip">{m.rooms} rooms</span>
                                    <span className="bw-chip">{m.bedrooms} bed</span>
                                    <span className="bw-chip">{m.baths} bath</span>
                                    <span className="bw-chip">{Math.round(m.area_sqft)} ft²</span>
                                </div>
                            </div>
                        )}
                        <ShareBlock />
                        <div className="bw-section !border-b-0">
                            <div className="bw-section-h">Saved models</div>
                            {projects.length === 0 ? (
                                <div className="bw-faint text-[12px]">No models yet.</div>
                            ) : (
                                <div className="flex flex-col gap-1">
                                    {projects.map((p) => (
                                        <div key={p.id} onClick={() => open(p.id)} className={`group flex cursor-pointer items-center gap-2.5 rounded-[0.7rem] px-2 py-1.5 transition-colors ${activeId === p.id ? "bg-[var(--bw-accent-soft)]" : "hover:bg-[var(--bw-surface-02)]"}`}>
                                            <span className="bw-row-ic !size-7"><Ico name="home" size={14} /></span>
                                            <div className="min-w-0 flex-1">
                                                <div className="flex items-center gap-1.5"><span className="truncate text-[12px] font-semibold">{p.name}</span>{p.public && <span className="bw-dot bg-[var(--bw-green)]" />}</div>
                                                <div className="bw-faint truncate text-[11px]">{p.state === "ready" ? `${p.rooms} rooms · ${Math.round(p.area_sqft)} ft²` : p.state}{p.source ? ` · ${SRC[p.source] || p.source}` : ""}</div>
                                            </div>
                                            <button type="button" title="Delete" onClick={(e) => { e.stopPropagation(); if (confirm(`Delete "${p.name}"?`)) remove(p.id); }} className="bw-icon !size-7 shrink-0 opacity-0 transition-opacity hover:!text-[var(--bw-danger)] group-hover:opacity-100"><Ico name="trash" size={14} /></button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </aside>
    );
}
