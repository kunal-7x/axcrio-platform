"use client";

// Forms & Surveys — the lead-capture + feedback workspace.
//
// A form/survey builder: define a public form, publish it on an unguessable
// token, and every submission feeds the CRM person spine + (when wired) the
// leads store and workflow triggers. Surveys add deterministic NPS/CSAT insights.
//
// The forms-surveys router is MOUNTED but FEATURE_FORMS defaults OFF on the live
// API, so the graceful "not configured / coming soon" path is the PRIMARY state
// right now — every read degrades to a calm dormant view rather than an error
// wall. Built entirely on the ported Core_2 kit (Layout/Card/Search/Tabs/Select/
// Table/TableRow/Button/Modal). Edits only this route's own files under app/forms.

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Search from "@/components/Search";
import Tabs from "@/components/Tabs";
import Select from "@/components/Select";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import { useMe, canWrite } from "@/lib/auth";
import {
    listForms,
    FormsDormantError,
    type Form,
    type FormKind,
    type FormStatus,
} from "./client";
import { StatusBadge, KindBadge, kindIcon, fmtRelative } from "./_ui";
import CreateFormModal from "./CreateFormModal";

const KIND_TABS = [
    { id: 1, name: "All", key: "all" as FormKind | "all" },
    { id: 2, name: "Forms", key: "form" as FormKind | "all" },
    { id: 3, name: "Surveys", key: "survey" as FormKind | "all" },
];

const STATUS_OPTIONS = [
    { id: 1, name: "All statuses", key: "all" as FormStatus | "all" },
    { id: 2, name: "Published", key: "published" as FormStatus | "all" },
    { id: 3, name: "Draft", key: "draft" as FormStatus | "all" },
    { id: 4, name: "Closed", key: "closed" as FormStatus | "all" },
];

const tableHead = ["Form", "Type", "Status", "Responses", "Updated"];

export default function FormsWorkspacePage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [forms, setForms] = useState<Form[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState("");

    const [kindTab, setKindTab] = useState(KIND_TABS[0]);
    const [statusOpt, setStatusOpt] = useState(STATUS_OPTIONS[0]);
    const [query, setQuery] = useState("");
    const [createOpen, setCreateOpen] = useState(false);

    const kind = kindTab.key;
    const status = statusOpt.key;

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        listForms({
            kind: kind !== "all" ? kind : "",
            status: status !== "all" ? status : "",
        })
            .then((r) => {
                setForms(r.forms || []);
                setTotal(r.total ?? (r.forms || []).length);
                setDormant(false);
            })
            .catch((e: unknown) => {
                if (e instanceof FormsDormantError) {
                    setDormant(true);
                    setForms([]);
                    setTotal(0);
                } else {
                    setError(
                        e instanceof Error ? e.message : "Failed to load forms"
                    );
                }
            })
            .finally(() => setLoading(false));
    }, [kind, status]);

    useEffect(() => {
        load();
    }, [load]);

    const visible = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return forms;
        return forms.filter(
            (f) =>
                f.title?.toLowerCase().includes(q) ||
                f.id?.toLowerCase().includes(q)
        );
    }, [forms, query]);

    // Real summary signals over the loaded set (never a fabricated delta).
    const summary = useMemo(() => {
        const n = forms.length;
        const published = forms.filter((f) => f.status === "published").length;
        const surveys = forms.filter((f) => f.kind === "survey").length;
        const responses = forms.reduce(
            (a, f) => a + (Number(f.submit_count) || 0),
            0
        );
        return { n, published, surveys, responses };
    }, [forms]);

    const hasFilters = !!query || kind !== "all" || status !== "all";
    const clearFilters = () => {
        setQuery("");
        setKindTab(KIND_TABS[0]);
        setStatusOpt(STATUS_OPTIONS[0]);
    };

    return (
        <Layout title="Forms & Surveys">
            {dormant ? (
                <Card title="Forms & Surveys">
                    <DormantBody />
                </Card>
            ) : (
                <div className="flex flex-col gap-3">
                    {/* ── Overview metric strip (Core_2 Overview archetype) ── */}
                    <Card
                        title="Overview"
                        headContent={
                            writable ? (
                                <Button
                                    className="ml-auto mr-3"
                                    isBlack
                                    icon="plus"
                                    onClick={() => setCreateOpen(true)}
                                >
                                    New form
                                </Button>
                            ) : undefined
                        }
                    >
                        <div className="flex gap-8 px-5 pb-5 pt-1 max-lg:gap-6 max-lg:px-3 max-lg:overflow-auto max-lg:scrollbar-none">
                            <MetricItem
                                icon="font"
                                title="Total forms"
                                value={loading ? "—" : total}
                                sub={
                                    loading
                                        ? undefined
                                        : total === 0
                                        ? "Create your first form"
                                        : `${summary.surveys} survey${
                                              summary.surveys === 1 ? "" : "s"
                                          }`
                                }
                            />
                            <MetricItem
                                icon="check-circle"
                                title="Published"
                                value={loading ? "—" : summary.published}
                                sub={
                                    loading || summary.n === 0
                                        ? undefined
                                        : `${Math.round(
                                              (summary.published / summary.n) * 100
                                          )}% live`
                                }
                                accent
                            />
                            <MetricItem
                                icon="list"
                                title="Responses"
                                value={loading ? "—" : summary.responses}
                                sub={
                                    loading
                                        ? undefined
                                        : summary.responses === 0
                                        ? "Awaiting first submission"
                                        : "Across all forms"
                                }
                            />
                            <MetricItem
                                icon="chart"
                                title="Surveys"
                                value={loading ? "—" : summary.surveys}
                                sub={
                                    loading
                                        ? undefined
                                        : summary.surveys === 0
                                        ? "NPS / CSAT ready"
                                        : "With live insights"
                                }
                            />
                        </div>
                    </Card>

                    {/* ── List/Table archetype (Core_2 CustomerListPage) ── */}
                    <div className="card">
                        <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                            <div className="pl-5 text-h6 max-lg:pl-3 max-md:w-full">
                                Your forms
                            </div>
                            <Search
                                className="w-70 ml-6 mr-auto max-lg:w-56 max-md:w-full max-md:ml-0"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                placeholder="Search by title"
                                isGray
                            />
                            {query === "" && (
                                <>
                                    <Select
                                        className="min-w-40 mr-3 max-md:w-full max-md:mr-0"
                                        value={statusOpt}
                                        onChange={(v) =>
                                            setStatusOpt(
                                                v as (typeof STATUS_OPTIONS)[number]
                                            )
                                        }
                                        options={STATUS_OPTIONS}
                                    />
                                    <Tabs
                                        className="max-md:w-full"
                                        items={KIND_TABS}
                                        value={kindTab}
                                        setValue={(v) =>
                                            setKindTab(
                                                v as (typeof KIND_TABS)[number]
                                            )
                                        }
                                    />
                                </>
                            )}
                        </div>

                        {error && (
                            <div className="mx-5 mt-3 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03 max-lg:mx-3">
                                <Icon
                                    name="info"
                                    className="size-4 shrink-0 fill-primary-03"
                                />
                                {error}
                            </div>
                        )}

                        <div className="p-1 pt-3 max-lg:px-0">
                            {loading ? (
                                <TableSkeleton />
                            ) : visible.length === 0 ? (
                                <EmptyState
                                    query={query}
                                    hasFilters={hasFilters}
                                    writable={writable}
                                    onClear={clearFilters}
                                    onCreate={() => setCreateOpen(true)}
                                />
                            ) : (
                                <Table
                                    cellsThead={tableHead.map((head) => (
                                        <th
                                            className={
                                                head === "Responses" ||
                                                head === "Updated"
                                                    ? "text-right max-md:hidden"
                                                    : head === "Type"
                                                    ? "max-lg:hidden"
                                                    : ""
                                            }
                                            key={head}
                                        >
                                            {head}
                                        </th>
                                    ))}
                                >
                                    {visible.map((f) => (
                                        <TableRow key={f.id}>
                                            <td className="font-medium text-t-primary">
                                                <Link
                                                    href={`/forms/${encodeURIComponent(
                                                        f.id
                                                    )}`}
                                                    className="flex items-center gap-3"
                                                >
                                                    <span className="grid place-items-center size-11 shrink-0 rounded-full bg-b-surface1 text-t-secondary">
                                                        <Icon
                                                            name={kindIcon(
                                                                f.kind
                                                            )}
                                                            className="size-5 fill-t-secondary"
                                                        />
                                                    </span>
                                                    <span className="min-w-0">
                                                        <span className="block truncate max-w-64 text-sub-title-1 text-t-primary">
                                                            {f.title ||
                                                                "Untitled form"}
                                                        </span>
                                                        <span className="block truncate max-w-64 text-body-2 text-t-tertiary">
                                                            {f.fields?.length ||
                                                                0}{" "}
                                                            field
                                                            {f.fields?.length ===
                                                            1
                                                                ? ""
                                                                : "s"}
                                                        </span>
                                                    </span>
                                                </Link>
                                            </td>
                                            <td className="max-lg:hidden">
                                                <KindBadge kind={f.kind} />
                                            </td>
                                            <td>
                                                <StatusBadge
                                                    status={f.status}
                                                />
                                            </td>
                                            <td className="text-right text-t-secondary max-md:hidden">
                                                {Number(f.submit_count) || 0}
                                            </td>
                                            <td className="text-right text-t-secondary max-md:hidden">
                                                {fmtRelative(f.updated_at)}
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <CreateFormModal
                open={createOpen}
                onClose={() => setCreateOpen(false)}
                onCreated={() => {
                    setCreateOpen(false);
                    load();
                }}
            />
        </Layout>
    );
}

// ── Core_2 Overview metric tile (ported inline) ──
function MetricItem({
    icon,
    title,
    value,
    sub,
    accent,
}: {
    icon: string;
    title: string;
    value: React.ReactNode;
    sub?: React.ReactNode;
    accent?: boolean;
}) {
    return (
        <div className="flex-1 min-w-44 pr-8 border-r border-s-subtle last:border-r-0 last:pr-0 max-lg:shrink-0">
            <div
                className={`flex items-center justify-center size-12 mb-6 rounded-full ${
                    accent ? "bg-primary-02/12" : "bg-b-surface1"
                }`}
            >
                <Icon
                    className={accent ? "fill-primary-02" : "fill-t-primary"}
                    name={icon}
                />
            </div>
            <div className="text-sub-title-1 text-t-secondary mb-2">{title}</div>
            <div className="text-h3">{value}</div>
            {sub && (
                <div className="mt-2 text-body-2 text-t-tertiary">{sub}</div>
            )}
        </div>
    );
}

function TableSkeleton() {
    return (
        <Table cellsThead={tableHead.map((head) => <th key={head}>{head}</th>)}>
            {[...Array(6)].map((_, i) => (
                <TableRow key={i}>
                    {[...Array(5)].map((__, j) => (
                        <td key={j}>
                            <div
                                className={`skeleton h-4 rounded-lg ${
                                    j === 0 ? "w-44" : j >= 3 ? "w-14 ml-auto" : "w-20"
                                }`}
                            />
                        </td>
                    ))}
                </TableRow>
            ))}
        </Table>
    );
}

function EmptyState({
    query,
    hasFilters,
    writable,
    onClear,
    onCreate,
}: {
    query: string;
    hasFilters: boolean;
    writable: boolean;
    onClear: () => void;
    onCreate: () => void;
}) {
    const fresh = !hasFilters;
    return (
        <div className="py-16 text-center max-md:py-12">
            <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                <Icon
                    name={query ? "search" : "font"}
                    className="fill-t-tertiary"
                />
            </span>
            <div className="text-h6 mb-1">
                {query
                    ? "No matching forms"
                    : hasFilters
                    ? "No forms match these filters"
                    : "No forms yet"}
            </div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                {query
                    ? `Nothing matches “${query}”.`
                    : "Create a form or survey to start capturing leads and feedback — each submission builds a CRM contact automatically."}
            </div>
            {fresh && writable ? (
                <Button className="mt-5" isStroke icon="plus" onClick={onCreate}>
                    New form
                </Button>
            ) : (
                hasFilters && (
                    <Button className="mt-5" isStroke onClick={onClear}>
                        Clear filters
                    </Button>
                )
            )}
        </div>
    );
}

function DormantBody() {
    return (
        <div className="py-16 text-center max-md:py-12">
            <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                <Icon name="font" className="fill-t-tertiary" />
            </span>
            <div className="text-h6 mb-1">Forms &amp; Surveys is being prepared</div>
            <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                The form builder lets you publish lead-capture forms and feedback
                surveys on a private link. Every submission becomes a CRM contact
                automatically, and surveys roll up into live NPS &amp; CSAT insights.
                This view lights up the moment the module is enabled for your
                workspace — nothing for you to do.
            </div>
            <span className="inline-block mt-5 px-3 h-8 leading-8 rounded-full bg-b-surface1 text-button text-t-secondary">
                Coming soon
            </span>
        </div>
    );
}
