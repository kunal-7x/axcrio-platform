"use client";

/**
 * CampaignContext (S3) — the TRUST surface. Proves the AI already knows the
 * business so the vendor doesn't re-spec (cs-workspace §5). Renders the resolved
 * campaign_ctx snapshot as label/value rows, each carrying a PROVENANCE DOT
 * (filled = from real data, hollow = "AI will ask") so the §20 no-invent
 * guarantee is VISIBLE — a value the AI must never invent (price/RERA/phone)
 * renders ONLY when provenance ≠ absent.
 *
 * Ports the `PopularProducts` / DetailsPage label-value-row + chip grammar.
 * Inside a `components/Card` titled "Campaign context". Pre-campaign: a NoFound
 * micro-state. Dormant/empty: same calm "pick a campaign" line.
 */

import { useEffect, useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Spinner from "@/components/Spinner";
import {
    getCampaignContext,
    type CampaignContextFact,
    type CampaignContextSnapshot,
} from "@/lib/assets";
import type { BrandKit } from "@/lib/assets";

type CampaignContextProps = {
    campaignId?: string;
    brandKit?: BrandKit | null;
    onEditBrand?: () => void;
};

const PROVENANCE_TITLE: Record<string, string> = {
    from_campaign: "From your campaign data",
    from_brand_kit: "From your brand kit",
    from_me: "You provided this",
    absent: "AI will ask if needed",
};

const CampaignContext = ({ campaignId, brandKit, onEditBrand }: CampaignContextProps) => {
    const [snap, setSnap] = useState<CampaignContextSnapshot | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!campaignId) {
            setSnap(null);
            return;
        }
        let active = true;
        setLoading(true);
        getCampaignContext(campaignId)
            .then((s) => active && setSnap(s))
            .finally(() => active && setLoading(false));
        return () => {
            active = false;
        };
    }, [campaignId]);

    return (
        <Card title="Campaign context">
            {!campaignId ? (
                <div className="px-5 py-10 text-center max-lg:px-3">
                    <p className="text-body-2 text-t-secondary">
                        Pick a campaign to see what I&apos;ll use.
                    </p>
                </div>
            ) : loading ? (
                <div className="py-10">
                    <Spinner />
                </div>
            ) : (
                <div className="px-5 max-lg:px-3">
                    {/* fact rows with provenance dots */}
                    <div className="divide-y divide-s-subtle">
                        {(snap?.facts?.length ? snap.facts : FALLBACK_FACTS).map((fact) => (
                            <FactRow key={fact.key} fact={fact} />
                        ))}
                    </div>

                    {/* brand chips */}
                    {brandKit && (
                        <div className="mt-4 pt-4 border-t border-s-subtle">
                            <div className="text-overline text-t-tertiary mb-2.5">Brand</div>
                            <div className="flex flex-wrap items-center gap-2">
                                {(brandKit.palette || []).slice(0, 6).map((c, i) => (
                                    <span
                                        key={i}
                                        className="size-6 rounded-full ring-1 ring-s-subtle ring-inset"
                                        style={{ backgroundColor: c }}
                                        title={c}
                                    />
                                ))}
                                {(brandKit.tone || []).slice(0, 3).map((t, i) => (
                                    <span key={i} className="label label-gray">
                                        {t}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {onEditBrand && (
                        <div className="mt-4">
                            <Button isStroke className="!h-10 !px-4 !text-body-2" onClick={onEditBrand}>
                                Edit in Brand Kit
                            </Button>
                        </div>
                    )}
                </div>
            )}
        </Card>
    );
};

const FactRow = ({ fact }: { fact: CampaignContextFact }) => {
    const filled = fact.provenance !== "absent";
    return (
        <div className="flex items-start gap-3 py-2.5">
            <span
                className={`mt-1.5 size-2 shrink-0 rounded-full ${
                    filled ? "bg-primary-02" : "border-2 border-s-stroke2"
                }`}
                title={PROVENANCE_TITLE[fact.provenance] || ""}
                aria-hidden
            />
            <div className="grow">
                <div className="text-caption text-t-tertiary">{fact.label}</div>
                {filled && fact.value ? (
                    <div className="text-body-2 text-t-primary">{fact.value}</div>
                ) : (
                    <span className="inline-flex mt-0.5 label label-gray">AI will ask if needed</span>
                )}
            </div>
        </div>
    );
};

// Shown before the backend snapshot lands (or when dormant) so the panel never
// renders blank — the labels are real, every value hollow ("AI will ask").
const FALLBACK_FACTS: CampaignContextFact[] = [
    { key: "business", label: "Business", provenance: "absent" },
    { key: "product", label: "Product", provenance: "absent" },
    { key: "offer", label: "Offer / Price", provenance: "absent" },
    { key: "location", label: "Location", provenance: "absent" },
    { key: "audience", label: "Audience", provenance: "absent" },
    { key: "goal", label: "Goal → CTA", provenance: "absent" },
    { key: "language", label: "Language", provenance: "absent" },
];

export default CampaignContext;
