"use client";

// Forms & Surveys — the lead-capture + feedback workspace.
//
// A form/survey builder: define a public form, publish it on an unguessable
// token, and every submission feeds the CRM person spine + (when wired) the
// leads store and workflow triggers. Surveys add deterministic NPS/CSAT insights.
//
// The forms-surveys router is DEFINED-NOT-MOUNTED on the live API today (deferred
// mount checklist), so the graceful "not configured / coming soon" path is the
// PRIMARY state right now — every read degrades to a premium dormant view rather
// than an error wall. Built entirely on the in-app "Signal" component language
// (Layout/PageHeader/Card/KpiCard/Badge/Modal/Button/Icon) + the verified
// globals.css utilities. Edits only this route's own files under app/forms.

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import PageHeader from "@/components/PageHeader";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import KpiCard from "@/components/KpiCard";
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

const KIND_FILTERS: { id: FormKind | "all"; label: string }[] = [
    { id: "all", label: "All" },
    { id: "form", label: "Forms" },
    { id: "survey", label: "Surveys" },
];

const STATUS_FILTERS: { id: FormStatus | "all"; label: string }[] = [
    { id: "all", label: "All statuses" },
    { id: "published", label: "Published" },
    { id: "draft", label: "Draft" },
    { id: "closed", label: "Closed" },
];

export default function FormsWorkspacePage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [forms, setForms] = useState<Form[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [error, setError] = useState("");

    const [kind, setKind] = useState<FormKind | "all">("all");
    const [status, setStatus] = useState<FormStatus | "all">("all");
    const [query, setQuery] = useState("");
    const [createOpen, setCreateOpen] = useState(false);

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
        return {
            n,
            published,
            surveys,
            responses,
            publishedRatio: n > 0 ? published / n : 0,
            surveyRatio: n > 0 ? surveys / n : 0,
        };
    }, [forms]);

    return (
        <Layout title="Forms & Surveys">
            <PageHeader
                eyebrow="Lead capture & feedback"
                title="Forms & Surveys"
                subtitle="Build public forms and surveys that feed the CRM spine on every submission — with deterministic NPS / CSAT insights, allow-list validation, and built-in anti-abuse."
                actions={
                    writable && !dormant ? (
                        <Button
                            isBlack
                            icon="plus"
                            onClick={() => setCreateOpen(true)}
                        >
                            New form
                        </Button>
                    ) : undefined
                }
            />

            {dormant ? (
                <Card title="Forms & Surveys">
                    <div className="state-block py-16">
                        <span className="state-glyph">
                            <Icon name="font" className="fill-inherit" />
                        </span>
                        <div className="state-title">
                            Forms &amp; Surveys is being prepared
                        </div>
                        <div className="state-sub max-w-md">
                            The form builder lets you publish lead-capture forms and
                            feedback surveys on a private link. Every submission
                            becomes a CRM contact automatically, and surveys roll up
                            into live NPS &amp; CSAT insights. This view lights up the
                            moment the module is enabled for your workspace — nothing
                            for you to do.
                        </div>
                        <span className="nav-soon mt-1">Coming soon</span>
                    </div>
                </Card>
            ) : (
                <>
                    {/* Hero KPI row — real meters over the loaded set */}
                    <div className="grid grid-cols-4 gap-3 mb-3 max-lg:grid-cols-2 max-sm:grid-cols-1">
                        <KpiCard
                            label="Total forms"
                            value={loading ? "—" : total}
                            icon="font"
                            tone="info"
                            sub={
                                loading
                                    ? undefined
                                    : total === 0
                                    ? "Create your first form"
                                    : `${summary.surveys} survey${
                                          summary.surveys === 1 ? "" : "s"
                                      }`
                            }
                            meter={loading ? null : summary.surveyRatio}
                            style={{ animationDelay: "0ms" }}
                        />
                        <KpiCard
                            label="Published"
                            value={loading ? "—" : summary.published}
                            icon="check-circle"
                            tone="success"
                            sub={
                                loading || summary.n === 0
                                    ? undefined
                                    : `${Math.round(
                                          summary.publishedRatio * 100
                                      )}% live`
                            }
                            meter={loading ? null : summary.publishedRatio}
                            style={{ animationDelay: "60ms" }}
                        />
                        <KpiCard
                            label="Responses"
                            value={loading ? "—" : summary.responses}
                            icon="list"
                            tone="warning"
                            sub={
                                loading
                                    ? undefined
                                    : summary.responses === 0
                                    ? "Awaiting first submission"
                                    : "Across all forms"
                            }
                            style={{ animationDelay: "120ms" }}
                        />
                        <KpiCard
                            label="Surveys"
                            value={loading ? "—" : summary.surveys}
                            icon="chart"
                            tone="neutral"
                            sub={
                                loading
                                    ? undefined
                                    : summary.surveys === 0
                                    ? "NPS / CSAT ready"
                                    : "With live insights"
                            }
                            meter={loading ? null : summary.surveyRatio}
                            style={{ animationDelay: "180ms" }}
                        />
                    </div>

                    <Card
                        title="Your forms"
                        headContent={
                            <div className="flex items-center gap-2.5 max-md:gap-2">
                                <label className="relative hidden sm:flex items-center">
                                    <Icon
                                        name="search"
                                        className="absolute left-3 size-4 fill-t-tertiary pointer-events-none"
                                    />
                                    <input
                                        value={query}
                                        onChange={(e) => setQuery(e.target.value)}
                                        placeholder="Search by title"
                                        className="input-base h-9 w-56 max-lg:w-40 pl-9 pr-3 rounded-full text-body-2"
                                    />
                                </label>
                                <select
                                    value={status}
                                    onChange={(e) =>
                                        setStatus(
                                            e.target.value as FormStatus | "all"
                                        )
                                    }
                                    className="input-base h-9 px-3 rounded-full text-body-2 max-md:hidden"
                                    aria-label="Filter by status"
                                >
                                    {STATUS_FILTERS.map((s) => (
                                        <option key={s.id} value={s.id}>
                                            {s.label}
                                        </option>
                                    ))}
                                </select>
                                <div className="inline-flex p-1 rounded-full bg-b-surface1 border border-s-subtle dark:bg-shade-04/40">
                                    {KIND_FILTERS.map((k) => (
                                        <SegBtn
                                            key={k.id}
                                            active={kind === k.id}
                                            onClick={() => setKind(k.id)}
                                        >
                                            {k.label}
                                        </SegBtn>
                                    ))}
                                </div>
                            </div>
                        }
                    >
                        {/* Count strip */}
                        {!loading && forms.length > 0 && (
                            <div className="flex items-center justify-between px-5 pb-3 max-lg:px-3">
                                <span className="eyebrow">
                                    {visible.length}
                                    {query ? ` of ${forms.length}` : ""}{" "}
                                    {visible.length === 1 ? "form" : "forms"}
                                </span>
                                {summary.published > 0 && (
                                    <span className="flex items-center gap-1.5 text-caption text-t-tertiary">
                                        <span className="size-1.5 rounded-full bg-primary-02" />
                                        {summary.published} published
                                    </span>
                                )}
                            </div>
                        )}

                        {error && (
                            <div className="mx-5 mb-3 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03 max-lg:mx-3">
                                <Icon
                                    name="info"
                                    className="size-4 shrink-0 fill-primary-03"
                                />
                                {error}
                            </div>
                        )}

                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Form</th>
                                        <th>Type</th>
                                        <th>Status</th>
                                        <th className="text-right">Responses</th>
                                        <th className="text-right">Updated</th>
                                        <th className="w-8" />
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        [...Array(6)].map((_, i) => (
                                            <tr key={i}>
                                                {[...Array(6)].map((__, j) => (
                                                    <td key={j}>
                                                        <div
                                                            className={`skeleton h-4 ${
                                                                j === 0
                                                                    ? "w-44"
                                                                    : j >= 3
                                                                    ? "w-14 ml-auto"
                                                                    : "w-20"
                                                            }`}
                                                        />
                                                    </td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : visible.length === 0 ? (
                                        <tr>
                                            <td colSpan={6}>
                                                <div className="state-block">
                                                    <span className="state-glyph">
                                                        <Icon
                                                            name={
                                                                query
                                                                    ? "search"
                                                                    : "font"
                                                            }
                                                            className="fill-inherit"
                                                        />
                                                    </span>
                                                    <div className="state-title">
                                                        {query
                                                            ? "No matching forms"
                                                            : kind !== "all" ||
                                                              status !== "all"
                                                            ? "No forms match these filters"
                                                            : "No forms yet"}
                                                    </div>
                                                    <div className="state-sub">
                                                        {query
                                                            ? `Nothing matches “${query}”.`
                                                            : "Create a form or survey to start capturing leads and feedback — each submission builds a CRM contact automatically."}
                                                    </div>
                                                    {writable &&
                                                    !query &&
                                                    kind === "all" &&
                                                    status === "all" ? (
                                                        <Button
                                                            isStroke
                                                            icon="plus"
                                                            className="mt-1"
                                                            onClick={() =>
                                                                setCreateOpen(true)
                                                            }
                                                        >
                                                            New form
                                                        </Button>
                                                    ) : (
                                                        (query ||
                                                            kind !== "all" ||
                                                            status !== "all") && (
                                                            <Button
                                                                isStroke
                                                                className="mt-1"
                                                                onClick={() => {
                                                                    setQuery("");
                                                                    setKind("all");
                                                                    setStatus(
                                                                        "all"
                                                                    );
                                                                }}
                                                            >
                                                                Clear filters
                                                            </Button>
                                                        )
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ) : (
                                        visible.map((f, i) => (
                                            <tr
                                                key={f.id}
                                                className="rise-in is-clickable group"
                                                style={{
                                                    animationDelay: `${Math.min(
                                                        i * 25,
                                                        300
                                                    )}ms`,
                                                }}
                                            >
                                                <td className="font-medium text-t-primary">
                                                    <Link
                                                        href={`/forms/${encodeURIComponent(
                                                            f.id
                                                        )}`}
                                                        className="flex items-center gap-2.5"
                                                    >
                                                        <span className="grid place-items-center size-9 shrink-0 rounded-full bg-b-surface1 text-t-secondary dark:bg-shade-04/60">
                                                            <Icon
                                                                name={kindIcon(
                                                                    f.kind
                                                                )}
                                                                className="size-4.5 fill-t-secondary"
                                                            />
                                                        </span>
                                                        <span className="min-w-0">
                                                            <span className="block truncate max-w-64 text-t-primary">
                                                                {f.title ||
                                                                    "Untitled form"}
                                                            </span>
                                                            <span className="block truncate max-w-64 text-caption text-t-tertiary">
                                                                {f.fields
                                                                    ?.length ||
                                                                    0}{" "}
                                                                field
                                                                {f.fields
                                                                    ?.length === 1
                                                                    ? ""
                                                                    : "s"}
                                                            </span>
                                                        </span>
                                                    </Link>
                                                </td>
                                                <td>
                                                    <KindBadge kind={f.kind} />
                                                </td>
                                                <td>
                                                    <StatusBadge
                                                        status={f.status}
                                                    />
                                                </td>
                                                <td className="text-right td-num text-t-secondary">
                                                    {Number(f.submit_count) || 0}
                                                </td>
                                                <td className="text-right td-num text-t-secondary">
                                                    {fmtRelative(f.updated_at)}
                                                </td>
                                                <td className="text-right">
                                                    <Link
                                                        href={`/forms/${encodeURIComponent(
                                                            f.id
                                                        )}`}
                                                        className="inline-grid place-items-center size-7 rounded-full text-t-tertiary opacity-0 group-hover:opacity-100 transition-opacity hover:bg-b-surface1 dark:hover:bg-shade-04/60"
                                                        aria-label="Open form"
                                                    >
                                                        <Icon
                                                            name="arrow"
                                                            className="size-4 fill-t-secondary"
                                                        />
                                                    </Link>
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </>
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

function SegBtn({
    active,
    onClick,
    children,
}: {
    active: boolean;
    onClick: () => void;
    children: React.ReactNode;
}) {
    return (
        <button
            onClick={onClick}
            className={`px-3.5 h-8 rounded-full text-button transition-all ${
                active
                    ? "bg-b-surface2 text-t-primary shadow-widget"
                    : "text-t-secondary hover:text-t-primary"
            }`}
        >
            {children}
        </button>
    );
}
