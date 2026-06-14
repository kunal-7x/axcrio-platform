"use client";

// Builder view — the author-once message/template composer (master-plan §7).
// Write the message once with {variables}; attach a banner / video / PDF; add URL
// buttons; watch the live TelegramPreview render exactly what the contact sees;
// fire a "test send to me". W3-4 extends this into the full multi-channel
// per-channel render — the seam (per-channel preview) is here from day one.
// Core_2, Inter Display, zero raw hex.

import { useMemo, useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Field from "@/components/Field";
import Spinner from "@/components/Spinner";
import { sendMessage, CommError } from "@/lib/communication";
import TelegramPreview, { type PreviewButton } from "../_components/TelegramPreview";
import { ghostBtnCls, textBtnCls, ConsentBadge } from "../_shared";

type Toast = (msg: string, type?: "success" | "error") => void;

const VARIABLES = [
    { token: "{name}", label: "Contact name" },
    { token: "{phone}", label: "Phone" },
    { token: "{company}", label: "Your company" },
    { token: "{summary}", label: "Call summary" },
];

const SEED_TEMPLATES = [
    { name: "Post-call summary", body: "Hi {name}, thanks for your time! Quick recap: {summary}. Reply here if you'd like to go ahead." },
    { name: "Booking nudge", body: "Hi {name}, your slot with {company} is ready to confirm. Tap below to book." },
    { name: "Re-engagement", body: "Hi {name}, still thinking it over? I'm here on Telegram any time — happy to help." },
];

export default function BuilderView({ writable, onToast }: { writable: boolean; onToast: Toast }) {
    const [body, setBody] = useState(SEED_TEMPLATES[0].body);
    const [assetUrl, setAssetUrl] = useState("");
    const [assetKind, setAssetKind] = useState<"photo" | "video" | "document">("photo");
    const [buttons, setButtons] = useState<PreviewButton[]>([{ text: "Book now", url: "" }]);
    const [testTo, setTestTo] = useState("");
    const [busy, setBusy] = useState(false);

    const draft = useMemo(
        () => ({ body, asset_url: assetUrl || undefined, asset_kind: assetKind, buttons }),
        [body, assetUrl, assetKind, buttons],
    );

    const insertVar = (token: string) => setBody((b) => `${b}${b && !b.endsWith(" ") ? " " : ""}${token}`);

    const updateButton = (i: number, patch: Partial<PreviewButton>) =>
        setButtons((bs) => bs.map((b, j) => (j === i ? { ...b, ...patch } : b)));
    const addButton = () => setButtons((bs) => (bs.length >= 3 ? bs : [...bs, { text: "", url: "" }]));
    const removeButton = (i: number) => setButtons((bs) => bs.filter((_, j) => j !== i));

    const testSend = async () => {
        if (!writable) {
            onToast("You need manager access to send.", "error");
            return;
        }
        if (!testTo.trim()) {
            onToast("Add your chat id to test-send.", "error");
            return;
        }
        setBusy(true);
        try {
            // Sample-resolve the same way the preview does, so the test matches.
            const sampleBody = body
                .replace(/\{name\}/g, "Asha")
                .replace(/\{company\}/g, "your company")
                .replace(/\{summary\}/g, "EMI options for a 3BHK")
                .replace(/\{(\w+)\}/g, "—");
            const r = await sendMessage({
                to_ref: testTo.trim(),
                kind: assetUrl ? assetKind : "text",
                purpose: "service",
                text: sampleBody,
                media: assetUrl ? [{ url: assetUrl, kind: assetKind }] : undefined,
                buttons: buttons.filter((b) => b.text && b.url).map((b) => ({ text: b.text, url: b.url! })),
            });
            if (r.ok) onToast("Test sent — check your Telegram.");
            else onToast(r.error_code ? `Send: ${r.error_code}` : "Send failed.", "error");
        } catch (e) {
            onToast(e instanceof CommError ? e.message : "Send failed.", "error");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="grid grid-cols-[1fr_auto] gap-5 max-lg:grid-cols-1">
            {/* AUTHOR column */}
            <div className="flex flex-col gap-5 min-w-0">
                <Card title="Start from a template" classHead="!h-10">
                    <div className="px-5 pb-5 max-lg:px-3 flex items-center gap-2.5 flex-wrap">
                        {SEED_TEMPLATES.map((t) => (
                            <button
                                key={t.name}
                                onClick={() => setBody(t.body)}
                                className={textBtnCls}
                            >
                                <Icon name="magic-pencil" className="size-3.5 fill-inherit" />
                                {t.name}
                            </button>
                        ))}
                    </div>
                </Card>

                <Card title="Message">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <Field
                            textarea
                            classInput="!h-40"
                            placeholder="Write your message… use {name} for the contact's name"
                            value={body}
                            onChange={(e) => setBody(e.target.value)}
                        />
                        <div className="mt-3 flex items-center gap-2 flex-wrap">
                            <span className="text-caption text-t-tertiary mr-1">Insert:</span>
                            {VARIABLES.map((v) => (
                                <button
                                    key={v.token}
                                    onClick={() => insertVar(v.token)}
                                    title={v.label}
                                    className="inline-flex items-center h-7 px-2.5 rounded-full bg-b-surface2 ring-1 ring-s-subtle text-caption text-t-secondary transition-colors hover:text-t-primary hover:ring-s-highlight"
                                >
                                    {v.token}
                                </button>
                            ))}
                            <span className="ml-auto text-caption text-t-tertiary tabular-nums">{body.length} chars</span>
                        </div>
                    </div>
                </Card>

                <Card title="Media (optional)">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <div className="flex items-center gap-1 p-1 mb-4 rounded-full bg-b-surface2 ring-1 ring-s-subtle w-fit">
                            {(["photo", "video", "document"] as const).map((k) => (
                                <button
                                    key={k}
                                    onClick={() => setAssetKind(k)}
                                    className={`inline-flex items-center gap-1.5 h-8 px-3.5 rounded-full text-button capitalize transition-colors ${
                                        assetKind === k
                                            ? "bg-b-surface1 text-t-primary shadow-widget dark:bg-shade-04"
                                            : "text-t-secondary hover:text-t-primary"
                                    }`}
                                >
                                    <Icon
                                        name={k === "video" ? "video" : k === "document" ? "upload" : "camera"}
                                        className="!size-3.5 fill-inherit"
                                    />
                                    {k}
                                </button>
                            ))}
                        </div>
                        <Field
                            label="Media URL"
                            tooltip="A presigned Spaces / CDN URL — never a base64 blob."
                            placeholder="https://…/banner.png"
                            value={assetUrl}
                            onChange={(e) => setAssetUrl(e.target.value)}
                        />
                        <p className="mt-2 text-caption text-t-tertiary">
                            Banners and brochures re-send for free after the first upload (Telegram caches them).
                        </p>
                    </div>
                </Card>

                <Card title="Buttons">
                    <div className="px-5 pb-5 max-lg:px-3 flex flex-col gap-3">
                        {buttons.map((b, i) => (
                            <div key={i} className="flex items-end gap-2.5">
                                <Field
                                    className="w-44 max-md:w-32"
                                    label={i === 0 ? "Label" : undefined}
                                    placeholder="Book now"
                                    value={b.text}
                                    onChange={(e) => updateButton(i, { text: e.target.value })}
                                />
                                <Field
                                    className="grow"
                                    label={i === 0 ? "URL" : undefined}
                                    placeholder="https://…"
                                    value={b.url || ""}
                                    onChange={(e) => updateButton(i, { url: e.target.value })}
                                />
                                <button
                                    onClick={() => removeButton(i)}
                                    className="flex justify-center items-center size-12 rounded-full text-t-tertiary fill-t-tertiary transition-colors hover:text-primary-03 hover:fill-primary-03 shrink-0"
                                    title="Remove"
                                >
                                    <Icon name="trash" className="size-4 fill-inherit" />
                                </button>
                            </div>
                        ))}
                        {buttons.length < 3 && (
                            <button className={textBtnCls} onClick={addButton}>
                                <Icon name="plus" className="size-3.5 fill-inherit" />
                                Add button
                            </button>
                        )}
                    </div>
                </Card>

                <Card title="Test send">
                    <div className="px-5 pb-5 max-lg:px-3">
                        <div className="flex items-center gap-2 mb-3">
                            <ConsentBadge purpose="service" />
                            <span className="text-caption text-t-tertiary">
                                Test sends only go to your own chat id — never to a contact.
                            </span>
                        </div>
                        <div className="flex items-end gap-3 flex-wrap">
                            <Field
                                className="w-56 max-md:w-full"
                                label="Your chat id"
                                placeholder="your chat id"
                                value={testTo}
                                onChange={(e) => setTestTo(e.target.value)}
                            />
                            <button className={ghostBtnCls} onClick={testSend} disabled={!writable || busy}>
                                {busy ? <Spinner /> : <Icon name="send" className="size-4 fill-inherit" />}
                                Send to me
                            </button>
                        </div>
                    </div>
                </Card>
            </div>

            {/* PREVIEW column — sticky live preview */}
            <div className="w-90 max-3xl:w-76 max-lg:w-full">
                <div className="sticky top-22 flex flex-col gap-3">
                    <div className="flex items-center gap-2 text-caption text-t-tertiary">
                        <Icon name="send" className="!size-3.5 fill-t-tertiary" />
                        Live Telegram preview
                    </div>
                    <TelegramPreview draft={draft} />
                </div>
            </div>
        </div>
    );
}
