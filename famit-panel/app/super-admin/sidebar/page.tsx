"use client";

// ============================================================
// Super-Admin · Sidebar Builder — /super-admin/sidebar
// Fully control ANY tenant's sidebar:
//   • DRAG to reorder sections + items (framer-motion Reorder)
//   • Shown/Hidden toggle (what to show / not show)
//   • inline RELABEL (how to show)
//   • MOVE a sub-page to a different category ("Move ▾")
//   • CREATE NEW items (links) and NEW sections
// Saves a per-tenant {order,hidden,labels,childOrder,parentOf,custom} via
// POST /admin/nav-config; the tenant's sidebar applies it (components/Sidebar
// applyNavConfig). Cosmetic over the static nav + entitlements — backend gate
// is the real boundary.
// ============================================================

import { useEffect, useState } from "react";
import { Reorder } from "framer-motion";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import Button from "@/components/Button";
import Select from "@/components/Select";
import { navigation } from "@/contstants/navigation";
import { navKey, childKey } from "@/components/Sidebar";
import {
    getTenants,
    getAdminNavConfig,
    saveAdminNavConfig,
    type Tenant,
    type NavConfig,
    type NavCustomItem,
} from "@/lib/api";
import {
    SuperAdminGuard,
    SuperAdminHeaderF3,
    ErrorBanner,
    ToastView,
    ghostBtnCls,
    type Toast,
} from "../_shared";

type Stage = "default" | "beta" | "premium";
type WChild = {
    key: string;
    label: string;
    def: string;
    hidden: boolean;
    stage: Stage; // #25: maturity gate — default | beta | premium
    unavailable: boolean; // #25: not exposed to the end user at all
    custom?: boolean;
    href?: string;
    catalogParent?: string; // the section it belongs to in the static catalog
};
type WItem = {
    key: string;
    label: string;
    def: string;
    hidden: boolean;
    stage: Stage;
    unavailable: boolean;
    icon?: string;
    isGroup: boolean;
    custom?: boolean;
    children: WChild[];
};

let _seq = 0;
function newKey(prefix: string): string {
    _seq += 1;
    return `custom:${prefix}-${Date.now().toString(36)}-${_seq}`;
}

// Build the editable tree = static catalog + saved config (order/hidden/labels/move/custom).
function buildTree(cfg: NavConfig): WItem[] {
    const hidden = new Set(cfg.hidden || []);
    const labels = cfg.labels || {};
    const childOrder = cfg.childOrder || {};
    const parentOf = cfg.parentOf || {};
    const custom = cfg.custom || [];
    const stageMap = cfg.stage || {};
    const unavail = new Set(cfg.unavailable || []);
    const stageOf = (k: string): Stage =>
        stageMap[k] === "beta" || stageMap[k] === "premium" ? stageMap[k] : "default";

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const items: WItem[] = (navigation as any[]).map((it) => {
        const k = navKey(it);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const kids: WChild[] = (it.list || []).map((c: any) => {
            const ck = childKey(c);
            return {
                key: ck,
                label: labels[ck] || c.title,
                def: c.title,
                hidden: hidden.has(ck),
                stage: stageOf(ck),
                unavailable: unavail.has(ck),
                catalogParent: k,
            };
        });
        return {
            key: k,
            label: labels[k] || it.title,
            def: it.title,
            hidden: hidden.has(k),
            stage: stageOf(k),
            unavailable: unavail.has(k),
            icon: it.icon,
            isGroup: !it.href,
            children: kids,
        };
    });
    const byKey = new Map(items.map((s) => [s.key, s] as const));

    // custom SECTIONS
    for (const c of custom) {
        if (c.isSection && !byKey.has(c.key)) {
            const sec: WItem = {
                key: c.key,
                label: labels[c.key] || c.label,
                def: c.label,
                hidden: hidden.has(c.key),
                stage: stageOf(c.key),
                unavailable: unavail.has(c.key),
                icon: c.icon || "grid",
                isGroup: true,
                custom: true,
                children: [],
            };
            items.push(sec);
            byKey.set(c.key, sec);
        }
    }

    // pool children, add custom LINKS, then redistribute by parentOf (moves)
    const pool: { child: WChild; from: string }[] = [];
    for (const s of items) {
        for (const c of s.children) pool.push({ child: c, from: s.key });
        s.children = [];
    }
    for (const c of custom) {
        if (!c.isSection && c.href) {
            pool.push({
                child: {
                    key: c.key,
                    label: labels[c.key] || c.label,
                    def: c.label,
                    hidden: hidden.has(c.key),
                    stage: stageOf(c.key),
                    unavailable: unavail.has(c.key),
                    custom: true,
                    href: c.href,
                    catalogParent: c.parent,
                },
                from: c.parent || "",
            });
        }
    }
    for (const { child, from } of pool) {
        const target = parentOf[child.key] || from;
        const sec = byKey.get(target) || byKey.get(from);
        if (sec) sec.children.push(child);
    }

    // child order
    for (const s of items) {
        const co = childOrder[s.key];
        if (co && co.length) {
            const ci = (c: WChild) => {
                const i = co.indexOf(c.key);
                return i === -1 ? 999 : i;
            };
            s.children = [...s.children].sort((a, b) => ci(a) - ci(b));
        }
    }

    // top-level order
    const order = cfg.order || [];
    if (order.length) {
        const oi = (it: WItem) => {
            const i = order.indexOf(it.key);
            return i === -1 ? 999 : i;
        };
        return [...items].sort((a, b) => oi(a) - oi(b));
    }
    return items;
}

function serialize(items: WItem[]): NavConfig {
    const order = items.map((i) => i.key);
    const hidden: string[] = [];
    const labels: Record<string, string> = {};
    const childOrder: Record<string, string[]> = {};
    const parentOf: Record<string, string> = {};
    const custom: NavCustomItem[] = [];
    const stage: Record<string, "beta" | "premium"> = {};
    const unavailable: string[] = [];
    const recordGate = (key: string, st: Stage, un: boolean) => {
        if (st === "beta" || st === "premium") stage[key] = st;
        if (un) unavailable.push(key);
    };
    for (const it of items) {
        if (it.hidden) hidden.push(it.key);
        if (it.label.trim() && it.label !== it.def) labels[it.key] = it.label.trim();
        recordGate(it.key, it.stage, it.unavailable);
        if (it.custom && it.isGroup) {
            custom.push({ key: it.key, label: it.label.trim() || it.def, isSection: true, icon: it.icon });
        }
        if (it.children.length) childOrder[it.key] = it.children.map((c) => c.key);
        for (const c of it.children) {
            if (c.hidden) hidden.push(c.key);
            if (c.label.trim() && c.label !== c.def) labels[c.key] = c.label.trim();
            recordGate(c.key, c.stage, c.unavailable);
            if (c.custom) {
                custom.push({ key: c.key, label: c.label.trim() || c.def, href: c.href || "#", parent: it.key });
            } else if (c.catalogParent && c.catalogParent !== it.key) {
                parentOf[c.key] = it.key; // moved to another category
            }
        }
    }
    return { order, hidden, labels, childOrder, parentOf, custom, stage, unavailable };
}

export default function SidebarBuilderPage() {
    const [tenants, setTenants] = useState<Tenant[]>([]);
    const [tid, setTid] = useState("");
    const [items, setItems] = useState<WItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [err, setErr] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);
    const [addingTo, setAddingTo] = useState<string | null>(null);
    const [newLabel, setNewLabel] = useState("");
    const [newHref, setNewHref] = useState("");

    useEffect(() => {
        getTenants()
            .then((r) => setTenants(r.tenants || []))
            .catch(() => setErr("Failed to load tenants."));
    }, []);

    async function loadTenant(id: string) {
        setTid(id);
        setAddingTo(null);
        if (!id) {
            setItems([]);
            return;
        }
        setLoading(true);
        setErr("");
        try {
            const r = await getAdminNavConfig(id);
            setItems(buildTree(r.config || {}));
        } catch {
            setErr("Failed to load this tenant's sidebar config.");
            setItems(buildTree({}));
        } finally {
            setLoading(false);
        }
    }

    async function save() {
        if (!tid) return;
        setSaving(true);
        try {
            await saveAdminNavConfig(tid, serialize(items));
            setToast({ msg: "Saved — the user's sidebar updates on their next page load.", type: "success" });
        } catch {
            setToast({ msg: "Save failed.", type: "error" });
        } finally {
            setSaving(false);
        }
    }

    // --- mutators ---
    const toggleItem = (k: string) =>
        setItems((p) => p.map((i) => (i.key === k ? { ...i, hidden: !i.hidden } : i)));
    // #24: select-all — show or hide every section + item in one click.
    const setAllHidden = (h: boolean) =>
        setItems((p) => p.map((i) => ({ ...i, hidden: h, children: i.children.map((c) => ({ ...c, hidden: h })) })));
    const labelItem = (k: string, v: string) =>
        setItems((p) => p.map((i) => (i.key === k ? { ...i, label: v } : i)));
    const deleteSection = (k: string) => setItems((p) => p.filter((i) => i.key !== k));
    // #25 per-item gating — section-level stage + availability.
    const setStageItem = (k: string, s: Stage) =>
        setItems((p) => p.map((i) => (i.key === k ? { ...i, stage: s } : i)));
    const toggleAvailItem = (k: string) =>
        setItems((p) => p.map((i) => (i.key === k ? { ...i, unavailable: !i.unavailable } : i)));

    const patchChildren = (ik: string, fn: (kids: WChild[]) => WChild[]) =>
        setItems((p) => p.map((i) => (i.key === ik ? { ...i, children: fn(i.children) } : i)));
    const toggleChild = (ik: string, ck: string) =>
        patchChildren(ik, (k) => k.map((c) => (c.key === ck ? { ...c, hidden: !c.hidden } : c)));
    const labelChild = (ik: string, ck: string, v: string) =>
        patchChildren(ik, (k) => k.map((c) => (c.key === ck ? { ...c, label: v } : c)));
    const setStageChild = (ik: string, ck: string, s: Stage) =>
        patchChildren(ik, (k) => k.map((c) => (c.key === ck ? { ...c, stage: s } : c)));
    const toggleAvailChild = (ik: string, ck: string) =>
        patchChildren(ik, (k) => k.map((c) => (c.key === ck ? { ...c, unavailable: !c.unavailable } : c)));
    const deleteChild = (ik: string, ck: string) =>
        patchChildren(ik, (k) => k.filter((c) => c.key !== ck));
    const setChildren = (ik: string, kids: WChild[]) =>
        setItems((p) => p.map((i) => (i.key === ik ? { ...i, children: kids } : i)));

    const moveChild = (fromKey: string, ck: string, toKey: string) => {
        if (fromKey === toKey) return;
        setItems((p) => {
            const child = p.find((i) => i.key === fromKey)?.children.find((c) => c.key === ck);
            if (!child) return p;
            return p.map((i) => {
                if (i.key === fromKey) return { ...i, children: i.children.filter((c) => c.key !== ck) };
                if (i.key === toKey) return { ...i, children: [...i.children, child] };
                return i;
            });
        });
    };

    const addItem = (sectionKey: string) => {
        const label = newLabel.trim() || "New link";
        const href = newHref.trim() || "#";
        const child: WChild = { key: newKey("link"), label, def: label, hidden: false, stage: "default", unavailable: false, custom: true, href, catalogParent: sectionKey };
        patchChildren(sectionKey, (k) => [...k, child]);
        setAddingTo(null);
        setNewLabel("");
        setNewHref("");
    };
    const addSection = () => {
        const label = "New Section";
        setItems((p) => [
            ...p,
            { key: newKey("sec"), label, def: label, hidden: false, stage: "default", unavailable: false, icon: "grid", isGroup: true, custom: true, children: [] },
        ]);
    };

    const selected = tenants.find((t) => t.tenant_id === tid);
    const sectionOpts = items.filter((i) => i.isGroup).map((i) => ({ key: i.key, label: i.label }));
    // Design-system Select options for the tenant picker (id === array index; `value` holds tenant_id).
    const tenantOpts = tenants.map((t, i) => ({
        id: i,
        name: `${t.name || t.email || t.tenant_id}${t.is_admin ? " · admin" : ""}`,
        value: t.tenant_id,
    }));

    return (
        <SuperAdminGuard>
            <Layout title="Sidebar Builder">
                <SuperAdminHeaderF3
                    actions={
                        tid ? (
                            <>
                                <button className={ghostBtnCls} onClick={() => setAllHidden(false)} title="Show every section + item">
                                    Show all
                                </button>
                                <button className={ghostBtnCls} onClick={() => setAllHidden(true)} title="Hide every section + item">
                                    Hide all
                                </button>
                                <button className={ghostBtnCls} onClick={addSection}>
                                    + New section
                                </button>
                                <button className={ghostBtnCls} onClick={() => setItems(buildTree({}))}>
                                    Reset
                                </button>
                                <Button onClick={save} disabled={saving}>
                                    {saving ? "Saving…" : "Save sidebar"}
                                </Button>
                            </>
                        ) : null
                    }
                />
                <ErrorBanner msg={err} />

                {/* Tenant picker */}
                <div className="mb-5 p-4 rounded-3xl bg-b-surface2 border border-s-subtle">
                    <label className="block text-button text-t-secondary mb-2">Choose a user / account</label>
                    <Select
                        className="w-full max-w-md"
                        classButton="!h-11"
                        placeholder="— select a tenant —"
                        value={tenantOpts.find((o) => o.value === tid) ?? null}
                        options={tenantOpts}
                        onChange={(o) => loadTenant(tenantOpts[o.id].value)}
                    />
                    {selected && (
                        <p className="mt-2 text-caption text-t-tertiary">
                            Editing the sidebar for{" "}
                            <span className="text-t-primary">{selected.name || selected.email}</span>. Drag to
                            reorder · toggle Shown/Hidden · edit text to relabel · Move ▾ to recategorise · +
                            New section / + Add item to create.
                        </p>
                    )}
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-24">
                        <Spinner />
                    </div>
                ) : tid ? (
                    <Reorder.Group axis="y" values={items} onReorder={setItems} className="flex flex-col gap-2.5">
                        {items.map((it) => (
                            <Reorder.Item
                                key={it.key}
                                value={it}
                                className={`rounded-2xl border border-s-subtle bg-b-surface2 ${it.hidden ? "opacity-55" : ""}`}
                            >
                                <Row
                                    icon={it.icon}
                                    label={it.label}
                                    hidden={it.hidden}
                                    isGroup={it.isGroup}
                                    custom={it.custom}
                                    stage={it.stage}
                                    unavailable={it.unavailable}
                                    onStage={(s) => setStageItem(it.key, s)}
                                    onAvail={() => toggleAvailItem(it.key)}
                                    onLabel={(v) => labelItem(it.key, v)}
                                    onToggle={() => toggleItem(it.key)}
                                    onDelete={it.custom ? () => deleteSection(it.key) : undefined}
                                />
                                {it.isGroup && (
                                    <div className="px-3 pb-3 pl-9">
                                        {it.children.length > 0 && (
                                            <Reorder.Group
                                                axis="y"
                                                values={it.children}
                                                onReorder={(kids) => setChildren(it.key, kids as WChild[])}
                                                className="flex flex-col gap-1.5"
                                            >
                                                {it.children.map((c) => (
                                                    <Reorder.Item
                                                        key={c.key}
                                                        value={c}
                                                        className={`rounded-xl border border-s-subtle/60 bg-b-surface1 ${c.hidden ? "opacity-55" : ""}`}
                                                    >
                                                        <Row
                                                            small
                                                            label={c.label}
                                                            hidden={c.hidden}
                                                            custom={c.custom}
                                                            stage={c.stage}
                                                            unavailable={c.unavailable}
                                                            onStage={(s) => setStageChild(it.key, c.key, s)}
                                                            onAvail={() => toggleAvailChild(it.key, c.key)}
                                                            moveOpts={sectionOpts}
                                                            moveValue={it.key}
                                                            onMove={(to) => moveChild(it.key, c.key, to)}
                                                            onLabel={(v) => labelChild(it.key, c.key, v)}
                                                            onToggle={() => toggleChild(it.key, c.key)}
                                                            onDelete={c.custom ? () => deleteChild(it.key, c.key) : undefined}
                                                        />
                                                    </Reorder.Item>
                                                ))}
                                            </Reorder.Group>
                                        )}
                                        {addingTo === it.key ? (
                                            <div className="mt-2 flex flex-wrap items-center gap-2 p-2 rounded-xl bg-b-surface1 border border-s-subtle">
                                                <input
                                                    autoFocus
                                                    value={newLabel}
                                                    onChange={(e) => setNewLabel(e.target.value)}
                                                    placeholder="Label (e.g. Help)"
                                                    className="input-base h-9 px-3 rounded-lg text-body-2 flex-1 min-w-32"
                                                />
                                                <input
                                                    value={newHref}
                                                    onChange={(e) => setNewHref(e.target.value)}
                                                    placeholder="/path or https://…"
                                                    className="input-base h-9 px-3 rounded-lg text-body-2 flex-1 min-w-40"
                                                />
                                                <button
                                                    onClick={() => addItem(it.key)}
                                                    className="h-9 px-3 rounded-lg text-caption bg-primary-01 text-t-light"
                                                >
                                                    Add
                                                </button>
                                                <button
                                                    onClick={() => setAddingTo(null)}
                                                    className="h-9 px-3 rounded-lg text-caption text-t-secondary border border-s-subtle"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        ) : (
                                            <button
                                                onClick={() => {
                                                    setAddingTo(it.key);
                                                    setNewLabel("");
                                                    setNewHref("");
                                                }}
                                                className="mt-2 text-caption text-t-secondary hover:text-t-primary"
                                            >
                                                + Add item
                                            </button>
                                        )}
                                    </div>
                                )}
                            </Reorder.Item>
                        ))}
                    </Reorder.Group>
                ) : (
                    <div className="py-24 text-center text-t-tertiary text-body-2">
                        Select a user above to customise their sidebar.
                    </div>
                )}
            </Layout>
            <ToastView toast={toast} onClose={() => setToast(null)} />
        </SuperAdminGuard>
    );
}

function Row({
    icon,
    small,
    label,
    hidden,
    isGroup,
    custom,
    stage,
    unavailable,
    onStage,
    onAvail,
    moveOpts,
    moveValue,
    onMove,
    onLabel,
    onToggle,
    onDelete,
}: {
    icon?: string;
    small?: boolean;
    label: string;
    hidden: boolean;
    isGroup?: boolean;
    custom?: boolean;
    stage?: Stage;
    unavailable?: boolean;
    onStage?: (s: Stage) => void;
    onAvail?: () => void;
    moveOpts?: { key: string; label: string }[];
    moveValue?: string;
    onMove?: (to: string) => void;
    onLabel: (v: string) => void;
    onToggle: () => void;
    onDelete?: () => void;
}) {
    const stop = (e: React.PointerEvent) => e.stopPropagation();
    return (
        <div className={`flex items-center gap-2.5 ${small ? "p-2" : "p-3"}`}>
            <span
                className="cursor-grab active:cursor-grabbing select-none text-t-tertiary leading-none px-1 text-lg"
                title="Drag to reorder"
            >
                ⠿
            </span>
            {icon && (
                <span className="flex size-7 items-center justify-center rounded-lg bg-b-surface1 shrink-0">
                    <Icon name={icon} className="size-4 fill-t-secondary" />
                </span>
            )}
            <input
                value={label}
                onChange={(e) => onLabel(e.target.value)}
                onPointerDownCapture={stop}
                className={`flex-1 min-w-24 bg-transparent outline-none text-t-primary placeholder:text-t-tertiary ${
                    small ? "text-body-2" : "text-button"
                }`}
                placeholder="Label"
            />
            {custom && (
                <span className="text-caption text-primary-02 px-1.5 py-0.5 rounded-md bg-primary-02/10 shrink-0">
                    new
                </span>
            )}
            {isGroup && !custom && (
                <span className="text-caption text-t-tertiary px-1.5 py-0.5 rounded-md bg-b-surface1 shrink-0">
                    section
                </span>
            )}
            {moveOpts && onMove && (() => {
                // id === array index; `value` holds the section key.
                const opts = moveOpts.map((o, i) => ({ id: i, name: o.label, value: o.key }));
                return (
                    <div
                        onPointerDownCapture={stop}
                        title="Move to another category"
                        className="shrink-0 max-w-36"
                    >
                        <Select
                            classButton="!h-8 !rounded-lg"
                            value={opts.find((o) => o.value === moveValue) ?? null}
                            options={opts}
                            onChange={(o) => onMove(opts[o.id].value)}
                        />
                    </div>
                );
            })()}
            {/* #25: maturity stage — Default / Beta / Premium (cosmetic pill on the user's rail) */}
            {onStage && (
                <select
                    value={stage || "default"}
                    onChange={(e) => onStage(e.target.value as Stage)}
                    onPointerDownCapture={stop}
                    title="Stage — Beta/Premium show a pill on the item; Default is plain"
                    className={`shrink-0 h-8 rounded-lg bg-b-surface1 border border-s-subtle text-caption px-2 outline-none ${
                        stage === "beta" ? "text-[#7C4DDF] dark:text-[#A78BFA]"
                        : stage === "premium" ? "text-[#B8860B] dark:text-[#E6C200]"
                        : "text-t-tertiary"
                    }`}
                >
                    <option value="default">Default</option>
                    <option value="beta">Beta</option>
                    <option value="premium">Premium</option>
                </select>
            )}
            {/* #25: availability — Unavailable hides the item from the end user entirely */}
            {onAvail && (
                <button
                    onClick={onAvail}
                    onPointerDownCapture={stop}
                    title={unavailable ? "Unavailable — hidden from users; click to release" : "Available — click to make unavailable"}
                    className={`shrink-0 inline-flex items-center h-8 px-3 rounded-full text-caption border transition-colors ${
                        unavailable
                            ? "border-[#FF6A55]/45 text-[#FF6A55]"
                            : "border-[#00A656]/40 text-[#00A656]"
                    }`}
                >
                    {unavailable ? "Unavailable" : "Available"}
                </button>
            )}
            <button
                onClick={onToggle}
                onPointerDownCapture={stop}
                className={`shrink-0 inline-flex items-center h-8 px-3 rounded-full text-caption border transition-colors ${
                    hidden
                        ? "border-s-subtle text-t-tertiary hover:text-t-primary"
                        : "border-primary-02/45 text-primary-02"
                }`}
                title={hidden ? "Hidden — click to show" : "Shown — click to hide"}
            >
                {hidden ? "Hidden" : "Shown"}
            </button>
            {onDelete && (
                <button
                    onClick={onDelete}
                    onPointerDownCapture={stop}
                    title="Delete this custom item"
                    className="shrink-0 inline-flex items-center justify-center size-8 rounded-full text-t-tertiary hover:text-primary-03 border border-s-subtle"
                >
                    ×
                </button>
            )}
        </div>
    );
}
