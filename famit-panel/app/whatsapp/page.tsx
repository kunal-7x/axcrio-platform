// WhatsApp Campaign Builder — the premium 11-step campaign WORKSPACE.
// ONE route /whatsapp driven by a horizontal STEP RAIL (Tabs stepper) over the
// 11-step pipeline (design/wa-builder-frontend.md). Replaces the old 2-card form.
//
// LIVE today: Launchpad · Campaign · Preview · Audience · Schedule(send-now) ·
//   Delivery (all via /api/whatsapp/*, /api/campaigns, /api/leads).
// DORMANT-SAFE (premium coming-soon on 404/503): AI Templates · Creative ·
//   Banner Studio · Approval(asset) · Analytics — until the parallel
//   whatsapp-builder + creative-attach backend wave lands.
//
// Reuse-first: Layout(single title) + Tabs rail + already-ported Card/Table/
//   KpiCard/CardChartPie/Modal/Field/Select. Inter Display, zero raw hex.

"use client";

import { useCallback, useMemo, useState } from "react";
import Layout from "@/components/Layout";
import Icon from "@/components/Icon";
import { useMe, canWrite } from "@/lib/auth";
import { type Campaign } from "@/lib/api";

import {
    STEPS,
    EMPTY_DRAFT,
    type StepKey,
    type TemplateDraft,
    type CampaignContext,
    type StepCtx,
} from "./_lib/types";

import LaunchpadStep from "./_steps/LaunchpadStep";
import CampaignStep from "./_steps/CampaignStep";
import TemplatesStep from "./_steps/TemplatesStep";
import CreativeStep from "./_steps/CreativeStep";
import BannerStep from "./_steps/BannerStep";
import PreviewStep from "./_steps/PreviewStep";
import ApprovalStep from "./_steps/ApprovalStep";
import AudienceStep from "./_steps/AudienceStep";
import ScheduleStep from "./_steps/ScheduleStep";
import DeliveryStep from "./_steps/DeliveryStep";
import AnalyticsStep from "./_steps/AnalyticsStep";

type Toast = { msg: string; type: "success" | "error" };

const STEP_COMPONENTS: Record<StepKey, React.ComponentType<StepCtx>> = {
    launchpad: LaunchpadStep,
    campaign: CampaignStep,
    templates: TemplatesStep,
    creative: CreativeStep,
    banner: BannerStep,
    preview: PreviewStep,
    approval: ApprovalStep,
    audience: AudienceStep,
    schedule: ScheduleStep,
    delivery: DeliveryStep,
    analytics: AnalyticsStep,
};

export default function WhatsAppPage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [active, setActive] = useState<StepKey>("launchpad");
    const [campaign, setCampaignState] = useState<Campaign | null>(null);
    const [context, setContext] = useState<CampaignContext>({});
    const [draft, setDraftState] = useState<TemplateDraft>(EMPTY_DRAFT);
    const [toast, setToast] = useState<Toast | null>(null);

    const notify = useCallback((msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    }, []);

    const setDraft = useCallback((patch: Partial<TemplateDraft>) => {
        setDraftState((prev) => ({ ...prev, ...patch }));
    }, []);

    const setCampaign = useCallback((c: Campaign | null, ctx: CampaignContext) => {
        setCampaignState(c);
        setContext(ctx);
        setDraftState((prev) => ({ ...prev, campaign_id: c?.id }));
    }, []);

    const goTo = useCallback((key: StepKey) => {
        setActive(key);
        if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
    }, []);

    const ctx: StepCtx = useMemo(
        () => ({ campaign, context, draft, writable, setDraft, setCampaign, goTo, notify }),
        [campaign, context, draft, writable, setDraft, setCampaign, goTo, notify]
    );

    const ActiveStep = STEP_COMPONENTS[active];
    const activeIndex = STEPS.findIndex((s) => s.key === active);

    return (
        <Layout title="WhatsApp campaigns">
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">
                        ×
                    </button>
                </div>
            )}

            {/* STEP RAIL — horizontal, scrollable Tabs stepper */}
            <div className="card !p-0 mb-3 overflow-hidden">
                <div className="flex items-center gap-1 px-3 py-2.5 overflow-x-auto scrollbar-none">
                    {STEPS.map((s, i) => {
                        const isActive = s.key === active;
                        const done = i < activeIndex;
                        return (
                            <button
                                key={s.key}
                                onClick={() => goTo(s.key)}
                                className={`group flex items-center gap-2 shrink-0 h-10 pl-2.5 pr-4 rounded-full border text-button transition-colors ${
                                    isActive
                                        ? "border-s-stroke2 text-t-primary"
                                        : "border-transparent text-t-secondary hover:text-t-primary"
                                }`}
                            >
                                <span
                                    className={`flex justify-center items-center size-6 shrink-0 rounded-full text-caption tabular-nums transition-colors ${
                                        isActive
                                            ? "bg-shade-01 text-shade-10 dark:bg-shade-10 dark:text-shade-01"
                                            : done
                                            ? "bg-b-surface2 text-t-secondary"
                                            : "bg-b-surface2 text-t-tertiary"
                                    }`}
                                >
                                    {done ? <Icon className="fill-primary-02 !size-3.5" name="check" /> : i + 1}
                                </span>
                                {s.name}
                                {!s.live && (
                                    <span className="size-1.5 rounded-full bg-primary-05" title="Activates when the engine is connected" />
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* STEP BODY */}
            <ActiveStep {...ctx} />
        </Layout>
    );
}
