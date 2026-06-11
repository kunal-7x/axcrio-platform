"use client";

// ============================================================
// CL-F3 · Audit Logs — /super-admin/audit
//
// The filterable permission-change log. Every /admin/* write lands on the
// IMMUTABLE PG events leg (channel="control") with actor / target / before /
// after (spec §7). Ports the Core_2 Notifications archetype: a feed of rows +
// a filter rail (action select + search + date) and pagination.
// design/control-ui.md §2.7.
//
// Reads GET /audit?channel=control&limit=&offset=&action=  (read-only; append-only
// source -> no mutation here). Admin sees ALL tenants' control events.
//
// SECURITY: cosmetic admin view; require_super_admin/admin-scope is the boundary.
// The log itself is tamper-proof (events leg is INSERT-only).
// ============================================================

import { useEffect, useMemo, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Search from "@/components/Search";
import Select from "@/components/Select";
import Spinner from "@/components/Spinner";
import { getControlAudit, type AuditEvent } from "@/lib/api";
import {
    SuperAdminGuard,
    SuperAdminHeaderF3,
    humanizeAction,
    fmtDateTime,
    ago,
    ErrorBanner,
    ghostBtnCls,
} from "../_shared";
import type { SelectOption } from "@/types/select";

const PAGE = 50;

// action -> badge tone (set/assign = info, status/suspend = warning, impersonate/
// disable/denied = danger, clear/exit = neutral).
function actionVariant(action: string): "info" | "warning" | "danger" | "neutral" | "success" {
    const a = action.toLowerCase();
    if (/(impersonate|disabled|denied|freeze|revoke)/.test(a)) return "danger";
    if (/(suspend|status|stepup)/.test(a)) return "warning";
    if (/(clear|exit|stop)/.test(a)) return "neutral";
    if (/(create|topup|credit)/.test(a)) return "success";
    return "info";
}

// Action filter options. id 1 = All; the rest map to an action prefix the
// backend filters on server-side (?action=).
const ACTION_OPTIONS: SelectOption[] = [
    { id: 1, name: "All actions" },
    { id: 2, name: "Overrides" },
    { id: 3, name: "Global flags" },
    { id: 4, name: "Plans" },
    { id: 5, name: "Status changes" },
    { id: 6, name: "Credits" },
    { id: 7, name: "Impersonation" },
];
const ACTION_PREFIX: Record<number, string> = {
    1: "",
    2: "control.override",
    3: "control.flag",
    4: "control.plan",
    5: "control.status",
    6: "control.credit",
    7: "control.impersonate",
};

function ValueChip({ label, value, tone }: { label: string; value?: string | null; tone: string }) {
    if (value == null || value === "") return null;
    return (
        <span className="inline-flex items-center gap-1 text-caption">
            <span className="text-t-tertiary">{label}</span>
            <span className={`px-1.5 py-0.5 rounded-md font-mono ${tone}`}>{value}</span>
        </span>
    );
}

export default function AuditLogPage() {
    const [events, setEvents] = useState<AuditEvent[]>([]);
    const [total, setTotal] = useState(0);
    const [offset, setOffset] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [search, setSearch] = useState("");
    const [actionFilter, setActionFilter] = useState<SelectOption>(ACTION_OPTIONS[0]);

    const load = useCallback(
        (off: number, action: string) => {
            setLoading(true);
            setError("");
            getControlAudit({ limit: PAGE, offset: off, action })
                .then((r) => {
                    setEvents(r.events);
                    setTotal(r.total);
                    setOffset(r.offset);
                })
                .catch((e) => setError(e instanceof Error ? e.message : "Failed to load audit log"))
                .finally(() => setLoading(false));
        },
        []
    );

    useEffect(() => {
        load(0, ACTION_PREFIX[Number(actionFilter.id)] ?? "");
    }, [load, actionFilter]);

    // client-side free-text filter over the already-fetched page (actor / target /
    // feature / reason). Server already filtered by action + channel.
    const rows = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return events;
        return events.filter((e) => {
            const m = e.meta || {};
            return (
                e.action.toLowerCase().includes(q) ||
                (e.actor || "").toLowerCase().includes(q) ||
                (m.target_tenant || "").toLowerCase().includes(q) ||
                (m.feature_key || "").toLowerCase().includes(q) ||
                (m.reason || "").toLowerCase().includes(q)
            );
        });
    }, [events, search]);

    const page = Math.floor(offset / PAGE) + 1;
    const pages = Math.max(1, Math.ceil(total / PAGE));
    const prefix = ACTION_PREFIX[Number(actionFilter.id)] ?? "";

    return (
        <SuperAdminGuard>
            <Layout title="Audit">
                <SuperAdminHeaderF3
                    actions={
                        <button
                            onClick={() => load(offset, prefix)}
                            className={ghostBtnCls}
                            disabled={loading}
                        >
                            <Icon name="clock" className={`size-4 fill-current ${loading ? "animate-spin" : ""}`} />
                            {loading ? "Refreshing…" : "Refresh"}
                        </button>
                    }
                />
                <ErrorBanner msg={error} />

                {/* filter rail */}
                <div className="flex items-center gap-3 mb-5 flex-wrap">
                    <div className="w-64 max-md:w-full">
                        <Search
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search actor, vendor, feature…"
                            isGray
                        />
                    </div>
                    <Select
                        className="min-w-48"
                        value={actionFilter}
                        onChange={setActionFilter}
                        options={ACTION_OPTIONS}
                    />
                    <div className="ml-auto text-caption text-t-tertiary tabular-nums">
                        {total.toLocaleString()} event{total === 1 ? "" : "s"} · channel=control
                    </div>
                </div>

                <Card title="Control activity">
                    {loading && events.length === 0 ? (
                        <div className="py-20">
                            <Spinner />
                        </div>
                    ) : rows.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="check-circle" className="fill-inherit" />
                            </span>
                            <div className="state-title">No control events</div>
                            <div className="state-sub">
                                {total === 0
                                    ? "No super-admin actions have been recorded yet."
                                    : "No event on this page matches your search."}
                            </div>
                        </div>
                    ) : (
                        <div className="divide-y divide-s-subtle">
                            {rows.map((e, i) => {
                                const m = e.meta || {};
                                const when = e.ts || (e.epoch ? new Date(e.epoch * 1000).toISOString() : undefined);
                                return (
                                    <div
                                        key={`${e.epoch ?? i}-${i}`}
                                        className="flex items-start gap-4 px-5 py-3.5 max-md:px-3 max-md:flex-col max-md:gap-2"
                                    >
                                        <div className="flex items-center gap-2 shrink-0 w-44 max-md:w-full">
                                            <Badge variant={actionVariant(e.action)}>{humanizeAction(e.action)}</Badge>
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-body-2">
                                                {m.feature_key && (
                                                    <span className="font-mono text-t-primary truncate">{m.feature_key}</span>
                                                )}
                                                {m.target_tenant && (
                                                    <span className="text-t-secondary">
                                                        vendor <span className="font-mono text-t-primary">{m.target_tenant}</span>
                                                    </span>
                                                )}
                                            </div>
                                            <div className="flex items-center gap-x-3 gap-y-1 flex-wrap mt-1">
                                                <ValueChip
                                                    label="from"
                                                    value={m.old_value}
                                                    tone="bg-shade-08/40 text-t-secondary dark:bg-shade-04"
                                                />
                                                {m.old_value != null && m.new_value != null && (
                                                    <Icon name="arrow" className="size-3 fill-t-tertiary" />
                                                )}
                                                <ValueChip
                                                    label="to"
                                                    value={m.new_value}
                                                    tone="bg-primary-01/10 text-primary-01"
                                                />
                                                {m.reason && (
                                                    <span className="text-caption text-t-tertiary italic truncate">
                                                        “{m.reason}”
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                        <div className="shrink-0 text-right max-md:text-left">
                                            <div className="text-body-2 text-t-secondary">
                                                {m.real_admin || e.actor || "—"}
                                            </div>
                                            <div
                                                className="text-caption text-t-tertiary whitespace-nowrap"
                                                title={fmtDateTime(when)}
                                            >
                                                {ago(when)}
                                                {m.auth_method && m.auth_method !== "jwt" && (
                                                    <span className="ml-1.5">· {m.auth_method}</span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </Card>

                {/* pagination */}
                {pages > 1 && (
                    <div className="flex items-center justify-between gap-3 mt-4">
                        <button
                            onClick={() => load(Math.max(0, offset - PAGE), prefix)}
                            disabled={loading || offset === 0}
                            className={ghostBtnCls}
                        >
                            <Icon name="chevron" className="size-4 fill-current rotate-90" />
                            Newer
                        </button>
                        <div className="text-caption text-t-tertiary tabular-nums">
                            Page {page} of {pages}
                        </div>
                        <button
                            onClick={() => load(offset + PAGE, prefix)}
                            disabled={loading || offset + PAGE >= total}
                            className={ghostBtnCls}
                        >
                            Older
                            <Icon name="chevron" className="size-4 fill-current -rotate-90" />
                        </button>
                    </div>
                )}
            </Layout>
        </SuperAdminGuard>
    );
}
