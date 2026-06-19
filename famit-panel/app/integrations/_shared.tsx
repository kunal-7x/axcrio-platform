"use client";

// ============================================================================
// app/integrations/_shared — chrome + trust-signal primitives for the Universal
// Connector / Provider registry page (design crazy-ui-security §B).
//
// REUSE, never approximate: this speaks the same "Signal" vocabulary as the rest
// of the panel — Core_2 Card/Badge/Icon + semantic @theme tokens, zero raw hex.
// The ONLY net-new primitives are the sub-nav pill-strip (ported from AdminHeader)
// and the HealthBadge (a circuit-state → Badge map, the trust signal on every
// provider). Glyph ground-truth honored: chain/lock/clock-1/info exist;
// shield/eye/copy/key/refresh DO NOT — so Reveal=lock, Rotate=clock-1, Connector
// nav=chain, every Test/Copy/Export is a text button.
// ============================================================================

import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "@/components/Icon";
import Badge, { type BadgeVariant } from "@/components/Badge";
import {
    type CircuitState,
    type Capability,
    type ProviderType,
    CAPABILITY_LABEL,
    PROVIDER_TYPE_LABEL,
} from "@/lib/integrations";

// Ghost (icon + label) action button — the shared affordance (matches _shared.tsx).
export const ghostBtnCls =
    "inline-flex items-center gap-2 h-10 px-4 rounded-full text-button text-t-secondary border border-s-subtle transition-all hover:border-s-highlight hover:text-t-primary disabled:opacity-50 disabled:cursor-not-allowed";

// A quiet text button (Test / Copy / Export — glyphs for these don't exist).
export const textBtnCls =
    "inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-caption text-t-secondary border border-s-subtle transition-all hover:border-s-highlight hover:text-t-primary disabled:opacity-50 disabled:cursor-not-allowed";

// ---- sub-nav pill-strip (Providers / Self-hosted / Health / Audit) ----------
// Ported from AdminHeader's tab strip, NOT a <Tabs> (these are routed sub-pages
// within ONE page that switches a local view — so it's a plain segmented control).
export type IntegrationsView = "providers" | "selfhosted" | "health" | "audit";

const VIEWS: { id: IntegrationsView; label: string }[] = [
    { id: "providers", label: "Providers" },
    { id: "selfhosted", label: "Self-hosted" },
    { id: "health", label: "Health" },
    { id: "audit", label: "Audit" },
];

export function SubNav({
    view,
    onChange,
    actions,
}: {
    view: IntegrationsView;
    onChange: (v: IntegrationsView) => void;
    actions?: React.ReactNode;
}) {
    return (
        <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
            <div className="flex items-center gap-1 w-fit max-w-full overflow-x-auto scrollbar-none">
                {VIEWS.map((v) => {
                    const active = v.id === view;
                    return (
                        <button
                            key={v.id}
                            onClick={() => onChange(v.id)}
                            className={`shrink-0 inline-flex items-center h-10 px-4 rounded-full border text-button transition-colors hover:text-t-primary ${
                                active
                                    ? "border-s-stroke2 text-t-primary"
                                    : "border-transparent text-t-secondary"
                            }`}
                        >
                            {v.label}
                        </button>
                    );
                })}
            </div>
            {actions && <div className="flex items-center gap-3 shrink-0">{actions}</div>}
        </div>
    );
}

// ---- HealthBadge (circuit-state → Badge) — the live trust signal -------------
// closed = healthy/in-rotation (green dot) · half_open = recovering (amber) ·
// open = circuit tripped / down (danger) · unknown = not probed yet (neutral).
const CIRCUIT_MAP: Record<CircuitState, { label: string; variant: BadgeVariant; dot?: boolean }> = {
    closed: { label: "Healthy", variant: "success", dot: true },
    half_open: { label: "Recovering", variant: "warning", dot: true },
    open: { label: "Down", variant: "danger" },
    unknown: { label: "Unchecked", variant: "neutral" },
};

export function HealthBadge({ circuit }: { circuit?: CircuitState }) {
    const c = CIRCUIT_MAP[circuit ?? "unknown"] ?? CIRCUIT_MAP.unknown;
    return (
        <Badge variant={c.variant} dot={c.dot}>
            {c.label}
        </Badge>
    );
}

// Capability chip row.
export function CapabilityChips({ capabilities }: { capabilities: Capability[] }) {
    if (!capabilities?.length) return null;
    return (
        <div className="flex items-center gap-1.5 flex-wrap">
            {capabilities.map((cap) => (
                <Badge key={cap} variant="info">
                    {CAPABILITY_LABEL[cap] || cap}
                </Badge>
            ))}
        </div>
    );
}

// Provider-type pill (Hosted API / Self-hosted / Connector / Built-in).
export function TypePill({ type }: { type: ProviderType }) {
    const variant: BadgeVariant = type === "self_hosted" ? "warning" : type === "tool_connector" ? "info" : "neutral";
    return <Badge variant={variant}>{PROVIDER_TYPE_LABEL[type] || type}</Badge>;
}

// The platform-managed lock chip (an ai_provider-scope key a vendor can't reveal).
export function PlatformLock() {
    return (
        <span className="inline-flex items-center gap-1.5 text-caption text-t-secondary">
            <Icon name="lock" className="size-3.5 fill-t-secondary" />
            Platform-managed
        </span>
    );
}

// Inline info strip (matches the api-keys live banner grammar).
export function InfoStrip({ children }: { children: React.ReactNode }) {
    return (
        <div className="mb-5 flex items-center gap-2 p-3.5 rounded-3xl bg-b-surface2 border border-s-subtle text-body-2 text-t-secondary">
            <Icon name="info" className="size-4 fill-t-secondary shrink-0" />
            {children}
        </div>
    );
}

export function fmtDateTime(d?: string | null): string {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}
