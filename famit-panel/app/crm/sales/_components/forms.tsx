"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Checkbox from "@/components/Checkbox";
import Icon from "@/components/Icon";
import { getLeads, type Lead } from "@/lib/api";
import {
    createCompany,
    createPerson,
    createOpportunity,
    syncLeads,
    type Stage,
    type SyncResult,
} from "../client";

export type CreateKind = "company" | "person" | "opportunity";

const TITLES: Record<CreateKind, string> = {
    company: "New company",
    person: "New person",
    opportunity: "New opportunity",
};

// ── Create modal (company / person / opportunity) ────────────────────────────
export function CreateRecordModal({
    open,
    kind,
    stages,
    onClose,
}: {
    open: boolean;
    kind: CreateKind;
    stages: Stage[];
    onClose: () => void;
}) {
    const qc = useQueryClient();
    const [form, setForm] = useState<Record<string, string>>({});
    const [err, setErr] = useState("");

    const stageOpts = useMemo(
        () => stages.map((s, i) => ({ id: i, name: s.label, value: s.value })),
        [stages]
    );
    type StageOpt = { id: number; name: string; value: string };
    const [stageOpt, setStageOpt] = useState<StageOpt | null>(stageOpts[0] ?? null);
    useEffect(() => {
        // reset when (re)opened
        if (open) {
            setForm({ currencyCode: "INR" });
            setStageOpt(stageOpts[0] ?? null);
            setErr("");
        }
    }, [open, kind, stageOpts]);

    const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        setForm((f) => ({ ...f, [k]: e.target.value }));

    const mut = useMutation({
        mutationFn: async () => {
            if (kind === "company") return createCompany({ name: form.name, domain: form.domain, city: form.city });
            if (kind === "person")
                return createPerson({
                    firstName: form.firstName,
                    lastName: form.lastName,
                    email: form.email,
                    phone: form.phone,
                    jobTitle: form.jobTitle,
                });
            return createOpportunity({
                name: form.name,
                stage: stageOpt?.value,
                amount: form.amount ? Number(form.amount) : undefined,
                currencyCode: form.currencyCode || "INR",
            });
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["twenty"] });
            onClose();
        },
        onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Could not create"),
    });

    const nameOk =
        kind === "person" ? !!(form.firstName || form.lastName) : !!form.name?.trim();

    return (
        <Modal open={open} onClose={onClose}>
            <div className="text-h5 mb-6">{TITLES[kind]}</div>
            <div className="flex flex-col gap-4">
                {kind === "company" && (
                    <>
                        <Field label="Company name" placeholder="Acme Inc." value={form.name || ""} onChange={set("name")} />
                        <Field label="Domain" placeholder="acme.com" value={form.domain || ""} onChange={set("domain")} />
                        <Field label="City" placeholder="Mumbai" value={form.city || ""} onChange={set("city")} />
                    </>
                )}
                {kind === "person" && (
                    <>
                        <div className="flex gap-4 max-md:flex-col">
                            <Field className="flex-1" label="First name" placeholder="Ada" value={form.firstName || ""} onChange={set("firstName")} />
                            <Field className="flex-1" label="Last name" placeholder="Lovelace" value={form.lastName || ""} onChange={set("lastName")} />
                        </div>
                        <Field label="Email" type="email" placeholder="ada@acme.com" value={form.email || ""} onChange={set("email")} />
                        <Field label="Phone" placeholder="+91 98765 43210" value={form.phone || ""} onChange={set("phone")} />
                        <Field label="Job title" placeholder="CTO" value={form.jobTitle || ""} onChange={set("jobTitle")} />
                    </>
                )}
                {kind === "opportunity" && (
                    <>
                        <Field label="Deal name" placeholder="Acme — annual plan" value={form.name || ""} onChange={set("name")} />
                        {stageOpts.length > 0 && (
                            <Select
                                label="Stage"
                                value={stageOpt}
                                onChange={(o) => setStageOpt(stageOpts.find((x) => x.id === o.id) ?? null)}
                                options={stageOpts}
                            />
                        )}
                        <div className="flex gap-4 max-md:flex-col">
                            <Field className="flex-1" label="Amount" type="number" placeholder="50000" value={form.amount || ""} onChange={set("amount")} />
                            <Field className="w-32 max-md:w-full" label="Currency" placeholder="INR" value={form.currencyCode || ""} onChange={set("currencyCode")} />
                        </div>
                    </>
                )}
                {err && (
                    <div className="flex items-center gap-2 p-3 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03">
                        <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                        {err}
                    </div>
                )}
                <div className="flex justify-end gap-3 mt-2">
                    <Button isStroke onClick={onClose}>
                        Cancel
                    </Button>
                    <Button isBlack disabled={!nameOk || mut.isPending} onClick={() => mut.mutate()}>
                        {mut.isPending ? "Creating…" : "Create"}
                    </Button>
                </div>
            </div>
        </Modal>
    );
}

// ── Import voice leads -> Twenty (People + Opportunities) ─────────────────────
export function ImportLeadsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
    const qc = useQueryClient();
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [createOpp, setCreateOpp] = useState(true);
    const [result, setResult] = useState<SyncResult | null>(null);
    const [err, setErr] = useState("");

    const leadsQ = useQuery({
        queryKey: ["twenty", "import", "leads"],
        queryFn: () => getLeads({ limit: 100, sort: "added_at" }),
        enabled: open,
    });
    const leads: Lead[] = leadsQ.data?.leads ?? [];

    useEffect(() => {
        if (open) {
            setSelected(new Set());
            setResult(null);
            setErr("");
        }
    }, [open]);

    const allSelected = leads.length > 0 && selected.size === leads.length;
    const toggleAll = () =>
        setSelected(allSelected ? new Set() : new Set(leads.map((l) => l.id)));
    const toggle = (id: string) =>
        setSelected((s) => {
            const n = new Set(s);
            if (n.has(id)) n.delete(id);
            else n.add(id);
            return n;
        });

    const mut = useMutation({
        mutationFn: () => {
            const chosen = leads.filter((l) => selected.has(l.id));
            return syncLeads(
                chosen.map((l) => ({ name: l.name, phone: l.phone, status: l.status })),
                createOpp
            );
        },
        onSuccess: (r) => {
            setResult(r);
            qc.invalidateQueries({ queryKey: ["twenty"] });
        },
        onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Import failed"),
    });

    return (
        <Modal open={open} onClose={onClose}>
            <div className="text-h5 mb-1">Import leads to CRM</div>
            <div className="text-body-2 text-t-secondary mb-5">
                Push your called leads into Twenty as People{createOpp ? " + pipeline deals" : ""}. Up to 50
                per import.
            </div>

            {result ? (
                <div>
                    <div className="flex items-center gap-2 p-3.5 rounded-2xl bg-primary-02/8 border border-primary-02/20 text-body-2 text-t-primary">
                        <Icon name="check-circle" className="size-4 shrink-0 fill-primary-02" />
                        Imported {result.imported} of {result.total}.
                    </div>
                    {result.results.some((r) => !r.ok) && (
                        <div className="mt-3 max-h-40 overflow-auto text-caption text-t-tertiary">
                            {result.results
                                .filter((r) => !r.ok)
                                .map((r, i) => (
                                    <div key={i}>• {r.name}: {r.error}</div>
                                ))}
                        </div>
                    )}
                    <div className="flex justify-end mt-6">
                        <Button isBlack onClick={onClose}>
                            Done
                        </Button>
                    </div>
                </div>
            ) : (
                <>
                    <div className="flex items-center justify-between px-1 mb-2">
                        <Checkbox
                            checked={allSelected}
                            onChange={toggleAll}
                            label={`Select all (${leads.length})`}
                        />
                        <Checkbox checked={createOpp} onChange={setCreateOpp} label="Create deals" />
                    </div>
                    <div className="max-h-72 overflow-auto rounded-2xl bg-b-surface1 divide-y divide-s-subtle">
                        {leadsQ.isLoading ? (
                            <div className="p-6 text-center text-body-2 text-t-tertiary">Loading leads…</div>
                        ) : leads.length === 0 ? (
                            <div className="p-6 text-center text-body-2 text-t-tertiary">
                                No leads to import yet.
                            </div>
                        ) : (
                            leads.map((l) => (
                                <button
                                    type="button"
                                    key={l.id}
                                    onClick={() => toggle(l.id)}
                                    className="flex items-center gap-3 w-full px-4 py-2.5 text-left transition-colors hover:bg-b-surface2"
                                >
                                    <Checkbox checked={selected.has(l.id)} onChange={() => toggle(l.id)} />
                                    <span className="min-w-0 flex-1">
                                        <span className="block truncate text-sub-title-1 text-t-primary">
                                            {l.name || "Unknown"}
                                        </span>
                                        <span className="block truncate text-caption text-t-tertiary">
                                            {l.phone} · {l.status || "new"}
                                        </span>
                                    </span>
                                </button>
                            ))
                        )}
                    </div>
                    {err && (
                        <div className="mt-3 flex items-center gap-2 p-3 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03">
                            <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                            {err}
                        </div>
                    )}
                    <div className="flex justify-end gap-3 mt-6">
                        <Button isStroke onClick={onClose}>
                            Cancel
                        </Button>
                        <Button
                            isBlack
                            disabled={selected.size === 0 || mut.isPending}
                            onClick={() => mut.mutate()}
                        >
                            {mut.isPending ? "Importing…" : `Import ${selected.size || ""}`}
                        </Button>
                    </div>
                </>
            )}
        </Modal>
    );
}
