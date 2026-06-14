"""Offline PROOF of the 6 Wave-3 cost guards (COMMUNICATION-MASTER-PLAN §6).

Each guard returns an explicit PASS/FAIL. No network, no real PG, no real wallet: we inject a
tiny in-memory fake `db.engine` (a dict-backed store that honours the SQL the modules issue) and
a fake `wallet` module (records reserve/settle/release calls), so the guards' REAL code paths run
deterministically.

The 6 guards:
  #1 per-message metering    — reserve BEFORE, settle on success, RELEASE (no bill) on failure
  #2 budget ceiling          — over the per-tenant daily cap -> blocked_budget (free TG still flows)
  #3 frequency cap           — (N+1)-th send to one contact/day -> blocked_frequency
  #4 spend-anomaly           — today's spend > 3x trailing-7-day median -> anomaly detected + alert
  #5 deliverability state     — a 403 flips the chat 'dead' -> next send blocked_dead
  #6 per-bot token-bucket     — paces a burst; founder/hot-lead alert priority lane never waits

Run: python -m comm.tests.test_cost_guards_offline
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import types
from datetime import datetime, timezone, timedelta


# ===========================================================================
# a tiny in-memory fake of db.engine that the cost_guards / send_log modules use.
# It honours exactly the SQL those modules issue (upserts + the aggregate selects).
# ===========================================================================
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, store, tenant_id, is_admin):
        self.store = store
        self.tenant_id = tenant_id
        self.is_admin = is_admin

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    # The modules call s.execute(text(SQL), params). We pattern-match on the SQL text.
    def execute(self, textobj, params=None):
        sql = str(getattr(textobj, "text", textobj))
        p = params or {}
        s = " ".join(sql.split())  # normalise whitespace

        # ---- comm_deliverability ----
        if "FROM comm_deliverability" in s and "SELECT state" in s:
            row = self.store["deliv"].get((p["t"], p["c"], p["ch"]))
            return _FakeResult([(row["state"],)] if row else [])
        if "INSERT INTO comm_deliverability" in s:
            key = (p["t"], p["c"], p["ch"])
            cur = self.store["deliv"].get(key)
            if cur is None:
                self.store["deliv"][key] = {"state": p["st"], "fail": p["inc"]}
            else:
                cur["state"] = p["st"]
                cur["fail"] = cur.get("fail", 0) + p["inc"]
            return _FakeResult([])

        # ---- comm_freq_counter ----
        if "FROM comm_freq_counter" in s and "SELECT sent_count" in s:
            row = self.store["freq"].get((p["t"], p["c"], p["ch"], p["d"]))
            return _FakeResult([(row,)] if row is not None else [])
        if "INSERT INTO comm_freq_counter" in s:
            key = (p["t"], p["c"], p["ch"], p["d"])
            self.store["freq"][key] = self.store["freq"].get(key, 0) + p["n"]
            return _FakeResult([])

        # ---- comm_daily_spend ----
        if "FROM comm_daily_spend" in s and "SUM(spend_minor)" in s and "day < CAST" in s:
            # trailing series: rows of (day, sum) for day < today and >= today - n
            today = datetime.now(timezone.utc).date()
            out = []
            for (t, ch, day), val in self.store["spend"].items():
                if t != p["t"]:
                    continue
                dd = datetime.strptime(day, "%Y-%m-%d").date()
                if dd < today and dd >= (today - timedelta(days=p["n"])):
                    out.append((day, val))
            # group by day
            agg = {}
            for day, val in out:
                agg[day] = agg.get(day, 0) + val
            rows = sorted(agg.items())
            return _FakeResult([(d, v) for d, v in rows])
        if "FROM comm_daily_spend" in s and "SUM(spend_minor)" in s:
            # today's spend (channel-specific or all-channel)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            total = 0
            for (t, ch, day), val in self.store["spend"].items():
                if t != p["t"] or day != p["d"]:
                    continue
                if "AND channel=:ch" in s and ch != p.get("ch"):
                    continue
                total += val
            return _FakeResult([(total,)])
        if "INSERT INTO comm_daily_spend" in s:
            key = (p["t"], p["ch"], p["d"])
            self.store["spend"][key] = self.store["spend"].get(key, 0) + p["amt"]
            return _FakeResult([])

        # ---- comm_send_log (best-effort; just record it lands) ----
        if "INSERT INTO comm_send_log" in s:
            self.store["sendlog"].append(dict(p))
            return _FakeResult([(p["message_id"],)])

        return _FakeResult([])


class _FakeEngine:
    def __init__(self, store):
        self.store = store

    def available(self):
        return True

    def session(self, tenant_id="", is_admin=False):
        return _FakeSession(self.store, tenant_id, is_admin)


def _install_fake_db(store):
    mod = types.ModuleType("db")
    eng = types.ModuleType("db.engine")
    fake = _FakeEngine(store)
    eng.available = fake.available           # type: ignore
    eng.session = fake.session               # type: ignore
    mod.engine = eng                         # type: ignore
    sys.modules["db"] = mod
    sys.modules["db.engine"] = eng


# ===========================================================================
# a fake wallet recording reserve/settle/release.
# ===========================================================================
class _FakeWallet:
    def __init__(self, *, funds=True):
        self.funds = funds
        self.calls = []
        self._hold = 1000

    def available(self):
        return True

    def reserve(self, tenant_id, amount_minor, **kw):
        self.calls.append(("reserve", tenant_id, amount_minor, kw.get("idem_key")))
        if not self.funds:
            return None
        self._hold += 1
        return self._hold

    def settle(self, hold_id, actual_minor, **kw):
        self.calls.append(("settle", hold_id, actual_minor, kw.get("idem_key")))
        return {"ok": True, "charged_minor": actual_minor, "refunded_minor": 0}

    def release(self, hold_id, **kw):
        self.calls.append(("release", hold_id, kw.get("idem_key")))
        return {"ok": True, "released_minor": 0}


def _install_fake_wallet(w):
    sys.modules["wallet"] = w  # type: ignore


def _run(coro):
    return asyncio.run(coro)


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ===========================================================================
# the proof.
# ===========================================================================
def main() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    # a fresh in-memory store + fakes for the whole run.
    store = {"deliv": {}, "freq": {}, "spend": {}, "sendlog": []}
    _install_fake_db(store)

    # import AFTER the fake db is installed (the modules import db lazily, so order is fine,
    # but a fresh import keeps the cached _engine() pointed at our fake).
    for m in list(sys.modules):
        if m == "comm" or m.startswith("comm."):
            del sys.modules[m]
    from comm import config, cost_guards, metering, token_bucket  # noqa: E402

    # base env: comm on, guards on, telegram on; small caps to make the proof crisp.
    os.environ["COMM_ENABLED"] = "1"
    os.environ["COMM_TELEGRAM_ENABLED"] = "1"
    os.environ["COMM_COST_GUARDS_ENABLED"] = "1"
    os.environ["COMM_FREQ_CAP_PER_CONTACT_DAY"] = "3"
    os.environ["COMM_DAILY_BUDGET_MINOR"] = "1000"     # ₹10/day
    os.environ["COMM_SPEND_ANOMALY_MULT"] = "3"
    os.environ["COMM_SPEND_ANOMALY_FLOOR_MINOR"] = "500"  # ₹5

    # =====================================================================
    # GUARD #5 — DELIVERABILITY STATE (a 403 flips dead; a dead chat is blocked)
    # =====================================================================
    print("\nGUARD #5 — deliverability state")
    t, c, ch = "tA", "chat_5", "telegram"
    check("5.default_ok", cost_guards.get_deliverability(t, c, ch) == "ok")
    check("5.precheck_allows_when_ok", cost_guards.precheck_send(t, c, ch, 0).allow)
    # classify a 403 error -> 'dead'
    check("5.classify_403_dead", cost_guards.classify_failure("http_403:bot was blocked by the user") == "dead")
    check("5.classify_net_no_change", cost_guards.classify_failure("net_ConnectError") == "")
    cost_guards.mark_deliverability(t, c, ch, "dead", reason="http_403")
    check("5.now_dead", cost_guards.get_deliverability(t, c, ch) == "dead")
    gd = cost_guards.precheck_send(t, c, ch, 0)
    check("5.dead_blocks_send", (not gd.allow) and gd.block_status == "blocked_dead")
    # a successful send to a different (live) chat is allowed
    check("5.live_chat_allowed", cost_guards.precheck_send(t, "chat_live", ch, 0).allow)

    # =====================================================================
    # GUARD #3 — FREQUENCY CAP (cap=3; 4th send to one contact/day blocked)
    # =====================================================================
    print("\nGUARD #3 — frequency cap")
    t3, c3 = "tB", "chat_3"
    for i in range(3):
        d = cost_guards.check_frequency(t3, c3, ch)
        check(f"3.send_{i+1}_allowed", d.allow)
        cost_guards.bump_frequency(t3, c3, ch)   # simulate the post-send bump
    blocked = cost_guards.check_frequency(t3, c3, ch)
    check("3.4th_send_blocked", (not blocked.allow) and blocked.block_status == "blocked_frequency")
    # a DIFFERENT contact under the same tenant is unaffected
    check("3.other_contact_ok", cost_guards.check_frequency(t3, "chat_other", ch).allow)

    # =====================================================================
    # GUARD #2 — BUDGET CEILING (cap ₹10/day; metered send over cap blocked; free TG flows)
    # =====================================================================
    print("\nGUARD #2 — budget ceiling")
    t2 = "tC"
    # a FREE send (est=0, Telegram) ALWAYS flows even with the ceiling on
    check("2.free_send_always_flows", cost_guards.check_budget(t2, 0).allow)
    # a metered send within budget passes
    check("2.metered_within_budget", cost_guards.check_budget(t2, 600).allow)
    # record ₹6 spent today, then a ₹6 send would exceed ₹10 -> blocked
    cost_guards.record_spend(t2, "sms", 600)
    over = cost_guards.check_budget(t2, 600)
    check("2.over_budget_blocked", (not over.allow) and over.block_status == "blocked_budget")
    # but a FREE Telegram send STILL flows even when over the metered ceiling (plan §6)
    check("2.free_flows_when_over_budget", cost_guards.check_budget(t2, 0).allow)

    # =====================================================================
    # GUARD #4 — SPEND-ANOMALY (today >> trailing-7-day median -> tripped)
    # =====================================================================
    print("\nGUARD #4 — spend-anomaly")
    t4 = "tD"
    # seed a quiet trailing week: ₹1/day for the last 7 days
    today = datetime.now(timezone.utc).date()
    for i in range(1, 8):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        store["spend"][(t4, "sms", day)] = 100   # ₹1
    # a NORMAL day: ₹1 today -> below floor, no anomaly
    store["spend"][(t4, "sms", _today())] = 100
    gd = cost_guards.check_anomaly(t4)
    check("4.normal_no_trip", (not gd.anomaly))
    # a SPIKE day: ₹50 today vs median ₹1 -> > 3x AND above the ₹5 floor -> trip
    store["spend"][(t4, "sms", _today())] = 5000   # ₹50
    gd = cost_guards.check_anomaly(t4)
    check("4.spike_trips", gd.anomaly and gd.detail.get("median") == 100)
    # a brand-new tenant (no history) spending above the floor IS the anomaly
    t4b = "tDb"
    store["spend"][(t4b, "sms", _today())] = 5000
    check("4.new_tenant_spike_trips", cost_guards.check_anomaly(t4b).anomaly)
    # below the floor never trips even with zero history
    t4c = "tDc"
    store["spend"][(t4c, "sms", _today())] = 100   # ₹1 < ₹5 floor
    check("4.below_floor_safe", (not cost_guards.check_anomaly(t4c).anomaly))

    # =====================================================================
    # GUARD #1 — PER-MESSAGE METERING (reserve BEFORE; settle on ok; RELEASE on fail; no debit)
    # =====================================================================
    print("\nGUARD #1 — per-message metering")
    # there is NO wallet.debit CALL anywhere in the comm package (the master plan: "wallet.debit()
    # does not exist — strike it everywhere"). We check the AST for an actual `.debit(...)` call,
    # not the docstring prose that *names* the anti-pattern to explain we don't use it.
    import comm.metering as _met_src
    import comm.engine as _eng_src
    import inspect, ast
    def _has_debit_call(mod):
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "debit":
                return True
        return False
    check("1.no_wallet_debit_call", (not _has_debit_call(_met_src)) and (not _has_debit_call(_eng_src)))
    # and the real ledger ops ARE used (reserve / settle / release)
    src_meter = inspect.getsource(_met_src)
    check("1.uses_reserve_settle_release",
          "w.reserve(" in src_meter and "w.settle(" in src_meter and "w.release(" in src_meter)

    os.environ["COMM_METERING_ENABLED"] = "1"
    w = _FakeWallet(funds=True)
    _install_fake_wallet(w)

    # a FREE send (cost 0) -> no hold taken (Telegram), ticket permissive
    tk = metering.reserve_for_send("tE", "cms_free", 0)
    check("1.free_no_hold", tk.hold_id is None and tk.reason == "free" and tk.ok)
    fin = metering.finalize(tk, sent_ok=True)
    check("1.free_finalize_noop", fin["charged_minor"] == 0)

    # a PAID send -> reserve a hold, settle the actual on success
    tk = metering.reserve_for_send("tE", "cms_paid", 700)
    check("1.paid_reserves_hold", tk.hold_id is not None and tk.reason == "reserved")
    check("1.reserve_idem_key", any(call[0] == "reserve" and call[3] == "reserve:comms:cms_paid"
                                    for call in w.calls))
    fin = metering.finalize(tk, sent_ok=True, actual_cost_minor=700)
    check("1.settle_charges_actual", any(call[0] == "settle" and call[2] == 700 for call in w.calls)
          and fin["charged_minor"] == 700)

    # a FAILED send -> RELEASE the hold (never bills)
    w.calls.clear()
    tk = metering.reserve_for_send("tE", "cms_fail", 700)
    fin = metering.finalize(tk, sent_ok=False)
    check("1.failed_send_releases", any(call[0] == "release" for call in w.calls)
          and not any(call[0] == "settle" for call in w.calls)
          and fin["charged_minor"] == 0)

    # insufficient funds -> ticket.ok False (the engine turns this into blocked_funds)
    w2 = _FakeWallet(funds=False)
    _install_fake_wallet(w2)
    tk = metering.reserve_for_send("tE", "cms_broke", 700)
    check("1.insufficient_funds_blocks", (not tk.ok) and tk.reason == "insufficient_funds")
    # metering OFF -> never touches the wallet (W1/W2 behaviour)
    os.environ["COMM_METERING_ENABLED"] = "0"
    w3 = _FakeWallet(funds=True)
    _install_fake_wallet(w3)
    tk = metering.reserve_for_send("tE", "cms_off", 700)
    check("1.metering_off_no_wallet", tk.hold_id is None and tk.reason == "metering_off"
          and len(w3.calls) == 0)
    os.environ["COMM_METERING_ENABLED"] = "1"

    # =====================================================================
    # GUARD #6 — PER-BOT TOKEN-BUCKET (pacing + priority lane)
    # =====================================================================
    print("\nGUARD #6 — per-bot token-bucket")
    os.environ["COMM_TOKEN_BUCKET_ENABLED"] = "1"
    os.environ["COMM_BUCKET_GLOBAL_RATE"] = "5"        # 5/s global (capacity 5)
    os.environ["COMM_BUCKET_PER_CHAT_RATE"] = "1"      # 1/s per chat
    os.environ["COMM_BUCKET_MAX_WAIT_S"] = "0"         # no-wait: prove the bucket empties

    token_bucket._reset_for_tests()
    bot = "pd_bot1"
    # the global capacity is 5 -> the first 5 normal sends to DISTINCT chats are granted, the 6th
    # (no-wait) is rejected because the global bucket is drained.
    grants = [_run(token_bucket.acquire(bot, f"chat_{i}", priority=False)) for i in range(6)]
    check("6.global_capacity_5", grants[:5] == [True]*5 and grants[5] is False)

    # per-chat pacing: refill, then 2 quick sends to ONE chat (capacity 2) ok, 3rd rejected no-wait
    token_bucket._reset_for_tests()
    os.environ["COMM_BUCKET_GLOBAL_RATE"] = "100"      # global not the limiter here
    g1 = _run(token_bucket.acquire(bot, "one_chat", priority=False))
    g2 = _run(token_bucket.acquire(bot, "one_chat", priority=False))
    g3 = _run(token_bucket.acquire(bot, "one_chat", priority=False))
    check("6.per_chat_paced", g1 and g2 and (g3 is False))

    # PRIORITY LANE: drain the global bucket, then a priority send STILL gets through (borrows)
    token_bucket._reset_for_tests()
    os.environ["COMM_BUCKET_GLOBAL_RATE"] = "2"
    _run(token_bucket.acquire(bot, "c1", priority=False))
    _run(token_bucket.acquire(bot, "c2", priority=False))
    normal_after_drain = _run(token_bucket.acquire(bot, "c3", priority=False))
    priority_after_drain = _run(token_bucket.acquire(bot, "c4", priority=True))
    check("6.global_drained_blocks_normal", normal_after_drain is False)
    check("6.priority_lane_bypasses_global", priority_after_drain is True)

    # disabled -> always grant instantly (no pacing)
    os.environ["COMM_TOKEN_BUCKET_ENABLED"] = "0"
    token_bucket._reset_for_tests()
    check("6.disabled_always_grants", all(_run(token_bucket.acquire(bot, "x")) for _ in range(20)))

    # =====================================================================
    # PERMISSIVE-ON-FAULT — guards never block when their datastore is gone
    # =====================================================================
    print("\nPERMISSIVE-ON-FAULT (a guard must never block on its own fault)")
    # point cost_guards at a 'down' engine
    class _DownEngine:
        def available(self):
            return False
        def session(self, **kw):
            raise RuntimeError("pg down")
    sys.modules["db.engine"].available = _DownEngine().available   # type: ignore
    sys.modules["db.engine"].session = _DownEngine().session       # type: ignore
    check("fault.deliverability_allows", not cost_guards.is_dead("tZ", "cZ", ch))
    check("fault.frequency_allows", cost_guards.check_frequency("tZ", "cZ", ch).allow)
    check("fault.budget_free_allows", cost_guards.check_budget("tZ", 0).allow)
    check("fault.precheck_allows", cost_guards.precheck_send("tZ", "cZ", ch, 0).allow)
    check("fault.anomaly_no_trip", not cost_guards.check_anomaly("tZ").anomaly)

    # =====================================================================
    # RESTING BYTE-IDENTICAL — guards OFF -> precheck always allows, no bookkeeping
    # =====================================================================
    print("\nRESTING (guards flag OFF -> permissive, no behaviour change)")
    os.environ["COMM_COST_GUARDS_ENABLED"] = "0"
    # reinstall a working fake db so the call could read if it tried
    _install_fake_db(store)
    gd = cost_guards.precheck_send("tA", "chat_5", ch, 9999)  # chat_5 is 'dead' but guards OFF
    check("resting.guards_off_allows_even_dead", gd.allow and gd.reason == "guards_off")

    # no agent.py imported anywhere in the new modules
    for modname in ("comm.cost_guards", "comm.metering", "comm.token_bucket"):
        src = inspect.getsource(sys.modules[modname])
        check(f"earner.no_agent_import:{modname}",
              not re.search(r"^\s*(import agent|from agent)\b", src, re.M))

    print(f"\n{'ALL PASS' if not fails else 'FAILURES: ' + ', '.join(fails)}")
    # cleanup env
    for k in list(os.environ):
        if k.startswith("COMM_"):
            os.environ.pop(k, None)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
