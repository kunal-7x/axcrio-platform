"use client";

// ============================================================
// CL-F3 · Plans — /super-admin/plans
//
// Plans = reusable bundles of per-feature entitlements + usage limits, assigned
// to a vendor in the Vendor Workspace. Ports two Core_2 archetypes:
//   • the GALLERY = UpgradeToProPage/Pricing tier cards (plan summary cards).
//   • the EDITOR  = Products/NewProductPage section-form (left = entitlement
//     3-state per feature grouped by module; right rail = numeric limit fields).
// design/control-ui.md §2.5.
//
// Reads  GET  /admin/plans       (+ /admin/features for the catalog)
// Writes POST /admin/plans       (create a new plan)
//        PUT  /admin/plans/{id}   JSON {entitlements:{key:mode}, limits:{key:int}}
//          -> the backend REPLACES both sets + bumps every tenant on the plan.
//
// A plan only lists features it OVERRIDES off the global default; an absent row
// means "inherit the global flag". So the editor's per-feature control has a 4th
// state — "Default (inherit)" — alongside On / Locked / Hidden.
//
// SECURITY: cosmetic admin view; require_super_admin is the real boundary.
// ============================================================

import { useEffect, useMemo, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Modal from "@/components/Modal";
import Spinner from "@/components/Spinner";
import {
    getAdminPlans,
    getAdminFeatures,
    createAdminPlan,
    updateAdminPlan,
    type AdminPlan,
    type FeatureRegistryRow,
    type FeatureMode,
} from "@/lib/api";
import {
    SuperAdminGuard,
    SuperAdminHeaderF3,
    KIND_META,
    LIMIT_KEYS,
    limitLabel,
    ErrorBanner,
    ToastView,
    type Toast,
    ghostBtnCls,
} from "../_shared";

// The editor's per-feature state: a FeatureMode OR "" = inherit the global default.
type EditMode = FeatureMode | "";
const EDIT_SEG: { value: EditMode; label: string; active: string }[] = [
    { value: "", label: "Default", active: "bg-b-surface1 text-t-primary border-s-stroke2 dark:bg-shade-04" },
    { value: "on", label: "On", active: "bg-primary-02/12 text-primary-02 border-primary-02/30" },
    { value: "locked", label: "Lock", active: "bg-primary-05/12 text-primary-05 border-primary-05/30" },
    { value: "hidden", label: "Hide", active: "bg-shade-08/40 text-t-primary border-s-stroke2" },
];

function EditSegment({
    value,
    onChange,
    disabled,
}: {
    value: EditMode;
    onChange: (m: EditMode) => void;
    disabled?: boolean;
}) {
    return (
        <div className="inline-flex items-center gap-1 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle shrink-0">
            {EDIT_SEG.map((seg) => {
                const isActive = value === seg.value;
                return (
                    <button
                        key={seg.value || "default"}
                        type="button"
                        disabled={disabled}
                        onClick={() => onChange(seg.value)}
                        className={`inline-flex items-center justify-center h-7 px-3 rounded-full text-caption font-medium border transition-all disabled:opacity-40 ${
                            isActive ? seg.active : "border-transparent text-t-secondary hover:text-t-primary"
                        }`}
                    >
                        {seg.label}
                    </button>
                );
            })}
        </div>
    );
}

export default function PlansPage() {
    const [plans, setPlans] = useState<AdminPlan[]>([]);
    const [features, setFeatures] = useState<FeatureRegistryRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);

    // editor state
    const [editing, setEditing] = useState<AdminPlan | null>(null);
    const [draftEnt, setDraftEnt] = useState<Record<string, FeatureMode>>({});
    const [draftLimits, setDraftLimits] = useState<Record<string, string>>({});
    const [saving, setSaving] = useState(false);

    // create-plan modal
    const [creating, setCreating] = useState(false);
    const [newId, setNewId] = useState("");
    const [newName, setNewName] = useState("");
    const [createBusy, setCreateBusy] = useState(false);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 3500);
    };

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        Promise.all([getAdminPlans(), getAdminFeatures()])
            .then(([p, f]) => {
                setPlans(p.plans);
                setFeatures(f.features);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load plans"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // controllable (non-module, non-core-implied) features grouped by module.
    const groupedFeatures = useMemo(() => {
        const moduleLabels = new Map<string, string>();
        for (const r of features) if (r.kind === "module") moduleLabels.set(r.key, r.label || r.key);
        const byMod = new Map<string, FeatureRegistryRow[]>();
        for (const r of features) {
            if (r.kind === "module") continue;
            const mod = r.key.split(".")[0];
            if (!byMod.has(mod)) byMod.set(mod, []);
            byMod.get(mod)!.push(r);
        }
        const out: { key: string; label: string; rows: FeatureRegistryRow[] }[] = [];
        for (const [mod, rows] of byMod) {
            rows.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.key.localeCompare(b.key));
            out.push({ key: mod, label: moduleLabels.get(mod) || mod, rows });
        }
        out.sort((a, b) => a.label.localeCompare(b.label));
        return out;
    }, [features]);

    function openEditor(p: AdminPlan) {
        setEditing(p);
        setDraftEnt({ ...p.entitlements });
        const lim: Record<string, string> = {};
        for (const k of LIMIT_KEYS) lim[k] = p.limits[k] != null ? String(p.limits[k]) : "";
        // include any non-standard limits the plan already carries
        for (const [k, v] of Object.entries(p.limits)) if (!(k in lim)) lim[k] = String(v);
        setDraftLimits(lim);
    }

    function setEntMode(key: string, mode: EditMode) {
        setDraftEnt((d) => {
            const next = { ...d };
            if (mode === "") delete next[key];
            else next[key] = mode;
            return next;
        });
    }

    async function savePlan() {
        if (!editing) return;
        setSaving(true);
        const limits: Record<string, number> = {};
        for (const [k, v] of Object.entries(draftLimits)) {
            const n = parseInt(v, 10);
            if (Number.isFinite(n)) limits[k] = n;
        }
        try {
            await updateAdminPlan(editing.plan_id, { entitlements: draftEnt, limits });
            showToast(`Plan “${editing.name || editing.plan_id}” saved`, "success");
            setEditing(null);
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Failed to save plan", "error");
        } finally {
            setSaving(false);
        }
    }

    async function doCreate() {
        const pid = newId.trim().toLowerCase().replace(/\s+/g, "_");
        if (!pid) return;
        setCreateBusy(true);
        try {
            await createAdminPlan({ plan_id: pid, name: newName.trim() || pid });
            showToast(`Plan “${newName.trim() || pid}” created`, "success");
            setCreating(false);
            setNewId("");
            setNewName("");
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Failed to create plan", "error");
        } finally {
            setCreateBusy(false);
        }
    }

    return (
        <SuperAdminGuard>
            <Layout title="Plans">
                <SuperAdminHeaderF3
                    actions={
                        <>
                            <button onClick={load} className={ghostBtnCls} disabled={loading}>
                                <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                                {loading ? "Refreshing…" : "Refresh"}
                            </button>
                            <Button isBlack onClick={() => setCreating(true)}>
                                New plan
                            </Button>
                        </>
                    }
                />
                <ToastView toast={toast} onClose={() => setToast(null)} />
                <ErrorBanner msg={error} />

                {loading && plans.length === 0 ? (
                    <div className="py-24">
                        <Spinner />
                    </div>
                ) : plans.length === 0 ? (
                    <Card title="Plans">
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="wallet" className="fill-inherit" />
                            </span>
                            <div className="state-title">No plans yet</div>
                            <div className="state-sub">Create a plan to bundle entitlements + limits for vendors.</div>
                        </div>
                    </Card>
                ) : (
                    <div className="grid grid-cols-3 gap-5 max-xl:grid-cols-2 max-md:grid-cols-1">
                        {plans.map((p) => {
                            const entCount = Object.keys(p.entitlements).length;
                            const limCount = Object.keys(p.limits).length;
                            return (
                                <div key={p.plan_id} className="card p-5 flex flex-col rise-in">
                                    <div className="flex items-center justify-between gap-2 mb-1">
                                        <div className="text-h6 text-t-primary truncate">{p.name || p.plan_id}</div>
                                        {p.is_default && <Badge variant="info">Default</Badge>}
                                    </div>
                                    <div className="text-caption text-t-tertiary font-mono mb-4">{p.plan_id}</div>

                                    {/* limits summary */}
                                    <div className="flex flex-col gap-2 mb-4">
                                        {LIMIT_KEYS.filter((k) => p.limits[k] != null).slice(0, 5).map((k) => (
                                            <div key={k} className="flex items-center justify-between text-body-2">
                                                <span className="text-t-secondary">{limitLabel(k)}</span>
                                                <span className="text-t-primary font-medium tabular-nums">
                                                    {p.limits[k].toLocaleString()}
                                                </span>
                                            </div>
                                        ))}
                                        {Object.keys(p.limits).length === 0 && (
                                            <div className="text-caption text-t-tertiary">No limits set — inherits defaults.</div>
                                        )}
                                    </div>

                                    <div className="flex items-center gap-2 mt-auto pt-3 border-t border-s-subtle">
                                        <Badge variant="neutral">{entCount} entitlement{entCount === 1 ? "" : "s"}</Badge>
                                        <Badge variant="neutral">{limCount} limit{limCount === 1 ? "" : "s"}</Badge>
                                        <button
                                            onClick={() => openEditor(p)}
                                            className="ml-auto inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full text-button text-t-secondary border border-s-subtle transition-all hover:border-s-highlight hover:text-t-primary"
                                        >
                                            <Icon name="edit" className="size-4 fill-current" />
                                            Edit
                                        </button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}

                {/* ---- editor (NewProductPage section-form archetype) ---- */}
                <Modal
                    classWrapper="max-w-4xl"
                    open={!!editing}
                    onClose={() => !saving && setEditing(null)}
                >
                    {editing && (
                        <div className="p-1">
                            <div className="flex items-center justify-between gap-3 mb-5">
                                <div>
                                    <div className="text-h5 text-t-primary">{editing.name || editing.plan_id}</div>
                                    <div className="text-caption text-t-tertiary font-mono">{editing.plan_id}</div>
                                </div>
                                {editing.is_default && <Badge variant="info">Default plan</Badge>}
                            </div>

                            <div className="grid grid-cols-[1fr_18rem] gap-6 max-lg:grid-cols-1">
                                {/* left: entitlements per module */}
                                <div className="min-w-0 max-h-[60vh] overflow-y-auto pr-1 flex flex-col gap-4 scrollbar scrollbar-thumb-t-tertiary/30">
                                    <div className="text-button text-t-secondary">Entitlements</div>
                                    {groupedFeatures.map((g) => (
                                        <div key={g.key}>
                                            <div className="text-caption uppercase tracking-[0.06em] text-t-tertiary font-semibold mb-2">
                                                {g.label}
                                            </div>
                                            <div className="rounded-2xl border border-s-subtle divide-y divide-s-subtle">
                                                {g.rows.map((r) => {
                                                    const kind = KIND_META[r.kind] ?? KIND_META.feature;
                                                    const cur = (draftEnt[r.key] ?? "") as EditMode;
                                                    return (
                                                        <div key={r.key} className="flex items-center justify-between gap-3 px-3.5 py-2.5">
                                                            <div className="min-w-0">
                                                                <div className="flex items-center gap-2">
                                                                    <span className="text-body-2 text-t-primary truncate">{r.label || r.key}</span>
                                                                    <Badge variant={kind.variant}>{kind.label}</Badge>
                                                                </div>
                                                                <div className="text-caption text-t-tertiary font-mono truncate">{r.key}</div>
                                                            </div>
                                                            <EditSegment
                                                                value={cur}
                                                                onChange={(m) => setEntMode(r.key, m)}
                                                            />
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                {/* right rail: usage limits */}
                                <div className="flex flex-col gap-4">
                                    <div className="text-button text-t-secondary">Usage limits</div>
                                    {LIMIT_KEYS.map((k) => (
                                        <Field
                                            key={k}
                                            label={limitLabel(k)}
                                            type="number"
                                            inputMode="numeric"
                                            placeholder="inherit"
                                            value={draftLimits[k] ?? ""}
                                            onChange={(e) =>
                                                setDraftLimits((d) => ({ ...d, [k]: e.target.value }))
                                            }
                                        />
                                    ))}
                                    <div className="text-caption text-t-tertiary">
                                        Leave a field blank to inherit the platform default. Saving replaces this plan’s
                                        full entitlement + limit set and re-evaluates every vendor on it.
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-s-subtle">
                                <Button isStroke onClick={() => setEditing(null)} disabled={saving}>
                                    Cancel
                                </Button>
                                <Button isBlack onClick={savePlan} disabled={saving}>
                                    {saving ? "Saving…" : "Save plan"}
                                </Button>
                            </div>
                        </div>
                    )}
                </Modal>

                {/* ---- create plan ---- */}
                <Modal classWrapper="max-w-md" open={creating} onClose={() => !createBusy && setCreating(false)}>
                    <div className="p-1">
                        <div className="text-h5 text-t-primary mb-1">New plan</div>
                        <div className="text-caption text-t-tertiary mb-5">
                            Give the plan an id (lowercase, no spaces) and a display name. Add entitlements + limits after.
                        </div>
                        <div className="flex flex-col gap-4">
                            <Field
                                label="Plan id"
                                placeholder="growth_pro"
                                value={newId}
                                onChange={(e) => setNewId(e.target.value)}
                            />
                            <Field
                                label="Display name"
                                placeholder="Growth Pro"
                                value={newName}
                                onChange={(e) => setNewName(e.target.value)}
                            />
                        </div>
                        <div className="flex items-center justify-end gap-3 mt-6">
                            <Button isStroke onClick={() => setCreating(false)} disabled={createBusy}>
                                Cancel
                            </Button>
                            <Button isBlack onClick={doCreate} disabled={createBusy || !newId.trim()}>
                                {createBusy ? "Creating…" : "Create plan"}
                            </Button>
                        </div>
                    </div>
                </Modal>
            </Layout>
        </SuperAdminGuard>
    );
}
