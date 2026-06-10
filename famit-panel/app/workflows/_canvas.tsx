"use client";

// The Workflow Studio canvas — a dependency-free node-graph renderer.
//
// Deliberately NO @xyflow/react: adding it would mean editing package.json +
// the lockfile (outside this route's own files) and a build risk. This canvas is
// plain React + inline SVG: <div> nodes positioned absolutely, bezier <path>
// edges in an SVG layer behind them, with pan (drag the background) and a local
// node-drag (drag a node within the session). Click a node to inspect it.
//
// It renders a STATIC definition (a sample / template DSL) as a premium preview
// while the durable engine is dormant — an honest showcase of the studio, not a
// live persisting editor wired to dead endpoints.

import { useCallback, useMemo, useRef, useState } from "react";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import {
    type WfDefinition,
    type WfNode,
    type WfEdge,
    nodeMeta,
} from "./_lib";

const NODE_W = 168;
const NODE_H = 64;

type Pt = { x: number; y: number };

// A smooth cubic bezier from the right edge of `a` to the left edge of `b`.
function edgePath(a: Pt, b: Pt): string {
    const sx = a.x + NODE_W;
    const sy = a.y + NODE_H / 2;
    const tx = b.x;
    const ty = b.y + NODE_H / 2;
    const dx = Math.max(40, Math.abs(tx - sx) * 0.5);
    return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`;
}

function NodeCard({
    node,
    selected,
    onPointerDown,
    onClick,
}: {
    node: WfNode;
    selected: boolean;
    onPointerDown: (e: React.PointerEvent) => void;
    onClick: () => void;
}) {
    const meta = nodeMeta(node.type);
    return (
        <div
            onPointerDown={onPointerDown}
            onClick={onClick}
            className={`absolute select-none cursor-grab active:cursor-grabbing rounded-2xl bg-b-surface2 ring-1 ring-inset transition-shadow ${
                selected
                    ? "ring-2 ring-primary-01 shadow-widget"
                    : "ring-s-subtle hover:shadow-widget"
            }`}
            style={{ left: node.x, top: node.y, width: NODE_W, minHeight: NODE_H }}
        >
            <span
                aria-hidden
                className="absolute left-0 top-3 bottom-3 w-1 rounded-full"
                style={{ background: meta.accent }}
            />
            <div className="flex items-start gap-2.5 p-3 pl-4">
                <span
                    className="grid place-items-center size-8 shrink-0 rounded-lg bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04"
                    style={{ fill: meta.accent }}
                >
                    <Icon name={meta.icon} className="size-4 fill-inherit" />
                </span>
                <div className="min-w-0 flex-1">
                    <div className="text-caption text-t-tertiary uppercase tracking-[0.06em]">
                        {meta.label}
                    </div>
                    <div className="text-body-2 text-t-primary truncate leading-tight mt-0.5">
                        {node.label || node.type}
                    </div>
                </div>
                {node.money && (
                    <span
                        title="Money node — gated by Budget + Approval"
                        className="grid place-items-center size-4 shrink-0 rounded-full"
                        style={{ background: "var(--primary-02)" }}
                    >
                        <Icon name="wallet" className="size-2.5 fill-white" />
                    </span>
                )}
            </div>
        </div>
    );
}

export default function WorkflowCanvas({
    def,
    className,
}: {
    def: WfDefinition;
    className?: string;
}) {
    // Local, session-only positions (drag never persists — engine is dormant).
    const initial = useMemo(() => {
        const all = [def.trigger, ...def.nodes];
        const map: Record<string, Pt> = {};
        all.forEach((n) => (map[n.node_id] = { x: n.x, y: n.y }));
        return map;
    }, [def]);

    const [pos, setPos] = useState<Record<string, Pt>>(initial);
    const [pan, setPan] = useState<Pt>({ x: 0, y: 0 });
    const [zoom, setZoom] = useState(1);
    const [selected, setSelected] = useState<string | null>(null);

    const drag = useRef<
        | { kind: "node"; id: string; ox: number; oy: number }
        | { kind: "pan"; ox: number; oy: number }
        | null
    >(null);

    // Keep positions synced if the definition changes (template switch).
    const lastDef = useRef(def.workflow_id);
    if (lastDef.current !== def.workflow_id) {
        lastDef.current = def.workflow_id;
        setPos(initial);
        setPan({ x: 0, y: 0 });
        setZoom(1);
        setSelected(null);
    }

    const allNodes = useMemo(() => [def.trigger, ...def.nodes], [def]);
    const nodeById = useMemo(() => {
        const m: Record<string, WfNode> = {};
        allNodes.forEach((n) => (m[n.node_id] = n));
        return m;
    }, [allNodes]);

    const onNodePointerDown = useCallback(
        (id: string) => (e: React.PointerEvent) => {
            e.stopPropagation();
            (e.target as Element).setPointerCapture?.(e.pointerId);
            const p = pos[id];
            drag.current = { kind: "node", id, ox: e.clientX - p.x * zoom, oy: e.clientY - p.y * zoom };
        },
        [pos, zoom]
    );

    const onBgPointerDown = useCallback(
        (e: React.PointerEvent) => {
            (e.target as Element).setPointerCapture?.(e.pointerId);
            drag.current = { kind: "pan", ox: e.clientX - pan.x, oy: e.clientY - pan.y };
            setSelected(null);
        },
        [pan]
    );

    const onPointerMove = useCallback(
        (e: React.PointerEvent) => {
            const d = drag.current;
            if (!d) return;
            if (d.kind === "pan") {
                setPan({ x: e.clientX - d.ox, y: e.clientY - d.oy });
            } else {
                const nx = (e.clientX - d.ox) / zoom;
                const ny = (e.clientY - d.oy) / zoom;
                setPos((prev) => ({ ...prev, [d.id]: { x: nx, y: ny } }));
            }
        },
        [zoom]
    );

    const onPointerUp = useCallback(() => {
        drag.current = null;
    }, []);

    const edges: WfEdge[] = def.edges;

    function edgeColor(e: WfEdge): string {
        if (e.error) return "var(--primary-03)";
        if (e.when === "true") return "var(--primary-02)";
        if (e.when === "false") return "var(--primary-05)";
        return "var(--color-s-highlight)";
    }

    // Dotted-grid backdrop applied inline (no custom utility class — we must not
    // edit globals.css). The dot colour rides the stroke-subtle token via a soft
    // radial so it reads correctly in both themes.
    const gridStyle: React.CSSProperties = {
        touchAction: "none",
        backgroundImage:
            "radial-gradient(circle, var(--color-s-subtle) 1px, transparent 1px)",
        backgroundSize: `${22 * zoom}px ${22 * zoom}px`,
        backgroundPosition: `${pan.x}px ${pan.y}px`,
    };

    return (
        <div
            className={`relative overflow-hidden rounded-3xl bg-b-surface1 ring-1 ring-inset ring-s-subtle ${
                className || ""
            }`}
            style={gridStyle}
            onPointerDown={onBgPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
        >
            {/* zoom controls */}
            <div className="absolute right-3 top-3 z-20 flex flex-col gap-1 p-1 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle">
                {[
                    { label: "+", fn: () => setZoom((z) => Math.min(1.6, +(z + 0.15).toFixed(2))) },
                    { label: "−", fn: () => setZoom((z) => Math.max(0.5, +(z - 0.15).toFixed(2))) },
                ].map((b) => (
                    <button
                        key={b.label}
                        onClick={(e) => {
                            e.stopPropagation();
                            b.fn();
                        }}
                        className="grid place-items-center size-8 rounded-xl text-h6 text-t-secondary hover:text-t-primary hover:bg-b-surface1 transition-colors"
                    >
                        {b.label}
                    </button>
                ))}
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        setPos(initial);
                        setPan({ x: 0, y: 0 });
                        setZoom(1);
                    }}
                    title="Reset view"
                    className="grid place-items-center size-8 rounded-xl text-t-secondary hover:text-t-primary hover:bg-b-surface1 transition-colors"
                >
                    <Icon name="grid" className="size-4 fill-current" />
                </button>
            </div>

            {/* hint */}
            <div className="absolute left-3 bottom-3 z-20 inline-flex items-center gap-1.5 text-caption text-t-tertiary px-2.5 py-1 rounded-full bg-b-surface2/80 ring-1 ring-s-subtle backdrop-blur-sm">
                <Icon name="dots" className="size-3.5 fill-t-tertiary" />
                Drag to pan · drag a node to move · click to inspect
            </div>

            {/* transformed world */}
            <div
                className="absolute left-0 top-0 origin-top-left"
                style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
            >
                <svg
                    className="absolute left-0 top-0 overflow-visible pointer-events-none"
                    width={1}
                    height={1}
                >
                    <defs>
                        <marker
                            id="wf-arrow"
                            viewBox="0 0 10 10"
                            refX="8"
                            refY="5"
                            markerWidth="7"
                            markerHeight="7"
                            orient="auto-start-reverse"
                        >
                            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-s-highlight)" />
                        </marker>
                    </defs>
                    {edges.map((e, i) => {
                        const a = pos[e.from];
                        const b = pos[e.to];
                        if (!a || !b) return null;
                        const col = edgeColor(e);
                        return (
                            <g key={i}>
                                <path
                                    d={edgePath(a, b)}
                                    fill="none"
                                    stroke={col}
                                    strokeWidth={2}
                                    strokeOpacity={e.when || e.error ? 0.85 : 0.55}
                                    markerEnd="url(#wf-arrow)"
                                />
                                {(e.when || e.error) && (
                                    <text
                                        x={(a.x + NODE_W + b.x) / 2}
                                        y={(a.y + b.y) / 2 + NODE_H / 2 - 8}
                                        textAnchor="middle"
                                        style={{ fill: col, fontSize: 10, fontWeight: 600 }}
                                    >
                                        {e.error ? "on error" : e.when}
                                    </text>
                                )}
                            </g>
                        );
                    })}
                </svg>

                {allNodes.map((n) => (
                    <NodeCard
                        key={n.node_id}
                        node={{ ...n, ...pos[n.node_id] }}
                        selected={selected === n.node_id}
                        onPointerDown={onNodePointerDown(n.node_id)}
                        onClick={() => setSelected(n.node_id)}
                    />
                ))}
            </div>

            {/* inspector flyout */}
            {selected && nodeById[selected] && (
                <NodeInspector node={nodeById[selected]} onClose={() => setSelected(null)} />
            )}
        </div>
    );
}

function NodeInspector({ node, onClose }: { node: WfNode; onClose: () => void }) {
    const meta = nodeMeta(node.type);
    const cfg = node.config || {};
    const entries = Object.entries(cfg);
    return (
        <div
            className="absolute right-3 bottom-12 z-30 w-72 max-w-[calc(100%-1.5rem)] rounded-2xl bg-b-surface2 ring-1 ring-s-subtle shadow-depth p-4 rise-in"
            onPointerDown={(e) => e.stopPropagation()}
        >
            <div className="flex items-start gap-2.5">
                <span
                    className="grid place-items-center size-9 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04"
                    style={{ fill: meta.accent }}
                >
                    <Icon name={meta.icon} className="size-4.5 fill-inherit" />
                </span>
                <div className="min-w-0 flex-1">
                    <div className="text-body-2 text-t-primary truncate">{node.label || node.type}</div>
                    <div className="text-caption text-t-tertiary">{meta.label} node</div>
                </div>
                <button
                    onClick={onClose}
                    className="shrink-0 grid place-items-center size-6 rounded-full text-t-tertiary hover:text-t-primary hover:bg-b-surface1"
                >
                    <Icon name="close" className="size-3.5 fill-current" />
                </button>
            </div>
            <p className="text-caption text-t-secondary mt-3">{meta.blurb}</p>
            <div className="flex flex-wrap gap-1.5 mt-3">
                {node.money && <Badge variant="success" dot>money</Badge>}
                {node.role && <Badge variant="info">{node.role}</Badge>}
                <Badge variant="neutral">{meta.gate}</Badge>
            </div>
            {entries.length > 0 && (
                <div className="mt-3 pt-3 border-t border-s-subtle space-y-1.5">
                    {entries.slice(0, 5).map(([k, v]) => (
                        <div key={k} className="flex items-baseline justify-between gap-3">
                            <span className="text-caption text-t-tertiary font-mono">{k}</span>
                            <span className="text-caption text-t-secondary text-right truncate max-w-[10rem]">
                                {typeof v === "object" ? JSON.stringify(v) : String(v)}
                            </span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
