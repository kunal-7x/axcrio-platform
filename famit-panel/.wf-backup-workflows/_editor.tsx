"use client";

// The REAL node-based Workflow editor — @xyflow/react (React Flow v12, MIT).
//
// Replaces the read-only SVG preview with a live editor: drag nodes from the
// palette onto the canvas, connect handles into edges, click a node to edit its
// config in the right-hand inspector flyout, and Save / Validate / Publish / Run
// the graph against the existing /workflows router. The canvas state is RF's
// Node[]/Edge[]; the persisted + executed format is the DSL JSON (WfDefinition) —
// mapped losslessly both ways by toDefinition/fromDefinition in _lib.ts. The
// canvas NEVER compiles or runs anything; all safety (dominator, budget hold,
// approval step-up, DND, bulk cap) is enforced server-side. When the engine is
// dormant (router 404s) every mutation degrades to a premium toast and the canvas
// stays fully editable locally — zero change needed at the wiring cutover.
//
// REUSE-ONLY: composes the ported Core_2 components (Card/Button/Field/Select/
// Switch/Modal/Badge/Icon) + Signal tokens. React Flow is the one new dep. We do
// NOT touch shared components/ or globals.css; RF's stylesheet is imported here.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
    ReactFlow,
    ReactFlowProvider,
    Background,
    BackgroundVariant,
    Controls,
    MiniMap,
    addEdge,
    useNodesState,
    useEdgesState,
    useReactFlow,
    type Connection,
    type Edge,
    type Node,
    type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import Icon from "@/components/Icon";
import {
    NODE_GROUPS,
    nodeMeta,
    RF_NODE_TYPE,
    newNodeId,
    fromDefinition,
    toDefinition,
    isValidWfConnection,
    saveWorkflow,
    validateWorkflow,
    publishWorkflow,
    runWorkflow,
    type WfNodeType,
    type WfNodeData,
    type WfDefinition,
    type RFNode,
    type RFEdge,
} from "./_lib";
import WfNodeView from "./_nodes/WfNodeView";
import NodeInspector from "./_nodes/NodeInspector";

const nodeTypes: NodeTypes = { [RF_NODE_TYPE]: WfNodeView };
const DRAG_MIME = "application/wf-node-type";

// Map a DSL edge label / error flag to a token-coloured RF edge.
function styleEdge(e: RFEdge): RFEdge {
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
    } as RFEdge;
}

type ToolbarState = "idle" | "saving" | "validating" | "publishing" | "running";

function EditorInner({
    initialDef,
    workflowId,
    writable,
    onToast,
}: {
    initialDef: WfDefinition;
    workflowId: string | null;
    writable: boolean;
    onToast: (msg: string, type?: "success" | "error") => void;
}) {
    const init = useMemo(() => fromDefinition(initialDef), [initialDef]);
    const [nodes, setNodes, onNodesChange] = useNodesState<Node>(init.nodes as unknown as Node[]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
        (init.edges as unknown as RFEdge[]).map(styleEdge) as unknown as Edge[]
    );
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [badNodes, setBadNodes] = useState<Set<string>>(new Set());
    const [busy, setBusy] = useState<ToolbarState>("idle");
    const rfWrap = useRef<HTMLDivElement | null>(null);
    const { screenToFlowPosition } = useReactFlow();

    // Reset the graph when the loaded definition changes (template "Edit", new).
    const lastDefId = useRef(initialDef.workflow_id);
    useEffect(() => {
        if (lastDefId.current !== initialDef.workflow_id) {
            lastDefId.current = initialDef.workflow_id;
            const next = fromDefinition(initialDef);
            setNodes(next.nodes as unknown as Node[]);
            setEdges((next.edges as unknown as RFEdge[]).map(styleEdge) as unknown as Edge[]);
            setSelectedId(null);
            setBadNodes(new Set());
        }
    }, [initialDef, setNodes, setEdges]);

    const typeOf = useCallback(
        (id: string): WfNodeType | undefined =>
            (nodes.find((n) => n.id === id)?.data as WfNodeData | undefined)?.wfType,
        [nodes]
    );

    /* --------------------------------------------------- connection handling */

    const isValidConnection = useCallback(
        (c: Connection | Edge) =>
            isValidWfConnection(typeOf(c.source!), typeOf(c.target!), c.source === c.target),
        [typeOf]
    );

    const onConnect = useCallback(
        (c: Connection) => {
            if (!isValidWfConnection(typeOf(c.source!), typeOf(c.target!), c.source === c.target)) {
                onToast("That connection isn't allowed.", "error");
                return;
            }
            const when = c.sourceHandle === "true" || c.sourceHandle === "false" ? c.sourceHandle : undefined;
            const raw: RFEdge = {
                id: `e_${c.source}_${c.target}_${Date.now().toString(36)}`,
                source: c.source!,
                target: c.target!,
                sourceHandle: c.sourceHandle ?? null,
                data: { when: when as "true" | "false" | undefined },
            };
            setEdges((eds) => addEdge(styleEdge(raw) as unknown as Edge, eds));
        },
        [typeOf, setEdges, onToast]
    );

    /* ------------------------------------------------------- palette drag-drop */

    const onDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
    }, []);

    const onDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            const wfType = e.dataTransfer.getData(DRAG_MIME) as WfNodeType;
            if (!wfType) return;
            // A workflow has exactly one trigger — don't allow dropping a second.
            if (wfType === "trigger" && nodes.some((n) => (n.data as WfNodeData).wfType === "trigger")) {
                onToast("A workflow can only have one Trigger.", "error");
                return;
            }
            const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
            const meta = nodeMeta(wfType);
            const node: RFNode = {
                id: newNodeId(wfType),
                type: RF_NODE_TYPE,
                position,
                data: { wfType, label: meta.label, config: {}, money: meta.money },
            };
            setNodes((nds) => nds.concat(node as unknown as Node));
            setSelectedId(node.id);
        },
        [nodes, screenToFlowPosition, setNodes, onToast]
    );

    /* ------------------------------------------------- inspector read / write */

    const selectedData = useMemo(() => {
        const n = nodes.find((x) => x.id === selectedId);
        return n ? (n.data as WfNodeData) : null;
    }, [nodes, selectedId]);

    const patchSelected = useCallback(
        (next: WfNodeData) => {
            setNodes((nds) =>
                nds.map((n) => (n.id === selectedId ? { ...n, data: next as unknown as Node["data"] } : n))
            );
        },
        [selectedId, setNodes]
    );

    const deleteSelected = useCallback(() => {
        if (!selectedId) return;
        const sel = nodes.find((n) => n.id === selectedId);
        if (sel && (sel.data as WfNodeData).wfType === "trigger") {
            onToast("The Trigger can't be deleted — every workflow needs one entry point.", "error");
            return;
        }
        setNodes((nds) => nds.filter((n) => n.id !== selectedId));
        setEdges((eds) => eds.filter((e) => e.source !== selectedId && e.target !== selectedId));
        setSelectedId(null);
    }, [selectedId, nodes, setNodes, setEdges, onToast]);

    // Paint validation-flagged nodes red (ring) by merging a className.
    const styledNodes = useMemo(
        () =>
            nodes.map((n) =>
                badNodes.has(n.id)
                    ? { ...n, className: "wf-node-invalid", selected: n.id === selectedId }
                    : { ...n, className: undefined, selected: n.id === selectedId }
            ),
        [nodes, badNodes, selectedId]
    );

    /* --------------------------------------------------------- the toolbar ops */

    const currentDef = useCallback(
        (): WfDefinition =>
            toDefinition(nodes as unknown as RFNode[], edges as unknown as RFEdge[], {
                workflow_id: workflowId || initialDef.workflow_id,
                name: initialDef.name,
                version: initialDef.version,
                status: initialDef.status,
                industry_pack: initialDef.industry_pack,
                guards: initialDef.guards,
                schema_version: initialDef.schema_version,
            }),
        [nodes, edges, workflowId, initialDef]
    );

    async function doValidate(): Promise<boolean> {
        const id = workflowId || initialDef.workflow_id;
        setBusy("validating");
        try {
            const res = await validateWorkflow(id, currentDef());
            if (res.ok) {
                setBadNodes(new Set());
                onToast("Looks good — every money node is governed.");
                return true;
            }
            setBadNodes(new Set(res.node_ids || []));
            onToast(res.message || `Validation failed: ${res.code || "graph invalid"}`, "error");
            return false;
        } catch (e) {
            onToast(e instanceof Error ? e.message : "Couldn't validate", "error");
            return false;
        } finally {
            setBusy("idle");
        }
    }

    async function doSave() {
        const id = workflowId || initialDef.workflow_id;
        setBusy("saving");
        try {
            await saveWorkflow(id, currentDef());
            onToast("Workflow saved.");
        } catch (e) {
            onToast(e instanceof Error ? e.message : "Couldn't save", "error");
        } finally {
            setBusy("idle");
        }
    }

    async function doPublish() {
        const ok = await doValidate();
        if (!ok) return;
        const id = workflowId || initialDef.workflow_id;
        setBusy("publishing");
        try {
            await publishWorkflow(id);
            onToast("Published — the workflow is live.");
        } catch (e) {
            onToast(e instanceof Error ? e.message : "Couldn't publish", "error");
        } finally {
            setBusy("idle");
        }
    }

    async function doRun() {
        const id = workflowId || initialDef.workflow_id;
        setBusy("running");
        try {
            await runWorkflow(id);
            onToast("Run started — watch it in the Runs tab.");
        } catch (e) {
            onToast(e instanceof Error ? e.message : "Couldn't run", "error");
        } finally {
            setBusy("idle");
        }
    }

    const ToolbarBtn = ({
        icon,
        label,
        onClick,
        primary,
        loading,
    }: {
        icon: string;
        label: string;
        onClick: () => void;
        primary?: boolean;
        loading?: boolean;
    }) => (
        <button
            onClick={onClick}
            disabled={!writable || busy !== "idle"}
            className={`inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full text-button transition-all active:scale-[0.98] disabled:opacity-50 ${
                primary
                    ? "bg-primary-01/12 text-primary-01 fill-primary-01 hover:bg-primary-01/20"
                    : "border border-s-subtle text-t-secondary fill-t-secondary bg-b-surface2 hover:border-s-highlight hover:text-t-primary"
            }`}
        >
            <Icon name={icon} className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
            {label}
        </button>
    );

    return (
        <div className="space-y-3">
            {/* toolbar */}
            <div className="flex items-center gap-2 flex-wrap">
                <ToolbarBtn icon="check-circle" label="Validate" onClick={doValidate} loading={busy === "validating"} />
                <ToolbarBtn icon="check" label={busy === "saving" ? "Saving…" : "Save"} onClick={doSave} loading={busy === "saving"} />
                <ToolbarBtn icon="layers" label={busy === "publishing" ? "Publishing…" : "Publish"} onClick={doPublish} loading={busy === "publishing"} />
                <ToolbarBtn icon="send" label={busy === "running" ? "Running…" : "Run"} onClick={doRun} primary loading={busy === "running"} />
                <span className="ml-auto inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                    <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                    {nodes.length} nodes · {edges.length} edges
                </span>
            </div>

            <div className="flex gap-3 max-xl:flex-col">
                {/* palette rail */}
                <div className="w-64 max-xl:w-full shrink-0">
                    <div className="card !mb-0 p-3 max-lg:p-2">
                        <div className="flex items-center gap-1.5 px-1 pb-2 text-caption text-t-tertiary">
                            <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                            Drag a node onto the canvas
                        </div>
                        <div className="space-y-4">
                            {NODE_GROUPS.map((grp) => (
                                <div key={grp.group}>
                                    <div className="text-overline text-t-tertiary px-1 mb-2">{grp.group}</div>
                                    <div className="space-y-1.5">
                                        {grp.types.map((t) => {
                                            const m = nodeMeta(t);
                                            return (
                                                <div
                                                    key={t}
                                                    draggable
                                                    onDragStart={(e) => {
                                                        e.dataTransfer.setData(DRAG_MIME, t);
                                                        e.dataTransfer.effectAllowed = "move";
                                                    }}
                                                    className="lift group flex items-center gap-2.5 p-2.5 rounded-xl bg-b-surface2 ring-1 ring-s-subtle ring-inset cursor-grab active:cursor-grabbing dark:bg-shade-04/30"
                                                    title={m.blurb}
                                                >
                                                    <span
                                                        className="grid place-items-center size-8 shrink-0 rounded-lg bg-b-surface1 ring-1 ring-s-subtle dark:bg-shade-04"
                                                        style={{ fill: m.accent }}
                                                    >
                                                        <Icon name={m.icon} className="size-4 fill-inherit" />
                                                    </span>
                                                    <div className="min-w-0 flex-1">
                                                        <div className="text-body-2 text-t-primary truncate">{m.label}</div>
                                                        <div className="text-caption text-t-tertiary truncate">{m.gate}</div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* canvas */}
                <div className="flex-1 min-w-0">
                    <div
                        ref={rfWrap}
                        className="wf-canvas relative rounded-3xl ring-1 ring-inset ring-s-subtle overflow-hidden h-[560px] max-sm:h-[420px]"
                        onDrop={onDrop}
                        onDragOver={onDragOver}
                    >
                        <ReactFlow
                            nodes={styledNodes}
                            edges={edges}
                            onNodesChange={onNodesChange}
                            onEdgesChange={onEdgesChange}
                            onConnect={onConnect}
                            isValidConnection={isValidConnection}
                            nodeTypes={nodeTypes}
                            onNodeClick={(_, n) => setSelectedId(n.id)}
                            onPaneClick={() => setSelectedId(null)}
                            fitView
                            proOptions={{ hideAttribution: true }}
                            defaultEdgeOptions={{ type: "smoothstep" }}
                            minZoom={0.4}
                            maxZoom={1.75}
                        >
                            <Background variant={BackgroundVariant.Dots} gap={22} size={1.4} />
                            <Controls showInteractive={false} />
                            <MiniMap pannable zoomable nodeColor={() => "#9ca3af"} nodeStrokeWidth={0} maskColor="rgba(0,0,0,0.08)" />
                        </ReactFlow>

                        {nodes.length <= 1 && (
                            <div className="pointer-events-none absolute inset-0 grid place-items-center">
                                <div className="text-center px-6">
                                    <div className="text-body-2 text-t-secondary">Drag nodes from the left to start</div>
                                    <div className="text-caption text-t-tertiary mt-1">
                                        Connect a node&apos;s right dot to another node&apos;s left dot to wire the path.
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <NodeInspector
                data={selectedData}
                onPatch={patchSelected}
                onDelete={deleteSelected}
                onClose={() => setSelectedId(null)}
            />
        </div>
    );
}

// Public wrapper — supplies the RF context provider + scopes our token overrides.
export default function WorkflowEditor(props: {
    initialDef: WfDefinition;
    workflowId: string | null;
    writable: boolean;
    onToast: (msg: string, type?: "success" | "error") => void;
}) {
    return (
        <ReactFlowProvider>
            {/* Scoped RF css-var overrides -> our Signal tokens (no globals.css edit). */}
            <style>{`
                .wf-canvas { background: var(--b-surface1); }
                .wf-canvas .react-flow__pane { cursor: grab; }
                .wf-canvas .react-flow__background { color: var(--color-s-subtle); }
                .wf-canvas .react-flow__edge-path { stroke: var(--color-s-highlight); }
                .wf-canvas .react-flow__handle { background: var(--b-surface1); border-color: var(--primary-01); }
                .wf-canvas .react-flow__node.wf-node-invalid > div {
                    box-shadow: 0 0 0 2px var(--primary-03);
                    border-radius: 1rem;
                }
                .wf-canvas .react-flow__controls {
                    box-shadow: none;
                    border: 1px solid var(--color-s-subtle);
                    border-radius: 0.75rem;
                    overflow: hidden;
                    background: var(--b-surface2);
                }
                .wf-canvas .react-flow__controls-button {
                    background: var(--b-surface2);
                    border-bottom: 1px solid var(--color-s-subtle);
                    fill: var(--color-t-secondary);
                }
                .wf-canvas .react-flow__controls-button:hover { background: var(--b-surface1); }
                .wf-canvas .react-flow__minimap {
                    background: var(--b-surface2);
                    border: 1px solid var(--color-s-subtle);
                    border-radius: 0.75rem;
                }
                .wf-canvas .react-flow__attribution { display: none; }
            `}</style>
            <EditorInner {...props} />
        </ReactFlowProvider>
    );
}
