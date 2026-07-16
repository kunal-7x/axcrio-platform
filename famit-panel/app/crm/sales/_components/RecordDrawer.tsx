"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Icon from "@/components/Icon";
import {
    getCompany,
    getPerson,
    getOpportunity,
    updateOpportunity,
    deleteCompany,
    deletePerson,
    deleteOpportunity,
    addNote,
    type ActivityTarget,
    type Company,
    type Person,
    type Opportunity,
    type Stage,
    type RecordDetail,
} from "../client";
import { Avatar, StageChip, fmtMoney, fmtDate, fmtRelative, stageIndex, stageMeta } from "../_ui";

type Target = { type: ActivityTarget; id: string };

export default function RecordDrawer({
    target,
    stages,
    canWrite,
    onClose,
    onOpen,
}: {
    target: Target | null;
    stages: Stage[];
    canWrite: boolean;
    onClose: () => void;
    onOpen: (type: ActivityTarget, id: string) => void;
}) {
    const open = !!target;
    return (
        <Modal open={open} onClose={onClose} isSlidePanel>
            {target && (
                <DrawerBody
                    target={target}
                    stages={stages}
                    canWrite={canWrite}
                    onClose={onClose}
                    onOpen={onOpen}
                />
            )}
        </Modal>
    );
}

function DrawerBody({
    target,
    stages,
    canWrite,
    onClose,
    onOpen,
}: {
    target: Target;
    stages: Stage[];
    canWrite: boolean;
    onClose: () => void;
    onOpen: (type: ActivityTarget, id: string) => void;
}) {
    const qc = useQueryClient();
    const idx = useMemo(() => stageIndex(stages), [stages]);
    const q = useQuery<RecordDetail<Company | Person | Opportunity>>({
        queryKey: ["twenty", "record", target.type, target.id],
        queryFn: () =>
            target.type === "company"
                ? getCompany(target.id)
                : target.type === "person"
                ? getPerson(target.id)
                : getOpportunity(target.id),
    });

    const invalidate = () => {
        qc.invalidateQueries({ queryKey: ["twenty", "record", target.type, target.id] });
        qc.invalidateQueries({ queryKey: ["twenty", "pipeline"] });
        qc.invalidateQueries({ queryKey: ["twenty", target.type === "company" ? "companies" : "people"] });
    };

    const del = useMutation({
        mutationFn: () =>
            target.type === "company"
                ? deleteCompany(target.id)
                : target.type === "person"
                ? deletePerson(target.id)
                : deleteOpportunity(target.id),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["twenty"] });
            onClose();
        },
    });

    const moveStage = useMutation({
        mutationFn: (stage: string) => updateOpportunity(target.id, { stage }),
        onSuccess: invalidate,
    });

    const rec = q.data?.record as Company | Person | Opportunity | null | undefined;

    const header: { title: string; sub: string; icon: string; url: string } = (() => {
        if (!rec) return { title: "…", sub: "", icon: "profile", url: "" };
        if (target.type === "company") {
            const c = rec as Company;
            return { title: c.name, sub: c.domain || "—", icon: "bag", url: "" };
        }
        if (target.type === "person") {
            const p = rec as Person;
            return { title: p.name, sub: p.jobTitle || p.email || "—", icon: "profile", url: p.avatarUrl };
        }
        const o = rec as Opportunity;
        return { title: o.name, sub: o.companyName || "—", icon: "chart", url: "" };
    })();

    return (
        <div className="flex flex-col h-full">
            {/* header */}
            <div className="flex items-start gap-3 p-5 pr-16 border-b border-s-subtle">
                {target.type === "person" ? (
                    <Avatar name={header.title} url={header.url} size={13} />
                ) : (
                    <span className="grid place-items-center size-13 shrink-0 rounded-2xl bg-b-surface1">
                        <Icon name={header.icon || "profile"} className="fill-t-secondary" />
                    </span>
                )}
                <div className="min-w-0 flex-1">
                    <div className="text-h6 truncate">{q.isLoading ? "Loading…" : header.title}</div>
                    <div className="text-body-2 text-t-tertiary truncate">{header.sub}</div>
                </div>
            </div>

            {/* scroll body */}
            <div className="flex-1 overflow-y-auto p-5 scrollbar scrollbar-thumb-t-tertiary/30">
                {q.isLoading ? (
                    <div className="flex flex-col gap-3">
                        {[...Array(5)].map((_, i) => (
                            <div key={i} className="skeleton h-10 rounded-xl" />
                        ))}
                    </div>
                ) : q.error || !rec ? (
                    <div className="flex items-center gap-2 p-3.5 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03">
                        <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                        {q.error instanceof Error ? q.error.message : "Could not load this record."}
                    </div>
                ) : (
                    <div className="flex flex-col gap-6">
                        {/* type-specific fields */}
                        {target.type === "opportunity" && (
                            <OpportunityFields
                                opp={rec as Opportunity}
                                stages={stages}
                                idx={idx}
                                canWrite={canWrite}
                                onMove={(s) => moveStage.mutate(s)}
                            />
                        )}
                        {target.type === "person" && <PersonFields person={rec as Person} />}
                        {target.type === "company" && <CompanyFields company={rec as Company} />}

                        {/* related */}
                        <Related
                            people={q.data?.people}
                            opportunities={q.data?.opportunities}
                            idx={idx}
                            onOpen={onOpen}
                        />

                        {/* activity */}
                        <Activity
                            target={target}
                            notes={q.data?.notes}
                            tasks={q.data?.tasks}
                            canWrite={canWrite}
                            onAdded={invalidate}
                        />
                    </div>
                )}
            </div>

            {/* footer actions */}
            {canWrite && rec && (
                <div className="flex justify-between gap-3 p-4 border-t border-s-subtle">
                    <Button
                        isStroke
                        className="!text-primary-03 !border-primary-03/30 hover:!bg-primary-03/8"
                        disabled={del.isPending}
                        onClick={() => del.mutate()}
                    >
                        {del.isPending ? "Deleting…" : "Delete"}
                    </Button>
                    <Button isGray onClick={onClose}>
                        Close
                    </Button>
                </div>
            )}
        </div>
    );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div className="flex items-center justify-between gap-4 py-2 border-b border-s-subtle last:border-0">
            <span className="text-caption text-t-tertiary uppercase tracking-[0.06em]">{label}</span>
            <span className="text-body-2 text-t-primary text-right truncate">{value || "—"}</span>
        </div>
    );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <div>
            <div className="text-button text-t-secondary mb-2">{title}</div>
            {children}
        </div>
    );
}

function OpportunityFields({
    opp,
    stages,
    idx,
    canWrite,
    onMove,
}: {
    opp: Opportunity;
    stages: Stage[];
    idx: Map<string, Stage>;
    canWrite: boolean;
    onMove: (stage: string) => void;
}) {
    const opts = stages.map((s, i) => ({ id: i, name: s.label, value: s.value }));
    const current = opts.find((o) => o.value === opp.stage) ?? opts[0] ?? null;
    return (
        <Section title="Deal">
            <div className="mb-3">
                {canWrite && opts.length > 0 ? (
                    <Select
                        label="Stage"
                        value={current}
                        onChange={(o) => {
                            const f = opts.find((x) => x.id === o.id);
                            if (f && f.value !== opp.stage) onMove(f.value);
                        }}
                        options={opts}
                    />
                ) : (
                    <StageChip stage={stageMeta(idx, opp.stage)} />
                )}
            </div>
            <Row label="Amount" value={fmtMoney(opp.amount, opp.currencyCode)} />
            <Row label="Company" value={opp.companyName} />
            <Row label="Contact" value={opp.pointOfContactName} />
            <Row label="Close date" value={opp.closeDate ? fmtDate(opp.closeDate) : "—"} />
            <Row label="Created" value={fmtRelative(opp.createdAt)} />
        </Section>
    );
}

function PersonFields({ person }: { person: Person }) {
    return (
        <Section title="Contact">
            <Row label="Email" value={person.email} />
            <Row label="Phone" value={person.phone} />
            <Row label="Company" value={person.companyName} />
            <Row label="Title" value={person.jobTitle} />
            <Row label="City" value={person.city} />
            <Row label="Added" value={fmtRelative(person.createdAt)} />
        </Section>
    );
}

function CompanyFields({ company }: { company: Company }) {
    return (
        <Section title="Company">
            <Row
                label="Domain"
                value={
                    company.domain ? (
                        <a
                            href={`https://${company.domain.replace(/^https?:\/\//, "")}`}
                            target="_blank"
                            rel="noreferrer"
                            className="text-primary-01 hover:underline"
                        >
                            {company.domain}
                        </a>
                    ) : (
                        "—"
                    )
                }
            />
            <Row label="Location" value={[company.city, company.country].filter(Boolean).join(", ")} />
            <Row label="Employees" value={company.employees ?? "—"} />
            <Row label="Added" value={fmtRelative(company.createdAt)} />
        </Section>
    );
}

function Related({
    people,
    opportunities,
    idx,
    onOpen,
}: {
    people?: Person[];
    opportunities?: Opportunity[];
    idx: Map<string, Stage>;
    onOpen: (type: ActivityTarget, id: string) => void;
}) {
    if (!people?.length && !opportunities?.length) return null;
    return (
        <Section title="Linked records">
            <div className="flex flex-col gap-2">
                {(opportunities ?? []).map((o) => (
                    <button
                        key={o.id}
                        onClick={() => onOpen("opportunity", o.id)}
                        className="flex items-center justify-between gap-3 w-full p-3 rounded-2xl bg-b-surface1 text-left transition-colors hover:bg-b-highlight"
                    >
                        <span className="flex items-center gap-2 min-w-0">
                            <Icon name="chart" className="size-4 shrink-0 fill-t-tertiary" />
                            <span className="truncate text-body-2 text-t-primary">{o.name}</span>
                        </span>
                        <StageChip stage={stageMeta(idx, o.stage)} />
                    </button>
                ))}
                {(people ?? []).map((p) => (
                    <button
                        key={p.id}
                        onClick={() => onOpen("person", p.id)}
                        className="flex items-center gap-3 w-full p-3 rounded-2xl bg-b-surface1 text-left transition-colors hover:bg-b-highlight"
                    >
                        <Avatar name={p.name} url={p.avatarUrl} size={8} />
                        <span className="min-w-0">
                            <span className="block truncate text-body-2 text-t-primary">{p.name}</span>
                            <span className="block truncate text-caption text-t-tertiary">{p.email || p.phone || "—"}</span>
                        </span>
                    </button>
                ))}
            </div>
        </Section>
    );
}

function Activity({
    target,
    notes,
    tasks,
    canWrite,
    onAdded,
}: {
    target: Target;
    notes?: { id: string; title: string; body: string; createdAt?: string | null }[];
    tasks?: { id: string; title: string; status: string; dueAt?: string | null }[];
    canWrite: boolean;
    onAdded: () => void;
}) {
    const [text, setText] = useState("");
    const add = useMutation({
        mutationFn: () =>
            addNote({ body: text.trim(), title: "Note", target_type: target.type, target_id: target.id }),
        onSuccess: () => {
            setText("");
            onAdded();
        },
    });
    return (
        <Section title="Activity">
            {canWrite && (
                <div className="mb-3">
                    <Field
                        textarea
                        placeholder="Add a note…"
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                    />
                    <div className="flex justify-end mt-2">
                        <Button
                            isStroke
                            className="!h-10"
                            disabled={!text.trim() || add.isPending}
                            onClick={() => add.mutate()}
                        >
                            {add.isPending ? "Saving…" : "Add note"}
                        </Button>
                    </div>
                </div>
            )}
            <div className="flex flex-col gap-2">
                {(tasks ?? []).map((t) => (
                    <div key={t.id} className="flex items-start gap-2.5 p-3 rounded-2xl bg-b-surface1">
                        <Icon name="check-circle" className="size-4 mt-0.5 shrink-0 fill-primary-05" />
                        <div className="min-w-0">
                            <div className="text-body-2 text-t-primary truncate">{t.title}</div>
                            <div className="text-caption text-t-tertiary">
                                {t.status}
                                {t.dueAt ? ` · due ${fmtDate(t.dueAt)}` : ""}
                            </div>
                        </div>
                    </div>
                ))}
                {(notes ?? []).map((n) => (
                    <div key={n.id} className="flex items-start gap-2.5 p-3 rounded-2xl bg-b-surface1">
                        <Icon name="feather" className="size-4 mt-0.5 shrink-0 fill-t-secondary" />
                        <div className="min-w-0">
                            <div className="text-body-2 text-t-primary whitespace-pre-wrap break-words">
                                {n.body || n.title}
                            </div>
                            <div className="text-caption text-t-tertiary">{fmtRelative(n.createdAt)}</div>
                        </div>
                    </div>
                ))}
                {!notes?.length && !tasks?.length && (
                    <div className="text-body-2 text-t-tertiary py-2">No notes or tasks yet.</div>
                )}
            </div>
        </Section>
    );
}
