"""comm.config — call-time env flag reads for the Communication package (Wave 1).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §8 WAVE 1 (the four flags) + the design
law "flags default OFF -> resting byte-identical".

PATTERN (mirrors provider_registry/config.py + droplet_work/config.py): every flag is read
from os.environ at CALL TIME, never cached at import, so:
  * an empty environment imports cleanly and yields safe defaults (every flag OFF),
  * a flag flip takes effect on the NEXT read with NO restart of this module's import,
  * nothing here ever raises at import (the master design law: resting byte-identical).

The four Wave-1 flags (all default OFF, flipped ON for the founder tenant only AFTER the
security probes pass):
  * COMM_ENABLED                     — the master flag (the whole comm surface is dormant when off)
  * COMM_TELEGRAM_ENABLED            — the Telegram channel adapter
  * FEATURE_TELEGRAM_FOUNDER_ALERT   — the hot-lead alert to the founder's own Telegram
  * FEATURE_TELEGRAM_FOLLOWUP        — the post-call contact auto-summary

This module only *reads* config — it never acts on it (that is the engine / adapter).
"""
from __future__ import annotations

import os

# The master flag — with this OFF the whole comm surface is dormant (no send, no I/O,
# no route mounted). This is the resting-byte-identical guarantee.
FLAG_MASTER = "COMM_ENABLED"
FLAG_TELEGRAM = "COMM_TELEGRAM_ENABLED"
FLAG_FOUNDER_ALERT = "FEATURE_TELEGRAM_FOUNDER_ALERT"
FLAG_FOLLOWUP = "FEATURE_TELEGRAM_FOLLOWUP"
# Wave 2 — the inbound conversation brain (reply-only). Default OFF: with this off the
# webhook keeps its W1 behaviour (verify + store the inbound turn + ack 200, NO reply, NO
# Groq call). Flipping it ON lets the contact chat with "Riya" (a grounded LLM reply).
FLAG_BRAIN = "COMM_BRAIN_ENABLED"


def _truthy(val: str | None) -> bool:
    """Lenient truthy parse (mirrors how the rest of the box reads boolean flags:
    '1' / 'true' / 'yes' / 'on', case-insensitive). Empty / unset -> False."""
    if val is None:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on", "y", "t")


def comm_enabled() -> bool:
    """Master flag. Read at call time; default OFF. With this False the whole package
    is dormant — no send, no network I/O, no route active."""
    return _truthy(os.environ.get(FLAG_MASTER))


def telegram_enabled() -> bool:
    """Is the Telegram channel adapter ON? Requires the master flag too (a channel can
    never be live while the package is dormant)."""
    return comm_enabled() and _truthy(os.environ.get(FLAG_TELEGRAM))


def founder_alert_enabled() -> bool:
    """Is the founder hot-lead alert ON? Requires the master + Telegram flags."""
    return telegram_enabled() and _truthy(os.environ.get(FLAG_FOUNDER_ALERT))


def followup_enabled() -> bool:
    """Is the post-call contact auto-summary ON? Requires the master + Telegram flags."""
    return telegram_enabled() and _truthy(os.environ.get(FLAG_FOLLOWUP))


def brain_enabled() -> bool:
    """Wave 2: is the inbound conversation brain (the contact-chats-with-Riya reply path) ON?
    Requires the master + Telegram flags. OFF -> the webhook only stores+acks (W1 behaviour)."""
    return telegram_enabled() and _truthy(os.environ.get(FLAG_BRAIN))


def _int_env(key: str, default: int) -> int:
    """Read an int env var; fall back to default on unset/garbage (never raises)."""
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def groq_daily_cap() -> int:
    """Per-tenant daily ceiling on brain LLM calls (a runaway/abuse circuit-breaker, checked
    BEFORE any Groq call). Default 500/day. 0 or negative -> treated as unlimited."""
    return _int_env("COMM_GROQ_DAILY_CAP", 500)


def inbound_rate_per_min() -> int:
    """Per-(tenant, chat) inbound webhook rate ceiling per minute (a flood guard, checked before
    the brain runs). Default 20/min. 0 or negative -> unlimited."""
    return _int_env("COMM_INBOUND_RATE_PER_MIN", 20)


def inbound_body_max_bytes() -> int:
    """Max accepted inbound webhook body size in bytes (oversized -> dropped, acked 200 so
    Telegram stops retrying). Default 64 KiB (a Telegram Update is small)."""
    return _int_env("COMM_INBOUND_BODY_MAX_BYTES", 64 * 1024)


# ---------------------------------------------------------------------------
# Wave-3 COST GUARDS (master plan §6) — caps read at call time, default safe.
# All guards are *additive* and *permissive-on-fault*: a missing flag / PG blip
# never blocks a send (the dial loop's detached task must always make progress).
# ---------------------------------------------------------------------------
FLAG_COST_GUARDS = "COMM_COST_GUARDS_ENABLED"   # master switch for budget/freq/anomaly/deliverability


def cost_guards_enabled() -> bool:
    """Wave-3 master cost-guard switch. OFF -> the engine sends exactly as W1/W2 (no budget,
    no frequency, no anomaly, no deliverability precheck). Requires the comm master flag too.
    Metering + the token-bucket are governed by their OWN flags below (independent)."""
    return comm_enabled() and _truthy(os.environ.get(FLAG_COST_GUARDS))


def metering_enabled() -> bool:
    """Per-message metering through the real wallet reserve->settle/release ledger. OFF ->
    no wallet row is written for a send (W1/W2 behaviour). Independent of cost_guards_enabled
    so metering can run (audit every send) even before the ceilings are switched on."""
    return comm_enabled() and _truthy(os.environ.get("COMM_METERING_ENABLED"))


def token_bucket_enabled() -> bool:
    """Per-bot async token-bucket (30/s global, 1/s per chat). OFF -> no pacing (W1/W2). The
    bucket is in-process; it never blocks longer than its own bounded wait."""
    return comm_enabled() and _truthy(os.environ.get("COMM_TOKEN_BUCKET_ENABLED"))


def daily_budget_minor() -> int:
    """Per-tenant daily comm-spend CEILING in INR paise. Default 50000 paise (₹500/day) — the
    circuit-breaker that caps a runaway at a known rupee number. 0 or negative -> unlimited."""
    return _int_env("COMM_DAILY_BUDGET_MINOR", 50000)


def freq_cap_per_contact_day() -> int:
    """Per-(contact, channel) per-UTC-day send cap (all channels). Default 8 — stops a journey
    bug from spamming + billing one contact. 0 or negative -> unlimited."""
    return _int_env("COMM_FREQ_CAP_PER_CONTACT_DAY", 8)


def anomaly_multiplier() -> float:
    """Spend-anomaly trip multiplier: today's spend > N x the trailing-7-day median -> alert +
    throttle. Default 3.0 (plan §6). <= 0 -> the anomaly guard is disabled."""
    return _float_env("COMM_SPEND_ANOMALY_MULT", 3.0)


def anomaly_floor_minor() -> int:
    """A paise floor below which the anomaly guard never trips (so a ₹0->₹2 day on free Telegram
    is not flagged as a 'spike'). Default 2000 paise (₹20). Anomaly trips only when today's spend
    exceeds BOTH the multiplier-of-median AND this floor."""
    return _int_env("COMM_SPEND_ANOMALY_FLOOR_MINOR", 2000)


def bucket_global_rate() -> float:
    """Per-bot global token-bucket refill rate (messages/second). Default 30/s (Telegram's
    documented global ceiling). Shared by the journey blast + post-call trickle + alerts."""
    return _float_env("COMM_BUCKET_GLOBAL_RATE", 30.0)


def bucket_per_chat_rate() -> float:
    """Per-(bot, chat) token-bucket refill rate (messages/second). Default 1/s (Telegram's
    documented per-chat ceiling). A burst to one chat is paced; other chats are unaffected."""
    return _float_env("COMM_BUCKET_PER_CHAT_RATE", 1.0)


def bucket_max_wait_s() -> float:
    """The HARD cap on how long token-bucket acquire() will wait for a token before giving up
    (returns False -> the send is dropped/deferred, never hangs). Default 3s — well under the
    per-channel send_timeout envelope so the detached task is always bounded. <=0 -> no-wait."""
    return _float_env("COMM_BUCKET_MAX_WAIT_S", 3.0)


def _float_env(key: str, default: float) -> float:
    """Read a float env var; fall back to default on unset/garbage (never raises)."""
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return default


def send_timeout_s() -> float:
    """Per-channel hard send timeout (seconds). The engine wraps EVERY adapter call in
    asyncio.wait_for(..., this) so a hung/black-holed provider can NEVER stall the
    detached post-call task beyond this bound (earner-safety: the dial loop never waits
    on this — it is create_task'd — but a bounded task is still mandatory). Default 8s."""
    return _float_env("COMM_SEND_TIMEOUT_S", 8.0)


def http_timeout_s() -> float:
    """The lower-level HTTP client timeout for ONE Bot API request. Strictly < the
    send_timeout_s envelope so the wait_for bound is the outer cap. Default 6s."""
    return _float_env("COMM_HTTP_TIMEOUT_S", 6.0)


def config_snapshot() -> dict:
    """A JSON-able snapshot of the comm flags (NEVER a secret) — safe for a /health
    style diagnostic. Behavioural code consumes the helpers above; this is for ops."""
    return {
        "comm_enabled": comm_enabled(),
        "telegram_enabled": telegram_enabled(),
        "founder_alert_enabled": founder_alert_enabled(),
        "followup_enabled": followup_enabled(),
        "brain_enabled": brain_enabled(),
        "send_timeout_s": send_timeout_s(),
        "http_timeout_s": http_timeout_s(),
        "groq_daily_cap": groq_daily_cap(),
        "inbound_rate_per_min": inbound_rate_per_min(),
        "cost_guards_enabled": cost_guards_enabled(),
        "metering_enabled": metering_enabled(),
        "token_bucket_enabled": token_bucket_enabled(),
        "daily_budget_minor": daily_budget_minor(),
        "freq_cap_per_contact_day": freq_cap_per_contact_day(),
        "anomaly_multiplier": anomaly_multiplier(),
        "bucket_global_rate": bucket_global_rate(),
        "bucket_per_chat_rate": bucket_per_chat_rate(),
    }
