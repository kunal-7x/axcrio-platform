"""Offline PROOF that the 6 cost guards are WIRED into comm.engine.send (the integration seam).

Acceptance: with the guards flagged ON, engine.send must
  * block a known-DEAD chat -> status blocked_dead, the adapter is NEVER called (#5);
  * block over the per-contact frequency cap -> blocked_frequency (#3);
  * block a metered send over the daily budget ceiling -> blocked_budget (#2);
  * pace via the token-bucket and HONOUR the priority lane for founder alerts (#6);
  * reserve->settle on a successful send and release on a failed send (#1);
  * after a 403 send, flip the chat to 'dead' so the NEXT send is blocked (#5 transition);
  * with the guards flag OFF, behave EXACTLY as before (resting byte-identical).

No network/PG/wallet: we inject the same in-memory fakes as test_cost_guards_offline and a fake
adapter via engine.resolve_telegram_adapter. Run: python -m comm.tests.test_engine_costguards_offline
"""
from __future__ import annotations

import asyncio
import os
import sys

# reuse the fakes from the sibling proof module
from comm.tests.test_cost_guards_offline import (
    _install_fake_db, _install_fake_wallet, _FakeWallet,
)
from comm.channels.base import SendEnvelope, SendResult


class _RecordingAdapter:
    channel = "telegram"

    def __init__(self, *, result=None, cost=0):
        # a paid adapter's success result carries the charged cost_minor (a real adapter does this);
        # a fixed failure/override result is used verbatim.
        self.result = result
        self.cost = cost
        self.calls = 0

    def status(self):
        return "configured"

    def estimate_cost_minor(self, env):
        return self.cost

    async def send(self, env):
        self.calls += 1
        if self.result is not None:
            return self.result
        return SendResult.success("telegram", external_id="m1", provider="telegram",
                                  cost_minor=self.cost)


def _run(coro):
    return asyncio.run(coro)


def main() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    store = {"deliv": {}, "freq": {}, "spend": {}, "sendlog": []}
    _install_fake_db(store)
    _install_fake_wallet(_FakeWallet(funds=True))

    for m in list(sys.modules):
        if m == "comm" or m.startswith("comm."):
            if "test_cost_guards_offline" in m:
                continue
            del sys.modules[m]
    from comm import engine, token_bucket, cost_guards  # noqa: E402

    os.environ.update({
        "COMM_ENABLED": "1", "COMM_TELEGRAM_ENABLED": "1",
        "COMM_COST_GUARDS_ENABLED": "1", "COMM_METERING_ENABLED": "1",
        "COMM_TOKEN_BUCKET_ENABLED": "1",
        "COMM_FREQ_CAP_PER_CONTACT_DAY": "2",
        "COMM_DAILY_BUDGET_MINOR": "1000",
        "COMM_BUCKET_GLOBAL_RATE": "1000", "COMM_BUCKET_PER_CHAT_RATE": "1000",
        "COMM_BUCKET_MAX_WAIT_S": "0",
        "COMM_SEND_TIMEOUT_S": "1", "COMM_HTTP_TIMEOUT_S": "1",
    })
    token_bucket._reset_for_tests()

    orig_resolve = engine.resolve_telegram_adapter

    # ---- #5 deliverability: a dead chat is blocked WITHOUT calling the adapter ----
    cost_guards.mark_deliverability("tI", "deadchat", "telegram", "dead", reason="http_403")
    ad = _RecordingAdapter()
    engine.resolve_telegram_adapter = lambda tid, **kw: (ad, "pdI")  # type: ignore
    r = _run(engine.send("tI", SendEnvelope(to_ref="deadchat", text="hi"), log=False))
    check("wire5.dead_blocked", (not r.ok) and r.status == "blocked_dead")
    check("wire5.adapter_not_called_for_dead", ad.calls == 0)

    # ---- #3 frequency: cap=2; 3rd send to one contact blocked ----
    ad = _RecordingAdapter()
    engine.resolve_telegram_adapter = lambda tid, **kw: (ad, "pdI")  # type: ignore
    r1 = _run(engine.send("tF", SendEnvelope(to_ref="freqchat", text="1"), log=False))
    r2 = _run(engine.send("tF", SendEnvelope(to_ref="freqchat", text="2"), log=False))
    r3 = _run(engine.send("tF", SendEnvelope(to_ref="freqchat", text="3"), log=False))
    check("wire3.two_sent", r1.ok and r2.ok and ad.calls == 2)
    check("wire3.third_blocked", (not r3.ok) and r3.status == "blocked_frequency")

    # ---- #2 budget: a metered (paid) send over the daily ceiling blocked; free TG flows ----
    paid = _RecordingAdapter(cost=600)   # ₹6/send
    engine.resolve_telegram_adapter = lambda tid, **kw: (paid, "pdI")  # type: ignore
    rb1 = _run(engine.send("tBud", SendEnvelope(to_ref="b1", text="x"), log=False))  # spends ₹6
    rb2 = _run(engine.send("tBud", SendEnvelope(to_ref="b2", text="x"), log=False))  # ₹6 -> over ₹10
    check("wire2.first_paid_ok", rb1.ok and rb1.cost_minor == 600)
    check("wire2.second_over_budget_blocked", (not rb2.ok) and rb2.status == "blocked_budget")
    # a FREE Telegram send (cost 0) STILL flows even when the metered ceiling is hit
    free = _RecordingAdapter(cost=0)
    engine.resolve_telegram_adapter = lambda tid, **kw: (free, "pdI")  # type: ignore
    rfree = _run(engine.send("tBud", SendEnvelope(to_ref="b3", text="free"), log=False))
    check("wire2.free_flows_over_budget", rfree.ok and free.calls == 1)

    # ---- #1 metering: a successful paid send settles; a failed send releases (never bills) ----
    w = _FakeWallet(funds=True)
    _install_fake_wallet(w)
    okpaid = _RecordingAdapter(cost=300)
    engine.resolve_telegram_adapter = lambda tid, **kw: (okpaid, "pdJ")  # type: ignore
    _run(engine.send("tMeter", SendEnvelope(to_ref="mc1", text="ok"), log=False))
    check("wire1.success_reserves_and_settles",
          any(c[0] == "reserve" for c in w.calls) and any(c[0] == "settle" for c in w.calls))
    w.calls.clear()
    failad = _RecordingAdapter(result=SendResult.failure("telegram", "http_500"), cost=300)
    engine.resolve_telegram_adapter = lambda tid, **kw: (failad, "pdJ")  # type: ignore
    _run(engine.send("tMeter", SendEnvelope(to_ref="mc2", text="fail"), log=False))
    check("wire1.failed_releases_never_settles",
          any(c[0] == "release" for c in w.calls) and not any(c[0] == "settle" for c in w.calls))

    # ---- #5 transition: a 403 send flips the chat dead -> the next send is blocked ----
    _install_fake_wallet(_FakeWallet(funds=True))
    blocked403 = _RecordingAdapter(result=SendResult.failure("telegram", "http_403:bot was blocked"), cost=0)
    engine.resolve_telegram_adapter = lambda tid, **kw: (blocked403, "pdK")  # type: ignore
    r = _run(engine.send("tDead", SendEnvelope(to_ref="willdie", text="x"), log=False))
    check("wire5.403_send_not_ok", not r.ok)
    check("wire5.403_flipped_dead", cost_guards.get_deliverability("tDead", "willdie", "telegram") == "dead")
    nxt = _RecordingAdapter()
    engine.resolve_telegram_adapter = lambda tid, **kw: (nxt, "pdK")  # type: ignore
    r2 = _run(engine.send("tDead", SendEnvelope(to_ref="willdie", text="again"), log=False))
    check("wire5.next_send_blocked_dead", (not r2.ok) and r2.status == "blocked_dead" and nxt.calls == 0)

    # ---- #6 token-bucket + priority: drain global, normal blocked, priority bypasses ----
    os.environ["COMM_BUCKET_GLOBAL_RATE"] = "1"
    token_bucket._reset_for_tests()
    pad = _RecordingAdapter()
    engine.resolve_telegram_adapter = lambda tid, **kw: (pad, "pdP")  # type: ignore
    first = _run(engine.send("tRate", SendEnvelope(to_ref="r1", text="1"), log=False))   # takes the only token
    normal = _run(engine.send("tRate", SendEnvelope(to_ref="r2", text="2"), log=False))  # global drained
    priority = _run(engine.send("tRate", SendEnvelope(to_ref="r3", text="3"), log=False, priority=True))
    check("wire6.first_ok", first.ok)
    check("wire6.normal_rate_limited", (not normal.ok) and normal.status == "blocked_rate")
    check("wire6.priority_bypasses", priority.ok)

    engine.resolve_telegram_adapter = orig_resolve  # type: ignore

    # ---- RESTING: guards OFF -> a dead chat sends normally (byte-identical to W1/W2) ----
    os.environ["COMM_COST_GUARDS_ENABLED"] = "0"
    os.environ["COMM_METERING_ENABLED"] = "0"
    os.environ["COMM_TOKEN_BUCKET_ENABLED"] = "0"
    cost_guards.mark_deliverability("tOff", "deadoff", "telegram", "dead", reason="http_403")
    restad = _RecordingAdapter()
    engine.resolve_telegram_adapter = lambda tid, **kw: (restad, "pdR")  # type: ignore
    r = _run(engine.send("tOff", SendEnvelope(to_ref="deadoff", text="x"), log=False))
    check("resting.guards_off_dead_chat_sends", r.ok and restad.calls == 1)
    engine.resolve_telegram_adapter = orig_resolve  # type: ignore

    for k in list(os.environ):
        if k.startswith("COMM_"):
            os.environ.pop(k, None)

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
