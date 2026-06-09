"use client";

import { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import Button from "@/components/Button";
import {
    sendWhatsApp,
    getWhatsAppLog,
    type WhatsAppLogEntry,
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

export default function WhatsAppPage() {
    const { me } = useMe();
    const writable = canWrite(me);

    const [log, setLog] = useState<WhatsAppLogEntry[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [toast, setToast] = useState<Toast | null>(null);
    const [notConfigured, setNotConfigured] = useState(false);

    // Send form
    const [to, setTo] = useState("");
    const [mode, setMode] = useState<"template" | "text">("template");
    const [template, setTemplate] = useState("");
    const [text, setText] = useState("");
    const [params, setParams] = useState("");
    const [sending, setSending] = useState(false);

    const showToast = (msg: string, type: "success" | "error" = "success") => {
        setToast({ msg, type });
        setTimeout(() => setToast(null), 4000);
    };

    const load = useCallback(() => {
        setLoading(true);
        setLoadError("");
        getWhatsAppLog()
            .then((r) => setLog(r.log))
            .catch((e) => setLoadError(e instanceof Error ? e.message : "Failed to load log"))
            .finally(() => setLoading(false));
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    async function handleSend(e: React.FormEvent) {
        e.preventDefault();
        if (!to.trim()) return;
        setSending(true);
        try {
            const res = await sendWhatsApp({
                to: to.trim(),
                template: mode === "template" ? template.trim() || undefined : undefined,
                text: mode === "text" ? text.trim() || undefined : undefined,
                params: params.trim() || undefined,
            });
            if (res.status === "skipped_no_config" || !res.configured) {
                setNotConfigured(true);
                showToast("WhatsApp not configured — message was not sent.", "error");
            } else {
                showToast(`Message ${res.status} to ${res.to}`, "success");
            }
            load();
        } catch (err: unknown) {
            showToast(err instanceof Error ? err.message : "Failed to send", "error");
        } finally {
            setSending(false);
        }
    }

    const inputCls = "w-full h-11 px-4 border border-s-stroke2 rounded-full text-body-2 text-t-primary outline-none transition-colors hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent";

    // Surface the banner if any recent log entry shows skipped_no_config too.
    const anyUnconfigured = notConfigured || log.some((l) => l.status === "skipped_no_config");

    return (
        <Layout title="WhatsApp">
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

            {anyUnconfigured && (
                <div className="mb-4 p-3 rounded-2xl bg-amber-50 text-amber-700 text-body-2 dark:bg-amber-900/20 dark:text-amber-400">
                    WhatsApp not configured — paste your BSP credentials on the server (WA_API_URL / WA_API_KEY / WA_FROM in <code className="font-mono">.env</code>), then restart the service. Sending is wired and will work once creds are set.
                </div>
            )}

            <div className="flex gap-6 max-lg:flex-col">
                {/* Log */}
                <div className="flex-1 min-w-0">
                    <Card title="Sent Log">
                        {loadError && (
                            <div className="mx-5 mb-3 p-3 rounded-2xl bg-red-50 text-red-600 text-body-2 dark:bg-red-900/20 dark:text-red-400">{loadError}</div>
                        )}
                        <div className="overflow-x-auto">
                            <table className="w-full text-body-2 [&_th]:h-13 [&_th,&_td]:px-5 [&_th,&_td]:py-3 [&_th]:align-middle [&_th]:text-left [&_th]:text-caption [&_th]:text-t-tertiary/80 [&_th]:font-normal">
                                <thead>
                                    <tr>
                                        <th>When</th>
                                        <th>Phone</th>
                                        <th>Template</th>
                                        <th>Kind</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        <tr><td colSpan={5} className="py-8 text-center text-t-secondary">Loading…</td></tr>
                                    ) : log.length === 0 ? (
                                        <tr><td colSpan={5} className="py-12 text-center text-t-tertiary">No messages sent yet</td></tr>
                                    ) : (
                                        log.map((l, i) => (
                                            <tr key={i} className="border-t border-s-subtle hover:bg-b-surface2/50 transition-colors">
                                                <td className="text-t-secondary">{fmt(l.at)}</td>
                                                <td className="text-t-secondary">{l.phone}</td>
                                                <td className="font-mono text-xs">{l.template || "—"}</td>
                                                <td>
                                                    <span className="inline-flex px-2 py-0.5 rounded-full text-caption font-medium bg-b-surface3 text-t-secondary">{l.kind}</span>
                                                </td>
                                                <td>
                                                    <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${
                                                        l.ok ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                                                        : l.status === "skipped_no_config" ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                                                        : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                                                    }`}>{l.status}</span>
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                </div>

                {/* Send form */}
                {writable && (
                    <div className="w-96 max-lg:w-full shrink-0">
                        <Card title="Send a Message">
                            <form onSubmit={handleSend} className="px-5 pb-5 space-y-4">
                                <div>
                                    <label className="block text-button mb-3 text-t-primary">To (phone)</label>
                                    <input type="text" value={to} onChange={(e) => setTo(e.target.value)} placeholder="+919876543210" className={inputCls} required />
                                </div>
                                <div>
                                    <label className="block text-button mb-3 text-t-primary">Mode</label>
                                    <div className="flex gap-4">
                                        <label className="flex items-center gap-2 cursor-pointer">
                                            <input type="radio" checked={mode === "template"} onChange={() => setMode("template")} />
                                            <span className="text-body-2 text-t-primary">Template</span>
                                        </label>
                                        <label className="flex items-center gap-2 cursor-pointer">
                                            <input type="radio" checked={mode === "text"} onChange={() => setMode("text")} />
                                            <span className="text-body-2 text-t-primary">Free text</span>
                                        </label>
                                    </div>
                                </div>
                                {mode === "template" ? (
                                    <div>
                                        <label className="block text-button mb-3 text-t-primary">Template name</label>
                                        <input type="text" value={template} onChange={(e) => setTemplate(e.target.value)} placeholder="welcome_followup" className={inputCls} />
                                    </div>
                                ) : (
                                    <div>
                                        <label className="block text-button mb-3 text-t-primary">Text</label>
                                        <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Hi! Thanks for your interest…" className="w-full h-24 px-4 py-3 border border-s-stroke2 rounded-3xl text-body-2 text-t-primary outline-none resize-none hover:border-s-highlight focus:border-s-highlight placeholder:text-t-secondary/50 bg-transparent" />
                                    </div>
                                )}
                                <div>
                                    <label className="block text-button mb-3 text-t-primary">Params (comma / pipe sep)</label>
                                    <input type="text" value={params} onChange={(e) => setParams(e.target.value)} placeholder="Kunal, DLF Crest" className={inputCls} />
                                </div>
                                <Button isBlack className="w-full justify-center" disabled={sending}>
                                    {sending ? "Sending…" : "Send"}
                                </Button>
                            </form>
                        </Card>
                    </div>
                )}
            </div>
        </Layout>
    );
}
