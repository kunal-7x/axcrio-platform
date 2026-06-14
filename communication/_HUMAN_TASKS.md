# communication/ — FOUNDER ACTION ITEMS (open forks the session left for you)

> AskUserQuestion was unavailable in this harness, so per the operating rules these are
> recorded here for you to steer. Each is a 1-tap action; the system is built + live and
> waits on exactly these.

## ⭐ #1 — Telegram hot-lead alert: tap your bot ONCE (the only thing blocking real-reach)

**What:** Open Telegram, find your bot **@mr_kunal_bot**, and send it ANY message (or tap
**Start**). That's it — one message.

**Why:** The hot-lead alert sends to YOUR Telegram. To learn your chat_id the bot reads
`getUpdates`, but Telegram only keeps the last ~24h of updates and drops old ones — your
original Start tap (days ago) has aged out, so `getUpdates` is currently empty. One fresh
message re-populates it; the system then **auto-captures + permanently persists** your
chat_id (a sentinel `comm_sessions` row), so it survives forever after — you never do this
again.

**After you tap:** the next hot lead (a call with interest score ≥ 70) auto-sends you a
Telegram alert with a "Open in panel" button. (Privacy-minimized by default — no name/phone
inline; set `COMM_FOUNDER_ALERT_FULL_PII=1` in `/opt/famit-agent/.env` if you want the full
lead detail in the message itself.)

**Status (updated 2026-06-15):** Everything else is LIVE for the `admin` tenant — and
now the **conversation brain + all 6 cost guards are LIVE too** (flags
`COMM_BRAIN_ENABLED · COMM_COST_GUARDS_ENABLED · COMM_METERING_ENABLED ·
COMM_TOKEN_BUCKET_ENABLED` all ON, on top of `FEATURE_TELEGRAM_FOUNDER_ALERT ·
FEATURE_TELEGRAM_FOLLOWUP`). Proven live: getMe → `mr_kunal_bot` (token decrypts), the
brain replies grounded in the prior call (real Hinglish reply generated through the live
webhook), the send pipeline reaches Telegram for real (`http_400 chat-not-found` — only
the destination is missing). **The ONLY thing standing between you and a real alert on
your phone is this one tap.** After you tap, run nothing — the next hot lead (interest
≥ 70) auto-sends you the alert.

## #2 — Post-call auto-summary to the CONTACT (W1: usually a no-op, by design)

The post-call summary to the *customer* needs the customer's Telegram chat_id, which only
exists once a customer has messaged your bot (via the `?start=` deep-link, W2). In W1 there
are no contact chats yet, so this path is a clean no-op (`no_destination`) — never an error,
never a block. It activates automatically in Wave 2 (the deep-link + brain). No action needed.
