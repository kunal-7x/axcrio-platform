"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import { provision } from "../client";

// Self-hosted (zero-touch) setup state. Twenty runs inside Haptica, so there is no
// API key to paste — the panel just provisions this tenant's OWN isolated workspace
// on first open. For a writer it auto-fires; a read-only user waits for their team.
export default function SetupPanel({ canWrite }: { canWrite: boolean }) {
    const qc = useQueryClient();
    const [err, setErr] = useState("");
    const [capacity, setCapacity] = useState(false);
    const fired = useRef(false);

    const mut = useMutation({
        mutationFn: provision,
        onSuccess: () => {
            setErr("");
            qc.invalidateQueries({ queryKey: ["twenty"] });
        },
        onError: (e: unknown) => {
            const m = e instanceof Error ? e.message : "Setup failed";
            setErr(m);
            setCapacity(/capacity|limit|reached/i.test(m));
        },
    });

    // Auto-provision once for a writer (the zero-touch path).
    useEffect(() => {
        if (canWrite && !fired.current) {
            fired.current = true;
            mut.mutate();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [canWrite]);

    // Read-only users can't provision — poll status so the page flips the moment a
    // teammate finishes setup.
    useEffect(() => {
        if (canWrite) return;
        const id = setInterval(
            () => qc.invalidateQueries({ queryKey: ["twenty", "status"] }),
            5000
        );
        return () => clearInterval(id);
    }, [canWrite, qc]);

    const busy = mut.isPending;

    return (
        <Card title="Sales CRM">
            <div className="grid place-items-center py-20 px-6 text-center max-md:py-14">
                {err ? (
                    <>
                        <span className="grid place-items-center size-14 mb-4 rounded-full bg-primary-03/12">
                            <Icon name="info" className="fill-primary-03" />
                        </span>
                        <div className="text-h6 mb-1">
                            {capacity ? "CRM capacity reached" : "Couldn’t set up your CRM"}
                        </div>
                        <div className="max-w-md text-body-2 text-t-secondary">
                            {capacity
                                ? "This Haptica server hosts up to 5 isolated CRM workspaces. Contact support to add capacity."
                                : err}
                        </div>
                        {canWrite && !capacity && (
                            <Button
                                className="mt-6"
                                isBlack
                                disabled={busy}
                                onClick={() => mut.mutate()}
                            >
                                {busy ? "Retrying…" : "Try again"}
                            </Button>
                        )}
                    </>
                ) : canWrite ? (
                    <>
                        <span className="relative grid place-items-center size-16 mb-5">
                            <span className="absolute inset-0 rounded-full border-2 border-primary-01/20" />
                            <span className="absolute inset-0 rounded-full border-2 border-transparent border-t-primary-01 animate-spin" />
                            <Icon name="chart" className="fill-primary-01" />
                        </span>
                        <div className="text-h5 mb-2">Setting up your CRM…</div>
                        <div className="max-w-md text-body-2 text-t-secondary">
                            Creating your private, self-hosted sales workspace inside Haptica. This
                            takes a few seconds — no account, no API key. It’ll open automatically.
                        </div>
                    </>
                ) : (
                    <>
                        <span className="grid place-items-center size-14 mb-4 rounded-full bg-b-surface1">
                            <Icon name="clock" className="fill-t-tertiary" />
                        </span>
                        <div className="text-h6 mb-1">Your CRM is being prepared</div>
                        <div className="max-w-md text-body-2 text-t-secondary">
                            An admin or manager on your team is setting up the sales workspace. This
                            page opens automatically once it’s ready.
                        </div>
                    </>
                )}
            </div>
        </Card>
    );
}
