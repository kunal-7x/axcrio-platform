// ② CAMPAIGN SELECTION — pick the campaign the message is FOR via the reusable
// CampaignSelect DROPDOWN (founder's "stop pasting campaign details" ask). On
// pick it AUTO-FETCHES that campaign's resolved detail snapshot and projects it
// onto the master Campaign Context panel (col-right, read-only) so the user SEES
// the exact inputs the AI will use before it runs. The detail then flows into
// generateTemplates({ campaign_id }) on ③.
//
// LIVE: GET /api/campaigns (list) + GET /api/assets/campaign-context (detail,
// dormant-safe). No manual paste, no full-page table — one action, one dropdown.

"use client";

import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import CampaignSelect from "@/components/CampaignSelect";
import { type Campaign } from "@/lib/api";
import { type CampaignContextSnapshot } from "@/lib/assets";
import { contextFromCampaign, ctxFromSnapshot } from "../_lib/waapi";
import NoInventNote from "../_components/NoInventNote";
import { type StepCtx, type CampaignContext } from "../_lib/types";

const CTX_ROWS: { key: keyof CampaignContext; label: string }[] = [
    { key: "business", label: "Business" },
    { key: "product", label: "Product" },
    { key: "location", label: "Location" },
    { key: "price", label: "Price" },
    { key: "offer", label: "Offer" },
    { key: "audience", label: "Audience" },
    { key: "goal", label: "Goal" },
    { key: "brand", label: "Brand style" },
    { key: "language", label: "Language" },
];

export default function CampaignStep({ campaign, context, setCampaign, goTo }: StepCtx) {
    // on select → use the auto-fetched detail snapshot; fall back to the client
    // derivation when the Asset Service is dormant (snapshot carried no facts).
    const handleSelect = (c: Campaign, detail: CampaignContextSnapshot) => {
        const ctx = ctxFromSnapshot(detail) ?? contextFromCampaign(c);
        setCampaign(c, ctx);
    };

    return (
        <div className="flex gap-3 max-lg:flex-col">
            {/* dropdown select */}
            <div className="flex-1 min-w-0">
                <Card title="Select campaign">
                    <div className="px-5 pb-5 pt-1 max-lg:px-3">
                        <p className="mb-5 text-body-2 text-t-secondary">
                            Pick a campaign — its details are fetched automatically and
                            handed to the AI. No copy-pasting.
                        </p>
                        <CampaignSelect
                            value={campaign?.id}
                            onSelect={handleSelect}
                            placeholder="Choose a campaign"
                        />
                        {campaign && (
                            <div className="mt-5 flex items-center gap-2 p-3.5 rounded-3xl bg-b-surface2 ring-1 ring-s-subtle text-body-2 text-t-secondary">
                                <Icon className="shrink-0 fill-primary-02 !size-4" name="check" />
                                <span>
                                    <span className="text-t-primary">{campaign.name}</span> selected
                                    — details fetched. Review them on the right, then generate.
                                </span>
                            </div>
                        )}
                    </div>
                </Card>
            </div>

            {/* read-only Campaign Context panel */}
            <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0 flex flex-col gap-3">
                <Card title="Campaign context">
                    <div className="px-5 pb-5 pt-1 max-lg:px-3">
                        {!campaign ? (
                            <div className="py-8 text-center text-body-2 text-t-secondary">
                                Select a campaign to see the data the AI will use.
                            </div>
                        ) : (
                            <>
                                <div className="flex flex-col divide-y divide-s-subtle">
                                    {CTX_ROWS.map((r) => (
                                        <div key={r.key} className="flex items-start gap-3 py-2.5">
                                            <div className="w-28 shrink-0 text-caption text-t-tertiary">{r.label}</div>
                                            <div className="grow text-body-2 text-t-primary">
                                                {context[r.key] || <span className="text-t-tertiary">—</span>}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                                <NoInventNote className="mt-4" />
                                <Button
                                    isBlack
                                    className="w-full mt-4"
                                    onClick={() => goTo("templates")}
                                >
                                    Generate templates
                                    <Icon className="fill-inherit !size-4 ml-1" name="arrow" />
                                </Button>
                            </>
                        )}
                    </div>
                </Card>
            </div>
        </div>
    );
}
