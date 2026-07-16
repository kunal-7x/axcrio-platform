"use client";

// The field-schema editor — the heart of the builder. Add / configure / reorder
// the 13 field types (core._FIELD_TYPES), set the label, the allow-list key
// (^[a-z0-9_]{1,40}$, validated client-side to match core.validate_fields),
// required flag, and options for select/multiselect. Pure-presentational: it
// owns no network — the parent persists the resulting FormField[] via updateForm.

import { useState } from "react";
import Icon from "@/components/Icon";
import Select from "@/components/Select";
import {
    FIELD_TYPES,
    type FieldType,
    type FormField,
} from "../client";
import {
    FIELD_TYPE_META,
    fieldTypeMeta,
    FIELD_KEY_RE,
    slugifyKey,
} from "../_ui";

type Props = {
    fields: FormField[];
    onChange: (fields: FormField[]) => void;
    disabled?: boolean;
};

const FIELD_TYPE_OPTS = FIELD_TYPES.map((t, i) => ({
    id: i,
    name: FIELD_TYPE_META[t].label,
    value: t,
}));

function emptyField(type: FieldType, existing: FormField[]): FormField {
    // derive a unique default key so the allow-list never trips on first add
    const base = type === "nps" || type === "csat" ? "score" : type;
    let key = base;
    let n = 1;
    const taken = new Set(existing.map((f) => f.key));
    while (taken.has(key)) key = `${base}_${++n}`;
    return {
        key,
        label: fieldTypeMeta(type).label,
        type,
        required: false,
        options: [],
    };
}

export default function FieldEditor({ fields, onChange, disabled }: Props) {
    const [adding, setAdding] = useState(false);

    function update(i: number, patch: Partial<FormField>) {
        onChange(fields.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));
    }
    function remove(i: number) {
        onChange(fields.filter((_, idx) => idx !== i));
    }
    function move(i: number, dir: -1 | 1) {
        const j = i + dir;
        if (j < 0 || j >= fields.length) return;
        const next = [...fields];
        [next[i], next[j]] = [next[j], next[i]];
        onChange(next);
    }
    function add(type: FieldType) {
        onChange([...fields, emptyField(type, fields)]);
        setAdding(false);
    }

    return (
        <div className="px-5 pb-5 max-lg:px-3">
            {fields.length === 0 ? (
                <div className="py-12 text-center">
                    <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1 fill-t-tertiary">
                        <Icon name="list" className="fill-inherit" />
                    </span>
                    <div className="text-h6 mb-1">No fields yet</div>
                    <div className="max-w-sm mx-auto text-body-2 text-t-secondary">
                        Add the questions people will answer. A phone or email
                        field lets each submission link to a CRM contact.
                    </div>
                </div>
            ) : (
                <div className="flex flex-col gap-3">
                    {fields.map((f, i) => (
                        <FieldRow
                            key={i}
                            field={f}
                            index={i}
                            count={fields.length}
                            disabled={disabled}
                            onUpdate={(patch) => update(i, patch)}
                            onRemove={() => remove(i)}
                            onMove={(dir) => move(i, dir)}
                        />
                    ))}
                </div>
            )}

            {/* Add-field control */}
            <div className="mt-3">
                {adding ? (
                    <div className="p-3 rounded-3xl border border-s-subtle bg-b-surface1 dark:bg-shade-04/30">
                        <div className="flex items-center justify-between mb-2.5 px-1">
                            <span className="text-button text-t-secondary">
                                Choose a field type
                            </span>
                            <button
                                onClick={() => setAdding(false)}
                                className="text-t-tertiary hover:text-t-primary"
                                aria-label="Cancel"
                            >
                                <Icon name="close" className="size-4 fill-inherit" />
                            </button>
                        </div>
                        <div className="grid grid-cols-3 gap-2 max-md:grid-cols-2">
                            {FIELD_TYPES.map((t) => {
                                const m = FIELD_TYPE_META[t];
                                return (
                                    <button
                                        key={t}
                                        onClick={() => add(t)}
                                        className="flex items-center gap-2.5 p-2.5 rounded-2xl border border-s-stroke2 text-left transition-all hover:border-s-highlight hover:bg-b-surface2"
                                    >
                                        <span className="grid place-items-center size-8 shrink-0 rounded-full bg-b-surface2 fill-t-secondary dark:bg-shade-04/60">
                                            <Icon
                                                name={m.icon}
                                                className="size-4 fill-inherit"
                                            />
                                        </span>
                                        <span className="min-w-0">
                                            <span className="block text-button text-t-primary truncate">
                                                {m.label}
                                            </span>
                                            <span className="block text-caption text-t-tertiary truncate">
                                                {m.hint}
                                            </span>
                                        </span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ) : (
                    <button
                        onClick={() => setAdding(true)}
                        disabled={disabled}
                        className="flex items-center justify-center gap-2 w-full h-12 rounded-3xl border border-dashed border-s-stroke2 text-button text-t-secondary fill-t-secondary transition-all hover:border-s-highlight hover:text-t-primary hover:fill-t-primary disabled:opacity-50 disabled:pointer-events-none"
                    >
                        <Icon name="plus" className="size-4.5 fill-inherit" />
                        Add field
                    </button>
                )}
            </div>
        </div>
    );
}

function FieldRow({
    field,
    index,
    count,
    disabled,
    onUpdate,
    onRemove,
    onMove,
}: {
    field: FormField;
    index: number;
    count: number;
    disabled?: boolean;
    onUpdate: (patch: Partial<FormField>) => void;
    onRemove: () => void;
    onMove: (dir: -1 | 1) => void;
}) {
    const meta = fieldTypeMeta(field.type);
    const keyValid = FIELD_KEY_RE.test(field.key);
    const optionsText = (field.options || []).join("\n");

    return (
        <div className="p-4 rounded-3xl border border-s-subtle bg-b-surface2 shadow-widget rise-in">
            <div className="flex items-start gap-3">
                <span className="grid place-items-center size-9 shrink-0 rounded-full bg-b-surface1 fill-t-secondary dark:bg-shade-04/60">
                    <Icon name={meta.icon} className="size-4.5 fill-inherit" />
                </span>

                <div className="flex-1 min-w-0 grid grid-cols-2 gap-3 max-md:grid-cols-1">
                    {/* Label */}
                    <label className="block">
                        <span className="block mb-1.5 text-caption text-t-tertiary">
                            Label
                        </span>
                        <input
                            value={field.label}
                            disabled={disabled}
                            onChange={(e) => {
                                const label = e.target.value;
                                // auto-fill key from label only while key is still the default-ish
                                const auto =
                                    !field.key ||
                                    field.key === slugifyKey(field.label);
                                onUpdate(
                                    auto
                                        ? { label, key: slugifyKey(label) || field.key }
                                        : { label }
                                );
                            }}
                            placeholder="Question label"
                            className="input-base w-full h-10 px-3.5 rounded-2xl text-body-2"
                        />
                    </label>

                    {/* Type + key */}
                    <div className="grid grid-cols-2 gap-3">
                        <label className="block">
                            <span className="block mb-1.5 text-caption text-t-tertiary">
                                Type
                            </span>
                            <Select
                                className="w-full"
                                classButton="!h-10"
                                disabled={disabled}
                                value={
                                    FIELD_TYPE_OPTS.find(
                                        (o) => o.value === field.type
                                    ) ?? null
                                }
                                options={FIELD_TYPE_OPTS}
                                onChange={(o) => {
                                    const next = FIELD_TYPE_OPTS[o.id]
                                        .value as FieldType;
                                    onUpdate({
                                        type: next,
                                        // clear options when leaving an option-bearing type
                                        options: FIELD_TYPE_META[next]?.hasOptions
                                            ? field.options
                                            : [],
                                    });
                                }}
                            />
                        </label>
                        <label className="block">
                            <span className="block mb-1.5 text-caption text-t-tertiary">
                                Key
                            </span>
                            <input
                                value={field.key}
                                disabled={disabled}
                                onChange={(e) =>
                                    onUpdate({
                                        key: e.target.value
                                            .toLowerCase()
                                            .slice(0, 40),
                                    })
                                }
                                placeholder="field_key"
                                className={`input-base w-full h-10 px-3.5 rounded-2xl text-body-2 td-num ${
                                    keyValid
                                        ? ""
                                        : "!border-primary-03/60 focus:!ring-primary-03/30"
                                }`}
                            />
                        </label>
                    </div>
                </div>

                {/* Row controls */}
                <div className="flex items-center gap-1 shrink-0">
                    <button
                        onClick={() => onMove(-1)}
                        disabled={disabled || index === 0}
                        className="grid place-items-center size-8 rounded-full text-t-tertiary fill-t-tertiary transition-colors hover:bg-b-surface1 hover:text-t-primary disabled:opacity-30 disabled:pointer-events-none dark:hover:bg-shade-04/60"
                        aria-label="Move up"
                    >
                        <Icon name="arrow" className="size-4 fill-inherit -rotate-90" />
                    </button>
                    <button
                        onClick={() => onMove(1)}
                        disabled={disabled || index === count - 1}
                        className="grid place-items-center size-8 rounded-full text-t-tertiary fill-t-tertiary transition-colors hover:bg-b-surface1 hover:text-t-primary disabled:opacity-30 disabled:pointer-events-none dark:hover:bg-shade-04/60"
                        aria-label="Move down"
                    >
                        <Icon name="arrow" className="size-4 fill-inherit rotate-90" />
                    </button>
                    <button
                        onClick={onRemove}
                        disabled={disabled}
                        className="grid place-items-center size-8 rounded-full text-t-tertiary fill-t-tertiary transition-colors hover:bg-primary-03/10 hover:text-primary-03 hover:fill-primary-03 disabled:opacity-30 disabled:pointer-events-none"
                        aria-label="Remove field"
                    >
                        <Icon name="trash" className="size-4 fill-inherit" />
                    </button>
                </div>
            </div>

            {/* Secondary row: key error + required + options */}
            <div className="mt-3 pl-12 max-md:pl-0">
                {!keyValid && (
                    <div className="mb-2.5 flex items-center gap-1.5 text-caption text-primary-03">
                        <Icon name="info" className="size-3.5 shrink-0 fill-primary-03" />
                        Key must be 1–40 lowercase letters, numbers or underscores.
                    </div>
                )}

                <div className="flex items-center gap-4 flex-wrap">
                    <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input
                            type="checkbox"
                            checked={field.required}
                            disabled={disabled}
                            onChange={(e) =>
                                onUpdate({ required: e.target.checked })
                            }
                            className="size-4 accent-primary-01"
                        />
                        <span className="text-body-2 text-t-secondary">
                            Required
                        </span>
                    </label>
                    <span className="text-caption text-t-tertiary">
                        {meta.hint}
                    </span>
                </div>

                {meta.hasOptions && (
                    <label className="block mt-3">
                        <span className="block mb-1.5 text-caption text-t-tertiary">
                            Options — one per line
                        </span>
                        <textarea
                            value={optionsText}
                            disabled={disabled}
                            onChange={(e) =>
                                onUpdate({
                                    options: e.target.value
                                        .split("\n")
                                        .map((o) => o.trim())
                                        .filter(Boolean)
                                        .slice(0, 200),
                                })
                            }
                            placeholder={"Option A\nOption B\nOption C"}
                            className="input-base w-full h-24 px-3.5 py-2.5 rounded-2xl text-body-2 resize-none"
                        />
                    </label>
                )}
            </div>
        </div>
    );
}
