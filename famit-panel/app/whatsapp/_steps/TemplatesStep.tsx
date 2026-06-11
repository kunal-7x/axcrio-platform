// ③ AI TEMPLATE GENERATION (PromotePage Insights + List archetype). On entry it
// fires the LLM → 3–5 AI suggestion cards (copy/CTA/angle/tokens/media-rec).
// While generating, the §6-PHASE2 dot-matrix GenerationLoader runs (NOT a spinner).
//
// THREE outcomes (the fix — a 200-with-no-templates is a REAL failure the founder
// must SEE, never a silent blank grid or a false "Coming Soon"):
//   • route truly absent (404/503/network)   → premium ComingSoon + manual path.
//   • engine ran but failed (no credits/empty) → a real error panel: the reason,
//                                                 a Retry, a Top-up link, AND the
//                                                 always-available manual path.
//   • templates returned                       → AI suggestion cards.
// A "Write one manually" affordance is ALWAYS present so the founder can create a
// template by hand at any moment (Preview step — the LIVE free-text authoring path).

"use client";

import { useCallback, useEffect, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import GenerationLoader, { type GenerationLoaderState } from "@/components/GenerationLoader";
import AiSuggestionCard from "../_components/AiSuggestionCard";
import ComingSoon from "../_components/ComingSoon";
import NoInventNote from "../_components/NoInventNote";
import { generateTemplates, submitTemplateToMeta, type MetaReview } from "../_lib/waapi";
import { type StepCtx, type TemplateSuggestion } from "../_lib/types";

// A small inline panel for the "engine ran but produced nothing" case (real
// failure — credits/empty/model error). NOT the dormant ComingSoon card.
function GenFailurePanel({
    message,
    errorCode,
    onRetry,
    onManual,
}: {
    message: string;
    errorCode?: string;
    onRetry: () => void;
    onManual: () => void;
}) {
    const needsCredits = errorCode === "insufficient_credits";
    return (
        <Card title="AI template generation">
            <div className="flex flex-col items-center text-center px-5 py-12 max-lg:px-3 max-md:py-9">
                <div className="flex justify-center items-center size-16 mb-5 rounded-full bg-b-surface1 ring-1 ring-s-stroke2">
                    <Icon
                        className="fill-primary-05 !size-7"
                        name={needsCredits ? "wallet" : "info"}
                    />
                </div>
                <div className="text-h6 text-t-primary">
                    {needsCredits ? "Add credits to generate" : "Couldn’t generate templates"}
                </div>
                <div className="mt-2 max-w-110 text-body-2 text-t-secondary">{message}</div>
                <div className="flex flex-wrap justify-center gap-3 mt-7">
                    {needsCredits && (
                        <Button as="link" href="/billing/overview" isBlack icon="wallet">
                            Top up wallet
                        </Button>
                    )}
                    <Button isStroke icon="magic-pencil" onClick={onRetry}>
                        Try again
                    </Button>
                    <Button isStroke icon="edit" onClick={onManual}>
                        Write one manually
                    </Button>
                </div>
            </div>
        </Card>
    );
}

export default function TemplatesStep({ campaign, context, draft, setDraft, goTo, notify }: StepCtx) {
    const [phase, setPhase] = useState<"idle" | "loading" | "ready" | "dormant" | "failed">("idle");
    const [loaderState, setLoaderState] = useState<GenerationLoaderState>("loading");
    const [suggestions, setSuggestions] = useState<TemplateSuggestion[]>([]);
    const [rationale, setRationale] = useState<string>("");
    const [partial, setPartial] = useState(false);
    const [failure, setFailure] = useState<{ message: string; errorCode?: string }>({ message: "" });
    // per-card Meta review + in-flight submit (keyed by template_id)
    const [reviewMap, setReviewMap] = useState<Record<string, MetaReview>>({});
    const [submittingId, setSubmittingId] = useState<string>("");

    const run = useCallback(async () => {
        setPhase("loading");
        setLoaderState("loading");
        const r = await generateTemplates({
            campaign_id: campaign?.id,
            objective: context.goal,
            audience: context.audience,
            language: draft.language,
        });
        // route truly absent on this box → dormant (premium coming-soon + manual)
        if (!r.configured) {
            setPhase("dormant");
            return;
        }
        // engine RAN but produced no usable templates (credits/empty/model error)
        // → surface the real reason, NOT a blank grid or a fake coming-soon.
        if (!r.ok) {
            setFailure({ message: r.message || "The AI couldn’t generate templates right now.", errorCode: r.errorCode });
            setPhase("failed");
            return;
        }
        setSuggestions(r.suggestions);
        setRationale(r.rationale || "");
        setPartial(!!r.partial);
        setLoaderState("completed");
    }, [campaign?.id, context.goal, context.audience, draft.language]);

    // auto-generate on entry when a campaign is chosen
    useEffect(() => {
        if (campaign && phase === "idle") run();
    }, [campaign, phase, run]);

    const use = (s: TemplateSuggestion) => {
        setDraft({
            name: s.name,
            body: s.body,
            cta: s.cta,
            angle: s.angle,
            language: s.language || draft.language,
            campaign_id: campaign?.id,
            // carry the persisted row id so Preview/Approval can submit THIS
            // template to Meta (approve → submit-to-meta → poll status).
            template_id: s.template_id,
            meta_template_status: "none",
        });
        notify("Template applied — review and refine it next", "success");
        goTo("preview");
    };

    // Submit THIS suggestion's persisted row to Meta directly (approve → submit).
    // Dormant-safe: a not-connected backend shows a toast, never an error wall.
    const submitMeta = async (s: TemplateSuggestion) => {
        if (!s.template_id) {
            notify("Open this template and submit it from the Approval step", "error");
            return;
        }
        setSubmittingId(s.template_id);
        const r = await submitTemplateToMeta({ templateId: s.template_id });
        setSubmittingId("");
        if (!r.configured) {
            notify("WhatsApp isn’t connected on this account yet", "error");
            return;
        }
        if (r.submitted) {
            setReviewMap((m) => ({ ...m, [s.template_id!]: r.review }));
            notify("Sent to Meta for review", "success");
        } else {
            notify(r.message || "Couldn’t submit to Meta right now", "error");
        }
    };

    // Seed a blank manual draft (keeps any chosen language) and jump to the
    // free-text authoring surface (Preview), where Meta-compliance is shown live.
    const writeManually = () => {
        setDraft({
            name: draft.name || "Untitled template",
            campaign_id: campaign?.id,
        });
        notify("Compose your template — the live preview and Meta check update as you type", "success");
        goTo("preview");
    };

    if (!campaign) {
        return (
            <Card title="AI template generation">
                <div className="px-5 py-14 text-center text-body-2 text-t-secondary max-lg:px-3">
                    Select a campaign first — the AI writes templates from its data.
                    <div className="mt-5 flex flex-wrap justify-center gap-3">
                        <Button isStroke onClick={() => goTo("campaign")}>Choose campaign</Button>
                        <Button isStroke icon="edit" onClick={() => goTo("preview")}>Write one manually</Button>
                    </div>
                </div>
            </Card>
        );
    }

    if (phase === "dormant") {
        return (
            <ComingSoon
                title="AI template generation"
                body="Connect the language engine and the AI auto-writes 3–5 WhatsApp templates — copy, CTA, marketing angle and personalization tokens — from this campaign's real data."
                fallbackLabel="Write one manually"
                onFallback={writeManually}
            />
        );
    }

    if (phase === "failed") {
        return (
            <GenFailurePanel
                message={failure.message}
                errorCode={failure.errorCode}
                onRetry={() => setPhase("idle")}
                onManual={writeManually}
            />
        );
    }

    if (phase === "loading") {
        return (
            <Card title="AI template generation">
                <div className="p-3">
                    <GenerationLoader
                        title="Writing your templates"
                        label="Thinking"
                        statusLines={[
                            "Understanding campaign",
                            "Writing the message",
                            "Designing the CTA",
                            "Finalizing",
                        ]}
                        state={loaderState}
                        onCompleted={() => setPhase("ready")}
                    />
                </div>
            </Card>
        );
    }

    return (
        <Card
            title="AI template suggestions"
            headContent={
                <div className="flex flex-wrap gap-2">
                    <Button isStroke icon="edit" onClick={writeManually}>
                        Write one manually
                    </Button>
                    <Button isStroke icon="magic-pencil" onClick={() => { setPhase("idle"); }}>
                        Regenerate all
                    </Button>
                </div>
            }
        >
            <div className="px-5 pb-5 pt-1 flex flex-col gap-4 max-lg:px-3">
                {partial && (
                    <div className="flex items-start gap-2.5 p-3.5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle text-body-2 text-t-secondary">
                        <Icon className="shrink-0 mt-px fill-primary-05 !size-4" name="info" />
                        <span>
                            We wrote these from your campaign — a couple were finished with our
                            built-in copywriter rather than the AI. They’re ready to use; refine any of them next.
                        </span>
                    </div>
                )}
                {rationale && (
                    <div className="flex items-start gap-2.5 p-3.5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle text-body-2 text-t-secondary">
                        <Icon className="shrink-0 mt-px fill-primary-01 !size-4" name="magic-pencil" />
                        <span>{rationale}</span>
                    </div>
                )}
                <NoInventNote />
                <div className="grid grid-cols-2 gap-4 max-lg:grid-cols-1">
                    {suggestions.map((s) => (
                        <AiSuggestionCard
                            key={s.id}
                            suggestion={s}
                            onUse={() => use(s)}
                            onRegenerate={() => setPhase("idle")}
                            onSubmitMeta={s.template_id ? () => submitMeta(s) : undefined}
                            submitting={!!s.template_id && submittingId === s.template_id}
                            review={(s.template_id && reviewMap[s.template_id]) || "none"}
                        />
                    ))}
                </div>
            </div>
        </Card>
    );
}
