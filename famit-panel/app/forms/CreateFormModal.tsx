"use client";

// Quick-create modal for a new form/survey. Keeps the routing surface contained
// (no /forms/new route) — it creates a DRAFT with an empty schema, then routes to
// the detail page where the field-schema editor lives. Built on the shared Modal
// + Field + Button language; envelope-aware via client.createForm.

import { useState } from "react";
import { useRouter } from "next/navigation";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Icon from "@/components/Icon";
import { createForm, FormsActionError, type FormKind } from "./client";

type Props = {
    open: boolean;
    onClose: () => void;
    onCreated: () => void;
};

const KIND_CARDS: {
    kind: FormKind;
    title: string;
    desc: string;
    icon: string;
}[] = [
    {
        kind: "form",
        title: "Form",
        desc: "Lead capture — every submission becomes a CRM contact.",
        icon: "font",
    },
    {
        kind: "survey",
        title: "Survey",
        desc: "Feedback with deterministic NPS / CSAT insights.",
        icon: "chart",
    },
];

export default function CreateFormModal({ open, onClose, onCreated }: Props) {
    const router = useRouter();
    const [kind, setKind] = useState<FormKind>("form");
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    function reset() {
        setKind("form");
        setTitle("");
        setDescription("");
        setError("");
        setSaving(false);
    }

    function handleClose() {
        if (saving) return;
        reset();
        onClose();
    }

    async function submit() {
        const t = title.trim();
        if (!t) {
            setError("Give your form a title to continue.");
            return;
        }
        setSaving(true);
        setError("");
        try {
            const form = await createForm({
                kind,
                title: t,
                description: description.trim(),
                status: "draft",
            });
            onCreated();
            reset();
            // Straight into the builder to add fields + publish.
            router.push(`/forms/${encodeURIComponent(form.id)}`);
        } catch (e: unknown) {
            setError(
                e instanceof FormsActionError || e instanceof Error
                    ? e.message
                    : "Could not create the form."
            );
            setSaving(false);
        }
    }

    return (
        <Modal open={open} onClose={handleClose}>
            <div className="mb-6">
                <div className="text-h5 mb-1">Create a form</div>
                <div className="text-body-2 text-t-secondary">
                    Start with the basics — you&apos;ll add fields and publish on
                    the next screen.
                </div>
            </div>

            {/* Kind picker */}
            <div className="grid grid-cols-2 gap-3 mb-5 max-sm:grid-cols-1">
                {KIND_CARDS.map((k) => {
                    const active = kind === k.kind;
                    return (
                        <button
                            key={k.kind}
                            type="button"
                            onClick={() => setKind(k.kind)}
                            className={`flex flex-col items-start gap-2 p-4 rounded-3xl border text-left transition-all ${
                                active
                                    ? "border-primary-01/60 bg-primary-01/6 ring-2 ring-primary-01/20"
                                    : "border-s-stroke2 hover:border-s-highlight"
                            }`}
                        >
                            <span
                                className={`grid place-items-center size-10 rounded-full ${
                                    active
                                        ? "bg-primary-01/15 fill-primary-01"
                                        : "bg-b-surface1 fill-t-secondary dark:bg-shade-04/60"
                                }`}
                            >
                                <Icon name={k.icon} className="fill-inherit" />
                            </span>
                            <span className="text-button text-t-primary">
                                {k.title}
                            </span>
                            <span className="text-caption text-t-tertiary">
                                {k.desc}
                            </span>
                        </button>
                    );
                })}
            </div>

            <Field
                label="Title"
                placeholder="e.g. Contact us, Product feedback"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => {
                    if (e.key === "Enter") submit();
                }}
                className="mb-4"
            />

            <Field
                label="Description"
                textarea
                placeholder="Optional — shown to people filling out the form."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="mb-4"
            />

            {error && (
                <div className="mb-4 flex items-center gap-2 p-3 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03">
                    <Icon
                        name="info"
                        className="size-4 shrink-0 fill-primary-03"
                    />
                    {error}
                </div>
            )}

            <div className="flex items-center justify-end gap-3">
                <Button isStroke onClick={handleClose} disabled={saving}>
                    Cancel
                </Button>
                <Button isBlack onClick={submit} disabled={saving}>
                    {saving ? "Creating…" : "Create & add fields"}
                </Button>
            </div>
        </Modal>
    );
}
