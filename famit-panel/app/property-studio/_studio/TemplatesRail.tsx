"use client";
// Left rail — instant-start templates (the built-in sample homes). One click builds
// + loads a fully furnished 3D model with no API key required.
import { useStudio } from "./store";
import Ico from "./icons";

const PREVIEW: Record<string, { grad: string; icon: string }> = {
    apartment_2bhk: { grad: "linear-gradient(135deg,#dbeafe,#eef2ff)", icon: "home" },
    studio: { grad: "linear-gradient(135deg,#fee2e2,#fdf2f8)", icon: "grid" },
    villa_3bhk: { grad: "linear-gradient(135deg,#dcfce7,#ecfeff)", icon: "layers" },
};

export default function TemplatesRail({ className = "" }: { className?: string }) {
    const samples = useStudio((s) => s.samples);
    const busy = useStudio((s) => s.busy);
    const buildSample = useStudio((s) => s.buildSample);

    return (
        <aside className={`bw-rail ${className}`}>
            <div className="bw-rail-head">
                <span className="flex size-7 items-center justify-center rounded-lg bg-[var(--bw-accent-soft)] text-[var(--bw-accent)]">
                    <Ico name="cube" size={16} />
                </span>
                <span className="bw-rail-title">Templates</span>
            </div>
            <div className="bw-rail-body bw-scroll flex flex-col gap-2.5 max-lg:max-h-[300px]">
                {samples.length === 0 ? (
                    <div className="bw-muted px-1 py-4 text-[12px]">Loading templates…</div>
                ) : (
                    samples.map((s) => {
                        const pv = PREVIEW[s.kind] || PREVIEW.apartment_2bhk;
                        return (
                            <button
                                key={s.kind}
                                type="button"
                                disabled={busy}
                                onClick={() => buildSample(s.kind)}
                                className="bw-card p-2 disabled:opacity-60"
                            >
                                <div
                                    className="relative mb-2 flex h-24 items-center justify-center rounded-[0.85rem]"
                                    style={{ background: pv.grad }}
                                >
                                    <span className="text-[var(--bw-s07)] opacity-70">
                                        <Ico name={pv.icon} size={34} />
                                    </span>
                                    <span className="absolute right-2 top-2 flex size-7 items-center justify-center rounded-lg bg-white/85 text-[var(--bw-accent)] shadow-sm">
                                        <Ico name="arrow" size={14} />
                                    </span>
                                </div>
                                <div className="px-1 pb-1">
                                    <div className="text-[13px] font-semibold">{s.title}</div>
                                    <div className="bw-muted mt-0.5 line-clamp-2 text-[11px] leading-[0.95rem]">
                                        {s.desc}
                                    </div>
                                </div>
                            </button>
                        );
                    })
                )}
            </div>
            <div className="border-t border-[var(--bw-border-1)] px-3 py-2.5">
                <div className="bw-muted text-[11px] leading-[0.95rem]">
                    Templates render instantly — no API key needed. Use the bar below to build from your
                    own plan or description.
                </div>
            </div>
        </aside>
    );
}
