"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Tabs from "@/components/Tabs";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import { getStatus, getStages, disconnect, type ActivityTarget, type Stage } from "./client";
import ConnectPanel from "./_components/ConnectPanel";
import SetupPanel from "./_components/SetupPanel";
import PipelineBoard from "./_components/PipelineBoard";
import CompaniesView from "./_components/CompaniesView";
import PeopleView from "./_components/PeopleView";
import RecordDrawer from "./_components/RecordDrawer";
import { CreateRecordModal, ImportLeadsModal, type CreateKind } from "./_components/forms";

const TABS = [
    { id: 1, name: "Pipeline", key: "pipeline" as const },
    { id: 2, name: "Companies", key: "companies" as const },
    { id: 3, name: "People", key: "people" as const },
];

const NEW_KIND: Record<string, CreateKind> = {
    pipeline: "opportunity",
    companies: "company",
    people: "person",
};

export default function SalesCrmPage() {
    const qc = useQueryClient();
    const statusQ = useQuery({ queryKey: ["twenty", "status"], queryFn: getStatus });
    const connected = !!statusQ.data?.connected;
    const canWrite = statusQ.data?.can_write !== false;

    const stagesQ = useQuery({
        queryKey: ["twenty", "stages"],
        queryFn: getStages,
        enabled: connected,
    });
    const stages: Stage[] = stagesQ.data?.stages ?? [];

    const [tab, setTab] = useState(TABS[0]);
    const [drawer, setDrawer] = useState<{ type: ActivityTarget; id: string } | null>(null);
    const [create, setCreate] = useState<{ open: boolean; kind: CreateKind }>({
        open: false,
        kind: "opportunity",
    });
    const [importOpen, setImportOpen] = useState(false);

    const openRecord = (type: ActivityTarget, id: string) => setDrawer({ type, id });

    const disconnectMut = useMutation({
        mutationFn: disconnect,
        onSuccess: () => qc.invalidateQueries({ queryKey: ["twenty"] }),
    });

    const status = statusQ.data;
    const showImport = tab.key === "pipeline" || tab.key === "people";

    if (statusQ.isLoading) {
        return (
            <Layout title="Sales CRM">
                <div className="card">
                    <div className="p-5">
                        <div className="skeleton h-8 w-48 rounded-xl mb-4" />
                        <div className="skeleton h-40 rounded-2xl" />
                    </div>
                </div>
            </Layout>
        );
    }

    if (!connected) {
        return (
            <Layout title="Sales CRM">
                {statusQ.data?.self_host ? (
                    <SetupPanel canWrite={canWrite} />
                ) : (
                    <ConnectPanel canWrite={canWrite} />
                )}
            </Layout>
        );
    }

    return (
        <Layout title="Sales CRM">
            <div className="flex flex-col gap-3">
                {/* control bar */}
                <div className="card">
                    <div className="flex items-center gap-3 px-2 py-2 max-md:flex-wrap">
                        <div className="overflow-x-auto scrollbar-none">
                            <Tabs
                                items={TABS}
                                value={tab}
                                setValue={(v) => setTab(TABS.find((t) => t.id === v.id) ?? TABS[0])}
                            />
                        </div>
                        <div className="ml-auto flex items-center gap-2 pr-1 max-md:w-full max-md:justify-end">
                            <span
                                className="flex items-center gap-1.5 max-lg:hidden"
                                title={`Twenty · ${status?.key_masked || ""}${
                                    status?.source === "env" ? " (server)" : ""
                                }`}
                            >
                                <Badge variant="success" dot>
                                    Connected
                                </Badge>
                            </span>
                            {showImport && (
                                <Button isStroke icon="upload" onClick={() => setImportOpen(true)}>
                                    <span className="max-md:hidden">Import leads</span>
                                </Button>
                            )}
                            {canWrite && (
                                <Button
                                    isBlack
                                    icon="plus"
                                    onClick={() => setCreate({ open: true, kind: NEW_KIND[tab.key] })}
                                >
                                    New
                                </Button>
                            )}
                            {canWrite && status?.source === "tenant" && (
                                <Button
                                    isCircle
                                    isStroke
                                    icon="logout"
                                    title="Disconnect Twenty"
                                    onClick={() => {
                                        if (confirm("Disconnect this Twenty workspace from Haptica?"))
                                            disconnectMut.mutate();
                                    }}
                                />
                            )}
                        </div>
                    </div>
                </div>

                {/* content */}
                {tab.key === "pipeline" && (
                    <Card title="Pipeline">
                        <PipelineBoard canWrite={canWrite} onOpen={openRecord} />
                    </Card>
                )}
                {tab.key === "companies" && (
                    <Card title="Companies">
                        <CompaniesView canWrite={canWrite} onOpen={openRecord} />
                    </Card>
                )}
                {tab.key === "people" && (
                    <Card title="People">
                        <PeopleView canWrite={canWrite} onOpen={openRecord} />
                    </Card>
                )}

                {/* link back to the call-driven Customer 360 */}
                <Link
                    href="/crm"
                    className="flex items-center justify-center gap-2 py-2 text-body-2 text-t-tertiary transition-colors hover:text-t-primary"
                >
                    <Icon name="arrow" className="size-4 fill-t-tertiary rotate-180" />
                    Back to Customer 360 (call timeline)
                </Link>
            </div>

            <RecordDrawer
                target={drawer}
                stages={stages}
                canWrite={canWrite}
                onClose={() => setDrawer(null)}
                onOpen={openRecord}
            />
            <CreateRecordModal
                open={create.open}
                kind={create.kind}
                stages={stages}
                onClose={() => setCreate((c) => ({ ...c, open: false }))}
            />
            <ImportLeadsModal open={importOpen} onClose={() => setImportOpen(false)} />
        </Layout>
    );
}
