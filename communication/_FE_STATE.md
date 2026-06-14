# communication/_FE_STATE.md — FE build tracker (Communication TAB)

Branch `fe/unify-run-wavec`. Build from it; tsc 0 + npm build GREEN + COMMIT; DO NOT deploy panel.
Reuse Core_2 "Signal" system (Inter Display, semantic tokens, zero raw hex). frontend-design skill invoked.

## Backend API surface (LIVE, from comm/endpoints.py — proxied at /api/comm/*)
- GET  /comm/channels                         -> {channels:[{channel,enabled,configured,founder_alert,followup}], flags}
- POST /comm/channels/telegram/test           -> {ok, username}            (getMe)
- POST /comm/channels/telegram/derive-chat-id -> {chat_id, found}          (write; body {force?})
- POST /comm/channels/telegram/set-webhook    -> {ok, provider_def_id, error}  (write; body {webhook_url})
- POST /comm/channels/telegram/deeplink       -> {payload, link, ok}       (write; body {phone, bot_username?})
- GET  /comm/sessions[?channel,status,limit,offset] -> {sessions:[...], total}
- GET  /comm/sessions/{id}                    -> {session:{...turns...}}
- POST /comm/send                             -> {ok,status,channel,external_id,error_code,cost_minor}
       body {to_ref, text, kind?, purpose?, media?[{url,kind,caption}], buttons?[{text,url}]}
- (dormant: COMM_ENABLED off -> every route 404)

## Plan (§7 frontend): Communication section in Engage nav, alongside WhatsApp.
W1 FE scope = Channel Setup + send/log view. Build the full shell dormant-safe for W2-6.

## TASKS
- [DONE] lib/communication.ts — typed dormant-safe client (mirrors lib/integrations.ts)
- [DONE] nav entry: Engage > Communication
- [DONE] /communication shell (ChannelPicker sub-nav + tab routing)
- [DONE] Channels page + Telegram setup wizard (token confirm + Test getMe + chat_id + send-to-me)
- [DONE] Template/message Builder (author-once, per-channel render, media, variables, buttons, test send)
- [DONE] Unified Inbox (sessions list + chat transcript, customer RIGHT / Riya LEFT)
- [DONE] Analytics (per-channel KPIs + out-of-box feature cards)
- [DONE] net-new components: ChannelPicker, TelegramPreview, Composer, ConsentBadge
- [DONE] tsc 0 + npm build GREEN
- [DONE] commit fe/unify-run-wavec
- [DONE] append _BUILD-LOG.md
