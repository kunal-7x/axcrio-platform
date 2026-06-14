"use client";

// ============================================================================
// _provider-card — one registered provider (design crazy-ui-security §B). A
// verbatim port of the api-keys ProviderCard/KeyRow grammar, generalised to the
// registry: display_name + capability chips + type pill + a masked credential row
// + a HealthBadge (circuit-state) + an enable Switch + a "Test connection" text
// button that POSTs the probe and renders the result inline + a two-step
// confirm-delete. The masked credential row carries the PIN-gated REVEAL only for
// a vendor's OWN (integration-scope) key; a platform (ai_provider) key shows a
// "Platform-managed" lock and NO reveal (Vault §9 trust model, FE defence-in-depth).
// ============================================================================

import { useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Switch from "@/components/Switch";
import {
    type ProviderDef,
    type TestResult,
    testConnection,
    updateProvider,
    adminUpdateProvider,
    deleteProvider,
    adminDeleteProvider,
    storeCredential,
    fmtCost,
    IntegrationError,
    humanizeError,
} from "@/lib/integrations";
import {
    HealthBadge,
    CapabilityChips,
    TypePill,
    PlatformLock,
    textBtnCls,
} from "./_shared";
import RevealPin from "./_reveal-pin";

export default function ProviderCard({
    def,
    admin = false,
    onChanged,
    onEdit,
    onToast,
}: {
    def: ProviderDef;
    admin?: boolean;
    onChanged: () => void;
    onEdit: (def: ProviderDef) => void;
    onToast: (msg: string, type?: "success" | "error") => void;
}) {
    const [enabled, setEnabled] = useState(def.is_enabled);
    const [testing, setTesting] = useState(false);
    const [test, setTest] = useState<TestResult | null>(null);
    const [testErr, setTestErr] = useState("");
    const [confirming, setConfirming] = useState(false);
    const [addingKey, setAddingKey] = useState(false);
    const [keyInput, setKeyInput] = useState("");

    // a vendor's own key (integration scope) is revealable; a platform key is not.
    // The backend marks platform creds masked-only; here we treat a `_global` def's
    // credential as platform (not vendor-revealable). A vendor-owned def's masked
    // key is revealable.
    const isPlatformKey = def.is_global; // platform-shared def → masked-only
    const hasKey = !!def.masked;

    const upd = admin ? adminUpdateProvider : updateProvider;
    const del = admin ? adminDeleteProvider : deleteProvider;

    const onToggle = async (next: boolean) => {
        setEnabled(next);
        try {
            await upd(def.id, { is_enabled: next });
            onChanged();
        } catch {
            setEnabled(!next);
            onToast("Couldn't update the provider.", "error");
        }
    };

    const onTest = async () => {
        setTesting(true);
        setTestErr("");
        setTest(null);
        try {
            const r = await testConnection(def.id, admin);
            setTest(r);
        } catch (e) {
            setTestErr(e instanceof IntegrationError ? e.message : humanizeError(String((e as Error)?.message || ""), 0));
        } finally {
            setTesting(false);
        }
    };

    const onDelete = async () => {
        try {
            await del(def.id);
            onToast("Provider removed.");
            onChanged();
        } catch (e) {
            onToast(e instanceof IntegrationError ? e.message : "Couldn't delete the provider.", "error");
        }
    };

    const onStoreKey = async () => {
        if (!keyInput.trim()) return;
        try {
            await storeCredential(def.id, keyInput.trim());
            onToast("Key stored — encrypted at rest.");
            setKeyInput("");
            setAddingKey(false);
            onChanged();
        } catch (e) {
            onToast(e instanceof IntegrationError ? e.message : "Couldn't store the key.", "error");
        }
    };

    return (
        <Card title={def.display_name || def.slug}>
            {/* head meta row */}
            <div className="px-1 -mt-1 mb-4 flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                    <TypePill type={def.provider_type} />
                    <HealthBadge circuit={def.circuit} />
                    {def.is_global && (
                        <span className="text-caption text-t-tertiary">platform catalogue</span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button className={textBtnCls} onClick={() => onEdit(def)}>
                        Edit
                    </button>
                    <Switch checked={enabled} onChange={onToggle} />
                </div>
            </div>

            {/* capability chips + base url */}
            <div className="px-1 mb-3 flex flex-col gap-2">
                <CapabilityChips capabilities={def.capabilities} />
                <div className="flex items-center gap-2 text-caption text-t-secondary flex-wrap">
                    <span className="font-mono text-t-tertiary truncate max-w-[22rem]" title={def.base_url}>
                        {def.base_url}
                    </span>
                    {def.model_default && <span className="text-t-tertiary">· {def.model_default}</span>}
                    {def.cost_per_unit_micros != null && (
                        <span className="text-t-tertiary">· {fmtCost(def.cost_per_unit_micros, def.cost_unit)}</span>
                    )}
                </div>
            </div>

            {/* credential row */}
            <div className="px-1 py-3 border-t border-s-subtle flex items-center gap-3 flex-wrap">
                {hasKey ? (
                    <>
                        <span className="font-mono text-body-2 text-t-primary tabular-nums">{def.masked}</span>
                        {isPlatformKey ? (
                            <PlatformLock />
                        ) : (
                            <div className="flex items-center gap-2">
                                <RevealPin providerId={def.id} onToast={onToast} />
                                <button className={textBtnCls} onClick={() => setAddingKey(true)} title="Replace the key">
                                    <Icon name="clock-1" className="size-3.5 fill-inherit" />
                                    Rotate
                                </button>
                            </div>
                        )}
                    </>
                ) : addingKey ? (
                    <div className="flex items-center gap-2 flex-1 flex-wrap">
                        <input
                            type="password"
                            autoComplete="off"
                            autoFocus
                            value={keyInput}
                            onChange={(e) => setKeyInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") onStoreKey();
                                if (e.key === "Escape") {
                                    setAddingKey(false);
                                    setKeyInput("");
                                }
                            }}
                            placeholder="Paste your key — stored encrypted"
                            className="flex-1 min-w-[12rem] h-8 px-3 rounded-full bg-b-surface2 border border-s-subtle text-body-2 text-t-primary focus:outline-none focus:border-s-highlight"
                        />
                        <button className={textBtnCls} onClick={onStoreKey} disabled={!keyInput.trim()}>
                            Save key
                        </button>
                        <button
                            className="inline-flex items-center h-8 px-2.5 rounded-full text-caption text-t-secondary hover:text-t-primary transition-colors"
                            onClick={() => {
                                setAddingKey(false);
                                setKeyInput("");
                            }}
                        >
                            Cancel
                        </button>
                    </div>
                ) : (
                    <button className={textBtnCls} onClick={() => setAddingKey(true)}>
                        <Icon name="lock" className="size-3.5 fill-inherit" />
                        Add a key
                    </button>
                )}
            </div>

            {/* actions: test connection + delete */}
            <div className="px-1 pt-3 flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                    <button className={textBtnCls} onClick={onTest} disabled={testing}>
                        {testing ? "Testing…" : "Test connection"}
                    </button>
                    {test && (
                        <span
                            className={`inline-flex items-center gap-1.5 text-caption ${
                                test.healthy ? "text-t-secondary" : "text-primary-03"
                            }`}
                        >
                            <Icon
                                name={test.healthy ? "check-circle" : "info"}
                                className={`size-3.5 ${test.healthy ? "fill-t-secondary" : "fill-primary-03"}`}
                            />
                            {test.healthy
                                ? `Connected · ${test.latency_ms}ms${test.detail ? ` · ${test.detail}` : ""}`
                                : `Failed · ${test.detail || "no response"}`}
                        </span>
                    )}
                    {testErr && (
                        <span className="inline-flex items-center gap-1.5 text-caption text-primary-03">
                            <Icon name="info" className="size-3.5 fill-primary-03" />
                            {testErr}
                        </span>
                    )}
                </div>

                {confirming ? (
                    <div className="flex items-center gap-1.5">
                        <button
                            className="inline-flex items-center h-8 px-3 rounded-full text-caption text-primary-03 border border-primary-03/30 hover:bg-primary-03/8 transition-colors"
                            onClick={onDelete}
                        >
                            Confirm delete
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
                        aria-label="Delete provider"
                        className="inline-flex items-center justify-center size-8 rounded-full text-t-secondary hover:text-primary-03 hover:bg-primary-03/8 transition-colors"
                        onClick={() => setConfirming(true)}
                    >
                        <Icon name="trash" className="size-4 fill-inherit" />
                    </button>
                )}
            </div>
        </Card>
    );
}
