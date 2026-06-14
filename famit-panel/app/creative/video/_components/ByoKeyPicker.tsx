"use client";

/**
 * ByoKeyPicker (W9, §10d) — the per-tenant gen-provider picker, a thin view over
 * the Universal Provider Framework's `video_gen` capability (consumes
 * `useIntegrations("video_gen")` from lib/integrations — the seam the BE wave left
 * ready). Lets the vendor pick WHICH registered video provider a PAID render routes
 * through, and deep-links to /integrations to add/rotate a key (the full secure
 * CRUD + PIN-gated reveal lives there — we never surface a key here).
 *
 * Shown only for a PAID tier (composite needs no key). When no provider is enabled
 * it renders a calm "add a key" affordance, never an error. Token-pure, zero hex.
 */

import { useEffect } from "react";
import Link from "next/link";
import Select from "@/components/Select";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import type { SelectOption } from "@/types/select";
import { useIntegrations, type ProviderDef } from "@/lib/integrations";

type ByoKeyPickerProps = {
    /** the chosen provider id ("" = auto/none) */
    value?: string;
    onChange: (providerId: string, provider?: ProviderDef) => void;
    /** surface availability up to the panel (drives the paid-tier "needs key" hint) */
    onAvailability?: (hasKey: boolean) => void;
};

const ByoKeyPicker = ({ value, onChange, onAvailability }: ByoKeyPickerProps) => {
    const { providers, loading, dormant } = useIntegrations("video_gen");

    // notify the panel once we know whether any keyed provider exists (effect, not
    // during render — never setState a parent mid-render).
    const hasKey = providers.length > 0;
    useEffect(() => {
        if (!loading && onAvailability) onAvailability(hasKey);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [hasKey, loading]);

    const options: SelectOption[] = [
        { id: 0, name: "Auto (best available)" },
        ...providers.map((p, i) => ({ id: i + 1, name: p.display_name })),
    ];
    const selected =
        options.find((o) => o.id !== 0 && providers[o.id - 1]?.id === value) || options[0];

    if (loading) {
        return (
            <div className="flex items-center gap-2 mt-3 text-caption text-t-tertiary">
                <Spinner className="!size-4" /> Loading providers…
            </div>
        );
    }

    if (dormant || !hasKey) {
        return (
            <div className="flex items-start gap-2.5 mt-3 p-3.5 rounded-2xl border border-s-subtle bg-b-surface2 text-body-2">
                <Icon className="!size-4 shrink-0 mt-0.5 fill-t-secondary" name="lock" />
                <div className="grow">
                    <p className="text-t-secondary">
                        No paid video provider connected yet. Add a key once — it stays encrypted and
                        only this workspace can use it.
                    </p>
                    <Button
                        as="link"
                        href="/integrations"
                        isStroke
                        className="mt-2.5 !h-9 !px-4 !text-body-2"
                        icon="chain"
                    >
                        Connect a provider
                    </Button>
                </div>
            </div>
        );
    }

    return (
        <div className="mt-3">
            <Select
                label="Video provider (paid)"
                value={selected}
                onChange={(o) => {
                    const p = o.id === 0 ? undefined : providers[o.id - 1];
                    onChange(p?.id || "", p);
                }}
                options={options}
            />
            <Link
                href="/integrations"
                className="mt-2 inline-flex items-center gap-1 text-caption text-t-secondary fill-t-secondary transition-colors hover:text-t-primary hover:fill-t-primary"
            >
                <Icon className="!size-3.5 fill-inherit" name="plus" /> Add or rotate a key
            </Link>
        </div>
    );
};

export default ByoKeyPicker;
