"use client";

// ============================================================
// CL-F3 · Feature Flags (GLOBAL) — /super-admin/flags
//
// The GLOBAL on/off (3-state) grid: each feature's default_mode, the baseline
// EVERY vendor inherits unless a plan or per-vendor override wins. Ports the
// Core_2 SettingsPage archetype (sticky section index + sectioned Cards): the
// left module index jumps to each module's card; each row is the 3-state
// On / Locked / Hidden segmented control (design/control-ui.md §3, §2.4).
//
// Writes PUT /admin/flags/{feature_key} (audited server-side, bumps every
// tenant's ent_version). Core (is_core) rows render the control with Lock/Hide
// DISABLED — the self-lockout floor (login/settings/billing-pay can't vanish).
//
// SECURITY: cosmetic admin view. The backend require_super_admin gate (403 for
// vendors / legacy-pw) is the boundary; this never grants access.
// ============================================================

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Search from "@/components/Search";
import Spinner from "@/components/Spinner";
import {
    getAdminFeatures,
    getAdminFlags,
    setAdminFlag,
    type FeatureRegistryRow,
    type FeatureMode,
} from "@/lib/api";
import {
    SuperAdminGuard,
    SuperAdminHeaderF3,
    KIND_META,
    MODE_ORDER,
    ErrorBanner,
    ToastView,
    type Toast,
    ghostBtnCls,
} from "../_shared";

// ---- the 3-state segmented control (On / Locked / Hidden) ------------------
// design §3: 3-state != a boolean Switch, so the segmented group is the primary
// control — styled like the kit's Tabs pill (border-s-stroke2 active). On=green,
// Locked=amber, Hidden=grey. Core features render Lock/Hide disabled.
const SEG: Record<FeatureMode, { label: string; active: string }> = {
    on: { label: "On", active: "bg-primary-02/12 text-primary-02 border-primary-02/30" },
    locked: { label: "Lock", active: "bg-primary-05/12 text-primary-05 border-primary-05/30" },
    hidden: { label: "Hide", active: "bg-b-surface1 text-t-primary border-s-stroke2 dark:bg-shade-04" },
};

function ModeSegment({
    value,
    onChange,
    disabledModes,
    busy,
}: {
    value: FeatureMode;
    onChange: (m: FeatureMode) => void;
    disabledModes?: FeatureMode[];
    busy?: boolean;
}) {
    return (
        <div className="inline-flex items-center gap-1 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle shrink-0">
            {MODE_ORDER.map((m) => {
                const isActive = value === m;
                const isDisabled = busy || (disabledModes?.includes(m) ?? false);
                return (
                    <button
                        key={m}
                        type="button"
                        disabled={isDisabled}
                        onClick={() => !isActive && !isDisabled && onChange(m)}
                        className={`inline-flex items-center justify-center h-7 px-3 rounded-full text-caption font-medium border transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                            isActive
                                ? SEG[m].active
                                : "border-transparent text-t-secondary hover:text-t-primary"
                        }`}
                    >
                        {SEG[m].label}
                    </button>
                );
            })}
        </div>
    );
}

type Group = { key: string; label: string; rows: FeatureRegistryRow[] };

export default function FeatureFlagsPage() {
    const [features, setFeatures] = useState<FeatureRegistryRow[]>([]);
    const [flags, setFlags] = useState<Record<string, FeatureMode>>({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [search, setSearch] = useState("");
    const [busyKey, setBusyKey] = useState<string | null>(null);
    const [toast, setToast] = useState<Toast | null>(null);
    const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 3500);
    };

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        Promise.all([getAdminFeatures(), getAdminFlags()])
            .then(([f, fl]) => {
                setFeatures(f.features);
                // seed effective flag value from /admin/flags, falling back to the
                // registry default_mode so a row always renders a state.
                const map: Record<string, FeatureMode> = { ...fl.flags };
                for (const row of f.features) {
                    if (!(row.key in map)) map[row.key] = row.default_mode;
                }
                setFlags(map);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load feature flags"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    // group by top-level module: a row's module is the first dot-segment of its
    // key (e.g. "engage.calls" -> "engage"), or the key itself for a module row.
    const groups = useMemo<Group[]>(() => {
        const q = search.trim().toLowerCase();
        const byModule = new Map<string, FeatureRegistryRow[]>();
        const moduleLabels = new Map<string, string>();
        for (const r of features) {
            if (r.kind === "module") moduleLabels.set(r.key, r.label || r.key);
        }
        for (const r of features) {
            if (r.kind === "module") continue; // module header rows are the section title
            if (
                q &&
                !(r.label.toLowerCase().includes(q) || r.key.toLowerCase().includes(q))
            )
                continue;
            const mod = r.key.split(".")[0];
            if (!byModule.has(mod)) byModule.set(mod, []);
            byModule.get(mod)!.push(r);
        }
        const out: Group[] = [];
        for (const [mod, rows] of byModule) {
            rows.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.key.localeCompare(b.key));
            out.push({
                key: mod,
                label: moduleLabels.get(mod) || mod.replace(/\b\w/g, (c) => c.toUpperCase()),
                rows,
            });
        }
        out.sort((a, b) => a.label.localeCompare(b.label));
        return out;
    }, [features, search]);

    async function setMode(key: string, mode: FeatureMode) {
        const prev = flags[key];
        setBusyKey(key);
        setFlags((f) => ({ ...f, [key]: mode })); // optimistic
        try {
            await setAdminFlag(key, mode);
            showToast(`Global flag updated — applies to all vendors`, "success");
        } catch (e) {
            setFlags((f) => ({ ...f, [key]: prev })); // rollback
            showToast(e instanceof Error ? e.message : "Failed to set flag", "error");
        } finally {
            setBusyKey(null);
        }
    }

    function jumpTo(mod: string) {
        sectionRefs.current[mod]?.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    return (
        <SuperAdminGuard>
            <Layout title="Feature Flags">
                <SuperAdminHeaderF3
                    actions={
                        <button onClick={load} className={ghostBtnCls} disabled={loading}>
                            <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                            {loading ? "Refreshing…" : "Refresh"}
                        </button>
                    }
                />
                <ToastView toast={toast} onClose={() => setToast(null)} />
                <ErrorBanner msg={error} />

                <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
                    <div className="w-full max-w-md">
                        <Search
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search features…"
                            isGray
                        />
                    </div>
                    <p className="text-body-2 text-t-secondary max-md:w-full">
                        Global baseline for every vendor — a plan or override wins. Core features can’t be hidden.
                    </p>
                </div>

                {loading && features.length === 0 ? (
                    <div className="py-24">
                        <Spinner />
                    </div>
                ) : groups.length === 0 ? (
                    <Card title="Feature catalog">
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="search" className="fill-inherit" />
                            </span>
                            <div className="state-title">No features match</div>
                            <div className="state-sub">
                                {features.length === 0
                                    ? "The control plane is not enabled yet, or no features are registered."
                                    : "Try a different search term."}
                            </div>
                        </div>
                    </Card>
                ) : (
                    <div className="flex gap-6 items-start max-lg:flex-col">
                        {/* sticky module index (SettingsPage/Menu archetype) */}
                        <nav className="sticky top-22 shrink-0 w-52 max-lg:static max-lg:w-full">
                            <div className="card p-2">
                                {groups.map((g) => (
                                    <button
                                        key={g.key}
                                        onClick={() => jumpTo(g.key)}
                                        className="flex items-center justify-between w-full px-3 py-2.5 rounded-2xl text-button text-t-secondary transition-colors hover:bg-b-surface1 hover:text-t-primary dark:hover:bg-shade-04 text-left"
                                    >
                                        <span className="truncate">{g.label}</span>
                                        <span className="text-caption text-t-tertiary tabular-nums">{g.rows.length}</span>
                                    </button>
                                ))}
                            </div>
                        </nav>

                        {/* one Card per module, each a list of EntitlementToggle-style rows */}
                        <div className="flex-1 min-w-0 flex flex-col gap-6">
                            {groups.map((g) => (
                                <div
                                    key={g.key}
                                    ref={(el) => {
                                        sectionRefs.current[g.key] = el;
                                    }}
                                    className="scroll-mt-22"
                                >
                                    <Card title={g.label}>
                                        <div className="divide-y divide-s-subtle">
                                            {g.rows.map((r) => {
                                                const mode = flags[r.key] ?? r.default_mode;
                                                const kind = KIND_META[r.kind] ?? KIND_META.feature;
                                                return (
                                                    <div
                                                        key={r.key}
                                                        className="flex items-center justify-between gap-4 px-5 py-3.5 max-md:px-3 max-md:flex-col max-md:items-start"
                                                    >
                                                        <div className="min-w-0">
                                                            <div className="flex items-center gap-2 flex-wrap">
                                                                <span className="text-body-2 font-medium text-t-primary truncate">
                                                                    {r.label || r.key}
                                                                </span>
                                                                <Badge variant={kind.variant}>{kind.label}</Badge>
                                                                {r.is_core && (
                                                                    <Badge variant="info">Core</Badge>
                                                                )}
                                                            </div>
                                                            <div className="text-caption text-t-tertiary mt-0.5 font-mono truncate">
                                                                {r.key}
                                                                {r.is_core && (
                                                                    <span className="ml-2 text-t-tertiary">
                                                                        · cannot be hidden (anti-lockout)
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </div>
                                                        <ModeSegment
                                                            value={mode}
                                                            onChange={(m) => setMode(r.key, m)}
                                                            // core: only "on" is selectable (Lock/Hide disabled)
                                                            disabledModes={r.is_core ? ["locked", "hidden"] : undefined}
                                                            busy={busyKey === r.key}
                                                        />
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </Card>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </Layout>
        </SuperAdminGuard>
    );
}
