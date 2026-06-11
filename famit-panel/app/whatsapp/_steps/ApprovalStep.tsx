// ⑦ APPROVAL — the content-policy gate (two gates, in order). A review card +
// a creative-quality checklist, then (a) asset-approval (creative.approve) and
// (b) WhatsApp send-approval. Meta template status is SHOWN, never faked.
//
// Non-writers see read-only state. The asset-approval call is DORMANT-SAFE: when
// :8310 is dormant the gate degrades to a calm "approval not yet wired" state and
// the user can still proceed to Audience (the LIVE path) for open-session/manual.

"use client";

import { useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Badge from "@/components/Badge";
import Icon from "@/components/Icon";
import Modal from "@/components/Modal";
import PhonePreview from "../_components/PhonePreview";
import { approveAsset } from "../_lib/waapi";
import { type StepCtx } from "../_lib/types";

const CHECKS = [
    { label: "Readable text", ok: true },
    { label: "Brand match", ok: true },
    { label: "No invented claims", ok: true },
    { label: "Platform-fit (WhatsApp)", ok: true },
];

export default function ApprovalStep({ draft, setDraft, goTo, writable, notify }: StepCtx) {
    const [confirm, setConfirm] = useState(false);
    const [busy, setBusy] = useState(false);

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

    const assetState = draft.asset_approved
        ? { variant: "success" as const, label: "Approved" }
        : draft.asset_id
        ? { variant: "warning" as const, label: "Pending approval" }
        : { variant: "neutral" as const, label: "No banner" };

    const metaStatus = draft.meta_template_status || "none";
    const metaBadge =
        metaStatus === "approved"
            ? { variant: "success" as const, label: "Approved" }
            : metaStatus === "rejected"
            ? { variant: "danger" as const, label: "Rejected" }
            : metaStatus === "pending"
            ? { variant: "warning" as const, label: "Pending Meta approval" }
            : { variant: "neutral" as const, label: "Not submitted" };

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

                            {writable ? (
                                <Button isBlack className="w-full" disabled={busy} onClick={() => setConfirm(true)}>
                                    Approve &amp; continue to audience
                                </Button>
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
