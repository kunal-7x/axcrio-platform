// ⑨ SCHEDULING — when to send. Send-now vs Schedule (Tabs), date-time, optional
// send-window/throttle, batch summary. The "Send now" path is LIVE today via
// /api/whatsapp/send (the proven send endpoint). Scheduling parks the run for a
// future job when the scheduler lands (degrades to a calm note today).

"use client";

import { useState } from "react";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Field from "@/components/Field";
import Tabs from "@/components/Tabs";
import Select from "@/components/Select";
import Icon from "@/components/Icon";
import Modal from "@/components/Modal";
import { type TabsOption } from "@/types/tabs";
import { type SelectOption } from "@/types/select";
import { sendWhatsApp } from "@/lib/api";
import { type StepCtx } from "../_lib/types";

const MODES: TabsOption[] = [
    { id: 1, name: "Send now" },
    { id: 2, name: "Schedule" },
];
const WINDOWS: SelectOption[] = [
    { id: 1, name: "Any time" },
    { id: 2, name: "Business hours (9am–7pm)" },
    { id: 3, name: "Throttled (respect WA limits)" },
];

export default function ScheduleStep({ draft, goTo, writable, notify }: StepCtx) {
    const [mode, setMode] = useState<TabsOption>(MODES[0]);
    const [when, setWhen] = useState("");
    const [window, setWindow] = useState<SelectOption>(WINDOWS[0]);
    const [confirm, setConfirm] = useState(false);
    const [busy, setBusy] = useState(false);
    const [to, setTo] = useState("");

    const isNow = mode.id === 1;

    async function send() {
        setBusy(true);
        try {
            // LIVE send path — the proven /api/whatsapp/send endpoint. A single
            // recipient send (or a test send to a number) works today; the
            // campaign-list blast resolves the audience server-side in the wired build.
            const res = await sendWhatsApp({
                to: to.trim(),
                text: draft.body.trim() || undefined,
                template: draft.name || undefined,
            });
            if (res.status === "skipped_no_config" || !res.configured) {
                notify("WhatsApp not connected — add provider credentials on the server.", "error");
            } else {
                notify(`Message ${res.status} to ${res.to}`, "success");
                goTo("delivery");
            }
        } catch (e) {
            notify(e instanceof Error ? e.message : "Failed to send", "error");
        } finally {
            setBusy(false);
            setConfirm(false);
        }
    }

    return (
        <>
            <div className="flex gap-3 max-lg:flex-col">
                <div className="flex-1 min-w-0">
                    <Card title="When to send">
                        <div className="flex flex-col gap-6 px-5 pb-5 pt-2 max-lg:px-3">
                            <Tabs items={MODES} value={mode} setValue={setMode} />

                            {!isNow && (
                                <Field
                                    label="Date & time"
                                    type="datetime-local"
                                    value={when}
                                    onChange={(e) => setWhen(e.target.value)}
                                />
                            )}

                            <Select label="Send window" value={window} onChange={setWindow} options={WINDOWS} />

                            <Field
                                label="Send to (test / single recipient)"
                                placeholder="+919876543210"
                                value={to}
                                onChange={(e) => setTo(e.target.value)}
                            />

                            {!isNow && (
                                <div className="flex items-start gap-2.5 p-3.5 rounded-3xl bg-b-surface1 text-caption text-t-tertiary">
                                    <Icon className="shrink-0 mt-px fill-t-tertiary !size-4" name="clock" />
                                    Scheduled sends run from the server queue. Until the scheduler is connected, use Send now.
                                </div>
                            )}
                        </div>
                    </Card>
                </div>

                {/* summary */}
                <div className="w-100 max-3xl:w-90 max-lg:w-full shrink-0">
                    <Card title="Summary">
                        <div className="flex flex-col divide-y divide-s-subtle px-5 pb-5 pt-1 max-lg:px-3">
                            {[
                                { k: "Template", v: draft.name || "Untitled" },
                                { k: "Banner", v: draft.asset_url ? "Attached" : "None" },
                                { k: "Language", v: draft.language || "English" },
                                { k: "When", v: isNow ? "Send now" : when || "Not set" },
                                { k: "Window", v: window.name },
                            ].map((r) => (
                                <div key={r.k} className="flex items-center gap-3 py-2.5">
                                    <div className="w-24 shrink-0 text-caption text-t-tertiary">{r.k}</div>
                                    <div className="grow text-body-2 text-t-primary truncate">{r.v}</div>
                                </div>
                            ))}
                            {writable && (
                                <div className="pt-4">
                                    <Button
                                        isBlack
                                        className="w-full"
                                        disabled={busy || !to.trim()}
                                        onClick={() => setConfirm(true)}
                                    >
                                        {isNow ? "Send now" : "Schedule send"}
                                    </Button>
                                </div>
                            )}
                        </div>
                    </Card>
                </div>
            </div>

            <Modal open={confirm} onClose={() => setConfirm(false)}>
                <div className="text-center">
                    <div className="flex justify-center items-center size-14 mx-auto mb-5 rounded-full bg-b-surface2">
                        <Icon className="fill-t-secondary" name="send" />
                    </div>
                    <div className="text-h5 text-t-primary">{isNow ? "Send this message now?" : "Schedule this send?"}</div>
                    <div className="mt-2 max-w-90 mx-auto text-body-2 text-t-secondary">
                        Sending to {to || "the selected recipient"}. WhatsApp message fees apply per recipient.
                    </div>
                    <div className="flex gap-3 justify-center mt-8">
                        <Button isStroke onClick={() => setConfirm(false)}>Cancel</Button>
                        <Button isBlack disabled={busy} onClick={send}>{busy ? "Sending…" : "Confirm"}</Button>
                    </div>
                </div>
            </Modal>
        </>
    );
}
