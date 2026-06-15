"""comm.poll_worker — standalone getUpdates long-poll worker for Telegram inbound.

Feeds every inbound Telegram update through comm.webhook.handle (the SAME fail-closed
HMAC-verified handler used by the public-webhook path). This gives us a REAL inbound
conversation loop (Riya replies) without needing a public HTTPS endpoint.

DESIGN:
  - Standalone process (no caller.py / agent.py import — earner-safe).
  - Calls GET /bot{TOKEN}/getUpdates?timeout=25&offset={next_offset} in a loop.
  - Each update is routed to webhook.handle(tenant_id, secret_header, raw_body).
  - The secret_header is DERIVED (comm.webhook._signing_secret + HMAC — same as setWebhook
    uses) so the FAIL-CLOSED verify path is exercised identically to the real webhook.
  - On any error: sleep + retry (never crash-exits; managed by systemd Restart=always).
  - Respects COMM_ENABLED / COMM_TELEGRAM_ENABLED flags (polls-but-no-ops when off).

INVOCATION (systemd service comm-poll.service):
  ExecStart=/opt/capsy-agent/.venv/bin/python3 /opt/famit-agent/comm/poll_worker.py

EARNER LAW:
  - agent.py NEVER imported.
  - caller.py NEVER imported.
  - No dial-loop coupling whatsoever.
  - The process is INDEPENDENT; it only talks to the DB (via db.engine) + Telegram API.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# ── Bootstrap ──────────────────────────────────────────────────────────────────
# Must run from /opt/famit-agent as the working directory (set in systemd unit).
sys.path.insert(0, "/opt/famit-agent")

# Load .env before any module import (mirrors caller.py bootstrap order).
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.isfile(_ENV_PATH):
    with open(_ENV_PATH) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [comm-poll] %(levelname)s %(message)s",
)
_log = logging.getLogger("comm.poll_worker")

# ── Constants ──────────────────────────────────────────────────────────────────
TENANT_ID = "admin"          # the only tenant that has a Telegram credential so far
POLL_TIMEOUT_S = 25          # Telegram long-poll window
RETRY_SLEEP_S = 5            # back-off on errors
MAX_CONSECUTIVE_ERRORS = 20  # exit (systemd restarts) after this many
SLUG = "telegram-founder"


# ── Main polling loop ──────────────────────────────────────────────────────────
async def run_poll_loop() -> None:
    _log.info("comm-poll starting for tenant=%s slug=%s", TENANT_ID, SLUG)

    # Lazy-init DB (required for store + sessions + brain).
    from db import engine as db_engine
    db_engine.init()
    if not db_engine.available():
        _log.error("DB not available — exiting; systemd will restart")
        sys.exit(1)

    from comm.vault_read import resolve_provider_def_id, get_channel_token
    from comm import webhook as _webhook
    from comm.webhook import derive_secret_token

    provider_def_id = resolve_provider_def_id(TENANT_ID, slug=SLUG)
    if not provider_def_id:
        _log.error("Could not resolve provider_def_id for slug=%s — exiting", SLUG)
        sys.exit(1)
    _log.info("provider_def_id=%s", provider_def_id)

    # Use the SAME derive_secret_token as the webhook handler (ensures HMAC matches).
    secret_token = derive_secret_token(TENANT_ID, provider_def_id)
    if not secret_token:
        _log.warning(
            "No signing secret found — webhook.handle will reject (fail-closed); "
            "ensure var/secret or COMM_WEBHOOK_SIGNING_SECRET is set"
        )

    import urllib.request
    import urllib.error

    offset = 0
    consecutive_errors = 0

    while True:
        tok = get_channel_token(TENANT_ID, provider_def_id)
        if not tok:
            _log.warning("Token unavailable — sleeping %ss", RETRY_SLEEP_S)
            await asyncio.sleep(RETRY_SLEEP_S)
            continue

        url = (
            f"https://api.telegram.org/bot{tok}/getUpdates"
            f"?timeout={POLL_TIMEOUT_S}&offset={offset}&allowed_updates=%5B%22message%22%5D"
        )
        try:
            resp_bytes = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: urllib.request.urlopen(url, timeout=POLL_TIMEOUT_S + 5).read(),
            )
            data = json.loads(resp_bytes)
            consecutive_errors = 0
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            consecutive_errors += 1
            _log.warning("getUpdates error #%d: %r", consecutive_errors, exc)
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                _log.error("Too many consecutive errors — exiting for systemd restart")
                sys.exit(1)
            await asyncio.sleep(RETRY_SLEEP_S)
            continue

        updates = data.get("result", [])
        if updates:
            _log.info("Got %d update(s)", len(updates))

        for update in updates:
            update_id = update.get("update_id", 0)
            # Advance offset BEFORE processing (ack to Telegram immediately).
            if update_id >= offset:
                offset = update_id + 1

            raw_body = json.dumps(update).encode()
            try:
                # handle() returns (status_code: int, body: dict)
                http_status, result = await _webhook.handle(TENANT_ID, secret_token, raw_body)
                _log.info(
                    "update_id=%d handled: http=%d stored=%s reply=%s action=%s",
                    update_id,
                    http_status,
                    result.get("stored"),
                    result.get("reply"),
                    result.get("action"),
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning("webhook.handle raised (update_id=%d): %r", update_id, exc)

        if not updates:
            # Long-poll timed out naturally — immediately re-poll.
            pass


def main() -> None:
    asyncio.run(run_poll_loop())


if __name__ == "__main__":
    main()
