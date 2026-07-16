"use client";

// ─────────────────────────────────────────────────────────────────────────────
// P7.2 — Script Studio 2.0 BLOCK BUILDER
// Author a call script as ordered, typed blocks. The backend (script_compiler.py) compiles these
// DOWN to the campaign fields the live agent already reads — but ONLY when "Script Studio 2.0" is
// enabled here (else the blocks are stored but the campaign runs on its existing flat script, so
// nothing about the live call changes). Reorder via up/down (no new dependency); a decision-tree
// canvas can layer on later (@xyflow/react is already installed).
// Pure presentation + local edit: everything bubbles up via onChange. Token-only styling.
// ─────────────────────────────────────────────────────────────────────────────

import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { generateScriptBlock } from "@/lib/api";
import { SCRIPT_TEMPLATES } from "./_script-templates";

export type QAPair = { q: string; a: string };
export type ScriptBlock = {
    id: string;
    type: string;
    enabled?: boolean;
    text?: string;
    items?: string[];
    qa?: QAPair[];
    options?: string[];
    goal?: string;
};

type Editor = "text" | "qual" | "items" | "qa" | "closing";
type BlockDef = { type: string; label: string; editor: Editor; hint: string; metaOnly?: boolean };

// The block catalogue. metaOnly blocks are builder/simulator notes — they do NOT change the live
// prompt (the compiler treats them as metadata), surfaced with a subtle "note" tag.
export const BLOCK_DEFS: BlockDef[] = [
    { type: "greeting", label: "Greeting", editor: "text", hint: "How the agent opens — persona & tone." },
    { type: "qualification", label: "Qualification", editor: "qual", hint: "The key question to qualify the lead, plus extra qualifiers." },
    { type: "discovery", label: "Discovery", editor: "items", hint: "Questions to understand the caller's need (one per line)." },
    { type: "objection", label: "Objection handling", editor: "qa", hint: "If the caller objects (e.g. price) → how to respond." },
    { type: "faq", label: "FAQs", editor: "qa", hint: "Common questions → short answers." },
    { type: "closing", label: "Closing", editor: "closing", hint: "The goal + appointment options to book." },
    { type: "followup", label: "Follow-up", editor: "text", hint: "Post-call follow-up note.", metaOnly: true },
    { type: "escalation", label: "Escalation", editor: "text", hint: "When / how to hand off to a human.", metaOnly: true },
    { type: "condition", label: "Condition", editor: "text", hint: "A branching note for the flow.", metaOnly: true },
];
const DEF = (t: string) => BLOCK_DEFS.find((d) => d.type === t);

let _seq = 0;
function newId(): string {
    _seq += 1;
    return `blk_${Date.now().toString(36)}_${_seq.toString(36)}`;
}

const inputCls = "input-base w-full h-10 px-3 rounded-xl text-body-2";
const areaCls = "input-base w-full px-3 py-2.5 rounded-xl text-body-2 resize-y min-h-[64px]";

type Props = {
    campaignId: string;
    blocks: ScriptBlock[];
    variables: Record<string, string>;
    v2: boolean;
    writable: boolean;
    onBlocksChange: (b: ScriptBlock[]) => void;
    onVariablesChange: (v: Record<string, string>) => void;
    onV2Change: (on: boolean) => void;
    onNotice?: (kind: "success" | "error" | "info", msg: string) => void;
};

export default function BlockBuilder({
    campaignId, blocks, variables, v2, writable, onBlocksChange, onVariablesChange, onV2Change, onNotice,
}: Props) {
    const [aiBusy, setAiBusy] = useState<string | null>(null);
    const patch = useCallback((id: string, p: Partial<ScriptBlock>) => {
        onBlocksChange(blocks.map((b) => (b.id === id ? { ...b, ...p } : b)));
    }, [blocks, onBlocksChange]);
    const add = useCallback((type: string) => {
        onBlocksChange([...blocks, { id: newId(), type, enabled: true }]);
    }, [blocks, onBlocksChange]);
    const remove = useCallback((id: string) => {
        onBlocksChange(blocks.filter((b) => b.id !== id));
    }, [blocks, onBlocksChange]);
    const move = useCallback((idx: number, dir: -1 | 1) => {
        const j = idx + dir;
        if (j < 0 || j >= blocks.length) return;
        const next = blocks.slice();
        [next[idx], next[j]] = [next[j], next[idx]];
        onBlocksChange(next);
    }, [blocks, onBlocksChange]);

    const loadTemplate = useCallback((tplId: string) => {
        const tpl = SCRIPT_TEMPLATES.find((t) => t.id === tplId);
        if (!tpl) return;
        if (blocks.length > 0 && typeof window !== "undefined"
            && !window.confirm(`Replace the current blocks with the "${tpl.label}" template?`)) return;
        onBlocksChange(tpl.blocks.map((b) => ({ ...b, id: newId() })));
    }, [blocks, onBlocksChange]);

    const aiFill = useCallback(async (b: ScriptBlock) => {
        if (!campaignId || aiBusy) return;
        setAiBusy(b.id);
        try {
            const r = await generateScriptBlock(campaignId, b.type);
            if (r.ok && r.block) {
                const { type: _t, ...gen } = r.block; // keep the block's own type
                onBlocksChange(blocks.map((x) => (x.id === b.id ? { ...x, ...gen } : x)));
                onNotice?.("success", `Drafted by ${r.model_label || "AI"} — review & tweak.`);
            } else {
                onNotice?.("error", r.error === "no_openrouter_key"
                    ? "AI drafting needs OPENROUTER_API_KEY on the server."
                    : (r.message || r.error || "Generation failed"));
            }
        } finally {
            setAiBusy(null);
        }
    }, [campaignId, aiBusy, blocks, onBlocksChange, onNotice]);

    return (
        <div className="flex flex-col gap-4">
            {/* v2 enable toggle + explainer */}
            <div className="flex items-start gap-3 rounded-2xl bg-primary-01/[0.06] ring-1 ring-primary-01/20 p-3.5">
                <button
                    type="button"
                    disabled={!writable}
                    role="switch"
                    aria-checked={v2}
                    onClick={() => onV2Change(!v2)}
                    className={`mt-0.5 relative h-6 w-11 shrink-0 rounded-full transition-colors ${v2 ? "bg-primary-01" : "bg-s-stroke2"} disabled:opacity-50`}
                >
                    <span className={`absolute top-0.5 size-5 rounded-full bg-white transition-transform ${v2 ? "translate-x-5" : "translate-x-0.5"}`} />
                </button>
                <div className="min-w-0">
                    <div className="text-button text-t-primary">Script Studio 2.0 {v2 ? "— live" : "— off"}</div>
                    <p className="text-caption text-t-secondary">
                        {v2
                            ? "These blocks compile into the live agent's brain on save. Reorder, edit, and preview on the right."
                            : "Build your script as blocks below. Turn this on to make the agent use them (otherwise the campaign keeps its current free script)."}
                    </p>
                </div>
            </div>

            {/* templates */}
            {writable && (
                <div className="flex flex-wrap items-center gap-1.5">
                    <span className="mr-1 text-caption text-t-tertiary">Start from a template:</span>
                    {SCRIPT_TEMPLATES.map((t) => (
                        <button key={t.id} type="button" onClick={() => loadTemplate(t.id)} title={t.blurb}
                            className="inline-flex items-center rounded-full bg-b-surface3 px-2.5 py-1 text-caption text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary">
                            {t.label}
                        </button>
                    ))}
                </div>
            )}

            {/* block list */}
            {blocks.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-s-stroke2 px-4 py-8 text-center">
                    <div className="text-sub-title-2 text-t-primary">No blocks yet</div>
                    <div className="mt-1 text-caption text-t-tertiary">Add a block below to start building your script.</div>
                </div>
            ) : (
                <div className="flex flex-col gap-3">
                    {blocks.map((b, idx) => {
                        const def = DEF(b.type);
                        const enabled = b.enabled !== false;
                        return (
                            <div key={b.id} className={`rounded-2xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-3.5 ${enabled ? "" : "opacity-60"}`}>
                                <div className="flex items-center gap-2 mb-2.5">
                                    <span className="text-button text-t-primary">{def?.label || b.type}</span>
                                    {def?.metaOnly && <span className="pill pill-neutral">note</span>}
                                    <span className="ml-auto flex items-center gap-1">
                                        <button type="button" disabled={!writable || aiBusy !== null} onClick={() => aiFill(b)} title="Draft this block with AI" className="grid size-7 place-items-center rounded-full fill-primary-01 hover:bg-primary-01/10 disabled:opacity-40"><Icon name="feather" className={`size-4 fill-inherit ${aiBusy === b.id ? "animate-spin" : ""}`} /></button>
                                        <button type="button" disabled={!writable || idx === 0} onClick={() => move(idx, -1)} title="Move up" className="grid size-7 place-items-center rounded-full fill-t-tertiary hover:fill-t-primary hover:bg-b-surface3 disabled:opacity-30"><Icon name="chevron" className="size-4 fill-inherit rotate-180" /></button>
                                        <button type="button" disabled={!writable || idx === blocks.length - 1} onClick={() => move(idx, 1)} title="Move down" className="grid size-7 place-items-center rounded-full fill-t-tertiary hover:fill-t-primary hover:bg-b-surface3 disabled:opacity-30"><Icon name="chevron" className="size-4 fill-inherit" /></button>
                                        <button type="button" disabled={!writable} onClick={() => patch(b.id, { enabled: !enabled })} title={enabled ? "Disable" : "Enable"} className={`grid size-7 place-items-center rounded-full hover:bg-b-surface3 ${enabled ? "fill-primary-02" : "fill-t-tertiary"}`}><Icon name="check" className="size-4 fill-inherit" /></button>
                                        <button type="button" disabled={!writable} onClick={() => remove(b.id)} title="Delete" className="grid size-7 place-items-center rounded-full fill-t-tertiary hover:fill-primary-03 hover:bg-primary-03/10"><Icon name="trash" className="size-4 fill-inherit" /></button>
                                    </span>
                                </div>
                                {def?.hint && <p className="mb-2 text-caption text-t-tertiary">{def.hint}</p>}
                                <BlockEditor block={b} editor={def?.editor || "text"} writable={writable} onChange={(p) => patch(b.id, p)} />
                            </div>
                        );
                    })}
                </div>
            )}

            {/* add-block palette */}
            {writable && (
                <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-caption text-t-tertiary mr-1">Add block:</span>
                    {BLOCK_DEFS.map((d) => (
                        <button key={d.type} type="button" onClick={() => add(d.type)}
                            className="inline-flex items-center gap-1 rounded-full bg-b-surface3 px-2.5 py-1 text-caption text-t-secondary transition-colors hover:text-t-primary hover:bg-b-surface1">
                            <Icon name="plus" className="size-3 fill-current" />{d.label}
                        </button>
                    ))}
                </div>
            )}

            {/* variables */}
            <VariablesEditor variables={variables} writable={writable} onChange={onVariablesChange} />
        </div>
    );
}

// Variables editor with STABLE row ids — editing a key in place can't drop/duplicate values.
// Local rows are the edit source of truth; we emit a sanitized dict (trim keys, drop empties,
// last-wins on dup) up via onChange, and only re-seed from the prop on a genuine external change
// (e.g. a different campaign loads), never on our own emit.
function VariablesEditor({ variables, writable, onChange }: {
    variables: Record<string, string>; writable: boolean; onChange: (v: Record<string, string>) => void;
}) {
    const vid = useRef(0);
    const seed = useCallback(
        () => Object.entries(variables || {}).map(([k, v]) => ({ id: `v${vid.current++}`, k, v: String(v ?? "") })),
        [variables],
    );
    const [rows, setRows] = useState(seed);
    const lastEmit = useRef(JSON.stringify(variables || {}));
    useEffect(() => {
        const incoming = JSON.stringify(variables || {});
        if (incoming !== lastEmit.current) {
            setRows(seed());
            lastEmit.current = incoming;
        }
    }, [variables, seed]);
    const emit = (next: { id: string; k: string; v: string }[]) => {
        setRows(next);
        const d: Record<string, string> = {};
        for (const r of next) { const k = r.k.trim(); if (k) d[k] = r.v; }
        lastEmit.current = JSON.stringify(d);
        onChange(d);
    };
    return (
        <div className="rounded-2xl bg-b-surface2 ring-1 ring-inset ring-s-subtle p-3.5">
            <div className="flex items-center gap-2 mb-1">
                <Icon name="font" className="size-4 fill-t-secondary" />
                <span className="text-button text-t-primary">Variables</span>
            </div>
            <p className="mb-2.5 text-caption text-t-tertiary">
                Reusable values you can drop into any block as <span className="font-mono">{"{{name}}"}</span>. Runtime values like <span className="font-mono">{"{{lead_name}}"}</span> are filled per call — don&apos;t define those here.
            </p>
            <div className="flex flex-col gap-2">
                {rows.map((r, i) => (
                    <div key={r.id} className="flex items-center gap-2">
                        <input className={`${inputCls} w-36`} value={r.k} disabled={!writable} placeholder="name"
                            onChange={(e) => { const n = rows.slice(); n[i] = { ...r, k: e.target.value.replace(/[^a-zA-Z0-9_]/g, "") }; emit(n); }} />
                        <span className="text-t-tertiary">=</span>
                        <input className={`${inputCls} flex-1`} value={r.v} disabled={!writable} placeholder="value"
                            onChange={(e) => { const n = rows.slice(); n[i] = { ...r, v: e.target.value }; emit(n); }} />
                        <button type="button" disabled={!writable} onClick={() => emit(rows.filter((_, j) => j !== i))}
                            className="grid size-8 shrink-0 place-items-center rounded-full fill-t-tertiary hover:fill-primary-03"><Icon name="close" className="size-4 fill-inherit" /></button>
                    </div>
                ))}
                {writable && (
                    <button type="button" onClick={() => emit([...rows, { id: `v${vid.current++}`, k: "", v: "" }])}
                        className="inline-flex w-fit items-center gap-1 rounded-full bg-b-surface3 px-2.5 py-1 text-caption text-t-secondary hover:text-t-primary">
                        <Icon name="plus" className="size-3 fill-current" />Add variable
                    </button>
                )}
            </div>
        </div>
    );
}

// ── per-type editors ──
function BlockEditor({ block, editor, writable, onChange }: {
    block: ScriptBlock; editor: Editor; writable: boolean; onChange: (p: Partial<ScriptBlock>) => void;
}) {
    if (editor === "text") {
        return <textarea className={areaCls} disabled={!writable} value={block.text || ""}
            onChange={(e) => onChange({ text: e.target.value })} placeholder="Write this section in plain language…" />;
    }
    if (editor === "qual") {
        return (
            <div className="flex flex-col gap-2">
                <input className={inputCls} disabled={!writable} value={block.text || ""}
                    onChange={(e) => onChange({ text: e.target.value })} placeholder="Main qualifying question…" />
                <ListEditor items={block.items || []} writable={writable} placeholder="Extra qualifier…" onChange={(items) => onChange({ items })} />
            </div>
        );
    }
    if (editor === "items") {
        return <ListEditor items={block.items || []} writable={writable} placeholder="A discovery question…" onChange={(items) => onChange({ items })} />;
    }
    if (editor === "qa") {
        return <QAEditor pairs={block.qa || []} writable={writable} onChange={(qa) => onChange({ qa })} />;
    }
    // closing
    return (
        <div className="flex flex-col gap-2">
            <input className={inputCls} disabled={!writable} value={block.goal || ""}
                onChange={(e) => onChange({ goal: e.target.value })} placeholder="Goal (e.g. book a site visit)…" />
            <ListEditor items={block.options || []} writable={writable} placeholder="Appointment option…" onChange={(options) => onChange({ options })} />
        </div>
    );
}

function ListEditor({ items, writable, placeholder, onChange }: {
    items: string[]; writable: boolean; placeholder: string; onChange: (v: string[]) => void;
}) {
    return (
        <div className="flex flex-col gap-1.5">
            {items.map((it, i) => (
                <div key={i} className="flex items-center gap-2">
                    <input className={inputCls} disabled={!writable} value={it} placeholder={placeholder}
                        onChange={(e) => { const n = items.slice(); n[i] = e.target.value; onChange(n); }} />
                    <button type="button" disabled={!writable} onClick={() => onChange(items.filter((_, j) => j !== i))}
                        className="grid size-8 shrink-0 place-items-center rounded-full fill-t-tertiary hover:fill-primary-03"><Icon name="close" className="size-4 fill-inherit" /></button>
                </div>
            ))}
            {writable && (
                <button type="button" onClick={() => onChange([...items, ""])}
                    className="inline-flex w-fit items-center gap-1 rounded-full bg-b-surface3 px-2.5 py-1 text-caption text-t-secondary hover:text-t-primary">
                    <Icon name="plus" className="size-3 fill-current" />Add
                </button>
            )}
        </div>
    );
}

function QAEditor({ pairs, writable, onChange }: {
    pairs: QAPair[]; writable: boolean; onChange: (v: QAPair[]) => void;
}) {
    return (
        <div className="flex flex-col gap-2">
            {pairs.map((p, i) => (
                <div key={i} className="rounded-xl bg-b-surface1 ring-1 ring-inset ring-s-subtle p-2.5 dark:bg-shade-04/30">
                    <div className="flex items-center gap-2">
                        <input className={`${inputCls} flex-1`} disabled={!writable} value={p.q} placeholder="If the caller says…"
                            onChange={(e) => { const n = pairs.slice(); n[i] = { ...p, q: e.target.value }; onChange(n); }} />
                        <button type="button" disabled={!writable} onClick={() => onChange(pairs.filter((_, j) => j !== i))}
                            className="grid size-8 shrink-0 place-items-center rounded-full fill-t-tertiary hover:fill-primary-03"><Icon name="close" className="size-4 fill-inherit" /></button>
                    </div>
                    <input className={`${inputCls} mt-1.5`} disabled={!writable} value={p.a} placeholder="…respond with"
                        onChange={(e) => { const n = pairs.slice(); n[i] = { ...p, a: e.target.value }; onChange(n); }} />
                </div>
            ))}
            {writable && (
                <button type="button" onClick={() => onChange([...pairs, { q: "", a: "" }])}
                    className="inline-flex w-fit items-center gap-1 rounded-full bg-b-surface3 px-2.5 py-1 text-caption text-t-secondary hover:text-t-primary">
                    <Icon name="plus" className="size-3 fill-current" />Add pair
                </button>
            )}
        </div>
    );
}
