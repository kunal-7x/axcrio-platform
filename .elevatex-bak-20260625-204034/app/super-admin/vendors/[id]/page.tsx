"use client";

// ============================================================
// CL-F2 — SUPER ADMIN · Vendor Workspace + the PERMISSION MATRIX (the heart)
//
// PORT of Core_2 Customers/CustomerList/DetailsPage: a `card p-0` two-pane —
// left identity/actions rail (the `/Customer` rail) + right tabbed detail body
// (the `/Details` body). Design of record: design/control-ui.md §2.3, §3, §5;
// contract: design/spec-control-layer.md §4.
//
// LEFT RAIL: vendor identity + plan re-assign (Select → PUT /plan) + account
//   status control (Select → confirm Modal capturing a reason → PUT /status) +
//   a credits top-up entry (firewall step-up — stubbed to a Modal here; the
//   step-up token mint is the backend's job).
// RIGHT BODY — 5 Tabs:
//   Overview     · profile recap + health tiles
//   Usage        · calls / minutes / leads / campaigns / spend tiles
//   Permissions  · THE MATRIX — every feature_registry key as an EntitlementToggle
//                  row (3-state On/Lock/Hide), grouped module→page→action, with a
//                  SettingsPage-style sticky section index; optimistic writes to
//                  PUT/DELETE /admin/vendors/{id}/entitlements/{key} + version bump.
//   Billing      · wallet balance + limits vs usage
//   Audit        · this vendor's control-audit slice (best-effort)
//
// SECURITY: admin plane. The BACKEND middleware (require_super_admin, legacy-auth
// EXCLUDED) is the only real boundary; this is admin tooling. Every write is
// audited server-side. tenant_id is token-derived, never sent in a body.
// Optimistic UI + toast-on-failure (the app/vendors/page.tsx toast pattern).
// ============================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Layout from "@/components/Layout";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Select from "@/components/Select";
import Modal from "@/components/Modal";
import EntitlementToggle from "@/components/EntitlementToggle";
import { AdminHeader, StatusPill, ErrorBanner, HeroCard, fmtDate, num } from "@/app/super-admin/_shared";
import {
    getAdminVendor,
    getAdminPlans,
    setVendorEntitlement,
    clearVendorEntitlement,
    setVendorPlan,
    setVendorStatus,
    type AdminVendorDetail,
    type ResolvedEntitlement,
    type FeatureMode,
    type VendorAccountStatus,
} from "@/lib/api";
import type { SelectOption } from "@/types/select";

type Toast = { msg: string; type: "success" | "error" };

// ---- Tabs ------------------------------------------------------------------
const TABS = ["Overview", "Usage", "Permissions", "Billing", "Audit"] as const;
type TabName = (typeof TABS)[number];

// ---- Status options for the rail Select ------------------------------------
const STATUS_OPTIONS: { id: number; name: string; value: VendorAccountStatus }[] = [
    { id: 1, name: "Active", value: "active" },
    { id: 2, name: "Trial", value: "trial" },
    { id: 3, name: "Suspended", value: "suspended" },
    { id: 4, name: "Disabled", value: "disabled" },
    { id: 5, name: "Expired", value: "expired" },
];

const DEFAULT_PLANS = [
    { plan_id: "trial", name: "Trial" },
    { plan_id: "plan_a", name: "Starter (Plan A)" },
    { plan_id: "plan_b", name: "Growth (Plan B)" },
    { plan_id: "enterprise", name: "Enterprise" },
];

// A status that requires a reason before it can be applied.
const NEEDS_REASON = new Set<VendorAccountStatus>(["suspended", "disabled", "expired"]);

export default function VendorWorkspacePage() {
    const params = useParams();
    const id = decodeURIComponent(String(params?.id ?? ""));

    const [vendor, setVendor] = useState<AdminVendorDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [tab, setTab] = useState<TabName>("Overview");
    const [toast, setToast] = useState<Toast | null>(null);

    // plan options
    const [plans, setPlans] = useState<{ plan_id: string; name: string }[]>(DEFAULT_PLANS);

    // status-change modal
    const [statusModal, setStatusModal] = useState<{ next: VendorAccountStatus } | null>(null);
    const [statusReason, setStatusReason] = useState("");
    const [statusBusy, setStatusBusy] = useState(false);

    // credits top-up modal (step-up handled server-side; this is the entry UX)
    const [creditModal, setCreditModal] = useState(false);

    // per-row write-in-flight set (feature_key)
    const [busyKeys, setBusyKeys] = useState<Set<string>>(new Set());
    const [planBusy, setPlanBusy] = useState(false);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        if (!id) return;
        setLoading(true);
        setLoadError("");
        getAdminVendor(id)
            .then((v) => setVendor(v))
            .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load vendor"))
            .finally(() => setLoading(false));
    }, [id]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        getAdminPlans()
            .then((r) => {
                if (r.plans && r.plans.length) {
                    setPlans(r.plans.map((p) => ({ plan_id: p.plan_id, name: p.name })));
                }
            })
            .catch(() => {
                /* keep DEFAULT_PLANS */
            });
    }, []);

    // ---- entitlement write (optimistic) ------------------------------------
    const markBusy = (key: string, on: boolean) =>
        setBusyKeys((prev) => {
            const next = new Set(prev);
            if (on) next.add(key);
            else next.delete(key);
            return next;
        });

    // Patch a single row in local state (optimistic), recomputing parent rolldown
    // so a module flip immediately dims its children in the UI before the refetch.
    const patchRow = (key: string, patch: Partial<ResolvedEntitlement>) => {
        setVendor((v) => {
            if (!v) return v;
            const ents = v.entitlements.map((r) => (r.key === key ? { ...r, ...patch } : r));
            return { ...v, entitlements: rolldown(ents) };
        });
    };

    const handleSet = async (row: ResolvedEntitlement, mode: FeatureMode) => {
        if (!vendor) return;
        const prev = { mode: row.mode, provenance: row.provenance, override: row.override };
        markBusy(row.key, true);
        // optimistic: an explicit set is always an "override"
        patchRow(row.key, { mode, provenance: "override", override: mode });
        try {
            await setVendorEntitlement(id, row.key, mode);
            showToast(`${row.label} set to ${labelFor(mode)}.`, "success");
            // reconcile against the server's resolved map (provenance/rolldown/version)
            load();
        } catch (e) {
            patchRow(row.key, prev); // revert
            showToast(e instanceof Error ? e.message : "Failed to update permission", "error");
        } finally {
            markBusy(row.key, false);
        }
    };

    const handleReset = async (row: ResolvedEntitlement) => {
        if (!vendor) return;
        const prev = { mode: row.mode, provenance: row.provenance, override: row.override };
        markBusy(row.key, true);
        // optimistic: clear the override → fall back to plan/global hint
        const fallbackMode = row.plan_mode ?? row.default_mode ?? "on";
        patchRow(row.key, {
            mode: fallbackMode,
            provenance: row.plan_mode != null ? "plan" : "global",
            override: null,
        });
        try {
            await clearVendorEntitlement(id, row.key);
            showToast(`${row.label} reset to plan / global.`, "success");
            load();
        } catch (e) {
            patchRow(row.key, prev);
            showToast(e instanceof Error ? e.message : "Failed to reset permission", "error");
        } finally {
            markBusy(row.key, false);
        }
    };

    // ---- plan re-assign -----------------------------------------------------
    const handlePlan = async (opt: SelectOption) => {
        const planId = plans.find((p) => p.name === opt.name)?.plan_id;
        if (!planId || !vendor) return;
        const prevPlan = vendor.plan;
        setPlanBusy(true);
        setVendor((v) => (v ? { ...v, plan: planId } : v));
        try {
            await setVendorPlan(id, planId);
            showToast(`Plan changed to ${opt.name}.`, "success");
            load();
        } catch (e) {
            setVendor((v) => (v ? { ...v, plan: prevPlan } : v));
            showToast(e instanceof Error ? e.message : "Failed to assign plan", "error");
        } finally {
            setPlanBusy(false);
        }
    };

    // ---- status change (with confirm modal + reason) ------------------------
    const onPickStatus = (opt: SelectOption) => {
        const target = STATUS_OPTIONS.find((s) => s.name === opt.name)?.value;
        if (!target || target === (vendor?.status ?? "active")) return;
        setStatusReason("");
        setStatusModal({ next: target });
    };

    const confirmStatus = async () => {
        if (!statusModal || !vendor) return;
        const target = statusModal.next;
        if (NEEDS_REASON.has(target) && !statusReason.trim()) {
            showToast("A reason is required to suspend / disable / expire.", "error");
            return;
        }
        setStatusBusy(true);
        try {
            await setVendorStatus(id, target, statusReason.trim() || undefined);
            showToast(`Account ${labelForStatus(target)}.`, "success");
            setStatusModal(null);
            setStatusReason("");
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Failed to update status", "error");
        } finally {
            setStatusBusy(false);
        }
    };

    // ---- derived ------------------------------------------------------------
    const planValue: SelectOption | null = useMemo(() => {
        if (!vendor?.plan) return null;
        const p = plans.find((x) => x.plan_id === vendor.plan);
        return p ? { id: 0, name: p.name } : { id: 0, name: vendor.plan };
    }, [vendor?.plan, plans]);

    const statusValue: SelectOption = useMemo(() => {
        const cur = vendor?.status ?? "active";
        const s = STATUS_OPTIONS.find((x) => x.value === cur) ?? STATUS_OPTIONS[0];
        return { id: s.id, name: s.name };
    }, [vendor?.status]);

    const overrideCount = useMemo(
        () => (vendor?.entitlements ?? []).filter((r) => r.override != null).length,
        [vendor?.entitlements]
    );

    return (
        <Layout title={vendor?.name || "Vendor"}>
            <AdminHeader
                actions={
                    <Link
                        href="/super-admin/vendors"
                        className="inline-flex items-center gap-1.5 text-button text-t-secondary hover:text-t-primary transition-colors"
                    >
                        <Icon name="chevron" className="size-4 fill-current rotate-90" />
                        All vendors
                    </Link>
                }
            />

            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">
                        ×
                    </button>
                </div>
            )}

            {loadError && <ErrorBanner msg={loadError} />}

            <div className="card p-0 overflow-hidden">
                <div className="flex max-lg:flex-col">
                    {/* ───────── LEFT RAIL — identity + actions ───────── */}
                    <aside className="w-80 shrink-0 border-r border-s-subtle max-lg:w-full max-lg:border-r-0 max-lg:border-b">
                        <div className="p-6">
                            {/* Avatar / initial */}
                            <div className="flex items-center gap-4">
                                <div className="flex items-center justify-center size-14 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-h5 text-t-primary shrink-0">
                                    {(vendor?.name || id || "?").slice(0, 1).toUpperCase()}
                                </div>
                                <div className="min-w-0">
                                    <div className="text-h6 text-t-primary truncate">{vendor?.name || (loading ? "…" : id)}</div>
                                    <div className="text-body-2 text-t-secondary truncate">{vendor?.email || "—"}</div>
                                </div>
                            </div>

                            <div className="mt-4">
                                <StatusPill status={vendor?.status} />
                            </div>

                            {/* Identity facts */}
                            <dl className="mt-6 space-y-3.5">
                                <Fact label="Tenant ID" value={<span className="font-mono text-caption">{vendor?.tenant_id || id}</span>} />
                                <Fact label="Role" value={vendor?.role || "—"} />
                                <Fact label="Created" value={fmtDate(vendor?.created_at)} />
                                <Fact
                                    label="Wallet"
                                    value={
                                        vendor?.wallet?.balance != null
                                            ? `${(vendor.wallet.balance / 100).toLocaleString(undefined, { style: "currency", currency: vendor.wallet.currency || "INR" })}`
                                            : "—"
                                    }
                                />
                                {vendor?.ent_version != null && (
                                    <Fact label="Entitlement ver." value={<span className="font-mono text-caption">v{vendor.ent_version}</span>} />
                                )}
                            </dl>

                            {/* Plan re-assign */}
                            <div className="mt-7">
                                <div className="text-button text-t-primary mb-2.5">Plan</div>
                                <Select
                                    value={planValue}
                                    onChange={handlePlan}
                                    options={plans.map((p, i) => ({ id: i, name: p.name }))}
                                    placeholder={planBusy ? "Saving…" : "Assign a plan"}
                                />
                            </div>

                            {/* Account status control */}
                            <div className="mt-5">
                                <div className="text-button text-t-primary mb-2.5">Account status</div>
                                <Select value={statusValue} onChange={onPickStatus} options={STATUS_OPTIONS.map((s) => ({ id: s.id, name: s.name }))} />
                                <p className="mt-2 text-caption text-t-tertiary">
                                    Suspend / disable instantly revokes access. Data is preserved.
                                </p>
                            </div>

                            {/* Credits top-up */}
                            <div className="mt-5">
                                <Button isStroke className="w-full justify-center" icon="wallet" onClick={() => setCreditModal(true)}>
                                    Top-up credits
                                </Button>
                            </div>
                        </div>
                    </aside>

                    {/* ───────── RIGHT BODY — tabs ───────── */}
                    <section className="flex-1 min-w-0">
                        {/* Tab strip */}
                        <div className="flex items-center gap-1 px-4 pt-4 border-b border-s-subtle overflow-x-auto scrollbar-none">
                            {TABS.map((t) => {
                                const active = t === tab;
                                return (
                                    <button
                                        key={t}
                                        onClick={() => setTab(t)}
                                        className={`shrink-0 inline-flex items-center gap-2 h-11 px-4 -mb-px border-b-2 text-button transition-colors ${
                                            active
                                                ? "border-primary-01 text-t-primary"
                                                : "border-transparent text-t-secondary hover:text-t-primary"
                                        }`}
                                    >
                                        {t}
                                        {t === "Permissions" && overrideCount > 0 && (
                                            <Badge variant="warning" className="!text-caption !px-1.5 !py-0">
                                                {overrideCount}
                                            </Badge>
                                        )}
                                    </button>
                                );
                            })}
                        </div>

                        <div className="p-5">
                            {loading ? (
                                <TabSkeleton />
                            ) : tab === "Overview" ? (
                                <OverviewTab vendor={vendor} />
                            ) : tab === "Usage" ? (
                                <UsageTab vendor={vendor} />
                            ) : tab === "Permissions" ? (
                                <PermissionsTab
                                    vendor={vendor}
                                    busyKeys={busyKeys}
                                    onSet={handleSet}
                                    onReset={handleReset}
                                />
                            ) : tab === "Billing" ? (
                                <BillingTab vendor={vendor} />
                            ) : (
                                <AuditTab vendorId={id} />
                            )}
                        </div>
                    </section>
                </div>
            </div>

            {/* ───────── Status confirm modal ───────── */}
            <Modal open={!!statusModal} onClose={() => !statusBusy && setStatusModal(null)}>
                {statusModal && (
                    <div>
                        <h3 className="text-h5 text-t-primary mb-2">Change account status</h3>
                        <p className="text-body-2 text-t-secondary mb-5">
                            Set <span className="text-t-primary font-medium">{vendor?.name || id}</span> to{" "}
                            <span className="text-t-primary font-medium">{labelForStatus(statusModal.next)}</span>.
                            {NEEDS_REASON.has(statusModal.next) && " This revokes access immediately; data is preserved."}
                        </p>
                        <label className="block text-button mb-2 text-t-primary">
                            Reason {NEEDS_REASON.has(statusModal.next) ? <span className="text-primary-03">*</span> : <span className="text-t-tertiary">(optional)</span>}
                        </label>
                        <textarea
                            value={statusReason}
                            onChange={(e) => setStatusReason(e.target.value)}
                            rows={3}
                            className="input-base w-full px-4 py-3 rounded-2xl text-body-2 resize-none"
                            placeholder="Why is this status changing? (audited)"
                        />
                        <div className="flex items-center justify-end gap-3 mt-6">
                            <Button isStroke onClick={() => setStatusModal(null)} disabled={statusBusy}>
                                Cancel
                            </Button>
                            <Button isBlack onClick={confirmStatus} disabled={statusBusy}>
                                {statusBusy ? "Saving…" : `Set ${labelForStatus(statusModal.next)}`}
                            </Button>
                        </div>
                    </div>
                )}
            </Modal>

            {/* ───────── Credits top-up modal (entry — step-up server-side) ───────── */}
            <Modal open={creditModal} onClose={() => setCreditModal(false)}>
                <div>
                    <h3 className="text-h5 text-t-primary mb-2">Top-up credits</h3>
                    <p className="text-body-2 text-t-secondary mb-5">
                        Crediting a vendor wallet is a money action and requires a firewall step-up (PIN) on
                        the server. Wire the step-up flow here when the credits endpoint is enabled.
                    </p>
                    <div className="flex items-center gap-2 p-3 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle text-body-2 text-t-secondary">
                        <Icon className="size-5 fill-t-secondary shrink-0" name="lock" />
                        Step-up protected — POST /admin/vendors/{id}/credits
                    </div>
                    <div className="flex items-center justify-end gap-3 mt-6">
                        <Button isStroke onClick={() => setCreditModal(false)}>
                            Close
                        </Button>
                    </div>
                </div>
            </Modal>
        </Layout>
    );
}

// ============================================================================
// Sub-components
// ============================================================================

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div className="flex items-center justify-between gap-3">
            <dt className="text-body-2 text-t-secondary shrink-0">{label}</dt>
            <dd className="text-body-2 text-t-primary text-right truncate">{value}</dd>
        </div>
    );
}

function OverviewTab({ vendor }: { vendor: AdminVendorDetail | null }) {
    const h = vendor?.health;
    return (
        <div className="space-y-5">
            <div className="grid grid-cols-2 max-md:grid-cols-1 gap-3">
                <HeroCard label="Calls today" glyph="chat" value={num(vendor?.usage?.calls_today ?? 0)} />
                <HeroCard label="Active now" glyph="dashboard" value={num(vendor?.usage?.active_now ?? 0)} />
            </div>
            <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-5">
                <div className="text-h6 text-t-primary mb-4">Activity & health</div>
                <dl className="grid grid-cols-2 max-md:grid-cols-1 gap-x-6 gap-y-3.5">
                    <Fact label="Last login" value={fmtDate(h?.last_login)} />
                    <Fact label="Last activity" value={fmtDate(h?.last_activity)} />
                    <Fact label="Last call" value={fmtDate(h?.last_call_at)} />
                    <Fact label="Last campaign" value={fmtDate(h?.last_campaign_at)} />
                    <Fact
                        label="Open alerts"
                        value={
                            (h?.alerts ?? 0) > 0 ? <Badge variant="danger">{h?.alerts}</Badge> : <span className="text-t-secondary">None</span>
                        }
                    />
                </dl>
            </div>
        </div>
    );
}

function UsageTab({ vendor }: { vendor: AdminVendorDetail | null }) {
    const u = vendor?.usage;
    return (
        <div className="grid grid-cols-3 max-lg:grid-cols-2 max-sm:grid-cols-1 gap-3">
            <HeroCard label="Calls (30d)" glyph="chat" value={num(u?.calls_30d ?? 0)} />
            <HeroCard label="Minutes (30d)" glyph="clock" value={num(u?.minutes_30d ?? 0)} />
            <HeroCard label="Active now" glyph="dashboard" value={num(u?.active_now ?? 0)} />
            <HeroCard label="Leads" glyph="profile" value={num(u?.leads ?? 0)} />
            <HeroCard label="Campaigns" glyph="promote" value={num(u?.campaigns ?? 0)} />
            <HeroCard label="WhatsApp (30d)" glyph="chat" value={num(u?.whatsapp_30d ?? 0)} />
        </div>
    );
}

function BillingTab({ vendor }: { vendor: AdminVendorDetail | null }) {
    const w = vendor?.wallet;
    const l = vendor?.limits;
    const u = vendor?.usage;
    const cur = w?.currency || "INR";
    const money = (paise?: number) =>
        paise == null ? "—" : (paise / 100).toLocaleString(undefined, { style: "currency", currency: cur });
    return (
        <div className="space-y-5">
            <div className="grid grid-cols-3 max-sm:grid-cols-1 gap-3">
                <HeroCard label="Wallet balance" glyph="wallet" value={money(w?.balance)} />
                <HeroCard label="Held" glyph="lock" value={money(w?.held)} />
                <HeroCard label="Spend (30d)" glyph="usd-circle" value={money(u?.spend_30d)} />
            </div>
            <div className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset p-5">
                <div className="text-h6 text-t-primary mb-4">Plan limits vs usage</div>
                <dl className="grid grid-cols-2 max-md:grid-cols-1 gap-x-6 gap-y-3.5">
                    <Fact label="Max concurrency" value={l?.max_concurrency ?? "—"} />
                    <Fact label="Daily call cap" value={l?.daily_call_cap ?? "—"} />
                    <Fact label="Monthly minutes cap" value={l?.monthly_minutes_cap ?? "—"} />
                    <Fact label="Calls today" value={num(u?.calls_today ?? 0)} />
                    <Fact label="Minutes (30d)" value={num(u?.minutes_30d ?? 0)} />
                </dl>
            </div>
        </div>
    );
}

function AuditTab({ vendorId }: { vendorId: string }) {
    return (
        <div className="state-block">
            <span className="state-glyph">
                <Icon name="list" className="fill-inherit" />
            </span>
            <div className="state-title">Control audit</div>
            <div className="state-sub">
                This vendor&apos;s permission-change history (channel=control). Open the full filterable
                ledger in{" "}
                <Link href="/super-admin/audit" className="text-t-primary underline underline-offset-2">
                    Audit Logs
                </Link>{" "}
                — filtered to {vendorId}.
            </div>
        </div>
    );
}

// ───────── THE PERMISSION MATRIX ─────────
function PermissionsTab({
    vendor,
    busyKeys,
    onSet,
    onReset,
}: {
    vendor: AdminVendorDetail | null;
    busyKeys: Set<string>;
    onSet: (row: ResolvedEntitlement, mode: FeatureMode) => void;
    onReset: (row: ResolvedEntitlement) => void;
}) {
    // group rows by their top-level module (the SettingsPage section index)
    const groups = useMemo(() => groupByModule(vendor?.entitlements ?? []), [vendor?.entitlements]);

    if (!vendor || groups.length === 0) {
        return (
            <div className="state-block">
                <span className="state-glyph">
                    <Icon name="lock" className="fill-inherit" />
                </span>
                <div className="state-title">No features to govern</div>
                <div className="state-sub">The feature registry resolved empty for this vendor.</div>
            </div>
        );
    }

    return (
        <div className="flex gap-6 max-lg:flex-col">
            {/* Sticky section index (SettingsPage/Menu archetype) */}
            <nav className="w-48 shrink-0 max-lg:w-full">
                <div className="sticky top-24 max-lg:static space-y-1 max-lg:flex max-lg:flex-wrap max-lg:gap-1 max-lg:space-y-0">
                    {groups.map((g) => (
                        <a
                            key={g.module.key}
                            href={`#mod-${g.module.key}`}
                            className="block max-lg:inline-flex px-3 py-2 rounded-2xl text-button text-t-secondary hover:text-t-primary hover:bg-b-surface2 transition-colors"
                        >
                            {g.module.label}
                        </a>
                    ))}
                </div>
            </nav>

            {/* The matrix — a Card per module with EntitlementToggle rows */}
            <div className="flex-1 min-w-0 space-y-5">
                <p className="text-body-2 text-t-secondary">
                    Each feature is{" "}
                    <span className="text-primary-02 font-medium">On</span>,{" "}
                    <span className="text-primary-05 font-medium">Locked</span> (visible
                    upsell), or <span className="text-t-secondary font-medium">Hidden</span>. A per-vendor
                    choice shows an <Badge variant="warning" className="!text-caption !px-1.5 !py-0 align-middle">Override</Badge>{" "}
                    pill — Reset reverts it to the plan / global default.
                </p>

                {groups.map((g) => (
                    <div key={g.module.key} id={`mod-${g.module.key}`} className="rounded-3xl bg-b-surface2 ring-1 ring-s-subtle ring-inset overflow-hidden scroll-mt-24">
                        <div className="flex items-center justify-between gap-3 px-4 h-12 border-b border-s-subtle">
                            <div className="flex items-center gap-2.5">
                                <span className="text-h6 text-t-primary">{g.module.label}</span>
                                <ModeChip mode={g.module.mode} />
                            </div>
                            <span className="text-caption text-t-tertiary">{g.rows.length} feature{g.rows.length === 1 ? "" : "s"}</span>
                        </div>
                        <div className="divide-y divide-s-subtle">
                            {/* module row itself first */}
                            <EntitlementToggle
                                key={g.module.key}
                                row={g.module}
                                busy={busyKeys.has(g.module.key)}
                                onSet={(m) => onSet(g.module, m)}
                                onReset={() => onReset(g.module)}
                                depth={0}
                            />
                            {g.rows.map((r) => (
                                <EntitlementToggle
                                    key={r.key}
                                    row={r}
                                    busy={busyKeys.has(r.key)}
                                    onSet={(m) => onSet(r, m)}
                                    onReset={() => onReset(r)}
                                    depth={depthOf(r)}
                                />
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function ModeChip({ mode }: { mode: FeatureMode }) {
    if (mode === "hidden") return <Badge variant="neutral" className="!text-caption">Hidden</Badge>;
    if (mode === "locked") return <Badge variant="warning" className="!text-caption">Locked</Badge>;
    return <Badge variant="success" className="!text-caption">On</Badge>;
}

function TabSkeleton() {
    return (
        <div className="space-y-3">
            <div className="grid grid-cols-3 max-sm:grid-cols-1 gap-3">
                {[...Array(3)].map((_, i) => (
                    <div key={i} className="kpi">
                        <div className="skeleton h-4 w-24 mb-4" />
                        <div className="skeleton h-9 w-32" />
                    </div>
                ))}
            </div>
            {[...Array(3)].map((_, i) => (
                <div key={i} className="skeleton h-14 w-full rounded-2xl" />
            ))}
        </div>
    );
}

// ============================================================================
// helpers
// ============================================================================

function labelFor(m: FeatureMode): string {
    return m === "on" ? "On" : m === "locked" ? "Locked" : "Hidden";
}
function labelForStatus(s: VendorAccountStatus): string {
    return s.charAt(0).toUpperCase() + s.slice(1);
}

function depthOf(row: ResolvedEntitlement): number {
    // module=0, page=1, action/feature/integration under a page=2
    if (row.kind === "module") return 0;
    if (row.kind === "page" || row.kind === "integration") return 1;
    return 2;
}

type ModuleGroup = { module: ResolvedEntitlement; rows: ResolvedEntitlement[] };

// Group resolved rows by their top-level module, ordering children by sort_order.
// Integrations parented to a module are listed under that module.
function groupByModule(ents: ResolvedEntitlement[]): ModuleGroup[] {
    const byKey = new Map(ents.map((e) => [e.key, e]));
    const topModule = (e: ResolvedEntitlement): string => {
        let cur: ResolvedEntitlement | undefined = e;
        const seen = new Set<string>();
        while (cur && cur.parent_key && !seen.has(cur.key)) {
            seen.add(cur.key);
            const parent = byKey.get(cur.parent_key);
            if (!parent) break;
            cur = parent;
        }
        return cur?.key ?? e.key;
    };

    const modules = ents
        .filter((e) => e.kind === "module")
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));

    return modules.map((module) => {
        const rows = ents
            .filter((e) => e.key !== module.key && topModule(e) === module.key)
            .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
        return { module, rows };
    });
}

// Recompute parent rolldown locally (mirrors entitlements.py PASS B) so an
// optimistic module flip immediately tightens its subtree in the UI. strictness:
// hidden > locked > on. is_core children are never rolled down to hidden.
function rolldown(ents: ResolvedEntitlement[]): ResolvedEntitlement[] {
    const byKey = new Map(ents.map((e) => [e.key, e]));
    const STRICT: Record<FeatureMode, number> = { on: 0, locked: 1, hidden: 2 };
    // base = the row's own (override/plan/global) mode, BEFORE rolldown. We treat
    // the current `override` (or, if none, the row's stored default/plan) as base.
    const baseOf = (e: ResolvedEntitlement): FeatureMode =>
        e.override ?? e.plan_mode ?? e.default_mode ?? e.mode;

    return ents.map((e) => {
        let strictest = baseOf(e);
        let forcedByParent = false;
        let anc = e.parent_key ? byKey.get(e.parent_key) : undefined;
        const seen = new Set<string>();
        while (anc && !seen.has(anc.key)) {
            seen.add(anc.key);
            const ancBase = baseOf(anc);
            if (STRICT[ancBase] > STRICT[strictest]) {
                strictest = ancBase;
                forcedByParent = true;
            }
            anc = anc.parent_key ? byKey.get(anc.parent_key) : undefined;
        }
        if (e.is_core && strictest === "hidden") {
            strictest = baseOf(e) === "hidden" ? "on" : baseOf(e);
            forcedByParent = false;
        }
        const provenance: ResolvedEntitlement["provenance"] = forcedByParent
            ? "parent"
            : e.override != null
            ? "override"
            : e.plan_mode != null
            ? "plan"
            : "global";
        return { ...e, mode: strictest, provenance };
    });
}
