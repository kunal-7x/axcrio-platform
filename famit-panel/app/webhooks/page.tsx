"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
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

    const inputCls = "w-full h-11 px-4 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent";

    return (
        <Layout title="CRM Webhooks">
            {toast && (
                <div className={`mb-4 p-3 rounded-2xl text-body-2 flex items-center justify-between gap-3 ${
                    toast.type === "success"
                        ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                        : "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                }`}>
                    <span>{toast.msg}</span>
                    <button onClick={() => setToast(null)} className="shrink-0 opacity-60 hover:opacity-100 text-lg leading-none">×</button>
                </div>
            )}

            <div className="mb-4 p-3 rounded-2xl bg-blue-50 text-blue-700 text-body-2 dark:bg-blue-900/20 dark:text-blue-400">
                Each payload is signed — verify the <code className="font-mono">X-Famit-Signature</code> header (HMAC-SHA256 of the raw body using your secret). The event name is also sent in <code className="font-mono">X-Famit-Event</code>.
            </div>

            <div className="flex gap-6 max-lg:flex-col">
                {/* List */}
                <div className="flex-1 min-w-0">
                    <Card title="Registered Webhooks">
                        {loadError && (
                            <div className="mx-5 mb-3 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">{loadError}</div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                                <thead>
                                    <tr>
                                        <th>URL</th>
                                        <th>Events</th>
                                        <th>Active</th>
                                        <th>Created</th>
                                        {writable && <th></th>}
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        <tr><td colSpan={writable ? 5 : 4} className="py-8 text-center text-t-secondary">Loading…</td></tr>
                                    ) : webhooks.length === 0 ? (
                                        <tr><td colSpan={writable ? 5 : 4} className="py-12 text-center text-t-tertiary">No webhooks yet</td></tr>
                                    ) : (
                                        webhooks.map((w) => (
                                            <tr key={w.id} className="border-t border-s-subtle hover:bg-b-surface2/50 transition-colors">
                                                <td className="font-medium break-all max-w-xs">{w.url}</td>
                                                <td>
                                                    <div className="flex flex-wrap gap-1">
                                                        {w.events.map((ev) => (
                                                            <span key={ev} className="inline-flex px-2 py-0.5 rounded-full text-caption font-medium bg-b-surface3 text-t-secondary">{ev}</span>
                                                        ))}
                                                    </div>
                                                </td>
                                                <td>
                                                    <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${w.active ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" : "bg-b-surface3 text-t-secondary"}`}>
                                                        {w.active ? "active" : "off"}
                                                    </span>
                                                </td>
                                                <td className="text-t-secondary">{fmt(w.created_at)}</td>
                                                {writable && (
                                                    <td>
                                                        <button onClick={() => handleDelete(w.id)} className="text-caption text-red-500 hover:text-red-700 transition-colors">Delete</button>
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
