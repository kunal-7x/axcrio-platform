// Presentational helpers for Auto Lead. Reuses the CRM date/initials helpers so
// the surfaces stay consistent.
import BrandMark from "@/components/BrandMark";

export { fmtRelative, fmtDateTime, initials } from "@/app/crm/_ui";

// Source type → the REAL company logo (full colour) where there is one, else a
// clean neutral glyph for generic sources. Email uses the Gmail mark.
const SOURCE_MARK: Record<string, { name?: string; icon?: string; label: string }> = {
    custom: { icon: "chain", label: "Custom" },
    website: { icon: "earth", label: "Website" },
    zapier: { name: "zapier", label: "Zapier" },
    meta_ads: { name: "meta", label: "Meta" },
    google_ads: { name: "googleads", label: "Google" },
    whatsapp: { name: "whatsapp", label: "WhatsApp" },
    email: { name: "gmail", label: "Email" },
    apollo: { name: "apollo", label: "Apollo" },
};

export function SourceIcon({ icon, type, size = 14 }: { icon?: string; type?: string; size?: number }) {
    const m = SOURCE_MARK[type || ""] ?? { icon: icon || "chain", label: type || "?" };
    return <BrandMark name={m.name} icon={m.icon} label={m.label} size={size} />;
}

export const CHANNEL_LABEL: Record<string, string> = {
    webhook: "Webhook",
    poll: "Polled",
    test: "Test",
};
