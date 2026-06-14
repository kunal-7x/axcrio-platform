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
    }
