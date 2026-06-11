"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Icon from "@/components/Icon";
import Tabs from "@/components/Tabs";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import { StatusBadge } from "@/lib/badges";
import { getCallbacks, cancelCallback, type CallbackEntry } from "@/lib/api";
import { type TabsOption } from "@/types/tabs";

function fmt(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

const VIEWS: TabsOption[] = [
    { id: 1, name: "Callbacks" },
    { id: 2, name: "All retries" },
];

export default function CallbacksPage() {
    const [items, setItems] = useState<CallbackEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [view, setView] = useState<TabsOption>(VIEWS[0]);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

    const showAll = view.id === 2;

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        getCallbacks(showAll)
            .then((r) => setItems(r.items))
            .catch(() => {})
            .finally(() => setLoading(false));
    }, [showAll]);

    useEffect(() => {
        load();
    }, [load]);

    async function handleCancel(id: string) {
        if (!confirm("Cancel this scheduled callback/retry?")) return;
        try {
            await cancelCallback(id);
            showToast("Cancelled");
            load();
        } catch {
            showToast("Failed to cancel", false);
        }
    }

    const tableHead = useMemo(
        () => (
            <>
                <th>Name</th>
                <th>Phone</th>
                <th className="max-lg:hidden">Campaign</th>
                <th>Scheduled for</th>
                <th className="max-md:hidden">Reason</th>
                <th className="max-lg:hidden">Attempts</th>
                <th className="text-right">Action</th>
            </>
        ),
        []
    );

    return (
        <Layout title="Callbacks">
            {toast && (
                <div
                    className={`mb-3 flex items-center gap-2 p-3.5 rounded-3xl text-body-2 ${
                        toast.ok
                            ? "bg-primary-02/8 text-primary-02"
                            : "bg-primary-03/8 text-primary-03"
                    }`}
                >
                    <Icon
                        name={toast.ok ? "check-circle" : "info"}
                        className={`size-4 shrink-0 ${
                            toast.ok ? "fill-primary-02" : "fill-primary-03"
                        }`}
                    />
                    {toast.msg}
                </div>
            )}

            <div className="card">
                <div className="flex items-center min-h-12 max-md:flex-wrap">
                    <div className="mr-auto pl-5 text-h6 max-lg:pl-3">
                        Scheduled callbacks
                    </div>
                    <Tabs items={VIEWS} value={view} setValue={setView} />
                </div>

                <div className="pt-3 overflow-x-auto">
                    {loading ? (
                        <div className="px-1 max-lg:px-0">
                            <Table cellsThead={tableHead}>
                                {[...Array(4)].map((_, i) => (
                                    <TableRow key={i}>
                                        {[...Array(7)].map((__, j) => (
                                            <td key={j}>
                                                <div className="skeleton h-4 w-20" />
                                            </td>
                                        ))}
                                    </TableRow>
                                ))}
                            </Table>
                        </div>
                    ) : items.length === 0 ? (
                        <div className="state-block">
                            <span className="state-glyph">
                                <Icon name="calendar" className="fill-inherit" />
                            </span>
                            <div className="state-title">
                                No scheduled callbacks
                            </div>
                            <div className="state-sub">
                                Callbacks and automatic retries scheduled by the
                                dialer appear here.
                            </div>
                        </div>
                    ) : (
                        <div className="px-1 max-lg:px-0">
                            <Table cellsThead={tableHead}>
                                {items.map((item) => (
                                    <TableRow key={item.id}>
                                        <td className="text-sub-title-1">
                                            {item.name || "—"}
                                        </td>
                                        <td className="text-t-secondary td-num">
                                            {item.phone}
                                        </td>
                                        <td className="text-t-secondary text-caption max-lg:hidden">
                                            {item.campaign_id}
                                        </td>
                                        <td className="text-t-secondary whitespace-nowrap">
                                            {fmt(item.next_attempt_at)}
                                        </td>
                                        <td className="max-md:hidden">
                                            <StatusBadge status={item.reason} />
                                        </td>
                                        <td className="text-t-secondary td-num max-lg:hidden">
                                            {item.attempts} / {item.max_attempts}
                                        </td>
                                        <td className="text-right">
                                            <Button
                                                isStroke
                                                className="!h-9 !px-4"
                                                onClick={() =>
                                                    handleCancel(item.id)
                                                }
                                            >
                                                Cancel
                                            </Button>
                                        </td>
                                    </TableRow>
                                ))}
                            </Table>
                        </div>
                    )}
                </div>
            </div>
        </Layout>
    );
}
