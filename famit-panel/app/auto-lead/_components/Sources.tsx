"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Card from "@/components/Card";
import Switch from "@/components/Switch";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import { getTypes, getSources, updateSource, type Source, type SourceType } from "../client";
import { SourceIcon, fmtRelative } from "../_ui";
import SourceModal from "./SourceModal";

export default function Sources() {
    const qc = useQueryClient();
    const typesQ = useQuery({ queryKey: ["auto-lead", "types"], queryFn: getTypes });
    const sourcesQ = useQuery({
        queryKey: ["auto-lead", "sources"],
        queryFn: getSources,
        refetchInterval: 15_000,
    });
    const types: SourceType[] = typesQ.data?.types ?? [];
    const sources: Source[] = sourcesQ.data?.sources ?? [];
    const canWrite = sourcesQ.data?.can_write !== false;

    const typeByKey = useMemo(() => new Map(types.map((t) => [t.type, t])), [types]);
    const [modal, setModal] = useState<{ type: SourceType; source: Source | null } | null>(null);

    const toggle = useMutation({
        mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => updateSource(id, { enabled }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ["auto-lead"] }),
    });

    const openEdit = (s: Source) => {
        const t = typeByKey.get(s.type);
        if (t) setModal({ type: t, source: s });
    };

    return (
        <div className="flex flex-col gap-3">
            {/* configured sources */}
            <Card title="Connected sources">
                {sources.length === 0 ? (
                    <div className="px-5 pb-8 pt-2 text-body-2 text-t-secondary max-lg:px-3">
                        No sources yet — pick one below to start capturing leads in real time.
                    </div>
                ) : (
                    <div className="grid grid-cols-2 gap-3 px-3 pb-4 max-lg:grid-cols-1">
                        {sources.map((s) => (
                            <div
                                key={s.id}
                                className="group flex items-center gap-3 p-3.5 rounded-3xl bg-b-surface1 ring-1 ring-s-subtle ring-inset transition-all hover:shadow-depth cursor-pointer"
                                onClick={() => openEdit(s)}
                            >
                                <SourceIcon icon={s.icon} type={s.type} size={13} />
                                <div className="min-w-0 flex-1">
                                    <div className="flex items-center gap-2">
                                        <span className="truncate text-sub-title-1 text-t-primary">{s.name}</span>
                                        <Badge variant={s.enabled ? "success" : "neutral"} dot>
                                            {s.enabled ? "Live" : "Paused"}
                                        </Badge>
                                    </div>
                                    <div className="text-caption text-t-tertiary truncate">
                                        {s.type_label} · {s.stats?.accepted ?? 0} leads
                                        {s.stats?.last_at ? ` · ${fmtRelative(s.stats.last_at)}` : ""}
                                    </div>
                                </div>
                                <div onClick={(e) => e.stopPropagation()}>
                                    <Switch
                                        checked={s.enabled}
                                        onChange={(v) => canWrite && toggle.mutate({ id: s.id, enabled: v })}
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Card>

            {/* add a source */}
            <Card title="Add a source">
                <div className="grid grid-cols-3 gap-3 px-3 pb-4 max-lg:grid-cols-2 max-md:grid-cols-1">
                    {types.map((t) => (
                        <button
                            key={t.type}
                            disabled={!canWrite}
                            onClick={() => setModal({ type: t, source: null })}
                            className="group flex items-start gap-3 p-4 rounded-3xl text-left bg-b-surface1 ring-1 ring-s-subtle ring-inset transition-all hover:shadow-depth disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <SourceIcon icon={t.icon} type={t.type} size={14} />
                            <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                    <span className="text-sub-title-1 text-t-primary">{t.label}</span>
                                    <span className="text-caption text-t-tertiary">
                                        {t.mode === "push" ? "Webhook" : "Polling"}
                                    </span>
                                </div>
                                <div className="text-caption text-t-tertiary line-clamp-2 mt-0.5">{t.desc}</div>
                            </div>
                            <Icon
                                name="plus"
                                className="size-4 ml-auto shrink-0 fill-t-tertiary opacity-0 transition-opacity group-hover:opacity-100"
                            />
                        </button>
                    ))}
                </div>
            </Card>

            {modal && (
                <SourceModal
                    open={!!modal}
                    sourceType={modal.type}
                    source={modal.source}
                    onClose={() => setModal(null)}
                />
            )}
        </div>
    );
}
