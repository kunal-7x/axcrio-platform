"use client";

// Form detail / builder — three tabs:
//   • Build       — title/description/contact-map settings + the field-schema editor
//                   + publish controls + the public link & rotate-token.
//   • Submissions — the stored submission rows (answers, score, sentiment).
//   • Insights    — deterministic survey rollups (NPS/CSAT/sentiment/per-question).
//
// Reads degrade to a premium dormant state (router not mounted yet). Writes go
// through the envelope-aware client (JSON body, {status,error} handling). Edits
// only this route's own files under app/forms/[id].

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Tabs from "@/components/Tabs";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import { useMe, canWrite } from "@/lib/auth";
import {
    getForm,
    getSubmissions,
    getInsights,
    updateForm,
    rotateToken,
    FormsDormantError,
    FormsActionError,
    type Form,
    type FormField,
    type FormStatus,
    type Submission,
    type Insights,
    type ContactMap,
} from "../client";
import {
    StatusBadge,
    KindBadge,
    kindIcon,
    fmtDateTime,
    fmtRelative,
    fmtAnswer,
    SentimentBadge,
} from "../_ui";
import FieldEditor from "./FieldEditor";
import InsightsPanel from "./InsightsPanel";

type TabKey = "build" | "submissions" | "insights";

const TABS = [
    { id: 1, name: "Build", key: "build" as TabKey },
    { id: 2, name: "Submissions", key: "submissions" as TabKey },
    { id: 3, name: "Insights", key: "insights" as TabKey },
];

export default function FormDetailPage() {
    const params = useParams();
    const id = decodeURIComponent(
        Array.isArray(params.id) ? params.id[0] : (params.id as string) || ""
    );
    const { me } = useMe();
    const writable = canWrite(me);

    const [form, setForm] = useState<Form | null>(null);
    const [loading, setLoading] = useState(true);
    const [dormant, setDormant] = useState(false);
    const [notFound, setNotFound] = useState(false);
    const [error, setError] = useState("");

    const [tabOpt, setTabOpt] = useState(TABS[0]);
    const tab = tabOpt.key;

    // editable draft of the schema/meta (the Build tab works on this copy)
    const [draftFields, setDraftFields] = useState<FormField[]>([]);
    const [draftTitle, setDraftTitle] = useState("");
    const [draftDesc, setDraftDesc] = useState("");
    const [draftMap, setDraftMap] = useState<ContactMap>({});
    const [saving, setSaving] = useState(false);
    const [saveMsg, setSaveMsg] = useState("");
    const [copyMsg, setCopyMsg] = useState("");
    const savedSnapshot = useRef<string>("");

    const load = useCallback(() => {
        if (!id) return;
        setLoading(true);
        setError("");
        getForm(id)
            .then((f) => {
                setForm(f);
                setDraftFields(f.fields || []);
                setDraftTitle(f.title || "");
                setDraftDesc(f.description || "");
                setDraftMap(f.contact_map || {});
                savedSnapshot.current = JSON.stringify({
                    fields: f.fields || [],
                    title: f.title || "",
                    description: f.description || "",
                    contact_map: f.contact_map || {},
                });
                setDormant(false);
                setNotFound(false);
            })
            .catch((e: unknown) => {
                if (e instanceof FormsDormantError) {
                    setDormant(true);
                } else if (
                    e instanceof FormsActionError &&
                    e.code === "not_found"
                ) {
                    setNotFound(true);
                } else if (
                    e instanceof Error &&
                    e.message.toLowerCase().includes("not_found")
                ) {
                    setNotFound(true);
                } else {
                    setError(
                        e instanceof Error ? e.message : "Failed to load form"
                    );
                }
            })
            .finally(() => setLoading(false));
    }, [id]);

    useEffect(() => {
        load();
    }, [load]);

    const dirty = useMemo(() => {
        if (!form) return false;
        return (
            JSON.stringify({
                fields: draftFields,
                title: draftTitle,
                description: draftDesc,
                contact_map: draftMap,
            }) !== savedSnapshot.current
        );
    }, [form, draftFields, draftTitle, draftDesc, draftMap]);

    async function persist(extra?: { status?: FormStatus }) {
        if (!form) return;
        setSaving(true);
        setSaveMsg("");
        setError("");
        try {
            const updated = await updateForm(form.id, {
                title: draftTitle,
                description: draftDesc,
                fields: draftFields,
                contact_map: draftMap,
                ...(extra?.status ? { status: extra.status } : {}),
            });
            setForm(updated);
            setDraftFields(updated.fields || []);
            savedSnapshot.current = JSON.stringify({
                fields: updated.fields || [],
                title: updated.title || "",
                description: updated.description || "",
                contact_map: updated.contact_map || {},
            });
            setSaveMsg(
                extra?.status === "published"
                    ? "Published"
                    : extra?.status === "draft"
                    ? "Unpublished"
                    : extra?.status === "closed"
                    ? "Closed"
                    : "Saved"
            );
            setTimeout(() => setSaveMsg(""), 2500);
        } catch (e: unknown) {
            setError(
                e instanceof FormsActionError || e instanceof Error
                    ? e.message
                    : "Could not save changes."
            );
        } finally {
            setSaving(false);
        }
    }

    async function handleRotate() {
        if (!form) return;
        setError("");
        try {
            const tok = await rotateToken(form.id);
            setForm({ ...form, public_token: tok });
            setSaveMsg("New link issued");
            setTimeout(() => setSaveMsg(""), 2500);
        } catch (e: unknown) {
            setError(
                e instanceof Error ? e.message : "Could not rotate the link."
            );
        }
    }

    const publicUrl = useMemo(() => {
        if (!form?.public_token) return "";
        const origin =
            typeof window !== "undefined" ? window.location.origin : "";
        return `${origin}/api/f/${form.public_token}`;
    }, [form?.public_token]);

    async function copyLink() {
        if (!publicUrl) return;
        try {
            await navigator.clipboard.writeText(publicUrl);
            setCopyMsg("Copied");
            setTimeout(() => setCopyMsg(""), 1800);
        } catch {
            setCopyMsg("Copy failed");
            setTimeout(() => setCopyMsg(""), 1800);
        }
    }

    // ── Dormant / not-found / loading shells ───────────────────────────────
    if (dormant) {
        return (
            <Layout title="Form">
                <BackLink />
                <Card title="Form">
                    <div className="py-16 text-center max-md:py-12">
                        <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                            <Icon name="font" className="fill-t-tertiary" />
                        </span>
                        <div className="text-h6 mb-1">
                            Forms &amp; Surveys is being prepared
                        </div>
                        <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                            This builder lights up the moment the module is enabled
                            for your workspace.
                        </div>
                        <span className="inline-block mt-5 px-3 h-8 leading-8 rounded-full bg-b-surface1 text-button text-t-secondary">
                            Coming soon
                        </span>
                    </div>
                </Card>
            </Layout>
        );
    }

    if (notFound) {
        return (
            <Layout title="Form">
                <BackLink />
                <Card title="Form">
                    <div className="py-16 text-center max-md:py-12">
                        <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                            <Icon name="info" className="fill-t-tertiary" />
                        </span>
                        <div className="text-h6 mb-1">Form not found</div>
                        <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                            This form may have been deleted, or the link is no
                            longer valid.
                        </div>
                        <Button as="link" href="/forms" isStroke className="mt-5">
                            Back to all forms
                        </Button>
                    </div>
                </Card>
            </Layout>
        );
    }

    const published = form?.status === "published";

    return (
        <Layout title={form?.title || "Form"}>
            <BackLink />

            {/* Form masthead */}
            <div className="card mb-3 rise-in">
                <div className="flex items-start gap-4 p-5 max-lg:p-3 max-md:flex-col">
                    <span className="grid place-items-center size-12 shrink-0 rounded-2xl bg-b-surface1 fill-t-secondary dark:bg-shade-04/60">
                        <Icon
                            name={kindIcon(form?.kind)}
                            className="size-6 fill-inherit"
                        />
                    </span>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2.5 flex-wrap mb-1.5">
                            <h1 className="text-h5 text-t-primary truncate max-w-full">
                                {loading
                                    ? "Loading…"
                                    : form?.title || "Untitled form"}
                            </h1>
                            {form && <KindBadge kind={form.kind} />}
                            {form && <StatusBadge status={form.status} />}
                        </div>
                        <p className="text-body-2 text-t-secondary">
                            {form?.description ||
                                "No description — add one in the Build tab."}
                        </p>
                        {form && (
                            <div className="flex items-center gap-4 mt-2 text-caption text-t-tertiary flex-wrap">
                                <span>{form.fields?.length || 0} fields</span>
                                <span>·</span>
                                <span>
                                    {Number(form.submit_count) || 0} responses
                                </span>
                                <span>·</span>
                                <span>Updated {fmtRelative(form.updated_at)}</span>
                            </div>
                        )}
                    </div>

                    {/* Publish controls */}
                    {writable && form && (
                        <div className="flex items-center gap-2.5 shrink-0 max-md:w-full">
                            {saveMsg && (
                                <span className="flex items-center gap-1.5 text-caption text-primary-02">
                                    <Icon
                                        name="check-circle"
                                        className="size-4 fill-primary-02"
                                    />
                                    {saveMsg}
                                </span>
                            )}
                            {published ? (
                                <Button
                                    isStroke
                                    onClick={() => persist({ status: "draft" })}
                                    disabled={saving}
                                >
                                    Unpublish
                                </Button>
                            ) : (
                                <Button
                                    isBlack
                                    icon="check"
                                    onClick={() =>
                                        persist({ status: "published" })
                                    }
                                    disabled={saving || (form.fields?.length || 0) === 0}
                                >
                                    Publish
                                </Button>
                            )}
                        </div>
                    )}
                </div>

                {/* Public link strip (published forms) */}
                {form && published && publicUrl && (
                    <div className="flex items-center gap-2.5 px-5 pb-5 max-lg:px-3 max-md:flex-col max-md:items-stretch">
                        <div className="flex items-center gap-2 flex-1 min-w-0 h-11 px-4 rounded-2xl bg-b-surface1 border border-s-subtle dark:bg-shade-04/40">
                            <Icon
                                name="link"
                                className="size-4 shrink-0 fill-t-tertiary"
                            />
                            <span className="truncate text-body-2 text-t-secondary td-num">
                                {publicUrl}
                            </span>
                        </div>
                        <Button isStroke icon="link" onClick={copyLink}>
                            {copyMsg || "Copy link"}
                        </Button>
                        {writable && (
                            <Button
                                isGray
                                onClick={handleRotate}
                                title="Issue a fresh link and invalidate the old one"
                            >
                                Rotate
                            </Button>
                        )}
                    </div>
                )}
            </div>

            {error && (
                <div className="mb-3 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03">
                    <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                    {error}
                </div>
            )}

            {/* Tabs */}
            <Card
                title={
                    tab === "build"
                        ? "Build"
                        : tab === "submissions"
                        ? "Submissions"
                        : "Insights"
                }
                headContent={
                    <Tabs
                        items={TABS}
                        value={tabOpt}
                        setValue={(v) => setTabOpt(v as (typeof TABS)[number])}
                    />
                }
            >
                {loading ? (
                    <div className="px-5 pb-5 flex flex-col gap-3 max-lg:px-3">
                        {[...Array(3)].map((_, i) => (
                            <div key={i} className="skeleton h-16 rounded-3xl" />
                        ))}
                    </div>
                ) : tab === "build" ? (
                    <BuildTab
                        writable={writable}
                        draftTitle={draftTitle}
                        setDraftTitle={setDraftTitle}
                        draftDesc={draftDesc}
                        setDraftDesc={setDraftDesc}
                        draftFields={draftFields}
                        setDraftFields={setDraftFields}
                        draftMap={draftMap}
                        setDraftMap={setDraftMap}
                        dirty={dirty}
                        saving={saving}
                        onSave={() => persist()}
                    />
                ) : tab === "submissions" ? (
                    <SubmissionsTab formId={id} />
                ) : (
                    <InsightsTab formId={id} kind={form?.kind || "form"} />
                )}
            </Card>
        </Layout>
    );
}

/* ───────────────────────────── Build tab ──────────────────────────────── */

function BuildTab({
    writable,
    draftTitle,
    setDraftTitle,
    draftDesc,
    setDraftDesc,
    draftFields,
    setDraftFields,
    draftMap,
    setDraftMap,
    dirty,
    saving,
    onSave,
}: {
    writable: boolean;
    draftTitle: string;
    setDraftTitle: (v: string) => void;
    draftDesc: string;
    setDraftDesc: (v: string) => void;
    draftFields: FormField[];
    setDraftFields: (f: FormField[]) => void;
    draftMap: ContactMap;
    setDraftMap: (m: ContactMap) => void;
    dirty: boolean;
    saving: boolean;
    onSave: () => void;
}) {
    // candidate keys for the contact-map (text-ish fields the CRM can map)
    const mappableFor = (kinds: string[]) =>
        draftFields.filter((f) => kinds.includes(f.type));

    return (
        <div>
            {/* Meta */}
            <div className="px-5 pb-4 grid grid-cols-2 gap-4 max-lg:px-3 max-md:grid-cols-1">
                <label className="block">
                    <span className="block mb-2 text-button text-t-primary">
                        Title
                    </span>
                    <input
                        value={draftTitle}
                        disabled={!writable}
                        onChange={(e) => setDraftTitle(e.target.value)}
                        placeholder="Form title"
                        className="input-base w-full h-12 px-4.5 rounded-full text-body-2"
                    />
                </label>
                <label className="block">
                    <span className="block mb-2 text-button text-t-primary">
                        Description
                    </span>
                    <input
                        value={draftDesc}
                        disabled={!writable}
                        onChange={(e) => setDraftDesc(e.target.value)}
                        placeholder="Optional — shown to people filling it out"
                        className="input-base w-full h-12 px-4.5 rounded-full text-body-2"
                    />
                </label>
            </div>

            {/* Schema editor */}
            <div className="px-5 max-lg:px-3">
                <div className="text-button text-t-primary mb-1">Fields</div>
                <p className="text-caption text-t-tertiary mb-3">
                    Add the questions people will answer. Keys must be unique and
                    use lowercase letters, numbers or underscores.
                </p>
            </div>
            <FieldEditor
                fields={draftFields}
                onChange={setDraftFields}
                disabled={!writable}
            />

            {/* Contact mapping — which field feeds the CRM person spine */}
            {draftFields.length > 0 && (
                <div className="px-5 pb-2 max-lg:px-3">
                    <div className="p-4 rounded-3xl border border-s-subtle bg-b-surface1 dark:bg-shade-04/30">
                        <div className="flex items-center gap-2 mb-1">
                            <Icon
                                name="profile"
                                className="size-4 fill-t-secondary"
                            />
                            <span className="text-button text-t-primary">
                                CRM contact mapping
                            </span>
                        </div>
                        <p className="text-caption text-t-tertiary mb-3">
                            Choose which fields feed the contact created on each
                            submission. Optional — defaults to fields named
                            phone / name / email.
                        </p>
                        <div className="grid grid-cols-3 gap-3 max-md:grid-cols-1">
                            <MapSelect
                                label="Phone"
                                value={draftMap.phone || ""}
                                options={mappableFor(["phone", "text", "number"])}
                                disabled={!writable}
                                onChange={(v) =>
                                    setDraftMap({ ...draftMap, phone: v })
                                }
                            />
                            <MapSelect
                                label="Name"
                                value={draftMap.name || ""}
                                options={mappableFor(["text"])}
                                disabled={!writable}
                                onChange={(v) =>
                                    setDraftMap({ ...draftMap, name: v })
                                }
                            />
                            <MapSelect
                                label="Email"
                                value={draftMap.email || ""}
                                options={mappableFor(["email", "text"])}
                                disabled={!writable}
                                onChange={(v) =>
                                    setDraftMap({ ...draftMap, email: v })
                                }
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* Save bar */}
            {writable && (
                <div className="sticky bottom-0 flex items-center justify-between gap-3 px-5 py-3.5 mt-2 bg-b-surface2/95 backdrop-blur border-t border-s-subtle max-lg:px-3">
                    <span className="text-caption text-t-tertiary">
                        {dirty ? "Unsaved changes" : "All changes saved"}
                    </span>
                    <Button
                        isBlack
                        icon="check"
                        onClick={onSave}
                        disabled={saving || !dirty}
                    >
                        {saving ? "Saving…" : "Save changes"}
                    </Button>
                </div>
            )}
        </div>
    );
}

function MapSelect({
    label,
    value,
    options,
    disabled,
    onChange,
}: {
    label: string;
    value: string;
    options: FormField[];
    disabled?: boolean;
    onChange: (v: string) => void;
}) {
    return (
        <label className="block">
            <span className="block mb-1.5 text-caption text-t-tertiary">
                {label}
            </span>
            <select
                value={value}
                disabled={disabled}
                onChange={(e) => onChange(e.target.value)}
                className="input-base w-full h-11 px-3.5 rounded-2xl text-body-2"
            >
                <option value="">Auto ({label.toLowerCase()})</option>
                {options.map((f) => (
                    <option key={f.key} value={f.key}>
                        {f.label} ({f.key})
                    </option>
                ))}
            </select>
        </label>
    );
}

/* ─────────────────────────── Submissions tab ──────────────────────────── */

function SubmissionsTab({ formId }: { formId: string }) {
    const [subs, setSubs] = useState<Submission[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        setLoading(true);
        getSubmissions(formId)
            .then((r) => {
                setSubs(r.submissions || []);
                setTotal(r.total ?? (r.submissions || []).length);
            })
            .catch((e: unknown) => {
                if (!(e instanceof FormsDormantError)) {
                    setError(
                        e instanceof Error
                            ? e.message
                            : "Failed to load submissions"
                    );
                }
            })
            .finally(() => setLoading(false));
    }, [formId]);

    // union of answer keys across the loaded set (stable column order)
    const keys = useMemo(() => {
        const seen: string[] = [];
        for (const s of subs) {
            for (const k of Object.keys(s.answers || {})) {
                if (!seen.includes(k)) seen.push(k);
            }
        }
        return seen.slice(0, 6); // keep the table readable
    }, [subs]);

    if (loading) {
        return (
            <div className="px-5 pb-5 flex flex-col gap-2 max-lg:px-3">
                {[...Array(5)].map((_, i) => (
                    <div key={i} className="skeleton h-10 rounded-2xl" />
                ))}
            </div>
        );
    }

    if (error) {
        return (
            <div className="mx-5 mb-5 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03 max-lg:mx-3">
                <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                {error}
            </div>
        );
    }

    if (subs.length === 0) {
        return (
            <div className="py-16 text-center max-md:py-12">
                <span className="inline-grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                    <Icon name="list" className="fill-t-tertiary" />
                </span>
                <div className="text-h6 mb-1">No submissions yet</div>
                <div className="max-w-md mx-auto text-body-2 text-t-secondary">
                    Share the public link from the form header — each submission
                    appears here and creates a CRM contact automatically.
                </div>
            </div>
        );
    }

    return (
        <div className="p-1 max-lg:px-0">
            <div className="px-4 pb-1 text-body-2 text-t-tertiary">
                {total} submission{total === 1 ? "" : "s"}
            </div>
            <Table
                cellsThead={
                    <>
                        <th>When</th>
                        {keys.map((k) => (
                            <th key={k} className="max-lg:hidden">
                                {k}
                            </th>
                        ))}
                        <th className="text-right">Score</th>
                        <th>Sentiment</th>
                    </>
                }
            >
                {subs.map((s) => (
                    <TableRow key={s.id}>
                        <td className="text-t-secondary whitespace-nowrap">
                            {fmtDateTime(s.created_at)}
                        </td>
                        {keys.map((k) => (
                            <td
                                key={k}
                                className="text-t-secondary max-w-48 truncate max-lg:hidden"
                            >
                                {fmtAnswer(s.answers?.[k])}
                            </td>
                        ))}
                        <td className="text-right text-t-secondary">
                            {s.score == null ? "—" : s.score}
                        </td>
                        <td>
                            {s.sentiment ? (
                                <SentimentBadge sentiment={s.sentiment} />
                            ) : (
                                <span className="text-t-tertiary">—</span>
                            )}
                        </td>
                    </TableRow>
                ))}
            </Table>
        </div>
    );
}

/* ──────────────────────────── Insights tab ────────────────────────────── */

function InsightsTab({ formId, kind }: { formId: string; kind: string }) {
    const [insights, setInsights] = useState<Insights | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        setLoading(true);
        getInsights(formId)
            .then((r) => setInsights(r))
            .catch((e: unknown) => {
                if (!(e instanceof FormsDormantError)) {
                    setError(
                        e instanceof Error
                            ? e.message
                            : "Failed to load insights"
                    );
                }
            })
            .finally(() => setLoading(false));
    }, [formId]);

    if (loading) {
        return (
            <div className="px-5 pb-5 grid grid-cols-4 gap-3 max-lg:grid-cols-2 max-lg:px-3">
                {[...Array(4)].map((_, i) => (
                    <div key={i} className="skeleton h-24 rounded-3xl" />
                ))}
            </div>
        );
    }

    if (error || !insights) {
        return (
            <div className="mx-5 mb-5 flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03 max-lg:mx-3">
                <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                {error || "Insights are unavailable."}
            </div>
        );
    }

    return <InsightsPanel insights={insights} kind={kind} />;
}

/* ──────────────────────────────── chrome ──────────────────────────────── */

function BackLink() {
    return (
        <Link
            href="/forms"
            className="inline-flex items-center gap-1.5 mb-3 text-button text-t-secondary fill-t-secondary transition-colors hover:text-t-primary hover:fill-t-primary"
        >
            <Icon name="arrow" className="size-4 fill-inherit rotate-180" />
            All forms
        </Link>
    );
}

