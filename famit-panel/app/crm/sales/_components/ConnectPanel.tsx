"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Icon from "@/components/Icon";
import { connect } from "../client";

// The "Connect your Twenty CRM" setup state, shown whenever no workspace is wired
// for this tenant. Posts the URL + API key to the backend, which VERIFIES the
// credentials before saving (a bad URL/key fails loud, here, not on first use).
// The key never round-trips back to the browser — only a masked tail.
export default function ConnectPanel({ canWrite }: { canWrite: boolean }) {
    const qc = useQueryClient();
    const [url, setUrl] = useState("");
    const [key, setKey] = useState("");
    const [err, setErr] = useState("");

    const mut = useMutation({
        mutationFn: () => connect(url.trim(), key.trim()),
        onSuccess: () => {
            setErr("");
            qc.invalidateQueries({ queryKey: ["twenty"] });
        },
        onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Could not connect"),
    });

    const disabled = !canWrite || mut.isPending || !url.trim() || !key.trim();

    return (
        <div className="flex flex-col gap-3">
            <Card title="Sales CRM">
                <div className="flex gap-8 px-5 pb-6 pt-2 max-lg:flex-col max-lg:gap-6 max-lg:px-3">
                    {/* Left: pitch */}
                    <div className="flex-1 min-w-0">
                        <span className="inline-grid place-items-center size-12 mb-5 rounded-full bg-primary-01/12">
                            <Icon name="chart" className="fill-primary-01" />
                        </span>
                        <div className="text-h5 mb-2">Turn called leads into a sales pipeline</div>
                        <div className="max-w-md text-body-2 text-t-secondary">
                            Connect your{" "}
                            <a
                                href="https://twenty.com"
                                target="_blank"
                                rel="noreferrer"
                                className="text-primary-01 hover:underline"
                            >
                                Twenty
                            </a>{" "}
                            workspace to manage Companies, People and a drag-and-drop deal
                            pipeline right here — in the same dashboard, no new tab, no
                            iframe. Riya&apos;s leads flow straight into it.
                        </div>
                        <ul className="mt-5 flex flex-col gap-2.5">
                            {[
                                "Drag deals across stages — synced live to Twenty",
                                "One-click import of your voice leads as People + Opportunities",
                                "Companies, contacts, notes & tasks — native Haptica UI",
                            ].map((t) => (
                                <li key={t} className="flex items-start gap-2.5 text-body-2 text-t-secondary">
                                    <Icon name="check-circle" className="size-4 mt-0.5 shrink-0 fill-primary-02" />
                                    {t}
                                </li>
                            ))}
                        </ul>
                    </div>

                    {/* Right: connect form */}
                    <div className="w-100 shrink-0 p-5 rounded-3xl bg-b-surface1 max-lg:w-full">
                        <div className="text-button mb-1">Connect a workspace</div>
                        <div className="text-caption text-t-tertiary mb-5">
                            Get an API key from Twenty → Settings → APIs &amp; Webhooks.
                        </div>
                        <div className="flex flex-col gap-4">
                            <Field
                                label="Workspace URL"
                                placeholder="https://yourteam.twenty.com"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                            />
                            <Field
                                label="API Key"
                                type="password"
                                placeholder="eyJhbGciOi…"
                                value={key}
                                onChange={(e) => setKey(e.target.value)}
                            />
                            {err && (
                                <div className="flex items-center gap-2 p-3 rounded-2xl text-body-2 bg-primary-03/8 border border-primary-03/20 text-primary-03">
                                    <Icon name="info" className="size-4 shrink-0 fill-primary-03" />
                                    {err}
                                </div>
                            )}
                            <Button isBlack disabled={disabled} onClick={() => mut.mutate()}>
                                {mut.isPending ? "Connecting…" : "Connect"}
                            </Button>
                            {!canWrite && (
                                <div className="text-caption text-t-tertiary text-center">
                                    Ask an admin or manager to connect the workspace.
                                </div>
                            )}
                            <div className="text-caption text-t-tertiary text-center">
                                No Twenty account?{" "}
                                <a
                                    href="https://twenty.com"
                                    target="_blank"
                                    rel="noreferrer"
                                    className="text-primary-01 hover:underline"
                                >
                                    It&apos;s free &amp; open-source →
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
            </Card>
        </div>
    );
}
