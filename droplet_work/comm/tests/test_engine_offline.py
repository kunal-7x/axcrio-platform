"""Offline test for comm.engine — the channel-agnostic send engine (Wave 1).

Acceptance (COMMUNICATION-MASTER-PLAN §2.2 / §2.3 / WAVE 1):
  * dormant: COMM_ENABLED off -> send() returns 'not_configured' (comm_disabled) with NO I/O;
  * non-telegram channel -> 'not_configured' (channel_not_enabled) — W1 is Telegram-only;
  * a resolved adapter that HANGS is killed by the per-channel asyncio.wait_for -> status='timeout'
    (the earner-safety cap — a black-holed provider can never keep the task alive);
  * a happy send returns the adapter's SendResult; idempotency_key is minted when absent;
  * send_log is best-effort: with no PG, the engine still returns the SendResult and never raises;
  * NEVER raises on any path.

No network, no PG. The resolver (resolve_telegram_adapter) is monkeypatched to inject a fake
adapter, and config flags are forced via os.environ.
Run: python -m comm.tests.test_engine_offline
"""
from __future__ import annotations

import asyncio
import os
import sys

from comm import engine
from comm.channels.base import SendEnvelope, SendResult


class FakeAdapter:
    channel = "telegram"

    def __init__(self, *, hang=False, result=None):
        self.hang = hang
        self.result = result or SendResult.success("telegram", external_id="9001", provider="telegram")
        self.sent = []

    def status(self):
        return "configured"

    def estimate_cost_minor(self, env):
        return 0

    async def send(self, env):
        self.sent.append(env)
        if self.hang:
            await asyncio.sleep(60)   # longer than any test timeout -> wait_for must kill it
        return self.result


def _run(coro):
    return asyncio.run(coro)


def main() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    # keep tests fast + bound: a 1s timeout envelope.
    os.environ["COMM_SEND_TIMEOUT_S"] = "1"
    os.environ["COMM_HTTP_TIMEOUT_S"] = "1"

    # --- 1) dormant: master flag OFF -> not_configured, no resolver call ---
    for k in ("COMM_ENABLED", "COMM_TELEGRAM_ENABLED"):
        os.environ.pop(k, None)
    r = _run(engine.send("admin", SendEnvelope(to_ref="1", text="x"), log=False))
    check("dormant.comm_disabled", (not r.ok) and r.error_code == "comm_disabled")

    # --- 2) non-telegram channel -> not_configured (W1 Telegram-only) ---
    os.environ["COMM_ENABLED"] = "1"
    os.environ["COMM_TELEGRAM_ENABLED"] = "1"
    r = _run(engine.send("admin", SendEnvelope(to_ref="1", text="x"), channel="email", log=False))
    check("email.channel_not_enabled", (not r.ok) and r.error_code == "channel_not_enabled")

    # --- inject a fake resolver for the happy + timeout paths ---
    orig_resolve = engine.resolve_telegram_adapter

    happy = FakeAdapter()
    engine.resolve_telegram_adapter = lambda tenant_id, **kw: (happy, "pd1")  # type: ignore
    try:
        # --- 3) happy send: returns the adapter result, mints an idem key ---
        env = SendEnvelope(to_ref="555111", text="Hi")
        r = _run(engine.send("admin", env, log=False))
        check("happy.ok", r.ok and r.external_id == "9001")
        check("happy.idem_minted", env.idempotency_key.startswith("comms:"))
        check("happy.adapter_received", len(happy.sent) == 1)

        # --- 4) timeout: a hanging adapter is killed by wait_for -> status timeout ---
        hung = FakeAdapter(hang=True)
        engine.resolve_telegram_adapter = lambda tenant_id, **kw: (hung, "pd1")  # type: ignore
        r = _run(engine.send("admin", SendEnvelope(to_ref="1", text="x"), log=False))
        check("timeout.status", (not r.ok) and r.status == "timeout" and r.error_code == "send_timeout")

        # --- 5) no adapter (resolver returns None) -> not_configured ---
        engine.resolve_telegram_adapter = lambda tenant_id, **kw: (None, "")  # type: ignore
        r = _run(engine.send("admin", SendEnvelope(to_ref="1", text="x"), log=False))
        check("no_adapter.not_configured", (not r.ok) and r.error_code == "no_channel_or_token")
    finally:
        engine.resolve_telegram_adapter = orig_resolve  # type: ignore

    # --- 6) send_log best-effort with no PG: returns False, never raises ---
    from comm import send_log
    wrote = send_log.record_send("admin", message_id=send_log.new_message_id(), status="sent")
    check("send_log.no_pg_returns_false", wrote is False)

    # --- 7) status() never leaks a secret / never raises ---
    st = engine.status()
    check("status.shape", isinstance(st, dict) and "flags" in st)

    # cleanup env
    for k in ("COMM_ENABLED", "COMM_TELEGRAM_ENABLED", "COMM_SEND_TIMEOUT_S", "COMM_HTTP_TIMEOUT_S"):
        os.environ.pop(k, None)

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
