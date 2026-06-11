"use client";

// Read-only workflow preview — the SAME @xyflow/react renderer as the live editor,
// but non-interactive. Used by the Templates tab so the whole app has ONE canvas
// renderer (spec §E) and the old dependency-free SVG _canvas.tsx is retired.
//
// Reuses fromDefinition + the WfNodeView custom node + the editor's token styles
// (the scoped <style> the editor injects is global, so .wf-canvas rules apply here
// too — we add a thin local <style> only for the read-only minimap container).

import { useMemo } from "react";
import {
    ReactFlow,
    ReactFlowProvider,
    Background,
    BackgroundVariant,
    Controls,
    type Edge,
    type Node,
    type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { fromDefinition, RF_NODE_TYPE, type WfDefinition, type RFEdge } from "./_lib";
import WfNodeView from "./_nodes/WfNodeView";

const nodeTypes: NodeTypes = { [RF_NODE_TYPE]: WfNodeView };

// Mirror the editor's edge styling (kept local so this file is self-contained).
function styleEdge(e: RFEdge): Edge {
    const when = (e.sourceHandle as string | null) || e.data?.when;
    let stroke = "var(--color-s-highlight)";
    if (e.data?.error) stroke = "var(--primary-03)";
    else if (when === "true") stroke = "var(--primary-02)";
    else if (when === "false") stroke = "var(--primary-05)";
    const label = e.data?.error ? "on error" : when === "true" || when === "false" ? when : undefined;
    return {
        ...e,
        type: "smoothstep",
        animated: !!when || !!e.data?.error,
        label,
        labelStyle: { fill: stroke, fontSize: 10, fontWeight: 600 },
        labelBgStyle: { fill: "var(--b-surface1)", fillOpacity: 0.85 },
        style: { stroke, strokeWidth: 2 },
        selectable: false,
        focusable: false,
    } as Edge;
}

function PreviewInner({ def, className }: { def: WfDefinition; className?: string }) {
    const { nodes, edges } = useMemo(() => {
        const rf = fromDefinition(def);
        return {
            nodes: rf.nodes as unknown as Node[],
            edges: (rf.edges as RFEdge[]).map(styleEdge),
        };
    }, [def]);

    return (
        <div
            className={`wf-canvas relative rounded-3xl ring-1 ring-inset ring-s-subtle overflow-hidden ${
                className || ""
            }`}
        >
            <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView
                proOptions={{ hideAttribution: true }}
                // Read-only: no edits, no connections, no selection mutations.
                nodesDraggable={false}
                nodesConnectable={false}
                elementsSelectable={false}
                edgesFocusable={false}
                panOnDrag
                zoomOnScroll={false}
                minZoom={0.3}
                maxZoom={1.5}
            >
                <Background variant={BackgroundVariant.Dots} gap={22} size={1.4} />
                <Controls showInteractive={false} showZoom={false} />
            </ReactFlow>
        </div>
    );
}

export default function WorkflowMiniMap({
    def,
    className,
}: {
    def: WfDefinition;
    className?: string;
}) {
    return (
        <ReactFlowProvider>
            <PreviewInner def={def} className={className} />
        </ReactFlowProvider>
    );
}
