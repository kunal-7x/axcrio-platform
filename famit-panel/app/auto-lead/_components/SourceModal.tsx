"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Switch from "@/components/Switch";
import Icon from "@/components/Icon";
import {
    createSource,
    updateSource,
    deleteSource,
    testSource,
    syncSource,
    ingestUrl,
    type Source,
    type SourceType,
} from "../client";
import { SourceIcon } from "../_ui";

const STATUS_OPTS = ["new", "contacted", "engaged", "qualified", "hot"].map((s, i) => ({
    id: i,
    name: s[0].toUpperCase() + s.slice(1),
    value: s,
}));

type FormState = {
    name: string;
    config: Record<string, string>;
    mapping: Record<string, string>;
    validation: Record<string, boolean>;
    routing: { status: string; tags: string; mark_hot: boolean; sync_crm: boolean };
    honeypot: string;
};

function seed(sourceType: SourceType, source: Source | null): FormState {
    return {
        name: source?.name ?? sourceType.label,
        config: { ...(source?.config ?? {}) },
        mapping: {
            name: source?.mapping?.name ?? "",
            phone: source?.mapping?.phone ?? "",
            email: source?.mapping?.email ?? "",
            company: source?.mapping?.company ?? "",
        },
        validation: {
            require_phone: source?.validation?.require_phone ?? true,
            valid_phone_only: source?.validation?.valid_phone_only ?? true,
            require_email: source?.validation?.require_email ?? false,
        },
        routing: {
            status: source?.routing?.status ?? "new",
            tags: (source?.routing?.tags ?? []).join(", "),
            mark_hot: source?.routing?.mark_hot ?? false,
            sync_crm: source?.routing?.sync_crm ?? false,
        },
        honeypot: source?.honeypot ?? "",
    };
}

export default function SourceModal({
    open,
    sourceType,
    source,
    onClose,
}: {
    open: boolean;
    sourceType: SourceType;
    source: Source | null;
    onClose: () => void;
}) {
    const qc = useQueryClient();
    const [current, setCurrent] = useState<Source | null>(source);
    const [form, setForm] = useState<FormState>(() => seed(sourceType, source));
    const [err, setErr] = useState("");
    const [copied, setCopied] = useState(false);
    const [testMsg, setTestMsg] = useState("");

    useEffect(() => {
        if (open) {
            setCurrent(source);
            setForm(seed(sourceType, source));
            setErr("");
            setTestMsg("");
            setCopied(false);
        }
    }, [open, source, sourceType]);

    const isPull = sourceType.mode === "pull";

    const payload = (): Partial<Source> => ({
        type: sourceType.type,
        name: form.name.trim() || sourceType.label,
        config: form.config,
        mapping: form.mapping,
        validation: form.validation,
        routing: {
            status: form.routing.status,
            tags: form.routing.tags.split(",").map((s) => s.trim()).filter(Boolean),
            mark_hot: form.routing.mark_hot,
            sync_crm: form.routing.sync_crm,
        },
        honeypot: form.honeypot.trim(),
    });

    const save = useMutation({
        mutationFn: () => (current ? updateSource(current.id, payload()) : createSource(payload())),
        onSuccess: (r) => {
            setErr("");
            setCurrent(r.source);
            qc.invalidateQueries({ queryKey: ["auto-lead"] });
        },
        onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Save failed"),
    });

    const del = useMutation({
        mutationFn: () => deleteSource(current!.id),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["auto-lead"] });
            onClose();
        },
    });

    const test = useMutation({
        mutationFn: () => testSource(current!.id),
        onSuccess: (r) =>
            setTestMsg(
                r.would_accept
                    ? `✓ Valid — would create lead: ${r.parsed.name || "—"} ${r.parsed.phone || ""}`
                    : `✗ Rejected: ${r.reason}`
            ),
        onError: (e: unknown) => setTestMsg(e instanceof Error ? e.message : "Test failed"),
    });

    const sync = useMutation({
        mutationFn: () => syncSource(current!.id),
        onSuccess: (r) => {
            setTestMsg(`Fetched ${r.fetched}, imported ${r.accepted}.`);
            qc.invalidateQueries({ queryKey: ["auto-lead"] });
        },
        onError: (e: unknown) => setTestMsg(e instanceof Error ? e.message : "Sync failed"),
    });

    const url = current ? ingestUrl(current.token) : "";
    const setV = (k: keyof FormState["validation"]) => (v: boolean) =>
        setForm((f) => ({ ...f, validation: { ...f.validation, [k]: v } }));
    const setMap = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        setForm((f) => ({ ...f, mapping: { ...f.mapping, [k]: e.target.value } }));
    const setCfg = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        setForm((f) => ({ ...f, config: { ...f.config, [k]: e.target.value } }));

    return (
        <Modal open={open} onClose={onClose} isSlidePanel>
            <div className="flex flex-col h-full">
                {/* header */}
                <div className="flex items-center gap-3 p-5 pr-16 border-b border-s-subtle">
                    <SourceIcon icon={sourceType.icon} type={sourceType.type} size={13} />
                    <div className="min-w-0">
                        <div className="text-h6 truncate">{current ? form.name : `Add ${sourceType.label}`}</div>
                        <div className="text-caption text-t-tertiary">
                            {sourceType.mode === "push" ? "Real-time webhook" : "Scheduled polling"} · {sourceType.label}
                        </div>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto p-5 scrollbar scrollbar-thumb-t-tertiary/30 flex flex-col gap-6">
                    <Field label="Source name" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />

                    {/* CONNECT */}
                    <Section title="Connect">
                        <div className="text-body-2 text-t-secondary mb-3">{sourceType.desc}</div>
                        {!isPull ? (
                            current ? (
                                <>
                                    <div className="text-caption text-t-tertiary mb-1.5">Webhook URL — POST your leads here</div>
                                    <div className="flex gap-2">
                                        <input
                                            readOnly
                                            value={url}
                                            onFocus={(e) => e.target.select()}
                                            className="input-base flex-1 !h-11 text-caption font-mono"
                                        />
                                        <Button
                                            isStroke
                                            className="!h-11 shrink-0"
                                            onClick={() => {
                                                navigator.clipboard?.writeText(url);
                                                setCopied(true);
                                                setTimeout(() => setCopied(false), 1500);
                                            }}
                                        >
                                            {copied ? "Copied" : "Copy"}
                                        </Button>
                                    </div>
                                    <Button isStroke className="!h-10 mt-3" onClick={() => test.mutate()} disabled={test.isPending}>
                                        <Icon name="check-circle" className="size-4 mr-1.5 fill-current" />
                                        {test.isPending ? "Testing…" : "Send a test lead"}
                                    </Button>
                                </>
                            ) : (
                                <div className="flex items-center gap-2 p-3 rounded-2xl bg-b-surface1 text-body-2 text-t-tertiary">
                                    <Icon name="info" className="size-4 shrink-0 fill-t-tertiary" />
                                    Save to generate your unique webhook URL.
                                </div>
                            )
                        ) : (
                            <div className="flex flex-col gap-4">
                                {sourceType.fields.map((fl) => (
                                    <Field
                                        key={fl.key}
                                        label={fl.label}
                                        type={fl.type === "password" ? "password" : fl.type === "number" ? "number" : "text"}
                                        placeholder={fl.placeholder}
                                        value={form.config[fl.key] ?? ""}
                                        onChange={setCfg(fl.key)}
                                    />
                                ))}
                                {current && (
                                    <Button isStroke className="!h-10" onClick={() => sync.mutate()} disabled={sync.isPending}>
                                        {sync.isPending ? "Syncing…" : "Sync now"}
                                    </Button>
                                )}
                            </div>
                        )}
                        {testMsg && <div className="mt-3 text-caption text-t-secondary">{testMsg}</div>}
                    </Section>

                    {/* FIELD MAPPING */}
                    <Section title="Field mapping" hint="Leave blank to auto-detect common field names.">
                        <div className="grid grid-cols-2 gap-3 max-md:grid-cols-1">
                            {(["name", "phone", "email", "company"] as const).map((k) => (
                                <Field
                                    key={k}
                                    label={k[0].toUpperCase() + k.slice(1)}
                                    placeholder={`incoming "${k}" key`}
                                    value={form.mapping[k] ?? ""}
                                    onChange={setMap(k)}
                                />
                            ))}
                        </div>
                    </Section>

                    {/* VALIDATION */}
                    <Section title="Validation">
                        <Toggle label="Require a phone number" checked={form.validation.require_phone} onChange={setV("require_phone")} />
                        <Toggle label="Reject invalid phone numbers" checked={form.validation.valid_phone_only} onChange={setV("valid_phone_only")} />
                        <Toggle label="Require an email" checked={form.validation.require_email} onChange={setV("require_email")} />
                        <div className="text-caption text-t-tertiary pt-1">Duplicate phones are always skipped automatically.</div>
                    </Section>

                    {/* ROUTING */}
                    <Section title="Routing" hint="What happens to each accepted lead.">
                        <div className="mb-3">
                            <Select
                                label="Lead status"
                                value={STATUS_OPTS.find((o) => o.value === form.routing.status) ?? STATUS_OPTS[0]}
                                onChange={(o) =>
                                    setForm((f) => ({
                                        ...f,
                                        routing: { ...f.routing, status: (STATUS_OPTS.find((x) => x.id === o.id) ?? STATUS_OPTS[0]).value },
                                    }))
                                }
                                options={STATUS_OPTS}
                            />
                        </div>
                        <Field
                            label="Tags (comma separated)"
                            placeholder="e.g. meta, india"
                            value={form.routing.tags}
                            onChange={(e) => setForm((f) => ({ ...f, routing: { ...f.routing, tags: e.target.value } }))}
                        />
                        <div className="mt-3">
                            <Toggle label="Mark as hot (priority for calling)" checked={form.routing.mark_hot} onChange={(v) => setForm((f) => ({ ...f, routing: { ...f.routing, mark_hot: v } }))} />
                            <Toggle label="Also push to Sales CRM" checked={form.routing.sync_crm} onChange={(v) => setForm((f) => ({ ...f, routing: { ...f.routing, sync_crm: v } }))} />
                        </div>
                    </Section>

                    {/* ADVANCED */}
                    {!isPull && (
                        <Section title="Anti-spam (advanced)">
                            <Field
                                label="Honeypot field name"
                                placeholder="optional — bots that fill this are dropped"
                                value={form.honeypot}
                                onChange={(e) => setForm((f) => ({ ...f, honeypot: e.target.value }))}
                            />
                        </Section>
                    )}

                    {err && (
                        <div className="flex items-center gap-2 p-3 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03">
                            <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                            {err}
                        </div>
                    )}
                </div>

                {/* footer */}
                <div className="flex items-center justify-between gap-3 p-4 border-t border-s-subtle">
                    {current ? (
                        <Button
                            isStroke
                            className="!text-primary-03 !border-primary-03/30 hover:!bg-primary-03/8"
                            disabled={del.isPending}
                            onClick={() => del.mutate()}
                        >
                            {del.isPending ? "Removing…" : "Remove"}
                        </Button>
                    ) : (
                        <span />
                    )}
                    <div className="flex gap-3">
                        <Button isGray onClick={onClose}>
                            {current ? "Done" : "Cancel"}
                        </Button>
                        <Button isBlack disabled={save.isPending} onClick={() => save.mutate()}>
                            {save.isPending ? "Saving…" : current ? "Save changes" : "Create source"}
                        </Button>
                    </div>
                </div>
            </div>
        </Modal>
    );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
    return (
        <div>
            <div className="text-button text-t-secondary mb-0.5">{title}</div>
            {hint && <div className="text-caption text-t-tertiary mb-2.5">{hint}</div>}
            {!hint && <div className="mb-2.5" />}
            {children}
        </div>
    );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
    return (
        <label className="flex items-center justify-between gap-4 py-2 cursor-pointer">
            <span className="text-body-2 text-t-secondary">{label}</span>
            <Switch checked={checked} onChange={onChange} />
        </label>
    );
}
