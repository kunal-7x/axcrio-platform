"use client";

// ============================================================================
// LPR · API Keys (PLATFORM PROVIDERS) — /super-admin/api-keys
//
// The founder adds ANY number of Groq / Sarvam / SambaNova / OpenRouter keys.
// Stored ENCRYPTED on the box (key-store); the live AIM voice rotation HOT-RELOADS
// them in real time — no redeploy, no restart. One Card per provider; each key
// row shows a masked value, an editable label, an enable Switch, a delete, and a
// LIVE status dot (green = in rotation · amber = cooling after a 429 · grey =
// disabled) fed by /admin/provider-keys/status polled every 5s.
//
// SECURITY: the raw key is NEVER returned by the API (only `masked`); the add
// input is type=password and never pre-filled. Every route is require_super_admin
// (403 for vendors / legacy-pw) — this page is cosmetic, the server is the boundary.
// Zero raw hex — Signal tokens only.
// ============================================================================

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Switch from "@/components/Switch";
import Field from "@/components/Field";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Spinner from "@/components/Spinner";
import {
    getProviderKeys,
    getProviderKeyStatus,
    addProviderKey,
    updateProviderKey,
    deleteProviderKey,
    type ProviderName,
    type ProviderKeyRow,
    type ProviderKeyStatusRow,
} from "@/lib/api";
import {
    SuperAdminGuard,
    SuperAdminHeaderF3,
    ErrorBanner,
    ToastView,
    type Toast,
    ghostBtnCls,
} from "../_shared";
import CustomProvidersCard from "./_custom-providers";

// ---- provider catalogue (display only; the backend allow-lists the same set) ----
const PROVIDERS: { id: ProviderName; name: string; blurb: string; prefix: string }[] = [
    { id: "groq", name: "Groq", blurb: "Primary LLM — fastest. Add keys from several accounts to multiply the daily token pool.", prefix: "gsk_" },
    { id: "sambanova", name: "SambaNova", blurb: "Final LLM fallback (Llama-3.3-70B) after every Groq key is cooling.", prefix: "" },
    { id: "sarvam", name: "Sarvam", blurb: "Speech-to-text. Rotated so one rate-limited key never stalls a call.", prefix: "" },
    { id: "openrouter", name: "OpenRouter", blurb: "Free emergency LLM fallback, used last.", prefix: "sk-or-" },
];

type StatusMap = Record<string, ProviderKeyStatusRow>; // keyed by row id

export default function ApiKeysPage() {
    return (
        <SuperAdminGuard>
            <Layout title="API Keys">
                <SuperAdminHeaderF3 />
                <ApiKeysBody />
            </Layout>
        </SuperAdminGuard>
    );
}

function ApiKeysBody() {
    const [keys, setKeys] = useState<Record<ProviderName, ProviderKeyRow[]>>({
        groq: [], sarvam: [], sambanova: [], openrouter: [],
    });
    const [status, setStatus] = useState<StatusMap>({});
    const [envCount, setEnvCount] = useState<Record<string, number>>({});
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);
    const [addFor, setAddFor] = useState<ProviderName | null>(null);

    const load = useCallback(async () => {
        try {
            const d = await getProviderKeys();
            setKeys(d.providers);
            setErr("");
        } catch {
            setErr("Couldn't load provider keys.");
        } finally {
            setLoading(false);
        }
    }, []);

    // poll live pool status every 5s (cooling / pick_count / available + env-seed count)
    const pollStatus = useCallback(async () => {
        try {
            const d = await getProviderKeyStatus();
            const map: StatusMap = {};
            const env: Record<string, number> = {};
            (Object.keys(d.status) as ProviderName[]).forEach((p) => {
                let envN = 0;
                d.status[p].forEach((r) => {
                    map[r.id] = r;
                    if (r.source === "env") envN += 1;
                });
                env[p] = envN;
            });
            setStatus(map);
            setEnvCount(env);
        } catch {
            /* dormant-safe: leave the last snapshot */
        }
    }, []);

    useEffect(() => {
        load();
        pollStatus();
        const t = setInterval(pollStatus, 5000);
        return () => clearInterval(t);
    }, [load, pollStatus]);

    const flash = (msg: string, type: Toast["type"] = "success") => setToast({ msg, type });

    // ---- optimistic mutations -------------------------------------------------
    const onToggle = async (p: ProviderName, row: ProviderKeyRow, enabled: boolean) => {
        const prev = keys[p];
        setKeys((k) => ({ ...k, [p]: k[p].map((x) => (x.id === row.id ? { ...x, enabled } : x)) }));
        try {
            await updateProviderKey(row.id, { enabled });
            pollStatus();
        } catch {
            setKeys((k) => ({ ...k, [p]: prev })); // rollback
            flash("Couldn't update the key.", "error");
        }
    };

    const onDelete = async (p: ProviderName, row: ProviderKeyRow) => {
        const prev = keys[p];
        setKeys((k) => ({ ...k, [p]: k[p].filter((x) => x.id !== row.id) }));
        try {
            await deleteProviderKey(row.id);
            flash("Key deleted — removed from the live rotation.");
            pollStatus();
        } catch {
            setKeys((k) => ({ ...k, [p]: prev })); // rollback
            flash("Couldn't delete the key.", "error");
        }
    };

    const onAdd = async (p: ProviderName, key: string, label: string) => {
        const res = await addProviderKey(p, key, label || undefined);
        if (res.deduped) {
            flash("That key is already in the pool.", "error");
        } else {
            flash("Key added — it's in the live rotation now.");
        }
        await load();
        pollStatus();
    };

    return (
        <>
            <div className="mb-5 flex items-center gap-2 p-3.5 rounded-3xl bg-b-surface2 border border-s-subtle text-body-2 text-t-secondary">
                <Icon name="info" className="size-4 fill-t-secondary shrink-0" />
                Live — a key you add or disable here reaches the running voice agent within seconds. No redeploy.
            </div>

            <ErrorBanner msg={err} />

            {loading ? (
                <div className="flex items-center justify-center py-32">
                    <Spinner />
                </div>
            ) : (
                <div className="flex flex-col gap-5">
                    {PROVIDERS.map((prov) => (
                        <ProviderCard
                            key={prov.id}
                            prov={prov}
                            rows={keys[prov.id] || []}
                            status={status}
                            envCount={envCount[prov.id] || 0}
                            onAdd={() => setAddFor(prov.id)}
                            onToggle={onToggle}
                            onDelete={onDelete}
                        />
                    ))}
                    {/* PVS Phase-1: register custom OpenAI-compatible STT/LLM/TTS providers
                        (isolated encrypted store; surfaced in the per-campaign Advanced picker). */}
                    <CustomProvidersCard flash={flash} />
                </div>
            )}

            <AddKeyModal
                provider={addFor}
                onClose={() => setAddFor(null)}
                onAdd={onAdd}
            />
            <ToastView toast={toast} onClose={() => setToast(null)} />
        </>
    );
}

// ---- one provider card ------------------------------------------------------
function ProviderCard({
    prov, rows, status, envCount, onAdd, onToggle, onDelete,
}: {
    prov: { id: ProviderName; name: string; blurb: string };
    rows: ProviderKeyRow[];
    status: StatusMap;
    envCount: number;
    onAdd: () => void;
    onToggle: (p: ProviderName, row: ProviderKeyRow, enabled: boolean) => void;
    onDelete: (p: ProviderName, row: ProviderKeyRow) => void;
}) {
    // live rotation summary (store rows + env-seed rows)
    const live = useMemo(() => {
        const ids = rows.map((r) => r.id);
        const storeAvail = ids.filter((id) => status[id]?.available).length;
        return { storeAvail };
    }, [rows, status]);

    return (
        <Card title={prov.name}>
            <div className="px-1 -mt-1 mb-4 flex items-center justify-between gap-3 flex-wrap">
                <p className="text-body-2 text-t-secondary max-w-xl">{prov.blurb}</p>
                <button className={ghostBtnCls} onClick={onAdd}>
                    <Icon name="plus" className="size-4 fill-inherit" />
                    Add key
                </button>
            </div>

            <div className="px-1 mb-3 flex items-center gap-2 flex-wrap text-caption text-t-secondary">
                <Badge variant="success" dot>
                    {live.storeAvail + envCount} in rotation
                </Badge>
                {envCount > 0 && (
                    <span className="inline-flex items-center gap-1.5">
                        <Icon name="lock" className="size-3.5 fill-t-secondary" />
                        {envCount} from server config (not editable here)
                    </span>
                )}
            </div>

            {rows.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-s-subtle px-5 py-8 text-center text-body-2 text-t-secondary">
                    {envCount > 0
                        ? "Running on server-config keys. Add your own to expand the pool."
                        : "No keys yet — add one to put this provider in rotation."}
                </div>
            ) : (
                <div className="flex flex-col divide-y divide-s-subtle">
                    {rows.map((row) => (
                        <KeyRow
                            key={row.id}
                            row={row}
                            st={status[row.id]}
                            onToggle={(en) => onToggle(prov.id, row, en)}
                            onDelete={() => onDelete(prov.id, row)}
                        />
                    ))}
                </div>
            )}
        </Card>
    );
}

// ---- one key row ------------------------------------------------------------
function KeyRow({
    row, st, onToggle, onDelete,
}: {
    row: ProviderKeyRow;
    st?: ProviderKeyStatusRow;
    onToggle: (enabled: boolean) => void;
    onDelete: () => void;
}) {
    const [confirming, setConfirming] = useState(false);

    // status dot: disabled (grey) · cooling after 429 (amber) · in rotation (green)
    const dot: { variant: "success" | "warning" | "neutral"; label: string } = !row.enabled
        ? { variant: "neutral", label: "Disabled" }
        : st?.cooling
        ? { variant: "warning", label: `Cooling ${Math.ceil(st.cooldown_remaining_s || 0)}s` }
        : { variant: "success", label: "In rotation" };

    return (
        <div className="flex items-center gap-3 py-3.5 flex-wrap sm:flex-nowrap">
            <span className="font-mono text-body-2 text-t-primary tabular-nums">{row.masked}</span>
            <Badge variant={dot.variant} dot={dot.variant !== "neutral"}>
                {dot.label}
            </Badge>
            {row.label && <span className="text-caption text-t-secondary truncate max-w-[12rem]">{row.label}</span>}

            <div className="ml-auto flex items-center gap-3">
                {typeof st?.pick_count === "number" && (
                    <span className="text-caption text-t-secondary tabular-nums hidden sm:inline">
                        {st.pick_count} picks
                    </span>
                )}
                <Switch checked={row.enabled} onChange={onToggle} />
                {confirming ? (
                    <div className="flex items-center gap-1.5">
                        <button
                            className="inline-flex items-center h-8 px-3 rounded-full text-caption text-primary-03 border border-primary-03/30 hover:bg-primary-03/8 transition-colors"
                            onClick={onDelete}
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
                        aria-label="Delete key"
                        className="inline-flex items-center justify-center size-8 rounded-full text-t-secondary hover:text-primary-03 hover:bg-primary-03/8 transition-colors"
                        onClick={() => setConfirming(true)}
                    >
                        <Icon name="trash" className="size-4 fill-inherit" />
                    </button>
                )}
            </div>
        </div>
    );
}

// ---- add-key modal ----------------------------------------------------------
function AddKeyModal({
    provider, onClose, onAdd,
}: {
    provider: ProviderName | null;
    onClose: () => void;
    onAdd: (p: ProviderName, key: string, label: string) => Promise<void>;
}) {
    const [key, setKey] = useState("");
    const [label, setLabel] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const meta = PROVIDERS.find((p) => p.id === provider);

    useEffect(() => {
        if (provider) {
            setKey("");
            setLabel("");
            setError("");
        }
    }, [provider]);

    const submit = async () => {
        if (!provider || !key.trim()) {
            setError("Paste a key first.");
            return;
        }
        setBusy(true);
        setError("");
        try {
            await onAdd(provider, key.trim(), label.trim());
            onClose();
        } catch {
            setError("Couldn't add the key. Check it and try again.");
        } finally {
            setBusy(false);
        }
    };

    return (
        <Modal classWrapper="max-w-md" open={!!provider} onClose={() => !busy && onClose()}>
            <div className="text-h6 text-t-primary mb-1">Add a {meta?.name} key</div>
            <p className="text-body-2 text-t-secondary mb-5">
                The key is stored encrypted on the server and enters the live rotation immediately.
                It is never shown again — only a masked preview.
            </p>

            <Field
                label="API key"
                type="password"
                autoComplete="off"
                placeholder={meta?.prefix ? `${meta.prefix}…` : "Paste the key"}
                value={key}
                onChange={(e) => setKey(e.target.value)}
                className="mb-4"
            />
            <Field
                label="Label (optional)"
                placeholder="e.g. account-2, billing card on file"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
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
                <Button isBlack onClick={submit} disabled={busy || !key.trim()}>
                    {busy ? "Adding…" : "Add key"}
                </Button>
            </div>
        </Modal>
    );
}
