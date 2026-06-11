"use client";

// The Node Inspector — a right-hand slide-in panel (Core_2 Modal isSlidePanel)
// whose body is generated from the per-type INSPECTOR_FIELDS schema (_lib §2/§3)
// using ONLY the ported Core_2 form primitives: Field (text/number/textarea),
// Select (enums), Switch (advisory money flag) + a small repeatable args key/val
// sub-editor. It reads/writes the selected RF node's data via getPath/setPath and
// calls onPatch to merge the change back into canvas state. Zero bespoke inputs.

import { useMemo } from "react";
import Modal from "@/components/Modal";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Switch from "@/components/Switch";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import {
    INSPECTOR_FIELDS,
    nodeMeta,
    selOpts,
    selFind,
    type FieldDef,
    type WfNodeData,
} from "../_lib";

type ArgRow = { k: string; v: string };

/* ---- nested get/set on the WfNodeData object via "a.b" dotted paths ---- */

function getPath(data: WfNodeData, path: string): unknown {
    const parts = path.split(".");
    let cur: unknown = data;
    for (const p of parts) {
        if (cur == null || typeof cur !== "object") return undefined;
        cur = (cur as Record<string, unknown>)[p];
    }
    return cur;
}

function setPath(data: WfNodeData, path: string, value: unknown): WfNodeData {
    const parts = path.split(".");
    const next: WfNodeData = {
        ...data,
        config: { ...(data.config || {}) },
    };
    let cur: Record<string, unknown> = next as unknown as Record<string, unknown>;
    for (let i = 0; i < parts.length - 1; i++) {
        const p = parts[i];
        const child = cur[p];
        cur[p] = child && typeof child === "object" ? { ...(child as object) } : {};
        cur = cur[p] as Record<string, unknown>;
    }
    cur[parts[parts.length - 1]] = value;
    return next;
}

/* ---- args (config.args) <-> editable key/value rows ---- */

function argsToRows(data: WfNodeData): ArgRow[] {
    const raw = (data.config?.args ?? {}) as Record<string, unknown>;
    const rows = Object.entries(raw).map(([k, v]) => ({
        k,
        v: typeof v === "object" ? JSON.stringify(v) : String(v),
    }));
    return rows;
}

function rowsToArgs(rows: ArgRow[]): Record<string, unknown> {
    const out: Record<string, unknown> = {};
    for (const r of rows) {
        if (!r.k.trim()) continue;
        // Coerce simple numerics; otherwise keep the string.
        const n = Number(r.v);
        out[r.k.trim()] = r.v.trim() !== "" && !Number.isNaN(n) ? n : r.v;
    }
    return out;
}

/* ---- field visibility (the `when` conditional in the schema) ---- */

function visible(field: FieldDef, data: WfNodeData): boolean {
    if (!field.when) return true;
    return String(getPath(data, field.when.path) ?? "") === field.when.equals;
}

/* ===================================================================== panel */

export default function NodeInspector({
    data,
    onPatch,
    onDelete,
    onClose,
}: {
    data: WfNodeData | null;
    onPatch: (next: WfNodeData) => void;
    onDelete: () => void;
    onClose: () => void;
}) {
    const meta = data ? nodeMeta(data.wfType) : null;
    const fields = data ? INSPECTOR_FIELDS[data.wfType] : [];

    const argRows = useMemo(() => (data ? argsToRows(data) : []), [data]);

    function patchField(field: FieldDef, value: unknown) {
        if (!data) return;
        onPatch(setPath(data, field.path, value));
    }

    function patchArgs(rows: ArgRow[]) {
        if (!data) return;
        onPatch(setPath(data, "config.args", rowsToArgs(rows)));
    }

    return (
        <Modal open={!!data} onClose={onClose} isSlidePanel>
            {data && meta && (
                <div className="flex h-full flex-col">
                    {/* header */}
                    <div className="flex items-start gap-3 p-5 border-b border-s-subtle">
                        <span
                            className="grid place-items-center size-10 shrink-0 rounded-xl bg-b-surface2 ring-1 ring-s-subtle"
                            style={{ fill: meta.accent }}
                        >
                            <Icon name={meta.icon} className="size-5 fill-inherit" />
                        </span>
                        <div className="min-w-0 flex-1">
                            <div className="text-h6 text-t-primary truncate">
                                {data.label || meta.label}
                            </div>
                            <div className="text-caption text-t-tertiary">{meta.label} node</div>
                        </div>
                    </div>

                    {/* body — generated fields */}
                    <div className="flex-1 overflow-y-auto px-5 py-5 space-y-5 scrollbar-none">
                        <div className="flex flex-wrap gap-1.5">
                            {data.role && <Badge variant="info">{data.role}</Badge>}
                            <Badge variant="neutral">{meta.gate}</Badge>
                            {data.money && (
                                <Badge variant="success" dot>
                                    can spend
                                </Badge>
                            )}
                        </div>
                        <p className="text-caption text-t-secondary">{meta.blurb}</p>

                        {fields.map((field) => {
                            if (!visible(field, data)) return null;
                            const key = field.path;

                            if (field.kind === "args") {
                                return (
                                    <ArgsEditor
                                        key={key}
                                        label={field.label}
                                        rows={argRows}
                                        onChange={patchArgs}
                                    />
                                );
                            }

                            if (field.kind === "switch") {
                                return (
                                    <div key={key}>
                                        <div className="flex items-center justify-between gap-3">
                                            <div className="text-button">{field.label}</div>
                                            <Switch
                                                checked={!!getPath(data, field.path)}
                                                onChange={(c) => patchField(field, c)}
                                            />
                                        </div>
                                        {field.help && (
                                            <p className="text-caption text-t-tertiary mt-1.5">{field.help}</p>
                                        )}
                                    </div>
                                );
                            }

                            if (field.kind === "select") {
                                const opts = field.options || [];
                                return (
                                    <div key={key}>
                                        <Select
                                            label={field.label}
                                            tooltip={field.tooltip}
                                            value={selFind(opts, getPath(data, field.path))}
                                            options={selOpts(opts)}
                                            placeholder="Select…"
                                            onChange={(o) => patchField(field, o.name)}
                                        />
                                        {field.help && (
                                            <p className="text-caption text-t-tertiary mt-1.5">{field.help}</p>
                                        )}
                                    </div>
                                );
                            }

                            // text / number / textarea
                            const cur = getPath(data, field.path);
                            return (
                                <div key={key}>
                                    <Field
                                        label={field.label}
                                        tooltip={field.tooltip}
                                        textarea={field.kind === "textarea"}
                                        type={field.kind === "number" ? "number" : "text"}
                                        placeholder={field.placeholder}
                                        value={cur == null ? "" : String(cur)}
                                        onChange={(e) => {
                                            const raw = e.target.value;
                                            patchField(
                                                field,
                                                field.kind === "number"
                                                    ? raw === ""
                                                        ? ""
                                                        : Number(raw)
                                                    : raw
                                            );
                                        }}
                                    />
                                    {field.help && (
                                        <p className="text-caption text-t-tertiary mt-1.5">{field.help}</p>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {/* footer */}
                    <div className="flex items-center gap-2 p-4 border-t border-s-subtle">
                        <button
                            onClick={onDelete}
                            className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full border border-s-subtle text-button text-primary-03 fill-primary-03 transition-colors hover:border-primary-03/40 hover:bg-primary-03/10"
                        >
                            <Icon name="trash" className="size-4 fill-current" />
                            Delete node
                        </button>
                        <button
                            onClick={onClose}
                            className="ml-auto inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full bg-b-surface2 text-button text-t-secondary transition-colors hover:text-t-primary"
                        >
                            Done
                        </button>
                    </div>
                </div>
            )}
        </Modal>
    );
}

/* ---------------------------- repeatable args key/val sub-editor (Core_2 Field) */

function ArgsEditor({
    label,
    rows,
    onChange,
}: {
    label: string;
    rows: ArgRow[];
    onChange: (rows: ArgRow[]) => void;
}) {
    const list = rows.length > 0 ? rows : [{ k: "", v: "" }];

    function update(i: number, patch: Partial<ArgRow>) {
        const next = list.map((r, idx) => (idx === i ? { ...r, ...patch } : r));
        onChange(next);
    }
    function add() {
        onChange([...list, { k: "", v: "" }]);
    }
    function remove(i: number) {
        const next = list.filter((_, idx) => idx !== i);
        onChange(next.length ? next : [{ k: "", v: "" }]);
    }

    return (
        <div>
            <div className="flex items-center justify-between mb-3">
                <div className="text-button">{label}</div>
                <button
                    onClick={add}
                    className="inline-flex items-center gap-1 text-caption text-t-secondary hover:text-t-primary fill-t-secondary hover:fill-t-primary"
                >
                    <Icon name="plus" className="size-3.5 fill-inherit" />
                    Add
                </button>
            </div>
            <div className="space-y-2">
                {list.map((r, i) => (
                    <div key={i} className="flex items-center gap-2">
                        <input
                            value={r.k}
                            onChange={(e) => update(i, { k: e.target.value })}
                            placeholder="key"
                            className="w-2/5 h-10 px-3.5 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-primary-01/60 focus:ring-2 focus:ring-primary-01/30 placeholder:text-t-secondary/50"
                        />
                        <input
                            value={r.v}
                            onChange={(e) => update(i, { v: e.target.value })}
                            placeholder="value"
                            className="flex-1 h-10 px-3.5 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-primary-01/60 focus:ring-2 focus:ring-primary-01/30 placeholder:text-t-secondary/50"
                        />
                        <button
                            onClick={() => remove(i)}
                            className="grid place-items-center size-9 shrink-0 rounded-full text-t-tertiary hover:text-primary-03 hover:bg-primary-03/10"
                            title="Remove"
                        >
                            <Icon name="close" className="size-3.5 fill-current" />
                        </button>
                    </div>
                ))}
            </div>
        </div>
    );
}
