"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Icon from "@/components/Icon";
import {
    getPipeline,
    updateOpportunity,
    type Opportunity,
    type Stage,
    type ActivityTarget,
} from "../client";
import { fmtMoney, stageColor } from "../_ui";

type Props = {
    canWrite: boolean;
    onOpen: (type: ActivityTarget, id: string) => void;
};

// The deal pipeline as a Twenty-style Kanban: one column per live stage, cards
// dragged across columns. A drop PATCHes the opportunity's `stage` in Twenty
// (optimistic — the card moves instantly, reverting if the write fails).
export default function PipelineBoard({ canWrite, onOpen }: Props) {
    const qc = useQueryClient();
    const q = useQuery({ queryKey: ["twenty", "pipeline"], queryFn: getPipeline, refetchInterval: 20_000 });

    const stages: Stage[] = q.data?.stages ?? [];

    // Local column copy so a drag moves the card instantly. Re-synced from the
    // server whenever the query refreshes AND we aren't mid-drag or mid-write — a
    // 20s refetch that lands during a PATCH must NOT revert the just-dropped card.
    const [cols, setCols] = useState<Record<string, Opportunity[]>>({});
    const dragging = useRef(false);
    const inFlight = useRef(false);
    const prevCols = useRef<Record<string, Opportunity[]> | null>(null);
    useEffect(() => {
        if (!dragging.current && !inFlight.current && q.data?.columns) setCols(q.data.columns);
    }, [q.data?.columns]);

    const [dragId, setDragId] = useState<string | null>(null);
    const [overStage, setOverStage] = useState<string | null>(null);

    const move = useMutation({
        mutationFn: ({ id, stage }: { id: string; stage: string }) =>
            updateOpportunity(id, { stage }),
        // Explicit rollback so a failed move reverts immediately (not only once the
        // next refetch happens to return authoritative state).
        onError: () => {
            if (prevCols.current) setCols(prevCols.current);
        },
        onSettled: () => {
            inFlight.current = false;
            qc.invalidateQueries({ queryKey: ["twenty", "pipeline"] });
        },
    });

    const findCard = (id: string): { stage: string; card: Opportunity } | null => {
        for (const [stage, list] of Object.entries(cols)) {
            const card = list.find((o) => o.id === id);
            if (card) return { stage, card };
        }
        return null;
    };

    const drop = (toStage: string) => {
        setOverStage(null);
        const id = dragId;
        setDragId(null);
        dragging.current = false;
        if (!id || !canWrite) return;
        const found = findCard(id);
        if (!found || found.stage === toStage) return;
        // optimistic local move (snapshot first so onError can roll back); inFlight
        // keeps the periodic refetch from reverting the card until the PATCH settles.
        prevCols.current = cols;
        inFlight.current = true;
        setCols((prev) => {
            const next: Record<string, Opportunity[]> = {};
            for (const [s, list] of Object.entries(prev)) next[s] = list.filter((o) => o.id !== id);
            next[toStage] = [{ ...found.card, stage: toStage }, ...(next[toStage] ?? [])];
            return next;
        });
        move.mutate({ id, stage: toStage });
    };

    if (q.isLoading) return <BoardSkeleton />;
    if (q.error)
        return (
            <div className="flex items-center gap-2 m-3 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03">
                <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                {q.error instanceof Error ? q.error.message : "Could not load the pipeline"}
            </div>
        );

    const totalDeals = Object.values(cols).reduce((n, l) => n + l.length, 0);
    if (totalDeals === 0)
        return (
            <div className="py-16 text-center max-md:py-12">
                <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                    <Icon name="chart" className="fill-t-tertiary" />
                </span>
                <div className="text-h6 mb-1">No deals yet</div>
                <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                    Create an opportunity, or import your called leads — each becomes a card
                    you can drag across the pipeline.
                </div>
            </div>
        );

    return (
        <div className="flex gap-3 p-3 pt-1 overflow-x-auto scrollbar-none max-md:px-2">
            {stages.map((stage) => {
                const list = cols[stage.value] ?? [];
                const sum = list.reduce((n, o) => n + (o.amount ?? 0), 0);
                const cur = list.find((o) => o.currencyCode)?.currencyCode || "USD";
                const isOver = overStage === stage.value;
                return (
                    <div
                        key={stage.value}
                        className={`flex flex-col w-72 shrink-0 rounded-3xl bg-b-surface1 transition-colors ${
                            isOver ? "ring-2 ring-primary-01/40" : ""
                        }`}
                        onDragOver={(e) => {
                            if (!dragId) return;
                            e.preventDefault();
                            setOverStage(stage.value);
                        }}
                        onDragLeave={() => setOverStage((s) => (s === stage.value ? null : s))}
                        onDrop={() => drop(stage.value)}
                    >
                        {/* column header */}
                        <div className="flex items-center gap-2 px-4 pt-4 pb-3">
                            <span
                                className="size-2.5 rounded-full shrink-0"
                                style={{ backgroundColor: stageColor(stage.color) }}
                            />
                            <span className="text-button text-t-primary truncate">{stage.label}</span>
                            <span className="ml-auto inline-flex items-center justify-center min-w-6 h-6 px-2 rounded-full bg-b-surface2 text-caption text-t-secondary">
                                {list.length}
                            </span>
                        </div>
                        {sum > 0 && (
                            <div className="px-4 -mt-1 mb-1 text-caption text-t-tertiary">
                                {fmtMoney(sum, cur)} total
                            </div>
                        )}
                        {/* cards */}
                        <div className="flex flex-col gap-2 p-2 pt-1 min-h-24">
                            {list.map((o) => (
                                <DealCard
                                    key={o.id}
                                    opp={o}
                                    draggable={canWrite}
                                    onDragStart={() => {
                                        dragging.current = true;
                                        setDragId(o.id);
                                    }}
                                    onDragEnd={() => {
                                        dragging.current = false;
                                        setDragId(null);
                                        setOverStage(null);
                                    }}
                                    onClick={() => onOpen("opportunity", o.id)}
                                />
                            ))}
                            {list.length === 0 && (
                                <div className="grid place-items-center h-20 rounded-2xl border border-dashed border-s-subtle text-caption text-t-tertiary">
                                    {dragId ? "Drop here" : "Empty"}
                                </div>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

function DealCard({
    opp,
    draggable,
    onDragStart,
    onDragEnd,
    onClick,
}: {
    opp: Opportunity;
    draggable: boolean;
    onDragStart: () => void;
    onDragEnd: () => void;
    onClick: () => void;
}) {
    return (
        <div
            draggable={draggable}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
            onClick={onClick}
            className={`group p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset transition-all hover:shadow-depth ${
                draggable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"
            }`}
        >
            <div className="text-sub-title-1 text-t-primary truncate">{opp.name}</div>
            <div className="mt-1 flex items-center justify-between gap-2">
                <span className="text-body-2 text-t-tertiary truncate">
                    {opp.companyName || "—"}
                </span>
                {opp.amount != null && (
                    <span className="text-button text-t-primary shrink-0">
                        {fmtMoney(opp.amount, opp.currencyCode)}
                    </span>
                )}
            </div>
            {opp.pointOfContactName && (
                <div className="mt-2 flex items-center gap-1.5 text-caption text-t-tertiary">
                    <Icon name="profile" className="size-3.5 fill-t-tertiary" />
                    <span className="truncate">{opp.pointOfContactName}</span>
                </div>
            )}
        </div>
    );
}

function BoardSkeleton() {
    return (
        <div className="flex gap-3 p-3 pt-1 overflow-hidden">
            {[...Array(5)].map((_, i) => (
                <div key={i} className="w-72 shrink-0 rounded-3xl bg-b-surface1 p-2">
                    <div className="skeleton h-6 w-32 m-2 rounded-lg" />
                    {[...Array(3)].map((__, j) => (
                        <div key={j} className="skeleton h-20 m-2 rounded-2xl" />
                    ))}
                </div>
            ))}
        </div>
    );
}
