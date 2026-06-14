"use client";

// Shared body — used by /integrations (admin=false) and /super-admin/integrations (admin=true).
// Extracted from page.tsx to avoid exporting a named function from the Next.js page module
// (which causes a .next/types TS2344 error from the route-type checker).

import { useMemo, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Spinner from "@/components/Spinner";
import { useProviders, type ProviderDef } from "@/lib/integrations";
import { SubNav, InfoStrip, ghostBtnCls, type IntegrationsView } from "./_shared";
import { ToastView, type Toast } from "../super-admin/_shared";
import ProviderCard from "./_provider-card";
import AddProviderModal from "./_add-provider-modal";
import HealthTable from "./_health-table";
import AuditDrawer from "./_audit-drawer";

export function IntegrationsBody({ admin }: { admin: boolean }) {
    const [view, setView] = useState<IntegrationsView>("providers");
    const [toast, setToast] = useState<Toast | null>(null);
    const [adding, setAdding] = useState(false);
    const [addingSelfHosted, setAddingSelfHosted] = useState(false);
    const [editing, setEditing] = useState<ProviderDef | null>(null);

    const { providers, loading, dormant, reload } = useProviders({ admin });

    const flash = (msg: string, type: Toast["type"] = "success") => setToast({ msg, type });

    const hosted = useMemo(
        () => providers.filter((p) => p.provider_type !== "self_hosted"),
        [providers],
    );
    const selfHosted = useMemo(
        () => providers.filter((p) => p.provider_type === "self_hosted"),
        [providers],
    );

    const addBtn = (
        <button
            className={ghostBtnCls}
            onClick={() => {
                setAddingSelfHosted(view === "selfhosted");
                setAdding(true);
            }}
        >
            <Icon name="plus" className="size-4 fill-inherit" />
            {view === "selfhosted" ? "Add endpoint" : "Add provider"}
        </button>
    );

    // ---- dormant (flag off / not entitled) -> calm coming-soon card -----------
    if (!loading && dormant) {
        return (
            <Card title="Integrations">
                <div className="flex flex-col items-center text-center py-16 gap-3">
                    <span className="inline-flex items-center justify-center size-14 rounded-full bg-b-surface2">
                        <Icon name="chain" className="size-6 fill-t-secondary" />
                    </span>
                    <div className="text-h6 text-t-primary">Connect any AI model or tool</div>
                    <p className="text-body-2 text-t-secondary max-w-md">
                        Add a hosted model with your own key, self-host a model and point to its endpoint, or wire
                        any future tool — all from here, no code. This workspace isn&apos;t enabled for integrations
                        yet.
                    </p>
                </div>
            </Card>
        );
    }

    return (
        <>
            <SubNav view={view} onChange={setView} actions={view !== "health" && view !== "audit" ? addBtn : undefined} />

            {view === "providers" && (
                <>
                    <InfoStrip>
                        Add any AI model or tool. A hosted provider takes your own key (encrypted at rest, revealed
                        only with your PIN). Video Studio and every other feature picks a provider from here by what
                        it can do.
                    </InfoStrip>
                    {loading ? (
                        <Center />
                    ) : hosted.length === 0 ? (
                        <EmptyState
                            title="No providers yet"
                            body="Add a hosted model — OpenAI-compatible endpoints work with zero configuration."
                        />
                    ) : (
                        <div className="flex flex-col gap-5">
                            {hosted.map((p) => (
                                <ProviderCard
                                    key={p.id}
                                    def={p}
                                    admin={admin}
                                    onChanged={reload}
                                    onEdit={(d) => {
                                        setEditing(d);
                                    }}
                                    onToast={flash}
                                />
                            ))}
                        </div>
                    )}
                </>
            )}

            {view === "selfhosted" && (
                <>
                    <InfoStrip>
                        Self-hosted endpoints are validated against the SSRF guard before they can serve — private,
                        loopback and cloud-metadata addresses are always refused.{" "}
                        {!admin && "Adding a self-hosted endpoint is managed by your admin."}
                    </InfoStrip>
                    {loading ? (
                        <Center />
                    ) : selfHosted.length === 0 ? (
                        <EmptyState
                            title="No self-hosted endpoints"
                            body={
                                admin
                                    ? "Point at a vLLM / Ollama / ComfyUI node — it's probed before it can serve."
                                    : "Your admin can register a self-hosted model endpoint."
                            }
                        />
                    ) : (
                        <div className="flex flex-col gap-5">
                            {selfHosted.map((p) => (
                                <ProviderCard
                                    key={p.id}
                                    def={p}
                                    admin={admin}
                                    onChanged={reload}
                                    onEdit={(d) => setEditing(d)}
                                    onToast={flash}
                                />
                            ))}
                        </div>
                    )}
                </>
            )}

            {view === "health" && <HealthTable admin={admin} />}
            {view === "audit" && <AuditDrawer />}

            {/* add (provider or self-hosted) */}
            <AddProviderModal
                open={adding}
                admin={admin}
                seedSelfHosted={addingSelfHosted}
                onClose={() => {
                    setAdding(false);
                    setAddingSelfHosted(false);
                }}
                onSaved={async () => {
                    flash("Provider added.");
                    await reload();
                }}
            />
            {/* edit */}
            <AddProviderModal
                open={!!editing}
                admin={admin}
                edit={editing}
                onClose={() => setEditing(null)}
                onSaved={async () => {
                    flash("Saved.");
                    await reload();
                }}
            />

            <ToastView toast={toast} onClose={() => setToast(null)} />
        </>
    );
}

function Center() {
    return (
        <div className="flex items-center justify-center py-32">
            <Spinner />
        </div>
    );
}

function EmptyState({ title, body }: { title: string; body: string }) {
    return (
        <Card title={title}>
            <div className="rounded-3xl border border-dashed border-s-subtle px-5 py-10 text-center text-body-2 text-t-secondary">
                {body}
            </div>
        </Card>
    );
}
