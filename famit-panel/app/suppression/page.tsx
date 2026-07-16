"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Search from "@/components/Search";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";

import { getSuppression, addSuppression, deleteSuppression, type SuppressionEntry } from "@/lib/api";

// DND reasons -> ONE badge language (token-based, no raw colors).
function ReasonBadge({ reason }: { reason: string }) {
    const variant =
        reason === "opt_out_call" ? "danger"
        : reason === "manual" ? "warning"
        : reason === "api" ? "info"
        : "neutral";
    return <Badge variant={variant}>{reason.replace(/_/g, " ")}</Badge>;
}

function fmtDate(d: string) {
    if (!d) return "—";
    try { return new Date(d).toLocaleDateString(); } catch { return d; }
}

export default function SuppressionPage() {
    const [entries, setEntries] = useState<SuppressionEntry[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [text, setText] = useState("");
    const [file, setFile] = useState<File | null>(null);
    const [adding, setAdding] = useState(false);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const showToast = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        getSuppression()
            .then((r) => { setEntries(r.numbers); setTotal(r.total); })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => { load(); }, [load]);

    async function handleAdd() {
        if (!text.trim() && !file) return;
        setAdding(true);
        try {
            const r = await addSuppression(text, file);
            showToast(`Added ${r.added} number(s). Total: ${r.total}`);
            setText("");
            setFile(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
            load();
        } catch (e: unknown) {
            showToast(e instanceof Error ? e.message : "Failed to add", false);
        } finally {
            setAdding(false);
        }
    }

    async function handleDelete(phone: string) {
        if (!confirm(`Remove ${phone} from the Do-Not-Call list?`)) return;
        try {
            await deleteSuppression(phone);
            showToast(`Removed ${phone}`);
            load();
        } catch {
            showToast("Delete failed", false);
        }
    }

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return entries;
        return entries.filter((e) => (e.phone || "").toLowerCase().includes(q));
    }, [entries, search]);

    return (
        <Layout title="Do-Not-Call">
            {toast && (
                <div className={`toast ${toast.ok ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                </div>
            )}

            <div className="flex gap-3 max-lg:flex-col">
                {/* Left: suppression list */}
                <div className="flex-1 min-w-0">
                    <div className="card">
                        <div className="flex items-center min-h-12 max-md:flex-wrap max-md:gap-3">
                            <div className="pl-5 text-h6 max-lg:pl-3 mr-auto">
                                Suppressed numbers
                                <span className="ml-2 text-body-2 text-t-tertiary tabular-nums">{total}</span>
                            </div>
                            <Search
                                className="w-64 max-md:w-full max-md:order-3"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                                placeholder="Search by number"
                                isGray
                            />
                        </div>

                        {loading ? (
                            <div className="py-16"><Spinner /></div>
                        ) : filtered.length === 0 ? (
                            <div className="flex flex-col items-center text-center py-16 px-5">
                                <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-secondary" name="block" />
                                </div>
                                <div className="text-sub-title-1 text-t-primary">
                                    {search ? "No numbers match your search" : "No suppressed numbers"}
                                </div>
                                <div className="mt-1 text-body-2 text-t-secondary max-w-80">
                                    Add numbers on the right, or they appear here automatically when a lead opts out. Suppressed numbers are never dialed.
                                </div>
                            </div>
                        ) : (
                            <div className="p-1 pt-3 max-lg:px-0">
                                <Table
                                    cellsThead={
                                        <>
                                            <th>Phone</th>
                                            <th>Reason</th>
                                            <th>Source</th>
                                            <th>Added</th>
                                            <th className="text-right">Action</th>
                                        </>
                                    }
                                >
                                    {filtered.map((e) => (
                                        <TableRow key={e.phone}>
                                            <td className="font-medium text-t-primary tabular-nums">{e.phone}</td>
                                            <td><ReasonBadge reason={e.reason} /></td>
                                            <td className="text-t-secondary">{e.source || "—"}</td>
                                            <td className="text-t-secondary whitespace-nowrap">{fmtDate(e.added_at)}</td>
                                            <td className="text-right">
                                                <Button
                                                    isStroke
                                                    className="!h-9 !px-4 !text-body-2 !font-normal hover:!border-primary-03/40 hover:!text-primary-03"
                                                    onClick={() => handleDelete(e.phone)}
                                                >
                                                    Remove
                                                </Button>
                                            </td>
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        )}
                    </div>
                </div>

                {/* Right: Add numbers */}
                <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0">
                    <Card title="Add to Do-Not-Call">
                        <div className="flex flex-col gap-6 p-5 pt-3 max-lg:px-3">
                            <Field
                                label="Paste numbers (Name, Phone or bare phone per line)"
                                textarea
                                classInput="!h-32"
                                placeholder={"+919876543210\nJohn Doe, +918765432109"}
                                value={text}
                                onChange={(e) => setText(e.target.value)}
                            />

                            <div>
                                <div className="mb-4 text-button">Or upload CSV</div>
                                <div className="relative flex flex-col justify-center items-center h-32 bg-b-surface3 border border-transparent rounded-4xl overflow-hidden transition-colors hover:border-s-highlight">
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".csv,text/csv"
                                        className="absolute inset-0 opacity-0 cursor-pointer z-10"
                                        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                                    />
                                    <Icon className="mb-2 size-8 fill-t-secondary" name="upload" />
                                    <div className="text-body-2 text-t-secondary">
                                        {file ? (
                                            <span className="font-bold text-t-primary">{file.name}</span>
                                        ) : (
                                            <>Drop CSV, or <span className="font-bold text-t-primary">Browse</span></>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <Button
                                isBlack
                                className="w-full"
                                onClick={handleAdd}
                                disabled={adding || (!text.trim() && !file)}
                            >
                                {adding ? "Adding…" : "Add to Do-Not-Call"}
                            </Button>
                        </div>
                    </Card>
                </div>
            </div>
        </Layout>
    );
}
