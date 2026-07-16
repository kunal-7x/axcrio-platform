"use client";

// Ad-Engine · Campaigns tab — the live paid-ad campaign list.
//
// LIFTED from the inline `CampaignsTab` + `ProposeForm` that lived in
// app/ads/page.tsx, then ENHANCED to the FRONTEND_ARCHITECTURE §3 spec:
//   • the `data-table` keeps skeleton / dormant / empty / error / data states;
//   • status `Badge` via statusVariant; the inline spend-vs-cap `.meter` bar;
//   • per-row Approve (step-up, fail-closed) + Pause (with a reason `Modal`);
//   • a Leads column; a "Draft a campaign" `Button isBlack` (gated `writable`)
//     that opens the `ProposeForm` in a centred `Modal` (collects MAJOR budget,
//     sends `*100` minor).
// The live backend + the 30s visibility-gated poll are wired at the page level
// (page.tsx → getAdsCampaigns → useRealtimeRefresh). Shared widgets/maps come
// from ../_shared; data helpers from ../_lib. Zero raw hex — tokens only.

import { useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import {
    approveCampaign,
    pauseCampaign,
    proposeCampaign,
    fmtMoney,
    ADS_OBJECTIVES,
    type AdsHealth,
    type AdsCampaign,
    type AdsStatusResponse,
    type AdsBrief,
    type AdsObjective,
    type ReadResult,
} from "../_lib";
import {
    DormantPanel,
    statusVariant,
    statusLabel,
    objectiveLabel,
    providerLabel,
    providerIcon,
    type ToastFn,
} from "../_shared";
import StepUpModal from "./_step-up";
import CampaignWizard from "./_campaign-wizard";

export type CampaignsTabProps = {
    result: ReadResult<AdsStatusResponse> | null;
    rows: AdsCampaign[];
    loading: boolean;
    writable: boolean;
    currency: string;
    hc: AdsHealth | null;
    onChanged: () => void;
    toast: ToastFn;
};

// The backend campaign record doesn't always carry a lead count; read it
// defensively (leads / conversions) so the column degrades to "—" rather than
// throwing while the engine is still dormant.
function leadCount(c: AdsCampaign): number | null {
    const v = (c as { leads_today?: number; leads?: number; conversions?: number });
    const n = v.leads_today ?? v.leads ?? v.conversions;
    return typeof n === "number" ? n : null;
}

export default function CampaignsTab({
    result,
    rows,
    loading,
    writable,
    currency,
    hc,
    onChanged,
    toast,
}: CampaignsTabProps) {
    const dormant = result?.kind === "dormant";
    const error = result?.kind === "error" ? result.message : "";
    const [busyId, setBusyId] = useState<string>("");
    const [proposeOpen, setProposeOpen] = useState(false);
    const [wizardOpen, setWizardOpen] = useState(false);
    const [pauseTarget, setPauseTarget] = useState<AdsCampaign | null>(null);
    // The campaign whose launch is awaiting a PIN step-up token (opens StepUpModal).
    const [approveTarget, setApproveTarget] = useState<AdsCampaign | null>(null);

    // writable controls every write surface; columns shift when actions hide.
    const cols = writable ? 8 : 7;

    // Approve & launch — now wired through the step-up PIN. The PIN modal mints a
    // `spend`-scope X-Step-Up token; we replay it on the approve call so the
    // backend's fail-closed launch gate is satisfied (previously this sent NO
    // token, so every launch returned blocked_not_approved).
    async function doApprove(c: AdsCampaign, token: string) {
        setBusyId(c.plan_id);
        try {
            const res = await approveCampaign(c.plan_id, token);
            if (res.status === "active") {
                toast(`${c.name} is live`);
            } else if (res.status === "dry_run" || res.status === "not_configured") {
                toast(`${c.name} approved — held in dry-run until ad platforms are connected`);
            } else if (res.status === "blocked_not_approved") {
                toast("That PIN didn't satisfy the launch gate — try again", "error");
            } else {
                toast(`${c.name}: ${statusLabel(res.status)}`, "error");
            }
            onChanged();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Approve failed", "error");
        } finally {
            setBusyId("");
        }
    }

    async function doPause(c: AdsCampaign, reason: string) {
        setBusyId(c.plan_id);
        try {
            await pauseCampaign(c.plan_id, reason || "manual_pause");
            toast(`${c.name} paused`);
            setPauseTarget(null);
            onChanged();
        } catch (e) {
            toast(e instanceof Error ? e.message : "Pause failed", "error");
        } finally {
            setBusyId("");
        }
    }

    return (
        <>
            <Card
                title="Campaigns"
                classHead="pr-5 max-lg:pr-3"
                headContent={
                    <div className="flex items-center gap-3">
                        <span className="inline-flex items-center gap-1.5 text-caption text-t-tertiary max-sm:hidden">
                            <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                            Capped · approval-gated
                        </span>
                        {writable && !dormant && (
                            <Button
                                isStroke
                                className="h-9 !px-4 text-button"
                                onClick={() => setProposeOpen(true)}
                            >
                                <Icon name="magic-pencil" className="size-4 fill-inherit" />
                                Draft a campaign
                            </Button>
                        )}
                        {writable && !dormant && (
                            <Button
                                isBlack
                                className="h-9 !px-4 text-button"
                                icon="send"
                                onClick={() => setWizardOpen(true)}
                            >
                                Run a Campaign
                            </Button>
                        )}
                    </div>
                }
            >
                {error ? (
                    // Real non-200 (not dormant): say what happened + offer a retry.
                    <div className="state-block">
                        <span className="state-glyph">
                            <Icon name="info" className="fill-inherit" />
                        </span>
                        <div className="state-title">Couldn’t load campaigns</div>
                        <div className="state-sub">{error}</div>
                        <Button isStroke className="h-9 !px-4 text-button mt-1" onClick={onChanged}>
                            <Icon name="clock" className="size-4 fill-inherit" />
                            Try again
                        </Button>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th>Campaign</th>
                                    <th>Platform</th>
                                    <th>Objective</th>
                                    <th>Spend / Cap</th>
                                    <th>CPL</th>
                                    <th>Leads</th>
                                    <th>Status</th>
                                    {writable && <th className="text-right pr-5">Actions</th>}
                                </tr>
                            </thead>
                            <tbody>
                                {loading ? (
                                    [...Array(3)].map((_, i) => (
                                        <tr key={i}>
                                            {[...Array(cols)].map((__, j) => (
                                                <td key={j}>
                                                    <div className="skeleton h-4 w-20" />
                                                </td>
                                            ))}
                                        </tr>
                                    ))
                                ) : dormant ? (
                                    <tr>
                                        <td colSpan={cols}>
                                            <DormantPanel
                                                icon="promote"
                                                title="Campaigns coming soon"
                                                sub="Once the Ads engine is provisioned on the server, every drafted, live and paused campaign appears here with its live spend against the hard cap, its cost-per-lead and one-tap approve / pause controls."
                                            />
                                        </td>
                                    </tr>
                                ) : rows.length === 0 ? (
                                    <tr>
                                        <td colSpan={cols}>
                                            <div className="state-block">
                                                <span className="state-glyph">
                                                    <Icon name="magic-pencil" className="fill-inherit" />
                                                </span>
                                                <div className="state-title">No campaigns yet</div>
                                                <div className="state-sub">
                                                    Draft one from a brief to get started. The AI builds the copy,
                                                    audience and objective and parks it as a capped draft — nothing
                                                    spends until you approve it.
                                                </div>
                                                {writable && (
                                                    <Button
                                                        isBlack
                                                        className="h-9 !px-4 text-button mt-1"
                                                        onClick={() => setProposeOpen(true)}
                                                    >
                                                        <Icon name="magic-pencil" className="size-4 fill-inherit" />
                                                        Draft a campaign
                                                    </Button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    rows.map((c) => {
                                        const cap = c.daily_cap_minor || hc?.caps.daily_cap_minor || 0;
                                        const spend = c.spend_today_minor || 0;
                                        const pct = cap > 0 ? Math.min(100, Math.round((spend / cap) * 100)) : 0;
                                        const breaker = c.status === "blocked_cap_exceeded" || pct >= 100;
                                        const leads = leadCount(c);
                                        return (
                                            <tr key={c.plan_id}>
                                                <td>
                                                    <div className="text-body-2 text-t-primary truncate max-w-[14rem]">
                                                        {c.name}
                                                    </div>
                                                    {c.pause_reason && c.status === "paused" && (
                                                        <div className="text-caption text-t-tertiary mt-0.5 truncate max-w-[14rem]">
                                                            {c.pause_reason.replace(/_/g, " ")}
                                                        </div>
                                                    )}
                                                </td>
                                                <td>
                                                    <span className="inline-flex items-center gap-1.5 text-body-2 text-t-secondary">
                                                        <Icon
                                                            name={providerIcon(c.provider)}
                                                            className="size-4 fill-t-tertiary"
                                                        />
                                                        {providerLabel(c.provider)}
                                                    </span>
                                                </td>
                                                <td className="text-t-secondary">{objectiveLabel(c.objective)}</td>
                                                <td>
                                                    <div className="text-body-2 text-t-primary tabular-nums whitespace-nowrap">
                                                        {fmtMoney(spend, currency)}
                                                        <span className="text-t-tertiary">
                                                            {" "}
                                                            / {cap > 0 ? fmtMoney(cap, currency) : "—"}
                                                        </span>
                                                    </div>
                                                    {cap > 0 && (
                                                        <div className="meter mt-1.5 w-24">
                                                            <div
                                                                className="meter-fill"
                                                                style={{
                                                                    width: `${pct}%`,
                                                                    background: breaker
                                                                        ? "var(--primary-03)"
                                                                        : pct >= 90
                                                                        ? "var(--primary-05)"
                                                                        : "var(--primary-02)",
                                                                }}
                                                            />
                                                        </div>
                                                    )}
                                                </td>
                                                <td className="text-t-secondary tabular-nums whitespace-nowrap">
                                                    {c.last_cpl_minor != null
                                                        ? fmtMoney(c.last_cpl_minor, currency)
                                                        : "—"}
                                                </td>
                                                <td className="text-t-secondary tabular-nums">
                                                    {leads != null ? leads.toLocaleString() : "—"}
                                                </td>
                                                <td>
                                                    <Badge
                                                        variant={statusVariant(c.status)}
                                                        dot={c.status === "active"}
                                                    >
                                                        {statusLabel(c.status)}
                                                    </Badge>
                                                </td>
                                                {writable && (
                                                    <td className="text-right pr-5">
                                                        <div className="inline-flex items-center gap-2">
                                                            {c.status === "pending_approval" && (
                                                                <button
                                                                    onClick={() => setApproveTarget(c)}
                                                                    disabled={busyId === c.plan_id}
                                                                    className="inline-flex items-center gap-1 h-8 px-3 rounded-full border border-s-subtle text-button text-t-secondary transition-colors hover:border-s-highlight hover:text-t-primary disabled:opacity-50"
                                                                    title="Launching spends budget — confirmed with your security PIN"
                                                                >
                                                                    <Icon name="check-circle" className="size-3.5 fill-current" />
                                                                    Approve
                                                                </button>
                                                            )}
                                                            {c.status === "active" && (
                                                                <button
                                                                    onClick={() => setPauseTarget(c)}
                                                                    disabled={busyId === c.plan_id}
                                                                    className="inline-flex items-center gap-1 h-8 px-3 rounded-full border border-s-subtle text-button text-primary-03 fill-primary-03 transition-colors hover:bg-primary-03/8 disabled:opacity-50"
                                                                >
                                                                    <Icon name="block" className="size-3.5 fill-current" />
                                                                    Pause
                                                                </button>
                                                            )}
                                                        </div>
                                                    </td>
                                                )}
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>

            {/* Draft a campaign — manager+ only, in a centred Modal. */}
            {writable && (
                <Modal open={proposeOpen} onClose={() => setProposeOpen(false)}>
                    <ProposeForm
                        onProposed={() => {
                            setProposeOpen(false);
                            onChanged();
                        }}
                        toast={toast}
                        disabled={dormant}
                        currency={currency}
                    />
                </Modal>
            )}

            {/* Pause — capture a reason before stopping spend. */}
            {writable && (
                <PauseModal
                    target={pauseTarget}
                    busy={!!pauseTarget && busyId === pauseTarget.plan_id}
                    onClose={() => setPauseTarget(null)}
                    onConfirm={(reason) => pauseTarget && doPause(pauseTarget, reason)}
                />
            )}

            {/* Run a Campaign — the full guided 4-step wizard. */}
            {writable && (
                <CampaignWizard
                    open={wizardOpen}
                    onClose={() => setWizardOpen(false)}
                    writable={writable}
                    currency={currency}
                    hc={hc}
                    onLaunched={onChanged}
                    toast={toast}
                />
            )}

            {/* Per-row Approve — PIN step-up mints the spend token, then launches. */}
            {writable && (
                <StepUpModal
                    open={!!approveTarget}
                    onClose={() => setApproveTarget(null)}
                    onToken={async (token) => {
                        const c = approveTarget;
                        setApproveTarget(null);
                        if (c) await doApprove(c, token);
                    }}
                    scope="spend"
                    title="Approve & launch"
                    description={
                        approveTarget
                            ? `Launching ${approveTarget.name} spends real budget. Enter your security PIN to authorise it.`
                            : "Enter your security PIN to authorise this launch."
                    }
                    actionLabel="Approve & launch"
                />
            )}
        </>
    );
}

/* ------------------------------------------------------------ propose form */

function ProposeForm({
    onProposed,
    toast,
    disabled,
    currency,
}: {
    onProposed: () => void;
    toast: ToastFn;
    disabled: boolean;
    currency: string;
}) {
    const [name, setName] = useState("");
    const [objective, setObjective] = useState<AdsObjective>("leads");
    const [geo, setGeo] = useState("");
    const [audience, setAudience] = useState("");
    const [budget, setBudget] = useState(""); // major units, e.g. "1500"
    const [variants, setVariants] = useState(3);
    const [saving, setSaving] = useState(false);

    const inputCls = "input-base w-full h-11 px-4 rounded-2xl text-body-2";
    const selectCls = `${inputCls} appearance-none`;

    async function submit(e: React.FormEvent) {
        e.preventDefault();
        if (!name.trim()) return;
        setSaving(true);
        const brief: AdsBrief = {
            name: name.trim(),
            objective,
            variants,
        };
        // Inputs collect MAJOR currency; the engine meters in minor (paise).
        const budgetMajor = parseFloat(budget);
        if (Number.isFinite(budgetMajor) && budgetMajor > 0) {
            brief.budget_daily_minor = Math.round(budgetMajor * 100);
        }
        if (geo.trim()) {
            brief.geo = geo
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean);
        }
        if (audience.trim()) {
            brief.audience = { description: audience.trim() };
        }
        try {
            await proposeCampaign(brief);
            toast(`${name.trim()} drafted — review and approve it to go live`);
            setName("");
            setGeo("");
            setAudience("");
            setBudget("");
            onProposed();
        } catch (e2) {
            toast(e2 instanceof Error ? e2.message : "Draft failed", "error");
        } finally {
            setSaving(false);
        }
    }

    return (
        <form onSubmit={submit} className="space-y-4">
            <div className="text-h6 text-t-primary">Draft a campaign</div>
            {disabled && (
                <div className="p-3 rounded-2xl border border-s-subtle bg-b-surface2 text-caption text-t-secondary">
                    The backend isn’t live yet — drafts are accepted once the Ads engine is provisioned on
                    the server. In dry-run nothing can spend.
                </div>
            )}
            <div>
                <label className="block text-button mb-3 text-t-primary">Campaign name / product</label>
                <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Diwali offer — 2BHK Gurgaon"
                    className={inputCls}
                    required
                />
            </div>
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <label className="block text-button mb-3 text-t-primary">Objective</label>
                    <select
                        value={objective}
                        onChange={(e) => setObjective(e.target.value as AdsObjective)}
                        className={selectCls}
                    >
                        {ADS_OBJECTIVES.map((o) => (
                            <option key={o} value={o}>
                                {o.charAt(0).toUpperCase() + o.slice(1)}
                            </option>
                        ))}
                    </select>
                </div>
                <div>
                    <label className="block text-button mb-3 text-t-primary">
                        Daily budget ({currency === "INR" ? "₹" : currency})
                    </label>
                    <input
                        type="number"
                        min="0"
                        step="1"
                        value={budget}
                        onChange={(e) => setBudget(e.target.value)}
                        placeholder="1500"
                        className={inputCls}
                    />
                </div>
            </div>
            <div>
                <label className="block text-button mb-3 text-t-primary">Locations</label>
                <input
                    type="text"
                    value={geo}
                    onChange={(e) => setGeo(e.target.value)}
                    placeholder="Gurgaon, Delhi NCR"
                    className={inputCls}
                />
                <p className="text-caption text-t-tertiary mt-2">Comma-separated.</p>
            </div>
            <div>
                <label className="block text-button mb-3 text-t-primary">Audience</label>
                <input
                    type="text"
                    value={audience}
                    onChange={(e) => setAudience(e.target.value)}
                    placeholder="Home buyers, 28–45, ready to move"
                    className={inputCls}
                />
            </div>
            <div>
                <label className="block text-button mb-3 text-t-primary">
                    Creative variants — {variants}
                </label>
                <input
                    type="range"
                    min={1}
                    max={5}
                    value={variants}
                    onChange={(e) => setVariants(parseInt(e.target.value, 10))}
                    className="w-full accent-primary-01"
                />
                <p className="text-caption text-t-tertiary mt-2">
                    The optimizer tests these, scales the winner and kills the losers.
                </p>
            </div>
            <p className="text-caption text-t-tertiary">
                The budget is clamped to your hard cap. The draft is parked at
                <span className="text-t-secondary"> awaiting approval</span> — nothing spends until you
                sign off.
            </p>
            <Button isBlack className="w-full justify-center" disabled={saving}>
                {saving ? "Drafting…" : "Draft campaign"}
            </Button>
        </form>
    );
}

/* -------------------------------------------------------------- pause modal */

function PauseModal({
    target,
    busy,
    onClose,
    onConfirm,
}: {
    target: AdsCampaign | null;
    busy: boolean;
    onClose: () => void;
    onConfirm: (reason: string) => void;
}) {
    const [reason, setReason] = useState("");

    return (
        <Modal open={!!target} onClose={onClose}>
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    onConfirm(reason.trim());
                }}
                className="space-y-4"
            >
                <div className="text-h6 text-t-primary">Pause campaign</div>
                <p className="text-body-2 text-t-secondary">
                    Spend stops immediately on <span className="text-t-primary">{target?.name}</span>. Add a
                    reason so the audit log shows why it was paused.
                </p>
                <div>
                    <label className="block text-button mb-3 text-t-primary">Reason (optional)</label>
                    <input
                        type="text"
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="CPL above target this week"
                        className="input-base w-full h-11 px-4 rounded-2xl text-body-2"
                        autoFocus
                    />
                </div>
                <div className="flex items-center gap-3 pt-1">
                    <Button isStroke className="flex-1 justify-center" type="button" onClick={onClose}>
                        Keep running
                    </Button>
                    <Button isBlack className="flex-1 justify-center" disabled={busy}>
                        {busy ? "Pausing…" : "Pause campaign"}
                    </Button>
                </div>
            </form>
        </Modal>
    );
}
