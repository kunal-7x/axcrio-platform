"use client";
import Card from "@/components/Card";
import type { ProjectSummary } from "@/lib/pmodel";

const SRC: Record<string, string> = { image: "Plan", text: "Brief", sample: "Sample" };

export default function ProjectGrid({
    projects,
    activeId,
    onOpen,
    onDelete,
}: {
    projects: ProjectSummary[];
    activeId: string | null;
    onOpen: (id: string) => void;
    onDelete: (id: string) => void;
}) {
    return (
        <Card title="Your models">
            <div className="px-2 pb-2">
                {projects.length === 0 ? (
                    <div className="px-3 py-6 text-caption text-t-tertiary">
                        No models yet — generate one above.
                    </div>
                ) : (
                    <div className="flex flex-col">
                        {projects.map((p) => (
                            <div
                                key={p.id}
                                className={`group flex items-center gap-3 rounded-xl px-3 py-2.5 cursor-pointer transition-colors ${
                                    activeId === p.id ? "bg-primary-01/8" : "hover:bg-b-surface1"
                                }`}
                                onClick={() => onOpen(p.id)}
                            >
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className="truncate text-body-2 font-semibold">{p.name}</span>
                                        {p.public && (
                                            <span className="size-1.5 rounded-full bg-[#00A656]" title="Shared publicly" />
                                        )}
                                    </div>
                                    <div className="text-caption text-t-tertiary">
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
                                        if (confirm(`Delete “${p.name}”?`)) onDelete(p.id);
                                    }}
                                    className="opacity-0 group-hover:opacity-100 transition-opacity text-t-tertiary hover:text-[#FF6A55] text-[13px] px-2"
                                >
                                    Delete
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </Card>
    );
}
