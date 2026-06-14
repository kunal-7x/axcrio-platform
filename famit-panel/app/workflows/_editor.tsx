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
import { createPortal } from "react-dom";
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
    newNodeData,
    RF_NODE_TYPE,
    newNodeId,
    fromDefinition,
    toDefinition,
    isValidWfConnection,
    upsertWorkflow,
    saveDraftLocal,
    validateWorkflow,
    publishWorkflow,
    runWorkflow,
    STARTER_CALL_TEMPLATE,
    TEMPLATES,
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
    engineLive,
    onToast,
    onRename,
}: {
    initialDef: WfDefinition;
    workflowId: string | null;
    writable: boolean;
    engineLive?: boolean;
    onToast: (msg: string, type?: "success" | "error") => void;
    onRename?: (name: string) => void;
}) {
    const init = useMemo(() => fromDefinition(initialDef), [initialDef]);
    const [nodes, setNodes, onNodesChange] = useNodesState<Node>(init.nodes as unknown as Node[]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(
        (init.edges as unknown as RFEdge[]).map(styleEdge) as unknown as Edge[]
    );
    const [selectedId, setSelectedId] = useState<string | null>(null);
    const [badNodes, setBadNodes] = useState<Set<string>>(new Set());
    const [busy, setBusy] = useState<ToolbarState>("idle");
    // Inline run status shown after a Run click (spec §D) — shown until dismissed.
    const [runStatus, setRunStatus] = useState<{
        ok: boolean;
        run_id?: string;
        status?: string;
        msg: string;
    } | null>(null);
    // Template picker state — controls the small template dropdown in the toolbar.
    const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
    const [fullscreen, setFullscreen] = useState(false);
    // The editable workflow name (spec §C). Seeded from the loaded def; flushed up
    // to the page via onRename so a from-scratch workflow can be named before save.
    const [name, setName] = useState(initialDef.name);
    // The AUTHORITATIVE server workflow id. Starts as the client id; the first
    // server save (upsertWorkflow) creates the row and ADOPTS the server-minted id,
    // which every later validate / publish / run must target. Persisting it in state
    // means a from-scratch graph becomes publishable + runnable without a reload.
    const [serverId, setServerId] = useState<string>(workflowId || initialDef.workflow_id);
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
            setName(initialDef.name);
            // A different graph was loaded — reset the adopted server id to its id.
            setServerId(workflowId || initialDef.workflow_id);
        }
    }, [initialDef, workflowId, setNodes, setEdges]);

    // Esc exits fullscreen (spec §A). Bound only while the overlay is open.
    useEffect(() => {
        if (!fullscreen) return;
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") setFullscreen(false);
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [fullscreen]);

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

    /* ----------------------------------------- add-node (click + drop share this) */

    // Single source of truth for inserting a node (spec §B). `screenPos` is the
    // drop pointer in SCREEN coords; when omitted (click-to-add) we drop at the
    // visible canvas centre with a small stepped offset so repeats don't stack.
    const addSeq = useRef(0);
    const addNode = useCallback(
        (wfType: WfNodeType, screenPos?: { x: number; y: number }) => {
            // A workflow has exactly one trigger — don't allow a second.
            if (wfType === "trigger" && nodes.some((n) => (n.data as WfNodeData).wfType === "trigger")) {
                onToast("A workflow can only have one Trigger.", "error");
                return;
            }
            let position: { x: number; y: number };
            if (screenPos) {
                position = screenToFlowPosition(screenPos);
            } else {
                const rect = rfWrap.current?.getBoundingClientRect();
                const cx = rect ? rect.left + rect.width / 2 : window.innerWidth / 2;
                const cy = rect ? rect.top + rect.height / 2 : window.innerHeight / 2;
                const k = addSeq.current % 6;
                position = screenToFlowPosition({ x: cx + k * 28, y: cy + k * 28 });
            }
            addSeq.current += 1;
            const node: RFNode = {
                id: newNodeId(wfType),
                type: RF_NODE_TYPE,
                position,
                data: newNodeData(wfType),
            };
            setNodes((nds) => nds.concat(node as unknown as Node));
            setSelectedId(node.id);
        },
        [nodes, screenToFlowPosition, setNodes, onToast]
    );

    const onDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
    }, []);

    const onDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            const wfType = e.dataTransfer.getData(DRAG_MIME) as WfNodeType;
            if (!wfType) return;
            addNode(wfType, { x: e.clientX, y: e.clientY });
        },
        [addNode]
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
                workflow_id: serverId,
                name: (name || "").trim() || "Untitled workflow",
                version: initialDef.version,
                status: initialDef.status,
                industry_pack: initialDef.industry_pack,
                guards: initialDef.guards,
                schema_version: initialDef.schema_version,
            }),
        [nodes, edges, serverId, initialDef, name]
    );

    // Ensure the workflow exists server-side and return its authoritative id. Used
    // by validate / publish / run so a brand-new from-scratch graph is created +
    // saved before those ops (which require a pre-existing row) run against it.
    const ensureSaved = useCallback(async (): Promise<string> => {
        const def = currentDef();
        saveDraftLocal(def);
        const { workflow_id } = await upsertWorkflow(serverId, def);
        if (workflow_id !== serverId) setServerId(workflow_id);
        return workflow_id;
    }, [currentDef, serverId]);

    // Validate accepts the draft in the BODY, so it works on the in-memory graph
    // without needing the row created first — true even before a save.
    async function doValidate(): Promise<boolean> {
        setBusy("validating");
        try {
            const res = await validateWorkflow(serverId, currentDef());
            if (res.ok) {
                setBadNodes(new Set());
                onToast("Looks good — every money node is governed.");
                return true;
            }
            // The live validator returns { errors:[{code,node_ids,msg}] }; the older
            // shape returns { code, node_ids, message }. Surface whichever is present.
            const errs = (res as { errors?: { code?: string; node_ids?: string[]; msg?: string }[] }).errors;
            const bad = new Set<string>();
            let msg = res.message || "";
            if (Array.isArray(errs) && errs.length) {
                errs.forEach((e) => (e.node_ids || []).forEach((n) => bad.add(n)));
                msg = errs.map((e) => e.msg || e.code).filter(Boolean).join("; ");
            } else {
                (res.node_ids || []).forEach((n) => bad.add(n));
            }
            setBadNodes(bad);
            onToast(msg || `Validation failed: ${res.code || "graph invalid"}`, "error");
            return false;
        } catch (e) {
            onToast(e instanceof Error ? e.message : "Couldn't validate", "error");
            return false;
        } finally {
            setBusy("idle");
        }
    }

    async function doSave() {
        // Always persist a local draft first so a from-scratch graph survives a
        // reload even before the engine is mounted (spec §F).
        saveDraftLocal(currentDef());
        if (!engineLive) {
            onToast("Saved on this device — the engine isn't live yet, so it'll sync once provisioned.");
            return;
        }
        setBusy("saving");
        try {
            // Create the row (adopting the server id) on first save, then PUT.
            await ensureSaved();
            onToast("Workflow saved.");
        } catch (e) {
            // Server refused but the local draft is safe — be honest, not alarming.
            onToast(
                e instanceof Error && /not configured|not available/i.test(e.message)
                    ? "Saved on this device — the engine isn't live yet."
                    : e instanceof Error
                    ? e.message
                    : "Couldn't save",
                "error"
            );
        } finally {
            setBusy("idle");
        }
    }

    async function doPublish() {
        const ok = await doValidate();
        if (!ok) return;
        setBusy("publishing");
        try {
            // Publish freezes the STORED draft, so the row must exist + hold the
            // current graph first. ensureSaved creates/updates it, returning the id.
            const id = await ensureSaved();
            const res = await publishWorkflow(id);
            const pubErrs = (res as { ok?: boolean; errors?: { msg?: string; code?: string }[] }).errors;
            if (res && res.ok === false && Array.isArray(pubErrs)) {
                onToast(pubErrs.map((e) => e.msg || e.code).filter(Boolean).join("; ") || "Couldn't publish", "error");
                return;
            }
            onToast("Published — the workflow is live.");
        } catch (e) {
            onToast(e instanceof Error ? e.message : "Couldn't publish", "error");
        } finally {
            setBusy("idle");
        }
    }

    async function doRun() {
        // Don't imply a run happened when the engine is dormant (spec §D).
        if (!engineLive) {
            onToast("Engine not live yet — your workflow is saved, but runs start once it's provisioned.", "error");
            return;
        }
        setRunStatus(null);
        setBusy("running");
        try {
            // Run executes the PUBLISHED version. Save + publish first so a
            // from-scratch graph runs in one click; the backend runs it in-process.
            const ok = await doValidateInline();
            if (!ok) return;
            const id = await ensureSaved();
            const pub = await publishWorkflow(id);
            const pubErrs = (pub as { ok?: boolean; errors?: { msg?: string; code?: string }[] }).errors;
            if (pub && pub.ok === false && Array.isArray(pubErrs)) {
                const msg = pubErrs.map((e) => e.msg || e.code).filter(Boolean).join("; ") || "Couldn't publish before run";
                setRunStatus({ ok: false, msg });
                onToast(msg, "error");
                return;
            }
            const res = await runWorkflow(id);
            const rr = res as { ok?: boolean; run_id?: string; status?: string; reason?: string };
            if (rr && rr.ok === false) {
                const msg = rr.reason ? `Run blocked: ${rr.reason.replace(/_/g, " ")}` : "Couldn't run";
                setRunStatus({ ok: false, msg });
                onToast(msg, "error");
                return;
            }
            const statusLabel = rr.status ? rr.status.replace(/_/g, " ") : "queued";
            const msg = `Run started — ${statusLabel}`;
            setRunStatus({ ok: true, run_id: rr.run_id, status: statusLabel, msg });
            onToast(`${msg}. Watch it in the Runs tab.`);
        } catch (e) {
            const msg = e instanceof Error ? e.message : "Couldn't run";
            setRunStatus({ ok: false, msg });
            onToast(msg, "error");
        } finally {
            setBusy("idle");
        }
    }

    // Validate without toggling the toolbar busy state (used inside doRun, which
    // already owns the "running" state) — returns ok and paints bad nodes.
    async function doValidateInline(): Promise<boolean> {
        try {
            const res = await validateWorkflow(serverId, currentDef());
            if (res.ok) {
                setBadNodes(new Set());
                return true;
            }
            const errs = (res as { errors?: { node_ids?: string[]; msg?: string; code?: string }[] }).errors;
            const bad = new Set<string>();
            let msg = res.message || "";
            if (Array.isArray(errs) && errs.length) {
                errs.forEach((e) => (e.node_ids || []).forEach((n) => bad.add(n)));
                msg = errs.map((e) => e.msg || e.code).filter(Boolean).join("; ");
            } else {
                (res.node_ids || []).forEach((n) => bad.add(n));
            }
            setBadNodes(bad);
            onToast(msg || "Fix validation before running.", "error");
            return false;
        } catch (e) {
            onToast(e instanceof Error ? e.message : "Couldn't validate before run", "error");
            return false;
        }
    }

    const ToolbarBtn = ({
        icon,
        label,
        onClick,
        primary,
        loading,
        disabled,
        title,
    }: {
        icon: string;
        label: string;
        onClick: () => void;
        primary?: boolean;
        loading?: boolean;
        disabled?: boolean;
        title?: string;
    }) => (
        <button
            onClick={onClick}
            disabled={!writable || busy !== "idle" || disabled}
            title={title}
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

    // The editor body — rendered inline in the card OR portaled into a fullscreen
    // overlay (spec §A). `tall` makes the canvas fill the screen in fullscreen.
    const body = (
        <div className={fullscreen ? "flex h-full flex-col gap-3" : "space-y-3"}>
            {/* toolbar */}
            <div className="flex items-center gap-2 flex-wrap shrink-0">
                {/* editable workflow name (spec §C) */}
                <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    onBlur={() => onRename?.((name || "").trim() || "Untitled workflow")}
                    disabled={!writable}
                    placeholder="Untitled workflow"
                    aria-label="Workflow name"
                    className="h-9 min-w-0 max-w-[16rem] flex-1 px-3 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-button text-t-primary outline-none transition-colors hover:ring-s-highlight focus:ring-primary-01/50 disabled:opacity-60 placeholder:text-t-tertiary"
                />
                {/* Load template — one-click template picker */}
                <div className="relative">
                    <button
                        onClick={() => setTemplatePickerOpen((v) => !v)}
                        disabled={!writable || busy !== "idle"}
                        title="Load a pre-built template onto the canvas"
                        className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary fill-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary active:scale-[0.98] disabled:opacity-50"
                    >
                        <Icon name="layers" className="size-4 fill-current" />
                        Load template
                    </button>
                    {templatePickerOpen && (
                        <>
                            {/* backdrop */}
                            <div
                                className="fixed inset-0 z-10"
                                onClick={() => setTemplatePickerOpen(false)}
                            />
                            {/* dropdown */}
                            <div className="absolute left-0 top-11 z-20 w-64 rounded-2xl bg-b-surface1 ring-1 ring-s-subtle shadow-widget overflow-hidden">
                                <div className="px-3 pt-3 pb-1 text-caption text-t-tertiary uppercase tracking-[0.06em]">
                                    Templates
                                </div>
                                {/* Working starter template — the backend-verified one-click flow */}
                                <button
                                    onClick={() => {
                                        onRename?.(STARTER_CALL_TEMPLATE.name);
                                        // Reset to the starter template graph
                                        const next = fromDefinition(STARTER_CALL_TEMPLATE);
                                        setNodes(next.nodes as unknown as Node[]);
                                        setEdges((next.edges as unknown as RFEdge[]).map(styleEdge) as unknown as Edge[]);
                                        setSelectedId(null);
                                        setBadNodes(new Set());
                                        setName(STARTER_CALL_TEMPLATE.name);
                                        setServerId(STARTER_CALL_TEMPLATE.workflow_id);
                                        setTemplatePickerOpen(false);
                                        onToast("Template loaded — wire your leads and hit Run.");
                                    }}
                                    className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left hover:bg-b-surface2 transition-colors"
                                >
                                    <span className="grid place-items-center size-8 shrink-0 rounded-lg bg-b-surface2 ring-1 ring-s-subtle fill-primary-01 mt-0.5">
                                        <Icon name="mobile" className="size-4 fill-inherit" />
                                    </span>
                                    <div>
                                        <div className="text-body-2 text-t-primary">{STARTER_CALL_TEMPLATE.name}</div>
                                        <div className="text-caption text-t-tertiary">New lead → AI calls them</div>
                                    </div>
                                </button>
                                <div className="mx-3 h-px bg-s-subtle" />
                                {TEMPLATES.slice(0, 4).map((t) => (
                                    <button
                                        key={t.template_id}
                                        onClick={() => {
                                            const next = fromDefinition(t.definition);
                                            setNodes(next.nodes as unknown as Node[]);
                                            setEdges((next.edges as unknown as RFEdge[]).map(styleEdge) as unknown as Edge[]);
                                            setSelectedId(null);
                                            setBadNodes(new Set());
                                            setName(t.name);
                                            setServerId(t.definition.workflow_id);
                                            onRename?.(t.name);
                                            setTemplatePickerOpen(false);
                                            onToast(`"${t.name}" loaded onto the canvas.`);
                                        }}
                                        className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left hover:bg-b-surface2 transition-colors"
                                    >
                                        <span className="grid place-items-center size-8 shrink-0 rounded-lg bg-b-surface2 ring-1 ring-s-subtle fill-primary-01 mt-0.5">
                                            <Icon name={t.icon} className="size-4 fill-inherit" />
                                        </span>
                                        <div>
                                            <div className="text-body-2 text-t-primary">{t.name}</div>
                                            <div className="text-caption text-t-tertiary truncate max-w-[180px]">{t.industry_pack}</div>
                                        </div>
                                    </button>
                                ))}
                                <div className="px-3 py-2" />
                            </div>
                        </>
                    )}
                </div>
                <ToolbarBtn icon="check-circle" label="Validate" onClick={doValidate} loading={busy === "validating"} />
                <ToolbarBtn icon="check" label={busy === "saving" ? "Saving…" : "Save"} onClick={doSave} loading={busy === "saving"} />
                <ToolbarBtn icon="layers" label={busy === "publishing" ? "Publishing…" : "Publish"} onClick={doPublish} loading={busy === "publishing"} />
                <ToolbarBtn
                    icon="send"
                    label={busy === "running" ? "Running…" : "Run workflow"}
                    onClick={doRun}
                    primary
                    loading={busy === "running"}
                    disabled={!engineLive}
                    title={engineLive ? "Save → publish → run in one click" : "Engine not live yet — runs start once it's provisioned"}
                />
                <button
                    onClick={() => setFullscreen((v) => !v)}
                    title={fullscreen ? "Exit fullscreen (Esc)" : "Fullscreen canvas"}
                    className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full border border-s-subtle text-button text-t-secondary fill-t-secondary bg-b-surface2 transition-all hover:border-s-highlight hover:text-t-primary active:scale-[0.98]"
                >
                    <Icon name={fullscreen ? "close" : "grid"} className="size-4 fill-current" />
                    {fullscreen ? "Exit" : "Fullscreen"}
                </button>
                <span className="ml-auto inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                    <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                    {nodes.length} nodes · {edges.length} edges
                </span>
            </div>

            {/* Inline run status banner — shows after a Run click, dismissed on × */}
            {runStatus && (
                <div
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl text-body-2 ring-1 ring-inset ${
                        runStatus.ok
                            ? "bg-primary-02/10 text-primary-02 ring-primary-02/20"
                            : "bg-primary-03/10 text-primary-03 ring-primary-03/20"
                    }`}
                >
                    <span className={`size-2 shrink-0 rounded-full ${runStatus.ok ? "bg-primary-02" : "bg-primary-03"}`} />
                    <span className="flex-1 min-w-0">
                        {runStatus.ok ? (
                            <>
                                <span className="font-semibold">Run dispatched</span>
                                {runStatus.status && (
                                    <span className="ml-2 opacity-70 capitalize">{runStatus.status}</span>
                                )}
                                {runStatus.run_id && (
                                    <span className="ml-2 font-mono text-caption opacity-60">{runStatus.run_id}</span>
                                )}
                            </>
                        ) : (
                            <span>{runStatus.msg}</span>
                        )}
                    </span>
                    <button
                        onClick={() => setRunStatus(null)}
                        className="shrink-0 grid place-items-center size-6 rounded-full opacity-60 hover:opacity-100 hover:bg-current/10 transition-opacity"
                        title="Dismiss"
                    >
                        <Icon name="close" className="size-3.5 fill-current" />
                    </button>
                </div>
            )}

            <div className={`flex gap-3 max-xl:flex-col ${fullscreen ? "flex-1 min-h-0" : ""}`}>
                {/* palette rail */}
                <div className="w-64 max-xl:w-full shrink-0">
                    <div className={`card !mb-0 p-3 max-lg:p-2 ${fullscreen ? "h-full overflow-y-auto scrollbar-none" : ""}`}>
                        <div className="flex items-center gap-1.5 px-1 pb-2 text-caption text-t-tertiary">
                            <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                            Click to add — or drag onto the canvas
                        </div>
                        <div className="space-y-4">
                            {NODE_GROUPS.map((grp) => (
                                <div key={grp.group}>
                                    <div className="text-overline text-t-tertiary px-1 mb-2">{grp.group}</div>
                                    <div className="space-y-1.5">
                                        {grp.types.map((t) => {
                                            const m = nodeMeta(t);
                                            return (
                                                <button
                                                    type="button"
                                                    key={t}
                                                    draggable={writable}
                                                    onDragStart={(e) => {
                                                        e.dataTransfer.setData(DRAG_MIME, t);
                                                        e.dataTransfer.effectAllowed = "move";
                                                    }}
                                                    onClick={() => writable && addNode(t)}
                                                    disabled={!writable}
                                                    className="lift group flex w-full items-center gap-2.5 p-2.5 rounded-xl bg-b-surface2 ring-1 ring-s-subtle ring-inset text-left cursor-pointer active:cursor-grabbing disabled:opacity-50 disabled:cursor-not-allowed dark:bg-shade-04/30"
                                                    title={`${m.blurb}\nClick to add, or drag onto the canvas.`}
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
                                                    <Icon
                                                        name="plus"
                                                        className="size-3.5 shrink-0 fill-t-tertiary opacity-0 transition-opacity group-hover:opacity-100"
                                                    />
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* canvas */}
                <div className="flex-1 min-w-0 min-h-0">
                    <div
                        ref={rfWrap}
                        className={`wf-canvas relative rounded-3xl ring-1 ring-inset ring-s-subtle overflow-hidden ${
                            fullscreen ? "h-full" : "h-[70vh] min-h-[480px] max-sm:h-[420px]"
                        }`}
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
                                    <div className="text-body-2 text-t-secondary">Click a node on the left to add it</div>
                                    <div className="text-caption text-t-tertiary mt-1">
                                        Then drag a node&apos;s right dot to another node&apos;s left dot to wire the path.
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

    // Fullscreen: portal to <body> so the sidebar / Layout never clips the canvas.
    if (fullscreen && typeof document !== "undefined") {
        return createPortal(
            <div className="wf-fullscreen fixed inset-0 z-[60] bg-b-surface1 p-4 max-sm:p-2 overflow-hidden flex flex-col">
                {body}
            </div>,
            document.body
        );
    }

    return body;
}

// Public wrapper — supplies the RF context provider + scopes our token overrides.
export default function WorkflowEditor(props: {
    initialDef: WfDefinition;
    workflowId: string | null;
    writable: boolean;
    engineLive?: boolean;
    onToast: (msg: string, type?: "success" | "error") => void;
    onRename?: (name: string) => void;
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
