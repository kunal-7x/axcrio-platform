"use client";

// ============================================================================
// TelegramSetup — the channel-setup FLOW for Telegram (master-plan §7 + §9).
// A guided 3-step connect card:
//   1) Connect the bot   — Test the stored BotFather token via getMe (identity)
//   2) Find your chat     — derive the founder chat_id from getUpdates (after the
//                           founder taps Start on the bot) + register the webhook
//   3) Send me a test     — prove real reach to the founder's own Telegram
//
// SECURITY: the bot token is NEVER pasted/revealed in this UI — it lives AAD-
// encrypted in the live vault (W1-P0). The webhook secret_token is derived
// server-side. Every action is a single backend call; errors humanized.
// Dormant-safe: when COMM is off the parent renders a coming-soon card instead.
// Core_2, Inter Display, zero raw hex.
// ============================================================================

import { useState } from "react";
import Card from "@/components/Card";
import Icon from "@/components/Icon";
import Field from "@/components/Field";
import Spinner from "@/components/Spinner";
import {
    testTelegram,
    deriveChatId,
    setWebhook,
    sendMessage,
    mintDeeplink,
    CommError,
    type CommChannel,
} from "@/lib/communication";
import { ghostBtnCls, textBtnCls, StatusDot } from "../_shared";

type Toast = (msg: string, type?: "success" | "error") => void;

function StepRow({
    n,
    title,
    desc,
    done,
    children,
}: {
    n: number;
    title: string;
    desc: string;
    done?: boolean;
    children: React.ReactNode;
}) {
    return (
        <div className="flex gap-4 max-md:gap-3">
            <div className="flex flex-col items-center shrink-0">
                <span
                    className={`flex justify-center items-center size-8 rounded-full text-button tabular-nums transition-colors ${
                        done
                            ? "bg-primary-02/15 text-primary-02 fill-primary-02"
                            : "bg-b-surface2 ring-1 ring-s-subtle text-t-secondary"
                    }`}
                >
                    {done ? <Icon name="check" className="!size-4 fill-primary-02" /> : n}
                </span>
                <span className="grow w-px bg-s-subtle mt-2 last:hidden" />
            </div>
            <div className="grow pb-7 last:pb-0">
                <div className="text-button text-t-primary">{title}</div>
                <p className="mt-1 mb-3 text-body-2 text-t-secondary max-w-xl">{desc}</p>
                {children}
            </div>
        </div>
    );
}

export default function TelegramSetup({
    channel,
    writable,
    onToast,
}: {
    channel?: CommChannel;
    writable: boolean;
    onToast: Toast;
    onChanged?: () => void;
}) {
    const configured = !!channel?.configured;

    const [botName, setBotName] = useState<string>("");
    const [tested, setTested] = useState<boolean>(configured);
    const [chatId, setChatId] = useState<string>("");
    const [testTo, setTestTo] = useState<string>("");
    const [busy, setBusy] = useState<string>("");

    const guardWrite = () => {
        if (!writable) {
            onToast("You need manager access to change channels.", "error");
            return false;
        }
        return true;
    };

    const runTest = async () => {
        setBusy("test");
        try {
            const r = await testTelegram();
            if (r.ok) {
                setBotName(r.username);
                setTested(true);
                onToast(`Connected to @${r.username}.`);
            } else {
                onToast("Token didn't verify — check it with BotFather.", "error");
            }
        } catch (e) {
            onToast(e instanceof CommError ? e.message : "Test failed.", "error");
        } finally {
            setBusy("");
        }
    };

    const findChat = async () => {
        if (!guardWrite()) return;
        setBusy("chat");
        try {
            const r = await deriveChatId(true);
            if (r.found) {
                setChatId(r.chat_id);
                setTestTo((p) => p || r.chat_id);
                onToast("Found your chat — hot-lead alerts will reach you here.");
            } else {
                onToast("No chat yet — open Telegram, tap Start on your bot, then try again.", "error");
            }
        } catch (e) {
            onToast(e instanceof CommError ? e.message : "Couldn't read updates.", "error");
        } finally {
            setBusy("");
        }
    };

    const connectWebhook = async () => {
        if (!guardWrite()) return;
        setBusy("webhook");
        try {
            // The webhook URL is the public panel API base + the tenant path; the
            // backend derives the secret_token server-side and binds it to the bot.
            const origin = typeof window !== "undefined" ? window.location.origin : "";
            const url = `${origin}/api/comm/webhook/telegram`;
            const r = await setWebhook(url);
            if (r.ok) onToast("Inbound webhook registered — Riya can now reply.");
            else onToast(r.error ? `Webhook: ${r.error}` : "Webhook not set.", "error");
        } catch (e) {
            onToast(e instanceof CommError ? e.message : "Webhook failed.", "error");
        } finally {
            setBusy("");
        }
    };

    const sendTest = async () => {
        if (!guardWrite()) return;
        const to = (testTo || chatId).trim();
        if (!to) {
            onToast("Find your chat first, or paste a chat id.", "error");
            return;
        }
        setBusy("send");
        try {
            const r = await sendMessage({
                to_ref: to,
                kind: "text",
                purpose: "service",
                text: "✅ This is a test from your Haptica AI Communication setup. Real reach confirmed.",
            });
            if (r.ok) onToast("Sent — check your Telegram.");
            else onToast(r.error_code ? `Send: ${r.error_code}` : "Send failed.", "error");
        } catch (e) {
            onToast(e instanceof CommError ? e.message : "Send failed.", "error");
        } finally {
            setBusy("");
        }
    };

    return (
        <Card
            title="Telegram"
            headContent={
                <div className="mr-4 flex items-center gap-3">
                    <StatusDot ok={tested || configured} label={tested || configured ? "Connected" : "Awaiting token"} />
                </div>
            }
        >
            <div className="px-5 pb-5 max-lg:px-3">
                <div className="mb-6 flex items-start gap-3 p-4 rounded-3xl bg-primary-01/8 border border-primary-01/15">
                    <span className="flex justify-center items-center size-9 rounded-2xl bg-primary-01/12 shrink-0">
                        <Icon name="send" className="!size-4.5 fill-primary-01" />
                    </span>
                    <div className="text-body-2 text-t-secondary">
                        <span className="text-t-primary text-button">Free, instant, no verification.</span>{" "}
                        Message{" "}
                        <span className="text-t-primary">@BotFather</span> on Telegram, run{" "}
                        <span className="text-t-primary">/newbot</span>, and give us the token (we already store it
                        encrypted). Then tap <span className="text-t-primary">Start</span> on your new bot once so we
                        can reach you.
                    </div>
                </div>

                <StepRow
                    n={1}
                    title="Connect the bot"
                    desc="We verify the stored BotFather token with Telegram (getMe). Your token is never shown here — it stays encrypted in the vault."
                    done={tested || configured}
                >
                    <div className="flex items-center gap-3 flex-wrap">
                        <button className={ghostBtnCls} onClick={runTest} disabled={busy === "test"}>
                            {busy === "test" ? <Spinner /> : <Icon name="reply" className="size-4 fill-inherit" />}
                            Test connection
                        </button>
                        {(botName || configured) && (
                            <span className="inline-flex items-center gap-1.5 text-caption text-t-secondary">
                                <Icon name="check-circle-fill" className="size-4 fill-primary-02" />
                                {botName ? `@${botName}` : "Connected"}
                            </span>
                        )}
                    </div>
                </StepRow>

                <StepRow
                    n={2}
                    title="Find your chat & turn on replies"
                    desc="After you tap Start on the bot, we read your chat id so hot-lead alerts land on your phone, then register the inbound webhook so Riya can reply to contacts."
                    done={!!chatId}
                >
                    <div className="flex items-center gap-3 flex-wrap">
                        <button className={ghostBtnCls} onClick={findChat} disabled={!writable || busy === "chat"}>
                            {busy === "chat" ? <Spinner /> : <Icon name="profile" className="size-4 fill-inherit" />}
                            Find my chat
                        </button>
                        <button className={textBtnCls} onClick={connectWebhook} disabled={!writable || busy === "webhook"}>
                            {busy === "webhook" ? <Spinner /> : <Icon name="chain" className="size-3.5 fill-inherit" />}
                            Register webhook
                        </button>
                        {chatId && (
                            <span className="inline-flex items-center gap-1.5 text-caption text-t-secondary">
                                <Icon name="check-circle-fill" className="size-4 fill-primary-02" />
                                chat {chatId}
                            </span>
                        )}
                    </div>
                </StepRow>

                <StepRow
                    n={3}
                    title="Send me a test"
                    desc="Prove real reach — fire one message to your own Telegram. This is the only true confirmation it works end-to-end."
                >
                    <div className="flex items-end gap-3 flex-wrap">
                        <Field
                            className="w-56 max-md:w-full"
                            label="Send to (chat id)"
                            placeholder="your chat id"
                            value={testTo}
                            onChange={(e) => setTestTo(e.target.value)}
                        />
                        <button className={ghostBtnCls} onClick={sendTest} disabled={!writable || busy === "send"}>
                            {busy === "send" ? <Spinner /> : <Icon name="send" className="size-4 fill-inherit" />}
                            Send test
                        </button>
                    </div>
                </StepRow>
            </div>
        </Card>
    );
}

// A small helper the Channels page reuses: mint a contact deep-link (so a contact
// can chat with Riya, which seeds the post-call auto-summary's deliverable path).
export function useContactDeeplink(onToast: Toast) {
    const [busy, setBusy] = useState(false);
    const [link, setLink] = useState("");
    const mint = async (phone: string, bot = "") => {
        if (!phone.trim()) {
            onToast("Enter a contact phone first.", "error");
            return;
        }
        setBusy(true);
        try {
            const r = await mintDeeplink(phone.trim(), bot);
            setLink(r.link || r.payload);
            onToast("Deep-link ready — share it with the contact.");
        } catch (e) {
            onToast(e instanceof CommError ? e.message : "Couldn't mint link.", "error");
        } finally {
            setBusy(false);
        }
    };
    return { busy, link, mint, setLink };
}
