// ⑦ APPROVAL — the content-policy gate (two gates, in order). A review card +
// a creative-quality checklist, then (a) asset-approval (creative.approve) and
// (b) the LIVE Submit-to-Meta gate: approve (builder) → submit-to-Meta → poll the
// real PENDING/APPROVED/REJECTED review state. Meta's status is SHOWN, never faked.
//
// Non-writers see read-only state. Every backend call is DORMANT-SAFE: when the
// builder/asset service is dormant the gate degrades to a calm "not connected"
// note and the user can still proceed to Audience (the LIVE open-session path).

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Modal from "@/components/Modal";
import PhonePreview from "../_components/PhonePreview";
import { MetaReadinessHint } from "../_components/MetaStatusNote";
import {
    approveAsset,
    submitTemplateToMeta,
    getMetaStatus,
    type MetaReview,
} from "../_lib/waapi";
import { type StepCtx } from "../_lib/types";

const CHECKS = [
    { label: "Readable text", ok: true },
    { label: "Brand match", ok: true },
    { label: "No invented claims", ok: true },
    { label: "Platform-fit (WhatsApp)", ok: true },
];

// Map the four Meta review states → premium Badge + label (shown, never faked).
function reviewBadge(review: MetaReview) {
    switch (review) {
        case "approved":
            return { variant: "success" as const, label: "Approved by Meta" };
        case "rejected":
            return { variant: "danger" as const, label: "Rejected by Meta" };
        case "pending":
            return { variant: "warning" as const, label: "Pending Meta approval" };
        default:
            return { variant: "neutral" as const, label: "Not submitted" };
    }
}

export default function ApprovalStep({ draft, setDraft, goTo, writable, notify }: StepCtx) {
    const [confirm, setConfirm] = useState(false);
    const [busy, setBusy] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [submitNote, setSubmitNote] = useState<string>("");
    // Meta's own raw line + code when Meta rejected the submission (debug muted line).
    const [submitDebug, setSubmitDebug] = useState<string>("");

    // The live Meta review state for the persisted template row. Seeded from the
    // draft, then refreshed by submit + polling.
    const seedReview: MetaReview =
        draft.meta_template_status === "approved"
            ? "approved"
            : draft.meta_template_status === "rejected"
            ? "rejected"
            : draft.meta_template_status === "pending"
            ? "pending"
            : "none";
    const [review, setReview] = useState<MetaReview>(seedReview);
    const [rejectionReason, setRejectionReason] = useState<string>(draft.meta_rejection_reason || "");

    async function approve() {
        setBusy(true);
        if (draft.asset_id) {
            const r = await approveAsset(draft.asset_id);
            // dormant -> we still allow the send gate to proceed (open-session/manual)
            if (r.configured) notify("Asset approved", "success");
            else notify("Approval engine not connected — proceed with manual send", "error");
        }
        setDraft({ asset_approved: true });
        setBusy(false);
        setConfirm(false);
        goTo("audience");
    }

    // ── LIVE Submit-to-Meta: approve (builder) → optional banner attach → submit.
    const doSubmit = useCallback(async () => {
        if (!draft.template_id) {
            setSubmitNote(
                "This template wasn’t created through the AI builder, so it can’t be submitted to Meta automatically. Use an AI-generated template, or send it as an open-session message."
            );
            return;
        }
        setSubmitting(true);
        setSubmitNote("");
        setSubmitDebug("");
        const r = await submitTemplateToMeta({
            templateId: draft.template_id,
            assetId: draft.asset_id, // bind the banner as the IMAGE header (if any)
        });
        if (!r.configured) {
            setSubmitNote(
                "WhatsApp isn’t connected on this account yet — the template can’t be submitted to Meta. You can still send open-session messages."
            );
            setSubmitting(false);
            return;
        }
        if (r.submitted) {
            setReview(r.review);
            setDraft({
                meta_template_status: r.review === "approved" ? "approved" : r.review === "rejected" ? "rejected" : "pending",
                meta_template_id: r.metaTemplateId,
            });
            notify("Sent to Meta for review — we’ll track the status here", "success");
        } else {
            setSubmitNote(r.message || "The template couldn’t be submitted to Meta right now.");
            if (r.metaDebug) setSubmitDebug(r.metaDebug);
        }
        setSubmitting(false);
    }, [draft.template_id, draft.asset_id, setDraft, notify]);

    // ── Poll the real Meta review state while PENDING (every 12s, self-cleaning).
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
    useEffect(() => {
        if (review !== "pending" || !draft.template_id) return;
        const tick = async () => {
            const r = await getMetaStatus(draft.template_id!);
            if (!r.configured) return;
            if (r.review !== "none" && r.review !== "pending") {
                setReview(r.review);
                if (r.rejectionReason) setRejectionReason(r.rejectionReason);
                setDraft({
                    meta_template_status: r.review,
                    meta_rejection_reason: r.rejectionReason,
                });
            }
        };
        pollRef.current = setInterval(tick, 12000);
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, [review, draft.template_id, setDraft]);

    const assetState = draft.asset_approved
        ? { variant: "success" as const, label: "Approved" }
        : draft.asset_id
        ? { variant: "warning" as const, label: "Pending approval" }
        : { variant: "neutral" as const, label: "No banner" };

    const metaBadge = reviewBadge(review);
    const canSubmit = review === "none" || review === "rejected";

    return (
        <>
            <div className="flex gap-3 max-lg:flex-col">
                <div className="flex-1 min-w-0 flex flex-col gap-3">
                    <Card title="Quality checklist">
                        <div className="grid grid-cols-2 gap-3 px-5 pb-5 pt-1 max-md:grid-cols-1 max-lg:px-3">
                            {CHECKS.map((c) => (
                                <div key={c.label} className="flex items-center gap-2.5 p-3 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
                                    <Icon className={`!size-4.5 ${c.ok ? "fill-primary-02" : "fill-t-tertiary"}`} name="check-circle-fill" />
                                    <span className="text-body-2 text-t-primary">{c.label}</span>
                                </div>
                            ))}
                        </div>
                    </Card>

                    <Card title="Gates">
                        <div className="flex flex-col gap-3 px-5 pb-5 pt-1 max-lg:px-3">
                            <div className="flex items-center gap-3 p-3.5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
                                <div className="grow">
                                    <div className="text-button text-t-primary">Asset approval</div>
                                    <div className="text-caption text-t-tertiary">Only approved banners can be sent.</div>
                                </div>
                                <Badge variant={assetState.variant}>{assetState.label}</Badge>
                            </div>

                            <div className="flex items-center gap-3 p-3.5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
                                <div className="grow">
                                    <div className="text-button text-t-primary">Meta template approval</div>
                                    <div className="text-caption text-t-tertiary">Meta&apos;s own gate — shown live, never faked.</div>
                                </div>
                                <Badge variant={metaBadge.variant}>{metaBadge.label}</Badge>
                            </div>

                            {/* live rejection reason, surfaced verbatim from Meta */}
                            {review === "rejected" && rejectionReason && (
                                <div className="flex items-start gap-2.5 p-3.5 rounded-3xl bg-b-surface1 ring-1 ring-s-subtle text-body-2 text-t-secondary">
                                    <Icon className="shrink-0 mt-px fill-primary-05 !size-4" name="info" />
                                    <span>
                                        <span className="text-t-primary">Meta’s reason:</span> {rejectionReason}
                                    </span>
                                </div>
                            )}

                            {/* submit note (refused gate / not-an-AI-template / Meta error) */}
                            {submitNote && (
                                <div className="flex items-start gap-2.5 p-3.5 rounded-3xl bg-b-surface1 ring-1 ring-s-subtle text-body-2 text-t-secondary">
                                    <Icon className="shrink-0 mt-px fill-primary-05 !size-4" name="info" />
                                    <span>
                                        {submitNote}
                                        {submitDebug && (
                                            <span className="mt-1 block text-caption text-t-tertiary break-words">{submitDebug}</span>
                                        )}
                                    </span>
                                </div>
                            )}

                            {writable ? (
                                <>
                                    {/* Calm, honest WhatsApp account status near the submit area. */}
                                    {canSubmit && <MetaReadinessHint />}

                                    {/* LIVE Submit-to-Meta — approve (builder) → submit */}
                                    {canSubmit && (
                                        <Button
                                            isStroke
                                            className="w-full"
                                            icon="upload"
                                            disabled={submitting}
                                            onClick={doSubmit}
                                        >
                                            {submitting
                                                ? "Submitting to Meta…"
                                                : review === "rejected"
                                                ? "Fix & resubmit to Meta"
                                                : "Submit template to Meta"}
                                        </Button>
                                    )}
                                    {review === "pending" && (
                                        <div className="flex items-center gap-2 p-3.5 rounded-3xl bg-b-surface1 text-caption text-t-tertiary">
                                            <Icon className="fill-t-tertiary !size-4" name="clock" />
                                            Submitted — waiting on Meta. This status updates automatically.
                                        </div>
                                    )}

                                    <Button isBlack className="w-full" disabled={busy} onClick={() => setConfirm(true)}>
                                        Approve &amp; continue to audience
                                    </Button>
                                </>
                            ) : (
                                <div className="flex items-center gap-2 p-3.5 rounded-3xl bg-b-surface1 text-caption text-t-tertiary">
                                    <Icon className="fill-t-tertiary !size-4" name="lock" />
                                    You have read-only access — ask a manager to approve.
                                </div>
                            )}
                        </div>
                    </Card>
                </div>

                <div className="w-90 max-3xl:w-76 max-lg:w-full shrink-0">
                    <div className="px-1 mb-3 text-button text-t-secondary">What gets sent</div>
                    <PhonePreview draft={draft} />
                </div>
            </div>

            <Modal open={confirm} onClose={() => setConfirm(false)}>
                <div className="text-center">
                    <div className="flex justify-center items-center size-14 mx-auto mb-5 rounded-full bg-b-surface2">
                        <Icon className="fill-primary-02" name="check-circle" />
                    </div>
                    <div className="text-h5 text-t-primary">Approve this template?</div>
                    <div className="mt-2 max-w-90 mx-auto text-body-2 text-t-secondary">
                        This marks the banner approved and unlocks sending. You can still pick the audience next.
                    </div>
                    <div className="flex gap-3 justify-center mt-8">
                        <Button isStroke onClick={() => setConfirm(false)}>Cancel</Button>
                        <Button isBlack disabled={busy} onClick={approve}>{busy ? "Approving…" : "Approve"}</Button>
                    </div>
                </div>
            </Modal>
        </>
    );
}
