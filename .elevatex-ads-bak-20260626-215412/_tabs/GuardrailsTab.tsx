"use client";

// Ad-Engine · Guardrails tab — caps / circuit-breaker / approval-gate config.
//
// LIFTED VERBATIM from the inline `Overview` Configuration widgets that lived in
// app/ads/page.tsx (the "Configuration" `Card` + `ConfigRow` + the "How your
// spend is protected" `GuardCard` board) and GROWN to the FRONTEND_ARCHITECTURE
// §8 spec: the EDITABLE caps / breaker / approval form on top of that read-only
// board.
//   • Spend cap — a MAJOR-money `Field` (→ `*100` minor) + a live spend-vs-cap
//     `.meter`; org + per-account caps too.
//   • CPL circuit-breaker — a threshold `Field` + an on/off `Switch` + the
//     current CPL echoed back live.
//   • Anomaly breaker — a read-only warm-up / armed `Badge` (server-owned).
//   • Approval gate — a `Switch` ("Require step-up for spend-increasing moves").
//   • No-tracking gate — its current state.
//   • A single "Save changes" `Button isBlack` (gated `writable` + step-up PIN)
//     → audited mutation → toast "Guardrails saved".
//
// Data via getAdsGuardrails / saveAdsGuardrails (../_lib); the read is dormant-
// safe (404 → DormantPanel, never an error wall). A 30s visibility-gated poll
// (useRealtimeRefresh) keeps the live cap / breaker / current-CPL state fresh.
// Shared widgets/maps come from ../_shared; zero raw hex — tokens only.
//
// NOTE on props: page.tsx renders this tab as
//   <GuardrailsTab hc health loading currency />
// (no writable / toast) and the Spine owns page.tsx, so this file does NOT widen
// that call. The writable gate is derived in-tab from useMe()/canWrite(me) and
// the save feedback uses a small in-tab toast — mirroring how the page itself
// gates and toasts, so the editable surface stays self-contained.

import { useCallback, useEffect, useMemo, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Switch from "@/components/Switch";
import { useMe, canWrite } from "@/lib/auth";
import {
    getAdsGuardrails,
    saveAdsGuardrails,
    useRealtimeRefresh,
    fmtMoney,
    type AdsGuardrails,
    type AdsHealth,
    type ReadResult,
} from "../_lib";
import { ConfigRow, GuardCard } from "../_shared";

export type GuardrailsTabProps = {
    hc: AdsHealth | null;
    health: ReadResult<AdsHealth> | null;
    loading: boolean;
    currency: string;
};

// The editable form state — MAJOR currency strings for the money inputs (the
// engine meters in minor/paise; we convert on save), booleans for the toggles.
type FormState = {
    dailyCap: string; // MAJOR
    orgDailyCap: string; // MAJOR
    perAccountCap: string; // MAJOR
    cplMax: string; // MAJOR
    cplBreakerOn: boolean;
    requireApproval: boolean;
};

// minor (paise) → a MAJOR string for an input (empty when unset/zero).
function minorToMajorStr(minor?: number | null): string {
    if (minor === null || minor === undefined || minor <= 0) return "";
    return String(minor / 100);
}

// a MAJOR input string → minor (paise); blank/NaN/≤0 → 0 (server reads 0 = unset).
function majorStrToMinor(major: string): number {
    const v = parseFloat(major);
    return Number.isFinite(v) && v > 0 ? Math.round(v * 100) : 0;
}

function formFrom(g: AdsGuardrails): FormState {
    return {
        dailyCap: minorToMajorStr(g.daily_cap_minor),
        orgDailyCap: minorToMajorStr(g.org_daily_cap_minor),
        perAccountCap: minorToMajorStr(g.per_account_cap_minor),
        cplMax: minorToMajorStr(g.cpl_max_minor),
        cplBreakerOn: !!g.cpl_breaker_on,
        requireApproval: !!g.require_approval,
    };
}

export default function GuardrailsTab({ hc, health, loading, currency }: GuardrailsTabProps) {
    const { me } = useMe();
    const writable = canWrite(me);

    // ---- guardrails read (dormant-safe) + 30s visibility-gated poll ----
    const [res, setRes] = useState<ReadResult<AdsGuardrails> | null>(null);
    const [gLoading, setGLoading] = useState(true);
    const load = useCallback(() => {
        setGLoading(true);
        getAdsGuardrails()
            .then(setRes)
            .finally(() => setGLoading(false));
    }, []);
    useEffect(() => {
        load();
    }, [load]);
    useRealtimeRefresh(load, 30000);

    const g = res?.kind === "ok" ? res.data : null;
    // The guardrails read is the source of truth; fall back to the health caps so
    // the read-only board still shows real numbers while the dedicated route is
    // dormant. NEVER an error wall — a non-200 here degrades to the board below.
    const dormant = res?.kind === "dormant";
    const readError = res?.kind === "error" ? res.message : "";
    const cur = g?.currency || currency;

    // ---- editable form state, seeded from the server, dirty-tracked ----
    const [form, setForm] = useState<FormState | null>(null);
    const [saving, setSaving] = useState(false);
    const [toast, setToast] = useState<{ msg: string; type: "success" | "error" } | null>(null);
    const showToast = useCallback((msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4600);
    }, []);

    // Seed the form once we have real guardrails; re-seed when the server values
    // change (a poll) only if the user hasn't started editing (no local form).
    useEffect(() => {
        if (g && !form) setForm(formFrom(g));
    }, [g, form]);

    const dirty = useMemo(() => {
        if (!g || !form) return false;
        const base = formFrom(g);
        return (
            base.dailyCap !== form.dailyCap ||
            base.orgDailyCap !== form.orgDailyCap ||
            base.perAccountCap !== form.perAccountCap ||
            base.cplMax !== form.cplMax ||
            base.cplBreakerOn !== form.cplBreakerOn ||
            base.requireApproval !== form.requireApproval
        );
    }, [g, form]);

    const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
        setForm((f) => (f ? { ...f, [k]: v } : f));

    // live spend-vs-cap meter (paise). Cap is the configured daily cap (or org).
    const liveDailyCap = g?.daily_cap_minor ?? hc?.caps.daily_cap_minor ?? 0;
    const realSpend = g?.spend_today_minor ?? 0;
    const capPct =
        liveDailyCap > 0 ? Math.min(100, Math.round((realSpend / liveDailyCap) * 100)) : 0;
    const breaker = capPct >= 100;
    const currentCpl = g?.current_cpl_minor ?? null;
    const noTrackingOn = !!g?.no_tracking_gate;
    const anomalyOn = g?.anomaly_breaker_on;

    async function save() {
        if (!form) return;
        setSaving(true);
        try {
            const body: Partial<AdsGuardrails> = {
                daily_cap_minor: majorStrToMinor(form.dailyCap),
                org_daily_cap_minor: majorStrToMinor(form.orgDailyCap),
                per_account_cap_minor: majorStrToMinor(form.perAccountCap),
                cpl_max_minor: majorStrToMinor(form.cplMax),
                cpl_breaker_on: form.cplBreakerOn,
                require_approval: form.requireApproval,
            };
            // Spend-mutating → step-up gated. No step-up token seam yet, so the
            // backend's fail-closed gate may 403 — surfaced honestly as the
            // friendly "needs a step-up PIN" copy from _lib's write() handler.
            const out = await saveAdsGuardrails(body);
            if (out?.guardrails) {
                setRes({ kind: "ok", data: out.guardrails });
                setForm(formFrom(out.guardrails));
            }
            showToast("Guardrails saved");
            load();
        } catch (e) {
            showToast(e instanceof Error ? e.message : "Save failed", "error");
        } finally {
            setSaving(false);
        }
    }

    const moneyInputCls = "tabular-nums";
    const showSkeleton = (loading || gLoading) && !g && !dormant && !readError;

    return (
        <div className="space-y-3">
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button
                        onClick={() => setToast(null)}
                        className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none"
                    >
                        ×
                    </button>
                </div>
            )}

            {/* ---- Editable guardrails form (caps / breaker / approval) ---- */}
            <Card
                title="Guardrails"
                classHead="pr-5 max-lg:pr-3"
                headContent={
                    <div className="flex items-center gap-3">
                        <span className="inline-flex items-center gap-1.5 text-caption text-t-tertiary max-sm:hidden">
                            <Icon name="lock" className="size-3.5 fill-t-tertiary" />
                            Audited · step-up gated
                        </span>
                        {writable && !dormant && !readError && (
                            <Button
                                isBlack
                                className="h-9 !px-4 text-button"
                                onClick={save}
                                disabled={saving || !dirty || !form}
                                title="Saving spend guardrails is step-up gated and may require a PIN"
                            >
                                <Icon name="check-circle" className="size-4 fill-inherit" />
                                {saving ? "Saving…" : "Save changes"}
                            </Button>
                        )}
                    </div>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {showSkeleton ? (
                        <div className="space-y-4">
                            {[...Array(4)].map((_, i) => (
                                <div key={i} className="space-y-2">
                                    <div className="skeleton h-4 w-44" />
                                    <div className="skeleton h-12 w-full rounded-full" />
                                </div>
                            ))}
                        </div>
                    ) : dormant ? (
                        // Route not mounted yet — degrade to the read-only board below,
                        // with an honest "warming up" note. NEVER an error wall.
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="filters" className="fill-inherit" />
                            </span>
                            <div className="state-title">Guardrails warming up</div>
                            <div className="state-sub max-w-md mx-auto">
                                Connect a Meta or Google account to set live spend caps and the cost-per-lead
                                breaker here. Your protections — shown below — are already enforced server-side
                                in dry-run.
                            </div>
                        </div>
                    ) : readError ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="info" className="fill-inherit" />
                            </span>
                            <div className="state-title">Couldn’t load guardrails</div>
                            <div className="state-sub">{readError}</div>
                            <Button isStroke className="h-9 !px-4 text-button mt-1" onClick={load}>
                                <Icon name="clock" className="size-4 fill-inherit" />
                                Try again
                            </Button>
                        </div>
                    ) : form ? (
                        <div className="grid grid-cols-2 gap-x-6 gap-y-6 max-md:grid-cols-1">
                            {/* Daily spend cap + live spend meter */}
                            <div>
                                <Field
                                    label={`Daily spend cap (${cur === "INR" ? "₹" : cur})`}
                                    tooltip="The most this account can spend in a day. Spend is metered live and any campaign at or over the cap is paused."
                                    type="number"
                                    min="0"
                                    step="1"
                                    placeholder="5000"
                                    classInput={moneyInputCls}
                                    value={form.dailyCap}
                                    disabled={!writable}
                                    onChange={(e) => set("dailyCap", e.target.value)}
                                />
                                <div className="mt-3 flex items-center justify-between text-caption">
                                    <span className="text-t-tertiary">Spent today</span>
                                    <span className="text-t-secondary tabular-nums">
                                        {fmtMoney(realSpend, cur)}
                                        <span className="text-t-tertiary">
                                            {" "}
                                            / {liveDailyCap > 0 ? fmtMoney(liveDailyCap, cur) : "—"}
                                        </span>
                                    </span>
                                </div>
                                {liveDailyCap > 0 && (
                                    <div className="meter mt-2">
                                        <div
                                            className="meter-fill"
                                            style={{
                                                width: `${capPct}%`,
                                                background: breaker
                                                    ? "var(--primary-03)"
                                                    : capPct >= 90
                                                    ? "var(--primary-05)"
                                                    : "var(--primary-02)",
                                            }}
                                        />
                                    </div>
                                )}
                            </div>

                            {/* Org-wide daily cap */}
                            <div>
                                <Field
                                    label={`Org-wide daily cap (${cur === "INR" ? "₹" : cur})`}
                                    tooltip="A ceiling across every ad account in your org, on top of the per-account daily cap."
                                    type="number"
                                    min="0"
                                    step="1"
                                    placeholder="20000"
                                    classInput={moneyInputCls}
                                    value={form.orgDailyCap}
                                    disabled={!writable}
                                    onChange={(e) => set("orgDailyCap", e.target.value)}
                                />
                                <p className="text-caption text-t-tertiary mt-3">
                                    Caps the combined daily spend of all accounts.
                                </p>
                            </div>

                            {/* Per-account cap */}
                            <div>
                                <Field
                                    label={`Per-account daily cap (${cur === "INR" ? "₹" : cur})`}
                                    tooltip="The default daily cap applied to each connected ad account unless overridden on a campaign."
                                    type="number"
                                    min="0"
                                    step="1"
                                    placeholder="5000"
                                    classInput={moneyInputCls}
                                    value={form.perAccountCap}
                                    disabled={!writable}
                                    onChange={(e) => set("perAccountCap", e.target.value)}
                                />
                                <p className="text-caption text-t-tertiary mt-3">
                                    Leave blank to use the daily spend cap.
                                </p>
                            </div>

                            {/* CPL circuit-breaker: threshold + switch + current CPL */}
                            <div>
                                <Field
                                    label={`Cost-per-lead breaker (${cur === "INR" ? "₹" : cur})`}
                                    tooltip="If a campaign’s cost-per-lead blows past this — once it has enough conversions to be sure — the breaker pauses it."
                                    type="number"
                                    min="0"
                                    step="1"
                                    placeholder="400"
                                    classInput={moneyInputCls}
                                    value={form.cplMax}
                                    disabled={!writable || !form.cplBreakerOn}
                                    onChange={(e) => set("cplMax", e.target.value)}
                                />
                                <div className="mt-3 flex items-center justify-between gap-4">
                                    <div className="min-w-0">
                                        <div className="text-body-2 text-t-primary">Breaker armed</div>
                                        <div className="text-caption text-t-tertiary">
                                            Current CPL{" "}
                                            <span className="text-t-secondary tabular-nums">
                                                {currentCpl != null ? fmtMoney(currentCpl, cur) : "—"}
                                            </span>
                                        </div>
                                    </div>
                                    <Switch
                                        checked={form.cplBreakerOn}
                                        onChange={(v) => writable && set("cplBreakerOn", v)}
                                    />
                                </div>
                            </div>

                            {/* Anomaly breaker — read-only server-owned state */}
                            <div className="flex items-start justify-between gap-4">
                                <div className="min-w-0">
                                    <div className="text-body-2 text-t-primary">Anomaly breaker</div>
                                    <div className="text-caption text-t-tertiary max-w-xs">
                                        Watches for sudden spend or CPL spikes and pauses the offender. It learns
                                        a baseline first — it won’t fire on a tiny sample.
                                    </div>
                                </div>
                                <Badge
                                    variant={anomalyOn === true ? "success" : "info"}
                                    dot={anomalyOn === true}
                                >
                                    {anomalyOn === true ? "Armed" : "Warming up"}
                                </Badge>
                            </div>

                            {/* Approval gate — step-up on spend-increasing moves */}
                            <div className="flex items-start justify-between gap-4">
                                <div className="min-w-0">
                                    <div className="text-body-2 text-t-primary">
                                        Require step-up for spend-increasing moves
                                    </div>
                                    <div className="text-caption text-t-tertiary max-w-xs">
                                        Any move that raises spend — activate, scale, raise a cap — needs a human
                                        step-up PIN. Spend-neutral and spend-lowering moves stay one-tap.
                                    </div>
                                </div>
                                <Switch
                                    checked={form.requireApproval}
                                    onChange={(v) => writable && set("requireApproval", v)}
                                />
                            </div>

                            {/* No-tracking gate — current state */}
                            <div className="flex items-start justify-between gap-4">
                                <div className="min-w-0">
                                    <div className="text-body-2 text-t-primary">No-tracking gate</div>
                                    <div className="text-caption text-t-tertiary max-w-xs">
                                        Blocks spend on any campaign with no conversion tracking, so you never pay
                                        for leads you can’t measure.
                                    </div>
                                </div>
                                <Badge variant={noTrackingOn ? "success" : "neutral"} dot={noTrackingOn}>
                                    {noTrackingOn ? "Enforced" : "Off"}
                                </Badge>
                            </div>
                        </div>
                    ) : null}

                    {!writable && !dormant && !readError && form && (
                        <p className="text-caption text-t-tertiary mt-5">
                            You have read-only access — ask an admin or manager to change these guardrails.
                        </p>
                    )}
                </div>
            </Card>

            {/* ---- Read-only configuration board (every dependency, surfaced honestly) ---- */}
            <Card
                title="Configuration"
                headContent={
                    <span className="ml-3 inline-flex items-center gap-1.5 text-caption text-t-tertiary">
                        <Icon name="cube" className="size-3.5 fill-t-tertiary" />
                        Server-side · dormant until creds
                    </span>
                }
            >
                <div className="px-5 pb-5 max-lg:px-3">
                    {loading && !hc ? (
                        <div className="space-y-3">
                            {[...Array(5)].map((_, i) => (
                                <div key={i} className="flex items-center justify-between">
                                    <div className="skeleton h-4 w-40" />
                                    <div className="skeleton h-5 w-24" />
                                </div>
                            ))}
                        </div>
                    ) : health?.kind === "error" ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="info" className="fill-inherit" />
                            </span>
                            <div className="state-title">Could not load configuration</div>
                            <div className="state-sub">{health.message}</div>
                        </div>
                    ) : (
                        <div className="divide-y divide-s-subtle">
                            <ConfigRow icon="facebook" label="Meta Ads" hint="Facebook & Instagram Marketing API">
                                {hc?.providers.meta === "configured" ? (
                                    <Badge variant="success" dot>
                                        Connected
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Not configured</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow icon="earth" label="Google Ads" hint="Search & display via the Google Ads API">
                                {hc?.providers.google === "configured" ? (
                                    <Badge variant="success" dot>
                                        Connected
                                    </Badge>
                                ) : (
                                    <Badge variant="neutral">Not configured</Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow icon="wallet" label="Spend mode" hint="Whether real money can move">
                                {hc?.dry_run ? (
                                    <Badge variant="info" dot>
                                        Dry-run (safe)
                                    </Badge>
                                ) : (
                                    <Badge variant="warning" dot>
                                        Live spend
                                    </Badge>
                                )}
                            </ConfigRow>
                            <ConfigRow icon="lock" label="Approval gate" hint="Human step-up before activation">
                                <Badge variant={hc?.require_approval ? "success" : "neutral"} dot={hc?.require_approval}>
                                    {hc?.require_approval ? "Required" : "Off"}
                                </Badge>
                            </ConfigRow>
                            <ConfigRow icon="usd-circle" label="Hard daily cap" hint="The real spend floor, set on the platform">
                                <span className="text-body-2 text-t-primary tabular-nums">
                                    {(hc?.caps.daily_cap_minor ?? 0) > 0
                                        ? fmtMoney(hc?.caps.daily_cap_minor, cur)
                                        : "Not set"}
                                </span>
                            </ConfigRow>
                        </div>
                    )}
                </div>
            </Card>

            {/* The defense-in-depth guardrails, told as a board */}
            <Card title="How your spend is protected">
                <div className="px-5 pb-5 max-lg:px-3 grid grid-cols-2 gap-3 max-md:grid-cols-1">
                    <GuardCard
                        icon="usd-circle"
                        title="Platform hard cap"
                        body="A daily budget set ≤ your cap at create-time. Meta and Google will not spend past it — the strongest, on-platform floor."
                    />
                    <GuardCard
                        icon="clock"
                        title="Polling breaker"
                        body={`Every ${hc?.caps.poll_minutes ?? g?.poll_minutes ?? 30} minutes the engine pulls live spend and pauses any campaign at or over its cap.`}
                    />
                    <GuardCard
                        icon="arrow-percent"
                        title="CPL breaker"
                        body={`Pauses a campaign whose cost-per-lead blows the target — only once it has ≥ ${hc?.caps.cpl_min_conversions ?? 15} conversions, never on a tiny sample.`}
                    />
                    <GuardCard
                        icon="lock"
                        title="Approval + audit"
                        body="Nothing activates without a human step-up, and every propose, approve and pause is written to an immutable ledger."
                    />
                </div>
            </Card>
        </div>
    );
}
