"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import NoFound from "@/components/NoFound";
import Badge from "@/components/Badge";
import {
    getBillingAudit,
    postBillingSync,
    type BillingAuditVendor,
} from "@/lib/api";
import { useMe, isAdmin } from "@/lib/auth";
import { money, fmt, StatusBadge, ErrorBanner, BillingTabs } from "../_shared";

const tableHead = [
    "Vendor",
    "Status",
    "Last sync",
    "Internal",
    "Vendor-reported",
    "Difference",
    "Notes",
];

export default function BillingAuditPage() {
    const { me } = useMe();
    const admin = isAdmin(me);

    const [vendors, setVendors] = useState<BillingAuditVendor[]>([]);
    const [currency, setCurrency] = useState("");
    const [note, setNote] = useState("");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [syncing, setSyncing] = useState(false);
    const [syncMsg, setSyncMsg] = useState("");

    const load = useCallback(() => {
        setLoading(true);
        setError("");
        getBillingAudit()
            .then((r) => {
                setVendors(r.vendors);
                setCurrency(r.currency);
                setNote(r.note);
            })
            .catch((e) => setError(e instanceof Error ? e.message : "Failed to load audit"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    async function handleSync() {
        setSyncing(true);
        setSyncMsg("");
        try {
            const r = await postBillingSync();
            setSyncMsg(`Synced at ${fmt(r.synced_at)}`);
            load();
        } catch (e) {
            setSyncMsg(e instanceof Error ? e.message : "Sync failed");
        } finally {
            setSyncing(false);
        }
    }

    return (
        <Layout title="Audit">
            <BillingTabs />
            <ErrorBanner msg={error} />

            <Card
                title="Vendor reconciliation"
                headContent={
                    <div className="flex items-center gap-3 ml-auto">
                        {syncMsg && (
                            <span className="text-caption text-t-secondary max-md:hidden">
                                {syncMsg}
                            </span>
                        )}
                        <Button isStroke icon="clock" onClick={load} disabled={loading}>
                            {loading ? "Refreshing…" : "Refresh"}
                        </Button>
                        {admin && (
                            <Button isBlack onClick={handleSync} disabled={syncing}>
                                {syncing ? "Syncing…" : "Sync now"}
                            </Button>
                        )}
                    </div>
                }
            >
                {!loading && vendors.length === 0 ? (
                    <NoFound title="Nothing to reconcile" />
                ) : (
                    <>
                        <div className="px-5 pt-1 text-body-2 text-t-secondary max-lg:px-3">
                            {note ||
                                "Reconciles the internal metered ledger against each vendor's reported spend."}
                        </div>
                        <div className="p-1 pt-3 max-lg:px-0 max-md:pt-0">
                            <Table
                                cellsThead={tableHead.map((head) => (
                                    <th
                                        className="!h-12.5 nth-4:text-right nth-5:text-right nth-6:text-right max-lg:nth-3:hidden max-md:nth-5:hidden"
                                        key={head}
                                    >
                                        {head}
                                    </th>
                                ))}
                                isMobileVisibleTHead
                            >
                                {(loading ? PLACEHOLDER : vendors).map((v, idx) => {
                                    const delta =
                                        v.vendor_reported == null
                                            ? null
                                            : v.vendor_reported - v.internal_ledger_cost;
                                    return (
                                        <TableRow key={v.vendor || idx}>
                                            <td className="text-sub-title-2">
                                                {v.display_name || "—"}
                                            </td>
                                            <td>
                                                {v.vendor && (
                                                    <StatusBadge status={v.status} stale={v.stale} />
                                                )}
                                            </td>
                                            <td className="text-t-secondary whitespace-nowrap max-lg:hidden">
                                                {v.vendor ? fmt(v.synced_at) : "—"}
                                            </td>
                                            <td className="text-right text-sub-title-2 tabular-nums">
                                                {v.vendor ? money(v.internal_ledger_cost, currency) : "—"}
                                            </td>
                                            <td className="text-right text-t-secondary tabular-nums max-md:hidden">
                                                {v.vendor_reported == null
                                                    ? "—"
                                                    : money(v.vendor_reported, currency)}
                                            </td>
                                            <td className="text-right tabular-nums">
                                                {delta == null ? (
                                                    <span className="text-t-tertiary">—</span>
                                                ) : Math.abs(delta) < 0.005 ? (
                                                    <span className="text-primary-02">matched</span>
                                                ) : (
                                                    <span
                                                        className={
                                                            delta > 0
                                                                ? "text-primary-05"
                                                                : "text-primary-01"
                                                        }
                                                    >
                                                        {delta > 0 ? "+" : ""}
                                                        {money(delta, currency)}
                                                    </span>
                                                )}
                                            </td>
                                            <td>
                                                {!v.vendor ? (
                                                    <span className="text-t-tertiary">—</span>
                                                ) : v.error ? (
                                                    <Badge variant="danger">{v.error}</Badge>
                                                ) : v.stale ? (
                                                    <Badge variant="warning">Stale snapshot</Badge>
                                                ) : (
                                                    <Badge variant="success" dot>
                                                        OK
                                                    </Badge>
                                                )}
                                            </td>
                                        </TableRow>
                                    );
                                })}
                            </Table>
                        </div>
                    </>
                )}
            </Card>
        </Layout>
    );
}

const PLACEHOLDER: BillingAuditVendor[] = [...Array(4)].map(() => ({
    vendor: "",
    display_name: "",
    status: "not_configured" as const,
    synced_at: "",
    stale: false,
    error: "",
    internal_ledger_cost: 0,
    vendor_reported: null,
}));
