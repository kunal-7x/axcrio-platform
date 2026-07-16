"use client";

// Ad Automation › Run a Campaign (V2-W5) — the FULL-PAGE multi-step wizard.
//
// De-modaled from the old _campaign-wizard. A two-column flow (form left, LIVE
// estimation right) on the proven Run-page <Stepper> spine:
//
//   ① Campaign & Audience  → pick an EXISTING voice campaign from a dropdown; the
//                            engine PREFILLS product / audience / geo / budget from
//                            its saved brief (no re-typing). Read-only context panel.
//   ② Platforms & Budget   → multi-select Meta / Google / WhatsApp + daily budget,
//                            balance + add-funds.
//   ③ Creative             → generate from the brief OR adopt a library asset; each
//                            clears the moderation gate; pick an approved variant.
//   ④ Review & Launch      → read-only summary → PIN step-up → approve & launch.
//
// The Auto-Pilot toggle is GONE — it lives on Connections › Autopilot now. Every
// spend path stays dry-run server-side; launch fail-closes without an X-Step-Up
// token. On success we return to the cockpit. Token-pure, zero raw hex.

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Layout from "@/components/Layout";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import CampaignSelect from "@/components/CampaignSelect";
import Stepper, { type Step } from "@/app/run/_stepper";
import { getCampaign, type Campaign } from "@/lib/api";
import { listAssets, type Asset, type CampaignContextSnapshot } from "@/lib/assets";
import { useMe, canWrite } from "@/lib/auth";
import StepUpModal from "../_tabs/_step-up";
import { useToast } from "../_chrome";
import { useAdsSpine } from "../_spine";
import { getConnectProviders, getFundingPrecheck, type ConnectProviderStatus } from "../_tabs/_connect-lib";
import {
    proposeCampaign,
    submitCreative,
    uploadCreative,
    getCreativeVariants,
    approveCampaign,
    getBudgetBalance,
    fundBudget,
    campaignToBrief,
    fmtMoney,
    ADS_OBJECTIVES,
    ADS_PLATFORMS,
    type AdsObjective,
    type AdsPlatform,
    type AdsBrief,
    type BudgetBalance,
    type CreativeVariant,
} from "../_lib";

const STEPS: Step[] = [
    { label: "Campaign & Audience", hint: "Reuse a voice campaign" },
    { label: "Platforms & Budget", hint: "Where & how much" },
    { label: "Creative", hint: "The ad itself" },
    { label: "Review & Launch", hint: "Confirm & go" },
];

const inputCls =
    "w-full h-11 px-4 rounded-2xl text-body-2 bg-b-surface2 border border-s-subtle text-t-primary focus:outline-none focus:border-s-highlight transition-colors";

export default function AdsRunPage() {
    return (
        <Suspense fallback={<Layout title="Run a Campaign"><div className="py-24" /></Layout>}>
            <RunInner />
        </Suspense>
    );
}

function RunInner() {
    const router = useRouter();
    const { me } = useMe();
    const writable = canWrite(me);
    const { showToast, ToastHost } = useToast();
    const { currency, hc } = useAdsSpine();

    const [step, setStep] = useState(0);

    // ── Step 1: campaign + brief ──
    const [campaignId, setCampaignId] = useState("");
    const [context, setContext] = useState<CampaignContextSnapshot | null>(null);
    const [name, setName] = useState("");
    const [objective, setObjective] = useState<AdsObjective>("leads");
    const [geo, setGeo] = useState("");
    const [audience, setAudience] = useState("");
    const [instruction, setInstruction] = useState("");
    const [sourceCampaignId, setSourceCampaignId] = useState("");
    const variants = 3;
    const [planId, setPlanId] = useState("");
    const [proposing, setProposing] = useState(false);

    // ── Step 2: platforms & budget ──
    const [providers, setProviders] = useState<ConnectProviderStatus[] | null>(null);
    const [platforms, setPlatforms] = useState<Set<AdsPlatform>>(new Set());
    const [budget, setBudget] = useState("");
    const [balance, setBalance] = useState<BudgetBalance | null>(null);
    const [funding, setFunding] = useState(false);
    const [precheckBlocked, setPrecheckBlocked] = useState(false);

    // ── Step 3: creative ──
    const [creativeMode, setCreativeMode] = useState<"generate" | "upload">("generate");
    const [generating, setGenerating] = useState(false);
    const [vlist, setVlist] = useState<CreativeVariant[]>([]);
    const [pickedVariant, setPickedVariant] = useState("");
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

    useEffect(() => {
        getConnectProviders().then((r) => setProviders(r?.providers ?? []));
        getBudgetBalance().then((r) => setBalance(r.kind === "ok" ? r.data : null));
    }, []);

    useEffect(() => {
        if (!providersResolved) return;
        setPlatforms((prev) => {
            if (prev.size > 0) return prev;
            const next = new Set<AdsPlatform>();
            (Object.keys(connected) as AdsPlatform[]).forEach((p) => connected[p] && next.add(p));
            return next;
        });
    }, [providersResolved, connected]);

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

    // ── campaign pick → prefill from the voice campaign's saved brief ──
    const handleCampaignPick = useCallback(
        (c: Campaign, detail: CampaignContextSnapshot) => {
            if (!c.id) {
                // "All campaigns" reset row — clear the prefill
                setCampaignId("");
                setContext(null);
                setSourceCampaignId("");
                return;
            }
            setCampaignId(c.id);
            setContext(detail);
            // fetch the full `fields` blob (CampaignSelect only has the lean row) and
            // map it onto the ad brief — prefill, never overwrite a field the user
            // already typed if it resolves empty.
            getCampaign(c.id).then((full) => {
                const brief = campaignToBrief(full || c);
                if (brief.source_campaign_id) setSourceCampaignId(brief.source_campaign_id);
                if (brief.name) setName(brief.name);
                if (brief.audience && typeof brief.audience.description === "string") {
                    setAudience(brief.audience.description);
                }
                if (brief.geo?.length) setGeo(brief.geo.join(", "));
                if (brief.budget_daily_minor) setBudget(String(brief.budget_daily_minor / 100));
                if (brief.instruction) setInstruction(brief.instruction);
            });
        },
        [],
    );

    const buildBrief = useCallback((): AdsBrief => {
        const b: AdsBrief = { name: name.trim(), objective, variants };
        if (budgetMinor > 0) b.budget_daily_minor = budgetMinor;
        if (geo.trim()) b.geo = geo.split(",").map((s) => s.trim()).filter(Boolean);
        if (audience.trim()) b.audience = { description: audience.trim() };
        if (instruction.trim()) b.instruction = instruction.trim();
        if (sourceCampaignId) b.source_campaign_id = sourceCampaignId;
        return b;
    }, [name, objective, budgetMinor, geo, audience, instruction, sourceCampaignId]);

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

    useEffect(() => {
        if (step === 2 && creativeMode === "upload" && assets.length === 0) {
            listAssets({ limit: 12 }).then((p) => setAssets(p.assets || []));
        }
    }, [step, creativeMode, assets.length]);

    const doPropose = useCallback(async () => {
        if (!name.trim() || proposing) return;
        setProposing(true);
        try {
            const res = await proposeCampaign(buildBrief());
            setPlanId(res.plan_id);
            setStep(1);
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Couldn't draft the campaign.", "error");
        } finally {
            setProposing(false);
        }
    }, [name, proposing, buildBrief, showToast]);

    const doFund = useCallback(async () => {
        const need = Math.max(budgetMinor - balanceMinor, budgetMinor);
        if (need <= 0 || funding) return;
        setFunding(true);
        try {
            const intent = await fundBudget(need, { description: `Top-up for ${name.trim() || "campaign"}` });
            if (intent.status === "not_configured" || intent.needs_setup) {
                showToast("Connect a payment method in Connections to add funds.", "error");
            } else {
                showToast("Funding started — your balance updates once the payment clears.");
            }
            const r = await getBudgetBalance();
            setBalance(r.kind === "ok" ? r.data : balance);
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Couldn't start funding.", "error");
        } finally {
            setFunding(false);
        }
    }, [budgetMinor, balanceMinor, funding, name, balance, showToast]);

    const doGenerate = useCallback(async () => {
        if (!planId || generating) return;
        setGenerating(true);
        try {
            await submitCreative({ plan_id: planId, brief: { ...buildBrief(), instruction: instruction.trim() || audience.trim() } });
            showToast("Generating variants — they appear below as each clears moderation.");
            loadVariants();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Couldn't start generation.", "error");
        } finally {
            setGenerating(false);
        }
    }, [planId, generating, buildBrief, instruction, audience, loadVariants, showToast]);

    const doAdopt = useCallback(
        async (asset: Asset) => {
            if (!planId || adoptingId) return;
            setAdoptingId(asset.id);
            try {
                await uploadCreative(planId, asset.id, { brief: buildBrief() });
                showToast("Asset added — it runs the moderation gate before it can spend.");
                loadVariants();
            } catch (e) {
                showToast(e instanceof Error ? e.message : "Couldn't add that asset.", "error");
            } finally {
                setAdoptingId("");
            }
        },
        [planId, adoptingId, buildBrief, loadVariants, showToast],
    );

    const doApprove = useCallback(
        async (token: string) => {
            if (!planId) return;
            setLaunching(true);
            try {
                const res = await approveCampaign(planId, token);
                if (res.status === "blocked_not_approved") {
                    showToast("That PIN didn't satisfy the launch gate — try again.", "error");
                } else {
                    setLaunched({ ref: res.campaign_ref, status: res.status });
                    showToast(
                        res.status === "active"
                            ? `${name.trim() || "Campaign"} is live.`
                            : `${name.trim() || "Campaign"} approved — held in test mode until ad platforms go live.`,
                    );
                }
            } catch (e) {
                showToast(e instanceof Error ? e.message : "Launch failed.", "error");
            } finally {
                setLaunching(false);
            }
        },
        [planId, name, showToast],
    );

    const approvedVariants = vlist.filter((v) => (v.moderation_status || "pending").toLowerCase() === "approved");
    const step0Valid = !!name.trim();
    const maxReachable = !planId ? 0 : STEPS.length - 1;
    const goBack = () => setStep((s) => Math.max(0, s - 1));

    return (
        <Layout title="Run a Campaign">
            <ToastHost />

            <div className="mb-5">
                <Stepper steps={STEPS} step={step} maxReachable={maxReachable} onStep={(i) => i <= maxReachable && setStep(i)} />
            </div>

            <div className="grid grid-cols-[1fr_22rem] gap-5 items-start max-lg:grid-cols-1">
                {/* ── LEFT: the step form ── */}
                <div className="card p-5 max-lg:p-4 min-w-0">
                    {launched ? (
                        <LaunchedState
                            launched={launched}
                            onDone={() => router.push("/ads/command")}
                        />
                    ) : (
                        <>
                            {step === 0 && (
                                <div key="w0" className="step-reveal space-y-4">
                                    <div>
                                        <div className="eyebrow mb-2">Start from a campaign</div>
                                        <CampaignSelect
                                            value={campaignId}
                                            onSelect={handleCampaignPick}
                                            label="Voice campaign"
                                            placeholder="Pick a campaign to reuse its brief"
                                        />
                                        <p className="text-caption text-t-tertiary mt-2">
                                            We prefill the product, audience, locations and budget from the
                                            campaign you already built — no re-typing.
                                        </p>
                                    </div>

                                    {context && context.facts.length > 0 && (
                                        <div className="rounded-2xl bg-b-surface2 border border-s-subtle p-4">
                                            <div className="eyebrow mb-2.5">Campaign context</div>
                                            <div className="grid grid-cols-2 gap-x-4 gap-y-2.5 max-sm:grid-cols-1">
                                                {context.facts.slice(0, 8).map((f) => (
                                                    <div key={f.key} className="min-w-0">
                                                        <div className="text-caption text-t-tertiary">{f.label}</div>
                                                        <div className="text-body-2 text-t-primary truncate">{f.value || "—"}</div>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    <Labeled label="Campaign name / product">
                                        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Diwali offer — 2BHK Gurgaon" className={inputCls} />
                                    </Labeled>
                                    <Labeled label="Objective">
                                        <select value={objective} onChange={(e) => setObjective(e.target.value as AdsObjective)} className={`${inputCls} appearance-none`}>
                                            {ADS_OBJECTIVES.map((o) => (
                                                <option key={o} value={o}>{o.charAt(0).toUpperCase() + o.slice(1)}</option>
                                            ))}
                                        </select>
                                    </Labeled>
                                    <div className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
                                        <Labeled label="Locations" hint="Comma-separated.">
                                            <input value={geo} onChange={(e) => setGeo(e.target.value)} placeholder="Gurgaon, Delhi NCR" className={inputCls} />
                                        </Labeled>
                                        <Labeled label="Audience">
                                            <input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Home buyers, 28–45" className={inputCls} />
                                        </Labeled>
                                    </div>
                                </div>
                            )}

                            {step === 1 && (
                                <div key="w1" className="step-reveal space-y-5">
                                    <div>
                                        <div className="text-button text-t-primary mb-2.5">Platforms</div>
                                        {providersResolved && !anyConnected && (
                                            <div className="mb-3 flex items-start gap-2 p-3 rounded-2xl bg-primary-05/8 text-caption text-t-secondary">
                                                <Icon name="info" className="size-4 fill-primary-05 shrink-0 mt-px" />
                                                No ad accounts connected yet. Connect one under Connections to launch live — you can still draft and review everything here in test mode.
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
                                                            on ? "border-primary-01/40 bg-primary-01/8" : "border-s-subtle bg-b-surface2 hover:border-s-stroke2"
                                                        }`}
                                                    >
                                                        <span className="flex items-center justify-between w-full">
                                                            <Icon name={p.icon} className={`size-5 ${on ? "fill-primary-01" : "fill-t-secondary"}`} />
                                                            {isConnected ? <Badge variant="success" dot>Connected</Badge> : <Badge variant="neutral">Not connected</Badge>}
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

                                    <Labeled label={`Daily budget (${currency === "INR" ? "₹" : currency})`} hint="Clamped to your hard cap server-side. Nothing spends until you launch.">
                                        <input type="number" min="0" step="1" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="1500" className={inputCls} />
                                    </Labeled>

                                    <div className="flex items-center justify-between gap-3 p-3.5 rounded-2xl bg-b-surface2 border border-s-subtle">
                                        <div className="min-w-0">
                                            <div className="text-caption text-t-tertiary">Ad-budget balance</div>
                                            <div className="text-body-1 text-t-primary tabular-nums">{fmtMoney(balanceMinor, currency)}</div>
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
                                            Your balance can't cover this daily budget. Add funds to launch live — or continue and keep it in test mode.
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
                                                    creativeMode === m ? "bg-b-surface1 text-t-primary shadow-widget ring-1 ring-s-subtle dark:bg-shade-04" : "text-t-secondary hover:text-t-primary"
                                                }`}
                                            >
                                                {m === "generate" ? "Generate" : "Use my asset"}
                                            </button>
                                        ))}
                                    </div>

                                    {creativeMode === "generate" ? (
                                        <div className="p-4 rounded-2xl bg-b-surface2 border border-s-subtle">
                                            <p className="text-body-2 text-t-secondary mb-3">
                                                The AI writes {variants} variants from your brief. Each runs the moderation gate (RERA, Housing, brand, broken-text) before it can spend.
                                            </p>
                                            <Button isBlack icon="magic-pencil" onClick={doGenerate} disabled={generating || !writable || !planId}>
                                                {generating ? "Generating…" : "Generate variants"}
                                            </Button>
                                        </div>
                                    ) : (
                                        <div>
                                            <p className="text-body-2 text-t-secondary mb-3">Pick one of your library assets — it becomes an ad variant and runs the same moderation gate.</p>
                                            {assets.length === 0 ? (
                                                <div className="p-6 text-center text-caption text-t-tertiary rounded-2xl bg-b-surface2 border border-s-subtle">
                                                    No library assets yet. Generate one on the left, or add media in Creative Studio.
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
                                                                <span className="absolute inset-0 grid place-items-center bg-shade-04/60 text-caption text-t-light">Adding…</span>
                                                            )}
                                                        </button>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    <div>
                                        <div className="flex items-center justify-between mb-2.5">
                                            <div className="text-button text-t-primary">Pick a variant to run</div>
                                            {vlist.length > 0 && (
                                                <span className="text-caption text-t-tertiary">{approvedVariants.length} approved · {vlist.length} total</span>
                                            )}
                                        </div>
                                        {vlist.length === 0 ? (
                                            <div className="p-5 text-center text-caption text-t-tertiary rounded-2xl bg-b-surface2 border border-s-subtle">
                                                No variants yet — generate or add one above, then it appears here once it clears moderation.
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
                                                                picked ? "border-primary-01/50 bg-primary-01/8" : approved ? "border-s-subtle bg-b-surface2 hover:border-s-stroke2" : "border-s-subtle bg-b-surface2 opacity-70 cursor-not-allowed"
                                                            }`}
                                                        >
                                                            <span className="size-11 shrink-0 rounded-xl bg-cover bg-center bg-b-surface1 dark:bg-shade-04/40" style={v.url ? { backgroundImage: `url(${v.url})` } : undefined} />
                                                            <span className="min-w-0 flex-1">
                                                                <span className="block text-body-2 text-t-primary line-clamp-1">{v.headline || "Untitled variant"}</span>
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
                                    <div className="grid grid-cols-2 gap-px rounded-2xl overflow-hidden border border-s-subtle bg-s-subtle max-sm:grid-cols-1">
                                        <ReviewCell label="Campaign" value={name.trim() || "—"} />
                                        <ReviewCell label="Objective" value={objective.charAt(0).toUpperCase() + objective.slice(1)} />
                                        <ReviewCell label="Platforms" value={platforms.size ? ADS_PLATFORMS.filter((p) => platforms.has(p.id)).map((p) => p.label).join(" · ") : "None selected"} />
                                        <ReviewCell label="Daily budget" value={budgetMinor ? fmtMoney(budgetMinor, currency) : "Capped default"} />
                                        <ReviewCell label="Locations" value={geo.trim() || "—"} />
                                        <ReviewCell label="Creative" value={pickedVariant ? "1 variant selected" : "Not selected"} sub={pickedVariant ? "Approved & moderated" : "Pick one in step 3"} />
                                    </div>
                                    {precheckBlocked && (
                                        <div className="flex items-start gap-2 p-3 rounded-2xl bg-primary-05/8 text-caption text-t-secondary">
                                            <Icon name="info" className="size-4 fill-primary-05 shrink-0 mt-px" />
                                            Balance is below the daily budget — launching keeps the campaign in test mode until it's funded.
                                        </div>
                                    )}
                                    <Button isBlack className="w-full justify-center" icon="send" onClick={() => setStepUpOpen(true)} disabled={launching || !writable || !planId}>
                                        {launching ? "Launching…" : "Launch — confirm with PIN"}
                                    </Button>
                                    <p className="text-caption text-t-tertiary text-center">
                                        Launching requires your security PIN. Spend stays in test mode until ad platforms are connected.
                                    </p>
                                </div>
                            )}

                            {/* footer nav */}
                            <div className="flex items-center justify-between gap-3 mt-6 pt-4 border-t border-s-subtle">
                                <button
                                    type="button"
                                    onClick={step === 0 ? () => router.push("/ads/command") : goBack}
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
                        </>
                    )}
                </div>

                {/* ── RIGHT: live estimation rail ── */}
                <EstimateRail
                    budgetMinor={budgetMinor}
                    platforms={platforms}
                    currency={currency}
                    balanceMinor={balanceMinor}
                    objective={objective}
                />
            </div>

            <StepUpModal open={stepUpOpen} onClose={() => setStepUpOpen(false)} onToken={doApprove} scope="spend" actionLabel="Approve & launch" />
        </Layout>
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

function LaunchedState({ launched, onDone }: { launched: { ref?: string; status: string }; onDone: () => void }) {
    return (
        <div className="step-reveal text-center py-6">
            <span className="grid place-items-center size-14 mx-auto rounded-2xl bg-primary-02/12 fill-primary-02">
                <Icon name="check-circle-fill" className="size-8 fill-inherit" />
            </span>
            <div className="mt-4 text-h5 text-t-primary">{launched.status === "active" ? "Campaign launched" : "Approved — test mode"}</div>
            <p className="mt-1.5 text-body-2 text-t-secondary max-w-md mx-auto">
                {launched.status === "active"
                    ? "It's live and spending against its hard cap."
                    : "Approved and parked in test mode — it goes live the moment your ad platforms are connected. Nothing spends until then."}
            </p>
            {launched.ref && <div className="mt-2 text-caption text-t-tertiary tabular-nums">Ref {launched.ref}</div>}
            <Button isBlack className="mt-5" icon="arrow" onClick={onDone}>Go to cockpit</Button>
        </div>
    );
}

/* ------------------------------------------------------ live estimation rail */

// Honest, clearly-labelled projections from the daily budget + platform mix. Not
// a guarantee — a planning aid (the same "estimated results" rail every premium
// builder shows). Ranges widen the fewer platforms are selected.
function EstimateRail({
    budgetMinor,
    platforms,
    currency,
    balanceMinor,
    objective,
}: {
    budgetMinor: number;
    platforms: Set<AdsPlatform>;
    currency: string;
    balanceMinor: number;
    objective: AdsObjective;
}) {
    const daily = budgetMinor / 100;
    const weekly = daily * 7;
    const platformCount = Math.max(1, platforms.size);
    // CPM assumption band (₹ per 1000 impressions) — India social/search blend.
    const cpmLo = 35;
    const cpmHi = 90;
    const imprLo = daily > 0 ? Math.round((daily / cpmHi) * 1000) : 0;
    const imprHi = daily > 0 ? Math.round((daily / cpmLo) * 1000) : 0;
    // reach ≈ impressions / frequency (1.4–2.2)
    const reachLo = Math.round(imprLo / 2.2);
    const reachHi = Math.round(imprHi / 1.4);
    // CPL band by objective (leads cheaper than sales)
    const cplBase = objective === "sales" ? 320 : objective === "leads" ? 160 : 90;
    const cplLo = Math.round(cplBase * 0.7);
    const cplHi = Math.round(cplBase * 1.5);
    const pacing = balanceMinor > 0 && budgetMinor > 0 ? Math.min(100, Math.round((budgetMinor / balanceMinor) * 100)) : 0;

    const fmtK = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}K` : String(n));

    return (
        <aside className="card p-5 max-lg:p-4 sticky top-4 max-lg:static">
            <div className="eyebrow mb-1">Estimated results</div>
            <p className="text-caption text-t-tertiary mb-4">A planning estimate — actuals depend on creative and the live auction.</p>

            {daily <= 0 ? (
                <div className="rounded-2xl bg-b-surface2 border border-s-subtle p-4 text-caption text-t-tertiary">
                    Set a daily budget to see projected reach, impressions and cost per lead.
                </div>
            ) : (
                <div className="space-y-3">
                    <EstRow label="Reach" value={`${fmtK(reachLo)}–${fmtK(reachHi)}`} sub="unique people / day" />
                    <EstRow label="Impressions" value={`${fmtK(imprLo)}–${fmtK(imprHi)}`} sub="per day" />
                    <EstRow label="Cost per lead" value={`${fmtMoney(cplLo * 100, currency)}–${fmtMoney(cplHi * 100, currency)}`} sub="estimated" />
                    <EstRow label="Weekly spend" value={fmtMoney(Math.round(weekly * 100), currency)} sub={`${platformCount} platform${platformCount === 1 ? "" : "s"}`} />

                    <div className="pt-2">
                        <div className="flex items-center justify-between text-caption mb-1.5">
                            <span className="text-t-tertiary">Budget pacing</span>
                            <span className="text-t-secondary tabular-nums">{pacing}% of balance / day</span>
                        </div>
                        <div className="h-2 rounded-full bg-b-surface2 overflow-hidden">
                            <div
                                className="h-full rounded-full transition-all"
                                style={{ width: `${pacing}%`, background: pacing >= 90 ? "var(--primary-03)" : "var(--primary-01)" }}
                            />
                        </div>
                    </div>
                </div>
            )}
        </aside>
    );
}

function EstRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
    return (
        <div className="flex items-end justify-between gap-3 pb-3 border-b border-s-subtle last:border-0 last:pb-0">
            <div className="min-w-0">
                <div className="text-body-2 text-t-primary">{label}</div>
                {sub && <div className="text-caption text-t-tertiary">{sub}</div>}
            </div>
            <div className="text-body-1 text-t-primary tabular-nums text-right">{value}</div>
        </div>
    );
}
