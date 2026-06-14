"use client";

// ============================================================================
// _add-provider-modal — ADD / EDIT a provider definition (design crazy-ui-security
// §B). Extends the api-keys AddCustomModal grammar, generalised to the full
// registry spec: display_name / capability multiselect / type / base_url
// (or SSRF-decomposed host+port for self-hosted) / auth_scheme / auth_header_name
// / transform_type (+ visual FieldMapper for custom) / model / cost / api_key.
//
// MODES:
//   • vendor add (default): Hosted API only; self_hosted is super-admin-only and the
//     backend 403s it — so the type Select hides Self-hosted unless `admin`.
//   • super-admin add (`admin`): Hosted + Self-hosted; the latter shows the
//     SSRF-decomposed host+port fields + the self-hosted server preset.
//   • edit: prefilled from a ProviderDef (key field hidden — keys are rotated via
//     the credential route + reveal, never re-pasted here).
//
// Slide-over via <Modal isSlidePanel>. Core_2, zero hex, registered glyphs only.
// ============================================================================

import { useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Switch from "@/components/Switch";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Badge from "@/components/Badge";
import { type SelectOption } from "@/types/select";
import {
    type ProviderDef,
    type ProviderDefInput,
    type Capability,
    type ProviderType,
    type AuthScheme,
    type TransformType,
    ALL_CAPABILITIES,
    CAPABILITY_LABEL,
    AUTH_SCHEME_LABEL,
    TRANSFORM_LABEL,
    SELFHOST_PRESETS,
    createProvider,
    updateProvider,
    adminCreateProvider,
    adminUpdateProvider,
    IntegrationError,
    humanizeError,
} from "@/lib/integrations";
import FieldMapper, { validateMap } from "./_field-mapper";
import { ghostBtnCls } from "./_shared";

const TYPE_OPTS_VENDOR: SelectOption[] = [{ id: 0, name: "Hosted API" }];
const TYPE_OPTS_ADMIN: SelectOption[] = [
    { id: 0, name: "Hosted API" },
    { id: 1, name: "Self-hosted" },
];
const TYPE_BY_IDX: ProviderType[] = ["hosted_api", "self_hosted"];

const AUTH_OPTS: SelectOption[] = (Object.keys(AUTH_SCHEME_LABEL) as AuthScheme[]).map((k, i) => ({
    id: i,
    name: AUTH_SCHEME_LABEL[k],
}));
const AUTH_BY_IDX = Object.keys(AUTH_SCHEME_LABEL) as AuthScheme[];

const TRANSFORM_OPTS: SelectOption[] = (Object.keys(TRANSFORM_LABEL) as TransformType[]).map((k, i) => ({
    id: i,
    name: TRANSFORM_LABEL[k],
}));
const TRANSFORM_BY_IDX = Object.keys(TRANSFORM_LABEL) as TransformType[];

const COST_UNIT_OPTS: SelectOption[] = [
    { id: 0, name: "per second" },
    { id: 1, name: "per generation" },
    { id: 2, name: "per 1k tokens" },
    { id: 3, name: "per character" },
    { id: 4, name: "per minute" },
];
const COST_UNIT_BY_IDX = ["per_second", "per_generation", "per_1k_tokens", "per_char", "per_minute"];

export default function AddProviderModal({
    open,
    onClose,
    onSaved,
    admin = false,
    edit = null,
    seedSelfHosted = false,
}: {
    open: boolean;
    onClose: () => void;
    onSaved: () => Promise<void> | void;
    admin?: boolean;
    edit?: ProviderDef | null;
    // pre-select the Self-hosted type on a NEW add (the SSRF-decomposed form).
    seedSelfHosted?: boolean;
}) {
    // a row with no id is a SEED (a pre-filled new form), not an edit.
    const isEdit = !!edit && !!edit.id;
    const [displayName, setDisplayName] = useState("");
    const [slug, setSlug] = useState("");
    const [caps, setCaps] = useState<Set<Capability>>(new Set());
    const [typeIdx, setTypeIdx] = useState<SelectOption>(TYPE_OPTS_VENDOR[0]);
    const [baseUrl, setBaseUrl] = useState("");
    const [host, setHost] = useState("");
    const [port, setPort] = useState("");
    const [presetIdx, setPresetIdx] = useState<SelectOption>(SELFHOST_PRESETS[0]);
    const [authIdx, setAuthIdx] = useState<SelectOption>(AUTH_OPTS[0]);
    const [authHeader, setAuthHeader] = useState("");
    const [transformIdx, setTransformIdx] = useState<SelectOption>(TRANSFORM_OPTS[0]);
    const [model, setModel] = useState("");
    const [requestMap, setRequestMap] = useState<Record<string, string>>({});
    const [responseMap, setResponseMap] = useState<Record<string, string>>({});
    const [costUsd, setCostUsd] = useState("");
    const [costUnitIdx, setCostUnitIdx] = useState<SelectOption>(COST_UNIT_OPTS[0]);
    const [apiKey, setApiKey] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    const typeOpts = admin ? TYPE_OPTS_ADMIN : TYPE_OPTS_VENDOR;
    const providerType = TYPE_BY_IDX[typeIdx.id as number];
    const isSelfHosted = providerType === "self_hosted";
    const transform = TRANSFORM_BY_IDX[transformIdx.id as number];
    const authScheme = AUTH_BY_IDX[authIdx.id as number] as AuthScheme;

    // hydrate / reset on open
    useEffect(() => {
        if (!open) return;
        if (edit && edit.id) {
            setDisplayName(edit.display_name || "");
            setSlug(edit.slug || "");
            setCaps(new Set(edit.capabilities || []));
            const tIdx = TYPE_BY_IDX.indexOf(edit.provider_type) >= 0 ? TYPE_BY_IDX.indexOf(edit.provider_type) : 0;
            setTypeIdx(typeOpts[Math.min(tIdx, typeOpts.length - 1)]);
            setBaseUrl(edit.base_url || "");
            const aIdx = AUTH_BY_IDX.indexOf(edit.auth_scheme);
            setAuthIdx(AUTH_OPTS[aIdx >= 0 ? aIdx : 0]);
            setAuthHeader(edit.auth_header_name || "");
            const trIdx = TRANSFORM_BY_IDX.indexOf(edit.transform_type);
            setTransformIdx(TRANSFORM_OPTS[trIdx >= 0 ? trIdx : 0]);
            setModel(edit.model_default || "");
            setRequestMap(edit.request_field_map || {});
            setResponseMap(edit.response_field_map || {});
            setCostUsd(edit.cost_per_unit_micros != null ? String(edit.cost_per_unit_micros / 1_000_000) : "");
            const cuIdx = COST_UNIT_BY_IDX.indexOf(edit.cost_unit || "");
            setCostUnitIdx(COST_UNIT_OPTS[cuIdx >= 0 ? cuIdx : 0]);
        } else {
            setDisplayName("");
            setSlug("");
            setCaps(new Set());
            // seed Self-hosted (admin only) -> idx 1; else Hosted -> idx 0.
            setTypeIdx(seedSelfHosted && admin ? typeOpts[1] || typeOpts[0] : typeOpts[0]);
            setBaseUrl("");
            setHost("");
            setPort("");
            setPresetIdx(SELFHOST_PRESETS[0]);
            setAuthIdx(AUTH_OPTS[0]);
            setAuthHeader("");
            setTransformIdx(TRANSFORM_OPTS[0]);
            setModel("");
            setRequestMap({});
            setResponseMap({});
            setCostUsd("");
            setCostUnitIdx(COST_UNIT_OPTS[0]);
        }
        setApiKey("");
        setError("");
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, edit, admin, seedSelfHosted]);

    const toggleCap = (cap: Capability) => {
        setCaps((s) => {
            const n = new Set(s);
            if (n.has(cap)) n.delete(cap);
            else n.add(cap);
            return n;
        });
    };

    // derive base_url from host+port for self-hosted (SSRF layer-1: separate fields).
    const effectiveBaseUrl = useMemo(() => {
        if (isSelfHosted && host.trim()) {
            const scheme = host.includes("://") ? "" : "http://";
            const p = port.trim() ? `:${port.trim()}` : "";
            return `${scheme}${host.trim().replace(/\/$/, "")}${p}`;
        }
        return baseUrl.trim();
    }, [isSelfHosted, host, port, baseUrl]);

    const canSave =
        displayName.trim() &&
        (slug.trim() || isEdit) &&
        effectiveBaseUrl &&
        caps.size > 0 &&
        (transform !== "custom_field_map" || !validateMap(requestMap)) &&
        (transform !== "custom_field_map" || !validateMap(responseMap));

    const buildInput = (): ProviderDefInput => {
        const input: ProviderDefInput = {
            slug: slug.trim() || displayName.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-"),
            display_name: displayName.trim(),
            provider_type: providerType,
            capabilities: Array.from(caps),
            base_url: effectiveBaseUrl,
            auth_scheme: authScheme,
            transform_type: transform,
        };
        if (authScheme === "api_key_header" && authHeader.trim()) input.auth_header_name = authHeader.trim();
        if (model.trim()) input.model_default = model.trim();
        if (transform === "custom_field_map") {
            input.request_field_map = requestMap;
            input.response_field_map = responseMap;
        }
        if (costUsd.trim() && !Number.isNaN(Number(costUsd))) {
            input.cost_per_unit_micros = Math.round(Number(costUsd) * 1_000_000);
            input.cost_unit = COST_UNIT_BY_IDX[costUnitIdx.id as number];
        }
        if (!isEdit && apiKey.trim()) input.api_key = apiKey.trim();
        return input;
    };

    const submit = async () => {
        if (!canSave) {
            setError("Fill name, base URL and at least one capability.");
            return;
        }
        setBusy(true);
        setError("");
        try {
            const input = buildInput();
            if (isEdit && edit) {
                if (admin) await adminUpdateProvider(edit.id, input);
                else await updateProvider(edit.id, input);
            } else if (admin) {
                await adminCreateProvider(input);
            } else {
                await createProvider(input);
            }
            await onSaved();
            onClose();
        } catch (e) {
            setError(
                e instanceof IntegrationError ? e.message : humanizeError(String((e as Error)?.message || ""), 0),
            );
        } finally {
            setBusy(false);
        }
    };

    return (
        <Modal classWrapper="max-w-lg" open={open} onClose={() => !busy && onClose()} isSlidePanel>
            <div className="text-h6 text-t-primary mb-1">
                {isEdit ? "Edit provider" : isSelfHosted ? "Add a self-hosted endpoint" : "Add a provider"}
            </div>
            <p className="text-body-2 text-t-secondary mb-5">
                {isSelfHosted
                    ? "Point at a model you host. The endpoint is validated against the SSRF guard before it can serve — private, loopback and metadata addresses are refused."
                    : "Connect any AI or tool provider. Keys are stored encrypted and never shown again — only a masked preview."}
            </p>

            <div className="flex flex-col gap-4">
                <Field
                    label="Display name"
                    placeholder="e.g. My fal.ai · Acme LLM · Office GPU"
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                />
                {!isEdit && (
                    <Field
                        label="Slug (optional)"
                        placeholder="auto from the name — e.g. my-fal"
                        value={slug}
                        onChange={(e) => setSlug(e.target.value.replace(/[^a-z0-9-]/g, ""))}
                    />
                )}

                {/* capability multiselect */}
                <div>
                    <div className="text-button text-t-secondary mb-2">Capabilities</div>
                    <div className="flex items-center gap-1.5 flex-wrap">
                        {ALL_CAPABILITIES.map((cap) => {
                            const on = caps.has(cap);
                            return (
                                <button
                                    key={cap}
                                    type="button"
                                    onClick={() => toggleCap(cap)}
                                    className={`inline-flex items-center gap-1 h-8 px-3 rounded-full text-caption transition-all ${
                                        on
                                            ? "bg-b-surface2 text-t-primary border border-s-highlight"
                                            : "text-t-secondary border border-s-subtle hover:border-s-highlight"
                                    }`}
                                >
                                    {on && <Icon name="check" className="size-3 fill-t-primary" />}
                                    {CAPABILITY_LABEL[cap]}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {admin && (
                    <div>
                        <Select label="Type" value={typeIdx} onChange={setTypeIdx} options={typeOpts} />
                    </div>
                )}

                {isSelfHosted ? (
                    <>
                        <div>
                            <Select
                                label="Server"
                                value={presetIdx}
                                onChange={(o) => {
                                    setPresetIdx(o);
                                }}
                                options={SELFHOST_PRESETS.map((p) => ({ id: p.id, name: p.name }))}
                            />
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                            <Field
                                className="col-span-2"
                                label="Host"
                                placeholder="gpu.internal or 10.x is refused"
                                value={host}
                                onChange={(e) => setHost(e.target.value)}
                            />
                            <Field
                                label="Port"
                                placeholder="8000"
                                value={port}
                                onChange={(e) => setPort(e.target.value.replace(/[^0-9]/g, ""))}
                            />
                        </div>
                        <div className="flex items-center gap-2 text-caption text-t-secondary -mt-1">
                            <Icon name="chain" className="size-3.5 fill-t-secondary shrink-0" />
                            Will probe <span className="font-mono text-t-primary">{effectiveBaseUrl || "—"}</span>
                        </div>
                    </>
                ) : (
                    <Field
                        label="Base URL"
                        placeholder="https://api.example.com/v1"
                        value={baseUrl}
                        onChange={(e) => setBaseUrl(e.target.value)}
                    />
                )}

                <div className="grid grid-cols-2 gap-3">
                    <Select label="Auth" value={authIdx} onChange={setAuthIdx} options={AUTH_OPTS} />
                    <Select
                        label="Format"
                        value={transformIdx}
                        onChange={setTransformIdx}
                        options={TRANSFORM_OPTS}
                    />
                </div>

                {authScheme === "api_key_header" && (
                    <Field
                        label="Auth header name"
                        placeholder="x-api-key"
                        value={authHeader}
                        onChange={(e) => setAuthHeader(e.target.value)}
                    />
                )}

                {transform !== "custom_field_map" && (
                    <Field
                        label="Default model (optional)"
                        placeholder="e.g. gpt-4o-mini · kling-v2 · llama-3.3-70b"
                        value={model}
                        onChange={(e) => setModel(e.target.value)}
                    />
                )}

                {transform === "custom_field_map" && (
                    <FieldMapper
                        requestMap={requestMap}
                        responseMap={responseMap}
                        onChange={(req, res) => {
                            setRequestMap(req);
                            setResponseMap(res);
                        }}
                    />
                )}

                {/* cost (optional) */}
                <div className="grid grid-cols-2 gap-3">
                    <Field
                        label="Cost (USD, optional)"
                        placeholder="0.05"
                        value={costUsd}
                        onChange={(e) => setCostUsd(e.target.value.replace(/[^0-9.]/g, ""))}
                    />
                    <Select label="Per" value={costUnitIdx} onChange={setCostUnitIdx} options={COST_UNIT_OPTS} />
                </div>

                {!isEdit && authScheme !== "none" && (
                    <Field
                        label={admin ? "API key (stored as a platform key)" : "API key (your own — optional)"}
                        type="password"
                        autoComplete="off"
                        placeholder="Paste the key — stored encrypted"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                    />
                )}

                {transform === "openai_compat" && (
                    <div className="flex items-center gap-2 text-caption text-t-secondary">
                        <Icon name="check-circle" className="size-3.5 fill-t-secondary shrink-0" />
                        OpenAI-compatible — no field-mapping needed.
                    </div>
                )}
            </div>

            {error && (
                <div className="mt-4 flex items-start gap-2 text-body-2 text-primary-03">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0 mt-0.5" />
                    {error}
                </div>
            )}

            <div className="mt-6 flex items-center justify-end gap-3">
                <button className={ghostBtnCls} onClick={() => !busy && onClose()} disabled={busy}>
                    Cancel
                </button>
                <Button isBlack onClick={submit} disabled={busy || !canSave}>
                    {busy ? "Saving…" : isEdit ? "Save changes" : "Add provider"}
                </Button>
            </div>

            {!isEdit && (
                <div className="mt-4 flex items-center gap-1.5 flex-wrap text-caption text-t-tertiary">
                    <Badge variant="neutral">{caps.size} capabilities</Badge>
                    {isSelfHosted && <Badge variant="warning">SSRF-validated on save</Badge>}
                </div>
            )}
        </Modal>
    );
}
