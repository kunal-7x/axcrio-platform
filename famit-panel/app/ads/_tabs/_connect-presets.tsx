"use client";

// Ad-Engine · CONNECT PRESETS (BLINDSPOTS B2/B3/B15) — the "paste your keys -> CONNECTED" wizard.
//
// The generic /integrations add-provider modal cannot, on its own, produce a def the ads engine
// can resolve: the vault resolves Meta/Google by named_provider "meta"/"google" (both share the
// capability `ad_platform`, so capability alone is ambiguous) and WhatsApp by named_provider
// "whatsapp" + capability `messaging`. It also needs a SPECIFIC credential BLOB shape — the exact
// fields each connector reads via get_secret_json(...)[field]. This wizard captures exactly those
// fields, sets named_provider + capability, and writes them as one JSON credential blob through the
// existing /provider-registry routes (createProvider -> storeCredential). The instant the key is
// saved, GET /ads/connections/status flips the channel to "configured" and POST /ads/connections/test
// proves the engine can read the required fields (secret-free — field NAMES only).
//
// Core_2 kit, zero raw hex, registered glyphs only (facebook / earth / chat / link / lock / check-circle).

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Badge from "@/components/Badge";
import { type SelectOption } from "@/types/select";
import {
    type ProviderDef,
    type ProviderDefInput,
    type Capability,
    type AuthScheme,
    type TransformType,
    listProviders,
    createProvider,
    storeCredential,
    IntegrationError,
    humanizeError,
} from "@/lib/integrations";
import {
    type AdsConnChannel,
    type AdsConnTest,
    type AdsProviderStatus,
    getAdsConnectionsStatus,
    testAdConnection,
} from "../_lib";
import type { ToastFn } from "../_shared";

// ---------------------------------------------------------------------------
// PRESET CATALOG — the EXACT blob fields each connector reads (connectors/*.py).
//   Meta     (connectors/meta.py)     : system_user_token, app_secret, ad_account_id, page_id,
//                                        dataset_id, webhook_verify_token   [bearer]
//   Google   (connectors/google.py)   : refresh_token, developer_token, client_id, client_secret,
//                                        login_customer_id, customer_id      [oauth2 refresh]
//   WhatsApp (connectors/whatsapp.py) : channel(360dialog|cloud), api_key (D360-API-KEY) OR
//                                        access_token (cloud Bearer), phone_number_id, waba_id, app_secret
// `required` gates the Save button; `secret` renders a password input. The values are JSON.stringified
// into ONE credential blob and stored encrypted — the connectors json.loads it back.
// ---------------------------------------------------------------------------
type PresetField = {
    key: string;
    label: string;
    placeholder?: string;
    required?: boolean;
    secret?: boolean;
    hint?: string;
};

type ConnectPreset = {
    channel: AdsConnChannel;
    named_provider: string;
    capability: Capability;
    display_name: string;
    slug: string;
    base_url: string;
    auth_scheme: AuthScheme;
    transform_type: TransformType;
    icon: string;
    blurb: string;
    docs?: string;
    fields: PresetField[];
    // whatsapp picks its backend (360dialog vs Meta Cloud) from a `channel` blob field.
    backend?: { key: string; label: string; options: { value: string; label: string }[] };
};

const PRESETS: ConnectPreset[] = [
    {
        channel: "meta",
        named_provider: "meta",
        capability: "ad_platform",
        display_name: "Meta Ads",
        slug: "meta-ads",
        base_url: "https://graph.facebook.com",
        auth_scheme: "bearer",
        transform_type: "named_provider",
        icon: "facebook",
        blurb: "Facebook & Instagram lead ads + Conversions API (CAPI).",
        docs: "Business Manager → System Users → generate a long-lived token with ads_management + leads_retrieval.",
        fields: [
            { key: "system_user_token", label: "System User token", required: true, secret: true, hint: "Long-lived token from Meta Business → System Users." },
            { key: "app_secret", label: "App secret", required: true, secret: true, hint: "Verifies webhook signatures." },
            { key: "ad_account_id", label: "Ad account ID", required: true, placeholder: "act_1234567890" },
            { key: "page_id", label: "Facebook Page ID", placeholder: "Optional — for lead forms" },
            { key: "dataset_id", label: "Dataset / Pixel ID", placeholder: "Optional — Conversions API" },
            { key: "webhook_verify_token", label: "Webhook verify token", secret: true, placeholder: "Optional — leadgen webhook" },
        ],
    },
    {
        channel: "google",
        named_provider: "google",
        capability: "ad_platform",
        display_name: "Google Ads",
        slug: "google-ads",
        base_url: "https://googleads.googleapis.com",
        auth_scheme: "oauth2_cc",
        transform_type: "named_provider",
        icon: "earth",
        blurb: "Search / Performance Max campaigns + offline conversion upload.",
        docs: "Google Ads API: a developer token + an OAuth client (id/secret) + a refresh token for the manager account.",
        fields: [
            { key: "refresh_token", label: "OAuth refresh token", required: true, secret: true },
            { key: "developer_token", label: "Developer token", required: true, secret: true },
            { key: "client_id", label: "OAuth client ID", required: true },
            { key: "client_secret", label: "OAuth client secret", required: true, secret: true },
            { key: "login_customer_id", label: "Login customer ID (MCC)", placeholder: "1234567890 (no dashes)" },
            { key: "customer_id", label: "Customer ID", placeholder: "Optional — the account to run in" },
        ],
    },
    {
        channel: "whatsapp",
        named_provider: "whatsapp",
        capability: "messaging",
        display_name: "WhatsApp",
        slug: "whatsapp",
        base_url: "https://waba.360dialog.io",
        auth_scheme: "api_key_header",
        transform_type: "named_provider",
        icon: "chat",
        blurb: "Template messages + Click-to-WhatsApp lead capture.",
        docs: "360dialog: paste the D360 API key. Meta Cloud API: paste the access token + phone number ID.",
        backend: {
            key: "channel",
            label: "Backend",
            options: [
                { value: "360dialog", label: "360dialog (D360 API key)" },
                { value: "cloud", label: "Meta Cloud API (access token)" },
            ],
        },
        fields: [
            { key: "api_key", label: "360dialog API key", secret: true, hint: "D360-API-KEY (360dialog backend)." },
            { key: "access_token", label: "Cloud API access token", secret: true, hint: "Bearer token (Meta Cloud backend)." },
            { key: "phone_number_id", label: "Phone number ID", required: true },
            { key: "waba_id", label: "WABA ID", placeholder: "Optional" },
            { key: "app_secret", label: "App secret", secret: true, placeholder: "Optional — webhook signature" },
        ],
    },
];

// channel -> status badge tone + label.
function statusBadge(s: AdsProviderStatus | undefined): { variant: "success" | "neutral" | "danger"; label: string } {
    if (s === "configured") return { variant: "success", label: "Connected" };
    if (s === "error") return { variant: "danger", label: "Error" };
    return { variant: "neutral", label: "Not connected" };
}

// human-readable reason for a test result.
function testReason(r: AdsConnTest): string {
    if (r.ok) return "Connected — all required keys present.";
    const map: Record<string, string> = {
        registry_disabled: "The secrets vault isn't available on this box yet.",
        not_configured: "No provider saved for this channel yet — add your keys.",
        no_credential: "A provider exists but no key blob is stored — paste your keys.",
        bad_channel: "Unsupported channel.",
        missing_fields: `Missing required keys: ${(r.missing || []).join(", ") || "—"}.`,
        error: "Couldn't read the key — try saving it again.",
    };
    return map[r.reason] || r.reason || "Not connected.";
}

export default function AdConnectPresets({ toast, refresh }: { toast: ToastFn; refresh: () => void }) {
    const [status, setStatus] = useState<Record<string, AdsProviderStatus>>({});
    const [dormant, setDormant] = useState(false);
    const [tests, setTests] = useState<Record<string, AdsConnTest>>({});
    const [openChannel, setOpenChannel] = useState<AdsConnChannel | null>(null);

    const loadStatus = useCallback(async () => {
        const res = await getAdsConnectionsStatus();
        if (res.kind === "ok") {
            setStatus(res.data.providers || {});
            setDormant(false);
        } else if (res.kind === "dormant") {
            setDormant(true);
        }
    }, []);

    useEffect(() => {
        loadStatus();
    }, [loadStatus]);

    const runTest = useCallback(
        async (channel: AdsConnChannel, quiet = false) => {
            try {
                const r = await testAdConnection(channel);
                setTests((t) => ({ ...t, [channel]: r }));
                if (!quiet) toast(r.ok ? `${channel} connection verified.` : testReason(r), r.ok ? "success" : "error");
                return r;
            } catch (e) {
                if (!quiet) toast((e as Error)?.message || "Test failed", "error");
                return null;
            }
        },
        [toast],
    );

    const preset = useMemo(() => PRESETS.find((p) => p.channel === openChannel) || null, [openChannel]);

    return (
        <div className="card p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3 mb-1">
                <div className="text-h6 text-t-primary">Connect an ad platform</div>
                <Badge variant="neutral">Paste keys → Connected</Badge>
            </div>
            <p className="text-body-2 text-t-secondary mb-5 max-w-2xl">
                Add ONE set of keys per platform — the engine resolves them automatically and the badge flips to
                <span className="text-t-primary"> Connected</span> the moment they verify. Keys are stored encrypted and
                never shown again.
            </p>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {PRESETS.map((p) => {
                    const sb = statusBadge(status[p.channel]);
                    const t = tests[p.channel];
                    const connected = status[p.channel] === "configured";
                    return (
                        <div
                            key={p.channel}
                            className="lift flex flex-col gap-3 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30"
                        >
                            <div className="flex items-center gap-3">
                                <span className="grid place-items-center size-10 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                                    <Icon name={p.icon} className="size-5 fill-inherit" />
                                </span>
                                <div className="min-w-0 flex-1">
                                    <div className="text-sub-title-2 text-t-primary truncate">{p.display_name}</div>
                                    <Badge variant={sb.variant}>{sb.label}</Badge>
                                </div>
                            </div>
                            <div className="text-caption text-t-secondary">{p.blurb}</div>
                            {t && !t.ok && (
                                <div className="flex items-start gap-1.5 text-caption text-t-tertiary">
                                    <Icon name="info" className="size-3.5 fill-t-tertiary shrink-0 mt-0.5" />
                                    {testReason(t)}
                                </div>
                            )}
                            {t && t.ok && (
                                <div className="flex items-center gap-1.5 text-caption text-primary-02">
                                    <Icon name="check-circle" className="size-3.5 fill-primary-02 shrink-0" />
                                    Verified — ready to launch.
                                </div>
                            )}
                            <div className="mt-auto flex items-center gap-2 pt-1">
                                <Button isBlack onClick={() => setOpenChannel(p.channel)}>
                                    {connected ? "Update keys" : "Connect"}
                                </Button>
                                <button
                                    type="button"
                                    onClick={() => runTest(p.channel)}
                                    className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-button text-t-secondary border border-s-subtle hover:border-s-highlight transition-colors"
                                >
                                    <Icon name="link" className="size-3.5 fill-t-secondary" />
                                    Test
                                </button>
                            </div>
                        </div>
                    );
                })}
            </div>

            {dormant && (
                <div className="mt-4 flex items-center gap-2 text-caption text-t-tertiary">
                    <Icon name="lock" className="size-3.5 fill-t-tertiary shrink-0" />
                    The ads engine isn't mounted on this workspace yet — keys can be added once it's enabled.
                </div>
            )}

            {preset && (
                <ConnectModal
                    preset={preset}
                    open={!!openChannel}
                    onClose={() => setOpenChannel(null)}
                    onSaved={async (channel) => {
                        setOpenChannel(null);
                        await loadStatus();
                        await runTest(channel, true);
                        refresh();
                    }}
                    toast={toast}
                />
            )}
        </div>
    );
}

// ---------------------------------------------------------------------------
// The guided key form. Find-or-create the named_provider def, then write ONE
// JSON credential blob (the connector json.loads it back). Idempotent: re-saving
// reuses the existing def for the channel (no duplicate providers).
// ---------------------------------------------------------------------------
function ConnectModal({
    preset,
    open,
    onClose,
    onSaved,
    toast,
}: {
    preset: ConnectPreset;
    open: boolean;
    onClose: () => void;
    onSaved: (channel: AdsConnChannel) => Promise<void> | void;
    toast: ToastFn;
}) {
    const [vals, setVals] = useState<Record<string, string>>({});
    const [backend, setBackend] = useState<SelectOption>(
        preset.backend ? { id: 0, name: preset.backend.options[0].label } : { id: 0, name: "" },
    );
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        if (!open) return;
        setVals({});
        setBackend(preset.backend ? { id: 0, name: preset.backend.options[0].label } : { id: 0, name: "" });
        setError("");
    }, [open, preset]);

    const backendValue = preset.backend ? preset.backend.options[backend.id as number]?.value : "";

    // WhatsApp: require phone_number_id + (api_key for 360dialog | access_token for cloud);
    // others: every `required` field non-empty.
    const canSave = useMemo(() => {
        const baseReq = preset.fields.filter((f) => f.required).every((f) => (vals[f.key] || "").trim());
        if (preset.channel === "whatsapp") {
            const auth = backendValue === "cloud" ? (vals.access_token || "").trim() : (vals.api_key || "").trim();
            return baseReq && !!auth;
        }
        return baseReq;
    }, [preset, vals, backendValue]);

    const submit = async () => {
        if (!canSave) {
            setError("Fill the required keys first.");
            return;
        }
        setBusy(true);
        setError("");
        try {
            // 1) find-or-create the def for this named_provider (idempotent).
            let def: ProviderDef | undefined;
            const list = await listProviders(preset.capability);
            def = list.providers.find((p) => (p.named_provider || "") === preset.named_provider);
            if (!def) {
                const input: ProviderDefInput = {
                    slug: preset.slug,
                    display_name: preset.display_name,
                    provider_type: "hosted_api",
                    capabilities: [preset.capability],
                    base_url: preset.base_url,
                    auth_scheme: preset.auth_scheme,
                    transform_type: preset.transform_type,
                    named_provider: preset.named_provider,
                };
                def = await createProvider(input);
            }
            if (!def || !def.id) throw new Error("Could not create the provider.");

            // 2) assemble the credential BLOB — exactly the fields the connector reads.
            const blob: Record<string, string> = {};
            for (const f of preset.fields) {
                const v = (vals[f.key] || "").trim();
                if (v) blob[f.key] = v;
            }
            if (preset.backend && backendValue) blob[preset.backend.key] = backendValue;

            // 3) store the blob as ONE encrypted credential (connectors json.loads it).
            await storeCredential(def.id, JSON.stringify(blob));

            toast(`${preset.display_name} keys saved.`, "success");
            await onSaved(preset.channel);
        } catch (e) {
            setError(e instanceof IntegrationError ? e.message : humanizeError(String((e as Error)?.message || ""), 0));
        } finally {
            setBusy(false);
        }
    };

    return (
        <Modal classWrapper="max-w-lg" open={open} onClose={() => !busy && onClose()} isSlidePanel>
            <div className="flex items-center gap-2.5 mb-1">
                <span className="grid place-items-center size-9 rounded-xl bg-b-surface2 ring-1 ring-s-subtle fill-primary-01">
                    <Icon name={preset.icon} className="size-5 fill-inherit" />
                </span>
                <div className="text-h6 text-t-primary">Connect {preset.display_name}</div>
            </div>
            <p className="text-body-2 text-t-secondary mb-5">{preset.docs || preset.blurb}</p>

            <div className="flex flex-col gap-4">
                {preset.backend && (
                    <Select
                        label={preset.backend.label}
                        value={backend}
                        onChange={setBackend}
                        options={preset.backend.options.map((o, i) => ({ id: i, name: o.label }))}
                    />
                )}
                {preset.fields.map((f) => {
                    // hide the auth field that doesn't apply to the chosen WhatsApp backend.
                    if (preset.channel === "whatsapp") {
                        if (f.key === "api_key" && backendValue === "cloud") return null;
                        if (f.key === "access_token" && backendValue !== "cloud") return null;
                    }
                    return (
                        <div key={f.key}>
                            <Field
                                label={`${f.label}${f.required ? "" : " (optional)"}`}
                                tooltip={f.hint}
                                type={f.secret ? "password" : "text"}
                                autoComplete="off"
                                placeholder={f.placeholder || (f.secret ? "Paste — stored encrypted" : "")}
                                value={vals[f.key] || ""}
                                onChange={(e) => setVals((s) => ({ ...s, [f.key]: e.target.value }))}
                            />
                            {f.hint && <div className="mt-1.5 text-caption text-t-tertiary">{f.hint}</div>}
                        </div>
                    );
                })}
            </div>

            {error && (
                <div className="mt-4 flex items-start gap-2 text-body-2 text-primary-03">
                    <Icon name="info" className="size-4 fill-primary-03 shrink-0 mt-0.5" />
                    {error}
                </div>
            )}

            <div className="mt-6 flex items-center justify-between gap-3">
                <div className="flex items-center gap-1.5 text-caption text-t-tertiary">
                    <Icon name="lock" className="size-3.5 fill-t-tertiary shrink-0" />
                    Encrypted at rest · never shown again
                </div>
                <div className="flex items-center gap-3">
                    <button
                        type="button"
                        className="h-10 px-4 rounded-full text-button text-t-secondary border border-s-subtle hover:border-s-highlight transition-colors"
                        onClick={() => !busy && onClose()}
                        disabled={busy}
                    >
                        Cancel
                    </button>
                    <Button isBlack onClick={submit} disabled={busy || !canSave}>
                        {busy ? "Saving…" : "Save & connect"}
                    </Button>
                </div>
            </div>
        </Modal>
    );
}
