"use client";

/**
 * CampaignSelect — ONE reusable campaign dropdown that ENDS the manual-paste flow
 * (founder's #1 recurring ask). It self-fetches the vendor's campaigns, owns the
 * selection, and on pick AUTO-FETCHES that campaign's detail snapshot, handing
 * BOTH the lean record and the resolved detail upward in a single action.
 *
 * Wraps the premium `components/Select` (headlessui Listbox + SelectOption) so it
 * looks identical to every other selector in the app — no hand-rolled dropdown,
 * no PageHeader/jargon rules touched.
 *
 * Dormant-safe end to end:
 *   - list fetch fails  -> empty options, calm "No campaigns yet" placeholder
 *   - detail fetch dormant (Asset Service off) -> getCampaignContext resolves to
 *     { facts: [] }; the caller falls back to its own client derivation.
 *
 * Zero new backend: GET /api/campaigns (list) + GET /api/assets/campaign-context
 * (detail) both already LIVE. See design/fix-campaign-dropdown.md.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Select from "@/components/Select";
import type { SelectOption } from "@/types/select";
import { getCampaigns, type Campaign } from "@/lib/api";
import { getCampaignContext, type CampaignContextSnapshot } from "@/lib/assets";

type CampaignSelectProps = {
    /** selected campaign id (controlled) — keeps the dropdown in sync with the page */
    value?: string;
    /** fired after the detail snapshot is auto-fetched (facts=[] on dormant) */
    onSelect: (campaign: Campaign, detail: CampaignContextSnapshot) => void;
    className?: string;
    label?: string;
    placeholder?: string;
    /** convenience: auto-pick + auto-fetch the first campaign once loaded */
    autoSelectFirst?: boolean;
};

const CampaignSelect = ({
    value,
    onSelect,
    className,
    label = "Campaign",
    placeholder = "Choose a campaign",
    autoSelectFirst = false,
}: CampaignSelectProps) => {
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [loading, setLoading] = useState(true);
    // guards autoSelectFirst from re-firing after the user has touched the field
    const autoPicked = useRef(false);

    useEffect(() => {
        let active = true;
        setLoading(true);
        getCampaigns()
            .then(({ campaigns }) => active && setCampaigns(campaigns))
            .catch(() => active && setCampaigns([]))
            .finally(() => active && setLoading(false));
        return () => {
            active = false;
        };
    }, []);

    // SelectOption ids are positional (1-based) so the premium Select stays generic;
    // we map back to the real Campaign by index on change.
    const options: SelectOption[] = useMemo(
        () => campaigns.map((c, i) => ({ id: i + 1, name: c.name })),
        [campaigns]
    );

    const selected: SelectOption | null = useMemo(() => {
        if (!value) return null;
        const idx = campaigns.findIndex((c) => c.id === value);
        return idx >= 0 ? { id: idx + 1, name: campaigns[idx].name } : null;
    }, [value, campaigns]);

    const emit = (campaign: Campaign) => {
        // auto-fetch the per-campaign detail; getCampaignContext is dormant-safe
        // (resolves to { facts: [] } on any non-200 / asset service off), never throws.
        getCampaignContext(campaign.id)
            .then((detail) => onSelect(campaign, detail))
            .catch(() =>
                onSelect(campaign, { campaign_id: campaign.id, facts: [] })
            );
    };

    const handleChange = (opt: SelectOption) => {
        const campaign = campaigns[opt.id - 1];
        if (campaign) emit(campaign);
    };

    // optional: auto-pick the first campaign so the studio isn't blank on load
    useEffect(() => {
        if (!autoSelectFirst || autoPicked.current) return;
        if (value || campaigns.length === 0) return;
        autoPicked.current = true;
        emit(campaigns[0]);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [autoSelectFirst, value, campaigns]);

    return (
        <Select
            className={className}
            label={label}
            value={selected}
            onChange={handleChange}
            options={options}
            placeholder={
                loading
                    ? "Loading campaigns…"
                    : options.length === 0
                      ? "No campaigns yet"
                      : placeholder
            }
        />
    );
};

export default CampaignSelect;
