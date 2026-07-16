"use client";

// Ad-Engine · OAUTH CONNECT + CLAIM + FUND (BLINDSPOTS B4 / B16 / B17 / B13-B15).
//
// The one-click half of "add ONE key and it runs": instead of hand-minting a System-User / refresh
// token, the vendor clicks "Connect with Meta / Google" → the engine redirects them through the
// provider's OAuth consent → the callback lands the token straight into their vault. Then they CLAIM
// their Facebook Page / dataset / WhatsApp number (ownership-proven into page_tenant_map, so inbound
// webhooks stop 403-ing), SUBSCRIBE the leadgen webhook in one tap, and confirm the ad account is
// FUNDED (vendor-own-card) before any launch.
//
// EARNER-SAFE: every real provider call is flag-gated on the backend (ADS_OAUTH_LIVE / ADS_CONNECT_LIVE);
// while dry-run, Connect shows a clear "sandbox / founder must finish app setup" state and nothing is
// fabricated. Core_2 kit, zero raw hex, registered glyphs only.

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";
import Field from "@/components/Field";
import Select from "@/components/Select";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import { type SelectOption } from "@/types/select";
import {
    type ConnectProvider,
    type ConnectProviderStatus,
    type ClaimKind,
    type ClaimRow,
    type FundingStatus,
    getConnectProviders,
    startConnect,
    claimAsset,
    listClaims,
    subscribeLeadgen,
    getFundingStatus,
    getFundingManageLink,
} from "./_connect-lib";
import type { ToastFn } from "../_shared";

const PROVIDER_META: Record<ConnectProvider, { label: string; icon: string; blurb: string }> = {
    meta: {
        label: "Meta (Facebook / Instagram)",
        icon: "facebook",
        blurb: "Login for Business → ad account, Pages, leadgen + CAPI, all in one consent.",
    },
    google: {
        label: "Google Ads",
        icon: "earth",
        blurb: "OAuth → a refresh token for the Ads API + Data Manager, no console token-minting.",
    },
};

// The shared <Select> contract is SelectOption.id: number, but the backend claim
// route keys on a string ClaimKind ("page"|"dataset"|"wa-phone"). So the widget
// carries stable numeric ids and we map each back to its ClaimKind at call time.
const CLAIM_KINDS: SelectOption[] = [
    { id: 0, name: "Facebook Page" },
    { id: 1, name: "Dataset / Pixel" },
    { id: 2, name: "WhatsApp number" },
];
const CLAIM_KIND_BY_ID: Record<number, ClaimKind> = {
    0: "page",
    1: "dataset",
    2: "wa-phone",
};

export default function OAuthConnectPanel({ toast, refresh }: { toast: ToastFn; refresh?: () => void }) {
    const [providers, setProviders] = useState<ConnectProviderStatus[] | null>(null);
    const [funding, setFunding] = useState<FundingStatus | null>(null);
    const [claims, setClaims] = useState<ClaimRow[]>([]);
    const [busy, setBusy] = useState<string>("");

    const [claimKind, setClaimKind] = useState<SelectOption>(CLAIM_KINDS[0]);
    const [claimId, setClaimId] = useState("");

    const load = useCallback(async () => {
        const [p, f, c] = await Promise.all([
            getConnectProviders(),
            getFundingStatus(),
            listClaims(),
        ]);
        if (p?.ok) setProviders(p.providers);
        if (f) setFunding(f);
        if (c?.ok) setClaims(c.claims || []);
    }, []);

    useEffect(() => {
        void load();
    }, [load]);

    const onConnect = useCallback(
        async (provider: ConnectProvider) => {
            setBusy(`connect:${provider}`);
            const res = await startConnect(provider);
            setBusy("");
            if (!res) return toast("Couldn't start the connect flow — try again.", "error");
            if (res.ok && res.authorize_url) {
                // Hand the browser to the provider's consent screen; the callback redirects back here.
                window.location.href = res.authorize_url;
                return;
            }
            if (res.reason === "app_not_configured") {
                return toast(
                    "Connect isn't live yet — the platform app (App ID + redirect URI) must be registered first.",
                    "error",
                );
            }
            toast(`Connect unavailable (${res.reason || "error"}).`, "error");
        },
        [toast],
    );

    const onClaim = useCallback(async () => {
        const id = claimId.trim();
        if (!id) return toast("Enter the Page / dataset / WhatsApp id to claim.", "error");
        setBusy("claim");
        const res = await claimAsset(CLAIM_KIND_BY_ID[claimKind.id], id);
        setBusy("");
        if (!res) return toast("Claim failed — try again.", "error");
        if (res.ok) {
            toast(`Claimed ${claimKind.name} ${id}.`, "success");
            setClaimId("");
            void load();
            refresh?.();
            return;
        }
        const human: Record<string, string> = {
            already_claimed_by_other_tenant: "That id is already linked to another workspace.",
            not_owned: "That Page isn't in your Meta account — connect Meta first.",
            meta_not_configured: "Connect Meta before claiming a Page.",
            invalid_id: "That id format isn't valid.",
        };
        toast(human[res.reason || ""] || `Claim blocked (${res.reason || "error"}).`, "error");
    }, [claimId, claimKind, toast, load, refresh]);

    const onSubscribe = useCallback(
        async (pageId: string) => {
            setBusy(`sub:${pageId}`);
            const res = await subscribeLeadgen(pageId);
            setBusy("");
            if (!res) return toast("Subscribe failed — try again.", "error");
            if (res.ok && res.simulated) {
                return toast("Leadgen webhook queued (sandbox) — goes live when the engine is armed.", "success");
            }
            if (res.ok) return toast(`Leadgen webhook subscribed for ${pageId}.`, "success");
            toast(`Subscribe blocked (${res.status || res.reason || "error"}).`, "error");
        },
        [toast],
    );

    const onManageFunding = useCallback(async () => {
        const r = await getFundingManageLink();
        if (r?.ok && r.url) {
            window.open(r.url, "_blank", "noopener,noreferrer");
            return;
        }
        toast("Add your ad account first, then manage payment there.", "error");
    }, [toast]);

    const fundingBadge = useMemo(() => {
        if (!funding) return { variant: "neutral" as const, label: "Funding…" };
        if (funding.funded === true) return { variant: "success" as const, label: "Funded" };
        if (funding.funded === false) return { variant: "danger" as const, label: "Not funded" };
        return { variant: "warning" as const, label: "Connect a card" };
    }, [funding]);

    return (
        <div className="card p-5 sm:p-6 flex flex-col gap-6">
            {/* ---- OAuth connect ---- */}
            <div>
                <div className="flex items-start justify-between gap-3 mb-1">
                    <div className="text-h6 text-t-primary">One-click connect</div>
                    <Badge variant="neutral">OAuth → vault</Badge>
                </div>
                <p className="text-body-2 text-t-secondary mb-4 max-w-2xl">
                    Sign in with Meta or Google and the token lands in your encrypted vault automatically — no
                    console token-minting, no pasting.
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                    {(providers || []).map((p) => {
                        const meta = PROVIDER_META[p.provider];
                        return (
                            <div
                                key={p.provider}
                                className="lift flex flex-col gap-3 p-4 rounded-2xl bg-b-surface2 ring-1 ring-s-subtle ring-inset dark:bg-shade-04/30"
                            >
                                <div className="flex items-center gap-3">
                                    <span className="grid place-items-center size-10 shrink-0 rounded-xl bg-b-surface1 ring-1 ring-s-subtle fill-primary-01 dark:bg-shade-04">
                                        <Icon name={meta.icon} className="size-5 fill-inherit" />
                                    </span>
                                    <div className="min-w-0 flex-1">
                                        <div className="text-sub-title-2 text-t-primary truncate">{meta.label}</div>
                                        <Badge variant={p.connected ? "success" : "neutral"}>
                                            {p.connected ? "Connected" : "Not connected"}
                                        </Badge>
                                    </div>
                                </div>
                                <div className="text-caption text-t-secondary">{meta.blurb}</div>
                                {!p.app_configured && (
                                    <div className="flex items-start gap-1.5 text-caption text-t-tertiary">
                                        <Icon name="info" className="size-3.5 fill-t-tertiary shrink-0 mt-0.5" />
                                        Platform app setup pending — Connect arms once the founder registers it.
                                    </div>
                                )}
                                {!p.live && p.app_configured && (
                                    <div className="flex items-start gap-1.5 text-caption text-t-tertiary">
                                        <Icon name="info" className="size-3.5 fill-t-tertiary shrink-0 mt-0.5" />
                                        Sandbox mode — live token exchange is gated until go-live.
                                    </div>
                                )}
                                <div className="mt-auto pt-1">
                                    <Button
                                        isBlack
                                        disabled={busy === `connect:${p.provider}` || !p.app_configured}
                                        onClick={() => onConnect(p.provider)}
                                    >
                                        {p.connected ? "Reconnect" : `Connect with ${p.provider === "meta" ? "Meta" : "Google"}`}
                                    </Button>
                                </div>
                            </div>
                        );
                    })}
                    {providers && providers.length === 0 && (
                        <div className="text-caption text-t-tertiary">No connectable platforms on this workspace yet.</div>
                    )}
                </div>
            </div>

            {/* ---- Claim a Page / dataset / WhatsApp ---- */}
            <div className="border-t border-s-subtle pt-5">
                <div className="text-sub-title-1 text-t-primary mb-1">Claim your lead sources</div>
                <p className="text-body-2 text-t-secondary mb-3 max-w-2xl">
                    Link your Facebook Page, dataset/pixel or WhatsApp number so inbound leads route to you. Ownership is
                    proven against your connected Meta account.
                </p>
                <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                    <div className="sm:w-52">
                        <Select label="Type" value={claimKind} onChange={setClaimKind} options={CLAIM_KINDS} />
                    </div>
                    <div className="flex-1">
                        <Field
                            label="Page / dataset / WhatsApp id"
                            placeholder="e.g. 1029384756"
                            value={claimId}
                            onChange={(e) => setClaimId(e.target.value)}
                        />
                    </div>
                    <Button isBlack disabled={busy === "claim"} onClick={onClaim}>
                        Claim
                    </Button>
                </div>

                {claims.length > 0 && (
                    <div className="mt-4 flex flex-col gap-2">
                        {claims.map((c) => (
                            <div
                                key={c.id}
                                className="flex items-center justify-between gap-3 p-3 rounded-xl bg-b-surface2 ring-1 ring-s-subtle ring-inset"
                            >
                                <div className="flex items-center gap-2 min-w-0">
                                    <Icon name="link" className="size-3.5 fill-t-secondary shrink-0" />
                                    <span className="text-caption text-t-primary truncate">{c.id}</span>
                                    {c.kind && <Badge variant="neutral">{c.kind}</Badge>}
                                </div>
                                <button
                                    type="button"
                                    disabled={busy === `sub:${c.id}`}
                                    onClick={() => onSubscribe(c.id)}
                                    className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-button text-t-secondary border border-s-subtle hover:border-s-highlight transition-colors disabled:opacity-50"
                                >
                                    <Icon name="chat" className="size-3.5 fill-t-secondary" />
                                    Subscribe leadgen
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* ---- Funding (vendor-own-card) ---- */}
            <div className="border-t border-s-subtle pt-5">
                <div className="flex items-center justify-between gap-3 mb-1">
                    <div className="text-sub-title-1 text-t-primary">Ad budget funding</div>
                    <Badge variant={fundingBadge.variant}>{fundingBadge.label}</Badge>
                </div>
                <p className="text-body-2 text-t-secondary mb-3 max-w-2xl">
                    {funding?.model === "managed"
                        ? "Managed budget — top up here and the engine draws spend from your balance."
                        : "Your card on your own ad account — we never front spend. A launch is blocked until the account is funded."}
                </p>
                <div className="flex items-center gap-2">
                    <Button isBlack onClick={onManageFunding}>
                        {funding?.funded === true ? "Manage payment" : "Add payment method"}
                    </Button>
                    {funding?.funded === false && (
                        <span className="inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                            <Icon name="info" className="size-3.5 fill-t-tertiary shrink-0" />
                            Launch is blocked (insufficient funds) until a card is attached.
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}
