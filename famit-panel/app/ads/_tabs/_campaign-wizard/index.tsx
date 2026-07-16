"use client";

// ============================================================================
// Run-a-Campaign wizard — the guided, 4-step flow that drafts a paid campaign,
// connects budget, attaches a moderated creative, and launches it (dry-run) with
// a PIN step-up. Hosted in a centred Modal off the Campaigns tab.
//
// Reuses the proven Run-page spine: the same <Stepper> (app/run/_stepper.tsx) +
// the `.step-reveal` panel rhythm + Core_2 cards/buttons/badges. Every spend path
// stays dry-run server-side; the launch fail-closes without an X-Step-Up token,
// which we obtain via the shared <StepUpModal>.
//
//   ① Goal & Audience   → POST /ads/campaigns/propose            (→ plan_id)
//   ② Platforms & Budget→ providers + balance + fund + precheck
//   ③ Creative          → generate / adopt asset → poll variants → pick approved
//   ④ Review & Launch   → step-up PIN → POST /campaigns/{id}/approve (X-Step-Up)
//
// Auto-Pilot toggle (top): collapses to goal+budget+confirm and hands the brief
// to POST /ads/autorun/enable {autopilot_launch:true} — the engine sequences the
// rest itself, behind the SAME gates (no new spend authority).
//
// Token-pure (zero raw hex — only globals.css tokens).
// ============================================================================

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Modal from "@/components/Modal";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Stepper, { type Step } from "@/app/run/_stepper";
import StepUpModal from "../_step-up";
import {
    proposeCampaign,
    submitCreative,
    uploadCreative,
    getCreativeVariants,
    approveCampaign,
    getBudgetBalance,
    fundBudget,
    enableAutorun,
    fmtMoney,
    ADS_OBJECTIVES,
    ADS_PLATFORMS,
    type AdsObjective,
    type AdsPlatform,
    type AdsBrief,
    type AdsHealth,
    type BudgetBalance,
    type CreativeVariant,
} from "../../_lib";
import {
    getConnectProviders,
    getFundingPrecheck,
    type ConnectProviderStatus,
} from "../_connect-lib";
import { listAssets, type Asset } from "@/lib/assets";
import type { ToastFn } from "../../_shared";

const STEPS: Step[] = [
    { label: "Goal & Audience", hint: "What you're selling" },
    { label: "Platforms & Budget", hint: "Where & how much" },
    { label: "Creative", hint: "The ad itself" },
    { label: "Review & Launch", hint: "Confirm & go" },
];

const inputCls =
    "input-base w-full h-11 px-4 rounded-2xl text-body-2 bg-b-surface2 border border-s-subtle text-t-primary focus:outline-none focus:border-s-highlight transition-colors";

export type CampaignWizardProps = {
    open: boolean;
    onClose: () => void;
    writable: boolean;
    currency: string;
    hc: AdsHealth | null;
    onLaunched: () => void;
    toast: ToastFn;
};

export default function CampaignWizard(props: CampaignWizardProps) {
    // Remount the inner flow each time the modal opens so state always starts
    // clean (no stale plan_id / variant from a prior run).
    return (
        <Modal open={props.open} onClose={props.onClose} classWrapper="!max-w-3xl !p-0">
            {props.open && <WizardBody {...props} />}
        </Modal>
    );
}

function WizardBody({ onClose, writable, currency, hc, onLaunched, toast }: CampaignWizardProps) {
    const [autopilot, setAutopilot] = useState(false);
    const [step, setStep] = useState(0);

    // ── Step 1: goal & audience ──
    const [name, setName] = useState("");
    const [objective, setObjective] = useState<AdsObjective>("leads");
    const [geo, setGeo] = useState("");
    const [audience, setAudience] = useState("");
    const [variants, setVariants] = useState(3);
    const [planId, setPlanId] = useState("");
    const [proposing, setProposing] = useState(false);

    // ── Step 2: platforms & budget ──
    const [providers, setProviders] = useState<ConnectProviderStatus[] | null>(null);
    const [platforms, setPlatforms] = useState<Set<AdsPlatform>>(new Set());
    const [budget, setBudget] = useState(""); // major units
    const [balance, setBalance] = useState<BudgetBalance | null>(null);
    const [funding, setFunding] = useState(false);
    const [precheckBlocked, setPrecheckBlocked] = useState(false);

    // ── Step 3: creative ──
    const [creativeMode, setCreativeMode] = useState<"generate" | "upload">("generate");
    const [generating, setGenerating] = useState(false);
    const [vlist, setVlist] = useState<CreativeVariant[]>([]);
    const [pickedVariant, setPickedVariant] = useState<string>("");
    const [assets, setAssets] = useState<Asset[]>([]);
    const [adoptingId, setAdoptingId] = useState("");
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // ── Step 4: launch ──
    const [stepUpOpen, setStepUpOpen] = useState(false);
    const [launching, setLaunching] = useState(false);
    const [launched, setLaunched] = useState<{ ref?: string; status: string } | null>(null);

    const budgetMinor = useMemo(() => {
        const n = parseFloat(budget);
        return Number.isFinite(n) && n > 0 ? Math.round(n * 100) : 0;
    }, [budget]);

    // ── connected map (meta/google from /connect/providers; whatsapp from health) ──
    const connected = useMemo(() => {
        const map: Record<AdsPlatform, boolean> = { meta: false, google: false, whatsapp: false };
        for (const p of providers || []) {
            if (p.provider === "meta") map.meta = p.connected;
            if (p.provider === "google") map.google = p.connected;
        }
        map.whatsapp = hc?.providers.whatsapp === "configured";
        return map;
    }, [providers, hc]);
    const providersResolved = providers !== null;
    const anyConnected = connected.meta || connected.google || connected.whatsapp;

    // Load tenant-level reads (providers + balance) once the flow is on screen.
    useEffect(() => {
        getConnectProviders().then((r) => setProviders(r?.providers ?? []));
        getBudgetBalance().then((r) => setBalance(r.kind === "ok" ? r.data : null));
    }, []);

    // Pre-select connected platforms the first time they resolve.
    useEffect(() => {
        if (!providersResolved) return;
        setPlatforms((prev) => {
            if (prev.size > 0) return prev;
            const next = new Set<AdsPlatform>();
            (Object.keys(connected) as AdsPlatform[]).forEach((p) => connected[p] && next.add(p));
            return next;
        });
    }, [providersResolved, connected]);

    // Funding precheck — warn when the chosen daily budget can't be covered.
    useEffect(() => {
        if (budgetMinor <= 0) {
            setPrecheckBlocked(false);
            return;
        }
        let cancelled = false;
        getFundingPrecheck(budgetMinor).then((r) => {
            if (cancelled) return;
            setPrecheckBlocked(!!r && (r.blocked || r.status === "blocked_insufficient_funds"));
        });
        return () => {
            cancelled = true;
        };
    }, [budgetMinor]);

    const balanceMinor = balance?.balance_minor ?? 0;
    const balanceLow = budgetMinor > 0 && balanceMinor < budgetMinor;

    // ── creative variants poll (step 3 only, while a job may still be moderating) ──
    const loadVariants = useCallback(() => {
        if (!planId) return;
        getCreativeVariants({ plan_id: planId }).then((r) => {
            if (r.kind === "ok") setVlist(r.data.variants || []);
        });
    }, [planId]);

    useEffect(() => {
        if (step !== 2 || !planId) return;
        loadVariants();
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(loadVariants, 2500);
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [step, planId, loadVariants]);

    // Load the media gallery for the "adopt an asset" path.
    useEffect(() => {
        if (step === 2 && creativeMode === "upload" && assets.length === 0) {
            listAssets({ limit: 12 }).then((p) => setAssets(p.assets || []));
        }
    }, [step, creativeMode, assets.length]);

    const buildBrief = useCallback((): AdsBrief => {
        const b: AdsBrief = { name: name.trim(), objective, variants };
        if (budgetMinor > 0) b.budget_daily_minor = budgetMinor;
        if (geo.trim()) b.geo = geo.split(",").map((s) => s.trim()).filter(Boolean);
        if (audience.trim()) b.audience = { description: audience.trim() };
        return b;
    }, [name, objective, variants, budgetMinor, geo, audience]);

    // ── step transitions ──
    const doPropose = useCallback(async () => {
        if (!name.trim() || proposing) return;
        setProposing(true);
        try {
            const res = await proposeCampaign(buildBrief());
            setPlanId(res.plan_id);
            setStep(1);
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't draft the campaign.", "error");
        } finally {
            setProposing(false);
        }
    }, [name, proposing, buildBrief, toast]);

    const doFund = useCallback(async () => {
        const need = Math.max(budgetMinor - balanceMinor, budgetMinor);
        if (need <= 0 || funding) return;
        setFunding(true);
        try {
            const intent = await fundBudget(need, { description: `Top-up for ${name.trim() || "campaign"}` });
            if (intent.status === "not_configured" || intent.needs_setup) {
                toast("Connect a payment method in Connections to add funds.", "error");
            } else {
                toast("Funding started — your balance updates once the payment clears.");
            }
            const r = await getBudgetBalance();
            setBalance(r.kind === "ok" ? r.data : balance);
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't start funding.", "error");
        } finally {
            setFunding(false);
        }
    }, [budgetMinor, balanceMinor, funding, name, balance, toast]);

    const doGenerate = useCallback(async () => {
        if (!planId || generating) return;
        setGenerating(true);
        try {
            await submitCreative({ plan_id: planId, brief: { ...buildBrief(), instruction: audience.trim() } });
            toast("Generating variants — they appear below as each clears moderation.");
            loadVariants();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't start generation.", "error");
        } finally {
            setGenerating(false);
        }
    }, [planId, generating, buildBrief, audience, loadVariants, toast]);

    const doAdopt = useCallback(
        async (asset: Asset) => {
            if (!planId || adoptingId) return;
            setAdoptingId(asset.id);
            try {
                await uploadCreative(planId, asset.id, { brief: buildBrief() });
                toast("Asset added — it runs the moderation gate before it can spend.");
                loadVariants();
            } catch (e) {
                toast(e instanceof Error ? e.message : "Couldn't add that asset.", "error");
            } finally {
                setAdoptingId("");
            }
        },
        [planId, adoptingId, buildBrief, loadVariants, toast],
    );

    // The step-up token arrives here; spend it immediately on the approve call.
    const doApprove = useCallback(
        async (token: string) => {
            if (!planId) return;
            setLaunching(true);
            try {
                const res = await approveCampaign(planId, token);
                if (res.status === "blocked_not_approved") {
                    toast("That PIN didn't satisfy the launch gate — try again.", "error");
                } else {
                    setLaunched({ ref: res.campaign_ref, status: res.status });
                    toast(
                        res.status === "active"
                            ? `${name.trim() || "Campaign"} is live.`
                            : `${name.trim() || "Campaign"} approved — held in dry-run until ad platforms go live.`,
                    );
                    onLaunched();
                }
            } catch (e) {
                toast(e instanceof Error ? e.message : "Launch failed.", "error");
            } finally {
                setLaunching(false);
            }
        },
        [planId, name, onLaunched, toast],
    );

    // ── Auto-Pilot path ──
    const [autopilotBusy, setAutopilotBusy] = useState(false);
    const doAutopilot = useCallback(async () => {
        if (!name.trim() || autopilotBusy) return;
        setAutopilotBusy(true);
        try {
            const res = await enableAutorun(buildBrief(), { autopilotLaunch: true });
            if (res.ok === false) {
                toast(res.error ? `Auto-Pilot: ${res.error}` : "Couldn't start Auto-Pilot.", "error");
            } else {
                toast("Auto-Pilot is on — it drafts, creates, moderates and launches on its own (dry-run).");
                onLaunched();
                onClose();
            }
        } catch (e) {
            toast(e instanceof Error ? e.message : "Couldn't start Auto-Pilot.", "error");
        } finally {
            setAutopilotBusy(false);
        }
    }, [name, autopilotBusy, buildBrief, onLaunched, onClose, toast]);

    const approvedVariants = vlist.filter(
        (v) => (v.moderation_status || "pending").toLowerCase() === "approved",
    );
    const step0Valid = !!name.trim();
    const maxReachable = !planId ? 0 : STEPS.length - 1;
    const goBack = () => setStep((s) => Math.max(0, s - 1));

    return (
        <div className="flex flex-col max-h-[88vh]">
            {/* ── header: title + Auto-Pilot toggle ── */}
            <div className="flex items-start justify-between gap-4 p-6 pb-4 border-b border-s-subtle">
                <div className="min-w-0">
                    <div className="eyebrow mb-1">New campaign</div>
                    <h1 className="text-h5 text-t-primary">Run a Campaign</h1>
                </div>
                <button
                    type="button"
                    onClick={() => setAutopilot((v) => !v)}
                    className={`flex items-center gap-2.5 h-10 px-3 rounded-full border text-button transition-colors shrink-0 ${
                        autopilot
                            ? "border-primary-01/40 bg-primary-01/8 text-t-primary"
                            : "border-s-subtle bg-b-surface2 text-t-secondary hover:border-s-stroke2"
                    }`}
                    aria-pressed={autopilot}
                >
                    <Icon name="promote" className={`size-4 ${autopilot ? "fill-primary-01" : "fill-t-tertiary"}`} />
                    Auto-Pilot
                    <span className={`relative w-9 h-5 rounded-full transition-colors ${autopilot ? "bg-primary-01" : "bg-s-stroke2"}`}>
                        <span
                            className={`absolute top-0.5 size-4 rounded-full bg-b-surface2 transition-transform ${
                                autopilot ? "translate-x-4" : "translate-x-0.5"
                            }`}
                        />
                    </span>
                </button>
            </div>

            <div className="overflow-y-auto px-6 py-5 scrollbar scrollbar-thumb-t-tertiary/40 scrollbar-track-transparent">
                {autopilot ? (
                    <AutopilotPanel
                        name={name}
                        setName={setName}
                        objective={objective}
                        setObjective={setObjective}
                        geo={geo}
                        setGeo={setGeo}
                        audience={audience}
                        setAudience={setAudience}
                        budget={budget}
                        setBudget={setBudget}
                        currency={currency}
                        busy={autopilotBusy}
                        writable={writable}
                        onLaunch={doAutopilot}
                    />
                ) : (
                    <>
                        <Stepper steps={STEPS} step={step} maxReachable={maxReachable} onStep={(i) => i <= maxReachable && setStep(i)} />

                        <div className="mt-5">
                            {step === 0 && (
                                <div key="w0" className="step-reveal space-y-4">
                                    <Labeled label="Campaign name / product">
                                        <input
                                            value={name}
                                            onChange={(e) => setName(e.target.value)}
                                            placeholder="Diwali offer — 2BHK Gurgaon"
                                            className={inputCls}
                                            autoFocus
                                        />
                                    </Labeled>
                                    <Labeled label="Objective">
                                        <select
                                            value={objective}
                                            onChange={(e) => setObjective(e.target.value as AdsObjective)}
                                            className={`${inputCls} appearance-none`}
                                        >
                                            {ADS_OBJECTIVES.map((o) => (
                                                <option key={o} value={o}>
                                                    {o.charAt(0).toUpperCase() + o.slice(1)}
                                                </option>
                                            ))}
                                        </select>
                                    </Labeled>
                                    <Labeled label="Locations" hint="Comma-separated cities or regions.">
                                        <input
                                            value={geo}
                                            onChange={(e) => setGeo(e.target.value)}
                                            placeholder="Gurgaon, Delhi NCR"
                                            className={inputCls}
                                        />
                                    </Labeled>
                                    <Labeled label="Audience">
                                        <input
                                            value={audience}
                                            onChange={(e) => setAudience(e.target.value)}
                                            placeholder="Home buyers, 28–45, ready to move"
                                            className={inputCls}
                                        />
                                    </Labeled>
                                </div>
                            )}

                            {step === 1 && (
                                <div key="w1" className="step-reveal space-y-5">
                                    <div>
                                        <div className="text-button text-t-primary mb-2.5">Platforms</div>
                                        {providersResolved && !anyConnected && (
                                            <div className="mb-3 flex items-start gap-2 p-3 rounded-2xl bg-primary-05/8 text-caption text-t-secondary">
                                                <Icon name="info" className="size-4 fill-primary-05 shrink-0 mt-px" />
                                                No ad accounts connected yet. Connect one under Connections to launch
                                                live — you can still draft and review everything here in dry-run.
                                            </div>
                                        )}
                                        <div className="grid grid-cols-3 gap-2.5 max-sm:grid-cols-1">
                                            {ADS_PLATFORMS.map((p) => {
                                                const on = platforms.has(p.id);
                                                const isConnected = connected[p.id];
                                                return (
                                                    <button
                                                        key={p.id}
                                                        type="button"
                                                        onClick={() =>
                                                            setPlatforms((prev) => {
                                                                const next = new Set(prev);
                                                                next.has(p.id) ? next.delete(p.id) : next.add(p.id);
                                                                return next;
                                                            })
                                                        }
                                                        className={`flex flex-col items-start gap-2 p-3.5 rounded-2xl border text-left transition-colors ${
                                                            on
                                                                ? "border-primary-01/40 bg-primary-01/8"
                                                                : "border-s-subtle bg-b-surface2 hover:border-s-stroke2"
                                                        }`}
                                                    >
                                                        <span className="flex items-center justify-between w-full">
                                                            <Icon name={p.icon} className={`size-5 ${on ? "fill-primary-01" : "fill-t-secondary"}`} />
                                                            {isConnected ? (
                                                                <Badge variant="success" dot>Connected</Badge>
                                                            ) : (
                                                                <Badge variant="neutral">Not connected</Badge>
                                                            )}
                                                        </span>
                                                        <span className="min-w-0">
                                                            <span className="block text-button text-t-primary">{p.label}</span>
                                                            <span className="block text-caption text-t-tertiary">{p.hint}</span>
                                                        </span>
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>

                                    <Labeled
                                        label={`Daily budget (${currency === "INR" ? "₹" : currency})`}
                                        hint="Clamped to your hard cap server-side. Nothing spends until you launch."
                                    >
                                        <input
                                            type="number"
                                            min="0"
                                            step="1"
                                            value={budget}
                                            onChange={(e) => setBudget(e.target.value)}
                                            placeholder="1500"
                                            className={inputCls}
                                        />
                                    </Labeled>

                                    {/* balance + fund */}
                                    <div className="flex items-center justify-between gap-3 p-3.5 rounded-2xl bg-b-surface2 border border-s-subtle">
                                        <div className="min-w-0">
                                            <div className="text-caption text-t-tertiary">Ad-budget balance</div>
                                            <div className="text-body-1 text-t-primary tabular-nums">
                                                {fmtMoney(balanceMinor, currency)}
                                            </div>
                                        </div>
                                        {(balanceLow || precheckBlocked) && (
                                            <Button isStroke className="!h-10 !px-4 shrink-0" icon="wallet" onClick={doFund} disabled={funding || !writable}>
                                                {funding ? "Starting…" : "Add funds"}
                                            </Button>
                                        )}
                                    </div>
                                    {precheckBlocked && (
                                        <div className="flex items-start gap-2 p-3 rounded-2xl bg-primary-03/8 text-caption text-primary-03">
                                            <Icon name="info" className="size-4 fill-primary-03 shrink-0 mt-px" />
                                            Your balance can't cover this daily budget. Add funds to launch live — or
                                            continue and keep it in dry-run.
                                        </div>
                                    )}
                                </div>
                            )}

                            {step === 2 && (
                                <div key="w2" className="step-reveal space-y-4">
                                    <div className="flex items-center gap-1 p-1 rounded-full bg-b-surface2 ring-1 ring-s-subtle ring-inset w-fit">
                                        {(["generate", "upload"] as const).map((m) => (
                                            <button
                                                key={m}
                                                type="button"
                                                onClick={() => setCreativeMode(m)}
                                                className={`h-9 px-4 rounded-full text-button transition-all ${
                                                    creativeMode === m
                                                        ? "bg-b-surface1 text-t-primary shadow-widget ring-1 ring-s-subtle dark:bg-shade-04"
                                                        : "text-t-secondary hover:text-t-primary"
                                                }`}
                                            >
                                                {m === "generate" ? "Generate" : "Use my asset"}
                                            </button>
                                        ))}
                                    </div>

                                    {creativeMode === "generate" ? (
                                        <div className="p-4 rounded-2xl bg-b-surface2 border border-s-subtle">
                                            <p className="text-body-2 text-t-secondary mb-3">
                                                The AI writes {variants} variant{variants === 1 ? "" : "s"} from your
                                                brief. Each runs the moderation gate (RERA, Housing, brand,
                                                broken-text) before it can spend.
                                            </p>
                                            <Button isBlack icon="magic-pencil" onClick={doGenerate} disabled={generating || !writable || !planId}>
                                                {generating ? "Generating…" : "Generate variants"}
                                            </Button>
                                        </div>
                                    ) : (
                                        <div>
                                            <p className="text-body-2 text-t-secondary mb-3">
                                                Pick one of your library assets — it becomes an ad variant and runs the
                                                same moderation gate.
                                            </p>
                                            {assets.length === 0 ? (
                                                <div className="p-6 text-center text-caption text-t-tertiary rounded-2xl bg-b-surface2 border border-s-subtle">
                                                    No library assets yet. Generate one on the left, or add media in
                                                    Creative.
                                                </div>
                                            ) : (
                                                <div className="grid grid-cols-4 gap-2.5 max-sm:grid-cols-3">
                                                    {assets.map((a) => (
                                                        <button
                                                            key={a.id}
                                                            type="button"
                                                            onClick={() => doAdopt(a)}
                                                            disabled={!!adoptingId || !writable}
                                                            className="group relative aspect-square rounded-xl overflow-hidden bg-b-surface1 border border-s-subtle bg-cover bg-center transition-all hover:border-s-highlight disabled:opacity-50 dark:bg-shade-04/40"
                                                            style={a.thumb_url || a.url ? { backgroundImage: `url(${a.thumb_url || a.url})` } : undefined}
                                                            title={a.headline || a.kind || "asset"}
                                                        >
                                                            {adoptingId === a.id && (
                                                                <span className="absolute inset-0 grid place-items-center bg-shade-04/60 text-caption text-t-light">
                                                                    Adding…
                                                                </span>
                                                            )}
                                                        </button>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* variant picker (poll) */}
                                    <div>
                                        <div className="flex items-center justify-between mb-2.5">
                                            <div className="text-button text-t-primary">Pick a variant to run</div>
                                            {vlist.length > 0 && (
                                                <span className="text-caption text-t-tertiary">
                                                    {approvedVariants.length} approved · {vlist.length} total
                                                </span>
                                            )}
                                        </div>
                                        {vlist.length === 0 ? (
                                            <div className="p-5 text-center text-caption text-t-tertiary rounded-2xl bg-b-surface2 border border-s-subtle">
                                                No variants yet — generate or add one above, then it appears here once
                                                it clears moderation.
                                            </div>
                                        ) : (
                                            <div className="space-y-2">
                                                {vlist.map((v) => {
                                                    const status = (v.moderation_status || "pending").toLowerCase();
                                                    const approved = status === "approved";
                                                    const picked = pickedVariant === v.variant_id;
                                                    return (
                                                        <button
                                                            key={v.variant_id}
                                                            type="button"
                                                            disabled={!approved}
                                                            onClick={() => setPickedVariant(v.variant_id)}
                                                            className={`flex items-center gap-3 w-full p-3 rounded-2xl border text-left transition-colors ${
                                                                picked
                                                                    ? "border-primary-01/50 bg-primary-01/8"
                                                                    : approved
                                                                    ? "border-s-subtle bg-b-surface2 hover:border-s-stroke2"
                                                                    : "border-s-subtle bg-b-surface2 opacity-70 cursor-not-allowed"
                                                            }`}
                                                        >
                                                            <span
                                                                className="size-11 shrink-0 rounded-xl bg-cover bg-center bg-b-surface1 dark:bg-shade-04/40"
                                                                style={v.url ? { backgroundImage: `url(${v.url})` } : undefined}
                                                            />
                                                            <span className="min-w-0 flex-1">
                                                                <span className="block text-body-2 text-t-primary line-clamp-1">
                                                                    {v.headline || "Untitled variant"}
                                                                </span>
                                                                <span className="mt-1 inline-flex">
                                                                    <Badge variant={approved ? "success" : status.startsWith("blocked") ? "danger" : "info"} dot>
                                                                        {approved ? "Approved" : status.startsWith("blocked") ? "Blocked" : "In review"}
                                                                    </Badge>
                                                                </span>
                                                            </span>
                                                            {picked && <Icon name="check-circle-fill" className="size-6 fill-primary-02 shrink-0" />}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}

                            {step === 3 && (
                                <div key="w3" className="step-reveal space-y-4">
                                    {launched ? (
                                        <div className="p-5 rounded-2xl bg-primary-02/8 text-center">
                                            <span className="grid place-items-center size-12 mx-auto rounded-2xl bg-b-surface1 fill-primary-02 dark:bg-shade-04">
                                                <Icon name="check-circle-fill" className="size-7 fill-inherit" />
                                            </span>
                                            <div className="mt-3 text-h6 text-t-primary">
                                                {launched.status === "active" ? "Campaign launched" : "Approved — dry-run"}
                                            </div>
                                            <p className="mt-1 text-body-2 text-t-secondary">
                                                {launched.status === "active"
                                                    ? "It's live and spending against its hard cap."
                                                    : "Approved and parked in dry-run — it goes live the moment your ad platforms are connected. Nothing spends until then."}
                                            </p>
                                            {launched.ref && (
                                                <div className="mt-2 text-caption text-t-tertiary tabular-nums">
                                                    Ref {launched.ref}
                                                </div>
                                            )}
                                        </div>
                                    ) : (
                                        <>
                                            <div className="grid grid-cols-2 gap-px rounded-2xl overflow-hidden border border-s-subtle bg-s-subtle max-sm:grid-cols-1">
                                                <ReviewCell label="Campaign" value={name.trim() || "—"} />
                                                <ReviewCell label="Objective" value={objective.charAt(0).toUpperCase() + objective.slice(1)} />
                                                <ReviewCell
                                                    label="Platforms"
                                                    value={
                                                        platforms.size
                                                            ? ADS_PLATFORMS.filter((p) => platforms.has(p.id)).map((p) => p.label).join(" · ")
                                                            : "None selected"
                                                    }
                                                />
                                                <ReviewCell label="Daily budget" value={budgetMinor ? fmtMoney(budgetMinor, currency) : "Capped default"} />
                                                <ReviewCell label="Locations" value={geo.trim() || "—"} />
                                                <ReviewCell
                                                    label="Creative"
                                                    value={pickedVariant ? "1 variant selected" : "Not selected"}
                                                    sub={pickedVariant ? "Approved & moderated" : "Pick one in step 3"}
                                                />
                                            </div>
                                            {precheckBlocked && (
                                                <div className="flex items-start gap-2 p-3 rounded-2xl bg-primary-05/8 text-caption text-t-secondary">
                                                    <Icon name="info" className="size-4 fill-primary-05 shrink-0 mt-px" />
                                                    Balance is below the daily budget — launching keeps the campaign in
                                                    dry-run until it's funded.
                                                </div>
                                            )}
                                            <Button
                                                isBlack
                                                className="w-full justify-center"
                                                icon="send"
                                                onClick={() => setStepUpOpen(true)}
                                                disabled={launching || !writable || !planId}
                                            >
                                                {launching ? "Launching…" : "Launch — confirm with PIN"}
                                            </Button>
                                            <p className="text-caption text-t-tertiary text-center">
                                                Launching requires your security PIN. Spend stays dry-run until ad
                                                platforms are connected.
                                            </p>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>

            {/* ── footer nav (hidden in auto-pilot + once launched) ── */}
            {!autopilot && !launched && (
                <div className="flex items-center justify-between gap-3 p-6 pt-4 border-t border-s-subtle">
                    <button
                        type="button"
                        onClick={step === 0 ? onClose : goBack}
                        className="inline-flex items-center gap-1.5 h-11 px-5 rounded-3xl border border-s-stroke2 text-button text-t-secondary transition-colors hover:text-t-primary hover:border-s-highlight"
                    >
                        {step === 0 ? "Cancel" : "Back"}
                    </button>
                    {step === 0 ? (
                        <Button isBlack icon="arrow" onClick={doPropose} disabled={!step0Valid || proposing || !writable}>
                            {proposing ? "Drafting…" : "Draft & continue"}
                        </Button>
                    ) : step < 3 ? (
                        <Button isBlack icon="arrow" onClick={() => setStep((s) => s + 1)}>
                            {step === 2 ? "Review" : "Continue"}
                        </Button>
                    ) : null}
                </div>
            )}

            {launched && (
                <div className="flex items-center justify-end gap-3 p-6 pt-4 border-t border-s-subtle">
                    <Button isBlack onClick={onClose}>Done</Button>
                </div>
            )}

            <StepUpModal
                open={stepUpOpen}
                onClose={() => setStepUpOpen(false)}
                onToken={doApprove}
                scope="spend"
                actionLabel="Approve & launch"
            />
        </div>
    );
}

/* ----------------------------------------------------------------- helpers */

function Labeled({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
    return (
        <div>
            <label className="block text-button mb-2.5 text-t-primary">{label}</label>
            {children}
            {hint && <p className="text-caption text-t-tertiary mt-2">{hint}</p>}
        </div>
    );
}

function ReviewCell({ label, value, sub }: { label: string; value: string; sub?: string }) {
    return (
        <div className="bg-b-surface2 p-4">
            <div className="eyebrow mb-1">{label}</div>
            <div className="text-body-1 text-t-primary truncate">{value}</div>
            {sub && <div className="mt-0.5 text-caption text-t-tertiary truncate">{sub}</div>}
        </div>
    );
}

/* ------------------------------------------------------------- auto-pilot */

function AutopilotPanel({
    name,
    setName,
    objective,
    setObjective,
    geo,
    setGeo,
    audience,
    setAudience,
    budget,
    setBudget,
    currency,
    busy,
    writable,
    onLaunch,
}: {
    name: string;
    setName: (v: string) => void;
    objective: AdsObjective;
    setObjective: (v: AdsObjective) => void;
    geo: string;
    setGeo: (v: string) => void;
    audience: string;
    setAudience: (v: string) => void;
    budget: string;
    setBudget: (v: string) => void;
    currency: string;
    busy: boolean;
    writable: boolean;
    onLaunch: () => void;
}) {
    return (
        <div className="step-reveal space-y-4">
            <div className="flex items-start gap-3 p-4 rounded-2xl bg-primary-01/8">
                <Icon name="promote" className="size-5 fill-primary-01 shrink-0 mt-0.5" />
                <p className="text-body-2 text-t-secondary">
                    Tell Auto-Pilot the goal and the budget. It drafts the plan, writes and moderates the
                    creative, checks viability and launches — all on its own, behind the same caps and the
                    dry-run guard. You can pause it any time from Campaigns.
                </p>
            </div>
            <Labeled label="Campaign name / product">
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Diwali offer — 2BHK Gurgaon" className={inputCls} autoFocus />
            </Labeled>
            <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
                <Labeled label="Objective">
                    <select value={objective} onChange={(e) => setObjective(e.target.value as AdsObjective)} className={`${inputCls} appearance-none`}>
                        {ADS_OBJECTIVES.map((o) => (
                            <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>
                        ))}
                    </select>
                </Labeled>
                <Labeled label={`Daily budget (${currency === "INR" ? "₹" : currency})`}>
                    <input type="number" min="0" step="1" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="1500" className={inputCls} />
                </Labeled>
            </div>
            <Labeled label="Locations" hint="Comma-separated.">
                <input value={geo} onChange={(e) => setGeo(e.target.value)} placeholder="Gurgaon, Delhi NCR" className={inputCls} />
            </Labeled>
            <Labeled label="Audience">
                <input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Home buyers, 28–45, ready to move" className={inputCls} />
            </Labeled>
            <Button isBlack className="w-full justify-center" icon="promote" onClick={onLaunch} disabled={!name.trim() || busy || !writable}>
                {busy ? "Starting Auto-Pilot…" : "Start Auto-Pilot"}
            </Button>
        </div>
    );
}
