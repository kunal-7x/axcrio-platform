"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Checkbox from "@/components/Checkbox";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
import Spinner from "@/components/Spinner";
import Table from "@/components/Table";
import TableRow from "@/components/TableRow";
import {
    getWebhooks,
    createWebhook,
    deleteWebhook,
    WEBHOOK_EVENTS,
    type Webhook,
} from "@/lib/api";
import { useMe, canWrite } from "@/lib/auth";

type Toast = { msg: string; type: "success" | "error" };

function fmt(d: string) {
    if (!d) return "—";
    try {
        return new Date(d).toLocaleString();
    } catch {
        return d;
    }
}

export default function WebhooksPage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [webhooks, setWebhooks] = useState<Webhook[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);

    // Create form
    const [url, setUrl] = useState("");
    const [secret, setSecret] = useState("");
    const [events, setEvents] = useState<string[]>(["call.completed"]);
    const [creating, setCreating] = useState(false);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        setLoadError("");
        getWebhooks()
            .then((r) => setWebhooks(r.webhooks))
            .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load webhooks"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    function toggleEvent(ev: string) {
        setEvents((prev) => (prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev]));
    }

    async function handleCreate(e: React.FormEvent) {
        e.preventDefault();
        if (!url.trim()) return;
        if (events.length === 0) {
            showToast("Select at least one event", "error");
            return;
        }
        setCreating(true);
        try {
            await createWebhook({ url: url.trim(), secret: secret.trim() || undefined, events });
            showToast("Webhook added", "success");
            setUrl("");
            setSecret("");
            setEvents(["call.completed"]);
            load();
        } catch (err: unknown) {
            showToast(err instanceof Error ? err.message : "Failed to add webhook", "error");
        } finally {
            setCreating(false);
        }
    }

    async function handleDelete(id: string) {
        if (!confirm("Delete this webhook?")) return;
        try {
            await deleteWebhook(id);
            showToast("Webhook deleted", "success");
            load();
        } catch (err: unknown) {
            showToast(err instanceof Error ? err.message : "Delete failed", "error");
        }
    }

    return (
        <Layout title="CRM Webhooks">
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="mb-4 flex items-start gap-3 p-4 rounded-3xl bg-b-surface2 border border-s-subtle text-body-2 text-t-secondary">
                <Icon className="shrink-0 mt-0.5 fill-primary-01" name="info" />
                <div>
                    Every payload is signed. Verify the <span className="text-t-primary">X-Famit-Signature</span> header (HMAC-SHA256 of the raw body using your secret); the event name is also sent in <span className="text-t-primary">X-Famit-Event</span>.
                </div>
            </div>

            <div className="flex gap-3 max-lg:flex-col">
                {/* List */}
                <div className="flex-1 min-w-0">
                    <div className="card">
                        <div className="flex items-center min-h-12">
                            <div className="pl-5 text-h6 max-lg:pl-3 mr-auto">Registered webhooks</div>
                        </div>

                        {loadError ? (
                            <div className="mx-5 my-4 flex items-center gap-3 p-4 rounded-3xl bg-b-surface2 border border-primary-03/40 text-body-2 text-t-secondary max-lg:mx-3">
                                <Icon className="shrink-0 fill-primary-03" name="info" />
                                <span className="text-t-primary">{loadError}</span>
                            </div>
                        ) : loading ? (
                            <div className="py-16"><Spinner /></div>
                        ) : webhooks.length === 0 ? (
                            <div className="flex flex-col items-center text-center py-16 px-5">
                                <div className="flex justify-center items-center size-16 mb-4 rounded-full bg-b-surface1">
                                    <Icon className="fill-t-secondary" name="link" />
                                </div>
                                <div className="text-sub-title-1 text-t-primary">No webhooks yet</div>
                                <div className="mt-1 text-body-2 text-t-secondary max-w-80">
                                    Register an endpoint on the right to start receiving signed events.
                                </div>
                            </div>
                        ) : (
                            <div className="p-1 pt-3 max-lg:px-0">
                                <Table
                                    cellsThead={
                                        <>
                                            <th>URL</th>
                                            <th>Events</th>
                                            <th>Active</th>
                                            <th>Created</th>
                                            {writable && <th className="text-right">Action</th>}
                                        </>
                                    }
                                >
                                    {webhooks.map((w) => (
                                        <TableRow key={w.id}>
                                            <td className="font-medium text-t-primary break-all max-w-xs">{w.url}</td>
                                            <td>
                                                <div className="flex flex-wrap gap-1">
                                                    {w.events.map((ev) => (
                                                        <Badge key={ev} variant="neutral">{ev}</Badge>
                                                    ))}
                                                </div>
                                            </td>
                                            <td>
                                                <Badge variant={w.active ? "success" : "neutral"} dot={w.active}>
                                                    {w.active ? "active" : "off"}
                                                </Badge>
                                            </td>
                                            <td className="text-t-secondary whitespace-nowrap">{fmt(w.created_at)}</td>
                                            {writable && (
                                                <td className="text-right">
                                                    <Button
                                                        isStroke
                                                        className="!h-9 !px-4 !text-body-2 !font-normal hover:!border-primary-03/40 hover:!text-primary-03"
                                                        onClick={() => handleDelete(w.id)}
                                                    >
                                                        Delete
                                                    </Button>
                                                </td>
                                            )}
                                        </TableRow>
                                    ))}
                                </Table>
                            </div>
                        )}
                    </div>
                </div>

                {/* Create */}
                {writable && (
                    <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0">
                        <Card title="Add webhook">
                            <form onSubmit={handleCreate} className="flex flex-col gap-6 p-5 pt-3 max-lg:px-3">
                                <Field
                                    label="Endpoint URL"
                                    type="url"
                                    placeholder="https://crm.example.com/famit"
                                    value={url}
                                    onChange={(e) => setUrl(e.target.value)}
                                    required
                                />
                                <Field
                                    label="Secret (optional)"
                                    placeholder="auto-generated if blank"
                                    value={secret}
                                    onChange={(e) => setSecret(e.target.value)}
                                />
                                <div>
                                    <div className="mb-4 text-button">Events</div>
                                    <div className="flex flex-col gap-3">
                                        {WEBHOOK_EVENTS.map((ev) => (
                                            <Checkbox
                                                key={ev}
                                                label={ev}
                                                checked={events.includes(ev)}
                                                onChange={() => toggleEvent(ev)}
                                            />
                                        ))}
                                    </div>
                                </div>
                                <Button isBlack className="w-full" disabled={creating}>
                                    {creating ? "Adding…" : "Add webhook"}
                                </Button>
                            </form>
                        </Card>
                    </div>
                )}
            </div>
        </Layout>
    );
}
