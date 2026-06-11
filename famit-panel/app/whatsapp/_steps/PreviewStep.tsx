// ⑥ TEMPLATE PREVIEW — the real WhatsApp message preview (master-detail). The
// pinned phone mock (PhonePreview) renders the EXACT message; the editable
// template (body / CTA / language / banner thumb) sits on the left. A Switch
// toggles "Sample data ↔ Real lead". LIVE: client-side render — no backend gen.

"use client";

import { useMemo, useState } from "react";
import Card from "@/components/Card";
import Field from "@/components/Field";
import Button from "@/components/Button";
import Switch from "@/components/Switch";
import Tabs from "@/components/Tabs";
import Image from "@/components/Image";
import Icon from "@/components/Icon";
import { type TabsOption } from "@/types/tabs";
import PhonePreview from "../_components/PhonePreview";
import MetaComplianceCard from "../_components/MetaComplianceCard";
import { checkMetaCompliance } from "../_lib/meta";
import { LANGUAGES, type StepCtx } from "../_lib/types";

export default function PreviewStep({ draft, setDraft, goTo, writable, notify }: StepCtx) {
    const [real, setReal] = useState(false);
    const lang =
        LANGUAGES.find((l) => l.name === draft.language) || LANGUAGES[0];

    const setLang = (l: TabsOption) => setDraft({ language: l.name });

    // Live Meta-compliance pre-check — recomputed as the founder types so the
    // created template's status is always visible BEFORE submitting to Meta.
    const compliance = useMemo(() => checkMetaCompliance(draft), [draft]);
    const blocked = compliance.failCount > 0;

    return (
        <div className="flex gap-3 max-lg:flex-col">
            {/* editable template */}
            <div className="flex-1 min-w-0">
                <Card title="Template">
                    <div className="flex flex-col gap-5 px-5 pb-5 pt-1 max-lg:px-3">
                        <Field
                            label="Template name"
                            placeholder="festive_launch_offer"
                            value={draft.name || ""}
                            onChange={(e) => setDraft({ name: e.target.value })}
                        />

                        {/* header banner — becomes the WhatsApp IMAGE header on the
                            template. Bound to an approved Creative asset (asset_id);
                            on Submit-to-Meta the backend turns it into a real Meta
                            header_handle. No banner ⇒ a clean text-header template. */}
                        <div>
                            <div className="mb-3 text-button">Header banner <span className="text-caption text-t-tertiary font-normal">(optional — shows above the message)</span></div>
                            <div className="flex items-center gap-3 p-3 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle">
                                <div className="relative size-14 shrink-0 rounded-2xl overflow-hidden bg-b-surface1">
                                    {draft.asset_url ? (
                                        <Image className="object-cover" src={draft.asset_url} alt="" fill sizes="56px" />
                                    ) : (
                                        <div className="flex items-center justify-center h-full"><Icon className="fill-t-tertiary" name="camera" /></div>
                                    )}
                                </div>
                                <div className="grow min-w-0">
                                    <div className="text-button text-t-primary">{draft.asset_url ? "Banner attached" : "No banner"}</div>
                                    <div className="text-caption text-t-tertiary">{draft.asset_url ? "Sent as the WhatsApp header image" : "Pick or generate one — it’s sent to Meta with the template"}</div>
                                </div>
                                {draft.asset_url ? (
                                    <>
                                        <Button isStroke icon="camera" onClick={() => goTo("creative")}>Change</Button>
                                        <Button isStroke icon="magic-pencil" onClick={() => goTo("banner")}>Generate</Button>
                                    </>
                                ) : (
                                    <>
                                        <Button isStroke icon="camera" onClick={() => goTo("creative")}>Add banner</Button>
                                        <Button isStroke icon="magic-pencil" onClick={() => goTo("banner")}>Generate</Button>
                                    </>
                                )}
                            </div>
                        </div>

                        <Field
                            label="Message body"
                            textarea
                            placeholder="Hi {{1}}, our festive 2BHK launch offer is live…"
                            value={draft.body}
                            onChange={(e) => setDraft({ body: e.target.value })}
                        />
                        <div className="flex gap-4 max-md:flex-col">
                            <Field className="flex-1" label="CTA button label" placeholder="Book now" value={draft.cta || ""} onChange={(e) => setDraft({ cta: e.target.value })} />
                            <Field className="flex-1" label="CTA URL" placeholder="https://…/book" value={draft.cta_url || ""} onChange={(e) => setDraft({ cta_url: e.target.value })} />
                        </div>
                        <Field label="Footer (optional)" placeholder="Reply STOP to opt out" value={draft.footer || ""} onChange={(e) => setDraft({ footer: e.target.value })} />

                        <div>
                            <div className="mb-3 text-button">Language</div>
                            <Tabs items={LANGUAGES} value={lang} setValue={setLang} />
                        </div>

                        {/* live Meta-compliance status of the template being authored */}
                        <MetaComplianceCard report={compliance} />

                        {writable && (
                            <Button
                                isBlack
                                className="w-full"
                                disabled={!draft.body.trim() || blocked}
                                onClick={() => {
                                    if (blocked) return;
                                    notify("Template ready — sending for approval", "success");
                                    goTo("approval");
                                }}
                            >
                                {blocked
                                    ? "Fix the Meta issues above to continue"
                                    : "Looks good — send for approval"}
                            </Button>
                        )}
                    </div>
                </Card>
            </div>

            {/* pinned phone preview */}
            <div className="w-90 max-3xl:w-76 max-lg:w-full shrink-0">
                <div className="sticky top-22 flex flex-col gap-3 max-lg:static">
                    <div className="flex items-center justify-between px-1">
                        <div className="text-button text-t-secondary">Live preview</div>
                        <label className="flex items-center gap-2 text-caption text-t-tertiary cursor-pointer">
                            {real ? "Real lead" : "Sample data"}
                            <Switch checked={real} onChange={setReal} />
                        </label>
                    </div>
                    <PhonePreview draft={draft} sampleName={real ? "Rohan Mehta" : "Kunal"} />
                </div>
            </div>
        </div>
    );
}
