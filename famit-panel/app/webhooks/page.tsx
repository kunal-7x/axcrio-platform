"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import PageHeader from "@/components/PageHeader";
import Icon from "@/components/Icon";
import Badge from "@/components/Badge";
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

    const inputCls = "input-base w-full h-11 px-4 rounded-2xl text-body-2";

    return (
        <Layout title="CRM Webhooks">
            <PageHeader
                eyebrow="Integrations"
                title="CRM Webhooks"
                subtitle="Push call outcomes, qualified leads and callbacks to your CRM in real time — every payload is HMAC-signed."
            />
            {toast && (
                <div className={`toast ${toast.type === "success" ? "toast-success" : "toast-error"}`}>
                    <span className="flex items-center gap-2">
                        <span className="size-1.5 rounded-full bg-current" />
                        {toast.msg}
                    </span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="mb-4 p-3.5 rounded-2xl border border-[#2A85FF]/20 bg-[#2A85FF]/8 text-t-secondary text-body-2">
                Each payload is signed — verify the <code className="font-mono text-t-primary">X-Famit-Signature</code> header (HMAC-SHA256 of the raw body using your secret). The event name is also sent in <code className="font-mono text-t-primary">X-Famit-Event</code>.
            </div>

            <div className="flex gap-6 max-lg:flex-col">
                {/* List */}
                <div className="flex-1 min-w-0">
                    <Card title="Registered Webhooks">
                        {loadError && (
                            <div className="mx-5 mb-3 toast toast-error"><span className="flex items-center gap-2"><span className="size-1.5 rounded-full bg-current" />{loadError}</span></div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>URL</th>
                                        <th>Events</th>
                                        <th>Active</th>
                                        <th>Created</th>
                                        {writable && <th className="text-right">Action</th>}
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        [...Array(3)].map((_, i) => (
                                            <tr key={i}>
                                                {[...Array(writable ? 5 : 4)].map((__, j) => (
                                                    <td key={j}><div className="skeleton h-4 w-24" /></td>
                                                ))}
                                            </tr>
                                        ))
                                    ) : webhooks.length === 0 ? (
                                        <tr><td colSpan={writable ? 5 : 4}>
                                            <div className="state-block">
                                                <span className="state-glyph"><Icon name="link" className="fill-inherit" /></span>
                                                <div className="state-title">No webhooks yet</div>
                                                <div className="state-sub">Register an endpoint on the right to start receiving signed events.</div>
                                            </div>
                                        </td></tr>
                                    ) : (
                                        webhooks.map((w) => (
                                            <tr key={w.id}>
                                                <td className="font-medium text-t-primary break-all max-w-xs">{w.url}</td>
                                                <td>
                                                    <div className="flex flex-wrap gap-1">
                                                        {w.events.map((ev) => (
                                                            <span key={ev} className="pill pill-neutral">{ev}</span>
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
                                                    <td>
                                                        <div className="flex justify-end">
                                                            <button onClick={() => handleDelete(w.id)} className="action hover:!text-primary-03 hover:!border-primary-03/30">Delete</button>
                                                        </div>
                                                    </td>
                                                )}
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>

                {/* Create */}
                {writable && (
                    <div className="w-96 max-lg:w-full shrink-0">
                        <Card title="Add Webhook">
                            <form onSubmit={handleCreate} className="px-5 pb-5 space-y-4">
                                <div>
                                    <label className="block text-button mb-3 text-t-primary">Endpoint URL</label>
                                    <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://crm.example.com/famit" className={inputCls} required />
                                </div>
                                <div>
                                    <label className="block text-button mb-3 text-t-primary">Secret (optional)</label>
                                    <input type="text" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="auto-generated if blank" className={inputCls} />
                                </div>
                                <div>
                                    <label className="block text-button mb-3 text-t-primary">Events</label>
                                    <div className="space-y-2">
                                        {WEBHOOK_EVENTS.map((ev) => (
                                            <label key={ev} className="flex items-center gap-3 cursor-pointer">
                                                <input type="checkbox" className="w-4 h-4 rounded" checked={events.includes(ev)} onChange={() => toggleEvent(ev)} />
                                                <span className="text-body-2 text-t-primary font-mono text-xs">{ev}</span>
                                            </label>
                                        ))}
                                    </div>
                                </div>
                                <Button isBlack className="w-full justify-center" disabled={creating}>
                                    {creating ? "Adding…" : "Add Webhook"}
                                </Button>
                            </form>
                        </Card>
                    </div>
                )}
            </div>
        </Layout>
    );
}
