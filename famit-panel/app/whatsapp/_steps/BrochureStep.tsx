// ⑦ BROCHURE — a dedicated PDF brochure step (W16).
// Brochures are CRITICAL in real estate, so the PDF gets its OWN step (not lumped
// under images). Upload a brochure from the device, preview it, OR reuse a saved
// one. Binds a single brochure to the draft. DORMANT-SAFE like the media step.

"use client";

import MediaUploader from "../_components/MediaUploader";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import { type StepCtx, type WaMedia } from "../_lib/types";

export default function BrochureStep({ draft, setDraft, goTo, notify }: StepCtx) {
    const brochure = draft.brochure || null;
    const selected: WaMedia[] = brochure ? [brochure] : [];

    return (
        <div className="flex flex-col gap-3">
            <MediaUploader
                kind="brochure"
                title="Brochure (PDF)"
                hint="Attach the project brochure or floor plan as a PDF (up to 100MB). Leads who ask for the brochure get it in their follow-up."
                multiple={false}
                selected={selected}
                onChange={(next) => setDraft({ brochure: next[0] || null })}
                notify={notify}
            />

            {brochure && (
                <Card title="Attached brochure">
                    <div className="flex items-center gap-4 px-5 pb-5 max-lg:px-3">
                        <div className="flex items-center justify-center size-14 rounded-2xl bg-b-surface1 shrink-0">
                            <Icon className="fill-primary-03 !size-7" name="feather" />
                        </div>
                        <div className="grow min-w-0">
                            <div className="truncate text-sub-title-2 text-t-primary">{brochure.title || "Brochure.pdf"}</div>
                            <div className="text-body-2 text-t-secondary">
                                {brochure.page_count ? `${brochure.page_count} pages · ` : ""}PDF brochure
                            </div>
                        </div>
                        {brochure.url && (
                            <a href={brochure.url} target="_blank" rel="noreferrer">
                                <Button isStroke icon="search">Preview</Button>
                            </a>
                        )}
                    </div>
                </Card>
            )}

            <div className="flex items-center justify-between gap-3 card !py-4">
                <div className="text-body-2 text-t-secondary">
                    {brochure ? "Brochure ready to send" : "No brochure — optional, you can continue."}
                </div>
                <Button isBlack onClick={() => goTo("preview")}>
                    Next: preview
                </Button>
            </div>
        </div>
    );
}
