"use client";

// ============================================================================
// PVS Phase-1 · Custom providers — /super-admin/api-keys
//
// Register ANY OpenAI-compatible (or API-compatible) STT/LLM/TTS endpoint as a named provider:
// name + kind + base_url + model + key. Stored in a SEPARATE encrypted Fernet store on the box
// (var/custom_providers.json.enc) — DELIBERATELY isolated from the live key pool that feeds the
// earner. In Phase 1 these appear in the per-campaign Advanced provider selects; ROUTING an
// outbound call through a custom provider is Phase 2 (OB-PROV). The raw key is never returned —
// only a masked preview. Every route is require_super_admin (legacy password -> 403 by design).
// ============================================================================

import { useCallback, useEffect, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Switch from "@/components/Switch";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import {
    getCustomProviders,
    addCustomProvider,
    updateCustomProvider,
    deleteCustomProvider,
    fetchCompanyLogo,
    type CustomProvider,
} from "@/lib/api";
import { ghostBtnCls } from "../_shared";
import { type SelectOption } from "@/types/select";

const KIND_OPTS: SelectOption[] = [
    { id: 0, name: "LLM (language model)" },
    { id: 1, name: "STT (speech-to-text)" },
    { id: 2, name: "TTS (text-to-speech)" },
];
const KIND_BY_IDX: ("llm" | "stt" | "tts")[] = ["llm", "stt", "tts"];
const KIND_LABEL: Record<string, string> = { llm: "LLM", stt: "STT", tts: "TTS" };

export default function CustomProvidersCard({
    flash,
}: {
    flash: (msg: string, type?: "success" | "error") => void;
}) {
    const [rows, setRows] = useState<CustomProvider[]>([]);
    const [adding, setAdding] = useState(false);

    const load = useCallback(async () => {
        try {
            const d = await getCustomProviders();
            setRows(d.custom_providers);
        } catch {
            /* dormant-safe */
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const onToggle = async (row: CustomProvider, enabled: boolean) => {
        const prev = rows;
        setRows((r) => r.map((x) => (x.id === row.id ? { ...x, enabled } : x)));
        try {
            await updateCustomProvider(row.id, { enabled });
        } catch {
            setRows(prev);
            flash("Couldn't update the provider.", "error");
        }
    };

    const onDelete = async (row: CustomProvider) => {
        const prev = rows;
        setRows((r) => r.filter((x) => x.id !== row.id));
        try {
            await deleteCustomProvider(row.id);
            flash("Custom provider removed.");
        } catch {
            setRows(prev);
            flash("Couldn't delete the provider.", "error");
        }
    };

    return (
        <Card title="Custom providers">
            <div className="px-1 -mt-1 mb-4 flex items-center justify-between gap-3 flex-wrap">
                <p className="text-body-2 text-t-secondary max-w-xl">
                    Register your own STT / LLM / TTS endpoint (OpenAI-compatible base URL + model).
                    Stored encrypted, isolated from the platform key pool. Available in the
                    per-campaign Advanced provider picker. Routing live outbound calls through a custom
                    provider ships in Phase 2.
                </p>
                <button className={ghostBtnCls} onClick={() => setAdding(true)}>
                    <Icon name="plus" className="size-4 fill-inherit" />
                    Add custom provider
                </button>
            </div>

            {rows.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-s-subtle px-5 py-8 text-center text-body-2 text-t-secondary">
                    No custom providers yet — add one to extend the per-campaign provider options.
                </div>
            ) : (
                <div className="flex flex-col divide-y divide-s-subtle">
                    {rows.map((row) => (
                        <div
                            key={row.id}
                            className="flex items-center gap-3 py-3.5 flex-wrap sm:flex-nowrap"
                        >
                            <span className="font-medium text-t-primary truncate max-w-[10rem]">
                                {row.name}
                            </span>
                            <Badge variant="info">{KIND_LABEL[row.kind] || row.kind}</Badge>
                            <Badge variant={row.available ? "success" : "neutral"} dot={row.available}>
                                {row.available ? "Ready" : "Disabled / no key"}
                            </Badge>
                            <span className="text-caption text-t-secondary truncate max-w-[12rem] hidden sm:inline">
                                {row.model}
                            </span>
                            <span className="font-mono text-caption text-t-tertiary tabular-nums hidden md:inline">
                                {row.masked}
                            </span>
                            <div className="ml-auto flex items-center gap-3">
                                <Switch
                                    checked={row.enabled}
                                    onChange={(en) => onToggle(row, en)}
                                />
                                <DeleteBtn onConfirm={() => onDelete(row)} />
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <AddCustomModal
                open={adding}
                onClose={() => setAdding(false)}
                onAdded={async () => {
                    await load();
                    flash("Custom provider added.");
                }}
            />
        </Card>
    );
}

function DeleteBtn({ onConfirm }: { onConfirm: () => void }) {
    const [confirming, setConfirming] = useState(false);
    return confirming ? (
        <div className="flex items-center gap-1.5">
            <button
                className="inline-flex items-center h-8 px-3 rounded-full text-caption text-primary-03 border border-primary-03/30 hover:bg-primary-03/8 transition-colors"
                onClick={onConfirm}
            >
                Confirm
            </button>
            <button
                className="inline-flex items-center h-8 px-3 rounded-full text-caption text-t-secondary hover:text-t-primary transition-colors"
                onClick={() => setConfirming(false)}
            >
                Cancel
            </button>
        </div>
    ) : (
        <button
            aria-label="Delete custom provider"
            className="inline-flex items-center justify-center size-8 rounded-full text-t-secondary hover:text-primary-03 hover:bg-primary-03/8 transition-colors"
            onClick={() => setConfirming(true)}
        >
            <Icon name="trash" className="size-4 fill-inherit" />
        </button>
    );
}

function AddCustomModal({
    open,
    onClose,
    onAdded,
}: {
    open: boolean;
    onClose: () => void;
    onAdded: () => Promise<void>;
}) {
    const [name, setName] = useState("");
    const [kind, setKind] = useState<SelectOption>(KIND_OPTS[0]);
    const [baseUrl, setBaseUrl] = useState("");
    const [model, setModel] = useState("");
    const [key, setKey] = useState("");
    const [website, setWebsite] = useState("");
    const [logoUrl, setLogoUrl] = useState("");
    const [fetchingLogo, setFetchingLogo] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        if (open) {
            setName("");
            setKind(KIND_OPTS[0]);
            setBaseUrl("");
            setModel("");
            setKey("");
            setWebsite("");
            setLogoUrl("");
            setFetchingLogo(false);
            setError("");
        }
    }, [open]);

    // Website → logo: best-effort, never blocks the form (Clearbit → favicon fallback on the backend).
    const grabLogo = async (u: string) => {
        const url = (u || "").trim();
        if (!url) return;
        setFetchingLogo(true);
        try {
            const r = await fetchCompanyLogo(url);
            if (r.logo_url) setLogoUrl(r.logo_url);
        } catch { /* ignore — logo is optional */ }
        finally { setFetchingLogo(false); }
    };

    const submit = async () => {
        if (!name.trim() || !baseUrl.trim() || !model.trim()) {
            setError("Name, base URL and model are required.");
            return;
        }
        setBusy(true);
        setError("");
        try {
            await addCustomProvider({
                name: name.trim(),
                kind: KIND_BY_IDX[kind.id as number],
                base_url: baseUrl.trim(),
                model: model.trim(),
                key: key.trim(),
                logo_url: logoUrl.trim(),
            });
            await onAdded();
            onClose();
        } catch {
            setError("Couldn't add the provider. Check the details and try again.");
        } finally {
            setBusy(false);
        }
    };

    return (
        <Modal classWrapper="max-w-md" open={open} onClose={() => !busy && onClose()}>
            <div className="text-h6 text-t-primary mb-1">Add a custom provider</div>
            <p className="text-body-2 text-t-secondary mb-5">
                Point at any OpenAI-compatible endpoint. The key is stored encrypted and never shown
                again — only a masked preview.
            </p>

            <Field
                label="Name"
                placeholder="e.g. My SambaNova"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mb-4"
            />
            <div className="mb-4">
                <Field
                    label="Website (for logo)"
                    placeholder="https://provider.com"
                    value={website}
                    onChange={(e) => setWebsite(e.target.value)}
                    className="mb-2"
                />
                <div className="flex items-center gap-2">
                    <button
                        type="button"
                        onClick={() => grabLogo(website)}
                        disabled={fetchingLogo || !website.trim()}
                        className={ghostBtnCls}
                    >
                        {fetchingLogo ? "Fetching…" : "Fetch logo"}
                    </button>
                    {logoUrl && (
                        <>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={logoUrl} alt="" className="size-8 rounded-lg object-contain bg-b-surface1 ring-1 ring-inset ring-s-subtle" onError={() => setLogoUrl("")} />
                            <span className="text-caption text-t-tertiary">Logo fetched</span>
                        </>
                    )}
                </div>
            </div>
            <div className="mb-4">
                <Select label="Kind" value={kind} onChange={setKind} options={KIND_OPTS} />
            </div>
            <Field
                label="Base URL"
                placeholder="https://api.example.com/v1"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                className="mb-4"
            />
            <Field
                label="Model"
                placeholder="e.g. llama-3.3-70b"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="mb-4"
            />
            <Field
                label="API key (optional)"
                type="password"
                autoComplete="off"
                placeholder="Paste the key"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                className="mb-2"
            />

            {error && (
                <div className="mt-3 flex items-center gap-2 text-body-2 text-primary-03">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0" />
                    {error}
                </div>
            )}

            <div className="mt-6 flex items-center justify-end gap-3">
                <button className={ghostBtnCls} onClick={() => !busy && onClose()} disabled={busy}>
                    Cancel
                </button>
                <Button
                    isBlack
                    onClick={submit}
                    disabled={busy || !name.trim() || !baseUrl.trim() || !model.trim()}
                >
                    {busy ? "Adding…" : "Add provider"}
                </Button>
            </div>
        </Modal>
    );
}
