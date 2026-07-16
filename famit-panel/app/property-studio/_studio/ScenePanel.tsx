"use client";
// Left panel (Brainwave LeftSidebar): project head + Scene/Templates tabs. Scene = the
// active model's room tree; Templates = one-click sample homes.
import { useStudio } from "./store";
import Ico from "./icons";

const ROOM_ICON: Record<string, string> = {
    bedroom: "bed", living: "home", kitchen: "grid", bath: "grid", dining: "grid",
    balcony: "layers", office: "grid",
};
const PREVIEW: Record<string, string> = {
    apartment_2bhk: "linear-gradient(135deg,#1f3a8a55,#3b1d6e44)",
    studio: "linear-gradient(135deg,#7a1d3a55,#3a1d6e44)",
    villa_3bhk: "linear-gradient(135deg,#14532d55,#0e4a5e44)",
};

export default function ScenePanel({ className = "" }: { className?: string }) {
    const scene = useStudio((s) => s.scene);
    const samples = useStudio((s) => s.samples);
    const busy = useStudio((s) => s.busy);
    const buildSample = useStudio((s) => s.buildSample);
    const tab = useStudio((s) => s.leftTab);
    const setTab = useStudio((s) => s.setLeftTab);

    return (
        <aside className={`bw-panel ${className}`}>
            <div className="bw-phead">
                <span className="flex size-8 items-center justify-center rounded-[0.6rem] bg-[var(--bw-accent-soft)] text-[var(--bw-accent)]">
                    <Ico name="cube" size={17} />
                </span>
                <div className="min-w-0">
                    <div className="truncate text-[13.5px] font-semibold leading-tight">
                        {scene ? scene.meta.title : "Property Studio"}
                    </div>
                    <div className="bw-faint text-[11px] leading-tight">3D property model</div>
                </div>
            </div>

            <div className="border-b border-[var(--bw-border-1)] px-3 py-2.5">
                <div className="bw-tabs">
                    <button className={`bw-tab ${tab === "scene" ? "is-active" : ""}`} onClick={() => setTab("scene")}>Scene</button>
                    <button className={`bw-tab ${tab === "templates" ? "is-active" : ""}`} onClick={() => setTab("templates")}>Templates</button>
                </div>
            </div>

            <div className="bw-pbody bw-scroll">
                {tab === "scene" ? (
                    scene ? (
                        <div className="flex flex-col gap-1">
                            <div className="bw-row">
                                <span className="bw-row-ic"><Ico name="camera" size={15} /></span>
                                <span className="text-[12.5px]">Camera</span>
                            </div>
                            <div className="bw-row">
                                <span className="bw-row-ic"><Ico name={scene.meta ? "sun" : "sun"} size={15} /></span>
                                <span className="text-[12.5px]">Lighting</span>
                            </div>
                            <div className="my-1.5 h-px bg-[var(--bw-border-1)]" />
                            {scene.floors.map((f, i) => (
                                <div key={i} className="bw-row">
                                    <span className="bw-row-ic"><Ico name={ROOM_ICON[f.type] || "grid"} size={15} /></span>
                                    <span className="min-w-0 flex-1 truncate text-[12.5px]">{f.name}</span>
                                    <span className="bw-faint text-[11px]">{Math.round(f.area_sqm * 10.764)} ft²</span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="bw-faint px-1 py-6 text-center text-[12px]">
                            No model yet. Pick a Template, or describe / upload a plan below.
                        </div>
                    )
                ) : (
                    <div className="flex flex-col gap-2.5">
                        {samples.map((s) => (
                            <button key={s.kind} type="button" disabled={busy} onClick={() => buildSample(s.kind)} className="bw-card p-2 disabled:opacity-60">
                                <div className="relative mb-2 flex h-20 items-center justify-center rounded-[0.7rem]" style={{ background: PREVIEW[s.kind] || PREVIEW.apartment_2bhk }}>
                                    <span className="text-[var(--bw-secondary)]"><Ico name="home" size={28} /></span>
                                    <span className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-lg bg-black/30 text-[var(--bw-accent)]"><Ico name="arrow" size={13} /></span>
                                </div>
                                <div className="px-1 pb-1">
                                    <div className="text-[12.5px] font-semibold">{s.title}</div>
                                    <div className="bw-faint mt-0.5 line-clamp-2 text-[11px] leading-[0.95rem]">{s.desc}</div>
                                </div>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </aside>
    );
}
